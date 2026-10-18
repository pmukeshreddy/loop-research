"""Sequential research/grade/check/refine with durable, lineage-safe recovery."""
from contextlib import contextmanager
from datetime import date
import fcntl
import json
import math
from pathlib import Path
import random
import re
from uuid import uuid4

from .agent import AgentResult, run_task
from .archive import RunContext, GradeContext, digest, read_json, stamp, write_json
from .benchmarks import GradeResult, Task
from .harness import Harness
from .isolation import verify_isolation
from .research import ResearchData, validate_research_spec
from .session import Session


def load_benchmark(name, root, config):
    if name == 'widesearch':
        from .benchmarks.widesearch.grader import WideSearchBenchmark
        return WideSearchBenchmark(root, config)
    if name == 'wandr':
        from .benchmarks.wandr.grader import WandrBenchmark
        return WandrBenchmark(root, config)
    raise ValueError('Unknown benchmark: ' + name)


@contextmanager
def workspace(harness):
    with (harness.path / '.git/session.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('Another task is using this harness; wait for it to finish') from exc
        yield


def _error(exc):
    return f'{type(exc).__name__}: {exc}'


def _grade(task, adapter, ctx, failed):
    state = ctx.load('grading_state.json', {'empty': failed, 'errors': [], 'complete': False})
    if state['complete']:
        result = GradeResult.model_validate(state['result'])
        ctx.save('grade.json', result.model_dump())
        return result, state['errors']
    while True:
        ctx.save('grading_state.json', state)
        submission = (adapter.to_submission(task, adapter.output_contract(task).empty) if state['empty'] else
                      RunContext(ctx.root, ctx.run_id, ctx.config, task.task_id).load('submission.json'))
        try:
            result = adapter.grade(task, submission, ctx)
            if result.judge != ctx.config.judge_label or not math.isfinite(result.metrics[result.primary_metric]):
                raise ValueError('Official grader returned an invalid score or judge label')
        except Exception as exc:
            state['errors'].append(_error(exc))
            already_empty = state['empty']
            state['empty'] = True
            ctx.save('grading_state.json', state)
            if already_empty:
                raise RuntimeError('Official empty-submission grading failed: ' + _error(exc)) from exc
        else:
            state.update(complete=True, result=result.model_dump())
            ctx.save('grading_state.json', state)
            ctx.save('grade.json', result.model_dump())
            return result, state['errors']


def _task(task, benchmark, ctx, harness, learning, *, grade):
    state = ctx.load('task_state.json')
    resumed = state is not None
    grade_ctx = GradeContext(ctx.root, ctx.run_id, ctx.config, task.task_id)
    if state and state['phase'] == 'complete':
        return grade_ctx.load('task_result.json')
    if state is None:
        seen = harness.snapshot()['seen'].get(task.benchmark + ':' + task.task_id)
        identity = ctx.run_id + '/' + task.task_id
        before = (seen['before'] if seen and seen['run_id'] == identity else
                  harness.begin_task(task.benchmark + ':' + task.task_id, identity))
        ctx.initialize(before, kind='research', benchmark=task.benchmark)
        state = {'phase': 'research', 'before': before, 'status': {}, 'error': None,
                 'output': benchmark.output_contract(task).empty}
        ctx.save('task_state.json', state)
    session = Session(task, ctx, harness, learning=learning, resume=resumed)
    session.status, session.output = state['status'], state['output']
    try:
        if state['phase'] == 'research':
            try:
                if resumed:
                    if ctx.load('submission.json') is None or ctx.load('agent_result.json') is None:
                        raise RuntimeError('Research interrupted before completion')
                    archived = AgentResult.model_validate(ctx.load('agent_result.json'))
                    session.output, session.status = archived.output, archived.status
                else:
                    run_task(task, benchmark, session)
            except Exception as exc:
                state['error'] = _error(exc)
                session.status['timeout' if isinstance(exc, TimeoutError) else 'worker_error'] = True
                session.output = benchmark.output_contract(task).empty
                ctx.save('error.json', {'error': state['error']})
            finally:
                session.close_worker()
            state.update(phase='grade', status=session.status, output=session.output)
            ctx.save('task_state.json', state)
        graded, grade_errors = _grade(task, benchmark, grade_ctx, bool(state['error'])) if grade else (None, [])
        state['phase'] = 'finish'
        ctx.save('task_state.json', state)
        report = session.finish()
        error = '; '.join(filter(None, [state['error'], *grade_errors])) or None
        result = {'task_id': task.task_id, 'score': graded.metrics[graded.primary_metric] if graded else None,
                  'primary_metric': graded.primary_metric if graded else None, 'judge': ctx.config.judge_label,
                  'status': 'failed' if error else 'succeeded', 'error': error,
                  'harness_before': state['before'], 'harness_after': harness.head,
                  'output': session.output, 'self_check': report}
        grade_ctx.save('task_result.json', result)
        state['phase'] = 'complete'
        ctx.save('task_state.json', state)
        return result
    finally:
        session.close_worker()
        session.refiner.close()


def research(root, config, question, columns, keys, language):
    if not isinstance(question, str) or not question.strip():
        raise ValueError('A nonempty research question is required')
    validate_research_spec(columns, keys, language)
    root = Path(root).resolve()
    verify_isolation()
    harness = Harness(root / 'harness')
    task = Task(task_id=digest({'question': question, 'columns': columns, 'keys': keys, 'language': language})[:24],
                benchmark='research', question=question, spec={'columns': columns, 'keys': keys}, language=language)
    run_id = 'research-' + uuid4().hex
    ctx = RunContext(root, run_id, config, task.task_id)
    with workspace(harness):
        result = _task(task, ResearchData(), ctx, harness, True, grade=False)
    return {'run_id': run_id, **result}


def _base(harness, tasks, base=None):
    keys = {task.benchmark + ':' + task.task_id for task in tasks}
    if base is not None:
        if not re.fullmatch(r'[a-fA-F0-9]{7,40}', base):
            raise ValueError('--base must be a commit SHA from the harness repository')
        sha = harness.git('rev-parse', '--verify', base + '^{commit}')
        seen = json.loads(harness.git('show', sha + ':harness_state.json'))['seen']
        if keys.intersection(seen):
            raise ValueError('--base already contains research for a selected task')
        return sha
    seen = harness.snapshot()['seen']
    ancestors = [seen[key]['before'] for key in keys.intersection(seen)]
    return min(ancestors, key=lambda sha: int(harness.git('rev-list', '--count', sha))) if ancestors else harness.head


def stream(root, config, benchmark, no_learning=False, base=None, resume=None):
    from .report import build_report
    if no_learning and base is None and resume is None:
        raise ValueError('--no-learning requires --base from the learning stream manifest')
    root = Path(root).resolve()
    adapter = load_benchmark(benchmark, root, config)
    tasks = sorted(adapter.load_tasks(), key=lambda task: task.task_id)
    random.Random(config.wandr.seed if benchmark == 'wandr' else config.data.seed).shuffle(tasks)
    if benchmark == 'wandr' and config.wandr.final_n_tasks is not None:
        if config.wandr.final_n_tasks > len(tasks):
            raise ValueError('wandr.final_n_tasks exceeds available tasks')
        tasks = tasks[:config.wandr.final_n_tasks]
    if not tasks or len({t.task_id for t in tasks}) != len(tasks):
        raise ValueError('Stream requires unique nonempty tasks')
    run_id = resume or 'stream-' + benchmark + '-' + uuid4().hex
    RunContext(root, run_id, config)
    report_path = root / 'reports' / run_id / 'stream.json'
    task_digest = digest([task.model_dump(mode='json') for task in tasks])
    verify_isolation()
    harness = Harness(root / 'harness')
    with workspace(harness):
        if resume:
            manifest = read_json(report_path)
            if manifest is None:
                raise ValueError('No stream manifest for --resume ' + resume)
            if (manifest['benchmark'] != benchmark or manifest['config'] != config.model_dump() or
                    manifest['task_digest'] != task_digest):
                raise ValueError('Resume requires identical benchmark, configuration and ordered tasks')
            if (base is not None and _base(harness, tasks, base) != manifest['base_sha'] or
                    no_learning and manifest['learning']):
                raise ValueError('Resume cannot change the starting commit or learning mode')
            if [row['task_id'] for row in manifest['tasks']] != manifest['task_ids'][:len(manifest['tasks'])]:
                raise ValueError('Stream completion checkpoint is not an ordered prefix')
            if (manifest['status'] in {'interrupted', 'complete'} and
                    harness.git('rev-parse', manifest['lineage']) != manifest['harness_head']):
                raise ValueError('Resume lineage changed outside the interrupted stream')
            harness.git('checkout', '-q', manifest['lineage'])
        else:
            previous_branch = harness.branch
            base = _base(harness, tasks, base)
            harness.fork(base)
            manifest = {'run_id': run_id, 'created_at': stamp(), 'benchmark': benchmark, 'learning': not no_learning,
                        'base_sha': base, 'lineage': harness.branch, 'return_branch': previous_branch,
                        'task_ids': [t.task_id for t in tasks], 'task_digest': task_digest,
                        'as_of_date': date.today().isoformat() if config.agent.as_of == 'today' else config.agent.as_of,
                        'config': config.model_dump(), 'judge': config.judge_label, 'tasks': []}
        manifest.update(status='running', error=None, harness_head=harness.head)
        write_json(report_path, manifest)
        ctx = None
        try:
            for index, task in enumerate(tasks[len(manifest['tasks']):], len(manifest['tasks']) + 1):
                manifest.update(active_task_id=task.task_id, phase='research')
                write_json(report_path, manifest)
                ctx = RunContext(root, run_id, config, task.task_id)
                if ctx.load('as_of.json') is None:
                    task_date = task.as_of_date.isoformat() if task.as_of_date else None
                    ctx.save('as_of.json', {'policy': config.agent.as_of, 'task_date': task_date,
                             'as_of_date': task_date or manifest['as_of_date'],
                             'date_source': 'task' if task_date else 'today' if config.agent.as_of == 'today' else 'config'})
                result = _task(task, adapter, ctx, harness, manifest['learning'], grade=True)
                manifest['tasks'].append({'index': index, **{k: v for k, v in result.items()
                                                           if k not in {'output', 'self_check'}}})
                manifest['harness_head'] = harness.head
                write_json(report_path, manifest)
            manifest.update(status='complete', active_task_id=None, phase=None)
            write_json(report_path, manifest)
        except BaseException as exc:
            state = ctx.load('task_state.json', {}) if ctx else {}
            manifest.update(status='interrupted', error=_error(exc), phase=state.get('phase', 'research'),
                            harness_head=harness.head)
            write_json(report_path, manifest)
            message = (f'Stream {run_id} stopped during {manifest["phase"]}: {_error(exc)}. '
                       f'Resume with loop-research stream --benchmark {benchmark} --resume {run_id}')
            try:
                build_report(root)
            except Exception as report_error:
                message += '; report generation failed: ' + _error(report_error)
            raise RuntimeError(message) from exc
        finally:
            if not manifest['learning']:
                harness.git('checkout', '-q', manifest['return_branch'])
        build_report(root)
    return manifest
