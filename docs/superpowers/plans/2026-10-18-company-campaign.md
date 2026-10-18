# Company campaign implementation plan

> Execute inline with test-driven development and a fresh independent final review.

**Goal:** Discover and qualify 50 companies and target five diverse, validated
open-web questions per company, with honest resumable shortfall reporting.
**Architecture:** An optional campaign scheduler shares the existing Journal,
ModelGateway, source storage, expansion and unchanged open-web validation gates.
**Stack:** Existing Python/Pydantic/SQLite/official Codex CLI; no new dependencies.
**Spec:** [Design](../specs/2026-10-18-company-campaign-design.md).

## Constraints and review focus

$0 extra; default 1,447,740 tokens/49 calls/13 web actions/concurrency one. Private
allocation never reaches a solver. Discovery names are not qualified coverage.
Review duplicate identities/aliases, unsupported primary classifications, crash
windows around quota credit, structural near-duplicates, and budget-extension
replay without changing frozen generation settings.

## Tasks

1. [x] Add campaign contracts and typed partnership events (`models.py`,
   `query.py`). Add tests for 50×5 target consistency, mode restrictions, depth
   schedule and event joins; run them red, implement, then rerun green.
2. [x] Implement `discovery.py`: observed-URL provenance, company identity
   deduplication, balanced queue, dated primary snapshots, independent company
   assessment, connected-evidence qualification. Test hallucinated URLs, aliases,
   sparse evidence, unknown classifications and interrupted cached discovery.
3. [x] Implement `campaign.py` and `diversity.py`; integrate `pipeline.py` via
   optional company/slot context and stable seed IDs. Test company-reference
   mismatch, five-per-company ceilings, strict requested depth, equivalent/near
   queries, fairness, and no duplicate work after interruption. Reuse all existing
   validation functions and question-only solver payloads.
4. [x] Add private company exports and coverage metrics; add explicit idempotent
   budget extensions (`storage.py`, `cli.py`, `export.py`). Tests must prove public
   privacy, per-company counts after dedup/manual rejection, usage attribution,
   shortfalls, and unchanged frozen acceptance rules on extended resume.
5. [x] Add campaign config, regenerate schemas, update concise README and detailed
   guides. Run full pytest/Ruff and independent review, then freeze implementation
   and start a new bounded live campaign. Preserve and report its actual outcome;
   test no-call resume on a pause. Commit and push authorized changes.

**Outcome:** Implementation and bounded live campaign completed; campaign paused at its existing web-action ceiling with five proposals, zero qualified companies and zero accepted questions. See [recorded results](../../run-results.md). No quota or acceptance standard was relaxed.
