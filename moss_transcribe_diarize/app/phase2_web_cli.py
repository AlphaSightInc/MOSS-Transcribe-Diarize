"""The packaged Account HTTPS startup path.

This command is the complete product process surface: it builds only the Account app,
binds its canonical SQLite database, and hands the configured certificate to Uvicorn.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import replace
from pathlib import Path
from typing import Sequence

from .phase2 import DEFAULT_PHASE2_DATABASE_PATH, create_phase2_app
from .phase2_audio import DEFAULT_PHASE2_MEETING_AUDIO_ROOT
from .phase2_file import DEFAULT_PHASE2_FILE_WORK_ROOT
from .phase2_control import DEFAULT_PHASE2_CONTROL_SOCKET_PATH
from .gemini_lane_engine import GEMINI_MIC_WINDOW_SECONDS, GEMINI_MIC_WINDOW_STRIDE_SECONDS


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


GEMINI_WINDOW_LMAX_SECONDS = 90
GEMINI_WINDOW_STRIDE_SECONDS = 15
GEMINI_CONTINUITY_E = 0.46
GEMINI_CONTINUITY_W = 0.60
GEMINI_BIRTH_MIN_SECONDS = 2
GEMINI_EMBEDDING_INTERVAL_WORKERS = 3


def _serialize_gemini_lanes(system_diarizer, microphone_diarizer):
    from .gemini_lane_engine import SerializedDiarizer
    return SerializedDiarizer(system_diarizer), SerializedDiarizer(microphone_diarizer)


def _gemini_http_options():
    from google.genai import types
    return types.HttpOptions(timeout=120_000,
                             retry_options=types.HttpRetryOptions(attempts=1))


def _gemini_client(api_key: str | None):
    from .gemini_live_runtime import ApiKeyRequired
    if not api_key:
        # genai.Client(api_key=None) would fall back to a process env key (Q4: never).
        raise ApiKeyRequired()
    from google import genai
    client = genai.Client(api_key=api_key, http_options=_gemini_http_options())
    # Installed google-genai normalizes attempts=0/1 to one hidden retry.
    # Its generated interactions transport has no public zero-retry setting.
    # Keep WindowDiarizer as the sole, counted owner of physical REST retries.
    client.interactions.sdk_configuration.retry_config.strategy = "none"
    return client


def _transcription_diarizer(transcription, report_usage, *, gemini_client=None):
    """One lane's batch diarizer for the user's provider choice (I-2 `T`)."""
    if transcription["vendor"] == "openai_compatible":
        from .openai_compatible_provider import OpenAICompatibleDiarizer
        return OpenAICompatibleDiarizer(transcription["url"], transcription["model"],
                                        transcription["api_key"], report_usage)
    from .gemini_provider import WindowDiarizer
    return WindowDiarizer(gemini_client or _gemini_client(transcription["api_key"]),
                          report_usage, model=transcription["model"])


def _file_transcription_diarizer(transcription):
    if transcription is None:
        # Keys live only for the request that started the job; a restart cannot resume it.
        raise RuntimeError("File transcription settings are not kept across a restart.")
    return _transcription_diarizer(transcription, lambda **_usage: None)


def _build_gemini_file_runner(args: argparse.Namespace):
    from .file_identity_album import AlbumIdentityResolver
    from .gemini_file_runner import GeminiFileRunner
    from .live_provider_bundle import LiveProviderBundleConfig, _identity_encoder

    config = LiveProviderBundleConfig.from_manifest(args.live_provider_manifest)
    encoder = _identity_encoder(config, interval_workers=GEMINI_EMBEDDING_INTERVAL_WORKERS)
    return GeminiFileRunner(
        _file_transcription_diarizer,
        encoder,
        identity_resolver=AlbumIdentityResolver(config=config, encoder=encoder),
    )


def _build_gemini_live_runtime_factory(args: argparse.Namespace):
    """Clients are built per meeting from its own key; MOSS model/GPU construction stays outside."""
    from .gemini_hybrid_engine import (GrowingContextWindowScheduler,
                                       GeminiHybridEngine,
                                       WeSpeakerWindowEmbeddings)
    from .gemini_continuity_registry import ContinuityRegistry
    from .gemini_lane_engine import (AcousticEchoGuard, ConditionalMicrophoneTerminal, LaneGeminiEngine, LocalVoiceEvidence,
                                     VoicedLiveWords, MicrophoneWordGate,
                                     SystemWordLedger, CrossLaneVoiceEchoGuard,
                                     WebRtcSpeechDetector)
    from .gemini_live_words import GeminiLiveWordSource
    from .gemini_final_policy import FinalWordPolicy, WebRtcWordGate
    from .gemini_long_final import LongFinalStitcher
    from .gemini_live_runtime import (GeminiLiveRuntime, GEMINI_CONTEXT_SECONDS,
                                      GEMINI_DEFAULT_ENGINE_SETTINGS,
                                      GEMINI_DEFAULT_TRANSCRIPTION_MODEL, GEMINI_MAX_TAPE_BYTES,
                                      GEMINI_REFRESH_SECONDS, TRANSCRIPTION_VENDORS)
    from .gemini_provider import GeminiWord, TerminalTranscriber
    from .live_provider_bundle import LiveProviderBundleConfig, _bounds, _identity_encoder
    from .live_service_runtime import LiveServiceConfigHashes, LiveServiceDescriptor
    from .live_service_runtime import hash_config

    config = LiveProviderBundleConfig.from_manifest(args.live_provider_manifest)
    bounds = replace(_bounds(config.bounds_config),
                     max_tape_bytes=max(int(config.bounds_config["max_tape_bytes"]),
                                        GEMINI_MAX_TAPE_BYTES))
    encoder = _identity_encoder(config, interval_workers=GEMINI_EMBEDDING_INTERVAL_WORKERS)
    policy = {"model": "gemini-3.5-transcribe",
              "window_max_seconds": GEMINI_WINDOW_LMAX_SECONDS,
              "stride_seconds": GEMINI_WINDOW_STRIDE_SECONDS,
              "microphone_window_seconds": GEMINI_MIC_WINDOW_SECONDS,
              "microphone_stride_seconds": GEMINI_MIC_WINDOW_STRIDE_SECONDS,
              "microphone_window_activation": "new_voiced_audio_only",
              "system_preview_activation": "new_voiced_audio_only",
              "holdback_seconds": 0, "terminal_chunk_seconds": 900,
              "terminal_overlap_seconds": 30,
              "timestamp_repair": "P53-R2-annotation-order",
              "continuity_embedding_cosine": GEMINI_CONTINUITY_E,
              "within_window_cosine": GEMINI_CONTINUITY_W,
              "birth_min_seconds": GEMINI_BIRTH_MIN_SECONDS,
              "terminal_merge_cosine": 0.65, "terminal_converse_gap_seconds": 2,
              "word_gate": "webrtc-mode1-10ms-pad200ms",
              "capture_lanes": "system_and_microphone_diarized",
              "microphone_local_voice": "echo_return_median_plus6dB_vad3_0p4s_weight15_coverage0p8",
              "microphone_echo_guard": "text_acoustic_and_voice_cosine_0p60_overlap_400ms"}
    identity_policy = {
        "registry": "word-time-overlap-hungarian",
        "voiceprint": f"{encoder.spec.provider}:{encoder.spec.revision}",
        "voiceprint_state_sha": encoder.spec.state_sha256,
        "embedding_dimension": encoder.spec.embedding_dimension,
    }
    descriptor = LiveServiceDescriptor(
        source_revision=config.source_revision,
        provider_name="gemini-3.5-transcribe",
        provider_revision="hybrid-w3-mic-short-v9",
        provider_manifest_hash=hash_config({"gemini_policy": policy, "identity": identity_policy}),
        config_hashes=LiveServiceConfigHashes.from_parts(
            endpoint_config={"preview_model": "gemini-3.5-transcribe-live",
                             "preview_vad_silence_ms": 500, "preview_replay_seconds": 5},
            identity_config=identity_policy,
            decoder_config=policy,
        ),
        bounds=bounds,
        frame_samples=int(config.bounds_config.get("frame_samples", bounds.max_frame_samples)),
        engine_options={"transcription_vendors": list(TRANSCRIPTION_VENDORS),
                        "default_model": GEMINI_DEFAULT_TRANSCRIPTION_MODEL,
                        "refresh_seconds": dict(GEMINI_REFRESH_SECONDS),
                        "context_seconds": dict(GEMINI_CONTEXT_SECONDS),
                        "cleanup_after_stop": {"available": True, "default": True}},
    )

    def factory():
        def engine_factory(_sid, publish, report_usage, settings=None):
            settings = settings or GEMINI_DEFAULT_ENGINE_SETTINGS
            transcription = settings["transcription"]
            # Gemini: one client per meeting from the meeting's key (batch + instant words).
            client = (_gemini_client(transcription["api_key"])
                      if transcription["vendor"] == "gemini" else None)
            def lane_report(lane):
                def report(**usage):
                    report_usage(**{**usage, "kind": f"{lane}_{usage['kind']}"})
                return report
            system_report, mic_report = lane_report("system"), lane_report("microphone")
            system_diarizer, mic_diarizer = _serialize_gemini_lanes(
                _transcription_diarizer(transcription, system_report, gemini_client=client),
                _transcription_diarizer(transcription, mic_report, gemini_client=client))
            system_words = SystemWordLedger()
            voice_echo = CrossLaneVoiceEchoGuard(threshold=.60)
            system_embeddings = WeSpeakerWindowEmbeddings(encoder)
            mic_embeddings = WeSpeakerWindowEmbeddings(encoder)
            mic_registry = ContinuityRegistry(
                embedding_threshold=GEMINI_CONTINUITY_E,
                within_window_threshold=GEMINI_CONTINUITY_W,
                birth_min_seconds=GEMINI_BIRTH_MIN_SECONDS,
                id_prefix="local")
            system_gate = WebRtcWordGate()
            mic_gate = WebRtcWordGate()
            system_preview_detector = WebRtcSpeechDetector()
            system_batch_detector = WebRtcSpeechDetector()
            mic_preview_detector = WebRtcSpeechDetector()
            mic_batch_detector = WebRtcSpeechDetector()
            lane_engine = None
            acoustic_guard = AcousticEchoGuard(
                lambda start, end: lane_engine.lane_tape("system").read(
                    start_sample=start, end_sample=end))
            mic_word_gate = MicrophoneWordGate(
                mic_gate, system_words, acoustic_guard,
                lambda counts: mic_report(kind="gate", count_call=False, **counts),
                voice_guard=voice_echo, embedding_source=mic_embeddings,
                local_voice=LocalVoiceEvidence(acoustic_guard.system_read))
            system_terminal = TerminalTranscriber(
                system_diarizer, identity_policy=FinalWordPolicy(encoder),
                stitcher=LongFinalStitcher(encoder), report_usage=system_report,
                word_gate=system_gate, source_lane="system",
                voiced_audio=system_batch_detector)
            def mic_terminal_filter(words):
                mic_pcm = lane_engine.lane_tape("microphone").read()
                filtered = mic_word_gate.filter_terminal(
                    mic_pcm, words, system_terminal.last_words,
                    system_pcm16=lane_engine.lane_tape("system").read())
                vectors = mic_embeddings(mic_pcm, 0, filtered)
                mapping, _ = mic_registry.observe_window(0, filtered, vectors)
                return tuple(GeminiWord(word.text, mapping[word.speaker],
                                        word.start_sample, word.end_sample)
                             for word in filtered)
            def mic_witness_filter(cleanup, kept, witness, skip):
                return mic_word_gate.restore_witnessed_words(
                    lane_engine.lane_tape("microphone").read(), cleanup, kept, witness,
                    system_terminal.last_words, system_pcm16=lane_engine.lane_tape("system").read(),
                    skip=skip, local_speaker="local-0001")
            mic_terminal = TerminalTranscriber(
                mic_diarizer, diarize=True, identity_policy=FinalWordPolicy(encoder),
                word_gate=mic_gate, word_filter=mic_terminal_filter, witness_filter=mic_witness_filter,
                source_lane="microphone",
                report_usage=mic_report, voiced_audio=mic_batch_detector)
            def preview_words(report):
                # The instant-word model stays gemini-3.5-transcribe-live (gemini_live_words);
                # OpenAI-compatible meetings have none, so rolling windows publish all text.
                if client is not None:
                    return lambda: GeminiLiveWordSource(client, report)
                from .openai_compatible_provider import NoPreviewWords
                return NoPreviewWords
            system_source = VoicedLiveWords(preview_words(system_report),
                                            voiced_audio=system_preview_detector)
            mic_source = VoicedLiveWords(preview_words(mic_report),
                                         voiced_audio=mic_preview_detector)
            def system_factory(lane_publish):
                def observed_system_embeddings(pcm, start, words):
                    vectors = system_embeddings(pcm, start, words)
                    voice_echo.observe_system(words, vectors,
                                              frontier=start + len(pcm) // 2)
                    return vectors
                return GeminiHybridEngine(
                    lane_publish, word_source=system_source,
                    window_scheduler=GrowingContextWindowScheduler(
                        max_seconds=settings["context_seconds"],
                        stride_seconds=settings["refresh_seconds"]),
                    registry=ContinuityRegistry(
                        embedding_threshold=GEMINI_CONTINUITY_E,
                        within_window_threshold=GEMINI_CONTINUITY_W,
                        birth_min_seconds=GEMINI_BIRTH_MIN_SECONDS),
                    diarizer=system_diarizer,
                    terminal=system_terminal,
                    embedding_source=observed_system_embeddings,
                    encoder_spec=encoder.spec, word_gate=system_gate,
                    report_usage=system_report, source_lane="system",
                    voiced_audio=system_batch_detector,
                    word_observer=system_words.observe)
            def microphone_factory(lane_publish):
                return GeminiHybridEngine(
                    lane_publish, word_source=mic_source,
                    window_scheduler=GrowingContextWindowScheduler(
                        max_seconds=GEMINI_MIC_WINDOW_SECONDS,
                        stride_seconds=GEMINI_MIC_WINDOW_STRIDE_SECONDS),
                    registry=mic_registry, diarizer=mic_diarizer,
                    terminal=ConditionalMicrophoneTerminal(mic_source, mic_terminal),
                    embedding_source=mic_embeddings,
                    encoder_spec=encoder.spec,
                    word_gate=mic_word_gate,
                    report_usage=mic_report, source_lane="microphone",
                    voiced_audio=mic_batch_detector, diarize_windows=True)
            lane_engine = LaneGeminiEngine(
                publish, system_factory=system_factory,
                microphone_factory=microphone_factory,
                tape_root=Path(args.file_work_root).expanduser() / "gemini-lanes")
            return lane_engine
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
    from .phase2_llm import GeminiSummaryGenerator
    parse_upstreams(args.llm_upstreams)
    from .phase2_operator import configure_operator_journal

    configure_operator_journal()
    file_runner = (_build_file_runner(args) if args.live_engine == "moss"
                   else _build_gemini_file_runner(args))
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
        summary_generator=GeminiSummaryGenerator(),
        open_workspace=os.environ.get("MOSS_OPEN_WORKSPACE") == "1",
        replace_unmatched_credential=os.environ.get("MOSS_REPLACE_UNMATCHED_CREDENTIAL") == "1",
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
