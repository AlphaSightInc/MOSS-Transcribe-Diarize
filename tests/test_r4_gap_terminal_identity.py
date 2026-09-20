"""R4-3 controls: terminal-local partition evidence must not become neighbour guessing."""
from types import SimpleNamespace
import wave

import pytest

from moss_transcribe_diarize.app.live_identity import (
    BoundedCausalIdentityPreparer,
    LiveIdentityConfig,
)
from moss_transcribe_diarize.app.live_identity_album import FingerprintAlbum
from moss_transcribe_diarize.app.live_lane_decode import finalize_lanes
from moss_transcribe_diarize.app.live_provider_bundle import WeSpeakerLiveEvidenceProvider
from moss_transcribe_diarize.app.live_session import EffectiveTranscriptSegment, LiveIdentitySnapshot
from moss_transcribe_diarize.app.live_tape import CompleteMixedTape
from moss_transcribe_diarize.app.live_transcript_convergence import (
    RollingStatus,
    TerminalDecodePlan,
    TerminalTranscriptFinalizer,
)


RATE = 16_000


class MarkerEncoder:
    spec = SimpleNamespace(provider="wespeaker", revision="test", state_sha256="test")

    def embed(self, wav_path, intervals):
        with wave.open(str(wav_path), "rb") as audio:
            audio.setpos(round(intervals[0][0] * RATE))
            marker = audio.readframes(1)[0]
        return (1.0, 0.0) if marker == 1 else (0.0, 1.0)


class SplitTerminalRunner:
    def transcribe(self, *_args, **_kwargs):
        return SimpleNamespace(
            text=(
                "[0][S01]established[2.5]"
                "[3][S02]brief return[3.27]"
                "[3.3][S02]eligible return[5.8]"
            )
        )


def terminal_result(tmp_path, *, returning_marker: int):
    speaker = "speaker-0001"
    album = FingerprintAlbum(admission_seconds=2.0)
    assert album.observe(
        canonical_speaker=speaker,
        vector=(1.0, 0.0),
        duration_sec=2.5,
        span_id=0,
    ) == "admitted"
    provider = WeSpeakerLiveEvidenceProvider(
        encoder=MarkerEncoder(),
        album=album,
        birth_min_seconds=1.0,
        min_segment_samples=8000,
    )
    preparer = BoundedCausalIdentityPreparer(
        config=LiveIdentityConfig(16, 0.35, 0.1),
        evidence_provider=provider,
    )
    tape = CompleteMixedTape(
        epoch=0,
        capacity_bytes=6 * RATE * 2,
        storage_root=tmp_path,
    )
    pcm = bytearray(6 * RATE * 2)
    pcm[: round(2.5 * RATE) * 2] = bytes([1]) * round(2.5 * RATE) * 2
    pcm[3 * RATE * 2 : round(3.27 * RATE) * 2] = (
        bytes([returning_marker]) * round(0.27 * RATE) * 2
    )
    pcm[round(3.3 * RATE) * 2 : round(5.8 * RATE) * 2] = (
        bytes([returning_marker]) * round(2.5 * RATE) * 2
    )
    assert tape.append(start_sample=0, pcm=bytes(pcm)).written
    base = (
        EffectiveTranscriptSegment(
            0, round(2.5 * RATE), "established", speaker, "rolling", "system"
        ),
    )
    snapshot = SimpleNamespace(
        identity_snapshot=LiveIdentitySnapshot(canonical_speakers=(speaker,))
    )
    coordinator = SimpleNamespace(
        lane_tapes={"system": tape},
        _lane_speakers={"system": {speaker}},
        _lane_preparers={"system": preparer},
        session=SimpleNamespace(snapshot=lambda: snapshot),
    )
    return finalize_lanes(
        coordinator,
        TerminalTranscriptFinalizer(runner=SplitTerminalRunner(), scratch_dir=tmp_path),
        plan=TerminalDecodePlan(0, 6 * RATE, 0, RollingStatus.STOPPED, 0, 0),
        tape=tape,
        base_text_revision_version=0,
        base_surface=base,
        canonical_speakers=(speaker,),
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "R4-3: per-segment terminal fallback drops a 0.27 s return even when the same "
        "terminal-local partition has eligible matching evidence"
    ),
)
def test_r4_3_same_terminal_partition_reuses_eligible_voice_evidence(tmp_path):
    result = terminal_result(tmp_path, returning_marker=1)
    assert [segment.canonical_speaker for segment in result.proposal.segments] == [
        "speaker-0001",
        "speaker-0001",
        "speaker-0001",
    ]


def test_r4_3_different_returning_voice_is_not_absorbed(tmp_path):
    result = terminal_result(tmp_path, returning_marker=2)
    assert [segment.canonical_speaker for segment in result.proposal.segments] == [
        "speaker-0001",
        None,
        None,
    ]
