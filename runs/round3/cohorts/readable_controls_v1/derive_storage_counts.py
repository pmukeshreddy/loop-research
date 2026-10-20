"""Read-only report derivation, never used by the research runtime or launch gate."""

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def record(path):
    data = path.read_bytes()
    return {"path": str(path.resolve()), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def derive(directory, labels):
    execution_path = directory / "execution.json"
    execution = json.loads(execution_path.read_text())
    result = {
        "source_commit": execution["source_commit"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "fetch_path": "direct-readable-v1",
        "definition": "Raw bytes: distinct archived HTTP response-body .raw paths, including retained redirects/failures; no wire-overhead claim. Text counts: successful evidence-store strings; hash dedup across URL values without normalization.",
        "execution_receipt": record(execution_path),
        "derivation_receipt": record(Path(__file__)),
        "runs": {},
    }
    for label in labels:
        arm = execution["arms"][label]
        assert arm["status"] == "complete" and arm["exit_code"] == 0
        assert arm["source_unchanged"] is True
        assert arm["source_commit"] == execution["source_commit"]
        run = Path(arm["run_path"])
        assert run.name == arm["run_id"]
        task = run / arm["task_id"]
        evidence_path = task / "evidence.json"
        evidence = json.loads(evidence_path.read_text())
        raw = [record(path) for path in sorted((task / "downloads").glob("*.raw"))]
        groups = defaultdict(list)
        lengths = {}
        ordinary = 0
        instances = 0
        for url, texts in sorted(evidence.get("fetched", {}).items()):
            for index, text in enumerate(texts):
                assert isinstance(text, str)
                digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
                groups[digest].append({"url": url, "text_index": index, "characters": len(text)})
                assert digest not in lengths or lengths[digest] == len(text)
                lengths[digest] = len(text)
                ordinary += len(text)
                instances += 1
        metrics = {
            "downloaded_raw_artifact_bytes": sum(row["bytes"] for row in raw),
            "retained_text_instances": instances,
            "unique_text_hashes": len(groups),
            "whole_text_hash_dedup_readable_characters": sum(lengths.values()),
        }
        assert metrics["unique_text_hashes"] <= instances
        assert metrics["whole_text_hash_dedup_readable_characters"] <= ordinary
        result["runs"][label] = {
            "run_id": arm["run_id"], "metrics": metrics,
            "ordinary_readable_characters": ordinary,
            "evidence_receipt": record(evidence_path),
            "archive_inventory_receipt": arm["archive_hashes"],
            "raw_artifacts": raw,
            "text_hash_groups": dict(sorted(groups.items())),
        }
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--labels", nargs="+", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    assert not args.output.exists(), "Preserve prior derivations; choose a new output path"
    derived = derive(args.directory.resolve(), args.labels)
    args.output.write_text(json.dumps(derived, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({label: row["metrics"] for label, row in derived["runs"].items()}, indent=2))
