import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

from loop_research.archive import append_json, read_jsonl
from loop_research.config import Config
from loop_research.reflect import condensed_trajectory, reflect


@pytest.mark.parametrize("data", [{"extra": True}, {"codex": {"max_concurrent": 0}},
                                  {"data": {"split": {"train": .7, "val": .2, "test": .2}}}])
def test_config_rejects_invalid_values(data):
    with pytest.raises(ValidationError):
        Config.model_validate(data)


def test_archive_resume_preserves_config_and_library(ctx):
    root = ctx.task("other")
    root.initialize("fixture-sha", benchmark="widesearch")
    root.initialize("fixture-sha", benchmark="widesearch")
    assert root.load("config.json") == ctx.config.model_dump()
    with pytest.raises(ValueError, match="library"):
        root.initialize("changed-sha")
    root.config.codex.timeout_s = 100
    with pytest.raises(ValueError, match="configuration"):
        root.initialize("fixture-sha")


def test_jsonl_and_real_trajectory_fields(ctx):
    path = ctx.path / "trajectory.jsonl"
    iteration = {"type": "iteration", "iteration": 1, "code_blocks": [{"code": "print('fixture')",
                 "result": {"stdout": "fixture", "stderr": "", "rlm_calls": [{"response": "subcall"}]}}]}
    append_json(path, {"type": "metadata"})
    append_json(path, iteration)
    assert read_jsonl(path)[1] == iteration
    condensed = condensed_trajectory(path, 10000)
    assert "subcall" in condensed and "print" in condensed and "metadata" not in condensed
    assert len(condensed_trajectory(path, 20)) == 20


def test_codex_call_count_includes_pending_attempts_without_double_counting(ctx):
    from loop_research.archive import count_codex_calls, write_json
    log = ctx.path / "codex_calls.jsonl"
    write_json(ctx.path / "codex_attempts/completed.json", {"call_id": "completed", "purpose": "root"})
    write_json(ctx.path / "codex_attempts/pending.json", {"call_id": "pending", "purpose": "sub"})
    write_json(ctx.path / "codex_attempts/judge.json", {"call_id": "judge", "purpose": "grade"})
    append_json(log, {"call_id": "completed", "purpose": "root", "duration_s": .1})
    append_json(log, {"call_id": "completed", "purpose": "root", "duration_s": .1})
    append_json(log, {"purpose": "search", "duration_s": .1})  # Legacy completed call.
    assert count_codex_calls(ctx.path) == 4
    assert count_codex_calls(ctx.path, exclude_purposes=("grade",)) == 3
    assert count_codex_calls(ctx.path / "empty") == 0


def test_reflection_rejects_non_train_before_reading_archives(ctx, task):
    with pytest.raises(ValueError, match="train"):
        reflect([task], [ctx], ctx, set())


def test_reflection_validates_task_evidence_and_feedback(ctx, task):
    ctx.path.mkdir(parents=True)
    (ctx.path / "playbook.txt").write_text("[sk_0001] Check sources")
    ctx.save("output.json", {"rows": []})
    ctx.save("grade.json", {"errors": {"missing_entities": []}})
    class Backend:
        def complete(self, prompt, **kwargs):
            assert kwargs["purpose"] == "reflect"
            assert "never facts" in prompt and "TRAIN" in prompt
            return json.dumps({"ops": [], "skill_feedback": {"sk_0001": "unused"}})
    result = reflect([task], [ctx], ctx, {task.task_id}, backend=Backend())
    assert result.skill_feedback == {"sk_0001": "unused"}
    assert ctx.load("reflection.json")["ops"] == []


@pytest.mark.parametrize("used", [[], ["sk_0001", "sk_0002"]])
def test_reflection_sends_closed_strict_schema_for_rendered_skills(ctx, task, used):
    ctx.path.mkdir(parents=True)
    (ctx.path / "playbook.txt").write_text("\n".join(f"[{ident}] Check sources" for ident in used))
    ctx.save("output.json", {"rows": []})
    ctx.save("grade.json", {"errors": {}})

    class Backend:
        def complete(self, prompt, **kwargs):
            schema = kwargs["schema"]
            feedback = schema["properties"]["skill_feedback"]
            assert feedback["additionalProperties"] is False
            assert set(feedback["properties"]) == set(feedback["required"]) == set(used)
            assert all(field == {"type": "string", "enum": ["helped", "hurt", "unused"]}
                       for field in feedback["properties"].values())
            edit = schema["$defs"]["EditOp"]
            assert edit["additionalProperties"] is False
            assert set(edit["required"]) == set(edit["properties"])
            for name in ("id", "title", "body", "applies_to"):
                assert {"type": "null"} in edit["properties"][name]["anyOf"]
                assert "default" not in edit["properties"][name]
            return json.dumps({"ops": [], "skill_feedback": {ident: "unused" for ident in used}})

    result = reflect([task], [ctx], ctx, {task.task_id}, backend=Backend())
    assert result.skill_feedback == {ident: "unused" for ident in used}


@pytest.mark.parametrize("module", ["agent", "reflect", "repl_tools", "gate"])
def test_import_boundaries(module):
    code = f'''
import sys
import loop_research.{module}
assert not any(name.startswith('loop_research.benchmarks.wandr') for name in sys.modules)
assert 'loop_research.benchmarks.widesearch.answers' not in sys.modules
'''
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    result = subprocess.run([sys.executable, "-c", code], text=True, capture_output=True, env=env)
    assert result.returncode == 0, result.stderr
