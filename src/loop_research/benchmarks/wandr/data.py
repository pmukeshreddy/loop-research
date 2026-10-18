import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request
from pydantic import ConfigDict, Field, create_model
from .. import OutputContract, Task

DATASET_REVISION = "066ee3d71cd332cb2fb4f49146cad7f9c7249f86"
CODE_REVISION = "ccb0baeb96f1c77a48e47f92122c57479ee99700"
FILES = {
    "README.md": "f8018be62be523a66548fb56942e8f269628810a70618a036516b9622a6dbfa1",
    "release-manifest.json": "2083cfab62fc170623db893168865ad89ccd0a8de768fcf4690b0036a2721909",
    "data/test.jsonl": "52e76377088a5d96f08c24dc2e00d2988040ef5a68bc60f5b00b0b68a9cbc764",
}


class WandrData:
    def __init__(self, root, config):
        self.root, self.config = Path(root).resolve(), config
        self.download = self.root / "data/downloads/wandr"
        self.code = self.root / "data/vendor/wandr"

    def package(self, task_id):
        return self.code / "datasets/wandr" / task_id.replace("_", "-")

    def verify_sources(self):
        sha = subprocess.check_output(["git", "-C", str(self.code), "rev-parse", "HEAD"], text=True).strip()
        dirty = subprocess.check_output(["git", "-C", str(self.code), "status", "--porcelain", "--untracked-files=no"], text=True)
        if sha != CODE_REVISION or dirty:
            raise ValueError("WANDR harness must be clean at its pinned revision")
        for name, expected in FILES.items():
            if hashlib.sha256((self.download / name).read_bytes()).hexdigest() != expected:
                raise ValueError(f"WANDR dataset checksum mismatch: {name}")

    def load_tasks(self):
        tasks = []
        for line in (self.download / "data/test.jsonl").read_text().splitlines():
            row = json.loads(line)
            if row["source_commit"] != CODE_REVISION or not row["scored"]:
                raise ValueError("Unexpected WANDR release record")
            package = self.package(row["task_id"])
            # Some HF instructions omit embedded assets; use the matching canonical package.
            instruction = row["instruction"] or (package / "instruction.md").read_text()
            nodes = json.loads(row["task_tree_json"])
            structure = [{k: node[k] for k in ("task_id", "parent_id", "order", "item_fields", "key_hierarchy", "required_output_file")}
                         for node in nodes]
            tasks.append(Task(task_id=row["task_id"], benchmark="wandr", question=instruction,
                spec={"nodes": structure}, language="en", raw={"source_commit": CODE_REVISION,
                    "required_output_files": row["required_output_files"]}))
        return tasks

    def output_contract(self, task):
        files = {}
        for i, node in enumerate(task.spec["nodes"]):
            item = create_model(f"Item{i}", __config__=ConfigDict(extra="forbid", strict=True),
                **{f"field_{j}": (str, Field(alias=name, min_length=1)) for j, name in enumerate(node["item_fields"])})
            record = create_model(f"Record{i}", __config__=ConfigDict(extra="forbid", strict=True),
                item=(item, ...), url=(str, Field(pattern=r"^https?://[^\s]+$")),
                excerpts=(list[str], ...), answer=(dict, ...))
            files[f"file_{i}"] = (list[record], Field(alias=node["required_output_file"]))
        output_files = create_model("OutputFiles", __config__=ConfigDict(extra="forbid"), **files)
        output = create_model("WandrOutput", __config__=ConfigDict(extra="forbid"), files=(output_files, ...))
        empty = {"files": {node["required_output_file"]: [] for node in task.spec["nodes"]}}
        return OutputContract(output, "Return {files: {filename: [records]}} with every required output filename. "
            "Each record has item (the node's required string fields), an HTTP(S) page url, excerpts "
            "copied verbatim from fetched text, and answer (a free-form object containing the requested facts). "
            "Honor the task's entity qualifications, hierarchy and required counts. Do not flatten subtasks.", empty)

    def to_submission(self, task, agent_output):
        return self.output_contract(task).model.model_validate(agent_output).model_dump(by_alias=True)["files"]

    def prepare(self):
        for filename, expected in FILES.items():
            path = self.download / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                url = f"https://huggingface.co/datasets/perplexity-ai/wandr/resolve/{DATASET_REVISION}/{filename}"
                with urllib.request.urlopen(url, timeout=120) as response:
                    payload = response.read()
                if hashlib.sha256(payload).hexdigest() != expected:
                    raise ValueError(f"Downloaded WANDR checksum mismatch: {filename}")
                path.write_bytes(payload)
        if not self.code.exists():
            self.code.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "clone", "--quiet", "--no-checkout", "https://github.com/perplexityai/wandr.git", str(self.code)], check=True)
            subprocess.run(["git", "-C", str(self.code), "checkout", "--quiet", "--detach", CODE_REVISION], check=True)
        self.verify_sources()
