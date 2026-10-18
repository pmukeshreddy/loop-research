"""Conservative requirement deduplication plus an independent semantic screen."""
import re

from .models import SemanticAssessment
from .query import OPERATIONAL, PREDICATES, variable


def requirement_features(query):
    features = set()
    for branch in query.branches:
        substantive = [a for a in branch if a.predicate not in OPERATIONAL]
        for atom in substantive:
            features.add(("edge", atom.predicate))
            for other in substantive:
                # Both incoming/outgoing joins matter, including shared event participants.
                for side, term in (("s", atom.subject), ("o", atom.object)):
                    for other_side, other_term in (("s", other.subject), ("o", other.object)):
                        if atom is not other and variable(term) and term == other_term:
                            features.add(("join", atom.predicate, side, other.predicate, other_side))
        for atom in substantive:
            features.add(("answer", atom.predicate, PREDICATES[atom.predicate][0])
                         if atom.subject == query.target else ("dependency", atom.predicate))
    return features


def requirement_similarity(a, b):
    x, y = requirement_features(a), requirement_features(b)
    return len(x & y) / max(1, len(x | y))


def diversity_check(candidate, prior, gateway, journal, phase):
    previous = [c for c in prior if c.company_id == candidate.company_id and c.seed_id != candidate.seed_id]
    key = candidate.task.task_id + ":diversity:" + phase
    cached = journal.record_value("company_diversity", key)
    if cached:
        return cached["distinct"]
    scores = [{"task_id": c.task.task_id, "similarity": requirement_similarity(candidate.query, c.query)} for c in previous]
    def words(question):
        return set(re.findall(r"\w+", question.casefold()))
    text = words(candidate.task.question)
    # Catch nearly identical public templates even when the assigned company differs.
    global_duplicates = [c.task.task_id for c in prior if c.seed_id != candidate.seed_id
                         and len(text & words(c.task.question)) / max(1, len(text | words(c.task.question))) >= .85
                         and requirement_similarity(candidate.query, c.query) >= .8]
    distinct = not global_duplicates and not any(s["similarity"] >= .8 for s in scores)
    assessment = None
    if distinct and previous:
        assessment = gateway.call("verifier", "question_diversity", {
            "candidate": {"question": candidate.task.question, "query": candidate.query.model_dump(mode="json")},
            "previous": [{"question": c.task.question, "query": c.query.model_dump(mode="json")} for c in previous],
        }, SemanticAssessment, key)
        distinct = any(c.name == "distinct_research_requirements" and c.status == "pass" for c in assessment.checks)
    journal.record("company_diversity", key, {"task_id": candidate.task.task_id, "company_id": candidate.company_id,
                   "phase": phase, "distinct": distinct, "similarities": scores,
                   "global_near_duplicates": global_duplicates,
                   "assessment": assessment.model_dump(mode="json") if assessment else None})
    return distinct
