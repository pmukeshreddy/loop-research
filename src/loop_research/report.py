"""Reports are derived exclusively from archived files; no research or grading."""
import csv
import io
from pathlib import Path

from .archive import read_json


def _rounds(root):
    rows = []
    for path in sorted((root / "runs").glob("*/round-*/round_metrics.json")):
        row = read_json(path)
        rows.append((row, path))
    return sorted(rows, key=lambda item: (item[0]["run_id"], item[0]["round"]))


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text)
    temporary.replace(path)


def write_rounds(root):
    root = Path(root).resolve()
    rows = _rounds(root)
    metric_names = sorted({name for row, _ in rows for name in row["train_metrics"]})
    names = ["run_id", "round", "library_sha", "active_skills", *["train_" + n for n in metric_names],
             "gate_score", "ops_proposed", "ops_accepted", "ops_rejected", "codex_calls", "wall_time_s", "judge", "source"]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=names)
    writer.writeheader()
    for row, source in rows:
        value = {name: row[name] for name in names if name in row}
        value.update({"train_" + name: score for name, score in row["train_metrics"].items()})
        value["source"] = str(source.relative_to(root))
        writer.writerow(value)
    path = root / "reports/rounds.csv"
    _write(path, buffer.getvalue())
    return path


def _text(value):
    if value is None:
        return "unavailable"
    if isinstance(value, float):
        return format(value, ".8g")
    return str(value).replace("|", "\\|").replace("\n", " ")


def _link(root, path, label="source"):
    relative = Path(path).relative_to(root)
    return f"[{label}](../{relative.as_posix()})"


def build_report(root):
    root = Path(root).resolve()
    directory = root / "reports"
    write_rounds(root)
    rows = _rounds(root)
    lines = ["# Research loop report", "", "Generated from archived run and report files only.", "",
             "## Improvement rounds", ""]
    if rows:
        names = ["run_id", "round", "library_sha", "active_skills", "train_metrics", "gate_score",
                 "ops_proposed", "ops_accepted", "ops_rejected", "codex_calls", "wall_time_s", "judge"]
        lines += ["Full table: [rounds.csv](rounds.csv). Each row links to its source archive.", "",
                  "| " + " | ".join(names) + " | source |",
                  "| " + " | ".join("---" for _ in names) + " | --- |"]
        for row, source in rows:
            values = dict(row)
            values["train_metrics"] = "; ".join(name + "=" + _text(value) for name, value in row["train_metrics"].items())
            lines.append("| " + " | ".join(_text(values[name]) for name in names) + " | " + _link(root, source) + " |")
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        figure, axes = plt.subplots(figsize=(8, 4.5))
        for run_id in sorted({row["run_id"] for row, _ in rows}):
            selected = [row for row, _ in rows if row["run_id"] == run_id]
            axes.plot([row["round"] for row in selected], [row["gate_score"] for row in selected], marker="o", label=run_id)
        axes.set(xlabel="Completed round", ylabel="Validation mean Row F1", ylim=(0, 1))
        axes.grid(alpha=.2)
        if len({row["run_id"] for row, _ in rows}) > 1:
            axes.legend(fontsize="small")
        figure.tight_layout()
        figure.savefig(directory / "validation_curve.png", dpi=160)
        plt.close(figure)
        lines += ["", "![Validation curve](validation_curve.png)", "", "Curve source: [rounds.csv](rounds.csv)."]
    else:
        lines.append("No completed improvement rounds are archived.")
    lines += ["", "## Skill decisions", ""]
    events = sorted((root / "runs").glob("*/round-*/gate_events/*.json"))
    if events:
        lines += ["| decision | operation | skill | reason | validation delta | source |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for path in events:
            event = read_json(path)
            if not event.get("done"):
                continue
            accepted = event["decision"]["accepted"]
            values = ["accepted" if accepted else "rejected", event["op"]["op"], event["op"].get("id"),
                      event.get("reason"), event["decision"].get("delta")]
            lines.append("| " + " | ".join(_text(v) for v in values) + " | " + _link(root, path) + " |")
    else:
        lines.append("No completed skill gate decisions are archived.")
    for benchmark in ("widesearch", "wandr"):
        lines += ["", "## Final " + benchmark, ""]
        source = directory / ("final_" + benchmark + ".json")
        result = read_json(source)
        if result is None:
            lines.append("No final evaluation report is archived.")
            continue
        source_link = _link(root, source)
        provenance = f"judge: {_text(result['judge'])}"
        if "fetch" in result:
            provenance += f"; fetch: {_text(result['fetch'])}"
        primary = "Project primary metric: `" + result["primary_metric"] + "`."
        if "harness_primary_metric" in result:
            primary += " Harness primary metric: `" + result["harness_primary_metric"] + "`."
        lines += [provenance + ". " + source_link, "", primary + " " + source_link, "",
                  f"Tasks: {_text(result['task_count'])}; repeats: {_text(result['repeats'])}; library: `{result['library_sha']}`. " + source_link,
                  "", "| variant | metric | aggregation | value | source |", "| --- | --- | --- | --- | --- |"]
        for variant, value in result["variants"].items():
            for metric, scores in value["metrics"].items():
                for aggregation, score in (scores.items() if isinstance(scores, dict) else [("value", scores)]):
                    lines.append(f"| {variant} | {_text(metric)} | {aggregation} | {_text(score)} | {source_link} |")
            for metric in ("excerpt_failures", "excerpt_judged", "excerpt_failure_rate", "unjudged_records"):
                if metric in value:
                    lines.append(f"| {variant} | {metric} | pooled | {_text(value[metric])} | {source_link} |")
        for variant, value in result["variants"].items():
            lines += ["", variant + " run archives: " + ", ".join(
                _link(root, root / "runs" / run_id / "run_summary.json", run_id) for run_id in value["run_ids"]) + "."]
        lines += ["", "Per-task metrics, grader provenance, and failure reasons are linked by `grade_paths` in " + source_link + "."]
    path = directory / "summary.md"
    _write(path, "\n".join(lines) + "\n")
    return path
