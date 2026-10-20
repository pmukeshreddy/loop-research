# Round 3 item 2 — same-run refinement feedback and retrieval

Implemented in isolated worktree `runs/round3/worktrees/same-run`, branch `round3/same-run`, based on `1752a36`. Commit: `dbe50820166fed1793d74d9c2ced18baa7281c21`. This is offline implementation evidence, not a live research result or proof that a model will spontaneously request refinement. The shared harness and prior research archives were not modified.

## Root cause and archived evidence

Two independent information boundaries prevented same-run reuse.

1. `Session.retrieve()` used only the unchanged question plus JSON spec as its BM25 query. `Harness.search()` discards every entry whose lexical score is zero. Run A committed the generic recovery memory `d8b0266283de48cf91d4ddf431354ade` in commit `4a7b6abf47234f67c89ea977e2e70048e8fda42b`, 731.660464 seconds before worker exit, but all 11 later retrievals returned only the baseline memory. The new body/ID never appeared in a root prompt. Applying the edit therefore did not establish same-run retrieval or behavior change. [Saved analysis](../round2/A.refine_analysis.md:488).
2. `refine.run()` returned only a scheduling acknowledgement. `Refiner.boundary()` returned an empty list both while no plan was ready and after a valid zero-edit plan completed; `Session` discarded that result and supplied only harness retrieval. The explicit diagnostic's plan declined all three candidates and was applied at trace255, yet no root-visible completion or decline existed. That overconstrained proof request then spent 24 pause blocks declaring 985 seconds of sleeps and ended at root turn30. This was an observability gap combined with a defective wait-for-known-completion probe, not a hung planner, a failed application, or evidence that a lesson must be forced. [Completed explicit analysis](../round2/explicit.analysis.md), [visibility analysis](../round2/explicit_refine_status_analysis.md), [prior conditional design](../round2/refinement_status_design.md).

The parent explicitly authorized the generic product change for Round 3. It retains the earlier design's read-only status semantics and additionally supplies status automatically at the already-existing root boundary, avoiding a requirement to spend another turn querying status. Scheduling remains agent-initiated during research; finalization retains its existing behavior.

## Source changes and interfaces

`src/loop_research/refine.py`:

- Adds `Refiner.status()`, reading one atomically saved `refine_state.json` and one immutable Git HEAD. Returns `enabled`, exact `state`, `request_id`, `job_id`, `focus`, complete `proposal` (summary, edits, additional candidates, all decisions and evidence references), `error`, and proven `commits` receipts.
- Each receipt contains `operation_id`, Git `commit`, entry `key`, and `action`. Receipts come from committed `edits/<operation>.json` at the captured HEAD and history, never a working-tree edit file. A planned job may have real commit receipts after an interrupted final status save; its state remains planned until the existing resume/application path settles it.
- Never calls a backend, observation, self-check, resume, boundary, Future.result, or sleep from status. Missing status means idle; corrupt JSON and invalid operation identities fail visibly. Failure/fatal propagation remains intact.
- Adds request/job IDs to successful, resumed, already-applied, and pending scheduling receipts. Does not change when jobs are scheduled or applied.

`src/loop_research/session.py`:

- After existing nonblocking boundary application, appends the latest job's status plus Session `fatal`, then performs retrieval. Idle has no automatic status suffix. Status and retrieval do not require additional model turns.
- Keeps the existing relevance search and its configured limit for prior entries. Also reads full entries from committed `HEAD:harness_state.json` whose edit provenance `evidence` includes this exact research run/task. These current-run entries precede relevant prior entries and are deduplicated by `(kind, id)`. The union can exceed the relevance limit; it does not truncate fields or discard the prior relevance results. Deleted entries are absent from the current committed state.
- Preserves all returned fields, including body, module, usage, outcomes, evidence, version, and refinement identity. Records usage through the existing call; the comparison agent's separately coordinated change can replace that call with its durable deferred-usage helper without changing selection.
- Retrieval trace rows retain ID/title/score and add `current_run`; a zero-overlap current-run entry has score0.0, not fabricated positive relevance.
- Adds strictly zero-argument `refine.status` dispatch. It returns Session `fatal` separately and is permitted in no-learning mode without scheduling anything.

`src/loop_research/agent.py`:

- Only refinement learning policy, tool documentation, and the Remote allowlist changed. Exposes `refine.status()` and explains planning versus completion, legitimate zero edits, ongoing useful research, and finishing when research is complete without polling/sleeping for a new entry.
- Full initial instructions, root history, task text, output validation, immutable base rules, pinned RLM dependency, and date handling remain unchanged by this branch.

Exact appended format when a durable job exists:

```text
<original complete root prompt and history>
CURRENT REFINEMENT STATUS
<one full JSON status object>
CURRENT RELEVANT HARNESS ENTRIES
<one full JSON entries array>
```

The harness marker and its trailing JSON remain unchanged. The parent was notified that `archive_audit.py` also checks whether the entire dynamic suffix begins with the harness marker; its prefix matching and segmentation must accept the optional earlier status marker. That audit integration is outside this branch's assigned files.

## Tests, red/green sequence, and retained evidence

All commands used the existing main `.venv/bin/python`, with `PYTHONPATH=src` and working directory set to the isolated worktree. Pinned local benchmark fixtures were copied into the ignored worktree; `.verification` was linked to existing local verification fixtures. No dependency update, live backend, live research, production refinement, or shared harness edit occurred. Existing offline guards and test assertions were preserved.

| Stage | Command scope | Result | Log |
| --- | --- | --- | --- |
| Baseline before changes | `test_midtask_refine.py test_refine.py test_session.py` | 22 passed, 5.71s | [baseline](same_run_baseline.log) |
| Tests before production changes | `test_refine_feedback.py test_midtask_refine.py` | Expected 8 failures, 4 passes, 7.91s | [red](same_run_red.log) |
| Initial implementation | New and existing focused refinement/session tests | 31 passed, 10.13s | [green](same_run_green.log) |
| Full offline suite | `python -m pytest -q` | 853 passed, 1 live test deselected, 98.26s | [full suite](same_run_full.log) |
| Retained focused evidence | Four focused files, explicit persistent `--basetemp` | 35 passed, 10.58s | [final focused](same_run_final_focused.log) |

The initial failures were absent Refiner.status/dispatch, absent completed-job boundary feedback in actual worker prompts, and omission of a committed zero-overlap lesson from retrieval. There were no production changes before that failing run. Existing behavior tests remained in place.

New regressions cover:

- Idle, planning, planned and applied zero-edit states; complete explicit decline reasons; request/job correlation; status reads that do not change saved JSON, HEAD, pending identity, or planner count.
- Exclusion of an uncommitted operation file, committed receipt identity, read-only restart with learning disabled, blocked background planner, malformed planner output and persistent fatal propagation, strict no-argument dispatch, and no automatic schedule.
- Commit-before-state-save interruption and idempotent resume with no second planner call; discarded state distinct from a completed decline; corrupt JSON and invalid operation identifiers fail visibly.
- Full-field current-run retrieval with genuinely zero lexical overlap, prior relevance preserved, unrelated prior entries excluded, usage/outcome/module metadata retained, and deleted entries removed.
- Actual OS-isolated workers: a mid-task committed generic lesson is retrieved and drives later REPL quotation validation; a legitimate decline is visible and research finishes; a still-planning request does not prevent finishing; no call is scheduled when the agent makes no refinement request. The workers use synthetic offline model completions and trusted fixture evidence; real boundary application, Git commits, RPC, retrieval, citation checking, isolated REPL, and final validation execute.

### Actual isolated commit → retrieval → action

Persistent fixture directory: [edit case](same_run_test_artifacts/test_isolated_worker_uses_boun0/).

- [trace.jsonl:27](same_run_test_artifacts/test_isolated_worker_uses_boun0/runs/unit/trace.jsonl:27): one agent request schedules request `0fe7e30779a945a28f81eb446cdf9b03`, job `6241a0b6af6849c190ad5187d0c40542`.
- [trace.jsonl:54](same_run_test_artifacts/test_isolated_worker_uses_boun0/runs/unit/trace.jsonl:54): existing boundary applies commit `75644ef626c40fe86094e0d9f0443e1a41e48cf1`.
- [trace.jsonl:56](same_run_test_artifacts/test_isolated_worker_uses_boun0/runs/unit/trace.jsonl:56): next retrieval exposes entry `15c22bdbc1a74062bf7ddb35a4ce2010`, title `Validate provenance`, `score: 0.0`, `current_run: true`.
- The second root prompt contains the full entry and completion receipt. Its next REPL block reads that exact entry, confirms its procedure body, validates the quotation against retained extracted evidence, and prints the applied ID plus `quotation_validated: True`. [Complete trajectory](same_run_test_artifacts/test_isolated_worker_uses_boun0/runs/unit/fixture/trajectory.jsonl).
- [trace.jsonl:77](same_run_test_artifacts/test_isolated_worker_uses_boun0/runs/unit/trace.jsonl:77): worker ends successfully after exactly two root blocks. No worker sleep, polling loop, or status query was used. Final output has no uncited cells and no repair.

The scripted offline sub-model transport synchronizes planner completion with a Future timeout solely to make this concurrency regression deterministic while the worker performs its extraction call. This is not a production wait and is not evidence of real-world planning latency or spontaneous model judgment.

### Actual isolated legitimate decline

Persistent fixture directory: [decline case](same_run_test_artifacts/test_isolated_worker_uses_boun1/).

- [trace.jsonl:51](same_run_test_artifacts/test_isolated_worker_uses_boun1/runs/unit/trace.jsonl:51): applied zero-edit proposal, `commits: []`.
- [trace.jsonl:53](same_run_test_artifacts/test_isolated_worker_uses_boun1/runs/unit/trace.jsonl:53): retrieval remains empty; no lesson is manufactured.
- The second root receives the full decline decisions and prints `completed_decline: True`, then submits. [Complete trajectory](same_run_test_artifacts/test_isolated_worker_uses_boun1/runs/unit/fixture/trajectory.jsonl).
- [trace.jsonl:70](same_run_test_artifacts/test_isolated_worker_uses_boun1/runs/unit/trace.jsonl:70): worker ends successfully after exactly two root blocks, without sleeping or status polling.

## Generalization and integration boundaries

Selection depends on committed entry provenance, current run/task identity, and existing relevance search. Feedback depends on durable lifecycle state and immutable committed operation evidence. Neither depends on benchmark names, web sites, known answers, case-specific prompt text, or preseeded lessons. Declines remain valid; learning-disabled restrictions and existing error checks remain enforced. This fix makes evidence available to the model; it does not prove the model will choose to use every retrieved procedure.

The parent owns integration with the page-fetch change, date change, comparison/usage change, and audit segmentation. The new worker tests use fixture evidence and are independent of the page-fetch transport; the older existing worker regression still uses the original scripted fetch backend and may need the already-planned fetcher fixture migration. Parent must preserve deferred usage call sites when merging Session changes and run the integrated full suite. This branch did not edit `harness.py`, `archive_audit.py`, `Round3.md`, or any proof report.

## Parent integration

Integrated after direct-fetch commit `313603d`, retaining the migrated direct-download fixture. The audit's optional status suffix is parsed separately from the complete harness JSON: status characters count as other task instructions and markers as wrappers, with exact total/hash preserved. `same_run_audit_red.log` reproduces the previously unmatched iteration; `same_run_integrated.log` verifies 64 tests across feedback, real isolated mid-task workers, refiner/session and archive audit (12.48s). The whole root input remains present; no status or entry field is truncated. Live explicit evidence remains required and is separate from scripted fixture evidence.
