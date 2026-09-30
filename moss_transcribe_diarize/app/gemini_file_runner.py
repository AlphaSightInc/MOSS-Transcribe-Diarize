"""Gemini terminal transcription through the existing File Meeting runner seam."""

from __future__ import annotations

import time
import wave
from pathlib import Path

from .file_identity_album import AlbumIdentityResolver
from .gemini_final_policy import FinalWordPolicy, WebRtcWordGate
from .gemini_lane_engine import WebRtcSpeechDetector
from .gemini_live_runtime import validate_transcription
from .gemini_long_final import LongFinalStitcher
from .gemini_provider import TerminalTranscriber
from .live_span_bounds import LIVE_SAMPLE_RATE
from .model_runner import TranscriptionResult


class _WavTape:
    """Read the prepared File PCM on the terminal transcriber's sample clock."""

    def __init__(self, path: Path):
        self.path = path
        with wave.open(str(path), "rb") as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, LIVE_SAMPLE_RATE):
                raise ValueError("Gemini File input must be 16 kHz mono PCM16 WAV")
            self.sample_count = wav.getnframes()

    def read(self, *, start_sample: int = 0, end_sample: int | None = None) -> bytes:
        end = self.sample_count if end_sample is None else end_sample
        if not 0 <= start_sample <= end <= self.sample_count:
            raise ValueError("Gemini File interval outside prepared audio")
        with wave.open(str(self.path), "rb") as wav:
            wav.setpos(start_sample)
            return wav.readframes(end - start_sample)


class GeminiFileRunner:
    """One diarized terminal pass per job; FileMeetingTasks owns outcomes and saved audio."""

    model_path = "gemini-3.5-transcribe"

    def __init__(self, diarizer_factory, encoder, *, identity_resolver=None,
                 word_gate=None, voiced_audio=None, report_usage=None):
        # diarizer_factory(transcription) builds the job's client from the request's key.
        self._diarizer_factory = diarizer_factory
        self._encoder = encoder
        self.identity_resolver = identity_resolver or AlbumIdentityResolver(encoder=encoder)
        self.live_enrollment_observation = self.identity_resolver.enrollment_observation
        self._voiced_audio = voiced_audio or WebRtcSpeechDetector()
        self._word_gate = word_gate or WebRtcWordGate()
        self._report_usage = report_usage

    @staticmethod
    def transcription_settings(value: object) -> dict[str, object]:
        """Validate the upload's provider choice before any meeting exists."""
        return validate_transcription(value)

    def transcribe(self, audio_path: str | Path, *, transcription=None,
                   **_options) -> TranscriptionResult:
        path = Path(audio_path)
        tape = _WavTape(path)
        started = time.monotonic()
        terminal = TerminalTranscriber(
            self._diarizer_factory(transcription), identity_policy=FinalWordPolicy(self._encoder),
            stitcher=LongFinalStitcher(self._encoder), word_gate=self._word_gate,
            voiced_audio=self._voiced_audio, report_usage=self._report_usage,
        )
        rows = terminal.transcribe(tape)
        speakers = tuple(dict.fromkeys(row.speaker for row in rows))
        labels = {speaker: f"S{index:02d}" for index, speaker in enumerate(speakers, 1)}
        text = "".join(
            f"[{row.start_sample / LIVE_SAMPLE_RATE:g}][{labels[row.speaker]}]"
            f"{row.text}[{row.end_sample / LIVE_SAMPLE_RATE:g}]"
            for row in rows if row.text.strip()
        )
        speechless = not rows and not self._voiced_audio(tape.read())
        return TranscriptionResult(
            text=text, prompt_len=0, generated_tokens=0,
            elapsed_sec=time.monotonic() - started,
            model=(transcription or {}).get("model") or self.model_path,
            audio=str(path), decoding="gemini", temperature=None,
            window_diagnostics=([{"condition": "speechless_window_empty"}]
                                if speechless else []),
        )
