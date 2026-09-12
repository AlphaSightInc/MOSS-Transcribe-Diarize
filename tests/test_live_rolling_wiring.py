"""Plan §10.5 step 4 -- the rolling witness inside the live runtime (test tier T2).

The three pieces E2 shipped before this were each provably correct on their own: the
converger reproduces the selected arm, the session validates every revision, and the arbiter
schedules a witness below the base path. What none of them could show is that the *runtime*
puts them together -- that a base commit reaches the converger, that the window it plans is
dispatched and released, that what comes back publishes, and that none of it can take down
the meeting the base path is already publishing.

These are the seams that only exist once the wiring does. The arm itself is measured
elsewhere, on real audio, against the grid: `verify_runtime_rolling.py`.

`RollingEventSerializationTest` is plan §10.5 step 5 -- the §7.4 events the runtime writes for
that wiring. It lives here because the events are the wiring's own report: what a window did is
knowable only where the window is dispatched. The corpus reading of the same events is
`verify_rolling_events.py`, and three of the branches below are branches sixty seconds of real
speech never takes -- a refused revision, a refused admission, a defect -- for the reasons
iteration 14 recorded about producer pacing.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import unittest
from dataclasses import dataclass, replace
from typing import Any

from moss_transcribe_diarize.app.live_adapters import (
    canonical_decode_token_cap,
    InferenceTranscript,
    LiveProviderError,
    LiveProviderTransientError,
    RunnerBoundedWavInference,
)
from moss_transcribe_diarize.app.live_arbiter import InferenceArbiter
from moss_transcribe_diarize.app.live_coordinator import (
    LiveCoordinator,
    ROLLING_DECODE_DID_NOT_ANSWER,
    ROLLING_DECODE_FAILED,
    ROLLING_WINDOW_REASON,
    RefinementWork,
    RollingWindowPlan,
)
from moss_transcribe_diarize.app.live_endpoint import EndpointPolicy, EndpointPolicyConfig
from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceBounds,
    LiveServiceConfigHashes,
    LiveServiceDescriptor,
    LiveServiceRuntime,
    _ManualCanonicalPumpScheduler,
)
from moss_transcribe_diarize.app.live_session import (
    AudioFrame,
    FrozenSpan,
    LIVE_SAMPLE_RATE,
    LiveIdentityPreparation,
    LiveIdentitySnapshot,
    LiveSession,
)
from moss_transcribe_diarize.app.live_span_bounds import HARD_CAP_REASON
from moss_transcribe_diarize.app.live_transcript_convergence import (
    DEFAULT_ROLLING_GEOMETRY,
    RollingStatus,
    RollingTranscriptConverger,
)
from moss_transcribe_diarize.app.transcription_outcome import (
    EmptyTranscriptCause,
    EmptyTranscriptionError,
)

FRAME_SAMPLES = 8000
HARD_CAP_SAMPLES = 40000
WINDOW_SAMPLES = DEFAULT_ROLLING_GEOMETRY.window_samples
DECODER_MAX_SAMPLES = 120000


class ScriptedSpeech:
    """Every accepted range is speech, so the endpoint freezes on the hard cap alone."""

    def observe(self, *, frame: AudioFrame, start_sample: int, end_sample: int):
        from moss_transcribe_diarize.app.live_endpoint import SpeechObservation

        del frame
        return (
            SpeechObservation(start_sample=start_sample, end_sample=end_sample, speech_present=True),
        )


class ScriptedIdentity:
    def prepare(self, *, span, pcm, transcript, base_snapshot):
        del pcm
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
            relabeled_transcript=transcript,
        )


@dataclass
class ScriptedDecoder:
    """One word per decode, naming the interval it came from, so ownership is readable.

    `max_samples` is the real bound the adapter enforces, and the two decoders differ in it:
    the base decoder cannot physically accept a ten-second window, which is why the wiring
    needs a second one at all.
    """

    max_samples: int
    label: str
    calls: list[tuple[int, int]]
    failure: Exception | None = None

    def preflight(self):
        from moss_transcribe_diarize.app.live_adapters import AdapterPreflight

        return AdapterPreflight(True)

    def transcribe_pcm(self, *, span: FrozenSpan, pcm: bytes) -> InferenceTranscript:
        if len(pcm) != span.sample_count * 2:
            raise AssertionError("decoder was handed PCM that does not match its span.")
        if span.sample_count > self.max_samples:
            raise LiveProviderError("span exceeds bounded inference capacity.")
        self.calls.append((span.start_sample, span.end_sample))
        if self.failure is not None:
            raise self.failure
        seconds = span.sample_count / LIVE_SAMPLE_RATE
        # The cap is reported the way the real adapter reports it, because plan §7.4 asks
        # every completion event for it and a double that omits it would let a production
        # omission pass.
        cap = canonical_decode_token_cap(sample_count=span.sample_count)
        return InferenceTranscript(
            transcript=f"[0.00][S01] {self.label} {span.start_sample}[{seconds:g}]",
            elapsed_sec=0.01,
            token_cap=cap,
            capped=False,
        )


def _endpoint_config() -> EndpointPolicyConfig:
    return EndpointPolicyConfig(
        min_speech_samples=1600,
        min_silence_samples=8000,
        pre_speech_padding_samples=1600,
        post_speech_padding_samples=1600,
        hard_cap_samples=HARD_CAP_SAMPLES,
    )


def _descriptor(*, max_events: int = 1000) -> LiveServiceDescriptor:
    return LiveServiceDescriptor(
        source_revision="0" * 40,
        provider_name="rolling-wiring",
        provider_revision="test",
        provider_manifest_hash=hashlib.sha256(b"rolling-wiring").hexdigest(),
        config_hashes=LiveServiceConfigHashes.from_parts(
            endpoint_config={"hard_cap_samples": HARD_CAP_SAMPLES},
            identity_config={"max_speakers": 16},
            decoder_config={"max_samples": DECODER_MAX_SAMPLES},
        ),
        bounds=LiveServiceBounds(
            max_frame_samples=LIVE_SAMPLE_RATE,
            max_queue_depth=16,
            max_retained_samples=960000,
            max_identity_speakers=16,
            max_events=max_events,
            hard_cap_samples=HARD_CAP_SAMPLES,
            stop_drain_deadline_seconds=5.0,
        ),
        frame_samples=FRAME_SAMPLES,
    )


def _runtime(
    *,
    base: ScriptedDecoder,
    rolling: ScriptedDecoder | None,
    max_events: int = 1000,
    scheduler: _ManualCanonicalPumpScheduler | None = None,
) -> LiveServiceRuntime:
    return LiveServiceRuntime(
        descriptor=_descriptor(max_events=max_events),
        endpoint_policy_factory=lambda: EndpointPolicy(_endpoint_config()),
        speech_provider_factory=ScriptedSpeech,
        decoder_factory=lambda: base,
        rolling_decoder_factory=None if rolling is None else (lambda: rolling),
        identity_preparer_factory=ScriptedIdentity,
        session_id_factory=lambda: "rolling-session",
        _canonical_scheduler=scheduler,
    )


def _decoders(*, rolling: bool, rolling_failure: Exception | None = None):
    base = ScriptedDecoder(max_samples=DECODER_MAX_SAMPLES, label="base", calls=[])
    witness = (
        ScriptedDecoder(
            max_samples=WINDOW_SAMPLES, label="rolling", calls=[], failure=rolling_failure
        )
        if rolling
        else None
    )
    return base, witness


def _run_meeting(runtime: LiveServiceRuntime, *, frames: int) -> str:
    created = runtime.create()
    for sequence in range(frames):
        runtime.accept_frame(
            created.session_id,
            AudioFrame(
                sequence=sequence,
                pcm=b"\x11\x22" * FRAME_SAMPLES,
                sample_count=FRAME_SAMPLES,
            ),
        )
    asyncio.run(runtime.stop(created.session_id, 5.0))
    return created.session_id


# Twenty frames is 160000 samples: four hard-cap spans, which is exactly one rolling window.
# Forty is two windows, which is what a test about the *second* window needs.
ONE_WINDOW_FRAMES = WINDOW_SAMPLES // FRAME_SAMPLES
TWO_WINDOW_FRAMES = 2 * ONE_WINDOW_FRAMES


class RollingRuntimeWiringTest(unittest.TestCase):
    def test_no_window_decoder_means_no_witness_and_no_change(self):
        """The pre-E2 service, unchanged: the collaborator is asked for, never assumed."""

        base, _ = _decoders(rolling=False)
        runtime = _runtime(base=base, rolling=None)
        session_id = _run_meeting(runtime, frames=ONE_WINDOW_FRAMES)

        coordinator = runtime._sessions[session_id].coordinator
        self.assertIsNone(coordinator.converger)
        self.assertIsNone(coordinator.rolling_accounting())
        snapshot = runtime.snapshot(session_id).session
        self.assertEqual(snapshot.text_revision_version, 0)
        self.assertEqual(snapshot.canonical_through_sample, 0)
        self.assertEqual(
            {segment.authority for segment in snapshot.effective_transcript}, {"provisional"}
        )

    def test_a_base_commit_reaches_the_converger_and_its_window_publishes(self):
        base, witness = _decoders(rolling=True)
        runtime = _runtime(base=base, rolling=witness)
        session_id = _run_meeting(runtime, frames=ONE_WINDOW_FRAMES)

        snapshot = runtime.snapshot(session_id).session
        self.assertIsNone(runtime.snapshot(session_id).terminal_failure)
        self.assertEqual(witness.calls, [(0, WINDOW_SAMPLES)])
        self.assertEqual(snapshot.text_revision_version, 1)
        self.assertEqual(snapshot.canonical_through_sample, WINDOW_SAMPLES)
        prefix = [
            segment
            for segment in snapshot.effective_transcript
            if segment.end_sample <= WINDOW_SAMPLES
        ]
        self.assertEqual([segment.authority for segment in prefix], ["rolling"])
        self.assertIn("rolling 0", prefix[0].text)

    def test_the_base_path_is_byte_identical_with_and_without_the_witness(self):
        """ADR-0005 D2: the committed history is what the short path published, always."""

        without_base, _ = _decoders(rolling=False)
        without = _runtime(base=without_base, rolling=None)
        without_id = _run_meeting(without, frames=ONE_WINDOW_FRAMES)

        with_base, witness = _decoders(rolling=True)
        with_rolling = _runtime(base=with_base, rolling=witness)
        with_id = _run_meeting(with_rolling, frames=ONE_WINDOW_FRAMES)

        def committed(runtime, session_id):
            snapshot = runtime.snapshot(session_id).session
            return (
                [(item.start_sample, item.end_sample, item.transcript) for item in snapshot.committed],
                snapshot.committed_prefix_hash,
            )

        self.assertEqual(committed(without, without_id), committed(with_rolling, with_id))
        self.assertEqual(without_base.calls, with_base.calls)

    def test_every_dispatched_witness_is_released(self):
        base, witness = _decoders(rolling=True)
        runtime = _runtime(base=base, rolling=witness)
        session_id = _run_meeting(runtime, frames=TWO_WINDOW_FRAMES)

        self.assertEqual(
            witness.calls, [(0, WINDOW_SAMPLES), (WINDOW_SAMPLES, 2 * WINDOW_SAMPLES)]
        )
        queues = runtime._sessions[session_id].arbiter.snapshot()
        self.assertEqual((queues.live_refinement, queues.live_refinement_running), (0, 0))
        self.assertEqual(runtime.snapshot(session_id).session.text_revision_version, 2)

    def test_stop_waits_for_the_window_that_is_already_decoding(self):
        """Without this the last correction of every meeting would be thrown away."""

        base, witness = _decoders(rolling=True)
        runtime = _runtime(base=base, rolling=witness)
        session_id = _run_meeting(runtime, frames=TWO_WINDOW_FRAMES)

        snapshot = runtime.snapshot(session_id).session
        self.assertEqual(snapshot.status, "closed")
        self.assertEqual(snapshot.canonical_through_sample, 2 * WINDOW_SAMPLES)
        self.assertEqual(snapshot.accepted_samples, snapshot.accounted_samples)

    def test_a_decoder_that_never_answers_stalls_rolling_and_not_the_meeting(self):
        base, witness = _decoders(
            rolling=True, rolling_failure=LiveProviderTransientError("witness timed out")
        )
        runtime = _runtime(base=base, rolling=witness)
        session_id = _run_meeting(runtime, frames=TWO_WINDOW_FRAMES)

        self.assertIsNone(runtime.snapshot(session_id).terminal_failure)
        snapshot = runtime.snapshot(session_id).session
        self.assertEqual(snapshot.status, "closed")
        self.assertEqual(snapshot.text_revision_version, 0)
        self.assertEqual(
            {segment.authority for segment in snapshot.effective_transcript}, {"provisional"}
        )
        # One failed window, and no second one: a stalled converger plans nothing further.
        self.assertEqual(witness.calls, [(0, WINDOW_SAMPLES)])

    def test_a_defect_in_the_witness_stops_rolling_instead_of_the_meeting(self):
        base, witness = _decoders(rolling=True)
        runtime = _runtime(base=base, rolling=witness)
        created = runtime.create()
        coordinator = runtime._sessions[created.session_id].coordinator

        def exploding_submit(decode, item):
            raise RuntimeError("a defect in the second listener")

        coordinator.submit_refinement = exploding_submit
        for sequence in range(TWO_WINDOW_FRAMES):
            runtime.accept_frame(
                created.session_id,
                AudioFrame(
                    sequence=sequence, pcm=b"\x11\x22" * FRAME_SAMPLES, sample_count=FRAME_SAMPLES
                ),
            )
        asyncio.run(runtime.stop(created.session_id, 5.0))

        self.assertIsNone(runtime.snapshot(created.session_id).terminal_failure)
        snapshot = runtime.snapshot(created.session_id).session
        self.assertEqual(snapshot.status, "closed")
        self.assertEqual(snapshot.text_revision_version, 0)
        self.assertEqual(coordinator.rolling_accounting().status, RollingStatus.STOPPED)
        self.assertEqual(witness.calls, [(0, WINDOW_SAMPLES)])

    def test_a_witness_admitted_before_the_stop_is_not_decoded_after_it(self):
        base, witness = _decoders(rolling=True)
        session = LiveSession(max_retained_samples=960000)
        arbiter = InferenceArbiter()
        coordinator = LiveCoordinator(
            session_key="closing",
            session=session,
            endpoint_policy=EndpointPolicy(_endpoint_config()),
            speech_provider=ScriptedSpeech(),
            decoder=base,
            identity_preparer=ScriptedIdentity(),
            arbiter=arbiter,
            rolling_decoder=witness,
        )
        request = coordinator.converger.accept_pcm(0, b"\0" * WINDOW_SAMPLES * 2)
        self.assertEqual(request, ())
        item = _refinement_item(coordinator, arbiter)

        self.assertIsNotNone(coordinator.capture_refinement_item(item))
        coordinator.stop_rolling()
        self.assertIsNone(coordinator.capture_refinement_item(item))
        self.assertEqual(witness.calls, [])

    def test_the_coalesce_key_names_the_session_not_only_its_epoch(self):
        """Two epoch-0 sessions on one arbiter must not coalesce into one witness."""

        arbiter = InferenceArbiter()
        coordinators = []
        for name in ("session-a", "session-b"):
            base, witness = _decoders(rolling=True)
            session = LiveSession(max_retained_samples=960000)
            coordinators.append(
                LiveCoordinator(
                    session_key=name,
                    session=session,
                    endpoint_policy=EndpointPolicy(_endpoint_config()),
                    speech_provider=ScriptedSpeech(),
                    decoder=base,
                    identity_preparer=ScriptedIdentity(),
                    arbiter=arbiter,
                    rolling_decoder=witness,
                )
            )
        for coordinator in coordinators:
            _refinement_item(coordinator, arbiter, dispatch=False)

        self.assertEqual(arbiter.snapshot().live_refinement, 2)
        keys = set()
        while True:
            item = arbiter.next_work()
            if item is None:
                break
            keys.add(item.key)
        self.assertEqual(keys, {"session-a:rolling:0", "session-b:rolling:0"})

    def test_a_rolling_window_is_never_offered_to_the_M1_salvage_gate(self):
        """Bounded salvage was measured on 2.5 s hard-cap spans, and stays there.

        The same unparseable answer is decoded twice through the production adapter: once as
        a hard-cap span, where M1 completes its absent closing bound and publishes it, and
        once as a rolling window, where the gate refuses it and the window fails.
        """

        raw = "[0.00][S01] the difference between, you said the stock market."

        class UnparseableRunner:
            def transcribe(self, audio_path, **kwargs):
                raise EmptyTranscriptionError(
                    "zero parsed segments",
                    cause=EmptyTranscriptCause.UNPARSEABLE_TEXT,
                    text=raw,
                    generated_tokens=17,
                )

        adapter = RunnerBoundedWavInference(UnparseableRunner(), max_samples=WINDOW_SAMPLES)
        salvaged = adapter.transcribe_pcm(
            span=FrozenSpan(
                id=1, epoch=0, start_sample=0, end_sample=HARD_CAP_SAMPLES, reason=HARD_CAP_REASON
            ),
            pcm=b"\0" * HARD_CAP_SAMPLES * 2,
        )
        refused = adapter.transcribe_pcm(
            span=FrozenSpan(
                id=2,
                epoch=0,
                start_sample=0,
                end_sample=WINDOW_SAMPLES,
                reason=ROLLING_WINDOW_REASON,
            ),
            pcm=b"\0" * WINDOW_SAMPLES * 2,
        )

        self.assertIn("stock market", salvaged.transcript)
        self.assertEqual(refused.transcript, "")

    def test_a_failed_window_is_named_rather_than_silent(self):
        base, witness = _decoders(rolling=True)
        session = LiveSession(max_retained_samples=960000)
        arbiter = InferenceArbiter()
        coordinator = LiveCoordinator(
            session_key="named",
            session=session,
            endpoint_policy=EndpointPolicy(_endpoint_config()),
            speech_provider=ScriptedSpeech(),
            decoder=base,
            identity_preparer=ScriptedIdentity(),
            arbiter=arbiter,
            rolling_decoder=witness,
        )
        coordinator.converger.accept_pcm(0, b"\0" * WINDOW_SAMPLES * 2)
        item = _refinement_item(coordinator, arbiter)
        request = coordinator.capture_refinement_item(item)

        witness.failure = LiveProviderTransientError("no answer")
        did_not_answer = coordinator.decode_refinement(request)
        self.assertEqual(did_not_answer.failure, ROLLING_DECODE_DID_NOT_ANSWER)
        witness.failure = LiveProviderError("refused")
        failed = coordinator.decode_refinement(request)
        self.assertEqual(failed.failure, ROLLING_DECODE_FAILED)

        result = coordinator.submit_refinement(failed, item)
        self.assertFalse(result.applied)
        self.assertEqual(result.rolling_status, RollingStatus.WINDOW_FAILED.value)
        self.assertEqual(result.windows_failed, 1)
        # The submission already released it; a second release is a no-op, not a fault.
        self.assertFalse(coordinator.release_refinement(item))


class RollingEventSerializationTest(unittest.TestCase):
    """Plan §7.4: what a window did reaches a reader outside the process, in counts and names."""

    def _events(self, runtime: LiveServiceRuntime, session_id: str, kind: str) -> list[dict[str, Any]]:
        return [
            event.to_dict()["payload"]
            for event in runtime.events(session_id)
            if event.kind == kind
        ]

    def test_every_planned_window_is_announced_and_closed_with_its_whole_record(self):
        base, witness = _decoders(rolling=True)
        runtime = _runtime(base=base, rolling=witness)
        session_id = _run_meeting(runtime, frames=TWO_WINDOW_FRAMES)

        queued = self._events(runtime, session_id, "rolling_decode_queued")
        completed = self._events(runtime, session_id, "rolling_decode_completed")
        applied = self._events(runtime, session_id, "text_revision_applied")
        self.assertEqual([item["window_index"] for item in queued], [0, 1])
        self.assertTrue(all(item["admitted"] for item in queued))
        self.assertEqual([item["window_samples"] for item in queued], [WINDOW_SAMPLES] * 2)
        self.assertEqual(
            [item["item_id"] for item in completed], [item["item_id"] for item in queued]
        )
        self.assertEqual([item["outcome"] for item in completed], ["applied", "applied"])
        for item in completed:
            # Plan §7.4's completion record, field for field.
            self.assertEqual(item["window_samples"], WINDOW_SAMPLES)
            self.assertEqual(item["owned_samples"], WINDOW_SAMPLES)
            self.assertGreaterEqual(item["queue_wait_ms"], 0)
            self.assertIsNotNone(item["rolling_decode_elapsed_sec"])
            self.assertIsNotNone(item["rolling_decode_rtf"])
            self.assertIsNotNone(item["rolling_decode_token_cap"])
            self.assertIsNotNone(item["rolling_decode_generated_tokens"])
            self.assertIs(item["rolling_decode_capped"], False)
            self.assertEqual(item["rolling_status"], RollingStatus.ROLLING.value)
        self.assertEqual([item["text_revision_version"] for item in applied], [1, 2])
        self.assertEqual(
            applied[-1]["canonical_through_sample"],
            runtime.snapshot(session_id).session.canonical_through_sample,
        )
        # A base commit says what the second listener is doing, so a converger that stopped
        # while planning nothing is still visible on the stream it stopped appearing in.
        statuses = {
            item["rolling_status"] for item in self._events(runtime, session_id, "canonical_processed")
        }
        self.assertEqual(statuses, {RollingStatus.ROLLING.value})

    def test_overlap_normalization_cost_reaches_the_completion_event_without_text(self):
        base, witness = _decoders(rolling=True)

        def overlapping(*, span, pcm):
            self.assertEqual(len(pcm), span.sample_count * 2)
            witness.calls.append((span.start_sample, span.end_sample))
            return InferenceTranscript(
                transcript=(
                    "[0.00][S01]Incredible.[0.98]"
                    "[0.81][S02]So the question is how did he do it?[9.97]"
                ),
                elapsed_sec=0.01,
                token_cap=canonical_decode_token_cap(sample_count=span.sample_count),
                capped=False,
            )

        witness.transcribe_pcm = overlapping
        runtime = _runtime(base=base, rolling=witness)
        session_id = _run_meeting(runtime, frames=ONE_WINDOW_FRAMES)

        completed = self._events(runtime, session_id, "rolling_decode_completed")
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]["outcome"], "applied")
        self.assertEqual(completed[0]["normalization_merged_segments"], 0)
        self.assertEqual(completed[0]["normalization_dropped_segments"], 0)
        self.assertEqual(completed[0]["normalization_displaced_samples"], 2720)
        self.assertNotIn("transcript", completed[0])
        self.assertNotIn("text", completed[0])

    def test_a_failed_window_closes_its_account_and_names_why(self):
        base, witness = _decoders(
            rolling=True, rolling_failure=LiveProviderTransientError("witness timed out")
        )
        runtime = _runtime(base=base, rolling=witness)
        session_id = _run_meeting(runtime, frames=TWO_WINDOW_FRAMES)

        completed = self._events(runtime, session_id, "rolling_decode_completed")
        self.assertEqual([item["outcome"] for item in completed], ["no_proposal"])
        self.assertEqual(completed[0]["decode_failure"], ROLLING_DECODE_DID_NOT_ANSWER)
        self.assertEqual(completed[0]["rolling_status"], RollingStatus.WINDOW_FAILED.value)
        self.assertIsNone(completed[0]["owned_samples"])
        self.assertEqual(self._events(runtime, session_id, "text_revision_applied"), [])
        self.assertEqual(self._events(runtime, session_id, "text_revision_refused"), [])

    def test_a_defect_closes_the_window_as_a_defect_rather_than_losing_it(self):
        base, witness = _decoders(rolling=True)
        runtime = _runtime(base=base, rolling=witness)
        created = runtime.create()
        coordinator = runtime._sessions[created.session_id].coordinator

        def exploding_submit(decode, item):
            raise RuntimeError("a defect in the second listener")

        coordinator.submit_refinement = exploding_submit
        for sequence in range(TWO_WINDOW_FRAMES):
            runtime.accept_frame(
                created.session_id,
                AudioFrame(
                    sequence=sequence, pcm=b"\x11\x22" * FRAME_SAMPLES, sample_count=FRAME_SAMPLES
                ),
            )
        asyncio.run(runtime.stop(created.session_id, 5.0))

        completed = self._events(runtime, created.session_id, "rolling_decode_completed")
        self.assertEqual([item["outcome"] for item in completed], ["defect"])
        self.assertEqual(completed[0]["rolling_status"], RollingStatus.STOPPED.value)
        self.assertIsNone(runtime.snapshot(created.session_id).terminal_failure)

    def test_a_refused_revision_is_a_refusal_event_and_not_a_silent_no_change(self):
        """`applied=False` means two opposite things until the refusal is named."""

        base, witness = _decoders(rolling=True)
        scheduler = _ManualCanonicalPumpScheduler()
        runtime = _runtime(
            base=base, rolling=witness, max_events=5000, scheduler=scheduler
        )
        created = runtime.create()
        session = runtime._sessions[created.session_id].session
        accepted = session.apply_text_revision
        before_refusal = []
        after_refusal = []

        def stale(proposal):
            # A real refusal from the real validation: the producer's base version is behind.
            before_refusal.append(session.snapshot())
            outcome = accepted(
                replace(proposal, base_text_revision_version=proposal.base_text_revision_version + 7)
            )
            after_refusal.append(session.snapshot())
            return outcome

        session.apply_text_revision = stale
        for sequence in range(4 * ONE_WINDOW_FRAMES):
            runtime.accept_frame(
                created.session_id,
                AudioFrame(
                    sequence=sequence, pcm=b"\x11\x22" * FRAME_SAMPLES, sample_count=FRAME_SAMPLES
                ),
            )
            scheduler.drain()

        asyncio.run(runtime.stop(created.session_id, 5.0))

        completed = self._events(runtime, created.session_id, "rolling_decode_completed")
        refused = self._events(runtime, created.session_id, "text_revision_refused")
        self.assertEqual([item["outcome"] for item in completed], ["refused"])
        self.assertEqual(completed[0]["rolling_status"], RollingStatus.PROPOSAL_REFUSED.value)
        self.assertIn(completed[0]["rolling_status"], {status.value for status in RollingStatus})
        self.assertEqual(completed[0]["proposal_refusals"], 1)
        self.assertEqual(completed[0]["last_proposal_refusal"], "stale_text_revision_version")
        self.assertEqual(completed[0]["retained_samples"], 0)
        self.assertEqual(completed[0]["windows_planned"], 1)
        self.assertEqual(completed[0]["normalization_merged_segments"], 0)
        self.assertEqual(completed[0]["normalization_dropped_segments"], 0)
        self.assertEqual(completed[0]["normalization_displaced_samples"], 0)
        self.assertEqual([item["refusal"] for item in refused], ["stale_text_revision_version"])
        self.assertEqual(refused[0]["source"], "rolling")
        self.assertEqual(self._events(runtime, created.session_id, "text_revision_applied"), [])
        self.assertEqual(
            [item["window_index"] for item in self._events(runtime, created.session_id, "rolling_decode_queued")],
            [0],
        )
        self.assertEqual(len(before_refusal), 1)
        self.assertEqual(len(after_refusal), 1)
        self.assertEqual(after_refusal[0].effective_transcript, before_refusal[0].effective_transcript)
        self.assertEqual(after_refusal[0].committed, before_refusal[0].committed)
        self.assertEqual(
            after_refusal[0].committed_prefix_hash, before_refusal[0].committed_prefix_hash
        )
        self.assertEqual(
            after_refusal[0].text_revision_version, before_refusal[0].text_revision_version
        )
        self.assertEqual(
            after_refusal[0].canonical_through_sample,
            before_refusal[0].canonical_through_sample,
        )

        snapshot = runtime.snapshot(created.session_id).session
        self.assertEqual(snapshot.text_revision_version, 0)
        self.assertEqual(snapshot.canonical_through_sample, 0)
        self.assertEqual(snapshot.accepted_samples, snapshot.accounted_samples)
        self.assertEqual(snapshot.accepted_samples, 4 * WINDOW_SAMPLES)
        self.assertEqual({row.authority for row in snapshot.effective_transcript}, {"provisional"})
        accounting = runtime._sessions[created.session_id].coordinator.rolling_accounting()
        self.assertEqual(accounting.proposal_refusals, 1)
        self.assertEqual(accounting.last_proposal_refusal, "stale_text_revision_version")
        self.assertEqual(accounting.accepted_samples, 4 * WINDOW_SAMPLES)
        self.assertEqual(accounting.retained_samples, 0)
        self.assertEqual(witness.calls, [(0, WINDOW_SAMPLES)])

    def test_an_admission_the_arbiter_refused_is_announced_rather_than_only_counted(self):
        """Two halves of one property: the coordinator reports the refusal, the runtime shows it."""

        arbiter = InferenceArbiter()
        base, witness = _decoders(rolling=True)
        session = LiveSession(max_retained_samples=960000)
        coordinator = LiveCoordinator(
            session_key="refused",
            session=session,
            endpoint_policy=EndpointPolicy(_endpoint_config()),
            speech_provider=ScriptedSpeech(),
            decoder=base,
            identity_preparer=ScriptedIdentity(),
            arbiter=arbiter,
            rolling_decoder=witness,
        )
        item = _refinement_item(coordinator, arbiter)  # dispatched, so its key is RUNNING
        request = item.payload.request
        plans = coordinator._queue_refinement((request,))
        self.assertEqual(
            plans,
            (
                RollingWindowPlan(
                    item_id=None,
                    window_index=request.window_index,
                    start_sample=request.start_sample,
                    end_sample=request.end_sample,
                ),
            ),
        )
        self.assertEqual(coordinator._rolling_admission_refusals, 1)

        base2, witness2 = _decoders(rolling=True)
        runtime = _runtime(base=base2, rolling=witness2)
        created = runtime.create()
        state = runtime._sessions[created.session_id]
        runtime._record_rolling_queued(
            state,
            (RollingWindowPlan(item_id=None, window_index=3, start_sample=0, end_sample=WINDOW_SAMPLES),),
        )
        announced = self._events(runtime, created.session_id, "rolling_decode_queued")
        self.assertEqual([item["admitted"] for item in announced], [False])
        self.assertIsNone(announced[0]["item_id"])
        self.assertEqual(state.rolling_timing, {})

    def test_a_salvaged_span_is_named_on_the_stream(self):
        """The positive control for `decode_salvaged`; the trio corpus never reaches it."""

        raw = "[0.00][S01] the difference between, you said the stock market."

        class UnparseableRunner:
            def transcribe(self, audio_path, **kwargs):
                raise EmptyTranscriptionError(
                    "zero parsed segments",
                    cause=EmptyTranscriptCause.UNPARSEABLE_TEXT,
                    text=raw,
                    generated_tokens=17,
                )

        adapter = RunnerBoundedWavInference(UnparseableRunner(), max_samples=DECODER_MAX_SAMPLES)
        runtime = _runtime(base=adapter, rolling=None)
        session_id = _run_meeting(runtime, frames=HARD_CAP_SAMPLES // FRAME_SAMPLES)

        salvaged = self._events(runtime, session_id, "decode_salvaged")
        processed = self._events(runtime, session_id, "canonical_processed")
        self.assertEqual(len(salvaged), 1)
        self.assertEqual(salvaged[0]["disposition"], "salvaged")
        self.assertEqual(salvaged[0]["span_id"], processed[0]["span_id"])
        self.assertEqual(salvaged[0]["canonical_decode_generated_tokens"], 17)
        self.assertEqual(processed[0]["canonical_decode_salvage"], "salvaged")

    def test_no_event_payload_carries_a_word_anybody_said(self):
        """§7.4's rule, checked against what this meeting actually published."""

        base = ScriptedDecoder(max_samples=DECODER_MAX_SAMPLES, label="zarquon", calls=[])
        witness = ScriptedDecoder(max_samples=WINDOW_SAMPLES, label="beeblebrox", calls=[])
        runtime = _runtime(base=base, rolling=witness)
        session_id = _run_meeting(runtime, frames=ONE_WINDOW_FRAMES)

        surface = " ".join(
            segment.text for segment in runtime.snapshot(session_id).session.effective_transcript
        )
        self.assertIn("beeblebrox", surface)
        stream = json.dumps([event.to_dict() for event in runtime.events(session_id)])
        self.assertNotIn("beeblebrox", stream)
        self.assertNotIn("zarquon", stream)


def _refinement_item(coordinator: LiveCoordinator, arbiter: InferenceArbiter, *, dispatch: bool = True):
    """Plan one window by hand, submit it through the coordinator, and pop it if asked.

    The base is advanced far enough to own the window by committing one span over it, which
    is what makes the window ownable at all -- a revision may not end past committed audio.
    """

    session = coordinator.session
    if coordinator.rolling_accounting().accepted_samples == 0:
        coordinator.converger.accept_pcm(0, b"\0" * WINDOW_SAMPLES * 2)
    session.accept_frame(
        AudioFrame(sequence=0, pcm=b"\0" * WINDOW_SAMPLES * 2, sample_count=WINDOW_SAMPLES)
    )
    span = session.freeze_until(WINDOW_SAMPLES, reason=HARD_CAP_REASON)
    session.submit_unlabeled_canonical(
        span_id=span.id,
        epoch=span.epoch,
        start_sample=span.start_sample,
        end_sample=span.end_sample,
        transcript=f"[0.00][S00] base[{WINDOW_SAMPLES / LIVE_SAMPLE_RATE:g}]",
        local_speakers=("S00",),
    )
    queued = coordinator._observe_base_and_queue()
    if len(queued) != 1:
        raise AssertionError(f"expected one planned window, got {queued}")
    if not dispatch:
        return None
    item = arbiter.next_work()
    if item is None or not isinstance(item.payload, RefinementWork):
        raise AssertionError("the arbiter did not dispatch the window that was just planned.")
    return item


if __name__ == "__main__":
    unittest.main()


def test_capacity_event_capture_retains_all_600_seconds_past_product_ring_limit():
    from moss_transcribe_diarize.phase2_acceptance_external import _LoadEventCapture
    from moss_transcribe_diarize.concurrency_evidence import prestop_inference_projection

    base, witness = _decoders(rolling=True)
    scheduler = _ManualCanonicalPumpScheduler()
    runtime = _runtime(base=base, rolling=witness, scheduler=scheduler)
    session_id = runtime.create().session_id
    capture = _LoadEventCapture()
    for sequence in range(1200):
        runtime.accept_frame(session_id, AudioFrame(
            sequence=sequence, pcm=b"\x11\x22" * FRAME_SAMPLES,
            sample_count=FRAME_SAMPLES,
        ))
        scheduler.drain()
        capture.read(runtime, session_id)
    asyncio.run(runtime.stop(session_id, 5.0))
    capture.read(runtime, session_id)
    assert len(runtime.events(session_id)) == 1000
    assert len(capture.events) > 1000
    result = prestop_inference_projection(capture.events, accepted_audio_seconds=600)
    assert result["canonical_processed_items"] == 240
    assert result["rolling_completed_items"] == 60
    assert abs(result["decode_seconds"] - 3.0) < 1e-9


def _queued_window_after_long_wait(*, tape=True):
    """17.5 s admission plus 16.5 s queue wait, on the actual runtime/arbiter path."""
    base, witness = _decoders(rolling=True)
    clock = [0]
    descriptor = _descriptor()
    descriptor = replace(descriptor, bounds=replace(
        descriptor.bounds, max_tape_bytes=60 * LIVE_SAMPLE_RATE * 2 if tape else None))
    scheduler = _ManualCanonicalPumpScheduler()
    runtime = LiveServiceRuntime(
        descriptor=descriptor, endpoint_policy_factory=lambda: EndpointPolicy(_endpoint_config()),
        speech_provider_factory=ScriptedSpeech, decoder_factory=lambda: base,
        rolling_decoder_factory=lambda: witness, identity_preparer_factory=ScriptedIdentity,
        _canonical_scheduler=scheduler, monotonic_ns=lambda: clock[0],
    )
    sid = runtime.create().session_id
    def feed(start, end):
        for sequence in range(start, end):
            clock[0] += 500_000_000
            runtime.accept_frame(sid, AudioFrame(sequence=sequence,
                pcm=sequence.to_bytes(2, 'little') * FRAME_SAMPLES, sample_count=FRAME_SAMPLES))
    feed(0, 35)
    for _ in range(4):
        assert runtime._pump_next_ready_session(raise_errors=True)
    assert runtime._sessions[sid].arbiter.snapshot().live_refinement == 1
    feed(35, 68)
    return runtime, scheduler, sid, witness


def test_queued_rolling_recovers_evicted_audio_without_skipping_prefix():
    runtime, scheduler, sid, witness = _queued_window_after_long_wait()
    decode = witness.transcribe_pcm
    def checked_decode(*, span, pcm):
        expected = b"".join(sequence.to_bytes(2, 'little') * FRAME_SAMPLES
                            for sequence in range(span.start_sample // FRAME_SAMPLES,
                                                  span.end_sample // FRAME_SAMPLES))
        assert pcm == expected
        return decode(span=span, pcm=pcm)
    witness.transcribe_pcm = checked_decode
    scheduler.drain()
    snapshot = runtime.snapshot(sid).session
    assert witness.calls == [(0, 160000), (160000, 320000), (320000, 480000)]
    assert snapshot.canonical_through_sample == 480000
    assert snapshot.text_revision_version == 3
    assert snapshot.status == 'active'
    accounting = runtime._sessions[sid].coordinator.rolling_accounting()
    assert accounting.status is RollingStatus.ROLLING
    assert accounting.retained_high_water_samples <= 320000
    events = runtime.events(sid)
    queued = next(e for e in events if e.kind == 'rolling_decode_queued')
    completed = next(e for e in events if e.kind == 'rolling_decode_completed')
    assert completed.payload['runtime_monotonic_ns'] - queued.payload['runtime_monotonic_ns'] == 16_500_000_000
    assert completed.payload['applied'] is True
    assert all(end <= snapshot.committed_samples for _, end in witness.calls)


def test_queued_rolling_without_complete_tape_still_reports_eviction():
    runtime, scheduler, sid, witness = _queued_window_after_long_wait(tape=False)
    scheduler.drain()
    assert witness.calls == []
    assert runtime.snapshot(sid).session.status == 'active'
    assert runtime._sessions[sid].coordinator.rolling_accounting().status is RollingStatus.PCM_EVICTED


def test_abort_fences_queued_rolling_recovery():
    runtime, scheduler, sid, witness = _queued_window_after_long_wait()
    asyncio.run(runtime.abort(sid, 'presenter aborted'))
    scheduler.drain()
    snapshot = runtime.snapshot(sid).session
    assert snapshot.status == 'aborted'
    assert snapshot.text_revision_version == 0
    assert witness.calls == []


def test_recovery_refuses_missing_tape_without_skipping_to_newest_window():
    runtime, scheduler, sid, witness = _queued_window_after_long_wait()
    runtime._sessions[sid].coordinator.tape.release()
    scheduler.drain()
    # The original immutable request remains valid; the missing NEXT window does not.
    assert witness.calls == [(0, 160000)]
    assert runtime.snapshot(sid).session.canonical_through_sample == 160000
    assert runtime._sessions[sid].coordinator.rolling_accounting().status is RollingStatus.PCM_EVICTED


def test_complete_tape_does_not_revive_failed_rolling_decode():
    runtime, scheduler, sid, witness = _queued_window_after_long_wait()
    witness.failure = LiveProviderTransientError('decoder did not answer')
    scheduler.drain()
    assert witness.calls == [(0, 160000)]
    assert runtime.snapshot(sid).session.text_revision_version == 0
    assert runtime._sessions[sid].coordinator.rolling_accounting().status is RollingStatus.WINDOW_FAILED


def test_abort_fences_inflight_tape_recovery_publication():
    import threading
    runtime, scheduler, sid, witness = _queued_window_after_long_wait()
    entered, release = threading.Event(), threading.Event()
    decode = witness.transcribe_pcm
    def blocked(*, span, pcm):
        if span.start_sample == 160000:
            entered.set()
            assert release.wait(5)
        return decode(span=span, pcm=pcm)
    witness.transcribe_pcm = blocked
    worker = threading.Thread(target=scheduler.drain)
    worker.start()
    try:
        assert entered.wait(5), 'recovery window was not dispatched'
        asyncio.run(runtime.abort(sid, 'abort during recovered decode'))
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive()
    snapshot = runtime.snapshot(sid).session
    assert snapshot.status == 'aborted'
    assert snapshot.text_revision_version == 1
    assert snapshot.canonical_through_sample == 160000
