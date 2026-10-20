# Independent preregistration review — readable_controls_v1

**Approved with the stated measurement limits; no remaining blocker.** This is a reporting receipt, not a new preflight or evidence of learning benefit. Initial independent content and binding review occurred before the prediction commit and B launch. It raised only an S4 wording ambiguity, corrected before commit. This final receipt was written at 2026-10-20T18:24:35.428226+00:00, after B began; it is not represented as a prelaunch file. No new-cohort B outcome was inspected.

[Predictions](../../predictions.md) are exactly 15,055 bytes with SHA-256 `cec6bffde76d8a79aeac7c037dde65910e6fcac1927e899d63d8624582951f78`, identical to commit `2ecab945810592a7b9e084c3d3c5dc8b00a4f20a`. Source is `902abe33d06f64c426a65d55d5e600dd6d6a052a`; POST_A is `d63478eec4f3acd9a71662e79a44183008a364d9`.

| Boundary | UTC timestamp |
|---|---|
| A completed naturally, exit 0 | 2026-10-20 18:13:03.833090 |
| Initial prediction write receipt | 2026-10-20 18:18:26.938062 |
| S4 clarification finalized | 2026-10-20 18:20:41.901889 |
| Prediction commit | 2026-10-20 18:21:53 |
| Launch gate verified committed bytes | 2026-10-20 18:22:04.351455 |
| B phase started | 2026-10-20 18:22:05.319633 |

Initial review found no B phase, process record, console or launcher event. The later [execution record](execution.json), [prediction write receipt](prediction_write_receipt.json) and [launcher events](launcher_events.jsonl) preserve the actual sequence. The launch gate checks completed A, exact committed prediction bytes, source and POST_A. This review distinguishes those records from the later time at which this document was saved.

All four complete changed objects in [A.prediction_entry_binding.json](A.prediction_entry_binding.json) exactly match Git BASE/POST_A states, including all metadata; changed-field sets also match. Raw BASE state SHA-256 is `5031ab862ddcc418480fe8c645d190f43f7cd80f5548ab1e48d16add719baf29`; POST_A is `0ee27a891a46c6e81763bc9cd86cf67aed38362e69a46ef1f7f0c4239ce347ac`. The three additions and their directions are coherent:

| Bound entry | Registered measurement |
|---|---|
| `6bc3c4962d6e4eafab63ed0189268ec3`, memory v2 | S1 increases; S3 and V1 decrease; S4 decreases or remains zero. V1 conditional N/A without S3 exposure. |
| `b98beb481e414d02952f80dbd258928e`, memory v1 | D1 increases and D2/D3 decrease conditional on D0 duplicate-candidate exposure. |
| `f9d1625b7c1a49a7824cc94063b6be4c`, skill v1 | F1 decreases with failed-fetch exposure; R2 increases; supplementary retrieval increases given a required-field gap; failed-URL repeats and their ratio decrease. |
| Existing `bf8ebe4929de4c4493017583193abedc`, memory v1 | Only usage/outcomes changed. M1/M2 and search repeats are descriptive; no new discovery procedure is claimed. |

The S4 correction now states “for any cited URL, a quote occurring in none of that URL's retained original texts.” This matches the existing per-URL membership implementation in [metrics.py](../../metrics.py): every cited URL needs at least one retained text containing the exact quote. It is a wording clarification, not a scoring change.

V1 deliberately measures identifying diagnostics only for terminated quote-guard blocks, not all failures; no manual fraction is needed. D0–D3 require retained candidates, actual assignment order and field-level semantic support, with uncertainty reported as N/A. Their subset relationships imply D1 ≤ D0 and D3 ≤ D2 ≤ D0. F1 requires the exact recorded failed return in an actual research extraction/verification source payload, excluding failure-diagnosis calls, refinement and instructional mentions. R2 requires executed reuse in a later root block; mere length printing and same-block first extraction do not qualify. These boundaries are reportable from retained traces and inputs without inferring behavior from delivery alone.

The existing helper accepts arbitrary additional nonnegative integer manual counts or N/A and validates evidence. Automatic ratios already use its numeric path. Standard automatic metrics, all added manual counts and conditional forms, raw HTTP-body artifacts, per-URL evidence deduplication and additional whole-text SHA-256 deduplication remain reportable separately. Largest-root size and overlap across the union of all root prompts are distinct measures. No helper or scoring changes were needed or made for this review.

All numeric metrics must retain individual results, arm means/min–max/defined counts, frozen-minus-base delta and strict `abs(delta) > max(within-arm ranges)`. Equality does not pass; N/A is not zero; fewer than three defined observations is qualified. Three repeats are not statistical evidence. Exposure, source availability, block granularity and model variation limit raw-count comparisons. Quote membership and mechanical zeros do not establish semantic coverage, and actions following entry delivery do not establish causality.

Earlier superseded outcomes were known: this registration is prospective for this cohort, not blind. The intervention includes full entry metadata. Cross-round fetch changes do not isolate learning; saved replay lessons are not claimed to seed these arms. Primary controls are three frozen runs versus three BASE runs, with learning-enabled B1 separate. All unfavorable and unexercised outcomes remain required; no composite replaces the metric inventory.

[Machine-readable receipt](prediction_review.json) records exact hashes, object comparisons, metric locations and limitations. Live coordinator-file hashes are snapshots taken for this review and may later change. Only these two new review files were written; no source, prediction, input, harness, raw archive, launch, install or test was changed or run.
