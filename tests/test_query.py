from datetime import date

import pytest


def graph():
    from webshaper.models import Bundle, Entity, Fact, Evidence
    entities = [Entity(entity_id=i, name=i, kind=k, identifiers=[i], resolution_status="resolved")
                for i, k in [("a", "company"), ("b", "company"), ("a1", "funding_event"),
                             ("b1", "funding_event"), ("b2", "funding_event"), ("A", "category"),
                             ("B", "category"), ("2025", "year"), ("2024", "year"),
                             ("i", "investor"), ("j", "investor")]]
    triples = [("a", "has_funding_event", "a1", "a1"), ("a1", "round_type", "A", "a1"),
               ("a1", "announcement_year", "2025", "a1"), ("a1", "investor", "i", "a1"),
               ("b", "has_funding_event", "b1", "b1"), ("b1", "round_type", "A", "b1"),
               ("b1", "announcement_year", "2024", "b1"), ("b1", "investor", "i", "b1"),
               ("b", "has_funding_event", "b2", "b2"), ("b2", "round_type", "B", "b2"),
               ("b2", "announcement_year", "2025", "b2"), ("b2", "investor", "j", "b2")]
    facts, evidence = [], []
    for n, (s, p, o, event) in enumerate(triples):
        facts.append(Fact(claim_id=f"f{n}", subject_id=s, predicate=p, object_id_or_value=o, event_id=event,
                          valid_time={"start": "2024-01-01", "kind": "event"}, evidence_ids=[f"e{n}"],
                          resolution_status="resolved"))
        evidence.append(Evidence(evidence_id=f"e{n}", source_id="s", span_start=0, span_end=4,
                                 span_text="test", claim_id=f"f{n}", support_status="supported"))
    return Bundle(entities=entities, facts=facts, evidence=evidence)


def query():
    from webshaper.models import Query
    return Query(branches=[[{"subject": "?company", "predicate": "has_funding_event", "object": "?event"},
                            {"subject": "?event", "predicate": "round_type", "object": "A"},
                            {"subject": "?event", "predicate": "announcement_year", "object": "2025"}]])


def test_same_event_join_does_not_mix_round_and_year():
    from webshaper.query import execute
    result = execute(query(), graph())
    assert result.answers == ["a"]
    assert set(result.proofs["a"]) == {"f0", "f1", "f2"}


def test_union_and_directed_predicates():
    from webshaper.query import execute, validate_query
    q = query()
    q.branches[0][-1].object = ["2024", "2025"]
    assert execute(q, graph()).answers == ["a", "b"]
    q.branches[0][0].subject, q.branches[0][0].object = "?event", "?company"
    with pytest.raises(ValueError, match="type"):
        validate_query(q, graph())


def test_unsupported_and_unresolved_facts_do_not_create_answers():
    from webshaper.query import execute
    b = graph()
    b.evidence[1].support_status = "unknown"
    assert execute(query(), b).answers == []
    b.evidence[1].support_status = "supported"
    b.entities[0].resolution_status = "unresolved"
    assert execute(query(), b).answers == []


def test_absence_is_unknown_not_exclusion():
    from webshaper.query import membership
    decisions = membership(query(), graph(), ["a", "b"])
    assert decisions["a"]["decision"] == "included"
    assert decisions["b"]["decision"] == "unresolved"


def test_explicit_negative_evidence_can_exclude_a_candidate():
    from webshaper.models import Query
    from webshaper.query import membership
    b = graph()
    b.facts[4].polarity = "negative"
    q = Query(branches=[[{"subject":"?company", "predicate":"has_funding_event", "object":"b1"}]])
    decisions = membership(q, b, ["a", "b"])
    assert decisions["b"]["decision"] == "excluded"
    assert decisions["a"]["decision"] == "unresolved"


def test_disconnected_event_constraints_rejected():
    from webshaper.query import validate_query
    q = query()
    q.branches[0][-1].subject = "?different_event"
    with pytest.raises(ValueError, match="disconnected"):
        validate_query(q, graph())


def test_publication_date_is_not_retrieval_or_effective_date(tmp_path):
    from webshaper.sources import SourceStore
    from webshaper.query import eligible_facts
    store = SourceStore(tmp_path)
    b = graph()
    source = store.capture_text("test", "test", "test", date(2026, 1, 1))
    for e in b.evidence:
        e.source_id = source.source_id
    assert eligible_facts(b, [source], date(2025, 12, 31), False) == []
    assert len(eligible_facts(b, [source], date(2025, 12, 31), True)) == 12


def test_event_id_mismatch_is_rejected():
    from webshaper.query import validate_bundle
    b = graph()
    b.facts[1].event_id = "b1"
    with pytest.raises(ValueError, match="event"):
        validate_bundle(b)


def test_future_conflict_does_not_erase_a_historical_fact(tmp_path):
    from webshaper.models import Bundle, Entity, Fact, Evidence
    from webshaper.sources import SourceStore
    from webshaper.query import eligible_facts
    store = SourceStore(tmp_path)
    old = store.capture_text("old", "old", "Atlas builds robots.", date(2024, 1, 1))
    new = store.capture_text("new", "new", "Atlas no longer builds robots.", date(2025, 1, 1))
    entities = [Entity(entity_id=i, name=i, kind=k, identifiers=[i], resolution_status="resolved")
                for i, k in [("atlas", "company"), ("robot", "product")]]
    facts = [Fact(claim_id="old", subject_id="atlas", predicate="builds", object_id_or_value="robot", event_id=None,
                  valid_time={"start":"2024-01-01", "end":"2024-12-31"}, evidence_ids=["eold"], resolution_status="resolved"),
             Fact(claim_id="new", subject_id="atlas", predicate="builds", object_id_or_value="robot", event_id=None,
                  valid_time={"start":"2025-01-01"}, evidence_ids=["enew"], resolution_status="resolved", polarity="negative")]
    evidence = [Evidence(evidence_id=e, source_id=s.source_id, span_start=0, span_end=len(store.read(s)), span_text=store.read(s),
                         claim_id=c, support_status="supported") for e,s,c in [("eold",old,"old"),("enew",new,"new")]]
    bundle = Bundle(entities=entities, facts=facts, evidence=evidence)
    assert [f.claim_id for f in eligible_facts(bundle, [old,new], date(2024,6,1))] == ["old"]


def test_literal_values_canonicalize_but_company_names_do_not_merge():
    from webshaper.generation import normalize_extraction, Extraction
    data = Extraction(entities=[
        {"entity_id":"s_one:Series A", "name":"Series A", "kind":"category", "resolution_status":"resolved"},
        {"entity_id":"s_two:Series A", "name":"Series A", "kind":"category", "resolution_status":"resolved"},
        {"entity_id":"s_one:Atlas", "name":"Atlas", "kind":"company", "resolution_status":"resolved"},
        {"entity_id":"s_two:Atlas", "name":"Atlas", "kind":"company", "resolution_status":"unresolved"},
    ], facts=[])
    result = normalize_extraction(data, {"s_one", "s_two"})
    assert len([e for e in result.entities if e.kind == "category"]) == 1
    assert len([e for e in result.entities if e.kind == "company"]) == 2
    assert next(e for e in result.entities if e.entity_id == "s_one:Atlas").identifiers == ["s_one:Atlas"]
    assert next(e for e in result.entities if e.entity_id == "s_two:Atlas").resolution_status == "unresolved"


def test_duplicate_original_literal_ids_cannot_silently_retarget_facts():
    from webshaper.generation import normalize_extraction, Extraction
    data = Extraction(entities=[
        {"entity_id":"s:Atlas", "name":"Atlas", "kind":"company", "resolution_status":"resolved"},
        {"entity_id":"year", "name":"2024", "kind":"year", "resolution_status":"resolved"},
        {"entity_id":"year", "name":"2025", "kind":"year", "resolution_status":"resolved"},
    ], facts=[{"subject_id":"s:Atlas", "predicate":"founded_year", "object_id_or_value":"year",
               "event_id":None, "valid_time":{"start":"2024-01-01"}, "resolution_status":"resolved",
               "polarity":"positive", "quotes":[{"source_id":"s", "quote":"Founded in 2024.", "start":None}]}])
    with pytest.raises(ValueError, match="duplicate original entity"):
        normalize_extraction(data, {"s"})
