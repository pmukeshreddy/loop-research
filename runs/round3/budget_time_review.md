# Independent budget-time review

No blocking findings in the reviewed changes atop `6dad1de3938ca4775fd8fb084cb1e73107fd89c6`. Independent offline tests: **62 passed in 30.38s**, covering budget visibility, actual worker forwarding, first-root comparison inputs and backend behavior. Source hashes are in the [JSON receipt](budget_time_review.json).

`budget()` adds `seconds_remaining` from the existing monotonic deadline under the existing reservation lock. It consumes no call, changes no count/deadline, and clamps to zero at expiry. An independent clock probe confirmed positive/zero/expired values, unchanged reservations and deadline, rejected expired admission, and no civil-clock reads. Cancellation still prevents access and journaling after worker closure.

The tool contract explicitly names the task’s monotonic clock. Static common guidance adds 168 characters for default config; no automatic dynamic time metadata enters initial root prompts. Actual equal-entry first roots remain byte-identical across arms despite deliberately different deadlines. This verifies parity within the new version, not equality with the former static guidance.

The motivating frozen2 archive contains 17 requested call-only snapshots. The last reported 78 calls remaining, 12.161948 seconds before the recorded Worker timeout event. That does not prove the visibility gap caused the timeout or that the new field would prevent one. Separate oversized agent-written research subprompts remain preserved and unaffected.

Models, budgets, timeout enforcement, scheduling, root history, pinned formatter, strict evaluators, fetch policy and refiner transport are unchanged. No task/site-specific condition, truncation, padding, automatic call or finalization behavior was added. The snapshot can become stale while work proceeds and is not a reservation. Its monotonic-clock semantics do not promise civil wall-time behavior across host sleep.

Review was read-only apart from these evidence files: no source, installation, live calls, raw archives, processes or commits were changed.
