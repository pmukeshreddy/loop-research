# Continual harness implementation plan

**Goal:** Replace the gated skill loop with the user's continual harness design.
**Spec:** The seven-step request and the replacement `PIPELINE_SPEC.md`.
**Architecture:** A trusted host owns harness Git state, evidence, refinement,
grading, and reporting. A macOS Seatbelt worker runs stock LocalREPL with full
Python and accesses host services through a narrow JSON RPC interface.

Global constraints: subscription-only `codex exec`; no live tests or task runs;
no gold or grade feedback to research/refinement; delete obsolete implementations.

- [x] Record pinned Prime Agent and paper findings, including intentional overrides.
- [x] Test and build CRUD, BM25, Git edits, outcomes, rollback, and lineage forks.
- [x] Test and build evidence-based self-check and asynchronous refinement.
- [x] Test OS isolation and integrate stock LocalREPL, trusted tools and turn boundaries.
- [x] Replace orchestration/CLI with research and seeded streams; reports own grades.
- [x] Remove old code/config/tests, update spec and README, run the full offline suite.

Review focus: stale refinement plans; rollback after later edits; interrupted tasks
and reruns; malicious Python accessing archives or changing evidence; comparison
streams starting with different harness state. Tests must exercise each behavior.

Validation: 270 offline tests passed, one live test deselected. Independent review
findings were fixed with regressions. Installed CLI and packaged-wheel initialization
were verified without model calls. No live research, stream, or test was run.
