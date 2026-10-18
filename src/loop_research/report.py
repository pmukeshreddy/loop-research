"""Tables and plots derived only from archived stream and baseline reports."""
import copy
import csv
import io
import math
from pathlib import Path
from urllib.parse import quote, urlparse

from .archive import read_json
from .config import Config


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(text)
    temporary.replace(path)


def _text(value):
    if value is None:
        return 'unavailable'
    if isinstance(value, float):
        return format(value, '.8g')
    return str(value).replace('\\', '\\\\').replace('|', '\\|').replace('\n', '<br>')


def render_table(output):
    """Render the cited-row output contract without losing per-cell sources."""
    rows = output['rows']
    if not rows:
        return 'No rows returned.'
    columns = list(dict.fromkeys(name for row in rows for name in row['cells']))
    lines = ['| ' + ' | '.join(_text(column) for column in columns) + ' |',
             '| ' + ' | '.join('---' for _ in columns) + ' |']
    sources = {}
    for row in rows:
        values = []
        for column in columns:
            cell = row['cells'].get(column)
            if cell is None:
                values.append('')
                continue
            links = []
            for url in dict.fromkeys(cell['sources']):
                parsed = urlparse(url)
                if parsed.scheme not in ('http', 'https') or not parsed.netloc:
                    continue
                number = sources.setdefault(url, len(sources) + 1)
                links.append(f'[{number}](<{quote(url, safe=":/?#[]@!$&()*+,;=%")}>)')
            values.append(_text(cell['value']) + (' ' + ' '.join(links) if links else ''))
        lines.append('| ' + ' | '.join(values) + ' |')
    return '\n'.join(lines)


def _streams(root):
    streams = []
    for path in sorted([*(root / 'reports').glob('*/stream.json'),
                        *(root / 'reports').glob('*/baseline.json')]):
        manifest = read_json(path)
        config = Config.model_validate(manifest['config'])
        for field in ('as_of_date', 'task_digest'):
            if not isinstance(manifest.get(field), str) or not manifest[field].strip():
                raise ValueError(f'Invalid archived {field} for {manifest["run_id"]}')
        if manifest.get('judge') != config.judge_label:
            raise ValueError(f'Archived judge label does not match models.judge for {manifest["run_id"]}')
        rows = []
        tasks = sorted(manifest['tasks'], key=lambda row: row['index'])
        for position, task in enumerate(tasks):
            if task.get('judge') != config.judge_label:
                raise ValueError(f'Archived judge label does not match models.judge for '
                                 f'{manifest["run_id"]}/{task["task_id"]}')
            score = task.get('score')
            if type(score) not in (int, float) or not math.isfinite(score):
                raise ValueError(f'Invalid archived score for {manifest["run_id"]}/{task["task_id"]}')
            window = tasks[max(0, position + 1 - config.stream.rolling_window):position + 1]
            scores = [row['score'] for row in window]
            rows.append({
                'run_id': manifest['run_id'], 'benchmark': manifest['benchmark'],
                'mode': _mode(manifest),
                'learning': manifest['learning'], 'base_sha': manifest['base_sha'],
                **task, 'status': 'failed' if task['error'] else 'succeeded',
                'root_model': config.models.root, 'sub_model': config.models.sub,
                'refine_model': config.models.refine,
                'rolling_window': config.stream.rolling_window, 'rolling_scored': len(scores),
                'rolling_mean': sum(scores) / len(scores),
                'source': path.relative_to(root).as_posix(),
            })
        streams.append((manifest, rows, path))
    return streams


def _execution_config(config):
    result = copy.deepcopy(config)
    result.pop('stream')
    result['codex'].pop('log_full_text')
    return result


def _mode(manifest):
    return 'baseline' if manifest.get('mode') == 'baseline' else 'learning' if manifest['learning'] else 'no-learning'


def _comparison(learning, baseline):
    plain = _mode(baseline) == 'baseline'
    if plain:
        if _mode(learning) == 'baseline' or learning['benchmark'] != 'wandr':
            return None
    elif learning['learning'] is not True or baseline['learning'] is not False:
        return None
    keys = ('benchmark', 'task_ids', 'task_digest', 'as_of_date', 'judge')
    if any(learning[key] != baseline[key] for key in keys + (() if plain else ('base_sha',))):
        return None
    if _execution_config(learning['config']) != _execution_config(baseline['config']):
        return None
    left = {row['task_id']: row for row in learning['tasks']}
    right = {row['task_id']: row for row in baseline['tasks']}
    shared = [task_id for task_id in learning['task_ids'] if task_id in left and task_id in right]
    if any(left[key]['judge'] != learning['judge'] or right[key]['judge'] != baseline['judge'] for key in shared):
        return None
    if any(left[key]['primary_metric'] != right[key]['primary_metric'] for key in shared):
        return None
    paired = [(left[key]['score'], right[key]['score']) for key in shared]
    if not paired:
        return None
    learned = sum(value[0] for value in paired) / len(paired)
    unchanged = sum(value[1] for value in paired) / len(paired)
    return [learning['run_id'], baseline['run_id'], f'{len(paired)} / {len(learning["task_ids"])}',
            learned, unchanged, learned - unchanged]


def _curve(path, streams):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
    count = max(1, len(streams))
    columns = min(2, count)
    figure, grid = plt.subplots(math.ceil(count / columns), columns, squeeze=False,
                               figsize=(6 * columns, 4 * math.ceil(count / columns)))
    axes = list(grid.flat)
    for axis, (manifest, rows, _) in zip(axes, streams):
        mode = _mode(manifest)
        window = manifest['config']['stream']['rolling_window']
        models = manifest['config']['models']
        metrics = sorted({row['primary_metric'] for row in rows if row['primary_metric'] is not None})
        metric = ', '.join(metrics) if metrics else 'available score'
        axis.set(xlabel='Task position in stream', ylabel='Rolling ' + metric,
                 title=f'{manifest["run_id"]}\n{mode}; window {window}\n'
                       f'root: {models["root"]}; sub: {models["sub"]}\n'
                       f'refine: {models["refine"]}; judge: {manifest["judge"]}')
        axis.title.set_fontsize(8)
        axis.grid(alpha=.2)
        axis.xaxis.set_major_locator(MaxNLocator(integer=True))
        if rows and mode != 'baseline':
            axis.plot([row['index'] for row in rows],
                      [row['rolling_mean'] for row in rows],
                      marker='o', markersize=3)
        for reference, reference_rows, _ in streams:
            if _mode(reference) != 'baseline' or not reference_rows:
                continue
            paired = _comparison(manifest, reference)
            if mode == 'baseline' and reference['run_id'] == manifest['run_id']:
                mean = sum(row['score'] for row in reference_rows) / len(reference_rows)
            elif paired:
                mean = paired[4]
            else:
                continue
            axis.axhline(mean, linestyle='--', label='Plain Codex: ' + reference['run_id'])
            axis.legend(fontsize=6)
        if not rows:
            axis.text(.5, .5, 'No archived task scores', ha='center', va='center', transform=axis.transAxes)
    if not streams:
        axes[0].set_axis_off()
        axes[0].text(.5, .5, 'No archived task scores', ha='center', va='center', transform=axes[0].transAxes)
    for axis in axes[count:]:
        figure.delaxes(axis)
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def build_report(root):
    root = Path(root).resolve()
    directory = root / 'reports'
    directory.mkdir(parents=True, exist_ok=True)
    streams = _streams(root)
    fields = ['run_id', 'benchmark', 'mode', 'learning', 'base_sha', 'index', 'task_id', 'status', 'score',
              'primary_metric', 'judge', 'root_model', 'sub_model', 'refine_model',
              'error', 'harness_before', 'harness_after',
              'rolling_window', 'rolling_scored', 'rolling_mean', 'source']
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    for _, rows, _ in streams:
        for row in rows:
            writer.writerow({key: '' if row.get(key) is None else
                             format(row[key], '.8g') if isinstance(row[key], float) else row[key] for key in fields})
    _write(directory / 'tasks.csv', buffer.getvalue())
    _curve(directory / 'learning_curve.png', streams)
    lines = ['# Continual research report', '', 'Derived only from archived stream and baseline reports.', '',
             'Task details: [tasks.csv](tasks.csv). Every completed task has an official grader score.', '',
             'Rolling means include every completed task within the configured window, including '
             'official empty-submission scores for failed tasks. Failures retain their errors.', '',
             'WANDR primary: full-lineage soft F1 (`soft_f1_full`); official harness primary: '
             'full-lineage soft recall (`soft_recall_full`). Fetch: `wandr-browser`; judge: `codex/<model>`.', '',
             '## Streams', '']
    if not streams:
        lines.append('No stream reports are archived.')
    else:
        lines += ['| run | benchmark | mode | as-of date | tasks recorded / planned | scored | failed | metric | mean score | judge | root model | sub model | refine model | base | source |',
                  '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
        for manifest, rows, path in streams:
            scores = [row['score'] for row in rows]
            models = manifest['config']['models']
            values = [manifest['run_id'], manifest['benchmark'], _mode(manifest),
                      manifest['as_of_date'],
                      f'{len(rows)} / {len(manifest["task_ids"])}', len(scores), sum(row['status'] == 'failed' for row in rows),
                      ', '.join(sorted({row['primary_metric'] for row in rows if row['primary_metric'] is not None})) or None,
                      sum(scores) / len(scores) if scores else None, manifest['judge'],
                      models['root'], models['sub'], models['refine'], manifest['base_sha']]
            link = path.relative_to(directory).as_posix()
            lines.append('| ' + ' | '.join(_text(value) for value in values) + f' | [source]({link}) |')
    lines += ['', '![Rolling stream scores](learning_curve.png)', '', '## Failed tasks', '']
    failed = [row for _, rows, _ in streams for row in rows if row['status'] == 'failed']
    if failed:
        lines += ['| run | task | status | error | source |', '| --- | --- | --- | --- | --- |']
        for row in failed:
            link = Path(row['source']).relative_to('reports').as_posix()
            lines.append('| ' + ' | '.join(_text(row[key]) for key in ('run_id', 'task_id', 'status', 'error')) + f' | [source]({link}) |')
    else:
        lines.append('No failed task records.')
    interrupted = [(manifest, rows, path) for manifest, rows, path in streams
                   if manifest.get('status') == 'interrupted' or manifest.get('error')]
    lines += ['', '## Interrupted streams', '', f'Interrupted streams: {len(interrupted)}.', '']
    if interrupted:
        lines += ['| run | phase | active task | tasks pending | error | source |',
                  '| --- | --- | --- | --- | --- | --- |']
        for manifest, rows, path in interrupted:
            pending = len(set(manifest['task_ids']) - {row['task_id'] for row in rows})
            values = [manifest['run_id'], manifest.get('phase'), manifest.get('active_task_id'),
                      pending, manifest.get('error')]
            link = path.relative_to(directory).as_posix()
            lines.append('| ' + ' | '.join(_text(value) for value in values) + f' | [source]({link}) |')
    lines += ['', '## Learning comparisons', '',
              'Comparisons require the same benchmark, ordered tasks and task content, resolved as-of date, '
              'starting harness, judge and execution settings. '
              'All jointly completed tasks contribute, including scored failures; pending interrupted tasks remain visible above. '
              'Logging and rolling-window settings do not affect eligibility.', '']
    comparisons = [_comparison(left, right) for left, _, _ in streams for right, _, _ in streams
                   if _mode(right) != 'baseline']
    comparisons = [row for row in comparisons if row is not None]
    if comparisons:
        lines += ['| learning run | no-learning run | jointly scored / planned | learning mean | no-learning mean | difference |',
                  '| --- | --- | --- | --- | --- | --- |']
        lines.extend('| ' + ' | '.join(_text(value) for value in row) + ' |' for row in comparisons)
    else:
        lines.append('No comparable learning and no-learning streams with jointly scored tasks are archived.')
    lines += ['', '## Plain Codex baseline comparisons', '',
              'Each learning or no-learning stream is paired with the baseline on jointly completed task IDs, '
              'requiring the same ordered task list, content, date, judge, metric and execution settings. '
              'The baseline is independent of the starting harness. Dashed plot lines show its paired mean, '
              'including failures.', '']
    pairs = [_comparison(left, right) for left, _, _ in streams for right, _, _ in streams
             if _mode(right) == 'baseline']
    pairs = [pair for pair in pairs if pair is not None]
    if pairs:
        lines += ['| stream run | baseline run | jointly scored / planned | stream mean | baseline mean | difference |',
                  '| --- | --- | --- | --- | --- | --- |']
        lines.extend('| ' + ' | '.join(_text(value) for value in pair) + ' |' for pair in pairs)
    else:
        lines.append('No comparable WANDR streams and plain baselines with jointly scored tasks are archived.')
    path = directory / 'summary.md'
    _write(path, '\n'.join(lines) + '\n')
    return path
