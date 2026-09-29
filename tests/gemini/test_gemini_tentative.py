from __future__ import annotations

import threading

from moss_transcribe_diarize.app.gemini_tentative import GeminiTentativeLabeler
from moss_transcribe_diarize.app.live_provider_bundle import LiveSpeakerJournalObservation


RATE = 16000


class Encoder:
    def __init__(self, vector=(1.0, 0.0)):
        self.vector = vector
        self.calls = 0
        self.entered = threading.Event()
        self.release = threading.Event()
        self.release.set()

    def embed(self, path, intervals):
        self.calls += 1
        self.entered.set()
        self.release.wait(2)
        return self.vector


def observation(speaker, vector, seconds=2.0):
    return LiveSpeakerJournalObservation(
        speaker_label=speaker, centroid=vector, sample_seconds=seconds,
        exemplar_count=1, provisional=False, embedder_id="test", embedder_state_sha="a" * 64,
    )


def test_voiced_snippet_names_only_a_settled_speaker():
    encoder = Encoder()
    labeler = GeminiTentativeLabeler(encoder, voiced_audio=lambda _pcm: True)
    labeler.observe((observation("speaker-0001", (1.0, 0.0)),))
    labeler.accept_audio("system", 0, b"\x01\x00" * RATE)
    assert labeler.wait_idle(2)
    assert labeler.spans("system", 0, RATE) == (
        {"start_sample": RATE // 2, "end_sample": RATE,
         "source_lane": "system", "speaker": "speaker-0001"},
    )
    assert encoder.calls == 1
    labeler.close()


def test_low_cosine_abstains_and_short_observation_does_not_seed():
    encoder = Encoder((0.0, 1.0))
    labeler = GeminiTentativeLabeler(encoder, voiced_audio=lambda _pcm: True)
    labeler.observe((observation("speaker-short", (0.0, 1.0), 1.5),
                     observation("speaker-known", (1.0, 0.0))))
    labeler.accept_audio("system", 0, b"\x01\x00" * RATE)
    assert labeler.wait_idle(2)
    assert labeler.spans("system", 0, RATE) == ()
    assert labeler.diagnostics()["tentative_abstained_s"] == .5
    labeler.close()


def test_busy_tick_is_skipped_instead_of_queued():
    encoder = Encoder()
    encoder.release.clear()
    labeler = GeminiTentativeLabeler(encoder, voiced_audio=lambda _pcm: True)
    labeler.observe((observation("speaker-0001", (1.0, 0.0)),))
    labeler.accept_audio("system", 0, b"\x01\x00" * RATE)
    assert encoder.entered.wait(1)
    labeler.accept_audio("system", RATE, b"\x01\x00" * (RATE // 2))
    assert labeler.diagnostics()["tentative_busy_ticks"] == 1
    encoder.release.set()
    assert labeler.wait_idle(2)
    assert encoder.calls == 1
    labeler.close()


def test_tentative_spans_are_snapshot_only_and_outside_durable_document():
    from dataclasses import asdict
    from types import SimpleNamespace
    from moss_transcribe_diarize.app.live_session import AudioFrame, LiveSession
    from moss_transcribe_diarize.app.phase2_live import _transcript_document

    session = LiveSession(max_retained_samples=RATE)
    session.accept_frame(AudioFrame(0, b"\x00\x00" * RATE, RATE))
    epoch, generation, start = session.begin_provisional()
    spans = ({"start_sample": 8000, "end_sample": RATE,
              "source_lane": "system", "speaker": "speaker-0001"},)
    segments = ({"start_sample": 8000, "end_sample": RATE, "text": "hello",
                 "source_lane": "system", "tentative_speaker": "speaker-0001"},)
    assert session.publish_provisional(epoch=epoch, generation=generation,
        start_sample=start, end_sample=RATE, transcript="[0][S00]hello[1]",
        tentative_spans=spans, segments=segments)
    snapshot = session.snapshot()
    assert asdict(snapshot.provisional)["tentative_spans"] == spans
    assert asdict(snapshot.provisional)["segments"] == segments
    document = _transcript_document(SimpleNamespace(
        session=snapshot, descriptor=SimpleNamespace(sample_rate=RATE)))
    assert "tentative" not in str(document)
    assert "speaker-0001" not in str(document)


def test_one_lane_cannot_guess_from_the_other_lanes_centroids():
    encoder = Encoder()
    labeler = GeminiTentativeLabeler(encoder, voiced_audio=lambda _pcm: True)
    labeler.observe((observation("speaker-remote", (1.0, 0.0)),), lane="system")
    labeler.accept_audio("microphone", 0, b"\x01\x00" * RATE)
    assert labeler.spans("microphone", 0, RATE) == ()
    assert encoder.calls == 0
    labeler.close()


def test_embed_failure_abstains_without_raising_into_audio_ingress():
    class FailingEncoder:
        def embed(self, path, intervals):
            raise RuntimeError("encoder failure")

    labeler = GeminiTentativeLabeler(FailingEncoder(), voiced_audio=lambda _pcm: True)
    labeler.observe((observation("speaker-0001", (1.0, 0.0)),), lane="microphone")
    labeler.accept_audio("microphone", 0, b"\x01\x00" * RATE)
    assert not labeler.wait_idle(2)  # The worker failed; ingress and callbacks stayed alive.
    assert labeler.spans("microphone", 0, RATE) == ()
    assert labeler.diagnostics()["tentative_abstained_s"] == .5
    labeler.close()
