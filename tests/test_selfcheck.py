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
    assert {'empty_search', 'stalled_search', 'failed_fetch', 'iteration_limit', 'timeout'} <= kinds
    assert 'fabricated_quote' not in kinds and 'unchecked_constraint' not in kinds


def test_check_cannot_accept_grades_as_evidence(task):
    report = check(task, {'rows': []}, {'fetched': {}, 'checks': [], 'searches': [], 'discoveries': [], 'failures': []}, {})
    assert not report['ok']
    assert report['issues'] == [{'type': 'empty_output'}]
