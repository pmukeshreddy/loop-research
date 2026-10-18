from datetime import date

from test_query import graph, query


def candidate():
    from webshaper.models import Candidate, PublicTask, Scope
    return Candidate(task=PublicTask(task_id="task", question="As of 2025-12-31, which company raised Series A in 2025?",
                                    as_of=date(2025, 12, 31), scope=Scope(), corpus_id="corpus",
                                    allowed_tools=["corpus"], data_mode="fixture"), query=query(), answer=["a"],
                     seed_id="task", parent_id=None)


def test_answer_drift_and_answer_leakage_are_rejected():
    from webshaper.validation import deterministic_checks
    c = candidate()
    c.answer = ["b"]
    checks = deterministic_checks(c, graph(), [], None, check_spans=False)
    assert next(x for x in checks if x.name == "reference_answer").status == "fail"
    c = candidate()
    # Avoid one-letter entities as a leakage fixture.
    b = graph()
    b.entities[0].name = "Atlas Robotics"
    c.task.question += " The answer is Atlas Robotics."
    checks = deterministic_checks(c, b, [], None, check_spans=False)
    assert next(x for x in checks if x.name == "answer_leakage").status == "fail"


def test_unknown_semantic_checks_cannot_be_accepted():
    from webshaper.validation import decide
    from webshaper.models import Check
    assert decide([Check(name="evidence", status="unknown")], 0, 1) == "revise"
    assert decide([Check(name="evidence", status="unknown")], 1, 1) == "reject"


def test_exhaustive_universe_unknown_blocks_acceptance():
    from webshaper.validation import deterministic_checks
    from webshaper.models import Scope
    c = candidate()
    c.task.scope = Scope(mode="corpus_bounded", candidate_universe=["a", "b"])
    checks = deterministic_checks(c, graph(), [], None, check_spans=False)
    assert next(x for x in checks if x.name == "completeness").status == "unknown"


def test_solver_payload_contains_no_reference_or_graph():
    from webshaper.validation import solver_payload
    c = candidate()
    payload = solver_payload(c, [], closed_book=True)
    assert set(payload) == {"task", "mode", "documents"}
    assert payload["documents"] == []
    assert payload["task"]["allowed_tools"] == []
    assert not any(k in payload for k in ("answer", "query", "parent_id", "cell_evidence"))


def test_wrong_citations_do_not_count_as_solvable(tmp_path):
    from webshaper.validation import citations_valid
    from webshaper.models import SolverAnswer
    docs = [{"source_id": "s", "text": "Atlas builds robots."}]
    response = SolverAnswer(answer=["Atlas"], citations=[{"source_id":"s", "quote":"invented"}], uncertainty="")
    assert citations_valid(response, docs) is False


def test_redundant_clue_is_detected():
    from webshaper.expansion import redundant, replace_leaf
    from webshaper.models import Query
    from test_expansion import expansion_graph
    b, q = expansion_graph()
    sub = Query(target="?i", answer_type="investor", branches=[[{"subject":"?i", "predicate":"portfolio_company", "object":"anchor"}]])
    merged, _, atoms = replace_leaf(q, "i", sub, b)
    assert redundant(merged, atoms, b) is True
