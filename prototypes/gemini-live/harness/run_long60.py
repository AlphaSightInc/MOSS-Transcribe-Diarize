"""Paced long60 HTTP replay on a dedicated Gemini stack.

Run: python prototypes/gemini-live/harness/run_long60.py \
  --base-url https://127.0.0.1:18501 --out <new-dir> --status <pane-status>
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import ssl
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(ROOT / "prototypes/gemini-live/common"))

from corpus import clips  # noqa: E402
from latency_probe import percentile  # noqa: E402
from run_quality import SettingsReplayService, TimedSurfaceCapture, write_json, wav_pcm  # noqa: E402
from score import score  # noqa: E402
from moss_transcribe_diarize.phase2_acceptance_external import _load_surface_harness  # noqa: E402
from moss_transcribe_diarize.live_service_replay import run_service_replay  # noqa: E402


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def lag_window(values: list[float | None], start: int, end: int) -> dict:
    selected = values[start:end]
    observed = [value for value in selected if value is not None]
    return {"start_audio_second": start, "end_audio_second_exclusive": end,
            "audio_second_buckets": len(selected), "observed_buckets": len(observed),
            "unobserved_buckets": len(selected) - len(observed),
            "p50_seconds": percentile(observed, .5), "p90_seconds": percentile(observed, .9)}


def speaker_count(snapshot: dict) -> int:
    return len({row.get("canonical_speaker")
                for row in snapshot["session"]["effective_transcript"]
                if row.get("canonical_speaker") is not None and row.get("text", "").strip()})


class ProgressCapture(TimedSurfaceCapture):
    def __init__(self, inner, duration: float, out: Path, status: Path | None):
        super().__init__(inner, duration)
        self.out = out
        self.status = status

    def accept_frame(self, session_id, frame):
        result = super().accept_frame(session_id, frame)
        frame_seconds = frame.sample_count / 16000
        elapsed_audio = (frame.sequence + 1) * frame_seconds
        if frame.sequence % 600 == 599:  # Five audio minutes at the 0.5 s descriptor frame.
            raw = self.inner.inner._json(
                "GET", f"/api/live/sessions/{self.inner.inner._quoted(session_id)}/snapshot"
            )["snapshot"]
            diagnostic = raw.get("engine_diagnostics") or {}
            progress = {"audio_seconds_accepted": elapsed_audio,
                        "accepted_samples": raw["session"]["accepted_samples"],
                        "accounted_samples": raw["session"]["accounted_samples"],
                        "pending_work_items": raw["pending_work_items"],
                        "cost_usd": diagnostic.get("cost_usd"),
                        "system_calls": (diagnostic.get("lanes") or {}).get("system", {}).get("calls_by_kind"),
                        "observed_utc": stamp()}
            write_json(self.out / "progress.json", progress)
            message = (f"{progress['observed_utc']} long60 audio={elapsed_audio:.0f}s "
                       f"accounted={progress['accounted_samples']/16000:.1f}s "
                       f"pending={progress['pending_work_items']} cost=${progress['cost_usd']}")
            print(message, flush=True)
            if self.status is not None:
                with self.status.open("a", encoding="utf-8") as stream:
                    stream.write(message + "\n")
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--status", type=Path)
    parser.add_argument("--engine-settings", type=json.loads,
                        default={"speaker_window": "balanced", "cleanup_after_stop": False})
    args = parser.parse_args()
    if not args.base_url.startswith("https://127.0.0.1:"):
        parser.error("local HTTPS loopback stack required")
    if args.out.exists():
        parser.error("--out must be a new directory")
    clip, = clips("long60")
    audio = clip.audio
    reference = clip.reference_segments()
    duration = len(wav_pcm(audio)) / 32000
    if not reference or clip.true_speakers != 5 or duration < 2500:
        raise RuntimeError("long60 complete-reference fixture is unavailable")
    args.out.mkdir(parents=True)
    ssl._create_default_https_context = ssl._create_unverified_context
    cookie = args.out / "cookie.txt"
    cookie.write_text("local-open-workspace\n", encoding="utf-8")
    cookie.chmod(0o600)
    adapter = SettingsReplayService(base_url=args.base_url, cookie_file=cookie,
                                    timeout_seconds=300, engine_settings=args.engine_settings)
    surface = _load_surface_harness(ROOT)
    capture = surface.SurfaceCaptureService(adapter, settle_timeout=120.0, poll_seconds=.25)
    timed = ProgressCapture(capture, duration, args.out, args.status)
    descriptor = adapter.descriptor()
    identity = (descriptor.source_revision, descriptor.provider_manifest_hash,
                descriptor.config_hashes.combined_config_hash)
    write_json(args.out / "input.json", {"clip_id": clip.clip_id, "tier": clip.tier,
               "audio_path": str(audio), "reference_path": str(clip.reference),
               "duration_seconds": duration, "reference_segments": len(reference),
               "true_speakers": clip.true_speakers, "descriptor": descriptor.to_dict(),
               "started_utc": stamp(), "pace": 1.0, "system_audio": True,
               "microphone": "digital_silence"})
    print(f"long60 start duration={duration:.3f}s reference={len(reference)} rows", flush=True)
    try:
        try:
            run_service_replay(service=timed, audio_path=audio, out_dir=args.out / "replay",
                               pace=1.0, max_pacing_lag=3.0, runs=1,
                               expect_revision=identity[0], expect_provider_hash=identity[1],
                               expect_config_hash=identity[2], finalization_deadline=600.0)
        finally:
            timed.finish()
        if any(name not in capture.captures for name in
               ("pre_stop_immediate", "pre_stop_settled", "post_stop_final")):
            raise RuntimeError("long60 did not retain all three surfaces")
        snapshot = adapter._json(
            "GET", f"/api/live/sessions/{adapter._quoted(timed._session_id)}/snapshot"
        )["snapshot"]
        diagnostics = snapshot.get("engine_diagnostics") or {}
        write_json(args.out / "engine-diagnostics.json", diagnostics)
        scored = {}
        surfaces = {}
        for name in ("pre_stop_immediate", "pre_stop_settled", "post_stop_final"):
            capture_snapshot = capture.captures[name]["snapshot"]
            write_json(args.out / f"{name}.json", capture_snapshot)
            rows = surface.transcript_rows(capture_snapshot, duration)
            surfaces[name] = rows
            scored[name] = score(reference, rows)
        write_json(args.out / "timed-segments.json", {"reference": reference,
                   "surfaces": surfaces})
        write_json(args.out / "label-bucket-delays.json", {"seconds": timed.probe.labels})
        tentative = timed.tentative.result(reference, capture.captures["post_stop_final"]["snapshot"])
        write_json(args.out / "tentative.json", tentative)
        lag = {"first_5m": lag_window(timed.probe.labels, 0, 300),
               "last_5m": lag_window(timed.probe.labels,
                                      timed.probe.bucket_count - 300, timed.probe.bucket_count)}
        live_calls = (diagnostics.get("lanes") or {}).get("system", {}).get(
            "calls_by_kind", {}).get("live_preview", 0)
        live_errors = (diagnostics.get("lanes") or {}).get("system", {}).get(
            "errors_by_code", {})
        live_retries = (diagnostics.get("lanes") or {}).get("system", {}).get(
            "retries_by_code", {})
        result = {"schema": "gemini-long60-live.v1", "clip_id": clip.clip_id,
                  "engine_settings": args.engine_settings,
                  "duration_seconds": duration, "true_speakers": clip.true_speakers,
                  "reference_segments": len(reference), "labels_at_stop": speaker_count(
                      capture.captures["pre_stop_immediate"]["snapshot"]),
                  "labels_pre_stop_settled": speaker_count(
                      capture.captures["pre_stop_settled"]["snapshot"]),
                  "score": scored, "label_lag": lag, "snapshot_count": timed.probe.snapshots,
                  "tentative": tentative,
                  "reconnects": {"system_live_preview_connection_attempts": live_calls,
                                 "attempts_after_initial": max(0, live_calls - 1),
                                 "errors_by_code": live_errors, "retries_by_code": live_retries,
                                 "http_client_reconnects": "UNMEASURED: per-request HTTP adapter"},
                  "cost_usd": diagnostics.get("cost_usd"),
                  "cost_usd_per_audio_hour": diagnostics.get("cost_usd", 0) * 3600 / duration,
                  "accepted_samples": snapshot["session"]["accepted_samples"],
                  "accounted_samples": snapshot["session"]["accounted_samples"],
                  "pending_work_items": snapshot["pending_work_items"],
                  "finalization_status": snapshot["session"]["finalization_status"],
                  "finished_utc": stamp()}
        write_json(args.out / "summary.json", result)
        print(json.dumps(result, indent=2), flush=True)
        if args.status:
            with args.status.open("a", encoding="utf-8") as stream:
                stream.write(f"{stamp()} long60 complete: Stop labels={result['labels_at_stop']} "
                             f"settled DER={scored['pre_stop_settled']['der']:.6f} "
                             f"final DER={scored['post_stop_final']['der']:.6f} "
                             f"cost=${result['cost_usd']:.6f}.\n")
    except Exception as exc:
        write_json(args.out / "failure.json", {"type": type(exc).__name__,
                   "message": str(exc), "observed_utc": stamp()})
        if args.status:
            with args.status.open("a", encoding="utf-8") as stream:
                stream.write(f"{stamp()} long60 failed: {type(exc).__name__}: {exc}\n")
        raise
    finally:
        adapter.close()
        cookie.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
