"""The research prompt documents public argument types; host checks stay strict."""
from types import SimpleNamespace

import pytest

from loop_research.agent import make_prompt
from loop_research.repl_tools import ResearchTools


@pytest.fixture
def tool_prompt(task, config):
    contract = SimpleNamespace(prompt="Fixture output contract", schema={"type": "object"})
    prompt, _, _ = make_prompt(task, contract, [], as_of="2024-01-01", config=config)
    return prompt.split("TOOLS\n", 1)[1].split("CONSTRAINT IDS\n", 1)[0]


def test_constraint_contract_declares_bool_and_source_specific_text(tool_prompt):
    line = next(line for line in tool_prompt.splitlines() if line.startswith("check_constraint("))
    assert "row: str, constraint: str, verdict: bool, url: str, quote: str" in line
    assert "True or False" in line
    assert "strings or integers" in line
    assert "nonempty strings" in line
    assert "quoted URL's fetched text" in line


@pytest.mark.parametrize("prefix,fragments", [
    ("search(query,", ("nonempty string", "integer", "1 <= k <= 50")),
    ("search_many(queries,", ("queries: list[str]", "search's k range")),
    ("fetch(url,", ("HTTP(S) URL string", "focus: str")),
    ("fetch_many(urls,", ("urls: list[str]", "focus: str")),
    ("harness.create(", ("string arguments", "nonempty", "positive integer", "bare entry id")),
    ("refine.run(", ("focus: str or None", "id: nonempty str", "commit SHA")),
    ("record_discovery(", ("query: str", "entities: list[str]", "exact previously searched query", "nonempty")),
])
def test_other_public_tool_argument_contracts_are_explicit(tool_prompt, prefix, fragments):
    line = next(line for line in tool_prompt.splitlines() if line.startswith(prefix))
    for fragment in fragments:
        assert fragment in line


@pytest.fixture
def tools_with_evidence(ctx):
    tools = ResearchTools(None, ctx)
    tools.evidence["fetched"] = {"https://example.org/": ["Fixture supporting quotation."]}
    return tools


@pytest.mark.parametrize("verdict", ["pass", "true", 1, 0, None, []])
def test_nonboolean_constraint_verdicts_raise_without_recording_or_coercion(tools_with_evidence, verdict):
    tools = tools_with_evidence
    before = tools.snapshot()
    with pytest.raises(ValueError, match="boolean verdict"):
        tools.check_constraint("/rows/0", "question", verdict, "https://example.org/", "supporting quotation")
    assert tools.snapshot() == before


@pytest.mark.parametrize("verdict", [True, False])
def test_both_boolean_constraint_verdicts_are_recorded_exactly(tools_with_evidence, verdict):
    tools = tools_with_evidence
    assert tools.check_constraint("/rows/0", "question", verdict, "https://example.org/", "supporting quotation") is True
    assert tools.snapshot()["checks"] == [{"row": "/rows/0", "constraint": "question", "verdict": verdict,
                                           "url": "https://example.org/", "quote": "supporting quotation"}]
    assert type(tools.snapshot()["checks"][0]["verdict"]) is bool
