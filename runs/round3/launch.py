#!/usr/bin/env python3
"""Explicit Round 3 phases. Preparation never starts research; no retries or rollbacks."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = '2a423027212fe1c430dfd200bdd55f3a27b22d70'
sys.path.insert(0, str(HERE.parent / 'round2'))
from replay_saved_refine import file_record, git, save, stamp, verify_installed_source
from launch_replay import announced_archive


def load(path):
    return json.loads(Path(path).read_text())


def check_record(record):
    if file_record(Path(record['path'])) != record:
        raise ValueError('Recorded file changed: ' + record['path'])


def receipt_gate(preflight, rollback, source):
    if preflight.get('source_commit') != source or preflight.get('all_fixes_complete') is not True:
        raise ValueError('Preflight must certify all fixes on the exact source commit')
    suite = preflight.get('full_suite', {})
    if suite.get('exit_code') != 0 or type(suite.get('passed')) is not int or suite['passed'] < 1:
        raise ValueError('Preflight requires a passing full suite')
    for key in ('saved_refine', 'archive_audit'):
        if preflight.get(key, {}).get('status') != 'passed':
            raise ValueError('Preflight check incomplete: ' + key)
    for key in ('full_suite', 'saved_refine', 'archive_audit'):
        check_record(preflight[key]['evidence'])
    if (rollback.get('source_commit') != source or rollback.get('base_sha') != BASE
            or rollback.get('harness_head') != BASE or not rollback.get('completed_at')):
        raise ValueError('Parent rollback receipt must identify the exact BASE and source')
    datetime.fromisoformat(rollback['completed_at'])


def unchanged(plan):
    root = Path(plan['main_root'])
    verification = plan['source_verification']
    for record in plan['frozen_files']:
        check_record(record)
    directory = Path(plan['directory'])
    receipt_gate(load(directory / 'preflight.json'), load(directory / 'rollback.json'), plan['source_commit'])
    for record in verification['modules']:
        expected = record['sha256']
        if (file_record(root / record['source'])['sha256'] != expected
                or file_record(Path(record['installed']))['sha256'] != expected):
            raise ValueError('Research source/installed module changed: ' + record['source'])
    expected = {str(Path(r['source']).relative_to('src/loop_research')) for r in verification['modules']}
    for directory in (root / 'src/loop_research', Path(verification['package_root'])):
        actual = {str(path.relative_to(directory)) for path in directory.rglob('*.py')}
        if actual != expected:
            raise ValueError('Research Python module set changed')
    # A later predictions/documentation commit is allowed; executable sources are frozen.
    subprocess.run(['git', '-C', str(root), 'merge-base', '--is-ancestor', plan['source_commit'], 'HEAD'],
                   check=True, capture_output=True)


def clone_harness(source, workspace, base):
    source, workspace = Path(source).resolve(), Path(workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=False)
    clone = workspace / 'harness'
    commands = [
        ['git', 'clone', '--no-hardlinks', '--no-local', '--no-checkout', str(source), str(clone)],
        ['git', '-C', str(clone), 'checkout', '-q', '-b', 'round3-start', base],
        ['git', '-C', str(clone), 'config', 'user.name', 'Round 3 research'],
        ['git', '-C', str(clone), 'config', 'user.email', 'round3@localhost'],
    ]
    for command in commands:
        subprocess.run(command, check=True, capture_output=True, text=True)
    if ((clone / '.git/objects/info/alternates').exists() or (clone / '.git/shallow').exists()
            or git(clone, 'rev-parse', 'HEAD').strip() != base):
        raise ValueError('Harness clone is not independent, full, and at the exact base')
    for name in ('runs', 'reports', 'cache'):
        (workspace / name).mkdir()
    return {'commands': commands, 'source_harness': str(source), 'workspace': str(workspace),
            'base_sha': base, 'state': file_record(clone / 'harness_state.json'),
            'full_clone': True, 'alternates': False, 'hardlinks': False,
            'cache_note': 'Each task also owns tool_cache.json beneath this workspace/runs.'}


def eligible_base(harness, task, base):
    """Check the public CLI's replay boundary before creating or launching an arm."""
    commit = git(harness, 'rev-parse', '--verify', base + '^{commit}').strip()
    state = json.loads(git(harness, 'show', commit + ':harness_state.json'))
    if task['benchmark'] + ':' + task['task_id'] in state['seen']:
        raise ValueError('Selected baseline already contains research for task ' + task['task_id'])
    return commit


def command_for(plan, label, workspace, base):
    task = load(plan['tasks']['B' if label.startswith('B') else label])
    command = [plan['public_cli'], '--root', str(workspace), '--config', plan['config_file'],
               'research', task['question']]
    for column in task['spec']['columns']:
        command += ['--columns', column]
    for key in task['spec']['keys']:
        command += ['--keys', key]
    command += ['--language', task['language'], '--trace', '--base', base]
    if label.startswith('B0-') or label.startswith('B1-frozen-'):
        command.append('--no-learning')
    return command


def prepare(directory, source):
    directory = Path(directory).resolve()
    if Path(sys.prefix).resolve() != (ROOT / '.venv').resolve():
        raise ValueError('Run this helper with the main .venv/bin/python to verify the executed package')
    if (directory / 'plan.json').exists() or (directory / 'execution.json').exists():
        raise ValueError('This cohort already has a plan; never overwrite or retry it')
    source = git(ROOT, 'rev-parse', source + '^{commit}').strip()
    preflight_path, rollback_path = directory / 'preflight.json', directory / 'rollback.json'
    receipt_gate(load(preflight_path), load(rollback_path), source)
    if (git(ROOT / 'harness', 'rev-parse', 'HEAD').strip() != BASE
            or git(ROOT / 'harness', 'status', '--porcelain').strip()):
        raise ValueError('Parent must first leave the shared harness clean at BASE')
    verification = verify_installed_source(ROOT, source)
    if Path(verification['package_root']).is_relative_to(ROOT / 'src'):
        raise ValueError('Use the verified noneditable installed package')
    config_path = directory / 'inputs/config.json'
    config = load(config_path)
    original_manifest = load(ROOT / 'runs/round2/manifest.json')
    original = original_manifest['config']
    if config != original or config['agent']['as_of'] != '2026-10-18':
        raise ValueError('Round 3 configuration must equal the complete Round 2 configuration')
    if any(config['models'][role] != 'gpt-6-astra' for role in ('root', 'sub', 'refine', 'judge')):
        raise ValueError('All model roles must remain gpt-6-astra')
    if config['codex']['max_concurrent'] != 4:
        raise ValueError('Expected the existing four shared backend slots')
    tasks = {name: str(directory / f'inputs/{name}.task.json') for name in ('A', 'SI', 'B')}
    initial_bases = {}
    for name, path in tasks.items():
        task = load(path)
        if task['benchmark'] != 'research' or task.get('as_of_date') is not None:
            raise ValueError('Task date must come from the unchanged CLI configuration')
        run = ROOT / 'runs' / original_manifest['runs']['B0' if name == 'B' else name]
        record = load(run / 'research.json')
        if task != load(run / record['task_id'] / 'task.json'):
            raise ValueError('Task differs from its authoritative Round 2 request: ' + name)
        if name in ('A', 'SI'):
            initial_bases[name] = eligible_base(ROOT / 'harness', task, record['base_sha'])
    if initial_bases['A'] != BASE:
        raise ValueError('The recorded A baseline differs from requested BASE')
    frozen = [preflight_path, rollback_path, config_path, *map(Path, tasks.values()),
              Path(__file__).resolve(), HERE.parent / 'round2/replay_saved_refine.py',
              HERE.parent / 'round2/launch_replay.py', ROOT / 'pyproject.toml', ROOT / 'config.yaml',
              ROOT / '.venv/bin/loop-research']
    if (ROOT / 'uv.lock').exists():
        frozen.append(ROOT / 'uv.lock')
    for path in (ROOT / 'pyproject.toml', ROOT / 'config.yaml'):
        if path.read_bytes() != git(ROOT, 'show', source + ':' + path.name, binary=True):
            raise ValueError('Uncommitted runtime configuration or dependencies: ' + path.name)
    plan = {'created_at': stamp(), 'source_commit': source, 'source_verification': verification,
            'main_root': str(ROOT), 'directory': str(directory), 'base_sha': BASE,
            'config_file': str(config_path), 'tasks': tasks, 'initial_bases': initial_bases,
            'public_cli': str(ROOT / '.venv/bin/loop-research'),
            'frozen_files': [file_record(path) for path in frozen],
            'arms': ['A', 'SI', 'B1', 'B1-frozen-1', 'B0-1', 'B1-frozen-2', 'B0-2', 'B1-frozen-3', 'B0-3'],
            'prepare_command': [sys.executable, *sys.argv]}
    save(directory / 'plan.json', plan)
    state = {'created_at': stamp(), 'source_commit': source, 'phases': {}, 'arms': {}}
    save(directory / 'execution.json', state)
    try:
        for label in ('A', 'SI'):
            state['arms'][label] = prepare_arm(plan, label, ROOT / 'harness', initial_bases[label])
            save(directory / 'execution.json', state)
    except BaseException as exc:
        state['preparation_error'] = f'{type(exc).__name__}: {exc}'
        save(directory / 'execution.json', state)
        raise
    return plan


def prepare_arm(plan, label, source_harness, base):
    unchanged(plan)
    directory = Path(plan['directory'])
    workspace = directory / 'workspaces' / label
    task_path = plan['tasks']['B' if label.startswith('B') else label]
    eligible_base(source_harness, load(task_path), base)
    proof = clone_harness(source_harness, workspace, base)
    return {'status': 'prepared', 'workspace': str(workspace), 'isolation': proof,
            'task_id': load(task_path)['task_id'], 'task_file': task_path, 'base_sha': base,
            'learning': not (label.startswith('B0-') or label.startswith('B1-frozen-')),
            'command': command_for(plan, label, workspace, base),
            'console': str(directory / (label + '.console.log')), 'source_commit': plan['source_commit']}


def prediction_gate(plan, state, path, commit):
    a = state.get('arms', {}).get('A', {})
    if a.get('status') != 'complete' or state.get('phases', {}).get('a_si', {}).get('status') != 'complete':
        raise ValueError('B requires the completed A/SI phase and successful A')
    root, path = Path(plan['main_root']).resolve(), Path(path).resolve()
    relative = str(path.relative_to(root))
    commit = git(root, 'rev-parse', commit + '^{commit}').strip()
    subprocess.run(['git', '-C', str(root), 'merge-base', '--is-ancestor', plan['source_commit'], commit],
                   check=True, capture_output=True)
    subprocess.run(['git', '-C', str(root), 'merge-base', '--is-ancestor', commit, 'HEAD'],
                   check=True, capture_output=True)
    content = git(root, 'show', commit + ':' + relative, binary=True)
    if path.read_bytes() != content:
        raise ValueError('Predictions must exactly match their committed contents')
    lines = content.decode().splitlines()
    for binding in ('source_commit: ' + plan['source_commit'], 'POST_A: ' + a['record']['harness_head']):
        if binding not in lines:
            raise ValueError('Missing exact predictions binding: ' + binding)
    commit_time = int(git(root, 'show', '-s', '--format=%ct', commit).strip())
    if commit_time < int(datetime.fromisoformat(a['ended_at']).timestamp()):
        raise ValueError('Predictions commit predates A completion')
    return {'commit': commit, 'file': file_record(path), 'POST_A': a['record']['harness_head'],
            'verified_at': stamp()}


def process_group(records, state_path, *, max_parallel=3, before_spawn=None, after_exit=None):
    """Run owned processes, stopping new starts on failure and letting siblings finish."""
    if not 1 <= max_parallel <= 3:
        raise ValueError('Parallel process limit must be between one and three')
    active, stopped = {}, False
    environment = dict(os.environ)
    environment.pop('PYTHONPATH', None)
    environment.pop('PYTHONHOME', None)
    def persist():
        save(Path(state_path), {'updated_at': stamp(), 'arms': records})
    persist()
    try:
        while active or any(r['status'] == 'prepared' for r in records.values()):
            for label in list(active):
                process, output = active[label]
                code = process.poll()
                if code is None:
                    continue
                output.close()
                record = records[label]
                record.update(exit_code=code, ended_at=stamp(), status='exited' if code == 0 else 'failed')
                try:
                    if after_exit is not None:
                        after_exit(label, record)
                    if code:
                        raise ValueError('CLI exited with code ' + str(code))
                except Exception as exc:
                    record.update(status='failed', error=f'{type(exc).__name__}: {exc}')
                stopped |= record['status'] == 'failed'
                del active[label]
                persist()
            for label, record in records.items():
                if record['status'] != 'prepared':
                    continue
                if stopped:
                    record.update(status='not_launched', error='An earlier arm failed; parent diagnosis required')
                    persist()
                    continue
                if len(active) >= max_parallel:
                    break
                output = None
                try:
                    if before_spawn is not None:
                        before_spawn()
                    output = Path(record['console']).open('x')
                    record['started_at'] = stamp()
                    process = subprocess.Popen(record['command'], stdout=output, stderr=subprocess.STDOUT,
                                               env=environment, start_new_session=True)
                    active[label] = (process, output)
                    record.update(status='running', pid=process.pid)
                    print(json.dumps({'event': 'started', 'label': label, 'pid': process.pid,
                                      'command': record['command'], 'console': record['console']}), flush=True)
                except Exception as exc:
                    if output is not None:
                        output.close()
                    record.update(status='failed', ended_at=stamp(), error=f'{type(exc).__name__}: {exc}')
                    stopped = True
                persist()
            if active:
                time.sleep(.25)
    except BaseException as exc:
        for label, (process, _) in active.items():
            records[label].update(status='coordinator_interrupted',
                                  error=f'{type(exc).__name__}: {exc}', process_left_running=process.pid)
        persist()
        raise
    finally:
        for process, output in active.values():
            output.close()  # No signal is sent to independently running research sessions.


def validate_completion(plan, label, record):
    run, announcement = announced_archive(record['console'], record['workspace'], finished=True)
    archived = load(run / 'research.json')
    record.update(run_id=run.name, run_path=str(run), archive_announcement=announcement, record=archived)
    inventory = [file_record(path) for path in sorted(run.rglob('*')) if path.is_file()]
    inventory_path = Path(plan['directory']) / (label + '.archive_hashes.json')
    save(inventory_path, inventory)
    record['archive_hashes'] = file_record(inventory_path)
    if (record['exit_code'] != 0 or archived.get('status') != 'complete' or archived.get('error')
            or archived.get('run_id') != run.name or archived.get('task_id') != record['task_id']
            or archived.get('base_sha') != record['base_sha'] or archived.get('learning') != record['learning']
            or archived.get('config') != load(plan['config_file'])):
        raise ValueError('CLI exit or durable research identity/status/config is invalid')
    task = run / record['task_id']
    if load(task / 'task.json') != load(record['task_file']):
        raise ValueError('Executed task differs from the frozen request')
    date = load(task / 'as_of.json')
    if date != {'policy': '2026-10-18', 'task_date': None, 'as_of_date': '2026-10-18', 'date_source': 'config'}:
        raise ValueError('Executed date or provenance differs')
    if (task / 'error.json').exists() and load(task / 'error.json'):
        raise ValueError('Research has a durable task error')
    unchanged(plan)
    record.update(status='complete', source_unchanged=True)


@contextmanager
def lock(directory):
    with (Path(directory) / 'launcher.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def run_phase(directory, phase, predictions=None, predictions_commit=None):
    directory = Path(directory).resolve()
    with lock(directory):
        plan, state = load(directory / 'plan.json'), load(directory / 'execution.json')
        unchanged(plan)
        if phase in state['phases'] or state.get('preparation_error'):
            raise ValueError('Phase already started or preparation failed; preserve it for diagnosis')
        if phase == 'a_si':
            labels = ['A', 'SI']
        else:
            if predictions is None or predictions_commit is None:
                raise ValueError('B requires --predictions and --predictions-commit')
            state['predictions'] = prediction_gate(plan, state, predictions, predictions_commit)
            labels = plan['arms'][2:]
            state['phases'][phase] = {'status': 'preparing', 'started_at': stamp(),
                                     'command': [sys.executable, *sys.argv]}
            save(directory / 'execution.json', state)
            # Verify both saved requests/inputs and all bases before starting any B process.
            try:
                for label in labels:
                    source_harness = Path(state['arms']['A']['workspace']) / 'harness'
                    base = state['predictions']['POST_A']
                    if label.startswith('B0-'):
                        source_harness, base = Path(plan['main_root']) / 'harness', BASE
                    state['arms'][label] = prepare_arm(plan, label, source_harness, base)
                    save(directory / 'execution.json', state)
            except BaseException as exc:
                state['phases'][phase].update(status='preparation_failed', ended_at=stamp(),
                                             error=f'{type(exc).__name__}: {exc}')
                save(directory / 'execution.json', state)
                raise
        state['phases'][phase] = {'status': 'running', 'started_at': stamp(),
                                 'command': [sys.executable, *sys.argv]}
        save(directory / 'execution.json', state)
        records = {label: state['arms'][label] for label in labels}
        try:
            process_group(records, directory / (phase + '.processes.json'), max_parallel=2 if phase == 'a_si' else 3,
                          before_spawn=lambda: unchanged(plan),
                          after_exit=lambda label, record: validate_completion(plan, label, record))
            state['phases'][phase]['status'] = 'complete' if all(r['status'] == 'complete' for r in records.values()) else 'failed'
            if state['arms'].get('A', {}).get('status') == 'complete':
                state['POST_A'] = state['arms']['A']['record']['harness_head']
        except BaseException as exc:
            state['phases'][phase].update(status='interrupted', error=f'{type(exc).__name__}: {exc}')
            raise
        finally:
            state['phases'][phase]['ended_at'] = stamp()
            save(directory / 'execution.json', state)
        return 0 if state['phases'][phase]['status'] == 'complete' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=HERE)
    sub = parser.add_subparsers(dest='operation', required=True)
    prep = sub.add_parser('prepare', help='Verify receipts and clone A/SI; never starts research')
    prep.add_argument('--source', required=True)
    run = sub.add_parser('run', help='Explicitly execute a single gated phase')
    run.add_argument('--phase', choices=['a_si', 'b'], required=True)
    run.add_argument('--predictions', type=Path)
    run.add_argument('--predictions-commit')
    sub.add_parser('status', help='Read saved phase/process status only')
    args = parser.parse_args()
    def event(**details):
        with (args.directory / 'launcher_events.jsonl').open('a') as output:
            output.write(json.dumps({'timestamp': stamp(), 'command': [sys.executable, *sys.argv],
                                     'operation': args.operation, **details}) + '\n')
    try:
        event(status='requested')
        if args.operation == 'prepare':
            with lock(args.directory):
                print(json.dumps(prepare(args.directory, args.source), indent=2))
            return 0
        if args.operation == 'status':
            result = {}
            for name in ('execution.json', 'a_si.processes.json', 'b.processes.json'):
                if (args.directory / name).exists():
                    result[name] = load(args.directory / name)
            print(json.dumps(result or {'status': 'not_prepared'}, indent=2))
            return 0
        return run_phase(args.directory, args.phase, args.predictions, args.predictions_commit)
    except Exception as exc:
        details = {'status': 'refused_or_failed', 'error': f'{type(exc).__name__}: {exc}'}
        if args.directory.is_dir():
            event(**details)
        print(json.dumps(details), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
