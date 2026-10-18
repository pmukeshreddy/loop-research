"""Explicit collection-only repair continuation; old journals and snapshots are read-only."""
import json
import sqlite3
from pathlib import Path

from .sources import SourceStore, extract_document
from .storage import digest


def import_collection_run(parent_dir, root, config, journal):
    parent_dir, root = Path(parent_dir).resolve(), Path(root).resolve()
    if parent_dir == root:
        raise ValueError("collection repair requires a new run directory")
    old = sqlite3.connect((parent_dir / "run.sqlite").as_uri() + "?mode=ro", uri=True)
    old.row_factory = sqlite3.Row
    try:
        frozen = json.loads(old.execute("SELECT value FROM kv WHERE key='frozen'").fetchone()[0])
        previous = frozen["config"]["config"]
        for field in ("research_mode", "mode", "as_of", "scope", "campaign"):
            if previous.get(field) != config.model_dump(mode="json").get(field):
                raise ValueError("repair continuation cannot change mode, cutoff, scope or campaign acceptance settings")
        if previous.get("research_mode") != "open_web" or not config.campaign:
            raise ValueError("repair continuation requires an open-web campaign")
        if old.execute("SELECT count(*) FROM records WHERE kind IN ('candidates','candidate_attempts','validations')").fetchone()[0]:
            raise ValueError("collection-only repair cannot import generated tasks or validation checkpoints")
        calls = [dict(r) for r in old.execute("SELECT * FROM calls ORDER BY started,key")]
        if any(c["status"] != "complete" for c in calls):
            raise ValueError("parent has unresolved or subscription-limited calls; inspect before continuation")
        run_id = digest([str(parent_dir), frozen, calls])
        saved = journal.get("repair_parent")
        if saved:
            if saved != run_id:
                raise ValueError("repair parent is frozen")
            return
        if journal.calls() or journal.records("companies"):
            raise ValueError("repair import must initialize an empty run")
        record_rows = list(old.execute("SELECT kind,id,value FROM records ORDER BY kind,id"))
        kv_rows = list(old.execute("SELECT key,value FROM kv ORDER BY key"))
        parent_store, store = SourceStore(parent_dir / "sources"), SourceStore(root / "sources")
        source_rows = []
        for source in parent_store.all():
            parent_store.read(source)
            raw = (parent_store.root / source.raw_path).read_bytes()
            result = extract_document(raw, source.content_type, source.final_url or source.url_or_local_origin)
            repaired = store.capture_document(source.final_url or source.url_or_local_origin, raw, result,
                original_url=source.original_url or source.url_or_local_origin,
                final_url=source.final_url or source.url_or_local_origin,
                redirect_chain=source.redirect_chain, content_type=source.content_type, retrieved_at=source.retrieved_at)
            source_rows.append({"parent_source": source.model_dump(mode="json"), "source": repaired.model_dump(mode="json")})
        # Atomic journal import. A crash before commit leaves only immutable snapshots, safe to reuse.
        with journal.lock, journal.db:
            from .storage import dump
            for call in calls:
                key = "inherited:" + run_id[:16] + ":" + call["key"]
                call["key"] = key
                journal.db.execute("INSERT INTO calls(" + ",".join(call) + ") VALUES (" + ",".join("?" for _ in call) + ")", tuple(call.values()))
            for row in record_rows:
                kind = row["kind"]
                if kind in {"companies", "company_discovery", "company_source_searches"}:
                    identifier = "inherited:" + run_id[:16] + ":" + row["id"] if kind == "company_source_searches" else row["id"]
                    journal.db.execute("INSERT INTO records VALUES (?,?,?)", (kind, identifier, row["value"]))
                else:
                    journal.db.execute("INSERT INTO records VALUES (?,?,?)", ("parent_" + kind, row["id"], row["value"]))
            # Discovery has already happened; failed qualifications need reevaluation with repaired dates.
            for row in kv_rows:
                if row["key"].startswith("discovery:") and not row["key"].endswith(":queue"):
                    journal.db.execute("INSERT INTO kv VALUES (?,?)", (row["key"], row["value"]))
            for i, record in enumerate(source_rows):
                journal.db.execute("INSERT INTO records VALUES (?,?,?)", ("source_repairs", str(i), dump(record)))
            provenance = {"parent_run": str(parent_dir), "parent_frozen": frozen, "parent_calls": len(calls),
                          "inherited_tokens": sum(c["tokens"] or 0 for c in calls), "inherited_actions": sum(c["searches"] for c in calls),
                          "source_snapshots": len(source_rows), "reason": "Re-extract publication attribution; requalify without changing validation gates."}
            journal.db.execute("INSERT INTO records VALUES (?,?,?)", ("inherited_runs", run_id, dump(provenance)))
            journal.db.execute("INSERT INTO kv VALUES (?,?)", ("repair_parent", dump(run_id)))
    finally:
        old.close()
