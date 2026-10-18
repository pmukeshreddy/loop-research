from test_validation import candidate

import json
from contextlib import contextmanager

import pytest


@contextmanager
def export_journal(tmp_path, *, research_mode="open_web", mutate=None, attempts=None, validated=True):
    """Scripted export records and local snapshots; never model or web observations."""
    from test_query import graph
    from webshaper.fixtures import fixture_config
    from webshaper.sources import SourceStore
    from webshaper.storage import Journal

    config = fixture_config()
    config.research_mode = research_mode
    c = candidate()
    if research_mode == "open_web":
        c.task.corpus_id = None
        c.task.allowed_tools = ["web_search"]
    c.task.research_mode = research_mode
    c.graph_id = "PRIVATE_GRAPH_SENTINEL"
    c.answer = ["PRIVATE_REFERENCE_SENTINEL"]
    c.cell_evidence = {"PRIVATE_URL_SENTINEL": ["PRIVATE_PASSAGE_SENTINEL"]}
    c.task.scope.description = "PRIVATE_SCOPE_SENTINEL"
    source = SourceStore(tmp_path / "sources").capture_text(
        "https://example.invalid/PRIVATE_URL_SENTINEL", "PRIVATE_TITLE_SENTINEL",
        "PRIVATE_PASSAGE_SENTINEL", c.task.as_of, redistributable=True)
    records = {"frozen": {"config": config.model_dump(mode="json"), "prompt_version": "scripted-export"},
               "candidate": c.model_dump(mode="json"), "final": c.model_dump(mode="json"),
               "validation": {"task_id": c.task.task_id, "research_mode": research_mode,
                              "solver_attempts": attempts or []}}
    if mutate:
        mutate(records)
    with Journal(tmp_path / "run.sqlite", records["frozen"], config.budget) as journal:
        journal.record("graphs", c.graph_id, {"graph_id": c.graph_id, "bundle": graph().model_dump(mode="json"),
                                              "sources": [source.model_dump(mode="json")]})
        journal.record("candidates", c.task.task_id, records["candidate"])
        journal.put("final_candidates", [records["final"]] if validated else [])
        journal.put("status", "complete" if validated else "paused")
        if validated:
            journal.record("validations", c.task.task_id, records["validation"])
        yield journal, config


def jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_open_web_export_uses_public_allowlist_and_retains_private_evidence(tmp_path):
    from webshaper.export import export_dataset

    with export_journal(tmp_path) as (journal, config):
        stats = export_dataset(journal, config, tmp_path)
    output = tmp_path / "export"
    tasks = jsonl(output / "public/tasks.jsonl")
    assert set(tasks[0]) == {"task_id", "question", "answer_schema", "as_of", "allowed_tools",
                              "data_mode", "research_mode"}
    assert tasks[0]["allowed_tools"] == ["web_search"]
    assert tasks == jsonl(output / "tasks.jsonl")
    assert (output / "public/corpus.jsonl").read_text() == ""
    assert all("PRIVATE_" not in path.read_text() for path in (output / "public").rglob("*") if path.is_file())
    assert "PRIVATE_REFERENCE_SENTINEL" in (output / "references.jsonl").read_text()
    assert "PRIVATE_URL_SENTINEL" in (output / "sources.jsonl").read_text()
    assert "PRIVATE_GRAPH_SENTINEL" in (output / "graphs.jsonl").read_text()
    assert stats["research_mode"] == "open_web"
    assert json.loads((output / "manifest.json").read_text())["research_mode"] == "open_web"
    for name in ("references.jsonl", "provenance.jsonl"):
        assert jsonl(output / name)[0]["research_mode"] == "open_web"


@pytest.mark.parametrize("record", ["frozen", "candidate", "final", "validation"])
@pytest.mark.parametrize("mode", [None, "legacy_corpus"])
def test_open_web_export_rejects_missing_or_legacy_record_modes(tmp_path, record, mode):
    from webshaper.export import export_dataset

    def mutate(records):
        value = records[record]
        value = value["config"] if record == "frozen" else value["task"] if record in ("candidate", "final") else value
        if mode is None:
            value.pop("research_mode")
        else:
            value["research_mode"] = mode

    with export_journal(tmp_path, mutate=mutate) as (journal, config):
        with pytest.raises(ValueError, match="research.mode"):
            export_dataset(journal, config, tmp_path)
    assert not (tmp_path / "export/public/tasks.jsonl").exists()


def test_export_cannot_override_original_generation_mode(tmp_path):
    from webshaper.export import export_dataset

    with export_journal(tmp_path, research_mode="legacy_corpus") as (journal, config):
        config.research_mode = "open_web"
        with pytest.raises(ValueError, match="research.mode"):
            export_dataset(journal, config, tmp_path)


def test_historical_browsing_records_remain_legacy_corpus_metrics(tmp_path):
    from webshaper.export import export_dataset

    def historical(records):
        records["frozen"]["config"].pop("research_mode")
        records["candidate"]["task"].pop("research_mode")
        records["final"]["task"].pop("research_mode")
        records["validation"].pop("research_mode")

    with export_journal(tmp_path, research_mode="legacy_corpus", mutate=historical,
                        attempts=[{"mode": "browsing", "success": True}]) as (journal, config):
        stats = export_dataset(journal, config, tmp_path)
    assert stats["research_mode"] == "legacy_corpus"
    assert stats["browsing_attempts"] == stats["legacy_corpus_browsing_attempts"] == 1
    assert stats["legacy_corpus_browsing_success_rate"] == 1
    assert stats["open_web_observed_attempts"] == 0
    assert stats["open_web_success_rate"] is None


def test_web_metrics_require_completed_search_and_page_read_and_keep_failures_separate(tmp_path):
    from webshaper.export import export_dataset

    attempts = [{"mode": "open_web", "call_id": "no-tools", "success": True, "browsing_observed": True,
                 "failure_category": "no_browsing", "observation": {"web_events": []}},
                {"mode": "open_web", "call_id": "access", "success": False, "browsing_observed": False,
                 "failure_category": "access_error", "observation": {"web_events": []}},
                {"mode": "open_web", "call_id": "budget", "success": False, "browsing_observed": False,
                 "failure_category": "budget_exhausted", "observation": {"web_events": []}},
                {"mode": "open_web", "call_id": "observed", "success": True, "browsing_observed": True,
                 "failure_category": None, "observation": {"web_events": [
                     {"status": "completed", "action": {"type": "search", "query": "scripted"}},
                     {"status": "completed", "action": {"type": "open_page", "url": "https://example.invalid"}}]}}]
    with export_journal(tmp_path, attempts=attempts) as (journal, config):
        stats = export_dataset(journal, config, tmp_path)
    assert stats["open_web_attempts"] == 4
    assert stats["open_web_observed_attempts"] == stats["browsing_attempts"] == 1
    assert stats["open_web_success_rate"] == .25
    assert stats["browsing_success_rate"] == 1
    assert stats["open_web_failure_categories"] == {"no_browsing": 1, "access_error": 1, "budget_exhausted": 1}
    assert stats["legacy_corpus_browsing_attempts"] == 0


def test_paused_web_attempts_and_trace_records_are_exported_privately(tmp_path):
    from webshaper.export import export_dataset

    attempt = {"task_id": "task", "mode": "open_web", "call_id": "paused-call", "success": False,
               "browsing_observed": False, "failure_category": "budget_exhausted"}
    trace = {"call_id": "paused-call", "role": "solver", "operation": "web_solver", "cache_key": "key",
             "web_events": [], "visited_urls": ["https://example.invalid/PRIVATE_URL_SENTINEL"],
             "tokens": 10, "searches": 1, "latency_seconds": 1.5, "failures": ["budget_exhausted"]}
    with export_journal(tmp_path, validated=False) as (journal, config):
        journal.record("web_attempts", "paused-call", attempt)
        journal.record("web_traces", "paused-call", trace)
        for kind in ("web_evidence", "web_alternatives", "web_shortcuts"):
            journal.record(kind, "paused-call", {"task_id": "task", "private": "PRIVATE_EVIDENCE_SENTINEL"})
        stats = export_dataset(journal, config, tmp_path)
    output = tmp_path / "export"
    assert jsonl(output / "web_traces.jsonl") == [trace]
    assert jsonl(output / "web_attempts.jsonl") == [attempt]
    for name in ("web_evidence", "web_alternatives", "web_shortcuts"):
        assert "PRIVATE_EVIDENCE_SENTINEL" in (output / (name + ".jsonl")).read_text()
    assert stats["open_web_attempts"] == 1
    assert stats["open_web_failure_categories"] == {"budget_exhausted": 1}
    assert stats["open_web_observed_attempts"] == 0
    assert not list((output / "public").glob("web_*.jsonl"))


def test_identical_legacy_attempts_are_not_collapsed(tmp_path):
    from webshaper.export import export_dataset

    attempts = [{"mode": "browsing", "success": True}, {"mode": "browsing", "success": True}]
    with export_journal(tmp_path, research_mode="legacy_corpus", attempts=attempts) as (journal, config):
        stats = export_dataset(journal, config, tmp_path)
    assert stats["legacy_corpus_browsing_attempts"] == 2


def test_validation_result_replaces_same_journal_attempt_for_metrics(tmp_path):
    from webshaper.export import export_dataset

    attempt = {"mode": "open_web", "call_id": "same-call", "success": True, "browsing_observed": True,
               "failure_category": None, "observation": {"web_events": [
                   {"status": "completed", "action": {"type": "search"}},
                   {"status": "completed", "action": {"type": "open_page"}}]}}
    with export_journal(tmp_path, attempts=[attempt]) as (journal, config):
        journal.record("web_attempts", "same-call", {**attempt, "success": False, "failure_category": "ungraded"})
        stats = export_dataset(journal, config, tmp_path)
    assert stats["open_web_attempts"] == 1
    assert stats["open_web_success_rate"] == 1
    assert stats["open_web_failure_categories"] == {}


@pytest.mark.parametrize("research_mode,attempt_mode", [("open_web", "browsing"), ("legacy_corpus", "open_web")])
def test_validation_cannot_mix_legacy_and_open_web_attempts(tmp_path, research_mode, attempt_mode):
    from webshaper.export import export_dataset

    with export_journal(tmp_path, research_mode=research_mode,
                        attempts=[{"mode": attempt_mode, "success": True}]) as (journal, config):
        with pytest.raises(ValueError, match="research.mode"):
            export_dataset(journal, config, tmp_path)


@pytest.mark.parametrize("status,action,expected", [
    ("completed", None, 0), ("in_progress", {"type": "open_page"}, 0),
    ("item.completed", {"type": "open_page"}, 1), ("completed", {"type": "find_in_page"}, 1),
])
def test_web_metrics_handle_unknown_and_incomplete_tool_actions(tmp_path, status, action, expected):
    from webshaper.export import export_dataset

    attempt = {"mode": "open_web", "success": True, "browsing_observed": True, "failure_category": None,
               "observation": {"web_events": [{"status": "completed", "action": {"type": "search"}},
                                                {"status": status, "action": action}]}}
    with export_journal(tmp_path, attempts=[attempt]) as (journal, config):
        stats = export_dataset(journal, config, tmp_path)
    assert stats["open_web_observed_attempts"] == expected
    assert stats["open_web_success_rate"] == expected


def test_paused_metrics_use_final_attempt_phase_regardless_of_record_order(tmp_path):
    from webshaper.export import export_dataset

    attempt = {"mode": "open_web", "call_id": "same-call", "success": True, "browsing_observed": True,
               "failure_category": None, "observation": {"web_events": [
                   {"status": "completed", "action": {"type": "search"}},
                   {"status": "completed", "action": {"type": "open_page"}}]}}
    with export_journal(tmp_path, validated=False) as (journal, config):
        journal.record("web_attempts", "a-final", {**attempt, "phase": "final"})
        journal.record("web_attempts", "z-solver", {**attempt, "phase": "solver_complete", "success": False})
        stats = export_dataset(journal, config, tmp_path)
    assert stats["open_web_attempts"] == 1
    assert stats["open_web_success_rate"] == 1
    assert len(jsonl(tmp_path / "export/web_attempts.jsonl")) == 2


def test_open_web_call_metrics_count_completed_calls_without_validation(tmp_path):
    from webshaper.export import export_dataset

    with export_journal(tmp_path, validated=False) as (journal, config):
        for call_id, role in [("closed", "solver:web_closed"), ("solve", "solver:web_solver"),
                              ("grade", "verifier:web_grade")]:
            journal.reserve(call_id, role, 0, 10, 0)
            journal.complete(call_id, {"metadata": {"call_id": call_id}}, 0, 10)
        journal.record("web_attempts", "solve", {"mode": "open_web", "call_id": "solve", "success": False,
                       "browsing_observed": False, "failure_category": "no_browsing"})
        stats = export_dataset(journal, config, tmp_path)
    assert stats["completed_solver_responses"] == 2
    assert stats["completed_solver_grades"] == 1
    assert stats["solver_responses_without_validation_record"] == 2


def test_separate_web_captures_remain_private_and_hash_checked(tmp_path):
    from webshaper.export import export_dataset
    from webshaper.sources import SourceStore

    with export_journal(tmp_path) as (journal, config):
        store = SourceStore(tmp_path / "web_sources")
        source = store.capture_text("https://example.invalid/PRIVATE_SOLVER_URL", "Cited page",
                                    "PRIVATE_SOLVER_CAPTURE", config.as_of)
        export_dataset(journal, config, tmp_path)
        assert jsonl(tmp_path / "export/web_sources.jsonl")[0]["source_id"] == source.source_id
        manifest = json.loads((tmp_path / "export/manifest.json").read_text())
        assert manifest["web_source_store"] == "../web_sources"
        assert "web_sources.jsonl" in manifest["private_files"]
        assert "PRIVATE_SOLVER" not in (tmp_path / "export/public/tasks.jsonl").read_text()
        (store.root / source.text_path).write_text("corrupted")
        with pytest.raises(ValueError, match="hash"):
            export_dataset(journal, config, tmp_path)


@pytest.mark.parametrize("retrospective", [False, True])
@pytest.mark.parametrize("redistributable", [False, True])
def test_public_corpus_matches_temporal_access_and_keeps_private_snapshots(tmp_path, retrospective, redistributable):
    from webshaper.fixtures import fixture_config
    from webshaper.models import SourceInput
    from webshaper.pipeline import run
    from webshaper.sources import SourceStore
    from webshaper.validation import documents_for
    config = fixture_config()
    config.scope.allow_retrospective = retrospective
    for name, published in [("future", "2026-01-01"), ("undated", None)]:
        path = tmp_path / (name + ".txt")
        path.write_text("FICTIONAL EXTRA SOURCE: " + name)
        config.sources.append(SourceInput(origin=str(path), title=name, published_at=published,
                              date_basis="fixture", category="fixture", redistributable=redistributable))
    root = tmp_path / "run"
    assert run(config, root)["accepted_tasks"] == 1
    entries = [json.loads(line) for line in (root / "export/public/corpus.jsonl").read_text().splitlines()]
    origins = {entry["url"] for entry in entries}
    expected = {s.origin for s in config.sources[:2]}
    if retrospective:
        expected.add(str(tmp_path / "future.txt"))
    assert origins == expected  # Exclude entire metadata entries, even when text is withheld.
    store = SourceStore(root / "sources")
    sources = store.all()
    assert {d["url"] for d in documents_for(sources, store, config.as_of, retrospective)} == expected
    assert len(sources) == 4
    assert len((root / "export/sources.jsonl").read_text().splitlines()) == 4
    for source in sources:
        assert store.read(source)  # Private raw/text snapshots remain intact and hash-valid.


def test_dedup_discards_paraphrase_but_preserves_distinct_query():
    from webshaper.export import deduplicate
    a = candidate()
    b = a.model_copy(deep=True)
    b.task.task_id, b.task.question = "paraphrase", "A paraphrase asking the identical structured question."
    b.seed_id = "different_seed"
    kept, dropped = deduplicate([a, b])
    assert [c.task.task_id for c in kept] == ["task"]
    assert dropped[0]["reason_codes"] == ["duplicate_query_answer"]


def test_lineages_answers_and_duplicate_sources_stay_in_same_partition():
    from webshaper.export import partitions
    a = candidate()
    b = a.model_copy(deep=True)
    b.task.task_id, b.answer = "descendant", ["b"]
    c = a.model_copy(deep=True)
    c.task.task_id, c.seed_id, c.answer = "other", "other_seed", ["c"]
    source_groups = {"task": {"page1"}, "descendant": {"page2"}, "other": {"page2"}}
    result = partitions([a, b, c], source_groups)
    assert result["task"] == result["descendant"] == result["other"]


def test_reference_conflict_rejects_both_copies():
    from webshaper.export import deduplicate
    a = candidate()
    b = a.model_copy(deep=True)
    b.task.task_id, b.answer = "conflict", ["b"]
    kept, dropped = deduplicate([a, b])
    assert kept == []
    assert len(dropped) == 2


def test_canonical_union_does_not_permute_unrelated_branch_variables():
    from webshaper.query import canonical
    from webshaper.models import Query
    import time
    branches = []
    for b in range(2):
        branches.append([{"subject": "?company", "predicate": "builds", "object": f"?p{b}_{i}"} for i in range(7)])
    query = Query(branches=branches)
    start = time.monotonic()
    value = canonical(query)
    assert value and time.monotonic() - start < 2
