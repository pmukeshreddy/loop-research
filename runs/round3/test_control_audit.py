"""Offline synthetic archives and real temporary Git repositories; no product imports."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('control_audit', HERE / 'control_audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def lines(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(v, ensure_ascii=False) + '\n' for v in values))


def git(path, *args):
    return subprocess.check_output(['git', '-C', str(path), *args], stderr=subprocess.DEVNULL).decode().strip()


def init(path):
    path.mkdir(parents=True, exist_ok=True)
    git(path, 'init', '-q')
    git(path, 'config', 'user.name', 'Synthetic audit')
    git(path, 'config', 'user.email', 'audit@example.invalid')


def commit(path):
    git(path, 'add', '.')
    git(path, 'commit', '-qm', 'Synthetic fixture')
    return git(path, 'rev-parse', 'HEAD')


class ControlAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.directory = self.root / 'cohort'
        self.directory.mkdir()
        self.source = self.root / 'source'
        init(self.source)
        self.instruction = 'Backend instruction.\n\n'
        modules = {'codex_backend.py': 'INSTRUCTION = ' + repr(self.instruction) + '\n',
                   'page_fetch.py': "FETCH_PATH = 'direct-readable-v1'\n"}
        self.verification = []
        for name, content in modules.items():
            relative = 'src/loop_research/' + name
            path = self.source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            installed = self.root / 'installed' / name
            installed.parent.mkdir(exist_ok=True)
            installed.write_text(content)
            self.verification.append({'source': relative, 'installed': str(installed),
                                      **audit.bytes_record(content.encode())})
        self.source_sha = commit(self.source)
        self.config = {'agent': {'as_of': '2025-04-03'}, 'models': {'root': 'synthetic-model'}}
        self.task = {'task_id': 'synthetic-task', 'benchmark': 'research', 'question': 'Question α?',
                     'as_of_date': None, 'spec': {'columns': ['name'], 'keys': ['name']}, 'language': 'en'}
        save(self.directory / 'config.json', self.config)
        save(self.directory / 'task.json', self.task)
        self.origin = self.root / 'original-harness'
        init(self.origin)
        self.entry = {'id': 'entry', 'kind': 'memory', 'title': 'Complete α', 'body': 'Full body',
                      'module': None, 'version': 1, 'refinement_id': 'old-refinement',
                      'created_at': 'old', 'updated_at': 'old', 'trigger': 'prior', 'evidence': ['prior-evidence'],
                      'usage': [{'run_id': 'historical/run', 'version': 1, 'refinement_id': 'old-refinement'}],
                      'outcomes': [{'run_id': 'historical/run', 'ok': True, 'issues': [], 'recorded_at': 'old'}]}
        self.before = {'entries': {'memory:entry': self.entry}, 'seen': {}, 'usage': [], 'outcomes': []}
        save(self.origin / 'harness_state.json', self.before)
        self.base = commit(self.origin)
        self.after_a = copy.deepcopy(self.before)
        self.after_a['entries']['memory:entry']['usage'].append({'run_id': 'A/task', 'version': 1, 'refinement_id': 'old-refinement'})
        self.after_a['entries']['memory:entry']['outcomes'].append({'run_id': 'A/task', 'ok': True})
        self.after_a['entries']['memory:lesson'] = {**copy.deepcopy(self.entry), 'id': 'lesson', 'body': 'New lesson', 'refinement_id': 'new-refinement'}
        self.after_a['seen']['research:A'] = {'run_id': 'A/task', 'before': self.base, 'created_at': 'after-A'}
        save(self.origin / 'harness_state.json', self.after_a)
        self.post_a = commit(self.origin)
        self.plan = {'directory': str(self.directory), 'main_root': str(self.source), 'source_commit': self.source_sha,
                     'base_sha': self.base, 'config_file': str(self.directory / 'config.json'),
                     'tasks': {'B': str(self.directory / 'task.json')},
                     'source_verification': {'commit': self.source_sha, 'modules': self.verification,
                         'package_root': str(self.root / 'installed')}, 'frozen_files': [
                         audit.file_record(self.directory / 'config.json'), audit.file_record(self.directory / 'task.json')]}
        self.execution = {'source_commit': self.source_sha, 'POST_A': self.post_a, 'arms': {}}
        for label in audit.CONTROLS:
            self.make_arm(label)
        self.persist()

    def make_arm(self, label):
        workspace = self.directory / 'workspaces' / label
        workspace.mkdir(parents=True)
        harness = workspace / 'harness'
        subprocess.run(['git', 'clone', '-q', '--no-hardlinks', '--no-local', str(self.origin), str(harness)], check=True)
        git(harness, 'config', 'user.name', 'Synthetic audit')
        git(harness, 'config', 'user.email', 'audit@example.invalid')
        frozen = label.startswith('B1-frozen')
        base = self.post_a if frozen else self.base
        git(harness, 'checkout', '-q', base)
        base_state = copy.deepcopy(self.after_a if frozen else self.before)
        state_record = audit.file_record(harness / 'harness_state.json')
        run_id = 'run-' + label
        run = workspace / 'runs' / run_id
        task = run / self.task['task_id']
        identity = run_id + '/' + self.task['task_id']
        entries = list(base_state['entries'].values())
        state = copy.deepcopy(base_state)
        state['seen']['research:' + self.task['task_id']] = {'run_id': identity, 'before': base, 'created_at': label}
        outcome = {'run_id': identity, 'ok': True, 'issues': [], 'signals': [], 'recorded_at': label}
        state['outcomes'].append(outcome)
        for entry in state['entries'].values():
            use = {key: entry[key] for key in ('version', 'refinement_id')}
            use['run_id'] = identity
            state['usage'].append(use)
            entry['usage'].append(use)
            entry['outcomes'].append(outcome)
        save(harness / 'harness_state.json', state)
        head = commit(harness)
        record = {'run_id': run_id, 'task_id': self.task['task_id'], 'learning': False, 'base_sha': base,
                  'harness_head': head, 'config': self.config, 'status': 'complete', 'error': None}
        save(run / 'research.json', record)
        for name, value in [('config.json', self.config), ('task.json', self.task),
                ('as_of.json', {'policy': self.config['agent']['as_of'], 'task_date': None,
                               'as_of_date': self.config['agent']['as_of'], 'date_source': 'config'}),
                ('agent_result.json', {'as_of_date': self.config['agent']['as_of'], 'date_source': 'config'}),
                ('self_check.json', {'ok': True, 'issues': [], 'signals': []}),
                ('harness_usage.json', [{k: e[k] for k in ('kind', 'id', 'version', 'refinement_id')} for e in entries]),
                ('evidence.json', {'fetches': [{'id': 1, 'fetch_path': 'direct-readable-v1'}]}),
                ('fetch_telemetry.json', [{'id': 1, 'fetch_path': 'direct-readable-v1'}])]:
            save(task / name, value)
        (task / 'harness_sha.txt').write_text(base + '\n')
        context = (f"TASK\n{self.task['question']}\nSPEC\n{json.dumps(self.task['spec'], ensure_ascii=False)}\n\n"
                   f"AS-OF DATE\n{self.config['agent']['as_of']} (source: config). Honor all dates/periods in the task text.\n\n"
                   'Policy\nRELEVANT HARNESS\n' + json.dumps(entries, ensure_ascii=False) + '\n\nTOOLS\ncomplete tools')
        for name in ('prompt.txt', 'root_prompt.txt'):
            (task / name).write_text(context)
        save(task / 'prompt_metadata.json', {'context_type': 'str', 'context_total_length': len(context)})
        prompt = 'System framing\n' + context + '\ncontext has a stable type\nCURRENT RELEVANT HARNESS ENTRIES\n' + json.dumps(entries, ensure_ascii=False)
        lines(task / 'trajectory.jsonl', [{'type': 'model', 'purpose': 'root', 'model': 'synthetic-model', 'prompt': prompt, 'response': 'response'}])
        dispatch = {'call_id': label, 'timestamp': '2025-04-03T01:00:00+00:00', 'purpose': 'root', 'model': 'synthetic-model',
                    'attempt': 0, 'prompt_chars': len(self.instruction + prompt), 'prompt_sha256': audit.digest(self.instruction + prompt)}
        save(task / 'codex_attempts' / (label + '.json'), dispatch)
        completed = {**dispatch, 'exit_code': 0, 'error': None, 'response_chars': len('response')}
        lines(task / 'codex_calls.jsonl', [completed])
        trace = [{'component': 'RLM', 'event': 'context_metadata', 'details': {'depth': 0, 'context_type': 'str', 'context_total_length': len(context)}},
                 {'component': 'Codex backend (root)', 'event': 'exec.start', 'details': dispatch},
                 {'component': 'Codex backend (root)', 'event': 'exec.end', 'details': completed}]
        lines(run / 'trace.jsonl', trace)
        self.execution['arms'][label] = {'status': 'complete', 'exit_code': 0, 'source_unchanged': True,
             'source_commit': self.source_sha, 'workspace': str(workspace), 'base_sha': base, 'learning': False,
             'run_id': run_id, 'run_path': str(run), 'task_id': self.task['task_id'], 'task_file': self.plan['tasks']['B'],
             'record': record, 'command': ['loop-research', '--root', str(workspace), '--config', self.plan['config_file'],
                     'research', self.task['question'], '--trace', '--base', base, '--no-learning'],
             'isolation': {'base_sha': base, 'workspace': str(workspace), 'full_clone': True,
                           'alternates': False, 'hardlinks': False, 'state': state_record}}
        self.refresh(label)

    def paths(self, label='B0-1'):
        record = self.execution['arms'][label]
        run = Path(record['run_path'])
        return run, run / record['task_id']

    def refresh(self, label):
        run, _ = self.paths(label)
        path = self.directory / (label + '.archive_hashes.json')
        save(path, [audit.file_record(p) for p in sorted(run.rglob('*')) if p.is_file()])
        self.execution['arms'][label]['archive_hashes'] = audit.file_record(path)

    def persist(self):
        save(self.directory / 'plan.json', self.plan)
        save(self.directory / 'execution.json', self.execution)

    def run_audit(self):
        self.persist()
        return audit.audit_directory(self.directory)

    def test_complete_entries_metadata_and_backend_instruction_are_verified(self):
        result = self.run_audit()
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['source_verification']['commit'], self.source_sha)
        self.assertEqual(result['groups']['B0']['repeats'], 3)
        self.assertTrue(result['cross_base']['only_complete_entry_json_differs'])
        self.assertEqual(result['arms']['B0-1']['backend']['instruction_sha256'], audit.digest(self.instruction))
        self.assertEqual(result['arms']['B0-1']['entries']['initial'][0], self.entry)
        self.assertIn('/seen/research:A', [d['path'] for d in result['base_state_differences']])
        self.assertTrue(result['arms']['B0-1']['state_bookkeeping_differences'])
        self.assertIn('not statistical', result['limitations'])
        self.assertEqual(result['fetch_path'], 'direct-readable-v1')

    def test_backend_hash_wrong_even_when_saved_context_equal(self):
        _, task = self.paths()
        path = next((task / 'codex_attempts').glob('*.json'))
        data = json.loads(path.read_text()); data['prompt_sha256'] = '0' * 64; save(path, data)
        self.refresh('B0-1')
        with self.assertRaisesRegex(audit.AuditError, 'dispatch'):
            self.run_audit()

    def test_current_usage_injected_in_dynamic_entries_is_rejected(self):
        _, task = self.paths()
        path = task / 'trajectory.jsonl'
        row = json.loads(path.read_text())
        marker = '\nCURRENT RELEVANT HARNESS ENTRIES\n'
        prefix, value = row['prompt'].rsplit(marker, 1)
        entries = json.loads(value)
        entries[0]['usage'].append({'run_id': 'run-B0-1/synthetic-task'})
        row['prompt'] = prefix + marker + json.dumps(entries, ensure_ascii=False)
        lines(path, [row]); self.refresh('B0-1')
        with self.assertRaisesRegex(audit.AuditError, 'complete base entry|initial.*current'):
            self.run_audit()

    def test_entry_field_dropped_is_rejected(self):
        entry = copy.deepcopy(self.entry); del entry['outcomes']
        with self.assertRaisesRegex(audit.AuditError, 'complete base entry'):
            audit.verify_entries([entry], self.before, 'a-new-run/task')

    def test_cross_base_extra_framing_diff_is_rejected(self):
        same = {'full': 'before [entries] after', 'normalized': 'before <ENTRIES> after'}
        changed = {'full': 'before muchmore [entries] after', 'normalized': 'before muchmore <ENTRIES> after'}
        arms = {label: dict(same) for label in audit.CONTROLS}
        for label in audit.CONTROLS:
            if label.startswith('B1-frozen'):
                arms[label] = dict(changed)
        with self.assertRaisesRegex(audit.AuditError, 'outside complete entry JSON'):
            audit.compare_inputs(arms)

    def test_within_base_difference_is_rejected(self):
        arms = {label: {'full': 'x', 'normalized': 'same'} for label in audit.CONTROLS}
        arms['B0-2']['full'] = 'different'
        with self.assertRaisesRegex(audit.AuditError, 'within B0'):
            audit.compare_inputs(arms)

    def test_date_provenance_is_validated_before_parity(self):
        for label in audit.CONTROLS:
            _, task = self.paths(label)
            path = task / 'as_of.json'; value = json.loads(path.read_text()); value['date_source'] = 'task'; save(path, value)
            self.refresh(label)
        with self.assertRaisesRegex(audit.AuditError, 'date provenance'):
            self.run_audit()

    def test_procedure_edit_and_rollback_in_history_is_rejected(self):
        label = 'B0-1'; arm = self.execution['arms'][label]
        harness = Path(arm['workspace']) / 'harness'
        save(harness / 'edits' / 'attempt.json', {'op': 'edit'})
        commit(harness)
        (harness / 'edits' / 'attempt.json').unlink()
        arm['record']['harness_head'] = commit(harness)
        run, _ = self.paths(label); save(run / 'research.json', arm['record']); self.refresh(label)
        with self.assertRaisesRegex(audit.AuditError, 'procedure edit history'):
            self.run_audit()

    def test_missing_archive_hash_inventory_file_is_rejected(self):
        _, task = self.paths(); (task / 'unexpected.json').write_text('{}')
        with self.assertRaisesRegex(audit.AuditError, 'inventory'):
            self.run_audit()

    def test_changed_installed_source_is_rejected(self):
        Path(self.verification[0]['installed']).write_text('changed')
        with self.assertRaisesRegex(audit.AuditError, 'installed module'):
            self.run_audit()

    def test_incomplete_arm_is_rejected(self):
        self.execution['arms']['B0-3']['status'] = 'running'
        with self.assertRaisesRegex(audit.AuditError, 'completed control'):
            self.run_audit()

    def test_context_newlines_are_not_normalized(self):
        run, task = self.paths()
        old = (task / 'prompt.txt').read_bytes().decode()
        self.task['question'] += '\r\nNext line'
        new = old.replace('Question α?', self.task['question'], 1)
        save(task / 'task.json', self.task)
        save(self.directory / 'task.json', self.task)
        for name in ('prompt.txt', 'root_prompt.txt'):
            (task / name).write_bytes(new.encode())
        save(task / 'prompt_metadata.json', {'context_type': 'str', 'context_total_length': len(new)})
        row = json.loads((task / 'trajectory.jsonl').read_text())
        row['prompt'] = row['prompt'].replace(old, new)
        lines(task / 'trajectory.jsonl', [row])
        dispatch_path = next((task / 'codex_attempts').glob('*.json'))
        dispatch = json.loads(dispatch_path.read_text())
        full = self.instruction + row['prompt']
        dispatch.update(prompt_chars=len(full), prompt_sha256=audit.digest(full))
        save(dispatch_path, dispatch)
        completed = {**json.loads((task / 'codex_calls.jsonl').read_text()), **dispatch}
        lines(task / 'codex_calls.jsonl', [completed])
        events = [{'component': 'RLM', 'event': 'context_metadata', 'details': {'depth': 0, 'context_type': 'str', 'context_total_length': len(new)}},
                  {'component': 'Codex backend (root)', 'event': 'exec.start', 'details': dispatch},
                  {'component': 'Codex backend (root)', 'event': 'exec.end', 'details': completed}]
        lines(run / 'trace.jsonl', events); self.refresh('B0-1')
        report, _, _ = audit.audit_arm(self.plan, self.execution, 'B0-1',
            {'instruction': self.instruction, 'fetch_path': 'direct-readable-v1'}, self.config, self.task)
        self.assertEqual(report['context_sha256'], audit.digest(new))

    def test_prompt_task_date_header_must_agree_with_archive(self):
        run, task = self.paths()
        context = (task / 'prompt.txt').read_text().replace('(source: config)', '(source: today)')
        for name in ('prompt.txt', 'root_prompt.txt'):
            (task / name).write_text(context)
        save(task / 'prompt_metadata.json', {'context_type': 'str', 'context_total_length': len(context)})
        self.refresh('B0-1')
        with self.assertRaisesRegex(audit.AuditError, 'task/date header'):
            self.run_audit()

    def test_backend_character_count_uses_unicode_characters_not_bytes(self):
        _, task = self.paths()
        path = next((task / 'codex_attempts').glob('*.json'))
        data = json.loads(path.read_text())
        prompt = self.instruction + json.loads((task / 'trajectory.jsonl').read_text())['prompt']
        self.assertGreater(len(prompt.encode()), len(prompt))
        data['prompt_chars'] = len(prompt.encode()); save(path, data); self.refresh('B0-1')
        with self.assertRaisesRegex(audit.AuditError, 'dispatch'):
            self.run_audit()

    def test_missing_root_trace_is_rejected(self):
        run, _ = self.paths()
        rows = [json.loads(line) for line in (run / 'trace.jsonl').read_text().splitlines()]
        lines(run / 'trace.jsonl', rows[:-1]); self.refresh('B0-1')
        with self.assertRaisesRegex(audit.AuditError, 'trace exec.end'):
            self.run_audit()

    def test_first_root_retry_is_verified_and_retained(self):
        run, task = self.paths()
        dispatch_path = next((task / 'codex_attempts').glob('*.json'))
        first = json.loads(dispatch_path.read_text())
        success = json.loads((task / 'codex_calls.jsonl').read_text())
        failed = {**success, 'exit_code': 1, 'error': 'synthetic retry', 'response_chars': 0}
        second = {**first, 'call_id': 'retry', 'attempt': 1, 'timestamp': '2025-04-03T01:01:00+00:00'}
        success.update(second)
        save(task / 'codex_attempts/retry.json', second)
        lines(task / 'codex_calls.jsonl', [failed, success])
        context_event = json.loads((run / 'trace.jsonl').read_text().splitlines()[0])
        trace = [context_event]
        for dispatch, completed in [(first, failed), (second, success)]:
            trace += [{'component': 'Codex backend (root)', 'event': 'exec.start', 'details': dispatch},
                      {'component': 'Codex backend (root)', 'event': 'exec.end', 'details': completed}]
        lines(run / 'trace.jsonl', trace); self.refresh('B0-1')
        result = self.run_audit()
        self.assertEqual(len(result['arms']['B0-1']['backend']['attempts']), 2)

    def test_successful_root_cannot_hide_an_earlier_mismatched_call(self):
        _, task = self.paths()
        success = json.loads((task / 'codex_calls.jsonl').read_text())
        lines(task / 'codex_calls.jsonl', [{**success, 'call_id': 'unrecorded-earlier'}, success])
        self.refresh('B0-1')
        with self.assertRaisesRegex(audit.AuditError, 'Earliest root execution'):
            self.run_audit()

    def test_date_policies_accept_true_config_today_and_task_provenance(self):
        for policy, task_date, resolved, source in [('2025-04-03', None, '2025-04-03', 'config'),
                ('today', None, '2025-04-04', 'today'), ('today', '2025-04-02', '2025-04-02', 'task')]:
            with self.subTest(source=source):
                audit.verify_date({'agent': {'as_of': policy}}, {'as_of_date': task_date},
                    {'policy': policy, 'task_date': task_date, 'as_of_date': resolved, 'date_source': source},
                    {'as_of_date': resolved, 'date_source': source})

    def test_full_prompt_cannot_hide_missing_historical_fields_in_both_sections(self):
        entries = [copy.deepcopy(self.entry)]
        del entries[0]['evidence']
        context = 'TASK\nRELEVANT HARNESS\n' + json.dumps(entries) + '\n\nTOOLS\nFull tools'
        prompt = context + '\nCURRENT RELEVANT HARNESS ENTRIES\n' + json.dumps(entries)
        with self.assertRaisesRegex(audit.AuditError, 'complete base entry'):
            audit.parse_inputs(context, prompt, self.instruction, self.before, 'fresh-run/task')

    def test_refinement_attempt_is_rejected_even_without_completion(self):
        _, task = self.paths()
        save(task / 'codex_attempts/refine.json', {'call_id': 'refine', 'purpose': 'refine'})
        self.refresh('B0-1')
        with self.assertRaisesRegex(audit.AuditError, 'dispatched refinement'):
            self.run_audit()

    def test_preserved_metadata_may_not_be_erased_from_final_storage(self):
        label = 'B0-1'; arm = self.execution['arms'][label]
        harness = Path(arm['workspace']) / 'harness'
        state = json.loads((harness / 'harness_state.json').read_text())
        state['entries']['memory:entry']['usage'].pop(0)
        save(harness / 'harness_state.json', state)
        arm['record']['harness_head'] = commit(harness)
        run, _ = self.paths(label); save(run / 'research.json', arm['record']); self.refresh(label)
        with self.assertRaisesRegex(audit.AuditError, 'Historical metadata changed'):
            self.run_audit()

    def test_cli_exports_only_to_separate_output_and_keeps_archives_unchanged(self):
        before = {label: self.execution['arms'][label]['archive_hashes'] for label in audit.CONTROLS}
        output = self.directory / 'audit-output'
        result = subprocess.run([sys.executable, str(HERE / 'control_audit.py'), '--directory', str(self.directory),
                                 '--output-dir', str(output)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((output / 'control_audit.json').read_text())['status'], 'passed')
        self.assertEqual(len(list(output.glob('*.initial_backend_input.txt'))), 6)
        self.assertTrue((output / 'B0-1.initial_backend_input.txt').read_text().startswith(self.instruction))
        for label in audit.CONTROLS:
            self.assertEqual(audit.file_record(before[label]['path']), before[label])
        result = subprocess.run([sys.executable, str(HERE / 'control_audit.py'), '--directory', str(self.directory),
                                 '--output-dir', str(output)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('do not overwrite', result.stderr)

    def test_wrong_fetch_path_is_rejected(self):
        _, task = self.paths(); save(task / 'fetch_telemetry.json', [{'id': 1, 'fetch_path': 'old-model'}]); self.refresh('B0-1')
        with self.assertRaisesRegex(audit.AuditError, 'fetch path'):
            self.run_audit()


if __name__ == '__main__':
    unittest.main()
