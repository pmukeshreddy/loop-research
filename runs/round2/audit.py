"""Compatibility CLI for the tracked, read-only archive auditor.

Usage: python runs/round2/audit.py LABEL RUN_ID [--output-dir DIRECTORY]
       python runs/round2/audit.py --all ARCHIVE_ROOT --output-dir DIRECTORY
"""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from loop_research.archive_audit import audit, main


if __name__ == '__main__':
    if '--all' in sys.argv or '--run-dir' in sys.argv:
        if '--run-dir' in sys.argv:
            sys.argv.remove('--run-dir')
        sys.exit(main())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('label')
    parser.add_argument('run_id')
    parser.add_argument('--output-dir', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--excerpt-trace-lines', nargs='+', type=int)
    args = parser.parse_args()
    run = Path(args.run_id)
    if not run.is_dir():
        run = ROOT / 'runs' / args.run_id
    result = audit(args.label, run, args.output_dir, args.excerpt_trace_lines)
    print(f'Audited {run}: {args.output_dir}')
