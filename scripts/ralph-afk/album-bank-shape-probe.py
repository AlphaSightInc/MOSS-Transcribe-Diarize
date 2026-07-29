#!/usr/bin/env python3
"""Measure the album's bank shape on the REAL accuracy fixture, and test the causal claim
iteration 3 of run 20260729-094359 made from invented vectors.

WHY THIS EXISTS.  Two recorded facts in context.md contradict each other, and the newer one
is load-bearing for the authorization argument the loop wants to put to the operator:

  * Phase N decision 7 (iteration 23 of run 20260729-025318): "The album ends a meeting
    holding 3-6 of the 16 minted speakers, only 2-3 banked."
  * Phase N decision 19 (iteration 3 of run 20260729-094359): "Every fixture speaker earns an
    admitted bank; on F1 and F2 only 2 of 12 and 2 of 16 do." -- and therefore ADR-0002's
    measured +5.82 pp "is a property of a corpus in which every speaker earns an admitted
    bank", candidate 55 is the ordering constraint, and candidate 60 buys no correction.

They cannot both be true.  Decision 19 was measured on `sweep-fixpoint-probe.py`'s INVENTED
vectors (a noise spread the probe itself names as its one invention); this probe measures the
same quantities on the fixture's REAL encoder geometry, through production code, so the
premise is checked rather than inherited.

WHAT IT MEASURES.  Three configurations of the production replay, identical but for the
album's admission gate -- the one knob that decides whether an observation becomes a bank
exemplar or a provisional stand-in:

  banked     admission 0.001 s -- every observation is admitted, no stand-ins
  deployed   admission ALBUM_ADMISSION_SECONDS (1.0 s), what 7a4f59c runs
  standin    admission 1e6 s   -- no observation is ever admitted, every reference is a
                                 sub-admission stand-in

`standin` is the falsification control for iteration 3's mechanism.  Its claim is that a
reference set built from provisional stand-ins is mutually confusable, so `assign_speakers`
abstains and the sweep answers `kept_ambiguous` on every unit.  If that mechanism is about
STAND-INS, `standin` must go inert here too.  If `standin` still produces corrections on real
geometry, the mechanism is the real meeting's geometry -- 16 references drawn from 2 voices --
and "stand-in" is a correlate, not the cause.  Either answer re-prices candidates 55/60/65.

WHAT IS REAL.  Everything: the production `FingerprintAlbum`, `WeSpeakerLiveEvidenceProvider`,
`BoundedCausalIdentityPreparer`, `SweepLedger` and `sweep()`, driven by the tracked accuracy
harness `tests/live_identity_accuracy.py`.  The album and `sweep` are wrapped, never replaced:
the wrapper subclasses the production album and calls the production sweep, so what is
measured is what runs.  No product source, no test source and no fixture is modified.

rc=0 measured and printed; rc=2 a named refusal (harness or fixture unreadable).
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))


def refuse(message: str) -> int:
    print(f"REFUSED: {message}")
    return 2


try:
    import live_identity_accuracy as H
    from moss_transcribe_diarize.app.live_identity_album import FingerprintAlbum
    from moss_transcribe_diarize.app.live_identity_sweep import _album_view
except Exception as error:  # noqa: BLE001 - a named refusal, never a traceback
    print(f"REFUSED: the accuracy harness would not import ({error!r})")
    sys.exit(2)


# The admission gates that produce the three bank shapes. Only the middle one is a deployed
# value; the outer two are deliberate extremes chosen to bracket it, not candidate settings.
ALL_BANKED_ADMISSION = 0.001
NO_BANK_ADMISSION = 1.0e6


class _RecordingAlbum(FingerprintAlbum):
    """The production album, plus a handle on the instance the harness built.

    Subclassed rather than mocked: every admission, eviction and stand-in rule under test is
    the production one, and the only added behaviour is remembering the object so its shape
    can be read after the replay.
    """

    latest: "_RecordingAlbum | None" = None

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        type(self).latest = self


def _bank_shape(album: FingerprintAlbum) -> tuple[int, int, int]:
    """(speakers the album heard of, those holding an admitted bank, stand-in only)."""

    speakers = album.speakers()
    banked = sum(1 for speaker in speakers if album.exemplar_count(speaker) > 0)
    return len(speakers), banked, len(speakers) - banked


def _reference_shape(album: FingerprintAlbum, merge_threshold: float) -> tuple[int, int, int]:
    """The sweep's own reference set: (references, banked-backed, stand-in-backed).

    Read through the production `_album_view`, so this is the set `sweep()` actually matches
    against -- including its deliberate admission of stand-ins, which is the line iteration 3
    named as the mechanism.
    """

    references, _leader_of, _merges = _album_view(album, merge_threshold)
    banked = sum(1 for speaker in references if album.exemplar_count(speaker) > 0)
    return len(references), banked, len(references) - banked


def measure(name: str, *, admission_seconds: float, sweep_interval: float = 60.0) -> dict:
    """One meeting under one admission gate, with the album and sweep observed."""

    dispositions: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    sweep_rows: list[tuple[int, int, int, int]] = []
    real_sweep = H.sweep

    def observed_sweep(*, ledger, album, config, merge_threshold):
        revision = real_sweep(
            ledger=ledger, album=album, config=config, merge_threshold=merge_threshold
        )
        dispositions.update(dict(revision.dispositions))
        reasons.update(item.reason for item in revision.corrections)
        total, banked, standin = _reference_shape(album, merge_threshold)
        sweep_rows.append((total, banked, standin, len(revision.corrections)))
        return revision

    H.FingerprintAlbum = _RecordingAlbum
    H.sweep = observed_sweep
    _RecordingAlbum.latest = None
    try:
        result = H.replay(
            H.load_meeting(name),
            policy="album",
            admission_seconds=admission_seconds,
            sweep_interval=sweep_interval,
        )
    finally:
        H.FingerprintAlbum = FingerprintAlbum
        H.sweep = real_sweep

    album = _RecordingAlbum.latest
    speakers, banked, standin = _bank_shape(album) if album is not None else (0, 0, 0)
    # The final sweep's reference set is the one the session-end sweep matched against, which
    # is the shape the deployed system's `finalize_identity` would see.
    final_refs = sweep_rows[-1] if sweep_rows else (0, 0, 0, 0)
    return {
        "meeting": name,
        "true_speakers": H.load_meeting(name).speaker_count,
        "canonical": result.canonical_speaker_count,
        "album_speakers": speakers,
        "banked": banked,
        "standin": standin,
        "final_refs": final_refs[0],
        "final_refs_banked": final_refs[1],
        "final_refs_standin": final_refs[2],
        "sweeps": result.sweeps,
        "corrections": result.corrections,
        "merges": result.merges,
        "residual": result.residual_corrections,
        "dispositions": dict(dispositions),
        "reasons": dict(reasons),
        "live_accuracy": result.live_accuracy,
        "accuracy": result.accuracy,
    }


def run_config(tag: str, admission_seconds: float) -> list[dict]:
    print(f"\n=== {tag}  (album admission {admission_seconds:g} s, sweep 60 s meeting time) ===")
    print(
        f"{'meeting':<12}{'true':>5}{'canon':>6}{'album':>6}{'bank':>5}{'stand':>6}"
        f"{'refs':>6}{'r.bank':>7}{'corr':>6}{'merge':>6}{'resid':>6}"
        f"{'live%':>8}{'final%':>8}"
    )
    rows = []
    for name in H.MEETINGS:
        row = measure(name, admission_seconds=admission_seconds)
        rows.append(row)
        print(
            f"{row['meeting']:<12}{row['true_speakers']:>5}{row['canonical']:>6}"
            f"{row['album_speakers']:>6}{row['banked']:>5}{row['standin']:>6}"
            f"{row['final_refs']:>6}{row['final_refs_banked']:>7}{row['corrections']:>6}"
            f"{row['merges']:>6}{row['residual']:>6}"
            f"{row['live_accuracy'] * 100:>8.2f}{row['accuracy'] * 100:>8.2f}"
        )
    dispositions: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    for row in rows:
        dispositions.update(row["dispositions"])
        reasons.update(row["reasons"])
    banked = sum(row["banked"] for row in rows)
    speakers = sum(row["album_speakers"] for row in rows)
    refs = sum(row["final_refs"] for row in rows)
    refs_banked = sum(row["final_refs_banked"] for row in rows)
    units = sum(dispositions.values())
    ambiguous = dispositions.get("kept_ambiguous", 0)
    mean_live = sum(row["live_accuracy"] for row in rows) / len(rows)
    mean_final = sum(row["accuracy"] for row in rows) / len(rows)
    print(
        f"{'TOTAL':<12}{'':>5}{sum(r['canonical'] for r in rows):>6}{speakers:>6}{banked:>5}"
        f"{speakers - banked:>6}{refs:>6}{refs_banked:>7}"
        f"{sum(r['corrections'] for r in rows):>6}{sum(r['merges'] for r in rows):>6}"
        f"{sum(r['residual'] for r in rows):>6}"
        f"{mean_live * 100:>8.2f}{mean_final * 100:>8.2f}"
    )
    voices = sum(row["true_speakers"] for row in rows)
    canonical = sum(row["canonical"] for row in rows)
    print(f"  album banks        {banked}/{speakers} speakers hold an admitted exemplar")
    print(f"  banked per CANONICAL speaker {banked}/{canonical} "
          f"({banked / canonical * 100:.1f} %) -- the denominator F1/F2 were measured on")
    print(f"  sweep reference set {refs_banked}/{refs} references are bank-backed "
          f"({refs - refs_banked} are provisional stand-ins)")
    # The quantity the real meetings differ on most: F2 held 16 canonical speakers for 2 real
    # voices. Printed beside the ambiguity share because that pairing is what this probe can
    # say about the cause, and it is a correlation over three points, not a proof.
    print(f"  references per real voice {refs}/{voices} = {refs / voices:.2f}")
    print(f"  sweep dispositions  {dict(sorted(dispositions.items()))}")
    print(f"  kept_ambiguous      {ambiguous}/{units} scored units "
          f"({(ambiguous / units * 100) if units else 0:.1f} %)")
    print(f"  correction reasons  {dict(sorted(reasons.items()))}")
    return rows


def main() -> int:
    try:
        H.load_meeting(H.MEETINGS[0])
    except Exception as error:  # noqa: BLE001
        return refuse(f"the accuracy fixture would not load ({error!r})")

    print(
        "Album bank shape on the real accuracy fixture -- production code, real encoder "
        "geometry.\nDeployed matcher 0.35/0.1, k=10, 16 speakers; only the admission gate moves."
    )
    configs = (
        ("banked   (control: nothing is ever a stand-in)", ALL_BANKED_ADMISSION),
        ("deployed (album admission 1.0 s, what 7a4f59c runs)", H.ALBUM_ADMISSION_SECONDS),
        ("standin  (control: nothing is ever admitted)", NO_BANK_ADMISSION),
    )
    measured = {tag: run_config(tag, admission) for tag, admission in configs}

    print("\n=== what this decides ===")
    deployed = measured["deployed (album admission 1.0 s, what 7a4f59c runs)"]
    standin = measured["standin  (control: nothing is ever admitted)"]
    speakers = sum(row["album_speakers"] for row in deployed)
    banked = sum(row["banked"] for row in deployed)
    print(
        f"Phase N decision 19 claims every fixture speaker earns an admitted bank.\n"
        f"  MEASURED at the deployed admission: {banked}/{speakers} album speakers are banked "
        f"({banked / speakers * 100:.1f} %), against F2's 2/16 and F1's 2/12."
    )
    standin_units = sum(sum(row["dispositions"].values()) for row in standin)
    standin_ambiguous = sum(row["dispositions"].get("kept_ambiguous", 0) for row in standin)
    standin_corrections = sum(row["corrections"] for row in standin)
    print(
        f"Iteration 3's mechanism claims a stand-in reference set makes the sweep inert.\n"
        f"  MEASURED with EVERY reference a stand-in: {standin_corrections} corrections, "
        f"kept_ambiguous {standin_ambiguous}/{standin_units} "
        f"({(standin_ambiguous / standin_units * 100) if standin_units else 0:.1f} %)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
