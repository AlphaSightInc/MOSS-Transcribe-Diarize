#!/usr/bin/env python3
"""Measure how much of a real meeting ever reaches the album and the sweep ledger.

Candidate 65 asks a question the loop could only argue about: the eight-meeting accuracy
harness measures the retrospective sweep repairing +5.82 pp (93.44 -> 99.26 %), while F1 and
F2 on the deployed `7a4f59c` measured `identity_revision_version` 0 on every span and zero
`live identity sweep` lines. Candidate 65 states the two readings have to be reconciled *by
measurement*.

This probe measures the reconciliation's first branch -- "the deployed ledger/album disagrees
with the fixture in a way the harness cannot see" -- from evidence that already exists, with
no host, no session and no product change. It answers three questions about a finished run:

  1. How many of the meeting's segments clear the **evidence floor**
     (`identity_provider.min_segment_samples`, 8000 = 0.5 s on the deployed manifest)? A
     segment below it is never embedded, so it produces no ledger unit and no album
     observation -- it is invisible to step 3 entirely.
  2. How many (span, local speaker) observations clear the **album admission gate**
     (`ALBUM_ADMISSION_SECONDS`, 1.0 s)? Only an admitted exemplar enters a speaker's bank and
     can move that speaker's duration-weighted centroid.
  3. Given (2), how many canonical speakers ever hold an **admitted bank** at all -- i.e. how
     many references a sweep has to re-match against, and whether any of them could have moved
     during the meeting.

**Why those three and not a sweep replay.** A sweep proposes a correction only where re-matching
against the album *now* disagrees with what the live path matched against the album *then*. Both
sides call the same matcher on the same vectors (`live_identity.assign_speakers`, Phase N decision
5), so the only thing that can make them disagree is the album's references having moved in
between. A meeting whose references never move cannot produce a correction however the sweep is
wired, and that is a property of the meeting's segment durations alone -- measurable here.

**What this probe cannot say.** It does not re-embed and does not re-match: it never sees a
vector, so it cannot say a correction *would* have been proposed had the references moved. It
bounds the opportunity, not the outcome. And it reads a **prefix** of the meeting -- the drivers
poll a full snapshot every 30 polls (candidate 61) -- so every count is reported with its
coverage against the run's authoritative final span count.

Usage:
    python3 scripts/ralph-afk/identity-evidence-probe.py <evidence-dir> [<evidence-dir> ...]

`<evidence-dir>` is a canary/cert/soak evidence directory (the one holding `snap-full-*.json`
and `snapshot.tsv`). Exit codes: 0 measured, 6 unreadable layout (named, never a traceback).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

# Production's own parsers, imported rather than reimplemented: a probe that re-derived the span
# grammar or the interval filter would be measuring its own second opinion. Phase N decision 5's
# rule, applied to a measurement instead of to a matcher.
from moss_transcribe_diarize.app.live_identity_album import (  # noqa: E402
    ALBUM_ADMISSION_SECONDS,
    ALBUM_EXEMPLARS_PER_SPEAKER,
)
from moss_transcribe_diarize.app.live_provider_bundle import (  # noqa: E402
    _intervals_duration,
    _speaker_intervals_by_label,
)
from moss_transcribe_diarize.app.live_session import FrozenSpan  # noqa: E402
from moss_transcribe_diarize.app.live_span_bounds import span_segments  # noqa: E402

RC_OK = 0
RC_UNREADABLE = 6

# The deployed evidence floor, read off the host manifest rather than off a document (Phase N
# decision 16). Overridable so a future deployment can be measured without editing the probe.
DEPLOYED_MIN_SEGMENT_SAMPLES = 8000

# `S00` is J2's unattributed label: the span published its words with no speaker attributed, so
# it is a local speaker with no canonical claim rather than a canonical speaker of its own.
UNATTRIBUTED = "S00"


class Unreadable(Exception):
    """A named refusal. The layout could not be read; nothing is guessed from it."""


def _has_bodies(session: object) -> bool:
    """A committed list whose entries carry a `transcript`, not just a pruned `span_id`."""

    if not isinstance(session, dict):
        return False
    committed = session.get("committed")
    if not isinstance(committed, list) or not committed:
        return False
    return any(isinstance(entry, dict) and "transcript" in entry for entry in committed)


def _tsv_snapshots(directory: Path):
    """Every 200-answering `snapshot.tsv` row, newest first, as parsed session payloads."""

    try:
        rows = (directory / "snapshot.tsv").read_text().splitlines()
    except OSError:
        return
    for row in reversed(rows):
        fields = row.split("\t")
        if len(fields) < 3 or fields[1] != "200":
            continue
        try:
            payload = json.loads(fields[2])
        except ValueError:
            continue
        yield payload


def _spans_source(directory: Path) -> tuple[dict, str]:
    """The newest readable snapshot carrying span *bodies*, and the name of what answered.

    Candidate 61's rule, generalised over the two driver layouts this loop actually produces:
    the cert and soak drivers prune `snapshot.tsv` to `span_id` and write periodic
    `snap-full-*.json`, while the canary driver writes the whole snapshot into every TSV row.
    Either can answer; the probe always says which one did, because a body count that came from
    a prefix means something different from one that came from the run's last row.
    """

    for path in sorted(directory.glob("snap-full-*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if _has_bodies((payload.get("snapshot") or {}).get("session")):
            return payload, path.name
    for payload in _tsv_snapshots(directory):
        if _has_bodies((payload.get("snapshot") or {}).get("session")):
            return payload, "snapshot.tsv"
    raise Unreadable(f"no snapshot with span bodies under {directory}")


def _final_session(directory: Path) -> dict | None:
    """The run's own last 200-answering snapshot, body-carrying or not.

    The pruned TSV is authoritative for the run's *end* (candidate 61) even when the bodies had
    to come from a prefix, so the coverage figure is not the prefix measuring itself -- and
    `label_revision_version` is read from here rather than from the prefix, because "no
    correction was ever published" is a claim about the whole meeting.
    """

    for payload in _tsv_snapshots(directory):
        session = (payload.get("snapshot") or {}).get("session")
        if isinstance(session, dict) and isinstance(session.get("committed"), list):
            return session
    return None


def measure(directory: Path, *, min_segment_samples: int) -> dict:
    payload, source = _spans_source(directory)
    session = payload["snapshot"]["session"]
    committed = session["committed"]
    final = _final_session(directory) or session

    segments_total = 0
    segments_over_floor = 0
    observations = 0          # (span, local speaker) pairs that produced a vector at all
    admitted = 0              # ... of which cleared the album's 1.0 s admission gate
    admitted_by_speaker: Counter[str] = Counter()
    observed_by_speaker: Counter[str] = Counter()
    seconds_by_speaker: defaultdict[str, float] = defaultdict(float)
    unattributed_observations = 0
    empty_spans = 0
    revised = 0

    for entry in committed:
        transcript = entry.get("transcript") or ""
        if entry.get("revised_transcript"):
            revised += 1
        start_sample = int(entry["start_sample"])
        end_sample = int(entry["end_sample"])
        sample_count = end_sample - start_sample
        if sample_count <= 0 or not transcript:
            empty_spans += 1
            continue
        parsed = span_segments(transcript, sample_count=sample_count)
        segments_total += len(parsed)
        span = FrozenSpan(
            id=int(entry["span_id"]),
            epoch=0,
            start_sample=start_sample,
            end_sample=end_sample,
            reason="end_silence",
        )
        intervals = _speaker_intervals_by_label(span, parsed, min_segment_samples)
        segments_over_floor += sum(len(items) for items in intervals.values())
        for speaker, items in intervals.items():
            duration = _intervals_duration(items)
            observations += 1
            observed_by_speaker[speaker] += 1
            seconds_by_speaker[speaker] += duration
            if speaker == UNATTRIBUTED:
                unattributed_observations += 1
            if duration >= ALBUM_ADMISSION_SECONDS:
                admitted += 1
                admitted_by_speaker[speaker] += 1

    # A canonical speaker with no admitted exemplar holds only a provisional stand-in (Phase N
    # decision 3), which is never averaged and never moves -- so its reference is frozen for the
    # whole meeting no matter how much speech it goes on to carry.
    banked = {
        speaker: count
        for speaker, count in admitted_by_speaker.items()
        if speaker != UNATTRIBUTED
    }
    # A bank can only *move* a reference while it is still filling or still replacing: one
    # admitted exemplar is a bank that has never changed since it was created.
    moved = {speaker: count for speaker, count in banked.items() if count >= 2}

    return {
        "directory": str(directory),
        "source": source,
        "spans_read": len(committed),
        "spans_final": len(final.get("committed") or ()) or None,
        "empty_spans": empty_spans,
        "segments_total": segments_total,
        "segments_over_floor": segments_over_floor,
        "observations": observations,
        "unattributed_observations": unattributed_observations,
        "admitted": admitted,
        "canonical_speakers": len(final.get("identity_snapshot", {}).get("canonical_speakers", [])),
        "speakers_seen": sorted(observed_by_speaker),
        "speakers_banked": banked,
        "speakers_with_moving_reference": moved,
        "seconds_by_speaker": {k: round(v, 2) for k, v in sorted(seconds_by_speaker.items())},
        "label_revision_version": final.get("label_revision_version"),
        "revised_spans": revised,
        "min_segment_samples": min_segment_samples,
    }


def _report(result: dict) -> None:
    spans_read = result["spans_read"]
    spans_final = result["spans_final"]
    coverage = "unknown" if not spans_final else f"{spans_read}/{spans_final} spans"
    print(f"== {result['directory']}")
    print(f"   source           {result['source']}  (coverage {coverage}; a prefix by design)")
    print(
        f"   evidence floor   {result['segments_over_floor']}/{result['segments_total']} segments "
        f"clear min_segment_samples={result['min_segment_samples']} "
        f"({_pct(result['segments_over_floor'], result['segments_total'])})"
    )
    print(
        f"   album admission  {result['admitted']}/{result['observations']} observations clear "
        f"{ALBUM_ADMISSION_SECONDS:.1f} s ({_pct(result['admitted'], result['observations'])})"
    )
    print(
        f"   references       {len(result['speakers_banked'])} of {result['canonical_speakers']} "
        f"canonical speakers ever hold an admitted exemplar; "
        f"{len(result['speakers_with_moving_reference'])} could have MOVED (>= 2 exemplars, "
        f"k={ALBUM_EXEMPLARS_PER_SPEAKER})"
    )
    print(
        f"   banked           {result['speakers_banked'] or '{}'}   "
        f"unattributed observations {result['unattributed_observations']}"
    )
    print(
        f"   published        label_revision_version={result['label_revision_version']} "
        f"revised_transcript on {result['revised_spans']} spans"
    )


def _pct(part: int, whole: int) -> str:
    return "n/a" if not whole else f"{100.0 * part / whole:.1f} %"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="+", type=Path)
    parser.add_argument("--min-segment-samples", type=int, default=DEPLOYED_MIN_SEGMENT_SAMPLES)
    parser.add_argument("--json", action="store_true", help="emit the measurements as JSON too")
    args = parser.parse_args(argv)

    results = []
    for directory in args.directories:
        try:
            result = measure(directory, min_segment_samples=args.min_segment_samples)
        except Unreadable as exc:
            print(f"== {directory}\n   REFUSED: {exc}")
            return RC_UNREADABLE
        results.append(result)
        _report(result)
    if args.json:
        print(json.dumps(results, indent=1))
    return RC_OK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
