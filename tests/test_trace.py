"""Tracing observes the real isolated pipeline without changing its inputs/results."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json

from loop_research.archive import read_jsonl


def test_live_trace_is_flushed_and_counts_nested_calls_and_errors(tmp_path):
    from loop_research.trace import Trace
    trace = Trace(tmp_path)
    with trace.span('tools.search_many', 'call', queries=['one', 'two']):
        def search(query):
            with trace.span('tools.search', 'call', parent='tools.search_many', query=query):
                with trace.span('Codex backend (search)', 'exec', purpose='search'):
                    assert any(e['event'] == 'exec.start' for e in read_jsonl(tmp_path / 'trace.jsonl'))
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(search, ['one', 'two']))
    try:
        with trace.span('REPL', 'code'):
            raise ValueError('fixture error')
    except ValueError:
        pass
    events = read_jsonl(tmp_path / 'trace.jsonl')
    assert all({'timestamp', 'component', 'event', 'details'} <= e.keys() for e in events)
    assert len((tmp_path / 'trace.log').read_text().splitlines()) == len(events)
    assert events[-1]['details']['error'] == 'ValueError: fixture error'
    summary = trace.summary({'rows': []}, {'ok': True, 'issues': []})
    assert '| tools.search_many → tools.search | 2 |' in summary
    assert '| tools.search → Codex backend (search) | 2 |' in summary
    assert summary == (tmp_path / 'trace_summary.md').read_text()


def test_tracing_preserves_worker_prompts_tools_output_and_self_check(ctx, task, output, monkeypatch):
    from loop_research.agent import run_task
    from loop_research.harness import Harness
    from loop_research.research import ResearchData
    from loop_research.session import Session
    from loop_research.trace import Trace
    from test_worker import OfflineBackend, code_reply, final_code
    from test_agent_tools import install_fetch
    from loop_research import page_fetch
    from types import SimpleNamespace

    monkeypatch.setattr(page_fetch, 'uuid4', lambda: SimpleNamespace(hex='fixture-download'))
    downloads = install_fetch(monkeypatch, 'fixture-a fixture-value')

    code = '''
import json
hits = search_many(["fixture"], k=1)
assert search("fixture", k=1) == hits[0]
record_discovery("fixture", ["fixture-a"])
assert fetch_many(["https://example.org/"]) == ["fixture-a fixture-value"]
assert fetch("https://example.org/") == "fixture-a fixture-value"
assert llm_query("extract") == "fixture-value"
for constraint in ("question", "columns/0", "columns/1"):
    check_constraint("/rows/0", constraint, True, "https://example.org/", "fixture-a")
print("fixture stdout")
''' + final_code(output)
    def reply(prompt, options):
        purpose = options['purpose']
        if purpose == 'root':
            return code_reply(code)
        if purpose == 'sub':
            return 'fixture-value'
        if purpose == 'search':
            return json.dumps({'results': [{'title': 'fixture', 'url': 'https://example.org/', 'snippet': 'fixture'}]})
        raise AssertionError('Unexpected model purpose: ' + purpose)

    results = []
    for enabled in (False, True):
        run = replace(ctx, run_id='traced' if enabled else 'plain')
        if enabled:
            run.trace = Trace(run.run_dir)
        backend = OfflineBackend(reply)
        session = Session(task, run, Harness(run.root / ('harness-' + run.run_id)), learning=False, backend=backend)
        backend.budget = session.budget
        try:
            result = run_task(task, ResearchData(), session)
            results.append((result, backend.calls, session.finish(), (run.path / 'prompt.txt').read_text()))
        finally:
            session.refiner.close()
    assert downloads == ['https://example.org/', 'https://example.org/']
    for index in (0, 2, 3):
        assert results[0][index] == results[1][index]
    # Callbacks are different Python objects in separate sessions, but must be
    # supplied to the same calls; every prompt and serializable option is equal.
    def comparable(calls):
        return [(prompt, {k: callable(v) if callable(v) else v for k, v in options.items()})
                for prompt, options in calls]
    assert comparable(results[0][1]) == comparable(results[1][1])
    assert not (ctx.root / 'runs/plain/trace.jsonl').exists()
    events = read_jsonl(ctx.root / 'runs/traced/trace.jsonl')
    components = {e['component'] for e in events}
    assert {'Worker', 'Bridge', 'Harness', 'Prompt', 'RLM iteration', 'RLM root', 'RLM sub', 'REPL',
            'tools.search', 'tools.fetch', 'tools.search_many', 'tools.fetch_many',
            'tools.check_constraint', 'tools.record_discovery', 'Output'} <= components
    assert any(e['details'].get('cache') == 'hit' for e in events)
    assert any(e['details'].get('stdout') == 'fixture stdout\n' for e in events)
    assert any(e['details'].get('pid') for e in events)


def test_codex_trace_records_retries_usage_and_cancellation(ctx):
    from concurrent.futures import CancelledError
    from pathlib import Path
    import subprocess
    import pytest
    from loop_research.codex_backend import CodexBackend
    from loop_research.trace import Trace
    ctx.trace = Trace(ctx.run_dir)
    ctx.config.codex.max_retries = 1
    calls = []
    def runner(command, **kwargs):
        calls.append(command)
        if len(calls) == 1:
            return subprocess.CompletedProcess(command, 2, '', 'fixture failure')
        Path(command[command.index('--output-last-message') + 1]).write_text('done')
        stdout = '\n'.join(json.dumps(e) for e in [
            {'type': 'turn.completed', 'usage': {'input_tokens': 9, 'output_tokens': 2}},
            {'type': 'item.completed', 'item': {'type': 'web_search', 'action': {'type': 'open_page', 'url': 'https://example.org/'}}}])
        return subprocess.CompletedProcess(command, 0, stdout, '')
    backend = CodexBackend(ctx, runner=runner, sleep=lambda _: None)
    assert backend.complete('fixture', purpose='search') == 'done'
    events = read_jsonl(ctx.run_dir / 'trace.jsonl')
    ends = [e for e in events if e['event'] == 'exec.end']
    assert len(ends) == 2
    assert [e['details']['exit_code'] for e in ends] == [2, 0]
    assert ends[-1]['details']['usage']['input_tokens'] == 9
    assert ends[-1]['details']['web_action_count'] == 1
    assert ends[-1]['details']['retries'] == 1
    assert any(e['event'] == 'retry' for e in events)
    def cancel(*args, **kwargs):
        raise CancelledError('fixture cancellation')
    with pytest.raises(CancelledError):
        CodexBackend(ctx, runner=cancel).complete('fixture', purpose='root')
    last = read_jsonl(ctx.run_dir / 'trace.jsonl')[-1]
    assert last['event'] == 'exec.end' and 'CancelledError' in last['details']['error']


def test_refine_trace_proposal_edits_rollback_and_summary(ctx):
    from loop_research.harness import Harness
    from loop_research.refine import Refiner
    from loop_research.trace import Trace
    from test_refine import Planner, proposal
    ctx.trace = Trace(ctx.run_dir)
    harness = Harness(ctx.root / 'harness')
    planner = Planner(proposal())
    refiner = Refiner(harness, ctx, planner, lambda: {'trajectory': [], 'self_check': {'ok': True}})
    try:
        refiner.run('fixture focus')
        commits = refiner.boundary(wait=True)
        refiner.rollback(commits[0])
    finally:
        refiner.close()
    events = read_jsonl(ctx.run_dir / 'trace.jsonl')
    assert {'scheduled', 'planning.start', 'planning.end', 'proposal', 'edit_applied', 'rollback.end'} <= {e['event'] for e in events}
    assert 'trace' not in planner.prompts[0]
    summary = ctx.trace.summary({'rows': []}, {'ok': False, 'issues': [{'type': 'empty_output'}]})
    assert commits[0] in summary and 'Retry unavailable official pages.' in summary
    assert '**empty_output** (1)' in summary


def test_retrieval_trace_records_scores_without_changing_entries(ctx, task):
    from loop_research.harness import Harness
    from loop_research.session import Session
    from loop_research.trace import Trace
    ctx.trace = Trace(ctx.run_dir)
    harness = Harness(ctx.root / 'harness')
    harness.create('memory', 'fixture', 'Hand-written fixture procedure', id='fixture')
    session = Session(task, ctx, harness, learning=False)
    try:
        entries = session.retrieve()
    finally:
        session.refiner.close()
    last = read_jsonl(ctx.run_dir / 'trace.jsonl')[-1]['details']
    assert last['entries'][0]['score'] > 0 and last['entries'][0]['id'] == 'fixture'
    assert 'score' not in entries[0]
    assert last['head_before'] == last['head_after']
    assert ctx.load('harness_usage.json') == [
        {key: entries[0][key] for key in ('kind', 'id', 'version', 'refinement_id')}]
    session.close_worker()
    assert harness.head != last['head_after']
    assert harness.get('memory', 'fixture')['usage'] == [
        {'run_id': session.run_id, 'version': entries[0]['version'],
         'refinement_id': entries[0]['refinement_id']}]


def test_research_trace_prints_tail_before_isolation_and_saves_failure_summary(tmp_path, config, monkeypatch, capsys):
    import pytest
    from loop_research import stream
    def isolation():
        assert 'tail -f ' in capsys.readouterr().out
        raise RuntimeError('fixture isolation failed')
    monkeypatch.setattr(stream, 'verify_isolation', isolation)
    with pytest.raises(RuntimeError, match='fixture isolation failed'):
        stream.research(tmp_path, config, 'Fixture?', ['name'], ['name'], 'en', trace=True)
    summary = next((tmp_path / 'runs').glob('*/trace_summary.md'))
    assert 'fixture isolation failed' in summary.read_text()
    assert summary.read_text().strip() in capsys.readouterr().out


def test_recursive_repl_trace_attributes_code_to_sub_model(tmp_path):
    from loop_research.rlm_codex_client import CodexRLM
    from loop_research.trace import Trace
    trace = Trace(tmp_path)
    class Transport:
        last_usage = {'input_tokens': 1, 'output_tokens': 1}
        def call(self, method, *args, **kwargs):
            assert method == 'trace'
            trace.emit(*args, **kwargs)
        def complete(self, prompt, *, purpose, model):
            if purpose == 'root':
                return '```repl\nanswer["content"] = rlm_query("child")\nanswer["ready"] = True\n```'
            return '```repl\nanswer["content"] = "child answer"\nanswer["ready"] = True\n```'
    result = CodexRLM(Transport(), root_model='root', sub_model='sub', max_depth=2,
                      max_iterations=1, trace_enabled=True).completion('fixture')
    assert result.response == 'child answer'
    code = [e for e in read_jsonl(tmp_path / 'trace.jsonl') if e['component'] == 'REPL' and e['event'] == 'code.start']
    assert [(e['details']['depth'], e['parent']) for e in code] == [(0, 'RLM root'), (1, 'RLM sub')]


def test_summary_does_not_claim_failed_or_skipped_rollbacks_as_edits(tmp_path):
    import pytest
    from loop_research.trace import Trace
    trace = Trace(tmp_path)
    with pytest.raises(ValueError):
        with trace.span('Refine', 'rollback', id='missing'):
            raise ValueError('Unknown refinement')
    with trace.span('Refine', 'rollback', id='absent') as details:
        details['result'] = False
    summary = trace.summary({'rows': []}, {'ok': True, 'issues': []})
    edits = summary.split('## Harness edits from refinement', 1)[1].split('## Component errors')[0]
    assert 'No edits applied.' in edits
    assert 'Unknown refinement' not in edits


def test_batched_tools_cancel_queued_calls_after_failure(ctx, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    import pytest
    from loop_research import repl_tools
    from loop_research.trace import Trace
    ctx.trace = Trace(ctx.run_dir)
    ctx.config.codex.max_concurrent = 1
    for batch, single in [('search_many', 'search'), ('fetch_many', 'fetch')]:
        futures, calls = [], []
        submitted, cancelled = threading.Event(), threading.Event()
        class Executor(ThreadPoolExecutor):
            def submit(self, *args, **kwargs):
                future = super().submit(*args, **kwargs)
                futures.append(future)
                future.add_done_callback(lambda f: cancelled.set() if f.cancelled() else None)
                if len(futures) == 9:
                    submitted.set()
                return future
        monkeypatch.setattr(repl_tools, 'ThreadPoolExecutor', Executor)
        tool = repl_tools.ResearchTools(None, ctx)
        def call(value, *args):
            assert ctx.trace.current.get() == 'tools.' + batch
            calls.append(value)
            if value == 'bad':
                assert submitted.wait(2)
                raise ValueError('fixture failed')
            cancelled.wait(.1)
            return []
        monkeypatch.setattr(tool, single, call)
        with pytest.raises(ValueError, match='fixture failed'):
            getattr(tool, batch)(['bad', *map(str, range(8))])
        assert any(future.cancelled() for future in futures)
        assert len(calls) < 9


def test_trace_identifies_each_child_and_answer_ready_termination(tmp_path):
    from loop_research.rlm_codex_client import CodexRLM
    from loop_research.trace import Trace
    trace = Trace(tmp_path)
    class Transport:
        last_usage = {'input_tokens': 1, 'output_tokens': 1}
        def call(self, method, *args, **kwargs):
            trace.emit(*args, **kwargs)
        def complete(self, prompt, *, purpose, model):
            if purpose == 'root':
                return '```repl\nresults = [rlm_query("first"), rlm_query("second")]\nanswer["content"] = str(results)\nanswer["ready"] = True\n```'
            return '```repl\nanswer["content"] = "child"\nanswer["ready"] = True\n```'
    result = CodexRLM(Transport(), root_model='root', sub_model='sub', max_depth=2,
                      max_iterations=2, trace_enabled=True).completion('fixture')
    assert result.response == "['child', 'child']"
    events = read_jsonl(tmp_path / 'trace.jsonl')
    completed = [e['details'] for e in events if e['component'] == 'RLM' and e['event'] == 'completion.end']
    assert len(completed) == 3
    assert len({e['rlm_id'] for e in completed}) == 3
    root = next(e for e in completed if e['depth'] == 0)
    for item in completed:
        assert item['termination'] == 'answer_ready' and item['iterations'] == 1
        if item['depth']:
            assert item['parent_rlm_id'] == root['rlm_id']
        blocks = [e for e in events if e['component'] == 'REPL' and e['event'] == 'code.end'
                  and e['details']['rlm_id'] == item['rlm_id']]
        assert len(blocks) == 1 and blocks[0]['details']['answer_ready'] is True


def test_trace_distinguishes_iteration_limit_from_ready_answer(tmp_path):
    from loop_research.rlm_codex_client import CodexRLM
    from loop_research.trace import Trace
    trace = Trace(tmp_path)
    class Transport:
        last_usage = {'input_tokens': 1, 'output_tokens': 1}
        def call(self, method, *args, **kwargs):
            trace.emit(*args, **kwargs)
        def complete(self, prompt, *, purpose, model):
            return 'No ready answer'
    CodexRLM(Transport(), root_model='root', sub_model='sub', max_iterations=1,
             trace_enabled=True).completion('fixture')
    end = [e for e in read_jsonl(tmp_path / 'trace.jsonl') if e['event'] == 'completion.end']
    assert end[0]['details']['termination'] == 'iteration_limit'
