"""Grading uses hand-written fixtures; integrity checks use pinned release bytes."""
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


import pytest


@pytest.mark.parametrize("verdict", [None, {}, {"idx_0": .5}, {"idx_0": True}, {"idx_1": 1}, {"idx_0": 1, "extra": 0}])
def test_official_judge_rejects_malformed_scores(ctx, benchmark, verdict):
    from loop_research.benchmarks.widesearch.grader import _BACKEND
    class Judge:
        def __init__(self):
            self.ctx = ctx
        def complete(self, prompt, **kwargs):
            assert kwargs == {"purpose": "grade", "model": None}
            return '```json\n' + json.dumps(verdict) + '\n```'
    token = _BACKEND.set(Judge())
    try:
        metric = official_modules(benchmark.code)["src.evaluation.metric_utils"]
        with pytest.raises(ValueError, match="judge"):
            metric.llm_judge_column(["fixture-response"], ["fixture-target"], "Fixture criterion", "official-config")
    finally:
        _BACKEND.reset(token)
    assert not list((ctx.path / "judge_cache").glob("*.json"))


def test_official_judge_uses_codex_and_reuses_valid_verdict(ctx, benchmark):
    from loop_research.benchmarks.widesearch.grader import _BACKEND
    calls = []
    class Judge:
        def __init__(self):
            self.ctx = ctx
        def complete(self, prompt, **kwargs):
            calls.append((prompt, kwargs))
            return '```json\n{"idx_0": 1}\n```'
    token = _BACKEND.set(Judge())
    try:
        metric = official_modules(benchmark.code)["src.evaluation.metric_utils"]
        for _ in range(2):
            assert metric.llm_judge_column(["fixture-response"], ["fixture-target"], "Fixture criterion", "official-config")[0] == [1]
    finally:
        _BACKEND.reset(token)
    assert len(calls) == 1
    assert calls[0][0] == metric.eval_column_prompt.format(criterion="Fixture criterion", response={"idx_0": {"response": "fixture-response", "target": "fixture-target"}})


@pytest.mark.parametrize("filename", ["widesearch.jsonl", "widesearch_gold/ws_en_001.csv"])
def test_preparation_rejects_corrupted_pinned_downloads(benchmark, monkeypatch, filename, widesearch_download):
    import shutil
    from loop_research.benchmarks.widesearch import data
    shutil.copytree(widesearch_download, benchmark.download)
    (benchmark.download / filename).write_text('corrupted fixture')
    (benchmark.download / 'revision.json').write_text(json.dumps({'dataset': data.DATASET_REVISION, 'code': data.CODE_REVISION}))
    def no_network(*args, **kwargs):
        raise AssertionError('Existing downloads must be validated before reuse')
    monkeypatch.setattr(data.urllib.request, 'urlopen', no_network)
    with pytest.raises(ValueError, match='integrity'):
        benchmark.prepare()


def test_saved_splits_cannot_move_test_tasks_into_training(benchmark, task, monkeypatch):
    from loop_research.archive import read_json, write_json
    tasks = [task.model_copy(update={'task_id': f'fixture-{i}'}) for i in range(10)]
    monkeypatch.setattr(benchmark, 'load_tasks', lambda: tasks)
    benchmark.config.gate.val_batch_size = 2
    benchmark.prepare_splits(42)
    path = benchmark.root / 'data/splits.json'
    saved = read_json(path)
    saved['splits']['train'][0], saved['splits']['test'][0] = saved['splits']['test'][0], saved['splits']['train'][0]
    write_json(path, saved)
    with pytest.raises(ValueError, match='split'):
        benchmark.split_tasks('train')
