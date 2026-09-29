"""Accelerated 2600 s two-lane frontier probe; no provider access."""
import tempfile
import threading
import time
from pathlib import Path

from moss_transcribe_diarize.app.gemini_hybrid_engine import (GeminiHybridEngine,
    GrowingContextWindowScheduler, OverlapRegistry)
from moss_transcribe_diarize.app.gemini_lane_engine import LaneGeminiEngine
from moss_transcribe_diarize.app.gemini_live_runtime import GeminiRolling, GeminiSegment
from moss_transcribe_diarize.app.gemini_provider import GeminiWord, GeminiWords

RATE = 16000

class Source:
    def __init__(self, voiced): self.voiced = voiced
    def bind(self, callback): self.callback = callback
    def push_audio(self, start, pcm):
        if self.voiced:
            self.callback("spoken", start, start + min(RATE, len(pcm)//2), True)
    async def finish(self): pass
    def close(self): pass

class Diarizer:
    def __init__(self, voiced, *, failure_mode=None):
        self.voiced, self.calls = voiced, 0
        self.failure_mode = failure_mode
        self.blocked = threading.Event()
        self.release = threading.Event()
    def diarize(self, pcm, *, deadline, kind, diarize=True):
        self.calls += 1
        if self.voiced and self.calls == 47 and self.failure_mode:
            self.blocked.set()
            if not self.release.wait(timeout=10):
                raise TimeoutError("probe release missing")
            if self.failure_mode == "raise":
                raise RuntimeError("simulated provider retry exhaustion")
        time.sleep(.001)
        return GeminiWords((GeminiWord("spoken", "spk:0", max(0, len(pcm)//2-RATE), len(pcm)//2),)) if self.voiced else GeminiWords(())

class Terminal:
    def transcribe(self, tape): return ()

def main(failure_mode=None):
    updates = []
    system, mic = Diarizer(True, failure_mode=failure_mode), Diarizer(False)
    with tempfile.TemporaryDirectory() as root:
        engine = LaneGeminiEngine(updates.append, tape_root=Path(root),
            system_factory=lambda publish: GeminiHybridEngine(publish,
                word_source=Source(True), window_scheduler=GrowingContextWindowScheduler(
                    max_seconds=90, stride_seconds=15), registry=OverlapRegistry(),
                diarizer=system, terminal=Terminal(), source_lane="system",
                voiced_audio=lambda pcm: True),
            microphone_factory=lambda publish: GeminiHybridEngine(publish,
                word_source=Source(False), window_scheduler=GrowingContextWindowScheduler(
                    max_seconds=30, stride_seconds=15), registry=OverlapRegistry(),
                diarizer=mic, terminal=Terminal(), source_lane="microphone",
                voiced_audio=lambda pcm: False, diarize_windows=False))
        audio = b"\x01\x00" * (15*RATE)
        silence = bytes(len(audio))
        for i in range(174):
            start = i*15*RATE
            engine.push_lanes(start, (("system", audio), ("microphone", silence)))
            if failure_mode and system.blocked.is_set() and not system.release.is_set() and i >= 52:
                system.release.set()
            time.sleep(.003)
        for lane in engine.LANES:
            future = engine._engines[lane]._future
            if future: future.result(timeout=60)
        rolls = [x for x in updates if isinstance(x, GeminiRolling)]
        print({"mode": failure_mode or "baseline", "accepted_s": engine._accepted/RATE,
               "system_calls": system.calls, "mic_calls": mic.calls,
               "lane_frontiers_s": {k:v/RATE for k,v in engine._lane_frontiers.items()},
               "public_frontier_s": engine._frontier/RATE,
               "last_label_end_s": max((r.end_sample for x in rolls for r in x.segments), default=0)/RATE,
               "rolling_publications": len(rolls),
               "degraded_bases": sum(getattr(x, "degraded", False) for x in updates),
               "system_future_error": repr(engine._engines["system"]._future.exception())
                   if engine._engines["system"]._future else None})
        engine.close()

if __name__ == "__main__":
    main()
    main("slow")
    main("raise")
