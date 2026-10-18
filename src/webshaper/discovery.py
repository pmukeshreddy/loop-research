"""Private, observed-web company discovery and evidence-readiness qualification."""
from collections import Counter
from itertools import combinations
import re
from urllib.parse import urldefrag, urlsplit

from pydantic import Field

from .generation import source_documents
from .models import Check, Record, SourceInput
from .query import eligible_facts
from .storage import digest
from .web_validation import action_kind, completed_events

INDUSTRIES = ["enterprise_software", "financial_services", "healthcare", "biotechnology", "energy",
              "transportation", "manufacturing", "agriculture", "education", "consumer", "telecom", "space"]
REGIONS = ["north_america", "latin_america", "europe", "africa", "middle_east", "south_asia", "east_asia", "oceania"]
STAGES = ["bootstrapped", "pre_seed_seed", "series_a_b", "growth", "public", "acquired"]
FAMILIES = {"has_funding_event": "funding", "round_type": "funding", "investor": "investors",
            "portfolio_company": "investors", "founded_by": "founders", "builds": "products",
            "product_category": "products", "has_acquisition_event": "acquisitions",
            "acquired_company": "acquisitions", "has_partnership_event": "partnerships",
            "partner_company": "partnerships", "partnership_product": "partnerships"}


class CompanyProposal(Record):
    name: str = Field(min_length=1)
    official_url: str
    industry: str
    region: str
    funding_stage: str
    primary_urls: list[str] = Field(min_length=1, max_length=20)
    rationale: str


class CompanyDiscovery(Record):
    companies: list[CompanyProposal] = Field(max_length=50)
    limitations: str


class CompanySources(Record):
    urls: list[str] = Field(max_length=30)
    limitations: str


class AttributeSupport(Record):
    attribute: str
    source_id: str
    quote: str = Field(min_length=1)


class CompanyAssessment(Record):
    company_entity_id: str
    industry: str
    region: str
    funding_stage: str
    primary_source_ids: list[str]
    supports: list[AttributeSupport]
    checks: list[Check]
    feedback: str


def company_key(url):
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.port:
        raise ValueError("company official URL must be a public HTTPS origin")
    return parts.hostname.lower().removeprefix("www.")


def identity_keys(proposal, entity):
    """Conservative verified identity/alias keys; uncertainty never creates extra company credit."""
    legal_suffixes = {"inc", "incorporated", "ltd", "limited", "llc", "corp", "corporation", "plc",
                      "gmbh", "pte", "pvt", "sa", "ag"}
    keys = {"domain:" + proposal["official_domain"]}
    for name in [proposal["name"], entity.name, *entity.aliases]:
        tokens = re.findall(r"\w+", name.casefold())
        while tokens and tokens[-1] in legal_suffixes:
            tokens.pop()
        if tokens:
            keys.add("name:" + " ".join(tokens))
    for identifier in entity.identifiers:
        parsed = urlsplit(identifier)
        if parsed.scheme in ("https", "http") and parsed.hostname:
            keys.add("url:" + parsed.hostname.lower().removeprefix("www.") + parsed.path.rstrip("/"))
        else:
            keys.add("id:" + identifier.strip().casefold())
    return keys


def observed_urls(observation):
    urls = set(observation.get("visited_urls", []))
    for event in completed_events(observation):
        for result in event.get("raw_event", {}).get("item", {}).get("results", []):
            if isinstance(result, dict) and isinstance(result.get("url"), str):
                urls.add(result["url"])
    return {urldefrag(url)[0] for url in urls if url.startswith("https://") and urlsplit(url).hostname}


def diversity_order(proposals, selected):
    counts = {field: Counter(s[field] for s in selected) for field in ("industry", "region", "funding_stage")}
    return sorted(proposals, key=lambda p: (sum(counts[f][p[f]] for f in counts), p["company_id"]))


def discover_batch(config, gateway, journal, batch):
    from .pipeline import error_record
    key = f"discovery:{batch}"
    if journal.get(key + ":done"):
        return
    known = journal.records("companies")
    payload = journal.get(key + ":input") or {
        "count": min(config.campaign.discovery_batch_size, config.campaign.max_company_candidates - len(known)),
        "as_of": str(config.as_of), "excluded_companies": known,
        "coverage_targets": {"industries": INDUSTRIES, "regions": REGIONS, "funding_stages": STAGES},
        "verified_coverage": [q for q in journal.records("company_qualifications") if q["qualified"]],
    }
    journal.put(key + ":input", payload)
    response, observation = gateway.call_observed("generator", "company_discovery", payload, CompanyDiscovery, key, web=True)
    journal.record("company_discovery", key, {"batch": batch, "response": response.model_dump(mode="json"),
                                             "call_id": key, "observed_urls": sorted(observed_urls(observation))})
    if observation.get("failure_code") or not any(action_kind(e) == "search" for e in completed_events(observation)):
        raise ValueError("company_discovery_missing_observed_search")
    observed = observed_urls(observation)
    identities = {p["official_domain"] for p in known}
    names = {" ".join(p["name"].casefold().split()) for p in known}
    for proposal in response.companies[:config.campaign.discovery_batch_size]:
        try:
            domain = company_key(proposal.official_url)
            name = " ".join(proposal.name.casefold().split())
            if domain in identities or name in names:
                raise ValueError("duplicate_company_identity")
            urls = sorted({urldefrag(u)[0] for u in proposal.primary_urls} & observed)
            if not urls:
                raise ValueError("company_has_no_observed_source_url")
            company_id = "company-" + digest(domain)[:12]
            record = {**proposal.model_dump(mode="json"), "primary_urls": urls, "company_id": company_id,
                      "official_domain": domain, "discovery_call_id": key, "metadata_status": "provisional"}
            journal.record("companies", company_id, record)
            identities.add(domain)
            names.add(name)
            if len(identities) >= config.campaign.max_company_candidates:
                break
        except ValueError as error:
            error_record(journal, "company_discovery", key + ":" + proposal.name, error)
    journal.put(key + ":done", True)


def readiness(config, proposal, bundle, sources, assessment, store):
    """Deterministic support checks; graph connectivity is readiness, never web uniqueness."""
    reasons = []
    checks = {c.name: c.status for c in assessment.checks}
    for name in ("identity", "distinct_identity", "primary_sources", "classification", "temporal_support"):
        if checks.get(name) != "pass":
            reasons.append("company_" + name)
    source_map = {s.source_id: s for s in sources}
    valid_support = set()
    for support in assessment.supports:
        source = source_map.get(support.source_id)
        if source and support.quote in store.read(source) and source.published_at is not None and (
                config.scope.allow_retrospective or source.published_at <= config.as_of):
            valid_support.add(support.attribute)
        else:
            reasons.append("company_invalid_attribute_evidence")
    for attr in ("identity", "industry", "region", "funding_stage"):
        if attr not in valid_support:
            reasons.append("company_unsupported_" + attr)
    for field, vocabulary in (("industry", INDUSTRIES), ("region", REGIONS), ("funding_stage", STAGES)):
        if getattr(assessment, field) not in vocabulary:
            reasons.append("company_unknown_" + field)
    entities = {e.entity_id: e for e in bundle.entities}
    identity = entities.get(assessment.company_entity_id)
    if not identity or identity.kind != "company" or identity.resolution_status != "resolved":
        reasons.append("company_unresolved_identity")
    facts = [f for f in eligible_facts(bundle, sources, config.as_of, config.scope.allow_retrospective)
             if f.polarity == "positive"]
    connected = {assessment.company_entity_id}
    # Literal categories/dates cannot connect unrelated company subgraphs.
    traverse_kinds = {"company", "investor", "person", "product", "funding_event", "acquisition_event", "partnership_event"}
    for _ in range(len(entities)):
        added = {n for f in facts if f.subject_id in connected or f.object_id_or_value in connected
                 for n in (f.subject_id, f.object_id_or_value) if entities[n].kind in traverse_kinds}
        if added <= connected:
            break
        connected |= added
    related = [f for f in facts if f.subject_id in connected]
    evidence = {e.evidence_id: e for e in bundle.evidence}
    used_sources = {evidence[e].source_id for f in related for e in f.evidence_ids}
    primary = set(assessment.primary_source_ids) & used_sources
    primary = {sid for sid in primary if sid in source_map and "primary:" + sid in valid_support
               and source_map[sid].category in ("primary", "fixture" if config.mode == "fixture" else "primary")}
    families = sorted({FAMILIES[f.predicate] for f in related if f.predicate in FAMILIES})
    patterns = [list(c) for size in range(1, len(families) + 1) for c in combinations(families, size)]
    minimums = ((len(primary), config.campaign.min_primary_sources, "insufficient_primary_sources"),
                (len(families), config.campaign.min_relationship_families, "insufficient_relationship_families"),
                (len(connected) - 1, config.campaign.min_connected_entities, "insufficient_connected_entities"),
                (len(patterns), config.campaign.min_question_patterns, "insufficient_question_patterns"))
    reasons.extend(reason for count, minimum, reason in minimums if count < minimum)
    return {"company_id": proposal["company_id"], "name": proposal["name"],
            "official_domain": proposal["official_domain"], "company_entity_id": assessment.company_entity_id,
            "industry": assessment.industry, "region": assessment.region, "funding_stage": assessment.funding_stage,
            "qualified": not reasons, "reason_codes": sorted(set(reasons)),
            "primary_source_ids": sorted(primary), "relationship_families": families,
            "connected_entities": sorted(connected - {assessment.company_entity_id}), "question_patterns": patterns,
            "assessment": assessment.model_dump(mode="json")}


def qualify_company(config, proposal, store, journal, gateway):
    from .pipeline import collect_sources, error_record, generate_graph
    cid = proposal["company_id"]
    saved = journal.record_value("company_qualifications", cid)
    if saved is not None:
        return saved
    urls = set(proposal["primary_urls"])
    for prior in journal.records("company_source_searches"):
        if prior["company_id"] == cid:
            urls |= set(prior["response"]["urls"]) & set(prior["observed_urls"])
    saved_urls = journal.get(cid + ":qualification:initial_urls")
    if saved_urls is not None:
        urls = set(saved_urls)
    else:
        journal.put(cid + ":qualification:initial_urls", sorted(urls))
    sources = []
    failure = None
    for attempt in range(-1, config.campaign.source_search_attempts):
        key = cid + (":sources:cached" if attempt == -1 else f":sources:{attempt}")
        try:
            if attempt >= 0:
                payload = journal.get(key + ":input") or {
                    "company": proposal, "as_of": str(config.as_of), "existing_urls": sorted(urls),
                    "relationship_families": sorted(set(FAMILIES.values())), "prior_feedback": failure,
                    "unusable_sources": [e for e in journal.records("errors") if e["identifier"] in urls],
                    "captured_dates": [{"url": s.url_or_local_origin, "published_at": str(s.published_at),
                                        "status": s.date_status} for s in sources],
                }
                journal.put(key + ":input", payload)
                response, observation = gateway.call_observed("generator", "company_sources", payload, CompanySources, key, web=True)
                journal.record("company_source_searches", key, {"company_id": cid, "call_id": key,
                                "response": response.model_dump(mode="json"), "observed_urls": sorted(observed_urls(observation))})
                if observation.get("failure_code") or not any(action_kind(e) == "search" for e in completed_events(observation)):
                    raise ValueError("company_sources_missing_observed_search")
                urls |= {urldefrag(u)[0] for u in response.urls} & observed_urls(observation)
            domains = sorted({urlsplit(u).hostname for u in urls})
            local_config = config.model_copy(update={"allowed_domains": domains, "crawl_depth": 0})
            sources = collect_sources(local_config, store, journal, [SourceInput(origin=u) for u in sorted(urls)])
            sources = list({s.source_id: s for s in sources}.values())
            from .sources import eligible_sources
            dated = eligible_sources(sources, config.as_of, config.scope.allow_retrospective)
            if len(dated) < config.campaign.min_primary_sources:
                raise ValueError("insufficient_dated_captured_sources")
            graph_id, bundle, sources = generate_graph(local_config, dated, store, journal, gateway, key)
            assessment = gateway.call("verifier", "company_assess", {
                "company": proposal, "as_of": str(config.as_of), "documents": source_documents(sources, store),
                "graph": bundle.model_dump(mode="json"),
                "previous_companies": [{k: q.get(k) for k in ("company_id", "name", "official_domain", "identity_keys")}
                                       for q in journal.records("company_qualifications") if q["qualified"]],
                "vocabulary": {"industry": INDUSTRIES, "region": REGIONS, "funding_stage": STAGES},
            }, CompanyAssessment, key + ":assess")
            result = readiness(config, proposal, bundle, sources, assessment, store)
            result.update(graph_id=graph_id, source_ids=[s.source_id for s in sources])
            if result["qualified"]:
                # A source-backed alias/identifier overlap cannot fill a second company slot.
                identity = next(e for e in bundle.entities if e.entity_id == assessment.company_entity_id)
                keys = identity_keys(proposal, identity)
                for previous in journal.records("company_qualifications"):
                    if previous["qualified"] and keys & set(previous.get("identity_keys", [])):
                        result.update(qualified=False, reason_codes=["duplicate_verified_company_identity"])
                result["identity_keys"] = sorted(keys)
                journal.record("company_qualification_attempts", key, result)
                journal.record("company_qualifications", cid, result)
                return result
            journal.record("company_qualification_attempts", key, result)
            failure = ", ".join(result["reason_codes"])
        except ValueError as error:
            failure = str(error)
            error_record(journal, "company_qualification", key, error, company_id=cid)
    result = {"company_id": cid, "name": proposal["name"], "qualified": False,
              "reason_codes": ["evidence_qualification_failed"], "feedback": failure,
              "source_ids": [s.source_id for s in sources]}
    journal.record("company_qualifications", cid, result)
    return result
