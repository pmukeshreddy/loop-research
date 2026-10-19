import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from loop_research.codex_backend import INSTRUCTION
from loop_research.rlm_codex_client import transcript


def module():
    from loop_research import archive_audit
    return archive_audit


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False))


def write_lines(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))


def archive(tmp_path, *, task_name='task-one', trace=False):
    run = tmp_path / 'research-fixture'
    task = run / task_name
    write_json(run / 'research.json', {'run_id': run.name, 'task_id': task_name,
                                     'status': 'interrupted'})
    task.mkdir(exist_ok=True)
    brief = 'TASK\nA research question\nSPEC\n{"columns":["value"],"keys":["value"]}\n\nOTHER\nKeep exact evidence.'
    (task / 'root_prompt.txt').write_text(brief)
    (task / 'prompt.txt').write_text(brief)
    messages = [{'role': 'system', 'content': 'Research system.'},
                {'role': 'user', 'content': 'Answer: ' + brief}]
    prompt = transcript(messages)
    response = '```repl\nprint("done")\n```'
    model = {'type': 'model', 'purpose': 'root', 'prompt': prompt, 'response': response}
    call = {'call_id': 'first', 'purpose': 'root', 'attempt': 0, 'error': None,
            'prompt_chars': len(INSTRUCTION + prompt),
            'prompt_sha256': hashlib.sha256((INSTRUCTION + prompt).encode()).hexdigest(),
            'response_chars': len(response), 'duration_s': 1, 'exit_code': 0}
    iteration = {'type': 'worker_iteration', 'event': {'iteration': 1,
        'prompt': messages, 'response': response, 'code_blocks': [{'code': 'print("done")',
        'result': {'stdout': 'done\n', 'stderr': '', 'locals': {}}}]}}
    write_lines(task / 'trajectory.jsonl', [model, iteration])
    write_lines(task / 'codex_calls.jsonl', [call])
    write_json(task / 'evidence.json', {'fetched': {}, 'fetches': []})
    if trace:
        write_lines(run / 'trace.jsonl', [])
    return run, task, model, call, iteration


def test_unfinished_largest_root_keeps_exact_size_hash_and_text_without_partition(tmp_path):
    run, task, model, call, iteration = archive(tmp_path)
    larger = {**model, 'prompt': model['prompt'] + '\n' + 'retained evidence ' * 200}
    full = INSTRUCTION + larger['prompt']
    second = {**call, 'call_id': 'last', 'prompt_chars': len(full),
              'prompt_sha256': hashlib.sha256(full.encode()).hexdigest()}
    write_lines(task / 'trajectory.jsonl', [model, iteration, larger])
    write_lines(task / 'codex_calls.jsonl', [call, second])
    result = module().audit_task(task, run)
    assert result['largest_prompt']['total'] == len(full)
    assert result['largest_prompt']['sha256'] == second['prompt_sha256']
    assert result['largest_prompt']['trajectory_line'] == 3
    assert result['largest_prompt']['parts'] is None
    assert result['largest_prompt']['partition_unavailable_reason'] == 'worker_iteration_not_archived'
    assert result['_largest_prompt_text'] == full
    assert result['metrics']['codex_calls'] == 2


def test_dispatched_larger_input_without_model_body_is_not_replaced_by_smaller_input(tmp_path):
    run, task, model, call, iteration = archive(tmp_path)
    dispatched = {**call, 'call_id': 'pending', 'prompt_chars': 40000,
                  'prompt_sha256': 'a' * 64}
    write_json(task / 'codex_attempts' / 'pending.json', dispatched)
    result = module().audit_task(task, run)
    assert result['largest_prompt']['total'] == 40000
    assert result['largest_prompt']['sha256'] == 'a' * 64
    assert result['_largest_prompt_text'] is None
    assert result['largest_prompt']['text_unavailable_reason']
    assert result['overlap']['covered_chars'] is None
    assert result['overlap']['unavailable_reason']
    assert result['metrics']['codex_calls'] == 1
    assert result['metrics']['codex_attempts'] == 2


def test_missing_trace_does_not_erase_verified_prompt_or_iteration(tmp_path):
    run, task, model, call, iteration = archive(tmp_path)
    result = module().audit_task(task, run)
    assert result['largest_prompt']['total'] == call['prompt_chars']
    assert sum(result['largest_prompt']['parts'].values()) == call['prompt_chars']
    assert result['largest_prompt']['trace_line'] is None
    assert result['largest_prompt']['trace_unavailable_reason']
    assert result['iterations'][0]['iteration'] == 1
    assert result['iterations'][0]['trace_link'] is None
    assert result['blocks'][0]['stdout'] == 'done\n'
    assert result['metrics']['wall_s'] is None
    assert result['metrics']['unavailable']['wall_s']


def test_early_manifest_only_archive_marks_metrics_unavailable(tmp_path):
    run = tmp_path / 'early'
    write_json(run / 'research.json', {'task_id': 'pending', 'status': 'running'})
    result = module().audit_run(run)
    task = result['tasks'][0]
    assert task['largest_prompt']['total'] is None
    assert task['largest_prompt']['unavailable_reason']
    assert task['metrics']['codex_calls'] is None
    assert task['metrics']['page_chars'] is None
    assert task['overlap']['fraction'] is None
    assert task['overlap']['unavailable_reason']


def test_legacy_task_without_manifest_or_trace_retains_known_calls_and_text(tmp_path):
    run, task, model, call, iteration = archive(tmp_path)
    (run / 'research.json').unlink()
    (task / 'root_prompt.txt').unlink()
    result = module().audit_run(run)
    assert len(result['tasks']) == 1
    assert result['tasks'][0]['largest_prompt']['total'] == call['prompt_chars']
    assert result['tasks'][0]['largest_prompt']['initial_input_path'].endswith('prompt.txt')
    assert result['tasks'][0]['metrics']['codex_calls'] == 1


def test_missing_initial_brief_keeps_largest_input_but_marks_partition_unavailable(tmp_path):
    run, task, model, call, iteration = archive(tmp_path)
    (task / 'root_prompt.txt').unlink()
    (task / 'prompt.txt').unlink()
    result = module().audit_task(task, run)
    assert result['largest_prompt']['total'] == call['prompt_chars']
    assert result['largest_prompt']['parts'] is None
    assert result['largest_prompt']['partition_unavailable_reason'] == 'initial_task_input_not_archived'


def test_run_discovers_every_task_directory_not_only_manifest_task(tmp_path):
    run, task, *_ = archive(tmp_path)
    archive(tmp_path, task_name='task-two')
    result = module().audit_run(run)
    assert {Path(r['task_path']).name for r in result['tasks']} == {'task-one', 'task-two'}
    assert all(r['metrics']['codex_calls'] == 1 for r in result['tasks'])


def test_empty_explicit_run_is_reported_without_fabricated_task(tmp_path):
    run = tmp_path / 'empty'
    run.mkdir()
    result = module().audit_run(run)
    assert result['tasks'] == []
    assert result['unavailable_reason'] == 'no_task_archives_discovered'


def test_malformed_json_is_a_named_corruption_error_with_file_and_line(tmp_path):
    run, task, *_ = archive(tmp_path)
    (task / 'trajectory.jsonl').write_text('{"type":\n')
    with pytest.raises(module().ArchiveCorruptionError, match=r'trajectory.jsonl:1'):
        module().audit_task(task, run)


def test_inconsistent_archived_prompt_hash_is_reported_as_corruption(tmp_path):
    run, task, model, call, iteration = archive(tmp_path)
    write_lines(task / 'codex_calls.jsonl', [{**call, 'prompt': 'corrupted input body'}])
    with pytest.raises(module().ArchiveCorruptionError, match='prompt'):
        module().audit_task(task, run)


def test_exact_50_character_coverage_survives_unfinished_root_iteration(tmp_path):
    run, task, model, call, iteration = archive(tmp_path)
    page = 'Case-sensitive exact evidence with whitespace. ' * 4
    larger = {**model, 'prompt': model['prompt'] + '\n' + page}
    full = INSTRUCTION + larger['prompt']
    second = {**call, 'call_id': 'last', 'prompt_chars': len(full),
              'prompt_sha256': hashlib.sha256(full.encode()).hexdigest()}
    write_lines(task / 'trajectory.jsonl', [model, iteration, larger])
    write_lines(task / 'codex_calls.jsonl', [call, second])
    write_json(task / 'evidence.json', {'fetched': {'https://example.invalid/evidence': [page]}, 'fetches': []})
    overlap = module().audit_task(task, run)['overlap']
    assert overlap['ngram_chars'] == 50
    assert overlap['total_chars'] == len(page)
    assert overlap['covered_chars'] == len(page)
    assert overlap['fraction'] == 1
    assert overlap['fully_present_texts'] == 1


def test_bulk_audit_reports_corruption_and_keeps_other_runs_without_writing_inputs(tmp_path):
    good_root = tmp_path / 'archives' / 'one'
    good, task, *_ = archive(good_root)
    bad, bad_task, *_ = archive(tmp_path / 'archives' / 'two')
    (bad_task / 'trajectory.jsonl').write_text('invalid-json\n')
    original = {str(p): p.read_bytes() for p in (tmp_path / 'archives').rglob('*') if p.is_file()}
    output = tmp_path / 'audit_all'
    result = module().audit_all(tmp_path / 'archives', output)
    assert len(result['runs']) == 2
    assert any(r['errors'] for r in result['runs'])
    assert any(not r['errors'] for r in result['runs'])
    assert (output / 'index.json').exists()
    assert {str(p): p.read_bytes() for p in (tmp_path / 'archives').rglob('*') if p.is_file()} == original
    assert list(output.rglob('*.largest_root_prompt.txt'))


def test_retry_with_identical_verified_input_keeps_exact_coverage_and_attempt_count(tmp_path):
    run, task, model, call, iteration = archive(tmp_path)
    retry = {**call, 'call_id': 'failed-first', 'error': 'transport', 'attempt': 0}
    write_lines(task / 'codex_calls.jsonl', [retry, {**call, 'attempt': 1}])
    result = module().audit_task(task, run)
    assert result['_largest_prompt_text'] == INSTRUCTION + model['prompt']
    assert result['overlap']['covered_chars'] == 0
    assert 'unavailable_reason' not in result['overlap']
    assert result['metrics']['codex_attempts'] == 2
    assert result['metrics']['codex_retries'] == 1


def test_unmatched_iteration_retains_record_and_output_with_explicit_linkage_gap(tmp_path):
    run, task, model, call, iteration = archive(tmp_path)
    write_lines(task / 'trajectory.jsonl', [iteration])
    result = module().audit_task(task, run)
    assert len(result['iterations']) == 1
    assert result['iterations'][0]['trajectory_line'] == 1
    assert result['iterations'][0]['model_trajectory_line'] is None
    assert result['iterations'][0]['model_unavailable_reason']
    assert result['blocks'][0]['stdout'] == 'done\n'


def test_legacy_trace_without_rlm_ids_preserves_prompt_and_marks_trace_linkage_missing(tmp_path):
    run, task, model, call, iteration = archive(tmp_path)
    write_lines(run / 'trace.jsonl', [
        {'component': 'RLM iteration', 'event': 'iteration.start', 'details': {'iteration': 1}},
        {'component': 'RLM iteration', 'event': 'iteration.end', 'details': {'iteration': 1}},
        {'component': 'RLM', 'event': 'completion.end', 'details': {'iterations': 1}},
        {'component': 'REPL', 'event': 'code.end', 'details': {'first_lines': 'print("done")'}},
    ])
    result = module().audit_task(task, run)
    assert result['largest_prompt']['total'] == call['prompt_chars']
    assert result['iterations'][0]['trace_link'] is None
    assert result['iterations'][0]['trace_unavailable_reason']
    assert len(result['rlms']) == 1
    assert result['rlms'][0]['repl_blocks'] is None
    assert result['rlms'][0]['linkage_unavailable_reason']


def test_discovery_includes_nested_workspaces_and_explicit_check_archives(tmp_path):
    run, *_ = archive(tmp_path / 'isolated' / 'runs')
    check = tmp_path / 'checks' / 'manual' / 'task'
    write_lines(check / 'codex_calls.jsonl', [])
    stream = tmp_path / 'runs' / 'stream-legacy'
    write_json(stream / 'stream.json', {'status': 'interrupted'})
    found = module().discover_runs(tmp_path)
    assert set(found) == {run.resolve(), check.parent.resolve(), stream.resolve()}


def test_early_archive_does_not_report_missing_attempts_or_subcalls_as_zero(tmp_path):
    run = tmp_path / 'early'
    write_json(run / 'research.json', {'task_id': 'pending', 'status': 'running'})
    result = module().audit_run(run)['tasks'][0]
    assert result['metrics']['codex_attempts'] is None
    assert result['metrics']['unavailable']['codex_attempts']
    assert result['metrics']['max_root_prompt_chars'] is None
    assert result['metrics']['unavailable']['max_root_prompt_chars']
    assert result['subcall_count'] is None
    assert result['subcalls_unavailable_reason']


def test_invalid_manifest_shape_is_reported_as_corruption_in_bulk(tmp_path):
    run, *_ = archive(tmp_path)
    write_json(run / 'research.json', ['not an object'])
    result = module().audit_run(run)
    assert result['errors']
    assert 'research.json' in result['errors'][0]


def test_module_cli_writes_explicit_task_and_retains_input_files(tmp_path):
    run, task, model, call, iteration = archive(tmp_path)
    output = tmp_path / 'derived'
    completed = subprocess.run([sys.executable, '-m', 'loop_research.archive_audit', str(run),
        '--output-dir', str(output)], capture_output=True, text=True,
        env={**__import__('os').environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'src')})
    assert completed.returncode == 0, completed.stderr
    saved = json.loads((output / 'task-one.audit.json').read_text())
    assert saved['largest_prompt']['total'] == call['prompt_chars']
    assert (output / 'task-one.largest_root_prompt.txt').read_text() == INSTRUCTION + model['prompt']


def test_multi_task_unattributed_trace_is_preserved_at_run_scope_only(tmp_path):
    run, task, *_ = archive(tmp_path)
    archive(tmp_path, task_name='task-two')
    trace = [
        {'component': 'RLM', 'event': 'completion.end', 'details': {'rlm_id': 'one', 'iterations': 2}},
        {'component': 'RLM', 'event': 'completion.end', 'details': {'rlm_id': 'two', 'iterations': 3}},
        {'component': 'Worker', 'event': 'run.end', 'details': {'exit_code': 0}},
        {'component': 'Refine', 'event': 'run.end', 'details': {'error': 'other task'}},
    ]
    write_lines(run / 'trace.jsonl', trace)
    result = module().audit_task(task, run)
    assert result['rlms'] is None
    assert result['worker_end'] is None
    assert result['refine'] is None
    assert result['trace_unavailable_reason'] == 'multi_task_trace_ownership_not_archived'
    assert result['metrics']['rlms'] is None
    assert result['metrics']['errors'] is None
    assert result['metrics']['unavailable']['rlms']
    assert len(result['run_trace']['events']) == len(trace)
    assert result['run_trace']['scope'] == 'run'


def test_multi_task_explicit_trace_ownership_filters_other_tasks(tmp_path):
    run, task, *_ = archive(tmp_path)
    archive(tmp_path, task_name='task-two')
    write_lines(run / 'trace.jsonl', [
        {'component': 'RLM', 'event': 'completion.end', 'details': {'task_id': 'task-one', 'rlm_id': 'one', 'iterations': 2}},
        {'component': 'RLM', 'event': 'completion.end', 'details': {'task_id': 'task-two', 'rlm_id': 'two', 'iterations': 3}},
    ])
    result = module().audit_task(task, run)
    assert [rlm['rlm_id'] for rlm in result['rlms']] == ['one']
    assert [rlm['rlm_id'] for rlm in result['metrics']['rlms']] == ['one']


def test_interrupted_utf8_record_is_reported_without_aborting_bulk_audit(tmp_path):
    good, *_ = archive(tmp_path / 'good')
    bad, task, *_ = archive(tmp_path / 'bad')
    (task / 'trajectory.jsonl').write_bytes(b'{"type":"\xe2\x82')
    result = module().audit_all(tmp_path, tmp_path / 'derived')
    assert len(result['runs']) == 2
    errors = [error for run in result['runs'] for error in run['errors']]
    assert len(errors) == 1
    assert 'trajectory.jsonl' in errors[0]


def test_concurrent_identical_prompts_match_response_integrity_before_consuming_calls(tmp_path):
    run, task, model, call, iteration = archive(tmp_path)
    one = {**model, 'purpose': 'sub', 'response': 'one'}
    two = {**one, 'response': 'second response'}
    first = {**call, 'call_id': 'one', 'purpose': 'sub', 'response_chars': len(one['response'])}
    second = {**first, 'call_id': 'two', 'response_chars': len(two['response'])}
    write_lines(task / 'trajectory.jsonl', [two, one])
    write_lines(task / 'codex_calls.jsonl', [first, second])
    result = module().audit_task(task, run)
    assert [sub['call_id'] for sub in result['subcalls']] == ['two', 'one']
    assert result['subcall_count'] == 2


def test_indistinguishable_concurrent_calls_do_not_claim_unique_call_identity(tmp_path):
    run, task, model, call, iteration = archive(tmp_path)
    sub = {**model, 'purpose': 'sub'}
    first = {**call, 'purpose': 'sub', 'call_id': 'one'}
    write_lines(task / 'trajectory.jsonl', [sub, sub])
    write_lines(task / 'codex_calls.jsonl', [first, {**first, 'call_id': 'two'}])
    result = module().audit_task(task, run)
    assert all(sub['call_id'] is None for sub in result['subcalls'])
    assert all(sub['call_linkage_unavailable_reason'] == 'indistinguishable_archived_calls' for sub in result['subcalls'])
    assert all(sub['candidate_call_ids'] == ['one', 'two'] for sub in result['subcalls'])
    assert result['subcall_count'] == 2


def nested_iteration_archive(tmp_path, *, standalone_child=False, child_worker_start=1):
    """Archive call nesting without using the worker's shared counter as identity."""
    run, task, _, _, _ = archive(tmp_path)
    brief = (task / 'root_prompt.txt').read_text()
    page = 'Exact retained page evidence with a sufficiently long repeated passage. ' * 2
    trajectory, calls, trace, expected = [], [], [], []
    root_messages = [{'role': 'system', 'content': 'Research system.'},
                     {'role': 'user', 'content': 'Answer: ' + brief}]
    child_messages = [{'role': 'system', 'content': 'Child system.'},
                      {'role': 'user', 'content': 'Inspect this supplied evidence: ' + page}]

    def emit(component, event, **details):
        trace.append(dict(component=component, event=event, details=details))
        return len(trace)

    def start_turn(rlm_id, ordinal, worker_ordinal, messages, codes, stdout='repeat\n'):
        depth = int(rlm_id == 'child')
        identity = dict(rlm_id=rlm_id, parent_rlm_id='root' if depth else None, depth=depth)
        start = emit('RLM iteration', 'iteration.start', **identity, iteration=ordinal)
        prompt = transcript(messages)
        response = '\n'.join('```repl\n' + code + '\n```' for code in codes)
        full = INSTRUCTION + prompt
        call_id = f'{rlm_id}-{ordinal}'
        call = dict(call_id=call_id, purpose='sub' if depth else 'root', attempt=0,
                    error=None, exit_code=0, prompt_chars=len(full),
                    prompt_sha256=hashlib.sha256(full.encode()).hexdigest(),
                    response_chars=len(response))
        calls.append(call)
        emit('Codex', 'exec.end', call_id=call_id)
        trajectory.append(dict(type='model', purpose=call['purpose'], prompt=prompt, response=response))
        model_line = len(trajectory)
        first_code_start = emit('REPL', 'code.start', **identity, first_lines=codes[0])
        return dict(identity=identity, ordinal=ordinal, worker_ordinal=worker_ordinal,
                    messages=list(messages), codes=codes, stdout=stdout, response=response,
                    call=call, start=start, model_line=model_line, first_code_start=first_code_start)

    def finish_turn(turn, messages):
        ends, starts, code_blocks = [], [], []
        for index, code in enumerate(turn['codes']):
            starts.append(turn['first_code_start'] if index == 0 else
                          emit('REPL', 'code.start', **turn['identity'], first_lines=code))
            ends.append(emit('REPL', 'code.end', **turn['identity'], first_lines=code,
                             stdout=turn['stdout'][:1000], error=None))
            code_blocks.append(dict(code=code, result=dict(stdout=turn['stdout'], stderr='', locals={})))
        end = emit('RLM iteration', 'iteration.end', **turn['identity'], iteration=turn['ordinal'])
        trajectory.append(dict(type='worker_iteration', event=dict(iteration=turn['worker_ordinal'],
            prompt=turn['messages'], response=turn['response'], code_blocks=code_blocks)))
        expected.append(dict(**turn, trajectory_line=len(trajectory), end=end, code_ends=ends, code_starts=starts))
        messages.extend([{'role': 'assistant', 'content': turn['response']},
                         {'role': 'user', 'content': 'REPL output: ' + turn['stdout']}])

    if not standalone_child:
        finish_turn(start_turn('root', 1, 1, root_messages, ['print(context)'], stdout=page), root_messages)
        parent = start_turn('root', 2, 3, root_messages, ['child = rlm_query(context)'])
    for index in range(2):
        finish_turn(start_turn('child', index + 1, child_worker_start + index,
                               child_messages, ['print("repeat")']), child_messages)
    emit('RLM', 'completion.end', rlm_id='child', parent_rlm_id='root', depth=1, iterations=2)
    if not standalone_child:
        finish_turn(parent, root_messages)
        # Shared logger labels remain offset after child completion. Repeated
        # code also appears inside the child and twice in the same root turn.
        finish_turn(start_turn('root', 3, 4, root_messages, ['print("repeat")'] * 2), root_messages)
        finish_turn(start_turn('root', 4, 5, root_messages, ['print("repeat")']), root_messages)
        emit('RLM', 'completion.end', rlm_id='root', parent_rlm_id=None, depth=0, iterations=4)
    write_lines(task / 'trajectory.jsonl', trajectory)
    write_lines(task / 'codex_calls.jsonl', calls)
    write_lines(run / 'trace.jsonl', trace)
    write_json(task / 'evidence.json', {'fetched': {'https://example.invalid/page': [page]}, 'fetches': []})
    return run, task, expected, calls, page


def assert_iteration_links(result, expected):
    by_model = {record['model_trajectory_line']: record for record in result['iterations']}
    assert set(by_model) == {turn['model_line'] for turn in expected}
    for turn in expected:
        record = by_model[turn['model_line']]
        assert record['rlm_id'] == turn['identity']['rlm_id']
        assert record['depth'] == turn['identity']['depth']
        assert record['parent_rlm_id'] == turn['identity']['parent_rlm_id']
        assert record['iteration'] == turn['ordinal']
        assert record['worker_iteration'] == turn['worker_ordinal']
        assert record['trajectory_line'] == turn['trajectory_line']
        assert record['trace_start_line'] == turn['start']
        assert record['trace_end_line'] == turn['end']
        assert record['prompt_sha256'] == turn['call']['prompt_sha256']
        blocks = [block for block in result['blocks'] if block['model_trajectory_line'] == turn['model_line']]
        assert [block['trace_line'] for block in blocks] == turn['code_ends']
        assert [block['code_start_trace_line'] for block in blocks] == turn['code_starts']
        assert [block['code'] for block in blocks] == turn['codes']
        assert all(block['stdout'] == turn['stdout'] for block in blocks)


def test_child_and_repeated_post_child_blocks_join_by_call_span_not_shared_counter(tmp_path):
    run, task, expected, calls, page = nested_iteration_archive(tmp_path)
    original = {path: path.read_bytes() for path in run.rglob('*') if path.is_file()}
    result = module().audit_task(task, run)
    counts = {item['rlm_id']: (len(item['iteration_records']), item['repl_blocks']) for item in result['rlms']}
    assert counts == {'root': (4, 5), 'child': (2, 2)}
    assert_iteration_links(result, expected)
    largest = result['largest_prompt']
    assert largest['iteration'] == 4
    assert largest['worker_iteration'] == 5
    assert largest['total'] == calls[-1]['prompt_chars']
    assert largest['sha256'] == calls[-1]['prompt_sha256']
    assert sum(largest['parts'].values()) == largest['total']
    assert hashlib.sha256(result['_largest_prompt_text'].encode()).hexdigest() == largest['sha256']
    assert result['overlap']['ngram_chars'] == 50
    assert result['overlap']['covered_chars'] == result['overlap']['total_chars'] == len(page)
    assert {path: path.read_bytes() for path in original} == original


@pytest.mark.parametrize('worker_start', [1, 7])
def test_standalone_child_archive_uses_own_spans_without_parent_records(tmp_path, worker_start):
    run, task, expected, _, _ = nested_iteration_archive(
        tmp_path, standalone_child=True, child_worker_start=worker_start)
    result = module().audit_task(task, run)
    assert_iteration_links(result, expected)
    assert len(result['rlms']) == 1
    assert result['rlms'][0]['rlm_id'] == 'child'
    assert result['rlms'][0]['repl_blocks'] == 2
    assert all(sub['is_child_rlm_turn'] for sub in result['subcalls'])
    assert result['largest_prompt']['total'] is None


def test_overlapping_concurrent_child_spans_do_not_claim_arbitrary_identity(tmp_path):
    run, task, expected, _, _ = nested_iteration_archive(tmp_path, standalone_child=True)
    trace = [json.loads(line) for line in (run / 'trace.jsonl').read_text().splitlines()]
    # A sibling's long-running turn overlaps both calls in this child's archive.
    # The backend events carry no RLM id, so depth/time cannot distinguish them.
    sibling = dict(rlm_id='sibling', parent_rlm_id='root', depth=1, iteration=1)
    trace.insert(0, dict(component='RLM iteration', event='iteration.start', details=sibling))
    trace.append(dict(component='RLM iteration', event='iteration.end', details=sibling))
    write_lines(run / 'trace.jsonl', trace)
    result = module().audit_task(task, run)
    for record, turn in zip(result['iterations'], expected):
        assert record['rlm_id'] is None
        assert record['trace_link'] is None
        assert record['trace_unavailable_reason'] == 'ambiguous_overlapping_iteration_spans'
        assert {span['rlm_id'] for span in record['candidate_iteration_spans']} == {'child', 'sibling'}
        assert all(span['depth'] == 1 for span in record['candidate_iteration_spans'])
        assert record['worker_iteration'] == turn['worker_ordinal']
        assert record['model_trajectory_line'] == turn['model_line']
        assert record['backend_chars'] == turn['call']['prompt_chars']
        assert record['prompt_sha256'] == turn['call']['prompt_sha256']
    assert all(block['trace_line'] is None for block in result['blocks'])
    assert [block['stdout'] for block in result['blocks']] == [turn['stdout'] for turn in expected]
