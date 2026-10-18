"""Campaign tests use synthetic structures and SCRIPTED OFFLINE providers only."""
import pytest


def small_campaign(**changes):
    from webshaper.models import CampaignConfig
    return CampaignConfig(**{"target_companies": 1, "questions_per_company": 1, "depth_targets": [0],
                             "min_industries": 1, "min_regions": 1, "min_funding_stages": 1,
                             "max_discovery_batches": 1, "max_attempts_per_slot": 1, **changes})


def test_campaign_contract_requires_open_web_and_matching_quotas():
    from webshaper.models import CampaignConfig, RunConfig
    campaign = CampaignConfig()
    assert campaign.target_companies * campaign.questions_per_company == 250
    assert campaign.depth_targets == [0, 1, 1, 2, 2]
    with pytest.raises(ValueError, match="campaign"):
        RunConfig(as_of="2025-12-31", campaign=campaign)
    config = RunConfig(as_of="2025-12-31", research_mode="open_web", target_tasks=250,
                       layers=2, campaign=campaign)
    assert config.sources == []
    with pytest.raises(ValueError):
        CampaignConfig(depth_targets=[0])


def test_discovery_accepts_only_observed_https_sources_and_deduplicates_companies():
    from webshaper.discovery import company_key, observed_urls
    assert company_key("https://www.Acme.example/about") == company_key("https://acme.example/")
    observation = {"visited_urls": ["https://acme.example/news", "file:///private"], "web_events": [
        {"status": "completed", "raw_event": {"item": {"results": [
            {"url": "https://investor.example/acme"}]}}}]}
    assert observed_urls(observation) == {"https://acme.example/news", "https://investor.example/acme"}
    assert "https://invented.example" not in observed_urls(observation)


def test_question_diversity_ignores_paraphrases_and_changed_literal_clues():
    from webshaper.diversity import requirement_similarity
    from webshaper.models import Query
    a = Query(branches=[[{"subject": "?company", "predicate": "builds", "object": "productA"},
                        {"subject": "?company", "predicate": "founded_by", "object": "personA"}]])
    b = Query(branches=[[{"subject": "?c", "predicate": "builds", "object": "productB"},
                        {"subject": "?c", "predicate": "founded_by", "object": "personB"}]], target="?c")
    assert requirement_similarity(a, b) == 1
    b.branches[0][1].predicate = "headquartered_in"
    assert requirement_similarity(a, b) < .8


def test_budget_extensions_are_explicit_idempotent_and_keep_prior_usage(tmp_path):
    from webshaper.models import Budget, BudgetExtension
    from webshaper.storage import BudgetExceeded, Journal
    path = tmp_path / "run.sqlite"
    budget = Budget(max_calls=1, max_tokens=100, max_searches=0)
    extension = BudgetExtension(authorization_id="explicit-test", additional_calls=1,
                                additional_tokens=100, additional_searches=0)
    with Journal(path, {}, budget) as journal:
        journal.reserve("one", "test", 0, 100, 0)
        journal.complete("one", {}, 0, 100)
        with pytest.raises(BudgetExceeded):
            journal.reserve("two", "test", 0, 100, 0)
        journal.authorize_budget(extension)
        journal.authorize_budget(extension)
        journal.reserve("two", "test", 0, 100, 0)
        journal.complete("two", {}, 0, 100)
    with Journal(path, {}, budget) as journal:
        assert journal.budget.max_tokens == 200
        assert journal.usage()["calls"] == 2
        with pytest.raises(BudgetExceeded):
            journal.reserve("three", "test", 0, 100, 0)
        with pytest.raises(ValueError, match="immutable"):
            journal.authorize_budget(extension.model_copy(update={"additional_tokens": 200}))
    with pytest.raises(ValueError):
        BudgetExtension(authorization_id="paid", additional_usd=1)


def campaign_fixture(tmp_path, monkeypatch, depths, failure=None, target="atlas"):
    """Discovery is SCRIPTED; every question runs the existing offline web-validation fixture."""
    from test_open_web import scripted_web_pipeline
    from webshaper import campaign
    from webshaper.pipeline import collect_sources, generate_graph
    def discovery(config, gateway, journal, batch):
        journal.record("companies", "company-atlas", {"company_id": "company-atlas", "name": "FICTIONAL Atlas Robotics",
                       "official_domain": "fixture.invalid", "industry": "manufacturing", "region": "north_america",
                       "funding_stage": "series_a_b"})
        journal.put(f"discovery:{batch}:done", True)
    def qualification(config, proposal, store, journal, gateway):
        sources = collect_sources(config, store, journal)
        graph_id, _, _ = generate_graph(config, sources, store, journal, gateway, "SCRIPTED-company")
        company = {**proposal, "qualified": True, "reason_codes": [], "graph_id": graph_id,
                   "company_entity_id": target, "relationship_families": ["products", "funding", "investors"],
                   "question_patterns": [["products", "funding", "investors"]]}
        journal.record("company_qualifications", proposal["company_id"], company)
        return company
    monkeypatch.setattr(campaign, "discover_batch", discovery)
    monkeypatch.setattr(campaign, "qualify_company", qualification)
    # Pydantic assignment checks require related settings to be installed atomically.
    def prepare(config):
        replacement = config.model_dump()
        replacement.update(target_tasks=len(depths), layers=max(depths), campaign=small_campaign(
            questions_per_company=len(depths), depth_targets=depths).model_dump())
        validated = type(config).model_validate(replacement)
        config.__dict__.update(validated.__dict__)
    return scripted_web_pipeline(tmp_path, monkeypatch, failure=failure, layers=max(depths), configure=prepare)


def test_scripted_campaign_accepted_expansion_keeps_private_allocation_and_resumes(tmp_path, monkeypatch):
    import json
    from webshaper.pipeline import run
    stats, root, calls, config = campaign_fixture(tmp_path, monkeypatch, [1])
    assert stats["accepted_tasks"] == 1 and stats["depth_distribution"] == {"1": 1}
    assert stats["campaign"]["target_reached"]
    ref = json.loads((root / "export/references.jsonl").read_text())
    assert ref["answer_entities_or_rows"] == ["atlas"]
    assert ref["company_id"] == "company-atlas" and ref["requested_depth"] == 1
    task = json.loads((root / "export/public/tasks.jsonl").read_text())
    assert not {"company_id", "question_slot", "requested_depth", "graph", "answer"} & task.keys()
    assert task["task_id"] == ref["task_id"]
    assert "atlas" not in task["task_id"] and "slot" not in task["task_id"]
    assert ref["internal_task_id"].startswith("company-atlas:slot:")
    coverage = json.loads((root / "export/company_coverage.json").read_text())
    assert coverage["companies"][0]["accepted_questions"] == 1
    assert coverage["companies"][0]["verified_browsing_successes"] >= 1
    before = len(calls)
    assert run(config, root)["usage"] == stats["usage"]
    assert len(calls) == before


def test_campaign_five_slots_do_not_credit_paraphrases(tmp_path, monkeypatch):
    stats, root, _, _ = campaign_fixture(tmp_path, monkeypatch, [0, 1, 1, 2, 2])
    assert stats["accepted_tasks"] == 1
    assert stats["campaign"]["question_shortfall"] == 4
    assert stats["rejection_reasons"]["near_duplicate_research_requirements"] == 4
    assert not stats["target_reached"]


def test_campaign_cannot_credit_retained_seed_to_deeper_slot(tmp_path, monkeypatch):
    stats, _, _, _ = campaign_fixture(tmp_path, monkeypatch, [1], failure="partial_shortcut")
    assert stats["accepted_tasks"] == 0
    assert stats["rejection_reasons"]["campaign_depth_shortfall"] == 1


def test_campaign_company_reference_mismatch_stops_before_solver(tmp_path, monkeypatch):
    stats, _, calls, _ = campaign_fixture(tmp_path, monkeypatch, [0], target="delta")
    assert stats["accepted_tasks"] == 0
    assert stats["rejection_reasons"]["campaign_reference_mismatch"] == 1
    assert not any(op in ("web_solver", "web_closed") for op, _, _ in calls)


def test_campaign_final_checkpoint_crash_does_not_spend_again(tmp_path, monkeypatch):
    from webshaper.storage import Journal
    from webshaper.pipeline import run
    put = Journal.put
    interrupted = []
    def crash(self, key, value):
        put(self, key, value)
        if key == "final_candidates" and not interrupted:
            interrupted.append(True)
            raise KeyboardInterrupt()
    monkeypatch.setattr(Journal, "put", crash)
    stats, root, calls, config = campaign_fixture(tmp_path, monkeypatch, [1])
    assert stats["status"] == "paused" and stats["accepted_tasks"] == 1
    before = len(calls)
    result = run(config, root)
    assert result["accepted_tasks"] == 1 and result["status"] == "completed"
    assert len(calls) == before


def test_readiness_requires_dated_exact_primary_evidence_and_connected_relationships(tmp_path):
    import json
    from datetime import date
    from webshaper.discovery import CompanyAssessment, readiness
    from webshaper.fixtures import fixture_config
    from webshaper.models import Bundle, Source
    from webshaper.pipeline import run
    from webshaper.sources import SourceStore
    config = fixture_config()
    root = tmp_path / "SCRIPTED-readiness"
    run(config, root)
    graph = json.loads((root / "export/graphs.jsonl").read_text().splitlines()[0])
    bundle = Bundle.model_validate(graph["bundle"])
    sources = [Source.model_validate(s) for s in graph["sources"]]
    store = SourceStore(root / "sources")
    data = config.model_dump()
    data.update(research_mode="open_web", campaign=small_campaign(min_primary_sources=2).model_dump())
    config = type(config).model_validate(data)
    supports = [{"attribute": "primary:" + s.source_id, "source_id": s.source_id, "quote": store.read(s)[:40]} for s in sources]
    supports += [{"attribute": a, "source_id": sources[0].source_id, "quote": store.read(sources[0])[:40]}
                 for a in ("identity", "industry", "region", "funding_stage")]
    assessment = CompanyAssessment(company_entity_id="atlas", industry="manufacturing", region="north_america",
        funding_stage="series_a_b", primary_source_ids=[s.source_id for s in sources], supports=supports,
        checks=[{"name": n, "status": "pass"} for n in ("identity", "distinct_identity", "primary_sources", "classification", "temporal_support")],
        feedback="SCRIPTED OFFLINE, not real classifications")
    proposal = {"company_id": "company-atlas", "name": "FICTIONAL Atlas", "official_domain": "fixture.invalid"}
    assert readiness(config, proposal, bundle, sources, assessment, store)["qualified"]
    negative = bundle.model_copy(deep=True)
    for fact in negative.facts:
        fact.polarity = "negative"
    assert not readiness(config, proposal, negative, sources, assessment, store)["qualified"]
    bad = assessment.model_copy(deep=True)
    bad.supports[0].quote = "FABRICATED PASSAGE"
    assert not readiness(config, proposal, bundle, sources, bad, store)["qualified"]
    bad = assessment.model_copy(deep=True)
    bad.checks[0].status = "unknown"
    assert not readiness(config, proposal, bundle, sources, bad, store)["qualified"]
    for s in sources:
        s.published_at = date(2026, 1, 1)
    result = readiness(config, proposal, bundle, sources, assessment, store)
    assert not result["qualified"]
    assert "insufficient_relationship_families" in result["reason_codes"]


def test_campaign_queue_prefers_missing_classifications():
    from webshaper.discovery import diversity_order
    existing = {"company_id": "a", "industry": "enterprise_software", "region": "north_america", "funding_stage": "growth"}
    new = {"company_id": "z", "industry": "agriculture", "region": "africa", "funding_stage": "pre_seed_seed"}
    assert diversity_order([existing, new], [existing])[0] == new


def test_partnerships_require_shared_event_identity():
    from test_query import graph
    from webshaper.models import Entity, Evidence, Fact
    from webshaper.query import validate_bundle
    bundle = graph()
    bundle.entities.append(Entity(entity_id="partnership", name="FICTIONAL event", kind="partnership_event"))
    bundle.evidence.append(Evidence(evidence_id="ep", source_id="s", span_start=0, span_end=4, span_text="test", claim_id="fp"))
    bundle.facts.append(Fact(claim_id="fp", subject_id="a", predicate="has_partnership_event", object_id_or_value="partnership",
                             event_id="partnership", valid_time={"start": "2025-01-01"}, evidence_ids=["ep"]))
    validate_bundle(bundle)
    bundle.facts[-1].event_id = None
    with pytest.raises(ValueError, match="event_id"):
        validate_bundle(bundle)


def test_discovery_resume_reuses_frozen_input_after_registry_write(tmp_path, monkeypatch):
    from webshaper.discovery import discover_batch
    from webshaper.fixtures import FixtureProvider, fixture_config
    from webshaper.models import RunConfig
    from webshaper.providers import ModelGateway, ProviderResult
    from webshaper.storage import Journal
    config = fixture_config().model_dump()
    config.update(research_mode="open_web", campaign=small_campaign().model_dump())
    config = RunConfig.model_validate(config)
    count = []
    def invoke(self, prompt, payload, schema, web=False):
        assert web
        count.append(1)
        company = {"name": "SCRIPTED Acme", "official_url": "https://acme.invalid", "industry": "manufacturing",
                   "region": "north_america", "funding_stage": "series_a_b", "primary_urls": ["https://acme.invalid/news"],
                   "rationale": "SCRIPTED"}
        fake = {**company, "name": "SCRIPTED Invented", "official_url": "https://invented.invalid",
                "primary_urls": ["https://invented.invalid/not-observed"]}
        return ProviderResult({"companies": [company, fake], "limitations": "FICTIONAL"}, 10, 1, {}, {
            "web_enabled": True, "visited_urls": ["https://acme.invalid/news"],
            "web_events": [{"status": "completed", "action": {"type": "search", "query": "SCRIPTED"}}]})
    monkeypatch.setattr(FixtureProvider, "invoke", invoke)
    record = Journal.record
    interrupted = []
    def crash(self, kind, key, value):
        record(self, kind, key, value)
        if kind == "companies" and not interrupted:
            interrupted.append(True)
            raise KeyboardInterrupt()
    monkeypatch.setattr(Journal, "record", crash)
    with Journal(tmp_path / "run.sqlite", {}, config.budget) as journal:
        gateway = ModelGateway(journal, {"generator": FixtureProvider(config.generator)})
        with pytest.raises(KeyboardInterrupt):
            discover_batch(config, gateway, journal, 0)
        discover_batch(config, gateway, journal, 0)
        assert len(count) == 1
        assert len(journal.records("companies")) == 1
        assert any(e["reason"] == "company_has_no_observed_source_url" for e in journal.records("errors"))


def test_extended_budget_can_dispatch_previously_blocked_gateway_call(tmp_path):
    from webshaper.models import Budget, BudgetExtension, SeedProposal
    from webshaper.providers import ModelGateway, ProviderResult
    from webshaper.storage import BudgetExceeded, Journal
    class Provider:
        config = {"token_reservation": 100}
        def invoke(self, *args, **kwargs):
            return ProviderResult({"question": "SCRIPTED", "query": None, "concerns": [], "rejection_reason": "fixture"},
                                  100, 0, {"fixture": True})
    with Journal(tmp_path / "run.sqlite", {}, Budget(max_tokens=100, max_calls=1)) as journal:
        gateway = ModelGateway(journal, {"generator": Provider()})
        gateway.call("generator", "seed", {}, SeedProposal, "one")
        with pytest.raises(BudgetExceeded):
            gateway.call("generator", "seed", {}, SeedProposal, "two")
        journal.authorize_budget(BudgetExtension(authorization_id="explicit", additional_calls=1, additional_tokens=100))
        gateway.call("generator", "seed", {}, SeedProposal, "two")
        assert journal.usage()["calls"] == 2
        assert len(journal.records("web_traces")) == 3  # blocked dispatch remains auditable


def test_near_identical_public_templates_across_companies_are_rejected(tmp_path):
    from test_validation import candidate
    from webshaper.diversity import diversity_check
    from webshaper.models import Budget
    from webshaper.storage import Journal
    a = candidate()
    a.company_id = "private-A"
    b = a.model_copy(deep=True)
    b.company_id, b.seed_id = "private-B", "other-seed"
    b.task.task_id = "other-task"
    with Journal(tmp_path / "run.sqlite", {}, Budget()) as journal:
        assert not diversity_check(b, [a], None, journal, "seed")


def test_verified_rebrands_and_legal_name_aliases_share_identity_keys():
    from webshaper.discovery import identity_keys
    from webshaper.models import Entity
    old = Entity(entity_id="old:source-id", name="Acme, Inc.", kind="company",
                 identifiers=["https://www.Acme.example/about/"], aliases=["Acme Research Ltd"])
    new = Entity(entity_id="new:source-id", name="Acme Research Limited", kind="company",
                 identifiers=["http://acme.example/about"], aliases=["Renamed Acme"])
    a = identity_keys({"name": "Acme", "official_domain": "acme.example"}, old)
    b = identity_keys({"name": "Renamed Acme", "official_domain": "renamed.example"}, new)
    assert "name:acme research" in a & b
    assert "url:acme.example/about" in a & b


def test_bad_completed_discovery_batches_are_bounded_and_checkpointed(tmp_path, monkeypatch):
    from webshaper import campaign
    from webshaper.models import RunConfig
    from webshaper.storage import Journal
    config = RunConfig(as_of="2025-12-31", research_mode="open_web", target_tasks=1,
                       campaign=small_campaign(max_discovery_batches=2))
    calls = []
    def fail(config, gateway, journal, batch):
        if journal.get(f"discovery:{batch}:done"):
            return
        calls.append(batch)
        raise ValueError("company_discovery_missing_observed_search")
    monkeypatch.setattr(campaign, "discover_batch", fail)
    with Journal(tmp_path / "run.sqlite", {}, config.budget) as journal:
        campaign.run_campaign(config, None, journal, None)
        campaign.run_campaign(config, None, journal, None)
        assert calls == [0, 1]
        assert len(journal.records("company_discovery_failures")) == 2
