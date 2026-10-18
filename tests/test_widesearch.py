"""Grading uses hand-written fixtures; integrity checks use pinned release bytes."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from loop_research.benchmarks.widesearch.grader import error_breakdown, official_modules


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
                           {"entity": "partial", "entity_exact_match": 1, "value_exact_match": 0}])
    assert error_breakdown(detail, evaluation) == {
        "missing_entities": [{"entity": "missing"}], "wrong_additions": [{"entity": "extra"}],
        "partial_rows": [{"entity": {"entity": "partial"}, "columns": ["value"]}]}


def test_adapter_grade_preserves_metrics_and_label(ctx, benchmark, task, output, capsys):
    from loop_research.benchmarks.widesearch.grader import WideSearchBenchmark

    ctx.config.models.root = "fixture-root"
    ctx.config.models.judge = "fixture-judge"
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
    assert result.judge == "codex/fixture-judge"
    assert result.primary_metric == "f1_by_row"
    assert result.errors == {"missing_entities": [], "wrong_additions": [], "partial_rows": []}
    assert (ctx.path / "alignment.csv").exists()
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


@pytest.mark.parametrize("verdict", [None, {}, {"idx_0": .5}, {"idx_0": True}, {"idx_1": 1}, {"idx_0": 1, "extra": 0}])
def test_official_judge_rejects_malformed_scores(ctx, benchmark, verdict):
    from loop_research.benchmarks.widesearch.grader import _BACKEND
    class Judge:
        def __init__(self):
            self.ctx = ctx
        def complete(self, prompt, **kwargs):
            assert kwargs == {"purpose": "grade", "model": ctx.config.models.judge}
            return '```json\n' + json.dumps(verdict) + '\n```'
    token = _BACKEND.set(Judge())
    try:
        metric = official_modules(benchmark.code)["src.evaluation.metric_utils"]
        with pytest.raises(ValueError, match="judge"):
            metric.llm_judge_column(["fixture-response"], ["fixture-target"], "Fixture criterion", "official-config")
    finally:
        _BACKEND.reset(token)
    assert not list((ctx.path / "judge_cache").glob("*.json"))


@pytest.mark.parametrize("judge", ["fixture-judge", "other-fixture-judge"])
def test_official_judge_uses_codex_and_reuses_valid_verdict(ctx, benchmark, judge):
    from loop_research.benchmarks.widesearch.grader import _BACKEND
    ctx.config.models.root = "fixture-root"
    ctx.config.models.judge = judge
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
    assert calls[0][1] == {"purpose": "grade", "model": judge}
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


def test_preparation_exposes_complete_release_without_saved_partitions(benchmark, monkeypatch, widesearch_download):
    import shutil
    from loop_research.archive import read_json
    from loop_research.benchmarks.widesearch import data

    shutil.copytree(widesearch_download, benchmark.download)
    def no_network(*args, **kwargs):
        raise AssertionError('The pinned release is already downloaded')
    monkeypatch.setattr(data.urllib.request, 'urlopen', no_network)
    benchmark.prepare()
    benchmark.verify_data()
    release = [json.loads(line) for line in (widesearch_download / 'widesearch.jsonl').read_text().splitlines()]
    assert {task.task_id for task in benchmark.load_tasks()} == {row['instance_id'] for row in release}
    assert read_json(benchmark.download / 'revision.json') == {
        'dataset': data.DATASET_REVISION, 'code': data.CODE_REVISION}
    assert not (benchmark.root / 'data/splits.json').exists()
    assert not (benchmark.root / 'data/gate_batch.json').exists()

    benchmark.config.data.languages = ['zh']
    tasks = benchmark.load_tasks()
    assert {task.task_id for task in tasks} == {row['instance_id'] for row in release if row['language'] == 'zh'}
    assert all(task.language == 'zh' for task in tasks)


@pytest.mark.parametrize('metric', ['missing', None, float('nan'), 0])
def test_error_breakdown_treats_unavailable_metrics_as_failed_checks(metric):
    evaluation = {'required': ['entity', 'value'], 'unique_columns': ['entity'],
                  'eval_pipeline': {'entity': {'metric': ['in_match']},
                                    'value': {'metric': ['exact_match']}}}
    row = {'entity': 'fixture', 'exist_flag_gt': 1, 'exist_flag_response': 1,
           'entity_exact_match': 1}
    if metric != 'missing':
        row['value_exact_match'] = metric
    assert error_breakdown(pd.DataFrame([row]), evaluation) == {
        'missing_entities': [], 'wrong_additions': [],
        'partial_rows': [{'entity': {'entity': 'fixture'}, 'columns': ['value']}]}


def test_empty_grade_uses_official_absent_response_without_judge_or_stale_alignment(ctx, benchmark, task):
    from loop_research.benchmarks.widesearch.grader import WideSearchBenchmark
    graded = WideSearchBenchmark(ctx.root, ctx.config)
    graded.code = benchmark.code
    graded.download.mkdir(parents=True)
    query = fixture_query(official_modules(graded.code))
    # Even judge-based criteria must not invoke a model for an absent response.
    query.evaluation['eval_pipeline']['value']['metric'] = ['llm_judge']
    row = {'instance_id': task.task_id, 'query': task.question,
           'evaluation': json.dumps(query.evaluation), 'language': 'en'}
    (graded.download / 'widesearch.jsonl').write_text(json.dumps(row) + '\n')
    gold = graded.download / 'widesearch_gold'
    gold.mkdir()
    query.answer.to_csv(gold / 'fixture.csv', index=False)
    ctx.path.mkdir(parents=True)
    (ctx.path / 'alignment.csv').write_text('stale alignment from previous attempt')
    class NoJudge:
        def complete(self, *args, **kwargs):
            raise AssertionError('Empty official submissions need no model call')
    submission = graded.to_submission(task, graded.output_contract(task).empty)
    grade = graded.grade(task, submission, ctx, backend=NoJudge())
    assert grade.primary_metric == 'f1_by_row'
    assert grade.metrics == {'score': 0, 'precision_by_row': 0, 'recall_by_row': 0,
                             'f1_by_row': 0, 'precision_by_item': 0, 'recall_by_item': 0, 'f1_by_item': 0}
    assert grade.errors == {'missing_entities': [{'entity': 'fixture-a'}],
                            'wrong_additions': [], 'partial_rows': []}
    assert grade.provenance['official_message'] == 'response is None'
    assert grade.provenance['alignment'] is None
    assert not (ctx.path / 'alignment.csv').exists()
