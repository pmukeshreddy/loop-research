"""Offline baseline execution with real contracts, archives and subprocess boundaries."""
import copy
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from loop_research.archive import GradeContext, read_json, read_jsonl, write_json
from loop_research.benchmarks import GradeResult, Task
from loop_research.benchmarks.wandr.grader import WandrBenchmark
from loop_research.harness import Harness


@pytest.fixture
def offline(tmp_path, config, monkeypatch):
    from loop_research import baseline
    config.wandr.final_n_tasks = 3
    config.codex.max_concurrent = 1
    config.agent.as_of = '2026-10-18'
    config.models.reasoning_effort = 'high'
    harness = Harness(tmp_path / 'harness')
    tasks = [Task(task_id=f't{i}', benchmark='wandr', question='Find the fixture.', language='en',
                  spec={'nodes': [{'task_id': 'node', 'parent_id': None, 'order': 0,
                         'item_fields': ['name'], 'key_hierarchy': ['name'],
                         'required_output_file': 'answer.jsonl'}]}) for i in range(4)]
    output = {'files': {'answer.jsonl': [{'item': {'name': 'Fixture'}, 'url': 'https://example.org',
                                        'excerpts': ['Fixture quote'], 'answer': {'value': 'fixture'}}]}}
    state = SimpleNamespace(tasks=tasks, output=output, calls=[], grades=[], failure=None, grade_failure=None)
    monkeypatch.setattr(WandrBenchmark, 'load_tasks', lambda self: state.tasks)

    def runner(self, command, **kwargs):
        state.calls.append((command, kwargs))
        assert list(Path(kwargs['cwd']).iterdir()) == []
        assert json.loads(Path(command[command.index('--output-schema') + 1]).read_text()) == self.load('output_schema.json')
        if state.failure:
            return subprocess.CompletedProcess(command, 1, '', state.failure)
        Path(command[command.index('--output-last-message') + 1]).write_text(json.dumps(state.output))
        events = [{'type': 'item.completed', 'item': {'type': 'web_search', 'action': {
            'type': 'search', 'query': 'fixture'}}}, {'type': 'turn.completed', 'usage': {'input_tokens': 10}}]
        return subprocess.CompletedProcess(command, 0, '\n'.join(map(json.dumps, events)), '')

    def grade(self, task, submission, ctx):
        assert isinstance(ctx, GradeContext)
        state.grades.append((task.task_id, copy.deepcopy(submission)))
        if state.grade_failure:
            raise state.grade_failure
        return GradeResult(metrics={'soft_f1_full': .75 if submission['answer.jsonl'] else 0.,
                                    'soft_recall_full': .9 if submission['answer.jsonl'] else 0.},
                           primary_metric='soft_f1_full', judge=ctx.config.judge_label,
                           provenance={'fetch': 'wandr-browser', 'harness_primary_metric': 'soft_recall_full'})

    state.real_process = baseline.RunContext.run_process
    monkeypatch.setattr(baseline.RunContext, 'run_process', runner)
    monkeypatch.setattr(WandrBenchmark, 'grade', grade)
    state.harness = harness
    return state


def test_plain_call_contract_order_isolation_and_complete_archive(tmp_path, config, offline, monkeypatch):
    from loop_research.baseline import baseline
    before = offline.harness.head
    files = {p.relative_to(offline.harness.path): p.read_bytes()
             for p in offline.harness.path.rglob('*') if p.is_file()}
    def forbidden(*args, **kwargs):
        pytest.fail('Baseline must not load harness state or initialize a harness')
    monkeypatch.setattr(Harness, '__init__', forbidden)
    result = baseline(tmp_path, config, 'wandr')
    assert result['task_ids'] == ['t2', 't1', 't3']
    assert result['mode'] == 'baseline' and result['status'] == 'complete'
    assert result['config'] == config.model_dump()
    assert result['harness_before'] == result['harness_after'] == before
    assert files == {p.relative_to(offline.harness.path): p.read_bytes()
                     for p in offline.harness.path.rglob('*') if p.is_file()}
    assert len(offline.calls) == 3
    for row, (command, kwargs) in zip(result['tasks'], offline.calls):
        assert command[1] == 'exec'
        assert command[command.index('--model') + 1] == config.models.root
        assert 'model_reasoning_effort="high"' in command
        assert 'features.shell_tool=false' in command and 'web_search="live"' in command
        assert command[command.index('--sandbox') + 1] == 'read-only'
        assert kwargs['timeout'] > config.codex.timeout_s
        assert kwargs['timeout'] <= config.agent.task_timeout_s
        directory = tmp_path / 'runs' / result['run_id'] / row['task_id']
        prompt = json.loads((directory / 'prompt.txt').read_text())
        assert set(prompt) == {'question', 'spec', 'as_of_date', 'output_contract'}
        assert prompt['question'] == 'Find the fixture.'
        assert prompt['as_of_date'] == '2026-10-18'
        assert kwargs['input'] == (directory / 'prompt.txt').read_text()
        assert json.loads((directory / 'response.txt').read_text()) == offline.output
        assert read_json(directory / 'output.json') == offline.output
        assert read_json(directory / 'submission.json') == offline.output['files']
        assert read_json(directory / 'output_schema.json') == WandrBenchmark(tmp_path, config).output_contract(offline.tasks[0]).schema
        call = read_jsonl(directory / 'codex_calls.jsonl')[0]
        assert call['web_actions'] == [{'type': 'search', 'query': 'fixture'}]
        assert call['prompt'] == kwargs['input'] and json.loads(call['response']) == offline.output
        assert 'web_search' in (directory / 'codex_stdout.jsonl').read_text()
        grade = read_json(tmp_path / 'reports' / result['run_id'] / 'grading' / row['task_id'] / 'grade.json')
        assert grade['judge'] == config.judge_label
        assert grade['provenance']['fetch'] == 'wandr-browser'
        assert row['score'] == .75 and row['primary_metric'] == 'soft_f1_full'


@pytest.mark.parametrize('failure', ['transport', 'invalid_output'])
def test_failure_is_single_call_official_empty_score_and_resume_never_skips(tmp_path, config, offline, failure):
    from loop_research.baseline import baseline
    if failure == 'transport':
        offline.failure = 'fixture transport failure'
    else:
        offline.output = {'wrong': 'shape'}
    with pytest.raises(RuntimeError, match='stopped'):
        baseline(tmp_path, config, 'wandr')
    path, = (tmp_path / 'reports').glob('*/baseline.json')
    interrupted = read_json(path)
    assert len(offline.calls) == len(interrupted['tasks']) == 1
    assert interrupted['tasks'][0]['status'] == 'failed'
    assert interrupted['tasks'][0]['score'] == 0
    assert offline.grades == [('t2', {'answer.jsonl': []})]
    directory = tmp_path / 'runs' / interrupted['run_id'] / 't2'
    assert read_json(directory / 'submission.json') == {'answer.jsonl': []}
    assert (directory / 'response.txt').exists()
    offline.failure = None
    offline.output = {'files': {'answer.jsonl': []}}
    result = baseline(tmp_path, config, 'wandr', resume=True)
    assert result['status'] == 'complete'
    assert [row['task_id'] for row in result['tasks']] == ['t2', 't1', 't3']
    assert len(offline.calls) == 3
    assert result['tasks'][0] == interrupted['tasks'][0]


def test_grading_interruption_resume_matches_uninterrupted_results(tmp_path, config, offline):
    from loop_research.baseline import baseline
    offline.grade_failure = KeyboardInterrupt('fixture interruption')
    with pytest.raises(RuntimeError, match='stopped'):
        baseline(tmp_path, config, 'wandr')
    offline.grade_failure = None
    result = baseline(tmp_path, config, 'wandr', resume=True)
    assert len(offline.calls) == 3
    again = baseline(tmp_path, config, 'wandr', resume=True)
    assert again['tasks'] == result['tasks'] and len(offline.calls) == 3
    uninterrupted = baseline(tmp_path, config, 'wandr')
    assert result['tasks'] == uninterrupted['tasks']
    assert result['as_of_date'] == uninterrupted['as_of_date']


@pytest.mark.parametrize('change', ['config', 'tasks', 'prefix'])
def test_resume_rejects_changed_experiment(tmp_path, config, offline, change):
    from loop_research.baseline import baseline
    result = baseline(tmp_path, config, 'wandr')
    if change == 'config':
        config.models.root = 'different-root'
    elif change == 'tasks':
        offline.tasks[0].question = 'Changed question'
        offline.tasks[2].question = 'Changed question'
    else:
        result['tasks'].reverse()
        write_json(tmp_path / 'reports' / result['run_id'] / 'baseline.json', result)
    with pytest.raises(ValueError):
        baseline(tmp_path, config, 'wandr', resume=True)
    assert len(offline.calls) == 3


def test_harness_head_change_is_detected_even_when_run_fails(tmp_path, config, offline, monkeypatch):
    from loop_research import baseline
    heads = iter(['original', 'changed'])
    monkeypatch.setattr(baseline, 'harness_head', lambda root: next(heads))
    offline.grade_failure = RuntimeError('fixture grade failure')
    with pytest.raises(RuntimeError, match='Harness HEAD changed'):
        baseline.baseline(tmp_path, config, 'wandr')
    path, = (tmp_path / 'reports').glob('*/baseline.json')
    assert read_json(path)['status'] == 'interrupted'


def test_resume_requires_existing_baseline(tmp_path, config):
    from loop_research.baseline import baseline
    with pytest.raises(ValueError, match='No baseline'):
        baseline(tmp_path, config, 'wandr', resume=True)


def test_selection_is_same_prefix_for_stream_and_baseline(config, tmp_path):
    from loop_research.evaluation import select_tasks
    adapter = WandrBenchmark(Path(__file__).resolve().parents[1], config)
    limited = select_tasks(adapter, config, 'wandr')
    assert len(limited) == config.wandr.final_n_tasks
    config.wandr.final_n_tasks = None
    full = select_tasks(adapter, config, 'wandr')
    assert limited == full[:len(limited)]
    config.wandr.final_n_tasks = len(full) + 1
    with pytest.raises(ValueError, match='exceeds'):
        select_tasks(adapter, config, 'wandr')


def test_baseline_imports_no_harness_or_learning_modules():
    from test_import_boundaries import import_graph, reachable
    imported = reachable(import_graph(), 'loop_research.baseline')
    assert not imported.intersection({'loop_research.harness', 'loop_research.session',
                                      'loop_research.agent', 'loop_research.refine'})


def test_timeout_preserves_partial_raw_events_and_gets_official_empty_score(tmp_path, config, offline, monkeypatch):
    from loop_research import baseline
    def timeout(self, command, **kwargs):
        offline.calls.append(command)
        raise subprocess.TimeoutExpired(command, kwargs['timeout'], output=b'{"type":"partial"}\n')
    monkeypatch.setattr(baseline.RunContext, 'run_process', timeout)
    with pytest.raises(RuntimeError, match='stopped'):
        baseline.baseline(tmp_path, config, 'wandr')
    path, = (tmp_path / 'reports').glob('*/baseline.json')
    manifest = read_json(path)
    row, = manifest['tasks']
    assert row['score'] == 0 and row['status'] == 'failed'
    assert len(offline.calls) == 1
    directory = tmp_path / 'runs' / manifest['run_id'] / row['task_id']
    assert (directory / 'codex_stdout.jsonl').read_text() == '{"type":"partial"}\n'
    assert manifest['run_id'] in (tmp_path / 'reports/summary.md').read_text()


def test_cli_baseline_accepts_boolean_resume_and_rejects_other_benchmarks(tmp_path, config, offline):
    import yaml
    from loop_research.cli import app
    (tmp_path / 'config.yaml').write_text(yaml.safe_dump(config.model_dump()))
    runner = CliRunner()
    result = runner.invoke(app, ['--root', str(tmp_path), 'baseline', '--benchmark', 'wandr'])
    assert result.exit_code == 0, result.exception
    assert 'baseline.json' in result.output
    result = runner.invoke(app, ['--root', str(tmp_path), 'baseline', '--benchmark', 'wandr', '--resume'])
    assert result.exit_code == 0, result.exception
    assert len(offline.calls) == 3
    result = runner.invoke(app, ['--root', str(tmp_path), 'baseline', '--benchmark', 'widesearch'])
    assert result.exit_code != 0 and len(offline.calls) == 3


def test_parallel_completion_keeps_sequential_results_archives_and_report_order(tmp_path, config, offline, monkeypatch):
    import csv
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from loop_research import baseline

    sequential = baseline.baseline(tmp_path, config, 'wandr')
    config.codex.max_concurrent = 2
    original = baseline.RunContext.run_process
    started = {task_id: threading.Event() for task_id in ['t2', 't1', 't3']}
    release = threading.Event()
    lock = threading.Lock()
    active = peak = 0
    def runner(ctx, command, **kwargs):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        started[ctx.task_id].set()
        try:
            if ctx.task_id == 't2':
                assert release.wait(5)
            return original(ctx, command, **kwargs)
        finally:
            with lock:
                active -= 1
    monkeypatch.setattr(baseline.RunContext, 'run_process', runner)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(baseline.baseline, tmp_path, config, 'wandr')
        try:
            assert started['t2'].wait(5)
            assert started['t1'].wait(2), 'Second task must run while the first is blocked'
            assert started['t3'].wait(2), 'A completed task must free a slot before the first finishes'
        finally:
            release.set()
        parallel = future.result(timeout=5)
    assert peak == 2
    assert parallel['tasks'] == sequential['tasks']
    for task_id in sequential['task_ids']:
        before = tmp_path / 'runs' / sequential['run_id'] / task_id
        after = tmp_path / 'runs' / parallel['run_id'] / task_id
        for filename in ['prompt.txt', 'response.txt', 'output_schema.json', 'output.json', 'submission.json']:
            assert (before / filename).read_bytes() == (after / filename).read_bytes()
    rows = list(csv.DictReader((tmp_path / 'reports/tasks.csv').open()))
    assert [row['task_id'] for row in rows if row['run_id'] == parallel['run_id']] == ['t2', 't1', 't3']


def test_parallel_resume_keeps_completed_tasks_across_a_gap(tmp_path, config, offline):
    from loop_research.baseline import baseline
    sequential = baseline(tmp_path, config, 'wandr')
    config.codex.max_concurrent = 2
    parallel = baseline(tmp_path, config, 'wandr')
    path = tmp_path / 'reports' / parallel['run_id'] / 'baseline.json'
    parallel['tasks'] = [row for row in parallel['tasks'] if row['task_id'] != 't2']
    parallel['status'] = 'interrupted'
    write_json(path, parallel)
    # Simulate interruption after research, before the first task's grading checkpoint.
    grade_dir = path.parent / 'grading/t2'
    for name in ['task_result.json', 'grading_state.json']:
        (grade_dir / name).unlink()
    state = tmp_path / 'runs' / parallel['run_id'] / 't2/task_state.json'
    write_json(state, {'phase': 'grade', 'error': None})
    count = len(offline.calls)
    resumed = baseline(tmp_path, config, 'wandr', resume=True)
    assert len(offline.calls) == count
    assert resumed['tasks'] == sequential['tasks']


def test_parallel_failure_drains_active_tasks_and_does_not_dispatch_more(tmp_path, config, offline, monkeypatch):
    import threading
    import time
    from loop_research import baseline
    config.codex.max_concurrent = 2
    original = baseline.RunContext.run_process
    both = threading.Barrier(2)
    def runner(ctx, command, **kwargs):
        assert ctx.task_id in {'t2', 't1'}, 'Tasks must not start after a detected failure'
        both.wait(timeout=5)
        if ctx.task_id == 't2':
            offline.calls.append((command, kwargs))
            return subprocess.CompletedProcess(command, 1, '', 'fixture failure')
        deadline = time.monotonic() + 5
        while not read_json(tmp_path / 'reports' / ctx.run_id / 'baseline.json')['tasks']:
            assert time.monotonic() < deadline
            time.sleep(.01)
        return original(ctx, command, **kwargs)
    monkeypatch.setattr(baseline.RunContext, 'run_process', runner)
    with pytest.raises(RuntimeError, match='stopped'):
        baseline.baseline(tmp_path, config, 'wandr')
    path, = (tmp_path / 'reports').glob('*/baseline.json')
    result = read_json(path)
    assert [row['task_id'] for row in result['tasks']] == ['t2', 't1']
    assert [row['status'] for row in result['tasks']] == ['failed', 'succeeded']
    monkeypatch.setattr(baseline.RunContext, 'run_process', original)
    resumed = baseline.baseline(tmp_path, config, 'wandr', resume=True)
    assert len(offline.calls) == 3 and len(resumed['tasks']) == 3


def test_parallel_interruption_terminates_owned_processes_before_releasing_lock(tmp_path, config, offline, monkeypatch):
    import os
    import sys
    import time
    from loop_research import baseline
    config.codex.max_concurrent = 2
    # Use the real process supervisor while replacing only the external Codex executable.
    def runner(ctx, command, **kwargs):
        pidfile = tmp_path / (ctx.task_id + '.pid')
        script = 'import os,time; from pathlib import Path; Path(' + repr(str(pidfile)) + ').write_text(str(os.getpid())); time.sleep(30)'
        return offline.real_process(ctx, [sys.executable, '-c', script], **kwargs)
    monkeypatch.setattr(baseline.RunContext, 'run_process', runner)
    def interrupt(*args, **kwargs):
        deadline = time.monotonic() + 5
        while len(list(tmp_path.glob('*.pid'))) < 2:
            assert time.monotonic() < deadline
            time.sleep(.01)
        raise KeyboardInterrupt('fixture stop')
    monkeypatch.setattr(baseline, 'wait', interrupt)
    with pytest.raises(RuntimeError, match='fixture stop'):
        baseline.baseline(tmp_path, config, 'wandr')
    for pidfile in tmp_path.glob('*.pid'):
        with pytest.raises(ProcessLookupError):
            os.kill(int(pidfile.read_text()), 0)
    path, = (tmp_path / 'reports').glob('*/baseline.json')
    manifest = read_json(path)
    assert manifest['status'] == 'interrupted' and manifest['tasks'] == []


def test_grading_cancellation_preserves_successful_submission_for_resume(tmp_path, config, offline, monkeypatch):
    from concurrent.futures import CancelledError, Future
    from loop_research.archive import RunContext
    from loop_research.evaluation import _grade
    cancellation = Future()
    cancellation.cancel()
    task = offline.tasks[0]
    ctx = GradeContext(tmp_path, 'fixture-cancel', config, task.task_id, cancellation)
    RunContext(tmp_path, ctx.run_id, config, task.task_id).save('submission.json', offline.output['files'])
    original = WandrBenchmark.grade
    def grade(self, task, submission, ctx):
        ctx.check_cancelled()
        return original(self, task, submission, ctx)
    monkeypatch.setattr(WandrBenchmark, 'grade', grade)
    adapter = WandrBenchmark(tmp_path, config)
    with pytest.raises(CancelledError):
        _grade(task, adapter, ctx, False)
    assert ctx.load('grading_state.json') == {'empty': False, 'errors': [], 'complete': False}
    ctx.cancellation = None
    result, errors = _grade(task, adapter, ctx, False)
    assert result.metrics['soft_f1_full'] == .75 and errors == []
    assert offline.grades == [(task.task_id, offline.output['files'])]
