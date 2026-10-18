"""Versioned data contracts. All agent outputs reject unexpected fields."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.0"


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Budget(Record):
    max_usd: float = Field(default=0, ge=0, allow_inf_nan=False)
    max_tokens: int = Field(default=500_000, ge=1)
    max_searches: int = Field(default=100, ge=0)
    max_calls: int = Field(default=150, ge=1)


class Source(Record):
    source_id: str
    url_or_local_origin: str
    title: str
    published_at: date | None
    retrieved_at: datetime
    content_hash: str
    raw_hash: str
    text_path: str
    raw_path: str
    category: Literal["primary", "secondary", "fixture"] = "primary"
    redistributable: bool = False
    date_basis: str = "unknown"


class Evidence(Record):
    evidence_id: str
    source_id: str
    span_start: int = Field(ge=0)
    span_end: int = Field(gt=0)
    span_text: str = Field(min_length=1)
    claim_id: str
    support_status: Literal["supported", "unsupported", "unknown"] = "unknown"


EntityKind = Literal["company", "investor", "person", "product", "funding_event", "acquisition_event",
                     "category", "date", "year", "location"]


class Entity(Record):
    entity_id: str
    name: str
    kind: EntityKind
    identifiers: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    resolution_status: Literal["resolved", "unresolved", "conflict"] = "unresolved"


class ValidTime(Record):
    start: date | None
    end: date | None = None
    kind: Literal["event", "state"] = "state"


class Fact(Record):
    claim_id: str
    subject_id: str
    predicate: str
    object_id_or_value: str
    event_id: str | None
    valid_time: ValidTime
    evidence_ids: list[str] = Field(min_length=1)
    resolution_status: Literal["resolved", "unresolved", "conflict"] = "unresolved"
    polarity: Literal["positive", "negative"] = "positive"


class Bundle(Record):
    entities: list[Entity]
    facts: list[Fact]
    evidence: list[Evidence]


class Atom(Record):
    subject: str
    predicate: str
    object: str | list[str]


class Query(Record):
    target: str = "?company"
    answer_type: EntityKind = "company"
    branches: list[list[Atom]] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def bounded(self):
        if not self.target.startswith("?") or any(not b or len(b) > 24 for b in self.branches):
            raise ValueError("query needs a target variable and 1..24 atoms in every branch")
        return self


class Scope(Record):
    mode: Literal["corpus_bounded", "identified_target"] = "identified_target"
    candidate_universe: list[str] | None = None
    expected_count: int = Field(default=1, ge=1)
    allow_retrospective: bool = False
    description: str = "Identify the specified target; no open-web completeness claim."

    @model_validator(mode="after")
    def universe(self):
        if self.mode == "corpus_bounded" and not self.candidate_universe:
            raise ValueError("corpus-bounded tasks require an enumerated universe")
        if self.candidate_universe and len(set(self.candidate_universe)) != len(self.candidate_universe):
            raise ValueError("duplicate candidates")
        return self


class PublicTask(Record):
    task_id: str
    question: str = Field(min_length=10)
    answer_schema: str = "entity_names"
    as_of: date
    scope: Scope
    corpus_id: str
    allowed_tools: list[str]
    data_mode: Literal["fixture", "live"]


class Candidate(Record):
    task: PublicTask
    query: Query
    answer: list[str]
    seed_id: str
    parent_id: str | None
    layer: int = 0
    version: int = 0
    expanded_leaf: str | list[str] | None = None
    intermediate_answer: list[str] = Field(default_factory=list)
    subquery: Query | None = None
    added_atoms: list[Atom] = Field(default_factory=list)
    candidate_decisions: dict = Field(default_factory=dict)
    cell_evidence: dict[str, list[str]] = Field(default_factory=dict)
    graph_id: str = ""


class SeedProposal(Record):
    question: str
    query: Query | None
    concerns: list[str]
    rejection_reason: str | None


class ExpansionProposal(Record):
    subquery: Query | None
    proposed_question: str
    rationale: str
    rejection_reason: str | None


class Check(Record):
    name: str
    status: Literal["pass", "fail", "unknown"]
    feedback: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


class SemanticAssessment(Record):
    checks: list[Check]
    claim_support: list["ClaimSupport"]
    revision_feedback: list[str]


class ClaimSupport(Record):
    claim_id: str
    status: Literal["supported", "unsupported", "unknown"]
    feedback: str


class Citation(Record):
    source_id: str
    quote: str


class SolverAnswer(Record):
    answer: list[str]
    citations: list[Citation]
    uncertainty: str


class Validation(Record):
    task_id: str
    candidate_version: int
    decision: Literal["accept", "revise", "reject"]
    checks: list[Check]
    solver_attempts: list[dict]
    feedback: list[str]
    judge_config: dict
    audit_status: Literal["fixture_only", "pending_manual_review", "approved", "rejected"]


class SourceInput(Record):
    origin: str
    title: str = ""
    published_at: date | None = None
    date_basis: str = "unknown"
    category: Literal["primary", "secondary", "fixture"] = "primary"
    redistributable: bool = False


class ModelConfig(Record):
    backend: Literal["codex", "fixture"] = "codex"
    executable: str = "codex"
    model: str | None = None
    reasoning_effort: Literal["low", "medium", "high"] = "low"
    timeout_seconds: int = Field(default=240, ge=10, le=1800)
    token_reservation: int = Field(default=100_000, ge=100)
    max_searches_per_call: int = Field(default=3, ge=1, le=10)


class RunConfig(Record):
    schema_version: str = SCHEMA_VERSION
    mode: Literal["fixture", "live"] = "live"
    sources: list[SourceInput] = Field(default_factory=list)
    allowed_domains: list[str] = Field(default_factory=list)
    crawl_depth: int = Field(default=0, ge=0, le=3)
    max_sources: int = Field(default=20, ge=1, le=200)
    as_of: date
    scope: Scope = Field(default_factory=Scope)
    generator: ModelConfig = Field(default_factory=ModelConfig)
    expander: ModelConfig = Field(default_factory=ModelConfig)
    verifier: ModelConfig = Field(default_factory=ModelConfig)
    solver: ModelConfig = Field(default_factory=ModelConfig)
    search_provider: Literal["codex", "none", "fixture"] = "codex"
    budget: Budget = Field(default_factory=Budget)
    target_tasks: int = Field(default=10, ge=1, le=10000)
    max_seed_attempts: int = Field(default=20, ge=1, le=10000)
    layers: int = Field(default=1, ge=0, le=5)
    browsing_attempts: int = Field(default=5, ge=1, le=10)
    max_revisions: int = Field(default=1, ge=0, le=3)
    concurrency: int = Field(default=1, ge=1, le=2)
    shortcut_audit_rate: float = Field(default=0.1, ge=0, le=1)
    fixture_file: str | None = None

    @model_validator(mode="after")
    def isolation(self):
        backends = {getattr(self, r).backend for r in ("generator", "expander", "verifier", "solver")}
        if self.mode == "live" and (backends != {"codex"} or self.search_provider == "fixture"):
            raise ValueError("live runs may not use fixture providers")
        if self.mode == "fixture" and (backends != {"fixture"} or self.search_provider != "fixture"):
            raise ValueError("fixture runs must be fully offline")
        if self.budget.max_usd != 0:
            raise ValueError("only subscription/fixture backends implemented; additional paid budget must be $0")
        return self
