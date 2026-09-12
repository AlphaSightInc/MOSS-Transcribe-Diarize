from types import SimpleNamespace

import httpx
import pytest

from moss_transcribe_diarize import phase2_acceptance_external as external


@pytest.mark.parametrize("durable_status", ["completed", "interrupted", "active"])
def test_cleanup_distinguishes_recovered_terminal_meeting_from_missing_runtime(tmp_path, durable_status):
    closed = []
    class Client:
        def request(self, method, path, **kwargs):
            if path.endswith('/abort'):
                return httpx.Response(404)
            return httpx.Response(200, json={'id': 'old', 'status': durable_status})
    campaign = external.FixedAccountCampaign(candidate_sha='test', config={'campaign_work_dir': str(tmp_path)})
    campaign._clients['a'] = Client()
    campaign._live_helpers['old'] = ('a', SimpleNamespace(close=lambda: closed.append('old')))
    if durable_status == 'active':
        with pytest.raises(external.ExternalMeasurementError, match='old'):
            campaign.cleanup()
    else:
        campaign.cleanup()
    assert closed == ['old']
    assert not campaign._live_helpers


@pytest.mark.parametrize('timeout', [False, True])
def test_product_observer_zero_audio_session_is_closed_on_success_or_timeout(tmp_path, monkeypatch, timeout):
    aborted = []
    class Client:
        def json(self, *args, **kwargs):
            return {'id': 'zero-audio-observer'}, None
        def request(self, method, path, **kwargs):
            if path.endswith('/abort'):
                aborted.append(path)
            return httpx.Response(200, json={})
        def close(self): pass
    def product(*args):
        if timeout:
            raise TimeoutError('original browser timeout')
        return {'suites': []}
    campaign = external.FixedAccountCampaign(candidate_sha='test', config={'campaign_work_dir': str(tmp_path)})
    campaign._clients['a'] = Client()
    campaign._browser = SimpleNamespace(product_regression=product)
    monkeypatch.setattr(campaign, '_durable_transcript_meeting', lambda: {'id': 'completed'})
    try:
        if timeout:
            with pytest.raises(TimeoutError, match='original browser timeout'):
                campaign.account_product_regression()
        else:
            campaign.account_product_regression()
        assert aborted == ['/api/live/sessions/zero-audio-observer/abort']
        assert not campaign._live_helpers
        assert not campaign._live
    finally:
        campaign.close()
