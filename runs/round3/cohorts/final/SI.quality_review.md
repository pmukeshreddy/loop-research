# SI saved-output quality and mechanism review

Run `research-1f76e7b0b87045b88fd94aa92bb5ee2d` completes the unchanged five-quantity SI task with **five correct rows, 15 supported cited cells, zero final issues, and zero uncited cells**. The saved NIST documents directly support each quantity/unit/symbol relationship. Direct readable-page fetching, full-text retention in variables, batched stateless extraction, and cache reuse are demonstrated. **Same-run refinement application, later retrieval, and lesson reuse are not demonstrated.**

This review reads only completed SI archives and existing derived audits. No tests, model calls, web calls, production edits, harness changes, or interaction with the live A process were performed. The complete cell checks, hashes, receipt checks, comparisons, and timeline are in [SI.quality_review.json](SI.quality_review.json).

## Output identities and citation support

The archived task is exactly equal to Round 2 SI's task, including task ID `1109eb057f25ad2429b6e77e`, question, columns, keys, and language. Quantity order and all 15 output value strings also equal Round 2 SI. The reference run is `research-0bd4c80fa24c4fd99cfc8d2f6876762d`. This is an identity/value check, not a claim that source text, prompts, harness base, or timing are equivalent between rounds. [Final task](workspaces/SI/runs/research-1f76e7b0b87045b88fd94aa92bb5ee2d/1109eb057f25ad2429b6e77e/task.json), [final output](workspaces/SI/runs/research-1f76e7b0b87045b88fd94aa92bb5ee2d/1109eb057f25ad2429b6e77e/output.json), [Round 2 output](../../../research-0bd4c80fa24c4fd99cfc8d2f6876762d/1109eb057f25ad2429b6e77e/output.json).

| Quantity | Unit | Symbol | Verbatim support, reused across the row's three cells |
| --- | --- | --- | --- |
| length | meter | m | `Length - meter (m)` |
| mass | kilogram | kg | `Mass - kilogram (kg)` |
| time | second | s | `Time - second (s)` |
| electric current | ampere | A | `electric current` / `I, i` / `ampere` / `A`, on consecutive lines |
| thermodynamic temperature | kelvin | K | `thermodynamic temperature` / `T` / `kelvin` / `K`, on consecutive lines |

The first three quotes occur in NIST's SI Units page directly beneath “The seven SI base units, which are comprised of”. The latter two quotes are contiguous rows in “Table 2. SI base units” in NIST SP 330 Section 2. That table explicitly distinguishes the quantity's symbol from the unit's symbol, so `I, i` and `T` are not being mistaken for `A` and `K`. All source hosts are `www.nist.gov`; every nonempty quote is an exact substring of a saved successful fetched-text version. The JSON review retains each cell, source URL, matching version index, and surrounding table/list context. [SI Units downloaded text](workspaces/SI/runs/research-1f76e7b0b87045b88fd94aa92bb5ee2d/1109eb057f25ad2429b6e77e/downloads/01c2351e063142ff9102e7ecaca094b0.txt), [SP 330 downloaded text](workspaces/SI/runs/research-1f76e7b0b87045b88fd94aa92bb5ee2d/1109eb057f25ad2429b6e77e/downloads/297d8dbb1ab74440a53906c4a0523c09.txt).

Mechanical results agree with this specific semantic review: `self_check.ok=true`, no issues, no uncited cells, no agent/runtime errors, no output repair, and no retries. All 35 archived citation records are fetched and verbatim: 15 output cells plus 20 constraint-check citations. All 20 actual constraint calls pass Boolean `True`, covering the question and three columns for each of five rows. The two retained `stalled_search` signals are not hidden: the two required demonstration batch searches recorded no new entities after the first search discovered the five requested quantities. Their returned pages were subsequently fetched and used. [Self-check](workspaces/SI/runs/research-1f76e7b0b87045b88fd94aa92bb5ee2d/1109eb057f25ad2429b6e77e/self_check.json), [agent result](workspaces/SI/runs/research-1f76e7b0b87045b88fd94aa92bb5ee2d/1109eb057f25ad2429b6e77e/agent_result.json), [metrics](audits/SI.metrics.json).

## Direct fetch and actual processing path

Three unique static HTML downloads all returned HTTP 200 through `direct-readable-v1` and parser `stdlib-html-readable-v1`. Their saved raw-byte SHA-256, raw byte counts, readable-text SHA-256, and readable character counts independently match their receipts. The readable files also equal the successful host evidence versions.

| NIST page | Raw bytes | Decoded raw characters | Returned readable characters |
| --- | ---: | ---: | ---: |
| Definitions of SI Base Units | 91,293 | 91,204 | 6,619 |
| SI Units | 121,690 | 121,652 | 13,200 |
| SP 330 Section 2 | 149,896 | 149,380 | 44,922 |
| Unique total | **362,879** | **362,236** | **64,741** |

The readable-text count is distinct from raw HTML size. It includes static document text and the relevant list/table, rather than a model-rendered excerpt. The receipt records make this distinction observable. This is positive evidence for these three NIST HTML pages, including the longer SP 330 page. This run alone does not establish generalization across domains, PDFs, dynamic JavaScript pages, or every document format. [Fetch telemetry](workspaces/SI/runs/research-1f76e7b0b87045b88fd94aa92bb5ee2d/1109eb057f25ad2429b6e77e/fetch_telemetry.json).

The actual operation chain is visible in the root code, trace, and archived locals:

1. Root turn 2 performs one single search and one two-query `search_many`. Their trace spans are lines61–66 and73–86. The single search returns five hits; each batch query returns four. The batch requests overlap in time. Discoveries are recorded for all three queries. [Search code, trajectory4](workspaces/SI/runs/research-1f76e7b0b87045b88fd94aa92bb5ee2d/1109eb057f25ad2429b6e77e/trajectory.jsonl:4).
2. Root turn 3 performs one single fetch, one two-URL `fetch_many`, and a repeated fetch of the primary URL with a different focus. The telemetry marks the fourth invocation `source=cache`, `owner_id=1`, with the original receipt and 6,619 characters. Its returned text equals the first fetched text. Trace spans are119–123,126–137, and140–142. The batch downloads overlap. [Fetch/cache code, trajectory11](workspaces/SI/runs/research-1f76e7b0b87045b88fd94aa92bb5ee2d/1109eb057f25ad2429b6e77e/trajectory.jsonl:11).
3. The complete texts are present in `primary_text`, `batch_texts`, `cached_text`, and the URL-keyed `evidence` dictionary in the actual locals snapshot at trajectory16. All three values match host evidence exactly. The same evidence dictionary remains intact at trajectory21 and43. This is value-level evidence, not an inference from variable names. The printed progress contains URLs, lengths, cache equality, and budgets rather than page bodies. [Locals and successful output, trajectory16](workspaces/SI/runs/research-1f76e7b0b87045b88fd94aa92bb5ee2d/1109eb057f25ad2429b6e77e/trajectory.jsonl:16).
4. Root turn 4 makes `llm_query_json_batched` calls for two quantity groups. Both actual sub-model prompts contain the complete JSON serialization of all three fetched texts. Their prompt lengths are66,888 and66,865 characters; schema input contributes1,129 per call, for136,011 combined input characters. Each returns a typed group of rows. These are **two stateless structured subcalls, not child RLM executions**; there is only one RLM identity at depth0. This satisfies the SI request's sub-LM extraction requirement. [Extraction code, trajectory17](workspaces/SI/runs/research-1f76e7b0b87045b88fd94aa92bb5ee2d/1109eb057f25ad2429b6e77e/trajectory.jsonl:17), [sub response1, trajectory19](workspaces/SI/runs/research-1f76e7b0b87045b88fd94aa92bb5ee2d/1109eb057f25ad2429b6e77e/trajectory.jsonl:19), [sub response2, trajectory20](workspaces/SI/runs/research-1f76e7b0b87045b88fd94aa92bb5ee2d/1109eb057f25ad2429b6e77e/trajectory.jsonl:20).
5. Root turn 5 validates quantity coverage, official hosts, exact quotations, and unit/symbol values, records20 constraint checks, validates the output schema, and submits. The saved output equals the extracted rows and the final `your_output` local exactly. Five root iterations and five REPL blocks end with `answer_ready`. [Final code, trajectory22](workspaces/SI/runs/research-1f76e7b0b87045b88fd94aa92bb5ee2d/1109eb057f25ad2429b6e77e/trajectory.jsonl:22), [final execution, trajectory43](workspaces/SI/runs/research-1f76e7b0b87045b88fd94aa92bb5ee2d/1109eb057f25ad2429b6e77e/trajectory.jsonl:43).

The twelve model/backend calls comprise five root, three search, two sub, and two refine calls. Direct fetching consumes no model call here. The task explicitly requested the demonstration's single/batched/cache behavior, so these successful operations do not establish spontaneous selection of those tactics.

## Root prompt size: exact result and limit

The saved largest backend root prompt is **27,946 characters**, matching its archived call size and SHA-256. Unique readable fetched text totals **64,741 characters**:

`64,741 / 27,946 = 2.3166463894653977`, or **2.3166×**.

That is the supported quantitative statement. This review does not describe it as “far exceeds” or infer a large-context stress result. The exact case/whitespace-sensitive50-character-gram audit reports0 covered fetched characters,0% overlap, and0 complete fetched texts in root prompts. This is not a claim of zero shared short words, URLs, summaries, or factual content. Complete page text reaches the stateless sub-models through retained variables. [Overlap and prompt audit](audits/SI.audit.json), [largest root prompt](audits/SI.largest_root_prompt.txt).

The root prompt's27,946 characters partition into system3,146; question/columns470; other task instructions8,114; harness4; earlier code4,495; REPL output10,993; wrappers724. The first REPL block prints the entire8,586-character context, duplicating substantial instruction content in the ensuing root history. This contributes to root size; it is not fetched-page exposure. No history or instructions were removed for this review.

## Refinement timing and absence of same-run reuse

The agent invokes `refine.run` once in the **same final root block that sets `answer["ready"] = True`**. It proposes reviewing the procedure it just executed; no additional root turn remains. The scheduling receipt is in the final locals, but the root has no later prompt in which completion feedback or a new entry could appear.

| Event | Trace line | UTC timestamp | Relative to worker exit |
| --- | ---: | --- | ---: |
| Agent-requested plan scheduled | 287 | 2026-10-20T02:33:40.807224+00:00 | −0.536229s |
| Worker exit, code0 | 301 | 2026-10-20T02:33:41.343453+00:00 | 0 |
| First plan proposal, edits=[] | 310 | 2026-10-20T02:34:38.528266+00:00 | +57.184813s |
| First plan applied, commits=[] | 313 | 2026-10-20T02:34:38.546404+00:00 | +57.202951s |
| First apply span ends | 314 | 2026-10-20T02:34:38.553896+00:00 | +57.210443s |
| Automatic finalizer plan scheduled | 317 | 2026-10-20T02:34:38.582653+00:00 | +57.239200s |
| Finalizer plan applied, commits=[] | 324 | 2026-10-20T02:34:59.314126+00:00 | +77.970673s |
| Research run ends | 327 | 2026-10-20T02:34:59.349949+00:00 | +78.006496s |

The first request is `24e3635699e34d2cb528d7a60663fa7b`, job `42560a304d5a4011933b5b79de37c9fc`. Its three candidates are declined: the mid-block empty-output observation does not prove a finalization failure; the search signals reflect requested demonstration calls; and the successful evidence/cache/extraction procedure duplicates immutable base instructions. The automatic finalizer request `ad74fd62757541428ea1f0e770940043`, job `864b03c23ab541ab9a8ccdbd73ea4f93`, declines its two candidates for corresponding reasons. Both are legitimate zero-edit results, not failed planners or learned entries. [First applied result, trace313](workspaces/SI/runs/research-1f76e7b0b87045b88fd94aa92bb5ee2d/trace.jsonl:313), [finalizer applied result, trace324](workspaces/SI/runs/research-1f76e7b0b87045b88fd94aa92bb5ee2d/trace.jsonl:324).

All six harness retrieval events—initial retrieval plus five root boundaries—return empty entries. They occur at trace9,28,52,110,160,196, all before the agent request at287. There is **no retrieval after the request**, no refinement edit/commit, no learned entry, and no action attributable to such an entry. This run demonstrates a model-initiated request before worker exit and correct post-worker decline/finalization. It does not exercise the new completion-feedback/retrieval path on a later root turn and cannot be counted as same-run learning or reuse. The distinction is also preserved in the machine-readable review.
