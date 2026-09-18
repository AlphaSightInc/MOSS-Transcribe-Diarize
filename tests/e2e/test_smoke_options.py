"""Operator isolation and selection failures must be caught before any browser work."""
import pytest
from tests.e2e.verify_workspace import Harness, parse_args, summary


def test_no_decoder_selection_needs_neither_corpus_nor_relay(tmp_path):
    args = parse_args(['--base', 'https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861',
                       '--rows', '1,6,11,12', '--output', str(tmp_path)])
    assert args.rows == {1,6,11,12}
    assert args.corpus is None
    assert args.allow_local_self_signed is False


@pytest.mark.parametrize('extra', [
    ['--rows', '0'], ['--rows', '1,no'], ['--rows', '2'],
    ['--rows', '7', '--corpus', '/tmp/corpus'],
    ['--rows', '9', '--corpus', '/tmp/corpus'],
    ['--rows', '1', '--base', 'https://example.com', '--allow-local-self-signed'],
])
def test_invalid_selection_or_remote_tls_bypass_rejected(tmp_path, extra):
    with pytest.raises(SystemExit) as exc:
        parse_args(['--output', str(tmp_path), *extra])
    assert exc.value.code == 2


def test_existing_evidence_and_cookies_never_reused(tmp_path):
    existing = tmp_path / 'browser-state.json'
    existing.write_text('{"cookies": [{"value": "foreign"}]}')
    args = parse_args(['--rows', '1', '--output', str(tmp_path)])
    with pytest.raises(ValueError, match='never reused'):
        Harness(args)
    assert 'foreign' in existing.read_text()


def test_summary_reports_missing_selected_rows_as_fail():
    state = {'rows': {'1': {'status': 'PASS'}, '2': {'status': 'FAIL'}}}
    assert summary(state, {1,6}) == '1:PASS | 6:FAIL | total 1/2 PASS, 1 FAIL'


def test_no_provider_is_explicit_skip_not_transcription_failure(tmp_path):
    import asyncio
    harness=Harness(parse_args(['--rows','1','--output',str(tmp_path)]))
    async def api(path):
        assert path=='/api/llm/models'
        return {'body':{'data':[]}}
    harness.api=api
    try:
        asyncio.run(harness.check(9,harness.summaries))
        assert harness.state['rows']['9']['status']=='SKIP'
        assert harness.state['rows']['9']['reason_code']=='no_configured_relay_models'
        assert summary(harness.state,{9})=='9:SKIP | total 0/1 PASS, 0 FAIL, 1 SKIP'
    finally:
        harness.network.close();harness._private.cleanup()
