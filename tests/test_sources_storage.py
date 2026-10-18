from datetime import date

import pytest


def test_snapshots_are_immutable_and_spans_are_exact(tmp_path):
    from webshaper.sources import SourceStore
    store = SourceStore(tmp_path / "sources")
    source = store.capture_text("local:test", "Old", "Atlas builds robots.", date(2025, 1, 1))
    evidence = store.evidence(source, "c1", "builds robots")
    assert store.read(source)[evidence.span_start:evidence.span_end] == "builds robots"
    changed = store.capture_text("local:test", "New", "Atlas builds drones.", date(2025, 1, 1))
    assert source.content_hash != changed.content_hash
    assert store.read(source) == "Atlas builds robots."
    with pytest.raises(ValueError, match="span"):
        store.evidence(source, "c2", "invented evidence")


def test_budget_reservations_cache_and_uncertain_calls_survive_restart(tmp_path):
    from webshaper.storage import Journal, BudgetExceeded, UncertainCall
    from webshaper.models import Budget
    db = tmp_path / "run.sqlite"
    limits = Budget(max_usd=1, max_tokens=100, max_searches=2, max_calls=5)
    with Journal(db, {"mode": "fixture"}, limits) as journal:
        assert journal.reserve("one", "model", .6, 60, 0) is None
        journal.complete("one", {"ok": True}, .4, 40)
        assert journal.reserve("one", "model", .6, 60, 0) == {"ok": True}
        journal.reserve("two", "model", .5, 50, 0)
    with Journal(db, {"mode": "fixture"}, limits) as journal:
        with pytest.raises(UncertainCall):
            journal.reserve("two", "model", .5, 50, 0)
        with pytest.raises(BudgetExceeded):
            journal.reserve("three", "model", .2, 20, 0)
        assert journal.usage()["cost_upper_bound_usd"] == pytest.approx(.9)
        assert journal.usage()["uncertain_calls"] == 1


def test_run_configuration_cannot_change_on_resume(tmp_path):
    from webshaper.storage import Journal
    from webshaper.models import Budget
    with Journal(tmp_path / "run.sqlite", {"judge": "a"}, Budget()):
        pass
    with pytest.raises(ValueError, match="frozen"):
        Journal(tmp_path / "run.sqlite", {"judge": "b"}, Budget())


def test_url_scope_is_enforced_before_network(tmp_path):
    from webshaper.sources import SourceStore
    store = SourceStore(tmp_path)
    with pytest.raises(ValueError, match="scope"):
        store.capture_url("https://outside.example/private", ["inside.example"])


def test_repeated_verbatim_text_gets_a_deterministic_auditable_span(tmp_path):
    from webshaper.sources import SourceStore
    store = SourceStore(tmp_path)
    source = store.capture_text("test", "test", "Atlas builds robots.\nSummary: Atlas builds robots.")
    span = store.evidence(source, "claim", "Atlas builds robots.")
    assert span.span_start == 0
    assert store.read(source)[span.span_start:span.span_end] == "Atlas builds robots."


def test_raw_snapshot_corruption_is_detected(tmp_path):
    from webshaper.sources import SourceStore
    store = SourceStore(tmp_path)
    source = store.capture_text("test", "test", "Atlas builds robots.")
    (store.root / source.raw_path).write_bytes(b"corrupted raw")
    with pytest.raises(ValueError, match="hash"):
        store.read(source)
