#!/usr/bin/env python3
"""Reporting-only application of the reviewed common institution mapping."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import unicodedata


def record(path):
    path = Path(path).resolve()
    body = path.read_bytes()
    return {'path': str(path), 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}


def norm(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value)).casefold() if c.isalnum())


MAPPING = {
    'kosterlitz_kias': ('Kosterlitz', ['KIAS', 'Korea Institute']),
    'genzel_lmu': ('Genzel', ['LMU', 'Ludwig']),
    'aspect_cnrs': ('Aspect', ['CNRS', 'National Centre for Scientific Research', 'National Center for Scientific Research']),
    'hinton_vector': ('Hinton', ['Vector']),
    'zeilinger_iqoqi': ('Zeilinger', ['IQOQI', 'Quantum Optics and Quantum Information']),
    'haldane_perimeter': ('Haldane', ['Perimeter']),
    'hasselmann_hamburg': ('Hasselmann', ['University of Hamburg', 'Hamburg University', 'Universitat Hamburg']),
    'weiss_lsu': ('Weiss', ['Louisiana State', 'LSU']),
    'krausz_cmf': ('Krausz', ['Molecular Fingerprinting', 'CMF']),
    'kajita_icrr': ('Kajita', ['Cosmic Ray Research', 'ICRR']),
    'mcdonald_sno': ('McDonald', ['Sudbury', 'SNO']),
    'thorne_ligo': ('Thorne', ['LIGO', 'VIRGO']),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists(), 'Preserve previous reports'
    state = json.loads((args.directory / 'execution.json').read_text())
    assert state['phases']['b']['status'] == 'complete'
    index = json.loads(args.index.read_text())
    assert set(MAPPING) == {c['candidate_id'] for c in index['candidates']}
    labels = ['B1', 'B1-frozen-1', 'B0-1', 'B1-frozen-2', 'B0-2', 'B1-frozen-3', 'B0-3']
    inventories = {}
    for label in labels:
        arm = state['arms'][label]
        assert arm['status'] == 'complete' and arm['exit_code'] == 0 and arm['source_unchanged']
        assert record(arm['archive_hashes']['path']) == arm['archive_hashes']
        inventories[label] = {r['path']: r for r in json.loads(Path(arm['archive_hashes']['path']).read_text())}
    source_bindings = []
    for candidate in index['candidates']:
        verified = []
        for key in ('text_file', 'raw_file', 'receipt_file'):
            original = candidate['artifacts'][key]
            assert record(original['path']) == original
            assert inventories[candidate['source_arm']][original['path']] == original
            verified.append(original)
        text = Path(candidate['artifacts']['text_file']['path']).read_text()
        for span in [candidate['appointment_evidence'], *candidate.get('date_evidence', [])]:
            assert text[span['start_char']:span['end_char']] == span['quote']
        source_bindings.append({'candidate_id': candidate['candidate_id'], 'source_arm': candidate['source_arm'],
                                'terminal_inventory': state['arms'][candidate['source_arm']]['archive_hashes'],
                                'verified_artifacts': verified})
    runs = {}
    for label in labels:
        arm = state['arms'][label]
        output_path = Path(arm['run_path']) / arm['task_id'] / 'output.json'
        assert record(output_path) == inventories[label][str(output_path)]
        output = json.loads(output_path.read_text())
        cells = []
        for candidate in index['candidates']:
            surname, alternatives = MAPPING[candidate['candidate_id']]
            matching = [(i, r) for i, r in enumerate(output['rows'])
                        if norm(surname) in norm(r['cells']['laureate']['value'])
                        and str(r['cells']['year']['value']) == str(candidate['award_year'])]
            assert len(matching) == 1
            i, row = matching[0]
            cell = row['cells']['affiliation_at_award']
            matched = [s for s in alternatives if norm(s) in norm(cell['value'])]
            cells.append({'candidate_id': candidate['candidate_id'], 'row_index': i,
                          'entity': row['cells']['laureate']['value'], 'cell': cell,
                          'named': bool(matched), 'matched_reviewed_names': matched,
                          'name_mapping_mentions_in_selected_quote': [s for s in alternatives if norm(s) in norm(cell.get('quote', ''))],
                          'temporal_confidence': candidate['temporal_confidence'],
                          'scope_concern': not bool(matched)})
        dated = {r['row_index'] for r in cells if r['scope_concern'] and r['temporal_confidence'].startswith('dated_')}
        temporal = {r['row_index'] for r in cells if r['scope_concern'] and not r['temporal_confidence'].startswith('dated_')}
        runs[label] = {'run_id': arm['run_id'], 'output': record(output_path), 'cells': cells,
                       'dated_omitted_affiliation_cells': len(dated), 'undated_affiliation_lead_cells': len(temporal),
                       'concurrent_affiliation_scope_concerns': len(dated | temporal)}
    report = {'created_at': datetime.now(timezone.utc).isoformat(), 'source_commit': state['source_commit'],
              'scope': 'Common archived-evidence completeness check of final B affiliation cells; separate from own-citation listed-value support. Component-level scope: a parent institution does not substitute for an explicitly named institute (Tokyo/ICRR and Academy/IQOQI treated alike). Name matches in quotations are diagnostics, not a complete semantic quote-sufficiency audit. Institution mapping and cells require parent review. Undated leads are not proven award-year omissions. Pool not claimed exhaustive.',
              'index': record(args.index), 'script': record(__file__), 'execution': record(args.directory / 'execution.json'),
              'reviewed_name_mapping': MAPPING, 'terminal_source_bindings': source_bindings, 'runs': runs}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({label: {k: r[k] for k in ('dated_omitted_affiliation_cells', 'undated_affiliation_lead_cells', 'concurrent_affiliation_scope_concerns')} for label, r in runs.items()}))


if __name__ == '__main__':
    main()
