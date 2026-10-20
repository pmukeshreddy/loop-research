"""Render the completed round-two evidence and parent-authored interpretations.

Usage: .venv/bin/python runs/round2/render.py [--input-dir DIR] [--output FILE]

This script reads existing audits; it never runs an audit, research, or a model.
Required interpretation.json fields: root and self_improvement verdict objects,
and checks with exactly IDs 1..10. Each verdict has verdict, explanation, evidence
([{label, path}]). Optional fields: source_fixes ([{commit, description, tests:
[{command, result, evidence}]}]), runs ({LABEL: {explanation, evidence}}), transfer
({explanation, evidence}), and limitations ([text]). Evidence paths may end :LINE.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))
from loop_research.codex_backend import INSTRUCTION
from loop_research.report import render_table

REQUIRED = ('A', 'B1', 'B0', 'B1-frozen')
CHECK_NAMES = ('1a', '1b', '1c', '2a', '2b', '2c', '2d', '3', '4a', '4b')


def read(path):
    return json.loads(Path(path).read_text())


def rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def narrative(path):
    """Make local links portable when this narrative is embedded and appended."""
    path = Path(path)
    fence = None
    result = []
    for line in path.read_text().splitlines(keepends=True):
        marker = re.match(r'^\s*(`{3,}|~{3,})', line)
        if marker:
            token = marker[1]
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
        elif fence is None:
            def resolve(match):
                target = match[1].strip('<>')
                if target.startswith(('/', '#')) or re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', target):
                    return match[0]
                return '](<' + str((path.parent / target).resolve()) + '>)'
            line = re.sub(r'\]\(([^)\n]+)\)', resolve, line)
        result.append(line)
    return ''.join(result)


def sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()


def link(label, path, line=None):
    target = str(path) + (f':{line}' if line is not None else '')
    return f'[{label}](<{target}>)'


def text(value):
    if value is None:
        return 'unavailable'
    if isinstance(value, float):
        return f'{value:,.3f}'
    return str(value).replace('|', '\\|').replace('\n', '<br>')


def table(headers, values):
    return ['| ' + ' | '.join(map(text, headers)) + ' |',
            '| ' + ' | '.join('---' for _ in headers) + ' |',
            *['| ' + ' | '.join(map(text, row)) + ' |' for row in values], '']


def fenced(value, language='json'):
    value = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    longest = max((len(match[0]) for match in re.finditer(r'`+', value)), default=0)
    fence = '`' * max(3, longest + 1)
    return [fence + language, value, fence, '']


def evidence(items):
    return '; '.join(link(item['label'], item['path']) for item in items)


def interpretation_lines(value, title=None):
    result = []
    if title:
        result += [f'**{title}: {value["verdict"]}.** {value["explanation"]}', '']
    else:
        result += [value['explanation'], '']
    if value.get('evidence'):
        result += [evidence(value['evidence']), '']
    return result


def git(*args, harness_path=None):
    # All callers use read-only Git commands; the live harness is never checked out or changed.
    return subprocess.run(['git', '-C', str(harness_path or ROOT / 'harness'), *args],
                          check=True, capture_output=True, text=True).stdout


def offset(timestamp, boundary):
    if not timestamp or not boundary:
        return None
    return (datetime.fromisoformat(timestamp) - datetime.fromisoformat(boundary)).total_seconds()


def trace_link(audit, label, line):
    return link(label, Path(audit['task_path']).parent / 'trace.jsonl', line)


def validate_interpretation(value):
    for key in ('root', 'self_improvement'):
        verdict = value.get(key, {})
        if not verdict.get('verdict') or not verdict.get('explanation'):
            raise ValueError(f'Parent-authored {key} verdict and explanation are required')
    checks = value.get('checks', [])
    if len(checks) != 10 or {item.get('id') for item in checks} != set(range(1, 11)):
        raise ValueError('Parent-authored checks must contain exactly IDs 1..10')
    for check in checks:
        if not all(check.get(key) for key in ('check', 'verdict', 'explanation')):
            raise ValueError('Every check requires its name, verdict and explanation')


def verify_source_files(audit):
    for source in audit['source_files']:
        path = Path(source['path'])
        if not path.exists() or sha(path.read_bytes()) != source['sha256']:
            raise ValueError(f'Audited source changed or disappeared: {path}')


def run_details(label, audit, metrics, interpretation):
    task = Path(audit['task_path'])
    run = task.parent
    result = [f'## {label}: execution and evidence', '',
              f'Archive: {link(audit["run_id"], run / "research.json")}; '
              f'{link("full trajectory", task / "trajectory.jsonl")}; '
              f'{link("readable trace", run / "trace.log")}; '
              f'{link("run summary", run / "trace_summary.md")}.', '']
    if label in interpretation.get('runs', {}):
        result += interpretation_lines(interpretation['runs'][label])
    result += ['### Root and child RLMs', '']
    result += table(['RLM', 'Parent', 'Depth', 'Iterations', 'REPL blocks', 'Termination', 'Evidence'], [
        [r['rlm_id'], r.get('parent_rlm_id'), r['depth'], r['iterations'], r['repl_blocks'],
         r['termination'], link('completion', r['trace_link'])] for r in audit['rlms']])
    result += table(['RLM', 'Depth', 'Iteration', 'Backend input chars', 'Call', 'Evidence'], [
        [r['rlm_id'], r['depth'], r['iteration'], r['backend_chars'], r['call_id'],
         link('iteration', r['trace_link'])] for r in audit['iterations']])
    if not any(r['depth'] > 0 for r in audit['rlms']):
        result += ['No child RLM completion is recorded in this run.', '']
    if label == 'explicit':
        result += ['This arm explicitly requested the mechanism; it is not evidence of spontaneous delegation or refinement.', '']
    prompt = audit['largest_prompt']
    result += ['### Largest root input: disjoint parts', '',
               f'Total **{prompt["total"]:,} characters**; SHA-256 `{prompt["sha256"]}`; '
               f'iteration {prompt["iteration"]}; {link("backend call", prompt["trace_link"])}.', '']
    result += table(['Part', 'Characters'], list(prompt['parts'].items()))
    result += [prompt['partition_policy'], '',
               f'Archived initial input: {link("root input", prompt["initial_input_path"])} '
               f'({prompt["initial_input_chars"]:,} chars); current harness payload: '
               f'{prompt["current_harness_chars"]:,} chars.', '']
    overlap = audit['overlap']
    result += ['### Unchanged 50-character overlap criterion', '',
               f'Exact, case- and whitespace-sensitive {overlap["ngram_chars"]}-grams cover '
               f'**{overlap["covered_chars"]:,} / {overlap["total_chars"]:,}** returned-text characters '
               f'({text(overlap["fraction"] * 100 if overlap["fraction"] is not None else None)}%). '
               f'{overlap["fully_present_texts"]} fetched texts occur in full in a root input.', '',
               overlap['limitation'], '',
               f'Returned fetched-text / largest-root-input ratio: '
               f'**{audit["fetched_text_to_largest_root_ratio"]:.6f}×**. '
               'This is not a raw-page / root-context ratio. Raw-page size remains unavailable wherever telemetry reports null.', '']
    result += table(['URL / text index', 'Returned chars', 'Covered chars', 'Full text in root', 'First full-root evidence'], [
        [f'{item["url"]} / {item["text_index"]}', item['chars'], item['covered_chars'], item['full_text_in_root'],
         trace_link(audit, 'root call', item['first_full_root_trace_line'])
         if item.get('first_full_root_trace_line') else 'none'] for item in overlap['texts']])
    result += ['### Every fetch: returned size, raw availability and opened URLs', '',
               'Returned characters measure the tool response, including a failure sentinel where recorded. '
               'Only evidence-eligible successful returns count as fetched evidence. Action URLs and result URLs '
               'are reported separately. Action URLs below are open_page requests; result URLs can also include '
               'search hits when that backend call performed an extra search, so a result URL alone does not '
               'establish that a page opened. The linked complete events retain each action type. '
               'Neither event metadata nor a “Total lines” snippet is a raw-page size.', '']
    fetch_rows = []
    for fetch in audit['fetches']:
        attempts = []
        for attempt in fetch['attempts']:
            actions = '<br>'.join(attempt.get('requested_action_urls', [])) or 'none recorded'
            returned = '<br>'.join(attempt.get('result_urls', [])) or 'none recorded'
            traces = [link('call record', attempt['call_link'])] if attempt.get('call_link') else []
            if attempt.get('trace_link'):
                traces.append(link('exec trace', attempt['trace_link']))
            attempts.append(f'`{attempt["call_id"]}`: actions: {actions}; results: {returned}; ' + ', '.join(traces))
        tool_links = ', '.join(trace_link(audit, str(n), n) for n in fetch['tool_trace_lines'])
        fetch_rows.append([fetch['id'], fetch['url'], fetch.get('focus', ''),
                           f'{fetch["source"]}; owner {fetch["evidence_owner_id"]}', fetch['status'],
                           fetch['returned_chars'], fetch['evidence_eligible'], fetch.get('raw_page_chars'),
                           fetch.get('raw_page_chars_reason', ''), '<br><br>'.join(attempts) or 'no backend attempt', tool_links])
    result += table(['Request', 'URL', 'Focus', 'Source / owner', 'Status', 'Returned chars', 'Evidence eligible',
                     'Raw-page chars', 'Raw-size reason', 'Backend attempts and URLs', 'Tool trace lines'], fetch_rows)
    result += ['### Sub-model inputs', '',
               f'{audit["subcall_count"]} sub calls; **{audit["subcall_input_chars"]:,} input chars** '
               f'({audit["subcall_prompt_chars"]:,} prompt + {audit["subcall_schema_chars"]:,} schema-file chars); '
               f'**{audit["subcall_backend_chars"]:,} total backend input chars** also includes backend instructions. '
               'Schema characters use the exact JSON serialization sent through --output-schema, separately verified by its archived hash. '
               'Child RLM turns are identified separately from ordinary sub-model queries.', '']
    result += table(['Call', 'Prompt chars', 'Schema chars', 'Total input chars', 'Total backend chars', 'Child RLM turn', 'Prompt SHA-256', 'Schema SHA-256', 'Evidence'], [
        [item['call_id'], item['prompt_input_chars'], item['schema_input_chars'], item['input_chars'], item['backend_chars'], item['is_child_rlm_turn'],
         item['input_sha256'], item['schema_sha256'], link('sub call', item['trace_link'])] for item in audit['subcalls']])
    result += ['### Fetch-variable code excerpts', '']
    for index, excerpt in enumerate(audit['excerpts'], 1):
        result += [f'Excerpt {index}: RLM `{excerpt["rlm_id"]}`, depth {excerpt["depth"]}, '
                   f'iteration {excerpt["iteration"]}; {link("complete code", excerpt["trajectory_link"])}; '
                   f'{link("REPL trace", excerpt["code_trace_link"])}. '
                   f'The complete block returned {excerpt["stdout_chars"]:,} stdout chars.', '']
        result += fenced(excerpt['excerpt'], 'python')
    if audit['excerpt_shortfall']:
        result += [f'Only {audit["excerpt_count"]} qualifying page-variable blocks were verified; '
                   f'{audit["excerpt_shortfall"]} requested excerpts are unavailable.', '']
    result += ['### Parallel tool batches', '',
               'The table reports measured batch and inclusive child durations. These timings do not alone establish useful delegation or better research.', '']
    result += table(['Tool', 'Items', 'Batch seconds', 'Summed child seconds', 'Trace start → end'], [
        [batch['tool'], batch['items'], batch['duration_s'], batch['sum_inner_duration_s'],
         trace_link(audit, str(batch['start_line']), batch['start_line']) + ' → ' +
         trace_link(audit, str(batch['end_line']), batch['end_line'])] for batch in metrics['batches']])
    result += ['### Self-check issues and signals', '',
               f'Issues: **{len(metrics["issues"])}**; signals: **{len(metrics["signals"])}**. '
               f'{link("Complete self-check", task / "self_check.json")}. '
               'These checks measure recorded evidence and coverage, not independent factual correctness.', '']
    result += fenced({'issues_by_type': metrics['issues_by_type'], 'signals_by_type': metrics['signals_by_type'],
                      'issues': metrics['issues'], 'signals': metrics['signals']})
    result += ['Recorded constraint-verdict argument types (observations, not semantic verdict validation):', '']
    result += table(['Argument type', 'Calls'], sorted(Counter(item['verdict_type'] for item in audit['constraints']).items()))
    result += ['### Recorded errors and recovery', '',
               f'All recorded error events: **{len(metrics["errors"])}**. '
               'Recorded error events remain counted separately from final self-check issues; '
               'the accompanying review describes what failed and what subsequently recovered.', '']
    for error in metrics['errors']:
        result += [trace_link(audit, f'{error["component"]}: {error["event"]}', error['line']), '']
        result += fenced(error)
    return result


def refinement_details(label, audit):
    task = Path(audit['task_path'])
    jobs = [(path, read(path)) for path in (task / 'refine_requests').glob('*/*.json')]
    timestamps = {event['details']['job_id']: event['timestamp'] for event in reversed(audit['refine'])
                  if event['details'].get('job_id')}
    jobs.sort(key=lambda pair: (timestamps.get(pair[1]['job_id'], ''), pair[1]['job_id']))
    result = [f'## {label}: every durable refinement planning job', '',
              f'{len(jobs)} planning snapshots. Each link preserves its exact input, schema, candidate inventory, '
              'raw response, proposal and edit identities. Failed retries and stale replans remain separate snapshots.', '']
    calls = rows(task / 'codex_calls.jsonl')
    for path, job in jobs:
        result += [f'### Request `{job["request_id"]}`, job `{job["job_id"]}`', '',
                   f'Status: **{job["status"]}**; focus: {json.dumps(job.get("focus"), ensure_ascii=False)}; '
                   f'{link("full job snapshot and input", path)}.', '']
        prompt = job.get('planner_prompt')
        if job.get('planner_transport', {}).get('kind') == 'repl-context-v1':
            directory = task / 'refine_planners' / job['job_id']
            result += ['Transport: **complete snapshot through isolated REPL**. The saved `planner_prompt` '
                'is the prospective legacy representation, **not dispatched** as a model input. '
                f'{link("Complete logical context", directory / "context.json")}; '
                f'{link("strict schema", directory / "schema.json")}; '
                f'{link("full model inputs and action journal", directory / "actions.jsonl")}; '
                f'{link("transport manifest", directory / "manifest.json")}.', '']
            if (directory / 'actions.jsonl').exists():
                actions = rows(directory / 'actions.jsonl')
                attempted = {action['call_id']: action for action in actions
                    if action['event'] == 'model.attempt' and action['status'] == 'dispatched'}
                starts = {action['action_id']: action for action in actions if action['event'] == 'model.start'}
                by_id = {call['call_id']: call for call in calls}
                matching = []
                for identity, action in attempted.items():
                    call = by_id.get(identity)
                    receipt = task / 'codex_attempts' / (identity + '.json')
                    if call is None and not receipt.exists():
                        raise ValueError('Refinement context attempt lacks durable dispatch evidence: ' + identity)
                    current = dict(call if call is not None else read(receipt))
                    actual_input = starts[action['action_id']]['backend_prompt']
                    if (current['purpose'] != 'refine' or len(actual_input) != current['prompt_chars'] or
                            sha(actual_input) != current['prompt_sha256'] or
                            (call is not None and call.get('prompt') != actual_input)):
                        raise ValueError('Refinement context attempt input does not match its archive')
                    if call is None:
                        current['error'] = 'completion unavailable (dispatched; outcome and usage unavailable)'
                    matching.append(current)
                result += table(['Actual model call', 'Attempt', 'Backend input characters', 'Backend input SHA-256', 'Error'], [
                    [call['call_id'], call['attempt'], call['prompt_chars'], call['prompt_sha256'], call.get('error')]
                    for call in matching])
                result += ['Model retries remain separate attempts. Planner and submodel calls above all use the '
                    'refinement role; these are separate from research root/sub measurements. The complete original '
                    'supplied observation remains accessible through the snapshot capability. No full-raw-trajectory '
                    'losslessness claim is implied.', '']
            else:
                result += ['No action journal was recorded; no actual planner dispatch is inferred.', '']
        elif prompt is not None:
            backend = INSTRUCTION + prompt
            matching = [call for call in calls if call['purpose'] == 'refine' and call['prompt_sha256'] == sha(backend)]
            result += table(['Input measurement', 'Value'], [
                ['Exact planner prompt characters', len(prompt)], ['Exact planner prompt UTF-8 bytes', len(prompt.encode())],
                ['Exact planner prompt SHA-256', sha(prompt)], ['Backend input characters', len(backend)],
                ['Backend input SHA-256', sha(backend)],
                ['Matching archived backend calls', ', '.join(call['call_id'] for call in matching) or 'none']])
            for call in matching:
                if call['prompt_chars'] != len(backend):
                    raise ValueError('Refinement prompt size disagrees with archived backend call')
            representation = job.get('planner_representation')
            if representation is not None:
                result += ['Lossless serialization measurements (the logical payload includes the visible evidence index):', '']
                result += table(['Representation measurement', 'Value'], list(representation.items()))
                result += [f'Visible valid evidence anchors: **{len(job["evidence_index"])}**. '
                    'Every original logical field and string occurrence remains reconstructable. '
                    'Original observations and the exact transmitted representation are in the linked job archive. '
                    'This preserves the pre-existing observation projection; it does not make that inherited projection lossless.', '']
        else:
            result += ['No exact planner prompt was archived for this snapshot; it is not reconstructed as observed input.', '']
        result += ['Full presented candidate inventory:', ''] + fenced(job.get('candidate_inventory', []))
        proposal = job.get('proposal')
        if proposal is not None:
            result += ['Every decision, reason, additional candidate and proposed edit follows without selection:', '']
            result += fenced(proposal)
        else:
            result += ['No validated proposal was recorded.', '']
            if job.get('response_text') is not None:
                result += ['Raw response:', ''] + fenced(job['response_text'], 'text')
        if job.get('error'):
            result += ['Archived error:', ''] + fenced(job['error'], 'text')
    return result


def edit_timing(label, audit, metrics, harness_path=None):
    run_end = (audit.get('run_end') or {}).get('timestamp')
    worker_end = (audit.get('worker_end') or {}).get('timestamp')
    result = [f'### {label}: edit commits relative to worker and run completion', '',
              f'Worker end: `{worker_end}`. Research run end: `{run_end}`. '
              'Negative offsets precede the boundary; nonnegative offsets follow it.', '']
    lifecycle = {'scheduled', 'planning.start', 'planning.end', 'proposal', 'apply.start', 'apply.end',
                 'edit_applied', 'rollback.start', 'rollback.end'}
    result += table(['Refine event', 'Trace timestamp', 'Seconds vs worker end', 'Seconds vs run end',
                     'Request', 'Job', 'Focus', 'Evidence'], [
        [event['event'], event['timestamp'], offset(event['timestamp'], worker_end),
         offset(event['timestamp'], run_end), event['details'].get('request_id'),
         event['details'].get('job_id'), event['details'].get('focus'),
         trace_link(audit, 'refine event', event['_line'])]
        for event in audit['refine'] if event['event'] in lifecycle])
    events = [event for event in audit['refine']
              if event['event'] in {'edit_applied', 'rollback.end'} and event['details'].get('commit')]
    events += [event for event in metrics['harness_edits']
               if not event['details'].get('error') and event['details'].get('head_after')
               and event['details']['head_after'] != event['details'].get('head_before')]
    values = []
    for event in events:
        details = event['details']
        commit = details.get('commit', details.get('head_after'))
        committed = git('show', '-s', '--format=%cI', commit, harness_path=harness_path).strip()
        values.append([commit, committed, event['timestamp'], offset(event['timestamp'], worker_end),
                       offset(event['timestamp'], run_end), details.get('request_id'), details.get('job_id'),
                       details.get('operation_id'), trace_link(audit, 'edit', event.get('_line', event.get('line')))])
    result += table(['Commit', 'Git commit timestamp', 'Trace timestamp', 'Seconds vs worker end', 'Seconds vs run end',
                     'Request', 'Job', 'Operation', 'Evidence'], values)
    result += ['Direct harness CRUD end events (including any failed events) are retained separately:', '']
    result += fenced(metrics['harness_edits'])
    recorded = {event['details'].get('commit', event['details'].get('head_after')) for event in events}
    provenance = metrics['manifest']
    all_edits = git('log', '--reverse', '--format=%H%x09%cI%x09%s',
                    f'{provenance["base_sha"]}..{provenance["harness_head"]}', '--', 'edits/', harness_path=harness_path).splitlines()
    result += ['Git cross-check of every edit commit in this run’s harness range; Git timestamps have coarser precision than trace events:', '']
    result += table(['Commit', 'Git timestamp', 'Seconds vs worker end (Git time)', 'Seconds vs run end (Git time)',
                     'Matched edit trace', 'Subject'], [
        [commit, timestamp, offset(timestamp, worker_end), offset(timestamp, run_end), commit in recorded, subject]
        for commit, timestamp, subject in (line.split('\t', 2) for line in all_edits)])
    return result


def harness_comparison(manifest, audits, metrics, interpretation, output_dir):
    base, after = manifest['BASE'], manifest['POST_A']
    before = json.loads(git('show', f'{base}:harness_state.json'))
    learned = json.loads(git('show', f'{after}:harness_state.json'))
    changed = []
    for key in sorted(set(before['entries']) | set(learned['entries'])):
        left, right = before['entries'].get(key), learned['entries'].get(key)
        fields = ('title', 'body', 'module', 'kind')
        if left is None or right is None or any(left.get(field) != right.get(field) for field in fields):
            changed.append((key, left, right))
    result = ['## A harness changes and transfer evidence', '',
              f'Full harness diff `{base}..{after}`:', '']
    diff_path = output_dir / 'A.harness_diff.patch'
    diff_path.write_text(git('diff', base, after, '--'))
    result += [link('Complete unchanged Git diff, including metadata', diff_path), '']
    result += ['Every edit commit in that range (including direct CRUD if present):', '']
    commit_lines = git('log', '--reverse', '--format=%H%x09%cI%x09%s', f'{base}..{after}', '--', 'edits/').splitlines()
    result += table(['Commit', 'Timestamp', 'Subject'], [line.split('\t', 2) for line in commit_lines])
    result += ['Changed entry contents and their retrieval in B1:', '']
    values = []
    for key, left, right in changed:
        entry = right or left
        hits = [event for event in metrics['B1']['retrieved']
                if any(item['id'] == entry['id'] for item in event['details'].get('entries', []))]
        values.append([key, 'deleted' if right is None else 'created' if left is None else 'updated',
                       entry['title'], len(hits), ', '.join(trace_link(audits['B1'], str(event['line']), event['line']) for event in hits)])
    result += table(['Entry', 'Change', 'Title', 'B1 retrieval events containing ID', 'Evidence'], values)
    result += ['Retrieval counts match archived bare entry IDs; retrieval proves availability, not that a tactic was followed or improved an answer.', '']
    def researcher_entry(entry):
        return entry
    result += ['Entry content below includes every field sent to the researcher, including usage/outcome history.', '']
    result += fenced([{'key': key, 'before': researcher_entry(left), 'after': researcher_entry(right)} for key, left, right in changed])
    if interpretation.get('transfer'):
        result += interpretation_lines(interpretation['transfer'])
    return result


def render(input_dir=HERE, output=None):
    input_dir = Path(input_dir).resolve()
    output = Path(output).resolve() if output else input_dir / 'Round2.md'
    protected = ROOT / 'runs' / 'proof_report.md'
    if output.name == 'proof_report.md' or output == protected.resolve():
        raise ValueError('The original proof_report.md is protected')
    original = protected.read_bytes()
    identity_path = input_dir / 'original_report_identity.json'
    if identity_path.exists() and sha(original) != read(identity_path)['sha256']:
        raise ValueError('Original proof report differs from its pre-round-two identity')
    manifest = read(input_dir / 'manifest.json')
    missing = set(REQUIRED) - set(manifest.get('runs', {}))
    if missing:
        raise ValueError('Completed manifest arms are required: ' + ', '.join(sorted(missing)))
    interpretation = read(input_dir / 'interpretation.json')
    validate_interpretation(interpretation)
    labels = list(REQUIRED) + [label for label in ('SI', 'explicit') if label in manifest['runs']]
    audits, metrics, inputs = {}, {}, [input_dir / name for name in ('manifest.json', 'interpretation.json', 'diagnosis.md', 'rollback.json')]
    for label in labels:
        audit_path, metrics_path = input_dir / f'{label}.audit.json', input_dir / f'{label}.metrics.json'
        audits[label], metrics[label] = read(audit_path), read(metrics_path)
        run_id = manifest['runs'][label]
        if audits[label]['run_id'] != run_id or metrics[label]['run_id'] != run_id:
            raise ValueError(f'Mismatched run identity for {label}')
        if metrics[label]['manifest']['status'] != 'complete' or audits[label].get('run_end') is None:
            raise ValueError(f'{label} is not completed; never render an active run')
        verify_source_files(audits[label])
        largest_path = input_dir / f'{label}.largest_root_prompt.txt'
        largest = largest_path.read_text()
        if sha(largest) != audits[label]['largest_prompt']['sha256'] or len(largest) != audits[label]['largest_prompt']['total']:
            raise ValueError(f'{label} largest-root input disagrees with its audit')
        inputs += [audit_path, metrics_path, largest_path]
    content = ['# Round 2', ''] + interpretation_lines(interpretation['root'], 'RLM verdict')
    content += interpretation_lines(interpretation['self_improvement'], 'Self-improvement verdict')
    content += [
                'One pair provides mechanism evidence, not a statistical result. These runs include overlapping execution, recorded below. Model and web nondeterminism, '
                'source availability, and refinement overhead limit causal comparisons. Counts alone do not determine '
                'whether the system works; behavior assessments below cite the recorded actions.', '',
                '## Original diagnosis and complete old A proposal', '', narrative(input_dir / 'diagnosis.md'), '',
                '## Source fixes and offline verification', '',
                f'Executed source commit: `{manifest["source_commit"]}`. '
                f'Installed modules verified: {manifest.get("installed_modules_verified", "unavailable")}; '
                f'pinned RLM verified: {manifest.get("pinned_rlm_verified", "unavailable")}.', '']
    for fix in interpretation.get('source_fixes', []):
        content += [f'`{fix["commit"]}` — {fix["description"]}', '']
        for test in fix.get('tests', []):
            content += [f'`{test["command"]}`: {test["result"]}. {evidence(test.get("evidence", []))}', '']
    for name in ('fix_quality_review.md', 'fix_quality_details.md', 'refine_quality_audit.md', 'repl_state_review.md',
                 'planner_preflight.md', 'archive_audit_verification.md', 'shared_fragments_fix.md',
                 'saved_input_validator.md', 'planner_fragments_preflight.md', 'archive_audit_fragments_preflight.md',
                 'orchestration_recovery.md', 'run_explicit_completion.md', 'public_tool_contract_fix.md',
                 'planner_typed_preflight.md', 'archive_audit_typed_preflight.md'):
        path = input_dir / name
        if path.exists():
            content += [narrative(path), '']
            inputs.append(path)
    content += fenced({'unit_suite': manifest.get('unit_suite'), 'configuration': manifest['config']})
    logs = sorted(path for path in input_dir.glob('*.log') if not path.name.endswith('.console.log'))
    content += [', '.join(link(path.name, path) for path in logs), '', '## Lineage, rollback and run provenance', '']
    environment = input_dir / 'environment_notes.md'
    if environment.exists():
        content += [narrative(environment), '']
        inputs.append(environment)
    content += fenced(read(input_dir / 'rollback.json'))
    for retry in sorted(p for p in input_dir.glob('rollback*.json') if p.name != 'rollback.json'):
        content += [link('Restart rollback', retry), ''] + fenced(read(retry))
    if manifest.get('failed_runs'):
        content += ['### Preserved research and orchestration failures', ''] + fenced(manifest['failed_runs'])
    if manifest.get('superseded_runs'):
        content += ['### Prior arms superseded for a controlled replay', ''] + fenced(manifest['superseded_runs'])
    content += table(['Arm', 'Run', 'Base', 'Learning', 'Lineage', 'Final harness'], [
        [label, link(manifest['runs'][label], Path(audits[label]['task_path']).parent / 'research.json'),
         metrics[label]['manifest']['base_sha'], metrics[label]['manifest']['learning'],
         metrics[label]['manifest']['lineage'], metrics[label]['manifest']['harness_head']] for label in labels])
    for label in labels:
        content += [f'{label} command:', ''] + fenced(shlex.join(manifest['commands'][label]), 'bash')
    content += ['## B1, B1-frozen and B0 measurements', '']
    compare = ('B1', 'B1-frozen', 'B0')
    measurements = [
        ('All Codex attempts', lambda m, a: m['codex_calls']),
        ('Codex attempts excluding refinement', lambda m, a: m['codex_calls'] - m['calls_by_purpose'].get('refine', 0)),
        ('Refinement attempts', lambda m, a: m['calls_by_purpose'].get('refine', 0)),
        ('Codex retries', lambda m, a: m['codex_retries']),
        ('Recorded component error events', lambda m, a: len(m['errors'])),
        ('UTC wall seconds', lambda m, a: m['wall_s']),
        ('Monotonic active-span seconds', lambda m, a: m['active_span_s']),
        ('Root iterations', lambda m, a: sum(r['iterations'] for r in a['rlms'] if r['depth'] == 0)),
        ('Self-check issues', lambda m, a: len(m['issues'])), ('Signals', lambda m, a: len(m['signals'])),
        ('Uncited cells', lambda m, a: m['uncited_cells']), ('Failed fetch requests', lambda m, a: m['failed_fetches']),
        ('Failed fetch attempts', lambda m, a: m['failed_fetch_attempts']), ('Empty searches', lambda m, a: m['empty_searches']),
        ('Final rows', lambda m, a: m['rows']), ('Returned fetched-text chars', lambda m, a: a['overlap']['total_chars']),
        ('Largest root input chars', lambda m, a: a['largest_prompt']['total']),
        ('Returned-text 50-gram coverage fraction', lambda m, a: a['overlap']['fraction']),
        ('Sub-call input chars (prompt + schema)', lambda m, a: a['subcall_input_chars']),
    ]
    content += table(['Metric', *compare], [[name, *[fn(metrics[label], audits[label]) for label in compare]] for name, fn in measurements])
    content += ['B1 can refine during and after the task. B1-frozen starts from POST_A with learning disabled; '
                'B0 starts from BASE with learning disabled. These observed arms are not randomized replicates. '
                'Wall duration includes refinement where enabled; terminal request failures and backend attempt failures are distinct.', '']
    for label in labels:
        content += [link(f'{label}: exact largest root input', input_dir / f'{label}.largest_root_prompt.txt'), '']
        content += run_details(label, audits[label], metrics[label], interpretation)
        for suffix in ('root_analysis.md', 'quality_review.md'):
            path = input_dir / f'{label}.{suffix}'
            if path.exists():
                content += [narrative(path), '']
                inputs.append(path)
    for label in labels:
        content += refinement_details(label, audits[label])
        content += edit_timing(label, audits[label], metrics[label], Path(manifest.get('workspace_roots', {}).get(label, ROOT)) / 'harness')
        inputs += sorted((Path(audits[label]['task_path']) / 'refine_requests').glob('*/*.json'))
    content += harness_comparison(manifest, audits, metrics, interpretation, input_dir)
    for name in ('A.refine_analysis.md', 'B1.transfer_analysis.md', 'SI.generalization.md',
                 'quality_comparison.md', 'control_comparison.md', 'parallel_execution.md',
                 'explicit.analysis.md', 'reporting_fix.md', 'offline_test_isolation.md', 'error_review.md',
                 'whole_value_cohort.md', 'fragment_cohort.md', 'boolean_memory_lineage.md', 'archive_audit_final.md'):
        path = input_dir / name
        if path.exists():
            content += [narrative(path), '']
            inputs.append(path)
    content += ['## Ten-check verdict matrix', '',
                'These verdicts assess the recorded behavior against the unchanged checks.', '']
    content += table(['Prior follow-up check', 'Check', 'Verdict', 'Reason', 'Evidence'], [
        [CHECK_NAMES[item['id'] - 1], item['check'], item['verdict'], item['explanation'], evidence(item.get('evidence', []))]
        for item in sorted(interpretation['checks'], key=lambda item: item['id'])])
    if interpretation.get('limitations'):
        content += ['## Interpretation limits', '', *[f'- {item}' for item in interpretation['limitations']], '']
    content += ['## Final full cited tables', '']
    for label in labels:
        path = Path(audits[label]['task_path']) / 'output.json'
        content += [f'### {label}', '', link('Complete output with quotations', path), '', render_table(read(path)), '']
        inputs.append(path)
    document = '\n'.join(content) + '\n'
    if protected.read_bytes() != original:
        raise ValueError('Original proof report changed during rendering; output not written')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + '.tmp')
    temporary.write_text(document)
    temporary.replace(output)
    metadata = {'created_at': datetime.now(timezone.utc).isoformat(), 'output': str(output),
                'output_sha256': sha(document), 'output_chars': len(document),
                'renderer_sha256': sha(Path(__file__).read_bytes()), 'run_ids': manifest['runs'],
                'harness_base': manifest['BASE'], 'harness_post_a': manifest['POST_A'],
                'source_hashes_verified': True, 'original_proof_report_sha256': sha(original),
                'original_proof_report_unchanged': protected.read_bytes() == original,
                'inputs': [{'path': str(path), 'sha256': sha(path.read_bytes())} for path in inputs]}
    output.with_suffix('.render.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, default=HERE)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    print(render(args.input_dir, args.output))
