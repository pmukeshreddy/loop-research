# Collection repair and bounded pilot plan

Execute inline with focused regression tests and an independent final review.

1. Reproduce failures from the 26 immutable campaign snapshots. Add publication
   evidence records for metadata (including itemprop), article JSON-LD, semantic
   time tags and labeled visible dates. Keep conflicting, malformed and uncertain
   dates unresolved; retain modification/date candidates separately.
2. Add bounded redirect traversal with URL/robots checks at each destination,
   original/final URL provenance, explicit failure categories, and snapshot reuse.
   Reassess repaired cached sources before spending on alternative discovery.
3. Start a new implementation-frozen repair run importing the old discovery,
   snapshots and usage ledger read-only. Preserve the old run and its failed
   checkpoints. Only collection-stage runs without generated questions may use
   this explicit repair continuation; do not relabel old validation results.
4. Keep the campaign target 50 × 5. Add a pilot stop at five accepted questions
   across at least two companies with at least one accepted expansion. Exercise
   later depth slots within a small company window rather than qualifying 50
   companies before trying an expansion. All existing validation gates remain.
5. Record a finite allowance using the existing explicit extension mechanism:
   effective total 15,000,000 tokens, 220 calls and 700 web actions, including
   inherited 390,747 tokens / 6 calls / 12 actions; concurrency one and $0 paid.
   Plan: discovery/capture/support/classification up to 30 calls/100 actions;
   generation and complete validation of five questions up to 90 calls/300 actions;
   bounded revision/rejection allowance up to 100 calls/300 actions. Use larger
   per-session browsing caps (nine usable actions plus guard) for actual solving,
   alternatives and shortcuts. These are ceilings, not permission to weaken gates.
6. Full tests/Ruff, snapshot-date audit, independent review, then run the bounded
   real pilot. Verify no-call checkpoint replay. Report actual X/Y/E, accepted
   example if any, tool traces, failures, inherited/incremental usage, overhead
   versus accepted-question cost and an honest remaining-campaign estimate.

The user explicitly authorizes finite local allowance increases for this pilot.
No external paid provider, API-key fallback, training, RL or product UI is in scope.

Live follow-up: v1 exposed a source-selection cap retaining undated cached pages
ahead of an eligible cached release, plus repeated invalid event bindings and
nonliteral extraction quotes. Fix selection order and duplicate redirect slots;
make revision feedback identify the exact rejected fact/quote. Pause v1 between
provider sessions and continue in `company-repair-pilot-v2`, preserving all v1
usage within the SAME total 15,000,000 / 220 / 700 limits. Pre-question graphs may
be archived privately during continuation, but no generated questions or validation
results can be imported. Acceptance predicates and evidence requirements stay fixed.
