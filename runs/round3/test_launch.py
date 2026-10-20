"""Standalone offline launcher tests; every subprocess and repository is synthetic."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

HERE = Path(__file__).resolve().parent


def git(path, *args):
    return subprocess.check_output(['git', '-C', str(path), *args], text=True).strip()


def repository(path):
    path.mkdir()
    git(path, 'init', '-q', '-b', 'main')
    git(path, 'config', 'user.name', 'Offline fixture')
    git(path, 'config', 'user.email', 'fixture@localhost')
    (path / 'harness_state.json').write_text('{"entries":{},"seen":{},"usage":[],"outcomes":[]}')
    git(path, 'add', '.')
    git(path, 'commit', '-qm', 'fixture')
    return git(path, 'rev-parse', 'HEAD')


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((HERE / 'launch.py').is_file(), 'Round 3 launcher must exist')
        spec = importlib.util.spec_from_file_location('round3_launcher_test', HERE / 'launch.py')
        self.launch = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.launch)
        self.temp = tempfile.TemporaryDirectory(prefix='round3-launch-offline-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_receipts_require_completed_checks_for_exact_source_and_rollback(self):
        evidence = self.root / 'check.log'
        evidence.write_text('offline check complete')
        record = self.launch.file_record(evidence)
        preflight = {'source_commit': 'a' * 40, 'all_fixes_complete': True,
                     'full_suite': {'exit_code': 0, 'passed': 3, 'evidence': record},
                     'saved_refine': {'status': 'passed', 'evidence': record},
                     'archive_audit': {'status': 'passed', 'evidence': record}}
        rollback = {'source_commit': 'a' * 40, 'base_sha': self.launch.BASE,
                    'harness_head': self.launch.BASE, 'completed_at': '2026-10-19T20:00:00+00:00'}
        self.launch.receipt_gate(preflight, rollback, 'a' * 40)
        for key in ['saved_refine', 'archive_audit']:
            broken = json.loads(json.dumps(preflight))
            broken[key]['status'] = 'pending'
            with self.assertRaises(ValueError):
                self.launch.receipt_gate(broken, rollback, 'a' * 40)
        with self.assertRaises(ValueError):
            self.launch.receipt_gate(preflight, rollback, 'b' * 40)
        evidence.write_text('changed')
        with self.assertRaises(ValueError):
            self.launch.receipt_gate(preflight, rollback, 'a' * 40)

    def test_full_clone_has_independent_objects_and_exact_requested_base(self):
        source = self.root / 'original'
        base = repository(source)
        (source / 'harness_state.json').write_text('{"entries":{"later":{}}}')
        git(source, 'commit', '-qam', 'later state')
        workspace = self.root / 'arm'
        proof = self.launch.clone_harness(source, workspace, base)
        clone = workspace / 'harness'
        self.assertEqual(git(clone, 'rev-parse', 'HEAD'), base)
        self.assertFalse((clone / '.git/objects/info/alternates').exists())
        self.assertFalse((clone / '.git/shallow').exists())
        self.assertIn('--no-hardlinks', proof['commands'][0])
        self.assertTrue(all((workspace / name).is_dir() for name in ('runs', 'reports', 'cache')))
        source_inodes = {(p.stat().st_dev, p.stat().st_ino) for p in (source / '.git/objects').rglob('*') if p.is_file()}
        clone_inodes = {(p.stat().st_dev, p.stat().st_ino) for p in (clone / '.git/objects').rglob('*') if p.is_file()}
        self.assertFalse(source_inodes & clone_inodes)

    def test_b_requires_successful_a_and_committed_exact_prediction_binding(self):
        repo = self.root / 'repo'
        source = repository(repo)
        plan = {'main_root': str(repo), 'source_commit': source}
        state = {'phases': {'a_si': {'status': 'complete'}}, 'arms': {
            'A': {'status': 'complete', 'record': {'harness_head': 'b' * 40},
                  'ended_at': self.launch.stamp()}}}
        prediction = repo / 'predictions.md'
        prediction.write_text('source_commit: ' + source + '\nPOST_A: ' + 'b' * 40 + '\nExpected changes.\n')
        git(repo, 'add', 'predictions.md')
        git(repo, 'commit', '-qm', 'predictions')
        commit = git(repo, 'rev-parse', 'HEAD')
        receipt = self.launch.prediction_gate(plan, state, prediction, commit)
        self.assertEqual(receipt['commit'], commit)
        state['arms']['A']['status'] = 'failed'
        with self.assertRaises(ValueError):
            self.launch.prediction_gate(plan, state, prediction, commit)
        state['arms']['A']['status'] = 'complete'
        prediction.write_text(prediction.read_text() + 'uncommitted change')
        with self.assertRaises(ValueError):
            self.launch.prediction_gate(plan, state, prediction, commit)

    def test_scheduler_stops_new_work_on_failure_and_waits_for_owned_sibling(self):
        script = self.root / 'process.py'
        script.write_text('import pathlib,sys,time\ntime.sleep(float(sys.argv[2]))\npathlib.Path(sys.argv[1]).write_text("done")\nsys.exit(int(sys.argv[3]))\n')
        records = {}
        for label, seconds, status in [('bad', '.05', '2'), ('sibling', '.2', '0'), ('later', '0', '0')]:
            records[label] = {'command': [sys.executable, str(script), str(self.root / label), seconds, status],
                              'console': str(self.root / (label + '.log')), 'status': 'prepared'}
        # The scheduler owns only process lifecycle; archive validation is a separate strict step.
        self.launch.process_group(records, self.root / 'processes.json', max_parallel=2)
        self.assertEqual(records['bad']['status'], 'failed')
        self.assertEqual(records['sibling']['status'], 'exited')
        self.assertEqual(records['later']['status'], 'not_launched')
        self.assertTrue((self.root / 'sibling').is_file())
        self.assertFalse((self.root / 'later').exists())
        self.assertIn('started_at', records['bad'])
        self.assertIn('ended_at', records['bad'])
        self.assertEqual(records['bad']['exit_code'], 2)

    def test_group_rejects_more_than_three_parallel_processes(self):
        with self.assertRaises(ValueError):
            self.launch.process_group({}, self.root / 'state.json', max_parallel=4)

    def test_exit_zero_with_durable_error_blocks_next_process_and_keeps_archive(self):
        workspace = (self.root / 'workspace').resolve()
        workspace.mkdir()
        script = self.root / 'archive.py'
        script.write_text('''import json,pathlib,shlex,sys
workspace=pathlib.Path(sys.argv[1])
run=workspace/'runs'/('research-'+'1'*32)
run.mkdir(parents=True)
(run/'trace.log').write_text('fixture trace')
(run/'research.json').write_text(json.dumps({'run_id':run.name,'task_id':'fixture',
 'status':'complete','error':'worker failed','harness_head':'b'*40}))
print('Watch live: tail -f '+shlex.quote(str(run/'trace.log')),flush=True)
''')
        records = {
            'bad_archive': {'command': [sys.executable, str(script), str(workspace)],
                            'workspace': str(workspace), 'console': str(self.root / 'archive.log'),
                            'status': 'prepared'},
            'later': {'command': [sys.executable, '-c', 'raise AssertionError("must not run")'],
                      'console': str(self.root / 'later.log'), 'status': 'prepared'},
        }
        plan = {'directory': str(self.root)}
        self.launch.process_group(records, self.root / 'state.json', max_parallel=1,
                                  after_exit=lambda label, row: self.launch.validate_completion(plan, label, row))
        self.assertEqual(records['bad_archive']['exit_code'], 0)
        self.assertEqual(records['bad_archive']['status'], 'failed')
        self.assertEqual(records['later']['status'], 'not_launched')
        self.assertTrue(Path(records['bad_archive']['archive_hashes']['path']).is_file())
        self.assertIn('durable research', records['bad_archive']['error'])


if __name__ == '__main__':
    unittest.main()
