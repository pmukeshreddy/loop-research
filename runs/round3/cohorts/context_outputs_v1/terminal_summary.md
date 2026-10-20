# Superseded context-output cohort: terminal outcomes

These are historical **new-fetch-path** results, excluded from the final Round3 comparison. Nominal text counts include corrupt extractions; they are not full-readable-page proof. The one-hour failure and quote violations remain failures. No successful six-run comparison is claimed.

| Arm | Terminal status | Rows | Mechanical issues | Uncited cells | Model attempts | Retries | Elapsed seconds | Nominal extracted chars | Largest root chars |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|
| A | complete | 28 | {} | 0 | 80 | 0 | 639.876394 | 517615 | 89936 |
| SI | complete | 5 | {} | 0 | 13 | 0 | 210.129273 | 68075 | 31139 |
| B1 | complete | 28 | {"fabricated_quote": 6} | 0 | 131 | 0 | 2667.24058 | 1939530 | 154553 |
| B1-frozen-1 | complete | 28 | {"fabricated_quote": 27} | 0 | 199 | 0 | 2998.523681 | 6133337 | 204407 |
| B0-1 | complete | 28 | {} | 0 | 75 | 0 | 1617.838533 | 872468 | 84523 |
| B1-frozen-2 | failed | N/A | {"empty_output": 1, "timeout": 1} | N/A | 227 | 0 | 3600.6041 | 4755487 | 210781 |
| B0-2 | complete | 28 | {} | 0 | 79 | 0 | 645.140366 | 1264853 | 63334 |
| B1-frozen-3 | complete | 28 | {"fabricated_quote": 27} | 0 | 159 | 0 | 5338.822899 | 3702884 | 204057 |
| B0-3 | complete | 28 | {} | 0 | 87 | 0 | 765.31373 | 763954 | 85652 |

All six initial prompts were byte-identical within arm and differed only in complete entry objects across arms, with matching dates. The completed-five integrity audit passed; the standard six-control audit correctly rejected frozen2. That narrower input finding does not turn the failed run into a completed comparison.

Frozen3 elapsed time includes the recorded clamshell period. The existing task monotonic clock and all limits remained unchanged. Full semantic and entry-specific manual metrics were not completed for this excluded cohort; they will be reported for every replacement run. This exclusion was recorded before the remaining old arms finished.

See `terminal_summary.json`, `superseded.json`, `six_initial_inputs.json`, `control_audit.partial.json`, each review, and the exact historical predictions copy.
