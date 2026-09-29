"""Paced long60 HTTP run with first-seen, lane-preserving preview observations.

Usage: python prototypes/gemini-live/tentative/http_long60.py
  --base-url https://127.0.0.1:18740 --out <new scratch dir> --status <status file>
The existing harness owns replay, latency, Stop, and scoring. This adds only
content-free first-seen preview rows needed to score display-only guesses.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import moss_transcribe_diarize  # noqa: E402

# Reuse WP6's read-only HTTP client, snapshot cadence, and tentative scorer.
# Preloading the package above keeps client-side snapshot parsing on this WP4 tree.
WP6_HARNESS = Path("/Users/gao/Desktop/AI_Projects/Github_Projects/"
                   "MOSS-Transcribe-Diarize-wt-r2-int/prototypes/gemini-live/harness")
sys.path.insert(0, str(WP6_HARNESS))
import run_quality as wp6_quality  # noqa: E402
HARNESS = ROOT / "prototypes/gemini-live/harness"
sys.path.insert(0, str(HARNESS))
import run_long60  # noqa: E402

if not Path(moss_transcribe_diarize.__file__).resolve().is_relative_to(ROOT):
    raise RuntimeError("long60 HTTP client must parse snapshots with the WP4 package")
if not issubclass(run_long60.ProgressCapture, wp6_quality.TimedSurfaceCapture):
    raise RuntimeError("long60 capture did not bind the WP6 snapshot client")


def _wp6_adapter(**kwargs):
    return wp6_quality.SettingsReplayService(
        **kwargs, engine_settings={"speaker_window": "balanced",
                                   "cleanup_after_stop": False})


run_long60.AccountCookieLiveReplayService = _wp6_adapter


def _poll_with_guesses(self):
    assert self._started is not None and self._session_id is not None
    seen: set[tuple[int, int, str]] = set()
    tick = 0
    path = self.out / "tentative-first-seen.jsonl"
    with path.open("w", encoding="utf-8") as receipt:
        while not self._done.is_set():
            due = self._started + tick * .25
            if self._done.wait(max(0, due - time.monotonic())):
                return
            try:
                raw = self.inner.inner._json(
                    "GET", f"/api/live/sessions/{self.inner.inner._quoted(self._session_id)}/snapshot"
                )["snapshot"]
                if raw["session"]["status"] == "active":
                    wall = time.monotonic() - self._started
                    self.probe.observe(raw, wall)
                    self.tentative.observe(raw)
                    provisional = raw["session"].get("provisional") or {}
                    for row in provisional.get("segments", ()):
                        key = (row["start_sample"], row["end_sample"], row["source_lane"])
                        if key in seen:
                            continue
                        seen.add(key)
                        receipt.write(json.dumps({
                            "start_sample": key[0], "end_sample": key[1],
                            "source_lane": key[2], "tentative_speaker": row["tentative_speaker"],
                            "observed_wall_s": wall,
                            "committed_samples": raw["session"]["committed_samples"],
                        }) + "\n")
                    receipt.flush()
            except Exception as exc:
                self._error = exc
                self._done.set()
                return
            tick += 1


_wp6_finish = run_long60.ProgressCapture.finish


def _finish_with_wp6_tentative(self):
    _wp6_finish(self)
    final = self.inner.captures.get("post_stop_final")
    if final is not None:
        from corpus import clips
        clip, = clips("long60")
        run_long60.write_json(self.out / "tentative-wp6.json",
            self.tentative.result(clip.reference_segments(), final["snapshot"]))


run_long60.ProgressCapture._poll = _poll_with_guesses
run_long60.ProgressCapture.finish = _finish_with_wp6_tentative
run_long60.main()
