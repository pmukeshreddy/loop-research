"""Derive exact root-output overlap from an existing completed-run audit.

Usage: .venv/bin/python runs/round2/root_analysis.py LABEL.audit.json
Writes LABEL.root_output.json/.md, leaving audit and narrative reports untouched.
Only standard-library, disk-only analysis; no source imports or model calls.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re


OUTPUT_HEADER = re.compile(r"REPL output(?: \(block [1-9]\d*\))?:")


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def analyze(audit_path, prompt_path):
    audit = json.loads(audit_path.read_text())
    task = Path(audit["task_path"])
    research = json.loads((task.parent / "research.json").read_text())
    state = json.loads((task / "task_state.json").read_text())
    if research.get("status") != "complete" or state.get("phase") != "complete":
        raise ValueError("Only completed research/task archives may be analyzed")
    records = [json.loads(line) for line in (task / "trajectory.jsonl").read_text().splitlines()]
    largest = audit["largest_prompt"]
    model = records[largest["trajectory_line"] - 1]
    event = records[largest["iteration_trajectory_line"] - 1]["event"]
    full = prompt_path.read_text()
    if digest(full) != largest["sha256"] or len(full) != largest["total"] or not full.endswith(model["prompt"]):
        raise ValueError("Largest-prompt artifact does not match its archived model record and audit")
    instruction = full[:-len(model["prompt"])]
    evidence = json.loads((task / "evidence.json").read_text())
    texts = [(url, index, text) for url, values in evidence.get("fetched", {}).items()
             for index, text in enumerate(values)]
    n = audit["overlap"]["ngram_chars"]
    if n != 50:
        raise ValueError("This helper preserves the original 50-character criterion")
    wanted = {text[i:i+n] for _, _, text in texts for i in range(len(text)-n+1)}

    def grams(value):
        return {value[i:i+n] for i in range(len(value)-n+1)} & wanted

    def masks(matched):
        output = []
        for _, _, text in texts:
            mask = bytearray(len(text))
            for i in range(len(text)-n+1):
                if text[i:i+n] in matched:
                    mask[i:i+n] = b"\1" * n
            output.append(mask)
        return output

    def covered(matched):
        return sum(map(sum, masks(matched)))

    all_root_grams = set()
    for record in records:
        if record.get("type") == "model" and record.get("purpose") == "root":
            all_root_grams.update(grams(instruction + record["prompt"]))
    total_chars = sum(len(text) for _, _, text in texts)
    total_covered = covered(all_root_grams)
    if (total_chars, total_covered) != (audit["overlap"]["total_chars"], audit["overlap"]["covered_chars"]):
        raise ValueError("Original coverage calculation does not reproduce the supplied audit")
    stdout_grams, formatted_grams = set(), set()
    rows = []
    blocks = audit["blocks"]
    messages = event["prompt"]
    iteration_rows = {r["trajectory_line"]: r for r in audit["iterations"]}
    for message_index, message in enumerate(messages):
        content = message["content"]
        if message["role"] != "user" or not OUTPUT_HEADER.match(content):
            continue
        if message_index < 1 or messages[message_index-1]["role"] != "assistant":
            raise ValueError("REPL output lacks the expected preceding assistant response")
        # Match the complete transcript prefix; never assign child logs by adjacency.
        candidates = [line for line in iteration_rows
                      if records[line-1]["event"]["prompt"] == messages[:message_index-1]
                      and records[line-1]["event"]["response"] == messages[message_index-1]["content"]]
        if len(candidates) != 1:
            raise ValueError(f"Output message {message_index} has {len(candidates)} exact iteration matches")
        line = candidates[0]
        iteration = iteration_rows[line]
        audit_blocks = sorted((b for b in blocks if b["trajectory_line"] == line), key=lambda b: b["trace_line"])
        archived_blocks = records[line-1]["event"].get("code_blocks")
        if not isinstance(archived_blocks, list) or len(audit_blocks) != len(archived_blocks):
            raise ValueError("Audit block list does not match the archived iteration")
        source_blocks = []
        for index, (audit_block, archived_block) in enumerate(zip(audit_blocks, archived_blocks), 1):
            result = archived_block.get("result", {})
            if not all(isinstance(result.get(stream), str) for stream in ("stdout", "stderr")):
                raise ValueError(f"Archived block {index} lacks original stdout/stderr evidence")
            code = archived_block.get("code")
            if (not isinstance(code, str) or audit_block.get("code") != code
                    or audit_block.get("stdout") != result["stdout"]):
                raise ValueError(f"Audit block {index} code/stdout or execution order differs from the trajectory")
            source_blocks.append({**audit_block, "code": code,
                                  "stdout": result["stdout"], "stderr": result["stderr"]})
        previous = covered(formatted_grams)
        formatted_grams.update(grams(content))
        raw_stdout_chars = sum(len(b["stdout"]) for b in source_blocks)
        raw_stderr_chars = sum(len(b["stderr"]) for b in source_blocks)
        unmodified = True
        cursor = 0
        block_rows = []
        for index, block in enumerate(source_blocks, 1):
            header = f"REPL output (block {index}):" if len(source_blocks) > 1 else "REPL output:"
            start = content.find(header + "\n", cursor)
            if start < 0:
                unmodified = False
                start = cursor
            cursor = start + len(header) + 1
            for stream in (block["stdout"], block["stderr"]):
                if not stream:
                    continue
                pos = content.find(stream, cursor)
                if pos < 0:
                    unmodified = False
                else:
                    cursor = pos + len(stream)
            # Intersection ensures only grams actually retained in this output count.
            stdout_grams.update(grams(block["stdout"]) & grams(content))
            try:
                statements = [ast.get_source_segment(block["code"], node) for node in ast.walk(ast.parse(block["code"]))
                              if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print"]
            except SyntaxError:
                statements = None
            block_rows.append({"trace_link": block["code_trace_link"], "trajectory_link": block["trajectory_link"],
                               "code": block["code"], "code_sha256": digest(block["code"]),
                               "stdout_chars": len(block["stdout"]), "stdout_sha256": digest(block["stdout"]),
                               "stderr_chars": len(block["stderr"]), "stderr_sha256": digest(block["stderr"]),
                               "print_statements": statements})
        rows.append({"iteration": iteration["iteration"], "rlm_id": iteration["rlm_id"],
                     "trajectory_link": f"{task / 'trajectory.jsonl'}:{line}",
                     "trace_link": iteration["trace_link"], "message_index": message_index,
                     "formatted_chars": len(content), "formatted_sha256": digest(content),
                     "raw_stdout_chars": raw_stdout_chars, "raw_stderr_chars": raw_stderr_chars,
                     "all_raw_streams_found_unmodified_in_order": unmodified,
                     "formatted_nonstream_chars": len(content)-raw_stdout_chars-raw_stderr_chars if unmodified else None,
                     "independent_formatted_coverage_chars": covered(grams(content)),
                     "new_formatted_coverage_chars": covered(formatted_grams)-previous,
                     "blocks": block_rows})
    formatted_chars = sum(r["formatted_chars"] for r in rows)
    if formatted_chars != largest["parts"]["repl_output"]:
        raise ValueError("Formatted-output partition does not match the existing audit")
    source_url_covered = 0
    for (url, _, text), mask in zip(texts, masks(all_root_grams)):
        url_mask = bytearray(len(text))
        start = 0
        while (position := text.find(url, start)) >= 0:
            url_mask[position:position+len(url)] = b"\1" * len(url)
            start = position + len(url)
        source_url_covered += sum(a and b for a, b in zip(mask, url_mask))
    return {"run_id": audit["run_id"], "audit_path": str(audit_path), "audit_sha256": digest(audit_path.read_text()),
            "largest_prompt_path": str(prompt_path), "largest_prompt_sha256": digest(full),
            "largest_prompt_chars": len(full), "parts": largest["parts"],
            "criterion": {"ngram_chars": 50, "total_returned_chars": total_chars, "covered_chars": total_covered,
                          "fraction": total_covered/total_chars if total_chars else None,
                          "largest_prompt_coverage_chars": covered(grams(full)),
                          "largest_prompt_formatted_output_coverage_chars": covered(formatted_grams),
                          "largest_prompt_retained_stdout_coverage_chars": covered(stdout_grams),
                          "covered_chars_inside_exact_source_urls": source_url_covered,
                          "fully_present_texts": [r for r in audit["overlap"]["texts"] if r["full_text_in_root"]]},
            "output_totals": {"messages": len(rows), "formatted_chars": formatted_chars,
                              "raw_stdout_chars": sum(r["raw_stdout_chars"] for r in rows),
                              "raw_stderr_chars": sum(r["raw_stderr_chars"] for r in rows),
                              "formatted_nonstream_chars": sum(r["formatted_nonstream_chars"] for r in rows)
                                  if all(r["formatted_nonstream_chars"] is not None for r in rows) else None},
            "outputs": rows,
            "limitations": ["Raw stdout may exceed what the formatter retained. Missing full-stream matches leave nonstream attribution null; no retained-size estimate is substituted.",
                            "Overlap remains the original union of exact 50-character spans. Source URL and output attribution do not remove any positions from the criterion.",
                            "No raw website-body size is inferred from returned extracts or root overlap. Use web_inventory.py for full event exposure evidence."]}


def render(result):
    totals, criterion = result["output_totals"], result["criterion"]
    text = (f'# Root-output archive analysis: {result["run_id"]}\n\n'
            f'Completed archive only. Largest root request: **{result["largest_prompt_chars"]:,}** characters. '
            f'Formatted REPL output: **{totals["formatted_chars"]:,}**; raw stdout from its executed blocks: '
            f'**{totals["raw_stdout_chars"]:,}**; raw stderr: **{totals["raw_stderr_chars"]:,}**. Original 50-character overlap: '
            f'**{criterion["covered_chars"]:,}/{criterion["total_returned_chars"]:,}**.\n\n'
            f'Largest-prompt retained stdout accounts for **{criterion["largest_prompt_retained_stdout_coverage_chars"]:,}** '
            f'covered positions. Exact source URLs contain **{criterion["covered_chars_inside_exact_source_urls"]:,}** '
            'covered positions, still included in the criterion. These measurements concern returned extracts, not raw page bodies.\n\n'
            '| Producing iteration | Raw stdout | Raw stderr | Formatted output | New covered positions | Archive |\n'
            '|---:|---:|---:|---:|---:|---|\n')
    for row in result["outputs"]:
        text += (f'| {row["iteration"]} | {row["raw_stdout_chars"]:,} | {row["raw_stderr_chars"]:,} | {row["formatted_chars"]:,} | '
                 f'{row["new_formatted_coverage_chars"]:,} | [trace]({row["trace_link"]}) / '
                 f'[trajectory]({row["trajectory_link"]}) |\n')
    text += '\nActual print statements, in descending formatted-output size; full code and hashes are retained in the companion JSON.\n'
    for row in sorted(result["outputs"], key=lambda r: r["formatted_chars"], reverse=True):
        text += f'\n**Iteration {row["iteration"]}: {row["formatted_chars"]:,} formatted characters.**\n'
        statements = [s for b in row["blocks"] for s in (b["print_statements"] or [])]
        if statements:
            text += '\n```python\n' + '\n'.join(statements) + '\n```\n'
    text += '\n' + '\n\n'.join(result["limitations"]) + '\n'
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit", type=Path)
    parser.add_argument("--largest-prompt", type=Path)
    parser.add_argument("--output-prefix", type=Path)
    args = parser.parse_args()
    audit = args.audit.resolve()
    prefix = audit.name.removesuffix(".audit.json")
    prompt = args.largest_prompt.resolve() if args.largest_prompt else audit.with_name(prefix + ".largest_root_prompt.txt")
    output = args.output_prefix or audit.with_name(prefix + ".root_output")
    result = analyze(audit, prompt)
    Path(str(output) + ".json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    Path(str(output) + ".md").write_text(render(result))
    print(result["run_id"], result["output_totals"], result["criterion"]["covered_chars"])


if __name__ == "__main__":
    main()
