The static extractor previously treated a nonempty extraction as readable. A
successful Poppler exit therefore admitted corrupt control glyphs into fetched
evidence, cache and subsequent model inputs. This correction rejects that text
without repairing or shortening it. It applies to the complete returned static
extraction for PDF, HTML and other supported text media.

The change was developed on `round3/readable-controls`, isolated at
`runs/round3/worktrees/readable-controls`, from
`4644b7b55eaefce7485026fa36f5e367e2adedb3`. The still-running historical cohort
uses installed runtime `9251c8e8925f57cf9fc924e0fd57b1bd0d74bd6d`; this work does
not change that installation, its source, its helpers or its archives.

**Observed cause and scope.** The retained B1 KIAS PDF is 6,703,854 bytes and has
89 pages. Poppler returned exit 0 and empty stderr, but its 307,969-character
extraction contains 115,418 forbidden control characters. Rendering page 3
shows legible English; its extracted 2,789 characters contain 2,236 forbidden
controls. The retained font inspection reports embedded Identity-H CID fonts
without Unicode maps. This is consistent with corrupt glyph mapping, rather
than a valid document consisting of control text; it is not a claim that every
font mapping has been reconstructed.

The complete input/output diagnosis and page rendering are preserved separately
under `runs/round3/cohorts/context_outputs_v1/B1.error_diagnosis.*` and
`B1.error_evidence/`. The oversized direct subcall remains an observed error:
1,202,528 agent-supplied characters plus the 182-character backend instruction
equals 1,202,710 characters, exceeding the provider limit by 154,134. There was
one permanent failed attempt and no retry. Agent recovery selected explicit
text windows; a later quote assertion and its repair remain historical errors.
The extractor acceptance defect is an independent product failure and requires
replacement common-source runs. Fixing it does not establish that every future
agent-created direct subcall will fit the provider limit.

**Policy.** `unicode-layout-controls-v1` permits the layout controls TAB
(U+0009), LF (U+000A), VT (U+000B), FF (U+000C), CR (U+000D) and NEL (U+0085).
It rejects every other Unicode category `Cc` character. It does not use
`str.isspace()` as the acceptance rule: that function also accepts U+001C–001F.
Those four code points account for 9,860 characters in the KIAS extraction,
explaining the earlier 105,558 versus 115,418 counts. The rule has no site,
task, length, ratio or model-input-limit threshold.

All valid returned PDF/plain-text bytes and Unicode survive unchanged. HTML
continues to exclude script, style, template and hidden content and to normalize
visible layout whitespace. Its normalizer now preserves U+001C–001F through to
validation instead of silently removing them as whitespace. Validation examines
the returned visible extraction, not irrelevant raw HTML markup; controls in
excluded hidden content do not cause rejection.

**Evidence and errors.** Before validation, the complete successful extractor
return is written as an immutable extraction artifact. The receipt records its
path, byte count, SHA-256, parser, decoded character count where available, and
complete control-code counts. A rejected extraction has no successful
`text_path`, `text_sha256` or `readable_chars`. Its full original bytes and all
raw HTTP redirect/download bytes remain available in the archive.

Invalid UTF-8 extractor output produces `FetchError` with the distinct reason
`extraction_decode_error`; the exact undecodable bytes remain archived and the
character count is unavailable. `decode_error` remains the earlier HTTP entity
decoding/decompression failure. The distinct phase prevents deleting a rejected
extractor artifact from making its receipt appear to precede extraction.
Forbidden controls produce `forbidden_control_characters`, with complete
per-code-point counts. No automatic retry, text stripping, repair, model or
browser fallback is introduced. An explicit later caller retry can fetch again.

This retention change concerns a returned extraction rejected by validation.
Existing nonzero Poppler exits remain `pdf_extraction_error`, with the raw PDF
and stderr reason retained; this change does not add a promise to retain partial
stdout from a parser that itself fails.

**Cache and audit compatibility.** The fetch path remains `direct-readable-v1`;
the policy is a separate receipt/request/telemetry field and fourth cache-key
component. Fresh fetch and cache consumers explicitly require that policy and
verify the full bytes, so an old namespace, copied old cache value, or removed
receipt policy cannot bypass new validation. Failed extractions never enter the
new cache or fetched-evidence collection. Preexisting stored history is preserved.

Historical receipts without a policy still support exact transport verification,
reported as `not_recorded_by_legacy_policy`. They are not relabeled as having
passed the new readability check. Current receipts recompute validation from
their complete retained bytes. The audit requires the receipt when a request
records its durable receipt ID or an extraction-rejection reason, and binds the
receipt ID and requested URL to that request/owner. It therefore detects missing
or substituted failed receipts as well as modified extraction bytes. Genuine
failures before a download still need no download artifact. A failed cache
integrity check can refer to a prior successful owner's receipt; the audit does
not equate those two statuses.

Receipt consistency is not a cryptographic defense against a coordinated rewrite
of every request, receipt, cache and artifact. Externally preserved whole-archive
hash inventories remain the authority for that stronger historical claim.

**Test evidence.** All tests are offline; the existing suite forbids live Codex
and un-injected HTTP requests. The new tests exercise all 59 forbidden C0/C1
code points, explicitly allowed layouts and valid Unicode, mixed readable and
corrupt text, hidden HTML, invalid UTF-8 PDF output, exact rejected bytes, cache
reuse/separation and deliberate artifact/metadata/receipt tampering.

- Baseline: 71 existing direct-fetch, telemetry and archive tests passed.
- Initial RED: 29 failures. Three were a new legacy-fixture setup bug (missing
  parent directories); their setup was fixed and the original log retained.
- First implementation attempt: 95 passed and 5 failed; the three fixture
  failures plus two existing tests referring to the old cache key were corrected.
  The cache-integrity test still damages the actual active cache value.
- Corrected RED against unchanged main source: 33 failures.
- Additional missing-rejected-artifact RED: 1 failure; then 105 focused passed.
- Independent decode-phase review found a metadata-removal gap: its new RED
  failed to raise, then 106 focused passed after the distinct extraction reason.
- Independent failed-receipt review found missing telemetry and swapped receipt
  gaps. Seven tamper cases failed to raise. One negative-control test also used
  an incorrect telemetry `reason` assertion; it now reads the existing evidence
  field. The original eight-failure log remains preserved.
- Final focused command:
  `.venv/bin/python -m pytest -q tests/test_readable_controls.py tests/test_direct_fetch.py tests/test_fetch_telemetry.py tests/test_archive_audit.py`
  ran with the main virtualenv and isolated worktree source: **114 passed**.
- The parent's first broader run finished with 5 failures, 1,098 passes and
  5 setup errors (1 deselected). Four failures and the five setup errors were
  missing pinned WANDR fixtures in this isolated worktree. One existing
  `test_agent_tools.py` parameter raised an extraction-stage `no_readable_text`
  error directly from its fake HTTP request; the new contract correctly rejected
  its missing extraction artifact. That parameter now returns real hidden-only
  HTML and checks the actual retained empty extraction, raw bytes, parser and
  error, while retaining the no-cache/no-evidence/no-fallback assertions. Other
  HTTP/download-error parameters are unchanged. Its local RED was 1 failure and
  2 passes; adding all `test_agent_tools.py` cases to the focused command then
  produced **161 passes**. Product source did not change for this fixture repair.

`readable_controls_evidence/` retains every RED/intermediate/GREEN log rather
than replacing unsuccessful evidence. Independent reviews are retained in
`runs/round3/readable_controls_independent_review.md/.json` and
`runs/round3/readable_controls_policy_review.md/.json`; both reviewed the final
product hashes and independently passed the 114-test focused suite.

After copying the existing pinned WANDR fixtures into the isolated worktree and
repairing that single HTTP test fixture, the parent reran the complete suite:
**1,108 passed, 1 deselected in 147.03 seconds**, exit 0. Its 32 recorded product
module hashes remained unchanged. The original unsuccessful broader log,
fixture-preparation correction and successful receipt/log are retained under
`runs/round3/readable_controls/whole_suite.log`,
`fixture_preparation_correction.json`, and
`whole_suite_fixed.result.json`/`whole_suite_fixed.log`. No dependency installation
or live call was used for either test run.

**Retained-input verification.** `verify_readable_controls_saved.py` consumes
only archived HTTP hop bytes and executes the installed Poppler/static extractor.
It checks complete extraction-byte identity, new receipt integrity and unchanged
original source hashes. Its saved result covers 163 original files and these
five actual rejected extractions:

| Historical arm/request | Full extracted characters | Forbidden controls |
| --- | ---: | ---: |
| B1 / 96, KIAS PDF | 307,969 | 115,418 |
| B1-frozen-1 / 49, Christ's Magazine PDF | 395,839 | 120 |
| B1-frozen-1 / 56, UNN brochure PDF | 172,443 | 119 |
| B1-frozen-1 / 88, ORF HTML | 8,822 | 4 |
| B1-frozen-1 / 158, GFDL bulletin PDF | 19,929 | 265 |

All five were rejected with byte-identical extraction artifacts. All 49 B0-1
successful pages, totaling 872,468 retained characters, succeeded again with
byte-identical full text. All original source files remained unchanged. The
separate replay artifact directory contains complete copies and is not committed;
the source-bound summary and executable replay script are retained.

The deliberate availability tradeoff is that a partly readable document with
even one forbidden control is rejected in full. This is a necessary validity
check, not a general semantic-quality guarantee: printable glyph substitutions,
missing content, and misleading readable prose can still pass. No root prompt,
model, budget, refinement timing, dependency pin or new fetch mechanism changes.
