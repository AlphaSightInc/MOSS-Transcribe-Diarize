"""THROWAWAY: exercise the headed instrument through a loopback candidate stack.

One command:
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \\
  /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python \\
  prototypes/headed-session/short_stack_run.py \\
  --output evidence/round4/headed-session/short-stack-run.json

The public CLI deliberately permits only a 300 s S9 run.  This calls its unchanged
internal runner for five seconds against create_phase2_app and the built candidate
frontend.  The one local decoder and terminal runner return fixed synthetic text;
there are zero provider/remote-decoder requests.  Thus a pass proves only the browser,
loopback HTTP, live-frame API, DOM observation, and cleanup path--not recognition or
per-word quality.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
from typing import Sequence
import wave

import uvicorn

from moss_transcribe_diarize.app.live_adapters import InferenceTranscript
from moss_transcribe_diarize.app.live_endpoint import (
    EndpointPolicy,
    EndpointPolicyConfig,
    SpeechObservation,
)
from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceBounds,
    LiveServiceConfigHashes,
    LiveServiceDescriptor,
    LiveServiceRuntime,
    hash_config,
)
from moss_transcribe_diarize.app.live_session import (
    LIVE_SAMPLE_RATE,
    AudioFrame,
    FrozenSpan,
    LiveIdentityPreparation,
    LiveIdentitySnapshot,
)
from moss_transcribe_diarize.app.live_transcript_convergence import TerminalTranscriptFinalizer
from moss_transcribe_diarize.app.phase2 import create_phase2_app
from tools.qualify.visible_word_headed import _run


SECONDS = 5.0
FRAME_SAMPLES = 8_000
SYNTHETIC_TRANSCRIPT = "synthetic headed probe"


class _Speech:
    def observe(
        self, *, frame: AudioFrame, start_sample: int, end_sample: int
    ) -> tuple[SpeechObservation, ...]:
        return (
            SpeechObservation(
                start_sample=start_sample,
                end_sample=end_sample,
                speech_present=any(frame.analysis_pcm or frame.pcm),
            ),
        )


class _Decoder:
    max_samples = FRAME_SAMPLES * 2

    def transcribe_pcm(self, *, span: FrozenSpan, pcm: bytes) -> InferenceTranscript:
        del pcm
        end = span.sample_count / LIVE_SAMPLE_RATE
        return InferenceTranscript(f"[0][S01]{SYNTHETIC_TRANSCRIPT}[{end:g}]")


@dataclass
class _Identity:
    def fork_lane(self) -> "_Identity":
        return _Identity()

    def prepare(
        self,
        *,
        span: FrozenSpan,
        pcm: bytes,
        transcript: str,
        base_snapshot: LiveIdentitySnapshot,
        allowed_speakers: tuple[str, ...] | None = None,
    ) -> LiveIdentityPreparation:
        del pcm, transcript, allowed_speakers
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
            relabeled_transcript=f"[0][S01]{SYNTHETIC_TRANSCRIPT}[{span.sample_count / LIVE_SAMPLE_RATE:g}]",
        )


class _WholeMeetingRunner:
    window_seconds = 150
    stride_seconds = 120

    def transcribe(self, audio_path: Path, **kwargs: object) -> object:
        del kwargs
        with wave.open(str(audio_path), "rb") as source:
            source.readframes(source.getnframes())
        return type(
            "SyntheticResult",
            (),
            {
                "text": f"[0][S01]{SYNTHETIC_TRANSCRIPT}[{SECONDS:g}]",
                "generated_tokens": 0,
                "prompt_len": 0,
                "window_count": 1,
                "completed_windows": 1,
                "possibly_truncated": False,
            },
        )()


def _runtime(tape_root: Path) -> LiveServiceRuntime:
    descriptor = LiveServiceDescriptor(
        source_revision="headed-session-synthetic",
        provider_name="synthetic-local",
        provider_revision="no-network",
        provider_manifest_hash=hash_config({"provider": "synthetic-local"}),
        config_hashes=LiveServiceConfigHashes.from_parts(
            endpoint_config={
                "min_speech_samples": 1,
                "min_silence_samples": 1,
                "hard_cap_samples": FRAME_SAMPLES * 2,
            },
            identity_config={"max_speakers": 2},
            decoder_config={"max_samples": FRAME_SAMPLES * 2},
        ),
        bounds=LiveServiceBounds(
            max_frame_samples=FRAME_SAMPLES,
            max_queue_depth=4,
            max_retained_samples=FRAME_SAMPLES * 4,
            max_identity_speakers=2,
            max_events=128,
            hard_cap_samples=FRAME_SAMPLES * 2,
            max_tape_bytes=FRAME_SAMPLES * 2 * 16,
        ),
        frame_samples=FRAME_SAMPLES,
    )
    return LiveServiceRuntime(
        descriptor=descriptor,
        endpoint_policy_factory=lambda: EndpointPolicy(
            EndpointPolicyConfig(
                min_speech_samples=1,
                min_silence_samples=1,
                hard_cap_samples=FRAME_SAMPLES * 2,
            )
        ),
        speech_provider_factory=_Speech,
        decoder_factory=_Decoder,
        rolling_decoder_factory=_Decoder,
        identity_preparer_factory=_Identity,
        terminal_finalizer=TerminalTranscriptFinalizer(runner=_WholeMeetingRunner()),
        tape_storage_root=tape_root,
    )


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _certificate(root: Path) -> tuple[Path, Path]:
    certificate = root / "certificate.pem"
    key = root / "private-key.pem"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-subj", "/CN=localhost",
            "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
            "-keyout", str(key), "-out", str(certificate),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return certificate, key


def _write_wav(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(LIVE_SAMPLE_RATE)
        target.writeframes(pcm)


def _start_server(app: object, certificate: Path, key: Path) -> tuple[uvicorn.Server, threading.Thread, str]:
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            app, host="127.0.0.1", port=port, log_level="error",
            ssl_certfile=str(certificate), ssl_keyfile=str(key), access_log=False,
        )
    )
    thread = threading.Thread(target=server.run)
    thread.start()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not server.started:
        if not thread.is_alive():
            raise RuntimeError("loopback candidate stack exited during startup")
        time.sleep(0.02)
    if not server.started:
        raise RuntimeError("loopback candidate stack did not start")
    return server, thread, f"https://127.0.0.1:{port}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("output must not already exist")
    with tempfile.TemporaryDirectory(prefix="moss-headed-session-") as temporary:
        root = Path(temporary)
        certificate, key = _certificate(root)
        system_wav, microphone_wav, reference = (
            root / "system.wav", root / "microphone.wav", root / "reference.jsonl"
        )
        _write_wav(system_wav, b"\x01\x00" * int(SECONDS * LIVE_SAMPLE_RATE))
        _write_wav(microphone_wav, b"\0\0" * int(SECONDS * LIVE_SAMPLE_RATE))
        reference.write_text(
            json.dumps({"id": "synthetic-0", "text": SYNTHETIC_TRANSCRIPT, "start": 0, "end": SECONDS}) + "\n"
        )
        app = create_phase2_app(
            database_path=root / "phase2.sqlite3",
            live_runtime_factory=lambda: _runtime(root / "live-tapes"),
            live_helper_lease_seconds=30,
            meeting_audio_root=root / "meeting-audio",
        )
        try:
            server, thread, base = _start_server(app, certificate, key)
        except RuntimeError as exc:
            receipt = {
                "schema": "moss-headed-session-short-stack.v1",
                "short_seconds": SECONDS,
                "decoder_requests_remote": 0,
                "provider_requests": 0,
                "microphone_opened": False,
                "audio_playback": False,
                "synthetic_local_decoder": True,
                "outcome": "BLOCKED-ON-RUNTIME",
                "failure_type": type(exc).__name__,
                "failure": str(exc),
                "startup_error": (
                    f"Refusing SQLite runtime {sqlite3.sqlite_version}; exactly 3.53.4 is required."
                ),
            }
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(receipt, indent=2) + "\n")
            print(json.dumps(receipt, sort_keys=True), flush=True)
            return 1
        try:
            result = asyncio.run(
                _run(
                    argparse.Namespace(
                        base=base,
                        system_wav=system_wav,
                        microphone_wav=microphone_wav,
                        reference=reference,
                        output=args.output,
                        seconds=SECONDS,
                        poll_seconds=0.1,
                        terminal_timeout=10.0,
                    )
                )
            )
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            if thread.is_alive():
                raise RuntimeError("loopback candidate stack did not stop")
    receipt = {
        "schema": "moss-headed-session-short-stack.v1",
        "short_seconds": SECONDS,
        "decoder_requests_remote": 0,
        "provider_requests": 0,
        "microphone_opened": False,
        "audio_playback": False,
        "synthetic_local_decoder": True,
        "instrument": result,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({
        "meeting_status": result["meeting_status"],
        "finalization_status": result["finalization_status"],
        "dom_state_changes": result["dom_state_changes"],
        "reference_words": result["reference_words"],
        "remote_decoder_requests": 0,
    }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
