import asyncio
from types import SimpleNamespace

from moss_transcribe_diarize.app.gemini_live_runtime import (
    GeminiBase, GeminiLiveRuntime, GeminiRolling, GeminiSegment, ScriptedGeminiEngine,
)
from moss_transcribe_diarize.app.live_session import AudioFrame
from moss_transcribe_diarize.app.phase2_speaker_identity import AccountSpeakerIdentity
from tests.gemini.test_gemini_live_runtime import descriptor
from tests.phase2.test_manual_speaker_voiceprints import FakeActiveMeetings, active_meeting, provision


class FakeEncoder:
    spec = SimpleNamespace(provider="wespeaker", revision="test-revision",
                           state_sha256="ab"*32, embedding_dimension=2)
    def embed(self, wav_path, intervals):
        assert intervals[0][1] >= 2
        return [0.6, 0.8]


def observed_runtime(tmp_path, session_id):
    row = GeminiSegment(0, 3*16000, "hello world", "speaker-0001")
    rt = GeminiLiveRuntime(descriptor=descriptor(tape_bytes=3*32000),
        tape_storage_root=tmp_path,
        voiceprint_encoder=FakeEncoder(),
        engine_factory=lambda _id, publish, _usage: ScriptedGeminiEngine(
            publish, batches=[(GeminiBase(3*16000, ()), GeminiRolling(0, 3*16000, (row,)))],
            terminal=(row,)))
    rt.create(session_id=session_id)
    rt.accept_frame(session_id, AudioFrame(sequence=0, pcm=bytes(3*32000), sample_count=3*16000))
    return rt


def test_gemini_observation_enrolls_and_second_meeting_matches(tmp_path):
    async def run():
        store, workspace, _ = await provision(tmp_path / "identity.sqlite")
        active = FakeActiveMeetings()
        identity = AccountSpeakerIdentity(store, active)
        try:
            first, first_active = await active_meeting(workspace, active)
            rt1 = observed_runtime(tmp_path, first.meeting_id)
            observation = rt1._identity_observations(first.meeting_id)
            assert len(observation) == 1
            assert observation[0].sample_seconds == 3
            assert observation[0].embedder_id == "wespeaker:test-revision"
            first_active.observations["speaker-0001"] = observation[0]
            named = await identity.bank(workspace).name_speaker(first, "speaker-0001", "Alex")
            assert named.enrollment == "enrolled"
            second, _ = await active_meeting(workspace, active)
            rt2 = observed_runtime(tmp_path, second.meeting_id)
            prepared = await identity.prepare_matches(second, rt2._identity_match_observations(second.meeting_id))
            async with identity.publication(second, (), prepared=prepared) as changes:
                assert changes == {"speaker-0001": "Alex"}
            active.runtime = rt2
            listed = await identity.bank(workspace).list_voiceprints()
            assert len(listed) == 1 and listed[0].compatibility == "compatible"
        finally:
            await store.close()
    asyncio.run(run())
