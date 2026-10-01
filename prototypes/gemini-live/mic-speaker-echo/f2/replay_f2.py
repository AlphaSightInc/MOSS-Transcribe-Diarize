"""The production Gemini live engine on two lane wavs, provider answers recorded once and replayed (throwaway).

R5-D's `replay.py` method, restated for R5-F2: own evidence folder and ledger (cap $0.25), R5-D's recorded
answers read in place (never written), and the candidate applied as a patch.

    PYTHON f2/replay_f2.py <out-run> <system.wav> <mic.wav> [--answers <recorded-run>] [--candidate [json]]
                           [--donor <recorded-run>] [--record] [--w3 replay|donor|none|record]

  --answers   name the recorded answers belong to (instant-word file `<name>-w3.json`); default <out-run>
  --donor     unrecorded microphone requests take the donor run's answer of the same length (same words and
              times, new audio levels: only the product's gates respond) and its instant words
  --record    unrecorded requests are paid for (ledger first) and written under this run's name
  --candidate apply candidate.py (optional JSON of parameter overrides)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT), str(HERE)]
import ledger  # noqa: E402
import provider  # noqa: E402
import moss_transcribe_diarize.app.gemini_lane_engine as lane_engine  # noqa: E402
import moss_transcribe_diarize.app.gemini_live_words as live_words  # noqa: E402
import moss_transcribe_diarize.app.phase2_web_cli as cli  # noqa: E402
from moss_transcribe_diarize.app.live_session import AudioFrame  # noqa: E402

S = 16000
RUN, SYSTEM_WAV, MIC_WAV = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])


def option(name: str, default=None):
    at = sys.argv.index(name) + 1 if name in sys.argv else None
    return sys.argv[at] if at is not None and at < len(sys.argv) else default


RECORD = "--record" in sys.argv
ANSWERS = option("--answers", RUN.split("/")[-1])
DONOR = option("--donor")
W3_MODE = option("--w3", "record" if RECORD else ("donor" if DONOR else "replay"))
PREFIX = 3.0
OUT = ledger.EV / "runs" / RUN
RAWS = provider.RAWS
w3_file = provider.w3_file
MANIFEST = Path.home() / ".local/share/moss-transcribe-diarize/live/live-provider-manifest.json"
REAL_CLIENT = cli._gemini_client
RealLiveWords = live_words.GeminiLiveWordSource
w3_events: dict[str, list] = {"system": [], "microphone": []}
gates: list[dict] = []


class LiveWords:
    """Record the real instant-word socket of one lane, or replay its recorded events."""

    def __init__(self, client, report):
        self.lane = next(cell.cell_contents for cell in report.__closure__
                         if cell.cell_contents in ("system", "microphone"))
        self.report = report
        source = w3_file(DONOR if W3_MODE == "donor" else ANSWERS) if W3_MODE in ("replay", "donor") else None
        tab_source = w3_file(option("--w3-system-from")) if option("--w3-system-from") else None
        self.real = None
        self.events = []
        if self.lane == "system" and tab_source is not None:
            self.events = list(json.loads(tab_source.read_text())["system"])
        elif W3_MODE == "record":
            self.real = RealLiveWords(client._client(), report)
        elif source is not None:
            self.events = list(json.loads(source.read_text())[self.lane])
        self.replayed = list(self.events)
        self.sent = 0

    def bind(self, listener):
        self.listener = listener
        if self.real is not None:
            def heard(text, start, end, final):
                w3_events[self.lane].append([text, start, end, final])
                listener(text, start, end, final)
            self.real.bind(heard)

    def push_audio(self, start_sample, pcm16):
        self.sent = start_sample + len(pcm16) // 2
        if self.real is not None:
            return self.real.push_audio(start_sample, pcm16)
        while self.events and self.events[0][2] <= self.sent:
            text, start, end, final = self.events.pop(0)
            self.listener(text, start, end, final)

    def observe_batch_words(self, spans):
        if self.real is not None:
            self.real.observe_batch_words(spans)

    async def finish(self):
        if self.real is not None:
            await self.real.finish()
            ledger.add(f"w3 {ANSWERS} {self.lane}", self.sent / S * ledger.LIVE_PER_S, seconds=self.sent / S,
                       basis="list_price_plus_output_estimate")
        elif W3_MODE == "record":
            w3_events[self.lane] = self.replayed

    def close(self):
        if self.real is not None:
            self.real.close()


def words_of(words):
    return [[w.text, w.speaker, round(w.start_sample / S, 2), round(w.end_sample / S, 2)] for w in words]


def trace(cls, name, stage, words_at):
    original = getattr(cls, name)

    def traced(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        gates.append({"stage": stage, "given": words_of(args[words_at]), "kept": words_of(result)})
        return result
    setattr(cls, name, traced)


def instrument():
    trace(lane_engine.AcousticEchoGuard, "filter", "acoustic_level_gate", 1)
    trace(lane_engine.CrossLaneVoiceEchoGuard, "_filter", "voice_echo_guard", 0)
    trace(lane_engine.TextEchoGuard, "filter_voice_aware", "text_echo_guard", 0)
    record = lane_engine.MicrophoneWordGate._record

    def recorded_summary(self, before, acoustic, after_voice, after_text, unanchored=0, lane_withheld=0):
        gates.append({"stage": "window_summary", "after_voice_activity_gate": before, "after_acoustic": acoustic,
                      "after_voice_guard": after_voice, "after_text_guard": after_text,
                      "dropped_unanchored": unanchored, "withheld_lane": lane_withheld,
                      "local_speech_seen": self.local_speech_seen})
        return record(self, before, acoustic, after_voice, after_text, unanchored, lane_withheld)
    lane_engine.MicrophoneWordGate._record = recorded_summary
    for method, stage in (("filter", "mic_window"), ("filter_terminal", "mic_cleanup")):
        original = getattr(lane_engine.MicrophoneWordGate, method)

        def outer(self, pcm, words, *args, _original=original, _stage=stage, **kwargs):
            started = time.perf_counter()
            result = _original(self, pcm, words, *args, **kwargs)
            gates.append({"stage": _stage, "offset_s": kwargs.get("offset_sample", 0) / S, "seconds": len(pcm) / 2 / S,
                          "given": words_of(words), "kept": words_of(result),
                          "gate_ms": round((time.perf_counter() - started) * 1000, 1)})
            return result
        setattr(lane_engine.MicrophoneWordGate, method, outer)


def snapshot_row(rt, sid, e, note=None):
    snap = rt.snapshot(sid).to_dict()
    s = snap["session"]
    return {"e": round(e, 2), "note": note, "version": s["version"], "status": s["status"],
            "finalization_status": s["finalization_status"], "committed": s["committed_samples"],
            "effective": s["effective_transcript"], "provisional": s["provisional"],
            "diag": snap.get("engine_diagnostics")}


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    system = sf.read(str(SYSTEM_WAV), dtype="int16")[0]
    mic = sf.read(str(MIC_WAV), dtype="int16")[0]
    lead = int(PREFIX * S)
    floor = (np.random.default_rng(7).normal(0, 10 ** (-63 / 20), lead) * 32767).astype(np.int16)
    system = np.concatenate([np.zeros(lead, dtype=np.int16), system])
    mic = np.concatenate([floor, mic])
    total = min(len(system), len(mic))
    client = provider.Client(ANSWERS, record=RECORD, donor=DONOR, real_client=REAL_CLIENT)
    if W3_MODE == "record":
        lanes = 1 if option("--w3-system-from") else 2
        ledger.check(lanes * total / S * ledger.LIVE_PER_S, f"{ANSWERS} instant words {lanes} lane(s) {total / S:.0f}s")
    cli._gemini_client = lambda _key: client
    live_words.GeminiLiveWordSource = LiveWords
    candidate = None
    if "--candidate" in sys.argv:
        import candidate
        following = option("--candidate")
        candidate.install(**(json.loads(following) if following and following.startswith("{") else {}))
    instrument()
    work = tempfile.mkdtemp(prefix="r5f2-replay-")
    rt = cli._build_gemini_live_runtime_factory(argparse.Namespace(
        live_provider_manifest=str(MANIFEST), file_work_root=work))()
    sid = "replay"
    rt.create(session_id=sid, engine_settings={"transcription": {
        "vendor": "gemini", "model": "gemini-3.5-transcribe", "api_key": "recorded-provider"}})
    engines = rt._sessions[sid].engine._engines
    frame = rt.descriptor.frame_samples
    rows, last_version = [], None
    started = time.monotonic()

    def observe(e, note=None):
        nonlocal last_version
        row = snapshot_row(rt, sid, e, note)
        if row["version"] != last_version or note:
            last_version = row["version"]
            rows.append(row)
        return row

    def settle():
        for _ in range(2400):
            if all(engine._future is None or engine._future.done() for engine in engines.values()):
                return
            time.sleep(0.05)
        raise SystemExit("lane worker did not settle")

    for sequence, at in enumerate(range(0, total - frame + 1, frame)):
        s_pcm, m_pcm = system[at:at + frame], mic[at:at + frame]
        mixed = ((s_pcm.astype(np.int32) + m_pcm.astype(np.int32)) // 2).astype(np.int16)
        rt.accept_frame(sid, AudioFrame(sequence, mixed.tobytes(), frame, lane_pcm=(
            ("system", s_pcm.tobytes()), ("microphone", m_pcm.tobytes()))))
        end = at + frame
        if W3_MODE == "record":            # the instant-word socket needs real time
            delay = started + end / S - time.monotonic()
            if delay > 0:
                time.sleep(delay)
        elif end % (15 * S) == 0:
            settle()   # one rolling window per refresh tick, as in a real-time meeting whose calls return in time
        observe(end / S - PREFIX)
    observe(total / S - PREFIX, "before Stop")
    await rt.stop(sid, 300.0)
    observe(total / S - PREFIX, "completed (live transcript saved)")
    await rt.wait_terminal(sid)
    final = observe(total / S - PREFIX, "settled")
    (OUT / "snapshots.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    log = gates + (candidate.LOG if candidate else [])
    (OUT / "gates.jsonl").write_text("".join(json.dumps(g, ensure_ascii=False) + "\n" for g in log))
    (OUT / "receipt.json").write_text(json.dumps({
        "run": RUN, "answers": ANSWERS, "donor": DONOR, "system_wav": str(SYSTEM_WAV), "mic_wav": str(MIC_WAV),
        "prefix_s": PREFIX, "mode": "record" if RECORD else "replay", "w3": W3_MODE,
        "candidate": dict(candidate.PARAMS) if candidate else None,
        "candidate_counts": dict(candidate.COUNTS) if candidate else None,
        "finalization_status": final["finalization_status"], "batch_calls": client.calls,
        "wall_seconds": round(time.monotonic() - started, 1)}, indent=1))
    if W3_MODE == "record":
        RAWS[0].mkdir(parents=True, exist_ok=True)
        (RAWS[0] / f"{ANSWERS}-w3.json").write_text(json.dumps(w3_events, ensure_ascii=False, indent=1))
    print(json.dumps({"run": RUN, "mode": "record" if RECORD else "replay", "w3": W3_MODE,
                      "finalization": final["finalization_status"], "wall_s": round(time.monotonic() - started, 1),
                      "batch_calls": len(client.calls), "paid": sum(bool(c.get("paid")) for c in client.calls),
                      "donor_calls": sum(str(c["replayed"]).startswith("donor:") for c in client.calls)}))


asyncio.run(main())
