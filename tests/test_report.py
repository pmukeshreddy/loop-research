"""Reporting fixtures are hand-written, never benchmark results."""
import csv
from pathlib import Path

import pytest

from loop_research.archive import write_json


def save_stream(root, run_id, config, *, learning=True, scores=(.2, None, .8), **changes):
    tasks = [{
        'index': index, 'task_id': f'fixture-{index}', 'score': score,
        'primary_metric': 'fixture_metric' if score is not None else None, 'judge': 'codex/fixture-judge',
        'error': 'fixture grader failure' if score is None else None,
        'harness_before': f'before-{index}', 'harness_after': f'after-{index}',
    } for index, score in enumerate(scores, 1)]
    manifest = {
        'run_id': run_id, 'benchmark': 'widesearch', 'learning': learning,
        'base_sha': 'fixture-base', 'task_ids': [row['task_id'] for row in tasks],
        'config': config.model_dump(), 'judge': 'codex/fixture-judge', 'tasks': tasks,
    }
    manifest.update(changes)
    write_json(root / 'reports' / run_id / 'stream.json', manifest)
    return manifest


def test_report_keeps_failed_scores_missing_and_rolling_window_explicit(tmp_path, config):
    from loop_research.report import build_report
    config.stream.rolling_window = 2
    save_stream(tmp_path, 'fixture-learning', config)
    result = build_report(tmp_path)
    assert result == tmp_path / 'reports/summary.md'
    rows = list(csv.DictReader((tmp_path / 'reports/tasks.csv').open()))
    assert [row['score'] for row in rows] == ['0.2', '', '0.8']
    assert [row['rolling_mean'] for row in rows] == ['0.2', '0.2', '0.8']
    assert [row['rolling_scored'] for row in rows] == ['1', '1', '1']
    assert rows[1]['status'] == 'failed' and rows[1]['error'] == 'fixture grader failure'
    assert rows[1]['source'] == 'reports/fixture-learning/stream.json'
    summary = result.read_text()
    assert 'fixture grader failure' in summary
    assert 'codex/fixture-judge' in summary
    assert 'fixture-learning/stream.json' in summary
    assert 'No comparable learning and no-learning streams' in summary
    assert (tmp_path / 'reports/learning_curve.png').read_bytes().startswith(b'\x89PNG\r\n\x1a\n')


def test_report_compares_only_jointly_scored_tasks_from_the_same_start(tmp_path, config):
    from loop_research.report import build_report
    save_stream(tmp_path, 'learn', config, scores=(.6, None, .8))
    save_stream(tmp_path, 'baseline', config, learning=False, scores=(.2, .4, .8))
    summary = build_report(tmp_path).read_text()
    assert '| learn | baseline | 2 / 3 | 0.7 | 0.5 | 0.2 |' in summary
    assert 'jointly scored' in summary
    assert 'fixture grader failure' in summary


@pytest.mark.parametrize('difference', ['task_order', 'base', 'judge', 'benchmark', 'config', 'metric'])
def test_report_refuses_incomparable_runs(tmp_path, config, difference):
    from loop_research.report import build_report
    save_stream(tmp_path, 'learn', config)
    other = save_stream(tmp_path, 'baseline', config, learning=False)
    if difference == 'task_order':
        other['task_ids'].reverse()
    elif difference == 'base':
        other['base_sha'] = 'different-base'
    elif difference == 'judge':
        other['judge'] = 'codex/different-judge'
    elif difference == 'benchmark':
        other['benchmark'] = 'wandr'
    elif difference == 'config':
        other['config']['models']['root'] = 'different-root'
    else:
        other['tasks'][0]['primary_metric'] = 'different-metric'
    write_json(tmp_path / 'reports/baseline/stream.json', other)
    assert 'No comparable learning and no-learning streams' in build_report(tmp_path).read_text()


def test_report_ignores_only_reporting_settings_for_comparisons(tmp_path, config):
    from loop_research.report import build_report
    save_stream(tmp_path, 'learn', config, scores=(.6,))
    config.stream.rolling_window = 1
    config.codex.log_full_text = True
    save_stream(tmp_path, 'baseline', config, learning=False, scores=(.2,))
    assert '| learn | baseline | 1 / 1 | 0.6 | 0.2 | 0.4 |' in build_report(tmp_path).read_text()


def test_report_empty_workspace_and_unscored_stream_are_explicit(tmp_path, config):
    from loop_research.report import build_report
    assert 'No stream reports are archived' in build_report(tmp_path).read_text()
    save_stream(tmp_path, 'failed', config, scores=(None,))
    summary = build_report(tmp_path).read_text()
    assert 'unavailable' in summary
    rows = list(csv.DictReader((tmp_path / 'reports/tasks.csv').open()))
    assert rows[0]['score'] == rows[0]['rolling_mean'] == ''
    assert rows[0]['rolling_scored'] == '0'


def test_curve_keeps_different_stream_metrics_on_separate_axes(tmp_path, config, monkeypatch):
    import matplotlib.pyplot as plt
    from loop_research.report import build_report
    first = save_stream(tmp_path, 'first', config, scores=(.2,))
    second = save_stream(tmp_path, 'second', config, scores=(.8,), benchmark='wandr')
    for manifest, metric in ((first, 'fixture_metric_one'), (second, 'fixture_metric_two')):
        manifest['tasks'][0]['primary_metric'] = metric
        write_json(tmp_path / 'reports' / manifest['run_id'] / 'stream.json', manifest)
    figures = []
    subplots = plt.subplots
    def observe(*args, **kwargs):
        figure, axes = subplots(*args, **kwargs)
        figures.append(figure)
        return figure, axes
    monkeypatch.setattr(plt, 'subplots', observe)
    build_report(tmp_path)
    axes = figures[0].axes
    assert len(axes) == 2
    assert {axis.get_ylabel() for axis in axes} == {'Rolling fixture_metric_one', 'Rolling fixture_metric_two'}
    assert all(len(axis.lines) == 1 for axis in axes)


def test_render_table_preserves_columns_values_and_clickable_citations():
    from loop_research.report import render_table
    output = {'rows': [{'entity': 'fixture', 'cells': {
        'name|kind': {'value': 'A|B\nnext', 'sources': ['https://example.org/a(b)'], 'quote': 'fixture'},
        'detail': {'value': 'cited detail', 'sources': ['https://example.org/a(b)', 'https://example.org/b'], 'quote': 'fixture'},
    }}]}
    table = render_table(output)
    assert '| name\\|kind | detail |' in table
    assert 'A\\|B<br>next' in table
    assert '[1](<https://example.org/a(b)>)' in table
    assert '[2](<https://example.org/b>)' in table
    assert render_table({'rows': []}) == 'No rows returned.'
