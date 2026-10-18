"""Atomic durable archive primitives. No benchmark imports."""
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import fcntl
import hashlib
import json
import os
import tempfile
from .config import Config


def stamp():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
        name = f.name
    os.replace(name, path)


def read_json(path: Path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def append_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def read_jsonl(path: Path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []


def count_codex_calls(directory: Path, *, exclude_purposes=()):
    """Count dispatched attempts, including interrupted calls, once per identity."""
    calls = {record["call_id"]: record for path in (directory / "codex_attempts").glob("*.json")
             if (record := read_json(path)) is not None}
    legacy = []
    for record in read_jsonl(directory / "codex_calls.jsonl"):
        if record.get("call_id"):
            calls[record["call_id"]] = record
        else:
            legacy.append(record)
    return sum(record["purpose"] not in exclude_purposes for record in [*calls.values(), *legacy])


@dataclass
class RunContext:
    root: Path
    run_id: str
    config: Config
    task_id: str | None = None

    def __post_init__(self):
        self.root = self.root.resolve()
        for value in (self.run_id, self.task_id):
            if value is not None and (Path(value).name != value or value in (".", "..", "")):
                raise ValueError("Archive identifiers must be path-safe")

    @property
    def run_dir(self):
        return self.root / "runs" / self.run_id

    @property
    def path(self):
        return self.run_dir / self.task_id if self.task_id else self.run_dir

    def task(self, task_id):
        return RunContext(self.root, self.run_id, self.config, task_id)

    def save(self, name, value):
        write_json(self.path / name, value)

    def load(self, name, default=None):
        return read_json(self.path / name, default)

    def initialize(self, skills_sha, **metadata):
        self.path.mkdir(parents=True, exist_ok=True)
        snapshot = self.config.model_dump()
        existing = self.load("config.json")
        if existing is not None and Config.model_validate(existing).model_dump() != snapshot:
            raise ValueError("Cannot resume with changed configuration")
        if existing is None:
            self.save("config.json", snapshot)
        sha_file = self.path / "skills_sha.txt"
        if sha_file.exists() and sha_file.read_text().strip() != skills_sha:
            raise ValueError("Run library identity changed")
        sha_file.write_text(skills_sha + "\n")
        if not (self.path / "run_summary.json").exists():
            self.save("run_summary.json", {"created": stamp(), "skills_sha": skills_sha, **metadata})
