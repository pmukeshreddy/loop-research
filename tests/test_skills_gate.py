
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
