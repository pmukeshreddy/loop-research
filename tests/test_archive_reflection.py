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
