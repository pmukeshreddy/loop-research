"""Offline orchestration tests; all task data and model results here are fixtures."""
from datetime import date
import threading

import pytest

from loop_research.archive import append_json, digest, read_json, write_json
from loop_research.benchmarks import GradeResult, Task
from loop_research.config import Config
from loop_research.skills import Skill, commit_library, init_library, load_skills, write_skill


@pytest.fixture
def orchestration(tmp_path, monkeypatch):
    from loop_research import loop, evaluate
    from loop_research.agent import AgentResult
    from loop_research.benchmarks.widesearch.data import WideSearchData
    from loop_research.reflect import Reflection

    config = Config()
    config.loop.train_batch_size = 2
    config.reflect.batch_size = 2
    config.gate.val_batch_size = 1
    init_library(tmp_path / "skills")
    tasks = [Task(task_id=f"fixture-{i}", benchmark="widesearch", question="Fixture question",
                  spec={"columns": ["entity"], "keys": ["entity"]}, language="en") for i in range(6)]
    splits = {"splits": {"train": [t.task_id for t in tasks[:3]], "val": [tasks[3].task_id],
                         "test": [t.task_id for t in tasks[4:]]}}
    write_json(tmp_path / "data/splits.json", splits)
    batch = {"task_ids": splits["splits"]["val"], "split_hash": digest(splits), "seed": config.data.seed}
    batch["id"] = digest(batch)
    write_json(tmp_path / "data/gate_batch.json", batch)
    history = {"agent": [], "grade": [], "reflect": []}

    class FixtureBenchmark(WideSearchData):
        def load_tasks(self):
            return tasks

        def split_tasks(self, name):
            return [t for t in tasks if t.task_id in splits["splits"][name]]

        def grade(self, task, submission, ctx):
            history["grade"].append((ctx.run_id, task.task_id))
            return GradeResult(metrics={"score": 0.0, "f1_by_row": .2, "f1_by_item": .3},
                               primary_metric="f1_by_row", judge=ctx.config.judge_label)

    benchmark = FixtureBenchmark(tmp_path, config)

    def research(task, benchmark, library, ctx):
        history["agent"].append((ctx.run_id, task.task_id, library is None))
        ctx.path.mkdir(parents=True, exist_ok=True)
        output = {"rows": []}
        for filename, value in {"task.json": task.model_dump(mode="json"), "output.json": output,
                                "submission.json": None, "tool_cache.json": {}, "url_ledger.json": []}.items():
            ctx.save(filename, value)
        for filename in ("prompt.txt", "playbook.txt", "trajectory.jsonl"):
            (ctx.path / filename).write_text("")
        result = AgentResult(output=output, errors=[], uncited=[], as_of_date="2026-01-01", date_source="task")
        ctx.save("agent_result.json", result.model_dump())
        append_json(ctx.path / "codex_calls.jsonl", {"purpose": "root", "duration_s": .1})
        return result

    def reflection(selected, contexts, ctx, train_ids):
        assert {t.task_id for t in selected} <= set(splits["splits"]["train"])
        assert all(c.load("grade.json") for c in contexts)
        history["reflect"].append([t.task_id for t in selected])
        result = Reflection(ops=[], skill_feedback={})
        ctx.save("reflection.json", result.model_dump())
        return result

    monkeypatch.setattr(loop, "_widesearch", lambda root, cfg: benchmark)
    monkeypatch.setattr(loop, "build_leakage_index", lambda *a, **kw: set())
    monkeypatch.setattr(loop, "run_task", research)
    monkeypatch.setattr(loop, "reflect", reflection)
    monkeypatch.setattr(evaluate, "_benchmark", lambda name, root, cfg: benchmark)
    return tmp_path, config, benchmark, history


def test_parallel_tasks_config():
    from pydantic import ValidationError
    assert Config().loop.parallel_tasks == 4
    with pytest.raises(ValidationError):
        Config.model_validate({"loop": {"parallel_tasks": 0}})


@pytest.mark.parametrize("grade", [True, False])
@pytest.mark.parametrize("parallel_tasks", [1, 2, 3])
def test_parallel_run_matches_sequential_archives_and_resume(orchestration, monkeypatch, grade, parallel_tasks):
    from loop_research import archive, loop
    root, config, benchmark, history = orchestration
    config.loop.parallel_tasks = parallel_tasks
    tasks = benchmark.load_tasks()
    monkeypatch.setattr(archive, "stamp", lambda: "2026-01-01T00:00:00+00:00")
    sequential, frozen = loop.open_run(root / "sequential", config, "fixture", tasks, root / "skills")
    expected = {task.task_id: loop.execute_task(task, benchmark, frozen, sequential.task(task.task_id), grade=grade)
                for task in tasks}
    summary = sequential.load("run_summary.json")
    summary.update(status="complete" if grade else "researched", task_count=len(tasks))
    sequential.save("run_summary.json", summary)

    research = loop.run_task
    barrier, lock = threading.Barrier(parallel_tasks, timeout=5), threading.Lock()
    second_done = threading.Event()
    active = peak = 0

    def overlapping(*args):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            barrier.wait()
            if parallel_tasks > 1 and args[0] == tasks[0]:
                assert second_done.wait(5)
            result = research(*args)
            if args[0] == tasks[1]:
                second_done.set()
            return result
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(loop, "run_task", overlapping)
    parallel, frozen = loop.open_run(root / "parallel", config, "fixture", tasks, root / "skills")
    result = loop.execute_run(parallel, tasks, benchmark, frozen, grade=grade)
    assert peak == config.loop.parallel_tasks
    assert list(result) == list(expected) and result == expected
    if parallel_tasks > 1:
        order = [task_id for _, task_id, _ in history["agent"][len(tasks):]]
        assert order.index(tasks[1].task_id) < order.index(tasks[0].task_id)

    def files(ctx):
        return {str(p.relative_to(ctx.path)): p.read_bytes() for p in ctx.path.rglob("*") if p.is_file()}

    assert files(parallel) == files(sequential)
    before, calls = files(parallel), {key: list(value) for key, value in history.items()}
    parallel, frozen = loop.open_run(root / "parallel", config, "fixture", tasks, root / "skills")
    assert loop.execute_run(parallel, tasks, benchmark, frozen, grade=grade) == expected
    assert files(parallel) == before and history == calls


def test_parallel_failure_resumes_only_unfinished_grades(orchestration, monkeypatch):
    from loop_research import loop
    root, config, benchmark, history = orchestration
    config.loop.parallel_tasks = 2
    tasks = benchmark.load_tasks()[:2]
    ctx, frozen = loop.open_run(root, config, "fixture-failure", tasks, root / "skills")
    grade = benchmark.grade
    barrier = threading.Barrier(2, timeout=5)

    def interrupted(task, submission, ctx):
        barrier.wait()
        if task == tasks[0]:
            raise RuntimeError("Fixture interrupted grade")
        return grade(task, submission, ctx)

    monkeypatch.setattr(benchmark, "grade", interrupted)
    with pytest.raises(RuntimeError, match="interrupted grade"):
        loop.execute_run(ctx, tasks, benchmark, frozen)
    assert ctx.load("run_summary.json").get("status") != "complete"
    completed = ctx.task(tasks[1].task_id).load("completed.json")
    assert completed and ctx.task(tasks[0].task_id).load("completed.json") is None
    monkeypatch.setattr(benchmark, "grade", grade)
    results = loop.execute_run(ctx, tasks, benchmark, frozen)
    assert list(results) == [task.task_id for task in tasks]
    assert len(history["agent"]) == len(history["grade"]) == 2
    assert ctx.task(tasks[1].task_id).load("completed.json") == completed


def test_failed_run_does_not_start_remaining_tasks(orchestration, monkeypatch):
    from loop_research import loop
    root, config, benchmark, history = orchestration
    config.loop.parallel_tasks = 1
    tasks = benchmark.load_tasks()
    ctx, frozen = loop.open_run(root, config, "fixture-stop", tasks, root / "skills")

    def fail(*args):
        raise RuntimeError("Fixture first grade failed")

    monkeypatch.setattr(benchmark, "grade", fail)
    with pytest.raises(RuntimeError, match="first grade failed"):
        loop.execute_run(ctx, tasks, benchmark, frozen)
    assert [task_id for _, task_id, _ in history["agent"]] == [tasks[0].task_id]


def test_sigint_stops_research_process_and_pending_tasks(tmp_path):
    import os
    from pathlib import Path
    import signal
    import subprocess
    import sys

    code = '''
import os, signal, subprocess, sys
from pathlib import Path
from loop_research import agent, loop
from loop_research.benchmarks import Task
from loop_research.benchmarks.widesearch.data import WideSearchData
from loop_research.config import Config
root = Path(sys.argv[1])
config = Config()
config.loop.parallel_tasks = 1
tasks = [Task(task_id=f"fixture-{i}", benchmark="widesearch", question="Fixture",
              spec={"columns": ["entity"], "keys": ["entity"]}, language="en") for i in range(4)]
ctx, _ = loop.open_run(root, config, "fixture-interrupt", tasks, None)
popen = subprocess.Popen
def sleeper(command, **kwargs):
    process = popen([sys.executable, "-c", "import time; time.sleep(30)"], **kwargs)
    with (root / "pids").open("a") as handle:
        handle.write(str(process.pid) + "\\n")
    os.kill(os.getpid(), signal.SIGINT)
    return process
agent.subprocess.Popen = sleeper
try:
    loop.execute_run(ctx, tasks, WideSearchData(root, config), None, grade=False)
except KeyboardInterrupt:
    print("interrupted")
'''
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    try:
        result = subprocess.run([sys.executable, "-c", code, str(tmp_path)], env=env,
                                text=True, capture_output=True, timeout=5)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "interrupted"
        pids = (tmp_path / "pids").read_text().splitlines()
        assert len(pids) == 1
        with pytest.raises(ProcessLookupError):
            os.kill(int(pids[0]), 0)
        assert not list((tmp_path / "runs").rglob("output.json"))
    finally:
        if (tmp_path / "pids").exists():
            for pid in (tmp_path / "pids").read_text().splitlines():
                try:
                    os.killpg(int(pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass


def test_final_evaluation_pairs_tasks_and_reuses_complete_archives(orchestration):
    from loop_research.evaluate import evaluate
    root, config, _, history = orchestration
    config.final.repeats = 2
    result = evaluate(root, config, "widesearch", split="test", final=True)
    assert result["task_count"] == 2 and result["repeats"] == 2
    assert result["judge"] == config.judge_label
    assert set(result["variants"]) == {"library", "empty"}
    assert len(history["agent"]) == 8
    assert len({ident for _, ident, empty in history["agent"] if empty}) == 2
    assert evaluate(root, config, "widesearch", split="test", final=True) == result
    assert len(history["agent"]) == len(history["grade"]) == 8
    for variant in result["variants"].values():
        assert "f1_by_item" in variant["metrics"]
        for path in variant["grade_paths"]:
            assert (root / path).is_file()


@pytest.mark.parametrize("benchmark,split", [("widesearch", "test"), ("wandr", None)])
def test_final_only_boundaries_checked_before_loading_data(tmp_path, benchmark, split):
    from loop_research.evaluate import evaluate
    with pytest.raises(ValueError, match="final"):
        evaluate(tmp_path, Config(), benchmark, split=split)


def test_interrupted_final_grade_resumes_without_research(orchestration, monkeypatch):
    from loop_research.evaluate import evaluate
    root, config, benchmark, history = orchestration
    grade = benchmark.grade
    failed = False

    def interrupt(task, submission, ctx):
        nonlocal failed
        if not failed:
            failed = True
            raise RuntimeError("Fixture interrupted grading")
        return grade(task, submission, ctx)

    monkeypatch.setattr(benchmark, "grade", interrupt)
    with pytest.raises(RuntimeError, match="interrupted"):
        evaluate(root, config, "widesearch", "test", True)
    result = evaluate(root, config, "widesearch", "test", True)
    assert len(history["agent"]) == 4
    assert result["task_count"] == 2


def test_final_fallback_date_is_shared_across_resume_and_variants(orchestration, monkeypatch):
    from loop_research import evaluate
    root, config, benchmark, history = orchestration
    benchmark.load_tasks()[4].as_of_date = date(2020, 1, 1)

    class FrozenDate(date):
        current = date(2026, 1, 1)

        @classmethod
        def today(cls):
            return cls.current

    monkeypatch.setattr(evaluate, "date", FrozenDate, raising=False)
    original = benchmark.grade
    interrupted = False

    def grade(task, submission, ctx):
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            raise RuntimeError("Fixture date crossing")
        return original(task, submission, ctx)

    monkeypatch.setattr(benchmark, "grade", grade)
    with pytest.raises(RuntimeError, match="date crossing"):
        evaluate.evaluate(root, config, "widesearch", "test", True)
    FrozenDate.current = date(2026, 1, 2)
    result = evaluate.evaluate(root, config, "widesearch", "test", True)
    assert result["fallback_as_of_date"] == "2026-01-01"
    for variant in result["variants"].values():
        for run_id in variant["run_ids"]:
            tasks = read_json(root / "runs" / run_id / "tasks.json")
            assert tasks[0]["as_of_date"] == "2020-01-01" and "fallback_as_of_date" not in tasks[0]["raw"]
            assert tasks[1]["as_of_date"] is None and tasks[1]["raw"]["fallback_as_of_date"] == "2026-01-01"
            evaluate.grade_run(root, run_id)
    assert len(history["agent"]) == len(history["grade"]) == 4
    frozen = next((root / "runs/evaluations").glob("*.json"))
    saved = read_json(frozen)
    saved["fallback_as_of_date"] = "2026-01-03"
    write_json(frozen, saved)
    with pytest.raises(ValueError, match="changed"):
        evaluate.evaluate(root, config, "widesearch", "test", True)


def test_train_run_grades_with_archived_config(orchestration):
    from loop_research.loop import run_train
    from loop_research.evaluate import grade_run
    root, config, _, history = orchestration
    run_id = run_train(root, config, 2)
    assert len(history["agent"]) == 2 and history["grade"] == []
    config.models.root = "fixture-changed"
    assert grade_run(root, run_id) == run_id
    grades = list((root / "runs" / run_id).glob("*/grade.json"))
    assert len(grades) == 2
    assert {read_json(p)["judge"] for p in grades} == {"codex/default"}
    assert grade_run(root, run_id) == run_id and len(history["grade"]) == 2


def test_improvement_sampling_resume_and_disk_report(orchestration):
    from loop_research.loop import improve
    from loop_research.report import build_report
    root, config, _, history = orchestration
    run_id = improve(root, config, 2)
    trained = [ident for run, ident, _ in history["agent"] if "-train" in run]
    assert len(trained) == len(set(trained)) == 3
    assert sorted(map(len, history["reflect"])) == [1, 2]
    assert (root / "reports/rounds.csv").is_file()
    before = list(history["agent"])
    assert improve(root, config, 2, resume=True) == run_id
    assert history["agent"] == before
    summary = build_report(root)
    assert summary.name == "summary.md"
    text = summary.read_text()
    assert "rounds.csv" in text and "codex/default" in text
    assert (root / "reports/validation_curve.png").is_file()
    config.loop.train_batch_size = 1
    with pytest.raises(ValueError, match="configuration"):
        improve(root, config, 3, resume=True)


def test_improvement_resumes_saved_reflection(orchestration, monkeypatch):
    from loop_research import loop
    root, config, _, history = orchestration
    original = loop.reflect

    def interrupted(*args):
        original(*args)
        raise RuntimeError("Fixture interruption after reflection save")

    monkeypatch.setattr(loop, "reflect", interrupted)
    with pytest.raises(RuntimeError, match="interruption"):
        loop.improve(root, config, 1)
    monkeypatch.setattr(loop, "reflect", original)
    loop.improve(root, config, 1, resume=True)
    assert len(history["reflect"]) == 1
    assert len([r for r in history["agent"] if "-train" in r[0]]) == 2


def test_counter_journal_recovers_commit_window_without_double_count(orchestration, monkeypatch):
    from loop_research import loop
    from loop_research.archive import RunContext
    root, config, _, _ = orchestration
    library = root / "skills"
    write_skill(library, Skill(id="sk_0001", title="Check sources", body="Check original sources.",
                              applies_to=["wide"], source_tasks=["fixture"]))
    sha = commit_library(library, "Fixture skill")
    ctx = RunContext(root, "fixture-counter", config)
    original = loop.commit_library

    def interrupted(*args):
        original(*args)
        raise RuntimeError("Fixture after commit")

    monkeypatch.setattr(loop, "commit_library", interrupted)
    with pytest.raises(RuntimeError, match="after commit"):
        loop.apply_feedback(ctx, library, {"sk_0001": "helped"}, "fixture-event", sha)
    monkeypatch.setattr(loop, "commit_library", original)
    loop.apply_feedback(ctx, library, {"sk_0001": "helped"}, "fixture-event", sha)
    assert load_skills(library)[0].counters.helpful == 1


def test_counter_journal_recovers_partial_file_write(orchestration, monkeypatch):
    from loop_research import loop
    from loop_research.archive import RunContext
    root, config, _, _ = orchestration
    library = root / "skills"
    write_skill(library, Skill(id="sk_0001", title="Check sources", body="Check original sources.",
                              applies_to=["wide"], source_tasks=["fixture"]))
    sha = commit_library(library, "Fixture skill")
    ctx = RunContext(root, "fixture-counter-write", config)
    original = loop.write_skill

    def interrupted(*args):
        original(*args)
        raise RuntimeError("Fixture after file write")

    monkeypatch.setattr(loop, "write_skill", interrupted)
    with pytest.raises(RuntimeError, match="file write"):
        loop.apply_feedback(ctx, library, {"sk_0001": "helped"}, "fixture-event", sha)
    monkeypatch.setattr(loop, "write_skill", original)
    loop.apply_feedback(ctx, library, {"sk_0001": "helped"}, "fixture-event", sha)
    assert load_skills(library)[0].counters.helpful == 1


def test_completed_resume_rebuilds_round_csv_after_interruption(orchestration, monkeypatch):
    from loop_research import loop, report
    root, config, _, history = orchestration
    original = report.write_rounds

    def interrupted(*args):
        raise RuntimeError("Fixture before csv")

    monkeypatch.setattr(report, "write_rounds", interrupted)
    with pytest.raises(RuntimeError, match="before csv"):
        loop.improve(root, config, 1)
    monkeypatch.setattr(report, "write_rounds", original)
    before = list(history["agent"])
    loop.improve(root, config, 1, resume=True)
    assert (root / "reports/rounds.csv").is_file()
    assert history["agent"] == before


def test_gate_repeats_same_val_tasks_and_applies_edits_sequentially(orchestration, monkeypatch):
    from loop_research import loop
    from loop_research.reflect import Reflection
    from loop_research.skills import EditOp
    root, config, benchmark, history = orchestration
    config.gate.repeats = 2

    def reflect_edits(tasks, contexts, ctx, train_ids):
        edits = [EditOp(op="add", title=title, body=body, applies_to=[tag], rationale="Fixture method",
                        evidence_task_ids=[tasks[0].task_id]) for title, body, tag in [
            ("Enumerate broadly", "Explore independent directories to discover candidate entities.", "wide"),
            ("Validate constraints", "Reject candidates unless original evidence supports every requested condition.", "constraint")]]
        result = Reflection(ops=edits, skill_feedback={})
        ctx.save("reflection.json", result.model_dump())
        return result

    def grade(task, submission, ctx):
        skills = load_skills(ctx.run_dir / "library")
        history["grade"].append((ctx.run_id, task.task_id))
        return GradeResult(metrics={"f1_by_row": .2 + .2 * len(skills), "score": 0.0},
                           primary_metric="f1_by_row", judge=ctx.config.judge_label)

    monkeypatch.setattr(loop, "reflect", reflect_edits)
    monkeypatch.setattr(benchmark, "grade", grade)
    run_id = loop.improve(root, config, 1)
    metrics = read_json(root / "runs" / run_id / "round-0001/round_metrics.json")
    assert metrics["ops_accepted"] == metrics["ops_proposed"] == metrics["active_skills"] == 2
    assert metrics["gate_score"] == pytest.approx(.6)
    gate_calls = [(run, task) for run, task, _ in history["agent"] if run.startswith("gate-")]
    assert len(gate_calls) == 6 and {task for _, task in gate_calls} == {"fixture-3"}
    assert all(s.gate.repeats == 2 for s in load_skills(root / "skills"))


@pytest.mark.parametrize("counts,expected_rate", [([(0, 0), (0, 0)], None), ([(1, 2), (2, 8)], .3)])
def test_wandr_final_keeps_metrics_fetch_and_excerpt_rate(orchestration, monkeypatch, counts, expected_rate):
    from loop_research.evaluate import evaluate
    from loop_research.report import build_report
    root, config, benchmark, _ = orchestration
    for task in benchmark.load_tasks():
        task.benchmark = "wandr"
    monkeypatch.setattr(benchmark, "final_tasks", lambda: benchmark.load_tasks()[4:], raising=False)
    monkeypatch.setattr(benchmark, "verify_sources", lambda: None, raising=False)

    def grade(task, submission, ctx):
        failures, judged = counts[int(task.task_id.rsplit("-", 1)[1]) - 4]
        return GradeResult(metrics={f"{mode}_{metric}_{scope}": .2 for mode in ("soft", "hard")
                                   for metric in ("precision", "recall", "f1") for scope in ("full", "retrieval")},
            primary_metric="soft_f1_full", judge=ctx.config.judge_label,
            provenance={"fetch": "wandr-browser", "harness_primary_metric": "soft_recall_full",
                        "dataset_revision": "fixture-dataset", "code_revision": "fixture-code"},
            errors={"excerpt_failures": failures, "excerpt_judged": judged,
                    "excerpt_failure_rate": failures / judged if judged else None, "unjudged_records": 1})

    monkeypatch.setattr(benchmark, "grade", grade)
    result = evaluate(root, config, "wandr", final=True)
    assert result["fetch"] == "wandr-browser"
    assert result["harness_primary_metric"] == "soft_recall_full"
    assert result["primary_metric"] == "soft_f1_full"
    assert result["provenance"]["code_revision"] == "fixture-code"
    assert all(v["excerpt_failure_rate"] == expected_rate and v["unjudged_records"] == 2 for v in result["variants"].values())
    assert all(len(v["metrics"]) == 12 for v in result["variants"].values())
    summary = build_report(root).read_text()
    assert "wandr-browser" in summary
    assert "excerpt_failure_rate | pooled | " + ("unavailable" if expected_rate is None else "0.3") in summary


def test_root_skill_decision_log_survives_completed_resume(orchestration, monkeypatch):
    from loop_research import loop
    from loop_research.reflect import Reflection
    from loop_research.skills import EditOp
    root, config, _, _ = orchestration

    def rejected(tasks, contexts, ctx, train_ids):
        result = Reflection(ops=[EditOp(op="add", title="Fixture leaked URL", body="Check https://example.org.",
            applies_to=["wide"], rationale="Fixture rejection", evidence_task_ids=[tasks[0].task_id])], skill_feedback={})
        ctx.save("reflection.json", result.model_dump())
        return result

    monkeypatch.setattr(loop, "reflect", rejected)
    run_id = loop.improve(root, config, 1)
    path = root / "runs" / run_id / "skills_rejected.jsonl"
    assert path.is_file() and len(path.read_text().splitlines()) == 1
    loop.improve(root, config, 1, resume=True)
    assert len(path.read_text().splitlines()) == 1


def test_grade_run_refuses_nonfinal_wandr_archive(tmp_path):
    from loop_research.archive import RunContext
    from loop_research.evaluate import grade_run
    ctx = RunContext(tmp_path, "fixture-wandr", Config())
    ctx.initialize("empty", benchmark="wandr", final=False)
    with pytest.raises(ValueError, match="final"):
        grade_run(tmp_path, ctx.run_id)
