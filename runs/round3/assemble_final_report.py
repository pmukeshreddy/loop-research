"""Assemble the final report from reviewed disk fragments without touching proof_report."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parent
COHORT = ROOT / "cohorts/readable_controls_v1"
OUTPUT = ROOT / "Round3.candidate.v2.md"
MANIFEST = ROOT / "final_report_assembly.json"

def record(path):
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

resolved = []

def links(text, base):
    def replace(match):
        target = match.group(1).strip("<>")
        if target.startswith(("http://", "https://", "#", "mailto:")):
            return match.group(0)
        part = re.fullmatch(r"(.*?)(:\d+)?", target)
        path = Path(part.group(1))
        path = path if path.is_absolute() else (base / path).resolve()
        if not path.is_file():
            raise ValueError(f"Missing report link: {path}")
        resolved.append(str(path))
        return "](" + str(path) + (part.group(2) or "") + ")"
    return re.sub(r"\]\(([^\n)]+)\)", replace, text)

fragments = [
    COHORT / "outcomes_and_ten_checks.md",
    ROOT / "report_final_static.md",
    COHORT / "completed_A_SI_report.md",
    COHORT / "run_summary.md",
    COHORT / "completed_B_report.md",
    COHORT / "explicit.review.md",
    COHORT / "final_metrics/metrics.md",
]
sections = ["# Round 3 — fixes, completed runs, and demonstrated limits"]
for path in fragments:
    text = path.read_text()
    if path.name == "report_final_static.md":
        text = text.partition("\n")[2].lstrip("\n")
    elif path.name == "explicit.review.md":
        text = "## Explicit check — independent completed-run review\n" + text.partition("\n")[2]
    elif path.name == "metrics.md":
        text = re.sub(r"(?m)^## ", "### ", text)
        text = "## Complete metric tables\n" + text.partition("\n")[2]
    sections.append(links(text, path.parent).strip())
data = ("\n\n\n".join(sections) + "\n").encode()
with OUTPUT.open("xb") as stream:
    stream.write(data)
result = {
    "assembled_at": datetime.now(timezone.utc).isoformat(),
    "inputs": [record(path) for path in fragments],
    "output": record(OUTPUT),
    "resolved_file_links": len(resolved),
    "unique_linked_files": len(set(resolved)),
    "proof_report_modified": False,
    "runtime_or_metric_changes": False,
}
with MANIFEST.open("x") as stream:
    json.dump(result, stream, indent=2)
    stream.write("\n")
print(json.dumps(result["output"] | {"resolved_links": len(resolved)}))
