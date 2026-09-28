"""Paced two-lane public E1/M2 HTTPS probe with content-free output."""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
import wave
from pathlib import Path

from moss_transcribe_diarize.app.live_session import AudioFrame
from moss_transcribe_diarize.phase2_acceptance_replay import AccountCookieLiveReplayService

RATE = 16_000
OPERATORS = ((30.0, "they think that they're responsible for you"),
             (135.0, "deference to authority is not blind submission"),
             (248.0, "in exchange for some deference"))


def _pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as source:
        assert (source.getnchannels(), source.getsampwidth(), source.getframerate()) == (1, 2, RATE)
        return source.readframes(source.getnframes())


def _words(value: str) -> list[str]:
    return re.findall(r"[^\W_]+(?:'[^\W_]+)?", value.lower(), flags=re.UNICODE)


def _lcs(a: list[str], b: list[str]) -> int:
    prior = [0] * (len(b)+1)
    for x in a:
        current = [0]
        for i, y in enumerate(b, 1):
            current.append(prior[i-1]+1 if x == y else max(current[-1], prior[i]))
        prior = current
    return prior[-1]


def _surface_counts(snapshot: dict) -> dict:
    rows = snapshot["session"]["effective_transcript"]
    mic = [row for row in rows if row.get("source_lane") == "microphone"]
    system = [row for row in rows if row.get("source_lane") == "system"]
    outside = 0
    for row in mic:
        middle = (row["start_sample"]+row["end_sample"]) / (2*RATE)
        if not any(at <= middle <= at+3 for at, _ in OPERATORS):
            outside += len(_words(row["text"]))
    recall = []
    for at, phrase in OPERATORS:
        candidate = []
        for row in mic:
            middle = (row["start_sample"]+row["end_sample"]) / (2*RATE)
            if at-.2 <= middle <= at+3.2:
                candidate.extend(_words(row["text"]))
        target = _words(phrase)
        recall.append({"matched": _lcs(target, candidate), "reference_words": len(target)})
    mic_words = sum(len(_words(row["text"])) for row in mic)
    return {
        "system_turn_count": len(system), "microphone_turn_count": len(mic),
        "system_speaker_count": len({row["canonical_speaker"] for row in system
                                     if row.get("canonical_speaker")}),
        "microphone_speaker_count": len({row["canonical_speaker"] for row in mic
                                         if row.get("canonical_speaker")}),
        "mic_words": mic_words, "mic_words_outside_operator_intervals": outside,
        "mic_stray_rate": outside/mic_words if mic_words else None,
        "operator_recall": recall,
    }


def _envelope(service, meeting_id):
    return service._json("GET", f"/api/live/sessions/{service._quoted(meeting_id)}/snapshot")


def _settle(service, meeting_id, expected):
    until = time.monotonic()+90
    while time.monotonic() < until:
        envelope = _envelope(service, meeting_id)
        snapshot = envelope["snapshot"]
        if (snapshot["pending_work_items"] == 0 and
                snapshot["session"]["accepted_samples"] == expected):
            return envelope
        time.sleep(.25)
    return envelope


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-root", type=Path, required=True)
    parser.add_argument("--case", choices=("E1", "M2"), required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--cookie-file", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    system = _pcm(args.fixture_root / "system.wav")
    mic = _pcm(args.fixture_root / f"{args.case}-microphone.wav")
    assert len(system) == len(mic)
    service = AccountCookieLiveReplayService(
        base_url=args.base_url, cookie_file=args.cookie_file, timeout_seconds=300)
    receipt = {"schema": "p63-l3-real-http-v1", "case": args.case,
               "pace": 1.0, "source_seconds": len(system)/(2*RATE)}
    meeting_id = None
    try:
        created = service.create()
        meeting_id = created.session_id
        receipt["session_id"] = meeting_id
        frame_samples = created.descriptor.frame_samples
        sample_count = len(system)//2
        started = time.monotonic()
        maximum_lag = 0.0
        frames = 0
        for offset in range(0, sample_count, frame_samples):
            scheduled = started + offset/RATE
            if scheduled > time.monotonic():
                time.sleep(scheduled-time.monotonic())
            maximum_lag = max(maximum_lag, time.monotonic()-scheduled)
            count = min(frame_samples, sample_count-offset)
            stamp = offset * 1_000_000_000 // RATE
            for lane, pcm in (("system", system), ("microphone", mic)):
                chunk = pcm[offset*2:(offset+count)*2]
                payload = service._lane_payload(AudioFrame(frames, chunk, count),
                                                lane=lane, timestamp_ns=stamp,
                                                silent=not any(chunk))
                service.accept_lane(meeting_id, payload)
            frames += 1
            if frames % max(1, round(10*RATE/frame_samples)) == 0:
                print(f"{args.case}: accepted {offset/RATE+count/RATE:.0f}/{sample_count/RATE:.0f}s", flush=True)
        receipt["frame_count_per_lane"] = frames
        receipt["max_pacing_lag_seconds"] = round(maximum_lag, 3)
        settled = _settle(service, meeting_id, sample_count)
        receipt["settled"] = {
            "accepted_samples": settled["snapshot"]["session"]["accepted_samples"],
            "canonical_through_sample": settled["snapshot"]["session"]["canonical_through_sample"],
            "pending_work_items": settled["snapshot"]["pending_work_items"],
            **_surface_counts(settled["snapshot"]),
        }
        at_stop = asyncio.run(service.stop(meeting_id, 5.0))
        receipt["at_stop"] = {"status": at_stop.session.status,
                               "finalization_status": at_stop.session.finalization_status,
                               "speaker_count": len(at_stop.session.identity_snapshot.canonical_speakers),
                               **_surface_counts(at_stop.to_dict())}
        final_end = time.monotonic()+180
        while time.monotonic() < final_end:
            final = _envelope(service, meeting_id)["snapshot"]
            if final["session"]["finalization_status"] != "running":
                break
            time.sleep(.5)
        receipt["final"] = {"status": final["session"]["status"],
                            "finalization_status": final["session"]["finalization_status"],
                            **_surface_counts(final)}
        receipt["engine_diagnostics"] = final.get("engine_diagnostics")
    except Exception as exc:
        receipt["failure_type"] = type(exc).__name__
        raise
    finally:
        service.close()
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, indent=2)+"\n")
    if (receipt["settled"]["canonical_through_sample"] != len(system)//2 or
            receipt["final"]["finalization_status"] != "final"):
        raise SystemExit("L3 fixture did not settle/finalize; inspect content-free receipt")


if __name__ == "__main__":
    main()
