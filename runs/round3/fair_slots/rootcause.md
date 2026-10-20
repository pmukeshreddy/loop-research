# Fair Codex slot admission

This fix replaces the cross-process slot lottery with FIFO admission in `CodexBackend._acquire_slot`. It changes no research prompts, refinement scheduling, model choices, configuration limits, transport retries, or call accounting. Work began from source commit `9de64148a8b4bde40015d3001bc79d1c43b0a8ba` in the isolated `round3/fair-slots` worktree.

## Observed failure and reproduction

The superseded `cohorts/final` B0-1 run is `research-25eb3a4bccde4c03b0b61cce55ded4c9`. Its saved `trace.jsonl` line 332 starts search span `ea7c10869e014f47bd1d8bd047448453` at `2026-10-20T02:59:21.704158+00:00`. Line 394 ends that span at `03:09:21.711503+00:00`, with duration `600.0071062920033` seconds and `BudgetExceeded: Deadline while waiting for Codex concurrency slot`. Later requests could obtain slots while this request remained waiting. The parent preserved and interrupted the affected cohort; this patch does not edit that evidence.

Before the fix, `_acquire_slot` scanned numbered slot files from zero through `max_concurrent - 1`, attempted a nonblocking exclusive `flock`, then slept up to 50 ms if every slot was occupied. An arriving request and an older waiting request had exactly the same eligibility. A newly arriving request could take a just-released slot while the older request slept, repeatedly, until the older request's deadline expired. OS locks protected capacity and released slots after a crash, but provided no queued admission order.

The first new tests ran against the unchanged implementation. They hold the sole slot, let an older request reach its wait, pause that request's polling, release the slot, and let a later request poll first. They exercise real OS locks, once with threads and once with spawned processes. Both fail with actual admission `["late", "older"]` instead of `["older", "late"]`. The sleep hook controls the adversarial schedule; it does not replace locking or admission. See [the original red log](fair_slots_red.log).

## Protocol and cleanup

The existing per-user temporary directory and numbered slot locks remain. A persistent `queue.lock` inode serializes only queue registration, inspection, and slot claims. It is never unlinked, because replacing the inode could split mutual exclusion between participants.

Under that mutex, each requester creates an exclusive, uniquely named ticket, with an ordinal greater than every currently live queued ordinal and a UUID suffix. The requester locks the ticket before releasing the mutex. There is no mutable counter file or JSON queue manifest, so a process killed during a partial counter write cannot corrupt ordering. Empty ticket files carry only their filename and OS-held ownership lock.

Only the oldest live ticket may claim an eligible numbered slot. Successful admission removes its ticket immediately and releases the mutex before the model runs, allowing subsequent tickets to fill the other slots. A locked ticket is live; an unlocked ticket can be removed after acquiring its lock while holding the mutex. Liveness does not depend on a PID, PID reuse, wall-clock age, or assumptions about execution duration.

Cancellation or deadline expiry unlinks the requester's unique ticket without waiting for the queue mutex, then closes the ownership lock. Concurrent readers tolerate a missing path. A claimed slot is also closed if cancellation or deadline expiry races the claim. A process killed while queued, while holding a slot, or between ticket creation and ticket locking leaves OS locks released; the next entrant cleans up an abandoned ticket and can proceed. Malformed ticket names cause a visible failure; they are not silently treated as permission to evict a potentially live owner.

Both queue-mutex admission and capacity waiting check cancellation and the same original slot-wait deadline. Capacity waits retain the 50 ms maximum polling interval. The short metadata mutex uses a 1 ms maximum retry interval, for the regression described below. This is not a deadline extension or transport retry change. `complete`, `CallBudget`, the configured concurrency of four, operation timeout of 600 seconds, task timeout of 3600 seconds, call budget of 300, and existing retry policy remain unchanged.

## Full-suite regression found and corrected

The first focused run passed 38 tests; after additional cancellation/crash coverage, 44 focused tests passed, including 13 new tests and 31 existing backend/isolation tests.

The first full-suite attempt produced **913 passed, 1 failed, 1 deselected**. The failure was `test_selection_is_same_prefix_for_stream_and_baseline`: the new worktree had copied pinned fixtures under `.verification`, while this existing test requires `data/downloads/wandr/data/test.jsonl`. The repair created worktree-local `data/vendor` and `data/downloads` links to the worktree's own copied fixture directories. No installation, download, main-worktree fixture change, or test change was made. See [the full failure log](fair_slots_full.log) and [isolated reproduction](fair_slots_baseline_failure.log).

The second full-suite attempt produced **913 passed, 1 failed, 1 deselected**. This was a real new admission-latency regression: `test_parallel_completion_keeps_sequential_results_archives_and_report_order` measured peak concurrency one instead of two. Copying the original 50 ms capacity polling interval to the new, short queue mutex made a registering thread sleep while free capacity existed; fast fixture calls could finish before it retried. The same failure reproduced in isolation.

Only the queue-mutex retry interval changed to at most 1 ms. Capacity polling remains at most 50 ms, and no test assertion was changed. The previously failing concurrency test then passed in **10 out of 10 fresh pytest invocations**. The second full-suite log has the historical, misleading filename `fair_slots_full_green.log`; it is a **failure log**, not green evidence. See [that preserved log](fair_slots_full_green.log), [isolated concurrency failure](fair_slots_parallel_check.log), and [ten subsequent passes](fair_slots_parallel_repeated.log). The final retry change was made just before the second suite finished; only the subsequent complete run is evidence for the final source state.

The final source passed the complete offline suite: **914 passed, 1 deselected in 104.97 seconds**. The deselected test carries the existing live marker. The source remained unchanged throughout this final run. Command: `PYTHONPATH=src /Users/mukeshreddypochamreddy/Desktop/loop-research/.venv/bin/python -m pytest -q`, from the isolated worktree. See [the final full-suite log](fair_slots_full_final.log).

The nine raw logs are preserved byte for byte, including pytest's trailing whitespace; `log_manifest.json` records their hashes. Source, tests, documentation, and the manifest pass the whitespace check. An unfiltered check also reports the unchanged whitespace in those raw logs.

## Tests and independent review

The new tests cover thread FIFO; spawned-process FIFO; four simultaneous admitted processes with a fifth blocked; canceled and timed-out heads; killed queued and admitted processes; cancellation and deadline while waiting for the queue mutex; cancellation immediately after ticket registration and slot claim; a process killed after ticket creation but before ownership locking; and malformed live-ticket state failing without deleting ownership.

Existing backend process-sharing, durable attempt accounting, cancellation, retry, and ambient-slot isolation tests are retained. Offline tests keep their isolated `TMPDIR`; no test contends with production slots or invokes a model or network transport. Pinned WideSearch and WANDR files were copied from disk into the isolated worktree; no source dependency or vendor implementation was changed.

Two independent agents reviewed the initial FIFO protocol and each ran the 13 new tests successfully. They checked the persistent guard inode, registration and crash windows, lock-based liveness, unique-owner cleanup, deadlines/cancellation, concurrent capacity, and original red evidence. The final 1 ms mutex retry delta received a separate independent review with no significant remaining issue. That reviewer ran all 13 fairness tests plus the exact existing baseline parallelism regression: **14 passed in 1.87 seconds**, bound to the final backend hash below. Their separate receipts are `runs/round3/fair_slots_independent_review.md` and `.json` in the parent workspace; those parent-owned files are not included in this commit.

Final source SHA-256: `src/loop_research/codex_backend.py` is `b8f46de7dd14ee64143adbc4683cf6752233a1d3a81205116873537ee38106ac`; `tests/test_codex_slot_fairness.py` is `5024c91e5e9ebc435bcca04d7d9aa9ceca8529744eefc145b95f79848c39040d`.

## Generalization and limits

The queue is shared by all callers using the same per-user temporary directory and protocol, regardless of task, model role, source website, run ID, or research topic. It contains no seeded lesson or case-specific path. It prevents a later registered request from taking capacity ahead of an older live registered request.

FIFO means **successful registration order under the queue mutex**, not exact wall-clock function-entry order. The mutex itself uses cancellable nonblocking polling; the scheduler must still let a waiting process run. FIFO does not guarantee completion under overload, during indefinitely long held calls, or within a budget too small for the admitted workload. Those failures remain visible under the existing deadlines.

All participants should use the same `max_concurrent`, as the cohort does. With conflicting limits, a limit-one head can wait for slot zero while higher numbered slots are free; later tickets cannot bypass it. Therefore concurrent work-conservation is demonstrated for an agreed limit, not claimed for inconsistent configurations. Old code that ignores the queue can still compete for existing slots, so the parent must install the new source consistently and start the new cohort after the prior owned processes stop.

The fix retains stable empty slot/mutex files deliberately; they are coordination inodes, not leaked ownership. Live tickets are removed on admission/cancellation/timeout, and abandoned tickets from killed owners are reaped by subsequent admission. No claim is made that a process killed without any later caller can execute its own cleanup.
