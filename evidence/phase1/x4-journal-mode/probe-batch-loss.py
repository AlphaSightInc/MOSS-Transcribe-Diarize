#!/usr/bin/env python
"""Probe: one bad observation must not destroy a 4-speaker meeting.

Question this answers
---------------------
`LiveVectorJournalObservation` is a *structural* Protocol read by duck-typing,
and the runtime catches anything `append_session` raises as one opaque
`vector_journal_failed` event. So any per-observation failure that escapes as an
exception costs every other speaker in the session their row -- the exact
inverse of the by-name refusal policy.

Two ways a single observation can escape as an exception:
  A. a provider not updated in lockstep is MISSING a Protocol attribute
     (`AttributeError` while reading it), and
  B. an observation whose fields read fine but do not SERIALIZE -- e.g. a
     `speaker_label` that is not a string -- which raises `TypeError` from
     `json.dumps` after every row has already been validated.

Both are run here against `naive_append`, which is the obvious implementation
(direct attribute access, one `json.dumps` over the joined batch), and then
against the shipped `LiveVectorJournal.append_session`.

Run:  PYTHONPATH=. .venv/bin/python evidence/phase1/x4-journal-mode/probe-batch-loss.py
Exit: 0 when the naive writer loses all four speakers in both cases and the
      shipped writer journals the other three and declines the fourth by name.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from moss_transcribe_diarize.app.live_vector_journal import LiveVectorJournal  # noqa: E402

FIELDS = (
    "speaker_label",
    "centroid",
    "sample_seconds",
    "exemplar_count",
    "provisional",
    "embedder_id",
    "embedder_state_sha",
)


def _observation(label, *, drop: str | None = None) -> SimpleNamespace:
    """A synthetic observation. No real voice data is ever written by this probe."""

    values = dict(
        speaker_label=label,
        centroid=(0.6, 0.8),
        sample_seconds=2.5,
        exemplar_count=1,
        provisional=False,
        embedder_id="probe-embedder:synthetic",
        embedder_state_sha="ab" * 32,
    )
    if drop is not None:
        values.pop(drop)
    return SimpleNamespace(**values)


def naive_append(path: Path, observations) -> str:
    """The obvious implementation: read attributes directly, encode the batch once."""

    rows = []
    for observation in observations:
        rows.append(
            {field: getattr(observation, field) for field in FIELDS}
            | {"session_id": "probe-session", "created_at": 1.0, "echo_mode": "headphones"}
        )
    payload = b"".join(
        (json.dumps(row, allow_nan=False, sort_keys=True) + "\n").encode("utf-8")
        for row in rows
    )
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, payload)
    finally:
        os.close(descriptor)
    return "wrote"


def _labels_on_disk(path: Path) -> list[str]:
    return [row["speaker_label"] for row in LiveVectorJournal(path).read_rows()]


def _four_speakers(bad) -> tuple:
    return (
        _observation("speaker-0001"),
        _observation("speaker-0002"),
        bad,
        _observation("speaker-0004"),
    )


def run_case(root: Path, title: str, bad) -> tuple[list[str], list[str], list[tuple[str, str]]]:
    print(f"[{title}]")
    naive_path = root / f"naive-{title}.jsonl"
    try:
        naive_append(naive_path, _four_speakers(bad))
    except Exception as exc:  # noqa: BLE001 - the point of the probe
        print(f"  naive_append raised {type(exc).__name__}: {exc}")
    naive_labels = _labels_on_disk(naive_path) if naive_path.exists() else []
    print(f"  naive  journaled {len(naive_labels)}/4: {naive_labels}")

    shipped_path = root / f"shipped-{title}.jsonl"
    result = LiveVectorJournal(shipped_path).append_session(
        session_id="probe-session",
        echo_mode="headphones",
        created_at=1_800_000_000.0,
        observations=_four_speakers(bad),
    )
    shipped_labels = _labels_on_disk(shipped_path) if shipped_path.exists() else []
    refusals = [(item.speaker_label, item.reason) for item in result.refusals]
    print(f"  shipped journaled {len(shipped_labels)}/4: {shipped_labels}")
    print(f"  shipped refusals: {refusals}")
    return naive_labels, shipped_labels, refusals


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="x4-journal-batch-"))
    failures: list[str] = []
    try:
        naive, shipped, refusals = run_case(
            root, "missing-protocol-attribute", _observation("speaker-0003", drop="provisional")
        )
        if naive:
            failures.append(f"naive writer unexpectedly journaled {naive}")
        if shipped != ["speaker-0001", "speaker-0002", "speaker-0004"]:
            failures.append(f"shipped writer lost rows: {shipped}")
        if refusals != [("speaker-0003", "provisional_missing")]:
            failures.append(f"shipped writer did not decline by name: {refusals}")

        naive, shipped, refusals = run_case(
            root, "unserializable-speaker-label", _observation(b"speaker-0003")
        )
        if naive:
            failures.append(f"naive writer unexpectedly journaled {naive}")
        if shipped != ["speaker-0001", "speaker-0002", "speaker-0004"]:
            failures.append(f"shipped writer lost rows: {shipped}")
        if refusals != [("<invalid:bytes>", "speaker_label_invalid")]:
            failures.append(f"shipped writer did not decline by name: {refusals}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    for failure in failures:
        print(f"FAIL {failure}")
    print("PROBE OK" if not failures else "PROBE FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
