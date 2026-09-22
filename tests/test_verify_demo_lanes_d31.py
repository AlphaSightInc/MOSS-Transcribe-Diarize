from __future__ import annotations

import subprocess

from tests.e2e import verify_demo_lanes as demo
from tests.e2e.verify_workspace import retained_metadata


class _Clock:
    def __init__(self, value=0.0): self.value=value
    def __call__(self): return self.value


class _D31Client:
    def __init__(self, *, pre_tail: bool, endpoint_reason: str = 'end_silence',
                 post_endpoint_reason: str | None = None, snapshot_times=(), clock=None,
                 settle_after: int = 1, segments=None, empty_post_events: bool = False,
                 tail_span_end: int = 10_000_000, extra_pending_until: int | None = None):
        self.pre_tail = pre_tail
        self.endpoint_reason = endpoint_reason
        self.post_endpoint_reason = post_endpoint_reason or endpoint_reason
        self.snapshot_times = tuple(snapshot_times)
        self.clock = clock
        self.settle_after = settle_after
        self.empty_post_events = empty_post_events
        self.extra_pending_until = extra_pending_until
        self.tail_span_end = tail_span_end
        self.segments = (segments if segments is not None else [
            {'start_sample': 0, 'end_sample': tail_span_end, 'source_lane': 'microphone'}])
        self.stopped = False
        self.post_events_available = True
        self.live_snapshot_reads = 0
        self.active_event_reads = 0

    def _snapshot(self):
        segments = self.segments if self.pre_tail or self.stopped else []
        return {'snapshot': {'pending_work_items': 0, 'session': {
            'status': 'completed' if self.stopped else 'active',
            'finalization_status': 'final' if self.stopped else 'not_started',
            'pending_span_ids': [], 'committed_samples': self.tail_span_end,
            'effective_transcript': segments,
        }}}

    def _events(self):
        if self.stopped:
            if self.empty_post_events: return []
            if not self.post_events_available: return []
            if not self.pre_tail:
                return [{'seq': 4, 'kind': 'canonical_queued', 'payload': {
                    'item_id': 8, 'reason': 'stop'}}]
            return [{'seq': 1, 'kind': 'span_frozen', 'payload': {
                'span_id': 7, 'start_sample': 0, 'end_sample': self.tail_span_end,
                'reason': self.post_endpoint_reason}},
                    {'seq': 2, 'kind': 'canonical_queued', 'payload': {'item_id': 7}},
                    {'seq': 3, 'kind': 'canonical_processed', 'payload': {'item_id': 7, 'span_id': 7}}]
        if not self.pre_tail: return []
        self.active_event_reads += 1
        events=[{'seq': 1, 'kind': 'span_frozen', 'payload': {
            'span_id': 7, 'start_sample': 0, 'end_sample': self.tail_span_end, 'reason': self.endpoint_reason}},
                {'seq': 2, 'kind': 'canonical_queued', 'payload': {'item_id': 7}}]
        if self.active_event_reads >= self.settle_after:
            events.append({'seq': 3, 'kind': 'canonical_processed', 'payload': {'item_id': 7, 'span_id': 7}})
        if self.extra_pending_until is not None:
            events.append({'seq': 4, 'kind': 'canonical_queued', 'payload': {'item_id': 8}})
            if self.active_event_reads >= self.extra_pending_until:
                events.append({'seq': 5, 'kind': 'canonical_processed', 'payload': {'item_id': 8, 'span_id': 8}})
        return events

    def call(self, method, path, body=None):
        if path == '/api/workspace/bootstrap': return {}
        if path == '/api/live/descriptor':
            return {'descriptor': {'frame_samples': 8000, 'sample_rate': 16000, 'source_revision': 'test'}}
        if path == '/api/live/sessions' and method == 'POST': return {'id': 'meeting'}
        if path.endswith('/events?since_seq=-1'): return {'events': self._events()}
        if path.endswith('/snapshot'):
            if not self.stopped:
                if self.clock is not None and self.snapshot_times:
                    self.clock.value=self.snapshot_times[min(self.live_snapshot_reads, len(self.snapshot_times)-1)]
                self.live_snapshot_reads += 1
            return self._snapshot()
        if path.endswith('/stop'):
            self.stopped = True
            return self._snapshot()
        if path == '/api/meetings/meeting':
            if self.stopped: self.post_events_available = False
            return {'status': 'completed', 'transcript': {'segments': self.segments}}
        if path.endswith('/heartbeat') or path.endswith('/frames'): return {}
        raise AssertionError((method, path, body))


def _passing_score(*args, **kwargs):
    return {'passed': True, 'identity_unqualified': False,
            'unattributed_segment_count': 0, 'unattributed_word_count': 0,
            'lanes': {'system': {'wer': 0.0}, 'microphone': {'wer': 0.0}}}


def test_paused_live_tail_is_settled_and_gated_by_end_silence(monkeypatch):
    monkeypatch.setattr(demo, 'score_lanes', _passing_score)
    result=demo.run_case('https://unused',None,'overlap',client=_D31Client(pre_tail=True),realtime=False)

    assert result['passed'] is True
    assert result['settle'] == 'SETTLED'
    assert result['tail_endpoint_reason_pre'] == 'end_silence'
    assert result['tail_endpoint_reason'] == 'end_silence'
    assert result['tail_latency_seconds'] is not None
    assert result['first_cover_latency_seconds'] is not None
    assert result['identity_telemetry_missing'] is False
    assert result['silence_frames_streamed'] >= 1
    assert result['pre_snapshot_status'] == 'active'
    assert result['stop_requested_before_pre'] is False
    assert result['status'] == 'completed'
    assert result['finalization_status'] == 'final'
    assert demo.accepted_case(result) is True


def test_no_silence_control_preserves_pre_and_post_tail_reasons(monkeypatch):
    monkeypatch.setattr(demo, 'score_lanes', _passing_score)
    result=demo.run_case('https://unused',None,'alternation',client=_D31Client(pre_tail=False),realtime=False,
                         _stream_tail_silence=False)

    assert result['passed'] is False
    assert result['settle'] == 'TIMEOUT'
    assert result['tail_endpoint_reason_pre'] == 'none'
    assert result['tail_endpoint_reason'] == 'stop_flush'
    assert result['tail_latency_seconds'] is None
    assert result['silence_frames_streamed'] == 0


def test_post_stop_flush_rejects_an_otherwise_settled_tail(monkeypatch):
    monkeypatch.setattr(demo, 'score_lanes', _passing_score)
    result=demo.run_case('https://unused',None,'overlap',client=_D31Client(
        pre_tail=True,post_endpoint_reason='stop_flush'),realtime=False)

    assert result['tail_endpoint_reason_pre'] == 'end_silence'
    assert result['tail_endpoint_reason'] == 'stop_flush'
    assert result['passed'] is False


def test_empty_post_stop_evidence_rejects_an_otherwise_settled_tail(monkeypatch):
    monkeypatch.setattr(demo, 'score_lanes', _passing_score)
    result=demo.run_case('https://unused',None,'overlap',client=_D31Client(
        pre_tail=True,empty_post_events=True),realtime=False)

    assert result['settle'] == 'SETTLED'
    assert result['tail_endpoint_reason_pre'] == 'end_silence'
    assert result['tail_endpoint_reason'] == 'none'
    assert result['passed'] is False
    assert demo.accepted_case(result) is False


def test_hard_cap_does_not_satisfy_the_d31_end_silence_boundary(monkeypatch):
    monkeypatch.setattr(demo, 'score_lanes', _passing_score)
    result=demo.run_case('https://unused',None,'overlap',client=_D31Client(pre_tail=True,endpoint_reason='hard_cap'),
                         realtime=False)

    assert result['tail_endpoint_reason_pre'] == 'hard_cap'
    assert result['passed'] is False


def test_snapshot_at_or_after_deadline_cannot_accept_settled_facts(monkeypatch):
    monkeypatch.setattr(demo, 'score_lanes', _passing_score)
    clock=_Clock()
    result=demo.run_case('https://unused',None,'overlap',client=_D31Client(
        pre_tail=True,snapshot_times=(5.001,),clock=clock),realtime=False,_clock=clock)

    assert result['settle'] == 'TIMEOUT'
    assert result['passed'] is False
    assert result['first_cover_latency_seconds'] == 5.001
    assert result['tail_latency_seconds'] is None


def test_first_cover_latency_precedes_settled_tail_latency(monkeypatch):
    monkeypatch.setattr(demo, 'score_lanes', _passing_score)
    clock=_Clock()
    result=demo.run_case('https://unused',None,'overlap',client=_D31Client(
        pre_tail=True,snapshot_times=(1.0,2.0),clock=clock,extra_pending_until=2),realtime=False,_clock=clock)

    assert result['settle'] == 'SETTLED'
    assert result['first_cover_latency_seconds'] == 1.0
    assert result['tail_latency_seconds'] == 2.0


def _one_frame_inputs(_gain):
    return {
        'system': {'pcm': b'\1\0'*8000, 'reference': 'alpha'},
        'microphone': {'pcm': b'\1\0'*8000, 'reference': 'beta'},
    }


def test_partition_coverage_settles_when_word_timing_ends_before_last_pcm_sample(monkeypatch):
    monkeypatch.setattr(demo, 'score_lanes', _passing_score)
    monkeypatch.setattr(demo, 'reference_inputs', _one_frame_inputs)
    # The decoder words end 700 samples before the final captured non-zero sample.
    client=_D31Client(pre_tail=True,tail_span_end=8000,segments=[
        {'start_sample': 0, 'end_sample': 7300, 'source_lane': 'microphone'}])
    result=demo.run_case('https://unused',None,'overlap',client=client,realtime=False)

    assert result['settle'] == 'SETTLED'
    assert result['first_cover_latency_seconds'] is not None
    assert result['tail_words_present'] is True
    assert result['passed'] is True

    # RED under the replaced predicate: no effective segment reaches sample 8000.
    legacy_exact_cover=any(
        int(segment.get('start_sample',8000)) < 8000 <= int(segment.get('end_sample',0))
        for segment in client.segments)
    assert legacy_exact_cover is False
    assert ('SETTLED' if legacy_exact_cover else 'TIMEOUT') == 'TIMEOUT'


def test_committed_wordless_tail_partition_is_covered(monkeypatch):
    monkeypatch.setattr(demo, 'score_lanes', _passing_score)
    monkeypatch.setattr(demo, 'reference_inputs', _one_frame_inputs)
    result=demo.run_case('https://unused',None,'overlap',client=_D31Client(
        pre_tail=True,tail_span_end=8000,segments=[]),realtime=False)

    assert result['settle'] == 'SETTLED'
    assert result['first_cover_latency_seconds'] is not None
    assert result['tail_words_present'] is False


def test_missing_identity_telemetry_fails_closed(monkeypatch):
    def old_score(*args, **kwargs):
        return {'passed': True, 'lanes': {'system': {'wer': 0.0}, 'microphone': {'wer': 0.0}}}
    monkeypatch.setattr(demo, 'score_lanes', old_score)
    result=demo.run_case('https://unused',None,'overlap',client=_D31Client(pre_tail=True),realtime=False)

    assert all(score['passed'] is True for score in result['surfaces'].values())
    assert all('identity_unqualified' not in score for score in result['surfaces'].values())
    assert result['identity_telemetry_missing'] is True
    assert result['passed'] is False
    assert demo.accepted_case(result) is False


def _merged_score_lanes():
    source=subprocess.check_output(
        ['git','show','fd825ee7:moss_transcribe_diarize/lane_word_oracle.py'],cwd=demo.REPO,text=True)
    namespace={'__name__':'fetched_round5_scorer'}
    exec(compile(source,'fd825ee7:moss_transcribe_diarize/lane_word_oracle.py','exec'),namespace)
    return namespace['score_lanes']


def _two_lane_inputs(_gain):
    return {
        'system': {'pcm': b'\1\0'*8000, 'reference': 'alpha beta'},
        'microphone': {'pcm': b'\1\0'*8000, 'reference': 'gamma delta'},
    }


def test_fetched_merged_scorer_accepts_named_but_rejects_all_anonymous(monkeypatch):
    monkeypatch.setattr(demo, 'score_lanes', _merged_score_lanes())
    monkeypatch.setattr(demo, 'reference_inputs', _two_lane_inputs)
    named=[
        {'start_sample': 0, 'end_sample': 10_000_000, 'source_lane': 'system',
         'canonical_speaker': 'system-speaker', 'text': 'alpha beta'},
        {'start_sample': 0, 'end_sample': 10_000_000, 'source_lane': 'microphone',
         'canonical_speaker': 'microphone-speaker', 'text': 'gamma delta'},
    ]
    anonymous=[{**segment, 'canonical_speaker': ''} for segment in named]
    named_result=demo.run_case('https://unused',None,'overlap',client=_D31Client(
        pre_tail=True,segments=named),realtime=False)
    anonymous_result=demo.run_case('https://unused',None,'overlap',client=_D31Client(
        pre_tail=True,segments=anonymous),realtime=False)

    assert named_result['identity_telemetry_missing'] is False
    assert named_result['passed'] is True
    assert demo.accepted_case(named_result) is True
    assert all(score['passed'] is True for score in anonymous_result['surfaces'].values())
    assert all(score['identity_unqualified'] is True for score in anonymous_result['surfaces'].values())
    assert anonymous_result['passed'] is False
    assert demo.accepted_case(anonymous_result) is False


def test_d31_row_fields_and_surface_identity_telemetry_survive_retained_metadata():
    row={
        'tail_latency_seconds': 2.0,
        'first_cover_latency_seconds': 1.0,
        'tail_endpoint_reason_pre': 'end_silence',
        'tail_endpoint_reason': 'end_silence',
        'settle': 'SETTLED',
        'silence_frames_streamed': 2,
        'pre_snapshot_status': 'active',
        'stop_requested_before_pre': False,
        'identity_telemetry_missing': False,
        'tail_words_present': True,
        'surfaces': {'pre_terminal': {'identity_unqualified': False,
                                      'unattributed_segment_count': 0,
                                      'unattributed_word_count': 0}},
    }

    assert retained_metadata(row) == row
