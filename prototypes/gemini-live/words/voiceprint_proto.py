"""P52 D3 live voiceprint probe.

One command per case, same isolated stack/state:
 PYTHONDONTWRITEBYTECODE=1 <WT>.venv/bin/python prototypes/gemini-live/words/voiceprint_proto.py \
   --case A|B|D|E --state /tmp/p52-voiceprint.<id> --out <P52-evidence-dir>

Question: can a manual live name create a reusable voiceprint without false cross-meeting names?
Hypothesis: A enrolls Lex; B/D auto-name Lex, D auto-names enrolled Keyu, C remains unnamed.
Falsifier: missing enrollment/auto-name, wrong speaker label, or ambiguous speaker identity.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import ssl
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "prototypes/gemini-live/common"))
from corpus import clips
from moss_transcribe_diarize.app.live_session import AudioFrame, LIVE_SAMPLE_RATE
from moss_transcribe_diarize.phase2_acceptance_replay import AccountCookieLiveReplayService

CASES = {
    "A": ("interview_bill_ackman_60s", "Lex Fridman", 50.0),
    "B": ("interview_keyu_jin_60s", "Keyu Jin", 45.0),
    "D": ("benchmark_5m:lex_keyu_jin", None, None),
    "E": ("benchmark_5m:lex_bill_ackman", None, None),
}


def overlap(a, b, c, d):
    return max(0.0, min(b, d) - max(a, c))


def speaker_scores(snapshot, reference):
    session = snapshot.get("session") or {}
    rows = session.get("effective_transcript") or []
    scores = {}
    for row in rows:
        speaker = row.get("canonical_speaker")
        if speaker is None:
            continue
        s = row["start_sample"] / LIVE_SAMPLE_RATE
        e = row["end_sample"] / LIVE_SAMPLE_RATE
        counts = scores.setdefault(speaker, {})
        for ref in reference:
            sec = overlap(s, e, ref["start"], ref["end"])
            if sec:
                counts[ref["speaker"]] = counts.get(ref["speaker"], 0.0) + sec
    return scores


def select_speaker(scores, target):
    ranked = []
    for sid, counts in scores.items():
        target_sec = counts.get(target, 0.0)
        total = sum(counts.values())
        purity = target_sec / total if total else 0.0
        ranked.append((target_sec, purity, sid))
    ranked.sort(reverse=True)
    if not ranked:
        return None
    sec, purity, sid = ranked[0]
    if sec < 2.0 or purity < 0.60:
        return None
    if len(ranked) > 1 and ranked[1][0] >= sec * .85:
        return None
    return sid


def view(envelope, elapsed, sent, reference):
    snapshot = envelope["snapshot"]
    session = snapshot.get("session") or {}
    rows = session.get("effective_transcript") or []
    return {
        "wall_seconds": round(elapsed, 3), "sent_audio_seconds": round(sent, 3),
        "status": session.get("status"), "finalization_status": session.get("finalization_status"),
        "version": session.get("version"), "speaker_labels": envelope.get("speaker_labels", {}),
        "canonical_speakers": (session.get("identity_snapshot") or {}).get("canonical_speakers"),
        "speaker_scores_reference_seconds": speaker_scores(snapshot, reference),
        "segment_count": len(rows),
        "segments": [{"start": round(r["start_sample"] / LIVE_SAMPLE_RATE, 2),
                      "end": round(r["end_sample"] / LIVE_SAMPLE_RATE, 2),
                      "speaker": r.get("canonical_speaker"), "text": r.get("text", "")}
                     for r in rows],
        "identity_counts": snapshot.get("identity_counts"),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--case", choices=CASES, required=True)
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    clip_id, name, name_after = CASES[args.case]
    clip = next(c for c in clips() if c.clip_id == clip_id)
    reference = clip.reference_segments()
    with wave.open(str(clip.audio), "rb") as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, LIVE_SAMPLE_RATE)
        pcm = wav.readframes(wav.getnframes())
    cookie = args.state / "cookie.txt"
    cookie.write_text("local-open-workspace\n")
    cookie.chmod(0o600)
    ssl._create_default_https_context = ssl._create_unverified_context
    service = AccountCookieLiveReplayService(base_url="https://127.0.0.1:18530", cookie_file=cookie,
                                              timeout_seconds=300)
    result = {"case": args.case, "clip": clip_id, "duration_seconds": len(pcm) / (LIVE_SAMPLE_RATE * 2),
              "reference_speakers": sorted({r["speaker"] for r in reference}),
              "name_target": name, "name_after_audio_seconds": name_after,
              "observations": [], "naming": None, "errors": [], "voiceprints_before": None,
              "voiceprints_after": None, "session_id": None, "frame_samples": None,
              "sent_audio_seconds": 0.0, "stop": None}
    path = args.out / f"voiceprint-{args.case}.json"
    def save():
        path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    try:
        result["voiceprints_before"] = service._json("GET", "/api/voiceprints")
        created = service.create()
        sid = created.session_id
        result["session_id"] = sid
        size = created.descriptor.frame_samples
        result["frame_samples"] = size
        started = time.monotonic()
        previous_version = None
        previous_labels = None
        for seq, sample_offset in enumerate(range(0, len(pcm) // 2, size)):
            due = started + sample_offset / LIVE_SAMPLE_RATE
            if time.monotonic() < due:
                time.sleep(due - time.monotonic())
            n = min(size, len(pcm) // 2 - sample_offset)
            frame = AudioFrame(sequence=seq, pcm=pcm[2 * sample_offset:2 * (sample_offset + n)],
                               sample_count=n)
            accepted = service.accept_frame(sid, frame)
            if accepted.ack.sequence != seq or accepted.ack.start_sample != sample_offset:
                raise RuntimeError("frame ack mismatch")
            sent = (sample_offset + n) / LIVE_SAMPLE_RATE
            result["sent_audio_seconds"] = sent
            if seq % max(1, round(LIVE_SAMPLE_RATE / size)) == 0 or (name and result["naming"] is None and sent >= name_after):
                envelope = service._json("GET", f"/api/live/sessions/{sid}/snapshot")
                raw = envelope["snapshot"]
                version = (raw.get("session") or {}).get("version")
                labels = envelope.get("speaker_labels", {})
                if (version != previous_version or labels != previous_labels or
                        seq % max(1, round(5 * LIVE_SAMPLE_RATE / size)) == 0):
                    result["observations"].append(view(envelope, time.monotonic() - started, sent, reference))
                    previous_version = version
                    previous_labels = labels
                if name and result["naming"] is None and sent >= name_after:
                    scores = speaker_scores(raw, reference)
                    chosen = select_speaker(scores, name)
                    if chosen:
                        response = service._json("PUT", f"/api/meetings/{sid}/speakers/{chosen}/name",
                                                 {"label": name, "save_voiceprint": True})
                        result["naming"] = {"speaker_id": chosen, "audio_seconds": sent,
                                            "wall_seconds": time.monotonic() - started,
                                            "scores": scores, "response": response}
                        result["voiceprints_after_name"] = service._json("GET", "/api/voiceprints")
                        print(f"{args.case}: named {chosen} at audio {sent:.1f}s enrollment={response.get('enrollment')}", flush=True)
            if seq % max(1, round(10 * LIVE_SAMPLE_RATE / size)) == 0:
                print(f"{args.case}: sent {sent:.1f}/{result['duration_seconds']:.1f}s", flush=True)
                save()
        envelope = service._json("GET", f"/api/live/sessions/{sid}/snapshot")
        raw = envelope["snapshot"]
        result["observations"].append(view(envelope, time.monotonic() - started, result["sent_audio_seconds"], reference))
        settle_end = time.monotonic() + 60
        while time.monotonic() < settle_end and raw.get("pending_work_items", 0) > 0:
            time.sleep(.25)
            envelope = service._json("GET", f"/api/live/sessions/{sid}/snapshot")
            raw = envelope["snapshot"]
            labels = envelope.get("speaker_labels", {})
            if labels != previous_labels or (raw.get("session") or {}).get("version") != previous_version:
                result["observations"].append(view(envelope, time.monotonic() - started,
                                                   result["sent_audio_seconds"], reference))
                previous_labels = labels
                previous_version = (raw.get("session") or {}).get("version")
        if name and result["naming"] is None:
            scores = speaker_scores(raw, reference)
            chosen = select_speaker(scores, name)
            if chosen:
                response = service._json("PUT", f"/api/meetings/{sid}/speakers/{chosen}/name",
                                         {"label": name, "save_voiceprint": True})
                result["naming"] = {"speaker_id": chosen, "audio_seconds": result["sent_audio_seconds"],
                                    "wall_seconds": time.monotonic() - started,
                                    "scores": scores, "response": response}
                print(f"{args.case}: named {chosen} after audio enrollment={response.get('enrollment')}", flush=True)
        if result["naming"] is not None:
            target_label = name
            bank_end = time.monotonic() + 20
            while time.monotonic() < bank_end:
                bank = service._json("GET", "/api/voiceprints")
                result["voiceprints_after_name"] = bank
                if any(row.get("label") == target_label for row in bank.get("voiceprints", [])):
                    break
                time.sleep(.25)
        result["pre_stop"] = result["observations"][-1]
        stopped = asyncio.run(service.stop(sid, deadline=5.0))
        result["stop"] = {"wall_seconds": time.monotonic() - started,
                          "status": stopped.session.status,
                          "finalization_status": stopped.session.finalization_status}
        for _ in range(120):
            envelope = service._json("GET", f"/api/live/sessions/{sid}/snapshot")
            raw = envelope["snapshot"]
            session = raw.get("session") or {}
            if session.get("status") == "closed" and session.get("finalization_status") != "running":
                break
            time.sleep(.5)
        result["post_stop"] = view(envelope, time.monotonic() - started, result["sent_audio_seconds"], reference)
        result["voiceprints_after"] = service._json("GET", "/api/voiceprints")
        print(f"{args.case}: stopped status={result['stop']['status']} final={result['post_stop']['finalization_status']}", flush=True)
    except Exception as exc:
        result["errors"].append(f"{type(exc).__name__}: {exc}")
        print(f"{args.case}: ERROR {type(exc).__name__}: {exc}", flush=True)
    finally:
        save()
        service.close()

if __name__ == "__main__":
    main()
