"""The production Gemini live engine on two lane wavs from recorded provider answers, with rule H optional (throwaway).

    PY f3/engine.py <run> <system.wav> <mic.wav|--silent-mic> [--donor rp-short-aec40] [--prefix 3.0]
        [--terminal-from <recorded answer.json> --shift <s>]    # another draw stands in as the system clean-up answer
        [--rule <min_run_s>]                                    # apply rule H (no flag = the product as it is)
        [--record]                                              # paid: new requests reach the provider (with_key.sh)

The composition is the product's own (`phase2_web_cli._build_gemini_live_runtime_factory`), as in R5-D's
`replay.py`; only the provider is swapped. Three observation points are added by monkeypatch, none edits a file:
 - live committed words per lane (what `_publish_window` commits), the witness rule H needs;
 - the whole-recording words after labels are final and before the word gates, where rule H inserts;
 - which lane/kind each provider request belongs to (to substitute one recorded draw for another).
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
import tempfile
import threading
import time
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "f3")]
import compose
compose.candidate.install()
import f3lib  # noqa: E402
import rule as rule_h  # noqa: E402
from f3lib import EV, RD_RAW, S, tup  # noqa: E402

import moss_transcribe_diarize.app.gemini_hybrid_engine as hybrid  # noqa: E402
import moss_transcribe_diarize.app.gemini_live_words as live_words  # noqa: E402
import moss_transcribe_diarize.app.gemini_provider as provider  # noqa: E402
import moss_transcribe_diarize.app.phase2_web_cli as cli  # noqa: E402
from moss_transcribe_diarize.app.live_session import AudioFrame  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("run"); p.add_argument("system_wav"); p.add_argument("mic_wav", nargs="?")
p.add_argument("--silent-mic", action="store_true")
p.add_argument("--donor", default=None)          # recorded run whose instant-word events are replayed
p.add_argument("--prefix", type=float, default=3.0)
p.add_argument("--terminal-from", default=None); p.add_argument("--shift", type=float, default=0.0)
p.add_argument("--rule", type=float, default=None)
p.add_argument("--raw-witness", action="store_true")   # sweep only: skip the one-owner step
p.add_argument("--drop", default=None)                 # LANE:START-END  remove the clean-up answer's words there
p.add_argument("--chunk", type=int, default=None); p.add_argument("--overlap", type=int, default=None)
p.add_argument("--inject", type=Path)
p.add_argument("--w", action="store_true")
p.add_argument("--f2", action="store_true")
p.add_argument("--record", action="store_true")
p.add_argument("--quiet", action="store_true")
A = p.parse_args()
EV = Path.home() / "Documents/Codex/2026-09-28/moss-gemini/evidence/P72/bc"
OUT = EV / "runs" / A.run
current = threading.local()
substituted = {"count": 0}


def lane_of(report) -> str:
    for cell in report.__closure__ or ():
        if cell.cell_contents in ("system", "microphone"):
            return cell.cell_contents
    return "?"


class EngineClient(f3lib.Client):
    def __init__(self, label, **kwargs):
        super().__init__(label, **kwargs)
        if A.f2:
            import importlib.util
            spec = importlib.util.spec_from_file_location("bc_recorded_provider", compose.F2 / "provider.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.f2 = module.Client(label, donor=A.donor)
            self.calls = self.f2.calls

    def find(self, digest, repeat):
        path = super().find(digest, repeat)
        if path is None:   # R5-D's replay rule: the same request bytes recorded at any attempt are replayed
            for folder in (f3lib.RAW, RD_RAW):
                hits = sorted(folder.glob(f"*-{digest}-*.json"))
                hits = [h for h in hits if not h.name.endswith(".error.json")]
                if hits:
                    return hits[0]
        if path is None:
            folder = Path.home() / "Documents/Codex/2026-09-28/moss-gemini/evidence/P72/f2/provider-responses"
            hits = sorted(folder.glob(f"*-{digest}-{repeat}.json")) or sorted(folder.glob(f"*-{digest}-*.json"))
            if hits:
                return hits[0]
        return path

    def create(self, *, model, input, generation_config):  # noqa: A002
        if A.f2:
            return self.f2.create(model=model, input=input, generation_config=generation_config)
        if A.terminal_from and getattr(current, "tag", None) == ("system", "terminal"):
            data = copy.deepcopy(json.loads(Path(A.terminal_from).read_text())["response"])
            for step in data.get("steps") or ():
                for content in step.get("content") or ():
                    for a in content.get("annotations") or ():
                        for key in ("start_offset", "end_offset"):
                            if a.get(key) is not None:
                                a[key] = f"{float(str(a[key]).rstrip('s')) + A.shift:.3f}s"
            substituted["count"] += 1
            return type("Response", (), {"model_dump": lambda self, **_k: data})()
        response = super().create(model=model, input=input, generation_config=generation_config)
        tag = getattr(current, "tag", None)
        if A.drop and tag == (A.drop.split(":")[0], "terminal"):
            # Injected omission: the recorded clean-up answer without its words in one stretch (times untouched).
            lo, hi = (float(v) for v in A.drop.split(":")[1].split("-"))
            data = copy.deepcopy(response.model_dump())
            for step in data.get("steps") or ():
                for content in step.get("content") or ():
                    content["annotations"] = [a for a in content.get("annotations") or ()
                                              if not lo <= float(str(a.get("start_offset", "0")).rstrip("s")) < hi]
            substituted["count"] += 1
            return type("Response", (), {"model_dump": lambda self, **_k: data})()
        return response


class LiveWords:
    """Replay of the recorded instant-word socket (grey preview only; it does not feed the saved text)."""

    def __init__(self, client, report):
        self.lane = lane_of(report)
        source = RD_RAW / f"{A.donor}-w3.json" if A.donor else None
        self.events = list(json.loads(source.read_text())[self.lane]) if source and source.is_file() else []

    def bind(self, listener):
        self.listener = listener

    def push_audio(self, start_sample, pcm16):
        sent = start_sample + len(pcm16) // 2
        while self.events and self.events[0][2] <= sent:
            text, start, end, final = self.events.pop(0)
            self.listener(text, start, end, final)

    def observe_batch_words(self, spans):
        pass

    async def finish(self):
        pass

    def close(self):
        pass


witness: dict[str, list] = {"system": [], "microphone": []}
frontiers: dict[str, list] = {"system": [], "microphone": []}   # the frontier in force when each word was committed
terminal_log: dict[str, dict] = {}


def patch():
    diarize = provider.WindowDiarizer.diarize

    def tagged(self, pcm16, **kwargs):
        current.tag = (lane_of(self.report_usage), kwargs.get("kind", "rolling"))
        try:
            return diarize(self, pcm16, **kwargs)
        finally:
            current.tag = None
    provider.WindowDiarizer.diarize = tagged

    publish_window = hybrid.GeminiHybridEngine._publish_window

    def observed(self, start, frontier, pcm, words, fallback=(), *, gate_words=True):
        old, seen, original = self._rolling_frontier, {}, self.registry.observe_window

        def spy(window_start_s, gated, embeddings=None, **kwargs):
            seen["words"] = tuple(gated)
            return original(window_start_s, gated, embeddings, **kwargs)
        self.registry.observe_window = spy
        try:
            publish_window(self, start, frontier, pcm, words, fallback, gate_words=gate_words)
        finally:
            del self.registry.observe_window
        if gate_words and self._rolling_frontier > old:
            # exactly the words `_publish_window` commits, with the provider's own (unclipped) times
            committed = [w for w in seen.get("words", ()) if old < w.end_sample <= frontier]
            witness[self.source_lane].extend(committed)
            frontiers[self.source_lane].extend(old for _ in committed)
    hybrid.GeminiHybridEngine._publish_window = observed

    if A.chunk:
        init = provider.TerminalTranscriber.__init__

        def small_chunks(self, diarizer, **kwargs):
            init(self, diarizer, **{**kwargs, "chunk_seconds": A.chunk, "overlap_seconds": A.overlap})
        provider.TerminalTranscriber.__init__ = small_chunks
    transcribe = provider.TerminalTranscriber.transcribe

    def observed_transcribe(self, tape):
        lane = self.source_lane
        whole = getattr(tape, "sample_offset", 0) == 0
        gate, original = self.word_gate, getattr(self.word_gate, "filter", None)
        log = terminal_log.setdefault(lane, {"calls": 0})
        injection = json.loads(A.inject.read_text()) if A.inject and lane == "microphone" and whole else None
        if injection:
            witness[lane] = [provider.GeminiWord(*w) for w in injection["witness"]]
            frontiers[lane] = [0] * len(witness[lane])
            log["injection_source"] = str(A.inject)

        first_word_gate = True
        def gated(pcm, words, **kwargs):
            nonlocal first_word_gate
            if kwargs or not whole or not first_word_gate:          # a rolling window (offset_sample given) or a tail interval
                return original(pcm, words, **kwargs)
            first_word_gate = False
            if injection:
                words = [provider.GeminiWord(*w) for w in injection["cleanup"]]
            log["before_rule"] = [tup(w) for w in words]
            log["raw_cleanup"] = tuple(words)
            restored = []
            if A.rule is not None and lane == "system":
                owned = rule_h.one_owner(witness[lane], frontiers[lane]) if not A.raw_witness else witness[lane]
                words, restored = rule_h.fill_holes(words, owned, min_run_samples=int(round(A.rule * S)),
                                                    skip=self.coverage_gaps)
            log["restored"] = restored
            kept = original(pcm, words, **kwargs)
            inserted = {(t, int(round(r["start_s"] * S))) for r in restored for t in r["text"]}
            log["restored_words"] = sum(len(r["text"]) for r in restored)
            log["restored_words_kept_by_word_gate"] = sum(
                1 for w in kept if any(w.text == t and r["start_s"] * S - 1 <= w.start_sample <= r["end_s"] * S
                                       for r in restored for t in r["text"])) if inserted else 0
            return kept
        if original is not None:
            gate.filter = gated
        mic_original = compose.candidate.filter_terminal
        def microphone_gated(gate_self, pcm, words, system_words, *, system_pcm16=None):
            if lane != "microphone" or not whole or A.rule is None:
                return mic_original(gate_self, pcm, words, system_words, system_pcm16=system_pcm16)
            owned = rule_h.one_owner(witness[lane], frontiers[lane])
            result, restored = compose.mic_restore(gate_self, pcm, words, owned, system_words,
                                                   system_pcm16, skip=self.coverage_gaps, raw_cleanup=log.get("raw_cleanup", words))
            log["restored"] = restored
            log["restored_words"] = sum(len(r["text"]) for r in restored)
            log["restored_words_kept_by_word_gate"] = log["restored_words"]
            return result
        from moss_transcribe_diarize.app.gemini_lane_engine import MicrophoneWordGate
        if lane == "microphone":
            MicrophoneWordGate.filter_terminal = microphone_gated
        identity_original = self.identity_policy.remap if self.identity_policy is not None else None
        if lane == "system" and A.w and self.identity_policy is not None:
            def identity_w(words, pcm):
                result, state = compose.w_labels(words, pcm, self.identity_policy.encoder, enabled=True)
                log["w_state"] = state
                return result
            self.identity_policy.remap = identity_w
        stitch_original = self.stitcher.stitch if self.stitcher is not None else None
        if lane == "system" and A.w and self.stitcher is not None:
            def stitch_w(chunks, pcm):
                result, state = compose.w_labels((), pcm, self.stitcher.encoder, enabled=True, chunks=chunks)
                log["w_state"] = state
                return result
            self.stitcher.stitch = stitch_w
        started = time.monotonic()
        try:
            rows = transcribe(self, tape)
        finally:
            log.pop("raw_cleanup", None)
            if lane == "microphone":
                MicrophoneWordGate.filter_terminal = mic_original
            if identity_original is not None and lane == "system" and A.w:
                self.identity_policy.remap = identity_original
            if stitch_original is not None and lane == "system" and A.w:
                self.stitcher.stitch = stitch_original
            if original is not None:
                del gate.filter
        log["calls"] += 1
        log["wall_s"] = round(time.monotonic() - started, 3)
        if whole:
            log["final_words"] = [tup(w) for w in self.last_words]
            log["coverage_gaps"] = [list(g) for g in self.coverage_gaps]
        return rows
    provider.TerminalTranscriber.transcribe = observed_transcribe


def snapshot_row(rt, sid, note=None):
    s = rt.snapshot(sid).to_dict()
    return {"note": note, "version": s["session"]["version"], "finalization_status": s["session"]["finalization_status"],
            "effective": s["session"]["effective_transcript"], "diag": s.get("engine_diagnostics")}


def document(row):
    return {"transcript": {"segments": [
        {"start": r["start_sample"] / S, "end": r["end_sample"] / S, "speaker": r.get("canonical_speaker") or "Speaker TBD",
         "text": r["text"], "source_lane": r.get("source_lane")} for r in row["effective"]]}}


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    lead = int(A.prefix * S)
    system = np.concatenate([np.zeros(lead, dtype=np.int16), sf.read(A.system_wav, dtype="int16")[0]])
    if A.silent_mic or not A.mic_wav:
        mic = np.zeros(len(system), dtype=np.int16)
    else:
        floor = (np.random.default_rng(7).normal(0, 10 ** (-63 / 20), lead) * 32767).astype(np.int16)
        mic = np.concatenate([floor, sf.read(A.mic_wav, dtype="int16")[0]])
    total = min(len(system), len(mic))
    assert not A.record, "BC is replay-only ($0)"
    client = EngineClient(A.run, pay=False)
    cli._gemini_client = lambda _key: client
    live_words.GeminiLiveWordSource = LiveWords
    patch()
    rt = cli._build_gemini_live_runtime_factory(argparse.Namespace(
        live_provider_manifest=str(f3lib.MANIFEST), file_work_root=tempfile.mkdtemp(prefix="r5f3-")))()
    sid = "replay"
    rt.create(session_id=sid, engine_settings={"transcription": {
        "vendor": "gemini", "model": "gemini-3.5-transcribe", "api_key": "recorded-provider"}})
    engines = rt._sessions[sid].engine._engines
    frame = rt.descriptor.frame_samples
    started = time.monotonic()

    def settle():
        for _ in range(4800):
            if all(e._future is None or e._future.done() for e in engines.values()):
                return
            time.sleep(0.05)
        raise SystemExit("lane worker did not settle")

    for sequence, at in enumerate(range(0, total - frame + 1, frame)):
        s_pcm, m_pcm = system[at:at + frame], mic[at:at + frame]
        mixed = ((s_pcm.astype(np.int32) + m_pcm.astype(np.int32)) // 2).astype(np.int16)
        rt.accept_frame(sid, AudioFrame(sequence, mixed.tobytes(), frame, lane_pcm=(
            ("system", s_pcm.tobytes()), ("microphone", m_pcm.tobytes()))))
        if (at + frame) % (15 * S) == 0:
            settle()
    before_stop = snapshot_row(rt, sid, "before Stop")
    await rt.stop(sid, 300.0)
    live = snapshot_row(rt, sid, "completed (live transcript saved)")
    stop_done = time.monotonic()
    await rt.wait_terminal(sid)
    final = snapshot_row(rt, sid, "settled")
    (OUT / "saved-meeting-before-stop.json").write_text(json.dumps(document(before_stop), ensure_ascii=False, indent=1))
    (OUT / "saved-meeting-live.json").write_text(json.dumps(document(live), ensure_ascii=False, indent=1))
    (OUT / "saved-meeting.json").write_text(json.dumps(document(final), ensure_ascii=False, indent=1))
    (OUT / "witness.json").write_text(json.dumps({k: [tup(w) + [f] for w, f in zip(v, frontiers[k])]
                                                  for k, v in witness.items()}, ensure_ascii=False))
    (OUT / "mic-restores.json").write_text(json.dumps(compose.LOG, ensure_ascii=False, indent=1))
    (OUT / "f2-gates.json").write_text(json.dumps(compose.candidate.LOG, ensure_ascii=False, indent=1))
    (OUT / "terminal.json").write_text(json.dumps(terminal_log, ensure_ascii=False))
    (OUT / "engine.json").write_text(json.dumps(final["diag"], indent=1))
    receipt = {"run": A.run, "args": {k: str(v) if isinstance(v, Path) else v for k, v in vars(A).items()}, "finalization_status": final["finalization_status"],
               "batch_calls": client.calls, "substituted_terminal_answers": substituted["count"],
               "cleanup_wall_s": round(time.monotonic() - stop_done, 2), "wall_seconds": round(time.monotonic() - started, 1), "cost_usd": 0, "w_enabled": A.w, "holes_use_raw_cleanup": True, "single_terminal_observation": True, "production_modules": {"provider": provider.__file__, "hybrid": hybrid.__file__, "cli": cli.__file__}}
    (OUT / "receipt.json").write_text(json.dumps(receipt, indent=1))
    if not A.quiet:
        print(json.dumps({"run": A.run, "finalization": final["finalization_status"], "calls": len(client.calls),
                          "replayed": sum(bool(c["replayed"]) for c in client.calls),
                          "substituted": substituted["count"], "cleanup_wall_s": receipt["cleanup_wall_s"],
                          "restored": {lane: log.get("restored") for lane, log in terminal_log.items()}},
                         ensure_ascii=False))


asyncio.run(main())
