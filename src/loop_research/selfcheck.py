"""Deterministic evidence/coverage checks. No model, benchmark key, or grade input."""
import json

from .repl_tools import normalized_url


def constraints_for(task):
    constraints = [{'id': 'question', 'text': task.question}]
    for key, value in task.spec.items():
        if key not in {'keys'}:
            if isinstance(value, list):
                constraints.extend({'id': f'{key}/{i}', 'text': v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)}
                                   for i, v in enumerate(value))
            else:
                constraints.append({'id': key, 'text': str(value)})
    return constraints


def rows_of(output):
    for i, row in enumerate(output.get('rows', [])):
        yield f'/rows/{i}', row
    for name, records in output.get('files', {}).items():
        for i, row in enumerate(records):
            yield f'/files/{name}/{i}', row


def check(task, output, evidence, status):
    issues, signals, citations, coverage = [], [], [], []
    fetched = evidence.get('fetched', {})

    def cited(url, quote, path):
        try:
            pages = fetched.get(normalized_url(url), [])
        except ValueError:
            pages = []
        valid = bool(pages) and isinstance(quote, str) and bool(quote) and any(quote in text for text in pages)
        citations.append({'path': path, 'url': url, 'fetched': bool(pages), 'verbatim': valid})
        if not pages:
            issues.append({'type': 'unfetched_url', 'path': path, 'url': url})
        elif not valid:
            issues.append({'type': 'fabricated_quote', 'path': path, 'url': url})
        return valid

    rows = list(rows_of(output))
    if not rows:
        issues.append({'type': 'empty_output'})
    for path, row in rows:
        if 'cells' in row:
            for column, cell in row['cells'].items():
                if not cell.get('sources'):
                    issues.append({'type': 'missing_citation', 'path': path + '/cells/' + column})
                for url in cell.get('sources', []):
                    cited(url, cell.get('quote'), path + '/cells/' + column)
        else:
            if not row.get('excerpts'):
                issues.append({'type': 'missing_quote', 'path': path})
            for quote in row.get('excerpts', []):
                cited(row.get('url'), quote, path)
        for constraint in constraints_for(task):
            matches = [item for item in evidence.get('checks', [])
                       if item['row'] == path and item['constraint'] == constraint['id']]
            last = matches[-1] if matches else None
            checked = last is not None and cited(last['url'], last['quote'], path + ':' + constraint['id'])
            coverage.append({'row': path, 'constraint': constraint['id'], 'checked': checked,
                             'agent_verdict': last['verdict'] if last else None})
            if not checked:
                issues.append({'type': 'unchecked_constraint', 'row': path, 'constraint': constraint['id']})
            elif last['verdict'] is not True:
                issues.append({'type': 'failed_constraint', 'row': path, 'constraint': constraint['id']})
    for item in evidence.get('searches', []):
        if not item['hits']:
            signals.append({'type': 'empty_search', 'query': item['query']})
        if not any(d['query'] == item['query'] for d in evidence.get('discoveries', [])):
            issues.append({'type': 'unrecorded_discovery', 'query': item['query']})
    for item in evidence.get('discoveries', []):
        if not item['new_entities']:
            signals.append({'type': 'stalled_search', 'query': item['query']})
    for failure in evidence.get('failures', []):
        signals.append({'type': 'failed_fetch' if failure['operation'] == 'fetch' else 'failed_search', **failure})
    for dropped in evidence.get('dropped_search_hits', []):
        signals.append({'type': 'dropped_search_hit', **dropped})
    for flag in ('iteration_limit', 'timeout', 'call_limit', 'worker_error'):
        if status.get(flag):
            issues.append({'type': flag})
    return {'ok': not issues, 'issues': issues, 'signals': signals, 'citations': citations, 'constraint_coverage': coverage,
            'searches': evidence.get('searches', []), 'discoveries': evidence.get('discoveries', []),
            'fetches': evidence.get('fetches', []), 'dropped_search_hits': evidence.get('dropped_search_hits', []),
            'status': status}
