"""Research-only worker and output validation. No graders or answer stores."""
from datetime import date
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from pydantic import BaseModel
from .archive import RunContext, count_codex_calls, write_json, read_json
from .codex_backend import CodexBackend, CallBudget
from .config import Config
from .repl_tools import ResearchTools, normalized_url
from .skills import render_playbook


class AgentResult(BaseModel):
    output: dict
    errors: list[str]
    uncited: list[str]
    as_of_date: str
    date_source: str
    repaired: bool = False


def parse_output(text, contract, backend):
    errors = []
    for attempt in range(2):
        try:
            output = contract.model.model_validate_json(text).model_dump(mode="json", by_alias=True)
            return output, errors, bool(attempt)
        except (ValueError, TypeError) as exc:
            errors.append(str(exc))
        if attempt == 0:
            text = backend.complete("Reformat only the existing content to this JSON contract. "
                "Do not research, add facts, rows, sources, or records. Remove malformed entries if needed.\n"
                + contract.prompt + "\nJSON schema:\n" + json.dumps(contract.schema, ensure_ascii=False)
                + "\nExisting content:\n" + text, purpose="repair")
    return contract.empty, errors, True


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


def make_prompt(task, contract, playbook):
    asof = task.as_of_date
    if asof is None:
        fallback = task.raw.get("fallback_as_of_date")
        asof = date.fromisoformat(fallback) if fallback else date.today()
    source = "task" if task.as_of_date else "today_fallback"
    prompt = (f"TASK\n{task.question}\nSPEC\n{json.dumps(task.spec, ensure_ascii=False)}\n\n"
        f"AS-OF DATE\n{asof.isoformat()} (source: {source}). Honor all dates/periods in the task text.\n\n"
        f"RESEARCH PLAYBOOK\n{playbook}\n\nTOOLS\n"
        "search(query, k=8): live web hits with title, url, snippet. Never invent URLs.\n"
        "search_batched(queries, k=8): concurrent searches; one hit list per query, in input order.\n"
        "fetch(url, focus=''): model-rendered page text, not raw HTML; FETCH_FAILED on failure.\n"
        "fetch_batched(urls, focus=''): concurrent fetches; one page text or FETCH_FAILED per URL, in input order.\n"
        "llm_query(prompt): stateless sub-model, no independent tools; give it fetched evidence.\n"
        "llm_query_batched(prompts): parallel sub-model calls over supplied evidence.\n"
        "Python imports: json, re, math, statistics, collections, itertools, datetime, decimal. "
        "Filesystem, network clients, shell, introspection and private attributes are unavailable.\n\n"
        "METHOD\nGo wide: use search_batched for independent discovery queries and keep candidates in REPL variables. "
        "Go deep: fetch candidate pages with fetch_batched, then fill fields using parallel "
        "llm_query_batched calls on fetched pages. Verify every task "
        "constraint for every entity. Cite every value using a verbatim quote from fetched text. "
        "Do not search for benchmark answer keys, grader outputs, or other runs.\n\n"
        f"OUTPUT CONTRACT\n{contract.prompt}\n{json.dumps(contract.schema, ensure_ascii=False)}\n"
        'Set answer["content"] = json.dumps(your_output, ensure_ascii=False), then answer["ready"] = True.')
    return prompt, asof.isoformat(), source


def run_task(task, benchmark, library_dir, run_ctx):
    budget = CallBudget(run_ctx.config.agent.max_codex_calls, run_ctx.config.agent.task_timeout_s)
    run_ctx.path.mkdir(parents=True, exist_ok=True)
    contract = benchmark.output_contract(task)
    playbook = render_playbook(task, library_dir, run_ctx.config.skills.max_playbook_chars) if library_dir else ""
    prompt, asof, source = make_prompt(task, contract, playbook)
    (run_ctx.path / "prompt.txt").write_text(prompt)
    (run_ctx.path / "playbook.txt").write_text(playbook)
    run_ctx.save("task.json", task.model_dump(mode="json"))
    with tempfile.TemporaryDirectory(prefix="loop-task-") as tmp:
        tmp = Path(tmp)
        request = {"root": str(run_ctx.root), "run_id": run_ctx.run_id, "task_id": run_ctx.task_id,
                   "config": run_ctx.config.model_dump(), "prompt": prompt,
                   "deadline": budget.deadline,
                   "result_path": str(tmp / "result.json")}
        write_json(tmp / "request.json", request)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        with (run_ctx.path / "worker.log").open("a") as log:
            process = subprocess.Popen([sys.executable, "-m", "loop_research.agent", str(tmp / "request.json")],
                cwd=tmp, env=env, stdout=log, stderr=log, start_new_session=True)
            finished = False
            try:
                code = process.wait(timeout=budget.remaining())
                finished = True
            except subprocess.TimeoutExpired as exc:
                raise TimeoutError("Task hard deadline exceeded") from exc
            finally:
                if not finished:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass  # The worker may have exited between interruption and cleanup.
                    process.wait()
        if code:
            raise RuntimeError(f"Research worker failed ({code}); see {run_ctx.path / 'worker.log'}")
        result = read_json(tmp / "result.json")
        budget.remaining()
        budget.count = count_codex_calls(run_ctx.path, exclude_purposes=("grade",))
        output, errors, repaired = parse_output(result["text"], contract, CodexBackend(run_ctx, budget=budget))
        budget.remaining()
    result = AgentResult(output=output, errors=errors, repaired=repaired,
        uncited=citation_check(output, run_ctx.load("url_ledger.json", [])), as_of_date=asof, date_source=source)
    run_ctx.save("output.json", output)
    run_ctx.save("agent_result.json", result.model_dump())
    run_ctx.save("submission.json", benchmark.to_submission(task, output))
    for name, empty in (("tool_cache.json", {}), ("url_ledger.json", [])):
        if not (run_ctx.path / name).exists():
            run_ctx.save(name, empty)
    (run_ctx.path / "trajectory.jsonl").touch(exist_ok=True)
    return result


def worker(request_path):
    from rlm.logger import RLMLogger
    from .rlm_codex_client import CodexRLM
    request = read_json(Path(request_path))
    config = Config.model_validate(request["config"])
    ctx = RunContext(Path(request["root"]), request["run_id"], config, request["task_id"])
    budget = CallBudget(config.agent.max_codex_calls, config.agent.task_timeout_s)
    budget.deadline = request.get("deadline", budget.deadline)
    budget.count = count_codex_calls(ctx.path, exclude_purposes=("grade",))
    backend = CodexBackend(ctx, budget=budget)
    tools = ResearchTools(backend, ctx)
    logger = RLMLogger(log_dir=str(ctx.path))
    logger.log_file_path = str(ctx.path / "trajectory.jsonl")
    rlm = CodexRLM(backend, root_model=config.models.root, sub_model=config.models.sub,
        max_depth=config.rlm.max_depth, max_iterations=config.rlm.max_iterations,
        max_timeout=budget.remaining(), max_concurrent_subcalls=config.codex.max_concurrent,
        custom_tools=tools.injected(), logger=logger)
    result = rlm.completion(request["prompt"], root_prompt=request["prompt"])
    write_json(Path(request["result_path"]), {"text": result.response})


if __name__ == "__main__":
    worker(sys.argv[1])
