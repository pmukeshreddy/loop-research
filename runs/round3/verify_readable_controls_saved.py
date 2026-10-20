"""Offline replay of retained HTTP receipts through the current full extractor.

The HTTP callback consumes only archived hop bytes. No model, browser, live
request or installation is used. Originals are read-only; replay artifacts are
written to a new output directory. Run with PYTHONPATH=src from the worktree.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from loop_research.archive import RunContext, write_json
from loop_research.config import Config
from loop_research.page_fetch import FetchError, PageFetcher, TEXT_POLICY, verify_receipt
import loop_research.page_fetch as page_fetch


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_record(path):
    raw = path.read_bytes()
    return {'path': str(path.resolve()), 'bytes': len(raw), 'sha256': sha(raw)}


def forbidden(text):
    # Independent explicit control ranges, including C1, excluding six layouts.
    return Counter(f'U+{ord(char):04X}' for char in text
                   if (ord(char) < 32 or 127 <= ord(char) < 160)
                   and ord(char) not in (9, 10, 11, 12, 13, 133))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cohort', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--corrupt-arms', nargs='+', required=True)
    parser.add_argument('--valid-arm', required=True)
    parser.add_argument('--expect-rejected', type=int, required=True)
    parser.add_argument('--expect-unchanged', type=int, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    processes = json.loads((args.cohort / 'b.processes.json').read_text())['arms']
    config = Config.load(args.cohort / 'inputs/config.json')
    result = {'created_at': datetime.now(timezone.utc).isoformat(), 'text_policy': TEXT_POLICY,
              'method': 'Archived hops only; installed Poppler and current full static extractor; no live calls.',
              'source_module': file_record(Path(page_fetch.__file__)),
              'script': file_record(Path(__file__)), 'cases': []}
    sources = {}
    for label in [*args.corrupt_arms, args.valid_arm]:
        arm = processes[label]
        assert arm['status'] == 'complete' and arm['exit_code'] == 0
        task = Path(arm['run_path']) / arm['task_id']
        telemetry = json.loads((task / 'fetch_telemetry.json').read_text())
        receipts = {item['receipt']['id']: item for item in telemetry
                    if item['source'] == 'backend' and item['status'] == 'succeeded'}
        for identity, item in receipts.items():
            old = item['receipt']
            original = (task / old['text_path']).read_bytes()
            controls = forbidden(original.decode('utf-8'))
            if label != args.valid_arm and not controls:
                continue
            if label == args.valid_arm:
                assert not controls, 'Expected valid corpus contains previously observed forbidden controls'
            verify_receipt(task, old)
            paths = [task / 'downloads' / (identity + '.json'), task / old['text_path'],
                     *[task / hop['raw_path'] for hop in old['hops']]]
            for path in paths:
                sources[str(path)] = file_record(path)
            replay = RunContext(args.output / 'archives', label + '-' + identity, config, 'offline-replay')
            hops = iter(old['hops'])
            calls = []

            def request(url, timeout):
                hop = next(hops)
                assert url == hop['url']
                calls.append(url)
                return {'status': hop['status'], 'headers': hop['headers'],
                        'body': (task / hop['raw_path']).read_bytes(), 'peer_ip': hop.get('peer_ip')}

            try:
                page = PageFetcher(replay, request=request).fetch(old['requested_url'])
            except FetchError as error:
                assert controls and error.reason == 'forbidden_control_characters'
                receipt = error.receipt
                assert receipt['extraction_validation']['forbidden_controls'] == dict(controls)
                assert receipt['extraction_validation']['forbidden_control_count'] == sum(controls.values())
                assert (replay.path / receipt['extraction_path']).read_bytes() == original
                assert 'text_path' not in receipt and 'readable_chars' not in receipt
            else:
                assert not controls
                receipt = page.receipt
                assert page.text.encode('utf-8') == original
                assert (replay.path / receipt['extraction_path']).read_bytes() == original
            assert list(hops) == [] and len(calls) == len(old['hops'])
            verify_receipt(replay.path, receipt, expected_policy=TEXT_POLICY)
            result['cases'].append({
                'arm': label, 'request_id': item['id'], 'url': old['requested_url'],
                'historical_source_commit': arm['source_commit'], 'old_receipt': file_record(paths[0]),
                'old_text': file_record(task / old['text_path']), 'old_chars': len(original.decode()),
                'old_parser': old['parser'], 'new_parser': receipt['parser'],
                'expected_forbidden_controls': dict(sorted(controls.items())),
                'expected_forbidden_control_count': sum(controls.values()),
                'new_status': receipt['status'], 'new_reason': receipt.get('reason'),
                'new_receipt': file_record(replay.path / 'downloads' / (receipt['id'] + '.json')),
                'new_extraction': file_record(replay.path / receipt['extraction_path']),
                'exact_extraction_bytes_preserved': True, 'request_hops': calls})
    assert all(file_record(Path(path)) == before for path, before in sources.items())
    result.update(source_files=list(sources.values()), original_source_files_unchanged=True,
                  rejected=sum(case['new_status'] == 'failed' for case in result['cases']),
                  valid_unchanged=sum(case['new_status'] == 'succeeded' for case in result['cases']))
    assert result['rejected'] == args.expect_rejected
    assert result['valid_unchanged'] == args.expect_unchanged
    write_json(args.output / 'result.json', result)
    print(json.dumps({key: result[key] for key in
                      ('text_policy', 'rejected', 'valid_unchanged', 'original_source_files_unchanged')}))


if __name__ == '__main__':
    main()
