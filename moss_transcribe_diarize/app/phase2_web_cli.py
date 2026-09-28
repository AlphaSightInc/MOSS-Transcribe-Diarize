"""The packaged Account HTTPS startup path.

This command is the complete product process surface: it builds only the Account app,
binds its canonical SQLite database, and hands the configured certificate to Uvicorn.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import threading
from dataclasses import replace
from pathlib import Path
from typing import Sequence

from .phase2 import DEFAULT_PHASE2_DATABASE_PATH, create_phase2_app
from .phase2_audio import DEFAULT_PHASE2_MEETING_AUDIO_ROOT
from .phase2_file import DEFAULT_PHASE2_FILE_WORK_ROOT
from .phase2_control import DEFAULT_PHASE2_CONTROL_SOCKET_PATH


DEFAULT_MODEL = Path(__file__).resolve().parents[2] / "pretrained" / "moss-transcribe-diarize"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the MOSS Phase-2 Account web app over HTTPS.")
    parser.add_argument(
        "--database",
        default=str(DEFAULT_PHASE2_DATABASE_PATH),
        help="The Phase-2 SQLite database path (defaults to the product database).",
    )
    parser.add_argument(
        "--control-socket",
        default=str(DEFAULT_PHASE2_CONTROL_SOCKET_PATH),
        help="Mode-0600 host-local Account control socket.",
    )
    parser.add_argument("--tls-certfile", required=True)
    parser.add_argument("--tls-keyfile", required=True)
    parser.add_argument("--backend", choices=["hf", "vllm"], default="hf")
    parser.add_argument("--live-engine", choices=["moss", "gemini"], default="moss",
                        help="Live transcription engine; Gemini requires the measured provider adapter.")
    parser.add_argument("--model", default=str(DEFAULT_MODEL))
    parser.add_argument("--vllm-base-url")
    parser.add_argument("--vllm-model")
    parser.add_argument("--vllm-api-key", default="EMPTY")
    parser.add_argument("--vllm-timeout", type=float, default=600.0)
    parser.add_argument("--file-identity", choices=["album", "legacy"], default="album",
                        help="File cross-window identity; legacy is the one-release fallback.")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--dtype", default="bf16")
    parser.add_argument(
        "--file-work-root",
        default=str(DEFAULT_PHASE2_FILE_WORK_ROOT),
        help="Dedicated transient directory named file-work.",
    )
    parser.add_argument(
        "--meeting-audio-root",
        default=str(DEFAULT_PHASE2_MEETING_AUDIO_ROOT),
        help="Owner-partitioned durable Meeting MP3 root.",
    )
    parser.add_argument("--prompt")
    parser.add_argument("--max-len", type=int, default=131072)
    parser.add_argument("--max-new-tokens", type=int, default=2048)
    parser.add_argument("--decoding", choices=["greedy", "sample"], default="greedy")
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument(
        "--live-provider-manifest",
        required=True,
        help="Offline production Live provider manifest.",
    )
    parser.add_argument(
        "--live-helper-lease-seconds",
        required=True,
        type=float,
        help="Positive capture heartbeat lease; expiry interrupts the Live Meeting.",
    )
    parser.add_argument("--live-draft-lane-seconds", type=float, default=None,
                        help="Optional reader-only draft cadence; omitted means off.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=7861)
    parser.add_argument("--llm-upstreams", default=os.environ.get("MOSS_LLM_UPSTREAMS", ""),
                        help="JSON list of key-less tailnet LLM upstreams; defaults to MOSS_LLM_UPSTREAMS.")
    return parser.parse_args(argv)


def _build_file_runner(args: argparse.Namespace):
    # Keep model imports out of argument/help and admin paths. The runner crosses into Phase 2
    # only as the owner-bound File-Meeting inference seam.
    from .runner_composition import build_file_runner

    return build_file_runner(
        model_path=Path(args.model).expanduser(),
        device=args.device,
        dtype=args.dtype,
        backend=args.backend,
        vllm_base_url=args.vllm_base_url,
        vllm_model=args.vllm_model,
        vllm_api_key=args.vllm_api_key,
        vllm_timeout=args.vllm_timeout,
        file_identity=args.file_identity,
        identity_manifest=args.live_provider_manifest,
        inference_scheduler=getattr(args, "_inference_scheduler", None),
    )


def _build_live_runtime_factory(args: argparse.Namespace, file_runner: object):
    if args.live_helper_lease_seconds <= 0:
        raise SystemExit("--live-helper-lease-seconds must be positive.")
    if getattr(args, "live_engine", "moss") == "gemini":
        return _build_gemini_live_runtime_factory(args)
    from .live_provider_bundle import LiveProviderBundleConfig, build_live_runtime_factory
    from .runner_composition import LazyLiveRunner, build_terminal_finalizer

    config = LiveProviderBundleConfig.from_manifest(args.live_provider_manifest)
    live_runner = LazyLiveRunner(
        model_path=args.model,
        device=args.device,
        dtype=args.dtype,
        backend=args.backend,
        vllm_base_url=args.vllm_base_url,
        vllm_model=args.vllm_model,
        vllm_api_key=args.vllm_api_key,
        vllm_timeout=args.vllm_timeout,
        inference_scheduler=getattr(args, "_inference_scheduler", None),
    )
    return build_live_runtime_factory(
        config,
        live_runner,
        tape_storage_root=Path(args.file_work_root).expanduser() / "live-tapes",
        draft_lane_seconds=getattr(args, "live_draft_lane_seconds", None),
        terminal_finalizer=build_terminal_finalizer(
            runner=file_runner,
            prompt=args.prompt,
            max_length=args.max_len,
            max_new_tokens=args.max_new_tokens,
            decoding=args.decoding,
            temperature=args.temperature,
            max_length_cap=args.max_len if args.backend == "vllm" else None,
        ),
    )


GEMINI_WINDOW_LMAX_SECONDS = 60
GEMINI_WINDOW_STRIDE_SECONDS = 10
GEMINI_CONTINUITY_E = 0.46
GEMINI_CONTINUITY_W = 0.60
GEMINI_BIRTH_MIN_SECONDS = 2


def _build_gemini_live_runtime_factory(args: argparse.Namespace):
    """Load the provider key only here; MOSS model/GPU construction stays outside this path."""
    from google import genai
    from google.genai import types
    from .gemini_hybrid_engine import (GrowingContextWindowScheduler,
                                       GeminiHybridEngine,
                                       SingleMicrophoneRegistry, WeSpeakerWindowEmbeddings)
    from .gemini_continuity_registry import ContinuityRegistry
    from .gemini_lane_engine import (ConditionalMicrophoneTerminal, LaneGeminiEngine,
                                     LazyMicrophoneWords, MicrophoneWordGate,
                                     SerializedDiarizer, SystemWordLedger,
                                     TextEchoGuard, WebRtcSpeechDetector)
    from .gemini_live_words import GeminiLiveWordSource
    from .gemini_final_policy import FinalWordPolicy, WebRtcWordGate
    from .gemini_live_runtime import GeminiLiveRuntime
    from .gemini_provider import WindowDiarizer, TerminalTranscriber
    from .live_provider_bundle import LiveProviderBundleConfig, _bounds, _identity_encoder
    from .live_service_runtime import LiveServiceConfigHashes, LiveServiceDescriptor
    from .live_service_runtime import hash_config

    key = None
    key_path = Path(__file__).resolve().parents[2] / ".env.local"
    if key_path.exists():
        for line in key_path.read_text().splitlines():
            if line.startswith("GEMINI_API_KEY="):
                key = line.partition("=")[2].strip()
                break
    key = key or os.environ.get("MOSS_GEMINI_API_KEY")
    if not key:
        raise SystemExit("Gemini key missing from .env.local or MOSS_GEMINI_API_KEY")
    config = LiveProviderBundleConfig.from_manifest(args.live_provider_manifest)
    bounds = replace(_bounds(config.bounds_config),
                     max_tape_bytes=max(int(config.bounds_config["max_tape_bytes"]),
                                        60 * 60 * 16_000 * 2))
    encoder = _identity_encoder(config)
    policy = {"model": "gemini-3.5-transcribe",
              "window_max_seconds": GEMINI_WINDOW_LMAX_SECONDS,
              "stride_seconds": GEMINI_WINDOW_STRIDE_SECONDS,
              "holdback_seconds": 0, "terminal_chunk_seconds": 1800,
              "continuity_embedding_cosine": GEMINI_CONTINUITY_E,
              "within_window_cosine": GEMINI_CONTINUITY_W,
              "birth_min_seconds": GEMINI_BIRTH_MIN_SECONDS,
              "terminal_merge_cosine": 0.65, "terminal_converse_gap_seconds": 2,
              "word_gate": "webrtc-mode1-10ms-pad200ms",
              "capture_lanes": "system_diarized_microphone_single_speaker",
              "microphone_echo_guard": "exact_normalized_token_midpoint_1p5s"}
    identity_policy = {
        "registry": "word-time-overlap-hungarian",
        "voiceprint": f"{encoder.spec.provider}:{encoder.spec.revision}",
        "voiceprint_state_sha": encoder.spec.state_sha256,
        "embedding_dimension": encoder.spec.embedding_dimension,
    }
    descriptor = LiveServiceDescriptor(
        source_revision=config.source_revision,
        provider_name="gemini-3.5-transcribe",
        provider_revision="hybrid-w3-continuity-v5",
        provider_manifest_hash=hash_config({"gemini_policy": policy, "identity": identity_policy}),
        config_hashes=LiveServiceConfigHashes.from_parts(
            endpoint_config={"preview_model": "gemini-3.5-transcribe-live",
                             "preview_vad_silence_ms": 500, "preview_replay_seconds": 5},
            identity_config=identity_policy,
            decoder_config=policy,
        ),
        bounds=bounds,
        frame_samples=int(config.bounds_config.get("frame_samples", bounds.max_frame_samples)),
    )
    client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=120_000))

    def factory():
        def engine_factory(_sid, publish, report_usage):
            def lane_report(lane):
                def report(**usage):
                    report_usage(**{**usage, "kind": f"{lane}_{usage['kind']}"})
                return report
            system_report, mic_report = lane_report("system"), lane_report("microphone")
            batch_lock = threading.Lock()
            system_diarizer = SerializedDiarizer(WindowDiarizer(client, system_report), batch_lock)
            mic_diarizer = SerializedDiarizer(WindowDiarizer(client, mic_report), batch_lock)
            system_words = SystemWordLedger()
            system_gate = WebRtcWordGate()
            mic_gate = WebRtcWordGate()
            speech_detector = WebRtcSpeechDetector()
            echo_guard = TextEchoGuard()
            system_terminal = TerminalTranscriber(
                system_diarizer, identity_policy=FinalWordPolicy(encoder),
                word_gate=system_gate, source_lane="system")
            mic_terminal = TerminalTranscriber(
                mic_diarizer, diarize=False, word_gate=mic_gate,
                word_filter=lambda words: echo_guard.filter(words, system_terminal.last_words),
                source_lane="microphone", fixed_speaker="speaker-microphone")
            mic_source = LazyMicrophoneWords(
                lambda: GeminiLiveWordSource(client, mic_report),
                voiced_audio=speech_detector)
            def system_factory(lane_publish):
                return GeminiHybridEngine(
                    lane_publish, word_source=GeminiLiveWordSource(client, system_report),
                    window_scheduler=GrowingContextWindowScheduler(
                        max_seconds=GEMINI_WINDOW_LMAX_SECONDS,
                        stride_seconds=GEMINI_WINDOW_STRIDE_SECONDS),
                    registry=ContinuityRegistry(
                        embedding_threshold=GEMINI_CONTINUITY_E,
                        within_window_threshold=GEMINI_CONTINUITY_W,
                        birth_min_seconds=GEMINI_BIRTH_MIN_SECONDS),
                    diarizer=system_diarizer,
                    terminal=system_terminal,
                    embedding_source=WeSpeakerWindowEmbeddings(encoder),
                    encoder_spec=encoder.spec, word_gate=system_gate,
                    report_usage=system_report, source_lane="system",
                    word_observer=system_words.observe)
            def microphone_factory(lane_publish):
                return GeminiHybridEngine(
                    lane_publish, word_source=mic_source,
                    window_scheduler=GrowingContextWindowScheduler(
                        max_seconds=GEMINI_WINDOW_LMAX_SECONDS,
                        stride_seconds=GEMINI_WINDOW_STRIDE_SECONDS),
                    registry=SingleMicrophoneRegistry(), diarizer=mic_diarizer,
                    terminal=ConditionalMicrophoneTerminal(mic_source, mic_terminal),
                    embedding_source=WeSpeakerWindowEmbeddings(encoder),
                    encoder_spec=encoder.spec,
                    word_gate=MicrophoneWordGate(mic_gate, system_words),
                    report_usage=mic_report, source_lane="microphone",
                    voiced_audio=speech_detector, diarize_windows=False)
            return LaneGeminiEngine(
                publish, system_factory=system_factory,
                microphone_factory=microphone_factory,
                tape_root=Path(args.file_work_root).expanduser() / "gemini-lanes")
        return GeminiLiveRuntime(
            descriptor=descriptor, engine_factory=engine_factory,
            tape_storage_root=Path(args.file_work_root).expanduser() / "live-tapes",
            voiceprint_encoder=encoder,
        )
    return factory


def main(argv: Sequence[str] | None = None) -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit("Install uvicorn to run mtd-phase2-web.") from exc

    args = parse_args(argv)
    if args.live_engine == "moss":
        from .inference_scheduler import InferenceDispatchScheduler
        args._inference_scheduler = InferenceDispatchScheduler(max_calls=2, max_background_calls=1)
    else:
        args._inference_scheduler = None
    from .phase2_llm import parse_upstreams
    parse_upstreams(args.llm_upstreams)
    from .phase2_operator import configure_operator_journal

    configure_operator_journal()
    file_runner = _build_file_runner(args) if args.live_engine == "moss" else None
    live_runtime_factory = _build_live_runtime_factory(args, file_runner)
    app = create_phase2_app(
        database_path=Path(args.database).expanduser(),
        file_runner=file_runner,
        file_work_root=Path(args.file_work_root).expanduser(),
        meeting_audio_root=Path(args.meeting_audio_root).expanduser(),
        file_inference_options={
            "prompt": args.prompt,
            "max_length": args.max_len,
            "max_new_tokens": args.max_new_tokens,
            "decoding": args.decoding,
            "temperature": args.temperature,
        },
        live_runtime_factory=live_runtime_factory,
        live_helper_lease_seconds=args.live_helper_lease_seconds,
        control_socket_path=Path(args.control_socket).expanduser(),
        llm_upstreams=args.llm_upstreams,
        open_workspace=os.environ.get("MOSS_OPEN_WORKSPACE") == "1",
        inference_scheduler=args._inference_scheduler,
    )
    from .tls_reload import serve_with_certificate_reload

    config = uvicorn.Config(
        app,
        host=args.host,
        port=args.port,
        ssl_certfile=str(Path(args.tls_certfile).expanduser()),
        ssl_keyfile=str(Path(args.tls_keyfile).expanduser()),
        proxy_headers=False,
        access_log=False,
    )
    asyncio.run(serve_with_certificate_reload(config), loop_factory=config.get_loop_factory())


if __name__ == "__main__":
    main()
