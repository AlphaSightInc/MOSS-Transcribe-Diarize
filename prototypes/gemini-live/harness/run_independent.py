"""Paced Q-IND paired replay: live-only versus after-Stop clean-up on public clips.

Run with --case <clip-id> for a smoke test, then --all for the frozen population.
Each arm uses a fresh owner-bound Live meeting on the same HTTP stack.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import ssl
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(ROOT / "prototypes/gemini-live/common"))

from corpus import clips
from score import score
from run_quality import SettingsReplayService, wav_pcm, write_json
from moss_transcribe_diarize.phase2_acceptance_external import _load_surface_harness
from moss_transcribe_diarize.live_service_replay import run_service_replay


def population():
    """Plan §2 population; sparse references stay visible as diagnostics."""
    selected = []
    for clip in clips():
        if (clip.tier == "accept6"
                or clip.tier == "bench5m" and "lex_" in clip.clip_id
                or clip.clip_id in {"benchmark_30m:lex_bill_ackman", "long60"}
                or clip.tier == "gold9" and clip.clip_id.startswith("calibration:")):
            selected.append(clip)
    return selected


def run_arm(base_url: str, clip, cleanup: bool, out: Path, surface):
    duration = len(wav_pcm(clip.audio)) / 32000
    out.mkdir(parents=True)
    cookie = out / "cookie.txt"
    cookie.write_text("local-open-workspace\n", encoding="utf-8")
    cookie.chmod(0o600)
    adapter = SettingsReplayService(base_url=base_url, cookie_file=cookie,
                                    timeout_seconds=300,
                                    engine_settings={"speaker_window": "balanced",
                                                     "cleanup_after_stop": cleanup})
    capture = surface.SurfaceCaptureService(adapter, settle_timeout=120.0, poll_seconds=.25)
    descriptor = adapter.descriptor()
    identity = (descriptor.source_revision, descriptor.provider_manifest_hash,
                descriptor.config_hashes.combined_config_hash)
    try:
        run_service_replay(service=capture, audio_path=clip.audio, out_dir=out / "replay",
                           pace=1.0, max_pacing_lag=3.0, runs=1,
                           expect_revision=identity[0], expect_provider_hash=identity[1],
                           expect_config_hash=identity[2], finalization_deadline=600.0)
        final = capture.captures["post_stop_final"]["snapshot"]
        rows = surface.transcript_rows(final, duration)
        meeting_id = next(iter(adapter._frame_samples))
        raw = adapter._json("GET", f"/api/live/sessions/{adapter._quoted(meeting_id)}/snapshot")
        diagnostics = raw.get("snapshot", {}).get("engine_diagnostics") or {}
        reference = clip.reference_segments()
        result = {"clip_id": clip.clip_id, "tier": clip.tier, "cleanup_after_stop": cleanup,
                  "duration_seconds": duration, "reference_segments": len(reference),
                  "reference_covered_seconds": sum(float(r["end"])-float(r["start"]) for r in reference),
                  "score": score(reference, rows),
                  "canonical_ids": len({row.get("canonical_speaker") for row in
                                        final["session"]["effective_transcript"]
                                        if row.get("canonical_speaker") and row.get("text", "").strip()}),
                  "cost_usd": diagnostics.get("cost_usd"),
                  "output_cost_estimate_usd": diagnostics.get("output_cost_estimate_usd"),
                  "descriptor_revision": identity[0],
                  "finalization_status": final["session"]["finalization_status"]}
        write_json(out / "result.json", result)
        return result
    finally:
        adapter.close()
        cookie.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--out", type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--case")
    group.add_argument("--all", action="store_true")
    parser.add_argument("--status", type=Path)
    args = parser.parse_args()
    if not args.base_url.startswith("https://127.0.0.1:"):
        parser.error("local HTTPS loopback stack required")
    if args.out.exists():
        parser.error("--out must be new")
    selected = population()
    if args.case:
        selected = [c for c in selected if c.clip_id == args.case]
        if not selected:
            parser.error("unknown Q-IND clip id")
    args.out.mkdir(parents=True)
    ssl._create_default_https_context = ssl._create_unverified_context
    surface = _load_surface_harness(ROOT)
    results = []
    for clip in selected:
        print(f"Q-IND {clip.clip_id} live-only / clean-up on", flush=True)
        left = run_arm(args.base_url, clip, False, args.out / clip.clip_id.replace(":", "_") / "off", surface)
        right = run_arm(args.base_url, clip, True, args.out / clip.clip_id.replace(":", "_") / "on", surface)
        true = left["score"]["ref_speakers"]
        verdict = (left["canonical_ids"] <= true + 1
                   and left["score"]["der"] <= right["score"]["der"] + .03)
        row = {"clip_id": clip.clip_id, "tier": clip.tier, "true_speakers": true,
               "reference_covered_seconds": left["reference_covered_seconds"],
               "duration_seconds": left["duration_seconds"],
               "live_only": left, "cleanup_on": right, "passes_plan_predicate": verdict}
        results.append(row)
        write_json(args.out / "q-ind.json", {"schema": "q-ind.v1", "cases": results})
        if args.status:
            with args.status.open("a", encoding="utf-8") as stream:
                stream.write(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S UTC} | Q-IND {len(results)}/{len(selected)} "
                             f"{clip.clip_id}: OFF IDs {left['canonical_ids']}/{true}; "
                             f"DER {left['score']['der']:.6f} vs ON {right['score']['der']:.6f}; "
                             f"pass={verdict}.\n")
    print(json.dumps({"cases": len(results), "passed": sum(r["passes_plan_predicate"] for r in results)}, indent=2))


if __name__ == "__main__":
    main()
