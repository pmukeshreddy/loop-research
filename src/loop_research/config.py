"""Validate explicit configuration; deployment values live in config.yaml."""
from datetime import date
from pathlib import Path
import re
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True, allow_inf_nan=False)


ModelName = Annotated[str, Field(min_length=1, pattern=r"\S")]


class Models(Strict):
    root: ModelName
    sub: ModelName
    refine: ModelName
    judge: ModelName
    reasoning_effort: ModelName | None


class Codex(Strict):
    bin: str = Field(min_length=1)
    max_concurrent: int = Field(ge=1)
    timeout_s: float = Field(gt=0)
    max_retries: int = Field(ge=0)
    retry_delay_cap_s: float = Field(gt=0)
    log_full_text: bool


class RLM(Strict):
    max_iterations: int = Field(ge=1)
    max_depth: int = Field(ge=1)


class Agent(Strict):
    task_timeout_s: float = Field(gt=0)
    max_codex_calls: int = Field(ge=1)
    as_of: str

    @field_validator("as_of")
    @classmethod
    def valid_as_of(cls, value):
        if value != "today":
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError("as_of must be 'today' or an ISO YYYY-MM-DD date")
            date.fromisoformat(value)
        return value


class Refine(Strict):
    max_edits: int = Field(ge=1)


class Bridge(Strict):
    socket_timeout_s: float = Field(gt=0)


class Verify(Strict):
    codex_timeout_s: float = Field(gt=0)
    browser_timeout_s: float = Field(gt=0)


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
    refine: Refine
    bridge: Bridge
    verify: Verify

    @classmethod
    def load(cls, path: Path | str):
        return cls.model_validate(yaml.safe_load(Path(path).read_text()))

    @property
    def judge_label(self):
        return "codex/" + self.models.judge
