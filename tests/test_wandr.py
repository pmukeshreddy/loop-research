"""Hand-written WANDR fixtures exercise the unchanged pinned verifier offline."""
import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ValidationError
from openai.lib._parsing._completions import type_to_response_format_param

from loop_research.agent import citation_check, parse_output
from loop_research.archive import read_json, write_json
from loop_research.benchmarks import Task
from loop_research.benchmarks.wandr.data import CODE_REVISION
from loop_research.benchmarks.wandr.grader import CodexTransport, WandrBenchmark, install_services, load_verifier, record_errors

ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / 'data/vendor/wandr'
if not CODE.exists():
    CODE = ROOT / '.verification/wandr'
DATA = ROOT / 'data/downloads/wandr'
if not DATA.exists():
    DATA = ROOT / '.verification/wandr-dataset'


@pytest.fixture
def wandr(ctx):
    adapter = WandrBenchmark(ctx.root, ctx.config)
    adapter.code, adapter.download = CODE, DATA
    return adapter


@pytest.fixture
def fixture_task():
    return Task(task_id='fixture', benchmark='wandr', question='Hand-written fixture', language='en',
                spec={'nodes': [{'item_fields': ['entity'], 'required_output_file': 'results_fixture.jsonl'},
                                {'item_fields': ['entity', 'facet'], 'required_output_file': 'results_fixture.child.jsonl'}]})


@pytest.fixture
def fixture_output():
    record = {'item': {'entity': 'fixture-entity'}, 'url': 'https://example.org/fixture',
              'excerpts': ['fixture quotation'], 'answer': {'nested': {'arbitrary': ['fixture fact']}}}
    return {'files': {'results_fixture.jsonl': [record],
                      'results_fixture.child.jsonl': [{**record, 'item': {'entity': 'fixture-entity', 'facet': 'fixture-facet'}}]}}


@pytest.fixture
def verifier(monkeypatch):
    before = set(sys.modules)
    paths = sys.path[:]
    module = load_verifier(CODE / 'datasets/wandr/abm-provider-commercial-provenance')
    yield module
    sys.path[:] = paths
    for name in set(sys.modules) - before:
        if name.split('.')[0] in ('src', 'sidecars', 'verify', 'artifacts', 'rewards', 'submissions', 'utils', 'schemas', 'commercial_provenance'):
            sys.modules.pop(name)


def test_submission_contract_hierarchy_repair_and_citations(wandr, fixture_task, fixture_output):
    contract = wandr.output_contract(fixture_task)
    assert wandr.to_submission(fixture_task, fixture_output) == fixture_output['files']
    assert parse_output(json.dumps(fixture_output), contract, None) == (fixture_output, [], False)
    assert citation_check(fixture_output, ['https://example.org/fixture']) == []
    assert len(citation_check(fixture_output, [])) == 2
    invalid = json.loads(json.dumps(fixture_output))
    del invalid['files']['results_fixture.child.jsonl'][0]['item']['facet']
    with pytest.raises(ValidationError):
        wandr.to_submission(fixture_task, invalid)
    class Replies:
        calls = 0
        def complete(self, prompt, **kwargs):
            self.calls += 1
            return json.dumps(fixture_output)
    replies = Replies()
    assert parse_output('invalid', contract, replies)[0] == fixture_output
    assert replies.calls == 1
    replies.complete = lambda *a, **kw: 'invalid again'
    assert parse_output('invalid', contract, replies)[0] == contract.empty


def test_release_and_canonical_instructions(wandr):
    wandr.verify_sources()
    tasks = wandr.load_tasks()
    assert len(tasks) == 500
    assert all(t.question and t.as_of_date is None for t in tasks)
    assert all(t.raw['source_commit'] == CODE_REVISION for t in tasks)
    for task in tasks:
        assert set(wandr.output_contract(task).empty['files']) == set(task.raw['required_output_files'])
    excluded = [json.loads(line) for line in (DATA / 'data/test.jsonl').read_text().splitlines() if json.loads(line)['instruction'] is None]
    by_id = {t.task_id: t for t in tasks}
    assert len(excluded) == 4
    for row in excluded:
        assert by_id[row['task_id']].question == (wandr.package(row['task_id']) / 'instruction.md').read_text()


class FixtureVerdict(BaseModel):
    excerpts_faithful: bool
    reasoning: str


@pytest.mark.parametrize("judge", [None, "fixture-judge"])
def test_judge_exact_sdk_schema_parser_usage_and_cache(ctx, verifier, monkeypatch, judge):
    from loop_research.benchmarks.wandr import grader
    from src.runtime.llm import LLMRequest, llm_completion
    ctx.config.models.root = "fixture-root"
    ctx.config.models.judge = judge
    calls = []
    class Backend:
        def __init__(self, context):
            self.ctx, self.config = context, context.config
            self.last_usage = {'input_tokens': 7, 'output_tokens': 3}
        def complete(self, prompt, **kwargs):
            calls.append((prompt, kwargs))
            return '{"excerpts_faithful": true, "reasoning": "fixture verdict"}'
    monkeypatch.setattr(grader, 'CodexBackend', Backend)
    transport = CodexTransport(ctx, ctx.path / 'judge_cache')
    request = LLMRequest('official-model', 'exact system\ntext', 'record https://example.org/a', FixtureVerdict, 73, {'temperature': 0})
    result, usage = asyncio.run(llm_completion(transport, request))
    assert result == {'excerpts_faithful': True, 'reasoning': 'fixture verdict'}
    assert usage == {'input_tokens': 7, 'output_tokens': 3}
    assert asyncio.run(llm_completion(CodexTransport(ctx, transport.cache), request)) == (result, usage)
    assert len(calls) == 1
    assert json.loads(calls[0][0].split('\n', 1)[1]) == [
        {'role': 'system', 'content': request.system}, {'role': 'user', 'content': request.prompt}]
    assert calls[0][1] == {'purpose': 'grade', 'model': judge,
                         'schema': type_to_response_format_param(FixtureVerdict)['json_schema']['schema']}
    asyncio.run(llm_completion(transport, request._replace(prompt='record https://example.org/b')))
    asyncio.run(llm_completion(transport, request._replace(prompt='changed record https://example.org/a')))
    assert len(calls) == 3
    saved = read_json(next(transport.cache.glob('*.json')))
    assert saved['request']['request']['max_completion_tokens'] == 73
    assert saved['request']['request']['temperature'] == 0
    assert saved['request']['task'] == ctx.task_id


def test_judge_invalid_response_not_cached(ctx, monkeypatch):
    from loop_research.benchmarks.wandr import grader
    class Backend:
        def __init__(self, context):
            self.ctx, self.config, self.last_usage = context, context.config, None
        def complete(self, *args, **kwargs):
            return '{"wrong": "fixture"}'
    monkeypatch.setattr(grader, 'CodexBackend', Backend)
    transport = CodexTransport(ctx, ctx.path / 'judge_cache')
    with pytest.raises(ValidationError):
        asyncio.run(transport.parse(response_format=FixtureVerdict, model='fixture', messages=[]))
    assert not list(transport.cache.glob('*.json'))


def test_only_service_bindings_change_and_browser_fetch_is_used(ctx, verifier, monkeypatch):
    from src import components, pipeline
    from src.runtime.clients import create_browser_pool
    from src.runtime.llm import llm_completion
    original_pipeline = pipeline.run_pipeline
    original_judge = components.make_judge
    calls = []
    async def browser(client, record):
        calls.append((client, record))
        return {'page_text': 'fixture browser text', 'fetch_ok': True, 'status': 200}
    monkeypatch.setattr(components, 'browser_fetch', browser)
    install_services(verifier, ctx, ctx.path / 'judge_cache')
    record = {'url': 'https://example.org/fixture', 'excerpts': ['fixture']}
    assert asyncio.run(pipeline.fetch_pages('browser fixture', [record])) == [
        {'content': 'fixture browser text', 'page_text': 'fixture browser text', 'fetch_ok': True, 'status': 200}]
    assert calls == [('browser fixture', record)]
    assert pipeline.create_fetch_pool is create_browser_pool
    assert pipeline.run_pipeline is original_pipeline
    assert components.make_judge is original_judge
    assert components.llm_completion is llm_completion
    assert isinstance(pipeline.create_openai_pool(5, 2).next(), CodexTransport)
    assert pipeline.BROWSER_FALLBACK is False
    assert pipeline.FETCH_BATCH_SIZE == pipeline.FETCH_CLIENT_LOAD == 1
    async def failed(*args):
        return None
    monkeypatch.setattr(components, 'browser_fetch', failed)
    assert asyncio.run(pipeline.fetch_pages('browser fixture', [record])) == [None]


def test_error_breakdown_keeps_verdicts_and_unknown_rate():
    records = [{'task_name': 'fixture', 'url': 'https://example.org/a', 'item': {'entity': 'fixture'},
                'judge': {'excerpts_faithful': False, 'qualified': True, 'confidence': 3, 'reasoning': 'fixture reason'}}]
    result = record_errors(records, 2)
    assert result['excerpt_failure_rate'] == 1
    assert result['unjudged_records'] == 1
    assert result['records'][0]['failed_checks'] == ['excerpts_faithful']
    assert result['records'][0]['judge'] == records[0]['judge']
    assert record_errors([], 1)['excerpt_failure_rate'] is None


def test_empty_submission_uses_actual_official_zero_and_cached_result(ctx, wandr, monkeypatch):
    ctx.config.models.root = "fixture-root"
    ctx.config.models.judge = "fixture-judge"
    task = wandr.load_tasks()[0]
    task_ctx = ctx.task(task.task_id)
    submission = wandr.to_submission(task, wandr.output_contract(task).empty)
    result = wandr.grade(task, submission, task_ctx)
    assert result.primary_metric == 'soft_f1_full'
    assert result.provenance['harness_primary_metric'] == 'soft_recall_full'
    assert result.provenance['fetch'] == 'wandr-browser'
    assert result.judge == 'codex/fixture-judge'
    assert len(result.metrics) == 14 and set(result.metrics.values()) == {0}
    assert result.errors['invalid_submission'] is True
    assert result.errors['excerpt_failure_rate'] is None
    def forbidden(*args, **kwargs):
        raise AssertionError('Completed grade must not rerun the verifier')
    monkeypatch.setattr('loop_research.benchmarks.wandr.grader.subprocess.run', forbidden)
    assert wandr.grade(task, submission, task_ctx) == result


def test_cancelled_judge_wait_reuses_inflight_call_and_persists(ctx, monkeypatch):
    import time
    from loop_research.benchmarks.wandr import grader
    calls = []
    class Backend:
        def __init__(self, context):
            self.ctx, self.config, self.last_usage = context, context.config, None
        def complete(self, *args, **kwargs):
            calls.append(kwargs)
            time.sleep(.08)
            return '{"excerpts_faithful": true, "reasoning": "fixture"}'
    monkeypatch.setattr(grader, 'CodexBackend', Backend)
    transport = CodexTransport(ctx, ctx.path / 'judge_cache')
    async def check():
        kwargs = {'response_format': FixtureVerdict, 'model': 'fixture', 'messages': []}
        for _ in range(2):
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(transport.parse(**kwargs), timeout=.01)
        response = await transport.parse(**kwargs)
        assert response.choices[0].message.parsed.excerpts_faithful
        assert len(calls) == 1
        assert len(list(transport.cache.glob('*.json'))) == 1
        assert (await transport.parse(**kwargs)).usage is None
    asyncio.run(check())


def test_browser_client_has_no_overlapping_navigation(ctx, verifier, monkeypatch):
    from src import components, pipeline
    active = peak = 0
    async def browser(client, record):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(.02)
        active -= 1
        return {'page_text': record['url']}
    monkeypatch.setattr(components, 'browser_fetch', browser)
    install_services(verifier, ctx, ctx.path / 'cache')
    async def check():
        client = object()
        results = await asyncio.gather(*(pipeline.fetch_pages(client, [{'url': str(i)}]) for i in range(3)))
        assert [result[0]['page_text'] for result in results] == ['0', '1', '2']
    asyncio.run(check())
    assert peak == 1


def test_unchanged_pipeline_all_judge_stages_and_metrics(ctx, verifier, monkeypatch, capsys):
    from loop_research.benchmarks.wandr import grader
    from src import components, pipeline
    from src.config import TaskConfig, KeySpec, EvalConfig, CanonConfig, CanonKeyConfig, DedupConfig, DedupKeyConfig
    from src.metrics import metrics_for_tasks
    from src.runtime import clients
    ctx.config.models.root = "fixture-root"
    ctx.config.models.judge = "fixture-judge"
    stages = []
    class Backend:
        def __init__(self, context):
            self.ctx, self.config, self.last_usage = context, context.config, None
        def complete(self, prompt, *, schema, **kwargs):
            assert kwargs == {'purpose': 'grade', 'model': 'fixture-judge'}
            properties = schema['properties']
            if 'usable' in properties:
                stages.append('triage')
                response = {'usable': True, 'reason': 'fixture text'}
            elif 'canonical' in properties:
                stages.append('canon')
                response = {'canonical': f'fixture-canonical-{len(stages)}'}
            elif 'groups' in properties:
                stages.append('dedup')
                response = {'groups': []}
            else:
                stages.append('judge')
                response = {name: True for name, field in properties.items() if field.get('type') == 'boolean'}
                response.update(reasoning='hand-written fixture verdict', confidence=3)
            return json.dumps(response)
    class Page:
        async def goto(self, *args, **kwargs):
            return SimpleNamespace(status=200)
        async def inner_text(self, selector):
            return 'hand-written fixture quotation'
    class Browser:
        async def page(self, **kwargs):
            return Page()
    async def browser_pool(concurrency, client_load=None):
        return clients.ClientPool([Browser()])
    async def public_url(url, **kwargs):
        return 'example.org', ('93.184.215.14',)
    monkeypatch.setattr(grader, 'CodexBackend', Backend)
    monkeypatch.setattr(clients, 'create_browser_pool', browser_pool)
    monkeypatch.setattr(components, 'resolve_public_http_url', public_url)
    monkeypatch.setattr(components, '_BROWSER_SETTLE_DELAY', 0)
    install_services(verifier, ctx, ctx.path / 'cache')
    task = TaskConfig(name='fixture', task_template='Find two fixture entities.',
        key_hierarchy=[KeySpec('entity', required=2), KeySpec('url')],
        eval=EvalConfig(canon=CanonConfig(keys={'entity': CanonKeyConfig()}),
                        dedup=DedupConfig(keys={'entity': DedupKeyConfig()})))
    submission = ctx.path / 'results_fixture.jsonl'
    submission.parent.mkdir(parents=True, exist_ok=True)
    rows = [{'item': {'entity': f'fixture-{i}'}, 'url': f'https://example.org/{i}',
             'excerpts': ['hand-written fixture quotation'], 'answer': {'finding': 'fixture fact'}} for i in range(2)]
    submission.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    judged = asyncio.run(pipeline.run_pipeline([task], ctx.path / 'pipeline', submission_paths={'fixture': submission}))
    assert len(judged) == 2
    assert set(stages) == {'triage', 'canon', 'dedup', 'judge'}
    assert all(row['page_text'] == 'hand-written fixture quotation' for row in judged)
    report = verifier.report_from_metrics({'metrics': metrics_for_tasks(judged, [task])})
    rewards = verifier.scoremap_rewards(report['scoremap'])
    assert rewards['soft_f1_full'] == rewards['soft_recall_full'] == 1
    calls = len(stages)
    repeated = asyncio.run(pipeline.run_pipeline([task], ctx.path / 'pipeline', submission_paths={'fixture': submission}))
    assert len(repeated) == 2 and len(stages) == calls
    capsys.readouterr()
