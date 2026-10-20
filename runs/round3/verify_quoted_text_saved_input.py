"""Explicit disk-only regression; no CI dependency on local research archives."""
import argparse
import hashlib
import json
from pathlib import Path

from loop_research import codex_backend, refine, shared_text
from loop_research.codex_backend import INSTRUCTION
from loop_research.refine import INSTRUCTIONS
from loop_research.shared_text import decode_shared_text, encode_shared_text


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', type=Path, required=True)
    parser.add_argument('--expected-logical-sha256', required=True)
    parser.add_argument('--max-prompt-chars', type=int, required=True)
    args = parser.parse_args()
    original = args.job.read_bytes()
    job = json.loads(original)
    old = job['planner_representation']
    old_text = job['planner_prompt'][-old['wire_payload_chars']:]
    assert digest(old_text) == old['wire_payload_sha256']
    payload = decode_shared_text(json.loads(old_text))
    logical = json.dumps(payload, ensure_ascii=False)
    assert len(logical) == old['logical_payload_chars']
    assert digest(logical) == old['logical_payload_sha256'] == args.expected_logical_sha256
    encoded = encode_shared_text(payload)
    text = json.dumps(encoded, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    assert json.dumps(decode_shared_text(json.loads(text)), ensure_ascii=False) == logical
    full = INSTRUCTION + INSTRUCTIONS + text
    schema = json.dumps(job['planner_schema'], ensure_ascii=False)
    assert job['planner_schema']['$defs']['EvidenceRef']['enum'] == payload['evidence_index']
    assert args.job.read_bytes() == original
    result = {'job': str(args.job.resolve()), 'job_sha256': hashlib.sha256(original).hexdigest(),
              'logical_chars': len(logical), 'logical_sha256': digest(logical),
              'format': encoded['format'], 'old_wire_chars': len(old_text),
              'old_backend_prompt_chars': len(INSTRUCTION + job['planner_prompt']),
              'wire_chars': len(text), 'wire_sha256': digest(text),
              'instruction_chars': len(INSTRUCTION) + len(INSTRUCTIONS),
              'refiner_instruction_chars': len(INSTRUCTIONS),
              'backend_prefix_chars': len(INSTRUCTION),
              'backend_prompt_chars': len(full), 'backend_prompt_sha256': digest(full),
              'schema_chars': len(schema), 'schema_sha256': digest(schema),
              'logical_collection_counts': {key: len(value) for key, value in payload.items()
                                             if type(value) in (dict, list)},
              'schema_evidence_index_equal': True,
              'source_files': {Path(module.__file__).name: {
                  'path': str(Path(module.__file__).resolve()),
                  'sha256': hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()}
                  for module in (codex_backend, refine, shared_text)},
              'observed_limit_chars': args.max_prompt_chars,
              'exact_logical_roundtrip': True, 'original_job_unchanged': True}
    print(json.dumps(result, indent=2))
    assert len(full) <= args.max_prompt_chars, 'Saved input still exceeds the observed provider limit'


if __name__ == '__main__':
    main()
