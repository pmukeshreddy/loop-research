import json

import pytest

from loop_research import stream
from loop_research.archive import read_json
from loop_research.benchmarks import GradeResult
from loop_research.harness import Harness


class Benchmark:
    def __init__(self, tasks):
        self.tasks = tasks

    def load_tasks(self):
        return self.tasks

    def grade(self, task, submission, ctx):
        assert 'reports' in ctx.path.parts
        ctx.save('grade.json', {'SECRET_GRADE': 0.75})
        return GradeResult(metrics={'f1': .75}, primary_metric='f1', judge=ctx.config.judge_label)


def test_seeded_stream_grades_only_reports_and_refines_after_check(tmp_path, config, task, monkeypatch):
    tasks = [task.model_copy(update={'task_id': f't{i}'}) for i in range(3)]
    benchmark = Benchmark(tasks)
    monkeypatch.setattr(stream, 'load_benchmark', lambda *a: benchmark)
    monkeypatch.setattr(stream, 'verify_isolation', lambda: 'tested separately')
    order, events = [], []
    def research(task, benchmark, session):
        order.append(task.task_id); events.append('research')
        session.output = {'rows': []}
        session.ctx.save('submission.json', {})
        session.ctx.save('output.json', session.output)
    monkeypatch.setattr(stream, 'run_task', research)
    def finish(session):
        report = session.self_check(); events.append('selfcheck')
        payload = json.dumps(session.observation())
        assert 'SECRET_GRADE' not in payload and '0.75' not in payload
        assert not list(session.ctx.path.glob('*grade*'))
        events.append('refine')
        session.harness.create('memory', 'Failure', 'Check empty evidence', evidence=[session.run_id])
        session.refiner.close()
        return report
    monkeypatch.setattr(stream.Session, 'finish', finish)
    result = stream.stream(tmp_path, config, 'widesearch')
    assert order == ['t1', 't0', 't2']
    assert events == ['research', 'selfcheck', 'refine'] * 3
    assert [r['score'] for r in result['tasks']] == [.75] * 3
    assert all(r['error'] is None for r in result['tasks'])
    h = Harness(tmp_path / 'harness')
    assert 'SECRET_GRADE' not in json.dumps(h.snapshot())
    assert read_json(tmp_path / 'reports' / result['run_id'] / 'stream.json') == result


def test_no_learning_uses_identical_pre_stream_commit_and_restores_live_branch(tmp_path, config, task, monkeypatch):
    benchmark = Benchmark([task])
    monkeypatch.setattr(stream, 'load_benchmark', lambda *a: benchmark)
    monkeypatch.setattr(stream, 'verify_isolation', lambda: 'tested separately')
    observed = []
    def research(task, benchmark, session):
        observed.append(session.harness.list())
        session.ctx.save('submission.json', {})
        session.ctx.save('output.json', {'rows': []})
    monkeypatch.setattr(stream, 'run_task', research)
    def finish(session):
        if session.learning:
            session.harness.create('skill', 'Successful tactic', 'Check official pages')
        session.refiner.close()
        return session.self_check()
    monkeypatch.setattr(stream.Session, 'finish', finish)
    learned = stream.stream(tmp_path, config, 'widesearch')
    h = Harness(tmp_path / 'harness'); branch = h.branch
    baseline = stream.stream(tmp_path, config, 'widesearch', no_learning=True)
    assert baseline['base_sha'] == learned['base_sha']
    assert learned['tasks'][0]['error'] is baseline['tasks'][0]['error'] is None
    assert observed == [[], []]
    assert h.branch == branch and len(h.list()) == 1


def test_failed_research_is_selfchecked_refined_and_has_no_fabricated_score(tmp_path, config, task, monkeypatch):
    monkeypatch.setattr(stream, 'load_benchmark', lambda *a: Benchmark([task]))
    monkeypatch.setattr(stream, 'verify_isolation', lambda: 'tested separately')
    def fail(*a):
        raise TimeoutError('fixture timeout')
    monkeypatch.setattr(stream, 'run_task', fail)
    checks = []
    def finish(session):
        checks.append(session.self_check()); session.refiner.close()
        return checks[-1]
    monkeypatch.setattr(stream.Session, 'finish', finish)
    result = stream.stream(tmp_path, config, 'widesearch')
    assert result['tasks'][0]['score'] is None
    assert 'timeout' in result['tasks'][0]['error']
    assert any(i['type'] == 'timeout' for i in checks[0]['issues'])


def test_grader_failure_cannot_become_learning_feedback(tmp_path, config, task, monkeypatch):
    class FailedGrade(Benchmark):
        def grade(self, *args):
            raise RuntimeError('SECRET_GOLD grader failure')
    monkeypatch.setattr(stream, 'load_benchmark', lambda *a: FailedGrade([task]))
    monkeypatch.setattr(stream, 'verify_isolation', lambda: 'tested separately')
    monkeypatch.setattr(stream, 'run_task', lambda t, b, s: s.ctx.save('submission.json', {}))
    def finish(session):
        assert 'worker_error' not in session.status
        assert 'SECRET_GOLD' not in json.dumps(session.observation())
        assert not (session.ctx.path / 'error.json').exists()
        session.refiner.close()
        return session.self_check()
    monkeypatch.setattr(stream.Session, 'finish', finish)
    result = stream.stream(tmp_path, config, 'widesearch')
    assert result['tasks'][0]['score'] is None and 'SECRET_GOLD' in result['tasks'][0]['error']
    assert 'refine:' not in result['tasks'][0]['error']
    assert not list((tmp_path / 'runs').glob('**/error.json'))
