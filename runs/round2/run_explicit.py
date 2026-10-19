"""Run the separately requested mechanism check after the comparison finishes."""
import json
from pathlib import Path
import shlex
import subprocess
import time

from launch_replay import clone_workspace, unchanged_source
from replay_saved_refine import file_record, save, stamp

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    manifest = json.loads((HERE / 'manifest.json').read_text())
    plan = json.loads(Path(manifest['replay_plan']).read_text())
    cohort = json.loads(Path(manifest['replay_coordinator']).read_text())
    if cohort['status'] != 'complete' or any(a['status'] != 'complete' for a in cohort['arms'].values()):
        raise ValueError('The complete comparison must finish first')
    source = cohort['preflight']['source']
    if not unchanged_source(plan, source):
        raise ValueError('Research source changed before the explicit check')
    request = json.loads((HERE / 'explicit_request.json').read_text())
    workspace, isolation = clone_workspace(plan, {'label': request['label']}, request['base'], ROOT / 'harness')
    command = [plan['public_cli'], '--root', str(workspace), '--config', plan['config_file'],
               'research', request['question']]
    for column in request['columns']:
        command += ['--columns', column]
    for key in request['keys']:
        command += ['--keys', key]
    command += ['--language', request['language'], '--trace', '--base', request['base']]
    console = HERE / 'explicit.console.log'
    record = {'status': 'prepared', 'request': file_record(HERE / 'explicit_request.json'),
              'source_commit': source['commit'], 'command': command, 'workspace': str(workspace),
              'classification': request['classification'], 'isolation': isolation, 'console': str(console)}
    target = HERE / 'explicit_execution.json'
    save(target, record)
    print(json.dumps(record), flush=True)
    with console.open('x') as log:
        record['started_at'] = stamp()
        process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        record.update(status='running', pid=process.pid)
        save(target, record)
        while process.poll() is None:
            paths = list((workspace / 'runs').glob('research-*'))
            if len(paths) == 1 and 'run_id' not in record:
                record.update(run_id=paths[0].name, run_path=str(paths[0]),
                              trace_tail_command=shlex.join(['tail', '-f', str(paths[0] / 'trace.log')]))
                save(target, record)
                print(record['trace_tail_command'], flush=True)
            time.sleep(1)
    record.update(ended_at=stamp(), exit_code=process.returncode, source_unchanged=unchanged_source(plan, source))
    paths = list((workspace / 'runs').glob('research-*'))
    if len(paths) != 1:
        record.update(status='failed', error='Expected exactly one archive')
    else:
        archive = paths[0]
        run = json.loads((archive / 'research.json').read_text())
        record.update(run_id=archive.name, run_path=str(archive), record=run,
                      status='complete' if process.returncode == 0 and run['status'] == 'complete'
                      and not run.get('error') else 'failed')
        hashes = [{'relative_path': str(p.relative_to(archive)), **file_record(p)}
                  for p in sorted(archive.rglob('*')) if p.is_file()]
        save(HERE / 'explicit.archive_hashes.json', hashes)
    save(target, record)
    print(json.dumps(record), flush=True)
    if record['status'] != 'complete' or not record['source_unchanged']:
        raise ValueError('Explicit check did not complete unchanged; inspect its preserved archive')


if __name__ == '__main__':
    main()
