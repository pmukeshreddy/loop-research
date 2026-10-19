#!/usr/bin/env python3
"""Launch a JSON-defined research replay DAG after explicit preflight gates.

Without --launch, print the plan only. Never rollback, install, retry a failed
arm, stop another arm, or copy archives into the main runs directory. The
single coordinator owns manifest writes; each public CLI owns its own archive.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime

from replay_saved_refine import file_record, git, save, stamp, verify_installed_source


def load(path):
    return json.loads(Path(path).read_text())


def announce(kind, **details):
    print(json.dumps({"event": kind, **details}, ensure_ascii=False), flush=True)


def read_plan(path):
    plan = load(path)
    labels = [arm["label"] for arm in plan["arms"]]
    if len(labels) != len(set(labels)) or not labels:
        raise ValueError("Unique nonempty arm labels required")
    if any(not re.fullmatch(r"[A-Za-z0-9_-]+", label) for label in labels):
        raise ValueError("Arm labels must be path-safe")
    if sum(arm["workspace_mode"] == "main" for arm in plan["arms"]) > 1:
        raise ValueError("At most one arm may use the main workspace")
    visited = set()
    pending = plan["arms"][:]
    while pending:
        ready = [arm for arm in pending if set(arm.get("depends_on", [])) <= visited]
        if not ready:
            raise ValueError("Unknown dependency or cycle in replay plan")
        for arm in ready:
            if set(arm["base"]) not in ({"commit"}, {"from_arm"}):
                raise ValueError("Each arm requires one fixed or dependency-derived base")
            if "from_arm" in arm["base"] and arm["base"]["from_arm"] not in arm.get("depends_on", []):
                raise ValueError("Derived base must name an explicit dependency")
            if arm["workspace_mode"] not in {"main", "clone"}:
                raise ValueError("Unknown workspace mode")
            visited.add(arm["label"])
            pending.remove(arm)
    for record in plan["input_files"]:
        if file_record(Path(record["path"])) != record:
            raise ValueError(f"Planned input changed: {record['path']}")
    for arm in plan["arms"]:
        task = load(arm["task_file"])
        if task["benchmark"] != "research" or task.get("as_of_date") is not None:
            raise ValueError("Public-CLI replay requires a research task with its date supplied by config")
    return plan


def command_for(plan, arm, workspace, base):
    task = load(arm["task_file"])
    command = [plan["public_cli"], "--root", str(workspace), "--config", plan["config_file"],
               "research", task["question"]]
    for column in task["spec"]["columns"]:
        command += ["--columns", column]
    for key in task["spec"]["keys"]:
        command += ["--keys", key]
    command += ["--language", task["language"], "--trace", "--base", base]
    if not arm["learning"]:
        command.append("--no-learning")
    return command


def preflight(plan, expected_commit, audit_index):
    from loop_research.archive_audit import discover_runs
    from loop_research.config import Config

    root = Path(plan["main_root"])
    manifest = load(plan["manifest_file"])
    source = verify_installed_source(root, expected_commit)
    commit = source["commit"]
    if manifest["source_commit"] != commit:
        raise ValueError("Main manifest is not verified for the expected source")
    suite = manifest["unit_suite"]
    if suite.get("exit_code") != 0 or suite.get("source_commit") != commit or not suite.get("passed"):
        raise ValueError("A passing full suite on the expected source must be recorded first")
    replay = load(plan["saved_refine_execution"])
    results = replay.get("results", [])
    if (replay.get("status") != "complete" or replay["source_verification"]["commit"] != commit
            or {result["label"] for result in results} != set(plan["required_refine_cases"])
            or any(result.get("status") != "complete" or not result.get("strict_proposal_valid")
                   or not result.get("accounting_valid") or not result.get("original_inputs_unchanged")
                   or not result.get("original_harness_unchanged") for result in results)):
        raise ValueError("Saved-input refinement replays must pass strictly on the expected source first")
    index = load(audit_index)
    if Path(index["search_root"]).resolve() != (root / "runs").resolve():
        raise ValueError("Bulk audit must cover the full main runs tree")
    if any(run["errors"] for run in index["runs"]):
        raise ValueError("Bulk audit still reports archive errors")
    observed = {str(path) for path in discover_runs(index["search_root"], Path(audit_index).parent)}
    if {run["run_path"] for run in index["runs"]} != observed:
        raise ValueError("Bulk audit does not cover every currently observed run directory")
    for run in index["runs"]:
        for task in run["tasks"]:
            if not Path(task["audit_path"]).is_file():
                raise ValueError("Bulk audit is missing a task output")
    config = Config.load(plan["config_file"])
    if config.model_dump() != Config.load(plan["original_config_file"]).model_dump():
        raise ValueError("Replay configuration differs from the current proof configuration")
    if config.codex.max_concurrent != plan["shared_codex_max_concurrent"]:
        raise ValueError("Shared Codex concurrency differs from the plan")
    if any(arm["label"] in manifest["runs"] for arm in plan["arms"]):
        raise ValueError("Replay labels already completed; preserve/invalidate them explicitly before a new run")
    main = next((arm for arm in plan["arms"] if arm["workspace_mode"] == "main"), None)
    if main is not None and git(root / "harness", "rev-parse", "HEAD").strip() != main["base"]["commit"]:
        raise ValueError("Parent rollback/fork must leave main harness HEAD exactly at the planned base")
    if git(root / "harness", "status", "--porcelain"):
        raise ValueError("Main harness has uncommitted changes")
    return manifest, {"source": source, "unit_suite": suite,
                      "saved_refine_execution": file_record(Path(plan["saved_refine_execution"])),
                      "audit_index": file_record(Path(audit_index)), "audited_run_directories": len(observed),
                      "shared_codex_max_concurrent": config.codex.max_concurrent,
                      "public_cli_verifies_worker_isolation_per_run": True}


def clone_workspace(plan, arm, base, source_harness):
    workspace = Path(plan["workspace_parent"]) / arm["label"]
    workspace.mkdir(parents=True, exist_ok=False)
    clone = workspace / "harness"
    commands = [["git", "clone", "--no-local", "--no-checkout", str(source_harness), str(clone)],
                ["git", "-C", str(clone), "checkout", "-b", "replay-start", base],
                ["git", "-C", str(clone), "config", "user.name", "Research replay"],
                ["git", "-C", str(clone), "config", "user.email", "replay@localhost"]]
    for command in commands:
        subprocess.run(command, check=True, capture_output=True, text=True)
    if (clone / ".git/objects/info/alternates").exists() or (clone / ".git/shallow").exists():
        raise ValueError("Replay clone must be full and have independent objects")
    for name in ("runs", "reports", "cache"):
        (workspace / name).mkdir()
    actual = git(clone, "rev-parse", "HEAD").strip()
    if actual != base:
        raise ValueError("Clone base mismatch")
    proof = {"workspace": str(workspace), "git_dir": str((clone / ".git").resolve()),
             "source_git_dir": str((source_harness / ".git").resolve()),
             "runs_directory": str(workspace / "runs"), "cache_directory": str(workspace / "cache"),
             "task_cache_note": "Actual tool caches are per-task tool_cache.json under this workspace's runs.",
             "full_clone": True, "alternates": False, "clone_commands": commands, "base": actual,
             "base_state_sha256": file_record(clone / "harness_state.json")["sha256"]}
    return workspace, proof


def unchanged_source(plan, verification):
    root = Path(plan["main_root"])
    return (git(root, "rev-parse", "HEAD").strip() == verification["commit"]
            and all(file_record(root / item["source"])["sha256"] == item["sha256"]
                    and file_record(Path(item["installed"]))["sha256"] == item["sha256"]
                    for item in verification["modules"]))


def announced_archive(console, workspace, *, finished=False):
    """Read this CLI's ownership announcement; other directories are irrelevant."""
    parts = Path(console).read_bytes().split(b"\n")
    lines = [part.decode("utf-8") for part in parts[:-1] if part.startswith(b"Watch live:")]
    if finished and parts[-1].startswith(b"Watch live:"):
        raise ValueError("Incomplete archive announcement")
    if not lines and not finished:
        return None
    if len(lines) != 1:
        raise ValueError(f"Expected exactly one archive announcement, found {len(lines)}")
    line = lines[0]
    try:
        words = shlex.split(line)
    except ValueError as exc:
        raise ValueError(f"Invalid archive announcement: {exc}") from exc
    if not line.startswith("Watch live: tail -f ") or len(words) != 5 or words[:4] != ["Watch", "live:", "tail", "-f"]:
        raise ValueError("Invalid archive announcement command")
    trace = Path(words[4])
    expected_runs = Path(workspace).resolve() / "runs"
    if (not trace.is_absolute() or trace != trace.resolve() or trace.name != "trace.log"
            or trace.parent.parent != expected_runs
            or not re.fullmatch(r"research-[0-9a-f]{32}", trace.parent.name)):
        raise ValueError("Archive announcement must name this workspace's canonical research trace.log")
    if finished and (not trace.is_file() or not (trace.parent / "research.json").is_file()):
        raise ValueError("Archive announcement has no durable trace or research record")
    return trace.parent, line


def launch(plan_path, plan, expected_commit, audit_index, poll_seconds):
    manifest_path = Path(plan["manifest_file"])
    lock = (manifest_path.parent / "replay_coordinator.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    manifest, gates = preflight(plan, expected_commit, audit_index)
    log_root = Path(plan["log_directory"])
    log_root.mkdir(parents=True, exist_ok=False)
    Path(plan["workspace_parent"]).mkdir(parents=True, exist_ok=False)
    shutil.copyfile(manifest_path, log_root / "manifest_before.json")
    shutil.copyfile(plan_path, log_root / "plan.json")
    state_path = log_root / "coordinator.json"
    state = {"status": "running", "started_at": stamp(), "command": [sys.executable, *sys.argv],
             "plan": file_record(plan_path), "preflight": gates, "arms": {}, "overlaps": [],
             "timestamp_note": "UTC process starts are recorded immediately before Popen; ends are observed on poll. "
                               "Overlap is process-lifetime overlap, not a statistical or behavioral result."}
    for arm in plan["arms"]:
        state["arms"][arm["label"]] = {"status": "pending", "depends_on": arm.get("depends_on", [])}
    manifest["replay_coordinator"] = str(state_path)
    manifest["replay_preflight"] = gates
    active = {}
    terminal = {"complete", "failed", "not_launched"}

    def persist():
        manifest["replay_processes"] = state["arms"]
        save(state_path, state)
        save(manifest_path, manifest)

    def mark_failed(label, error, status="failed"):
        record = state["arms"][label]
        record.update(status=status, error=str(error), ended_at=stamp())
        manifest.setdefault("failed_runs", []).append({"label": label, **record})
        announce(status, label=label, error=str(error), pid=record.get("pid"))
        persist()

    def discover(label, finished=False):
        record = state["arms"][label]
        try:
            if record.get("archive_ownership_error"):
                raise ValueError(record["archive_ownership_error"])
            owned = announced_archive(record["console"], record["workspace"], finished=finished)
            if owned is None:
                return None
            run, line = owned
            if "run_id" in record and record["run_id"] != run.name:
                raise ValueError("Archive announcement changed identity")
            if "run_id" not in record:
                record.update(run_id=run.name, run_path=str(run), archive_announcement=line,
                              trace_tail_command=shlex.join(["tail", "-f", str(run / "trace.log")]))
                announce("trace", label=label, command=record["trace_tail_command"])
                persist()
            return run
        except Exception as exc:
            if finished:
                raise
            # Keep observing the owned process through its natural exit, even
            # when its announcement is invalid. Never stop sibling arms.
            if not record.get("archive_ownership_error"):
                record["archive_ownership_error"] = f"{type(exc).__name__}: {exc}"
                persist()
            return None

    persist()
    announce("preflight_passed", **gates)
    try:
        while any(record["status"] not in terminal for record in state["arms"].values()):
            ready = []
            for arm in plan["arms"]:
                label = arm["label"]
                if state["arms"][label]["status"] != "pending":
                    continue
                dependencies = [state["arms"][name] for name in arm.get("depends_on", [])]
                if any(dependency["status"] in {"failed", "not_launched"} for dependency in dependencies):
                    mark_failed(label, "Required dependency did not complete successfully", "not_launched")
                elif all(dependency["status"] == "complete" for dependency in dependencies):
                    ready.append(arm)
            # Prepare the entire ready cohort before any launch, so initial clones
            # are copied before the main arm can begin changing its own harness.
            for arm in ready:
                label = arm["label"]
                try:
                    if not unchanged_source(plan, gates["source"]):
                        raise ValueError("Source changed after preflight; no new arm will launch")
                    base = arm["base"].get("commit")
                    source_harness = Path(plan["main_root"]) / "harness"
                    if base is None:
                        dependency = state["arms"][arm["base"]["from_arm"]]
                        base = dependency["record"]["harness_head"]
                        source_harness = Path(dependency["workspace"]) / "harness"
                    if arm["workspace_mode"] == "clone":
                        workspace, isolation = clone_workspace(plan, arm, base, source_harness)
                    else:
                        workspace = Path(plan["main_root"])
                        isolation = {"workspace": str(workspace), "main_arm": True,
                                     "git_dir": str(workspace / "harness/.git"), "base": base}
                    record = state["arms"][label]
                    record.update(status="prepared", workspace=str(workspace), base=base,
                                  source_commit=gates["source"]["commit"], isolation=isolation,
                                  command=command_for(plan, arm, workspace, base))
                    manifest.setdefault("workspace_roots", {})[label] = str(workspace)
                    announce("workspace_isolation", label=label, **isolation)
                except Exception as exc:
                    mark_failed(label, f"Preparation failed: {type(exc).__name__}: {exc}", "not_launched")
            for arm in ready:
                label, record = arm["label"], state["arms"][arm["label"]]
                if record["status"] != "prepared":
                    continue
                stream = None
                try:
                    console = log_root / (label + ".console.log")
                    stream = console.open("x")
                    started_at = stamp()
                    process = subprocess.Popen(record["command"], cwd=plan["main_root"],
                                               stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
                    active[label] = {"process": process, "stream": stream}
                    record.update(status="running", pid=process.pid, started_at=started_at, console=str(console),
                                  console_tail_command=shlex.join(["tail", "-f", str(console)]))
                    manifest.setdefault("commands", {})[label] = record["command"]
                    announce("started", label=label, pid=process.pid, command=shlex.join(record["command"]),
                             tail=record["console_tail_command"])
                    persist()
                except Exception as exc:
                    if stream is not None:
                        stream.close()
                    mark_failed(label, f"Launch failed: {type(exc).__name__}: {exc}")
            for label in list(active):
                item, record = active[label], state["arms"][label]
                code = item["process"].poll()
                discover(label)
                if code is None:
                    continue
                record.update(exit_code=code, ended_at=stamp())
                item["stream"].close()
                try:
                    run = discover(label, finished=True)
                    archived = load(run / "research.json")
                    arm = next(arm for arm in plan["arms"] if arm["label"] == label)
                    if archived.get("run_id") != run.name or archived.get("task_id") != load(arm["task_file"])["task_id"]:
                        raise ValueError("Durable archive identity differs from its announcement or planned task")
                    record["record"] = archived
                    inventory = [{"relative_path": str(path.relative_to(run)), **file_record(path)}
                                 for path in sorted(run.rglob("*")) if path.is_file()]
                    save(log_root / (label + ".archive_hashes.json"), inventory)
                    record["archive_hashes"] = str(log_root / (label + ".archive_hashes.json"))
                    record["source_unchanged"] = unchanged_source(plan, gates["source"])
                    if code != 0 or archived["status"] != "complete" or archived.get("error"):
                        raise ValueError(f"CLI exit {code}; durable status {archived['status']}; {archived.get('error')}")
                    if not record["source_unchanged"]:
                        raise ValueError("Source changed during this arm")
                    record["status"] = "complete"
                    manifest["runs"][label] = run.name
                    if arm.get("publish_head"):
                        manifest[arm["publish_head"]] = archived["harness_head"]
                    announce("complete", label=label, run_id=run.name, head=archived["harness_head"])
                    persist()
                except Exception as exc:
                    mark_failed(label, f"{type(exc).__name__}: {exc}")
                del active[label]
            if active or any(record["status"] == "pending" for record in state["arms"].values()):
                time.sleep(poll_seconds)
        ended = [(label, record) for label, record in state["arms"].items() if "started_at" in record]
        for i, (left, a) in enumerate(ended):
            for right, b in ended[i + 1:]:
                start = max(datetime.fromisoformat(a["started_at"]), datetime.fromisoformat(b["started_at"]))
                end = min(datetime.fromisoformat(a["ended_at"]), datetime.fromisoformat(b["ended_at"]))
                state["overlaps"].append({"arms": [left, right], "overlap_s": max(0, (end - start).total_seconds())})
        state["status"] = "complete" if all(record["status"] == "complete" for record in state["arms"].values()) else "failed"
    except BaseException as exc:
        # Deliberately do not signal independently owned CLI process sessions.
        state.update(status="coordinator_interrupted", error=f"{type(exc).__name__}: {exc}",
                     processes_left_running={label: item["process"].pid for label, item in active.items()
                                             if item["process"].poll() is None})
        announce("coordinator_interrupted", **state["processes_left_running"])
        raise
    finally:
        state["ended_at"] = stamp()
        persist()
        lock.close()
    return 0 if state["status"] == "complete" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--expected-source-commit")
    parser.add_argument("--audit-index", type=Path)
    parser.add_argument("--poll-seconds", type=float, default=0.25)
    args = parser.parse_args()
    plan = read_plan(args.plan.resolve())
    if not args.launch:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    if not args.expected_source_commit or args.audit_index is None or args.poll_seconds <= 0:
        parser.error("--launch requires --expected-source-commit, --audit-index and positive polling interval")
    return launch(args.plan.resolve(), plan, args.expected_source_commit, args.audit_index.resolve(), args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
