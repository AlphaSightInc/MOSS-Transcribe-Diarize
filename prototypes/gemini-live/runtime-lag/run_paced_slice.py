"""Paced 600 s public long60 slice through the unchanged HTTPS API."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import ssl
import sys
import wave

LIVE = Path(__file__).resolve().parents[4] / "MOSS-Transcribe-Diarize-wt-gemini-live"
sys.path.insert(0, str(LIVE / "prototypes/gemini-live/harness"))
from run_quality import TimedSurfaceCapture, write_json  # noqa: E402
from moss_transcribe_diarize.phase2_acceptance_external import _load_surface_harness  # noqa: E402
from moss_transcribe_diarize.phase2_acceptance_replay import AccountCookieLiveReplayService  # noqa: E402
from moss_transcribe_diarize.live_service_replay import run_service_replay  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    args = parser.parse_args()
    if not args.base_url.startswith("https://127.0.0.1:") or args.out.exists():
        parser.error("new output directory and loopback HTTPS required")
    args.out.mkdir(parents=True)
    args.scratch.mkdir(parents=True, exist_ok=True)
    source = LIVE / "prototypes/gemini-live/.cache/long60/audio.wav"
    audio = args.scratch / "first-600s.wav"
    with wave.open(str(source), "rb") as original, wave.open(str(audio), "wb") as clipped:
        assert (original.getframerate(), original.getnchannels(), original.getsampwidth()) == (16000, 1, 2)
        clipped.setparams(original.getparams())
        clipped.writeframes(original.readframes(600 * 16000))
    ssl._create_default_https_context = ssl._create_unverified_context
    cookie = args.scratch / "cookie.txt"
    cookie.write_text("local-open-workspace\n")
    cookie.chmod(0o600)
    adapter = AccountCookieLiveReplayService(base_url=args.base_url, cookie_file=cookie,
                                             timeout_seconds=300)
    surface = _load_surface_harness(LIVE)
    capture = surface.SurfaceCaptureService(adapter, settle_timeout=60.0, poll_seconds=.25)
    timed = TimedSurfaceCapture(capture, 600)
    descriptor = adapter.descriptor()
    identity = (descriptor.source_revision, descriptor.provider_manifest_hash,
                descriptor.config_hashes.combined_config_hash)
    try:
        try:
            run_service_replay(service=timed, audio_path=audio, out_dir=args.out / "replay",
                               pace=1.0, max_pacing_lag=3.0, runs=1,
                               expect_revision=identity[0], expect_provider_hash=identity[1],
                               expect_config_hash=identity[2], finalization_deadline=180.0)
        finally:
            timed.finish()
        snapshot = adapter._json(
            "GET", f"/api/live/sessions/{adapter._quoted(timed._session_id)}/snapshot"
        )["snapshot"]
        delays = timed.probe.labels
        observed = sorted(value for value in delays if value is not None)
        groups = defaultdict(list)
        for second, delay in enumerate(delays):
            if delay is not None:
                groups[round(second + delay, 3)].append(second)
        windows = []
        previous = 0
        for published, buckets in groups.items():
            frontier = max(buckets) + 1
            windows.append({"frontier_seconds": frontier, "published_seconds": published,
                            "tick_to_commit_seconds": round(published-frontier, 3),
                            "stride_seconds": frontier-previous})
            previous = frontier
        def percentile(values, q):
            values = sorted(values)
            return values[round((len(values)-1)*q)] if values else None
        diagnostics = snapshot.get("engine_diagnostics") or {}
        result = {"duration_seconds": 600, "paced": True,
                  "label_buckets": len(delays), "observed_label_buckets": len(observed),
                  "label_p50_seconds": percentile(observed, .5),
                  "label_p90_seconds": percentile(observed, .9),
                  "tick_to_commit_p50_seconds": percentile(
                      [w["tick_to_commit_seconds"] for w in windows], .5),
                  "tick_to_commit_p90_seconds": percentile(
                      [w["tick_to_commit_seconds"] for w in windows], .9),
                  "windows": windows, "engine_diagnostics": diagnostics,
                  "finalization_status": snapshot["session"]["finalization_status"],
                  "labels_at_stop": len({r["canonical_speaker"] for r in
                                          capture.captures["pre_stop_immediate"]["snapshot"]
                                          ["session"]["effective_transcript"]
                                          if r["canonical_speaker"] is not None})}
        write_json(args.out / "result.json", result)
        print(json.dumps({k: v for k, v in result.items() if k not in
                          {"windows", "engine_diagnostics"}}, indent=2), flush=True)
    finally:
        adapter.close()
        cookie.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
