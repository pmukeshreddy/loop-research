#!/usr/bin/env python3
"""Read-only preregistered Round 3 metrics from completed archives and cited reviews."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
import sys
import unicodedata
from urllib.parse import urlsplit, urlunsplit

from control_audit import AuditError, CONTROLS, digest, file_record, read, read_lines, require, verify_file, verify_inventory

LABELS = ('A', 'SI', 'B1', *CONTROLS)
MANUAL = ('S1_preadd_validation', 'S2_gap_exposed', 'S2_supplementary_unique_urls',
          'S3_quote_exception_blocks', 'S3_caught_printed_quote_failures',
          'posthoc_fullcell_validation_before_answer_ready')
DEFAULT_CONTRACT = 'records-add-v1'
CONTRACTS = {
    'records-add-v1': {
        'id': 'records-add-v1', 'version': 1, 's1_metric': 'S1_preadd_validation',
        'boundary': 'first records.add (unavailable API)',
        'definition': 'Literal S1 remains N/A because records.add is not an exposed API. The separate posthoc_fullcell_validation_before_answer_ready measure cannot count as preregistered success.',
        'manual_fields': MANUAL,
    },
    'answer-ready-v2': {
        'id': 'answer-ready-v2', 'version': 2, 's1_metric': 'S1_pre_answer_ready_validation',
        'boundary': 'first root submission setting answer["ready"] = True',
        'definition': 'Binary 1 only when executed code before the first root submission setting answer["ready"] = True verifies a nonempty value, source list, and quote for every required cell in the nonempty candidate row set submitted, and verifies exact quote membership in retained original fetched text for every cited URL. Locate the submitting block using the first depth-0 REPL code.end event with answer_ready=true; checks must execute before the readiness assignment within that block or an earlier block and cover the actual submitted version. An earlier failed guard followed by repairs and a successful complete guard before submission can score 1. Partial checks, checks of an earlier candidate version, checks after submission, and unsupported assurances score 0. Cite executed code, output, coverage, and submission. If no root submission exists, report N/A with evidence and a reason; missing review evidence fails extraction. This measures an observed guard, not causal benefit.',
        'manual_fields': ('S1_pre_answer_ready_validation', *MANUAL[1:5]),
    },
}
DEFINITIONS = {
 'M1': 'Successful individual tools.search call.end events, including batch children/cache/shared calls. Match original exact query to successful discovery strictly after search completion and no later than the first depth-0 REPL code.end. Each completed request counted once. A single matching discovery can satisfy duplicate requests in its interval; shared matches are disclosed. Missing later root boundary makes late count/fraction N/A, not zero.',
 'M2': 'Each successful empty discovery event counted once if a later successful nonempty discovery has the identical original query. Uncorrected empties are not classified as wrong.',
 'search_repeats': 'Individual tools.search call.start after the first successful call.end for exactly the same original query, independent of k. Includes subsequent failed and cached requests. Case/whitespace are not normalized. Concurrent duplicates starting before first success are not reuse opportunities.',
 'fetch_repeats': 'Each request admission (tools.fetch cache event, bound in order to evidence request ID) after the first failed tools.fetch call.end for its exact stored URL. URL keys are product-normalized HTTP URLs. Concurrent shared requests admitted before first failure are excluded. Per-failed-URL denominator includes each distinct URL with final status failed; zero denominator is N/A. Cancelled/pending requests are separately retained, not silently called failed.',
 'model_calls': 'Unique durable backend dispatch call IDs, unioned with completed call records; every role/purpose and retries included. Retry means attempt > 0. Completion-only and missing-completion records are disclosed. Role counts are purposes root/search/sub/refine; other purposes remain separate and contribute to total.',
 'errors': 'Every trace event with a nonempty details.error is counted and retained, including propagated copies and expected HTTP/validation failures. REPL error blocks are code.end events with error. Non-error unsuccessful component events, evidence failures and model failures are also retained separately.',
 'S4': 'For each final row and every required column, violation if cell/quote/sources are missing or empty, retained text for any cited URL is absent, or the exact nonempty quote occurs in none of that URL\'s retained original texts. One violating cell counted once regardless of number of bad URLs. No whitespace/case normalization.',
 'identity': 'Declared task key columns; Unicode NFKD, casefold, and alphanumeric-only comparison as in the prior saved quality comparison. Raw set symmetric difference and duplicate-key counts are retained. Only explicitly cited alias mappings may change adjusted identity scores.',
 'page_root': 'Use frozen read-only archive auditor output: sum all retained fetched text characters, largest verified backend root input including INSTRUCTION, ratio page/root, exact case/whitespace-sensitive 50-character-gram covered character fraction. No title/URL exclusions and no threshold changes. Full root partition and individual subcall inputs retained.',
 'manual': 'S1 is N/A: preregistration named nonexistent records.add API. The separately labeled posthoc_fullcell_validation_before_answer_ready diagnostic is excluded from directional prediction success. S2 gap exposure/counts and S3 quote-specific classification require cited independent review. S3 caught/printed counts are individual failure records actually printed, retaining repeated observations.',
 'aggregation': 'Each scalar metric: individual controls, count of defined runs, mean, min, max, range. Delta=mean(frozen)-mean(B0). Spread=max(within-arm max-min). Exceeds iff abs(delta)>spread, strictly. N/A contributes no zero. Three repeats are not statistical evidence.',
}


def contract_definition(contract=DEFAULT_CONTRACT):
    require(contract in CONTRACTS, 'Unknown analysis scoring contract: ' + str(contract))
    return {key: value for key, value in CONTRACTS[contract].items() if key != 'manual_fields'}


def metric(value, *, reason=None, **details):
    if value is None:
        require(bool(reason), 'N/A metric needs an explicit reason')
    else:
        require(type(value) in (int, float) and math.isfinite(value), 'Metric must be finite numeric or N/A')
    return {'value': value, **({'reason': reason} if value is None and reason else {}), **details}


def trace_rows(path):
    return [{**row, 'line': line} for line, row in read_lines(path)]


def selected(trace, component, event):
    return [row for row in trace if row['component'] == component and row['event'] == event]


def successful(row):
    return row['details'].get('success') is True and not row['details'].get('error')


def discovery_metrics(trace):
    searches = [row for row in selected(trace, 'tools.search', 'call.end') if successful(row)]
    records = [row for row in selected(trace, 'tools.record_discovery', 'call.end') if successful(row)]
    boundaries = [row for row in selected(trace, 'REPL', 'code.end') if row['details'].get('depth') == 0]
    starts = {row['details']['span_id']: row for row in selected(trace, 'tools.search', 'call.start')}
    requests, shared = [], defaultdict(list)
    for search in searches:
        query, end = search['details']['query'], search['line']
        boundary = next((row for row in boundaries if row['line'] > end), None)
        matches = [row['line'] for row in records if row['details']['query'] == query and end < row['line'] <= boundary['line']] if boundary else []
        requests.append({'query': query, 'span_id': search['details'].get('span_id'), 'completion_line': end,
                         'start_line': starts.get(search['details'].get('span_id'), {}).get('line'),
                         'boundary_line': boundary['line'] if boundary else None, 'discovery_lines': matches,
                         'late': not bool(matches) if boundary else None})
        for line in matches:
            shared[line].append(end)
    unknown = sum(row['late'] is None for row in requests)
    late = None if unknown else sum(row['late'] for row in requests)
    late_reason = 'No subsequent root REPL end for ' + str(unknown) + ' completed searches' if unknown else None
    corrected = []
    for record in records:
        if record['details']['entities']:
            continue
        later = [row['line'] for row in records if row['line'] > record['line'] and
                 row['details']['query'] == record['details']['query'] and row['details']['entities']]
        if later:
            corrected.append({'empty_line': record['line'], 'query': record['details']['query'], 'later_nonempty_lines': later})
    first_success = {}
    for row in searches:
        first_success.setdefault(row['details']['query'], row['line'])
    repeats = [{'query': row['details']['query'], 'start_line': row['line'], 'span_id': row['details']['span_id'],
                'first_success_line': first_success[row['details']['query']]}
               for row in starts.values() if isinstance(row['details']['query'],str) and
               row['details']['query'] in first_success and row['line'] > first_success[row['details']['query']]]
    values = {'M1_completed_requests': metric(len(requests)), 'M1_late_requests': metric(late, reason=late_reason),
              'M1_late_fraction': metric(late / len(requests) if requests and late is not None else None,
                  reason=late_reason or ('No completed searches (zero denominator)' if not requests else None)),
              'M2_corrected_empty_records': metric(len(corrected)), 'repeated_exact_search_requests': metric(len(repeats)),
              'invalid_search_query_requests': metric(sum(not isinstance(row['details']['query'],str) or
                  not row['details']['query'].strip() for row in starts.values())),
              'search_cache_hit_requests': metric(sum(row['details'].get('cache') == 'hit' for row in selected(trace,'tools.search','cache'))),
              'search_shared_requests': metric(sum(row['details'].get('cache') == 'shared' for row in selected(trace,'tools.search','cache')))}
    return values, {'requests': requests, 'corrected_empty_events': corrected, 'repeated_queries': repeats,
                   'duplicate_matching_events': [{'discovery_line': line, 'search_completion_lines': rows} for line, rows in shared.items() if len(rows)>1],
                   'all_discovery_events': records, 'all_search_completions': selected(trace,'tools.search','call.end')}


def normalized_url(url):
    parts = urlsplit(url.strip())
    require(parts.scheme.lower() in ('http','https') and parts.hostname and not parts.username and not parts.password
            and not any(c.isspace() for c in url), 'Invalid fetch URL in trace')
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or '/', parts.query, ''))


def fetch_metrics(trace, evidence):
    requests = evidence.get('fetches', [])
    admissions = selected(trace, 'tools.fetch', 'cache')
    require(len(requests) == len(admissions), 'Fetch request/cache event inventory mismatch')
    first_failure = {}
    for row in selected(trace, 'tools.fetch', 'call.end'):
        if row['details'].get('success') is False or row['details'].get('error'):
            try:
                url = normalized_url(row['details']['url'])
            except (AuditError, ValueError, AttributeError):
                continue  # Invalid URL has no admitted request; remains in full error evidence.
            first_failure.setdefault(url, row['line'])
    failed_urls = sorted({row['url'] for row in requests if row['status'] == 'failed'})
    require(all(url in first_failure for url in failed_urls), 'Failed admitted fetch has no failed completion trace')
    bindings, repeats = [], []
    for index, (request, admission) in enumerate(zip(requests, admissions), 1):
        expected_cache = {'backend':'miss','cache':'hit','shared':'shared'}[request['source']]
        require(request['id'] == index and request['url'] == admission['details']['target'] and
                admission['details']['cache'] == expected_cache, 'Fetch admission/request binding mismatch')
        row = {'request_id': request['id'], 'url': request['url'], 'admission_line': admission['line'],
               'source': request['source'], 'status': request['status'], 'first_failure_line': first_failure.get(request['url'])}
        bindings.append(row)
        if request['url'] in first_failure and admission['line'] > first_failure[request['url']]:
            repeats.append(row)
    per_url = [{'url': url, 'repeat_count': sum(row['url'] == url for row in repeats),
                'first_failure_line': first_failure[url], 'request_ids': [row['request_id'] for row in repeats if row['url'] == url]}
               for url in failed_urls]
    values = {'successful_unique_fetched_urls':metric(len({row['url'] for row in requests if row['status']=='succeeded'})),
              'fetch_requests':metric(len(requests)), 'failed_fetch_requests':metric(sum(row['status']=='failed' for row in requests)),
              'cancelled_fetch_requests':metric(sum(row['status']=='cancelled' for row in requests)),
              'pending_fetch_requests':metric(sum(row['status']=='pending' for row in requests)),
              'distinct_failed_fetch_urls':metric(len(failed_urls)), 'fetch_repeats_after_failure':metric(len(repeats)),
              'fetch_repeats_per_failed_url':metric(len(repeats)/len(failed_urls) if failed_urls else None,
                  reason='No failed URLs (zero denominator)' if not failed_urls else None),
              'fetch_cache_hit_requests':metric(sum(row['source']=='cache' for row in requests)),
              'fetch_shared_requests':metric(sum(row['source']=='shared' for row in requests))}
    return values, {'admission_bindings':bindings, 'repeats_after_failure':repeats, 'repeats_per_failed_url':per_url,
                    'all_requests':requests, 'all_evidence_failures':evidence.get('failures',[])}


def citation_metrics(output, columns, evidence):
    violations = []
    for index, row in enumerate(output['rows']):
        for field in columns:
            cell = row.get('cells',{}).get(field)
            reasons, urls = [], []
            if not isinstance(cell,dict):
                reasons.append('Missing required cell')
            else:
                quote, sources = cell.get('quote'), cell.get('sources')
                if not isinstance(quote,str) or not quote.strip():
                    reasons.append('Missing/empty quote')
                if not isinstance(sources,list) or not sources:
                    reasons.append('Missing/empty sources')
                else:
                    for url in sources:
                        texts = evidence.get('fetched',{}).get(url,[]) if isinstance(url,str) else []
                        okay = bool(isinstance(quote,str) and quote.strip() and any(quote in text for text in texts))
                        urls.append({'url':url,'retained_texts':len(texts),'exact_quote':okay})
                        if not okay:
                            reasons.append('Quote absent from retained text for ' + str(url))
            if reasons:
                violations.append({'row':index,'column':field,'cell':cell,'reasons':reasons,'urls':urls})
    return {'S4_citation_violation_cells':metric(len(violations)),
            'required_cells':metric(len(output['rows'])*len(columns))}, violations


def normalize(value):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(value)).casefold() if c.isalnum())


def identity_metrics(output, prior, fields, aliases):
    mapping = {(row['field'],normalize(row['variant'])):normalize(row['canonical']) for row in aliases}
    def keys(data, mapped=False):
        return [tuple(mapping.get((field,normalize(row['cells'][field]['value'])),normalize(row['cells'][field]['value']))
                       if mapped else normalize(row['cells'][field]['value']) for field in fields) for row in data['rows']]
    raw, old = keys(output), keys(prior)
    current, previous = keys(output,True), keys(prior,True)
    return {'Q1_identity_symmetric_difference_raw':metric(len(set(raw)^set(old))),
            'Q1_identity_symmetric_difference':metric(len(set(current)^set(previous))),
            'Q1_duplicate_output_identities':metric(len(current)-len(set(current)))}, {
            'fields':fields,'aliases':aliases,'raw_only_current':sorted(set(raw)-set(old)),'raw_only_prior':sorted(set(old)-set(raw)),
            'only_current':sorted(set(current)-set(previous)),'only_prior':sorted(set(previous)-set(current)),'prior_rows':len(previous)}


def cited_evidence(items):
    require(isinstance(items,list) and items, 'Manual metric requires cited evidence')
    result = []
    for item in items:
        path = Path(item['path']).resolve()
        require(bool(item.get('note')), 'Manual evidence requires a note')
        if 'file' in item:
            verify_file(item['file'], 'Previously bound review evidence')
        if item.get('line') is not None:
            require(type(item['line']) is int and 1 <= item['line'] <= len(path.read_text().splitlines()), 'Manual evidence line invalid')
        result.append({**item,'file':file_record(path)})
    return result


def manual_metrics(review, run_id, *, contract=DEFAULT_CONTRACT):
    definition = contract_definition(contract)
    required = CONTRACTS[contract]['manual_fields']
    require(review.get('run_id') == run_id, 'Manual review run identity mismatch')
    values = dict(review.get('metrics',{}))
    alias = 'fullcell_validation_before_answer_ready'
    if alias in values:
        require('posthoc_' + alias not in values, 'Duplicate post-hoc diagnostic aliases')
        values['posthoc_' + alias] = values.pop(alias)
    require(all(key in values for key in required), 'Missing required manual metrics: ' + ', '.join(key for key in required if key not in values))
    other_s1 = {'S1_preadd_validation', 'S1_pre_answer_ready_validation'} - {definition['s1_metric']}
    require(not (other_s1 & values.keys()), 'S1 metric belongs to a different scoring contract')
    for key, value in values.items():
        require(value.get('value') is None or (type(value['value']) is int and value['value'] >= 0), 'Manual count must be nonnegative integer or N/A')
        if key in ('S1_preadd_validation','S1_pre_answer_ready_validation','S2_gap_exposed','posthoc_fullcell_validation_before_answer_ready'):
            require(value.get('value') in (None,0,1), 'Manual binary metric outside 0/1')
        values[key] = {**metric(value.get('value'),reason=value.get('reason')), 'review_reason':value.get('reason'),
                       'evidence':cited_evidence(value.get('evidence'))}
    if contract == DEFAULT_CONTRACT:
        require(values['S1_preadd_validation']['value'] is None, 'Literal preregistered records.add boundary is unavailable; S1 must be N/A')
    exposed, count = values['S2_gap_exposed']['value'], values['S2_supplementary_unique_urls']['value']
    require(exposed != 0 or count == 0, 'No exposed gap requires zero raw supplementary URLs')
    values['S2_supplementary_unique_urls_conditional'] = metric(count if exposed == 1 else None,
        reason='No exposed gap; conditional prediction not exercised' if exposed == 0 else 'Gap exposure unavailable' if exposed is None else values['S2_supplementary_unique_urls'].get('reason'))
    semantic = dict(review.get('semantic_review',{}))
    require(bool(semantic.get('summary')), 'Missing semantic review summary')
    semantic['evidence'] = cited_evidence(semantic.get('evidence'))
    for key, value in semantic.get('counts',{}).items():
        values['semantic_' + key] = {**metric(value.get('value'),reason=value.get('reason')), 'evidence':cited_evidence(value.get('evidence'))}
    return values, semantic


def aggregate_controls(runs, *, contract=DEFAULT_CONTRACT):
    contract_definition(contract)
    require(all(label in runs for label in CONTROLS), 'All six controls required for aggregate table')
    keys = sorted({key for label in CONTROLS for key in runs[label]['metrics']})
    result = {}
    for key in keys:
        row = {'individual':{label:runs[label]['metrics'].get(key,metric(None,reason='Metric not provided by this manual review')) for label in CONTROLS}}
        for arm in ('B0','B1-frozen'):
            values = [row['individual'][f'{arm}-{i}']['value'] for i in range(1,4)]
            defined = [value for value in values if value is not None]
            row[arm] = {'defined_runs':len(defined),'total_runs':3,'mean':statistics.mean(defined) if defined else None,
                        'min':min(defined) if defined else None,'max':max(defined) if defined else None,
                        'range':max(defined)-min(defined) if defined else None}
        if row['B0']['mean'] is not None and row['B1-frozen']['mean'] is not None:
            delta = row['B1-frozen']['mean']-row['B0']['mean']
            spread = max(row['B1-frozen']['range'],row['B0']['range'])
            row.update(delta=delta,spread=spread,abs_delta_exceeds_spread=abs(delta)>spread)
        else:
            row.update(delta=None,spread=None,abs_delta_exceeds_spread=None,reason='At least one arm has no defined runs')
        row['directional_claim_allowed'] = key in {'M1_late_requests','M1_late_fraction','M2_corrected_empty_records',
            'S2_supplementary_unique_urls_conditional','S3_quote_exception_blocks','S4_citation_violation_cells',
            'Q1_output_rows','Q1_self_check_issues','Q1_uncited_cells','Q1_identity_symmetric_difference'}
        if contract != DEFAULT_CONTRACT:
            row['directional_claim_allowed'] = None
            row['directional_claim_reason'] = 'Consult this cohort’s committed preregistration; the scoring contract does not select directional predictions.'
        result[key] = row
    return result


def load_manual(paths, source, *, contract=DEFAULT_CONTRACT):
    contract_definition(contract)
    result, receipts = {}, []
    for path in paths:
        data = read(path)
        require(data['source_commit'] == source, 'Manual review source commit mismatch')
        require(data.get('analysis_contract', DEFAULT_CONTRACT) == contract, 'Manual review scoring contract mismatch')
        require(not (set(result)&set(data['runs'])), 'Duplicate manual run review across files')
        result.update(data['runs']); receipts.append(file_record(path))
    return result, receipts


def submission_boundary(trace, values, *, contract=DEFAULT_CONTRACT):
    contract_definition(contract)
    if contract == DEFAULT_CONTRACT:
        return None
    boundary = next((row for row in selected(trace, 'REPL', 'code.end')
                     if row['details'].get('depth') == 0 and row['details'].get('answer_ready') is True), None)
    score = values['S1_pre_answer_ready_validation']['value']
    require(boundary is not None or score is None, 'No root submission exists; S1 must be justified N/A')
    require(boundary is None or score is not None, 'S1 requires an explicit 0/1 review for an observed submission')
    return boundary


def archive_metrics(label, arm, audit_path, review, reference, aliases, *, contract=DEFAULT_CONTRACT):
    require(arm.get('status')=='complete' and arm.get('exit_code')==0 and arm.get('source_unchanged') is True,
            'Metrics require completed run with source verification: ' + label)
    run=Path(arm['run_path']); task=run/arm['task_id']
    inventory=verify_inventory(arm['archive_hashes'],run)
    require(read(run/'research.json') == arm['record'], 'Archive completion record differs from launcher')
    audited=read(audit_path)
    require(audited['run_id']==arm['run_id'] and Path(audited['task_path']).resolve()==task.resolve(), 'Audit run/task identity mismatch')
    for record in audited['source_files']:
        verify_file(record,'Audit source')
    trace=trace_rows(run/'trace.jsonl'); evidence=read(task/'evidence.json'); output=read(task/'output.json')
    specification=read(task/'task.json')['spec']; checks=read(task/'self_check.json'); agent=read(task/'agent_result.json')
    values, discovery=discovery_metrics(trace)
    more, fetches=fetch_metrics(trace,evidence); values.update(more)
    more, violations=citation_metrics(output,specification['columns'],evidence); values.update(more)
    calls={row['call_id']:row for _,row in read_lines(task/'codex_calls.jsonl')}
    attempts={row['call_id']:row for path in (task/'codex_attempts').glob('*.json') for row in [read(path)]}
    combined={**calls,**attempts}; role_counts=Counter(row['purpose'] for row in combined.values())
    values.update({'model_calls_'+role:metric(role_counts[role]) for role in ('root','search','sub','refine')})
    values.update(model_calls_total=metric(len(combined)), model_calls_other=metric(sum(count for role,count in role_counts.items() if role not in ('root','search','sub','refine'))),
                  model_retries=metric(sum(row.get('attempt',0)>0 for row in combined.values())),
                  model_completion_records=metric(len(calls)), model_missing_completion_records=metric(len(set(attempts)-set(calls))))
    starts=selected(trace,'Research','run.start'); ends=selected(trace,'Research','run.end')
    wall=(datetime.fromisoformat(ends[-1]['timestamp'])-datetime.fromisoformat(starts[0]['timestamp'])).total_seconds() if starts and ends else None
    errors=[row for row in trace if row['details'].get('error')]
    failures=[row for row in trace if row['details'].get('success') is False and not row['details'].get('error')]
    repl_errors=[row for row in selected(trace,'REPL','code.end') if row['details'].get('error')]
    values.update(Q1_output_rows=metric(len(output['rows'])), Q1_self_check_issues=metric(len(checks['issues'])),
                  Q1_uncited_cells=metric(len({item.split(':',1)[0] for item in agent['uncited']})),
                  stalled_search_signals=metric(sum(row['type']=='stalled_search' for row in checks['signals'])),
                  repl_error_blocks=metric(len(repl_errors)), component_error_events=metric(len(errors)),
                  component_unsuccessful_events_without_error=metric(len(failures)),
                  run_wall_seconds=metric(wall,reason='Complete Research run timing unavailable' if wall is None else None))
    page_chars=sum(len(text) for texts in evidence.get('fetched',{}).values() for text in texts)
    require(audited['overlap']['total_chars']==page_chars, 'Readable text total differs from full audit')
    largest=audited['largest_prompt']; overlap=audited['overlap']
    values.update(fetched_readable_characters=metric(page_chars),
                  largest_root_prompt_characters=metric(largest['total'],reason=largest.get('unavailable_reason')),
                  fetched_to_largest_root_ratio=metric(audited['fetched_text_to_largest_root_ratio'],reason='Largest root prompt unavailable or zero' if audited['fetched_text_to_largest_root_ratio'] is None else None),
                  page_root_50gram_overlap_fraction=metric(overlap['fraction'],reason=overlap.get('unavailable_reason') or ('No fetched characters (zero denominator)' if not page_chars else None)))
    for key in ('system','question_and_columns','other_task_instructions','harness','code','repl_output','wrappers'):
        values['largest_root_partition_'+key]=metric(largest.get('parts',{}).get(key),reason=largest.get('partition_unavailable_reason') or 'Root partition unavailable')
    subcalls=audited['subcalls']
    for key in ('subcall_count','subcall_input_chars','subcall_backend_chars','subcall_prompt_chars','subcall_schema_chars'):
        values[key]=metric(audited.get(key),reason=audited.get('subcalls_unavailable_reason') or 'Subcall sizes unavailable')
    for field in ('input_chars','prompt_input_chars','schema_input_chars','backend_chars'):
        nums=[row[field] for row in subcalls if row.get(field) is not None]
        for suffix, fn in [('min',min),('max',max),('mean',statistics.mean)]:
            values['subcall_'+field+'_'+suffix]=metric(fn(nums) if nums else None,reason='No measured subcalls' if not nums else None)
    prior=read(reference/'output.json')
    require(read(reference/'task.json')['spec']['keys']==specification['keys'], 'Identity reference keys differ')
    more, identity=identity_metrics(output,prior,specification['keys'],aliases); values.update(more)
    identity['reference_output']=file_record(reference/'output.json')
    more, semantic=manual_metrics(review,arm['run_id'],contract=contract); values.update(more)
    boundary=submission_boundary(trace,values,contract=contract)
    require(values['S3_quote_exception_blocks']['value'] is None or values['S3_quote_exception_blocks']['value']<=len(repl_errors), 'Manual quote-error blocks exceed all REPL error blocks')
    return {'run_id':arm['run_id'],'task_id':arm['task_id'],'source_commit':arm['source_commit'],'metrics':values,
            'archive_inventory':inventory,'full_audit':file_record(audit_path),'discovery':discovery,'fetches':fetches,
            'citation_violations':violations,'identity':identity,'semantic_review':semantic,
            'submission_boundary':boundary,
            'all_component_error_events':errors,'all_unsuccessful_component_events_without_error':failures,
            'all_repl_error_blocks':repl_errors,'all_self_check_issues':checks['issues'],'all_self_check_signals':checks['signals'],
            'all_uncited':agent['uncited'],'all_model_call_records':list(calls.values()),'all_model_dispatch_records':list(attempts.values()),
            'model_counts_by_purpose':dict(role_counts),'missing_completion_call_ids':sorted(set(attempts)-set(calls)),
            'completion_only_call_ids':sorted(set(calls)-set(attempts)),
            'largest_root_prompt_partition':largest,'all_subcall_input_sizes':subcalls,'overlap':overlap,
            'fetch_paths':audited['fetch_paths']}


def build(directory, audit_dir, manual_paths, reference_manifest, aliases_path=None, labels=LABELS, *, contract=DEFAULT_CONTRACT):
    definition = contract_definition(contract)
    plan, execution=read(directory/'plan.json'),read(directory/'execution.json')
    require(plan['source_commit']==execution['source_commit'],'Plan/execution source mismatch')
    reviews, receipts=load_manual(manual_paths,plan['source_commit'],contract=contract)
    require(all(label in reviews for label in labels),'Missing manual review for: '+', '.join(label for label in labels if label not in reviews))
    aliases=read(aliases_path)['aliases'] if aliases_path else []
    for row in aliases:
        require(row.get('reason'), 'Explicit identity alias needs reason')
        row['evidence']=cited_evidence(row.get('evidence'))
    references=read(reference_manifest)['runs']; runs={}
    for label in labels:
        reference_label=label if label in ('A','SI') else 'B0'
        reference_run=Path(plan['main_root'])/'runs'/references[reference_label]
        reference=reference_run/read(reference_run/'research.json')['task_id']
        arm=execution['arms'][label]
        require(arm['source_commit']==plan['source_commit'],'Run source mismatch: '+label)
        runs[label]=archive_metrics(label,arm,audit_dir/(label+'.audit.json'),reviews[label],reference,aliases,contract=contract)
    controls=aggregate_controls(runs,contract=contract) if all(label in runs for label in CONTROLS) else None
    return {'status':'complete' if set(labels)==set(LABELS) else 'selected_completed_runs_only',
            'generated_at':datetime.now(timezone.utc).isoformat(),'source_commit':plan['source_commit'],
            'analysis_contract':definition,
            'definitions':{**DEFINITIONS, 'manual': definition['definition'] + ' S2/S3 still require cited manual review; caught/printed quote failures count individual printed records, including repeats.'},
            'runs':runs,'control_aggregates':controls,
            'inputs':{'plan':file_record(directory/'plan.json'),'execution':file_record(directory/'execution.json'),
                      'manual_reviews':receipts,'reference_manifest':file_record(reference_manifest),
                      'aliases':file_record(aliases_path) if aliases_path else None,
                      'predictions':execution.get('predictions'), 'extractor':file_record(Path(__file__))},
            'limitations':'Three repeats per base are descriptive, not statistical evidence. New direct-readable-v1 fetch transport. ' +
                ('Literal preregistered S1 is N/A; post-hoc submission-boundary diagnostic cannot count as preregistered success. ' if contract == DEFAULT_CONTRACT else
                 'The answer["ready"] assignment scoring contract defines an available measure; it does not select or establish a directional prediction for a new learned entry. Only that cohort’s committed preregistration can do so. ') +
                'Full historical harness metadata belongs to the intervention. Nine main runs serve ten report checks; an explicit-refinement run is separate.'}


def markdown(report):
    lines=['# Round 3 metrics','',report['limitations'],'','All values below have complete event-level evidence in metrics.json. N/A is never zero.','']
    if 'analysis_contract' in report:
        definition = report['analysis_contract']
        lines += [f"Scoring contract: `{definition['id']}`. S1 boundary: `{definition['boundary']}`.",
                  '', definition['definition'], '']
    for title, data in [('Directional and descriptive control metrics',report['control_aggregates'])]:
        if data is None:
            continue
        lines += ['## '+title,'','| Metric | B0 values | Frozen values | B0 mean [min,max]; n | Frozen mean [min,max]; n | Delta | Spread | Exceeds |','|---|---|---|---|---|---|---|---|']
        fmt=lambda v:'N/A' if v is None else f'{v:.8g}' if isinstance(v,float) else str(v)
        for key,row in data.items():
            vals=lambda arm:', '.join(fmt(row['individual'][f'{arm}-{i}']['value']) for i in range(1,4))
            stat=lambda arm:f"{fmt(row[arm]['mean'])} [{fmt(row[arm]['min'])},{fmt(row[arm]['max'])}]; {row[arm]['defined_runs']}"
            lines.append(f"| {key} | {vals('B0')} | {vals('B1-frozen')} | {stat('B0')} | {stat('B1-frozen')} | {fmt(row['delta'])} | {fmt(row['spread'])} | {row['abs_delta_exceeds_spread'] if row['abs_delta_exceeds_spread'] is not None else 'N/A'} |")
    lines += ['','## All individual run metrics','','| Metric | '+' | '.join(report['runs'])+' |','|---|'+'---|'*len(report['runs'])]
    for key in sorted({key for row in report['runs'].values() for key in row['metrics']}):
        cells=[]
        for row in report['runs'].values():
            value=row['metrics'].get(key,metric(None,reason='Not supplied by manual review'))
            cells.append(str(value['value']) if value['value'] is not None else 'N/A: '+value['reason'].replace('|','/').replace('\n',' '))
        lines.append('| '+key+' | '+' | '.join(cells)+' |')
    return '\n'.join(lines)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--audits',type=Path)
    parser.add_argument('--manual',type=Path,nargs='+',required=True)
    parser.add_argument('--reference-manifest',type=Path,default=Path(__file__).resolve().parent.parent/'round2/manifest.json')
    parser.add_argument('--aliases',type=Path)
    parser.add_argument('--labels',nargs='+',choices=LABELS,default=list(LABELS))
    parser.add_argument('--contract', choices=CONTRACTS, default=DEFAULT_CONTRACT)
    parser.add_argument('--output-dir',type=Path)
    args=parser.parse_args()
    try:
        directory=args.directory.resolve(); output=(args.output_dir or directory/'metrics').resolve()
        require(not output.exists() or not any(output.iterdir()),'Metrics output directory must be new or empty')
        execution=read(directory/'execution.json')
        require(all(not output.is_relative_to(Path(arm['workspace']).resolve()) for arm in execution['arms'].values()),'Metrics output must remain outside run workspaces')
        report=build(directory,args.audits or directory/'audits',args.manual,args.reference_manifest,args.aliases,tuple(args.labels),contract=args.contract)
        output.mkdir(parents=True,exist_ok=True)
        (output/'metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        (output/'metrics.md').write_text(markdown(report))
        print(json.dumps({'status':report['status'],'runs':list(report['runs']),'report':str(output/'metrics.json')}))
        return 0
    except (AuditError,KeyError,OSError,ValueError) as exc:
        print(json.dumps({'status':'failed','error':str(exc)}),file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
