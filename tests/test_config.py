from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from loop_research.config import Config


@pytest.fixture
def document():
    return yaml.safe_load((Path(__file__).resolve().parents[1] / "config.yaml").read_text())


def test_constructor_does_not_supply_configuration_defaults():
    with pytest.raises(ValidationError):
        Config()


@pytest.mark.parametrize("section,field", [
    ("models", "root"), ("models", "sub"), ("models", "reasoning_effort"),
    ("models", "refine"), ("models", "judge"),
    ("codex", "bin"), ("codex", "max_concurrent"), ("codex", "timeout_s"),
    ("codex", "max_retries"), ("codex", "log_full_text"),
    ("rlm", "max_iterations"), ("rlm", "max_depth"),
    ("agent", "task_timeout_s"), ("agent", "max_codex_calls"),
    ("data", "seed"), ("data", "languages"),
    ("wandr", "seed"), ("wandr", "final_n_tasks"),
    ("harness", "retrieval_limit"), ("stream", "rolling_window"),
])
def test_missing_values_are_rejected(document, tmp_path, section, field):
    del document[section][field]
    path = tmp_path / "missing.yaml"
    path.write_text(yaml.safe_dump(document))
    with pytest.raises(ValidationError) as error:
        Config.load(path)
    assert (section, field) in {tuple(item["loc"]) for item in error.value.errors()}


@pytest.mark.parametrize("section,field,value", [
    ("models", "root", 1), ("models", "sub", True), ("models", "reasoning_effort", 1),
    ("models", "root", ""), ("models", "sub", ""), ("models", "reasoning_effort", ""),
    ("models", "refine", False), ("models", "refine", ""),
    ("models", "judge", 123), ("models", "judge", ""),
    ("codex", "bin", 1), ("codex", "bin", ""),
    ("codex", "max_concurrent", "4"), ("codex", "max_concurrent", True),
    ("codex", "max_concurrent", 1.5), ("codex", "max_concurrent", 0),
    ("codex", "timeout_s", "600"), ("codex", "timeout_s", True),
    ("codex", "timeout_s", 0), ("codex", "timeout_s", float("inf")),
    ("codex", "max_retries", -1), ("codex", "max_retries", True),
    ("codex", "log_full_text", "false"), ("codex", "log_full_text", 0),
    ("rlm", "max_iterations", 0), ("rlm", "max_iterations", "30"),
    ("rlm", "max_depth", 0), ("rlm", "max_depth", True),
    ("agent", "task_timeout_s", 0), ("agent", "task_timeout_s", "3600"),
    ("agent", "task_timeout_s", float("nan")),
    ("agent", "max_codex_calls", 0), ("agent", "max_codex_calls", 1.5),
    ("data", "seed", "42"), ("data", "seed", -1),
    ("data", "languages", []), ("data", "languages", ["en", "en"]),
    ("data", "languages", ["fr"]), ("data", "languages", "en"),
    ("wandr", "seed", True), ("wandr", "seed", -1),
    ("wandr", "final_n_tasks", 0), ("wandr", "final_n_tasks", "50"),
    ("harness", "retrieval_limit", 0), ("harness", "retrieval_limit", "10"),
    ("harness", "retrieval_limit", True), ("harness", "retrieval_limit", 1.5),
    ("stream", "rolling_window", 0), ("stream", "rolling_window", "10"),
    ("stream", "rolling_window", True), ("stream", "rolling_window", 1.5),
])
def test_invalid_values_are_rejected(document, section, field, value):
    document[section][field] = value
    with pytest.raises(ValidationError) as error:
        Config.model_validate(document)
    assert any(tuple(item["loc"])[:2] == (section, field) for item in error.value.errors())


@pytest.mark.parametrize("section", [None, "models", "codex", "rlm", "agent", "data", "wandr", "harness", "stream"])
def test_unrecognized_settings_are_rejected(document, section):
    target = document if section is None else document[section]
    target["unexpected"] = True
    with pytest.raises(ValidationError):
        Config.model_validate(document)


@pytest.mark.parametrize("section", ["models", "codex", "rlm", "agent", "data", "wandr", "harness", "stream"])
def test_missing_sections_are_rejected(document, section):
    del document[section]
    with pytest.raises(ValidationError) as error:
        Config.model_validate(document)
    assert (section,) in {tuple(item["loc"]) for item in error.value.errors()}


@pytest.mark.parametrize("section", ["gate", "reflect", "skills", "loop", "final"])
def test_removed_sections_are_rejected(document, section):
    document[section] = {}
    with pytest.raises(ValidationError) as error:
        Config.model_validate(document)
    assert (section,) in {tuple(item["loc"]) for item in error.value.errors()}


@pytest.mark.parametrize("section,field,value", [
    ("models", "reflect", None), ("data", "split", {"train": .6, "val": .2, "test": .2}),
])
def test_removed_fields_are_rejected(document, section, field, value):
    document[section][field] = value
    with pytest.raises(ValidationError) as error:
        Config.model_validate(document)
    assert (section, field) in {tuple(item["loc"]) for item in error.value.errors()}


def test_config_accepts_explicit_null_models_and_unbounded_wandr_subset(document):
    for key in ("gate", "reflect", "skills", "loop", "final"):
        document.pop(key, None)
    document["models"] = {key: None for key in ("root", "sub", "refine", "judge", "reasoning_effort")}
    document["data"].pop("split", None)
    document["wandr"]["final_n_tasks"] = None
    document["harness"] = {"retrieval_limit": 10}
    document["stream"] = {"rolling_window": 10}
    loaded = Config.model_validate(document)
    assert loaded.models.judge is loaded.models.refine is None
    assert loaded.wandr.final_n_tasks is None
    assert loaded.harness.retrieval_limit == loaded.stream.rolling_window == 10


def test_load_preserves_explicit_values(document, tmp_path):
    document["codex"]["max_retries"] = 0
    document["codex"]["timeout_s"] = 1.25
    document["harness"] = {"retrieval_limit": 2}
    document["stream"] = {"rolling_window": 3}
    document["models"]["judge"] = "fixture-judge"
    path = tmp_path / "configured.yaml"
    path.write_text(yaml.safe_dump(document))
    loaded = Config.load(path)
    assert loaded.codex.max_retries == 0
    assert loaded.codex.timeout_s == 1.25
    assert loaded.harness.retrieval_limit == 2
    assert loaded.stream.rolling_window == 3
    assert loaded.judge_label == "codex/fixture-judge"


def test_assignment_keeps_strict_validation(config):
    with pytest.raises(ValidationError):
        config.codex.max_concurrent = "4"


@pytest.mark.parametrize("judge,label", [(None, "codex/default"), ("fixture-judge", "codex/fixture-judge")])
def test_judge_label_uses_judge_instead_of_root(config, judge, label):
    config.models.root = "fixture-root"
    config.models.judge = judge
    assert config.judge_label == label
