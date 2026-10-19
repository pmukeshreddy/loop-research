# Continual research harness

## 0. Ground rules

1. Build every component. No stubs, placeholders, or mocked model responses in the pipeline. Mocks belong only in `tests/`.
2. Never fabricate dataset contents, file formats, API signatures, or scores. Record unverified dependencies and open questions in `docs/VERIFIED.md`.
3. Fix failures at their root. Never skip, disable, weaken, or delete a failing check to obtain a passing suite. Tests of explicitly removed features are removed with those features.
4. Research and refinement never receive benchmark answer keys, grades, judge feedback, or other runs' archives. Grades belong only in reports. Learn from the current research trajectory and deterministic self-check.
5. Do not modify the pinned RLM library or official benchmark sources. Integrate through project adapters.
6. No benchmark performance claims without actual user-run measurements.
7. Verify source interfaces before depending on them. Pin and cite the Prime Agent reference and Continual Harness paper in `docs/VERIFIED.md`.
8. All model calls use the authenticated ChatGPT subscription through `codex exec`; no provider API keys. Do not run live tests, research, or streams while implementing this change.

## 1. Reference and scope

Mirror Prime Agent's supplemental harness entries, shared REPL CRUD surface, targeted refinement, evidence records, and snapshot-based compensating rollback. The base system prompt stays immutable. Harness edits never change tool, grader, or self-check source.

The pinned reference is Prime Agent `7cbffa77b38facd7c87277fa3c82bcadbe816880` and Continual Harness arXiv `2605.09998v1`. The verified reference differs from this project's explicit requirements in storage, retrieval, automation, and background execution; document these overrides, not invented upstream behavior.

## 2. Components

- `harness.py`: its own Git repository in `harness/`, CRUD, BM25, refinement snapshots, usage/outcomes and lineage tracking.
- `refine.py`: asynchronous model planning and targeted edits applied at model-turn boundaries.
- `selfcheck.py`: deterministic evidence and constraint-coverage report, without answer keys or model calls.
- `session.py`: trusted host services, evidence recording, budgets, refinement lifecycle.
- `bridge.py`: explicit JSON RPC methods available to the isolated research worker.
- `isolation.py`: fail-closed macOS Seatbelt execution and offline capability probe.
- `agent.py`: task prompt, isolated worker, validation and one format-only repair attempt.
- `rlm_codex_client.py`: subscription transport adaptation, stock LocalREPL and recursive calls.
- `repl_tools.py`: cached search/fetch and parallel variants, evidence and discovery records.
- `stream.py`: research and seeded sequential measurement; grader contexts write under reports.
- `report.py`: cited table rendering, ordered task scores and rolling-mean plots.
- `config.py`: required, strictly typed configuration schema; all values originate in `config.yaml`.
- `benchmarks/`: pinned WideSearch and WANDR task/output/grader adapters.

## 3. Harness state and CRUD

Four kinds: `prompt`, `skill`, `memory`, `subagent`. Each entry has an id, kind, title, body, trigger, evidence run ids, usage/outcome history, creation/update timestamps and version. Skills may carry Python module source. Selected modules load into the worker at session start; executable code runs only there.

The REPL exposes `harness.create(kind, title, content, ...)`, `get`/`read`, `update`, `delete`, `list`, and `search`, using the reference's generic operation names and `content` argument. Stored prose is named `body`. Skill module source is optional. CRUD works mid-task and writes narrowly scoped state changes.

Before each task, retrieve relevant entries using local BM25, with stable tie breaking and CJK bigrams. `harness.retrieval_limit` bounds the number retrieved. There is no character cap on harness entries or the store, and no embedding API. Retrieval is refreshed at root model-turn boundaries after pending refinements apply.

Every CRUD edit creates one Git commit containing the trigger, evidence and before/after entry snapshot under `edits/`. Separate bookkeeping commits record exposure, usage and self-check outcomes. Git notes on originating edit commits attach later outcomes without rewriting commit identities. Rollback compensates the selected edit from its snapshot and preserves unrelated entries and history.

## 4. Refinement

`refine.run(focus=None)` is callable from the REPL. It schedules planning on a background thread and immediately returns. Applying waits for a model-turn boundary; automatic refinement runs after every task, including failed research tasks. Planning, applying, rollback, or task-finalization failures stop the current stream; they are never suppressed so a later task can proceed. A pending plan cannot cross a lineage fork. Concurrently changed target entries cause replanning from current state.

The planner receives only current-run trajectory, self-check and harness entries including past usage/outcomes. It prefers updating, merging (update then delete), or deleting an existing entry over adding one. Failure lessons become memories; successful reusable procedures become skills. Repeatedly poor self-check outcomes prompt revision/deletion. An empty edit list is legitimate when no reusable change is supported. No rewrite of the whole harness, acceptance gate, freeze or learning rounds exists.

Planning uses the initial root instructions and incremental model/tool/REPL events.
Repeated accumulated root prompts, duplicate worker responses/sub-call records, and
full REPL locals snapshots are omitted from the planner input. Sub-model inputs,
tool results, code, stdout, errors and final answers remain. The full trajectory
archive is unchanged; this avoids quadratic repetition of history and page variables.

Persist the proposal, snapshot, request identity and per-edit operation identities before applying edits. Resume recognizes already committed edits and continues unfinished application without duplicate edits. Persist finalization and rollback progress; record discarded proposals and skipped deletes with explicit reasons.

`refine.rollback(id)` queues a compensating edit for the next boundary when invoked inside the REPL. Host rollback accepts a refinement id or its commit SHA.

## 5. Deterministic self-check

After each task, save `self_check.json` in its research archive. `issues` contains
citation/quotation failures, missing or failed constraint checks, unrecorded
discovery and execution failures. `signals` retains empty/stalled searches,
recoverable tool failures and dropped hits. `ok` depends only on `issues`; both
collections reach refinement and harness outcome history. Check:

- Every cited URL has a successful cached fetch in this run, backed by a completed Codex `open_page` event for that URL.
- Each supplied quotation appears verbatim in cached fetched text for its cited URL.
- Every output row has an evidence-backed check for each task constraint id.
- Failed fetch/search calls, empty searches, unrecorded discovery, and searches reported as yielding no new entity ids.
- Iteration limits, call limits, worker failures and timeouts.

`check_constraint(row, constraint, verdict, url, quote)` records per-row checks; `record_discovery(query, entities)` records entity discovery after every search. The host verifies quote provenance and coverage. Semantic truth of agent verdicts/entity labels is not mechanically proved. Fetch text is Codex's page rendering, not raw HTML. These limits must be visible in documentation; neither a passing check nor a fetch event proves external factual correctness.

Evidence and reports are owned by the trusted host, outside the worker filesystem. Imported or monkeypatched code in the worker cannot alter the host's checker or evidence.

## 6. Full Python and isolation

Use stock RLM LocalREPL. Restore full Python builtins on the instance because the pinned upstream default map omits some. No custom import allowlist, AST validation, blocked builtins, or restricted REPL class remains. Threading and asyncio work.

The worker runs in a fresh temporary directory under a verified macOS Seatbelt profile. It can read Python/runtime/project source and write its own scratch directory. It cannot read benchmark data, grade reports, harness Git history or run archives; it cannot write trusted source. Children inherit isolation. Networking is restricted to broker/loopback needs. Unknown or unsupported mechanisms fail closed; do not launch an unrestricted worker.

The host exposes only enumerated RPC operations. Root/sub-model completions, tools and CRUD share this boundary; there is no grade RPC or arbitrary host-path operation. Parent-owned evidence remains independent of worker-supplied trajectory annotations.

## 7. Tools and transport

`search(query, k=8)` and `fetch(url, focus='')` use `codex exec` and one task cache/URL ledger. `search_many(queries, k=8)` and `fetch_many(urls, focus='')` run concurrently up to `codex.max_concurrent`, returning results in input order. Duplicate in-flight requests share results. Record each fetch attempt, including backend calls, cache hits, shared requests, validation failures, exceptions and cancellation. Failed fetches are retryable and do not become cached evidence. Keep dropped malformed, invalid-URL and excess search hits with their reasons. No cache/ledger lock is held during a Codex call or while waiting for another request.

Codex runs with ChatGPT authentication forced, provider-key environment variables removed, shell tool disabled, user configuration ignored, ephemeral sessions, and read-only sandboxing. Retry limits, timeouts, call accounting and actual usage logs are explicit. All four model fields (`root`, `sub`, `refine`, `judge`) require explicit nonempty selections. All grading calls select `models.judge`; labels include `codex/<models.judge>`. Required YAML policy includes `agent.as_of` (`today` or `YYYY-MM-DD`), `codex.retry_delay_cap_s`, `refine.max_edits`, `bridge.socket_timeout_s`, and `verify.codex_timeout_s`/`verify.browser_timeout_s`. Resolve the as-of date once per task, preserving a structured task date when present, and archive it for reuse on resume. Streams freeze the `today` value at stream creation.

## 8. Commands and measurement

- `init`: create directories and initialize the separate harness repository; preserve existing configuration and verification findings.
- `prepare-data`: acquire and verify pinned benchmark data and evaluator sources.
- `verify`: offline dependency, authentication, source integrity, browser readiness and OS-isolation checks.
- `research "<question>" --columns <name> ... --keys <name> ... --language <language> [--trace] [--base SHA] [--no-learning]`: require explicit unique columns, unique keys drawn from those columns, and a nonempty answer language; return a cited table and refine from this run. Optional tracing writes live, flushed component events to `runs/<run_id>/trace.jsonl` and `trace.log`, then prints/saves `trace_summary.md` with inclusive timings, call counts, connection edges, final citations, self-check issues, and refinement edits. Trace observations never enter model prompts or refinement inputs. Research lineage options follow stream semantics: explicit unexposed base for no-learning, safe-base validation for learning, separate lineage, and restoration of the active learning branch after no-learning runs.
- `stream --benchmark widesearch|wandr [--base SHA]`: fixed seeded task order; each task runs research, then report-only grading, then self-check, then refinement before the next task.
- `stream --benchmark ... --no-learning --base SHA`: require the intended explicit starting harness commit, with refinement and agent CRUD writes disabled, for comparison only.
- `stream --benchmark ... --resume RUN_ID`: continue the explicit archived stream, preserving its configuration, order, mode, base and lineage; never rerun completed tasks or completed phases.
- `report`: regenerate ordered task scores, CSV and rolling-mean curves from report artifacts.

No train/validation/test partitions, leakage index, validation gate or improvement command remain. WideSearch uses the complete selected-language release. WANDR uses all 500 tasks when `wandr.final_n_tasks: null`.

Record a benchmark task's first exposure before starting research. A repeat forks the harness from a commit before that task was first seen. Exposure records survive entry rollback; prior learned content cannot enter a replay's active lineage. An unspecified learning base comes from the active harness or a safe ancestor before all selected tasks were exposed. Explicit unsafe bases are rejected. Never select a base by taking the newest report matching a benchmark. Comparison runs restore the live learning branch afterward. A workspace lock serializes tasks against the harness.

Worker failures, exhausted format repair, and grading failures remain visible errors. For benchmark failures, construct the adapter's canonical empty submission and run the unchanged official grader on it; do not manufacture a score. A resumed interrupted worker is a failed attempt, not a fresh research attempt. If empty grading cannot finish, archive the interruption and leave that task pending.

Persist task research, grading, and finalization phases separately. Grading state and results stay under reports, outside researcher/refiner observations; research/finalization checkpoints contain no grader feedback. Completed manifest rows must have finite official scores. Report generation rejects missing/nonfinite completed scores; rolling means and paired comparisons include scored failures. Show interruption counts, active task, phase, pending tasks and error. Identify all four model roles in CSV, summary and curves, and reject archived judge labels inconsistent with the configured judge. Pair learning/no-learning only for identical ordered tasks, initial commit, judge and execution configuration.

## 9. Verification

Unit coverage must include CRUD round trips, BM25, one commit per edit, outcome notes, rollback, commit-failure recovery, fabricated quotes, constraint coverage, lock-free backend calls, real OS gold-file isolation, full Python/async/thread execution, asynchronous planning/boundary application, stale plans, lineage-safe replay and grades excluded from refinement/harness. The intended verification suite must remain offline, with injected external transports and a guard against direct `codex exec` in non-live tests. Explicitly live-marked tests require separate user execution. Record any accidental live dispatch honestly; the reliability-session incident and guard limitations are documented in `docs/VERIFIED.md`.
