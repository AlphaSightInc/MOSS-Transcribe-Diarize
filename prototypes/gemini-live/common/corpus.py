"""Corpus registry for the gemini-live bake-off (public audio only, per D7).

Tiers (id -> Clip):
- accept6 : the 6 acceptance quality cases H1 #3 (8d8fb682) was scored on — the apples-to-apples
            MOSS baseline lives in moss-round6/evidence/r6-h1c-*/.../content-free-metrics.json
- gold9   : binding 9-clip golden set (benchmark_1min + calibration_3min)
- bench5m : 8 x 300 s real interviews/discussions (K=2-3)
- long30m : 2 x 1800 s
- synth   : LibriSpeech synthetic meetings K=2..6 (600 s)
- long60  : 43-min public Lex concatenation, 5 true speakers (build: window/long60/build.py)
- e1      : round-6 E1 fixture (Acquired/Jensen, 302 s, 3 true voices on system lane; mic lanes
            synthetic). No timed reference: speaker-count truth only (3 system + 1 mic).
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

WORKTREE = Path(__file__).resolve().parents[3]
REAL = WORKTREE / "prototypes" / "streaming-diarization" / "data" / "real"
SYNTH = WORKTREE / "prototypes" / "streaming-diarization" / "data"
ACCEPT = WORKTREE / "evidence" / "live-policy-sweep-20260825" / "corpus"
E1 = Path("/Users/gao/Documents/Codex/2026-09-23/moss-round6/evidence/dx-replay")
# H1 #3 scored accept6 against the corpus manifest sha 80fc15bd…; in this checkout the Bill Ackman and
# Keyu Jin references were later corrected (966d250b). Comparisons with recorded MOSS numbers must use
# the H1 truth set, so accept6 clips point at the manifest-matching references (materialized from git).
H1_REFERENCE_REVISION = "966d250b^"
H1_REFS = WORKTREE / "prototypes" / "gemini-live" / ".cache" / "h1-references"


def _h1_reference(case: str, current: Path) -> Path:
    target = H1_REFS / case / "reference.jsonl"
    if not target.exists():
        rel = current.relative_to(WORKTREE).as_posix()
        blob = subprocess.run(["git", "-C", str(WORKTREE), "show", f"{H1_REFERENCE_REVISION}:{rel}"],
                              capture_output=True, check=True).stdout
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
    return target


@dataclass(frozen=True)
class Clip:
    clip_id: str
    tier: str
    audio: Path
    reference: Path | None  # jsonl with speaker/text/start/end, or None
    true_speakers: int | None = None
    mic_audio: Path | None = None

    def reference_segments(self) -> list[dict]:
        if self.reference is None:
            return []
        if self.reference.suffix == ".json":  # synthetic: {"k":..,"truth":[[s,e,spk],...]}
            d = json.loads(self.reference.read_text())
            return [{"start": s, "end": e, "speaker": f"spk{int(k)}", "text": ""} for s, e, k in d["truth"]]
        out = []
        for line in self.reference.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                out.append({"start": float(r["start"]), "end": float(r["end"]),
                            "speaker": str(r["speaker"]), "text": r.get("text", "")})
        return out


def clips(tier: str | None = None) -> list[Clip]:
    out: list[Clip] = []
    for d in sorted(ACCEPT.glob("*/")):
        if (d / "audio.wav").exists():
            out.append(Clip(d.name, "accept6", d / "audio.wav", _h1_reference(d.name, d / "reference.jsonl")))
    for sub in ("benchmark_diarization_1min", "calibration_diarization_3min"):
        for d in sorted((REAL / sub / "samples").glob("*/")):
            if (d / "audio.wav").exists():
                out.append(Clip(f"{sub.split('_')[0]}:{d.name}", "gold9", d / "audio.wav", d / "reference.jsonl"))
    for tier_name, sub in (("bench5m", "benchmark_5m"), ("long30m", "benchmark_30m")):
        for d in sorted((REAL / sub).glob("*/")):
            if (d / "audio.wav").exists():
                out.append(Clip(f"{sub}:{d.name}", tier_name, d / "audio.wav", d / "reference.jsonl"))
    rtfl = REAL / "regression_fixtures" / "youtube_rtfl_first_90s"
    if (rtfl / "audio.wav").exists():
        ref = next((p for p in (rtfl / "reference.jsonl",) if p.exists()), None)
        out.append(Clip("rtfl90", "rtfl", rtfl / "audio.wav", ref, 4))
    for w in sorted(SYNTH.glob("meet_k*_s*.wav")):
        j = w.with_suffix(".json")
        k = int(w.stem.split("_")[1][1:])
        out.append(Clip(f"synth:{w.stem}", "synth", w, j if j.exists() else None, k))
    long60 = WORKTREE / "prototypes" / "gemini-live" / ".cache" / "long60" / "audio.wav"
    long60_ref = WORKTREE / "prototypes" / "gemini-live" / "window" / "long60" / "reference.jsonl"
    if long60.exists() and long60_ref.exists():
        # 43m06 concatenation of complete-reference public Lex clips (window/long60/build.py):
        # Lex Fridman hosts every part (separate recording sessions) + four guests = 5 true speakers.
        out.append(Clip("long60", "long60", long60, long60_ref, 5))
    if (E1 / "fixture" / "system.wav").exists():
        out.append(Clip("e1", "e1", E1 / "fixture" / "system.wav", None, 4,
                        mic_audio=E1 / "fixture" / "E1-microphone.wav"))
    return [c for c in out if tier is None or c.tier == tier]


if __name__ == "__main__":
    import soundfile as sf
    for c in clips():
        i = sf.info(str(c.audio))
        print(f"{c.tier:8} {c.clip_id:45} {i.duration:7.1f}s sr={i.samplerate} ch={i.channels} ref={'y' if c.reference else '-'}")
