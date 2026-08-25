#!/usr/bin/env python3
"""Does the DEPLOYED runtime run the rolling witness, and does it land on the selected arm?

Plan §10.5 step 4 wires the 2.5-second base commits into the converger. Steps 1-3 shipped the
three pieces in isolation and each was verified against the grid through a hand-built driver.
This one removes the driver: frames go in at the top of the real service runtime and the arm
comes out of the real session snapshot, with every seam in between owned by production code.

    audio frames -> LiveServiceRuntime.accept_frame
      -> WebRtcSpeechProvider + EndpointPolicy (the deployed configuration)
        -> LiveCoordinator -> InferenceArbiter (canonical AND refinement)
          -> RollingTranscriptConverger -> LiveSession.apply_text_revision
            -> snapshot().effective_transcript -> the grid's own scorer

Zero MOSS requests by construction. The decoder is the production `RunnerBoundedWavInference`
in front of a runner that replays the grid's recorded answers through the production response
validator (`vllm_runner._validate_transcription_response`), so the decode seam -- including M1
salvage -- behaves exactly as it does on the 4070 Ti, and a decode the grid never recorded is a
failure rather than a fresh GPU call. Reviewers can run this with no GPU:

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \\
      prototypes/streaming-diarization/live-convergence/verify_runtime_rolling.py

Every case is run TWICE through the same runtime configuration -- once with no rolling decoder
(the base arm, which is what the service shipped before this change) and once with one -- so
every gate below is a before/after on one instrument rather than a comparison against a number
copied from somewhere else.

Exit 0 iff every gate passes.

- G1 the base arm reproduces the published live trio: per-case WER equals the grid's base
  control to 6 dp and the trio mean equals `.199870` / `.913490`
- G2 the rolling arm reproduces the selected `10/10` arm: per-case WER to 6 dp and the trio
  means `.131861` / `.943916`
- G3 the base path is untouched by rolling: identical frozen spans, identical committed
  transcripts, identical committed-prefix hash in both arms (ADR-0005 D2)
- G4 every case dispatched and applied all six windows, in order, with no refusal, no failed
  window, no stale completion and no admission refusal
- G5 exact sample accounting at stop in both arms, and no terminal failure
- G6 rolling PCM retention never exceeded the plan §6 M2 bound of `2 x window`
- G7 zero fresh MOSS requests
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "prototypes/live-file-gap-context"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import proto_context_arms as bench  # noqa: E402
import verify_session_text_authority as authority  # noqa: E402
import webrtcvad  # noqa: E402
from moss_transcribe_diarize.app.live_adapters import RunnerBoundedWavInference  # noqa: E402
from moss_transcribe_diarize.app.live_endpoint import EndpointPolicy, EndpointPolicyConfig  # noqa: E402
from moss_transcribe_diarize.app.live_identity import (  # noqa: E402
    BoundedCausalIdentityPreparer,
    LiveIdentityConfig,
)
from moss_transcribe_diarize.app.live_provider_bundle import WebRtcSpeechProvider  # noqa: E402
from moss_transcribe_diarize.app.live_service_runtime import (  # noqa: E402
    LiveServiceBounds,
    LiveServiceConfigHashes,
    LiveServiceDescriptor,
    LiveServiceRuntime,
)
from moss_transcribe_diarize.app.live_session import (  # noqa: E402
    AudioFrame,
    UNATTRIBUTED_SPEAKER,
    display_speaker_label,
)
from moss_transcribe_diarize.app.live_transcript_convergence import (  # noqa: E402
    DEFAULT_ROLLING_GEOMETRY,
)
from moss_transcribe_diarize.app.vllm_runner import DEFAULT_PROMPT, _validate_transcription_response  # noqa: E402
from moss_transcribe_diarize.evaluation import Segment  # noqa: E402

SAMPLE_RATE = bench.SAMPLE_RATE
GRID = REPO / "evidence/live-convergence-0824/M2-rolling-grid"
DEPLOYED_MANIFEST = Path.home() / ".local/share/moss-transcribe-diarize/live/live-provider-manifest.json"
SELECTED_ARM = authority.SELECTED_ARM
PLACES = authority.PLACES


class CacheMiss(RuntimeError):
    """The runtime asked for a decode the grid never recorded. No GPU call is made."""


class ReplayRunner:
    """A `VllmRunner` stand-in that answers from the grid's recorded decodes.

    It is keyed on the audio itself -- the sha of the PCM the adapter wrote to its temporary
    WAV, plus the token cap -- because that is all the production adapter hands a runner. The
    recorded raw text then goes through the *production* response validator, so an empty or
    ungrammatical decode raises the same typed `EmptyTranscriptionError` the deployed runner
    raises and the M1 salvage gate sees exactly what it sees in production.
    """

    def __init__(self, entries: dict[tuple[str, int], dict[str, Any]]):
        self.entries = entries
        self.fresh_requests = 0
        self.requests = 0

    def transcribe(self, audio_path, **kwargs: Any):
        self.requests += 1
        pcm = _wav_pcm(Path(audio_path))
        key = (hashlib.sha256(pcm).hexdigest(), int(kwargs["max_new_tokens"]))
        record = self.entries.get(key)
        if record is None:
            self.fresh_requests += 1
            raise CacheMiss(
                f"no recorded decode for {len(pcm) // 2} samples at token cap {key[1]}."
            )
        text = str(record["raw_text"])
        generated_tokens = int(record["generated_tokens"])
        _validate_transcription_response(
            text=text, generated_tokens=generated_tokens, audio_path=audio_path
        )
        return _Result(
            text=text, prompt_len=int(record["prompt_tokens"]), generated_tokens=generated_tokens
        )


class _Result:
    __slots__ = ("text", "prompt_len", "generated_tokens")

    def __init__(self, *, text: str, prompt_len: int, generated_tokens: int):
        self.text = text
        self.prompt_len = prompt_len
        self.generated_tokens = generated_tokens


def _wav_pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as handle:
        return handle.readframes(handle.getnframes())


def load_replay_entries(cache_path: Path, cases: list[str]) -> dict[tuple[str, int], dict[str, Any]]:
    """Index every recorded decode of these cases by (PCM sha, token cap)."""

    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    if payload.get("schema") != "moss-context-arms-decode-cache.v2":
        raise RuntimeError("decode_cache_schema")
    prompt_sha = hashlib.sha256(DEFAULT_PROMPT.encode("utf-8")).hexdigest()[:16]
    audio: dict[str, bytes] = {}
    for case in cases:
        path = bench.CORPUS / case / "audio.wav"
        audio[hashlib.sha256(path.read_bytes()).hexdigest()] = bench.read_pcm(path)
    entries: dict[tuple[str, int], dict[str, Any]] = {}
    for key, record in payload["entries"].items():
        audio_sha, start, end, _model, cap, prompt = key.rsplit(":", 5)[0], *key.split(":")[1:]
        if prompt != prompt_sha:
            continue
        pcm = audio.get(audio_sha)
        if pcm is None:
            continue
        window = pcm[int(start) * 2 : int(end) * 2]
        entries[(hashlib.sha256(window).hexdigest(), int(cap))] = record
    return entries


def deployed_configuration() -> dict[str, Any]:
    """The endpoint, VAD, bounds and decoder capacity the dev service is running."""

    manifest = json.loads(DEPLOYED_MANIFEST.read_text(encoding="utf-8"))
    return {
        "endpoint_config": manifest["endpoint_config"],
        "bounds_config": manifest["bounds_config"],
        "decoder_config": manifest["decoder_config"],
        "speech_provider": manifest["speech_provider"],
        "identity_config": manifest["identity_config"],
    }


def build_runtime(config: dict[str, Any], runner: ReplayRunner, *, rolling: bool):
    """The deployed configuration, with the deployed (threaded) canonical pump.

    The production scheduler is used rather than the tests' manual one because the thing under
    test here is the runtime's own dispatch: a witness is admitted from inside the canonical
    pump and dispatched by it, so a scheduler that only runs when the driver says so would be
    verifying the driver.
    """

    endpoint = config["endpoint_config"]
    bounds = config["bounds_config"]
    speech = config["speech_provider"]
    identity = config["identity_config"]
    descriptor = LiveServiceDescriptor(
        source_revision="0" * 40,
        provider_name="runtime-rolling-verify",
        provider_revision="replay",
        provider_manifest_hash=hashlib.sha256(b"runtime-rolling-verify").hexdigest(),
        config_hashes=LiveServiceConfigHashes.from_parts(
            endpoint_config=endpoint,
            identity_config=identity,
            decoder_config=config["decoder_config"],
        ),
        bounds=LiveServiceBounds(
            max_frame_samples=bounds["max_frame_samples"],
            max_queue_depth=bounds["max_queue_depth"],
            max_retained_samples=bounds["max_retained_samples"],
            max_identity_speakers=bounds["max_identity_speakers"],
            max_events=bounds["max_events"],
            hard_cap_samples=bounds["hard_cap_samples"],
            stop_drain_deadline_seconds=bounds["stop_drain_deadline_seconds"],
        ),
        frame_samples=bounds["frame_samples"],
    )
    runtime = LiveServiceRuntime(
        descriptor=descriptor,
        endpoint_policy_factory=lambda: EndpointPolicy(
            EndpointPolicyConfig(
                min_speech_samples=endpoint["min_speech_samples"],
                min_silence_samples=endpoint["min_silence_samples"],
                pre_speech_padding_samples=endpoint["pre_speech_padding_samples"],
                post_speech_padding_samples=endpoint["post_speech_padding_samples"],
                hard_cap_samples=endpoint["hard_cap_samples"],
            )
        ),
        speech_provider_factory=lambda: WebRtcSpeechProvider(
            vad=webrtcvad.Vad(speech["mode"]), frame_samples=speech["frame_samples"]
        ),
        decoder_factory=lambda: RunnerBoundedWavInference(
            runner, max_samples=config["decoder_config"]["max_samples"]
        ),
        rolling_decoder_factory=(
            (
                lambda: RunnerBoundedWavInference(
                    runner, max_samples=DEFAULT_ROLLING_GEOMETRY.window_samples
                )
            )
            if rolling
            else None
        ),
        identity_preparer_factory=lambda: BoundedCausalIdentityPreparer(
            config=LiveIdentityConfig(
                max_speakers=identity["max_speakers"],
                min_match_score=identity["min_match_score"],
                min_match_margin=identity["min_match_margin"],
            ),
            evidence_provider=None,
        ),
    )
    return runtime


def _label(canonical_speaker: str | None, speakers: tuple[str, ...]) -> str:
    """The `Sxx` a reader is shown, from the album this run actually established.

    Not the baseline's album: this runtime builds its own from live evidence, and a name it
    invented is not a name the baseline's two-speaker list contains.
    """

    if canonical_speaker is None or canonical_speaker not in speakers:
        return UNATTRIBUTED_SPEAKER
    return display_speaker_label(canonical_speaker, speakers)


def run_case(
    config: dict[str, Any],
    runner: ReplayRunner,
    case: str,
    *,
    rolling: bool,
    collect_events: bool = False,
) -> dict[str, Any]:
    """One meeting, frame by frame, through the real runtime; then stop it and read the surface.

    `collect_events` adds the serialized event stream and the serialized service snapshot to
    the answer. Off by default so this verifier's own artifact keeps its shape; step 5's
    event verifier turns it on rather than rebuilding this driver.
    """

    pcm = bench.read_pcm(bench.CORPUS / case / "audio.wav")
    total = len(pcm) // 2
    frame_samples = config["bounds_config"]["frame_samples"]
    runtime = build_runtime(config, runner, rolling=rolling)
    created = runtime.create()
    session_id = created.session_id
    # How far the base may fall behind the audio the driver has handed over. A real client
    # sends one 0.5 s frame every 0.5 s and the base decodes a span at RTF ~0.1, so the
    # committed prefix tracks the accepted one within a span or two; this driver has no GPU
    # to wait for and would otherwise hand over the whole meeting before the pump thread ran
    # once, which is not a condition the deployed service can be in. Two spans is the bound,
    # and it is deliberately far tighter than the converger's own `2 x window` retention
    # bound, so the pacing never decides what the retention bound reports.
    max_base_lag_samples = 2 * config["bounds_config"]["hard_cap_samples"]

    cursor = 0
    sequence = 0
    while cursor < total:
        deadline = time.monotonic() + 30.0
        while True:
            live = runtime.snapshot(session_id).session
            if live.accepted_samples - live.committed_samples <= max_base_lag_samples:
                break
            if time.monotonic() > deadline:
                raise RuntimeError(
                    f"{case}: base fell {live.accepted_samples - live.committed_samples} samples "
                    "behind and never caught up."
                )
            time.sleep(0.001)
        count = min(frame_samples, total - cursor)
        runtime.accept_frame(
            session_id,
            AudioFrame(sequence=sequence, pcm=pcm[cursor * 2 : (cursor + count) * 2], sample_count=count),
        )
        cursor += count
        sequence += 1
    asyncio.run(runtime.stop(session_id, config["bounds_config"]["stop_drain_deadline_seconds"]))

    service = runtime.snapshot(session_id)
    session = service.session
    coordinator = runtime._sessions[session_id].coordinator
    accounting = coordinator.rolling_accounting()
    speakers = tuple(session.identity_snapshot.canonical_speakers)
    hypothesis = bench.normalise(
        [
            Segment(
                item.start_sample / SAMPLE_RATE,
                item.end_sample / SAMPLE_RATE,
                _label(item.canonical_speaker, speakers),
                item.text,
            )
            for item in session.effective_transcript
        ],
        total / SAMPLE_RATE,
    )
    spans = [
        (event.payload["start_sample"], event.payload["end_sample"], event.payload["reason"])
        for event in runtime.events(session_id)
        if event.kind == "span_frozen"
    ]
    collected: dict[str, Any] = {}
    if collect_events:
        collected["events"] = [event.to_dict() for event in runtime.events(session_id)]
        collected["service_snapshot"] = service.to_dict()
    return {
        **collected,
        "scores": bench.score(bench.load_reference(case), hypothesis),
        "terminal_failure": None if service.terminal_failure is None else service.terminal_failure.message,
        "accepted_samples": session.accepted_samples,
        "accounted_samples": session.accounted_samples,
        "committed_samples": session.committed_samples,
        "committed_prefix_hash": session.committed_prefix_hash,
        "committed": [
            [item.start_sample, item.end_sample, item.transcript] for item in session.committed
        ],
        "frozen_spans": spans,
        "text_revision_version": session.text_revision_version,
        "canonical_through_sample": session.canonical_through_sample,
        "finalization_status": session.finalization_status,
        "effective_segments": len(session.effective_transcript),
        "rolling": None
        if accounting is None
        else {
            "status": accounting.status.value,
            "windows_planned": accounting.windows_planned,
            "windows_completed": accounting.windows_completed,
            "windows_failed": accounting.windows_failed,
            "stale_completions": accounting.stale_completions,
            "decoded_audio_samples": accounting.decoded_audio_samples,
            "retained_high_water_samples": accounting.retained_high_water_samples,
            "max_retained_samples": accounting.max_retained_samples,
            "admission_refusals": coordinator._rolling_admission_refusals,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default=",".join(bench.CASES))
    parser.add_argument("--grid", type=Path, default=GRID / "grid.json")
    parser.add_argument("--cache", type=Path, default=GRID / "decode-cache/run0.json")
    parser.add_argument("--output", type=Path, default=None)
    cli = parser.parse_args()

    names = [item for item in cli.cases.split(",") if item]
    grid = json.loads(cli.grid.read_text(encoding="utf-8"))
    rolling_expected = grid["summary"]["arms"][SELECTED_ARM]
    # The grid records the base arm as a trio-level control plus the per-case comparators it
    # reproduced (`baseline_live`), so the base expectation is assembled from both halves.
    base_expected = dict(grid["summary"]["base_control"])
    base_expected["per_case"] = {
        case: {"wer_mean": grid["baseline_live"][case]["wer"]} for case in names
    }
    config = deployed_configuration()
    runner = ReplayRunner(load_replay_entries(cli.cache, names))

    document: dict[str, Any] = {
        "schema": "moss-live-convergence-runtime-rolling.v1",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "modules": [
            "moss_transcribe_diarize/app/live_coordinator.py",
            "moss_transcribe_diarize/app/live_service_runtime.py",
            "moss_transcribe_diarize/app/live_provider_bundle.py",
        ],
        "grid": {
            "path": str(cli.grid.relative_to(REPO)),
            "sha256": hashlib.sha256(cli.grid.read_bytes()).hexdigest(),
            "arm": SELECTED_ARM,
        },
        "deployed_configuration": config,
        "arms": {"base": {}, "rolling": {}},
    }
    for case in names:
        document["arms"]["base"][case] = run_case(config, runner, case, rolling=False)
        document["arms"]["rolling"][case] = run_case(config, runner, case, rolling=True)
    document["decode_cost"] = {"requests": runner.requests, "fresh_requests": runner.fresh_requests}

    failures: list[str] = []

    def close(actual: float, want: float) -> bool:
        return round(float(actual), PLACES) == round(float(want), PLACES)

    for case in names:
        base = document["arms"]["base"][case]
        roll = document["arms"]["rolling"][case]
        if not close(base["scores"]["wer"], base_expected["per_case"][case]["wer_mean"]):
            failures.append(
                f"G1 {case} base wer {base['scores']['wer']:.6f} != grid "
                f"{base_expected['per_case'][case]['wer_mean']:.6f}"
            )
        if not close(roll["scores"]["wer"], rolling_expected["per_case"][case]["wer_mean"]):
            failures.append(
                f"G2 {case} rolling wer {roll['scores']['wer']:.6f} != grid "
                f"{rolling_expected['per_case'][case]['wer_mean']:.6f}"
            )
        if base["frozen_spans"] != roll["frozen_spans"]:
            failures.append(f"G3 {case} rolling changed the frozen span grid")
        if base["committed"] != roll["committed"]:
            failures.append(f"G3 {case} rolling changed a committed base transcript")
        if base["committed_prefix_hash"] != roll["committed_prefix_hash"]:
            failures.append(f"G3 {case} rolling moved the committed prefix hash")
        rolling_state = roll["rolling"]
        if rolling_state is None:
            failures.append(f"G4 {case} ran without a converger")
        else:
            expected_windows = rolling_expected["windows_per_case"]
            if (
                rolling_state["windows_completed"] != expected_windows
                or rolling_state["windows_planned"] != expected_windows
                or roll["text_revision_version"] != expected_windows
            ):
                failures.append(
                    f"G4 {case} planned {rolling_state['windows_planned']} / completed "
                    f"{rolling_state['windows_completed']} / applied "
                    f"{roll['text_revision_version']} of {expected_windows} windows"
                )
            if (
                rolling_state["windows_failed"]
                or rolling_state["stale_completions"]
                or rolling_state["admission_refusals"]
            ):
                failures.append(
                    f"G4 {case} failed={rolling_state['windows_failed']} "
                    f"stale={rolling_state['stale_completions']} "
                    f"refused={rolling_state['admission_refusals']}"
                )
            if rolling_state["retained_high_water_samples"] > rolling_state["max_retained_samples"]:
                failures.append(
                    f"G6 {case} retained {rolling_state['retained_high_water_samples']} samples, "
                    f"bound is {rolling_state['max_retained_samples']}"
                )
        for arm_name, arm in (("base", base), ("rolling", roll)):
            if arm["terminal_failure"] is not None:
                failures.append(f"G5 {case} {arm_name} ended terminal: {arm['terminal_failure']}")
            if arm["accepted_samples"] != arm["accounted_samples"]:
                failures.append(
                    f"G5 {case} {arm_name} accepted {arm['accepted_samples']} != accounted "
                    f"{arm['accounted_samples']}"
                )

    for label, expected, key in (("G1", base_expected, "base"), ("G2", rolling_expected, "rolling")):
        arm = document["arms"][key]
        mean_wer = sum(arm[case]["scores"]["wer"] for case in names) / len(names)
        mean_recall = sum(arm[case]["scores"]["content_recall"] for case in names) / len(names)
        document.setdefault("trio", {})[key] = {
            "wer_mean": mean_wer,
            "content_recall_mean": mean_recall,
        }
        if len(names) == len(bench.CASES):
            if not close(mean_wer, expected["wer"]["mean"]):
                failures.append(
                    f"{label} trio {key} wer {mean_wer:.6f} != grid {expected['wer']['mean']:.6f}"
                )
            if not close(mean_recall, expected["content_recall"]["mean"]):
                failures.append(
                    f"{label} trio {key} recall {mean_recall:.6f} != grid "
                    f"{expected['content_recall']['mean']:.6f}"
                )

    if document["decode_cost"]["fresh_requests"]:
        failures.append(f"G7 {document['decode_cost']['fresh_requests']} fresh MOSS requests")

    document["failures"] = failures
    document["passed"] = not failures

    for case in names:
        base = document["arms"]["base"][case]
        roll = document["arms"]["rolling"][case]
        state = roll["rolling"] or {}
        print(
            f"{case:<18} base_wer={base['scores']['wer']:.6f} "
            f"(grid {base_expected['per_case'][case]['wer_mean']:.6f}) "
            f"rolling_wer={roll['scores']['wer']:.6f} "
            f"(grid {rolling_expected['per_case'][case]['wer_mean']:.6f}) "
            f"windows={state.get('windows_completed')} revisions={roll['text_revision_version']} "
            f"status={state.get('status')} pcm_high_water={state.get('retained_high_water_samples')}"
        )
    for key, expected in (("base", base_expected), ("rolling", rolling_expected)):
        trio = document["trio"][key]
        print(
            f"{'TRIO ' + key:<18} wer={trio['wer_mean']:.6f} (grid {expected['wer']['mean']:.6f}) "
            f"recall={trio['content_recall_mean']:.6f} "
            f"(grid {expected['content_recall']['mean']:.6f})"
        )
    print(f"decode cost: {document['decode_cost']}")
    if cli.output:
        cli.output.parent.mkdir(parents=True, exist_ok=True)
        cli.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for failure in failures:
        print(f"FAIL {failure}")
    print("PASS" if not failures else f"FAILED {len(failures)} gate(s)")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
