"""Accelerated 2600 s two-lane frontier probe; no provider access."""
import tempfile
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
    def __init__(self, voiced): self.voiced, self.calls = voiced, 0
    def diarize(self, pcm, *, deadline, kind, diarize=True):
        self.calls += 1
        time.sleep(.001)
        return GeminiWords((GeminiWord("spoken", "spk:0", max(0, len(pcm)//2-RATE), len(pcm)//2),)) if self.voiced else GeminiWords(())

class Terminal:
    def transcribe(self, tape): return ()

def main():
    updates = []
    system, mic = Diarizer(True), Diarizer(False)
    with tempfile.TemporaryDirectory() as root:
        engine = LaneGeminiEngine(updates.append, tape_root=Path(root),
            system_factory=lambda publish: GeminiHybridEngine(publish,
                word_source=Source(True), window_scheduler=GrowingContextWindowScheduler(
                    max_seconds=90, stride_seconds=15), registry=OverlapRegistry(),
                diarizer=system, terminal=Terminal(), source_lane="system",
                voiced_audio=lambda pcm: True),
            microphone_factory=lambda publish: GeminiHybridEngine(publish,
                word_source=Source(False), window_scheduler=GrowingContextWindowScheduler(
                    max_seconds=60, stride_seconds=10), registry=OverlapRegistry(),
                diarizer=mic, terminal=Terminal(), source_lane="microphone",
                voiced_audio=lambda pcm: False, diarize_windows=False))
        audio = b"\x01\x00" * (15*RATE)
        silence = bytes(len(audio))
        for i in range(174):
            start = i*15*RATE
            engine.push_lanes(start, (("system", audio), ("microphone", silence)))
            time.sleep(.003)
        for lane in engine.LANES:
            future = engine._engines[lane]._future
            if future: future.result(timeout=60)
        rolls = [x for x in updates if isinstance(x, GeminiRolling)]
        print({"accepted_s": engine._accepted/RATE,
               "system_calls": system.calls, "mic_calls": mic.calls,
               "lane_frontiers_s": {k:v/RATE for k,v in engine._lane_frontiers.items()},
               "public_frontier_s": engine._frontier/RATE,
               "last_label_end_s": max((r.end_sample for x in rolls for r in x.segments), default=0)/RATE,
               "rolling_publications": len(rolls)})
        engine.close()

if __name__ == "__main__": main()
