"""Structured sub-model calls retain normal isolation, budget, and trace semantics."""
from dataclasses import replace
import json

import pytest
from jsonschema.exceptions import ValidationError

from loop_research.archive import read_jsonl
from loop_research.harness import Harness
from loop_research.session import Session
from test_agent_tools import Replies

SCHEMA = {'type': 'object', 'properties': {'entities': {'type': 'array', 'items': {'type': 'string'}}},
          'required': ['entities'], 'additionalProperties': False}


def test_structured_session_enforces_shape_and_archives_exact_schema(ctx, task):
    backend = Replies('{"entities":[{"name":"Example"}]}')
    session = Session(task, ctx, Harness(ctx.root / 'harness'), learning=False, backend=backend)
    try:
        with pytest.raises(ValidationError, match='not of type'):
            session.dispatch('models.query_json', ['extract', SCHEMA], {})
        assert len(backend.calls) == 1
        assert backend.calls[0][1]['purpose'] == 'sub'
        assert backend.calls[0][1]['model'] == ctx.config.models.sub
        assert backend.calls[0][1]['schema'] == SCHEMA
        recorded = read_jsonl(ctx.path / 'trajectory.jsonl')[-1]
        assert recorded['purpose'] == 'sub' and recorded['schema'] == SCHEMA
        assert json.loads(recorded['response']) == {'entities': [{'name': 'Example'}]}
    finally:
        session.refiner.close()


def test_structured_session_rejects_unknown_operation_without_dispatch(ctx, task):
    backend = Replies()
    session = Session(task, ctx, Harness(ctx.root / 'harness'), learning=False, backend=backend)
    try:
        with pytest.raises(ValueError, match='Unknown'):
            session.dispatch('models.unrestricted', ['extract', SCHEMA], {})
        assert backend.calls == []
    finally:
        session.refiner.close()


def test_real_worker_structured_calls_preserve_trace_parity_and_budget(ctx, task, output):
    from loop_research.agent import run_task
    from loop_research.research import ResearchData
    from loop_research.trace import Trace
    from test_worker import OfflineBackend, code_reply, final_code

    code = f'''
schema = {SCHEMA!r}
before = budget()
result = llm_query_json("one", schema)
assert result == {{"entities": ["one"]}}
results = llm_query_json_batched(["two", "three"], schema)
assert results == [{{"entities": ["two"]}}, {{"entities": ["three"]}}]
after = budget()
assert before["reserved"] == 1 and after["reserved"] == 4
assert after["remaining"] == after["limit"] - 4
''' + final_code(output)

    def reply(prompt, options):
        if options['purpose'] == 'root':
            return code_reply(code)
        assert options['purpose'] == 'sub' and options['schema'] == SCHEMA
        return json.dumps({'entities': [prompt]})

    recorded_runs = []
    for traced in (False, True):
        run = replace(ctx, run_id='structured-traced' if traced else 'structured-plain')
        if traced:
            run.trace = Trace(run.run_dir)
        backend = OfflineBackend(reply)
        session = Session(task, run, Harness(run.root / run.run_id), learning=False, backend=backend)
        backend.budget = session.budget
        try:
            result = run_task(task, ResearchData(), session)
            assert result.output == output
            models = [r for r in read_jsonl(run.path / 'trajectory.jsonl') if r['type'] == 'model']
            assert len([r for r in models if r['purpose'] == 'sub']) == 3
            assert all(r['schema'] == SCHEMA for r in models if r['purpose'] == 'sub')
            recorded_runs.append((result, sorted(backend.calls, key=lambda item: item[0]), session.finish()))
        finally:
            session.refiner.close()
    assert recorded_runs[0] == recorded_runs[1]
    events = read_jsonl(ctx.root / 'runs/structured-traced/trace.jsonl')
    assert sum(e['component'] == 'RLM sub' and e['event'] == 'model.end' for e in events) == 3
    bridge = [e for e in events if e['component'] == 'Bridge' and e['event'] == 'rpc.start']
    assert {e['details']['method'] for e in bridge} >= {'models.query_json', 'models.query_json_batched', 'budget'}


def test_codex_archives_exact_schema_input_size_and_hash(ctx):
    from hashlib import sha256
    from pathlib import Path
    import subprocess
    from loop_research.codex_backend import CodexBackend

    schema = {**SCHEMA, 'description': 'Unicode example: café'}
    sent = []
    def runner(command, **options):
        sent.append(Path(command[command.index('--output-schema') + 1]).read_text())
        Path(command[command.index('--output-last-message') + 1]).write_text('{"entities":[]}')
        return subprocess.CompletedProcess(command, 0, '', '')
    CodexBackend(ctx, runner=runner).complete('extract', purpose='sub', schema=schema)
    record = read_jsonl(ctx.path / 'codex_calls.jsonl')[-1]
    assert json.loads(sent[0]) == schema
    assert record['schema_chars'] == len(sent[0])
    assert record['schema_sha256'] == sha256(sent[0].encode()).hexdigest()
    start = json.loads((ctx.path / 'codex_attempts' / (record['call_id'] + '.json')).read_text())
    assert start['schema_chars'] == record['schema_chars']
    assert start['schema_sha256'] == record['schema_sha256']
