"""Read-only Round 2 transport evidence; no project imports or network calls."""
import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'runs/round3'


def read(path):
    return json.loads(path.read_text())


def receipt(path):
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data),
            'sha256': hashlib.sha256(data).hexdigest()}


def main():
    manifest = read(ROOT / 'runs/round2/manifest.json')
    inventory_path = ROOT / 'runs/round2/web_inventory.json'
    # The saved inventory contains an arm list, not a dictionary keyed by label.
    inventory = {arm['label']: arm for arm in read(inventory_path)['arms']}
    result = {'mode': 'offline_saved_inputs_only', 'sources': [receipt(inventory_path)],
              'arms': {}, 'claim_boundary':
              'Observed events expose no full page body. This does not prove that every '
              'possible future provider response or every short public-domain page is unavailable.'}
    for label in ('A', 'B1', 'B1-frozen', 'B0', 'SI', 'explicit'):
        audit_path = ROOT / 'runs/round2' / (label + '.audit.json')
        audit = read(audit_path)
        metrics = read(ROOT / 'runs/round2' / (label + '.metrics.json'))
        task_path = Path(audit['task_path'])
        assert audit['run_id'] == manifest['runs'][label]
        assert metrics['manifest']['status'] == 'complete'
        calls_path = task_path / 'codex_calls.jsonl'
        trajectory_path = task_path / 'trajectory.jsonl'
        opens, key_sets, snippets, samples = 0, Counter(), Counter(), []
        for line_number, line in enumerate(calls_path.read_text().splitlines(), 1):
            call = json.loads(line)
            if call['purpose'] != 'fetch':
                continue
            for wrapper in call['web_events']:
                event = wrapper['event']
                item = event.get('item', {})
                if event['type'] != 'item.completed' or item.get('action', {}).get('type') != 'open_page':
                    continue
                opens += 1
                for native_result in item.get('results', []):
                    key_sets[tuple(sorted(native_result))] += 1
                    snippets[native_result.get('snippet')] += 1
                    if len(samples) < 2 and native_result.get('url'):
                        samples.append({'call_line': line_number, 'call_id': call['call_id'],
                                        'response_chars': call['response_chars'],
                                        'event': event})
        assert opens == inventory[label]['summary']['completed_action_types']['open_page']
        assert sum(snippets.values()) == inventory[label]['summary']['results_by_action']['open_page']
        assert all(isinstance(s, str) and s.startswith('Total lines: ') and
                   s.removeprefix('Total lines: ').isdigit() for s in snippets)
        allowed = {'type', 'ref_id', 'snippet', 'title', 'url', 'domain', 'thumbnail_url'}
        assert all(set(keys) <= allowed for keys in key_sets)
        notices = []
        for line_number, line in enumerate(trajectory_path.read_text().splitlines(), 1):
            event = json.loads(line)
            if event.get('type') != 'tool' or event.get('tool') not in ('fetch', 'fetch_many'):
                continue
            texts = event['result']
            texts = [texts] if isinstance(texts, str) else texts
            for index, text in enumerate(texts):
                if any(term in text.lower() for term in ('reproduce', 'copyright', 'full text', 'entire', 'verbatim')):
                    notices.append({'trajectory_line': line_number, 'result_index': index, 'text': text})
        prompt_path = ROOT / 'runs/round2' / (label + '.largest_root_prompt.txt')
        prompt = prompt_path.read_text()
        assert len(prompt) == audit['largest_prompt']['total']
        assert hashlib.sha256(prompt.encode()).hexdigest() == audit['largest_prompt']['sha256']
        assert metrics['page_chars'] == audit['overlap']['total_chars']
        result['arms'][label] = {
            'run_id': audit['run_id'], 'task_path': str(task_path),
            'completed_open_actions': opens, 'open_result_count': sum(snippets.values()),
            'open_result_key_sets': [{'keys': list(keys), 'count': count} for keys, count in key_sets.items()],
            'all_open_snippets_are_line_count_metadata': True,
            'raw_page_chars': None, 'raw_page_chars_reason': 'not_exposed_in_saved_events',
            'native_open_samples': samples,
            'keyword_matched_returns': notices,
            'fetched_chars': metrics['page_chars'], 'largest_root_chars': len(prompt),
            'ratio': metrics['page_chars'] / len(prompt),
            'overlap_percent': audit['overlap']['fraction'] * 100,
            'rows': metrics['rows'], 'issues': metrics['issues'],
            'uncited_cells': metrics['uncited_cells'],
            'root_parts': audit['largest_prompt']['parts'],
        }
        result['sources'].extend(receipt(p) for p in (calls_path, trajectory_path, audit_path, prompt_path))
    result['total_completed_open_actions'] = sum(a['completed_open_actions'] for a in result['arms'].values())
    result['total_open_results'] = sum(a['open_result_count'] for a in result['arms'].values())
    (OUT / 'fetch_gate_evidence.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'verified': True, 'arms': len(result['arms']),
                      'open_actions': result['total_completed_open_actions'],
                      'open_results': result['total_open_results'],
                      'full_page_body_fields': 0}))


if __name__ == '__main__':
    main()
