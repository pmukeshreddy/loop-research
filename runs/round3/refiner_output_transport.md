# Whole-iteration refinement feedback transport

## Failure and scope

The awake saved-input replay completed four direct planners. Its overflow planner printed all 77 supplied trajectory records in iteration 2: 2,981,867 stdout characters. The old worker appended the complete formatted output to its transcript, producing a 3,039,692-character backend prompt against the observed 1,048,576-character provider limit. The oversized request failed once; no retry was invented. The first iteration's 51,972 stdout characters had fit normally.

This change is a planner-feedback representation change. Future overflow planner prompts are intentionally not byte-identical to the old prompts: the policy explanation adds 680 instruction characters, and selected whole output messages become explicit references only when the complete next input would overflow. Research root prompts and the small direct refinement path are unchanged. The supplied logical context, entries, observations, candidates, output schema, model selection, call/retry allowances, deadlines and refinement timing policy are unchanged. Losslessness refers to retaining and retrieving complete supplied records and executed iteration output; it does not claim the model sees every output byte inline or that arbitrarily large control transcripts can fit.

## Contract and algorithm

`refine_feedback.py` defines policy `whole-iteration-reference-v1`. `initial_messages(instructions, limits)` constructs the existing two-message initial contract. `feedback_text(blocks)` preserves the existing complete Block/stdout/stderr formatting. `feedback_record(iteration, blocks)` contains the exact formatted feedback and full blocks, including code, stdout, stderr, execution_time, answer_ready, final_answer and derived_stream_failure. The last flag is derived from nonempty stderr, not a separate assertion of execution success. Empty stderr is explicitly not proof of success.

`FeedbackHistory(messages, max_prompt_chars)` retains every model/control message exactly as supplied. `append_response` records the complete model response; `append_output` seals one complete iteration. `read_output(iteration)` returns a fresh deep copy and rejects absent/current/unsealed iterations. The host owns this history; mutable worker locals cannot alter it.

Before a planner dispatch, `prepare()` computes the exact length of INSTRUCTION plus the serialized complete transcript. If it fits, feedback remains byte-identical and inline, including outputs larger than 20,000 characters. On overflow, candidate replacements are whole iteration feedback messages only. Actual complete serialized net savings include receipt text, message wrappers and backend prefix. Nonpositive savings are skipped; positive savings sort by decreasing saving, then increasing iteration number. Replacements stop as soon as the prompt fits. Previously externalized messages remain references; new small inspections stay inline whenever possible.

The reference contains no stream previews, prefixes, suffixes or semantic summaries. It supplies the exact iteration identity, full feedback length/hash, canonical complete-block hash, per-block stdout/stderr lengths/hashes, stderr_present and derived failure/final-ready flags, plus the exact `repl_output(iteration)` retrieval call. The originals remain in immutable host records and the existing code.start/code.end archive actions. If controls plus all profitable references still exceed the limit, preparation raises a visible local error atomically: no history mutation, fabricated dispatch or omitted content.

## Host broker and archive protocol

The worker invokes a no-argument internal `planner` broker. The host prepares the prompt, durably appends each generated `output.externalized` event, invokes only the configured refinement model, and retains the complete response. The ordinary model broker is subcall-only. Neither reference events nor their identity fields are accepted from worker-supplied action metadata.

An externalization event includes iteration, feedback_chars, feedback_sha256, blocks_sha256, exact receipt text/chars/hash, backend_prompt_chars_before, backend_prompt_chars_after and net_saving. A successful `repl_output(iteration)` read generates `output.read` with the same authoritative identity and returns a fresh full record. Hashes use SHA-256 over UTF-8; block identity uses JSON with ensure_ascii=False, sorted keys, compact separators and allow_nan=False. Character counts are Python string lengths, not byte counts.

The host merges code.start/code.end records, then seals output only on iteration.end. Thus subsequent blocks cannot alter an already readable record. Manifest and durable request record output_transport; the request also records exact derived initial_messages. The outer transport remains repl-context-v1 for historical compatibility. Parent owns strict audit integration, including reconstruction of actual model prompts and code/response linkage; existing legacy policy-absent archives retain their old interpretation.

## Validation and saved-input measurement

- RED: 10 failures and 10 existing passes. Seven pure-contract tests could not find the new helper; three real isolated-worker cases reproduced oversized stdout/cumulative output/stderr dispatches.
- First GREEN: 19 passes and one test setup mismatch. The host correctly rejected an unsealed output with ValueError; the pre-existing bridge wraps remote errors as RuntimeError. The test now catches that transport exception and checks the exact rejection message. The original failure log is preserved.
- Broader intermediate focused run: 44 passed.
- Final focused run: 46 passed in 15.42 seconds, covering pure boundaries/ties/nonprofitable savings/atomic failure, actual isolated multi-block >1MB stdout and full hash restoration, code-selected subcall/proposal, cumulative smaller outputs, giant stderr and fresh-copy immutability, rejection of current unsealed output, and an oversized assistant control response failing locally without another model dispatch. Existing >20k stdout/stderr behavior remains tested. Model transports are offline fixtures; the isolated Python worker is real.
- Parent explicitly owns the final integrated full suite; no isolated full-suite result is claimed for this change.

The exact failed archive was reconstructed offline, verifying all original archived prompts before projecting the new policy. With original instructions, independent review measured 58,655 characters for the formerly oversized turn. With the actual new policy instructions (+680), the projected turns are 5,606, 58,255 and 59,335 characters. Only iteration 2 is referenced; iteration 1's complete 51,997-character formatted feedback remains inline. Iteration 2's complete 2,981,892-character formatted feedback and both complete iteration block records restore exactly. Context/schema/archive hashes remain unchanged. This is an offline projection, not a successful live replay; see refiner_output_saved_projection.json.

No installation, live models, web calls, source/harness input edits or main-workspace writes occurred. The commit owns only the two refinement transport modules, their dedicated/context tests and these evidence/spec files.
