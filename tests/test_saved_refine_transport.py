"""Replay guards apply at the actual process boundary, including scoped contexts."""
import concurrent.futures
import copy
from dataclasses import replace
import hashlib
import json
import random
import string
import sys
from pathlib import Path

import pytest

from loop_research.archive import RunContext, read_jsonl
from loop_research.codex_backend import CodexBackend
from loop_research.config import Config
from loop_research.harness import Harness
from loop_research.refine import INSTRUCTIONS, Proposal, Refiner, evidence_anchors
from loop_research.shared_text import encode_shared_text
from test_saved_refine_input import helper


def recorder(tmp_path, expected, response='{"fixture":"response"}', schema=None):
    executable = tmp_path / 'offline-codex'
    executable.write_text(f'#!{sys.executable}\nimport pathlib,sys\n'
                          'sys.stdin.read()\n'
                          f'pathlib.Path(sys.argv[sys.argv.index("--output-last-message")+1]).write_text({response!r})\n')
    executable.chmod(0o755)
    config = Config.load(Path(__file__).resolve().parents[1] / 'config.yaml')
    config.codex.bin = str(executable)
    config.codex.max_retries = 0
    context_type, state = helper().recording_context(RunContext, expected, expected_schema=schema)
    return context_type(tmp_path, 'offline', config, 'task', concurrent.futures.Future()), state


def logical():
    return {'focus': None, 'candidate_inventory': [], 'entries': [], 'trajectory': [],
            'self_check': {'issues': [], 'signals': []}, 'max_edits': 2}


def direct(expected):
    payload = {**expected, 'evidence_index': evidence_anchors(expected)}
    schema = Proposal.model_json_schema()
    schema['$defs']['EvidenceRef'] = {'type': 'string', 'enum': payload['evidence_index']}
    prompt = INSTRUCTIONS + json.dumps(encode_shared_text(payload), ensure_ascii=False, separators=(',', ':'))
    return prompt, schema


def test_direct_guard_and_recorder_survive_dataclass_context_copy(tmp_path):
    expected = logical()
    ctx, state = recorder(tmp_path, expected)
    child = replace(ctx, cancellation=concurrent.futures.Future())
    prompt, schema = direct(expected)
    assert CodexBackend(child).complete(prompt, purpose='refine', schema=schema) == '{"fixture":"response"}'
    assert state['codex_calls'] == 1 and state['worker_processes'] == 0
    command = read_jsonl(ctx.path / 'commands.jsonl')[0]
    assert command['process_kind'] == 'codex'
    assert command['stdin_chars'] > len(prompt)
    assert (ctx.path / 'transport/000/schema.json').read_text() == json.dumps(schema)


@pytest.mark.parametrize('damage', ['purpose', 'web', 'payload', 'schema', 'missing_schema'])
def test_copied_context_rejects_research_or_changed_direct_input_before_process(tmp_path, damage):
    expected = logical()
    ctx, state = recorder(tmp_path, expected)
    prompt, schema = direct(expected)
    purpose, web = 'refine', False
    if damage == 'purpose':
        purpose = 'root'
    elif damage == 'web':
        web = True
    elif damage == 'payload':
        prompt, schema = direct({**expected, 'focus': 'altered'})
    elif damage == 'schema':
        schema['$defs']['EvidenceRef']['enum'] = []
    else:
        schema = None
    with pytest.raises(ValueError):
        CodexBackend(replace(ctx)).complete(prompt, purpose=purpose, web=web, schema=schema)
    assert state['codex_calls'] == state['worker_processes'] == 0


def test_real_isolated_overflow_replay_counts_worker_separately_and_audits_actual_calls(tmp_path):
    from loop_research.archive_audit import audit_refinement_transports
    observed = {'trajectory': [{'result': ''.join(random.Random(5).choices(string.ascii_letters, k=1_060_000))}],
                'self_check': {'issues': [], 'signals': []}}
    expected = {**logical(), **observed}
    proposal = {'summary': 'No supported edit.', 'edits': [], 'additional_candidates': [], 'decisions': []}
    source_hash = hashlib.sha256(observed['trajectory'][0]['result'].encode()).hexdigest()
    code = f'''import json, hashlib
assert hashlib.sha256(context["trajectory"][0]["result"].encode()).hexdigest() == {source_hash!r}
assert context == snapshot()
assert llm_query("Review fixture evidence") == "Reviewed complete fixture evidence."
answer["content"] = json.dumps({proposal!r})
answer["ready"] = True'''
    ctx, state = recorder(tmp_path, expected, '```repl\n' + code + '\n```')
    # Two offline response types exercise optional schemas and actual child calls.
    executable = ctx.config.codex.bin
    script = open(executable).read().replace('sys.stdin.read()', 'prompt = sys.stdin.read()')
    script = script.replace('pathlib.Path(sys.argv', 'response = "Reviewed complete fixture evidence." if prompt.endswith("Review fixture evidence") else ' + repr('```repl\n' + code + '\n```') + '\npathlib.Path(sys.argv')
    script = script[:script.rfind('.write_text(')] + '.write_text(response)\n'
    open(executable, 'w').write(script)
    harness = Harness(tmp_path / 'harness')
    refiner = Refiner(harness, ctx, CodexBackend(ctx), lambda: copy.deepcopy(observed))
    try:
        refiner.run()
        refiner.boundary(wait=True)
    finally:
        refiner.close()
    saved = ctx.load('refine_state.json')
    assert saved['status'] == 'applied'
    assert state['worker_processes'] == 1 and state['codex_calls'] == 2
    commands = read_jsonl(ctx.path / 'commands.jsonl')
    assert [row['process_kind'] for row in commands].count('refiner_worker') == 1
    assert all(row.get('schema_sha256') is None for row in commands)
    verified = ctx.load('input_verification.json')
    assert verified['original_logical_input_equal'] and verified['schema_enum_exact']
    report = audit_refinement_transports(ctx.path)[0]
    assert report['backend_attempt_count'] == 2 and report['accounting_valid']
    assert {row['role'] for row in report['attempts']} == {'planner', 'sub'}
    assert all(row['completion_available'] for row in report['attempts'])


def test_unknown_python_process_is_rejected(tmp_path):
    ctx, state = recorder(tmp_path, logical())
    with pytest.raises(ValueError, match='process'):
        replace(ctx).run_process([sys.executable, '-c', 'raise SystemExit(0)'])
    assert state['worker_processes'] == state['codex_calls'] == 0


def test_replay_rejects_changed_full_schema_even_when_reference_enum_matches(tmp_path):
    expected = logical()
    prompt, schema = direct(expected)
    ctx, state = recorder(tmp_path, expected, schema=copy.deepcopy(schema))
    schema['properties']['summary']['type'] = 'integer'
    with pytest.raises(ValueError, match='schema'):
        CodexBackend(replace(ctx)).complete(prompt, purpose='refine', schema=schema)
    assert state['codex_calls'] == 0


def test_legacy_schema_upgrade_is_exact_and_preserves_original_constraints():
    expected = logical()
    original = Proposal.model_json_schema()
    original['properties']['edits']['maxItems'] = expected['max_edits']
    contract = helper().replay_schema_contract({'planner_schema': original}, expected)
    assert contract['mode'] == 'legacy_anchor_restriction'
    assert contract['original_schema'] == original
    assert contract['current_schema']['properties']['edits'] == original['properties']['edits']
    assert contract['current_schema']['$defs']['EvidenceRef']['enum'] == evidence_anchors(expected)
    assert len(contract['changes']) == 3
    anchored = {**expected, 'evidence_index': evidence_anchors(expected)}
    current = contract['current_schema']
    assert helper().replay_schema_contract(
        {'planner_schema': current, 'evidence_index': anchored['evidence_index']}, expected)['mode'] == 'exact'


@pytest.mark.parametrize('change', ['schema', 'representation', 'index'])
def test_legacy_schema_upgrade_rejects_unrecognized_history(change):
    expected = logical()
    original = Proposal.model_json_schema()
    original['properties']['edits']['maxItems'] = expected['max_edits']
    job = {'planner_schema': original}
    if change == 'schema':
        original['properties']['edits']['maxItems'] += 1
    elif change == 'representation':
        job['planner_representation'] = {}
    else:
        job['evidence_index'] = []
    with pytest.raises(ValueError, match='schema'):
        helper().replay_schema_contract(job, expected)


def test_all_refine_attempt_count_includes_direct_jobs(tmp_path):
    from test_refinement_transport_audit import save, save_lines
    save(tmp_path/'codex_attempts/direct.json', {'call_id': 'direct', 'purpose': 'refine'})
    save(tmp_path/'codex_attempts/context.json', {'call_id': 'context', 'purpose': 'refine'})
    save_lines(tmp_path/'codex_calls.jsonl', [{'call_id': 'direct', 'purpose': 'refine'},
                                           {'call_id': 'context', 'purpose': 'refine'}])
    counts = helper().replay_attempt_counts(tmp_path, [{'backend_attempt_count': 1}])
    assert counts == {'actual_refinement_attempts': 2, 'context_refinement_attempts': 1}
