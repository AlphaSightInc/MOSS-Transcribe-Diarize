"""Offline span simulator + gate G2.

Reproduces the deployed live span policy without a live session: webrtcvad mode 1 over
160-sample frames (the deployed `speech_provider`), fed into the real `EndpointPolicy` with
the deployed `endpoint_config`. Gate: it must reproduce every committed span boundary of the
three baseline traces exactly. Only then may it be used to provoke spans on the 3-minute tier.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from common import HERE, SR, TRIO, load_spans, read_pcm

from moss_transcribe_diarize.app.live_endpoint import (
    EndpointPolicy,
    EndpointPolicyConfig,
    SpeechObservation,
)

# deployed live-provider-manifest.json -> endpoint_config / speech_provider
ENDPOINT = EndpointPolicyConfig(
    min_speech_samples=1600,
    min_silence_samples=8000,
    pre_speech_padding_samples=1600,
    post_speech_padding_samples=1600,
    hard_cap_samples=40000,
)
VAD_MODE = 1
VAD_FRAME_SAMPLES = 160
LIVE_FRAME_SAMPLES = 8000


def simulate(pcm: bytes) -> list[tuple[int, int, str]]:
    import webrtcvad

    vad = webrtcvad.Vad(VAD_MODE)
    policy = EndpointPolicy(ENDPOINT)
    spans: list[tuple[int, int, str]] = []
    total = len(pcm) // 2
    cursor = 0
    fb = VAD_FRAME_SAMPLES * 2
    while cursor < total:
        frame_end = min(cursor + LIVE_FRAME_SAMPLES, total)
        pos = cursor
        while pos < frame_end:
            piece_end = min(pos + VAD_FRAME_SAMPLES, frame_end)
            chunk = pcm[pos * 2 : piece_end * 2]
            voiced = vad.is_speech(chunk, SR) if len(chunk) == fb else False
            for s in policy.observe(
                SpeechObservation(start_sample=pos, end_sample=piece_end, speech_present=voiced)
            ):
                spans.append((s.start_sample, s.end_sample, s.reason))
            pos = piece_end
        cursor = frame_end
    for s in policy.stop():
        spans.append((s.start_sample, s.end_sample, s.reason))
    return spans


def gate() -> bool:
    ok = True
    for case in TRIO:
        want = [(s.start_sample, s.end_sample) for s in load_spans(case)]
        got = [(a, b) for a, b, _ in simulate(read_pcm(case))]
        match = want == got
        ok = ok and match
        print(f"[G2] {case:20s} baseline_spans={len(want):3d} simulated={len(got):3d} identical={match}")
        if not match:
            for i, (w, g) in enumerate(zip(want, got)):
                if w != g:
                    print(f"     first divergence at index {i}: baseline={w} simulated={g}")
                    break
    return ok


if __name__ == "__main__":
    passed = gate()
    if len(sys.argv) > 1:
        case = sys.argv[1]
        from common import case_dir

        spans = simulate(read_pcm(case))
        out = [{"span_id": i, "start_sample": a, "end_sample": b, "reason": r} for i, (a, b, r) in enumerate(spans)]
        (HERE / "out").mkdir(exist_ok=True)
        (HERE / f"out/sim-{case}.json").write_text(json.dumps(out, indent=1))
        print(f"{case}: {len(spans)} simulated spans -> out/sim-{case}.json")
    sys.exit(0 if passed else 1)
