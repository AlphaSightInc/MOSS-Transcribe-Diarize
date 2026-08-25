"""Re-measure live-mode vs file-mode accuracy on the deployed MacStudio stack.

Both arms hit the deployed backend (https://127.0.0.1:7861 -> SSH tunnel 18000 ->
4070Ti vLLM). File arm: POST /api/jobs (server ffmpeg + WindowedRunner 150/120).
Live arm: moss_transcribe_diarize.live_service_replay at pace 1.0 (2.5s span path).
Scoring: moss_transcribe_diarize.evaluation (TBSA composite / WER / coverage /
text-speaker accuracy / DER) + live_speaker_accuracy (duration-weighted speaker
accuracy + activity DER), identical evaluator for both arms.
"""
from __future__ import annotations

import json
import ssl
import sys
import time
import traceback
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ssl._create_default_https_context = ssl._create_unverified_context  # self-signed dev TLS

REPO = Path("/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize")
sys.path.insert(0, str(REPO))

from moss_transcribe_diarize import live_service_replay as replay  # noqa: E402
from moss_transcribe_diarize import live_speaker_accuracy as lsa  # noqa: E402
from moss_transcribe_diarize.evaluation import (  # noqa: E402
    Segment,
    calculate_diarization,
    calculate_tbsa,
)

BASE_URL = "https://127.0.0.1:7861"
TOKEN = (Path.home() / ".local/share/moss-transcribe-diarize/g3/shared-token").read_text().strip()
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
SAMPLES = REPO / "prototypes/streaming-diarization/data/real/benchmark_diarization_1min/samples"

CASES = [
    ("lex_bill_ackman", "primary"),
    ("lex_javier_milei", "primary"),
    ("lex_keyu_jin", "primary"),
    ("acquired_jamie_dimon", "secondary"),
    ("acquired_nfl", "secondary"),
    ("acquired_rolex", "secondary"),
]

OUT_ROOT = Path(sys.argv[1]).resolve()
OUT_ROOT.mkdir(parents=True, exist_ok=False)

TERMINAL = {"waiting_review", "done", "failed", "cancelled"}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def to_eval_segments(items) -> list[Segment]:
    return [Segment(start=float(i.start), end=float(i.end), speaker=str(i.speaker), text=str(i.text)) for i in items]


def score_arm(ref_transcript, ref_activity, hyp_segments) -> dict:
    ref_eval = to_eval_segments(ref_transcript)
    hyp_eval = to_eval_segments(hyp_segments)
    tbsa = calculate_tbsa(ref_eval, hyp_eval)
    diar = calculate_diarization(ref_eval, hyp_eval)
    hyp_activity = [lsa.SpeakerActivityInterval(s.start, s.end, s.speaker) for s in hyp_segments]
    spk = lsa.score_live_speaker_accuracy(list(ref_activity), hyp_activity)
    return {"tbsa": tbsa, "diarization": diar, "speaker": spk}


def run_file_arm(case_id: str, audio: Path) -> tuple[dict, list]:
    started = time.monotonic()
    with audio.open("rb") as fh:
        resp = requests.post(
            f"{BASE_URL}/api/jobs",
            headers=HEADERS,
            files={"file": (f"{case_id}.wav", fh, "audio/wav")},
            verify=False,
            timeout=120,
        )
    resp.raise_for_status()
    job = resp.json()
    job_id = job["id"]
    status = job.get("status")
    while status not in TERMINAL:
        time.sleep(1.0)
        job = requests.get(f"{BASE_URL}/api/jobs/{job_id}", headers=HEADERS, verify=False, timeout=30).json()
        status = job.get("status")
        if time.monotonic() - started > 600:
            raise RuntimeError(f"file job {job_id} timed out in status {status}")
    wall = time.monotonic() - started
    if status in {"failed", "cancelled"}:
        return {
            "job_id": job_id,
            "status": status,
            "error": job.get("error"),
            "wall_s": round(wall, 3),
        }, []
    seg_payload = requests.get(
        f"{BASE_URL}/api/jobs/{job_id}/segments", headers=HEADERS, verify=False, timeout=30
    ).json()
    raw_segments = seg_payload.get("segments") or []
    hyp = [
        lsa.TranscriptSegment(
            start=float(s["start"]), end=float(s["end"]), speaker=str(s["speaker"]), text=str(s.get("text") or "")
        )
        for s in raw_segments
        if s.get("end") is not None and s.get("start") is not None and float(s["end"]) > float(s["start"])
    ]
    meta = {
        "job_id": job_id,
        "status": status,
        "wall_s": round(wall, 3),
        "generated_tokens": job.get("generated_tokens"),
        "segments": len(hyp),
        "hyp_speakers": sorted({h.speaker for h in hyp}),
    }
    return meta, hyp


def run_live_arm(case_id: str, audio: Path, out_dir: Path, descriptor: dict, duration: float) -> tuple[dict, list]:
    started = time.monotonic()
    failure = None
    try:
        replay.run_service_replay(
            service=replay.HttpLiveReplayService(base_url=BASE_URL, bearer_token=TOKEN),
            audio_path=audio,
            out_dir=out_dir,
            pace=1.0,
            max_pacing_lag=3.0,
            runs=1,
            expect_revision=descriptor["source_revision"],
            expect_provider_hash=descriptor["provider_manifest_hash"],
            expect_config_hash=descriptor["config_hashes"]["combined_config_hash"],
        )
    except Exception as exc:  # keep artifacts; report failure
        failure = f"{type(exc).__name__}: {exc}"
    wall = time.monotonic() - started

    trace_path = out_dir / "run-001" / "trace.jsonl"
    snap = None
    span_reasons: dict[str, int] = {}
    empty_spans = 0
    processed = 0
    capped_flags = 0
    if trace_path.exists():
        for line in trace_path.read_text().splitlines():
            e = json.loads(line)
            kind = e.get("kind")
            if kind == "terminal":
                snap = e.get("snapshot")
            elif kind == "service_event":
                ev = e.get("event") or {}
                if ev.get("kind") == "span_frozen":
                    r = (ev.get("payload") or {}).get("reason") or "?"
                    span_reasons[r] = span_reasons.get(r, 0) + 1
                elif ev.get("kind") == "canonical_processed":
                    processed += 1
                    p = ev.get("payload") or {}
                    if p.get("empty_reason"):
                        empty_spans += 1
                    if p.get("canonical_decode_capped"):
                        capped_flags += 1
    summary_path = out_dir / "run-001" / "summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}

    hyp: list = []
    committed_empty = 0
    if snap is not None:
        payload = {"snapshot": snap}
        hyp = list(
            lsa.hypothesis_from_live_snapshot(payload, corpus_start_sample=0, corpus_duration_sec=duration)
        )
        committed = (snap.get("session") or {}).get("committed") or []
        committed_empty = sum(
            1 for c in committed if not ((c.get("revised_transcript") or c.get("transcript") or "").strip())
        )
    meta = {
        "failure": failure,
        "wall_s": round(wall, 3),
        "status": summary.get("status"),
        "frame_count": summary.get("frame_count"),
        "accepted_samples": summary.get("accepted_samples"),
        "decode_rtf_p95": summary.get("canonical_decode_rtf_p95"),
        "span_frozen_reasons": span_reasons,
        "spans_processed": processed,
        "spans_empty": committed_empty,
        "spans_empty_reason_events": empty_spans,
        "decode_capped_spans": capped_flags,
        "hyp_segments": len(hyp),
        "hyp_speakers": sorted({h.speaker for h in hyp}),
        "label_revision_version": ((snap or {}).get("session") or {}).get("label_revision_version"),
    }
    return meta, hyp


def main() -> int:
    runtime = requests.get(f"{BASE_URL}/api/runtime", verify=False, timeout=20).json()
    descriptor = runtime["live"]["descriptor"]
    provenance = {
        "base_url": BASE_URL,
        "vllm_base_url": runtime["model"].get("base_url"),
        "model": runtime["model"].get("path"),
        "windowing": runtime["model"].get("windowing"),
        "live_source_revision": descriptor.get("source_revision"),
        "combined_config_hash": descriptor.get("config_hashes", {}).get("combined_config_hash"),
        "decoding": runtime.get("inference", {}).get("decoding"),
        "max_new_tokens": runtime.get("inference", {}).get("max_new_tokens"),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    log(f"provenance: {json.dumps(provenance)}")

    results = []
    for index, (case_id, tier) in enumerate(CASES):
        case_dir = SAMPLES / case_id
        audio = case_dir / "audio.wav"
        reference = case_dir / "reference.jsonl"
        ref_transcript = lsa.load_reference_jsonl(reference)
        ref_activity = lsa.load_reference_speaker_activity_jsonl(reference)
        duration = 60.0
        ref_seconds = sum(r.duration for r in ref_activity)
        arm_order = ("file", "live") if index % 2 == 0 else ("live", "file")
        log(f"case {case_id} ({tier}) refs={len(ref_transcript)} ref_speech_s={ref_seconds:.1f} order={arm_order}")
        case_result = {
            "case_id": case_id,
            "tier": tier,
            "audio": str(audio.relative_to(REPO)),
            "reference": str(reference.relative_to(REPO)),
            "reference_segments": len(ref_transcript),
            "reference_speech_seconds": round(ref_seconds, 3),
            "reference_speakers": sorted({r.speaker for r in ref_activity}),
            "arm_order": list(arm_order),
            "arms": {},
        }
        for arm in arm_order:
            try:
                if arm == "file":
                    meta, hyp = run_file_arm(case_id, audio)
                else:
                    meta, hyp = run_live_arm(
                        case_id, audio, OUT_ROOT / case_id / "live", descriptor, duration
                    )
                scores = score_arm(ref_transcript, ref_activity, hyp) if hyp else None
                case_result["arms"][arm] = {"meta": meta, "scores": scores}
                if scores:
                    log(
                        f"  {arm:4s} tbsa={scores['tbsa']['composite']:.4f} wer={scores['tbsa']['wer']:.4f} "
                        f"cov={scores['tbsa']['text_coverage']:.4f} tsa={scores['tbsa']['text_speaker_accuracy']:.4f} "
                        f"der={scores['diarization']['der']:.4f} spk_acc={scores['speaker']['speaker_accuracy']:.4f}"
                    )
                else:
                    log(f"  {arm:4s} NO HYPOTHESIS meta={json.dumps(meta)}")
                # persist hypothesis for audit
                hyp_path = OUT_ROOT / case_id / f"{arm}-hypothesis.jsonl"
                hyp_path.parent.mkdir(parents=True, exist_ok=True)
                with hyp_path.open("w") as fh:
                    for h in hyp:
                        fh.write(
                            json.dumps(
                                {"start": h.start, "end": h.end, "speaker": h.speaker, "text": h.text},
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
            except Exception:
                case_result["arms"][arm] = {"meta": {"driver_error": traceback.format_exc()[-2000:]}, "scores": None}
                log(f"  {arm:4s} DRIVER ERROR")
        results.append(case_result)
        (OUT_ROOT / "results.json").write_text(
            json.dumps({"provenance": provenance, "cases": results}, ensure_ascii=False, indent=2) + "\n"
        )

    # aggregate primary tier
    def agg(tier: str, arm: str, path: tuple) -> float | None:
        vals = []
        for c in results:
            if c["tier"] != tier:
                continue
            node = c["arms"].get(arm, {}).get("scores")
            if not node:
                continue
            v = node
            for key in path:
                v = v[key]
            vals.append(v)
        return round(sum(vals) / len(vals), 4) if vals else None

    for tier in ("primary", "secondary"):
        line = {"tier": tier}
        for arm in ("file", "live"):
            line[arm] = {
                "tbsa": agg(tier, arm, ("tbsa", "composite")),
                "wer": agg(tier, arm, ("tbsa", "wer")),
                "coverage": agg(tier, arm, ("tbsa", "text_coverage")),
                "tsa": agg(tier, arm, ("tbsa", "text_speaker_accuracy")),
                "der": agg(tier, arm, ("diarization", "der")),
                "spk_acc": agg(tier, arm, ("speaker", "speaker_accuracy")),
                "act_der": agg(tier, arm, ("speaker", "diarization_error_rate")),
            }
        log("AGG " + json.dumps(line))
    log(f"RESULTS {OUT_ROOT / 'results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
