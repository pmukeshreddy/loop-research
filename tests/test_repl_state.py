"""Completed Python work survives a later exception without suppressing it."""
from loop_research.rlm_codex_client import CodexREPL
from loop_research.agent import run_task
from loop_research.archive import read_jsonl
from test_worker import code_reply, final_code, session_factory
from test_agent_tools import install_fetch


def test_completed_bindings_survive_failure_without_repeating_tool_work():
    calls = []
    def collect():
        calls.append(True)
        return {'text': 'complete evidence', 'count': 3}
    with CodexREPL(lm_timeout=5, custom_tools={'collect': collect}) as repl:
        repl.execute_code('version = 1')
        failed = repl.execute_code(
            'evidence = collect()\nversion = 2\n'
            'print(evidence["text"])\n'
            'raise ValueError("validation failed")\n'
            'unreached = True')
        assert failed.stdout == 'complete evidence\n'
        assert failed.stderr == '\nValueError: validation failed'
        assert failed.locals['evidence'] == {'text': 'complete evidence', 'count': 3}
        assert failed.locals['version'] == 2
        assert 'unreached' not in failed.locals
        recovered = repl.execute_code('print(evidence["count"], version)')
        assert recovered.stdout == '3 2\n'
        assert recovered.stderr == ''
        assert calls == [True]


def test_failure_restores_scaffold_and_retains_user_binding():
    with CodexREPL(lm_timeout=5, context_payload='original context') as repl:
        failed = repl.execute_code(
            'context = "temporary"\nllm_query = None\n'
            'collected = [1, 2]\nraise RuntimeError("stop")')
        assert failed.stderr == '\nRuntimeError: stop'
        recovered = repl.execute_code('print(context, callable(llm_query), collected)')
        assert recovered.stdout == 'original context True [1, 2]\n'
        assert recovered.stderr == ''


def test_syntax_failure_leaves_existing_values_and_error_visible():
    with CodexREPL(lm_timeout=5) as repl:
        repl.execute_code('retained = 7')
        failed = repl.execute_code('retained = 8\nif')
        assert 'SyntaxError:' in failed.stderr
        assert failed.locals['retained'] == 7
        assert repl.execute_code('print(retained)').stdout == '7\n'


def test_failed_answer_rebinding_does_not_submit_through_scaffold_restoration():
    with CodexREPL(lm_timeout=5) as repl:
        failed = repl.execute_code(
            'answer = {"content": "candidate", "ready": True}\n'
            'raise ValueError("validation failed")')
        assert failed.stderr == '\nValueError: validation failed'
        assert failed.final_answer is None
        later = repl.execute_code('print(answer["content"])')
        assert later.stdout == 'candidate\n'
        assert later.final_answer is None
        assert repl.execute_code('answer["ready"] = True').final_answer == 'candidate'


def test_failure_preserves_an_answer_already_captured_by_the_callback():
    with CodexREPL(lm_timeout=5) as repl:
        failed = repl.execute_code(
            'answer["content"] = "submitted"\nanswer["ready"] = True\n'
            'raise ValueError("later error")')
        assert failed.stderr == '\nValueError: later error'
        assert failed.final_answer == 'submitted'


def test_worker_reuses_completed_fetch_and_subcall_after_failure(
        ctx, task, benchmark, output, session_factory, monkeypatch):
    downloads = install_fetch(monkeypatch, 'fixture-a fixture-value')
    roots = 0
    def reply(prompt, options):
        nonlocal roots
        if options['purpose'] == 'sub':
            return 'extracted'
        roots += 1
        if roots == 1:
            return code_reply('page = fetch("https://example.org/")\n'
                              'review = llm_query("Inspect " + page)\n'
                              'print("collected")\nraise ValueError("check failed")')
        assert 'ValueError: check failed' in prompt
        return code_reply('assert page == "fixture-a fixture-value"\n'
                          'assert review == "extracted"\n' + final_code(output))
    session = session_factory(reply)
    assert run_task(task, benchmark, session).output == output
    assert roots == 2
    purposes = [options['purpose'] for _, options in session.backend.calls]
    assert downloads == ['https://example.org/']
    assert purposes.count('sub') == 1 and 'fetch' not in purposes
    iterations = [item['event'] for item in read_jsonl(ctx.path / 'trajectory.jsonl')
                  if item['type'] == 'worker_iteration']
    first, second = [item['code_blocks'][0]['result'] for item in iterations]
    assert first['stdout'] == 'collected\n'
    assert first['stderr'] == '\nValueError: check failed'
    assert len(first['rlm_calls']) == 1
    assert first['rlm_calls'][0]['response'] == 'extracted'
    assert second['stderr'] == ''
    assert second['rlm_calls'] == []
