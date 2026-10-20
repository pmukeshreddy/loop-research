## Every main run: new fetch path

All sizes are characters unless labeled bytes. Root sizes are actual largest research backend inputs; overlap uses exact case/whitespace-sensitive 50-character grams against all research roots. Source text counts exclude failed returns. Same identities are checked against Round 2 after documented aliases, with raw differences preserved.

| Run | Readable chars | Largest root | Ratio | Overlap | Rows / issues / uncited | Attempts | Wall seconds | Failed fetches |
|---|---:|---:|---:|---:|---|---:|---:|---:|
| A | 900,192 | 112,272 | 8.0180× | 6.7700% | 28 / 0 / 0 | 102 | 1414.330821 | 13 |
| SI | 68,075 | 28,594 | 2.3807× | 0.6008% | 5 / 0 / 0 | 11 | 181.680589 | 0 |
| B1 | 921,760 | 175,270 | 5.2591× | 0.7385% | 28 / 0 / 0 | 165 | 2616.339354 | 6 |
| B0-1 | 1,305,812 | 86,610 | 15.0769× | 2.1342% | 28 / 0 / 0 | 139 | 1047.978328 | 4 |
| B0-2 | 1,249,347 | 82,507 | 15.1423× | 0.7548% | 28 / 0 / 0 | 80 | 684.788533 | 5 |
| B0-3 | 1,651,962 | 86,409 | 19.1179× | 0.7823% | 28 / 0 / 0 | 134 | 930.618448 | 5 |
| B1-frozen-1 | 1,068,214 | 107,675 | 9.9207× | 0.1439% | 28 / 0 / 0 | 83 | 961.929480 | 4 |
| B1-frozen-2 | 945,540 | 103,207 | 9.1616× | 0.0420% | 28 / 0 / 0 | 86 | 806.307491 | 2 |
| B1-frozen-3 | 1,293,190 | 127,186 | 10.1677× | 0.1269% | 28 / 0 / 0 | 103 | 1530.249356 | 21 |

All runs have zero model retries. The single failed oversized research subcall in frozen1 remains in attempt counts; successful subcall input aggregates below exclude that failed result and are supplemented by its exact failed-input ledger.

| Run | Successful research subcalls | Logical input total | Backend input total | Stored raw body bytes | Text instances / whole hashes | Whole-hash-deduplicated chars |
|---|---:|---:|---:|---:|---:|---:|
| A | 42 | 806,176 | 813,820 | 18,120,283 | 47 / 47 | 900,192 |
| SI | 1 | 71,774 | 71,956 | 356,885 | 3 / 3 | 68,075 |
| B1 | 47 | 2,762,244 | 2,770,798 | 15,554,147 | 86 / 86 | 921,760 |
| B0-1 | 73 | 1,824,730 | 1,838,016 | 19,671,181 | 91 / 91 | 1,305,812 |
| B0-2 | 23 | 1,761,625 | 1,765,811 | 25,465,392 | 58 / 58 | 1,249,347 |
| B0-3 | 69 | 3,475,639 | 3,488,197 | 33,735,708 | 95 / 95 | 1,651,962 |
| B1-frozen-1 | 33 | 2,607,292 | 2,613,298 | 22,253,050 | 62 / 62 | 1,068,214 |
| B1-frozen-2 | 35 | 2,530,706 | 2,537,076 | 22,854,754 | 65 / 65 | 945,540 |
| B1-frozen-3 | 52 | 3,327,390 | 3,336,854 | 19,849,593 | 77 / 75 | 1,281,786 |

Raw bytes are distinct stored HTTP response bodies, including available failure/redirect bodies, not wire overhead. Whole-text hashing removes identical complete strings across URLs; it does not remove repeated page fragments or claim global informational uniqueness. The explicit child diagnostic is separate from these nine runs.

### Largest actual root input partitions

| Run | System | Question / columns | Other task instructions | Complete harness entries | Code | REPL output | Wrappers | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 3,146 | 177 | 15,562 | 4,811 | 24,934 | 61,976 | 1,666 | 112,272 |
| SI | 3,146 | 470 | 8,282 | 4 | 4,062 | 11,906 | 724 | 28,594 |
| B1 | 3,146 | 175 | 16,374 | 45,061 | 32,962 | 75,884 | 1,668 | 175,270 |
| B0-1 | 3,146 | 175 | 7,423 | 1,986 | 16,138 | 56,099 | 1,643 | 86,610 |
| B0-2 | 3,146 | 175 | 7,423 | 1,986 | 14,879 | 53,424 | 1,474 | 82,507 |
| B0-3 | 3,146 | 175 | 7,423 | 1,986 | 20,534 | 51,588 | 1,557 | 86,409 |
| B1-frozen-1 | 3,146 | 175 | 7,423 | 34,226 | 19,340 | 42,058 | 1,307 | 107,675 |
| B1-frozen-2 | 3,146 | 175 | 7,423 | 34,226 | 21,039 | 35,890 | 1,308 | 103,207 |
| B1-frozen-3 | 3,146 | 175 | 7,423 | 34,226 | 29,700 | 51,042 | 1,474 | 127,186 |

The seven partitions are disjoint and sum exactly. Complete per-call logical/schema/backend sizes, source hashes and code/result-use bindings are in [the final metrics](final_metrics/metrics.json) and the linked per-run audits. Ordinary research subcalls are stateless; the separate explicit run demonstrates an actual nested RLM.
