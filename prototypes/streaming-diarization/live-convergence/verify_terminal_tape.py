#!/usr/bin/env python3
"""Does the meeting keep the audio a terminal pass needs -- all of it, only it, and no longer?

Plan E4 step 1, and the precondition PREREGISTRATION-M4 §3 named `P-M4-B`: *no session retains
a complete tape today*. The base path keeps a span until it commits, the rolling witness keeps a
bounded ring of `2 x window`, and `live_tape.py`'s disk store is opt-in behind a declared root
the deployed service does not declare. A terminal 150/120 pass has nothing to run over, so E4
cannot start. This verifier is the measurement that the tape now exists and is faithful:

    audio frames -> LiveServiceRuntime.accept_frame -> LiveCoordinator -> CompleteMixedTape
      -> tape.read()                     (what a terminal reader would be handed)
      -> session_tape_released event     (what a reader outside the process can check)

Every case is run TWICE through the same runtime -- once with a declared tape capacity and once
with none, both with the rolling witness on, which is the deployed posture. So the inertness
gate is a before/after on one instrument rather than a comparison with a number from elsewhere.

Zero MOSS requests by construction: the decoder replays the §10.2 grid's recorded answers
through the production response validator. Reviewers can run this with no GPU:

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \\
      prototypes/streaming-diarization/live-convergence/verify_terminal_tape.py

Exit 0 iff every gate passes. Gates, fixed before the run. G1-G3 are the measurable half of
`G-M4-0` (tape fidelity) and G4-G5 the measurable half of `G-M4-10` (complete-tape retention);
the milestone scores those two ids itself, on the deployed passes, at the M4 exit.

- G1 the tape is the meeting: per case `sample_count == accepted_samples == through_sample`,
  an empty gap manifest, `complete` true, and no degradation.
- G2 the tape is the same audio: the digest the tape accumulated as the frames arrived equals
  the digest of the corpus PCM, and reading it back before release returns bytes that differ
  from the corpus in **zero** samples (max absolute delta reported beside it, because that is
  what separates a tape defect from a decoder reading when a terminal number misses -- R3).
- G3 the tape holds one contiguous interval and admits it: `covers(0, accepted_samples)` is
  true while the meeting owns it, and reading `[0, meeting_end)` is what the finalizer will do.
- G4 zero tapes survive the session: exactly one `session_tape_released` event per session,
  `released` true, `retained_bytes` 0 in the event and in the object.
- G5 the retained bytes are bounded and accounted: peak retained bytes equal
  `accepted_samples x 2` exactly (one buffer, no second copy) and stay within the declared
  capacity; and the capacity table read from production constants reproduces prediction P5 --
  1 920 000 / 5 760 000 / 9 600 000 bytes at 60 / 180 / 300 s.
- G6 the tape costs the meeting nothing: with a tape and without one, identical frozen spans,
  identical committed transcripts, identical committed-prefix hash, identical effective
  surface, identical scores and identical accounting (ADR-0003 D5 from the other direction --
  the meeting is not what degrades). One rolling field is reported rather than compared:
  `retained_high_water_samples` is how much audio the witness's ring happened to hold when the
  pump thread landed, and the no-tape arm is run TWICE so the reader can see that two identical
  configurations already disagree about it. What is gated for that field is its bound.
- G7 a deployment that declares no capacity retains no tape and emits no tape event (D2).
- G8 the tape event carries no transcript text: every string in the payload is a 64-character
  hex digest or a name drawn from the degradation vocabulary read out of `live_tape.py`.
- G9 zero fresh MOSS requests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "prototypes/live-file-gap-context"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import proto_context_arms as bench  # noqa: E402
import verify_runtime_rolling as runtime_rolling  # noqa: E402
from moss_transcribe_diarize.app import live_tape as tape_module  # noqa: E402
from moss_transcribe_diarize.app.live_session import (  # noqa: E402
    LIVE_SAMPLE_RATE,
    PCM16_BYTES_PER_SAMPLE,
)

GRID = REPO / "evidence/live-convergence-0824/M2-rolling-grid"

#: The durations Appendix B's rescope of §12.2 admits, and nothing longer. The bytes are not
#: written down: they are computed from the same two production constants the tape is, so a
#: sample-rate change moves the prediction instead of silently invalidating it.
PREDICTED_CAPACITY_SECONDS = (60, 180, 300)

_HEX64 = re.compile(r"^[0-9a-f]{64}$")

#: The one rolling quantity a second run of the same configuration can legitimately move: how
#: much audio the witness's bounded ring held at the moment the pump thread last looked.
HIGH_WATER = "retained_high_water_samples"


def capacity_table() -> dict[str, int]:
    return {
        str(seconds): seconds * LIVE_SAMPLE_RATE * PCM16_BYTES_PER_SAMPLE
        for seconds in PREDICTED_CAPACITY_SECONDS
    }


def degradation_vocabulary() -> set[str]:
    """Every reason a tape may name, read from production rather than listed here."""

    return {
        value
        for name, value in vars(tape_module).items()
        if name.startswith("TAPE_") and isinstance(value, str) and name.isupper()
    }


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for child in value.values() for item in _strings(child)]
    if isinstance(value, (list, tuple)):
        return [item for child in value for item in _strings(child)]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default=",".join(bench.CASES))
    parser.add_argument("--cache", type=Path, default=GRID / "decode-cache/run0.json")
    parser.add_argument(
        "--tape-bytes",
        type=int,
        default=max(PREDICTED_CAPACITY_SECONDS) * LIVE_SAMPLE_RATE * PCM16_BYTES_PER_SAMPLE,
        help="the capacity the deployment declares; default is the campaign's five-minute cap.",
    )
    parser.add_argument("--output", type=Path, default=None)
    cli = parser.parse_args()

    names = [item for item in cli.cases.split(",") if item]
    config = runtime_rolling.deployed_configuration()
    runner = runtime_rolling.ReplayRunner(runtime_rolling.load_replay_entries(cli.cache, names))

    document: dict[str, Any] = {
        "schema": "moss-live-convergence-terminal-tape.v1",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "modules": [
            "moss_transcribe_diarize/app/live_tape.py",
            "moss_transcribe_diarize/app/live_coordinator.py",
            "moss_transcribe_diarize/app/live_service_runtime.py",
            "moss_transcribe_diarize/app/live_provider_bundle.py",
        ],
        "declared_capacity_bytes": cli.tape_bytes,
        "capacity_table_bytes": capacity_table(),
        "degradation_vocabulary": sorted(degradation_vocabulary()),
        "arms": {"no_tape": {}, "no_tape_repeat": {}, "tape": {}},
    }
    for case in names:
        for arm in ("no_tape", "no_tape_repeat"):
            document["arms"][arm][case] = runtime_rolling.run_case(
                config, runner, case, rolling=True
            )
        document["arms"]["tape"][case] = runtime_rolling.run_case(
            config, runner, case, rolling=True, tape_bytes=cli.tape_bytes
        )
    document["decode_cost"] = {
        "requests": runner.requests,
        "fresh_requests": runner.fresh_requests,
    }

    failures: list[str] = []
    for case in names:
        control = document["arms"]["no_tape"][case]
        taped = document["arms"]["tape"][case]
        tape = taped["tape"]
        accounting = tape["accounting"]
        read = tape["read_before_release"]
        accepted = taped["accepted_samples"]

        # G1 -- the tape is the meeting.
        if accounting["sample_count"] != accepted:
            failures.append(
                f"G1 {case} tape holds {accounting['sample_count']} samples, session accepted {accepted}"
            )
        if accounting["through_sample"] != accepted:
            failures.append(f"G1 {case} tape was asked about the wrong extent")
        if accounting["gaps"]:
            failures.append(f"G1 {case} gap manifest is not empty: {accounting['gaps']}")
        if not accounting["complete"] or accounting["degradation"] is not None:
            failures.append(f"G1 {case} tape is not complete: {accounting['degradation']}")

        if "refused" in read:
            failures.append(f"G3 {case} the tape refused a terminal reader: {read['refused']}")
            continue

        # G2 -- the tape is the same audio.
        if accounting["pcm_sha256"] != tape["audio_sha256"]:
            failures.append(f"G2 {case} tape digest != corpus digest")
        if read["read_sha256"] != tape["audio_sha256"]:
            failures.append(f"G2 {case} tape read-back digest != corpus digest")
        if read["differing_samples"] != 0 or read["max_abs_delta"] != 0:
            failures.append(
                f"G2 {case} tape differs from the corpus in {read['differing_samples']} samples "
                f"(max abs delta {read['max_abs_delta']})"
            )

        # G3 -- the whole meeting is what a reader may ask for.
        if read["read_samples"] != accepted or read["read_bytes"] != accepted * PCM16_BYTES_PER_SAMPLE:
            failures.append(f"G3 {case} a reader was served {read['read_samples']} of {accepted} samples")
        if read["corpus_samples"] != accepted:
            failures.append(f"G3 {case} session accepted {accepted} of {read['corpus_samples']} corpus samples")

        # G4 -- zero tapes survive.
        events = tape["released_events"]
        if len(events) != 1:
            failures.append(f"G4 {case} {len(events)} session_tape_released events, expected 1")
        else:
            released = events[0]
            if not released["released"] or released["retained_bytes"] != 0:
                failures.append(f"G4 {case} the released tape still holds {released['retained_bytes']} bytes")
            if released["pcm_sha256"] != tape["audio_sha256"] or released["sample_count"] != accepted:
                failures.append(f"G4 {case} the released event does not describe the tape that was kept")
            for text in _strings(released):
                if not _HEX64.match(text) and text not in degradation_vocabulary():
                    failures.append(f"G8 {case} tape event carries an unrecognised string {text!r}")
        if accounting["retained_bytes"] != 0 or not accounting["released"]:
            failures.append(f"G4 {case} the tape object survived the meeting")

        # G5 -- bounded and accounted.
        expected_peak = accepted * PCM16_BYTES_PER_SAMPLE
        if accounting["peak_retained_bytes"] != expected_peak:
            failures.append(
                f"G5 {case} peak retained {accounting['peak_retained_bytes']} bytes, "
                f"expected {expected_peak} (one buffer, no second copy)"
            )
        if accounting["peak_retained_bytes"] > cli.tape_bytes:
            failures.append(f"G5 {case} peak retained bytes exceeded the declared capacity")

        # G6 -- the tape costs the meeting nothing.
        for field in (
            "scores",
            "frozen_spans",
            "committed",
            "committed_prefix_hash",
            "text_revision_version",
            "canonical_through_sample",
            "effective_segments",
            "accepted_samples",
            "accounted_samples",
            "committed_samples",
            "terminal_failure",
        ):
            if control[field] != taped[field]:
                failures.append(f"G6 {case} declaring a tape changed {field}")
        for key in sorted(set(control["rolling"]) - {HIGH_WATER}):
            if control["rolling"][key] != taped["rolling"][key]:
                failures.append(f"G6 {case} declaring a tape changed rolling.{key}")
        observed = {
            arm: document["arms"][arm][case]["rolling"][HIGH_WATER]
            for arm in ("no_tape", "no_tape_repeat", "tape")
        }
        document["arms"]["tape"][case]["rolling_high_water_observed"] = observed
        bound = taped["rolling"]["max_retained_samples"]
        for arm, value in observed.items():
            if value > bound:
                failures.append(f"G6 {case} {arm} rolling ring held {value} > {bound}")

        # G7 -- the opt-in posture.
        if "tape" in control:
            failures.append(f"G7 {case} a run that declared no capacity produced a tape")

    predicted = capacity_table()
    for seconds, want in (("60", 1920000), ("180", 5760000), ("300", 9600000)):
        if predicted[seconds] != want:
            failures.append(f"G5 capacity table {seconds}s = {predicted[seconds]}, P5 predicted {want}")

    if document["decode_cost"]["fresh_requests"]:
        failures.append(f"G9 {document['decode_cost']['fresh_requests']} fresh MOSS requests")

    document["failures"] = failures
    document["verdict"] = "PASS" if not failures else "FAIL"
    if cli.output is not None:
        cli.output.parent.mkdir(parents=True, exist_ok=True)
        cli.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for case in names:
        tape = document["arms"]["tape"][case]["tape"]
        accounting = tape["accounting"]
        read = tape["read_before_release"]
        print(
            f"{case:<18} samples={accounting['sample_count']:>7} "
            f"peak_bytes={accounting['peak_retained_bytes']:>8} "
            f"gaps={len(accounting['gaps'])} "
            f"differing_samples={read.get('differing_samples', 'REFUSED')} "
            f"released_bytes={accounting['retained_bytes']} "
            f"digest={accounting['pcm_sha256'][:12]}"
        )
    for case in names:
        observed = document["arms"]["tape"][case].get("rolling_high_water_observed", {})
        print(f"{case:<18} rolling ring high water by arm: {json.dumps(observed, sort_keys=True)}")
    print("capacity table (bytes):", json.dumps(predicted, sort_keys=True))
    print("decode cost:", document["decode_cost"])
    for failure in failures:
        print("FAIL", failure)
    print(document["verdict"])
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
