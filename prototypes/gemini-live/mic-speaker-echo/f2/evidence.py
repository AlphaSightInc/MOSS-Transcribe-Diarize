"""R5-F2 candidate primitive (throwaway prototype; the part meant to be lifted into the product).

Question answered per 10 ms frame of the microphone lane: is this voiced audio that the tab cannot explain?

    frame facts  -> echo return of the context -> unexplained voiced frames -> evidence of a run / of a word

Pure functions over two aligned int16 lanes. No provider text, no word list, no language rule.
"""
from __future__ import annotations

import numpy as np
import webrtcvad

RATE = 16000
FRAME = RATE // 100           # 10 ms, the product's WebRTC frame
MAX_LAG = 10                  # frames: the level gate's 0-100 ms echo delay search


class Facts:
    """Per-frame facts of one stretch of the two lanes (same start, same length)."""

    def __init__(self, mic: np.ndarray, system: np.ndarray, *, vad_mode: int = 1):
        n = min(len(mic), len(system)) // FRAME
        self.n = n
        mic, system = mic[:n * FRAME], system[:n * FRAME]
        mic_vad, sys_vad = webrtcvad.Vad(vad_mode), webrtcvad.Vad(vad_mode)
        mic_raw, sys_raw = mic.astype("<i2").tobytes(), system.astype("<i2").tobytes()
        step = FRAME * 2
        self.mic_voiced = np.fromiter((mic_vad.is_speech(mic_raw[i * step:(i + 1) * step], RATE) for i in range(n)),
                                      dtype=bool, count=n)
        sys_voiced = np.fromiter((sys_vad.is_speech(sys_raw[i * step:(i + 1) * step], RATE) for i in range(n)),
                                 dtype=bool, count=n)
        self.mic_rms = np.sqrt((mic.astype(np.float64).reshape(n, FRAME) ** 2).mean(axis=1))
        sys_rms = np.sqrt((system.astype(np.float64).reshape(n, FRAME) ** 2).mean(axis=1))
        # What a microphone frame could be echoing: the tab within the last 0-100 ms.
        pad_rms = np.concatenate([np.zeros(MAX_LAG), sys_rms])
        pad_voiced = np.concatenate([np.zeros(MAX_LAG, dtype=bool), sys_voiced])
        self.sys_best = np.max(np.stack([pad_rms[k:k + n] for k in range(MAX_LAG + 1)]), axis=0)
        self.sys_near = np.any(np.stack([pad_voiced[k:k + n] for k in range(MAX_LAG + 1)]), axis=0)

    def ratio_db(self) -> np.ndarray:
        """Microphone level relative to the tab, on frames where the tab is voiced (NaN elsewhere)."""
        out = np.full(self.n, np.nan)
        ok = self.sys_near & (self.sys_best > 0)
        out[ok] = 20 * np.log10(np.maximum(self.mic_rms[ok], 1e-3) / self.sys_best[ok])
        return out


def echo_return_db(facts: Facts, quantile: float) -> float | None:
    """The context's echo return: a quantile of microphone/tab level over tab-voiced frames. None: tab never talked."""
    ratio = facts.ratio_db()
    ratio = ratio[~np.isnan(ratio)]
    return float(np.quantile(ratio, quantile)) if len(ratio) >= 100 else None


def unexplained(facts: Facts, return_db: float | None, margin_db: float) -> np.ndarray:
    """Voiced microphone frames the tab cannot explain: the tab is silent there, or the microphone is louder
    than the meeting's measured echo return by the margin. With no measurement (the tab talked for under 1 s in
    the context) the level gate's fixed -15 dB stands in."""
    if return_db is None:
        return fixed_level(facts)
    limit = facts.sys_best * 10 ** ((return_db + margin_db) / 20)
    return facts.mic_voiced & (~facts.sys_near | (facts.mic_rms > limit))


def fixed_level(facts: Facts, threshold_db: float = -15.0) -> np.ndarray:
    """The withdrawn first draft (today's level-gate reference, per frame): for comparison only."""
    return facts.mic_voiced & (~facts.sys_near | (facts.mic_rms >= facts.sys_best * 10 ** (threshold_db / 20)))


def longest(flags: np.ndarray, lo: int, hi: int, gap: int = 0) -> int:
    """Longest stretch of true frames in [lo, hi), bridging holes of at most `gap` frames. In frames."""
    best = run = hole = 0
    for flag in flags[max(0, lo):hi]:
        if flag:
            run += hole + 1 if run else 1
            hole = 0
            best = max(best, run)
        elif run and hole < gap:
            hole += 1
        else:
            run = hole = 0
    return best


def span_frames(start_sample: int, end_sample: int, offset_sample: int, n: int, pad: int = 20) -> tuple[int, int]:
    """A word span on the frame grid, padded by 200 ms like the product's word gate."""
    lo = max(0, (start_sample - offset_sample) // FRAME - pad)
    hi = min(n, -(-(end_sample - offset_sample) // FRAME) + pad)
    return lo, hi
