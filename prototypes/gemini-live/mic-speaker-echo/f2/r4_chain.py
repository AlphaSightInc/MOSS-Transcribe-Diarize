"""Round-4 negative lanes through the product's microphone gate, today's rule and the candidate (throwaway).

    with_key.sh PYTHON f2/r4_chain.py terminal r4:A-listen-sp r4:B-listen-sp --record     # paid once
    with_key.sh PYTHON f2/r4_chain.py windows  r4:B-listen-sp 30,150,270,390 --record     # 30 s live windows ending there
    PYTHON f2/r4_chain.py terminal r4:A-listen-sp r4:B-listen-sp                          # $0 afterwards
    ... [--params '{"min_words": 4}']

The provider answers come from the product's own request path (WindowDiarizer; the saved pass through
TerminalTranscriber with the product's identity policy and word gate). The gate is the product's composition
(voice-activity word gate, level gate, voice guard, text guard, anchor). The tab lane's words are NOT bought: with
no tab words the voice and text guards drop nothing, so more words reach the anchor than in the product. A count
of 0 here is therefore an upper bound that holds in the product.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import soundfile as sf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT), str(HERE)]
import candidate  # noqa: E402
import fixtures  # noqa: E402
import ledger  # noqa: E402
import provider  # noqa: E402
from moss_transcribe_diarize.app.gemini_final_policy import FinalWordPolicy, WebRtcWordGate  # noqa: E402
from moss_transcribe_diarize.app.gemini_hybrid_engine import (WeSpeakerWindowEmbeddings,  # noqa: E402
                                                               attributed_embedding_intervals)
from moss_transcribe_diarize.app.gemini_lane_engine import (AcousticEchoGuard, CrossLaneVoiceEchoGuard,  # noqa: E402
                                                             MicrophoneWordGate, SystemWordLedger, WebRtcSpeechDetector)
from moss_transcribe_diarize.app.gemini_provider import GeminiWord, TerminalTranscriber, WindowDiarizer  # noqa: E402

S = 16000
MANIFEST = Path.home() / ".local/share/moss-transcribe-diarize/live/live-provider-manifest.json"
TODAY_LIVE, TODAY_TERMINAL = MicrophoneWordGate.filter, MicrophoneWordGate.filter_terminal
_encoder = None


def encoder():
    global _encoder
    if _encoder is None:
        from moss_transcribe_diarize.app.live_provider_bundle import LiveProviderBundleConfig, _identity_encoder
        _encoder = _identity_encoder(LiveProviderBundleConfig.from_manifest(MANIFEST), interval_workers=4)
    return _encoder


def gate(system_pcm: bytes) -> MicrophoneWordGate:
    tab_words = SystemWordLedger()
    tab_words.observe((), len(system_pcm) // 2)
    voice = CrossLaneVoiceEchoGuard(threshold=.60)
    voice.observe_system((), {}, frontier=len(system_pcm) // 2)
    return MicrophoneWordGate(WebRtcWordGate(), tab_words, AcousticEchoGuard(lambda a, b: system_pcm[a * 2:b * 2]),
                              None, voice_guard=voice, embedding_source=WeSpeakerWindowEmbeddings(encoder()))


def words_of(words):
    return [[w.text, w.speaker, round(w.start_sample / S, 2), round(w.end_sample / S, 2)] for w in words]


def longest_run(words) -> float:
    return max((( run[-1].end_sample - run[0].start_sample) / S for run in candidate.label_runs(words)), default=0.0)


def terminal(name: str, mic, tab, record: bool) -> dict:
    client = provider.Client(f"r4-{name.split(':')[1]}-terminal", record=record)
    given: list = []

    class Tape:
        sample_count = len(mic)
        def read(self, *, start_sample=0, end_sample=None):
            return mic[start_sample:self.sample_count if end_sample is None else end_sample].tobytes()
    transcriber = TerminalTranscriber(WindowDiarizer(client, lambda **_row: None), diarize=True,
                                      identity_policy=FinalWordPolicy(encoder()), word_gate=WebRtcWordGate(),
                                      word_filter=lambda words: given.extend(words) or (), source_lane="microphone",
                                      voiced_audio=WebRtcSpeechDetector())
    transcriber.transcribe(Tape())
    mic_pcm, tab_pcm = mic.tobytes(), tab.tobytes()
    today_gate, cand_gate, open_gate = gate(tab_pcm), gate(tab_pcm), gate(tab_pcm)
    today = TODAY_TERMINAL(today_gate, mic_pcm, given, (), system_pcm16=tab_pcm)
    open_gate.local_speech_seen = True         # what the echo guards alone let through (round 4's "104/73")
    survivors = TODAY_TERMINAL(open_gate, mic_pcm, given, (), system_pcm16=tab_pcm)
    candidate.LOG.clear()
    started = time.perf_counter()
    kept = candidate.filter_terminal(cand_gate, mic_pcm, given, (), system_pcm16=tab_pcm)
    return {"lane": name, "pass": "saved", "seconds": len(mic) / S, "paid_calls": sum(bool(c.get("paid")) for c in client.calls),
            "provider_words_after_voice_gate": len(given), "survive_echo_guards": len(survivors),
            "longest_surviving_run_s": round(longest_run(survivors), 2),
            "today_saved": len(today), "candidate_saved": len(kept), "candidate_saved_words": words_of(kept),
            "candidate_ms": round((time.perf_counter() - started) * 1000, 1),
            "added_ms": candidate.LOG[-1]["added_ms"],
            "runs_on_unexplained_audio": candidate.LOG[-1]["runs"], "survivors": words_of(survivors)}


def windows(name: str, mic, tab, ends: list[int], record: bool) -> list[dict]:
    client = provider.Client(f"r4-{name.split(':')[1]}-rolling", record=record)
    diarizer = WindowDiarizer(client, lambda **_row: None)
    out = []
    for end in ends:
        start = max(0, end - 30)
        pcm = mic[start * S:end * S].tobytes()
        tab_pcm = tab.tobytes()
        parsed = diarizer.diarize(pcm, deadline=time.monotonic() + 120, kind="rolling", diarize=True).words
        absolute = tuple(GeminiWord(w.text, w.speaker, w.start_sample + start * S, w.end_sample + start * S) for w in parsed)
        today = TODAY_LIVE(gate(tab_pcm), pcm, absolute, offset_sample=start * S)
        open_gate = gate(tab_pcm)
        voiced = open_gate.webrtc_gate.filter(pcm, absolute, offset_sample=start * S)
        survivors = open_gate.acoustic_gate.filter(pcm, voiced, offset_sample=start * S)
        candidate.LOG.clear()
        kept = candidate.filter_live(gate(tab_pcm), pcm, absolute, offset_sample=start * S)
        log = candidate.LOG[-1] if candidate.LOG else {"runs": [], "added_ms": None}
        out.append({"lane": name, "pass": "live", "window_s": [start, end],
                    "provider_words_after_voice_gate": len(voiced), "survive_level_gate": len(survivors),
                    "anchored_today": bool(attributed_embedding_intervals(survivors)),
                    "today_published": len(today), "candidate_published": len(kept),
                    "candidate_published_words": words_of(kept), "added_ms": log["added_ms"],
                    "runs_on_unexplained_audio": log["runs"], "survivors": words_of(survivors)})
    return out


def main():
    mode = sys.argv[1]
    record = "--record" in sys.argv
    if "--params" in sys.argv:
        candidate.PARAMS.update(json.loads(sys.argv[sys.argv.index("--params") + 1]))
    lanes = fixtures.r4_lanes()
    names = [a for a in sys.argv[2:] if a.startswith("r4:")]
    rows = []
    for name in names:
        mic_path, tab_path, _truth = lanes[name]
        mic, tab = sf.read(str(mic_path), dtype="int16")[0], sf.read(str(tab_path), dtype="int16")[0]
        if mode == "terminal":
            rows.append(terminal(name, mic, tab, record))
        else:
            ends = [int(v) for v in next(a for a in sys.argv[3:] if a[0].isdigit()).split(",")]
            rows.extend(windows(name, mic, tab, ends, record))
    out = ledger.EV / "runs" / (sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "r4")
    out.mkdir(parents=True, exist_ok=True)
    for row in rows:
        tag = row["lane"].split(":")[1] + ("-saved" if row["pass"] == "saved" else f"-live-{row['window_s'][1]}")
        (out / f"{tag}.json").write_text(json.dumps({**row, "params": dict(candidate.PARAMS)}, ensure_ascii=False, indent=1) + "\n")
        print(json.dumps({k: v for k, v in row.items() if k not in ("survivors", "runs_on_unexplained_audio")},
                         ensure_ascii=False))
        for run in row["runs_on_unexplained_audio"]:
            if run["weight_on_sustained"] >= 9 or run["local"]:
                print("    run", json.dumps(run, ensure_ascii=False))
    print(json.dumps(ledger.summary()))


if __name__ == "__main__":
    main()
