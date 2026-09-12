"""Exercise the real lane retention boundary through the acceptance transport seam."""
from types import SimpleNamespace
import threading

import pytest

from moss_transcribe_diarize import phase2_acceptance_external as external
from moss_transcribe_diarize.app.live_ingest import LiveV2LaneCapacityError
from moss_transcribe_diarize.app.live_lane_contract import LiveV2Frame, LiveLane
from moss_transcribe_diarize.app.live_v2_session import LiveV2Session


def test_overload_workload_reaches_real_sixty_second_lane_capacity_and_retries(monkeypatch, tmp_path):
    campaign = external.FixedAccountCampaign(candidate_sha='test', config={'campaign_work_dir': str(tmp_path)})
    class Client:
        def json(self, *args):
            return {'descriptor': {'frame_samples': 8000, 'bounds': {'max_retained_samples': 960000}}}, None
    campaign._clients['a'] = Client()
    source = LiveV2Session(max_retained_samples=960000)
    probe = external._CampaignBackpressure(8)
    refusal = []
    retried = []
    drained = threading.Event()
    errors = []

    def drain():
        watermarks = {lane: rows[-1].frame.sequence for lane in LiveLane
                      if (rows := source.retained_frames(lane))}
        if watermarks:
            source.account_through(watermarks)

    class Target:
        def accept_lane(self, sid, payload):
            if refusal and not retried:
                assert payload is refusal[0]
                retried.append(payload)
            try:
                source.accept(LiveV2Frame.from_dict(payload))
            except LiveV2LaneCapacityError as exc:
                refusal.append(payload)
                raise external.AccountReplayTransportFailure('full', http_status=429) from exc
            if drained.is_set():
                drain()
        def heartbeat(self, sid): pass
        def snapshot(self, sid): return SimpleNamespace(pending_work_items=0)

    class Peer:
        def accept_frame(self, sid, frame):
            drain()
            drained.set()
            return SimpleNamespace(snapshot=SimpleNamespace(pending_work_items=0))

    def run_load(*, sessions, duration_seconds, embedded_backpressure):
        assert sessions == 8 and embedded_backpressure
        target = Target()
        frame_count = int(duration_seconds * 16000 / 8000)
        def push():
            try:
                for seq in range(frame_count):
                    probe.accept(0, target, 'target', external.AudioFrame(seq, b'\0\0' * 8000, 8000, 16000))
            except Exception as exc:
                errors.append(exc)
        thread = threading.Thread(target=push)
        thread.start()
        try:
            assert probe._refusal_seen.wait(timeout=3), 'campaign ended before the 60-second lane boundary'
            probe.accept(1, Peer(), 'peer', external.AudioFrame(0, b'\0\0' * 8000, 8000, 16000))
        finally:
            thread.join(timeout=3)
        assert not thread.is_alive()
        assert not errors, errors
        assert len(refusal) == len(retried) == 1
        assert refusal[0]['sequence'] == 120
        assert all(row.accepted_samples == frame_count * 8000 for row in source.snapshot().lanes.values())
        return {'embedded_backpressure_observation': probe.observation(),
                'cross_account_sentinel_deliveries': 0, 'marker_isolation_failures': 0,
                'dispatch_skew': 0, 'fairness_measured': True}
    monkeypatch.setattr(campaign, '_run_live_load', run_load)
    result = campaign.eight_session_overload()
    assert result['per_session_backpressure_observed'] is True
    assert result['peer_progress_during_backpressure'] is True
    assert result['refused_frame_retry_succeeded'] is True


def test_campaign_backpressure_retry_has_a_wall_deadline(monkeypatch):
    probe = external._CampaignBackpressure(8)
    probe._peer_progress_seen.set()
    now = [0.0]
    monkeypatch.setattr(external.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(external.time, 'sleep', lambda seconds: now.__setitem__(0, now[0] + 31))
    class Target:
        def accept_lane(self, *args):
            raise external.AccountReplayTransportFailure('full', http_status=429)
        def heartbeat(self, sid): pass
    # A bounded fake response count keeps the old unbounded implementation from hanging.
    attempts = [0]
    original = Target.accept_lane
    def accept(self, *args):
        attempts[0] += 1
        assert attempts[0] < 4, 'unbounded retry'
        original(self, *args)
    monkeypatch.setattr(Target, 'accept_lane', accept)
    with pytest.raises(external.ExternalMeasurementError, match='retry timed out'):
        probe.accept(0, Target(), 'target', external.AudioFrame(0, b'\0\0' * 8000, 8000, 16000))
