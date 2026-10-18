"""Plain Codex WANDR baseline: no harness state, retrieval, or learning."""
from datetime import date
import fcntl
import json
from pathlib import Path
import subprocess
from uuid import uuid4

from .archive import GradeContext, RunContext, count_codex_calls, digest, read_json, stamp, write_json
from .benchmarks.wandr.grader import WandrBenchmark
from .codex_backend import CallBudget, CodexBackend
from .evaluation import _error, _grade, select_tasks


def harness_head(root):
    """Inspect Git identity only; never load or initialize the harness."""
    return subprocess.check_output(['git', '--git-dir', str(root / 'harness/.git'),
                                    'rev-parse', '--verify', 'HEAD'], text=True).strip()


def _task(task, adapter, ctx, manifest):
    grade_ctx = GradeContext(ctx.root, ctx.run_id, ctx.config, task.task_id)
    completed = grade_ctx.load('task_result.json')
    if completed is not None:
        return completed
    contract = adapter.output_contract(task)
    ctx.initialize(manifest['harness_before'], kind='baseline', benchmark=task.benchmark)
    as_of = task.as_of_date.isoformat() if task.as_of_date else manifest['as_of_date']
    prompt = json.dumps({'question': task.question, 'spec': task.spec, 'as_of_date': as_of,
                         'output_contract': contract.prompt}, ensure_ascii=False)
    (ctx.path / 'prompt.txt').write_text(prompt)
    ctx.save('output_schema.json', contract.schema)
    state = ctx.load('task_state.json')
    if state is None:
        output, error = contract.empty, None
        try:
            saved = ctx.load('baseline_response.json')
            if saved is None:
                if count_codex_calls(ctx.path):
                    raise RuntimeError('Research interrupted before completion')
                raw = CodexBackend(ctx, budget=CallBudget(1, ctx.config.agent.task_timeout_s)).complete(
                    prompt, purpose='baseline', web=True, schema=contract.schema)
            else:
                if saved['error']:
                    raise RuntimeError(saved['error'])
                raw = saved['response']
            output = contract.model.model_validate_json(raw).model_dump(by_alias=True)
        except Exception as exc:
            error = _error(exc)
            ctx.save('error.json', {'error': error})
        ctx.save('output.json', output)
        ctx.save('submission.json', adapter.to_submission(task, output))
        state = {'phase': 'grade', 'error': error}
        ctx.save('task_state.json', state)
    graded, errors = _grade(task, adapter, grade_ctx, bool(state['error']))
    error = '; '.join(filter(None, [state['error'], *errors])) or None
    result = {'task_id': task.task_id, 'score': graded.metrics[graded.primary_metric],
              'primary_metric': graded.primary_metric, 'judge': ctx.config.judge_label,
              'status': 'failed' if error else 'succeeded', 'error': error,
              'harness_before': manifest['harness_before'], 'harness_after': manifest['harness_before']}
    grade_ctx.save('task_result.json', result)
    ctx.save('task_state.json', {**state, 'phase': 'complete'})
    return result


def baseline(root, config, benchmark, resume=False):
    from .report import build_report
    if benchmark != 'wandr':
        raise ValueError('Plain baseline supports only WANDR')
    root = Path(root).resolve()
    reports = root / 'reports'
    reports.mkdir(parents=True, exist_ok=True)
    # This lock is outside the harness, so even coordination cannot mutate it.
    with (reports / '.baseline-wandr.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('Another WANDR baseline is running') from exc
        manifest = None
        if resume:
            candidates = [read_json(path) for path in reports.glob('*/baseline.json')]
            if not candidates:
                raise ValueError('No baseline manifest for --resume')
            manifest = max(candidates, key=lambda row: row['created_at'])
        adapter = WandrBenchmark(root, config)
        tasks = select_tasks(adapter, config, benchmark)
        task_digest = digest([task.model_dump(mode='json') for task in tasks])
        before = harness_head(root)
        if manifest is not None:
            if (manifest['benchmark'] != benchmark or manifest['config'] != config.model_dump() or
                    manifest['task_digest'] != task_digest or manifest['harness_before'] != before):
                raise ValueError('Resume requires identical configuration, ordered tasks and harness HEAD')
            if [row['task_id'] for row in manifest['tasks']] != manifest['task_ids'][:len(manifest['tasks'])]:
                raise ValueError('Baseline completion checkpoint is not an ordered prefix')
        else:
            manifest = {'run_id': 'baseline-wandr-' + uuid4().hex, 'created_at': stamp(),
                        'mode': 'baseline', 'benchmark': benchmark, 'learning': None,
                        'base_sha': before, 'harness_before': before,
                        'task_ids': [task.task_id for task in tasks], 'task_digest': task_digest,
                        'as_of_date': date.today().isoformat() if config.agent.as_of == 'today' else config.agent.as_of,
                        'config': config.model_dump(), 'judge': config.judge_label, 'tasks': []}
        run_id = manifest['run_id']
        path = reports / run_id / 'baseline.json'
        manifest.update(status='running', error=None)
        write_json(path, manifest)
        print(f'Archive: {run_id}; planned tasks: {len(tasks)}', flush=True)
        try:
            for index, task in enumerate(tasks[len(manifest['tasks']):], len(manifest['tasks']) + 1):
                manifest.update(active_task_id=task.task_id, phase='research')
                write_json(path, manifest)
                print(f'[{index}/{len(tasks)}] {task.task_id}: started', flush=True)
                ctx = RunContext(root, run_id, config, task.task_id)
                result = _task(task, adapter, ctx, manifest)
                manifest['tasks'].append({'index': index, **result})
                write_json(path, manifest)
                print(f'[{index}/{len(tasks)}] {task.task_id}: {result["status"]}; '
                      f'{result["primary_metric"]}={result["score"]}', flush=True)
                if result['error']:
                    raise RuntimeError('Task failed: ' + result['error'])
            manifest.update(status='complete', active_task_id=None, phase=None)
        except BaseException as exc:
            manifest.update(status='interrupted', error=_error(exc))
            raise RuntimeError(f'Baseline {run_id} stopped: {_error(exc)}. '
                               'Resume with loop-research baseline --benchmark wandr --resume') from exc
        finally:
            after = harness_head(root)
            manifest['harness_after'] = after
            if before != after:
                manifest.update(status='interrupted', error='Harness HEAD changed during baseline')
            write_json(path, manifest)
            build_report(root)
            if before != after:
                raise RuntimeError(manifest['error'])
        return manifest
