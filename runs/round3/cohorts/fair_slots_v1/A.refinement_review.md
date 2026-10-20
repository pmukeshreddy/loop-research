# A refinement review — failed and superseded

A demonstrated same-run commitment, retrieval/exposure, and subsequent execution consistent with the committed procedures. The worker exited successfully, but the subsequent finalizer failed because its complete input exceeded the provider limit. The cohort is superseded: this remains historical partial proof, not a successful final cohort result or a causal improvement estimate.

Frozen source: `dab5cf89963805d20d3d305ba14d8c8611cd8cf4`. Run: `research-0fd1b020f55e4155989dcd8c40c418f1`. Closed review: 2026-10-20T04:06:47.494779+00:00.

| Event | UTC timestamp | Evidence |
|---|---|---|
| Agent request | 2026-10-20T03:58:04.333798+00:00 | Trace 715 |
| Create memory/15a78c23e69945338281ca26123e25f8 v1 | 2026-10-20T03:59:02.286680+00:00 | Trace 915; commit 5719c140f4c5f7ba1158d4127ca34db16b64ffd7 |
| Create skill/c90b2ce3460a41e1a425275202953430 v1 | 2026-10-20T03:59:02.332375+00:00 | Trace 918; commit abe3028bd3179839add2dee23f888401f825accb |
| First current-run retrieval | 2026-10-20T03:59:02.409590+00:00 | Trace 922 |
| Applied receipt and full entries exposed | After first current-run retrieval | Root model trajectory 93 |
| Matching action starts | 2026-10-20T03:59:16.706188+00:00 | Trace 928; worker trajectory 107, iteration 8 |
| Matching action completes | 2026-10-20T04:00:08.412504+00:00 | Trace 1015; empty stderr |
| Worker exit 0 | 2026-10-20T04:02:43.429958+00:00 | Trace 1854 |
| Finalizer scheduled | 2026-10-20T04:02:44.145436+00:00 | Trace 1863 |
| Finalizer planning discarded | 2026-10-20T04:03:04.892940+00:00 | Trace 1879 |
| Research ends with error | 2026-10-20T04:03:04.917402+00:00 | Trace 1883 |

The request is `538171481177429fba7f4b4ce2507fef`, job `4ee6ad2413434990a893dfa03401829c`. It proposed a memory for exact PDF quote repair and a skill for diagnosing missing biographical fields. Both were accepted; the incomplete output snapshot and 32 stalled-search signals were declined with explicit reasons. The JSON companion preserves both complete edits, candidate inventory, additional candidates, every decision and evidence reference.

The first operation is `refine_15a78c23e69945338281ca26123e25f8`; the second is `refine_c90b2ce3460a41e1a425275202953430`. Apply began at trace 912 (03:59:02.215035 UTC), was recorded applied at trace 919 (03:59:02.332658 UTC), and ended at trace 920 (03:59:02.343897 UTC). Both entries were then marked current_run=true in retrieval 922. Retrievals 1028 (04:00:08.524120), 1082 (04:01:42.800928), 1133 (04:02:13.984954), and 1163 (04:02:33.857801) exposed them again while the worker was active. Root model trajectory records 93, 108, 114, 119, and 123 contain the applied receipt and complete entries. All five retrievals precede worker exit.

The exact-source memory was followed by executed code computing start/end indices in retained `source_2016`, taking `source_2016[start:end]`, asserting exact membership, and replacing row3 affiliation_at_award quotation. The same executed block selected previously discovered alternative URLs for two unresolved nationality cells, fetched those sources, extracted explicit citizenship evidence, and checked nonempty fields and exact quotation membership before replacement. The block also performed semantic completeness review. It completed with empty stderr.

This is evidence of exposure followed by matching action, not a counterfactual improvement estimate. Root response84, while status was planning, had already stated its intention to repair the PDF quote and printed candidate source spans. The skill also formalized source-absence diagnosis begun before commitment. Both new entries had positive BM25 scores (1.5004811557947897 and0.9329797405811842), so this live run does not isolate the zero-overlap retrieval-union case.

Useful research continued while the planner ran: the agent fetched explicit nationality sources, extracted unresolved fields in grouped subcalls, and inspected the stored PDF text. No sleep or polling loop for refinement is observed.

Two source-download failures are retained: fetch request 26, HTTP 403 from the Princeton news URL (trace 820); and fetch request 39, TLS certificate verification failure for the TAP news URL (trace 1105). These are observed source failures, not by themselves product defects. Subsequent research preserved the receipts and used other evidence. No hidden retry or model-rendering fallback is inferred.

The final executed block (worker trajectory 292, iteration 12; trace 1844) completed schema, 28-row coverage, nonempty-cell, exact quotation-membership, and 168 constraint checks before answer_ready. Citation check trace 1858 reports zero uncited cells, and self-check traces 1860/1862 report no issues. These mechanical checks do not establish independent semantic quality and do not override the later run failure.

The finalizer request is `e526f2d58c344551b9af464ae640f659`, job `b07049d849e54bad8ece2a1237c8606d`. It began after worker exit. Its input had 1,592,078 characters against the provider's 1,048,576-character limit. Attempts 0–4 all used identical input and returned zero response characters. Trace 1879 records planning_failed; no finalizer proposal, candidate decisions, edits, or commits exist. In particular, this is a failed plan, not an intentional zero-edit decline. Its archived candidate inventory contains 34 stalled_search occurrences and two failed_fetch occurrences, all retained without invented dispositions.

The complete archived planner prompt has 1,591,896 characters and SHA-256 `d155e19b3e09fa7445ecc6ca1b2de44ebd4154ab4f14ac79bfa7d7734f287e5e`. The frozen backend prepends 182 instruction characters. The resulting complete [failed finalizer input](A.failed_finalizer_input.txt) has SHA-256 `109048b0a26256192448e141ca917146ef77f19078ea9cf3cf72564f37f36564`, verified against every dispatch receipt. Its separate [schema](A.failed_finalizer_schema.json) has 8,959 characters and SHA-256 `ffd3283e4bfe33a41a65207df8717e0bb51325114b47d79f9a06bf5040383542`. [The input manifest](A.failed_finalizer_input_manifest.json) preserves full candidate inventory, null proposal, all five dispatch/result receipts, original job-file hash, and logical/wire representation hashes. No payload was truncated or modified.

The complete structured review is in [A.refinement_review.json](A.refinement_review.json), with all proposals, candidates, retrievals, root boundaries, executed blocks, errors, and terminal events. [The cohort timeline](refinement_timeline.json) is closed as failed/superseded; the original run still records research_status=interrupted. No source, harness, installation, model call, or test was changed or executed for this review.
