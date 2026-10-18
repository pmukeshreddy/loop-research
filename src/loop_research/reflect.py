"""Reflect only on explicitly authorized training trajectories; no grader imports."""
import json
from pathlib import Path
import re
from typing import Literal
from .config import Strict
from .skills import EditOp
from .archive import read_jsonl
from .codex_backend import CodexBackend

class Reflection(Strict):
    ops: list[EditOp]
    skill_feedback: dict[str, Literal["helped", "hurt", "unused"]]


def condensed_trajectory(path, max_chars):
    parts = []
    for item in read_jsonl(Path(path)):
        if item.get("type") != "iteration":
            continue
        parts.append({"iteration": item.get("iteration"), "response": item.get("response"),
                      "code_blocks": [{"code": block["code"],
                          "stdout": block["result"].get("stdout"), "stderr": block["result"].get("stderr"),
                          "rlm_calls": block["result"].get("rlm_calls", [])}
                          for block in item.get("code_blocks", [])], "final_answer": item.get("final_answer")})
    return json.dumps(parts, ensure_ascii=False)[:max_chars]


def reflect(tasks, contexts, run_ctx, train_ids, backend=None):
    if not tasks or any(t.benchmark != "widesearch" or t.task_id not in train_ids for t in tasks):
        raise ValueError("Reflection accepts WideSearch train tasks only")
    examples = []
    used = set()
    for task, ctx in zip(tasks, contexts, strict=True):
        playbook = (ctx.path / "playbook.txt").read_text()
        used.update(re.findall(r"\[(sk_\d{4})\]", playbook))
        examples.append({"task_id": task.task_id, "question": task.question, "spec": task.spec,
            "output": ctx.load("output.json"), "errors": ctx.load("grade.json")["errors"],
            "trajectory": condensed_trajectory(ctx.path / "trajectory.jsonl", run_ctx.config.reflect.max_chars),
            "playbook": playbook})
    prompt = ("Reflect on these TRAIN research runs. Propose reusable imperative methods, never facts. "
        "Do not include entity names, numbers, dates, URLs, or task answers in skill titles/bodies. "
        "Each body must be at most 80 words. Prefer updating an existing skill over a near-duplicate add. "
        "Return rationale and evidence_task_ids for every op, drawn only from these tasks. "
        f"Return at most {run_ctx.config.reflect.max_ops} ops. Give helped/hurt/unused feedback for "
        "every skill actually present in the playbooks.\n" + json.dumps(examples, ensure_ascii=False))
    schema = Reflection.model_json_schema()
    schema["properties"]["ops"]["maxItems"] = run_ctx.config.reflect.max_ops
    edit = schema["$defs"]["EditOp"]
    edit["required"] = list(edit["properties"])
    for field in edit["properties"].values():
        field.pop("default", None)
    schema["properties"]["skill_feedback"] = {"type": "object", "additionalProperties": False,
        "properties": {ident: {"type": "string", "enum": ["helped", "hurt", "unused"]} for ident in sorted(used)},
        "required": sorted(used)}
    text = (backend or CodexBackend(run_ctx)).complete(prompt, purpose="reflect", schema=schema,
                                                      model=run_ctx.config.models.reflect)
    result = Reflection.model_validate_json(text)
    if len(result.ops) > run_ctx.config.reflect.max_ops:
        raise ValueError("Reflection exceeded max_ops")
    if set(result.skill_feedback) != used:
        raise ValueError("Reflection must cover exactly the rendered skills")
    task_ids = {t.task_id for t in tasks}
    if any(not set(op.evidence_task_ids) <= task_ids for op in result.ops):
        raise ValueError("Reflection cited evidence outside this train batch")
    run_ctx.save("reflection.json", result.model_dump(mode="json"))
    return result
