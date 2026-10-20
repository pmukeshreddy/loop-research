# Complete-snapshot refinement implementation plan

> Execute inline with test-driven development, then independent review. The user's instruction to fix errors and replay affected runs authorizes this correction; scheduling remains agent-controlled.

**Goal:** Plan over a supplied observation larger than one provider prompt without removing any supplied field, occurrence, or candidate.

**Architecture:** Keep the exact existing shared-text planner for complete backend prompts at or below the observed 1,048,576-character provider limit. Above that transport boundary, an isolated Python worker receives the complete immutable logical JSON through a read-only `snapshot()` broker. The worker can inspect its mutable local copy and delegate selected evidence to the configured refine model. A separate loop archives complete model inputs, code, stdout/stderr and final content without a new truncation rule. Existing strict Proposal, evidence-anchor, candidate-accounting and edit-limit validation remain the host's final gate.

**Spec:** The actual failed request and manifest in `runs/round3/cohorts/quoted_text_v1/A.failed_midtask_manifest.json`, plus the conditional transport design review in that cohort. Full logical input is 3,027,914 characters; rejected backend input is 1,611,089. Generic input-size routing is not task/site routing or evidence selection.

**Constraints:** Preserve current research instructions, RLM pin/formatter, fetch path, scheduling, snapshots, harness mutation boundaries, model settings and schemas. Every planner call uses purpose/model `refine`; no search, fetch, grader or harness-write APIs are exposed. Small-input behavior and tests remain unchanged. No new content cap, summaries, field omission, automatic retry after planner failure, or forced edit. All actions and errors remain archived.

**Budget ruling:** The overflow operation uses the existing `codex.timeout_s` as one aggregate deadline, including queueing/subcalls and the isolated worker, and `rlm.max_iterations` as its maximum planner turns. Individual backend retries/configuration remain unchanged. This bounds a newly iterative path; it does not enlarge research budgets or change direct-path retry behavior. Any exhausted budget is a visible failed job. Scope cancellation must drain owned calls before the operation ends.

## Review focus

- Complete logical content including unknown fields, Unicode, all candidate occurrences and historical entry metadata must reach the isolated worker unchanged.
- A code block printing more than 20,000 characters must reach the next planner prompt and action archive unchanged.
- Planner and subcall role attribution must never enter the research root/sub metrics or answer-ready trace namespace.
- Cancellation, deadline, iteration exhaustion and malformed proposals must fail visibly without partial harness edits or lingering owned calls.
- Worker code must not read host archives/secrets or mutate the authoritative snapshot; a fresh snapshot call must restore its exact input.

## Task 1: owned backend scope (parallel isolated prerequisite)

Files: `codex_backend.py`, dedicated scope tests. Interface: `backend.scope(budget=...)` yields a child transport with complete/last_usage/ctx; exit cancels/drains only child calls. Preserve explicitly injected runner/sleep/jitter and bind the normal runner to the child context. Test parent cancellation, parent survival, concurrent drain and close races. Commit separately, then integrate into this worktree.

## Task 2: generic overflow planner

Files: new `refine_context.py`; minimal routing in `refine.py`; tests `test_refine_context.py`.

- [x] Write a failing integration test with an irreducible >limit synthetic observation and an injected Codex CLI runner. It must actually execute isolated code, verify the full snapshot hash/unknown fields, call the refine submodel, submit a valid strict proposal and preserve an unchanged source snapshot.
- [x] Add tests for >20k stdout/stderr preservation, strict accounting/schema failures, no cross-namespace traces, iteration/deadline/cancellation failures, exact routing boundary and unchanged small-input route.
- [x] Run RED and retain logs before implementation.
- [x] Implement `plan_context(ctx, backend, job_id, logical_text, schema, instructions) -> str`, the broker, isolated worker and untruncated code loop. Archive full context/schema/request/actions under the existing task archive in a job-specific directory. Pin all calls to configured refine model and purpose. Broker exposes complete snapshot, model completions, validated structured subcalls and action archival only.
- [x] Route overflow before any rejected backend dispatch. Preserve original prompt/wire/logical hashes as input evidence; label the representation and actual transport separately. Validate the returned proposal through the existing host code before application.
- [ ] Run focused and full offline suites; independently review the complete diff, tests, archive identities and actual saved-input replay.
- [ ] Commit tested product fix and review. Reinstall offline, freeze a new source, check saved refinement/audits, roll to BASE, and replay all A/SI/B runs. Fresh predictions must follow the new successful A and precede every new B.

## Execution ledger

- Baseline worktree `round3/refiner-context` starts at 4aa6b37. Focused inherited suite:57 passed/4.05s.
- Setup copied existing `data/` fixtures including pinned repositories. An extra attempted `vendor/` copy failed because that top-level directory does not exist; the actual fixture path is `data/vendor`. No source or run was affected.
- No product implementation written before the regression tests.

- Implementation and independent product review complete; full offline suite 992 passed, one live test deselected. Real saved-input replay and final integrated helper suite remain pending.
- Review found and tests reproduced two archival defects: failed-attempt reply loss (closed by scoped full logging) and post-dispatch journal race (closed by opt-in handler draining). No new evidence removal was introduced.
