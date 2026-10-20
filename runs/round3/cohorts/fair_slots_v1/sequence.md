# Fresh Round 3 replay after fair slot admission

Frozen research source: `dab5cf89963805d20d3d305ba14d8c8611cd8cf4` (product tree `ab81995142f2f27928dfc29e80567045e7497fbb`). Scheduler fix: `cfe361f`. The earlier `cohorts/final` attempt is superseded because the backend let later requests overtake an older waiter until its 600-second slot deadline. Its archives and original predictions remain intact. No old A state, cache, or pending B work is reused here.

The fresh main suite passed 914 tests, with one existing live test deselected, in 111.63 seconds. The 30 installed Python modules exactly match the frozen committed source. The suite ran after the scheduler commit and before the reporting-only `dab5cf8` commit; the recorded product tree and all module hashes are identical. Launcher checks passed 8 tests, explicit launcher checks 4, and control-audit checks 23. The reporting-contract tests and independent FIFO reviews are separately committed or preserved in `runs/round3`.

Three new saved-input refinement replays completed on the frozen source: one backend call each, no errors or retries, and 1/2/2 commits respectively. Six saved archive audits passed. The shared harness was already exactly BASE; the rollback helper recorded no compensating edits and forked exact BASE again. Only then were independent A and SI harness trees prepared and the traced A/SI phase launched. SI keeps its authoritative historical baseline because A/B BASE already marks its unchanged task seen. Configuration and task inputs are byte-identical to the previous attempt and Round 2.

Every Round 3 research measurement uses the new `direct-readable-v1` fetch path. Historical Round 1/2 measurements use model-mediated fetch. No cross-round difference is an isolated causal effect of learning or transport. The next predictions must describe the entries from this fresh A after it finishes, be committed before any B starts, and preserve the old preregistration as superseded evidence.

This is a preparation receipt, not a live outcome or success verdict. A/SI are running; all B runs and the separate explicit diagnostic remain pending. No product or frozen input may change during these runs.
