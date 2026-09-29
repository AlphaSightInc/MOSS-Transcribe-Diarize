"""Replay cached real long60 Gemini windows through the integration live engine; no provider client."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import traceback
import wave

from moss_transcribe_diarize.app import gemini_live_runtime as runtime_module
from moss_transcribe_diarize.app import gemini_hybrid_engine as hybrid_module
from moss_transcribe_diarize.app import gemini_lane_engine as lane_module
from moss_transcribe_diarize.app import gemini_provider as provider_module
from moss_transcribe_diarize.app.gemini_continuity_registry import ContinuityRegistry
from moss_transcribe_diarize.app.gemini_final_policy import WebRtcWordGate
from moss_transcribe_diarize.app.gemini_live_runtime import GeminiLiveRuntime, GeminiRolling
from moss_transcribe_diarize.app.gemini_hybrid_engine import GeminiHybridEngine, GrowingContextWindowScheduler, WeSpeakerWindowEmbeddings
from moss_transcribe_diarize.app.gemini_lane_engine import LaneGeminiEngine, WebRtcSpeechDetector
from moss_transcribe_diarize.app.gemini_provider import GeminiWords, parse_words, repair_word_timestamps
from moss_transcribe_diarize.app.live_provider_bundle import LiveProviderBundleConfig, _identity_encoder
from moss_transcribe_diarize.app.live_service_runtime import LiveServiceBounds, LiveServiceConfigHashes, LiveServiceDescriptor
from moss_transcribe_diarize.app.live_session import AudioFrame

RATE = 16000
MODEL = "gemini-3.5-transcribe"
CONFIG = {"transcription_config": {"mode": {"type": "verbatim", "diarization_mode": "speaker", "timestamp_granularities": ["word"]}}}
INTEGRATION = Path("/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-r2-int")
CACHE = Path("prototypes/gemini-live/.cache")
AUDIO = CACHE / "long60/audio.wav"
MANIFEST = Path.home() / ".local/share/moss-transcribe-diarize/live/live-provider-manifest.json"


class Trace:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self.events = 0
        self.stream = path.open("w", encoding="utf-8")

    def put(self, kind: str, **fields):
        row = {"event": self.events, "monotonic_s": round(time.monotonic(), 6), "kind": kind, **fields}
        with self.lock:
            row["event"] = self.events
            self.events += 1
            self.stream.write(json.dumps(row, sort_keys=True) + "\n")
            self.stream.flush()

    def close(self):
        self.stream.close()


def cache_path(pcm: bytes) -> Path:
    key = hashlib.sha256(provider_module._wav(pcm) + json.dumps([MODEL, CONFIG], sort_keys=True).encode()).hexdigest()
    return CACHE / key[:2] / f"{key}.json"


def preflight() -> tuple[int, int]:
    hits = misses = 0
    with wave.open(str(AUDIO), "rb") as source:
        for end in range(15 * RATE, source.getnframes() + 1, 15 * RATE):
            start = max(0, end - 90 * RATE)
            source.setpos(start)
            path = cache_path(source.readframes(end - start))
            if path.is_file():
                hits += 1
            else:
                misses += 1
    return hits, misses


class CachedDiarizer:
    def __init__(self, trace: Trace, lane: str):
        self.trace, self.lane, self.calls = trace, lane, 0

    def diarize(self, pcm: bytes, *, deadline: float, kind: str, diarize: bool = True) -> GeminiWords:
        self.calls += 1
        path = cache_path(pcm)
        self.trace.put("decode_request", lane=self.lane, call=self.calls,
                       audio_s=len(pcm) / (2 * RATE), key=path.stem, cached=path.is_file())
        if not path.is_file():
            raise RuntimeError(f"CACHE_MISS lane={self.lane} call={self.calls} key={path.stem}")
        raw = json.loads(path.read_text(encoding="utf-8"))["response"]
        parsed = parse_words(raw, audio_samples=len(pcm) // 2)
        words, repaired = repair_word_timestamps(parsed.words, len(pcm) // 2)
        self.trace.put("decode_result", lane=self.lane, call=self.calls,
                       words=len(words), repaired=repaired, clamped=parsed.clamped, dropped=parsed.dropped)
        return GeminiWords(words, parsed.clamped, parsed.dropped)


class NoopWords:
    def bind(self, callback):
        self.callback = callback

    def push_audio(self, start_sample: int, pcm: bytes):
        pass

    def close(self):
        pass


class UnusedTerminal:
    def transcribe(self, tape):
        raise RuntimeError("terminal transcription is outside S1 cache probe")


class LoggedRegistry(ContinuityRegistry):
    def __init__(self, trace: Trace, lane: str, **options):
        super().__init__(**options)
        self.trace, self.lane = trace, lane

    def observe_window(self, window_start_s, words, embeddings=None, **options):
        try:
            mapping, relabels = super().observe_window(window_start_s, words, embeddings, **options)
        except Exception as exc:
            self.trace.put("registry_exception", lane=self.lane, window_start_s=window_start_s,
                           words=len(words), error=repr(exc), traceback=traceback.format_exc())
            raise
        self.trace.put("registry_result", lane=self.lane, window_start_s=window_start_s,
                       words=len(words), embeddings=sorted((embeddings or {}).keys()),
                       mapping=mapping, relabels=len(relabels), next_id=self._next_id)
        return mapping, relabels


def run(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    source_sha = subprocess.check_output(["git", "-C", str(INTEGRATION), "rev-parse", "HEAD"], text=True).strip()
    modules = {"runtime": runtime_module.__file__, "hybrid": hybrid_module.__file__,
               "lane": lane_module.__file__, "provider": provider_module.__file__}
    if not all(Path(path).resolve().is_relative_to(INTEGRATION) for path in modules.values()):
        raise RuntimeError(f"integration module path mismatch: {modules}")
    hits, misses = preflight()
    if misses:
        raise RuntimeError(f"preflight missing {misses} of {hits + misses} exact windows")
    trace = Trace(out / "events.jsonl")
    trace.put("preflight", source_sha=source_sha, source_modules=modules,
              cache_hits=hits, cache_misses=misses)
    config = LiveProviderBundleConfig.from_manifest(MANIFEST)
    encoder = _identity_encoder(config, interval_workers=4)
    system_diarizer = CachedDiarizer(trace, "system")
    mic_diarizer = CachedDiarizer(trace, "microphone")
    engines = []
    descriptor = LiveServiceDescriptor(
        source_revision="s1-cache-probe", provider_name=MODEL,
        provider_revision="cached-real-responses", provider_manifest_hash=hashlib.sha256(b"s1").hexdigest(),
        config_hashes=LiveServiceConfigHashes.from_parts(endpoint_config={}, identity_config={}, decoder_config={}),
        bounds=LiveServiceBounds(max_frame_samples=15 * RATE, max_queue_depth=16,
            max_retained_samples=60 * RATE, max_identity_speakers=16,
            max_events=10000, max_tape_bytes=100_000_000), frame_samples=15 * RATE)
    result = {"source_sha": source_sha, "source_modules": modules,
              "cache_hits": hits, "cache_misses": misses,
              "provider_calls": 0, "system_cached_calls": 0, "mic_cached_calls": 0,
              "first_exception": None}
    with tempfile.TemporaryDirectory(prefix="s1-tapes-", dir=Path(__file__).parent) as tape_dir:
        def factory(_sid, publish, report_usage):
            def public(update):
                meta = {"type": type(update).__name__}
                for key in ("start_sample", "end_sample", "through_sample"):
                    if hasattr(update, key):
                        meta[key] = getattr(update, key)
                if isinstance(update, GeminiRolling):
                    meta["rows"] = len(update.segments)
                    meta["labels"] = sorted({row.speaker for row in update.segments if row.speaker})
                trace.put("public_attempt", **meta)
                try:
                    publish(update)
                except Exception as exc:
                    trace.put("public_exception", error=repr(exc), traceback=traceback.format_exc(), **meta)
                    raise
                trace.put("public_success", **meta)

            def lane_publish(lane, callback):
                def wrapped(update):
                    trace.put("lane_update", lane=lane, type=type(update).__name__,
                              end_sample=getattr(update, "end_sample", None),
                              rows=len(getattr(update, "segments", ())))
                    try:
                        callback(update)
                    except Exception as exc:
                        trace.put("lane_exception", lane=lane, error=repr(exc), traceback=traceback.format_exc())
                        raise
                return wrapped

            system_embeddings = WeSpeakerWindowEmbeddings(encoder)
            mic_embeddings = WeSpeakerWindowEmbeddings(encoder)
            gate_system, gate_mic = WebRtcWordGate(), WebRtcWordGate()
            def system_factory(callback):
                return GeminiHybridEngine(lane_publish("system", callback),
                    word_source=NoopWords(),
                    window_scheduler=GrowingContextWindowScheduler(max_seconds=90, stride_seconds=15),
                    registry=LoggedRegistry(trace, "system", embedding_threshold=.46,
                        within_window_threshold=.60, birth_min_seconds=2),
                    diarizer=system_diarizer, terminal=UnusedTerminal(),
                    embedding_source=system_embeddings, encoder_spec=encoder.spec,
                    word_gate=gate_system, report_usage=lambda **usage: None,
                    source_lane="system", voiced_audio=WebRtcSpeechDetector())
            def mic_factory(callback):
                return GeminiHybridEngine(lane_publish("microphone", callback),
                    word_source=NoopWords(),
                    window_scheduler=GrowingContextWindowScheduler(max_seconds=30, stride_seconds=15),
                    registry=LoggedRegistry(trace, "microphone", embedding_threshold=.46,
                        within_window_threshold=.60, birth_min_seconds=2, id_prefix="local"),
                    diarizer=mic_diarizer, terminal=UnusedTerminal(),
                    embedding_source=mic_embeddings, encoder_spec=encoder.spec,
                    word_gate=gate_mic, report_usage=lambda **usage: None,
                    source_lane="microphone", voiced_audio=WebRtcSpeechDetector(), diarize_windows=True)
            engine = LaneGeminiEngine(public, tape_root=Path(tape_dir),
                system_factory=system_factory, microphone_factory=mic_factory)
            engines.append(engine)
            return engine

        runtime = GeminiLiveRuntime(descriptor=descriptor, engine_factory=factory,
                                    tape_storage_root=Path(tape_dir))
        runtime.create(session_id="s1")
        engine = engines[0]
        seq = 0
        try:
            with wave.open(str(AUDIO), "rb") as source:
                start = 0
                while start < source.getnframes():
                    count = min(15 * RATE, source.getnframes() - start)
                    pcm = source.readframes(count)
                    silence = bytes(len(pcm))
                    runtime.accept_frame("s1", AudioFrame(seq, pcm, count,
                        lane_pcm=(("system", pcm), ("microphone", silence))))
                    seq += 1
                    start += count
                    if count == 15 * RATE:
                        future = engine._engines["system"]._future
                        if future is not None:
                            try:
                                future.result(timeout=120)
                            except Exception as exc:
                                trace.put("worker_exception", frame_end_s=start / RATE,
                                          error=repr(exc), traceback=traceback.format_exc())
                                if result["first_exception"] is None:
                                    result["first_exception"] = {"frame_end_s": start / RATE,
                                                                 "error": repr(exc), "traceback": traceback.format_exc()}
                    snap = runtime.snapshot("s1").session
                    trace.put("frame", accepted_s=start / RATE,
                              lane_frontiers_s={lane: value / RATE for lane, value in engine._lane_frontiers.items()},
                              public_frontier_s=engine._frontier / RATE,
                              committed_s=snap.committed_samples / RATE,
                              labelled_end_s=max((row.end_sample for row in snap.effective_transcript
                                                  if row.canonical_speaker), default=0) / RATE)
            for lane in engine.LANES:
                future = engine._engines[lane]._future
                if future is not None:
                    future.result(timeout=120)
            snap = runtime.snapshot("s1").session
            result.update(status=snap.status, accepted_s=snap.accepted_samples / RATE,
                committed_s=snap.committed_samples / RATE,
                lane_frontiers_s={lane: value / RATE for lane, value in engine._lane_frontiers.items()},
                public_frontier_s=engine._frontier / RATE,
                labelled_end_s=max((row.end_sample for row in snap.effective_transcript
                                    if row.canonical_speaker), default=0) / RATE,
                rolling_publications=sum(1 for line in (out / "events.jsonl").read_text().splitlines()
                                         if '"kind": "public_success"' in line and '"type": "GeminiRolling"' in line),
                system_cached_calls=system_diarizer.calls, mic_cached_calls=mic_diarizer.calls)
        except Exception as exc:
            trace.put("probe_exception", error=repr(exc), traceback=traceback.format_exc())
            if result["first_exception"] is None:
                result["first_exception"] = {"error": repr(exc), "traceback": traceback.format_exc()}
            result.update(system_cached_calls=system_diarizer.calls, mic_cached_calls=mic_diarizer.calls)
        finally:
            engine.close()
            runtime._release_tape(runtime._get("s1"))
            trace.close()
    (out / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    run(args.out)
