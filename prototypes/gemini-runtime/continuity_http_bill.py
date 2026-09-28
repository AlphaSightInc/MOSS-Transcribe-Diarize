"""Paced public accept6 Bill HTTPS run; receipt contains identity counts, no words."""
from __future__ import annotations

import argparse
import asyncio
import json
import time
import wave
from pathlib import Path

from moss_transcribe_diarize.app.live_session import AudioFrame
from moss_transcribe_diarize.phase2_acceptance_replay import AccountCookieLiveReplayService

RATE = 16_000


def _pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as source:
        assert (source.getnchannels(), source.getsampwidth(), source.getframerate()) == (1, 2, RATE)
        return source.readframes(source.getnframes())


def _surface(snapshot: dict, truth: list[dict]) -> dict:
    session = snapshot["session"]
    rows = session["effective_transcript"]
    speakers = session["identity_snapshot"]["canonical_speakers"]
    display = {speaker: f"S{index:02d}" for index, speaker in enumerate(speakers, 1)}
    overlap: dict[str, dict[str, float]] = {}
    for row in rows:
        start, end = row["start_sample"]/RATE, row["end_sample"]/RATE
        label = display.get(row.get("canonical_speaker"), "S00")
        for ref in truth:
            seconds = max(0.0, min(end, ref["end"])-max(start, ref["start"]))
            if seconds:
                bucket = overlap.setdefault(ref["speaker"], {})
                bucket[label] = bucket.get(label, 0.0) + seconds
    return {
        "accepted_samples": session["accepted_samples"],
        "canonical_through_sample": session["canonical_through_sample"],
        "pending_work_items": snapshot["pending_work_items"],
        "status": session["status"],
        "finalization_status": session["finalization_status"],
        "turn_count": len(rows),
        "displayed_speaker_count": len({row["canonical_speaker"] for row in rows
                                        if row.get("canonical_speaker")}),
        "display_labels_at_surface": {display[speaker]: speaker for speaker in
                                      {row["canonical_speaker"] for row in rows
                                       if row.get("canonical_speaker")}},
        "unattributed_seconds": round(sum(row["end_sample"]-row["start_sample"]
                                           for row in rows if row.get("canonical_speaker") is None)/RATE, 3),
        "reference_overlap_seconds_by_display_label": {
            speaker: {label: round(value, 3) for label, value in sorted(labels.items())}
            for speaker, labels in sorted(overlap.items())},
    }


def _snapshot(service, meeting_id):
    return service._json("GET", f"/api/live/sessions/{service._quoted(meeting_id)}/snapshot")["snapshot"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--clip", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--cookie-file", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    pcm = _pcm(args.clip / "audio.wav")
    truth = [json.loads(line) for line in (args.clip / "reference.jsonl").read_text().splitlines()]
    count = len(pcm)//2
    service = AccountCookieLiveReplayService(
        base_url=args.base_url, cookie_file=args.cookie_file, timeout_seconds=300)
    receipt = {"schema": "p63-c1c3-bill-http-v1", "clip": "interview_bill_ackman_60s",
               "pace": 1.0, "audio_seconds": count/RATE,
               "capture_lanes": ["system", "microphone_digital_silence"]}
    try:
        created = service.create()
        meeting_id = created.session_id
        receipt["session_id"] = meeting_id
        started = time.monotonic()
        max_lag = 0.0
        frames = 0
        for offset in range(0, count, created.descriptor.frame_samples):
            due = started + offset/RATE
            if due > time.monotonic():
                time.sleep(due-time.monotonic())
            max_lag = max(max_lag, time.monotonic()-due)
            size = min(created.descriptor.frame_samples, count-offset)
            chunk = pcm[offset*2:(offset+size)*2]
            zero = bytes(len(chunk))
            stamp = offset*1_000_000_000//RATE
            for lane, data, silent in (("system", chunk, False),
                                        ("microphone", zero, True)):
                service.accept_lane(meeting_id,
                    service._lane_payload(AudioFrame(frames, data, size), lane=lane,
                                          timestamp_ns=stamp, silent=silent))
            frames += 1
            if frames % max(1, round(10*RATE/created.descriptor.frame_samples)) == 0:
                print(f"Bill: accepted {(offset+size)/RATE:.0f}/{count/RATE:.0f}s", flush=True)
        receipt["frame_count_per_lane"] = frames
        receipt["max_pacing_lag_seconds"] = round(max_lag, 3)
        deadline = time.monotonic()+60
        while time.monotonic() < deadline:
            settled = _snapshot(service, meeting_id)
            if settled["pending_work_items"] == 0 and settled["session"]["accepted_samples"] == count:
                break
            time.sleep(.25)
        receipt["settled"] = _surface(settled, truth)
        stopped = asyncio.run(service.stop(meeting_id, 5.0))
        receipt["at_stop"] = _surface(stopped.to_dict(), truth)
        deadline = time.monotonic()+180
        while time.monotonic() < deadline:
            final = _snapshot(service, meeting_id)
            if final["session"]["finalization_status"] != "running":
                break
            time.sleep(.5)
        receipt["final"] = _surface(final, truth)
        receipt["engine_diagnostics"] = final.get("engine_diagnostics")
    except Exception as exc:
        receipt["failure_type"] = type(exc).__name__
        raise
    finally:
        service.close()
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, indent=2)+"\n")
    if (receipt["settled"]["canonical_through_sample"] != count or
            receipt["final"]["finalization_status"] != "final"):
        raise SystemExit("Bill did not settle/finalize; inspect content-free receipt")


if __name__ == "__main__":
    main()
