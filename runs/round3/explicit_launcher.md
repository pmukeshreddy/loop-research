# Explicit diagnostic preparation — not executed

This package prepares the separately requested Round 3 mechanism diagnostic. It is **excluded from spontaneous behavior and all A/B comparisons**. No research, model call, web call, harness clone, rollback, or explicit launch has been performed. The shared harness, main launcher, production source, main phase state, `Round3.md`, and proof reports were not edited by this preparation.

Prepared files:

- [explicit_request.json](explicit_request.json): the complete CLI request and classification.
- [explicit_task.json](explicit_task.json): the exact normal CLI Task serialization, task ID `279b4452911b3d5f1254f337`.
- [run_explicit.py](run_explicit.py): a separately gated one-run launcher reusing `launch.py`.
- [test_explicit_launcher.py](test_explicit_launcher.py): four offline tests for gates, durable refusal, and request identity.

## Why this request differs from the earlier diagnostic

Round 2's explicit request had only two symbol rows and required the root to establish that the planner finished before submission, even though a zero-edit plan had no root-visible completion signal. It encouraged pauses and repeated harness searches. The resulting 24 pause blocks and 985 seconds of declared sleeps were a defect in that proof request as well as evidence of the old visibility limitation. The new request does not carry forward that requirement.

The substantive task now covers five quantities—length, mass, time, electric current, and thermodynamic temperature—and six columns: quantity, unit, symbol, unit_definition, defining_constant, fixed_value. This requires checking 30 cells, exact defining statements, fixed numerical constants, powers of ten, SI unit expressions, citations, and dependencies between units against fetched official NIST or BIPM evidence. It introduces no answer values, source URLs, expected lessons, procedure bodies, or target entry IDs.

The agent must make one explicit mid-task refinement request after observed evidence processing while useful research remains. It chooses the actual timing and observed focus. It then continues the remaining research and uses an actual `rlm_query` child for a bounded evidence-processing or verification subtask, validates the child's cited findings, and uses them in the table or a concrete verification decision. This supplies genuine ongoing work rather than a timing delay.

On a later available root turn, the agent examines the existing automatically delivered status and current relevant entries. If a new committed entry is both retrieved and applicable, it applies that procedure to remaining work and prints compact IDs/action/result diagnostics. A valid zero-edit decline, a still-planning job, absent retrieval, or an inapplicable lesson is reported accurately. None is converted into a successful edit or reuse claim. No sleeping, polling, repeated refinement requests, repeated harness searching, direct harness writes, forced lesson, or manufactured extra research is permitted. Submission depends only on completion of the substantive research. A finalizer-only edit is explicitly excluded from same-run reuse.

The larger task improves the opportunity for a real plan to finish during useful work. It does **not** guarantee a qualifying edit, retrieval, or reuse demonstration. A valid decline or timing miss remains an honest result. The eventual auditor must join scheduling, commit, later retrieval exposure, subsequent action, and worker exit; the request's diagnostic claim alone is insufficient.

## Parent execution, only after the main B phase

Review the request and helper first. Once the main cohort is durably complete, the parent may run:

```sh
.venv/bin/python runs/round3/run_explicit.py check
.venv/bin/python runs/round3/run_explicit.py run
```

The `check` operation validates inputs and gates without cloning or starting research; `status` reads only saved explicit state. Both are separate from the explicit `run` operation. Do not use `run` as a speculative readiness probe: every `run` attempt creates a durable `explicit_execution.json`, including refusals, and a later attempt cannot overwrite it. Diagnose a refusal before deciding how to proceed.

The gate requires:

- Main `execution.json` source identity matches the frozen main plan.
- A/SI and B phases both have `status: complete`.
- Every arm listed in the main plan is present, marked complete, has exit code zero, has the same source identity, and has a complete durable research record without an error. Thus exit zero alone is insufficient.
- `launch.unchanged()` verifies the unchanged source/installed package, original preflight and rollback receipts, config, dependencies, helpers, and existing frozen artifacts. The helper requires the main virtual environment.
- The explicit request is classified correctly, starts from exact BASE `2a423027212fe1c430dfd200bdd55f3a27b22d70`, and reproduces the saved task by the same `digest({question, columns, keys, language})[:24]` and Task model used by `stream.research`. No explicit task date is injected; the inherited unchanged config still governs date policy.

The launcher additionally freezes its own bytes, explicit request/task, completed main plan/execution state, and completed B process record. It uses the existing cohort lock, so it cannot launch concurrently through the main coordinator's lock. These new frozen records are checked again immediately before process start and during durable completion validation.

Only the parent `run` operation creates `workspaces/explicit-BASE`, using the existing full `clone_harness` implementation with `--no-hardlinks --no-local --no-checkout`, followed by exact BASE checkout. The shared harness is a clone source only. The new workspace has independent Git objects, harness working tree, runs, reports, and cache; each task also has its own `tool_cache.json`. It does not reuse POST_A or a main-arm workspace. The CLI command uses the existing installed public CLI, unchanged config, the full explicit request, learning enabled, `--trace`, and `--base BASE`.

Execution uses `process_group(max_parallel=1)` and the existing `validate_completion()` machinery, including the exact CLI archive-ownership announcement, complete file inventory, exit and durable status, task/run/base/learning/config identities, date provenance, source hashes, and task-error check. It creates separately named `explicit_execution.json`, `explicit.processes.json`, `explicit.console.log`, and `explicit.archive_hashes.json`. Errors and interruptions are retained; there is no automatic retry or rollback. A process with exit zero and a durable research error remains failed. An interrupted coordinator preserves owned process IDs rather than issuing a new attempt.

## Offline verification

The four new tests failed before the launcher existed: [red log](explicit_launcher_red.log). After implementation all four pass: [green log](explicit_launcher_green.log). They use temporary JSON files and do not invoke cloning or research. They check incomplete/missing main arms, incomplete B, mismatched source, durable errors despite exit zero, persistent failed-attempt state, refusal to overwrite that state, no workspace creation on refusal, and exact saved CLI task identity/classification.

The new tests plus two existing process/validation tests pass together, six tests total: [shared machinery checks](explicit_launcher_shared_checks_green.log). Those existing tests run only short synthetic Python processes, exercising failure stopping queued starts while an already-owned sibling completes and exit-zero durable-error handling with retained archive hashes. No clone test was executed. `py_compile` succeeds for both new Python files.

An initial attempt to invoke these tests by the namespace `runs.round3` failed at import because `runs` is not an importable project test package; no test body or launch ran. That command failure is retained in [shared-check invocation log](explicit_launcher_shared_checks.log). The corrected invocation ran from `runs/round3` with the main virtual-environment Python and passed.

At handoff, `explicit_execution.json`, `explicit.processes.json`, `explicit.console.log`, and `workspaces/explicit-BASE` do not exist. The main cohort's progress was neither inspected beyond local configuration/source preparation reads nor advanced by this helper preparation.
