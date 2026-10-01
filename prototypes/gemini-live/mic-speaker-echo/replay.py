"""The production Gemini live engine on two lane wavs, with every provider answer recorded once and replayed (throwaway).

    with_key.sh PYTHON prototypes/gemini-live/mic-speaker-echo/replay.py <run> <system.wav> <mic.wav> --record   # paid, real time
    PYTHON prototypes/gemini-live/mic-speaker-echo/replay.py <run> <system.wav> <mic.wav>                        # $0, seconds

The engine is the product's own composition (`phase2_web_cli._build_gemini_live_runtime_factory`): two lane
engines, rolling windows, microphone gates, preview composer, Stop drain, clean-up. Only the provider is
swapped: batch requests go through a recorder keyed by the request bytes, and the instant-word socket is
recorded (text, turn start, sent position, final) and replayed at the same sent positions. Public or
synthetic audio only. Writes the same files as e2e_run.py, so e2e_analyze.py reads both, plus gates.jsonl:
every microphone gate decision with the words it was given and the words it kept.
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
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT), str(HERE)]
import ledger  # noqa: E402
import probe_batch  # noqa: E402
import moss_transcribe_diarize.app.gemini_lane_engine as lane_engine  # noqa: E402
import moss_transcribe_diarize.app.gemini_live_words as live_words  # noqa: E402
import moss_transcribe_diarize.app.phase2_web_cli as cli  # noqa: E402
from moss_transcribe_diarize.app.live_session import AudioFrame  # noqa: E402

S = 16000
RUN, SYSTEM_WAV, MIC_WAV = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
RECORD = "--record" in sys.argv
PREFIX = 3.0                       # same lead-in as the browser runs: both lanes quiet, then the content
OUT = ledger.EV / "runs" / RUN
W3 = ledger.EV / "provider-responses" / f"{RUN}-w3.json"
MANIFEST = Path.home() / ".local/share/moss-transcribe-diarize/live/live-provider-manifest.json"
REAL_CLIENT = cli._gemini_client
RealLiveWords = live_words.GeminiLiveWordSource
w3_events: dict[str, list] = {"system": [], "microphone": []}
gates: list[dict] = []


def option(name: str) -> str | None:
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else None


DONOR = option("--provider-words-from")   # a recorded run whose answers stand in for unrecorded requests of equal length


class Client(probe_batch.RecordingClient):
    def _client(self):
        if self._real is None:
            self._real = REAL_CLIENT(os.environ.get("GEMINI_API_KEY"))
        return self._real

    def create(self, *, model, input, generation_config):  # noqa: A002
        try:
            return super().create(model=model, input=input, generation_config=generation_config)
        except RuntimeError:
            if DONOR is None:
                raise
            # Gate-only variant: the microphone audio was re-levelled, so its request bytes are new. The donor
            # run's answer for the request of the same length is used: same words and times, new audio levels.
            seconds = self.calls[-1]["seconds"]
            for path in sorted(probe_batch.RAW.glob(f"{DONOR}-*-*.json")):
                recorded = json.loads(path.read_text())
                if "response" in recorded and abs(recorded["audio_seconds"] - seconds) < 0.01:
                    self.calls[-1]["replayed"] = f"donor:{path.name}"
                    data = recorded["response"]
                    return type("Response", (), {"model_dump": lambda self, **_k: data})()
            raise


class LiveWords:
    """Record the real instant-word socket of one lane, or replay its recorded events."""

    def __init__(self, client, report):
        self.lane = next(cell.cell_contents for cell in report.__closure__
                         if cell.cell_contents in ("system", "microphone"))
        self.report = report
        self.real = RealLiveWords(client._client(), report) if RECORD else None
        source = W3 if DONOR is None else W3.with_name(f"{DONOR}-w3.json")
        self.events = [] if RECORD else list(json.loads(source.read_text())[self.lane])
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
            ledger.add(f"replay {RUN} w3 {self.lane}", self.sent / S * ledger.LIVE_PER_S, seconds=self.sent / S,
                       basis="list_price_plus_output_estimate")

    def close(self):
        if self.real is not None:
            self.real.close()


def trim_in_units(segments, committed):
    """Feasibility probe only: the product's head trim with its tokens replaced by the lane composer's
    comparable units (a CJK character each, other runs whole). Same window, same `_repeated_head` rule."""
    from dataclasses import replace
    from moss_transcribe_diarize.app.gemini_lane_engine import _preview_units
    from moss_transcribe_diarize.app.gemini_live_runtime import _repeated_head
    lane_units: dict = {}
    for segment in segments:
        lane_units[segment.source_lane] = lane_units.get(segment.source_lane, 0) + len(_preview_units(segment.text))
    kept = []
    for segment in segments:
        lane = segment.source_lane
        limit = max(60, lane_units[lane] * 5 // 4 + 8)
        parts = [row.text for row in reversed(kept) if row.source_lane == lane]
        count = sum(len(_preview_units(text)) for text in parts)
        for row in reversed(committed):
            if count >= limit:
                break
            if row.source_lane == lane:
                parts.append(row.text)
                count += len(_preview_units(row.text))
        tail = [unit for text in reversed(parts) for unit, _, _ in _preview_units(text)][-limit:]
        spans = _preview_units(segment.text)
        cut = _repeated_head(tail, [unit for unit, _, _ in spans])
        text = segment.text[spans[cut - 1][2]:].lstrip(" \t\r\n,.;:!?，。；：！？、") if cut else segment.text
        if text:
            kept.append(replace(segment, text=text))
    return tuple(kept)


def words_of(words):
    return [[w.text, w.speaker, round(w.start_sample / S, 2), round(w.end_sample / S, 2)] for w in words]


def trace(cls, name, stage, words_at):
    original = getattr(cls, name)

    def traced(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        given = args[words_at]
        gates.append({"stage": stage, "given": words_of(given), "kept": words_of(result)})
        return result
    setattr(cls, name, traced)


def instrument():
    # [DEBUG-r5d] microphone gate stages, in the order MicrophoneWordGate applies them
    trace(lane_engine.AcousticEchoGuard, "filter", "acoustic_level_gate", 1)
    trace(lane_engine.CrossLaneVoiceEchoGuard, "_filter", "voice_echo_guard", 0)
    trace(lane_engine.TextEchoGuard, "filter_voice_aware", "text_echo_guard", 0)
    record = lane_engine.MicrophoneWordGate._record

    def recorded(self, before, acoustic, after_voice, after_text, unanchored=0, lane_withheld=0):
        gates.append({"stage": "window_summary", "after_voice_activity_gate": before, "after_acoustic": acoustic,
                      "after_voice_guard": after_voice, "after_text_guard": after_text,
                      "dropped_unanchored": unanchored, "withheld_lane": lane_withheld,
                      "local_speech_seen": self.local_speech_seen})
        return record(self, before, acoustic, after_voice, after_text, unanchored, lane_withheld)
    lane_engine.MicrophoneWordGate._record = recorded
    for method, stage in (("filter", "mic_window"), ("filter_terminal", "mic_cleanup")):
        original = getattr(lane_engine.MicrophoneWordGate, method)

        def outer(self, pcm, words, *args, _original=original, _stage=stage, **kwargs):
            result = _original(self, pcm, words, *args, **kwargs)
            gates.append({"stage": _stage, "offset_s": kwargs.get("offset_sample", 0) / S, "seconds": len(pcm) / 2 / S,
                          "given": words_of(words), "kept": words_of(result)})
            return result
        setattr(lane_engine.MicrophoneWordGate, method, outer)


def snapshot_row(rt, sid, e, note=None):
    snap = rt.snapshot(sid).to_dict()
    s = snap["session"]
    return {"t": int(time.time() * 1000), "e": round(e, 2), "note": note, "version": s["version"], "status": s["status"],
            "finalization_status": s["finalization_status"], "accepted": s["accepted_samples"],
            "committed": s["committed_samples"], "canonical_through": s["canonical_through_sample"],
            "effective": s["effective_transcript"], "provisional": s["provisional"],
            "pending": snap.get("pending_work_items"), "diag": snap.get("engine_diagnostics")}


def document(row):
    return {"transcript": {"segments": [
        {"start": r["start_sample"] / S, "end": r["end_sample"] / S, "speaker": r.get("canonical_speaker") or "Speaker TBD",
         "text": r["text"], "source_lane": r.get("source_lane")} for r in row["effective"]]}}


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    system = sf.read(str(SYSTEM_WAV), dtype="int16")[0]
    mic = sf.read(str(MIC_WAV), dtype="int16")[0]
    lead = int(PREFIX * S)
    floor = (np.random.default_rng(7).normal(0, 10 ** (-63 / 20), lead) * 32767).astype(np.int16)
    system = np.concatenate([np.zeros(lead, dtype=np.int16), system])
    mic = np.concatenate([floor, mic])
    if "--silent-mic" in sys.argv:      # round 5: a source that is not recorded is a lane of digital zeros
        mic = np.zeros(len(mic), dtype=np.int16)
    total = min(len(system), len(mic))
    if RECORD:
        ledger.check(2 * (15 + 30 + 45 + 15) * ledger.BATCH_PER_S + 2 * 45 * ledger.LIVE_PER_S, f"replay-record {RUN}")
    client = Client(RUN, share=True)
    client.may_pay = RECORD   # a replay never reaches the provider
    cli._gemini_client = lambda _key: client
    live_words.GeminiLiveWordSource = LiveWords
    instrument()
    if "--trim-in-units" in sys.argv:
        import moss_transcribe_diarize.app.gemini_live_runtime as runtime_module
        runtime_module._trim_committed_preview = trim_in_units
    work = tempfile.mkdtemp(prefix="r5d-replay-")
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
        if RECORD:
            delay = started + end / S - time.monotonic()
            if delay > 0:
                time.sleep(delay)
        elif end % (15 * S) == 0:
            settle()   # one rolling window per refresh tick, as in a real-time meeting whose calls return in time
        observe(end / S - PREFIX)
    before_stop = observe(total / S - PREFIX, "before Stop")
    await rt.stop(sid, 300.0)
    live = observe(total / S - PREFIX, "completed (live transcript saved)")
    await rt.wait_terminal(sid)
    final = observe(total / S - PREFIX, "settled")
    (OUT / "snapshots.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    (OUT / "rows.jsonl").write_text("")
    (OUT / "gates.jsonl").write_text("".join(json.dumps(g, ensure_ascii=False) + "\n" for g in gates))
    (OUT / "saved-meeting-live.json").write_text(json.dumps(document(live), ensure_ascii=False, indent=1))
    (OUT / "saved-meeting.json").write_text(json.dumps(document(final), ensure_ascii=False, indent=1))
    (OUT / "engine.json").write_text(json.dumps(final["diag"], indent=1))
    (OUT / "receipt.json").write_text(json.dumps({
        "run": RUN, "system_wav": SYSTEM_WAV.name, "mic_wav": MIC_WAV.name, "prefix_s": PREFIX,
        "mode": "record" if RECORD else "replay", "finalization_status": final["finalization_status"],
        "batch_calls": client.calls, "wall_seconds": round(time.monotonic() - started, 1)}, indent=1))
    if RECORD:
        W3.parent.mkdir(parents=True, exist_ok=True)
        W3.write_text(json.dumps(w3_events, ensure_ascii=False, indent=1))
    print(json.dumps({"run": RUN, "mode": "record" if RECORD else "replay", "snapshots": len(rows),
                      "finalization": final["finalization_status"], "wall_s": round(time.monotonic() - started, 1),
                      "batch_calls": len(client.calls), "replayed_calls": sum(bool(c["replayed"]) for c in client.calls),
                      "w3_events": {k: len(v) for k, v in w3_events.items()} if RECORD else "replayed",
                      "calls_by_kind": final["diag"]["calls_by_kind"]}))
    _ = before_stop


asyncio.run(main())
