import subprocess

import pytest

from loop_research.harness import Harness


def commits(h):
    return int(subprocess.check_output(['git', '-C', str(h.path), 'rev-list', '--count', 'HEAD']))


@pytest.mark.parametrize('kind', ['prompt', 'memory', 'skill', 'subagent'])
def test_crud_round_trip_one_commit_per_edit(tmp_path, kind):
    h = Harness(tmp_path / 'harness')
    n = commits(h)
    entry = h.create(kind, 'Discovery tactic', 'Enumerate directories first.', trigger='repeated failure', evidence=['run1'])
    assert commits(h) == n + 1
    assert Harness(h.path).get(kind, entry['id']) == entry
    assert h.list(kind) == [entry]
    updated = h.update(kind, entry['id'], 'Better discovery', 'Check official directories.', trigger='run2', evidence=['run2'])
    assert updated['version'] == 2 and updated['created_at'] == entry['created_at']
    assert commits(h) == n + 2
    assert h.delete(kind, entry['id'], trigger='obsolete', evidence=['run3'])
    assert commits(h) == n + 3 and h.get(kind, entry['id']) is None
    assert not h.delete(kind, entry['id'])
    assert commits(h) == n + 3


def test_bm25_ranks_relevant_entries_without_body_cap(tmp_path):
    h = Harness(tmp_path / 'harness')
    h.create('memory', 'Finance', 'Annual reports accounting cash flow')
    short = h.create('skill', 'Botanical directories', 'Botanical species identification')
    h.create('skill', 'Other research', ('unrelated ' * 9000) + 'botanical')
    assert h.search('botanical')[0]['id'] == short['id']
    assert h.search('unmatched') == []
    assert h.search('accounting', kind='skill') == []
    h.create('memory', '登录修复', '登录错误验证')
    assert h.search('登录故障')[0]['title'] == '登录修复'


def test_rollback_restores_target_and_keeps_unrelated_edits(tmp_path):
    h = Harness(tmp_path / 'harness')
    e = h.create('memory', 'Failure', 'original')
    h.update('memory', e['id'], 'Failure', 'bad change')
    refinement = h.head
    other = h.create('skill', 'Unrelated', 'keep this')
    n = commits(h)
    h.rollback(refinement)
    assert commits(h) == n + 1
    assert h.get('memory', e['id'])['body'] == 'original'
    assert h.get('skill', other['id']) == other
    with pytest.raises(ValueError):
        h.rollback('not-a-refinement')


def test_learn_once_forks_before_first_exposure_even_after_rollback(tmp_path):
    h = Harness(tmp_path / 'harness')
    base = h.head
    h.begin_task('widesearch:one', 'run1')
    lesson = h.create('memory', 'Task one', 'research from task one')
    edit = h.head
    h.begin_task('widesearch:two', 'run2')
    h.rollback(edit)
    h.create('memory', 'Later memory', 'more task one facts')
    branch = h.branch
    h.begin_task('widesearch:one', 'rerun')
    assert h.branch != branch
    assert h.get('memory', lesson['id']) is None
    assert h.list() == []
    assert h.snapshot()['seen']['widesearch:one']['before'] == base


def test_outcome_history_attaches_to_used_version_without_grades(tmp_path):
    h = Harness(tmp_path / 'harness')
    e = h.create('skill', 'Directories', 'Search directories')
    edit = h.head
    h.record_usage([e], 'run1')
    h.record_outcome('run1', {'ok': False, 'issues': ['fabricated_quote']})
    actual = h.get('skill', e['id'])
    assert actual['usage'][0]['run_id'] == 'run1'
    assert actual['outcomes'][0]['ok'] is False
    notes = subprocess.check_output(['git', '-C', str(h.path), 'notes', '--ref=outcomes', 'show', edit], text=True)
    assert 'run1' in notes and 'fabricated_quote' in notes
    with pytest.raises(ValueError, match='self-check'):
        h.record_outcome('run2', {'grade': 1.0})


def test_bad_shapes_cannot_escape_repo_or_turn_memories_into_modules(tmp_path):
    h = Harness(tmp_path / 'harness')
    with pytest.raises(ValueError):
        h.create('memory', 'bad', 'body', id='../escape')
    with pytest.raises(ValueError):
        h.create('memory', 'bad', 'body', module='print(1)')
    with pytest.raises(ValueError):
        h.create('factory', 'bad', 'body')


def test_rollback_removes_module_added_by_refinement(tmp_path):
    h = Harness(tmp_path / 'harness')
    e = h.create('skill', 'Tactic', 'original')
    h.update('skill', e['id'], 'Tactic', 'new', module='def run(): return 42')
    h.rollback(h.head)
    assert h.get('skill', e['id'])['module'] is None


def test_deleted_used_entry_still_records_outcome(tmp_path):
    h = Harness(tmp_path / 'harness')
    e = h.create('memory', 'Failure', 'lesson'); commit = h.head
    h.record_usage([e], 'run1'); h.delete('memory', e['id'])
    h.record_outcome('run1', {'ok': False, 'issues': ['empty_output']})
    assert 'run1' in h.git('notes', '--ref=outcomes', 'show', commit)


def test_failed_commit_leaves_no_edit_for_next_commit(tmp_path, monkeypatch):
    h = Harness(tmp_path / 'harness'); before = h.head
    commit = h.commit
    def fail(*a):
        raise RuntimeError('git write failure')
    monkeypatch.setattr(h, 'commit', fail)
    with pytest.raises(RuntimeError, match='git write'):
        h.create('memory', 'Failed', 'must not persist')
    assert h.list() == [] and h.head == before
    monkeypatch.setattr(h, 'commit', commit)
    h.create('memory', 'Successful', 'persist this')
    assert len(list((h.path / 'edits').glob('*.json'))) == 1


def test_rollback_deletion_preserves_usage_outcomes_and_creation_time(tmp_path):
    h = Harness(tmp_path / 'harness')
    entry = h.create('memory', 'Failure', 'prior lesson')
    h.record_usage([entry], 'run1')
    h.record_outcome('run1', {'ok': False, 'issues': ['fabricated_quote']})
    prior = h.get('memory', entry['id'])
    h.delete('memory', entry['id'])
    h.rollback(h.head)
    restored = h.get('memory', entry['id'])
    for key in ('usage', 'outcomes', 'created_at'):
        assert restored[key] == prior[key]
    assert restored['version'] == prior['version'] + 1
    assert restored['refinement_id'] != prior['refinement_id']
