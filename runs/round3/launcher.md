# Round 3 launcher handoff

Prepared helper only. No research, refinement, model or web call was started; no `prepare` or `run` command was executed and no shared harness checkout/rollback was performed.

Files are confined to `runs/round3`: `launch.py`, `test_launch.py`, this note, `launcher_red.log`, `launcher_green.log`, and `inputs/{config.json,A.task.json,SI.task.json,B.task.json}`. Configuration and requests are exact copies from the authoritative Round 2 manifest/archives. No lesson text or harness entries are synthesized.

## Parent receipts before preparation

Use the final code commit SHA after all fixes and verification. Save `preflight.json` with this structure (evidence records must identify real immutable files):

```json
{
  "source_commit": "<full fixed code commit>",
  "all_fixes_complete": true,
  "full_suite": {
    "exit_code": 0,
    "passed": 1,
    "evidence": {"path": "<absolute suite log>", "bytes": 123, "sha256": "<digest>"}
  },
  "saved_refine": {
    "status": "passed",
    "evidence": {"path": "<absolute completed saved-refine result>", "bytes": 123, "sha256": "<digest>"}
  },
  "archive_audit": {
    "status": "passed",
    "evidence": {"path": "<absolute completed audit result>", "bytes": 123, "sha256": "<digest>"}
  }
}
```

`passed` is the actual full-suite test count. Each evidence object must exactly match `file_record(Path(path))` from the helper. The receipt certifies these checks on the single stated source commit; the launcher does not rerun tests or audits.

After the parent performs the authorized rollback, save `rollback.json`:

```json
{
  "source_commit": "<same full fixed code commit>",
  "base_sha": "2a423027212fe1c430dfd200bdd55f3a27b22d70",
  "harness_head": "2a423027212fe1c430dfd200bdd55f3a27b22d70",
  "completed_at": "<ISO UTC timestamp>"
}
```

Preparation checks the shared harness's actual HEAD and clean worktree against this receipt. It does not perform the rollback itself.

## Explicit phases

Run with the main virtual environment so installed-package verification covers the actual CLI runtime:

```sh
.venv/bin/python runs/round3/launch.py prepare --source <fixed-code-commit>
.venv/bin/python runs/round3/launch.py run --phase a_si
```

Preparation verifies receipts and inputs, confirms the installed noneditable package matches committed source bytes, freezes source/config/helper/evidence hashes, and makes independent A and SI workspaces. It starts no research. A starts from BASE and SI retains its exact recorded Round 2 baseline (validated against task history); both use the same exact Round 2 configuration (including `as_of=2026-10-18`, all four roles `gpt-6-astra`), and use `--trace` with learning enabled. A/SI run together with at most two owned processes.

After successful A/SI completion, `execution.json` records `POST_A`. Parent writes predictions and commits them before B. The committed predictions file must contain these two exact standalone lines (the surrounding prose is owned by the parent):

```text
source_commit: <fixed-code-commit>
POST_A: <A's exact completed harness_head>
```

Then:

```sh
.venv/bin/python runs/round3/launch.py run --phase b \
  --predictions <tracked-predictions-file> --predictions-commit <commit-containing-predictions>
```

B refuses to start unless A/SI and A succeeded, the working prediction file exactly matches `git show`, the commit is a descendant of the fixed source and an ancestor of HEAD, its timestamp is not before A completion, and the exact source/POST_A bindings match. Documentation-only commits are allowed while all original source and installed module bytes remain frozen.

B prepares all seven independent harness clones before starting any B process. Start order is `B1`, `B1-frozen-1`, `B0-1`, `B1-frozen-2`, `B0-2`, `B1-frozen-3`, `B0-3`, with at most three live research processes. B1 learns from POST_A. All frozen arms use POST_A plus `--no-learning`; B0 replicates use BASE plus `--no-learning`. Every command includes `--trace`.

Each workspace uses its own full `git clone --no-hardlinks --no-local`, Git objects, harness working tree, runs, reports and cache directories. The backend's existing global four-call slot mechanism remains shared. No source copies, shared task caches, worktrees, alternates, seeded lessons or automatic retries are used.

## Observation and failure behavior

```sh
.venv/bin/python runs/round3/launch.py status
```

`plan.json` contains source/module hashes, frozen input records and preparation provenance. `execution.json` contains phase status and final per-arm metadata. During execution, `a_si.processes.json` or `b.processes.json` is updated for every process transition. `<label>.console.log` retains the public CLI output and its exact trace ownership announcement. `<label>.archive_hashes.json` inventories all files owned by the completed run. Commands, PIDs, start/end timestamps, exit codes, archive identities and errors are retained. `launcher_events.jsonl` preserves requested commands and gate failures.

Archive ownership uses the previously tested Round 2 announcement parser; the helper never guesses by scanning unrelated directories. Completion additionally verifies run/task/base/learning/config identity, exact task content, date/provenance, complete durable state and source hashes. Exit zero with a durable research error is still failure.

Any observed nonzero exit, invalid durable completion, failed clone or changed source prevents further queued starts. Already running sibling processes finish naturally; the launcher does not kill unrelated or completed processes. Coordinator interruption records owned PIDs left running. An attempted or failed phase cannot be rerun automatically in the same cohort. Parent diagnoses any failure before choosing further work.

## Offline verification

`python3 runs/round3/test_launch.py` executes six tests with temporary synthetic Git repositories and subprocesses: exact-source receipts/evidence hashes, independent full clone/base integrity, successful-A plus committed prediction binding, failure stopping new starts while a sibling completes, the maximum three-process cap, and exit-zero durable research errors blocking subsequent starts. Red evidence was recorded before implementation; all six pass in `launcher_green.log`. These are standalone helper tests; they do not run any product research and must not be run during the live phases.
