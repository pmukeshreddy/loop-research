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
