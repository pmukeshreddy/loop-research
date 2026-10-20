# Round 3 numeric metrics extractor

`metrics.py` reads completed cohort archives, existing full archive audits, the frozen plan/execution, a saved reference manifest, and explicitly cited manual reviews. It never imports the research product, starts a model, fetches a page, changes a harness, or edits research inputs. It rejects incomplete runs and missing required manual evidence. Nine main runs feed the report's ten checks; the separate explicit-refinement assessment is not silently counted as a tenth main run.

The complete final invocation, once every control has finished and reviewers have supplied their files, is:

```sh
.venv/bin/python runs/round3/metrics.py \
  --directory runs/round3/cohorts/final \
  --audits runs/round3/cohorts/final/audits \
  --manual <A-SI-review.json> <B0-review.json> <frozen-and-B1-review.json> \
  --aliases runs/round3/cohorts/final/metrics/identity_aliases.v2.json \
  --output-dir runs/round3/cohorts/final/metrics/all
```

`--manual` accepts multiple files with disjoint `runs` keys. `--reference-manifest` defaults to the saved Round 2 manifest. `--labels A SI` can select completed runs, explicitly labeling the result partial and withholding the six-control aggregate. Each output directory must be new or empty, outside every research workspace; previous results are not overwritten. Output comprises `metrics.json` (all values and complete evidence) and `metrics.md` (all numeric values and aggregate tables).

The exact event definitions are also embedded under `definitions` in every JSON report:

- M1 counts successful individual `tools.search` completions, including children of `search_many`, once each. A successful discovery with the identical original query must occur **after** completion and by the next depth-zero root REPL `code.end`. Empty discoveries count. Prior records do not satisfy a later search; child REPL endings are not root boundaries. One matching event may satisfy duplicate query requests whose intervals contain it, and those shared matches are explicitly listed. Missing root boundaries produce N/A rather than zero.
- M2 counts each successful empty discovery event with a later successful nonempty discovery for the exact query. Repeated empty events count individually; uncorrected empties are not deemed wrong.
- Repeated exact searches are individual request starts after the first successful completion for that original query, including later cache hits or failed attempts. Concurrent starts before a success are not reuse opportunities. Query case/whitespace remains significant; `k` does not change query identity. Invalid query attempts remain in error evidence and a separate count.
- Fetch requests are bound, in admission order, to `tools.fetch` cache events under the host lock. Exact same stored URL admissions after the first failed completion count as repeats; concurrent shared requests admitted before that failure do not. Counts, all requests, all evidence failures, per-URL repeats, and all denominators remain available. Zero failed-URL denominators yield N/A. Cancelled and pending requests are separately counted, not silently reclassified as failed. Cache and shared requests have separate counts.
- Model calls are the union of unique durable dispatch identities and completion identities. All purposes and retry attempts count; missing completion and completion-only records remain visible. Root/search/sub/refine counts and other purposes sum to the total. Every trace `details.error` event is retained and counted, including expected HTTP failures and propagated copies; this is an event count, not a deduplicated causal-error count. REPL error blocks, unsuccessful events without an error, evidence failures, and complete issue/signal lists remain separate.
- S4 checks every required final cell and every cited URL against retained original fetched text without normalization. A missing cell/quote/source/text or any failed exact quote membership makes that cell one violation. Q1 retains rows, all self-check issues, distinct uncited-cell counts, normalized identity symmetric differences, and duplicate identity counts.
- Identity matching uses the prior comparison's Unicode NFKD/casefold/alphanumeric key normalization. Raw differences remain. The only additional substitutions are explicit, cited alias receipts. `identity_aliases.v2.json` binds the independently reviewed `Sir J. Fraser Stoddart` / `Sir Fraser Stoddart` spelling pair to the review file's SHA-256; no generic name guessing is applied.
- Fetched readable character totals, largest verified backend root input, exact 50-character-gram overlap, full prompt partition, and every subcall input/schema/backend size come from the unchanged frozen archive-audit method. All audit source-file hashes are verified against the completed archive. Subcall per-run count/total/min/max/mean are included so varying-length call distributions are not forced into arbitrary index comparisons.
- Every scalar metric receives all six control values, defined-run count, arm mean/min/max/range, delta = frozen mean minus B0 mean, spread = maximum within-arm range, and strict `abs(delta) > spread`. Undefined values never become zeros. Every metric is reported; no composite score or favorable subset is substituted. Three repeats are descriptive, not statistical evidence.

Manual review schema:

```json
{
  "source_commit": "<exact cohort source>",
  "runs": {
    "<label>": {
      "run_id": "<exact archived run>",
      "metrics": {
        "S1_preadd_validation": {"value": null, "reason": "Unavailable preregistered boundary", "evidence": [{"path": "<existing file>", "line": 1, "note": "Explanation"}]},
        "S2_gap_exposed": {"value": 0, "reason": "Review explanation", "evidence": []},
        "S2_supplementary_unique_urls": {"value": 0, "reason": "Review explanation", "evidence": []},
        "S3_quote_exception_blocks": {"value": 0, "reason": "Review explanation", "evidence": []},
        "S3_caught_printed_quote_failures": {"value": 0, "reason": "Review explanation", "evidence": []},
        "posthoc_fullcell_validation_before_answer_ready": {"value": 1, "reason": "Separate post-hoc diagnostic", "evidence": []}
      },
      "semantic_review": {"summary": "Independent assessment", "counts": {}, "evidence": []}
    }
  }
}
```

All shown empty evidence arrays are placeholders: real inputs require at least one citation even for a zero. File existence, line bounds, source/run binding, and any supplied file hash are checked. Numeric manual explanations are preserved as `review_reason`; `reason` marks unavailable values only. `counts` may add explicitly reviewed semantic numeric measures; no semantic verdicts are guessed. The alias `fullcell_validation_before_answer_ready` is accepted and renamed with the `posthoc_` prefix.

Literal S1 is **N/A** because the committed preregistration names `records.add`, which is not an exposed API. The helper rejects a non-null S1 score. The before-`answer.ready` measure is a separately labeled post-hoc diagnostic and cannot count as directional success. S2 reports both raw count and gap exposure, with a conditional N/A when no gap appears. S3's primary score counts terminated quotation-exception blocks; the separate caught/printed diagnostic counts individual executed printed failure records, including repeats, as reviewed from complete execution evidence.

## Explicit scoring contracts

The default `--contract records-add-v1` preserves the preceding historical S1 behavior and the old metric keys. Existing review files without a contract declaration retain that interpretation. No old prediction, manual review, or generated result is rewritten.

The optional `--contract answer-ready-v2` provides a distinct `S1_pre_answer_ready_validation` measure for a future preregistration. Its boundary is the first root submission setting `answer["ready"] = True`, located through the first depth-0 `REPL code.end` event reporting `answer_ready=true`. This is a dictionary assignment, not a callable `answer.ready(...)` API. A score of 1 requires executed validation before that assignment covering the actual submitted, nonempty candidate row set: every required cell has a nonempty value/source list/quote and its quote occurs exactly in retained original text for every cited URL. Successful checks of an earlier candidate version do not suffice. A failed guard followed by repairs and a successful complete guard before submission may score 1. The score records an observed guard, not causal benefit.

A cited review must explicitly supply 0 or 1 when the submission exists. With no root submission, it must supply null with a reason and evidence. Missing manual fields or evidence fail extraction; absence is never scored 0. The extracted first submission trace event is retained as `submission_boundary`. JSON and Markdown name the contract, boundary, and complete definition.

Each v2 manual file must declare top-level `"analysis_contract": "answer-ready-v2"` alongside `source_commit` and `runs`. Its required metric keys are `S1_pre_answer_ready_validation`, `S2_gap_exposed`, `S2_supplementary_unique_urls`, `S3_quote_exception_blocks`, and `S3_caught_printed_quote_failures`, with the same cited-value format and semantic review as above. The legacy S1 key cannot be mixed into v2. The legacy post-hoc diagnostic is not required in v2, and is never automatically renamed to S1.

Selecting v2 defines a measurement; it does not select the future A entries or create a directional prediction. All v2 aggregates set `directional_claim_allowed: null` with a reason requiring the cohort’s committed preregistration. The old v1 flags are preserved. Any future directional claim must cite the new preregistration. The default v1 historical scoring remains unavailable.

The versioned contract change is covered by `test_metrics_contract.py`: explicit/default v1 equivalence; old/new S1 rejection across contracts; actual submission witness; explicit zero versus missing field versus justified N/A; binary score validation; manual contract receipt; output labels; and no automatic future S1 directional claim. `metrics_contract_red.log` preserves the initial missing-feature failures and `metrics_contract_boundary_red.log` preserves the corrected-assignment-boundary failures. `metrics_contract_final_green.log` records the combined 24 metric checks. `metrics_contract_direction_red.log` preserves the missing version-specific directional gating failure. The independent control audit suite is rerun in `control_audit_contract_green.log`.

## Verification and preserved corrections

The standalone `test_metrics.py` suite tests exact boundaries, prior-versus-later discovery, batch-child counting, repeated empty events, concurrent fetch failures, invalid query errors, missing evidence, nullable S1/zero denominators, strict spread equality, all-URL citation checks, and explicit alias identity handling. It also independently recomputes A/SI's unchanged case/whitespace-sensitive 50-gram coverage and verifies their saved largest-prompt hash/partition and subcall totals against frozen audit files. No product tests or models run.

`metrics_red.log` records the missing-helper red state. `metrics_reason_red.log` captures the misleading-unavailable-reason regression; `metrics_validation_red.log` captures rejection of malformed query values without losing error evidence. `metrics_green.log` records the final standalone suite.

The first completed-only A/SI extraction remains untouched at `cohorts/final/metrics/A_SI/`. It attached misleading unavailable explanations to valid size values and lacked the explicit Stoddart alias. `A_SI_v2/` preserves the corrected available-value explanations and raw A identity difference 2 alongside cited canonical difference 0. Later final extraction uses the final helper and current explicit alias receipt, with its own provenance hashes. No numerical research result, prediction, model input, or product code was changed by these reporting corrections.
