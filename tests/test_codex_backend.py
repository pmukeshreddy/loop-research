import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from loop_research.archive import read_jsonl
from loop_research.codex_backend import BudgetExceeded, CallBudget, CodexBackend, CodexError, INSTRUCTION


@pytest.mark.parametrize("web", [False, True])
@pytest.mark.parametrize("schema", [None, {"type": "object"}])
@pytest.mark.parametrize("model,effort", [(None, None), ("fixture-model", "high")])
def test_command_modes(ctx, web, schema, model, effort):
    ctx.config.models.reasoning_effort = effort
    if model is not None:
        ctx.config.models.root = model
    seen = []
    def runner(command, **kwargs):
        seen.append(command)
        assert kwargs["input"] == INSTRUCTION + "fixture prompt"
        assert list(Path(kwargs["cwd"]).iterdir()) == []
        assert command[command.index("--sandbox") + 1] == "read-only"
        assert "--skip-git-repo-check" in command
        assert "--ignore-user-config" in command
        assert 'forced_login_method="chatgpt"' in command
        assert command[-1] == "-"
        assert ('web_search="live"' if web else 'web_search="disabled"') in command
        if schema:
            assert json.loads(Path(command[command.index("--output-schema") + 1]).read_text()) == schema
        else:
            assert "--output-schema" not in command
        assert command[command.index("--model") + 1] == ctx.config.models.root
        if effort:
            assert 'model_reasoning_effort="high"' in command
        Path(command[command.index("--output-last-message") + 1]).write_text("fixture response")
        return SimpleNamespace(returncode=0, stdout=json.dumps({"type": "turn.completed", "usage": {
            "input_tokens": 12, "output_tokens": 4, "cached_input_tokens": 5}}), stderr="")
    backend = CodexBackend(ctx, runner=runner)
    assert backend.complete("fixture prompt", purpose="root", web=web, schema=schema, model=model) == "fixture response"
    records = read_jsonl(ctx.path / "codex_calls.jsonl")
    assert len(records) == len(seen) == 1
    assert records[0]["prompt_chars"] == len(INSTRUCTION + "fixture prompt")
    assert "prompt" not in records[0] and "response" not in records[0]
    assert backend.last_usage["input_tokens"] == 12


@pytest.mark.parametrize("purpose,model", [("root", "fixture-root"), ("repair", "fixture-root"),
    ("sub", "fixture-sub"), ("search", "fixture-sub"), ("fetch", "fixture-sub"),
    ("refine", "fixture-refine"), ("grade", "fixture-judge")])
def test_every_purpose_uses_and_logs_its_configured_model(ctx, purpose, model):
    for role in ("root", "sub", "refine", "judge"):
        setattr(ctx.config.models, role, "fixture-" + role)
    def runner(command, **kwargs):
        assert command[command.index("--model") + 1] == model
        Path(command[command.index("--output-last-message") + 1]).write_text("fixture response")
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    assert CodexBackend(ctx, runner=runner).complete("fixture", purpose=purpose) == "fixture response"
    assert read_jsonl(ctx.path / "codex_calls.jsonl")[0]["model"] == model


def test_backend_rejects_unconfigured_model_override_before_dispatch(ctx):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid model request must not invoke Codex")
    with pytest.raises(ValueError, match="configured"):
        CodexBackend(ctx, runner=forbidden).complete("fixture", purpose="root", model="unconfigured")


def test_retry_delay_obeys_configured_cap(ctx):
    ctx.config.codex.retry_delay_cap_s = .25
    ctx.config.codex.max_retries = 2
    waits = []
    def runner(*args, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="fixture failure")
    with pytest.raises(CodexError):
        CodexBackend(ctx, runner=runner, sleep=waits.append, jitter=lambda: 0).complete("fixture", purpose="repair")
    assert waits == [.25, .25]


def test_attempt_callback_links_dispatch_and_completion_for_every_retry(ctx):
    ctx.config.codex.max_retries = 1
    events, calls = [], []
    def runner(command, **kwargs):
        assert events[-1]['status'] == 'dispatched'
        calls.append(command)
        if len(calls) == 1:
            return SimpleNamespace(returncode=1, stdout='', stderr='fixture retry')
        Path(command[command.index('--output-last-message') + 1]).write_text('done')
        return SimpleNamespace(returncode=0, stdout='', stderr='')
    result = CodexBackend(ctx, runner=runner, sleep=lambda _: None).complete(
        'fixture', purpose='fetch', on_attempt=events.append)
    assert result == 'done'
    assert [event['status'] for event in events] == ['dispatched', 'failed', 'dispatched', 'succeeded']
    assert events[0]['call_id'] == events[1]['call_id'] != events[2]['call_id'] == events[3]['call_id']
    assert [event['attempt'] for event in events] == [0, 0, 1, 1]
    assert all(event['model'] == ctx.config.models.sub for event in events)
    assert 'fixture retry' in events[1]['error'] and events[3]['error'] is None


@pytest.mark.parametrize("failure", ["nonzero", "timeout", "rate", "terminal", "empty"])
def test_retries_and_failure_details(ctx, failure):
    ctx.config.codex.max_retries = 2
    calls, waits = [], []
    def runner(command, **kwargs):
        calls.append(command)
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        Path(command[command.index("--output-last-message") + 1]).write_text("" if failure == "empty" else "response")
        return SimpleNamespace(returncode=7 if failure == "nonzero" else 0,
            stdout=json.dumps({"type": "turn.failed", "error": {"message": "failed"}}) if failure == "terminal" else "",
            stderr="rate limit exceeded" if failure == "rate" else "fixture stderr")
    backend = CodexBackend(ctx, runner=runner, sleep=waits.append, jitter=lambda: 0)
    with pytest.raises(CodexError) as error:
        backend.complete("fixture", purpose="grade")
    assert len(calls) == 3 and waits == [1, 2]
    assert error.value.command == calls[-1]
    assert error.value.stderr_tail
    assert len(read_jsonl(ctx.path / "codex_calls.jsonl")) == 3


def test_retry_then_success_and_credentials(ctx, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-secret")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid")
    ctx.config.codex.log_full_text = True
    calls = []
    def runner(command, **kwargs):
        assert "OPENAI_API_KEY" not in kwargs["env"]
        assert "OPENAI_BASE_URL" not in kwargs["env"]
        calls.append(command)
        if len(calls) == 1:
            return SimpleNamespace(returncode=1, stderr="retry", stdout="")
        Path(command[command.index("--output-last-message") + 1]).write_text("done")
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    assert CodexBackend(ctx, runner=runner, sleep=lambda _: None).complete("fixture", purpose="sub") == "done"
    records = read_jsonl(ctx.path / "codex_calls.jsonl")
    assert records[-1]["response"] == "done" and records[-1]["usage_status"] == "unavailable"


def test_hard_call_budget(ctx):
    budget = CallBudget(1, 30)
    budget.reserve()
    with pytest.raises(BudgetExceeded, match="call limit"):
        budget.reserve()
    budget.deadline = 0
    with pytest.raises(BudgetExceeded, match="deadline"):
        budget.remaining()


def test_cancellation_interrupts_retry_backoff(ctx):
    from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
    import threading
    waiting, calls = threading.Event(), []

    class Cancellation(Future):
        def result(self, timeout=None):
            waiting.set()
            return super().result(timeout=timeout)

    ctx.cancellation = Cancellation()
    ctx.config.codex.max_retries = 1

    def runner(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=1, stdout="", stderr="Fixture retry")

    backend = CodexBackend(ctx, runner=runner, jitter=lambda: 0)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(backend.complete, "fixture", purpose="grade")
        try:
            assert waiting.wait(3), "Retry backoff does not wait on cancellation"
            ctx.cancellation.cancel()
            with pytest.raises(CancelledError):
                future.result(timeout=3)
            assert len(calls) == 1
        finally:
            ctx.cancellation.cancel()


def _offline_codex_process(ctx, index, started, ready, release):
    def runner(command, **kwargs):
        started[index].set()
        assert release.wait(5)
        Path(command[command.index('--output-last-message') + 1]).write_text('fixture response')
        return SimpleNamespace(returncode=0, stdout='', stderr='')
    ready[index].set()
    CodexBackend(ctx, runner=runner).complete('fixture', purpose='root')


def test_codex_limit_is_shared_by_worker_processes(ctx):
    import multiprocessing
    ctx.config.codex.max_concurrent = 1
    mp = multiprocessing.get_context('spawn')
    started = [mp.Event(), mp.Event()]
    ready = [mp.Event(), mp.Event()]
    release = mp.Event()
    first, second = [mp.Process(target=_offline_codex_process, args=(ctx, index, started, ready, release))
                     for index in range(2)]
    first.start()
    try:
        assert started[0].wait(5)
        second.start()
        assert ready[1].wait(5)
        assert not started[1].wait(.2), 'Second worker exceeded the global Codex limit'
    finally:
        release.set()
        first.join(5)
        if second.pid is not None:
            second.join(5)
    assert first.exitcode == second.exitcode == 0
    assert started[1].is_set()


def test_killed_codex_attempt_keeps_durable_start_without_fake_completion(ctx):
    import multiprocessing
    from loop_research.archive import count_codex_calls, read_json
    mp = multiprocessing.get_context('spawn')
    started, ready, release = [mp.Event()], [mp.Event()], mp.Event()
    process = mp.Process(target=_offline_codex_process, args=(ctx, 0, started, ready, release))
    process.start()
    try:
        assert started[0].wait(5)
        assert (ctx.path / 'codex_calls.jsonl').exists()
        starts = list((ctx.path / 'codex_attempts').glob('*.json'))
        assert len(starts) == 1
        record = read_json(starts[0])
        assert record['call_id'] == starts[0].stem
        assert record['purpose'] == 'root'
        assert not {'usage', 'duration_s', 'exit_code', 'response'} & record.keys()
    finally:
        process.terminate()
        process.join(5)
    assert process.exitcode != 0
    assert read_jsonl(ctx.path / 'codex_calls.jsonl') == []
    assert count_codex_calls(ctx.path) == 1


def test_retry_attempts_have_distinct_identity_and_matching_completion(ctx):
    from loop_research.archive import count_codex_calls, read_json
    ctx.config.codex.max_retries = 1
    def runner(command, **kwargs):
        starts = list((ctx.path / 'codex_attempts').glob('*.json'))
        assert len(starts) == len(read_jsonl(ctx.path / 'codex_calls.jsonl')) + 1
        return SimpleNamespace(returncode=1, stdout='', stderr='fixture failure')
    with pytest.raises(CodexError):
        CodexBackend(ctx, runner=runner, sleep=lambda _: None).complete('fixture', purpose='sub')
    completed = read_jsonl(ctx.path / 'codex_calls.jsonl')
    starts = [read_json(p) for p in (ctx.path / 'codex_attempts').glob('*.json')]
    assert len({call['call_id'] for call in completed}) == len(starts) == 2
    assert {call['call_id'] for call in completed} == {call['call_id'] for call in starts}
    assert count_codex_calls(ctx.path) == 2


def test_baseline_timeout_archives_web_actions_and_partial_stderr(ctx):
    event = json.dumps({'type': 'item.completed', 'item': {'type': 'web_search',
                       'action': {'type': 'open', 'url': 'https://example.org'}}})
    def runner(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs['timeout'],
                                        output=event.encode(), stderr=b'partial stderr evidence')
    with pytest.raises(CodexError):
        CodexBackend(ctx, runner=runner).complete('fixture', purpose='baseline', web=True)
    call, = read_jsonl(ctx.path / 'codex_calls.jsonl')
    assert call['web_actions'] == [{'type': 'open', 'url': 'https://example.org'}]
    assert 'partial stderr evidence' in (ctx.path / 'codex_stderr.txt').read_text()
