# Company research data generation — implementation plan

Inputs: `2026-10-17-webshaper-data-generation.md` and Tao et al.,
`2507.15061v1.pdf`, especially §§2, 3.1–3.3. Workspace inspection found
no existing implementation, package configuration, tests, or Git repository.

## Design and scope

Implement a Python CLI with Pydantic contracts, SQLite checkpoints/call journal,
content-addressed source snapshots, and JSONL exports. Start with one fully
offline fictional corpus; use exactly the same pipeline with configured live
model/search adapters. Do not run paid calls without credentials and an approved
USD limit. No training, RL, or demonstration collection.

User clarification: default live backend is official Codex CLI using existing
ChatGPT sign-in, separate ephemeral sessions per role. Additional API/search
budget is $0. No API-key backend or silent fallback. Check built-in web search;
start at concurrency 1 and pause on subscription limits. CLI authentication
remains managed by Codex; never read or copy auth tokens.

Paper mechanism: knowledge projections compose through unions, intersections,
and recursive dependencies. Freeze leaf constants at each layer, replace each
with an identifying subquery, and preserve the original answer.

Explicit adaptations: directed typed predicates, event joins, fixed operational
filters, exact intermediate/final answer equality, date-aware evidence,
three-valued candidate membership, independent semantic judging, and private
references separated from solver-visible tasks. Equality in the captured graph
does not prove open-world uniqueness; the judge must check plausible alternatives.

## Stages and interfaces

1. **Sources and durability** — `models.py`, `storage.py`, `sources.py`,
   `providers.py`. Define contracts before agents. Capture local TXT/HTML/PDF
   and scoped URLs, retain raw/text hashes, stable character spans, dates,
   categories, errors, access policy. Journal calls before dispatch; reserve
   budgets, cache completed calls, and halt on uncertain outcomes. Tests cover
   immutable snapshots, span integrity, cutoff rules, resume, and budgets.
2. **Facts and seeds** — `query.py`, `generation.py`, `prompts.py`.
   Extract source-grounded entities/facts, independently assess support, reject
   unresolved identities. Execute unions of conjunctive directed queries with
   shared event variables; derive Y and evidence paths. Explicit negative
   facts can exclude candidates; missing facts leave them unresolved. Tests
   cover unions, joins, mixed funding rounds, unsupported facts and completeness.
3. **Expansion** — `expansion.py`. Freeze deterministic eligible leaves per
   layer; build exact identifying subqueries, merge without changing filters,
   recompute answers, and measure clue-ablation redundancy. Newly introduced
   leaves wait until the next layer. Preserve all versions and last accepted
   parent on failure. Tests cover answer drift, ambiguous intermediate sets,
   variable capture, layer ordering, and redundant clues.
4. **Validation and orchestration** — `validation.py`, `pipeline.py`, `cli.py`.
   Separate judge and solver prompts/configuration; solver sees X and permitted
   source text only. Run five browsing attempts by default and closed-book
   screening on expansions. Fail closed on unknown correctness checks. Bound
   revision/tool loops and resume checkpoints. Test leakage, rejection/revision,
   independent payloads, provider failures, and one end-to-end fixture run.
5. **Deduplication and export** — `export.py`, configs, README.
   Deduplicate normalized questions and canonical query/answer/provenance;
   group lineages, answer companies and near-duplicate sources in partitions.
   Export tasks, references, provenance, validations, rejections, manifest,
   quality report and permitted public corpus. Test partition integrity,
   reference isolation, reproducibility and restart without additional calls.

## Verification and delivery

Write meaningful failure-case tests before each stage's implementation. Run
the full local test suite after each stage. Then run the fixture CLI, inspect
exported records, resume the same run, and verify unchanged completed calls.
Document exact install, fixture, provider setup, live preflight, run/resume,
review and export commands. Live default target: 10 accepted tasks. Keep the
first live pilot marked pending manual review. Report actual fixture metrics
as synthetic test results, never real company data.

## Review focus

Wrong event joins; absence mistaken for negative evidence; post-cutoff sources;
solver access to private metadata; retries after uncertain paid calls. All five
receive explicit regression tests. Configuration, prompts, schemas, source
hashes and acceptance policy are frozen per run; changes require a new run.
