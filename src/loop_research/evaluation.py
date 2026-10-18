"""Shared task selection and official failure grading, independent of the harness."""
import math
import random

from .archive import RunContext
from .benchmarks import GradeResult


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


def select_tasks(adapter, config, benchmark):
    tasks = sorted(adapter.load_tasks(), key=lambda task: task.task_id)
    random.Random(config.wandr.seed if benchmark == 'wandr' else config.data.seed).shuffle(tasks)
    if benchmark == 'wandr' and config.wandr.final_n_tasks is not None:
        if config.wandr.final_n_tasks > len(tasks):
            raise ValueError('wandr.final_n_tasks exceeds available tasks')
        tasks = tasks[:config.wandr.final_n_tasks]
    if not tasks or len({t.task_id for t in tasks}) != len(tasks):
        raise ValueError('Stream requires unique nonempty tasks')
    return tasks
