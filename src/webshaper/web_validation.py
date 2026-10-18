"""Open-web validation. Private evidence never crosses the solver boundary."""
import re
from datetime import date
from urllib.parse import urlsplit, urldefrag

from .expansion import ablated
from .models import (AlternativeReview, Check, SemanticAssessment,
                     Source, WebGrade, WebSolverAnswer)
from .query import execute, eligible_facts, validate_query
from .providers import usable_web_actions
from .sources import SourceStore, publication_eligible
from .storage import BudgetExceeded, SubscriptionLimit, UncertainCall, digest
from .validation import (SEMANTIC_CHECKS, RenderedQuestion, answer_matches, check,
                         deterministic_checks, documents_for, validation_result)

WEB_PRIVATE_CHECKS = tuple(name for name in SEMANTIC_CHECKS if name != 'ambiguity')


def self_contained(question):
    return not re.search(r'\b(corpus|supplied (?:sources|documents|graph)|attached documents|provided documents)\b|https?://|file://',
                         question, re.I)


def public_solver_payload(question, max_web_actions):
    # Intentionally accepts only a string, never Candidate/Bundle/private task metadata.
    return {'question': question,
            'output_requirements': 'Return entity names, exact short quotes and absolute page URLs supporting every constraint; report uncertainty and outcome.',
            'browsing_budget': {'max_web_actions': max_web_actions}}


def action_kind(event):
    action = event.get('action')
    kind = action.get('type', '') if isinstance(action, dict) else ''
    return re.sub(r'[^a-z]', '', kind.lower())


def completed_events(observation):
    return [e for e in observation.get('web_events', [])
            if e.get('status') in ('completed', 'item.completed')
            or (e.get('status') is None and e.get('event_type') == 'item.completed')]


def observed_browsing(observation):
    kinds = {action_kind(e) for e in completed_events(observation)}
    return observation.get('web_enabled', False) and 'search' in kinds and bool(kinds & {'openpage', 'findinpage'})


def browsing_failure(response, observation):
    if observation.get('failure_code'):
        code = observation['failure_code']
        return 'budget_exhausted' if code == 'web_action_budget' else code
    if not observation.get('web_enabled') or response.outcome == 'tools_unavailable':
        return 'tools_unavailable'
    if response.outcome in ('access_error', 'budget_exhausted'):
        return response.outcome
    kinds = {action_kind(e) for e in completed_events(observation)}
    if 'search' not in kinds:
        return 'no_browsing'
    if not kinds & {'openpage', 'findinpage'}:
        return 'no_page_read'
    return None


def page_key(url):
    return urldefrag(url)[0].rstrip('/')


def citation_dates_eligible(docs, candidate):
    return all(publication_eligible(date.fromisoformat(d['published_at']) if d['published_at'] else None,
                                   candidate.task.as_of, candidate.task.scope.allow_retrospective) for d in docs)


def capture_citations(citations, observation, store, journal, call_id):
    """Fetch only observed page URLs; never substitute generator snapshots."""
    visited = {page_key(u) for u in observation.get('visited_urls', [])}
    docs, spans, errors = {}, [], []
    for index, citation in enumerate(citations):
        url = urldefrag(citation.url)[0]
        key = digest([call_id, index, citation.model_dump(mode='json')])
        cached = journal.get('web_citation:' + key)
        if cached is None:
            failure_category = 'unobserved_citation'
            try:
                if page_key(url) not in visited:
                    raise ValueError('citation URL was not observed as an opened page')
                parts = urlsplit(url)
                if parts.scheme not in ('https', 'http') or not parts.hostname:
                    raise ValueError('invalid public citation URL')
                failure_category = 'access_error'
                source, _ = store.capture_url(url, [parts.hostname])
                text = store.read(source)
                # Whitespace may differ in tool excerpts, but characters/words must be exact.
                pattern = r'\s+'.join(re.escape(s) for s in citation.quote.split())
                match = re.search(pattern, text) if pattern else None
                failure_category = 'citation_span_error'
                if not match:
                    raise ValueError('citation quote missing from captured page')
                span = store.evidence(source, key, match.group(), match.start())
                cached = {'source': source.model_dump(mode='json'), 'evidence': span.model_dump(mode='json'),
                          'error': None, 'failure_category': None}
            except Exception as error:
                cached = {'source': None, 'evidence': None, 'error': type(error).__name__ + ': ' + str(error),
                          'failure_category': failure_category}
            journal.put('web_citation:' + key, cached)
            journal.record('web_evidence', key, {'call_id': call_id, 'url': url, **cached})
        if cached['error']:
            errors.append({'url': url, 'error': cached['error'], 'failure_category': cached['failure_category']})
        else:
            source = Source.model_validate(cached['source'])
            docs[source.source_id] = {'source_id': source.source_id, 'url': url, 'title': source.title,
                 'published_at': str(source.published_at) if source.published_at else None,
                 'date_basis': source.date_basis, 'text': store.read(source)}
            docs[source.source_id].update(date_status=source.date_status, date_evidence=source.date_evidence,
                                          original_url=source.original_url, final_url=source.final_url)
            spans.append(cached['evidence'])
    return list(docs.values()), spans, errors


def required_claims(candidate, bundle, sources, query=None):
    facts = eligible_facts(bundle, sources, candidate.task.as_of, candidate.task.scope.allow_retrospective)
    result = execute(query or candidate.query, bundle, facts)
    ids = {claim for answer, proof in result.proofs.items() if answer in candidate.answer for claim in proof}
    return [f for f in bundle.facts if f.claim_id in ids]


def grade_citations(candidate, response, docs, spans, claims, bundle, gateway, call_id, question=None):
    grade = gateway.call('verifier', 'web_grade', {
        'question': question or candidate.task.question, 'as_of': str(candidate.task.as_of),
        'allow_retrospective': candidate.task.scope.allow_retrospective,
        'response': response.model_dump(mode='json'), 'reference_names': [e.name for e in bundle.entities if e.entity_id in candidate.answer],
        'required_claims': [f.model_dump(mode='json') for f in claims],
        'entities': [e.model_dump(mode='json') for e in bundle.entities],
        'cited_pages': docs, 'verified_quote_spans': spans}, WebGrade, call_id)
    named = {c.name: c.status for c in grade.checks}
    supported = {c.claim_id: c.status for c in grade.constraint_support}
    passed = (bool(claims) and all(named.get(n) == 'pass' for n in ('citation_support', 'temporal_support', 'answer_identity', 'question_constraints'))
              and all(supported.get(f.claim_id) == 'supported' for f in claims))
    return passed, grade.model_dump(mode='json')


def web_attempt(candidate, bundle, sources, gateway, config, store, call_id, *, question=None, query=None, mode='open_web'):
    question = question or candidate.task.question
    journal = gateway.journal
    base = {'task_id': candidate.task.task_id, 'call_id': call_id, 'mode': mode, 'question': question,
            'research_mode': 'open_web', 'success': False, 'browsing_observed': False}
    try:
        response, observation = gateway.call_observed('solver', 'web_solver',
            public_solver_payload(question, usable_web_actions(config.solver.max_searches_per_call)), WebSolverAnswer, call_id, web=True)
    except (SubscriptionLimit, BudgetExceeded, UncertainCall) as error:
        observation = getattr(error, 'observation', {})
        code = observation.get('failure_code')
        result = {**base, 'failure_category': ('budget_exhausted' if isinstance(error, BudgetExceeded) else
                  'subscription_limit' if isinstance(error, SubscriptionLimit) else
                  'tools_unavailable' if code == 'capability_unavailable' else code or 'provider_interruption'),
                  'observation': observation, 'response': None}
        journal.record('web_attempts', digest(result), result)
        raise
    failure = browsing_failure(response, observation)
    matches = answer_matches(response.answer, candidate.answer, bundle)
    if mode == 'open_web_shortcut':
        # A reduced question may admit multiple answers. Recovering the original
        # reference among them is still a shortcut if its constraints are supported.
        matches = all(any(answer_matches([name], [expected], bundle) for name in response.answer)
                      for expected in candidate.answer)
    result = {**base, 'response': response.model_dump(mode='json'), 'observation': observation,
              'correct': matches,
              'browsing_observed': bool(observed_browsing(observation)), 'failure_category': failure,
              'citation_spans_valid': False, 'citation_support': False}
    if not failure:
        docs, spans, errors = capture_citations(response.citations, observation, store, journal, call_id)
        result.update(citation_errors=errors, cited_source_ids=[d['source_id'] for d in docs], evidence_ids=[e['evidence_id'] for e in spans])
        result['citation_spans_valid'] = bool(spans) and not errors
        if errors:
            result['failure_category'] = errors[0]['failure_category']
        elif not citation_dates_eligible(docs, candidate):
            result['failure_category'] = 'temporal_ineligible'
        elif not spans:
            result['failure_category'] = 'reasoning_uncertain' if not response.answer else 'missing_citations'
        elif not result['correct']:
            result['failure_category'] = 'incorrect_answer'
        else:
            # Persist the completed solver before a grader can pause.
            journal.record('web_attempts', digest([call_id, 'solver']), {**result, 'phase': 'solver_complete'})
            passed, grade = grade_citations(candidate, response, docs, spans,
                required_claims(candidate, bundle, sources, query), bundle, gateway, call_id + ':grade', question)
            result.update(citation_support=passed, grade=grade, success=passed,
                          failure_category=None if passed else 'unsupported_constraints')
    journal.record('web_attempts', digest([call_id, 'final']), {**result, 'phase': 'final'})
    return result


def alternative_audit(candidate, bundle, gateway, config, store, call_id, concerns=None):
    journal = gateway.journal
    names = [e.name for e in bundle.entities if e.entity_id in candidate.answer]
    review, observation = gateway.call_observed('verifier', 'web_alternatives', {
        'question': candidate.task.question, 'reference_names_to_challenge': names,
        'private_review_concerns': concerns or [],
        'browsing_budget': {'max_web_actions': usable_web_actions(config.verifier.max_searches_per_call)}}, AlternativeReview, call_id, web=True)
    citations = [c for a in review.candidates for c in a.citations]
    docs, spans, errors = capture_citations(citations, observation, store, journal, call_id)
    other = [a for a in review.candidates if not any(answer_matches([a.name], [expected], bundle)
                                                   for expected in candidate.answer)]
    plausible = bool(other) and all(a.status == 'excluded' and a.citations for a in other)
    passed = (observed_browsing(observation) and not errors and bool(spans) and plausible
              and citation_dates_eligible(docs, candidate)
              and review.outcome == 'unique_within_search' and bool(review.search_extent) and bool(review.limitations))
    result = {'task_id': candidate.task.task_id, 'call_id': call_id, 'review': review.model_dump(mode='json'),
              'observation': observation, 'capture_errors': errors, 'exhaustive': False, 'passed': False}
    journal.record('web_alternatives', call_id + ':research', {**result, 'phase': 'research_complete'})
    if passed:
        grade = gateway.call('verifier', 'web_alternative_grade', {'question': candidate.task.question,
            'as_of': str(candidate.task.as_of), 'allow_retrospective': candidate.task.scope.allow_retrospective,
            'reference_names': names, 'review': review.model_dump(mode='json'), 'cited_pages': docs,
            'private_review_concerns': concerns or [],
            'verified_quote_spans': spans}, WebGrade, call_id + ':grade')
        result['grade'] = grade.model_dump(mode='json')
        named = {c.name: c.status for c in grade.checks}
        passed = all(named.get(n) == 'pass' for n in ('alternative_exclusions', 'search_coverage', 'temporal_support'))
    result['passed'] = bool(passed)
    journal.record('web_alternatives', call_id, result)
    return result


def shortcut_queries(candidate, bundle):
    variants = [('whole', candidate.added_atoms)]
    # Probe every added atom, including variable joins; classify disconnected
    # reductions explicitly rather than silently skipping potential shortcuts.
    variants += [(f'partial:{i}', [a]) for i, a in enumerate(candidate.added_atoms)]
    results, seen = [], set()
    for label, removed in variants:
        try:
            query = ablated(candidate.query, removed)
            key = digest(query)
            if key in seen:
                results.append({'label': label, 'query': None, 'reason': 'same_as_another_ablation'})
                continue
            seen.add(key)
            validate_query(query, bundle)
            results.append({'label': label, 'query': query, 'reason': None})
        except ValueError as error:
            results.append({'label': label, 'query': None, 'reason': str(error)})
    return results


def validate_open_web(candidate, bundle, sources, store, gateway, config, parent=None):
    checks = deterministic_checks(candidate, bundle, sources, store, parent)
    checks.append(check('self_contained_question', self_contained(candidate.task.question),
                        'Question must stand alone without corpus references or supplied source URLs.'))
    attempts = []
    def finish():
        return validation_result(candidate, checks, attempts, config)
    if not all(c.status == 'pass' for c in checks):
        return finish()
    claims = required_claims(candidate, bundle, sources)
    ids = {e for f in claims for e in f.evidence_ids}
    context = {'candidate': candidate.model_dump(mode='json'), 'claims': [f.model_dump(mode='json') for f in claims],
               'evidence': [e.model_dump(mode='json') for e in bundle.evidence if e.evidence_id in ids],
               'entities': [e.model_dump(mode='json') for e in bundle.entities],
               'documents': documents_for(sources, store, candidate.task.as_of, candidate.task.scope.allow_retrospective)}
    prefix = candidate.task.task_id + f':v{candidate.version}:web'
    judgment = gateway.call('verifier', 'web_judge', context, SemanticAssessment, prefix + ':judge')
    named = {c.name: c for c in judgment.checks}
    # Open-web ambiguity is a mandatory later gate using actual search, not
    # an impossible request for global certainty from an offline private judge.
    for name in WEB_PRIVATE_CHECKS:
        c = named.get(name, Check(name=name, status='unknown', feedback='required judge check missing'))
        checks.append(c.model_copy(update={'name': 'semantic_' + name}))
    support = {s.claim_id: s.status for s in judgment.claim_support}
    checks.append(check('independent_claim_support', bool(claims) and all(support.get(f.claim_id) == 'supported' for f in claims)))
    if not all(c.status == 'pass' for c in checks):
        return finish()
    closed = gateway.call('solver', 'web_closed', public_solver_payload(candidate.task.question, 0),
                          WebSolverAnswer, prefix + ':closed')
    correct = answer_matches(closed.answer, candidate.answer, bundle)
    closed_attempt = {'task_id': candidate.task.task_id, 'mode': 'closed_book', 'call_id': prefix + ':closed',
                      'correct': correct, 'response': closed.model_dump(mode='json'), 'research_mode': 'open_web'}
    attempts.append(closed_attempt)
    gateway.journal.record('web_attempts', prefix + ':closed', closed_attempt)
    closed_valid = closed.outcome in ('answered', 'uncertain')
    checks.append(check('closed_book_completed', closed_valid, 'Access or budget errors do not establish difficulty.'))
    checks.append(check('closed_book_screen', not correct, 'Model-relative screen; not proof of browsing necessity.'))
    if correct or not closed_valid:
        return finish()
    web_store = SourceStore(store.root.parent / 'web_sources')
    for i in range(config.browsing_attempts):
        attempts.append(web_attempt(candidate, bundle, sources, gateway, config, web_store, prefix + f':browse:{i}'))
    browsing = [a for a in attempts if a['mode'] == 'open_web']
    checks.append(check('observed_web_browsing', any(a['browsing_observed'] for a in browsing), 'Require observed search and page-reading events.'))
    checks.append(check('web_solvability', any(a['success'] for a in browsing),
                        '; '.join(str(a['failure_category']) for a in browsing if not a['success'])))
    if not all(c.status == 'pass' for c in checks):
        return finish()
    concerns = judgment.revision_feedback + [c.feedback for c in judgment.checks if c.name == 'ambiguity' and c.feedback]
    alternatives = alternative_audit(candidate, bundle, gateway, config, web_store, prefix + ':alternatives', concerns)
    checks.append(check('web_alternatives', alternatives['passed'],
                        'Bounded alternative search only; not exhaustive web uniqueness. ' + alternatives['review']['search_extent']))
    if not alternatives['passed']:
        return finish()
    if candidate.layer:
        partial_done, whole_done = 0, False
        for variant in shortcut_queries(candidate, bundle):
            label, query = variant['label'], variant['query']
            key = prefix + ':shortcut:' + label
            if query is None:
                gateway.journal.record('web_shortcuts', key, {'task_id': candidate.task.task_id,
                    'label': label, 'status': 'unassessed', 'reason': variant['reason']})
                continue
            rendered = gateway.call('generator', 'web_render', {'query': query.model_dump(mode='json'),
                'as_of': str(candidate.task.as_of), 'entities': [e.model_dump(mode='json') for e in bundle.entities]},
                RenderedQuestion, key + ':render')
            render_judge = gateway.call('verifier', 'web_render_check', {'query': query.model_dump(mode='json'),
                'question': rendered.question, 'as_of': str(candidate.task.as_of),
                'entities': [e.model_dump(mode='json') for e in bundle.entities]}, SemanticAssessment, key + ':render_check')
            valid = (self_contained(rendered.question) and any(c.name == 'wording' and c.status == 'pass' for c in render_judge.checks)
                     and not any(re.search(r'(?<!\w)' + re.escape(name.casefold()) + r'(?!\w)', rendered.question.casefold())
                                 for e in bundle.entities if e.entity_id in candidate.answer for name in [e.name, *e.aliases]))
            if not valid:
                checks.append(check('shortcut_render:' + label, False, 'Independent wording validation failed.'))
                continue
            attempt = web_attempt(candidate, bundle, sources, gateway, config, web_store, key + ':solve',
                                  question=rendered.question, query=query, mode='open_web_shortcut')
            attempts.append(attempt)
            conclusive = attempt['success'] or attempt['failure_category'] in ('incorrect_answer', 'reasoning_uncertain')
            checks.append(Check(name='shortcut:' + label,
                status='pass' if conclusive and not attempt['success'] else 'fail' if attempt['success'] else 'unknown',
                feedback='Supported original answer after clue removal is a shortcut; access/budget failures are inconclusive.'))
            gateway.journal.record('web_shortcuts', key, {'task_id': candidate.task.task_id, 'label': label,
                'query': query.model_dump(mode='json'), 'question': rendered.question, 'attempt': attempt})
            partial_done += label.startswith('partial:') and conclusive
            whole_done |= label == 'whole' and conclusive
        checks.append(check('whole_shortcut_assessed', whole_done, 'Whole dependency removal must be assessed.'))
        checks.append(check('partial_shortcuts_assessed', partial_done > 0, 'At least one connected partial clue removal must be assessed.'))
    return finish()
