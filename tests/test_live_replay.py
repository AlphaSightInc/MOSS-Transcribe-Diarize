from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import wave
from copy import deepcopy
from pathlib import Path

from moss_transcribe_diarize.live_replay import main


def write_wav(path: Path, samples: int, byte: bytes = b"\0") -> bytes:
    pcm = byte * samples * 2
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(pcm)
    return pcm


def write_json(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return path


def base_manifest(tmp_path: Path) -> tuple[Path, dict, Path]:
    asset = tmp_path / "provider.asset"
    asset.write_bytes(b"offline replay provider")
    first_pcm = write_wav(tmp_path / "frame-0.wav", 1000, b"a")
    second_pcm = write_wav(tmp_path / "frame-1.wav", 1000, b"b")
    service_state = write_json(tmp_path / "service-state.json", {"live": {"enabled": False}, "pid": 123})
    manifest = {
        "schema_version": 1,
        "revision": "fixture-revision",
        "session_key": "fixture-session",
        "service_state_path": str(service_state),
        "provider": {
            "name": "manifest-fixture",
            "revision": "fixture-provider-rev",
            "assets": [
                {
                    "name": "provider-spec",
                    "path": str(asset),
                    "sha256": hashlib.sha256(asset.read_bytes()).hexdigest(),
                }
            ],
        },
        "config": {
            "max_retained_samples": 4000,
            "max_decode_samples": 4000,
            "max_rtf": 1.0,
            "endpoint_policy": {
                "min_speech_samples": 1,
                "min_silence_samples": 1,
            },
            "identity": {
                "max_speakers": 1,
                "min_match_score": 0.8,
                "min_match_margin": 0.1,
            },
        },
        "frames": [
            {
                "sequence": 0,
                "pcm_path": str(tmp_path / "frame-0.wav"),
                "sample_count": 1000,
                "sha256": hashlib.sha256(first_pcm).hexdigest(),
                "observations": [{"sample_count": 1000, "speech_present": True}],
            },
            {
                "sequence": 1,
                "pcm_path": str(tmp_path / "frame-1.wav"),
                "sample_count": 1000,
                "sha256": hashlib.sha256(second_pcm).hexdigest(),
                "observations": [{"sample_count": 1000, "speech_present": False}],
            },
        ],
        "decodes": [
            {
                "start_sample": 0,
                "end_sample": 1000,
                "transcript": "[0][S01]first[0.05]",
                "decode_seconds": 0.01,
            },
            {
                "start_sample": 1000,
                "end_sample": 2000,
                "transcript": "[0][S01]tail[0.05]",
                "decode_seconds": 0.01,
                "evidence": [
                    {
                        "local_speaker": "S01",
                        "canonical_speaker": "speaker-0001",
                        "score": 0.95,
                        "evidence_id": "fixture-evidence",
                    }
                ],
            },
        ],
    }
    return write_json(tmp_path / "manifest.json", manifest), manifest, service_state


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_live_replay_help_is_available():
    result = subprocess.run(
        [sys.executable, "-m", "moss_transcribe_diarize.live_replay", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--manifest" in result.stdout
    assert "default-off" in result.stdout


def test_live_replay_writes_deterministic_trace_summary_and_evaluator(tmp_path):
    manifest_path, _manifest, service_state = base_manifest(tmp_path)
    before_service_state = service_state.read_text(encoding="utf-8")
    out_dir = tmp_path / "out"

    code = main(["--manifest", str(manifest_path), "--out-dir", str(out_dir), "--expect-revision", "fixture-revision"])

    assert code == 0
    assert service_state.read_text(encoding="utf-8") == before_service_state
    trace = read_jsonl(out_dir / "trace.jsonl")
    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    evaluator = read_jsonl(out_dir / "evaluator.jsonl")
    assert [event["seq"] for event in trace] == list(range(len(trace)))
    assert trace[0]["event"] == "preflight"
    assert trace[-1]["event"] == "summary"
    assert summary["status"] == "passed"
    assert summary["accepted_samples"] == summary["accounted_samples"] == 2000
    assert summary["identity_snapshot"]["canonical_speakers"] == ["speaker-0001"]
    assert [row["text"] for row in evaluator] == ["first", "tail"]
    assert evaluator[1]["start"] == 0.0625


def test_live_replay_exits_nonzero_for_hard_failures(tmp_path):
    _manifest_path, manifest, _service_state = base_manifest(tmp_path)
    cases = [
        ("integrity", 2, lambda data: data["frames"][0].update({"sample_count": 999})),
        ("provider", 3, lambda data: data["provider"]["assets"][0].update({"sha256": "0" * 64})),
        (
            "identity",
            4,
            lambda data: data["decodes"][0].update({"transcript": "[0][S01]one[0.02][0.03][S02]two[0.05]"}),
        ),
        ("rtf", 5, lambda data: data["decodes"][0].update({"decode_seconds": 1.0})),
    ]

    for name, expected_code, mutate in cases:
        case_dir = tmp_path / name
        case_dir.mkdir()
        data = deepcopy(manifest)
        mutate(data)
        manifest_path = write_json(case_dir / "manifest.json", data)

        code = main(["--manifest", str(manifest_path), "--out-dir", str(case_dir / "out")])

        assert code == expected_code
        trace = read_jsonl(case_dir / "out" / "trace.jsonl")
        summary = json.loads((case_dir / "out" / "summary.json").read_text(encoding="utf-8"))
        assert trace[-1]["event"] == "failure"
        assert trace[-1]["failure_kind"] == name
        assert summary["status"] == "failed"
        assert summary["failure"]["kind"] == name
