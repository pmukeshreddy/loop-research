import json

import pytest


def test_fixture_pipeline_exports_and_resumes_without_more_calls(tmp_path):
    from webshaper.pipeline import run
    from webshaper.fixtures import fixture_config
    config = fixture_config()
    result = run(config, tmp_path / "run")
    assert result["accepted_tasks"] == 1
    assert result["data_mode"] == "fixture"
    export = tmp_path / "run" / "export"
    task = json.loads((export / "tasks.jsonl").read_text().splitlines()[0])
    reference = json.loads((export / "references.jsonl").read_text().splitlines()[0])
    assert task["data_mode"] == "fixture"
    assert "answer" not in task and "reference_query" not in task
    assert reference["answer_entities_or_rows"] == ["atlas"]
    assert reference["actual_layer"] == 1
    assert len(json.loads((export / "validation.jsonl").read_text().splitlines()[-1])["solver_attempts"]) >= 5
    again = run(config, tmp_path / "run")
    assert again["usage"] == result["usage"]


def test_live_config_rejects_fixture_provider():
    from webshaper.fixtures import fixture_config
    from webshaper.models import RunConfig
    config = fixture_config().model_dump(mode="json")
    config["mode"] = "live"
    with pytest.raises(ValueError, match="fixture"):
        RunConfig.model_validate(config)


def test_live_pipeline_will_not_spend_paid_budget():
    from webshaper.models import RunConfig
    with pytest.raises(ValueError, match="paid budget"):
        RunConfig(as_of="2025-12-31", budget={"max_usd": 1})


def test_subscription_limit_stops_dispatch_immediately(tmp_path, monkeypatch):
    from webshaper.fixtures import fixture_config, FixtureProvider
    from webshaper.pipeline import run
    from webshaper.storage import SubscriptionLimit
    from webshaper.prompts import PROMPTS
    original = FixtureProvider.invoke
    attempts = []
    def limited(self, prompt, payload, schema, web=False):
        if prompt == PROMPTS["solver"]:
            attempts.append(1)
            if len(attempts) == 1:
                raise SubscriptionLimit("test subscription limit")
        return original(self, prompt, payload, schema, web)
    monkeypatch.setattr(FixtureProvider, "invoke", limited)
    stats = run(fixture_config(), tmp_path / "run")
    assert stats["status"] == "paused"
    assert len(attempts) == 1


def test_tampered_snapshot_cannot_be_exported_as_valid(tmp_path):
    from webshaper.fixtures import fixture_config
    from webshaper.pipeline import run
    c = fixture_config()
    run(c, tmp_path / "run")
    source = next((tmp_path / "run/sources/text").glob("*.txt"))
    source.write_text("CORRUPTED SNAPSHOT")
    with pytest.raises(ValueError, match="hash"):
        run(c, tmp_path / "run")


def test_duplicate_tasks_do_not_end_generation_early(tmp_path):
    from webshaper.fixtures import fixture_config
    from webshaper.pipeline import run
    c = fixture_config()
    c.target_tasks, c.max_seed_attempts, c.layers = 2, 3, 0
    stats = run(c, tmp_path / "run")
    assert stats["accepted_tasks"] == 1  # this fixture deliberately only generates one semantic task
    assert stats["attempted_versions"] == 3


def test_resume_after_final_checkpoint_does_not_duplicate_a_family(tmp_path, monkeypatch):
    from webshaper.fixtures import fixture_config
    from webshaper.pipeline import run
    from webshaper.storage import Journal
    c = fixture_config()
    c.target_tasks, c.max_seed_attempts, c.layers = 2, 2, 0
    original = Journal.put
    interrupted = []
    def interrupt_after_final(self, key, value):
        original(self, key, value)
        if key == "final_candidates" and not interrupted:
            interrupted.append(True)
            raise KeyboardInterrupt()
    monkeypatch.setattr(Journal, "put", interrupt_after_final)
    run(c, tmp_path / "run")
    monkeypatch.setattr(Journal, "put", original)
    run(c, tmp_path / "run")
    import sqlite3
    db = sqlite3.connect(tmp_path / "run/run.sqlite")
    finals = json.loads(db.execute("SELECT value FROM kv WHERE key='final_candidates'").fetchone()[0])
    db.close()
    assert [f["seed_id"] for f in finals] == ["seed-0000", "seed-0001"]


def test_unknown_provider_outcome_does_not_trigger_generation_retry(tmp_path, monkeypatch):
    from webshaper.fixtures import fixture_config, FixtureProvider
    from webshaper.pipeline import run
    calls = []
    original = FixtureProvider.invoke
    def malformed(self, *args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise json.JSONDecodeError("incomplete transport response", "", 0)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(FixtureProvider, "invoke", malformed)
    stats = run(fixture_config(), tmp_path / "run")
    assert stats["status"] == "paused"
    assert len(calls) == 1
    assert stats["usage"]["uncertain_calls"] == 1


def test_bounded_revision_preserves_previous_candidate_and_feedback(tmp_path, monkeypatch):
    from webshaper.fixtures import fixture_config, FixtureProvider
    from webshaper.pipeline import run
    from webshaper.prompts import PROMPTS
    original = FixtureProvider.invoke
    feedback = []
    def revise(self, prompt, payload, schema, web=False):
        result = original(self, prompt, payload, schema, web)
        if prompt == PROMPTS["seed"]:
            feedback.append(payload["revision_feedback"])
            if not payload["revision_feedback"]:
                result.data["question"] = result.data["question"].replace("As of 2025-12-31, ", "")
        return result
    monkeypatch.setattr(FixtureProvider, "invoke", revise)
    config = fixture_config()
    config.layers = 0
    stats = run(config, tmp_path / "run")
    records = [json.loads(line) for line in (tmp_path / "run/export/validation.jsonl").read_text().splitlines()]
    assert stats["accepted_tasks"] == 1
    assert [r["decision"] for r in records] == ["revise", "accept"]
    assert "explicit_cutoff" in feedback[1][0]
    assert "2025-12-31" in feedback[1][0]


def test_two_layers_expand_new_leaves_only_in_the_second_layer(tmp_path):
    from webshaper.fixtures import fixture_config
    from webshaper.pipeline import run
    c = fixture_config()
    c.layers = 2
    stats = run(c, tmp_path / "run")
    assert stats["depth_distribution"] == {"2": 1}
    records = [json.loads(line) for line in (tmp_path / "run/export/provenance.jsonl").read_text().splitlines()]
    leaves = {(r["layer"], r["expanded_leaf"]) for r in records if r["expanded_leaf"]}
    assert (1, "cedar") in leaves and (2, "orion") in leaves


def test_explicit_limit_retry_reuses_successful_calls(tmp_path, monkeypatch):
    from webshaper.fixtures import fixture_config, FixtureProvider
    from webshaper.pipeline import run
    from webshaper.storage import SubscriptionLimit
    from webshaper.prompts import PROMPTS
    original = FixtureProvider.invoke
    limited = []
    def once(self, prompt, payload, schema, web=False):
        if prompt == PROMPTS["solver"] and not limited:
            limited.append(True)
            raise SubscriptionLimit("reset required")
        return original(self, prompt, payload, schema, web)
    monkeypatch.setattr(FixtureProvider, "invoke", once)
    c = fixture_config()
    first = run(c, tmp_path / "run")
    second = run(c, tmp_path / "run")
    assert first["status"] == second["status"] == "paused"
    assert first["usage"] == second["usage"]
    final = run(c, tmp_path / "run", retry_limited=True)
    assert final["accepted_tasks"] == 1
    assert final["usage"]["calls"] == 30  # 29 normal calls plus the retained limited attempt


def test_capture_coverage_survives_extraction_rejection(tmp_path, monkeypatch):
    from webshaper.fixtures import fixture_config, FixtureProvider
    from webshaper.pipeline import run
    from webshaper.prompts import PROMPTS
    original = FixtureProvider.invoke
    def unsupported(self, prompt, payload, schema, web=False):
        result = original(self, prompt, payload, schema, web)
        if prompt == PROMPTS["extract"]:
            result.data["facts"][0]["quotes"][0]["quote"] = "invented text"
        return result
    monkeypatch.setattr(FixtureProvider, "invoke", unsupported)
    stats = run(fixture_config(), tmp_path / "run")
    assert stats["status"] == "failed" and stats["accepted_tasks"] == 0
    assert stats["source_count"] == 2
    assert stats["source_errors"] == 0
    assert stats["extraction_errors"] == 2


def test_judge_can_resolve_every_claim_to_exact_evidence_without_solver_leakage(tmp_path, monkeypatch):
    from webshaper.fixtures import fixture_config, FixtureProvider
    from webshaper.pipeline import run
    from webshaper.prompts import PROMPTS
    original = FixtureProvider.invoke
    judgments = []
    def inspect(self, prompt, payload, schema, web=False):
        if prompt == PROMPTS["judge"]:
            judgments.append(payload)
        if prompt == PROMPTS["solver"]:
            assert set(payload) == {"task", "mode", "documents"}
        return original(self, prompt, payload, schema, web)
    monkeypatch.setattr(FixtureProvider, "invoke", inspect)
    run(fixture_config(), tmp_path / "run")
    assert judgments
    for payload in judgments:
        spans = {e["evidence_id"]: e for e in payload["evidence"]}
        documents = {d["source_id"]: d for d in payload["documents"]}
        for claim in payload["claims"]:
            for eid in claim["evidence_ids"]:
                span = spans[eid]
                document = documents[span["source_id"]]
                assert document["text"][span["span_start"]:span["span_end"]] == span["span_text"]
                assert "date_basis" in document and "retrieved_at" in document


def test_extraction_revision_receives_the_concrete_failure(tmp_path, monkeypatch):
    from webshaper.fixtures import fixture_config, FixtureProvider
    from webshaper.pipeline import run
    from webshaper.prompts import PROMPTS
    original = FixtureProvider.invoke
    seen = []
    def revise(self, prompt, payload, schema, web=False):
        result = original(self, prompt, payload, schema, web)
        if prompt == PROMPTS["extract"]:
            seen.append(payload.get("revision_feedback", []))
            if len(seen) == 1:
                result.data["facts"][0]["quotes"][0]["quote"] = "invented text"
        return result
    monkeypatch.setattr(FixtureProvider, "invoke", revise)
    stats = run(fixture_config(), tmp_path / "run")
    assert stats["accepted_tasks"] == 1
    assert len(seen) == 2 and seen[0] == []
    assert len(seen[1]) == 1 and seen[1][0].startswith("invalid evidence span:")
    assert "invented text" in seen[1][0] and "source s_" in seen[1][0]


def test_quality_counts_seed_proposals_rejected_before_candidate_creation(tmp_path, monkeypatch):
    from webshaper.fixtures import fixture_config, FixtureProvider
    from webshaper.pipeline import run
    from webshaper.prompts import PROMPTS
    original = FixtureProvider.invoke
    def invalid(self, prompt, payload, schema, web=False):
        result = original(self, prompt, payload, schema, web)
        if prompt == PROMPTS["seed"]:
            result.data["query"] = None
            result.data["rejection_reason"] = "insufficient evidence"
        return result
    monkeypatch.setattr(FixtureProvider, "invoke", invalid)
    config = fixture_config()
    config.max_seed_attempts = 1
    stats = run(config, tmp_path / "run")
    assert stats["attempted_versions"] == stats["rejection_records"] == 2
    assert stats["evaluated_versions"] == 0
    assert stats["source_errors"] == 0


def test_failed_expansion_evidence_retains_last_validated_parent(tmp_path, monkeypatch):
    from webshaper.fixtures import fixture_config
    from webshaper import pipeline
    def unavailable(*args, **kwargs):
        raise ValueError("built-in search unavailable")
    monkeypatch.setattr(pipeline, "discover", unavailable)
    stats = pipeline.run(fixture_config(), tmp_path / "run")
    assert stats["status"] == "completed"
    assert stats["accepted_tasks"] == 1
    assert stats["depth_distribution"] == {"0": 1}
    assert "expansion_evidence_unavailable" in stats["rejection_reasons"]


def test_natural_language_expansion_rejection_has_a_stable_reason_code(tmp_path, monkeypatch):
    from webshaper.fixtures import fixture_config, FixtureProvider
    from webshaper.pipeline import run
    from webshaper.prompts import PROMPTS
    original = FixtureProvider.invoke
    def reject(self, prompt, payload, schema, web=False):
        result = original(self, prompt, payload, schema, web)
        if prompt == PROMPTS["expand"]:
            result.data["subquery"] = None
            result.data["rejection_reason"] = "No dated distinguishing relationship is supported."
        return result
    monkeypatch.setattr(FixtureProvider, "invoke", reject)
    stats = run(fixture_config(), tmp_path / "run")
    assert set(stats["rejection_reasons"]) == {"no_valid_expansion"}


def test_partial_validation_attempts_remain_visible_after_subscription_pause(tmp_path, monkeypatch):
    from webshaper.fixtures import fixture_config, FixtureProvider
    from webshaper.pipeline import run
    from webshaper.prompts import PROMPTS
    from webshaper.storage import SubscriptionLimit
    original = FixtureProvider.invoke
    solver_calls = []
    def limited(self, prompt, payload, schema, web=False):
        if prompt == PROMPTS["solver"]:
            solver_calls.append(1)
            if len(solver_calls) == 2:
                raise SubscriptionLimit("fixture subscription limit")
        return original(self, prompt, payload, schema, web)
    monkeypatch.setattr(FixtureProvider, "invoke", limited)
    stats = run(fixture_config(), tmp_path / "run")
    assert stats["status"] == "paused"
    assert stats["attempted_versions"] == 1
    assert stats["evaluated_versions"] == 0
    assert stats["completed_solver_responses"] == stats["solver_responses_without_validation_record"] == 1
    assert stats["completed_solver_grades"] == 1
