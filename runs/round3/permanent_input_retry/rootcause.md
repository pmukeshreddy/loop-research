# Permanent provider input rejection retry

Base source: `e9b1dcd9d2e1a81e8d37ba09cdc028a6dd49feed`. Isolated worktree: `runs/round3/worktrees/permanent-input`, branch `round3/permanent-input`.

## Observed failure and root cause before implementation

In the superseded `fair_slots_v1` A run `research-0fd1b020f55e4155989dcd8c40c418f1`, finalizer job `b07049d849e54bad8ece2a1237c8606d` submitted the identical 1,592,078-character input on attempts 0–4. Each provider response rejected `turn/start` with JSON-RPC code `-32602`, parsed data `input_error_code=input_too_large`, and limit 1,048,576. Each response had zero reply characters. Trace dispatch/result pairs are 1865/1866, 1868/1869, 1871/1872, 1874/1875, and 1877/1878. The shared prompt SHA-256 is `109048b0a26256192448e141ca917146ef77f19078ea9cf3cf72564f37f36564`.

`CodexBackend.complete()` builds `full` once before its attempt loop. It treats every nonzero process, terminal error, timeout, rate limit, or empty reply as a retryable failure. After archiving dispatch and completion, it constructs `CodexError`, releases the slot, and retries up to the configured limit. It has no classification of a permanent provider input rejection. Repeating unchanged input cannot correct this explicit rejection, but consumes another reservation and another dispatch.

The independent payload-size defect is outside this patch and owned by the codec work. This fix must surface the original failure after one attempt; it must not truncate, modify, or accept rejected input.

## Bounded design

Classify the known permanent input code only from trusted terminal error metadata: a terminal JSON event with JSON-RPC `code=-32602` and object `data.input_error_code=input_too_large`, or the anchored Codex CLI `Error: turn/start: turn/start failed: ... (code -32602), data: {...}` line with parsed JSON data. Ordinary model/web items, final reply content, and casual mentions of the code are not provider errors.

Save the existing complete attempt/error evidence and callback before raising the existing `CodexError`; release the OS slot through the existing `finally`. Preserve configured concurrency, budgets, model, timeout, retry limit, retry delays, and transient/capacity/unknown-error behavior. No changes to codecs, research scheduling, prompts, or harness state.

## Verification record

Before source edits, baseline backend/fairness/baseline tests reported 60 passed and one missing pinned WandR fixture in the new worktree. `baseline.log` preserves this failure. Copying only the saved test dataset exposed its required vendor instruction files; `baseline_fixture_restored.log` preserves that second fixture-path failure. After copying the existing pinned vendor dataset files locally, the failing node passed in `baseline_fixture_complete.log`. No downloads, installs, live models, or network calls occurred.

The new tests exercise the real retry loop, budget, slot locks, callbacks, and durable archives through an offline runner at the subprocess boundary. Before product source edits, `red.log` recorded **3 failed, 9 passed**: the recorded CLI rejection and both structured terminal variants each reserved and archived five attempts instead of one. The failures occurred at the intended durable attempt-count assertion, not during setup.

The first implementation run (`green.log`, a historical filename that is **not** a passing result) reached the expected one-attempt, zero-backoff, matching callback/archive, and preserved-error checks, then exposed a test-only mistake: `Trace` has a `directory`, not a `path`, and is disabled by default. The test helper now enables the real `Trace(ctx.path)` and checks actual `trace.jsonl` events. No product behavior was changed for that correction.

`focused_green.log`: **73 passed in 5.24s**. The slot-release assertion was then strengthened by setting the test capacity to one, so it cannot succeed by acquiring a different free slot. `final_focused_green.log` reran the same suite: **73 passed in 5.48s**, running:

```text
/Users/mukeshreddypochamreddy/Desktop/loop-research/.venv/bin/python -m pytest -q \
  tests/test_codex_permanent_input.py tests/test_codex_backend.py \
  tests/test_codex_slot_fairness.py tests/test_baseline.py
```

All tests run from the isolated worktree, whose pytest configuration puts its own `src` on the import path. The main virtual environment provides only the existing dependencies. The existing autouse fixture forbids live Codex and direct HTTP calls and isolates the slot-lock directory.

## Final change and generalization

`_permanent_input_rejection` accepts the known `input_too_large` code only when it is paired with JSON-RPC `-32602`. A structured `error` or `turn.failed` event supplies the error object; a nonzero CLI process can supply the exact anchored `turn/start` error envelope and parsed JSON data on stderr. Malformed/unknown metadata stays on the existing retry path. The classifier never inspects final responses or ordinary model/web items.

The failure path still writes durable dispatch and completion records, emits `exec.start`/`exec.end`, records the full saved provider error line, sets thread-local usage/actions, and sends the failed attempt callback. It then raises the existing `CodexError` inside the existing slot cleanup scope. There is no retry event, retry sleep, second reservation, or second dispatch for this rejection. Archive formatting and its preexisting error-length policy are unchanged; there is no new truncation.

The three positive tests cover the real saved CLI line and both terminal event types. Four negative terminal cases cover capacity, an unknown input code, a different RPC code, and non-object data; they retain three dispatches and delays of 1 and 2 seconds under a two-retry configuration. Four content cases cover model items, web items, quoted stderr, and unstructured mentions; they retain a transient retry. A successful output containing the rejection text still returns successfully. Existing tests additionally cover timeouts, rate limits, retry caps, failed-then-successful callbacks, cancellation during backoff, FIFO admission, and capacity.

The classification is generic across tasks and purposes, with no URLs, task IDs, payload lengths, or model names in the production rule. It intentionally does not guess whether unknown provider codes are permanent. Future Codex CLI wording changes may require a separately observed envelope; unknown shapes continue to fail visibly with the prior retry policy.

The separate codec work must still prevent the oversized planner request. This patch only avoids futile redispatch if the provider rejects it. The parent owns integration, the fresh full-suite run, saved-input preflight, installation, and live replay; this isolated change has not performed those operations.
