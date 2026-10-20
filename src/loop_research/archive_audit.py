"""Read-only audit of durable run archives, including interrupted and legacy runs.

Run with ``python -m loop_research.archive_audit RUN_DIR --output-dir DIR`` or
``python -m loop_research.archive_audit --all ARCHIVE_ROOT --output-dir DIR``.
Missing evidence is explicit; malformed or contradictory evidence is an error.
"""
import argparse
import ast
from collections import Counter, defaultdict, deque
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys

from loop_research.codex_backend import INSTRUCTION
from loop_research.page_fetch import FETCH_PATH, FetchError, verify_receipt
from loop_research.repl_tools import normalized_url
from loop_research.rlm_codex_client import transcript

HARNESS_MARKER = '\nCURRENT RELEVANT HARNESS ENTRIES\n'
REFINEMENT_MARKER = '\nCURRENT REFINEMENT STATUS\n'


class ArchiveCorruptionError(ValueError):
    """An archived value contradicts its format or recorded integrity metadata."""


def read(path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, UnicodeError) as error:
        raise ArchiveCorruptionError(f'{path}: {error}') from error


def lines(path):
    if not path.exists():
        return []
    try:
        contents = path.read_text()
    except UnicodeError as error:
        raise ArchiveCorruptionError(f'{path}: {error}') from error
    records = []
    for number, line in enumerate(contents.splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError('JSONL record must be an object')
        except ValueError as error:
            raise ArchiveCorruptionError(f'{path}:{number}: {error}') from error
        records.append(dict(value, _line=number))
    return records


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def link(path, line=None):
    return str(path.resolve()) + (f':{line}' if line is not None else '')


def match_iterations(models, iterations):
    """Child iteration logs can occur before the parent's corresponding log.

    Match the complete serialized prompt prefix and model response; chronological
    adjacency alone is insufficient when an outer REPL invokes a child RLM.
    """
    matched, used = {}, set()
    for iteration in iterations:
        event = iteration['event']
        prefix = transcript(event['prompt'])
        candidates = [model for model in models if model['_line'] < iteration['_line']
            and model['_line'] not in used and model['prompt'].startswith(prefix)
            and (model['prompt'] == prefix or model['prompt'][len(prefix):].startswith((HARNESS_MARKER, REFINEMENT_MARKER)))
            and model['response'] == event['response']]
        if not candidates:
            continue
        model = max(candidates, key=lambda item: item['_line'])
        used.add(model['_line'])
        matched[model['_line']] = iteration
    return matched


def partition_prompt(model, iteration, task):
    messages = iteration['event']['prompt']
    serialized = transcript(messages)
    assert model['prompt'].startswith(serialized)
    suffix = model['prompt'][len(serialized):]
    refinement_status = ''
    if suffix.startswith(REFINEMENT_MARKER):
        suffix = suffix[len(REFINEMENT_MARKER):]
        _, end = json.JSONDecoder().raw_decode(suffix)
        refinement_status, suffix = suffix[:end], suffix[end:]
    assert not suffix or suffix.startswith(HARNESS_MARKER)
    full = INSTRUCTION + model['prompt']
    parts = dict(system=len(INSTRUCTION), question_and_columns=0, other_task_instructions=0,
                 harness=0, code=0, repl_output=0, wrappers=0)
    current_harness = suffix[len(HARNESS_MARKER):] if suffix else ''
    parts['harness'] += len(current_harness)
    brief_path = task / 'root_prompt.txt'
    initial_path = brief_path if brief_path.exists() else task / 'prompt.txt'
    initial = initial_path.read_text()
    first_user = next(i for i, message in enumerate(messages) if message['role'] == 'user')
    assert initial in messages[first_user]['content'], 'Archived task/root brief is absent from initial user message'
    harness = ''
    if 'RELEVANT HARNESS\n' in initial:
        harness = initial.split('RELEVANT HARNESS\n', 1)[1].split('\n\nTOOLS\n', 1)[0]
    parts['harness'] += len(harness)
    assert initial.startswith('TASK\n')
    spec_start = initial.index('\nSPEC\n') + len('\nSPEC\n')
    _, spec_chars = json.JSONDecoder().raw_decode(initial[spec_start:])
    question_and_columns = initial[:spec_start + spec_chars]
    parts['question_and_columns'] = len(question_and_columns)
    parts['other_task_instructions'] = len(initial) - len(question_and_columns) - len(harness) + len(refinement_status)
    details = []
    for index, message in enumerate(messages):
        content = message['content']
        assert isinstance(content, str)
        details.append(dict(message=index, role=message['role'], chars=len(content), sha256=sha(content), prefix=content[:80]))
        if message['role'] == 'system':
            parts['system'] += len(content)
        elif index == first_user:
            continue
        elif message['role'] == 'assistant':
            parts['code'] += sum(len(block.group(1)) for block in re.finditer(r'```repl\s*\n(.*?)```', content, re.S))
        elif re.match(r'REPL output(?: \(block [1-9]\d*\))?:', content):
            parts['repl_output'] += len(content)
    parts['wrappers'] = len(full) - sum(parts.values())
    assert parts['wrappers'] >= 0 and sum(parts.values()) == len(full)
    return full, dict(parts=parts, total=len(full), sha256=sha(full), messages=details,
        initial_input_path=str(initial_path), initial_input_chars=len(initial), initial_input_sha256=sha(initial),
        question_and_columns_sha256=sha(question_and_columns),
        initial_harness_chars=len(harness), current_harness_chars=len(current_harness),
        current_refinement_status_chars=len(refinement_status),
        partition_policy=('Nonoverlapping attribution by origin: system includes backend instruction; question_and_columns '
            'is the exact initial TASK/question plus SPEC JSON prefix through the end of that JSON value; '
            'other_task_instructions is the remaining archived initial root input, including '
            'language, as-of and learning policy, minus any initial harness payload, plus complete current refinement status; '
            'harness includes initial and current retrieved-entry payloads; code is earlier assistant REPL code; '
            'repl_output recognizes both REPL output: and REPL output (block N): headers and counts the complete '
            'formatted message content (including combined multi-block output), including its header, stdout, '
            'stderr and variable-name listings when present, not raw stdout alone; printed copies of instructions, '
            'harness or pages remain in that category; '
            'wrappers includes serialization, message/context/harness markers, reminders, assistant prose and fences.'))


def iteration_spans(trace):
    starts, spans = {}, []
    for event in trace:
        if event['component'] != 'RLM iteration':
            continue
        details = event['details']
        if 'rlm_id' not in details:
            continue  # Legacy traces cannot identify parent/child RLM spans.
        key = (details['rlm_id'], details['iteration'])
        if event['event'] == 'iteration.start':
            starts[key] = event
        elif event['event'] == 'iteration.end':
            if key not in starts:
                continue
            spans.append(dict(start=starts[key], end=event, **details))
    return spans


def fetch_audit(task, trajectory, calls, trace, evidence):
    telemetry = {item['id']: item for item in read(task / 'fetch_telemetry.json', [])}
    owners = {item['id']: item for item in evidence.get('fetches', [])}
    calls_by_id = {item['call_id']: item for item in calls if 'call_id' in item}
    execs = {item['details']['call_id']: item for item in trace if item['event'] == 'exec.end'}
    cache = read(task / 'tool_cache.json', {})
    returned = defaultdict(list)
    for record in trajectory:
        if record['type'] != 'tool' or record['tool'] not in ('fetch', 'fetch_many'):
            continue
        args, kwargs = record['args'], record['kwargs']
        many = record['tool'] == 'fetch_many'
        target = args[0] if args else kwargs['urls' if many else 'url']
        urls, results = (target, record['result']) if many else ([target], [record['result']])
        focus = kwargs.get('focus', args[1] if len(args) > 1 else '')
        assert len(urls) == len(results)
        for url, value in zip(urls, results):
            key = json.dumps(['fetch', normalized_url(url), ' '.join(focus.split())])
            returned[key].append(dict(trajectory_line=record['_line'], chars=len(value), sha256=sha(value)))
    rows = []
    for request in evidence.get('fetches', []):
        owner = owners.get(request.get('owner_id', request['id']), request)
        measured = telemetry.get(request['id'])
        key = json.dumps(['fetch', request['url'], ' '.join(request['focus'].split())])
        if measured is None:
            text = cache.get(key) if request['status'] == 'succeeded' else (
                'FETCH_FAILED' if request.get('reason') == 'fetch_failed' else None)
            measured = {**request, 'returned_chars': len(text) if text is not None else None,
                'evidence_eligible': request['status'] == 'succeeded', 'raw_page_chars': None,
                'raw_page_chars_reason': 'archive_predates_complete_web_event_telemetry'}
        else:
            assert all(measured[key] == request[key] for key in ('id', 'url', 'focus', 'source', 'status'))
        row = {**measured, 'measurement_source': 'fetch_telemetry.json' if request['id'] in telemetry else 'legacy_evidence_and_cache',
               'attempts': [], 'trajectory_returns': returned.get(key, []), 'tool_trace_lines': []}
        if request.get('fetch_path') == FETCH_PATH and request['status'] == 'succeeded' and 'receipt' not in measured:
            raise ArchiveCorruptionError('Successful direct fetch is missing telemetry/receipt')
        if request.get('fetch_path') == FETCH_PATH and 'receipt' in measured:
            receipt = measured['receipt']
            try:
                verify_receipt(task, receipt)
            except FetchError as error:
                raise ArchiveCorruptionError('Direct download ' + error.error) from error
            if request['status'] == 'succeeded':
                text = (task / receipt['text_path']).read_bytes().decode('utf-8')
                cached = cache.get(json.dumps(['fetch', request['url'], FETCH_PATH]))
                if (receipt['status'] != 'succeeded' or receipt['requested_url'] != request['url'] or
                    text not in evidence['fetched'].get(request['url'], []) or cached != text or
                    any(value['sha256'] not in {receipt['text_sha256'], sha('FETCH_FAILED')}
                        for value in row['trajectory_returns'])):
                    raise ArchiveCorruptionError('Direct download readable text differs from evidence')
            row['direct_receipt_verified'] = True
            row['download_link'] = link(task / 'downloads' / (receipt['id'] + '.json'))
        for event in trace:
            details = event['details']
            if event['component'] == 'tools.fetch' and event['event'] == 'call.end' and details.get('url') == request['url'] and details.get('focus') == request['focus']:
                row['tool_trace_lines'].append(event['_line'])
        for attempt in owner.get('attempts', []):
            call = calls_by_id.get(attempt['call_id'])
            if call is None:
                row['attempts'].append(dict(call_id=attempt['call_id'], status=attempt['status'], completed_record_available=False))
                continue
            web = call.get('web_events')
            entry = dict(call_id=call['call_id'], attempt=call['attempt'], call_line=call['_line'],
                trace_line=execs.get(call['call_id'], {}).get('_line'), response_chars=call['response_chars'],
                error=call['error'], completed_record_available=True, complete_web_events_available=web is not None,
                requested_action_urls=[action['url'] for action in call.get('web_actions', []) if action.get('type') == 'open_page' and action.get('url')],
                web_events=web,
                result_urls=[result['url'] for item in (web or []) for result in item['event']['item'].get('results', []) if result.get('url')])
            if call['call_id'] in execs:
                entry['trace_link'] = link(task.parent / 'trace.jsonl', entry['trace_line'])
            entry['call_link'] = link(task / 'codex_calls.jsonl', call['_line'])
            row['attempts'].append(entry)
        row['evidence_owner_id'] = owner['id']
        if row['returned_chars'] is not None and row['trajectory_returns']:
            assert any(item['chars'] == row['returned_chars'] for item in row['trajectory_returns'])
        if row['evidence_eligible']:
            assert request['status'] == 'succeeded'
        rows.append(row)
    return rows


def coverage_audit(evidence, roots, execs):
    # Preserve the original criterion exactly: case/whitespace-sensitive 50-grams.
    n = 50
    texts = [(url, index, text) for url, values in evidence.get('fetched', {}).items() for index, text in enumerate(values)]
    wanted = {text[index:index+n] for _, _, text in texts for index in range(len(text)-n+1)}
    matched = set()
    for root in roots:
        text = root.get('_full', INSTRUCTION + root['prompt'])
        matched.update(text[index:index+n] for index in range(len(text)-n+1) if text[index:index+n] in wanted)
    rows = []
    for url, index, text in texts:
        mask = bytearray(len(text))
        for offset in range(len(text)-n+1):
            if text[offset:offset+n] in matched:
                mask[offset:offset+n] = b'\1' * n
        first = next((root for root in roots if text in root.get('_full', root['prompt'])), None)
        rows.append(dict(url=url, text_index=index, chars=len(text), sha256=sha(text), covered_chars=sum(mask),
            full_text_in_root=first is not None,
            first_full_root_trace_line=execs.get(first.get('_call', {}).get('call_id'), {}).get('_line') if first else None))
    total = sum(item['chars'] for item in rows)
    covered = sum(item['covered_chars'] for item in rows)
    return dict(ngram_chars=n, total_chars=total, covered_chars=covered, fraction=covered/total if total else None,
        fully_present_texts=sum(item['full_text_in_root'] for item in rows), texts=rows,
        limitation='Measures exact returned fetched text in root prompts. Fetch-path labels distinguish direct readable text from historical model-rendered extracts; raw download sizes are separate.')


def page_variable_excerpts(blocks, trace, evidence, states, selected_trace_lines=None):
    """Find real stored page values, then AST references in executed REPL blocks.

    Locals snapshots establish data provenance; variable names alone do not. This
    is block-level evidence, not a claim that every branch/line executed.
    """
    pages = [(dict(url=url, text_index=index, chars=len(text), sha256=sha(text)), text)
        for url, texts in evidence.get('fetched', {}).items() for index, text in enumerate(texts) if text]

    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for item in value.values():
                yield from strings(item)
        elif isinstance(value, list):
            for item in value:
                yield from strings(item)

    def matches(value):
        values = list(strings(value))
        return [info for info, text in pages if any(text in value for value in values)]

    previous, candidates = {}, []
    for block in sorted(blocks, key=lambda item: item['trace_line']):
        current = states.get(block['trace_line']) or {}
        before, before_values = previous.get(block['rlm_id'], (None, {}))
        previous[block['rlm_id']] = (block, current)
        try:
            tree = ast.parse(block['code'])
        except SyntaxError:
            continue
        nodes = list(ast.walk(tree))
        stores = defaultdict(list)
        for node in nodes:
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                stores[node.id].append((node.lineno, node.col_offset))
        # A prior snapshot cannot prove a value read after reassignment. Ignore
        # such reads conservatively instead of inferring intra-block dataflow.
        loads = [node for node in nodes if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
                 and not any(position < (node.lineno, node.col_offset) for position in stores[node.id])]
        provenance, positions = {}, []
        for name in sorted({node.id for node in loads}):
            found = matches(before_values.get(name))
            if found:
                provenance[name] = dict(snapshot_trace_line=before['trace_line'],
                    snapshot_trajectory_line=before['trajectory_line'], snapshot_link=before['trajectory_link'], fetched_texts=found)
                positions.extend(node.lineno for node in loads if node.id == name)
        calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        kind = ('page_subcall' if calls & {'llm_query', 'llm_query_batched', 'llm_query_json',
                                         'llm_query_json_batched', 'rlm_query', 'rlm_query_batched'} else
                'page_validation' if any(isinstance(node, (ast.In, ast.NotIn)) for node in ast.walk(tree)) else
                'page_variable_processing')
        successes = [event['_line'] for event in trace if event['component'] == 'tools.fetch' and event['event'] == 'call.end'
            and event['details'].get('success') and block['code_start_trace_line'] < event['_line'] < block['trace_line']]
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
                continue
            fetch_calls = [call for call in ast.walk(node.value) if isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name) and call.func.id in {'fetch', 'fetch_many'}]
            if not fetch_calls or not successes:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = {target.id for value in targets for target in ast.walk(value) if isinstance(target, ast.Name)}
            for name in sorted(names):
                found = matches(current.get(name))
                if found:
                    provenance[name] = dict(snapshot_trace_line=block['trace_line'],
                        snapshot_trajectory_line=block['trajectory_line'], snapshot_link=block['trajectory_link'], fetched_texts=found)
                    positions.append(node.lineno)
                    kind = 'fetch_assignment'
        if not provenance:
            continue
        code_lines = block['code'].splitlines()
        start = max(1, min(positions)-1)
        end = min(len(code_lines), start+8)
        candidates.append(dict(**block, excerpt='\n'.join(code_lines[start-1:end]), excerpt_kind=kind,
            excerpt_start_line=start, excerpt_end_line=end, variables=sorted(provenance), variable_provenance=provenance,
            successful_fetch_trace_lines=successes,
            provenance_method='Complete successful fetched text occurs in the referenced variable in an archived REPL locals snapshot; AST references identify processing in this executed block. This is not per-line execution proof.'))
    if selected_trace_lines is not None:
        assert len(selected_trace_lines) <= 3 and len(set(selected_trace_lines)) == len(selected_trace_lines), 'Select at most three distinct block trace lines'
        by_line = {item['trace_line']: item for item in candidates}
        unknown = set(selected_trace_lines) - by_line.keys()
        assert not unknown, f'Selected blocks lack proven stored-page references: {sorted(unknown)}; eligible lines: {sorted(by_line)}'
        selected = [by_line[line] for line in selected_trace_lines]
    else:
        selected = []
        for kind in ('fetch_assignment', 'page_subcall', 'page_validation'):
            candidate = next((item for item in candidates if item['excerpt_kind'] == kind), None)
            if candidate is not None:
                selected.append(candidate)
        for candidate in candidates:
            if len(selected) == 3:
                break
            if candidate not in selected:
                selected.append(candidate)
        selected.sort(key=lambda item: item['trace_line'])
    return selected, candidates


def archived_calls(task, calls):
    """Include dispatched inputs even when no completion record was written."""
    attempts = {call.get('call_id', f'line:{call["_line"]}'): dict(call) for call in calls}
    for path in sorted((task / 'codex_attempts').glob('*.json')):
        item = read(path)
        if not isinstance(item, dict):
            raise ArchiveCorruptionError(f'{path}: attempt must be an object')
        key = item.get('call_id', str(path))
        if key in attempts:
            for field in ('purpose', 'prompt_chars', 'prompt_sha256'):
                if field in item and field in attempts[key] and item[field] != attempts[key][field]:
                    raise ArchiveCorruptionError(f'{path}: inconsistent {field} for call {key}')
        else:
            attempts[key] = dict(item, _attempt_path=str(path))
    for item in attempts.values():
        body = item.get('prompt')
        if body is not None:
            if not isinstance(body, str) or (item.get('prompt_chars', len(body)) != len(body)
                    or item.get('prompt_sha256', sha(body)) != sha(body)):
                raise ArchiveCorruptionError(f'{task}: prompt integrity mismatch for call {item.get("call_id")}')
            item['_full'] = body
    return list(attempts.values())


def attach_models(models, attempts, task):
    by_hash = defaultdict(deque)
    for call in attempts:
        if not call.get('error'):
            by_hash[(call.get('purpose'), call.get('prompt_sha256'))].append(call)
    for model in models:
        full = INSTRUCTION + model['prompt']
        queue = by_hash[(model['purpose'], sha(full))]
        if not queue:
            # The complete input may contain a historical backend instruction.
            queue = next((values for (purpose, _), values in by_hash.items() if values
                and purpose == model['purpose'] and values[0].get('_full', '').endswith(model['prompt'])), deque())
        schema_text = json.dumps(model['schema']) if 'schema' in model else ''
        candidates = [call for call in queue
            if call.get('response_chars', len(model['response'])) == len(model['response'])
            and call.get('response', model['response']) == model['response']
            and ('schema_chars' not in call or call['schema_chars'] == len(schema_text))
            and ('schema_sha256' not in call or call['schema_sha256'] == (sha(schema_text) if schema_text else None))]
        if queue and not candidates:
            raise ArchiveCorruptionError(f'{task}: response/schema integrity mismatch at trajectory line {model["_line"]}')
        call = candidates[0] if candidates else None
        ambiguous = len(candidates) > 1
        if call is not None and not ambiguous:
            queue.remove(call)
        model['_call'] = call or {}
        if call is not None:
            full = call.get('_full', full)
            if len(full) != call.get('prompt_chars', len(full)) or sha(full) != call.get('prompt_sha256', sha(full)):
                raise ArchiveCorruptionError(f'{task}: model prompt integrity mismatch at trajectory line {model["_line"]}')
            if call.get('response_chars', len(model['response'])) != len(model['response']):
                raise ArchiveCorruptionError(f'{task}: response size mismatch at trajectory line {model["_line"]}')
            for candidate in candidates:
                candidate['_full'] = full
            if ambiguous:
                model['_call'] = {**call, 'call_id': None}
                model['_candidate_call_ids'] = [candidate.get('call_id') for candidate in candidates]
            else:
                call['_model'] = model
            model['_full'] = full
        model['_schema_chars'] = len(schema_text)
        model['_schema_sha256'] = sha(schema_text) if schema_text else None
        if call and 'schema' in model:
            for field, expected in [('schema_chars', len(schema_text)), ('schema_sha256', sha(schema_text))]:
                if field in call and call[field] != expected:
                    raise ArchiveCorruptionError(f'{task}: {field} mismatch at trajectory line {model["_line"]}')
    verified = {(call.get('prompt_sha256'), call.get('prompt_chars')): call['_full']
                for call in attempts if '_full' in call}
    for call in attempts:
        key = (call.get('prompt_sha256'), call.get('prompt_chars'))
        if key in verified and key[0] is not None and key[1] is not None:
            call['_full'] = verified[key]


def iteration_records(models, matched, trace, execs, task, run):
    spans = iteration_spans(trace)
    details, blocks, states, used = [], [], {}, set()
    for model in models:
        iteration = matched.get(model['_line'])
        if iteration is None:
            continue
        call = model['_call']
        exec_line = execs.get(call.get('call_id'), {}).get('_line')
        # The worker logger is shared with child RLMs, which reset/increment its
        # counter. Identity comes from the exact prompt/response match and its
        # backend call inside the innermost per-RLM trace span, not that counter.
        candidates = [span for span in spans if exec_line is not None
            and span['start']['_line'] < exec_line < span['end']['_line']]
        deepest = max((span['depth'] for span in candidates), default=None)
        candidates = [span for span in candidates if span['depth'] == deepest]
        span = candidates[0] if len(candidates) == 1 else None
        info = dict(rlm_id=span['rlm_id'] if span else None,
            parent_rlm_id=span['parent_rlm_id'] if span else None, depth=span['depth'] if span else None,
            iteration=span['iteration'] if span else iteration['event']['iteration'],
            worker_iteration=iteration['event']['iteration'],
            model_trajectory_line=model['_line'], trajectory_line=iteration['_line'],
            trace_start_line=span['start']['_line'] if span else None, trace_end_line=span['end']['_line'] if span else None,
            trace_link=link(run / 'trace.jsonl', span['end']['_line']) if span else None,
            call_id=call.get('call_id'), prompt_sha256=call.get('prompt_sha256'), backend_chars=call.get('prompt_chars'))
        if span is None:
            info['trace_unavailable_reason'] = ('ambiguous_overlapping_iteration_spans' if candidates
                else 'matching_completed_iteration_span_not_archived')
            if candidates:
                info['candidate_iteration_spans'] = [dict(rlm_id=item['rlm_id'], depth=item['depth'],
                    iteration=item['iteration'], trace_start_line=item['start']['_line'],
                    trace_end_line=item['end']['_line']) for item in candidates]
        details.append(info)
        for block in iteration['event'].get('code_blocks', []):
            head = '\n'.join(block['code'].splitlines()[:8])
            candidates = [event for event in trace if span and event['component'] == 'REPL' and event['event'] == 'code.end'
                and event['details']['rlm_id'] == span['rlm_id'] and event['details']['first_lines'] == head
                and span['start']['_line'] < event['_line'] < span['end']['_line'] and event['_line'] not in used]
            end = min(candidates, key=lambda item: item['_line']) if candidates else None
            start_candidates = [event['_line'] for event in trace if end and event['component'] == 'REPL'
                and event['event'] == 'code.start' and event['details']['rlm_id'] == span['rlm_id']
                and event['details']['first_lines'] == head and event['_line'] < end['_line']]
            start = max(start_candidates) if start_candidates else None
            if end:
                used.add(end['_line'])
                states[end['_line']] = block['result'].get('locals', {})
            stdout = block['result']['stdout']
            blocks.append(dict(**info, trace_line=end['_line'] if end else None, code_start_trace_line=start,
                code=block['code'], code_sha256=sha(block['code']), stdout=stdout,
                stdout_chars=len(stdout), stdout_sha256=sha(stdout),
                code_trace_link=link(run / 'trace.jsonl', end['_line']) if end else None,
                trajectory_link=link(task / 'trajectory.jsonl', iteration['_line'])))
    return details, blocks, states


def largest_prompt(attempts, matched, execs, task, run, iteration_details=()):
    roots = [call for call in attempts if call.get('purpose') == 'root']
    measured = [call for call in roots if isinstance(call.get('prompt_chars'), int)]
    if not measured:
        return None, dict(total=None, sha256=None, parts=None, unavailable_reason='root_prompt_measurement_not_archived')
    call = max(measured, key=lambda item: item['prompt_chars'])
    model, full = call.get('_model'), call.get('_full')
    iteration = matched.get(model['_line']) if model else None
    iteration_info = next((info for info in iteration_details
        if model and info['model_trajectory_line'] == model['_line']), {})
    prompt = dict(total=call['prompt_chars'], sha256=call.get('prompt_sha256'), parts=None)
    reason = None
    if iteration is None:
        reason = 'worker_iteration_not_archived'
    elif not any((task / name).exists() for name in ('root_prompt.txt', 'prompt.txt')):
        reason = 'initial_task_input_not_archived'
    else:
        initial_path = task / ('root_prompt.txt' if (task / 'root_prompt.txt').exists() else 'prompt.txt')
        initial = initial_path.read_text()
        user = next((message['content'] for message in iteration['event']['prompt'] if message['role'] == 'user'), '')
        if initial not in user:
            reason = 'archived_initial_input_not_in_iteration_transcript'
        elif not initial.startswith('TASK\n') or '\nSPEC\n' not in initial:
            reason = 'legacy_initial_input_format_has_no_task_spec_partition'
        elif full != INSTRUCTION + model['prompt']:
            reason = 'historical_backend_instruction_not_partitioned'
        else:
            _, prompt = partition_prompt(model, iteration, task)
    if reason:
        prompt['partition_unavailable_reason'] = reason
    if full is None:
        prompt['text_unavailable_reason'] = 'full_backend_prompt_not_archived_or_verifiable'
    trace_line = execs.get(call.get('call_id'), {}).get('_line')
    prompt.update(trajectory_line=model['_line'] if model else None,
        iteration=iteration_info.get('iteration', iteration['event']['iteration'] if iteration else None),
        worker_iteration=iteration['event']['iteration'] if iteration else None,
        iteration_trajectory_line=iteration['_line'] if iteration else None, trace_line=trace_line,
        call_id=call.get('call_id'), trace_link=link(run / 'trace.jsonl', trace_line) if trace_line else None)
    if trace_line is None:
        prompt['trace_unavailable_reason'] = 'exec_end_not_archived'
    return full, prompt


def audit_task(task, run=None, excerpt_trace_lines=None):
    """Audit a task without writing into its archive; missing data remains null."""
    task = Path(task).resolve()
    run = Path(run).resolve() if run is not None else task.parent
    try:
        return _audit_task(task, run, excerpt_trace_lines)
    except (AssertionError, KeyError, TypeError, StopIteration) as error:
        raise ArchiveCorruptionError(f'{task}: invalid archive structure: {type(error).__name__}: {error}') from error


def _audit_task(task, run, excerpt_trace_lines):
    trace, trajectory, calls = lines(run / 'trace.jsonl'), lines(task / 'trajectory.jsonl'), lines(task / 'codex_calls.jsonl')
    run_trace = trace
    multi_task = len(task_directories(run)) > 1
    trace_reason = None
    if multi_task:
        if all(event.get('details', {}).get('task_id') is not None for event in trace):
            trace = [event for event in trace if event['details']['task_id'] == task.name]
        else:
            trace = []
            trace_reason = 'multi_task_trace_ownership_not_archived'
    attempts = archived_calls(task, calls)
    models = [item for item in trajectory if item.get('type') == 'model' and item.get('purpose') in ('root', 'sub')]
    attach_models(models, attempts, task)
    matched = match_iterations(models, [item for item in trajectory if item.get('type') == 'worker_iteration'])
    execs = {item['details']['call_id']: item for item in trace if item['event'] == 'exec.end'}
    iteration_details, blocks, states = iteration_records(models, matched, trace, execs, task, run)
    full, prompt = largest_prompt(attempts, matched, execs, task, run, iteration_details)
    linked_iterations = {item['_line'] for item in matched.values()}
    for iteration in trajectory:
        if iteration.get('type') != 'worker_iteration' or iteration['_line'] in linked_iterations:
            continue
        info = dict(rlm_id=None, parent_rlm_id=None, depth=None, iteration=iteration['event']['iteration'],
            worker_iteration=iteration['event']['iteration'],
            model_trajectory_line=None, trajectory_line=iteration['_line'], trace_start_line=None, trace_end_line=None,
            trace_link=None, call_id=None, prompt_sha256=None, backend_chars=None,
            model_unavailable_reason='matching_model_transcript_not_archived',
            trace_unavailable_reason='model_call_linkage_not_available')
        iteration_details.append(info)
        for block in iteration['event'].get('code_blocks', []):
            stdout = block['result']['stdout']
            blocks.append(dict(**info, trace_line=None, code_start_trace_line=None, code=block['code'],
                code_sha256=sha(block['code']), stdout=stdout, stdout_chars=len(stdout), stdout_sha256=sha(stdout),
                code_trace_link=None, trajectory_link=link(task / 'trajectory.jsonl', iteration['_line'])))
    evidence = read(task / 'evidence.json', {})
    fetches = fetch_audit(task, trajectory, calls, trace, evidence)
    roots = [dict(prompt=call['_full'], _full=call['_full'], _call=call) for call in attempts
             if call.get('purpose') == 'root' and '_full' in call]
    overlap = coverage_audit(evidence, roots, execs)
    missing_roots = [call for call in attempts if call.get('purpose') == 'root' and '_full' not in call]
    if not (task / 'evidence.json').exists() or missing_roots or not roots:
        reason = ('evidence_not_archived' if not (task / 'evidence.json').exists() else
                  'some_root_prompt_bodies_not_archived_or_verifiable' if missing_roots else 'root_prompt_bodies_not_archived')
        overlap.update(covered_chars=None, fraction=None, fully_present_texts=None, unavailable_reason=reason)
        for row in overlap['texts']:
            row.update(covered_chars=None, full_text_in_root=None, first_full_root_trace_line=None)
        if not (task / 'evidence.json').exists():
            overlap['total_chars'] = None
    linked_blocks = [block for block in blocks if block['trace_line'] is not None and block['code_start_trace_line'] is not None]
    excerpts, excerpt_candidates = page_variable_excerpts(linked_blocks, trace, evidence, states, excerpt_trace_lines)
    subs = [model for model in models if model['purpose'] == 'sub']
    subdetails = []
    for model in subs:
        call = model['_call']
        trace_line = execs.get(call.get('call_id'), {}).get('_line')
        backend_chars = call.get('prompt_chars')
        subdetails.append(dict(trajectory_line=model['_line'], trace_line=trace_line,
            call_id=call.get('call_id'), input_chars=len(model['prompt']) + model['_schema_chars'],
            prompt_input_chars=len(model['prompt']), schema_input_chars=model['_schema_chars'], schema_sha256=model['_schema_sha256'],
            backend_chars=backend_chars + model['_schema_chars'] if backend_chars is not None else None,
            backend_prompt_chars=backend_chars, input_sha256=sha(model['prompt']), prompt_sha256=call.get('prompt_sha256'),
            is_child_rlm_turn=model['_line'] in matched,
            trace_link=link(run / 'trace.jsonl', trace_line) if trace_line else None))
        if '_candidate_call_ids' in model:
            subdetails[-1].update(call_linkage_unavailable_reason='indistinguishable_archived_calls',
                                 candidate_call_ids=model['_candidate_call_ids'])
    rlms = [dict(trace_line=event['_line'], trace_link=link(run / 'trace.jsonl', event['_line']), **event['details'],
        iteration_records=[item for item in iteration_details if item['rlm_id'] is not None and item['rlm_id'] == event['details'].get('rlm_id')],
        repl_blocks=sum(block['rlm_id'] == event['details']['rlm_id'] for block in blocks) if 'rlm_id' in event['details'] else None)
        for event in trace if event['component'] == 'RLM' and event['event'] == 'completion.end']
    for rlm in rlms:
        if rlm['repl_blocks'] is None:
            rlm['linkage_unavailable_reason'] = 'legacy_trace_has_no_rlm_id'
    sources = [run / 'research.json', run / 'trace.jsonl', *[task / name for name in
        ('prompt.txt', 'root_prompt.txt', 'trajectory.jsonl', 'codex_calls.jsonl', 'evidence.json', 'tool_cache.json', 'fetch_telemetry.json')]]
    paths = sorted({request.get('fetch_path', 'model-mediated') for request in evidence.get('fetches', [])})
    result = dict(run_id=run.name, task_path=str(task), fetch_paths=paths, largest_prompt=prompt, fetches=fetches, overlap=overlap,
        subcalls=subdetails, subcall_count=len(subdetails), subcall_input_chars=sum(item['input_chars'] for item in subdetails),
        subcall_backend_chars=sum(item['backend_chars'] for item in subdetails) if all(item['backend_chars'] is not None for item in subdetails) else None,
        subcall_prompt_chars=sum(item['prompt_input_chars'] for item in subdetails),
        subcall_schema_chars=sum(item['schema_input_chars'] for item in subdetails), rlms=rlms, iterations=iteration_details,
        excerpts=excerpts, excerpt_count=len(excerpts), excerpt_shortfall=max(0, 3-len(excerpts)), blocks=blocks,
        excerpt_selection='explicit' if excerpt_trace_lines is not None else 'automatic_by_operation',
        excerpt_candidates=[{key: item[key] for key in ('trace_line', 'excerpt_kind', 'variables', 'code_trace_link', 'variable_provenance')}
            for item in excerpt_candidates],
        fetched_text_to_largest_root_ratio=overlap['total_chars']/prompt['total'] if overlap['total_chars'] is not None and prompt['total'] else None,
        constraints=[dict(trace_line=event['_line'], **event['details'], verdict_type=type(event['details']['verdict']).__name__)
            for event in trace if event['component'] == 'tools.check_constraint' and event['event'] == 'call.start'],
        refine=[event for event in trace if event['component'] == 'Refine'],
        run_end=next((event for event in reversed(trace) if event['component'] == 'Research' and event['event'] == 'run.end'), None),
        worker_end=next((event for event in reversed(trace) if event['component'] == 'Worker' and event['event'] == 'run.end'), None),
        source_files=[dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), bytes=path.stat().st_size)
            for path in sources if path.exists()], _largest_prompt_text=full)
    result['metrics'] = measure_task(task, run, calls, attempts, trace, evidence)
    if multi_task:
        result['run_trace'] = dict(scope='run', path=str(run / 'trace.jsonl'), events=run_trace)
    if trace_reason:
        result['trace_unavailable_reason'] = trace_reason
        for key in ('rlms', 'constraints', 'refine', 'run_end', 'worker_end'):
            result[key] = None
        for key in ('wall_s', 'active_span_s', 'rlms', 'batches', 'errors', 'refine', 'harness_edits', 'retrieved', 'repl'):
            result['metrics'][key] = None
            result['metrics']['unavailable'][key] = trace_reason
        for row in fetches:
            row['tool_trace_lines'] = None
            row['trace_unavailable_reason'] = trace_reason
    if not (task / 'trajectory.jsonl').exists():
        result['subcalls_unavailable_reason'] = 'trajectory.jsonl_not_archived'
        for key in ('subcall_count', 'subcall_input_chars', 'subcall_backend_chars', 'subcall_prompt_chars', 'subcall_schema_chars'):
            result[key] = None
    result['availability'] = {name: (task / name).exists() for name in
        ('trajectory.jsonl', 'codex_calls.jsonl', 'evidence.json', 'fetch_telemetry.json')}
    result['status'] = 'partial' if any(not present for present in result['availability'].values()) or prompt.get('partition_unavailable_reason') or overlap.get('unavailable_reason') or not result['run_end'] else 'available'
    return result

def measure_task(task, run, calls, attempts, trace, evidence):
    """Original proof metrics, with explicit absence instead of invented zeros."""
    manifest = read(run / 'research.json', {})
    trace = [dict({key: value for key, value in event.items() if key != '_line'}, line=event['_line']) for event in trace]
    checks = read(task / 'self_check.json', {})
    result = read(task / 'agent_result.json', {})
    rlms = [e for e in trace if e['component'] == 'RLM' and e['event'] == 'completion.end']
    repl = [e for e in trace if e['component'] == 'REPL' and e['event'] == 'code.end']
    batches, unavailable = [], {}
    for event in trace:
        if event['component'] not in ('tools.search_many', 'tools.fetch_many') or event['event'] != 'call.end':
            continue
        start = next((x for x in trace if x['event'] == 'call.start' and x['details'].get('span_id') == event['details']['span_id']), None)
        if start is None:
            unavailable['batches'] = 'some_batch_start_events_not_archived'
            continue
        inner = [x for x in trace if x['component'] == event['component'].removesuffix('_many') and x['event'] == 'call.end'
                 and start['line'] < x['line'] < event['line']]
        batches.append(dict(tool=event['component'], start_line=start['line'], end_line=event['line'], duration_s=event['duration_s'],
            items=len(event['details'].get('queries', event['details'].get('urls', []))),
            sum_inner_duration_s=sum(x['duration_s'] for x in inner), details=event['details']))
    ends = [e for e in trace if e['component'] == 'Research' and e['event'] == 'run.end']
    start = next((e for e in trace if e['component'] == 'Research' and e['event'] == 'run.start'), None)
    pages = [text for texts in evidence.get('fetched', {}).values() for text in texts]
    root_calls = [c for c in attempts if c.get('purpose') == 'root']
    metrics = dict(run_id=run.name, task_id=task.name, manifest=manifest,
        fetch_paths=sorted({f.get('fetch_path', 'model-mediated') for f in evidence.get('fetches', [])}),
        wall_s=(datetime.fromisoformat(ends[-1]['timestamp']) - datetime.fromisoformat(start['timestamp'])).total_seconds() if ends and start else None,
        active_span_s=ends[-1].get('duration_s') if ends else None,
        codex_calls=len(calls), codex_attempts=len(attempts), calls_by_purpose=dict(Counter(c['purpose'] for c in calls)),
        codex_retries=sum(c['attempt'] > 0 for c in calls), page_chars=sum(map(len, pages)), page_texts=len(pages),
        urls_fetched=len(evidence.get('fetched', {})), max_root_prompt_chars=max((c['prompt_chars'] for c in root_calls if 'prompt_chars' in c), default=None),
        rlms=[dict(trace_line=e['line'], **e['details'], repl_blocks=sum(b['details'].get('rlm_id') == e['details']['rlm_id'] for b in repl)
                   if 'rlm_id' in e['details'] else None) for e in rlms],
        batches=batches, issues=checks.get('issues', []), signals=checks.get('signals', []),
        issues_by_type=dict(Counter(x['type'] for x in checks.get('issues', []))),
        signals_by_type=dict(Counter(x['type'] for x in checks.get('signals', []))),
        uncited_cells=len({i.split(':', 1)[0] for i in result.get('uncited', [])}), uncited=result.get('uncited', []),
        rows=len(result.get('output', {}).get('rows', [])),
        failed_fetches=sum(f['status'] == 'failed' for f in evidence.get('fetches', [])),
        failed_fetch_attempts=sum(f['operation'] == 'fetch' for f in evidence.get('failures', [])),
        empty_searches=sum(s['hits'] == 0 for s in evidence.get('searches', [])), errors=[e for e in trace if e['details'].get('error')],
        refine=[e for e in trace if e['component'] == 'Refine'],
        harness_edits=[e for e in trace if e['component'] == 'Harness' and e['event'] in ('create.end', 'update.end', 'delete.end')],
        retrieved=[e for e in trace if e['component'] == 'Harness' and e['event'] == 'retrieve.end'], repl=repl)
    absent = {
        'codex_calls.jsonl': ('codex_calls', 'calls_by_purpose', 'codex_retries'),
        'evidence.json': ('page_chars', 'page_texts', 'urls_fetched', 'failed_fetches', 'failed_fetch_attempts', 'empty_searches'),
        'self_check.json': ('issues', 'signals', 'issues_by_type', 'signals_by_type'),
        'agent_result.json': ('rows', 'uncited_cells', 'uncited'),
    }
    for filename, keys in absent.items():
        if not (task / filename).exists():
            for key in keys:
                metrics[key] = None
                unavailable[key] = f'{filename}_not_archived'
    for key in ('wall_s', 'active_span_s'):
        if metrics[key] is None:
            unavailable[key] = 'complete_research_timing_not_archived'
    if not (task / 'codex_calls.jsonl').exists() and not (task / 'codex_attempts').is_dir():
        metrics['codex_attempts'] = None
        unavailable['codex_attempts'] = 'call_and_attempt_records_not_archived'
    if metrics['max_root_prompt_chars'] is None:
        unavailable['max_root_prompt_chars'] = 'root_prompt_measurement_not_archived'
    if not (run / 'trace.jsonl').exists():
        for key in ('rlms', 'batches', 'errors', 'refine', 'harness_edits', 'retrieved', 'repl'):
            metrics[key] = None
            unavailable[key] = 'trace.jsonl_not_archived'
    metrics['unavailable'] = unavailable
    return metrics


TASK_MARKERS = {'trajectory.jsonl', 'codex_calls.jsonl', 'task_state.json', 'baseline_response.json',
                'root_prompt.txt', 'prompt.txt', 'evidence.json'}


def task_directories(run):
    if any((run / name).is_file() for name in TASK_MARKERS):
        return [run]
    tasks = {path for path in run.iterdir() if path.is_dir() and
             (any((path / name).is_file() for name in TASK_MARKERS) or (path / 'codex_attempts').is_dir())}
    manifest = read(run / 'research.json', {})
    if not isinstance(manifest, dict):
        raise ArchiveCorruptionError(f'{run / "research.json"}: manifest must be an object')
    if manifest.get('task_id'):
        task_id = manifest['task_id']
        if not isinstance(task_id, str) or Path(task_id).name != task_id or task_id in ('.', '..'):
            raise ArchiveCorruptionError(f'{run / "research.json"}: invalid task_id')
        tasks.add(run / task_id)
    return sorted(tasks)


def audit_run(run_dir, excerpt_trace_lines=None):
    run = Path(run_dir).resolve()
    result = dict(run_id=run.name, run_path=str(run), tasks=[], errors=[])
    if not run.is_dir():
        result['unavailable_reason'] = 'run_directory_not_present'
        return result
    try:
        tasks = task_directories(run)
    except ArchiveCorruptionError as error:
        result['errors'].append(str(error))
        return result
    for task in tasks:
        try:
            result['tasks'].append(audit_task(task, run if task != run else run.parent, excerpt_trace_lines))
        except ArchiveCorruptionError as error:
            result['errors'].append(str(error))
    if not tasks:
        result['unavailable_reason'] = 'no_task_archives_discovered'
    result['status'] = 'error' if result['errors'] else ('partial' if not tasks or any(t['status'] == 'partial' for t in result['tasks']) else 'available')
    return result


def write_task(result, output_dir, label):
    if Path(label).name != label or label in ('.', '..'):
        raise ValueError('label must be a filename component')
    output_dir = Path(output_dir)
    task = Path(result['task_path'])
    if output_dir.resolve().is_relative_to(task):
        raise ValueError('derived outputs must be outside the task archive')
    output_dir.mkdir(parents=True, exist_ok=True)
    full = result['_largest_prompt_text']
    if full is not None:
        (output_dir / f'{label}.largest_root_prompt.txt').write_text(full)
    public = {key: value for key, value in result.items() if not key.startswith('_') and key != 'metrics'}
    (output_dir / f'{label}.audit.json').write_text(json.dumps(public, ensure_ascii=False, indent=2) + '\n')
    (output_dir / f'{label}.metrics.json').write_text(json.dumps(result['metrics'], ensure_ascii=False, indent=2) + '\n')


def discover_runs(search_root, output_dir=None):
    """Discover all task archives, including nested isolated workspaces and streams."""
    root = Path(search_root).resolve()
    excluded = Path(output_dir).resolve() if output_dir else None
    runs = set()
    for path in root.rglob('*'):
        if excluded and path.is_relative_to(excluded):
            continue
        if path.is_file() and path.name in ('research.json', 'stream.json'):
            runs.add(path.parent)
        elif path.is_file() and path.name in TASK_MARKERS:
            runs.add(path.parent.parent)
        elif path.is_dir() and path.name == 'codex_attempts':
            runs.add(path.parent.parent)
    return sorted(runs)


def audit_all(search_root, output_dir):
    output_dir = Path(output_dir).resolve()
    index = dict(search_root=str(Path(search_root).resolve()), runs=[])
    for run in discover_runs(search_root, output_dir):
        result = audit_run(run)
        target = output_dir / (run.name + '-' + sha(str(run))[:12])
        for task in result['tasks']:
            write_task(task, target, Path(task['task_path']).name)
        entry = {key: value for key, value in result.items() if key != 'tasks'}
        entry['tasks'] = [dict(task_path=task['task_path'], status=task['status'],
            largest_prompt_chars=task['largest_prompt']['total'], largest_prompt_sha256=task['largest_prompt']['sha256'],
            audit_path=str(target / (Path(task['task_path']).name + '.audit.json'))) for task in result['tasks']]
        index['runs'].append(entry)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n')
    return index


def audit(label, run_id, output_dir, excerpt_trace_lines=None):
    """Compatibility entry point for the original report helper."""
    run = Path(run_id)
    if not run.is_dir():
        run = Path.cwd() / 'runs' / run_id
    result = audit_run(run, excerpt_trace_lines)
    for task in result['tasks']:
        write_task(task, output_dir, label if len(result['tasks']) == 1 else f'{label}.{Path(task["task_path"]).name}')
    if result['errors']:
        raise ArchiveCorruptionError('\n'.join(result['errors']))
    return result['tasks'][0] if len(result['tasks']) == 1 else result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir', nargs='?', type=Path)
    parser.add_argument('--all', dest='search_root', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    if bool(args.run_dir) == bool(args.search_root):
        parser.error('provide either RUN_DIR or --all ARCHIVE_ROOT')
    if args.search_root:
        result = audit_all(args.search_root, args.output_dir)
        print(json.dumps(dict(runs=len(result['runs']), errors=sum(bool(run['errors']) for run in result['runs']))))
        return int(any(run['errors'] for run in result['runs']))
    result = audit_run(args.run_dir)
    for task in result['tasks']:
        write_task(task, args.output_dir, Path(task['task_path']).name)
    summary = {key: value for key, value in result.items() if key != 'tasks'}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / 'index.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary))
    return int(bool(result['errors']))


if __name__ == '__main__':
    sys.exit(main())
