"""Synthetic regressions for the source-cap and extraction feedback failures."""
from datetime import date
import pytest

from webshaper.models import RunConfig, SourceInput
from webshaper.pipeline import collect_sources
from webshaper.sources import SourceStore, extract_document
from webshaper.storage import Journal


def capture(store, original, final=None, published=False):
    final = final or original
    raw = ('<html><p>FICTIONAL source ' + final + '</p>' +
           ('<meta itemprop="datePublished" content="2025-01-01">' if published else '') + '</html>').encode()
    return store.capture_document(final, raw, extract_document(raw, 'text/html', final),
                                  original_url=original, final_url=final)


def test_unusable_cached_pages_cannot_displace_usable_or_new_sources(tmp_path, monkeypatch):
    store = SourceStore(tmp_path / 'sources')
    urls = ['https://fixture.invalid/' + p for p in ('a-bad', 'b-bad', 'c-new', 'z-good')]
    for url in (urls[0], urls[1], urls[3]):
        capture(store, url, published=url == urls[3])
    fetched = []
    def fetch(url, domains, spec=None):
        cached = store.reusable(url)
        if cached:
            return cached, []
        fetched.append(url)
        return capture(store, url, published=True), []
    monkeypatch.setattr(store, 'capture_url', fetch)
    config = RunConfig(as_of=date(2025, 12, 31), research_mode='open_web', max_sources=2)
    with Journal(tmp_path / 'run.sqlite', {}, config.budget) as journal:
        inputs = [SourceInput(origin=u) for u in urls]
        selected = collect_sources(config, store, journal, inputs)
        assert {s.url_or_local_origin for s in selected} == {urls[2], urls[3]}
        assert len(store.all()) == 4  # unusable original captures still exist privately
        assert collect_sources(config, store, journal, inputs) == selected
    assert fetched == [urls[2]]


def test_redirect_aliases_do_not_consume_multiple_source_slots(tmp_path, monkeypatch):
    store = SourceStore(tmp_path / 'sources')
    urls = ['https://fixture.invalid/' + p for p in ('a-alias', 'b-alias', 'c-other')]
    captures = {u: capture(store, u, 'https://fixture.invalid/same' if i < 2 else u, True)
                for i, u in enumerate(urls)}
    monkeypatch.setattr(store, 'capture_url', lambda url, domains, spec=None: (captures[url], []))
    config = RunConfig(as_of=date(2025, 12, 31), research_mode='open_web', max_sources=2)
    with Journal(tmp_path / 'run.sqlite', {}, config.budget) as journal:
        selected = collect_sources(config, store, journal, [SourceInput(origin=u) for u in urls])
    assert {s.final_url for s in selected} == {'https://fixture.invalid/same', urls[2]}
    assert len(store.all()) == 3  # both original URL records are retained


def test_event_repair_feedback_identifies_predicate_and_required_binding():
    from test_query import graph
    from webshaper.query import validate_bundle
    bundle = graph()
    fact = bundle.facts[0]
    fact.subject_id, fact.predicate, fact.object_id_or_value = 'i', 'portfolio_company', 'a'
    with pytest.raises(ValueError, match=r'portfolio_company.*event_id=None'):
        validate_bundle(bundle)
    assert fact.event_id == 'a1'  # invalid output is rejected, never silently rewritten


def test_quote_repair_feedback_identifies_missing_literal(tmp_path):
    store = SourceStore(tmp_path)
    source = store.capture_text('fixture:example', 'FICTIONAL', "Fixture's electric buses")
    with pytest.raises(ValueError) as error:
        store.evidence(source, 'fixture-claim', 'Fixture’s electric buses')
    assert source.source_id in str(error.value)
    assert 'Fixture’s electric buses' in str(error.value)
