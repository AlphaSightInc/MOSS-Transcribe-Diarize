"""Start the unmodified integration HTTPS stack with temporary window logging."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

MODEL = "gemini-3.5-transcribe"
CONFIG = {"transcription_config": {"mode": {"type": "verbatim",
           "diarization_mode": "speaker", "timestamp_granularities": ["word"]}}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--integration", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    args, cli_args = parser.parse_known_args()
    integration = args.integration.resolve()
    if cli_args and cli_args[0] == "--":
        cli_args.pop(0)
    sys.path.insert(0, str(integration))
    from moss_transcribe_diarize.app import (gemini_provider, gemini_hybrid_engine,
                                              gemini_continuity_registry, phase2_web_cli)
    modules = (gemini_provider, gemini_hybrid_engine,
               gemini_continuity_registry, phase2_web_cli)
    if not all(Path(module.__file__).resolve().is_relative_to(integration) for module in modules):
        raise RuntimeError("integration module import mismatch")
    source_sha = subprocess.check_output(
        ["git", "rev-parse", "gemini/r2-integration"], text=True).strip()
    trace_lock = threading.Lock()
    local = threading.local()
    metered_cost = [0.0]
    trace_stream = args.trace.open("w", encoding="utf-8")

    def log(event, **fields):
        with trace_lock:
            trace_stream.write(json.dumps({"event": event, "at": round(time.monotonic(), 6),
                                           **fields}, sort_keys=True) + "\n")
            trace_stream.flush()

    log("source", sha=source_sha,
        modules={module.__name__: module.__file__ for module in modules})
    old_decode = gemini_hybrid_engine.GeminiHybridEngine._decode_covered_window
    old_publish = gemini_hybrid_engine.GeminiHybridEngine._publish_window
    old_diarize = gemini_provider.WindowDiarizer.diarize
    old_init = gemini_provider.WindowDiarizer.__init__
    old_observe = gemini_continuity_registry.ContinuityRegistry.observe_window
    cache = integration / "prototypes/gemini-live/.cache"

    def decode(self, pcm, start, voice_start, *, deadline):
        previous = getattr(local, "window", None)
        local.window = {"lane": self.source_lane, "start_sample": start,
                        "end_sample": start + len(pcm)//2}
        try:
            return old_decode(self, pcm, start, voice_start, deadline=deadline)
        finally:
            local.window = previous

    def publish(self, start, frontier, pcm, words, fallback=(), *, gate_words=True):
        previous = getattr(local, "window", None)
        local.window = {"lane": self.source_lane, "start_sample": start,
                        "end_sample": start + len(pcm)//2,
                        "frontier_sample": frontier}
        try:
            return old_publish(self, start, frontier, pcm, words, fallback,
                               gate_words=gate_words)
        finally:
            local.window = previous

    def init(self, client, report_usage, *, max_attempts=3):
        def report(**usage):
            amount = float(usage.get("cost_usd", 0.0))
            with trace_lock:
                metered_cost[0] += amount
                total = metered_cost[0]
            log("usage", kind=usage.get("kind"), cost_usd=amount,
                metered_total_usd=round(total, 9),
                audio_seconds_sent=usage.get("audio_seconds_sent", 0),
                error_code=usage.get("error_code"), retry_code=usage.get("retry_code"))
            report_usage(**usage)
        old_init(self, client, report, max_attempts=max_attempts)

    def diarize(self, pcm, *, deadline, kind="rolling", diarize=True):
        with trace_lock:
            spent = metered_cost[0]
        if spent >= .39:
            log("budget_stop", metered_cost_usd=spent)
            raise RuntimeError("LIVE_DIVERGENCE_BUDGET_STOP")
        audio = gemini_provider._wav(pcm)
        wav_sha = hashlib.sha256(audio).hexdigest()
        key = hashlib.sha256(audio + json.dumps([MODEL, CONFIG], sort_keys=True).encode()).hexdigest()
        path = cache / key[:2] / f"{key}.json"
        window = dict(getattr(local, "window", None) or {})
        log("request", **window, kind=kind, wav_sha256=wav_sha,
            cache_key=key, cache_hit=path.is_file(), audio_samples=len(pcm)//2)
        result = old_diarize(self, pcm, deadline=deadline, kind=kind, diarize=diarize)
        labels = dict(Counter(word.speaker for word in result.words))
        same = None
        if path.is_file():
            raw = json.loads(path.read_text(encoding="utf-8"))["response"]
            cached = gemini_provider.parse_words(raw, audio_samples=len(pcm)//2)
            if kind in {"rolling", "terminal"}:
                fixed, _ = gemini_provider.repair_word_timestamps(cached.words, len(pcm)//2)
                cached = gemini_provider.GeminiWords(fixed, cached.clamped, cached.dropped)
            same = result.words == cached.words
        log("response", **window, kind=kind, cache_key=key,
            word_count=len(result.words), labels=labels, words_equal_cache=same)
        return result

    def observe(self, window_start_s, words, embeddings=None, **options):
        mapping, relabels = old_observe(self, window_start_s, words, embeddings, **options)
        log("mapping", **dict(getattr(local, "window", None) or {}),
            window_start_s=window_start_s, word_count=len(words),
            local_labels=dict(Counter(word.speaker for word in words)),
            mapping=mapping, relabels=len(relabels))
        return mapping, relabels

    gemini_hybrid_engine.GeminiHybridEngine._decode_covered_window = decode
    gemini_hybrid_engine.GeminiHybridEngine._publish_window = publish
    gemini_provider.WindowDiarizer.__init__ = init
    gemini_provider.WindowDiarizer.diarize = diarize
    gemini_continuity_registry.ContinuityRegistry.observe_window = observe
    try:
        phase2_web_cli.main(cli_args)
    finally:
        log("done", metered_cost_usd=metered_cost[0])
        trace_stream.close()


if __name__ == "__main__":
    main()
