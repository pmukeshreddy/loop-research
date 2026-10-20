"""Compensate current-branch learned edits, retaining history, then fork exact BASE."""
import argparse
import json
from pathlib import Path
import subprocess

from loop_research.archive import stamp, write_json
from loop_research.harness import Harness
from loop_research.trace import Trace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--base', required=True)
    parser.add_argument('--directory', type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    out = args.directory.resolve()
    out.mkdir(parents=True, exist_ok=True)
    receipt = out / 'rollback.json'
    if receipt.exists():
        raise ValueError('Rollback already attempted; preserve its receipt')
    if subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip() != args.source:
        raise ValueError('Source differs from verified preflight')
    h = Harness(root / 'harness')
    if h.head != args.expected_head or h.git('status', '--porcelain'):
        raise ValueError('Unexpected harness HEAD or uncommitted state')
    record = {'source_commit': args.source, 'base_sha': args.base, 'started_at': stamp(),
              'before': h.head, 'branch_before': h.branch, 'rollbacks': [], 'status': 'running'}
    write_json(receipt, record)
    trace = Trace(out / 'rollback_trace')
    try:
        log = h.git('log', '--format=%H %s', args.base + '..HEAD')
        (out / 'rollback_before.log').write_text(log + '\n')
        edits = [line.split(' ', 1)[0] for line in log.splitlines()
                 if line.split(' ', 1)[1].startswith('refine_')]
        for commit in edits:
            before = h.head
            with trace.span('Harness', 'rollback', id=commit, head_before=before) as details:
                h.rollback(commit)
                details['head_after'] = h.head
            record['rollbacks'].append({'edit_sha': commit, 'head_before': before, 'rollback_sha': h.head})
            write_json(receipt, record)
        base = json.loads(h.git('show', args.base + ':harness_state.json'))
        def procedures(state):
            return {key: {k: entry[k] for k in ('id', 'kind', 'title', 'body', 'module')}
                    for key, entry in state['entries'].items()}
        if procedures(h.snapshot()) != procedures(base):
            raise ValueError('Compensation did not restore BASE procedures')
        record['compensated_head'] = h.head
        with trace.span('Harness', 'fork', base=args.base) as details:
            h.fork(args.base)
            details['head_after'] = h.head
        if h.head != args.base or h.snapshot() != base or h.git('status', '--porcelain'):
            raise ValueError('Fork differs from exact clean BASE')
        record.update(status='complete', completed_at=stamp(), harness_head=h.head, branch_after=h.branch)
    except BaseException as error:
        record.update(status='failed', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        write_json(receipt, record)
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
