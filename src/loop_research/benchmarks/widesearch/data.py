"""Task metadata and pinned acquisition. Never opens gold tables."""
import csv
import io
import json
from pathlib import Path
import random
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pydantic import BaseModel, ConfigDict, Field, create_model
from .. import Task, OutputContract
from ...archive import digest, read_json, write_json

DATASET_REVISION = "6531a7e5b497d44c8912407e0cb3dc95bd98cc09"
CODE_REVISION = "9825ba7b140b71d81b364793f86dabe4cfed6749"
REPO = "https://github.com/ByteDance-Seed/WideSearch.git"
DATASET = "https://huggingface.co/datasets/ByteDance-Seed/WideSearch/resolve/" + DATASET_REVISION


class Cell(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    value: str
    sources: list[str]
    quote: str


class WideSearchData:
    def __init__(self, root, config):
        self.root, self.config = Path(root), config
        self.download = self.root / "data/downloads/widesearch"
        self.code = self.root / "data/vendor/widesearch"

    def load_tasks(self):
        rows = [json.loads(x) for x in (self.download / "widesearch.jsonl").read_text().splitlines() if x.strip()]
        result = []
        for row in rows:
            if row["language"] not in self.config.data.languages:
                continue
            evaluation = json.loads(row["evaluation"])
            # Task.raw holds only solver-facing metadata, never evaluator criteria or answers.
            safe = {"instance_id": row["instance_id"], "query": row["query"], "language": row["language"]}
            result.append(Task(task_id=row["instance_id"], benchmark="widesearch", question=row["query"],
                spec={"columns": evaluation["required"], "keys": evaluation["unique_columns"]},
                language=row["language"], raw=safe))
        if not result or len({t.task_id for t in result}) != len(result):
            raise ValueError("Empty or duplicate task dataset")
        return result

    def output_contract(self, task):
        columns = task.spec["columns"]
        cells = create_model("Cells", __config__=ConfigDict(extra="forbid", strict=True),
            **{f"column_{i}": (Cell, Field(alias=name)) for i, name in enumerate(columns)})
        row = create_model("CitedRow", __config__=ConfigDict(extra="forbid", strict=True),
                           entity=(str, ...), cells=(cells, ...))
        table = create_model("CitedTable", __config__=ConfigDict(extra="forbid", strict=True), rows=(list[row], ...))
        return OutputContract(table, "Return a JSON object with rows. Each row has entity and cells. "
            "Cells must have exactly these column keys: " + json.dumps(columns, ensure_ascii=False) +
            ". Each cell has string value, sources (HTTP(S) URLs), and quote copied verbatim from fetched text. "
            "Include all key columns in cells. Do not add citations inside value.", {"rows": []})

    def to_submission(self, task, agent_output):
        data = self.output_contract(task).model.model_validate(agent_output).model_dump(by_alias=True)
        if not data["rows"]:
            return None  # Official evaluator's explicit absent-response input.
        columns = task.spec["columns"]
        def line(values):
            buf = io.StringIO()
            writer = csv.writer(buf, delimiter="|", quoting=csv.QUOTE_ALL, lineterminator="")
            writer.writerow([v.replace('\r', ' ').replace('\n', ' ') for v in values])
            return "|" + buf.getvalue() + "|"
        table = [line(columns), "|" + "|".join("---" for _ in columns) + "|"]
        table.extend(line([row["cells"][c]["value"] for c in columns]) for row in data["rows"])
        return {"instance_id": task.task_id, "response": "```markdown\n" + "\n".join(table) + "\n```"}

    def prepare(self):
        self.download.mkdir(parents=True, exist_ok=True)
        def download(filename):
            path = self.download / filename
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                with urllib.request.urlopen(DATASET + "/" + filename, timeout=120) as response:
                    payload = response.read()
                temporary = path.with_suffix(path.suffix + ".part")
                temporary.write_bytes(payload)
                temporary.replace(path)
        download("widesearch.jsonl")
        download("README.md")
        # Only filenames are read here; table contents remain grader-only.
        ids = [json.loads(line)["instance_id"] for line in (self.download / "widesearch.jsonl").read_text().splitlines()]
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(download, [f"widesearch_gold/{task_id}.csv" for task_id in ids]))
        if not self.code.exists():
            self.code.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "clone", "--quiet", "--no-checkout", REPO, str(self.code)], check=True)
            subprocess.run(["git", "-C", str(self.code), "checkout", "--quiet", "--detach", CODE_REVISION], check=True)
        self.verify_code()
        write_json(self.download / "revision.json", {"dataset": DATASET_REVISION, "code": CODE_REVISION})
        self.prepare_splits(self.config.data.seed)

    def verify_code(self):
        sha = subprocess.check_output(["git", "-C", str(self.code), "rev-parse", "HEAD"], text=True).strip()
        dirty = subprocess.check_output(["git", "-C", str(self.code), "status", "--porcelain", "--untracked-files=no"], text=True)
        if sha != CODE_REVISION or dirty:
            raise ValueError("Official WideSearch checkout is not clean at the pinned revision")

    def prepare_splits(self, seed):
        tasks = self.load_tasks()
        split = deterministic_split(tasks, seed, self.config.data.split.model_dump())
        meta = {"revision": DATASET_REVISION, "seed": seed, "languages": self.config.data.languages,
                "ratios": self.config.data.split.model_dump(), "splits": split}
        path = self.root / "data/splits.json"
        previous = read_json(path)
        if previous is not None and previous != meta:
            raise ValueError("Saved splits differ; use a separate workspace for a different split")
        write_json(path, meta)
        rng = random.Random(seed)
        candidates = sorted(split["val"])
        rng.shuffle(candidates)
        n = self.config.gate.val_batch_size
        if n > len(candidates):
            raise ValueError("gate.val_batch_size exceeds validation split")
        gate = {"split_hash": digest(meta), "task_ids": candidates[:n], "seed": seed}
        gate["id"] = digest(gate)
        previous = read_json(self.root / "data/gate_batch.json")
        if previous is not None and previous != gate:
            raise ValueError("Saved gate batch differs; use a separate workspace")
        write_json(self.root / "data/gate_batch.json", gate)
        return split

    def split_tasks(self, name):
        meta = read_json(self.root / "data/splits.json")
        if not meta or meta["revision"] != DATASET_REVISION or meta["seed"] != self.config.data.seed or meta["languages"] != self.config.data.languages or meta["ratios"] != self.config.data.split.model_dump():
            raise ValueError("Prepare data with matching configuration first")
        tasks = {t.task_id: t for t in self.load_tasks()}
        return [tasks[x] for x in meta["splits"][name]]


def deterministic_split(tasks, seed, proportions):
    rng = random.Random(seed)
    splits = {k: [] for k in ("train", "val", "test")}
    for language in sorted({t.language for t in tasks}):
        ids = sorted(t.task_id for t in tasks if t.language == language)
        rng.shuffle(ids)
        a, b = int(len(ids) * proportions["train"]), int(len(ids) * proportions["val"])
        for name, values in zip(splits, (ids[:a], ids[a:a+b], ids[a+b:])):
            splits[name].extend(values)
    return splits
