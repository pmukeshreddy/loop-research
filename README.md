# loop-research

A continual research agent using RLM and a ChatGPT-authenticated Codex CLI. It answers questions with cited tables and carries reusable prompts, memories, skills and subagent instructions between tasks in a versioned harness. Model weights never change.

The researcher runs full Python in an isolated process. A trusted host provides search, fetch, model calls and harness operations. Deterministic self-checks record evidence and coverage issues; refinement can update the harness during and after research. Benchmark grading is independent: grades and answer keys stay outside the researcher and refiner, and scores are used only for reports.

## Setup

Use **macOS**, Python 3.12 or newer, Git, `uv`, and an installed Codex CLI authenticated with a ChatGPT subscription. The full-Python worker requires macOS Seatbelt (`sandbox-exec`); unsupported or unenforced isolation fails closed.

From this repository:

```sh
uv venv --python 3.12
uv pip install '.[test]'
.venv/bin/python -m camoufox fetch
codex login
.venv/bin/loop-research init
.venv/bin/loop-research prepare-data
.venv/bin/loop-research verify
```

`init` copies the repository's [config.yaml](config.yaml) when the target config is absent, initializes `harness/` as a separate Git repository, and preserves existing configuration and verification notes. `prepare-data` downloads and verifies pinned datasets and unchanged official evaluator sources. It makes no model calls. `verify` checks Codex flags and authentication, installed RLM provenance, dataset and evaluator integrity, WANDR browser readiness, and kernel-enforced worker isolation. Its browser probe opens an empty page; its isolation probe uses local fixtures. It does not research or grade tasks.

The YAML file is the sole source of configuration values. Every setting is required, types and ranges are validated, and unknown keys are rejected. `models.root`, `models.sub`, `models.refine`, and `models.judge` must each name a model explicitly; missing, blank, and `null` selections are rejected. `models.reasoning_effort` may be `null` to leave that separate setting unspecified. The YAML also sets call concurrency, retry count and delay cap, task timeouts and call budgets, RLM limits, refinement edit limits, bridge and verification timeouts, harness retrieval count, and report rolling window. There are no embedding models or train/validation/test splits. `wandr.final_n_tasks: null` includes the entire available WANDR release; a positive integer limits the stream.

`agent.as_of` must be `today` or an explicit `YYYY-MM-DD` date. A structured task date takes precedence. The resolved date and source are archived before research and reused on resume, so `today` does not drift across a resumed task. Streams freeze that date at stream creation for tasks without a structured date.

Global options precede commands. A relative `--config` path is resolved inside `--root`:

```sh
.venv/bin/loop-research --root /path/to/workspace --config config.yaml init
.venv/bin/loop-research --root /path/to/workspace verify
```

## Research and continual learning

Research one question with explicit columns, unique key columns, and answer language:

```sh
.venv/bin/loop-research research "Which public datasets document urban tree inventories?" \
  --columns dataset --columns city --columns publisher --columns access \
  --keys dataset --keys city --language en
```

The command prints a Markdown table with per-cell source links, the self-check result, and an archive ID. Columns and keys must be nonempty and unique, and every key must name a selected column. No table schema or language is inferred. These commands make live subscription and web calls when you invoke them.

Add `--trace` to watch all component boundaries live. Before isolation or model work starts,
the command prints the exact `tail -f` command for `runs/<run_id>/trace.log`.
The same events are flushed to `trace.jsonl`, including timing, RPC methods, cache
outcomes, actual opened URLs, model usage, retrieval scores, REPL snippets, and
refinement edits/commits. Each recursive RLM has a trace identity, parent identity,
its own iterations/REPL blocks, and an explicit completion reason. At completion (including failures), the command saves
and prints `runs/<run_id>/trace_summary.md` with component call counts and inclusive
times, the connection map, cited table, self-check issues, and refinement edits.
Nested and concurrent durations overlap; they do not sum to wall time. Tracing
adds no model/tool calls, changes no prompts or results, and stays out of the
research trajectory and refinement observations. Trace-only RPCs carry worker
iteration/REPL observations to the trusted host; the worker cannot write the logs.

Research also accepts `--base SHA` and `--no-learning`. Learning runs start from
the current safe harness state unless a base is supplied. `--no-learning`
requires an explicit unexposed base, disables agent/refinement edits, and restores
the active learning branch afterward, including after failure. Each run records
its base, lineage, learning mode and final HEAD in `runs/<run_id>/research.json`.
A base already exposed to that exact question/schema/language is rejected.

Run the full configured benchmark stream in deterministic order:

```sh
.venv/bin/loop-research stream --benchmark widesearch
.venv/bin/loop-research stream --benchmark widesearch --no-learning --base LEARNING_BASE_SHA
.venv/bin/loop-research stream --benchmark wandr
.venv/bin/loop-research stream --benchmark wandr --no-learning --base LEARNING_BASE_SHA
.venv/bin/loop-research stream --benchmark widesearch --resume RUN_ID
.venv/bin/loop-research baseline --benchmark wandr
.venv/bin/loop-research baseline --benchmark wandr --resume
.venv/bin/loop-research report
```

A stream researches tasks sequentially, records independent official grades, checks the research evidence, and refines the harness. The agent can also request refinement or edit relevant harness entries during a task. Entries preserve versions, evidence run IDs, usage and self-check outcomes in Git history. Replaying an already seen task starts from its earlier harness state rather than learning from a copy of that same task's prior result.

A new `--no-learning` run requires `--base SHA`, using the `base_sha` recorded in the intended learning run's `reports/<run_id>/stream.json`. A learning run can also select `--base SHA`; without it, it starts from the current harness or a safe ancestor before the selected tasks were exposed. An explicit base that already contains exposure to a selected task is rejected. Starting state is never selected from the newest matching report. `--no-learning` disables learning edits and restores the active learning branch afterward. It retains research and grading so the results can be compared against a learning stream. Run both modes with the same config and task selection. Reports compare them only when the benchmark, ordered task content, resolved date, starting harness SHA, judge and execution settings match. Reporting window and full-text logging settings do not change comparison eligibility. A comparison uses all jointly completed tasks and displays the paired count, including failed tasks scored by the official grader on an empty submission. Their errors remain visible.

`--resume RUN_ID` continues the named archived stream with its original configuration, task order, mode, base and lineage. The supplied configuration and selected tasks must match the archive; incompatible settings or an externally changed lineage are rejected. Completed tasks and completed research/grading phases are reused. A worker interrupted before a durable research result is treated as a failed attempt and receives official empty-submission grading. Refinement, rollback, and finalization failures stop the stream with an archived phase and error; resume retries the unfinished phase. Persisted proposal and edit identities prevent committed edits from being applied twice. If official empty grading also fails, the task remains pending and the stream stays interrupted until it can be graded.

The plain WANDR baseline uses the same seeded task order and `wandr.final_n_tasks` limit as both stream modes. It makes one Codex research call per task, with live web search, shell disabled, a read-only sandbox and an empty temporary working directory. It uses `models.root`, `models.reasoning_effort` and the full `agent.task_timeout_s`; transport retries and the shorter per-call timeout do not apply to this one call. Its prompt contains only the question, spec, resolved date and WANDR contract. The same contract supplies `--output-schema`, validation and submission adaptation, followed by the same official browser-fetch/Codex-judge verifier. It never loads harness contents or changes the harness, and checks Git HEAD before and after execution.

Baseline runs up to `codex.max_concurrent` independent tasks at once; Codex calls, including judging, also obey that shared limit. Reports keep the seeded task order even when tasks finish out of order. `--resume` selects the latest baseline archive and requires identical settings, task content and harness HEAD. It reuses completed research and grades, including tasks completed beyond an interrupted task. A failed task receives official empty-submission grading and remains in every mean. The scheduler stops dispatching new tasks, lets active tasks finish, and stops for investigation; resume runs only pending tasks. User interruption cancels owned subprocesses and saves completed work before releasing the run lock. An interrupted call without a durable response is treated as failed, as in stream. Baseline archives always retain prompt, raw response, Codex events and web actions, regardless of `log_full_text`. Reports identify baseline separately, compare it with each compatible stream and plot its paired mean as a dashed reference line. The current config selects the first 50 tasks in the seeded order for all WANDR modes.

The commands are `init`, `prepare-data`, `verify`, `research`, `stream`, `baseline`, and `report`.

## Evidence, grading and limits

The research tools include single and batched search/fetch, plus evidence recording for discovery and constraint checks. Search and fetch use Codex web search; `fetch()` returns the model's rendering of a page, not raw HTML. Self-checks test whether quoted text appears in fetched material, source URLs were fetched, and each recorded task constraint has an evidence check. The report separates `issues` (missing/unbacked citations, bad quotes, missing or
failed constraint checks, unrecorded discovery, and execution limits) from
`signals` (empty/stalled searches, failed tool attempts, and dropped search hits).
`ok` depends only on issues. Tool failures remain visible as signals even after
recovery; unsupported final claims still produce citation/coverage issues.
Both collections are preserved in trace summaries and refinement observations. Every fetch request records its outcome and whether it used the backend, cache, or an in-flight shared request; failed fetches are retryable and never retained as successful evidence. Malformed, invalid-URL, and excess search hits are retained with drop reasons. Refinement records discarded proposals, failures, and skipped deletes with reasons. **These checks establish recorded coverage and quotation consistency, not factual truth, exhaustive discovery, or correct interpretation of a constraint.**

All model calls, including judges, use the Codex subscription login. The two official grading adapters retain their pinned scoring logic and label results `judge: codex/<models.judge>`. WideSearch reports the official row F1, item metrics and success metric. WANDR uses full-lineage soft F1 as the project primary metric and preserves the upstream soft-recall primary metric in provenance, alongside soft/hard metrics and excerpt-failure diagnostics.

WANDR independently re-fetches cited pages through the official harness's Camoufox browser and uses Codex for triage, canonicalization, deduplication and judging. The browser-primary service adapter is a project adaptation; the upstream source is unchanged. It requires no provider API keys. Quotes returned during research may fail independent excerpt checking. Official prompts and strict schemas are retained, but provider generation controls without verified Codex equivalents are not reproduced.

Worker failures and exhausted format repair remain failures. Benchmark worker or grading failures are submitted to the unchanged official grader as an empty submission, while the original error is retained. WideSearch uses its explicit absent-response input; WANDR receives empty required JSONL files and its verifier produces the official empty-file reward. No adapter invents a replacement score.

The isolated worker can use Python libraries, threads, asynchronous code and subprocesses in its scratch directory. Kernel restrictions protect host archives, benchmark gold, grading reports and trusted source code; children inherit the restrictions. Web access goes through trusted research tools. Refinement receives research observations and deterministic self-checks, never benchmark grades or gold tables. A passed offline verification probe does not establish live model availability, web access or benchmark performance.

## Files and reports

```text
config.yaml                     explicit configuration values
harness/                        versioned supplemental state and edit history
  harness_state.json            prompts, memories, skills, subagents and usage
  edits/                        recorded edits with trigger and evidence
data/downloads/                 pinned datasets
data/vendor/                    unchanged official evaluators
runs/<run_id>/<task_id>/         research-only artifacts
  config.json                   configuration snapshot
  prompt.txt                    research instructions
  trajectory.jsonl              model, tool and worker events
  output.json                   validated output
  submission.json               official submission representation
  self_check.json               deterministic evidence and coverage checks
  as_of.json                    resolved date and policy for this task
  task_state.json               research and finalization progress
  session_state.json            pending rollback and finalization state
  refine_state.json             durable refinement proposal and edit identities
  refine_requests/              every planning snapshot, exact input and decisions
  refinements.jsonl             applied, discarded, skipped, and failed edits
  codex_calls.jsonl              completed model call metadata
  codex_attempts/                durable attempt starts
reports/<run_id>/
  stream.json                   task order, base, outcomes, interruption phase/error
  baseline.json                 plain baseline task order, outcomes and harness HEAD checks
  grading/                      official grades, grading checkpoints, diagnostics and judge caches
reports/tasks.csv               task scores, failures and rolling means
reports/learning_curve.png      rolling task-score means by stream
reports/summary.md              stream summaries and eligible comparisons
```

The exact task archive also contains tool caches and evidence records. `fetch_telemetry.json`
records returned character counts and links fetch attempts to the complete Codex web events in
`codex_calls.jsonl`. Raw opened-page character counts remain unavailable when those events
expose only result metadata; returned model text is not a raw-page size measurement.
`codex.log_full_text` controls full prompt/response logging. Grader artifacts remain under
reports, separate from research observations.

The project RLM subclass gives the root the full task contract, also available in
the persistent REPL context. Its coordination prompt asks for page processing in variables
and sub-calls, compact diagnostics, and direct submission of the validated Python value.
Printed output still reaches later root prompts with the pinned RLM's existing per-block
truncation; no output filter enforces this policy. Retrieved entries retain all fields,
including usage and outcome history, in researcher prompts.
The root and REPL receive configured resource limits. `budget()` reports cumulative reserved
research calls and remaining allowance without consuming a call; retries and in-flight calls
are included. `llm_query_json(prompt, schema)` and `llm_query_json_batched(prompts, schema)`
return native Python values validated against an explicit JSON Schema. They use the configured
sub-model, shared research budget and concurrency limit, and reject malformed or incorrectly
typed output without coercion or automatic repair. Schemas and raw responses remain archived.
Learning runs describe when to request evidence-grounded mid-task refinement. The planner
must account for every presented issue/signal group and each additional candidate, with
evidence references and a reason for accepting or declining it. The edit limit is a ceiling,
and an empty edit list remains valid.

`report` reads archived stream files without model or dataset access. Every completed task must have a finite official score; report generation rejects completed rows with missing or nonfinite scores. Rolling means include every completed task in the last `stream.rolling_window` positions, including official empty-submission scores for failures, with the contributing count in the CSV. Interrupted streams show their count, active task, phase, pending count, and error. CSV, summary and curve labels identify all four model roles; archived judge labels must match the configured judge. Curves for different streams are descriptive; the comparison table enforces the matching conditions above. No benchmark scores are claimed in this documentation.

## Tests

The default suite is intended to use hand-written fixtures and injected external transports. An autouse pytest guard rejects direct `codex exec` dispatch from tests without a `live` marker. It covers strict configuration, isolation, tools, self-checks, harness state, refinement, official grading adapters, orchestration, CLI and reports:

```sh
.venv/bin/python -m pytest
```

One research example is marked `live` and excluded by default. It makes subscription and web calls only if you explicitly select it after setup:

```sh
.venv/bin/python -m pytest -m live
```

The marked live test was not selected during this reliability work. However, an unmocked new regression accidentally dispatched live refinement calls before the pytest guard was added; this implementation session must not be described as entirely offline. The incident is recorded in [docs/VERIFIED.md](docs/VERIFIED.md). Fixture tests and accidental refinement calls do not measure research quality or benchmark performance. Source verification evidence and any unresolved questions are in [docs/VERIFIED.md](docs/VERIFIED.md).
