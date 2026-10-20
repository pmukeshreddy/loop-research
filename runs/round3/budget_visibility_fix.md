# Requested task-time visibility

The failed `B1-frozen-2` run exposed a product observability gap: `budget()` reported remaining calls while omitting the remaining time on the task's existing monotonic deadline. This change adds `seconds_remaining` to explicitly requested snapshots. It does not establish that time visibility alone would have made that run finish.

## Archived evidence

The source was `9251c8e8925f57cf9fc924e0fd57b1bd0d74bd6d`; the archive is `runs/round3/cohorts/context_outputs_v1/workspaces/B1-frozen-2/runs/research-d34b080d45ab4d4da1a026a2ecc21e39`, task `5f579a96530b9d0b8eaa08f9`. The CLI exited 1 after the configured 3,600-second task deadline, with `empty_output` and `timeout`; no agent result was submitted. The archive's top-level `status: complete` records terminal processing and must not be read as successful research.

The researcher requested and printed 17 budget snapshots. The last, trajectory line 279 and trace lines 3017–3018, completed at `2026-10-20T16:36:46.285951Z` and returned:

```json
{"limit": 300, "reserved": 222, "remaining": 78}
```

The worker timeout occurred 12.161948 seconds later at trace line 3055. That interval is a retrospective timestamp calculation, not a value that the old API returned. The last root request began at `16:36:58.217198Z` and failed with `BudgetExceeded: Task deadline exceeded`.

Other contributors remain visible. Two distinct downloads each spent about 600 seconds before `Broken pipe` failures. The final executed REPL block constructed five structured subcall prompts; four were attempted, including two permanent provider input-length failures at 2,127,326 and 1,456,368 characters, each with no retry. Those are invalid agent-assembled ordinary subcalls. Time visibility neither shrinks their inputs nor prevents that strategy.

The 3,599.989534-second observed worker interval comprises 495.186707 seconds of clipped root-model spans, 3,103.148874 seconds of REPL spans and 1.653953 seconds between them. Within the REPL, the nonoverlapping top-level search, fetch and subcall spans total 873.883739, 1,395.473699 and 723.425966 seconds respectively. See the independently preserved `B1-frozen-2.budget_timeline.json` and `B1-frozen-2.final_subcalls.json` beside the cohort. Their hashes and original trace/trajectory hashes are recorded in `budget_visibility_fix.json`.

The later host clamshell interval began at `16:40:55Z`, after this timeout; it did not cause this run's terminal deadline. The new field uses the existing monotonic clock, whose behavior during system suspension is unchanged. It is not a promise about elapsed civil time across suspension.

## Minimal implementation

The isolated baseline is `6dad1de3938ca4775fd8fb084cb1e73107fd89c6`, following the independently reviewed readable-extraction correction.

* `codex_backend.py`: under the existing snapshot lock, return `seconds_remaining = max(0.0, self.deadline - time.monotonic())` alongside unchanged call counters. Reading does not reserve calls, extend the deadline or raise merely because time has expired.
* `agent.py`: explain the new field in the shared static resource contract, including the possibility of calls remaining at zero time. The task timeout and every other configured limit remain unchanged.

The existing session RPC already checks cancellation and archives exactly the explicitly requested snapshot. It needs no changes. No dynamic value is inserted into initial root or task inputs, and no snapshot is requested automatically. Updated static wording is shared across the new cohort; it intentionally differs from the prior source's static wording. The research model remains responsible for its choices. There is no forced submission, new retry, scheduling change, root-history change, truncation, model fallback or automatic subcall splitting.

A snapshot immediately becomes historical: other work and time passage can reduce both allowances. It is neither a reservation nor an estimate of how long the next operation will take. Completion and evidence quality are not guaranteed.

## Verification

Tests were changed before implementation. The first RED run preserved six missing-field failures plus two test-fixture failures because the initial-parity backend factory also constructs a refinement backend without a research budget. Guarding that test-only `None` case yielded six expected failures and twelve passes before product edits. The worker regression's missing field caused its normal recovery path to reach the offline fixture's unsupported repair response; the complete traceback is retained rather than presenting that as a separate product issue.

The focused GREEN run passed all 18 tests in 15.22 seconds. It covers exact controlled-clock values, zero and expired deadlines, read-only behavior, concurrent reservations, retries and in-flight calls, resumed counts, cancellation, exact RPC archive values, and a real isolated worker. The existing actual-root comparison tests retain complete entry checks and now also vary remaining task time while forbidding any implicit snapshot; all initial input bytes outside the complete entry payload remain equal.

The whole isolated suite passed **1,110 tests, with 1 deselected, in 138.59 seconds**, exit 0. All four source/test hashes remained unchanged after verification. Independent review passed 62 focused tests in 30.38 seconds and found no blocker; an additional controlled-clock probe verified no civil-clock reads and no extension of the deadline. The review measured the common static contract change at +168 characters with the default configuration. Its receipts are `runs/round3/budget_time_review.md` and `.json` in the main checkout; the JSON hash is bound in this fix's evidence file.

RED, GREEN and whole-suite logs are under `runs/round3/budget_visibility_evidence/`. No installation or live model/network call was performed.
