"""Reproduce Stop request timeout versus accepted voiced tail on the runtime path."""

import asyncio
import hashlib
import json
import tempfile

from moss_transcribe_diarize.app.gemini_live_runtime import (
    GeminiBase, GeminiLiveRuntime, GeminiRolling, GeminiSegment, LiveServiceStopPending,
)
from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceBounds, LiveServiceConfigHashes, LiveServiceDescriptor,
)
from moss_transcribe_diarize.app.live_session import AudioFrame


def descriptor():
    return LiveServiceDescriptor(
        source_revision="probe", provider_name="gemini", provider_revision="fake",
        provider_manifest_hash=hashlib.sha256(b"fake").hexdigest(),
        config_hashes=LiveServiceConfigHashes.from_parts(
            endpoint_config={}, identity_config={}, decoder_config={}),
        bounds=LiveServiceBounds(max_frame_samples=16000, max_queue_depth=4,
            max_retained_samples=32000, max_identity_speakers=8, max_events=64,
            max_tape_bytes=64000), frame_samples=16000)


def frame(sequence):
    return AudioFrame(sequence, bytes(32000), 16000)


class LateTail:
    def __init__(self, publish):
        self.publish = publish

    def push_audio(self, start, pcm):
        if start == 0:
            self.publish(GeminiBase(16000, ()))
            self.publish(GeminiRolling(0, 16000,
                (GeminiSegment(0, 8000, "first", "speaker-0001"),)))

    async def drain_tail(self, deadline):
        await asyncio.sleep(.05)
        self.publish(GeminiBase(32000, ()))
        self.publish(GeminiRolling(16000, 32000,
            (GeminiSegment(16000, 24000, "tail", "speaker-0001"),)))
        return True

    async def finish(self, tape):
        return ()


async def main():
    with tempfile.TemporaryDirectory() as scratch:
        rt = GeminiLiveRuntime(descriptor=descriptor(), tape_storage_root=scratch,
            engine_factory=lambda _id, publish, _usage: LateTail(publish))
        rt.create(session_id="one")
        rt.accept_frame("one", frame(0))
        rt.accept_frame("one", frame(1))
        pending = False
        try:
            await rt.stop("one", .01)
        except LiveServiceStopPending:
            pending = True
        snap = (await rt.stop("one", 1.0)).session
        print(json.dumps({"pending": pending, "accepted_samples": snap.accepted_samples,
            "committed_samples": snap.committed_samples,
            "finalization_status": snap.finalization_status,
            "rows": [(row.text, row.start_sample, row.end_sample,
                      row.canonical_speaker) for row in snap.effective_transcript]},
            sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
