"""Opt-in subscription/web tests. Never selected by the default pytest command."""
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from loop_research.archive import read_json
from loop_research.cli import app
from loop_research.config import Config
from loop_research.skills import init_library

pytestmark = pytest.mark.live


@pytest.fixture
def live_workspace(tmp_path):
    source = Path(__file__).resolve().parents[1]
    config = Config.load(source / "config.yaml")
    config.wandr.final_n_tasks = 1
    config.final.repeats = 1
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(config.model_dump(), sort_keys=False))
    (tmp_path / "data").mkdir()
    for name in ("downloads", "vendor"):
        path = source / "data" / name
        if path.exists():
            (tmp_path / "data" / name).symlink_to(path, target_is_directory=True)
    init_library(tmp_path / "skills")
    return tmp_path, config


def invoke(root, *arguments):
    result = CliRunner().invoke(app, ["--root", str(root), *arguments])
    assert result.exit_code == 0, f"{result.output}\n{result.exception}"
    return result.stdout.strip()


def test_live_smoke(live_workspace):
    root, _ = live_workspace
    run_id = invoke(root, "smoke")
    archive = root / "runs" / run_id
    assert read_json(archive / "run_summary.json")["status"] == "complete"
    assert read_json(archive / "smoke/smoke.json")["rlm"] == "5"
    assert (archive / "smoke/codex_calls.jsonl").stat().st_size > 0
    assert (archive / "smoke/trajectory.jsonl").stat().st_size > 0


def test_live_widesearch_train_task(live_workspace):
    from loop_research.benchmarks.widesearch.data import WideSearchData
    root, config = live_workspace
    adapter = WideSearchData(root, config)
    adapter.verify_data()
    adapter.verify_code()
    adapter.prepare_splits(config.data.seed)
    run_id = invoke(root, "run", "--split", "train", "--n", "1")
    invoke(root, "grade", "--run", run_id)
    archive = root / "runs" / run_id
    tasks = read_json(archive / "tasks.json")
    assert len(tasks) == 1
    task_path = archive / tasks[0]["task_id"]
    for name in ("output.json", "submission.json", "grade.json"):
        assert (task_path / name).is_file()
    assert read_json(task_path / "grade.json")["primary_metric"] == "f1_by_row"


def test_live_wandr_task_through_official_harness(live_workspace):
    from loop_research import evaluate
    root, config = live_workspace
    adapter = evaluate._benchmark("wandr", root, config)
    adapter.verify_sources()
    adapter.prepare_final_subset(config.wandr.seed)
    invoke(root, "evaluate", "--benchmark", "wandr", "--final")
    result = read_json(root / "reports/final_wandr.json")
    assert result["task_count"] == 1
    assert result["fetch"] == "wandr-browser" and result["judge"].startswith("codex/")
    assert set(result["variants"]) == {"library", "empty"}
    for variant in result["variants"].values():
        assert variant["grade_paths"]
        for relative in variant["grade_paths"]:
            grade = read_json(root / relative)
            assert grade["metrics"] and grade["provenance"]["fetch"] == "wandr-browser"
            assert grade["primary_metric"] in grade["metrics"]
