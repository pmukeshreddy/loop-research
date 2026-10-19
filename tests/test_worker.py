"""Real isolated RLM workers with only model completions replaced offline."""

from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
import json
import subprocess
import threading
import time

import pytest

from loop_research.agent import run_task
from loop_research.archive import append_json, read_jsonl, write_json
from loop_research.codex_backend import BudgetExceeded
from loop_research.harness import Harness
from loop_research.session import Session


class OfflineBackend:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []
        self.local = threading.local()
        self.budget = None

    def complete(self, prompt, **options):
        self.budget.reserve()
        self.calls.append((prompt, options))
        self.local.web_actions = []
        response = self.reply(prompt, options)
        if isinstance(response, tuple):
            response, self.local.web_actions = response
        return response

    @property
    def last_usage(self):
        return {"input_tokens": 7, "output_tokens": 3}

    @property
    def last_web_actions(self):
        return getattr(self.local, "web_actions", [])


@pytest.fixture
def session_factory(tmp_path, ctx, task):
    sessions = []
    ctx.config.rlm.max_iterations = 3
    ctx.config.models.root = "offline-root"
    ctx.config.models.sub = "offline-sub"
    harness = Harness(tmp_path / "harness")

    def create(reply):
        backend = OfflineBackend(reply)
        session = Session(task, ctx, harness, learning=False, backend=backend)
        backend.budget = session.budget
        sessions.append(session)
        return session

    yield create
    for session in sessions:
        session.refiner.close()


def code_reply(code):
    return "```repl\n" + code + "\n```"


def final_code(output):
    return 'answer["content"] = ' + repr(json.dumps(output)) + '\nanswer["ready"] = True'


def test_refinement_observation_preserves_actions_without_repeated_history(ctx, session_factory):
    session = session_factory(lambda *args: None)
    events = [
        {'type': 'model', 'purpose': 'root', 'prompt': 'initial task and instructions', 'response': 'first code'},
        {'type': 'model', 'purpose': 'root', 'prompt': 'accumulated root history', 'response': 'second code'},
        {'type': 'model', 'purpose': 'sub', 'prompt': 'page extraction input', 'response': 'extraction'},
        {'type': 'tool', 'tool': 'fetch', 'result': 'page evidence'},
        {'type': 'worker_iteration', 'event': {'iteration': 2, 'prompt': 'accumulated root history',
            'response': 'second code', 'code_blocks': [{'code': 'second code', 'result': {
                'stdout': 'diagnostic', 'stderr': 'execution error', 'locals': {'pages': 'accumulated pages'},
                'rlm_calls': ['duplicate sub call'], 'final_answer': 'answer'}}]}}
    ]
    for event in events:
        append_json(ctx.path / 'trajectory.jsonl', event)
    observed = session.observation()['trajectory']
    assert observed[0] == events[0]
    assert observed[1] == {k: v for k, v in events[1].items() if k != 'prompt'}
    assert observed[2:4] == events[2:4]
    iteration = observed[4]['event']
    assert 'prompt' not in iteration and 'response' not in iteration
    assert iteration['code_blocks'] == [{'code': 'second code', 'result': {
        'stdout': 'diagnostic', 'stderr': 'execution error', 'final_answer': 'answer'}}]
    assert read_jsonl(ctx.path / 'trajectory.jsonl') == events


def test_worker_full_python_tools_subcalls_and_trusted_trajectory(ctx, task, benchmark, output, session_factory):
    code = '''
import asyncio, json, pathlib, subprocess, sys, threading
class Number:
    value = 42
assert eval("Number.value") == 42
exec(compile("computed = 42", "fixture", "exec"))
assert computed == 42
seen = []
thread = threading.Thread(target=lambda: seen.append(True))
thread.start()
thread.join()
assert seen == [True]
async def compute():
    await asyncio.sleep(0)
    return 42
assert asyncio.run(compute()) == 42
pathlib.Path("scratch.txt").write_text("scratch works")
assert pathlib.Path("scratch.txt").read_text() == "scratch works"
child = subprocess.run([sys.executable, "-c", "print(42)"], capture_output=True, text=True)
assert child.returncode == 0 and child.stdout.strip() == "42"
hits = search_many(["fixture first", "fixture second"], k=1)
assert len(hits) == 2 and all(len(batch) == 1 for batch in hits)
record_discovery("fixture first", ["fixture-a"])
record_discovery("fixture second", ["fixture-b"])
pages = fetch_many(["https://example.org/", "https://example.org/other"])
assert pages == ["fixture-a fixture-value", "fixture-a fixture-value"]
assert llm_query_batched(["first", "second"]) == ["first result", "second result"]
for constraint in ("question", "columns/0", "columns/1"):
    check_constraint("/rows/0", constraint, True, "https://example.org/", "fixture-a")
''' + final_code(output)

    def reply(prompt, options):
        purpose = options["purpose"]
        if purpose == "root":
            return code_reply(code)
        if purpose == "sub":
            return prompt + " result"
        if purpose == "search":
            return json.dumps({"results": [{"title": "fixture", "url": "https://example.org/", "snippet": "fixture"}]})
        if purpose == "fetch":
            url = prompt.splitlines()[0].split(": ", 1)[1]
            return "fixture-a fixture-value", [{"type": "open_page", "url": url}]
        raise AssertionError("Unexpected model purpose: " + purpose)

    session = session_factory(reply)
    result = run_task(task, benchmark, session)
    assert result.output == output
    assert result.uncited == [] and not result.repaired
    assert ctx.load("output.json") == output
    assert ctx.load("submission.json") == benchmark.to_submission(task, output)
    assert session.self_check()["ok"] is True
    events = read_jsonl(ctx.path / "trajectory.jsonl")
    assert {event["type"] for event in events} == {"model", "tool", "worker_iteration"}
    assert {event["tool"] for event in events if event["type"] == "tool"} >= {
        "search_many", "fetch_many", "record_discovery", "check_constraint",
    }
    iterations = [event["event"] for event in events if event["type"] == "worker_iteration"]
    assert iterations[-1]["final_answer"] == json.dumps(output)
    root_calls = [options for _, options in session.backend.calls if options["purpose"] == "root"]
    sub_calls = [options for _, options in session.backend.calls if options["purpose"] == "sub"]
    assert len(root_calls) == 1 and root_calls[0]["model"] == "offline-root"
    assert len(sub_calls) == 2 and all(options["model"] == "offline-sub" for options in sub_calls)


def test_selected_skill_module_loads_into_full_python_worker(task, benchmark, output, session_factory):
    session = session_factory(lambda prompt, options: code_reply(
        'assert loaded_skills["fixture"].calculate() == 42\n'
        'import skill_fixture\nassert skill_fixture.calculate() == 42\n' + final_code(output)))
    session.harness.create('skill', 'Hand-written fixture', 'Reusable fixture procedure', id='fixture',
                           module='import asyncio\ndef calculate():\n    return eval("6 * 7")\n')
    result = run_task(task, benchmark, session)
    assert result.output == output
    assert session.harness.get('skill', 'fixture')['usage'][0]['run_id'] == session.run_id


def test_worker_cannot_read_grades_or_modify_trusted_evidence(ctx, task, benchmark, output, session_factory):
    evidence = {"fetched": {}, "checks": [], "searches": [], "discoveries": [], "failures": [],
                "fetches": [], "dropped_search_hits": []}
    ctx.save("evidence.json", evidence)
    ctx.save("self_check.json", {"ok": False, "issues": ["host-owned"]})
    ctx.save("grades.json", {"private": "SYNTHETIC_GRADE"})
    gold = ctx.root / "data/gold.json"
    other = ctx.root / "runs/other/task/output.json"
    write_json(gold, {"private": "SYNTHETIC_GOLD"})
    write_json(other, {"private": "SYNTHETIC_OTHER_RUN"})
    paths = [str(gold), str(other), str(ctx.path / "grades.json")]
    protected = [str(ctx.path / name) for name in ("evidence.json", "self_check.json", "grades.json")]
    code = f'''
import json, os, pathlib
for name in {paths!r}:
    for reader in (pathlib.Path(name).read_text, lambda: json.codecs.open(name).read()):
        try:
            reader()
        except PermissionError:
            pass
        else:
            raise AssertionError("Protected host file readable: " + name)
for name in {protected!r}:
    try:
        fd = os.open(name, os.O_WRONLY)
    except PermissionError:
        pass
    else:
        os.close(fd)
        raise AssertionError("Host evidence writable: " + name)
# The remote tool object has no host Session or backend in its globals.
assert "session" not in search.__globals__
client = harness.client
for method, args, kwargs in (
    ("grade", [], {{}}),
    ("self_check", [], {{}}),
    ("tools.persist", [], {{}}),
    ("complete", ["read answer key"], {{"purpose": "grade"}}),
):
    try:
        client.call(method, *args, **kwargs)
    except RuntimeError:
        pass
    else:
        raise AssertionError("Private host operation exposed: " + method)
''' + final_code(output)
    session = session_factory(lambda prompt, options: code_reply(code))
    result = run_task(task, benchmark, session)
    assert result.output == output
    assert session.tools.snapshot() == evidence
    assert ctx.load("evidence.json") == evidence
    assert ctx.load("self_check.json") == {"ok": False, "issues": ["host-owned"]}
    assert ctx.load("grades.json") == {"private": "SYNTHETIC_GRADE"}
    report = session.self_check()
    assert not report["ok"]
    assert "unfetched_url" in {issue["type"] for issue in report["issues"]}


@pytest.mark.parametrize("phase", ["worker", "repair"])
def test_research_operational_errors_surface(ctx, task, benchmark, session_factory, phase):
    def reply(prompt, options):
        if phase == "repair" and options["purpose"] == "root":
            return code_reply('answer["content"] = "invalid output"\nanswer["ready"] = True')
        raise RuntimeError("fixture transport failure")

    session = session_factory(reply)
    expected = "fixture transport failure" if phase == "repair" else "Research worker failed"
    with pytest.raises(RuntimeError, match=expected):
        run_task(task, benchmark, session)
    if phase == "worker":
        assert session.status["worker_error"]
        assert "fixture transport failure" in (ctx.path / "worker.log").read_text()
    assert not (ctx.path / "output.json").exists()


@pytest.mark.parametrize("phase", ["worker", "repair"])
def test_resumed_task_budget_counts_interrupted_codex_attempt(ctx, task, benchmark, session_factory, phase):
    ctx.config.agent.max_codex_calls = 1 if phase == "worker" else 2
    write_json(ctx.path / "codex_attempts/pending.json", {"call_id": "pending", "purpose": "root"})
    write_json(ctx.path / "codex_attempts/judge.json", {"call_id": "judge", "purpose": "grade"})
    session = session_factory(lambda prompt, options: code_reply(
        'answer["content"] = "invalid output"\nanswer["ready"] = True'))
    assert session.budget.count == 1
    error = RuntimeError if phase == "worker" else BudgetExceeded
    message = "Research worker failed" if phase == "worker" else "call limit"
    with pytest.raises(error, match=message):
        run_task(task, benchmark, session)
    assert session.status["call_limit"]
    assert not (ctx.path / "output.json").exists()


def test_task_deadline_is_shared_by_worker_and_repair(ctx, task, benchmark, output, session_factory):
    def reply(prompt, options):
        if options["purpose"] == "root":
            return code_reply('answer["content"] = "invalid output"\nanswer["ready"] = True')
        assert options["purpose"] == "repair"
        session.budget.deadline = 0
        return json.dumps(output)

    session = session_factory(reply)
    with pytest.raises(BudgetExceeded, match="deadline"):
        run_task(task, benchmark, session)
    assert session.status["timeout"]
    assert not (ctx.path / "output.json").exists()


def test_hard_deadline_terminates_running_python(ctx, task, benchmark, session_factory):
    session = session_factory(lambda prompt, options: code_reply("import time\ntime.sleep(30)"))
    session.budget.deadline = time.monotonic() + 1.5
    started = time.monotonic()
    with pytest.raises(TimeoutError, match="hard deadline"):
        run_task(task, benchmark, session)
    assert time.monotonic() - started < 5
    assert session.status["timeout"]
    assert not (ctx.path / "output.json").exists()


def test_call_limit_is_shared_with_output_repair(ctx, task, benchmark, session_factory):
    ctx.config.agent.max_codex_calls = 1
    session = session_factory(lambda prompt, options: code_reply(
        'answer["content"] = "invalid output"\nanswer["ready"] = True'))
    with pytest.raises(BudgetExceeded, match="call limit"):
        run_task(task, benchmark, session)
    assert session.status["call_limit"]
    assert not (ctx.path / "output.json").exists()


def test_caught_tool_budget_exhaustion_is_still_an_issue(ctx, task, benchmark, output, session_factory):
    ctx.config.agent.max_codex_calls = 2
    code = '''fetch("https://example.org/")
for c in ("question", "columns/0", "columns/1"):
    check_constraint("/rows/0", c, True, "https://example.org/", "fixture-a")
try:
    search("optional additional evidence")
except Exception:
    pass
''' + final_code(output)

    def reply(prompt, options):
        if options['purpose'] == 'root':
            return code_reply(code)
        assert options['purpose'] == 'fetch'
        return 'fixture-a fixture-value', [{'type': 'open_page', 'url': 'https://example.org/'}]

    session = session_factory(reply)
    result = run_task(task, benchmark, session)
    assert result.status['call_limit']
    report = session.self_check()
    assert not report['ok']
    assert any(i['type'] == 'call_limit' for i in report['issues'])
    assert any(s['type'] == 'failed_search' for s in report['signals'])


def test_cancelled_task_terminates_worker_and_its_child(ctx, task, benchmark, session_factory):
    child_ready = threading.Event()
    child_pids = []
    ctx.cancellation = Future()
    code = '''
import subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
search("child-pid:" + str(child.pid))
time.sleep(30)
'''

    def reply(prompt, options):
        if options["purpose"] == "root":
            return code_reply(code)
        assert options["purpose"] == "search"
        child_pids.append(int(prompt.split("child-pid:", 1)[1].split("'", 1)[0]))
        child_ready.set()
        return '{"results": []}'

    session = session_factory(reply)
    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(run_task, task, benchmark, session)
        try:
            assert child_ready.wait(5), "Worker did not spawn its child"
        finally:
            ctx.cancellation.cancel()
        with pytest.raises(CancelledError):
            running.result(timeout=5)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        status = subprocess.run(["/bin/ps", "-o", "stat=", "-p", str(child_pids[0])],
                                capture_output=True, text=True).stdout.strip()
        if not status or status.startswith("Z"):
            break
        time.sleep(.02)
    assert not status or status.startswith("Z"), "A worker descendant survived cancellation"
    assert not (ctx.path / "output.json").exists()


def test_completed_research_archive_preserves_status_for_resume(ctx, task, benchmark, output, session_factory):
    session = session_factory(lambda prompt, options: code_reply(final_code(output)))
    session.status['iteration_limit'] = True
    result = run_task(task, benchmark, session)
    assert ctx.load('agent_result.json')['status'] == result.status == {'iteration_limit': True}
