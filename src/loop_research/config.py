from pathlib import Path
from typing import Literal
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

class Models(Strict):
    root: str | None = None
    sub: str | None = None
    reflect: str | None = None
    reasoning_effort: str | None = None

class Codex(Strict):
    bin: str = "codex"
    max_concurrent: int = Field(4, ge=1)
    timeout_s: float = Field(600, gt=0)
    max_retries: int = Field(4, ge=0)
    log_full_text: bool = False

class RLM(Strict):
    max_iterations: int = Field(30, ge=1)
    max_depth: int = Field(1, ge=1)

class Agent(Strict):
    task_timeout_s: float = Field(3600, gt=0)
    max_codex_calls: int = Field(300, ge=1)

class Split(Strict):
    train: float = Field(.6, gt=0, lt=1)
    val: float = Field(.2, gt=0, lt=1)
    test: float = Field(.2, gt=0, lt=1)
    @model_validator(mode="after")
    def total(self):
        if abs(self.train + self.val + self.test - 1) > 1e-9:
            raise ValueError("split proportions must sum to one")
        return self

class Data(Strict):
    seed: int = 42
    languages: list[Literal["en", "zh"]] = Field(default_factory=lambda: ["en", "zh"], min_length=1)
    split: Split = Field(default_factory=Split)
    @model_validator(mode="after")
    def unique(self):
        if len(set(self.languages)) != len(self.languages):
            raise ValueError("languages must be unique")
        return self

class Wandr(Strict):
    final_n_tasks: int | None = Field(50, ge=1)
    seed: int = 42

class Final(Strict):
    repeats: int = Field(1, ge=1)

class Skills(Strict):
    max_playbook_chars: int = Field(6000, ge=0)

class Reflect(Strict):
    max_ops: int = Field(3, ge=1)
    max_chars: int = Field(20000, ge=1)
    batch_size: int = Field(1, ge=1)

class Gate(Strict):
    val_batch_size: int = Field(20, ge=1)
    repeats: int = Field(1, ge=1)
    min_delta: float = Field(.01, ge=0, le=1)
    max_regressions: int = Field(2, ge=0)
    regression_tol: float = Field(.10, ge=0, le=1)
    dedup_threshold: float = Field(.85, ge=0, le=1)
    leakage_min_len: int = Field(4, ge=1)

class Loop(Strict):
    train_batch_size: int = Field(5, ge=1)
    parallel_tasks: int = Field(4, ge=1)

class Config(Strict):
    models: Models = Field(default_factory=Models)
    codex: Codex = Field(default_factory=Codex)
    rlm: RLM = Field(default_factory=RLM)
    agent: Agent = Field(default_factory=Agent)
    data: Data = Field(default_factory=Data)
    wandr: Wandr = Field(default_factory=Wandr)
    final: Final = Field(default_factory=Final)
    skills: Skills = Field(default_factory=Skills)
    reflect: Reflect = Field(default_factory=Reflect)
    gate: Gate = Field(default_factory=Gate)
    loop: Loop = Field(default_factory=Loop)

    @classmethod
    def load(cls, path: Path | str = "config.yaml"):
        return cls.model_validate(yaml.safe_load(Path(path).read_text()) or {})

    @property
    def judge_label(self):
        return "codex/" + (self.models.root or "default")
