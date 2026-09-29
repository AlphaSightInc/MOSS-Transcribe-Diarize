from __future__ import annotations

import json
import tempfile
import time
import unittest
import wave
from dataclasses import MISSING, dataclass, fields, is_dataclass, replace
from pathlib import Path

from moss_transcribe_diarize import live_service_replay
from moss_transcribe_diarize.app.live_adapters import InferenceTranscript
from moss_transcribe_diarize.app.live_endpoint import EndpointPolicy, EndpointPolicyConfig, SpeechObservation
from moss_transcribe_diarize.app.live_lane_contract import LiveV2Capabilities, LiveV2Descriptor
from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceBounds,
    _ManualTerminalScheduler,
    LiveServiceConfigHashes,
    LiveServiceDescriptor,
    LiveServiceEvent,
    LiveServiceFailureKind,
    LiveServiceFailureRecord,
    LiveServiceIdentityCommitFailure,
    LiveServiceProviderConfigFailure,
    LiveServiceRtfFailure,
    LiveServiceRuntime,
    LiveServiceSnapshot,
    LiveDraft,
    hash_config,
)
from moss_transcribe_diarize.app.live_transcript_convergence import TerminalTranscriptFinalizer
from moss_transcribe_diarize.app.live_session import (
    AudioFrame,
    CanonicalCommit,
    EffectiveTranscriptSegment,
    FrameAck,
    FrozenSpan,
    LIVE_SAMPLE_RATE,
    LiveIdentityPreparation,
    LiveIdentitySnapshot,
    LiveSnapshot,
    PCM16_BYTES_PER_SAMPLE,
    ProvisionalSuffix,
)
from tests.test_live_terminal_finalizer import WholeMeetingStub
from tests.test_live_terminal_lifecycle import MEETING_SAMPLES as _TERMINAL_MEETING_SAMPLES
from tests.test_live_terminal_lifecycle import _runtime as _terminal_runtime


class LiveServiceReplayContractTest(unittest.TestCase):
    def test_service_failure_kinds_map_to_typed_replay_exits(self):
        error = LiveServiceProviderConfigFailure("config mismatch")

        self.assertEqual(
            live_service_replay._exit_code_for_service_failure(error.failure.kind),
            live_service_replay.ServiceReplayProviderConfigFailure.exit_code,
        )
        self.assertEqual(
            live_service_replay._exit_code_for_service_failure(LiveServiceFailureKind.TRANSPORT_PACING),
            live_service_replay.ServiceReplayTransportFailure.exit_code,
        )
        self.assertEqual(
            live_service_replay._exit_code_for_service_failure(LiveServiceFailureKind.IDENTITY_COMMIT),
            live_service_replay.ServiceReplayIdentityCommitFailure.exit_code,
        )
        self.assertEqual(
            live_service_replay._exit_code_for_service_failure(LiveServiceFailureKind.RTF),
            live_service_replay.ServiceReplayRtfFailure.exit_code,
        )

    def test_in_memory_paced_runner_uses_descriptor_frames_and_final_short_frame(self):
        descriptor = _descriptor(frame_samples=400)
        service = live_service_replay.InMemoryLiveReplayService(
            _runtime(
                descriptor=descriptor,
                speech=(False, False, False),
                session_ids=("session-1",),
                decoder=RecordingDecoder(elapsed_sec=0.001),
            )
        )
        clock = ScriptedClock()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "audio.wav"
            _write_wav(audio, samples=900)
            outputs = live_service_replay.run_service_replay(
                service=service,
                audio_path=audio,
                out_dir=root / "out",
                pace=1.0,
                max_pacing_lag=0.5,
                runs=1,
                expect_revision=descriptor.source_revision,
                expect_provider_hash=descriptor.provider_manifest_hash,
                expect_config_hash=descriptor.config_hashes.combined_config_hash,
                monotonic=clock.monotonic,
                sleep=clock.sleep,
            )

            trace = _jsonl(outputs.trace_path)
            summary = json.loads(outputs.summary_path.read_text(encoding="utf-8"))
            manifest = json.loads(outputs.manifest_path.read_text(encoding="utf-8"))
            evaluator = _jsonl(outputs.evaluator_path)
            frame_events = [item for item in trace if item["kind"] == "frame_accepted"]

        self.assertTrue(all(item["schema_version"] == 1 for item in trace))
        self.assertEqual(manifest["artifact_schema_versions"]["trace"], 1)
        self.assertEqual(manifest["audio"]["sample_count"], 900)
        self.assertEqual(manifest["audio"]["duration_seconds"], 900 / LIVE_SAMPLE_RATE)
        self.assertEqual(manifest["frame_samples"], 400)
        self.assertEqual(manifest["frame_count"], 3)
        self.assertEqual(manifest["descriptor"]["provider_manifest_hash"], descriptor.provider_manifest_hash)
        self.assertEqual([item["sample_count"] for item in frame_events], [400, 400, 100])
        self.assertEqual([item["scheduled_sample"] for item in frame_events], [0, 400, 800])
        self.assertEqual(summary["status"], "succeeded")
        self.assertEqual(summary["trace_event_count"], len(trace))
        self.assertEqual(summary["scheduled_sample_offsets"], [0, 400, 800])
        self.assertEqual(summary["accepted_samples"], 900)
        self.assertEqual(summary["accounted_samples"], 900)
        self.assertTrue(summary["exact_accounting"])
        self.assertEqual(
            [item["kind"] for item in evaluator],
            ["terminal_outcome", "frame_sequence", "sample_accounting", "canonical_decode_rtf"],
        )
        self.assertTrue(evaluator[2]["exact_accounting"])
        self.assertEqual(evaluator[-1]["values"], [0.001 / (900 / LIVE_SAMPLE_RATE)])
        self.assertTrue(evaluator[-1]["passed"])

    def test_descriptor_mismatch_fails_before_audio_admission(self):
        descriptor = _descriptor()
        runtime = _runtime(descriptor=descriptor, speech=(False,), session_ids=("session-1",))
        service = live_service_replay.InMemoryLiveReplayService(runtime)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "audio.wav"
            _write_wav(audio, samples=400)
            with self.assertRaises(live_service_replay.ServiceReplayProviderConfigFailure):
                live_service_replay.run_service_replay(
                    service=service,
                    audio_path=audio,
                    out_dir=root / "out",
                    pace=1.0,
                    max_pacing_lag=0.5,
                    runs=1,
                    expect_revision="wrong-revision",
                    expect_provider_hash=descriptor.provider_manifest_hash,
                    expect_config_hash=descriptor.config_hashes.combined_config_hash,
                    monotonic=lambda: 0.0,
                    sleep=lambda seconds: None,
                )

            summary = json.loads((root / "out" / "run-001" / "summary.json").read_text(encoding="utf-8"))
            manifest = json.loads((root / "out" / "replay-manifest.json").read_text(encoding="utf-8"))
            trace = _jsonl(root / "out" / "run-001" / "trace.jsonl")

        self.assertEqual(summary["failure_kind"], "provider_config")
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["accepted_samples"], 0)
        self.assertEqual(summary["accounted_samples"], 0)
        self.assertEqual(manifest["descriptor"]["source_revision"], descriptor.source_revision)
        self.assertEqual(trace[-1]["kind"], "terminal")
        self.assertEqual(trace[-1]["failure_kind"], "provider_config")
        self.assertIn("snapshot", trace[-1])
        self.assertEqual(runtime.snapshot("session-1").session.accepted_samples, 0)

    def test_ambiguous_frame_failure_aborts_without_retrying_sequence(self):
        descriptor = _descriptor(frame_samples=400)
        service = AmbiguousOnceService(_runtime(descriptor=descriptor, speech=(False,), session_ids=("session-1",)))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "audio.wav"
            _write_wav(audio, samples=400)
            with self.assertRaises(live_service_replay.ServiceReplayTransportFailure):
                live_service_replay.run_service_replay(
                    service=service,
                    audio_path=audio,
                    out_dir=root / "out",
                    pace=1.0,
                    max_pacing_lag=0.5,
                    runs=1,
                    expect_revision=descriptor.source_revision,
                    expect_provider_hash=descriptor.provider_manifest_hash,
                    expect_config_hash=descriptor.config_hashes.combined_config_hash,
                    monotonic=lambda: 0.0,
                    sleep=lambda seconds: None,
                )

            summary = json.loads((root / "out" / "run-001" / "summary.json").read_text(encoding="utf-8"))
            evaluator = _jsonl(root / "out" / "run-001" / "evaluator.jsonl")

        self.assertEqual(service.frame_sequences, [0])
        self.assertEqual(service.abort_reasons, ["timeout after possible admission"])
        self.assertEqual(summary["failure_kind"], "transport_pacing")
        self.assertEqual(evaluator[0]["status"], "failed")
        self.assertEqual(evaluator[0]["failure_kind"], "transport_pacing")

    def test_identity_commit_failure_writes_typed_terminal_artifacts(self):
        descriptor = _descriptor(frame_samples=400)
        service = live_service_replay.InMemoryLiveReplayService(
            _runtime(
                descriptor=descriptor,
                speech=(False,),
                session_ids=("session-1",),
                identity=PreparingIdentity(stale_base_version=True),
            )
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "audio.wav"
            _write_wav(audio, samples=400)
            with self.assertRaises(live_service_replay.ServiceReplayIdentityCommitFailure):
                live_service_replay.run_service_replay(
                    service=service,
                    audio_path=audio,
                    out_dir=root / "out",
                    pace=1.0,
                    max_pacing_lag=0.5,
                    runs=1,
                    expect_revision=descriptor.source_revision,
                    expect_provider_hash=descriptor.provider_manifest_hash,
                    expect_config_hash=descriptor.config_hashes.combined_config_hash,
                    monotonic=lambda: 0.0,
                    sleep=lambda seconds: None,
                )

            trace = _jsonl(root / "out" / "run-001" / "trace.jsonl")
            summary = json.loads((root / "out" / "run-001" / "summary.json").read_text(encoding="utf-8"))
            evaluator = _jsonl(root / "out" / "run-001" / "evaluator.jsonl")

        self.assertEqual(trace[-1]["failure_kind"], "identity_commit")
        self.assertEqual(trace[-1]["service_failure"]["kind"], "identity_commit")
        self.assertEqual(summary["failure_kind"], "identity_commit")
        self.assertEqual(summary["accepted_samples"], 400)
        self.assertEqual(summary["accounted_samples"], 0)
        self.assertFalse(summary["exact_accounting"])
        self.assertEqual(evaluator[0]["failure_kind"], "identity_commit")
        self.assertFalse(evaluator[2]["exact_accounting"])

    def test_rtf_failure_writes_typed_terminal_artifacts_after_admission(self):
        descriptor = _descriptor(frame_samples=400)
        service = StopFailureService(
            _runtime(descriptor=descriptor, speech=(False,), session_ids=("session-1",)),
            LiveServiceRtfFailure("canonical decoder p95 RTF bound exceeded.", code="rtf_exceeded"),
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "audio.wav"
            _write_wav(audio, samples=400)
            with self.assertRaises(live_service_replay.ServiceReplayRtfFailure):
                live_service_replay.run_service_replay(
                    service=service,
                    audio_path=audio,
                    out_dir=root / "out",
                    pace=1.0,
                    max_pacing_lag=0.5,
                    runs=1,
                    expect_revision=descriptor.source_revision,
                    expect_provider_hash=descriptor.provider_manifest_hash,
                    expect_config_hash=descriptor.config_hashes.combined_config_hash,
                    monotonic=lambda: 0.0,
                    sleep=lambda seconds: None,
                )

            trace = _jsonl(root / "out" / "run-001" / "trace.jsonl")
            summary = json.loads((root / "out" / "run-001" / "summary.json").read_text(encoding="utf-8"))
            evaluator = _jsonl(root / "out" / "run-001" / "evaluator.jsonl")

        self.assertEqual(service.frame_sequences, [0])
        self.assertEqual(service.abort_reasons, ["canonical decoder p95 RTF bound exceeded."])
        self.assertEqual(trace[-1]["failure_kind"], "rtf")
        self.assertEqual(trace[-1]["service_failure"]["code"], "rtf_exceeded")
        self.assertEqual(summary["failure_kind"], "rtf")
        self.assertEqual(summary["accepted_samples"], 400)
        self.assertEqual(summary["accounted_samples"], 0)
        self.assertFalse(summary["exact_accounting"])
        self.assertEqual(evaluator[0]["failure_kind"], "rtf")

    def test_measured_canonical_decode_rtf_0_999999_passes_with_artifacts(self):
        descriptor = _descriptor(frame_samples=400)
        service = live_service_replay.InMemoryLiveReplayService(
            _runtime(
                descriptor=descriptor,
                speech=(True, False),
                session_ids=("session-1",),
                decoder=RecordingDecoder(elapsed_sec=0.024999975),
            )
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "audio.wav"
            _write_wav(audio, samples=800)
            outputs = live_service_replay.run_service_replay(
                service=service,
                audio_path=audio,
                out_dir=root / "out",
                pace=1.0,
                max_pacing_lag=0.5,
                runs=1,
                expect_revision=descriptor.source_revision,
                expect_provider_hash=descriptor.provider_manifest_hash,
                expect_config_hash=descriptor.config_hashes.combined_config_hash,
                monotonic=ScriptedClock().monotonic,
                sleep=ScriptedClock().sleep,
            )

            trace = _jsonl(outputs.trace_path)
            summary = json.loads(outputs.summary_path.read_text(encoding="utf-8"))
            evaluator = _jsonl(outputs.evaluator_path)

        rtf_evaluation = [item for item in trace if item["kind"] == "canonical_decode_rtf_evaluation"][0]
        self.assertEqual(summary["status"], "succeeded")
        self.assertEqual(summary["canonical_decode_rtf_values"], [0.999999, 0.999999])
        self.assertEqual(summary["canonical_decode_rtf_span_ids"], [0, 1])
        self.assertEqual(summary["canonical_decode_rtf_p95"], 0.999999)
        self.assertEqual(summary["canonical_decode_rtf_bound"], 1.0)
        self.assertTrue(summary["canonical_decode_rtf_passed"])
        self.assertEqual(rtf_evaluation["canonical_decode_rtf_p95"], 0.999999)
        self.assertEqual(evaluator[-1]["kind"], "canonical_decode_rtf")
        self.assertEqual(evaluator[-1]["p95"], 0.999999)
        self.assertTrue(evaluator[-1]["passed"])

    def test_measured_canonical_decode_rtf_1_0_fails_with_retained_artifacts(self):
        descriptor = _descriptor(frame_samples=400)
        service = live_service_replay.InMemoryLiveReplayService(
            _runtime(
                descriptor=descriptor,
                speech=(True, False),
                session_ids=("session-1",),
                decoder=RecordingDecoder(elapsed_sec=0.025),
            )
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "audio.wav"
            _write_wav(audio, samples=800)
            with self.assertRaises(live_service_replay.ServiceReplayRtfFailure):
                live_service_replay.run_service_replay(
                    service=service,
                    audio_path=audio,
                    out_dir=root / "out",
                    pace=1.0,
                    max_pacing_lag=0.5,
                    runs=1,
                    expect_revision=descriptor.source_revision,
                    expect_provider_hash=descriptor.provider_manifest_hash,
                    expect_config_hash=descriptor.config_hashes.combined_config_hash,
                    monotonic=ScriptedClock().monotonic,
                    sleep=ScriptedClock().sleep,
                )

            trace = _jsonl(root / "out" / "run-001" / "trace.jsonl")
            summary = json.loads((root / "out" / "run-001" / "summary.json").read_text(encoding="utf-8"))
            evaluator = _jsonl(root / "out" / "run-001" / "evaluator.jsonl")

        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["failure_kind"], "rtf")
        self.assertEqual(summary["canonical_decode_rtf_values"], [1.0, 1.0])
        self.assertEqual(summary["canonical_decode_rtf_p95"], 1.0)
        self.assertEqual(summary["canonical_decode_rtf_bound"], 1.0)
        self.assertFalse(summary["canonical_decode_rtf_passed"])
        self.assertEqual(trace[-1]["kind"], "terminal")
        self.assertEqual(trace[-1]["failure_kind"], "rtf")
        self.assertEqual(evaluator[0]["failure_kind"], "rtf")
        self.assertEqual(evaluator[-1]["p95"], 1.0)
        self.assertFalse(evaluator[-1]["passed"])

    def test_canonical_decode_rtf_uses_nearest_rank_p95_not_mean_or_max(self):
        values = [0.1] * 18 + [0.8, 2.0]
        events = tuple(
            _canonical_processed_event(seq=index, span_id=index, rtf=value)
            for index, value in enumerate(values, start=1)
        )

        evaluation = live_service_replay._canonical_decode_rtf_evaluation(events)

        self.assertEqual(evaluation["canonical_decode_rtf_values"], values)
        self.assertEqual(evaluation["canonical_decode_rtf_span_ids"], list(range(1, 21)))
        self.assertEqual(evaluation["canonical_decode_rtf_p95"], 0.8)
        self.assertLess(evaluation["canonical_decode_rtf_p95"], max(values))
        self.assertNotEqual(evaluation["canonical_decode_rtf_p95"], sum(values) / len(values))

    def test_declared_unknown_canonical_decode_rtf_is_visible_and_excluded_from_p95(self):
        numeric = _canonical_processed_event(seq=1, span_id=7, rtf=0.4)
        unknown = _canonical_processed_event(seq=2, span_id=8, rtf=0.9)
        unknown_payload = dict(unknown.payload)
        unknown_payload.update(
            {
                "canonical_decode_elapsed_sec": None,
                "canonical_decode_rtf": None,
            }
        )

        evaluation = live_service_replay._canonical_decode_rtf_evaluation(
            (numeric, _event_with_payload(unknown, unknown_payload))
        )

        self.assertEqual(evaluation["canonical_decode_rtf_values"], [0.4])
        self.assertEqual(evaluation["canonical_decode_rtf_span_ids"], [7])
        self.assertEqual(evaluation["canonical_decode_rtf_p95"], 0.4)
        self.assertEqual(evaluation["canonical_decode_rtf_invalid_count"], 0)
        self.assertEqual(evaluation["canonical_decode_rtf_declared_unknown_count"], 1)
        self.assertEqual(
            evaluation["canonical_decode_rtf_declared_unknown_measurements"],
            [
                {
                    "event_seq": 2,
                    "span_id": 8,
                    "canonical_decode_elapsed_sec": None,
                    "frozen_span_sample_count": LIVE_SAMPLE_RATE,
                    "frozen_span_duration_sec": 1.0,
                    "canonical_decode_rtf": None,
                }
            ],
        )
        self.assertTrue(evaluation["canonical_decode_rtf_passed"])

    def test_declared_unknown_canonical_decode_rtf_survives_summary_trace_and_evaluator(self):
        descriptor = _descriptor(frame_samples=400)
        service = CorruptingEventsService(
            _runtime(
                descriptor=descriptor,
                speech=(True, False),
                session_ids=("session-1",),
                decoder=RecordingDecoder(elapsed_sec=0.01),
            ),
            lambda payload: (
                payload.update(
                    {
                        "canonical_decode_elapsed_sec": None,
                        "canonical_decode_rtf": None,
                    }
                )
                if payload["span_id"] == 1
                else None
            ),
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "audio.wav"
            _write_wav(audio, samples=800)
            outputs = live_service_replay.run_service_replay(
                service=service,
                audio_path=audio,
                out_dir=root / "out",
                pace=1.0,
                max_pacing_lag=0.5,
                runs=1,
                expect_revision=descriptor.source_revision,
                expect_provider_hash=descriptor.provider_manifest_hash,
                expect_config_hash=descriptor.config_hashes.combined_config_hash,
                monotonic=ScriptedClock().monotonic,
                sleep=ScriptedClock().sleep,
            )

            trace = _jsonl(outputs.trace_path)
            summary = json.loads(outputs.summary_path.read_text(encoding="utf-8"))
            evaluator = _jsonl(outputs.evaluator_path)

        rtf_evaluation = [item for item in trace if item["kind"] == "canonical_decode_rtf_evaluation"][0]
        self.assertEqual(summary["status"], "succeeded")
        self.assertEqual(len(summary["canonical_decode_rtf_values"]), 1)
        self.assertAlmostEqual(summary["canonical_decode_rtf_values"][0], 0.4)
        self.assertEqual(summary["canonical_decode_rtf_declared_unknown_count"], 1)
        self.assertEqual(
            summary["canonical_decode_rtf_declared_unknown_measurements"][0]["span_id"],
            1,
        )
        self.assertEqual(rtf_evaluation["canonical_decode_rtf_declared_unknown_count"], 1)
        self.assertEqual(evaluator[-1]["kind"], "canonical_decode_rtf")
        self.assertEqual(evaluator[-1]["declared_unknown_count"], 1)
        self.assertEqual(evaluator[-1]["declared_unknown_measurements"][0]["span_id"], 1)
        self.assertTrue(evaluator[-1]["passed"])

    def test_half_null_canonical_decode_rtf_event_payloads_fail_closed(self):
        cases = {
            "elapsed_only_null": {
                "canonical_decode_elapsed_sec": None,
                "canonical_decode_rtf": 0.5,
            },
            "rtf_only_null": {
                "canonical_decode_elapsed_sec": 0.5,
                "canonical_decode_rtf": None,
            },
        }

        for name, updates in cases.items():
            with self.subTest(name=name):
                event = _canonical_processed_event(seq=1, span_id=7, rtf=0.5)
                payload = dict(event.payload)
                payload.update(updates)
                evaluation = live_service_replay._canonical_decode_rtf_evaluation(
                    (_event_with_payload(event, payload),)
                )

                self.assertFalse(evaluation["canonical_decode_rtf_passed"])
                self.assertEqual(evaluation["canonical_decode_rtf_invalid_count"], 1)
                self.assertEqual(evaluation["canonical_decode_rtf_declared_unknown_count"], 0)

    def test_invalid_canonical_decode_rtf_event_payloads_fail_closed(self):
        cases = {
            "missing_elapsed": lambda payload: payload.pop("canonical_decode_elapsed_sec"),
            "missing_rtf": lambda payload: payload.pop("canonical_decode_rtf"),
            "negative_elapsed": lambda payload: payload.update({"canonical_decode_elapsed_sec": -0.1}),
            "negative_rtf": lambda payload: payload.update({"canonical_decode_rtf": -0.1}),
            "non_finite_elapsed": lambda payload: payload.update({"canonical_decode_elapsed_sec": float("nan")}),
            "non_finite_rtf": lambda payload: payload.update({"canonical_decode_rtf": float("inf")}),
            "zero_duration": lambda payload: payload.update({"frozen_span_duration_sec": 0.0}),
        }

        for name, mutate in cases.items():
            with self.subTest(name=name):
                event = _canonical_processed_event(seq=1, span_id=7, rtf=0.5)
                payload = dict(event.payload)
                mutate(payload)
                evaluation = live_service_replay._canonical_decode_rtf_evaluation(
                    (_event_with_payload(event, payload),)
                )

                self.assertEqual(evaluation["canonical_decode_rtf_values"], [])
                self.assertEqual(evaluation["canonical_decode_rtf_span_ids"], [])
                self.assertIsNone(evaluation["canonical_decode_rtf_p95"])
                self.assertEqual(evaluation["canonical_decode_rtf_bound"], 1.0)
                self.assertFalse(evaluation["canonical_decode_rtf_passed"])
                self.assertEqual(evaluation["canonical_decode_rtf_invalid_count"], 1)
                self.assertEqual(evaluation["canonical_decode_rtf_declared_unknown_count"], 0)
                self.assertEqual(evaluation["canonical_decode_rtf_invalid_measurements"][0]["span_id"], 7)

    def test_invalid_canonical_decode_rtf_event_retains_failure_artifacts(self):
        descriptor = _descriptor(frame_samples=400)
        service = CorruptingEventsService(
            _runtime(
                descriptor=descriptor,
                speech=(True, False),
                session_ids=("session-1",),
                decoder=RecordingDecoder(elapsed_sec=0.01),
            ),
            lambda payload: payload.pop("canonical_decode_elapsed_sec"),
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "audio.wav"
            _write_wav(audio, samples=800)
            with self.assertRaises(live_service_replay.ServiceReplayRtfFailure):
                live_service_replay.run_service_replay(
                    service=service,
                    audio_path=audio,
                    out_dir=root / "out",
                    pace=1.0,
                    max_pacing_lag=0.5,
                    runs=1,
                    expect_revision=descriptor.source_revision,
                    expect_provider_hash=descriptor.provider_manifest_hash,
                    expect_config_hash=descriptor.config_hashes.combined_config_hash,
                    monotonic=ScriptedClock().monotonic,
                    sleep=ScriptedClock().sleep,
                )

            trace = _jsonl(root / "out" / "run-001" / "trace.jsonl")
            summary = json.loads((root / "out" / "run-001" / "summary.json").read_text(encoding="utf-8"))
            evaluator = _jsonl(root / "out" / "run-001" / "evaluator.jsonl")

        rtf_evaluation = [item for item in trace if item["kind"] == "canonical_decode_rtf_evaluation"][0]
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["failure_kind"], "rtf")
        self.assertEqual(summary["canonical_decode_rtf_values"], [])
        self.assertEqual(summary["canonical_decode_rtf_span_ids"], [])
        self.assertIsNone(summary["canonical_decode_rtf_p95"])
        self.assertEqual(summary["canonical_decode_rtf_bound"], 1.0)
        self.assertFalse(summary["canonical_decode_rtf_passed"])
        self.assertEqual(summary["canonical_decode_rtf_invalid_count"], 2)
        self.assertIn("canonical_decode_elapsed_sec", summary["canonical_decode_rtf_invalid_measurements"][0]["message"])
        self.assertEqual(rtf_evaluation["canonical_decode_rtf_invalid_count"], 2)
        self.assertEqual(trace[-1]["failure_kind"], "rtf")
        self.assertEqual(evaluator[0]["failure_kind"], "rtf")
        self.assertEqual(evaluator[-1]["invalid_count"], 2)

    def test_event_stream_outliving_the_retention_bound_is_recorded_in_full(self):
        # The runtime keeps events in a deque(maxlen=bounds.max_events).  A client that
        # reads once, after the session ends, gets only the tail -- which is how every
        # 5-minute trace in this repo lost its first ~30 s while still looking well
        # formed.  Thirty events past a twenty-event bound is the same shape in miniature.
        descriptor = _descriptor(frame_samples=400, max_events=20)
        service = RecordingService(
            _runtime(
                descriptor=descriptor,
                speech=(True, True, False, True, True, False, True, True),
                session_ids=("session-1",),
            )
        )
        clock = ScriptedClock()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "audio.wav"
            _write_wav(audio, samples=3200)
            outputs = live_service_replay.run_service_replay(
                service=service,
                audio_path=audio,
                out_dir=root / "out",
                pace=1.0,
                max_pacing_lag=0.5,
                runs=1,
                expect_revision=descriptor.source_revision,
                expect_provider_hash=descriptor.provider_manifest_hash,
                expect_config_hash=descriptor.config_hashes.combined_config_hash,
                monotonic=clock.monotonic,
                sleep=clock.sleep,
            )
            trace = _jsonl(outputs.trace_path)
            summary = json.loads(outputs.summary_path.read_text(encoding="utf-8"))

        recorded = [item["event"] for item in trace if item["kind"] == "service_event"]
        seqs = [item["seq"] for item in recorded]
        self.assertEqual(summary["status"], "succeeded")
        self.assertGreater(len(recorded), descriptor.bounds.max_events)
        self.assertEqual(seqs, list(range(len(recorded))))
        self.assertEqual(recorded[0]["kind"], "session_created")
        self.assertEqual(recorded[-1]["kind"], "session_closed")
        self.assertEqual(
            [item["payload"]["sequence"] for item in recorded if item["kind"] == "frame_accepted"],
            list(range(8)),
        )

    def test_evicted_service_events_fail_the_replay_instead_of_truncating_the_trace(self):
        descriptor = _descriptor(frame_samples=400)
        service = EvictingEventsService(
            _runtime(
                descriptor=descriptor,
                speech=(True, False, True),
                session_ids=("session-1",),
            ),
            retain=1,
        )
        clock = ScriptedClock()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "audio.wav"
            _write_wav(audio, samples=1200)
            with self.assertRaises(live_service_replay.ServiceReplayEventLossFailure):
                live_service_replay.run_service_replay(
                    service=service,
                    audio_path=audio,
                    out_dir=root / "out",
                    pace=1.0,
                    max_pacing_lag=0.5,
                    runs=1,
                    expect_revision=descriptor.source_revision,
                    expect_provider_hash=descriptor.provider_manifest_hash,
                    expect_config_hash=descriptor.config_hashes.combined_config_hash,
                    monotonic=clock.monotonic,
                    sleep=clock.sleep,
                )
            summary = json.loads((root / "out" / "run-001" / "summary.json").read_text(encoding="utf-8"))

        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["failure_kind"], "event_loss")

    def test_pacing_lag_fails_before_late_frame_admission(self):
        descriptor = _descriptor(frame_samples=400)
        service = RecordingService(_runtime(descriptor=descriptor, speech=(False,), session_ids=("session-1",)))
        clock = ScriptedClock(values=[0.0, 1.0])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "audio.wav"
            _write_wav(audio, samples=400)
            with self.assertRaises(live_service_replay.ServiceReplayTransportFailure):
                live_service_replay.run_service_replay(
                    service=service,
                    audio_path=audio,
                    out_dir=root / "out",
                    pace=1.0,
                    max_pacing_lag=0.5,
                    runs=1,
                    expect_revision=descriptor.source_revision,
                    expect_provider_hash=descriptor.provider_manifest_hash,
                    expect_config_hash=descriptor.config_hashes.combined_config_hash,
                    monotonic=clock.monotonic,
                    sleep=clock.sleep,
                )

        self.assertEqual(service.frame_sequences, [])

class ReplayTerminalFinalizationWaitTest(unittest.TestCase):
    """Plan §12.3 from the measuring client's side: a run ends when the *meeting* does.

    The terminal pass deliberately runs behind the stop response, so a client that returned
    the moment `POST /stop` answered wrote the ROLLING surface into `trace.jsonl` while every
    filename around it said the run had completed -- measured on the deployed service and
    recorded as finding F1 of `evidence/live-convergence-0824/M4-deployed-terminal/`, where
    the terminal events arrived after the artifacts were closed and the numbers had to be
    recovered by polling the session afterwards.

    Waiting belongs here rather than in a synchronous stop (plan §12.3 M2 refuses that: on the
    longest audio this repo measures the terminal decode is minutes, on a request a browser
    holds open), and here rather than in each driver, because the three paired drivers share
    exactly one client. These tests pin the four endings a meeting can have as an outside
    reader sees them: a pass that lands, a deployment that runs none, a pass that ends without
    a surface, and a pass that never ends.
    """

    def test_the_run_reports_the_terminal_surface_and_the_events_that_made_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace, summary = _run_terminal_replay(Path(tmp), finalizer=_terminal_finalizer())

        wait = _one_trace_record(self, trace, "terminal_finalization_wait")
        terminal = _one_trace_record(self, trace, "terminal")
        session = terminal["snapshot"]["session"]
        kinds = [
            record["event"]["kind"] for record in trace if record["kind"] == "service_event"
        ]

        self.assertEqual(wait["stop_finalization_status"], "running")
        self.assertEqual(wait["finalization_status"], "final")
        self.assertTrue(wait["waited"])
        self.assertEqual(wait["polls"], 2)
        self.assertEqual(session["finalization_status"], "final")
        self.assertEqual(session["text_revision_version"], wait["text_revision_version"])
        self.assertEqual(
            {segment["authority"] for segment in session["effective_transcript"]},
            {"terminal"},
        )
        self.assertEqual(summary["status"], "succeeded")
        self.assertEqual(summary["finalization_status"], "final")
        self.assertTrue(summary["finalization_waited"])
        for kind in (
            "terminal_finalization_started",
            "text_revision_applied",
            "terminal_finalization_completed",
            "session_tape_released",
        ):
            self.assertIn(kind, kinds)

    def test_a_deployment_that_runs_no_terminal_pass_is_not_waited_on(self):
        """`not_started` is an answer. A client that waited on it would wait every run."""

        with tempfile.TemporaryDirectory() as tmp:
            trace, summary = _run_terminal_replay(Path(tmp), finalizer=None)

        wait = _one_trace_record(self, trace, "terminal_finalization_wait")

        self.assertEqual(wait["stop_finalization_status"], "not_started")
        self.assertEqual(wait["finalization_status"], "not_started")
        self.assertFalse(wait["waited"])
        self.assertEqual(wait["polls"], 0)
        self.assertEqual(summary["finalization_status"], "not_started")
        self.assertFalse(summary["finalization_waited"])
        self.assertEqual(
            {
                segment["authority"]
                for segment in _one_trace_record(self, trace, "terminal")["snapshot"]["session"][
                    "effective_transcript"
                ]
            },
            {"rolling"},
        )

    def test_a_pass_that_ends_without_a_surface_is_an_answer_too(self):
        """No tape, no pass: `unavailable` reaches the artifact and the run still succeeds."""

        with tempfile.TemporaryDirectory() as tmp:
            trace, summary = _run_terminal_replay(
                Path(tmp), finalizer=_terminal_finalizer(), tape_bytes=None
            )

        wait = _one_trace_record(self, trace, "terminal_finalization_wait")

        self.assertEqual(wait["stop_finalization_status"], "unavailable")
        self.assertFalse(wait["waited"])
        self.assertEqual(summary["status"], "succeeded")
        self.assertEqual(summary["finalization_status"], "unavailable")

    def test_a_pass_that_never_answers_fails_the_run_by_name(self):
        """The deadline is the instrument's patience, and spending it is not a measurement.

        Writing the artifacts anyway would reproduce F1 with extra steps: the surface in them
        would be the rolling one under a run that called itself complete.
        """

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(live_service_replay.ServiceReplayFinalizationTimeout) as cm:
                _run_terminal_replay(
                    root,
                    finalizer=_terminal_finalizer(),
                    delay_polls=None,
                    finalization_deadline=2.0,
                )
            trace = _jsonl(root / "out/run-001/trace.jsonl")
            summary = json.loads((root / "out/run-001/summary.json").read_text(encoding="utf-8"))

        terminal = _one_trace_record(self, trace, "terminal")

        self.assertEqual(cm.exception.exit_code, 8)
        self.assertEqual(cm.exception.failure_kind, "finalization_timeout")
        self.assertIn("'running'", str(cm.exception))
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["failure_kind"], "finalization_timeout")
        self.assertEqual(terminal["status"], "failed")
        self.assertEqual(
            [record["kind"] for record in trace].count("terminal_finalization_wait"), 0
        )

    def test_a_non_positive_deadline_is_refused_before_any_audio_is_sent(self):
        service = RecordingService(
            _runtime(descriptor=_descriptor(), speech=(False,), session_ids=("session-1",))
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "audio.wav"
            _write_wav(audio, samples=400)
            with self.assertRaises(live_service_replay.ServiceReplayFailure):
                live_service_replay.run_service_replay(
                    service=service,
                    audio_path=audio,
                    out_dir=root / "out",
                    pace=1.0,
                    max_pacing_lag=0.5,
                    runs=1,
                    expect_revision="revision",
                    expect_provider_hash="a" * 64,
                    expect_config_hash="b" * 64,
                    finalization_deadline=0.0,
                )

        self.assertEqual(service.frame_sequences, [])


class ReplayReconstructorRoundTripTest(unittest.TestCase):
    """The replay client's reconstructors must be exact inverses of the service's `asdict`.

    Every measurement this campaign makes reads a replay artifact, so a field the client
    silently drops is a metric quietly computed on the wrong transcript -- `revised_transcript`
    and `label_revision_version` were dropped that way, and every replayed snapshot read as
    "never corrected". Equality alone is not enough of a guard: it only bites when the fixture
    varies the field, so `_assert_varies_from_defaults` fails the moment a new defaulted field
    arrives unset, which then forces the equality check to cover it too.
    """

    def test_service_snapshot_survives_json_round_trip_field_for_field(self):
        snapshot = _rich_service_snapshot()
        _assert_varies_from_defaults(self, snapshot)

        restored = live_service_replay._snapshot_from_dict(json.loads(json.dumps(snapshot.to_dict())))

        self.assertEqual(restored, snapshot)

    def test_event_and_frame_ack_survive_json_round_trip_field_for_field(self):
        event = _canonical_processed_event(seq=3, span_id=1, rtf=0.4)
        ack = FrameAck(
            sequence=2,
            start_sample=400,
            end_sample=800,
            accepted_samples=800,
            retained_samples=120,
            frozen_span_ids=(0, 1),
        )
        _assert_varies_from_defaults(self, event)
        _assert_varies_from_defaults(self, ack)

        restored_event = live_service_replay._event_from_dict(json.loads(json.dumps(event.to_dict())))
        restored_ack = live_service_replay._frame_ack_from_dict(json.loads(json.dumps(live_service_replay._jsonable(ack))))

        self.assertEqual(restored_event, event)
        self.assertEqual(restored_ack, ack)


def _rich_service_snapshot() -> LiveServiceSnapshot:
    """A snapshot whose every free field is off its default, so a dropped field cannot pass."""

    descriptor = replace(
        _descriptor(),
        bounds=LiveServiceBounds(
            max_frame_samples=LIVE_SAMPLE_RATE,
            max_queue_depth=8,
            max_retained_samples=4000,
            max_identity_speakers=2,
            max_events=128,
            hard_cap_samples=40000,
            stop_drain_deadline_seconds=2.5,
            max_tape_bytes=1920000,
        ),
        live_protocol=LiveV2Descriptor(
            capabilities=LiveV2Capabilities(
                lanes=False,
                binary=True,
                idempotent_frames=False,
                resumable=False,
            )
        ),
        engine_options={"speaker_windows": ["balanced"],
                        "default_speaker_window": "balanced"},
    )
    session = LiveSnapshot(
        status="closed",
        epoch=1,
        version=9,
        accepted_samples=40000,
        accounted_samples=40000,
        retained_samples=160,
        committed_samples=39840,
        committed_prefix_hash=_digest("prefix"),
        identity_snapshot=LiveIdentitySnapshot(
            version=2,
            canonical_speakers=("speaker-0001", "speaker-0002"),
            diagnostics=(("adopted", "speaker-0002"),),
        ),
        committed=(
            CanonicalCommit(
                span_id=0,
                start_sample=0,
                end_sample=39840,
                transcript="[0][S00]hello[2.49]",
                prefix_hash=_digest("commit"),
                identity_snapshot_version=2,
                revised_transcript="[0][S01]hello[2.49]",
                source_lanes=("system",),
            ),
        ),
        provisional=ProvisionalSuffix(
            generation=4,
            start_sample=39840,
            end_sample=40000,
            transcript="[0][S01]there[0.01]",
        ),
        next_frame_sequence=3,
        frozen_until_sample=39840,
        pending_span_ids=(1,),
        failure_reason="stop_drain_deadline",
        label_revision_version=7,
        text_revision_version=5,
        canonical_through_sample=32000,
        effective_transcript=(
            EffectiveTranscriptSegment(
                start_sample=0,
                end_sample=32000,
                text="hello there",
                canonical_speaker="speaker-0002",
                authority="rolling",
                source_lane="microphone",
            ),
            EffectiveTranscriptSegment(
                start_sample=32000,
                end_sample=39840,
                text="hello",
                canonical_speaker=None,
                authority="provisional",
                source_lane="system",
            ),
        ),
        finalization_status="running",
    )
    return LiveServiceSnapshot(
        draft=LiveDraft(3, 39840, 40000, "[0][S00]draft[0.01]"),
        draft_stats={"ticks": 3, "started": 2, "skipped": 1},
        identity_counts={"identities_born_count": 2, "album_admitted_count": 1, "provisional_only_count": 1, "abstention_count": 3},
        session_id="session-round-trip",
        descriptor=descriptor,
        session=session,
        pending_work_items=2,
        terminal_failure=LiveServiceFailureRecord(
            kind=LiveServiceFailureKind.RTF,
            code="rtf_bound_exceeded",
            message="canonical decode exceeded the real-time bound.",
            retryable=True,
            detail={"rtf": 1.4},
        ),
    )


# Fields the runtime pins to one legal value in `__post_init__`: a fixture cannot vary them,
# and a reconstructor that read the wrong one would raise rather than mis-measure.
_PINNED_FIELDS = frozenset(
    {
        ("LiveServiceSnapshot", "schema_version"),
        ("LiveDraft", "authority"),
        ("LiveServiceDescriptor", "schema_version"),
        ("LiveServiceDescriptor", "live_protocol_version"),
        ("LiveServiceDescriptor", "sample_rate"),
        ("LiveServiceDescriptor", "feature_enabled"),
        ("LiveV2Descriptor", "protocol"),
        ("LiveV2Descriptor", "min_protocol_version"),
        ("LiveV2Descriptor", "max_protocol_version"),
        ("LiveServiceEvent", "schema_version"),
    }
)


def _assert_varies_from_defaults(case: unittest.TestCase, instance: object, path: str = "") -> None:
    """Fail if any defaulted field of `instance` (or a nested dataclass) still holds its default."""

    label = type(instance).__name__
    for field_info in fields(instance):
        value = getattr(instance, field_info.name)
        where = f"{path}{label}.{field_info.name}"
        if (label, field_info.name) not in _PINNED_FIELDS:
            default = field_info.default
            if default is MISSING and field_info.default_factory is not MISSING:
                default = field_info.default_factory()
            if default is not MISSING:
                case.assertNotEqual(
                    value,
                    default,
                    f"{where} still holds its default; vary it so the round-trip check can see it.",
                )
        for nested in _nested_dataclasses(value):
            _assert_varies_from_defaults(case, nested, path=f"{where}.")


def _nested_dataclasses(value: object) -> list[object]:
    if is_dataclass(value) and not isinstance(value, type):
        return [value]
    if isinstance(value, (tuple, list)):
        return [item for item in value if is_dataclass(item) and not isinstance(item, type)]
    return []


def _canonical_processed_event(*, seq: int, span_id: int, rtf: float) -> LiveServiceEvent:
    return LiveServiceEvent(
        seq=seq,
        session_id="session-1",
        kind="canonical_processed",
        snapshot_version=seq,
        payload={
            "span_id": span_id,
            "canonical_decode_elapsed_sec": rtf,
            "frozen_span_sample_count": LIVE_SAMPLE_RATE,
            "frozen_span_duration_sec": 1.0,
            "canonical_decode_rtf": rtf,
        },
    )


def _event_with_payload(event: LiveServiceEvent, payload: dict) -> LiveServiceEvent:
    return LiveServiceEvent(
        seq=event.seq,
        session_id=event.session_id,
        kind=event.kind,
        snapshot_version=event.snapshot_version,
        payload=payload,
        schema_version=event.schema_version,
    )


def _digest(label: str) -> str:
    return hash_config({"label": label})


def _descriptor(*, frame_samples: int = 400, max_events: int = 128) -> LiveServiceDescriptor:
    return LiveServiceDescriptor(
        source_revision="eda5e69faf0e0251383029295f7e8875a2a1a4f6",
        provider_name="deterministic-fake",
        provider_revision="test-revision",
        provider_manifest_hash=_digest("provider"),
        config_hashes=LiveServiceConfigHashes.from_parts(
            endpoint_config={"min_speech_samples": 1, "min_silence_samples": 1},
            identity_config={"max_speakers": 2},
            decoder_config={"max_samples": 400},
        ),
        bounds=LiveServiceBounds(
            max_frame_samples=LIVE_SAMPLE_RATE,
            max_queue_depth=8,
            max_retained_samples=4000,
            max_identity_speakers=2,
            max_events=max_events,
        ),
        frame_samples=frame_samples,
    )


def _runtime(
    *,
    descriptor: LiveServiceDescriptor,
    speech: tuple[bool, ...],
    session_ids: tuple[str, ...],
    decoder: "RecordingDecoder | None" = None,
    identity: "PreparingIdentity | None" = None,
) -> LiveServiceRuntime:
    ids = iter(session_ids)
    return LiveServiceRuntime(
        descriptor=descriptor,
        endpoint_policy_factory=lambda: EndpointPolicy(
            EndpointPolicyConfig(min_speech_samples=1, min_silence_samples=1)
        ),
        speech_provider_factory=lambda: ScriptedSpeechProvider(speech),
        decoder_factory=lambda: decoder or RecordingDecoder(),
        identity_preparer_factory=lambda: identity or PreparingIdentity(),
        session_id_factory=lambda: next(ids),
    )


class ScriptedSpeechProvider:
    def __init__(self, speech: tuple[bool, ...]):
        self.speech = list(speech)

    def observe(self, *, frame: AudioFrame, start_sample: int, end_sample: int) -> tuple[SpeechObservation, ...]:
        del frame
        return (
            SpeechObservation(
                start_sample=start_sample,
                end_sample=end_sample,
                speech_present=self.speech.pop(0),
            ),
        )


class RecordingDecoder:
    max_samples = 4000

    def __init__(self, elapsed_sec: float | None = None):
        self.elapsed_sec = elapsed_sec

    def transcribe_pcm(self, *, span: FrozenSpan, pcm: bytes) -> InferenceTranscript:
        del span, pcm
        return InferenceTranscript("[0][S01]decoded[0.01]", elapsed_sec=self.elapsed_sec)


@dataclass
class PreparingIdentity:
    status: str = "prepared"
    reason: str | None = None
    # See the same knob in tests/test_live_service_runtime.py: a preparation built against
    # identity state the session has moved past is the remaining way a canonical submission
    # refuses, now that a non-`prepared` status publishes the span unattributed.
    stale_base_version: bool = False

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
            canonical_speakers=base_snapshot.canonical_speakers or ("speaker-0001",),
        )
        return LiveIdentityPreparation(
            span_id=span.id,
            epoch=span.epoch,
            start_sample=span.start_sample,
            end_sample=span.end_sample,
            base_snapshot_version=base_snapshot.version - 1 if self.stale_base_version else base_snapshot.version,
            proposed_snapshot=proposed,
            relabeled_transcript="[0][S01]stable[0.01]",
            status=self.status,
            reason=self.reason,
        )


class RecordingService(live_service_replay.InMemoryLiveReplayService):
    def __init__(self, runtime: LiveServiceRuntime):
        super().__init__(runtime)
        self.frame_sequences: list[int] = []
        self.abort_reasons: list[str] = []

    def accept_frame(self, session_id: str, frame: AudioFrame):
        self.frame_sequences.append(frame.sequence)
        return super().accept_frame(session_id, frame)

    async def abort(self, session_id: str, reason: str):
        self.abort_reasons.append(reason)
        return await super().abort(session_id, reason)


class AmbiguousOnceService(RecordingService):
    def accept_frame(self, session_id: str, frame: AudioFrame):
        self.frame_sequences.append(frame.sequence)
        raise live_service_replay.ServiceReplayTransportFailure("timeout after possible admission")


class CorruptingEventsService(live_service_replay.InMemoryLiveReplayService):
    def __init__(self, runtime: LiveServiceRuntime, mutate):
        super().__init__(runtime)
        self.mutate = mutate

    def events(self, session_id: str, since_seq: int = 0):
        events = []
        for event in super().events(session_id, since_seq=since_seq):
            if event.kind == "canonical_processed":
                payload = dict(event.payload)
                self.mutate(payload)
                event = _event_with_payload(event, payload)
            events.append(event)
        return tuple(events)


class EvictingEventsService(live_service_replay.InMemoryLiveReplayService):
    """A service whose retention window is narrower than the client's read cadence.

    The runtime bound cannot be pushed below one event, so this double stands in for the
    condition the bound produces at scale: by the time the client reads, the sequence it
    asked for is gone.  It exists to prove the replay client refuses that trace instead of
    writing a hole into it.
    """

    def __init__(self, runtime: LiveServiceRuntime, retain: int):
        super().__init__(runtime)
        self.retain = int(retain)

    def events(self, session_id: str, since_seq: int = 0):
        retained = super().events(session_id, since_seq=-1)[-self.retain :]
        return tuple(event for event in retained if event.seq >= since_seq)


class StopFailureService(RecordingService):
    def __init__(self, runtime: LiveServiceRuntime, failure: Exception):
        super().__init__(runtime)
        self.failure = failure

    async def stop(self, session_id: str, deadline: float):
        del session_id, deadline
        raise self.failure


class ScriptedClock:
    def __init__(self, values: list[float] | None = None):
        self.now = 0.0
        self.values = list(values or [])

    def monotonic(self) -> float:
        if self.values:
            return self.values.pop(0)
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class TerminalScriptedClock(ScriptedClock):
    """A replay clock that lets a scheduled terminal pass finish after `delay_polls` polls.

    The client's wait is a real loop over a real service; what a test cannot afford is its
    wall-clock cost or its timing luck. Driving the manual scheduler from `sleep` makes the
    pass land at an exact poll: the runtime is untouched and the interleaving is chosen, not
    raced. `delay_polls=None` is the pass that never answers.
    """

    def __init__(self, scheduler, *, delay_polls: int | None = 1):
        super().__init__()
        self.scheduler = scheduler
        self.delay_polls = delay_polls
        self.polls = 0

    def sleep(self, seconds: float) -> None:
        super().sleep(seconds)
        if not self.scheduler.pending:
            return
        self.polls += 1
        if self.delay_polls is not None and self.polls > self.delay_polls:
            self.scheduler.run_one()


def _terminal_finalizer(text: str = "[0][S01]the whole meeting[10]"):
    return TerminalTranscriptFinalizer(runner=WholeMeetingStub(text))


def _run_terminal_replay(
    root: Path,
    *,
    finalizer,
    tape_bytes: int | None = _TERMINAL_MEETING_SAMPLES * PCM16_BYTES_PER_SAMPLE,
    delay_polls: int | None = 1,
    finalization_deadline: float = 60.0,
) -> tuple[list[dict], dict]:
    """One replayed meeting through the runtime that has E4 wired, and its artifacts."""

    scheduler = _ManualTerminalScheduler()
    runtime, _ = _terminal_runtime(
        finalizer=finalizer, tape_bytes=tape_bytes, scheduler=scheduler
    )
    descriptor = runtime.descriptor
    clock = TerminalScriptedClock(scheduler, delay_polls=delay_polls)
    audio = root / "audio.wav"
    _write_wav(audio, samples=_TERMINAL_MEETING_SAMPLES, sample=b"\x11\x22")
    live_service_replay.run_service_replay(
        service=live_service_replay.InMemoryLiveReplayService(runtime),
        audio_path=audio,
        out_dir=root / "out",
        pace=1.0,
        max_pacing_lag=0.5,
        runs=1,
        expect_revision=descriptor.source_revision,
        expect_provider_hash=descriptor.provider_manifest_hash,
        expect_config_hash=descriptor.config_hashes.combined_config_hash,
        finalization_deadline=finalization_deadline,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    return (
        _jsonl(root / "out/run-001/trace.jsonl"),
        json.loads((root / "out/run-001/summary.json").read_text(encoding="utf-8")),
    )


def _one_trace_record(case: unittest.TestCase, trace: list[dict], kind: str) -> dict:
    records = [record for record in trace if record["kind"] == kind]
    case.assertEqual(len(records), 1, f"expected exactly one {kind} record")
    return records[0]


def _write_wav(path: Path, *, samples: int, sample: bytes = b"\0\0") -> None:
    """Replayed audio. `sample` is silence by default and audible where the run needs audio.

    Digital zeros are the cheapest thing to write and the only PCM most of these runs care
    about -- they measure pacing, framing and event order, never words. The terminal run is
    the exception: its last listener refuses to decode a meeting that never held a nonzero
    sample (`live_silence`), so a zero-filled meeting there would measure the refusal instead
    of the surface the test is about.
    """

    pcm = sample * samples
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(LIVE_SAMPLE_RATE)
        wav.writeframes(pcm)


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


if __name__ == "__main__":
    unittest.main()
