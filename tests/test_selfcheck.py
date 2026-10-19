from loop_research.selfcheck import check, constraints_for


def test_fabricated_quote_and_search_only_url_are_caught(task, output):
    report = check(task, output, {
        'fetched': {'https://example.org/': ['fixture-a real value']},
        'checks': [], 'searches': [], 'discoveries': [], 'failures': [],
    }, {})
    assert any(x['type'] == 'fabricated_quote' for x in report['issues'])
    assert any(x['type'] == 'unchecked_constraint' for x in report['issues'])
    report = check(task, output, {'fetched': {}, 'checks': [], 'searches': [], 'discoveries': [], 'failures': []}, {})
    assert any(x['type'] == 'unfetched_url' for x in report['issues'])


def test_all_rows_constraints_quotes_and_operational_failures(task, output):
    checks = [{'row': '/rows/0', 'constraint': c['id'], 'verdict': True,
               'url': 'https://example.org/', 'quote': 'fixture-value'} for c in constraints_for(task)]
    evidence = {'fetched': {'https://example.org/': ['fixture-a fixture-value']}, 'checks': checks,
                'searches': [{'query': 'empty', 'hits': 0}],
                'discoveries': [{'query': 'stalled', 'new_entities': []}],
                'failures': [{'operation': 'fetch', 'url': 'https://failed.example/'}]}
    report = check(task, output, evidence, {'iteration_limit': True, 'timeout': True})
    kinds = {x['type'] for x in report['issues']}
    assert {'iteration_limit', 'timeout'} <= kinds
    assert {'empty_search', 'stalled_search', 'failed_fetch'} <= {s['type'] for s in report['signals']}
    assert 'fabricated_quote' not in kinds and 'unchecked_constraint' not in kinds


def test_check_cannot_accept_grades_as_evidence(task):
    report = check(task, {'rows': []}, {'fetched': {}, 'checks': [], 'searches': [], 'discoveries': [], 'failures': []}, {})
    assert not report['ok']
    assert report['issues'] == [{'type': 'empty_output'}]


def test_selfcheck_exposes_fetch_audit_and_every_dropped_hit(task, output):
    fetches = [{'id': 1, 'url': 'https://example.org/', 'focus': '',
                'source': 'backend', 'status': 'succeeded'}]
    dropped = [{'query': 'fixture', 'index': 0, 'hit': None, 'reason': 'malformed_hit'},
               {'query': 'fixture', 'index': 2, 'hit': {'title': 'excess'}, 'reason': 'excess_k'}]
    evidence = {'fetched': {}, 'checks': [], 'searches': [], 'discoveries': [], 'failures': [],
                'fetches': fetches, 'dropped_search_hits': dropped}
    report = check(task, output, evidence, {})
    assert report['fetches'] == fetches
    assert report['dropped_search_hits'] == dropped
    assert [item for item in report['signals'] if item['type'] == 'dropped_search_hit'] == [
        {'type': 'dropped_search_hit', **item} for item in dropped]


def test_operational_signals_do_not_fail_supported_answer(task, output):
    evidence = {'fetched': {'https://example.org/': ['fixture-a fixture-value']},
        'checks': [{'row': '/rows/0', 'constraint': c['id'], 'verdict': True,
                    'url': 'https://example.org/', 'quote': 'fixture-value'} for c in constraints_for(task)],
        'searches': [{'query': 'empty', 'hits': 0}],
        'discoveries': [{'query': 'empty', 'new_entities': []}],
        'failures': [{'operation': 'fetch', 'url': 'https://example.org/', 'reason': 'backend_attempt_failed'}],
        'dropped_search_hits': [{'query': 'empty', 'reason': 'excess_k'}]}
    report = check(task, output, evidence, {})
    assert report['ok'] and report['issues'] == []
    assert {s['type'] for s in report['signals']} == {'empty_search', 'stalled_search', 'failed_fetch', 'dropped_search_hit'}
    evidence['fetched'] = {}
    report = check(task, output, evidence, {'timeout': True})
    assert not report['ok']
    assert {'unfetched_url', 'unchecked_constraint', 'timeout'} <= {i['type'] for i in report['issues']}
    assert any(s['type'] == 'failed_fetch' for s in report['signals'])
