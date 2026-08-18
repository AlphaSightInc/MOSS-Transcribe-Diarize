#!/usr/bin/env python3
"""Measure one live WebRTC VAD frame's canonical-span demand.

Question: can a VAD pattern at the provider's real observation granularity emit
more spans than treating the whole client frame as one speech observation?
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path

from moss_transcribe_diarize.app.live_coordinator import LiveCoordinator
from moss_transcribe_diarize.app.live_endpoint import EndpointPolicy, EndpointPolicyConfig, SpeechObservation
from moss_transcribe_diarize.app.live_provider_bundle import WebRtcSpeechProvider
from moss_transcribe_diarize.app.live_session import AudioFrame, LiveSession


class PatternVad:
    def __init__(self, pattern: str) -> None:
        self._pattern = tuple(bit == "1" for bit in pattern)
        self._index = 0

    def is_speech(self, pcm: bytes, sample_rate: int) -> bool:
        del pcm
        if sample_rate != 16_000:
            raise ValueError("the production WebRTC adapter requires 16 kHz audio")
        result = self._pattern[self._index % len(self._pattern)]
        self._index += 1
        return result


def positive(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def bits(value: str) -> str:
    if not value or any(bit not in "01" for bit in value):
        raise argparse.ArgumentTypeError("must be a non-empty sequence of 0 and 1")
    return value


def measure(args: argparse.Namespace, pattern: str) -> dict[str, object]:
    provider = WebRtcSpeechProvider(vad=PatternVad(pattern), frame_samples=args.vad_frame_samples)
    policy = EndpointPolicy(
        EndpointPolicyConfig(
            min_speech_samples=args.min_speech_samples,
            min_silence_samples=args.min_silence_samples,
            pre_speech_padding_samples=args.pre_speech_padding_samples,
            post_speech_padding_samples=args.post_speech_padding_samples,
            hard_cap_samples=args.hard_cap_samples,
        )
    )
    frame = AudioFrame(
        sequence=0,
        pcm=b"\x01\x00" * args.frame_samples,
        sample_count=args.frame_samples,
    )
    observations = provider.observe(frame=frame, start_sample=0, end_sample=args.frame_samples)
    spans = tuple(span for observation in observations for span in policy.observe(observation))
    tail = policy.stop()
    return {
        "pattern": pattern,
        "observations": [
            {
                "start_sample": observation.start_sample,
                "end_sample": observation.end_sample,
                "speech_present": observation.speech_present,
            }
            for observation in observations
        ],
        "span_count": len(spans),
        "span_reasons": dict(sorted(Counter(span.reason for span in spans).items())),
        "spans": [
            {
                "start_sample": span.start_sample,
                "end_sample": span.end_sample,
                "reason": span.reason,
            }
            for span in spans
        ],
        "stop_tail_count": len(tail),
        "stop_tail": [
            {
                "start_sample": span.start_sample,
                "end_sample": span.end_sample,
                "reason": span.reason,
            }
            for span in tail
        ],
        "required_queue_depth": max(len(spans), len(tail)),
    }


def _policy_state(policy: EndpointPolicy, *, at_sample: int) -> tuple[object, ...]:
    """Return every mutable endpoint field which can affect later observations.

    Every search layer has the same accepted sample position, so positions are
    recorded relative to that layer.  Equal keys therefore have identical
    future behavior; retaining only the route with the most emitted spans is
    an exhaustive dynamic-programming reduction, not a sampled search.
    """

    def relative(value: int | None) -> int | None:
        return None if value is None else value - at_sample

    snapshot = policy.snapshot()
    # Once speech is active, EndpointPolicy never reads either candidate field
    # again: `_observe_speech` skips its activation branch and every reset
    # clears both fields before a later activation can inspect them.  Keeping
    # stale candidate history in the key therefore splits future-equivalent
    # reachable states.  Canonicalize it here, while leaving the production
    # policy itself untouched.  Conversely, an inactive policy has no last
    # speech end after `_reset_speech_state`, so that value cannot distinguish
    # its future behavior either.  For an inactive candidate, duration equals
    # accepted-until minus candidate start, so its relative start determines
    # its duration; do not retain that duplicate coordinate in every key.
    if snapshot.speech_active:
        candidate_start = None
        last_speech_end = relative(policy._last_speech_end)
    else:
        candidate_start = relative(policy._speech_candidate_start)
        expected_candidate_samples = 0 if candidate_start is None else -candidate_start
        if policy._speech_candidate_samples != expected_candidate_samples:
            raise AssertionError("EndpointPolicy candidate duration is not derivable from its start.")
        last_speech_end = None
    return (
        relative(snapshot.open_start_sample),
        snapshot.speech_active,
        candidate_start,
        last_speech_end,
        snapshot.stopped,
    )


def _new_policy(args: argparse.Namespace) -> EndpointPolicy:
    return EndpointPolicy(
        EndpointPolicyConfig(
            min_speech_samples=args.min_speech_samples,
            min_silence_samples=args.min_silence_samples,
            pre_speech_padding_samples=args.pre_speech_padding_samples,
            post_speech_padding_samples=args.post_speech_padding_samples,
            hard_cap_samples=args.hard_cap_samples,
        )
    )


def _observe(policy: EndpointPolicy, *, sample_count: int, speech_present: bool) -> tuple[object, ...]:
    """Run one abstract provider observation at the policy's next accepted sample."""

    if sample_count <= 0:
        return ()
    start_sample = policy.snapshot().accepted_until_sample
    return policy.observe(
        SpeechObservation(
            start_sample=start_sample,
            end_sample=start_sample + sample_count,
            speech_present=speech_present,
        )
    )


def _copy_policy(policy: EndpointPolicy) -> EndpointPolicy:
    """Copy the real policy's seven mutable scalar fields without generic deepcopy overhead."""

    copy = EndpointPolicy(policy.config)
    copy._accepted_until = policy._accepted_until
    copy._open_start = policy._open_start
    copy._speech_candidate_start = policy._speech_candidate_start
    copy._speech_candidate_samples = policy._speech_candidate_samples
    copy._speech_active = policy._speech_active
    copy._last_speech_end = policy._last_speech_end
    copy._stopped = policy._stopped
    return copy


def _write_json_snapshot(path: Path, payload: dict[str, object]) -> None:
    """Atomically publish the latest bounded search state for interrupted runs."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.tmp")
    temporary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary_path.replace(path)


def _history_horizon(args: argparse.Namespace) -> int:
    """Return the bounded number of VAD decisions needed to rebuild a state."""

    if args.hard_cap_samples is None:
        raise AssertionError("reachable-state history requires the configured hard cap.")
    return -(-args.hard_cap_samples // args.vad_frame_samples) + 2


def _history_symbol_width(vad_frame_samples: int) -> int:
    """Return bits needed for one `(carried_samples, decision)` history entry."""

    return max(1, (vad_frame_samples * 2 - 1).bit_length())


def _append_packed_history(
    history: int,
    *,
    carried_samples: int,
    decision: bool,
    symbol_width: int,
) -> int:
    """Losslessly append one reachable VAD split/decision history entry."""

    return (history << symbol_width) | ((carried_samples << 1) | int(decision))


def _decode_packed_history(
    history: int,
    *,
    entry_count: int,
    symbol_width: int,
) -> tuple[tuple[int, bool], ...]:
    """Recover the one witness history needed for the final production replay."""

    mask = (1 << symbol_width) - 1
    decoded: list[tuple[int, bool]] = []
    for _ in range(entry_count):
        symbol = history & mask
        decoded.append((symbol >> 1, bool(symbol & 1)))
        history >>= symbol_width
    return tuple(reversed(decoded))


def _policy_from_relative_state(args: argparse.Namespace, state: tuple[object, ...]) -> EndpointPolicy:
    """Materialize a translated policy state for a cached real-policy transition."""

    if args.hard_cap_samples is None:
        raise AssertionError("relative state materialization requires a hard cap.")
    open_start, speech_active, candidate_start, last_speech_end, stopped = state
    anchor = args.hard_cap_samples
    policy = _new_policy(args)
    policy._accepted_until = anchor
    policy._open_start = anchor + int(open_start)
    policy._speech_active = bool(speech_active)
    policy._speech_candidate_start = None if candidate_start is None else anchor + int(candidate_start)
    policy._speech_candidate_samples = 0 if candidate_start is None else -int(candidate_start)
    policy._last_speech_end = None if last_speech_end is None else anchor + int(last_speech_end)
    policy._stopped = bool(stopped)
    return policy


class PolicyTransitionCache:
    """Cache translated transitions while still executing EndpointPolicy itself.

    The all-history search re-visits the same compact endpoint state through
    many VAD split histories.  Keeping the state as a relative tuple avoids
    deep-copying full policy objects on every edge; a cache miss materializes
    that tuple and calls the production policy implementation.
    """

    def __init__(self, args: argparse.Namespace) -> None:
        self._args = args
        self._transitions: dict[tuple[tuple[object, ...], int, bool], tuple[tuple[object, ...], int]] = {}
        self._stop_tails: dict[tuple[object, ...], int] = {}

    def observe(
        self,
        state: tuple[object, ...],
        *,
        sample_count: int,
        speech_present: bool,
    ) -> tuple[tuple[object, ...], int]:
        key = (state, sample_count, speech_present)
        cached = self._transitions.get(key)
        if cached is not None:
            return cached
        policy = _policy_from_relative_state(self._args, state)
        emitted = _observe(policy, sample_count=sample_count, speech_present=speech_present)
        result = (
            _policy_state(policy, at_sample=policy.snapshot().accepted_until_sample),
            len(emitted),
        )
        self._transitions[key] = result
        return result

    def stop_tail_count(self, state: tuple[object, ...]) -> int:
        cached = self._stop_tails.get(state)
        if cached is not None:
            return cached
        count = len(_policy_from_relative_state(self._args, state).stop())
        self._stop_tails[state] = count
        return count

    def statistics(self) -> dict[str, int]:
        """Expose bounded cache counts without serializing any policy state."""

        return {
            "cached_observe_transitions": len(self._transitions),
            "cached_stop_tails": len(self._stop_tails),
        }


def _fresh_provider_observations(args: argparse.Namespace) -> tuple[object, ...]:
    """Ask the production adapter for the exact fresh-session observation grid."""

    provider = WebRtcSpeechProvider(vad=PatternVad("0"), frame_samples=args.vad_frame_samples)
    frame = AudioFrame(
        sequence=0,
        pcm=b"\x01\x00" * args.frame_samples,
        sample_count=args.frame_samples,
    )
    return provider.observe(frame=frame, start_sample=0, end_sample=args.frame_samples)


def measure_worst_case(args: argparse.Namespace) -> dict[str, object]:
    """Exhaustively maximize one fresh WebRTC frame without enumerating 2**N strings.

    The live adapter produces one binary decision for every complete VAD
    chunk.  `EndpointPolicy` is run for both values of each decision.  States
    with identical future behavior are merged after retaining the route that
    emitted the most spans, so this evaluates every VAD sequence exactly even
    when a client frame contains hundreds of VAD chunks.
    """

    observations = _fresh_provider_observations(args)
    decision_observations = tuple(item for item in observations if item.confidence is not None)
    tail_observations = tuple(item for item in observations if item.confidence is None)
    if len(tail_observations) > 1:
        raise AssertionError("WebRTC adapter returned more than one carried observation.")

    policy = EndpointPolicy(
        EndpointPolicyConfig(
            min_speech_samples=args.min_speech_samples,
            min_silence_samples=args.min_silence_samples,
            pre_speech_padding_samples=args.pre_speech_padding_samples,
            post_speech_padding_samples=args.post_speech_padding_samples,
            hard_cap_samples=args.hard_cap_samples,
        )
    )
    # (endpoint state, preceding VAD decision) -> (span count, witness, policy)
    # The preceding decision is only relevant to the adapter's possible carried
    # tail, whose answer deliberately repeats the last complete VAD decision.
    states: dict[tuple[tuple[object, ...], bool], tuple[int, str, EndpointPolicy]] = {
        (_policy_state(policy, at_sample=0), False): (0, "", policy)
    }
    layers: list[dict[str, int]] = []
    for index, observation in enumerate(decision_observations, start=1):
        next_states: dict[tuple[tuple[object, ...], bool], tuple[int, str, EndpointPolicy]] = {}
        for (_, _), (span_count, witness, prior_policy) in states.items():
            for speech_present, bit in ((False, "0"), (True, "1")):
                candidate = deepcopy(prior_policy)
                emitted = candidate.observe(
                    SpeechObservation(
                        start_sample=observation.start_sample,
                        end_sample=observation.end_sample,
                        speech_present=speech_present,
                    )
                )
                key = (_policy_state(candidate, at_sample=observation.end_sample), speech_present)
                proposal = (span_count + len(emitted), witness + bit, candidate)
                existing = next_states.get(key)
                if existing is None or proposal[0] > existing[0]:
                    next_states[key] = proposal
        states = next_states
        layers.append(
            {
                "completed_vad_decisions": index,
                "equivalent_endpoint_states": len(states),
                "max_frame_spans_so_far": max(item[0] for item in states.values()),
            }
        )

    for observation in tail_observations:
        next_states = {}
        for (_, last_decision), (span_count, witness, prior_policy) in states.items():
            candidate = deepcopy(prior_policy)
            emitted = candidate.observe(
                SpeechObservation(
                    start_sample=observation.start_sample,
                    end_sample=observation.end_sample,
                    speech_present=last_decision,
                )
            )
            key = (_policy_state(candidate, at_sample=observation.end_sample), last_decision)
            proposal = (span_count + len(emitted), witness, candidate)
            existing = next_states.get(key)
            if existing is None or proposal[0] > existing[0]:
                next_states[key] = proposal
        states = next_states

    candidates = []
    for (_, _), (span_count, witness, candidate_policy) in states.items():
        stop_tail = candidate_policy.stop()
        candidates.append((max(span_count, len(stop_tail)), span_count, len(stop_tail), witness))
    required_queue_depth, frame_span_count, stop_tail_count, witness = max(candidates)
    verification = measure(args, witness)
    if verification["span_count"] != frame_span_count or verification["stop_tail_count"] != stop_tail_count:
        raise AssertionError("production WebRTC replay did not reproduce the dynamic-programming witness.")

    return {
        "method": "exact dynamic program over production EndpointPolicy states",
        "fresh_provider_observations": [
            {
                "start_sample": item.start_sample,
                "end_sample": item.end_sample,
                "is_vad_decision": item.confidence is not None,
                "carried_answer_repeats_previous_vad_decision": item.confidence is None,
            }
            for item in observations
        ],
        "vad_decision_count": len(decision_observations),
        "symbolic_patterns_evaluated": f"2^{len(decision_observations)}",
        "state_layers": layers,
        "terminal_equivalent_endpoint_states": len(states),
        "maximum_frame_span_count": frame_span_count,
        "maximum_stop_tail_count": stop_tail_count,
        "required_queue_depth": required_queue_depth,
        "witness_vad_pattern": witness,
        "production_adapter_replay": verification,
    }


def _reachable_boundary_states(
    args: argparse.Namespace,
) -> tuple[dict[tuple[tuple[object, ...], bool], int], list[dict[str, int]]]:
    """Exactly enumerate policy states at a completed WebRTC VAD-frame boundary.

    A client may split a 10 ms VAD frame at any sample.  Before that VAD frame
    completes, the adapter reports the preceding VAD decision; the final piece
    reports the new one.  Splitting either same-valued piece further cannot
    change EndpointPolicy's state, so one split length and the new Boolean
    VAD decision describe every distinct provider transition.  A hard cap
    bounds the policy's retained state, making the fixed point finite.
    """

    vad_frame_samples = args.vad_frame_samples
    policy = _new_policy(args)
    initial_key = (_policy_state(policy, at_sample=0), False)
    transition = PolicyTransitionCache(args)
    states: dict[tuple[tuple[object, ...], bool], int] = {initial_key: 0}
    layers: list[dict[str, int]] = []

    # EndpointPolicy retains no observation before its current open partition,
    # whose hard cap is strictly less than `hard_cap_samples`.  At a VAD-frame
    # boundary that means the next state can depend on at most ceil(cap / VAD)
    # prior VAD frames, plus one preceding decision for a split frame.  Starting
    # from the initial silent carried answer, one additional frame supplies both
    # possible preceding decisions, so this horizon contains every reachable
    # state without an unbounded fixed-point walk.
    history_horizon = _history_horizon(args)
    history_symbol_width = _history_symbol_width(vad_frame_samples)
    for completed_vad_frames in range(1, history_horizon + 1):
        # `undecided` has observed the old VAD answer for this source VAD
        # frame so far.  At every sample it can either remain old, or choose
        # the new answer and continue with that answer to the VAD boundary.
        # Advancing one sample at a time lets equivalent intermediate policy
        # states merge before the remaining split positions are explored.
        undecided = dict(states)
        decided: dict[tuple[tuple[object, ...], bool], int] = {}
        for carried_samples in range(vad_frame_samples):
            next_undecided: dict[tuple[tuple[object, ...], bool], int] = {}
            next_decided: dict[tuple[tuple[object, ...], bool], int] = {}
            for (prior_state, prior_decision), history in undecided.items():
                for decision in (False, True):
                    candidate, _ = transition.observe(
                        prior_state,
                        sample_count=1,
                        speech_present=decision,
                    )
                    key = (candidate, decision)
                    proposal = _append_packed_history(
                        history,
                        carried_samples=carried_samples,
                        decision=decision,
                        symbol_width=history_symbol_width,
                    )
                    existing = next_decided.get(key)
                    if existing is None:
                        next_decided[key] = proposal
                if carried_samples + 1 < vad_frame_samples:
                    candidate, _ = transition.observe(
                        prior_state,
                        sample_count=1,
                        speech_present=prior_decision,
                    )
                    key = (candidate, prior_decision)
                    proposal = history
                    existing = next_undecided.get(key)
                    if existing is None:
                        next_undecided[key] = proposal
            for (prior_state, decision), history in decided.items():
                candidate, _ = transition.observe(
                    prior_state,
                    sample_count=1,
                    speech_present=decision,
                )
                key = (candidate, decision)
                proposal = history
                existing = next_decided.get(key)
                if existing is None:
                    next_decided[key] = proposal
            undecided = next_undecided
            decided = next_decided
            if (
                args.reachable_progress_output is not None
                and (carried_samples + 1) % args.reachable_progress_every_samples == 0
            ):
                _write_json_snapshot(
                    args.reachable_progress_output,
                    {
                        "status": "in_progress",
                        "method": "sample-at-a-time reachable-state dynamic program",
                        "history_horizon_vad_frames": history_horizon,
                        "last_completed_vad_frames": completed_vad_frames - 1,
                        "current_vad_frame": completed_vad_frames,
                        "current_vad_frame_samples": carried_samples + 1,
                        "state_counts": {
                            "boundary": len(states),
                            "undecided": len(undecided),
                            "decided": len(decided),
                        },
                        "transition_cache": transition.statistics(),
                    },
                )
        next_states = decided
        layers.append(
            {
                "completed_vad_frames": completed_vad_frames,
                "reachable_equivalent_states": len(next_states),
            }
        )
        states = next_states
        if args.reachable_progress_output is not None:
            _write_json_snapshot(
                args.reachable_progress_output,
                {
                    "status": (
                        "reachable_boundary_complete"
                        if completed_vad_frames == history_horizon
                        else "in_progress"
                    ),
                    "method": "sample-at-a-time reachable-state dynamic program",
                    "history_horizon_vad_frames": history_horizon,
                    "last_completed_vad_frames": completed_vad_frames,
                    "current_vad_frame": None,
                    "current_vad_frame_samples": 0,
                    "state_counts": {
                        "boundary": len(states),
                        "undecided": 0,
                        "decided": len(states),
                    },
                    "transition_cache": transition.statistics(),
                },
            )
    return states, layers


def _target_piece_plan(
    *,
    frame_samples: int,
    vad_frame_samples: int,
    initial_carried_samples: int,
) -> tuple[tuple[int, bool], ...]:
    """Return (sample count, needs a new VAD decision) for one client frame."""

    remaining = frame_samples
    pieces: list[tuple[int, bool]] = []
    if initial_carried_samples:
        needed = vad_frame_samples - initial_carried_samples
        piece = min(needed, remaining)
        pieces.append((piece, piece == needed))
        remaining -= piece
        if remaining == 0:
            return tuple(pieces)
    while remaining >= vad_frame_samples:
        pieces.append((vad_frame_samples, True))
        remaining -= vad_frame_samples
    if remaining:
        pieces.append((remaining, False))
    return tuple(pieces)


def _replay_reachable_witness(
    args: argparse.Namespace,
    *,
    history: tuple[tuple[int, bool], ...],
    initial_carried_samples: int,
    target_pattern: str,
) -> dict[str, object]:
    """Rebuild the reachable state with real adapter calls, then call preview."""

    history_pattern = "".join("1" if decision else "0" for _, decision in history)
    provider = WebRtcSpeechProvider(
        vad=PatternVad(history_pattern + target_pattern),
        frame_samples=args.vad_frame_samples,
    )
    policy = _new_policy(args)
    session = LiveSession(
        max_retained_samples=(len(history) + 2) * args.vad_frame_samples + args.frame_samples,
    )
    sequence = 0

    def feed(sample_count: int) -> tuple[object, ...]:
        nonlocal sequence
        frame = AudioFrame(
            sequence=sequence,
            pcm=b"\x01\x00" * sample_count,
            sample_count=sample_count,
        )
        session.accept_frame(frame)
        start_sample = policy.snapshot().accepted_until_sample
        observations = provider.observe(
            frame=frame,
            start_sample=start_sample,
            end_sample=start_sample + sample_count,
        )
        spans = tuple(span for observation in observations for span in policy.observe(observation))
        sequence += 1
        return spans

    for carried_samples, _ in history:
        if carried_samples:
            feed(carried_samples)
        feed(args.vad_frame_samples - carried_samples)
    if initial_carried_samples:
        feed(initial_carried_samples)

    target = AudioFrame(
        sequence=sequence,
        pcm=b"\x01\x00" * args.frame_samples,
        sample_count=args.frame_samples,
    )
    coordinator = LiveCoordinator(
        session_key="queue-depth-floor-probe",
        session=session,
        endpoint_policy=policy,
        speech_provider=provider,
        decoder=None,
        identity_preparer=None,
        arbiter=None,
    )
    preview_count = coordinator.preview_frame_work_items(target)
    return {
        "history_vad_frames": len(history),
        "history_vad_pattern": history_pattern,
        "history_frame_splits": [
            {"carried_samples": carried_samples, "new_vad_decision": decision}
            for carried_samples, decision in history
        ],
        "initial_carried_samples": initial_carried_samples,
        "target_vad_pattern": target_pattern,
        "production_preview_frame_work_items": preview_count,
    }


def measure_reachable_worst_case(args: argparse.Namespace) -> dict[str, object]:
    """Maximize one frame over every reachable policy and WebRTC carry state.

    The initial fresh-policy search is insufficient because a mixer can emit an
    arbitrary positive number of samples (up to its configured maximum), so
    the next client frame may start inside a WebRTC VAD frame.  This search
    first reaches the exact fixed point of every such provider/policy state,
    then runs the same binary-decision dynamic program through the configured
    client frame.  State merging is valid only when the endpoint state, VAD
    carry length, and last VAD decision all agree.
    """

    if args.hard_cap_samples is None:
        raise AssertionError("reachable-state search requires the configured hard cap.")
    boundary_states, reachability_layers = _reachable_boundary_states(args)
    transition = PolicyTransitionCache(args)
    by_carry: dict[
        int,
        dict[
            tuple[tuple[object, ...], bool],
            int,
        ],
    ] = {}
    for (policy, prior_decision), history in boundary_states.items():
        for carried_samples in range(args.vad_frame_samples):
            candidate, _ = transition.observe(
                policy,
                sample_count=carried_samples,
                speech_present=prior_decision,
            )
            key = (candidate, prior_decision)
            states = by_carry.setdefault(carried_samples, {})
            existing = states.get(key)
            if existing is None:
                states[key] = history

    maximum: tuple[int, int, int, int, int, str] | None = None
    target_layers: list[dict[str, int]] = []
    for carried_samples, starting_states in sorted(by_carry.items()):
        states: dict[
            tuple[tuple[object, ...], bool],
            tuple[int, int, str],
        ] = {
            key: (0, history, "") for key, history in starting_states.items()
        }
        for piece_samples, needs_decision in _target_piece_plan(
            frame_samples=args.frame_samples,
            vad_frame_samples=args.vad_frame_samples,
            initial_carried_samples=carried_samples,
        ):
            next_states: dict[
                tuple[tuple[object, ...], bool],
                tuple[int, int, str],
            ] = {}
            for (prior_policy, prior_decision), (span_count, history, pattern) in states.items():
                options = ((False, "0"), (True, "1")) if needs_decision else ((prior_decision, ""),)
                for decision, bit in options:
                    candidate, emitted = transition.observe(
                        prior_policy,
                        sample_count=piece_samples,
                        speech_present=decision,
                    )
                    key = (candidate, decision)
                    current_pattern = pattern + bit
                    proposal = (
                        span_count + emitted,
                        history,
                        current_pattern,
                    )
                    existing = next_states.get(key)
                    if existing is None or proposal[0] > existing[0]:
                        next_states[key] = proposal
            states = next_states
        target_layers.append(
            {
                "initial_carried_samples": carried_samples,
                "terminal_equivalent_states": len(states),
                "maximum_frame_spans": max(item[0] for item in states.values()),
            }
        )
        for (policy, _), (frame_span_count, history, pattern) in states.items():
            stop_tail_count = transition.stop_tail_count(policy)
            candidate = (
                max(frame_span_count, stop_tail_count),
                frame_span_count,
                stop_tail_count,
                history,
                carried_samples,
                pattern,
            )
            if maximum is None or candidate[:3] > maximum[:3]:
                maximum = candidate

    assert maximum is not None
    required_queue_depth, frame_span_count, stop_tail_count, packed_history, carried_samples, pattern = maximum
    replay = _replay_reachable_witness(
        args,
        history=_decode_packed_history(
            packed_history,
            entry_count=_history_horizon(args),
            symbol_width=_history_symbol_width(args.vad_frame_samples),
        ),
        initial_carried_samples=carried_samples,
        target_pattern=pattern,
    )
    if replay["production_preview_frame_work_items"] != frame_span_count:
        raise AssertionError("production preview_frame_work_items did not reproduce the reachable-state witness.")
    return {
        "method": "exact reachable-state dynamic program over production EndpointPolicy semantics",
        "reachability": {
            "boundary_equivalent_states": len(boundary_states),
            "layers": reachability_layers,
            "pre_frame_equivalent_states_by_carry": {
                str(carried_samples): len(states) for carried_samples, states in sorted(by_carry.items())
            },
        },
        "maximum_frame_span_count": frame_span_count,
        "maximum_stop_tail_count": stop_tail_count,
        "required_queue_depth": required_queue_depth,
        "witness": replay,
        "target_layers": target_layers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frame-samples", type=positive, required=True)
    parser.add_argument("--vad-frame-samples", type=positive, required=True)
    parser.add_argument("--min-speech-samples", type=int, required=True)
    parser.add_argument("--min-silence-samples", type=int, required=True)
    parser.add_argument("--pre-speech-padding-samples", type=int, default=0)
    parser.add_argument("--post-speech-padding-samples", type=int, default=0)
    parser.add_argument("--hard-cap-samples", type=positive, required=True)
    parser.add_argument("--pattern", type=bits, action="append", default=[])
    parser.add_argument(
        "--search-worst-case",
        action="store_true",
        help="exactly maximize all VAD decision sequences for this fresh WebRTC frame",
    )
    parser.add_argument(
        "--search-reachable-worst-case",
        action="store_true",
        help="exactly maximize one frame over every reachable WebRTC carry and endpoint state",
    )
    parser.add_argument(
        "--reachable-progress-output",
        type=Path,
        help="atomically overwrite this JSON snapshot while the reachable-state search runs",
    )
    parser.add_argument(
        "--reachable-progress-every-samples",
        type=positive,
        default=16,
        help="publish reachable-state counts after this many sample transitions (default: 16)",
    )
    parser.add_argument("--json-output", type=Path, required=True)
    args = parser.parse_args()

    result = {
        "question": "Does real WebRTC VAD observation granularity change one-frame queue demand?",
        "endpoint_config": {
            "min_speech_samples": args.min_speech_samples,
            "min_silence_samples": args.min_silence_samples,
            "pre_speech_padding_samples": args.pre_speech_padding_samples,
            "post_speech_padding_samples": args.post_speech_padding_samples,
            "hard_cap_samples": args.hard_cap_samples,
        },
        "frame_samples": args.frame_samples,
        "vad_frame_samples": args.vad_frame_samples,
        "patterns": [measure(args, pattern) for pattern in args.pattern],
    }
    if args.search_worst_case:
        result["worst_case_search"] = measure_worst_case(args)
    if args.search_reachable_worst_case:
        result["reachable_worst_case_search"] = measure_reachable_worst_case(args)
    elif not args.pattern and not args.search_worst_case:
        parser.error("provide --pattern, --search-worst-case, or --search-reachable-worst-case")
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
