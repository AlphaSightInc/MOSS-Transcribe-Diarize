#!/usr/bin/env python
"""Probe: the reader contract over a journal that contains real crash debris.

Question this answers
---------------------
The writer deliberately leaves unparseable bytes on disk -- it terminates a torn
tail with one newline instead of deleting it -- so every consumer of the journal
must skip blank and malformed lines. Nothing consumes the journal in Phase 1, so
this probe stands in for that consumer and pins the contract documented in
`docs/adr/0003-live-session-audio-retention.md`.

The file this probe builds contains, in order:
  1. a leading blank line,
  2. a valid row,
  3. a forensic line -- a truncated record from a crash before fsync,
  4. a line that is valid JSON but not an object,
  5. a line that is not valid UTF-8,
  6. an unterminated torn tail,
and is then handed to a REFUSAL-ONLY session (every observation invalid), which
is the case where a naive `if rows:` guard would skip recovery and leave the
torn tail glued to the next real row.

Run:  PYTHONPATH=. .venv/bin/python evidence/phase1/x4-journal-mode/probe-reader-contract.py
Exit: 0 when the refusal-only session terminates the tail without writing a row,
      the next real session appends a clean row, every forensic byte survives,
      and read_rows() returns exactly the two well-formed rows.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from moss_transcribe_diarize.app.live_vector_journal import LiveVectorJournal  # noqa: E402

VALID_ROW = (
    b'{"centroid":[0.6,0.8],"created_at":1.0,"echo_mode":"headphones",'
    b'"embedder_id":"probe-embedder:synthetic","embedder_state_sha":"' + b"ab" * 32 + b'",'
    b'"exemplar_count":1,"provisional":false,"sample_seconds":2.5,'
    b'"session_id":"an-earlier-session","speaker_label":"speaker-0001"}'
)
FORENSIC = b'{"session_id":"crashed-before-fsync","speaker_label":"speaker-000'
NOT_AN_OBJECT = b'["not","an","object"]'
NOT_UTF8 = b"\xff\xfe not utf-8 \x00"
TORN_TAIL = b'{"session_id":"torn","speaker_label"'

DEBRIS = b"\n".join((b"", VALID_ROW, FORENSIC, NOT_AN_OBJECT, NOT_UTF8, TORN_TAIL))


def _observation(label: str, **overrides) -> SimpleNamespace:
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
    values.update(overrides)
    return SimpleNamespace(**values)


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="x4-journal-reader-"))
    failures: list[str] = []
    try:
        path = root / "speaker-vectors.jsonl"
        path.write_bytes(DEBRIS)
        journal = LiveVectorJournal(path)
        print(f"seeded {len(DEBRIS)} bytes, ends with newline={DEBRIS.endswith(chr(10).encode())}")

        refused = journal.append_session(
            session_id="refusal-only-session",
            echo_mode="headphones",
            created_at=1_800_000_001.0,
            observations=(
                _observation("speaker-refused", centroid=()),
                _observation("speaker-also-refused", sample_seconds=0.0),
            ),
        )
        after_refusals = path.read_bytes()
        print(f"refusal-only session: written={refused.written} refusals="
              f"{[(item.speaker_label, item.reason) for item in refused.refusals]}")
        print(f"  torn tail terminated={after_refusals.endswith(TORN_TAIL + chr(10).encode())}")

        written = journal.append_session(
            session_id="next-real-session",
            echo_mode="headphones",
            created_at=1_800_000_002.0,
            observations=(_observation("speaker-0002"),),
        )
        final = path.read_bytes()
        rows = journal.read_rows()
        print(f"next real session: written={written.written}")
        print(f"forensic bytes retained={DEBRIS in final}")
        print(f"lines on disk={len(final.splitlines())} rows read={len(rows)}")
        for row in rows:
            print(f"  row session_id={row['session_id']!r} speaker_label={row['speaker_label']!r}")

        if refused.written != 0:
            failures.append(f"refusal-only session wrote {refused.written} rows")
        if not after_refusals.endswith(TORN_TAIL + b"\n"):
            failures.append("refusal-only session did not terminate the torn tail")
        if DEBRIS not in final:
            failures.append("forensic bytes were mutated or dropped")
        if written.written != 1:
            failures.append("the next real session did not append its row")
        if [row["session_id"] for row in rows] != ["an-earlier-session", "next-real-session"]:
            failures.append(f"reader did not skip blank/malformed lines: {rows}")
        if len(final.splitlines()) != 7:
            failures.append(f"unexpected line count on disk: {len(final.splitlines())}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    for failure in failures:
        print(f"FAIL {failure}")
    print("PROBE OK" if not failures else "PROBE FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
