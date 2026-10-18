# Company discovery and generation campaign

The generation target is **50 distinct companies, five validated questions each**:
250 accepted X/Y pairs, with private evidence E. This is a target, not a claim of
250 completed questions. Company research is the current example domain. No
training, RL or product UI is implemented.

## Configure and run

Install dependencies using the [quickstart](../README.md#quickstart). From the
repository root, with `PYTHONPATH` set as in that quickstart:

```bash
codex login status
.venv/bin/python -m webshaper doctor --config configs/company-campaign.json
.venv/bin/python -m webshaper run --config configs/company-campaign.json --run-dir runs/company-campaign-v1
.venv/bin/python -m webshaper status --run-dir runs/company-campaign-v1
```

`doctor` without `--probe-search` does not spend a model call. Discovery itself
records actual search activity. Each fresh solver receives only its self-contained
question, output requirements and browsing budget; it cannot read private run
artifacts. No corpus, company assignment, reference answer or generation history
is sent to the solver. [Open-web validation](open-web-design.md) describes the
unchanged correctness, temporal, ambiguity, difficulty and shortcut gates.

The [campaign config](../configs/company-campaign.json) has no fixed company list
or initial source URLs. It uses the Codex subscription, concurrency one, a shared
ceiling of **1,447,740 tokens, 49 calls, 13 web actions**, and **$0 additional paid
API/search spending**. These inherited pilot limits are too small to promise
250 accepted questions. Search, page opens and in-page finds consume actions.
Roles reserve a stop margin; usage is observed after dispatch and is not an
upstream hard quota. [Authentication and limits](running.md) apply unchanged.

For a different cutoff, copy this config before starting or use `webshaper init
--mode live --output configs/my-campaign.json`. Live init now creates an empty
discovery campaign; fixture init retains the historical offline example.
The four-company [open-web config](../configs/open-web.json) remains a historical
pilot, not a company-selection boundary. Keep its runs unchanged.

## Discovery and evidence readiness

The private registry distinguishes **discovered proposals**, **qualified and
selected companies**, **generated candidate versions**, and **accepted questions**.
Provisional industry, region and funding-stage labels never count as verified
coverage. Discovery prioritizes missing classifications, targeting at least ten
industry categories, five geographic regions and four funding-stage categories.
Coverage gaps block the overall `target_reached` flag even if question counts fit.

Only source URLs observed in actual hosted search/page activity are admitted by
discovery. Capture applies the existing public-URL, access, robots, byte-limit,
snapshot-hash and temporal rules. Independent assessment checks official company
identity, primary authorship and classifications using exact snapshot quotations.
Aliases/duplicate official domains and overlapping verified identifiers cannot
fill two company slots. Classification remains a bounded model assessment, not
an exhaustive corporate-identity audit.

Qualification normally requires three dated primary sources, three relationship
families, five connected entities and five possible family combinations. Funding,
founders, products, acquisitions, partnerships and investor relationships are
searched; every company need not have an acquisition. Typed partnership events
keep partners tied to the same event. Shared dates/categories cannot join
otherwise unrelated graph components. Combination counts measure readiness to
try generation, not guaranteed question diversity or web uniqueness. Missing
dates, access failures and unsupported claims remain rejection records.

## Quotas, diversity and depth

The company-research adaptation asks five different questions identifying the
same company. Each lineage preserves that company's reference answer. Default
minimum depth slots are **[0, 1, 1, 2, 2]**. All selected companies receive their
first-slot opportunity before later slots; attempts and revisions are bounded.
A validated shallow parent cannot fill a deeper slot. One final per lineage
earns credit, after all open-web validation and diversity gates pass.

Requirement signatures compare predicates and variable joins while ignoring
literal clue substitutions. Similarities of at least 0.8 within a company are
rejected, as are near-identical public templates across companies. A fresh
independent verifier also compares requirements against prior accepted questions
for the company. Unknown diversity judgments reject. These conservative rules
may reject useful candidates; they are not a guarantee of exhaustive semantic
deduplication. More clues alone never establish additional research depth.

Layer number is structural. Empirical difficulty remains separate: closed-book
results, observed question-only browsing success, and whole/partial shortcut
audits. Failed access and exhausted budgets do not prove a reasoning failure.

## Resume and explicit usage extensions

Repeat the exact run command to resume. The journal checkpoints discovery input,
company selection, graphs, per-slot allocation, validation and final quota credit.
Completed calls are reused. The implementation and acceptance configuration stay
frozen; code/config changes require a new directory. A subscription-limit pause
requires `--retry-limited` after reset. Unknown remote outcomes are never blindly
retried. Preserve incomplete and unsuccessful attempts.

A budget pause can be resumed with an **explicitly authorized additive usage
extension** without replacing frozen acceptance settings. Create a JSON file
containing a unique `authorization_id`, nonnegative `additional_tokens`,
`additional_calls`, `additional_searches`, and `additional_usd: 0`. At least one
usage increment must be positive. Choose the amounts only after authorizing them.

```bash
.venv/bin/python -m webshaper run --config configs/company-campaign.json --run-dir runs/company-campaign-v1 --budget-extension /absolute/path/to/authorized-extension.json
```

Reusing an identical authorization is idempotent; changing an existing ID is
rejected. Prior usage is never reset. Passing the file is the explicit authorization;
the pipeline never creates an extension or increases limits automatically.
No extension was authorized for the initial campaign.

## Collection repair and bounded pilot

The [repair config](../configs/repair-pilot.json) keeps the full 50 × 5 campaign
and all acceptance gates, but stops at five accepted questions across at least two
companies, including an accepted expansion. It qualifies a small company window
and tries question slots before discovering fifty companies. Failure to meet this
pilot target is reported as a shortfall, even if bounded work finishes.

The recorded [pilot plan](superpowers/plans/2026-10-18-collection-repair-pilot.md)
allocates **15,000,000 tokens, 220 calls and 700 web actions**, concurrency one,
including the old run's usage. The [explicit extension](../configs/repair-pilot-budget.json)
adds to the original allowance; paid spending remains $0. This is a finite ceiling,
not an estimate that guarantees five accepted questions. Source discovery has five
usable actions per session; solving, alternative checks and shortcut sessions have
nine, each with a reserved stop margin.

To continue the collection-only failed run in this workspace:

```bash
.venv/bin/python -m webshaper doctor --config configs/repair-pilot.json
.venv/bin/python -m webshaper run --config configs/repair-pilot.json --run-dir runs/company-repair-pilot-v1 --continue-from runs/company-campaign-v1 --budget-extension configs/repair-pilot-budget.json
.venv/bin/python -m webshaper status --run-dir runs/company-repair-pilot-v1
```

Repeat the same run command to resume under the frozen implementation. For a
fresh checkout without historical artifacts, omit `--continue-from` and choose a
new directory. `--continue-from` opens the parent read-only, verifies and copies
its raw snapshots, re-extracts date provenance, and inherits every completed call
and its usage. It does not import accepted tasks or solver results; parents with
graphs, candidates, validations or unresolved calls are rejected. Mode, cutoff,
scope and campaign acceptance settings must match. Previous failed qualifications
remain private audit records while repaired evidence is reassessed.

Dates are attributed to metadata, matching article JSON-LD, semantic time tags or
labeled visible publication dates. Modification, event and retrieval dates are
not substitutes; conflicting or uncertain publication dates remain unresolved.
Each source stores the method, supporting field/passage, original/final URLs and
redirect chain. Redirects are bounded and destinations receive access and robots
checks. Inaccessible pages prompt searches for alternative primary sources;
restrictions are not bypassed. Captured successes and failures are checkpointed
per URL so a growing discovery queue does not repeat completed collection work.

`export/pilot_report.json` separates inherited usage, new usage, collection and
qualification overhead, and question work including rejections. Per-accepted
figures and the remaining-campaign extrapolation are unavailable until at least
one question is accepted. Token figures there are observed usage; conservative
reservations for uncertain calls are in `manifest.json` and `usage.jsonl`.
Local budget exhaustion and subscription-limit pauses have distinct reason codes.

## Results and private artifacts

`export/company_coverage.json` summarizes discovered/qualified/selected counts,
verified classification coverage, missing company slots, accepted questions per
company, depth, browsing outcomes, rejection reasons and usage. Its per-company
rows also appear in `company_coverage.jsonl`. `manifest.json` contains aggregate
metrics and the effective budget. The private registry, source searches,
qualification attempts, slot allocations and diversity decisions are JSONL files
named `companies`, `company_discovery`, `company_source_searches`,
`company_discovery_failures`, `company_qualification_attempts`, `company_qualifications`, `company_allocations`,
and `company_diversity`. Usage extensions are in `budget_authorizations.jsonl`.

Accepted X is in `public/tasks.jsonl`; Y and private allocation/depth are in
`references.jsonl`. Public IDs are opaque and salted per run; they encode no
company domain or slot. References use the public ID and retain `internal_task_id`
for private audit joins; provenance also records the `public_task_id`. Human
review accepts either ID. E is in `graphs.jsonl`, `sources.jsonl`, `web_sources.jsonl`,
`web_evidence.jsonl`, and the immutable snapshot directories. Actual browsing
events and visited URLs are in `web_traces.jsonl`; validation, attempted solves,
alternatives, shortcuts and rejection records retain failed work too. Only
`public/` is intended for solver distribution. Never distribute the private
coverage registry or references with the questions.

See [output contracts](outputs.md), [testing](development.md), and
[recorded results](run-results.md). Offline campaign tests are **fictional,
scripted fixtures** and are never presented as real generated company data.
