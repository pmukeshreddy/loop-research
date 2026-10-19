> Current status (2026-10-18): the continual harness replaces the historical gated design. The reliability changes and testing incident are recorded in the final section. An unmocked regression accidentally made live refinement calls during this work; do not describe the current implementation session as entirely offline. No benchmark performance result is claimed. Earlier records below describe their own historical verification passes and are superseded where the current contract differs.

# Verify-first findings

Checked on 2026-10-18 in `/Users/mukeshreddypochamreddy/Desktop/loop-research`.
Specification: [PIPELINE_SPEC.md](../PIPELINE_SPEC.md), read completely before other work.

**Historical status from the original ATLAS spec (superseded below).**
No official, publicly accessible Exa ATLAS dataset or grader was located. The
publisher still describes their release as forthcoming. Section 3.3 explicitly
requires stopping if the dataset is unavailable. Accordingly, no dataset schema,
answer-key parser, grader, pipeline, project tests, or project README was invented.

The independent RLM and Codex checks below are complete at the source/help/import
level. Source inspection is distinguished from live execution. No model calls,
live tests, `smoke`, `run`, `improve`, or `evaluate` were executed.

## Verification status

| Spec item | Result | Evidence |
| --- | --- | --- |
| 3.1 pinned RLM installation and Python requirement | Confirmed | `evidence/rlm-install.txt`, `evidence/rlm-import.txt` |
| 3.1 client interface, backend routing, usage | Confirmed in pinned source | RLM source references below |
| 3.1 REPL injection and completion protocol | Confirmed in pinned source | RLM source references below |
| 3.1 system prompt, constructor, subcalls, logger | Confirmed in pinned source | RLM source references below |
| 3.2 installed version and required CLI options | Confirmed by installed CLI | `evidence/codex-version.txt`, `evidence/codex-exec-help.txt` |
| 3.2 web-search configuration | Confirmed in matching release source | Codex source references below |
| 3.2 login | Confirmed: ChatGPT | `evidence/codex-login-status.txt` |
| 3.2 rate/usage-limit behavior | Confirmed in matching release source; not triggered live | Codex error references below |
| 3.3 official dataset and grader release | **Blocked: no release located** | Exa announcement, GitHub, and Hugging Face evidence below |
| 3.3 exact fields, required columns, reference dates, answer-key encoding | **Unverified: distribution unavailable** | Open questions |
| 3.3 metric definitions | Published descriptions verified; executable matching rules unavailable | Exa grading section |

## 3.1 RLM

### Source and installation

- Official repository: <https://github.com/alexzhang13/rlm>.
- Pinned commit: **`d04208afbad29ca675ab13478c40ee8bebc84bfe`**.
- Local, unmodified source: `.verification/rlm/` (detached checkout).
- Distribution name is `rlms`; import name is `rlm`; installed distribution version
  is `0.1.3`. Source: `.verification/rlm/pyproject.toml:2-10`.
- Requires Python `>=3.11`; upstream's manual installation shows `uv` with Python
  3.12. Source: `pyproject.toml:10`, `README.md:42-44,65-71` in that checkout.
- Created `.venv/` with Python 3.12.12 and installed directly from the pinned Git
  URL, including upstream dependencies. No provider API keys were used.

Commands actually executed:

```text
$ git ls-remote https://github.com/alexzhang13/rlm.git HEAD
d04208afbad29ca675ab13478c40ee8bebc84bfe	HEAD
$ git -C .verification/rlm rev-parse HEAD
d04208afbad29ca675ab13478c40ee8bebc84bfe
$ uv venv --python 3.12 .venv
Using CPython 3.12.12
$ uv pip install --python .venv/bin/python 'rlms @ git+https://github.com/alexzhang13/rlm.git@d04208afbad29ca675ab13478c40ee8bebc84bfe'
```

Full commands, exit codes, stdout, and stderr are in
[rlm-remote.txt](evidence/rlm-remote.txt),
[rlm-clone.txt](evidence/rlm-clone.txt),
[rlm-checkout.txt](evidence/rlm-checkout.txt),
[rlm-pin.txt](evidence/rlm-pin.txt),
[rlm-venv.txt](evidence/rlm-venv.txt), and
[rlm-install.txt](evidence/rlm-install.txt).

[rlm-import.txt](evidence/rlm-import.txt) contains the exact offline inspection
command and full output. It imported `RLM`, `BaseLM`, `LocalREPL`, `LMHandler`,
`RLMLogger`, and usage types, printed their actual signatures, and asserted that
installed `direct_url.json` records this commit. Import path:
`.venv/lib/python3.12/site-packages/rlm/__init__.py`.

### Client contract and integration constraints

All following paths are relative to `.verification/rlm/`. A line-numbered command
transcript is preserved in [rlm-source-evidence.txt](evidence/rlm-source-evidence.txt).
Permanent source links can be formed under
<https://github.com/alexzhang13/rlm/tree/d04208afbad29ca675ab13478c40ee8bebc84bfe>.

| Finding | Pinned source |
| --- | --- |
| `BaseLM(model_name, timeout=300.0, sampling_args=None, **kwargs)` stores configuration | `rlm/clients/base_lm.py:16-29` |
| Required sync `completion(self, prompt: str \| dict[str, Any]) -> str` | `rlm/clients/base_lm.py:31-33` |
| Required async `acompletion(self, prompt: str \| dict[str, Any]) -> str` | `rlm/clients/base_lm.py:35-37` |
| Required `get_usage_summary() -> UsageSummary` and `get_last_usage() -> ModelUsageSummary` | `rlm/clients/base_lm.py:39-47` |
| Actual root prompts are lists of role/content dictionaries despite the narrower abstract annotation | `rlm/core/rlm.py:300-324,394-408,646-657`; `rlm/utils/prompts.py:242-245` |
| `get_client(backend, backend_kwargs)` uses a fixed conditional dispatcher; unknown names raise `ValueError`. There is no public client-registration hook on `RLM`. | `rlm/clients/__init__.py:11-59`; `rlm/core/rlm.py:49-81,226-256` |
| Usage requires integer call/input-token/output-token totals and optional cost; summary is a mapping from model names | `rlm/core/types.py:42-110` |

Integration conclusion, **not an implemented adapter**: subclass `BaseLM`, then
subclass `RLM` inside this project to supply Codex clients through
`_spawn_completion_context`. `LMHandler` accepts actual client objects. Also
override `_fallback_answer` and `_subcall`: upstream's implementations call the
fixed `get_client`, and `_subcall` constructs `RLM(...)` rather than `type(self)`.
Only overriding the root context would miss recursive calls. Source:
`rlm/core/rlm.py:698-704,706-743,808-836`.

Codex exposes actual token usage through `--json` (see 3.2), so the adapter should
use those fields instead of inventing token estimates from characters. Character
counts remain separate archive fields. A missing usage event must be recorded
as missing, not silently represented as measured token usage. No such adapter
has been built because implementation stopped at 3.3.

### REPL functions, termination, and prompts

| Finding | Pinned source |
| --- | --- |
| `LocalREPL` accepts `custom_tools`, `custom_sub_tools`, handler address, context, depth, and subcall callback | `rlm/environments/local_repl.py:153-188` |
| `setup()` installs `llm_query`, `llm_query_batched`, `rlm_query`, and `rlm_query_batched` in `self.globals` | `rlm/environments/local_repl.py:222-227` |
| Supported custom functions go into globals; noncallable custom values go into locals | `rlm/environments/local_repl.py:234-242` |
| Supported tool formats are a callable/value or `{"tool": callable_or_value, "description": text}` | `rlm/environments/base_env.py:41-63,81-93,96-127` |
| Reserved tool names are rejected | `rlm/environments/base_env.py:13-24,130-148` |
| `answer` starts with content and ready fields. Setting ready truthy captures `str(content)` | `rlm/environments/local_repl.py:26-47,229-245` |
| RLM reads `REPLResult.final_answer` after code execution and returns it when present | `rlm/core/rlm.py:413-453` |
| If iterations exhaust, upstream makes another final-answer LM call; a total-call limit must include it | `rlm/core/rlm.py:470-490,673-696` |
| `custom_system_prompt` replaces the default template; `_setup_prompt` passes it through the builder | `rlm/core/rlm.py:49-81,174,300-324` |
| Builder uses `str.format(custom_tools_section=...)`, appends an orchestrator addendum by default, and puts `root_prompt` in a user message | `rlm/utils/prompts.py:211-245` |

Therefore pass `search` and `fetch` through the supported `custom_tools` argument;
a `LocalREPL` subclass is unnecessary for injection. The comment mentioning tool
tuples in `local_repl.py:235` is inconsistent with the parser; the parser's dict
format is authoritative. JSON output must be serialized to a string before
assigning `answer["content"]`: `str(a_python_dict)` is not JSON. JSON braces in a
custom system template need escaping for `str.format`, or the contract can be
placed in `root_prompt`.

Constructor parameters were verified by import inspection, not inferred from
README examples: `max_iterations`, `max_depth`, `environment`,
`environment_kwargs`, `logger`, `other_backends`, `other_backend_kwargs`,
`max_timeout`, custom tools, and `max_concurrent_subcalls` all exist. There is no
`sub_model` constructor argument; upstream supports one additional backend.
Source: `rlm/core/rlm.py:49-81,145-156`.

`max_timeout` is checked between iterations, not a hard interruption of executing
Python. `LocalREPL` is in-process and exposes `open` and `__import__`; read-only
Codex scratch directories alone do not prevent REPL access to answer files.
These matter for the specification's task-timeout and answer-isolation
requirements. Source: `rlm/core/rlm.py:361-363,492-510`;
`rlm/environments/local_repl.py:115-116`; upstream `README.md:51`.

### LM routing

- Root turns call `lm_handler.completion(prompt)`, which selects the default
  client. Source: `rlm/core/rlm.py:646-657`, `rlm/core/lm_handler.py:225-227`.
- REPL `llm_query(prompt, model=None)` sends an `LMRequest` containing its
  environment depth. Source: `rlm/environments/local_repl.py:258-278`.
- A named registered model overrides depth routing. At depth one the additional
  client is selected if provided; otherwise the default client is used. Source:
  `rlm/core/lm_handler.py:153-191`.
- Single requests invoke `completion`; batched requests invoke `acompletion`
  concurrently and preserve per-prompt failures. Source:
  `rlm/core/lm_handler.py:61-135`.
- `rlm_query` can invoke the recursive callback when configured; otherwise it
  falls back to a plain LM query. Source:
  `rlm/environments/local_repl.py:313-333`.
- The upstream batched handler reads `get_last_usage()` once after the batch and
  reuses it in successful result records. Per-call archive usage must therefore
  come from the backend call records; these trajectory usage records must not
  be summed as if independently measured. Source:
  `rlm/core/lm_handler.py:100-131`.

### Logger format

`RLMLogger(log_dir=None, file_name="rlm")` keeps memory records by default. With a
directory it creates `<file_name>_<timestamp>_<uuid-fragment>.jsonl`; it does not
accept an exact `trajectory.jsonl` filename. Archive integration must deliberately
copy/rename the actual file or adapt the logger. Source:
`rlm/logger/rlm_logger.py:26-39`.

The JSONL format is verified as follows:

- Metadata line: `type="metadata"`, timestamp, root model, maximum depth and
  iterations, backend/kwargs, environment type/kwargs, other backends.
- Iteration lines: `type="iteration"`, one-based iteration number, timestamp,
  prompt, response, code blocks, final answer, iteration time.
- Each code block contains `code` and `result`; result contains stdout, stderr,
  serialized locals, execution time, **`rlm_calls`**, and final answer. A parser
  expecting a serialized `llm_calls` key would be wrong.
- Each nested call contains root model, prompt, response, usage summary,
  execution time, and optional metadata/error.

Sources: `rlm/logger/rlm_logger.py:41-87`;
`rlm/core/types.py:118-145,161-223,232-256`. Reflection should extract code,
stdout/stderr and nested call records from these actual fields, then apply its
character cap. No sample trajectory or model output has been fabricated.

## 3.2 Codex CLI

### Installed CLI and login

```text
$ codex --version
codex-cli 0.163.0
$ codex login status
Logged in using ChatGPT
```

Both commands exited zero. Login status is emitted on stderr; this is not an
error. `codex login --help` explicitly lists `status`.
Evidence: [codex-version.txt](evidence/codex-version.txt):1-6,
[codex-login-help.txt](evidence/codex-login-help.txt):1-11,
[codex-login-status.txt](evidence/codex-login-status.txt):1-6.
Executable located at `/opt/homebrew/bin/codex`.

All required flags were confirmed in the installed `codex exec --help`, whose
complete output is in [codex-exec-help.txt](evidence/codex-exec-help.txt):

| Backend input | Evidence lines |
| --- | --- |
| Prompt from stdin via `-` | 15-19 |
| `-c key=value` TOML configuration override | 22-28 |
| `--model` | 43-44 |
| `--sandbox read-only` | 56-59 |
| `--cd` | 72-73 |
| `--skip-git-repo-check` | 90-91 |
| `--output-schema` | 102-103 |
| `--output-last-message` | 114-115 |
| Additional useful flags: `--json`, `--color never`, `--ephemeral`, `--ignore-user-config` | 93-112 |

No completion was submitted to test these flags. Help confirms syntax; actual
model execution remains for the user's live verification.

### Matching source, web search, and usage

Official source: <https://github.com/openai/codex>.
Tag **`rust-v0.163.0`** resolves to commit
**`83086188ae0614bd882818ff1aa23f3194962012`**. Unmodified checkout:
`.verification/codex/`. This is the release source matching the installed
version, not a claim that the installed binary was independently rebuilt.
Evidence: [codex-source-tag.txt](evidence/codex-source-tag.txt),
[codex-source-clone.txt](evidence/codex-source-clone.txt),
[codex-source-pin.txt](evidence/codex-source-pin.txt).

All paths in the rest of this subsection are relative to that checkout.
Line-numbered command output is in
[codex-source-evidence.txt](evidence/codex-source-evidence.txt).

- Use `-c 'web_search="live"'` for web calls and
  `-c 'web_search="disabled"'` for non-web calls. These values are verified in
  `codex-rs/core/config.schema.json:8106-8112` and
  `codex-rs/protocol/src/config_types.rs:371-382`. Explicit configuration takes
  precedence over legacy feature flags at
  `codex-rs/core/src/config/mod.rs:2735-2746`. The turn resolver preserves an
  allowed preferred mode, subject to provider/administrator constraints, at
  `3147-3191`.
- The top-level help has `--search`, but `codex exec --help` does not advertise it
  as an exec option. The config key avoids assuming that flag is accepted after
  `exec`. See [codex-help.txt](evidence/codex-help.txt):124-126.
- Reasoning effort uses `-c 'model_reasoning_effort="high"'` when explicitly
  configured; omit it when null. The configuration key is at
  `codex-rs/core/config.schema.json:7866-7868`. In this release, `ReasoningEffort`
  is a nonempty string advertised by the model, not a fixed enum
  (`4069-4073`). The example `high` must only be requested for a model that
  supports it; no model availability has been tested.
- `--json` supplies `turn.completed.usage` with `input_tokens`,
  `cached_input_tokens`, `cache_write_input_tokens`, `output_tokens`, and
  `reasoning_output_tokens`. Source:
  `codex-rs/exec/src/exec_events.rs:19-24,49-73`;
  `codex-rs/exec/src/event_processor_with_jsonl_output.rs:509-535`.
  Use input/output totals for RLM usage and retain character counts separately.
  Cached/reasoning subsets must not be added a second time. The emitter defaults
  usage fields to zero when it received no usage update; zero fields alone do
  not establish a measured zero-token call. See
  `codex-rs/exec/src/event_processor_with_jsonl_output.rs:118-128`.

Official documentation was also opened:
<https://developers.openai.com/codex/config-reference/> redirects to
<https://learn.chatgpt.com/docs/config-file/config-reference>.
Version-specific conclusions above rely on the pinned release source and local
help, not on assuming the moving documentation matches the installed version.

### Rate limits and usage limits

Confirmed from the matching source, **not from a live error induced on this account**:

| Condition | Verified behavior and source |
| --- | --- |
| Stream rate limit | `rate_limit_exceeded` and `slow_down` become a rate-limit error; retry delays can come from headers or message text. `codex-rs/codex-api/src/sse/responses_error.rs:90-115` |
| Rendered rate limit | Prefix `rate limit exceeded:`. `codex-rs/protocol/src/error.rs:121-123` |
| HTTP usage limit | HTTP 429 with error type `usage_limit_reached` becomes `UsageLimitReached`, including optional reset timestamp. `codex-rs/codex-api/src/api_bridge.rs:185-220` |
| Rendered usage limit | Messages include `You’ve hit your usage limit`, optional model/window and retry time; workspace variants mention exhausted credits or spend caps. `codex-rs/protocol/src/error.rs:705-836` |
| Retry exhaustion | Message begins `exceeded retry limit, last status:`. `codex-rs/protocol/src/error.rs:685-701` |
| Human-output stderr | Failed turns clear the final message and emit `ERROR:` plus the error. `codex-rs/exec/src/event_processor_with_human_output.rs:327-334` |
| JSON output | Failed turns emit `turn.failed` with `error.message`; unrecoverable stream errors have type `error`. `codex-rs/exec/src/exec_events.rs:22-36,54-57,90-94`; `event_processor_with_jsonl_output.rs:538-557` |
| Process status | Non-retrying terminal errors and failed/interrupted turns set `error_seen`; exit is 1. `codex-rs/exec/src/lib.rs:1340-1359,1399-1407` |
| Upstream regression coverage | A synthetic rate-limit response is asserted to exit 1 in `codex-rs/exec/tests/suite/server_error_exit.rs:7-30`. This upstream test was inspected, not executed. |

Backend implication: inspect return code **and** structured terminal events.
With `--json`, stderr alone is insufficient. Human-readable detection must handle
the curly apostrophe in `You’ve`, case/spacing variants, and exhausted-credit
messages. Keep real stderr and terminal-error text in failure diagnostics.
Retry according to the spec's bounded backoff; never treat an error message or a
missing output file as a successful completion. No account-specific reset time
or usage allowance was inferred.

Exploratory searches used obsolete paths `codex-rs/core/src/error.rs` and
`codex-rs/app-server-protocol/src/protocol/v2.rs`, which reported missing files.
The actual error definitions are at `codex-rs/protocol/src/error.rs`; v2 protocol
definitions are split across `protocol/v2/`, including `thread.rs:1995` for token
usage. These paths were located and inspected; no missing-source check was
treated as successful.

## Historical 3.3 ATLAS (superseded by WideSearch)

### Official release search

The official [ATLAS announcement](https://exa.ai/blog/atlas-benchmark), dated
2026-10-08, still says the tasks, golden tables, grader, and technical details
are forthcoming. This is Exa's search benchmark, not the unrelated OpenCompass
scientific-reasoning benchmark with the same name. The exact release statement,
fetch timestamp, HTTP status and source hash are in
[exa-release-status.txt](evidence/exa-release-status.txt):1-6.

Checks performed:

1. Exa's verified GitHub organization: <https://github.com/exa-labs>.
   Public repository API pages were saved in
   [exa-repos-page-1.json](evidence/exa-repos-page-1.json) and
   [exa-repos-page-2.json](evidence/exa-repos-page-2.json).
   `GET https://api.github.com/search/repositories?q=org%3Aexa-labs+atlas`
   returned HTTP 200, `total_count: 0`, `incomplete_results: false`, `items: []`.
   Full response: [exa-atlas-repo-search.json](evidence/exa-atlas-repo-search.json):1-9.
2. Official benchmark repository: <https://github.com/exa-labs/benchmarks>,
   inspected at commit **`0d817af66fb6c47afb7b097b9f4e40a763b6fc3a`** in
   `.verification/exa-benchmarks/`. Its complete tracked-file list contains other
   benchmarks but no ATLAS dataset, loader, or grader. Evidence:
   [exa-benchmarks-pin.txt](evidence/exa-benchmarks-pin.txt):1-6,
   [exa-benchmarks-files.txt](evidence/exa-benchmarks-files.txt):1-66,
   [exa-benchmarks-atlas-search.txt](evidence/exa-benchmarks-atlas-search.txt).
   Incidental occurrences of the word “Atlas” in unrelated dataset records do
   not constitute an Exa ATLAS release.
3. Hugging Face dataset APIs for `author=exa-labs` and `author=exa` both returned
   HTTP 200 with empty lists. Full responses:
   [hf-exa-labs-datasets.json](evidence/hf-exa-labs-datasets.json):1-5,
   [hf-exa-datasets.json](evidence/hf-exa-datasets.json):1-5.
   A broader `search=atlas&limit=1000` listing was also inspected and saved in
   [hf-atlas-datasets.json](evidence/hf-atlas-datasets.json); it did not identify
   an official Exa release. No dataset was substituted based on name alone.

These are dated observations of the checked public sources, not proof that no
private distribution exists. No official dataset download URL, release revision,
or official ATLAS grading-code URL can currently be recorded as verified.

### Published metrics and format limits

Exa's [Grading section](https://exa.ai/blog/atlas-benchmark#grading) describes
per-task F1 followed by an average over tasks. Discovery counts entity matches;
Item counts correct cells; Row counts rows with every graded cell correct.
Precision divides correct units by returned units, and recall divides them by
gold units. F1 is their harmonic mean. Row alignment uses names/aliases with an
LLM fallback. Cell checks use deterministic rules when possible and an LLM
judge otherwise. Verified blank cells require empty predictions; ungraded cells
are excluded. Evidence checks: `evidence/exa-release-status.txt:7-16`.

The exact task fields, required-column representation, as-of/reference-date
field, answer-table serialization, aliases, and blank/ungraded encodings could
not be verified. Neither could duplicate-row handling, normalization rules,
judge prompts, nor empty-denominator conventions. The published descriptions
are insufficient to recover these executable interfaces. No scores were
computed. No unofficial grader was implemented against a guessed format.

If data is supplied while the official grader remains unavailable, Section 3.3
already permits implementing the published metrics with reports labeled
`unofficial_grader`. That work must first inspect the real data and explicitly
document every matching-rule difference; it must not claim official equivalence.

## Historical ATLAS open questions (superseded)

1. **Blocking — official ATLAS distribution.** Provide a public official release
   URL and revision, or the local path to an official Exa-supplied distribution
   you are authorized to use. It must contain real tasks and golden tables.
   The associated schema/documentation must establish identifiers, required
   columns, reference dates (or explicitly their absence), entity aliases, and
   blank versus ungraded cell encoding. A hand-written task example or a
   different benchmark called ATLAS does not resolve this.
2. **Blocking for the official grader — grading release/interface.** Provide
   the official grader repository/package and revision or its documentation if
   distributed separately. If no grader has been released, the verified dataset
   and its grading metadata are still required before applying the spec's
   authorized `unofficial_grader` fallback. Any remaining unpublished matching
   choices must be listed as differences, not invented as official behavior.

No additional Codex login or API key is needed to resolve these questions.
Live functionality and model availability remain intentionally untested, as
requested; they are not being represented as completed checks.

## Historical work and test status

- Created this verification record, captured command/API evidence, pinned source
  checkouts, and the isolated Python environment.
- RLM source, Codex source and Exa benchmark source remain unmodified; see
  [source-integrity.txt](evidence/source-integrity.txt).
- No `src/atlas_rlm`, package entry point, `config.yaml`, project tests, or
  `README.md` was created. Steps 2–4 were not started because of the explicit
  dataset stop condition. This is not an end-to-end implementation or a claim
  that the definition of done is satisfied.
- **Unit test output: none.** No project tests exist yet, and `pytest` was not
  run. Running dependency tests or reporting an empty suite as passing would
  not validate this project.
- **Live test output: none.** No live test or prohibited pipeline command ran.

Commands available now, in order, to review the actual result:

```sh
cd /Users/mukeshreddypochamreddy/Desktop/loop-research
cat docs/VERIFIED.md
codex --version
codex login status
.venv/bin/python -c 'import rlm; print(rlm.__file__)'
```

There are no working `atlas-rlm` commands to run yet. Supply the missing official
distribution first; implementation and unit tests must follow before a runnable
project setup/live-command sequence can honestly be provided.

## Historical verification status (WANDR deferral later revoked)

The preceding ATLAS findings are preserved as history, not current requirements.
RLM and Codex pins and findings above remain unchanged. No live model call or
prohibited command has been executed. On 2026-10-18 the user explicitly chose:
**defer WANDR until an official key-free fetch mode exists**. If later enabled,
use **full-lineage soft F1**, labeled as different from the harness's primary
soft recall. WANDR execution, grading adapter/cache and live test are deferred;
no replacement fetcher, simulated grader, or zero-score fallback is authorized.

## 3.3 WideSearch

- Dataset: https://huggingface.co/datasets/ByteDance-Seed/WideSearch,
  revision `6531a7e5b497d44c8912407e0cb3dc95bd98cc09`.
- Code: https://github.com/ByteDance-Seed/WideSearch,
  revision `9825ba7b140b71d81b364793f86dabe4cfed6749`.
- Local source `.verification/widesearch`; local download
  `.verification/widesearch-dataset`. These are the existing pins, unchanged.
- Evidence: `evidence/widesearch-dataset-info.json`, `widesearch-code-pin.txt`,
  `widesearch-current-integrity.txt`, `widesearch-gold-manifest.json` (each actual
  CSV download's size and SHA256), and `widesearch-source.txt` (line-numbered source).

Actual raw JSONL fields are `instance_id: str`, `query: str`, `evaluation: str`,
`language: str`. `evaluation` must be decoded with `json.loads`; an initial probe
incorrectly treated it as a dict and raised AttributeError, then was corrected.
The decoded keys are `required`, `unique_columns`, `eval_pipeline`. Languages
are `en`, `zh`. There is no dedicated reference-date field. Dates embedded in
query text stay intact; the agent records today's fallback date explicitly.
The query specifies Markdown table headings and formatting requirements;
`evaluation.required` gives normalized column names. Gold is CSV at
`widesearch_gold/<instance_id>.csv`, read with pandas defaults, headers stripped,
lowercased and spaces removed, then restricted to `required`.
Sources: dataset card lines 43–79; `src/evaluation/data_loader.py:33–74,92–134`.
The HF loader reads gold, so it must never be used to load agent tasks.

Actual inspection/download output:

```text
fields/types: {'instance_id': 'str', 'query': 'str', 'evaluation': 'str', 'language': 'str'}
evaluation fields: ['unique_columns', 'required', 'eval_pipeline']
languages: ['en', 'zh']
downloaded gold files: 200
all nonempty: True
All required gold columns found.
No dedicated as-of date field.
```

`evidence/widesearch-column-rules.json` records every real task's required/key
columns and exact per-column preprocessors, metrics, and criteria. It contains
metadata only, no gold values. Do not replace these heterogeneous rules with
one invented normalization rule. The official implementation uses:

- `norm_str`: lower/strip, remove ASCII spaces and asterisks;
  `extract_number`: first signed number (optional percent), commas removed;
  `norm_date`: dateparser, prefer first day, ISO date when parseable.
- `exact_match`: case-insensitive string equality; `url_match`: equality of
  extracted URL host sets; `in_match`: response substring of target;
  `number_near`: absolute difference bounded by target magnitude times criterion;
  `date_near`: at most 31 days; two unparsable dates also match upstream.
- `llm_judge` columns use `llm_judge_column`, not the unused upstream function
  with that name. Prompts require fenced JSON; scores are binary.

Sources: `src/evaluation/metric_utils.py:30–158,189–265,340–387`.
Keys are deduplicated before normalization, semantically mapped through the
judge when configured exact/LLM, then inner/outer-joined on `unique_columns`.
Key fields of matched rows receive full credit. Row credit is the minimum of
that row's cell metric scores; item credit is their sum. Precision/recall divide
by predicted/gold row or cell counts; empty denominators yield zero. F1 is the
harmonic mean with upstream epsilon. Success requires all row/item measures to
be perfect (or the upstream full-frame equality check). Preserve these exact
choices, including their quirks. Official error CSV has unmatched origin flags,
key values, cell metric columns, and judge messages; derive diagnostics from it.
Sources: `src/evaluation/evaluation.py:100–348`.

The official entry point is `evaluate_single_query(query, response,
result_save_path, eval_model_config_name)`, with dataclasses `WideSearchQuery`,
`WideSearchResponse`, `EvaluationResult`. Responses are fenced Markdown tables;
the official parser uses pipe-delimited pandas CSV. The adapter must preserve
that parser and quoting behavior. Sources: `data_loader.py:33–39,153–198`,
`evaluation.py:36–46,76–81`. Evaluator exceptions return a zero-filled object
whose `msg` starts `evaluator error:`; the wrapper must surface an operational
failure instead of recording a score for a broken grading run.

Official judge configuration: `gpt-4.1-2025-04-14`, temperature zero,
max tokens 10240 (`src/utils/config.py:81–91`). Official `src/utils/llm.py`
uses provider API clients. Only this transport is to be replaced by Codex;
the scoring functions and judge prompts stay unchanged. Every grade/report
must say `judge: codex/<configured-root-model-or-default>`; this is a different
judge from the published benchmark. No built-in RLM/API client may be called.

Aggregations: per-task arithmetic mean across repeats then mean across tasks
is Avg@N. Pass@N is the fraction of tasks with any success. Max@N averages each
task's maximum row/item F1. The implementation also exports min_n.
Source: paper https://arxiv.org/html/2508.07999v1, Section 3.5.2; official code
`scripts/run_infer_and_eval_batching.py:175–215`. The code calls Pass@N `max_n`
for binary `score`; it is not an estimator from subsampling. No performance
results are reproduced here.

## 3.4 WANDR (verified, execution deferred by user)

Dataset https://huggingface.co/datasets/perplexity-ai/wandr is pinned to
`066ee3d71cd332cb2fb4f49146cad7f9c7249f86`. The card and release manifest require
harness https://github.com/perplexityai/wandr at
**`ccb0baeb96f1c77a48e47f92122c57479ee99700`**. The initially inspected moving
HEAD `9ea23c7f24d0aaabc2c87b26815a513001b2e7ce` was superseded by the card's
revision before drawing integration conclusions. The final checkout is detached
and unmodified. Evidence: `wandr-dataset-info.json`, `wandr-current-integrity.txt`,
`wandr-source.txt`. Card, manifest, evaluator index and test JSONL downloaded
under `.verification/wandr-dataset/` at the dataset pin. Web rendering of the
pinned card failed; the raw pinned download succeeded and was inspected locally.

Official scoring executes generated `datasets/wandr/<slug>/tests/verify.py`
(and task-local manifest, task modules, schemas, prompts and vendored core), not
the HF source bundle. The canonical template is
`adapters/wandr/src/wandr/task-template/tests/verify.py`: `_run_evaluation`
loads/validates task-owned JSONL, invokes `run_pipeline`, then
`metrics_for_tasks`, report/reward serialization (lines 102–123,150–243).
Card lines 223–247 identify the GitHub/Harbor workflow, Python 3.12, uv, Docker,
and artifacts `reward.json`, `wandr_metrics.json`, `report.html`, `error.json`.
No live harness was run; no API key was used.

Task records identify task_id, source_commit/source_url, instruction and its
hash/status/source URL, required_output_files, task_tree_json, metadata_json,
submission_contract_json, evaluator_index_path, source_bundle_path,
external_dependencies_json, self_contained and scored. JSON-suffixed fields
are serialized JSON strings. The task tree preserves parent/order, task text,
item_fields, ordered key_hierarchy entries (fields, name, required count),
output paths and fingerprints. Qualification text and nested structures are
per-task, not one fixed rubric. Some instructions/artifacts are explicitly
withheld: never invent replacements. There are no gold answer sets.
Sources: dataset card lines 140–197; pinned `src/config.py:843–978`.

Each task-tree node has its own required JSONL file. A record has `item`
(object of task-specific string fields), `url` (HTTP(S)), `excerpts` (string
array), and `answer` (free-form object). The generic schema allows additional
properties; actual item-key and hierarchy validation is task-specific. Card
186–197 and core `src/submissions.py` are authoritative. The final root subset
must be deterministic and final-only; training/reflection/gating never consume it.

All following core paths are relative to
`adapters/wandr/src/wandr/origin/wandr_core/`:

- Fetch: `src/runtime/fetch.py:187–246,360–384` requires
  `PERPLEXITY_API_KEY`, creates a background Agent API response (default
  `google/gemini-3.1-flash-lite`) which executes `pplx_sdk.content.fetch` in its
  sandbox, then downloads an artifact. This is a paid model call, not a
  key-free raw HTTP fetch. `adapters/wandr/README.md:97–122` documents it.
- `src/runtime/browser.py:14–58` uses Camoufox. However
  `src/pipeline.py:105–112,302–358,519–550` ALWAYS runs the fetch stage;
  `WANDR_BROWSER_FALLBACK` only enables the later failed/triaged-page fallback.
  `src/runtime/clients.py:70–75` always creates `FetchClient.from_env`.
  There is no supported browser-only/key-free mode in this pinned harness.
- Pipeline: validate URLs/DNS, fetch, triage, optionally browser fallback,
  canonicalize keys, deduplicate evidence, judge. Stage LLM boundary is
  `src/runtime/llm.py:16–74`, with system/prompt, Pydantic response format,
  max-completion tokens, params. `src/config.py:326–340` defaults to gpt-5.4;
  task overrides and composed task-specific prompts must be retained. All
  triage/canon/dedup/judge model calls would need Codex transport, not just the
  final verdict. No such transport was enabled because fetch is blocked.
- Excerpt faithfulness is **judged**, not a byte-equality or regex test:
  `src/prompts/judge_macro.md.jinja:64–78,119–129` accepts near-verbatim text
  with formatting quirks but rejects substantive paraphrase/fabrication.
  Model-rendered fetch text risks disagreement on re-fetch. Future reports
  must separately show false `excerpts_faithful` / judged-record count and
  report unjudged records separately (no invented verdict for failures).
- `src/metrics.py:49–72,92–216` defines full (`verdict`) and retrieval
  (`requirements_all_satisfied`) lineages. Only confidence >=2 supplies a leaf
  signal. Precision averages supplied records. Recall takes worst duplicate
  entity score, ranks and truncates/pads to required counts; soft keeps partial
  values and hard requires completion at non-root levels. F1 is derived from
  precision/recall; hierarchical composition multiplies matching parent/child
  scores before re-aggregation (`244–261,304–482`). Missing judgments remain
  distinct from confidently false judgments.
- Template `tests/rewards.py:38–41` names full soft recall as PRIMARY_REWARD.
  No F1 is named headline. User selected full-lineage soft F1 for future
  project primary metric, with this difference explicitly labeled.

Actual pin command:

```text
$ git -C .verification/wandr fetch origin ccb0baeb96f1c77a48e47f92122c57479ee99700
From https://github.com/perplexityai/wandr
 * branch ccb0baeb96f1c77a48e47f92122c57479ee99700 -> FETCH_HEAD
$ git -C .verification/wandr checkout --detach ccb0baeb96f1c77a48e47f92122c57479ee99700
HEAD is now at ccb0bae Merge pull request #6 from perplexityai/codex/add-integration-attribution
```

## Superseded open questions

- **Previously deferred WANDR:** need an official harness revision with a documented
  key-free fetch mode before WANDR execution/grading/cache/live tests can be
  implemented. User explicitly chose to defer, so no API key or permission to
  use a paid service is requested. Existing pins are retained as evidence;
  changing the harness pin later requires a fresh verification.
- All live behavior (Codex completions, search/fetch, real benchmark grading,
  improvement and final runs) is intentionally untested at user request.
  Offline checks cannot establish live model availability or scores.

## Cleanup verification (2026-10-18)

The implementation was interrupted before `loop.py`, `evaluate.py`, `report.py`,
`cli.py`, and README were built. This cleanup does not claim an end-to-end
implementation. WANDR remains deferred by the user's decision above.

The initial `python -m pytest` collected no tests. The standalone official
evaluator fixture in `tests/verify_official.py` was migrated, with its assertions
preserved, into `tests/test_widesearch.py`. Offline regression tests now cover
the implemented components; the final complete output is preserved in
[evidence/cleanup-unit-tests.txt](evidence/cleanup-unit-tests.txt). No test was
skipped or weakened, and no live model or prohibited pipeline command ran.

Removed unreferenced `docs/plans/implementation.md`, unused imports/constants,
the unused archive lock helper, pass-through contract/registry helpers, duplicate
text normalization, and broad agent error swallowing. Unexpected worker/transport
failures now surface; the spec-required one-repair and invalid-output empty
fallback remain. The new REPL test found a preexisting defect: Python passes
`fromlist=None` to the import hook for a plain import. The hook now accepts it.

Official WideSearch startup stdout is suppressed only while our adapter loads
its unchanged modules; Loguru output is disabled by those private module names.
Official scoring and provider-bridge behavior are unchanged. Fixture tests check
metrics, citation conversion and quiet imports/evaluation. Upstream RLM,
WideSearch and WANDR checkouts remain unmodified.

All project files are currently untracked against an empty repository HEAD, so
plain `git diff --stat` produces no output. A before/after source comparison for
this cleanup is preserved in [evidence/cleanup-diff-stat.txt](evidence/cleanup-diff-stat.txt).

## WANDR reactivation: authorized service adapters

The user revoked the WANDR deferral and explicitly authorized browser-primary
fetching plus Codex subscription judging. The on-disk spec still contains the
earlier stop clause; this later user instruction controls. Keep the original
dataset and harness pins. No provider keys may be used. Full-lineage soft F1
remains the project primary metric; upstream PRIMARY_REWARD is full soft recall.
Every WANDR report must label `fetch: wandr-browser` and `judge: codex/<model>`.

Verified integration boundaries (paths relative to the pinned WANDR checkout):

- `adapters/wandr/src/wandr/origin/wandr_core/src/components.py:280–288` calls
  Perplexity through `fetch_pages`; replace the pipeline's binding to that
  service function with batched calls to unchanged `browser_fetch` (335–336).
  Browser retries, URL validation, Camoufox navigation, text extraction and
  excerpt windowing remain at `components.py:299–318`. Browser output supplies
  `page_text`; the adapter supplies that same text as `content` for the unchanged
  triage stage. No page text, titles, metadata or verdicts are synthesized.
- Wire the fetch service's pool through unchanged `create_browser_pool`
  (`src/runtime/clients.py:95–119`), using one browser per concurrent fetch
  worker. Set the fetch service's batch/client-load to one and its concurrency
  to the existing browser-concurrency setting. Keep browser fallback disabled:
  browser fetching is now primary and the only retrieval service.
- `src/runtime/llm.py:23–74` is the unmodified judge-call boundary for triage,
  canon, dedup and final judgment. It builds exact system/user messages and
  invokes `client.beta.chat.completions.parse` or `client.chat.completions.create`.
  Replace the client pool binding in `src/pipeline.py:39–41` with a Codex-backed
  client; keep this function and all stage prompts/schemas/parsing unchanged.
  Schema conversion uses the installed OpenAI SDK's offline
  `type_to_response_format_param`; response parsing uses that same SDK's
  `_parse_content` (the content parser used by `parse_chat_completion`). These utilities make no API calls. SDK parameter
  signatures were inspected locally before integration.
- The service auth preflight `task-template/tests/verify.py:97–99` assumes
  an OpenAI API key. Its project adapter instead validates the actual
  `codex login status` ChatGPT result. This is auth wiring for the judge
  replacement, not a fake key or a scoring change.
- Execute the unchanged generated `tests/verify.py:282–325` entrypoint in
  a fresh subprocess for each task. This preserves validation, healing,
  schema failures, hierarchical metrics and artifact construction.
- Original judge caches in `src/pipeline.py:208–216,395–417` key task evaluator
  fingerprint, canonical entity keys, URL, answer/excerpt hashes, page text and
  aliases. Keep them; an additional atomic transport-response cache prevents
  repeating finished calls if interrupted before upstream's buffered cache
  is flushed (`runtime/modifiers.py:45,68–193`, default flush batch is 25).

Data inspection found every release root has a matching generated task package.
Some HF instructions omit embedded artifacts; the loader uses the matching
canonical package instruction in those cases. It never substitutes synthetic
text. The dataset's benchmark-construction metadata is not sent to the agent.

Browser installation output (trailing whitespace normalized) is recorded in `evidence/wandr-browser-install.txt`.
Only installation and offline import/browser readiness checks are permitted
during this build; no page fetch, judge call, or benchmark run is authorized.


## Implementation completion (2026-10-18)

The initial state was committed first as `52dcc36` (`Save verified sources,
research components, and offline tests`). The earlier ATLAS and WANDR-deferral
findings remain as historical evidence; WANDR is now implemented under the
user's explicit browser-primary/Codex authorization. No upstream source was edited.

### Exact WANDR adaptation

Project paths below are relative to this repository. Upstream paths are relative
to `data/vendor/wandr` at `ccb0baeb96f1c77a48e47f92122c57479ee99700`.
The generated package used to inspect the integration is
`datasets/wandr/abm-provider-commercial-provenance/tests`; each release task
runs its own corresponding generated package in a fresh Python process.

| Service binding | Original function | Project replacement |
| --- | --- | --- |
| Fetch operation | `adapters/wandr/src/wandr/origin/wandr_core/src/components.py:284` (`fetch_pages`), imported by `src/pipeline.py:27` | `src/loop_research/benchmarks/wandr/grader.py:76` (`browser_pages`), bound at line 90; calls the original `components.browser_fetch` at upstream line 335 |
| Fetch pool | Upstream `src/runtime/clients.py:70` (`create_fetch_pool`), imported by `src/pipeline.py:40` | Original `create_browser_pool` at upstream `src/runtime/clients.py:95`, bound by project `grader.py:91`; batch/client load 1, existing browser concurrency, no fallback fetch |
| Judge pool | Upstream `src/runtime/clients.py:78` (`create_openai_pool`), imported by `src/pipeline.py:41` | Project `grader.py:87` (`judge_pool`), bound at line 95; returns `CodexTransport` (lines 24–68) |
| Judge auth preflight | `adapters/wandr/src/wandr/task-template/tests/verify.py:97` (`_validate_runtime_env`) | Project `grader.py:18` (`subscription_auth`), bound at line 96; checks real ChatGPT login, supplies no fake key |

These are two service substitutions and their pool/auth wiring. The unmodified
upstream `src/runtime/llm.py:23` still builds the original role messages and
parses through the same response interface. The adapter uses the exact offline
OpenAI SDK strict-schema converter and content parser from **openai 3.35.1**.
Installed paths, source line numbers and function bodies are captured in
[evidence/wandr-adapter-verification.txt](evidence/wandr-adapter-verification.txt).
The model request's system/user strings are preserved verbatim as a JSON role
transcript. The required Codex component instruction is prepended by the shared
backend. All grading stages use `models.root` (or Codex default), with configured
`models.reasoning_effort`. Original model/token-limit/provider parameters are
retained in the transport cache; unverified provider controls are not translated
to invented CLI flags. Judge substitution therefore does not claim identical
model behavior to the upstream provider.

Per-browser serialization prevents the upstream enqueue-time round robin
(`src/runtime/node.py:109–121`) from navigating a single page concurrently.
Cancelled upstream waits leave a shared in-flight Codex call running; its parsed
response is persisted inside the worker thread, so healing can reuse it.
Upstream triage/canon/dedup/judge timeouts, retry/healing policy, prompt templates,
validation, hierarchy and metric computations remain unchanged. Atomic project
response caching complements the untouched original task/record/URL caches.

Project `grader.py:117–144` invokes the original generated verifier `main`, reads
its actual artifacts, preserves all twelve official metrics and the official
`grade`/`reward` soft-recall aliases, and labels human-readable reports. Project
primary: `soft_f1_full`; harness primary: `soft_recall_full`. Provenance is
`fetch: wandr-browser`, `judge: codex/<model>`. Excerpt failures count actual false
`excerpts_faithful` judgments divided by actual boolean judgments; no judgments
means `null`, not a fabricated zero. Original full verdicts and unjudged counts
are retained. Invalid submissions use only the original harness's zero rewards.

`src/loop_research/benchmarks/wandr/data.py:46–61` loads all 500 scored roots.
Four missing HF instruction bodies use their exact canonical generated
`instruction.md`. All required filenames and subtask structures come from the
pinned release. Agent `answer` objects remain free-form; repair includes the
contract in its prompt and validates locally because Codex strict output schemas
cannot represent an open object. Reflection uses a closed schema with every
nullable edit property required and feedback keys limited to rendered skill IDs.

### Installation and offline checks

The public pinned sources already inspected under `.verification/` were copied
into the Section 4 `data/vendor/` and `data/downloads/` locations. `prepare-data`
then checked their pins/content and wrote all deterministic selection files.
WideSearch checks every release file against the pinned Git blob hashes in its
packaged `manifest.json`; the original metadata response is retained in
[evidence/widesearch-pinned-tree.json](evidence/widesearch-pinned-tree.json).

Commands executed without model calls:

```text
uv pip install --python .venv/bin/python -e '.[test]'
python -m camoufox fetch
python -m camoufox path
python -m camoufox active
PYTHONPATH=src .venv/bin/python -m loop_research.cli init
PYTHONPATH=src .venv/bin/python -m loop_research.cli prepare-data
PYTHONPATH=src .venv/bin/python -m loop_research.cli verify
uv pip install --python .venv/bin/python --reinstall-package loop-research '.[test]'
.venv/bin/loop-research verify
.venv/bin/python -m pytest
uvx ruff check src tests --select F --output-format concise
```

Camoufox installed successfully; the official `BrowserClient` launched and
navigated only to `about:blank`. The complete successful verification table is
[evidence/final-verify.txt](evidence/final-verify.txt). It confirms Codex 0.163.0,
ChatGPT login, required flags, installed RLM SHA/source hashes, both dataset/code
pins and browser readiness. No model capability or benchmark score is inferred
from these checks.

This environment assigned macOS `UF_HIDDEN` to the editable installation's `.pth`
file; Python 3.12 `site.py:176–182` skips hidden `.pth` files. Tests and worker
subprocesses explicitly use the project source path; the delivered CLI is installed
as a normal wheel, and README recommends a normal installation. This is an
installation issue, not a reason to skip a check. The installed wheel matches
all tested package source/manifest files; see
[evidence/final-installation.txt](evidence/final-installation.txt).

The offline suite includes actual pinned WideSearch scoring on hand-written
fixtures, the unchanged WANDR pipeline through all four judging stages on
hand-written fixtures, real upstream invalid-submission handling, cache hits and
misses, cancellation/concurrency, import boundaries, CLI guards, resumable gate
commits, reflection schemas, citation/repair paths, and paired final evaluation.
All external responses in these tests are declared test fixtures. Exactly three
`live` tests are opt-in and are not part of the executed suite.

Final result: **141 passed, 3 live tests deselected in 12.60 seconds**. Static unused-import/name checks and `git diff --check` also passed.

Full final unit output is retained in
[evidence/final-unit-tests.txt](evidence/final-unit-tests.txt). No tests or checks
were skipped or weakened to obtain a pass. The three live tests are deselected
by the requested default test configuration.

## Historical open questions (before the continual-harness redesign)

None block implementation or the verified local setup. Live Codex/web behavior,
real research/grades, improvement cycles and final evaluations remain unexecuted
at the user's explicit request. The user must run those commands to validate live
availability and outcomes; no live success or benchmark performance is claimed.

## PR preparation

Whitespace-only cleanup removed trailing spaces/tabs and extra end-of-file blank
lines from recorded evidence. Commands, findings, source line numbers, and
non-whitespace content are preserved. The full offline suite passed again before
publication; live tests remained deselected.

## Continual harness: pinned reference verification (2026-10-18)

This section records source inspection and the requested adaptation. It does not
claim that a new harness, stream, refiner, or comparison run has been implemented
or executed. No live model calls, research tasks, benchmark grading, or task
streams were run during this verification. Only the requested public reference
material was fetched. The earlier test results above belong to the previous
implementation and are not evidence that the new design passes.

### Reference identity and evidence

The official [Prime Agent repository](https://github.com/PrimeIntellect-ai/prime-agent)
was inspected in the clean, read-only checkout `.verification/prime-agent` at
**`7cbffa77b38facd7c87277fa3c82bcadbe816880`**. This is the Rust implementation,
including its Python kernel library, rather than the historical TypeScript
implementation. The commit date is 2026-10-16. The repository's `AGENTS.md` and
MIT license were read; its source was not edited and its Rust tests were not run.

Commands executed and their complete results are in
[prime-pin.txt](evidence/prime-pin.txt):

```text
$ git -C .verification/prime-agent remote get-url origin
https://github.com/PrimeIntellect-ai/prime-agent
$ git -C .verification/prime-agent rev-parse HEAD
7cbffa77b38facd7c87277fa3c82bcadbe816880
$ git -C .verification/prime-agent status --porcelain
<empty; exit 0>
```

[prime-source-evidence.txt](evidence/prime-source-evidence.txt) contains file
SHA-256 hashes, inspected line ranges, immutable source links, and the scheduling
field search. The state, CRUD, planner, executor, ranking, session refinement,
automatic trigger, master switch, and digest modules were read, including the
relevant boundary consumers and refinement skill. Source links below are
permalinks to the pinned commit; paths and ranges refer to that checkout.

The paper is [Continual Harness: Online Adaptation for Self-Improving Foundation
Agents, arXiv:2605.09998v1](https://arxiv.org/html/2605.09998v1), dated 11 May 2026.
Its retrieval URL, HTTP status, byte count, SHA-256, and inspected sections are
recorded in [prime-paper.txt](evidence/prime-paper.txt).

### Paper model and limits of attribution

The paper defines four components: prompt, subagents, skills, and memory. A
refiner uses recent trajectory windows after warm-up, edits those components,
and lets the agent continue without resetting the environment. It shares the
agent's model; executable skills can be repaired from observed failures.
The separate co-learning experiment additionally updates model weights using
process rewards and teacher relabeling; that is not this project's design.
[Sections 2.2–3.3](https://arxiv.org/html/2605.09998v1#S2.SS2).

The experiments include frozen and continuing bootstrap conditions. Appendix C
reports unused authored entries and regressions when inherited subagents are
abandoned. These results motivate tracking actual use and observed outcomes;
they do not prove this project's research performance. The requested task-level
cadence and deterministic self-check signal are project choices, not the
paper's evaluation protocol. [Section 4.1](https://arxiv.org/html/2605.09998v1#S4.SS1),
[Appendix C](https://arxiv.org/html/2605.09998v1#A3).

### Persistent harness state

The current source has **five** kinds: `prompt`, `memory`, `skill`, `subagent`,
and `factory`. The requested project has exactly the first four; omitting
`factory` is an intentional override, not a claim about the current upstream
schema. The factory kind describes state-machine workflows and has its own
opt-in policy. [Kinds and schema, `refinement/mod.rs:9–108`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/crates/pa-core/src/refinement/mod.rs#L9-L108).

`HarnessEntry` contains `id`, `kind`, `title`, `content`, `path`, `scope`,
`reference`, `arguments`, `metadata`, `source`, `created_at`, `updated_at`, and
`version`. Python defaults include local scope, `path="general"`,
`source="agent"`, and version 1. The persisted document is
`{schema: 1, entries: {kind: {id: entry}}, refinements: [...]}`. A successful
update increments the entry version and preserves its creation time.
[Python types, `harness.py:194–222`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/prime-agent-runtime/src/rlm/harness.py#L194-L222),
[serialization and updates, `harness.py:627–798`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/prime-agent-runtime/src/rlm/harness.py#L627-L798).

The default local store is the session's `harness/harness_state.json`; global
state is under the agent directory's `harness/`. Python resolves explicit state
directories, `RLM_HARNESS_STATE_DIR`, `RLM_SESSION_DIR`, and
`RLM_GLOBAL_HARNESS_STATE_DIR`. A missing local session path raises rather than
silently targeting the global store. Host prompt construction merges both
scopes, preserving conflicting global and local IDs with a display prefix for
the latter. It does not overwrite the global entry with the local entry.
[Path resolution, `harness.py:127–191`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/prime-agent-runtime/src/rlm/harness.py#L127-L191),
[host merge, `refinement/mod.rs:230–270`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/crates/pa-core/src/refinement/mod.rs#L230-L270).

Both writers lock, reload, and atomically replace the JSON store. The Python
cache checks file modification time to notice host writes. Corrupt/unreadable
state loads as empty upstream; this behavior is a reference fact, not a required
project recovery policy. Upstream persists JSON state and before/after edit
snapshots; these modules do **not** implement one Git commit per edit.
[Python synchronization, `harness.py:442–676`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/prime-agent-runtime/src/rlm/harness.py#L442-L676),
[host persistence, `refinement/mod.rs:279–326`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/crates/pa-core/src/refinement/mod.rs#L279-L326).

### Agent CRUD and retrieval API

`rlm.harness.*` is synchronous. `rlm.get_harness_state(state_dir=None,
global_=False)` returns the selected cached store. The generic methods are
`create`, `get`, `update`, `delete`, `list`, and `upsert`; helpers exist for each
kind. Create fails on duplicate IDs; update fails on missing IDs; delete returns
a boolean. Omitting optional update fields preserves existing values, while an
explicit `{}` replaces the corresponding mapping. These checks occur inside
the locked mutation. [Generic methods, `harness.py:678–930`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/prime-agent-runtime/src/rlm/harness.py#L678-L930).

| Surface | Verified contract | Pinned source |
| --- | --- | --- |
| Memories | `create_memory(title, content, *, id=None, path="general", metadata=None, global_=False)`, corresponding update/delete | [`harness.py:932–959`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/prime-agent-runtime/src/rlm/harness.py#L932-L959) |
| Prompt notes | Create/update/delete supplemental prompt records; default grouping path `policy` | [`harness.py:961–988`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/prime-agent-runtime/src/rlm/harness.py#L961-L988) |
| Skills | Create requires a Python reference with `type="python"`, `import`/`python_import`, and `callable`/`call_pattern`; update can preserve the existing reference | [`harness.py:229–246`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/prime-agent-runtime/src/rlm/harness.py#L229-L246), [`990–1049`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/prime-agent-runtime/src/rlm/harness.py#L990-L1049) |
| Subagents | Create/update/delete reusable textual delegation specifications; execution is a separate runtime operation | [`harness.py:1051–1078`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/prime-agent-runtime/src/rlm/harness.py#L1051-L1078) |
| Refinement records | `record_refinement(trigger, changes, *, evidence="", outcome="", id=None, global_=False)` appends caller-supplied strings; `plan_refinement(...)` returns suggested steps only | [`harness.py:1159–1207`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/prime-agent-runtime/src/rlm/harness.py#L1159-L1207) |
| Inspection | `overview(max_entries_per_kind=20)`, `search(query, kind=None, limit=10)`, and `snapshot()` | [`harness.py:1209–1343`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/prime-agent-runtime/src/rlm/harness.py#L1209-L1343) |

The project may store optional inline Python modules with skill records. That is
an explicit extension: the inspected upstream skill entry describes an installed
Python import and callable; its CRUD layer does not compile inline module source.
Upstream refiner validation additionally requires a skill `arguments` object,
whereas the Python CRUD signature permits omitted arguments. Prompt refinement
is supplemental; the refiner rejects `base_system_prompt` edits.
[Planner policy and validation, `planner.rs:10–54,194–284`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/crates/pa-core/src/refinement/planner.rs#L10-L284).

Upstream search is **weighted TF-IDF-style substring overlap**, not BM25. It
deduplicates query terms; scores title, content, and combined path/ID field
coverage; multiplies by `log(1 + N / df)`; and breaks explicit-search ties by
recency. It lacks BM25 term-frequency saturation and document-length
normalization. Host digest ranking uses related weighted overlap within each
kind, with a deterministic path/title/ID tie-break.
[Python search, `harness.py:1264–1329`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/prime-agent-runtime/src/rlm/harness.py#L1264-L1329),
[host ranking, `ranking.rs:104–175,235–262`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/crates/pa-core/src/refinement/ranking.rs#L104-L262).

The default host digest includes three entries per kind, 140-character content
snippets, and ten recent refinements. It is a separate model-facing
`[harness-digest]` context message delivered at session start/resume/compaction
boundaries. Query weights come from the active goal and four recent messages;
the state fingerprint excludes the query terms so a delivered digest is stable.
[Defaults, `refinement/mod.rs:16–19`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/crates/pa-core/src/refinement/mod.rs#L16-L19),
[delivery and query inputs, `harness_digest.rs:1–190`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/crates/pa-core/src/session_engine/harness_digest.rs#L1-L190),
[freshness check, `harness_digest.rs:440–565`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/crates/pa-core/src/session_engine/harness_digest.rs#L440-L565).

### `/refine`: scheduling, planning, and boundary application

The user command accepts `/refine [--global] [instructions]` and
`/refine rollback <refinement-id>`. The Python skill's
`await refine.run(instructions=None, global_=False)` sends a host request and
returns a scheduling result immediately. Repeated requests in one turn merge
into one pending request. The host consumes it after the current turn settles,
after any requested compaction. Direct synchronous CRUD remains a separate
immediate-write surface; it is not deferred through this scheduler.
[Command parser, `slash_commands.rs:37–84`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/crates/pa-core/src/session_engine/slash_commands.rs#L37-L84),
[skill bridge, `skills/refine/src/refine/__init__.py:15–50`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/skills/refine/src/refine/__init__.py#L15-L50),
[scheduling, `turn_boundary.rs:298–378`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/crates/pa-core/src/session_engine/turn_boundary.rs#L298-L378),
[consumption, `turn_boundary.rs:416–464`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/crates/pa-core/src/session_engine/turn_boundary.rs#L416-L464).

The current Rust implementation explicitly says the TypeScript background
planning path was not ported: kernel `refine.status()` reports the pending flag
and `in_flight=false`, because its cell cannot observe the synchronous
between-turn refinement. The skill prose still says the system prompt is
rebuilt, but the actual Rust consumer appends this run's outcome and notice rows
to live context and explicitly avoids a full rebuild. The implementation is the
authority for this pin. [Status, `turn_boundary.rs:312–316`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/crates/pa-core/src/session_engine/turn_boundary.rs#L312-L316),
[context application, `compaction_arms.rs:420–473`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/crates/pa-core/src/session_engine/compaction_arms.rs#L420-L473).

The planner receives an overview of current entries (at most 40 per kind with
240-character content snippets), the last 20 refinement results, a recent
conversation tail (initially capped at 80,000 characters), scope policy, and
optional instructions. It requests JSON containing `summary`, `rationale`,
`expectedOutcome`, and CRUD `edits`; an empty edit list is valid. It trims the
conversation further to fit the model's context and caps output at 32,000 tokens.
Planning itself does not mutate state.
[Planner inputs, `executor.rs:38–127,194–286`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/crates/pa-core/src/refinement/executor.rs#L38-L286),
[request fitting, `planner.rs:567–630`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/crates/pa-core/src/refinement/planner.rs#L567-L630).

The session captures the target store before planning, then locks and rereads it
before applying. Edits whose entry changed since that baseline are rejected
individually. Valid edits apply sequentially, so a proposal can partly succeed;
there is no all-or-nothing success assumption. Applied rows carry before/after
snapshots, `applied`, optional `error`, and the edit reason. The new state is
saved atomically, global results additionally append to
`refinement_history.jsonl`, and session audit/outcome/notice rows are recorded.
A storage failure can occur after durable edits; the source does not pretend
state and every log form one atomic transaction.
[Session flow, `refine.rs:334–467`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/crates/pa-core/src/session_engine/refine.rs#L334-L467),
[apply checks, `planner.rs:310–500`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/crates/pa-core/src/refinement/planner.rs#L310-L500).

The reference has policies the user expressly does not want copied. Its master
`harnessRefinements` switch controls scheduling, planning, apply, reads/writes,
and model-context delivery. Automatic compaction-triggered refinement has a
separate model review that returns `shouldRefine`, plus enabled/compact flags
and a 20-minute cooldown. `AutoRefineGates` stores a default `turn_interval=25`,
but repository-wide Rust search finds that field only in configuration/defaults
and tests, not an interval scheduler; this pin is not verified to run every 25
turns. An approved review is retained if the agent is streaming and runs at a
later boundary; branch changes discard stale reviews.
[Review call, `executor.rs:347–419`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/crates/pa-core/src/refinement/executor.rs#L347-L419),
[defaults, `refine.rs:29–64`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/crates/pa-core/src/session_engine/refine.rs#L29-L64),
[automatic trigger, `auto_refine_trigger.rs:13–261`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/crates/pa-core/src/session_engine/auto_refine_trigger.rs#L13-L261),
[master switch, `refinement_gate.rs:1–80`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/crates/pa-core/src/session_engine/refinement_gate.rs#L1-L80).

### Outcome records and rollback

The reference has three distinct uses of outcome language:

1. Python `RefinementEvent.outcome` is a free string supplied to
   `record_refinement`; it is not computed by a checker.
2. The model's `expectedOutcome` becomes `RefinementResult.expected_outcome`.
   Critically, the host copies that same prediction directly into
   `HarnessRefinementEvent.outcome` when applying the proposal.
3. `refinement_outcome` is a UI/session message with the refinement ID, summary,
   scope, applied-edit rows, and optional rollback ID. It reports edit application,
   not benchmark quality.

These are auditable application records and expectations, **not actual benchmark
evaluation or measured success**. The only verified success flags here mean an
edit applied. [Record types, `refinement/mod.rs:73–93,334–387`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/crates/pa-core/src/refinement/mod.rs#L73-L387),
[prediction copied into outcome, `planner.rs:471–500`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/crates/pa-core/src/refinement/planner.rs#L471-L500),
[outcome/notice messages, `refine.rs:112–160`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/crates/pa-core/src/session_engine/refine.rs#L112-L160).

Rollback finds a prior result in merged history, infers its scope, and builds
inverse edits from successful rows in reverse order: undo a create by deleting;
undo a delete by recreating the before snapshot; undo an update by restoring its
before content and metadata through an update. It runs through normal apply and
records `rollbackOf`. It is snapshot-based compensation, not Git history reset,
and failed edits are not inverted. The concurrency check compares against the
state just before rollback planning; it does not guarantee that later intervening
edits will be preserved when explicitly rolling back an older refinement.
[Rollback planning, `executor.rs:205–229`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/crates/pa-core/src/refinement/executor.rs#L205-L229),
[inverse edits, `planner.rs:503–546`](https://github.com/PrimeIntellect-ai/prime-agent/blob/7cbffa77b38facd7c87277fa3c82bcadbe816880/crates/pa-core/src/refinement/planner.rs#L503-L546).

### Explicit project overrides, not upstream claims

| Requested project behavior | Difference from the verified reference |
| --- | --- |
| Exactly four entry kinds: prompt, memory, skill, subagent | Current Prime Agent additionally has `factory`. |
| A Git repository with one commit per persistent edit | Reference storage is atomic JSON plus refinement history and snapshots. |
| BM25 retrieval over the harness entries | Reference uses weighted TF-IDF-style field overlap. |
| Automatic refinement after every task, with agent-triggered requests also available | Reference exposes user/agent requests and a gated compaction-triggered review path. |
| Background planning with application at a model-turn boundary | The inspected Rust reference plans synchronously between settled turns; its source explicitly says the prior background path was not ported. |
| No approval gates, benchmark promotion gates, cooldowns, or operational off switches; a frozen comparison mode is the explicit exception | Reference has live master/automatic switches, a review decision, and cooldowns. Serialization and shape validation are correctness checks, not quality-promotion gates. |
| Optional inline Python skill modules | Reference entries point to installed Python imports/call patterns. |
| Observed task outcomes derived **only from deterministic `selfcheck`** | Reference `outcome` is caller text or the model's expected outcome. Grades, answer keys, benchmark metrics, and judge feedback must never feed refinement or its outcome records. |

The permitted future comparison is separate from adaptation. It may assess
frozen baseline/evolved harness snapshots with benchmark graders, but those
scores cannot become a promotion gate or a refiner input. Source inspection
does not validate any future measured improvement.

### Stock pinned RLM and full-builtins adaptation

The research runtime remains the separately pinned
[`alexzhang13/rlm` at `d04208afbad29ca675ab13478c40ee8bebc84bfe`](https://github.com/alexzhang13/rlm/tree/d04208afbad29ca675ab13478c40ee8bebc84bfe),
not Prime Agent's Python package with the same `rlm` import name. Offline import
inspection confirmed that installed `LocalREPL` source exactly matches that pin:
both SHA-256 hashes are
`cee6bcfc530b01cef4b39f722b2efc084dd2fa08fe495b88ceda7efa63b5e31e`.
The installed distribution's `direct_url.json` records the pinned Git commit.
Commands and output are in [prime-rlm-builtins.txt](evidence/prime-rlm-builtins.txt).

Stock `LocalREPL.setup()` installs a copy of `_SAFE_BUILTINS` in
`self.globals["__builtins__"]`. That map sets `input`, `eval`, `exec`, `compile`,
`globals`, and `locals` to `None`; it already includes `open` and `__import__`.
Therefore stock behavior must not be described as full Python builtins.
[Builtin map, `local_repl.py:50–144`](https://github.com/alexzhang13/rlm/blob/d04208afbad29ca675ab13478c40ee8bebc84bfe/rlm/environments/local_repl.py#L50-L144),
[instance namespace, `local_repl.py:208–242`](https://github.com/alexzhang13/rlm/blob/d04208afbad29ca675ab13478c40ee8bebc84bfe/rlm/environments/local_repl.py#L208-L242).

The implemented project adaptation constructs the stock `LocalREPL` and then
sets its instance namespace to the full builtin mapping,
`repl.globals["__builtins__"] = dict(vars(builtins))`, before model-authored cells
execute. It does not edit installed/upstream RLM source or introduce a
replacement REPL implementation. The source identity evidence above and the
isolated worker tests below verify different parts of this integration.

## Open questions after reference verification

No unresolved reference question blocks the requested adaptation. The differences
above are explicit project choices. Remaining limits are recorded rather than
silently filled in:

- The inspected Rust pin differs from inherited TypeScript-oriented skill prose
  about background planning and prompt rebuilds. The current Rust behavior is
  cited above; no uninspected historical implementation is assumed.
- The stored `turn_interval` setting has no identified Rust scheduling consumer.
  This does not affect the requested every-task cadence, which is a project
  requirement.
- The reference does not provide the requested deterministic outcome evaluator,
  BM25 implementation, per-edit Git history, or inline-module loader. Their
  project implementations are verified separately below.
- Local source inspection does not establish live Codex availability, research
  quality, performance gains, or real stream/comparison results. Those remain
  unexecuted under the user's instruction; no simulated result is presented as
  a live measurement.

## Historical continual harness implementation verification (2026-10-18)

This section describes the built code, separately from the reference findings.
It supersedes historical completion records about the removed loop. No open
design question blocks use; live availability and research quality remain
unmeasured at the user's explicit instruction.

| Requirement | Implementation and offline evidence |
| --- | --- |
| Four entry kinds and shared generic CRUD | `src/loop_research/harness.py:30,88,123`; `session.py:103`; four-kind round trips in `tests/test_harness.py`. |
| Relevant retrieval without embedding or character cap | BM25 with stable ties and CJK bigrams, `harness.py:19,105`; relevant and long-entry tests. |
| Git edit records, trigger, evidence, usage and outcomes | `harness.py:123,216,231`; one commit per edit, separate bookkeeping commits, actual self-check outcomes attached to originating edit commits through Git notes. No grade fields enter this path. |
| Compensating rollback | `harness.py:177`; restores content/module and deleted-entry history, keeps unrelated edits and lineage exposure; tested against module addition and deletion. |
| Background planning and boundary apply | `refine.py:60,83,92`; `session.py:38,134`; stale target plans replan, branch changes discard plans, invalid model JSON is audited without suppressing the next automatic refinement. Final-cell rollback is drained at task end. |
| Immutable checker and evidence | `selfcheck.py:7,27`; checks every output row against the full question plus each structured spec item. `repl_tools.py:116,153,167` owns fetch/quote/constraint/discovery records. Tests catch fabricated quotes, unfetched URLs, missing constraints and operational failures. |
| Full Python and skill modules | Stock `LocalREPL` instance in `rlm_codex_client.py:81`; modules load as `skill_<id>` and in `loaded_skills`. `tests/test_worker.py` executes classes, eval/exec/compile, threads, asyncio, child processes, parallel tools, subcalls and a selected skill module in real isolated workers. |
| OS isolation verified on this machine | macOS Seatbelt, `isolation.py:38,86`. Real tests deny gold/grade/archive reads, symlink escapes, trusted-source writes, external connections, foreign Unix sockets and parent signaling; descendants retain restrictions. [Isolation output](evidence/isolation-tests.txt). |
| Concurrent tools without backend lock contention | `repl_tools.py:40,111,148`; ordered results, shared cache/ledger and duplicate in-flight suppression. Lock-ownership tests and real isolated batched tool calls pass. |
| Bounded worker shutdown | `session.py:34,66`; task-owned cancellation terminates dispatched Codex processes and prevents late tool/harness/trajectory writes. The bridge closes partial sockets. Delayed-dispatch and hard-deadline regressions cover these paths. Host refinement/format repair have separate contexts. |
| Grade separation and ordering | `stream.py:37`; `archive.py:158` (`GradeContext`); WANDR child also uses `GradeContext` at `benchmarks/wandr/grader.py:119`. Research precedes independent grading, then final self-check/refinement. Grader errors and judge logs stay under reports. Secret-marker tests inspect refiner input and harness state. |
| Learn once per lineage | `harness.py:205`; `stream.py:90,102`. Exposure is committed before research. Replay forks before exposure; matching streams use a common initial commit; no-learning restores the live branch. Tests cover repeat tasks, rollback, baseline restoration and identical task order. |
| Single config source and judge model | All values in root `config.yaml`; strict, required fields in `config.py`. WANDR uses `final_n_tasks: null`; legacy subset/split/gate artifacts and code removed. WideSearch judge uses `models.judge` at `benchmarks/widesearch/grader.py:40`; WANDR at `benchmarks/wandr/grader.py:51`; result labels include that selection. |
| Reports | `report.py:88,148`; ordered scores and rolling available-score mean, explicit null failures, compatible paired learning/no-learning comparisons. Report tests use clearly synthetic fixtures only. |

`fetch()` is a Codex-rendered excerpt, not a raw HTTP capture. A completed
`open_page` event confirms the exact URL was opened; the deterministic checker
then verifies verbatim membership in the cached rendering. It does not prove
that the model faithfully copied the remote page. Likewise, per-row constraint
coverage verifies a supported recorded verdict for the whole question and
each structured spec item; it does not mechanically prove the semantic verdict
or split arbitrary natural language into independently verified predicates.
Discovery stagnation is based on recorded entity identifiers. These are explicit
measurement limits, not hidden claims of truth or exhaustive search.

An editable-install check found that its macOS `.pth` file inherited
`UF_HIDDEN`, which Python 3.12's `site.py:176–179` explicitly ignores. Clearing
that flag on `.venv/lib/python3.12/site-packages/_editable_impl_loop_research.pth`
temporarily restored the source import, but the flag recurred. The final install
therefore uses the freshly built wheel without an editable path file; repeated
plain imports and installed command help checks pass. Setup uses a regular
install for this reason. The wheel was independently extracted into a temporary
directory: all modules imported from it, `init`
copied its packaged root YAML byte-for-byte, and created the separate harness
repository. These probes made no model calls.

All 270 offline tests passed in 27.59 seconds. Full suite output is preserved in
[continual-unit-tests.txt](evidence/continual-unit-tests.txt). The only deselected
test has the explicit `live` marker; it was not run. Deleted legacy tests covered
the removed features; archive/transport/source-integrity coverage was retained
and the new architecture has dedicated regression tests.


## Current reliability changes and testing incident (2026-10-18)

This section supersedes historical statements above about implicit models,
null failure scores, discarded refinement errors, implicit baseline selection,
and the absence of live calls across the entire implementation session.
The README and PIPELINE_SPEC describe the current contract. Older test totals
and source line numbers are historical evidence, not results for this revision.

### Testing incident and guard

An unmocked new regression accidentally dispatched live refinement calls through
the normal Codex subscription backend during this reliability work. This violated
the instruction to keep implementation testing offline. The calls are not
benchmark research or measured benchmark results, and no quality claim follows
from them. The explicitly marked live test was not selected.

`tests/conftest.py` now installs an autouse guard for tests without a `live`
marker. It intercepts `subprocess.Popen` in the pytest process and rejects a
direct command whose executable basename is `codex` and whose arguments contain
`exec`. Tests must inject their external model transports. The guard is a
process-local monkeypatch: it does not by itself propagate into separately
launched Python interpreters or recognize renamed executables. It is not proof
that every possible child-process path is offline. Do not report this session
as having made no live calls.

### Current behavior and evidence

| Area | Current contract and regression coverage |
| --- | --- |
| Explicit settings | `config.yaml` requires four named models, date policy, retry delay cap, refinement edit limit, bridge timeout, and verification timeouts. Null/blank model selections are rejected. Config and CLI tests cover required values. |
| Research schema and date | Research requires columns, key columns and language. Keys must name selected columns. `agent.as_of` is `today` or an ISO date; a structured task date takes precedence, and the resolved date/source is archived for reuse. Exhausted format repair raises a visible error. |
| Official failure scores | Failed research or grading uses each adapter's canonical empty submission with the unchanged official scorer. WideSearch receives `response=None`; WANDR receives every required JSONL file with zero records. WANDR itself classifies these files as invalid submissions and emits its official rewards before authentication/browser/model stages. No project-generated score substitutes for a grader result. |
| Empty-grade evidence | `tests/test_widesearch.py` runs the pinned absent-response evaluator with a judge that raises if called, verifies all official metrics, and checks that stale alignment artifacts are removed. `tests/test_wandr.py` runs the pinned verifier with a nonexistent Codex binary, checks native rewards against the reward artifact and verifies empty required files and no judge-cache calls. |
| Error breakdown | WideSearch missing, null or NaN metric values are failed checks. Matched key columns use the official alignment's `exact_match` fields, even when the configured key matching pipeline has another name. |
| Fetch and search audit | Every fetch has a durable attempt outcome, including shared/cache requests, invalid arguments, backend failure and cancellation. Failed fetches can be retried. Malformed, invalid-URL and excess search hits are retained with drop reasons. Evidence tests cover concurrent and failed paths. |
| Refinement recovery | Proposal, snapshot, request and operation identities persist before application. Discards and skipped deletes have reasons. A committed edit can be recognized after a checkpoint failure. Planning, apply, rollback and finalization errors stop stream progress; resumed work continues the unfinished phase. |
| Explicit lineage and resume | New no-learning runs require `--base SHA`. Learning can use an explicit safe base or a safe ancestor of the active harness. No newest-report heuristic selects a baseline. `--resume RUN_ID` retains the original configuration, order, mode, base and lineage and reuses completed phases. A worker interrupted before its result checkpoint is graded as a failed empty attempt. |
| Reports | Every completed row must contain a finite official score. Missing/nonfinite rows are rejected instead of excluded. Rolling means and paired comparisons include scored failures. Interrupted streams display count, phase, active task, pending count and error. Synthetic report fixtures prove failed scores contribute to both aggregates. CSV, summary and curve labels identify all four model roles; archived judge labels must match the configured judge. |

Final verification for this revision: `.venv/bin/pytest` completed with **411
passed, 1 deselected in 35.32 seconds**. The deselected test is explicitly marked
`live`; it was not selected. Complete output is preserved in
[explicit-failures-unit-tests.txt](evidence/explicit-failures-unit-tests.txt).
This final run used the offline transport fixtures and guard described above;
it does not erase the earlier accidental live refinement calls.

Recovery tests exercise failures before and after a harness commit, after the
atomic official-grade checkpoint, before the stream manifest append, and during
learning/no-learning finalization. A transaction journal restores only unfinished
harness writes from committed Git state. Persisted edit identities prevent
reapplication after a successful commit. Completed research archives preserve
self-check status. Interrupted runs with actual edits retain the same semantic
harness contents and ordered scores as uninterrupted fixture runs.

Backend fetch retries now retain each dispatched attempt's call id, model,
status and error in the owning fetch evidence record. Transient failures remain
self-check issues after eventual success; shared/cache callers reference the
owner without duplicating backend attempts. Tests verify Codex runs without the
tool lock held. Report comparisons require matching task content digests and
resolved dates, as well as matching order, base, judge and execution settings.
Independent review identified these recovery and provenance gaps; regression
coverage now verifies their fixes. `git diff --check` is clean.

## Research tracing (2026-10-18)

The full offline suite passed with **446 passed, 1 deselected in 46.26 seconds**
using `.venv/bin/python -m pytest -q`. The live-marked test was not selected.
Trace regressions compare real isolated workers with injected transports: model
prompts/options, tool results, final output, saved prompt and self-check are
identical with tracing enabled/disabled. Additional checks cover live flushing,
concurrent edge counts, cancellation, retries/usage, scored retrieval, recursive
REPL attribution, refinement commits/rollbacks, failure summaries and CLI routing.
Review caught and fixed batched-call cancellation semantics before any live run.
Trace files are separate from trajectory/evidence and never enter refinement.

The local package was installed editable for the requested debug run. macOS had
marked its generated `.pth` file hidden; Python skipped that file. Clearing the
hidden flag restored the source import, verified by `loop_research.__file__` and
the CLI's `research --help` showing `--trace`.

The editable install's hidden flag recurred before launch, preventing the CLI
from importing. No run or model call started. Reinstalled the normal package
with `uv pip install --python .venv/bin/python --no-deps --reinstall .`, matching
the documented non-editable setup; every installed Python module's SHA-256 was
verified equal to its source counterpart. This removes dependence on `.pth`
processing. The following live debug run uses that installation.

The user-authorized traced research run
`research-3265370f49e64ebbbc3c3bf0c24af6de` completed in **142.274 seconds**.
It asked for the SI unit names/symbols of five quantities, using NIST sources,
with explicit `--columns quantity --columns unit --columns symbol --keys quantity
--language en --trace`. It exercised single and batched search/fetch, two sub-LM
calls, six RLM iterations, evidence recording and automatic refinement.
The archive contains 327 trace events and 15 successful Codex calls, with no
component errors, retries or format repair. All 35 citation/quotation checks and
20 constraint-coverage checks passed. The self-check retained three
`stalled_search` issues from empty discovery records; it did not pass overall.
Refinement created the memory "Inspect search results before recording
discoveries" in harness commit `2a423027212fe1c430dfd200bdd55f3a27b22d70`.
The final table, all counts/timings/edges, issues and exact edit are saved in
`runs/research-3265370f49e64ebbbc3c3bf0c24af6de/trace_summary.md`.
This is a live debugging example, not a benchmark measurement.

## Full-system proof setup (2026-10-18)

The offline suite passed with **453 passed, 1 deselected in 49.43 seconds**
using `.venv/bin/pytest -q`. New coverage verifies the issues/signals split,
research base/no-learning lineage and restoration (including failed finalization),
individual child RLM identities and termination, and hard call-limit reporting
when the REPL catches a tool exception. Independent review found that last gap;
the regression failed before the trusted dispatch boundary fix and passed after.
The proof configuration uses `rlm.max_depth: 2`, committed separately for the run.

The first Chemistry proof attempt (`research-b758ea4a247a498485418f1266c7cacd`)
returned 28 rows with zero self-check issues after 15 iterations, but automatic
refinement exceeded Codex's input limit: 4,479,711 characters. Repeated root
history and REPL locals snapshots dominated the input. Refinement observations
now preserve initial instructions and incremental actions/results while omitting
those duplicates; the raw trajectory remains intact. Reprojecting that archive
produces 488,130 characters. The new regression failed before the fix and passed
after; independent review found no blocker. Full suite: **454 passed, 1 deselected
in 46.97 seconds**. The proof is rerun from the original BASE, not resumed from
the persisted oversized planning job. This removes duplication, not a general
bound on arbitrary future task/evidence sizes.

## Completed traced proof (2026-10-18)

With source commit `c944f51`, the final proof runs completed:

| Run | Archive | Root iterations | Codex attempts | Issues | Signals |
| --- | --- | ---: | ---: | ---: | ---: |
| A, Chemistry | `research-2903d5a9ba3744aaaa894dbff69cec32` | 21 | 150 | 0 | 58 |
| B1, Physics with learning | `research-7855ad7a472341bea97828cf8a104409` | 16 | 125 | 0 | 36 |
| B0, Physics from BASE without learning | `research-50e10a73a30a45fea4461a2b1b88832e` | 14 | 121 | 0 | 51 |

All three ended answer-ready and returned 28 cited rows with zero uncited cells.
All archived self-checks were independently recomputed and matched. B1 took
778.965 seconds versus B0's 681.376 seconds; this pair does not establish a
performance benefit. A crossed a long interruption: its UTC wall span was
6778.080 seconds versus 1413.605 seconds measured by the monotonic trace clock.
Fetched-text/largest-root-prompt ratios were 0.099, 0.179 and 0.170, so the
requested large-context advantage was not demonstrated.

A's automatic refinement created “Use boolean verdicts in constraint checks”
in harness commit `be22b9c3159359252b4edac1dad426af7ab26820`. B1 retrieved it
and used boolean verdicts, but B0 also did so without the entry; causal influence
is not established. Neither run refined mid-task. B1's subsequent edit ended at
`6c8f6e1361489ff027007edb00562c1b97a68640`; B0 restored that active HEAD.
Successful refinement inputs were 555,222 and 623,198 characters.

No child RLM spawned naturally. The explicitly requested extra traced check,
`research-dce3477bcf9141be8ebae3c66d384318`, spawned one depth-1 child with
three iterations and three REPL blocks, ending answer-ready. Its root used six
iterations and returned two cited rows with no issues, signals or component
errors. It also restored the active B1 harness afterward.

The Nobel fetch audit found no requested/opened URL mismatches in failed A
fetches. Suspicious paths came from search results, not root URL construction;
the fetch backend itself returned FETCH_FAILED. Per-page HTTP statuses were not
archived, so these are backend-reported access failures, not proof of a specific
HTTP status for every page. No fetch-code change or rollback was warranted.

The report at `runs/proof_report.md` leads with the RLM and self-improvement
verdicts and includes exact commands, provenance, context/call measurements,
REPL excerpts, parallel timings, every issue/signal, A's exact refinement edit,
component verdicts, and all final cited tables. Its 193 local evidence links,
all rendered tables, self-checks and lineage restoration were verified. One pair
is mechanism evidence, not a statistical result. No source changes followed the
454-test passing suite; this commit records the live evidence only.

## Round 2 implementation verification

The disk audit traced page leakage to printed REPL output retained by the pinned
RLM, the stock orchestrator's printed-candidate requirement, duplicated full task
context in the initial root prompt, and retrieved usage/outcome history. Project
subclasses now use a coordination prompt and task brief; full evidence remains in
Python variables/sub-calls, and printed stdout is still observable under the
unchanged upstream truncation. This is guidance, not a claim of live context
advantage. A negative test confirms deliberately printed page text still reaches
the root. The pinned RLM source integrity check passed unchanged.

Mid-task refinement already existed. The prompt now describes observed triggers
and learning mode. An isolated-worker fixture proves a background proposal commits
and is retrieved at a later root turn before worker completion. Candidate accounting
requires evidence-linked decisions for all presented issue/signal groups and model
added candidates, while allowing zero edits. Each planning job retains exact input,
schema, raw response and decisions across requests, stale replans and retries.

Codex completed web events in existing disk archives expose opened URLs and result
metadata, but no raw opened-page character count. Complete web events and separate
fetch telemetry now preserve that limitation explicitly; model-rendered returned
text is measured independently. Telemetry stays outside research/refiner inputs.

Fresh default suite: **500 passed, 1 deselected in 56.15 seconds**. The deselected
case is the opt-in live test; no tests or criteria were weakened. The full log is
`runs/round2/unit_suite.log`. The user has explicitly requested the subsequent
traced proof arms; their results belong in the append-only Round 2 report.
