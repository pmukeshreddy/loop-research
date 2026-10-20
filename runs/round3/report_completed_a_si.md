# Completed A and SI evidence for the final Round 3 section

This is historical drafting material from the superseded context_outputs_v1 cohort, excluded from the final comparison after its extraction-quality defect was established. Individual completed archive findings are retained, not promoted to the replacement cohort. All values use the **new `direct-readable-v1` fetch path**. The fixed runtime source is `9251c8e8925f57cf9fc924e0fd57b1bd0d74bd6d`.

| Measure | A, Chemistry | SI generalization |
|---|---:|---:|
| Output rows / required cells | 28 / 140 | 5 / 15 |
| Self-check issues / uncited cells / final quote violations | 0 / 0 / 0 | 0 / 0 / 0 |
| Raw / reviewed identity symmetric difference from Round 2 | 2 / 0 | 0 / 0 |
| Successful URLs / distinct complete-text hashes | 38 / 38 | 3 / 3 |
| Retained readable characters | 517,615 | 68,075 |
| Largest actual root prompt characters | 89,936 | 31,139 |
| Page/root ratio | 5.755370486 | 2.186165259 |
| Exact 50-character-gram overlap against all roots | 8.701834375% | 0.600807932% |
| Complete pages appearing intact in a root | 0 | 0 |
| Model calls: root / search / sub / refine | 13 / 31 / 34 / 2 | 6 / 3 / 2 / 2 |
| Total model calls / retries | 80 / 0 | 13 / 0 |
| Fetch requests / failed requests | 41 / 3 | 4 / 0 |
| REPL error blocks | 0 | 0 |
| Wall seconds | 639.876394 | 210.129273 |
| Complete pre-readiness guard (S1) | 1 | 1 |
| Missing-field exposure / successful supplementary URLs (S2) | 1 / 28 | 0 / 0; conditional N/A |
| Terminating quote exceptions / printed quote failures (S3) | 0 / 4 | 0 / 0 |

[All metrics and event-level derivations](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/context_outputs_v1/metrics/a_si/metrics.json), [A review](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/context_outputs_v1/A.review.md), [SI review](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/context_outputs_v1/SI.review.md). A's sole identity alias is the documented spelling `Sir J. Fraser Stoddart` → `Sir Fraser Stoddart`; no nationality sets or other values were silently equated.

All saved successful response bodies independently reproduce their complete readable strings: A has nine all-page PDF extractions and 29 HTML extractions; SI has three HTML extractions and one focus-changed cache hit. A's 41 receipts contain 8,186,923 raw bytes across 41 distinct raw-hop hashes. Its three failures are the KVA self-redirect loop, Axios HTTP403 and Princeton HTTP403. Those failures, five unsuccessful fetch/batch summary events, and 29 stalled-search signals remain counted. SI has zero errors and two stalled-search signals. Neither identical-text deduplication nor an extra fetch inflates these totals; SI explicitly requests individual/batched tool and cache demonstrations.

The full-text research path is concrete: A's official 2017 release is 7,712 characters, SHA256 `78eba2f0581d0c227833d3de976fa4df03bcc14e049b54afa1cc883e25115ac1`. The returned string equals `pages[2]` and `evidence[url]`, then the decoded `text` in the actual subcall. That call takes 8,609 prompt plus 1,636 schema characters (10,427 including backend framing), returns three rows, and supplies 12 unchanged final cells. A's 34 research subcalls total 1,173,669 prompt-plus-schema characters; individual inputs range 8,347–189,820. SI's first extraction takes all three full texts, 70,597 prompt plus 1,129 schema characters, and returns the actual final table. Its separate 3,399-character review subcall receives the quoted rows and is acted on. These are research calls; refinement calls do not inflate the totals.

Largest-root partitions, with no double counting, are:

| Origin | A | SI |
|---|---:|---:|
| System | 3,146 | 3,146 |
| Question and columns | 177 | 470 |
| Other task instructions | 14,521 | 8,625 |
| Complete harness entries | 3,546 | 4 |
| Executed code | 15,149 | 5,374 |
| Formatted REPL outputs | 51,979 | 12,686 |
| Wrappers | 1,418 | 834 |
| Total | 89,936 | 31,139 |

The mechanical zeros do **not** establish complete semantic quality in A. Only 136/140 cells have strict cited support. Henderson, Goodenough and Yoshino nationality quotes are unlabeled country tags in another laureate's navigation template; Yekimov's `USA/USSR (now Russia)` label was strengthened to `American; Russian` without resolving its historical distinction. The values are not all established false; their submitted citations do not justify the stronger readings. A also leaves List's concurrent Cologne/Hokkaido affiliations unresolved after a subcall raises them, choosing the award-listed Max Planck affiliation instead. SI's 15 cells are independently supported by the retained NIST table. Its ratio of 2.19 is not described as “far exceeds.” Therefore neither a large A ratio alone nor clean SI cells alone proves the full size/overlap/quality conjunction.

For spontaneous same-run delivery, A requests refinement at trace356, keeps working in iteration6, commits skill `a3ae0f09db864545b6322e57285e5c5a` v1 at trace513 (`19e87280306e24df3b40597ac43974799090a2a5`), and retrieves the complete new entry at trace517. Actual backend trajectory50 establishes root exposure. Seven later retrievals contain it; the commit is 241.051837 seconds before worker exit. There are 13 executed root blocks, one `refine.run`, zero sleeps and zero status polls. Iteration7 selects saved hits and fetches quote/nationality repairs; iteration8 validates 31 grouped patches with zero invalid patches. These match the lesson, but the root had already diagnosed the gaps and started the same repair strategy before commitment. Thus delivery works, while an entry-induced behavioral decision is **not demonstrated** by A alone. Its positive relevance score also does not isolate the zero-score union regression. [Exact request→commit→retrieval→action evidence](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/context_outputs_v1/A.refinement_review.md).

A's mid-task proposal has five decisions (two accepted sharing one edit, three declined). Finalization after worker exit has four decisions (two accepted/two declined) and two edits: the updated discovery memory and new semantic-reconciliation memory. Those later edits cannot explain A's earlier work. All nine candidates and three edits retain strict schema/evidence/accounting checks. SI's mid-task request commits only after readiness: trace209 request, trace316 ready, trace340 commit. Its seven retrievals all precede commitment, so same-run reuse is not demonstrated there. Its finalizer declines all three candidates without an edit. A valid zero-edit result is completion, not a hung planner.

The historical Boolean-verdict memory `25c641be4308494f907cb85b2691901a` is absent from BASE and the fresh A/SI lineage. Correct Boolean calls do not demonstrate use of that memory. Original check3 remains **not exercised**; the separate explicit diagnostic must not be substituted for historical-memory evidence.
