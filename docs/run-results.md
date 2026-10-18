# Recorded implementation checks and real diagnostics

All runs below used the official Codex CLI with ChatGPT authentication or
explicitly fictional offline fixtures. No separately billed model API or
external search provider was configured or invoked. Codex subscription usage
is measured in tokens; subscription fees and account credit policies are not
included in the recorded $0 additional API/search cost.

Run artifacts and source snapshots are local, ignored by Git, and are not
included in this repository. Paths below refer to the development workspace;
the [live-run guide](running.md) documents how to produce your own runs.

## Local implementation

- 62 tests pass; Ruff passes (including six temporal-export and closed-book
  early-return regression cases added after the initial delivery).
- The built wheel installs and runs the fixture workflow outside this checkout.
- `runs/fixture-final-delivery` contains one **fictional scripted** expanded task at
  layer 1, two rejected expansion proposals and two source fixtures.
- Repeating that run leaves all 15 export files and all 29 completed scripted
  calls unchanged. The test suite also exercises two-layer expansion, rejection,
  bounded revision, exact answers, event joins, unknown membership and pauses.
- Fixture solver success rates are programmed test behavior, not model results.

## Real integration history

Earlier runs remain available for audit; errors were not erased or relabeled.

| Run | Outcome | Calls | CLI tokens | Search actions |
| --- | --- | ---: | ---: | ---: |
| `live-smoke-v1` | No tasks; repeated exact quote span handling failed | 2 | 45,159 | 0 |
| `live-smoke-v2` | No tasks; source identifier field mismatch | 2 | 44,134 | 0 |
| `live-smoke-v3` | No tasks; two seeds plus revisions rejected | 9 | 205,086 | 0 |
| `live-smoke-v4` | One automatically accepted seed; two expansion refusals | 19 | 520,227 | 3 |
| `live-delivery` | One automatically accepted seed; four non-accepted versions | 21 | 516,171 | 2 |

These runs used different frozen implementation hashes as fixes were made.
Generation cannot resume under changed code. Existing exports can be rebuilt
and actual human reviews recorded using the journal's original settings;
the manifest tracks the export implementation separately.

In `live-smoke-v4`, all five isolated corpus-based solver attempts answered the
seed correctly with separately graded citations. Its six required source spans
still reproduce its reference under the final deterministic checks. There were
nine captured primary documents across the initial bundle and expansion search;
two lacked usable publication dates and cannot support historical claims.
Support-audit totals count assessments across graph versions, not distinct facts.

No expansion was accepted: the permitted evidence did not identify the selected
investor through a supported new dependency. The actual depth is **0**, and no
closed-book difficulty result was obtained. Its expansion refusals retain their
original free-text reason fields; new runs use a stable `no_valid_expansion` code.
The seed also said “supplied graph” although the solver received documents. The
generator prompt was corrected for the final diagnostic; this earlier output
remains unchanged and pending manual review.

## Initial delivered real dataset (historical)

The initial delivery used the local `runs/live-delivery/export/` directory, rather than
combining the diagnostic runs. The earlier accepted seed and delivered seed
identify the same company; these are separate integration runs, not two unique
dataset examples.

- **One automatically validated real task**, `seed-0001-v0`, with a private
  reference, six supporting spans, source snapshots, query and validation record.
- Five of five independent corpus-based solver sessions returned the correct
  answer with separately graded supporting citations.
- **Actual expansion depth: 0.** One expansion proposal violated the typed
  subject rule; its revision failed exact-answer/cardinality/expansion checks
  and clue-ablation nonredundancy. The valid seed was retained.
- Two earlier seed versions failed the required ISO cutoff wording. Feedback
  and future prompts now spell out the exact required date string; the gate was
  not relaxed. All four non-accepted versions remain recorded.
- Seven primary documents captured; three publication-date errors recorded.
  Undated evidence did not support the accepted historical answer. No source
  capture or fact-extraction failures occurred in this run.
- 21 completed Codex sessions, 516,171 observed input/output tokens, two search
  actions and approximately 356 seconds of summed provider latency. No uncertain
  calls and no separately billed API/search cost. These are this run's figures;
  the table separately preserves earlier diagnostic usage.
- No duplicate final tasks; one grouped partition. No closed-book attempt was
  warranted because no expanded candidate passed the preceding correctness gates.

The final reference and all six spans were replayed under the delivered
deterministic checks. JSONL exports parse, source hashes verify, and public files
contain no reference or validation records. Source text without known reuse
permission is withheld from the public corpus export.

**Human review remains pending.** No approval has been invented or recorded.
The question now refers to the supplied corpus:

> As of 2025-12-31, which company in the supplied corpus builds a humanoid robot
> and announced Series A funding on February 13, 2025, with Google participating?

After an actual human audit, record the decision with the
[review command](outputs.md#human-review), using
`--run-dir runs/live-delivery --task-id seed-0001-v0`.

Built-in Codex search was observed in isolated diagnostic sessions and in the
live expansion search. There is no missing search capability requiring an
external provider. Solver validation deliberately uses a frozen document corpus,
not open-web navigation. Separate sessions reduce information sharing but do
not make same-model judgments statistically independent.

The ten-task diagnostic batch, a manually approved dataset, and an accepted
expanded real task were not established by these original runs. Successful expanded
tasks in the local fixtures are not evidence of real-data difficulty. Review the
first accepted real task before expanding the source universe or target size.

## Expansion milestone follow-up

Previous runs were preserved. The two bugs were fixed before generating new data:
public corpus export now applies the validator's temporal eligibility to whole
entries; a failed closed-book difficulty gate returns before browsing, grading,
or shortcut auditing. Private original snapshots remain available.

Source discovery used three isolated Codex sessions: **199,263 tokens, seven
built-in search actions, $0 additional API/search cost**. The first searches did
not find the requested 2025 announcement; those empty/partial results remain in
`runs/expansion-source-discovery/run.sqlite`. Captured articles, not search
snippets, supplied the eventual evidence. No missing search capability or paid
external fallback was encountered.

`configs/real-expansion.json` contains four primary investor articles with visible
dateline bases. Cerbos and Cradle provide different investor relationships for
funding announcements in 2023; Fullview and Salesroom supply earlier, independent
relationships identifying Seedcamp. All articles predate the 2025-12-31 cutoff.
Generation uses the fixed bundle (`search_provider: none`), fresh Codex sessions,
concurrency 1, and the unchanged 50-call / 1,500,000-token / 15-search / $0 limits.

`runs/real-expansion-v1` retained **only depth 0**, using 16 calls and 326,290
tokens, with zero searches and $0 additional spend. Its first seed was rejected
for a wording/query mismatch. Extraction had omitted announcement-year facts;
the corrected two-date query repeated the investor constant across branches,
leaving no eligible degree-one leaf. This does **not** satisfy the milestone.
Prompt v1.3 requests separately evidenced year projections and an eligible leaf;
the next run starts in a new directory with its own frozen implementation hash.

### Accepted real expansion: `runs/real-expansion-v2`

**Milestone achieved: one automatically accepted real task at depth 1**,
`seed-0000-l1-leaf0-v1`, from parent `seed-0000-v0`. Human review remains pending.
This is live model output, not a fixture or a retained depth-0 seed.

> As of 2025-12-31, which company in the supplied frozen corpus had a funding
> announcement in 2023 with an investor that also co-invested with Lightspeed
> Venture Partners in one funding round and Craft Ventures in another?

- Original and expanded reference: **Cerbos**, with the identical canonical ID.
- Supported intermediate identity: **Seedcamp**, using its co-investment in
  Fullview's round with Lightspeed Venture Partners and Salesroom's round with
  Craft Ventures. Four independently supported event-investor claims identify
  the intermediate exactly. Unsupported portfolio start-date claims were not used.
- Removing the added dependency changes the computed answer set to **Cerbos and
  Cradle**, passing the unchanged deterministic nonredundancy check.
- The independent candidate judge passed every required semantic and claim-support
  check. Historical source/effective-date and exact-answer checks passed.
- The closed-book solver returned no answer and explicitly reported insufficient
  knowledge of the corpus and co-investment links. The difficulty screen passed.
- **5/5 expanded-task corpus solver attempts passed** exact-answer and independent
  citation grading. The seed separately passed 5/5. The optional 10% empirical
  shortcut audit was not sampled for this task; deterministic clue ablation was
  performed and replayed. This is model-relative evidence, not universal difficulty.
- One invalid event binding was corrected within the existing extraction revision
  allowance. An initial expansion failed exact intermediate identity and was
  revised. The failed records remain; no acceptance rule was relaxed.
- Four captured primary sources; no capture/date failures. All source hashes and
  required evidence spans verified. Full private snapshots remain local; public
  text is withheld where redistribution permission is unknown.
- **29 completed Codex sessions, 541,516 tokens, zero search actions in this run,
  $0 additional paid API/search cost**, and no uncertain calls. About 421 seconds
  of summed provider latency. Resume dispatched zero calls and left all 15 export
  files byte-identical.

The follow-up including discovery and the unsuccessful v1 attempt used **48
completed pipeline sessions, 1,067,069 tokens, seven Codex search actions and $0
additional paid API/search cost**. Earlier historical runs are separate, as listed
above. All original run directories remain unchanged.

Local artifacts under `runs/real-expansion-v2/`:

| Path | Contents |
| --- | --- |
| `export/tasks.jsonl` | Accepted expanded question and public task |
| `export/references.jsonl` | Original-preserving reference, query and evidence IDs |
| `export/graphs.jsonl` | Typed facts, exact evidence spans and support assessments |
| `export/sources.jsonl`, `sources/` | Source metadata and immutable original raw/text snapshots |
| `export/validation.jsonl` | Seed and expanded-task checks, solver responses and citation grades |
| `export/provenance.jsonl` | Parent, layer, selected leaf and exact intermediate subquery |
| `export/rejected.jsonl`, `export/errors.jsonl` | Preserved failures and revision reasons |
| `export/usage.jsonl`, `export/manifest.json` | Call-level usage and frozen run configuration |
| `milestone-check.json` | Read-only deterministic replay results and resume verification |

Reproduce with the [live-run commands](running.md#authentication-and-a-live-run)
in a fresh directory. To resume this run under its unchanged implementation,
use `runs/real-expansion-v2` as the run directory. Local test commands are in
[development](development.md#tests).

The separate model sessions are isolated, but same-model errors may be correlated.
The dataset makes a corpus-scoped identification claim, not open-web completeness.
Neither training nor RL was introduced.
