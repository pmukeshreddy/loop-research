"""Synthetic parser checks only; never import/run the research product."""
import importlib.util
from pathlib import Path
import sys
import json
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('round3_metrics', HERE / 'metrics.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def event(line, component, kind, **details):
    return {'line': line, 'component': component, 'event': kind, 'details': details}


class MetricTests(unittest.TestCase):
    def test_m1_does_not_use_prior_discovery_or_child_repl_boundary(self):
        trace = [event(1,'tools.record_discovery','call.end',query='Q',entities=[],success=True),
            event(2,'tools.search','call.start',query='Q',span_id='s'),
            event(3,'tools.search','call.end',query='Q',span_id='s',success=True),
            event(4,'REPL','code.end',depth=1), event(5,'REPL','code.end',depth=0),
            event(6,'tools.record_discovery','call.end',query='Q',entities=['a'],success=True)]
        values, evidence = m.discovery_metrics(trace)
        self.assertEqual(values['M1_late_requests']['value'], 1)
        self.assertEqual(values['M1_late_fraction']['value'], 1)
        self.assertEqual(values['M2_corrected_empty_records']['value'], 1)
        self.assertEqual(evidence['requests'][0]['boundary_line'], 5)

    def test_exact_matching_and_duplicate_queries_share_interval_record(self):
        trace = [event(1,'tools.search','call.start',query='Q',span_id='a'),
            event(2,'tools.search','call.start',query='Q',span_id='b'),
            event(3,'tools.search','call.end',query='Q',span_id='a',success=True),
            event(4,'tools.search','call.end',query='Q',span_id='b',success=True),
            event(5,'tools.record_discovery','call.end',query='Q',entities=[],success=True),
            event(6,'REPL','code.end',depth=0)]
        values, proof = m.discovery_metrics(trace)
        self.assertEqual(values['M1_completed_requests']['value'], 2)
        self.assertEqual(values['M1_late_requests']['value'], 0)
        self.assertEqual(values['repeated_exact_search_requests']['value'], 0)
        self.assertEqual(len(proof['duplicate_matching_events']), 1)
        trace[4]['details']['query'] = 'q'
        self.assertEqual(m.discovery_metrics(trace)[0]['M1_late_requests']['value'], 2)

    def test_completed_search_without_root_boundary_is_na_not_zero(self):
        trace = [event(1,'tools.search','call.start',query='Q',span_id='a'),
            event(2,'tools.search','call.end',query='Q',span_id='a',success=True)]
        values, _ = m.discovery_metrics(trace)
        self.assertIsNone(values['M1_late_requests']['value'])
        self.assertIsNone(values['M1_late_fraction']['value'])

    def test_repeated_search_uses_start_after_success_and_counts_failed_repeat(self):
        trace = [event(1,'tools.search','call.start',query='Q',span_id='a'),
            event(2,'tools.search','call.end',query='Q',span_id='a',success=True),
            event(3,'tools.search','call.start',query='Q',span_id='b'),
            event(4,'tools.search','call.end',query='Q',span_id='b',error='failed'),
            event(5,'REPL','code.end',depth=0)]
        values, proof = m.discovery_metrics(trace)
        self.assertEqual(values['repeated_exact_search_requests']['value'], 1)
        self.assertEqual(proof['repeated_queries'][0]['start_line'], 3)

    def test_fetch_retry_excludes_concurrent_shared_admission(self):
        requests = [{'id':1,'url':'https://example.invalid/','source':'backend','status':'failed'},
            {'id':2,'url':'https://example.invalid/','source':'shared','status':'failed'},
            {'id':3,'url':'https://example.invalid/','source':'backend','status':'succeeded'}]
        trace = [event(1,'tools.fetch','cache',target='https://example.invalid/',cache='miss'),
            event(2,'tools.fetch','cache',target='https://example.invalid/',cache='shared'),
            event(3,'tools.fetch','call.end',url='https://example.invalid/',success=False),
            event(4,'tools.fetch','cache',target='https://example.invalid/',cache='miss')]
        values, proof = m.fetch_metrics(trace, {'fetches':requests})
        self.assertEqual(values['fetch_repeats_after_failure']['value'], 1)
        self.assertEqual(values['fetch_repeats_per_failed_url']['value'], 1)
        self.assertEqual(proof['repeats_after_failure'][0]['request_id'], 3)

    def test_invalid_search_query_error_is_retained_without_crashing_counts(self):
        trace=[event(1,'tools.search','call.start',query={'invalid':'query'},span_id='bad'),
               event(2,'tools.search','call.end',query={'invalid':'query'},span_id='bad',error='Expected string'),
               event(3,'REPL','code.end',depth=0,error='Expected string')]
        values,proof=m.discovery_metrics(trace)
        self.assertEqual(values['repeated_exact_search_requests']['value'],0)
        self.assertEqual(values['invalid_search_query_requests']['value'],1)
        self.assertEqual(proof['all_search_completions'][0]['details']['error'],'Expected string')

    def test_no_failed_fetch_denominator_is_na(self):
        values, _ = m.fetch_metrics([], {'fetches': []})
        self.assertEqual(values['fetch_repeats_after_failure']['value'], 0)
        self.assertIsNone(values['fetch_repeats_per_failed_url']['value'])

    def test_quote_checks_every_required_cell_and_every_source(self):
        output = {'rows':[{'cells':{'x':{'value':'a','quote':'exact','sources':['u','v']}}}]}
        value, proof = m.citation_metrics(output, ['x','missing'], {'fetched': {'u':['exact'], 'v':['wrong']}})
        self.assertEqual(value['S4_citation_violation_cells']['value'], 2)
        self.assertEqual(len(proof), 2)

    def test_aggregate_na_denominators_and_strict_spread(self):
        runs = {f'{arm}-{i+1}': {'metrics': {'x': m.metric(value, reason='missing' if value is None else None)}}
                for arm, values in [('B0',[0,1,None]),('B1-frozen',[1,2,None])] for i,value in enumerate(values)}
        row = m.aggregate_controls(runs)['x']
        self.assertEqual(row['B0']['defined_runs'], 2)
        self.assertEqual(row['delta'], 1)
        self.assertEqual(row['spread'], 1)
        self.assertFalse(row['abs_delta_exceeds_spread'])

    def test_manual_missing_fields_fail(self):
        with self.assertRaisesRegex(m.AuditError,'manual'):
            m.manual_metrics({'run_id':'id','metrics':{},'semantic_review':{}},'id')

    def test_defined_metric_does_not_claim_it_is_unavailable(self):
        self.assertEqual(m.metric(42,reason='Unavailable'), {'value':42})
        self.assertEqual(m.metric(None,reason='Unavailable'), {'value':None,'reason':'Unavailable'})

    def test_repeated_empty_discovery_events_are_counted_individually(self):
        trace=[event(i,'tools.record_discovery','call.end',query='Q',entities=[],success=True) for i in range(1,4)]
        trace.append(event(4,'tools.record_discovery','call.end',query='Q',entities=['found'],success=True))
        self.assertEqual(m.discovery_metrics(trace)[0]['M2_corrected_empty_records']['value'],3)

    def test_batch_wrapper_does_not_duplicate_child_searches(self):
        trace=[event(1,'tools.search','call.start',query='A',span_id='a'),
               event(2,'tools.search','call.start',query='B',span_id='b'),
               event(3,'tools.search','call.end',query='A',span_id='a',success=True),
               event(4,'tools.search','call.end',query='B',span_id='b',success=True),
               event(5,'tools.search_many','call.end',queries=['A','B'],success=True),
               event(6,'tools.record_discovery','call.end',query='A',entities=[],success=True),
               event(7,'REPL','code.end',depth=0)]
        values,_=m.discovery_metrics(trace)
        self.assertEqual(values['M1_completed_requests']['value'],2)
        self.assertEqual(values['M1_late_requests']['value'],1)

    def test_literal_s1_stays_null_and_conditional_gap_is_na(self):
        evidence=[{'path':str(Path(__file__).resolve()),'line':1,'note':'Synthetic explicit reviewer evidence'}]
        review={'run_id':'test','metrics':{key:{'value':None if key=='S1_preadd_validation' else 0,
                    'reason':'Literal boundary unavailable' if key=='S1_preadd_validation' else 'Observed zero',
                    'evidence':evidence} for key in m.MANUAL},
                'semantic_review':{'summary':'Synthetic review','evidence':evidence}}
        values,_=m.manual_metrics(review,'test')
        self.assertIsNone(values['S1_preadd_validation']['value'])
        self.assertIsNone(values['S2_supplementary_unique_urls_conditional']['value'])
        self.assertEqual(values['S2_gap_exposed']['review_reason'],'Observed zero')
        review['metrics']['S1_preadd_validation']['value']=1
        with self.assertRaisesRegex(m.AuditError,'S1 must be N/A'):
            m.manual_metrics(review,'test')

    def test_completed_archive_sizes_equal_frozen_audit_method(self):
        # Disk-only independent calculation over the already completed A/SI archives.
        directory=HERE/'cohorts/final'
        for label in ('A','SI'):
            with self.subTest(label=label):
                audited=json.loads((directory/'audits'/f'{label}.audit.json').read_text())
                task=Path(audited['task_path'])
                evidence=json.loads((task/'evidence.json').read_text())
                pages=[text for texts in evidence['fetched'].values() for text in texts]
                self.assertEqual(sum(map(len,pages)),audited['overlap']['total_chars'])
                full=(directory/'audits'/f'{label}.largest_root_prompt.txt').read_bytes().decode()
                self.assertEqual(len(full),audited['largest_prompt']['total'])
                self.assertEqual(m.digest(full),audited['largest_prompt']['sha256'])
                self.assertEqual(sum(audited['largest_prompt']['parts'].values()),len(full))
                trajectory=[json.loads(line) for line in (task/'trajectory.jsonl').read_text().splitlines()]
                roots=[row['prompt'] for row in trajectory if row.get('type')=='model' and row.get('purpose')=='root']
                # INSTRUCTION alone cannot create page matches in these archives; include its exact archived prefix.
                first=roots[0]
                prefix=full[:full.index('<system>')]
                self.assertTrue(first.startswith('<system>'))
                grams={text[i:i+50] for text in pages for i in range(max(0,len(text)-49))}
                present=set()
                for root in roots:
                    root=prefix+root
                    present.update(root[i:i+50] for i in range(max(0,len(root)-49)) if root[i:i+50] in grams)
                covered=0
                for text in pages:
                    mask=bytearray(len(text))
                    for i in range(max(0,len(text)-49)):
                        if text[i:i+50] in present:
                            mask[i:i+50]=b'1'*50
                    covered+=sum(bool(value) for value in mask)
                self.assertEqual(covered,audited['overlap']['covered_chars'])
                self.assertEqual(covered/sum(map(len,pages)),audited['overlap']['fraction'])
                self.assertEqual(sum(row['input_chars'] for row in audited['subcalls']),audited['subcall_input_chars'])

    def test_identity_aliases_are_explicit_and_raw_difference_preserved(self):
        current = {'rows':[{'cells':{'name':{'value':'Variant'},'year':{'value':'2020'}}}]}
        prior = {'rows':[{'cells':{'name':{'value':'Canonical'},'year':{'value':'2020'}}}]}
        values, proof = m.identity_metrics(current, prior, ['name','year'], [{'field':'name','variant':'Variant','canonical':'Canonical'}])
        self.assertEqual(values['Q1_identity_symmetric_difference_raw']['value'],2)
        self.assertEqual(values['Q1_identity_symmetric_difference']['value'],0)
        self.assertTrue(proof['aliases'])


if __name__ == '__main__':
    unittest.main()
