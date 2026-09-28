"""Score a hypothesis against a reference with the PRODUCTION metric code
(moss_transcribe_diarize.evaluation: WER, text-speaker accuracy, DER = miss + FA + confusion).

Hypothesis/reference = list of {start, end, speaker, text} in absolute seconds.
Also reports speaker-count facts (hyp speakers, ref speakers) used by the D6 split/merge bars.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from moss_transcribe_diarize.evaluation import Segment, calculate_diarization, calculate_tbsa  # noqa: E402


def _segs(rows: list[dict]) -> list[Segment]:
    return [Segment(float(r["start"]), float(r["end"]), str(r["speaker"]), str(r.get("text", "")))
            for r in rows if float(r["end"]) > float(r["start"])]


def score(reference: list[dict], hypothesis: list[dict], *, with_text: bool = True) -> dict:
    ref, hyp = _segs(reference), _segs(hypothesis)
    out: dict = {"ref_speakers": len({s.speaker for s in ref}), "hyp_speakers": len({s.speaker for s in hyp})}
    d = calculate_diarization(ref, hyp)
    out.update({k: d[k] for k in ("der", "miss", "false_alarm", "speaker_confusion")})
    if with_text and any(s.text for s in ref):
        t = calculate_tbsa(ref, hyp)
        out.update({"wer": t["wer"], "text_speaker_accuracy": t["text_speaker_accuracy"],
                    "text_coverage": t["text_coverage"]})
    return out
