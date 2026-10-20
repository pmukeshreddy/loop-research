"""Overflow planner archives bind complete input to actual, separately counted calls."""
import copy
import hashlib
import json

import pytest

from loop_research import archive_audit as audit
from loop_research.codex_backend import INSTRUCTION
from loop_research.refine import INSTRUCTIONS, Proposal, evidence_anchors
from loop_research.shared_text import encode_shared_text


def text(value):
    return json.dumps(value, ensure_ascii=False)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text(value))


def save_lines(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(text(value) + '\n' for value in values))


def transport(task, *, retry=False):
    expected = {'focus': None, 'candidate_inventory': [], 'entries': [],
                'trajectory': [{'result': 'complete evidence 雪 ' * 150}],
                'self_check': {'issues': [], 'signals': []}, 'max_edits': 2}
    payload = {**expected, 'evidence_index': evidence_anchors(expected)}
    schema = Proposal.model_json_schema()
    schema['properties']['edits']['maxItems'] = 2
    schema['$defs']['EvidenceRef'] = {'type': 'string', 'enum': payload['evidence_index']}
    for name in ('Candidate', 'Decision'):
        schema['$defs'][name]['properties']['evidence_refs']['items'] = {'$ref': '#/$defs/EvidenceRef'}
    wire = encode_shared_text(payload)
    wire_text = json.dumps(wire, ensure_ascii=False, separators=(',', ':'))
    proposal = {'summary': 'No supported change.', 'edits': [], 'additional_candidates': [], 'decisions': []}
    response = text(proposal)
    job = {'job_id': 'job-one', 'request_id': 'request-one', 'status': 'applied',
           'focus': None, 'candidate_inventory': [], 'snapshot': {'entries': {}},
           'observed': {key: payload[key] for key in ('trajectory', 'self_check')},
           'evidence_index': payload['evidence_index'], 'planner_schema': schema,
           'planner_prompt': INSTRUCTIONS + wire_text, 'response_text': response, 'proposal': proposal,
           'planner_representation': {'format': wire['format'], 'wire_payload_chars': len(wire_text),
               'wire_payload_sha256': digest(wire_text), 'logical_payload_chars': len(text(payload)),
               'logical_payload_sha256': digest(text(payload))},
           'planner_transport': {'kind': 'repl-context-v1', 'input_limit_chars': 1024,
               'complete_prompt_chars': len(INSTRUCTION + INSTRUCTIONS + wire_text)}}
    directory = task / 'refine_planners/job-one'
    save(task / 'refine_state.json', job)
    save(task / 'refine_requests/request-one/job-one.json', job)
    save(directory / 'context.json', payload)
    save(directory / 'schema.json', schema)
    save(directory / 'request.json', {'schema': schema, 'instructions': 'Inspect context.',
                                     'limits': {'backend_prompt_chars': 1024}})
    save(directory / 'manifest.json', {'job_id': 'job-one', 'transport': 'repl-context-v1',
        'status': 'complete', 'logical_payload_chars': len(text(payload)),
        'logical_payload_sha256': digest(text(payload)), 'limits': {'backend_prompt_chars': 1024}})
    prompt, result = 'Inspect the full context variable.', '```repl\nanswer["ready"] = True\n```'
    full = INSTRUCTION + prompt
    actions = [{'event': 'snapshot.read', 'logical_payload_sha256': digest(text(payload))},
               {'event': 'model.start', 'action_id': 'action-one', 'role': 'planner',
                'prompt': prompt, 'backend_prompt': full, 'schema': None}]
    calls = []
    for attempt in range(2 if retry else 1):
        failed = retry and attempt == 0
        call = {'call_id': f'call-{attempt}', 'purpose': 'refine', 'model': 'fixed-refine',
                'attempt': attempt, 'prompt_chars': len(full), 'prompt_sha256': digest(full),
                'prompt': full, 'response': 'partial' if failed else result,
                'response_chars': len('partial' if failed else result), 'error': 'transient' if failed else None}
        save(task / 'codex_attempts' / (call['call_id'] + '.json'),
             {key: value for key, value in call.items() if key not in ('prompt', 'response', 'response_chars', 'error')})
        calls.append(call)
        for status in ('dispatched', 'failed' if failed else 'succeeded'):
            actions.append({'event': 'model.attempt', 'action_id': 'action-one', 'role': 'planner',
                            'call_id': call['call_id'], 'model': call['model'], 'attempt': attempt,
                            'status': status, 'error': 'transient' if status == 'failed' else None})
    actions += [{'event': 'model.end', 'action_id': 'action-one', 'role': 'planner', 'response': result},
                {'event': 'code.start', 'iteration': 1, 'block': 0, 'code': 'answer["ready"] = True'},
                {'event': 'code.end', 'iteration': 1, 'block': 0, 'stdout': '', 'stderr': '',
                 'answer_ready': True, 'final_answer': response},
                {'event': 'proposal.returned', 'text': response}]
    save_lines(directory / 'actions.jsonl', actions)
    save_lines(task / 'codex_calls.jsonl', calls)
    return expected, job, directory, actions, calls


def test_actual_calls_and_retries_are_verified_without_inventing_monolithic_dispatch(tmp_path):
    expected, job, directory, actions, calls = transport(tmp_path, retry=True)
    original = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    result = audit.audit_refinement_transports(tmp_path)
    assert len(result) == 1
    report = result[0]
    assert report['status'] == 'available'
    assert report['pre_routing_input_dispatched'] is False
    assert report['logical_input_equal'] and report['schema_enum_exact']
    assert report['model_action_count'] == 1 and report['backend_attempt_count'] == 2
    assert report['attempts'][0]['response'] == 'partial'
    assert report['attempts'][1]['prompt'] != INSTRUCTION + job['planner_prompt']
    assert report['proposal_schema_valid'] and report['accounting_valid']
    assert {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()} == original
    assert str(directory / 'context.json') in {x['path'] for x in report['source_files']}


@pytest.mark.parametrize('damage', ['context', 'schema', 'manifest', 'snapshot_hash',
                                  'action_prompt', 'action_schema', 'action_call_id',
                                  'completion_response', 'completion_schema', 'missing_action',
                                  'unbound_attempt', 'proposal', 'readiness', 'job_identity'])
def test_transport_audit_rejects_tampered_or_unbound_evidence(tmp_path, damage):
    _, job, directory, actions, calls = transport(tmp_path)
    if damage in ('context', 'schema', 'manifest'):
        path = directory / (damage + '.json')
        value = json.loads(path.read_text())
        if damage == 'context':
            value['trajectory'][0]['result'] += 'changed'
        elif damage == 'schema':
            value['properties']['edits']['maxItems'] = 3
        else:
            value['logical_payload_sha256'] = 'wrong'
        save(path, value)
    elif damage == 'completion_response':
        calls[0]['response'] = 'same length altered response'.ljust(calls[0]['response_chars'])[:calls[0]['response_chars']]
    elif damage == 'completion_schema':
        calls[0]['schema_chars'] = 12
        calls[0]['schema_sha256'] = 'unexpected'
    elif damage == 'unbound_attempt':
        save(tmp_path / 'codex_attempts/stray.json', {**calls[0], 'call_id': 'stray'})
    elif damage == 'job_identity':
        job['job_id'] = 'wrong'
        save(tmp_path / 'refine_requests/request-one/job-one.json', job)
    else:
        if damage == 'snapshot_hash':
            actions[0]['logical_payload_sha256'] = 'wrong'
        elif damage == 'action_prompt':
            actions[1]['backend_prompt'] += 'changed'
        elif damage == 'action_schema':
            actions[1]['schema'] = {'type': 'string'}
        elif damage == 'action_call_id':
            actions[2]['call_id'] = 'unknown'
        elif damage == 'missing_action':
            actions = [x for x in actions if x['event'] != 'model.start']
        elif damage == 'proposal':
            actions[-1]['text'] = '{}'
        else:
            actions[-2]['final_answer'] = 'different'
    save_lines(directory / 'actions.jsonl', actions)
    save_lines(tmp_path / 'codex_calls.jsonl', calls)
    with pytest.raises(audit.ArchiveCorruptionError):
        audit.audit_refinement_transports(tmp_path)


def test_incomplete_attempt_is_preserved_with_explicit_missing_completion(tmp_path):
    _, job, directory, actions, calls = transport(tmp_path)
    job.update(status='failed', response_text=None, proposal=None)
    for path in (tmp_path/'refine_state.json', tmp_path/'refine_requests/request-one/job-one.json'):
        save(path, job)
    manifest = json.loads((directory/'manifest.json').read_text())
    manifest.update(status='failed', error='interrupted')
    save(directory/'manifest.json', manifest)
    save_lines(directory/'actions.jsonl', actions[:3])
    save_lines(tmp_path/'codex_calls.jsonl', [])
    report = audit.audit_refinement_transports(tmp_path)[0]
    assert report['status'] == 'partial'
    assert report['missing_completion_call_ids'] == ['call-0']
    assert report['attempts'][0]['response'] is None
    assert report['proposal_schema_valid'] is None


def test_audit_keeps_refiner_worker_roles_out_of_research_subcall_statistics(tmp_path):
    from test_archive_audit import archive
    run, task, *_ = archive(tmp_path)
    old_calls = audit.lines(task/'codex_calls.jsonl')
    transport(task)
    new_calls = audit.lines(task/'codex_calls.jsonl')
    save_lines(task/'codex_calls.jsonl', [{k:v for k,v in x.items() if k != '_line'}
                                        for x in old_calls + new_calls])
    result = audit.audit_task(task, run)
    assert result['subcall_count'] == 0
    assert result['metrics']['calls_by_purpose'] == {'root': 1, 'refine': 1}
    assert result['refinement_transports'][0]['backend_attempt_count'] == 1
    assert any('/refine_planners/' in x['path'] for x in result['source_files'])


@pytest.mark.parametrize('damage', ['completion_prompt_missing', 'terminal_owner', 'retry_sequence'])
def test_actual_attempt_identity_is_strict_even_for_identical_inputs(tmp_path, damage):
    _, job, directory, actions, calls = transport(tmp_path, retry=True)
    if damage == 'completion_prompt_missing':
        calls[0].pop('prompt')
    elif damage == 'terminal_owner':
        second = {**actions[1], 'action_id': 'another-action'}
        actions.insert(2, second)
        actions[4]['action_id'] = 'another-action'  # failed terminal for the original action
    else:
        calls[1]['attempt'] = 0
        receipt_path = tmp_path/'codex_attempts/call-1.json'
        receipt = json.loads(receipt_path.read_text())
        receipt['attempt'] = 0
        save(receipt_path, receipt)
        for event in actions:
            if event.get('call_id') == 'call-1':
                event['attempt'] = 0
    save_lines(directory/'actions.jsonl', actions)
    save_lines(tmp_path/'codex_calls.jsonl', calls)
    with pytest.raises(audit.ArchiveCorruptionError):
        audit.audit_refinement_transports(tmp_path)


def test_failed_proposal_validation_is_preserved_without_claiming_archive_corruption(tmp_path):
    _, job, directory, actions, _ = transport(tmp_path)
    invalid = {'summary': 42, 'edits': [], 'additional_candidates': [], 'decisions': []}
    response = text(invalid)
    job.update(status='failed', response_text=response, proposal=None)
    for path in (tmp_path/'refine_state.json', tmp_path/'refine_requests/request-one/job-one.json'):
        save(path, job)
    actions[-2]['final_answer'] = response
    actions[-1]['text'] = response
    save_lines(directory/'actions.jsonl', actions)
    report = audit.audit_refinement_transports(tmp_path)[0]
    assert report['proposal_schema_valid'] is False
    assert report['accounting_valid'] is False
    assert 'ValidationError' in report['proposal_validation_error']
    assert report['job_status'] == 'failed'
