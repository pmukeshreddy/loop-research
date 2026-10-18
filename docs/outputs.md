# Dataset outputs and review

Each run stores questions, reference answers, evidence, validation records and
provenance. The dataset endpoint is implemented; training and RL are not.
See [running the pipeline](running.md) for configuration and run commands.
Discovery campaigns also provide a private [company coverage report](company-campaign.md#results-and-private-artifacts)
with qualified companies, accepted counts, depth, browsing results, shortfalls and
usage. Campaign public task IDs are opaque; reference records include the private
internal ID for validation/provenance joins. The review command accepts either ID.

## Files

`RUN/export/` contains:

| File | Content |
| --- | --- |
| `tasks.jsonl` | Public questions, answer schema, cutoff, scope and permitted environment |
| `references.jsonl` | Private reference answers, queries, answer evidence and completeness decisions |
| `provenance.jsonl` | Candidate versions, parent lineage, layers, leaf replacements, models and hashes |
| `graphs.jsonl`, `sources.jsonl` | Frozen typed facts, exact evidence spans, support assessments and source metadata |
| `validation.jsonl` | Checks, isolated solver attempts and citation grades |
| `attempts.jsonl` | Validation starts, including work paused before a final decision |
| `rejected.jsonl`, `errors.jsonl` | Revisions, rejections and capture/extraction errors |
| `usage.jsonl` | Call status, tokens, search actions, latency and additional API cost |
| `manifest.json` | Frozen configuration, versions, hashes, metrics and partition membership |
| `quality_report.md` | Coverage, depth, screens, validation results, costs and limitations |
| `web_traces.jsonl` | Private observed CLI web events, absolute opened URLs, token usage, latency and failures |
| `web_attempts.jsonl`, `web_evidence.jsonl`, `web_sources.jsonl` | Private completed/paused solver attempts and independently captured citation spans/pages |
| `web_alternatives.jsonl`, `web_shortcuts.jsonl` | Private alternative-answer search extent/exclusions and whole/partial ablation results |
| `public/` | Open-web questions only; legacy mode additionally exports temporally eligible corpus entries |

Original raw bytes and extracted text remain in `RUN/sources/`, protected by
content hashes. Independent solver-citation captures are in `RUN/web_sources/`.
JSON schemas are in [`schemas/`](../schemas/).

## Access and interpretation

Do not mount the entire run directory in a solver environment. References,
graphs, traces, validation records and private evidence mappings must remain separate
from solver-visible questions. For `research_mode: open_web`, public X has only
task ID, question, answer schema, cutoff, tool declaration, data mode and research
mode. Its public corpus file is empty. Actual solver payloads are smaller: question,
output requirements and budget. The solver discovers pages independently.

Legacy `research_mode: legacy_corpus` preserves the original corpus-solving contract.
Its public export excludes entire entries for undated sources and, unless
`allow_retrospective` is explicit, post-cutoff sources. Original snapshots and
metadata remain private. Text with unknown redistribution rights is withheld;
such tasks require separately authorized access to snapshots. Their public
export alone is not a self-contained corpus.

Open-web metrics distinguish all attempted sessions from sessions with observed
search and page reads; self-reported browsing never counts. Inspect failure
categories for access errors, missing tools, budget exhaustion, incorrect answers
and unsupported citations. `actual_layer` measures accepted graph expansion,
not the number of sources a solver needed or a universal difficulty level.
Alternative checks report bounded search coverage, not exhaustive uniqueness.

Check `data_mode` before interpreting results. Fictional scripted fixtures test
implementation behavior; their success rates are not measured model performance.
Live tasks are automatically validated but remain `pending_manual_review` until
an actual reviewer records a decision. Separate sessions may share model errors.

The query engine returns canonical entity sets, not multi-column tables.
Exhaustive exclusions require explicit negative evidence in each relevant query
branch; absence is unknown. Small datasets can form one partition because splits
group related sources, answers and lineages. Partition labels do not imply a
training implementation or an independent evaluation benchmark.

## Human review

After auditing an accepted live task, use its actual run directory and task ID:

```bash
.venv/bin/python -m webshaper review --run-dir runs/my-real-expansion \
  --task-id TASK_ID --decision approved --reviewer 'Reviewer name' \
  --notes 'Checked dates, answer set, source spans, wording and alternative answers.'
```

The command records the review and refreshes exports. Use `--decision rejected`
for a human rejection; the task is removed from the dataset while its history
remains. Do not record approval without an actual audit.

To rebuild exports independently, without dispatching models:

```bash
.venv/bin/python -m webshaper export --run-dir runs/my-real-expansion
```

Export and review use the authoritative journal's original generation settings,
including after implementation upgrades. The manifest records the current
exporter hash separately. Run setup is described in [the live-run guide](running.md).
