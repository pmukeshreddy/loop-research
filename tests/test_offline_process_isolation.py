"""Offline transports must not contend with an unrelated live backend's slots."""
import fcntl
import os
from pathlib import Path
import subprocess
import sys


def test_offline_backend_ignores_occupied_ambient_slots(tmp_path):
    ambient = tmp_path / 'ambient'
    slots = ambient / f'loop-codex-slots-{os.getuid()}'
    slots.mkdir(parents=True)
    case = tmp_path / 'case'
    case.mkdir()
    source = Path(__file__).with_name('conftest.py')
    (case / 'conftest.py').write_text(
        'import importlib.util\n'
        f'spec = importlib.util.spec_from_file_location("offline_fixture_probe", {str(source)!r})\n'
        'module = importlib.util.module_from_spec(spec)\n'
        'spec.loader.exec_module(module)\n'
        'globals().update({k: v for k, v in vars(module).items() if not k.startswith("__")})\n')
    (case / 'test_probe.py').write_text('''
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from loop_research.codex_backend import CodexBackend

def test_fake_transport_while_ambient_slot_is_occupied(ctx):
    ctx.config.codex.max_concurrent = 1
    ctx.config.codex.timeout_s = 0.1
    ctx.config.codex.max_retries = 0
    def runner(command, **kwargs):
        Path(command[command.index('--output-last-message') + 1]).write_text('complete')
        return SimpleNamespace(returncode=0, stdout='', stderr='')
    assert CodexBackend(ctx, runner=runner).complete('fixture', purpose='root') == 'complete'
    child_temp = subprocess.check_output(
        [sys.executable, '-c', 'import tempfile; print(tempfile.gettempdir())'], text=True).strip()
    assert Path(child_temp).resolve() == Path(tempfile.gettempdir()).resolve()
    assert Path(child_temp).resolve() != Path(os.environ['AMBIENT_TEST_TMP']).resolve()
''')
    env = {**os.environ, 'TMPDIR': str(ambient), 'AMBIENT_TEST_TMP': str(ambient),
           'PYTHONPATH': str(source.parents[1] / 'src')}
    with (slots / '0').open('a') as occupied:
        fcntl.flock(occupied, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(case)],
                                env=env, cwd=source.parents[1], capture_output=True,
                                text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
