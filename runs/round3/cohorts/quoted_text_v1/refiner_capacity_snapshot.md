# Refiner capacity snapshot — incomplete A run

Captured 2026-10-20T04:39:53.351277+00:00 through 2026-10-20T04:39:53.355680+00:00, source `09c77902babb879abe2b0dcc8cab7cf5209bf5ae`, run `research-f43c96b33c5d43b299e491341eb65216`. Latest captured trace timestamp: 2026-10-20T04:34:17.957669+00:00. Manifest remains running; no actual saved refinement planner request exists. No live run/source/harness/process was modified.

The current archived trajectory projection is **not the full downloaded corpus**. It has 68 records and, with the existing product observation rules, the captured empty-output self-check, current harness entries and automatic-focus assumption, selects v3 at **308,838 wire / 312,905 backend characters**. This is a nonfinal in-memory candidate, not a submitted request or the finalizer's future input.

An active **75-URL fetch_many** starts at trace 716, timestamp 2026-10-20T04:33:36.570088+00:00, and has no matching call.end. Its **66 already successful full texts total 1,245,775 characters**. `Session._dispatch` appends the batch result only after the entire call returns (session.py:198–202), so these values are not yet in its trajectory return. Current evidence has 84 successful, 9 failed and 1 pending requests; the pending URL is listed in the JSON.

Current codec measurements of known retained data:

| Measured value | Literal compact JSON | v2 wire | v3 wire | Selected |
|---|---:|---:|---:|---|
| Nonfinal retained planner projection | 418,383 | 366,503 | 308,838 | v3 |
| Known unreturned URL→full-text component | 1,276,886 | 1,234,166 | 1,276,258 | v2 |
| All retained URL→full-text values | 1,430,375 | 1,366,235 | 1,429,747 | v2 |
| Explicit diagnostic envelope: projection + known unreturned texts | 1,695,332 | 1,599,167 | 1,584,864 | shared-text-v3 |

The source component alone selects **1,234,166 characters**, already above the observed **1,048,576-character** provider input limit before instructions. This supports a capacity risk. Neither component nor the explicitly synthetic envelope is a real planner input; no unknown pending result, final output, future subcall, constraint or harness outcome was invented. All measured encodings round-trip exactly.

There are **84 full-text occurrences / 84 distinct full-text SHA-256 values**, totaling **1,395,914 characters**, with no duplicate whole-page group. This does not mean the pages have no repeated internal text. The JSON gives per-URL hashes, global exact-string occurrence/unique-literal costs, codec table/payload costs, source rules, captured file hashes and assumptions. Existing product projection removes repeated later-root prompt fields and repeated worker prompt/response/locals/rlm_calls; no new truncation or field selection was introduced for this diagnostic.

If the eventual actual saved input confirms this risk, a general option is to retain the **complete immutable logical snapshot** in an isolated read-only refiner REPL/file and let the same refiner model use code and subcalls to inspect full values by stable pointers. Preserve the candidate inventory and every occurrence reference, require every decision, retain the unchanged Proposal schema/max_edits/host validation, and keep existing background scheduling and boundary/finalization semantics. This is a design option, not authorized implementation or a change to the active run. Additional generic inspectable lossless factoring can also be measured offline, but no representation can guarantee arbitrary unique data fits a fixed cap. Field dropping, summaries, threshold-tuned selections and truncation are not supported.

There is **no observed planner product failure at this snapshot**. Final request size is unavailable, and serialization cost need not be monotone as future records arrive. Files were read without locks and rechecked unchanged immediately after capture; they can advance afterward. This report is not a final archive audit or a reason to stop the run.
