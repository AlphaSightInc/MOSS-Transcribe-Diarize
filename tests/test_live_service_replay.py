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
    LiveServiceFailureKind,
    LiveServiceProviderConfigFailure,
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

    def test_in_memory_paced_runner_uses_descriptor_frames_and_final_short_frame(self):
        descriptor = _descriptor(frame_samples=400)
        service = live_service_replay.InMemoryLiveReplayService(
            _runtime(descriptor=descriptor, speech=(False, False, False), session_ids=("session-1",))
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
            ["terminal_outcome", "frame_sequence", "sample_accounting"],
        )
        self.assertTrue(evaluator[-1]["exact_accounting"])

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
                speech=(False,),
                session_ids=("http-session",),
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

            self.assertEqual(created.session_id, "http-session")
            self.assertEqual(result.ack.accepted_samples, 400)
            self.assertEqual(events[0].kind, "session_created")
        finally:
            server.should_exit = True
            thread.join(timeout=5)

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
) -> LiveServiceRuntime:
    ids = iter(session_ids)
    return LiveServiceRuntime(
        descriptor=descriptor,
        endpoint_policy_factory=lambda: EndpointPolicy(
            EndpointPolicyConfig(min_speech_samples=1, min_silence_samples=1)
        ),
        speech_provider_factory=lambda: ScriptedSpeechProvider(speech),
        decoder_factory=lambda: RecordingDecoder(),
        identity_preparer_factory=lambda: PreparingIdentity(),
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

    def transcribe_pcm(self, *, span: FrozenSpan, pcm: bytes) -> InferenceTranscript:
        del span, pcm
        return InferenceTranscript("[0][S01]decoded[0.01]")


@dataclass
class PreparingIdentity:
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
