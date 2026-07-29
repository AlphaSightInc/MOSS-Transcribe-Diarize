#!/usr/bin/env python3
"""PROTOTYPE — throwaway. Design doc §6 gate C: tape-recorder assembly correctness.

Question: can an append-only per-lane assembler fed 0.5 s sequenced frames with
outbox-retry semantics (duplicates, reorder, drops) reconstruct session audio
byte-exactly with silence-filled manifested gaps, stable wall-clock offsets, and
checkpoint/resume mid-session?

Run: python3 proto_c_assembly.py
"""
from __future__ import annotations

import hashlib
import json
import random
import struct

FRAME_SAMPLES = 8000  # 0.5 s @ 16 kHz, production wire contract
SAMPLE_BYTES = 2  # PCM16


def frame_payload(lane: str, seq: int) -> bytes:
    """Deterministic pseudo-audio unique per (lane, seq) so byte identity is checkable."""
    rnd = random.Random(f"{lane}:{seq}")
    return struct.pack(
        f"<{FRAME_SAMPLES}h", *(rnd.randrange(-32768, 32768) for _ in range(FRAME_SAMPLES))
    )


SILENCE = b"\x00" * (FRAME_SAMPLES * SAMPLE_BYTES)


class LaneAssembler:
    """Append-only lane tape: contiguous writes, silence-filled sealed gaps, gap manifest.

    A frame with seq == next_expected extends the tape. Later seqs buffer up to
    `reorder_window` frames; when the buffer would overflow (client outbox gave up),
    the missing range is sealed as silence + manifest entries. Duplicates and
    frames at/below the sealed watermark are dropped idempotently.
    """

    def __init__(self, lane: str, reorder_window: int = 30):
        self.lane = lane
        self.reorder_window = reorder_window
        self.tape = bytearray()
        self.next_expected = 0
        self.pending: dict[int, bytes] = {}
        self.gaps: list[dict] = []
        self.duplicates_dropped = 0
        self.stale_dropped = 0

    def offer(self, seq: int, payload: bytes) -> None:
        if seq < self.next_expected or seq in self.pending:
            if seq < self.next_expected:
                self.stale_dropped += 1
            else:
                self.duplicates_dropped += 1
            return
        self.pending[seq] = payload
        self._drain()
        while len(self.pending) > self.reorder_window:
            self._seal_through(min(self.pending))

    def finalize(self, last_seq: int) -> None:
        """End of session: seal every remaining hole through last_seq."""
        while self.pending:
            self._seal_through(min(self.pending))
        if self.next_expected <= last_seq:
            self._record_gap(self.next_expected, last_seq)
            for _ in range(self.next_expected, last_seq + 1):
                self.tape += SILENCE
            self.next_expected = last_seq + 1

    def _seal_through(self, ready_seq: int) -> None:
        if ready_seq > self.next_expected:
            self._record_gap(self.next_expected, ready_seq - 1)
            for _ in range(self.next_expected, ready_seq):
                self.tape += SILENCE
            self.next_expected = ready_seq
        self._drain()

    def _drain(self) -> None:
        while self.next_expected in self.pending:
            self.tape += self.pending.pop(self.next_expected)
            self.next_expected += 1

    def _record_gap(self, first: int, last: int) -> None:
        self.gaps.append({"first_seq": first, "last_seq": last, "fill": "silence"})

    # --- checkpoint / resume -------------------------------------------------
    def checkpoint(self) -> dict:
        return {
            "lane": self.lane,
            "reorder_window": self.reorder_window,
            "tape_sha": hashlib.sha256(bytes(self.tape)).hexdigest(),
            "tape_hex": bytes(self.tape).hex(),  # prototype only; real impl keeps file
            "next_expected": self.next_expected,
            "pending": {str(k): v.hex() for k, v in self.pending.items()},
            "gaps": self.gaps,
        }

    @classmethod
    def resume(cls, state: dict) -> "LaneAssembler":
        inst = cls(state["lane"], state["reorder_window"])
        inst.tape = bytearray(bytes.fromhex(state["tape_hex"]))
        assert hashlib.sha256(bytes(inst.tape)).hexdigest() == state["tape_sha"], "tape corrupt"
        inst.next_expected = state["next_expected"]
        inst.pending = {int(k): bytes.fromhex(v) for k, v in state["pending"].items()}
        inst.gaps = list(state["gaps"])
        return inst


def mix(lane_tapes: list[bytes]) -> bytes:
    """Average available lanes sample-wise (production mixes aligned safe intervals)."""
    n = max(len(t) for t in lane_tapes)
    padded = [t + b"\x00" * (n - len(t)) for t in lane_tapes]
    out = bytearray(n)
    count = len(padded)
    for i in range(0, n, SAMPLE_BYTES):
        acc = sum(struct.unpack_from("<h", t, i)[0] for t in padded)
        struct.pack_into("<h", out, i, int(acc / count))
    return bytes(out)


def reference_tape(delivered: set[int], last_seq: int, lane: str) -> bytes:
    out = bytearray()
    for seq in range(last_seq + 1):
        out += frame_payload(lane, seq) if seq in delivered else SILENCE
    return bytes(out)


def gremlin_schedule(
    lane: str,
    n_frames: int,
    *,
    dup_rate: float = 0.0,
    drop_rate: float = 0.0,
    burst_drop: tuple[int, int] | None = None,
    jitter: int = 0,
    seed: int = 7,
) -> tuple[list[tuple[int, bytes]], set[int]]:
    """Returns (arrival stream, delivered seq set). Retries duplicate the SAME payload."""
    rnd = random.Random(f"sched:{lane}:{seed}")
    arrivals: list[tuple[float, int]] = []
    delivered: set[int] = set()
    for seq in range(n_frames):
        if burst_drop and burst_drop[0] <= seq < burst_drop[1]:
            continue
        if rnd.random() < drop_rate:
            continue
        delivered.add(seq)
        t = seq + (rnd.uniform(0, jitter) if jitter else 0.0)
        arrivals.append((t, seq))
        if rnd.random() < dup_rate:
            arrivals.append((t + rnd.uniform(0.1, 5.0), seq))  # outbox retry, same bytes
    arrivals.sort()
    return [(seq, frame_payload(lane, seq)) for _, seq in arrivals], delivered


def run_case(name: str, *, n_frames: int = 1200, resume_points: list[float] | None = None, **gremlins) -> bool:
    lanes = ["microphone", "system"]
    ok = True
    print(f"\n=== case: {name} ({n_frames} frames/lane = {n_frames // 2} s) ===")
    tapes = {}
    for lane in lanes:
        stream, delivered = gremlin_schedule(lane, n_frames, **gremlins)
        asm = LaneAssembler(lane)
        cut_indices = [int(len(stream) * p) for p in (resume_points or [])]
        for i, (seq, payload) in enumerate(stream):
            if i in cut_indices:  # simulated crash: checkpoint, discard instance, resume
                asm = LaneAssembler.resume(json.loads(json.dumps(asm.checkpoint())))
            asm.offer(seq, payload)
        asm.finalize(n_frames - 1)
        ref = reference_tape(delivered, n_frames - 1, lane)
        exact = bytes(asm.tape) == ref
        expected_len = n_frames * FRAME_SAMPLES * SAMPLE_BYTES
        gap_frames = sum(g["last_seq"] - g["first_seq"] + 1 for g in asm.gaps)
        print(
            f"  {lane:<11} bytes={len(asm.tape):>9} (expect {expected_len}) byte-exact={exact} "
            f"gaps={len(asm.gaps)} gap_frames={gap_frames} dropped_frames={n_frames - len(delivered)} "
            f"dups_dropped={asm.duplicates_dropped} stale_dropped={asm.stale_dropped}"
        )
        ok &= exact and len(asm.tape) == expected_len and gap_frames == n_frames - len(delivered)
        tapes[lane] = bytes(asm.tape)
    mixed = mix(list(tapes.values()))
    print(f"  mixed       bytes={len(mixed):>9} sha={hashlib.sha256(mixed).hexdigest()[:16]}")
    print(f"  -> {'PASS' if ok else 'FAIL'}")
    return ok


def main() -> None:
    results = {}
    results["clean in-order"] = run_case("clean in-order")
    results["duplicates 5%"] = run_case("duplicates 5% (outbox retries)", dup_rate=0.05)
    results["reorder jitter 4"] = run_case("reorder jitter 4 frames", jitter=4)
    results["drops 2%"] = run_case("drops 2% (outbox gave up)", drop_rate=0.02)
    results["burst drop 3s"] = run_case("burst drop 3 s (frames 600-605)", burst_drop=(600, 606))
    results["combined"] = run_case("combined gremlins", dup_rate=0.05, drop_rate=0.02, jitter=4, burst_drop=(300, 306))
    results["combined + resume x2"] = run_case(
        "combined + checkpoint/resume at 40% and 70%",
        dup_rate=0.05, drop_rate=0.02, jitter=4, burst_drop=(300, 306),
        resume_points=[0.4, 0.7],
    )

    print("\n=== VERDICT (gate C) ===")
    for k, v in results.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    print("ALL PASS" if all(results.values()) else "SOME FAILED")


if __name__ == "__main__":
    main()
