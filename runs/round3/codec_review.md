# Independent lossless codec review

Reviewer: `fetch_review`; 2026-10-20T04:21:09.126347+00:00. Reviewed author-owned final source in `runs/round3/worktrees/quoted-text`, based on `e9b1dcd9d2e1a81e8d37ba09cdc028a6dd49feed`. The source was uncommitted at review and is bound by the exact file hashes below.

No important defect found. The change preserves the full logical planner input while sharing raw strings with their exact JSON-quoted occurrences. Product edits are confined to the codec and its explanatory refiner instructions. No root prompt truncation, field projection, model/budget change, task/site-specific rule, schema change or evaluator change is present.

`_json_fragments` (shared_text.py:158) treats only double quotes as JSON boundaries, so prose apostrophes cannot hide evidence. `_unquote_canonical` (168–177) accepts a decoded string only if re-serializing it exactly reproduces its spelling. `$json_quote` performs one `json.dumps(..., ensure_ascii=False)` operation, including outer quotes. Noncanonical escapes remain unchanged. Literal-only table entries and the absence of a quote-depth parameter avoid recursive table expansion.

Selection uses actual serialized reference indices and escaped literals, checks each concatenation, removes unused table entries, and then requires the **complete** v3 wrapper to beat both compact original input and unchanged v2 output (189–251). V2 wins ties. This is a safe cost comparison, not a claim of globally optimal compression. Decoder checks preserve v1/v2 behavior, keep `$json_quote` literal in those older formats, escape literal marker-shaped objects in v3, and reject malformed marker shapes, booleans/invalid indices, nonliteral table entries and cyclic/non-JSON input (261–305). Refiner instructions (192–207) accurately specify these rules and decoded evidence pointers.

Independent targeted tests: **193 passed in 4.96s**, tool receipt `02d63f`, exit 0. This includes all shared-text, saved-input, and focused refine tests named in the companion JSON. An additional **300 deterministic generic property cases** passed (seed 821551; receipt `6dfcae`): mixed raw/quoted/noncanonical strings, Unicode/control characters, marker collisions and scalar types round-trip exactly; original data stays unchanged; private v2 output equals the original git version; selected output never exceeds v2 cost. These are retained tool-output receipts; no separate raw logs are claimed.

The original failing A job was read without modification and decoded independently using the original codec from git. Re-encoding with the reviewed source and decoding again preserved the exact **1,984,123-character logical JSON**, SHA-256 `2cd53600de561fdfad4d7ce8832de41e756cbadec841ccc2ca522c5a3e37bcd2`, including all **292 trajectory records and 344 evidence anchors**. The reconstructed output schema is byte-for-byte identical under its original JSON serialization: **8,959 characters**, SHA-256 `ffd3283e4bfe33a41a65207df8717e0bb51325114b47d79f9a06bf5040383542`. Original job hash remains `5ecca81175881e538d8f63d24e24480b4e0c6c929d0697fc4633bb5eace302d0`.

The new wire is **851,924 characters**. Including the revised refiner instructions and backend prefix, the complete request is **855,991 characters**, versus **1,592,078** originally. It is **192,585 characters below** the observed 1,048,576-character provider limit. Full new backend SHA-256: `a1275aeead23e7d4bcc10e6da32e3048a89cb6b0aaff0086830bf24a9f9cdb88`. This is an offline exact-payload measurement, not a live acceptance claim.

The existing fragment tests retain explicit legacy v2 checks and add v3 checks, so the format transition is not covered by weakening old compatibility assertions. New tests additionally cover whole-wrapper profitability, index widths, marker collisions, malformed references and raw/escaped identity.

Exact reviewed SHA-256:

- `src/loop_research/shared_text.py`: `21f8f633a5042ca7bcf23831a394326ec380b83b2579c9e1e5f38fb76a1849cf`
- `src/loop_research/refine.py`: `9e37d099ae0c8e22077a54ceb36b72eb9778ff670e1cc986d4867553278634c0`
- `tests/test_shared_text_quotes.py`: `438a9b130d20a8393b2d05228ccc3869d1861eb3460237cfd3c214b676f297d2`
- `tests/test_shared_text_fragments.py`: `9a8b0d7f30c2069ef4fa71e9e344fa53af61c1dc0dff9b8ddb896d8b15f04897`
- `tests/test_saved_refine_input.py`: `389f10c174b7668f1f3739f171aa2276e7dd7df55bf28a2c276dbbd1f92393c8`

A future input containing substantially more unique data can still exceed a finite provider limit; no lossless codec can promise otherwise. This patch neither drops fields nor changes that failure into success. No live calls, installation, product edits, research mutations or commits were performed by this review. Full-suite integration and any fresh cohort remain the parent's work.
