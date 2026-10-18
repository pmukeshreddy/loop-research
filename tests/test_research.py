import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

from loop_research.benchmarks import Task


def test_research_contract_and_submission_are_independent_of_benchmarks(output):
    from loop_research.research import ResearchData
    task = Task(task_id='fixture', benchmark='research', question='Fixture question', language='fr',
                spec={'columns': ['entity', 'value'], 'keys': ['entity']})
    adapter = ResearchData()
    contract = adapter.output_contract(task)
    assert contract.model.model_validate_json(json.dumps(output)).model_dump(by_alias=True) == output
    assert adapter.to_submission(task, output) == output
    assert adapter.to_submission(task, {'rows': []}) == {'rows': []}
    with pytest.raises(ValidationError):
        contract.model.model_validate({'rows': [{'entity': 'x', 'cells': {}}]})


@pytest.mark.parametrize('columns,keys,language', [([], ['entity'], 'en'), (['entity'], [], 'en'),
    (['entity'], ['unknown'], 'en'), (['entity', 'entity'], ['entity'], 'en'),
    (['entity'], ['entity', 'entity'], 'en'), ([' '], [' '], 'en'),
    (['entity'], ['entity'], ''), (['entity'], ['entity'], '  ')])
def test_research_contract_rejects_incomplete_specs(columns, keys, language):
    from loop_research.research import ResearchData
    task = Task(task_id='fixture', benchmark='research', question='Fixture question', language=language,
                spec={'columns': columns, 'keys': keys})
    with pytest.raises(ValueError):
        ResearchData().output_contract(task)


def test_research_adapter_import_does_not_load_a_benchmark():
    source = Path(__file__).resolve().parents[1] / 'src'
    result = subprocess.run([sys.executable, '-c',
        'import sys; from loop_research.research import ResearchData; '
        'assert not any(name.startswith(("loop_research.benchmarks.widesearch", "loop_research.benchmarks.wandr")) for name in sys.modules)'],
        env={**os.environ, 'PYTHONPATH': str(source)}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
