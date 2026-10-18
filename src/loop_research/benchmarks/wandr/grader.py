import asyncio
import importlib
from html import escape
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from openai.lib._parsing._completions import _parse_content, type_to_response_format_param
from .data import CODE_REVISION, DATASET_REVISION, WandrData
from .. import GradeResult
from ...archive import GradeContext, digest, read_json, write_json
from ...codex_backend import CodexBackend
from ...config import Config


def subscription_auth(binary):
    status = subprocess.run([binary, 'login', 'status'], capture_output=True, text=True, check=True)
    if 'chatgpt' not in (status.stdout + status.stderr).lower():
        raise RuntimeError('WANDR judging requires Codex ChatGPT subscription login')


class CodexTransport:
    def __init__(self, ctx, cache):
        self.backend = CodexBackend(ctx)
        self.cache = cache
        self.pending = {}
        self.chat = SimpleNamespace(completions=self)
        self.beta = SimpleNamespace(chat=self.chat)

    async def parse(self, *, response_format, **request):
        return await self.complete(response_format, request)

    async def create(self, **request):
        return await self.complete(None, request)

    async def complete(self, response_format, request):
        schema = (type_to_response_format_param(response_format)['json_schema']['schema']
                  if response_format is not None else None)
        identity = {'task': self.backend.ctx.task_id, 'request': request, 'schema': schema,
                    'config': self.backend.config.model_dump(), 'code': CODE_REVISION}
        path = self.cache / (digest(identity) + '.json')
        saved = read_json(path)
        if saved is None:
            # Upstream stage timeouts must not discard an already-running Codex call.
            if path not in self.pending:
                prompt = 'Execute this judge conversation. Return only its requested response.\n' + json.dumps(request['messages'], ensure_ascii=False)
                def call():
                    text = self.backend.complete(prompt, purpose='grade', schema=schema,
                                                 model=self.backend.config.models.judge)
                    if response_format is not None:
                        _parse_content(response_format, text)
                    result = {'text': text, 'usage': self.backend.last_usage, 'request': identity}
                    write_json(path, result)
                    return result
                pending = asyncio.create_task(asyncio.to_thread(call))
                self.pending[path] = pending
                def finished(task):
                    self.pending.pop(path, None)
                    if not task.cancelled():
                        task.exception()  # Retrieve failures even if upstream already timed out.
                pending.add_done_callback(finished)
            saved = await asyncio.shield(self.pending[path])
        parsed = _parse_content(response_format, saved['text']) if response_format else None
        usage = saved['usage']
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed, content=saved['text']))],
            usage=SimpleNamespace(prompt_tokens=usage.get('input_tokens'), completion_tokens=usage.get('output_tokens')) if usage else None)


def install_services(verifier, ctx, cache):
    from src import components, pipeline
    from src.runtime.clients import ClientPool, create_browser_pool
    browser_locks = {}

    async def browser_pages(client, records):
        results = []
        for record in records:
            # The harness assigns clients when enqueueing, before a worker is free.
            async with browser_locks.setdefault(client, asyncio.Lock()):
                fetched = await components.browser_fetch(client, record)
            results.append({**fetched, 'content': fetched['page_text']} if fetched is not None else None)
        return results

    transport = CodexTransport(ctx, cache)

    def judge_pool(concurrency, client_load=None, *, max_retries=3):
        return ClientPool([transport])

    pipeline.fetch_pages = browser_pages
    pipeline.create_fetch_pool = create_browser_pool
    pipeline.FETCH_BATCH_SIZE = pipeline.FETCH_CLIENT_LOAD = 1
    pipeline.FETCH_CONCURRENCY = pipeline.BROWSER_CONCURRENCY
    pipeline.BROWSER_FALLBACK = False
    pipeline.create_openai_pool = judge_pool
    verifier._validate_runtime_env = lambda env: subscription_auth(ctx.config.codex.bin)


def record_errors(records, submitted):
    verdicts = [r['judge']['excerpts_faithful'] for r in records
                if isinstance(r.get('judge', {}).get('excerpts_faithful'), bool)]
    failures = sum(not value for value in verdicts)
    return {'records': [{'task': r.get('task_name'), 'url': r['url'], 'item': r['item'],
                        'failed_checks': [k for k, v in r.get('judge', {}).items() if v is False],
                        'judge': r.get('judge', {})} for r in records],
            'excerpt_failures': failures, 'excerpt_judged': len(verdicts),
            'excerpt_failure_rate': failures / len(verdicts) if verdicts else None,
            'unjudged_records': submitted - len(records)}


def load_verifier(package):
    tests = package / 'tests'
    sys.path[:0] = [str(tests), str(tests / 'wandr_core')]
    return importlib.import_module('verify')


def worker(request_path):
    request = read_json(Path(request_path))
    ctx = GradeContext(Path(request['root']), request['run_id'], Config.model_validate(request['config']), request['task_id'])
    package, work = Path(request['package']), Path(request['work'])
    verifier = load_verifier(package)
    install_services(verifier, ctx, work / 'judge_cache')
    os.environ['LOGS_DIR'] = str(work / 'logs')
    sys.argv = ['verify.py', '--workspace-dir', str(work / 'submission'), '--task-dir',
                str(package / 'tests/wandr_task'), '--instruction-path', str(package / 'instruction.md'),
                '--output-dir', str(work / 'pipeline')]
    code = verifier.main()
    if code:
        raise RuntimeError(f"WANDR verifier failed: {read_json(work / 'logs/error.json')}")
    metrics = read_json(work / 'logs/wandr_metrics.json')
    records = verifier.report_from_metrics(metrics)['records'] if metrics is not None else []
    errors = record_errors(records, request['submitted'])
    if metrics is None:
        errors['invalid_submission'] = True
    result = GradeResult(metrics=read_json(work / 'logs/reward.json'), primary_metric='soft_f1_full',
        errors=errors, judge=ctx.config.judge_label,
        provenance={'fetch': 'wandr-browser', 'dataset_revision': DATASET_REVISION,
                    'code_revision': CODE_REVISION, 'harness_primary_metric': 'soft_recall_full',
                    'artifacts': str(work.relative_to(ctx.root))})
    label = f'fetch: wandr-browser | judge: {ctx.config.judge_label} | project primary: soft_f1_full | harness primary: soft_recall_full'
    for report in (*work.glob('logs/report.*'), *work.glob('artifacts/wandr_viewer.*')):
        banner = '<p>' + escape(label) + '</p>\n' if report.suffix == '.html' else label + '\n\n'
        report.write_text(banner + report.read_text())
    write_json(work / 'result.json', result.model_dump())


class WandrBenchmark(WandrData):
    def grade(self, task, submission, run_ctx):
        submission = self.to_submission(task, {'files': submission})
        key = digest({'submission': submission, 'config': self.config.model_dump(), 'code': CODE_REVISION})
        work = run_ctx.path / 'wandr' / key
        cached = read_json(work / 'result.json')
        if cached is not None:
            return GradeResult.model_validate(cached)
        directory = work / 'submission'
        directory.mkdir(parents=True, exist_ok=True)
        for filename, rows in submission.items():
            (directory / filename).write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))
        request = {'root': str(run_ctx.root), 'run_id': run_ctx.run_id, 'task_id': task.task_id,
                   'config': self.config.model_dump(), 'package': str(self.package(task.task_id)),
                   'work': str(work), 'submitted': sum(map(len, submission.values()))}
        write_json(work / 'request.json', request)
        env = {k: v for k, v in os.environ.items() if 'API_KEY' not in k and not k.startswith(('OPENAI_', 'AZURE_OPENAI_', 'WANDR_'))}
        env['PYTHONPATH'] = str(Path(__file__).resolve().parents[3])
        with (work / 'worker.log').open('w') as log:
            process = run_ctx.run_process([sys.executable, '-m', __name__, str(work / 'request.json')],
                                      env=env, stdout=log, stderr=subprocess.STDOUT)
        if process.returncode:
            raise RuntimeError(f'WANDR verifier failed; see {work / "worker.log"}')
        return GradeResult.model_validate(read_json(work / 'result.json'))

    def verify(self):
        self.verify_sources()
        package = self.package(self.load_tasks()[0].task_id)
        script = """import asyncio, sys
from pathlib import Path
from loop_research.benchmarks.wandr.grader import load_verifier
verifier = load_verifier(Path(sys.argv[1]))
manifest = verifier.load_manifest()
verifier._load_task_configs(manifest, Path(sys.argv[1]) / 'tests/wandr_task')
from src.runtime.browser import BrowserClient
async def check():
    client = BrowserClient()
    try:
        await client.start()
        page = await client.page()
        await page.goto('about:blank')
    finally:
        await client.close()
asyncio.run(check())
print('Pinned verifier imports; official BrowserClient launches successfully')
"""
        result = subprocess.run([sys.executable, '-c', script, str(package)], capture_output=True, text=True, timeout=120)
        if result.returncode:
            raise RuntimeError('WANDR browser readiness failed: ' + result.stderr)
        return [('WANDR', True, f'{DATASET_REVISION} / {CODE_REVISION}; fetch: wandr-browser'),
                ('WANDR browser', True, result.stdout.strip())]


if __name__ == '__main__':
    worker(sys.argv[1])
