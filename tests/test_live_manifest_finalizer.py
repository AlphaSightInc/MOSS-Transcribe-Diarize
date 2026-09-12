from __future__ import annotations

import importlib.util
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from moss_transcribe_diarize.app.live_endpoint import EndpointPolicy
from moss_transcribe_diarize.app.live_ingest import LiveLaneIngress, LiveV2LaneCapacityError
from moss_transcribe_diarize.app.live_lane_contract import (
    LIVE_V2_REPLAY_ACK_WINDOW,
    LiveLane,
    LiveV2Frame,
)
from moss_transcribe_diarize.app.live_identity_album import (
    ALBUM_ADMISSION_SECONDS,
    ALBUM_BIRTH_MIN_SECONDS,
    ALBUM_MIN_MATCH_MARGIN,
    ALBUM_MIN_MATCH_SCORE,
)
from moss_transcribe_diarize.app.live_manifest_finalizer import (
    LIVE_RECONNECT_BURST_FRAMES,
    LIVE_RECONNECT_BURST_SAMPLES,
    LIVE_WIRE_FRAME_SAMPLES,
    LiveIdentityRecalibration,
    LiveManifestRetune,
    finalize_payload,
    main,
)
from moss_transcribe_diarize.app.live_provider_bundle import (
    LiveProviderBundleConfig,
    _bounds,
    _endpoint_config,
    _identity_config,
    compute_live_provider_bundle_hashes,
    compute_live_provider_manifest_hash,
)
from moss_transcribe_diarize.app.live_session import LIVE_SAMPLE_RATE

REPO_ROOT = Path(__file__).resolve().parents[1]
OPS_TOOL = REPO_ROOT / "ops" / "finalize-live-provider-manifest.py"
STAGE_TOOL = REPO_ROOT / "ops" / "stage-account-provider-manifest.py"

# The retuned contract values (plan D3/D5/D6): 2.5 s span cap, 60 s retention, 0.5 s frames.
HARD_CAP_SAMPLES = 40000
MAX_RETAINED_SAMPLES = 960000
FRAME_SAMPLES = 8000
DEPLOYED_REVISION = "4445a49b1c3d5e7f9012345678901234567890ab"

# The matcher thresholds the host manifest carried before the fingerprint album: calibrated
# for the latest-span overwrite policy the album replaced, and measured at 75.0 % mean live
# speaker accuracy under the album -- below ADR-0002's bar. See tests/live_identity_accuracy.
PRE_ALBUM_MIN_MATCH_SCORE = 0.5
PRE_ALBUM_MIN_MATCH_MARGIN = 0.2

STALE_HASH = "b" * 64


def _provisional_payload() -> dict:
    """A host-shaped manifest carrying the pre-retune bounds.

    The tuned sections mirror the staged host file measured on 2026-07-27:
    frame_samples 4000, hard_cap_samples 120000 in both sections, max_retained_samples
    480000, max_frame_samples 16000, decoder max_samples 120000, min_silence_samples 8000.
    """

    return {
        "schema_version": 1,
        "source_revision": "PROVISIONAL-UPDATE-AFTER-KEEPER",
        "provider_name": "moss-live",
        "provider_revision": "host-staged",
        "provider_license": "operator-owned",
        "provider_provenance": "staged on ga0-alienware-rtx4070ti",
        "packages": [
            {"distribution": "onnxruntime", "version": "1.23.2", "import_name": "onnxruntime"},
        ],
        "assets": [
            {
                "name": "identity-state",
                "path": "wespeaker-resnet152-lm.onnx",
                "byte_size": 1024,
                "sha256": "a" * 64,
                "identity": "wespeaker_resnet152_lm",
            },
        ],
        "runtime": {
            "backend": "onnxruntime-cpu",
            "device": "cpu",
            "intra_op_threads": 1,
            "inter_op_threads": 1,
            "embedding_dimension": 256,
        },
        "golden": {
            "input": {
                "name": "golden-input",
                "path": "golden.wav",
                "byte_size": 32000,
                "sha256": "c" * 64,
                "identity": "golden-v1",
            },
            "expected_output_identity": "silero_onnx+wespeaker_resnet152_lm:golden-v1",
            "expected_output_sha256": "d" * 64,
        },
        "endpoint_config": {
            "min_speech_samples": 1600,
            "min_silence_samples": 8000,
            "pre_speech_padding_samples": 1600,
            "post_speech_padding_samples": 1600,
            "hard_cap_samples": 120000,
        },
        "identity_config": {
            "max_speakers": 16,
            "min_match_score": PRE_ALBUM_MIN_MATCH_SCORE,
            "min_match_margin": PRE_ALBUM_MIN_MATCH_MARGIN,
        },
        "decoder_config": {"max_samples": 120000},
        "bounds_config": {
            "max_frame_samples": LIVE_SAMPLE_RATE,
            "max_queue_depth": 16,
            "max_retained_samples": 480000,
            "max_identity_speakers": 16,
            "max_events": 1000,
            "frame_samples": 4000,
            "stop_drain_deadline_seconds": 5.0,
        },
        "speech_provider": {
            "kind": "silero_onnx",
            "package_import": "onnxruntime",
            "factory": "make_silero",
            "asset_name": "identity-state",
            "threshold": 0.5,
        },
        "identity_provider": {
            "kind": "wespeaker_resnet152_lm",
            "package_import": "onnxruntime",
            "state_asset_name": "identity-state",
            "revision": "host-staged",
            "frontend_version": "v1",
            "min_segment_samples": 8000,
            "album_admission_seconds": 1.0,
            "birth_min_seconds": 0.5,
        },
        # Deliberately stale: a finalized manifest must never inherit declared hashes.
        "config_hashes": {
            "endpoint_config_hash": STALE_HASH,
            "identity_config_hash": STALE_HASH,
            "decoder_config_hash": STALE_HASH,
            "bounds_config_hash": STALE_HASH,
            "component_config_hash": STALE_HASH,
            "combined_config_hash": STALE_HASH,
        },
    }


def _write_provisional(tmp_path: Path, **overrides) -> Path:
    payload = _provisional_payload()
    for dotted, value in overrides.items():
        section, key = dotted.split(".", 1)
        payload[section][key] = value
    path = tmp_path / "live-provider-manifest.provisional.json"
    path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
    return path


def _finalize(
    tmp_path: Path,
    *,
    source_revision: str = DEPLOYED_REVISION,
    hard_cap_samples: int = HARD_CAP_SAMPLES,
    max_retained_samples: int = MAX_RETAINED_SAMPLES,
    frame_samples: int = FRAME_SAMPLES,
    min_match_score: float = ALBUM_MIN_MATCH_SCORE,
    min_match_margin: float = ALBUM_MIN_MATCH_MARGIN,
    album_admission_seconds: float = ALBUM_ADMISSION_SECONDS,
    birth_min_seconds: float = ALBUM_BIRTH_MIN_SECONDS,
    max_tape_bytes: int | None = None,
    input_path: Path | None = None,
    output_path: Path | None = None,
    dry_run: bool = False,
) -> int:
    source = _write_provisional(tmp_path) if input_path is None else input_path
    target = tmp_path / "live-provider-manifest.json" if output_path is None else output_path
    argv = [
        "--input",
        str(source),
        "--output",
        str(target),
        "--source-revision",
        source_revision,
        "--hard-cap-samples",
        str(hard_cap_samples),
        "--max-retained-samples",
        str(max_retained_samples),
        "--frame-samples",
        str(frame_samples),
        "--min-match-score",
        str(min_match_score),
        "--min-match-margin",
        str(min_match_margin),
        "--album-admission-seconds",
        str(album_admission_seconds),
        "--birth-min-seconds",
        str(birth_min_seconds),
    ]
    if max_tape_bytes is not None:
        argv += ["--max-tape-bytes", str(max_tape_bytes)]
    if dry_run:
        argv.append("--dry-run")
    return main(argv)


def _lane_frame(lane: LiveLane, sequence: int, samples: int = FRAME_SAMPLES) -> LiveV2Frame:
    return LiveV2Frame(
        lane=lane,
        sequence=sequence,
        capture_timestamp_ns=sequence * 500_000_000,
        device_epoch=0,
        silent=False,
        discontinuity=False,
        sample_rate=LIVE_SAMPLE_RATE,
        sample_count=samples,
        pcm=bytes(samples * 2),
    )


def test_finalize_writes_the_retuned_bounds_and_regenerated_hashes(tmp_path, capsys):
    source = _write_provisional(tmp_path)
    source_bytes = source.read_bytes()
    output = tmp_path / "live-provider-manifest.json"

    assert _finalize(tmp_path, input_path=source, output_path=output) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["source_revision"] == DEPLOYED_REVISION
    assert payload["endpoint_config"]["hard_cap_samples"] == HARD_CAP_SAMPLES
    assert payload["bounds_config"]["hard_cap_samples"] == HARD_CAP_SAMPLES
    assert payload["bounds_config"]["max_retained_samples"] == MAX_RETAINED_SAMPLES
    assert payload["bounds_config"]["frame_samples"] == FRAME_SAMPLES
    assert payload["identity_provider"]["min_segment_samples"] == 8000
    assert payload["identity_provider"]["album_admission_seconds"] == ALBUM_ADMISSION_SECONDS
    assert payload["identity_provider"]["birth_min_seconds"] == ALBUM_BIRTH_MIN_SECONDS
    # Everything the retune does not name survives untouched.
    assert payload["endpoint_config"]["min_silence_samples"] == 8000
    assert payload["decoder_config"] == {"max_samples": 120000}

    config = LiveProviderBundleConfig.from_mapping(payload, base_dir=output.parent)
    assert payload["config_hashes"] == compute_live_provider_bundle_hashes(config)
    assert STALE_HASH not in payload["config_hashes"].values()

    assert source.read_bytes() == source_bytes
    printed = capsys.readouterr().out
    assert f"wrote: {output}" in printed
    assert "evidence: hard_cap_seconds=2.5" in printed
    assert "evidence: max_retained_seconds=60.0" in printed


def test_a_stated_tape_capacity_reaches_the_deployed_bounds_and_its_hashes(tmp_path, capsys):
    """ADR-0003 D8: the complete session tape is a capacity the deployment declares."""

    output = tmp_path / "live-provider-manifest.json"
    # 300 s of 16 kHz mono PCM16 -- Appendix B Q10's own premise, and the campaign's cap.
    assert _finalize(tmp_path, output_path=output, max_tape_bytes=9_600_000) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["bounds_config"]["max_tape_bytes"] == 9_600_000
    assert _bounds(payload["bounds_config"]).max_tape_bytes == 9_600_000

    config = LiveProviderBundleConfig.from_mapping(payload, base_dir=output.parent)
    computed = compute_live_provider_bundle_hashes(config)
    assert payload["config_hashes"] == computed

    printed = capsys.readouterr().out
    assert "plan: set bounds_config.max_tape_bytes=9600000" in printed
    assert "evidence: max_tape_seconds=300.0" in printed


def test_declaring_a_tape_moves_the_bounds_hash_and_leaves_the_decode_hashes_alone(tmp_path):
    """The signature of the change: what a redeploy should expect to differ, and what not."""

    without = tmp_path / "without.json"
    with_tape = tmp_path / "with.json"
    assert _finalize(tmp_path, output_path=without) == 0
    assert _finalize(tmp_path, output_path=with_tape, max_tape_bytes=9_600_000) == 0

    before = json.loads(without.read_text(encoding="utf-8"))
    after = json.loads(with_tape.read_text(encoding="utf-8"))

    assert "max_tape_bytes" not in before["bounds_config"]
    assert before["config_hashes"]["bounds_config_hash"] != after["config_hashes"]["bounds_config_hash"]
    assert before["config_hashes"]["component_config_hash"] != after["config_hashes"]["component_config_hash"]
    # `combined_config_hash` is f(decoder, endpoint, identity): retention is none of them,
    # so a paired arm measured against the previous manifest is still the same decode.
    for key in ("combined_config_hash", "decoder_config_hash", "endpoint_config_hash", "identity_config_hash"):
        assert before["config_hashes"][key] == after["config_hashes"][key]
    assert compute_live_provider_manifest_hash(
        LiveProviderBundleConfig.from_mapping(before, base_dir=without.parent)
    ) != compute_live_provider_manifest_hash(
        LiveProviderBundleConfig.from_mapping(after, base_dir=with_tape.parent)
    )


def test_a_finalize_that_states_no_tape_clears_one_a_previous_run_declared(tmp_path, capsys):
    """Retention stays opt-in: withdrawing the flag withdraws the tape, it does not linger."""

    output = tmp_path / "live-provider-manifest.json"
    assert _finalize(tmp_path, output_path=output, max_tape_bytes=9_600_000) == 0
    capsys.readouterr()

    source = _write_provisional(tmp_path, **{"bounds_config.max_tape_bytes": 9_600_000})
    assert _finalize(tmp_path, input_path=source, output_path=output) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert "max_tape_bytes" not in payload["bounds_config"]
    assert _bounds(payload["bounds_config"]).max_tape_bytes is None
    assert "plan: clear bounds_config.max_tape_bytes" in capsys.readouterr().out


def test_finalized_manifest_admits_as_a_live_service_descriptor(tmp_path):
    output = tmp_path / "live-provider-manifest.json"
    assert _finalize(tmp_path, output_path=output) == 0

    config = LiveProviderBundleConfig.from_manifest(output)
    bounds = _bounds(config.bounds_config)
    policy = EndpointPolicy(_endpoint_config(config.endpoint_config))

    assert bounds.hard_cap_samples == HARD_CAP_SAMPLES
    assert bounds.max_retained_samples == MAX_RETAINED_SAMPLES
    assert bounds.max_frame_samples >= FRAME_SAMPLES
    assert policy.config.hard_cap_samples == HARD_CAP_SAMPLES
    # The span cap is what the ≤6 s user-visible gate rests on.
    assert bounds.hard_cap_samples / LIVE_SAMPLE_RATE == 2.5
    assert config.bounds_config["frame_samples"] * 2 == LIVE_SAMPLE_RATE


def test_finalize_states_the_matcher_thresholds_the_shipped_policy_is_calibrated_for(tmp_path, capsys):
    """Candidate 63: a recalibration is a reviewed flag, not a hand edit of the host file.

    The provisional manifest carries the pre-album pair, because that is how the deployed one
    got them -- typed into an untracked file on the host. Finalizing has to replace them with
    the pair the deployment states, carry that pair into the regenerated `identity_config_hash`
    (a hand-edited section fails preflight, so an unhashed recalibration would not run at all),
    and leave every identity key the flags do not name alone.
    """

    source = _write_provisional(tmp_path)
    output = tmp_path / "live-provider-manifest.json"
    assert _finalize(tmp_path, input_path=source, output_path=output) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    identity = _identity_config(payload["identity_config"])
    assert (identity.min_match_score, identity.min_match_margin) == (
        ALBUM_MIN_MATCH_SCORE,
        ALBUM_MIN_MATCH_MARGIN,
    )
    assert identity.max_speakers == 16  # untouched: the flags name two thresholds, not a bound
    assert json.loads(source.read_text(encoding="utf-8"))["identity_config"]["min_match_score"] == (
        PRE_ALBUM_MIN_MATCH_SCORE
    )

    config = LiveProviderBundleConfig.from_mapping(payload, base_dir=output.parent)
    assert payload["config_hashes"] == compute_live_provider_bundle_hashes(config)
    printed = capsys.readouterr().out
    assert f"evidence: identity_min_match_score={ALBUM_MIN_MATCH_SCORE}" in printed
    assert f"evidence: identity_min_match_margin={ALBUM_MIN_MATCH_MARGIN}" in printed
    assert f"evidence: identity_album_admission_seconds={ALBUM_ADMISSION_SECONDS}" in printed
    assert f"evidence: identity_birth_min_seconds={ALBUM_BIRTH_MIN_SECONDS}" in printed


def test_a_different_calibration_is_a_different_manifest_hash(tmp_path):
    """The thresholds are hash-covered, so which pair shipped is answerable after the fact."""

    album = tmp_path / "album.json"
    pre_album = tmp_path / "pre-album.json"
    assert _finalize(tmp_path, output_path=album) == 0
    assert (
        _finalize(
            tmp_path,
            output_path=pre_album,
            min_match_score=PRE_ALBUM_MIN_MATCH_SCORE,
            min_match_margin=PRE_ALBUM_MIN_MATCH_MARGIN,
        )
        == 0
    )

    left = json.loads(album.read_text(encoding="utf-8"))["config_hashes"]
    right = json.loads(pre_album.read_text(encoding="utf-8"))["config_hashes"]
    assert left["identity_config_hash"] != right["identity_config_hash"]
    assert left["combined_config_hash"] != right["combined_config_hash"]
    assert left["bounds_config_hash"] == right["bounds_config_hash"]


def test_a_different_enrollment_floor_is_a_different_manifest_hash(tmp_path):
    enrolled_at_two = tmp_path / "enrolled-at-two.json"
    enrolled_at_one = tmp_path / "enrolled-at-one.json"
    assert _finalize(tmp_path, output_path=enrolled_at_two) == 0
    assert (
        _finalize(
            tmp_path,
            output_path=enrolled_at_one,
            album_admission_seconds=1.0,
        )
        == 0
    )

    left = json.loads(enrolled_at_two.read_text(encoding="utf-8"))["config_hashes"]
    right = json.loads(enrolled_at_one.read_text(encoding="utf-8"))["config_hashes"]
    assert left["component_config_hash"] != right["component_config_hash"]
    assert compute_live_provider_manifest_hash(
        LiveProviderBundleConfig.from_manifest(enrolled_at_two)
    ) != compute_live_provider_manifest_hash(
        LiveProviderBundleConfig.from_manifest(enrolled_at_one)
    )
    assert left["identity_config_hash"] == right["identity_config_hash"]


def test_a_finalize_that_does_not_state_its_calibration_is_refused(tmp_path):
    """The flags are required for the same reason the bounds are: nothing else states them.

    Before this, `identity_config` was carried through from the provisional file untouched, so
    the thresholds the live matcher runs on were whatever the host happened to hold and no
    review saw them. Omitting a flag is an argparse refusal, not a silent inheritance.
    """

    source = _write_provisional(tmp_path)
    output = tmp_path / "live-provider-manifest.json"
    with pytest.raises(SystemExit) as refusal:
        main(
            [
                "--input",
                str(source),
                "--output",
                str(output),
                "--source-revision",
                DEPLOYED_REVISION,
                "--hard-cap-samples",
                str(HARD_CAP_SAMPLES),
                "--max-retained-samples",
                str(MAX_RETAINED_SAMPLES),
                "--frame-samples",
                str(FRAME_SAMPLES),
            ]
        )

    assert refusal.value.code == 2
    assert not output.exists()


@pytest.mark.parametrize(
    "kwargs, reason",
    [
        ({"min_match_score": 1.5}, "min_match_score must be between 0 and 1"),
        ({"min_match_score": -0.1}, "min_match_score must be between 0 and 1"),
        ({"min_match_margin": -0.2}, "min_match_margin must be non-negative"),
        ({"album_admission_seconds": 0.0}, "album_admission_seconds must be a positive number"),
        ({"birth_min_seconds": 0.0}, "birth_min_seconds must be a positive number"),
    ],
)
def test_refuses_a_calibration_the_live_runtime_would_not_admit(tmp_path, capsys, kwargs, reason):
    """There is no relation to check a threshold against, so the runtime's reader is the check.

    A free parameter has no derivation the tool could verify. What it can verify is that the
    live runtime admits the value, and it verifies that with the runtime's own reader rather
    than a second copy of its rules.
    """

    output = tmp_path / "live-provider-manifest.json"
    assert _finalize(tmp_path, output_path=output, **kwargs) == 2
    assert not output.exists()
    captured = capsys.readouterr()
    assert captured.err.startswith("refused:")
    assert "identity_config is not one the live runtime admits" in captured.err
    assert reason in captured.err


def test_retention_holds_a_reconnect_burst_on_both_lanes_and_keeps_acks_replayable(tmp_path):
    output = tmp_path / "live-provider-manifest.json"
    assert _finalize(tmp_path, output_path=output) == 0
    bounds = _bounds(LiveProviderBundleConfig.from_manifest(output).bounds_config)

    ingress = LiveLaneIngress(max_retained_samples=bounds.max_retained_samples)
    span_frames = HARD_CAP_SAMPLES // FRAME_SAMPLES
    burst_frames = LIVE_RECONNECT_BURST_FRAMES
    assert burst_frames * len(LiveLane) < LIVE_V2_REPLAY_ACK_WINDOW

    first_acks = {}
    for lane in LiveLane:
        for sequence in range(span_frames + burst_frames):
            ack = ingress.accept(_lane_frame(lane, sequence))
            if sequence == 0:
                first_acks[lane] = ack

    for lane in LiveLane:
        snapshot = ingress.snapshot(lane)
        assert snapshot.retained_samples == (span_frames + burst_frames) * FRAME_SAMPLES
        assert snapshot.retained_samples <= bounds.max_retained_samples
        # A duplicate retry of the oldest frame in the burst still finds its ack.
        assert ingress.accept(_lane_frame(lane, 0)) == first_acks[lane]

    retained_frames = bounds.max_retained_samples // FRAME_SAMPLES
    for lane in LiveLane:
        for sequence in range(span_frames + burst_frames, retained_frames):
            ingress.accept(_lane_frame(lane, sequence))
        assert ingress.snapshot(lane).retained_samples == bounds.max_retained_samples
        with pytest.raises(LiveV2LaneCapacityError):
            ingress.accept(_lane_frame(lane, retained_frames))

    assert retained_frames * FRAME_SAMPLES / LIVE_SAMPLE_RATE == 60.0
    assert bounds.max_retained_samples - LIVE_RECONNECT_BURST_SAMPLES - HARD_CAP_SAMPLES > 0


@pytest.mark.parametrize(
    "kwargs, reason",
    [
        ({"source_revision": "PROVISIONAL-UPDATE-AFTER-KEEPER"}, "source_revision"),
        ({"source_revision": DEPLOYED_REVISION.upper()}, "source_revision"),
        ({"source_revision": DEPLOYED_REVISION[:12]}, "source_revision"),
        ({"frame_samples": 4000}, "frame_samples"),
        ({"hard_cap_samples": 40001}, "wire frames"),
        ({"hard_cap_samples": 8000}, "min_silence_samples"),
        ({"hard_cap_samples": 160000}, "decoder_config.max_samples"),
        ({"max_retained_samples": 240000}, "reconnect burst"),
        ({"max_tape_bytes": 9_600_001}, "wire frames"),
        ({"max_tape_bytes": 1_904_000}, "rolling ring"),
        ({"max_tape_bytes": 0}, "max_tape_bytes"),
    ],
)
def test_refuses_bounds_the_wire_contract_cannot_carry(tmp_path, capsys, kwargs, reason):
    output = tmp_path / "live-provider-manifest.json"
    assert _finalize(tmp_path, output_path=output, **kwargs) == 2
    assert not output.exists()
    captured = capsys.readouterr()
    assert captured.err.startswith("refused:")
    assert reason in captured.err


def test_refuses_a_manifest_whose_untuned_sections_break_the_contract(tmp_path, capsys):
    source = _write_provisional(tmp_path, **{"endpoint_config.min_silence_samples": 4000})
    output = tmp_path / "live-provider-manifest.json"
    assert _finalize(tmp_path, input_path=source, output_path=output) == 2
    assert not output.exists()
    assert "min_silence_samples" in capsys.readouterr().err


def test_refuses_to_overwrite_its_own_input_or_read_a_broken_manifest(tmp_path, capsys):
    source = _write_provisional(tmp_path)
    assert _finalize(tmp_path, input_path=source, output_path=source) == 2
    assert "provisional input manifest" in capsys.readouterr().err
    assert json.loads(source.read_text(encoding="utf-8"))["source_revision"].startswith("PROVISIONAL")

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert _finalize(tmp_path, input_path=broken) == 2
    assert "not valid JSON" in capsys.readouterr().err

    assert _finalize(tmp_path, input_path=tmp_path / "absent.json") == 2
    assert "not a readable file" in capsys.readouterr().err


def test_dry_run_prints_the_plan_and_rollback_and_writes_nothing(tmp_path, capsys):
    output = tmp_path / "live-provider-manifest.json"
    assert _finalize(tmp_path, output_path=output, dry_run=True) == 0
    assert not output.exists()

    lines = capsys.readouterr().out.splitlines()
    assert f"plan: set bounds_config.max_retained_samples={MAX_RETAINED_SAMPLES}" in lines
    assert f"plan: set identity_config.min_match_score={ALBUM_MIN_MATCH_SCORE}" in lines
    assert f"plan: set identity_config.min_match_margin={ALBUM_MIN_MATCH_MARGIN}" in lines
    assert (
        f"plan: set identity_provider.album_admission_seconds={ALBUM_ADMISSION_SECONDS}"
        in lines
    )
    assert f"plan: set identity_provider.birth_min_seconds={ALBUM_BIRTH_MIN_SECONDS}" in lines
    assert "plan: regenerate config_hashes" in lines
    assert f"rollback: rm -f {output}" in lines
    assert f"dry-run: {output} not written" in lines
    # The operator sees the measured headroom before deciding to write.
    assert any(line.startswith("evidence: retention_headroom_seconds=") for line in lines)


def test_rerunning_the_finalizer_is_unchanged_and_does_not_rewrite(tmp_path, capsys):
    source = _write_provisional(tmp_path)
    output = tmp_path / "live-provider-manifest.json"
    assert _finalize(tmp_path, input_path=source, output_path=output) == 0
    capsys.readouterr()
    before = output.stat()

    assert _finalize(tmp_path, input_path=source, output_path=output) == 0
    after = output.stat()
    printed = capsys.readouterr().out

    assert f"unchanged: {output}" in printed
    assert "rollback:" not in printed
    assert (after.st_ino, after.st_mtime_ns) == (before.st_ino, before.st_mtime_ns)


def test_replacing_a_differing_manifest_backs_it_up_before_writing(tmp_path, capsys):
    source = _write_provisional(tmp_path)
    output = tmp_path / "live-provider-manifest.json"
    stale_bytes = b'{"schema_version": 1, "stale": true}\n'
    output.write_bytes(stale_bytes)

    assert _finalize(tmp_path, input_path=source, output_path=output) == 0
    lines = capsys.readouterr().out.splitlines()

    rollback_line = next(line for line in lines if line.startswith("rollback: "))
    assert lines.index(rollback_line) < lines.index(f"wrote: {output}")
    _, backup, restored = rollback_line.removeprefix("rollback: ").split()
    assert Path(backup).read_bytes() == stale_bytes
    assert json.loads(output.read_text(encoding="utf-8"))["source_revision"] == DEPLOYED_REVISION

    shutil.move(backup, restored)
    assert output.read_bytes() == stale_bytes


def test_tracked_ops_tool_finalizes_from_the_checkout(tmp_path):
    source = _write_provisional(tmp_path)
    output = tmp_path / "live-provider-manifest.json"
    result = subprocess.run(
        [
            sys.executable,
            str(OPS_TOOL),
            "--input",
            str(source),
            "--output",
            str(output),
            "--source-revision",
            DEPLOYED_REVISION,
            "--hard-cap-samples",
            str(HARD_CAP_SAMPLES),
            "--max-retained-samples",
            str(MAX_RETAINED_SAMPLES),
            "--frame-samples",
            str(FRAME_SAMPLES),
            "--min-match-score",
            str(ALBUM_MIN_MATCH_SCORE),
            "--min-match-margin",
            str(ALBUM_MIN_MATCH_MARGIN),
            "--album-admission-seconds",
            str(ALBUM_ADMISSION_SECONDS),
            "--birth-min-seconds",
            str(ALBUM_BIRTH_MIN_SECONDS),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["bounds_config"]["frame_samples"] == LIVE_WIRE_FRAME_SAMPLES
    assert payload["bounds_config"]["max_retained_samples"] == MAX_RETAINED_SAMPLES
    assert payload["source_revision"] == DEPLOYED_REVISION
    assert payload["identity_config"]["min_match_score"] == ALBUM_MIN_MATCH_SCORE
    assert payload["identity_provider"]["album_admission_seconds"] == ALBUM_ADMISSION_SECONDS
    assert payload["identity_provider"]["birth_min_seconds"] == ALBUM_BIRTH_MIN_SECONDS
    assert f"wrote: {output}" in result.stdout


@pytest.fixture
def candidate_provider_tree(tmp_path):
    home = tmp_path / "home"
    config = home / ".config/moss-transcribe-diarize"
    staged = config / "staged/moss-account.env"
    staged.parent.mkdir(parents=True)
    live = home / ".local/share/moss-transcribe-diarize/live"
    live.mkdir(parents=True)
    source = live / "previous-provider.json"
    payload, _ = finalize_payload(
        _provisional_payload(),
        source_revision="a" * 40,
        retune=LiveManifestRetune(HARD_CAP_SAMPLES, MAX_RETAINED_SAMPLES, FRAME_SAMPLES, 19200000),
        identity=LiveIdentityRecalibration(
            ALBUM_MIN_MATCH_SCORE, ALBUM_MIN_MATCH_MARGIN,
            ALBUM_ADMISSION_SECONDS, ALBUM_BIRTH_MIN_SECONDS,
        ),
    )
    source.write_text(json.dumps(payload))
    staged.write_text(
        f"# Keep all unrelated assignments verbatim.\nMOSS_LIVE_PROVIDER_MANIFEST={source}\n"
        'MOSS_LLM_UPSTREAMS=[{"name":"test","base_url":"http://localhost:1234/v1"}]\n'
        "MOSS_LIVE_DRAFT_LANE_SECONDS=1.0\nMOSS_TLS_CERTFILE=unchanged-cert\n"
    )
    staged.chmod(0o600)
    active = config / "moss-account.env"
    active.write_text("active profile must not change\n")
    profile = config / "moss-cutover.json"
    profile.write_text(json.dumps({
        "candidate": {"account_profile_source": str(staged)},
        "candidate_manifest": "previous-candidate.json",
    }))
    profile.chmod(0o600)
    release = home / ".local/share/moss-transcribe-diarize/account-runtimes" / DEPLOYED_REVISION
    (release / "bin").mkdir(parents=True)
    python = release / "bin/python"
    python.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} "$@"\n')
    python.chmod(0o755)
    checkout = tmp_path / "candidate-checkout"
    (checkout / "ops").mkdir(parents=True)
    shutil.copy2(STAGE_TOOL, checkout / "ops" / STAGE_TOOL.name)
    (checkout / "moss_transcribe_diarize").symlink_to(REPO_ROOT / "moss_transcribe_diarize")
    spec = importlib.util.spec_from_file_location("stage_account_provider", STAGE_TOOL)
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    return home, release, checkout, source, staged, profile, active, tool


def test_candidate_stage_finalizes_provider_with_fake_runtime_before_repointing(candidate_provider_tree):
    home, release, checkout, source, staged, profile, active, tool = candidate_provider_tree
    originals = {p: p.read_bytes() for p in (source, staged, profile, active)}
    script = (REPO_ROOT / "ops/stage-account-candidate.sh").read_text()
    start = script.index("finalize_candidate_provider() {")
    end = script.index("\n}", start) + 2
    # Execute the actual shell boundary with a fake installed runtime and detached checkout.
    shell = (
        'set -eu\nRELEASE="$1"\nCHECKOUT="$2"\nLINUX_USER_DIR="$3"\n'
        'CANDIDATE_SHA="$4"\nSQLITE_PREFIX="$3/sqlite"\n'
        + script[start:end] + "\nfinalize_candidate_provider\n"
    )
    command = ["bash", "-c", shell, "bash", str(release), str(checkout), str(home), DEPLOYED_REVISION]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    destination = source.with_name(f"live-provider-{DEPLOYED_REVISION}.json")
    final = json.loads(destination.read_text())
    assert tool.verify_admission(final, base_dir=destination.parent)["source_revision"] == DEPLOYED_REVISION
    previous = json.loads(originals[source])
    assert final == {**previous, "source_revision": DEPLOYED_REVISION, "config_hashes": final["config_hashes"]}
    assert staged.read_bytes() == originals[staged].replace(str(source).encode(), str(destination).encode())
    assert staged.stat().st_mode & 0o777 == 0o600
    assert destination.stat().st_mode & 0o777 == 0o600
    for path in (source, profile, active):
        assert path.read_bytes() == originals[path]
    assert script.index("\nfinalize_candidate_provider\n") < script.index('ln -s "${RELEASE}" "${CHECKOUT}/.venv"')
    assert script.index("\nfinalize_candidate_provider\n") < script.index('if [ ! -e "${MANIFEST}" ]')
    # A repeated stage now reads its own finalized provider; it must remain idempotent.
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in (staged, destination)}
    repeated = subprocess.run(command, capture_output=True, text=True)
    assert repeated.returncode == 0, repeated.stderr
    assert {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in before} == before


@pytest.mark.parametrize("failure", ["descriptor_revision", "generated_revision", "policy", "existing_manifest"])
def test_candidate_stage_refuses_provider_mismatch_without_repointing(
    candidate_provider_tree, monkeypatch, failure,
):
    _, _, _, source, staged, profile, active, tool = candidate_provider_tree
    before = {p: p.read_bytes() for p in (source, staged, profile, active)}
    destination = source.with_name(f"live-provider-{DEPLOYED_REVISION}.json")
    if failure == "descriptor_revision":
        verify = tool.verify_admission
        monkeypatch.setattr(tool, "verify_admission", lambda *a, **kw: {
            **verify(*a, **kw), "source_revision": "b" * 40,
        })
    elif failure in ("generated_revision", "policy"):
        finalize = tool.finalize_payload

        def broken_finalizer(*args, **kwargs):
            payload, evidence = finalize(*args, **kwargs)
            if failure == "generated_revision":
                payload["source_revision"] = "b" * 40
            else:
                payload["identity_provider"]["album_admission_seconds"] += 1.0
            return payload, evidence

        monkeypatch.setattr(tool, "finalize_payload", broken_finalizer)
    else:
        destination.write_bytes(before[source])
    with pytest.raises(ValueError, match="revision|policy|differs"):
        tool.stage_provider_manifest(DEPLOYED_REVISION, profile)
    assert {path: path.read_bytes() for path in before} == before
    if failure == "existing_manifest":
        assert destination.read_bytes() == before[source]
    else:
        assert not destination.exists()
