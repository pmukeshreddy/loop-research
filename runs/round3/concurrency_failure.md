# Concurrency starvation diagnosis — superseded Round 3 cohort

The frozen backend scheduler admitted later requests while an older B0 search waited until its 600-second concurrency deadline. This is an observed fairness failure in the client-side slot acquisition loop. It is not evidence that the model attempted and failed that search. The preserved old cohort remains superseded; no new run was started for this diagnosis.

Source commit: `9585403c5b78bdac50d89818aba262ff89837fca`. Full evidence, all 25 dispatches in the wait window, all 14 later requests, the active-span reconstruction, complete search span records, and error events are in [concurrency_failure.json](concurrency_failure.json).

## Exact failed request

- Arm: B0-1; run `research-25eb3a4bccde4c03b0b61cce55ded4c9`.
- Query: `Kip S. Thorne physicist nationality citizenship`, `k=4`.
- Request start: trace 332, `2026-10-20T02:59:21.704158+00:00`; cache miss: trace 333 at `02:59:21.704467`.
- Request end: trace 394, `2026-10-20T03:09:21.711503+00:00`; reported monotonic duration **600.0071062920033 seconds**. The timestamp difference is 600.007345 seconds.
- Error: `BudgetExceeded: Deadline while waiting for Codex concurrency slot`.
- Exact expected backend prompt SHA-256: `8794e6cbbfb606f3892686764e9b8040bb5c4ea67d280c91d87d8dfa79a55362`. Matching dispatch traces, durable attempt files, and completed call records: **0, 0, 0**.
- The slot wait begins after the adjacent cache-miss event. There is no explicit queue-entry timestamp in this source, so the internal wait is not separately measured; cache miss to error is an upper bound of 600.007036 seconds. The trace duration measures the enclosing tool call.

## Demonstrated overtaking

A backend `exec.start` is emitted only after a slot is acquired. During the failed request’s interval, 25 backend dispatches occurred: B1 6, B1-frozen-1 9, and B0-1 10. Fourteen hash-matched search requests were themselves started after the failed request and nevertheless dispatched before its timeout: nine in the same B0 process and five in B1. The query-to-dispatch matches use the frozen search template and `INSTRUCTION`, not a fuzzy query match.

| Arm | Later query | Request start UTC | Backend dispatch UTC | Tool-start / dispatch trace lines | Start-to-dispatch seconds |
|---|---|---|---|---:|---:|
| B0-1 | Arthur Ashkin physicist nationality citizenship | 02:59:23.072371 | 02:59:23.073539 | 337 / 339 | 0.001168 |
| B0-1 | Gérard Mourou physicist nationality citizenship | 02:59:34.412342 | 02:59:34.414373 | 343 / 345 | 0.002031 |
| B0-1 | James Peebles physicist nationality citizenship | 03:01:19.154994 | 03:03:17.203332 | 354 / 356 | 118.048338 |
| B0-1 | Michel Mayor physicist nationality citizenship | 03:03:31.183386 | 03:03:31.184811 | 361 / 363 | 0.001425 |
| B0-1 | Donna Strickland physicist nationality citizenship | 03:01:18.863032 | 03:03:32.788144 | 349 / 364 | 133.925112 |
| B1 | J. Michael Kosterlitz physicist nationality citizenship | 03:03:17.203161 | 03:05:15.537787 | 408 / 414 | 118.334626 |
| B1 | F. Duncan M. Haldane physicist nationality citizenship | 03:03:17.203041 | 03:05:20.776571 | 407 / 415 | 123.573530 |
| B0-1 | Reinhard Genzel physicist nationality citizenship | 03:05:27.253333 | 03:05:27.254935 | 378 / 380 | 0.001602 |
| B1 | Barry C. Barish physicist nationality citizenship | 03:05:28.202392 | 03:05:28.204011 | 419 / 421 | 0.001619 |
| B0-1 | Andrea Ghez physicist nationality citizenship | 03:07:20.187506 | 03:07:20.189183 | 384 / 386 | 0.001677 |
| B1 | Rainer Weiss physicist nationality citizenship | 03:03:17.203279 | 03:07:21.991083 | 409 / 424 | 244.787804 |
| B1 | Arthur Ashkin physicist nationality citizenship | 03:07:22.925811 | 03:07:22.927259 | 431 / 433 | 0.001448 |
| B0-1 | Syukuro Manabe physicist nationality citizenship | 03:07:32.201629 | 03:07:32.203241 | 390 / 392 | 0.001612 |
| B0-1 | Roger Penrose physicist nationality citizenship | 03:05:20.777551 | 03:07:33.000162 | 373 / 393 | 132.222611 |

The earliest example is decisive: B0’s Arthur Ashkin request began 1.368213 seconds after the older Kip Thorne request, then reached backend dispatch in 0.001168 seconds. Multiple subsequent requests similarly acquired a just-released slot within a few milliseconds while the older waiter kept polling. This proves loss of arrival-order priority; it does not prove infinite starvation for every workload.

## Source mechanism and alternative causes

`CodexBackend._acquire_slot` (frozen lines 67–86) repeatedly opens numbered slot files, tries each `LOCK_EX | LOCK_NB`, and returns the first available lock. A failed scan sleeps up to 50 ms. No pending-request queue, age, or reservation exists. `complete` calls this before `budget.reserve()`, before the attempt record, and before `exec.start`. The exception therefore cannot be counted as a model attempt or a consumed model-call reservation. The 600-second concurrency limit is distinct from the configured 3,600-second task limit and 300-call budget.

The code permits a newly arriving or finishing thread to claim a released slot before an older sleeper polls again. The later same-process dispatches demonstrate this occurred here. The source establishes a scheduling fairness defect; the logs do not establish which precise OS wakeup sequence caused every lost poll.

Across the three preserved traces, the maximum simultaneous backend execution spans is four, consistent with the configured cap. During the older request’s 600.007345-second wall span, four owned backend spans overlap for **599.737304 seconds**. These are conservative lower bounds on held-slot intervals: acquisition precedes `exec.start` and release follows `exec.end`. Four concurrent owned holders leave no capacity for an additional continuously held external slot in those intervals; this rules out a permanently occupied external slot throughout the episode. Unobserved brief external activity is not ruled out and is not required to explain the observed overtaking.

The separate [preserved pre-stop lsof observation](cohorts/final/slots_before_stop.observed.txt) lists visible open slot-file descriptors only for owned PIDs 47072 (B1) and 47076 (B0-1). It was copied after the stop from tool result `c23c18`, not contemporaneously redirected. `lsof` lists descriptors rather than proving each descriptor held `flock`, and the observation covers that snapshot only. The [stop receipt](cohorts/final/queue_failure_stop.json) records fresh post-stop `lsof` with no descriptors at 03:13:28.888790 UTC and confirms all owned CLIs/coordinator stopped. No lock was deleted or forcibly released during this diagnosis.

B1-frozen-1’s separate provider-capacity response and retry (trace 89–90, 02:48:58 UTC) are retained. Operator-interrupt cancellation errors after 03:11:50 UTC are also retained separately. Neither is silently counted as a successful search or used as an unsupported alternative explanation for the 03:09:21 slot timeout. All three final run manifests say `interrupted`.

## Replay setup recommendation — do not execute until fixed source passes preflight

Use a fresh `runs/round3/cohorts/fair_slots_v1/` directory. Preserve the superseded `final/` directory, original predictions commit `ac93f4788ac0c5374c16181150769ec0333b4a2e`, its [exact preserved copy](cohorts/final/predictions.superseded.md), and [supersession receipt](cohorts/final/predictions.supersession.json). Do not reuse old A/SI output, POST_A, pending B work, caches, or preflight receipts as new-cohort evidence.

The parent’s sequence should be: integrate and commit the reviewed FIFO fix; reinstall that exact source using the previously verified offline noneditable command; run the full offline suite; prepare/execute saved refinement checks and rerun saved archive audits into fresh cohort paths; write new source-bound preflight evidence; perform and record the authorized BASE rollback; only then prepare the cohort. Preserve the exact original configuration and A/SI/B requests by copying the old input bytes, with hashes. A’s recorded baseline remains `2a423027212fe1c430dfd200bdd55f3a27b22d70`; SI’s independent historical baseline remains `0ca9606e11ed1e3c14ee21834cbc6e76b313b90a`. All new harness clones, caches, and run directories must be distinct.

Commands below use the new verified `FIXED_SOURCE` SHA, which does not exist yet at the time of this diagnosis. They are recommendations, not executed actions:

```sh
uv pip install --python .venv/bin/python --no-deps --offline --reinstall .
.venv/bin/python -m pytest -q
.venv/bin/python runs/round2/replay_saved_refine.py --manifest runs/round2/saved_refine_typed_manifest.json --output-root runs/round3/cohorts/fair_slots_v1/saved_refine
.venv/bin/python runs/round2/replay_saved_refine.py --output-root runs/round3/cohorts/fair_slots_v1/saved_refine --execute --expected-source-commit "$FIXED_SOURCE"
cp -R runs/round3/cohorts/final/inputs runs/round3/cohorts/fair_slots_v1/inputs
.venv/bin/python runs/round3/rollback.py --source "$FIXED_SOURCE" --expected-head 2a423027212fe1c430dfd200bdd55f3a27b22d70 --base 2a423027212fe1c430dfd200bdd55f3a27b22d70 --directory runs/round3/cohorts/fair_slots_v1
.venv/bin/python runs/round3/launch.py --directory runs/round3/cohorts/fair_slots_v1 prepare --source "$FIXED_SOURCE"
.venv/bin/python runs/round3/launch.py --directory runs/round3/cohorts/fair_slots_v1 run --phase a_si
```

The install command is the verified command in `runs/round3/install.md`; the failed no-build-isolation invocation in `install.log` must not be reused. The saved-refine commands are the prior recorded commands with a fresh output root and new exact source. The old saved-refine preparation ran 02:29:20.392970–02:29:21.023310 UTC, execution 02:29:30.473330–02:30:30.216648, and the old full suite was 901 passed / 1 live deselected in 108.49 seconds. Those timestamps and counts describe prior evidence only; new evidence must record new commands, statuses, counts, and times. Saved audits can use `runs/round2/audit.py LABEL RUN_PATH --output-dir runs/round3/cohorts/fair_slots_v1/saved_audit` for the same six saved Round 2 archives.

Before `prepare`, the parent must write `fair_slots_v1/preflight.json` with the exact fixed `source_commit`, `all_fixes_complete: true`, a `full_suite` object containing its actual `exit_code: 0`, actual positive `passed` count and hashed `evidence`, plus `saved_refine` and `archive_audit` objects containing actual `status: "passed"` and hashed evidence. Every evidence object is `{path, bytes, sha256}`. Record new completion times; never transplant old status or count fields. The rollback helper creates `fair_slots_v1/rollback.json` itself, including `source_commit`, exact `base_sha`, `harness_head`, and `completed_at`. The expected HEAD shown above was independently read as clean BASE during diagnosis; the parent must stop and diagnose an unexpected current HEAD rather than silently substitute it. Copy inputs only into a new input directory and compare byte hashes.

After the **new** A/SI phase completes, write a **new** `runs/round3/predictions.md` from the new A’s actual complete changed entries, bind its exact new `source_commit` and `POST_A`, save an exact additional copy at `cohorts/fair_slots_v1/predictions.md`, and commit both before any new B launch. The original prediction commit and its preserved `final/predictions.superseded.md` copy remain immutable and do not silently become the new preregistration. The `answer-ready-v2` analysis contract defines the actual first root submission setting `answer["ready"] = True`; select it and any directional S1 prediction only if justified by the new A’s learned entry. The old nonexistent `records.add` S1 remains N/A under the default `records-add-v1` contract. Then invoke the B phase with the new prediction path and commit; use at most the existing three parallel arms / four backend slots, and keep every research arm on the same verified source.

```sh
.venv/bin/python runs/round3/launch.py --directory runs/round3/cohorts/fair_slots_v1 run --phase b --predictions runs/round3/predictions.md --predictions-commit "$NEW_PREDICTIONS_COMMIT"
```

No product code, model input, shared harness, package installation, saved model replay, or new research run was changed or executed by this diagnosis. The later FIFO review and offline tests are recorded separately in [fair_slots_comparison_review.json](fair_slots_comparison_review.json).
