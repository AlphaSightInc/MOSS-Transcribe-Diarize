"""R5-F3 shared pieces (throwaway): paths, spend ledger, recording provider client with request variants, metrics.

Nothing here edits product code. The provider client is the production one (`phase2_web_cli._gemini_client`);
a request variant only adds fields to the request the production `WindowDiarizer` builds.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT), str(HERE)]

from moss_transcribe_diarize.app.gemini_lane_engine import _preview_units  # noqa: E402
from moss_transcribe_diarize.app.gemini_provider import parse_words, repair_word_timestamps  # noqa: E402

S = 16000
EV = Path.home() / "Documents/Codex/2026-09-28/moss-gemini/evidence/P72/f3"
RD = Path.home() / "Documents/Codex/2026-09-28/moss-gemini/evidence/P72/mic-speaker-echo"   # R5-D, read only
RAW, RD_RAW, FIX, RD_FIX = EV / "provider-responses", RD / "provider-responses", EV / "fixtures", RD / "fixtures"
LEDGER = EV / "spend.jsonl"
CAP, SAFETY = 0.35, 1.25
BATCH_PER_S = 0.0000547 + 0.002 / 60     # R5-D / P69 method: measured metered input + output estimate
MANIFEST = Path.home() / ".local/share/moss-transcribe-diarize/live/live-provider-manifest.json"

INSTRUCTION = ("Transcribe the audio verbatim. Keep every word in the language and script it was spoken in. "
               "Do not translate, drop or romanise names. Keep sentence punctuation.")


# ---------------------------------------------------------------- spend
def spent() -> float:
    return sum(json.loads(line)["usd"] for line in LEDGER.read_text().splitlines()) if LEDGER.is_file() else 0.0


def check(planned: float, label: str) -> None:
    known = spent()
    if known + SAFETY * planned > CAP:
        raise SystemExit(f"spend cap: {known:.4f} + 1.25 x {planned:.4f} > {CAP} ({label})")


def add(label: str, usd: float, **detail) -> None:
    EV.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as out:
        out.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "label": label, "usd": round(usd, 6),
                              **detail}) + "\n")


# ---------------------------------------------------------------- provider client
from moss_transcribe_diarize.app.phase2_web_cli import _gemini_client as REAL_CLIENT  # noqa: E402  (bound before any patch)


_CLIENT_LOCK = __import__("threading").Lock()


class Client:
    """Production client; every raw answer is written once and replayed for the same request bytes.

    variant: {"language_codes": [...], "custom_vocabulary": [...], "system_instruction": "..."} (any subset).
    The empty variant sends exactly the production request and replays R5-D's recordings by the same digest.
    """

    def __init__(self, label: str, variant: dict | None = None, *, pay: bool = False):
        self.label, self.variant, self.pay = label, dict(variant or {}), pay
        self.interactions = self
        self.calls: list[dict] = []
        self._real = None

    def _request(self, generation_config: dict) -> tuple[dict, dict]:
        config = copy.deepcopy(generation_config)
        for key in ("language_codes", "custom_vocabulary"):
            if self.variant.get(key):
                config["transcription_config"][key] = list(self.variant[key])
        extra = ({"system_instruction": self.variant["system_instruction"]}
                 if self.variant.get("system_instruction") else {})
        return config, extra

    def _input(self, input):  # noqa: A002
        if self.variant.get("input_text"):   # an instruction as a text part before the audio
            return [{"type": "text", "text": self.variant["input_text"]}, *input]
        return input

    def find(self, digest: str, repeat: int) -> Path | None:
        own = RAW / f"{self.label}-{digest}-{repeat}.json"
        if own.is_file():
            return own
        for folder in (RAW, RD_RAW):
            hits = sorted(folder.glob(f"*-{digest}-{repeat}.json"))
            if hits:
                return hits[0]
        return None

    def create(self, *, model, input, generation_config):  # noqa: A002
        config, extra = self._request(generation_config)
        digest = hashlib.sha256((input[0]["data"] + json.dumps(config, sort_keys=True) + model
                                 + (json.dumps(extra, sort_keys=True) if extra else "")
                                 + (self.variant.get("input_text") or "")).encode()).hexdigest()[:16]
        repeat = sum(1 for call in self.calls if call["digest"] == digest)
        seconds = (len(input[0]["data"]) * 3 // 4 - 44) / (2 * S)
        path = self.find(digest, repeat)
        self.calls.append({"digest": digest, "seconds": seconds, "replayed": path is not None,
                           "file": path.name if path else None})
        if path is None:
            if not self.pay:
                raise RuntimeError(f"replay: no recorded answer for {self.label} {digest} ({seconds:.1f} s)")
            check(seconds * BATCH_PER_S, f"{self.label} {seconds:.0f}s")
            with _CLIENT_LOCK:      # final chunks are decoded on three threads; one shared provider client
                if self._real is None:
                    self._real = REAL_CLIENT(os.environ.get("GEMINI_API_KEY"))
            if self._real is self:
                raise SystemExit("recording client would call itself")
            started = time.monotonic()
            try:
                response = self._real.interactions.create(model=model, input=self._input(input),
                                                          generation_config=config, **extra)
            except Exception as exc:
                # A rejected request is recorded (reason only) so it is never re-sent; it is not billed.
                RAW.mkdir(parents=True, exist_ok=True)
                (RAW / f"{self.label}-{digest}-{repeat}.error.json").write_text(json.dumps(
                    {"model": model, "generation_config": config, **extra, "audio_seconds": seconds,
                     "error": f"{type(exc).__name__}: {str(exc)[:400]}"}, ensure_ascii=False, indent=1))
                add(f"{self.label} {digest} REJECTED", 0.0, seconds=seconds, basis="rejected, not billed")
                raise
            data = response.model_dump(exclude_none=True, mode="json")
            RAW.mkdir(parents=True, exist_ok=True)
            path = RAW / f"{self.label}-{digest}-{repeat}.json"
            path.write_text(json.dumps({"model": model, "generation_config": config, **extra,
                                        "audio_seconds": seconds, "wall_seconds": round(time.monotonic() - started, 2),
                                        "response": data}, ensure_ascii=False, indent=1))
            add(f"{self.label} {digest}", seconds * BATCH_PER_S, seconds=seconds, basis="with_output_estimate")
            self.calls[-1]["file"] = path.name
        data = json.loads(path.read_text())["response"]
        return type("Response", (), {"model_dump": lambda self, **_k: data})()


# ---------------------------------------------------------------- audio and words
def read_pcm(path: Path | str, prefix_s: float = 0.0) -> bytes:
    audio = sf.read(str(path), dtype="int16")[0]
    return np.concatenate([np.zeros(int(round(prefix_s * S)), dtype=np.int16), audio]).tobytes()


class Tape:
    def __init__(self, pcm: bytes):
        self.pcm, self.sample_count = pcm, len(pcm) // 2

    def read(self, *, start_sample=0, end_sample=None):
        return self.pcm[start_sample * 2:(self.sample_count if end_sample is None else end_sample) * 2]


def response_words(path: Path, audio_samples: int | None = None):
    """Words of one recorded answer exactly as the production parser + timestamp repair give them."""
    recorded = json.loads(Path(path).read_text())
    samples = audio_samples if audio_samples is not None else int(round(recorded["audio_seconds"] * S))
    parsed = parse_words(recorded["response"], audio_samples=samples)
    fixed, repaired = repair_word_timestamps(parsed.words, samples)
    return fixed, {"clamped": parsed.clamped, "dropped": parsed.dropped, "repaired": repaired}


# ---------------------------------------------------------------- text measures
def units(text: str) -> list[str]:
    return [unit for unit, _, _ in _preview_units(text)]


def _only(char: str, codec: str, other: str) -> bool:
    try:
        char.encode(codec)
    except UnicodeEncodeError:
        return False
    try:
        char.encode(other)
    except UnicodeEncodeError:
        return True
    return False


def script_counts(text: str) -> dict:
    """Han characters that exist only in the simplified (GB2312) or only in the traditional (Big5) set.
    Standard-library codecs; no conversion table."""
    han = [ch for ch in text if "一" <= ch <= "鿿"]
    return {"han": len(han), "simplified_only": sum(_only(ch, "gb2312", "big5") for ch in han),
            "traditional_only": sum(_only(ch, "big5", "gb2312") for ch in han)}


def script_of(text: str) -> str:
    c = script_counts(text)
    if not c["simplified_only"] and not c["traditional_only"]:
        return "none"
    if c["simplified_only"] and c["traditional_only"]:
        return ("mixed(s%d/t%d)" % (c["simplified_only"], c["traditional_only"]))
    return "simplified" if c["simplified_only"] else "traditional"


def punctuation(text: str) -> int:
    return sum(1 for ch in text if unicodedata.category(ch).startswith("P"))


def latin_tokens(text: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[A-Za-z]+", text)]


def kept_of(expected: list[str], found: list[str]) -> tuple[int, list[str]]:
    """How many expected tokens (a multiset) are in `found`; returns (kept, missing)."""
    pool = list(found)
    missing = []
    for token in expected:
        if token in pool:
            pool.remove(token)
        else:
            missing.append(token)
    return len(expected) - len(missing), missing


def repeated_units(text: str, run: int = 5) -> int:
    """Units inside runs of >= `run` units that occur a second time later in the same text (G2)."""
    seq = units(text)
    seen: dict[tuple, int] = {}
    doubled = set()
    for i in range(len(seq) - run + 1):
        key = tuple(seq[i:i + run])
        if key in seen and i - seen[key] >= run:
            doubled.update(range(i, i + run))
        seen.setdefault(key, i)
    return len(doubled)


def code_switched_phrases(texts: list[str]) -> list[str]:
    """Runs of non-CJK letter words inside text that also holds CJK characters (what a vocabulary hint would
    carry from the live rows). Order of first appearance, no repeats."""
    out: list[str] = []
    for text in texts:
        if not any(unicodedata.name(ch, "").startswith(("CJK", "HIRAGANA", "KATAKANA")) for ch in text):
            continue
        for phrase in re.findall(r"[A-Za-z][A-Za-z']*(?: [A-Za-z][A-Za-z']*)*", text):
            if phrase not in out:
                out.append(phrase)
    return out


# ---------------------------------------------------------------- speaker error against exact truth
def speaker_error(rows, truth: list[tuple[float, float, object]], total_s: float) -> dict:
    """Frame (10 ms) diarization error with the best one-to-one label mapping, no collar.
    rows: (start_s, end_s, speaker); truth: (start_s, end_s, speaker)."""
    from scipy.optimize import linear_sum_assignment
    n = int(round(total_s * 100))
    ref = np.full(n, -1)
    hyp = np.full(n, -1)
    t_labels = sorted({str(s) for _, _, s in truth})
    h_labels = sorted({str(s) for _, _, s in rows})
    for a, b, s in truth:
        ref[int(round(a * 100)):int(round(b * 100))] = t_labels.index(str(s))
    for a, b, s in rows:
        hyp[int(round(a * 100)):int(round(b * 100))] = h_labels.index(str(s))
    speech = ref >= 0
    miss = int(np.sum(speech & (hyp < 0)))
    false_alarm = int(np.sum(~speech & (hyp >= 0)))
    both = speech & (hyp >= 0)
    table = np.zeros((len(t_labels), max(len(h_labels), 1)), dtype=int)
    for t, h in zip(ref[both], hyp[both]):
        table[t, h] += 1
    r, c = linear_sum_assignment(-table)
    confusion = int(both.sum() - table[r, c].sum())
    total = int(speech.sum())
    return {"der": round((miss + false_alarm + confusion) / total, 4), "miss_s": miss / 100,
            "false_alarm_s": false_alarm / 100, "confusion_s": confusion / 100, "speech_s": total / 100,
            "hyp_speakers": len(h_labels), "truth_speakers": len(t_labels)}


def tup(word) -> list:
    return [word.text, word.speaker, word.start_sample, word.end_sample]
