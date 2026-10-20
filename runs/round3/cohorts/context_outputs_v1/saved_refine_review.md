# Independent saved-replay review: context_outputs_v1

Reviewer `fetch_review`; frozen source `9251c8e8925f57cf9fc924e0fd57b1bd0d74bd6d`; reviewed 2026-10-20T14:53:46.977491+00:00.

**Mechanism preflight passes; semantic review is qualified.** All five saved replays completed, preserving full original inputs, schema contracts, actual-call links and candidate accounting. There is one demonstrated historical-count overstatement in a saved decision rationale. The conditional procedure remains supported; this is not an unqualified zero-issue quality claim, and it does not measure fresh research or A/B improvement.

Execution ran from 2026-10-20T14:41:45.760722+00:00 to 2026-10-20T14:47:07.415316+00:00 with four case workers and four shared Codex slots. There were **21 successful model attempts, zero failed attempts/retries, one isolated worker, nine applied edits, and 24 decisions** (10 accepted, 14 declined). All calls use purpose `refine` and configured `gpt-6-astra`; no research, search, fetch or web calls were made. Actual command receipts disable shell and web tools.

| Saved case | Actual model attempts | Actual backend prompt characters | Edits / decisions |
|---|---:|---|---:|
| A_distinct_pages_midtask | 17 | 6 planner + 11 sub; max 618,114 | 2 / 6 |
| A_full_pages_finalizer | 1 | 855,991 | 2 / 5 |
| B1_finalizer | 1 | 690,910 | 2 / 4 |
| B1_fragments_finalizer | 1 | 757,559 | 2 / 5 |
| SI_midtask | 1 | 52,954 | 1 / 4 |

## Exact preservation and accounting

Independently hash-checked all 32 installed/source modules and all 1,159 prepared original-file records, totaling 141,262,196 bytes (a record total, not a unique-byte count). Original job/config/logical-input files remain byte-identical to the preserved awake-failure cohort. Saved wire inputs decode exactly. Every current direct dispatch decodes to the original complete logical input plus the generated evidence index; actual `stdin.txt` bytes match recorded prompts by hash, including concurrent calls joined by identity rather than completion order.

`B1_finalizer` and `SI_midtask` use the authorized exact legacy schema restriction with three anchor-related changes. Their original/current schemas both validate the final proposal. The other three schema contracts are exact. All **323 referenced pointers** resolve into the immutable inputs; all presented/additional candidates have exactly one decision, accepted decisions link valid edits, declined decisions link none, and no edit is orphaned. Every decision and proposed edit was read.

The overflow snapshot is 3,027,914 characters, SHA-256 `2c9dd4b6c0a8aac815b784af57ca5501bbdd20fd3664d0b96204565c8499c663`, exactly original input plus generated index. Its strict schema canonical SHA-256 is `4f3b234f6027ef98c081e384dd786732e0e9d8fc1a334ac213aa33e306811892`. The prospective 1,611,089-character monolithic prompt was not dispatched.

## Actual output-reference and semantic-review use

Evidence is in `runs/round3/cohorts/context_outputs_v1/saved_refine/A_distinct_pages_midtask/workspace/runs/refine-replay-fcd166614bd64d4bbff447c8da39969c/289901ce021c28d56fdac993/refine_planners/758e92705e99406ebb105ffc01f83bb1/actions.jsonl`.

- Lines 6–8 execute and retain a complete snapshot/schema print: **3,033,076 stdout characters**, SHA-256 `efbbadbffb273f63f5b626ceb6148aeb6b5d1cc06d11de2e7a7288bc341afca0`. Independent regeneration from the original snapshot/schema equals the stdout exactly.
- Line 9 externalizes that entire completed iteration using an 855-character receipt. The complete prospective backend prompt decreases from **3,038,870 to 6,624 characters**. Original output and block hashes match; no prefix/suffix excerpt or summary replaces the stored output.
- All six actual planner prompts independently reconstruct byte-for-byte from initial messages, exact model responses, complete code outputs and the preceding reference event. Their backend sizes are **5,606; 6,624; 59,376; 140,837; 222,980; 249,991**. Model/control messages are intact, and later small observations stay inline. Every model action joins exactly one durable actual call and successful completion.
- **No `output.read` occurred.** The reference was used in real prompt transport, while semantic inspection proceeded through the still-complete `context`. This live replay does not itself demonstrate calling `repl_output`; that capability has separate offline evidence.
- Line 28 executes batched semantic reviews. Exact input comparison confirms that the 11 actual subcalls collectively receive all **76 other complete trajectory records** and all **75 full source results** in `/trajectory/68`, with their URLs and kwargs. The special split omits the record's type/tool wrapper in the model-selected subcall view; the original full record remains available. This is not host field suppression.
- Line 73 prints all 11 actual subresponses. Every response is present unchanged in later planner prompts. Subreview at line 70 identifies temporal ambiguity despite exact quotation membership. The coordinator then executes independent checks at lines 79–80, inspects all 35 stalled-search cases, prints the specific ambiguous extraction, and obtains **140 quote checks / zero membership failures**. This pure quote computation was independently repeated from archived input with the same result.
- Lines 86–87 validate and return the final two-edit/six-decision proposal. The output uses the reviewed temporal ambiguity and field-supplementation evidence, while declining a subreview's suggestion that populated search hits necessarily make empty new-entity discovery logging wrong. This establishes actual result use and adjudication, beyond mere data access.

Six code blocks have empty stderr; five nonterminal iterations are sealed and the sixth returns readiness directly. Actual traces show no error/retry event. The complete model/worker distinction and all 26 saved-audit source records were independently checked.

## Semantic assessment and retained qualifications

The proposals preserve general procedures rather than answer keys or fixed task/site rules. A full-pages proposal addresses scope clarification and comparison before replacing supported cells; original `/trajectory/118` and `/trajectory/121` show loss and restoration of stronger prior evidence. B1 addresses alias-aware discovery and populated-but-incomplete factual fields; original `/trajectory/43`, `/trajectory/58`, `/trajectory/126` and `/trajectory/130` show the exact-string novelty and later repair. SI's cache procedure follows executed reuse and validation at `/trajectory/11`, `/trajectory/15`, `/trajectory/19`; it correctly declines treating a midtask empty output as failed finalization.

Overflow preserves explicit-field supplementation and a distinction between exact quotation and temporal support. The original output normalizes `Nationality USA/USSR (now Russia)` to `American; Russian`. That is evidence of lost qualification/ambiguity, **not proof here that the real-world value is false**; another retained source describes the person as Russian. The general memory asks for temporal reconciliation rather than storing an answer. All ten download failures are accounted for as six HTTP errors, three redirect loops and one broken pipe; alternative-source coverage is distinguished from repairing failed endpoints. No new fetch happened during this replay.

**Observed rationale overstatement:** `B1_fragments_finalizer` accepts `trajectory:respect_explicit_field_absence` and says: “Earlier saved extractions explicitly reported absent nationality/citizenship for all eight revisited announcement pages.” Seven prior outputs explicitly do so. The 2016 page's earlier `/trajectory/23` result is a short motivation excerpt, and `/trajectory/68` lists people and institutions without an absence statement. All eight later `/trajectory/86` outputs report absence. The earlier 2016 excerpts therefore do not support the eight-of-eight claim. Raw proposal/committed replay entry are preserved unchanged.

The updated procedure itself is conditional: consult explicit absence notes before another focused fetch, while permitting a retry when earlier retrieval may have omitted relevant material. Seven examples support that rule, and its correctness does not require the erroneous eighth example. This is a disclosed model semantic limitation in rationale, not a transport/accounting defect. Companion JSON retains the exact decision, full entry and three exact source excerpts.

Historical B1 advice for concise summaries/revised focus is explicitly scoped to model-rendered fetches. It does not establish such behavior for current direct full-page fetching. Quote membership and valid evidence pointers do not alone establish semantic truth. External page facts were not fetched again.

These saved proposals do not seed fresh A/B harnesses. Prior failed attempts, original snapshots, raw output streams, errors and proposals remain untouched. No source, helper, installation, live process or research state was changed by this review. Companion JSON records source hashes, each actual call, every decision, subcall coverage, exact reconstruction evidence and limitations.
