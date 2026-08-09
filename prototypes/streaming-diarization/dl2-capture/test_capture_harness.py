#!/usr/bin/env python3
"""Minimal red-first safety tests for the DL2 capture harness."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import capture_harness

from capture_harness import (
    HarnessRefusal,
    assert_no_overdue_retained_raw,
    begin_session,
    capture_script,
    validate_capture_window,
    validate_grant,
    validate_tape_dir,
)


class CaptureHarnessSafetyTests(unittest.TestCase):
    def test_finish_external_stop_recovery_never_calls_stop_again(self) -> None:
        observed = {
            "status": {
                "ok": True,
                "running": False,
                "publishedFrameCount": 2747,
                "outboxRetainedFrames": 0,
                "lanes": [
                    {"lane": "system", "state": "stopped"},
                    {"lane": "microphone", "state": "stopped"},
                ],
            },
            "topology_read_only": "output_volume=50;output_muted=false",
            "checked_at_utc": "2026-08-09T03:36:44Z",
        }
        with mock.patch("capture_harness.capture_state", return_value=observed), mock.patch(
            "capture_harness.capture_script"
        ) as stop:
            result = capture_harness.finish_stop(external_stop_recovery=True)
        stop.assert_not_called()
        self.assertEqual(result["status"]["publishedFrameCount"], 2747)
        self.assertEqual(result["deviation"]["kind"], "external_stop_after_controller_loss")

    def test_block_device_gate_refuses_airpods_input(self) -> None:
        with self.assertRaisesRegex(HarnessRefusal, "default_input_device_refused"):
            capture_harness.assert_block_audio_devices(
                {
                    "default_input": {"name": "G@0 AirPods Pro #2"},
                    "default_output": {"name": "G@0 AirPods Pro #2"},
                },
                {
                    "default_input_name": "MacBook Pro Microphone",
                    "default_output_name_contains": "AirPods Pro",
                },
            )

    def test_block_device_gate_accepts_builtin_input_and_airpods_output(self) -> None:
        capture_harness.assert_block_audio_devices(
            {
                "default_input": {
                    "name": "MacBook Pro Microphone",
                    "uid": "BuiltInMicrophoneDevice",
                },
                "default_output": {
                    "name": "G@0 AirPods Pro #2",
                    "uid": "A4-C6-F0-D9-8F-14:output",
                },
            },
            {
                "default_input_name": "MacBook Pro Microphone",
                "default_input_uid": "BuiltInMicrophoneDevice",
                "default_output_name_contains": "AirPods Pro",
            },
        )

    def test_capture_script_uses_hostkey_checked_tailscale_fallback_on_dns_failure(self) -> None:
        completed = [
            mock.Mock(returncode=255, stdout="", stderr="ssh: Could not resolve hostname m4mbp"),
            mock.Mock(returncode=0, stdout="100.64.0.4\n", stderr=""),
            mock.Mock(returncode=0, stdout="OK\n", stderr=""),
        ]
        with mock.patch("capture_harness.subprocess.run", side_effect=completed) as invoked:
            self.assertEqual(capture_script("printf ok\n"), "OK\n")
        fallback = invoked.call_args_list[2].args[0]
        self.assertIn("HostName=100.64.0.4", fallback)
        self.assertIn("HostKeyAlias=m4mbp", fallback)
        self.assertIn("ga0@m4mbp", fallback)

    def test_overdue_retained_raw_blocks_new_preflight(self) -> None:
        grant = {"raw_delete_deadline_et": "2026-08-06T23:05:00-04:00"}
        ledger = {"sessions": [{"session_id": "retained-a", "raw_deleted": False}]}
        with self.assertRaisesRegex(HarnessRefusal, "retained_raw_cleanup_overdue:retained-a"):
            assert_no_overdue_retained_raw(
                grant,
                ledger,
                dt.datetime.fromisoformat("2026-08-06T23:05:00-04:00"),
            )

    def test_begin_embeds_descriptor_hard_abort_before_speech(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            program = Path(raw)
            (program / "grant.json").write_text(
                json.dumps(
                    {
                        "ttl_seconds": 86_400,
                        "program_cap_bytes": 2_147_483_648,
                        "decision_deadline_et": "2099-01-01T00:00:00-05:00",
                        "raw_delete_deadline_et": "2099-01-02T00:00:00-05:00",
                        "retention_root": "/home/example/dl2",
                    }
                )
            )
            (program / "program-ledger.json").write_text(
                json.dumps({"captured_bytes_total": 0, "sessions": []})
            )
            emitted: dict[str, str] = {}

            def fake_capture(script: str) -> str:
                emitted["script"] = script
                return "\n".join(
                    (
                        'START\t{"ok":true}',
                        'HANDOFF\t{"sessionID":"session-a"}',
                        'STATUS\t{"running":true,"lanes":[{"lane":"system","state":"capturing"},{"lane":"microphone","state":"capturing"}]}',
                        "SNAPSHOT_HTTP\t200",
                        "SOURCE_REVISION\t9089b33210401111865da7abc160ab0bcb4aa266",
                        "SNAPSHOT_SHA256\t" + "a" * 64,
                    )
                )

            args = argparse.Namespace(
                operator_present=True,
                consented_content=True,
                program_root=program,
                projected_bytes=1,
                shape="S01",
            )
            with mock.patch("capture_harness.server_preflight", return_value={"verdict": "PASS"}), mock.patch(
                "capture_harness.capture_state",
                return_value={
                    "status": {
                        "running": False,
                        "lanes": [
                            {"lane": "system", "state": "stopped"},
                            {"lane": "microphone", "state": "stopped"},
                        ],
                    }
                },
            ), mock.patch("capture_harness.capture_script", side_effect=fake_capture):
                self.assertEqual(begin_session(args), 0)
            self.assertIn(".snapshot.descriptor.source_revision", emitted["script"])
            self.assertIn('deadline=$((SECONDS + 3))', emitted["script"])
            self.assertIn('.state=="capturing"', emitted["script"])
            self.assertNotIn('.state=="running"', emitted["script"])
            self.assertIn('if [ "$rc" -ne 0 ] && [ "$started" = 1 ]', emitted["script"])
            self.assertIn('"$cli" stop', emitted["script"])
            manifest = json.loads((program / "sessions" / "S01-session-a" / "session-manifest.json").read_text())
            self.assertEqual(
                manifest["live_descriptor_preflight"]["verdict"],
                "PASS_BEFORE_OPERATOR_SPEECH",
            )

    def test_post_decision_pilot_is_single_shape_single_use(self) -> None:
        grant = {
            "decision_deadline_et": "2026-08-06T07:50:00-04:00",
            "raw_delete_deadline_et": "2026-08-06T23:05:00-04:00",
            "post_decision_pilot_authorization": {
                "authorized": True,
                "shape_id": "S01",
                "single_use": True,
            },
        }
        now = dt.datetime.fromisoformat("2026-08-06T13:30:00-04:00")
        self.assertEqual(
            validate_capture_window(grant, {"sessions": []}, "S01", now),
            "POST_DECISION_SINGLE_USE_PILOT",
        )

    def test_block_grant_refuses_shape_outside_scope(self) -> None:
        grant = {
            "grant_id": "dl2-block-20260808",
            "decision_deadline_et": "2026-08-08T23:59:00-04:00",
            "shape_authorizations": [
                {"shape_id": "CAL-HP", "single_use": True},
                {"shape_id": "S06", "single_use": True},
                {"shape_id": "S05", "single_use": True},
            ],
        }
        now = dt.datetime.fromisoformat("2026-08-08T22:30:00-04:00")
        with self.assertRaisesRegex(HarnessRefusal, "shape_not_authorized:CAL-MIC"):
            validate_capture_window(grant, {"sessions": []}, "CAL-MIC", now)

    def test_block_grant_is_single_use_per_shape_and_grant(self) -> None:
        grant = {
            "grant_id": "dl2-block-20260808",
            "decision_deadline_et": "2026-08-08T23:59:00-04:00",
            "shape_authorizations": [
                {"shape_id": "CAL-HP", "single_use": True},
                {"shape_id": "S06", "single_use": True},
                {"shape_id": "S05", "single_use": True},
            ],
        }
        now = dt.datetime.fromisoformat("2026-08-08T22:30:00-04:00")
        prior_grant = {
            "sessions": [{"shape_id": "CAL-HP", "grant_id": "cal-hp-microphone-test-20260808"}]
        }
        self.assertEqual(
            validate_capture_window(grant, prior_grant, "CAL-HP", now),
            "GRANT_SINGLE_USE_SHAPE",
        )
        current_grant = {
            "sessions": [{"shape_id": "CAL-HP", "grant_id": "dl2-block-20260808"}]
        }
        with self.assertRaisesRegex(HarnessRefusal, "shape_already_used:CAL-HP"):
            validate_capture_window(grant, current_grant, "CAL-HP", now)

    def test_s06r_amendment_is_distinct_and_single_use(self) -> None:
        grant = {
            "grant_id": "dl2-block-20260808",
            "decision_deadline_et": "2026-08-08T23:59:00-04:00",
            "shape_authorizations": [
                {"shape_id": "S06", "single_use": True},
                {"shape_id": "S06R", "single_use": True},
            ],
        }
        now = dt.datetime.fromisoformat("2026-08-08T23:00:00-04:00")
        used_s06 = {
            "sessions": [{"shape_id": "S06", "grant_id": "dl2-block-20260808"}]
        }
        self.assertEqual(
            validate_capture_window(grant, used_s06, "S06R", now),
            "GRANT_SINGLE_USE_SHAPE",
        )
        used_s06r = {
            "sessions": [{"shape_id": "S06R", "grant_id": "dl2-block-20260808"}]
        }
        with self.assertRaisesRegex(HarnessRefusal, "shape_already_used:S06R"):
            validate_capture_window(grant, used_s06r, "S06R", now)

    def test_post_decision_retry_requires_exact_one_use_label(self) -> None:
        grant = {
            "decision_deadline_et": "2026-08-06T07:50:00-04:00",
            "raw_delete_deadline_et": "2026-08-06T23:05:00-04:00",
            "post_decision_pilot_authorization": {
                "authorized": True,
                "shape_id": "S01",
                "single_use": True,
            },
            "post_decision_retry_authorization": {
                "authorized": True,
                "shape_id": "S01",
                "attempt_label": "S01b",
                "single_use": True,
            },
        }
        now = dt.datetime.fromisoformat("2026-08-06T14:40:00-04:00")
        used = {"sessions": [{"shape_id": "S01"}]}
        self.assertEqual(
            validate_capture_window(grant, used, "S01", now, attempt_label="S01b"),
            "POST_DECISION_SINGLE_USE_RETRY",
        )
        with self.assertRaisesRegex(HarnessRefusal, "post_decision_retry_already_used:S01b"):
            validate_capture_window(
                grant,
                {"sessions": [{"shape_id": "S01"}, {"shape_id": "S01", "attempt_label": "S01b"}]},
                "S01",
                now,
                attempt_label="S01b",
            )
        with self.assertRaisesRegex(HarnessRefusal, "post_decision_capture_not_authorized:S03"):
            validate_capture_window(grant, {"sessions": []}, "S03", now)
        with self.assertRaisesRegex(HarnessRefusal, "post_decision_pilot_already_used:S01"):
            validate_capture_window(grant, {"sessions": [{"shape_id": "S01"}]}, "S01", now)
        self.assertEqual(
            validate_capture_window(
                grant,
                {"sessions": [{"shape_id": "S01", "acceptance_case": False}]},
                "S01",
                now,
            ),
            "POST_DECISION_SINGLE_USE_PILOT",
        )

    def test_grant_bounds_refuse_ttl_over_24_hours(self) -> None:
        with self.assertRaisesRegex(HarnessRefusal, "grant_bounds_refused:ttl_seconds"):
            validate_grant(
                {"ttl_seconds": 86_401, "program_cap_bytes": 2_147_483_648},
                {"captured_bytes_total": 0},
            )

    def test_grant_bounds_refuse_cap_over_2_gib(self) -> None:
        with self.assertRaisesRegex(HarnessRefusal, "grant_bounds_refused:program_cap_bytes"):
            validate_grant(
                {"ttl_seconds": 86_400, "program_cap_bytes": 2_147_483_649},
                {"captured_bytes_total": 0},
            )

    def test_program_accounting_refuses_projected_overrun(self) -> None:
        with self.assertRaisesRegex(HarnessRefusal, "program_cap_refused"):
            validate_grant(
                {"ttl_seconds": 86_400, "program_cap_bytes": 2_147_483_648},
                {"captured_bytes_total": 2_147_483_640},
                projected_bytes=9,
            )

    def test_missing_lane_is_named(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "system.pcm").write_bytes(b"\x01\x00")
            (root / "mixed.pcm").write_bytes(b"\x01\x00")
            (root / "index.json").write_text(
                json.dumps(
                    {
                        "session_id": "session-a",
                        "sample_rate": 16_000,
                        "total_bytes": 4,
                        "tracks": {
                            "system": {"sample_count": 1, "bytes": 2},
                            "mixed": {"sample_count": 1, "bytes": 2},
                        },
                    }
                )
            )
            with self.assertRaisesRegex(HarnessRefusal, "missing_lane_tape:microphone"):
                validate_tape_dir(root, "session-a")

    def test_complete_three_track_tape_passes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            tracks = {}
            for name in ("system", "microphone", "mixed"):
                (root / f"{name}.pcm").write_bytes(b"\x01\x00")
                tracks[name] = {"sample_count": 1, "bytes": 2}
            (root / "index.json").write_text(
                json.dumps(
                    {
                        "session_id": "session-a",
                        "sample_rate": 16_000,
                        "total_bytes": 6,
                        "tracks": tracks,
                    }
                )
            )
            result = validate_tape_dir(root, "session-a")
            self.assertEqual(result["total_bytes"], 6)
            self.assertEqual(sorted(result["tracks"]), ["microphone", "mixed", "system"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
