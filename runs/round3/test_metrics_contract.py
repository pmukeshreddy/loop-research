"""Offline scoring-contract checks; no product imports, models, or network."""
from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import metrics as m


def review(version=2, score=0):
    evidence = [{'path': str(Path(__file__).resolve()), 'line': 1,
                 'note': 'Synthetic manual evidence for contract validation only'}]
    values = {
        'S2_gap_exposed': 0, 'S2_supplementary_unique_urls': 0,
        'S3_quote_exception_blocks': 0, 'S3_caught_printed_quote_failures': 0,
    }
    if version == 1:
        values.update(S1_preadd_validation=None,
                      posthoc_fullcell_validation_before_answer_ready=score)
    else:
        values['S1_pre_answer_ready_validation'] = score
    return {'run_id': 'synthetic', 'metrics': {
        key: {'value': value, 'reason': 'Unavailable boundary' if value is None else 'Cited observation',
              'evidence': evidence} for key, value in values.items()},
        'semantic_review': {'summary': 'Synthetic reviewer input', 'evidence': evidence}}


class ContractTests(unittest.TestCase):
    def test_default_preserves_legacy_null_and_separate_diagnostic(self):
        old = review(1, 1)
        default, _ = m.manual_metrics(old, 'synthetic')
        explicit, _ = m.manual_metrics(old, 'synthetic', contract='records-add-v1')
        self.assertEqual(default, explicit)
        self.assertIsNone(default['S1_preadd_validation']['value'])
        self.assertEqual(default['posthoc_fullcell_validation_before_answer_ready']['value'], 1)
        self.assertNotIn('S1_pre_answer_ready_validation', default)
        old['metrics']['S1_preadd_validation']['value'] = 1
        with self.assertRaisesRegex(m.AuditError, 'S1 must be N/A'):
            m.manual_metrics(old, 'synthetic')

    def test_v2_explicit_zero_is_observed_and_missing_score_fails(self):
        supplied = review(2, 0)
        values, _ = m.manual_metrics(supplied, 'synthetic', contract='answer-ready-v2')
        self.assertEqual(values['S1_pre_answer_ready_validation']['value'], 0)
        self.assertNotIn('reason', values['S1_pre_answer_ready_validation'])
        del supplied['metrics']['S1_pre_answer_ready_validation']
        with self.assertRaisesRegex(m.AuditError, 'Missing required manual'):
            m.manual_metrics(supplied, 'synthetic', contract='answer-ready-v2')

    def test_v2_binary_score_and_justified_unavailable_are_distinct(self):
        for score in (0, 1, None):
            with self.subTest(score=score):
                values, _ = m.manual_metrics(review(2, score), 'synthetic', contract='answer-ready-v2')
                self.assertEqual(values['S1_pre_answer_ready_validation']['value'], score)
        missing_reason = review(2, None)
        del missing_reason['metrics']['S1_pre_answer_ready_validation']['reason']
        with self.assertRaisesRegex(m.AuditError, 'explicit reason'):
            m.manual_metrics(missing_reason, 'synthetic', contract='answer-ready-v2')
        with self.assertRaisesRegex(m.AuditError, 'binary'):
            m.manual_metrics(review(2, 2), 'synthetic', contract='answer-ready-v2')

    def test_contracts_do_not_silently_accept_each_others_s1(self):
        with self.assertRaisesRegex(m.AuditError, 'Missing required manual'):
            m.manual_metrics(review(2, 1), 'synthetic')
        with self.assertRaisesRegex(m.AuditError, 'Missing required manual'):
            m.manual_metrics(review(1, 1), 'synthetic', contract='answer-ready-v2')
        mixed = review(2, 1)
        mixed['metrics']['S1_preadd_validation'] = review(1)['metrics']['S1_preadd_validation']
        with self.assertRaisesRegex(m.AuditError, 'different scoring contract'):
            m.manual_metrics(mixed, 'synthetic', contract='answer-ready-v2')

    def test_review_file_requires_v2_contract_receipt_and_legacy_default_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'review.json'
            data = {'source_commit': 'source', 'runs': {'A': review(1)}}
            path.write_text(json.dumps(data))
            self.assertEqual(m.load_manual([path], 'source')[0]['A']['run_id'], 'synthetic')
            data['runs']['A'] = review(2)
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(m.AuditError, 'contract'):
                m.load_manual([path], 'source', contract='answer-ready-v2')
            data['analysis_contract'] = 'answer-ready-v2'
            path.write_text(json.dumps(data))
            self.assertIn('A', m.load_manual([path], 'source', contract='answer-ready-v2')[0])
            with self.assertRaisesRegex(m.AuditError, 'contract'):
                m.load_manual([path], 'source')

    def test_new_output_names_actual_boundary_without_relabeling_legacy(self):
        new = m.contract_definition('answer-ready-v2')
        self.assertEqual(new['s1_metric'], 'S1_pre_answer_ready_validation')
        self.assertEqual(new['boundary'], 'first root submission setting answer["ready"] = True')
        self.assertIn('every required cell', new['definition'])
        self.assertIn('every cited URL', new['definition'])
        report = {'analysis_contract': new, 'limitations': 'Synthetic contract rendering.',
                  'control_aggregates': None, 'runs': {'A': {'metrics': {'S1_pre_answer_ready_validation': {'value': 0}}}}}
        output = m.markdown(report)
        self.assertIn('answer-ready-v2', output)
        self.assertIn('first root submission setting answer["ready"] = True', output)
        self.assertIn('S1_pre_answer_ready_validation', output)
        self.assertNotIn('S1_preadd_validation', output)
        old = m.contract_definition('records-add-v1')
        self.assertEqual(old['boundary'], 'first records.add (unavailable API)')
        self.assertEqual(old['s1_metric'], 'S1_preadd_validation')

    def test_v2_submission_witness_uses_first_successful_root_boundary(self):
        def end(line, depth, ready):
            return {'line': line, 'component': 'REPL', 'event': 'code.end',
                    'details': {'depth': depth, 'answer_ready': ready}}
        trace = [end(1, 1, True), end(2, 0, False), end(3, 0, True), end(4, 0, True)]
        values, _ = m.manual_metrics(review(2, 1), 'synthetic', contract='answer-ready-v2')
        proof = m.submission_boundary(trace, values, contract='answer-ready-v2')
        self.assertEqual(proof['line'], 3)
        self.assertEqual(values['S1_pre_answer_ready_validation']['value'], 1)
        with self.assertRaisesRegex(m.AuditError, 'No root submission'):
            m.submission_boundary(trace[:2], values, contract='answer-ready-v2')
        values, _ = m.manual_metrics(review(2, None), 'synthetic', contract='answer-ready-v2')
        self.assertIsNone(m.submission_boundary(trace[:2], values, contract='answer-ready-v2'))
        with self.assertRaisesRegex(m.AuditError, 'observed submission'):
            m.submission_boundary(trace, values, contract='answer-ready-v2')

    def test_new_contract_does_not_preselect_future_directional_claims(self):
        runs = {f'{arm}-{i}': {'metrics': {'S1_pre_answer_ready_validation': m.metric(score),
                                        'M1_late_requests': m.metric(score)}}
                for arm, score in [('B0', 0), ('B1-frozen', 1)] for i in (1, 2, 3)}
        report = m.aggregate_controls(runs, contract='answer-ready-v2')
        result = report['S1_pre_answer_ready_validation']
        self.assertEqual(result['delta'], 1)
        self.assertIsNone(result['directional_claim_allowed'])
        self.assertIsNone(report['M1_late_requests']['directional_claim_allowed'])
        self.assertIn('preregistration', result['directional_claim_reason'])
        self.assertTrue(m.aggregate_controls(runs)['M1_late_requests']['directional_claim_allowed'])


if __name__ == '__main__':
    unittest.main()
