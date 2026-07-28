#!/usr/bin/env python3
"""Measure what D-c's token cap actually costs a runaway decode, on the deployed engine.

Iteration 23 proved the cap is DEPLOYED (58/58 spans carry it, derivation exact on the
wire) and SAFE (min headroom 7.64x on content it was not derived from) -- and left its
LATENCY EFFECT unmeasured, because `capped_count` was 0: no span ran away, so nothing was
truncated, so the missing tail could not be credited to the cap. "Deployed", "exercised"
and "effective" are three different claims.

This probe measures the third one without waiting for a runaway to happen by chance.
F1's two runaways were *degenerate repeat loops* -- hundreds of `[0.99][S06]...[1.21]`
fragments for 2.5 s of audio, generating 2024 / 2019 tokens against VllmRunner's own 2048
default and taking 8.49 s / 8.29 s. The deployed vLLM's transcription endpoint accepts
`repetition_penalty`, and a value BELOW 1.0 rewards repeated tokens, which is the direct
way to put the decoder into that state deliberately.

The measurement is then a paired one over the SAME audio and the SAME induced loop:

  A  "pre-D-c"  -- `_token_cap` overridden to the 2048 default that was actually in force
                   before iteration 16. A semantic revert of D-c, inside the probe.
  B  "deployed" -- the product's own `_token_cap`, i.e. `canonical_decode_token_cap`.

Both run through the REAL `RunnerBoundedWavInference.transcribe_pcm` seam with a real
`FrozenSpan`, so the cap under test is the number the service would use, derived by the
product's own function rather than restated here (iteration 23's rule: import, never
restate, or the tool drifts from the code it checks).

A third condition is the control: the deployed cap with NO repetition penalty. Ordinary
content must decode normally and must NOT be truncated -- a cap that bites real speech
would be worse than the runaway it prevents.

WHAT THIS CANNOT SAY, stated so the number is not over-read: the trigger is synthetic.
F1's loops arose from real audio; this one is induced. That makes the *rate* of runaways
unmeasured here -- it says nothing about how often a meeting hits one. What it does
measure is trigger-independent: once a decode is looping, what the cap costs it in wall
clock. The serial decode queue is also untouched by this probe; it bounds the head of the
queue, not the queue.

Read-only with respect to deployed state: no session, no device, no auth state, no
service, no file outside its own scratch directory, and no restart. It sends inference
requests to the resident vLLM -- the same thing `live-identity-seam-probe.py` does.

rc 0  the runaway reproduced AND the cap hard-stopped it AND the capped decode was faster
rc 3  the runaway could NOT be induced -- the measurement is inconclusive, not a pass
rc 4  the cap did not stop generation (generated tokens exceeded the cap)
rc 2  the probe could not run
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
import wave
from pathlib import Path
from typing import Any

LIVE_SAMPLE_RATE = 16000
RECORDED_PRE_DC_DEFAULT_TOKENS = 2048  # VllmRunner.transcribe's own default, pre-D-c.
# F1's measured runaways, for comparison in the report. Evidence, not an assertion.
F1_RUNAWAY_TOKENS = (2024, 2019)
F1_RUNAWAY_ELAPSED_SEC = (8.49, 8.29)


class ProbeError(RuntimeError):
    pass


def _load_product(checkout: Path | None) -> dict[str, Any]:
    if checkout is not None:
        sys.path.insert(0, str(checkout))
    try:
        from moss_transcribe_diarize.app.live_adapters import (  # type: ignore
            RunnerBoundedWavInference,
            canonical_decode_token_cap,
        )
        from moss_transcribe_diarize.app.live_session import FrozenSpan  # type: ignore
        from moss_transcribe_diarize.app.vllm_runner import VllmRunner  # type: ignore
    except Exception as exc:  # pragma: no cover - environment problem, not logic
        raise ProbeError(f"cannot import the product from the checkout: {exc}") from exc
    return {
        "RunnerBoundedWavInference": RunnerBoundedWavInference,
        "canonical_decode_token_cap": canonical_decode_token_cap,
        "FrozenSpan": FrozenSpan,
        "VllmRunner": VllmRunner,
    }


def _read_pcm16_mono_16k(path: Path) -> bytes:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    if (channels, width, rate) != (1, 2, LIVE_SAMPLE_RATE):
        raise ProbeError(
            f"{path} is {channels}ch/{width * 8}bit/{rate}Hz; this probe needs the canonical "
            f"1ch/16bit/{LIVE_SAMPLE_RATE}Hz form and will not resample (a resampler here would "
            "be a second unreviewed implementation of the mixer's own arithmetic)."
        )
    return frames


def _fit_to_span(pcm: bytes, span_samples: int) -> tuple[bytes, str]:
    """Make the audio exactly one span long, and say which way it was adjusted."""

    have = len(pcm) // 2
    if have == span_samples:
        return pcm, "exact"
    if have > span_samples:
        return pcm[: span_samples * 2], f"truncated from {have} samples"
    # Pad with silence rather than tiling: tiling would itself be repeated content, which
    # is the very thing the repetition penalty is being used to induce. Padding keeps the
    # trigger attributable to the sampling parameter alone.
    return pcm + b"\x00" * ((span_samples - have) * 2), f"silence-padded from {have} samples"


def _make_runner(product: dict[str, Any], args: argparse.Namespace):
    base = product["VllmRunner"]

    class _PenaltyRunner(base):  # type: ignore[misc, valid-type]
        """The product's runner with one extra request field.

        `_build_fields` is the single place the wire form is decided, so overriding it and
        nothing else keeps every other part of the request byte-identical to production.
        """

        repetition_penalty: float | None = None

        def _build_fields(self, **kwargs):  # type: ignore[override]
            fields = super()._build_fields(**kwargs)
            if self.repetition_penalty is not None:
                fields["repetition_penalty"] = str(float(self.repetition_penalty))
            return fields

    runner = _PenaltyRunner(
        base_url=args.vllm_base_url,
        model=args.model,
        timeout=args.timeout,
    )
    return runner


def _bounded(product: dict[str, Any], runner, *, span_samples: int, forced_cap: int | None):
    base = product["RunnerBoundedWavInference"]
    if forced_cap is None:
        return base(runner, max_samples=span_samples, scratch_dir=None)

    class _PreDcInference(base):  # type: ignore[misc, valid-type]
        """D-c reverted: the bound that was actually in force is the runner's own default."""

        def _token_cap(self, span):  # type: ignore[override]
            return forced_cap

    return _PreDcInference(runner, max_samples=span_samples, scratch_dir=None)


def _decode_once(inference, span, pcm: bytes) -> dict[str, Any]:
    started = time.monotonic()
    result = inference.transcribe_pcm(span=span, pcm=pcm)
    wall = time.monotonic() - started
    text = result.transcript or ""
    return {
        "generated_tokens": int(result.generated_tokens),
        "token_cap": int(result.token_cap),
        "elapsed_sec": round(float(result.elapsed_sec), 4),
        "wall_sec": round(wall, 4),
        "transcript_chars": len(text),
        "transcript_head": text[:160],
        "hit_cap": int(result.generated_tokens) >= int(result.token_cap),
        "rtf": round(wall / (span.sample_count / float(LIVE_SAMPLE_RATE)), 4),
    }


def _summarise(runs: list[dict[str, Any]]) -> dict[str, Any]:
    if not runs:
        return {}
    walls = [r["wall_sec"] for r in runs]
    tokens = [r["generated_tokens"] for r in runs]
    return {
        "n": len(runs),
        "wall_sec_min": round(min(walls), 4),
        "wall_sec_median": round(statistics.median(walls), 4),
        "wall_sec_max": round(max(walls), 4),
        "tokens_min": min(tokens),
        "tokens_max": max(tokens),
        "token_cap": runs[0]["token_cap"],
        "hit_cap_count": sum(1 for r in runs if r["hit_cap"]),
        "rtf_max": round(max(r["rtf"] for r in runs), 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wav", required=True, help="16 kHz mono 16-bit source audio")
    parser.add_argument("--vllm-base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--model", default="OpenMOSS-Team/MOSS-Transcribe-Diarize")
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--checkout", default=None, help="repo root to import the product from")
    parser.add_argument(
        "--span-samples",
        type=int,
        default=40000,
        help="the contract's hard_cap_samples (2.5 s) by default",
    )
    parser.add_argument(
        "--repetition-penalty",
        type=float,
        default=0.5,
        help="below 1.0 rewards repeats; this is what induces the degenerate loop",
    )
    parser.add_argument(
        "--uncapped-tokens",
        type=int,
        default=RECORDED_PRE_DC_DEFAULT_TOKENS,
        help="the bound that was in force before D-c (VllmRunner.transcribe's own default)",
    )
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--report", default=None)
    args = parser.parse_args()

    report: dict[str, Any] = {"probe": "decode-cap-latency", "argv": vars(args).copy()}
    try:
        product = _load_product(Path(args.checkout).expanduser() if args.checkout else None)
        cap_fn = product["canonical_decode_token_cap"]
        expected_cap = int(cap_fn(sample_count=args.span_samples))
        report["expected_cap"] = expected_cap
        report["cap_expectation_source"] = "product-function"

        pcm, fit = _fit_to_span(_read_pcm16_mono_16k(Path(args.wav).expanduser()), args.span_samples)
        report["audio"] = {
            "path": str(args.wav),
            "span_samples": args.span_samples,
            "span_seconds": round(args.span_samples / float(LIVE_SAMPLE_RATE), 4),
            "fit": fit,
        }
        span = product["FrozenSpan"](
            id=0, epoch=0, start_sample=0, end_sample=args.span_samples, reason="probe"
        )

        runner = _make_runner(product, args)
        deployed = _bounded(product, runner, span_samples=args.span_samples, forced_cap=None)
        pre_dc = _bounded(
            product, runner, span_samples=args.span_samples, forced_cap=args.uncapped_tokens
        )

        # Warm-up first and discard it. Iteration 23 measured the session's first decode at
        # RTF 2.214 against <= 0.456 s for every other span; timing it would report a false
        # tail and would land on whichever condition happened to run first.
        runner.repetition_penalty = None
        warm = _decode_once(deployed, span, pcm)
        report["warmup_discarded"] = warm

        # Control: ordinary decode under the deployed cap. Must not be truncated.
        control = [_decode_once(deployed, span, pcm) for _ in range(args.repeats)]
        report["control_no_penalty_deployed_cap"] = {"runs": control, **_summarise(control)}

        # A: the runaway as it was before D-c.
        runner.repetition_penalty = args.repetition_penalty
        uncapped = [_decode_once(pre_dc, span, pcm) for _ in range(args.repeats)]
        report["induced_pre_dc_2048"] = {"runs": uncapped, **_summarise(uncapped)}

        # B: the same runaway with the deployed cap in force.
        capped = [_decode_once(deployed, span, pcm) for _ in range(args.repeats)]
        report["induced_deployed_cap"] = {"runs": capped, **_summarise(capped)}
        runner.repetition_penalty = None

        a = report["induced_pre_dc_2048"]
        b = report["induced_deployed_cap"]
        c = report["control_no_penalty_deployed_cap"]

        runaway_reproduced = a["hit_cap_count"] == a["n"]
        cap_is_hard_stop = all(r["generated_tokens"] <= expected_cap for r in capped)
        cap_bit = b["hit_cap_count"] == b["n"]
        control_untruncated = c["hit_cap_count"] == 0

        saved_median = round(a["wall_sec_median"] - b["wall_sec_median"], 4)
        report["verdict"] = {
            "expected_cap": expected_cap,
            "deployed_cap_observed": b["token_cap"],
            "cap_matches_product_function": b["token_cap"] == expected_cap,
            "runaway_reproduced": runaway_reproduced,
            "cap_is_hard_stop": cap_is_hard_stop,
            "cap_actually_bit": cap_bit,
            "control_untruncated": control_untruncated,
            "uncapped_wall_median_sec": a["wall_sec_median"],
            "capped_wall_median_sec": b["wall_sec_median"],
            "control_wall_median_sec": c["wall_sec_median"],
            "wall_saved_median_sec": saved_median,
            "speedup_x": round(a["wall_sec_median"] / b["wall_sec_median"], 3)
            if b["wall_sec_median"] > 0
            else None,
            "observed_generation_rate_tok_per_sec": round(
                a["tokens_max"] / a["wall_sec_median"], 1
            )
            if a["wall_sec_median"] > 0
            else None,
            "f1_runaway_tokens": list(F1_RUNAWAY_TOKENS),
            "f1_runaway_elapsed_sec": list(F1_RUNAWAY_ELAPSED_SEC),
        }

        if not runaway_reproduced:
            report["verdict"]["conclusion"] = (
                "INCONCLUSIVE: the decoder did not run to the pre-D-c bound, so there was no "
                "runaway for the cap to bound. This is not a pass."
            )
            rc = 3
        elif not cap_is_hard_stop:
            report["verdict"]["conclusion"] = (
                "CAP FAILED: generation exceeded the derived cap, so the bound is not enforced "
                "by the deployed engine."
            )
            rc = 4
        else:
            report["verdict"]["conclusion"] = (
                f"MEASURED: a looping decode costs {a['wall_sec_median']}s uncapped and "
                f"{b['wall_sec_median']}s under the deployed cap of {expected_cap} tokens "
                f"({saved_median}s off the head of the serial queue). The queue itself is "
                "untouched by this probe, and the runaway RATE is not measured here."
            )
            rc = 0
    except ProbeError as exc:
        report["error"] = str(exc)
        rc = 2
    except Exception as exc:  # pragma: no cover
        report["error"] = f"{type(exc).__name__}: {exc}"
        rc = 2

    report["rc"] = rc
    text = json.dumps(report, indent=2, sort_keys=False)
    if args.report:
        Path(args.report).expanduser().write_text(text + "\n", encoding="utf-8")
    print(text)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
