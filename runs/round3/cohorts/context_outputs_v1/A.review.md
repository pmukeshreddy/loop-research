A completed naturally on source `9251c8e8925f57cf9fc924e0fd57b1bd0d74bd6d` with **28 rows and 140 required cells**. The read-only archive audit passed. All 140 cells have exact nonempty quotes under every cited URL, no final citation violations, no uncited cells and no self-check issues. This is **not a finding of complete semantic support**: four nationality citations remain unresolved under a strict reading, and Benjamin List’s all-concurrent affiliation scope was narrowed after a semantic finding.

This is the **new `direct-readable-v1` fetch path**. Round2 is a historical identity/value comparator, not an interchangeable fetch experiment or independent ground truth. This review made no model or network calls and changed only new derived reports. [A.review.json](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/context_outputs_v1/A.review.json) contains every cell, full values/quotes, exact offsets, source hashes, errors and receipts. [A.manual.json](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/context_outputs_v1/A.manual.json) binds the `answer-ready-v2` scores. Runtime completion inventory verification covered **239 files**.

The 28 Chemistry laureate/year identities match Round2 after **one explicitly reviewed spelling alias**, `Sir J. Fraser Stoddart` → `Sir Fraser Stoddart`; raw normalized symmetric difference is 2, adjusted difference 0, duplicates 0. There are three recipients each year except two in 2020 and 2021. Exact value-string agreement with Round2 is 120/140: laureate 27/28, year 28/28, nationality 20/28, affiliation 17/28, motivation 28/28. All 20 differences are retained in the JSON. This does not silently treat different nationality sets as equivalent.

| Observed measure | Result |
|---|---:|
| S1 complete executed guard before first `answer["ready"] = True` | 1 |
| S2 gap exposed | 1 |
| S2 distinct successful supplementary URLs after gaps | 28 |
| S3 REPL blocks terminated by quote-validation exceptions | 0 |
| S3 individual printed quote-failure observations | 4 |
| S4 final exact-citation violation cells | 0 |
| Strict cited semantic support, with stated affiliation/nationality scope | 136/140 |
| Strict nationality support unresolved | 4/140 |
| Additional all-concurrent affiliation scope concern | 1 |

At [trajectory.jsonl:103](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/context_outputs_v1/workspaces/A/runs/research-14a1aac50cd9414fb7d4d42011e4e016/289901ce021c28d56fdac993/trajectory.jsonl:103), the submitting code validates the full nested schema, all five required cells in every row, nonempty values/quotes/source lists, and exact quote membership for **every cited URL**. It registers 140 cell plus 28 year constraints, verifies 28 unique identities, and only then sets readiness. Execution at [trajectory.jsonl:273](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/context_outputs_v1/workspaces/A/runs/research-14a1aac50cd9414fb7d4d42011e4e016/289901ce021c28d56fdac993/trajectory.jsonl:273) prints 168 passed constraints; [trace.jsonl:1724](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/context_outputs_v1/workspaces/A/runs/research-14a1aac50cd9414fb7d4d42011e4e016/trace.jsonl:1724) is the first depth-0 ready event. The submitted object equals archived `output.json`. S1 describes an observed guard, not a causal learning benefit.

Iteration 5 printed 25 missing nationality fields and four affiliation quote mismatches: Sauvage, Arnold, Winter and Baker. Those four observations count even though repaired. No exception terminated a block. Subsequent invalid-patch and unresolved-check lists were empty. After exposing gaps, the root fetched 3 HTML repair pages, 17 nationality-source URLs (15 succeeded, 2 returned HTTP 403), then 10 targeted nationality pages: **28 distinct successful supplementary URLs**. The earlier 2015 replacement PDF is excluded because it preceded the exposed gaps. [trajectory.jsonl:37](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/context_outputs_v1/workspaces/A/runs/research-14a1aac50cd9414fb7d4d42011e4e016/289901ce021c28d56fdac993/trajectory.jsonl:37), [trajectory.jsonl:63](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/context_outputs_v1/workspaces/A/runs/research-14a1aac50cd9414fb7d4d42011e4e016/289901ce021c28d56fdac993/trajectory.jsonl:63), [trajectory.jsonl:93](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/context_outputs_v1/workspaces/A/runs/research-14a1aac50cd9414fb7d4d42011e4e016/289901ce021c28d56fdac993/trajectory.jsonl:93).

The semantic qualifications are:

- **Henderson, Goodenough and Yoshino nationality:** their submitted quotes are country tags in Nobel navigation templates on another laureate’s Wikipedia page. These tags do not explicitly label citizenship or nationality. The values may be true; exact quotation alone does not establish the requested field. Henderson also has stronger uncited personal evidence elsewhere in this archive, but that is not silently substituted for his submitted citation.
- **Yekimov nationality:** the cited Lindau field says `Nationality USA/USSR (now Russia)`. The root changed `American; Soviet (now Russian)` to `American; Russian`. The historical USSR distinction and a dated modern-Russian citizenship basis are unresolved. American is supported by the label; the stronger modern dual reading is not established.
- **List affiliation:** the official award release supports Max Planck. The retained biography additionally dates Cologne honorary professorship since 2004 and Hokkaido principal-investigator position since 2018. A semantic subcall raised both omissions; the root explicitly retained only the official award-listed affiliation. Under award-designated scope the cell is supported; under all-concurrent scope it is incomplete. This is preserved as a scope narrowing, not erased by the successful mechanical checks. [trajectory.jsonl:99](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/context_outputs_v1/workspaces/A/runs/research-14a1aac50cd9414fb7d4d42011e4e016/289901ce021c28d56fdac993/trajectory.jsonl:99), [trajectory.jsonl:103](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/context_outputs_v1/workspaces/A/runs/research-14a1aac50cd9414fb7d4d42011e4e016/289901ce021c28d56fdac993/trajectory.jsonl:103).
- **Other limits:** Yekimov’s release lists Nanocrystals and says “Formerly Chief Scientist”; the cell supports an award-listed institution, not active employment. Bawendi’s MIT name is supported but Cambridge/MA/USA is omitted. Lindahl is only Swedish and Bawendi only American here, while Round2 reported additional British and French/Tunisian descriptions; historical model-rendered material is not imported as fresh proof. National descriptors and country labels are not uniformly dated legal citizenship records.

All 28 names, years and motivations were checked in complete official release context, including the distinct 2018 and 2024 prize shares. Award affiliation mappings were read with the PDF columns intact in the retained extraction; incidental interleaved column text inside some exact quotes is preserved, not silently normalized.

| Row | Laureate/year | Exact quote cells | Semantic review |
|---|---|---:|---|
| 1 | Tomas Lindahl (2015) | 5/5 | All five supported within stated scope |
| 2 | Paul Modrich (2015) | 5/5 | All five supported within stated scope |
| 3 | Aziz Sancar (2015) | 5/5 | All five supported within stated scope |
| 4 | Jean-Pierre Sauvage (2016) | 5/5 | All five supported within stated scope |
| 5 | Sir J. Fraser Stoddart (2016) | 5/5 | All five supported within stated scope |
| 6 | Bernard L. Feringa (2016) | 5/5 | All five supported within stated scope |
| 7 | Jacques Dubochet (2017) | 5/5 | All five supported within stated scope |
| 8 | Joachim Frank (2017) | 5/5 | All five supported within stated scope |
| 9 | Richard Henderson (2017) | 5/5 | Nationality citation unresolved; other four supported |
| 10 | Frances H. Arnold (2018) | 5/5 | All five supported within stated scope |
| 11 | George P. Smith (2018) | 5/5 | All five supported within stated scope |
| 12 | Sir Gregory P. Winter (2018) | 5/5 | All five supported within stated scope |
| 13 | John B. Goodenough (2019) | 5/5 | Nationality citation unresolved; other four supported |
| 14 | M. Stanley Whittingham (2019) | 5/5 | All five supported within stated scope |
| 15 | Akira Yoshino (2019) | 5/5 | Nationality citation unresolved; other four supported |
| 16 | Emmanuelle Charpentier (2020) | 5/5 | All five supported within stated scope |
| 17 | Jennifer A. Doudna (2020) | 5/5 | All five supported within stated scope |
| 18 | Benjamin List (2021) | 5/5 | Award-designated affiliation supported; two concurrent posts omitted |
| 19 | David W.C. MacMillan (2021) | 5/5 | All five supported within stated scope |
| 20 | Carolyn R. Bertozzi (2022) | 5/5 | All five supported within stated scope |
| 21 | Morten Meldal (2022) | 5/5 | All five supported within stated scope |
| 22 | K. Barry Sharpless (2022) | 5/5 | All five supported within stated scope |
| 23 | Moungi G. Bawendi (2023) | 5/5 | Supported; American only, MIT location omitted versus Round2 |
| 24 | Louis E. Brus (2023) | 5/5 | All five supported within stated scope |
| 25 | Aleksey Yekimov (2023) | 5/5 | Nationality citation unresolved; other four supported |
| 26 | David Baker (2024) | 5/5 | All five supported within stated scope |
| 27 | Demis Hassabis (2024) | 5/5 | All five supported within stated scope |
| 28 | John Jumper (2024) | 5/5 | All five supported within stated scope |

The archive contains **41 fetch requests: 38 succeeded and 3 failed**. All 41 durable receipts and raw-hop hashes verified. Offline re-extraction of all 38 successful raw responses reproduced the saved readable strings exactly: **9 all-page Poppler-layout PDFs and 29 HTML readable extractions**. There are **8,186,923 raw bytes across 41 distinct raw-hop SHA-256 hashes**. Successful evidence totals **517,615 characters across 38 texts/URLs**, all 38 complete-text hashes distinct; complete-document hash deduplication therefore also totals 517,615 characters. This is not a claim that 517,615 characters are globally unique substrings.

All errors remain counted: trace 180 is the KVA self-redirect loop; trace 619 is Axios HTTP 403; trace 634 is Princeton HTTP 403. Their unsuccessful fetch events and two unsuccessful batch summaries are retained separately (five `success=false` events without an `error` field). No failed body establishes evidence, and no model fallback occurred. There are **3 trace error events, 0 REPL exceptions, 0 model failures, 0 model retries**, plus **29 stalled-search and 3 failed-fetch self-check signals**. Calls total **80: 13 root, 31 search, 34 sub and 2 refine**; all dispatched calls have completion records.

The largest actual research backend root input is **89,936 characters** at iteration 13, trace 1041. Complete nonoverlapping attribution:

| Origin | Characters |
|---|---:|
| system | 3,146 |
| question and columns | 177 |
| other task instructions | 14,521 |
| harness | 3,546 |
| code | 15,149 |
| repl output | 51,979 |
| wrappers | 1,418 |
| Total | 89,936 |

The fetched-text/root maximum ratio is **5.7553704856787045**. Across **all** actual research-root inputs, exact case/whitespace-sensitive 50-character-gram coverage is **45,042 / 517,615 = 8.701834374969813%**. No complete retained page appears intact in any root prompt. This method measures exact textual overlap, not semantic information exposed; printed source snippets and quotes still count. All individual root partitions and measured subcalls are retained in the audit.

The 34 research subcalls use **1,150,467 prompt characters + 23,202 schema characters = 1,173,669 input characters**, or **1,179,857 including backend instruction prefixes**. Individual input sizes range from 8,347 to 189,820 characters. Refinement calls are counted separately and do not inflate these research-subcall totals.

A concrete full-text path is the official 2017 release: **7,712 characters**, SHA-256 `78eba2f0581d0c227833d3de976fa4df03bcc14e049b54afa1cc883e25115ac1`. The complete fetch return at trajectory 8 equals `pages[2]` and `evidence[url]` in trajectory 9, and equals the decoded JSON `text` in the subcall at trajectory 23. That call has 8,609 prompt + 1,636 schema characters (10,427 backend characters), produces three rows, and feeds `extracted` → `candidate_rows`. Twelve of those final cells (all three recipients’ name/year/affiliation/motivation) remain byte-for-byte equal to that subcall’s cells; nationality was repaired later. This establishes full-text availability, exact subcall input and observed result use without claiming the whole page entered the root.

The completed run ended at 15:06:04 UTC; POST_A is `e37fab78867ade934708523fdec324332c893015`. Detailed refinement timing, later retrieval and causal attribution are reviewed separately by the coordinator. This document does not credit a learned entry merely because it was created. [A.audit.json](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/context_outputs_v1/audits/A.audit.json)
