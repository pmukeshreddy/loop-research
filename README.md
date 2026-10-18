# Loop Research

Loop Research explores data and methods for deep-research systems. **Synthetic
Data Generation** is the first implemented stage, with company research as the
current example domain. Later project stages, including training and RL, are not
implemented.

## Synthetic Data Generation

<p align="center">
  <a href="docs/assets/synthetic-data-pipeline.png">
    <img src="docs/assets/synthetic-data-pipeline.png" width="420" alt="Synthetic data pipeline: source collection, evidence graph, seed generation and validation, question expansion and validation, then deduplication and export. Failed validation loops back to seed generation or expansion.">
  </a>
</p>

We generate **X**, a self-contained research question, and **Y**, its verified
reference answer, backed by **E**, private sources, passages, and an evidence
chain. We collect evidence, generate seeds, expand research dependencies while
preserving the answer, validate, revise or reject, and export. Open-web solvers
receive only X and internet tools; acceptance requires observed browsing,
independent citation checks, and a bounded search for alternative answers.
The expansion method is inspired by
[WebShaper](https://arxiv.org/abs/2507.15061v1).

## Quickstart

Requires Python 3.11+ and `uv`; run from the repository root. This offline example
uses **fictional scripted fixtures**, with no model or search calls.

```bash
uv venv
uv pip install -r requirements.lock
export PYTHONPATH="$PWD/src"
.venv/bin/python -m webshaper run --config configs/fixture.json --run-dir runs/quickstart
```

Results appear in `runs/quickstart/export/`; repeat the run command to resume.
This quickstart exercises the legacy corpus path; open-web validation has
[offline tests and a bounded live command](docs/running.md).
Live runs use Codex subscription authentication through ChatGPT sign-in, enforce
configured usage limits, and allow $0 additional paid API/search spend.

## Outputs

Each dataset includes **questions, reference answers, evidence, and validation
records**, with source snapshots and revision history retained for audit.
Only public questions go to open-web solvers; references, evidence, source lists,
and validation records stay private. Legacy corpus runs retain their original mode;
automatically accepted live tasks await human review.

## Documentation

- [Configuration, live runs, and authentication](docs/running.md)
- [Output files and human review](docs/outputs.md)
- [Testing and troubleshooting](docs/development.md)
- [Design and company-research adaptations](docs/design.md)
- [Open-web contracts and validation](docs/open-web-design.md)
- [Recorded runs](docs/run-results.md) and [verification history](docs/verification-log.md)
- [Implementation plan](docs/implementation-plan.md) and [original brief](2026-10-17-webshaper-data-generation.md)
