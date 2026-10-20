"""Extraction validity, exact rejected evidence, and historical cache separation."""
import hashlib
import json
from types import SimpleNamespace

import pytest

from loop_research.archive import write_json
from loop_research.archive_audit import ArchiveCorruptionError, fetch_audit
from loop_research.page_fetch import FetchError, PageFetcher, verify_receipt
from loop_research.repl_tools import ResearchTools
from test_direct_fetch import NoModel, response


POLICY = 'unicode-layout-controls-v1'
URL = 'https://example.org/document'


def digest(value):
    return hashlib.sha256(value).hexdigest()


def fetch_tools(ctx, raw, media, *, extracted=None, monkeypatch=None):
    requests = []
    if extracted is not None:
        monkeypatch.setattr('loop_research.page_fetch.shutil.which', lambda name: '/fixture/pdftotext')
        monkeypatch.setattr(ctx, 'run_process', lambda *args, **kwargs:
                            SimpleNamespace(returncode=0, stdout=extracted, stderr=b''))

    def request(url, timeout):
        requests.append(url)
        return response(raw, media)

    return ResearchTools(NoModel(), ctx, fetcher=PageFetcher(ctx, request=request)), requests


@pytest.mark.parametrize('control', ['\x00', '\x01', '\x07', '\x08', '\x1b',
                                    '\x1c', '\x1d', '\x1e', '\x1f', '\x7f',
                                    '\x80', '\x9f'])
def test_plain_text_rejects_each_nonlayout_control_without_stripping(ctx, control):
    original = f'Complete readable beginning. {control} Final qualification.'
    tools, requests = fetch_tools(ctx, original, 'text/plain; charset=utf-8')
    assert tools.fetch(URL) == 'FETCH_FAILED'
    assert requests == [URL]  # No automatic retry, repair, browser or model fallback.
    assert tools.cache == {} and tools.snapshot()['fetched'] == {}
    receipt = ctx.load('fetch_telemetry.json')[0]['receipt']
    assert receipt['reason'] == 'forbidden_control_characters'
    assert receipt['text_policy'] == POLICY
    assert receipt['extraction_chars'] == len(original)
    assert receipt['extraction_bytes'] == len(original.encode())
    assert receipt['extraction_sha256'] == digest(original.encode())
    assert (ctx.path / receipt['extraction_path']).read_bytes() == original.encode()
    assert receipt['extraction_validation'] == {
        'reason': 'forbidden_control_characters', 'forbidden_control_count': 1,
        'forbidden_controls': {f'U+{ord(control):04X}': 1}}
    assert 'text_path' not in receipt and 'readable_chars' not in receipt
    assert tools.snapshot()['failures'][0]['reason'] == receipt['reason']
    assert ctx.load('fetch_telemetry.json')[0]['readable_chars'] is None
    verify_receipt(ctx.path, receipt)


def test_pdf_rejection_archives_exact_stdout_raw_and_complete_diagnostic(ctx, monkeypatch):
    raw = b'%PDF-1.4\narchived synthetic parser input'
    extracted = ('English heading.\f' + '\x02' * 120 + 'English ending.\x80').encode()
    tools, requests = fetch_tools(ctx, raw, 'application/pdf', extracted=extracted,
                                 monkeypatch=monkeypatch)
    assert tools.fetch(URL) == 'FETCH_FAILED'
    receipt = ctx.load('fetch_telemetry.json')[0]['receipt']
    assert requests == [URL] and tools.cache == {} and tools.snapshot()['fetched'] == {}
    assert (ctx.path / receipt['raw_path']).read_bytes() == raw
    assert (ctx.path / receipt['extraction_path']).read_bytes() == extracted
    assert receipt['extraction_sha256'] == digest(extracted)
    assert receipt['parser'] == 'poppler-pdftotext-layout'
    assert receipt['extraction_validation']['forbidden_controls'] == {'U+0002': 120, 'U+0080': 1}
    assert receipt['extraction_validation']['forbidden_control_count'] == 121
    assert receipt['raw_page_chars'] is None
    row, = fetch_audit(ctx.path, [], [], [], tools.snapshot())
    assert row['direct_receipt_verified'] is True
    assert row['readability_validation'] == 'rejected'
    assert row['text_validation_policy'] == POLICY


def test_invalid_utf8_pdf_stdout_is_archived_fetch_failure_not_uncaught_decode(ctx, monkeypatch):
    extracted = b'Readable prefix\xffunmodified suffix'
    tools, requests = fetch_tools(ctx, b'%PDF-1.4\nfixture', 'application/pdf',
                                 extracted=extracted, monkeypatch=monkeypatch)
    assert tools.fetch(URL) == 'FETCH_FAILED'
    receipt = ctx.load('fetch_telemetry.json')[0]['receipt']
    assert receipt['reason'] == 'extraction_decode_error'
    assert receipt['extraction_chars'] is None
    assert receipt['extraction_bytes'] == len(extracted)
    assert receipt['extraction_sha256'] == digest(extracted)
    assert (ctx.path / receipt['extraction_path']).read_bytes() == extracted
    assert requests == [URL] and tools.cache == {} and tools.snapshot()['fetched'] == {}
    assert fetch_audit(ctx.path, [], [], [], tools.snapshot())[0]['readability_validation'] == 'rejected'


@pytest.mark.parametrize('media', ['text/plain; charset=utf-8', 'application/pdf'])
def test_all_explicit_layout_and_valid_unicode_survive_exactly(ctx, monkeypatch, media):
    original = 'α\t中文\n🙂\r\nZ\fQ\vV\x85N\u00a0\u2003e\u0301\u200d\u2028tail\u2029'
    raw = original.encode() if media.startswith('text/') else b'%PDF-1.4\nfixture'
    tools, _ = fetch_tools(ctx, raw, media, monkeypatch=monkeypatch,
                          extracted=None if media.startswith('text/') else original.encode())
    assert tools.fetch(URL) == original
    assert tools.fetch(URL, 'arbitrary focus') == original
    receipt = ctx.load('fetch_telemetry.json')[0]['receipt']
    assert receipt['text_policy'] == POLICY
    assert receipt['extraction_validation'] == {
        'reason': None, 'forbidden_control_count': 0, 'forbidden_controls': {}}
    assert (ctx.path / receipt['text_path']).read_bytes() == original.encode()
    assert (ctx.path / receipt['extraction_path']).read_bytes() == original.encode()
    assert receipt['extraction_sha256'] == receipt['text_sha256']
    assert all(row['readability_validation'] == 'passed'
               for row in fetch_audit(ctx.path, [], [], [], tools.snapshot()))


@pytest.mark.parametrize('control', ['\x01', '\x1c', '\x1d', '\x1e', '\x1f', '\x80'])
def test_html_visible_controls_cannot_be_normalized_away(ctx, control):
    original = f'<p>Visible{control}qualification</p>'
    tools, _ = fetch_tools(ctx, original, 'text/html; charset=utf-8')
    assert tools.fetch(URL) == 'FETCH_FAILED'
    receipt = ctx.load('fetch_telemetry.json')[0]['receipt']
    assert (ctx.path / receipt['extraction_path']).read_bytes() == f'Visible{control}qualification'.encode()
    assert receipt['extraction_validation']['forbidden_control_count'] == 1


def test_controls_in_hidden_html_do_not_reject_full_visible_extraction(ctx):
    original = ('<script>\x01\x1c</script><style>\x80</style><template>\x02</template>'
                '<div hidden>\x03</div><p aria-hidden="true">\x04</p>'
                '<p>Whole visible\ttext α.</p><footer>Final qualification.</footer>')
    tools, _ = fetch_tools(ctx, original, 'text/html; charset=utf-8')
    assert tools.fetch(URL) == 'Whole visible text α.\nFinal qualification.'
    receipt = ctx.load('fetch_telemetry.json')[0]['receipt']
    assert (ctx.path / receipt['raw_path']).read_bytes() == original.encode()
    assert receipt['extraction_validation']['forbidden_control_count'] == 0


def archive_legacy(ctx, text='Historically returned \x01 text.'):
    """A complete pre-policy receipt, independent of the current extractor."""
    raw = text.encode()
    directory = ctx.path / 'downloads'
    directory.mkdir(parents=True)
    (directory / 'old.raw').write_bytes(raw)
    (directory / 'old.txt').write_bytes(raw)
    hop = {'url': URL, 'status': 200, 'headers': {'content-type': 'text/plain'},
           'raw_path': 'downloads/old.raw', 'raw_page_bytes': len(raw), 'raw_sha256': digest(raw)}
    receipt = {'id': 'old', 'fetch_path': 'direct-readable-v1', 'requested_url': URL,
               'status': 'succeeded', 'hops': [hop], **{key: hop[key] for key in
               ('raw_path', 'raw_page_bytes', 'raw_sha256')},
               'text_path': 'downloads/old.txt', 'readable_chars': len(text),
               'text_sha256': digest(raw), 'parser': 'decoded-text-v1'}
    write_json(directory / 'old.json', receipt)
    request = {'id': 1, 'url': URL, 'focus': '', 'source': 'backend',
               'status': 'succeeded', 'fetch_path': 'direct-readable-v1'}
    evidence = {'fetched': {URL: [text]}, 'fetches': [request], 'checks': [], 'searches': [],
                'discoveries': [], 'failures': []}
    write_json(ctx.path / 'evidence.json', evidence)
    write_json(ctx.path / 'fetch_telemetry.json', [{**request, 'receipt': receipt,
        'returned_chars': len(text), 'readable_chars': len(text), 'raw_page_chars': len(text),
        'raw_page_chars_reason': 'decoded_download', 'evidence_eligible': True}])
    write_json(ctx.path / 'tool_cache.json', {json.dumps(['fetch', URL, 'direct-readable-v1']): text})
    return evidence


def test_old_receipt_audit_verifies_faithful_transport_without_claiming_current_validity(ctx):
    evidence = archive_legacy(ctx)
    row, = fetch_audit(ctx.path, [], [], [], evidence)
    assert row['direct_receipt_verified'] is True
    assert row['text_validation_policy'] is None
    assert row['readability_validation'] == 'not_recorded_by_legacy_policy'


def test_legacy_cache_never_bypasses_current_validation_or_loses_history(ctx):
    old = archive_legacy(ctx)
    tools, requests = fetch_tools(ctx, 'Newly rejected \x02 text.', 'text/plain')
    assert tools.fetch(URL) == 'FETCH_FAILED'
    assert requests == [URL]  # Old namespace is not a current-policy cache hit.
    assert tools.snapshot()['fetched'] == old['fetched']  # Historical evidence remains historical.
    assert len(tools.cache) == 1
    assert json.loads(next(iter(tools.cache))) == ['fetch', URL, 'direct-readable-v1']
    old_row, rejected = fetch_audit(ctx.path, [], [], [], tools.snapshot())
    assert old_row['readability_validation'] == 'not_recorded_by_legacy_policy'
    assert rejected['readability_validation'] == 'rejected'


def test_old_receipt_cannot_be_rebranded_by_copying_cache_key(ctx):
    archive_legacy(ctx, 'Old text with no corrupt controls.')
    cache = ctx.load('tool_cache.json')
    cache[json.dumps(['fetch', URL, 'direct-readable-v1', POLICY])] = next(iter(cache.values()))
    write_json(ctx.path / 'tool_cache.json', cache)
    tools, requests = fetch_tools(ctx, 'Must not silently retry.', 'text/plain')
    assert tools.fetch(URL) == 'FETCH_FAILED'
    assert requests == []
    assert tools.snapshot()['failures'][-1]['reason'] == 'receipt_integrity'
    assert json.dumps(['fetch', URL, 'direct-readable-v1', POLICY]) not in tools.cache


@pytest.mark.parametrize('damage', ['artifact', 'diagnostic', 'policy', 'extraction_removed'])
def test_rejected_extraction_artifact_and_diagnostics_are_bound_by_audit(ctx, damage):
    tools, _ = fetch_tools(ctx, 'Visible \x01 text.', 'text/plain')
    assert tools.fetch(URL) == 'FETCH_FAILED'
    telemetry = ctx.load('fetch_telemetry.json')
    receipt = telemetry[0]['receipt']
    if damage == 'artifact':
        (ctx.path / receipt['extraction_path']).write_bytes(b'changed rejected extraction')
    else:
        if damage == 'diagnostic':
            receipt['extraction_validation']['forbidden_control_count'] = 0
        elif damage == 'policy':
            receipt['text_policy'] = 'unknown-policy'
        else:
            for key in list(receipt):
                if key.startswith('extraction_'):
                    del receipt[key]
        write_json(ctx.path / 'downloads' / (receipt['id'] + '.json'), receipt)
        write_json(ctx.path / 'fetch_telemetry.json', telemetry)
    with pytest.raises(ArchiveCorruptionError, match='Direct download'):
        fetch_audit(ctx.path, [], [], [], tools.snapshot())


@pytest.mark.parametrize('damage', ['policy_only', 'entire_validation'])
def test_fresh_cache_and_audit_cannot_downgrade_receipt_to_historical(ctx, damage):
    tools, requests = fetch_tools(ctx, 'Valid complete text.', 'text/plain')
    assert tools.fetch(URL) == 'Valid complete text.'
    telemetry = ctx.load('fetch_telemetry.json')
    receipt = telemetry[0]['receipt']
    del receipt['text_policy']
    if damage == 'entire_validation':
        for key in list(receipt):
            if key.startswith('extraction_'):
                del receipt[key]
    write_json(ctx.path / 'downloads' / (receipt['id'] + '.json'), receipt)
    write_json(ctx.path / 'fetch_telemetry.json', telemetry)
    with pytest.raises(ArchiveCorruptionError, match='policy'):
        fetch_audit(ctx.path, [], [], [], tools.snapshot())
    restored = ResearchTools(NoModel(), ctx, fetcher=tools.fetcher)
    assert restored.fetch(URL) == 'FETCH_FAILED'
    assert restored.snapshot()['failures'][-1]['reason'] == 'receipt_integrity'
    assert requests == [URL] and restored.cache == {}


def test_every_forbidden_control_is_counted_even_when_otherwise_only_whitespace(ctx):
    # Explicit code ranges independent of the implementation's Unicode classifier.
    forbidden = ''.join(chr(code) for code in [*range(32), *range(127, 160)]
                        if code not in (9, 10, 11, 12, 13, 133))
    tools, _ = fetch_tools(ctx, forbidden, 'text/plain')
    assert tools.fetch(URL) == 'FETCH_FAILED'
    receipt = ctx.load('fetch_telemetry.json')[0]['receipt']
    assert receipt['extraction_validation']['forbidden_control_count'] == 59
    assert len(receipt['extraction_validation']['forbidden_controls']) == 59
    assert (ctx.path / receipt['extraction_path']).read_bytes() == forbidden.encode()


def test_an_explicit_retry_refetches_rejected_text_and_can_then_cache_valid_text(ctx):
    replies = iter([response('Corrupt \x02 text.', 'text/plain'),
                    response('Complete corrected source.', 'text/plain')])
    tools = ResearchTools(NoModel(), ctx, fetcher=PageFetcher(ctx, request=lambda *args: next(replies)))
    assert tools.fetch(URL) == 'FETCH_FAILED'
    assert tools.cache == {} and tools.snapshot()['fetched'] == {}
    assert tools.fetch(URL) == 'Complete corrected source.'
    assert tools.fetch(URL) == 'Complete corrected source.'
    assert tools.snapshot()['fetched'] == {URL: ['Complete corrected source.']}
    assert len(tools.cache) == 1
    assert [row['readability_validation'] for row in
            fetch_audit(ctx.path, [], [], [], tools.snapshot())] == ['rejected', 'passed', 'passed']


def test_invalid_extractor_utf8_cannot_be_downgraded_to_entity_decode_failure(ctx, monkeypatch):
    tools, _ = fetch_tools(ctx, b'%PDF-1.4\nfixture', 'application/pdf',
                          extracted=b'prefix\xffsuffix', monkeypatch=monkeypatch)
    assert tools.fetch(URL) == 'FETCH_FAILED'
    telemetry = ctx.load('fetch_telemetry.json')
    receipt = telemetry[0]['receipt']
    for key in list(receipt):
        if key.startswith('extraction_') or key == 'parser':
            del receipt[key]
    write_json(ctx.path / 'downloads' / (receipt['id'] + '.json'), receipt)
    write_json(ctx.path / 'fetch_telemetry.json', telemetry)
    with pytest.raises(ArchiveCorruptionError, match='extraction'):
        fetch_audit(ctx.path, [], [], [], tools.snapshot())


@pytest.mark.parametrize('damage', ['receipt', 'telemetry_record', 'telemetry_file'])
@pytest.mark.parametrize('extracted', [True, False])
def test_failed_download_with_durable_receipt_cannot_lose_audit_evidence(ctx, damage, extracted):
    reply = response('Visible \x01 text.', 'text/plain') if extracted else response('Denied', status=403)
    tools = ResearchTools(NoModel(), ctx, fetcher=PageFetcher(ctx, request=lambda *args: reply))
    assert tools.fetch(URL) == 'FETCH_FAILED'
    telemetry = ctx.load('fetch_telemetry.json')
    receipt = telemetry[0]['receipt']
    assert tools.snapshot()['fetches'][0]['receipt_id'] == receipt['id']
    if extracted:
        (ctx.path / receipt['extraction_path']).unlink()
    if damage == 'receipt':
        del telemetry[0]['receipt']
        write_json(ctx.path / 'fetch_telemetry.json', telemetry)
    elif damage == 'telemetry_record':
        write_json(ctx.path / 'fetch_telemetry.json', [])
    else:
        (ctx.path / 'fetch_telemetry.json').unlink()
    with pytest.raises(ArchiveCorruptionError, match='receipt|telemetry'):
        fetch_audit(ctx.path, [], [], [], tools.snapshot())


def test_failed_receipt_cannot_be_swapped_from_another_request(ctx):
    tools, _ = fetch_tools(ctx, 'Visible \x01 text.', 'text/plain')
    assert tools.fetch(URL) == tools.fetch(URL + '/other') == 'FETCH_FAILED'
    telemetry = ctx.load('fetch_telemetry.json')
    telemetry[0]['receipt'] = telemetry[1]['receipt']
    write_json(ctx.path / 'fetch_telemetry.json', telemetry)
    with pytest.raises(ArchiveCorruptionError, match='Direct download'):
        fetch_audit(ctx.path, [], [], [], tools.snapshot())


def test_fetch_validation_failure_before_download_needs_no_download_receipt(ctx):
    tools, requests = fetch_tools(ctx, 'Never requested.', 'text/plain')
    with pytest.raises(ValueError):
        tools.fetch('file:///unavailable')
    row, = fetch_audit(ctx.path, [], [], [], tools.snapshot())
    assert row['status'] == 'failed'
    assert tools.snapshot()['fetches'][0]['reason'] == 'validation_error'
    assert 'receipt' not in row and requests == []
