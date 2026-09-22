from __future__ import annotations

from tests.e2e import verify_demo_lanes as demo
from tests.e2e.verify_workspace import retained_metadata


class _D31Client:
    def __init__(self, *, pre_tail: bool, endpoint_reason: str = 'end_silence'):
        self.pre_tail = pre_tail
        self.endpoint_reason = endpoint_reason
        self.stopped = False

    def _snapshot(self):
        segments = ([{'start_sample': 0, 'end_sample': 10_000_000, 'source_lane': 'microphone'}]
                    if self.pre_tail or self.stopped else [])
        return {'snapshot': {'pending_work_items': 0, 'session': {
            'status': 'completed' if self.stopped else 'active',
            'finalization_status': 'final' if self.stopped else 'not_started',
            'pending_span_ids': [], 'committed_samples': 10_000_000,
            'effective_transcript': segments,
        }}}

    def call(self, method, path, body=None):
        if path == '/api/workspace/bootstrap': return {}
        if path == '/api/live/descriptor':
            return {'descriptor': {'frame_samples': 8000, 'sample_rate': 16000, 'source_revision': 'test'}}
        if path == '/api/live/sessions' and method == 'POST': return {'id': 'meeting'}
        if path.endswith('/events?since_seq=-1'):
            events=[]
            if self.pre_tail:
                events=[
                    {'seq': 1, 'kind': 'span_frozen', 'payload': {
                        'start_sample': 0, 'end_sample': 10_000_000, 'reason': self.endpoint_reason}},
                    {'seq': 2, 'kind': 'canonical_queued', 'payload': {'item_id': 7}},
                    {'seq': 3, 'kind': 'canonical_processed', 'payload': {'item_id': 7}},
                ]
            return {'events': events}
        if path.endswith('/snapshot'): return self._snapshot()
        if path.endswith('/stop'):
            self.stopped = True
            return self._snapshot()
        if path == '/api/meetings/meeting': return {'status': 'completed', 'transcript': {'segments': []}}
        if path.endswith('/heartbeat') or path.endswith('/frames'): return {}
        raise AssertionError((method, path, body))


def _passing_score(*args, **kwargs):
    return {'passed': True, 'lanes': {'system': {'wer': 0.0}, 'microphone': {'wer': 0.0}}}


def test_paused_live_tail_is_settled_and_gated_by_end_silence(monkeypatch):
    monkeypatch.setattr(demo, 'score_lanes', _passing_score)
    result=demo.run_case('https://unused',None,'overlap',client=_D31Client(pre_tail=True),realtime=False)

    assert result['passed'] is True
    assert result['settle'] == 'SETTLED'
    assert result['tail_endpoint_reason'] == 'end_silence'
    assert result['tail_latency_seconds'] is not None
    assert result['silence_frames_streamed'] >= 1
    assert result['pre_snapshot_status'] == 'active'
    assert result['stop_requested_before_pre'] is False
    assert all(score['identity_unqualified'] is False for score in result['surfaces'].values())
    assert all(score['unattributed_segment_count'] == score['unattributed_word_count'] == 0
               for score in result['surfaces'].values())
    assert result['status'] == 'completed'
    assert result['finalization_status'] == 'final'
    assert demo.accepted_case(result) is True


def test_no_silence_control_preserves_the_missing_pre_tail(monkeypatch):
    monkeypatch.setattr(demo, 'score_lanes', _passing_score)
    result=demo.run_case('https://unused',None,'alternation',client=_D31Client(pre_tail=False),realtime=False,
                         _stream_tail_silence=False)

    assert result['passed'] is False
    assert result['settle'] == 'TIMEOUT'
    assert result['tail_endpoint_reason'] == 'none'
    assert result['tail_latency_seconds'] is None
    assert result['silence_frames_streamed'] == 0


def test_hard_cap_does_not_satisfy_the_d31_end_silence_boundary(monkeypatch):
    monkeypatch.setattr(demo, 'score_lanes', _passing_score)
    result=demo.run_case('https://unused',None,'overlap',client=_D31Client(pre_tail=True,endpoint_reason='hard_cap'),
                         realtime=False)

    assert result['tail_endpoint_reason'] == 'hard_cap'
    assert result['passed'] is False


def test_d31_row_fields_survive_retained_metadata():
    row={
        'tail_latency_seconds': 2.0,
        'tail_endpoint_reason': 'end_silence',
        'settle': 'SETTLED',
        'silence_frames_streamed': 2,
        'pre_snapshot_status': 'active',
        'stop_requested_before_pre': False,
    }

    assert retained_metadata(row) == row


def test_all_anonymous_surface_is_not_accepted_even_when_word_and_lane_checks_pass(monkeypatch):
    def anonymous_score(*args, **kwargs):
        return {'passed': True, 'identity_unqualified': True,
                'lanes': {'system': {'wer': 0.0}, 'microphone': {'wer': 0.0}}}
    monkeypatch.setattr(demo, 'score_lanes', anonymous_score)
    result=demo.run_case('https://unused',None,'overlap',client=_D31Client(pre_tail=True),realtime=False)

    assert all(score['passed'] is True for score in result['surfaces'].values())
    assert demo.accepted_case(result) is False
