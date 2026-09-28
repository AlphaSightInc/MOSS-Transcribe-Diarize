"""WebRTC voiced audio absent from Gemini word spans."""
from __future__ import annotations

from typing import Sequence

import webrtcvad

from .live_span_bounds import LIVE_SAMPLE_RATE


def voiced_word_gaps(pcm16: bytes, spans: Sequence[tuple[int, int]], *,
                     minimum_voiced_samples: int,
                     offset_sample: int = 0) -> tuple[tuple[int, int], ...]:
    """Return wordless intervals with enough mode-1, 10 ms voiced frames."""
    frame = LIVE_SAMPLE_RATE // 100
    count = len(pcm16) // (2 * frame)
    vad = webrtcvad.Vad(1)
    voiced = [0]
    for index in range(count):
        voiced.append(voiced[-1] + int(vad.is_speech(
            pcm16[index*320:(index+1)*320], LIVE_SAMPLE_RATE)))
    boundaries = []
    for start, end in sorted(spans):
        start = max(offset_sample, min(offset_sample + count*frame, start))
        end = max(start, min(offset_sample + count*frame, end))
        if boundaries and start <= boundaries[-1][1]:
            boundaries[-1] = (boundaries[-1][0], max(boundaries[-1][1], end))
        else:
            boundaries.append((start, end))
    gaps = []
    cursor = offset_sample
    for start, end in (*boundaries, (offset_sample + count*frame,
                                     offset_sample + count*frame)):
        lo = max(0, (cursor - offset_sample + frame - 1) // frame)
        hi = min(count, (start - offset_sample) // frame)
        if hi > lo and (voiced[hi] - voiced[lo]) * frame >= minimum_voiced_samples:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    return tuple(gaps)
