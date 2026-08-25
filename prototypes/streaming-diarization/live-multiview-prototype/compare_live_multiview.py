#!/usr/bin/env python3
"""Throwaway real-MOSS comparison of short provisional and longer witness views.

Question: can 5 s seam, staggered 10 s, or terminal 150 s MOSS views correct the
quality lost by independent short live spans, especially after reducing the first
publication cap from 2.5 s to 1.0 s?

One command:
    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
      prototypes/streaming-diarization/live-multiview-prototype/compare_live_multiview.py \
      --output /tmp/moss-live-multiview-results.json

The model endpoint is called serially.  Quality and endpoint inference work are
measured.  Online publication/correction times are a replay model using each real
request's elapsed time; they are not browser-paint measurements.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import tempfile
import time
import urllib.request
import wave
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

from lane_current import CASES, CORPUS_ROOT, SAMPLE_RATE, run_current_lane  # noqa: E402
from lane_rolling_terminal import (  # noqa: E402
    DecodeObservation,
    Segment as ViewSegment,
    ViewPlan,
    measure_arm,
    plan_rolling10,
    plan_terminal150,
    provisional_plan,
)
from lane_seam5 import run_lane as run_seam5_lane  # noqa: E402
from moss_transcribe_diarize.app.live_adapters import canonical_decode_token_cap  # noqa: E402
from moss_transcribe_diarize.app.live_identity import unattributed_transcript  # noqa: E402
from moss_transcribe_diarize.app.live_provider_bundle import (  # noqa: E402
    LiveProviderBundleConfig,
    _identity_encoder,
    _identity_preparer,
)
from moss_transcribe_diarize.app.live_session import (  # noqa: E402
    FrozenSpan,
    LiveIdentitySnapshot,
)
from moss_transcribe_diarize.app.live_span_bounds import span_segments  # noqa: E402
from moss_transcribe_diarize.app.vllm_runner import VllmRunner  # noqa: E402
from moss_transcribe_diarize.app.transcription_outcome import EmptyTranscriptionError  # noqa: E402


MODEL = "OpenMOSS-Team/MOSS-Transcribe-Diarize"
DEFAULT_BASE_URL = "http://127.0.0.1:18000/v1"
DEFAULT_MANIFEST = Path.home() / ".local/share/moss-transcribe-diarize/live/live-provider-manifest.json"
PCM_WIDTH = 2


def _read_case(case_id: str) -> tuple[bytes, list[dict[str, Any]], float]:
    case_dir = CORPUS_ROOT / case_id
    with wave.open(str(case_dir / "audio.wav"), "rb") as source:
        contract = (source.getnchannels(), source.getsampwidth(), source.getframerate())
        if contract != (1, PCM_WIDTH, SAMPLE_RATE):
            raise RuntimeError(f"unsupported audio contract {contract}: {case_id}")
        pcm = source.readframes(source.getnframes())
    reference = [
        json.loads(line)
        for line in (case_dir / "reference.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return pcm, reference, len(pcm) / PCM_WIDTH / SAMPLE_RATE


def _wav_file(pcm: bytes) -> Path:
    handle = tempfile.NamedTemporaryFile(prefix="moss-view-", suffix=".wav", delete=False)
    path = Path(handle.name)
    handle.close()
    with wave.open(str(path), "wb") as sink:
        sink.setnchannels(1)
        sink.setsampwidth(PCM_WIDTH)
        sink.setframerate(SAMPLE_RATE)
        sink.writeframes(pcm)
    return path


def _decode(
    runner: VllmRunner,
    *,
    pcm: bytes,
    max_new_tokens: int,
) -> dict[str, Any]:
    path = _wav_file(pcm)
    started = time.monotonic()
    try:
        result = runner.transcribe(path, max_new_tokens=max_new_tokens)
        transcript = result.text
        generated = result.generated_tokens
        outcome = "valid"
    except EmptyTranscriptionError:
        transcript = ""
        generated = 0
        outcome = "empty"
    finally:
        path.unlink(missing_ok=True)
    return {
        "transcript": transcript,
        "decode_elapsed_sec": time.monotonic() - started,
        "generated_tokens": generated,
        "classification": outcome,
    }


class _CanonicalShortDecoder:
    """Fresh per-case production WeSpeaker identity over independent MOSS spans."""

    def __init__(self, runner: VllmRunner, manifest: Path):
        self.runner = runner
        self.config = LiveProviderBundleConfig.from_manifest(manifest)
        preflight = self.config.preflight()
        if not preflight.available:
            raise RuntimeError(f"live identity preflight failed: {preflight.failures}")
        self.encoder = _identity_encoder(self.config)
        self.case_id: str | None = None
        self.preparer = None
        self.snapshot = LiveIdentitySnapshot()

    def __call__(
        self,
        case_id: str,
        span_id: int,
        start_sample: int,
        end_sample: int,
        pcm: bytes,
    ) -> Mapping[str, Any]:
        if case_id != self.case_id:
            self.case_id = case_id
            self.preparer = _identity_preparer(self.config, encoder=self.encoder)
            self.snapshot = LiveIdentitySnapshot()
        assert self.preparer is not None
        processing_started = time.monotonic()
        decoded = _decode(
            self.runner,
            pcm=pcm,
            max_new_tokens=canonical_decode_token_cap(sample_count=end_sample - start_sample),
        )
        raw = str(decoded["transcript"])
        span = FrozenSpan(
            id=span_id,
            epoch=0,
            start_sample=start_sample,
            end_sample=end_sample,
            reason="prototype_replay",
        )
        preparation = self.preparer.prepare(
            span=span,
            pcm=pcm,
            transcript=raw,
            base_snapshot=self.snapshot,
        )
        self.snapshot = preparation.proposed_snapshot
        canonical = (
            preparation.relabeled_transcript
            if preparation.status == "prepared"
            else unattributed_transcript(raw, sample_count=span.sample_count)
        )
        return {
            **decoded,
            "canonical_transcript": canonical,
            "processing_elapsed_sec": time.monotonic() - processing_started,
            "identity_status": preparation.status,
            "identity_reason": preparation.reason,
        }


def _metric_snapshot(base_url: str) -> dict[str, float]:
    url = base_url.removesuffix("/v1") + "/metrics"
    with urllib.request.urlopen(url, timeout=10) as response:
        text = response.read().decode("utf-8")
    wanted = {
        "vllm:e2e_request_latency_seconds_count",
        "vllm:e2e_request_latency_seconds_sum",
        "vllm:request_queue_time_seconds_sum",
        "vllm:request_inference_time_seconds_count",
        "vllm:request_inference_time_seconds_sum",
        "vllm:num_requests_running",
        "vllm:num_requests_waiting",
    }
    found: dict[str, float] = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        name = line.split("{", 1)[0]
        if name in wanted:
            found[name] = float(line.rsplit(" ", 1)[1])
    missing = wanted - found.keys()
    if missing:
        raise RuntimeError(f"missing endpoint metrics: {sorted(missing)}")
    return found


def _metric_delta(
    before: Mapping[str, float],
    after: Mapping[str, float],
    *,
    expected_requests: int,
    source_audio_sec: float,
    decoded_audio_sec: float,
) -> dict[str, Any]:
    count = after["vllm:request_inference_time_seconds_count"] - before["vllm:request_inference_time_seconds_count"]
    inference = after["vllm:request_inference_time_seconds_sum"] - before["vllm:request_inference_time_seconds_sum"]
    e2e = after["vllm:e2e_request_latency_seconds_sum"] - before["vllm:e2e_request_latency_seconds_sum"]
    queue = after["vllm:request_queue_time_seconds_sum"] - before["vllm:request_queue_time_seconds_sum"]
    exact = math.isclose(count, expected_requests, abs_tol=1e-9)
    return {
        "measurement_status": "measured_uncontaminated" if exact else "contaminated_external_requests",
        "expected_requests": expected_requests,
        "observed_request_delta": count,
        "endpoint_inference_sec": inference,
        "endpoint_e2e_sec": e2e,
        "endpoint_queue_sec": queue,
        "source_audio_sec": source_audio_sec,
        "decoded_audio_sec": decoded_audio_sec,
        "gpu_meeting_load_rtf": inference / source_audio_sec,
        "gpu_decoder_rtf": inference / decoded_audio_sec,
        "running_before_after": [
            before["vllm:num_requests_running"],
            after["vllm:num_requests_running"],
        ],
        "waiting_before_after": [
            before["vllm:num_requests_waiting"],
            after["vllm:num_requests_waiting"],
        ],
    }


def _run_group(
    name: str,
    base_url: str,
    expected_requests: Callable[[Any], int],
    decoded_audio: Callable[[Any], float],
    fn: Callable[[], Any],
) -> tuple[Any, dict[str, Any]]:
    print(json.dumps({"state": "group_start", "group": name}), flush=True)
    before = _metric_snapshot(base_url)
    wall_started = time.monotonic()
    result = fn()
    wall = time.monotonic() - wall_started
    after = _metric_snapshot(base_url)
    metrics = _metric_delta(
        before,
        after,
        expected_requests=expected_requests(result),
        source_audio_sec=180.0,
        decoded_audio_sec=decoded_audio(result),
    )
    metrics["client_wall_sec"] = wall
    print(json.dumps({"state": "group_complete", "group": name, "endpoint": metrics}), flush=True)
    return result, metrics


def _decode_plans(
    runner: VllmRunner,
    plans_by_case: Mapping[str, Sequence[ViewPlan]],
) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {}
    for case_id in CASES:
        pcm, _reference, _duration = _read_case(case_id)
        rows: list[dict[str, Any]] = []
        for plan in plans_by_case[case_id]:
            start_sample = round(plan.start * SAMPLE_RATE)
            end_sample = round(plan.end * SAMPLE_RATE)
            decoded = _decode(
                runner,
                pcm=pcm[start_sample * PCM_WIDTH : end_sample * PCM_WIDTH],
                max_new_tokens=(
                    12_000
                    if plan.arm == "terminal150"
                    else canonical_decode_token_cap(sample_count=end_sample - start_sample)
                ),
            )
            segments = [
                {
                    "start": segment.start,
                    "end": segment.end,
                    "speaker": segment.speaker,
                    "text": segment.text,
                }
                for segment in span_segments(
                    str(decoded["transcript"]),
                    sample_count=end_sample - start_sample,
                )
                if segment.text.strip() and segment.end > segment.start
            ]
            rows.append(
                {
                    "plan": asdict(plan),
                    **decoded,
                    "segments": segments,
                    "published_at": plan.eligible_at + float(decoded["decode_elapsed_sec"]),
                }
            )
        output[case_id] = rows
    return output


def _seam_plans(current: Mapping[str, Any]) -> dict[str, list[ViewPlan]]:
    output: dict[str, list[ViewPlan]] = {}
    for case_id, case in current["cases"].items():
        duration = float(case["duration_sec"])
        seams = [float(row["end_sec"]) for row in case["spans"][:-1]]
        eligible_seams = [
            seam
            for seam in seams
            if seam >= 2.5 - 1e-9 and seam <= duration - 2.5 + 1e-9
        ]
        plans: list[ViewPlan] = []
        for index, seam in enumerate(eligible_seams):
            previous = eligible_seams[index - 1] if index else None
            following = eligible_seams[index + 1] if index + 1 < len(eligible_seams) else None
            plans.append(
                ViewPlan(
                    arm="seam5",
                    index=len(plans),
                    start=seam - 2.5,
                    end=seam + 2.5,
                    own_start=max(
                        seam - 1.25,
                        (previous + seam) / 2.0 if previous is not None else seam - 1.25,
                    ),
                    own_end=min(
                        seam + 1.25,
                        (seam + following) / 2.0 if following is not None else seam + 1.25,
                    ),
                    eligible_at=seam + 2.5,
                )
            )
        output[case_id] = plans
    return output


def _base_segments(case: Mapping[str, Any]) -> list[dict[str, Any]]:
    output = []
    for row in case["spans"]:
        segments = row.get("canonical_absolute_segments")
        if segments is None:
            segments = row.get("absolute_segments") or []
        for segment in segments:
            output.append({**segment, "published_at": row["publication_session_sec"]})
    return output


def _provisional_observations(case: Mapping[str, Any], arm: str) -> tuple[DecodeObservation, ...]:
    observations = []
    for index, row in enumerate(case["spans"]):
        start = float(row["start_sec"])
        end = float(row["end_sec"])
        absolute = row.get("canonical_absolute_segments")
        if absolute is None:
            absolute = row.get("absolute_segments") or []
        relative = tuple(
            ViewSegment(
                start=float(item["start"]) - start,
                end=float(item["end"]) - start,
                speaker=str(item["speaker"]),
                text=str(item["text"]),
            )
            for item in absolute
        )
        observations.append(
            DecodeObservation(
                plan=provisional_plan(index, start, end, arm=arm),
                segments=relative,
                decode_started_at=max(start, end - float(row["duration_sec"])),
                published_at=float(row["publication_session_sec"]),
                gpu_elapsed_sec=float(row["decode_elapsed_sec"]),
            )
        )
    return tuple(observations)


def _view_observations(rows: Sequence[Mapping[str, Any]]) -> tuple[DecodeObservation, ...]:
    output = []
    for row in rows:
        plan = ViewPlan(**row["plan"])
        output.append(
            DecodeObservation(
                plan=plan,
                segments=tuple(ViewSegment(**item) for item in row["segments"]),
                decode_started_at=plan.eligible_at,
                published_at=float(row["published_at"]),
                gpu_elapsed_sec=float(row["decode_elapsed_sec"]),
            )
        )
    return tuple(output)


def _reference_segments(reference: Sequence[Mapping[str, Any]]) -> tuple[ViewSegment, ...]:
    return tuple(
        ViewSegment(
            start=float(item["start"]),
            end=float(item["end"]),
            speaker=str(item["speaker"]),
            text=str(item["text"]),
        )
        for item in reference
    )


def _run_seam_results(
    current: Mapping[str, Any],
    decoded: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    cases = {}
    for case_id in CASES:
        _pcm, reference, duration = _read_case(case_id)
        witness_rows = []
        for row in decoded[case_id]:
            plan = row["plan"]
            witness_rows.append(
                {
                    "window_start": plan["start"],
                    "window_end": plan["end"],
                    "seam": (plan["start"] + plan["end"]) / 2.0,
                    "ownership_start": plan["own_start"],
                    "ownership_end": plan["own_end"],
                    "timestamps": "relative",
                    "available_at": row["published_at"],
                    "decode_elapsed_sec": row["decode_elapsed_sec"],
                    "segments": row["segments"],
                }
            )
        provisional_decodes = [
            {
                "window_start": row["start_sec"],
                "window_end": row["end_sec"],
                "decode_elapsed_sec": row["decode_elapsed_sec"],
            }
            for row in current["cases"][case_id]["spans"]
        ]
        cases[case_id] = run_seam5_lane(
            duration_sec=duration,
            reference_segments=reference,
            provisional_segments=_base_segments(current["cases"][case_id]),
            witness_decodes=witness_rows,
            provisional_cap_sec=2.5,
            provisional_decodes=provisional_decodes,
        )
    return {"cases": cases, "aggregate": _aggregate_seam(cases)}


def _aggregate_quality(cases: Iterable[Mapping[str, Any]], path: Sequence[str]) -> dict[str, float]:
    rows = []
    for case in cases:
        value: Any = case
        for key in path:
            value = value[key]
        rows.append(value)
    keys = ("tbsa", "wer", "coverage", "der", "text_speaker_accuracy")
    return {
        key: statistics.mean(float(row[key]) for row in rows)
        for key in keys
        if all(key in row for row in rows)
    }


def _aggregate_seam(cases: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "macro_quality": _aggregate_quality(cases.values(), ("quality",)),
        "mean_first_publication_lag_sec": _mean_distribution(cases.values(), ("latency_sec", "first_publication")),
        "mean_visible_correction_after_provisional_sec": _mean_distribution(
            cases.values(), ("latency_sec", "visible_correction")
        ),
        "visible_corrections": sum(int(case["counts"]["visible_corrections"]) for case in cases.values()),
    }


def _mean_distribution(cases: Iterable[Mapping[str, Any]], path: Sequence[str]) -> float | None:
    values = []
    for case in cases:
        value: Any = case
        for key in path:
            value = value[key]
        mean = value.get("mean") if isinstance(value, Mapping) else None
        if isinstance(mean, (int, float)):
            values.append(float(mean))
    return statistics.mean(values) if values else None


def _run_rolling_results(
    current25: Mapping[str, Any],
    current1: Mapping[str, Any],
    rolling: Mapping[str, Sequence[Mapping[str, Any]]],
    terminal: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    cases: dict[str, Any] = {}
    for case_id in CASES:
        _pcm, reference, duration = _read_case(case_id)
        shared = {
            "duration_sec": duration,
            "reference": _reference_segments(reference),
            "rolling10": _view_observations(rolling[case_id]),
            "terminal150": _view_observations(terminal[case_id]),
        }
        cases[case_id] = {
            "base2.5": measure_arm(
                **shared,
                provisional=_provisional_observations(current25["cases"][case_id], "current2.5"),
            ),
            "base1": measure_arm(
                **shared,
                provisional=_provisional_observations(current1["cases"][case_id], "current1"),
            ),
        }
    aggregate = {}
    for base in ("base2.5", "base1"):
        base_cases = [case[base] for case in cases.values()]
        aggregate[base] = {
            "current": _aggregate_quality(base_cases, ("quality", "current")),
            "rolling10": _aggregate_quality(base_cases, ("quality", "rolling10")),
            "terminal150": _aggregate_quality(base_cases, ("quality", "terminal150")),
            "mean_first_publication_lag_sec": _mean_distribution(
                base_cases, ("latency_sec", "first_publication")
            ),
            "mean_rolling_correction_after_provisional_sec": _mean_distribution(
                base_cases, ("latency_sec", "rolling10_after_provisional_publication")
            ),
            "mean_rolling_processing_lag_sec": _mean_distribution(
                base_cases, ("latency_sec", "rolling10_processing_lag")
            ),
            "mean_terminal_final_after_meeting_sec": statistics.mean(
                float(case["latency_sec"]["terminal_final_after_meeting"])
                for case in base_cases
            ),
        }
    return {"cases": cases, "aggregate": aggregate}


def _plans(kind: str) -> dict[str, tuple[ViewPlan, ...]]:
    output = {}
    for case_id in CASES:
        _pcm, _reference, duration = _read_case(case_id)
        output[case_id] = plan_rolling10(duration) if kind == "rolling10" else plan_terminal150(duration)
    return output


def _request_count(rows: Mapping[str, Sequence[Any]]) -> int:
    return sum(len(value) for value in rows.values())


def _decoded_audio(rows: Mapping[str, Sequence[Mapping[str, Any]]]) -> float:
    return sum(
        float(row["plan"]["end"]) - float(row["plan"]["start"])
        for case in rows.values()
        for row in case
    )


def _current_requests(result: Mapping[str, Any]) -> int:
    return sum(int(case["span_count"]) for case in result["cases"].values())


def _current_audio(result: Mapping[str, Any]) -> float:
    return sum(float(case["decode"]["decoded_audio_sec"]) for case in result["cases"].values())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    runner = VllmRunner(base_url=args.base_url, model=args.model, timeout=600)
    preflight = {
        "endpoint_model": json.loads(
            urllib.request.urlopen(args.base_url + "/models", timeout=10).read().decode("utf-8")
        )["data"][0]["id"],
        "endpoint_metrics": _metric_snapshot(args.base_url),
        "cases": list(CASES),
        "source_audio_sec": 180.0,
        "manifest": str(args.manifest),
    }
    print(json.dumps({"state": "preflight", **preflight}), flush=True)

    current25, current25_gpu = _run_group(
        "current2.5",
        args.base_url,
        _current_requests,
        _current_audio,
        lambda: run_current_lane(
            cap_seconds=2.5,
            decoder=_CanonicalShortDecoder(runner, args.manifest),
        ),
    )
    current1, current1_gpu = _run_group(
        "current1",
        args.base_url,
        _current_requests,
        _current_audio,
        lambda: run_current_lane(
            cap_seconds=1.0,
            decoder=_CanonicalShortDecoder(runner, args.manifest),
        ),
    )

    seam_plans = _seam_plans(current25)
    seam, seam_gpu = _run_group(
        "seam5",
        args.base_url,
        _request_count,
        _decoded_audio,
        lambda: _decode_plans(runner, seam_plans),
    )
    rolling, rolling_gpu = _run_group(
        "rolling10",
        args.base_url,
        _request_count,
        _decoded_audio,
        lambda: _decode_plans(runner, _plans("rolling10")),
    )
    terminal, terminal_gpu = _run_group(
        "terminal150",
        args.base_url,
        _request_count,
        _decoded_audio,
        lambda: _decode_plans(runner, _plans("terminal150")),
    )

    seam_results = _run_seam_results(current25, seam)
    rolling_results = _run_rolling_results(current25, current1, rolling, terminal)
    output = {
        "schema": "moss-live-multiview-prototype.v1",
        "throwaway": True,
        "question": __doc__.splitlines()[2],
        "preflight": preflight,
        "measurement_contract": {
            "quality": "production evaluator; truth enters only after hypothesis-only reconciliation",
            "gpu": "vLLM endpoint inference-time metric deltas; exact request-count contamination guard",
            "first_publication": "replayed span eligibility plus measured request and identity wall time",
            "correction": "replayed witness eligibility plus measured isolated request wall time",
            "known_limit": (
                "coarse full-turn reference timestamps inflate TBSA/coverage/DER; WER is the primary "
                "test of actual word correction"
            ),
        },
        "current2.5": current25,
        "current1": current1,
        "seam5": {"decoded": seam, "results": seam_results},
        "rolling_terminal": {"rolling_decoded": rolling, "terminal_decoded": terminal, "results": rolling_results},
        "endpoint_gpu": {
            "current2.5": current25_gpu,
            "current1": current1_gpu,
            "seam5_component": seam_gpu,
            "rolling10_component": rolling_gpu,
            "terminal150_component": terminal_gpu,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    summary = {
        "current2.5": current25["aggregate"],
        "current1": current1["aggregate"],
        "seam5_on_2.5": seam_results["aggregate"],
        "rolling_terminal": rolling_results["aggregate"],
        "endpoint_gpu": output["endpoint_gpu"],
        "full_output": str(args.output),
    }
    print(json.dumps({"state": "complete", "summary": summary}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
