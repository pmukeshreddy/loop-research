# Independent process-cleanup review

Reviewer `fetch_review`; 2026-10-20T08:48:04.579308+00:00; base `42424491009371cc7063c2a88394e92c97e974a7`. Reviewed commit `8a45fe2ff8e5b6468f6fcbd1f96ec22828a778db` retains the exact tested source bytes. No blocking finding for this narrow cleanup change. This is an offline source/test review, not a live-preflight success claim.

Reviewed source SHA-256: `b66c43f0348ad0868774dcd9548473002c9e23ff50de592ef4384aca86018b0c`. Tests SHA-256: `7ab9b215e0c7046506a27824e73655c18a0e757dba6b23663473518e6a78b97c`. Both pytest and probes explicitly asserted that `archive.__file__` resolved to the isolated `process-cleanup` worktree, avoiding the older installed source.

The nine new regressions passed in **0.89 seconds** (tool receipt `059142`; separate raw pytest log not retained). The exact three timer probes that previously reproduced duplicate-cleanup EPERM now issue **one successful group signal each**, retain `TimeoutExpired`, and emit no callback error. Full events/stacks: `process_cleanup_fetch_probe.json` (tool `838645`).

The parent's requested normal-completion probe cancels after real `communicate()` returns but before its wrapper returns to `RunContext`. The first signal gets ESRCH, which the existing handler catches; the caller receives `CancelledError`, with no callback error. Evidence: `process_cleanup_completion_gap_probe.json` (tool `67e5b2`). The completion/state gap exists, but this controlled probe did not establish a remaining EPERM; no broader claim is made.

The lock serializes stop-state checks and the owned signal. It marks `stopped` only on successful signaling or ESRCH and never holds the lock across wait/communicate drain. It does not skip cleanup merely because the leader exited: the regression reaps the leader, then confirms the descendant holding a pipe is killed and an unrelated group survives. Genuine first EPERM remains visible at the timeout caller or in Future callback logging. There is no blanket suppression or false success marker.

Only process cleanup and its tests change. No task/site selection, model, deadline, retry allowance, root/context truncation, field projection, planner schema/accounting or evaluator changes occur. The original failed Codex attempt lacks a full exception stack; reproducing and fixing local duplicate cleanup does not reconstruct its precise historical throw order. Broader installed/full-suite verification and a new live preflight remain parent-owned.
