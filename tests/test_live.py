"""Opt-in research example. The default pytest command never executes it."""
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from loop_research.archive import read_json
from loop_research.cli import app
from loop_research.config import Config
from loop_research.harness import Harness

pytestmark = pytest.mark.live


@pytest.fixture
def live_workspace(tmp_path):
    source = Path(__file__).resolve().parents[1]
    config = Config.load(source / 'config.yaml')
    (tmp_path / 'config.yaml').write_text(yaml.safe_dump(config.model_dump(), sort_keys=False))
    Harness(tmp_path / 'harness')
    return tmp_path


def test_live_research_cited_table(live_workspace):
    root = live_workspace
    result = CliRunner().invoke(app, ['--root', str(root), 'research',
        'Identify the official website and current stable version of the Python programming language.',
        '--columns', 'project', '--columns', 'website', '--columns', 'stable_version',
        '--keys', 'project', '--language', 'en'])
    assert result.exit_code == 0, f'{result.output}\n{result.exception}'
    run_id = next(line.removeprefix('Archive: ') for line in result.stdout.splitlines() if line.startswith('Archive: '))
    archives = list((root / 'runs' / run_id).glob('*/output.json'))
    assert len(archives) == 1
    task_path = archives[0].parent
    output = read_json(archives[0])
    assert output['rows'], 'Live research did not produce a cited table'
    assert all(cell['sources'] for row in output['rows'] for cell in row['cells'].values())
    assert read_json(task_path / 'self_check.json')['ok'], 'Inspect self_check.json for evidence/coverage issues'
    assert (task_path / 'trajectory.jsonl').stat().st_size > 0
    assert (task_path / 'codex_calls.jsonl').stat().st_size > 0
