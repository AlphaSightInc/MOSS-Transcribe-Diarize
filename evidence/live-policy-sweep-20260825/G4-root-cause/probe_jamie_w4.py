"""Decode Jamie window 4 ([640000, 800000)) once; test order before/after the terminal resolver.

Question: is the deterministic `segments_out_of_order` refusal on
discussion_jamie_dimon_180s window 4 the disorder class `resolve_segment_overlaps`
already handles — i.e. would normalizing rolling proposals the way terminal proposals
are normalized have admitted this window?
"""
import json
import sys
import wave
from pathlib import Path

REPO = Path("/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize")
sys.path.insert(0, str(REPO))

from moss_transcribe_diarize.app.live_adapters import canonical_decode_token_cap  # noqa: E402
from moss_transcribe_diarize.app.live_transcript_convergence import (  # noqa: E402
    resolve_segment_overlaps,
)
from moss_transcribe_diarize.transcript_parser import parse_transcript  # noqa: E402

WAV = REPO / "prototypes/streaming-diarization/data/real/calibration_diarization_3min/samples/acquired_jamie_dimon_3min/audio.wav"
START, END = 640000, 800000
SR = 16000

# 1. cut the window
with wave.open(str(WAV), "rb") as fh:
    assert fh.getframerate() == SR and fh.getnchannels() == 1
    fh.setpos(START)
    pcm = fh.readframes(END - START)
cut = Path(__file__).parent / "jamie-w4.wav"
with wave.open(str(cut), "wb") as out:
    out.setnchannels(1); out.setsampwidth(2); out.setframerate(SR)
    out.writeframes(pcm)

# 2. one greedy decode through the same runner the service uses
from moss_transcribe_diarize.app.vllm_runner import VllmRunner  # noqa: E402
cap = canonical_decode_token_cap(sample_count=END - START)
runner = VllmRunner(base_url="http://127.0.0.1:18000/v1", model="OpenMOSS-Team/MOSS-Transcribe-Diarize")
result = runner.transcribe(str(cut), max_new_tokens=cap)
text = result.text
print(f"raw decode ({result.generated_tokens} tokens):", text[:400])

# 3. parse to segments the way the pipeline does
parsed = parse_transcript(text)
segs = [(s.speaker, int(START + round(s.start * SR)), int(START + round(s.end * SR)), s.text)
        for s in parsed]
print(f"\nparsed {len(segs)} segments:")
disorder = []
prev_end = None
for i, (spk, s, e, tx) in enumerate(segs):
    flag = ""
    if prev_end is not None and s < prev_end:
        flag = f"  <-- OUT OF ORDER (starts {prev_end - s} samples before previous end)"
        disorder.append(i)
    print(f"  [{i}] {spk} [{s},{e}) {tx[:60]!r}{flag}")
    prev_end = e if prev_end is None else max(prev_end, e)

# 4. session refusal predicate (the exact rule from LiveSession._text_revision_refusal)
def refusal(items):
    prev = None
    for spk, s, e, tx in items:
        if e <= s:
            return "segment_does_not_advance"
        if prev is not None and s < prev:
            return "segments_out_of_order"
        prev = e
    return None

print("\nrefusal BEFORE resolver:", refusal(segs))

res = resolve_segment_overlaps(segs)
print(f"resolver: merged={res.merged} dropped={res.dropped} displaced={res.displaced_samples}")
print("refusal AFTER resolver:", refusal(res.segments))
before_words = " ".join(t for _, _, _, t in segs).split()
after_words = " ".join(t for _, _, _, t in res.segments).split()
print(f"words before={len(before_words)} after={len(after_words)} lost={len(before_words)-len(after_words)}")
