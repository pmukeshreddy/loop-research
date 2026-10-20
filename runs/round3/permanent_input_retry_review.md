# Independent permanent input retry review

Reviewer: `fetch_review`. Reviewed at 2026-10-20T04:14:52.527045+00:00. Base `e9b1dcd9d2e1a81e8d37ba09cdc028a6dd49feed`; reviewed commit `e6f1cdb1665769174248e6ff46f14c1cfacb223d`, clean isolated worktree `runs/round3/worktrees/permanent-input`.

No important defect found. This narrow patch raises the existing error after one archived failed attempt when trusted provider metadata explicitly identifies JSON-RPC `-32602` and `data.input_error_code=input_too_large`. It does not guess from descriptive text, payload length, model output, or web content.

The CLI string parser requires a complete anchored `turn/start` error envelope with valid JSON data (backend lines 24–46), and stderr is considered only for a nonzero process exit (280–281). Structured metadata is considered only on top-level `error` or `turn.failed` events (311–314). Final replies and ordinary model/web items are excluded.

The new raise follows the durable completion archive, trace, thread-local usage/actions, and callback (332–348), inside the existing slot `finally` (349–350). It bypasses retry events/backoff and further reservations without losing the first reservation or attempt. The one-slot positive tests establish actual release rather than admission into a different free slot. Capacity, unknown codes and malformed data retain existing retry/accounting behavior. Model/web content, quoted stderr and a successful answer containing the exact provider error text remain unaffected.

Independent offline verification from this worktree: **73 passed in 5.39s**, running the new permanent-input tests plus existing backend, FIFO and baseline suites. Tool output receipt `994f60`, exit 0; no separate raw log file was retained. The existing autouse guard blocks live model/direct HTTP calls and isolates slot locks. An additional 10-case in-memory classifier check passed (tool receipt `2d4d7b`, exit 0), including wrong/string RPC codes, malformed JSON, unknown metadata, quoted/prefixed lines and message-only lookalikes. The full command and cases are recorded in the companion JSON.

Exact reviewed SHA-256:

- `src/loop_research/codex_backend.py`: `0e27bcb9effd44f111d6117055127c17b80e47d3126dcf60547e4dc7b5f06841`
- `tests/test_codex_permanent_input.py`: `59d7a65437e3ddf8489e3987fb918e496a9c1296b024512b6313e3f1e98557b3`

The production diff has no task/site/model-specific condition, budget, timeout, retry-delay, concurrency or prompt change. It adds no truncation; the preexisting archive error-tail policy is unchanged. It only avoids futile redispatch of explicitly rejected immutable input. Unknown future CLI envelopes still take the old retry path; the separate lossless codec change must address payload size. No product edits, installs, live models, web calls, commits or live-success claims were made by this review.
