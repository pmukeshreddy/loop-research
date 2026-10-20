#!/usr/bin/env python3
"""Separately gated explicit diagnostic; excluded from every Round 3 comparison."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('round3_explicit_launch_helpers', HERE / 'launch.py')
launch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launch)
CLASSIFICATION = 'explicit mechanism diagnostic; excluded from spontaneous behavior and all A/B comparisons'


def explicit_gate(plan, state):
    if state.get('source_commit') != plan['source_commit']:
        raise ValueError('Main cohort source identity differs')
    if state.get('phases', {}).get('b', {}).get('status') != 'complete':
        raise ValueError('The main B phase must complete first')
    if state.get('phases', {}).get('a_si', {}).get('status') != 'complete':
        raise ValueError('The main A/SI phase must complete first')
    if not plan['arms']:
        raise ValueError('The main cohort has no planned arms')
    for label in plan['arms']:
        arm = state.get('arms', {}).get(label, {})
        durable = arm.get('record', {})
        if (arm.get('status') != 'complete' or arm.get('exit_code') != 0
                or arm.get('source_commit') != plan['source_commit']
                or durable.get('status') != 'complete' or durable.get('error')):
            raise ValueError('Every main arm must have completed successfully: ' + label)


def task_for(request):
    # Same task identity/model as stream.research; this constructs data, never starts research.
    from loop_research.archive import digest
    from loop_research.benchmarks import Task
    from loop_research.research import validate_research_spec
    validate_research_spec(request['columns'], request['keys'], request['language'])
    identity = {key: request[key] for key in ('question', 'columns', 'keys', 'language')}
    if not isinstance(identity['question'], str) or not identity['question'].strip():
        raise ValueError('A nonempty explicit question is required')
    return Task(task_id=digest(identity)[:24], benchmark='research', question=request['question'],
                spec={'columns': request['columns'], 'keys': request['keys']},
                language=request['language']).model_dump(mode='json')


def checked_plan(directory):
    """Read-only: validate the completed main cohort and freeze this independent request."""
    directory = Path(directory).resolve()
    plan = launch.load(directory / 'plan.json')
    state = launch.load(directory / 'execution.json')
    explicit_gate(plan, state)
    if Path(sys.prefix).resolve() != (Path(plan['main_root']) / '.venv').resolve():
        raise ValueError('Use the main .venv/bin/python for the explicit diagnostic')
    launch.unchanged(plan)
    request_path, task_path = directory / 'explicit_request.json', directory / 'explicit_task.json'
    request = launch.load(request_path)
    if (request.get('classification') != CLASSIFICATION or request.get('label') != 'explicit'
            or request.get('base') != launch.BASE):
        raise ValueError('Explicit request must be classified separately and start from BASE')
    if launch.load(task_path) != task_for(request):
        raise ValueError('Explicit task differs from the normal CLI request identity')
    paths = [Path(__file__).resolve(), request_path, task_path,
             directory / 'plan.json', directory / 'execution.json', directory / 'b.processes.json']
    return {**plan, 'tasks': {**plan['tasks'], 'explicit': str(task_path)},
            'frozen_files': [*plan['frozen_files'], *(launch.file_record(path) for path in paths)]}


def execute(directory):
    directory = Path(directory).resolve()
    with launch.lock(directory):
        target = directory / 'explicit_execution.json'
        if target.exists():
            raise ValueError('Explicit diagnostic already attempted; preserve its result for parent review')
        state = {'status': 'checking', 'classification': CLASSIFICATION, 'created_at': launch.stamp(),
                 'command': [sys.executable, *sys.argv], 'arms': {}}
        launch.save(target, state)
        try:
            plan = checked_plan(directory)
            state.update(source_commit=plan['source_commit'], status='preparing',
                         frozen_files=plan['frozen_files'], base_sha=launch.BASE)
            launch.save(target, state)
            workspace = directory / 'workspaces' / 'explicit-BASE'
            isolation = launch.clone_harness(Path(plan['main_root']) / 'harness', workspace, launch.BASE)
            task_path = plan['tasks']['explicit']
            record = {'status': 'prepared', 'classification': CLASSIFICATION, 'learning': True,
                      'workspace': str(workspace), 'isolation': isolation, 'base_sha': launch.BASE,
                      'task_id': launch.load(task_path)['task_id'], 'task_file': task_path,
                      'source_commit': plan['source_commit'],
                      'command': launch.command_for(plan, 'explicit', workspace, launch.BASE),
                      'console': str(directory / 'explicit.console.log')}
            state.update(status='running', arms={'explicit': record})
            launch.save(target, state)
            launch.process_group(state['arms'], directory / 'explicit.processes.json', max_parallel=1,
                                 before_spawn=lambda: launch.unchanged(plan),
                                 after_exit=lambda label, row: launch.validate_completion(plan, label, row))
            state['status'] = 'complete' if record['status'] == 'complete' else 'failed'
        except BaseException as exc:
            state.update(status='failed' if isinstance(exc, Exception) else 'interrupted',
                         error=f'{type(exc).__name__}: {exc}')
            raise
        finally:
            state['ended_at'] = launch.stamp()
            launch.save(target, state)
        return 0 if state['status'] == 'complete' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=HERE)
    parser.add_argument('operation', choices=['check', 'run', 'status'],
                        help='check/status only read files; run explicitly starts the diagnostic')
    args = parser.parse_args()
    try:
        if args.operation == 'check':
            with launch.lock(args.directory):
                plan = checked_plan(args.directory)
            print(json.dumps({'status': 'ready', 'classification': CLASSIFICATION,
                              'source_commit': plan['source_commit'], 'base_sha': launch.BASE,
                              'task': launch.load(plan['tasks']['explicit'])}, indent=2))
            return 0
        if args.operation == 'status':
            result = {name: launch.load(args.directory / name)
                      for name in ('explicit_execution.json', 'explicit.processes.json')
                      if (args.directory / name).exists()}
            print(json.dumps(result or {'status': 'not_started', 'classification': CLASSIFICATION}, indent=2))
            return 0
        return execute(args.directory)
    except Exception as exc:
        print(json.dumps({'status': 'refused_or_failed', 'classification': CLASSIFICATION,
                          'error': f'{type(exc).__name__}: {exc}'}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
