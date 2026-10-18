"""Sequential candidate pipeline; optional bounded parallel independent solver attempts."""
import fcntl
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import ValidationError

from .expansion import leaf_constants, replace_leaf
from .generation import SearchResults, extract_bundle, make_seed
from .models import Bundle, Candidate, ExpansionProposal, SeedProposal, Source, SourceInput, Validation
from .prompts import PROMPTS, PROMPT_VERSION
from .providers import CodexProvider, ModelGateway
from .query import eligible_facts
from .sources import SourceStore
from .storage import BudgetExceeded, Journal, SubscriptionLimit, UncertainCall, digest, now
from .validation import validate


@contextmanager
def run_lock(root):
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("another process is running this run directory") from error
        yield


def frozen_config(config):
    files = {str(Path(s.origin).resolve()): digest(Path(s.origin).read_bytes())
             for s in config.sources if not s.origin.startswith(("http://", "https://"))}
    implementation = {p.name: digest(p.read_bytes()) for p in sorted(Path(__file__).parent.glob("*.py"))}
    return {"config": config.model_dump(mode="json"), "local_source_hashes": files,
            "prompt_version": PROMPT_VERSION, "prompt_hash": digest(PROMPTS), "implementation_hash": digest(implementation)}


def error_record(journal, stage, identifier, error, **extra):
    data = {"stage": stage, "identifier": identifier, "code": type(error).__name__,
            "reason": str(error), **extra}
    journal.record("errors", digest(data), data)


def collect_sources(config, store, journal, inputs=None):
    checkpoint = "sources:" + digest([s.model_dump(mode="json") for s in (inputs or config.sources)])
    cached = journal.get(checkpoint)
    if cached is not None:
        return [Source.model_validate(s) for s in cached]
    queue = [(s, 0) for s in (inputs or config.sources)]
    sources, visited = [], set()
    while queue and len(sources) < config.max_sources:
        spec, depth = queue.pop(0)
        if spec.origin in visited:
            continue
        visited.add(spec.origin)
        try:
            if spec.origin.startswith(("http://", "https://")):
                if config.mode == "fixture":
                    raise ValueError("fixture sources cannot use the network")
                source, links = store.capture_url(spec.origin, config.allowed_domains, spec)
            else:
                source, links = store.capture_local(spec)
            sources.append(source)
            if source.published_at is None:
                error_record(journal, "source_date", spec.origin, ValueError("publication_date_missing"))
            if depth < config.crawl_depth:
                queue.extend((SourceInput(origin=url), depth + 1) for url in links
                             if urlsplit(url).hostname in config.allowed_domains)
        except (ValueError, OSError, Exception) as error:
            # Retrieval/extraction errors are explicit records; never synthesize replacement text.
            error_record(journal, "source_capture", spec.origin, error)
    journal.put(checkpoint, [s.model_dump(mode="json") for s in sources])
    return sources


def save_graph(journal, bundle, sources):
    data = {"bundle": bundle.model_dump(mode="json"), "sources": [s.model_dump(mode="json") for s in sources]}
    graph_id = "corpus_" + digest(data)[:24]
    journal.record("graphs", graph_id, {"graph_id": graph_id, **data})
    return graph_id


def load_graph(journal, graph_id):
    data = next(g for g in journal.records("graphs") if g["graph_id"] == graph_id)
    return Bundle.model_validate(data["bundle"]), [Source.model_validate(s) for s in data["sources"]]


def discover(config, gateway, journal, store, request, call_id, existing):
    if config.mode == "fixture" or config.search_provider == "none" or not config.allowed_domains:
        return existing
    results = gateway.call("expander", "search", {"request": request, "as_of": str(config.as_of),
                           "allowed_domains": config.allowed_domains}, SearchResults, call_id, web=True)
    if not results.capability_available:
        raise ValueError("Codex built-in search unavailable; no paid external fallback is configured")
    inputs = [SourceInput(origin=h.url, title=h.title) for h in results.hits
              if urlsplit(h.url).hostname in config.allowed_domains
              and h.url not in {s.url_or_local_origin for s in existing}]
    remaining = config.max_sources - len(existing)
    if inputs and remaining > 0:
        added = collect_sources(config, store, journal, inputs[:remaining])
        return list({s.source_id: s for s in existing + added}.values())
    return existing


def generate_graph(config, sources, store, journal, gateway, prefix, previous=None):
    cached = journal.get(prefix + ":graph")
    if cached:
        return cached, *load_graph(journal, cached)
    feedback = []
    for revision in range(config.max_revisions + 1):
        try:
            bundle, assessment = extract_bundle(sources, store, gateway, prefix + f":v{revision}", previous, feedback)
            graph_id = save_graph(journal, bundle, sources)
            journal.record("support_audits", prefix + f":v{revision}", assessment)
            journal.put(prefix + ":graph", graph_id)
            return graph_id, bundle, sources
        except (ValueError, ValidationError) as error:
            feedback = [str(error)]
            error_record(journal, "extraction", prefix + f":v{revision}", error)
    raise ValueError("no schema-valid evidence graph after bounded extraction attempts")


def evaluate(candidate, bundle, sources, store, gateway, config, journal, parent=None):
    key = candidate.task.task_id
    saved = journal.get("evaluated:" + key)
    if saved:
        return Candidate.model_validate(saved["candidate"]), Validation.model_validate(saved["validation"])
    journal.record("candidate_attempts", key, {"task_id": key, "seed_id": candidate.seed_id,
                   "parent_id": candidate.parent_id, "candidate_version": candidate.version,
                   "layer": candidate.layer, "graph_id": candidate.graph_id})
    result = validate(candidate, bundle, sources, store, gateway, config, parent)
    journal.record("candidates", key, candidate)
    journal.record("validations", key, result)
    if result.decision != "accept":
        journal.record("rejected", key, {"task_id": key, "seed_id": candidate.seed_id,
                       "decision": result.decision, "reason_codes": [c.name for c in result.checks if c.status != "pass"],
                       "feedback": result.feedback, "candidate_version": candidate.version})
    journal.put("evaluated:" + key, {"candidate": candidate.model_dump(mode="json"), "validation": result.model_dump(mode="json")})
    return candidate, result


def generate_seed(config, bundle, sources, graph_id, store, journal, gateway, index, prior):
    seed_id = f"seed-{index:04d}"
    feedback = []
    for revision in range(config.max_revisions + 1):
        task_id = seed_id + f"-v{revision}"
        try:
            operation = "web_seed" if config.research_mode == "open_web" else "seed"
            proposal = gateway.call("generator", operation, {"graph": bundle.model_dump(mode="json"),
                                    "scope": config.scope.model_dump(mode="json"), "as_of": str(config.as_of),
                                    "prior_questions": prior, "revision_feedback": feedback}, SeedProposal, task_id)
            candidate = make_seed(proposal, config, bundle, sources, task_id, seed_id, revision, graph_id)
            candidate, result = evaluate(candidate, bundle, sources, store, gateway, config, journal)
            if result.decision == "accept":
                return candidate
            feedback = result.feedback
        except (ValueError, ValidationError) as error:
            feedback = [str(error)]
            error_record(journal, "seed", task_id, error)
            journal.record("rejected", task_id, {"task_id": task_id, "seed_id": seed_id, "decision": "reject",
                           "reason_codes": ["invalid_seed_proposal"], "feedback": feedback, "candidate_version": revision})
    return None


def expand_layers(parent, config, store, journal, gateway):
    for layer in range(1, config.layers + 1):
        bundle, sources = load_graph(journal, parent.graph_id)
        layer_key = parent.seed_id + f":layer:{layer}"
        frozen = journal.get(layer_key + ":leaves")
        if frozen is None:
            frozen = leaf_constants(parent.query, bundle)
            journal.put(layer_key + ":leaves", frozen)
        successes = 0
        for index, leaf in enumerate(frozen):
            step_key = layer_key + f":leaf:{index}"
            finished = journal.get(step_key + ":done")
            if finished is not None:
                if finished["accepted"]:
                    parent = Candidate.model_validate(finished["candidate"])
                    successes += 1
                continue
            bundle, sources = load_graph(journal, parent.graph_id)
            entities = {e.entity_id: e for e in bundle.entities}
            names = [entities[c].name for c in (leaf if isinstance(leaf, list) else [leaf])]
            try:
                enriched_sources = discover(config, gateway, journal, store,
                                            "Find dated identifying company/product/investor relationships for " + ", ".join(names),
                                            step_key + ":search", sources)
                graph_id = parent.graph_id
                if len(enriched_sources) > len(sources):
                    graph_id, bundle, sources = generate_graph(config, enriched_sources, store, journal, gateway,
                                                               step_key + ":enriched", bundle)
            except ValueError as error:
                # A known evidence/discovery failure rejects this leaf, not its
                # already validated parent. Limits and uncertain calls still pause.
                error_record(journal, "expansion_evidence", step_key, error)
                journal.record("rejected", step_key + ":evidence", {"task_id": step_key + ":evidence",
                               "seed_id": parent.seed_id, "decision": "reject",
                               "reason_codes": ["expansion_evidence_unavailable"], "feedback": [str(error)],
                               "candidate_version": 0})
                journal.put(step_key + ":done", {"accepted": False, "candidate": None})
                continue
            feedback, accepted = [], None
            for revision in range(config.max_revisions + 1):
                task_id = parent.seed_id + f"-l{layer}-leaf{index}-v{revision}"
                try:
                    operation = "web_expand" if config.research_mode == "open_web" else "expand"
                    proposal = gateway.call("expander", operation, {"parent": parent.model_dump(mode="json"),
                                            "selected_leaf": leaf, "graph": bundle.model_dump(mode="json"),
                                            "revision_feedback": feedback}, ExpansionProposal, task_id)
                    if proposal.subquery is None:
                        raise ValueError("no_valid_expansion: " + (proposal.rejection_reason or "no grounded proposal"))
                    facts = eligible_facts(bundle, sources, config.as_of, config.scope.allow_retrospective)
                    query, intermediate, atoms = replace_leaf(parent.query, leaf, proposal.subquery, bundle, facts)
                    task = parent.task.model_copy(update={"task_id": task_id, "question": proposal.proposed_question,
                                                          "corpus_id": graph_id if config.research_mode == "legacy_corpus" else None})
                    candidate = Candidate(task=task, query=query, answer=parent.answer, seed_id=parent.seed_id,
                                          parent_id=parent.task.task_id, layer=layer, version=revision,
                                          expanded_leaf=leaf, intermediate_answer=intermediate, subquery=proposal.subquery,
                                          added_atoms=atoms, graph_id=graph_id)
                    candidate, result = evaluate(candidate, bundle, sources, store, gateway, config, journal, parent)
                    if result.decision == "accept":
                        accepted = candidate
                        break
                    feedback = result.feedback
                except (ValueError, ValidationError) as error:
                    feedback = [str(error)]
                    journal.record("rejected", task_id, {"task_id": task_id, "seed_id": parent.seed_id,
                                   "decision": "reject", "reason_codes": [str(error).split(":")[0]],
                                   "feedback": feedback, "candidate_version": revision})
            journal.put(step_key + ":done", {"accepted": accepted is not None,
                         "candidate": accepted.model_dump(mode="json") if accepted else None})
            if accepted:
                parent = accepted
                successes += 1
        journal.put(layer_key + ":summary", {"frozen_leaves": frozen, "accepted_leaves": successes,
                                             "fully_expanded": successes == len(frozen) and bool(frozen)})
        if not successes:
            break
    return parent


def run(config, run_dir, retry_limited=False):
    from .export import export_dataset, deduplicate
    from .fixtures import FixtureProvider
    run_dir = Path(run_dir)
    with run_lock(run_dir), Journal(run_dir / "run.sqlite", frozen_config(config), config.budget) as journal:
        if retry_limited:
            journal.retry_limited()
        if journal.get("completed"):
            return export_dataset(journal, config, run_dir)
        journal.put("started_at", journal.get("started_at") or now())
        providers = {r: (FixtureProvider(getattr(config, r)) if config.mode == "fixture" else CodexProvider(getattr(config, r)))
                     for r in ("generator", "expander", "verifier", "solver")}
        gateway = ModelGateway(journal, providers)
        store = SourceStore(run_dir / "sources")
        try:
            if config.mode == "live":
                status = providers["generator"].preflight()
                old = journal.get("runtime")
                if old and old != status:
                    raise ValueError("Codex runtime changed; start a new run")
                journal.put("runtime", status)
            sources = collect_sources(config, store, journal)
            if not sources:
                raise ValueError("no captured source documents; configure accessible dated sources")
            graph_id, bundle, sources = generate_graph(config, sources, store, journal, gateway, "initial")
            finals = journal.get("final_candidates") or []
            prior = [c["task"]["question"] for c in finals]
            for index in range(config.max_seed_attempts):
                if len(deduplicate([Candidate.model_validate(c) for c in finals])[0]) >= config.target_tasks:
                    break
                checkpoint = f"family:{index}:done"
                # Reconcile the crash window between writing a final candidate
                # and marking its family done. Never regenerate an already saved family.
                if any(c["seed_id"] == f"seed-{index:04d}" for c in finals):
                    journal.put(checkpoint, True)
                    continue
                if journal.get(checkpoint):
                    continue
                seed = generate_seed(config, bundle, sources, graph_id, store, journal, gateway, index, prior)
                if seed:
                    final = expand_layers(seed, config, store, journal, gateway)
                    finals.append(final.model_dump(mode="json"))
                    prior.append(final.task.question)
                    journal.put("final_candidates", finals)
                journal.put(checkpoint, True)
            journal.put("completed", True)
            journal.put("status", "completed")
            journal.put("pause_reason", None)
        except (SubscriptionLimit, BudgetExceeded, UncertainCall, KeyboardInterrupt) as error:
            journal.put("status", "paused")
            journal.put("pause_reason", {"code": type(error).__name__, "message": str(error)})
        except (ValueError, OSError) as error:
            error_record(journal, "run", "run", error)
            journal.put("status", "failed")
        return export_dataset(journal, config, run_dir)
