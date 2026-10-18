"""All tables in this module are hand-written fixtures, not benchmark data."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

from loop_research.benchmarks.widesearch.grader import error_breakdown, official_modules
from loop_research.benchmarks.widesearch.data import deterministic_split


def fixture_query(modules):
    return modules["src.evaluation.data_loader"].WideSearchQuery("fixture", "Hand-written fixture", {
        "required": ["entity", "value"], "unique_columns": ["entity"],
        "eval_pipeline": {"entity": {"preprocess": ["norm_str"], "metric": ["in_match"]},
                          "value": {"preprocess": ["norm_str"], "metric": ["exact_match"]}}},
        pd.DataFrame([{"entity": "fixture-a", "value": "fixture-value"}]), "en")


def test_unchanged_official_evaluator_fixture(benchmark, task, output):
    modules = official_modules(benchmark.code)
    query = fixture_query(modules)
    response = modules["src.evaluation.data_loader"].WideSearchResponse(**benchmark.to_submission(task, output))
    result = modules["src.evaluation.evaluation"].evaluate_single_query(query, response)
    assert result.f1_by_row == 1 and result.f1_by_item == 1 and result.score == 1, result.msg


def test_official_import_and_evaluation_are_quiet(benchmark):
    code = f'''
from loop_research.benchmarks.widesearch.grader import official_modules
modules = official_modules({str(benchmark.code)!r})
modules['src.evaluation.evaluation'].evaluate_single_query(type('Query', (), {{'instance_id': 'fixture'}})(), None)
'''
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                            env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / 'src')})
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""


def test_official_table_parser_and_empty_submission(benchmark, task, output):
    output["rows"][0]["cells"]["value"]["value"] = 'text|with "quotes"'
    module = official_modules(benchmark.code)["src.evaluation.data_loader"]
    response = module.WideSearchResponse(**benchmark.to_submission(task, output))
    assert response.extract_dataframe().iloc[0]["value"] == 'text|with "quotes"'
    assert benchmark.to_submission(task, {"rows": []}) is None


def test_error_breakdown_uses_official_alignment():
    evaluation = {"required": ["entity", "value"], "unique_columns": ["entity"],
                  "eval_pipeline": {"entity": {"metric": ["exact_match"]}, "value": {"metric": ["exact_match"]}}}
    detail = pd.DataFrame([{"entity": "missing", "exist_flag_gt": 1},
                           {"entity": "extra", "exist_flag_response": 1},
                           {"entity": "partial", "value_exact_match": 0}])
    assert error_breakdown(detail, evaluation) == {
        "missing_entities": [{"entity": "missing"}], "wrong_additions": [{"entity": "extra"}],
        "partial_rows": [{"entity": {"entity": "partial"}, "columns": ["value"]}]}


def test_split_determinism_and_disjointness(task):
    tasks = [task.model_copy(update={"task_id": f"fixture-{lang}-{i}", "language": lang})
             for lang in ("en", "zh") for i in range(10)]
    proportions = {"train": .6, "val": .2, "test": .2}
    splits = deterministic_split(tasks, 42, proportions)
    assert splits == deterministic_split(list(reversed(tasks)), 42, proportions)
    assert splits != deterministic_split(tasks, 43, proportions)
    assert len(set().union(*map(set, splits.values()))) == len(tasks)
    assert sum(map(len, splits.values())) == len(tasks)
    assert all(sum(lang in item for item in splits[split]) == n
               for split, n in (("train", 6), ("val", 2), ("test", 2)) for lang in ("en", "zh"))


def test_adapter_grade_preserves_metrics_and_label(ctx, benchmark, task, output, capsys):
    from loop_research.benchmarks.widesearch.grader import WideSearchBenchmark

    graded = WideSearchBenchmark(ctx.root, ctx.config)
    graded.code = benchmark.code
    graded.download.mkdir(parents=True)
    modules = official_modules(graded.code)
    query = fixture_query(modules)
    row = {"instance_id": "fixture", "query": task.question,
           "evaluation": json.dumps(query.evaluation), "language": "en"}
    (graded.download / "widesearch.jsonl").write_text(json.dumps(row) + "\n")
    gold = graded.download / "widesearch_gold"
    gold.mkdir()
    query.answer.to_csv(gold / "fixture.csv", index=False)
    result = graded.grade(task, graded.to_submission(task, output), ctx)
    assert result.metrics["score"] == result.metrics["f1_by_row"] == result.metrics["f1_by_item"] == 1
    assert result.judge == "codex/default"
    assert result.primary_metric == "f1_by_row"
    assert result.errors == {"missing_entities": [], "wrong_additions": [], "partial_rows": []}
    assert (ctx.path / "alignment.csv").exists()
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""
