"""CLI entry points; no credentials or secrets are accepted in configuration files."""
import argparse
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

from .generation import SearchResults
from .models import RunConfig
from .pipeline import frozen_config, run, run_lock
from .providers import CodexProvider, ModelGateway
from .storage import Journal, digest, now


def load_config(path):
    path = Path(path).resolve()
    data = json.loads(path.read_text())
    for source in data.get("sources", []):
        if not source["origin"].startswith(("https://", "http://")):
            source["origin"] = str((path.parent / source["origin"]).resolve())
    return RunConfig.model_validate(data)


def saved_frozen(root):
    """Read authoritative generation settings without touching call status.

    Export/review may use newer code, but can neither dispatch generation nor
    replace the original acceptance rules. Never trust an edited export manifest.
    """
    path = (Path(root) / "run.sqlite").resolve()
    if not path.is_file():
        raise ValueError("run journal does not exist")
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        row = db.execute("SELECT value FROM kv WHERE key='frozen'").fetchone()
        if row is None:
            raise ValueError("run journal has no frozen configuration")
        return json.loads(row[0])
    finally:
        db.close()


def main(argv=None):
    parser = argparse.ArgumentParser(prog="webshaper", description="Open-web research QA generation; Codex subscription or labeled fixtures")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="write editable configuration; never overwrite")
    init.add_argument("--mode", choices=["fixture", "live"], default="live")
    init.add_argument("--output", type=Path, required=True)
    execute = sub.add_parser("run", help="run or resume the same frozen configuration")
    execute.add_argument("--config", type=Path, required=True)
    execute.add_argument("--run-dir", type=Path, required=True)
    execute.add_argument("--retry-limited", action="store_true", help="explicitly retry subscription-limited calls after reset")
    execute.add_argument("--budget-extension", type=Path,
                         help="explicit additive subscription-usage authorization JSON; never changes $0 paid limit")
    doctor = sub.add_parser("doctor", help="verify CLI auth/flags without reading tokens")
    doctor.add_argument("--config", type=Path, required=True)
    doctor.add_argument("--probe-search", action="store_true", help="uses one bounded subscription session")
    doctor.add_argument("--run-dir", type=Path, default=Path("runs/diagnostics"))
    for name in ("status", "export"):
        command = sub.add_parser(name)
        command.add_argument("--run-dir", type=Path, required=True)
    review = sub.add_parser("review", help="record an actual human review of a live task")
    review.add_argument("--run-dir", type=Path, required=True)
    review.add_argument("--task-id", required=True)
    review.add_argument("--decision", choices=["approved", "rejected"], required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--notes", required=True)
    schemas = sub.add_parser("schemas", help="export machine-readable JSON schemas")
    schemas.add_argument("--output", type=Path, default=Path("schemas"))
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            from .fixtures import fixture_config
            from .models import Budget, CampaignConfig, ModelConfig
            config = fixture_config() if args.mode == "fixture" else RunConfig(
                as_of=date.today(), research_mode="open_web", campaign=CampaignConfig(), target_tasks=250,
                max_seed_attempts=750, layers=2, browsing_attempts=1, shortcut_audit_rate=1,
                solver=ModelConfig(max_searches_per_call=4), verifier=ModelConfig(max_searches_per_call=4),
                budget=Budget(max_tokens=1_447_740, max_calls=49, max_searches=13))
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x") as f:
                f.write(config.model_dump_json(indent=2) + "\n")
            print(f"Wrote {args.output}; mode={config.mode}, additional paid budget=$0")
        elif args.command == "run":
            from .models import BudgetExtension
            extension = BudgetExtension.model_validate_json(args.budget_extension.read_text()) if args.budget_extension else None
            stats = run(load_config(args.config), args.run_dir, args.retry_limited, extension)
            print(json.dumps(stats, indent=2, sort_keys=True))
            return 0 if stats["status"] == "completed" else (75 if stats["status"] == "paused" else 1)
        elif args.command == "status":
            print(json.dumps(json.loads((args.run_dir / "export/manifest.json").read_text())["stats"], indent=2, sort_keys=True))
        elif args.command in ("export", "review"):
            from .export import export_dataset
            frozen = saved_frozen(args.run_dir)
            config = RunConfig.model_validate(frozen["config"]["config"])
            with run_lock(args.run_dir), Journal(args.run_dir / "run.sqlite", frozen["config"], config.budget) as journal:
                if args.command == "review":
                    candidates = journal.get("final_candidates") or []
                    ids = {c["task"]["task_id"] for c in candidates}
                    public_ids = {"task-" + digest([journal.get("campaign_public_id_salt"), internal])[:32]: internal
                                  for internal in ids} if config.campaign else {}
                    internal_id = public_ids.get(args.task_id, args.task_id)
                    if config.mode != "live" or internal_id not in ids:
                        raise ValueError("manual review requires an accepted live task ID")
                    journal.record("manual_reviews", internal_id, {"task_id": internal_id, "decision": args.decision,
                                   "reviewer": args.reviewer, "notes": args.notes, "reviewed_at": now()})
                stats = export_dataset(journal, config, args.run_dir)
            print(json.dumps(stats, indent=2, sort_keys=True))
        elif args.command == "doctor":
            config = load_config(args.config)
            if config.mode == "fixture":
                print(json.dumps({"mode": "fixture", "network": "disabled", "paid_budget_usd": 0}))
                return 0
            provider = CodexProvider(config.generator)
            report = provider.preflight()
            report["search"] = "configured; not probed"
            if args.probe_search:
                with run_lock(args.run_dir), Journal(args.run_dir / "run.sqlite", frozen_config(config), config.budget) as journal:
                    gateway = ModelGateway(journal, {"generator": provider})
                    from .web_validation import observed_browsing
                    result, observation = gateway.call_observed("generator", "probe", {}, SearchResults, "search-probe", web=True)
                    report["search"] = "verified" if result.capability_available and observed_browsing(observation) else "unavailable"
                    report["result"] = result.model_dump(mode="json")
                    report["observation"] = observation
                    report["usage"] = journal.usage()
                if report["search"] != "verified":
                    print(json.dumps(report, indent=2))
                    return 1
            print(json.dumps(report, indent=2, sort_keys=True))
        elif args.command == "schemas":
            from . import models
            from .generation import Extraction
            args.output.mkdir(parents=True, exist_ok=True)
            classes = [getattr(models, n) for n in ("Source", "Evidence", "Entity", "Fact", "Bundle", "Query",
                        "PublicTask", "Candidate", "Validation", "RunConfig", "SemanticAssessment", "SolverAnswer",
                        "WebSolverAnswer", "AlternativeReview", "WebGrade", "CampaignConfig", "BudgetExtension")]
            from .discovery import CompanyDiscovery, CompanyAssessment, CompanySources
            classes.extend([Extraction, CompanyDiscovery, CompanyAssessment, CompanySources])
            for cls in classes:
                (args.output / (cls.__name__ + ".json")).write_text(json.dumps(cls.model_json_schema(), indent=2) + "\n")
            print(f"Wrote {len(classes)} schemas to {args.output}")
        return 0
    except (ValueError, OSError, RuntimeError) as error:
        print(f"webshaper: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
