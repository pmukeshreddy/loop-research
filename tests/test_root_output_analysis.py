"""Reporting regressions use only synthetic, completed on-disk archives."""
import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def helper():
    path = Path(__file__).resolve().parents[1] / 'runs' / 'round2' / 'root_analysis.py'
    spec = importlib.util.spec_from_file_location('root_output_analysis', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def archived_output(tmp_path, helper, *, multiple=False):
    task = tmp_path / 'run' / 'task'
    task.mkdir(parents=True)
    (task.parent / 'research.json').write_text(json.dumps({'status': 'complete'}))
    (task / 'task_state.json').write_text(json.dumps({'phase': 'complete'}))
    evidence = 'Exact case-sensitive evidence in the retained output. ' * 2
    source_blocks = [{'code': 'print(page)\nassert False',
        'result': {'stdout': evidence, 'stderr': '\nAssertionError: validation rejected', 'locals': {}}}]
    if multiple:
        source_blocks.append({'code': 'print("recovered")',
            'result': {'stdout': 'recovered\n', 'stderr': '', 'locals': {}}})
    initial = [{'role': 'system', 'content': 'system'}, {'role': 'user', 'content': 'task'}]
    response = '\n'.join('```repl\n' + block['code'] + '\n```' for block in source_blocks)
    chunks = []
    for index, block in enumerate(source_blocks, 1):
        header = f'REPL output (block {index}):' if multiple else 'REPL output:'
        chunks.append(header + '\n\n' + block['result']['stdout'] + block['result']['stderr'] + '\nREPL variables: []\n')
    formatted = '\n'.join(chunks)
    messages = initial + [{'role': 'assistant', 'content': response}, {'role': 'user', 'content': formatted}]
    prompt = json.dumps(messages)
    records = [
        {'type': 'model', 'purpose': 'root', 'prompt': 'initial', 'response': response},
        {'type': 'worker_iteration', 'event': {'prompt': initial, 'response': response, 'code_blocks': source_blocks}},
        {'type': 'model', 'purpose': 'root', 'prompt': prompt, 'response': 'done'},
        {'type': 'worker_iteration', 'event': {'prompt': messages, 'response': 'done', 'code_blocks': []}},
    ]
    trajectory_path = task / 'trajectory.jsonl'
    trajectory_path.write_text(''.join(json.dumps(record) + '\n' for record in records))
    (task / 'evidence.json').write_text(json.dumps({'fetched': {'https://example.invalid/page': [evidence]}}))
    full = 'backend\n' + prompt
    prompt_path = tmp_path / 'case.largest_root_prompt.txt'
    prompt_path.write_text(full)
    audit_blocks = [{'trajectory_line': 2, 'trace_line': index * 10, 'code': block['code'],
                     'stdout': block['result']['stdout'], 'code_trace_link': f'trace:{index * 10}',
                     'trajectory_link': str(trajectory_path) + ':2'}
                    for index, block in enumerate(source_blocks, 1)]
    audit = {'run_id': 'fixture', 'task_path': str(task),
        'largest_prompt': {'trajectory_line': 3, 'iteration_trajectory_line': 4, 'sha256': helper.digest(full),
                           'total': len(full), 'parts': {'repl_output': len(formatted)}},
        'overlap': {'ngram_chars': 50, 'total_chars': len(evidence), 'covered_chars': len(evidence),
                    'texts': [{'full_text_in_root': True}]},
        'blocks': audit_blocks,
        'iterations': [{'trajectory_line': 2, 'iteration': 1, 'rlm_id': 'root', 'trace_link': 'trace:30'}]}
    audit_path = tmp_path / 'case.audit.json'
    audit_path.write_text(json.dumps(audit))
    return audit_path, prompt_path, records, audit, source_blocks, formatted


def test_nonempty_stderr_comes_from_original_trajectory_and_preserves_criterion(tmp_path, helper):
    audit_path, prompt_path, records, audit, blocks, formatted = archived_output(tmp_path, helper)
    result = helper.analyze(audit_path, prompt_path)
    stderr = blocks[0]['result']['stderr']
    assert result['output_totals']['raw_stderr_chars'] == len(stderr)
    assert result['outputs'][0]['blocks'][0]['stderr_chars'] == len(stderr)
    assert result['outputs'][0]['blocks'][0]['stderr_sha256'] == helper.digest(stderr)
    assert result['outputs'][0]['all_raw_streams_found_unmodified_in_order'] is True
    assert result['output_totals']['formatted_nonstream_chars'] == len(formatted) - len(blocks[0]['result']['stdout']) - len(stderr)
    assert result['parts'] == audit['largest_prompt']['parts']
    assert result['criterion']['covered_chars'] == audit['overlap']['covered_chars']
    assert result['criterion']['ngram_chars'] == 50


@pytest.mark.parametrize('damage', ['missing_stdout', 'missing_stderr', 'audit_stdout', 'audit_code', 'block_order'])
def test_missing_or_mismatched_block_evidence_is_rejected(tmp_path, helper, damage):
    audit_path, prompt_path, records, audit, blocks, formatted = archived_output(tmp_path, helper, multiple=True)
    if damage.startswith('missing_'):
        del blocks[0]['result'][damage.removeprefix('missing_')]
        task = Path(audit['task_path'])
        (task / 'trajectory.jsonl').write_text(''.join(json.dumps(record) + '\n' for record in records))
    elif damage == 'audit_stdout':
        audit['blocks'][0]['stdout'] = 'wrong stdout'
    elif damage == 'audit_code':
        audit['blocks'][0]['code'] = 'wrong code'
    else:
        audit['blocks'][0]['trace_line'], audit['blocks'][1]['trace_line'] = 20, 10
    audit_path.write_text(json.dumps(audit))
    with pytest.raises(ValueError, match='block|stdout|stderr'):
        helper.analyze(audit_path, prompt_path)


def test_multiblock_stderr_and_known_empty_stderr_are_measured_in_order(tmp_path, helper):
    audit_path, prompt_path, records, audit, blocks, formatted = archived_output(tmp_path, helper, multiple=True)
    result = helper.analyze(audit_path, prompt_path)
    assert [block['stderr_chars'] for block in result['outputs'][0]['blocks']] == [len(blocks[0]['result']['stderr']), 0]
    assert result['outputs'][0]['all_raw_streams_found_unmodified_in_order'] is True
    assert result['output_totals']['formatted_chars'] == len(formatted)
