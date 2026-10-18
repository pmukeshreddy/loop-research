# Recorded implementation checks and real diagnostics

All runs below used the official Codex CLI with ChatGPT authentication or
explicitly fictional offline fixtures. No separately billed model API or
external search provider was configured or invoked. Codex subscription usage
is measured in tokens; subscription fees and account credit policies are not
included in the recorded $0 additional API/search cost.

Run artifacts and source snapshots are local, ignored by Git, and are not
included in this repository. Paths below refer to the development workspace;
the README documents how to produce your own runs.

## Local implementation

- 56 tests pass; Ruff passes.
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

## Delivered real dataset

Use the local `runs/live-delivery/export/` directory, rather than
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

After an actual human audit, record the decision with the `review` command in
the README, using `--run-dir runs/live-delivery --task-id seed-0001-v0`.

Built-in Codex search was observed in isolated diagnostic sessions and in the
live expansion search. There is no missing search capability requiring an
external provider. Solver validation deliberately uses a frozen document corpus,
not open-web navigation. Separate sessions reduce information sharing but do
not make same-model judgments statistically independent.

The ten-task diagnostic batch, a manually approved dataset, and an accepted
expanded real task have not been established by these runs. Successful expanded
tasks in the local fixtures are not evidence of real-data difficulty. Review the
first accepted real task before expanding the source universe or target size.
