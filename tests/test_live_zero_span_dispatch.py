"""WP10: digital silence is decided at dispatch, and the decoder seams stay decoder seams.

WP3 established the fact this file protects -- a decoder asked for words about exact digital
zeros invents them, ~40 on one measured span -- and put the check inside
`RunnerBoundedWavInference.transcribe_pcm` and `TerminalTranscriptFinalizer.finalize`. Those
are the seams that report what a runner *said*: which empty cause it was, what the salvage
gate did, the duration-derived token cap it spent, the difference between a decoder that
failed and a span with nothing to say. A seam that answers before asking reports none of that,
so nineteen contracts went dark at once (`tests/test_live_pipeline_seams.py` and friends).

So the tests here are deliberately *not* written against a decode seam. Each one names the
place the decision now lives and the guarantee that place is responsible for:

* `live_silence.is_digital_silence` -- the predicate, and the only thing that is a threshold
  question; WP1's per-lane producer is expected to import this name.
* `bounded_live_inference` -- the one function every deployed lane builds its decoder through,
  so "no model request for zeros" is a property of the deployment, not of one class.
* `CompleteMixedTape.has_signal` -- established as audio arrives, so the meeting's last
  listener can refuse a silent meeting without rescanning it or mistaking a fixture for one.
"""

from __future__ import annotations

import unittest
import tempfile

from moss_transcribe_diarize.app.live_adapters import DigitalSilenceGuardedInference
from moss_transcribe_diarize.app.live_endpoint import EndpointPolicy, EndpointPolicyConfig
from moss_transcribe_diarize.app.live_provider_bundle import (
    LiveProviderBundleConfig,
    bounded_live_inference,
    build_live_runtime_factory,
)
from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceRuntime,
    _ManualCanonicalPumpScheduler,
)
from moss_transcribe_diarize.app.live_session import (
    AudioFrame,
    FrozenSpan,
    LIVE_SAMPLE_RATE,
    LiveIdentityPreparation,
    LiveIdentitySnapshot,
)
from moss_transcribe_diarize.app.live_silence import is_digital_silence
from moss_transcribe_diarize.app.live_tape import CompleteMixedTape, PCM16_BYTES_PER_SAMPLE
from moss_transcribe_diarize.app.live_transcript_convergence import (
    TerminalOutcome,
    TerminalTranscriptFinalizer,
)
from moss_transcribe_diarize.app.transcription_outcome import EmptyTranscriptCause

from moss_transcribe_diarize.app import live_provider_bundle
from tests.test_live_provider_bundle import (
    FakeRunner,
    _FakeVad,
    _FakeWeSpeakerAdapter,
    _manifest,
    _write_manifest,
    packaging,
)
from tests.test_live_service_runtime import ScriptedSpeechProvider, _descriptor
from tests.test_live_terminal_finalizer import plan_for, tape_of
from moss_transcribe_diarize.app.live_service_runtime import _ManualTerminalScheduler
from tests.test_live_terminal_lifecycle import (
    MEETING_SAMPLES,
    _finalizer,
    _payload,
    _runtime as _terminal_runtime,
    _stop_after_a_meeting,
)

FRAME_SAMPLES = 1000
HARD_CAP_SAMPLES = 4000


class MustNotDecode:
    """The forbidden event, made loud: `transcribe` IS the model request."""

    def __init__(self) -> None:
        self.requests: list[str] = []

    def transcribe(self, audio_path, **kwargs):
        self.requests.append(str(audio_path))
        raise AssertionError("a model request was made for digital silence")


class BirthRecordingIdentity:
    """Records every span it was offered evidence for. A birth begins with one of these."""

    def __init__(self) -> None:
        self.prepared: list[int] = []

    def prepare(self, *, span, pcm, transcript, base_snapshot):
        del pcm, transcript
        self.prepared.append(span.id)
        return LiveIdentityPreparation(
            span_id=span.id,
            epoch=span.epoch,
            start_sample=span.start_sample,
            end_sample=span.end_sample,
            base_snapshot_version=base_snapshot.version,
            proposed_snapshot=LiveIdentitySnapshot(
                version=base_snapshot.version + 1,
                canonical_speakers=base_snapshot.canonical_speakers or ("speaker-0001",),
            ),
            relabeled_transcript=f"[0][S01]stable[{span.sample_count / LIVE_SAMPLE_RATE:g}]",
            status="prepared",
        )


def _zero_frame(sequence: int, *, sample: bytes = b"\0\0") -> AudioFrame:
    return AudioFrame(
        sequence=sequence, pcm=sample * FRAME_SAMPLES, sample_count=FRAME_SAMPLES
    )


def _runtime(runner, identity):
    scheduler = _ManualCanonicalPumpScheduler()
    storage_owner = tempfile.TemporaryDirectory()
    runtime = LiveServiceRuntime(
        descriptor=_descriptor(),
        endpoint_policy_factory=lambda: EndpointPolicy(
            EndpointPolicyConfig(
                min_speech_samples=1, min_silence_samples=1, hard_cap_samples=HARD_CAP_SAMPLES
            )
        ),
        speech_provider_factory=lambda: ScriptedSpeechProvider((True,) * 64),
        decoder_factory=lambda: bounded_live_inference(runner, max_samples=HARD_CAP_SAMPLES),
        identity_preparer_factory=lambda: identity,
        _canonical_scheduler=scheduler,
        tape_storage_root=storage_owner.name,
    )
    runtime._test_tape_storage_owner = storage_owner
    return runtime, scheduler


class DigitalSilencePredicateTest(unittest.TestCase):
    """The only threshold question in WP10, and it is answered with `== 0`."""

    def test_exact_zeros_and_nothing_quieter_counts_as_silence(self):
        self.assertTrue(is_digital_silence(b"\0\0" * 8000))
        self.assertTrue(is_digital_silence(b""))
        self.assertTrue(is_digital_silence(memoryview(bytearray(16))))
        # One least-significant bit anywhere is quiet speech. WP3's bench falsified every
        # energy threshold above this on real quiet local speech, so the line is exactness.
        self.assertFalse(is_digital_silence(b"\0\0" * 3999 + b"\x01\0" + b"\0\0" * 4000))
        self.assertFalse(is_digital_silence(b"\xff\xff"))


class ZeroSpanDispatchTest(unittest.TestCase):
    def test_an_all_zero_span_makes_no_model_request_and_births_no_speaker(self):
        """The two harms in one meeting: invented words, and a speaker invented to own them.

        A span the identity stack never sees cannot contribute an exemplar, so no canonical
        speaker can be born from zeros -- which is why this asserts on the preparer's call log
        and not only on the snapshot: an album that admitted evidence and then abstained would
        satisfy the snapshot and still have heard silence.
        """

        runner, identity = MustNotDecode(), BirthRecordingIdentity()
        runtime, scheduler = _runtime(runner, identity)
        session_id = runtime.create().session_id
        for sequence in range(4):
            runtime.accept_frame(session_id, _zero_frame(sequence))
        scheduler.run_one()

        snapshot = runtime.snapshot(session_id).session
        processed = _payload(runtime, session_id, "canonical_processed")

        self.assertEqual(runner.requests, [])
        self.assertEqual(identity.prepared, [])
        self.assertEqual(snapshot.identity_snapshot.version, 0)
        self.assertEqual(snapshot.identity_snapshot.canonical_speakers, ())
        # The audio is still accounted for: the span commits, empty and named, and the
        # committed prefix advances over it. Silence that stalled the timeline would be a
        # worse bug than silence that hallucinated.
        self.assertEqual(snapshot.committed_samples, 4 * FRAME_SAMPLES)
        self.assertEqual([span.transcript for span in snapshot.committed], [""])
        self.assertEqual(processed["empty_reason"], "span_was_digital_silence")
        self.assertTrue(processed["submitted"])
        # No cap was spent, because nothing was asked. A reported cap here would put invented
        # numbers into the truncation and RTF accounting the live path is judged by.
        self.assertIsNone(processed["canonical_decode_token_cap"])
        self.assertEqual(processed["canonical_decode_generated_tokens"], 0)

    def test_one_nonzero_sample_in_the_span_still_reaches_the_model(self):
        """WP3's kept contract, asserted on the deployed decoder rather than on the seam."""

        runner = MustNotDecode()
        decoder = bounded_live_inference(runner, max_samples=HARD_CAP_SAMPLES)
        span = FrozenSpan(
            id=0, epoch=0, start_sample=0, end_sample=HARD_CAP_SAMPLES, reason="hard_cap"
        )
        pcm = b"\0\0" * 1999 + b"\x01\0" + b"\0\0" * 2000

        with self.assertRaises(Exception):
            decoder.transcribe_pcm(span=span, pcm=pcm)
        self.assertEqual(len(runner.requests), 1)

    def test_a_rolling_window_of_zeros_is_completed_without_a_model_request(self):
        """The witness must still be released, or rolling stops with no status saying so."""

        runner = MustNotDecode()
        decoder = bounded_live_inference(runner, max_samples=HARD_CAP_SAMPLES)
        span = FrozenSpan(
            id=7, epoch=0, start_sample=0, end_sample=HARD_CAP_SAMPLES, reason="rolling_window"
        )

        outcome = decoder.transcribe_pcm(span=span, pcm=b"\0\0" * HARD_CAP_SAMPLES)

        self.assertEqual(runner.requests, [])
        self.assertEqual(outcome.transcript, "")
        self.assertIs(outcome.empty_cause, EmptyTranscriptCause.DIGITAL_SILENCE)


class TerminalSurfaceTest(unittest.TestCase):
    def test_the_terminal_surface_still_reaches_final_with_its_accounting(self):
        """The contract WP3 broke from the other side: a meeting with audio still finalises."""

        scheduler = _ManualTerminalScheduler()
        runtime, _ = _terminal_runtime(finalizer=_finalizer(), scheduler=scheduler)
        session_id = _stop_after_a_meeting(runtime)
        self.assertTrue(scheduler.run_one())

        snapshot = runtime.snapshot(session_id).session
        completed = _payload(runtime, session_id, "terminal_finalization_completed")

        self.assertEqual(snapshot.finalization_status, "final")
        self.assertEqual(completed["finalization_status"], "final")
        self.assertTrue(completed["applied"])
        self.assertEqual(completed["outcome"], TerminalOutcome.FINALIZED.value)
        self.assertEqual(completed["tape_samples"], MEETING_SAMPLES)
        self.assertEqual(
            {segment.authority for segment in snapshot.effective_transcript}, {"terminal"}
        )

    def test_a_meeting_that_held_no_signal_is_refused_by_name_instead_of_decoded(self):
        """The worst place to hallucinate: this pass replaces the surface permanently."""

        runner = MustNotDecode()
        tape = tape_of(MEETING_SAMPLES, fill=b"\0\0")

        finalization = TerminalTranscriptFinalizer(runner=runner).finalize(
            plan=plan_for(MEETING_SAMPLES), tape=tape, base_text_revision_version=0
        )

        self.assertEqual(runner.requests, [])
        self.assertFalse(tape.has_signal)
        self.assertIsNone(finalization.proposal)
        self.assertEqual(finalization.accounting.outcome, TerminalOutcome.NO_TRANSCRIPT)
        self.assertEqual(finalization.accounting.reason, "digital_silence")
        # Refused, not lost: the accounting still says how much audio was there to refuse.
        self.assertEqual(finalization.accounting.tape_samples, MEETING_SAMPLES)

    def test_a_tape_that_ever_held_one_nonzero_sample_still_decodes(self):
        """`has_signal` is about the whole meeting, not about the last frame of it."""

        storage_owner = tempfile.TemporaryDirectory()
        tape = CompleteMixedTape(
            epoch=0,
            capacity_bytes=4 * FRAME_SAMPLES * PCM16_BYTES_PER_SAMPLE,
            storage_root=storage_owner.name,
        )
        tape._test_storage_owner = storage_owner
        tape.append(start_sample=0, pcm=b"\0\0" * FRAME_SAMPLES)
        self.assertFalse(tape.has_signal)
        tape.append(start_sample=FRAME_SAMPLES, pcm=b"\0\0" * (FRAME_SAMPLES - 1) + b"\x01\0")
        self.assertTrue(tape.has_signal)
        tape.append(start_sample=2 * FRAME_SAMPLES, pcm=b"\0\0" * FRAME_SAMPLES)
        self.assertTrue(tape.has_signal)

    def test_a_tape_that_explicitly_reports_signal_still_decodes(self):
        """The owned terminal-tape interface carries the arrival-time observation."""

        tape = tape_of(FRAME_SAMPLES, fill=b"\x01\0")
        runner = MustNotDecode()
        finalization = TerminalTranscriptFinalizer(runner=runner).finalize(
            plan=plan_for(FRAME_SAMPLES),
            tape=tape,
            base_text_revision_version=0,
        )

        # The runner was asked, which is the whole point; what it did with the question is the
        # ordinary decode-failure path and not this test's business.
        self.assertEqual(len(runner.requests), 1)
        self.assertEqual(finalization.accounting.outcome, TerminalOutcome.DECODE_FAILED)


def test_every_deployed_lane_is_built_through_the_guarded_dispatch(tmp_path, monkeypatch):
    """Not "the canonical decoder is guarded" -- "a deployed decoder is guarded".

    This is the assertion that fails if a fourth lane is added and wired straight to
    `RunnerBoundedWavInference`, which is now the only way the guarantee can be lost. It is a
    pytest function rather than a `TestCase` method because it needs the provider-bundle
    fixture's offline fakes, which are an autouse pytest fixture.
    """

    monkeypatch.setattr(packaging, "Vad", _FakeVad, raising=False)
    monkeypatch.setattr(
        live_provider_bundle, "WeSpeakerResNet152LmAdapter", _FakeWeSpeakerAdapter
    )
    config = LiveProviderBundleConfig.from_manifest(
        _write_manifest(tmp_path, _manifest(tmp_path))
    )

    runtime = build_live_runtime_factory(config, FakeRunner(), draft_lane_seconds=1.0)()

    for factory in (
        runtime._decoder_factory,
        runtime._rolling_decoder_factory,
        runtime._draft_decoder_factory,
    ):
        assert factory is not None
        assert isinstance(factory(), DigitalSilenceGuardedInference)


if __name__ == "__main__":
    unittest.main()
