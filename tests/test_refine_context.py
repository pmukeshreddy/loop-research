"""Oversized observations remain complete, inspectable, isolated and accountable."""
import copy
import hashlib
import json
from pathlib import Path
import random
import string
import threading
import tempfile
from types import SimpleNamespace

import pytest

from loop_research.archive import read_jsonl
from loop_research.codex_backend import CodexBackend
from loop_research.harness import Harness
from loop_research.refine import Refiner
from loop_research.trace import Trace


@pytest.fixture(scope='module')
def large_observation():
    text = ''.join(random.Random(13).choices(string.ascii_letters, k=1_060_000))
    return {'trajectory': [{'type': 'tool', 'result': text, 'unknown': [False, None, '雪']}],
            'self_check': {'ok': True, 'issues': [], 'signals': [
                {'type': 'fixture_signal', 'detail': 'first occurrence'},
                {'type': 'fixture_signal', 'detail': 'second occurrence'}]}}


def declined_proposal():
    return {'summary': 'Observed occurrences have no supported durable lesson.', 'edits': [],
            'additional_candidates': [], 'decisions': [{
                'candidate_id': 'self_check:signals:fixture_signal', 'decision': 'declined',
                'reason': 'Both observed occurrences were inspected and supply no reusable change.',
                'evidence_refs': ['/self_check/signals/0', '/self_check/signals/1'], 'edit_indexes': []}]}


def cli_runner(respond, seen):
    def run(command, **kwargs):
        prompt = kwargs['input']
        assert len(prompt) <= 1_048_576, 'Planner dispatched oversized input instead of inspecting its full snapshot'
        schema = (json.loads(Path(command[command.index('--output-schema') + 1]).read_text())
                  if '--output-schema' in command else None)
        seen.append((prompt, schema, command[command.index('--model') + 1]))
        response = respond(prompt, schema)
        Path(command[command.index('--output-last-message') + 1]).write_text(response)
        return SimpleNamespace(returncode=0, stdout='', stderr='')
    return run


def execute(ctx, observation, respond):
    seen = []
    ctx.trace = Trace(ctx.run_dir)
    harness = Harness(ctx.root / 'harness')
    backend = CodexBackend(ctx, runner=cli_runner(respond, seen))
    refiner = Refiner(harness, ctx, backend, lambda: copy.deepcopy(observation))
    try:
        refiner.run()
        refiner.boundary(wait=True)
    finally:
        refiner.close()
    return ctx.load('refine_state.json'), seen, harness


def test_full_snapshot_code_subcall_and_untruncated_feedback(ctx, large_observation):
    original = copy.deepcopy(large_observation)
    ctx.config.models.root = 'fixture-root'
    ctx.config.models.sub = 'fixture-sub'
    ctx.config.models.refine = 'fixture-refiner'
    seed = Harness(ctx.root / 'harness')
    entry = seed.create('memory', 'Earlier procedure', 'Preserve complete historical metadata.')
    seed.record_usage([entry], 'earlier-run')
    seed.record_outcome('earlier-run', {'ok': True, 'issues': [], 'signals': []})
    expected_entries = list(seed.snapshot()['entries'].values())
    expected_hash = hashlib.sha256(original['trajectory'][0]['result'].encode()).hexdigest()
    secret = ctx.root / 'private.txt'
    secret.write_text('host-only fixture')
    printed = 'visible-feedback-' * 1800
    schema = {'type': 'object', 'properties': {'count': {'type': 'integer'}},
              'required': ['count'], 'additionalProperties': False}
    root_calls = 0
    def respond(prompt, requested_schema):
        nonlocal root_calls
        if requested_schema is not None:
            assert requested_schema == schema
            assert 'second occurrence' in prompt
            return '{"count":2}'
        root_calls += 1
        if root_calls == 1:
            return '```repl\n' + f'''
import hashlib, json
from pathlib import Path
assert hashlib.sha256(context['trajectory'][0]['result'].encode()).hexdigest() == {expected_hash!r}
assert context['trajectory'][0]['unknown'] == [False, None, '雪']
assert context['entries'] == {expected_entries!r}
assert context['candidate_inventory'][0]['count'] == 2
assert context['candidate_inventory'][0]['evidence_refs'] == ['/self_check/signals/0', '/self_check/signals/1']
assert context == snapshot()
context['trajectory'][0]['result'] = 'local change'
assert hashlib.sha256(snapshot()['trajectory'][0]['result'].encode()).hexdigest() == {expected_hash!r}
try:
    Path({str(secret)!r}).read_text()
except PermissionError:
    pass
else:
    raise AssertionError('worker read outside snapshot capability')
print({printed!r})
''' + '\n```'
        assert root_calls == 2
        assert printed + '\n' in prompt
        return '```repl\n' + f'''
result = llm_query_json(json.dumps(snapshot()['self_check']['signals']), {schema!r})
assert result == {{'count': 2}}
proposal = {declined_proposal()!r}
answer['content'] = json.dumps(proposal)
answer['ready'] = True
''' + '\n```'
    state, seen, harness = execute(ctx, original, respond)
    assert state['status'] == 'applied' and state['proposal'] == declined_proposal()
    assert state['observed'] == original == large_observation
    assert list(harness.snapshot()['entries'].values()) == expected_entries
    assert len(seen) == 3 and all(model == ctx.config.models.refine for _, _, model in seen)
    assert all(row['purpose'] == 'refine' for row in read_jsonl(ctx.path / 'codex_calls.jsonl'))
    directory = ctx.path / 'refine_planners' / state['job_id']
    payload = json.loads((directory / 'context.json').read_text())
    assert payload['trajectory'] == original['trajectory'] and payload['self_check'] == original['self_check']
    assert payload['evidence_index'] == state['evidence_index']
    assert json.loads((directory / 'schema.json').read_text()) == state['planner_schema']
    actions = read_jsonl(directory / 'actions.jsonl')
    assert any(row.get('stdout') == printed + '\n' for row in actions)
    assert all('root' not in row['component'].lower() and row['component'] != 'REPL'
               for row in read_jsonl(ctx.run_dir / 'trace.jsonl'))


@pytest.mark.parametrize('failure', ['missing_candidate', 'wrong_type', 'too_many_edits', 'bad_evidence', 'non_anchor_pointer'])
def test_overflow_keeps_strict_proposal_validation_before_edits(ctx, large_observation, failure):
    proposal = declined_proposal()
    if failure == 'missing_candidate':
        proposal['decisions'] = []
    elif failure == 'wrong_type':
        proposal['decisions'][0]['reason'] = 42
    elif failure == 'too_many_edits':
        proposal['edits'] = [{'action': 'create', 'kind': 'memory', 'id': None, 'title': 'Fixture',
                              'content': 'Procedure', 'module': None}] * 3
    elif failure == 'bad_evidence':
        proposal['decisions'][0]['evidence_refs'] = ['/self_check/signals/99']
    else:
        # This child pointer exists and passes accounting, but is absent from
        # the original strict EvidenceRef enum supplied to the direct planner.
        proposal['decisions'][0]['evidence_refs'] = ['/self_check/signals/0/detail']
    code = 'import json\nanswer["content"] = json.dumps(' + repr(proposal) + ')\nanswer["ready"] = True'
    with pytest.raises((ValueError, RuntimeError)):
        execute(ctx, large_observation, lambda *_: '```repl\n' + code + '\n```')
    assert ctx.load('refine_state.json')['status'] == 'failed'
    assert Harness(ctx.root / 'harness').list() == []


def test_overflow_iteration_exhaustion_has_no_unlogged_fallback(ctx, large_observation):
    ctx.config.rlm.max_iterations = 1
    with pytest.raises(RuntimeError, match='iteration'):
        execute(ctx, large_observation, lambda *_: '```repl\nprint(len(context["trajectory"]))\n```')
    assert len(read_jsonl(ctx.path / 'codex_calls.jsonl')) == 1
    assert ctx.load('refine_state.json')['status'] == 'failed'


def test_overflow_stderr_and_completed_bindings_reach_next_planner(ctx, large_observation):
    error_text = 'full-error-' * 2500
    calls = 0
    def respond(prompt, schema):
        nonlocal calls
        calls += 1
        if calls == 1:
            return '```repl\ncompleted = 42\nraise ValueError(' + repr(error_text) + ')\n```'
        assert calls == 2 and 'ValueError: ' + error_text in prompt
        return '```repl\nimport json\nassert completed == 42\nanswer["content"] = json.dumps(' + \
            repr(declined_proposal()) + ')\nanswer["ready"] = True\n```'
    state, _, _ = execute(ctx, large_observation, respond)
    actions = read_jsonl(ctx.path / 'refine_planners' / state['job_id'] / 'actions.jsonl')
    assert any(row.get('stderr', '').endswith('ValueError: ' + error_text) for row in actions)


def test_large_print_is_retrievable_in_full_and_selected_subcall_can_complete(ctx, large_observation):
    expected = large_observation['trajectory'][0]['result'] + '\n'
    expected_hash = hashlib.sha256(expected.encode()).hexdigest()
    planner_calls = 0
    def respond(prompt, schema):
        nonlocal planner_calls
        if prompt.endswith('EXACT_SELECTED ' + expected[:80]):
            return 'Selected evidence reviewed.'
        planner_calls += 1
        if planner_calls == 1:
            return ('```repl\nprint(context["trajectory"][0]["result"])\n```\n'
                    '```repl\nprint("second block retained")\n```')
        assert planner_calls == 2
        assert 'REPL OUTPUT REFERENCE' in prompt and expected not in prompt
        return '```repl\n' + f'''
import hashlib, json
saved = repl_output(1)
assert len(saved["blocks"]) == 2
assert hashlib.sha256(saved["blocks"][0]["stdout"].encode()).hexdigest() == {expected_hash!r}
assert saved["blocks"][0]["stderr"] == ""
assert saved["blocks"][0]["code"] == 'print(context["trajectory"][0]["result"])'
assert saved["blocks"][1]["stdout"] == "second block retained\\n"
saved["blocks"][0]["stdout"] = "local mutation"
restored = repl_output(1)
assert hashlib.sha256(restored["blocks"][0]["stdout"].encode()).hexdigest() == {expected_hash!r}
assert llm_query("EXACT_SELECTED " + restored["blocks"][0]["stdout"][:80]) == "Selected evidence reviewed."
answer["content"] = json.dumps({declined_proposal()!r})
answer["ready"] = True
''' + '\n```'
    state, seen, _ = execute(ctx, large_observation, respond)
    directory = ctx.path / 'refine_planners' / state['job_id']
    actions = read_jsonl(directory / 'actions.jsonl')
    assert state['status'] == 'applied' and len(seen) == 3
    assert next(row for row in actions if row['event'] == 'code.end')['stdout'] == expected
    references = [row for row in actions if row['event'] == 'output.externalized']
    assert len(references) == 1 and references[0]['iteration'] == 1
    assert len([row for row in actions if row['event'] == 'output.read']) == 2
    assert json.loads((directory/'request.json').read_text())['output_transport'] == 'whole-iteration-reference-v1'
    assert json.loads((directory/'manifest.json').read_text())['output_transport'] == 'whole-iteration-reference-v1'


def test_cumulative_prints_externalize_one_whole_iteration_and_keep_smaller_new_output_inline(ctx, large_observation):
    calls = 0
    def respond(prompt, schema):
        nonlocal calls
        calls += 1
        if calls == 1:
            return '```repl\nprint("A" * 600000)\n```'
        if calls == 2:
            assert 'A' * 600000 in prompt
            return '```repl\nprint("B" * 600000)\n```'
        assert calls == 3
        assert 'A' * 600000 not in prompt and 'B' * 600000 in prompt
        return '```repl\nimport json\nanswer["content"] = json.dumps(' + repr(declined_proposal()) + ')\nanswer["ready"] = True\n```'
    state, _, _ = execute(ctx, large_observation, respond)
    events = read_jsonl(ctx.path/'refine_planners'/state['job_id']/'actions.jsonl')
    assert [row['iteration'] for row in events if row['event'] == 'output.externalized'] == [1]


def test_large_stderr_receipt_is_visible_and_full_iteration_restores_after_local_mutation(ctx, large_observation):
    calls = 0
    def respond(prompt, schema):
        nonlocal calls
        calls += 1
        if calls == 1:
            return '```repl\ncompleted = 42\nprint("small stdout")\nraise ValueError("Z" * 1060000)\n```'
        assert calls == 2 and '"stderr_present":true' in prompt
        return '```repl\n' + f'''
import json
assert completed == 42
saved = repl_output(1)
assert saved["blocks"][0]["stderr"].endswith("ValueError: " + "Z" * 1060000)
assert saved["blocks"][0]["stdout"] == "small stdout\\n"
assert saved["blocks"][0]["derived_stream_failure"] is True
saved["blocks"][0]["stderr"] = ""
assert repl_output(1)["blocks"][0]["stderr"].endswith("ValueError: " + "Z" * 1060000)
try:
    repl_output(2)
except RuntimeError as error:
    assert "not a sealed completed iteration" in str(error)
else:
    raise AssertionError("unsealed current iteration was exposed")
answer["content"] = json.dumps({declined_proposal()!r})
answer["ready"] = True
''' + '\n```'
    state, _, _ = execute(ctx, large_observation, respond)
    assert state['status'] == 'applied'


def test_oversized_control_response_fails_locally_without_another_model_dispatch(ctx, large_observation):
    control = 'Exact assistant control ' * 50_000
    calls = 0
    def respond(prompt, schema):
        nonlocal calls
        calls += 1
        assert calls == 1
        return control
    with pytest.raises(RuntimeError, match='control messages and whole-output references'):
        execute(ctx, large_observation, respond)
    state = ctx.load('refine_state.json')
    assert state['status'] == 'failed' and calls == 1
    actions = read_jsonl(ctx.path/'refine_planners'/state['job_id']/'actions.jsonl')
    assert next(row for row in actions if row['event'] == 'model.end')['response'] == control
    assert len([row for row in actions if row['event'] == 'model.start']) == 1
    assert not any(row['event'] == 'output.externalized' for row in actions)


def test_overflow_python_deadline_is_visible_and_does_not_edit(ctx, large_observation):
    ctx.config.codex.timeout_s = 2
    with pytest.raises((RuntimeError, TimeoutError)):
        execute(ctx, large_observation, lambda *_: '```repl\nwhile True:\n    pass\n```')
    assert ctx.load('refine_state.json')['status'] == 'failed'
    assert Harness(ctx.root / 'harness').list() == []


@pytest.fixture
def short_socket_dir():
    with tempfile.TemporaryDirectory(prefix='refine-test-', dir='/tmp') as directory:
        yield Path(directory)


def test_planner_server_exit_drains_post_dispatch_work(short_socket_dir):
    from loop_research.bridge import Client, Server
    entered, release, exiting, exited, recorded = (threading.Event() for _ in range(5))
    def dispatch(*_):
        entered.set()
        assert release.wait(5)
        recorded.set()
        return None
    socket = short_socket_dir / 'host.sock'
    server = Server(socket, dispatch, socket_timeout_s=5)
    # Exercise the opt-in behavior without requiring a changed constructor for RED.
    server.drain_handlers = True
    def owner():
        with server:
            assert entered.wait(5)
            exiting.set()
        exited.set()
    thread = threading.Thread(target=owner)
    thread.start()
    caller_errors = []
    def call():
        try:
            Client(socket).call('model')
        except Exception as error:
            caller_errors.append(error)
    caller = threading.Thread(target=call)
    caller.start()
    assert exiting.wait(5)
    try:
        assert not exited.wait(.7), 'Server exited before the handler finished its archive writes'
        assert not recorded.is_set()
    finally:
        release.set()
        caller.join(5)
        thread.join(5)
    assert exited.is_set() and recorded.is_set()
