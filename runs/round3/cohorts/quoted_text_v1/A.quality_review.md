# A quality review — failed before submission

Run `research-f43c96b33c5d43b299e491341eb65216`, on runtime source `09c77902babb879abe2b0dcc8cab7cf5209bf5ae`, ended naturally with a refiner input-limit failure. Its research record says `interrupted`; the launcher records `failed`, exit 1. This is not evidence of an operator interruption. There is **no `output.json`, no root readiness event and no completed final answer**. Final 140-cell semantic quality, final identity equivalence and the S1 submission guard are **unavailable**, not zero or success. No POST_A, predictions or B comparison is assigned.

The refiner prompt was rejected once at [trace 1165](workspaces/A/runs/research-f43c96b33c5d43b299e491341eb65216/trace.jsonl:1165): 1,611,089 characters exceeded the provider's 1,048,576-character limit. The research failure propagated at [trace 1204](workspaces/A/runs/research-f43c96b33c5d43b299e491341eb65216/trace.jsonl:1204), 04:44:31.651745 UTC, after 938.922 seconds. There was one refiner dispatch and no retry of this permanent rejection. The separate refinement timeline is owned by the other reviewer.

[The JSON review](A.quality_review.json) preserves the terminal record, every error event, all partial cell checks, exact raw/text receipt checks, complete root-size attribution and subcall measurements. [The manual metrics](A.manual_metrics.json) use `answer-ready-v2` and explicitly label this as a failed-cohort descriptive review. The archive auditor's `available` status means the evidence is archived; it does not mean the research succeeded.

## Partial rows are not a final answer

The last executed block, [trajectory 81](workspaces/A/runs/research-f43c96b33c5d43b299e491341eb65216/289901ce021c28d56fdac993/trajectory.jsonl:81), leaves `answer` empty and `ready=False`. Its locals contain 28 partial rows and 140 nonempty required cells. All 140 partial cells have an exact nonempty quotation in the retained original text for **every** cited URL. This mechanical diagnostic does not establish semantic correctness or submission.

The partial laureate/year set matches the 28 Round 2 identities after one explicitly documented alias: `Sir J. Fraser Stoddart` versus `Sir Fraser Stoddart`, the same 2016 laureate associated with Northwestern in the cited Nobel page. The raw key-set symmetric difference contains those two spellings; it is not silently normalized to equality. No final identity score is assigned.

The archived semantic-review subcall identifies unresolved points that the root had not repaired when the run failed. Inspection of the partial values and their exact quoted text confirms:

- Lindahl's affiliation value omits **Cancer Research UK**, which the quoted PDF passage names with Clare Hall Laboratory.
- Yekimov's `American; Russian` is stronger than the historical label `Nationality USA/USSR (now Russia)`. That wording does not establish a concurrent, dated citizenship set.
- Whittingham's `British-American chemist` and Frank's `Nationality Germany/USA` support descriptive nationality labels, without independently proving dated legal dual citizenship.

These are known partial-output qualifications, not a comprehensive final semantic review. The model's statement that all motivations appear correct is retained as model output and is not substituted for an independent final review.

## Observed manual measures

| Measure | Failed-run observation |
|---|---:|
| S1 full-cell guard before actual readiness assignment | N/A: no submission |
| S2 required-field gap exposed | 1 |
| S2 successful distinct supplementary URLs | 75 |
| S3 REPL blocks terminated by a quote exception | 0 |
| S3 individual caught/printed quote-failure records | 0 |

The initial extraction printed **25 missing nationality cells** at [trajectory 34](workspaces/A/runs/research-f43c96b33c5d43b299e491341eb65216/289901ce021c28d56fdac993/trajectory.jsonl:34). Subsequent gap-directed work fetched nine official PDFs and 66 successful distinct biography URLs; nine other biography requests failed. The 75 successful URLs and their request IDs are listed individually in JSON. Initial fetches and failed supplementary fetches are excluded from that count.

All ten executed root REPL blocks have empty stderr and no trace error. The printed `quote_errors` lists at iterations 5 and 9 are empty; the 2015 quotation assertions and later `assert not nat_errors` complete without failure. There are no printed individual quote-failure records to count. These observations cover executed blocks before termination and do not imply a successful full submission guard.

## Full-page evidence use and root exposure

A concrete example is the **7,419-character 2016 Nobel press release**. Iteration 4 stores the complete text in `pages[1]`; its hash is `62fc079e56e0421b4e156cb66c3f3c45cd4f06bad20abb7b47d31d5a4da08f1e`. The JSON evidence in the [subcall at trajectory 24](workspaces/A/runs/research-f43c96b33c5d43b299e491341eb65216/289901ce021c28d56fdac993/trajectory.jsonl:24) contains that exact full text. Its prompt is 8,253 characters, schema 1,636, and combined backend input 10,071 including the 182-character prefix. The returned three-row object equals `extracted[0]`; the executed flattening at trajectory 34 uses all three rows in `rows`. The initially empty nationality fields lead to the subsequent gap-directed research. This proves actual full-page extraction and partial-result use, not final submission.

The retained text sum is **1,395,914 characters across 84 URL/text variants**; this is not an unqualified claim of globally unique content. The largest verified backend root input is **56,124 characters**, in iteration 10, giving a retained-text/largest-root ratio of **24.872**. Its nonoverlapping partition is:

| Component | Characters |
|---|---:|
| System, including backend prefix | 3,146 |
| Question and columns | 177 |
| Other task instructions and current refinement status | 8,617 |
| Initial/current harness payloads | 1,986 |
| Earlier REPL code | 7,380 |
| Formatted REPL output | 33,652 |
| Wrappers and reminders | 1,166 |
| Total | 56,124 |

Across all ten root inputs, the frozen auditor's exact, case-sensitive 50-character-gram method covers **5,725 / 1,395,914 characters (0.4101%)** of the retained texts. No retained text is fully present in those roots. This metric measures exact overlap, not semantic exposure. All 16 subcall input/prompt/schema/backend sizes and the full root records remain in JSON.

## Errors and receipt preservation

All **19 trace error events** remain in the review: ten direct-fetch errors and nine occurrences of the propagated refiner failure. The ten fetch failures comprise five HTTP 403 responses, one HTTP 401, three redirect-loop failures and one download error recorded as `Broken pipe`. HTTP failures have no model fallback. No different underlying cause is inferred for the download error.

All 94 direct-fetch receipts verify, including 84 successful and ten failed requests; every recorded raw-download/text file was independently rehashed against its receipt. The final self-check records `empty_output`, 35 stalled-search signals and ten failed-fetch signals. Backend dispatches total 63: ten root, 36 search, 16 sub and one refine.

This review made no model or web calls, installed nothing, changed no source/runtime helper/original archive/harness, and committed nothing. A complete fresh run is still required for final quality and the planned comparison.
