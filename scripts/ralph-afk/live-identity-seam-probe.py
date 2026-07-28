#!/usr/bin/env python3
"""Host-side identity-seam probe: what does a real decode + real identity preparation produce?

Why this exists
---------------
`live-pipeline-probe.py` drives the deployed service from outside and can see only what the
HTTP surface reports. When a span fails identity preparation the surface says
`{kind: identity_commit, code: canonical_not_submitted, detail: {identity_status: "failed"}}`
and stops: the preparation's `reason` is written into a *proposed* snapshot that is never
committed, so the one string that names the defect never leaves the process.

This probe closes that gap without changing product source. It runs on the host, under the
service's own interpreter and the deployed checkout, and rebuilds exactly the two seams the
runtime builds from the same manifest -- the bounded decoder over the vLLM runner, and the
bounded causal identity preparer over the manifest's evidence provider -- then reports
`status`, `reason` and the decoded transcript for one span of real audio.

It is a Ralph evidence tool, not product source: nothing in the product imports it, and it
mutates nothing. It sends one inference request to the same vLLM endpoint the service uses
and loads a second copy of the ONNX identity encoder (CPU); it does not touch the live
service, its state file, or any session.

Discriminating the four `_failed` reasons
-----------------------------------------
`BoundedCausalIdentityPreparer` checks pcm length, then transcript parseability, then segment
timestamps, and only then calls the evidence provider. So the preparation is run twice --
once with the manifest's real evidence provider and once with none -- and the pair of answers
names which side of that boundary the defect is on:

    same reason both times      -> a pre-evidence check (pcm / parse / timestamps)
    only the real one fails     -> the evidence provider
    both prepared               -> this input does not reproduce it
"""

from __future__ import annotations

import argparse
import json
import sys
import wave
from pathlib import Path

SAMPLE_RATE = 16000


def read_pcm(path: Path) -> bytes:
    with wave.open(str(path)) as handle:
        if (handle.getnchannels(), handle.getframerate(), handle.getsampwidth()) != (1, SAMPLE_RATE, 2):
            raise SystemExit(
                f"{path} must be mono {SAMPLE_RATE} Hz 16-bit, got "
                f"{handle.getnchannels()}ch/{handle.getframerate()}Hz/{handle.getsampwidth()*8}bit"
            )
        return handle.readframes(handle.getnframes())


def prepare_once(preparer, *, span, pcm: bytes, transcript: str, snapshot) -> dict:
    preparation = preparer.prepare(span=span, pcm=pcm, transcript=transcript, base_snapshot=snapshot)
    return {
        "status": preparation.status,
        "reason": preparation.reason,
        "proposed_snapshot_version": preparation.proposed_snapshot.version,
        "base_snapshot_version": preparation.base_snapshot_version,
        "canonical_speakers": list(preparation.proposed_snapshot.canonical_speakers),
        "diagnostics": {key: value for key, value in preparation.proposed_snapshot.diagnostics},
        "relabeled_transcript_len": len(preparation.relabeled_transcript),
        # The session publishes a *relabeled* span only when this is true (live_session.
        # _identity_preparation_refusal); since J2 anything else publishes the span
        # unattributed instead of ending the session.
        "would_publish": preparation.status == "prepared" and preparation.reason is None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", required=True, help="deployed live provider manifest")
    parser.add_argument("--wav", required=True, help="one span of real audio, mono 16 kHz 16-bit")
    parser.add_argument("--vllm-base-url", required=True)
    parser.add_argument("--vllm-model", required=True)
    parser.add_argument("--vllm-timeout", type=float, default=600.0)
    parser.add_argument("--vllm-api-key", default=None)
    parser.add_argument("--span-id", type=int, default=0)
    parser.add_argument("--report", default="", help="optional JSON report path")
    args = parser.parse_args()

    from moss_transcribe_diarize.app.live_adapters import RunnerBoundedWavInference
    from moss_transcribe_diarize.app.live_coordinator import _empty_transcript_reason
    from moss_transcribe_diarize.app.live_identity import (
        BoundedCausalIdentityPreparer,
        NoLiveSpeakerEvidence,
    )
    from moss_transcribe_diarize.app.live_provider_bundle import (
        LiveProviderBundleConfig,
        _identity_config,
        _identity_encoder,
        _identity_evidence_provider,
    )
    from moss_transcribe_diarize.app.live_session import FrozenSpan, LiveIdentitySnapshot
    from moss_transcribe_diarize.app.vllm_runner import VllmRunner
    from moss_transcribe_diarize.transcript_parser import parse_transcript

    config = LiveProviderBundleConfig.from_manifest(args.manifest)
    pcm = read_pcm(Path(args.wav))
    sample_count = len(pcm) // 2
    span = FrozenSpan(
        id=args.span_id,
        epoch=0,
        start_sample=0,
        end_sample=sample_count,
        reason="identity_seam_probe",
    )
    duration_sec = sample_count / float(SAMPLE_RATE)

    report: dict = {
        "schema": "ralph-live-identity-seam-probe.v1",
        "manifest": str(args.manifest),
        "wav": str(args.wav),
        "span": {"sample_count": sample_count, "duration_sec": round(duration_sec, 4)},
        "identity_config": dict(config.identity_config),
        "identity_provider": {
            key: value for key, value in config.identity_provider.items() if key != "path"
        },
    }

    decoder = RunnerBoundedWavInference(
        VllmRunner(
            base_url=args.vllm_base_url,
            model=args.vllm_model,
            api_key=args.vllm_api_key,
            timeout=args.vllm_timeout,
        ),
        max_samples=int(config.decoder_config["max_samples"]),
    )
    inferred = decoder.transcribe_pcm(span=span, pcm=pcm)
    segments = tuple(parse_transcript(inferred.transcript))
    report["decode"] = {
        "elapsed_sec": round(inferred.elapsed_sec or 0.0, 3),
        "rtf": round((inferred.elapsed_sec or 0.0) / duration_sec, 3) if duration_sec else None,
        "generated_tokens": inferred.generated_tokens,
        "transcript": inferred.transcript,
        "coordinator_empty_reason": _empty_transcript_reason(inferred.transcript),
        "segments": [
            {"start": segment.start, "end": segment.end, "speaker": segment.speaker}
            for segment in segments
        ],
        # The check at live_identity.py:101 -- a segment ending past the span is `_failed`.
        "max_segment_end": max((segment.end for segment in segments), default=None),
        "segments_outside_span": [
            {"start": segment.start, "end": segment.end}
            for segment in segments
            if segment.start < 0 or segment.end > duration_sec
        ],
    }

    identity_config = _identity_config(config.identity_config)
    snapshot = LiveIdentitySnapshot()
    report["preparation_with_evidence"] = prepare_once(
        BoundedCausalIdentityPreparer(
            config=identity_config,
            evidence_provider=_identity_evidence_provider(config, encoder=_identity_encoder(config)),
        ),
        span=span,
        pcm=pcm,
        transcript=inferred.transcript,
        snapshot=snapshot,
    )
    report["preparation_without_evidence"] = prepare_once(
        BoundedCausalIdentityPreparer(config=identity_config, evidence_provider=NoLiveSpeakerEvidence()),
        span=span,
        pcm=pcm,
        transcript=inferred.transcript,
        snapshot=snapshot,
    )

    with_evidence = report["preparation_with_evidence"]
    without_evidence = report["preparation_without_evidence"]
    if with_evidence["would_publish"]:
        verdict = "prepared: this input does not reproduce the identity failure"
    elif with_evidence["reason"] == without_evidence["reason"]:
        verdict = f"pre-evidence check: {with_evidence['status']}/{with_evidence['reason']}"
    elif without_evidence["would_publish"]:
        verdict = f"evidence provider: {with_evidence['status']}/{with_evidence['reason']}"
    else:
        verdict = (
            f"both sides answer, differently: with={with_evidence['status']}/{with_evidence['reason']} "
            f"without={without_evidence['status']}/{without_evidence['reason']}"
        )
    report["verdict"] = verdict

    text = json.dumps(report, indent=2)
    print(text)
    if args.report:
        Path(args.report).write_text(text + "\n", encoding="utf-8")
    return 0 if with_evidence["would_publish"] else 4


if __name__ == "__main__":
    sys.exit(main())
