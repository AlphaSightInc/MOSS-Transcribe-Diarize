"""Pace one Q-MIC variant through a local Gemini HTTP stack and score Stop."""
from __future__ import annotations

import argparse
import json
import ssl
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "prototypes/gemini-live/harness"))

from run_quality import MicReplayService, wav_pcm  # noqa: E402
from corpus import clips  # noqa: E402
from moss_transcribe_diarize.live_service_replay import run_service_replay  # noqa: E402
sys.path.insert(0, str(HERE))
from score import score  # noqa: E402


class TrackedMicReplayService(MicReplayService):
    session_id: str

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.birth_observations = {}
        self.stop_snapshot = None

    def create(self):
        created = super().create()
        self.session_id = created.session_id
        return created

    def accept_frame(self, session_id, frame):
        result = super().accept_frame(session_id, frame)
        for row in result.snapshot.session.effective_transcript:
            identity = row.canonical_speaker
            if (row.source_lane == "microphone" and isinstance(identity, str)
                    and identity.startswith("local-") and identity not in self.birth_observations):
                self.birth_observations[identity] = {
                    "start_s": row.start_sample / 16000,
                    "end_s": row.end_sample / 16000}
        return result

    async def stop(self, session_id, deadline):
        snapshot = await super().stop(session_id, deadline)
        self.stop_snapshot = snapshot.to_dict()
        return snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--variant", choices=("headphones", "speakers--20", "speakers--10", "e1"),
                        required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not args.base_url.startswith("https://127.0.0.1:"):
        parser.error("local HTTPS 127.0.0.1 stack required")
    if args.out.exists():
        parser.error("--out must be a new directory")
    reference = json.loads((HERE / "out/reference.json").read_text())
    if args.variant == "e1":
        clip = next(clip for clip in clips("e1") if clip.clip_id == "e1")
        system_path, mic_path = clip.audio, clip.mic_audio
    else:
        fixture = reference["variants"][args.variant]
        system_path = HERE / "out" / fixture["system"]
        mic_path = HERE / "out" / fixture["microphone"]
    args.out.mkdir(parents=True)
    cookie = args.out / "cookie.txt"
    cookie.write_text("local-open-workspace\n")
    cookie.chmod(0o600)
    ssl._create_default_https_context = ssl._create_unverified_context
    adapter = TrackedMicReplayService(
        base_url=args.base_url, cookie_file=cookie, timeout_seconds=300,
        mic_pcm=wav_pcm(mic_path))
    try:
        descriptor = adapter.descriptor()
        run_service_replay(
            service=adapter, audio_path=system_path, out_dir=args.out / "replay",
            pace=1.0, max_pacing_lag=3.0, runs=1,
            expect_revision=descriptor.source_revision,
            expect_provider_hash=descriptor.provider_manifest_hash,
            expect_config_hash=descriptor.config_hashes.combined_config_hash)
        snapshot = adapter._json(
            "GET", f"/api/live/sessions/{adapter._quoted(adapter.session_id)}/snapshot"
        )["snapshot"]
    finally:
        adapter.close()
    (args.out / "snapshot.json").write_text(json.dumps(snapshot, indent=2) + "\n")
    (args.out / "stop_snapshot.json").write_text(json.dumps(adapter.stop_snapshot, indent=2) + "\n")
    if args.variant == "e1":
        stop_rows = adapter.stop_snapshot["session"]["effective_transcript"]
        identities = sorted({row["canonical_speaker"] for row in stop_rows
                             if row.get("canonical_speaker")})
        result = {"variant": "e1", "duration_s": 302,
                  "stop_labels": identities, "stop_label_count": len(identities),
                  "pass": len(identities) <= 4,
                  "cost_usd": snapshot.get("engine_diagnostics", {}).get("cost_usd")}
    else:
        result = score(snapshot, reference, args.variant,
                       birth_observations=adapter.birth_observations)
    result["descriptor"] = {
        "source_revision": descriptor.source_revision,
        "provider_manifest_hash": descriptor.provider_manifest_hash,
        "combined_config_hash": descriptor.config_hashes.combined_config_hash}
    result["pace"] = 1.0
    (args.out / ("e1.json" if args.variant == "e1" else "qmic.json")).write_text(
        json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
