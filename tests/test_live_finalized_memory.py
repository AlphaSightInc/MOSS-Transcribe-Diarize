"""WP30: lane identity evidence lives through the last reader, then is released."""
import asyncio
from dataclasses import replace
import tempfile
from types import SimpleNamespace
import weakref

import pytest

from moss_transcribe_diarize.app.live_endpoint import EndpointPolicy, EndpointPolicyConfig
from moss_transcribe_diarize.app.live_identity import BoundedCausalIdentityPreparer, LiveIdentityConfig
from moss_transcribe_diarize.app.live_identity_album import FingerprintAlbum
from moss_transcribe_diarize.app.live_provider_bundle import WeSpeakerLiveEvidenceProvider
from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceRuntime, _ManualCanonicalPumpScheduler, _ManualTerminalScheduler,
)
from moss_transcribe_diarize.app.live_transcript_convergence import TerminalTranscriptFinalizer
from tests.test_live_lane_decode import Speech, Decoder, frame
from tests.test_live_service_runtime import _descriptor
from tests.test_live_terminal_finalizer import WholeMeetingStub


@pytest.mark.parametrize('ending', ['final', 'failed', 'not_started'])
def test_final_lane_owners_released_without_losing_observations(ending):
    class Encoder:
        spec = SimpleNamespace(provider='wespeaker', revision='test', state_sha256='test')
        def embed(self, path, intervals):
            return [1.0, 0.0]

    def identity():
        return BoundedCausalIdentityPreparer(
            config=LiveIdentityConfig(16, .35, .1),
            evidence_provider=WeSpeakerLiveEvidenceProvider(
                encoder=Encoder(), album=FingerprintAlbum(admission_seconds=2.0),
                birth_min_seconds=1.0,
            ), lane_factory=identity,
        )

    pump, terminal = _ManualCanonicalPumpScheduler(), _ManualTerminalScheduler()
    descriptor = _descriptor()
    descriptor = replace(descriptor, frame_samples=40000, bounds=replace(
        descriptor.bounds, max_frame_samples=40000, max_retained_samples=160000,
        hard_cap_samples=40000, max_queue_depth=16, max_tape_bytes=320000,
    ))
    runner = WholeMeetingStub('[0][S01]terminal words[2.5]',
                              raises=RuntimeError('injected') if ending == 'failed' else None)
    storage_owner = tempfile.TemporaryDirectory()
    runtime = LiveServiceRuntime(
        descriptor=descriptor,
        endpoint_policy_factory=lambda: EndpointPolicy(EndpointPolicyConfig(
            min_speech_samples=1, min_silence_samples=1, hard_cap_samples=40000)),
        speech_provider_factory=Speech, decoder_factory=Decoder,
        rolling_decoder_factory=Decoder, identity_preparer_factory=identity,
        terminal_finalizer=None if ending == 'not_started' else TerminalTranscriptFinalizer(runner=runner),
        _canonical_scheduler=pump, _terminal_scheduler=terminal,
        tape_storage_root=storage_owner.name,
    )
    runtime._test_tape_storage_owner = storage_owner
    sid = runtime.create().session_id
    runtime.accept_frame(sid, frame())
    pump.drain()
    coordinator = runtime._sessions[sid].coordinator
    owners = [weakref.ref(p) for p in coordinator._lane_preparers.values()]
    journal = coordinator.journal_observations()
    counts = coordinator.identity_counts()
    assert len(owners) == len(journal) == 2
    asyncio.run(runtime.stop(sid, 5))
    matches = coordinator.match_observations()
    if ending != 'not_started':
        assert terminal.pending == 1
        assert all(ref() is not None for ref in owners)
        assert runtime.snapshot(sid).session.finalization_status == 'running'
        terminal.drain()
    assert all(ref() is None for ref in owners)
    assert runtime.snapshot(sid).session.finalization_status == ending
    assert coordinator.journal_observations() == journal
    assert coordinator.match_observations() == matches
    assert coordinator.identity_counts() == counts
    assert {s.source_lane for s in runtime.snapshot(sid).session.effective_transcript} == {'system', 'microphone'}
    asyncio.run(runtime.stop(sid, 5))
    assert coordinator.journal_observations() == journal
