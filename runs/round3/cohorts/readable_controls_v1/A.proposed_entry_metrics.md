# Proposed entry-specific metrics for readable_controls_v1

This is an analysis proposal for the parent to register, not the registration itself. It uses completed A on runtime `902abe33d06f64c426a65d55d5e600dd6d6a052a`, BASE `2a423027212fe1c430dfd200bdd55f3a27b22d70`, and POST_A `d63478eec4f3acd9a71662e79a44183008a364d9`. Complete original entry objects are bound in [A.prediction_entry_binding.json](A.prediction_entry_binding.json); timing and candidate evidence are in [A.entry_review.json](A.entry_review.json) and [A.entry_review.md](A.entry_review.md). Prior cohorts' B results are already known, so a new registration is prospective, not blind.

## Existing discovery memory: bf8ebe4929de4c4493017583193abedc, version 1

“Inspect search results before recording discoveries” has identical operative title/body/version in BASE and POST_A. Only usage/outcomes changed. Preserve M1/M2 search-discovery measurements as descriptive checks; do not attribute a new procedural benefit to unchanged text. Full historical metadata is part of the intervention and is not silently removed.

## Exact source-span memory: 6bc3c4962d6e4eafab63ed0189268ec3, version 2

Predicted behavior: validate nonempty values, evidence and source lists; check the quote in every cited fetched source before accepting a cell; stage updates; report diagnostic identity; revalidate repairs. Suggested directions:

- Increase the fraction of executed cell-ingestion blocks that validate every admitted nonempty cell before corresponding row mutation. A complete check covers nonempty value/quote/sources and quote membership in every cited retained source. A failed gate that prevents mutation is a safeguard, but does not count as a completed repair. Retain the numerator and denominator and cite the executed code and record set.
- Decrease accepted invalid cells and destructive partial-batch mutation before validation. Keep final S1 (the actual readiness assignment boundary), S2 gap exposure/follow-up, S3 quote-exception blocks, and S4 final exact-citation findings separately; none alone proves this pre-mutation mechanism.
- Conditional on an actually observed quote-validation failure, increase diagnostic completeness (entity, field, source URL, failed condition) and decrease uninformative bare failures. A printed failure is an exposure even if it avoids throwing an exception. A denominator restricted to S3 exceptions should be labeled as that narrower diagnostic; otherwise a useful switch from exceptions to printed checks can erase the denominator.
- Conditional on repaired quote/citation mismatches, increase complete revalidation before acceptance. Removing a citation counts as a valid repair only if the remaining fetched citation independently supports the complete value. Semantic support is independently reviewed; exact substring membership alone is insufficient.

S3 exceptions can increase when earlier guards expose more errors. Report their direction as registered, but do not equate fewer exceptions with better semantic support without the exposure and final-result evidence. Zero failure exposure gives conditional diagnostics N/A, not a perfect score.

## Duplicate reconciliation memory: b98beb481e414d02952f80dbd258928e, version 1

Predicted behavior: detect duplicate entity-field records and reconcile supported complementary facts before updating rows, instead of sequential last-record assignment. Suggested directions:

- Record duplicate entity-field group exposures (at least two records for the same task entity key and field in an ingestion batch), with a separate count of groups containing nonidentical values. Use explicit reviewed aliases only; do not guess identity normalization.
- Increase duplicate-group detection and evidence reconciliation completed before mutation. A uniqueness assertion that stops mutation is detection, not completed reconciliation.
- Decrease destructive last-record overwrite occurrences: an earlier supported complementary component disappears solely because a later record is assigned without adjudication. Count the occurrence even if a later repair restores it, and preserve the actual record order and supporting sources.
- Decrease supported complementary components still missing in the final answer conditional on duplicate exposure. Distinguish citizenship, regional identity, ancestry, and conflicting claims. Do not merge unrelated quotations into a fabricated contiguous span.

Zero duplicate exposure makes reconciliation and remaining-loss conditional rates N/A. Raw counts remain available.

## Partial-fetch recovery skill: f9d1625b7c1a49a7824cc94063b6be4c, version 1

Predicted behavior: retain successful downloads, exclude failed fetch markers from extraction evidence, inspect retained text for unresolved entity-field gaps, and fetch relevant alternatives only where needed. Suggested directions:

- Decrease actual dispatched extraction calls whose evidence inputs include a `FETCH_FAILED` sentinel from a failed request. Count calls and enumerate the failed inputs. Instructional mentions of the sentinel are not evidence exposure.
- Increase executed retained-download reuse blocks before further acquisition for remaining gaps. Credit actual use of the retained text, not merely the existence of a product cache.
- Increase verified alternate-source gap recoveries conditional on gaps exposed after a partially failed batch; preserve the distinct successfully fetched supplementary URLs and S2 gap-directed actions. This skill says relevant alternatives, not official-only alternatives. A URL need not eventually succeed if another fetched source resolves the claim.
- Decrease repeated failed-URL attempts and repeated requests for the already successful portion of the batch. Report cache-hit requests separately from fresh network downloads; a cache hit is not a repeated download. A deliberate retry with changed conditions is still an occurrence and its reason remains visible.
- Require both exact retained-source quotation validation and independent support for the complete value before counting a resolved gap. Search snippets alone do not close a gap.

No partial failures or no unresolved post-batch gaps gives the corresponding conditional measure N/A. Keep failures and every error/recovery observation, including errors later repaired.

## Comparison and interpretation

For B0 and B1-frozen, report all three individual values, means, ranges, mean delta, and whether the absolute mean difference strictly exceeds the larger within-arm range. Three repeats are descriptive, not a significance test. Use the same fresh source, tasks, configuration and exact complete initial entry payloads. B1 has learning enabled and is reported separately. A/SI illustrate operation but are not the paired controls.

In A, both newly created version-1 memories were retrieved into seven subsequent root prompts. Quote checks and targeted duplicate-nationality searches already existed before those commits. Later duplicate diagnostics, reconciliation and staged mutation are compatible with the memories, but timing alone does not establish causal benefit. The final version-2 revision and fetch-recovery skill were committed after A's worker ended and were not reused by A.
