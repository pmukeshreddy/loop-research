# Formalization and engineering adaptations

WebShaper §2 defines Knowledge Projections as entity sets reached through a
relation. Intersections combine constraints; R-union distributes over input
sets. §3.2.1 flattens recursion into variable/constant triplets. §3.2.2 freezes
leaf constants and replaces them with identifying subquestions one layer at a
time, preserving the target answer. §3.2.3's consistency check tests type fit,
not exact equality. This implementation adds stronger checks; it does not
reproduce the paper's full system, datasets, results or training pipeline.

Our query is a union (`branches`) of conjunctions (`Atom`s). Each atom has a
variable subject, a directed typed predicate and a variable or constant-set
object. A constant list is the R-union input set. A shared variable joins
relations; funding/acquisition events are typed entities so dates, rounds and
investors bind to the same event. Predicates live in `query.PREDICATES`.
Every branch must connect to the answer; cycles are evaluated as finite joins.
Branch/variable/row bounds prevent accidental combinatorial resource exhaustion.

The evidence graph is open-world. Only resolved, independently supported facts
with suitable effective/publication dates can produce answers. Contradictory
eligible claims are removed from executable facts. Missing positive evidence
does not establish a negative. Exhaustive lists require enumerated candidates;
every candidate must have an inclusion proof or an explicit exclusion certificate.
The initial engine supports conservative rooted-negative certificates; other
exclusions remain unresolved. Identified targets require cardinality checks
and separate semantic ambiguity assessment.

Expansion eligibility is limited to degree-one company, investor, person,
product and location constants. Dates, categories and operational predicates
stay fixed. At layer start the ordered leaves are checkpointed. New leaves wait
until the next layer. Subquery answers must equal the original constant set.
Variables are renamed to prevent capture, and only the selected leaf is replaced.
The final answer must equal its parent and original reference. Clue ablation
must change graph answers; a configured sample also tests solver behavior.
Failed leaves retain their last validated parent. `actual_layer` records the
last successful layer; the journal also records whether all leaves expanded.
Known discovery or evidence-extraction failures reject the affected leaf and
retain its parent; subscription limits and uncertain remote outcomes pause.

Evidence spans use Python Unicode character offsets in the saved UTF-8 text.
Raw bytes and extracted text have separate SHA-256 hashes. Publication,
retrieval and effective/event dates are separate. HTML dates are parsed from
publication metadata; curated dates must include their source basis. Unknown
dates cannot pass historical gates. Source retrieval never uses a model to
replace inaccessible content. Captured HTML strips script/style text; the
remaining content is still treated as untrusted evidence by all prompts.

An exact quote repeated in a summary and body uses the first occurrence unless
the generator provides an explicit valid offset. There is no fuzzy quote repair.
An explicit source-scoped entity ID also counts as a source identifier; that
identifier is preserved for the independent identity assessment. Equal literal
year/date/category values are canonicalized across sources. Real companies,
people and investors are never merged merely because their names match.

The verifier has separate instructions and sessions. It assesses claim meaning,
identity, time, wording, alternatives, leakage and usefulness. Deterministic
gates run first and cannot be overridden. Five independent corpus-based solver
attempts are used by default; exact answers alone do not pass, because citations
need resolvable quotes and separate semantic grading. Expanded tasks also receive
a closed-book screen. These screens are model-relative, not truth guarantees.

SQLite records calls before dispatch. Completed structured responses are cached;
malformed completed responses may be revised within limits, while unknown
transport outcomes stop the run. Subscription-limit retries require an explicit
CLI flag after reset. Token/search/call counts survive restarts. Authentication
is exclusively delegated to Codex. No OAuth tokens or API keys enter run data.

Deduplication combines normalized wording with alpha-normalized query structure,
answer set, date and scope. Provenance remains retained for discarded candidates.
Question/reference conflicts reject both copies. Splits group seed families,
shared answers and exact/near-duplicate source pages. Conservative grouping can
yield only one split for a small corpus; that is reported rather than forced into
misleading train/test proportions. A generated test split is not an independent
benchmark for research-agent generalization.
