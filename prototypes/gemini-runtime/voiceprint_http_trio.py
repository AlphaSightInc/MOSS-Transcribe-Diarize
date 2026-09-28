"""Paced public-audio D3 probe; writes only operational/identity verdict metadata.

Run with SSL_CERT_FILE pointing at the local stack certificate and an Account cookie
file (0600) as arguments. The three source clips are sent through the HTTPS API.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import wave
from pathlib import Path

from moss_transcribe_diarize.app.live_session import AudioFrame
from moss_transcribe_diarize.phase2_acceptance_replay import AccountCookieLiveReplayService


CLIPS = (
    ("interview_bill_ackman_60s", "Lex Fridman"),
    ("interview_keyu_jin_60s", "Lex Fridman"),
    ("discussion_jamie_dimon_180s", None),
)
RATE = 16_000


def _pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as source:
        assert (source.getnchannels(), source.getsampwidth(), source.getframerate()) == (1, 2, RATE)
        return source.readframes(source.getnframes())


def _references(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def _attribution(snapshot: dict, references: list[dict]) -> dict[str, dict[str, float]]:
    rows = snapshot["session"]["effective_transcript"]
    scores: dict[str, dict[str, float]] = {}
    for row in rows:
        speaker = row.get("canonical_speaker")
        if speaker is None:
            continue
        a, b = row["start_sample"] / RATE, row["end_sample"] / RATE
        for reference in references:
            overlap = max(0.0, min(b, reference["end"]) - max(a, reference["start"]))
            if overlap:
                bucket = scores.setdefault(reference["speaker"], {})
                bucket[speaker] = bucket.get(speaker, 0.0) + overlap
    return scores


def _best(scores: dict[str, dict[str, float]], label: str) -> tuple[str | None, float]:
    candidates = scores.get(label, {})
    return max(candidates.items(), key=lambda item: item[1]) if candidates else (None, 0.0)


def _envelope(service: AccountCookieLiveReplayService, meeting_id: str) -> dict:
    return service._json("GET", f"/api/live/sessions/{service._quoted(meeting_id)}/snapshot")


def _raw(service: AccountCookieLiveReplayService, meeting_id: str) -> dict:
    return _envelope(service, meeting_id)["snapshot"]


def _settle(service: AccountCookieLiveReplayService, meeting_id: str, sample_count: int) -> dict:
    end = time.monotonic() + 60
    while time.monotonic() < end:
        snapshot = _raw(service, meeting_id)
        if (snapshot["pending_work_items"] == 0 and
                snapshot["session"]["accepted_samples"] == sample_count):
            return snapshot
        time.sleep(.25)
    return snapshot


def _run_clip(service: AccountCookieLiveReplayService, corpus: Path, name: str,
              index: int) -> dict:
    clip = corpus / name
    pcm = _pcm(clip / "audio.wav")
    references = _references(clip / "reference.jsonl")
    sample_count = len(pcm) // 2
    created = service.create()
    meeting_id = created.session_id
    frame_samples = created.descriptor.frame_samples
    started = time.monotonic()
    offset = sequence = 0
    max_lag = 0.0
    while offset < sample_count:
        scheduled = started + offset / RATE
        if scheduled > time.monotonic():
            time.sleep(scheduled - time.monotonic())
        max_lag = max(max_lag, time.monotonic() - scheduled)
        count = min(frame_samples, sample_count - offset)
        service.accept_frame(meeting_id, AudioFrame(sequence, pcm[offset*2:(offset+count)*2], count))
        offset += count
        sequence += 1
        if sequence % max(1, round(10 * RATE / frame_samples)) == 0:
            print(f"{name}: accepted {offset/RATE:.0f}/{sample_count/RATE:.0f}s", flush=True)
    snapshot = _settle(service, meeting_id, sample_count)
    scores = _attribution(snapshot, references)
    lex_id, lex_overlap = _best(scores, "Lex Fridman")
    other_label = "Bill Ackman" if index == 0 else "Keyu Jin" if index == 1 else None
    other_id, other_overlap = _best(scores, other_label) if other_label else (None, 0.0)
    naming = None
    if index == 0 and lex_id is not None:
        naming = service._json("PUT", f"/api/meetings/{service._quoted(meeting_id)}/speakers/{service._quoted(lex_id)}/name",
                               {"label": "Lex Fridman"})
        # A pending enrollment can complete when a later observation arrives.
        bank_end = time.monotonic() + 15
        while time.monotonic() < bank_end:
            bank = service._json("GET", "/api/voiceprints")["voiceprints"]
            if any(row["label"] == "Lex Fridman" for row in bank):
                break
            time.sleep(.25)
    else:
        bank = service._json("GET", "/api/voiceprints")["voiceprints"]
    labels = _envelope(service, meeting_id).get("speaker_labels", {})
    settled = snapshot["session"]
    row = {
        "clip": name, "session_id": meeting_id, "audio_seconds": sample_count / RATE,
        "frame_count": sequence, "pace": 1.0, "max_pacing_lag_seconds": round(max_lag, 3),
        "settled_pending_work_items": snapshot["pending_work_items"],
        "settled_accepted_samples": settled["accepted_samples"],
        "settled_canonical_through_sample": settled["canonical_through_sample"],
        "lex_reference_overlap_seconds": round(lex_overlap, 3),
        "other_reference_overlap_seconds": round(other_overlap, 3),
        "lex_identity_found": lex_id is not None,
        "other_identity_found": other_id is not None if other_label else None,
        "visible_speaker_count": len({item["canonical_speaker"] for item in
                                      snapshot["session"]["effective_transcript"]
                                      if item.get("canonical_speaker")}),
        "lex_auto_named": labels.get(lex_id) == "Lex Fridman" if lex_id else False,
        "other_auto_named_lex": labels.get(other_id) == "Lex Fridman" if other_id else False,
        "any_lex_name": "Lex Fridman" in labels.values(),
        "voiceprint_bank_lex_count": sum(value["label"] == "Lex Fridman" for value in bank),
        "naming_enrollment": naming.get("enrollment") if naming else None,
        "engine_diagnostics": snapshot.get("engine_diagnostics"),
    }
    final = asyncio.run(service.stop(meeting_id, deadline=5.0))
    row["stop_status"] = final.session.status
    row["finalization_status"] = final.session.finalization_status
    row["final_accepted_samples"] = final.session.accepted_samples
    row["settled_engine_diagnostics"] = row.pop("engine_diagnostics")
    row["engine_diagnostics"] = _raw(service, meeting_id).get("engine_diagnostics")
    return row


def _verdict(runs: list[dict]) -> bool:
    a, b, c = runs
    return bool(a["naming_enrollment"] == "enrolled" and a["voiceprint_bank_lex_count"] == 1
                and b["lex_auto_named"] and not b["other_auto_named_lex"]
                and not c["any_lex_name"])


def _audit_existing(service: AccountCookieLiveReplayService, corpus: Path, receipt: dict) -> None:
    """Re-read public HTTPS envelopes after a probe field-location correction."""
    for index, row in enumerate(receipt["runs"]):
        envelope = _envelope(service, row["session_id"])
        scores = _attribution(envelope["snapshot"],
                              _references(corpus / row["clip"] / "reference.jsonl"))
        lex_id, _ = _best(scores, "Lex Fridman")
        other_label = "Bill Ackman" if index == 0 else "Keyu Jin" if index == 1 else None
        other_id, _ = _best(scores, other_label) if other_label else (None, 0.0)
        labels = envelope.get("speaker_labels", {})
        row["visible_speaker_count"] = len({item["canonical_speaker"] for item in
                                             envelope["snapshot"]["session"]["effective_transcript"]
                                             if item.get("canonical_speaker")})
        row["lex_auto_named"] = labels.get(lex_id) == "Lex Fridman" if lex_id else False
        row["other_auto_named_lex"] = labels.get(other_id) == "Lex Fridman" if other_id else False
        row["any_lex_name"] = "Lex Fridman" in labels.values()
        row["speaker_label_count"] = len(labels)
        if "settled_engine_diagnostics" not in row:
            row["settled_engine_diagnostics"] = row.pop("engine_diagnostics")
        row["engine_diagnostics"] = envelope["snapshot"].get("engine_diagnostics")
    receipt["label_source"] = "https_snapshot_outer_envelope"
    receipt["probe_correction"] = "initial pass read speaker_labels inside snapshot; audited the public outer envelope after Stop"
    receipt["verdict"] = _verdict(receipt["runs"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--cookie-file", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--audit-existing", action="store_true")
    args = parser.parse_args()
    service = AccountCookieLiveReplayService(base_url=args.base_url, cookie_file=args.cookie_file,
                                             timeout_seconds=300)
    receipt = {"schema": "p63-d3-real-http-trio-v1", "engine": "gemini", "runs": []}
    try:
        if args.audit_existing:
            receipt = json.loads(args.receipt.read_text())
            _audit_existing(service, args.corpus, receipt)
        else:
            for index, (name, _) in enumerate(CLIPS):
                row = _run_clip(service, args.corpus, name, index)
                receipt["runs"].append(row)
                args.receipt.parent.mkdir(parents=True, exist_ok=True)
                args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
                print(f"{name}: lex_found={row['lex_identity_found']} lex_named={row['lex_auto_named']} bank={row['voiceprint_bank_lex_count']}", flush=True)
    finally:
        service.close()
    receipt["verdict"] = _verdict(receipt["runs"])
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    if not receipt["verdict"]:
        raise SystemExit("D3 cross-meeting voiceprint acceptance failed; inspect content-free receipt")


if __name__ == "__main__":
    main()
