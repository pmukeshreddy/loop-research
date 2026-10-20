#!/usr/bin/env python3
"""Read-only six-control archive audit. No product imports, network, or model calls."""
from __future__ import annotations

import argparse
import ast
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

CONTROLS = tuple(f'{group}-{i}' for group in ('B0', 'B1-frozen') for i in range(1, 4))
INITIAL = '\nRELEVANT HARNESS\n'
CURRENT = '\nCURRENT RELEVANT HARNESS ENTRIES\n'
LIMITATIONS = ('Three repeats per base are descriptive checks, not statistical evidence of an effect. '
    'The intervention is complete retrieved harness entries, including their historical metadata, '
    'not only lesson bodies. Later model-generated prompts and web responses may diverge. '
    'These runs use the new direct readable fetch path; they are not interchangeable with old '
    'model-rendered fetch runs. This comparison does not replace the full fetch-receipt/content audit. '
    'Dispatch hashes and trace records verify reconstructed input; they are local execution evidence, '
    'not a server-side attestation.')


class AuditError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise AuditError(message)


def read(path):
    return json.loads(Path(path).read_text())


def read_lines(path):
    return [(n, json.loads(line)) for n, line in enumerate(Path(path).read_text().splitlines(), 1) if line.strip()]


def digest(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def bytes_record(data):
    return {'bytes': len(data), 'sha256': digest(data)}


def file_record(path):
    path = Path(path).resolve()
    return {'path': str(path), **bytes_record(path.read_bytes())}


def verify_file(record, description='file'):
    require(file_record(record['path']) == record, description + ' hash/size/path changed: ' + record['path'])


def git(directory, *args):
    result = subprocess.run(['git', '-C', str(directory), *args], capture_output=True)
    require(result.returncode == 0, 'Read-only Git check failed: ' + ' '.join(args) + ': ' + result.stderr.decode())
    return result.stdout


def literal(source, name):
    values = [ast.literal_eval(node.value) for node in ast.parse(source).body
              if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets)]
    require(len(values) == 1 and isinstance(values[0], str), 'Frozen source must define one literal ' + name)
    return values[0]


def verify_source(plan):
    root, sha = Path(plan['main_root']).resolve(), plan['source_commit']
    proof = plan['source_verification']
    require(proof['commit'] == sha, 'Source verification commit mismatch')
    committed = {x for x in git(root, 'ls-tree', '-r', '--name-only', sha, '--', 'src/loop_research').decode().splitlines()
                 if x.endswith('.py')}
    records = proof['modules']
    require(len({r['source'] for r in records}) == len(records) and {r['source'] for r in records} == committed,
            'Source module inventory differs from frozen commit')
    package = Path(proof['package_root']).resolve()
    require(not package.is_relative_to(root / 'src'), 'Installed package must be noneditable')
    for directory in (root / 'src/loop_research', package):
        require({str(p.relative_to(directory)) for p in directory.rglob('*.py')} ==
                {str(Path(r['source']).relative_to('src/loop_research')) for r in records}, 'Python module set changed')
    verified = []
    for record in records:
        relative = Path(record['source']).relative_to('src/loop_research')
        require(Path(record['installed']).resolve() == package / relative, 'Installed module path mismatch')
        expected = {k: record[k] for k in ('bytes', 'sha256')}
        require(bytes_record(git(root, 'show', sha + ':' + record['source'])) == expected,
                'Committed module differs from source verification: ' + record['source'])
        for path, kind in ((root / record['source'], 'working source'), (package / relative, 'installed module')):
            require(bytes_record(path.read_bytes()) == expected, kind + ' changed: ' + str(path))
        verified.append({**record, 'committed_matches': True, 'working_matches': True, 'installed_matches': True})
    for record in plan['frozen_files']:
        verify_file(record, 'Frozen input')
    git(root, 'merge-base', '--is-ancestor', sha, 'HEAD')
    return {'commit': sha, 'modules': verified, 'frozen_files': plan['frozen_files'], 'status': 'passed'}, {
        'instruction': literal(git(root, 'show', sha + ':src/loop_research/codex_backend.py'), 'INSTRUCTION'),
        'fetch_path': literal(git(root, 'show', sha + ':src/loop_research/page_fetch.py'), 'FETCH_PATH')}


def state_differences(before, after, prefix=''):
    """Complete changed values, including entire arrays: never truncate evidence."""
    if before == after:
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        rows = []
        for key in sorted(before.keys() | after.keys()):
            path = prefix + '/' + key.replace('~', '~0').replace('/', '~1')
            if key not in before or key not in after:
                rows.append({'path': path, 'before_present': key in before, 'after_present': key in after,
                             'before': before.get(key), 'after': after.get(key)})
            else:
                rows.extend(state_differences(before[key], after[key], path))
        return rows
    return [{'path': prefix or '/', 'before': before, 'after': after}]


def verify_entries(entries, base_state, identity):
    require(isinstance(entries, list), 'Harness entries must be a JSON list')
    keys = []
    for entry in entries:
        require(isinstance(entry, dict) and 'kind' in entry and 'id' in entry, 'Malformed harness entry')
        key = entry['kind'] + ':' + entry['id']
        keys.append(key)
        require(key in base_state['entries'] and entry == base_state['entries'][key],
                'Retrieved entry does not equal its complete base entry: ' + key)
        for field in ('usage', 'outcomes'):
            require(all(item.get('run_id') != identity for item in entry.get(field, [])),
                    'Current-run ' + field + ' injected in initial entries: ' + key)
    require(len(keys) == len(set(keys)), 'Duplicate complete entry identity')


def parse_inputs(context, model_prompt, instruction, base_state, identity):
    require(model_prompt.count(context) == 1, 'Saved context must appear exactly once in actual initial root prompt')
    require(context.count(INITIAL) == 1, 'Expected exactly one initial harness section')
    start = context.index(INITIAL) + len(INITIAL)
    initial, end = json.JSONDecoder().raw_decode(context, start)
    require(context[end:].startswith('\n\nTOOLS\n'), 'Unexpected data after initial entry JSON')
    context_start = model_prompt.index(context)
    current_start = model_prompt.find(CURRENT, context_start + len(context))
    require(current_start >= 0 and model_prompt.count(CURRENT, context_start + len(context)) == 1,
            'Expected exactly one current harness section after context')
    current_start += len(CURRENT)
    current, current_end = json.JSONDecoder().raw_decode(model_prompt, current_start)
    require(model_prompt[current_end:] == '', 'Unexpected data after current entry JSON')
    verify_entries(initial, base_state, identity)
    verify_entries(current, base_state, identity)
    require(initial == current, 'Initial and current complete harness entries differ before first root call')
    normalized = (model_prompt[:context_start + start] + '<COMPLETE_INITIAL_ENTRY_JSON>' +
                  model_prompt[context_start + end:current_start] + '<COMPLETE_CURRENT_ENTRY_JSON>')
    full = instruction + model_prompt
    require(identity not in full and identity.split('/')[0] not in full, 'Current run identity injected into initial root input')
    return {'full': full, 'normalized': instruction + normalized, 'entries': {'initial': initial, 'current': current},
            'context_sha256': digest(context), 'context_chars': len(context), 'context_bytes': len(context.encode())}


def verify_backend(task, trace, model, instruction, root_model):
    full = instruction + model['prompt']
    expected = {'purpose': 'root', 'model': root_model, 'prompt_chars': len(full), 'prompt_sha256': digest(full)}
    require(model['model'] == root_model, 'First trajectory model differs from configured root model')
    attempts = [(path, read(path)) for path in sorted((task / 'codex_attempts').glob('*.json'))]
    attempts = sorted([(p, r) for p, r in attempts if r.get('purpose') == 'root'], key=lambda item: (datetime.fromisoformat(item[1]['timestamp']), item[1]['call_id']))
    require(attempts, 'Missing root dispatch records')
    calls = read_lines(task / 'codex_calls.jsonl')
    require(len({row['call_id'] for _, row in calls}) == len(calls), 'Duplicate completed backend call identity')
    by_id = {row['call_id']: (n, row) for n, row in calls}
    verified, success = [], False
    for index, (path, attempt) in enumerate(attempts):
        require(path.stem == attempt['call_id'], 'Dispatch filename/call identity mismatch')
        require(all(attempt.get(k) == v for k, v in expected.items()) and attempt.get('attempt') == index,
                'Initial backend dispatch hash/length/model/attempt mismatch')
        require(attempt['call_id'] in by_id, 'Initial root dispatch has no completion')
        line, completion = by_id[attempt['call_id']]
        for kind, record in (('completion', completion),):
            require(all(record.get(k) == v for k, v in attempt.items()), 'Backend ' + kind + ' differs from dispatch')
            if 'prompt' in record:
                require(record['prompt'] == full, 'Full logged backend prompt differs from reconstruction')
        trace_refs = {}
        for event in ('exec.start', 'exec.end'):
            matches = [(n, row['details']) for n, row in trace if row.get('component') == 'Codex backend (root)'
                       and row.get('event') == event and row.get('details', {}).get('call_id') == attempt['call_id']]
            require(len(matches) == 1, 'Missing/duplicate initial backend trace ' + event)
            trace_line, details = matches[0]
            require(all(details.get(k) == v for k, v in expected.items()) and details.get('attempt') == index,
                    'Initial backend trace hash/length/model/attempt mismatch')
            if event == 'exec.end':
                require(all(details.get(k) == completion.get(k) for k in ('exit_code', 'error', 'response_chars')),
                        'Backend trace completion differs from call log')
            trace_refs[event] = trace_line
        verified.append({'dispatch': str(path), 'call_id': attempt['call_id'], 'attempt': index,
                         'completion_line': line, 'trace_lines': trace_refs, **expected})
        if completion.get('exit_code') == 0 and not completion.get('error'):
            require(completion.get('response_chars') == len(model['response']), 'Initial successful response length mismatch')
            if 'response' in completion:
                require(completion['response'] == model['response'], 'Initial successful response text mismatch')
            success = True
            break
    require(success, 'No successful backend completion for first root trajectory')
    # The earliest root event/call must be the first selected dispatch, not a hidden earlier execution.
    first_id = verified[0]['call_id']
    root_calls = [row for _, row in calls if row.get('purpose') == 'root']
    root_starts = [row['details'] for _, row in trace if row.get('component') == 'Codex backend (root)' and row.get('event') == 'exec.start']
    require(root_calls and root_calls[0]['call_id'] == first_id and root_starts and root_starts[0]['call_id'] == first_id,
            'Earliest root execution is not the reconstructed initial dispatch')
    return {'instruction_sha256': digest(instruction), 'instruction_chars': len(instruction),
            'instruction_bytes': len(instruction.encode()), 'prompt_sha256': digest(full),
            'prompt_chars': len(full), 'prompt_bytes': len(full.encode()), 'attempts': verified,
            'all_initial_dispatches_verified': True}, calls, attempts


def verify_date(config, task, archived, result):
    policy, task_date = config['agent']['as_of'], task.get('as_of_date')
    require(archived.get('policy') == policy and archived.get('task_date') == task_date, 'Date policy/task identity mismatch')
    expected_source = 'task' if task_date is not None else 'today' if policy == 'today' else 'config'
    require(archived.get('date_source') == expected_source, 'Invalid date provenance')
    resolved = archived['as_of_date']
    require(date.fromisoformat(resolved).isoformat() == resolved, 'Invalid resolved date')
    if task_date is not None or policy != 'today':
        require(resolved == (task_date or policy), 'Resolved date differs from task/config')
    require(result['as_of_date'] == resolved and result['date_source'] == expected_source, 'Agent result date provenance differs')


def verify_no_learning(harness, base, head, before, after, trace, calls, task, identity, initial):
    git(harness, 'merge-base', '--is-ancestor', base, head)
    require(not git(harness, 'log', '--format=%H', base + '..' + head, '--', 'edits').strip(),
            'Control contains procedure edit history, including a possible rollback')
    def procedure(state):
        return {key: {field: value for field, value in entry.items() if field not in ('usage', 'outcomes')}
                for key, entry in state['entries'].items()}
    require(procedure(before) == procedure(after), 'Control harness procedure fields changed')
    require({k: v for k, v in before.items() if k not in ('entries', 'seen', 'usage', 'outcomes')} ==
            {k: v for k, v in after.items() if k not in ('entries', 'seen', 'usage', 'outcomes')}, 'Unexpected top-level harness change')
    require(all(row.get('purpose') != 'refine' for _, row in calls), 'No-learning control invoked refinement model')
    attempts = [read(path) for path in (task / 'codex_attempts').glob('*.json')]
    require(all(row.get('purpose') != 'refine' for row in attempts), 'No-learning control dispatched refinement model')
    for _, row in trace:
        component, event = row.get('component', ''), row.get('event', '')
        require(not (component == 'Refine' and (event.startswith(('planning', 'apply', 'rollback')) or
                    event in ('scheduled', 'proposal', 'applied', 'edit_applied'))) and
                not (component == 'Harness' and event.split('.')[0] in ('create', 'update', 'delete', 'refine_edit')),
                'No-learning control contains a refinement/procedure edit trace')
    task_value = read(task / 'task.json')
    key = task_value['benchmark'] + ':' + task_value['task_id']
    require(key not in before['seen'], 'Control task was already seen at its base')
    require({k: v for k, v in after['seen'].items() if k != key} == before['seen'] and
            after['seen'].get(key, {}).get('run_id') == identity and after['seen'][key].get('before') == base,
            'Unexpected control seen bookkeeping')
    # Previous metadata is retained verbatim. New bookkeeping must belong to this run.
    for old, new in [(before, after), *((before['entries'][key], after['entries'][key]) for key in before['entries'])]:
        for field in ('usage', 'outcomes'):
            previous, current = old.get(field, []), new.get(field, [])
            require(current[:len(previous)] == previous and all(row.get('run_id') == identity for row in current[len(previous):]),
                    'Historical metadata changed or unrelated bookkeeping added: ' + field)
    journal_path = task / 'harness_usage.json'
    journal = read(journal_path) if journal_path.exists() else []
    for entry in initial:
        require({k: entry[k] for k in ('kind', 'id', 'version', 'refinement_id')} in journal,
                'Initial entry missing from durable usage journal')
    self_check = read(task / 'self_check.json')
    outcomes = [item for item in after['outcomes'] if item.get('run_id') == identity]
    if journal:
        require(len(outcomes) == 1 and all(outcomes[0].get(k) == self_check.get(k, []) for k in ('ok', 'issues', 'signals')),
                'Current self-check outcome missing or inconsistent in preserved harness state')
    for row in journal:
        key = row['kind'] + ':' + row['id']
        require(key in before['entries'] and all(row[k] == before['entries'][key][k] for k in ('version', 'refinement_id')),
                'Journal contains an entry version outside the control base')
        use = {'run_id': identity, 'version': row['version'], 'refinement_id': row['refinement_id']}
        require(use in after['usage'] and use in after['entries'][key]['usage'], 'Durable usage not retained in final harness state')
        require(outcomes[0] in after['entries'][key]['outcomes'], 'Outcome not retained on consumed entry')
    return state_differences(before, after)


def compare_inputs(arms):
    groups = {}
    for group in ('B0', 'B1-frozen'):
        labels = [f'{group}-{i}' for i in range(1, 4)]
        require(all(arms[label]['full'] == arms[labels[0]]['full'] for label in labels),
                'Initial full backend input differs within ' + group)
        groups[group] = {'labels': labels, 'repeats': 3, 'full_backend_input_identical': True,
                         'full_backend_sha256': digest(arms[labels[0]]['full'])}
    normalized = arms['B0-1']['normalized']
    require(all(arm['normalized'] == normalized for arm in arms.values()),
            'Cross-base initial backend input differs outside complete entry JSON')
    return groups, {'only_complete_entry_json_differs': True, 'outside_entries_sha256': digest(normalized),
                    'normalized_prompt_chars': len(normalized)}


def verify_inventory(record, run):
    verify_file(record, 'Archive inventory')
    inventory = read(record['path'])
    actual = {str(path.resolve()) for path in run.rglob('*') if path.is_file()}
    recorded = [item['path'] for item in inventory]
    require(len(recorded) == len(set(recorded)) and set(recorded) == actual, 'Archive inventory is incomplete or contains extra paths')
    for item in inventory:
        verify_file(item, 'Archived input')
    return {'record': record, 'files_verified': len(inventory), 'status': 'passed'}


def option(command, flag):
    require(command.count(flag) == 1, 'Expected one CLI option ' + flag)
    return command[command.index(flag) + 1]


def audit_arm(plan, execution, label, constants, config, expected_task):
    arm = execution.get('arms', {}).get(label, {})
    require(arm.get('status') == 'complete' and arm.get('exit_code') == 0 and arm.get('source_unchanged') is True,
            'Expected completed control with source verification: ' + label)
    require(arm.get('source_commit') == plan['source_commit'], 'Control source commit mismatch')
    base = plan['base_sha'] if label.startswith('B0-') else execution['POST_A']
    require(arm.get('base_sha') == base and arm.get('learning') is False, 'Control base/no-learning binding mismatch')
    workspace, run = Path(arm['workspace']).resolve(), Path(arm['run_path']).resolve()
    require(run == workspace / 'runs' / arm['run_id'] and arm['task_id'] == expected_task['task_id'], 'Control archive ownership mismatch')
    task, harness = run / arm['task_id'], workspace / 'harness'
    command = arm['command']
    require('--trace' in command and '--no-learning' in command and option(command, '--base') == base and
            Path(option(command, '--root')).resolve() == workspace and option(command, '--config') == plan['config_file'],
            'Recorded control command differs from its required flags')
    inventory = verify_inventory(arm['archive_hashes'], run)
    record = read(run / 'research.json')
    require(record == arm['record'] and record.get('status') == 'complete' and not record.get('error') and
            record['run_id'] == arm['run_id'] and record['task_id'] == arm['task_id'] and record['base_sha'] == base and
            record['learning'] is False and record['config'] == config, 'Durable control completion/identity/config mismatch')
    require(read(task / 'task.json') == expected_task and read(arm['task_file']) == expected_task and
            read(task / 'config.json') == config, 'Task/config differs from frozen request')
    require((task / 'harness_sha.txt').read_text().strip() == base, 'Archived task harness base mismatch')
    require(not (task / 'error.json').exists() or not read(task / 'error.json'), 'Durable task error present')
    isolation = arm['isolation']
    require(isolation.get('full_clone') is True and isolation.get('alternates') is False and isolation.get('hardlinks') is False and
            isolation['base_sha'] == base and Path(isolation['workspace']).resolve() == workspace, 'Control clone isolation receipt invalid')
    require(not (harness / '.git/objects/info/alternates').exists() and not (harness / '.git/shallow').exists(), 'Control clone is shared/shallow')
    require(all(path.stat().st_nlink == 1 for path in (harness / '.git/objects').rglob('*') if path.is_file()), 'Hardlinked harness objects')
    raw_before = git(harness, 'show', base + ':harness_state.json')
    require(bytes_record(raw_before) == {k: isolation['state'][k] for k in ('bytes', 'sha256')}, 'Initial isolated harness state differs from base')
    before, after = json.loads(raw_before), json.loads(git(harness, 'show', record['harness_head'] + ':harness_state.json'))
    as_of = read(task / 'as_of.json')
    verify_date(config, expected_task, as_of, read(task / 'agent_result.json'))
    context = (task / 'prompt.txt').read_bytes().decode('utf-8')
    require((task / 'root_prompt.txt').read_bytes().decode('utf-8') == context, 'Saved context/root context differs')
    header = (f"TASK\n{expected_task['question']}\nSPEC\n{json.dumps(expected_task['spec'], ensure_ascii=False)}\n\n"
              f"AS-OF DATE\n{as_of['as_of_date']} (source: {as_of['date_source']}). "
              'Honor all dates/periods in the task text.\n\n')
    require(context.startswith(header), 'Prompt task/date header differs from archived task and provenance')
    metadata = {'context_type': 'str', 'context_total_length': len(context)}
    require(read(task / 'prompt_metadata.json') == metadata, 'Saved true context-size metadata mismatch')
    trajectory = read_lines(task / 'trajectory.jsonl')
    roots = [(n, row) for n, row in trajectory if row.get('type') == 'model' and row.get('purpose') == 'root']
    require(roots, 'Missing initial root trajectory')
    root_line, model = roots[0]
    identity = arm['run_id'] + '/' + arm['task_id']
    inputs = parse_inputs(context, model['prompt'], constants['instruction'], before, identity)
    trace = read_lines(run / 'trace.jsonl')
    observed = [row['details'] for _, row in trace if row.get('component') == 'RLM' and row.get('event') == 'context_metadata'
                and row.get('details', {}).get('depth') == 0]
    require(observed and all(observed[0].get(k) == v for k, v in metadata.items()), 'True root context size missing/different in trace')
    backend, calls, _ = verify_backend(task, trace, model, constants['instruction'], config['models']['root'])
    changes = verify_no_learning(harness, base, record['harness_head'], before, after, trace, calls, task, identity, inputs['entries']['initial'])
    fetches = read(task / 'evidence.json').get('fetches', [])
    telemetry = read(task / 'fetch_telemetry.json') if (task / 'fetch_telemetry.json').exists() else []
    require(all(row.get('fetch_path') == constants['fetch_path'] for row in [*fetches, *telemetry]), 'Unexpected fetch path in archive')
    require({row['id'] for row in fetches} == {row['id'] for row in telemetry}, 'Fetch telemetry/request identities differ')
    require(all(row.get('purpose') != 'fetch' for _, row in calls), 'New direct fetch path invoked model fetch')
    report = {'run_id': arm['run_id'], 'workspace': str(workspace), 'run_path': str(run), 'base_sha': base,
              'harness_head': record['harness_head'], 'source_commit': arm['source_commit'], 'source_unchanged_at_finish': True,
              'inventory': inventory, 'as_of': as_of, 'backend': {**backend, 'trajectory_line': root_line},
              'entries': inputs['entries'], 'context_sha256': inputs['context_sha256'], 'context_chars': inputs['context_chars'],
              'context_bytes': inputs['context_bytes'], 'state_bookkeeping_differences': changes,
              'procedural_edits': False, 'current_run_metadata_in_initial_entries': False,
              'fetch_path': constants['fetch_path'], 'fetch_requests': len(fetches), 'fetch_measurements': len(telemetry),
              'bookkeeping_injection_check': 'Current run identity absent; complete entries match their base; all outside-entry bytes compared.'}
    return report, inputs, before


def audit_directory(directory, expected_source=None):
    directory = Path(directory).resolve()
    plan, execution = read(directory / 'plan.json'), read(directory / 'execution.json')
    require(Path(plan['directory']).resolve() == directory, 'Plan belongs to a different cohort directory')
    require(execution['source_commit'] == plan['source_commit'], 'Plan/execution source commit mismatch')
    if expected_source is not None:
        require(expected_source == plan['source_commit'], 'Expected source differs from cohort plan')
    source, constants = verify_source(plan)
    config, task = read(plan['config_file']), read(plan['tasks']['B'])
    arms, inputs, bases = {}, {}, {}
    for label in CONTROLS:
        try:
            arms[label], inputs[label], bases[label] = audit_arm(plan, execution, label, constants, config, task)
        except (KeyError, ValueError, OSError) as exc:
            raise AuditError(label + ': ' + str(exc)) from exc
    require(len({a['workspace'] for a in arms.values()}) == len(CONTROLS) and
            len({a['run_path'] for a in arms.values()}) == len(CONTROLS) and
            len({a['run_id'] for a in arms.values()}) == len(CONTROLS), 'Controls share a workspace/run identity')
    require(all(arm['as_of'] == arms['B0-1']['as_of'] for arm in arms.values()), 'Date policy/provenance differs across controls')
    for group in ('B0', 'B1-frozen'):
        require(all(bases[f'{group}-{i}'] == bases[f'{group}-1'] for i in range(1, 4)), 'Same-base harness snapshots differ')
    groups, comparison = compare_inputs(inputs)
    entry_diff = state_differences(inputs['B0-1']['entries'], inputs['B1-frozen-1']['entries'])
    return {'status': 'passed', 'audited_at': datetime.now(timezone.utc).isoformat(), 'directory': str(directory),
            'source_commit': plan['source_commit'], 'source_verification': source, 'config': config, 'task': task,
            'inputs': {'plan': file_record(directory / 'plan.json'), 'execution': file_record(directory / 'execution.json')},
            'fetch_path': constants['fetch_path'], 'groups': groups, 'cross_base': {**comparison, 'complete_entry_differences': entry_diff},
            'base_state_differences': state_differences(bases['B0-1'], bases['B1-frozen-1']), 'arms': arms,
            'bookkeeping_scope': 'Full BASE/POST_A and per-run state differences are reported. Historical entry usage/outcomes are part of the allowed entry intervention. Top-level seen/usage/outcomes are storage bookkeeping; run-specific changes do not enter the verified initial root input.',
            'limitations': LIMITATIONS}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True, help='Completed cohort containing plan.json/execution.json')
    parser.add_argument('--expected-source', help='Optional exact source assertion; default inferred from plan')
    parser.add_argument('--output-dir', type=Path, help='Write JSON audit and verified initial inputs outside all run archives; otherwise print JSON')
    args = parser.parse_args()
    try:
        report = audit_directory(args.directory, args.expected_source)
        if args.output_dir:
            output = args.output_dir.resolve()
            protected = [Path(arm['workspace']).resolve() for arm in report['arms'].values()]
            require(all(not output.is_relative_to(p) for p in protected), 'Output must be outside all control workspaces')
            require(not output.exists() or not any(output.iterdir()), 'Output directory must be new or empty; do not overwrite an audit')
            output.mkdir(parents=True, exist_ok=True)
            instruction = literal(git(Path(read(args.directory / 'plan.json')['main_root']), 'show', report['source_commit'] + ':src/loop_research/codex_backend.py'), 'INSTRUCTION')
            for label, arm in report['arms'].items():
                task = Path(arm['run_path']) / report['task']['task_id']
                model = next(row for _, row in read_lines(task / 'trajectory.jsonl') if row.get('type') == 'model' and row.get('purpose') == 'root')
                full = instruction + model['prompt']
                require(digest(full) == arm['backend']['prompt_sha256'], 'Verified input changed while exporting')
                (output / (label + '.initial_backend_input.txt')).write_bytes(full.encode('utf-8'))
            (output / 'control_audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            print(json.dumps({'status': 'passed', 'report': str(output / 'control_audit.json'),
                              'source_commit': report['source_commit'], 'fetch_path': report['fetch_path'], 'limitations': LIMITATIONS}))
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (AuditError, KeyError, OSError, ValueError) as exc:
        print(json.dumps({'status': 'failed', 'error': str(exc)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
