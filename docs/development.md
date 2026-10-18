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
| Source cannot be captured | Inspect `export/errors.jsonl` for robots restrictions, redirects, domain restrictions, byte limits or retrieval failures. Configure the final allowed URL explicitly. Changed capture conditions require a new run. |
| Historical evidence is rejected | Verify publication and effective dates and their source basis. Undated sources remain ineligible; do not substitute retrieval dates. |
| Run reports frozen configuration mismatch | Restore the original settings or use a new run directory. Do not edit the journal's frozen hashes. |
| Run pauses or a call outcome is unknown | Follow [checkpoints and limits](running.md#checkpoints-and-limits); unknown calls are not blindly retried. |
| Run completes with no task or only depth 0 | Inspect `rejected.jsonl`, `errors.jsonl`, `validation.jsonl` and the quality report. Bounded completion is not an acceptance or expansion guarantee. |
| Public corpus lacks source text | Check redistribution and temporal access policies in [outputs](outputs.md#access-and-interpretation). Private snapshots may still exist. |

SQLite checkpoints and locking support one local run process; distributed workers
are outside the current implementation. Preserve prior runs when changing code.
