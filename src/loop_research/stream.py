"""Sequential research/grade/check/refine orchestration with lineage-safe replay."""
from contextlib import contextmanager
import fcntl
from pathlib import Path
import random
from uuid import uuid4

from .agent import run_task
from .archive import RunContext, GradeContext, digest, read_json, stamp, write_json
from .benchmarks import Task
from .benchmarks.widesearch.data import WideSearchData
from .harness import Harness
from .isolation import verify_isolation
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


def _task(task, benchmark, ctx, harness, learning, *, grade):
    before = harness.begin_task(task.benchmark + ':' + task.task_id, ctx.run_id + '/' + task.task_id)
    ctx.initialize(before, kind='research', benchmark=task.benchmark)
    session = Session(task, ctx, harness, learning=learning)
    error, result, graded, report = None, None, None, None
    try:
        result = run_task(task, benchmark, session)
    except Exception as exc:
        error = f'{type(exc).__name__}: {exc}'
        session.status['timeout' if isinstance(exc, TimeoutError) else 'worker_error'] = True
        ctx.save('error.json', {'error': error})
    else:
        if grade:
            grade_ctx = GradeContext(ctx.root, ctx.run_id, ctx.config, task.task_id)
            try:
                graded = benchmark.grade(task, ctx.load('submission.json'), grade_ctx)
                grade_ctx.save('grade.json', graded.model_dump())
            except Exception as exc:
                error = f'{type(exc).__name__}: {exc}'
                grade_ctx.save('error.json', {'error': error})
    finally:
        try:
            report = session.finish()
        except Exception as exc:
            session.refiner.close()
            refine_error = f'{type(exc).__name__}: {exc}'
            ctx.save('refine_error.json', {'error': refine_error})
            error = (error + '; ' if error else '') + 'refine: ' + refine_error
            report = session.self_check()
    return {'task_id': task.task_id, 'score': graded.metrics[graded.primary_metric] if graded else None,
            'primary_metric': graded.primary_metric if graded else None, 'judge': ctx.config.judge_label,
            'error': error, 'harness_before': before, 'harness_after': harness.head,
            'output': result.output if result else session.output, 'self_check': report}


def research(root, config, question, columns):
    if not isinstance(question, str) or not question.strip():
        raise ValueError('A nonempty research question is required')
    columns = columns or ['entity', 'answer']
    if len(columns) != len(set(columns)) or not all(isinstance(c, str) and c.strip() for c in columns):
        raise ValueError('Columns must be unique nonempty names')
    root = Path(root).resolve()
    verify_isolation()
    harness = Harness(root / 'harness')
    task = Task(task_id=digest({'question': question, 'columns': columns})[:24], benchmark='research',
                question=question, spec={'columns': columns, 'keys': [columns[0]]}, language='en')
    run_id = 'research-' + uuid4().hex
    ctx = RunContext(root, run_id, config, task.task_id)
    with workspace(harness):
        result = _task(task, WideSearchData(root, config), ctx, harness, True, grade=False)
    return {'run_id': run_id, **result}


def _base(harness, tasks, root, config, benchmark):
    task_ids = [task.task_id for task in tasks]
    files = sorted((root / 'reports').glob('*/stream.json'), key=lambda p: p.stat().st_mtime, reverse=True)
    for file in files:
        prior = read_json(file)
        if prior['benchmark'] == benchmark and prior['task_ids'] == task_ids and prior['config'] == config.model_dump():
            return prior['base_sha']
    seen = harness.snapshot()['seen']
    ancestors = [seen[key]['before'] for task in tasks if (key := task.benchmark + ':' + task.task_id) in seen]
    return min(ancestors, key=lambda sha: int(harness.git('rev-list', '--count', sha))) if ancestors else harness.head


def stream(root, config, benchmark, no_learning=False):
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
    verify_isolation()
    harness = Harness(root / 'harness')
    run_id = 'stream-' + benchmark + '-' + uuid4().hex
    with workspace(harness):
        previous_branch = harness.branch
        base = _base(harness, tasks, root, config, benchmark)
        if no_learning or base != harness.head:
            harness.fork(base)
        manifest = {'run_id': run_id, 'created_at': stamp(), 'benchmark': benchmark, 'learning': not no_learning,
                    'base_sha': base, 'lineage': harness.branch, 'task_ids': [t.task_id for t in tasks],
                    'config': config.model_dump(), 'judge': config.judge_label, 'tasks': []}
        report_path = root / 'reports' / run_id / 'stream.json'
        write_json(report_path, manifest)
        try:
            for index, task in enumerate(tasks, 1):
                ctx = RunContext(root, run_id, config, task.task_id)
                result = _task(task, adapter, ctx, harness, not no_learning, grade=True)
                manifest['tasks'].append({'index': index, **{k: v for k, v in result.items() if k not in {'output', 'self_check'}}})
                write_json(report_path, manifest)
        finally:
            if no_learning:
                harness.git('checkout', '-q', previous_branch)
    from .report import build_report
    build_report(root)
    return manifest
