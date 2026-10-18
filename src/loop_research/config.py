"""Validate explicit configuration; deployment values live in config.yaml."""
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True, allow_inf_nan=False)


ModelName = Annotated[str, Field(min_length=1)]


class Models(Strict):
    root: ModelName | None
    sub: ModelName | None
    refine: ModelName | None
    judge: ModelName | None
    reasoning_effort: ModelName | None


class Codex(Strict):
    bin: str = Field(min_length=1)
    max_concurrent: int = Field(ge=1)
    timeout_s: float = Field(gt=0)
    max_retries: int = Field(ge=0)
    log_full_text: bool


class RLM(Strict):
    max_iterations: int = Field(ge=1)
    max_depth: int = Field(ge=1)


class Agent(Strict):
    task_timeout_s: float = Field(gt=0)
    max_codex_calls: int = Field(ge=1)


class Data(Strict):
    seed: int = Field(ge=0)
    languages: list[Literal["en", "zh"]] = Field(min_length=1)

    @field_validator("languages")
    @classmethod
    def unique_languages(cls, languages):
        if len(set(languages)) != len(languages):
            raise ValueError("languages must be unique")
        return languages


class Wandr(Strict):
    final_n_tasks: int | None = Field(ge=1)
    seed: int = Field(ge=0)


class Harness(Strict):
    retrieval_limit: int = Field(ge=1)


class Stream(Strict):
    rolling_window: int = Field(ge=1)


class Config(Strict):
    models: Models
    codex: Codex
    rlm: RLM
    agent: Agent
    data: Data
    wandr: Wandr
    harness: Harness
    stream: Stream

    @classmethod
    def load(cls, path: Path | str):
        return cls.model_validate(yaml.safe_load(Path(path).read_text()))

    @property
    def judge_label(self):
        return "codex/" + (self.models.judge or "default")
