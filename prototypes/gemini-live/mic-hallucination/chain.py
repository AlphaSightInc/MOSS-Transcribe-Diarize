"""Replay the production microphone word-gate chain over cached fixture Gemini words (throwaway)."""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from array import array
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT), str(HERE.parent / "common"), str(HERE)]
from gemini_common import read_wav  # noqa: E402
from moss_transcribe_diarize.app.gemini_provider import GeminiWord  # noqa: E402
from moss_transcribe_diarize.app.gemini_final_policy import WebRtcWordGate  # noqa: E402
from moss_transcribe_diarize.app.gemini_lane_engine import (  # noqa: E402
    AcousticEchoGuard, CrossLaneVoiceEchoGuard, MicrophoneWordGate, SystemWordLedger)
from moss_transcribe_diarize.app.gemini_hybrid_engine import WeSpeakerWindowEmbeddings  # noqa: E402

RATE = 16000
FIX = HERE / "out" / ("fixture2" if "--v2" in sys.argv else "fixture")
MANIFEST = Path.home() / ".local/share/moss-transcribe-diarize/live/live-provider-manifest.json"
_encoder = None


def encoder():
    global _encoder
    if _encoder is None:
        from moss_transcribe_diarize.app.live_provider_bundle import LiveProviderBundleConfig, _identity_encoder
        _encoder = _identity_encoder(LiveProviderBundleConfig.from_manifest(MANIFEST), interval_workers=4)
    return _encoder


def gw(rows, offset_s=0.0):
    return tuple(GeminiWord(r["text"], r["speaker"], round((offset_s + r["start"]) * RATE),
                            round((offset_s + r["end"]) * RATE)) for r in rows)


def units(text: str) -> list[str]:
    out = []
    for token in re.findall(r"[^\W_]+(?:'[^\W_]+)?", text.casefold()):
        run = ""
        for ch in token:
            if "CJK" in unicodedata.name(ch, ""):
                if run:
                    out.append(run)
                    run = ""
                out.append(ch)
            else:
                run += ch
        if run:
            out.append(run)
    return out


def lcs(a, b):
    table = [array("H", [0]) * (len(b) + 1)]
    for x in a:
        prior, cur = table[-1], array("H", [0]) * (len(b) + 1)
        for j, y in enumerate(b, 1):
            cur[j] = prior[j - 1] + 1 if x == y else max(prior[j], cur[j - 1])
        table.append(cur)
    return table[-1][-1]


class Variant:
    def __init__(self, name: str):
        self.name = name
        self.manifest = json.loads((FIX / "reference.json").read_text())
        v = self.manifest["variants"][name]
        self.lang = v.get("case", name.split("-")[0])
        self.mic = read_wav(FIX / v["microphone"])
        self.system = read_wav(FIX / v["system"])
        self.gemini = json.loads((FIX / f"{name}-gemini.json").read_text())
        ref = self.manifest[self.lang]
        self.local = [(r["start"], r["end"]) for r in ref["local_turns"] + ref["backchannels"]]
        self.reference_units = [u for r in sorted(ref["local_turns"] + ref["backchannels"],
                                                  key=lambda r: r["start"]) for u in units(r["text"])]
        self.back_units = {r["start"]: units(r["text"]) for r in ref["backchannels"]}
        self.backchannels = ref["backchannels"]

    def is_local(self, word: GeminiWord, tol: float = .3) -> bool:
        mid = (word.start_sample + word.end_sample) / 2 / RATE
        return any(a - tol <= mid <= b + tol for a, b in self.local)

    def gate(self):
        enc = encoder()
        system_words = WebRtcWordGate().filter(self.system.tobytes(), gw(self.gemini["whole_system"]))
        ledger = SystemWordLedger()
        ledger.observe(system_words, len(self.system))
        voice = CrossLaneVoiceEchoGuard(threshold=.60)
        sys_emb = WeSpeakerWindowEmbeddings(enc)
        voice.observe_system(system_words, sys_emb(self.system.tobytes(), 0, system_words),
                             frontier=len(self.system))
        system_pcm = self.system.tobytes()
        acoustic = AcousticEchoGuard(lambda s, e: system_pcm[s * 2:e * 2])
        self.drops = {}
        return MicrophoneWordGate(WebRtcWordGate(), ledger, acoustic,
                                  lambda counts: [self.drops.__setitem__(k, self.drops.get(k, 0) + v)
                                                  for k, v in counts.items()],
                                  voice_guard=voice, embedding_source=WeSpeakerWindowEmbeddings(enc)), system_words

    def rolling(self, gate, extra=None):
        """Words the live path publishes: each window owns words ending in (previous frontier, t]."""
        kept = []
        frontier = 0
        memo = self.memo()
        for w in self.gemini["rolling"]:
            start, t = int(w["start_s"] * RATE), int(w["end_s"] * RATE)
            if not w.get("skipped"):
                pcm = self.mic[start:t].tobytes()
                if (start, t) not in memo:
                    memo[(start, t)] = gate.filter(pcm, gw(w["words"], w["start_s"]), offset_sample=start)
                words = memo[(start, t)]
                if extra is not None:
                    words = extra(words, pcm, (start, t, frontier), "rolling")
                kept.extend(x for x in words if frontier < x.end_sample <= t)
            frontier = t
        return kept

    def terminal(self, gate, system_words, extra=None):
        mic_pcm = self.mic.tobytes()
        memo = self.memo()
        if "terminal" not in memo:
            words = WebRtcWordGate().filter(mic_pcm, gw(self.gemini["whole_mic"]))
            memo["terminal"] = gate.filter_terminal(mic_pcm, words, system_words, system_pcm16=self.system.tobytes())
        words = memo["terminal"]
        if extra is not None:
            words = extra(words, mic_pcm, (0, len(self.mic), -1), "terminal")
        return list(words)

    def memo(self):
        """Gated words per window, persisted: the production chain is deterministic for fixed inputs."""
        if "_memo" not in self.__dict__:
            path = FIX / f"{self.name}-gated.json"
            self._memo_path = path
            self._memo = {}
            if path.exists():
                for key, rows in json.loads(path.read_text()).items():
                    k = key if key == "terminal" else tuple(int(x) for x in key.split(":"))
                    self._memo[k] = tuple(GeminiWord(*r) for r in rows)
        return self._memo

    def save_memo(self):
        self._memo_path.write_text(json.dumps({
            (k if k == "terminal" else f"{k[0]}:{k[1]}"): [[w.text, w.speaker, w.start_sample, w.end_sample] for w in v]
            for k, v in self._memo.items()}, ensure_ascii=False))

    def score(self, words):
        words = sorted(words, key=lambda w: w.start_sample)
        local = [w for w in words if self.is_local(w)]
        stray = [w for w in words if not self.is_local(w)]
        hyp = [u for w in local for u in units(w.text)]
        retained = lcs(self.reference_units, hyp)
        back_kept = 0
        for r in self.backchannels:
            got = [u for w in local if r["start"] - .3 <= (w.start_sample + w.end_sample) / 2 / RATE <= r["end"] + .3
                   for u in units(w.text)]
            back_kept += lcs(units(r["text"]), got)
        return {"retained": retained, "reference": len(self.reference_units),
                "backchannel_units_kept": back_kept,
                "backchannel_units": sum(len(units(r["text"])) for r in self.backchannels),
                "stray_words": len(stray),
                "stray": [(w.text, round(w.start_sample / RATE, 2), round(w.end_sample / RATE, 2)) for w in stray]}
