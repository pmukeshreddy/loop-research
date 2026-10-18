from datetime import date
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
from contextlib import contextmanager
from typing import Literal
import yaml
from pydantic import Field, model_validator
from .config import Strict

Tag = Literal["wide", "constraint", "enrichment", "entity_resolution", "rlm_usage", "format"]


def normalize_text(value):
    return " ".join(unicodedata.normalize("NFKC", str(value)).casefold().split())

class Counters(Strict):
    helpful: int = Field(0, ge=0)
    harmful: int = Field(0, ge=0)
    unused: int = Field(0, ge=0)

class GateMetadata(Strict):
    val_batch: str
    baseline: float
    with_edit: float
    delta: float
    repeats: int = Field(ge=1)
    date: date

class Skill(Strict):
    id: str = Field(pattern=r"^sk_\d{4}$")
    title: str = Field(min_length=1)
    applies_to: list[Tag] = Field(min_length=1)
    status: Literal["active", "retired"] = "active"
    source_tasks: list[str]
    gate: GateMetadata | None = None
    counters: Counters = Field(default_factory=Counters)
    body: str = Field(min_length=1)

    @model_validator(mode="after")
    def concise(self):
        if len(self.body.split()) > 80:
            raise ValueError("Skill body exceeds 80 words")
        if len(set(self.applies_to)) != len(self.applies_to):
            raise ValueError("Skill tags must be unique")
        return self

class EditOp(Strict):
    op: Literal["add", "update", "retire"]
    id: str | None = Field(None, pattern=r"^sk_\d{4}$")
    title: str | None = None
    body: str | None = None
    applies_to: list[Tag] | None = None
    rationale: str
    evidence_task_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def valid(self):
        if self.op != "add" and self.id is None:
            raise ValueError("update/retire requires an id")
        if self.op != "retire":
            if not self.title or not self.body or not self.applies_to:
                raise ValueError("add/update requires title, body, applies_to")
            if len(self.body.split()) > 80:
                raise ValueError("Skill body exceeds 80 words")
        return self


def parse_skill(path):
    text = Path(path).read_text()
    parts = re.split(r"(?m)^---[ \t]*$", text, maxsplit=2)
    if len(parts) != 3 or parts[0].strip():
        raise ValueError(f"Invalid skill front matter: {path}")
    return Skill.model_validate({**yaml.safe_load(parts[1]), "body": parts[2].strip()})


def write_skill(directory, skill):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    meta = skill.model_dump(mode="json", exclude={"body"})
    text = "---\n" + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True) + "---\n\n" + skill.body.strip() + "\n"
    with tempfile.NamedTemporaryFile(mode="w", dir=directory, delete=False) as pending:
        pending.write(text)
        pending.flush()
        os.fsync(pending.fileno())
    os.replace(pending.name, directory / (skill.id + ".md"))


def load_skills(directory):
    if directory is None:
        return []
    skills = [parse_skill(p) for p in sorted(Path(directory).glob("sk_*.md"))]
    if len({s.id for s in skills}) != len(skills):
        raise ValueError("Duplicate skill id")
    return skills


def render_playbook(task, library_dir, max_chars=6000):
    relevance = {"wide": 6, "constraint": 5, "enrichment": 4 if task.spec.get("columns") else 2,
                 "entity_resolution": 4 if len(task.spec.get("keys", [])) > 1 else 3,
                 "rlm_usage": 2, "format": 1}
    skills = [s for s in load_skills(library_dir) if s.status == "active"]
    skills.sort(key=lambda s: (-max(relevance[t] for t in s.applies_to),
                              -(s.counters.helpful - s.counters.harmful), s.id))
    text = ""
    for skill in skills:
        block = f"[{skill.id}] {skill.title}\n{skill.body}\n\n"
        if len(text) + len(block) <= max_chars:
            text += block
    return text.rstrip()


def git(directory, *args):
    return subprocess.check_output(["git", "-c", "commit.gpgsign=false", "-C", str(directory), *args],
                                   text=True, stderr=subprocess.STDOUT).strip()


def init_library(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if not (directory / ".git").exists():
        git(directory, "init", "-b", "main")
        git(directory, "config", "user.name", "loop-research")
        git(directory, "config", "user.email", "loop-research@localhost")
        git(directory, "commit", "--allow-empty", "-m", "Initialize research skills")
    return library_sha(directory)


def library_sha(directory):
    if directory is None:
        return "empty"
    if git(directory, "status", "--porcelain"):
        raise ValueError("Skills library has uncommitted changes; commit or resolve them first")
    return git(directory, "rev-parse", "HEAD")


def commit_library(directory, message):
    git(directory, "add", "--", ".")
    git(directory, "commit", "--allow-empty", "-m", message)
    return library_sha(directory)


def assign_id(op, directory):
    if op.op != "add":
        return op
    existing = {s.id for s in load_skills(directory)}
    if op.id and op.id in existing:
        raise ValueError("New skill id already exists")
    number = max([int(x[3:]) for x in existing], default=0) + 1
    return op.model_copy(update={"id": op.id or f"sk_{number:04d}"})


def apply_op(directory, op, gate=None):
    op = assign_id(op, directory)
    existing = {s.id: s for s in load_skills(directory)}
    if op.op == "add":
        skill = Skill(id=op.id, title=op.title, body=op.body, applies_to=op.applies_to,
                      source_tasks=op.evidence_task_ids, gate=gate)
    else:
        if op.id not in existing:
            raise ValueError("Unknown skill id")
        old = existing[op.id]
        if op.op == "retire":
            skill = old.model_copy(update={"status": "retired", "gate": gate or old.gate})
        else:
            skill = Skill(id=op.id, title=op.title, body=op.body, applies_to=op.applies_to,
                source_tasks=sorted(set(old.source_tasks + op.evidence_task_ids)), counters=old.counters, gate=gate)
    write_skill(directory, skill)
    return op


@contextmanager
def staged_library(directory, op):
    with tempfile.TemporaryDirectory(prefix="loop-skills-") as tmp:
        target = Path(tmp) / "skills"
        shutil.copytree(directory, target, ignore=shutil.ignore_patterns(".git"))
        applied = apply_op(target, op)
        yield target, applied


def update_counters(directory, judgments):
    by_id = {s.id: s for s in load_skills(directory)}
    for ident, judgment in judgments.items():
        if ident not in by_id:
            raise ValueError(f"Unknown skill in reflection: {ident}")
        skill = by_id[ident]
        field = {"helped": "helpful", "hurt": "harmful", "unused": "unused"}[judgment]
        setattr(skill.counters, field, getattr(skill.counters, field) + 1)
        write_skill(directory, skill)
