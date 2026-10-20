# Owned process cleanup race

Base: 42424491009371cc7063c2a88394e92c97e974a7. Worktree: runs/round3/worktrees/process-cleanup. Production scope: archive.py only; dedicated regression tests: test_process_cleanup.py.

## Diagnosis before implementation

RunContext.run_process installs a Future callback calling stop() and also calls stop() in its exception path. The same unsynchronized finished flag stays false until communicate()/wait() and exception cleanup return. There is no successful-stop state. Two threads can signal the same group even after the first kill succeeds, before finished becomes true. The existing exception filter catches only ProcessLookupError; on the observed Darwin path the duplicate returns PermissionError.

Independent reviewer disk evidence: main runs/round3/cohorts/context_refiner_v1/saved_refine_local_cancel_probe.json, archived source SHA256 072c6652bb649314e0019e0c59ad2c3f322d1f6049d73e5d5f6732b19e453caf. Three instrumented local Python processes show timeout thread successful killpg, then Future callback getpgid ESRCH and killpg EPERM. This local traceback establishes a cleanup race. The actual saved refinement replay's EPERM lacked a full traceback, so this is not a claim that every replay error has been conclusively localized.

Baseline before source edits: 18 archive/scoped-backend tests passed in 0.61s (baseline.log). New tests initially showed 4 failures/5 passes for concurrent serialization (red.log). The assertion was then made less implementation-specific: require exactly one real owned-group signal, with no duplicate callback error. The final pre-product run has 4 failures/5 passes in 0.44s, each recording two signals instead of one (red_count.log). Both logs are retained.

The first group signal really kills an owned local Python process blocked in signal.pause(). Event synchronization holds the signal wrapper open while Future cancellation enters. Only an erroneous second invocation returns the exact observed EPERM to make the outcome deterministic across OS timing. Two variants exercise wait/communicate; two distinguish success from benign ESRCH. No model, fetch, network, installed package, shared harness, production lock or live process is involved.

## Bounded correction to implement

Serialize finished/stopped checks and signaling with one local threading.Lock. A successful group/process kill or ProcessLookupError marks stopped. Later cancellation/timeout callbacks skip an already stopped child; the completion path writes finished under the same lock. Genuine first PermissionError remains raised/logged under the existing policy, never converted to successful cancellation or blanket-suppressed. No new poll loop, timeout, budget, retry, callback-error policy or process-group target is introduced.

A reaped group leader is not proof its group disappeared: descendants may still hold captured pipes. Preserve group cleanup independently of leader returncode and drain through existing communicate()/wait(). The test reaps a forked leader before timeout while a descendant retains stdout, then proves real group kill releases the pipe and a separate live group survives. Late cancellation after completed run must not signal again. A genuinely denied first signal cannot be claimed successfully drained; tests preserve the PermissionError and clean their fixture explicitly afterward.

## Implemented change and focused verification

The implementation matches the bounded correction above: one local threading.Lock, finished and stopped state under that lock, and stopped=True only after successful signal/benign ProcessLookupError. Other exceptions still propagate. There is no returncode/poll shortcut: the live-descendant regression passes with the leader already reaped. Existing communicate()/wait() draining and exception ordering remain unchanged.

Focused command:

```
/Users/mukeshreddypochamreddy/Desktop/loop-research/.venv/bin/python -m pytest -q \
  tests/test_process_cleanup.py tests/test_archive.py tests/test_codex_scope.py \
  tests/test_codex_backend.py tests/test_refine_context.py
```

Result: 67 passed in 11.71 seconds (focused_green.log), with the existing live/network guards and isolated TMPDIR. No benchmark fixtures were needed and none were copied or edited. git diff --check passed. The parent owns one final integrated whole-suite run; this branch does not duplicate it.

The tests prove the reproduced duplicate cleanup race is prevented, preserve ordinary timeout/cancellation and successful completion, preserve group cleanup after leader exit, and retain genuine first-denial visibility. They do not claim every possible operating-system cleanup failure can be recovered or every original replay error has been conclusively localized. Existing Future callback failure reporting remains Python logging; there is no new promise that such an error is synchronously returned to the cancellation caller. A denied cleanup is not falsely reported as a successful drain.

Independent review completed with no blocking finding. The reviewer ran all nine new tests: 9 passed in 0.89 seconds (tool receipt 059142). The exact original three timer probes each recorded one owned group signal, retained TimeoutExpired, and emitted no callback exception logs. A separate deterministic cancellation after actual communicate return but before wrapper return produced a benign ESRCH that the existing handler caught, then CancelledError; no EPERM. Source SHA256 b66c43f0348ad0868774dcd9548473002c9e23ff50de592ef4384aca86018b0c was verified against this worktree. Parent-owned probe receipts remain at main runs/round3/process_cleanup_fetch_probe.json and process_cleanup_completion_gap_probe.json. This commit contains only the owned source/test and original local evidence; it does not copy or alter parent reporting files.

The successful-completion gap check does not establish a universal PID-reuse guarantee. No new process-group selection or operating-system ownership mechanism was introduced. The correction is specifically one successful termination and synchronized cleanup state for timeout/cancellation convergence, with the original group target and error semantics retained. Raw pytest logs are preserved byte-for-byte, including their original trailing whitespace.
