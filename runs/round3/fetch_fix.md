# Round 3 item 1 — full readable page transport

All Round 3 live page metrics use the **new `direct-readable-v1` fetch path**. Rounds 1–2 used model-mediated excerpts; cross-round changes do not isolate the transport from research decisions.

## Root cause and permission

The unchanged Round 2 evidence is analyzed in `fetch_gate_evidence.json` and the earlier appended checkpoint. `ResearchTools.fetch` called `CodexBackend.complete(purpose="fetch", web=True)` with a focus and an instruction to copy relevant page text. The web tool opened a source, but the REPL received the sub-model's final answer, not the opened document. `CodexBackend` archived native web events whose open results exposed metadata (including total lines), not a complete body. Asking that model for a longer answer cannot establish complete text transport. Focused extracts, repeated failed requests and occasional quotation refusals kept returned text small while root history, task, entries, code and printed results grew normally. For example, Round 2 A retained 12,187 fetched characters versus its 79,147-character largest root (0.1540×); B1-frozen retained 29,020 versus 122,054 (0.2378×). These are **old-path** observations, not Round 3 outcomes.

After presenting that evidence and stopping at item 1c, the user approved direct retrieval with full readable-text extraction, Codex discovery, general host eligibility, no model fallback, recorded download failures, and explicit cross-round labels.

## Diff and why it generalizes

`page_fetch.py` adds direct HTTP(S) retrieval in the trusted host process. Any public URL the agent selects is eligible, including URLs found by search; no domain lists or benchmark facts occur in the implementation. DNS results and each redirect must be public, connections use the checked IP, and HTTPS authenticates the original hostname. DNS, connection, header/body reads and PDF extraction obey the existing operation timeout; cancellation interrupts sockets. No automatic download retry exists.

Full HTML static readable text is extracted with the standard HTML parser; hidden/script/style/template content is omitted and layout whitespace normalized. Every visible occurrence is retained, including navigation, qualification and footer text; no relevance selection, padding, repetition, excerpt cap or root truncation is added. Optional HTML end tags are handled so hidden elements do not leak visibility into later text. Text documents are decoded without lossy character replacement. PDFs use installed Poppler `pdftotext` for all pages. JavaScript-only pages, scanned PDFs without readable text, HTTP failures, malformed/incomplete responses, unsupported encodings and extraction failures remain failed fetches with a reason, never model fallbacks.

`repl_tools.py` returns the full extraction into the existing REPL RPC path, uses normalized URL plus path version as the cache key, and records focus only as intent. Concurrent duplicate requests share the one result. Successful downloads archive exact response bytes, each redirect hop, full readable text, parser identity and byte/text SHA-256 receipts. Cache retrieval verifies the receipt and both raw/text artifacts; corruption fails visibly instead of silently re-downloading. Search remains the existing Codex path. Agent tool/resource documentation now describes these semantics and encourages code/sub-calls on retained variables. Existing root history is unchanged.

`archive_audit.py` verifies the new receipts and exact text returned in saved trajectories/cache/evidence. Both audits and metrics identify their fetch paths. Historical metadata-only archives remain readable with explicit unavailable raw sizes. The overlap measurement and quality checks are unchanged.

## Tests and evidence

Tests use local fixtures and local HTTP servers; the automatic offline guard now prohibits accidental direct network downloads as well as live Codex calls. Existing model-fetch fixtures were migrated to an injected HTTP response transport while retaining real parsing, receipts, cache/concurrency, order, failures, cancellation, prompt and worker assertions. Because direct fetch consumes no model calls, the worker budget fixture was adjusted to preserve its budget-exhaustion check. No test was dropped.

- `fetch_red.log`: missing direct transport and expected pre-fix failures.
- `fetch_audit_red.log`: receipt-integrity audit regression before its implementation.
- `fetch_review_red.log`: nine failures expose real deadline, cache integrity and optional-end-tag defects discovered during independent review; these are implementation errors, not live experimental outcomes.
- `fetch_deadline_red.log`: slow DNS exceeded the intended total timeout before bounded resolution was added; cancellation already passed.
- `fetch_final_targeted.log`: 70 passing direct fetch, telemetry and archive checks. Full HTML includes all 1,400 distinct fixture sections exactly once and the final qualification; both pages of a hand-built PDF survive. Real socket checks cover full-body transfer, trickling body timeout and cancellation during response headers. No fixture size contributes to live proof metrics.
- `fetch_final_suite.log`: 871 passed, 1 live test deselected in 92.09s, before the final line-ending correction. The final targeted 70-test run includes that correction; the integrated all-fixes suite will run before live work.

No main harness, saved Round 2 input, pinned RLM source, evaluator, research task, model selection or research budget was changed by this fix. Live size, overlap and quality verdicts remain **not yet demonstrated** until the requested new cohort runs.

Final independent review also reproduced CRLF/CR normalization by `Path.read_text()` during receipt validation. `fetch_line_endings_red.log` records the failure; byte reads plus explicit UTF-8 decoding/writing preserve exactly returned text. The final targeted run covers first fetch, cache reuse and archive verification with mixed original line endings.
