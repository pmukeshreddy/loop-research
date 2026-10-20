#!/usr/bin/env python3
"""Prepare, or explicitly execute, isolated refinement replays of saved jobs.

No research worker or web tool is launched. Preparation uses the standard library
and the lossless representation decoder. Execution verifies installed source bytes, then uses the real product
Refiner, CodexBackend, Harness and RunContext. Case-specific inputs live in a
manifest, never in this script. New output roots are required for new attempts.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import traceback
from datetime import datetime, timezone
from uuid import uuid4


def stamp():
    return datetime.now(timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False).encode()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    os.replace(temporary, path)


def git(repo, *args, binary=False):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=not binary,
                                   stderr=subprocess.PIPE)


def logical_input(job, max_edits):
    return {"focus": job["focus"], "candidate_inventory": job["candidate_inventory"],
            "entries": list(job["snapshot"]["entries"].values()),
            **job["observed"], "max_edits": max_edits}


def verify_saved_input(job, expected):
    """Verify archived wire/logical identities before accepting a saved snapshot."""
    prompt = job['planner_prompt']
    if 'planner_representation' not in job:
        if not prompt.endswith(encoded(expected).decode()):
            raise ValueError('Archived plain planner input differs from the saved logical fields')
        return {'representation': 'plain-json', 'logical_input_equal': True}
    from loop_research.shared_text import decode_shared_text
    metadata = job['planner_representation']
    if not isinstance(metadata, dict):
        raise ValueError('Invalid archived representation metadata')
    size = metadata['wire_payload_chars']
    if type(size) is not int or not 0 < size <= len(prompt):
        raise ValueError('Invalid archived wire payload length')
    wire_text = prompt[-size:]
    if sha(wire_text.encode()) != metadata['wire_payload_sha256']:
        raise ValueError('Archived wire payload hash differs')
    wire = json.loads(wire_text)
    if wire['format'] != metadata['format']:
        raise ValueError('Archived representation format differs')
    logical = decode_shared_text(wire)
    logical_bytes = encoded(logical)
    if (len(logical_bytes.decode()) != metadata['logical_payload_chars']
            or sha(logical_bytes) != metadata['logical_payload_sha256']):
        raise ValueError('Archived logical payload identity differs')
    with_index = dict(expected)
    if 'evidence_index' in job:
        with_index['evidence_index'] = job['evidence_index']
    if logical_bytes != encoded(with_index):
        raise ValueError('Decoded planner input differs from the saved logical fields/index')
    return {'representation': metadata['format'], 'logical_input_equal': True,
            'wire_hash_verified': True, 'logical_hash_verified': True}


def source_identity(repo):
    return {"head": git(repo, "rev-parse", "HEAD").strip(),
            "branch": git(repo, "branch", "--show-current").strip(),
            "status": git(repo, "status", "--porcelain"),
            "refs": git(repo, "show-ref"),
            "state_sha256": sha((repo / "harness_state.json").read_bytes())}


def file_record(path):
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": sha(data)}


def prepare(manifest_path, output_root):
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    source_root = Path(manifest["source_root"]).resolve()
    cases = manifest["cases"]
    labels = [case["label"] for case in cases]
    if not cases or len(set(labels)) != len(labels):
        raise ValueError("Manifest needs independent, uniquely labeled cases")
    if any(not re.fullmatch(r"[A-Za-z0-9_-]+", label) for label in labels):
        raise ValueError("Case labels must be path-safe")
    output_root.mkdir(parents=True, exist_ok=False)
    (output_root / "source_manifest.json").write_bytes(manifest_bytes)
    prepared = {"created_at": stamp(), "status": "preparing", "source_root": str(source_root),
                "source_manifest": file_record(manifest_path), "script": file_record(Path(__file__).resolve()),
                "prepare_command": [sys.executable, *sys.argv], "cases": []}
    save(output_root / "prepared.json", prepared)
    try:
        for case in cases:
            label = case["label"]
            case_root = output_root / label
            evidence = case_root / "evidence"
            evidence.mkdir(parents=True)
            job_path = Path(case["job_archive"]).resolve()
            config_path = Path(case["config_archive"]).resolve()
            harness_path = Path(case["harness_repository"]).resolve()
            job_bytes, config_bytes = job_path.read_bytes(), config_path.read_bytes()
            job, config = json.loads(job_bytes), json.loads(config_bytes)
            if job["status"] != "failed" or job.get("proposal") is not None:
                raise ValueError(f"{label}: expected failed, unapplied saved planner job")
            if set(job["observed"]) != {"trajectory", "self_check"}:
                raise ValueError(f"{label}: unexpected observation contract")
            snapshot_head = case["snapshot_head"]
            original_identity = source_identity(harness_path)
            committed_snapshot = json.loads(git(harness_path, "show", snapshot_head + ":harness_state.json"))
            if committed_snapshot != job["snapshot"]:
                raise ValueError(f"{label}: supplied Git head does not exactly match archived snapshot")
            subprocess.run(["git", "-C", str(harness_path), "merge-base", "--is-ancestor",
                            snapshot_head, job["branch"]], check=True, capture_output=True)
            expected = logical_input(job, config["refine"]["max_edits"])
            original_payload = encoded(expected)
            input_verification = verify_saved_input(job, expected)
            (evidence / "original_job.json").write_bytes(job_bytes)
            (evidence / "original_config.json").write_bytes(config_bytes)
            (evidence / "original_logical_input.json").write_bytes(original_payload)
            originals = [file_record(job_path), file_record(config_path)]
            for number, source in enumerate(case.get("source_archives", [])):
                path = Path(source).resolve()
                originals.append(file_record(path))
                shutil.copyfile(path, evidence / f"source_{number:02d}_{path.name}")
            for directory in case.get("source_archive_directories", []):
                originals += [file_record(path) for path in sorted(Path(directory).resolve().rglob("*"))
                              if path.is_file()]
            originals = list({item["path"]: item for item in originals}.values())
            clone = case_root / "workspace" / "harness"
            clone.parent.mkdir(parents=True)
            commands = [
                ["git", "clone", "--no-hardlinks", "--no-checkout", str(harness_path), str(clone)],
                ["git", "-C", str(clone), "checkout", "-b", "saved-refine-" + uuid4().hex, snapshot_head],
                ["git", "-C", str(clone), "config", "user.name", "Saved refinement replay"],
                ["git", "-C", str(clone), "config", "user.email", "refine-replay@localhost"],
            ]
            for command in commands:
                subprocess.run(command, check=True, capture_output=True, text=True)
            if (clone / ".git/objects/info/alternates").exists():
                raise ValueError("Clone must have independent object storage")
            if json.loads((clone / "harness_state.json").read_text()) != job["snapshot"]:
                raise ValueError("Clone snapshot differs from original")
            item = {"label": label, "root": str(case_root), "harness": str(clone),
                    "source_harness": str(harness_path), "source_harness_identity": original_identity,
                    "source_files": originals, "original_job_id": job["job_id"],
                    "original_request_id": job["request_id"], "original_branch": job["branch"],
                    "original_run_id": case["original_run_id"], "task_id": case["task_id"],
                    "snapshot_head": snapshot_head, "snapshot_matches_committed_state": True,
                    "snapshot_commit_metadata": git(harness_path, "show", "-s", "--format=%H%n%cI%n%B", snapshot_head),
                    "replay_branch": git(clone, "branch", "--show-current").strip(),
                    "original_logical_input_chars": len(original_payload.decode()),
                    "original_logical_input_sha256": sha(original_payload),
                    "original_input_verification": input_verification,
                    "clone_commands": commands, "config": config}
            prepared["cases"].append(item)
            save(case_root / "prepared_case.json", item)
            save(output_root / "prepared.json", prepared)
            if source_identity(harness_path) != original_identity:
                raise ValueError("Source harness changed during preparation")
        prepared.update(status="prepared", completed_at=stamp(), live_calls=0)
    except BaseException as exc:
        prepared.update(status="prepare_failed", error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
        raise
    finally:
        save(output_root / "prepared.json", prepared)
    return prepared


def verify_installed_source(source_root, requested_commit):
    commit = git(source_root, "rev-parse", requested_commit + "^{commit}").strip()
    if git(source_root, "rev-parse", "HEAD").strip() != commit:
        raise ValueError("Expected source commit is not the current repository HEAD")
    specification = importlib.util.find_spec("loop_research")
    if specification is None or not specification.submodule_search_locations:
        raise ValueError("Installed loop_research package unavailable")
    package_root = Path(next(iter(specification.submodule_search_locations))).resolve()
    source_files = git(source_root, "ls-tree", "-r", "--name-only", commit, "src/loop_research").splitlines()
    source_files = [name for name in source_files if name.endswith(".py")]
    expected_names = {str(Path(name).relative_to("src/loop_research")) for name in source_files}
    installed_names = {str(path.relative_to(package_root)) for path in package_root.rglob("*.py")}
    if installed_names != expected_names:
        raise ValueError("Installed Python module set differs from committed source")
    records = []
    for name in source_files:
        committed = git(source_root, "show", commit + ":" + name, binary=True)
        working = source_root / name
        installed = package_root / Path(name).relative_to("src/loop_research")
        if working.read_bytes() != committed or installed.read_bytes() != committed:
            raise ValueError(f"Uncommitted or stale installed module: {name}")
        records.append({"source": name, "installed": str(installed), "bytes": len(committed),
                        "sha256": sha(committed)})
    return {"commit": commit, "python": sys.executable, "package_root": str(package_root),
            "verified_at": stamp(), "modules": records}


def expected_anchors(payload):
    # Independent specification of the agreed presentation-only anchor vocabulary.
    refs = ["/trajectory", "/self_check", "/entries"]
    refs += [f"/trajectory/{i}" for i in range(len(payload["trajectory"]))]
    refs += [f"/entries/{i}" for i in range(len(payload["entries"]))]
    refs += ["/self_check/" + key.replace("~", "~0").replace("/", "~1")
             for key in payload["self_check"]]
    refs += [ref for candidate in payload["candidate_inventory"] for ref in candidate["evidence_refs"]]
    return list(dict.fromkeys(refs))


def verify_originals(case):
    for record in case["source_files"]:
        if file_record(Path(record["path"])) != record:
            raise ValueError(f"Original source archive changed: {record['path']}")
    if source_identity(Path(case["source_harness"])) != case["source_harness_identity"]:
        raise ValueError("Original source harness changed")


def verify_scheduled(scheduled, request_id, job):
    """Require a fresh scheduling acknowledgement bound to the durable job."""
    if (not isinstance(scheduled, dict) or set(scheduled) != {'scheduled', 'request_id', 'job_id'}
            or scheduled['scheduled'] is not True or scheduled['request_id'] != request_id
            or job.get('request_id') != request_id or not job.get('job_id')
            or scheduled['job_id'] != job['job_id']):
        raise ValueError(f"Unexpected replay scheduling result: {scheduled}")


def replay_schema_contract(job, expected):
    """Accept exact current schemas or the sole historical anchor restriction.

    The recognized old schema is byte-for-byte the current base schema with the
    original edit cap. Replacing its string items with a finite enum only
    restricts accepted values. Arbitrary historical schema changes fail closed.
    """
    from loop_research.refine import Proposal
    original = job["planner_schema"]
    base = Proposal.model_json_schema()
    base["properties"]["edits"]["maxItems"] = expected["max_edits"]
    current = copy.deepcopy(base)
    anchors = expected_anchors(expected)
    current["$defs"]["EvidenceRef"] = {"type": "string", "enum": anchors}
    changes = [{"path": "/$defs/EvidenceRef", "before": None, "after": current["$defs"]["EvidenceRef"]}]
    for name in ("Candidate", "Decision"):
        items = current["$defs"][name]["properties"]["evidence_refs"]
        previous = items["items"]
        items["items"] = {"$ref": "#/$defs/EvidenceRef"}
        changes.append({"path": f"/$defs/{name}/properties/evidence_refs/items",
                        "before": previous, "after": items["items"]})
    if encoded(original) == encoded(current):
        mode, changes = "exact", []
    elif (encoded(original) == encoded(base) and "planner_representation" not in job
          and "evidence_index" not in job):
        mode = "legacy_anchor_restriction"
    else:
        raise ValueError("Original planner schema differs from the recognized replay schema contracts")
    return {"mode": mode, "original_schema": original, "current_schema": current, "changes": changes,
            "original_schema_sha256": sha(encoded(original)), "current_schema_sha256": sha(encoded(current)),
            "current_evidence_index": anchors, "original_constraints_preserved": True,
            "final_validation_required": ["original_schema", "current_schema", "complete_candidate_accounting"]}


def replay_attempt_counts(task, transport_audit):
    from loop_research.archive_audit import archived_calls, lines
    calls = archived_calls(task, lines(task / "codex_calls.jsonl"))
    return {"actual_refinement_attempts": sum(call.get("purpose") == "refine" for call in calls),
            "context_refinement_attempts": sum(row["backend_attempt_count"] for row in transport_audit)}


def recording_context(base_context, expected, *, expected_schema=None):
    """Keep replay guards/counters across scoped dataclass context copies.

    The guard runs at the process boundary: backend.scope intentionally creates
    a base CodexBackend, so a complete() override alone cannot guard its calls.
    Python workers and real Codex executions have separate counters.
    """
    from loop_research.archive import append_json, read_jsonl
    from loop_research.archive_audit import verify_refinement_context
    from loop_research.codex_backend import CodexBackend, INSTRUCTION
    from loop_research.isolation import isolated_command, worker_env
    from loop_research import refine
    from loop_research.shared_text import decode_shared_text

    state = {"codex_calls": 0, "worker_processes": 0, "processes": 0}
    lock = threading.Lock()

    def verify_context(ctx, job):
        checked = verify_refinement_context(ctx.path, job, expected)
        if expected_schema is not None and encoded(checked["schema"]) != encoded(expected_schema):
            raise ValueError("Overflow planner schema differs from original saved schema")
        anchors = expected_anchors(expected)
        if checked["payload"]["evidence_index"] != anchors:
            raise ValueError("Context evidence_index differs from independently computed anchors")
        checked = {key: value for key, value in checked.items()
                   if key not in ("payload", "schema", "manifest", "directory")}
        ctx.save("input_verification.json", {
            **checked, "verified_at": stamp(), "original_logical_input_equal": True,
            "original_logical_input_sha256": sha(encoded(expected)),
            "evidence_index_exact": True, "evidence_index": anchors,
            "removed_for_comparison_only": ["evidence_index"],
        })
        return ctx.path / "refine_planners" / job["job_id"]

    def verify_direct(ctx, stdin, schema):
        prefix = INSTRUCTION + refine.INSTRUCTIONS
        if not stdin.startswith(prefix):
            raise ValueError("Planner prefix differs from current Refiner instructions")
        wire_text = stdin[len(prefix):]
        decoded = decode_shared_text(json.loads(wire_text))
        supplied_index = decoded.pop("evidence_index")
        if decoded != expected or encoded(decoded) != encoded(expected):
            raise ValueError("Decoded logical input differs from original saved planner input")
        anchors = expected_anchors(expected)
        if supplied_index != anchors:
            raise ValueError("Presentation evidence_index differs from independently computed anchors")
        if schema is None or schema.get("$defs", {}).get("EvidenceRef", {}).get("enum") != anchors:
            raise ValueError("Output schema reference enum differs from visible evidence_index")
        if expected_schema is not None and encoded(schema) != encoded(expected_schema):
            raise ValueError("Direct planner schema differs from original saved schema")
        ctx.save("input_verification.json", {
            "verified_at": stamp(), "original_logical_input_equal": True,
            "original_logical_input_sha256": sha(encoded(decoded)),
            "evidence_index_exact": True, "evidence_index": supplied_index, "schema_enum_exact": True,
            "wire_chars": len(wire_text), "wire_sha256": sha(wire_text.encode()),
            "planner_prompt_chars": len(stdin) - len(INSTRUCTION),
            "planner_prompt_sha256": sha(stdin[len(INSTRUCTION):].encode()),
            "removed_for_comparison_only": ["evidence_index"],
        })

    class RecordingContext(base_context):
        def run_process(self, command, **kwargs):
            command = list(map(str, command))
            stdin = kwargs.get("input")
            schema_path, schema = None, None
            job = self.load("refine_state.json", {})
            overflow = job.get("planner_transport", {}).get("kind") == "repl-context-v1"
            if command[:2] == [self.config.codex.bin, "exec"]:
                if not isinstance(stdin, str):
                    raise ValueError("Replay expects text Codex stdin")
                if "--output-schema" in command:
                    schema_path = Path(command[command.index("--output-schema") + 1])
                    schema = json.loads(schema_path.read_text())
                try:
                    output = Path(command[command.index("--output-last-message") + 1])
                    expected_command = CodexBackend(self).command(
                        Path(kwargs["cwd"]), output, model=self.config.models.refine, schema_file=schema_path)
                except (ValueError, KeyError) as error:
                    raise ValueError("Invalid saved replay Codex process") from error
                if command != expected_command:
                    raise ValueError("Saved refinement replay cannot make research/web calls")
                schema_text = json.dumps(schema) if schema is not None else None
                receipts = [self.load(str(path.relative_to(self.path)))
                            for path in (self.path / "codex_attempts").glob("*.json")]
                matching = [row for row in receipts if row.get("prompt_sha256") == sha(stdin.encode())
                            and row.get("prompt_chars") == len(stdin)
                            and row.get("schema_sha256") == (sha(schema_text.encode()) if schema_text is not None else None)
                            and row.get("schema_chars") == (len(schema_text) if schema_text is not None else None)]
                if not matching or any(row["purpose"] != "refine" or row["model"] != self.config.models.refine
                                       for row in matching):
                    raise ValueError("Saved replay process lacks an exclusively refine dispatch receipt")
                if overflow:
                    directory = verify_context(self, job)
                    actions = read_jsonl(directory / "actions.jsonl")
                    action_ids = {row["action_id"] for row in actions if row["event"] == "model.start"
                                  and row["backend_prompt"] == stdin and row.get("schema") == schema}
                    bound = {row["call_id"] for row in actions if row["event"] == "model.attempt"
                             and row["status"] == "dispatched" and row["action_id"] in action_ids}
                    if not bound.intersection(row["call_id"] for row in matching):
                        raise ValueError("Saved replay call lacks its actual overflow model action")
                else:
                    verify_direct(self, stdin, schema)
                kind, counter = "codex", "codex_calls"
            else:
                if not overflow or kwargs.get("trace_component") != "Refiner context worker" or stdin is not None:
                    raise ValueError("Saved replay refuses an unrelated worker process")
                directory = verify_context(self, job)
                work = Path(kwargs["cwd"]).resolve()
                request_path = work / "request.json"
                intended = isolated_command(work, [sys.executable, "-m", "loop_research.refine_context", str(request_path)])
                request = json.loads(request_path.read_text())
                stable = {key: value for key, value in request.items() if key not in ("socket", "result_path")}
                if (command != intended or kwargs.get("env") != worker_env(work)
                        or stable != json.loads((directory / "request.json").read_text())
                        or request.get("socket") != str(work / "host.sock")
                        or request.get("result_path") != str(work / "result.json")):
                    raise ValueError("Saved replay worker process differs from the isolated refinement contract")
                kind, counter = "refiner_worker", "worker_processes"
            with lock:
                number = state["processes"]
                state["processes"] += 1
                state[counter] += 1
            directory = self.path / "transport" / f"{number:03d}"
            directory.mkdir(parents=True, exist_ok=False)
            if stdin is not None:
                (directory / "stdin.txt").write_text(stdin)
            if schema_path is not None:
                shutil.copyfile(schema_path, directory / "schema.json")
            metadata = {"timestamp": stamp(), "process_kind": kind, "command": command,
                        "cwd": str(kwargs.get("cwd")), "stdin_chars": len(stdin) if stdin is not None else None,
                        "stdin_sha256": sha(stdin.encode()) if stdin is not None else None,
                        "schema_sha256": sha(schema_path.read_bytes()) if schema_path is not None else None,
                        "archive": str(directory)}
            if kind == "refiner_worker":
                shutil.copyfile(request_path, directory / "request.json")
                metadata["worker_log"] = str(self.path / "refine_planners" / job["job_id"] / "worker.log")
            save(directory / "command.json", metadata)
            append_json(self.path / "commands.jsonl", metadata)
            try:
                completed = super().run_process(command, **kwargs)
            except BaseException as exc:
                save(directory / "transport_result.json", {"error": f"{type(exc).__name__}: {exc}"})
                raise
            if completed.stdout is not None:
                (directory / "stdout.jsonl").write_text(completed.stdout)
            if completed.stderr is not None:
                (directory / "stderr.txt").write_text(completed.stderr)
            save(directory / "transport_result.json", {"returncode": completed.returncode, "ended_at": stamp()})
            return completed

    return RecordingContext, state


def replay_case(case, cancellation):
    from loop_research.archive import RunContext, append_json
    from loop_research.codex_backend import CodexBackend
    from loop_research.config import Config
    from loop_research.harness import Harness
    from loop_research import refine
    from loop_research.shared_text import decode_shared_text
    from loop_research.trace import Trace
    import jsonschema

    case_root = Path(case["root"])
    expected_bytes = (case_root / "evidence/original_logical_input.json").read_bytes()
    job_bytes = (case_root / "evidence/original_job.json").read_bytes()
    config_bytes = (case_root / "evidence/original_config.json").read_bytes()
    if (sha(expected_bytes) != case["original_logical_input_sha256"]
            or sha(job_bytes) != case["source_files"][0]["sha256"]
            or sha(config_bytes) != case["source_files"][1]["sha256"]):
        raise ValueError("Prepared original-input copies changed")
    expected, job = json.loads(expected_bytes), json.loads(job_bytes)
    config = Config.model_validate(json.loads(config_bytes))
    if logical_input(job, config.refine.max_edits) != expected:
        raise ValueError("Prepared logical input differs from its original job/config")
    result_path = case_root / "replay_result.json"
    result = {"label": case["label"], "status": "preflight", "started_at": stamp(),
              "original_job_id": case["original_job_id"], "original_request_id": case["original_request_id"],
              "snapshot_head": case["snapshot_head"], "live_calls": 0}
    save(result_path, result)
    refiner = None

    schema_contract = replay_schema_contract(job, expected)
    save(case_root / "schema_contract.json", schema_contract)
    result["schema_contract"] = str(case_root / "schema_contract.json")
    RecordingContext, recorder_state = recording_context(
        RunContext, expected, expected_schema=schema_contract["current_schema"])

    try:
        verify_originals(case)
        harness = Harness(Path(case["harness"]))
        if harness.head != case["snapshot_head"] or harness.snapshot() != job["snapshot"]:
            raise ValueError("Replay clone is no longer exactly at the saved snapshot")
        run_id = "refine-replay-" + uuid4().hex
        ctx = RecordingContext(Path(case["harness"]).parent, run_id, config, case["task_id"], cancellation)
        ctx.trace = Trace(ctx.run_dir)
        ctx.initialize(harness.head, kind="saved-refine-replay", original_run_id=case["original_run_id"],
                       original_job_id=job["job_id"], original_request_id=job["request_id"])
        ctx.save("original_job_provenance.json", case)
        result.update(status="running", run_id=run_id, run_dir=str(ctx.run_dir), task_dir=str(ctx.path))
        save(result_path, result)
        backend = CodexBackend(ctx)
        refiner = refine.Refiner(harness, ctx, backend, lambda: copy.deepcopy(job["observed"]))
        request_id = "saved-replay-" + uuid4().hex
        with ctx.trace.span("Saved refinement replay", "run", parent="Replay CLI",
                            original_job_id=job["job_id"], snapshot_head=harness.head):
            scheduled = refiner.run(job["focus"], request_id=request_id)
            verify_scheduled(scheduled, request_id, ctx.load('refine_state.json'))
            commits = refiner.boundary(wait=True)
            saved = ctx.load("refine_state.json")
            if saved["status"] != "applied" or refiner.pending is not None:
                raise ValueError("Replay did not durably apply its strict proposal")
            proposal = refine.Proposal.model_validate(saved["proposal"])
            jsonschema.Draft202012Validator(saved["planner_schema"]).validate(proposal.model_dump())
            jsonschema.Draft202012Validator(schema_contract["original_schema"]).validate(proposal.model_dump())
            refine.validate_accounting(proposal, expected)
            if len(proposal.edits) > config.refine.max_edits:
                raise ValueError("Replay exceeded original max_edits")
            applied_commits = [{"sha": commit,
                                "metadata": harness.git("show", "-s", "--format=%H%n%cI%n%B", commit),
                                "files": harness.git("show", "--format=", "--name-only", commit)}
                               for commit in commits]
            verify_originals(case)
            result.update(status="complete", strict_proposal_valid=True, original_schema_valid=True, accounting_valid=True,
                          original_inputs_unchanged=True, original_harness_unchanged=True,
                          proposal=proposal.model_dump(), job_id=saved["job_id"], request_id=request_id,
                          head_after=harness.head, commits=applied_commits,
                          live_calls=recorder_state["codex_calls"], input_verification=str(ctx.path / "input_verification.json"))
    except BaseException as exc:
        result.update(status="failed", error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
        if "ctx" in locals():
            result["live_calls"] = recorder_state["codex_calls"]
        try:
            verify_originals(case)
            result.update(original_inputs_unchanged=True, original_harness_unchanged=True)
        except BaseException as changed:
            result["original_integrity_error"] = str(changed)
    finally:
        if refiner is not None:
            refiner.close()
        if "ctx" in locals():
            # A failed helper assertion may still have a background planner.
            # Count after shutdown settles it, not before its process starts.
            result["live_calls"] = recorder_state["codex_calls"]
            result["worker_processes"] = recorder_state["worker_processes"]
            try:
                from loop_research.archive_audit import audit_refinement_transports
                transport_audit = audit_refinement_transports(ctx.path)
                save(ctx.path / "refinement_transport_audit.json", transport_audit)
                result["refinement_transport_audit"] = str(ctx.path / "refinement_transport_audit.json")
                result.update(replay_attempt_counts(ctx.path, transport_audit))
            except BaseException as audit_error:
                result.update(status="failed", transport_audit_error=f"{type(audit_error).__name__}: {audit_error}")
        result["ended_at"] = stamp()
        save(result_path, result)
    return result


def execute(output_root, expected_commit):
    prepared = json.loads((output_root / "prepared.json").read_text())
    if prepared["status"] != "prepared":
        raise ValueError("Output root is not a complete prepared replay")
    if (output_root / "execution.json").exists():
        raise ValueError("Execution already attempted; prepare a fresh root for a new attempt")
    if file_record(Path(__file__).resolve()) != prepared["script"]:
        raise ValueError("Replay script changed since preparation")
    source = verify_installed_source(Path(prepared["source_root"]), expected_commit)
    limits = {case["config"]["codex"]["max_concurrent"] for case in prepared["cases"]}
    if len(limits) != 1:
        raise ValueError("Parallel cases must share the same configured Codex slot limit")
    for case in prepared["cases"]:
        verify_originals(case)
    execution = {"status": "running", "started_at": stamp(), "command": [sys.executable, *sys.argv],
                 "source_verification": source, "shared_codex_max_concurrent": next(iter(limits)),
                 "results": []}
    save(output_root / "execution.json", execution)
    cancellation = concurrent.futures.Future()
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=len(prepared["cases"]))
    futures = {pool.submit(replay_case, case, cancellation): case for case in prepared["cases"]}
    try:
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
            except Exception as exc:
                result = {"label": futures[future]["label"], "status": "failed",
                          "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()}
                save(Path(futures[future]["root"]) / "replay_result.json", result)
            execution["results"].append(result)
            save(output_root / "execution.json", execution)
        execution["status"] = "complete" if all(r["status"] == "complete" for r in execution["results"]) else "failed"
    except BaseException as exc:
        cancellation.cancel()
        execution.update(status="interrupted", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        pool.shutdown(wait=True)
        execution["ended_at"] = stamp()
        save(output_root / "execution.json", execution)
    return execution


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, help="Required for preparation")
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--execute", action="store_true", help="Make real refinement calls in already prepared clones")
    parser.add_argument("--expected-source-commit", help="Required for live execution")
    args = parser.parse_args()
    if args.execute:
        if not args.expected_source_commit:
            parser.error("--execute requires --expected-source-commit")
        result = execute(args.output_root.resolve(), args.expected_source_commit)
    else:
        if args.manifest is None:
            parser.error("Preparation requires --manifest")
        result = prepare(args.manifest.resolve(), args.output_root.resolve())
    print(json.dumps({"status": result["status"], "output_root": str(args.output_root.resolve())}, indent=2))
    return 0 if result["status"] in {"prepared", "complete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
