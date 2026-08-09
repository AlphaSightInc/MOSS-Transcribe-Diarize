#!/usr/bin/env python3
"""Audit-packet metadata tests for DL2 post-session processing."""

from __future__ import annotations

import json
import datetime as dt
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from post_session import (
    bleed_rate_for_packet,
    raw_retention_decision,
    render_html,
    run_pipeline,
    trim_leading_silence,
)


class PostSessionAuditMetadataTests(unittest.TestCase):
    def test_fully_silent_operator_declared_track_skips_leading_silence_trim(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            session = Path(raw) / "session"
            audio = session / "audio"
            audio.mkdir(parents=True)
            (session / "session-manifest.json").write_text(
                json.dumps(
                    {
                        "state": "pulled_pending_asr",
                        "session_id": "silent-system-session",
                        "shape": {"shape_id": "CAL-MIC"},
                    }
                ),
                encoding="utf-8",
            )
            tone = struct.pack("<hh", 10_000, -10_000) * 24_000
            for track in ("system", "microphone", "mixed"):
                with wave.open(str(audio / (track + ".wav")), "wb") as writer:
                    writer.setnchannels(1)
                    writer.setsampwidth(2)
                    writer.setframerate(16_000)
                    writer.writeframes(b"\0\0" * 48_000 if track == "system" else tone)
            mock_asr = Path(raw) / "mock.json"
            mock_asr.write_text(
                json.dumps(
                    {
                        "microphone": [{"start": 0.0, "end": 1.0, "speaker": "S01", "text": "mic works"}],
                        "mixed": [{"start": 0.0, "end": 1.0, "speaker": "S01", "text": "mic works"}],
                    }
                ),
                encoding="utf-8",
            )

            run_pipeline(
                session,
                mock_asr,
                keep_raw=True,
                operator_non_speech_tracks=["system"],
            )

            provenance = json.loads((session / "derived/provenance.json").read_text())
            tracks = {item["track"]: item for item in provenance["tracks"]}
            self.assertTrue(tracks["system"]["operator_declared_non_speech"])
            self.assertEqual(tracks["system"]["segment_count"], 0)
            self.assertEqual(tracks["microphone"]["segment_count"], 1)

    def test_full_pipeline_records_and_applies_leading_silence_sample_offset(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            session = Path(raw) / "session"
            audio = session / "audio"
            audio.mkdir(parents=True)
            (session / "session-manifest.json").write_text(
                json.dumps(
                    {
                        "state": "pulled_pending_asr",
                        "session_id": "offset-session",
                        "shape": {"shape_id": "S03"},
                    }
                ),
                encoding="utf-8",
            )
            tone = struct.pack("<hh", 10_000, -10_000) * 8_000
            for track in ("system", "microphone", "mixed"):
                with wave.open(str(audio / (track + ".wav")), "wb") as writer:
                    writer.setnchannels(1)
                    writer.setsampwidth(2)
                    writer.setframerate(16_000)
                    writer.writeframes(b"\0\0" * 48_000 + tone)
            mock_asr = Path(raw) / "mock.json"
            mock_asr.write_text(
                json.dumps(
                    {
                        track: [{"start": 0.1, "end": 0.2, "speaker": "S01", "text": track}]
                        for track in ("system", "microphone", "mixed")
                    }
                ),
                encoding="utf-8",
            )
            run_pipeline(session, mock_asr, keep_raw=True)
            provenance = json.loads((session / "derived/provenance.json").read_text())
            transcript = json.loads((session / "derived/asr/microphone/asr-transcript.json").read_text())
            self.assertEqual(
                {track["sample_offset"] for track in provenance["tracks"]},
                {48_000},
            )
            self.assertEqual(transcript["segments"][0]["start"], 3.1)
            self.assertEqual(transcript["segments"][0]["end"], 3.2)

    def test_tonight_raw_retention_is_scoped_and_deadline_bounded(self) -> None:
        grant = {
            "raw_delete_deadline_et": "2026-08-06T23:05:00-04:00",
            "raw_retention_amendment": {
                "authorized": True,
                "shape_ids": ["CAL-HP", "S06", "S05"],
                "retain_until_et": "2026-08-06T23:05:00-04:00",
            },
        }
        before = dt.datetime.fromisoformat("2026-08-06T22:00:00-04:00")
        after = dt.datetime.fromisoformat("2026-08-06T23:05:00-04:00")
        self.assertTrue(raw_retention_decision(grant, {"shape": {"shape_id": "S06"}}, before)["retain"])
        self.assertFalse(raw_retention_decision(grant, {"shape": {"shape_id": "S01"}}, before)["retain"])
        self.assertFalse(raw_retention_decision(grant, {"shape": {"shape_id": "S06"}}, after)["retain"])

    def test_210s_leading_silence_is_trimmed_with_exact_sample_offset(self) -> None:
        source = Path(__file__).resolve().parent / "evidence/d3-leading-silence/fixtures/leading-210s.wav"
        control = Path(
            "/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-l2-stage0/"
            "prototypes/streaming-diarization/data/real/benchmark_diarization_1min/samples/"
            "acquired_jamie_dimon/audio.wav"
        )
        with tempfile.TemporaryDirectory() as raw:
            selected, record = trim_leading_silence(source, Path(raw) / "selected.wav")
            self.assertEqual(record["sample_rate"], 16_000)
            self.assertEqual(record["sample_offset"], 3_360_000)
            self.assertEqual(record["offset_seconds"], 210.0)
            with wave.open(str(selected), "rb") as selected_reader, wave.open(str(control), "rb") as control_reader:
                self.assertEqual(
                    selected_reader.readframes(selected_reader.getnframes()),
                    control_reader.readframes(control_reader.getnframes()),
                )

    def test_full_future_packet_emits_pending_bleed_rate(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            session = Path(raw) / "session"
            audio = session / "audio"
            audio.mkdir(parents=True)
            (session / "session-manifest.json").write_text(
                json.dumps(
                    {
                        "state": "pulled_pending_asr",
                        "session_id": "future-session",
                        "shape": {"shape_id": "S03"},
                    }
                ),
                encoding="utf-8",
            )
            for track in ("system", "microphone", "mixed"):
                with wave.open(str(audio / (track + ".wav")), "wb") as writer:
                    writer.setnchannels(1)
                    writer.setsampwidth(2)
                    writer.setframerate(16_000)
                    writer.writeframes(b"\0\0" * 160)
            mock_asr = Path(raw) / "mock.json"
            mock_asr.write_text(
                json.dumps(
                    {
                        "system": [{"start": 0.0, "end": 0.01, "speaker": "S01", "text": "a"}],
                        "microphone": [{"start": 0.0, "end": 0.01, "speaker": "S01", "text": "b"}],
                        "mixed": [{"start": 0.0, "end": 0.01, "speaker": "S01", "text": "a b"}],
                    }
                ),
                encoding="utf-8",
            )
            run_pipeline(session, mock_asr, keep_raw=True)
            rows = json.loads((session / "derived/audit-packet/audit-rows.json").read_text())
            provenance = json.loads((session / "derived/provenance.json").read_text())
            packet = (session / "derived/audit-packet/audit-rows.html").read_text()
            self.assertEqual(rows["bleed_rate"]["status"], "pending_human_audit")
            self.assertEqual(provenance["bleed_rate"], rows["bleed_rate"])
            self.assertIn("Bleed rate: pending human audit", packet)

    def test_future_packet_marks_bleed_rate_pending_until_human_audit(self) -> None:
        metric = bleed_rate_for_packet({})
        self.assertEqual(metric["status"], "pending_human_audit")
        self.assertIsNone(metric["value"])
        self.assertIn("Bleed rate: pending human audit", render_html([], "session-a", metric))

    def test_audited_bleed_rate_is_emitted(self) -> None:
        source = {
            "status": "human_audited",
            "bleeded_speech_seconds": 66.79,
            "true_local_speech_seconds": 75.27,
            "mic_speech_seconds": 142.06,
            "value": 0.47015345628607635,
            "percent_rounded_1dp": 47.0,
            "formula": "bleeded_speech_seconds / mic_speech_seconds",
        }
        metric = bleed_rate_for_packet({"bleed_rate": source})
        self.assertEqual(metric, source)
        self.assertIn("Bleed rate: 47.0%", render_html([], "session-a", metric))


if __name__ == "__main__":
    unittest.main(verbosity=2)
