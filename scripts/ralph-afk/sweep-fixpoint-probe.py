#!/usr/bin/env python3
"""Run the production sweep on a real meeting's measured shape and count its corrections.

Candidate 65's second branch. `identity-evidence-probe.py` measures, from F1's and F2's own
evidence on the deployed `7a4f59c`, that only **2 of 16** canonical speakers ever hold an
admitted album exemplar -- every other canonical speaker holds nothing but the single
sub-admission fragment that minted it. This probe asks what the **production** `sweep()` does
with a ledger and an album in that shape, and answers with its own dispositions rather than
with an argument.

Nothing here is a model of the sweep: `FingerprintAlbum`, `SweepLedger`, `sweep()` and
`LiveIdentityConfig` are imported from `moss_transcribe_diarize`, and the parameters are the
deployed ones read off the host manifest (`min_match_score` 0.35, `min_match_margin` 0.1,
`max_speakers` 16, admission 1.0 s, k=10). What *is* synthetic is the audio: two base voice
directions plus per-unit noise, because the real vectors were never retained -- the ledger is
in-process state and F2's is gone. So this probe speaks for the **shape** of a meeting, not for
F2's particular vectors, and the number that carries weight is the disposition each unit gets,
not the score behind it.

Three scenarios, and the third is the falsification control: a green "0 corrections" means
nothing unless the same harness can produce corrections when the mechanism is removed.

Usage:
    python3 scripts/ralph-afk/sweep-fixpoint-probe.py [--seed N]
Exit 0 when every scenario matched its stated prediction, 1 when one did not.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from moss_transcribe_diarize.app.live_identity import LiveIdentityConfig  # noqa: E402
from moss_transcribe_diarize.app.live_identity_album import (  # noqa: E402
    ALBUM_ADMISSION_SECONDS,
    ALBUM_EXEMPLARS_PER_SPEAKER,
    ALBUM_MIN_MATCH_MARGIN,
    ALBUM_MIN_MATCH_SCORE,
    FingerprintAlbum,
)
from moss_transcribe_diarize.app.live_identity_sweep import MERGED, SweepLedger, sweep  # noqa: E402

DIMENSION = 256
# F2's measured shape on the deployed 7a4f59c: 16 canonical speakers, one holding 74 admitted
# exemplars and one holding 1; the other 14 minted by a single sub-admission fragment each.
BANKED_SPEAKER = "speaker-0001"
BANKED_EXEMPLARS = 74
SECOND_BANKED_SPEAKER = "speaker-0006"
PHANTOMS = 14
# The one quantity this probe invents. F2's vectors were never retained, so the spread of the
# per-unit noise around a base voice is a choice, not a measurement -- which is why the run
# reports the whole sensitivity sweep rather than one value.
DEFAULT_SPREAD = 0.35
# F2 committed 16 abstained spans, 15 of them `speaker_capacity_exceeded`. Their units are
# retained unlabelled (that is what the ledger's wider rule is for), so they are part of the
# shape too.
ABSTAINED_UNITS = 16


def _voice(rng: random.Random) -> list[float]:
    return [rng.gauss(0.0, 1.0) for _ in range(DIMENSION)]


def _near(rng: random.Random, base: list[float], spread: float) -> list[float]:
    return [value + rng.gauss(0.0, spread) for value in base]


def _config() -> LiveIdentityConfig:
    return LiveIdentityConfig(
        max_speakers=16,
        min_match_score=ALBUM_MIN_MATCH_SCORE,
        min_match_margin=ALBUM_MIN_MATCH_MARGIN,
    )


def _build(
    rng: random.Random,
    *,
    phantoms_are_banked: bool,
    spread: float = DEFAULT_SPREAD,
    second_bank_is_same_voice: bool = True,
):
    """One meeting's album and ledger in F2's measured shape.

    `phantoms_are_banked` is the single lever the control flips: whether the 14 fragment-born
    speakers hold an admitted bank (a reference that is a centroid over evidence) or a
    provisional stand-in (a reference that *is* one retained unit's own vector).
    """

    album = FingerprintAlbum(
        admission_seconds=ALBUM_ADMISSION_SECONDS,
        exemplars_per_speaker=ALBUM_EXEMPLARS_PER_SPEAKER,
    )
    ledger = SweepLedger()
    voice_a = _voice(rng)
    # F2's two banked speakers may be its two real voices or one voice banked twice; the
    # evidence cannot say which, so both readings are run and the finding is what survives both.
    voice_second = voice_a if second_bank_is_same_voice else _voice(rng)
    span_id = 0

    # The dominant voice: a real bank, and its units labelled as the live path labelled them.
    # F2 measured two speakers with an admitted bank: one holding 74 exemplars and one holding a
    # single exemplar. Both are reproduced -- a bank of one is still a bank, and it is the only
    # thing separating "could have moved" from "could be merged".
    for index in range(BANKED_EXEMPLARS + 1):
        second = index >= BANKED_EXEMPLARS
        speaker = SECOND_BANKED_SPEAKER if second else BANKED_SPEAKER
        vector = _near(rng, voice_second if second else voice_a, spread)
        album.observe(canonical_speaker=speaker, vector=vector, duration_sec=2.0, span_id=span_id)
        ledger.record(
            span_id=span_id,
            local_speaker="S01",
            canonical_speaker=speaker,
            vector=vector,
            duration_sec=2.0,
        )
        span_id += 1

    # The fragmentation candidate 55 measures and the sweep exists to heal: the same voice,
    # born again under a new id from one short fragment.
    phantom_duration = 2.0 if phantoms_are_banked else 0.6
    for index in range(PHANTOMS):
        speaker = f"speaker-{index + 100:04d}"
        vector = _near(rng, voice_a, spread)
        album.observe(
            canonical_speaker=speaker,
            vector=vector,
            duration_sec=phantom_duration,
            span_id=span_id,
        )
        ledger.record(
            span_id=span_id,
            local_speaker="S01",
            canonical_speaker=speaker,
            vector=vector,
            duration_sec=phantom_duration,
        )
        span_id += 1

    # The abstained spans: retained, unlabelled, and the ones a sweep has the most to say about.
    for _ in range(ABSTAINED_UNITS):
        ledger.record(
            span_id=span_id,
            local_speaker="S01",
            canonical_speaker=None,
            vector=_near(rng, voice_a, spread),
            duration_sec=0.6,
        )
        span_id += 1

    return album, ledger


def _rematched(revision) -> int:
    """Corrections that re-matched a unit, as opposed to following a merge.

    The distinction is the whole finding: a `MERGED` correction is the album collapsing two
    ids and relabelling whatever hung off the absorbed one, while `REASSIGNED` / `LABELLED`
    is the sweep saying this unit's evidence points somewhere else -- the thing ADR-0002's
    +5.82 pp was measured on, and the thing the fixture has and a real meeting does not.
    """

    return sum(1 for correction in revision.corrections if correction.reason != MERGED)


def _run(name: str, album: FingerprintAlbum, ledger: SweepLedger):
    revision = sweep(ledger=ledger, album=album, config=_config())
    banked = sum(1 for speaker in album.speakers() if album.exemplar_count(speaker) > 0)
    print(f"-- {name}")
    print(
        f"   album            {len(album.speakers())} speakers, {banked} with an admitted bank, "
        f"{len(album.speakers()) - banked} on a provisional stand-in"
    )
    print(f"   ledger           {revision.swept_spans} spans / {revision.swept_units} units")
    print(f"   dispositions     {dict(revision.dispositions)}")
    print(
        f"   corrections      {len(revision.corrections)} "
        f"({_rematched(revision)} re-matched, {len(revision.corrections) - _rematched(revision)} "
        f"from a merge)   merges {len(revision.merges)}"
    )
    return revision


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20260729)
    args = parser.parse_args(argv)

    failures = []

    # 1. F2's measured shape. Prediction: zero corrections. A fragment-born speaker's reference
    #    *is* the retained unit that minted it, so that unit scores 1.0 against itself and can
    #    never be beaten by the margin rule -- the exact units the sweep exists to re-home are
    #    the ones it is structurally unable to move.
    for same_voice in (True, False):
        reading = "one voice banked twice" if same_voice else "two real voices"
        album, ledger = _build(
            random.Random(args.seed), phantoms_are_banked=False, second_bank_is_same_voice=same_voice
        )
        revision = _run(
            f"F2's measured shape, 14 of 16 speakers on a provisional stand-in ({reading})",
            album,
            ledger,
        )
        if _rematched(revision) != 0:
            failures.append(
                f"expected no re-matched correction in the deployed shape ({reading}), "
                f"got {_rematched(revision)}"
            )

    # The spread is the probe's one invented quantity, so the finding is reported across it
    # rather than at one value. A conclusion that held only at 0.35 would be a property of this
    # script.
    print("-- sensitivity: the same shape across the invented noise spread")
    for spread in (0.10, 0.20, 0.35, 0.50, 0.80):
        album, ledger = _build(random.Random(args.seed), phantoms_are_banked=False, spread=spread)
        revision = sweep(ledger=ledger, album=album, config=_config())
        print(
            f"   spread {spread:.2f}   corrections {len(revision.corrections):3d}   "
            f"merges {len(revision.merges):2d}   {dict(revision.dispositions)}"
        )

    # 2. The same meeting with the stand-in mechanism removed: the phantoms hold admitted banks,
    #    so their references are centroids over evidence rather than one unit's own vector.
    #    Prediction: corrections appear. If they do not, the diagnosis above is wrong and the
    #    cause is somewhere else entirely.
    album, ledger = _build(random.Random(args.seed), phantoms_are_banked=True)
    control = _run("control: the same 16 speakers, all with admitted banks", album, ledger)
    if len(control.corrections) == 0:
        failures.append("the control produced no corrections, so the harness proves nothing")

    # 3. The positive control the first scenario needs to be readable: one unit labelled with a
    #    speaker whose reference is a *different* voice. A sweep that cannot move even this is
    #    broken rather than blocked, and the two verdicts must not look alike.
    rng = random.Random(args.seed + 1)
    album = FingerprintAlbum(
        admission_seconds=ALBUM_ADMISSION_SECONDS, exemplars_per_speaker=ALBUM_EXEMPLARS_PER_SPEAKER
    )
    ledger = SweepLedger()
    voice_a, voice_b = _voice(rng), _voice(rng)
    for index in range(6):
        album.observe(
            canonical_speaker="speaker-0001", vector=_near(rng, voice_a, 0.2), duration_sec=2.0, span_id=index
        )
        album.observe(
            canonical_speaker="speaker-0002", vector=_near(rng, voice_b, 0.2), duration_sec=2.0, span_id=index
        )
    # A voice-A unit the live path had labelled as speaker-0002, which is what a mislabel is.
    ledger.record(
        span_id=99,
        local_speaker="S01",
        canonical_speaker="speaker-0002",
        vector=_near(rng, voice_a, 0.2),
        duration_sec=2.0,
    )
    mislabel = _run("positive control: one voice-A unit labelled speaker-0002", album, ledger)
    if _rematched(mislabel) != 1:
        failures.append(f"expected the mislabel re-matched once, got {_rematched(mislabel)}")

    for line in failures:
        print(f"FAIL: {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
