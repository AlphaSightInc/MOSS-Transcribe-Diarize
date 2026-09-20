"""R4-7: finalize and consume a two-meeting, 200-minute-per-tape manifest."""

from __future__ import annotations

import asyncio
import json
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from moss_transcribe_diarize.app.live_manifest_finalizer import (
    LiveIdentityRecalibration,
    LiveManifestRetune,
    finalize_payload,
    verify_admission,
)
from moss_transcribe_diarize.app.live_provider_bundle import (
    LiveProviderBundleConfig,
    build_live_runtime_factory,
)
from moss_transcribe_diarize.app.phase2 import Phase2Store, SESSION_COOKIE, create_phase2_app


REPO = Path(__file__).resolve().parents[2]
SOURCE = Path.home() / ".local/share/moss-transcribe-diarize/live/live-provider-manifest.json"
PER_MEETING_BYTES = 200 * 60 * 16_000 * 2
MEETING_COUNT = 2


class NoCallRunner:
    model_path = "runtime-capacity-no-call"

    def transcribe(self, *_args: object, **_kwargs: object) -> SimpleNamespace:
        raise AssertionError("capacity probe must not decode")


async def provision(database: Path) -> str:
    store = await Phase2Store.open(database)
    try:
        _, session_id = await store.bootstrap_browser(None)
        return session_id
    finally:
        await store.close()


def main() -> int:
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
    ).strip()
    if head != "89f833acd4c654dd702664a17ed19783a2999c95":
        raise RuntimeError(f"wrong prototype base: {head}")
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    for asset in [*payload["assets"], payload["golden"]["input"]]:
        path = Path(asset["path"])
        if not path.is_absolute():
            asset["path"] = str((SOURCE.parent / path).resolve())
    bounds = payload["bounds_config"]
    identity = payload["identity_config"]
    provider = payload["identity_provider"]
    final, changes = finalize_payload(
        payload,
        source_revision=head,
        retune=LiveManifestRetune(
            hard_cap_samples=bounds["hard_cap_samples"],
            max_retained_samples=bounds["max_retained_samples"],
            frame_samples=bounds["frame_samples"],
            max_tape_bytes=PER_MEETING_BYTES,
        ),
        identity=LiveIdentityRecalibration(
            min_match_score=identity["min_match_score"],
            min_match_margin=identity["min_match_margin"],
            album_admission_seconds=provider["album_admission_seconds"],
            birth_min_seconds=provider["birth_min_seconds"],
        ),
    )
    with tempfile.TemporaryDirectory(prefix="moss-r4-runtime-capacity-") as raw:
        root = Path(raw)
        manifest = root / "live-provider-manifest.json"
        manifest.write_text(json.dumps(final, sort_keys=True, indent=2) + "\n")
        admitted = verify_admission(final, base_dir=root)
        config = LiveProviderBundleConfig.from_manifest(manifest)
        preflight = config.preflight()
        if not preflight.available:
            raise RuntimeError(f"manifest preflight failed: {preflight.failures}")
        runtime_factory = build_live_runtime_factory(
            config, NoCallRunner(), tape_storage_root=root / "tapes"
        )
        runtime = runtime_factory()
        reported = runtime.descriptor.bounds.max_tape_bytes
        if reported != PER_MEETING_BYTES:
            raise AssertionError((reported, PER_MEETING_BYTES))

        database = root / "state" / "moss.sqlite3"
        session_id = asyncio.run(provision(database))
        app = create_phase2_app(
            database_path=database,
            live_runtime_factory=runtime_factory,
            live_helper_lease_seconds=30.0,
            file_work_root=root / "file-work",
            meeting_audio_root=root / "meetings",
        )
        with TestClient(app, base_url="https://moss.test") as client:
            client.cookies.set(SESSION_COOKIE, session_id, domain="moss.test", path="/")
            response = client.get("/api/live/descriptor")
            response.raise_for_status()
            app_reported = response.json()["descriptor"]["bounds"]["max_tape_bytes"]
        if app_reported != PER_MEETING_BYTES:
            raise AssertionError((app_reported, PER_MEETING_BYTES))

        state = {
            "verdict": "SUPPORTED",
            "source_manifest_bytes": SOURCE.stat().st_size,
            "candidate_manifest_bytes": manifest.stat().st_size,
            "wire_frame_bytes": bounds["frame_samples"] * 2,
            "per_meeting_minutes": 200,
            "per_meeting_max_tape_bytes": PER_MEETING_BYTES,
            "two_meeting_total_tape_bytes": MEETING_COUNT * PER_MEETING_BYTES,
            "whole_wire_frames": PER_MEETING_BYTES // (bounds["frame_samples"] * 2),
            "rolling_ring_bytes": bounds["max_retained_samples"] * 2,
            "finalizer_reported_bytes": final["bounds_config"]["max_tape_bytes"],
            "runtime_reported_bytes": reported,
            "app_descriptor_reported_bytes": app_reported,
            "provider_manifest_hash": admitted["provider_manifest_hash"],
            "changes": [str(change) for change in changes],
            "decoder_requests": 0,
        }
        print(json.dumps(state, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
