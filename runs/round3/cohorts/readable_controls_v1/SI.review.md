# Fresh SI review — readable_controls_v1

The run completed naturally, and all 15 required cells are supported by the retained official NIST evidence. The automatic archive audit passes. This run requested refinement during the task, but its sole edit committed after the worker exited: it does **not** demonstrate same-run committed-entry retrieval or benefit.

Source: `902abe33d06f64c426a65d55d5e600dd6d6a052a`. Run: `research-215ac89bf8fc46ebadb8af0a8d47dfee`; task: `1109eb057f25ad2429b6e77e`. The exact run was resolved from the `Watch live` path and final `Archive` line in [SI.console.log](SI.console.log). [research.json](workspaces/SI/runs/research-215ac89bf8fc46ebadb8af0a8d47dfee/research.json) is complete without an error; the final trace event is at `2026-10-20T17:52:31.051008+00:00`. All 49 files, totaling 3,352,832 bytes, match the complete [archive inventory](SI.archive_hashes.json).

The [full review JSON](SI.review.json) retains per-cell checks, raw/readable artifact hashes, both full proposals, every candidate disposition, exact timeline events, commit verification, and limitations. [SI.manual.json](SI.manual.json) supplies the five required `answer-ready-v2` metrics and independent semantic counts. Its evidence paths, hashes, line numbers, and submission boundary were validated using the existing metrics helper.

The [output](workspaces/SI/runs/research-215ac89bf8fc46ebadb8af0a8d47dfee/1109eb057f25ad2429b6e77e/output.json) has exactly the same five quantity identities and all 15 values as the saved Round2 SI output, with no alias adjustment:

| Quantity | Unit | Symbol | Exact retained quotation for all three cells |
| --- | --- | --- | --- |
| length | meter | m | `length\nmeter\nm` |
| mass | kilogram | kg | `mass\nkilogram\nkg` |
| time | second | s | `time\nsecond\ns` |
| electric current | ampere | A | `electric current\nampere\nA` |
| thermodynamic temperature | kelvin | K | `thermodynamic temperature\nkelvin\nK` |

Here `\n` represents an actual newline in each saved quotation. Every cell cites NIST SP 811, Chapter 4, Table 1. The [retained readable page](workspaces/SI/runs/research-215ac89bf8fc46ebadb8af0a8d47dfee/1109eb057f25ad2429b6e77e/downloads/5ef8582e7b9f4a3e917fceebf5c66d0d.txt) contains these exact contiguous rows. Independently parsing the [original downloaded HTML](workspaces/SI/runs/research-215ac89bf8fc46ebadb8af0a8d47dfee/1109eb057f25ad2429b6e77e/downloads/5ef8582e7b9f4a3e917fceebf5c66d0d-0.raw) confirms each triplet belongs to one table row under “Base quantity / Name / Symbol.” Thus the semantic result is 15 supported cells and zero unresolved cells, independently of mechanical citation success.

There are three successful distinct HTML downloads and one cache hit, with no failed download. Their retained texts contain 6,619, 16,534 and 44,922 characters; all three whole-text hashes differ. Their raw downloads total 356,885 bytes. Each receipt binds `direct-readable-v1` and `unicode-layout-controls-v1`; all raw/readable hashes match, all forbidden-control counts are zero, and offline re-extraction of each complete raw HTML response exactly reproduces its retained readable text. This establishes the static extraction contract, not JavaScript rendering or visual equivalence.

The [automatic audit](audits/SI.audit.json) is available, with zero issues, zero uncited cells and all 20 recorded constraints covered. No backend error, retry, REPL exception, trace error or fetch failure was recorded. The two `stalled_search` signals are truthful empty new-entity reports after the complete five-quantity discovery. Both batched searches returned four hits, their sources were used, and the task explicitly requested this demonstration; they are not failed searches.

The complete page/root comparison is **68,075 / 28,594 = 2.3807442120724627**. This is a descriptive ratio, without an unqualified “far exceeds” verdict. Exact 50-character-gram overlap covers **409 / 68,075 = 0.006008079324274697**, or about 0.601%; coverage is unioned across **all** root prompts. No complete fetched page occurs in any root prompt. The denominator is retained fetched text, deduplicated by the evidence store per URL; the three whole-text hashes were also independently distinct here.

The largest root input is iteration 5, backend call `431027196b374df8aef1301d40a35f23`, trace line 192, SHA-256 `b26e69a57a8f70b39be67f2aa21868cba12aaab1aa6fd9e6f0a537e4c78bafdb`. Its exact nonoverlapping partition is:

| Component | Characters |
| --- | ---: |
| System, including backend instruction | 3,146 |
| Question and columns | 470 |
| Other task instructions | 8,282 |
| Harness payloads | 4 |
| Prior assistant code | 4,062 |
| REPL output | 11,906 |
| Wrappers | 724 |
| Total | 28,594 |

Executed [trajectory](workspaces/SI/runs/research-215ac89bf8fc46ebadb8af0a8d47dfee/1109eb057f25ad2429b6e77e/trajectory.jsonl) line 16 retains complete texts in `single_text`, `batch_texts`, `cached_text` and the URL-keyed `evidence` dictionary. It performs single fetch, two-item batched fetch and a different-focus cache request, then asserts exact cache equality. Line 19 supplies the complete three-page dictionary to one schema-validated submodel call and checks the returned rows against those texts. Its response equals the submitted object. The call has 70,567 prompt characters plus 1,207 schema characters; including backend instruction, total backend input is 71,956 characters. It is a stateless submodel call, **not** a child iterative RLM.

The [trace](workspaces/SI/runs/research-215ac89bf8fc46ebadb8af0a8d47dfee/trace.jsonl) confirms a single search plus a two-query search batch (lines 73–86), and single/cache fetch calls plus a two-URL fetch batch (126–137). The auditor binds two executed full-text-processing excerpts at lines 147 and 177 to archived locals and referenced variables. These operations satisfy the explicitly requested small demonstration; they do not establish learned general behavior.

The manual scores are:

| Metric | Value | Evidence |
| --- | ---: | --- |
| S1 validation before first answer-ready submission | 1 | Trajectory 18–19: nested schema, all required fields, nonempty quote/source lists, quantity and every-source exact quote checks. Line 41 asserts no failures, each nonempty expected unit/symbol and complete unique coverage before readiness. First root readiness: trace 285. |
| S2 exposed missing-field gap | 0 | Five rows and `Validation failures: []`; final checks pass. |
| S2 supplementary unique URLs after such a gap | 0 | All downloads precede extraction; no gap is exposed. Conditional score is N/A. |
| S3 quote-exception blocks | 0 | All five root blocks complete without error. |
| S3 caught/printed quote-failure records | 0 | The printed validation-failure list is empty. |

Refinement timing is unambiguous:

| Event | UTC time | Trace line |
| --- | --- | ---: |
| Mid-task request `8bba9ec8762a47e5bfc17f9579d94f83`, job `f26731dc94624279aa9420115332dc73` | 17:51:42.406418 | 201 |
| Planning starts | 17:51:42.406815 | 203 |
| Answer ready | 17:51:42.539591 | 285 |
| Worker exits | 17:51:43.040863 | 296 |
| Proposal | 17:52:09.218885 | 304 |
| Edit committed/applied | 17:52:09.282280 | 309 |
| Finalizer request `aca36d94e64948f6a4a1e68261a4ad8b`, job `3c109bfc06ed43f0be7391935b06230b` | 17:52:09.305782 | 314 |
| Finalizer completes with no edits or commits | 17:52:31.025751 | 321 |

All six harness retrievals, including initialization, precede the request and return empty entries. The commit is 26.241417 seconds after worker exit. There is no subsequent root retrieval or executed action, and no sleeping or polling block. The successful research procedure had already been performed or planned before the entry existed.

Both proposals pass strict schema and complete candidate accounting, and both lossless planner inputs match their full saved fields. Across them are six decisions: one accepted and five declined. The first snapshot has an `empty_output` occurrence and two search-signal occurrences; the final snapshot has the same two search-signal occurrences. Three additional candidates are separately accounted. The full proposals and rationales are preserved in the JSON.

- The mid-task planner accepts `empty_output` to create memory `44003b6780964d1ea56fb112a515b95e`, version 1, “Generated finalization code does not establish submission.” Commit `febc0d435a83fc8e40702b7015290310124a55f6` and [receipt](workspaces/SI/harness/edits/refine_44003b6780964d1ea56fb112a515b95e.json) exactly match the proposal and durable entry. The principle of requiring execution receipts is supported by the snapshot's missing completed worker result. **Its wording “before that block ran” is imprecise:** `refine.run` was executing inside that block; the constraint recording and submission subsequently completed. This is a snapshot-observation lesson, not an observed finalization failure or recovered error.
- The mid-task planner declines both search-signal occurrences because these are useful, required demonstration searches; that rationale is supported.
- It declines the additional successful-extraction candidate because the observed cache/schema/quote procedure mostly repeats base instructions and explicit task requirements; that is a supported conservative disposition.
- The finalizer declines the two search-signal occurrences for the same supported reason.
- It declines the additional successful-workflow candidate as redundant with existing instructions; the completed execution supports the success it describes.
- It declines revision/deletion of the finalization memory because the complete trace supports its general distinction and there is no usage/outcome history. That rationale does not remove the literal timing-wording qualification above. No use or benefit is inferred from retaining it.

This review performed no network request, model call, research launch or mutation of source, harness, inputs or raw outputs. It supports the answer and recorded execution within the retained archive. The qualified memory wording, late commit, absent same-run reuse and absence of a child RLM remain explicit limits.
