#!/usr/bin/env python3
"""Measure whether candidate duration is redundant in reachable-policy keys.

Question: for the production ``EndpointPolicy``, can a reachable-state search
derive an inactive speech candidate's accumulated duration from its candidate
start and the current accepted position, rather than retaining both values?

The production policy is not changed here.  This prototype executes it for
every cache miss in two otherwise-identical sample-at-a-time searches, then
compares all terminal policy keys and retained witness histories.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import TypeAlias


ROOT = Path(__file__).resolve().parents[3]
PROBE_PATH = ROOT / "evidence/phase1/y5-guardrail-and-floor/probe_queue_depth_floor.py"


def _load_probe() -> ModuleType:
    spec = importlib.util.spec_from_file_location("queue_depth_floor_probe", PROBE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load probe from {PROBE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


probe = _load_probe()
PolicyState: TypeAlias = tuple[object, ...]
ReducedPolicyState: TypeAlias = tuple[object, ...]
SearchKey: TypeAlias = tuple[ReducedPolicyState, bool]


def _reduced_key(full_key: PolicyState) -> ReducedPolicyState:
    """Drop only the duration that the real policy state already implies."""

    open_start, speech_active, candidate_start, candidate_samples, last_speech_end, stopped = full_key
    expected_samples = 0 if candidate_start is None else -int(candidate_start)
    if candidate_samples != expected_samples:
        raise AssertionError(
            "candidate duration is not derivable from candidate start: "
            f"start={candidate_start!r}, duration={candidate_samples!r}, expected={expected_samples!r}"
        )
    return (open_start, speech_active, candidate_start, last_speech_end, stopped)


def _policy_from_reduced_state(args: object, state: ReducedPolicyState) -> object:
    """Materialize the omitted duration before calling production policy code."""

    open_start, speech_active, candidate_start, last_speech_end, stopped = state
    anchor = args.hard_cap_samples
    policy = probe._new_policy(args)
    policy._accepted_until = anchor
    policy._open_start = anchor + int(open_start)
    policy._speech_active = bool(speech_active)
    policy._speech_candidate_start = None if candidate_start is None else anchor + int(candidate_start)
    policy._speech_candidate_samples = 0 if candidate_start is None else -int(candidate_start)
    policy._last_speech_end = None if last_speech_end is None else anchor + int(last_speech_end)
    policy._stopped = bool(stopped)
    return policy


class _ReducedTransitionCache:
    """Use the real policy while caching on the candidate-duration-free key."""

    def __init__(self, args: object) -> None:
        self._args = args
        self._transitions: dict[tuple[ReducedPolicyState, int, bool], tuple[ReducedPolicyState, int]] = {}

    def observe(
        self,
        state: ReducedPolicyState,
        *,
        sample_count: int,
        speech_present: bool,
    ) -> tuple[ReducedPolicyState, int]:
        key = (state, sample_count, speech_present)
        cached = self._transitions.get(key)
        if cached is not None:
            return cached
        policy = _policy_from_reduced_state(self._args, state)
        emitted = probe._observe(policy, sample_count=sample_count, speech_present=speech_present)
        result = (
            _reduced_key(probe._policy_state(policy, at_sample=policy.snapshot().accepted_until_sample)),
            len(emitted),
        )
        self._transitions[key] = result
        return result


def _reduced_boundary_states(args: object) -> dict[SearchKey, int]:
    policy = probe._new_policy(args)
    states: dict[SearchKey, int] = {(_reduced_key(probe._policy_state(policy, at_sample=0)), False): 0}
    transition = _ReducedTransitionCache(args)
    horizon = probe._history_horizon(args)
    symbol_width = probe._history_symbol_width(args.vad_frame_samples)

    for _ in range(horizon):
        undecided = dict(states)
        decided: dict[SearchKey, int] = {}
        for carried_samples in range(args.vad_frame_samples):
            next_undecided: dict[SearchKey, int] = {}
            next_decided: dict[SearchKey, int] = {}
            for (prior_state, prior_decision), history in undecided.items():
                for decision in (False, True):
                    candidate, _ = transition.observe(
                        prior_state, sample_count=1, speech_present=decision
                    )
                    key = (candidate, decision)
                    proposal = probe._append_packed_history(
                        history,
                        carried_samples=carried_samples,
                        decision=decision,
                        symbol_width=symbol_width,
                    )
                    if key not in next_decided:
                        next_decided[key] = proposal
                if carried_samples + 1 < args.vad_frame_samples:
                    candidate, _ = transition.observe(
                        prior_state, sample_count=1, speech_present=prior_decision
                    )
                    key = (candidate, prior_decision)
                    if key not in next_undecided:
                        next_undecided[key] = history
            for (prior_state, decision), history in decided.items():
                candidate, _ = transition.observe(prior_state, sample_count=1, speech_present=decision)
                key = (candidate, decision)
                if key not in next_decided:
                    next_decided[key] = history
            undecided, decided = next_undecided, next_decided
        states = decided
    return states


def _retained_size(value: object, seen: set[int] | None = None) -> int:
    """Return a stable direct-container footprint for the terminal state map."""

    if seen is None:
        seen = set()
    identifier = id(value)
    if identifier in seen:
        return 0
    seen.add(identifier)
    size = sys.getsizeof(value)
    if isinstance(value, dict):
        for key, item in value.items():
            size += _retained_size(key, seen)
            size += _retained_size(item, seen)
    elif isinstance(value, tuple):
        for item in value:
            size += _retained_size(item, seen)
    return size


def _args(**values: int) -> object:
    return SimpleNamespace(
        **values,
        pre_speech_padding_samples=0,
        post_speech_padding_samples=0,
        reachable_progress_output=None,
        reachable_progress_every_samples=16,
    )


def _run_case(name: str, **values: int) -> None:
    args = _args(**values)
    full_states, _ = probe._reachable_boundary_states(args)
    projected_full: dict[SearchKey, int] = {}
    for (full_policy, decision), history in full_states.items():
        key = (_reduced_key(full_policy), decision)
        if key in projected_full:
            raise AssertionError(f"{name}: reduced key merged two distinct full policy states")
        projected_full[key] = history
    reduced_states = _reduced_boundary_states(args)
    identical_keys = projected_full.keys() == reduced_states.keys()
    identical_histories = identical_keys and all(
        projected_full[key] == reduced_states[key] for key in projected_full
    )
    if not identical_histories:
        raise AssertionError(f"{name}: removing candidate duration changed reachable states or witnesses")

    full_bytes = _retained_size(full_states)
    reduced_bytes = _retained_size(reduced_states)
    saved_bytes = full_bytes - reduced_bytes
    print(
        {
            "case": name,
            "history_horizon_vad_frames": probe._history_horizon(args),
            "full_terminal_states": len(full_states),
            "reduced_terminal_states": len(reduced_states),
            "identical_projected_policy_keys": identical_keys,
            "identical_packed_histories": identical_histories,
            "full_state_map_retained_bytes": full_bytes,
            "reduced_state_map_retained_bytes": reduced_bytes,
            "saved_bytes": saved_bytes,
            "saved_percent": round(0.0 if full_bytes == 0 else saved_bytes * 100 / full_bytes, 2),
        }
    )


def main() -> int:
    _run_case(
        "existing_one_vad_frame_toy",
        frame_samples=160,
        vad_frame_samples=160,
        min_speech_samples=160,
        min_silence_samples=320,
        hard_cap_samples=160,
    )
    _run_case(
        "six_frame_small_horizon",
        frame_samples=96,
        vad_frame_samples=16,
        min_speech_samples=16,
        min_silence_samples=32,
        hard_cap_samples=64,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
