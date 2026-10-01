"""PROTOTYPE — $0 audit on the fetched raw labels: every label pair with >= 1 alternation, any cosine.

Question (added after `raw_pass.py evaluate`, not precommitted): does rule V's voice check keep the veto for
pairs whose labels are different true speakers, in particular pairs with a single alternation?
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import raw_pass as rp  # noqa: E402
from v_rule import RulePolicy  # noqa: E402
from moss_transcribe_diarize.app.gemini_long_final import _cosine  # noqa: E402


def main() -> None:
    real = rp._identity_encoder(rp.LiveProviderBundleConfig.from_manifest(rp.MANIFEST), interval_workers=3)
    rows, table = [], collections.Counter()
    for clip in rp.clips("synth"):
        saved = json.loads(rp.raw_path(clip.clip_id).read_text())
        truth = sorted(clip.reference_segments(), key=lambda r: r["start"])
        tape = rp._WavTape(clip.audio)
        policy = RulePolicy(real, "V")
        terminal = rp.TerminalTranscriber(rp.SavedWords(saved["response"]), identity_policy=policy)
        terminal.transcribe(tape)
        veto, centroids = policy.last_veto, policy.last_centroids
        truth_of = rp.dominant(policy.last_words, truth)
        import tempfile, wave
        with tempfile.NamedTemporaryFile(suffix=".wav") as file:  # the veto's wav is gone; give it the clip
            veto.wav_path = str(clip.audio)
            for pair, seen in sorted(veto.alternations.items()):
                a, b = pair
                ta, tb = truth_of.get(a), truth_of.get(b)
                relation = "unknown" if ta is None or tb is None else ("same" if ta[0] == tb[0] else "different")
                cosine = _cosine(centroids[a], centroids[b]) if a in centroids and b in centroids else None
                checked = [[(t[0], round(t[1] / rp.S, 1), round((t[2] - t[1]) / rp.S, 1), veto.disagrees(t)) for t in triple]
                           for triple in seen]
                stands = any(not any(t[3] for t in triple) for triple in checked)
                bucket = "1" if len(seen) == 1 else ">=2"
                table[(relation, bucket, "stands" if stands else "dropped")] += 1
                rows.append({"clip": clip.clip_id, "labels": [a, b], "truth": [ta, tb], "relation": relation,
                             "cosine": None if cosine is None else round(cosine, 3), "alternations": len(seen),
                             "veto_stands_under_V": stands,
                             "dropped_detail": None if stands else checked})
    summary = {f"{k[0]} | alternations {k[1]} | {k[2]}": v for k, v in sorted(table.items())}
    (rp.OUT / "raw-audit.json").write_text(json.dumps({"schema": "aba-veto-raw-audit.v1", "summary": summary,
                                                       "pairs": rows}, indent=1) + "\n")
    print(json.dumps(summary, indent=1))
    for r in rows:
        if r["relation"] == "different" and not r["veto_stands_under_V"]:
            print("DROPPED different-speaker veto:", json.dumps(r))


if __name__ == "__main__":
    main()
