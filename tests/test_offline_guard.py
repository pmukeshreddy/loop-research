import subprocess

import pytest


def test_real_codex_exec_is_blocked_before_process_creation():
    with pytest.raises(AssertionError, match='Live codex exec is forbidden'):
        subprocess.run(['codex', 'exec', 'must never be sent'], check=True)
