## Completed A and SI: direct-readable-v1

These are the replacement runs on `902abe33d06f64c426a65d55d5e600dd6d6a052a`. Every Round 3 number below uses the **new fetch path**. Round 2 used model-mediated returns; cross-round changes therefore do not isolate learning. Both runs completed naturally. Their archived results, independent full-cell reviews and exact metrics are retained at [A review](A.review.md), [A entry review](A.entry_review.md), [SI review](SI.review.md) and [selected A/SI metrics](selected_metrics_A_SI/metrics.json).

| Measurement | Round 2 A, old fetch | Round 3 A, new fetch | Round 2 SI, old fetch | Round 3 SI, new fetch |
|---|---:|---:|---:|---:|
| Fetched text characters | 12,187 | 900,192 | 1,343 | 68,075 |
| Largest actual root characters | 79,147 | 112,272 | 24,866 | 28,594 |
| Fetched/largest root | 0.154× | 8.018× | 0.054× | 2.381× |
| Exact 50-gram overlap against all roots | 27.316% | 6.770% | 18.690% | 0.601% |
| Rows | 28 | 28 | 5 | 5 |
| Mechanical self-check issues / uncited cells | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| Model attempts | 115 | 102 | 14 | 11 |
| Wall seconds, including finalization | 1,085.890348 | 1,414.330821 | 339.902331 | 181.680589 |
| Failed fetch requests | 21 | 13 | 0 | 0 |

A's identities match after the documented “Sir J. Fraser Stoddart”/“Sir Fraser Stoddart” alias; raw differences remain recorded. SI's five identities and all 15 values match without aliases. No duplicate whole texts inflate these totals: A has 47 retained text instances and 47 distinct whole-text hashes; SI has three and three. Whole-text hash deduplication leaves their respective 900,192 and 68,075 characters unchanged. Distinct archived raw HTTP bodies total 18,120,283 bytes for A and 356,885 for SI, including retained redirect/failure bodies; those are stored body bytes, not wire overhead. Every successful extraction reproduces exactly from its retained raw response, including all ten A PDFs. [Storage counts and hashes](page_storage_counts.A_SI.json).

The root partitions are disjoint and sum to the actual largest backend inputs:

| Component | A characters | SI characters |
|---|---:|---:|
| System | 3,146 | 3,146 |
| Question and columns | 177 | 470 |
| Other task instructions | 15,562 | 8,282 |
| Complete retrieved harness entries | 4,811 | 4 |
| Executed/generated code in history | 24,934 | 4,062 |
| REPL output in history | 61,976 | 11,906 |
| Wrappers | 1,666 | 724 |
| **Total** | **112,272** | **28,594** |

A made 42 actual research subcalls with 806,176 prompt-plus-schema characters (813,820 with backend framing); SI made one with 71,774 (71,956 framed). These were stateless model calls, not child RLMs. Refinement calls are excluded from these counts and included in total cost. A's 324,148-character Stoddart CV was fully present in `source_texts`; code selected an original 1,000-character nationality span for a later subcall. This is agent-directed inspection, not host truncation, padding or an extra fetch to raise the count. SI supplied its three complete page texts to its extraction call. Exact per-call input sizes and result-use evidence remain in [A audit](audits/A.audit.json) and [SI audit](audits/SI.audit.json).

A's mechanical criterion holds, but the independent review supports 139 of 140 listed cell values and leaves Yekimov's “American; Russian” unresolved: “Nationality USA/USSR (now Russia)” does not establish current dual nationality. No established falsehood is claimed. Four separate affiliation-coverage concerns overlap otherwise supported values: Stoddart/Tianjin and Winter/Trinity have dated appointments spanning the award year; Frank/HHMI and Whittingham/NAATBatt are weaker unclosed continuation leads. An official credited institution is supported without proving exhaustive concurrent affiliations. SI's original NIST table independently supports all 15 values, with no unresolved value or affiliation concern. Mechanical citation success is reported separately from semantic completeness. SI's 2.38× size ratio does **not** establish “far exceeds”; no new numeric cutoff is introduced.

A's thirteen failures are three redirect loops, six HTTP 403 responses, one HTTP 404, two TLS verification errors and one broken pipe. The latter lasted 600.0058 seconds and remains recorded as `download_error: [Errno 32] Broken pipe`, not reclassified as a timeout. A also had one terminated quotation-validation block: a Doudna quotation matched one citation but not a second; later code diagnosed it and retained the supporting citation. There were four individual printed quote-failure records. All failures remain counted; there was no model-mediated fallback or model retry. SI had no failed fetch, quote exception or backend retry.

### Same-run delivery in A, and its limit in SI

A requested refinement itself while substantive work remained. The duplicate-reconciliation memory had BM25 score zero, yet the current-run inclusion rule returned its complete committed object. The same seven later actual backend root inputs contained both midtask v1 memories. There were no root blocks spent sleeping or polling for refinement.

| A event | UTC on 2026-10-20 | Trace line |
|---|---|---:|
| Agent requests midtask refinement | 18:05:23.411616 | [778](workspaces/A/runs/research-a685a2c37ca948fa9d7ab1a551451ff2/trace.jsonl:778) |
| Proposal recorded | 18:06:07.285170 | [867](workspaces/A/runs/research-a685a2c37ca948fa9d7ab1a551451ff2/trace.jsonl:867) |
| Exact-span v1 committed, `08e662ec…` | 18:06:35.688619 | [941](workspaces/A/runs/research-a685a2c37ca948fa9d7ab1a551451ff2/trace.jsonl:941) |
| Duplicate memory committed, `b78f2307…` | 18:06:35.730884 | [944](workspaces/A/runs/research-a685a2c37ca948fa9d7ab1a551451ff2/trace.jsonl:944) |
| Later retrieval returns both | 18:06:35.815765 | [948](workspaces/A/runs/research-a685a2c37ca948fa9d7ab1a551451ff2/trace.jsonl:948) |
| Worker completes | 18:09:25.914474 | [1948](workspaces/A/runs/research-a685a2c37ca948fa9d7ab1a551451ff2/trace.jsonl:1948) |
| Finalizer updates exact-span memory to v2 | 18:13:03.606842 | [2003](workspaces/A/runs/research-a685a2c37ca948fa9d7ab1a551451ff2/trace.jsonl:2003) |
| Finalizer commits partial-fetch recovery skill | 18:13:03.653204 | [2006](workspaces/A/runs/research-a685a2c37ca948fa9d7ab1a551451ff2/trace.jsonl:2006) |

After retrieval, iteration 10 (trajectory line 93) prints duplicate counts and a per-source quotation diagnostic. Iteration 11 (line 100) asks for one reconciled record per entity, validates the batch before mutation and restores supported components. This is a verified commit→retrieval→compatible action chain. It is **not isolated causal proof**: quotation guards and targeted Stoddart/Bawendi searches already appeared before the commits. The final v2 changes and recovery skill committed after worker exit and had no A worker reuse. Complete prompt-object comparisons and raw trace links are in [A entry review](A.entry_review.md).

Relative to Round 2 A's zero of eleven later retrievals, Round 3 A has seven of seven later root inputs containing the two new midtask entries. The earlier explicit probe's 24 pause blocks and 985 declared sleep seconds are not repeated by this A. The separately requested **explicit** diagnostic is reported on its own below, rather than substituting this spontaneous chain for that check.

SI requested refinement at 17:51:42.406418 UTC, then finished its worker at 17:51:43.040863. Its memory committed at 17:52:09.282280, 26.241417 seconds after worker exit; all six retrievals preceded the request. Therefore SI's committed same-run reuse is **not demonstrated**. The lesson distinguishes generated finalization code from observed execution, but its rationale's literal “before that block ran” is imprecise: the request occurred inside the executing block. Later checks and submission completed. This was not an actual finalization failure or demonstrated benefit.

### Final lesson accounting

A's midtask proposal accounts for five candidates: two accepted and three declined. Its finalizer accounts for seven: two accepted and five declined. Four edits create two memories, update the exact-span memory and create the fetch skill. The final proposal explicitly preserves historical-nationality uncertainty and distinguishes mechanical quote checks from semantic proof. The fetch-sentinel evidence is concrete: eight actual extraction calls received ten `FETCH_FAILED` source objects. SI accounts for six decisions, one accepted and five declined, with one committed memory; its finalizer made zero edits. A reasoned zero-edit result remains valid.

A's finalizer exercised the complete supplied-context path, with five planner calls and seven refinement subcalls after the one direct midtask call. A whole 2,217,369-character feedback message was retained and replaced by its 855-character receipt before the next backend call. There were zero `repl_output` reads; availability alone is not a read demonstration. The complete supplied logical input, schema, decisions, evidence anchors and commits are verified. The inherited observation selection remains separately qualified and is not described as a globally lossless copy of every worker state.
