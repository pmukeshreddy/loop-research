import pytest

from loop_research.archive import write_json
from loop_research.benchmarks.wandr import grader


def test_wandr_child_uses_report_context_for_all_judge_logs(ctx, monkeypatch):
    request = ctx.root / 'request.json'
    work = ctx.root / 'reports' / ctx.run_id / 'grading' / ctx.task_id / 'wandr'
    write_json(request, {'root': str(ctx.root), 'run_id': ctx.run_id, 'task_id': ctx.task_id,
                        'config': ctx.config.model_dump(), 'package': str(work), 'work': str(work)})
    monkeypatch.setattr(grader, 'load_verifier', lambda path: object())
    class ProbeComplete(Exception):
        pass
    def capture(verifier, child_ctx, cache):
        child_ctx.save('judge-marker.json', {'grade_secret': 'private'})
        raise ProbeComplete()
    monkeypatch.setattr(grader, 'install_services', capture)
    with pytest.raises(ProbeComplete):
        grader.worker(request)
    assert not (ctx.path / 'judge-marker.json').exists()
    assert (ctx.root / 'reports' / ctx.run_id / 'grading' / ctx.task_id / 'judge-marker.json').exists()
