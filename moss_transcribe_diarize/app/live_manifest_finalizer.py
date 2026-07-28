"""Generate the deployed live provider manifest bounds from the live wire contract.

The deployed manifest is host-owned and provisional until a reviewed revision exists.
Finalizing it means three things, and all three are mechanical: stamp the deployed
source revision, retune the bounds the Mac client's wire contract needs, and regenerate
the bundle config hashes. A hand-edited ``bounds_config`` fails the runtime's declared
hash comparison at preflight, so the generated hashes are the only ones that admit.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .live_endpoint import EndpointPolicy
from .live_lane_contract import LIVE_V2_REPLAY_ACK_WINDOW, LiveLane
from .live_provider_bundle import (
    LiveProviderBundleAdmissionError,
    LiveProviderBundleConfig,
    compute_live_provider_bundle_hashes,
    compute_live_provider_manifest_hash,
)

# Admission must be proven with the readers the live runtime itself uses; rebuilding
# the mapping here would prove only that this module agrees with itself.
from .live_provider_bundle import _bounds as read_service_bounds
from .live_provider_bundle import _endpoint_config as read_endpoint_policy_config
from .live_service_runtime import LiveServiceConfigHashes, LiveServiceDescriptor
from .live_session import LIVE_SAMPLE_RATE


class LiveManifestFinalizeError(ValueError):
    """A finalize request that the live wire contract refuses."""


def _contract_samples(seconds: float, name: str) -> int:
    exact = LIVE_SAMPLE_RATE * seconds
    samples = int(round(exact))
    if abs(exact - samples) > 1e-9:
        raise ValueError(f"{name} is not a whole number of {LIVE_SAMPLE_RATE} Hz samples.")
    return samples


# The wire contract the Mac client implements (NativeLaneWireFormat.live) and the
# retention headroom its outbox requires (CaptureFrameOutbox).
LIVE_WIRE_FRAME_SECONDS = 0.5
LIVE_MAX_WIRE_FRAME_SECONDS = 1.0
LIVE_MIN_SILENCE_SECONDS = 0.5
LIVE_CLIENT_OUTBOX_SECONDS = 15.0

LIVE_WIRE_FRAME_SAMPLES = _contract_samples(LIVE_WIRE_FRAME_SECONDS, "live wire frame")
LIVE_MAX_WIRE_FRAME_SAMPLES = _contract_samples(LIVE_MAX_WIRE_FRAME_SECONDS, "maximum wire frame")
LIVE_MIN_SILENCE_SAMPLES = _contract_samples(LIVE_MIN_SILENCE_SECONDS, "minimum silence")
LIVE_RECONNECT_BURST_SAMPLES = _contract_samples(LIVE_CLIENT_OUTBOX_SECONDS, "client outbox")
LIVE_RECONNECT_BURST_FRAMES = LIVE_RECONNECT_BURST_SAMPLES // LIVE_WIRE_FRAME_SAMPLES


@dataclass(frozen=True, slots=True)
class LiveManifestRetune:
    """The three bounds a deployment states explicitly, checked against the contract."""

    hard_cap_samples: int
    max_retained_samples: int
    frame_samples: int

    def __post_init__(self) -> None:
        for name in ("hard_cap_samples", "max_retained_samples", "frame_samples"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise LiveManifestFinalizeError(f"{name} must be a positive integer.")


def finalize_payload(
    payload: Mapping[str, Any],
    *,
    source_revision: str,
    retune: LiveManifestRetune,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the finalized manifest payload and the contract evidence behind it."""

    _require_source_revision(source_revision)
    final = deepcopy(dict(payload))
    for key in ("endpoint_config", "bounds_config", "decoder_config"):
        section = final.get(key)
        if not isinstance(section, Mapping):
            raise LiveManifestFinalizeError(f"{key} is required in the input manifest.")
        final[key] = dict(section)

    final["source_revision"] = source_revision
    final["endpoint_config"]["hard_cap_samples"] = retune.hard_cap_samples
    final["bounds_config"]["hard_cap_samples"] = retune.hard_cap_samples
    final["bounds_config"]["max_retained_samples"] = retune.max_retained_samples
    final["bounds_config"]["frame_samples"] = retune.frame_samples

    evidence = validate_contract(final)

    # The declared hashes are regenerated from the retuned sections, never carried over:
    # they are what the runtime compares against at preflight.
    final["config_hashes"] = {}
    config = LiveProviderBundleConfig.from_mapping(final)
    final["config_hashes"] = compute_live_provider_bundle_hashes(config)
    return final, evidence


def validate_contract(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Check the finalized bounds against the live wire contract; return the evidence."""

    endpoint = _section(payload, "endpoint_config")
    bounds = _section(payload, "bounds_config")
    decoder = _section(payload, "decoder_config")

    frame_samples = _positive(bounds, "frame_samples", "bounds_config")
    max_frame_samples = _positive(bounds, "max_frame_samples", "bounds_config")
    hard_cap = _positive(bounds, "hard_cap_samples", "bounds_config")
    endpoint_hard_cap = _positive(endpoint, "hard_cap_samples", "endpoint_config")
    max_retained = _positive(bounds, "max_retained_samples", "bounds_config")
    min_silence = _positive(endpoint, "min_silence_samples", "endpoint_config")
    decoder_max = _positive(decoder, "max_samples", "decoder_config")

    if frame_samples != LIVE_WIRE_FRAME_SAMPLES:
        raise LiveManifestFinalizeError(
            f"frame_samples must be the {LIVE_WIRE_FRAME_SECONDS} s wire frame "
            f"({LIVE_WIRE_FRAME_SAMPLES} samples) the capture client emits; got {frame_samples}."
        )
    if not frame_samples <= max_frame_samples <= LIVE_MAX_WIRE_FRAME_SAMPLES:
        raise LiveManifestFinalizeError(
            f"max_frame_samples must hold one wire frame and stay within the "
            f"{LIVE_MAX_WIRE_FRAME_SAMPLES}-sample contract maximum; got {max_frame_samples}."
        )
    if endpoint_hard_cap != hard_cap:
        raise LiveManifestFinalizeError(
            "endpoint_config.hard_cap_samples and bounds_config.hard_cap_samples must be the "
            f"same span cap; got {endpoint_hard_cap} and {hard_cap}."
        )
    if min_silence != LIVE_MIN_SILENCE_SAMPLES:
        raise LiveManifestFinalizeError(
            f"min_silence_samples must be the contract {LIVE_MIN_SILENCE_SAMPLES} samples "
            f"({LIVE_MIN_SILENCE_SECONDS} s); got {min_silence}."
        )
    if hard_cap % frame_samples:
        raise LiveManifestFinalizeError(
            f"hard_cap_samples must be a whole number of {frame_samples}-sample wire frames; "
            f"got {hard_cap}."
        )
    if hard_cap <= min_silence:
        raise LiveManifestFinalizeError(
            f"hard_cap_samples {hard_cap} must exceed min_silence_samples {min_silence}, "
            "otherwise the cap preempts every silence close."
        )
    if hard_cap > decoder_max:
        raise LiveManifestFinalizeError(
            f"hard_cap_samples {hard_cap} exceeds decoder_config.max_samples {decoder_max}; "
            "a capped span must decode in one bounded request."
        )
    if max_retained % frame_samples:
        raise LiveManifestFinalizeError(
            f"max_retained_samples must be a whole number of {frame_samples}-sample wire "
            f"frames; got {max_retained}."
        )
    required_retention = LIVE_RECONNECT_BURST_SAMPLES + hard_cap
    if max_retained < required_retention:
        raise LiveManifestFinalizeError(
            f"max_retained_samples {max_retained} cannot hold a {LIVE_CLIENT_OUTBOX_SECONDS} s "
            f"client reconnect burst ({LIVE_RECONNECT_BURST_SAMPLES}) on top of one open "
            f"{hard_cap}-sample span; needs at least {required_retention}."
        )
    replay_frames = LIVE_RECONNECT_BURST_FRAMES * len(LiveLane)
    if replay_frames > LIVE_V2_REPLAY_ACK_WINDOW:
        raise LiveManifestFinalizeError(
            f"a {LIVE_CLIENT_OUTBOX_SECONDS} s outbox on {len(LiveLane)} lanes replays "
            f"{replay_frames} frames, beyond the {LIVE_V2_REPLAY_ACK_WINDOW}-ack replay window."
        )

    return {
        "frame_samples": frame_samples,
        "frame_seconds": frame_samples / LIVE_SAMPLE_RATE,
        "hard_cap_samples": hard_cap,
        "hard_cap_seconds": hard_cap / LIVE_SAMPLE_RATE,
        "max_retained_samples": max_retained,
        "max_retained_seconds": max_retained / LIVE_SAMPLE_RATE,
        "reconnect_burst_samples": LIVE_RECONNECT_BURST_SAMPLES,
        "retention_headroom_seconds": (max_retained - required_retention) / LIVE_SAMPLE_RATE,
        "decoder_headroom_samples": decoder_max - hard_cap,
        "replay_ack_headroom_frames": LIVE_V2_REPLAY_ACK_WINDOW - replay_frames,
    }


def verify_admission(payload: Mapping[str, Any], *, base_dir: Path) -> dict[str, Any]:
    """Prove the finalized payload admits as a live service descriptor."""

    config = LiveProviderBundleConfig.from_mapping(payload, base_dir=base_dir)
    computed = compute_live_provider_bundle_hashes(config)
    if config.declared_config_hashes != computed:
        raise LiveManifestFinalizeError("finalized config_hashes do not match the generated hashes.")

    EndpointPolicy(read_endpoint_policy_config(config.endpoint_config))
    bounds = read_service_bounds(config.bounds_config)
    descriptor = LiveServiceDescriptor(
        source_revision=config.source_revision,
        provider_name=config.provider_name,
        provider_revision=config.provider_revision,
        provider_manifest_hash=compute_live_provider_manifest_hash(config),
        config_hashes=LiveServiceConfigHashes(
            endpoint_config_hash=computed["endpoint_config_hash"],
            identity_config_hash=computed["identity_config_hash"],
            decoder_config_hash=computed["decoder_config_hash"],
            combined_config_hash=computed["combined_config_hash"],
        ),
        bounds=bounds,
        frame_samples=int(config.bounds_config["frame_samples"]),
    )
    return {
        "descriptor_frame_samples": descriptor.frame_samples,
        "descriptor_sample_rate": descriptor.sample_rate,
        "bounds_config_hash": computed["bounds_config_hash"],
        "combined_config_hash": computed["combined_config_hash"],
        "provider_manifest_hash": descriptor.provider_manifest_hash,
        "source_revision": descriptor.source_revision,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the deployed live provider manifest bounds and config hashes.",
    )
    parser.add_argument("--input", required=True, help="Provisional live provider manifest JSON.")
    parser.add_argument("--output", required=True, help="Finalized manifest JSON to generate.")
    parser.add_argument("--source-revision", required=True, help="Deployed commit SHA (40 hex).")
    parser.add_argument("--hard-cap-samples", required=True, type=int)
    parser.add_argument("--max-retained-samples", required=True, type=int)
    parser.add_argument("--frame-samples", required=True, type=int)
    parser.add_argument("--dry-run", action="store_true", help="Print the plan and rollback; write nothing.")
    args = parser.parse_args(argv)

    try:
        return _run(args)
    except (LiveManifestFinalizeError, LiveProviderBundleAdmissionError, ValueError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


def _run(args: argparse.Namespace) -> int:
    input_path = Path(args.input).expanduser()
    output_path = Path(args.output).expanduser()
    if not input_path.is_file():
        raise LiveManifestFinalizeError(f"input manifest is not a readable file: {input_path}")
    if _same_file(input_path, output_path):
        raise LiveManifestFinalizeError("output must not overwrite the provisional input manifest.")
    if not output_path.parent.is_dir():
        raise LiveManifestFinalizeError(f"output directory does not exist: {output_path.parent}")

    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LiveManifestFinalizeError(f"input manifest is not valid JSON: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise LiveManifestFinalizeError("input manifest root must be an object.")

    retune = LiveManifestRetune(
        hard_cap_samples=args.hard_cap_samples,
        max_retained_samples=args.max_retained_samples,
        frame_samples=args.frame_samples,
    )
    final, contract = finalize_payload(payload, source_revision=args.source_revision, retune=retune)
    text = json.dumps(final, sort_keys=True, indent=2) + "\n"
    admission = verify_admission(final, base_dir=output_path.parent)

    existing = output_path.read_text(encoding="utf-8") if output_path.is_file() else None
    unchanged = existing == text
    backup_path = None if existing is None or unchanged else _backup_path(output_path)

    for line in (
        f"read {input_path}",
        f"set source_revision={args.source_revision}",
        f"set endpoint_config.hard_cap_samples={retune.hard_cap_samples}",
        f"set bounds_config.hard_cap_samples={retune.hard_cap_samples}",
        f"set bounds_config.max_retained_samples={retune.max_retained_samples}",
        f"set bounds_config.frame_samples={retune.frame_samples}",
        "regenerate config_hashes",
        f"write {output_path}",
    ):
        print(f"plan: {line}")

    rollback = (
        f"mv {backup_path} {output_path}" if backup_path is not None else f"rm -f {output_path}"
    )
    if not unchanged:
        print(f"rollback: {rollback}")

    for key, value in {**contract, **admission}.items():
        print(f"evidence: {key}={value}")

    if args.dry_run:
        print(f"dry-run: {output_path} not written")
        return 0
    if unchanged:
        print(f"unchanged: {output_path}")
        return 0

    if backup_path is not None:
        os.replace(output_path, backup_path)
        print(f"backup: {backup_path}")
    _write_atomic(output_path, text)
    print(f"wrote: {output_path}")
    return 0


def _write_atomic(path: Path, text: str) -> None:
    staged = path.with_name(path.name + ".staged")
    staged.write_text(text, encoding="utf-8")
    os.replace(staged, path)


def _backup_path(path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return path.with_name(f"{path.name}.backup-{stamp}")


def _same_file(left: Path, right: Path) -> bool:
    return left.resolve() == right.resolve()


def _require_source_revision(value: str) -> None:
    if not isinstance(value, str) or len(value) != 40 or any(char not in "0123456789abcdef" for char in value):
        raise LiveManifestFinalizeError(
            "source_revision must be the deployed 40-character lowercase commit SHA."
        )


def _section(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    section = payload.get(key)
    if not isinstance(section, Mapping):
        raise LiveManifestFinalizeError(f"{key} is required in the input manifest.")
    return section


def _positive(section: Mapping[str, Any], key: str, name: str) -> int:
    value = section.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise LiveManifestFinalizeError(f"{name}.{key} must be a positive integer.")
    return value


__all__ = [
    "LIVE_CLIENT_OUTBOX_SECONDS",
    "LIVE_MAX_WIRE_FRAME_SAMPLES",
    "LIVE_MIN_SILENCE_SAMPLES",
    "LIVE_RECONNECT_BURST_FRAMES",
    "LIVE_RECONNECT_BURST_SAMPLES",
    "LIVE_WIRE_FRAME_SAMPLES",
    "LiveManifestFinalizeError",
    "LiveManifestRetune",
    "finalize_payload",
    "main",
    "validate_contract",
    "verify_admission",
]


if __name__ == "__main__":  # pragma: no cover - module entrypoint
    raise SystemExit(main())
