# WideSearch + WANDR + RLM self-improving research agent: build spec

You are building a complete, working Python project from this spec. Read the whole file before writing any code.

---

## 0. Ground rules (follow strictly)

1. Build every component described here. No stubs, no `TODO` or `pass` placeholders, no mocked model responses anywhere in the main pipeline. Mocks are allowed only inside `tests/` for unit tests.
2. Never fabricate anything: dataset contents, file formats, API signatures, CLI flags, or scores. If you cannot verify something, stop that part and write it under "Open questions" in `docs/VERIFIED.md`.
3. When a command, import, or test fails, find and fix the root cause. Never skip, delete, disable, or weaken a test or check to make it pass.
4. No reward hacking. The agent never sees answer keys. Skills never contain task answers. The WideSearch test split and all of WANDR are used only by final evaluation commands, never by reflection or the skill gate.
5. Do not edit the RLM library source, the WideSearch code, or the WANDR harness. Integrate through adapters and subclasses inside this project.
6. Do not write benchmark numbers into README, docs, or comments. Real numbers come only from runs the user executes.
7. Complete the verify-first checklist (Section 3) before writing code that depends on it.

---

## 1. What we are building

A research agent that solves wide-and-deep web research tasks (find every entity that matches a set of conditions, then fill in its attributes with cited evidence) using Recursive Language Models (RLM; Zhang, Kraska and Khattab), and improves itself across runs by growing a library of reusable research skills.

Two benchmarks, with separate jobs:

| Benchmark | Role | Why |
|---|---|---|
| WideSearch (ByteDance Seed) | Inner loop: agent runs, reflection, skill gate | Fixed gold tables, cheap and fast to grade |
| WANDR (Perplexity) | Final evaluation only | Built from real production research tasks; reference-free, evidence-verified grading |

- All model calls go through the user's ChatGPT subscription via the Codex CLI (`codex exec`, authenticated with `codex login`). No API keys, including for grading.
- Web search and page fetching use Codex's built-in web search.
- Self-improvement updates a skills library only. Model weights are never changed.
- Benchmark-specific code lives only under `src/loop_research/benchmarks/`, behind one shared interface, so benchmarks can be added or swapped (for example ATLAS, once released) without touching the rest of the pipeline.

---

## 2. Pipeline

```
INNER LOOP (WideSearch only)
WideSearch task (train split)
  -> skill retrieval      render a playbook from the skills library
  -> RLM research         root LM + REPL with search(), fetch(), llm_query()
  -> cited output         JSON in the benchmark's output contract, every cell/record cited
  -> grading              official WideSearch evaluation + error breakdown
  -> reflection           trajectory + errors -> candidate skill edits
  -> leakage filter       reject edits containing task facts
  -> skill gate           WideSearch val batch: library with edit vs without
  -> accepted edit        one git commit in the skills library
  -> next round

FINAL EVALUATION (after the loop; final library AND empty library, same tasks)
  -> WideSearch test split   official WideSearch evaluation
  -> WANDR final subset      official WANDR harness (re-fetch + judge)
```

Two stores, always kept separate:

| Store | Path | Contents | Who reads it |
|---|---|---|---|
| Skills library | `skills/` | Short, general research lessons | The agent (as a playbook) |
| Run archive | `runs/` | Trajectories, outputs, grades, Codex call logs | Reflection and reports only |

Data usage:

| Data | Used by |
|---|---|
| WideSearch train | Agent runs + reflection (where skills are learned) |
| WideSearch val | Skill gate only |
| WideSearch test | Final evaluation only (`--final`) |
| WANDR final subset | Final evaluation only (`--final`) |

---

## 3. Verify-first checklist

Record every finding in `docs/VERIFIED.md` with file paths, line references, and command output. Keep existing findings; add to them.

### 3.1 RLM library (https://github.com/alexzhang13/rlm)

- Install from GitHub pinned to a specific commit and record the SHA. Python 3.11+ is required; the docs recommend Python 3.12 with `uv`.
- Inspect `rlm/clients/`: the base class or protocol for LM clients, method signatures (sync/async, message format, return type, usage tracking), and how a backend name maps to a client class.
- Inspect `rlm/environments/local_repl.py`: how `llm_query` and `rlm_query` get injected into the REPL namespace. Find the supported way to add extra functions (`search`, `fetch`). If none exists, subclass `LocalREPL` in this project.
- Inspect `rlm/core/rlm.py`: how the loop ends (the docs indicate the model sets `answer["content"]` and `answer["ready"] = True`), how the system prompt is built and whether it can be extended, and the constructor arguments (max iterations, max depth, environment, logger, sub-model).
- Inspect `rlm/core/lm_handler.py`: how LM calls from REPL code are routed, so the Codex client is used for both root and sub calls.
- Inspect `RLMLogger`: the `.jsonl` trajectory format, so reflection can parse it.

### 3.2 Codex CLI

- Run `codex --version` and `codex exec --help`. Confirm each flag the backend uses: `--sandbox read-only`, `--skip-git-repo-check`, `--cd`, `--output-last-message`, `--output-schema`, `--model`, `-c key=value`, prompt from stdin via `-`.
- Confirm how web search is enabled for `codex exec` in the installed version (a `--search` flag, a config key, or a feature flag). Use whatever the installed version supports.
- Confirm the active auth is ChatGPT login, not an API key, using the CLI's own status command (verify the exact command exists).
- Determine how rate-limit and usage-limit errors appear (exit code, stderr text) so the backend can back off correctly.

### 3.3 WideSearch (ByteDance Seed)

- Dataset: https://huggingface.co/datasets/ByteDance-Seed/WideSearch. Official code and evaluation: https://github.com/ByteDance-Seed/WideSearch. Pin both to exact revisions (dataset revision hash, git commit SHA) and record them.
- Record the exact task format: fields, how required columns and the output table format are specified, the language field (WideSearch contains English and Chinese tasks), any as-of or reference date, and the gold table format.
- Record the official metrics and how each is computed: Success Rate, Row-level F1, Item-level F1, and the Avg@N / Pass@N / Max@N aggregations. Record which columns use exact or normalized matching, which use an LLM judge, how rows are aligned to gold (key columns), and which judge model the official code uses.
- Wrap the official evaluation code; do not rewrite its scoring logic. If its LLM judge calls an API with a key, route only those judge calls through `CodexBackend` (purpose `grade`), keep prompts and scoring identical, record in `VERIFIED.md` that the judge model differs from the official one, and label every report `judge: codex/<model>`.
- If the dataset or official evaluation cannot be downloaded or run, stop and report. Never synthesize tasks.

### 3.4 WANDR (Perplexity)

- Dataset: https://huggingface.co/datasets/perplexity-ai/wandr. Harness: https://github.com/perplexityai/wandr. Pin both to exact revisions and record them. The dataset card refers to a pinned GitHub/Harbor harness; determine which entry point is the official one for scoring and record it.
- WANDR has no reference answer sets. Record exactly how tasks are specified (entity qualifications, hierarchical record structure, required fields), and the exact submission format the harness expects (how each record carries its page URL and excerpt).
- Record how grading works end to end: how cited pages are re-fetched (which fetch backend or browser, and whether any of them needs an API key or paid service), how the task-specific judge is invoked (model, prompts), how excerpts are matched (exact, fuzzy, or judged), and how soft and hard precision, recall, and F1 are computed.
- Wrap the official harness; do not rewrite its scoring logic. Route only judge LLM calls through `CodexBackend` (purpose `grade`), keep prompts and scoring identical, record that the judge model differs from the official one, and label every WANDR report `judge: codex/<model>`.
- If page re-fetching requires an API key or paid service, use a key-free fetch mode the harness officially supports if one exists, record which, and label reports with it. If none exists, stop and ask the user before proceeding with WANDR.
- Record whether excerpts must be verbatim. Our `fetch()` returns a model rendering of the page, so quotes may not be byte-identical; if the harness requires exact excerpts, record this risk and make sure the WANDR report shows the excerpt-failure rate separately.
- If the dataset or harness cannot be downloaded or run, stop and report. Never synthesize tasks.

---

## 4. Repo layout

```
loop-research/
  README.md
  pyproject.toml
  config.yaml
  src/loop_research/
    __init__.py
    config.py             # load + validate config.yaml (pydantic)
    codex_backend.py      # subprocess wrapper around `codex exec`
    rlm_codex_client.py   # RLM client adapter backed by CodexBackend
    repl_tools.py         # search(), fetch(), REPL injection
    agent.py              # run one task with RLM + playbook
    archive.py            # run archive read/write
    skills.py             # skills library: parse, render, edit, git
    reflect.py            # reflection -> candidate edit ops
    gate.py               # leakage filter, dedup, validation gate
    loop.py               # improvement rounds (WideSearch only)
    evaluate.py           # final evaluation on WideSearch test + WANDR
    report.py             # summary.md, rounds.csv, curve plot
    cli.py                # typer CLI entry point
    benchmarks/
      __init__.py         # Benchmark protocol, Task model, registry
      widesearch/
        data.py           # tasks + splits (never reads gold)
        answers.py        # gold tables (grader-only)
        grader.py         # wraps official WideSearch evaluation
      wandr/
        data.py           # tasks + final subset
        grader.py         # wraps official WANDR harness
  skills/                 # skills library, its own git repo (gitignored by parent)
  runs/                   # run archive (gitignored)
  data/                   # splits.json, gate_batch.json, wandr_final.json (dataset files gitignored)
  reports/
  docs/VERIFIED.md
  tests/
```

---

## 5. Components

### 5.1 `codex_backend.py`

- `CodexBackend.complete(prompt, *, purpose, web=False, schema=None, model=None) -> str`.
- Each call runs `codex exec` as a subprocess in an empty scratch directory with a read-only sandbox, prompt on stdin, final message read from `--output-last-message`. Write the schema to a temp file when `schema` is given.
- Prepend a fixed instruction to every prompt: Codex is acting as a component inside a program; no shell commands, no file edits, reply with text only.
- Concurrency: a global semaphore of size `codex.max_concurrent`.
- Retries: exponential backoff with jitter on non-zero exit, timeout, or a detected rate limit, up to `codex.max_retries`. On final failure raise `CodexError` containing the command, exit code, and stderr tail.
- Log every call to the active run archive: timestamp, purpose (`root | sub | search | fetch | reflect | grade | repair`), model, duration, exit code, prompt sha256, prompt and response character counts. Full text logging is controlled by `codex.log_full_text`.

### 5.2 `rlm_codex_client.py`

- A client that conforms exactly to the interface found in 3.1, backed by `CodexBackend`.
- Each turn is a stateless call: convert the message list into one role-tagged transcript.
- Support separate models for root and sub calls (`models.root`, `models.sub`; `null` means the Codex default).
- Report usage the way the interface expects. If it wants token counts and Codex does not expose them, report character counts and document this in `VERIFIED.md`.
- Connect it to RLM without editing library files, using whatever mechanism exists (registration, passing a client instance, or a subclass). Document which one in `VERIFIED.md`.

### 5.3 `repl_tools.py`

- `search(query: str, k: int = 8) -> list[dict]` returning `title`, `url`, `snippet`, via Codex web search with an output schema. The prompt forbids invented URLs; drop results whose URL is not a valid http(s) URL.
- `fetch(url: str, focus: str = "") -> str` via Codex web search, returning page content as plain text, copied as faithfully as possible, or the exact string `FETCH_FAILED`. The docstring must state this is the model's rendering of the page, not raw HTML.
- Per-task cache keyed by normalized query or URL; saved to the archive as `tool_cache.json`.
- Record every URL returned by `search` or `fetch` in a per-task URL ledger (used for citation checks).
- Inject both functions into the REPL namespace using the mechanism found in 3.1, and document them in the root prompt.

### 5.4 `benchmarks/` (shared interface)

`Task(task_id, benchmark, question, spec, language, as_of_date | None, raw)`, where `spec` holds the benchmark's own description of what to collect (WideSearch columns; WANDR qualifications and record structure).

Each benchmark implements one protocol:

- `load_tasks() -> list[Task]` (never reads gold data)
- `output_contract(task) -> OutputContract`: the JSON schema the agent must produce plus the prompt text that explains it
- `to_submission(task, agent_output) -> object`: converts the agent's JSON into the official submission format
- `grade(task, submission, run_ctx) -> GradeResult`: all official metrics, the primary metric, and an error breakdown where available

**WideSearch**

- `data.py`: loads tasks; `data.languages` in config filters by language. `prepare_splits(seed)`: deterministic train/val/test split (default 60/20/20, seed 42), stratified by language, saved to `data/splits.json`; the fixed val gate batch (`gate.val_batch_size` tasks) saved to `data/gate_batch.json`.
- `answers.py`: loads gold tables. Only `widesearch/grader.py` may import it.
- `grader.py`: wraps the official evaluation (3.3). Primary metric: Row F1. Error breakdown from the official row alignment: `missing_entities`, `wrong_additions`, `partial_rows` (with columns). Also `build_leakage_index()`: a normalized set of entity names and cell values from all WideSearch gold tables, for the leakage filter, excluding very short or very common strings (`gate.leakage_min_len`).
- Output contract: a cited table:

```json
{
  "rows": [
    {
      "entity": "string",
      "cells": {
        "<column name>": {
          "value": "string",
          "sources": ["https://..."],
          "quote": "string"
        }
      }
    }
  ]
}
```

**WANDR**

- `data.py`: loads tasks; `prepare_final_subset(seed)` picks `wandr.final_n_tasks` tasks deterministically (or all, if `null`) and saves them to `data/wandr_final.json`.
- `grader.py`: wraps the official harness (3.4). Primary metric: the harness's headline F1. Reports soft and hard precision, recall, and F1, plus per-record failure reasons where the harness provides them, and the excerpt-failure rate.
- Output contract: derived from the task's own record structure (3.4). Every record carries its page URL and an excerpt copied verbatim from the fetched page text.
- Grading cache: store judge verdicts keyed by (task, record hash, URL) so an interrupted or repeated grading run does not redo finished work.

### 5.5 `agent.py`

`run_task(task, benchmark, library_dir, run_ctx) -> AgentResult`

Root prompt contains, in order:

1. Task question and the task spec.
2. As-of date: the task's own date if present, otherwise today's date (record which one was used).
3. Research playbook: rendered skills (5.8). Empty when evaluating the empty-library baseline.
4. Tool docs for `search`, `fetch`, `llm_query`.
5. Working method: go wide (discover candidate entities, keep them in a REPL variable), go deep (fill fields with parallel `llm_query` calls over fetched pages), verify (check every task constraint per entity, cite every value with a verbatim quote from fetched text).
6. The benchmark's output contract (5.4). The model sets `answer["content"]` to JSON matching it.

- Validate with pydantic against the contract. If the JSON is invalid, make one `repair` call that only reformats the existing content (no new research). If still invalid, record an empty output with the error. Never invent rows or records.
- Citation check: every source URL must appear in this task's URL ledger. Values failing this are flagged `uncited` and reported. They are still graded as the agent's answer.
- Limits from config: `rlm.max_iterations`, `rlm.max_depth` (default 1), `agent.task_timeout_s`, `agent.max_codex_calls`.
- Attach `RLMLogger`; save the trajectory to `runs/<run_id>/<task_id>/trajectory.jsonl`.

### 5.6 `archive.py`

```
runs/<run_id>/
  config.json          # config snapshot
  skills_sha.txt       # skills library git SHA used ("empty" for the baseline)
  run_summary.json
  <task_id>/
    prompt.txt
    trajectory.jsonl
    output.json
    submission.json
    grade.json
    codex_calls.jsonl
    tool_cache.json
    url_ledger.json
```

### 5.7 Import boundaries

- `agent.py`, `reflect.py`, and `repl_tools.py` must never import `benchmarks/widesearch/answers.py`, directly or indirectly.
- `loop.py`, `reflect.py`, and `gate.py` must never import `benchmarks/wandr/`, directly or indirectly. WANDR is reachable only from `evaluate.py`.
- Unit tests enforce both boundaries.

### 5.8 `skills.py`

The library lives in `skills/`, initialized as its own git repo by `loop-research init`. One file per skill, `skills/<id>.md`, with YAML front matter (values below are placeholders):

```yaml
id: sk_<4 digits>
title: <short imperative title>
applies_to: [wide]   # any of: wide, constraint, enrichment, entity_resolution, rlm_usage, format
status: active       # active | retired
source_tasks: [<train task ids>]
gate: {val_batch: <id>, baseline: <float>, with_edit: <float>, delta: <float>, repeats: <int>, date: <YYYY-MM-DD>}
counters: {helpful: <int>, harmful: <int>, unused: <int>}
```

The body is the lesson: at most 80 words, imperative, general.

| `applies_to` | Fixes | Example lesson shape |
|---|---|---|
| `wide` | missing entities | Where to enumerate candidates; when to stop searching |
| `constraint` | wrong additions | How to check each task constraint per entity |
| `enrichment` | partial rows | Which source types to trust for which attribute |
| `entity_resolution` | duplicates, mismatches | How to merge name variants |
| `rlm_usage` | wasted steps, timeouts | How to use REPL variables and parallel `llm_query` |
| `format` | value mismatches | Match requested formats exactly |

Functions:

- `render_playbook(task, library_dir) -> str`: all active skills. If the total exceeds `skills.max_playbook_chars`, select by `applies_to` relevance, then by `helpful - harmful`, tie-break by id (deterministic).
- Edit ops: `add`, `update(id, ...)`, `retire(id)`. Apply ops to a temporary copy for gating. On acceptance, apply to `skills/` and commit with the message `accept <op> <id>: val delta=<delta>`.
- Rejected ops go to `runs/<run_id>/skills_rejected.jsonl` with the reason.

### 5.9 `reflect.py`

Inputs per WideSearch train task: question, spec, the agent's output, error breakdown, condensed trajectory (code blocks, tool calls, key outputs from the `RLMLogger` file, truncated to `reflect.max_chars`), and the playbook that was used.

Output (enforced with an output schema):

- Up to `reflect.max_ops` edit ops, each with a rationale and evidence task ids.
- For each skill in the playbook: `helped | hurt | unused` (updates counters).

Prompt rules for reflection:

- Write methods, never facts. No entity names, numbers, dates, or URLs from any task.
- Prefer updating an existing skill over adding a near-duplicate.
- At most 80 words per skill.

`reflect.batch_size` controls how many train tasks are reflected on together to find shared patterns.

### 5.10 `gate.py`

Order of checks for each candidate op:

1. Leakage filter: reject if the op text contains any leakage index entry, or any URL.
2. Dedup: reject an `add` whose normalized text similarity to an existing skill exceeds `gate.dedup_threshold`; log a suggestion to use `update`.
3. Validation on the WideSearch val gate batch: baseline = current library (cached by library SHA); candidate = library plus op, same batch, same settings, `gate.repeats` runs each, averaged. Accept if mean Row F1 improves by at least `gate.min_delta` and at most `gate.max_regressions` tasks drop by more than `gate.regression_tol`.

Accepted ops apply sequentially; the next baseline is the updated library (cached by its new SHA).

### 5.11 `loop.py`

`improve(rounds, resume=False)`, WideSearch only. Each round:

1. Sample `loop.train_batch_size` WideSearch train tasks (seeded, without replacement across rounds until train is exhausted).
2. Run the agent on each; grade each.
3. Reflect; collect candidate ops.
4. Leakage filter, dedup, gate.
5. Commit accepted ops.
6. Append round metrics to `reports/rounds.csv`: round, library SHA, active skill count, train mean metrics, gate batch score after the round, ops proposed/accepted/rejected, Codex call count, wall time.

`--resume` continues from the last completed step using archive state.

### 5.12 `evaluate.py`

- `evaluate(benchmark, split, final)`. For `--final`, run both the final library and the empty library on the same tasks with the same settings and `final.repeats` runs each.
- WideSearch: `--split val` is allowed any time; `--split test` requires `--final`.
- WANDR: always requires `--final`; uses `data/wandr_final.json`.
- Resumable: completed tasks and cached judge verdicts are reused.
- Write `reports/final_<benchmark>.json` with every metric, the judge label, the fetch mode label (WANDR), task count, library SHA, and run ids.

### 5.13 `report.py`

Builds `reports/summary.md` only from files on disk: the per-round table, a validation curve PNG (matplotlib), accepted and rejected skills, and the final results for WideSearch test and WANDR (final library vs empty library), each with its judge label. Every number must trace to a file in `runs/` or `reports/`.

---

## 6. `config.yaml` defaults

```yaml
models:
  root: null        # null = Codex default
  sub: null
  reflect: null
  reasoning_effort: null

codex:
  bin: codex
  max_concurrent: 4
  timeout_s: 600
  max_retries: 4
  log_full_text: false

rlm:
  max_iterations: 30
  max_depth: 1

agent:
  task_timeout_s: 3600
  max_codex_calls: 300

data:
  seed: 42
  languages: [en, zh]   # use the language codes found in 3.3
  split: {train: 0.6, val: 0.2, test: 0.2}

wandr:
  final_n_tasks: 50     # null = all tasks
  seed: 42

final:
  repeats: 1

skills:
  max_playbook_chars: 6000

reflect:
  max_ops: 3
  max_chars: 20000
  batch_size: 1

gate:
  val_batch_size: 20
  repeats: 1
  min_delta: 0.01
  max_regressions: 2
  regression_tol: 0.10
  dedup_threshold: 0.85
  leakage_min_len: 4

loop:
  train_batch_size: 5
```

---

## 7. CLI (`typer`, entry point `loop-research`)

| Command | Does |
|---|---|
| `loop-research init` | Create dirs, init `skills/` git repo, write `VERIFIED.md` template if missing |
| `loop-research verify` | Check Codex installed and logged in with ChatGPT auth, required flags present, RLM importable at pinned SHA, both datasets and both official evaluators present at pinned revisions; print a pass/fail table |
| `loop-research smoke` | One plain call, one `search`, one `fetch`, one RLM completion on a tiny non-benchmark toy question |
| `loop-research prepare-data` | Download both benchmarks at pinned revisions; write `splits.json`, `gate_batch.json`, `wandr_final.json` |
| `loop-research run --split train --n N` | WideSearch agent runs only |
| `loop-research grade --run RUN_ID` | Grade an existing run with its benchmark's grader |
| `loop-research improve --rounds N [--resume]` | Full self-improvement loop on WideSearch |
| `loop-research evaluate --benchmark widesearch --split val` | Evaluate current library on WideSearch val |
| `loop-research evaluate --benchmark widesearch --split test --final` | Final WideSearch test evaluation, final library and empty library |
| `loop-research evaluate --benchmark wandr --final` | Final WANDR evaluation, final library and empty library |
| `loop-research report` | Build `reports/summary.md` |

---

## 8. Tests

Unit tests (no network, run with `pytest`):

- Codex command construction for each mode (plain, web, schema, model, reasoning effort).
- Backoff/retry behavior using a fake subprocess runner.
- Message-to-transcript conversion in the RLM client.
- Agent output parsing against each benchmark's contract, repair path, and empty-output fallback.
- Citation check against a URL ledger.
- WideSearch adapter: `to_submission` and error breakdown on small hand-written fixtures (clearly labeled as fixtures, not WideSearch data).
- WANDR adapter: `to_submission` on small hand-written fixtures matching the verified submission format; grading cache hit and miss.
- Skill file parse/render round-trip; playbook selection under the char cap; deterministic ordering.
- Leakage filter and dedup decisions.
- Gate accept/reject logic with injected scores.
- Import-boundary tests from 5.7.
- `evaluate` refuses test and WANDR without `--final`.
- Split and subset determinism for a fixed seed.

Live tests (marker `live`, run by the user with `pytest -m live`):

- `smoke` path end to end.
- One WideSearch train task end to end, producing `output.json`, `submission.json`, and `grade.json`.
- One WANDR task end to end through the official harness.

---

## 9. Definition of done

1. All unit tests pass.
2. `docs/VERIFIED.md` is filled in for every item in Section 3, with no unresolved open questions blocking the pipeline.
3. `loop-research verify` passes on the user's machine.
4. `loop-research smoke` completes.
5. `loop-research run --split train --n 1` produces a cited output and a grade.
6. `loop-research improve --rounds 1` completes a full cycle, ending in either a commit in `skills/` or logged rejections with reasons.
7. Both `evaluate --final` commands run end to end on a small subset.
8. `README.md` explains setup, each command, and where outputs land, with no benchmark numbers.
