"""Resumable 50 x 5 scheduler. Only fully validated, diverse finals earn quota credit."""
from collections import Counter
from urllib.parse import urlsplit

from .discovery import discover_batch, diversity_order, qualify_company
from .diversity import diversity_check
from .models import Candidate


def accepted_finals(journal):
    from .export import deduplicate
    rejected = {r["task_id"] for r in journal.records("manual_reviews") if r["decision"] == "rejected"}
    finals = [Candidate.model_validate(c) for c in journal.get("final_candidates") or []]
    return [c for c in deduplicate(finals)[0] if c.task.task_id not in rejected]


def run_slot(config, company, slot, store, journal, gateway):
    from .pipeline import expand_layers, generate_seed, load_graph
    cid = company["company_id"]
    depth = config.campaign.depth_targets[slot]
    key = cid + f":slot:{slot}"
    # Reconcile the final-before-slot-checkpoint crash window from authoritative finals.
    if any(c.company_id == cid and c.question_slot == slot for c in accepted_finals(journal)):
        journal.put(key + ":done", True)
        return
    if journal.get(key + ":done"):
        return
    graph_id = company["graph_id"]
    bundle, sources = load_graph(journal, graph_id)
    local_config = config.model_copy(update={"layers": depth, "allowed_domains": sorted({
        urlsplit(s.url_or_local_origin).hostname
        for s in sources if s.url_or_local_origin.startswith("https://")})})
    for attempt in range(config.campaign.max_attempts_per_slot):
        seed_id = key + f":attempt:{attempt}"
        if journal.get(seed_id + ":done"):
            continue
        prior = accepted_finals(journal)
        context = {"company_id": cid, "company_entity_id": company["company_entity_id"],
                   "question_slot": slot, "requested_depth": depth,
                   "relationship_focus": company["question_patterns"][(slot + attempt) % len(company["question_patterns"])],
                   "available_relationships": company["relationship_families"],
                   "prior_requirements": [{"question": c.task.question, "query": c.query.model_dump(mode="json")}
                                          for c in prior if c.company_id == cid],
                   "previous_failures": [r for r in journal.records("rejected") if r.get("seed_id", "").startswith(cid)][-20:]}
        saved = journal.get(seed_id + ":input")
        if saved:
            context = saved["context"]
            prior = [Candidate.model_validate(c) for c in saved["prior"]]
        else:
            journal.put(seed_id + ":input", {"context": context, "prior": [c.model_dump(mode="json") for c in prior]})
        journal.record("company_allocations", seed_id, {"company_id": cid, "seed_id": seed_id,
                       "slot": slot, "attempt": attempt, "requested_depth": depth})
        seed = generate_seed(local_config, bundle, sources, graph_id, store, journal, gateway,
                             0, [c.task.question for c in prior], seed_id=seed_id,
                             company_context=context, prior_candidates=prior)
        final = expand_layers(seed, local_config, store, journal, gateway) if seed else None
        reason = None
        if final:
            if final.answer != [company["company_entity_id"]]:
                reason = "campaign_reference_mismatch"
            elif final.layer < depth:
                reason = "campaign_depth_shortfall"
            elif not diversity_check(final, prior, gateway, journal, "final"):
                reason = "near_duplicate_research_requirements"
            else:
                finals = journal.get("final_candidates") or []
                finals.append(final.model_dump(mode="json"))
                journal.put("final_candidates", finals)
                journal.put(seed_id + ":done", True)
                journal.put(key + ":done", True)
                return
            journal.record("rejected", seed_id + ":quota", {"task_id": final.task.task_id,
                           "seed_id": seed_id, "decision": "reject", "reason_codes": [reason],
                           "feedback": ["Validated parent/proposal does not satisfy this campaign slot."],
                           "candidate_version": final.version})
        journal.put(seed_id + ":done", True)
    journal.put(key + ":done", True)


def run_campaign(config, store, journal, gateway):
    """One shared gateway/budget; give each selected company slot zero before later slots."""
    from .pipeline import error_record
    selected = journal.get("selected_companies") or []
    for company in selected:
        run_slot(config, company, 0, store, journal, gateway)
    for batch in range(config.campaign.max_discovery_batches):
        if len(selected) >= config.campaign.target_companies:
            break
        if not journal.get(f"discovery:{batch}:done") and len(journal.records("companies")) >= config.campaign.max_company_candidates:
            break
        try:
            discover_batch(config, gateway, journal, batch)
        except ValueError as error:
            # Malformed completed responses are deterministic failures; limits/unknown calls propagate.
            key = f"discovery:{batch}"
            error_record(journal, "company_discovery_batch", key, error)
            journal.record("company_discovery_failures", key, {"batch": batch, "reason": str(error)})
            journal.put(key + ":done", True)
        frozen_queue = journal.get(f"discovery:{batch}:queue")
        if frozen_queue is None:
            processed = {q["company_id"] for q in journal.records("company_qualifications")}
            pending = [p for p in journal.records("companies") if p["company_id"] not in processed]
            frozen_queue = [p["company_id"] for p in diversity_order(pending, selected)]
            journal.put(f"discovery:{batch}:queue", frozen_queue)
        proposals = {p["company_id"]: p for p in journal.records("companies")}
        for cid in frozen_queue:
            if len(selected) >= config.campaign.target_companies and cid not in {s["company_id"] for s in selected}:
                break
            company = qualify_company(config, proposals[cid], store, journal, gateway)
            if not company["qualified"]:
                continue
            if cid not in {s["company_id"] for s in selected}:
                selected.append(company)
                journal.put("selected_companies", selected)
            run_slot(config, company, 0, store, journal, gateway)
    for slot in range(1, config.campaign.questions_per_company):
        for company in selected:
            run_slot(config, company, slot, store, journal, gateway)


def campaign_report(journal, config, candidates, attempts, calls):
    from .export import observed_browsing
    cfg = config.campaign
    selected = journal.get("selected_companies") or []
    qualifications = {q["company_id"]: q for q in journal.records("company_qualifications")}
    allocations = journal.records("company_allocations")
    rejections = journal.records("rejected")
    rows = []
    for company in journal.records("companies"):
        cid = company["company_id"]
        accepted = [c for c in candidates if c.company_id == cid]
        allocation = [a for a in allocations if a["company_id"] == cid]
        seeds = {a["seed_id"] for a in allocation}
        failed = [r for r in rejections if r.get("seed_id") in seeds]
        own_attempts = [a for a in attempts if (a.get("call_id") or (a.get("observation") or {}).get("call_id", "")).startswith(cid)]
        browsing = [a for a in own_attempts if a["mode"] == "open_web"]
        closed = [a for a in own_attempts if a["mode"] == "closed_book"]
        own_calls = [c for c in calls if (c.get("call_id") or "").startswith(cid)]
        qualification = qualifications.get(cid, {})
        selected_here = cid in {c["company_id"] for c in selected}
        rows.append({"company_id": cid, "name": company["name"], "official_domain": company["official_domain"],
                     "qualified": qualification.get("qualified", False), "selected": selected_here,
                     "classification": {f: qualification.get(f) for f in ("industry", "region", "funding_stage")},
                     "accepted_questions": len(accepted), "target_questions": cfg.questions_per_company,
                     "shortfall": cfg.questions_per_company - len(accepted),
                     "shortfall_status": "fulfilled" if len(accepted) == cfg.questions_per_company else
                         "evidence_insufficient" if qualification and not qualification["qualified"] else
                         "paused" if journal.get("status") == "paused" else "attempts_exhausted" if selected_here else "not_selected",
                     "qualification_reasons": qualification.get("reason_codes", []),
                     "qualification_feedback": qualification.get("feedback"),
                     "allocated_seed_attempts": len(allocation),
                     "candidate_versions": sum(c.get("company_id") == cid for c in journal.records("candidates")),
                     "depth_distribution": dict(Counter(str(c.layer) for c in accepted)),
                     "rejection_reasons": dict(Counter(code for r in failed for code in r["reason_codes"])),
                     "open_web_attempts": len(browsing), "observed_browsing_attempts": sum(observed_browsing(a) for a in browsing),
                     "verified_browsing_successes": sum(a.get("success", False) and observed_browsing(a) for a in browsing),
                     "browsing_success_rate": sum(a.get("success", False) and observed_browsing(a) for a in browsing) / len(browsing) if browsing else None,
                     "browsing_failure_categories": dict(Counter(a["failure_category"] for a in browsing if a.get("failure_category"))),
                     "closed_book_attempts": len(closed), "closed_book_correct": sum(a.get("correct", False) for a in closed),
                     "usage": {"calls": len(own_calls), "tokens": sum(c["tokens"] or 0 for c in own_calls),
                               "web_actions": sum(c["searches"] for c in own_calls),
                               "latency_seconds": sum(c["latency"] for c in own_calls)},
                     "task_ids": [c.task.task_id for c in accepted]})
    distributions = {f: dict(Counter(c[f] for c in selected)) for f in ("industry", "region", "funding_stage")}
    minimums = {"industry": cfg.min_industries, "region": cfg.min_regions, "funding_stage": cfg.min_funding_stages}
    gaps = {f: max(0, minimums[f] - len(distributions[f])) for f in minimums}
    return {"target_companies": cfg.target_companies, "target_questions": config.target_tasks,
            "discovered_companies": len(rows), "qualified_companies": sum(q["qualified"] for q in qualifications.values()),
            "selected_companies": len(selected), "unfilled_company_slots": cfg.target_companies - len(selected),
            "accepted_questions": len(candidates), "question_shortfall": config.target_tasks - len(candidates),
            "companies_with_five_or_configured_quota": sum(r["accepted_questions"] == cfg.questions_per_company for r in rows),
            "target_reached": len(selected) == cfg.target_companies and not any(gaps.values())
                and sum(r["accepted_questions"] == cfg.questions_per_company for r in rows) == cfg.target_companies,
            "verified_coverage": distributions, "coverage_shortfalls": gaps,
            "qualification_rejections": dict(Counter(reason for q in qualifications.values() for reason in q["reason_codes"])),
            "discovery_failures": journal.records("company_discovery_failures"),
            "companies": rows, "depth_targets": cfg.depth_targets,
            "pause_reason": journal.get("pause_reason"), "effective_budget": journal.budget.model_dump(mode="json"),
            "usage": journal.usage(), "usage_note": "Per-company calls use stable call-ID prefixes; discovery/unassigned usage remains in total usage."}
