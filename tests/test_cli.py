import base64
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest
import yaml
from typer.testing import CliRunner


def cli_module():
    return importlib.import_module('loop_research.cli')


def save_config(root, config, filename='config.yaml'):
    (root / filename).write_text(yaml.safe_dump(config.model_dump()))


@pytest.fixture
def stream_module(monkeypatch):
    module = ModuleType('loop_research.stream')
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return module


def test_init_is_idempotent_and_preserves_config_and_verification(tmp_path, config):
    cli = cli_module()
    runner = CliRunner()
    result = runner.invoke(cli.app, ['--root', str(tmp_path), 'init'])
    assert result.exit_code == 0, f'{result.output}\n{result.exception}'
    for name in ('harness', 'runs', 'reports', 'data', 'docs'):
        assert (tmp_path / name).is_dir()
    assert (tmp_path / 'harness/.git').is_dir()
    assert (tmp_path / 'harness/harness_state.json').is_file()
    assert (tmp_path / 'config.yaml').read_bytes() == (Path(__file__).resolve().parents[1] / 'config.yaml').read_bytes()
    verification = tmp_path / 'docs/VERIFIED.md'
    assert 'unverified' in verification.read_text().lower()
    verification.write_text('Existing verified evidence\n')
    config.data.seed = 73
    save_config(tmp_path, config)
    again = runner.invoke(cli.app, ['--root', str(tmp_path), 'init'])
    assert again.exit_code == 0, f'{again.output}\n{again.exception}'
    assert verification.read_text() == 'Existing verified evidence\n'
    assert yaml.safe_load((tmp_path / 'config.yaml').read_text())['data']['seed'] == 73


def test_init_uses_packaged_template_outside_a_repository(tmp_path, config, monkeypatch):
    cli = cli_module()
    package = tmp_path / 'site-packages/loop_research'
    package.mkdir(parents=True)
    config.data.seed = 73
    save_config(package, config)
    monkeypatch.setattr(cli, '__file__', str(package / 'cli.py'))
    workspace = tmp_path / 'workspace'
    result = CliRunner().invoke(cli.app, ['--root', str(workspace), 'init'])
    assert result.exit_code == 0, f'{result.output}\n{result.exception}'
    assert (workspace / 'config.yaml').read_bytes() == (package / 'config.yaml').read_bytes()
    assert (workspace / 'harness/harness_state.json').is_file()


def test_research_uses_explicit_config_and_prints_cited_table(tmp_path, config, output, stream_module):
    cli = cli_module()
    config.data.seed = 73
    save_config(tmp_path, config, 'custom.yaml')
    def research(root, settings, question, columns, keys, language):
        assert root == tmp_path and settings.data.seed == 73
        assert question == 'Find the fixture' and columns == ['entity', 'value']
        assert keys == ['entity'] and language == 'zh'
        return {'run_id': 'research-fixture', 'output': output, 'self_check': {'ok': True, 'issues': []}}
    stream_module.research = research
    result = CliRunner().invoke(cli.app, ['--root', str(tmp_path), '--config', 'custom.yaml',
        'research', 'Find the fixture', '--columns', 'entity', '--columns', 'value', '--keys', 'entity', '--language', 'zh'])
    assert result.exit_code == 0, f'{result.output}\n{result.exception}'
    assert '| entity | value |' in result.stdout
    assert '[1](<https://example.org>)' in result.stdout
    assert 'Archive: research-fixture' in result.stdout


@pytest.mark.parametrize('missing', ['--columns', '--keys', '--language'])
def test_research_requires_each_explicit_output_option(tmp_path, missing):
    options = {'--columns': 'entity', '--keys': 'entity', '--language': 'en'}
    args = [item for key, value in options.items() if key != missing for item in (key, value)]
    result = CliRunner().invoke(cli_module().app, ['--root', str(tmp_path), 'research', 'Fixture question', *args])
    assert result.exit_code == 2, f'{result.output}\n{result.exception}'
    assert missing in result.output and not (tmp_path / 'runs').exists()


def test_research_failure_keeps_archive_visible_and_returns_nonzero(tmp_path, config, stream_module):
    save_config(tmp_path, config)
    stream_module.research = lambda *args: {
        'run_id': 'failed-fixture', 'output': {'rows': []},
        'self_check': {'ok': False, 'issues': ['worker_error']}, 'error': 'fixture timeout',
    }
    result = CliRunner().invoke(cli_module().app, ['--root', str(tmp_path), 'research', 'Fixture question',
        '--columns', 'entity', '--keys', 'entity', '--language', 'en'])
    assert result.exit_code == 1
    assert 'Archive: failed-fixture' in result.stdout
    assert 'fixture timeout' in result.output


@pytest.mark.parametrize('benchmark,no_learning', [('widesearch', False), ('wandr', True)])
def test_stream_routes_benchmark_and_learning_mode(tmp_path, config, stream_module, benchmark, no_learning):
    cli = cli_module()
    save_config(tmp_path, config)
    def stream(root, settings, selected, no_learning=False, base=None, resume=None):
        assert root == tmp_path and selected == benchmark
        assert no_learning is (benchmark == 'wandr')
        assert base is None and resume is None
        return {'run_id': 'stream-fixture'}
    stream_module.stream = stream
    args = ['--root', str(tmp_path), 'stream', '--benchmark', benchmark]
    if no_learning:
        args.append('--no-learning')
    result = CliRunner().invoke(cli.app, args)
    assert result.exit_code == 0, f'{result.output}\n{result.exception}'
    assert 'stream-fixture' in result.stdout
    assert 'reports/stream-fixture/stream.json' in result.stdout


@pytest.mark.parametrize('arguments', [['stream', '--benchmark', 'unknown'], ['research', '  ']])
def test_invalid_research_requests_fail_before_loading_config(tmp_path, arguments):
    result = CliRunner().invoke(cli_module().app, ['--root', str(tmp_path), *arguments])
    assert result.exit_code == 2, f'{result.output}\n{result.exception}'
    assert not (tmp_path / 'runs').exists()


def test_stream_help_has_single_no_learning_switch():
    result = CliRunner().invoke(cli_module().app, ['stream', '--help'])
    assert result.exit_code == 0
    assert '--no-learning' in result.stdout
    assert '--no-no-learning' not in result.stdout


@pytest.mark.parametrize('options,base,resume', [(['--base', 'a' * 40], 'a' * 40, None),
                                               (['--resume', 'stream-fixture'], None, 'stream-fixture')])
def test_stream_forwards_explicit_lineage_options(tmp_path, config, stream_module, options, base, resume):
    save_config(tmp_path, config)
    def stream(root, settings, selected, *, no_learning, base, resume):
        assert (base, resume) == expected
        return {'run_id': 'stream-fixture'}
    expected = (base, resume)
    stream_module.stream = stream
    result = CliRunner().invoke(cli_module().app, ['--root', str(tmp_path), 'stream', '--benchmark', 'widesearch', *options])
    assert result.exit_code == 0, f'{result.output}\n{result.exception}'


def test_stream_resume_requires_a_run_id():
    result = CliRunner().invoke(cli_module().app, ['stream', '--benchmark', 'widesearch', '--resume'])
    assert result.exit_code == 2


def test_prepare_data_uses_both_pinned_adapters(tmp_path, config, monkeypatch):
    cli = cli_module()
    from loop_research.benchmarks.wandr.data import WandrData
    save_config(tmp_path, config)
    calls = []
    def prepare(self):
        calls.append((type(self).__name__, self.root, self.config.model_dump()))
    monkeypatch.setattr(cli.WideSearchData, 'prepare', prepare)
    monkeypatch.setattr(WandrData, 'prepare', prepare)
    result = CliRunner().invoke(cli.app, ['--root', str(tmp_path), 'prepare-data'])
    assert result.exit_code == 0, f'{result.output}\n{result.exception}'
    assert [name for name, _, _ in calls] == ['WideSearchData', 'WandrData']
    assert all(root == tmp_path and data == config.model_dump() for _, root, data in calls)


@pytest.mark.parametrize('authenticated,isolation_ok', [(False, True), (True, False), (True, True)])
def test_verify_checks_auth_sources_and_isolation_without_live_calls(tmp_path, config, monkeypatch, authenticated, isolation_ok):
    cli = cli_module()
    from loop_research import isolation
    from loop_research.benchmarks.wandr.grader import WandrBenchmark
    config.verify.codex_timeout_s = 1.25
    save_config(tmp_path, config)
    required = '--sandbox --skip-git-repo-check --cd --output-last-message --output-schema --model --config --json --color --ephemeral --ignore-user-config read-only stdin'
    def command(args, **kwargs):
        assert kwargs['timeout'] == 1.25
        assert args[1:] in (['--version'], ['exec', '--help'], ['login', 'status'])
        text = {'--version': 'codex fixture', 'exec': required,
                'login': 'Logged in using ChatGPT' if authenticated else 'Logged in using an API key'}[args[1]]
        return subprocess.CompletedProcess(args, 0, text, '')
    def probe():
        if not isolation_ok:
            raise RuntimeError('fixture isolation unavailable')
        return 'fixture kernel checks passed'
    monkeypatch.setattr(cli.subprocess, 'run', command)
    monkeypatch.setattr(cli, 'verify_rlm', lambda: 'pinned fixture')
    monkeypatch.setattr(cli.WideSearchData, 'verify_code', lambda self: None)
    monkeypatch.setattr(cli.WideSearchData, 'verify_data', lambda self: None)
    monkeypatch.setattr(WandrBenchmark, 'verify', lambda self: [('WANDR browser', True, 'ready')])
    monkeypatch.setattr(isolation, 'verify_isolation', probe)
    result = CliRunner().invoke(cli.app, ['--root', str(tmp_path), 'verify'])
    assert result.exit_code == (0 if authenticated and isolation_ok else 1), f'{result.output}\n{result.exception}'
    assert 'ChatGPT' in result.output and 'WANDR browser' in result.output and 'isolation' in result.output.lower()
    if not authenticated:
        assert 'FAIL\tCodex ChatGPT auth' in result.output
    if not isolation_ok:
        assert 'fixture isolation unavailable' in result.output


def test_rlm_verification_checks_import_location_and_installed_hash(tmp_path, monkeypatch):
    cli = cli_module()
    source = tmp_path / 'rlm/__init__.py'
    source.parent.mkdir()
    source.write_text('# fixture package\n')
    digest = base64.urlsafe_b64encode(hashlib.sha256(source.read_bytes()).digest()).decode().rstrip('=')
    class Entry:
        hash = SimpleNamespace(mode='sha256', value=digest)
        def __str__(self):
            return 'rlm/__init__.py'
    distribution = SimpleNamespace(
        files=[Entry()],
        read_text=lambda name: json.dumps({'url': 'https://github.com/alexzhang13/rlm.git', 'vcs_info': {
            'vcs': 'git', 'commit_id': 'd04208afbad29ca675ab13478c40ee8bebc84bfe'}}),
        locate_file=lambda path: tmp_path / str(path),
    )
    monkeypatch.setattr(cli.metadata, 'distribution', lambda name: distribution)
    monkeypatch.setattr(cli.importlib, 'import_module', lambda name: SimpleNamespace(__file__=str(source)))
    assert 'd04208a' in cli.verify_rlm()
    source.write_text('# altered package\n')
    with pytest.raises(ValueError, match='integrity'):
        cli.verify_rlm()


def test_report_works_without_model_dataset_or_configuration(tmp_path):
    result = CliRunner().invoke(cli_module().app, ['--root', str(tmp_path), 'report'])
    assert result.exit_code == 0, f'{result.output}\n{result.exception}'
    assert (tmp_path / 'reports/summary.md').is_file()


def test_research_forwards_trace_option(tmp_path, config, output, stream_module):
    save_config(tmp_path, config)
    def research(*args, trace=False):
        assert trace is True
        return {'run_id': 'traced-fixture', 'output': output}
    stream_module.research = research
    result = CliRunner().invoke(cli_module().app, ['--root', str(tmp_path), 'research', 'Fixture',
        '--columns', 'entity', '--columns', 'value', '--keys', 'entity', '--language', 'en', '--trace'])
    assert result.exit_code == 0, result.exception
    assert 'Archive: traced-fixture' in result.stdout
