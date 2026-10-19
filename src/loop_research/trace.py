"""Optional host-owned observation. Never included in research/refinement inputs."""
from collections import Counter, defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
import fcntl
import inspect
import json
import threading
import time
from uuid import uuid4


class Trace:
    def __init__(self, directory=None):
        self.directory = directory
        self.lock = threading.RLock()
        self.current = ContextVar('trace_component', default='Research')
        if directory is not None:
            directory.mkdir(parents=True, exist_ok=True)
            for name in ('trace.jsonl', 'trace.log'):
                (directory / name).touch()

    def __reduce__(self):
        return type(self), (self.directory,)

    @property
    def enabled(self):
        return self.directory is not None

    def emit(self, component, event, *, duration_s=None, parent=None, **details):
        if not self.enabled:
            return
        record = {'timestamp': datetime.now(timezone.utc).isoformat(), 'component': component,
                  'event': event, 'details': details}
        if duration_s is not None:
            record['duration_s'] = duration_s
        if parent is not None:
            record['parent'] = parent
        with self.lock:
            line = json.dumps(record, ensure_ascii=False, allow_nan=False)
            readable = f"{record['timestamp']} [{component}] {event}"
            if duration_s is not None:
                readable += f' ({duration_s:.3f}s)'
            readable += ' ' + json.dumps(details, ensure_ascii=False, allow_nan=False)
            # Open/flush each event: readers see it immediately, even on failure.
            with (self.directory / 'trace.jsonl').open('a') as stream:
                fcntl.flock(stream, fcntl.LOCK_EX)
                stream.write(line + '\n')
                stream.flush()
                with (self.directory / 'trace.log').open('a') as log:
                    log.write(readable + '\n')
                    log.flush()

    @contextmanager
    def span(self, component, event, *, parent=None, **details):
        if not self.enabled:
            yield details
            return
        span_id = uuid4().hex
        caller = parent or self.current.get()
        self.emit(component, event + '.start', parent=caller, span_id=span_id, **details)
        token = self.current.set(component)
        started = time.monotonic()
        try:
            yield details
        except BaseException as exc:
            details['error'] = f'{type(exc).__name__}: {exc}'
            raise
        finally:
            self.emit(component, event + '.end', duration_s=time.monotonic() - started,
                      span_id=span_id, **details)
            self.current.reset(token)

    def summary(self, output, self_check, *, error=None):
        from .archive import read_jsonl
        from .report import render_table
        events = read_jsonl(self.directory / 'trace.jsonl')
        counts, durations, edges = Counter(), Counter(), Counter()
        components = sorted({e['component'] for e in events})
        for event in events:
            if event['event'].endswith('.start'):
                counts[event['component']] += 1
                if event.get('parent'):
                    edges[(event['parent'], event['component'])] += 1
            durations[event['component']] += event.get('duration_s', 0)
        lines = ['# Research trace summary', '', f'Run: `{self.directory.name}`', '',
                 'Times are inclusive summed call durations; concurrent/nested calls overlap.', '',
                 '| Component | Calls | Time (s) |', '| --- | ---: | ---: |']
        lines += [f'| {name} | {counts[name]} | {durations[name]:.3f} |' for name in components]
        lines += ['', '## Connection map', '', '| Connection | Calls |', '| --- | ---: |']
        lines += [f'| {source} → {target} | {count} |' for (source, target), count in sorted(edges.items())]
        lines += ['', '## Final cited table', '', render_table(output), '', '## Self-check issues', '']
        grouped = defaultdict(list)
        for issue in self_check.get('issues', []):
            grouped[issue['type']].append(issue)
        if not grouped:
            lines.append('None recorded.' if self_check.get('ok') else 'Self-check did not complete.')
        for kind, issues in sorted(grouped.items()):
            lines.append(f'- **{kind}** ({len(issues)}): ' + json.dumps(issues, ensure_ascii=False))
        lines += ['', '## Harness edits from refinement', '']
        edits = [e['details'] for e in events if e['component'] == 'Refine' and
                 (e['event'] == 'edit_applied' or (e['event'] == 'rollback.end' and
                  not e['details'].get('error') and e['details'].get('result') is not False))]
        for edit in edits:
            lines += ['```json', json.dumps(edit, ensure_ascii=False, indent=2), '```', '']
        if not edits:
            lines.append('No edits applied.')
        proposals = [e['details']['summary'] for e in events if e['component'] == 'Refine' and e['event'] == 'proposal']
        for proposal in proposals:
            lines += ['', 'Proposal: ' + proposal]
        errors = [e for e in events if e['details'].get('error')]
        if error or errors:
            lines += ['', '## Component errors', '']
            if error:
                lines.append(str(error))
            lines += [f"- {e['component']} / {e['event']}: {e['details']['error']}" for e in errors]
        text = '\n'.join(lines) + '\n'
        (self.directory / 'trace_summary.md').write_text(text)
        return text


def observed(component, event='call'):
    """Observe a host service method, without altering its arguments or result."""
    def decorate(function):
        signature = inspect.signature(function)
        @wraps(function)
        def invoke(self, *args, **kwargs):
            trace = self.ctx.trace
            if not trace.enabled:
                return function(self, *args, **kwargs)
            details = dict(signature.bind(self, *args, **kwargs).arguments)
            details.pop('self')
            with trace.span(component, event, **details) as observed_details:
                result = function(self, *args, **kwargs)
                if component.startswith('tools.'):
                    observed_details['success'] = result != 'FETCH_FAILED' and (
                        not isinstance(result, list) or 'FETCH_FAILED' not in result)
                    if isinstance(result, list):
                        observed_details['hit_count'] = (sum(len(batch) for batch in result)
                            if component == 'tools.search_many' else len(result))
                return result
        return invoke
    return decorate
