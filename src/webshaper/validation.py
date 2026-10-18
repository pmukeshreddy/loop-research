"""Read-only validation; deterministic gates cannot be overridden by any model."""
import re
import threading
from concurrent.futures import ThreadPoolExecutor

from .expansion import ablated, redundant
from .models import Check, Record, SemanticAssessment, SolverAnswer, Validation
from .query import eligible_facts, execute, membership, validate_bundle, validate_query
from .storage import digest, SubscriptionLimit, BudgetExceeded, UncertainCall
from .sources import eligible_sources

SEMANTIC_CHECKS = ("wording", "identity", "temporal_semantics", "ambiguity", "leakage", "usefulness", "evidence_support")


class RenderedQuestion(Record):
    question: str


def check(name, passed, feedback="", evidence_ids=None):
    return Check(name=name, status="pass" if passed else "fail", feedback=feedback,
                 evidence_ids=evidence_ids or [])


def deterministic_checks(candidate, bundle, sources, store, parent=None, *, check_spans=True):
    checks = []
    try:
        validate_bundle(bundle)
        validate_query(candidate.query, bundle)
    except ValueError as error:
        return [check("structural_validity", False, str(error))]
    checks.append(check("structural_validity", True))
    cutoff, scope = candidate.task.as_of, candidate.task.scope
    facts = eligible_facts(bundle, sources, cutoff, scope.allow_retrospective) if check_spans else None
    result = execute(candidate.query, bundle, facts)
    checks.append(check("reference_answer", bool(result.answers) and result.answers == sorted(candidate.answer),
                        "computed answers must equal the immutable reference"))
    required = {c for ids in result.proofs.values() for c in ids}
    candidate.cell_evidence = {a: sorted({e for f in bundle.facts if f.claim_id in ids for e in f.evidence_ids})
                               for a, ids in result.proofs.items()}
    if scope.mode == "corpus_bounded":
        candidate.candidate_decisions = membership(candidate.query, bundle, scope.candidate_universe, facts)
        complete = set(result.answers) <= set(scope.candidate_universe) and all(
            d["decision"] != "unresolved" for d in candidate.candidate_decisions.values())
        checks.append(Check(name="completeness", status="pass" if complete else "unknown",
                            feedback="Every candidate needs positive or explicit negative evidence."))
        required.update(c for d in candidate.candidate_decisions.values() for c in d["claim_ids"])
    else:
        candidate.candidate_decisions = {"not_applicable": "Identified-target mode; no exhaustive universe claimed."}
        checks.append(check("target_cardinality", len(result.answers) == scope.expected_count,
                            "plausible open-world alternatives require separate semantic judging"))
    if candidate.layer:
        if parent is None or candidate.subquery is None or candidate.expanded_leaf is None:
            checks.append(check("exact_expansion", False, "missing parent/subquery"))
        else:
            original = sorted(candidate.expanded_leaf if isinstance(candidate.expanded_leaf, list) else [candidate.expanded_leaf])
            intermediate = execute(candidate.subquery, bundle, facts)
            required.update(c for ids in intermediate.proofs.values() for c in ids)
            checks.append(check("exact_expansion", intermediate.answers == original == candidate.intermediate_answer
                                and result.answers == parent.answer == candidate.answer
                                and candidate.task.as_of == parent.task.as_of and candidate.task.scope == parent.task.scope,
                                "intermediate/final answers and scope must be preserved"))
            checks.append(check("nonredundant_expansion", not redundant(candidate.query, candidate.added_atoms, bundle, facts),
                                "remove new clues and compare answer sets"))
    if check_spans:
        source_map = {s.source_id: s for s in sources}
        evidence_map = {e.evidence_id: e for e in bundle.evidence}
        required_evidence = {eid for f in bundle.facts if f.claim_id in required for eid in f.evidence_ids}
        valid = True
        for eid in required_evidence:
            e = evidence_map[eid]
            source = source_map.get(e.source_id)
            if not source or store.read(source)[e.span_start:e.span_end] != e.span_text or e.support_status != "supported":
                valid = False
        checks.append(check("evidence_spans", valid and bool(required_evidence), evidence_ids=sorted(required_evidence)))
        checks.append(check("historical_evidence", bool(required) and required <= {f.claim_id for f in facts},
                            "effective and publication dates must satisfy the frozen cutoff policy"))
    question = candidate.task.question.casefold()
    entities = {e.entity_id: e for e in bundle.entities}
    names = [n for a in candidate.answer for n in [entities[a].name, *entities[a].aliases]]
    leakage = any(re.search(r"(?<!\w)" + re.escape(n.casefold()) + r"(?!\w)", question) for n in names)
    checks.append(check("answer_leakage", not leakage, "question must not disclose its answer"))
    checks.append(check("explicit_cutoff", cutoff.isoformat() in candidate.task.question
                        and not re.search(r"\b(currently|recently|today)\b", question),
                        f"Include the exact ISO cutoff {cutoff.isoformat()} in the question; avoid relative dates."))
    if scope.mode == "corpus_bounded":
        checks.append(check("bounded_wording", "corpus" in question))
    return checks


def decide(checks, revision, max_revisions):
    if checks and all(c.status == "pass" for c in checks):
        return "accept"
    return "revise" if revision < max_revisions else "reject"


def solver_payload(candidate, documents, closed_book=False):
    task = candidate.task.model_dump(mode="json")
    task["allowed_tools"] = [] if closed_book else ["corpus"]
    return {"task": task, "mode": "closed_book" if closed_book else "corpus",
            "documents": [] if closed_book else documents}


def citations_valid(answer, documents):
    docs = {d["source_id"]: d["text"] for d in documents}
    return bool(answer.citations) and all(c.source_id in docs and c.quote.strip() and c.quote in docs[c.source_id]
                                          for c in answer.citations)


def answer_matches(answer, expected, bundle):
    def norm(s):
        return " ".join(s.casefold().split())
    names = {}
    for e in bundle.entities:
        for name in (e.entity_id, e.name, *e.aliases):
            names.setdefault(norm(name), set()).add(e.entity_id)
    resolved = []
    for item in answer:
        matches = names.get(norm(item), set())
        if len(matches) != 1:
            return False
        resolved.append(next(iter(matches)))
    return len(resolved) == len(set(resolved)) and sorted(resolved) == sorted(expected)


def documents_for(sources, store, cutoff, retrospective=False):
    return [{"source_id": s.source_id, "url": s.url_or_local_origin, "title": s.title,
             "published_at": s.published_at.isoformat(), "date_basis": s.date_basis,
             "retrieved_at": s.retrieved_at.isoformat(), "category": s.category, "text": store.read(s)}
            for s in eligible_sources(sources, cutoff, retrospective)]


def validation_result(candidate, checks, attempts, config):
    return Validation(task_id=candidate.task.task_id, candidate_version=candidate.version,
                      decision=decide(checks, candidate.version, config.max_revisions), checks=checks,
                      solver_attempts=attempts, feedback=[c.name + ": " + c.feedback for c in checks if c.status != "pass"],
                      judge_config=config.verifier.model_dump(mode="json"),
                      audit_status="fixture_only" if config.mode == "fixture" else "pending_manual_review")


def validate(candidate, bundle, sources, store, gateway, config, parent=None):
    checks = deterministic_checks(candidate, bundle, sources, store, parent)
    attempts = []
    call_prefix = candidate.task.task_id + f":v{candidate.version}"
    docs = documents_for(sources, store, candidate.task.as_of, candidate.task.scope.allow_retrospective)
    if all(c.status == "pass" for c in checks):
        evidence_ids = {e for ids in candidate.cell_evidence.values() for e in ids}
        relevant_claims = [f for f in bundle.facts if evidence_ids.intersection(f.evidence_ids)]
        for decision in candidate.candidate_decisions.values():
            if isinstance(decision, dict):
                relevant_claims += [f for f in bundle.facts if f.claim_id in decision.get("claim_ids", [])]
        if candidate.subquery:
            ids = {c for cs in execute(candidate.subquery, bundle,
                   eligible_facts(bundle, sources, candidate.task.as_of, candidate.task.scope.allow_retrospective)).proofs.values() for c in cs}
            relevant_claims += [f for f in bundle.facts if f.claim_id in ids]
        relevant_claims = list({f.claim_id: f for f in relevant_claims}.values())
        relevant_evidence = {eid for f in relevant_claims for eid in f.evidence_ids}
        judgment = gateway.call("verifier", "judge", {"candidate": candidate.model_dump(mode="json"),
                                "claims": [f.model_dump(mode="json") for f in relevant_claims],
                                "evidence": [e.model_dump(mode="json") for e in bundle.evidence
                                             if e.evidence_id in relevant_evidence],
                                "entities": [e.model_dump(mode="json") for e in bundle.entities],
                                "documents": docs}, SemanticAssessment, call_prefix + ":judge")
        named = {c.name: c for c in judgment.checks}
        for name in SEMANTIC_CHECKS:
            c = named.get(name, Check(name=name, status="unknown", feedback="required judge check missing"))
            checks.append(c.model_copy(update={"name": "semantic_" + name}))
        support = {s.claim_id: s.status for s in judgment.claim_support}
        checks.append(check("independent_claim_support", bool(relevant_claims) and all(
            support.get(f.claim_id) == "supported" for f in relevant_claims)))
        if all(c.status == "pass" for c in checks):
            if candidate.layer:
                closed = gateway.call("solver", "solver", solver_payload(candidate, docs, True), SolverAnswer,
                                      call_prefix + ":closed")
                correct = answer_matches(closed.answer, candidate.answer, bundle)
                attempts.append({"mode": "closed_book", "correct": correct, "response": closed.model_dump(mode="json"),
                                 "model_config": config.solver.model_dump(mode="json")})
                checks.append(check("closed_book_screen", not correct, "model-relative screen; not proof of browsing necessity"))
                if correct:
                    return validation_result(candidate, checks, attempts, config)
            # Five fresh sessions by default, never sharing previous attempts or references.
            stopped = threading.Event()
            def solve(i):
                if stopped.is_set():
                    raise SubscriptionLimit("another attempt requested a pause")
                try:
                    response = gateway.call("solver", "solver", solver_payload(candidate, docs), SolverAnswer,
                                            call_prefix + f":browse:{i}")
                except (SubscriptionLimit, BudgetExceeded, UncertainCall):
                    stopped.set()
                    raise
                matches = answer_matches(response.answer, candidate.answer, bundle)
                valid_citations = citations_valid(response, docs)
                graded = False
                if matches and valid_citations:
                    if stopped.is_set():
                        raise SubscriptionLimit("another attempt requested a pause; grading was not dispatched")
                    grade = gateway.call("verifier", "grade", {"task": candidate.task.model_dump(mode="json"),
                                         "response": response.model_dump(mode="json"), "reference": candidate.answer,
                                         "query": candidate.query.model_dump(mode="json"), "documents": docs,
                                         "entities": [e.model_dump(mode="json") for e in bundle.entities]},
                                         SemanticAssessment, call_prefix + f":grade:{i}")
                    graded = any(c.name == "citation_support" and c.status == "pass" for c in grade.checks)
                return {"mode": "browsing", "attempt": i, "correct": matches, "citation_spans_valid": valid_citations,
                        "citation_support": graded, "success": matches and valid_citations and graded,
                        "response": response.model_dump(mode="json"), "model_config": config.solver.model_dump(mode="json")}
            if config.concurrency == 1:
                browsed = [solve(i) for i in range(config.browsing_attempts)]
            else:
                browsed = []
                with ThreadPoolExecutor(max_workers=config.concurrency) as pool:
                    # At most one batch is in flight; no queue continues after quota failure.
                    for start in range(0, config.browsing_attempts, config.concurrency):
                        browsed.extend(pool.map(solve, range(start, min(start + config.concurrency, config.browsing_attempts))))
            attempts.extend(browsed)
            checks.append(check("solvability", any(a["success"] for a in browsed),
                                "solver failure may reflect model limits; source-access failures recorded separately"))
            sampled = int(digest(candidate.task.task_id)[:8], 16) / 0xFFFFFFFF < config.shortcut_audit_rate
            if candidate.layer and sampled:
                rendered = gateway.call("generator", "render", {"query": ablated(candidate.query, candidate.added_atoms).model_dump(mode="json"),
                                        "scope": candidate.task.scope.model_dump(mode="json"), "as_of": str(candidate.task.as_of),
                                        "entities": [e.model_dump(mode="json") for e in bundle.entities]},
                                        RenderedQuestion, call_prefix + ":ablation_render")
                audit = candidate.model_copy(deep=True)
                audit.task.question = rendered.question
                answer = gateway.call("solver", "solver", solver_payload(audit, docs), SolverAnswer, call_prefix + ":ablation_solve")
                shortcut = answer_matches(answer.answer, candidate.answer, bundle)
                attempts.append({"mode": "ablation", "question": rendered.question, "correct": shortcut,
                                 "response": answer.model_dump(mode="json")})
                checks.append(check("empirical_shortcut_audit", not shortcut, "sampled solver behavior after clue removal"))
    return validation_result(candidate, checks, attempts, config)
