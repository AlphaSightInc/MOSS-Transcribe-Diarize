#!/usr/bin/env python3
"""Measure what each canonical speaker of a real meeting was BORN from.

Iteration 5 (`sweep-multiplicity-probe.py`) settled candidate 65's cause on real encoder
geometry: the deployed sweep is inert because F2's reference set is *many stand-ins per
voice*, and a stand-in is unmergeable, so `_album_view`'s merge -- the sweep's own defence
against multiplicity -- never fires. Two controls make it a mechanism rather than a
correlation: stand-ins without multiplicity cost 3.8 % ambiguity, multiplicity without
stand-ins costs 1.1 %, the product costs 74.4 %.

That says what is *sufficient* to cause the inert sweep. It does not say what to change. This
probe asks the next question, on the same evidence and with no host and no product change:

    **Where does an unbankable reference come from?**

The answer is a single site. `BoundedCausalIdentityPreparer.prepare` (`live_identity.py:129`)
mints a canonical speaker for *every* local speaker the span's diarization produced that did
not match an existing one -- with no duration condition of any kind. The evidence floor sits
one layer down (`live_provider_bundle._speaker_intervals_by_label`, `min_segment_samples`
8000 = 0.5 s on the deployed manifest) and the album's admission gate one layer below that
(`ALBUM_ADMISSION_SECONDS` 1.0 s). So a birth can land in one of three states, and only the
third is a reference the sweep can ever merge:

  * **no_reference** -- the local speaker's speech never cleared the evidence floor, so the
    encoder was never asked for a vector. A canonical slot is spent on audio the system
    deliberately refused to embed. It is not even a stand-in.
  * **provisional** -- cleared the evidence floor but not the admission gate, so the album
    holds one sub-admission fragment as a stand-in (Phase N decision 3). Never averaged,
    never moves, and **unmergeable** (decision 7 needs an admitted bank on *both* sides).
  * **banked** -- cleared admission at birth, so the speaker holds an admitted exemplar from
    its very first span and is mergeable for the rest of the meeting.

What this measures per evidence directory: the birth state of every canonical speaker, the
resulting references-per-real-voice ratio, and what that ratio would have been had a birth
floor been enforced at each of the three thresholds.

**What this probe cannot say, stated first because the headline number is a counterfactual.**
Suppressing a birth changes the matcher's later inputs: a span whose speaker was refused a
birth may, in the next span, match an *existing* canonical instead of birthing again. So the
surviving-speaker counts are an **upper bound on births suppressed** and a lower bound on the
final canonical count under a floor -- not a simulation of the run. Nothing here re-embeds,
re-matches or re-renders; it reads the labels the deployed system actually published.

Two further limits inherited from the evidence itself: the span bodies come from the newest
readable `snap-full-*.json`, so every count covers a **prefix** of the meeting (candidate 61),
reported against the run's authoritative final span count; and the local speaker of a span is
recovered from the *relabeled* transcript, so two locals the live path mapped onto one
canonical are indistinguishable here -- which cannot happen inside one span (Phase N decision
10 forbids it) but does across spans, and is exactly what the ratio is measuring.

Usage:
    python3 scripts/ralph-afk/birth-floor-probe.py <evidence-dir> [<evidence-dir> ...]
        [--real-voices N] [--min-segment-samples N]

Exit codes: 0 measured, 6 unreadable layout (named, never a traceback).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

# Production's own parsers, imported rather than reimplemented -- Phase N decision 5's rule
# applied to a measurement: a probe that re-derived the span grammar or the interval filter
# would be measuring its own second opinion of the thing it is auditing.
from moss_transcribe_diarize.app.live_identity_album import (  # noqa: E402
    ALBUM_ADMISSION_SECONDS,
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

# J2's unattributed label: the span published its words with no speaker attributed, so it is a
# local speaker with no canonical claim rather than a canonical speaker of its own.
UNATTRIBUTED = "S00"

NO_REFERENCE = "no_reference"
PROVISIONAL = "provisional"
BANKED = "banked"


class Unreadable(Exception):
    """A named refusal for a layout the probe cannot read -- never a traceback."""


def _has_bodies(session: object) -> bool:
    if not isinstance(session, dict):
        return False
    committed = session.get("committed")
    if not isinstance(committed, list) or not committed:
        return False
    return any(isinstance(entry, dict) and "transcript" in entry for entry in committed)


def _tsv_snapshots(directory: Path):
    try:
        rows = (directory / "snapshot.tsv").read_text().splitlines()
    except OSError:
        return
    for row in reversed(rows):
        fields = row.split("\t")
        if len(fields) < 3 or fields[1] != "200":
            continue
        try:
            yield json.loads(fields[2])
        except ValueError:
            continue


def _spans_source(directory: Path) -> tuple[dict, str]:
    """The newest readable snapshot carrying span *bodies*, and the name of what answered."""

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
    for payload in _tsv_snapshots(directory):
        session = (payload.get("snapshot") or {}).get("session")
        if isinstance(session, dict) and isinstance(session.get("committed"), list):
            return session
    return None


def _birth_state(embedded_seconds: float) -> str:
    if embedded_seconds <= 0.0:
        return NO_REFERENCE
    if embedded_seconds < ALBUM_ADMISSION_SECONDS:
        return PROVISIONAL
    return BANKED


def measure(directory: Path, *, min_segment_samples: int, real_voices: int) -> dict:
    payload, source = _spans_source(directory)
    session = payload["snapshot"]["session"]
    committed = session["committed"]
    final = _final_session(directory) or session

    births: dict[str, dict] = {}
    seconds_by_speaker: Counter[str] = Counter()
    spans_with_body = 0

    for entry in committed:
        transcript = entry.get("transcript") or ""
        start_sample = int(entry["start_sample"])
        end_sample = int(entry["end_sample"])
        sample_count = end_sample - start_sample
        if sample_count <= 0 or not transcript:
            continue
        spans_with_body += 1
        parsed = span_segments(transcript, sample_count=sample_count)
        span = FrozenSpan(
            id=int(entry["span_id"]),
            epoch=0,
            start_sample=start_sample,
            end_sample=end_sample,
            reason="end_silence",
        )
        # Two readings of the same span: every segment the transcript carries, and only those
        # the deployed evidence floor would have embedded. The gap between them is the audio a
        # birth can be minted from while producing no vector at all.
        spoken = _speaker_intervals_by_label(span, parsed, 1)
        embedded = _speaker_intervals_by_label(span, parsed, min_segment_samples)
        for speaker, intervals in spoken.items():
            if speaker == UNATTRIBUTED:
                continue
            seconds_by_speaker[speaker] += _intervals_duration(intervals)
            if speaker in births:
                continue
            embedded_seconds = _intervals_duration(embedded.get(speaker, []))
            # The words the birth was minted from, because the durations alone understate the
            # case: a canonical slot spent on a segment the decoder filled with `...` is a
            # different fact from one spent on a short real utterance.
            spoken_text = "".join(
                segment.text for segment in parsed if segment.speaker == speaker
            ).strip()
            births[speaker] = {
                "span_id": int(entry["span_id"]),
                "span_start_seconds": round(start_sample / 16000.0, 2),
                "spoken_seconds": round(_intervals_duration(intervals), 3),
                "embedded_seconds": round(embedded_seconds, 3),
                "state": _birth_state(embedded_seconds),
                "segments": len(embedded.get(speaker, [])) or len(intervals),
                "text": spoken_text[:60],
            }

    states = Counter(record["state"] for record in births.values())
    # A floor is enforced on the quantity the album's admission gate already uses -- the seconds
    # of speech that produced a vector -- so "survives floor F" and "is banked at birth" are the
    # same predicate when F == ALBUM_ADMISSION_SECONDS. That coincidence is the proposal.
    floors = {}
    for floor in (0.0, 0.5, ALBUM_ADMISSION_SECONDS, 2.0):
        survivors = [
            speaker
            for speaker, record in births.items()
            if record["embedded_seconds"] >= floor
        ]
        floors[f"{floor:.1f}"] = {
            "surviving_canonical_speakers": len(survivors),
            "references_per_real_voice": (
                round(len(survivors) / real_voices, 2) if real_voices else None
            ),
            "banked_at_birth": sum(
                1
                for speaker in survivors
                if births[speaker]["embedded_seconds"] >= ALBUM_ADMISSION_SECONDS
            ),
        }

    final_committed = final.get("committed") or ()
    return {
        "directory": str(directory),
        "spans_source": source,
        "spans_read": len(committed),
        "spans_with_body": spans_with_body,
        "spans_final": len(final_committed) or None,
        "coverage": (
            round(len(committed) / len(final_committed), 3) if final_committed else None
        ),
        "min_segment_samples": min_segment_samples,
        "album_admission_seconds": ALBUM_ADMISSION_SECONDS,
        "real_voices": real_voices,
        "canonical_speakers": len(births),
        "references_per_real_voice": (
            round(len(births) / real_voices, 2) if real_voices else None
        ),
        "birth_states": {
            NO_REFERENCE: states.get(NO_REFERENCE, 0),
            PROVISIONAL: states.get(PROVISIONAL, 0),
            BANKED: states.get(BANKED, 0),
        },
        "unbankable_births": states.get(NO_REFERENCE, 0) + states.get(PROVISIONAL, 0),
        "floors": floors,
        "births": dict(sorted(births.items())),
        "spoken_seconds_by_speaker": {
            speaker: round(seconds, 2)
            for speaker, seconds in sorted(seconds_by_speaker.items())
        },
    }


def report(result: dict) -> None:
    print(f"=== {result['directory']}")
    print(
        f"  spans {result['spans_read']} read ({result['spans_with_body']} with a body) of "
        f"{result['spans_final']} final -- coverage {result['coverage']}, "
        f"source {result['spans_source']}"
    )
    states = result["birth_states"]
    print(
        f"  canonical speakers {result['canonical_speakers']} for "
        f"{result['real_voices']} real voices -- "
        f"{result['references_per_real_voice']} references per voice"
    )
    print(
        f"  born  no_reference {states[NO_REFERENCE]}  provisional {states[PROVISIONAL]}  "
        f"banked {states[BANKED]}   -> unbankable {result['unbankable_births']}"
    )
    print("  birth floor (on embedded seconds)   survivors   refs/voice   banked at birth")
    for floor, row in result["floors"].items():
        print(
            f"    >= {floor:>4} s{' (deployed: none)' if floor == '0.0' else '':<18} "
            f"{row['surviving_canonical_speakers']:>9}   {str(row['references_per_real_voice']):>10}"
            f"   {row['banked_at_birth']:>15}"
        )
    print("  births, in order:")
    for speaker, record in result["births"].items():
        print(
            f"    {speaker}  span {record['span_id']:>4} at t+{record['span_start_seconds']:>7.2f} s  "
            f"spoken {record['spoken_seconds']:>6.3f} s  embedded {record['embedded_seconds']:>6.3f} s"
            f"  {record['state']:<12} {record['text']!r}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("directories", nargs="+", type=Path)
    parser.add_argument(
        "--real-voices",
        type=int,
        default=2,
        help="How many human/program voices the run actually carried (F1/F2/F3 all carried 2).",
    )
    parser.add_argument(
        "--min-segment-samples",
        type=int,
        default=DEPLOYED_MIN_SEGMENT_SAMPLES,
        help="The deployed evidence floor; 8000 = 0.5 s.",
    )
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    results = []
    for directory in args.directories:
        try:
            result = measure(
                directory,
                min_segment_samples=args.min_segment_samples,
                real_voices=args.real_voices,
            )
        except Unreadable as exc:
            print(f"UNREADABLE: {exc}", file=sys.stderr)
            return RC_UNREADABLE
        except (KeyError, TypeError, ValueError) as exc:
            print(f"UNREADABLE: {directory}: {exc.__class__.__name__}: {exc}", file=sys.stderr)
            return RC_UNREADABLE
        results.append(result)
        report(result)

    if args.json:
        args.json.write_text(json.dumps(results, indent=2))
        print(f"\nwrote {args.json}")
    return RC_OK


if __name__ == "__main__":
    raise SystemExit(main())
