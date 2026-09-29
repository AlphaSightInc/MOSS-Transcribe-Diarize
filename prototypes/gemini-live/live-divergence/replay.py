"""One 1.0x Account HTTPS replay of the frozen 900 s long60 prefix."""
import argparse
import json
from pathlib import Path
import ssl
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from moss_transcribe_diarize.phase2_acceptance_replay import AccountCookieLiveReplayService
from moss_transcribe_diarize.live_service_replay import run_service_replay


class ObservedReplay(AccountCookieLiveReplayService):
    def __init__(self, *, out: Path, **kwargs):
        super().__init__(**kwargs)
        self.out = out
        self.session_id = None

    def create(self):
        result = super().create()
        self.session_id = result.session_id
        return result

    def accept_frame(self, session_id, frame):
        result = super().accept_frame(session_id, frame)
        if frame.sequence % 120 == 119:  # One diagnostic per accepted audio minute.
            raw = self._json("GET", f"/api/live/sessions/{self._quoted(session_id)}/snapshot")["snapshot"]
            diagnostic = raw.get("engine_diagnostics") or {}
            row = {"accepted_s": raw["session"]["accepted_samples"] / 16000,
                   "cost_usd": diagnostic.get("cost_usd"),
                   "metered_output_usd": diagnostic.get("metered_output_usd"),
                   "system_calls": (diagnostic.get("lanes") or {}).get("system", {}).get("calls_by_kind")}
            with (self.out / "progress.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, sort_keys=True) + "\n")
            print(json.dumps(row, sort_keys=True), flush=True)
            if isinstance(row["cost_usd"], (int, float)) and row["cost_usd"] >= .47:
                raise RuntimeError("LIVE_DIVERGENCE_TOTAL_BUDGET_STOP")
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    audio = args.out / "long60-first900.wav"
    if not audio.is_file() or not (args.out / "input-preflight.json").is_file():
        raise RuntimeError("frozen input preflight missing")
    ssl._create_default_https_context = ssl._create_unverified_context
    cookie = args.out / "cookie.txt"
    cookie.write_text("local-open-workspace\n", encoding="utf-8")
    cookie.chmod(0o600)
    adapter = ObservedReplay(out=args.out, base_url=args.base_url,
                             cookie_file=cookie, timeout_seconds=300)
    try:
        descriptor = adapter.descriptor()
        identity = (descriptor.source_revision, descriptor.provider_manifest_hash,
                    descriptor.config_hashes.combined_config_hash)
        print(json.dumps({"descriptor_source_revision": identity[0],
                          "provider_manifest_hash": identity[1],
                          "config_hash": identity[2]}, sort_keys=True), flush=True)
        run_service_replay(service=adapter, audio_path=audio, out_dir=args.out / "replay",
                           pace=1.0, max_pacing_lag=3.0, runs=1,
                           expect_revision=identity[0], expect_provider_hash=identity[1],
                           expect_config_hash=identity[2], finalization_deadline=600.0)
        if adapter.session_id:
            raw = adapter._json(
                "GET", f"/api/live/sessions/{adapter._quoted(adapter.session_id)}/snapshot")
            (args.out / "final-snapshot.json").write_text(
                json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    finally:
        adapter.close()


if __name__ == "__main__":
    main()
