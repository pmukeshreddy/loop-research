"""Sub-call transport failures remain errors and configured concurrency is honored."""
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from loop_research.rlm_codex_client import CodexRLM
from test_worker import session_factory


class Transport:
    @property
    def last_usage(self):
        return {'input_tokens': 1, 'output_tokens': 1}

    def complete(self, prompt, **options):
        if prompt == 'fail':
            raise RuntimeError('fixture transport unavailable')
        return prompt


@pytest.mark.parametrize('batched', [False, True])
def test_transport_failure_raises_instead_of_returning_error_text(batched):
    rlm = CodexRLM(Transport(), root_model='fixture', sub_model='fixture')
    with rlm._spawn_completion_context('fixture context') as (_, env):
        with pytest.raises(RuntimeError, match='fixture transport unavailable'):
            if batched:
                env._llm_query_batched(['successful response', 'fail'])
            else:
                env._llm_query('fail')


def test_successful_error_looking_model_text_is_preserved():
    rlm = CodexRLM(Transport(), root_model='fixture', sub_model='fixture')
    with rlm._spawn_completion_context('fixture context') as (_, env):
        value = 'Error: this is legitimate model response content'
        assert env._llm_query(value) == value
        assert env._llm_query_batched([value, 'second']) == [value, 'second']


def test_flat_batch_obeys_configured_subcall_concurrency():
    two_started, third_started, release = threading.Event(), threading.Event(), threading.Event()
    lock = threading.Lock()
    class Blocking(Transport):
        active = 0
        peak = 0
        def complete(self, prompt, **options):
            with lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
                if self.active == 2:
                    two_started.set()
                if self.active > 2:
                    third_started.set()
            try:
                assert release.wait(5)
                return super().complete(prompt, **options)
            finally:
                with lock:
                    self.active -= 1
    transport = Blocking()
    rlm = CodexRLM(transport, root_model='fixture', sub_model='fixture', max_concurrent_subcalls=2)
    with rlm._spawn_completion_context('fixture context') as (_, env), ThreadPoolExecutor(1) as pool:
        result = pool.submit(env._llm_query_batched, [str(i) for i in range(8)])
        try:
            assert two_started.wait(5)
            exceeded = third_started.wait(.2)
        finally:
            release.set()
        assert result.result(5) == [str(i) for i in range(8)]
        assert not exceeded
        assert transport.peak == 2


@pytest.mark.parametrize('batched', [False, True])
def test_subcall_socket_uses_configured_task_timeout(batched):
    release = threading.Event()
    class Blocked(Transport):
        def complete(self, prompt, **options):
            assert release.wait(5)
            return prompt
    rlm = CodexRLM(Blocked(), root_model='fixture', sub_model='fixture', max_timeout=.05)
    with rlm._spawn_completion_context('fixture context') as (_, env):
        try:
            with pytest.raises(RuntimeError, match='timed out'):
                if batched:
                    env._llm_query_batched(['one', 'two'])
                else:
                    env._llm_query('one')
        finally:
            release.set()


def test_large_flat_batch_through_real_isolated_worker(task, benchmark, output, session_factory):
    import json
    from loop_research.agent import run_task
    from test_worker import code_reply, final_code
    def reply(prompt, options):
        if options['purpose'] == 'sub':
            return prompt
        return code_reply('import json\n'
                          'prompts = [json.dumps({"index": i}) for i in range(22)]\n'
                          'values = [json.loads(s) for s in llm_query_batched(prompts)]\n'
                          'assert [v["index"] for v in values] == list(range(22))\n' + final_code(output))
    session = session_factory(reply)
    assert run_task(task, benchmark, session).output == output
    assert sum(options['purpose'] == 'sub' for _, options in session.backend.calls) == 22


@pytest.mark.parametrize('batched', [False, True])
def test_child_failures_raise_instead_of_becoming_response_text(batched):
    rlm = CodexRLM(Transport(), root_model='fixture', sub_model='fixture', max_depth=2)
    with rlm._spawn_completion_context('fixture context') as (_, env):
        def failure(*args):
            raise RuntimeError('fixture child unavailable')
        env.subcall_fn = failure
        with pytest.raises(RuntimeError, match='fixture child unavailable'):
            if batched:
                env._rlm_query_batched(['one', 'two'])
            else:
                env._rlm_query('one')
