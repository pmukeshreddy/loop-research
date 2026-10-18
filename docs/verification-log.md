# Verification log

The repository initially contained only the supplied brief and paper; no Git
history or application baseline existed. Implementation followed
`implementation-plan.md` in five stages.

- Source/storage tests first failed on absent functionality, then passed after
  immutable snapshot/span capture and durable call reservations were implemented.
- Query tests established typed direction, event joins, union semantics,
  unresolved identities/support, historical source rules and three-valued membership.
- Expansion tests established frozen layers, exact intermediate equality,
  alpha-renaming, final-answer checks and ablation redundancy detection.
- Validation tests cover private solver inputs, citation correctness, unknown
  judgments, leakage, bounded revision and five-attempt solvability.
- The fixture CLI exercises every stage and exports one fictional expanded task.
  Running it again produces the same summary without additional model calls.

A separate read-only code reviewer found important issues. Each was reproduced
by a failing regression test, fixed, and followed by a passing full suite:

| Finding | Regression |
| --- | --- |
| Queued work after subscription limit | `test_subscription_limit_stops_dispatch_immediately` |
| Corrupted snapshots re-exported | `test_tampered_snapshot_cannot_be_exported_as_valid` |
| Global factorial query normalization | `test_canonical_union_does_not_permute_unrelated_branch_variables` |
| Target count before deduplication | `test_duplicate_tasks_do_not_end_generation_early` |
| Interrupted family checkpoint duplicated work | `test_resume_after_final_checkpoint_does_not_duplicate_a_family` |
| Unknown transport outcome treated as revision | `test_unknown_provider_outcome_does_not_trigger_generation_retry` |
| Future evidence invalidated historical claims | `test_future_conflict_does_not_erase_a_historical_fact` |

Additional tests cover explicit subscription-limit retry, two-layer replay,
negative exclusion certificates, raw snapshot integrity and capture coverage
when extraction fails. The first live attempt also exposed repeated exact text
in a press-release summary/body; deterministic first-occurrence selection is
now tested without weakening exact-text or semantic-support checks.

Live integration also exposed omitted evidence-span mappings in the candidate
judge payload and ambiguity between private canonical IDs and public answer
names. The judge now receives the spans and publication-date basis, and its
instructions distinguish those representations. Extraction retries receive
the concrete prior failure. Regression tests cover these changes and ensure
the private evidence graph still cannot enter a solver payload.

Quality counters include proposals rejected before candidate construction;
capture/date errors and extraction errors are reported separately. The final
local suite at the original delivery had **56 passing tests**, with Ruff passing. The wheel was
installed in a separate environment and completed the offline workflow.
`runs/fixture-final-delivery` exported one fictional task at layer 1 with two
rejected expansion proposals. Re-running it left all 15 export files and all
29 completed scripted provider calls unchanged. These fixture success rates
are test behavior, not measured model performance.

Final review found two further edge cases: duplicate original literal IDs could
silently retarget a fact during canonicalization, and a subscription pause could
hide completed solver responses from quality counters. Both have failing-then-
passing regressions. Original IDs must now be unique before normalization;
candidate starts and incomplete validation response counts survive pauses.
The reviewer confirmed these fixes. Both completed real extractions also pass
the stricter duplicate-ID check in a read-only replay.

Known expansion-evidence failures preserve the last accepted parent. Export
and human review after an implementation upgrade use the original journal
configuration without dispatching models. Natural-language expansion refusals
receive a stable `no_valid_expansion` code in new runs. These paths are tested.

There are no deferred reviewer findings. Architectural decisions are documented
in `design.md`: entity-set output, corpus-based browsing validation, conservative
negative certificates, branch bounds, local process locking, and pending human
review of live tasks. These are explicit first-path limits, not assertions of
paper reproduction or an independent evaluation benchmark.

Paid API/search calls remain disabled. Codex CLI 0.163.0 reported ChatGPT login;
isolated subscription sessions successfully exercised structured output and
built-in web search. The role configuration must keep Codex's execution host
enabled for web search while disabling other capabilities separately.

## Temporal export and difficulty-gate follow-up

The public export included metadata for sources unavailable to validation. Six
new parameterized regression cases first failed, then passed after the fixes:

- Export and `documents_for` now share `eligible_sources`. A 2026 source is
  excluded from a 2025 task unless retrospective access is explicit; undated
  sources remain excluded in both modes. Tests check whole entries with both
  redistributable and withheld text, plus intact private raw/text snapshots.
- A correct closed-book answer on an expanded task now returns immediately.
  Tests cover revise and reject, preserve the completed attempt, earlier checks,
  feedback and metadata, and assert zero downstream provider calls, including
  when shortcut auditing is forced on. Before the fix, 12 downstream calls ran.

The full suite now has **62 passing tests**; Ruff passes. An independent read-only
review found no actionable correctness issue in these fixes. Acceptance gates,
historical evidence policy and exact answer equality are unchanged.

Prompt v1.2 favors minimally constrained seeds with necessary expandable leaves,
reinforces variable subjects and stable identifiers, and requests separately
quoted investor-to-company relationships where the primary source supports them.
These are proposal improvements, not exceptions to validation. A new frozen
real run uses `configs/real-expansion.json`; previous runs are preserved.
Its first attempt retained a depth-0 seed: extraction omitted announcement-year
facts, and the revised date-disjunction query repeated its investor constant,
making that constant ineligible for expansion. Prompt v1.3 explicitly requests
separately evidenced year projections and degree-one leaf selection. Neither
change bypasses the independent fact assessor or changes leaf eligibility.


## Open-web mode follow-up

Added a distinct `open_web` contract; absent modes remain `legacy_corpus`.
Public exports and solver payloads use allowlists. Solvers receive only the
question, output requirements and browsing budget, in fresh Codex sessions with
local tools disabled and a restricted filesystem permission profile.

The full local suite has **122 passing tests**; Ruff and relative-link checks pass.
New scripted offline tests cover complete seed/expansion validation and resume,
missing browsing, incorrect closed-book difficulty, unsupported citations,
plausible alternatives, partial shortcuts and failure categories. These synthetic
traces do not demonstrate real browsing. Provider tests cover observed native CLI
events, cached and interrupted traces, restricted flags and conservative usage.

Independent review found three issues, each corrected before the pilot:

- All added atoms now receive partial-removal consideration, including connected
  variable-object joins. A failing-then-passing regression covers the missed case.
- Fresh cited pages share the deterministic publication policy. Future and undated
  captures cannot be accepted by a permissive grader; both counterexamples have
  failing-then-passing regressions. Explicit retrospective access remains distinct.
- Web sessions reserve a stop margin and retain already queued events after
  cancellation. This is a local guard, not an upstream hard quota. Missing-tool
  errors retain their specific category in attempt metrics.

The reviewer reran **71 focused tests**, checked the corrections and found no
additional pre-pilot blockers. Full-suite and Ruff checks were also run by the
implementer. The real capability probe and bounded pilot are recorded separately
in [run results](run-results.md); legacy corpus success is not open-web validation.


The first open-web pilot exposed an ordering issue: the offline construction judge
was asked to establish global uniqueness before the live alternative audit could
run. Global ambiguity is now assessed by that mandatory live audit. Construction
support, dates, wording, identity, leakage and usefulness still gate progression;
unknown/ambiguous live alternatives still reject. Named private-review concerns
reach both the live researcher and its independent grader. A new regression
fails before this correction and passes afterward. The final suite has **122
passing tests** and Ruff passes; independent review reran 23 open-web tests.
