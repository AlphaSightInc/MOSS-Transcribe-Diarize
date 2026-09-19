"""Bounded decoder probe for native WAV/MP3 local-label behavior; see NOTES.md."""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from moss_transcribe_diarize.app.vllm_runner import VllmRunner
from moss_transcribe_diarize.app.windowed_transcription import extract_window_wav
from moss_transcribe_diarize.transcript_parser import parse_transcript

ROOT = Path(__file__).resolve().parents[3]
RUNTIME = Path("/private/tmp/moss-independent-assessment-20260918/.wp25runtime/20260919T033906530769Z")
CORPUS = ROOT / "evidence/live-policy-sweep-20260825/corpus"
REQUEST_LOG = Path("/Users/gao/Documents/Codex/2026-09-19/moss-round2/decoder-requests.jsonl")


def sent_count() -> int:
    count = 0
    for line in REQUEST_LOG.read_text().splitlines():
        row = json.loads(line)
        if row.get("kind") == "start":
            count = max(count, int(row["sent"]))
    return count


def transcode_mp3(source: Path, destination: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(source), "-codec:a", "libmp3lame", "-q:a", "2", str(destination)],
        check=True,
        capture_output=True,
        text=True,
    )


def cases(scratch: Path) -> list[tuple[str, Path, float, float]]:
    long_wav = RUNTIME / "files/media/long.wav"
    long_mp3 = RUNTIME / "files/media/long.mp3"
    rows: list[tuple[str, Path, float, float]] = []
    for start in (0.0, 120.0, 240.0):
        rows.extend(
            ((f"composite-wav-{int(start)}", long_wav, start, 150.0),
             (f"composite-mp3-{int(start)}", long_mp3, start, 150.0))
        )
    for name in ("interview_bill_ackman_60s", "interview_keyu_jin_60s"):
        wav = CORPUS / name / "audio.wav"
        mp3 = scratch / f"{name}.mp3"
        transcode_mp3(wav, mp3)
        rows.extend(((f"{name}-wav", wav, 0.0, 60.0), (f"{name}-mp3", mp3, 0.0, 60.0)))
    rows.append((
        "discussion_jamie_dimon-context",
        CORPUS / "discussion_jamie_dimon_180s" / "audio.wav",
        30.0,
        150.0,
    ))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    before = sent_count()
    if before >= 269:
        raise RuntimeError(f"decoder lease exhausted before run: sent={before}")
    runner = VllmRunner(
        base_url=args.endpoint,
        model="OpenMOSS-Team/MOSS-Transcribe-Diarize",
        timeout=600.0,
    )
    results = []
    with tempfile.TemporaryDirectory(prefix="identity-paired-codec-") as directory:
        scratch = Path(directory)
        planned = cases(scratch)
        if before + len(planned) > 269:
            raise RuntimeError(f"decoder lease insufficient: sent={before}, planned={len(planned)}")
        for index, (name, source, start, duration) in enumerate(planned):
            window = scratch / f"window-{index:02d}.wav"
            extract_window_wav(source, window, start_seconds=start, duration_seconds=duration)
            result = runner.transcribe(window, max_new_tokens=12000, decoding="greedy")
            segments = parse_transcript(result.text)
            results.append({
                "case": name,
                "source": str(source),
                "source_start": start,
                "duration": duration,
                "generated_tokens": result.generated_tokens,
                "elapsed_sec": round(result.elapsed_sec, 6),
                "segments": [
                    {"start": item.start, "end": item.end, "speaker": item.speaker, "text": item.text}
                    for item in segments
                ],
            })
    after = sent_count()
    payload = {"sent_before": before, "sent_after": after, "requests": after - before, "cases": results}
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"sent_before": before, "sent_after": after, "requests": after - before,
                      "segments": {item["case"]: len(item["segments"]) for item in results}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
