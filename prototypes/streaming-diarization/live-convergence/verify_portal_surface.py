#!/usr/bin/env python3
"""Does the reader SEE the selected arm, and is what they see one replacement surface?

Plan §10.5 step 6: "update portal to render `effective_transcript` as one replacement surface".
Steps 1-5 built the rolling authority, put it inside the real runtime and proved the §7.3
snapshot reaches a client unchanged. None of that is worth anything until the words arrive on a
screen -- and a surface that is *appended to* rather than *replaced* would show a corrected
meeting as the meeting said twice while every snapshot gate above stayed green.

So this verifier reads the DOM, not the snapshot:

    audio frames -> LiveServiceRuntime.accept_frame -> ... -> apply_text_revision
      -> snapshot().to_dict() -> json -> the portal script the service actually serves
        -> the transcript node -> parse_transcript -> the grid's own scorer

Three instruments, all production or already-owned: step 4's driver
(`verify_runtime_rolling.run_case`, with `collect_surfaces=True`) supplies every distinct
snapshot the meeting passed through; `LIVE_PORTAL_HTML` supplies the page; and the headless
browser is the T2 tier's own (`tests/test_live_portal._run_node_probe`, `servedPolls`), so there
is one browser emulation in this repo rather than two.

Zero MOSS requests by construction (the decoder replays the §10.2 grid's recorded answers
through the production response validator). Node is required. Reviewers can run this with no GPU:

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \\
      prototypes/streaming-diarization/live-convergence/verify_portal_surface.py

Every case is rendered TWICE -- once from a session with no rolling decoder, once from a session
with one -- so each gate below is a before/after on one instrument.

Exit 0 iff every gate passes. Gates, fixed before the run:

- G1 the base arm is on the screen: the transcript node, parsed back with the production
  parser and scored by the grid's own scorer, gives per-case WER to 6 dp and the trio means
  `.199870` / `.913490`.
- G2 the rolling arm is on the screen: the same reading gives the §10.4 arm, per-case to 6 dp
  and the trio means `.131861` / `.943916`.
- G3 the render is a pure function of the snapshot it was given: at EVERY poll of every case,
  the transcript node equals this file's independent render of that poll's snapshot alone,
  built with the SERVER's own `display_speaker_label` rule. Equality at every poll is the
  replacement property stated exactly -- a page that accumulated would diverge at the first
  poll after the first revision, and a page that mislabelled would diverge at the first
  speaker.
- G4 G3 is not vacuous: across the trio the rendered surface exercises the unattributed token
  and at least two established speakers, and the rolling arm's sequence contains at least one
  poll where `text_revision_version` rose.
- G5 nothing but the surface reaches the screen: no canonical speaker identity, no authority
  name and no `S00`-for-an-established-speaker appears in the transcript node.
- G6 the surface a reader sees is ordered and inside the meeting: rendered segment starts are
  non-decreasing, every end follows its start, and nothing lies outside `[0, duration]`.
- G7 zero fresh MOSS requests.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "prototypes/live-file-gap-context"))
sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import proto_context_arms as bench  # noqa: E402
import verify_runtime_rolling as runtime_rolling  # noqa: E402
import verify_session_text_authority as authority  # noqa: E402
from moss_transcribe_diarize.app.live_portal import LIVE_PORTAL_HTML  # noqa: E402
from moss_transcribe_diarize.app.live_session import (  # noqa: E402
    UNATTRIBUTED_SPEAKER,
    display_speaker_label,
)
from moss_transcribe_diarize.evaluation import Segment  # noqa: E402
from moss_transcribe_diarize.transcript_parser import parse_transcript  # noqa: E402

PLACES = authority.PLACES
SELECTED_ARM = authority.SELECTED_ARM
GRID = runtime_rolling.GRID
SAMPLE_RATE = runtime_rolling.SAMPLE_RATE

# Which authority produced a segment is a fact about the surface, not a word anybody said. If
# one of these ever reaches the transcript node, the page started printing its own bookkeeping.
AUTHORITY_NAMES = ("provisional", "rolling", "final")


def speaker_token(canonical_speaker: str | None, canonical_speakers: tuple[str, ...]) -> str:
    """The `Sxx` a segment must be shown as -- the SERVER's rule, not a second copy of it.

    `display_speaker_label` raises for an identity the session never established, which is the
    same fact about the surface as "nobody was attributed": neither one may be rendered as a
    guess, and both read as the unattributed token.
    """

    if canonical_speaker is None:
        return UNATTRIBUTED_SPEAKER
    try:
        return display_speaker_label(canonical_speaker, canonical_speakers)
    except ValueError:
        return UNATTRIBUTED_SPEAKER


def expected_render(payload: dict[str, Any]) -> str:
    """What the transcript node must hold for this snapshot, built from the snapshot alone.

    Independent of the page: the seconds come from the rate the descriptor declares, the token
    from the server's own label rule, and the order from the surface. Nothing here remembers a
    previous snapshot, which is the whole claim -- if the page needs one and this does not, the
    two disagree at the first correction.
    """

    session = payload["session"]
    rate = payload["descriptor"]["sample_rate"]
    speakers = tuple(session["identity_snapshot"]["canonical_speakers"])
    rows = []
    for segment in session["effective_transcript"]:
        if not segment["text"]:
            continue
        token = speaker_token(segment["canonical_speaker"], speakers)
        rows.append(
            f"[{segment['start_sample'] / rate:g}][{token}]{segment['text']}"
            f"[{segment['end_sample'] / rate:g}]"
        )
    provisional = session.get("provisional")
    if provisional and provisional.get("transcript"):
        rows.append(provisional["transcript"])
    return "\n\n".join(rows)


def render_surfaces(surfaces: list[dict[str, Any]]) -> list[str]:
    """Replay one session's whole sequence of snapshots into one portal, reading the DOM."""

    from test_live_portal import _run_node_probe  # noqa: PLC0415 -- the T2 tier's own browser

    served: list[dict[str, Any]] = []
    for payload in surfaces:
        served.append({"payload": {"snapshot": payload}, "ok": True, "status": 200})
        served.append({"payload": {"events": []}, "ok": True, "status": 200})
    probe = _run_node_probe(LIVE_PORTAL_HTML, "servedPolls", served)
    return probe["transcriptAfterEachPoll"]


def dom_hypothesis(case: str, transcript: str, duration_sec: float):
    """The reader's screen, read back as a transcript nobody in the pipeline helped parse."""

    segments = [
        Segment(item.start, item.end, item.speaker, item.text)
        for row in transcript.split("\n\n")
        for item in parse_transcript(row)
    ]
    del case
    return bench.normalise(segments, duration_sec), segments


def check_case(
    case: str,
    arm_name: str,
    arm: dict[str, Any],
    rendered: list[str],
    duration_sec: float,
) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    surfaces = arm["surfaces"]

    # ---- G3: the render is a pure function of the snapshot it was given.
    if len(rendered) != len(surfaces):
        failures.append(
            f"G3 {case}/{arm_name} portal rendered {len(rendered)} polls of {len(surfaces)} served"
        )
    mismatches = 0
    first_mismatch: dict[str, Any] | None = None
    for index, (payload, dom) in enumerate(zip(surfaces, rendered)):
        want = expected_render(payload)
        if dom != want:
            mismatches += 1
            if first_mismatch is None:
                first_mismatch = {"poll": index, "dom": dom[:400], "expected": want[:400]}
    if mismatches:
        failures.append(
            f"G3 {case}/{arm_name} {mismatches} of {len(rendered)} polls did not render the surface"
        )

    # ---- G4 evidence: what the corpus actually exercised.
    final_dom = rendered[-1] if rendered else ""
    _, dom_segments = dom_hypothesis(case, final_dom, duration_sec)
    tokens = sorted({segment.speaker for segment in dom_segments})
    revisions = [payload["session"]["text_revision_version"] for payload in surfaces]

    # ---- G5: nothing but the surface reaches the screen.
    identities = tuple(surfaces[-1]["session"]["identity_snapshot"]["canonical_speakers"])
    for identity in identities:
        if identity and identity in final_dom:
            failures.append(f"G5 {case}/{arm_name} a canonical identity reached the transcript node")
            break
    for name in AUTHORITY_NAMES:
        if f"[{name}]" in final_dom:
            failures.append(f"G5 {case}/{arm_name} an authority name reached the transcript node")
            break

    # ---- G6: ordered, and inside the meeting.
    starts = [segment.start for segment in dom_segments]
    if starts != sorted(starts):
        failures.append(f"G6 {case}/{arm_name} rendered segment starts are not non-decreasing")
    for segment in dom_segments:
        if segment.end < segment.start or segment.start < 0 or segment.end > duration_sec + 1e-6:
            failures.append(
                f"G6 {case}/{arm_name} segment [{segment.start:g},{segment.end:g}] "
                f"is outside [0,{duration_sec:g}]"
            )
            break

    report = {
        "polls": len(rendered),
        "surfaces": len(surfaces),
        "render_mismatches": mismatches,
        "first_mismatch": first_mismatch,
        "dom_segments": len(dom_segments),
        "effective_segments": len(surfaces[-1]["session"]["effective_transcript"]) if surfaces else 0,
        "speaker_tokens": tokens,
        "text_revision_versions": sorted(set(revisions)),
        "dom_characters": len(final_dom),
    }
    return report, failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default=",".join(bench.CASES))
    parser.add_argument("--grid", type=Path, default=GRID / "grid.json")
    parser.add_argument("--cache", type=Path, default=GRID / "decode-cache/run0.json")
    parser.add_argument("--output", type=Path, default=None)
    cli = parser.parse_args()

    names = [item for item in cli.cases.split(",") if item]
    grid = json.loads(cli.grid.read_text(encoding="utf-8"))
    rolling_expected = grid["summary"]["arms"][SELECTED_ARM]
    base_expected = dict(grid["summary"]["base_control"])
    base_expected["per_case"] = {
        case: {"wer_mean": grid["baseline_live"][case]["wer"]} for case in names
    }
    config = runtime_rolling.deployed_configuration()
    runner = runtime_rolling.ReplayRunner(runtime_rolling.load_replay_entries(cli.cache, names))

    document: dict[str, Any] = {
        "schema": "moss-live-convergence-portal-surface.v1",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "modules": ["moss_transcribe_diarize/app/live_portal.py"],
        "grid": {"path": str(cli.grid.relative_to(REPO)), "arm": SELECTED_ARM},
        "cases": {},
    }
    failures: list[str] = []

    def close(actual: float, want: float) -> bool:
        return round(float(actual), PLACES) == round(float(want), PLACES)

    arms = (("base", False, base_expected, "G1"), ("rolling", True, rolling_expected, "G2"))
    for case in names:
        duration_sec = len(bench.read_pcm(bench.CORPUS / case / "audio.wav")) / 2 / SAMPLE_RATE
        reference = bench.load_reference(case)
        document["cases"][case] = {}
        for arm_name, rolling, expected, gate in arms:
            arm = runtime_rolling.run_case(
                config, runner, case, rolling=rolling, collect_surfaces=True
            )
            rendered = render_surfaces(arm["surfaces"])
            report, case_failures = check_case(case, arm_name, arm, rendered, duration_sec)
            hypothesis, _ = dom_hypothesis(case, rendered[-1] if rendered else "", duration_sec)
            scores = bench.score(reference, hypothesis)
            report["wer"] = scores["wer"]
            report["content_recall"] = scores["content_recall"]
            report["snapshot_wer"] = arm["scores"]["wer"]
            if not close(scores["wer"], expected["per_case"][case]["wer_mean"]):
                case_failures.append(
                    f"{gate} {case}/{arm_name} screen wer {scores['wer']:.6f} != grid "
                    f"{expected['per_case'][case]['wer_mean']:.6f}"
                )
            # The screen and the snapshot are two readings of one session; a difference means
            # the render lost or invented words, not that the arm moved.
            if not close(scores["wer"], arm["scores"]["wer"]):
                case_failures.append(
                    f"{gate} {case}/{arm_name} screen wer {scores['wer']:.6f} != snapshot wer "
                    f"{arm['scores']['wer']:.6f}"
                )
            document["cases"][case][arm_name] = report
            failures.extend(case_failures)

    for arm_name, _, expected, gate in arms:
        mean_wer = sum(document["cases"][case][arm_name]["wer"] for case in names) / len(names)
        mean_recall = sum(
            document["cases"][case][arm_name]["content_recall"] for case in names
        ) / len(names)
        document.setdefault("trio", {})[arm_name] = {
            "wer_mean": mean_wer,
            "content_recall_mean": mean_recall,
        }
        if len(names) == len(bench.CASES):
            if not close(mean_wer, expected["wer"]["mean"]):
                failures.append(
                    f"{gate} trio/{arm_name} screen wer {mean_wer:.6f} != grid "
                    f"{expected['wer']['mean']:.6f}"
                )
            if not close(mean_recall, expected["content_recall"]["mean"]):
                failures.append(
                    f"{gate} trio/{arm_name} screen recall {mean_recall:.6f} != grid "
                    f"{expected['content_recall']['mean']:.6f}"
                )

    # ---- G4: the corpus has to have exercised the rule this run claims to have checked.
    tokens = {
        token
        for case in names
        for arm_name, *_ in arms
        for token in document["cases"][case][arm_name]["speaker_tokens"]
    }
    document["speaker_tokens"] = sorted(tokens)
    if UNATTRIBUTED_SPEAKER not in tokens:
        failures.append(f"G4 no rendered segment exercised {UNATTRIBUTED_SPEAKER}")
    if len(tokens - {UNATTRIBUTED_SPEAKER}) < 2:
        failures.append("G4 fewer than two established speakers reached the screen")
    for case in names:
        if len(document["cases"][case]["rolling"]["text_revision_versions"]) < 2:
            failures.append(f"G4 {case} never showed a poll where a revision had landed")

    document["decode_cost"] = {"requests": runner.requests, "fresh_requests": runner.fresh_requests}
    if runner.fresh_requests:
        failures.append(f"G7 {runner.fresh_requests} fresh MOSS requests")

    document["failures"] = failures
    document["passed"] = not failures

    for case in names:
        for arm_name, *_ in arms:
            report = document["cases"][case][arm_name]
            print(
                f"{case:<18} {arm_name:<8} polls={report['polls']:<4} "
                f"mismatches={report['render_mismatches']:<3} "
                f"dom_segments={report['dom_segments']:<3} "
                f"revisions={report['text_revision_versions'][-1]:<2} "
                f"wer={report['wer']:.6f} recall={report['content_recall']:.6f}"
            )
    for arm_name, _, expected, _ in arms:
        trio = document["trio"][arm_name]
        print(
            f"{'TRIO':<18} {arm_name:<8} wer={trio['wer_mean']:.6f} "
            f"(grid {expected['wer']['mean']:.6f}) "
            f"recall={trio['content_recall_mean']:.6f} "
            f"(grid {expected['content_recall']['mean']:.6f})"
        )
    print(f"speaker tokens on the screen: {document['speaker_tokens']}")
    print(f"decode cost: {document['decode_cost']}")
    if cli.output:
        cli.output.parent.mkdir(parents=True, exist_ok=True)
        cli.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for failure in failures:
        print(f"FAIL {failure}")
    print("PASS" if not failures else f"FAILED {len(failures)} gate(s)")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
