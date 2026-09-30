"""Per-word acoustic features on the production 10 ms WebRTC frame grid (throwaway)."""
from __future__ import annotations

import math

import numpy as np
import webrtcvad

RATE = 16000
FRAME = RATE // 100


class Frames:
    def __init__(self, pcm16: np.ndarray):
        self.pcm = pcm16
        n = len(pcm16) // FRAME
        raw = pcm16[:n * FRAME].tobytes()
        self.voiced = {m: np.array([webrtcvad.Vad(m).is_speech(raw[i*2*FRAME:(i+1)*2*FRAME], RATE)
                                    for i in range(n)], dtype=bool) for m in (1, 2, 3)}
        x = pcm16[:n * FRAME].astype(np.float64).reshape(n, FRAME)
        self.rms_db = 20 * np.log10(np.sqrt((x ** 2).mean(axis=1)) + 1e-9) - 20 * math.log10(32768)
        self.n = n

    def span(self, start_s: float, end_s: float, pad_s: float = .2) -> tuple[int, int]:
        lo = max(0, math.floor(start_s * 100 - pad_s * 100))
        hi = min(self.n, math.ceil(end_s * 100 + pad_s * 100))
        return lo, hi

    def longest(self, mode: int, lo: int, hi: int) -> int:
        best = run = 0
        for v in self.voiced[mode][lo:hi]:
            run = run + 1 if v else 0
            best = max(best, run)
        return best

    def word(self, start_s: float, end_s: float, pad_s: float = .2) -> dict:
        lo, hi = self.span(start_s, end_s, pad_s)
        return {f"m{m}_any": bool(self.voiced[m][lo:hi].any()) for m in (1, 2, 3)} | {
            f"m{m}_run": self.longest(m, lo, hi) for m in (1, 2, 3)} | {
            f"m{m}_count": int(self.voiced[m][lo:hi].sum()) for m in (1, 2, 3)} | {
            "peak_db": float(self.rms_db[lo:hi].max()) if hi > lo else -99.0}
