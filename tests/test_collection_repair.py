"""Reduced markup reproductions and scripted HTTP fixtures; no generated company facts."""
from datetime import date

import httpx
import pytest


@pytest.mark.parametrize("markup,expected,method", [
    ('<meta itemprop="datePublished" content="2023-12-06T20:05:00+0300">', '2023-12-06', 'metadata'),
    ('<script type="application/ld+json">{"@type":"NewsArticle","datePublished":"2024-10-15T17:05:20+01:00","dateModified":"2024-11-08"}</script>', '2024-10-15', 'json_ld'),
    ('<article><header><time datetime="2025-02-03">3 February 2025</time></header></article>', '2025-02-03', 'time'),
    ('<p class="published"><label>Published:</label> 31 October 2025</p>', '2025-10-31', 'visible_label'),
])
def test_reproduced_publication_formats_preserve_support(markup, expected, method):
    from webshaper.sources import extract_document
    result = extract_document((markup + '<p>Fixture article.</p>').encode(), 'text/html', 'https://fixture.invalid/article')
    assert result.published_at == date.fromisoformat(expected)
    assert any(c['method'] == method and c['kind'] == 'publication' and c['support'] for c in result.date_evidence)


def test_conflicting_cfao_style_metadata_and_article_time_remain_unresolved():
    from webshaper.sources import extract_document
    html = '''<meta property="article:published_time" content="2024-04-03T22:13:29+00:00">
    <time class="o-article-hero__date" datetime="2024-04-04">04 April 2024</time>'''
    result = extract_document(html.encode(), 'text/html', 'https://fixture.invalid/news')
    assert result.published_at is None and result.date_status == 'conflicting'
    assert {c['parsed_date'] for c in result.date_evidence} == {'2024-04-03', '2024-04-04'}


def test_related_articles_modification_events_and_webflow_build_dates_are_not_publication():
    from webshaper.sources import extract_document
    html = '''<!-- Last Published: Wed Sep 30 2026 02:32:31 GMT+0000 -->
    <meta property="article:modified_time" content="2025-02-02">
    <script type="application/ld+json">{"@graph":[
     {"@type":"Event","startDate":"2025-02-01"},
     {"@type":"NewsArticle","url":"https://fixture.invalid/related","datePublished":"2025-03-01"}]}</script>
    <aside><time datetime="2025-04-01">April 1 2025</time></aside>
    <p>Our event is on May 6, 2025.</p><p>Updated: June 7, 2025</p>'''
    result = extract_document(html.encode(), 'text/html', 'https://fixture.invalid/current')
    assert result.published_at is None
    assert all(c['kind'] != 'publication' for c in result.date_evidence)
    assert any(c['kind'] == 'modification' for c in result.date_evidence)


def test_malformed_rocketlab_dates_and_incomplete_time_never_invent_a_date():
    from webshaper.sources import extract_document
    html = '''<script type="application/ld+json">{"@type":"Article","datePublished":"2017-0-22TAD::Z"}</script>
    <time class="dt-published" datetime="Dec 6">Dec 6</time>'''
    result = extract_document(html.encode(), 'text/html', 'https://fixture.invalid/news')
    assert result.published_at is None and result.date_status == 'unresolved'


def mock_http(monkeypatch, routes):
    from webshaper import sources
    requests = []
    client = httpx.Client
    def handler(request):
        url = str(request.url)
        requests.append(url)
        assert url in routes, url
        status, headers, content = routes[url]
        return httpx.Response(status, headers=headers, content=content, request=request)
    monkeypatch.setattr(sources.httpx, 'Client', lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setattr(sources.socket, 'getaddrinfo', lambda *args: [(2, 1, 6, '', ('93.184.216.34', 443))])
    return requests


def test_bounded_redirect_checks_destination_robots_and_reuses_snapshot(tmp_path, monkeypatch):
    from webshaper.sources import SourceStore
    requests = mock_http(monkeypatch, {
        'https://old.invalid/robots.txt': (404, {}, ''),
        'https://old.invalid/a': (301, {'location': 'https://new.invalid/article'}, ''),
        'https://new.invalid/robots.txt': (200, {}, 'User-agent: *\nAllow: /'),
        'https://new.invalid/article': (200, {'content-type': 'text/html'}, '<p>Published: 31 October 2025</p><p>Fixture.</p>')})
    store = SourceStore(tmp_path)
    source, _ = store.capture_url('https://old.invalid/a', ['old.invalid'])
    assert source.original_url == 'https://old.invalid/a'
    assert source.final_url == 'https://new.invalid/article'
    assert source.published_at == date(2025, 10, 31) and source.date_evidence
    assert requests.index('https://new.invalid/robots.txt') < requests.index('https://new.invalid/article')
    before = list(requests)
    again, _ = store.capture_url('https://old.invalid/a', ['old.invalid'])
    assert source == again and requests == before


def test_redirect_cannot_bypass_destination_denial(tmp_path, monkeypatch):
    from webshaper.sources import SourceStore
    requests = mock_http(monkeypatch, {
        'https://old.invalid/robots.txt': (404, {}, ''),
        'https://old.invalid/a': (302, {'location': 'https://new.invalid/private'}, ''),
        'https://new.invalid/robots.txt': (200, {}, 'User-agent: *\nDisallow: /')})
    with pytest.raises(ValueError, match='blocked_access'):
        SourceStore(tmp_path).capture_url('https://old.invalid/a', ['old.invalid'])
    assert 'https://new.invalid/private' not in requests


def test_redirect_loop_and_unsupported_format_have_distinct_codes(tmp_path, monkeypatch):
    from webshaper.sources import SourceStore
    mock_http(monkeypatch, {'https://x.invalid/robots.txt': (404, {}, ''),
        'https://x.invalid/a': (302, {'location': '/a'}, ''),
        'https://x.invalid/image': (200, {'content-type': 'image/png'}, b'\x89PNG')})
    store = SourceStore(tmp_path)
    with pytest.raises(ValueError, match='redirect_loop'):
        store.capture_url('https://x.invalid/a', ['x.invalid'])
    with pytest.raises(ValueError, match='unsupported_format'):
        store.capture_url('https://x.invalid/image', ['x.invalid'])


def test_sentia_blog_schema_matches_percent_encoded_current_article():
    from webshaper.sources import extract_document
    html = '''<script type="application/ld+json">{"@type":"Blog", "headline":"Fixture announcement",
    "mainEntityOfPage":{"@id":"https://fixture.invalid/sælges"},
    "datePublished":"2023-10-09T08:03:28+0000", "dateModified":"2024-02-20T11:32:13+0000"}</script>'''
    result = extract_document(html.encode(), 'text/html', 'https://fixture.invalid/s%C3%A6lges')
    assert result.published_at == date(2023, 10, 9)


def test_article_query_id_must_match_but_tracking_query_is_ignored():
    from webshaper.publication import page_identity
    assert page_identity('https://x.invalid/news?id=1') != page_identity('https://x.invalid/news?id=2')
    assert page_identity('https://x.invalid/news?_hsmi=123') == page_identity('https://x.invalid/news')


@pytest.mark.parametrize('markup', [
    '<article><header><p>Updated: <time datetime="2024-01-01">January 1, 2024</time></p></header></article>',
    '<article><header><h1>Company update</h1><span>Updated: </span><time datetime="2024-01-01">January 1, 2024</time></header></article>',
    '<article><header>Last updated: <time datetime="2024-01-01">January 1, 2024</time></header></article>',
    '<p class="last-updated"><span class="published">January 1, 2024</span></p>',
    '<article><header><time itemprop="startDate" datetime="2024-01-01">January 1, 2024</time></header></article>',
    '<aside><meta itemprop="datePublished" content="2024-01-01"></aside>',
    '<aside><script type="application/ld+json">{"@type":"Article","datePublished":"2024-01-01"}</script></aside>',
])
def test_structured_dates_cannot_escape_event_updated_or_related_context(markup):
    from webshaper.sources import extract_document
    result = extract_document(markup.encode(), 'text/html', 'https://fixture.invalid/current')
    assert result.published_at is None


def test_nested_article_cannot_discard_different_parent_page_identity():
    from webshaper.sources import extract_document
    html = '''<script type="application/ld+json">{"@type":"WebPage",
    "url":"https://fixture.invalid/other", "mainEntity":{"@type":"Article",
    "datePublished":"2020-01-01"}}</script>'''
    result = extract_document(html.encode(), 'text/html', 'https://fixture.invalid/current')
    assert result.published_at is None


def test_collection_reuses_success_and_failure_when_source_queue_grows(tmp_path, monkeypatch):
    from webshaper.pipeline import collect_sources
    from webshaper.sources import SourceStore
    from webshaper.models import RunConfig, SourceInput
    from webshaper.storage import Journal
    requests = mock_http(monkeypatch, {
        'https://x.invalid/robots.txt': (404, {}, ''),
        'https://x.invalid/blocked': (403, {}, ''),
        'https://x.invalid/a': (200, {'content-type': 'text/html'}, '<p>Published: 1 January 2025</p>'),
        'https://x.invalid/b': (200, {'content-type': 'text/html'}, '<p>Published: 2 January 2025</p>')})
    config = RunConfig(as_of='2025-12-31', allowed_domains=['x.invalid'])
    store = SourceStore(tmp_path / 'sources')
    inputs = [SourceInput(origin='https://x.invalid/' + p) for p in ['a', 'blocked']]
    with Journal(tmp_path / 'run.sqlite', {}, config.budget) as journal:
        assert len(collect_sources(config, store, journal, inputs)) == 1
        assert len(collect_sources(config, store, journal, inputs + [SourceInput(origin='https://x.invalid/b')])) == 2
        assert requests.count('https://x.invalid/blocked') == 1
        assert requests.count('https://x.invalid/a') == 1


def test_repair_continuation_preserves_accounting_and_original_snapshots(tmp_path):
    from webshaper.continuation import import_collection_run
    from webshaper.models import RunConfig, CampaignConfig, Budget
    from webshaper.pipeline import frozen_config
    from webshaper.sources import SourceStore
    from webshaper.storage import Journal, BudgetExceeded
    config = RunConfig(as_of='2025-12-31', research_mode='open_web', target_tasks=250, layers=2,
                       campaign=CampaignConfig(), budget=Budget(max_calls=1, max_tokens=1000))
    old = tmp_path / 'old'
    store = SourceStore(old / 'sources')
    raw = b'<html><meta itemprop="datePublished" content="2024-10-23"><p>Fixture company announcement.</p></html>'
    source = store.capture_text('https://fixture.invalid/news', 'Fixture', 'Fixture company announcement.', raw=raw)
    with Journal(old / 'run.sqlite', frozen_config(config), config.budget) as journal:
        journal.reserve('prior-call', 'generator:test', 0, 1000, 0)
        journal.complete('prior-call', {}, 0, 900)
        journal.record('companies', 'fixture-company', {'company_id':'fixture-company', 'name':'FICTIONAL'})
    before = (old / 'sources' / source.raw_path).read_bytes()
    new = tmp_path / 'new'
    with Journal(new / 'run.sqlite', frozen_config(config), config.budget) as journal:
        import_collection_run(old, new, config, journal)
        import_collection_run(old, new, config, journal)
        assert journal.usage()['calls'] == 1 and journal.usage()['tokens'] == 900
        with pytest.raises(BudgetExceeded):
            journal.reserve('new-call', 'generator:test', 0, 100, 0)
        repaired = SourceStore(new / 'sources').all()
        assert len(repaired) == 1 and repaired[0].published_at == date(2024, 10, 23)
        assert repaired[0].raw_hash == source.raw_hash
        assert repaired[0].retrieved_at == source.retrieved_at
    assert (old / 'sources' / source.raw_path).read_bytes() == before


def test_pilot_success_requires_multiple_companies_and_an_accepted_expansion():
    from webshaper.campaign import pilot_reached
    from webshaper.models import PilotConfig
    from test_validation import candidate
    finals = []
    for index in range(5):
        c = candidate()
        c.company_id = 'A'
        finals.append(c)
    pilot = PilotConfig()
    assert not pilot_reached(finals, pilot)
    finals[-1].company_id = 'B'
    assert not pilot_reached(finals, pilot)
    finals[-1].layer = 1
    assert pilot_reached(finals, pilot)
