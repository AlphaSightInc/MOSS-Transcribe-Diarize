"""Build an isolated 240-minute-storage candidate manifest from the consumed manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from moss_transcribe_diarize.app.live_manifest_finalizer import (
    LiveIdentityRecalibration,
    LiveManifestRetune,
    finalize_payload,
    verify_admission,
)


CAPACITY_BYTES = 240 * 60 * 16_000 * 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-revision", required=True)
    args = parser.parse_args()

    source = args.input.expanduser().resolve()
    output = args.output.expanduser().resolve()
    payload = json.loads(source.read_text())
    # The isolated output does not share the source manifest's directory. Make its existing
    # model asset reference absolute; no asset is copied or changed.
    for asset in [*payload["assets"], payload["golden"]["input"]]:
        asset_path = Path(asset["path"])
        if not asset_path.is_absolute():
            asset["path"] = str((source.parent / asset_path).resolve())
    bounds = payload["bounds_config"]
    identity = payload["identity_config"]
    provider = payload["identity_provider"]
    final, _changes = finalize_payload(
        payload,
        source_revision=args.source_revision,
        retune=LiveManifestRetune(
            hard_cap_samples=bounds["hard_cap_samples"],
            max_retained_samples=bounds["max_retained_samples"],
            frame_samples=bounds["frame_samples"],
            max_tape_bytes=CAPACITY_BYTES,
        ),
        identity=LiveIdentityRecalibration(
            min_match_score=identity["min_match_score"],
            min_match_margin=identity["min_match_margin"],
            album_admission_seconds=provider["album_admission_seconds"],
            birth_min_seconds=provider["birth_min_seconds"],
        ),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(final, indent=2, sort_keys=True) + "\n")
    admitted = verify_admission(final, base_dir=output.parent)
    from moss_transcribe_diarize.app.live_provider_bundle import LiveProviderBundleConfig
    preflight = LiveProviderBundleConfig.from_manifest(output).preflight()
    if not preflight.available:
        raise RuntimeError(f"candidate runtime preflight failed: {preflight.failures}")
    print(json.dumps({
        "output": str(output),
        "max_tape_bytes": final["bounds_config"]["max_tape_bytes"],
        "source_revision": admitted["source_revision"],
        "provider_manifest_hash": admitted["provider_manifest_hash"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
