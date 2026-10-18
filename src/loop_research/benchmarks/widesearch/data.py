"""Task metadata and pinned acquisition. Never opens gold tables."""
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pydantic import BaseModel, ConfigDict, Field, create_model
from .. import Task, OutputContract
from ...archive import write_json

DATASET_REVISION = "6531a7e5b497d44c8912407e0cb3dc95bd98cc09"
CODE_REVISION = "9825ba7b140b71d81b364793f86dabe4cfed6749"
REPO = "https://github.com/ByteDance-Seed/WideSearch.git"
DATASET = "https://huggingface.co/datasets/ByteDance-Seed/WideSearch/resolve/" + DATASET_REVISION
MANIFEST = json.loads(Path(__file__).with_name("manifest.json").read_text())


def verify_payload(filename, payload):
    """Validate bytes against Git blob IDs from the pinned Hugging Face tree."""
    actual = hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()
    if MANIFEST["revision"] != DATASET_REVISION or actual != MANIFEST["files"][filename]:
        raise ValueError(f"WideSearch dataset integrity check failed: {filename}")


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
            if path.exists():
                verify_payload(filename, path.read_bytes())
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with urllib.request.urlopen(DATASET + "/" + filename, timeout=120) as response:
                    payload = response.read()
                verify_payload(filename, payload)
                temporary = path.with_suffix(path.suffix + ".part")
                temporary.write_bytes(payload)
                temporary.replace(path)
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(download, MANIFEST["files"]))
        if not self.code.exists():
            self.code.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "clone", "--quiet", "--no-checkout", REPO, str(self.code)], check=True)
            subprocess.run(["git", "-C", str(self.code), "checkout", "--quiet", "--detach", CODE_REVISION], check=True)
        self.verify_code()
        write_json(self.download / "revision.json", {"dataset": DATASET_REVISION, "code": CODE_REVISION})

    def verify_data(self):
        # Acquisition integrity only; no gold values are parsed or returned to a solver.
        for filename in MANIFEST["files"]:
            verify_payload(filename, (self.download / filename).read_bytes())

    def verify_code(self):
        sha = subprocess.check_output(["git", "-C", str(self.code), "rev-parse", "HEAD"], text=True).strip()
        dirty = subprocess.check_output(["git", "-C", str(self.code), "status", "--porcelain", "--untracked-files=no"], text=True)
        if sha != CODE_REVISION or dirty:
            raise ValueError("Official WideSearch checkout is not clean at the pinned revision")
