"""Check the completed report against its local evidence before append."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys
import unicodedata

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from loop_research.report import render_table

def read(path):
    return json.loads(path.read_text())

def sha(data):
    return hashlib.sha256(data).hexdigest()

def verify_source_provenance(manifest):
    """Verify historical execution receipts and current report bytes separately."""
    prefix = Path('src/loop_research')
    def git_modules(commit):
        tree = subprocess.check_output(['git', 'ls-tree', '-r', '-z', commit, '--', str(prefix)], cwd=ROOT)
        modules = {}
        for record in tree.split(b'\0'):
            if not record:
                continue
            metadata, path_bytes = record.split(b'\t', 1)
            path = path_bytes.decode()
            if not path.endswith('.py'):
                continue
            mode, kind, object_id = metadata.split()
            assert mode in (b'100644', b'100755') and kind == b'blob', path
            modules[path] = subprocess.check_output(['git', 'cat-file', 'blob', object_id.decode()], cwd=ROOT)
        assert modules, f'No Python modules at {commit}'
        return modules

    coordinator = read(Path(manifest['replay_coordinator']))
    runtime = coordinator['preflight']['source']
    assert runtime['commit'] == manifest['source_commit']
    historical = git_modules(runtime['commit'])
    captured = runtime['modules']
    assert len(captured) == len({module['source'] for module in captured})
    assert {module['source'] for module in captured} == set(historical)
    package_root = Path(runtime['package_root'])
    assert package_root.is_absolute()
    for module in captured:
        content = historical[module['source']]
        assert module['sha256'] == sha(content) and module['bytes'] == len(content), module['source']
        expected = package_root / Path(module['source']).relative_to(prefix)
        assert Path(module['installed']).resolve() == expected.resolve(), module['source']

    # These immutable receipts attest checks performed at completion. They are
    # not new measurements of an installation that no longer exists.
    assert coordinator['status'] == 'complete'
    assert set(coordinator['arms']) == set(manifest['runs']) - {'explicit'}
    receipts = dict(coordinator['arms'])
    if 'explicit' in manifest['runs']:
        receipts['explicit'] = read(HERE / 'explicit_execution.json')
    verified_receipts = []
    for label, receipt in sorted(receipts.items()):
        assert receipt['run_id'] == manifest['runs'][label]
        assert receipt['source_commit'] == runtime['commit']
        assert receipt['source_unchanged'] is True
        assert receipt['status'] == 'complete' and receipt['exit_code'] == 0
        archive = Path(receipt['run_path'])
        assert archive.name == receipt['run_id']
        owner = read(archive / 'research.json')
        assert owner['run_id'] == receipt['run_id'] and owner['status'] == 'complete' and not owner['error']
        audit = read(HERE / f'{label}.audit.json')
        assert owner['task_id'] == Path(audit['task_path']).name
        assert owner == read(Path(audit['task_path']).parent / 'research.json')
        verified_receipts.append({'label': label, 'run_id': receipt['run_id'],
                                  'run_path': str(archive), 'source_commit': runtime['commit'],
                                  'source_unchanged': True})

    current = git_modules(manifest['report_source_commit'])
    assert {str(path.relative_to(ROOT)) for path in (ROOT / prefix).rglob('*.py')} == set(current)
    installed_paths = {str(prefix / path.relative_to(package_root)) for path in package_root.rglob('*.py')}
    assert installed_paths == set(current)
    for path, content in current.items():
        assert (ROOT / path).read_bytes() == content, path
        assert (package_root / Path(path).relative_to(prefix)).read_bytes() == content, path

    changed = []
    for path in sorted(set(historical) | set(current)):
        before, after = historical.get(path), current.get(path)
        if before != after:
            changed.append({'source': path,
                            'change': 'added' if before is None else 'deleted' if after is None else 'modified',
                            'runtime_sha256': sha(before) if before is not None else None,
                            'report_sha256': sha(after) if after is not None else None})
    return {'runtime_commit': runtime['commit'], 'report_commit': manifest['report_source_commit'],
            'runtime_module_count': len(historical), 'report_module_count': len(current),
            'runtime_modules_verified': True, 'report_modules_verified': True,
            'completion_receipts': verified_receipts,
            'completion_receipt_meaning': 'Captured completion checks attest the original source and installed '
                                          'bytes; historical installed bytes are not remeasured.',
            'changed_modules': changed}

def normalized(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value)).casefold() if c.isalnum())

def verify_task_file(path, task_path, run_id, filename):
    """Bind a file to its durable owner, allowing an exact copied archive."""
    path, task_path = Path(path), Path(task_path)
    assert path.name == filename
    owner = read(path.parent.parent / 'research.json')
    assert owner['run_id'] == run_id and owner['task_id'] == path.parent.name == task_path.name
    assert path.read_bytes() == (task_path / filename).read_bytes()
    return sha(path.read_bytes())

def verify_cohort_inputs(manifest, control, quality, generalization):
    """Reject successful comparison artifacts belonging to another cohort."""
    audits = {label: read(HERE / f'{label}.audit.json') for label in manifest['runs']}
    metrics = {label: read(HERE / f'{label}.metrics.json') for label in manifest['runs']}
    for label, run_id in manifest['runs'].items():
        assert audits[label]['run_id'] == metrics[label]['run_id'] == run_id
        task = Path(audits[label]['task_path'])
        owner = read(task.parent / 'research.json')
        assert owner['run_id'] == run_id and owner['task_id'] == task.name
        assert metrics[label]['manifest'] == owner

    controls = ('B0', 'B1-frozen')
    assert control['run_ids'] == {label: manifest['runs'][label] for label in controls}
    assert control['BASE'] == manifest['BASE'] and control['POST_A'] == manifest['POST_A']
    for label, base in zip(controls, ('BASE', 'POST_A')):
        assert metrics[label]['manifest']['base_sha'] == manifest[base]
        assert metrics[label]['manifest']['learning'] is False
        task = Path(audits[label]['task_path'])
        digest = verify_task_file(control['input_paths'][label], task, manifest['runs'][label], 'prompt.txt')
        assert digest == control['root_input_sha256'][label] == sha((task / 'root_prompt.txt').read_bytes())
        before, payload = (task / 'prompt.txt').read_text().split('RELEVANT HARNESS\n', 1)
        entries, after = payload.split('\n\nTOOLS\n', 1)
        assert json.loads(entries) == control['initial_retrieved_entries'][label]
        without_harness = before + 'RELEVANT HARNESS\n\n\nTOOLS\n' + after
        assert sha(without_harness.encode()) == control['full_context_without_harness_sha256']

    prior_runs = read(ROOT / 'runs/proof_manifest.json')['runs']
    prior_runs['B1-frozen'] = read(ROOT / 'runs/followup/manifest.json')['frozen_run']
    for label, comparison in quality.items():
        assert comparison['run_id'] == manifest['runs'][label]
        assert comparison['prior_run_id'] == prior_runs[label]
        task = Path(audits[label]['task_path'])
        prior_run = ROOT / 'runs' / prior_runs[label]
        prior_task = prior_run / read(prior_run / 'research.json')['task_id']
        verify_task_file(comparison['current_output'], task, manifest['runs'][label], 'output.json')
        verify_task_file(comparison['prior_output'], prior_task, prior_runs[label], 'output.json')
        fields = read(task / 'task.json')['spec']['keys']
        def keys(path):
            return [tuple(normalized(row['cells'][field]['value']) for field in fields)
                    for row in read(path)['rows']]
        current, prior = keys(task / 'output.json'), keys(prior_task / 'output.json')
        assert comparison['rows'] == len(current) and comparison['prior_rows'] == len(prior)
        assert comparison['same_key_set'] is (set(current) == set(prior) and len(current) == len(prior))
        assert comparison['only_current_keys'] == [list(key) for key in sorted(set(current) - set(prior))]
        assert comparison['only_prior_keys'] == [list(key) for key in sorted(set(prior) - set(current))]
        assert comparison['issues'] == read(task / 'self_check.json')['issues']
        assert comparison['uncited'] == read(task / 'agent_result.json')['uncited']

    provenance = generalization['provenance']
    task = Path(audits['SI']['task_path'])
    assert provenance['run_id'] == manifest['runs']['SI']
    assert provenance['task_id'] == task.name
    assert provenance['base_sha'] == metrics['SI']['manifest']['base_sha']
    for filename, field in (('task.json', 'task_sha256'), ('output.json', 'output_sha256')):
        assert verify_task_file(Path(provenance['task_path']) / filename, task,
                                manifest['runs']['SI'], filename) == provenance[field]
    baseline_path = HERE / 'SI.baseline.json'
    assert Path(provenance['baseline_path']).resolve() == baseline_path.resolve()
    assert provenance['baseline_sha256'] == sha(baseline_path.read_bytes())
    baseline = read(baseline_path)
    assert provenance['prior_run_id'] == baseline['identity']['run_id']
    assert provenance['base_sha'] == baseline['harness']['initial_sha']
    assert read(task / 'task.json') == baseline['task']
    for filename, field in (('task.json', 'task'), ('output.json', 'output')):
        original = baseline['artifacts'][filename]
        assert sha(Path(original['path']).read_bytes()) == original['sha256']
        assert read(Path(original['path'])) == baseline[field]
    assert generalization['rows'] == len(read(task / 'output.json')['rows']) == metrics['SI']['rows']
    assert generalization['issues'] == len(metrics['SI']['issues'])
    assert generalization['uncited'] == metrics['SI']['uncited_cells']

def verify_identity_review(label, comparison):
    """Check evidence for reviewed identities without changing the key comparator."""
    review = read(HERE / f'{label}.identity_review.json')
    assert review['current_run'] == comparison['run_id']
    assert review['prior_run'] == comparison['prior_run_id']
    assert review['same_key_set'] is False and comparison['same_key_set'] is False
    assert review['reviewed_identity_equivalence'] is True
    current = {tuple(x) for x in comparison['only_current_keys']}
    prior = {tuple(x) for x in comparison['only_prior_keys']}
    assert current == {tuple(x) for x in review['only_current_keys']}
    assert prior == {tuple(x) for x in review['only_prior_keys']}
    pairs = review['pairs']
    assert len(pairs) == len(current) == len(prior)
    assert {tuple(p['current_normalized_key']) for p in pairs} == current
    assert {tuple(p['prior_normalized_key']) for p in pairs} == prior
    for pair in pairs:
        assert pair['same_entity'] is True and pair['reason'].strip()
        for side in ('current', 'prior'):
            raw = pair[f'{side}_key']
            assert tuple(map(normalized, raw)) == tuple(pair[f'{side}_normalized_key'])
            output_path = Path(comparison[f'{side}_output'])
            task = read(output_path.parent / 'task.json')
            output = read(output_path)
            matching = [row for row in output['rows'] if
                        [str(row['cells'][f]['value']) for f in task['spec']['keys']] == raw]
            assert len(matching) == 1
            assert pair[f'{side}_evidence']
            for item in pair[f'{side}_evidence']:
                # Isolated originals and byte-identical copied archives are both valid.
                assert Path(item['output_path']).read_bytes() == output_path.read_bytes()
                cell = matching[0]['cells'][item['field']]
                assert item['quote'] == cell['quote'] and item['url'] in cell['sources']
        for item in pair['current_evidence'] + pair['prior_evidence'] + [pair['bridge_evidence']]:
            texts = read(Path(item['evidence_path']))['fetched'][item['url']]
            assert item['quote'] and item['fetched_text_indexes']
            assert all(item['quote'] in texts[i] for i in item['fetched_text_indexes'])
    return {'label': label, 'same_key_set': False, 'reviewed_pairs': len(pairs),
            'evidence_references_verified': True, 'scope': review['scope']}

def verify_capacity_retry(item, trace, task):
    """Verify authorized backend completion, without asserting fetch success."""
    policy = read(Path(item['policy']))
    assert 'Count any capacity errors and retries as usual.' in policy['user_instruction']
    assert item['reason'] and len(item['recovery_trace_lines']) == 1
    failed_line, retry_line, start_line = (item[key] for key in
                                         ('failed_trace_line', 'retry_trace_line', 'recovery_start_line'))
    end_line = item['recovery_trace_lines'][0]
    assert all(type(line) is int and 1 <= line <= len(trace)
               for line in (failed_line, retry_line, start_line, end_line))
    assert failed_line < retry_line < start_line < end_line
    assert item['event']['line'] in (failed_line, retry_line)
    failed, retry, start, completed = [trace[line - 1] for line in (failed_line, retry_line, start_line, end_line)]
    fd, rd, sd, cd = [event['details'] for event in (failed, retry, start, completed)]
    component = f'Codex backend ({fd["purpose"]})'
    assert all(event['component'] == component for event in (failed, retry, start, completed))
    assert [event['event'] for event in (failed, retry, start, completed)] == ['exec.end', 'retry', 'exec.start', 'exec.end']
    assert re.search(r'(^|\n)Selected model is at capacity\. Please try a different model\.(\n|$)', fd['error'])
    assert rd['error'] == f'Codex failed (exit={fd["exit_code"]}): {fd["error"]}'
    assert type(fd['attempt']) is int and type(cd['attempt']) is int
    assert rd['attempt'] == fd['attempt'] and rd['next_attempt'] == fd['attempt'] + 1 <= cd['attempt']
    # Retry records have no call ID. Require one unambiguous matching failure
    # since the preceding matching retry rather than inventing that linkage.
    boundary = max((index + 1 for index, event in enumerate(trace[:retry_line - 1])
                    if event['component'] == component and event['event'] == 'retry'
                    and event['details'].get('attempt') == rd['attempt']
                    and event['details'].get('error') == rd['error']), default=0)
    failures = [index + 1 for index, event in enumerate(trace[:retry_line - 1])
                if index + 1 > boundary and event['component'] == component and event['event'] == 'exec.end'
                and event['details'].get('attempt') == fd['attempt']
                and event['details'].get('error') == fd['error']]
    assert failures == [failed_line]
    signature = ('purpose', 'model', 'prompt_sha256', 'prompt_chars') + tuple(
        key for key in ('schema_sha256', 'schema_chars') if key in fd or key in cd)
    assert all(fd[key] == cd[key] for key in signature)
    assert all(sd[key] == cd[key] for key in (*signature, 'call_id', 'attempt'))
    next_starts = [event for event in trace[retry_line:end_line]
                   if event['component'] == component and event['event'] == 'exec.start'
                   and event['details'].get('attempt') == rd['next_attempt']
                   and all(event['details'].get(key) == fd[key] for key in signature)]
    assert len(next_starts) == 1
    assert fd['call_id'] != cd['call_id'] and cd['exit_code'] == 0 and cd['error'] is None
    assert cd['response_chars'] > 0 and cd['retries'] == cd['attempt']
    calls = [json.loads(line) for line in (task / 'codex_calls.jsonl').read_text().splitlines() if line.strip()]
    fields = (*signature, 'call_id', 'attempt', 'exit_code', 'response_chars', 'error')
    for details in (fd, cd):
        matches = [call for call in calls if call['call_id'] == details['call_id']]
        assert len(matches) == 1 and all(matches[0][key] == details[key] for key in fields)

report = HERE / 'Round2.md'
document = report.read_text()
metadata = read(HERE / 'Round2.render.json')
manifest = read(HERE / 'manifest.json')
identity = read(HERE / 'original_report_identity.json')
original = (ROOT / 'runs/proof_report.md').read_bytes()
assert original == (HERE / 'proof_report.before_round2.md').read_bytes()
assert sha(original) == identity['sha256']
assert sha(report.read_bytes()) == metadata['output_sha256']
assert document.startswith('# Round 2\n')
assert document.index('**RLM verdict:') < document.index('**Self-improvement verdict:') < document.index('## Original diagnosis')
assert 'mechanism evidence, not a statistical result' in document
interpretation = read(HERE / 'interpretation.json')
assert {c['id'] for c in interpretation['checks']} == set(range(1, 11))
assert all(c['verdict'] in {"works", "doesn't work", "not exercised", "not demonstrated"} for c in interpretation['checks'])
control = read(HERE / 'control_audit.json')
assert control['controls_equal'] and control['no_learning_verified']
quality = read(HERE / 'quality_comparison.json')
assert set(quality) == {'A', 'B1', 'B0', 'B1-frozen'}
assert all(q['rows'] == q['prior_rows'] and q['issues'] == [] and q['uncited'] == [] for q in quality.values())
identity_reviews = [verify_identity_review(label, q) for label, q in quality.items() if not q['same_key_set']]
generalization = read(HERE / 'SI.generalization.json')
assert generalization['same_exact_task'] and generalization['quality_preserved']
verify_cohort_inputs(manifest, control, quality, generalization)
error_review = read(HERE / 'reviewed_error_events.json')
assert read(Path(error_review['policy']))['user_clarification'] == 'Record the validation error and recovery; preserve all counts'
observed_errors = []

checked = []
for label, run_id in manifest['runs'].items():
    audit = read(HERE / f'{label}.audit.json')
    metrics = read(HERE / f'{label}.metrics.json')
    assert audit['run_id'] == metrics['run_id'] == run_id
    assert metrics['manifest']['status'] == 'complete'
    reviewed = [r for r in error_review['entries'] if r['label'] == label]
    assert [r['event'] for r in reviewed] == metrics['errors'], (label, 'unreviewed or changed error events')
    trace = [json.loads(line) for line in (Path(audit['task_path']).parent / 'trace.jsonl').read_text().splitlines()]
    for item in reviewed:
        assert item['run_id'] == run_id
        error = item['event']
        assert trace[error['line'] - 1] == {k: v for k, v in error.items() if k != 'line'}
        if item['classification'] == 'external_capacity_retried':
            verify_capacity_retry(item, trace, Path(audit['task_path']))
        else:
            assert item['classification'] == 'validation_recovered'
            assert error['component'] == 'REPL' and error['event'] == 'code.end'
            assert error['details']['error'] and item['reason'] and item['recovery_trace_lines']
            for line in item['recovery_trace_lines']:
                event = trace[line - 1]
                assert line > error['line'] and event['component'] == 'REPL' and event['event'] == 'code.end'
                assert not event['details']['error']
        observed_errors.append(item)
    assert metrics['issues'] == [] and metrics['uncited_cells'] == 0, label
    assert sum(audit['largest_prompt']['parts'].values()) == audit['largest_prompt']['total']
    assert audit['overlap']['ngram_chars'] == 50
    assert audit['overlap']['total_chars'] == metrics['page_chars']
    assert audit['subcall_input_chars'] == sum(c['input_chars'] for c in audit['subcalls'])
    assert audit['subcall_input_chars'] == audit['subcall_prompt_chars'] + audit['subcall_schema_chars']
    largest = (HERE / f'{label}.largest_root_prompt.txt').read_bytes()
    assert sha(largest) == audit['largest_prompt']['sha256']
    for item in audit['source_files']:
        assert sha(Path(item['path']).read_bytes()) == item['sha256'], item['path']
    output = read(Path(audit['task_path']) / 'output.json')
    assert render_table(output) in document, label
    checked.append({'label': label, 'run_id': run_id, 'runtime_errors': len(metrics['errors']),
                    'rows': metrics['rows'], 'prompt_hash_verified': True,
                    'full_table_in_report': True})

links = set()
for match in re.finditer(r'\]\(<(/[^>]+)>\)|\]\((/[^)\n]+)\)', document):
    target = match.group(1) or match.group(2)
    location = re.fullmatch(r'(.+):(\d+)', target)
    path = Path(location.group(1) if location else target)
    assert path.exists(), target
    if location:
        assert path.is_file(), target
        assert 1 <= int(location.group(2)) <= len(path.read_text().splitlines()), target
    links.add(target)
assert observed_errors == error_review['entries']
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == manifest['report_source_commit']
assert subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip() == ''
for suite in (manifest['unit_suite'], manifest['reporting_unit_suite']):
    assert suite['exit_code'] == 0
    assert f"{suite['passed']} passed" in Path(suite['log']).read_text()
source_provenance = verify_source_provenance(manifest)
result = {'report_sha256': sha(report.read_bytes()), 'original_sha256': sha(original),
          'original_bytes': len(original), 'original_unchanged_before_append': True,
          'verified_local_links': len(links), 'controls_equal': True,
          'source_commit': manifest['source_commit'], 'report_source_commit': manifest['report_source_commit'],
          'research_modules_unchanged': not source_provenance['changed_modules'],
          'source_provenance': source_provenance, 'source_clean': True, 'runs': checked,
          'identity_reviews': identity_reviews, 'recorded_recovered_errors': len(observed_errors),
          'recorded_validation_errors': sum(item['classification'] == 'validation_recovered' for item in observed_errors),
          'recorded_capacity_error_events': sum(item['classification'] == 'external_capacity_retried' for item in observed_errors)}
(HERE / 'report_verification.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
