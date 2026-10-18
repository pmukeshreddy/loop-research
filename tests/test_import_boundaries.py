"""Inspect function-local imports too, so deferred imports cannot bypass the boundary."""
import ast
from importlib.util import resolve_name
from pathlib import Path

import pytest


def import_graph():
    root = Path(__file__).resolve().parents[1] / "src"
    paths = {}
    for path in (root / "loop_research").rglob("*.py"):
        parts = list(path.relative_to(root).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        paths[".".join(parts)] = path
    graph = {name: set() for name in paths}
    for name, path in paths.items():
        package = name if path.name == "__init__.py" else name.rpartition(".")[0]
        targets = set()
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                targets.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                base = resolve_name("." * node.level + (node.module or ""), package) if node.level else node.module
                targets.add(base)
                targets.update(base + "." + alias.name for alias in node.names)
            elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
                function = node.func
                if (isinstance(function, ast.Attribute) and function.attr == "import_module") or (
                        isinstance(function, ast.Name) and function.id == "__import__"):
                    value = node.args[0].value
                    if isinstance(value, str):
                        targets.add(resolve_name(value, package) if value.startswith(".") else value)
        for target in targets:
            parts = target.split(".")
            graph[name].update(".".join(parts[:i]) for i in range(1, len(parts) + 1)
                               if ".".join(parts[:i]) in graph)
    return graph


def reachable(graph, start, stop=()):
    seen, pending = set(), [start]
    while pending:
        name = pending.pop()
        if name in seen or name in stop:
            continue
        seen.add(name)
        pending.extend(graph[name] - seen)
    return seen


@pytest.mark.parametrize("module", ["agent", "refine", "harness", "selfcheck", "session", "repl_tools", "rlm_codex_client"])
def test_research_and_refinement_cannot_import_graders_or_answers(module):
    graph = import_graph()
    found = reachable(graph, "loop_research." + module)
    assert not any(name.endswith((".grader", ".answers")) for name in found)
