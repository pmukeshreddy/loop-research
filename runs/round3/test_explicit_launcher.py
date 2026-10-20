"""Offline explicit-launch gates; no research, clone, rollback, model, or web calls."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class ExplicitLauncherTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((HERE / 'run_explicit.py').is_file(), 'The explicit launcher must exist')
        spec = importlib.util.spec_from_file_location('round3_explicit_test', HERE / 'run_explicit.py')
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory(prefix='round3-explicit-offline-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plan = {'source_commit': 'a' * 40, 'arms': ['A', 'SI', 'B1', 'B0-1']}
        self.state = {'source_commit': 'a' * 40,
            'phases': {'a_si': {'status': 'complete'}, 'b': {'status': 'complete'}},
            'arms': {label: {'status': 'complete', 'exit_code': 0, 'source_commit': 'a' * 40,
                             'record': {'status': 'complete', 'error': None}}
                     for label in self.plan['arms']}}

    def test_gate_requires_every_main_arm_and_b_phase_to_finish_successfully(self):
        self.module.explicit_gate(self.plan, self.state)
        for state in (
            {**self.state, 'phases': {'a_si': {'status': 'complete'}, 'b': {'status': 'running'}}},
            {**self.state, 'source_commit': 'b' * 40},
        ):
            with self.assertRaises(ValueError):
                self.module.explicit_gate(self.plan, state)
        for label in self.plan['arms']:
            state = copy.deepcopy(self.state)
            state['arms'][label]['status'] = 'running'
            with self.assertRaises(ValueError):
                self.module.explicit_gate(self.plan, state)
            del state['arms'][label]
            with self.assertRaises(ValueError):
                self.module.explicit_gate(self.plan, state)

    def test_gate_rejects_exit_zero_with_durable_failure(self):
        self.state['arms']['B1']['record']['error'] = 'worker failed'
        with self.assertRaisesRegex(ValueError, 'completed successfully'):
            self.module.explicit_gate(self.plan, self.state)

    def test_premature_attempt_is_durable_and_cannot_overwrite_itself(self):
        self.state['phases']['b']['status'] = 'running'
        (self.root / 'plan.json').write_text(json.dumps(self.plan))
        (self.root / 'execution.json').write_text(json.dumps(self.state))
        with self.assertRaisesRegex(ValueError, 'B phase'):
            self.module.execute(self.root)
        target = self.root / 'explicit_execution.json'
        first = target.read_bytes()
        failure = json.loads(first)
        self.assertEqual(failure['status'], 'failed')
        self.assertEqual(failure['classification'], self.module.CLASSIFICATION)
        self.assertIn('ended_at', failure)
        self.assertFalse((self.root / 'workspaces').exists())
        with self.assertRaisesRegex(ValueError, 'already attempted'):
            self.module.execute(self.root)
        self.assertEqual(target.read_bytes(), first)

    def test_request_and_saved_task_have_exact_normal_cli_identity(self):
        request = self.module.launch.load(HERE / 'explicit_request.json')
        task = self.module.task_for(request)
        self.assertEqual(task, self.module.launch.load(HERE / 'explicit_task.json'))
        from loop_research.archive import digest
        expected_id = digest({key: request[key] for key in ('question', 'columns', 'keys', 'language')})[:24]
        self.assertEqual(task['task_id'], expected_id)
        self.assertEqual(task['benchmark'], 'research')
        self.assertIsNone(task['as_of_date'])
        self.assertEqual(request['base'], self.module.launch.BASE)
        self.assertEqual(request['classification'], self.module.CLASSIFICATION)


if __name__ == '__main__':
    unittest.main()
