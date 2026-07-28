#!/usr/bin/env python3
"""Offline reproduction of F0 blocker 2: `frozen span end must advance.`

Why this exists
---------------
F0 (iteration 9) hit `400 frozen span end must advance.` on the deployed host after
eleven accepted frames and recorded an honest caveat: the probe's two lanes carried
*identical* `capture_timestamp_ns`, which a real Mac capture will not, so the defect
could not be concluded before that input property was ruled in or out.

This script rules it out structurally rather than by argument. It drives the **real**
`LiveSession` + `EndpointPolicy` + `LiveCoordinator` with the values the deployed
provider manifest actually carries, on this host, with no server, no GPU, no Mac and no
network. Everything it needs lives downstream of the mixer, and the frame the mixer hands
the coordinator (`live_session.AudioFrame`) has no timestamp field at all -- which the
script checks and prints rather than asserting in prose.

It is a Ralph evidence tool, not product source: nothing in the product imports it, and
it changes nothing. It exists so that whoever is authorized to fix H2 has a red
reproduction that costs two seconds instead of a paired device and a live session.

Defaults are the deployed values, read from
`~/.local/share/moss-transcribe-diarize/live/live-provider-manifest.json` on
ga0-alienware-rtx4070ti on 2026-07-28:
    bounds_config.hard_cap_samples   = 40000   -> LiveSession(hard_cap_samples=...)
    endpoint_config.hard_cap_samples = 40000   -> EndpointPolicyConfig(hard_cap_samples=...)
    endpoint_config.min_speech_samples  = 1600
    endpoint_config.min_silence_samples = 8000
    endpoint_config.{pre,post}_speech_padding_samples = 1600
    bounds_config.max_retained_samples = 960000, frame_samples = 8000

The two caps are equal because C2's finalizer *requires* them to be equal
(`live_manifest_finalizer.py`: "the endpoint closes the span and LiveSession freezes it --
a divergence silently splits spans"). Pass `--session-hard-cap none` to get the shape
every test in the repo uses instead.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from moss_transcribe_diarize.app.live_arbiter import InferenceArbiter  # noqa: E402
from moss_transcribe_diarize.app.live_coordinator import LiveCoordinator  # noqa: E402
from moss_transcribe_diarize.app.live_endpoint import (  # noqa: E402
    EndpointPolicy,
    EndpointPolicyConfig,
    SpeechObservation,
)
from moss_transcribe_diarize.app.live_session import AudioFrame, LiveSession  # noqa: E402

# Deployed manifest values (see the module docstring for provenance).
DEPLOYED = {
    "session_hard_cap": 40000,
    "endpoint_hard_cap": 40000,
    "min_speech_samples": 1600,
    "min_silence_samples": 8000,
    "pre_speech_padding_samples": 1600,
    "post_speech_padding_samples": 1600,
    "max_retained_samples": 960000,
    "frame_samples": 8000,
}


class WholeFrameSpeech:
    """One observation per accepted frame, speech present per the requested pattern.

    A real `SpeechSignalProvider` segments inside the frame; this one does not, because
    the collision under test is a function of cumulative accepted samples and the two
    hard caps, never of where inside a frame speech starts. Using the real VAD here would
    add a dependency and remove nothing from the reproduction.
    """

    def __init__(self, pattern: str):
        self._pattern = pattern
        self._index = 0

    def observe(self, *, frame, start_sample: int, end_sample: int):
        del frame
        present = self._pattern[self._index % len(self._pattern)] == "1"
        self._index += 1
        return (
            SpeechObservation(
                start_sample=start_sample,
                end_sample=end_sample,
                speech_present=present,
            ),
        )


class UnusedDecoder:
    """The coordinator requires a decoder; nothing in this reproduction decodes."""

    def transcribe(self, *args, **kwargs):  # pragma: no cover - never reached
        raise AssertionError("this reproduction fails before any decode")


class UnusedIdentityPreparer:
    def prepare(self, *args, **kwargs):  # pragma: no cover - never reached
        raise AssertionError("this reproduction fails before any identity work")


def _hard_cap(value: str) -> int | None:
    if value.strip().lower() in {"none", "null", ""}:
        return None
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("hard cap must be positive or 'none'")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--session-hard-cap", type=_hard_cap, default=str(DEPLOYED["session_hard_cap"]),
                        help="LiveSession hard cap; 'none' reproduces every test harness in the repo")
    parser.add_argument("--endpoint-hard-cap", type=_hard_cap, default=str(DEPLOYED["endpoint_hard_cap"]),
                        help="EndpointPolicy hard cap; 'none' disables the policy's own boundary")
    parser.add_argument("--min-speech-samples", type=int, default=DEPLOYED["min_speech_samples"])
    parser.add_argument("--min-silence-samples", type=int, default=DEPLOYED["min_silence_samples"])
    parser.add_argument("--pre-speech-padding-samples", type=int, default=DEPLOYED["pre_speech_padding_samples"])
    parser.add_argument("--post-speech-padding-samples", type=int, default=DEPLOYED["post_speech_padding_samples"])
    parser.add_argument("--max-retained-samples", type=int, default=DEPLOYED["max_retained_samples"])
    parser.add_argument("--frame-samples", type=int, default=DEPLOYED["frame_samples"],
                        help="mixed frame size; the collision is independent of this")
    parser.add_argument("--frames", type=int, default=16, help="how many mixed frames to feed")
    parser.add_argument("--speech-pattern", default="1",
                        help="cycled per frame: '1' speech, '0' silence. Default '1' = "
                             "continuous speech, i.e. no endpoint before the hard cap")
    args = parser.parse_args()

    for character in args.speech_pattern:
        if character not in "01":
            parser.error("--speech-pattern accepts only '0' and '1'")

    timestamp_fields = [
        field.name for field in dataclasses.fields(AudioFrame) if "time" in field.name
    ]
    print("evidence: mixed_frame_fields=" + ",".join(field.name for field in dataclasses.fields(AudioFrame)))
    print(f"evidence: mixed_frame_timestamp_fields={timestamp_fields or 'none'}")
    print(
        "evidence: lane_capture_timestamps_reach_the_coordinator="
        f"{'true' if timestamp_fields else 'false'}"
    )

    session = LiveSession(
        max_retained_samples=args.max_retained_samples,
        hard_cap_samples=args.session_hard_cap,
    )
    coordinator = LiveCoordinator(
        session_key="hardcap-repro",
        session=session,
        endpoint_policy=EndpointPolicy(
            EndpointPolicyConfig(
                min_speech_samples=args.min_speech_samples,
                min_silence_samples=args.min_silence_samples,
                pre_speech_padding_samples=args.pre_speech_padding_samples,
                post_speech_padding_samples=args.post_speech_padding_samples,
                hard_cap_samples=args.endpoint_hard_cap,
            )
        ),
        speech_provider=WholeFrameSpeech(args.speech_pattern),
        decoder=UnusedDecoder(),
        identity_preparer=UnusedIdentityPreparer(),
        arbiter=InferenceArbiter(),
    )

    print(
        f"config: session_hard_cap={args.session_hard_cap} "
        f"endpoint_hard_cap={args.endpoint_hard_cap} "
        f"frame_samples={args.frame_samples} pattern={args.speech_pattern}"
    )

    pcm = bytes(args.frame_samples * 2)
    queued_ids: list[int] = []
    for sequence in range(args.frames):
        frame = AudioFrame(sequence=sequence, pcm=pcm, sample_count=args.frame_samples)
        frozen_before = session.snapshot().frozen_until_sample
        try:
            result = coordinator.accept_frame(frame)
        except Exception as error:  # the defect surfaces as ValueError from LiveSession
            snapshot = session.snapshot()
            print(
                f"frame={sequence:3d} accepted_samples={snapshot.accepted_samples:7d} "
                f"REFUSED {type(error).__name__}: {error}"
            )
            print(
                "evidence: session_frozen_until_before_the_refused_freeze="
                f"{snapshot.frozen_until_sample}"
            )
            print(f"evidence: session_frozen_span_ids={list(snapshot.pending_span_ids)}")
            print(f"evidence: coordinator_queued_span_ids={queued_ids}")
            print(
                "verdict: reproduced at accepted_samples="
                f"{snapshot.accepted_samples} — {type(error).__name__}: {error}"
            )
            return 3
        queued_ids.extend(result.queued_item_ids)
        snapshot = session.snapshot()
        session_frozen = snapshot.frozen_until_sample != frozen_before and not result.frozen_spans
        print(
            f"frame={sequence:3d} accepted_samples={snapshot.accepted_samples:7d} "
            f"frozen_until={snapshot.frozen_until_sample:7d} "
            f"endpoint_spans={[(span.start_sample, span.end_sample, span.reason) for span in result.endpoint_spans]} "
            f"queued={list(result.queued_item_ids)}"
            + ("  <- LiveSession froze this span itself; nothing queued it for decode" if session_frozen else "")
        )

    snapshot = session.snapshot()
    print(f"evidence: session_frozen_span_ids={list(snapshot.pending_span_ids)}")
    print(f"evidence: coordinator_queued_span_ids={queued_ids}")
    print(
        f"verdict: survived {args.frames} frames "
        f"({snapshot.accepted_samples} accepted samples)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
