"""Versioned supplemental state. Only the trusted host opens this repository."""
from collections import Counter
from contextlib import contextmanager
import copy
import fcntl
import math
from pathlib import Path
import re
import subprocess
import threading
from uuid import uuid4

from .archive import read_json, stamp, write_json

KINDS = ('prompt', 'memory', 'skill', 'subagent')
_UNSET = object()


def terms(text):
    words = re.findall(r'[a-z0-9]+|[^\W\d_]+', text.casefold(), re.UNICODE)
    result = []
    for word in words:
        if any('\u3400' <= c <= '\u9fff' or '\u3040' <= c <= '\u30ff' for c in word):
            result.extend([word[i:i+2] for i in range(len(word)-1)] or [word])
        else:
            result.append(word)
    return result


class Harness:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.local = threading.local()
        if not (self.path / '.git').exists():
            self.git('init', '-q', '-b', 'main')
            self.git('config', 'user.name', 'Continual Harness')
            self.git('config', 'user.email', 'harness@localhost')
            write_json(self.path / 'harness_state.json', {'entries': {}, 'seen': {}, 'usage': [], 'outcomes': []})
            self.commit('Initialize continual harness')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.path), *args], text=True, stderr=subprocess.PIPE).strip()

    @property
    def head(self):
        return self.git('rev-parse', 'HEAD')

    @property
    def branch(self):
        return self.git('branch', '--show-current')

    @contextmanager
    def transaction(self):
        with self.lock:
            if getattr(self.local, 'transaction', False):
                yield
            else:
                with (self.path / '.git/harness.lock').open('a') as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX)
                    self.local.transaction = True
                    try:
                        yield
                    finally:
                        self.local.transaction = False

    def commit(self, message):
        self.git('add', 'harness_state.json', 'edits') if (self.path / 'edits').exists() else self.git('add', 'harness_state.json')
        self.git('-c', 'commit.gpgsign=false', 'commit', '-q', '-m', message)
        return self.head

    def snapshot(self):
        with self.lock:
            return read_json(self.path / 'harness_state.json')

    def _save(self, state, message):
        path = self.path / 'harness_state.json'
        previous = path.read_bytes()
        try:
            write_json(path, state)
            return self.commit(message)
        except BaseException:
            path.write_bytes(previous)
            self.git('reset', '-q', 'HEAD', '--', 'harness_state.json', 'edits')
            raise

    def _key(self, kind, id):
        if kind not in KINDS or not isinstance(id, str) or not re.fullmatch(r'[\w-]+', id):
            raise ValueError('Invalid harness kind or id')
        return kind + ':' + id

    def get(self, kind, id):
        return self.snapshot()['entries'].get(self._key(kind, id))

    def read(self, kind, id):
        return self.get(kind, id)

    def list(self, kind=None):
        if kind is not None and kind not in KINDS:
            raise ValueError('Invalid harness kind')
        return sorted((e for e in self.snapshot()['entries'].values() if kind is None or e['kind'] == kind),
                      key=lambda e: (e['kind'], e['title'], e['id']))

    def search(self, query, kind=None, limit=10):
        if not isinstance(query, str) or type(limit) is not int or limit < 1:
            raise ValueError('Search requires text and a positive limit')
        entries = self.list(kind)
        documents = [Counter(terms(e['title'] + ' ' + e['body'])) for e in entries]
        lengths = [sum(doc.values()) for doc in documents]
        average = sum(lengths) / len(lengths) if lengths else 1
        scores = [0.0] * len(entries)
        for term in set(terms(query)):
            df = sum(term in doc for doc in documents)
            idf = math.log(1 + (len(entries) - df + .5) / (df + .5))
            for i, doc in enumerate(documents):
                tf = doc[term]
                if tf:
                    scores[i] += idf * tf * 2.5 / (tf + 1.5 * (.25 + .75 * lengths[i] / average))
        ranked = sorted(zip(scores, entries), key=lambda pair: (-pair[0], pair[1]['id']))
        return [e for score, e in ranked if score > 0][:limit]

    def _edit(self, action, kind, id, title=None, content=None, *, trigger='agent', evidence=(), module=_UNSET,
              expected_version=None, rollback_of=None, restore=None):
        key = self._key(kind, id)
        if not isinstance(trigger, str) or not trigger or not all(isinstance(r, str) for r in evidence):
            raise ValueError('Trigger and evidence run ids required')
        with self.transaction():
            state = self.snapshot()
            before = state['entries'].get(key)
            if action == 'create' and before is not None:
                raise ValueError('Entry already exists')
            if action == 'update' and before is None:
                raise ValueError('Entry does not exist')
            if expected_version is not None and (before or {}).get('version') != expected_version:
                raise ValueError('Entry changed while refinement was planning')
            if action == 'delete' and before is None:
                return False
            after = None
            event_id = 'refine_' + uuid4().hex
            if action != 'delete':
                if not isinstance(title, str) or not title.strip() or not isinstance(content, str) or not content.strip():
                    raise ValueError('Nonempty title and body required')
                if module is not _UNSET and module is not None and (kind != 'skill' or not isinstance(module, str)):
                    raise ValueError('Only skills may carry a Python module')
                after = copy.deepcopy(before or restore) if before or restore else {
                    'id': id, 'kind': kind, 'created_at': stamp(), 'usage': [], 'outcomes': [], 'version': 0,
                    'module': None,
                }
                after.update(title=title, body=content, trigger=trigger, evidence=list(evidence),
                             updated_at=stamp(), version=after['version'] + 1, refinement_id=event_id)
                if module is not _UNSET:
                    after['module'] = module
                state['entries'][key] = after
            else:
                del state['entries'][key]
            record = {'id': event_id, 'trigger': trigger, 'evidence': list(evidence), 'action': action,
                      'key': key, 'before': before, 'after': after, 'created_at': stamp(), 'rollback_of': rollback_of}
            record_path = self.path / 'edits' / (event_id + '.json')
            write_json(record_path, record)
            try:
                self._save(state, f'{event_id}: {action} {key}\n\nTrigger: {trigger}\nEvidence: {", ".join(evidence)}')
            except BaseException:
                record_path.unlink(missing_ok=True)
                raise
            return copy.deepcopy(after) if after else True

    def create(self, kind, title, content, *, id=None, **kwargs):
        return self._edit('create', kind, id or uuid4().hex, title, content, **kwargs)

    def update(self, kind, id, title, content, **kwargs):
        return self._edit('update', kind, id, title, content, **kwargs)

    def delete(self, kind, id, **kwargs):
        return self._edit('delete', kind, id, **kwargs)

    def rollback(self, id):
        if not isinstance(id, str) or not id:
            raise ValueError('Expected a refinement id or commit SHA')
        with self.transaction():
            try:
                sha = self.git('rev-parse', '--verify', id + '^{commit}')
                event_id = self.git('show', '-s', '--format=%s', sha).split(':', 1)[0]
            except subprocess.CalledProcessError:
                event_id = id
            if not re.fullmatch(r'refine_[a-f0-9]+', event_id):
                raise ValueError('Unknown refinement')
            record = read_json(self.path / 'edits' / (event_id + '.json'))
            if record is None:
                raise ValueError('Unknown refinement in this lineage')
            kind, ident = record['key'].split(':', 1)
            before = record['before']
            if before is None:
                return self.delete(kind, ident, trigger='rollback ' + event_id, rollback_of=event_id)
            current = self.get(kind, ident)
            return self._edit('update' if current else 'create', kind, ident, before['title'], before['body'],
                              module=before['module'], trigger='rollback ' + event_id,
                              evidence=before['evidence'], rollback_of=event_id, restore=before)

    def fork(self, commit):
        with self.transaction():
            self.git('checkout', '-q', '-b', 'lineage-' + uuid4().hex, commit)
        return self.head

    def begin_task(self, task_key, run_id):
        with self.transaction():
            state = self.snapshot()
            if task_key in state['seen']:
                self.git('checkout', '-q', '-b', 'lineage-' + uuid4().hex, state['seen'][task_key]['before'])
                state = self.snapshot()
            before = self.head
            state['seen'][task_key] = {'run_id': run_id, 'before': before, 'created_at': stamp()}
            self._save(state, f'Observe {task_key} in {run_id}')
            return before

    def record_usage(self, entries, run_id):
        with self.transaction():
            state = self.snapshot()
            changed = False
            for entry in entries:
                key = self._key(entry['kind'], entry['id'])
                use = {'run_id': run_id, 'version': entry['version'], 'refinement_id': entry['refinement_id']}
                if use not in state['usage']:
                    state['usage'].append(use)
                    if key in state['entries']:
                        state['entries'][key]['usage'].append(use)
                    changed = True
            if changed:
                self._save(state, 'Record usage ' + run_id)

    def record_outcome(self, run_id, report):
        if set(report) != {'ok', 'issues'} or type(report['ok']) is not bool or not isinstance(report['issues'], list):
            raise ValueError('Outcomes accept only self-check ok and issues')
        outcome = {'run_id': run_id, **report, 'recorded_at': stamp()}
        with self.transaction():
            state = self.snapshot()
            uses = [use for use in state['usage'] if use['run_id'] == run_id]
            for entry in state['entries'].values():
                if any(use in entry['usage'] for use in uses):
                    entry['outcomes'].append(copy.deepcopy(outcome))
            if uses:
                state['outcomes'].append(outcome)
                self._save(state, 'Record self-check outcome ' + run_id)
                import json
                for event_id in {use['refinement_id'] for use in uses}:
                    commit = self.git('log', '--format=%H', '--', 'edits/' + event_id + '.json').splitlines()[-1]
                    self.git('notes', '--ref=outcomes', 'append', '-m', json.dumps(outcome), commit)
