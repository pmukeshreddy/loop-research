"""Command entry points. Live research runs only when its command is invoked."""
import base64
import hashlib
import importlib
from importlib import metadata
import json
from pathlib import Path
import subprocess
from typing import Annotated
from urllib.parse import unquote, urlparse
from uuid import uuid4

import typer
import yaml

from .archive import RunContext
from .benchmarks.widesearch.data import WideSearchData
from .codex_backend import CallBudget, CodexBackend
from .config import Config
from .repl_tools import ResearchTools
from .skills import init_library

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False,
                  help="Subscription-backed research, skill learning, and final evaluation.")
RLM_REVISION = "d04208afbad29ca675ab13478c40ee8bebc84bfe"


@app.callback()
def main(ctx: typer.Context,
         root: Annotated[Path, typer.Option(help="Workspace containing data, skills, runs and reports.")] = Path("."),
         config: Annotated[Path, typer.Option(help="Config file, relative to the workspace unless absolute.")] = Path("config.yaml")):
    root = root.resolve()
    ctx.obj = (root, config if config.is_absolute() else root / config)


def settings(ctx):
    root, path = ctx.obj
    return root, Config.load(path)


@app.command()
def init(ctx: typer.Context):
    """Create the workspace and a separate Git repository for learned skills."""
    root, path = ctx.obj
    for name in ("data", "runs", "reports", "docs"):
        (root / name).mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(Config().model_dump(), sort_keys=False))
    Config.load(path)
    init_library(root / "skills")
    verified = root / "docs/VERIFIED.md"
    if not verified.exists():
        verified.write_text("# Verification record\n\nStatus: unverified. No findings have been recorded.\n\n"
            "## RLM\n\nUnverified: pinned source, client interface, REPL injection, logger and usage.\n\n"
            "## Codex\n\nUnverified: version, flags, ChatGPT authentication and retry signals.\n\n"
            "## WideSearch\n\nUnverified: dataset/evaluator pins, formats, metrics and judge transport.\n\n"
            "## WANDR\n\nUnverified: dataset/harness pins, browser fetch, schemas, metrics and judge transport.\n\n"
            "## Open questions\n\nRun verification and record source paths, line references and command output.\n")
    typer.echo(str(root))


def verify_rlm():
    """Check installed Git provenance and the actual imported source bytes."""
    distribution = metadata.distribution("rlms")
    provenance = json.loads(distribution.read_text("direct_url.json") or "{}")
    module = importlib.import_module("rlm")
    source = Path(module.__file__).resolve()
    if provenance.get("dir_info", {}).get("editable"):
        parsed = urlparse(provenance["url"])
        if parsed.scheme != "file":
            raise ValueError("Editable RLM has no local source provenance")
        checkout = Path(unquote(parsed.path)).resolve()
        sha = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
        dirty = subprocess.check_output(["git", "-C", str(checkout), "status", "--porcelain", "--untracked-files=no"], text=True)
        if sha != RLM_REVISION or dirty or not source.is_relative_to(checkout):
            raise ValueError("RLM source is not clean at the pinned revision")
    else:
        vcs = provenance.get("vcs_info", {})
        if vcs.get("vcs") != "git" or vcs.get("commit_id") != RLM_REVISION:
            raise ValueError("Installed RLM has no matching pinned Git provenance")
        if source != Path(distribution.locate_file("rlm/__init__.py")).resolve():
            raise ValueError("Imported RLM is shadowed by a different source tree")
        files = [entry for entry in distribution.files or [] if str(entry).startswith("rlm/") and str(entry).endswith(".py")]
        if not files:
            raise ValueError("RLM source integrity cannot be checked: missing installation records")
        for entry in files:
            if not entry.hash:
                raise ValueError(f"RLM source integrity has no hash: {entry}")
            actual = hashlib.new(entry.hash.mode, Path(distribution.locate_file(entry)).read_bytes()).digest()
            if base64.urlsafe_b64encode(actual).decode().rstrip("=") != entry.hash.value:
                raise ValueError(f"RLM source integrity check failed: {entry}")
    return RLM_REVISION + "; " + str(source)


@app.command()
def verify(ctx: typer.Context):
    """Check local dependencies, authentication, pinned sources and browser readiness."""
    from .evaluate import verify_wandr
    root, config = settings(ctx)
    rows = []
    def check(name, action):
        try:
            detail = action()
        except (OSError, ValueError, ImportError, subprocess.SubprocessError) as exc:
            rows.append((name, False, str(exc)))
        else:
            rows.append((name, True, str(detail or "verified")))
    def codex(*args):
        result = subprocess.run([config.codex.bin, *args], check=True, text=True, capture_output=True, timeout=30)
        return (result.stdout + result.stderr).strip()
    def flags():
        help_text = codex("exec", "--help")
        required = ("--sandbox", "--skip-git-repo-check", "--cd", "--output-last-message", "--output-schema",
                    "--model", "--config", "--json", "--color", "--ephemeral", "--ignore-user-config", "read-only", "stdin")
        missing = [flag for flag in required if flag not in help_text]
        if missing:
            raise ValueError("Missing Codex capabilities: " + ", ".join(missing))
        return "Required exec flags and stdin prompt supported"
    def authentication():
        status = codex("login", "status")
        if "logged in using chatgpt" not in status.casefold():
            raise ValueError("ChatGPT login required; run codex login. Status: " + status)
        return status
    check("Codex version", lambda: codex("--version"))
    check("Codex exec flags", flags)
    check("Codex ChatGPT auth", authentication)
    check("RLM installed source", verify_rlm)
    benchmark = WideSearchData(root, config)
    check("WideSearch dataset", benchmark.verify_data)
    check("WideSearch evaluator", benchmark.verify_code)
    try:
        rows.extend(verify_wandr(root, config))
    except (OSError, ValueError, RuntimeError, ImportError, subprocess.SubprocessError) as exc:
        rows.append(("WANDR", False, str(exc)))
    typer.echo("STATUS\tCHECK\tDETAIL")
    for name, passed, detail in rows:
        typer.echo(f"{'PASS' if passed else 'FAIL'}\t{name}\t{detail}")
    if not all(passed for _, passed, _ in rows):
        raise typer.Exit(1)


@app.command("prepare-data")
def prepare_data(ctx: typer.Context):
    """Acquire and verify pinned sources; persist deterministic data selections."""
    from .evaluate import prepare_wandr
    root, config = settings(ctx)
    WideSearchData(root, config).prepare()
    prepare_wandr(root, config)
    typer.echo(str(root / "data"))


def smoke_run(root, config):
    """Run a plain call, search, fetch and non-benchmark RLM computation."""
    from rlm.logger import RLMLogger
    from .rlm_codex_client import CodexRLM
    ctx = RunContext(Path(root), "smoke-" + uuid4().hex, config)
    ctx.initialize("empty", kind="smoke", benchmark="toy")
    task_ctx = ctx.task("smoke")
    task_ctx.path.mkdir(parents=True, exist_ok=True)
    budget = CallBudget(config.agent.max_codex_calls, config.agent.task_timeout_s)
    backend = CodexBackend(task_ctx, budget=budget)
    plain = backend.complete("Reply with exactly READY.", purpose="root", model=config.models.root)
    if plain.strip() != "READY":
        raise ValueError("Plain smoke call did not return READY")
    tools = ResearchTools(backend, task_ctx)
    hits = tools.search("Python programming language official website", k=1)
    if not hits:
        raise ValueError("Smoke search returned no valid URLs")
    page = tools.fetch("https://www.python.org/")
    if not page.strip() or page == "FETCH_FAILED":
        raise ValueError("Smoke fetch failed")
    logger = RLMLogger(log_dir=str(task_ctx.path))
    logger.log_file_path = str(task_ctx.path / "trajectory.jsonl")
    rlm = CodexRLM(backend, root_model=config.models.root, sub_model=config.models.sub,
        max_depth=config.rlm.max_depth, max_iterations=config.rlm.max_iterations,
        max_timeout=budget.remaining(), max_concurrent_subcalls=config.codex.max_concurrent,
        custom_tools=tools.injected(), logger=logger)
    prompt = ('Use the Python REPL to compute sum([2, 3]). Set answer["content"] to the string result '
              'and answer["ready"] to True. Return only the result. This is a non-benchmark toy task.')
    result = rlm.completion(prompt, root_prompt=prompt)
    if result.response.strip() != "5":
        raise ValueError("RLM smoke computation returned an incorrect result")
    task_ctx.save("smoke.json", {"plain": plain, "search": hits, "fetch_url": "https://www.python.org/", "rlm": result.response})
    summary = ctx.load("run_summary.json")
    ctx.save("run_summary.json", {**summary, "status": "complete"})
    return ctx.run_id


@app.command()
def smoke(ctx: typer.Context):
    """Make live subscription and web calls on a non-benchmark toy task."""
    typer.echo(smoke_run(*settings(ctx)))


@app.command()
def run(ctx: typer.Context, split: Annotated[str, typer.Option()] = "train",
        n: Annotated[int, typer.Option(min=1)] = 1):
    """Research WideSearch training tasks without grading them."""
    if split != "train":
        raise typer.BadParameter("run only accepts --split train; use evaluate for validation/final tasks")
    from .loop import run_train
    root, config = settings(ctx)
    typer.echo(run_train(root, config, n))


@app.command()
def grade(ctx: typer.Context, run: Annotated[str, typer.Option("--run")]):
    """Grade a completed research archive using its original configuration."""
    from .evaluate import grade_run
    typer.echo(grade_run(ctx.obj[0], run))


@app.command()
def improve(ctx: typer.Context, rounds: Annotated[int, typer.Option(min=1)],
            resume: Annotated[bool, typer.Option()] = False):
    """Learn skills from WideSearch train tasks and gate them on validation tasks."""
    from .loop import improve as improve_loop
    root, config = settings(ctx)
    typer.echo(improve_loop(root, config, rounds, resume=resume))


@app.command()
def evaluate(ctx: typer.Context, benchmark: Annotated[str, typer.Option()],
             split: Annotated[str | None, typer.Option()] = None,
             final: Annotated[bool, typer.Option()] = False):
    """Evaluate validation tasks or compare final and empty libraries with --final."""
    from .evaluate import evaluate as evaluate_benchmark
    root, config = settings(ctx)
    result = evaluate_benchmark(root, config, benchmark, split=split, final=final)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


@app.command()
def report(ctx: typer.Context):
    """Build the summary, rounds CSV and curve from archived files only."""
    from .report import build_report
    typer.echo(str(build_report(ctx.obj[0])))


if __name__ == "__main__":
    app()
