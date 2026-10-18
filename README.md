# loop-research

A research agent using RLM and a ChatGPT-authenticated Codex CLI. WideSearch training tasks produce candidate research skills; a fixed validation batch gates each edit. Final evaluation compares the learned library with an empty library on the same tasks. Model weights never change.

All model calls, including benchmark judges, use the Codex subscription login. Research search/fetch uses Codex web search. WANDR grading re-fetches pages with the pinned harness's Camoufox browser and routes its triage, canonicalization, deduplication and judge calls through Codex. It requires no provider API keys.

## Setup

Use Python 3.12 or newer, Git, `uv`, and an installed Codex CLI with a ChatGPT subscription login. From this repository:

```sh
uv venv --python 3.12
uv pip install '.[test]'
source .venv/bin/activate
python -m camoufox fetch
codex login
loop-research init
loop-research prepare-data
loop-research verify
```

`prepare-data` downloads the pinned datasets and unchanged official evaluator sources, verifies their contents, and persists the WideSearch splits, validation gate batch and WANDR final subset. It makes no model calls. `verify` checks local source integrity, required Codex flags, ChatGPT authentication, and browser readiness; it does not research or grade tasks. Browser readiness may launch an empty browser. Findings and source references are in [docs/VERIFIED.md](docs/VERIFIED.md).

`init` preserves existing configuration and verification notes and initializes `skills/` as its own Git repository. The parent project ignores this library, datasets, run archives and generated reports. Keep learned skill changes committed; the pipeline rejects unrelated dirty library state.

Settings are in [config.yaml](config.yaml). `models.root`, `models.sub` and `models.reflect` default to the Codex default model. Adjust concurrency, per-call/task timeouts, call budget, reflection batches, gate thresholds and repeat counts there. `wandr.final_n_tasks: null` selects the full final set. A saved split/subset is immutable for its configuration; use a separate workspace to change it.

`loop.parallel_tasks` defaults to 4 concurrent task workers; set it to 1 for sequential execution. Each task keeps its own research process and archive. `codex.max_concurrent` remains the global file-lock limit for Codex calls across workers.

Global options precede the command. `--root` selects the workspace, and a relative `--config` path is resolved within that workspace:

```sh
loop-research --root /path/to/workspace --config config.yaml init
loop-research --root /path/to/workspace --config config.yaml verify
```

## Commands

The commands below are available for the user to run. `smoke`, `run`, `grade`, `improve` and `evaluate` make live subscription/web calls; they were not executed during implementation.

| Command | Behavior |
| --- | --- |
| `loop-research init` | Create directories, config if absent, verification template if absent, and the skills Git repository. |
| `loop-research verify` | Print a pass/fail table for Codex, RLM, both pinned datasets/evaluators, and WANDR browser readiness; exit nonzero on a failed check. |
| `loop-research smoke` | One plain Codex call, one search, one fetch, and an RLM computation on a tiny non-benchmark question. |
| `loop-research prepare-data` | Acquire pinned source/data and save deterministic selections. |
| `loop-research run --split train --n 1` | Research WideSearch train tasks and print the run ID. |
| `loop-research grade --run RUN_ID` | Grade that archive using its original configuration; reuse completed valid grades. |
| `loop-research improve --rounds 1` | Run training, reflection, leakage/dedup checks and validation gates; commit accepted skills. |
| `loop-research improve --rounds 3 --resume` | Resume the latest improvement session toward a total of three completed rounds. |
| `loop-research evaluate --benchmark widesearch --split val` | Evaluate the current library on validation tasks. |
| `loop-research evaluate --benchmark widesearch --split test --final` | Paired final/empty-library WideSearch test evaluation. |
| `loop-research evaluate --benchmark wandr --final` | Paired final/empty-library evaluation on the saved WANDR final subset. |
| `loop-research report` | Build a summary, rounds CSV and validation curve from archived files. |

WideSearch test and every WANDR run require `--final`. Training, reflection and skill gates never load WANDR. Research and reflection never import the WideSearch gold-answer store. Final evaluation uses the same tasks, settings and repeat count for both libraries. Repeating the same evaluation reuses completed tasks and judge caches. Resume checks configuration, task selections and library identities before continuing.

## Scoring and provenance

WideSearch wraps the unchanged official scorer. Its primary metric is Row F1; reports also contain the official success and item metrics, repeated-run aggregations, and row-alignment diagnostics. Judge prompts and scoring stay unchanged, while the judge model is the configured Codex model; reports label this `judge: codex/<model>`.

WANDR runs the pinned generated official harness with project-owned browser and Codex service adapters. It reports `fetch: wandr-browser` and `judge: codex/<model>`. This browser-primary fetch path is a user-authorized adaptation, not an upstream key-free fetch mode. The project primary metric is **full-lineage soft F1**; the upstream harness's primary reward is **full-lineage soft recall**. Reports preserve soft/hard precision, recall and F1, per-record diagnostics, excerpt-failure rate and unjudged-record counts. Operational failures surface instead of becoming fabricated scores.

Every grader uses `models.root`, or the Codex default when it is null. WANDR preserves the exact stage prompts and SDK strict schemas/response parser. Its original model, token limit and provider parameters remain in the archived request cache for provenance; Codex uses `models.reasoning_effort` and does not reproduce provider generation controls that lack verified CLI equivalents. The Perplexity SDK is an import dependency of the unchanged upstream fetch module; the adapter constructs no provider API clients.

The agent's `fetch()` returns a model rendering of a page, not raw HTML. WANDR re-fetches independently and judges excerpt faithfulness, so quotations can fail even when research returned text successfully. Citation checks flag source URLs absent from the task's URL ledger; flagged values remain part of the graded answer.

The REPL also exposes `search_batched(queries, k=8)` and `fetch_batched(urls, focus="")`. Both preserve input order and share the single-call tools' cache and URL ledger. Each batch uses at most `codex.max_concurrent` threads; duplicate in-flight requests share one backend call.

## Files and archives

```text
skills/                          learned Markdown skills; separate Git history
data/splits.json                 fixed WideSearch train/val/test selection
data/gate_batch.json             fixed validation gate selection
data/wandr_final.json            fixed WANDR final subset
data/downloads/                  pinned datasets
data/vendor/                     unchanged official evaluators
runs/<run_id>/
  config.json                    configuration snapshot
  skills_sha.txt                 library identity, or empty for the baseline
  run_summary.json               run metadata and completion state
  tasks.json                     solver-facing task manifest
  <task_id>/
    prompt.txt                   research prompt
    playbook.txt                 skills shown to the agent
    trajectory.jsonl             RLM trajectory
    output.json                  validated agent output
    submission.json              official submission representation
    grade.json                   metrics, diagnostics and provenance
    codex_calls.jsonl            completed call metadata and optional full text
    codex_attempts/              durable starts, including interrupted attempts
    tool_cache.json              task-local search/fetch cache
    url_ledger.json              observed source URLs
reports/rounds.csv               completed improvement rounds
reports/validation_curve.png     created when completed rounds exist
reports/final_<benchmark>.json   paired final results and archive references
reports/summary.md               report built from files on disk
```

Improvement archives also contain step journals and accepted/rejected skill decisions. WANDR task archives retain official harness artifacts and judge caches. Call logs always include purpose, timing, status and prompt/response sizes; full text is controlled by `codex.log_full_text`. Reports link their values to run/report files. No benchmark performance claims are included in this repository documentation.

## Tests

Default tests are offline. They use hand-written fixtures and injected transports, enforce import/data boundaries, and exercise parsing, repair, citations, official scoring adapters, skills, gates, resume behavior, CLI checks and report generation:

```sh
pytest
```

Exactly three live tests are opt-in: the smoke path, one WideSearch train task through grading, and one WANDR task through paired official-harness evaluation. Prepare data, install the browser and log in before running them. They use temporary output workspaces with links to the pinned local datasets/sources:

```sh
pytest -m live
```

Offline tests cannot establish live model availability, web access, task completion or benchmark performance. Live tests have been defined but not executed during implementation.
