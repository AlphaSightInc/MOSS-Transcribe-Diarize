"""R5-F1 T2 ($0): the production Gemini live engine on R5-D's recorded provider answers, one trim arm
patched in, every trim call captured (throwaway; adapted from R5-D's ../replay.py, replay mode only).

    PYTHON prototypes/gemini-live/mic-speaker-echo/f1/capture.py <cell> <arm> [--lag 3.5] [--silent-mic]
           [--w3-from <cell>] [--mic <wav name>]

<cell> names R5-D's recorded cell (rp-short-aec40 ...): batch answers are looked up by request bytes
under R5-D's provider-responses/ (read only), instant-word events are replayed at their sent
positions. It cannot reach the provider (no key, may_pay False). Differences from R5-D's replay:
- writes under P72/f1/runs/<cell>-<arm>[-lagN]/, never into R5-D's folder;
- `--lag s`: a rolling answer is released s seconds of audio after its window tick (real-time
  recordings published the 15 s frontier at 18.5 s; R5-D's replay publishes it at 15.0 s);
- every call of the patched `_trim_committed_preview` is written to trim.jsonl with its inputs,
  so other arms can be scored offline on identical inputs.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
import threading
import time
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT), str(HERE.parent), str(HERE)]
import ledger  # noqa: E402  (R5-D's; only its EV path is used, nothing is added to its ledger)
import probe_batch  # noqa: E402
import trim as arms  # noqa: E402
import moss_transcribe_diarize.app.gemini_live_words as live_words  # noqa: E402
import moss_transcribe_diarize.app.phase2_web_cli as cli  # noqa: E402
from moss_transcribe_diarize.app import gemini_live_runtime as runtime_module  # noqa: E402
from moss_transcribe_diarize.app.live_session import AudioFrame  # noqa: E402

S = 16000
PREFIX = 3.0
F1EV = Path.home() / "Documents/Codex/2026-09-28/moss-gemini/evidence/P72/f1"
MANIFEST = Path.home() / ".local/share/moss-transcribe-diarize/live/live-provider-manifest.json"

parser = argparse.ArgumentParser()
parser.add_argument("cell")
parser.add_argument("arm")
parser.add_argument("--lag", type=float, default=0.0)
parser.add_argument("--silent-mic", action="store_true")
parser.add_argument("--w3-from")
parser.add_argument("--mic")
parser.add_argument("--system", default="sys-zhlatin-en.wav")
parser.add_argument("--tag", default="")
args = parser.parse_args()
FIX = ledger.EV / "fixtures"
MIC = FIX / (args.mic or f"mic-{args.cell.removeprefix('rp-')}.wav")
W3 = ledger.EV / "provider-responses" / f"{args.w3_from or args.cell}-w3.json"
NAME = f"{args.cell}{args.tag}-{args.arm}" + (f"-lag{args.lag:g}" if args.lag else "")
OUT = F1EV / "runs" / NAME
position = 0
calls: list[dict] = []


class Client(probe_batch.RecordingClient):
    """Recorded answers only. With --lag, an answer asked while a tick is open waits for its release."""

    lagging = False
    blocked = 0
    release = threading.Event()

    def create(self, *, model, input, generation_config):  # noqa: A002
        if Client.lagging:
            Client.blocked += 1
            Client.release.wait(120)
            Client.blocked -= 1
        return super().create(model=model, input=input, generation_config=generation_config)


class LiveWords:
    """Replay one lane's recorded instant-word events at their sent positions (R5-D's method)."""

    def __init__(self, client, report):
        self.lane = next(cell.cell_contents for cell in report.__closure__
                         if cell.cell_contents in ("system", "microphone"))
        self.events = list(json.loads(W3.read_text())[self.lane])
        self.sent = 0

    def bind(self, listener):
        self.listener = listener

    def push_audio(self, start_sample, pcm16):
        self.sent = start_sample + len(pcm16) // 2
        while self.events and self.events[0][2] <= self.sent:
            text, start, end, final = self.events.pop(0)
            self.listener(text, start, end, final)

    def observe_batch_words(self, spans):
        pass

    async def finish(self):
        pass

    def close(self):
        pass


def capturing(arm):
    def trim(segments, committed):
        started = time.perf_counter()
        kept = arm(segments, committed)
        calls.append({
            "at": position, "us": round((time.perf_counter() - started) * 1e6, 1),
            "segments": [[r.start_sample, r.end_sample, r.text, r.source_lane] for r in segments],
            "committed": [[r.start_sample, r.end_sample, r.text, r.source_lane] for r in committed],
            "kept": [[r.start_sample, r.end_sample, r.text, r.source_lane] for r in kept]})
        return kept
    return trim


def snapshot_row(rt, sid, e, note=None):
    s = rt.snapshot(sid).to_dict()["session"]
    return {"e": round(e, 2), "note": note, "version": s["version"], "status": s["status"],
            "accepted": s["accepted_samples"], "committed": s["committed_samples"],
            "effective": s["effective_transcript"], "provisional": s["provisional"]}


async def main():
    global position
    OUT.mkdir(parents=True, exist_ok=True)
    system = sf.read(str(FIX / args.system), dtype="int16")[0]
    mic = sf.read(str(MIC), dtype="int16")[0]
    lead = int(PREFIX * S)
    floor = (np.random.default_rng(7).normal(0, 10 ** (-63 / 20), lead) * 32767).astype(np.int16)
    system = np.concatenate([np.zeros(lead, dtype=np.int16), system])
    mic = np.concatenate([floor, mic])
    if args.silent_mic:
        mic = np.zeros(len(mic), dtype=np.int16)
    total = min(len(system), len(mic))
    client = Client(args.cell, share=True)
    client.may_pay = False
    cli._gemini_client = lambda _key: client
    live_words.GeminiLiveWordSource = LiveWords
    runtime_module._trim_committed_preview = capturing(arms.ARMS[args.arm])
    rt = cli._build_gemini_live_runtime_factory(argparse.Namespace(
        live_provider_manifest=str(MANIFEST), file_work_root=tempfile.mkdtemp(prefix="r5f1-")))()
    sid = "replay"
    rt.create(session_id=sid, engine_settings={"transcription": {
        "vendor": "gemini", "model": "gemini-3.5-transcribe", "api_key": "recorded-provider"}})
    engines = rt._sessions[sid].engine._engines
    frame = rt.descriptor.frame_samples
    lag = round(args.lag * S)
    assert lag % frame == 0
    rows, last_version = [], None
    started = time.monotonic()

    def observe(e, note=None):
        nonlocal last_version
        row = snapshot_row(rt, sid, e, note)
        if row["version"] != last_version or note:
            last_version = row["version"]
            rows.append(row)

    def pending():
        return [engine for engine in engines.values() if engine._future is not None and not engine._future.done()]

    def settle(until_blocked=False):
        for _ in range(24000):
            waiting = pending()
            if not waiting or (until_blocked and len(waiting) <= Client.blocked):
                return
            time.sleep(0.005)
        raise SystemExit("lane worker did not settle")

    release_at = None
    for sequence, at in enumerate(range(0, total - frame + 1, frame)):
        s_pcm, m_pcm = system[at:at + frame], mic[at:at + frame]
        mixed = ((s_pcm.astype(np.int32) + m_pcm.astype(np.int32)) // 2).astype(np.int16)
        end = at + frame
        position = end
        tick = end % (15 * S) == 0
        if tick and lag:
            Client.lagging = True
            Client.release.clear()
        rt.accept_frame(sid, AudioFrame(sequence, mixed.tobytes(), frame, lane_pcm=(
            ("system", s_pcm.tobytes()), ("microphone", m_pcm.tobytes()))))
        if tick and lag:
            settle(until_blocked=True)      # the tick's requests are now waiting for their answers
            release_at = end + lag
        elif tick:
            settle()
        if release_at is not None and end >= release_at:
            Client.lagging = False
            Client.release.set()
            settle()
            release_at = None
        observe(end / S - PREFIX)
    Client.lagging = False
    Client.release.set()
    settle()
    observe(total / S - PREFIX, "before Stop")
    await rt.stop(sid, 300.0)
    observe(total / S - PREFIX, "completed (live transcript saved)")
    await rt.wait_terminal(sid)
    observe(total / S - PREFIX, "settled")
    (OUT / "snapshots.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    (OUT / "trim.jsonl").write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in calls))
    receipt = {"run": NAME, "cell": args.cell, "arm": args.arm, "lag_s": args.lag, "system_wav": args.system,
               "mic_wav": "digital zeros" if args.silent_mic else MIC.name, "w3": W3.name, "prefix_s": PREFIX,
               "mode": "replay", "snapshots": len(rows), "trim_calls": len(calls),
               "batch_calls": len(client.calls), "replayed_calls": sum(bool(c["replayed"]) for c in client.calls),
               "paid_seconds": client.paid_seconds, "wall_seconds": round(time.monotonic() - started, 1)}
    (OUT / "receipt.json").write_text(json.dumps(receipt, indent=1))
    print(json.dumps(receipt))


asyncio.run(main())
