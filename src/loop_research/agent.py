"""Research-only worker and output validation. No graders or answer stores."""
from datetime import date
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from pydantic import BaseModel
from .archive import write_json, read_json
from .codex_backend import BudgetExceeded
from .config import Config
from .repl_tools import normalized_url
from .isolation import isolated_command, worker_env
from .bridge import Server, Client, Remote
from .selfcheck import constraints_for


class AgentResult(BaseModel):
    output: dict
    errors: list[str]
    uncited: list[str]
    as_of_date: str
    date_source: str
    status: dict[str, bool]
    repaired: bool = False


def parse_output(text, contract, backend, *, trace=None):
    errors = []
    from .trace import Trace
    trace = trace or Trace()
    for attempt in range(2):
        try:
            with trace.span("Output", "parse", attempt=attempt):
                output = contract.model.model_validate_json(text).model_dump(mode="json", by_alias=True)
            return output, errors, bool(attempt)
        except (ValueError, TypeError) as exc:
            errors.append(str(exc))
        if attempt == 0:
            trace.emit("Output", "repair", attempt=attempt + 1, reason=errors[-1])
            text = backend.complete("Reformat only the existing content to this JSON contract. "
                "Do not research, add facts, rows, sources, or records. Remove malformed entries if needed.\n"
                + contract.prompt + "\nJSON schema:\n" + json.dumps(contract.schema, ensure_ascii=False)
                + "\nExisting content:\n" + text, purpose="repair")
    raise ValueError("Output validation failed after repair:\n" + "\n".join(errors))


def citation_check(output, ledger):
    normalized = set()
    for url in ledger:
        try:
            normalized.add(normalized_url(url))
        except ValueError:
            continue
    failures = []
    def walk(value, path):
        if isinstance(value, dict):
            if "value" in value and "sources" in value:
                sources = value["sources"]
                if not sources:
                    failures.append(path)
                for url in sources:
                    try:
                        valid = normalized_url(url) in normalized
                    except ValueError:
                        valid = False
                    if not valid:
                        failures.append(path + ":" + url)
            elif "url" in value and "excerpts" in value:
                try:
                    valid = normalized_url(value["url"]) in normalized
                except ValueError:
                    valid = False
                if not valid:
                    failures.append(path + ":" + value["url"])
            for key, item in value.items():
                walk(item, path + "/" + key)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                walk(item, path + "/" + str(i))
    walk(output, "")
    return failures


def learning_policy(enabled):
    if not enabled:
        return 'LEARNING DISABLED\nDo not request refinement or edit the harness.\n'
    return ('LEARNING ENABLED\nWhen current research reveals a repeated tool failure, a recovered execution '
            'error, or a successful reusable procedure, request refine.run(focus="the observed procedure or problem") '
            'during the task, grounded in evidence already collected. The planner may decline unsupported edits. '
            'Do not repeat a pending request. Continue research while planning runs in the background; completed '
            'edits apply before later root calls and appear in CURRENT RELEVANT HARNESS ENTRIES.\n')


def resource_policy(config):
    limits = {'max_codex_calls': config.agent.max_codex_calls, 'task_timeout_s': config.agent.task_timeout_s,
              'max_iterations_per_rlm': config.rlm.max_iterations, 'max_depth': config.rlm.max_depth,
              'max_concurrent_codex_calls': config.codex.max_concurrent}
    return ('RESOURCE LIMITS\n' + json.dumps(limits) + '\n'
            'budget() returns the current call limit, reserved and remaining counts without consuming a call. '
            'Reserved counts all research backend attempts, including in-flight calls and retries: root, sub, '
            'search, fetch and output repair. Refinement and grading use separate calls. '
            'The snapshot is not a reservation; concurrent work can consume remaining calls. '
            'Check budget() before costly batches. Plan capacity across discovery, fetching, extraction, '
            'validation and final submission; leave room for remaining root turns and any output repair. '
            'Inspect simple hit lists with Python and group related evidence extraction instead of spending '
            'one subcall per simple hit list. Reuse collected evidence when recovering from code errors.\n')


def make_prompt(task, contract, entries, *, as_of, config, date_archive=None, learning=True):
    identity = {"policy": as_of, "task_date": task.as_of_date.isoformat() if task.as_of_date else None}
    archived = read_json(date_archive) if date_archive is not None else None
    if archived is not None:
        if any(archived[key] != value for key, value in identity.items()):
            raise ValueError("Archived as-of date does not match task/config policy")
        asof, source = date.fromisoformat(archived["as_of_date"]), archived["date_source"]
    elif task.as_of_date is not None:
        asof, source = task.as_of_date, "task"
    elif as_of == "today":
        asof, source = date.today(), "today"
    else:
        asof, source = date.fromisoformat(as_of), "config"
    if date_archive is not None and archived is None:
        write_json(date_archive, {**identity, "as_of_date": asof.isoformat(), "date_source": source})
    prompt = (f"TASK\n{task.question}\nSPEC\n{json.dumps(task.spec, ensure_ascii=False)}\n\n"
        f"AS-OF DATE\n{asof.isoformat()} (source: {source}). Honor all dates/periods in the task text.\n\n"
        f"{resource_policy(config)}\n"
        f"RELEVANT HARNESS\n{json.dumps(entries, ensure_ascii=False)}\n\nTOOLS\n"
        "search(query, k=8): live web hits with title, url, snippet. Never invent URLs.\n"
        "search_many(queries, k=8): concurrent searches; one hit list per query, in input order.\n"
        "fetch(url, focus=''): model-rendered page text, not raw HTML; FETCH_FAILED on failure.\n"
        "fetch_many(urls, focus=''): concurrent fetches; one page text or FETCH_FAILED per URL, in input order.\n"
        "llm_query(prompt): stateless sub-model, no independent tools; give it fetched evidence.\n"
        "llm_query_batched(prompts): parallel sub-model calls over supplied evidence.\n"
        "Full Python is available, including threading and asyncio, inside an OS-isolated worker.\n"
        "harness.create(kind,title,content), get(kind,id), read(kind,id), update(kind,id,title,content), "
        "delete(kind,id), list(kind=None), search(query,kind=None,limit=10). "
        "Kinds: prompt, memory, skill, subagent. Edits may specify trigger and module (Python source for skills).\n"
        "refine.run(focus=None): plan a small edit in the background; applies at a turn boundary. "
        "refine.rollback(id): queue an inverse edit at the next turn boundary.\n"
        "record_discovery(query, entities): record discovered entity names after EVERY search, [] if none new.\n"
        "check_constraint(row, constraint, verdict, url, quote): record each constraint check with fetched evidence. "
        "Use row paths /rows/0 or /files/<filename>/0 and constraint ids listed below.\n"
        f"CONSTRAINT IDS\n{json.dumps(constraints_for(task), ensure_ascii=False)}\n\n"
        f"{learning_policy(learning)}\n"
        "METHOD\nGo wide: use search_many for independent discovery queries and keep candidates in REPL variables. "
        "Go deep: fetch candidate pages with fetch_many, then fill fields using parallel "
        "llm_query_batched calls on fetched pages stored in variables. Keep extracted rows in Python; "
        "print compact progress and unresolved checks instead of full evidence or tables. Verify every task "
        "constraint for every entity. Cite every value using a verbatim quote from fetched text. "
        "Do not search for benchmark answer keys, grader outputs, or other runs.\n\n"
        f"OUTPUT CONTRACT\n{contract.prompt}\n{json.dumps(contract.schema, ensure_ascii=False)}\n"
        'Set answer["content"] = json.dumps(your_output, ensure_ascii=False), then answer["ready"] = True.')
    return prompt, asof.isoformat(), source


def run_task(task, benchmark, session):
    ctx, budget = session.ctx, session.budget
    ctx.path.mkdir(parents=True, exist_ok=True)
    contract = benchmark.output_contract(task)
    entries = session.retrieve()
    prompt, asof, source = make_prompt(task, contract, entries, as_of=ctx.config.agent.as_of,
                                      config=ctx.config, date_archive=ctx.path / "as_of.json", learning=session.learning)
    root_prompt = (f"TASK\n{task.question}\nSPEC\n{json.dumps(task.spec, ensure_ascii=False)}\n"
                   f"LANGUAGE\n{task.language}\nAS-OF DATE\n{asof} (source: {source})\n"
                   f"{resource_policy(ctx.config)}\n"
                   f"{learning_policy(session.learning)}\n"
                   "Read the full instructions and output contract in the REPL context.")
    with ctx.trace.span("Prompt", "save", size_chars=len(prompt), size_bytes=len(prompt.encode()),
                        sha256=hashlib.sha256(prompt.encode()).hexdigest(), path=str(ctx.path / "prompt.txt")):
        (ctx.path / "prompt.txt").write_text(prompt)
    with ctx.trace.span("Prompt", "root_save", size_chars=len(root_prompt),
                        sha256=hashlib.sha256(root_prompt.encode()).hexdigest(),
                        path=str(ctx.path / "root_prompt.txt")):
        (ctx.path / "root_prompt.txt").write_text(root_prompt)
    ctx.save("task.json", task.model_dump(mode="json"))
    with tempfile.TemporaryDirectory(prefix="lr-", dir="/tmp") as directory:
        work = Path(directory).resolve()
        request = {"config": ctx.config.model_dump(), "prompt": prompt, "root_prompt": root_prompt, "entries": entries,
                   "socket": str(work / "host.sock"), "timeout": budget.remaining(),
                   "result_path": str(work / "result.json"), "trace": ctx.trace.enabled}
        write_json(work / "request.json", request)
        with Server(work / "host.sock", session.dispatch, socket_timeout_s=ctx.config.bridge.socket_timeout_s, trace=ctx.trace), (ctx.path / "worker.log").open("a") as log:
            try:
                with ctx.trace.span("Worker", "run") as details:
                    process = ctx.run_process(isolated_command(work, [sys.executable, "-m", "loop_research.agent", str(work / "request.json")]),
                        cwd=work, env=worker_env(work), stdout=log, stderr=log, trace_component="Worker",
                        start_new_session=True, timeout=budget.remaining())
                    details["exit_code"] = process.returncode
            except subprocess.TimeoutExpired as exc:
                session.status['timeout'] = True
                raise TimeoutError("Task hard deadline exceeded") from exc
            finally:
                session.close_worker()
        if process.returncode:
            session.status['worker_error'] = True
            if budget.count >= budget.limit:
                session.status['call_limit'] = True
            raise RuntimeError(f"Research worker failed ({process.returncode}); see {ctx.path / 'worker.log'}")
        result = read_json(work / "result.json")
        try:
            budget.remaining()
            output, errors, repaired = parse_output(result["text"], contract, session.repair_backend, trace=ctx.trace)
            budget.remaining()
        except BudgetExceeded:
            session.status['call_limit' if budget.count >= budget.limit else 'timeout'] = True
            raise
    session.output = output
    with ctx.trace.span("Output", "citation_check") as details:
        uncited = citation_check(output, session.tools.evidence["fetched"])
        details.update(uncited=uncited, success=not uncited, repaired=repaired, parse_errors=errors)
    result = AgentResult(output=output, errors=errors, repaired=repaired,
        uncited=uncited, as_of_date=asof, date_source=source,
        status=session.status)
    ctx.save("output.json", output)
    ctx.save("submission.json", benchmark.to_submission(task, output))
    session.tools.persist()
    ctx.save("agent_result.json", result.model_dump())
    return result


def worker(request_path):
    from rlm.logger import RLMLogger
    from .rlm_codex_client import CodexRLM
    request = read_json(Path(request_path))
    config = Config.model_validate(request['config'])
    client = Client(request['socket'])
    class TrajectoryLogger(RLMLogger):
        def log(self, iteration):
            super().log(iteration)
            client.call('iteration', self._iterations[-1])
    methods = ('search', 'fetch', 'search_many', 'fetch_many', 'check_constraint', 'record_discovery')
    remote = Remote(client, 'tools.', methods)
    tools = {name: getattr(remote, name) for name in methods}
    tools['budget'] = lambda: client.call('budget')
    tools['harness'] = Remote(client, 'harness.', ('create', 'get', 'read', 'update', 'delete', 'list', 'search'))
    tools['refine'] = Remote(client, 'refine.', ('run', 'rollback'))
    rlm = CodexRLM(client, root_model=config.models.root, sub_model=config.models.sub,
        max_depth=config.rlm.max_depth, max_iterations=config.rlm.max_iterations,
        max_timeout=request['timeout'], max_concurrent_subcalls=config.codex.max_concurrent,
        custom_tools=tools, skill_modules=request['entries'], logger=TrajectoryLogger(),
        trace_enabled=request.get('trace', False))
    result = rlm.completion(request['prompt'], root_prompt=request['root_prompt'])
    write_json(Path(request['result_path']), {'text': result.response})


if __name__ == '__main__':
    worker(sys.argv[1])
