"""Evidence extraction, independent support assessment, and seed construction."""
from typing import Literal

from .models import (Bundle, Entity, Fact, PublicTask, Candidate, Record, SeedProposal,
                     SemanticAssessment, ValidTime)
from .query import PREDICATES, eligible_facts, execute, validate_bundle
from .storage import digest


class Quote(Record):
    source_id: str
    quote: str
    start: int | None


class ExtractedFact(Record):
    subject_id: str
    predicate: str
    object_id_or_value: str
    event_id: str | None
    valid_time: ValidTime
    resolution_status: Literal["resolved", "unresolved", "conflict"]
    polarity: Literal["positive", "negative"]
    quotes: list[Quote]


class Extraction(Record):
    entities: list[Entity]
    facts: list[ExtractedFact]


class SearchHit(Record):
    url: str
    title: str


class SearchResults(Record):
    hits: list[SearchHit]
    capability_available: bool
    note: str


def normalize_extraction(response, source_ids):
    """Canonicalize literal values, never merge real entities by name.

    A generator-supplied source-scoped entity ID is already an explicit
    identifier. Preserve it in the identifier field for the independent judge.
    This is bookkeeping, not an assertion that identity is factually resolved.
    """
    response = response.model_copy(deep=True)
    original_ids = [e.entity_id for e in response.entities]
    if len(set(original_ids)) != len(original_ids):
        raise ValueError("duplicate original entity identifier")
    mapping, entities = {}, {}
    for entity in response.entities:
        original = entity.entity_id
        if not entity.identifiers and any(original.startswith(s + ":") for s in source_ids):
            entity.identifiers = [original]
        if entity.kind in ("year", "date", "category"):
            value = " ".join(entity.name.casefold().split())
            entity.entity_id = "value:" + entity.kind + ":" + digest(value)[:20]
            entity.identifiers = sorted(set(entity.identifiers + [entity.entity_id]))
        mapping[original] = entity.entity_id
        if entity.entity_id in entities:
            old = entities[entity.entity_id]
            if entity.kind not in ("year", "date", "category"):
                raise ValueError("duplicate nonliteral entity identifier")
            old.identifiers = sorted(set(old.identifiers + entity.identifiers))
            if entity.resolution_status != "resolved":
                old.resolution_status = entity.resolution_status
        else:
            entities[entity.entity_id] = entity
    response.entities = list(entities.values())
    for fact in response.facts:
        fact.subject_id = mapping.get(fact.subject_id, fact.subject_id)
        fact.object_id_or_value = mapping.get(fact.object_id_or_value, fact.object_id_or_value)
        fact.event_id = mapping.get(fact.event_id, fact.event_id)
    return response


def source_documents(sources, store):
    return [{"source_id": s.source_id, "url": s.url_or_local_origin, "title": s.title,
             "published_at": str(s.published_at) if s.published_at else None,
             "date_basis": s.date_basis, "date_status": s.date_status, "date_evidence": s.date_evidence,
             "text": store.read(s)} for s in sources]


def extract_bundle(sources, store, gateway, checkpoint_id, previous=None, revision_feedback=None):
    docs = source_documents(sources, store)
    response = gateway.call("generator", "extract", {"documents": docs, "predicates": PREDICATES,
                            "existing_entities": [e.model_dump(mode="json") for e in previous.entities] if previous else [],
                            "revision_feedback": revision_feedback or []},
                            Extraction, checkpoint_id + ":extract")
    source_map = {s.source_id: s for s in sources}
    response = normalize_extraction(response, set(source_map))
    facts, evidence = [], []
    for raw in response.facts:
        if not raw.quotes:
            raise ValueError("extracted fact has no evidence")
        claim_id = "f_" + digest(raw)[:24]
        refs = []
        for quote in raw.quotes:
            if quote.source_id not in source_map:
                raise ValueError("invented source ID in extraction")
            e = store.evidence(source_map[quote.source_id], claim_id, quote.quote, quote.start)
            evidence.append(e)
            refs.append(e.evidence_id)
        facts.append(Fact(claim_id=claim_id, **raw.model_dump(exclude={"quotes"}), evidence_ids=refs))
    bundle = Bundle(entities=response.entities, facts=facts, evidence=evidence)
    validate_bundle(bundle)
    assessment = gateway.call("verifier", "support", {"claims": [f.model_dump(mode="json") for f in facts],
                              "entities": [e.model_dump(mode="json") for e in bundle.entities],
                              "evidence": [e.model_dump(mode="json") for e in evidence], "documents": docs},
                              SemanticAssessment, checkpoint_id + ":support")
    supported = {c.claim_id: c.status for c in assessment.claim_support}
    for e in bundle.evidence:
        e.support_status = supported.get(e.claim_id, "unknown")
    return bundle, assessment


def make_seed(proposal: SeedProposal, config, bundle, sources, task_id, seed_id, version, graph_id):
    if proposal.query is None:
        raise ValueError("seed_generator_rejected: " + str(proposal.rejection_reason))
    facts = eligible_facts(bundle, sources, config.as_of, config.scope.allow_retrospective)
    result = execute(proposal.query, bundle, facts)
    task = PublicTask(task_id=task_id, question=proposal.question, as_of=config.as_of,
                      scope=config.scope.model_copy(deep=True),
                      research_mode=config.research_mode,
                      corpus_id=graph_id if config.research_mode == "legacy_corpus" else None,
                      allowed_tools=["corpus"] if config.research_mode == "legacy_corpus" else ["web_search"],
                      data_mode=config.mode)
    return Candidate(task=task, query=proposal.query, answer=result.answers, seed_id=seed_id,
                     parent_id=None, version=version, graph_id=graph_id)
