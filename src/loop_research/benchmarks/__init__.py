"""Data-only benchmark contracts. Importing this module loads no benchmark."""
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol
from pydantic import BaseModel, ConfigDict, Field

class Task(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$")
    benchmark: str
    question: str
    spec: dict[str, Any]
    language: str
    as_of_date: date | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

@dataclass
class OutputContract:
    model: type[BaseModel]
    prompt: str
    empty: dict

    @property
    def schema(self):
        return self.model.model_json_schema()

class GradeResult(BaseModel):
    metrics: dict[str, float]
    primary_metric: str
    errors: dict[str, Any] = Field(default_factory=dict)
    judge: str
    provenance: dict[str, Any] = Field(default_factory=dict)

class Benchmark(Protocol):
    def load_tasks(self) -> list[Task]: ...
    def output_contract(self, task: Task) -> OutputContract: ...
    def to_submission(self, task: Task, agent_output: dict) -> object: ...
    def grade(self, task: Task, submission: object, run_ctx) -> GradeResult: ...

# Explicit registration avoids imports of answer stores or final-only benchmarks.
registry: dict[str, Benchmark] = {}
