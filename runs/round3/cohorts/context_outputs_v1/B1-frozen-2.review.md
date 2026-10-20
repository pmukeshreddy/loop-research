# B1-frozen-2: failed, superseded historical preservation

B1-frozen-2 **failed naturally at the task deadline**; it did not deliver an answer. The launcher records CLI exit 1 at 2026-10-20T16:36:59.272322+00:00, on frozen source `9251c8e8925f57cf9fc924e0fd57b1bd0d74bd6d` and POST_A `e37fab78867ade934708523fdec324332c893015`. Run `research-d34b080d45ab4d4da1a026a2ecc21e39` was resolved from its original CLI announcement. `research.json` has terminal `status="complete"` together with `error="TimeoutError: Task hard deadline exceeded"`; the launcher correctly rejects that as a successful run. No `output.json` or `agent_result.json` exists. Self-check reports `empty_output` and `timeout`. This entire cohort is superseded; these are historical findings, excluded from final comparison claims.

The [automatic audit](audits/B1-frozen-2.audit.json) passed archive accounting ([log](B1-frozen-2.review_audit.log)), which does not convert the research into a success. All **818 original archive files** match the launcher's [hash manifest](B1-frozen-2.archive_hashes.json). Its `source_unchanged` flag is absent because completion validation failed; the report preserves that absence. A separate current `src` comparison against the recorded launch commit found no differences. Full launch identity, source/artifact hashes and error events are in [review JSON](B1-frozen-2.review.json).

The worker ran from 15:36:58.458365 to 16:36:58.447899 UTC (trace14/3055): 3,599.989534 seconds. Clipping nonoverlapping spans to that interval yields 495.186707 seconds in root-model spans, 3,103.148874 in REPL spans and 1.653953 between those spans. Inside the REPL, twelve search batches took 873.883739 seconds, twelve fetch batches 1,395.473699, and seventeen top-level structured-query operations 723.425966; the remaining 110.365470 seconds is other REPL time. These are elapsed spans, not sums of concurrent individual backend times. The [timing JSON](B1-frozen-2.budget_timeline.json) retains every paired interval.

Two Washington Post downloads failed with Broken pipe after 600.017433 and 600.007138 seconds (trace 1679–1691 and 2057–2090). A CNRS download failed after 75.138295 seconds (1368–1415). Overall there were 191 direct requests, 158 successful retained texts and 33 failed fetches. These are observed download failures; this archive does not establish an OS, cancellation or scheduling malfunction.

The agent executed seventeen `budget()` calls. Every response had only `limit`, `reserved` and `remaining` call counts. The initial context exposed the static 3,600-second task limit. `CallBudget` already holds the authoritative monotonic deadline (`codex_backend.py:92–101`), but `snapshot()` omits remaining time (`:109–112`); `Session._state_dispatch` forwards that snapshot (`session.py:209–216`), and `resource_policy` documents call counts (`agent.py:102–112`). No explicit clock/elapsed-time measurement occurs in the seventeen executed blocks. Python could support such measurement, so this is a missing requested status field, not absolute inability to read a clock.

| Trajectory line | Trace RPC lines | RPC end UTC | Reserved calls | Remaining calls | Seconds until observed timeout |
|---:|---:|---|---:|---:|---:|
| 2 | 36–37 | 15:37:03.526750 | 1 | 299 | 3594.921149 |
| 5 | 60–61 | 15:37:14.400439 | 2 | 298 | 3584.047460 |
| 10 | 202–203 | 15:38:28.859207 | 13 | 287 | 3509.588692 |
| 34 | 368–369 | 15:40:41.676872 | 33 | 267 | 3376.771027 |
| 58 | 529–530 | 15:42:49.294495 | 45 | 255 | 3249.153404 |
| 89 | 1081–1082 | 15:47:01.192050 | 72 | 228 | 2997.255849 |
| 99 | 1137–1138 | 15:48:10.499234 | 80 | 220 | 2927.948665 |
| 127 | 1537–1538 | 15:53:45.507216 | 104 | 196 | 2592.940683 |
| 144 | 1769–1770 | 16:06:20.815955 | 117 | 183 | 1837.631944 |
| 161 | 2007–2008 | 16:10:52.753331 | 130 | 170 | 1565.694568 |
| 175 | 2152–2153 | 16:22:28.326210 | 140 | 160 | 870.121689 |
| 188 | 2226–2227 | 16:23:52.626795 | 151 | 149 | 785.821104 |
| 201 | 2348–2349 | 16:25:22.917376 | 160 | 140 | 695.530523 |
| 216 | 2474–2475 | 16:27:54.390852 | 171 | 129 | 544.057047 |
| 232 | 2632–2633 | 16:30:20.554383 | 183 | 117 | 397.893516 |
| 258 | 2809–2810 | 16:33:57.680991 | 205 | 95 | 180.766908 |
| 279 | 3017–3018 | 16:36:46.285951 | 222 | 78 | 12.161948 |

The last column is retrospective subtraction from the observed worker timeout; it was **not returned to the agent**. The final printed snapshot reported 78 calls left only 12.161948 seconds before timeout. A narrow correction is supported: include finite nonnegative `seconds_remaining` from the existing deadline in explicit snapshots, while preserving budgets, retries, scheduling and agent choice. This does not prove the run would succeed with that field.

The final operation also failed independently of the remaining-time gap. REPL 17 selected all retained documents containing each surname and assembled five broad structured prompts (trajectory 282, code SHA`23f50c111760065d648c10baffe34c024dd52f5406e8fba417fb50e3cc254107`). Four entered the backend; two succeeded and two were rejected as `input_too_large` at 2,127,326 and 1,456,368 characters versus 1,048,576 (Codex log 223–224, trace 3028/3031). Each rejected prompt was attempted once, with no retry. The fifth has no backend attempt after batch abort. Their full original strings remain in the archived REPL locals, and [reconstruction receipts](B1-frozen-2.final_subcalls.json) match exact backend prompt hashes. The batch failure reached REPL stderr at trace 3040. Root 18 began at 16:36:58.265067 with about 0.178 seconds admitted timeout; worker deadline fired at 16:36:58.447899, followed by backend timeout, `BudgetExceeded` and self-check failure (trace 3054–3060). All 227 backend attempts are retained: 224 successes, two permanent input failures and one terminal root timeout; zero retries.

A read-only control scan found three accepted historical PDF extractions with forbidden Unicode Cc characters: GFDL Fall 2021 Bulletin 265, UNN 2019 book 68, and Wadham 2021 Gazette 293 (626 total). Their complete control distributions, text/receipt paths and hashes are in the JSON. This is the same extraction-quality defect that already superseded the cohort, not a new repaired result. Retained text totals 4,755,487 characters across 158 texts; the largest recorded root input is 210,781 characters (ratio 22.5612697539152). The auditor cannot verify every failed final root body, so all-root 50-character-gram overlap is explicitly **N/A**, not zero.

There are 44 trace error events, including propagation of the same errors across layers; this is not 44 independent failures. The JSON preserves them all. No full manual semantic or benefit scoring was performed under the reduced scope. All original archives remain unchanged; only derived reports outside the workspace were added.
