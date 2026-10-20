"""Offline transport regressions for deterministic provider input rejection."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from loop_research.archive import count_codex_calls, read_jsonl
from loop_research.codex_backend import CallBudget, CodexBackend, CodexError, INSTRUCTION
from loop_research.trace import Trace


# Verbatim CLI error line archived by fair_slots_v1/A, trace 1866. It is provider
# metadata, not an inferred limit or a phrase searched in model/source content.
INPUT_ERROR = (
    'Error: turn/start: turn/start failed: Input exceeds the maximum length of '
    '1048576 characters. (code -32602), data: {"input_error_code":"input_too_large",'
    '"max_chars":1048576,"actual_chars":1592078}'
)
STRUCTURED_ERROR = {
    "code": -32602,
    "message": "Input exceeds the maximum length of 1048576 characters.",
    "data": {"input_error_code": "input_too_large", "max_chars": 1048576, "actual_chars": 1592078},
}


def run_failed(ctx, stdout="", stderr="", *, retries=4, response="", exit_code=1):
    ctx.config.codex.max_retries = retries
    ctx.trace = Trace(ctx.path)
    budget = CallBudget(20, 30)
    waits, events = [], []

    def runner(command, **kwargs):
        Path(command[command.index("--output-last-message") + 1]).write_text(response)
        return SimpleNamespace(returncode=exit_code, stdout=stdout, stderr=stderr)

    backend = CodexBackend(ctx, runner=runner, budget=budget, sleep=waits.append, jitter=lambda: 0)
    with pytest.raises(CodexError) as caught:
        backend.complete("unchanged input", purpose="refine", on_attempt=events.append)
    return backend, caught.value, budget, waits, events


@pytest.mark.parametrize("channel", ["cli_stderr", "error_event", "turn_failed_event"])
def test_permanent_provider_input_rejection_records_one_attempt_without_retry(ctx, channel):
    ctx.config.codex.max_concurrent = 1
    stdout = "" if channel == "cli_stderr" else json.dumps({
        "type": "error" if channel == "error_event" else "turn.failed",
        "error": STRUCTURED_ERROR,
    })
    stderr = INPUT_ERROR if channel == "cli_stderr" else ""
    backend, error, budget, waits, events = run_failed(ctx, stdout, stderr)
    records = read_jsonl(ctx.path / "codex_calls.jsonl")
    # Repeating deterministic rejection wastes reservations and dispatches, even
    # when the retries are configured and would otherwise be available.
    assert count_codex_calls(ctx.path) == budget.count == len(records) == 1
    assert waits == []
    assert [event["status"] for event in events] == ["dispatched", "failed"]
    assert events[0]["call_id"] == events[1]["call_id"] == records[0]["call_id"]
    assert records[0]["attempt"] == 0
    assert records[0]["response_chars"] == 0
    assert "input_too_large" in records[0]["error"] == error.stderr_tail
    if channel == "cli_stderr":
        assert INPUT_ERROR in records[0]["error"]
    assert records[0]["prompt_sha256"] == hashlib.sha256(
        (INSTRUCTION + "unchanged input").encode()
    ).hexdigest()
    trace = read_jsonl(ctx.path / "trace.jsonl")
    assert [event["event"] for event in trace] == ["exec.start", "exec.end"]
    assert trace[-1]["details"]["error"] == records[0]["error"]
    # Failure still releases its real OS slot so subsequent calls can proceed.
    slot = backend._acquire_slot(.1)
    slot.close()


@pytest.mark.parametrize("kind", ["capacity", "unknown_input", "unknown_rpc", "malformed_data"])
def test_other_provider_rejections_keep_retry_backoff_and_accounting(ctx, kind):
    error = dict(STRUCTURED_ERROR)
    if kind == "capacity":
        error = {"code": -32000, "message": "server temporarily at capacity"}
    elif kind == "unknown_input":
        error["data"] = {"input_error_code": "new_provider_code"}
    elif kind == "unknown_rpc":
        error["code"] = -32000
    else:
        error["data"] = "input_too_large"
    _, _, budget, waits, events = run_failed(ctx, json.dumps({"type": "turn.failed", "error": error}),
                                            retries=2)
    records = read_jsonl(ctx.path / "codex_calls.jsonl")
    assert count_codex_calls(ctx.path) == budget.count == len(records) == 3
    assert waits == [1, 2]
    assert [r["attempt"] for r in records] == [0, 1, 2]
    assert len({r["call_id"] for r in records}) == 3
    assert [e["status"] for e in events] == ["dispatched", "failed"] * 3


@pytest.mark.parametrize("channel", ["model_item", "web_item", "quoted_stderr", "unstructured_stderr"])
def test_error_text_in_ordinary_content_does_not_disable_transient_retry(ctx, channel):
    stdout = ""
    stderr = "temporary transport failure"
    if channel == "model_item":
        stdout = json.dumps({"type": "item.completed", "item": {
            "type": "agent_message", "text": INPUT_ERROR, "example_error": STRUCTURED_ERROR}})
    elif channel == "web_item":
        stdout = json.dumps({"type": "item.completed", "item": {
            "type": "web_search", "action": {"type": "open", "url": "https://example.invalid"},
            "text": INPUT_ERROR, "example_error": STRUCTURED_ERROR}})
    elif channel == "quoted_stderr":
        stderr += "\nQuoted source: " + INPUT_ERROR
    else:
        stderr += '\ninput_too_large: {"input_error_code":"input_too_large"}'
    _, _, budget, waits, _ = run_failed(ctx, stdout, stderr, retries=1)
    assert count_codex_calls(ctx.path) == budget.count == 2
    assert waits == [1]


def test_successful_output_containing_provider_error_text_remains_success(ctx):
    response = "Example of a provider error:\n" + INPUT_ERROR
    budget = CallBudget(20, 30)

    def runner(command, **kwargs):
        Path(command[command.index("--output-last-message") + 1]).write_text(response)
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "type": "item.completed", "item": {"type": "agent_message", "text": response}
        }), stderr=INPUT_ERROR)

    result = CodexBackend(ctx, runner=runner, budget=budget).complete("explain errors", purpose="root")
    assert result == response
    record, = read_jsonl(ctx.path / "codex_calls.jsonl")
    assert record["error"] is None
    assert budget.count == 1
