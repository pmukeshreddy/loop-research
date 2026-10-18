# Testing and troubleshooting

Use the [README quickstart](../README.md#quickstart) for environment setup and the
single canonical offline run command. Commands below run from the repository root
with the same `PYTHONPATH`. No live generation is required for local verification.

## Tests

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
```

The fixture workflow produces one fictional task at expansion layer 1 and retains
two unsupported expansion proposals as rejections. Its corpus, provider, judgments
and solver responses are scripted, not real company data or empirical model
results. Fixture mode cannot access the network; live mode rejects fixture
providers. See [fixture data](../tests/fixtures/README.md).

`tests/test_open_web.py` additionally runs a fully scripted open-web path, including
expansion, citation capture, alternatives, whole/partial shortcuts and resume.
All tool events, network captures and judgments in these tests are synthetic;
they never constitute actual browsing. Provider tests separately check live CLI
flags, filesystem restrictions, observed event parsing and failure checkpoints.

`tests/test_campaign.py` adds scripted campaign coverage for private allocation,
minimum depth, diverse quotas, official-identity deduplication, positive-only
connected evidence, observed discovery URLs, crash recovery and explicit budget
extensions. Its accepted expansion is an **offline fixture**, not a live result.

`tests/test_collection_repair.py` reproduces captured markup patterns with clearly
synthetic pages: itemprop and JSON-LD publication fields, article time tags,
visible labels, conflicting dates, modification/event/related-content exclusions,
and a nested article with a different page identity. Mocked HTTP tests cover
bounded redirects, destination robots denial, unsupported formats and capture
reuse. Continuation tests preserve original snapshot hashes and inherited usage;
the pilot milestone requires multiple companies and an accepted expansion.

Repeat the quickstart run command to check resumability: completed calls and
exports should remain unchanged. The tests cover exact-answer preservation,
nonredundancy, date eligibility, source hashes, validation, budgets and pauses.
[Verification history](verification-log.md) records completed checks;
[run results](run-results.md) separately records live observations.

When changing model contracts, regenerate their schemas:

```bash
.venv/bin/python -m webshaper schemas --output schemas
```

For a regular package installation rather than a checkout on `PYTHONPATH`:

```bash
uv pip install '.[dev]'
```

The installed entry point is `webshaper`, equivalent to `python -m webshaper`.
Python 3.11+ is required; recorded checks used Python 3.12.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| `No module named webshaper` | Set `PYTHONPATH` as shown in the quickstart, from the repository root. Some macOS environments hide editable-install `.pth` files, causing Python to skip them. A regular package installation also works. |
| Codex authentication or flag check fails | Use the [authentication checks](running.md#authentication-and-a-live-run); ChatGPT sign-in and a compatible official CLI are required. Never copy OAuth tokens into pipeline configuration. |
| Source cannot be captured | Inspect `export/errors.jsonl` for blocked access, redirect loops/limits, unsupported formats or retrieval failures. Legitimate redirects receive destination checks. Seek another accessible primary source; do not bypass restrictions. Changed capture conditions require a new run. |
| Historical evidence is rejected | Verify publication and effective dates and their source basis. Undated sources remain ineligible; do not substitute retrieval dates. |
| Run reports frozen configuration mismatch | Restore the original settings or use a new run directory. Do not edit the journal's frozen hashes. |
| Run pauses or a call outcome is unknown | Follow [checkpoints and limits](running.md#checkpoints-and-limits); unknown calls are not blindly retried. |
| Collection-only run predates a parser repair | Use the explicit [new-directory continuation](company-campaign.md#collection-repair-and-bounded-pilot); original runs remain unchanged and their usage is inherited. |
| Run completes with no task or only depth 0 | Inspect `rejected.jsonl`, `errors.jsonl`, `validation.jsonl` and the quality report. Bounded completion is not an acceptance or expansion guarantee. |
| Public corpus lacks source text | Check redistribution and temporal access policies in [outputs](outputs.md#access-and-interpretation). Private snapshots may still exist. |
| Open-web attempt has no browsing or page read | Inspect `web_traces.jsonl` and the capability report. No generated answer can substitute for observed search and page-reading events. |
| Citation cannot be verified | Inspect `web_evidence.jsonl`: unobserved URL, retrieval/access failure and missing exact quote are distinct reasons. The verifier does not fill gaps with private generator evidence. |

SQLite checkpoints and locking support one local run process; distributed workers
are outside the current implementation. Preserve prior runs when changing code.
