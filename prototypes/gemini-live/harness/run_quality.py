"""Local H1-shape quality replay through any Account Live HTTPS stack.

One command: PYTHONDONTWRITEBYTECODE=1 <worktree>.venv/bin/python
    prototypes/gemini-live/harness/run_quality.py --base-url https://127.0.0.1:18500 --out <dir>

The optional --case/--passes flags produce partial per-case metrics; only a
12-session run emits the H1 content-free-metrics projection.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import threading
import time
import wave

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "prototypes/gemini-live/common"))

from corpus import clips
from latency_probe import LatencyProbe
from moss_transcribe_diarize.phase2_acceptance import QUALITY_CASE_IDS
from moss_transcribe_diarize.phase2_acceptance_external import (
    ExternalMeasurementError, _load_surface_harness, _quality_projection, _quality_speaker_intervals,
    _quality_surface_observations, _quality_window_coverage, _verify_quality_inputs,
)
from moss_transcribe_diarize.phase2_acceptance_replay import AccountCookieLiveReplayService
from moss_transcribe_diarize.live_service_replay import run_service_replay, _snapshot_from_dict
from moss_transcribe_diarize.app.live_session import AudioFrame, LIVE_SAMPLE_RATE

CORPUS = ROOT / "evidence/live-policy-sweep-20260825/corpus"
SURFACES = ("pre_stop_immediate", "pre_stop_settled", "post_stop_final")
H1_REFERENCE_REVISION = "966d250b^"
H1_REFERENCE_CASES = ("interview_bill_ackman_60s", "interview_keyu_jin_60s")


def wav_pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, LIVE_SAMPLE_RATE):
            raise ValueError(f"expected 16 kHz mono PCM16 WAV: {path}")
        return source.readframes(source.getnframes())


class MicReplayService(AccountCookieLiveReplayService):
    def __init__(self, *args, mic_pcm: bytes, **kwargs):
        super().__init__(*args, **kwargs)
        self.mic_pcm = mic_pcm

    def accept_frame(self, session_id, frame):
        frame_samples = self._frame_samples[session_id]
        timestamp_ns = frame.sequence * frame_samples * 1_000_000_000 // LIVE_SAMPLE_RATE
        offset = frame.sequence * frame_samples * 2
        mic = self.mic_pcm[offset:offset + len(frame.pcm)]
        if len(mic) != len(frame.pcm):
            raise ValueError("microphone WAV is shorter than the case audio")
        system_result = self.accept_lane(session_id, self._lane_payload(
            frame, lane="system", timestamp_ns=timestamp_ns, silent=False))
        mic_result = self.accept_lane(session_id, self._lane_payload(
            AudioFrame(sequence=frame.sequence, pcm=mic, sample_count=frame.sample_count,
                       sample_rate=frame.sample_rate),
            lane="microphone", timestamp_ns=timestamp_ns, silent=not any(mic)))
        self._heartbeat(session_id)
        snapshot_payload = self._json("GET", f"/api/live/sessions/{self._quoted(session_id)}/snapshot")["snapshot"]
        from moss_transcribe_diarize.app.live_service_runtime import LiveServiceFrameResult
        from moss_transcribe_diarize.live_service_replay import _frame_ack_from_dict
        return LiveServiceFrameResult(
            ack=_frame_ack_from_dict(system_result["ack"]),
            queued_item_ids=tuple(int(i) for i in [*system_result.get("queued_item_ids", ()),
                                                   *mic_result.get("queued_item_ids", ())]),
            snapshot=_snapshot_from_dict(snapshot_payload))


class TimedSurfaceCapture:
    """Compose H1's capture with a reader-cadence public snapshot observer."""

    def __init__(self, inner, duration: float):
        self.inner = inner
        self.probe = LatencyProbe(duration)
        self._done = threading.Event()
        self._thread = None
        self._session_id = None
        self._started = None
        self._error = None

    def create(self):
        result = self.inner.create()
        self._session_id = result.session_id
        return result

    def accept_frame(self, session_id, frame):
        if self._thread is None:
            self._started = time.monotonic()
            self._thread = threading.Thread(target=self._poll, daemon=True)
            self._thread.start()
        return self.inner.accept_frame(session_id, frame)

    def _poll(self):
        assert self._started is not None and self._session_id is not None
        tick = 0
        while not self._done.is_set():
            due = self._started + tick * .25
            if self._done.wait(max(0, due - time.monotonic())):
                return
            try:
                snap = self.inner.inner.snapshot(self._session_id)
                if snap is not None and snap.session.status == "active":
                    self.probe.observe(snap.to_dict(), time.monotonic() - self._started)
            except Exception as exc:
                self._error = exc
                self._done.set()
                return
            tick += 1

    def finish(self):
        self._done.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        if self._error is not None:
            raise self._error

    def events(self, *args, **kwargs):
        return self.inner.events(*args, **kwargs)

    def snapshot(self, *args, **kwargs):
        return self.inner.snapshot(*args, **kwargs)

    async def stop(self, *args, **kwargs):
        return await self.inner.stop(*args, **kwargs)

    async def abort(self, *args, **kwargs):
        return await self.inner.abort(*args, **kwargs)


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verified_corpus(source: Path, out: Path, cases: list[dict]) -> tuple[Path, list[dict]]:
    """Restore only two stale reference files in scratch from manifest-matching Git history."""
    try:
        return source, _verify_quality_inputs(repo=ROOT, corpus=source, cases=cases)
    except ExternalMeasurementError:
        if source != CORPUS:
            raise
    staged = out / "_frozen_corpus"
    shutil.copytree(source, staged)
    for case_id in H1_REFERENCE_CASES:
        relative = f"evidence/live-policy-sweep-20260825/corpus/{case_id}/reference.jsonl"
        blob = subprocess.check_output(["git", "show", f"{H1_REFERENCE_REVISION}:{relative}"], cwd=ROOT)
        (staged / case_id / "reference.jsonl").write_bytes(blob)
    identities = _verify_quality_inputs(repo=ROOT, corpus=staged, cases=cases)
    print(f"recovered manifest-matching H1 references in scratch: {staged}", flush=True)
    return staged, identities


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--status", type=Path, help="append one progress line after each case pass")
    parser.add_argument("--corpus", type=Path, default=CORPUS,
                        help="frozen manifest-matching corpus root; default is worktree corpus")
    parser.add_argument("--mic", type=Path)
    parser.add_argument("--case", choices=sorted(QUALITY_CASE_IDS))
    parser.add_argument("--passes", type=int, choices=(1, 2), default=2)
    parser.add_argument("--pass-number", type=int, choices=(1, 2), default=1,
                        help="first pass number; standalone pass 2 runs in reverse order")
    args = parser.parse_args()
    if not args.base_url.startswith("https://127.0.0.1:"):
        parser.error("local HTTPS 127.0.0.1 stack required")
    if args.mic is not None:
        public_audio = {path.resolve() for clip in clips()
                        for path in (clip.audio, clip.mic_audio) if path is not None}
        if args.mic.resolve() not in public_audio:
            parser.error("--mic must name a PUBLIC WAV registered in common/corpus.py")
    if args.out.exists():
        parser.error("--out must be a new directory")
    args.out.mkdir(parents=True)
    # Loopback self-signed certificate. No external host is accepted above.
    ssl._create_default_https_context = ssl._create_unverified_context
    corpus = args.corpus.resolve()
    manifest_path = corpus / "corpus-manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    cases = manifest["cases"]
    if len(cases) != 6 or {item["case_id"] for item in cases} != QUALITY_CASE_IDS:
        raise RuntimeError("frozen six-case manifest changed")
    corpus, identities = verified_corpus(corpus, args.out, cases)
    surface = _load_surface_harness(ROOT)
    order = [item["case_id"] for item in cases]
    selected = [args.case] if args.case else order
    cookie = args.out / "cookie.txt"
    cookie.write_text("local-open-workspace\n", encoding="utf-8")
    cookie.chmod(0o600)
    observations = []
    timed_cases = []
    engine_cases = []
    descriptor_identity = None
    try:
        for pass_number in range(args.pass_number, args.pass_number + args.passes):
            pass_order = selected if pass_number % 2 == 1 else list(reversed(selected))
            for case_id in pass_order:
                case_dir = corpus / case_id
                audio = case_dir / "audio.wav"
                reference = case_dir / "reference.jsonl"
                duration = len(wav_pcm(audio)) / (LIVE_SAMPLE_RATE * 2)
                mic_pcm = wav_pcm(args.mic) if args.mic else None
                if mic_pcm is not None and len(mic_pcm) < len(wav_pcm(audio)):
                    raise ValueError("--mic WAV must cover the case duration")
                adapter = (AccountCookieLiveReplayService(
                    base_url=args.base_url, cookie_file=cookie, timeout_seconds=300)
                    if mic_pcm is None else MicReplayService(
                        base_url=args.base_url, cookie_file=cookie,
                        timeout_seconds=300, mic_pcm=mic_pcm))
                descriptor = adapter.descriptor()
                captured = surface.SurfaceCaptureService(adapter, settle_timeout=30.0, poll_seconds=.25)
                timed = TimedSurfaceCapture(captured, duration)
                run_dir = args.out / f"pass-{pass_number}" / case_id
                identity = (descriptor.source_revision, descriptor.provider_manifest_hash,
                            descriptor.config_hashes.combined_config_hash)
                if descriptor_identity is None:
                    descriptor_identity = identity
                elif identity != descriptor_identity:
                    raise RuntimeError("quality descriptor changed during campaign")
                print(f"pass={pass_number} case={case_id} duration={duration:.3f}s", flush=True)
                raw_snapshot = None
                try:
                    run_service_replay(service=timed, audio_path=audio, out_dir=run_dir,
                                       pace=1.0, max_pacing_lag=3.0, runs=1,
                                       expect_revision=identity[0], expect_provider_hash=identity[1],
                                       expect_config_hash=identity[2])
                    raw_snapshot = adapter._json(
                        "GET", f"/api/live/sessions/{adapter._quoted(timed._session_id)}/snapshot"
                    )["snapshot"]
                finally:
                    timed.finish()
                    adapter.close()
                    write_json(run_dir / "latency.json", timed.probe.result())
                if any(name not in captured.captures for name in SURFACES):
                    raise RuntimeError(f"missing surface in {case_id}")
                scored = {}
                settled_rows = None
                surface_rows = {}
                case = surface.Case(case_id, case_dir, reference)
                for name in SURFACES:
                    rows = surface.transcript_rows(captured.captures[name]["snapshot"], duration)
                    surface_rows[name] = rows
                    key = {"pre_stop_immediate": "immediate", "pre_stop_settled": "settled",
                           "post_stop_final": "final"}[name]
                    scored[key] = surface.score_surface(case, rows)
                    if key == "settled":
                        settled_rows = rows
                speaker_intervals = _quality_speaker_intervals(
                    captured.captures["pre_stop_settled"]["snapshot"], settled_rows, reference,
                    speech_regions=surface.speech_regions_from_wav(audio))
                diagnostic = speaker_intervals["settled_der_s00_diagnostic"]
                if diagnostic["as_is"] != scored["settled"]["der"]:
                    raise RuntimeError("settled interval scorer disagrees")
                if diagnostic["reference_speech_as_is"] != scored["settled"]["reference_speech_der"]:
                    raise RuntimeError("settled reference-speech interval scorer disagrees")
                scored["settled"]["der_raw"] = scored["settled"]["der"]
                scored["settled"]["reference_speech_der_raw"] = scored["settled"]["reference_speech_der"]
                scored["settled"]["der"] = diagnostic["without_s00_confusion"]
                scored["settled"]["reference_speech_der"] = diagnostic["reference_speech_without_s00_confusion"]
                trace = run_dir / "run-001" / "trace.jsonl"
                events = surface.read_service_events(trace)
                final = captured.captures["post_stop_final"]["snapshot"]["session"]
                coverage = _quality_window_coverage(events, accepted_samples=final["accepted_samples"],
                                                    finalization_status=final["finalization_status"])
                observations.append({"case_id": case_id, "pass": pass_number,
                    "session_id": f"session-{len(observations)+1:02d}",
                    "category": next(item["category"] for item in cases if item["case_id"] == case_id),
                    "duration_seconds": duration, "windows": coverage["rolling_decoded"],
                    "window_coverage": coverage, "metrics": scored, **speaker_intervals,
                    "surface_observations": _quality_surface_observations(
                        captured.captures, reference_speaker_count=len({json.loads(line)["speaker"]
                            for line in reference.read_text().splitlines() if line.strip()}))})
                reference_rows = [
                    {key: row[key] for key in ("start", "end", "speaker", "text")}
                    for line in reference.read_text(encoding="utf-8").splitlines() if line.strip()
                    for row in (json.loads(line),)
                ]
                stop_return = captured.captures.get("stop_return")
                if stop_return is not None:
                    stop_snapshot = stop_return["snapshot"]
                    write_json(run_dir / "stop-return-timed-segments.json", {
                        "case_id": case_id, "pass": pass_number,
                        "finalization_status": stop_snapshot["session"]["finalization_status"],
                        "reference": reference_rows,
                        "stop_return": surface.transcript_rows(stop_snapshot, duration),
                    })
                timed_case = {"case_id": case_id, "pass": pass_number,
                              "reference": reference_rows, "surfaces": surface_rows}
                write_json(run_dir / "timed-segments.json", timed_case)
                timed_cases.append(timed_case)
                write_json(args.out / "h1-timed-segments.json", {
                    "schema": "h1-timed-segments.v1",
                    "corpus_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                    "cases": timed_cases,
                })
                diagnostics = raw_snapshot.get("engine_diagnostics") if isinstance(raw_snapshot, dict) else None
                if diagnostics is None:
                    diagnostics = {"status": "UNMEASURED", "reason": "runtime snapshot has no engine_diagnostics"}
                at_stop = captured.captures["pre_stop_immediate"]["snapshot"]["session"]["effective_transcript"]
                labels_at_stop = len({row.get("canonical_speaker") for row in at_stop
                                      if row.get("canonical_speaker") is not None and row.get("text", "").strip()})
                engine_cases.append({"case_id": case_id, "pass": pass_number,
                                     "labels_at_stop": labels_at_stop,
                                     "engine_diagnostics": diagnostics})
                write_json(args.out / "engine-diagnostics.json", {"cases": engine_cases})
                write_json(args.out / "pass-content-free-metrics.json", {
                    "schema": "h1-partial-quality.v1", "h1_comparable": len(observations) == 12,
                    "corpus_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                    "per_case": observations,
                })
                write_json(args.out / "progress.json", {"completed": len(observations),
                           "case_id": case_id, "pass": pass_number, "coverage": coverage})
                if args.status:
                    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    with args.status.open("a", encoding="utf-8") as stream:
                        stream.write(f"{stamp} Quality replay: {len(observations)}/{len(selected)*args.passes} "
                                     f"case={case_id} pass={pass_number} coverage={coverage}.\n")
        if len(observations) == 12 and args.mic is None:
            result = _quality_projection(observations,
                corpus_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest())
            result["input_identities"] = identities
            write_json(args.out / "content-free-metrics.json", result)
            print(json.dumps({"sessions": result["sessions"], "macro": result["macro"]}, indent=2))
        else:
            print(json.dumps({"sessions": len(observations), "h1_comparable": False,
                              "reason": "partial population or non-silent microphone"}, indent=2))
    finally:
        cookie.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
