# Open-web question generation and validation

The dataset is X (a self-contained question), Y (a verified answer), and private E
(sources, exact passages, typed claims and evidence chain). Company research
remains the example domain. Training, RL and UI remain outside scope.

## Boundary and compatibility

Add explicit `research_mode: open_web` alongside `legacy_corpus`. Missing mode
means legacy, so historical records cannot acquire web-validation claims by being
re-exported. New live templates select open web. Keep historical run directories
unchanged. The private typed graph still constructs and checks references, but
open-web public tasks carry no corpus identifier, URLs or document manifest.
Fresh solver payloads contain only question, output requirements and a fixed
browsing budget. Disable local tools and restrict local readable roots to the
temporary role directory (output schema only) plus minimal runtime paths; never
mount private run artifacts. Disable local network access; hosted web is separate.

## Validation

Retain deterministic and independent private-evidence checks. Generate new,
self-contained wording and investigate web alternatives; graph uniqueness is
insufficient. The offline private judge checks construction support and wording;
the mandatory browsing alternative audit assesses web ambiguity. Offline inability
to search must not prevent that audit from running. Closed-book screening applies
to every open-web task. A browsing
attempt needs observed completed search and page-reading activity, not a model's
claim of browsing. Capture tool events, URLs/ref targets, citations, token usage,
latency and failures. Unknown action/ref mappings are not invented visited URLs.

Independently capture solver-cited pages, verify exact quoted spans and date
eligibility, then grade every required condition against those pages. Freshly
captured pages with missing publication metadata or disallowed future dates fail
the shared deterministic source policy before grading; model judgments cannot
override it. Original captures remain private for audit. Separately
search for plausible alternatives and record candidates, evidence, exclusions,
unresolved alternatives and search extent. Never claim exhaustive uniqueness.
Missing tools, missing activity, access errors, budgets, incorrect answers and
unsupported citations have distinct outcomes. All incomplete checks fail closed.

Expanded tasks preserve exact intermediate identity and Y. Retain graph ablation,
then test whole-dependency removal and each connected partial-clue removal with
fresh solvers. Unrenderable/disconnected partial removals are explicitly recorded;
a connected partial shortcut producing a supported original answer rejects the
claimed expansion. Report actual graph layer and observed behavior, never equate
longer wording with empirical research depth. Enumerate removal of every added
atom, including variable joins; each connected distinct variant must pass, and
acceptance requires both a whole removal and at least one connected partial test.
A single-clue dependency without a distinct partial test remains unaccepted.

## Bounded operation

Official Codex CLI, ChatGPT subscription authentication, no extracted tokens,
API-key backend or paid search fallback. Existing pilot ceiling: $0 additional,
1,500,000 tokens, 50 calls, 15 web actions, concurrency 1. Search/open/find events
all consume the web-action budget. Reserve one action above the model's instructed
allowance and stop at that margin, retaining queued events. Remote cancellation
and token usage can lag local observation; this is not an upstream hard quota.
Provider traces survive failures; completed
calls are cached and unknown outcomes pause. A pilot may finish rejected or pause
without producing a dataset; preserve and report those outcomes.
