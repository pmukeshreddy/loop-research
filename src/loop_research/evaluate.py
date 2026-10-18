"""Evaluation boundary: the only pipeline module allowed to load WANDR."""
from datetime import date
from pathlib import Path

from .archive import RunContext, digest, read_json, write_json
from .benchmarks import Task
from .config import Config
from .loop import execute_run, library_identity, open_run, task_manifest


def _benchmark(name, root, config):
    if name == "widesearch":
        from .loop import _widesearch
        return _widesearch(root, config)
    if name == "wandr":
        from .benchmarks.wandr.grader import WandrBenchmark
        return WandrBenchmark(root, config)
    raise ValueError("Unknown benchmark: " + name)


def prepare_wandr(root, config):
    return _benchmark("wandr", root, config).prepare()


def verify_wandr(root, config):
    return _benchmark("wandr", root, config).verify()


def _check_scope(benchmark, split, final):
    if benchmark not in ("widesearch", "wandr"):
        raise ValueError("Unknown benchmark: " + benchmark)
    if (benchmark == "wandr" or split == "test") and not final:
        raise ValueError("WideSearch test and all WANDR require --final")
    if benchmark == "widesearch" and split not in ("val", "test"):
        raise ValueError("Evaluation split must be val or test")
    if benchmark == "widesearch" and final and split != "test":
        raise ValueError("Final WideSearch evaluation uses the test split")
    if benchmark == "wandr" and split != "final":
        raise ValueError("WANDR uses its fixed final subset")


def aggregate(grades_by_task):
    groups = list(grades_by_task.values())
    if not groups or not groups[0] or len({len(g) for g in groups}) != 1:
        raise ValueError("Aggregation requires equal nonempty repeats for every task")
    names = set(groups[0][0].metrics)
    if any(set(grade.metrics) != names for group in groups for grade in group):
        raise ValueError("Grade metrics changed across paired evaluation")
    metrics = {}
    for name in sorted(names):
        values = [[grade.metrics[name] for grade in group] for group in groups]
        metrics[name] = {"avg_n": sum(sum(v) / len(v) for v in values) / len(values),
                         "max_n": sum(max(v) for v in values) / len(values),
                         "min_n": sum(min(v) for v in values) / len(values)}
    if "score" in names:
        metrics["pass_at_n"] = metrics["score"]["max_n"]
    return metrics


def evaluate(root, config, benchmark, split=None, final=False):
    root = Path(root).resolve()
    split = split or ("final" if benchmark == "wandr" else "test" if final else "val")
    _check_scope(benchmark, split, final)
    adapter = _benchmark(benchmark, root, config)
    if benchmark == "wandr":
        adapter.verify_sources()
    tasks = adapter.final_tasks() if benchmark == "wandr" else adapter.split_tasks(split)
    manifest = task_manifest(tasks)
    sha = library_identity(root / "skills")
    selection_path = root / "data" / ("wandr_final.json" if benchmark == "wandr" else "splits.json")
    identity = {"benchmark": benchmark, "split": split, "final": final, "config": config.model_dump(),
                "tasks": manifest, "selection": read_json(selection_path), "skills_sha": sha}
    key = digest(identity)
    session_path = root / "runs/evaluations" / (key + ".json")
    session = read_json(session_path)
    if session is None:
        session = {"identity": identity, "fallback_as_of_date": date.today().isoformat()}
        write_json(session_path, session)
    if session["identity"] != identity:
        raise ValueError("Evaluation identity changed")
    fallback = session["fallback_as_of_date"]
    if date.fromisoformat(fallback).isoformat() != fallback:
        raise ValueError("Invalid archived evaluation fallback date")
    tasks = [task.model_copy(update={"raw": {**task.raw, "fallback_as_of_date": fallback}})
             if task.as_of_date is None else task for task in tasks]
    result = {"benchmark": benchmark, "split": split, "final": final, "evaluation_id": key,
              "task_count": len(tasks), "task_ids": [t.task_id for t in tasks], "library_sha": sha,
              "fallback_as_of_date": fallback, "repeats": config.final.repeats if final else 1,
              "judge": config.judge_label, "variants": {}}
    if benchmark == "wandr":
        result["fetch"] = "wandr-browser"
    for variant in (("library", "empty") if final else ("library",)):
        library = root / "skills" if variant == "library" else None
        groups = {t.task_id: [] for t in tasks}
        run_ids, grade_paths = [], []
        for repeat in range(result["repeats"]):
            if library_identity(root / "skills") != sha:
                raise ValueError("Skills changed during paired evaluation")
            run_id = f"eval-{benchmark}-{key}-{variant}-{repeat}"
            ctx, frozen = open_run(root, config, run_id, tasks, library, kind="evaluation", benchmark=benchmark,
                split=split, final=final, evaluation_id=key, variant=variant, repeat=repeat,
                fallback_as_of_date=fallback)
            grades = execute_run(ctx, tasks, adapter, frozen)
            run_ids.append(run_id)
            for ident, grade in grades.items():
                if grade.judge != result["judge"]:
                    raise ValueError("Evaluation judge label differs from run configuration")
                if benchmark == "wandr" and grade.provenance.get("fetch") != result["fetch"]:
                    raise ValueError("WANDR fetch provenance is missing or inconsistent")
                groups[ident].append(grade)
                grade_paths.append(str((ctx.task(ident).path / "grade.json").relative_to(root)))
        flat = [grade for group in groups.values() for grade in group]
        if len({g.primary_metric for g in flat}) != 1:
            raise ValueError("Primary metric changed across evaluation")
        provenance = {name: flat[0].provenance[name] for name in ("dataset_revision", "code_revision", "harness_primary_metric")
                      if name in flat[0].provenance}
        if any(any(grade.provenance.get(name) != value for name, value in provenance.items()) for grade in flat):
            raise ValueError("Grader provenance changed across evaluation")
        if "primary_metric" in result and (result["primary_metric"] != flat[0].primary_metric or result["provenance"] != provenance):
            raise ValueError("Grader identity changed between evaluation variants")
        result.update(primary_metric=flat[0].primary_metric, provenance=provenance)
        if benchmark == "wandr":
            result["harness_primary_metric"] = provenance["harness_primary_metric"]
        value = {"skills_sha": sha if variant == "library" else "empty", "run_ids": run_ids,
                 "primary_metric": flat[0].primary_metric, "metrics": aggregate(groups), "grade_paths": grade_paths}
        if benchmark == "wandr":
            failures = sum(g.errors["excerpt_failures"] for g in flat)
            judged = sum(g.errors["excerpt_judged"] for g in flat)
            value.update(excerpt_failures=failures, excerpt_judged=judged,
                         excerpt_failure_rate=failures / judged if judged else None,
                         unjudged_records=sum(g.errors["unjudged_records"] for g in flat))
        result["variants"][variant] = value
    if library_identity(root / "skills") != sha:
        raise ValueError("Skills changed during paired evaluation")
    directory = root / "reports"
    write_json(directory / "evaluations" / (key + ".json"), result)
    write_json(directory / (("final_" if final else "validation_") + benchmark + ".json"), result)
    return result


def grade_run(root, run_id):
    root = Path(root).resolve()
    probe = RunContext(root, run_id, Config())
    config_data, summary = probe.load("config.json"), probe.load("run_summary.json")
    if config_data is None or summary is None:
        raise ValueError("Unknown archived run")
    benchmark = summary.get("benchmark")
    if (benchmark == "wandr" or summary.get("split") == "test") and not summary.get("final"):
        raise ValueError("WideSearch test and all WANDR require a final evaluation archive")
    config = Config.model_validate(config_data)
    adapter = _benchmark(benchmark, root, config)
    if benchmark == "wandr":
        adapter.verify_sources()
    ctx = RunContext(root, run_id, config)
    tasks = [Task.model_validate(item) for item in ctx.load("tasks.json", [])]
    task_manifest(tasks)
    current = {t.task_id: t for t in adapter.load_tasks()}
    for task in tasks:
        original = task
        if summary.get("kind") == "evaluation" and task.as_of_date is None:
            if task.raw.get("fallback_as_of_date") != summary.get("fallback_as_of_date"):
                raise ValueError("Archived evaluation fallback date changed")
            original = task.model_copy(update={"raw": {k: v for k, v in task.raw.items() if k != "fallback_as_of_date"}})
        if current.get(task.task_id) != original:
            raise ValueError("Archived tasks differ from the pinned dataset")
    execute_run(ctx, tasks, adapter, None, research=False)
    return run_id
