"""Runtime bytes and later report bytes are verified against their own Git commits."""
import copy
import importlib.util
from pathlib import Path
import shutil
import subprocess

import pytest


# Keep the prepared repository fixture and helper from this checkout together
# even when the parent runs its complete suite plus this uniquely named file.
spec = importlib.util.spec_from_file_location(
    "source_provenance_cohort", Path(__file__).with_name("test_report_cohort_identity.py"))
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
cohort, read, write, verify, sha = fixtures.cohort, fixtures.read, fixtures.write, fixtures.verify, fixtures.sha


def commit_report(here):
    root = here.parents[1]
    subprocess.run(["git", "-C", str(root), "add", "src"], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.org",
                    "commit", "-qm", "Report analysis revision"], check=True)
    commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    manifest = read(here / "manifest.json")
    manifest["report_source_commit"] = commit
    write(here / "manifest.json", manifest)
    return commit


def change_report_module(here, content=b"VALUE = 2\n"):
    runtime = read(here / "coordinator.json")["preflight"]["source"]
    module = runtime["modules"][0]
    (here.parents[1] / module["source"]).write_bytes(content)
    Path(module["installed"]).write_bytes(content)
    return module, commit_report(here)


def test_unchanged_versions_verify_every_runtime_and_installed_module(cohort):
    result = verify(cohort)
    assert result.returncode == 0, result.stderr
    report = read(cohort / "report_verification.json")
    provenance = report["source_provenance"]
    assert provenance["runtime_module_count"] == provenance["report_module_count"] == 1
    assert provenance["runtime_modules_verified"] is provenance["report_modules_verified"] is True
    assert provenance["changed_modules"] == []
    assert report["research_modules_unchanged"] is True
    assert {entry["label"] for entry in provenance["completion_receipts"]} == set(fixtures.LABELS)
    assert all(entry["source_unchanged"] is True for entry in provenance["completion_receipts"])


def test_later_committed_report_revision_preserves_historical_runtime_proof(cohort):
    coordinator_before = (cohort / "coordinator.json").read_bytes()
    module, report_commit = change_report_module(cohort)
    result = verify(cohort)
    assert result.returncode == 0, result.stderr
    report = read(cohort / "report_verification.json")
    provenance = report["source_provenance"]
    assert report["research_modules_unchanged"] is False
    assert provenance["runtime_commit"] == read(cohort / "manifest.json")["source_commit"]
    assert provenance["report_commit"] == report_commit
    assert provenance["changed_modules"] == [{"source": module["source"], "change": "modified",
                                               "runtime_sha256": sha(b"VALUE = 1\n"),
                                               "report_sha256": sha(b"VALUE = 2\n")}]
    assert (cohort / "coordinator.json").read_bytes() == coordinator_before


def test_all_added_deleted_and_modified_modules_are_reported_without_filename_exemptions(cohort):
    runtime = read(cohort / "coordinator.json")["preflight"]["source"]
    root = cohort.parents[1]
    original = runtime["modules"][0]
    (root / original["source"]).unlink()
    Path(original["installed"]).unlink()
    for name, data in (("agent.py", b"agent revision\n"), ("analysis.py", b"analysis revision\n")):
        (root / "src/loop_research" / name).write_bytes(data)
        (Path(runtime["package_root"]) / name).write_bytes(data)
    commit_report(cohort)
    result = verify(cohort)
    assert result.returncode == 0, result.stderr
    provenance = read(cohort / "report_verification.json")["source_provenance"]
    assert provenance["runtime_module_count"] == 1 and provenance["report_module_count"] == 2
    assert provenance["changed_modules"] == [
        {"source": "src/loop_research/agent.py", "change": "added", "runtime_sha256": None,
         "report_sha256": sha(b"agent revision\n")},
        {"source": "src/loop_research/analysis.py", "change": "added", "runtime_sha256": None,
         "report_sha256": sha(b"analysis revision\n")},
        {"source": original["source"], "change": "deleted", "runtime_sha256": sha(b"VALUE = 1\n"),
         "report_sha256": None}]


@pytest.mark.parametrize("case", ["missing_module", "duplicate_module", "wrong_hash", "wrong_length",
                                 "wrong_source", "wrong_installed_mapping", "wrong_runtime_commit"])
def test_invalid_or_incomplete_runtime_snapshot_is_rejected(cohort, case):
    coordinator = read(cohort / "coordinator.json")
    runtime = coordinator["preflight"]["source"]
    module = runtime["modules"][0]
    if case == "missing_module":
        runtime["modules"] = []
    elif case == "duplicate_module":
        runtime["modules"].append(copy.deepcopy(module))
    elif case == "wrong_hash":
        module["sha256"] = "0" * 64
    elif case == "wrong_length":
        module["bytes"] += 1
    elif case == "wrong_source":
        module["source"] = "src/loop_research/missing.py"
    elif case == "wrong_installed_mapping":
        other = Path(runtime["package_root"]) / "unrelated.py"
        other.write_bytes(b"VALUE = 1\n")
        module["installed"] = str(other)
    else:
        runtime["commit"] = "0" * 40
    write(cohort / "coordinator.json", coordinator)
    assert verify(cohort).returncode != 0


@pytest.mark.parametrize("case", ["stale_install", "missing_install", "extra_install", "uncommitted_source",
                                 "untracked_source", "wrong_report_commit"])
def test_current_report_source_and_installation_must_exactly_match_report_commit(cohort, case):
    module, _ = change_report_module(cohort)
    if case == "stale_install":
        Path(module["installed"]).write_bytes(b"VALUE = 1\n")
    elif case == "missing_install":
        Path(module["installed"]).unlink()
    elif case == "extra_install":
        Path(module["installed"]).with_name("stale.py").write_bytes(b"unexpected\n")
    elif case == "uncommitted_source":
        (cohort.parents[1] / module["source"]).write_bytes(b"VALUE = 3\n")
    elif case == "untracked_source":
        (cohort.parents[1] / "src/loop_research/extra.py").write_bytes(b"unexpected\n")
    else:
        manifest = read(cohort / "manifest.json")
        manifest["report_source_commit"] = manifest["source_commit"]
        write(cohort / "manifest.json", manifest)
    assert verify(cohort).returncode != 0


@pytest.mark.parametrize("case", ["missing_arm", "wrong_run", "wrong_commit", "changed_source",
                                 "incomplete", "failed_process", "wrong_path", "owner_error"])
def test_completion_receipts_must_attest_the_correct_run_and_runtime_version(cohort, case):
    coordinator = read(cohort / "coordinator.json")
    receipt = coordinator["arms"]["A"]
    if case == "missing_arm":
        del coordinator["arms"]["A"]
    elif case == "wrong_run":
        receipt["run_id"] = "research-wrong"
    elif case == "wrong_commit":
        receipt["source_commit"] = "0" * 40
    elif case == "changed_source":
        receipt["source_unchanged"] = False
    elif case == "incomplete":
        receipt["status"] = "running"
    elif case == "failed_process":
        receipt["exit_code"] = 1
    elif case == "wrong_path":
        receipt["run_path"] = coordinator["arms"]["B0"]["run_path"]
    else:
        path = Path(receipt["run_path"]) / "research.json"
        owner = read(path)
        owner["error"] = "runtime error"
        write(path, owner)
        # Keep other ownership checks satisfied so the receipt gate is tested.
        metric = read(cohort / "A.metrics.json")
        metric["manifest"] = owner
        write(cohort / "A.metrics.json", metric)
    write(cohort / "coordinator.json", coordinator)
    assert verify(cohort).returncode != 0


@pytest.mark.parametrize("case", ["valid", "missing_receipt", "wrong_run", "changed_source", "wrong_commit"])
def test_explicit_completion_is_bound_to_its_own_receipt(cohort, case):
    manifest = read(cohort / "manifest.json")
    coordinator = read(cohort / "coordinator.json")
    prior = coordinator["arms"]["A"]
    run_id = "research-" + "e" * 32
    archive = Path(prior["run_path"]).with_name(run_id)
    shutil.copytree(prior["run_path"], archive)
    owner = read(archive / "research.json")
    owner["run_id"] = run_id
    write(archive / "research.json", owner)
    audit = read(cohort / "A.audit.json")
    audit.update(run_id=run_id, task_path=str(archive / owner["task_id"]))
    write(cohort / "explicit.audit.json", audit)
    metric = read(cohort / "A.metrics.json")
    metric.update(run_id=run_id, manifest=owner)
    write(cohort / "explicit.metrics.json", metric)
    shutil.copyfile(cohort / "A.largest_root_prompt.txt", cohort / "explicit.largest_root_prompt.txt")
    manifest["runs"]["explicit"] = run_id
    write(cohort / "manifest.json", manifest)
    receipt = {**prior, "run_id": run_id, "run_path": str(archive)}
    if case == "wrong_run":
        receipt["run_id"] = prior["run_id"]
    elif case == "changed_source":
        receipt["source_unchanged"] = False
    elif case == "wrong_commit":
        receipt["source_commit"] = "0" * 40
    if case != "missing_receipt":
        write(cohort / "explicit_execution.json", receipt)
    result = verify(cohort)
    if case == "valid":
        assert result.returncode == 0, result.stderr
        receipts = read(cohort / "report_verification.json")["source_provenance"]["completion_receipts"]
        assert len(receipts) == 6
        assert next(entry for entry in receipts if entry["label"] == "explicit")["run_id"] == run_id
    else:
        assert result.returncode != 0
