"""CLI for continual research. Model calls occur only in research and stream."""
import base64
from enum import Enum
import hashlib
import importlib
from importlib import metadata
import json
from pathlib import Path
import shutil
import subprocess
from typing import Annotated
from urllib.parse import unquote, urlparse

import typer

from .benchmarks.widesearch.data import WideSearchData
from .config import Config

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False,
                  help="Subscription-backed research with a continual harness.")
RLM_REVISION = "d04208afbad29ca675ab13478c40ee8bebc84bfe"


class Benchmark(str, Enum):
    widesearch = "widesearch"
    wandr = "wandr"


@app.callback()
def main(ctx: typer.Context,
         root: Annotated[Path, typer.Option(help="Workspace containing data, harness, runs and reports.")] = Path("."),
         config: Annotated[Path, typer.Option(help="Config file, relative to the workspace unless absolute.")] = Path("config.yaml")):
    root = root.resolve()
    ctx.obj = (root, config if config.is_absolute() else root / config)


def settings(ctx):
    root, path = ctx.obj
    return root, Config.load(path)


@app.command()
def init(ctx: typer.Context):
    """Create a workspace, copying the repository config only when absent."""
    from .harness import Harness
    root, path = ctx.obj
    for name in ("data", "runs", "reports", "docs"):
        (root / name).mkdir(parents=True, exist_ok=True)
    if not path.exists():
        source = Path(__file__).resolve().with_name("config.yaml")
        if not source.exists():
            source = Path(__file__).resolve().parents[2] / "config.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, path)
    Config.load(path)
    Harness(root / "harness")
    verified = root / "docs/VERIFIED.md"
    if not verified.exists():
        verified.write_text("# Verification record\n\nStatus: unverified. No findings have been recorded.\n\n"
            "Run verify and record source paths, line references and command output.\n")
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
    """Check local sources, authentication, browser readiness and OS isolation."""
    from .benchmarks.wandr.grader import WandrBenchmark
    from .isolation import verify_isolation
    root, config = settings(ctx)
    rows = []
    def check(name, action):
        try:
            detail = action()
        except (OSError, ValueError, RuntimeError, ImportError, subprocess.SubprocessError) as exc:
            rows.append((name, False, str(exc)))
        else:
            rows.append((name, True, str(detail or "verified")))
    def codex(*args):
        result = subprocess.run([config.codex.bin, *args], check=True, text=True, capture_output=True,
                                timeout=config.verify.codex_timeout_s)
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
    check("REPL isolation", verify_isolation)
    benchmark = WideSearchData(root, config)
    check("WideSearch dataset", benchmark.verify_data)
    check("WideSearch evaluator", benchmark.verify_code)
    try:
        rows.extend(WandrBenchmark(root, config).verify())
    except (OSError, ValueError, RuntimeError, ImportError, subprocess.SubprocessError) as exc:
        rows.append(("WANDR", False, str(exc)))
    typer.echo("STATUS\tCHECK\tDETAIL")
    for name, passed, detail in rows:
        typer.echo(f"{'PASS' if passed else 'FAIL'}\t{name}\t{detail}")
    if not all(passed for _, passed, _ in rows):
        raise typer.Exit(1)


@app.command("prepare-data")
def prepare_data(ctx: typer.Context):
    """Download and verify pinned datasets and unchanged evaluator sources."""
    from .benchmarks.wandr.data import WandrData
    root, config = settings(ctx)
    WideSearchData(root, config).prepare()
    WandrData(root, config).prepare()
    typer.echo(str(root / "data"))


@app.command()
def research(ctx: typer.Context,
             question: Annotated[str, typer.Argument(help="Research question to answer with a cited table.")],
             columns: Annotated[list[str], typer.Option("--columns", help="Output column; repeat for multiple columns.")],
             keys: Annotated[list[str], typer.Option("--keys", help="Unique key column; repeat for composite keys.")],
             language: Annotated[str, typer.Option("--language", help="Language for the research answer.")]):
    """Research one question and print its cited table and archive ID."""
    if not question.strip():
        raise typer.BadParameter("Question must not be empty", param_hint="QUESTION")
    from .research import validate_research_spec
    try:
        validate_research_spec(columns, keys, language)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    from .stream import research as research_question
    from .report import render_table
    result = research_question(*settings(ctx), question, columns, keys, language)
    typer.echo(render_table(result["output"]))
    check = result.get("self_check")
    if check is not None:
        typer.echo("Self-check: " + ("passed" if check["ok"] else "issues found"))
        for issue in check["issues"]:
            typer.echo("- " + str(issue))
    typer.echo("Archive: " + result["run_id"])
    if result.get("error"):
        typer.echo("Research failed: " + result["error"], err=True)
        raise typer.Exit(1)


@app.command()
def stream(ctx: typer.Context,
           benchmark: Annotated[Benchmark, typer.Option(help="Pinned benchmark to research in deterministic order.")],
           no_learning: Annotated[bool, typer.Option("--no-learning", help="Use the same starting harness without learning updates.")] = False,
           base: Annotated[str | None, typer.Option("--base", help="Start from this harness commit SHA.")] = None,
           resume: Annotated[str | None, typer.Option("--resume", help="Resume this archived stream run ID.")] = None):
    """Research a benchmark stream and archive independent grading reports."""
    from .stream import stream as stream_tasks
    result = stream_tasks(*settings(ctx), benchmark.value, no_learning=no_learning, base=base, resume=resume)
    typer.echo("Archive: " + result["run_id"])
    typer.echo("Report: " + str(ctx.obj[0] / "reports" / result["run_id"] / "stream.json"))


@app.command()
def baseline(ctx: typer.Context,
             benchmark: Annotated[Benchmark, typer.Option(help="Benchmark for the plain Codex baseline.")],
             resume: Annotated[bool, typer.Option("--resume", help="Continue the latest baseline run.")] = False):
    """Run plain Codex on WANDR with official grading and no harness access."""
    from .baseline import baseline as baseline_tasks
    result = baseline_tasks(*settings(ctx), benchmark.value, resume=resume)
    typer.echo("Archive: " + result['run_id'])
    typer.echo("Report: " + str(ctx.obj[0] / 'reports' / result['run_id'] / 'baseline.json'))


@app.command()
def report(ctx: typer.Context):
    """Build a task CSV, rolling learning curve and summary from reports on disk."""
    from .report import build_report
    typer.echo(str(build_report(ctx.obj[0])))


if __name__ == "__main__":
    app()
