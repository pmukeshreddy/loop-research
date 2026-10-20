"""Lossless, whole-iteration references for oversized refinement feedback.

Only feedback messages may change representation. Model responses and control
messages remain exact; complete output records remain independently accessible.
"""
import copy
import hashlib
import json

from .codex_backend import INSTRUCTION
from .rlm_codex_client import transcript


OUTPUT_TRANSPORT = 'whole-iteration-reference-v1'
NO_CODE = 'No REPL code was executed. Inspect the complete context and submit a validated proposal with answer.'


class FeedbackTooLarge(ValueError):
    """The complete control transcript and profitable references cannot fit."""


def _sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def initial_messages(instructions, limits):
    return [{'role': 'system', 'content': instructions}, {'role': 'user',
        'content': 'Inspect the complete context and proposal_schema variables, evaluate every supplied candidate '
                   'and occurrence, and produce the evidence-backed proposal.\nLimits: ' + json.dumps(limits)}]


def feedback_text(blocks):
    return '\n\n'.join(f"Block {item['block']} stdout:\n{item['stdout']}\nstderr:\n{item['stderr']}"
                      for item in blocks) if blocks else NO_CODE


def feedback_record(iteration, blocks):
    return {'iteration': iteration, 'blocks': copy.deepcopy(blocks), 'feedback': feedback_text(blocks)}


def output_identity(record):
    return {'iteration': record['iteration'], 'feedback_chars': len(record['feedback']),
            'feedback_sha256': _sha(record['feedback']), 'blocks_sha256': _sha(_json(record['blocks']))}


def output_reference(record):
    details = {**output_identity(record), 'output_transport': OUTPUT_TRANSPORT,
        'retrieve': f"repl_output({record['iteration']})",
        'stderr_present': any(bool(block['stderr']) for block in record['blocks']),
        'blocks': [{'block': block['block'], 'stdout_chars': len(block['stdout']),
                    'stdout_sha256': _sha(block['stdout']), 'stderr_chars': len(block['stderr']),
                    'stderr_sha256': _sha(block['stderr']),
                    'derived_stream_failure': bool(block['stderr']), 'answer_ready': block['answer_ready']}
                   for block in record['blocks']]}
    return ('REPL OUTPUT REFERENCE\n' + _json(details) +
            '\nThe complete original feedback and all blocks are retained. '
            'Use the retrieval call above for fresh full code, stdout, stderr, execution and final-status records. '
            'A nonempty stderr is flagged; an empty stderr is not proof of execution success.')


class FeedbackHistory:
    def __init__(self, messages, max_prompt_chars):
        self.messages = copy.deepcopy(messages)
        self.max_prompt_chars = max_prompt_chars
        self._records = {}
        self._message_indexes = {}
        self._externalized = set()

    def append_response(self, response):
        self.messages.append({'role': 'assistant', 'content': response})

    def append_output(self, iteration, blocks):
        if type(iteration) is not int or iteration < 1 or iteration in self._records:
            raise ValueError('Invalid or duplicate completed refinement iteration')
        record = feedback_record(iteration, blocks)
        self._records[iteration] = record
        if blocks:
            self._message_indexes[iteration] = len(self.messages)
        self.messages.append({'role': 'user', 'content': record['feedback']})

    def read_output(self, iteration):
        if type(iteration) is not int or iteration not in self._records:
            raise ValueError('Refinement output is not a sealed completed iteration')
        return copy.deepcopy(self._records[iteration])

    def prepare(self):
        """Return exact prompt and new receipt events, or leave history unchanged.

        Costs include every message wrapper and the backend instruction prefix.
        Positive savings are ranked by decreasing net characters, then iteration.
        """
        proposed = copy.deepcopy(self.messages)
        prompt = transcript(proposed)
        complete_chars = len(INSTRUCTION + prompt)
        if complete_chars <= self.max_prompt_chars:
            return prompt, []
        candidates = []
        for iteration, index in self._message_indexes.items():
            if iteration in self._externalized:
                continue
            receipt = output_reference(self._records[iteration])
            candidate = copy.deepcopy(proposed)
            candidate[index]['content'] = receipt
            saving = complete_chars - len(INSTRUCTION + transcript(candidate))
            if saving > 0:
                candidates.append((saving, iteration, index, receipt))
        events, selected = [], []
        for _, iteration, index, receipt in sorted(candidates, key=lambda item: (-item[0], item[1])):
            before = complete_chars
            proposed[index]['content'] = receipt
            prompt = transcript(proposed)
            complete_chars = len(INSTRUCTION + prompt)
            events.append({'event': 'output.externalized', **output_identity(self._records[iteration]),
                           'receipt': receipt, 'receipt_chars': len(receipt), 'receipt_sha256': _sha(receipt),
                           'backend_prompt_chars_before': before, 'backend_prompt_chars_after': complete_chars,
                           'net_saving': before - complete_chars})
            selected.append(iteration)
            if complete_chars <= self.max_prompt_chars:
                self.messages = proposed
                self._externalized.update(selected)
                return prompt, events
        raise FeedbackTooLarge(
            f'Refinement control messages and whole-output references require {complete_chars} characters '
            f'including backend instructions; limit is {self.max_prompt_chars}. '
            'No control messages or output contents were dropped.')
