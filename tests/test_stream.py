import copy
import json
import os
from types import SimpleNamespace

import pytest

from loop_research import session as session_module, stream
from loop_research.agent import AgentResult
from loop_research.archive import GradeContext, RunContext, read_json
from loop_research.benchmarks import GradeResult
from loop_research.harness import Harness
from loop_research.research import ResearchData
from test_refine import accounted_fixture


class Benchmark(ResearchData):
    def __init__(self, tasks):
        self.tasks, self.calls = tasks, []
        self.failure = None

    def load_tasks(self):
        return self.tasks

    def grade(self, task, submission, ctx):
        assert isinstance(ctx, GradeContext)
        self.calls.append((task.task_id, copy.deepcopy(submission)))
        ctx.save('private_grade_evidence.json', {'SECRET_GOLD': 'official fixture evidence'})
        if self.failure is not None:
            self.failure(task, submission)
        return GradeResult(metrics={'f1': .75 if submission['rows'] else 0.0},
                           primary_metric='f1', judge=ctx.config.judge_label)


@pytest.fixture
def offline(tmp_path, task, output, monkeypatch):
    state = SimpleNamespace(adapter=Benchmark([task]), research=[], observed=[], plans=[], events=[],
                            research_error=None, plan_failures=0, plan_failure_at=None, edits=[])

    class Planner:
        def complete(self, prompt, **options):
            assert options['purpose'] == 'refine'
            state.plans.append(prompt)
            state.events.append('refine')
            assert 'SECRET_GOLD' not in prompt
            if state.plan_failures or len(state.plans) == state.plan_failure_at:
                state.plan_failures = max(0, state.plan_failures - 1)
                raise ValueError('fixture refinement failed')
            return json.dumps(accounted_fixture({'summary': 'Fixture procedure', 'edits': state.edits}, prompt))

    monkeypatch.setattr(session_module, 'CodexBackend', lambda *args, **kwargs: Planner())
    monkeypatch.setattr(stream, 'load_benchmark', lambda *args: state.adapter)
    monkeypatch.setattr(stream, 'verify_isolation', lambda: 'isolation tested separately')

    def research(task, adapter, session):
        state.research.append(task.task_id)
        state.events.append('research')
        state.observed.append(session.harness.list())
        if state.research_error is not None:
            raise state.research_error
        session.output = copy.deepcopy(output)
        session.ctx.save('submission.json', adapter.to_submission(task, session.output))
        session.ctx.save('output.json', session.output)
        session.ctx.save('agent_result.json', AgentResult(output=session.output, errors=[], uncited=[],
                         as_of_date='2026-10-18', date_source='fixture', status=session.status).model_dump())

    monkeypatch.setattr(stream, 'run_task', research)
    return state


def interrupted_manifest(root):
    paths = list((root / 'reports').glob('*/stream.json'))
    assert len(paths) == 1
    return read_json(paths[0])


def test_seeded_stream_grades_only_reports_and_refines_after_check(tmp_path, config, task, offline):
    offline.adapter.tasks = [task.model_copy(update={'task_id': f't{i}'}) for i in range(3)]
    result = stream.stream(tmp_path, config, 'widesearch')
    assert offline.research == ['t1', 't0', 't2']
    assert offline.events == ['research', 'refine'] * 3
    assert [item['score'] for item in result['tasks']] == [.75] * 3
    assert result['status'] == 'complete'
    assert all(item['error'] is None and item['status'] == 'succeeded' for item in result['tasks'])
    assert all('"self_check"' in prompt and 'unchecked_constraint' in prompt for prompt in offline.plans)
    for task_id in offline.research:
        ctx = RunContext(tmp_path, result['run_id'], config, task_id)
        assert ctx.load('task_state.json')['phase'] == 'complete'
        assert ctx.load('session_state.json')['finish_phase'] == 'complete'
        assert not list(ctx.path.glob('*grad*'))
    assert 'SECRET_GOLD' not in json.dumps(Harness(tmp_path / 'harness').snapshot())
    assert read_json(tmp_path / 'reports' / result['run_id'] / 'stream.json') == result


def test_no_learning_requires_explicit_base_then_restores_learning_branch(tmp_path, config, offline):
    with pytest.raises(ValueError, match='--no-learning requires --base'):
        stream.stream(tmp_path, config, 'widesearch', no_learning=True)
    assert offline.research == [] and not list((tmp_path / 'reports').glob('*/stream.json'))
    offline.edits = [{'action': 'create', 'kind': 'skill', 'id': None, 'title': 'Check sources',
                      'content': 'Open source pages before citing them.', 'module': None}]
    learned = stream.stream(tmp_path, config, 'widesearch')
    harness = Harness(tmp_path / 'harness')
    branch, head = harness.branch, harness.head
    baseline = stream.stream(tmp_path, config, 'widesearch', no_learning=True, base=learned['base_sha'])
    assert baseline['base_sha'] == learned['base_sha']
    assert baseline['learning'] is False and baseline['lineage'] != learned['lineage']
    assert [item['score'] for item in baseline['tasks']] == [.75]
    assert offline.observed == [[], []] and len(offline.plans) == 1
    assert harness.branch == branch and harness.head == head and len(harness.list()) == 1


def test_base_uses_earliest_preexposure_ancestor_not_manifest_mtime(tmp_path, config, task, offline):
    first_task = task.model_copy(update={'task_id': 'first'})
    second_task = task.model_copy(update={'task_id': 'second'})
    offline.adapter.tasks = [first_task]
    first = stream.stream(tmp_path, config, 'widesearch')
    offline.adapter.tasks = [second_task]
    second = stream.stream(tmp_path, config, 'widesearch')
    assert first['base_sha'] != second['base_sha']
    harness = Harness(tmp_path / 'harness')
    paths = [tmp_path / 'reports' / run['run_id'] / 'stream.json' for run in (first, second)]
    for times in ((100, 200), (300, 100)):
        for path, timestamp in zip(paths, times):
            os.utime(path, (timestamp, timestamp))
        assert stream._base(harness, [second_task, first_task]) == first['base_sha']
    with pytest.raises(ValueError, match='already contains research'):
        stream._base(harness, [first_task, second_task], second['base_sha'])
    assert stream._base(harness, [first_task, second_task], first['base_sha']) == first['base_sha']


def test_failed_research_receives_official_empty_grade_and_failure_selfcheck(tmp_path, config, offline):
    offline.research_error = TimeoutError('fixture timeout')
    result = stream.stream(tmp_path, config, 'widesearch')
    row = result['tasks'][0]
    assert row['score'] == 0.0 and row['status'] == 'failed' and 'fixture timeout' in row['error']
    assert offline.adapter.calls == [('fixture', {'rows': []})]
    from loop_research.refine import INSTRUCTIONS
    from loop_research.shared_text import decode_shared_text
    assert len(offline.plans) == 1
    planner_input = decode_shared_text(json.loads(offline.plans[0].removeprefix(INSTRUCTIONS)))
    assert any(issue['type'] == 'timeout' for issue in planner_input['self_check']['issues'])
    ctx = RunContext(tmp_path, result['run_id'], config, 'fixture')
    assert any(item['type'] == 'timeout' for item in ctx.load('self_check.json')['issues'])
    graded = GradeContext(tmp_path, result['run_id'], config, 'fixture').load('grade.json')
    assert graded['metrics']['f1'] == 0.0 and graded['judge'] == config.judge_label


def test_grader_failure_retries_empty_without_leaking_into_learning(tmp_path, config, output, offline):
    def fail_original(task, submission):
        if submission['rows']:
            raise RuntimeError('SECRET_GOLD original grader failure')
    offline.adapter.failure = fail_original
    result = stream.stream(tmp_path, config, 'widesearch')
    assert offline.adapter.calls == [('fixture', output), ('fixture', {'rows': []})]
    row = result['tasks'][0]
    assert row['score'] == 0.0 and row['status'] == 'failed' and 'SECRET_GOLD' in row['error']
    ctx = RunContext(tmp_path, result['run_id'], config, 'fixture')
    assert ctx.load('task_state.json')['error'] is None
    assert not (ctx.path / 'error.json').exists()
    assert 'worker_error' not in ctx.load('task_state.json')['status']
    assert 'SECRET_GOLD' not in '\n'.join(path.read_text() for path in ctx.path.glob('*.json'))
    assert 'SECRET_GOLD' not in json.dumps(Harness(tmp_path / 'harness').snapshot())


def test_empty_grader_failure_interrupts_and_resume_retries_without_research(tmp_path, config, output, offline):
    def fail_grading(task, submission):
        raise RuntimeError('SECRET_GOLD grader unavailable')
    offline.adapter.failure = fail_grading
    with pytest.raises(RuntimeError, match='Official empty-submission grading failed'):
        stream.stream(tmp_path, config, 'widesearch')
    stopped = interrupted_manifest(tmp_path)
    assert stopped['status'] == 'interrupted' and stopped['phase'] == 'grade' and stopped['tasks'] == []
    assert offline.research == ['fixture'] and offline.plans == []
    assert offline.adapter.calls == [('fixture', output), ('fixture', {'rows': []})]
    offline.adapter.failure = None
    resumed = stream.stream(tmp_path, config, 'widesearch', resume=stopped['run_id'])
    assert resumed['status'] == 'complete' and resumed['lineage'] == stopped['lineage']
    assert offline.research == ['fixture'] and len(offline.plans) == 1
    assert offline.adapter.calls == [('fixture', output), ('fixture', {'rows': []}), ('fixture', {'rows': []})]
    assert resumed['tasks'][0]['score'] == 0.0 and resumed['tasks'][0]['status'] == 'failed'
    assert 'SECRET_GOLD' in resumed['tasks'][0]['error']


@pytest.mark.parametrize('failure_at', [1, 2])
def test_refinement_failure_stops_before_next_task_and_resumes_same_lineage(tmp_path, config, task, offline, failure_at):
    offline.adapter.tasks = [task.model_copy(update={'task_id': f't{i}'}) for i in range(3)]
    offline.plan_failure_at = failure_at
    with pytest.raises(RuntimeError, match='Refinement failed'):
        stream.stream(tmp_path, config, 'widesearch')
    stopped = interrupted_manifest(tmp_path)
    order = ['t1', 't0', 't2']
    assert stopped['phase'] == 'finish' and stopped['active_task_id'] == order[failure_at - 1]
    assert [item['task_id'] for item in stopped['tasks']] == order[:failure_at - 1]
    assert offline.research == order[:failure_at]
    assert len(offline.adapter.calls) == len(offline.plans) == failure_at
    harness = Harness(tmp_path / 'harness')
    harness.git('checkout', '-q', stopped['return_branch'])
    result = stream.stream(tmp_path, config, 'widesearch', resume=stopped['run_id'])
    assert result['status'] == 'complete' and result['lineage'] == stopped['lineage']
    assert result['base_sha'] == stopped['base_sha'] and harness.branch == stopped['lineage']
    assert result['task_ids'] == [row['task_id'] for row in result['tasks']] == ['t1', 't0', 't2']
    assert offline.research == ['t1', 't0', 't2']
    assert [task_id for task_id, _ in offline.adapter.calls] == ['t1', 't0', 't2']
    assert len(offline.plans) == 4 and all(row['score'] == .75 for row in result['tasks'])
    assert result['tasks'][:failure_at - 1] == stopped['tasks']


def test_grade_checkpoint_survives_failed_grade_result_mirror(tmp_path, config, offline, monkeypatch):
    original = GradeContext.save
    failed = False

    def fail_grade_mirror(ctx, name, value):
        nonlocal failed
        if name == 'grade.json' and not failed:
            failed = True
            raise OSError('fixture grade mirror write interrupted')
        return original(ctx, name, value)

    monkeypatch.setattr(GradeContext, 'save', fail_grade_mirror)
    with pytest.raises(RuntimeError, match='fixture grade mirror write interrupted'):
        stream.stream(tmp_path, config, 'widesearch')
    stopped = interrupted_manifest(tmp_path)
    assert stopped['phase'] == 'grade' and stopped['tasks'] == []
    grade_ctx = GradeContext(tmp_path, stopped['run_id'], config, 'fixture')
    checkpoint = grade_ctx.load('grading_state.json')
    assert checkpoint['complete'] is True and checkpoint['result']['metrics'] == {'f1': .75}
    assert grade_ctx.load('grade.json') is None
    assert offline.research == ['fixture'] and len(offline.adapter.calls) == 1 and not offline.plans
    result = stream.stream(tmp_path, config, 'widesearch', resume=stopped['run_id'])
    assert result['tasks'][0]['score'] == .75 and result['tasks'][0]['status'] == 'succeeded'
    assert grade_ctx.load('grade.json') == checkpoint['result']
    assert offline.research == ['fixture'] and len(offline.adapter.calls) == len(offline.plans) == 1


@pytest.mark.parametrize('research_complete', [True, False])
def test_research_phase_recovery_uses_completion_marker_without_repeating_worker(tmp_path, config, output, offline, monkeypatch, research_complete):
    original = stream.run_task

    def interrupted_worker(task, adapter, session):
        session.status['iteration_limit'] = True
        original(task, adapter, session)
        if not research_complete:
            (session.ctx.path / 'agent_result.json').unlink()
        raise KeyboardInterrupt('fixture process interrupted before task checkpoint')

    monkeypatch.setattr(stream, 'run_task', interrupted_worker)
    with pytest.raises(RuntimeError, match='fixture process interrupted before task checkpoint'):
        stream.stream(tmp_path, config, 'widesearch')
    stopped = interrupted_manifest(tmp_path)
    ctx = RunContext(tmp_path, stopped['run_id'], config, 'fixture')
    assert stopped['phase'] == ctx.load('task_state.json')['phase'] == 'research'
    assert offline.research == ['fixture'] and not offline.adapter.calls and not offline.plans
    assert (ctx.load('agent_result.json') is not None) is research_complete
    result = stream.stream(tmp_path, config, 'widesearch', resume=stopped['run_id'])
    assert offline.research == ['fixture'] and len(offline.plans) == 1
    assert offline.adapter.calls == [('fixture', output if research_complete else {'rows': []})]
    row = result['tasks'][0]
    assert row['score'] == (.75 if research_complete else 0.0)
    assert row['status'] == ('succeeded' if research_complete else 'failed')
    issue = 'iteration_limit' if research_complete else 'worker_error'
    assert ctx.load('task_state.json')['status'][issue] is True
    assert issue in {item['type'] for item in ctx.load('self_check.json')['issues']}
    if not research_complete:
        assert 'Research interrupted before completion' in row['error']


def test_resume_after_refinement_commit_matches_uninterrupted_harness_without_duplicate_edit(tmp_path, config, offline, monkeypatch):
    offline.edits = [{'action': 'create', 'kind': 'memory', 'id': None, 'title': 'Verify page wording',
                      'content': 'Keep an exact supporting quotation for every constraint.', 'module': None}]
    control_root, recovery_root = tmp_path / 'control', tmp_path / 'recovery'
    control = stream.stream(control_root, config, 'widesearch')
    control_entries = Harness(control_root / 'harness').list()
    offline.research.clear()
    offline.adapter.calls.clear()
    offline.plans.clear()
    original = RunContext.save
    failed = False

    def fail_after_edit_commit(ctx, name, value):
        nonlocal failed
        if name == 'refine_state.json' and value['status'] == 'applied' and not failed:
            failed = True
            raise OSError('fixture stop after committed refinement')
        return original(ctx, name, value)

    monkeypatch.setattr(RunContext, 'save', fail_after_edit_commit)
    with pytest.raises(RuntimeError, match='fixture stop after committed refinement'):
        stream.stream(recovery_root, config, 'widesearch')
    stopped = interrupted_manifest(recovery_root)
    ctx = RunContext(recovery_root, stopped['run_id'], config, 'fixture')
    session_state = ctx.load('session_state.json')
    assert session_state['finish_phase'] == 'automatic'
    assert ctx.load('refine_state.json')['status'] == 'planned'
    harness = Harness(recovery_root / 'harness')
    assert len(harness.list()) == 1
    edits = {path.name: path.read_bytes() for path in (harness.path / 'edits').glob('*.json')}
    head = harness.head
    recovered = stream.stream(recovery_root, config, 'widesearch', resume=stopped['run_id'])
    assert [row['score'] for row in recovered['tasks']] == [row['score'] for row in control['tasks']] == [.75]
    fields = ('kind', 'title', 'body', 'module', 'version')
    assert [{key: item[key] for key in fields} for item in harness.list()] == [
        {key: item[key] for key in fields} for item in control_entries]
    assert {path.name: path.read_bytes() for path in (harness.path / 'edits').glob('*.json')} == edits
    assert len(edits) == 1 and harness.head == head
    assert offline.research == ['fixture'] and len(offline.adapter.calls) == len(offline.plans) == 1
    assert ctx.load('session_state.json')['finish_phase'] == 'complete'
    assert ctx.load('session_state.json')['automatic_id'] == session_state['automatic_id']
    assert ctx.load('refine_state.json')['status'] == 'applied'


def test_no_learning_finish_interruption_and_resume_restore_live_branch(tmp_path, config, offline, monkeypatch):
    offline.edits = [{'action': 'create', 'kind': 'memory', 'id': None, 'title': 'Check dates',
                      'content': 'Record publication dates before comparing sources.', 'module': None}]
    learned = stream.stream(tmp_path, config, 'widesearch')
    harness = Harness(tmp_path / 'harness')
    branch, head = harness.branch, harness.head
    original = RunContext.save
    failed = False

    def fail_baseline_finish(ctx, name, value):
        nonlocal failed
        if (ctx.run_id != learned['run_id'] and name == 'session_state.json' and
                value['finish_phase'] == 'complete' and not failed):
            failed = True
            raise OSError('fixture baseline finish interrupted')
        return original(ctx, name, value)

    monkeypatch.setattr(RunContext, 'save', fail_baseline_finish)
    with pytest.raises(RuntimeError, match='fixture baseline finish interrupted'):
        stream.stream(tmp_path, config, 'widesearch', no_learning=True, base=learned['base_sha'])
    manifests = [read_json(path) for path in (tmp_path / 'reports').glob('*/stream.json')]
    stopped = next(item for item in manifests if item['learning'] is False)
    assert stopped['status'] == 'interrupted' and stopped['phase'] == 'finish'
    assert harness.branch == branch and harness.head == head
    assert len(offline.research) == len(offline.adapter.calls) == 2 and len(offline.plans) == 1
    resumed = stream.stream(tmp_path, config, 'widesearch', resume=stopped['run_id'])
    assert resumed['learning'] is False and resumed['lineage'] == stopped['lineage']
    assert resumed['status'] == 'complete' and resumed['tasks'][0]['score'] == .75
    assert harness.branch == branch and harness.head == head
    assert json.loads(harness.git('show', resumed['lineage'] + ':harness_state.json'))['entries'] == {}
    assert len(offline.research) == len(offline.adapter.calls) == 2 and len(offline.plans) == 1


def test_completed_task_checkpoint_survives_interruption_before_manifest_append(tmp_path, config, offline, monkeypatch):
    original = stream._task
    completed = []

    def stop_after_task(*args, **kwargs):
        result = original(*args, **kwargs)
        if not completed:
            completed.append(result)
            raise RuntimeError('fixture stop before manifest append')
        return result

    monkeypatch.setattr(stream, '_task', stop_after_task)
    with pytest.raises(RuntimeError, match='fixture stop before manifest append'):
        stream.stream(tmp_path, config, 'widesearch')
    stopped = interrupted_manifest(tmp_path)
    assert stopped['phase'] == 'complete' and stopped['tasks'] == []
    harness = Harness(tmp_path / 'harness')
    head = harness.head
    result = stream.stream(tmp_path, config, 'widesearch', resume=stopped['run_id'])
    assert len(result['tasks']) == 1 and result['tasks'][0]['harness_after'] == completed[0]['harness_after']
    assert result['tasks'][0]['score'] == completed[0]['score'] == .75
    assert offline.research == ['fixture'] and len(offline.adapter.calls) == len(offline.plans) == 1
    assert harness.head == head


@pytest.mark.parametrize('change', ['configuration', 'tasks'])
def test_resume_rejects_changed_configuration_or_task_content(tmp_path, config, task, offline, change):
    result = stream.stream(tmp_path, config, 'widesearch')
    changed = config.model_copy(deep=True)
    if change == 'configuration':
        changed.models.root = 'different-fixture-model'
    else:
        offline.adapter.tasks = [task.model_copy(update={'question': 'Changed research question'})]
    with pytest.raises(ValueError, match='identical benchmark, configuration and ordered tasks'):
        stream.stream(tmp_path, changed, 'widesearch', resume=result['run_id'])
    assert offline.research == ['fixture'] and len(offline.adapter.calls) == len(offline.plans) == 1
    assert read_json(tmp_path / 'reports' / result['run_id'] / 'stream.json') == result


def test_resume_rejects_external_changes_to_interrupted_lineage(tmp_path, config, offline):
    offline.plan_failures = 1
    with pytest.raises(RuntimeError, match='Refinement failed'):
        stream.stream(tmp_path, config, 'widesearch')
    stopped = interrupted_manifest(tmp_path)
    harness = Harness(tmp_path / 'harness')
    harness.create('memory', 'External change', 'This was not part of the interrupted task.')
    with pytest.raises(ValueError, match='(?i)(lineage|harness|changed)'):
        stream.stream(tmp_path, config, 'widesearch', resume=stopped['run_id'])
    assert offline.research == ['fixture'] and len(offline.adapter.calls) == len(offline.plans) == 1


def test_report_failure_preserves_stream_error_and_resume_guidance(tmp_path, config, offline, monkeypatch):
    from loop_research import report
    offline.plan_failures = 1

    def broken_report(root):
        raise ValueError('fixture broken report')

    monkeypatch.setattr(report, 'build_report', broken_report)
    with pytest.raises(RuntimeError) as failure:
        stream.stream(tmp_path, config, 'widesearch')
    stopped = interrupted_manifest(tmp_path)
    assert stopped['status'] == 'interrupted' and stopped['phase'] == 'finish'
    assert 'Refinement failed' in str(failure.value)
    assert 'fixture broken report' in str(failure.value)
    assert '--resume ' + stopped['run_id'] in str(failure.value)


def test_freeform_research_uses_own_adapter_and_metadata(tmp_path, config, offline, monkeypatch):
    seen = []
    original = stream.run_task

    def research(task, adapter, session):
        seen.append((task, adapter))
        return original(task, adapter, session)

    monkeypatch.setattr(stream, 'run_task', research)
    monkeypatch.setattr(stream, 'load_benchmark', lambda *args: pytest.fail('Free-form research loaded a benchmark'))
    result = stream.research(tmp_path, config, 'Find fixture facts', ['entity', 'value'], ['entity'], 'fr')
    task, adapter = seen[0]
    assert type(adapter) is ResearchData and task.benchmark == 'research' and task.language == 'fr'
    assert result['status'] == 'succeeded' and result['score'] is None and result['primary_metric'] is None
    summary = RunContext(tmp_path, result['run_id'], config, task.task_id).load('run_summary.json')
    assert summary['kind'] == summary['benchmark'] == 'research'
    assert set(Harness(tmp_path / 'harness').snapshot()['seen']) == {'research:' + task.task_id}
    assert offline.adapter.calls == [] and len(offline.plans) == 1


def test_research_comparison_uses_explicit_base_and_restores_learning_branch(tmp_path, config, offline):
    with pytest.raises(ValueError, match='--no-learning requires --base'):
        stream.research(tmp_path, config, 'Fixture A', ['entity', 'value'], ['entity'], 'en', no_learning=True)
    harness = Harness(tmp_path / 'harness')
    base = harness.head
    offline.edits = [{'action': 'create', 'kind': 'memory', 'id': None, 'title': 'Fixture procedure',
                      'content': 'Inspect fixture source evidence.', 'module': None}]
    first = stream.research(tmp_path, config, 'Fixture A', ['entity', 'value'], ['entity'], 'en')
    second = stream.research(tmp_path, config, 'Fixture B', ['entity', 'value'], ['entity'], 'en')
    assert first['base_sha'] == base and second['base_sha'] == first['harness_after']
    branch, head = harness.branch, harness.head
    plans = len(offline.plans)
    baseline = stream.research(tmp_path, config, 'Fixture B', ['entity', 'value'], ['entity'], 'en',
                               no_learning=True, base=base, trace=True)
    assert baseline['base_sha'] == base and baseline['learning'] is False
    assert baseline['lineage'] != second['lineage'] and len(offline.plans) == plans
    assert offline.observed[-1] == []
    assert harness.branch == branch and harness.head == head
    manifest = read_json(tmp_path / 'runs' / baseline['run_id'] / 'research.json')
    assert manifest['base_sha'] == base and manifest['return_branch'] == branch
    assert manifest['status'] == 'complete' and manifest['learning'] is False
    with pytest.raises(ValueError, match='already contains research'):
        stream.research(tmp_path, config, 'Fixture B', ['entity', 'value'], ['entity'], 'en', base=head)
    assert harness.branch == branch and harness.head == head


def test_research_no_learning_restores_branch_on_finalization_failure(tmp_path, config, offline, monkeypatch):
    harness = Harness(tmp_path / 'harness')
    base, branch = harness.head, harness.branch
    def fail(*args, **kwargs):
        raise RuntimeError('fixture finalization error')
    monkeypatch.setattr(stream.Session, 'finish', fail)
    with pytest.raises(RuntimeError, match='finalization error'):
        stream.research(tmp_path, config, 'Fixture', ['entity', 'value'], ['entity'], 'en',
                        no_learning=True, base=base)
    assert harness.head == base and harness.branch == branch
    manifest = read_json(next((tmp_path / 'runs').glob('*/research.json')))
    assert manifest['status'] == 'interrupted' and 'finalization error' in manifest['error']
