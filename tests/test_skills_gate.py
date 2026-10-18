
import pytest
from pydantic import ValidationError

from loop_research.gate import SkillGate, filter_edit, gate_decision
from loop_research.skills import (EditOp, Skill, apply_op, init_library, library_sha, load_skills,
                                  normalize_text, parse_skill, render_playbook, staged_library, write_skill)


@pytest.fixture
def library(tmp_path):
    directory = tmp_path / "skills"
    init_library(directory)
    return directory


def edit(**overrides):
    return EditOp.model_validate({"op": "add", "title": "Check independent sources",
        "body": "Compare independent sources before accepting a claim.", "applies_to": ["constraint"],
        "rationale": "A general verification method", "evidence_task_ids": ["fixture"], **overrides})


def test_skill_round_trip_and_staged_edit(library):
    before = library_sha(library)
    with staged_library(library, edit()) as (staged, op):
        skill = parse_skill(staged / (op.id + ".md"))
        assert skill.body == edit().body and skill.id == "sk_0001"
        assert load_skills(library) == []
        write_skill(staged, skill)
        assert parse_skill(staged / (op.id + ".md")) == skill
        apply_op(staged, edit(op="update", id=op.id, body="Check original sources before accepting a claim."))
        assert parse_skill(staged / (op.id + ".md")).body.startswith("Check original")
        apply_op(staged, edit(op="retire", id=op.id))
        assert parse_skill(staged / (op.id + ".md")).status == "retired"
    assert library_sha(library) == before


def test_word_limit_is_enforced():
    with pytest.raises(ValidationError, match="80 words"):
        edit(body=" ".join(["word"] * 81))


def test_playbook_selection_is_deterministic_under_cap(library, task):
    for ident in ["sk_0002", "sk_0001", "sk_0003"]:
        write_skill(library, Skill(id=ident, title="Check", body="Check authoritative sources.",
                                  applies_to=["wide"], source_tasks=["fixture"]))
    full = render_playbook(task, library)
    assert full.index("sk_0001") < full.index("sk_0002") < full.index("sk_0003")
    first_block_size = len(full.split("\n\n")[0]) + 2
    limited = render_playbook(task, library, first_block_size)
    assert "sk_0001" in limited and "sk_0002" not in limited
    assert len(limited) <= first_block_size
    assert render_playbook(task, library, 0) == ""


@pytest.mark.parametrize("text,index,expected", [
    ("Consult https://example.org for evidence.", set(), "URL"),
    ("Check sources from 2025.", set(), "numbers"),
    ("Check Fixture Entity before deciding.", {"fixture entity"}, "gold"),
    ("Check original sources before deciding.", {"fixture entity"}, None),
])
def test_leakage_filter(library, text, index, expected):
    reason = filter_edit(edit(body=text), library, index, .85)
    assert (reason is None) if expected is None else expected in reason


@pytest.mark.parametrize("gold,text,leaked", [
    ("art", "Compare partial results from different sources.", False),
    ("art", "Compare art sources.", True),
    ("land", "Compare island names with mainland sources.", False),
    ("land", "Check the land record.", True),
    ("new york", "Check New Yorkshire sources.", False),
    ("new york", "Check Renew York sources.", False),
    ("new york", "Check (NEW\nYORK) sources.", True),
    ("café", "Check cafés and cafeteria sources.", False),
    ("café", "Check café sources.", True),
    ("a.b", "Check a-b sources.", False),
    ("a.b", "Check (a.b) sources.", True),
    ("北京", "核实北京市的来源。", True),
    ("北京", "核实上海市的来源。", False),
    ("京", "核实京的来源。", False),
    ("京", "核实 京 来源。", False),
    ("東京", "東京都の出典を確認する。", True),
    ("서울", "서울시의 출처를 확인한다.", True),
])
def test_leakage_matches_tokens_and_cjk_phrases(library, gold, text, leaked):
    reason = filter_edit(edit(title="Verify evidence", body=text), library, {gold}, .85)
    assert reason == ("leakage: gold cell/entity text" if leaked else None)


def test_normalization_and_dedup(library):
    assert normalize_text(" Ｆｉｘｔｕｒｅ\n ENTITY ") == "fixture entity"
    apply_op(library, edit())
    assert "use update" in filter_edit(edit(), library, set(), .85)
    assert filter_edit(edit(op="update", id="sk_0001"), library, set(), .85) is None


@pytest.mark.parametrize("candidate,accepted", [({"a": .51, "b": .51}, True),
                                                 ({"a": .50, "b": .50}, False),
                                                 ({"a": .35, "b": .85}, False)])
def test_gate_accept_reject_logic(ctx, candidate, accepted):
    ctx.config.gate.max_regressions = 0
    result = gate_decision({"a": .5, "b": .5}, candidate, ctx.config.gate)
    assert result["accepted"] is accepted


def test_gate_cache_commit_and_replay(ctx, library):
    calls = []
    def scores(directory, key):
        calls.append((directory, key))
        return {"fixture-val": .6 if load_skills(directory) else .4}
    gate = SkillGate(ctx, {"id": "fixture-batch", "task_ids": ["fixture-val"]}, set(), scores)
    result = gate.consider(edit(), library, "fixture-event")
    assert result["decision"]["accepted"] and len(calls) == 2
    assert gate.consider(edit(), library, "fixture-event") == result
    assert len(calls) == 2
    assert result["skills_sha"] == library_sha(library)
    assert gate.scores(library, result["skills_sha"]) == {"fixture-val": .6}
    assert len(calls) == 2
    assert load_skills(library)[0].gate.delta == pytest.approx(.2)


def test_gate_rejection_archived_before_validation(ctx, library):
    def no_scores(*args):
        raise AssertionError("Leakage must be rejected before validation")
    gate = SkillGate(ctx, {"id": "fixture-batch", "task_ids": ["fixture-val"]}, {"fixture secret"}, no_scores)
    result = gate.consider(edit(body="Find fixture secret in the source."), library, "reject")
    assert not result["decision"]["accepted"]
    assert (ctx.path / "skills_rejected.jsonl").exists()


@pytest.mark.parametrize("operation,ident", [("update", "sk_9999"), ("retire", "sk_9999"),
                                             ("add", "sk_0001")])
def test_gate_invalid_target_is_rejected_once_before_validation(ctx, library, operation, ident):
    from loop_research.archive import read_jsonl
    from loop_research.skills import commit_library
    apply_op(library, edit())
    commit_library(library, "Initial fixture skill")
    before = library_sha(library)
    def no_scores(*args):
        raise AssertionError("Invalid skill targets must not trigger validation")
    gate = SkillGate(ctx, {"id": "batch", "task_ids": ["val"]}, set(), no_scores)
    op = edit(op=operation, id=ident)
    result = gate.consider(op, library, "invalid-target")
    assert result["done"] and not result["decision"]["accepted"]
    assert ident in result["reason"]
    assert gate.consider(op, library, "invalid-target") == result
    assert read_jsonl(ctx.path / "skills_rejected.jsonl") == [result]
    assert library_sha(library) == before


def test_gate_does_not_turn_validation_failure_into_rejected_edit(ctx, library):
    def failed_scores(*args):
        raise RuntimeError("fixture evaluator failure")
    gate = SkillGate(ctx, {"id": "batch", "task_ids": ["val"]}, set(), failed_scores)
    with pytest.raises(RuntimeError, match="fixture evaluator failure"):
        gate.consider(edit(), library, "failed-validation")
    assert not (ctx.path / "gate_events/failed-validation.json").exists()
    assert not (ctx.path / "skills_rejected.jsonl").exists()


@pytest.mark.parametrize("crash_after_commit", [False, True])
def test_gate_resumes_interrupted_accept_with_frozen_date(ctx, library, monkeypatch, crash_after_commit):
    from datetime import date
    from loop_research import gate as module
    from loop_research.archive import read_json, read_jsonl
    from loop_research.skills import git

    gate = SkillGate(ctx, {"id": "batch", "task_ids": ["val"]}, set(),
                     lambda directory, key: {"val": .6 if load_skills(directory) else .4})
    commit = module.commit_library
    def interrupted(directory, message):
        if crash_after_commit:
            commit(directory, message)
        raise RuntimeError("simulated interruption")
    class FirstDay:
        @staticmethod
        def today():
            return date(2025, 1, 1)
    monkeypatch.setattr(module, "date", FirstDay)
    monkeypatch.setattr(module, "commit_library", interrupted)
    with pytest.raises(RuntimeError, match="interruption"):
        gate.consider(edit(), library, "resume")
    assert not read_json(ctx.path / "gate_events/resume.json")["done"]
    monkeypatch.setattr(module, "commit_library", commit)
    monkeypatch.setattr(module, "date", date)
    result = gate.consider(edit(), library, "resume")
    assert result["done"] and library_sha(library) == result["skills_sha"]
    assert load_skills(library)[0].gate.date == date(2025, 1, 1)
    assert git(library, "rev-list", "--count", "HEAD") == "2"
    assert len(read_jsonl(ctx.path / "skills_accepted.jsonl")) == 1
    assert gate.consider(edit(), library, "resume") == result


def test_gate_resumes_update_and_recovers_missing_event_log(ctx, library, monkeypatch):
    from loop_research import gate as module
    from loop_research.archive import read_jsonl
    from loop_research.skills import commit_library
    apply_op(library, edit())
    commit_library(library, "Initial fixture skill")
    candidate = edit(op="update", id="sk_0001", body="Check original sources before accepting any claim.")
    gate = SkillGate(ctx, {"id": "batch", "task_ids": ["val"]}, set(),
                     lambda directory, key: {"val": .6 if load_skills(directory)[0].body == candidate.body else .4})
    commit = module.commit_library
    def interrupt(*args):
        raise RuntimeError("interruption")
    monkeypatch.setattr(module, "commit_library", interrupt)
    with pytest.raises(RuntimeError, match="interruption"):
        gate.consider(candidate, library, "update")
    monkeypatch.setattr(module, "commit_library", commit)
    result = gate.consider(candidate, library, "update")
    (ctx.path / "skills_accepted.jsonl").unlink()
    assert gate.consider(candidate, library, "update") == result
    assert len(read_jsonl(ctx.path / "skills_accepted.jsonl")) == 1


def test_skill_round_trip_preserves_dashes_inside_yaml_values(library):
    skill = Skill(id='sk_0001', title='Check --- separators', body='Keep source-specific formatting.',
                  applies_to=['format'], source_tasks=['fixture'])
    write_skill(library, skill)
    assert parse_skill(library / 'sk_0001.md') == skill
