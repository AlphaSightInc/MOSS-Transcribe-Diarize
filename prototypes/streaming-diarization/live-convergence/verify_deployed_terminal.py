"""Did the E4 build reach the DEPLOYED service, and did a real meeting get a terminal pass?

Every M4 measurement so far was taken with the decoder held fixed -- the grid cache for the
base path, a checked-in `file-hypothesis.jsonl` for the terminal decode -- which is what made
"the lifecycle costs the surface nothing" a fact about the code rather than about a run. This
instrument answers the other question, and only that one: on the *running* service, with a
real MOSS decoder and the deployed manifest, does a meeting

  1. hold a complete tape, because the deployment declared a capacity for one,
  2. start a terminal pass after its stop request has already returned,
  3. decode the whole meeting through FILE MODE's own runner and arguments, and
  4. replace its published surface with the result before its audio is released?

It scores from artifacts, not from a live service, so it re-runs from the evidence bundle:
a pass directory in the layout `remeasure_one_case.py` writes, plus the two things that
pass cannot contain because they happen after its replay client stops reading -- the event
page from the stop onward, and the session's final snapshot.

    python verify_deployed_terminal.py --bundle <dir> [--output gates.json]

Exit 0 iff every gate passes. Zero MOSS requests: nothing here decodes.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from moss_transcribe_diarize import live_speaker_accuracy as lsa  # noqa: E402
from moss_transcribe_diarize.app.live_session import LIVE_SAMPLE_RATE  # noqa: E402

# The scoring clock is the paired driver's, imported rather than restated so a change to it
# is a change to both arms at once.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from remeasure_one_case import load_hypothesis, score  # noqa: E402

#: The three §7.4 terminal events, in the order plan §12.3 requires them: a pass announces
#: itself, the revision it proposes lands, and only then is the pass reported complete.
TERMINAL_EVENT_ORDER = (
    "terminal_finalization_started",
    "text_revision_applied",
    "terminal_finalization_completed",
)


def words(text: str) -> list[str]:
    return re.findall(r"[\w']+", text.lower())


def word_stream(rows) -> list[str]:
    return [w for row in rows for w in words(row.text if hasattr(row, "text") else row["text"])]


def terminal_hypothesis(snapshot: dict) -> list:
    """The surface the meeting ended on, read off the session the same way a client would."""

    return [
        lsa.TranscriptSegment(
            start=int(item["start_sample"]) / LIVE_SAMPLE_RATE,
            end=int(item["end_sample"]) / LIVE_SAMPLE_RATE,
            speaker=str(item["canonical_speaker"]),
            text=str(item["text"]),
        )
        for item in snapshot["session"]["effective_transcript"]
    ]


def gate(gates: list, gate_id: str, claim: str, passed: bool, detail) -> None:
    gates.append({"id": gate_id, "claim": claim, "passed": bool(passed), "detail": detail})


def load(bundle: Path) -> dict:
    """Everything the gates read, as plain data, so a reaction test can perturb it."""

    pass_root = bundle / "pass"
    return {
        "snapshot": json.loads((bundle / "final-snapshot.json").read_text())["snapshot"],
        "events": json.loads((bundle / "events-after-stop.json").read_text())["events"],
        "results": json.loads((pass_root / "results.json").read_text()),
        "file_arm": [_row(h) for h in load_hypothesis(pass_root / "file-hypothesis.jsonl")],
        "rolling_arm": [_row(h) for h in load_hypothesis(pass_root / "live-hypothesis.jsonl")],
    }


def _row(segment) -> dict:
    return {"start": segment.start, "end": segment.end, "speaker": segment.speaker, "text": segment.text}


def _hypothesis(rows) -> list:
    return [
        lsa.TranscriptSegment(start=float(r["start"]), end=float(r["end"]), speaker=str(r["speaker"]), text=str(r["text"]))
        for r in rows
    ]


def run(artifacts: dict) -> dict:
    snapshot = {"snapshot": artifacts["snapshot"]}
    events = artifacts["events"]
    results = artifacts["results"]
    case_dir = REPO / results["case_dir"]

    session = snapshot["snapshot"]["session"]
    descriptor = snapshot["snapshot"]["descriptor"]
    completed = next(
        (e for e in events if e["kind"] == "terminal_finalization_completed"), None
    )
    terminal_revision = next(
        (e for e in events if e["kind"] == "text_revision_applied" and e["payload"].get("source") == "terminal"),
        None,
    )

    ref_transcript = lsa.load_reference_jsonl(case_dir / "reference.jsonl")
    ref_activity = lsa.load_reference_speaker_activity_jsonl(case_dir / "reference.jsonl")
    file_arm = _hypothesis(artifacts["file_arm"])
    rolling_arm = _hypothesis(artifacts["rolling_arm"])
    terminal_arm = terminal_hypothesis(snapshot["snapshot"])
    scored = {
        arm: score(ref_transcript, ref_activity, hypothesis)
        for arm, hypothesis in (("file", file_arm), ("rolling", rolling_arm), ("terminal", terminal_arm))
    }

    gates: list = []

    gate(
        gates,
        "D-M4-1",
        "the deployed manifest declares a complete-tape capacity, so a meeting can keep its audio",
        descriptor["bounds"].get("max_tape_bytes") is not None,
        {"max_tape_bytes": descriptor["bounds"].get("max_tape_bytes"),
         "source_revision": descriptor["source_revision"]},
    )

    ordered = [e["kind"] for e in events if e["kind"] in TERMINAL_EVENT_ORDER or e["kind"] == "session_tape_released"]
    tail = ordered[-4:]
    gate(
        gates,
        "D-M4-2",
        "the pass announces itself, lands its revision, reports completion, and only then releases the audio",
        tail == [*TERMINAL_EVENT_ORDER, "session_tape_released"],
        {"observed_tail": tail, "all_terminal_kinds": ordered},
    )

    started = next((e for e in events if e["kind"] == "terminal_finalization_started"), None)
    closed = next((e for e in events if e["kind"] == "session_closed"), None)
    gate(
        gates,
        "D-M4-3",
        "the stop request had already answered when the pass began: the meeting closes first",
        started is not None and closed is not None and closed["seq"] < started["seq"]
        and started["payload"].get("finalization_status") == "running",
        {"session_closed_seq": None if closed is None else closed["seq"],
         "terminal_started_seq": None if started is None else started["seq"],
         "status_at_start": None if started is None else started["payload"].get("finalization_status")},
    )

    gate(
        gates,
        "D-M4-4",
        "the pass decoded the whole meeting: its tape is every accepted sample, with no gap",
        completed is not None
        and completed["payload"].get("outcome") == "finalized"
        and completed["payload"].get("tape_samples") == session["accepted_samples"]
        and session["accepted_samples"] == session["accounted_samples"],
        {"outcome": None if completed is None else completed["payload"].get("outcome"),
         "tape_samples": None if completed is None else completed["payload"].get("tape_samples"),
         "accepted_samples": session["accepted_samples"],
         "accounted_samples": session["accounted_samples"],
         "decode_elapsed_sec": None if completed is None else completed["payload"].get("decode_elapsed_sec")},
    )

    authorities = sorted({item.get("authority") for item in session["effective_transcript"]})
    gate(
        gates,
        "D-M4-5",
        "the published surface is the terminal one: every segment, exactly one replacement",
        authorities == ["terminal"]
        and terminal_revision is not None
        and session["finalization_status"] == "final"
        and session["text_revision_version"] == terminal_revision["payload"]["text_revision_version"],
        {"authorities": authorities,
         "finalization_status": session["finalization_status"],
         "text_revision_version": session["text_revision_version"],
         "terminal_revision_version": None if terminal_revision is None else terminal_revision["payload"]["text_revision_version"],
         "terminal_revised_segments": None if terminal_revision is None else terminal_revision["payload"]["revised_segments"]},
    )

    file_words, terminal_words = word_stream(file_arm), word_stream(terminal_arm)
    same_bounds = len(file_arm) == len(terminal_arm) and all(
        abs(f.start - t.start) < 1e-9 and abs(f.end - t.end) < 1e-9
        for f, t in zip(file_arm, terminal_arm)
    )
    gate(
        gates,
        "D-M4-6",
        "terminal IS the file arm on the same audio -- same words, same segment bounds",
        file_words == terminal_words and same_bounds,
        {"file_words": len(file_words), "terminal_words": len(terminal_words),
         "file_segments": len(file_arm), "terminal_segments": len(terminal_arm),
         "identical_bounds": same_bounds},
    )

    wer = {arm: scored[arm]["tbsa"]["wer"] for arm in scored}
    gate(
        gates,
        "D-M4-7",
        "the deployed terminal pass costs the meeting nothing it had already earned",
        wer["terminal"] <= wer["rolling"] + 1e-9 and abs(wer["terminal"] - wer["file"]) < 1e-9,
        {"wer": wer,
         "der": {arm: scored[arm]["diarization"]["der"] for arm in scored},
         "speaker_accuracy": {arm: scored[arm]["speaker"]["speaker_accuracy"] for arm in scored}},
    )

    released = next((e for e in events if e["kind"] == "session_tape_released"), None)
    gate(
        gates,
        "D-M4-8",
        "the audio is released once the meeting's last listener is done with it",
        released is not None
        and completed is not None
        and released["seq"] > completed["seq"]
        and session["retained_samples"] == 0,
        {"released_seq": None if released is None else released["seq"],
         "completed_seq": None if completed is None else completed["seq"],
         "retained_samples": session["retained_samples"],
         "released_payload": None if released is None else released["payload"]},
    )

    # Plan §7.4: a terminal event carries counts and names, never a word of the meeting. The
    # test is derived from THIS meeting's published words rather than from a list of allowed
    # tokens, so a status vocabulary that happens to overlap ordinary English ("final",
    # "running") cannot trip it and a leaked phrase cannot hide behind one.
    said = word_stream(terminal_arm)
    runs = {tuple(said[i:i + 3]) for i in range(max(0, len(said) - 2))}
    leaks = [
        {"kind": e["kind"], "field": key}
        for e in events
        if e["kind"].startswith("terminal_finalization") or e["kind"] == "session_tape_released"
        for key, value in e["payload"].items()
        if isinstance(value, str)
        and any(tuple(words(value)[i:i + 3]) in runs for i in range(max(0, len(words(value)) - 2)))
    ]
    gate(
        gates,
        "D-M4-9",
        "no terminal event carries a word of the meeting: not one three-word run of it",
        not leaks and len(runs) > 0,
        {"published_three_word_runs": len(runs), "leaks": leaks},
    )

    return {
        "case": results["case"],
        "session_id": snapshot["snapshot"]["session_id"],
        "provenance": results["provenance"],
        "scores": {arm: {"wer": scored[arm]["tbsa"]["wer"],
                         "tbsa": scored[arm]["tbsa"]["composite"],
                         "der": scored[arm]["diarization"]["der"],
                         "speaker_accuracy": scored[arm]["speaker"]["speaker_accuracy"]}
                   for arm in scored},
        "gates": gates,
        "passed": all(g["passed"] for g in gates),
    }


#: Each reaction names one gate and one thing the deployment could have got wrong. A gate
#: that survives its own reaction is measuring nothing, so the selftest fails on that too.
REACTIONS = (
    ("D-M4-1", "the deployment declared no tape capacity",
     lambda a: a["snapshot"]["descriptor"]["bounds"].pop("max_tape_bytes", None)),
    ("D-M4-2", "the audio is released before the pass reports completion",
     lambda a: a["events"].insert(
         next(i for i, e in enumerate(a["events"]) if e["kind"] == "terminal_finalization_completed"),
         a["events"].pop(next(i for i, e in enumerate(a["events"]) if e["kind"] == "session_tape_released")))),
    ("D-M4-3", "the pass ran inside the stop request, before the meeting closed",
     lambda a: a["events"].__setitem__(
         next(i for i, e in enumerate(a["events"]) if e["kind"] == "session_closed"),
         {**next(e for e in a["events"] if e["kind"] == "session_closed"), "seq": 10_000})),
    ("D-M4-4", "the pass decoded a tape shorter than the meeting",
     lambda a: next(e for e in a["events"] if e["kind"] == "terminal_finalization_completed")["payload"]
     .__setitem__("tape_samples", 1)),
    ("D-M4-5", "one segment kept the rolling authority",
     lambda a: a["snapshot"]["session"]["effective_transcript"][0].__setitem__("authority", "rolling")),
    ("D-M4-6", "the terminal pass decoded with different arguments and moved a boundary",
     lambda a: a["snapshot"]["session"]["effective_transcript"][0].__setitem__("end_sample", 12345)),
    ("D-M4-7", "the terminal surface is worse than the rolling one it replaced",
     lambda a: a["snapshot"]["session"]["effective_transcript"].__setitem__(
         0, {**a["snapshot"]["session"]["effective_transcript"][0], "text": "xx xx xx"})),
    ("D-M4-8", "the audio was released while the pass was still reading it",
     lambda a: next(e for e in a["events"] if e["kind"] == "session_tape_released").__setitem__("seq", 0)),
    ("D-M4-9", "a terminal event quoted the meeting",
     lambda a: next(e for e in a["events"] if e["kind"] == "terminal_finalization_completed")["payload"]
     .__setitem__("reason", " ".join(
         w for w in re.findall(r"[\w']+", a["snapshot"]["session"]["effective_transcript"][0]["text"])[:5]))),
)


def selftest(bundle: Path) -> int:
    """Push each gate past its own bound and require exactly that gate to fail."""

    control = run(load(bundle))
    if not control["passed"]:
        print("SELFTEST FAIL: the control bundle does not pass its own gates")
        return 1
    failures = []
    for gate_id, description, mutate in REACTIONS:
        artifacts = load(bundle)
        mutate(artifacts)
        report = run(artifacts)
        broken = {entry["id"] for entry in report["gates"] if not entry["passed"]}
        caught = gate_id in broken
        print(f"[{'PASS' if caught else 'FAIL'}] {gate_id} reacts to: {description}"
              f"{'' if caught else '  (nothing failed)' if not broken else ''}"
              f"{'' if broken == {gate_id} or not caught else f'  also: {sorted(broken - {gate_id})}'}")
        if not caught:
            failures.append(gate_id)
    print("PASS" if not failures else f"FAIL: unreactive gates {failures}")
    return 0 if not failures else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bundle", type=Path, required=True, help="evidence bundle holding pass/, final-snapshot.json, events-after-stop.json")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--selftest", action="store_true", help="perturb the bundle and require each gate to react")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest(args.bundle)

    report = run(load(args.bundle))
    for arm, row in report["scores"].items():
        print(f"  {arm:9s} wer={row['wer']:.6f} tbsa={row['tbsa']:.6f} der={row['der']:.6f} spk={row['speaker_accuracy']:.6f}")
    for entry in report["gates"]:
        print(f"[{'PASS' if entry['passed'] else 'FAIL'}] {entry['id']} {entry['claim']}")
        if not entry["passed"]:
            print(f"       {json.dumps(entry['detail'], ensure_ascii=False)}")
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote: {args.output}")
    print("PASS" if report["passed"] else "FAIL")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
