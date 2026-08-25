"""Paired live-vs-file measurement for one 5-minute case (5m-lex-keyu-jin) on the deployed stack."""
from __future__ import annotations

import json
import ssl
import sys
import time
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ssl._create_default_https_context = ssl._create_unverified_context

REPO = Path("/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize")
sys.path.insert(0, str(REPO))

from moss_transcribe_diarize import live_service_replay as replay  # noqa: E402
from moss_transcribe_diarize import live_speaker_accuracy as lsa  # noqa: E402
from moss_transcribe_diarize.evaluation import Segment, calculate_diarization, calculate_tbsa  # noqa: E402

BASE_URL = "https://127.0.0.1:7861"
TOKEN = (Path.home() / ".local/share/moss-transcribe-diarize/g3/shared-token").read_text().strip()
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
CASE_DIR = REPO / "prototypes/streaming-diarization/data/real/benchmark_5m/lex_keyu_jin"
DURATION = 300.0
OUT = Path(sys.argv[1]).resolve()
OUT.mkdir(parents=True, exist_ok=False)
TERMINAL = {"waiting_review", "done", "failed", "cancelled"}


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def to_eval(items):
    return [Segment(float(i.start), float(i.end), str(i.speaker), str(i.text)) for i in items]


def score(ref_t, ref_a, hyp):
    t = calculate_tbsa(to_eval(ref_t), to_eval(hyp))
    dz = calculate_diarization(to_eval(ref_t), to_eval(hyp))
    spk = lsa.score_live_speaker_accuracy(list(ref_a), [lsa.SpeakerActivityInterval(h.start, h.end, h.speaker) for h in hyp])
    return {"tbsa": t, "diarization": dz, "speaker": spk}


ref_t = lsa.load_reference_jsonl(CASE_DIR / "reference.jsonl")
ref_a = lsa.load_reference_speaker_activity_jsonl(CASE_DIR / "reference.jsonl")
log(f"refs={len(ref_t)} speech_s={sum(r.duration for r in ref_a):.1f}")

results = {}

# FILE arm
started = time.monotonic()
with (CASE_DIR / "audio.wav").open("rb") as fh:
    job = requests.post(f"{BASE_URL}/api/jobs", headers=HEADERS, files={"file": ("keyu5m.wav", fh, "audio/wav")}, verify=False, timeout=300).json()
while job.get("status") not in TERMINAL:
    time.sleep(2)
    job = requests.get(f"{BASE_URL}/api/jobs/{job['id']}", headers=HEADERS, verify=False, timeout=30).json()
segs = requests.get(f"{BASE_URL}/api/jobs/{job['id']}/segments", headers=HEADERS, verify=False, timeout=30).json()["segments"]
fhyp = [lsa.TranscriptSegment(float(s["start"]), float(s["end"]), str(s["speaker"]), str(s.get("text") or "")) for s in segs if float(s["end"]) > float(s["start"])]
results["file"] = {"meta": {"job_id": job["id"], "status": job.get("status"), "wall_s": round(time.monotonic() - started, 1), "segments": len(fhyp), "speakers": sorted({h.speaker for h in fhyp})}, "scores": score(ref_t, ref_a, fhyp)}
s = results["file"]["scores"]
log(f"file tbsa={s['tbsa']['composite']:.4f} wer={s['tbsa']['wer']:.4f} cov={s['tbsa']['text_coverage']:.4f} der={s['diarization']['der']:.4f} spk={s['speaker']['speaker_accuracy']:.4f}")

# LIVE arm
desc = requests.get(f"{BASE_URL}/api/runtime", verify=False, timeout=20).json()["live"]["descriptor"]
failure = None
started = time.monotonic()
try:
    replay.run_service_replay(
        service=replay.HttpLiveReplayService(base_url=BASE_URL, bearer_token=TOKEN),
        audio_path=CASE_DIR / "audio.wav", out_dir=OUT / "live", pace=1.0, max_pacing_lag=3.0, runs=1,
        expect_revision=desc["source_revision"], expect_provider_hash=desc["provider_manifest_hash"],
        expect_config_hash=desc["config_hashes"]["combined_config_hash"])
except Exception as exc:
    failure = f"{type(exc).__name__}: {exc}"
snap = None
reasons = {}
empty = 0
for line in (OUT / "live/run-001/trace.jsonl").read_text().splitlines():
    e = json.loads(line)
    if e.get("kind") == "terminal":
        snap = e.get("snapshot")
    elif e.get("kind") == "service_event":
        ev = e.get("event") or {}
        if ev.get("kind") == "span_frozen":
            r = (ev.get("payload") or {}).get("reason") or "?"
            reasons[r] = reasons.get(r, 0) + 1
lhyp = []
if snap:
    committed = (snap.get("session") or {}).get("committed") or []
    empty = sum(1 for c in committed if not ((c.get("revised_transcript") or c.get("transcript") or "").strip()))
    lhyp = list(lsa.hypothesis_from_live_snapshot({"snapshot": snap}, corpus_start_sample=0, corpus_duration_sec=DURATION))
results["live"] = {"meta": {"failure": failure, "wall_s": round(time.monotonic() - started, 1), "span_reasons": reasons, "spans_empty": empty, "segments": len(lhyp), "speakers": sorted({h.speaker for h in lhyp}), "label_revision_version": ((snap or {}).get("session") or {}).get("label_revision_version")}, "scores": score(ref_t, ref_a, lhyp) if lhyp else None}
if results["live"]["scores"]:
    s = results["live"]["scores"]
    log(f"live tbsa={s['tbsa']['composite']:.4f} wer={s['tbsa']['wer']:.4f} cov={s['tbsa']['text_coverage']:.4f} der={s['diarization']['der']:.4f} spk={s['speaker']['speaker_accuracy']:.4f}")
log(f"live meta: {json.dumps(results['live']['meta'])}")

for arm in ("file", "live"):
    hyp = fhyp if arm == "file" else lhyp
    with (OUT / f"{arm}-hypothesis.jsonl").open("w") as fh:
        for h in hyp:
            fh.write(json.dumps({"start": h.start, "end": h.end, "speaker": h.speaker, "text": h.text}, ensure_ascii=False) + "\n")
(OUT / "results.json").write_text(json.dumps({"case": "5m-lex-keyu-jin", "results": results}, ensure_ascii=False, indent=2) + "\n")
log(f"RESULTS {OUT}/results.json")
