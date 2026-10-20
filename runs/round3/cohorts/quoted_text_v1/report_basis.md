# Round 3 report basis — outcomes pending

Active cohort: `quoted_text_v1`. Frozen runtime source: `09c77902babb879abe2b0dcc8cab7cf5209bf5ae`; installed product tree: `3f9775e49c32365a5b348282a8b8f4b42a331d22`. The earlier `final` and `fair_slots_v1` cohorts are preserved, superseded attempts. They cannot provide final controls, POST_A, or substituted predictions.

All Round 3 research numbers use **new direct-readable-v1 fetch**. Round 2 numbers below use **old model-mediated fetch**. Cross-round differences also include nondeterministic model behavior and retrieved content; they do not isolate learning. The original criterion is unchanged: fetched text must far exceed the largest root prompt, overlap must be low, and final quality must hold. A ratio merely greater than one does not establish that conjunction.

## Historical Round 2 measurements

| Arm | Returned text chars | Largest root chars | Ratio | Exact 50-gram overlap | Rows | Issues | Uncited | Model attempts | Failed fetch requests |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 12,187 | 79,147 | 0.153979 | 27.315992% | 28 | 0 | 0 | 115 | 21 |
| B1 | 34,985 | 158,458 | 0.220784 | 25.942547% | 28 | 0 | 0 | 211 | 23 |
| B1-frozen | 29,020 | 122,054 | 0.237764 | 14.076499% | 28 | 0 | 0 | 248 | 49 |
| B0 | 20,456 | 105,964 | 0.193047 | 35.808565% | 28 | 0 | 0 | 185 | 27 |
| SI | 1,343 | 24,866 | 0.054009 | 18.689501% | 5 | 0 | 0 | 14 | 0 |

B0 has 27 failed fetch requests and 28 failed backend fetch attempts. Preserve those denominators. Quality counts above are mechanical, not blanket semantic certification. Overlap uses the union of exact, case/whitespace-sensitive 50-character grams across **all** root inputs; the size denominator is the **largest** verified backend root input. Retained evidence deduplicates identical text at the same URL, not necessarily across different URLs. Do not call its character sum globally unique unless its hashes establish that.

## Fixes and evidence boundaries

The three requested fixes have separate commits, diagnoses and tests: `313603d` full direct readable fetch; `fd1be81` nonblocking refinement feedback and committed same-run retrieval; `8d45343` entry-only initial-input differences. Read their full reports for exact code paths and pre-fix evidence. No domain allowlist, model fetch fallback, padding, count-driven retrieval, new root truncation, forced lesson or agent-timing change was introduced. Public transport eligibility does not certify a source's factual reliability. Static extraction does not render JavaScript or OCR.

The first fresh cohort exposed slot starvation: a request waited 600.007106 monotonic seconds without a backend dispatch while fourteen later search requests overtook it. FIFO admission fix `cfe361f` preserves four slots, deadlines and budgets; it orders registered waiters and does not promise completion under overload. The next cohort exposed a final-refiner input limit, not an operator interruption: five identical 1,592,078-character attempts were rejected. `af3a457` stops futile redispatch of that explicit permanent rejection after one fully archived attempt. `dae5e2d` shares raw text with canonical JSON-quoted occurrences, preserving the complete supplied logical payload; the failed request becomes 855,991 characters including revised instructions. The inherited observation projection and root formatter boundaries remain unchanged. An arbitrarily large unique payload can still exceed a finite provider limit.

All errors and superseded archives remain preserved. The old A's mid-task commit/retrieval/matching action is historical evidence, not a completed-run outcome or proof of a newly caused decision. Old B partial outcomes were seen before this cohort: disclose that history in fresh predictions. Old S1 used nonexistent `records.add` and remains N/A in its original contract; `answer-ready-v2` uses the actual first root submission and requires complete executed checks of the submitted version before readiness.

## Fresh preflight and sequence

Main full suite: 967 passed, one live test deselected, 112.94 seconds. Helper suites: 8 launcher, 4 explicit launcher, 23 control-audit and 24 metric tests. Seven saved archive audits pass. Four isolated saved refinement replays each made one call, zero errors/retries, valid complete candidate accounting; they committed 1, 2, 2 and 1 edits. Exact original inputs/harnesses were preserved during replay. Their edits stay in isolated clones and do not seed research.

The shared harness was already BASE; rollback made zero compensating edits, then forked exact BASE. A and SI launched at approximately 04:28:58 UTC on October 20 with trace, separate full harness clones, caches and run directories. A uses BASE; SI retains its authoritative historical baseline so the replay guard is unchanged. After A completes, write and commit fresh entry-specific predictions before any B starts. Then B1 plus three frozen and three base controls, followed by the separate explicitly labeled same-run reuse check. Never substitute old A/POST_A or mix runtime versions.

Same-base controls must have byte-identical first researcher inputs. Cross-base inputs may differ only in complete harness entry regions, including historical A metadata. This tests full-entry intervention, not isolated lesson prose. Later tool histories may diverge. Date provenance was already equal and has no invented fix.

Every predicted and descriptive metric must be reported for each run. For the six controls include each value, arm mean and min–max, frozen-minus-base mean difference, and whether its absolute value strictly exceeds the larger within-arm range. Zero denominators remain N/A with defined-run counts. Three repeats are not a statistical result. Do not omit unfavorable measures or replace them with a composite.

## Ten unchanged check subjects

1a subcalls and exact input sizes; 1b full page variables and code; 1c A mid-task refine timing; 2a raw opened document versus returned text; 2b largest-root partition; 2c exact 50-gram overlap; 2d far-exceeds/low-overlap/quality conjunction; 3 historical Boolean-verdict memory effect; 4a after-task candidate selection and commit; 4b controlled frozen benefit. The separate explicit same-run reuse check must not replace check 3.

## Final append only

Write the completed section to `runs/round3/Round3.md` and append its exact bytes to the proof report. Preserve the current 2,222,983-byte prefix, SHA-256 `1cb77b132ee3317753888f258fbba8e576e7e5baf38011dcd1de482fd033d94f`, and original pre-Round-3 2,207,879-byte prefix, SHA-256 `cbd76f98200e77723ccf8ba5cfb1b396875637253722fe68558985916c747f27`. Do not append this preparation file or placeholder outcomes.
