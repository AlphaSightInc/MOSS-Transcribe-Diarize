from __future__ import annotations

import importlib.util
import json
import socket
import tempfile
import threading
import time
import unittest
import wave
from dataclasses import dataclass
from pathlib import Path

from moss_transcribe_diarize import live_service_replay
from moss_transcribe_diarize.app.live_adapters import InferenceTranscript
from moss_transcribe_diarize.app.live_endpoint import EndpointPolicy, EndpointPolicyConfig, SpeechObservation
from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceBounds,
    LiveServiceConfigHashes,
    LiveServiceDescriptor,
    LiveServiceEvent,
    LiveServiceFailureKind,
    LiveServiceIdentityCommitFailure,
    LiveServiceProviderConfigFailure,
    LiveServiceRtfFailure,
    LiveServiceRuntime,
    hash_config,
)
from moss_transcribe_diarize.app.live_session import (
    AudioFrame,
    FrozenSpan,
    LIVE_SAMPLE_RATE,
    LiveIdentityPreparation,
    LiveIdentitySnapshot,
)


UVICORN_AVAILABLE = importlib.util.find_spec("uvicorn") is not None


class LiveServiceReplayContractTest(unittest.TestCase):
    def test_help_shape_parses_service_backed_flags(self):
        with self.assertRaises(SystemExit) as cm:
            live_service_replay.parse_args(["--help"])

        self.assertEqual(cm.exception.code, 0)

    def test_required_cli_flags_are_separate_from_offline_manifest_replay(self):
        args = live_service_replay.parse_args(
            [
                "--base-url",
                "http://127.0.0.1:7860",
                "--audio",
                "audio.wav",
                "--out-dir",
                "runs/live-service-replay",
                "--pace",
                "1.0",
                "--max-pacing-lag",
                "0.25",
                "--runs",
                "3",
                "--expect-revision",
                "revision",
                "--expect-provider-hash",
                "a" * 64,
                "--expect-config-hash",
                "b" * 64,
            ]
        )

        self.assertEqual(args.base_url, "http://127.0.0.1:7860")
        self.assertEqual(args.audio, "audio.wav")
        self.assertEqual(args.runs, 3)
        self.assertEqual(args.expect_provider_hash, "a" * 64)

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
                identity=PreparingIdentity(status="abstain", reason="ambiguous_identity"),
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

    def test_invalid_canonical_decode_rtf_event_payloads_fail_closed(self):
        cases = {
            "missing_elapsed": lambda payload: payload.pop("canonical_decode_elapsed_sec"),
            "negative_elapsed": lambda payload: payload.update({"canonical_decode_elapsed_sec": -0.1}),
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

    @unittest.skipUnless(UVICORN_AVAILABLE, "uvicorn is not installed")
    def test_http_adapter_crosses_real_loopback_live_routes(self):
        from moss_transcribe_diarize.app.server import create_app
        import uvicorn

        descriptor = _descriptor(frame_samples=400)
        app = create_app(
            model_path="fake-model",
            runs_dir=tempfile.mkdtemp(),
            live_enabled=True,
            live_runtime_factory=lambda: _runtime(
                descriptor=descriptor,
                speech=(True, False),
                session_ids=("http-session",),
                decoder=RecordingDecoder(elapsed_sec=0.01),
            ),
        )
        port = _free_port()
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="critical"))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 5.0
            while not server.started and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(server.started)

            service = live_service_replay.HttpLiveReplayService(base_url=f"http://127.0.0.1:{port}")
            created = service.create()
            result = service.accept_frame(
                created.session_id,
                AudioFrame(sequence=0, pcm=b"\0\0" * 400, sample_count=400),
            )
            events = service.events(created.session_id, since_seq=0)
            filtered_events = service.events(created.session_id, since_seq=1)
            service.accept_frame(
                created.session_id,
                AudioFrame(sequence=1, pcm=b"\0\0" * 400, sample_count=400),
            )
            deadline = time.monotonic() + 5.0
            processed = []
            while time.monotonic() < deadline:
                processed = [event for event in service.events(created.session_id) if event.kind == "canonical_processed"]
                if processed:
                    break
                time.sleep(0.01)

            self.assertEqual(created.session_id, "http-session")
            self.assertEqual(result.ack.accepted_samples, 400)
            self.assertEqual(events[0].kind, "session_created")
            self.assertEqual([event.seq for event in filtered_events], [1])
            self.assertEqual(filtered_events[0].kind, "frame_accepted")
            self.assertTrue(processed)
            self.assertEqual(processed[0].payload["canonical_decode_elapsed_sec"], 0.01)
            self.assertEqual(processed[0].payload["frozen_span_sample_count"], 400)
            self.assertEqual(processed[0].payload["frozen_span_duration_sec"], 400 / LIVE_SAMPLE_RATE)
            self.assertAlmostEqual(processed[0].payload["canonical_decode_rtf"], 0.4)
        finally:
            server.should_exit = True
            thread.join(timeout=5)


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


def _descriptor(*, frame_samples: int = 400) -> LiveServiceDescriptor:
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
            max_events=128,
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
            base_snapshot_version=base_snapshot.version,
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


def _write_wav(path: Path, *, samples: int) -> None:
    pcm = b"\0\0" * samples
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(LIVE_SAMPLE_RATE)
        wav.writeframes(pcm)


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


if __name__ == "__main__":
    unittest.main()
