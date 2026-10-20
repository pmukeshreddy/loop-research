# Independent readable-controls review

No remaining blocking defect found in the reviewed bytes, based on read-only review and offline verification. Base at review: `4644b7b55eaefce7485026fa36f5e367e2adedb3`. Final source hashes:

- `page_fetch.py`: `7cfb41684c44017ca707ce269c321b56f0a71505b750074ac88eef4478a5ce13`
- `repl_tools.py`: `2df545b3d7b16a7abc684f9e22bb472e06c128f73934038d467941dae41113f2`
- `archive_audit.py`: `f06fecdf12357c4f853f320f9639121d2c38d70d74eb8b4f4b334bd343b0532b`

Independent focused suite: **114 passed in2.40s** (tool receipts070127/ae6b75; no separate original pytest log claimed). Independent production-flow replay of retained files: **49 B0-1 texts unchanged byte-for-byte**, all focus-independent cache hits; **four affected Frozen1 artifacts rejected with complete exact extraction bytes retained** (120/119/4/265 forbidden controls). No network/models were used. The JSON contains every artifact identity, exact output hash, and replay script.

Two reproduced audit defects were fixed before approval: missing rejected receipt/artifact was silently accepted; a failed receipt from another URL could be substituted. The final audit requires linked receipts and verifies request/owner identity and URL. The separately identified invalid-UTF8 downgrade is also closed through a distinct extraction-phase reason. Negative pre-download cases remain supported; a failed cache request is not forced to have its owner's status.

The change rejects forbidden Unicode Cc across PDF/text/visible HTML, permitting TAB/LF/CR/FF/VT/NEL. HTML normalization preserves U+001C–001F for rejection. Complete extraction and raw bodies remain archived; rejected text is neither sanitized nor admitted as successful evidence. Fresh policy-tagged cache entries cannot downgrade to legacy validation. Historical receipts remain transport-only evidence explicitly labelled as lacking the new readability validation.

Only the three product files above changed. Research root/pinned formatter, refiner transport/prompts, evaluator, model selection, budgets, scheduling and deadlines remain unchanged. No task/site-specific rule, count padding, truncation, fallback or automatic fetch/retry was added.

This strict policy reduces availability when one corrupt control occurs amid readable material. It does not detect every printable wrong glyph or establish general PDF/HTML semantic completeness. No live-quality success is claimed. The affected cohort remains superseded; all comparisons must use the common replacement code. Author's separate KIAS replay is not counted as an independent fifth replay here.
