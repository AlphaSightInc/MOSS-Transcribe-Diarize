"""Paired live-vs-file measurement for ONE case on the deployed stack, case supplied by argument.

Why this exists (PREREGISTRATION-M4.md, precondition P-M4-A). M4 gates five cases; the
three-minute one (`calibration_diarization_3min/samples/lex_adam_frank`) has never been run
through the live path in this campaign, so two of M4's five gated cases have no comparator.
The checked-in paired drivers cannot acquire it: `remeasure_live_vs_file.py` walks a fixed
list of 60-second samples and `remeasure_5m_case.py` names one corpus in a module constant.

P-M4-A also says the acquiring driver must be *the checked-in paired driver's shape, not a
new instrument*. This module is that shape with the case lifted out of the constants:

- same endpoints (`/api/jobs`, `/api/runtime`) and the same shared-token file,
- same live arm (`live_service_replay.run_service_replay` at pace 1.0, lag 3.0, one run,
  descriptor pinned from `/api/runtime`),
- same scoring clock (`evaluation.calculate_tbsa` / `calculate_diarization` +
  `live_speaker_accuracy.score_live_speaker_accuracy`), the same for both arms,
- same on-disk layout, so `verify_m2_exit.case_paths`' five-file contract holds.

`--selftest` does not assert that equivalence, it checks it: the replay keywords and the
endpoint are parsed out of `remeasure_5m_case.py`'s own source, and the scoring path is
re-run over a checked-in campaign pass and required to reproduce the numbers that pass
recorded. Both fail loudly if either driver moves.

Two deliberate differences, both strictly-more-evidence:

1. the live meta carries `summary.json`'s accounting (status, frames, accepted samples,
   decode RTF) that the trio driver records and the five-minute one drops -- M4's G-M4-5
   and G-M4-11 read exactly those,
2. the case duration is derived from the WAV rather than declared, and a `--duration` (when
   given) is checked against it instead of trusted.

    python remeasure_one_case.py --case <id> --case-dir <dir> <out-dir>
    python remeasure_one_case.py --selftest
"""
from __future__ import annotations

import argparse
import ast
import json
import ssl
import sys
import time
import wave
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ssl._create_default_https_context = ssl._create_unverified_context  # self-signed dev TLS

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from moss_transcribe_diarize import live_service_replay as replay  # noqa: E402
from moss_transcribe_diarize import live_speaker_accuracy as lsa  # noqa: E402
from moss_transcribe_diarize.evaluation import (  # noqa: E402
    Segment,
    calculate_diarization,
    calculate_tbsa,
)

#: The checked-in single-case paired driver this one is the parameterized shape of. Its
#: source is the reference for every measurement parameter below; `--selftest` reads it.
REFERENCE_DRIVER = REPO / "prototypes/live-file-gap-baseline-20260824/remeasure_5m_case.py"
#: A checked-in campaign pass of that driver, used to prove the scoring clock is the same one.
REFERENCE_PASS = REPO / "evidence/live-convergence-0824/M2-e2-exit/passes/keyu5m-A"
REFERENCE_CASE_DIR = REPO / "prototypes/streaming-diarization/data/real/benchmark_5m/lex_keyu_jin"

BASE_URL = "https://127.0.0.1:7861"
TOKEN_PATH = Path.home() / ".local/share/moss-transcribe-diarize/g3/shared-token"
REPLAY_KWARGS = {"pace": 1.0, "max_pacing_lag": 3.0, "runs": 1}
TERMINAL = {"waiting_review", "done", "failed", "cancelled"}
#: The pass layout downstream verifiers read (`verify_m2_exit.case_paths`); `--selftest`
#: requires these to be exactly the five relative paths that contract names.
RESULTS_NAME = "results.json"
HYPOTHESIS_NAME = "{arm}-hypothesis.jsonl"
LIVE_DIR = "live"
#: The live path's transport contract (`app/live_session.py`): 16 kHz mono PCM16.
EXPECTED_SAMPLE_RATE = 16000
EXPECTED_CHANNELS = 1
EXPECTED_SAMPLE_WIDTH = 2


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN_PATH.read_text().strip()}"}


# ------------------------------------------------------------------ corpus


def wav_duration_seconds(path: Path) -> float:
    """The case duration, read from the audio rather than declared beside it.

    Refuses anything the live transport would have to resample: a comparator measured on
    converted audio is not paired with the file arm's bytes.
    """

    with wave.open(str(path)) as handle:
        rate, channels, width, frames = (
            handle.getframerate(),
            handle.getnchannels(),
            handle.getsampwidth(),
            handle.getnframes(),
        )
    if (rate, channels, width) != (EXPECTED_SAMPLE_RATE, EXPECTED_CHANNELS, EXPECTED_SAMPLE_WIDTH):
        raise SystemExit(
            f"REFUSED: {path} is {rate} Hz / {channels} ch / {width * 8} bit; "
            f"the live path takes {EXPECTED_SAMPLE_RATE} Hz mono PCM16"
        )
    return frames / float(rate)


def to_eval(items) -> list[Segment]:
    return [
        Segment(start=float(i.start), end=float(i.end), speaker=str(i.speaker), text=str(i.text))
        for i in items
    ]


def score(ref_transcript, ref_activity, hypothesis) -> dict:
    """The campaign's scoring clock, identical for both arms (checked by `--selftest`)."""

    return {
        "tbsa": calculate_tbsa(to_eval(ref_transcript), to_eval(hypothesis)),
        "diarization": calculate_diarization(to_eval(ref_transcript), to_eval(hypothesis)),
        "speaker": lsa.score_live_speaker_accuracy(
            list(ref_activity),
            [lsa.SpeakerActivityInterval(h.start, h.end, h.speaker) for h in hypothesis],
        ),
    }


def write_hypothesis(path: Path, hypothesis) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for h in hypothesis:
            fh.write(
                json.dumps(
                    {"start": h.start, "end": h.end, "speaker": h.speaker, "text": h.text},
                    ensure_ascii=False,
                )
                + "\n"
            )


def load_hypothesis(path: Path) -> list:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return [
        lsa.TranscriptSegment(
            start=float(r["start"]), end=float(r["end"]), speaker=str(r["speaker"]), text=str(r["text"])
        )
        for r in rows
    ]


# ------------------------------------------------------------------ arms


def run_file_arm(case: str, audio: Path) -> tuple[dict, list]:
    started = time.monotonic()
    with audio.open("rb") as fh:
        job = requests.post(
            f"{BASE_URL}/api/jobs",
            headers=headers(),
            files={"file": (f"{case}.wav", fh, "audio/wav")},
            verify=False,
            timeout=300,
        ).json()
    while job.get("status") not in TERMINAL:
        time.sleep(2)
        job = requests.get(
            f"{BASE_URL}/api/jobs/{job['id']}", headers=headers(), verify=False, timeout=30
        ).json()
    segments = requests.get(
        f"{BASE_URL}/api/jobs/{job['id']}/segments", headers=headers(), verify=False, timeout=30
    ).json()["segments"]
    hypothesis = [
        lsa.TranscriptSegment(
            float(s["start"]), float(s["end"]), str(s["speaker"]), str(s.get("text") or "")
        )
        for s in segments
        if float(s["end"]) > float(s["start"])
    ]
    meta = {
        "job_id": job["id"],
        "status": job.get("status"),
        "wall_s": round(time.monotonic() - started, 1),
        "generated_tokens": job.get("generated_tokens"),
        "segments": len(hypothesis),
        "speakers": sorted({h.speaker for h in hypothesis}),
    }
    return meta, hypothesis


def run_live_arm(audio: Path, out_dir: Path, descriptor: dict, duration: float) -> tuple[dict, list]:
    started = time.monotonic()
    failure = None
    try:
        replay.run_service_replay(
            service=replay.HttpLiveReplayService(base_url=BASE_URL, bearer_token=TOKEN_PATH.read_text().strip()),
            audio_path=audio,
            out_dir=out_dir,
            expect_revision=descriptor["source_revision"],
            expect_provider_hash=descriptor["provider_manifest_hash"],
            expect_config_hash=descriptor["config_hashes"]["combined_config_hash"],
            **REPLAY_KWARGS,
        )
    except Exception as exc:  # keep the artifacts; the trace is the evidence
        failure = f"{type(exc).__name__}: {exc}"
    wall = time.monotonic() - started

    snapshot = None
    span_reasons: dict[str, int] = {}
    trace = out_dir / "run-001/trace.jsonl"
    if trace.exists():
        for line in trace.read_text().splitlines():
            event = json.loads(line)
            if event.get("kind") == "terminal":
                snapshot = event.get("snapshot")
            elif event.get("kind") == "service_event":
                payload = event.get("event") or {}
                if payload.get("kind") == "span_frozen":
                    reason = (payload.get("payload") or {}).get("reason") or "?"
                    span_reasons[reason] = span_reasons.get(reason, 0) + 1
    summary_path = out_dir / "run-001/summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}

    hypothesis: list = []
    empty = 0
    if snapshot is not None:
        committed = (snapshot.get("session") or {}).get("committed") or []
        empty = sum(
            1 for c in committed if not ((c.get("revised_transcript") or c.get("transcript") or "").strip())
        )
        hypothesis = list(
            lsa.hypothesis_from_live_snapshot(
                {"snapshot": snapshot}, corpus_start_sample=0, corpus_duration_sec=duration
            )
        )
    meta = {
        "failure": failure,
        "wall_s": round(wall, 1),
        "status": summary.get("status"),
        "frame_count": summary.get("frame_count"),
        "accepted_samples": summary.get("accepted_samples"),
        "decode_rtf_p95": summary.get("canonical_decode_rtf_p95"),
        "span_reasons": span_reasons,
        "spans_empty": empty,
        "segments": len(hypothesis),
        "speakers": sorted({h.speaker for h in hypothesis}),
        "label_revision_version": ((snapshot or {}).get("session") or {}).get("label_revision_version"),
        "text_revision_version": ((snapshot or {}).get("session") or {}).get("text_revision_version"),
    }
    return meta, hypothesis


# ------------------------------------------------------------------ the pass


def measure(case: str, case_dir: Path, out: Path, declared_duration: float | None) -> int:
    audio, reference = case_dir / "audio.wav", case_dir / "reference.jsonl"
    duration = wav_duration_seconds(audio)
    if declared_duration is not None and abs(declared_duration - duration) > 1e-6:
        raise SystemExit(f"REFUSED: --duration {declared_duration} but {audio} is {duration}s long")
    out.mkdir(parents=True, exist_ok=False)

    ref_transcript = lsa.load_reference_jsonl(reference)
    ref_activity = lsa.load_reference_speaker_activity_jsonl(reference)
    log(
        f"case={case} duration={duration:.1f}s refs={len(ref_transcript)} "
        f"speech_s={sum(r.duration for r in ref_activity):.1f} "
        f"speakers={sorted({r.speaker for r in ref_activity})}"
    )

    runtime = requests.get(f"{BASE_URL}/api/runtime", verify=False, timeout=20).json()
    descriptor = runtime["live"]["descriptor"]
    provenance = {
        "base_url": BASE_URL,
        "vllm_base_url": runtime["model"].get("base_url"),
        "model": runtime["model"].get("path"),
        "windowing": runtime["model"].get("windowing"),
        "live_source_revision": descriptor.get("source_revision"),
        "combined_config_hash": (descriptor.get("config_hashes") or {}).get("combined_config_hash"),
        "decoding": (runtime.get("inference") or {}).get("decoding"),
        "max_new_tokens": (runtime.get("inference") or {}).get("max_new_tokens"),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    log(f"provenance: {json.dumps(provenance)}")

    results: dict[str, dict] = {}
    for arm in ("file", "live"):
        if arm == "file":
            meta, hypothesis = run_file_arm(case, audio)
        else:
            meta, hypothesis = run_live_arm(audio, out / LIVE_DIR, descriptor, duration)
        scores = score(ref_transcript, ref_activity, hypothesis) if hypothesis else None
        results[arm] = {"meta": meta, "scores": scores}
        write_hypothesis(out / HYPOTHESIS_NAME.format(arm=arm), hypothesis)
        if scores:
            log(
                f"  {arm:4s} tbsa={scores['tbsa']['composite']:.4f} wer={scores['tbsa']['wer']:.4f} "
                f"cov={scores['tbsa']['text_coverage']:.4f} der={scores['diarization']['der']:.4f} "
                f"spk={scores['speaker']['speaker_accuracy']:.4f}"
            )
        else:
            log(f"  {arm:4s} NO HYPOTHESIS meta={json.dumps(meta)}")
    log(f"live meta: {json.dumps(results['live']['meta'])}")

    (out / RESULTS_NAME).write_text(
        json.dumps(
            {
                "case": case,
                "case_dir": str(case_dir.relative_to(REPO)),
                "duration_sec": duration,
                "provenance": provenance,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    log(f"RESULTS {out / RESULTS_NAME}")
    return 0 if results["live"]["scores"] and results["file"]["scores"] else 1


# ------------------------------------------------------------------ selftest


def reference_driver_facts() -> dict:
    """Measurement parameters parsed out of the checked-in driver, not restated here."""

    tree = ast.parse(REFERENCE_DRIVER.read_text())
    facts: dict = {"replay_kwargs": {}, "base_url": None, "endpoints": set()}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "BASE_URL":
                    facts["base_url"] = ast.literal_eval(node.value)
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "run_service_replay":
                for keyword in node.keywords:
                    if isinstance(keyword.value, ast.Constant):
                        facts["replay_kwargs"][keyword.arg] = keyword.value.value
        if isinstance(node, ast.JoinedStr):
            rendered = "".join(
                part.value for part in node.values if isinstance(part, ast.Constant)
            )
            if "/api/" in rendered:
                facts["endpoints"].add(rendered)
    return facts


def selftest() -> int:
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str) -> None:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}: {detail}")
        if not ok:
            failures.append(name)

    facts = reference_driver_facts()

    check(
        "replay-kwargs-match-checked-in-driver",
        facts["replay_kwargs"] == REPLAY_KWARGS,
        f"reference {facts['replay_kwargs']} vs ours {REPLAY_KWARGS}",
    )
    check(
        "endpoint-matches-checked-in-driver",
        facts["base_url"] == BASE_URL,
        f"reference {facts['base_url']} vs ours {BASE_URL}",
    )
    ours = {"/api/jobs", "/api/runtime"}
    check(
        "endpoints-are-a-subset-of-the-checked-in-driver's",
        all(any(e in ref for ref in facts["endpoints"]) for e in ours),
        f"ours {sorted(ours)} against reference {sorted(facts['endpoints'])}",
    )

    # The scoring clock: re-score a checked-in campaign pass and reproduce its own numbers.
    recorded = json.loads((REFERENCE_PASS / "results.json").read_text())["results"]
    ref_transcript = lsa.load_reference_jsonl(REFERENCE_CASE_DIR / "reference.jsonl")
    ref_activity = lsa.load_reference_speaker_activity_jsonl(REFERENCE_CASE_DIR / "reference.jsonl")
    for arm in ("file", "live"):
        rescored = score(ref_transcript, ref_activity, load_hypothesis(REFERENCE_PASS / f"{arm}-hypothesis.jsonl"))
        deltas = {
            "wer": abs(rescored["tbsa"]["wer"] - recorded[arm]["scores"]["tbsa"]["wer"]),
            "der": abs(rescored["diarization"]["der"] - recorded[arm]["scores"]["diarization"]["der"]),
            "spk": abs(
                rescored["speaker"]["speaker_accuracy"]
                - recorded[arm]["scores"]["speaker"]["speaker_accuracy"]
            ),
            "cov": abs(
                rescored["tbsa"]["text_coverage"] - recorded[arm]["scores"]["tbsa"]["text_coverage"]
            ),
        }
        check(
            f"scoring-reproduces-checked-in-pass-{arm}",
            max(deltas.values()) <= 1e-12,
            f"max delta {max(deltas.values()):.3e} over {sorted(deltas)}",
        )

    # Duration comes from the audio, and non-live-path audio is refused rather than resampled.
    check(
        "duration-read-from-the-wav",
        abs(wav_duration_seconds(REFERENCE_CASE_DIR / "audio.wav") - 300.0) <= 1e-9,
        f"{wav_duration_seconds(REFERENCE_CASE_DIR / 'audio.wav'):.6f}s",
    )
    bad = Path("/tmp/remeasure-one-case-selftest-8k.wav")
    with wave.open(str(bad), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\0\0" * 8000)
    refused = False
    try:
        wav_duration_seconds(bad)
    except SystemExit:
        refused = True
    check("refuses-audio-the-live-path-would-resample", refused, "8 kHz WAV -> SystemExit")
    bad.unlink()

    # The on-disk layout the downstream verifiers read (`verify_m2_exit.case_paths`).
    from verify_m2_exit import case_paths  # noqa: PLC0415 - selftest-only dependency

    expected = case_paths(REFERENCE_PASS.parent, "keyu-5m", "A")
    # Archived bundles gzip the trace, so a path counts as present in either form.
    present = {
        name: path.exists() or path.with_suffix(path.suffix + ".gz").exists()
        for name, path in expected.items()
    }
    check(
        "layout-matches-case_paths",
        all(present.values()),
        f"{sum(present.values())}/{len(expected)} paths under {REFERENCE_PASS.name}: "
        f"{sorted(name for name, ok in present.items() if not ok) or 'all present'}",
    )
    produced = {
        RESULTS_NAME,
        HYPOTHESIS_NAME.format(arm="file"),
        HYPOTHESIS_NAME.format(arm="live"),
        f"{LIVE_DIR}/run-001/trace.jsonl",
        f"{LIVE_DIR}/run-001/summary.json",
    }
    wanted = {str(path.relative_to(REFERENCE_PASS)) for path in expected.values()}
    check(
        "driver-writes-that-layout",
        produced == wanted,
        f"writes {sorted(produced)}; contract wants {sorted(wanted)}",
    )

    print(f"\nselftest: {len(failures)} failures")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", nargs="?", type=Path, help="pass directory to create")
    parser.add_argument("--case", help="case id recorded in results.json")
    parser.add_argument("--case-dir", type=Path, help="directory holding audio.wav + reference.jsonl")
    parser.add_argument("--duration", type=float, default=None, help="checked against the WAV, never trusted")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    if not (args.out and args.case and args.case_dir):
        parser.error("--case, --case-dir and <out> are required unless --selftest")
    return measure(args.case, args.case_dir.resolve(), args.out.resolve(), args.duration)


if __name__ == "__main__":
    raise SystemExit(main())
