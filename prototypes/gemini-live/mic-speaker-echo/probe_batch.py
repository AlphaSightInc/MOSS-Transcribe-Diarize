"""S3b: where do Latin words and punctuation go between the live window and the clean-up pass?  (throwaway)

    prototypes/gemini-live/mic-speaker-echo/with_key.sh PYTHON prototypes/gemini-live/mic-speaker-echo/probe_batch.py \
        <label> <system.wav> [--mic]      # paid once per distinct request; replays from the recorded responses after

Sends the production requests (WindowDiarizer, production client options) for the live windows
[0,15] and [0,30] and for the whole recording, records every raw provider response under the
evidence folder (public/synthetic audio only), and prints each stage of the production
clean-up pipeline for the system lane with what it kept: words, Latin words, punctuation marks.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

import soundfile as sf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT), str(HERE)]
import ledger  # noqa: E402
from moss_transcribe_diarize.app.gemini_final_policy import FinalWordPolicy, WebRtcWordGate  # noqa: E402
from moss_transcribe_diarize.app.gemini_lane_engine import WebRtcSpeechDetector  # noqa: E402
from moss_transcribe_diarize.app.gemini_live_runtime import GeminiSegment  # noqa: E402
from moss_transcribe_diarize.app.gemini_long_final import LongFinalStitcher  # noqa: E402
from moss_transcribe_diarize.app.gemini_provider import (  # noqa: E402
    GeminiWord, TerminalTranscriber, WindowDiarizer, ordered_segments, parse_words, repair_word_timestamps,
    speaker_turns)

S = 16000
EV = ledger.EV
RAW = EV / "provider-responses"


class RecordingClient:
    """The production client; each raw response is written once and replayed for identical requests."""

    def __init__(self, label: str, *, share: bool = False):
        self.label = label
        self.share = share
        self.interactions = self
        self._real = None
        self.paid_seconds = 0.0
        self.calls: list[dict] = []

    def _client(self):
        if self._real is None:
            from moss_transcribe_diarize.app.phase2_web_cli import _gemini_client
            self._real = _gemini_client(os.environ.get("GEMINI_API_KEY"))
        return self._real

    def create(self, *, model, input, generation_config):  # noqa: A002
        digest = hashlib.sha256((input[0]["data"] + json.dumps(generation_config, sort_keys=True) + model)
                                .encode()).hexdigest()[:16]
        repeat = sum(1 for call in self.calls if call["digest"] == digest)
        path = RAW / f"{self.label}-{digest}-{repeat}.json"
        if self.share and not path.is_file():
            # The same request bytes recorded by another run (e.g. the shared system lane) are replayed, not re-paid.
            path = next(iter(sorted(RAW.glob(f"*-{digest}-{repeat}.json"))), path)
        seconds = (len(input[0]["data"]) * 3 // 4 - 44) / (2 * S)
        self.calls.append({"digest": digest, "seconds": seconds, "replayed": path.is_file()})
        if not path.is_file():
            ledger.check(seconds * ledger.BATCH_PER_S, f"{self.label} batch {seconds:.0f}s")
            response = self._client().interactions.create(model=model, input=input,
                                                          generation_config=generation_config)
            data = response.model_dump(exclude_none=True, mode="json")
            RAW.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"model": model, "generation_config": generation_config,
                                        "audio_seconds": seconds, "response": data}, ensure_ascii=False, indent=1))
            self.paid_seconds += seconds
            ledger.add(f"{self.label} batch {digest}", seconds * ledger.BATCH_PER_S, seconds=seconds,
                       basis="with_output_estimate")
        data = json.loads(path.read_text())["response"]

        class Response:
            def model_dump(self, **_kwargs):
                return data
        return Response()


def stats(words) -> dict:
    text = [w.text for w in words]
    joined = "".join(text)
    return {"words": len(words),
            "latin_words": sum(1 for t in text if re.search(r"[A-Za-z]", t)),
            "han_chars": sum(1 for ch in joined if "一" <= ch <= "鿿"),
            "punctuation": sum(1 for ch in joined if unicodedata.category(ch).startswith("P")),
            "zero_length": sum(1 for w in words if w.end_sample <= w.start_sample),
            "speakers": sorted({w.speaker for w in words})}


def raw_annotations(data: dict) -> list[dict]:
    return [a for step in data.get("steps") or () for content in step.get("content") or ()
            for a in content.get("annotations") or () if a.get("type") == "word_info"]


def trace_terminal(label: str, pcm: bytes, encoder, usage: list) -> dict:
    client = RecordingClient(f"{label}-terminal")
    diarizer = WindowDiarizer(client, lambda **row: usage.append(row))
    # 1. the production pass, as composed for the system lane in phase2_web_cli
    class Tape:
        sample_count = len(pcm) // 2
        def read(self, *, start_sample=0, end_sample=None):
            return pcm[start_sample * 2:(self.sample_count if end_sample is None else end_sample) * 2]
    gate = WebRtcWordGate()
    terminal = TerminalTranscriber(diarizer, identity_policy=FinalWordPolicy(encoder),
                                   stitcher=LongFinalStitcher(encoder), report_usage=lambda **row: usage.append(row),
                                   word_gate=gate, source_lane="system", voiced_audio=WebRtcSpeechDetector())
    rows = terminal.transcribe(Tape())
    # 2. the same stages one by one on the recorded response (single chunk: start 0, core = whole audio)
    path = sorted(RAW.glob(f"{label}-terminal-*-0.json"))[-1]
    data = json.loads(path.read_text())["response"]
    samples = len(pcm) // 2
    raw = raw_annotations(data)
    parsed = parse_words(data, audio_samples=samples)
    fixed, repaired = repair_word_timestamps(parsed.words, samples)
    core = [w for w in fixed if 0 <= (w.start_sample + w.end_sample) / 2 < samples]
    remapped = FinalWordPolicy(encoder).remap(core, pcm)
    gated = gate.filter(pcm, remapped)
    dropped = [w for w in remapped if w not in set(gated)]
    stages = {
        "raw_annotations": {"words": len(raw), "latin_words": sum(1 for a in raw if re.search(r"[A-Za-z]", a.get("text") or "")),
                            "punctuation": sum(1 for a in raw for ch in (a.get("text") or "")
                                               if unicodedata.category(ch).startswith("P")),
                            "without_start_offset": sum(1 for a in raw if a.get("start_offset") is None),
                            "without_end_offset": sum(1 for a in raw if a.get("end_offset") is None)},
        "parse_words": {**stats(parsed.words), "clamped": parsed.clamped, "dropped": parsed.dropped},
        "repair_word_timestamps": {**stats(fixed), "repaired": repaired},
        "core_filter": stats(core),
        "identity_remap": stats(remapped),
        "webrtc_word_gate": {**stats(gated), "dropped": [
            {"text": w.text, "start_s": w.start_sample / S, "end_s": w.end_sample / S} for w in dropped]},
        "rows": [{"start_s": r.start_sample / S, "end_s": r.end_sample / S, "speaker": r.speaker, "text": r.text}
                 for r in rows],
    }
    return {"stages": stages, "calls": client.calls, "response_file": path.name,
            "words": [{"text": w.text, "speaker": w.speaker, "start_s": w.start_sample / S, "end_s": w.end_sample / S}
                      for w in parsed.words]}


def trace_rolling(label: str, pcm: bytes, end_s: int, usage: list) -> dict:
    client = RecordingClient(f"{label}-rolling{end_s}")
    diarizer = WindowDiarizer(client, lambda **row: usage.append(row))
    cut = pcm[:end_s * S * 2]
    parsed = diarizer.diarize(cut, deadline=time.monotonic() + 120, kind="rolling", diarize=True)
    gated = WebRtcWordGate().filter(cut, parsed.words, offset_sample=0)
    rows = speaker_turns(ordered_segments(tuple(GeminiSegment(w.start_sample, max(w.end_sample, w.start_sample + 1),
                                                              w.text, w.speaker, "system") for w in gated),
                                          start_sample=0, end_sample=end_s * S, preserve_order=True))
    return {"window_s": [0, end_s], "parse_words": {**stats(parsed.words), "clamped": parsed.clamped,
                                                   "dropped": parsed.dropped},
            "webrtc_word_gate": stats(gated), "calls": client.calls,
            "rows": [{"start_s": r.start_sample / S, "end_s": r.end_sample / S, "speaker": r.speaker, "text": r.text}
                     for r in rows],
            "words": [{"text": w.text, "speaker": w.speaker, "start_s": w.start_sample / S, "end_s": w.end_sample / S}
                      for w in parsed.words]}


def main():
    label, wav = sys.argv[1], sys.argv[2]
    windows = [int(v) for v in sys.argv[3].split(",")] if len(sys.argv) > 3 and sys.argv[3] != "-" else [15, 30]
    pcm = sf.read(wav, dtype="int16")[0].tobytes()
    from moss_transcribe_diarize.app.live_provider_bundle import LiveProviderBundleConfig, _identity_encoder
    encoder = _identity_encoder(LiveProviderBundleConfig.from_manifest(
        Path.home() / ".local/share/moss-transcribe-diarize/live/live-provider-manifest.json"), interval_workers=3)
    usage: list = []
    out = {"label": label, "wav": wav, "seconds": len(pcm) / 2 / S,
           "rolling": [trace_rolling(label, pcm, end, usage) for end in windows],
           "terminal": trace_terminal(label, pcm, encoder, usage),
           "usage": [{k: v for k, v in row.items()} for row in usage]}
    (EV / "runs").mkdir(parents=True, exist_ok=True)
    (EV / "runs" / f"batch-{label}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    for window in out["rolling"]:
        print(f"rolling [0,{window['window_s'][1]}]  parse {window['parse_words']}  gate {window['webrtc_word_gate']}")
        for row in window["rows"]:
            print(f"    {row['start_s']:6.2f}-{row['end_s']:6.2f} {row['speaker']:8s} {row['text']}")
    for stage, value in out["terminal"]["stages"].items():
        if stage == "rows":
            for row in value:
                print(f"    {row['start_s']:6.2f}-{row['end_s']:6.2f} {row['speaker']:14s} {row['text']}")
        else:
            print(f"terminal {stage}: {value}")
    print("calls", [(c["seconds"], c["replayed"]) for w in out["rolling"] for c in w["calls"]] +
          [(c["seconds"], c["replayed"]) for c in out["terminal"]["calls"]])


if __name__ == "__main__":
    main()
