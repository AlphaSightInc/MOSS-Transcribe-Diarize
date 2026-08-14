#!/usr/bin/env python
"""Probe: what the journal does to paths that already exist.

Question this answers
---------------------
`os.open(path, O_CREAT, 0o600)` is a no-op for an existing file and
`Path.mkdir(mode=0o700, exist_ok=True)` is a no-op for an existing directory, so
a journal created once at a loose mode stays loose forever. This probe builds
the loose state, runs the ORIGINAL primitives over it, then runs the current
`LiveVectorJournal.declared()` over an identical sandbox, and prints raw
`stat` for the leaf file, the leaf directory, and the loose ancestor in both
cases.

It also drives the third case the ticket names: an ancestor this process cannot
repair (owned by another principal) must be refused, not silently trusted.

Run:  PYTHONPATH=. .venv/bin/python evidence/phase1/x4-journal-mode/probe-preexisting-modes.py
Exit: 0 when the current writer repairs both leaves, tightens the loose ancestor,
      and refuses the unrepairable one. Non-zero otherwise.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from moss_transcribe_diarize.app import live_vector_journal  # noqa: E402
from moss_transcribe_diarize.app.live_vector_journal import LiveVectorJournal  # noqa: E402

PREEXISTING_FILE_MODE = 0o644
PREEXISTING_LEAF_DIR_MODE = 0o777
PREEXISTING_ANCESTOR_MODE = 0o775
PREEXISTING_LINE = b'{"session_id":"written-by-an-earlier-release"}\n'


def _observation(label: str) -> SimpleNamespace:
    """A synthetic observation. No real voice data is ever written by this probe."""

    return SimpleNamespace(
        speaker_label=label,
        centroid=(0.6, 0.8),
        sample_seconds=2.5,
        exemplar_count=1,
        provisional=False,
        embedder_id="probe-embedder:synthetic",
        embedder_state_sha="ab" * 32,
    )


def _build_sandbox(root: Path) -> Path:
    """`root/data` (0775, the umask-masked mode an earlier release left behind)
    -> `root/data/live` (0777) -> `root/data/live/speaker-vectors.jsonl` (0644)."""

    ancestor = root / "data"
    leaf = ancestor / "live"
    leaf.mkdir(parents=True)
    journal = leaf / "speaker-vectors.jsonl"
    journal.write_bytes(PREEXISTING_LINE)
    os.chmod(journal, PREEXISTING_FILE_MODE)
    os.chmod(leaf, PREEXISTING_LEAF_DIR_MODE)
    os.chmod(ancestor, PREEXISTING_ANCESTOR_MODE)
    return journal


def _modes(journal: Path) -> dict[str, str]:
    return {
        "file": f"{journal.stat().st_mode & 0o777:04o}",
        "leaf_dir": f"{journal.parent.stat().st_mode & 0o777:04o}",
        "ancestor": f"{journal.parent.parent.stat().st_mode & 0o777:04o}",
    }


def _report(title: str, modes: dict[str, str]) -> None:
    print(f"  {title:<22} file={modes['file']} leaf_dir={modes['leaf_dir']} ancestor={modes['ancestor']}")


def original_primitives(root: Path) -> dict[str, str]:
    """Exactly what the pre-branch writer did: mkdir(mode=...) + open(..., 0o600)."""

    journal = _build_sandbox(root)
    _report("before", _modes(journal))
    journal.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(journal, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, b'{"session_id":"probe"}\n')
    finally:
        os.close(descriptor)
    after = _modes(journal)
    _report("after (original)", after)
    return after


def current_writer(root: Path) -> dict[str, str]:
    journal_path = _build_sandbox(root)
    _report("before", _modes(journal_path))
    journal = LiveVectorJournal.declared(journal_path, checkout_root=root / "checkout")
    result = journal.append_session(
        session_id="probe-session",
        echo_mode="headphones",
        created_at=1_800_000_000.0,
        observations=(_observation("speaker-0001"),),
    )
    after = _modes(journal_path)
    _report("after (current)", after)
    print(f"  rows written={result.written} refusals={result.refusals}")
    print(f"  preexisting line retained={journal_path.read_bytes().startswith(PREEXISTING_LINE)}")
    return after


def unrepairable_ancestor(root: Path) -> tuple[str | None, str]:
    """An ancestor owned by another principal cannot be chmoded from here."""

    journal_path = _build_sandbox(root)
    ancestor = journal_path.parent.parent
    before = f"{ancestor.stat().st_mode & 0o777:04o}"
    real_geteuid = os.geteuid
    live_vector_journal.os.geteuid = lambda: real_geteuid() + 1
    try:
        LiveVectorJournal.declared(journal_path, checkout_root=root / "checkout")
    except ValueError as exc:
        message = str(exc)
    else:
        message = None
    finally:
        live_vector_journal.os.geteuid = real_geteuid
    after = f"{ancestor.stat().st_mode & 0o777:04o}"
    print(f"  ancestor before={before} after={after} refusal={message!r}")
    return message, after


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="x4-journal-modes-"))
    failures: list[str] = []
    try:
        print("[1] original primitives over pre-existing paths")
        original = original_primitives(root / "original")

        print("[2] current LiveVectorJournal.declared over an identical sandbox")
        current = current_writer(root / "current")

        print("[3] an ancestor this process does not own")
        refusal, ancestor_after = unrepairable_ancestor(root / "foreign")

        if original != {
            "file": f"{PREEXISTING_FILE_MODE:04o}",
            "leaf_dir": f"{PREEXISTING_LEAF_DIR_MODE:04o}",
            "ancestor": f"{PREEXISTING_ANCESTOR_MODE:04o}",
        }:
            failures.append(f"original primitives did not leave the loose modes intact: {original}")
        if current != {"file": "0600", "leaf_dir": "0700", "ancestor": "0755"}:
            failures.append(f"current writer left non-private modes: {current}")
        if refusal is None or "could not be made private" not in refusal:
            failures.append(f"unrepairable ancestor was not refused: {refusal!r}")
        if ancestor_after != f"{PREEXISTING_ANCESTOR_MODE:04o}":
            failures.append(
                f"a foreign-owned ancestor was mutated anyway: {ancestor_after}"
            )
    finally:
        for path in root.rglob("*"):
            if path.is_dir():
                os.chmod(path, 0o700)
        shutil.rmtree(root, ignore_errors=True)

    for failure in failures:
        print(f"FAIL {failure}")
    print("PROBE OK" if not failures else "PROBE FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
