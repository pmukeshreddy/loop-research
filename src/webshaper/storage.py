"""Durable checkpoints and conservative call accounting, including unknown outcomes."""
import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from .models import Budget


def dump(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(value):
    return hashlib.sha256((value if isinstance(value, bytes) else dump(value).encode())).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


class BudgetExceeded(RuntimeError):
    pass


class UncertainCall(RuntimeError):
    pass


class SubscriptionLimit(RuntimeError):
    pass


class Journal:
    def __init__(self, path: Path, config: dict, budget: Budget):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.budget = budget
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS records (kind TEXT, id TEXT, value TEXT, PRIMARY KEY(kind,id));
            CREATE TABLE IF NOT EXISTS calls (
                key TEXT PRIMARY KEY, role TEXT, status TEXT, reserved_usd REAL, reserved_tokens INTEGER,
                searches INTEGER, cost_usd REAL, tokens INTEGER, result TEXT, started TEXT, ended TEXT,
                error TEXT, latency REAL DEFAULT 0);
        """)
        frozen = {"config": config, "budget": budget.model_dump(mode="json")}
        old = self.get("frozen")
        if old is not None and old != frozen:
            self.db.close()
            raise ValueError("run configuration is frozen; start a new run")
        self.put("frozen", frozen)
        # The process holding a reservation is gone when a run is reopened.
        self.db.execute("UPDATE calls SET status='uncertain' WHERE status='pending'")
        self.db.commit()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.db.close()

    def get(self, key):
        with self.lock:
            row = self.db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else None

    def put(self, key, value):
        with self.lock, self.db:
            self.db.execute("INSERT OR REPLACE INTO kv VALUES (?,?)", (key, dump(value)))

    def record(self, kind, record_id, value):
        encoded = dump(value)
        with self.lock, self.db:
            old = self.db.execute("SELECT value FROM records WHERE kind=? AND id=?", (kind, record_id)).fetchone()
            if old and old[0] != encoded:
                raise ValueError(f"immutable {kind} record already exists: {record_id}")
            self.db.execute("INSERT OR IGNORE INTO records VALUES (?,?,?)", (kind, record_id, encoded))

    def records(self, kind):
        with self.lock:
            return [json.loads(r[0]) for r in self.db.execute(
                "SELECT value FROM records WHERE kind=? ORDER BY id", (kind,))]

    def usage(self):
        with self.lock:
            rows = list(self.db.execute("SELECT * FROM calls"))
        return {
            "calls": len(rows),
            "completed_calls": sum(r["status"] == "complete" for r in rows),
            "uncertain_calls": sum(r["status"] in ("pending", "uncertain") for r in rows),
            "cost_usd": sum(r["cost_usd"] or 0 for r in rows),
            "cost_upper_bound_usd": sum(r["cost_usd"] if r["cost_usd"] is not None else r["reserved_usd"] for r in rows),
            "tokens": sum(r["tokens"] or 0 for r in rows),
            "token_upper_bound": sum(r["tokens"] if r["tokens"] is not None else r["reserved_tokens"] for r in rows),
            "searches": sum(r["searches"] for r in rows),
            "latency_seconds": sum(r["latency"] for r in rows),
        }

    def reserve(self, key, role, usd, tokens, searches):
        with self.lock, self.db:
            row = self.db.execute("SELECT * FROM calls WHERE key=?", (key,)).fetchone()
            if row:
                if row["status"] == "complete":
                    return json.loads(row["result"])
                if row["status"] == "limited":
                    raise SubscriptionLimit("subscription limit: resume with --retry-limited after reset")
                raise UncertainCall("call outcome unknown; inspect journal before explicit retry")
            use = self.usage()
            if (use["cost_upper_bound_usd"] + usd > self.budget.max_usd + 1e-9
                    or use["token_upper_bound"] + tokens > self.budget.max_tokens
                    or use["searches"] + searches > self.budget.max_searches
                    or use["calls"] + 1 > self.budget.max_calls):
                raise BudgetExceeded("run budget exhausted before dispatch")
            self.db.execute("INSERT INTO calls(key,role,status,reserved_usd,reserved_tokens,searches,started) "
                            "VALUES (?,?,'pending',?,?,?,?)", (key, role, usd, tokens, searches, now()))
        return None

    def complete(self, key, result, usd, tokens, searches=None, latency=0):
        with self.lock, self.db:
            self.db.execute("UPDATE calls SET status='complete',result=?,cost_usd=?,tokens=?,ended=?,latency=? "
                            "WHERE key=?", (dump(result), usd, tokens, now(), latency, key))
            if searches is not None:
                self.db.execute("UPDATE calls SET searches=? WHERE key=?", (searches, key))

    def fail(self, key, status, code, latency=0):
        with self.lock, self.db:
            self.db.execute("UPDATE calls SET status=?,error=?,ended=?,latency=? WHERE key=?",
                            (status, code, now(), latency, key))

    def retry_limited(self):
        # Preserve failed attempts and their conservative usage before allocating a new call.
        with self.lock, self.db:
            for row in self.db.execute("SELECT key FROM calls WHERE status='limited'").fetchall():
                self.db.execute("UPDATE calls SET key=? WHERE key=?", (row[0] + ":limited:" + now(), row[0]))

    def calls(self):
        with self.lock:
            return [dict(r) for r in self.db.execute("SELECT * FROM calls ORDER BY started,key")]
