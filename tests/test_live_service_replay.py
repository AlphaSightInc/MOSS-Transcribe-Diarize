from __future__ import annotations

import unittest

from moss_transcribe_diarize import live_service_replay
from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceFailureKind,
    LiveServiceProviderConfigFailure,
)


class LiveServiceReplayContractTest(unittest.TestCase):
    def test_help_shape_parses_service_backed_flags(self):
        with self.assertRaises(SystemExit) as cm:
            live_service_replay.parse_args(["--help"])

        self.assertEqual(cm.exception.code, 0)

    def test_required_cli_flags_are_separate_from_offline_manifest_replay(self):
        args = live_service_replay.parse_args(
            [
                "--base-url",
                "http://127.0.0.1:7860",
                "--audio",
                "audio.wav",
                "--out-dir",
                "runs/live-service-replay",
                "--pace",
                "1.0",
                "--max-pacing-lag",
                "0.25",
                "--runs",
                "3",
                "--expect-revision",
                "revision",
                "--expect-provider-hash",
                "a" * 64,
                "--expect-config-hash",
                "b" * 64,
            ]
        )

        self.assertEqual(args.base_url, "http://127.0.0.1:7860")
        self.assertEqual(args.audio, "audio.wav")
        self.assertEqual(args.runs, 3)
        self.assertEqual(args.expect_provider_hash, "a" * 64)

    def test_service_failure_kinds_map_to_typed_replay_exits(self):
        error = LiveServiceProviderConfigFailure("config mismatch")

        self.assertEqual(
            live_service_replay._exit_code_for_service_failure(error.failure.kind),
            live_service_replay.ServiceReplayProviderConfigFailure.exit_code,
        )
        self.assertEqual(
            live_service_replay._exit_code_for_service_failure(LiveServiceFailureKind.TRANSPORT_PACING),
            live_service_replay.ServiceReplayTransportFailure.exit_code,
        )


if __name__ == "__main__":
    unittest.main()
