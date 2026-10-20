# Final-refiner input-size failure

The `fair_slots_v1` A run reached root submission, then failed during automatic final refinement because its **prompt** exceeded the provider's character limit. The output schema was separate and small. This is a different product failure from the earlier concurrency starvation. No new B arm started, and no semantic score for this failed A is assigned here.

Source: `dab5cf89963805d20d3d305ba14d8c8611cd8cf4`. Run: `research-0fd1b020f55e4155989dcd8c40c418f1`. Final planner request/job: `e526f2d58c344551b9af464ae640f659` / `b07049d849e54bad8ece2a1237c8606d`. [Full measurements, hashes, preserved errors, exact source-occurrence examples, and trial results](refiner_input_failure.json).

## Exact failure and separation of causes

The first root `REPL code.end` with `answer_ready=true` is trace 1844 at 04:02:43.137263 UTC. Final refinement begins at trace 1864. Backend attempts 0–4, trace 1865–1878, all dispatch the same prompt hash `109048b0a26256192448e141ca917146ef77f19078ea9cf3cf72564f37f36564` and fail with `input_too_large`, actual characters 1,592,078 and maximum 1,048,576. All five dispatches/completions and four retries are retained; none produced a proposal or usage report. The final failure propagates to research trace 1883 at 04:03:04.917402 UTC. The manifest records `status: interrupted` with this RuntimeError; that status does not establish an operator interruption.

| Component | Exact characters |
|---|---:|
| Complete supplied logical payload, default JSON | 1,984,123 |
| Same payload, compact JSON | 1,970,560 |
| Shared-text-v2 wire payload | 1,588,531 |
| Refiner instructions | 3,365 |
| Archived planner prompt | 1,591,896 |
| Backend instruction prefix | 182 |
| Actual backend prompt / provider `actual_chars` | **1,592,078** |
| Provider input limit | **1,048,576** |
| Excess | **543,502** |
| Separate output schema | 8,959 |

The 344 evidence anchors occupy 6,359 compact JSON characters. They remain in the logical payload and the strict schema. Removing or weakening that enumeration would not fix the observed prompt limit; the provider's reported size exactly equals the prompt alone. Candidate accounting is also small: 1,138 compact characters for two groups preserving all 34 stalled-search and two failed-fetch occurrences.

The final supplied payload has three complete harness entries, 292 trajectory observations (61 model, 219 tool, 12 worker-iteration records), zero self-check issues and 36 signals. Its trajectory occupies 1,867,667 compact characters. Model-prompt fields account for 1,115,913 compact characters; tool results account for 466,684. The successful mid-task planner had only 458,546 logical / 326,921 wire characters and committed two entries. That earlier success did not test the final observation's larger and differently serialized evidence.

## Why v2 misses sufficient reuse

The existing representation is reversible, but its sharing candidates do not cover this input's duplication well:

1. **A mixed quote lexer can absorb JSON evidence into unrelated spans.** In `/trajectory/99/prompt`, the prose apostrophe in “person's” starts a 17,907-character single-quote span at character 180. The following match spans 66,982 characters. The actual JSON object begins at character 482. Thus the repeated page strings inside that object are not independently recognized. The exact offsets and prompt hash are recorded in the JSON report. Trying independent double-quoted segmentation saves 322,331 wire characters, but still exceeds the limit.
2. **Raw text and its JSON-quoted form are different literal strings.** The supplied observation retains original fetch text and later prompts embedding that text through `json.dumps`. V2 can share identical quoted occurrences with each other, but cannot represent a quoted occurrence by applying a specified JSON-quoting operation to the already retained raw literal. For example, `/trajectory/93/result/0` is 69,601 raw characters; its canonical 71,105-character quoted form appears in both `/trajectory/94/prompt` and `/trajectory/99/prompt`. Exact hashes and every measured occurrence are retained. Sharing these forms requires an explicit reversible representation rule, not deleting either occurrence.
3. **Factoring only the current literal table cannot suffice.** The v2 table occupies 257,567 characters, but its encoded `payload` member alone occupies 1,330,910. Even an impossible zero-cost table would leave at least 1,334,457 backend characters including the existing instructions. Recursive table sharing can complement a fix, but cannot by itself remove this failure.

The unchanged retry loop treats the permanent provider rejection like a retryable call failure. That explains the five identical rejected attempts and added delay; it did not create the oversized input. A separate backend correction is being implemented by another agent.

## Measured lossless candidates

All trials below operated on decoded saved input, changed no product source, and checked exact decoded equality, including every field/string occurrence. “Backend” adds the existing 3,547 instruction characters; a new format must measure its own final instructions.

| Offline representation trial | Wire characters | Backend with existing instructions | Fits observed limit |
|---|---:|---:|---|
| Existing v2 | 1,588,531 | 1,592,078 | No |
| Fragment-only selection instead of whole-value-first | 1,594,460 | 1,598,007 | No |
| Independent double-quote partition | 1,266,200 | 1,269,747 | No |
| Actual and escaped newline partition | 1,484,574 | 1,488,121 | No |
| Best of measured content-defined exact substring partitions | 1,326,807 | 1,330,354 | No |
| Independent double-quote partition plus canonical JSON-quoted references to raw strings, measured by `fetch_review` | **846,191** | **849,738** | **Yes** |

The last prototype was independently reported by `fetch_review`, with the same decoded logical SHA-256 `2cd53600de561fdfad4d7ce8832de41e756cbadec841ccc2ca522c5a3e37bcd2` and 198,838 characters of headroom using the old instructions. Its additional outer v2 factoring measured 796,049 wire characters. Those prototype results establish a promising representation change, not an implemented or live-validated fix; its separate analysis supplies the algorithm and evidence.

The smallest supported direction is a generic, inspectable representation that shares exact raw text with canonical JSON-quoted occurrences and avoids treating prose apostrophes as a reason to miss double-quoted JSON strings. Preserve v1/v2 decoding, exact reference/escape semantics, complete-cost selection, and every logical field. Any new quoting marker must specify exact escaping, preserve noncanonical literal spellings unchanged, and reject malformed references. Additional table factoring should be selected only if its complete serialized cost decreases.

This does **not** authorize dropping tool results, later history, usage/outcomes, candidates or schema validation; replacing observations with summaries; capping the root prompt/stdout; changing models/limits; task/site-specific branches; or forced lessons. Nor can a lossless codec guarantee arbitrary irreducible content fits a finite provider limit. Such a case must remain visible rather than silently omit evidence.

## Preservation boundary and next verification

[The Round 2 fix-quality review](../round2/fix_quality_review.md) distinguishes the pre-existing `c944f51` planner-observation policy from the codec: it retains the full initial task prompt and supplied observations but does not retain every subsequent root prompt in the planner observation. The pinned root formatter also has an inherited output cap. This diagnosis proposes no change to either boundary and makes no claim that either is globally lossless. Exact losslessness here means the **complete supplied logical planner payload**, whose original default serialization and SHA were independently reproduced from the archived v2 input.

A product fix needs tests for exact JSON quoting/unquoting, apostrophes preceding embedded JSON, Unicode/escape variants, marker collisions, malformed references, all preserved scalar/container types, old-format compatibility, strict candidate accounting, and full-cost selection. Replay this failed saved planner input with the new complete serialized instructions and unchanged logical payload; also repeat prior saved cases and the full offline suite. A replay success must retain all candidate decisions and does not establish a new research comparison. The parent will preserve the failed cohort and perform the authorized full fresh replay after source/preflight gates pass.

This diagnosis made no model/web calls, package installs, product edits, original archive/harness mutations, or new research runs. All measurements are from disk.
