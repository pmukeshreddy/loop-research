"""Cited-table output for free-form research, independent of benchmark adapters."""
import json

from pydantic import BaseModel, ConfigDict, Field, create_model

from .benchmarks import OutputContract


def validate_research_spec(columns, keys, language):
    for name, values in (("Columns", columns), ("Keys", keys)):
        if not isinstance(values, list) or not values or not all(isinstance(value, str) and value.strip() for value in values):
            raise ValueError(f"{name} must be a nonempty list of names")
        if len(set(values)) != len(values):
            raise ValueError(f"{name} must be unique")
    if not set(keys).issubset(columns):
        raise ValueError("Keys must name selected columns")
    if not isinstance(language, str) or not language.strip():
        raise ValueError("Language must be nonempty")


class ResearchCell(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    value: str
    sources: list[str]
    quote: str


class ResearchData:
    def output_contract(self, task):
        columns, keys = task.spec["columns"], task.spec["keys"]
        validate_research_spec(columns, keys, task.language)
        cells = create_model("ResearchCells", __config__=ConfigDict(extra="forbid", strict=True),
            **{f"column_{i}": (ResearchCell, Field(alias=name)) for i, name in enumerate(columns)})
        row = create_model("ResearchRow", __config__=ConfigDict(extra="forbid", strict=True),
                           entity=(str, ...), cells=(cells, ...))
        table = create_model("ResearchTable", __config__=ConfigDict(extra="forbid", strict=True), rows=(list[row], ...))
        prompt = ("Return a JSON object with rows. Each row has entity and cells. "
            "Cells must have exactly these column keys: " + json.dumps(columns, ensure_ascii=False) +
            ". Use these columns as the unique entity key: " + json.dumps(keys, ensure_ascii=False) +
            ". Each cell has string value, sources (HTTP(S) URLs), and quote copied verbatim from fetched text. "
            "Write the answer in language " + task.language + ". Do not add citations inside value.")
        return OutputContract(table, prompt, {"rows": []})

    def to_submission(self, task, agent_output):
        return self.output_contract(task).model.model_validate(agent_output).model_dump(mode="json", by_alias=True)
