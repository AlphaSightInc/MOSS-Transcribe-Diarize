"""H1/H3: does a request-side field make the whole-recording answer keep names, punctuation and script? (throwaway)

    PY f3/s1_request.py <fixture> <variant> <prefix_s,...> [--pay] [--window <end_s>]
    fixture: any wav stem under the F3 or R5-D fixtures folder (sys-zhlatin-en, sys-zhlatin, en-k3, ...)
    variant: base | lang | vocab | sys | langvocab

One production whole-recording pass per leading-silence draw (`TerminalTranscriber` as composed for the system
lane: production `WindowDiarizer` request, parser, timestamp repair, identity policy, word gate, row builder).
The variant only adds request fields. Answers are recorded once and replayed at $0.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import f3lib  # noqa: E402
from f3lib import EV, FIX, RD_FIX, S  # noqa: E402

from moss_transcribe_diarize.app.gemini_final_policy import FinalWordPolicy, WebRtcWordGate  # noqa: E402
from moss_transcribe_diarize.app.gemini_lane_engine import WebRtcSpeechDetector  # noqa: E402
from moss_transcribe_diarize.app.gemini_long_final import LongFinalStitcher  # noqa: E402
from moss_transcribe_diarize.app.gemini_provider import TerminalTranscriber, WindowDiarizer  # noqa: E402

NAMES = ["media", "lab", "alan", "turing", "grace", "hopper", "microsoft", "google", "google", "computerphile"]
ZH_END = 20.6          # the Mandarin passage ends before this (R5-D's fixtures), seconds after the leading silence
# What the live rows of R5-D's recorded meeting give (f3lib.code_switched_phrases over its system rows).
LIVE_PHRASES = ["Media Lab", "Alan Turing", "Grace Hopper", "Microsoft", "Google", "Computerphile"]


def variant_fields(variant: str, fixture: str) -> dict:
    chinese = "zh" in fixture
    fields = {}
    if variant == "lang2":      # the other common spelling of the same hint
        fields["language_codes"] = ["zh-CN", "en-US"] if chinese else ["en-US"]
    elif variant == "lang3":    # Chinese only, script named
        fields["language_codes"] = ["zh-Hans"] if chinese else ["en"]
    elif "lang" in variant:
        fields["language_codes"] = ["cmn-Hans-CN", "en-US"] if chinese else ["en-US"]
    if variant == "text":
        fields["input_text"] = f3lib.INSTRUCTION
    if "vocab" in variant:
        fields["custom_vocabulary"] = LIVE_PHRASES if chinese else []
    if "sys" in variant:
        fields["system_instruction"] = f3lib.INSTRUCTION
    return fields


_encoder = None


def encoder():
    global _encoder
    if _encoder is None:
        from moss_transcribe_diarize.app.live_provider_bundle import LiveProviderBundleConfig, _identity_encoder
        _encoder = _identity_encoder(LiveProviderBundleConfig.from_manifest(f3lib.MANIFEST), interval_workers=3)
    return _encoder


def fixture_path(name: str) -> Path:
    for folder in (FIX, RD_FIX):
        if (folder / f"{name}.wav").is_file():
            return folder / f"{name}.wav"
    raise SystemExit(f"no fixture {name}")


def truth_of(name: str):
    path = FIX / f"{name}.truth.json"
    return json.loads(path.read_text()) if path.is_file() else None


def one(fixture: str, variant: str, prefix: float, pay: bool, window: float | None = None) -> dict:
    pcm = f3lib.read_pcm(fixture_path(fixture), prefix)
    if window is not None:
        pcm = pcm[:int(round(window * S)) * 2]
    label = f"{fixture}-{variant}-p{prefix:g}" + (f"-w{window:g}" if window is not None else "")
    client = f3lib.Client(label, variant_fields(variant, fixture), pay=pay)
    usage: list = []
    gate = WebRtcWordGate()
    terminal = TerminalTranscriber(WindowDiarizer(client, lambda **row: usage.append(row)),
                                   identity_policy=FinalWordPolicy(encoder()), stitcher=LongFinalStitcher(encoder()),
                                   report_usage=lambda **row: usage.append(row), word_gate=gate, source_lane="system",
                                   voiced_audio=WebRtcSpeechDetector())
    try:
        rows = terminal.transcribe(f3lib.Tape(pcm))
    except Exception as exc:
        return {"draw": label, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    call = client.calls[0]
    source = next(folder / call["file"] for folder in (f3lib.RAW, f3lib.RD_RAW) if (folder / call["file"]).is_file())
    raw, counts = f3lib.response_words(source, len(pcm) // 2)
    words = terminal.last_words
    out = {"draw": label, "seconds": len(pcm) / 2 / S, "replayed": call["replayed"], "answer": call["file"],
           "raw_words": len(raw), "kept_words": len(words), **counts,
           "dropped_by_word_gate": len(raw) - len(words),
           "zero_length_words": sum(w.end_sample <= w.start_sample for w in raw),
           "out_of_order_words": sum(b.start_sample < a.start_sample for a, b in zip(raw, raw[1:])),
           "rows": [[round(r.start_sample / S, 2), round(r.end_sample / S, 2), r.speaker, r.text] for r in rows]}
    text = "".join(r.text + " " for r in rows)
    if "zh" in fixture:
        cut = int((prefix + ZH_END) * S)
        zh = [w for w in words if w.start_sample < cut]
        zh_text = " ".join(w.text for w in zh)
        kept, missing = f3lib.kept_of(NAMES, f3lib.latin_tokens(zh_text))
        out.update({"names_kept_of_10": kept, "names_missing": missing,
                    "zh_punctuation": f3lib.punctuation(zh_text), "script": f3lib.script_of(zh_text),
                    "zh_units": len(f3lib.units(zh_text)), "zh_speakers": len({w.speaker for w in zh}),
                    "en_words": len(words) - len(zh), "en_punctuation": f3lib.punctuation(" ".join(
                        w.text for w in words if w.start_sample >= cut)),
                    "en_speakers": len({w.speaker for w in words if w.start_sample >= cut}),
                    "zh_text": "".join(w.text if w.text.isascii() is False else f" {w.text} " for w in zh)})
    else:
        out.update({"words": len(words), "punctuation": f3lib.punctuation(text),
                    "digits": sum(ch.isdigit() for ch in text)})
    truth = truth_of(fixture)
    if truth:
        shifted = [(a + prefix, b + prefix, s) for a, b, s in truth["turns"]]
        out["speaker_error"] = f3lib.speaker_error(
            [(r.start_sample / S, r.end_sample / S, r.speaker) for r in rows], shifted, len(pcm) / 2 / S)
        if truth.get("text"):
            expected = f3lib.units(truth["text"])
            got = f3lib.units(text)
            import difflib
            same = sum(b.size for b in difflib.SequenceMatcher(None, expected, got, autojunk=False).get_matching_blocks())
            out["units_kept_of_truth"] = [same, len(expected)]
    return out


def main():
    fixture, variant = sys.argv[1], sys.argv[2]
    prefixes = [float(v) for v in sys.argv[3].split(",")]
    pay = "--pay" in sys.argv
    window = float(sys.argv[sys.argv.index("--window") + 1]) if "--window" in sys.argv else None
    rows = [one(fixture, variant, prefix, pay, window) for prefix in prefixes]
    (EV / "runs").mkdir(parents=True, exist_ok=True)
    path = EV / "runs" / f"request-{fixture}-{variant}.json"
    known = {r["draw"]: r for r in (json.loads(path.read_text()) if path.is_file() else [])}
    known.update({r["draw"]: r for r in rows})
    path.write_text(json.dumps(list(known.values()), ensure_ascii=False, indent=1) + "\n")
    for r in rows:
        print(json.dumps({k: v for k, v in r.items() if k not in ("rows", "zh_text")}, ensure_ascii=False), flush=True)
        if "zh_text" in r:
            print("   ", r["zh_text"])
    print(json.dumps({"spent_usd": round(f3lib.spent(), 4), "cap": f3lib.CAP}))


if __name__ == "__main__":
    main()
