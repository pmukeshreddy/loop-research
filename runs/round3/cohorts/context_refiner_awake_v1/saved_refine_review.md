# Independent awake saved-preflight review

Reviewer `fetch_review`; source `5cd8fcbc3065a49717fd534ab3a804bd99d8090a`; reviewed 2026-10-20T08:57:58.048632+00:00. **Preflight failed.** Four direct saved replays completed on their first attempt; overflow failed after printing the entire historical trajectory into its own prompt. This cohort does not establish readiness for main research.

| Case | Status | Attempts | Failed | Retries | Actual backend prompt characters | Edits/decisions |
|---|---|---:|---:|---:|---|---:|
| A_distinct_pages_midtask | failed | 3 | 1 | 0 | 4,926, 57,575, 3,039,692 | 0/0 |
| A_full_pages_finalizer | complete | 1 | 0 | 0 | 855,991 | 1/5 |
| B1_finalizer | complete | 1 | 0 | 0 | 690,910 | 2/4 |
| B1_fragments_finalizer | complete | 1 | 0 | 0 | 757,559 | 1/3 |
| SI_midtask | complete | 1 | 0 | 0 | 52,954 | 1/4 |

Totals: seven model attempts, six successful and one failed, zero retries, one isolated Python worker, five proposed edits and 16 decisions across the four completed direct cases. All attempts use purpose `refine` and configured `gpt-6-astra`; no research root/sub, search, fetch or web calls were dispatched. The three overflow calls are all coordinator calls; no refinement subcalls occurred.

## Exact input and schema preservation

Independently rechecked all 31 installed modules against recorded source identity, and all 1,159 prepared original-file records (141,262,196 bytes; not a unique-file count). Every original job/config/logical-input file matches the preserved failed-preflight counterpart. Original archived wire formats decode exactly; all current direct `stdin.txt` payloads decode to complete original logical input plus the generated evidence index. Hashes, finite anchors and actual schema files match.

`B1_finalizer` and `SI_midtask` retain the authorized three-change restrictive anchor upgrade of their exact historical pre-anchor schema; both original/current schemas validate the final proposals. The other three use exact original schemas. All 16 returned decisions were independently checked for complete unique candidate coverage, valid finite pointers, accepted-edit links and no orphan edits.

Overflow loaded the complete 3,027,914-character context, SHA-256 `2c9dd4b6c0a8aac815b784af57ca5501bbdd20fd3664d0b96204565c8499c663`; schema SHA-256 `4f3b234f6027ef98c081e384dd786732e0e9d8fc1a334ac213aa33e306811892`. Context equality with the original plus generated index is verified. The prospective oversized direct prompt was not used.

## Trace-backed overflow failure

The overflow archive is `saved_refine/A_distinct_pages_midtask/workspace/runs/refine-replay-02154493d8d847b58f3e787aceef79aa/289901ce021c28d56fdac993/refine_planners/29ed2c2a399d40839eece9bb00b2aab1`. Its `actions.jsonl` establishes this sequence:

1. Line 1 records the full snapshot read. Lines 2–5 link coordinator action `fab90f9a26ce4876860dbd9c56648ec5` to successful call `c996630583884601bae1f94b279da7a3` (4,926 characters).
2. Lines 6–7 execute inspection of keys, schema, focus, edit cap, candidate inventory, anchors, entries and self-check. Output is 51,972 characters, with no stderr. The next coordinator call succeeds at 57,575 characters (lines 9–12).
3. Line 13 executes the model's next block: loop over all 77 `context["trajectory"]` records and print each entire JSON record. Line 14 retains **2,981,867 characters** of stdout, zero stderr. Independent reconstruction of the print output from all 77 original records matches it exactly.
4. Lines 16–19 link the third action `085474b5369f4bafb5e32bcaa1e10136` to failed call `14da5843c4bd42bf83e3f547d2ce9b45`. Its coordinator prompt is 3,039,510 characters; the 182-character backend prefix makes **3,039,692**, exactly the provider's rejected count. The trusted response is `-32602`, `input_too_large`, limit 1,048,576. It is not retried.

The initial instructions explicitly ask for focused diagnostics and prohibit printing the whole oversized snapshot. The model nevertheless selects whole-trajectory printing. The host retains its complete output and sends full history as designed. This is a demonstrated planner transport failure, not missing/corrupted input or host truncation. No snapshot edits, semantic compression, repair attempt or counterfactual retry occurred. There is no final proposal and no completed overflow candidate accounting.

This failure is distinct from the preceding cohort's sleep/queue/cleanup episode: all seven calls here finish without timeout, capacity error or EPERM. The five-case harness uses four concurrent case workers. The permanent input-size error is preserved and counted once.

## Proposed-edit quality and limits

The direct proposals contain general procedures, without fixed answers, target URLs/domain lists or changes to production code:

- A proposes comparing replacements with prior verified evidence. Original trajectory pointers `/trajectory/118` and `/trajectory/121` explicitly restore a previously supported value lost by a follow-up extraction.
- B1 proposes alias-aware novelty and checks for populated-but-incomplete fields. `/trajectory/43` and `/trajectory/58` show exact-string novelty; `/trajectory/126` requests a full motivation and prohibits editorial notes in values. Its historical model-rendered-fetch advice is conditional and does not establish that focus/summary refetching applies to current direct full-page retrieval.
- B1 fragments updates field/provenance review. `/trajectory/93` explicitly demands citizenship evidence for nationality cells, supporting the field-scope concern. Existing skill `/entries/3` is updated, not duplicated.
- SI proposes cache reuse. `/trajectory/11` and `/trajectory/15` show deduplicated fetching and reuse; `/trajectory/19` reports five rows and zero validation failures. It declines unsupported final-output failure attribution and declines preserving a task-specific expected-value dictionary.

Every decision and edit was read; every citation was structurally resolved against immutable input. These checks do not convert pointer membership into proof of every historical semantic narrative, and no external sources were fetched again. The overflow output has no quality verdict because it has no proposal.

All raw attempts, errors, code, full streams, source identities and prior cohorts remain preserved. Companion JSON records each call, decision, evidence pointer, action link and supporting artifact hash.
