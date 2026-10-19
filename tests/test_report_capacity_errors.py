"""Explicitly authorized capacity retries remain counted and require a verified completion."""
import copy
import json
from pathlib import Path

import pytest

from test_report_cohort_identity import cohort, mutate, read, verify, write


@pytest.fixture
def capacity(cohort):
    audit = read(cohort / "B0.audit.json")
    task = Path(audit["task_path"])
    component = "Codex backend (fetch)"
    message = "\nSelected model is at capacity. Please try a different model.\nMissing or empty final message"
    failed = {"call_id": "failed", "purpose": "fetch", "model": "fixture-model", "attempt": 0,
              "prompt_sha256": "a" * 64, "prompt_chars": 123, "exit_code": 1, "response_chars": 0,
              "error": message, "retries": 0}
    completed = {**failed, "call_id": "completed", "attempt": 1, "exit_code": 0,
                 "response_chars": 12, "error": None, "retries": 1}
    def start(details):
        return {"component": component, "event": "exec.start", "details": {
            key: details[key] for key in ("call_id", "purpose", "model", "attempt", "prompt_sha256", "prompt_chars")}}
    events = [start(failed), {"component": component, "event": "exec.end", "details": failed},
              {"component": component, "event": "retry", "details": {
                  "attempt": 0, "next_attempt": 1, "delay_s": 1, "error": f"Codex failed (exit=1): {message}"}},
              start(completed), {"component": component, "event": "exec.end", "details": completed},
              {"component": "tools.fetch", "event": "call.end", "details": {"success": False}}]
    errors = [{**events[index], "line": index + 1} for index in (1, 2)]
    mutate(cohort, "B0.metrics.json", "errors", value=errors)
    metric = read(cohort / "B0.metrics.json")
    metric.update(codex_calls=2, codex_retries=1, failed_fetches=1,
                  signals=[{"type": "failed_fetch", "reason": "FETCH_FAILED"}])
    write(cohort / "B0.metrics.json", metric)
    (task.parent / "trace.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    (task / "codex_calls.jsonl").write_text(json.dumps(failed) + "\n" + json.dumps(completed) + "\n")
    policy = cohort / "capacity_error_policy.json"
    write(policy, {"user_instruction": "Count any capacity errors and retries as usual."})
    entries = [{"label": "B0", "run_id": audit["run_id"], "event": error,
                "classification": "external_capacity_retried", "policy": str(policy),
                "reason": "Provider capacity error followed by backend completion; fetched text remains FETCH_FAILED.",
                "failed_trace_line": 2, "retry_trace_line": 3, "recovery_start_line": 4,
                "recovery_trace_lines": [5]} for error in errors]
    mutate(cohort, "reviewed_error_events.json", "entries", value=entries)
    return cohort, task, events


def test_verified_capacity_retry_is_accepted_without_hiding_failed_fetch_or_error_counts(capacity):
    here, task, _ = capacity
    before = {path: path.read_bytes() for path in (here / "B0.metrics.json", task.parent / "trace.jsonl",
                                                  task / "codex_calls.jsonl")}
    result = verify(here)
    assert result.returncode == 0, result.stderr
    report = read(here / "report_verification.json")
    assert report["recorded_capacity_error_events"] == 2
    assert report["recorded_validation_errors"] == 0
    assert next(r for r in report["runs"] if r["label"] == "B0")["runtime_errors"] == 2
    assert all(path.read_bytes() == content for path, content in before.items())
    metric = read(here / "B0.metrics.json")
    assert metric["codex_retries"] == metric["failed_fetches"] == 1
    assert metric["signals"] == [{"type": "failed_fetch", "reason": "FETCH_FAILED"}]


@pytest.mark.parametrize("case", ["wrong_model", "wrong_purpose", "wrong_prompt", "wrong_schema", "same_attempt",
                                 "failed_completion", "empty_completion", "missing_start", "missing_retry",
                                 "wrong_retry_attempt", "wrong_retry_error", "missing_call_record",
                                 "wrong_call_record", "not_capacity", "tool_error", "missing_authorization"])
def test_capacity_exception_rejects_missing_or_mismatched_completion_evidence(capacity, case):
    here, task, events = capacity
    if case in {"wrong_model", "wrong_purpose", "wrong_prompt"}:
        key = {"wrong_model": "model", "wrong_purpose": "purpose", "wrong_prompt": "prompt_sha256"}[case]
        events[4]["details"][key] = "different"
    elif case == "wrong_schema":
        for index in (0, 1):
            events[index]["details"].update(schema_sha256="b" * 64, schema_chars=25)
        for index in (3, 4):
            events[index]["details"].update(schema_sha256="c" * 64, schema_chars=25)
        (task / "codex_calls.jsonl").write_text(json.dumps(events[1]["details"]) + "\n" + json.dumps(events[4]["details"]) + "\n")
    elif case == "same_attempt":
        events[4]["details"]["attempt"] = 0
    elif case == "failed_completion":
        events[4]["details"].update(exit_code=1, error="Unrelated failure")
    elif case == "empty_completion":
        events[4]["details"]["response_chars"] = 0
    elif case in {"missing_start", "missing_retry"}:
        events[3 if case == "missing_start" else 2]["event"] = "unrelated"
    elif case == "wrong_retry_attempt":
        events[2]["details"]["next_attempt"] = 4
    elif case == "wrong_retry_error":
        events[2]["details"]["error"] = "Different request failed"
    elif case == "missing_call_record":
        (task / "codex_calls.jsonl").write_text(json.dumps(events[1]["details"]) + "\n")
    elif case == "wrong_call_record":
        bad = copy.deepcopy(events[4]["details"])
        bad["prompt_sha256"] = "different"
        (task / "codex_calls.jsonl").write_text(json.dumps(events[1]["details"]) + "\n" + json.dumps(bad) + "\n")
    elif case == "not_capacity":
        events[1]["details"]["error"] = "ValueError: bad argument"
        events[2]["details"]["error"] = "Codex failed (exit=1): ValueError: bad argument"
    elif case == "tool_error":
        events[1]["component"], events[1]["event"] = "tools.check_constraint", "call.end"
    elif case == "missing_authorization":
        write(here / "capacity_error_policy.json", {"user_instruction": "Record deliberate citation assertions only."})
    (task.parent / "trace.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    # Keep reviewed and measured events identical so rejection must come from the
    # capacity/retry proof, not the existing exact-event guard.
    errors = [{**events[index], "line": index + 1} for index in (1, 2)]
    mutate(here, "B0.metrics.json", "errors", value=errors)
    review = read(here / "reviewed_error_events.json")
    for entry, error in zip(review["entries"], errors):
        entry["event"] = error
    write(here / "reviewed_error_events.json", review)
    result = verify(here)
    assert result.returncode != 0, "unproven capacity recovery was accepted"
    assert not (here / "report_verification.json").exists()
