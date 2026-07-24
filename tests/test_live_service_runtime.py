from __future__ import annotations

import dataclasses
import unittest

from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceBounds,
    LiveServiceConfigHashes,
    LiveServiceDescriptor,
    LiveServiceEvent,
    LiveServiceFailureKind,
    LiveServiceProviderConfigFailure,
    hash_config,
)
from moss_transcribe_diarize.app.live_session import LIVE_SAMPLE_RATE


def _digest(label: str) -> str:
    return hash_config({"label": label})


class LiveServiceContractTypesTest(unittest.TestCase):
    def test_descriptor_is_immutable_versioned_and_json_safe(self):
        hashes = LiveServiceConfigHashes.from_parts(
            endpoint_config={"min_speech_samples": 1600},
            identity_config={"max_speakers": 4},
            decoder_config={"max_samples": 16000},
        )
        descriptor = LiveServiceDescriptor(
            source_revision="eda5e69faf0e0251383029295f7e8875a2a1a4f6",
            provider_name="deterministic-fake",
            provider_revision="test-revision",
            provider_manifest_hash=_digest("provider"),
            config_hashes=hashes,
            bounds=LiveServiceBounds(
                max_frame_samples=LIVE_SAMPLE_RATE,
                max_queue_depth=2,
                max_retained_samples=LIVE_SAMPLE_RATE * 4,
                max_identity_speakers=4,
                max_events=32,
            ),
        )

        payload = descriptor.to_dict()

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["live_protocol_version"], "moss-live-service.v1")
        self.assertEqual(payload["sample_rate"], LIVE_SAMPLE_RATE)
        self.assertTrue(payload["feature_enabled"])
        self.assertEqual(payload["config_hashes"]["combined_config_hash"], hashes.combined_config_hash)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            descriptor.provider_name = "mutated"  # type: ignore[misc]

    def test_config_hashes_are_deterministic_and_validate_digest_shape(self):
        left = LiveServiceConfigHashes.from_parts(
            endpoint_config={"b": 2, "a": [1, 2]},
            identity_config={"speakers": 4},
            decoder_config={"rtf": 1.0},
        )
        right = LiveServiceConfigHashes.from_parts(
            endpoint_config={"a": [1, 2], "b": 2},
            identity_config={"speakers": 4},
            decoder_config={"rtf": 1.0},
        )

        self.assertEqual(left, right)
        with self.assertRaisesRegex(ValueError, "provider_manifest_hash"):
            LiveServiceDescriptor(
                source_revision="revision",
                provider_name="provider",
                provider_revision="provider-revision",
                provider_manifest_hash="not-a-digest",
                config_hashes=left,
                bounds=LiveServiceBounds(
                    max_frame_samples=1,
                    max_queue_depth=1,
                    max_retained_samples=1,
                    max_identity_speakers=1,
                    max_events=1,
                ),
                frame_samples=1,
            )

    def test_events_and_failures_are_typed_payloads(self):
        failure = LiveServiceProviderConfigFailure(
            "descriptor provider hash mismatch",
            code="descriptor_mismatch",
            detail={"expected": _digest("expected"), "actual": _digest("actual")},
        ).failure
        event = LiveServiceEvent(
            seq=0,
            session_id="session-1",
            kind="terminal_failure",
            snapshot_version=3,
            payload={"failure": failure.to_dict()},
        )

        self.assertEqual(failure.kind, LiveServiceFailureKind.PROVIDER_CONFIG)
        self.assertFalse(failure.retryable)
        self.assertEqual(event.to_dict()["payload"]["failure"]["kind"], "provider_config")


if __name__ == "__main__":
    unittest.main()
