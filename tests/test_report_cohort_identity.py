"""The real report verifier rejects otherwise passing evidence from another cohort."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from loop_research.report import render_table


HELPERS = Path(__file__).resolve().parents[1] / "runs/round2"
LABELS = ("A", "B1", "B0", "B1-frozen", "SI")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def read(path):
    return json.loads(path.read_text())


@pytest.fixture
def cohort(tmp_path):
    root = tmp_path / "repo"
    here = root / "runs/round2"
    here.mkdir(parents=True)
    (root / ".gitignore").write_text("runs/\n")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", ".gitignore"], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.org",
                    "commit", "-qm", "Fixture baseline"], check=True)
    commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    for name in ("verify_report.py", "generalization.py"):
        shutil.copyfile(HELPERS / name, here / name)
    manifest = {"runs": {}, "BASE": "a" * 40, "POST_A": "b" * 40,
                "source_commit": commit, "report_source_commit": commit}
    old_runs, quality, outputs, records, audits, metrics = {}, {}, {}, {}, {}, {}
    for index, label in enumerate(LABELS, 1):
        for age in ("current", "prior"):
            run_id = "research-" + f"{index + (10 if age == 'prior' else 0):032x}"
            task = root / "runs" / run_id / "fixture-task"
            record = {"run_id": run_id, "task_id": task.name, "status": "complete", "error": None,
                      "base_sha": manifest["POST_A"] if label in ("B1", "B1-frozen") else manifest["BASE"],
                      "learning": label not in ("B0", "B1-frozen")}
            task_spec = {"task_id": task.name, "question": "Fixture question", "spec": {"keys": ["quantity"]}}
            output = {"rows": [{"cells": {"quantity": {"value": "fixture", "quote": "fixture evidence",
                                                       "sources": ["https://example.org/"]}}}]}
            write(task.parent / "research.json", record)
            write(task / "task.json", task_spec)
            write(task / "output.json", output)
            write(task / "self_check.json", {"issues": []})
            write(task / "agent_result.json", {"uncited": []})
            (task.parent / "trace.jsonl").write_text("")
            prompt = 'TASK\nFixture question\nRELEVANT HARNESS\n[]\n\nTOOLS\nFixture tools'
            (task / "prompt.txt").write_text(prompt)
            (task / "root_prompt.txt").write_text(prompt)
            outputs[label, age] = task / "output.json"
            if age == "prior":
                old_runs[label] = run_id
                continue
            manifest["runs"][label] = run_id
            records[label] = record
            audit = {"run_id": run_id, "task_id": task.name, "task_path": str(task),
                     "largest_prompt": {"parts": {"instruction": 3}, "total": 3, "sha256": sha(b"abc")},
                     "overlap": {"ngram_chars": 50, "total_chars": 0, "fraction": 0},
                     "subcall_input_chars": 0, "subcalls": [], "subcall_prompt_chars": 0,
                     "subcall_schema_chars": 0, "subcall_count": 0, "fetches": [],
                     "rlms": [{"depth": 0, "iterations": 1, "termination": "answer_ready"}],
                     "source_files": [{"path": str(task / name), "sha256": sha((task / name).read_bytes())}
                                      for name in ("task.json", "output.json")]}
            metric = {"run_id": run_id, "manifest": record, "errors": [], "issues": [], "uncited_cells": 0,
                      "page_chars": 0, "rows": 1, "codex_calls": 1, "wall_s": 1.0, "signals": [],
                      "calls_by_purpose": {"root": 1}, "failed_fetches": 0}
            write(here / f"{label}.audit.json", audit)
            write(here / f"{label}.metrics.json", metric)
            (here / f"{label}.largest_root_prompt.txt").write_text("abc")
            audits[label], metrics[label] = audit, metric
        if label != "SI":
            quality[label] = {"run_id": manifest["runs"][label], "prior_run_id": old_runs[label],
                              "rows": 1, "prior_rows": 1, "same_key_set": True,
                              "only_current_keys": [], "only_prior_keys": [], "issues": [], "uncited": [],
                              "current_output": str(outputs[label, "current"]),
                              "prior_output": str(outputs[label, "prior"])}
    write(root / "runs/proof_manifest.json", {"runs": {k: v for k, v in old_runs.items() if k != "B1-frozen"}})
    write(root / "runs/followup/manifest.json", {"frozen_run": old_runs["B1-frozen"]})
    write(here / "quality_comparison.json", quality)
    controls = ("B0", "B1-frozen")
    prompt_hash = sha((outputs["B0", "current"].parent / "prompt.txt").read_bytes())
    without_harness = 'TASK\nFixture question\nRELEVANT HARNESS\n\n\nTOOLS\nFixture tools'
    control = {"controls_equal": True, "no_learning_verified": True, "BASE": manifest["BASE"],
               "POST_A": manifest["POST_A"], "run_ids": {k: manifest["runs"][k] for k in controls},
               "input_paths": {k: str(outputs[k, "current"].parent / "prompt.txt") for k in controls},
               "root_input_sha256": {k: prompt_hash for k in controls},
               "initial_retrieved_entries": {k: [] for k in controls},
               "full_context_without_harness_sha256": sha(without_harness.encode())}
    write(here / "control_audit.json", control)
    baseline = {"identity": {"run_id": old_runs["SI"], "task_id": "fixture-task"},
                "task": read(outputs["SI", "prior"].parent / "task.json"),
                "output": read(outputs["SI", "prior"]), "harness": {"initial_sha": manifest["BASE"]},
                "quality": {"row_count": 1},
                "artifacts": {name: {"path": str(outputs["SI", "prior"].parent / name),
                                     "sha256": sha((outputs["SI", "prior"].parent / name).read_bytes())}
                              for name in ("task.json", "output.json")}}
    write(here / "SI.baseline.json", baseline)
    old_metric = {"codex_calls": 1, "wall_s": 1.0, "root_iterations": 1, "page_chars": 0,
                  "max_root_prompt_chars": 3, "overlap_covered_chars": 0, "overlap_total_chars": 1,
                  "calls_by_purpose": {"sub": 0, "refine": 0}, "subcall_input_chars": 0,
                  "failed_fetches": 0, "rows": 1, "uncited": [], "issues": [],
                  "largest_prompt_parts": {"instruction": 3}}
    write(here / "SI_baseline/SI.metrics_partial.json", old_metric)
    si_task = outputs["SI", "current"].parent
    si = {"same_exact_task": True, "same_values": True, "quality_preserved": True,
          "issues": 0, "uncited": 0, "rows": 1, "measurements": [],
          "provenance": {"run_id": manifest["runs"]["SI"], "task_id": si_task.name,
                         "task_path": str(si_task), "base_sha": records["SI"]["base_sha"],
                         "task_sha256": sha((si_task / "task.json").read_bytes()),
                         "output_sha256": sha((si_task / "output.json").read_bytes()),
                         "baseline_path": str(here / "SI.baseline.json"),
                         "baseline_sha256": sha((here / "SI.baseline.json").read_bytes()),
                         "prior_run_id": old_runs["SI"]}}
    write(here / "SI.generalization.json", si)
    write(here / "validation_error_policy.json", {"user_clarification": "Record the validation error and recovery; preserve all counts"})
    write(here / "reviewed_error_events.json", {"policy": str(here / "validation_error_policy.json"), "entries": []})
    original = b"Original report bytes.\n"
    (root / "runs/proof_report.md").write_bytes(original)
    (here / "proof_report.before_round2.md").write_bytes(original)
    write(here / "original_report_identity.json", {"sha256": sha(original)})
    document = '# Round 2\n**RLM verdict: works**\n**Self-improvement verdict: works**\n## Original diagnosis\nmechanism evidence, not a statistical result\n'
    document += "\n".join(render_table(read(outputs[k, "current"])) for k in LABELS)
    (here / "Round2.md").write_text(document)
    write(here / "Round2.render.json", {"output_sha256": sha(document.encode())})
    write(here / "interpretation.json", {"checks": [{"id": i, "verdict": "works"} for i in range(1, 11)]})
    (here / "suite.log").write_text("1 passed\n")
    suite = {"exit_code": 0, "passed": 1, "log": str(here / "suite.log")}
    manifest.update(unit_suite=suite, reporting_unit_suite=suite, replay_coordinator=str(here / "coordinator.json"))
    write(here / "coordinator.json", {"preflight": {"source": {"commit": commit, "modules": []}}})
    write(here / "manifest.json", manifest)
    return here


def verify(here):
    return subprocess.run([sys.executable, str(here / "verify_report.py")], text=True, capture_output=True)


def mutate(here, filename, *path, value):
    data = read(here / filename)
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    write(here / filename, data)


def test_current_cohort_evidence_remains_accepted(cohort):
    result = verify(cohort)
    assert result.returncode == 0, result.stderr
    assert len(read(cohort / "report_verification.json")["runs"]) == 5


def test_byte_identical_copied_archives_with_same_durable_owner_are_accepted(cohort):
    quality = read(cohort / "quality_comparison.json")
    copied = {}
    for label in ("B0", "SI"):
        task = Path(read(cohort / f"{label}.audit.json")["task_path"])
        destination = cohort / "copies" / task.parent.name
        shutil.copytree(task.parent, destination)
        copied[label] = destination / task.name
    quality["B0"]["current_output"] = str(copied["B0"] / "output.json")
    write(cohort / "quality_comparison.json", quality)
    mutate(cohort, "control_audit.json", "input_paths", "B0", value=str(copied["B0"] / "prompt.txt"))
    mutate(cohort, "SI.generalization.json", "provenance", "task_path", value=str(copied["SI"]))
    result = verify(cohort)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("component,event_name,allowed", [("REPL", "code.end", True),
                                                         ("tools.check_constraint", "call.end", False)])
def test_existing_reviewed_error_policy_still_distinguishes_tool_misuse(cohort, component, event_name, allowed):
    audit = read(cohort / "A.audit.json")
    error = {"component": component, "event": event_name, "details": {"error": "AssertionError: citation mismatch"}}
    recovered = {"component": "REPL", "event": "code.end", "details": {"error": ""}}
    (Path(audit["task_path"]).parent / "trace.jsonl").write_text(json.dumps(error) + "\n" + json.dumps(recovered) + "\n")
    recorded = {**error, "line": 1}
    mutate(cohort, "A.metrics.json", "errors", value=[recorded])
    mutate(cohort, "reviewed_error_events.json", "entries", value=[{
        "label": "A", "run_id": audit["run_id"], "event": recorded,
        "classification": "validation_recovered", "reason": "Deliberate citation check and repair.",
        "recovery_trace_lines": [2]}])
    result = verify(cohort)
    assert (result.returncode == 0) is allowed, result.stderr
    if allowed:
        assert read(cohort / "report_verification.json")["recorded_recovered_errors"] == 1


@pytest.mark.parametrize("field", ["run_ids", "BASE", "POST_A", "input_paths", "root_input_sha256",
                                   "initial_retrieved_entries", "full_context_without_harness_sha256"])
def test_stale_control_artifact_cannot_certify_current_cohort(cohort, field):
    values = {"run_ids": {"B0": "old", "B1-frozen": "old"}, "BASE": "old", "POST_A": "old",
              "input_paths": {"B0": str(Path(read(cohort / "quality_comparison.json")["B0"]["prior_output"]).parent / "prompt.txt"),
                              "B1-frozen": read(cohort / "control_audit.json")["input_paths"]["B1-frozen"]},
              "root_input_sha256": {"B0": "old", "B1-frozen": "old"},
              "initial_retrieved_entries": {"B0": ["old"], "B1-frozen": []},
              "full_context_without_harness_sha256": "old"}
    mutate(cohort, "control_audit.json", field, value=values[field])
    result = verify(cohort)
    assert result.returncode != 0, "stale control artifact was accepted"
    assert not (cohort / "report_verification.json").exists()


@pytest.mark.parametrize("field", ["run_id", "current_output", "prior_run_id", "prior_output", "row_counts", "only_current_keys"])
def test_stale_quality_artifact_cannot_certify_current_outputs(cohort, field):
    quality = read(cohort / "quality_comparison.json")
    if field == "row_counts":
        quality["A"].update(rows=2, prior_rows=2)
    else:
        quality["A"][field] = {"run_id": "old", "prior_run_id": "old", "current_output": quality["A"]["prior_output"],
                                "prior_output": quality["A"]["current_output"], "only_current_keys": [["old"]]}[field]
    write(cohort / "quality_comparison.json", quality)
    result = verify(cohort)
    assert result.returncode != 0, "stale quality artifact was accepted"
    assert not (cohort / "report_verification.json").exists()


@pytest.mark.parametrize("field", ["run_id", "task_id", "task_path", "base_sha", "task_sha256", "output_sha256",
                                   "baseline_path", "baseline_sha256", "prior_run_id", "missing"])
def test_stale_generalization_artifact_cannot_certify_current_run(cohort, field):
    data = read(cohort / "SI.generalization.json")
    if field == "missing":
        data.pop("provenance")
    elif field == "task_path":
        data["provenance"][field] = str(Path(read(cohort / "SI.baseline.json")["artifacts"]["output.json"]["path"]).parent)
    elif field == "baseline_path":
        other = cohort / "stale_baseline.json"
        old = read(cohort / "SI.baseline.json")
        old["identity"]["run_id"] = "old"
        write(other, old)
        data["provenance"][field] = str(other)
    else:
        data["provenance"][field] = "old"
    write(cohort / "SI.generalization.json", data)
    result = verify(cohort)
    assert result.returncode != 0, "stale generalization artifact was accepted"
    assert not (cohort / "report_verification.json").exists()


def test_generalization_generator_archives_actual_run_and_output_identity(cohort):
    expected = copy.deepcopy(read(cohort / "SI.generalization.json")["provenance"])
    result = subprocess.run([sys.executable, str(cohort / "generalization.py")], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    generated = read(cohort / "SI.generalization.json")
    assert generated["provenance"] == expected
    assert generated["same_values"] is True and generated["quality_preserved"] is True
    assert generated["rows"] == 1 and generated["issues"] == generated["uncited"] == 0
    assert verify(cohort).returncode == 0
