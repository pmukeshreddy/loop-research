# Six-control comparison audit

`control_audit.py` is a standalone, standard-library, disk-only reader. It imports no product modules and performs no research, network fetches, harness mutations, or model calls. Git commands only read committed snapshots and ancestry. It has **not** been run against any research cohort during preparation.

After the final cohort's six controls complete, run:

```sh
.venv/bin/python runs/round3/control_audit.py \
  --directory runs/round3/cohorts/final \
  --output-dir runs/round3/cohorts/final/control_comparison
```

The helper takes source commit, BASE, POST_A, task, configuration, archive paths, and source/module records from that directory's `plan.json` and `execution.json`. `--expected-source SHA` is an optional extra assertion. The only fixed experiment identities are the six control labels `B0-1..3` and `B1-frozen-1..3`. No task, site, date, lesson, source SHA, or baseline SHA is embedded in the helper.

Without `--output-dir`, the report is JSON on stdout. An explicit output directory must be new or empty and outside all six control workspaces; the helper refuses to overwrite an earlier report. It writes `control_audit.json` and six full `*.initial_backend_input.txt` files. Exit status is zero only when all gates pass; a failed gate emits structured error JSON to stderr and exits one. It does not write success reports for partial/failed audits.

## Evidence checked

- Every arm must be complete, exit zero, have no durable error, record no learning, use its expected BASE or POST_A with `--trace`, and certify unchanged source on completion. Task/config/archive identities must match the frozen plan. The complete archive file inventory is checked for file additions, omissions, content changes, and duplicate paths.
- Every recorded product Python module is matched to its bytes in the source commit, current working source, and installed noneditable package. Module inventories, installed paths, frozen files, source commit ancestry, and hashes/byte counts are checked. The report retains each module verification result. No source SHA is hardcoded.
- `INSTRUCTION` and `FETCH_PATH` are read as literal constants from the committed source with Python AST parsing; the source is never executed. The actual initial backend input is `INSTRUCTION + first root trajectory prompt`. Its SHA-256, Unicode character count, configured model, call identity, and attempt sequence must agree with the earliest durable dispatch record, completion log, and `exec.start`/`exec.end` trace. Initial retries are checked through the first success; response size and full logged text, when present, must also agree. A hidden earlier root call is rejected. The report includes instruction and full prompt hashes, character/byte counts, and archive line references.
- Saved context and root context must be byte-equivalent UTF-8, with no universal-newline normalization. The task/spec/date header must agree with the archived task and date provenance. The saved context must occur exactly once in the actual initial root prompt. True context length must remain correct in `prompt_metadata.json` and the root trace.
- Only the complete JSON array after `RELEVANT HARNESS` in the context and the complete array after `CURRENT RELEVANT HARNESS ENTRIES` in the first root input are replaced for the cross-base comparison. Every other character, including backend instruction, system framing, tools, task, date, and trailing framing, remains compared. Nothing is truncated or summarized. Each retrieved entry must equal its complete object at the selected harness base, including body, module, evidence, version, timestamps, provenance, usage, and outcomes. Initial and current arrays must agree; duplicates and current-run metadata are rejected.
- The three B0 full backend inputs must match exactly, and the three frozen full inputs must match exactly. Across all six, the normalized full inputs must match exactly. The report includes both complete entry arrays for every arm and complete changed values across bases.
- Date policy, resolved date, task-date override, and provenance must be internally valid and identical across controls. Config, task, agent result, and prompt date are checked. `today` is checked against its archived resolved date, never against the audit machine's current date.
- Each harness must be a full independent clone, with no alternates, shallow history, or hardlinked object files. Initial state bytes must match the baseline receipt. Final state must descend from that baseline. No entry procedure fields may change, and no edit history is allowed even if an edit was later rolled back. Refinement dispatch/completion and apply/edit trace events are rejected.
- Historical usage/outcomes must remain verbatim in final storage. New bookkeeping must belong to the current run; the durable usage journal and final entry/top-level usage/outcomes must agree with the consumed entries and saved self-check. Full per-run bookkeeping differences and full BASE-to-POST_A state differences are retained in the report. Storage-level `seen`, usage and outcomes are distinguished from complete historical metadata inside the allowed entry intervention.
- Every fetch request and telemetry record must declare the fetch path extracted from the frozen source, with matching request IDs, and no model fetch call may appear. This identifies the **new direct readable fetch path**, while the separate full fetch-receipt/content audit remains necessary.

Three repeats per base are descriptive checks, **not statistical evidence of an effect**. Historical metadata is part of the complete harness-entry intervention. Later prompts may differ because model outputs, code, tool results, and live pages differ. Local dispatch/trace hashes are execution evidence, not a server-side attestation. Old model-rendered fetch runs are not interchangeable with the new fetch transport.

## Offline verification

`test_control_audit.py` creates temporary source repositories, installed-package files, independent real Git harness clones, and six synthetic completed archives. No product code or live backend is used. The suite covers passing complete inputs, metadata preservation, dispatch hashes/lengths/retries, hidden or missing root events, source drift, unexpected archive files, same-base/cross-base differences, dropped entry fields, run-specific usage injection, date policies/provenance/header, newline preservation, refinement dispatches, edit-plus-rollback history, incomplete arms, wrong fetch paths, and safe CLI export.

Command:

```sh
python3 -m unittest discover -s runs/round3 -p test_control_audit.py
```

Logs: `control_audit_red.log` (initial missing helper), `control_audit_newline_red.log` (newline preservation regression), `control_audit_header_red.log` (explicit task/date header gate), and `control_audit_green.log` (final suite). No product files were changed.
