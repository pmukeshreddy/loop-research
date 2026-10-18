from pathlib import Path

import pytest

from loop_research.archive import RunContext
from loop_research.benchmarks import Task
from loop_research.benchmarks.widesearch.data import WideSearchData
from loop_research.config import Config


def load_config():
    return Config.load(Path(__file__).resolve().parents[1] / "config.yaml")


@pytest.fixture
def config():
    return load_config()


@pytest.fixture
def ctx(tmp_path, config):
    return RunContext(tmp_path, "unit", config, "fixture")


@pytest.fixture
def task():
    return Task(task_id="fixture", benchmark="widesearch", question="Hand-written fixture",
                spec={"columns": ["entity", "value"], "keys": ["entity"]}, language="en")


@pytest.fixture
def benchmark(tmp_path, config):
    benchmark = WideSearchData(tmp_path, config)
    benchmark.code = widesearch_source("data/vendor/widesearch", ".verification/widesearch")
    return benchmark


def widesearch_source(prepared, verification):
    root = Path(__file__).resolve().parents[1]
    for relative in (prepared, verification):
        path = root / relative
        if path.exists():
            return path
    pytest.fail("Pinned WideSearch files are missing; run loop-research prepare-data before pytest")


@pytest.fixture
def widesearch_download():
    return widesearch_source("data/downloads/widesearch", ".verification/widesearch-dataset")


@pytest.fixture
def output():
    return {"rows": [{"entity": "fixture-a", "cells": {
        "entity": {"value": "fixture-a", "sources": ["https://example.org"], "quote": "fixture-a"},
        "value": {"value": "fixture-value", "sources": ["https://example.org"], "quote": "fixture-value"},
    }}]}
