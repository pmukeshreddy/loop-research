# Round 3 comparison-input investigation and fix

This work used archived files and offline tests only. No research, web, model, refinement, or live-test calls were made. Implementation is isolated on `round3/comparison`, based on `1752a36`, under `runs/round3/worktrees/comparison`. The shared harness and Round 2 archives were read, never changed.

## Scope and evidence

The authoritative final pair is B0 `research-f37257f9ddb845a3ae35992e1f944927` and B1-frozen `research-a0d4fedc1c544fa2b0be4a55f13641b7`, both task `5f579a96530b9d0b8eaa08f9`. Their bases are `2a423027212fe1c430dfd200bdd55f3a27b22d70` and POST_A `29d290b53bfa877e2223dc232dffb60233b32c15` respectively.

Inputs inspected: `runs/round2/manifest.json`, `control_audit.json`, `control_audit.py`, both runs' `research.json`, `config.json`, `task.json`, `as_of.json`, `prompt.txt`, `root_prompt.txt`, and first actual root records in `trajectory.jsonl`; immutable harness states were read with `git show`. Seven superseded B0/frozen date archives were also checked. Complete first-root prompts and their unified diff are saved as `B0.original_initial_root.txt`, `B1-frozen.original_initial_root.txt`, and `comparison_initial_root.diff` beside this file. `comparison_evidence.json` retains all changed base-state paths and full before/after values, all first-root entry sections, exact hashes/counts, date evidence, and the non-entry first-root diff.

## Every difference and its cause

| Surface | Observed difference | Cause and treatment |
| --- | --- | --- |
| Task/config/date/instructions in saved context | None outside complete entries. `prompt.txt == root_prompt.txt` within both arms. | Existing Round 2 audit is correct for these saved files. Its shared context-without-harness hash is `8e0e102f97ba154850912e16f6ab493b5bd2c3a83245cf85e4fbff4e0d788764`. |
| Complete base entries | Three entry objects change: two new learned entries and historical A usage/outcomes on the existing memory. The first root retrieves the new skill and existing memory in B1-frozen, versus only the existing memory in B0. | Allowed harness-state intervention. All fields, including historical usage, outcomes, provenance, timestamps, versions, bodies and modules, remain intact. This does **not** isolate lesson bodies from prior A bookkeeping. |
| Base-level bookkeeping | `/usage`, `/outcomes`, and `/seen/research:289901ce021c28d56fdac993` change between BASE and POST_A. | Genuine A history, stored in harness state; the root receives entry objects rather than these top-level containers. No filtering or erasure introduced. |
| Current-run entry bookkeeping in first actual root | The initial `RELEVANT HARNESS` section contains base entries, but `CURRENT RELEVANT HARNESS ENTRIES` additionally contains each arm's newly generated run ID in `usage`. | `run_task()` retrieves and records usage; the first root call retrieves again, exposing that just-written metadata. Fixed by durable per-task usage journaling and attaching usage only after researcher shutdown. |
| Actual root text outside entry payloads | Exactly one difference: `Your context is a str of 7600 total characters.` versus `...16855 total characters.`. Replacing only complete entry JSON and this derived sentence makes the actual first-root remainders identical. | Pinned RLM generates aggregate-length framing from the full, differently sized entry-bearing context. The local adapter now uses stable truthful framing; exact counts remain archived and traced. |
| Date provenance | No difference: both final dates are `{policy: "2026-10-18", task_date: null, as_of_date: "2026-10-18", date_source: "config"}`. All seven inspected superseded B0/frozen dates have the same values. | No date bug established. No speculative date code change. Offline worker parity tests cover task, explicit config, and `today` provenance. `today` across genuinely different calendar days is a different effective input; a controlled cross-day comparison must pin its date. |
| Run manifests, traces, paths and commit IDs | Arm identities, paths, lineage, timestamps, return branches, duration and resulting metadata/history naturally differ. | Observational provenance belongs in archives/history and is preserved. It is not injected as current-run usage in researcher entry reads. |
| Later prompts, calls, outputs and self-check outcomes | Research trajectories diverge after the first model response. | Different entries, model/web nondeterminism, responses, tool results and subsequent decisions change later inputs. Forcing those equal would overwrite research evidence and is outside the comparison contract. |

The prior `control_audit.py` only compared saved `prompt.txt`/`root_prompt.txt`, so it did not detect the generated first-call length sentence or the extra current-run usage attachment. The new tests compare actual backend inputs from real isolated workers.

## General implementation

`Session.record_usage()` writes an atomic per-task `harness_usage.json` journal containing every distinct consumed entry identity and version. All automatic retrieval and worker `get/read/list/search` paths use it. Researcher reads continue returning complete real entry objects with their preexisting usage and outcomes. No fields are removed or replaced. `close_worker()` first cancels further researcher work, then commits the journal through the existing idempotent `Harness.record_usage()` API. Thus normal success, failure/cancellation cleanup and resumed finish retain correct history before final outcome recording and after-task refinement. A journal write failure does not advance in-memory state, so a retry cannot silently skip the durable write. The journal remains as provenance after commit.

The local `CodexRLM._setup_prompt()` changes only the pinned generator's known suffix. Before:

> Your context is a str of N total characters. Each sub-LLM call can handle roughly ~100k tokens at once.

After:

> Your context is a str. Inspect its size with Python len(context). Each sub-LLM call can handle roughly ~100k tokens at once.

The actual type is retained. The adapter verifies the expected generated suffix and changes only that suffix, so matching text inside the task cannot be rewritten. The exact full context remains in the REPL, `prompt.txt`, and `root_prompt.txt`; `prompt_metadata.json` records its type and character count even with tracing off. With tracing on, `RLM/context_metadata` records the computed type/count for root and child contexts. No task, instruction, entry, fetched evidence, stdout, response or history is truncated, summarized, capped or filtered. Pinned dependencies are unchanged.

“Only entries” means complete JSON entry payloads may differ when explicit bases differ. Given the same task, spec, effective date/provenance, config and learning mode, initial actual root text outside those payloads is identical. With the same base, the entire actual first-root prompt is identical even though run IDs differ. This claim concerns controlled initial inputs, not model-generated later trajectories or storage metadata equality.

## Tests and integration

`tests/test_comparison_inputs.py` exercises real isolated RLM workers with only the external model backend replaced. It checks same-base full-root equality, different-base equality outside complete entries, unchanged full REPL context, preserved historical fields, durable current-run usage and final outcomes, resume/idempotence, retry after journal write failure, exact count archives/traces, and actual-root date parity for config/today/task provenance.

Red evidence: `comparison_red.log` reports four expected failures and three already-correct date checks. `comparison_journal_red.log` shows the explicit write-failure/retry regression failing before its fix. The first broad focused run, `comparison_focused_green.log`, reports 128 passed and one old trace expectation failure: `test_retrieval_trace_records_scores_without_changing_entries` required a harness commit during retrieval. That expectation was updated to the authorized deferred-commit behavior, preserving its score/entry checks and adding assertions for a durable journal, a commit on shutdown, and exact persisted usage. No test was dropped or weakened.

Final focused verification: **129 passed in 53.48s**, exit 0, in `comparison_focused_final.log`. This runs the new comparisons plus worker, session, stream, harness, agent/tool, mid-task refinement and trace tests. `comparison_final_green.log` separately records **19 passed in 19.26s** for the final comparison and trace cases. `git diff --check` passes.

The parent performs the full-suite check after integrating the independent Round 3 fixes. The session retrieval call site overlaps the same-run retrieval work; preserve both the new entry union and this journal call during integration. No changes to `stream.py`, `harness.py`, date resolution, CLI base selection, benchmark data or shared harness state were needed.

## Parent integration and independent review

Merged after `313603d` (direct fetch) and `fd1be81` (same-run feedback), preserving the complete current-run/relevance union and changing only its bookkeeping call to the durable journal. The existing migrated direct-fetch trace fixtures remain in place. An independent reviewer found no significant defect in these changes, including shutdown ordering, read-only status and optional audit segmentation. The generated numeric metadata sentence replacement is an explicit framing change; it is not described as unchanged prompt bytes. Full supplied context/history/entries are preserved and exact lengths archived. The integrated suite result is recorded in `integrated_suite.log` and the Round 3 preflight receipt.
