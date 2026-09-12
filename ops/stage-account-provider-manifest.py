#!/usr/bin/env python3
"""Bind the staged Account profile to a provider finalized by its candidate code."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moss_transcribe_diarize.app.live_manifest_finalizer import (  # noqa: E402
    LiveIdentityRecalibration,
    LiveManifestRetune,
    finalize_payload,
    verify_admission,
)
from moss_transcribe_diarize.phase2_cutover import (  # noqa: E402
    _atomic_private_file,
    _parse_env_file,
)


def stage_provider_manifest(candidate_sha: str, cutover_profile: Path) -> Path:
    profile = json.loads(cutover_profile.read_text())
    account_profile = Path(profile["candidate"]["account_profile_source"]).expanduser()
    values = _parse_env_file(account_profile)
    source = Path(values["MOSS_LIVE_PROVIDER_MANIFEST"]).expanduser().resolve()
    payload = json.loads(source.read_text())
    bounds = payload["bounds_config"]
    identity = payload["identity_config"]
    provider = payload["identity_provider"]
    final, _ = finalize_payload(
        payload,
        source_revision=candidate_sha,
        retune=LiveManifestRetune(
            hard_cap_samples=bounds["hard_cap_samples"],
            max_retained_samples=bounds["max_retained_samples"],
            frame_samples=bounds["frame_samples"],
            max_tape_bytes=bounds.get("max_tape_bytes"),
        ),
        identity=LiveIdentityRecalibration(
            min_match_score=identity["min_match_score"],
            min_match_margin=identity["min_match_margin"],
            album_admission_seconds=provider["album_admission_seconds"],
            birth_min_seconds=provider["birth_min_seconds"],
        ),
    )
    # Staging stamps identity; changing deployment policy requires separate review.
    if final != {**payload, "source_revision": candidate_sha, "config_hashes": final["config_hashes"]}:
        raise ValueError("provider finalization changed policy or candidate source revision")
    # Keep relative asset paths anchored to the same host directory.
    destination = source.with_name(f"live-provider-{candidate_sha}.json")
    admission = verify_admission(final, base_dir=destination.parent)
    if admission["source_revision"] != candidate_sha:
        raise ValueError("provider descriptor revision differs from candidate SHA")
    if destination.exists():
        if json.loads(destination.read_text()) != final:
            raise ValueError("existing candidate provider manifest differs from finalized candidate")
    else:
        _atomic_private_file(destination, (json.dumps(final, indent=2, sort_keys=True) + "\n").encode())

    original = account_profile.read_text()
    updated = "".join(
        f"MOSS_LIVE_PROVIDER_MANIFEST={destination}\n"
        if line.strip().startswith("MOSS_LIVE_PROVIDER_MANIFEST=") else line
        for line in original.splitlines(keepends=True)
    )
    if updated != original:
        _atomic_private_file(account_profile, updated.encode())
    print("evidence: live_provider_manifest_staged=true")
    print(f"evidence: provider_descriptor_source_revision={admission['source_revision']}")
    return destination


if __name__ == "__main__":
    try:
        stage_provider_manifest(sys.argv[1], Path(sys.argv[2]))
    except (OSError, ValueError, KeyError) as exc:
        raise SystemExit(f"refused: {type(exc).__name__}") from None
