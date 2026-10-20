# Superseded cohort: final refinement input limit

Research source `dab5cf89963805d20d3d305ba14d8c8611cd8cf4`. A worker submitted its table and exited at trace1854, but final refinement made five identical failed attempts (0–4), each rejected because the exact backend prompt was 1,592,078 characters against a 1,048,576-character provider limit. Schema size is separate. Research ends failed at trace1883; A is not a successful completed research run. SI completed, but this cohort cannot supply the final comparison after the required general planner-input fix. All affected A/SI work will be replayed on that fixed source.

No B run began and no predictions for this cohort were written. The old root-level predictions still belong to the earlier scheduler-failed cohort; no old POST_A is substituted. Actual mid-task commits, later retrieval and matching A actions remain evidence of this superseded attempt only. Keep SI's completed quality review as historical evidence, not the final replay result.

All three owned coordinator/CLI processes have exited; no interruption was needed. The failure receipt and at-rest inventories preserve both archives. The two direct download failures (HTTP403 and TLS certificate verification) are retained separately from the five deterministic planner-input failures and four retries. There was no model-mediated fetch fallback.
