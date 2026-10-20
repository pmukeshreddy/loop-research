"""Whole iteration references preserve full streams and exact control messages."""
import copy
import hashlib

import pytest

from loop_research.codex_backend import INSTRUCTION
from loop_research.rlm_codex_client import transcript


def module():
    from loop_research import refine_feedback
    return refine_feedback


def block(stdout, stderr='', *, number=0):
    return {'block': number, 'code': 'print(value)', 'stdout': stdout, 'stderr': stderr,
            'execution_time': 0.1, 'answer_ready': False, 'final_answer': None,
            'derived_stream_failure': bool(stderr)}


def history(limit=1_048_576):
    return module().FeedbackHistory(
        [{'role': 'system', 'content': 'unchanged system 雪'},
         {'role': 'user', 'content': 'unchanged control'}], limit)


def test_complete_feedback_under_limit_is_byte_identical_even_above_twenty_thousand_chars():
    h = history()
    h.append_response('```repl\nprint(value)\n```')
    blocks = [block('whole stdout 雪\n' * 3000, 'whole stderr\n' * 2000)]
    h.append_output(1, blocks)
    before = copy.deepcopy(h.messages)
    prompt, events = h.prepare()
    assert prompt == transcript(before) and events == [] and h.messages == before
    assert blocks[0]['stdout'] in prompt and blocks[0]['stderr'] in prompt


def test_exact_backend_boundary_and_one_character_overflow_use_full_serialized_cost():
    h = history()
    h.append_response('control response')
    h.append_output(1, [block('data' * 5000)])
    full_size = len(INSTRUCTION + transcript(h.messages))
    h.max_prompt_chars = full_size
    original = copy.deepcopy(h.messages)
    assert h.prepare() == (transcript(original), [])
    h.max_prompt_chars = full_size - 1
    prompt, events = h.prepare()
    assert len(events) == 1
    event = events[0]
    assert event['backend_prompt_chars_before'] == full_size
    assert event['backend_prompt_chars_after'] == len(INSTRUCTION + prompt)
    assert event['net_saving'] == full_size - len(INSTRUCTION + prompt) > 0
    assert event['receipt'] == h.messages[-1]['content']
    assert event['receipt_chars'] == len(event['receipt'])
    assert event['receipt_sha256'] == hashlib.sha256(event['receipt'].encode()).hexdigest()
    assert h.messages[:-1] == original[:-1]


def test_cumulative_overflow_chooses_largest_net_saving_and_keeps_references_permanent():
    h = history()
    h.append_response('first exact assistant response')
    h.append_output(1, [block('a' * 10_000)])
    h.append_response('second exact assistant response')
    h.append_output(2, [block('b' * 20_000)])
    original = copy.deepcopy(h.messages)
    h.max_prompt_chars = len(INSTRUCTION + transcript(original)) - 1
    _, events = h.prepare()
    assert [event['iteration'] for event in events] == [2]
    assert 'a' * 10_000 in h.messages[3]['content']
    reference = h.messages[5]['content']
    h.append_response('third exact assistant response')
    h.append_output(3, [block('small new inspection')])
    prompt, events = h.prepare()
    assert events == [] and reference in prompt and 'small new inspection' in prompt
    assert h.messages[0:3] == original[0:3] and h.messages[4] == original[4]


def test_equal_net_savings_tie_breaks_by_iteration_not_insertion_order():
    h = history()
    h.append_response('earlier response')
    h.append_output(2, [block('same content' * 1000)])
    h.append_response('later response')
    h.append_output(1, [block('same content' * 1000)])
    h.max_prompt_chars = len(INSTRUCTION + transcript(h.messages)) - 1
    assert [event['iteration'] for event in h.prepare()[1]] == [1]


def test_receipt_identifies_all_blocks_and_stderr_without_any_stream_preview():
    blocks = [block('first full stdout', number=0), block('second full stdout', 'EXACT ERROR 雪', number=1)]
    record = module().feedback_record(7, blocks)
    receipt = module().output_reference(record)
    assert '"stderr_present":true' in receipt
    assert '"derived_stream_failure":true' in receipt
    assert 'repl_output(7)' in receipt
    assert all(value not in receipt for row in blocks for value in (row['stdout'], row['stderr']) if value)
    assert record['blocks'] == blocks
    assert record['feedback'] == module().feedback_text(blocks)
    blocks[0]['stdout'] = 'mutated'
    assert record['blocks'][0]['stdout'] == 'first full stdout'


@pytest.mark.parametrize('stdout', ['tiny', 'large profitable output' * 1000])
def test_unfit_controls_or_nonprofitable_outputs_fail_without_mutating_history(stdout):
    h = history(limit=1)
    h.append_response('large exact assistant control' * 100)
    h.append_output(1, [block(stdout)])
    before = copy.deepcopy(h.messages)
    with pytest.raises(module().FeedbackTooLarge, match='control'):
        h.prepare()
    assert h.messages == before


def test_no_code_message_remains_control_and_is_never_externalized():
    h = history(limit=1)
    h.append_response('No code this turn.')
    h.append_output(1, [])
    before = copy.deepcopy(h.messages)
    with pytest.raises(module().FeedbackTooLarge):
        h.prepare()
    assert h.messages == before
    assert h.messages[-1]['content'].startswith('No REPL code was executed.')
