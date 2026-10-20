# Completed A: entries, candidate accounting and same-run delivery

A completed with exit 0 at **2026-10-20 18:13:03.833090 UTC**. Runtime/source is `902abe33d06f64c426a65d55d5e600dd6d6a052a`; later evidence-only repository commits are not a new runtime. The run is `research-a685a2c37ca948fa9d7ab1a551451ff2`, task `289901ce021c28d56fdac993`. BASE is `2a423027212fe1c430dfd200bdd55f3a27b22d70`; exact POST_A is **`d63478eec4f3acd9a71662e79a44183008a364d9`**.

The complete before/after entry objects, intermediate versions, all proposal decisions and evidence references, commit history, full selected executed code/output streams, actual prompt-entry comparisons, and a 314-file unchanged raw-archive inventory are retained in [A.entry_review.json](A.entry_review.json). Its entry objects exactly match the independently written [prediction entry binding](A.prediction_entry_binding.json). No raw archive, harness, source, configuration or executable helper was edited. [Proposed metrics](A.proposed_entry_metrics.md) are a draft for registration, not a registration or result claim.

## Complete entry delta

| Entry | BASE → POST_A | Origin and committed change |
|---|---|---|
| Memory `bf8ebe4929de4c4493017583193abedc` — Inspect search results before recording discoveries | v1 → v1 | Only complete usage/outcomes metadata changes. Title, body and version are unchanged. |
| Memory `6bc3c4962d6e4eafab63ed0189268ec3` — Validate exact source spans before accepting extracted cells | absent → v2 | Midtask create v1 at `08e662ec91dda2e96c3515699a8d056b52381153`; finalizer update v2 at `e23dc24b573104902c38ebc58dd39d05c9189ba1`. |
| Memory `b98beb481e414d02952f80dbd258928e` — Reconcile duplicate entity records before updating cells | absent → v1 | Midtask create at `b78f23073314fe6c2f9ad8277b943ec7af377e84`; later usage/outcomes recorded, no subsequent body edit. |
| Skill `f9d1625b7c1a49a7824cc94063b6be4c` — Recover evidence from partially failed fetch batches | absent → v1 | Finalizer create at POST_A `d63478eec4f3acd9a71662e79a44183008a364d9`. |

The exact-span memory originally required quote membership in every cited source, preserving PDF whitespace and checking support for the complete value. Version 2 adds nonempty values/source lists, staged mutation, entity/field/URL/condition diagnostics, and a guard against removing a citation unless the remaining citation independently supports the complete value. The duplicate memory prevents sequential last-record assignment from discarding supported complementary facts and distinguishes citizenship from regional identity or ancestry. The fetch skill separates failure sentinels from evidence, preserves successful downloads, inspects retained text for unresolved gaps and seeks verified alternatives. These bodies remain general; they do not prescribe specific task identities or websites.

The seven BASE-to-POST_A commits contain four procedure edits and three bookkeeping commits: observe task; record usage; record self-check outcome. Metadata is retained as part of complete entry objects rather than silently discarded. Existing discovery text is not a new procedural intervention.

## Candidate decisions and evidence

The midtask request `0849400449214df2a7b23011586e18f6`, job `48e74973b1214300baea6c389394ddf2`, has three presented groups plus two additional candidates: **five decisions, two accepted and three declined**. Every occurrence reference in each presented group is explicitly cited by its decision. The one empty-output issue is correctly treated as an unfinished snapshot rather than a failed terminal submission. All 18 stalled-search signals and nine failed-fetch signals are discussed and declined. Two additional candidates drive the edits: three PDF affiliation-quote mismatches after row accumulation, and duplicate nationality records overwriting earlier values.

The finalizer request `f46cb2cf1b5f4971bad7764fbbcd4521`, job `a13083e09028499cbac309247a2de22c`, has three presented groups plus four additional candidates: **seven decisions, two accepted and five declined**. Its 29 stalled-search occurrences are all cited and declined. All 13 failed-fetch occurrences are cited and accepted as evidence for a recovery workflow, without treating the retrieval failures themselves as agent fault. A single bare assertion candidate updates the quote-validation memory. Duplicate reconciliation, semantic audit, release validation and evidence-selection efficiency are separately accounted for and declined with reasons.

Both proposals pass the exact archived JSON schemas and strict accounting checks. The candidate inventories and evidence-anchor indices exactly recompute from each supplied observation snapshot, and the encoded input decodes to the full supplied logical payload with the archived SHA-256. These checks establish structural accounting and input identity, not semantic correctness. Planner projection of observations is the inherited policy; this is not a claim that the planner received every raw trajectory field.

The duplicate finding is independently supported by the exact ordered records at worker iteration 7 (trajectory line 73): Stoddart's earlier British/American record is overwritten by Scottish, and Bawendi's earlier American record by French. All the individual quotes passed their source checks, so membership validation alone did not detect the duplicate-key loss. Later diagnostics name exactly these two duplicate groups.

The finalizer's bare-assertion rationale also matches execution: iteration 9 checks one Doudna quote against two sources, with only one matching; the assertion prevents the subsequent mutation loop. Iteration 10 prints the per-source membership diagnostic; iteration 11 retains matching citations and stages later reconciled updates. Citation removal and exact membership still require an independent semantic-support judgment.

The fetch-sentinel concern is concrete: **eight actual research extraction subcalls contain ten source-evidence objects whose complete text is `FETCH_FAILED`** (trajectory lines 64, 65, 67, 68, 69, 71, 116 and 117). These are parsed evidence objects, not instructional mentions. The derived JSON preserves their exact URLs and prompt hashes. The finalizer's decision strengthens an operative workflow already partly present in base guidance; this is not evidence that the new skill caused A's earlier recovery.

## Request → commit → delivery → subsequent action

All trace and trajectory line numbers below are 1-based JSONL lines. Proposal `/trajectory/N` anchors are 0-based positions in that job's supplied snapshot and must not be confused with raw line numbers.

| Event | UTC time | Raw trace line |
|---|---|---:|
| Midtask request scheduled | 18:05:23.411616 | 778 |
| Planning starts | 18:05:23.411934 | 780 |
| Proposal recorded | 18:06:07.285170 | 867 |
| Apply begins at a later model boundary | 18:06:35.628403 | 938 |
| Exact-span v1 committed | 18:06:35.688619 | 941 |
| Duplicate memory v1 committed | 18:06:35.730884 | 944 |
| First retrieval includes both | 18:06:35.815765 | 948 |
| Research worker ends successfully | 18:09:25.914474 | 1948 |
| Finalizer scheduled | 18:09:26.683888 | 1957 |
| Exact-span v2 committed | 18:13:03.606842 | 2003 |
| Fetch skill committed | 18:13:03.653204 | 2006 |

The first midtask commit occurs 72.277003 seconds after scheduling and 28.403449 seconds after proposal recording; no claim of immediate application is made. Both memories arrive about 170 seconds before the worker ends. The second commit precedes the first retrieval by 0.084881 seconds. The duplicate entry has BM25 score 0 but is delivered through the current-run inclusion rule.

Both complete v1 entry objects appear in **seven actual subsequent backend root inputs, roots 10–16**, at trajectory model-record lines 90, 94, 101, 107, 114, 120 and 124. Each object, including metadata, equals the object at the committed midtask state; this is stronger than checking title strings or a saved context file. Retrieval traces are 948, 1006, 1050, 1092, 1158, 1223 and 1257.

After exposure, iteration 10 (trajectory line 93) prints duplicate counts and a quote-membership diagnostic. Iteration 11 (line 100) requests one reconciled record per target entity, checks all returned records before its mutation loop, and restores supported components. It retains the full Stoddart CV while selecting an exact original source slice for a subcall. Later iterations perform semantic review and final validation. **This is compatible action after delivery, not causal proof:** quote guards and repairs already existed, and targeted Stoddart/Bawendi multiple-nationality searches began in iteration 9 before the memories committed. The final v2 revision and recovery skill were created after the worker ended and had no A worker reuse.

## Actual finalizer transport and interpretation limits

Midtask refinement used one direct model attempt with 598,125 backend prompt characters. The finalizer's 1,341,179-character monolithic pre-routing prompt was not dispatched. It used context transport with five planner calls and seven subcalls, all purpose `refine`; these 12 actual calls plus the direct call are 13 refinement attempts. Action/attempt links and full backend prompt hashes match the durable call records. There are no retries or failed backend attempts in those calls.

Finalizer iteration 1's complete 2,217,369-character feedback (stdout 2,217,344) was retained and represented by an 855-character receipt before the next call, reducing that complete backend prompt from 2,223,626 to 7,112 characters. There was one externalization event and no `repl_output` reads; do not infer a retrieval demonstration. The planner inspected its complete context through code and subcalls. The separate authoritative audit validates this transport; the entry review retains action references and actual-call identities rather than pretending the pre-routing prompt was dispatched.

The semantic-audit decision explicitly acknowledges uncertain historical labels and a permissive later review. It prioritizes diagnostic and recovery edits under the two-edit ceiling; it does not establish that all semantic concerns were resolved. The release-validation decision expressly calls 308 quotation/citation records and 168 agent-supplied constraint verdicts mechanical completion, not independent semantic proof. The independent 140-cell quality review is a separate artifact owned by `fetch_review`, including temporal nationality and broader affiliation-coverage concerns.

All reported observations use the new fetch path. Future three-repeat comparisons are descriptive, not statistical significance. Prior cohorts have been observed, so prospective predictions cannot be labeled blind.
