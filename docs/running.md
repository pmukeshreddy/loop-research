# Configuration and live runs

Start with the [README quickstart](../README.md#quickstart) to install dependencies
and verify the offline path. Run the commands below from the repository root
with `PYTHONPATH` set as in that quickstart. [Recorded results](run-results.md)
distinguish real generation from fictional fixture behavior.

## Choose a configuration

| Configuration | Purpose |
| --- | --- |
| [`fixture.json`](../configs/fixture.json) | One fictional scripted task; no network or model calls |
| [`company-campaign.json`](../configs/company-campaign.json) | Current discovery target: 50 companies × 5 accepted open-web questions; shared bounded usage |
| [`open-web.json`](../configs/open-web.json) | Historical four-company open-web pilot; not the generation boundary |
| [`real-expansion.json`](../configs/real-expansion.json) | Legacy corpus pilot using four dated primary investor announcements |
| [`live-smoke.json`](../configs/live-smoke.json) | Earlier Apptronik/Bedrock integration configuration |
| [`codex.json`](../configs/codex.json) | Larger live template; supply sources before running |

Use the [company campaign guide](company-campaign.md) for current live commands,
discovery, quotas, coverage reports and explicit budget extensions.
The historical open-web and real-expansion configurations include Cerbos and Cradle announcements from
2023 and Fullview and Salesroom announcements from 2022. Comparison companies
and independent co-investment relationships support a necessary expansion.
Publication dates have documented bases. Discovery used Codex search; this
configurations set `search_provider: none` to keep generation evidence fixed.
Open-web solver and alternative-audit sessions still use live hosted search;
this setting controls generation discovery only. Every model role uses a fresh Codex session.

The open-web pilot permits 49 calls, 1,447,740 tokens and 13 web actions,
reserving the remainder of the existing 50-call/1.5M-token/15-action allowance
for the recorded capability probe. It uses concurrency 1, two seed attempts,
one layer, one browsing attempt per candidate and one revision. Search, page
open and in-page find each count as an action. Solver/verifier calls reserve four
actions, request at most three, and stop if the fourth is observed; generation
discovery reserves three and requests at most two. The spare action is a stop
margin because the CLI reports activity after dispatch.
Legacy real-expansion uses five corpus-solving attempts per candidate.
The larger template targets 10 unique tasks within 20 seed attempts. A target
is not a promise of acceptance; a run may reject every candidate.

Create a separate editable configuration without overwriting an existing file:

```bash
.venv/bin/python -m webshaper init --mode live --output configs/my-live.json
```

Live init defaults to a 50 × 5 discovery campaign with `research_mode: open_web`; absent modes in old files mean
`legacy_corpus`. `--mode fixture` creates a legacy offline configuration instead.
The open-web acceptance/rejection fixtures run with `pytest tests/test_open_web.py`;
their tool traces and judgments are scripted and cannot demonstrate real browsing.
Model and search
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
- `research_mode`: `open_web` for self-contained questions; `legacy_corpus` for
  historical corpus experiments. Never reuse a run directory across modes.
- `scope`: open-web mode requires `identified_target` without a private candidate
  universe. Legacy mode also permits `corpus_bounded` with a complete canonical
  candidate-ID list. Graph uniqueness never proves open-web uniqueness.
- `search_provider`: `codex` enables built-in subscription search for expansion
  evidence; `none` uses only supplied sources. Snippets never become evidence;
  claims must cite captured source text.
- `redistributable`: false unless source reuse permits public text export.
- `generator`, `expander`, `verifier`, `solver`: separate `model` and
  `reasoning_effort` settings. `model: null` uses the installed CLI default.
- `budget`: bounds calls, tokens and searches; additional paid spend is $0.
  Keep `concurrency: 1` for the pilot. Open-web validation is sequential;
  higher values only parallelize legacy corpus attempts.

Accepted live tasks remain pending human review; larger targets do not bypass validation.
Requested models, runtime version, configuration, prompts and schemas are recorded.
Separate sessions do not guarantee independent model errors.

## Authentication and a live run

The official Codex CLI owns ChatGPT sign-in and OAuth refresh. The pipeline does
not read or copy tokens, accept API keys, or fall back to a paid API/search provider.
Check your login; run `codex login` only if ChatGPT sign-in is needed.

```bash
codex --version
codex login status
.venv/bin/python -m webshaper doctor --config configs/company-campaign.json
.venv/bin/python -m webshaper run --config configs/company-campaign.json --run-dir runs/my-company-campaign
.venv/bin/python -m webshaper status --run-dir runs/my-company-campaign
```

Substitute your config and a fresh run directory when using different sources or
settings. Check `target_reached`, `depth_distribution`, and the reference's
`actual_layer`: a retained depth-0 seed does not establish an accepted expansion.

To check built-in search availability separately:

```bash
.venv/bin/python -m webshaper doctor --config configs/company-campaign.json --probe-search --run-dir runs/search-check
```

This optional probe consumes a separate bounded Codex subscription session; account
for it in any aggregate allowance. It requires observed search and page opening.
Missing search capability
is reported; there is no external provider fallback. Built-in search and structured
output were observed with Codex CLI 0.163.0; see [run results](run-results.md).

## Role isolation

Each generator, expander, verifier and solver call uses a separate
`codex exec --ephemeral --output-schema` session. The adapter forces ChatGPT
authentication and Codex's OpenAI provider, removes API credential environment
variables, and disables user configuration, project instructions, plugins, apps,
shell execution, browser/computer control and delegation. A custom Codex permission
profile denies filesystem access except minimal runtime paths and an empty role
directory containing its output schema. Local network access is disabled; the
hosted web tool works independently. `--sandbox` must not override this profile.

Open-web solvers receive only a question string, response requirements, and a fixed
action budget. They receive no corpus, source list, reference URL, graph, answer or
generator history. Closed-book sessions have zero tools. Legacy corpus solvers
retain their original document-based environment and remain labeled accordingly.
See [open-web validation](open-web-design.md) for independent citation, alternative
and shortcut checks and their limits.

Adapter references: [non-interactive execution](https://learn.chatgpt.com/docs/non-interactive-mode),
[configuration](https://learn.chatgpt.com/docs/config-file/config-reference), and
[web search](https://learn.chatgpt.com/docs/web-search), and
[permissions](https://learn.chatgpt.com/docs/permissions).

## Checkpoints and limits

Repeat the same run command to resume; completed model calls are cached.
Configuration, local input contents, implementation, prompts and runtime are frozen.
Changes require a new run directory. Original snapshots, failed captures and
candidate versions remain available for audit.

Subscription limits pause the run without an external fallback. Only after the
limit resets, explicitly retry those calls:

```bash
.venv/bin/python -m webshaper run --config configs/company-campaign.json --run-dir runs/my-company-campaign --retry-limited
```

Tokens are observed after a Codex turn. Reservations stop new calls before the
configured limit, but a turn can exceed its reservation; subsequent dispatch then
stops. Web sessions stop at the reserved margin, retaining already queued events
and conservative usage. Hosted work already in flight may finish; this local CLI
guard is not an upstream hard quota. The pipeline cannot inspect account-level
extra-credit purchase policy.

Timeouts, crashes during calls and unknown remote outcomes are not automatically
retried. Inspect `usage.jsonl` and `run.sqlite`; there is no blind retry-unknown
switch. Preserve the original run and use a new bounded run for new work.

CLI exit codes: 0 means bounded work completed, 75 means checkpointed pause, and
1 means failure. Completion does not imply the requested number or depth of tasks.
[Export and review](outputs.md#human-review) can operate after a code upgrade
using the original journal configuration without making model calls.
