import wave
from types import SimpleNamespace

from moss_transcribe_diarize.app.gemini_provider import GeminiWord, GeminiWords
from moss_transcribe_diarize.subtitle import subtitle_segments_from_transcript


class FakeDiarizer:
    def __init__(self, words):
        self.words = words
        self.calls = 0

    def diarize(self, pcm16, *, deadline, kind, diarize=True):
        self.calls += 1
        assert kind == "terminal" and diarize
        return GeminiWords(tuple(self.words))


class FakeEncoder:
    spec = SimpleNamespace(provider="wespeaker", revision="pinned", state_sha256="ab" * 32)

    def embed_intervals(self, path, intervals):
        return [(1.0, 0.0) for _ in intervals]


class PassthroughGate:
    def filter(self, pcm16, words):
        return words


def wav_file(path, seconds=4):
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(bytes(32000 * seconds))
    return path


def test_file_runner_emits_stable_parseable_speaker_tokens(tmp_path):
    from moss_transcribe_diarize.app.gemini_file_runner import GeminiFileRunner

    diarizer = FakeDiarizer([
        GeminiWord("hello", "spk:1", 0, 16000),
        GeminiWord("there", "spk:1", 16000, 32000),
        GeminiWord("reply", "spk:2", 32000, 48000),
    ])
    runner = GeminiFileRunner(diarizer, FakeEncoder(), word_gate=PassthroughGate(),
                              voiced_audio=lambda _pcm: True)
    result = runner.transcribe(wav_file(tmp_path / "input.wav"), prompt="ignored")
    rows = subtitle_segments_from_transcript(result.text, postprocess=False)
    assert [(row.speaker, row.text) for row in rows] == [
        ("S01", "hello there"), ("S02", "reply")]
    assert result.window_diagnostics == []
    assert diarizer.calls == 1


def test_file_runner_marks_speechless_audio_without_calling_provider(tmp_path):
    from moss_transcribe_diarize.app.gemini_file_runner import GeminiFileRunner

    diarizer = FakeDiarizer(())
    result = GeminiFileRunner(diarizer, FakeEncoder()).transcribe(wav_file(tmp_path / "silent.wav"))
    assert result.text == ""
    assert result.window_diagnostics[0]["condition"] == "speechless_window_empty"
    assert diarizer.calls == 0

