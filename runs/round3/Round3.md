# Round 3 — item 1(c) decision checkpoint

Round 3 is **unfinished**. The on-disk evidence establishes a fetch-transport limitation that invokes the user's explicit instruction: “If full text can't come through the current web tool, show the evidence, then stop and ask me before changing the fetch path.” No fetch-path change, product fix, harness rollback, or new A/SI/B/explicit run has been made. The requested sequence remains pending at item 1. This is a checkpoint, not a completed comparison or a replacement for Round 2.

## 1. RLM pages: root cause and transport evidence

`ResearchTools.fetch` sends a model prompt asking it to open the URL and “Copy relevant page text as faithfully as possible.” The optional `focus` further selects what is returned. The returned Python string is `CodexBackend.complete(...).strip()`, not the native web page body. [Fetch path](/Users/mukeshreddypochamreddy/Desktop/loop-research/src/loop_research/repl_tools.py:281).

`CodexBackend.complete` reads the file specified by `--output-last-message` as the response. It separately archives complete `web_search` events from CLI stdout. Its successful return is that final model message. The URL guard in `fetch` verifies a completed `open_page` action for the requested URL; it does not make the final message a full page or establish textual equivalence to the opened resource. [Command](/Users/mukeshreddypochamreddy/Desktop/loop-research/src/loop_research/codex_backend.py:101), [event/response handling](/Users/mukeshreddypochamreddy/Desktop/loop-research/src/loop_research/codex_backend.py:190).

The saved A run directly distinguishes the two:

- The native event identifies the Academy's 2015 chemistry announcement at the requested URL and reports `Total lines: 122`. It contains title, URL, domain, reference, snippet and thumbnail metadata; no page body. The backend response has 270 characters. [Complete native event, call 47](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/research-65cc14c4722a4caf9c67f56e2883a0ca/289901ce021c28d56fdac993/codex_calls.jsonl:47).
- The corresponding value returned in the fetch batch begins, “I can’t reproduce the full copyrighted announcement.” It supplies a short prize-motivation excerpt and a link. Another return in the same batch explicitly declines to reproduce the full announcement verbatim. These are actual model returns, not inferred truncation. [Returned batch, trajectory 29](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/research-65cc14c4722a4caf9c67f56e2883a0ca/289901ce021c28d56fdac993/trajectory.jsonl:29).
- A later request for the same resource returns 509 characters while the native event still reports 122 lines. This illustrates focus-dependent model rendering, not two measured versions of a raw page. [Call 61](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/research-65cc14c4722a4caf9c67f56e2883a0ca/289901ce021c28d56fdac993/codex_calls.jsonl:61).

The new offline audit reads the completed archives themselves, cross-checks the saved inventory, and verifies the largest-root-prompt lengths and SHA-256 hashes. Across A, B1, B1-frozen, B0, SI and explicit there are **375 completed open actions and 375 result objects**. Every open-result snippet is `Total lines: N`; the observed key sets contain no body or character/byte count. Counts by arm are 54, 101, 133, 82, 3 and 2 respectively. All six archived research manifests are complete. [Reproducible audit](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/audit_fetch_gate.py), [complete evidence and input hashes](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/fetch_gate_evidence.json).

The on-disk pinned CLI source defines `WebSearchItem.results` as optional generic JSON, not a documented full-body field. Consequently the evidence supports **no full text exposed in this observed transport**, not a universal impossibility claim about every future provider response. Some short pages may be reproduced by the model. That does not provide a general full-readable-page transport, and the saved refusal examples rule out treating a prompt-only wording change as demonstrated full-page delivery. No live probe or new fetch was made. [Pinned event type](/Users/mukeshreddypochamreddy/Desktop/loop-research/.verification/codex/codex-rs/exec/src/exec_events.rs:298).

The root still receives the full initial task prompt, code history, formatted REPL output and current retrieved entries. In A the largest prompt's 79,147 characters include 49,172 formatted REPL-output characters and 16,120 code characters. The output includes printed context, search hits, diagnostics and selected page extracts. Short model-rendered fetch returns therefore remain smaller than the accumulated root history even when the worker stores and processes them in variables. Neither variable storage nor low overlap alone satisfies the unchanged size conjunction. [Exact root partition and print-site analysis](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round2/A.root_analysis.md), [root boundary](/Users/mukeshreddypochamreddy/Desktop/loop-research/src/loop_research/session.py:116), [worker invocation](/Users/mukeshreddypochamreddy/Desktop/loop-research/src/loop_research/agent.py:263).

| Saved Round 2 arm | Fetched text chars | Largest root chars | Fetched/root | 50-character overlap | Rows | Issues | Uncited cells | Round 3 after |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| A | 12,187 | 79,147 | 0.1540 | 27.315992% | 28 | 0 | 0 | Not run |
| B1 | 34,985 | 158,458 | 0.2208 | 25.942547% | 28 | 0 | 0 | Not run |
| B1-frozen | 29,020 | 122,054 | 0.2378 | 14.076499% | 28 | 0 | 0 | Not run |
| B0 | 20,456 | 105,964 | 0.1930 | 35.808565% | 28 | 0 | 0 | Not run |
| SI | 1,343 | 24,866 | 0.0540 | 18.689501% | 5 | 0 | 0 | Not run |
| explicit | 340 | 68,104 | 0.0050 | 19.117647% | 2 | 0 | 0 | Not run |

These are saved before measurements, independently checked against the prompt files and audits; none is a new Round 3 result. No raw-page size is inferred from line counts. Equal row counts do not independently prove identical row identities or semantic quality; Round 2's attribution qualifications still apply.

**Diff:** no product change. The new audit and this checkpoint are the only additions. **Generalization:** the diagnosed selection and final-message boundary apply to every URL; there is no site-specific condition. **Verdict:** the existing size criterion **doesn't work**; a Round 3 fix is **not exercised**.

**Decision requested under item 1(c):** authorize replacing the model-mediated fetch return with a trusted-host page retrieval and readable-text extraction path, retaining Codex web search for discovery. The implementation would preserve source bytes/provenance and complete readable text in REPL variables, cache the actual retrieval, and update provenance checks to validate the real retrieval receipt. It would not pretend the old Codex-open receipt proves a new direct fetch. No padding, repeated-text inflation, extra retrievals solely for size, or root-prompt truncation is proposed. This is the concrete boundary change awaiting approval; it is not implemented or claimed successful. Parser choices and full-text/quality tests would be reviewed on local fixtures before the ordered live runs.

## 2. Same-run reuse: saved diagnosis, implementation pending

Two separate causes are visible. First, `refine.run()` returns an immediate scheduling receipt; the public worker interface exposes only `run` and `rollback`. Root boundaries call `apply_refinement()` but discard its returned commits and append only relevance-filtered entries. A no-edit result therefore gives the root no completion/decline feedback. The old explicit request required waiting until completion was known, producing repeated pauses and searches despite a settled zero-edit plan. The final recorded outcome was **answer_ready on turn 30**, not an iteration-limit error: 24 pause blocks declared 985 seconds of sleep. The plan had already applied zero edits at trace 255. [Completed explicit analysis](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round2/explicit.analysis.md), [settled plan](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/research-3961381ee9da4be7b94a663cc00adb90/trace.jsonl:255).

Second, `Session.retrieve()` always queries the original question plus schema. `Harness.search()` scores only entry title/body and discards zero-score matches. A generic operational lesson can be committed successfully yet have no lexical overlap with the subject query. A's new fetch-recovery memory applied mid-task, but none of eleven later retrievals returned it. This is retrieval relevance, not evidence that the commit failed or planning remained pending. [Query construction](/Users/mukeshreddypochamreddy/Desktop/loop-research/src/loop_research/session.py:72), [score/filter](/Users/mukeshreddypochamreddy/Desktop/loop-research/src/loop_research/harness.py:132), [A commit and retrieval accounting](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round2/A.refine_analysis.md).

**Diff/generalization:** no fix yet; completion feedback and retrieval of newly committed current-run guidance require a general correction after the fetch decision. Agent control of when to request refinement remains required. **Before:** A 0/11 later retrievals returned the new memory; the explicit check made no mid-task edit and spent 985 seconds in declared sleeps. **After:** unavailable. **Verdict:** same-run reuse **not demonstrated**; the Round 3 **explicit** check is **not exercised**. No post-worker edit is counted as mid-task reuse.

## 3. Self-improvement benefit: comparison audit and runs pending

The saved control audit establishes that POST_A includes changes to usage/outcome bookkeeping on the inherited discovery entry as well as A's new entries. `Session.retrieve()` returns complete entries and records usage, so those fields reach model inputs. Simply deleting fields from the prompt would repeat the rejected Round 2 input-suppression fix and is not proposed. [Saved control audit](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round2/control_audit.json), [input-preservation review](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round2/fix_quality_review.md).

The final saved pair's date record is identical (`2026-10-18`, source `config`), and its context-without-harness hash matches. That does not establish the general `--base` behavior requested in 3(a), nor enumerate every difference across the earlier cohorts. The full bookkeeping/date-provenance root-cause audit and regression fixes are still pending. No assertion that all confounds are fixed is made.

**Diff/generalization:** no product change. **Before:** B1-frozen/B0 had 248/185 attempts, 1,961.780/1,588.753 wall seconds and 19/16 root iterations, with 28 rows, zero issues and zero uncited cells each. **After:** no new runs, mean or min–max range exists. **Verdict:** benefit **not demonstrated**; the Round 3 comparison is **not exercised**.

`predictions.md` has deliberately not been written: it must describe entries from the **new** A, after that A finishes and before any B starts. Nothing from the old A is being substituted for that preregistration. B1 and the three repeats each of B1-frozen and B0 remain pending, with separate harnesses, caches and run directories. Every preregistered metric must eventually be reported, including unfavorable outcomes; three repeats will still **not be a statistical result**.

## Ten-check table at this checkpoint

The middle column retains the last observed Round 2 verdict. The final column describes Round 3 execution status, not a new experimental outcome. Source for the retained verdicts and exact trace links: [Round 2 ten-check matrix](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round2/Round2.md:15328).

| Check | Last observed verdict | Round 3 status and evidence |
| --- | --- | --- |
| 1a — sub-calls and exact input sizes | works | not exercised; no new research runs |
| 1b — page text in REPL variables | works | not exercised; existing variables contain model returns, not verified full pages |
| 1c — mid-task refinement timing | works | not exercised; timing alone did not demonstrate later retrieval/use |
| 2a — raw opened-page versus returned size | not demonstrated | not demonstrated; fresh disk audit finds no body/count in all 375 open results |
| 2b — largest root prompt partition | works | works for saved inputs only; all six prompt hashes/lengths reverified |
| 2c — exact 50-character overlap measurement | works | not exercised anew; saved overlap values reported unchanged |
| 2d — fetched text far exceeds root, low overlap | doesn't work | doesn't work on saved evidence; full-page-path decision pending |
| 3 — historical boolean-verdict memory use | not demonstrated | not exercised; no new memory-use claim |
| 4a — after-task lesson selection/commit | works | not exercised; no new A or saved-input refinement preflight yet |
| 4b — effect isolated by frozen comparison | not demonstrated | not exercised; no predictions or repeated comparison yet |

## Verification, preservation and continuation

Executed only disk reads and the standard-library audit. `.venv/bin/python runs/round3/audit_fetch_gate.py` passes with six completed arms, 375 open actions/results and zero full-page-body fields. This is saved-evidence verification, not a product regression suite or the requested saved-refine preflight. There are no product fixes to claim tested. The research source remains at `1f610a94577dac260a0e2221845c8466225f2ed3`; the harness remains at POST_A `29d290b53bfa877e2223dc232dffb60233b32c15` pending the prescribed rollback step.

One exploratory read incorrectly treated the inventory's arm list as a dictionary and raised `TypeError`. The saved audit fixes that assumption by indexing the actual list by label, then reruns all six arms successfully. Two exploratory searches also referenced an absent optional glob/path; neither changed source or launched a process. These were operator inspection errors, not research-run errors; no comparison run is affected.

The pre-Round-3 report is exactly **2,207,879 bytes**, SHA-256 **`cbd76f98200e77723ccf8ba5cfb1b396875637253722fe68558985916c747f27`**. Its complete preimage is saved locally. This checkpoint is appended after that unchanged prefix; [append verification](/Users/mukeshreddypochamreddy/Desktop/loop-research/runs/round3/append_verification.json) records byte equality and hashes.

After the user's item 1(c) decision, the remaining order is unchanged: fix/test/commit items 1, 2 and 3(a) separately; saved refine/audit preflight; compensate/fork to BASE; traced A alongside SI; commit predictions from new A; traced B1, B1-frozen ×3 and B0 ×3; explicit reuse evidence; all metrics and full final report. Any product correction discovered during execution requires committing it and replaying every affected comparison arm on the same code.
