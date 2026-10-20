# Round 3 — fixes, completed runs, and demonstrated limits


## Round 3 outcomes

The three implementation fixes have separate commits, root causes and regression tests. All nine main runs and the separate explicit diagnostic finished on the same final runtime. The full integrated suite passed 1,110 tests with one live test deselected; saved refinement/audit checks and a clean BASE rollback preceded the replacement A/SI runs. Predictions were committed after A and before B. The report preserves earlier failed/superseded work and every final-cohort error.

| Open item | Before | Round 3, **new fetch path** | Verdict |
|---|---|---|---|
| Full pages and size criterion | Model-mediated fetched text was smaller than the largest root in every Round 2 arm. A: 12,187 / 79,147 chars. | Full pages are retained in variables and used through code/subcalls. Main Nobel ratios are 5.259–19.118×, overlap 0.0420%–6.7700%, with the same 28 identities, zero mechanical issues and zero uncited cells. SI is only 2.381×; the separate explicit diagnostic is 1.165×. Semantic completeness is separately qualified. | **Works** for transport and the main Nobel demonstration; the size conjunction is **not demonstrated across tasks**. No new cutoff, padding or count-driven fetching is used. |
| Same-run reuse | A's midtask entry appeared in 0/11 later retrievals; the old explicit probe used 24 pause blocks / 985 declared sleep seconds. | A's two midtask entries reached all 7 later root inputs; B1's two reached all 8 later inputs, followed by compatible executed actions and no refinement-wait turns. The new explicit run used 6 root turns, no waiting, and correctly handled a completed zero-edit decline. | The delivery/status fix **works**. The specifically requested explicit committed-entry-reuse chain is **not exercised**, because no midtask entry was created. The old/new explicit tasks differ; turn counts are mechanism evidence, not an isolated speed estimate. |
| Input isolation and benefit | Current-run bookkeeping and a generated context-length sentence differed outside complete harness entries; the single Round 2 frozen/base comparison did not show benefit. | All 6 controlled initial inputs pass exact same-base and outside-entry parity. Frozen attempts average 90.667 versus B0 117.667; difference −27 does not exceed spread 59. Some resource signals exceed spread, while a post-registration nationality-completeness diagnostic worsens beyond its spread. | Isolation **works**; consistent self-improvement benefit is **not demonstrated**. Three repeats are not a statistical result. |

## Full ten-check table

The ten original check identities are preserved. “Works” is scoped to the behavior actually evidenced; it does not turn a mechanical pass into semantic completeness or a sequence into a causal estimate.

| Check | Original subject | Verdict | Round 3 evidence |
|---|---|---|---|
| 1a | Actual subcalls and exact input sizes | **works** | Every main arm has actual research subcalls with exact logical/schema/backend sizes and executed result use. Refinement calls are separate. Frozen1's failed oversized attempt is separately counted. The **explicit** child runs 3 REPL turns on 61,328 characters and returns a 1,223-character result that the root validates and uses. [All metrics](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/final_metrics/metrics.json), [failed-input ledger](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/B1-frozen-1.failed_subcall_inputs.json), [explicit review](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/explicit.review.md). |
| 1b | Page text handled in REPL variables | **works** | Direct readable bodies reproduce from retained raw responses and enter source dictionaries; code selects/serializes evidence and consumes sub-results. B1's 7,343-character release has exact input/result bindings; A retains the full 324,148-character CV before code selects a span. [A audit](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/audits/A.audit.json), [B1 full-text chain](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/B1.review.md), [all storage hashes](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/page_storage_counts.final.json). |
| 1c | Agent-initiated midtask timing | **works** | A/B1/SI choose their refinement timing before worker exit. A and B1 also commit/deliver before exit; SI commits afterward. The explicit request is separately labeled and its completed decline is truthful. No automatic refinement trigger or forced edit was introduced. [A entries](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/A.entry_review.md), [B1 timing](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/B1.review.md), [SI](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/SI.review.md), [explicit](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/explicit.review.md). |
| 2a | Raw opened pages versus returned text | **works** on the new path | Round 2's native web opens had metadata but no retained full-body field; the approval gate is preserved. New raw HTTP bodies, complete readable text, receipts and failed-download reasons are auditable; no model-mediated fetch fallback exists. [Gate evidence](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/fetch_gate_evidence.json), [storage decomposition](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/page_storage_counts.final.json), [fetch implementation](/Users/mukeshreddypochamreddy/Desktop/loop-research/src/loop_research/page_fetch.py). |
| 2b | Largest actual root prompt partition | **works** | Seven disjoint components sum exactly for every main root maximum, from SI's 28,594 to B1's 175,270 characters. Complete harness metadata remains included; no new research-root truncation was used. [Per-run partitions](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/run_summary.md), [full audit-derived metrics](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/final_metrics/metrics.json). |
| 2c | Exact page/root overlap | **works** | Unchanged case/whitespace-sensitive 50-gram coverage uses the union of all research roots and the retained-text denominator. Main-arm overlap ranges 0.0420%–6.7700%. Frozen3's URL-text total and whole-hash-deduplicated total are separately reported; whole hashes do not imply globally unique information. [Full overlap records](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/final_metrics/metrics.json), [hash decomposition](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/page_storage_counts.final.json). |
| 2d | Fetched text far exceeds largest root, low overlap, same rows/quality | **not demonstrated across tasks** | Main Nobel runs have 5.259–19.118× ratios, low overlap, identical identities after reviewed aliases, 0 mechanical issues and 0 uncited cells. SI's 2.381× and explicit's 1.165× do not establish “far exceeds.” The broader semantic review finds omissions and one selected-quote limitation; those are not erased by the mechanical criterion. [Main table](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/run_summary.md), [semantic review](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/completed_B_report.md), [explicit](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/explicit.review.md). |
| 3 | Use of the historical Boolean-verdict memory | **not exercised** | Historical entry `25c641be4308494f907cb85b2691901a` is absent from all 10 recorded final run heads. The old shared Boolean argument contract and 168 True calls in each historical arm were not causal evidence. This check is not replaced with new-entry reuse. [Current lineage check](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/historical_boolean_memory.final.json), [historical lineage](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round2/boolean_memory_lineage.md). |
| 4a | After-task candidate accounting and refinement | **works** | Complete supplied inputs, candidate decisions, accepted/declined reasons, edits and commits are verified. A finalizes two edits; B1's final 8 decisions map to 2 updates; explicit's finalizer creates 1 memory only after worker exit. Zero-edit outcomes remain valid. Overflow feedback is retained behind references, but no live reference read is credited. [A entry review](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/A.entry_review.md), [B1](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/B1.review.md), [explicit](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/explicit.review.md), [saved checks](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/preflight.json). |
| 4b | Controlled frozen benefit | **not demonstrated** | All six initial controls pass, all 100 aggregate metrics include individual values/means/min–max/defined N and strict spread comparisons. Total attempts improve within spread; root/search counts improve beyond spread; registered behavior results are flat, contrary, unexercised or within spread. The common nationality diagnostic worsens beyond spread. Only one of A's three new entries is exposed in frozen roots. Three repeats are **not statistical evidence**. [Complete tables](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/final_metrics/metrics.md), [interpretation](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/completed_B_report.md), [input audit](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/control_audit/control_audit.json). |



All fresh results in this section use the **new fetch path, `direct-readable-v1`**. Rounds 1–2 used model-mediated returns; their resource, size and overlap differences are not an isolated estimate of learning. The former `9251c8e8925f57cf9fc924e0fd57b1bd0d74bd6d` cohort is superseded because static extraction admitted corrupt control glyphs. Its results are retained as historical evidence only. Replacement common runtime is `902abe33d06f64c426a65d55d5e600dd6d6a052a`; all 32 installed modules match the exact tested source. Replacement A and SI started in parallel at 2026-10-20T17:49:28.756886+00:00 and completed naturally. A finished at 18:13:03.833090 UTC; SI finished earlier at 17:52:31 UTC. The B phase began at 18:22:05.319633 UTC after the prediction commit. The exact tasks, models, date policy (`2026-10-18`, config provenance), four shared model slots and research budgets remain fixed.

The final results, verdicts, per-run metrics and ten-check table below distinguish transport correctness, mechanical checks, semantic support, actual reuse and measured benefit. A valid decline is not an error, a delivered entry is not automatically used, and a matching action is not by itself evidence that the entry caused it.

## 1. Full readable pages

**Root cause.** The former `ResearchTools.fetch → CodexBackend.complete(purpose="fetch", web=True)` returned the sub-model's final message. The native web open was a different boundary: Round 2's 375 observed opens exposed line-count metadata and no full-body field. A 122-line open yielded a 270-character refusal; a focused retry yielded 509 characters. Meanwhile complete task instructions, code, printed outputs and root history accumulated. Hence A's fetched 12,187 characters stayed below its largest 79,147-character root, and frozen B's 29,020 stayed below 122,054. These are **old-fetch-path** measurements. [Gate evidence](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/fetch_gate_evidence.json), [Round 2 source trace](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/research-65cc14c4722a4caf9c67f56e2883a0ca/289901ce021c28d56fdac993/codex_calls.jsonl:47).

**Diff and generalization.** After the recorded stop-and-ask and user approval, commit `313603d1abf58a64f3fa8f22585a477fc776a574` replaced model-rendered fetch returns with direct retrieval. Any agent-selected public HTTP(S) URL is eligible, including search hits; there is no hand-picked site list. Checked DNS addresses and every redirect must be public, connections pin the checked IP and HTTPS authenticates the original hostname. Codex web search still discovers sources. Static HTML/text extraction retains full readable content; Poppler extracts every PDF page. The entire returned text enters REPL variables for code/subcalls. Focus is intent metadata and cannot shorten a page. Exact response bytes, redirect hops, extracted text and hashes remain on disk. The cache verifies those receipts. Failed downloads record their reasons, with no model fallback or automatic re-download. No padding, duplicated content, count-driven fetching or new research-root truncation is used. [Implementation](/Users/mukeshreddypochamreddy/Desktop/loop-research/src/loop_research/page_fetch.py), [RPC/cache path](/Users/mukeshreddypochamreddy/Desktop/loop-research/src/loop_research/repl_tools.py), [fix and tests](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/fetch_fix.md).

Tests cover full multi-section HTML and multi-page PDFs, hidden/optional tags, CRLF preservation, redirects, public-address validation, cancellation/deadlines, cache integrity and actual isolated-worker transport. Final targeted fetch/audit checks: **70 passed**; the final integrated suite below covers all fixes. Static extraction cannot render JavaScript or OCR an image-only page; such failures remain visible. Raw bytes, readable characters and returned characters are reported separately. Full text in a variable alone does not establish the required size/overlap/quality conjunction.

## 2. Same-run reuse

**Root cause.** `refine.run()` acknowledged scheduling, but `Refiner.boundary()` returned `[]` both while pending and after a completed zero-edit proposal. The root could not distinguish those states. Round 2's explicit probe consequently spent **24 pause blocks / 985 declared sleep seconds**, finishing on root turn 30 despite a completed decline at trace255. Separately, `Session.retrieve → Harness.search` used only question/schema BM25; a generic new lesson scored zero and was excluded. Round 2 A committed `d8b0266283de48cf91d4ddf431354ade` **731.660464 seconds before worker exit**, yet **0/11 later retrievals** returned it. [Completion visibility](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round2/explicit_refine_status_analysis.md), [missed retrievals](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round2/A.refine_analysis.md:488).

**Diff and generalization.** Commit `fd1be810937de45c3e48845a50fbcd5b144d7be3` adds nonblocking durable `Refiner.status()` with complete proposals, decisions, errors, request/job IDs and proven commit receipts. Existing root boundaries apply ready work without waiting, then supply that status and full entries. Retrieval unions complete committed current-run entries with the unchanged relevance results, deduplicating identities without dropping metadata or fabricating positive scores. The agent still chooses whether, when and why to request refinement. No automatic mid-task trigger, forced edit, sleeping or polling was introduced. Provenance and lifecycle govern this behavior, independently of task or site. [Status implementation](/Users/mukeshreddypochamreddy/Desktop/loop-research/src/loop_research/refine.py), [retrieval/feedback](/Users/mukeshreddypochamreddy/Desktop/loop-research/src/loop_research/session.py), [fix evidence](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/same_run_fix.md).

Offline isolated-worker regressions cover zero-score delivery, complete zero-edit decisions, no-request/no-scheduling, pending-job completion, interrupted application/resume and full-field integrity. One retained regression has commit→retrieval→executed quotation check at trace54→56→77, **two root blocks and no waiting**; this is scripted plumbing evidence, not spontaneous model judgment. The integrated status/audit suite had **64 passes**. Fresh spontaneous and separately labeled **explicit** request→commit→retrieval→action chains are assessed below, without crediting finalizer-only edits.

## 3. Comparable inputs and self-improvement benefit

**Root cause of every initial non-entry difference.** Round 2's saved context comparison missed the actual generated backend input. Immediate usage commits inserted each new run ID into later entry reads before the first root call. Pinned RLM also generated `Your context is a str of 7600 total characters` versus `16855`, leaking entry size outside the entry region. Date provenance already matched in both final controls and all seven inspected earlier date archives: no date bug was established. Top-level A history differed in storage but was not passed to the root. Run IDs, paths, timestamps and later model/tool trajectories legitimately differ in archives. [Complete input diagnosis and exact diff](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/comparison_fix.md), [evidence](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/comparison_evidence.json).

**Diff and generalization.** Commit `8d45343786529f6573d87cb5d3ae9c2a6d6e0385` journals current-run usage durably and attaches it after researcher shutdown, before outcomes/final refinement. Reads preserve all preexisting metadata and complete entry objects. The local adapter changes only the pinned generator's known size sentence to truthful stable framing: “Inspect its size with Python len(context).” Exact full contexts and lengths remain archived. No task text, entry fields or observations are filtered to obtain parity. Actual isolated-backend tests cover same-base byte equality, cross-base equality outside complete entry regions, preserved historical fields, durable usage/resume/write-failure recovery and task/config/today date provenance; **129 focused tests passed**. [Tests and implementation details](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/comparison_fix.md).

The intervention is the **complete harness entry objects**, including A's historical usage/outcomes; it does not isolate lesson prose. Equality applies to initial controlled inputs. Later inputs may diverge because the model and retrieved content vary. The six-run control audit below verifies actual backend inputs, complete metadata, dates, installed source, independent trees/caches and disabled procedural learning.

**Predictions committed before B.** The completed A added memory `6bc3c4962d6e4eafab63ed0189268ec3` (exact spans, final v2), memory `b98beb481e414d02952f80dbd258928e` (duplicate reconciliation, v1), and skill `f9d1625b7c1a49a7824cc94063b6be4c` (partial-fetch recovery, v1). Existing discovery memory `bf8ebe4929de4c4493017583193abedc` kept its procedure and version; only usage/outcomes changed. [Complete before/after objects and candidate review](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/A.entry_review.md).

The replacement [predictions](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/predictions.md), SHA-256 `cec6bffde76d8a79aeac7c037dde65910e6fcac1927e899d63d8624582951f78`, were first written at 18:18:26.938062 UTC and committed as **`2ecab945810592a7b9e084c3d3c5dc8b00a4f20a` at 18:21:53 UTC**, after A's terminal receipt and before the first B at 18:22:05.319633 UTC. The launch gate verified the commit and exact POST_A `d63478eec4f3acd9a71662e79a44183008a364d9`. The [independent review](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/prediction_review.md) distinguishes its prelaunch review from the later documentation of timestamps. The superseded predictions remain byte-exact at [their historical copy](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/context_outputs_v1/predictions.superseded_context_outputs_v1.md). Prior B results were seen: this registration is prospective for this cohort, **not blind**.

Predicted changes are more complete pre-submission guards (S1), fewer quote exceptions/final citation violations/bare diagnostics (S3/S4/V1); more duplicate reconciliation before mutation and less supported-value loss (D1–D3 conditional on D0); fewer failed responses sent to extraction (F1 conditional), more retained-evidence reuse and directed gap follow-up (R2/S2 conditional), and fewer repeats after failed URLs. Rows, identities and mechanical quality must hold. M1/M2 and search repeats are descriptive because discovery procedure text did not change. Every registered metric is reported below, including unexercised conditions and contrary outcomes. Actual complete-entry exposure is checked separately; no action is credited to a lesson absent from the agent's inputs.

## Verification, ordering and retained failures

The three original fixes have separate commits and root-cause/tests above. Additional observed failures were fixed generically before the final frozen cohort; all affected research from earlier sources is excluded from its comparison. The full failure evidence remains on disk. [Detailed earlier corrections and traces](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/report_draft_items.md), [later corrections and saved-replay evidence](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/report_post_draft_addendum.md).

| Observed failure | General correction / commit | Preserved evidence |
|---|---|---|
| Older model request starved while later requests took slots | FIFO registered admission with cancellation/crash cleanup; `cfe361f5` | [queue diagnosis](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/concurrency_failure.md), [verification](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/fair_slots/rootcause.md) |
| Identical permanently oversized provider input retried | Classify that rejection as permanent; `af3a4576` | [permanent-error correction](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/permanent_input_retry/rootcause.md), archived failed attempts |
| Repeated quoted text defeated exact sharing and oversized one-call refinement | Lossless JSON-aware sharing `dae5e2d3`; route genuinely oversized complete supplied planner contexts to code/subcalls `44bd200`, with scoped cancellation/full attempt logging `0026197`/`810c7ca` | [codec](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/quoted_text_fix.md), [context transport](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/refiner_context_fix.md) |
| Five saved case bodies consumed deadlines against four slots; cancellation signaled an owned process group twice | Saved-case admission `b1d7bee`; serialized stop/drain `d03277e` | [admission](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/saved_replay_admission.md), [cleanup](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/process_cleanup/rootcause.md) |
| Overflow refiner printed 2,981,867 chars, making next backend input 3,039,692 chars | Retain complete sealed host outputs, replace whole feedback messages with hash-bound readable references only as needed; `80c9a7e`. Reconstruct/verify every actual prompt and reference in audit; `9251c8e` | [transport](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/refiner_output_transport.md), [strict audit](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/refiner_feedback_audit/README.md) |
| Poppler returned success and nonempty text containing corrupt control glyphs | Reject forbidden non-layout Unicode controls, retain exact extraction bytes, version cache policy and require linked receipts; integrated fix `86d8dc2` (original isolated commit `6dad1de`) | [root cause and saved-input verification](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/readable_controls_fix.md), [independent review](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/readable_controls_independent_review.md) |
| An agent requested 17 budget snapshots, yet the last showed 78 available calls only 12.16 seconds before the task deadline | Add truthful remaining monotonic seconds to explicitly requested budget snapshots, preserving limits and initial-input parity; integrated fix `902abe3` (original isolated commit `8a8876c`) | [timestamped failure evidence](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/context_outputs_v1/B1-frozen-2.budget_timeline.json). Two independent oversized agent subcalls also failed once each before timeout; time visibility is not a completion guarantee. |

The output policy changes **refinement feedback representation**, not research-root truncation. Complete outputs remain retrievable with `repl_output(iteration)`; model/control history is not dropped. Unsupported oversized controls or explicit subcalls still fail visibly. The inherited research formatter's 20,000-character per-block policy is unchanged. The older `c944f51` observation selection is **not globally lossless**; “lossless” here means the complete supplied logical refinement payload, not every state ever present in a worker.

The combined extraction and requested-budget corrections passed **1,110 offline tests, one live test deselected**, with all 32 tested product modules unchanged during verification. The extraction-only predecessor independently passed 1,108. Independent focused review passed 114 tests. Offline production-flow replay rejected five archived corrupt extractions while preserving their complete bytes; all 49 valid B0-1 pages remained byte-identical. The failed earlier whole-suite attempt is retained: missing isolated benchmark fixtures and one invalid HTTP mock were corrected, with no subsequent product changes. [Combined whole-suite receipt](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/budget_time/whole_suite.result.json), [extraction review](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/readable_controls_independent_review.md), [budget review](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/budget_time_review.md).

Nine saved-archive audits, installed-byte checks and 59 helper tests plus eight subtests pass on `902abe3`. All five new saved-refinement cases completed: nine model attempts, zero failed attempts or retries, seven edits and 21 candidate decisions. Three independent reviews verified original inputs, schemas, anchors, candidate accounting and commits. The large case retained all 3,027,914 supplied logical characters and archived a 3,033,043-character stdout as a whole-output reference; it did not read that reference back. The A pages case overstates authorization for announcement-only scope in its rationale, while its committed instruction is conditional. Historical rendered texts do not authenticate publisher wording. One model-list refresh timeout was logged nonfatally; the requested call succeeded. These limitations and exact receipts are in the [new preflight scope](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/preflight_scope.json). Saved edits never seed research. After these checks, a fresh [rollback receipt](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/rollback.json) confirms exact clean BASE before A/SI start. The parent full-suite receipt retains a stale `status=running` field; its completed timestamp, exit 0, complete pytest log and module hashes establish completion without rewriting that receipt. The old 9251 preflight passed its transport/accounting checks but does not certify the corrected source. Its saved-refinement semantic review also found one rationale overstatement (8/8 explicit absences asserted, 7/8 supported); the conditional lesson was supported, and those saved edits never seeded research. [Historical preflight](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/context_outputs_v1/preflight.json), [historical semantic review](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/context_outputs_v1/saved_refine_review.md).

The suspended and awake failed preflights remain failed, not relabeled successes. Host sleep explains elapsed time in the suspended attempt; `caffeinate -i` used subsequently prevents idle sleep, not lid closure. Required replacement order is saved checks→clean BASE rollback→A alongside SI→committed predictions→B1 plus three frozen/three baseline runs→separate explicit diagnostic. Each arm owns a full harness clone, cache and run directory and uses `--trace`. The superseded cohort finished on unchanged source 9251. All six actual initial inputs passed same-arm equality and cross-arm equality outside complete entries; the completed-five terminal integrity audit passed. The standard six-run audit correctly failed because frozen2 timed out and produced no table. All terminal metrics, quote violations and timeouts are retained in [its terminal summary](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/context_outputs_v1/terminal_summary.md). Frozen3 also spans the recorded 44m36s clamshell-to-lid-open interval with maintenance wakes, so its elapsed time is further confounded.


## Completed A and SI: direct-readable-v1

These are the replacement runs on `902abe33d06f64c426a65d55d5e600dd6d6a052a`. Every Round 3 number below uses the **new fetch path**. Round 2 used model-mediated returns; cross-round changes therefore do not isolate learning. Both runs completed naturally. Their archived results, independent full-cell reviews and exact metrics are retained at [A review](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/A.review.md), [A entry review](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/A.entry_review.md), [SI review](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/SI.review.md) and [selected A/SI metrics](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/selected_metrics_A_SI/metrics.json).

| Measurement | Round 2 A, old fetch | Round 3 A, new fetch | Round 2 SI, old fetch | Round 3 SI, new fetch |
|---|---:|---:|---:|---:|
| Fetched text characters | 12,187 | 900,192 | 1,343 | 68,075 |
| Largest actual root characters | 79,147 | 112,272 | 24,866 | 28,594 |
| Fetched/largest root | 0.154× | 8.018× | 0.054× | 2.381× |
| Exact 50-gram overlap against all roots | 27.316% | 6.770% | 18.690% | 0.601% |
| Rows | 28 | 28 | 5 | 5 |
| Mechanical self-check issues / uncited cells | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| Model attempts | 115 | 102 | 14 | 11 |
| Wall seconds, including finalization | 1,085.890348 | 1,414.330821 | 339.902331 | 181.680589 |
| Failed fetch requests | 21 | 13 | 0 | 0 |

A's identities match after the documented “Sir J. Fraser Stoddart”/“Sir Fraser Stoddart” alias; raw differences remain recorded. SI's five identities and all 15 values match without aliases. No duplicate whole texts inflate these totals: A has 47 retained text instances and 47 distinct whole-text hashes; SI has three and three. Whole-text hash deduplication leaves their respective 900,192 and 68,075 characters unchanged. Distinct archived raw HTTP bodies total 18,120,283 bytes for A and 356,885 for SI, including retained redirect/failure bodies; those are stored body bytes, not wire overhead. Every successful extraction reproduces exactly from its retained raw response, including all ten A PDFs. [Storage counts and hashes](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/page_storage_counts.A_SI.json).

The root partitions are disjoint and sum to the actual largest backend inputs:

| Component | A characters | SI characters |
|---|---:|---:|
| System | 3,146 | 3,146 |
| Question and columns | 177 | 470 |
| Other task instructions | 15,562 | 8,282 |
| Complete retrieved harness entries | 4,811 | 4 |
| Executed/generated code in history | 24,934 | 4,062 |
| REPL output in history | 61,976 | 11,906 |
| Wrappers | 1,666 | 724 |
| **Total** | **112,272** | **28,594** |

A made 42 actual research subcalls with 806,176 prompt-plus-schema characters (813,820 with backend framing); SI made one with 71,774 (71,956 framed). These were stateless model calls, not child RLMs. Refinement calls are excluded from these counts and included in total cost. A's 324,148-character Stoddart CV was fully present in `source_texts`; code selected an original 1,000-character nationality span for a later subcall. This is agent-directed inspection, not host truncation, padding or an extra fetch to raise the count. SI supplied its three complete page texts to its extraction call. Exact per-call input sizes and result-use evidence remain in [A audit](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/audits/A.audit.json) and [SI audit](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/audits/SI.audit.json).

Saved search-hit reuse is directly observed in both runs: A assigns `hits_by_year` in iteration 2 (trajectory line 6), then uses it for discovery extraction and URL selection in iteration 3 (line 30; trace 125→144→287). SI assigns `single_hits` and `batch_hits` in iteration 2 (line 10), then selects fetch URLs from those variables in iteration 3 (line 16; trace 97→116→147). [Exact executed code and trace bindings](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/A_SI.search_reuse_examples.json). This is separate from query-count proxies: A had 31 completed searches, 11 searches without a matching discovery record by the next root-block end (M1), zero corrected empty discoveries and zero repeated exact-query requests; SI had 3, 0, 0 and 0 respectively. A's late discovery timing persists despite the unchanged baseline discovery memory. No new discovery-procedure benefit is claimed.

A's mechanical criterion holds, but the independent review supports 139 of 140 listed cell values and leaves Yekimov's “American; Russian” unresolved: “Nationality USA/USSR (now Russia)” does not establish current dual nationality. No established falsehood is claimed. Four separate affiliation-coverage concerns overlap otherwise supported values: Stoddart/Tianjin and Winter/Trinity have dated appointments spanning the award year; Frank/HHMI and Whittingham/NAATBatt are weaker unclosed continuation leads. An official credited institution is supported without proving exhaustive concurrent affiliations. SI's original NIST table independently supports all 15 values, with no unresolved value or affiliation concern. Mechanical citation success is reported separately from semantic completeness. SI's 2.38× size ratio does **not** establish “far exceeds”; no new numeric cutoff is introduced.

A's thirteen failures are three redirect loops, six HTTP 403 responses, one HTTP 404, two TLS verification errors and one broken pipe. The latter lasted 600.0058 seconds and remains recorded as `download_error: [Errno 32] Broken pipe`, not reclassified as a timeout. A also had one terminated quotation-validation block: a Doudna quotation matched one citation but not a second; later code diagnosed it and retained the supporting citation. There were four individual printed quote-failure records. All failures remain counted; there was no model-mediated fallback or model retry. SI had no failed fetch, quote exception or backend retry.

### Same-run delivery in A, and its limit in SI

A requested refinement itself while substantive work remained. The duplicate-reconciliation memory had BM25 score zero, yet the current-run inclusion rule returned its complete committed object. The same seven later actual backend root inputs contained both midtask v1 memories. There were no root blocks spent sleeping or polling for refinement.

| A event | UTC on 2026-10-20 | Trace line |
|---|---|---:|
| Agent requests midtask refinement | 18:05:23.411616 | [778](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/workspaces/A/runs/research-a685a2c37ca948fa9d7ab1a551451ff2/trace.jsonl:778) |
| Proposal recorded | 18:06:07.285170 | [867](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/workspaces/A/runs/research-a685a2c37ca948fa9d7ab1a551451ff2/trace.jsonl:867) |
| Exact-span v1 committed, `08e662ec…` | 18:06:35.688619 | [941](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/workspaces/A/runs/research-a685a2c37ca948fa9d7ab1a551451ff2/trace.jsonl:941) |
| Duplicate memory committed, `b78f2307…` | 18:06:35.730884 | [944](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/workspaces/A/runs/research-a685a2c37ca948fa9d7ab1a551451ff2/trace.jsonl:944) |
| Later retrieval returns both | 18:06:35.815765 | [948](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/workspaces/A/runs/research-a685a2c37ca948fa9d7ab1a551451ff2/trace.jsonl:948) |
| Worker completes | 18:09:25.914474 | [1948](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/workspaces/A/runs/research-a685a2c37ca948fa9d7ab1a551451ff2/trace.jsonl:1948) |
| Finalizer updates exact-span memory to v2 | 18:13:03.606842 | [2003](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/workspaces/A/runs/research-a685a2c37ca948fa9d7ab1a551451ff2/trace.jsonl:2003) |
| Finalizer commits partial-fetch recovery skill | 18:13:03.653204 | [2006](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/workspaces/A/runs/research-a685a2c37ca948fa9d7ab1a551451ff2/trace.jsonl:2006) |

After retrieval, iteration 10 (trajectory line 93) prints duplicate counts and a per-source quotation diagnostic. Iteration 11 (line 100) asks for one reconciled record per entity, validates the batch before mutation and restores supported components. This is a verified commit→retrieval→compatible action chain. It is **not isolated causal proof**: quotation guards and targeted Stoddart/Bawendi searches already appeared before the commits. The final v2 changes and recovery skill committed after worker exit and had no A worker reuse. Complete prompt-object comparisons and raw trace links are in [A entry review](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/A.entry_review.md).

Relative to Round 2 A's zero of eleven later retrievals, Round 3 A has seven of seven later root inputs containing the two new midtask entries. The earlier explicit probe's 24 pause blocks and 985 declared sleep seconds are not repeated by this A. The separately requested **explicit** diagnostic is reported on its own below, rather than substituting this spontaneous chain for that check.

SI requested refinement at 17:51:42.406418 UTC, then finished its worker at 17:51:43.040863. Its memory committed at 17:52:09.282280, 26.241417 seconds after worker exit; all six retrievals preceded the request. Therefore SI's committed same-run reuse is **not demonstrated**. The lesson distinguishes generated finalization code from observed execution, but its rationale's literal “before that block ran” is imprecise: the request occurred inside the executing block. Later checks and submission completed. This was not an actual finalization failure or demonstrated benefit.

### Final lesson accounting

A's midtask proposal accounts for five candidates: two accepted and three declined. Its finalizer accounts for seven: two accepted and five declined. Four edits create two memories, update the exact-span memory and create the fetch skill. The final proposal explicitly preserves historical-nationality uncertainty and distinguishes mechanical quote checks from semantic proof. The fetch-sentinel evidence is concrete: eight actual extraction calls received ten `FETCH_FAILED` source objects. SI accounts for six decisions, one accepted and five declined, with one committed memory; its finalizer made zero edits. A reasoned zero-edit result remains valid.

A's finalizer exercised the complete supplied-context path, with five planner calls and seven refinement subcalls after the one direct midtask call. A whole 2,217,369-character feedback message was retained and replaced by its 855-character receipt before the next backend call. There were zero `repl_output` reads; availability alone is not a read demonstration. The complete supplied logical input, schema, decisions, evidence anchors and commits are verified. The inherited observation selection remains separately qualified and is not described as a globally lossless copy of every worker state.


## Every main run: new fetch path

All sizes are characters unless labeled bytes. Root sizes are actual largest research backend inputs; overlap uses exact case/whitespace-sensitive 50-character grams against all research roots. Source text counts exclude failed returns. Same identities are checked against Round 2 after documented aliases, with raw differences preserved.

| Run | Readable chars | Largest root | Ratio | Overlap | Rows / issues / uncited | Attempts | Wall seconds | Failed fetches |
|---|---:|---:|---:|---:|---|---:|---:|---:|
| A | 900,192 | 112,272 | 8.0180× | 6.7700% | 28 / 0 / 0 | 102 | 1414.330821 | 13 |
| SI | 68,075 | 28,594 | 2.3807× | 0.6008% | 5 / 0 / 0 | 11 | 181.680589 | 0 |
| B1 | 921,760 | 175,270 | 5.2591× | 0.7385% | 28 / 0 / 0 | 165 | 2616.339354 | 6 |
| B0-1 | 1,305,812 | 86,610 | 15.0769× | 2.1342% | 28 / 0 / 0 | 139 | 1047.978328 | 4 |
| B0-2 | 1,249,347 | 82,507 | 15.1423× | 0.7548% | 28 / 0 / 0 | 80 | 684.788533 | 5 |
| B0-3 | 1,651,962 | 86,409 | 19.1179× | 0.7823% | 28 / 0 / 0 | 134 | 930.618448 | 5 |
| B1-frozen-1 | 1,068,214 | 107,675 | 9.9207× | 0.1439% | 28 / 0 / 0 | 83 | 961.929480 | 4 |
| B1-frozen-2 | 945,540 | 103,207 | 9.1616× | 0.0420% | 28 / 0 / 0 | 86 | 806.307491 | 2 |
| B1-frozen-3 | 1,293,190 | 127,186 | 10.1677× | 0.1269% | 28 / 0 / 0 | 103 | 1530.249356 | 21 |

All runs have zero model retries. The single failed oversized research subcall in frozen1 remains in attempt counts; successful subcall input aggregates below exclude that failed result and are supplemented by its exact failed-input ledger.

| Run | Successful research subcalls | Logical input total | Backend input total | Stored raw body bytes | Text instances / whole hashes | Whole-hash-deduplicated chars |
|---|---:|---:|---:|---:|---:|---:|
| A | 42 | 806,176 | 813,820 | 18,120,283 | 47 / 47 | 900,192 |
| SI | 1 | 71,774 | 71,956 | 356,885 | 3 / 3 | 68,075 |
| B1 | 47 | 2,762,244 | 2,770,798 | 15,554,147 | 86 / 86 | 921,760 |
| B0-1 | 73 | 1,824,730 | 1,838,016 | 19,671,181 | 91 / 91 | 1,305,812 |
| B0-2 | 23 | 1,761,625 | 1,765,811 | 25,465,392 | 58 / 58 | 1,249,347 |
| B0-3 | 69 | 3,475,639 | 3,488,197 | 33,735,708 | 95 / 95 | 1,651,962 |
| B1-frozen-1 | 33 | 2,607,292 | 2,613,298 | 22,253,050 | 62 / 62 | 1,068,214 |
| B1-frozen-2 | 35 | 2,530,706 | 2,537,076 | 22,854,754 | 65 / 65 | 945,540 |
| B1-frozen-3 | 52 | 3,327,390 | 3,336,854 | 19,849,593 | 77 / 75 | 1,281,786 |

Raw bytes are distinct stored HTTP response bodies, including available failure/redirect bodies, not wire overhead. Whole-text hashing removes identical complete strings across URLs; it does not remove repeated page fragments or claim global informational uniqueness. The explicit child diagnostic is separate from these nine runs.

### Largest actual root input partitions

| Run | System | Question / columns | Other task instructions | Complete harness entries | Code | REPL output | Wrappers | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 3,146 | 177 | 15,562 | 4,811 | 24,934 | 61,976 | 1,666 | 112,272 |
| SI | 3,146 | 470 | 8,282 | 4 | 4,062 | 11,906 | 724 | 28,594 |
| B1 | 3,146 | 175 | 16,374 | 45,061 | 32,962 | 75,884 | 1,668 | 175,270 |
| B0-1 | 3,146 | 175 | 7,423 | 1,986 | 16,138 | 56,099 | 1,643 | 86,610 |
| B0-2 | 3,146 | 175 | 7,423 | 1,986 | 14,879 | 53,424 | 1,474 | 82,507 |
| B0-3 | 3,146 | 175 | 7,423 | 1,986 | 20,534 | 51,588 | 1,557 | 86,409 |
| B1-frozen-1 | 3,146 | 175 | 7,423 | 34,226 | 19,340 | 42,058 | 1,307 | 107,675 |
| B1-frozen-2 | 3,146 | 175 | 7,423 | 34,226 | 21,039 | 35,890 | 1,308 | 103,207 |
| B1-frozen-3 | 3,146 | 175 | 7,423 | 34,226 | 29,700 | 51,042 | 1,474 | 127,186 |

The seven partitions are disjoint and sum exactly. Complete per-call logical/schema/backend sizes, source hashes and code/result-use bindings are in [the final metrics](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/final_metrics/metrics.json) and the linked per-run audits. Ordinary research subcalls are stateless; the separate explicit run demonstrates an actual nested RLM.


## Completed B runs and controlled benefit

All seven B runs completed naturally on runtime `902abe33d06f64c426a65d55d5e600dd6d6a052a`, using the **new direct-readable-v1 fetch path**. B1 is learning-enabled and is not pooled into the frozen/base estimate. Each control has an independent harness clone, task cache and run directory. All return 28 identities, 140 required cells, zero mechanical self-check issues, zero uncited cells and zero automatic exact-quote membership violations. Explicit identity aliases and raw identity differences remain in the full metrics; no submitted rows were changed by review.

The before evidence was one Round 2 old-fetch-path pair: frozen B used 248 model attempts and 1,961.780381 seconds, versus B0's 185 attempts and 1,588.7534 seconds. Both had 28 rows and zero mechanical issues/uncited cells, but the initial-input comparison still had the non-entry defects diagnosed above. The new three-repeat estimates below use the new fetch path and corrected runtime; cross-round resource changes do not isolate learning or any single fix.

The [six-control audit](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/control_audit/control_audit.json) passes. All three B0 initial backend inputs are byte-identical (SHA `61d99d1061f753cd9d86ae8ea080883deba36ff4d337eec2bc42d419e07f1cc7`); all three frozen inputs are byte-identical (`7b01a9cea635ebf19160ffee863beff859224d6351653986ef9bfac9697a50f3`). Across bases, only complete harness-entry JSON differs. The 11,195-character outside-entry representation has SHA `42f9c4f0b87d274630671d194679c21d7c27cf5bacfea61e45170de6260c20e1`. Date provenance and all 32 source/installed modules match. Full historical entry fields remain visible. The audit reads each recorded run head, not the restored checkout: frozen/base runs still make bookkeeping commits, while their procedures remain unchanged. Later generated prompts and retrieved evidence naturally diverge.

All **38 actual frozen root inputs** (12/12/14 across repeats) contain A's complete validation memory v2 plus the inherited discovery memory. None contains A's duplicate-reconciliation v1 memory or partial-fetch-recovery skill. Retrieval still ranks historical entries by the unchanged task/schema relevance query; the current-run inclusion fix does not force unrelated historical entries into a later run. This explains a major exposure limit, without changing retrieval to pursue a favorable result. The validation memory is exposed; the other two preregistered lessons are not. Their metrics are still reported.

The registered validation guard is present in all six controls (S1=1). All six have zero thrown quote exceptions and final citation-membership violations, so reduced exception incidence is not demonstrated and V1's conditional comparison is not exercised. Frozen1 has one duplicate-candidate group, an unreconciled destructive Haldane overwrite, and a later repair: D0=1, D1=0, D2=1, D3=0. The other five controls have no qualifying duplicate group. Conditional D1–D3 are N/A there, not zeros. The absent duplicate memory cannot receive credit or blame for this behavior. Sequential loss/recovery outside the registered duplicate-group condition remains described in the reviews, including B1's lost/restored McDonald collaboration and B0-3's unrepaired affiliation losses.

For gap-directed follow-up (S2), B0 values are 76/43/73 and frozen values 52/49/38: means 64 versus 46.333, a difference of −17.667 against a spread of 33. This is opposite the predicted increase. Retained-download reuse blocks (R2) likewise average 11.333 versus 9.667, difference −1.667 against spread 2. Failed responses passed into extraction (F1) are 0/4/7 versus 0/0/0: the favorable mean difference −3.667 does not exceed spread 7, and the proposed recovery skill was absent from the frozen inputs. Every control has failed-fetch exposure. Repeated requests after failed URLs and repeats per failed URL are zero in both arms. The complete ledgers preserve each query, failure, gap and inclusion/exclusion decision; downloading a source does not itself prove that a gap was closed.

The S2 reviews required disclosed post-registration adjudications. Empty required values and supported missing components count; semantic disambiguation of a populated nationality description, quotation-context repair and broad re-verification without an observed gap do not. Frozen2 changes 55→49, B0-2 46→43, and B1's provisional count 58→55. Originals and every excluded URL are preserved. These decisions apply to all arms; they do not alter predictions, scoring code or research outputs. [Original boundary](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/review_adjudications.md), [final common adjudication](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/common_review_parent_adjudication.md), [combined manual with original receipts and overrides](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/combined.manual.json).

There are descriptive efficiency signals. Frozen root calls average 12.667 versus B0 15 (difference −2.333, spread 2); search calls average 37.667 versus 47.667 (difference −10, spread 7). Both exceed the specified within-arm spread. Total model attempts average 90.667 versus 117.667 (difference −27, spread 59), which does not. Wall time averages 1,099.495 versus 887.795 seconds (difference +211.700, spread 723.942); the frozen mean is slower. Wall time includes source delays, queueing and finalization, and shared parallel execution limits interpretation. Search-completion count repeats the search-call signal rather than providing independent evidence. No dollar-cost or statistical-significance claim is inferred.

The other spread-exceeding results are reported, including unfavorable or structural ones: frozen prompts are larger by 27,514 mean characters (spread 23,979), their complete harness partitions are larger by 32,240 characters (spread zero), wrappers are smaller by 195 characters (spread 169), and their fetched/root ratio is lower by 6.6957 (spread 4.0410). These are not separate demonstrations of improved answer quality. Complete entry metadata is part of this intervention, and task/web/model variation remains. **Three repeats are descriptive, not a statistical result.**

### Semantic review and corrections

Independent reviews support all 140 *listed* values in each B output using its cited full-source context. They do not certify all concurrent affiliations or all nationality components. The parent found omissions in the initial reviews themselves, then applied one common archived evidence pool to all seven outputs. Original source-local counts and reviews remain untouched. [Review corrections](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/review_corrections_and_limits.md), [immutable affiliation evidence v5](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/common_coverage_evidence.v5.md), [parent-reviewed final cells](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/common_coverage_final.v2.json).

The final component-level affiliation concern counts are B1 9; frozen 10/9/9; B0 9/9/12. Each includes one undated Weiss/LSU lead, not a proved award-year omission; the remaining identified concerns have dated support. Some are institute-detail omissions within a listed parent institution. Tokyo without ICRR and the Austrian Academy without IQOQI receive the same treatment. Frozen3's initial parent-ledger count of eight was corrected to nine for that consistency; both ledgers and scripts remain preserved. The mean difference is −0.667 against spread 3, not a demonstrated improvement. The pool is not claimed exhaustive.

The common nationality review supplies an adverse result. Mourou's CV explicitly states US/France dual citizenship. Agostini's official university publication describes French-American nationality, without proving dual legal citizenship. French-only values remain supported but omit those components. The two-component omission counts are frozen 2/2/1 and B0 0/0/1: means 1.667 versus 0.333, difference +1.333 exceeding spread 1. This is a **post-registration completeness diagnostic**, not a new directional prediction or statistical finding. It is not hidden by the mechanical passes. Haldane's possible additional US citizenship remains a shared unresolved conflict between the collective PNAS assertion and the specific citizen/permanent-resident description in all seven B outputs. [Evidence and temporal limits](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/common_nationality_evidence.v2.md), [same final-cell review across all B](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/common_nationality_final.json).

Frozen3 also has one identified selected-quotation insufficiency: Kajita's value includes ICRR/directorship, while its selected quote names only Super-Kamiokande and Tokyo. The cited full release supports ICRR elsewhere, so this is not a false full-source value or an automatic exact-membership failure. That additional metric is one in frozen3 and N/A where no comparable dedicated exhaustive quote-sufficiency count was supplied. The targeted twelve-component cross-arm check does not substitute for a full quotation audit of every other arm.

### Preserved errors and concrete evidence use

Frozen1's 34 research-subcall attempts include one failed oversized input and 33 successful results. The failed logical input is **1,174,954 characters**, or **1,175,136** with backend framing, SHA `dda7c58ae8d0eb32aa20c0b1830c9de254c22854dbc0a673d2e6e0aa9d8b2a98`. It failed once, without retry. Seven successful recovery calls contain 76,061; 535,974; 101,097; 86,210; 72,768; 55,923; and 39,921 logical characters. Their 51-URL/full-text dictionary union equals the failed input's dictionary exactly. This is agent-directed decomposition, not host truncation or a silently removed failure. Four propagated error events describe that one underlying rejection. The ordinary audit's size aggregate covers successful results; the [failed-input ledger](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/B1-frozen-1.failed_subcall_inputs.json) separately retains the failed size/hash and every recovery binding. All other research-subcall attempts in the final main cohort succeeded.

Every failed download remains counted with its reason, with no model-mediated fallback. B1 and frozen3 each include a Washington Post request lasting approximately 600 seconds before `download_error: [Errno 32] Broken pipe`; A has the same recorded failure type. These are not relabeled as successful fetches or silently converted to a different error reason. Frozen3's 21 failures include HTTP, redirect and TLS failures. One root block in frozen1 failed on the oversized subcall; all six controls have zero quote-exception blocks. Printed quote-failure observations retain repeats: B0 1/6/0, frozen 0/0/6.

The page/code/subcall path is concrete. In B1, the full 7,343-character 2015 release enters `sources[press_urls[2015]]` at trajectory21, then the actual extraction prompt at trajectory25/trace287; the parsed source equals the archived text, and the validated result enters working rows. The final iteration reuses it for McDonald's repair. In frozen1, the large Lindau annual report was selected for a real nationality question and supplied as source evidence, not acquired to inflate the ratio. Frozen3's two identical-text URL pairs reduce 1,293,190 retained characters to 1,281,786 under whole-text hashing; its size ratio still exceeds ten after that deduplication. The other main arms have distinct complete-text hashes. Whole-text uniqueness does not claim globally unique information.

Saved search results are reused directly in all reviewed trajectories; this is not inferred from repeated-query counts. B1 reuses `search_results` in iterations2→3, `followup_hits` 8→9, `dual_hits` 10→11 and `facts_hits` 11→12. B0-1 reuses its initial hits 2→3 and `nat_hits` 5→6. The inherited discovery procedure was not changed by A, so those examples do not establish a newly learned discovery benefit. M1/M2, search repeats, cache hits and all cost/size/error metrics remain in the complete tables below.

### B1 same-run learning and final refinement

B1 requested midtask refinement at trace940, 18:34:22.560629 UTC. Its two edits committed at traces1063/1066, 18:36:09.432548/18:36:09.498877: updated complementary-evidence memory `b98beb…` v2 and new missing-field skill `b820f0…` v1. Both complete objects reached all eight later root inputs, iterations9–16, starting at trajectory88. The next retrieval followed the second commit by 0.102915 seconds, while 1,405.825693 seconds of worker activity remained. Iteration9 then compared selected and nonselected nationality evidence. The chain is observed, but related review/search work predated the commits, so compatible action is not isolated causal proof. No root turns were spent waiting for refinement.

The midtask job accounts for six decisions, two accepted and four declined, and two edits. The final job accounts for eight decisions, five accepted and three declined, mapped to two updates under the edit limit. Final versions committed at traces2786/2789 after worker end at trace2722, and were not reused by the worker. The full candidate ledger preserves rejected unfinished-output claims, context-sensitive empty discoveries, wrong-person source repair, sequential affiliation loss and conclusion-led conflict review. Its complete supplied logical input is 4,504,239 characters. Fifteen actual refinement calls use the overflow planner; the pre-routing 1,640,715-character prompt was not dispatched. Whole feedback of 4,300,276 characters is retained behind a readable reference; no reference read occurred. This verifies availability/representation, not live output-reference retrieval or globally lossless worker history. [Full B1 review and trace bindings](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/cohorts/readable_controls_v1/B1.review.md).

**Verdict:** initial comparison isolation works; consistent self-improvement benefit is **not demonstrated**. Some descriptive resource reductions exceed spread, but the registered behavior results are flat, contrary, unexercised or within spread; two new lessons were not exposed; and the common completeness review finds an adverse nationality difference. All individual values, means, ranges, defined-run counts and strict spread comparisons follow, including unfavorable and N/A outcomes.


## Explicit check — independent completed-run review

The explicit run completed naturally with exit 0 at **2026-10-20 19:20:00.649546 UTC**, on frozen source `902abe33d06f64c426a65d55d5e600dd6d6a052a`. Its run is `research-bfb3a6076ef5499080a3f8a19b2c6b32`, task `279b4452911b3d5f1254f337`, in the separate `explicit-BASE` workspace. It began from `2a423027212fe1c430dfd200bdd55f3a27b22d70`, after the nine main arms. This was explicitly requested and is excluded from spontaneous-refinement claims and all A/B estimates.

The actual child REPL and validated result use are demonstrated. The midtask refinement completed as an **applied zero-edit decline**; the later root saw and correctly reported that state. **Same-run committed-entry reuse was not exercised.** The finalizer subsequently created one entry, after the research worker ended. That later entry is not same-run reuse. No replay, forced acceptance, waiting loop or additional research was introduced to obtain an edit.

The unchanged archive audit passed. All **59** files matched the launcher's byte counts, complete SHA-256 hashes and exact file set before and after this review. Inventory SHA-256: `b877daef26de51f0bd0f56d074958b1107813760ed93ec5a5859e1bbb79a8f07`. The full review JSON preserves all 30 cells, exact quotes at every cited URL, artifact hashes, code/stdout/stderr, full refinement candidates and entry deltas. No runtime, source, harness, archive, input or process was changed by this review.

All **five requested quantities and 30 required cells** are present and semantically supported by retained official NIST text. The source requests comprise two NIST and two BIPM pages. Every final citation uses the retained NIST SP 330 Section 2 page. Each complete defining statement includes its relevant constant, fixed value, unit relation and dependency clause. All quotations match every cited source exactly.

| Quantity | Unit / symbol | Fixed defining constant and value | Checked dependency/unit relation |
|---|---|---|---|
| Length | meter / m | Speed of light in vacuum, 299 792 458 m s−1 | Second defined through cesium frequency. |
| Mass | kilogram / kg | Planck constant, 6.626 070 15 × 10−34 J s | J s = kg m² s−1; meter and second defined through c and ΔνCs. |
| Time | second / s | Unperturbed ground-state hyperfine transition frequency of cesium-133, 9 192 631 770 Hz | Hz = s−1; transition identity explicitly included. |
| Electric current | ampere / A | Elementary charge, 1.602 176 634 × 10−19 C | C = A s; second defined through ΔνCs. |
| Thermodynamic temperature | kelvin / K | Boltzmann constant, 1.380 649 × 10−23 J/K | J K−1 = kg m² s−2 K−1; kilogram, meter and second defined through h, c and ΔνCs. |

The exact readable quotes use `m2` where the retained HTML renders `m<sup>2</sup>`. The raw source was checked to confirm the exponent; quoted strings were not silently rewritten. This review assesses the official evidence actually retrieved, without a new external lookup. The final root's executed guard checks five unique quantity keys, all fields, every source's official hostname, every exact quotation, five passed audit findings, and 35 constraint checks before actual readiness at **trace 447, 19:19:31.324347 UTC**. This independent per-cell review is separate from those agent-supplied pass flags.

The researcher fetched four pages, performed two grouped structured extractions, and checked quotation membership before requesting refinement. At **trace 169, 19:18:13.573610 UTC**, request `13e19fc00cb5432f9ed0626a47fbf16b` / job `a6f2e6d670114e7c846d579edce24ec3` asks the planner to evaluate the observed procedure while independent numerical and dependency checks remain. It does not prescribe a lesson or edit an entry. The next actual root input, trajectory 17, contains the full automatic status `planning` with this exact request/job identity and no commits.

That root then invokes **one actual `rlm_query` child**, RLM `fc10bec17e4547f3b8666ba87c74c45e`, parent `3bffc96349d548ee8e36320a4f36b806`, depth 1. It passes **61,328 characters** comprising instructions, the two candidate rows and three complete retained texts: NIST SP 330 (44,922), BIPM ampere (5,270) and BIPM kelvin (5,337). The child's parsed evidence strings equal the retained source strings and their hashes exactly.

The child executes three REPL turns: it inspects context; parses the evidence and rows; then checks the two quantities' field values, full defining sentences, numeric exponents, unit relations and every quotation against those retained strings. It returns two compact cited findings, ending with `answer_ready` at trace 259. Its **1,223-character** JSON result equals the parent's received result. The parent also runs a structured conversion call; the entire converted findings object equals the child's parsed JSON exactly. The final root validates both returned source URLs and quotations again, requires their `passed` fields, and uses the two findings to approve current/temperature numerical and dependency checks. This is concrete result use, not merely a child invocation or a print of its response. The child verifies existing rows; it did not originate the table.

There is one visible recovered diagnostic problem. The child prints its entire evidence-bearing context: complete raw stdout is **61,335 characters**. The next child model input contains the existing display marker `... + [41389 chars...]`. The complete context remains in the child's variables; the next REPL turn parses it and subsequent checks access the full source. No evidence was refetched. The final review does not conceal this output truncation or mistake it for lost stored evidence. RLM identity/depth and audited turn sequence are used throughout: there are six actual root turns and three child turns; worker-local iteration numbers repeat after nesting and must not be treated as globally unique.

The midtask proposal arrives at **trace 210, 19:18:36.067289 UTC** and is applied at **trace 295, 19:19:15.125758 UTC**, with **zero edits and zero commits**. It considers the presented unfinished-output candidate plus three additional candidates and declines all four:

- Empty output reflects an unfinished snapshot with verification pending, not demonstrated abandonment or final failure.
- Grouped structured extraction and quote validation are useful but already covered by the base instructions; quotation membership alone does not prove numerical/dependency correctness.
- Existing discovery guidance was followed by actual three-entity and two-entity records, with no evidence warranting revision or deletion.
- Full search-result prints oppose existing compact-output guidance, but the midtask snapshot did not yet show resulting truncation or recovery cost sufficient to justify another entry.

The later root's **actual input at trajectory 28** contains the complete applied proposal, decisions and empty commits array. It prints a completed-decline diagnostic and proceeds to final validation. Its relevant-entry objects remain exactly the BASE entry; no entry from this midtask request exists to retrieve or apply. The report therefore terminates the requested chain at **request → completed decline → accurate later status handling**, not at a fictional commit or reuse step.

Inspection of every executed root/child code block finds exactly one `refine.run`, one `rlm_query`, no sleep, no refinement-status polling, no harness searching to await an entry, no resubmission, and no harness mutation. The remaining work is the bounded child audit, the other three quantities' verification, schema conversion and final evidence checks. Search and fetch occurred before the request; no artificial acquisition was added afterward to wait for the planner.

Worker end is **trace 457, 19:19:31.860486 UTC**. The separate finalizer begins at trace 466 and considers three additional candidates, accepting oversized diagnostics and declining duplicate validation guidance and changes to the existing discovery memory. This later snapshot contains the actual child-output truncation absent from the midtask snapshot, so the different decision has new supporting evidence. Its generic memory, **`c7c9753005b64b029a058c6395b27f76` v1, “Inspect instructions without dumping embedded evidence,”** commits at **trace 475, 19:20:00.427814 UTC**, commit `a3d69af6eb6e050bf1ab06aef48677d9762a0347`. The content distinguishes complete retained evidence from truncated diagnostic output and recommends targeted inspection without refetching. It was created after worker end and was never delivered to a later research root. Both jobs pass the archived proposal schema and strict candidate-accounting checks; their complete supplied logical inputs round-trip exactly through the recorded representations.

There were **17 calls and 17 attempts, zero retries**: six research-root calls, two searches, seven sub-purpose calls and two refinement calls. Three of those seven sub-purpose calls are the real child's turns; the other four are ordinary structured extraction/audit calls. No fetch failures, backend error completions or root/child stderr exceptions are recorded. The diagnostic truncation remains a distinct recovered process observation, despite those zero error counts.

The run retains **62,148 characters in four successful texts**, with four distinct complete-text hashes. The largest root input is **53,362 characters**, giving a retained-text/root ratio of **1.16465**. Its partition is system 3,146; task question/columns 3,057; other task instructions 14,962; harness 1,986; code 7,738; REPL output 21,639; wrappers 834. Exact 50-character overlap across root inputs covers 1,864/62,148 retained characters (**2.9993%**), with zero full fetched texts in a root input. Child input, child output display and root input are separate measurements; whole-text hashing is not a claim of globally unique information.

Evidence files: `explicit.review.json`, `explicit.review_verification.json`, `audits/explicit.audit.json`, `audits/explicit.metrics.json` and `explicit.review_audit.log`. Trace and trajectory lines are one-based; proposal evidence indexes are zero-based. This diagnostic demonstrates actual delegation, validated child-result use and truthful handling of a completed decline. It supplies no same-run committed-entry-reuse observation and no controlled quality-benefit estimate.


## Complete metric tables

Three repeats per base are descriptive, not statistical evidence. New direct-readable-v1 fetch transport. The answer["ready"] assignment scoring contract defines an available measure; it does not select or establish a directional prediction for a new learned entry. Only that cohort’s committed preregistration can do so. Full historical harness metadata belongs to the intervention. Nine main runs serve ten report checks; an explicit-refinement run is separate.

All values below have complete event-level evidence in metrics.json. N/A is never zero.

Scoring contract: `answer-ready-v2`. S1 boundary: `first root submission setting answer["ready"] = True`.

Binary 1 only when executed code before the first root submission setting answer["ready"] = True verifies a nonempty value, source list, and quote for every required cell in the nonempty candidate row set submitted, and verifies exact quote membership in retained original fetched text for every cited URL. Locate the submitting block using the first depth-0 REPL code.end event with answer_ready=true; checks must execute before the readiness assignment within that block or an earlier block and cover the actual submitted version. An earlier failed guard followed by repairs and a successful complete guard before submission can score 1. Partial checks, checks of an earlier candidate version, checks after submission, and unsupported assurances score 0. Cite executed code, output, coverage, and submission. If no root submission exists, report N/A with evidence and a reason; missing review evidence fails extraction. This measures an observed guard, not causal benefit.

### Directional and descriptive control metrics

| Metric | B0 values | Frozen values | B0 mean [min,max]; n | Frozen mean [min,max]; n | Delta | Spread | Exceeds |
|---|---|---|---|---|---|---|---|
| D0_duplicate_candidate_groups | 0, 0, 0 | 1, 0, 0 | 0 [0,0]; 3 | 0.33333333 [0,1]; 3 | 0.33333333 | 1 | False |
| D1_reconciled_before_mutation_groups | 0, 0, 0 | 0, 0, 0 | 0 [0,0]; 3 | 0 [0,0]; 3 | 0 | 0 | False |
| D1_reconciled_before_mutation_groups_conditional | N/A, N/A, N/A | 0, N/A, N/A | N/A [N/A,N/A]; 0 | 0 [0,0]; 1 | N/A | N/A | N/A |
| D2_destructive_overwrite_groups | 0, 0, 0 | 1, 0, 0 | 0 [0,0]; 3 | 0.33333333 [0,1]; 3 | 0.33333333 | 1 | False |
| D2_destructive_overwrite_groups_conditional | N/A, N/A, N/A | 1, N/A, N/A | N/A [N/A,N/A]; 0 | 1 [1,1]; 1 | N/A | N/A | N/A |
| D3_unresolved_overwrite_groups | 0, 0, 0 | 0, 0, 0 | 0 [0,0]; 3 | 0 [0,0]; 3 | 0 | 0 | False |
| D3_unresolved_overwrite_groups_conditional | N/A, N/A, N/A | 0, N/A, N/A | N/A [N/A,N/A]; 0 | 0 [0,0]; 1 | N/A | N/A | N/A |
| F1_failed_fetch_exposure | 1, 1, 1 | 1, 1, 1 | 1 [1,1]; 3 | 1 [1,1]; 3 | 0 | 0 | False |
| F1_failed_response_extraction_calls | 0, 4, 7 | 0, 0, 0 | 3.6666667 [0,7]; 3 | 0 [0,0]; 3 | -3.6666667 | 7 | False |
| F1_failed_response_extraction_calls_conditional | 0, 4, 7 | 0, 0, 0 | 3.6666667 [0,7]; 3 | 0 [0,0]; 3 | -3.6666667 | 7 | False |
| M1_completed_requests | 50, 43, 50 | 37, 39, 37 | 47.666667 [43,50]; 3 | 37.666667 [37,39]; 3 | -10 | 7 | True |
| M1_late_fraction | 0.72, 1, 0.2 | 0.27027027, 0.25641026, 0.27027027 | 0.64 [0.2,1]; 3 | 0.26565027 [0.25641026,0.27027027]; 3 | -0.37434973 | 0.8 | False |
| M1_late_requests | 36, 43, 10 | 10, 10, 10 | 29.666667 [10,43]; 3 | 10 [10,10]; 3 | -19.666667 | 33 | False |
| M2_corrected_empty_records | 0, 0, 0 | 0, 0, 0 | 0 [0,0]; 3 | 0 [0,0]; 3 | 0 | 0 | False |
| Q1_duplicate_output_identities | 0, 0, 0 | 0, 0, 0 | 0 [0,0]; 3 | 0 [0,0]; 3 | 0 | 0 | False |
| Q1_identity_symmetric_difference | 0, 0, 0 | 0, 0, 0 | 0 [0,0]; 3 | 0 [0,0]; 3 | 0 | 0 | False |
| Q1_identity_symmetric_difference_raw | 0, 0, 0 | 0, 0, 0 | 0 [0,0]; 3 | 0 [0,0]; 3 | 0 | 0 | False |
| Q1_output_rows | 28, 28, 28 | 28, 28, 28 | 28 [28,28]; 3 | 28 [28,28]; 3 | 0 | 0 | False |
| Q1_self_check_issues | 0, 0, 0 | 0, 0, 0 | 0 [0,0]; 3 | 0 [0,0]; 3 | 0 | 0 | False |
| Q1_uncited_cells | 0, 0, 0 | 0, 0, 0 | 0 [0,0]; 3 | 0 [0,0]; 3 | 0 | 0 | False |
| R2_retained_download_reuse_blocks | 12, 10, 12 | 9, 9, 11 | 11.333333 [10,12]; 3 | 9.6666667 [9,11]; 3 | -1.6666667 | 2 | False |
| S1_pre_answer_ready_validation | 1, 1, 1 | 1, 1, 1 | 1 [1,1]; 3 | 1 [1,1]; 3 | 0 | 0 | False |
| S2_gap_exposed | 1, 1, 1 | 1, 1, 1 | 1 [1,1]; 3 | 1 [1,1]; 3 | 0 | 0 | False |
| S2_supplementary_unique_urls | 76, 43, 73 | 52, 49, 38 | 64 [43,76]; 3 | 46.333333 [38,52]; 3 | -17.666667 | 33 | False |
| S2_supplementary_unique_urls_conditional | 76, 43, 73 | 52, 49, 38 | 64 [43,76]; 3 | 46.333333 [38,52]; 3 | -17.666667 | 33 | False |
| S3_caught_printed_quote_failures | 1, 6, 0 | 0, 0, 6 | 2.3333333 [0,6]; 3 | 2 [0,6]; 3 | -0.33333333 | 6 | False |
| S3_quote_exception_blocks | 0, 0, 0 | 0, 0, 0 | 0 [0,0]; 3 | 0 [0,0]; 3 | 0 | 0 | False |
| S4_citation_violation_cells | 0, 0, 0 | 0, 0, 0 | 0 [0,0]; 3 | 0 [0,0]; 3 | 0 | 0 | False |
| V1_bare_quote_exception_blocks | 0, 0, 0 | 0, 0, 0 | 0 [0,0]; 3 | 0 [0,0]; 3 | 0 | 0 | False |
| V1_bare_quote_exception_blocks_conditional | N/A, N/A, N/A | N/A, N/A, N/A | N/A [N/A,N/A]; 0 | N/A [N/A,N/A]; 0 | N/A | N/A | N/A |
| cancelled_fetch_requests | 0, 0, 0 | 0, 0, 0 | 0 [0,0]; 3 | 0 [0,0]; 3 | 0 | 0 | False |
| component_error_events | 4, 5, 5 | 8, 2, 21 | 4.6666667 [4,5]; 3 | 10.333333 [2,21]; 3 | 5.6666667 | 19 | False |
| component_unsuccessful_events_without_error | 5, 6, 6 | 6, 4, 25 | 5.6666667 [5,6]; 3 | 11.666667 [4,25]; 3 | 6 | 21 | False |
| distinct_failed_fetch_urls | 4, 5, 5 | 4, 2, 21 | 4.6666667 [4,5]; 3 | 9 [2,21]; 3 | 4.3333333 | 19 | False |
| downloaded_raw_artifact_bytes | 19671181, 25465392, 33735708 | 22253050, 22854754, 19849593 | 26290760 [19671181,33735708]; 3 | 21652466 [19849593,22854754]; 3 | -4638294.7 | 14064527 | False |
| failed_fetch_requests | 4, 5, 5 | 4, 2, 21 | 4.6666667 [4,5]; 3 | 9 [2,21]; 3 | 4.3333333 | 19 | False |
| fetch_cache_hit_requests | 4, 0, 1 | 0, 1, 0 | 1.6666667 [0,4]; 3 | 0.33333333 [0,1]; 3 | -1.3333333 | 4 | False |
| fetch_repeats_after_failure | 0, 0, 0 | 0, 0, 0 | 0 [0,0]; 3 | 0 [0,0]; 3 | 0 | 0 | False |
| fetch_repeats_per_failed_url | 0, 0, 0 | 0, 0, 0 | 0 [0,0]; 3 | 0 [0,0]; 3 | 0 | 0 | False |
| fetch_requests | 99, 63, 101 | 66, 68, 98 | 87.666667 [63,101]; 3 | 77.333333 [66,98]; 3 | -10.333333 | 38 | False |
| fetch_shared_requests | 0, 0, 0 | 0, 0, 0 | 0 [0,0]; 3 | 0 [0,0]; 3 | 0 | 0 | False |
| fetched_readable_characters | 1305812, 1249347, 1651962 | 1068214, 945540, 1293190 | 1402373.7 [1249347,1651962]; 3 | 1102314.7 [945540,1293190]; 3 | -300059 | 402615 | False |
| fetched_to_largest_root_ratio | 15.07692, 15.142315, 19.117939 | 9.9207244, 9.1615879, 10.167707 | 16.445725 [15.07692,19.117939]; 3 | 9.7500065 [9.1615879,10.167707]; 3 | -6.6957181 | 4.0410196 | True |
| invalid_search_query_requests | 0, 0, 0 | 0, 0, 0 | 0 [0,0]; 3 | 0 [0,0]; 3 | 0 | 0 | False |
| largest_root_partition_code | 16138, 14879, 20534 | 19340, 21039, 29700 | 17183.667 [14879,20534]; 3 | 23359.667 [19340,29700]; 3 | 6176 | 10360 | False |
| largest_root_partition_harness | 1986, 1986, 1986 | 34226, 34226, 34226 | 1986 [1986,1986]; 3 | 34226 [34226,34226]; 3 | 32240 | 0 | True |
| largest_root_partition_other_task_instructions | 7423, 7423, 7423 | 7423, 7423, 7423 | 7423 [7423,7423]; 3 | 7423 [7423,7423]; 3 | 0 | 0 | False |
| largest_root_partition_question_and_columns | 175, 175, 175 | 175, 175, 175 | 175 [175,175]; 3 | 175 [175,175]; 3 | 0 | 0 | False |
| largest_root_partition_repl_output | 56099, 53424, 51588 | 42058, 35890, 51042 | 53703.667 [51588,56099]; 3 | 42996.667 [35890,51042]; 3 | -10707 | 15152 | False |
| largest_root_partition_system | 3146, 3146, 3146 | 3146, 3146, 3146 | 3146 [3146,3146]; 3 | 3146 [3146,3146]; 3 | 0 | 0 | False |
| largest_root_partition_wrappers | 1643, 1474, 1557 | 1307, 1308, 1474 | 1558 [1474,1643]; 3 | 1363 [1307,1474]; 3 | -195 | 169 | True |
| largest_root_prompt_characters | 86610, 82507, 86409 | 107675, 103207, 127186 | 85175.333 [82507,86610]; 3 | 112689.33 [103207,127186]; 3 | 27514 | 23979 | True |
| model_calls_other | 0, 0, 0 | 0, 0, 0 | 0 [0,0]; 3 | 0 [0,0]; 3 | 0 | 0 | False |
| model_calls_refine | 0, 0, 0 | 0, 0, 0 | 0 [0,0]; 3 | 0 [0,0]; 3 | 0 | 0 | False |
| model_calls_root | 16, 14, 15 | 12, 12, 14 | 15 [14,16]; 3 | 12.666667 [12,14]; 3 | -2.3333333 | 2 | True |
| model_calls_search | 50, 43, 50 | 37, 39, 37 | 47.666667 [43,50]; 3 | 37.666667 [37,39]; 3 | -10 | 7 | True |
| model_calls_sub | 73, 23, 69 | 34, 35, 52 | 55 [23,73]; 3 | 40.333333 [34,52]; 3 | -14.666667 | 50 | False |
| model_calls_total | 139, 80, 134 | 83, 86, 103 | 117.66667 [80,139]; 3 | 90.666667 [83,103]; 3 | -27 | 59 | False |
| model_completion_records | 139, 80, 134 | 83, 86, 103 | 117.66667 [80,139]; 3 | 90.666667 [83,103]; 3 | -27 | 59 | False |
| model_missing_completion_records | 0, 0, 0 | 0, 0, 0 | 0 [0,0]; 3 | 0 [0,0]; 3 | 0 | 0 | False |
| model_retries | 0, 0, 0 | 0, 0, 0 | 0 [0,0]; 3 | 0 [0,0]; 3 | 0 | 0 | False |
| page_root_50gram_overlap_fraction | 0.021342276, 0.007547943, 0.0078234245 | 0.0014388503, 0.0004198659, 0.0012689551 | 0.012237881 [0.007547943,0.021342276]; 3 | 0.0010425571 [0.0004198659,0.0014388503]; 3 | -0.011195324 | 0.013794333 | False |
| pending_fetch_requests | 0, 0, 0 | 0, 0, 0 | 0 [0,0]; 3 | 0 [0,0]; 3 | 0 | 0 | False |
| repeated_exact_search_requests | 0, 0, 0 | 0, 0, 0 | 0 [0,0]; 3 | 0 [0,0]; 3 | 0 | 0 | False |
| repl_error_blocks | 0, 0, 0 | 1, 0, 0 | 0 [0,0]; 3 | 0.33333333 [0,1]; 3 | 0.33333333 | 1 | False |
| required_cells | 140, 140, 140 | 140, 140, 140 | 140 [140,140]; 3 | 140 [140,140]; 3 | 0 | 0 | False |
| retained_text_instances | 91, 58, 95 | 62, 65, 77 | 81.333333 [58,95]; 3 | 68 [62,77]; 3 | -13.333333 | 37 | False |
| run_wall_seconds | 1047.9783, 684.78853, 930.61845 | 961.92948, 806.30749, 1530.2494 | 887.7951 [684.78853,1047.9783]; 3 | 1099.4954 [806.30749,1530.2494]; 3 | 211.70034 | 723.94187 | False |
| search_cache_hit_requests | 0, 0, 0 | 0, 0, 0 | 0 [0,0]; 3 | 0 [0,0]; 3 | 0 | 0 | False |
| search_shared_requests | 0, 0, 0 | 0, 0, 0 | 0 [0,0]; 3 | 0 [0,0]; 3 | 0 | 0 | False |
| semantic_common_nationality_component_omission_cells | 0, 0, 1 | 2, 2, 1 | 0.33333333 [0,1]; 3 | 1.6666667 [1,2]; 3 | 1.3333333 | 1 | True |
| semantic_common_nationality_conflict_cells | 1, 1, 1 | 1, 1, 1 | 1 [1,1]; 3 | 1 [1,1]; 3 | 0 | 0 | False |
| semantic_concurrent_affiliation_scope_concerns | 9, 9, 12 | 10, 9, 9 | 10 [9,12]; 3 | 9.3333333 [9,10]; 3 | -0.66666667 | 3 | False |
| semantic_dated_omitted_affiliation_cells | 8, 8, 11 | 9, 8, 8 | 9 [8,11]; 3 | 8.3333333 [8,9]; 3 | -0.66666667 | 3 | False |
| semantic_proven_false_required_cells | N/A, N/A, N/A | 0, 0, 0 | N/A [N/A,N/A]; 0 | 0 [0,0]; 3 | N/A | N/A | N/A |
| semantic_selected_quote_incomplete_required_cells | N/A, N/A, N/A | N/A, N/A, 1 | N/A [N/A,N/A]; 0 | 1 [1,1]; 1 | N/A | N/A | N/A |
| semantic_semantically_supported_required_cells | 140, 140, 140 | 140, 140, 140 | 140 [140,140]; 3 | 140 [140,140]; 3 | 0 | 0 | False |
| semantic_undated_affiliation_lead_cells | 1, 1, 1 | 1, 1, 1 | 1 [1,1]; 3 | 1 [1,1]; 3 | 0 | 0 | False |
| semantic_unresolved_semantic_cells | 0, 0, 0 | 0, 0, 0 | 0 [0,0]; 3 | 0 [0,0]; 3 | 0 | 0 | False |
| stalled_search_signals | 41, 33, 40 | 36, 37, 24 | 38 [33,41]; 3 | 32.333333 [24,37]; 3 | -5.6666667 | 13 | False |
| subcall_backend_chars | 1838016, 1765811, 3488197 | 2613298, 2537076, 3336854 | 2364008 [1765811,3488197]; 3 | 2829076 [2537076,3336854]; 3 | 465068 | 1722386 | False |
| subcall_backend_chars_max | 153968, 234383, 235207 | 536156, 348252, 329722 | 207852.67 [153968,235207]; 3 | 404710 [329722,536156]; 3 | 196857.33 | 206434 | False |
| subcall_backend_chars_mean | 25178.301, 76774.391, 50553.58 | 79190.848, 72487.886, 64170.269 | 50835.424 [25178.301,76774.391]; 3 | 71949.668 [64170.269,79190.848]; 3 | 21114.244 | 51596.09 | False |
| subcall_backend_chars_min | 1015, 5431, 4875 | 8199, 4350, 3467 | 3773.6667 [1015,5431]; 3 | 5338.6667 [3467,8199]; 3 | 1565 | 4732 | False |
| subcall_count | 73, 23, 69 | 33, 35, 52 | 55 [23,73]; 3 | 40 [33,52]; 3 | -15 | 50 | False |
| subcall_input_chars | 1824730, 1761625, 3475639 | 2607292, 2530706, 3327390 | 2353998 [1761625,3475639]; 3 | 2821796 [2530706,3327390]; 3 | 467798 | 1714014 | False |
| subcall_input_chars_max | 153786, 234201, 235025 | 535974, 348070, 329540 | 207670.67 [153786,235025]; 3 | 404528 [329540,535974]; 3 | 196857.33 | 206434 | False |
| subcall_input_chars_mean | 24996.301, 76592.391, 50371.58 | 79008.848, 72305.886, 63988.269 | 50653.424 [24996.301,76592.391]; 3 | 71767.668 [63988.269,79008.848]; 3 | 21114.244 | 51596.09 | False |
| subcall_input_chars_min | 833, 5249, 4693 | 8017, 4168, 3285 | 3591.6667 [833,5249]; 3 | 5156.6667 [3285,8017]; 3 | 1565 | 4732 | False |
| subcall_prompt_chars | 1790588, 1740905, 3441232 | 2585263, 2505969, 3290004 | 2324241.7 [1740905,3441232]; 3 | 2793745.3 [2505969,3290004]; 3 | 469503.67 | 1700327 | False |
| subcall_prompt_input_chars_max | 153414, 234201, 234639 | 535974, 347577, 328830 | 207418 [153414,234639]; 3 | 404127 [328830,535974]; 3 | 196709 | 207144 | False |
| subcall_prompt_input_chars_mean | 24528.603, 75691.522, 49872.928 | 78341.303, 71599.114, 63269.308 | 50031.017 [24528.603,75691.522]; 3 | 71069.908 [63269.308,78341.303]; 3 | 21038.891 | 51162.919 | False |
| subcall_prompt_input_chars_min | 688, 5249, 4468 | 7689, 3850, 2796 | 3468.3333 [688,5249]; 3 | 4778.3333 [2796,7689]; 3 | 1310 | 4893 | False |
| subcall_schema_chars | 34142, 20720, 34407 | 22029, 24737, 37386 | 29756.333 [20720,34407]; 3 | 28050.667 [22029,37386]; 3 | -1705.6667 | 15357 | False |
| subcall_schema_input_chars_max | 1636, 1636, 1636 | 1636, 1636, 1636 | 1636 [1636,1636]; 3 | 1636 [1636,1636]; 3 | 0 | 0 | False |
| subcall_schema_input_chars_mean | 467.69863, 900.86957, 498.65217 | 667.54545, 706.77143, 718.96154 | 622.40679 [467.69863,900.86957]; 3 | 697.75947 [667.54545,718.96154]; 3 | 75.352684 | 433.17094 | False |
| subcall_schema_input_chars_min | 0, 0, 145 | 0, 0, 0 | 48.333333 [0,145]; 3 | 0 [0,0]; 3 | -48.333333 | 145 | False |
| successful_unique_fetched_urls | 91, 58, 95 | 62, 65, 77 | 81.333333 [58,95]; 3 | 68 [62,77]; 3 | -13.333333 | 37 | False |
| unique_text_hashes | 91, 58, 95 | 62, 65, 75 | 81.333333 [58,95]; 3 | 67.333333 [62,75]; 3 | -14 | 37 | False |
| whole_text_hash_dedup_readable_characters | 1305812, 1249347, 1651962 | 1068214, 945540, 1281786 | 1402373.7 [1249347,1651962]; 3 | 1098513.3 [945540,1281786]; 3 | -303860.33 | 402615 | False |

### All individual run metrics

| Metric | A | SI | B1 | B0-1 | B0-2 | B0-3 | B1-frozen-1 | B1-frozen-2 | B1-frozen-3 |
|---|---|---|---|---|---|---|---|---|---|
| D0_duplicate_candidate_groups | N/A: Dedicated additional behavior-count review was registered for B arms; this A/SI metric was not independently scored under that protocol. Narrative examples are not substituted as counts. | N/A: Dedicated additional behavior-count review was registered for B arms; this A/SI metric was not independently scored under that protocol. Narrative examples are not substituted as counts. | 0 | 0 | 0 | 0 | 1 | 0 | 0 |
| D1_reconciled_before_mutation_groups | N/A: Dedicated additional behavior-count review was registered for B arms; this A/SI metric was not independently scored under that protocol. Narrative examples are not substituted as counts. | N/A: Dedicated additional behavior-count review was registered for B arms; this A/SI metric was not independently scored under that protocol. Narrative examples are not substituted as counts. | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| D1_reconciled_before_mutation_groups_conditional | N/A: Dedicated additional behavior-count review was registered for B arms; this A/SI metric was not independently scored under that protocol. Narrative examples are not substituted as counts. | N/A: Dedicated additional behavior-count review was registered for B arms; this A/SI metric was not independently scored under that protocol. Narrative examples are not substituted as counts. | N/A: N/A because D0_duplicate_candidate_groups = 0; registered duplicate-group benefit was not exercised. | N/A: D0=0; duplicate reconciliation prediction unexercised. | N/A: N/A: D0=0; no duplicate candidate exposure. | N/A: N/A: D0=0; noduplicatecandidateexposure. | 0 | N/A: D0=0; no duplicate candidate group exposure. | N/A: D0=0; no duplicatecandidateexposure. |
| D2_destructive_overwrite_groups | N/A: Dedicated additional behavior-count review was registered for B arms; this A/SI metric was not independently scored under that protocol. Narrative examples are not substituted as counts. | N/A: Dedicated additional behavior-count review was registered for B arms; this A/SI metric was not independently scored under that protocol. Narrative examples are not substituted as counts. | 0 | 0 | 0 | 0 | 1 | 0 | 0 |
| D2_destructive_overwrite_groups_conditional | N/A: Dedicated additional behavior-count review was registered for B arms; this A/SI metric was not independently scored under that protocol. Narrative examples are not substituted as counts. | N/A: Dedicated additional behavior-count review was registered for B arms; this A/SI metric was not independently scored under that protocol. Narrative examples are not substituted as counts. | N/A: N/A because D0_duplicate_candidate_groups = 0; registered duplicate-group benefit was not exercised. | N/A: D0=0; duplicate overwrite prediction unexercised. | N/A: N/A: D0=0; no duplicate candidate exposure. | N/A: N/A: D0=0; noduplicatecandidateexposure. | 1 | N/A: D0=0; no duplicate candidate group exposure. | N/A: D0=0; no duplicatecandidateexposure. |
| D3_unresolved_overwrite_groups | N/A: Dedicated additional behavior-count review was registered for B arms; this A/SI metric was not independently scored under that protocol. Narrative examples are not substituted as counts. | N/A: Dedicated additional behavior-count review was registered for B arms; this A/SI metric was not independently scored under that protocol. Narrative examples are not substituted as counts. | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| D3_unresolved_overwrite_groups_conditional | N/A: Dedicated additional behavior-count review was registered for B arms; this A/SI metric was not independently scored under that protocol. Narrative examples are not substituted as counts. | N/A: Dedicated additional behavior-count review was registered for B arms; this A/SI metric was not independently scored under that protocol. Narrative examples are not substituted as counts. | N/A: N/A because D0_duplicate_candidate_groups = 0; registered duplicate-group benefit was not exercised. | N/A: D0=0; unresolved duplicate overwrite prediction unexercised. | N/A: N/A: D0=0; no duplicate candidate exposure. | N/A: N/A: D0=0; noduplicatecandidateexposure. | 0 | N/A: D0=0; no duplicate candidate group exposure. | N/A: D0=0; no duplicatecandidateexposure. |
| F1_failed_fetch_exposure | 1 | 0 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| F1_failed_response_extraction_calls | N/A: Dedicated additional behavior-count review was registered for B arms; this A/SI metric was not independently scored under that protocol. Narrative examples are not substituted as counts. | N/A: Dedicated additional behavior-count review was registered for B arms; this A/SI metric was not independently scored under that protocol. Narrative examples are not substituted as counts. | 2 | 0 | 4 | 7 | 0 | 0 | 0 |
| F1_failed_response_extraction_calls_conditional | N/A: Dedicated additional behavior-count review was registered for B arms; this A/SI metric was not independently scored under that protocol. Narrative examples are not substituted as counts. | N/A: Dedicated additional behavior-count review was registered for B arms; this A/SI metric was not independently scored under that protocol. Narrative examples are not substituted as counts. | 2 | 0 | 4 | 7 | 0 | 0 | 0 |
| M1_completed_requests | 31 | 3 | 86 | 50 | 43 | 50 | 37 | 39 | 37 |
| M1_late_fraction | 0.3548387096774194 | 0.0 | 0.5 | 0.72 | 1.0 | 0.2 | 0.2702702702702703 | 0.2564102564102564 | 0.2702702702702703 |
| M1_late_requests | 11 | 0 | 43 | 36 | 43 | 10 | 10 | 10 | 10 |
| M2_corrected_empty_records | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Q1_duplicate_output_identities | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Q1_identity_symmetric_difference | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Q1_identity_symmetric_difference_raw | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Q1_output_rows | 28 | 5 | 28 | 28 | 28 | 28 | 28 | 28 | 28 |
| Q1_self_check_issues | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Q1_uncited_cells | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| R2_retained_download_reuse_blocks | N/A: Dedicated additional behavior-count review was registered for B arms; this A/SI metric was not independently scored under that protocol. Narrative examples are not substituted as counts. | N/A: Dedicated additional behavior-count review was registered for B arms; this A/SI metric was not independently scored under that protocol. Narrative examples are not substituted as counts. | 13 | 12 | 10 | 12 | 9 | 9 | 11 |
| S1_pre_answer_ready_validation | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| S2_gap_exposed | 1 | 0 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| S2_supplementary_unique_urls | 36 | 0 | 55 | 76 | 43 | 73 | 52 | 49 | 38 |
| S2_supplementary_unique_urls_conditional | 36 | N/A: No exposed gap; conditional prediction not exercised | 55 | 76 | 43 | 73 | 52 | 49 | 38 |
| S3_caught_printed_quote_failures | 4 | 0 | 0 | 1 | 6 | 0 | 0 | 0 | 6 |
| S3_quote_exception_blocks | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| S4_citation_violation_cells | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| V1_bare_quote_exception_blocks | N/A: Dedicated additional behavior-count review was registered for B arms; this A/SI metric was not independently scored under that protocol. Narrative examples are not substituted as counts. | N/A: Dedicated additional behavior-count review was registered for B arms; this A/SI metric was not independently scored under that protocol. Narrative examples are not substituted as counts. | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| V1_bare_quote_exception_blocks_conditional | N/A: Dedicated additional behavior-count review was registered for B arms; this A/SI metric was not independently scored under that protocol. Narrative examples are not substituted as counts. | N/A: Dedicated additional behavior-count review was registered for B arms; this A/SI metric was not independently scored under that protocol. Narrative examples are not substituted as counts. | N/A: N/A because S3_quote_exception_blocks = 0; the registered diagnostic mechanism was not exercised. | N/A: No quotation-exception exposure: S3=0, so diagnostic prediction is unexercised. | N/A: N/A: S3_quote_exception_blocks=0. | N/A: N/A: S3quotationexceptions=0. | N/A: S3=0; the conditional diagnostic is not exercised. | N/A: No quote-exception exposure. | N/A: S3exceptionexposure0. |
| cancelled_fetch_requests | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| component_error_events | 14 | 0 | 6 | 4 | 5 | 5 | 8 | 2 | 21 |
| component_unsuccessful_events_without_error | 17 | 0 | 8 | 5 | 6 | 6 | 6 | 4 | 25 |
| distinct_failed_fetch_urls | 13 | 0 | 6 | 4 | 5 | 5 | 4 | 2 | 21 |
| downloaded_raw_artifact_bytes | 18120283 | 356885 | 15554147 | 19671181 | 25465392 | 33735708 | 22253050 | 22854754 | 19849593 |
| failed_fetch_requests | 13 | 0 | 6 | 4 | 5 | 5 | 4 | 2 | 21 |
| fetch_cache_hit_requests | 0 | 1 | 0 | 4 | 0 | 1 | 0 | 1 | 0 |
| fetch_repeats_after_failure | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| fetch_repeats_per_failed_url | 0.0 | N/A: No failed URLs (zero denominator) | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| fetch_requests | 60 | 4 | 92 | 99 | 63 | 101 | 66 | 68 | 98 |
| fetch_shared_requests | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| fetched_readable_characters | 900192 | 68075 | 921760 | 1305812 | 1249347 | 1651962 | 1068214 | 945540 | 1293190 |
| fetched_to_largest_root_ratio | 8.01795639162035 | 2.3807442120724627 | 5.259085981628345 | 15.076919524304353 | 15.142315197498394 | 19.1179391035656 | 9.920724402136058 | 9.161587876791303 | 10.167707137578036 |
| invalid_search_query_requests | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| largest_root_partition_code | 24934 | 4062 | 32962 | 16138 | 14879 | 20534 | 19340 | 21039 | 29700 |
| largest_root_partition_harness | 4811 | 4 | 45061 | 1986 | 1986 | 1986 | 34226 | 34226 | 34226 |
| largest_root_partition_other_task_instructions | 15562 | 8282 | 16374 | 7423 | 7423 | 7423 | 7423 | 7423 | 7423 |
| largest_root_partition_question_and_columns | 177 | 470 | 175 | 175 | 175 | 175 | 175 | 175 | 175 |
| largest_root_partition_repl_output | 61976 | 11906 | 75884 | 56099 | 53424 | 51588 | 42058 | 35890 | 51042 |
| largest_root_partition_system | 3146 | 3146 | 3146 | 3146 | 3146 | 3146 | 3146 | 3146 | 3146 |
| largest_root_partition_wrappers | 1666 | 724 | 1668 | 1643 | 1474 | 1557 | 1307 | 1308 | 1474 |
| largest_root_prompt_characters | 112272 | 28594 | 175270 | 86610 | 82507 | 86409 | 107675 | 103207 | 127186 |
| model_calls_other | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| model_calls_refine | 13 | 2 | 16 | 0 | 0 | 0 | 0 | 0 | 0 |
| model_calls_root | 16 | 5 | 16 | 16 | 14 | 15 | 12 | 12 | 14 |
| model_calls_search | 31 | 3 | 86 | 50 | 43 | 50 | 37 | 39 | 37 |
| model_calls_sub | 42 | 1 | 47 | 73 | 23 | 69 | 34 | 35 | 52 |
| model_calls_total | 102 | 11 | 165 | 139 | 80 | 134 | 83 | 86 | 103 |
| model_completion_records | 102 | 11 | 165 | 139 | 80 | 134 | 83 | 86 | 103 |
| model_missing_completion_records | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| model_retries | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| page_root_50gram_overlap_fraction | 0.0677000017773986 | 0.006008079324274697 | 0.007384785627495226 | 0.02134227591720707 | 0.007547943045446942 | 0.007823424509764752 | 0.0014388502678302287 | 0.00041986589673625655 | 0.0012689550646076755 |
| pending_fetch_requests | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| repeated_exact_search_requests | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| repl_error_blocks | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 |
| required_cells | 140 | 15 | 140 | 140 | 140 | 140 | 140 | 140 | 140 |
| retained_text_instances | 47 | 3 | 86 | 91 | 58 | 95 | 62 | 65 | 77 |
| run_wall_seconds | 1414.330821 | 181.680589 | 2616.339354 | 1047.978328 | 684.788533 | 930.618448 | 961.92948 | 806.307491 | 1530.249356 |
| search_cache_hit_requests | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| search_shared_requests | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| semantic_common_nationality_component_omission_cells | N/A: This additional common-pool diagnostic covers the seven B physics outputs only. The independent A/SI semantic review and its original scope count remain separate. | N/A: This additional common-pool diagnostic covers the seven B physics outputs only. The independent A/SI semantic review and its original scope count remain separate. | 2 | 0 | 0 | 1 | 2 | 2 | 1 |
| semantic_common_nationality_conflict_cells | N/A: This additional common-pool diagnostic covers the seven B physics outputs only. The independent A/SI semantic review and its original scope count remain separate. | N/A: This additional common-pool diagnostic covers the seven B physics outputs only. The independent A/SI semantic review and its original scope count remain separate. | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| semantic_concurrent_affiliation_scope_concerns | 4 | 0 | 9 | 9 | 9 | 12 | 10 | 9 | 9 |
| semantic_dated_omitted_affiliation_cells | N/A: This additional common-pool diagnostic covers the seven B physics outputs only. The independent A/SI semantic review and its original scope count remain separate. | N/A: This additional common-pool diagnostic covers the seven B physics outputs only. The independent A/SI semantic review and its original scope count remain separate. | 8 | 8 | 8 | 11 | 9 | 8 | 8 |
| semantic_proven_false_required_cells | 0 | N/A: Not supplied by manual review | N/A: Not supplied by manual review | N/A: Not supplied by manual review | N/A: Not supplied by manual review | N/A: Not supplied by manual review | 0 | 0 | 0 |
| semantic_selected_quote_incomplete_required_cells | N/A: Not supplied by manual review | N/A: Not supplied by manual review | N/A: Not supplied by manual review | N/A: Not supplied by manual review | N/A: Not supplied by manual review | N/A: Not supplied by manual review | N/A: Not supplied by manual review | N/A: Not supplied by manual review | 1 |
| semantic_semantically_supported_required_cells | 139 | 15 | 140 | 140 | 140 | 140 | 140 | 140 | 140 |
| semantic_undated_affiliation_lead_cells | N/A: This additional common-pool diagnostic covers the seven B physics outputs only. The independent A/SI semantic review and its original scope count remain separate. | N/A: This additional common-pool diagnostic covers the seven B physics outputs only. The independent A/SI semantic review and its original scope count remain separate. | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| semantic_unresolved_semantic_cells | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| stalled_search_signals | 29 | 2 | 83 | 41 | 33 | 40 | 36 | 37 | 24 |
| subcall_backend_chars | 813820 | 71956 | 2770798 | 1838016 | 1765811 | 3488197 | 2613298 | 2537076 | 3336854 |
| subcall_backend_chars_max | 63562 | 71956 | 163072 | 153968 | 234383 | 235207 | 536156 | 348252 | 329722 |
| subcall_backend_chars_mean | 19376.666666666668 | 71956 | 58953.14893617021 | 25178.301369863013 | 76774.39130434782 | 50553.57971014493 | 79190.84848484848 | 72487.88571428572 | 64170.269230769234 |
| subcall_backend_chars_min | 727 | 71956 | 607 | 1015 | 5431 | 4875 | 8199 | 4350 | 3467 |
| subcall_count | 42 | 1 | 47 | 73 | 23 | 69 | 33 | 35 | 52 |
| subcall_input_chars | 806176 | 71774 | 2762244 | 1824730 | 1761625 | 3475639 | 2607292 | 2530706 | 3327390 |
| subcall_input_chars_max | 63380 | 71774 | 162890 | 153786 | 234201 | 235025 | 535974 | 348070 | 329540 |
| subcall_input_chars_mean | 19194.666666666668 | 71774 | 58771.14893617021 | 24996.301369863013 | 76592.39130434782 | 50371.57971014493 | 79008.84848484848 | 72305.88571428572 | 63988.269230769234 |
| subcall_input_chars_min | 545 | 71774 | 425 | 833 | 5249 | 4693 | 8017 | 4168 | 3285 |
| subcall_prompt_chars | 779657 | 70567 | 2732109 | 1790588 | 1740905 | 3441232 | 2585263 | 2505969 | 3290004 |
| subcall_prompt_input_chars_max | 62869 | 70567 | 162352 | 153414 | 234201 | 234639 | 535974 | 347577 | 328830 |
| subcall_prompt_input_chars_mean | 18563.261904761905 | 70567 | 58129.97872340425 | 24528.602739726026 | 75691.52173913043 | 49872.92753623189 | 78341.30303030302 | 71599.11428571428 | 63269.307692307695 |
| subcall_prompt_input_chars_min | 400 | 70567 | 425 | 688 | 5249 | 4468 | 7689 | 3850 | 2796 |
| subcall_schema_chars | 26519 | 1207 | 30135 | 34142 | 20720 | 34407 | 22029 | 24737 | 37386 |
| subcall_schema_input_chars_max | 1636 | 1207 | 1636 | 1636 | 1636 | 1636 | 1636 | 1636 | 1636 |
| subcall_schema_input_chars_mean | 631.4047619047619 | 1207 | 641.1702127659574 | 467.6986301369863 | 900.8695652173913 | 498.6521739130435 | 667.5454545454545 | 706.7714285714286 | 718.9615384615385 |
| subcall_schema_input_chars_min | 0 | 1207 | 0 | 0 | 0 | 145 | 0 | 0 | 0 |
| successful_unique_fetched_urls | 47 | 3 | 86 | 91 | 58 | 95 | 62 | 65 | 77 |
| unique_text_hashes | 47 | 3 | 86 | 91 | 58 | 95 | 62 | 65 | 75 |
| whole_text_hash_dedup_readable_characters | 900192 | 68075 | 921760 | 1305812 | 1249347 | 1651962 | 1068214 | 945540 | 1281786 |

