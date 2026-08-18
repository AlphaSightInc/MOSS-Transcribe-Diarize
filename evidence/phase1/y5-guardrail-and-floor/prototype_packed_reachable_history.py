#!/usr/bin/env python3
"""Measure whether packed VAD histories preserve reachable-state search results.

Question: can the sample-at-a-time search replace its per-state tuple of
``(carried_samples, decision)`` entries with a fixed-width integer without
changing any merged endpoint state or its replay history?

The prototype runs both representations through the production EndpointPolicy
transition cache.  It deliberately retains the existing per-sample merge point
and compares every final policy key and decoded history before reporting the
retained Python-object size of each state map.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path
from types import ModuleType
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
SearchKey: TypeAlias = tuple[PolicyState, bool]
TupleHistory: TypeAlias = tuple[tuple[int, bool], ...]


def _retained_size(value: object, seen: set[int] | None = None) -> int:
    """Return a stable, direct-container retained-size estimate for this prototype."""

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


def _symbol_width(vad_frame_samples: int) -> int:
    return max(1, (vad_frame_samples * 2 - 1).bit_length())


def _append_packed(history: int, *, carried_samples: int, decision: bool, width: int) -> int:
    return (history << width) | ((carried_samples << 1) | int(decision))


def _decode_packed(history: int, *, entry_count: int, width: int) -> TupleHistory:
    mask = (1 << width) - 1
    decoded: list[tuple[int, bool]] = []
    for _ in range(entry_count):
        symbol = history & mask
        decoded.append((symbol >> 1, bool(symbol & 1)))
        history >>= width
    return tuple(reversed(decoded))


def _boundary_states_tuple(args: object) -> tuple[dict[SearchKey, TupleHistory], dict[str, int]]:
    policy = probe._new_policy(args)
    states: dict[SearchKey, TupleHistory] = {(probe._policy_state(policy, at_sample=0), False): ()}
    transition = probe.PolicyTransitionCache(args)
    horizon = -(-args.hard_cap_samples // args.vad_frame_samples) + 2
    for _ in range(horizon):
        undecided = dict(states)
        decided: dict[SearchKey, TupleHistory] = {}
        for carried_samples in range(args.vad_frame_samples):
            next_undecided: dict[SearchKey, TupleHistory] = {}
            next_decided: dict[SearchKey, TupleHistory] = {}
            for (prior_state, prior_decision), history in undecided.items():
                for decision in (False, True):
                    candidate, _ = transition.observe(prior_state, sample_count=1, speech_present=decision)
                    key = (candidate, decision)
                    proposal = history + ((carried_samples, decision),)
                    existing = next_decided.get(key)
                    if existing is None or len(proposal) < len(existing):
                        next_decided[key] = proposal
                if carried_samples + 1 < args.vad_frame_samples:
                    candidate, _ = transition.observe(
                        prior_state, sample_count=1, speech_present=prior_decision
                    )
                    key = (candidate, prior_decision)
                    existing = next_undecided.get(key)
                    if existing is None or len(history) < len(existing):
                        next_undecided[key] = history
            for (prior_state, decision), history in decided.items():
                candidate, _ = transition.observe(prior_state, sample_count=1, speech_present=decision)
                key = (candidate, decision)
                existing = next_decided.get(key)
                if existing is None or len(history) < len(existing):
                    next_decided[key] = history
            undecided, decided = next_undecided, next_decided
        states = decided
    return states, transition.statistics()


def _boundary_states_packed(args: object) -> tuple[dict[SearchKey, int], dict[str, int], int]:
    policy = probe._new_policy(args)
    states: dict[SearchKey, int] = {(probe._policy_state(policy, at_sample=0), False): 0}
    transition = probe.PolicyTransitionCache(args)
    width = _symbol_width(args.vad_frame_samples)
    horizon = -(-args.hard_cap_samples // args.vad_frame_samples) + 2
    for _ in range(horizon):
        undecided = dict(states)
        decided: dict[SearchKey, int] = {}
        for carried_samples in range(args.vad_frame_samples):
            next_undecided: dict[SearchKey, int] = {}
            next_decided: dict[SearchKey, int] = {}
            for (prior_state, prior_decision), history in undecided.items():
                for decision in (False, True):
                    candidate, _ = transition.observe(prior_state, sample_count=1, speech_present=decision)
                    key = (candidate, decision)
                    proposal = _append_packed(
                        history,
                        carried_samples=carried_samples,
                        decision=decision,
                        width=width,
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
    return states, transition.statistics(), width


def _args(**values: int) -> object:
    return type("Args", (), {**values, "pre_speech_padding_samples": 0, "post_speech_padding_samples": 0})()


def _run_case(name: str, **values: int) -> None:
    args = _args(**values)
    horizon = -(-args.hard_cap_samples // args.vad_frame_samples) + 2

    start = time.monotonic()
    tuple_states, tuple_cache = _boundary_states_tuple(args)
    tuple_seconds = time.monotonic() - start
    start = time.monotonic()
    packed_states, packed_cache, width = _boundary_states_packed(args)
    packed_seconds = time.monotonic() - start

    identical_keys = tuple_states.keys() == packed_states.keys()
    identical_histories = identical_keys and all(
        history
        == _decode_packed(
            packed_states[key],
            entry_count=horizon,
            width=width,
        )
        for key, history in tuple_states.items()
    )
    tuple_bytes = _retained_size(tuple_states)
    packed_bytes = _retained_size(packed_states)
    saved_bytes = tuple_bytes - packed_bytes
    saved_percent = 0.0 if tuple_bytes == 0 else saved_bytes * 100 / tuple_bytes

    print(
        {
            "case": name,
            "history_horizon_vad_frames": horizon,
            "history_symbol_width_bits": width,
            "terminal_equivalent_states": len(tuple_states),
            "identical_policy_keys": identical_keys,
            "identical_decoded_histories": identical_histories,
            "tuple_state_map_retained_bytes": tuple_bytes,
            "packed_state_map_retained_bytes": packed_bytes,
            "saved_bytes": saved_bytes,
            "saved_percent": round(saved_percent, 2),
            "tuple_seconds": round(tuple_seconds, 4),
            "packed_seconds": round(packed_seconds, 4),
            "tuple_transition_cache": tuple_cache,
            "packed_transition_cache": packed_cache,
        }
    )
    if not identical_histories:
        raise AssertionError(f"{name}: packed history changed a reachable-state result")


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
