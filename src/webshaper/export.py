"""Private/public separation, deduplication, grouped partitions and honest metrics."""
import json
import re
from collections import Counter
from pathlib import Path

from .models import Candidate, SCHEMA_VERSION, Source
from .query import canonical
from .sources import SourceStore
from .storage import digest, dump


def normalize(text):
    return " ".join(re.findall(r"\w+", text.casefold()))


def deduplicate(candidates):
    kept, dropped, by_text, by_query = [], [], {}, {}
    conflicted = set()
    for c in candidates:
        text = (normalize(c.task.question), str(c.task.as_of), dump(c.task.scope))
        key = (canonical(c.query), tuple(sorted(c.answer)), str(c.task.as_of), dump(c.task.scope))
        if text in by_text and by_text[text].answer != c.answer:
            old = by_text[text]
            conflicted.update((old.task.task_id, c.task.task_id))
            dropped.extend({"task_id": t.task.task_id, "decision": "reject", "reason_codes": ["conflicting_reference"]}
                           for t in (old, c) if not any(d["task_id"] == t.task.task_id for d in dropped))
        elif text in by_text or key in by_query:
            dropped.append({"task_id": c.task.task_id, "decision": "reject", "reason_codes": [
                "duplicate_question" if text in by_text else "duplicate_query_answer"],
                "duplicate_of": (by_text.get(text) or by_query[key]).task.task_id})
        else:
            kept.append(c)
            by_text[text], by_query[key] = c, c
    return [c for c in kept if c.task.task_id not in conflicted], dropped


def partitions(candidates, source_groups):
    parent = {c.task.task_id: c.task.task_id for c in candidates}
    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k
    def union(a, b):
        a, b = find(a), find(b)
        parent[max(a, b)] = min(a, b)
    owners = {}
    for c in candidates:
        # Lineage, any shared primary answer entity, or duplicate source content.
        groups = [("seed", c.seed_id)] + [("answer", a) for a in c.answer]
        groups += [("source", h) for h in source_groups.get(c.task.task_id, set())]
        for group in groups:
            if group in owners:
                union(c.task.task_id, owners[group])
            owners[group] = c.task.task_id
    result = {}
    for c in candidates:
        bucket = int(digest(find(c.task.task_id))[:8], 16) % 100
        result[c.task.task_id] = "train" if bucket < 80 else ("validation" if bucket < 90 else "test")
    return result


def source_clusters(graphs, store):
    sources = {s["source_id"]: s for g in graphs for s in g["sources"]}
    parent = {s: s for s in sources}
    def find(s):
        while parent[s] != s:
            s = parent[s]
        return s
    shingles = {}
    for sid, s in sources.items():
        text = store.read(Source.model_validate(s))
        words = normalize(text).split()
        shingles[sid] = {tuple(words[i:i+5]) for i in range(max(1, len(words)-4))}
    ids = sorted(sources)
    for i, a in enumerate(ids):
        for b in ids[i+1:]:
            x, y = shingles[a], shingles[b]
            if (sources[a]["content_hash"] == sources[b]["content_hash"]
                    or sources[a]["url_or_local_origin"] == sources[b]["url_or_local_origin"]
                    or len(x & y) / max(1, len(x | y)) >= .9):
                ar, br = find(a), find(b)
                parent[max(ar, br)] = min(ar, br)
    return {sid: find(sid) for sid in ids}


def write_jsonl(path, records):
    data = "".join(dump(r) + "\n" for r in records)
    atomic_write(path, data)


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(data)
    temp.replace(path)


def export_dataset(journal, config, root):
    output = Path(root) / "export"
    output.mkdir(parents=True, exist_ok=True)
    all_final = [Candidate.model_validate(c) for c in (journal.get("final_candidates") or [])]
    candidates, duplicates = deduplicate(all_final)
    graphs = journal.records("graphs")
    graph_map = {g["graph_id"]: g for g in graphs}
    store = SourceStore(Path(root) / "sources")
    clusters = source_clusters(graphs, store)
    groups = {c.task.task_id: {clusters[s["source_id"]] for s in graph_map[c.graph_id]["sources"]} for c in candidates}
    partition = partitions(candidates, groups)
    validations = journal.records("validations")
    reviews = journal.records("manual_reviews")
    reviewed = {r["task_id"]: r for r in reviews}
    for v in validations:
        if v["task_id"] in reviewed:
            v["audit_status"] = reviewed[v["task_id"]]["decision"]
    manually_rejected = {r["task_id"] for r in reviews if r["decision"] == "rejected"}
    candidates = [c for c in candidates if c.task.task_id not in manually_rejected]
    references, provenance = [], []
    for c in candidates:
        graph = graph_map[c.graph_id]
        reference = {"task_id": c.task.task_id, "answer_entities_or_rows": c.answer, "cell_evidence": c.cell_evidence,
                     "reference_query": c.query.model_dump(mode="json"), "candidate_universe": c.task.scope.candidate_universe,
                     "candidate_decisions": c.candidate_decisions, "actual_layer": c.layer, "graph_id": c.graph_id,
                     "grading": "exact canonical entity set; source-backed aliases only", "data_mode": config.mode}
        references.append(reference)
    for record in journal.records("candidates"):
        c = Candidate.model_validate(record)
        graph = graph_map[c.graph_id]
        provenance.append({"task_id": c.task.task_id, "seed_id": c.seed_id, "parent_id": c.parent_id,
                           "layer": c.layer, "candidate_version": c.version, "expanded_leaf": c.expanded_leaf,
                           "intermediate_answer": c.intermediate_answer,
                           "subquery": c.subquery.model_dump(mode="json") if c.subquery else None,
                           "graph_id": c.graph_id, "prompt_version": journal.get("frozen")["config"]["prompt_version"],
                           "model_config": {r: getattr(config, r).model_dump(mode="json") for r in ("generator", "expander", "verifier", "solver")},
                           "source_hashes": {s["source_id"]: s["content_hash"] for s in graph["sources"]},
                           "data_mode": config.mode})
    # All reference-bearing files remain private; public/ contains only X and permitted source text.
    tasks = [c.task.model_dump(mode="json") for c in candidates]
    write_jsonl(output / "tasks.jsonl", tasks)
    write_jsonl(output / "public" / "tasks.jsonl", tasks)
    write_jsonl(output / "references.jsonl", references)
    write_jsonl(output / "provenance.jsonl", provenance)
    write_jsonl(output / "validation.jsonl", validations)
    write_jsonl(output / "attempts.jsonl", journal.records("candidate_attempts"))
    write_jsonl(output / "manual_reviews.jsonl", reviews)
    write_jsonl(output / "graphs.jsonl", graphs)
    write_jsonl(output / "errors.jsonl", journal.records("errors"))
    rejected = journal.records("rejected") + duplicates + [{"task_id": t, "decision": "reject",
                "reason_codes": ["manual_review_rejected"]} for t in manually_rejected]
    write_jsonl(output / "rejected.jsonl", rejected)
    sources = {s.source_id: s.model_dump(mode="json") for s in store.all()}
    for source in sources.values():
        store.read(Source.model_validate(source))
    write_jsonl(output / "sources.jsonl", list(sources.values()))
    public_corpora = []
    for gid in sorted({c.graph_id for c in candidates}):
        for s in graph_map[gid]["sources"]:
            public_corpora.append({"corpus_id": gid, "source_id": s["source_id"], "url": s["url_or_local_origin"],
                                  "title": s["title"], "published_at": s["published_at"],
                                  "text": store.read(Source.model_validate(s)) if s["redistributable"] else None,
                                  "access": "redistributable" if s["redistributable"] else "authorized_source_access_required"})
    write_jsonl(output / "public" / "corpus.jsonl", public_corpora)
    # Usage export omits prompts/results and never includes environment or authentication material.
    calls = []
    for call in journal.calls():
        entry = {k: v for k, v in call.items() if k != "result"}
        if call["result"]:
            entry["call_id"] = json.loads(call["result"]).get("metadata", {}).get("call_id")
        calls.append(entry)
    write_jsonl(output / "usage.jsonl", calls)
    attempts = [a for v in validations for a in v["solver_attempts"]]
    browsing = [a for a in attempts if a["mode"] == "browsing"]
    closed = [a for a in attempts if a["mode"] == "closed_book"]
    support_audits = journal.records("support_audits")
    support = Counter(c["status"] for a in support_audits for c in a["claim_support"])
    usage = journal.usage()
    errors = journal.records("errors")
    attempted_ids = {c["task"]["task_id"] for c in journal.records("candidates")}
    attempted_ids.update(r["task_id"] for r in journal.records("rejected"))
    attempted_ids.update(r["task_id"] for r in journal.records("candidate_attempts"))
    solver_responses = sum(c["role"] == "solver:solver" and c["status"] == "complete" for c in calls)
    stats = {"data_mode": config.mode, "status": journal.get("status"), "accepted_tasks": len(candidates),
             "target_tasks": config.target_tasks, "target_reached": len(candidates) >= config.target_tasks,
             "attempted_versions": len(attempted_ids), "evaluated_versions": len(validations),
             "rejection_records": len(rejected),
             "rejection_reasons": dict(Counter(code for r in rejected for code in r["reason_codes"])),
             "source_count": len(sources), "source_categories": dict(Counter(s["category"] for s in sources.values())),
             "error_records": len(errors),
             "source_errors": sum(e["stage"] in ("source_capture", "source_date") for e in errors),
             "extraction_errors": sum(e["stage"] == "extraction" for e in errors),
             "answer_support_audit": dict(support),
             "browsing_attempts": len(browsing), "browsing_success_rate": sum(a["success"] for a in browsing) / len(browsing) if browsing else None,
             "completed_solver_responses": solver_responses,
             "completed_solver_grades": sum(c["role"] == "verifier:grade" and c["status"] == "complete" for c in calls),
             "solver_responses_without_validation_record": max(0, solver_responses - len(attempts)),
             "closed_book_attempts": len(closed), "closed_book_success_rate": sum(a["correct"] for a in closed) / len(closed) if closed else None,
             "depth_distribution": dict(Counter(str(c.layer) for c in candidates)),
             "duplicate_rate": len(duplicates) / len(all_final) if all_final else 0,
             "manual_reviews_pending": sum(c.task.task_id not in reviewed for c in candidates) if config.mode == "live" else 0,
             "usage": usage, "cost_per_accepted_task_usd": usage["cost_usd"] / len(candidates) if candidates else None,
             "shared_background_sources": [], "partition_counts": dict(Counter(partition.get(c.task.task_id) for c in candidates))}
    manifest = {"schema_version": SCHEMA_VERSION, "stats": stats, "data_mode": config.mode,
                "configuration": config.model_dump(mode="json"), "frozen": journal.get("frozen"),
                "runtime": journal.get("runtime"), "pause_reason": journal.get("pause_reason"),
                "exporter_hash": digest(Path(__file__).read_bytes()),
                "started_at": journal.get("started_at"), "partitions": {c.task.task_id: partition[c.task.task_id] for c in candidates},
                "source_store": "../sources", "private_files": ["references.jsonl", "graphs.jsonl", "provenance.jsonl", "validation.jsonl"],
                "file_hashes": {p.name: digest(p.read_bytes()) for p in output.glob("*.jsonl")}}
    atomic_write(output / "manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
    label = "FICTIONAL SCRIPTED FIXTURE — NOT REAL GENERATED COMPANY DATA" if config.mode == "fixture" else "LIVE SUBSCRIPTION GENERATION — MANUAL PILOT REVIEW REQUIRED"
    report = f"# Quality report\n\n{label}\n\n```json\n{json.dumps(stats, indent=2, sort_keys=True)}\n```\n\n"
    report += ("Counts cover all candidate versions, including failed revisions and expansions. Source failures are in errors.jsonl.\n\n"
               "Success rates use completed validation records only. During a pause, completed solver responses "
               "without a final validation record are counted separately; responses remain cached in run.sqlite "
               "and candidate attempts remain in attempts.jsonl. They are not implicitly graded as failures.\n\n"
               "Correctness gates and independent semantic checks are separate from model-relative difficulty screens. "
               "Closed-book failure does not prove that browsing is necessary. Structural layer is measured separately "
               "from empirical difficulty. A partially expanded layer is not a fully expanded graph.\n\n"
               "All lineages, shared answers and near-duplicate source pages are grouped. This conservative grouping "
               "can collapse a small corpus into one partition; no independent benchmark is claimed. "
               "Source similarity uses five-word shingles at Jaccard >= 0.90, not an embedding guarantee.\n\n"
               "No separate API/search charges are enabled. Subscription usage is recorded in tokens; subscription fees "
               "and optional account credits are not priced here. CLI tokens are observed after turns, so token "
               "reservations are conservative scheduling bounds, not a hard per-turn token limit. "
               "Interrupted calls remain uncertain and are never automatically repeated.\n\n"
               "The first live pilot requires human review of every accepted task. No training/RL was run and no "
               "model-improvement claim is made. Source text with unknown reuse permission is withheld from public/.\n")
    atomic_write(output / "quality_report.md", report)
    return stats
