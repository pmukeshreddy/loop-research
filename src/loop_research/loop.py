"""Resumable WideSearch learning and benchmark-independent run execution."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import math
from pathlib import Path
import random
import shutil
import tempfile
from uuid import uuid4

from .agent import AgentResult, run_task
from .archive import RunContext, append_json, count_codex_calls, digest, read_json, read_jsonl, stamp, write_json
from .benchmarks import GradeResult
from .benchmarks.widesearch.grader import build_leakage_index
from .gate import SkillGate
from .reflect import Reflection, reflect
from .skills import (Skill, commit_library, git, library_sha, load_skills, write_skill)


def _widesearch(root, config):
    from .benchmarks.widesearch.grader import WideSearchBenchmark
    benchmark = WideSearchBenchmark(root, config)
    benchmark.verify_data()
    benchmark.verify_code()
    return benchmark


def new_run_id(prefix):
    return prefix + "-" + uuid4().hex


def task_manifest(tasks):
    if not tasks or len({t.task_id for t in tasks}) != len(tasks):
        raise ValueError("A run requires nonempty, distinct tasks")
    return [t.model_dump(mode="json") for t in tasks]


def library_identity(directory):
    if directory is None or (Path(directory) / ".git").exists():
        return library_sha(directory)
    return "candidate:" + digest({p.name: p.read_text() for p in sorted(Path(directory).glob("sk_*.md"))})


def open_run(root, config, run_id, tasks, directory, **metadata):
    ctx = RunContext(Path(root), run_id, config)
    manifest, sha = task_manifest(tasks), library_identity(directory)
    ctx.initialize(sha, task_ids=[t.task_id for t in tasks], **metadata)
    summary = ctx.load("run_summary.json")
    if any(summary.get(key) != value for key, value in metadata.items()):
        raise ValueError("Run metadata changed")
    saved = ctx.load("tasks.json")
    if saved is not None and saved != manifest:
        raise ValueError("Run task/dataset identity changed")
    ctx.save("tasks.json", manifest)
    frozen = None
    if directory is not None:
        frozen = ctx.path / "library"
        if not frozen.exists():
            with tempfile.TemporaryDirectory(dir=ctx.path, prefix="library-") as temporary:
                target = Path(temporary) / "snapshot"
                target.mkdir()
                for path in sorted(Path(directory).glob("sk_*.md")):
                    shutil.copy2(path, target / path.name)
                target.rename(frozen)
        content = digest({p.name: p.read_text() for p in sorted(frozen.glob("sk_*.md"))})
        saved_hash = ctx.load("library_manifest.json")
        if saved_hash is not None and saved_hash != {"sha": sha, "content": content}:
            raise ValueError("Archived library was modified")
        ctx.save("library_manifest.json", {"sha": sha, "content": content})
    return ctx, frozen


def _research_ready(task, benchmark, ctx):
    required = ("task.json", "prompt.txt", "playbook.txt", "trajectory.jsonl", "output.json",
                "submission.json", "agent_result.json", "tool_cache.json", "url_ledger.json")
    if not all((ctx.path / name).is_file() for name in required):
        return False
    if ctx.load("task.json") != task.model_dump(mode="json"):
        raise ValueError("Archived task identity changed")
    output = ctx.load("output.json")
    benchmark.output_contract(task).model.model_validate(output)
    result = AgentResult.model_validate(ctx.load("agent_result.json"))
    if result.output != output or ctx.load("submission.json") != benchmark.to_submission(task, output):
        raise ValueError("Archived output and submission disagree")
    return True


def execute_task(task, benchmark, library, ctx, *, grade=True, research=True):
    """Reuse only validated complete research artifacts; journal the grader input."""
    ctx.path.mkdir(parents=True, exist_ok=True)
    if not _research_ready(task, benchmark, ctx):
        if not research:
            raise ValueError(f"Incomplete research archive for {task.task_id}")
        for name in ("grade.json", "grade_input.json", "completed.json"):
            (ctx.path / name).unlink(missing_ok=True)
        run_task(task, benchmark, library, ctx)
        if not _research_ready(task, benchmark, ctx):
            raise ValueError("Agent returned without complete research artifacts")
    (ctx.path / "codex_calls.jsonl").touch(exist_ok=True)
    identity = digest({"task": task.model_dump(mode="json"), "output": ctx.load("output.json"),
                       "submission": ctx.load("submission.json"), "config": read_json(ctx.run_dir / "config.json"),
                       "library": (ctx.run_dir / "skills_sha.txt").read_text().strip()})
    if not grade:
        return None
    if ctx.load("grade_input.json") != {"identity": identity}:
        (ctx.path / "grade.json").unlink(missing_ok=True)
        (ctx.path / "completed.json").unlink(missing_ok=True)
        ctx.save("grade_input.json", {"identity": identity})
    saved = ctx.load("grade.json")
    result = GradeResult.model_validate(saved) if saved is not None else benchmark.grade(task, ctx.load("submission.json"), ctx)
    if not result.metrics or result.primary_metric not in result.metrics or any(not math.isfinite(v) for v in result.metrics.values()):
        raise ValueError("Grader returned missing or nonfinite metrics")
    if saved is None:
        ctx.save("grade.json", result.model_dump(mode="json"))
    completed = {"identity": identity, "grade": digest(result.model_dump(mode="json"))}
    if ctx.load("completed.json") != completed:
        ctx.save("completed.json", completed)
    return result


def execute_run(ctx, tasks, benchmark, library, *, grade=True, research=True):
    with ThreadPoolExecutor(max_workers=ctx.config.loop.parallel_tasks) as pool:
        futures = [pool.submit(execute_task, task, benchmark, library, ctx.task(task.task_id),
                               grade=grade, research=research) for task in tasks]
        grades = {task.task_id: future.result() for task, future in zip(tasks, futures)}
    summary = ctx.load("run_summary.json")
    summary.update(status="complete" if grade else "researched", task_count=len(tasks))
    ctx.save("run_summary.json", summary)
    return grades


def run_train(root, config, n):
    benchmark = _widesearch(root, config)
    tasks = sorted(benchmark.split_tasks("train"), key=lambda t: t.task_id)
    if not 1 <= n <= len(tasks):
        raise ValueError("n must fit the nonempty training split")
    random.Random(config.data.seed).shuffle(tasks)
    tasks = tasks[:n]
    ctx, frozen = open_run(root, config, new_run_id("train"), tasks, Path(root) / "skills",
                           kind="train", benchmark="widesearch", split="train", final=False)
    execute_run(ctx, tasks, benchmark, frozen, grade=False)
    return ctx.run_id


def train_batch(tasks, seed, number, size):
    """Finish each seeded epoch before recycling tasks; its last batch can be shorter."""
    if not tasks:
        raise ValueError("Training split is empty")
    cycle, batch = divmod(number, math.ceil(len(tasks) / size))
    ordered = sorted(tasks, key=lambda t: t.task_id)
    random.Random(seed + cycle).shuffle(ordered)
    return ordered[batch * size:(batch + 1) * size]


def apply_feedback(ctx, library, feedback, event_id, expected_sha):
    if not feedback:
        return expected_sha
    path = ctx.path / "counter_events" / (event_id + ".json")
    event = read_json(path)
    if event is None:
        if library_sha(library) != expected_sha:
            raise ValueError("Skills changed outside the improvement session")
        skills = {s.id: s for s in load_skills(library)}
        snapshots = []
        for ident, judgment in feedback.items():
            skill = skills[ident]
            field = {"helped": "helpful", "hurt": "harmful", "unused": "unused"}[judgment]
            setattr(skill.counters, field, getattr(skill.counters, field) + 1)
            snapshots.append(skill.model_dump(mode="json"))
        event = {"before": expected_sha, "skills": snapshots, "done": False}
        write_json(path, event)
    if event["done"]:
        return event["after"]
    message = "reflect counters " + event_id
    head = git(library, "rev-parse", "HEAD")
    if head == event["before"]:
        allowed = {s["id"] + ".md" for s in event["skills"]}
        changed = set(git(library, "diff", "--name-only", "HEAD").splitlines())
        changed.update(git(library, "ls-files", "--others", "--exclude-standard").splitlines())
        if changed - allowed:
            raise ValueError("Unrelated edits conflict with pending skill counters")
        for snapshot in event["skills"]:
            write_skill(library, Skill.model_validate(snapshot))
        commit_library(library, message)
    elif git(library, "log", "-1", "--format=%s") != message or git(library, "rev-parse", "HEAD^") != event["before"]:
        raise ValueError("Skills changed outside the pending counter transaction")
    actual = {s.id: s.model_dump(mode="json") for s in load_skills(library)}
    for snapshot in event["skills"]:
        if actual[snapshot["id"]] != snapshot:
            raise ValueError("Committed skill counters differ from journal")
    event.update(done=True, after=library_sha(library))
    write_json(path, event)
    return event["after"]


def _gate_batch(root, benchmark, config):
    batch = read_json(Path(root) / "data/gate_batch.json")
    splits = read_json(Path(root) / "data/splits.json")
    val = {t.task_id: t for t in benchmark.split_tasks("val")}
    if not batch or batch["split_hash"] != digest(splits) or batch["seed"] != config.data.seed:
        raise ValueError("Prepare the matching fixed validation gate batch first")
    ids = batch["task_ids"]
    if len(ids) != config.gate.val_batch_size or len(set(ids)) != len(ids) or not set(ids) <= set(val):
        raise ValueError("Gate batch must contain distinct validation tasks of configured size")
    return batch, [val[ident] for ident in ids]


def _sync_decisions(ctx):
    for accepted, name in ((True, "skills_accepted.jsonl"), (False, "skills_rejected.jsonl")):
        path = ctx.path / name
        recorded = {event["event_id"] for event in read_jsonl(path)}
        for source in sorted(ctx.path.glob("round-*/gate_events/*.json")):
            event = read_json(source)
            if event.get("done") and event["decision"]["accepted"] == accepted and event["event_id"] not in recorded:
                append_json(path, event)
                recorded.add(event["event_id"])


def improve(root, config, rounds, resume=False):
    if rounds < 1:
        raise ValueError("rounds must be positive")
    root = Path(root).resolve()
    benchmark, library = _widesearch(root, config), root / "skills"
    train = benchmark.split_tasks("train")
    batch, validation = _gate_batch(root, benchmark, config)
    identity = digest({"train": task_manifest(train), "val": task_manifest(validation), "batch": batch,
                       "splits": read_json(root / "data/splits.json")})
    pointer = root / "runs/latest_improve.json"
    previous = read_json(pointer) if resume else None
    if resume and previous is None:
        raise ValueError("No improvement session to resume")
    run_id = previous["run_id"] if previous else new_run_id("improve")
    ctx = RunContext(root, run_id, config)
    state = ctx.load("state.json")
    initial_sha = ctx.load("run_summary.json", {}).get("skills_sha") if state else library_sha(library)
    ctx.initialize(initial_sha, kind="improve", benchmark="widesearch", split="train", final=False)
    if state and state["data_identity"] != identity:
        raise ValueError("Cannot resume with changed dataset/split identity")
    if state is None:
        state = {"data_identity": identity, "completed_rounds": 0, "expected_sha": initial_sha, "target_rounds": rounds}
        ctx.save("state.json", state)
    if rounds < state["completed_rounds"]:
        raise ValueError("rounds cannot precede completed rounds")
    state["target_rounds"] = rounds
    ctx.save("state.json", state)
    write_json(pointer, {"run_id": run_id})
    leakage = None
    for number in range(state["completed_rounds"], rounds):
        round_ctx = ctx.task(f"round-{number + 1:04d}")
        progress = round_ctx.load("state.json")
        selected = train_batch(train, config.data.seed, number, config.loop.train_batch_size)
        if progress is None:
            if library_sha(library) != state["expected_sha"]:
                raise ValueError("Skills changed outside the improvement session")
            progress = {"stage": "train", "started": stamp(), "expected_sha": state["expected_sha"],
                        "task_ids": [t.task_id for t in selected], "batch_index": 0, "op_index": 0,
                        "counters_done": False, "train_run": f"{run_id}-r{number + 1:04d}-train"}
            round_ctx.save("state.json", progress)
        if progress["task_ids"] != [t.task_id for t in selected]:
            raise ValueError("Training schedule changed")
        if progress["stage"] == "train":
            if library_sha(library) != progress["expected_sha"]:
                raise ValueError("Skills changed during training")
            training, frozen = open_run(root, config, progress["train_run"], selected, library,
                kind="train", benchmark="widesearch", split="train", final=False, parent_run=run_id, round=number + 1)
            execute_run(training, selected, benchmark, frozen)
            progress["stage"] = "reflect"
            round_ctx.save("state.json", progress)
        training = RunContext(root, progress["train_run"], config)
        chunks = [selected[i:i + config.reflect.batch_size] for i in range(0, len(selected), config.reflect.batch_size)]
        if progress["stage"] == "reflect":
            for i, chunk in enumerate(chunks):
                reflection_ctx = ctx.task(f"reflect-r{number + 1:04d}-b{i:04d}")
                saved = reflection_ctx.load("reflection.json")
                if saved is None:
                    reflect(chunk, [training.task(t.task_id) for t in chunk], reflection_ctx,
                            {t.task_id for t in train})
                else:
                    Reflection.model_validate(saved)
            progress["stage"] = "edits"
            round_ctx.save("state.json", progress)

        def score_library(directory, key):
            per_task = {t.task_id: [] for t in validation}
            for repeat in range(config.gate.repeats):
                gate_ctx, frozen = open_run(root, config, f"gate-{key}-{repeat}", validation, directory,
                    kind="gate", benchmark="widesearch", split="val", final=False, cache_key=key, repeat=repeat)
                if gate_ctx.load("owner.json") is None:
                    gate_ctx.save("owner.json", {"parent_run": run_id, "round": number + 1})
                scores = execute_run(gate_ctx, validation, benchmark, frozen)
                for ident, result in scores.items():
                    per_task[ident].append(result.metrics[result.primary_metric])
            return {ident: sum(values) / len(values) for ident, values in per_task.items()}

        if leakage is None:
            leakage = build_leakage_index(benchmark, config.gate.leakage_min_len)
        gate = SkillGate(round_ctx, batch, leakage, score_library)
        if progress["stage"] == "edits":
            while progress["batch_index"] < len(chunks):
                i = progress["batch_index"]
                event_prefix = f"r{number + 1:04d}-b{i:04d}"
                result = Reflection.model_validate(ctx.task("reflect-" + event_prefix).load("reflection.json"))
                if not progress["counters_done"]:
                    progress["expected_sha"] = apply_feedback(round_ctx, library, result.skill_feedback,
                                                              event_prefix, progress["expected_sha"])
                    progress["counters_done"] = True
                    round_ctx.save("state.json", progress)
                while progress["op_index"] < len(result.ops):
                    index = progress["op_index"]
                    event_id = event_prefix + f"-op{index:04d}"
                    if not (round_ctx.path / "gate_events" / (event_id + ".json")).exists() and library_sha(library) != progress["expected_sha"]:
                        raise ValueError("Skills changed before validation")
                    event = gate.consider(result.ops[index], library, event_id)
                    _sync_decisions(ctx)
                    progress["expected_sha"] = event.get("skills_sha", progress["expected_sha"])
                    progress["op_index"] += 1
                    round_ctx.save("state.json", progress)
                progress.update(batch_index=i + 1, op_index=0, counters_done=False)
                round_ctx.save("state.json", progress)
            progress["stage"] = "metrics"
            round_ctx.save("state.json", progress)
        if progress["stage"] == "metrics":
            sha = library_sha(library)
            if sha != progress["expected_sha"]:
                raise ValueError("Skills changed before round completion")
            scores = gate.scores(library, sha)
            grades = [GradeResult.model_validate(training.task(t.task_id).load("grade.json")) for t in selected]
            events = [read_json(p) for p in sorted((round_ctx.path / "gate_events").glob("*.json"))]
            logs = list(training.path.glob("*/codex_calls.jsonl"))
            logs += list(ctx.path.glob(f"reflect-r{number + 1:04d}-*/codex_calls.jsonl"))
            for owner in (root / "runs").glob("gate-*/owner.json"):
                if read_json(owner) == {"parent_run": run_id, "round": number + 1}:
                    logs += list(owner.parent.glob("*/codex_calls.jsonl"))
            accepted = sum(e["decision"]["accepted"] for e in events)
            metrics = {"run_id": run_id, "round": number + 1, "library_sha": sha,
                "active_skills": sum(s.status == "active" for s in load_skills(library)),
                "train_metrics": {name: sum(g.metrics[name] for g in grades) / len(grades) for name in grades[0].metrics},
                "gate_score": sum(scores.values()) / len(scores), "ops_proposed": len(events),
                "ops_accepted": accepted, "ops_rejected": len(events) - accepted,
                "codex_calls": sum(count_codex_calls(p.parent) for p in logs),
                "wall_time_s": (datetime.fromisoformat(stamp()) - datetime.fromisoformat(progress["started"])).total_seconds(),
                "judge": config.judge_label, "train_run": training.run_id,
                "grade_paths": [str((training.task(t.task_id).path / "grade.json").relative_to(root.resolve())) for t in selected],
                "gate_cache": str((root / "runs/gate_cache" / (gate.cache_key(sha) + ".json")).relative_to(root)),
                "call_logs": [str(p.relative_to(root.resolve())) for p in logs]}
            round_ctx.save("round_metrics.json", metrics)
            progress["stage"] = "complete"
            round_ctx.save("state.json", progress)
        state.update(completed_rounds=number + 1, expected_sha=progress["expected_sha"])
        ctx.save("state.json", state)
        from .report import write_rounds
        write_rounds(root)
    if library_sha(library) != state["expected_sha"]:
        raise ValueError("Skills changed outside the improvement session")
    summary = ctx.load("run_summary.json")
    summary.update(status="complete", completed_rounds=state["completed_rounds"], final_skills_sha=state["expected_sha"])
    ctx.save("run_summary.json", summary)
    _sync_decisions(ctx)
    from .report import write_rounds
    write_rounds(root)
    return run_id
