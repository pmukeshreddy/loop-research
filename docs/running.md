# Configuration and live runs

Start with the [README quickstart](../README.md#quickstart) to install dependencies
and verify the offline path. Run the commands below from the repository root
with `PYTHONPATH` set as in that quickstart. [Recorded results](run-results.md)
distinguish real generation from fictional fixture behavior.

## Choose a configuration

| Configuration | Purpose |
| --- | --- |
| [`fixture.json`](../configs/fixture.json) | One fictional scripted task; no network or model calls |
| [`real-expansion.json`](../configs/real-expansion.json) | One-task live pilot using four dated primary investor announcements |
| [`live-smoke.json`](../configs/live-smoke.json) | Earlier Apptronik/Bedrock integration configuration |
| [`codex.json`](../configs/codex.json) | Larger live template; supply sources before running |

The real-expansion configuration includes Cerbos and Cradle announcements from
2023 and Fullview and Salesroom announcements from 2022. Comparison companies
and independent co-investment relationships support a necessary expansion.
Publication dates have documented bases. Discovery used Codex search; this
configuration sets `search_provider: none` to keep the supplied source bundle
fixed during generation. Every model role still uses a live Codex session.

Its limits are 50 calls, 1,500,000 tokens, 15 search actions, concurrency 1, two
seed attempts, one expansion layer, five browsing attempts and one revision.
The larger template targets 10 unique tasks within 20 seed attempts. A target
is not a promise of acceptance; a run may reject every candidate.

Create a separate editable configuration without overwriting an existing file:

```bash
.venv/bin/python -m webshaper init --mode live --output configs/my-live.json
```

`--mode fixture` creates an offline configuration instead. Model and search
providers are configured separately; the supported model backends are Codex
and labeled fixtures, with no separately billed API adapter.

## Configure sources and scope

- `sources`: URLs or local TXT, HTML or PDF paths, relative to the configuration
  file. Set `published_at` only from a documented source and explain it in
  `date_basis`; otherwise HTML publication metadata is used.
- `allowed_domains`: exact hostnames allowed for capture and discovery. Configure
  redirect destinations explicitly. Crawling respects robots rules, byte/source
  limits and `crawl_depth` (zero by default).
- `as_of`: fixed ISO cutoff. The default requires effective and publication dates
  no later than this date. Retrospective access requires `allow_retrospective`;
  undated sources still cannot support historical validation.
- `scope`: `identified_target` with an expected count, or `corpus_bounded` with
  a complete canonical candidate-ID list. Unknown membership blocks acceptance.
- `search_provider`: `codex` enables built-in subscription search for expansion
  evidence; `none` uses only supplied sources. Snippets never become evidence;
  claims must cite captured source text.
- `redistributable`: false unless source reuse permits public text export.
- `generator`, `expander`, `verifier`, `solver`: separate `model` and
  `reasoning_effort` settings. `model: null` uses the installed CLI default.
- `budget`: bounds calls, tokens and searches; additional paid spend is $0.
  Keep `concurrency: 1` for the pilot. Higher values only parallelize independent
  solver attempts; candidate generation remains sequential.

Review accepted pilot tasks before increasing source coverage or target size.
Requested models, runtime version, configuration, prompts and schemas are recorded.
Separate sessions do not guarantee independent model errors.

## Authentication and a live run

The official Codex CLI owns ChatGPT sign-in and OAuth refresh. The pipeline does
not read or copy tokens, accept API keys, or fall back to a paid API/search provider.
Check your login; run `codex login` only if ChatGPT sign-in is needed.

```bash
codex --version
codex login status
.venv/bin/python -m webshaper doctor --config configs/real-expansion.json
.venv/bin/python -m webshaper run --config configs/real-expansion.json --run-dir runs/my-real-expansion
.venv/bin/python -m webshaper status --run-dir runs/my-real-expansion
```

Substitute your config and a fresh run directory when using different sources or
settings. Check `target_reached`, `depth_distribution`, and the reference's
`actual_layer`: a retained depth-0 seed does not establish an accepted expansion.

To check built-in search availability separately:

```bash
.venv/bin/python -m webshaper doctor --config configs/codex.json --probe-search --run-dir runs/search-check
```

The probe consumes a bounded Codex subscription session. Missing search capability
is reported; there is no external provider fallback. Built-in search and structured
output were observed with Codex CLI 0.163.0; see [run results](run-results.md).

## Role isolation

Each generator, expander, verifier and solver call uses a separate
`codex exec --ephemeral --output-schema` session. The adapter forces ChatGPT
authentication and Codex's OpenAI provider, removes API credential environment
variables, and disables user configuration, project instructions, plugins, apps,
shell execution, browser/computer control and delegation. The execution host
stays enabled for built-in web search. Source text is supplied in prompts;
roles do not receive arbitrary file access.

Solvers receive public tasks and permitted frozen documents only. Closed-book
sessions receive no documents or tools. Private references, evidence graphs,
previous solver answers and generator history are withheld from solver inputs.
See [design](design.md) for the independent validation gates.

Adapter references: [non-interactive execution](https://learn.chatgpt.com/docs/non-interactive-mode),
[configuration](https://learn.chatgpt.com/docs/config-file/config-reference), and
[web search](https://learn.chatgpt.com/docs/web-search).

## Checkpoints and limits

Repeat the same run command to resume; completed model calls are cached.
Configuration, local input contents, implementation, prompts and runtime are frozen.
Changes require a new run directory. Original snapshots, failed captures and
candidate versions remain available for audit.

Subscription limits pause the run without an external fallback. Only after the
limit resets, explicitly retry those calls:

```bash
.venv/bin/python -m webshaper run --config configs/real-expansion.json --run-dir runs/my-real-expansion --retry-limited
```

Tokens are observed after a Codex turn. Reservations stop new calls before the
configured limit, but a turn can exceed its reservation; subsequent dispatch then
stops. Search events are monitored and excess-search sessions are terminated,
though an initiated action may finish. The pipeline cannot inspect account-level
extra-credit purchase policy.

Timeouts, crashes during calls and unknown remote outcomes are not automatically
retried. Inspect `usage.jsonl` and `run.sqlite`; there is no blind retry-unknown
switch. Preserve the original run and use a new bounded run for new work.

CLI exit codes: 0 means bounded work completed, 75 means checkpointed pause, and
1 means failure. Completion does not imply the requested number or depth of tasks.
[Export and review](outputs.md#human-review) can operate after a code upgrade
using the original journal configuration without making model calls.
