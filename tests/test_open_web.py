"""Scripted offline tests; no real web/model results are represented here."""
from datetime import date
import json

import pytest
from pydantic import ValidationError

from test_validation import candidate


def test_open_web_solver_payload_is_an_allowlist_not_a_redacted_private_task():
    from webshaper.web_validation import public_solver_payload
    c = candidate()
    c.task = c.task.model_copy(update={'research_mode': 'open_web', 'corpus_id': None,
                                     'allowed_tools': ['web_search']})
    c.graph_id = 'PRIVATE_GRAPH_SENTINEL'
    c.answer = ['PRIVATE_REFERENCE_SENTINEL']
    c.cell_evidence = {'PRIVATE_URL_SENTINEL': ['PRIVATE_PASSAGE_SENTINEL']}
    payload = public_solver_payload(c.task.question, 3)
    assert set(payload) == {'question', 'output_requirements', 'browsing_budget'}
    assert payload['question'] == c.task.question
    assert payload['browsing_budget']['max_web_actions'] == 3
    assert all(secret not in str(payload) for secret in ['PRIVATE_', 'corpus_id', 'task_id', 'graph_id'])
    assert 'answer' not in payload


def test_missing_research_mode_is_legacy_and_open_web_forbids_corpus_identity():
    from webshaper.models import PublicTask
    c = candidate()
    assert c.task.research_mode == 'legacy_corpus'
    raw = c.task.model_dump()
    raw['research_mode'] = 'open_web'
    with pytest.raises(ValidationError, match='open-web'):
        PublicTask.model_validate(raw)
    raw.update(corpus_id=None, allowed_tools=['web_search'])
    assert PublicTask.model_validate(raw).research_mode == 'open_web'


def test_open_web_configuration_rejects_corpus_scoped_universe():
    from webshaper.models import RunConfig, Scope
    with pytest.raises(ValidationError, match='open-web'):
        RunConfig(as_of=date(2025, 12, 31), research_mode='open_web',
                  scope=Scope(mode='corpus_bounded', candidate_universe=['PRIVATE_COMPANY']))


def test_self_reported_browsing_never_substitutes_for_observed_tools():
    from webshaper.web_validation import browsing_failure
    from webshaper.models import WebSolverAnswer
    response = WebSolverAnswer(answer=['Acme'], citations=[], uncertainty='', outcome='answered')
    assert browsing_failure(response, {'web_enabled': False, 'web_events': []}) == 'tools_unavailable'
    assert browsing_failure(response, {'web_enabled': True, 'web_events': []}) == 'no_browsing'
    searched = {'web_enabled': True, 'web_events': [
        {'status': 'completed', 'action': {'type': 'search', 'query': 'Acme'}}]}
    assert browsing_failure(response, searched) == 'no_page_read'
    searched['web_events'].append({'status': 'completed', 'action': {'type': 'open_page', 'url': 'https://example.com/news'}})
    assert browsing_failure(response, searched) is None
    response.outcome = 'access_error'
    assert browsing_failure(response, searched) == 'access_error'
    response.outcome = 'budget_exhausted'
    assert browsing_failure(response, searched) == 'budget_exhausted'


def test_open_web_question_rejects_corpus_wording_and_reference_urls():
    from webshaper.web_validation import self_contained
    assert self_contained('As of 2025-12-31, which company announced Series A funding in May 2025?')
    assert not self_contained('As of 2025-12-31, which company in the supplied corpus raised funding?')
    assert not self_contained('As of 2025-12-31, which company is identified at https://private.example/reference?')


def scripted_web_pipeline(tmp_path, monkeypatch, failure=None, layers=0):
    """All content, tool events and judgments are FICTIONAL OFFLINE FIXTURES."""
    from webshaper.fixtures import FixtureProvider, fixture_config
    from webshaper.pipeline import run
    from webshaper.prompts import PROMPTS
    from webshaper.providers import ProviderResult
    from webshaper.sources import SourceStore
    from webshaper.validation import SEMANTIC_CHECKS

    config = fixture_config()
    # Three scripted actions plus one conservative provider guard reservation.
    config.solver.max_searches_per_call = config.verifier.max_searches_per_call = 4
    config.research_mode = 'open_web'
    config.layers, config.browsing_attempts, config.max_revisions = layers, 1, 0
    docs = {f'https://fixture.invalid/{i}': open(s.origin).read() for i, s in enumerate(config.sources)}
    calls = []
    original = FixtureProvider.invoke

    def fake_capture(self, url, domains, spec=None):
        assert url in docs  # An unexpected network request is a test failure.
        published = None if failure == 'undated' else date(2026, 1, 1) if failure == 'future' else date(2025, 3, 15)
        return self.capture_text(url, 'SCRIPTED OFFLINE FIXTURE', docs[url], published, category='fixture'), []

    def invoke(self, prompt, payload, schema, web=False):
        op = next(k for k, v in PROMPTS.items() if v == prompt)
        calls.append((op, payload, web))
        if not op.startswith('web_'):
            return original(self, prompt, payload, schema, web)
        observation = {'web_enabled': web, 'web_events': [], 'visited_urls': [],
                       'tokens': 10, 'latency_seconds': 0, 'fixture': True}
        citations = [{'url': url, 'quote': text} for url, text in docs.items()]
        if web:
            observation['web_events'] = [{'status': 'completed', 'action': {'type': 'search', 'query': 'SCRIPTED'}}]
            observation['web_events'] += [{'status': 'completed', 'action': {'type': 'open_page', 'url': url}} for url in docs]
            observation['visited_urls'] = list(docs)
        if op == 'web_seed':
            return original(self, PROMPTS['seed'], payload, schema)
        if op == 'web_expand':
            if payload['selected_leaf'] != 'cedar':
                data = {'subquery': None, 'proposed_question': '', 'rationale': 'fixture', 'rejection_reason': 'no fixture dependency'}
            else:
                data = {'subquery': {'target': '?investor', 'answer_type': 'investor', 'branches': [[
                    {'subject': '?investor', 'predicate': 'portfolio_company', 'object': '?anchor'},
                    {'subject': '?anchor', 'predicate': 'builds', 'object': 'dock'}]]},
                    'proposed_question': 'As of 2025-12-31, which company builds WarehouseBot warehouse robots and announced a Series A funding round in 2025 with an investor whose portfolio includes the company that builds DockBot dock robots?',
                    'rationale': 'SCRIPTED FIXTURE', 'rejection_reason': None}
        elif op in ('web_judge', 'web_render_check'):
            names = SEMANTIC_CHECKS if op == 'web_judge' else ['wording']
            data = {'checks': [{'name': n, 'status': 'unknown' if n == 'ambiguity' and failure == 'private_web_uncertainty' else 'pass'} for n in names],
                    'claim_support': [{'claim_id': f['claim_id'], 'status': 'supported', 'feedback': 'SCRIPTED'} for f in payload.get('claims', [])],
                    'revision_feedback': ['Investigate Delta Robotics as a plausible alternative.'] if failure == 'private_web_uncertainty' else []}
        elif op in ('web_closed', 'web_solver'):
            assert set(payload) == {'question', 'output_requirements', 'browsing_budget'}
            assert not any(s in json.dumps(payload) for s in ('Atlas Robotics', 'fixture.invalid', 'claim_id', 'source_id', 'parent_id'))
            reduced = 'REDUCED FIXTURE' in payload['question']
            answer = ['Atlas Robotics'] if op == 'web_solver' and not reduced or failure == 'closed' else []
            data = {'answer': answer, 'citations': citations if answer and web else [],
                    'uncertainty': 'SCRIPTED OFFLINE FIXTURE', 'outcome': 'answered' if answer else 'uncertain'}
            if op == 'web_solver' and failure == 'no_tools':
                observation['web_events'] = []
            if reduced and failure == 'partial_shortcut' and 'PARTIAL' in payload['question']:
                data.update(answer=['Atlas Robotics', 'Delta Robotics'], citations=citations, outcome='answered')
        elif op in ('web_grade', 'web_alternative_grade'):
            names = ['citation_support', 'temporal_support', 'answer_identity', 'question_constraints'] if op == 'web_grade' else ['alternative_exclusions', 'search_coverage', 'temporal_support']
            data = {'checks': [{'name': n, 'status': 'pass'} for n in names], 'feedback': 'SCRIPTED',
                    'constraint_support': [{'claim_id': f['claim_id'], 'status': 'unknown' if failure == 'unsupported' else 'supported', 'feedback': 'SCRIPTED'} for f in payload.get('required_claims', [])]}
        elif op == 'web_alternatives':
            data = {'outcome': 'unique_within_search', 'search_extent': 'SCRIPTED local fake search', 'limitations': 'Not real web evidence.',
                    'candidates': [{'name': 'Delta Robotics', 'status': 'unresolved' if failure == 'ambiguous' else 'excluded',
                                    'reason': 'SCRIPTED different investor', 'citations': citations}]}
        elif op == 'web_render':
            partial = any(a['predicate'] == 'portfolio_company' for b in payload['query']['branches'] for a in b)
            data = {'question': 'As of 2025-12-31, which company meets the REDUCED FIXTURE ' + ('PARTIAL' if partial else 'WHOLE') + ' conditions?'}
        else:
            raise AssertionError(op)
        return ProviderResult(data, 10, 3 if web else 0, {'fixture': True, 'scripted': True}, observation)

    monkeypatch.setattr(FixtureProvider, 'invoke', invoke)
    monkeypatch.setattr(SourceStore, 'capture_url', fake_capture)
    root = tmp_path / 'SCRIPTED-OFFLINE-open-web'
    stats = run(config, root)
    return stats, root, calls, config


def test_scripted_open_web_path_preserves_answer_and_resumes(tmp_path, monkeypatch):
    from webshaper.pipeline import run
    stats, root, calls, config = scripted_web_pipeline(tmp_path, monkeypatch, layers=1)
    assert stats['accepted_tasks'] == 1
    assert stats['depth_distribution'] == {'1': 1}
    assert stats['data_mode'] == 'fixture'
    task = json.loads((root / 'export/tasks.jsonl').read_text())
    reference = json.loads((root / 'export/references.jsonl').read_text())
    assert task['research_mode'] == 'open_web' and task['data_mode'] == 'fixture'
    assert reference['answer_entities_or_rows'] == ['atlas']
    validations = [json.loads(v) for v in (root / 'export/validation.jsonl').read_text().splitlines()]
    expanded = next(v for v in validations if 'l1-' in v['task_id'])
    checks = {c['name']: c['status'] for c in expanded['checks']}
    assert checks['exact_expansion'] == checks['closed_book_screen'] == checks['web_solvability'] == 'pass'
    assert checks['whole_shortcut_assessed'] == checks['partial_shortcuts_assessed'] == 'pass'
    before = len(calls)
    assert run(config, root)['usage'] == stats['usage']
    assert len(calls) == before


@pytest.mark.parametrize('failure, expected', [
    ('closed', 'closed_book_screen'), ('no_tools', 'observed_web_browsing'),
    ('unsupported', 'web_solvability'), ('ambiguous', 'web_alternatives')])
def test_scripted_open_web_rejection_gates(tmp_path, monkeypatch, failure, expected):
    stats, root, calls, _ = scripted_web_pipeline(tmp_path, monkeypatch, failure)
    assert stats['accepted_tasks'] == 0
    validation = json.loads((root / 'export/validation.jsonl').read_text())
    assert any(c['name'] == expected and c['status'] == 'fail' for c in validation['checks'])
    if failure == 'closed':
        assert [op for op, _, _ in calls if op.startswith('web_')] == ['web_seed', 'web_judge', 'web_closed']
    if failure == 'no_tools':
        assert not any(op in ('web_grade', 'web_alternatives') for op, _, _ in calls)


def test_partial_shortcut_finds_original_among_multiple_answers(tmp_path, monkeypatch):
    stats, root, _, _ = scripted_web_pipeline(tmp_path, monkeypatch, 'partial_shortcut', layers=1)
    assert stats['depth_distribution'] == {'0': 1}  # Only the seed survives.
    validations = [json.loads(v) for v in (root / 'export/validation.jsonl').read_text().splitlines()]
    expanded = next(v for v in validations if 'l1-' in v['task_id'])
    assert expanded['decision'] == 'reject'
    assert any(c['name'].startswith('shortcut:partial:') and c['status'] == 'fail' for c in expanded['checks'])


def test_web_uniqueness_is_assessed_by_required_live_audit_not_offline_judge(tmp_path, monkeypatch):
    stats, root, calls, _ = scripted_web_pipeline(tmp_path, monkeypatch, 'private_web_uncertainty')
    assert stats['accepted_tasks'] == 1
    assert any(op == 'web_alternatives' and web for op, _, web in calls)
    for op, payload, _ in calls:
        if op in ('web_alternatives', 'web_alternative_grade'):
            assert payload['private_review_concerns'] == ['Investigate Delta Robotics as a plausible alternative.']
    validation = json.loads((root / 'export/validation.jsonl').read_text())
    assert any(c['name'] == 'web_alternatives' and c['status'] == 'pass' for c in validation['checks'])


@pytest.mark.parametrize('failure', ['future', 'undated'])
def test_ineligible_fresh_citation_dates_cannot_be_overridden_by_grader(tmp_path, monkeypatch, failure):
    stats, root, calls, _ = scripted_web_pipeline(tmp_path, monkeypatch, failure)
    assert stats['accepted_tasks'] == 0
    assert not any(op == 'web_grade' for op, _, _ in calls)
    validation = json.loads((root / 'export/validation.jsonl').read_text())
    attempt = next(a for a in validation['solver_attempts'] if a['mode'] == 'open_web')
    assert attempt['failure_category'] == 'temporal_ineligible'


def test_failed_or_missing_web_actions_do_not_count_as_page_reads():
    from webshaper.web_validation import observed_browsing
    observation = {'web_enabled': True, 'web_events': [
        {'status': 'completed', 'action': {'type': 'search'}},
        {'event_type': 'item.completed', 'status': 'failed', 'action': {'type': 'open_page'}},
        {'status': 'completed', 'action': None}]}
    assert not observed_browsing(observation)


def test_partial_audits_include_connected_variable_object_atom_removals():
    from webshaper.models import Atom, Query
    from webshaper.web_validation import shortcut_queries
    from test_expansion import expansion_graph
    b, _ = expansion_graph()
    c = candidate()
    c.query = Query(target='?i', answer_type='investor', branches=[[
        Atom(subject='?i', predicate='portfolio_company', object='?company'),
        Atom(subject='?i', predicate='portfolio_company', object='anchor'),
        Atom(subject='?i', predicate='portfolio_company', object='?other')]])
    c.added_atoms = c.query.branches[0][1:]
    variants = {v['label']: v for v in shortcut_queries(c, b)}
    assert variants['partial:1']['query'] is not None


def test_citation_failure_categories_and_no_unobserved_fetch(tmp_path, monkeypatch):
    from webshaper.web_validation import capture_citations
    from webshaper.models import Budget, WebCitation
    from webshaper.sources import SourceStore
    from webshaper.storage import Journal
    store = SourceStore(tmp_path / 'web_sources')
    requested = []
    def capture(url, domains):
        requested.append(url)
        if url.endswith('/denied'):
            raise OSError('SCRIPTED 403')
        return store.capture_text(url, 'fixture', 'Exact real fixture text.', date(2025, 1, 1)), []
    monkeypatch.setattr(store, 'capture_url', capture)
    citations = [WebCitation(url='https://fixture.invalid/' + name, quote='invented') for name in ('unvisited', 'denied', 'wrongspan')]
    observation = {'visited_urls': [c.url for c in citations[1:]]}
    with Journal(tmp_path / 'journal.sqlite', {}, Budget()) as journal:
        docs, spans, errors = capture_citations(citations, observation, store, journal, 'fixture-call')
    assert not docs and not spans
    assert len(requested) == 2
    assert [e['failure_category'] for e in errors] == ['unobserved_citation', 'access_error', 'citation_span_error']


@pytest.mark.parametrize('published, retrospective, expected', [
    ('2026-01-01', False, False), ('2026-01-01', True, True),
    (None, False, False), (None, True, False), ('2025-01-01', False, True)])
def test_fresh_citation_dates_share_source_policy(published, retrospective, expected):
    from webshaper.web_validation import citation_dates_eligible
    c = candidate()
    c.task.scope.allow_retrospective = retrospective
    assert citation_dates_eligible([{'published_at': published}], c) is expected


def test_provider_tool_unavailability_keeps_its_failure_category(tmp_path):
    from types import SimpleNamespace
    from test_query import graph
    from webshaper.fixtures import fixture_config
    from webshaper.sources import SourceStore
    from webshaper.storage import Journal, UncertainCall
    from webshaper.web_validation import web_attempt
    config = fixture_config()
    def unavailable(*args, **kwargs):
        error = UncertainCall('SCRIPTED unavailable tool')
        error.observation = {'failure_code': 'capability_unavailable', 'web_enabled': True, 'web_events': []}
        raise error
    with Journal(tmp_path / 'journal.sqlite', {}, config.budget) as journal:
        gateway = SimpleNamespace(journal=journal, call_observed=unavailable)
        with pytest.raises(UncertainCall):
            web_attempt(candidate(), graph(), [], gateway, config, SourceStore(tmp_path / 'web_sources'), 'fixture')
        assert journal.records('web_attempts')[0]['failure_category'] == 'tools_unavailable'
