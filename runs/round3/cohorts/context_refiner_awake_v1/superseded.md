This cohort is **failed and superseded for launch eligibility**. Its frozen product source is `5cd8fcbc3065a49717fd534ab3a804bd99d8090a` (product tree `be983d99019cb018c1b035fa35c8494c07134f47`). No replacement cohort result is asserted here, and no main research was started in this cohort. These saved refinement replays are excluded from A/B research comparisons.

The archived offline gates passed: **1,038 full-suite tests**, one deselected; **59 helper tests**; and **31 installed modules** matched the frozen source. The subsequent five-case saved replay ran from **2026-10-20T08:52:23.577811+00:00** to **2026-10-20T08:53:20.161780+00:00** and failed overall. Passing offline checks remain valid evidence of their scope; they do not make this preflight successful. See [offline verification](offline_verification.json), [installed verification](installed_verification.json), and [execution](saved_refine/execution.json).

| Saved case | Result | Model attempts | Backend input characters | Proposed edits/decisions |
|---|---|---:|---|---:|
| A_distinct_pages_midtask | failed | 3 | 4,926, 57,575, 3,039,692 | 0/0 |
| A_full_pages_finalizer | complete | 1 | 855,991 | 1/5 |
| B1_finalizer | complete | 1 | 690,910 | 2/4 |
| B1_fragments_finalizer | complete | 1 | 757,559 | 1/3 |
| SI_midtask | complete | 1 | 52,954 | 1/4 |

The overflow planner loaded the complete snapshot, then selected code that printed all 77 trajectory records. Its second stdout contained **2,981,867 characters**, entering the next coordinator prompt unchanged. That backend input contained **3,039,692 characters**, exceeding the provider limit of **1,048,576**. The provider rejected it once with `input_too_large` / `-32602`; no retry occurred. The overflow case returned no proposal, edits, or decisions: its three candidate groups (46 occurrences) are **incomplete, not declined**. Four direct cases produced five proposed edits and 16 decisions. Across all five cases there were seven model attempts, six successful and one failed, with no search, fetch, web actions, or research root/sub calls. See [failure diagnosis](overflow_failure.md) and the original [independent review](saved_refine_review.md).

This is a demonstrated limit of the planner transport: externalizing the initial context does not prevent model-selected output or accumulated history from exceeding a later input limit. It is not evidence of lost snapshot data, and this replay reports no timeout, capacity error, or cleanup EPERM. The bounded local power-log inspection found no matched sleep/wake event during the observed cohort window; that negative observation is not proof against every possible host interruption. [Power observation](power_log_observation.json).

All original files remain unchanged. [Archive hashes](superseded_archive_hashes.json) inventory **1,073 file paths / 95,010,317 bytes** present before these five new preservation reports, including raw attempts, streams, requests, results, independent review, and isolated harness histories. This is a path-based inventory, not a unique-content count; it is distinct from the independent review's 1,159 original-file comparison records. [Detailed evidence](overflow_failure.json) includes exact action, code, stdout, prompt, response and raw-transport hashes. No product fix, replay, install, or new research was performed for this preservation task.
