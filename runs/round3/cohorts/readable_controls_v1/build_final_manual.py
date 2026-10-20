#!/usr/bin/env python3
"""Compose reviewed counts without editing any original run or review."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

C = Path(__file__).resolve().parent
sys.path.insert(0, str(C.parents[1]))
import metrics


def read(path):
    return json.loads(Path(path).read_text())


def record(path):
    path = Path(path).resolve()
    body = path.read_bytes()
    return {'path': str(path), 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}


def evidence(path, note):
    return [{'path': str(Path(path).resolve()), 'note': note, 'file': record(path)}]


def count(value, path, reason):
    return {'value': value, 'reason': reason, 'evidence': evidence(path, reason)}


def main():
    target, alias_target = C / 'combined.manual.json', C / 'combined.identity_aliases.json'
    assert not target.exists() and not alias_target.exists()
    state = read(C / 'execution.json')
    storage_path = C / 'page_storage_counts.final.json'
    coverage_path = C / 'common_coverage_final.v2.json'
    storage, coverage = read(storage_path), read(coverage_path)
    nationality_path = C / 'common_nationality_final.json'
    nationality = read(nationality_path)
    labels = list(metrics.LABELS)
    runs, inputs, alias_inputs, aliases = {}, [], [], []
    for label in labels:
        name = 'B0-2.adjudicated.manual.json' if label == 'B0-2' else label + '.manual.json'
        path = C / name
        original = read(path)
        assert original['source_commit'] == state['source_commit']
        row = deepcopy(original['runs'][label])
        assert row['run_id'] == state['arms'][label]['run_id']
        metrics.manual_metrics(row, row['run_id'], contract='answer-ready-v2')
        row['original_manual_receipt'] = record(path)
        row['original_semantic_review'] = deepcopy(row['semantic_review'])
        row['reporting_adjustments'] = []
        inputs.append(record(path))
        if label == 'B1-frozen-2':
            correction_path = C / 'B1-frozen-2.S2_correction.json'
            correction = read(correction_path)
            key = correction['metric']
            assert row['metrics'][key]['value'] == correction['original_value']
            row['reporting_adjustments'].append({'metric': key, 'original': deepcopy(row['metrics'][key]), 'correction': record(correction_path)})
            row['metrics'][key] = count(correction['corrected_value'], correction_path, correction['reason'])
        if label in coverage['runs']:
            scope = coverage['runs'][label]
            assert scope['run_id'] == row['run_id']
            for key in ('concurrent_affiliation_scope_concerns', 'dated_omitted_affiliation_cells', 'undated_affiliation_lead_cells'):
                row['semantic_review']['counts'][key] = count(scope[key], coverage_path,
                    'Parent-reviewed common component-level affiliation check; original source-local review preserved. Dated omissions and undated leads are separate; listed values are not thereby false.')
            row['semantic_review']['summary'] += ' Final affiliation completeness uses the same archived candidate pool across every B arm, including institute-detail omissions; the original source-local count is preserved separately.'
            row['semantic_review']['evidence'] += evidence(coverage_path, 'Common final cells, exact source receipts and terminal-inventory bindings; v2 corrects parent/subunit consistency.')
            row['reporting_adjustments'].append({'metric': 'semantic_concurrent_affiliation_scope_concerns', 'original': deepcopy(row['original_semantic_review']['counts']['concurrent_affiliation_scope_concerns']), 'replacement': row['semantic_review']['counts']['concurrent_affiliation_scope_concerns']})
            for key in ('common_nationality_component_omission_cells', 'common_nationality_conflict_cells'):
                row['semantic_review']['counts'][key] = count(nationality['runs'][label][key], nationality_path,
                    'Post-registration common-evidence diagnostic, not a new directional prediction. Supported listed values are separate from omitted descriptive components or conflicting additional citizenship claims.')
        for key, value in storage['runs'][label]['metrics'].items():
            row['metrics'][key] = count(value, storage_path, 'Post-registration storage decomposition; retained raw bodies and whole-text hashes, not wire bytes or an added directional prediction.')
        evidence_path = Path(state['arms'][label]['run_path']) / state['arms'][label]['task_id'] / 'evidence.json'
        failed = any(r['status'] == 'failed' for r in read(evidence_path)['fetches'])
        row['metrics']['F1_failed_fetch_exposure'] = count(int(failed), evidence_path, 'Binary exposure to at least one admitted failed fetch; independent of whether its return was sent to extraction.')
        runs[label] = row
        alias_path = C / (label + '.identity_aliases.json')
        if alias_path.exists():
            alias_inputs.append(record(alias_path))
            for item in read(alias_path)['aliases']:
                prior = next((x for x in aliases if (x['field'], x['variant']) == (item['field'], item['variant'])), None)
                assert prior is None or prior['canonical'] == item['canonical']
                if prior is None:
                    aliases.append(item)
    additional = {k for label, row in runs.items() if label.startswith('B') for k in row['metrics'] if k.startswith(('V1_', 'D0_', 'D1_', 'D2_', 'D3_', 'F1_', 'R2_'))}
    for label in ('A', 'SI'):
        for key in additional - runs[label]['metrics'].keys():
            runs[label]['metrics'][key] = count(None, C / 'review_protocol.md', 'Dedicated additional behavior-count review was registered for B arms; this A/SI metric was not independently scored under that protocol. Narrative examples are not substituted as counts.')
        for key in ('dated_omitted_affiliation_cells', 'undated_affiliation_lead_cells', 'common_nationality_component_omission_cells', 'common_nationality_conflict_cells'):
            runs[label]['semantic_review']['counts'][key] = count(None, coverage_path,
                'This additional common-pool diagnostic covers the seven B physics outputs only. The independent A/SI semantic review and its original scope count remain separate.')
    for row in runs.values():
        metrics.manual_metrics(row, row['run_id'], contract='answer-ready-v2')
    target.write_text(json.dumps({'source_commit': state['source_commit'], 'analysis_contract': 'answer-ready-v2',
        'created_at': datetime.now(timezone.utc).isoformat(), 'composition_script': record(__file__),
        'original_inputs': inputs, 'runs': runs}, ensure_ascii=False, indent=2) + '\n')
    alias_target.write_text(json.dumps({'source_commit': state['source_commit'], 'inputs': alias_inputs, 'aliases': aliases}, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'manual': record(target), 'aliases': record(alias_target), 'runs': labels}))


if __name__ == '__main__':
    main()
