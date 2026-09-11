"""Reader-only draft lifecycle. No browser, provider, or identity model required."""
import asyncio
import dataclasses
import threading
import time

import pytest

from tests.test_live_service_runtime import (
    _descriptor, _frame, RecordingDecoder, PreparingIdentity, ScriptedSpeechProvider,
)
from moss_transcribe_diarize.app.live_endpoint import EndpointPolicy, EndpointPolicyConfig
from moss_transcribe_diarize.app.live_service_runtime import LiveServiceRuntime, _ManualCanonicalPumpScheduler
from moss_transcribe_diarize.live_replay import _write_evaluator
from tests.phase2.test_canonical_preview import read_snapshots


def runtime(decoder, *, enabled=True):
    scheduler = _ManualCanonicalPumpScheduler()
    result = LiveServiceRuntime(
        descriptor=_descriptor(),
        endpoint_policy_factory=lambda: EndpointPolicy(EndpointPolicyConfig(
            min_speech_samples=1, min_silence_samples=1, hard_cap_samples=4000)),
        speech_provider_factory=lambda: ScriptedSpeechProvider((True,) * 100),
        decoder_factory=RecordingDecoder, identity_preparer_factory=PreparingIdentity,
        draft_lane_seconds=.0625 if enabled else None,
        draft_decoder_factory=lambda: decoder,
        _canonical_scheduler=scheduler,
    )
    return result, scheduler, result.create().session_id


class HeldDraft(RecordingDecoder):
    def __init__(self):
        super().__init__()
        self.entered, self.release = threading.Event(), threading.Event()

    def transcribe_pcm(self, **kwargs):
        self.entered.set()
        assert self.release.wait(5)
        return super().transcribe_pcm(**kwargs)


def finished(r):
    deadline = time.monotonic() + 5
    while r._draft_in_flight and time.monotonic() < deadline:
        time.sleep(.001)
    assert not r._draft_in_flight


def test_default_off_does_no_draft_work():
    decoder = RecordingDecoder()
    r, _, sid = runtime(decoder, enabled=False)
    r.accept_frame(sid, _frame(0))
    assert decoder.calls == []
    assert 'draft' not in r.snapshot(sid).to_dict()


def test_draft_is_unlabelled_and_outside_every_quality_capture(tmp_path):
    decoder = HeldDraft()
    r, _, sid = runtime(decoder)
    before = r.accept_frame(sid, _frame(0)).snapshot
    assert decoder.entered.wait(2)
    decoder.release.set(); finished(r)
    after = r.snapshot(sid, since_version=before.session.version)
    assert after.draft.authority == 'draft'
    assert '[S00]' in after.draft.transcript
    assert dataclasses.asdict(before.session) == dataclasses.asdict(after.session)
    assert after.session.identity_snapshot.version == 0
    from moss_transcribe_diarize.live_speaker_accuracy import hypothesis_from_live_snapshot
    for surface in ('pre_stop_immediate', 'pre_stop_settled', 'post_stop_final'):
        assert hypothesis_from_live_snapshot({'snapshot': before.to_dict()}, corpus_start_sample=0,
            corpus_duration_sec=.0625) == hypothesis_from_live_snapshot(
                {'snapshot': after.to_dict()}, corpus_start_sample=0, corpus_duration_sec=.0625) == ()
    # The exact evaluator used by immediate, settled and final captures only sees LiveSnapshot.
    _write_evaluator(tmp_path / 'before', before.session)
    _write_evaluator(tmp_path / 'after', after.session)
    assert (tmp_path / 'before').read_bytes() == (tmp_path / 'after').read_bytes() == b''
    assert 'decoded' not in str([event.to_dict() for event in r.events(sid)])
    rows = read_snapshots([{'snapshot': after.to_dict()}])
    assert len(rows[0]) == 1 and rows[0][0]['state'] == 'provisional'
    assert rows[0][0].get('speaker_entity_id') == 'S00'


@pytest.mark.parametrize('ending', ['commit', 'preview', 'abort', 'stop'])
def test_late_draft_fenced(ending):
    decoder = HeldDraft()
    r, scheduler, sid = runtime(decoder)
    r.accept_frame(sid, _frame(0)); assert decoder.entered.wait(2)
    try:
        if ending == 'abort':
            asyncio.run(r.abort(sid, reason='test abort'))
        elif ending == 'stop':
            async def stop():
                task = asyncio.create_task(r.stop(sid, deadline=2))
                await asyncio.sleep(.01)
                scheduler.run_one()
                return await task
            asyncio.run(stop())
        else:
            for seq in range(1, 4):
                r.accept_frame(sid, _frame(seq))
            if ending == 'commit':
                scheduler.run_one()
            else:
                state = r._sessions[sid]
                from moss_transcribe_diarize.app.live_session import FrozenSpan
                span_id = state.session.snapshot().pending_span_ids[0]
                r._publish_canonical_preview(state, FrozenSpan(span_id, state.session.epoch, 0, 4000, 'hard_cap'),
                                             '[0][S01]canonical[0.25]')
                assert state.session.snapshot().provisional is not None
    finally:
        decoder.release.set(); finished(r)
    assert r.snapshot(sid).draft is None
    assert not any(e.kind == 'draft_published' for e in r.events(sid))


def test_busy_ticks_skip_and_canonical_does_not_wait_for_draft():
    decoder = HeldDraft()
    r, scheduler, sid = runtime(decoder)
    r.accept_frame(sid, _frame(0)); assert decoder.entered.wait(2)
    try:
        for seq in range(1, 4): r.accept_frame(sid, _frame(seq))
        assert scheduler.run_one()
        assert r.snapshot(sid).session.committed_samples == 4000
        assert not decoder.release.is_set()
        stats = r.snapshot(sid).draft_stats
        assert stats['ticks'] == 4 and stats['started'] == 1 and stats['skipped'] == 3
    finally:
        decoder.release.set(); finished(r)


def test_draft_failure_does_not_fail_session():
    class Broken:
        def transcribe_pcm(self, **kwargs): raise RuntimeError('private provider content')
    r, _, sid = runtime(Broken())
    r.accept_frame(sid, _frame(0)); finished(r)
    snapshot = r.snapshot(sid)
    assert snapshot.session.status == 'active' and snapshot.terminal_failure is None
    assert snapshot.draft_stats['errors'] == 1
    assert 'private provider content' not in str(snapshot.to_dict())


@pytest.mark.parametrize('replacement', ['preview', 'multiple', 'empty', 'abort'])
def test_reader_retires_draft_by_audio_boundary(replacement):
    r, _, sid = runtime(RecordingDecoder())
    r.accept_frame(sid, _frame(0)); finished(r)
    first = r.snapshot(sid).to_dict()
    import copy
    second = copy.deepcopy(first)
    # Even a stale transport draft cannot survive the reader's canonical boundary.
    if replacement == 'preview':
        second['session']['provisional'] = dict(generation=1, start_sample=0,
                                               end_sample=1000, transcript='[0][S00]confirmed preview[0.0625]')
    elif replacement == 'abort':
        second['session']['status'] = 'aborted'
    else:
        second['session']['committed_samples'] = 1000
        second['session']['committed'] = [dict(span_id=0, start_sample=0, end_sample=1000,
            transcript='[0][S00]one[0.03][0.03][S00]two[0.0625]' if replacement == 'multiple' else '',
            revised_transcript=None)]
    rows = read_snapshots([{'snapshot': first}, {'snapshot': second}])
    assert len(rows[0]) == 1
    assert len(rows[1]) == {'preview': 1, 'multiple': 2, 'empty': 0, 'abort': 0}[replacement]
    assert not any(str(row['segment_id']).startswith('draft:') for row in rows[1])


def test_account_projection_does_not_suppress_draft_at_same_canonical_version():
    from types import SimpleNamespace
    from moss_transcribe_diarize.app.phase2_live import Phase2LiveMeetings
    r, _, sid = runtime(RecordingDecoder())
    r.accept_frame(sid, _frame(0)); finished(r)
    snapshot = r.snapshot(sid)
    binding = SimpleNamespace(public_snapshot=snapshot, capture_fenced=False)
    assert Phase2LiveMeetings.snapshot(None, binding, since_version=snapshot.session.version) is snapshot
