from __future__ import annotations

from dataclasses import dataclass

import pytest

from moss_transcribe_diarize.app.live_adapters import InferenceTranscript
from moss_transcribe_diarize.app.live_arbiter import InferenceArbiter, InferenceArbiterBackpressure
from moss_transcribe_diarize.app.live_coordinator import (
    IDENTITY_FINALIZE_FAILED,
    CoordinatorFinalizeResult,
    LiveCoordinator,
)
from moss_transcribe_diarize.app.live_endpoint import EndpointPolicy, EndpointPolicyConfig, SpeechObservation
from moss_transcribe_diarize.app.live_session import (
    AudioFrame,
    FrozenSpan,
    LIVE_SAMPLE_RATE,
    LiveIdentityPreparation,
    LiveIdentitySnapshot,
    LiveSession,
)


def pcm(samples: int, byte: bytes = b"\0") -> bytes:
    return byte * samples * 2


def frame(sequence: int, samples: int, byte: bytes = b"\0") -> AudioFrame:
    return AudioFrame(sequence=sequence, pcm=pcm(samples, byte), sample_count=samples)


class WholeFrameSpeech:
    def __init__(self, speech: tuple[bool, ...]):
        self._speech = list(speech)

    def observe(self, *, frame: AudioFrame, start_sample: int, end_sample: int) -> tuple[SpeechObservation, ...]:
        del frame
        return (
            SpeechObservation(
                start_sample=start_sample,
                end_sample=end_sample,
                speech_present=self._speech.pop(0),
            ),
        )


class RecordingDecoder:
    max_samples = LIVE_SAMPLE_RATE

    def __init__(self, transcript: str = "[0][S01]decoded[0.0625]", elapsed_sec: float | None = None):
        self.transcript = transcript
        self.elapsed_sec = elapsed_sec
        self.calls: list[tuple[tuple[int, int], int, bytes]] = []

    def preflight(self):
        raise AssertionError("coordinator tests do not use adapter admission")

    def transcribe_pcm(self, *, span: FrozenSpan, pcm: bytes) -> InferenceTranscript:
        self.calls.append(((span.start_sample, span.end_sample), len(pcm), pcm[:2]))
        return InferenceTranscript(self.transcript, elapsed_sec=self.elapsed_sec)


@dataclass
class PreparingIdentity:
    status: str = "prepared"
    reason: str | None = None

    def prepare(
        self,
        *,
        span: FrozenSpan,
        pcm: bytes,
        transcript: str,
        base_snapshot: LiveIdentitySnapshot,
    ) -> LiveIdentityPreparation:
        del pcm, transcript
        proposed = LiveIdentitySnapshot(
            version=base_snapshot.version + 1,
            canonical_speakers=("speaker-a",),
            diagnostics=(("span_id", str(span.id)),),
        )
        text = f"[0][S01]stable[{span.sample_count / LIVE_SAMPLE_RATE:g}]"
        return LiveIdentityPreparation(
            span_id=span.id,
            epoch=span.epoch,
            start_sample=span.start_sample,
            end_sample=span.end_sample,
            base_snapshot_version=base_snapshot.version,
            proposed_snapshot=proposed,
            relabeled_transcript=text,
            status=self.status,
            reason=self.reason,
        )


def coordinator(
    *,
    speech: tuple[bool, ...],
    session: LiveSession | None = None,
    arbiter: InferenceArbiter | None = None,
    decoder: RecordingDecoder | None = None,
    identity: PreparingIdentity | None = None,
) -> tuple[LiveCoordinator, RecordingDecoder, InferenceArbiter, LiveSession]:
    live_session = session or LiveSession(max_retained_samples=8000)
    live_arbiter = arbiter or InferenceArbiter()
    live_decoder = decoder or RecordingDecoder()
    return (
        LiveCoordinator(
            session_key="session-a",
            session=live_session,
            endpoint_policy=EndpointPolicy(
                EndpointPolicyConfig(
                    min_speech_samples=1,
                    min_silence_samples=1,
                    hard_cap_samples=4000,
                )
            ),
            speech_provider=WholeFrameSpeech(speech),
            decoder=live_decoder,
            identity_preparer=identity or PreparingIdentity(),
            arbiter=live_arbiter,
        ),
        live_decoder,
        live_arbiter,
        live_session,
    )


def test_coordinator_endpoint_queues_and_atomically_commits_frozen_pcm():
    live, decoder, arbiter, session = coordinator(speech=(True, False))

    first = live.accept_frame(frame(0, 1000, b"a"))
    second = live.accept_frame(frame(1, 1000, b"b"))

    assert first.queued_item_ids == ()
    assert [(span.start_sample, span.end_sample, span.reason) for span in second.endpoint_spans] == [
        (0, 1000, "end_silence")
    ]
    assert second.queued_item_ids == (0,)

    item = arbiter.next_work()
    result = live.process_work_item(item)

    snapshot = session.snapshot()
    assert result.submitted is True
    assert snapshot.accounted_samples == 1000
    assert snapshot.identity_snapshot.version == 1
    assert snapshot.committed[0].transcript == "[0][S01]stable[0.0625]"
    assert decoder.calls == [((0, 1000), 2000, b"aa")]


def test_coordinator_prepares_against_captured_identity_snapshot():
    class RecordingIdentity(PreparingIdentity):
        def __init__(self) -> None:
            super().__init__()
            self.base_versions: list[int] = []

        def prepare(self, **kwargs):
            self.base_versions.append(kwargs["base_snapshot"].version)
            return super().prepare(**kwargs)

    identity = RecordingIdentity()
    live, _decoder, arbiter, session = coordinator(speech=(True, False), identity=identity)
    live.accept_frame(frame(0, 1000, b"a"))
    live.accept_frame(frame(1, 1000, b"b"))
    work = live.capture_work_item(arbiter.next_work())

    session._identity_snapshot = LiveIdentitySnapshot(
        version=7,
        canonical_speakers=("speaker-newer",),
        diagnostics=(("test", "newer"),),
    )
    prepared = live.prepare_work_item(work)

    assert work.base_snapshot.version == 0
    assert identity.base_versions == [0]
    assert prepared.preparation.base_snapshot_version == 0
    assert session.snapshot().identity_snapshot.version == 7


def test_coordinator_prepared_work_preserves_decoder_elapsed_sec():
    live, _decoder, arbiter, _session = coordinator(
        speech=(True, False),
        decoder=RecordingDecoder(elapsed_sec=123.0),
    )
    live.accept_frame(frame(0, 1000, b"a"))
    live.accept_frame(frame(1, 1000, b"b"))

    prepared = live.prepare_work_item(live.capture_work_item(arbiter.next_work()))

    assert prepared.decode_elapsed_sec == 123.0
    result = live.submit_prepared_work(prepared)
    assert result.canonical_decode_elapsed_sec == 123.0
    assert result.frozen_span_sample_count == 1000
    assert result.frozen_span_duration_sec == 1000 / LIVE_SAMPLE_RATE
    assert result.canonical_decode_rtf == pytest.approx(123.0 / (1000 / LIVE_SAMPLE_RATE))


def test_coordinator_backpressure_leaves_frozen_span_uncommitted_not_dropped():
    live, decoder, _arbiter, session = coordinator(
        speech=(True, False),
        arbiter=InferenceArbiter(max_live_canonical_items=0),
    )

    live.accept_frame(frame(0, 1000))
    with pytest.raises(InferenceArbiterBackpressure, match="live canonical queue is full"):
        live.accept_frame(frame(1, 1000))

    snapshot = session.snapshot()
    assert snapshot.accepted_samples == 2000
    assert snapshot.accounted_samples == 0
    assert snapshot.pending_span_ids == (0,)
    assert decoder.calls == []


def test_coordinator_identity_abstention_publishes_the_span_without_a_speaker():
    """An abstention withholds the label, not the audio.

    It is the *designed* answer to ambiguous identity or exhausted speaker capacity, so it
    cannot also mean "end the meeting". The span commits, the identity snapshot does not
    move -- no speaker is born and the next span still prepares against this state -- and
    the words carry the unattributed marker rather than the decoder's local `S01`.
    """
    live, decoder, arbiter, session = coordinator(
        speech=(True, False),
        identity=PreparingIdentity(status="abstain", reason="ambiguous identity"),
    )
    live.accept_frame(frame(0, 1000))
    live.accept_frame(frame(1, 1000))
    before = session.snapshot()

    result = live.process_work_item(arbiter.next_work())

    assert result.submitted is True
    assert result.identity_status == "abstain"
    snapshot = session.snapshot()
    assert snapshot.status == "active"
    assert snapshot.committed_samples == 1000
    assert snapshot.accounted_samples == snapshot.committed_samples
    assert snapshot.identity_snapshot == before.identity_snapshot
    assert snapshot.committed[-1].transcript == "[0][S00]decoded[0.0625]"
    assert decoder.transcript == "[0][S01]decoded[0.0625]"


# --------------------------------------------------------------------------------------
# ADR-0002's final sweep, from the coordinator's side. The identity stack's half is
# measured in `test_live_provider_bundle` and the whole of it in `test_live_pipeline_seams`;
# what these three nodes pin is the seam's *shape* -- which snapshot the stack is settled
# against, and the two ways a stack can decline to settle without ending a clean stop.
# --------------------------------------------------------------------------------------


@dataclass
class FinalizingIdentity(PreparingIdentity):
    """A stack that records what it was asked to settle against, or refuses to settle."""

    raises: bool = False

    def __post_init__(self) -> None:
        self.finalized: list[LiveIdentitySnapshot] = []

    def finalize_identity(self, *, base_snapshot: LiveIdentitySnapshot) -> None:
        self.finalized.append(base_snapshot)
        if self.raises:
            raise RuntimeError("the album could not be settled")


def test_a_session_end_finalize_settles_the_stack_against_the_meetings_final_snapshot():
    """The last span's own preparation is what the stack has to reconcile.

    A span's vectors acquire their canonical speaker when the *next* span's preparation
    arrives, so the meeting's last span is the one nothing follows. Handing the stack the
    session's snapshot as it stands at stop time is what closes that gap, and it is the
    snapshot rather than the preparation because the session is the thing that decided
    which preparation was published.
    """

    identity = FinalizingIdentity()
    live, _decoder, arbiter, session = coordinator(speech=(True, False), identity=identity)
    live.accept_frame(frame(0, 1000))
    live.accept_frame(frame(1, 1000))
    live.process_work_item(arbiter.next_work())

    result = live.finalize_identity()

    assert [dict(snapshot.diagnostics) for snapshot in identity.finalized] == [{"span_id": "0"}]
    assert identity.finalized[0] == session.snapshot().identity_snapshot
    # Nothing to correct, and the version is the session's own rather than a zero standing
    # in for it -- the same rule `_publish_identity_revision` follows on every span.
    assert result.identity_revision_spans == 0
    assert result.identity_revision_units == 0
    assert result.identity_revision_refusals == ()


def test_a_session_end_finalize_is_harmless_for_a_stack_that_cannot_sweep():
    """Every identity stack that predates ADR-0002 step 3, and every test double.

    The capability is asked for by name, so a stack without it is not an error condition:
    it has retained nothing and has nothing to say about a span it has already answered.
    """

    live, _decoder, arbiter, _session = coordinator(speech=(True, False))
    live.accept_frame(frame(0, 1000))
    live.accept_frame(frame(1, 1000))
    live.process_work_item(arbiter.next_work())

    result = live.finalize_identity()

    assert result == CoordinatorFinalizeResult()


def test_a_session_end_finalize_that_raises_is_named_rather_than_terminal():
    """A meeting that reached a clean stop has already succeeded.

    An identity layer that breaks on the way out costs the transcript its last correction
    and nothing else. It is counted by name because the alternative -- reporting zero
    corrections -- is indistinguishable from a meeting nobody needed to correct.
    """

    identity = FinalizingIdentity(raises=True)
    live, _decoder, arbiter, session = coordinator(speech=(True, False), identity=identity)
    live.accept_frame(frame(0, 1000))
    live.accept_frame(frame(1, 1000))
    live.process_work_item(arbiter.next_work())

    result = live.finalize_identity()

    assert result.identity_revision_refusals == ((IDENTITY_FINALIZE_FAILED, 1),)
    assert session.snapshot().status == "active"
