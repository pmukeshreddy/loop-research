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

The YAML file is the sole source of configuration values. Every setting is required, types and ranges are validated, and unknown keys are rejected. `models.root`, `models.sub`, `models.refine`, and `models.judge` independently select Codex models; `null` uses the Codex default. `models.reasoning_effort` applies to Codex calls. Adjust call concurrency and retry limits, research timeouts and budgets, RLM limits, harness retrieval count, and report rolling window there. There are no embedding models or train/validation/test splits. `wandr.final_n_tasks: null` includes the entire available WANDR release; a positive integer limits the stream.

Global options precede commands. A relative `--config` path is resolved inside `--root`:

```sh
.venv/bin/loop-research --root /path/to/workspace --config config.yaml init
.venv/bin/loop-research --root /path/to/workspace verify
```

## Research and continual learning

Research one question, optionally specifying each table column:

```sh
.venv/bin/loop-research research "Which public datasets document urban tree inventories?" \
  --columns dataset --columns city --columns publisher --columns access
```

The command prints a Markdown table with per-cell source links, the self-check result, and an archive ID. Without `--columns`, the table uses `entity` and `answer`. These commands make live subscription and web calls when you invoke them.

Run the full configured benchmark stream in deterministic order:

```sh
.venv/bin/loop-research stream --benchmark widesearch
.venv/bin/loop-research stream --benchmark widesearch --no-learning
.venv/bin/loop-research stream --benchmark wandr
.venv/bin/loop-research stream --benchmark wandr --no-learning
.venv/bin/loop-research report
```

A stream researches tasks sequentially, records independent official grades, checks the research evidence, and refines the harness. The agent can also request refinement or edit relevant harness entries during a task. Entries preserve versions, evidence run IDs, usage and self-check outcomes in Git history. Replaying an already seen task starts from its earlier harness state rather than learning from a copy of that same task's prior result.

`--no-learning` uses the matching starting harness with learning edits disabled. It retains research and grading so the results can be compared against a learning stream. Run both modes with the same config and task selection. Reports compare them only when the benchmark, ordered task IDs, starting harness SHA, judge and execution settings match. Reporting window and full-text logging settings do not change comparison eligibility. A comparison uses only tasks scored in both streams and displays the paired count; failures are listed separately.

The commands are `init`, `prepare-data`, `verify`, `research`, `stream`, and `report`. The previous round-based training and final-evaluation commands have been removed.

## Evidence, grading and limits

The research tools include single and batched search/fetch, plus evidence recording for discovery and constraint checks. Search and fetch use Codex web search; `fetch()` returns the model's rendering of a page, not raw HTML. Self-checks test whether quoted text appears in fetched material, source URLs were fetched, and each recorded task constraint has an evidence check. They also surface missing citations, empty or stalled searches, tool failures and execution limits. **These checks establish recorded coverage and quotation consistency, not factual truth, exhaustive discovery, or correct interpretation of a constraint.**

All model calls, including judges, use the Codex subscription login. The two official grading adapters retain their pinned scoring logic and label results `judge: codex/<models.judge or default>`. WideSearch reports the official row F1, item metrics and success metric. WANDR uses full-lineage soft F1 as the project primary metric and preserves the upstream soft-recall primary metric in provenance, alongside soft/hard metrics and excerpt-failure diagnostics.

WANDR independently re-fetches cited pages through the official harness's Camoufox browser and uses Codex for triage, canonicalization, deduplication and judging. The browser-primary service adapter is a project adaptation; the upstream source is unchanged. It requires no provider API keys. Quotes returned during research may fail independent excerpt checking. Official prompts and strict schemas are retained, but provider generation controls without verified Codex equivalents are not reproduced.

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
  codex_calls.jsonl              completed model call metadata
  codex_attempts/                durable attempt starts
reports/<run_id>/
  stream.json                   task order, starting harness, outcomes and scores
  grading/                      official grades, diagnostics and judge caches
reports/tasks.csv               task scores, failures and rolling means
reports/learning_curve.png      rolling available-score means by stream
reports/summary.md              stream summaries and eligible comparisons
```

The exact task archive also contains tool caches and evidence records. `codex.log_full_text` controls full prompt/response logging. Grader artifacts remain under reports, separate from research observations.

`report` reads archived stream files without model or dataset access. Missing scores remain blank in the CSV and explicit in the summary; an operational failure never becomes an invented zero. Rolling means consider scored tasks among the last `stream.rolling_window` task attempts, with the contributing count in the CSV. Curves for different streams are descriptive; the comparison table enforces the matching conditions above. No benchmark scores are claimed in this documentation.

## Tests

The default suite is offline and uses hand-written fixtures and injected external transports. It covers strict configuration, isolation, tools, self-checks, harness state, refinement, official grading adapters, orchestration, CLI and reports:

```sh
.venv/bin/python -m pytest
```

One research example is marked `live` and excluded by default. It makes subscription and web calls only if you explicitly select it after setup:

```sh
.venv/bin/python -m pytest -m live
```

The live test is defined but was not executed during implementation. Offline tests do not measure research quality or benchmark performance. Source verification evidence and any unresolved questions are in [docs/VERIFIED.md](docs/VERIFIED.md).
