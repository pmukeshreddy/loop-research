# Company research data generation

A WebShaper-inspired pipeline that ends at QA datasets, evidence, provenance,
validation records and quality reports. Training, RL, demonstrations and claims
of model improvement are outside scope.

The design inputs are [the company-research brief](2026-10-17-webshaper-data-generation.md)
and [WebShaper v1](https://arxiv.org/abs/2507.15061v1). See the
[implementation plan](docs/implementation-plan.md) and [design notes](docs/design.md).
The [run results](docs/run-results.md) document an accepted real depth-1 expansion,
distinguish earlier diagnostics from fictional fixture tests, and describe the
remaining manual review.

## Configure and test

Python 3.11+; tested with Python 3.12. The following commands run from this directory.

```bash
uv venv
uv pip install -r requirements.lock
uv pip install --no-deps -e .
export PYTHONPATH="$PWD/src"
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
```

`PYTHONPATH` intentionally selects this checkout. Some macOS environments mark
editable-install `.pth` files hidden, which makes Python skip them. These commands
work without changing machine-wide Python configuration. A normal wheel install
also works: `uv pip install '.[dev]'`; its CLI is `webshaper`.

## Offline end-to-end test

```bash
export PYTHONPATH="$PWD/src"
.venv/bin/python -m webshaper run --config configs/fixture.json --run-dir runs/fixture-demo
.venv/bin/python -m webshaper status --run-dir runs/fixture-demo
# Same command resumes; completed provider calls are reused.
.venv/bin/python -m webshaper run --config configs/fixture.json --run-dir runs/fixture-demo
```

This corpus, provider, judgments and solver responses are **fictional scripted
fixtures**, not real generated company data or empirical model performance.
Expected result: one task with one accepted expansion layer; two unsupported
product-expansion proposals are retained as rejections. All records identify
`data_mode: fixture`. Fixture mode cannot access the network; live mode rejects
fixture providers. `tests/fixtures/README.md` describes the test data.

Create fresh configuration files without overwriting existing ones:

```bash
.venv/bin/python -m webshaper init --mode fixture --output configs/my-fixture.json
.venv/bin/python -m webshaper init --mode live --output configs/my-live.json
```

## Codex subscription backend

The default live backend is the **official Codex CLI**, authenticated by ChatGPT
sign-in. There is no OpenAI API client, API-key requirement, external paid search
provider, or automatic fallback. Additional API/search budget is fixed at **$0**.
Authentication and OAuth refresh remain entirely inside Codex; this application
does not read, copy or hardcode credentials.

```bash
codex --version
codex login status
# Only if not already signed in with ChatGPT:
codex login
.venv/bin/python -m webshaper doctor --config configs/codex.json
# Optional live search capability probe: consumes subscription usage, no separate API calls.
.venv/bin/python -m webshaper doctor --config configs/codex.json --probe-search --run-dir runs/search-check
```

Each generator, expander, verifier and solver call runs in a separate
`codex exec --ephemeral --output-schema` session. Codex is forced to use ChatGPT
authentication and its OpenAI provider; API credential environment variables are
removed from child environments. User config, project instructions, plugins,
apps, shell execution, browser/computer control and delegation are disabled.
The execution host remains enabled because Codex built-in web search needs it.
Local source text is supplied in the prompt, not through arbitrary file access.

These options follow the official [non-interactive execution documentation](https://learn.chatgpt.com/docs/non-interactive-mode)
and [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).
Built-in search uses [Codex web search](https://learn.chatgpt.com/docs/web-search).
The first compatibility probe was run on Codex CLI 0.163.0.

`model` and `reasoning_effort` are configurable separately for all four roles.
`model: null` uses the installed CLI's default; pin a supported model name for
more repeatable experiments. Runtime version, requested model settings, prompt,
schema and implementation hashes are recorded. Independent sessions do not
guarantee independent model errors.

## Prepare and run real sources

Edit `configs/codex.json` (or a new config created with `init`):

- `sources`: URLs or paths to TXT, HTML or PDF documents. Paths are relative to
  the configuration file. Supply `published_at` only from a documented source,
  and explain it in `date_basis`; otherwise the HTML publication metadata is used.
- `allowed_domains`: exact hostnames permitted for capture and discovery.
  Redirect destinations must be configured explicitly. Crawling respects
  robots rules, byte/source limits and `crawl_depth` (default zero).
- `as_of`: an ISO date; default policy requires both effective dates and
  publication dates no later than that cutoff. `allow_retrospective` is explicit.
- `scope`: `identified_target` with an expected count, or `corpus_bounded` with
  the complete canonical candidate-ID list. Unknown candidates block acceptance.
- `search_provider`: `codex` enables subscription search for expansion evidence;
  `none` restricts generation to the supplied sources. Search snippets never
  become evidence. All model-generated facts must cite fetched text.
- `redistributable`: defaults false; only set true when source reuse permits it.

Default live target is 10 accepted unique tasks, bounded by 20 seed attempts,
one expansion layer, five browsing attempts, one revision and concurrency 1.
Concurrency 2 permits two independent solver attempts at once; candidate
generation remains sequential. Budgets bound calls, tokens and search actions.
Keep concurrency 1 for the first pilot. Review every accepted pilot task before
increasing `target_tasks` and `max_seed_attempts`.

`configs/live-smoke.json` is a ready-to-run, one-task integration configuration
using real Apptronik and Bedrock Robotics announcements, a 2025-12-31 cutoff,
two seed attempts, one expansion layer and concurrency 1. Publication dates
include a documented basis in each announcement. It is separate from the
fictional fixture configuration and the larger diagnostic batch. Run it with:

```bash
.venv/bin/python -m webshaper run --config configs/live-smoke.json --run-dir runs/my-live-smoke
.venv/bin/python -m webshaper status --run-dir runs/my-live-smoke
```

This consumes Codex subscription usage. A live run can reject every candidate;
the configured target is not a promise of acceptance. See
[verification notes](docs/verification-log.md) for the checks actually run.

`configs/real-expansion.json` supplies four primary investor announcements:
Cerbos and Cradle in 2023, plus Fullview and Salesroom in 2022. The comparison
company makes the investor dependency necessary; the earlier announcements
can identify that investor independently of the final answer. Dates use visible
article datelines, with their basis recorded in the config. Discovery used Codex
search; this curated run sets `search_provider: none` to keep the source bundle
fixed. Every generation and validation role still uses a fresh live Codex session.
Limits remain 50 calls, 1,500,000 tokens, 15 search actions, concurrency 1 and $0
additional paid spend. To run and resume in your own fresh directory:

```bash
export PYTHONPATH="$PWD/src"
.venv/bin/python -m webshaper doctor --config configs/real-expansion.json
.venv/bin/python -m webshaper run --config configs/real-expansion.json --run-dir runs/my-real-expansion
.venv/bin/python -m webshaper status --run-dir runs/my-real-expansion
# Resume completed checkpoints without repeating calls:
.venv/bin/python -m webshaper run --config configs/real-expansion.json --run-dir runs/my-real-expansion
```

Check `depth_distribution` and the reference's `actual_layer`: a retained depth-0
seed does not establish a successful expansion. Results are model-dependent.

```bash
.venv/bin/python -m webshaper run --config configs/codex.json --run-dir runs/live-pilot
.venv/bin/python -m webshaper status --run-dir runs/live-pilot
# Resume after a normal interruption, using exactly the same configuration:
.venv/bin/python -m webshaper run --config configs/codex.json --run-dir runs/live-pilot
# Only after a subscription limit has reset:
.venv/bin/python -m webshaper run --config configs/codex.json --run-dir runs/live-pilot --retry-limited
```

Missing sources produce explicit errors and no fabricated output. The CLI exits
75 on a checkpointed pause, 1 on failure, and 0 when all bounded work is complete.
Always inspect `target_reached`: completing attempts need not reach the target.

Completed calls are durably cached. A timeout, crash during a call, or unknown
provider outcome is **not automatically retried**. Inspect `usage.jsonl` and
`run.sqlite`; keep the original run as an audit record. There is deliberately no
blind retry-unknown switch. To authorize new work, create a new run with its own
bounded configuration; it may consume additional subscription usage.

Tokens are observed after Codex turns. Reservations stop new sessions before
the run limit; a single turn can exceed its reservation, after which no further
work is dispatched. Search events are monitored and an over-budget session is
terminated, but an already initiated action may finish. Subscription limits
pause the run with no external fallback. The application cannot inspect account
credit-purchase policy; keep automatic extra-credit purchases disabled if needed.

Configuration, local input contents, implementation, prompts and runtime are
frozen on resume. Changes require a new run directory. Source snapshots and
candidate versions are never overwritten. Source-fetch failures are frozen in
the run; retry changed access conditions in a new run.
The `export` and `review` commands also work after code upgrades: they reuse the
original generation settings from the journal, verify snapshots, and make no
model calls. The manifest records the exporter hash separately.

## Dataset and review

`RUN/export/` contains:

| File | Content |
| --- | --- |
| `tasks.jsonl` | Public X: question, schema, cutoff, scope and permitted environment |
| `references.jsonl` | Private Y, query, answer evidence and completeness decisions |
| `provenance.jsonl` | All candidate versions, lineage, leaf replacements, models and hashes |
| `graphs.jsonl`, `sources.jsonl` | Frozen graph snapshots, fact/evidence records and source metadata |
| `validation.jsonl` | Checks and isolated solver attempts for evaluated candidates |
| `attempts.jsonl` | Candidate validation starts, including work paused before a final decision |
| `rejected.jsonl`, `errors.jsonl` | Revisions/rejections, reasons, capture/extraction errors |
| `usage.jsonl` | Call status, tokens, search actions, latency and $0 additional API cost |
| `manifest.json` | Frozen configuration, versions, hashes, metrics and partition membership |
| `quality_report.md` | Counts, coverage, audit results, screens, depth, costs and limitations |
| `public/` | X and redistributable corpus text only; never reference or validation files |

All snapshots remain in `RUN/sources/`. **Do not mount the entire run directory
in a solver environment**. The built-in solver receives only public X and its
dated source documents; it has no file tools and never receives Y, the graph,
evidence map, previous answers or generator history. Closed-book sessions receive
neither sources nor web tools. Browsing validation currently uses the frozen
corpus, making evidence and access reproducible. Live web discovery is used for
expansion; this is not a general web-browsing research agent.

Public source text with unknown redistribution rights is withheld. Such corpus
tasks need separately authorized access to the associated snapshots; the public
directory alone is not advertised as self-contained for those tasks.
Public corpus entries also follow the validator's temporal access policy:
undated sources are excluded, and post-cutoff sources require explicit
`allow_retrospective`. Exclusion removes the entire entry, including its URL and
title; original snapshots and metadata remain private for auditing.

Record real human reviews, then regenerate the export:

```bash
.venv/bin/python -m webshaper review --run-dir runs/live-pilot \
  --task-id TASK_ID --decision approved --reviewer 'Reviewer name' \
  --notes 'Checked dates, answer set, source spans, wording and alternative answers.'
.venv/bin/python -m webshaper export --run-dir runs/live-pilot
.venv/bin/python -m webshaper schemas --output schemas
```

Human rejections remove the task from export while preserving its history.
Automated acceptance is labeled `pending_manual_review` until reviewed.
Partition names are dataset split labels only; there is no training command.

The query engine currently returns canonical entity sets (not multi-column
tables). Exhaustive exclusions need an explicit negative rooted condition in
each union branch; unsupported cases remain unresolved rather than being
treated as false. This conservative first path favors rejection over invented
completeness. Checkpoints use SQLite and a local process lock; distributed
workers are outside this implementation.
