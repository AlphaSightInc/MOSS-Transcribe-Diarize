"""One public Bill 60s, 1.0x HTTPS replay of default async refinement."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import ssl
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from moss_transcribe_diarize.phase2_acceptance_replay import AccountCookieLiveReplayService
from moss_transcribe_diarize.live_service_replay import run_service_replay

SOURCE = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P66/wp1/http-smoke-bill-1x/_frozen_corpus/interview_bill_ackman_60s/audio.wav")


def project(raw):
    return {"status": raw["status"], "refinement_state": raw["refinement_state"],
            "transcript_version": raw["transcript_version"],
            "segments": len((raw.get("transcript") or {}).get("segments", [])),
            "notice": raw.get("notice"), "needs_review": raw.get("needs_review")}


class ObservedReplay(AccountCookieLiveReplayService):
    def __init__(self, *, out, **options):
        super().__init__(**options)
        self.out = out
        self.session_id = None

    def create(self):
        result = super().create()
        self.session_id = result.session_id
        return result

    async def stop(self, session_id, deadline):
        started = time.monotonic()
        result = await super().stop(session_id, deadline)
        meeting = await asyncio.to_thread(
            self._json, "GET", f"/api/meetings/{self._quoted(session_id)}")
        self.out.joinpath("stop-observation.json").write_text(json.dumps({
            "stop_elapsed_s": round(time.monotonic() - started, 6),
            "meeting": project(meeting),
            "runtime_finalization": result.session.finalization_status,
        }, indent=2, sort_keys=True) + "\n")
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not args.base_url.startswith("https://127.0.0.1:") or args.out.exists():
        parser.error("requires a new output directory and local HTTPS stack")
    args.out.mkdir(parents=True)
    ssl._create_default_https_context = ssl._create_unverified_context
    with tempfile.TemporaryDirectory(prefix="moss-wp1-async-cookie-") as scratch:
        cookie = Path(scratch) / "cookie.txt"
        cookie.write_text("local-open-workspace\n")
        cookie.chmod(0o600)
        adapter = ObservedReplay(out=args.out, base_url=args.base_url,
                                 cookie_file=cookie, timeout_seconds=300)
        try:
            descriptor = adapter.descriptor()
            identity = (descriptor.source_revision, descriptor.provider_manifest_hash,
                        descriptor.config_hashes.combined_config_hash)
            if descriptor.engine_options["cleanup_after_stop"]["default"] is not True:
                raise RuntimeError("server descriptor does not default cleanup on")
            run_service_replay(service=adapter, audio_path=SOURCE, out_dir=args.out / "replay",
                               pace=1.0, max_pacing_lag=3.0, runs=1,
                               expect_revision=identity[0], expect_provider_hash=identity[1],
                               expect_config_hash=identity[2], finalization_deadline=600.0)
            meeting = adapter._json(
                "GET", f"/api/meetings/{adapter._quoted(adapter.session_id)}")
            snapshot = adapter._json(
                "GET", f"/api/live/sessions/{adapter._quoted(adapter.session_id)}/snapshot")['snapshot']
            result = {"source_wav_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                      "descriptor_source_revision": identity[0],
                      "meeting": project(meeting),
                      "accepted_samples": snapshot["session"]["accepted_samples"],
                      "accounted_samples": snapshot["session"]["accounted_samples"],
                      "cost_usd": (snapshot.get("engine_diagnostics") or {}).get("cost_usd")}
            args.out.joinpath("result.json").write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n")
            print(json.dumps(result, sort_keys=True), flush=True)
        finally:
            adapter.close()


if __name__ == "__main__":
    main()
