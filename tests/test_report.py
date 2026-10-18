"""Reporting fixtures are hand-written, never benchmark results."""
import csv
import json
from pathlib import Path

import pytest

from loop_research.archive import write_json


def save_stream(root, run_id, config, *, learning=True, scores=(.2, 0, .8), failed=(2,), **changes):
    config = config.model_copy(deep=True)
    config.models.judge = 'fixture-judge'
    tasks = [{
        'index': index, 'task_id': f'fixture-{index}', 'score': score,
        'primary_metric': 'fixture_metric' if score is not None else None, 'judge': 'codex/fixture-judge',
        'error': 'fixture grader failure' if index in failed else None,
        'status': 'failed' if index in failed else 'succeeded',
        'harness_before': f'before-{index}', 'harness_after': f'after-{index}',
    } for index, score in enumerate(scores, 1)]
    manifest = {
        'run_id': run_id, 'benchmark': 'widesearch', 'learning': learning,
        'base_sha': 'fixture-base', 'task_ids': [row['task_id'] for row in tasks],
        'as_of_date': '2026-10-18', 'task_digest': 'fixture-task-content-v1',
        'config': config.model_dump(), 'judge': 'codex/fixture-judge', 'tasks': tasks,
    }
    manifest.update(changes)
    write_json(root / 'reports' / run_id / 'stream.json', manifest)
    return manifest


def test_report_includes_official_scores_for_failed_tasks_in_rolling_means(tmp_path, config):
    from loop_research.report import build_report
    config.stream.rolling_window = 2
    save_stream(tmp_path, 'fixture-learning', config)
    result = build_report(tmp_path)
    assert result == tmp_path / 'reports/summary.md'
    rows = list(csv.DictReader((tmp_path / 'reports/tasks.csv').open()))
    assert [row['score'] for row in rows] == ['0.2', '0', '0.8']
    assert [row['rolling_mean'] for row in rows] == ['0.2', '0.1', '0.4']
    assert [row['rolling_scored'] for row in rows] == ['1', '2', '2']
    assert rows[1]['status'] == 'failed' and rows[1]['error'] == 'fixture grader failure'
    assert rows[1]['source'] == 'reports/fixture-learning/stream.json'
    summary = result.read_text()
    assert 'fixture grader failure' in summary
    assert 'Failures are excluded' not in summary
    assert 'official empty-submission scores' in summary
    assert 'codex/fixture-judge' in summary
    assert 'fixture-learning/stream.json' in summary
    assert 'No comparable learning and no-learning streams' in summary
    assert (tmp_path / 'reports/learning_curve.png').read_bytes().startswith(b'\x89PNG\r\n\x1a\n')


def test_report_includes_scored_failures_in_paired_comparisons(tmp_path, config):
    from loop_research.report import build_report
    save_stream(tmp_path, 'learn', config, scores=(.6, .1, .8))
    save_stream(tmp_path, 'baseline', config, learning=False, scores=(.2, .4, .8))
    summary = build_report(tmp_path).read_text()
    assert '| learn | baseline | 3 / 3 | 0.5 | 0.46666667 | 0.033333333 |' in summary
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
        other['config']['models']['judge'] = 'different-judge'
        for task in other['tasks']:
            task['judge'] = 'codex/different-judge'
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


def test_report_empty_workspace_and_interrupted_stream_are_explicit(tmp_path, config):
    from loop_research.report import build_report
    assert 'No stream reports are archived' in build_report(tmp_path).read_text()
    save_stream(tmp_path, 'interrupted', config, scores=(), task_ids=['fixture-1', 'fixture-2'],
                status='interrupted', phase='empty_grading', active_task_id='fixture-1',
                error='fixture official empty grader failed')
    summary = build_report(tmp_path).read_text()
    assert 'Interrupted streams: 1.' in summary
    assert '| interrupted | empty_grading | fixture-1 | 2 | fixture official empty grader failed |' in summary
    assert list(csv.DictReader((tmp_path / 'reports/tasks.csv').open())) == []


@pytest.mark.parametrize('score', [None, float('nan'), float('inf'), -float('inf'), True, '0.5'])
def test_report_refuses_completed_rows_without_finite_numeric_scores(tmp_path, config, score):
    from loop_research.report import build_report
    manifest = save_stream(tmp_path, 'incomplete', config, scores=(.2,))
    manifest['tasks'][0]['score'] = score
    (tmp_path / 'reports/incomplete/stream.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='Invalid archived score.*incomplete/fixture-1'):
        build_report(tmp_path)
    assert not (tmp_path / 'reports/tasks.csv').exists()


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


@pytest.mark.parametrize('scope', ['manifest', 'task'])
@pytest.mark.parametrize('label', ['codex/default', 'codex/incorrect-model'])
def test_report_refuses_judge_labels_inconsistent_with_config(tmp_path, config, scope, label):
    from loop_research.report import build_report
    manifest = save_stream(tmp_path, 'mislabelled', config, scores=(.2,))
    record = manifest if scope == 'manifest' else manifest['tasks'][0]
    record['judge'] = label
    write_json(tmp_path / 'reports/mislabelled/stream.json', manifest)
    with pytest.raises(ValueError, match='Archived judge label.*models.judge.*mislabelled'):
        build_report(tmp_path)
    assert not (tmp_path / 'reports/tasks.csv').exists()


def test_report_identifies_all_model_roles_in_csv_summary_and_plot(tmp_path, config, monkeypatch):
    import matplotlib.pyplot as plt
    from loop_research.report import build_report
    config.models.root = 'fixture-root-model'
    config.models.sub = 'fixture-sub-model'
    config.models.refine = 'fixture-refine-model'
    save_stream(tmp_path, 'models', config, scores=(.2,))
    figures = []
    subplots = plt.subplots
    def observe(*args, **kwargs):
        figure, axes = subplots(*args, **kwargs)
        figures.append(figure)
        return figure, axes
    monkeypatch.setattr(plt, 'subplots', observe)
    summary = build_report(tmp_path).read_text()
    row = next(csv.DictReader((tmp_path / 'reports/tasks.csv').open()))
    assert row['root_model'] == 'fixture-root-model'
    assert row['sub_model'] == 'fixture-sub-model'
    assert row['refine_model'] == 'fixture-refine-model'
    assert row['judge'] == 'codex/fixture-judge'
    for model in ('fixture-root-model', 'fixture-sub-model', 'fixture-refine-model', 'codex/fixture-judge'):
        assert model in summary
        assert model in figures[0].axes[0].get_title()


@pytest.mark.parametrize('difference', ['as_of_date', 'task_digest'])
def test_report_requires_matching_resolved_date_and_task_content(tmp_path, config, difference):
    from loop_research.report import build_report
    config.agent.as_of = 'today'
    save_stream(tmp_path, 'learn', config, scores=(.6,))
    other = save_stream(tmp_path, 'baseline', config, learning=False, scores=(.2,))
    other[difference] = '2026-10-19' if difference == 'as_of_date' else 'fixture-task-content-v2'
    write_json(tmp_path / 'reports/baseline/stream.json', other)
    summary = build_report(tmp_path).read_text()
    assert 'No comparable learning and no-learning streams' in summary
    assert '| learn | baseline |' not in summary


@pytest.mark.parametrize('field', ['as_of_date', 'task_digest'])
@pytest.mark.parametrize('value', ['missing', None, ''])
def test_report_refuses_missing_comparison_provenance(tmp_path, config, field, value):
    from loop_research.report import build_report
    manifest = save_stream(tmp_path, 'incomplete-provenance', config, scores=(.2,))
    if value == 'missing':
        del manifest[field]
    else:
        manifest[field] = value
    write_json(tmp_path / 'reports/incomplete-provenance/stream.json', manifest)
    with pytest.raises(ValueError, match=f'Invalid archived {field}.*incomplete-provenance'):
        build_report(tmp_path)
    assert not (tmp_path / 'reports/tasks.csv').exists()


def test_report_labels_resolved_as_of_date(tmp_path, config):
    from loop_research.report import build_report
    save_stream(tmp_path, 'dated', config, scores=(.2,), as_of_date='2026-09-01')
    summary = build_report(tmp_path).read_text()
    assert '| as-of date |' in summary
    assert '| 2026-09-01 |' in summary


def save_baseline(root, config):
    manifest = save_stream(root, 'plain', config, learning=None, scores=(.2, 0, .4),
                           benchmark='wandr', mode='baseline', base_sha='independent-harness')
    for task in manifest['tasks']:
        task['primary_metric'] = 'soft_f1_full'
    (root / 'reports/plain/stream.json').unlink()
    write_json(root / 'reports/plain/baseline.json', manifest)
    return manifest


def test_baseline_reports_pair_both_modes_and_plot_reference_lines(tmp_path, config, monkeypatch):
    import matplotlib.pyplot as plt
    from loop_research.report import build_report
    for name, learning in [('learn', True), ('fixed', False)]:
        manifest = save_stream(tmp_path, name, config, learning=learning,
                               benchmark='wandr', scores=(.6, .1, .8))
        for task in manifest['tasks']:
            task['primary_metric'] = 'soft_f1_full'
        write_json(tmp_path / 'reports' / name / 'stream.json', manifest)
    save_baseline(tmp_path, config)
    figures = []
    original = plt.subplots
    def observe(*args, **kwargs):
        figure, axes = original(*args, **kwargs)
        figures.append(figure)
        return figure, axes
    monkeypatch.setattr(plt, 'subplots', observe)
    summary = build_report(tmp_path).read_text()
    assert '| plain | wandr | baseline |' in summary
    assert '| learn | plain | 3 / 3 | 0.5 | 0.2 | 0.3 |' in summary
    assert '| fixed | plain | 3 / 3 | 0.5 | 0.2 | 0.3 |' in summary
    assert 'full-lineage soft F1' in summary and 'soft_recall_full' in summary
    rows = list(csv.DictReader((tmp_path / 'reports/tasks.csv').open()))
    assert {row['mode'] for row in rows} == {'baseline', 'learning', 'no-learning'}
    assert sum(row['status'] == 'failed' for row in rows if row['mode'] == 'baseline') == 1
    for axis in figures[0].axes:
        reference = [line for line in axis.lines if line.get_label().startswith('Plain Codex')]
        assert len(reference) == 1
        assert list(reference[0].get_ydata()) == pytest.approx([.2, .2])


@pytest.mark.parametrize('difference', ['task_ids', 'task_digest', 'as_of_date', 'config', 'metric'])
def test_baseline_pairs_only_matching_tasks_settings_and_metrics(tmp_path, config, difference):
    from loop_research.report import build_report
    manifest = save_stream(tmp_path, 'learn', config, benchmark='wandr', scores=(.6, .1, .8))
    for task in manifest['tasks']:
        task['primary_metric'] = 'soft_f1_full'
    write_json(tmp_path / 'reports/learn/stream.json', manifest)
    other = save_baseline(tmp_path, config)
    if difference == 'config':
        other['config']['agent']['task_timeout_s'] += 1
    elif difference == 'metric':
        other['tasks'][0]['primary_metric'] = 'soft_recall_full'
    elif difference == 'task_ids':
        other['task_ids'].reverse()
    else:
        other[difference] = 'changed'
    write_json(tmp_path / 'reports/plain/baseline.json', other)
    summary = build_report(tmp_path).read_text()
    assert '| learn | plain |' not in summary
