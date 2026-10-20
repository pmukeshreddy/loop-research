# Failed saved-input preflight — no research launched

This directory is preserved and excluded from the final Round 3 comparisons. Its source is `42424491009371cc7063c2a88394e92c97e974a7`. The full offline suite passed 1,027 tests with one live test deselected; 59 separate launcher/metric checks and nine saved archive audits passed. All 31 installed Python modules matched that source. The five real saved-input replays did **not** pass as a group. A, SI and B research were never launched from this directory, and no predictions or learned state from these replay clones may seed them.

The replay began at 05:15:03 UTC on October 20. The Mac entered **Clamshell Sleep** at 01:15:19 EDT (05:15:19 UTC), then repeatedly performed brief maintenance wakes. The recorded lid/user wake was 04:26:29 EDT (08:26:29 UTC). The selected original `pmset` lines remain in `host_sleep_wake.log`; `host_sleep_events.log` selects the sleep/wake event lines without rewriting the original capture. This is evidence of host suspension and network interruption, not evidence that the model took hours of active computation.

| Saved case | Result | Model attempts | Retries | Failed attempts | Applied commits |
|---|---|---:|---:|---:|---:|
| B1_finalizer | complete after retry | 2 | 1 | 1 | 2 |
| SI_midtask | complete after retry | 2 | 1 | 1 | 1 |
| B1_fragments_finalizer | complete after retry | 2 | 1 | 1 | 2 |
| A_full_pages_finalizer | complete after retry | 2 | 1 | 1 | 2 |
| A_distinct_pages_midtask | failed | 1 | 0 | 1 | 0 |

Each direct case's first attempt recorded a 600-second timeout and DNS/connection errors. The overflow worker successfully started, read the full original snapshot, and requested its first 4,926-character coordinator input. With five cases admitted against four shared backend slots, it spent nearly all of its aggregate 600-second active-time deadline waiting behind the direct cases. Its first dispatch followed the first direct recorded completion by about 46 milliseconds: this is consistent with prompt FIFO admission and does not show starvation. The exact slot-release instant is not separately archived. It executed no planner code or subcall. That attempt recorded `PermissionError`, and the operation ended with its aggregate deadline error. No original input was dropped and no proposal was fabricated.

The archived error has no exception traceback that would distinguish process creation from cleanup. A separate local-process-only reproduction nevertheless established a real cleanup race in the same source: timeout and cancellation both called `stop()` before `finished` became true; after the first group kill succeeded, the second kill raised `PermissionError` on this Mac. Three instrumented repetitions preserve both thread events and complete callback stacks in `saved_refine_local_cancel_probe.json`. This independently justifies a general cleanup fix; it does not retrospectively prove the throwing line of the archived model attempt.

Corrections are separate: bound outer saved-case admission to the configured shared capacity (without changing any planner deadline or agent timing), fix duplicate process-group cleanup, then rerun all five original saved inputs in fresh independent clones on the final common code. The next cohort is `context_refiner_awake_v1`. Its live coordinators use `/usr/bin/caffeinate -i`; a local probe verified the idle-sleep assertion and its release after command completion. This does **not** override lid closure, explicit sleep, shutdown, or network failure. The host must remain awake with the lid open. Neither increased budgets nor hidden retries are used to compensate for suspension.

All saved replay files are bound by `failed_preflight_archive_hashes.json`; original inputs, generated proposals, failures, retry records, transport archives and clone histories remain on disk. The root proof report and old predictions remain unchanged.
