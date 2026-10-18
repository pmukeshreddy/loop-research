from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
import re
from .archive import append_json, digest, read_json, read_jsonl, write_json
from .skills import (GateMetadata, Skill, assign_id, load_skills, library_sha, staged_library,
                     commit_library, normalize_text, parse_skill, write_skill)


def filter_edit(op, library, leakage_index, threshold):
    text = " ".join(x for x in (op.title, op.body) if x)
    norm = normalize_text(text)
    if re.search(r"(?:https?://|www\.)", text, re.I):
        return "leakage: URL"
    if re.search(r"\d", text):
        return "leakage: numbers/dates are not general methods"
    if any(entry in norm for entry in leakage_index):
        return "leakage: gold cell/entity text"
    if op.op == "add":
        for skill in load_skills(library):
            if skill.status == "active" and SequenceMatcher(None, normalize_text(op.body or ""), normalize_text(skill.body)).ratio() > threshold:
                return f"near-duplicate of {skill.id}; use update"
    return None


def gate_decision(baseline, candidate, config):
    if not baseline or set(baseline) != set(candidate):
        raise ValueError("Gate requires identical nonempty task sets")
    if any(not 0 <= x <= 1 for x in [*baseline.values(), *candidate.values()]):
        raise ValueError("Gate scores must be finite Row F1 values in [0, 1]")
    before = sum(baseline.values()) / len(baseline)
    after = sum(candidate.values()) / len(candidate)
    regressions = sum(baseline[k] - candidate[k] > config.regression_tol for k in baseline)
    delta = after - before
    return {"accepted": delta + 1e-12 >= config.min_delta and regressions <= config.max_regressions,
            "baseline": before, "with_edit": after, "delta": delta, "regressions": regressions}


class SkillGate:
    def __init__(self, ctx, batch, leakage_index, score_library):
        self.ctx, self.batch, self.index, self.score_library = ctx, batch, leakage_index, score_library

    def cache_key(self, sha):
        return digest({"sha": sha, "batch": self.batch, "config": self.ctx.config.model_dump()})

    def scores(self, directory, sha):
        path = self.ctx.root / "runs/gate_cache" / (self.cache_key(sha) + ".json")
        cached = read_json(path)
        if cached is not None:
            return cached
        scores = self.score_library(directory, self.cache_key(sha))
        if set(scores) != set(self.batch["task_ids"]):
            raise ValueError("Gate runner returned a different task batch")
        write_json(path, scores)
        return scores

    def consider(self, op, library, event_id):
        # Event journal survives a crash between writing the skill and committing it.
        event_path = self.ctx.path / "gate_events" / (event_id + ".json")
        saved = read_json(event_path)
        if saved and saved.get("done"):
            self._record(saved)
            return saved
        if saved and saved.get("decision", {}).get("accepted"):
            return self._finish_accept(saved, event_path, library)
        existing = {skill.id for skill in load_skills(library)}
        if op.op == "add" and op.id in existing:
            reason = f"invalid target: skill {op.id} already exists; use update"
        elif op.op != "add" and op.id not in existing:
            reason = f"invalid target: unknown skill {op.id}"
        else:
            op = assign_id(op, library)
            reason = filter_edit(op, library, self.index, self.ctx.config.gate.dedup_threshold)
        if reason:
            saved = {"done": True, "op": op.model_dump(), "decision": {"accepted": False},
                     "event_id": event_id, "reason": reason}
        else:
            baseline_sha = library_sha(library)
            baseline = self.scores(library, baseline_sha)
            with staged_library(library, op) as (staged, applied):
                candidate_key = digest({"parent": baseline_sha, "op": applied.model_dump()})
                candidate = self.scores(staged, candidate_key)
                skill = parse_skill(staged / (applied.id + ".md"))
            decision = gate_decision(baseline, candidate, self.ctx.config.gate)
            saved = {"done": False, "op": applied.model_dump(), "decision": decision,
                     "baseline_sha": baseline_sha, "baseline_scores": baseline,
                     "baseline_cache_key": self.cache_key(baseline_sha),
                     "candidate_cache_key": self.cache_key(candidate_key),
                     "scores": candidate, "event_id": event_id,
                     "reason": "validation gain/regression limits"}
            if decision["accepted"]:
                skill.gate = GateMetadata(val_batch=self.batch["id"], baseline=decision["baseline"],
                    with_edit=decision["with_edit"], delta=decision["delta"],
                    repeats=self.ctx.config.gate.repeats, date=date.today())
                saved["skill"] = skill.model_dump(mode="json")
                write_json(event_path, saved)
                return self._finish_accept(saved, event_path, library)
            saved["done"] = True
        write_json(event_path, saved)
        self._record(saved)
        return saved

    def _record(self, saved):
        name = "skills_accepted.jsonl" if saved["decision"]["accepted"] else "skills_rejected.jsonl"
        path = self.ctx.path / name
        if not any(item.get("event_id") == saved["event_id"] for item in read_jsonl(path)):
            append_json(path, saved)

    def _finish_accept(self, saved, path, library):
        from .skills import EditOp, git
        op = EditOp.model_validate(saved["op"])
        decision = saved["decision"]
        message = f"accept {op.op} {op.id}: val delta={decision['delta']:.12g}"
        head = git(library, "rev-parse", "HEAD")
        if head != saved["baseline_sha"]:
            if git(library, "log", "-1", "--format=%s") != message or git(library, "rev-parse", "HEAD^") != saved["baseline_sha"]:
                raise ValueError("Skills changed outside the pending gate transaction")
        else:
            skill = Skill.model_validate(saved["skill"])
            filename = op.id + ".md"
            dirty = set(git(library, "diff", "--name-only", "HEAD").splitlines())
            dirty.update(git(library, "ls-files", "--others", "--exclude-standard").splitlines())
            if dirty and (dirty != {filename} or
                          parse_skill(Path(library) / filename) != skill):
                raise ValueError("Skills changed outside the pending gate transaction")
            write_skill(library, skill)
            commit_library(library, message)
        saved.update(done=True, skills_sha=library_sha(library))
        write_json(self.ctx.root / "runs/gate_cache" / (self.cache_key(saved["skills_sha"]) + ".json"), saved["scores"])
        write_json(path, saved)
        self._record(saved)
        return saved
