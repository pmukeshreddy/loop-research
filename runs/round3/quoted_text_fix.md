# Lossless quoted-text sharing

The final A refiner failed on a 1,592,078-character backend prompt. V2's mixed quote lexer missed embedded JSON after prose apostrophes, and its literal references could not share raw fetched text with the same text embedded as a JSON string. The separately supplied 8,959-character schema was not the cause. The disk-only [failure diagnosis](refiner_input_failure.md) and [measurements](refiner_input_failure.json) preserve the rejected input, all five attempts and four retries, and the unsuccessful representation experiments.

The fix changes only the representation of the supplied logical planner input and the refiner instructions explaining that representation. It changes no observation selection, candidate accounting, schema rules, root instructions, models, budgets, retry policy or refinement timing.

## Representation and cost contract

V3 retains a table of literal strings. `{"$shared_text": N}` copies a raw string; `{"$json_quote": N}` applies `json.dumps(shared_texts[N], ensure_ascii=False)` **exactly once**, including the surrounding double quotes and escapes. Either reference can appear in a `$shared_text_parts` concatenation. The quote operation has no configurable depth and no recursively encoded table.

The candidate lexer considers double-quoted spans independently of prose apostrophes. A quoted occurrence is eligible only if decoding it and re-encoding it with the specified operation reproduces its exact spelling. Invalid JSON and noncanonical escaping remain literal text. The candidate encoding preserves every value, key, ordering and scalar type accepted by the existing JSON validator.

The new marker and its literal-object escaping apply only to v3. V1/v2 decoding treats `$json_quote` as ordinary data, and the complete prior v2 encoder and its marker-escape set remain intact. Malformed v3 references, booleans used as indices, extra marker fields and unsupported concatenation parts are rejected.

Selection compares the complete compact JSON character cost, including actual reference-index widths, escapes, table entries, concatenation objects and the outer wrapper. V3 is selected only when it is strictly smaller than both the complete v2 encoding and the original logical JSON; otherwise the original v2 result is retained. Ties retain v2. No input-limit threshold, task identity, site name or seeded lesson participates in selection.

## Exact saved-input verification

The explicit disk-only helper [verify_quoted_text_saved_input.py](verify_quoted_text_saved_input.py) takes a saved job, expected logical SHA and observed limit as arguments. The limit is a regression assertion, never an encoder parameter. It verifies archived wire/logical hashes, exact decoded JSON, unchanged schema evidence enumeration and unchanged original archive bytes. The [final receipt](quoted_text_saved_green.json) also binds all measurements to the executing source-file hashes.

| Measurement | Original | Fixed |
|---|---:|---:|
| Logical JSON characters | 1,984,123 | 1,984,123 |
| Wire characters | 1,588,531 | 851,924 |
| Refiner instructions | 3,365 | 3,885 |
| Backend prefix | 182 | 182 |
| Full backend prompt characters | 1,592,078 | **855,991** |
| Separate schema characters | 8,959 | 8,959 |

The fixed prompt is 736,087 characters smaller and has 192,585 characters of headroom against the observed 1,048,576-character limit. All 292 supplied trajectory records, three complete entries, two candidate groups and 344 evidence anchors remain. The logical SHA is unchanged:

`2cd53600de561fdfad4d7ce8832de41e756cbadec841ccc2ca522c5a3e37bcd2`

The schema SHA is unchanged:

`ffd3283e4bfe33a41a65207df8717e0bb51325114b47d79f9a06bf5040383542`

## Test evidence

The isolated branch starts at `e9b1dcd9d2e1a81e8d37ba09cdc028a6dd49feed`. Tests use the existing main `.venv` with the isolated source selected by pytest's `pythonpath`; no package installation or live calls occurred.

- The prior focused suite passed 134 tests before implementation.
- [New-test RED](quoted_text_red.log): 9 failed, 19 passed against v2. [Saved-input RED](quoted_text_saved_red.log) reproduced the exact 1,592,078-character failing prompt with unchanged hashes.
- [First implementation run](quoted_text_first_green.log): 10 failed, 152 passed. Eight failures were expected version/table-form assertions; those tests now run against both the unchanged v2 encoder and selected v3, preserving their size and equality checks. One new collision fixture repeated whole prompts and correctly preferred v2; its prompts were made distinct to test actual v3 escaping. The remaining failure exposed a real small-payload profitability regression; the original complete-wrapper test was kept and the encoder was corrected.
- [Final focused run](quoted_text_second_green.log): **193 passed**, including saved-input v1/v2/v3 compatibility, generic raw/quoted repetition, Unicode and all line endings, noncanonical spellings, malformed markers, literal collisions, original fallback behavior and complete candidate costs across three-digit indices.
- [Final saved-input receipt](quoted_text_saved_green.json): exact logical round trip and unchanged archive, including the real updated refiner instructions and backend prefix.
- Independent review by `fetch_review` ran the same 193 tests plus 300 deterministic generic property cases and independently reproduced the saved input and schema identities. Its separate receipt is `codec_review.md/json`.
- The [isolated full-suite attempt](quoted_text_full_suite.log) reported 950 passed, five failed and one deselected. All five failures were benchmark fixture revision checks: the local copy omitted the fixture repositories' `.git` directories, causing Git to resolve the enclosing worktree instead. Restoring only those directories from the existing pinned local fixtures yielded clean WANDR `ccb0baeb96f1c77a48e47f92122c57479ee99700` and WideSearch `9825ba7b140b71d81b364793f86dabe4cfed6749` checkouts. [Rerunning both entire affected test files](quoted_text_fixture_corrected.log) passed all 33 tests, including every previously failed node. No product/test changes were made for these failures. This is a failed full attempt plus a successful targeted correction, not a claim that a new full run passed; the parent still runs the required integrated suite.

The normal suite has no dependency on the ignored local failed archive. The separate saved-input command is:

```sh
PYTHONPATH=src /path/to/main/.venv/bin/python runs/round3/verify_quoted_text_saved_input.py \
  --job /path/to/archived/refine_state.json \
  --expected-logical-sha256 2cd53600de561fdfad4d7ce8832de41e756cbadec841ccc2ca522c5a3e37bcd2 \
  --max-prompt-chars 1048576
```

These checks establish losslessness for the **supplied logical planner payload**. They do not establish raw-trajectory losslessness: the inherited `c944f51` observation projection still omits later accumulated root prompts and locals/`rlm_calls` without an equality proof. This fix does not alter that policy. Unique, incompressible inputs can still exceed a finite provider limit. Successful live saved-input replay and a fresh research cohort remain separate integration gates owned by the parent.
