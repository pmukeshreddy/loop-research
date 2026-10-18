"""EXPLICITLY FICTIONAL, SCRIPTED test backend. Never used by live runs."""
from pathlib import Path

from .models import ModelConfig, RunConfig, SourceInput
from .prompts import PROMPTS
from .providers import ProviderResult
from .validation import SEMANTIC_CHECKS


def fixture_config():
    root = Path(__file__).resolve().parent / "fixture_data"
    if not root.exists():
        root = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
    model = ModelConfig(backend="fixture", token_reservation=100)
    return RunConfig(mode="fixture", as_of="2025-12-31", generator=model, expander=model,
                     verifier=model, solver=model, search_provider="fixture", target_tasks=1,
                     max_seed_attempts=1, shortcut_audit_rate=0,
                     sources=[SourceInput(origin=str(root / name), published_at="2025-03-15",
                                          date_basis="fictional test document", category="fixture", redistributable=True)
                              for name in ("funding.txt", "portfolio.txt")])


def fixture_extraction(documents):
    definitions = [("atlas", "Atlas Robotics", "company"), ("delta", "Delta Robotics", "company"),
                   ("nova", "Nova Robotics", "company"), ("orion", "Orion Dockworks", "company"),
                   ("lyra", "Lyra Systems", "company"), ("cedar", "Cedar Ventures", "investor"),
                   ("birch", "Birch Ventures", "investor"), ("warehouse", "WarehouseBot", "product"),
                   ("dock", "DockBot", "product"), ("shelf", "ShelfBot", "product"),
                   ("series_a", "Series A", "category"), ("series_b", "Series B", "category"),
                   ("y2024", "2024", "year"), ("y2025", "2025", "year"),
                   ("atlas_a", "Atlas-A-2025", "funding_event"), ("delta_a", "Delta-A-2025", "funding_event"),
                   ("nova_a", "Nova-A-2024", "funding_event"), ("nova_b", "Nova-B-2025", "funding_event")]
    entities = [{"entity_id": i, "name": n, "kind": k, "identifiers": ["fixture:" + i],
                 "aliases": [], "resolution_status": "resolved"} for i, n, k in definitions]
    docs = {"funding": next(d for d in documents if "Atlas-A-2025" in d["text"]),
            "portfolio": next(d for d in documents if "Orion Dockworks" in d["text"])}
    facts = []
    def add(s, p, o, event, quote, doc="funding", date="2025-03-15"):
        facts.append({"subject_id": s, "predicate": p, "object_id_or_value": o, "event_id": event,
                      "valid_time": {"start": date, "end": None, "kind": "event" if event else "state"},
                      "resolution_status": "resolved", "polarity": "positive",
                      "quotes": [{"source_id": docs[doc]["source_id"], "quote": quote, "start": docs[doc]["text"].index(quote)}]})
    for company, name in (("atlas", "Atlas"), ("delta", "Delta"), ("nova", "Nova")):
        add(company, "builds", "warehouse", None, f"{name} Robotics builds WarehouseBot warehouse robots.")
    events = [("atlas", "atlas_a", "series_a", "y2025", "cedar", "2025-03-15",
               "On 2025-03-15 Atlas Robotics announced funding event Atlas-A-2025, a Series A round with Cedar Ventures as an investor."),
              ("delta", "delta_a", "series_a", "y2025", "birch", "2025-03-15",
               "On 2025-03-15 Delta Robotics announced funding event Delta-A-2025, a Series A round with Birch Ventures as an investor."),
              ("nova", "nova_a", "series_a", "y2024", "cedar", "2024-02-01",
               "On 2024-02-01 Nova Robotics announced Nova-A-2024, a Series A round with Cedar Ventures as an investor."),
              ("nova", "nova_b", "series_b", "y2025", "birch", "2025-03-15",
               "On 2025-03-15 Nova Robotics announced Nova-B-2025, a Series B round with Birch Ventures as an investor.")]
    for company, event, series, year, investor, date, quote in events:
        for s, p, o in ((company, "has_funding_event", event), (event, "round_type", series),
                        (event, "announcement_year", year), (event, "investor", investor)):
            add(s, p, o, event, quote, date=date)
    for s, p, o, quote in [
        ("cedar", "portfolio_company", "orion", "Cedar Ventures has Orion Dockworks as a portfolio company as of 2025-03-15."),
        ("birch", "portfolio_company", "lyra", "Birch Ventures has Lyra Systems as a portfolio company as of 2025-03-15."),
        ("orion", "builds", "dock", "Orion Dockworks builds DockBot dock robots as of 2025-03-15."),
        ("lyra", "builds", "shelf", "Lyra Systems builds ShelfBot shelf scanners as of 2025-03-15.")]:
        add(s, p, o, None, quote, doc="portfolio")
    return {"entities": entities, "facts": facts}


class FixtureProvider:
    def __init__(self, config):
        self.config = config.model_dump(mode="json")

    def invoke(self, prompt, payload, schema, web=False):
        if web:
            raise ValueError("fictional backend cannot access the network")
        op = next(k for k, v in PROMPTS.items() if v == prompt)
        if op == "extract":
            data = fixture_extraction(payload["documents"])
        elif op in ("support", "judge", "grade"):
            names = SEMANTIC_CHECKS if op == "judge" else (["citation_support"] if op == "grade" else ["identity", "temporal_semantics"])
            data = {"checks": [{"name": n, "status": "pass", "feedback": "SCRIPTED FIXTURE judgment, not a real factual audit.", "evidence_ids": []} for n in names],
                    "claim_support": [{"claim_id": f["claim_id"], "status": "supported", "feedback": "SCRIPTED FIXTURE"} for f in payload.get("claims", [])],
                    "revision_feedback": []}
        elif op == "seed":
            literals = {e["name"]: e["entity_id"] for e in payload["graph"]["entities"] if e["kind"] in ("year", "category")}
            data = {"question": "As of 2025-12-31, which company builds WarehouseBot warehouse robots and announced a Series A funding round in 2025 with Cedar Ventures as an investor?",
                    "query": {"target": "?company", "answer_type": "company", "branches": [[
                        {"subject": "?company", "predicate": "builds", "object": "warehouse"},
                        {"subject": "?company", "predicate": "has_funding_event", "object": "?event"},
                        {"subject": "?event", "predicate": "round_type", "object": literals["Series A"]},
                        {"subject": "?event", "predicate": "announcement_year", "object": literals["2025"]},
                        {"subject": "?event", "predicate": "investor", "object": "cedar"}]]},
                    "concerns": ["SCRIPTED FIXTURE"], "rejection_reason": None}
        elif op == "expand":
            leaf = payload["selected_leaf"]
            if leaf == "cedar":
                sub = {"target": "?investor", "answer_type": "investor", "branches": [[
                    {"subject": "?investor", "predicate": "portfolio_company", "object": "orion"}]]}
                question = "As of 2025-12-31, which company builds WarehouseBot warehouse robots and announced a Series A funding round in 2025 with an investor whose portfolio includes Orion Dockworks?"
            elif leaf == "orion":
                sub = {"target": "?anchor", "answer_type": "company", "branches": [[
                    {"subject": "?anchor", "predicate": "builds", "object": "dock"}]]}
                question = "As of 2025-12-31, which company builds WarehouseBot warehouse robots and announced a Series A funding round in 2025 with an investor whose portfolio includes the company that builds DockBot dock robots?"
            else:
                sub, question = None, ""
            data = {"subquery": sub, "proposed_question": question, "rationale": "FICTIONAL identifying portfolio dependency.",
                    "rejection_reason": None if sub else "no_valid_expansion: fixture has no additional product clues"}
        elif op == "solver":
            docs = payload["documents"]
            data = {"answer": ["Atlas Robotics"] if docs else [], "citations": [],
                    "uncertainty": "SCRIPTED FIXTURE, not an empirical solver assessment"}
            if docs:
                data["citations"] = [{"source_id": d["source_id"], "quote": d["text"]} for d in docs]
        elif op == "render":
            data = {"question": "As of 2025-12-31, which companies build WarehouseBot warehouse robots and announced Series A funding in 2025?"}
        else:
            raise ValueError("unsupported fixture operation")
        return ProviderResult(data, 10, 0, {"fixture": True, "scripted": True, "operation": op})
