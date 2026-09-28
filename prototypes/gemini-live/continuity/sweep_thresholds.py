"""Zero-send E/W threshold sweep on fixed L1 vectors and cached S10/L30 calls."""
from __future__ import annotations

import json
import sys

import numpy as np

from measure import EVIDENCE, HERE, cached_embeddings, evaluate, note, windows

sys.path.insert(0, str(HERE.parent))
from common.corpus import clips  # noqa: E402
from common.gemini_common import diarize_window, read_wav  # noqa: E402

E_VALUES = (.30, .40, .46, .60, .70)
W_VALUES = (.46, .60, .70)


def observations(clip, *, mix=False):
    pcm = read_wav(clip.audio)
    if mix:
        mic = read_wav(clip.mic_audio)
        pcm = np.clip(pcm.astype(np.int32) + mic.astype(np.int32),
                      -32768, 32767).astype(np.int16)
    rows = []
    for start, end, part in windows(pcm, 10, 30):
        result = diarize_window(part, max_attempts=0)
        rows.append({"start": start, "end": end,
                     "words": [vars(word) for word in result.words],
                     "api_latency_s": result.latency_s})
    _, cached = cached_embeddings(clip, rows, 10, 30, mix, pcm)
    if not cached:
        raise RuntimeError(f"missing L1 vectors: {clip.clip_id}")
    return rows


if __name__ == "__main__":
    selected = [(clip, False) for clip in clips("accept6")]
    selected += [(clip, False) for clip in clips("synth")
                 if clip.clip_id in {"synth:meet_k2_s0", "synth:meet_k6_s0"}]
    e1 = clips("e1")[0]
    selected += [(e1, False), (e1, True)]
    output = []
    for clip, mixed in selected:
        obs = observations(clip, mix=mixed)
        reference = [] if clip.tier == "e1" else clip.reference_segments()
        values = {}
        for e in E_VALUES:
            for w in W_VALUES:
                variant = evaluate(reference, obs, 0, .3, e, w)
                values[f"E{e:g}_W{w:g}"] = {
                    "first_der": variant["first"]["der"] if variant["first"] else None,
                    "speaker_count": variant["speaker_count"],
                    "births": variant["births"],
                    "local_merges": variant["local_merges"],
                }
        row = {"case": clip.clip_id, "mixed": mixed,
               "true_speakers": 4 if mixed else 3 if clip.tier == "e1" else
               clip.true_speakers if clip.tier == "synth" else
               len({segment["speaker"] for segment in reference}),
               "variants": values}
        output.append(row)
        note(f"Threshold sweep {clip.clip_id}{'-mix' if mixed else ''}: "
             f"{len(obs)} cached calls, {len(values)} E/W variants")
        print(json.dumps(row), flush=True)
    path = EVIDENCE / "threshold-sweep-S10-L30-H0-L1.json"
    path.write_text(json.dumps(output, indent=2))
    note(f"Threshold sweep complete: {len(output)} cases, 15 E/W variants, receipt {path.name}")
