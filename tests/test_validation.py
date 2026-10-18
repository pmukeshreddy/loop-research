from datetime import date

from test_query import graph, query

import json
import pytest


@pytest.mark.parametrize("max_revisions, decision", [(1, "revise"), (0, "reject")])
def test_correct_closed_book_answer_stops_all_downstream_calls(tmp_path, monkeypatch, max_revisions, decision):
    from webshaper.fixtures import fixture_config, FixtureProvider
    from webshaper.pipeline import run
    from webshaper.models import Candidate, Bundle, Source
    from webshaper.providers import ModelGateway
    from webshaper.storage import Journal
    from webshaper.sources import SourceStore
    from webshaper.validation import validate
    from webshaper.prompts import PROMPTS
    config = fixture_config()
    root = tmp_path / "baseline"
    run(config, root)
    records = [json.loads(s) for s in (root / "export/graphs.jsonl").read_text().splitlines()]
    # Rehydrate the actually validated fixture seed and expansion, not invented checks.
    import sqlite3
    db = sqlite3.connect(root / "run.sqlite")
    candidates = [Candidate.model_validate(json.loads(r[0])) for r in db.execute("SELECT value FROM records WHERE kind='candidates'")]
    db.close()
    child = next(c for c in candidates if c.layer == 1)
    parent = next(c for c in candidates if c.task.task_id == child.parent_id)
    saved_graph = next(g for g in records if g["graph_id"] == child.graph_id)
    config.max_revisions, config.shortcut_audit_rate = max_revisions, 1
    original = FixtureProvider.invoke
    closed_seen, downstream = [], []
    def answers_closed(self, prompt, payload, schema, web=False):
        if closed_seen:
            downstream.append((prompt, payload))
        response = original(self, prompt, payload, schema, web)
        if prompt == PROMPTS["solver"] and payload["mode"] == "closed_book":
            closed_seen.append(True)
            response.data["answer"] = ["Atlas Robotics"]
        return response
    monkeypatch.setattr(FixtureProvider, "invoke", answers_closed)
    with Journal(tmp_path / "validation.sqlite", {}, config.budget) as journal:
        gateway = ModelGateway(journal, {r: FixtureProvider(getattr(config, r)) for r in ("generator", "verifier", "solver")})
        result = validate(child, Bundle.model_validate(saved_graph["bundle"]),
                          [Source.model_validate(s) for s in saved_graph["sources"]],
                          SourceStore(root / "sources"), gateway, config, parent)
    assert closed_seen == [True]
    assert downstream == []
    assert result.decision == decision
    assert len(result.solver_attempts) == 1 and result.solver_attempts[0]["correct"]
    assert result.solver_attempts[0]["mode"] == "closed_book"
    assert any(c.name == "closed_book_screen" and c.status == "fail" for c in result.checks)
    assert any("closed_book_screen" in feedback for feedback in result.feedback)
    assert all(c.status == "pass" for c in result.checks if c.name != "closed_book_screen")
    assert {"exact_expansion", "nonredundant_expansion", "historical_evidence", "semantic_wording"} <= {c.name for c in result.checks}
    assert result.judge_config == config.verifier.model_dump(mode="json")
    assert result.audit_status == "fixture_only"


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
