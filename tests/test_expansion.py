import pytest
from test_query import graph, query


def expansion_graph():
    from webshaper.models import Entity, Fact, Evidence
    b = graph()
    b.entities.append(Entity(entity_id="anchor", name="Anchor", kind="company", identifiers=["anchor"], resolution_status="resolved"))
    b.facts.append(Fact(claim_id="portfolio", subject_id="i", predicate="portfolio_company", object_id_or_value="anchor",
                        event_id=None, valid_time={"start": "2024-01-01"}, evidence_ids=["ep"], resolution_status="resolved"))
    b.evidence.append(Evidence(evidence_id="ep", source_id="s", span_start=0, span_end=4, span_text="test",
                               claim_id="portfolio", support_status="supported"))
    q = query()
    q.branches[0].append(__import__("webshaper.models", fromlist=["Atom"]).Atom(subject="?event", predicate="investor", object="i"))
    return b, q


def test_expansion_preserves_answer_and_freezes_next_layer():
    from webshaper.expansion import leaf_constants, replace_leaf
    from webshaper.models import Query
    from webshaper.query import execute
    b, q = expansion_graph()
    frozen = leaf_constants(q, b)
    sub = Query(target="?i", answer_type="investor", branches=[[{"subject":"?i", "predicate":"portfolio_company", "object":"anchor"}]])
    expanded, _, _ = replace_leaf(q, "i", sub, b)
    assert frozen == ["i"]
    assert leaf_constants(expanded, b) == ["anchor"]
    assert execute(expanded, b).answers == ["a"]


def test_ambiguous_intermediate_rejected_even_if_final_answer_unchanged():
    from webshaper.expansion import replace_leaf
    from webshaper.models import Query
    b, q = expansion_graph()
    f = b.facts[-1].model_copy(deep=True)
    f.subject_id, f.claim_id = "j", "other"
    e = b.evidence[-1].model_copy(deep=True)
    e.evidence_id, e.claim_id = "other_e", "other"
    f.evidence_ids = ["other_e"]
    b.facts.append(f)
    b.evidence.append(e)
    sub = Query(target="?i", answer_type="investor", branches=[[{"subject":"?i", "predicate":"portfolio_company", "object":"anchor"}]])
    with pytest.raises(ValueError, match="intermediate_answer_changed"):
        replace_leaf(q, "i", sub, b)


def test_variable_capture_and_operational_filter_changes_blocked():
    from webshaper.expansion import replace_leaf
    from webshaper.models import Query
    b, q = expansion_graph()
    sub = Query(target="?event", answer_type="investor", branches=[[{"subject":"?event", "predicate":"portfolio_company", "object":"anchor"}]])
    merged, _, _ = replace_leaf(q, "i", sub, b)
    assert any(a.object == "?event" for a in merged.branches[0])
    assert any(a.subject not in ("?event", "?company") for a in merged.branches[0])
    with pytest.raises(ValueError, match="ineligible"):
        replace_leaf(q, "2025", sub, b)


def test_canonicalization_ignores_variable_names_and_atom_order():
    from webshaper.query import canonical
    q = query()
    renamed = q.model_copy(deep=True)
    for atom in renamed.branches[0]:
        atom.subject = atom.subject.replace("?event", "?funding")
        if isinstance(atom.object, str):
            atom.object = atom.object.replace("?event", "?funding")
    renamed.branches[0].reverse()
    assert canonical(q) == canonical(renamed)
