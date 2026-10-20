# Independent review of failed saved preflight

Reviewer `fetch_review`; source `42424491009371cc7063c2a88394e92c97e974a7`; reviewed 2026-10-20T08:45:32.572071+00:00. This is a preserved **failed preflight**, not a successful overflow demonstration or live comparison. The companion JSON contains exact identities, every call's error/timing, schemas, decisions, references and evidence hashes.

| Saved case | Outcome | Model attempts | Failed attempts | Retries | Python workers | Prompt characters per attempt | Edits / decisions |
|---|---|---:|---:|---:|---:|---:|---:|
| A_distinct_pages_midtask | failed | 1 | 1 | 0 | 1 | 4,926 | 0 / 0 |
| A_full_pages_finalizer | complete | 2 | 1 | 1 | 0 | 855,991 | 2 / 5 |
| B1_finalizer | complete | 2 | 1 | 1 | 0 | 690,910 | 2 / 4 |
| B1_fragments_finalizer | complete | 2 | 1 | 1 | 0 | 757,559 | 2 / 4 |
| SI_midtask | complete | 2 | 1 | 1 | 0 | 52,954 | 1 / 3 |

All nine actual attempts used purpose `refine`, configured model `gpt-6-astra`, and no web actions. Totals: four successful attempts, five failed attempts, four retries, one isolated Python worker. No research-root/sub, search or fetch calls were dispatched by these replays; historical calls embedded in input are evidence. Actual prompts were below 1,048,576 characters. The overflow case's prospective 1,611,089-character legacy prompt was never dispatched.

All four direct initial attempts reached their configured 600-second active timeout with empty response and unavailable usage. Retained diagnostics include DNS failure around 06:22:32 UTC and connection resets. Each later succeeded on one retry with identical prompt/schema. These failures and retries remain counted. Overflow has a separate permission error and aggregate deadline failure, with no proposal.

## Identity, schema and returned decisions

Independently reread and hashed 1,159 prepared original-file records (141,262,196 bytes, not a unique-file count), with no mismatch. An earlier check verified all 31 installed modules against frozen source. Every original logical input matches its archived plain/shared-text representation. Actual direct `transport/*/stdin.txt` prompts decode to the entire original logical input, removing only the generated evidence index for comparison; schemas and hashes match. Overflow `context.json` equals the complete original plus that index. All anchors/enums match independently derived anchors.

`B1_finalizer` and `SI_midtask` use the authorized historical pre-anchor schema restriction: three restrictive additions, complete original/current schemas and hashes retained, final proposal valid against both. The other three retain exact original schemas. The two legacy schemas are not mislabeled byte-identical replays.

All 16 returned decisions and every cited pointer were independently checked: exactly one decision per presented/additional candidate, valid finite anchors, accepted-edit links, no orphan edits, and original/current strict schemas. All seven edit texts and decision reasons were read; they describe general procedures without fixed answers, URL/domain lists or product-code edits. This diagnostic does not certify every narrative assertion across the entire historical trajectories. In particular, B1 advice conditioned on model-rendered fetching does not validate summary/focus refetching for today's direct full-page path. These edits reside only in replay clones.

## Overflow initialization, admission and timing

The worker **initialized and loaded its complete input**. Trace records spawn at 05:15:05.759953 UTC; action 1 records `snapshot.read` at 05:15:06.129422; action 2 records its initial planner request at 05:15:06.173879. Loaded context: 3,027,914 characters, SHA-256 `2c9dd4b6c0a8aac815b784af57ca5501bbdd20fd3664d0b96204565c8499c663`; schema SHA-256 `4f3b234f6027ef98c081e384dd786732e0e9d8fc1a334ac213aa33e306811892`.

Four direct cases occupied all four backend slots. Overflow was admitted at 07:53:03.706798, **46.005 ms** after SI's first attempt ended at 07:53:03.660793 and before SI retried at 07:53:05.573412. This compares SI trace `exec.end` with overflow trace `exec.start`; slot release itself is not timestamped. The ~46 ms interval is consistent with FIFO prompt admission, not starvation by newer retries. The harness launched five cases against four slots while overflow's aggregate 600-second deadline included queue time. Approximately two active seconds remained at admission. Its one 4,926-character coordinator prompt produced no response; there were no code blocks, subcalls or proposal. The empty worker log is not evidence of initialization failure.

Planning consumed 9481.263323 wall seconds between trace start/end versus 601.200862 archived monotonic seconds, a 8880.062461-second difference. `host_sleep_wake.log:1` records Clamshell Sleep at `2026-10-20 01:15:19 -0400`, or **05:15:19 UTC**. Intervening maintenance/dark wakes and user/lid wake at 08:26:29 UTC appear in the raw log (user wake line 382). Sleep is confirmed, and wall time is not active planner time. Sleep alone does not establish EPERM's cause.

## EPERM: independently reproduced cleanup race

The archived `PermissionError: [Errno 1] Operation not permitted` belongs to host `RecordingContext.run_process` for Codex transport `001`, after worker initialization. Worker transport `000` records its timeout, normalized to the aggregate deadline error. The Codex receipt has no stack trace; spawn, communication and secondary cleanup cannot be distinguished for that attempt. This review does not claim an exact reconstructed stack or attribute its EPERM solely to sleep.

Six local Python subprocess probes using unchanged `RunContext.run_process` produced one Future callback EPERM at `archive.py:114` (tool receipt `b4b004`; five caller `TimeoutExpired` outcomes and one `CancelledError`). Three instrumented follow-ups reproduced duplicate cleanup in all three: main timeout successfully signals the group, cancellation enters before `finished` is set, `getpgid` reports no process, and the second `killpg` returns EPERM. Full events and stacks are preserved in `saved_refine_local_cancel_probe.json` (tool receipt `cebc95`). Archive source SHA-256: `072c6652bb649314e0019e0c59ad2c3f322d1f6049d73e5d5f6732b19e453caf`.

No model, network, sleep or source edit was involved in these probes. They prove an independent local cleanup issue. Observed probe EPERM is callback-side and logged by Future; all three instrumented callers still raised `TimeoutExpired`, so the replay's caller-side PermissionError throw order remains unproven. Source inspection permits a secondary cleanup exception to mask the primary error, but the original archive cannot prove this branch. Findings and full probe evidence were sent to the parent and implementation agent before further live work.

All failed attempts and receipts remain intact. Exact snapshot availability is verified; successful overflow inspection/use and semantic output quality remain unestablished. No research readiness claim follows from this cohort.
