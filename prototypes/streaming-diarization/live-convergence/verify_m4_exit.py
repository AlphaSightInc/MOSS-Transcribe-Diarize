"""Score the 14 preregistered M4 gates on a fresh paired pass of all five cases.

`PREREGISTRATION-M4.md` fixed the gates, their clocks and their comparators on campaign
iteration 22, before any terminal finalizer existed. This driver is the scoring half. It reads
one fresh batch of paired passes taken against the deployed service - trio + three-minute +
five-minute, two runs each - and says which of those gates the terminal surface meets.

Three properties keep the scoring honest, and they are the same three `verify_m3_disposition.py`
carried:

  * the gate id set is **parsed out of the preregistration**, both directions, so editing the
    table without editing this driver fails the command;
  * every bound this driver applies must appear **verbatim in that gate's own row** - numbers
    and the one prose comparator alike - so a threshold cannot be tuned here to pass;
  * `--selftest` pushes each gate's input past its own bound and requires the gate to flip.

Instruments, named per gate and never blended:

  deployed(fresh)          this batch's `results.json` / trace / summary, from the running service
  deployed(M4-three-minute) iteration 23's paired passes - the ONLY surviving rolling arm for
                           `lex_adam_frank`, because a pass now publishes its terminal surface
                           in `live-hypothesis.jsonl` and no longer records the rolling one
  in-memory(fresh)         `verify_terminal_lifecycle.py`, run now, no service and no MOSS
  fresh-run                pytest node ids and the file-mode decoder A/B probe, run now

Usage:
  python verify_m4_exit.py --fresh-root /tmp/m4-exit-<stamp> [--output out.json]
  python verify_m4_exit.py --fresh-root <root> --selftest

The batch layout this reads is what `run_paired_passes.sh` plus `run_paired_case.sh` write:

  <fresh-root>/trio-{A,B}/            the three 60 s cases, one pass each
  <fresh-root>/keyu5m-{A,B}/          the five-minute case
  <fresh-root>/three-minute/adam3m-{A,B}/   the three-minute case, in its own root because
                                      `measure_m4_baseline.single_case_pass_dir` refuses an
                                      ambiguous one
  <fresh-root>/restart-post-ps.txt    the service restart this batch was taken behind (G-M4-8)
  <fresh-root>/console/runner.log     pass start times, written by the pass scripts

Exit 0 iff every gate passes and the gate-set contract holds.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import wave
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

import measure_m4_baseline as baseline  # noqa: E402
import verify_m2_exit as m2  # noqa: E402
from evaluator_v2 import Segment as V2Segment, speech_regions_from_wav  # noqa: E402

PREREGISTRATION = HERE / "PREREGISTRATION-M4.md"
THREE_MINUTE_BUNDLE = REPO / "evidence/live-convergence-0824/M4-three-minute/passes"
LIFECYCLE_DRIVER = HERE / "verify_terminal_lifecycle.py"
FILE_MODE_PROBE = HERE / "probe_file_mode_decode_identity.py"

TRIO_CASES = baseline.TRIO_CASES
FIVE_MINUTE_CASE = baseline.FIVE_MINUTE_CASE
THREE_MINUTE_CASE = baseline.THREE_MINUTE_CASE
CASES = (*TRIO_CASES, THREE_MINUTE_CASE, FIVE_MINUTE_CASE)
RUNS = baseline.RUNS
SAMPLE_RATE = m2.SAMPLE_RATE

# ---- every bound below is checked against the preregistration row it claims to come from ----
G8_WER_TOLERANCE = baseline.G8_WER_TOLERANCE          # .010, plan G8
TERMINAL_DER_TOLERANCE = baseline.TERMINAL_DER_TOLERANCE  # .020, owner-directed prerelease
ROLLING_WER = {                       # G-M4-3, the rolling surface terminal replaces
    "lex_bill_ackman": 0.204545,
    "lex_javier_milei": 0.096000,
    "lex_keyu_jin": 0.093525,
    FIVE_MINUTE_CASE: 0.082079,
}
ROLLING_V2 = {                        # G-M4-4, content recall / matched-word speaker accuracy
    "lex_bill_ackman": (0.926136, 0.920455),
    "lex_javier_milei": (0.920000, 0.920000),
    "lex_keyu_jin": (0.985612, 0.985612),
    FIVE_MINUTE_CASE: (0.957592, 0.954856),
}
#: The three-minute row states its comparator in prose rather than a number, because the case
#: had no pass when the preregistration was written. The words are the bound; the number is
#: read from the pass that acquired the case and is reported with its provenance.
THREE_MINUTE_COMPARATOR = "that pass's own rolling arm"
TAPE_CAPACITY_BYTES = 9600000         # G-M4-10, the five-minute cap
COMBINED_RTF_BOUND = 1.0              # G-M4-11
ROLLING_DEPTH_BOUND = 1
ZERO = 0
#: Three rows state their bound in words rather than digits. The words are what the gate-set
#: contract checks, because "0" is a substring of almost any number and quoting a digit that
#: the row never wrote would make the contract agree with itself.
NO_SURVIVING_TAPE = "zero tapes survive"
NO_ADMISSION_REFUSALS = "zero admission refusals"
NO_STALE_COMPLETIONS = "zero stale completions"
NO_FAILED_WINDOWS = "zero failed windows"
NO_LEAK = "zero"
FILE_MODE_DECODER_DIGEST = "ad381d8bd247e4a8ebe56240dfbc29c0b5a86ffb35a2fcb411c07bbd5b7707f2"
ALREADY_FINALIZED = "already_finalized"
ALREADY_FINALIZED_TESTS = (
    "tests/test_live_terminal_finalizer.py::TerminalFinalizerSessionTest"
    "::test_the_proposal_replaces_the_whole_surface_and_a_second_one_is_refused",
    "tests/test_live_text_revision.py::test_terminal_finalization_replaces_the_whole_surface_once",
)
TERMINAL_EVENT_KINDS = (
    "terminal_finalization_started",
    "terminal_finalization_completed",
    "terminal_finalization_failed",
    "session_tape_released",
)


# ------------------------------------------------------------------ the preregistered table


def parse_gate_rows(preregistration: Path = PREREGISTRATION) -> dict[str, str]:
    """`{gate id: the whole row text}` for every row of the preregistration's §5 table."""

    rows: dict[str, str] = {}
    for line in preregistration.read_text().splitlines():
        match = re.match(r"^\|\s*(G-M4-\d+)\b", line)
        if match:
            rows[match.group(1)] = line
    return rows


def _renderings(value: float | int | str) -> list[str]:
    """Every way the preregistration might legitimately have written this bound.

    Integers gain their space- and comma-grouped forms: a byte capacity reads as `9 600 000`
    in prose and `9600000` in code, and a gate-set contract that cannot see through the
    grouping would force the bound to be restated rather than quoted.
    """

    if isinstance(value, str):
        return [value]
    if isinstance(value, int) or float(value).is_integer():
        whole = int(value)
        text = str(whole)
        grouped = f"{whole:,}"
        return sorted({text, grouped, grouped.replace(",", " "), f"{float(value):.2f}",
                       f"{float(value):.2f}".lstrip("0")})
    out: set[str] = set()
    for places in (2, 3, 4, 6):
        text = f"{value:.{places}f}"
        out.add(text)
        out.add(text.lstrip("0"))
        trimmed = text.rstrip("0")
        if trimmed.endswith("."):
            continue
        out.add(trimmed)
        out.add(trimmed.lstrip("0"))
    return sorted(out)


def bound_stated_in_row(row: str, value: float | int | str) -> bool:
    return any(rendering in row for rendering in _renderings(value))


# ------------------------------------------------------------------ reading one fresh pass


def case_paths(fresh_root: Path, three_minute_root: Path, case: str, run: str) -> dict[str, Path]:
    if case == THREE_MINUTE_CASE:
        return baseline.three_minute_paths(three_minute_root, run)
    return m2.case_paths(fresh_root, case, run)


def corpus_pcm(audio: Path) -> tuple[bytes, dict]:
    """The mono 16 kHz PCM16 bytes a live pass feeds the transport, and what they are."""

    with wave.open(str(audio), "rb") as handle:
        facts = {
            "channels": handle.getnchannels(),
            "sample_rate": handle.getframerate(),
            "sample_width": handle.getsampwidth(),
            "frames": handle.getnframes(),
        }
        raw = handle.readframes(handle.getnframes())
    return raw, facts


def trace_records(trace: Path) -> list[dict]:
    return [json.loads(line) for line in m2.trace_lines(trace) if line.strip()]


def session_facts(paths: dict[str, Path], duration_sec: float, pcm: bytes) -> dict:
    """Everything the mechanism gates read off one live session, from its own trace.

    The quality axes are NOT read here: `measure_m4_baseline` owns those, so a gate can never
    be scored against a number this driver computed for itself.
    """

    trace = paths["trace"]
    if not trace.exists() and not trace.with_suffix(trace.suffix + ".gz").exists():
        return {"present": False}

    records = trace_records(trace)
    events = [
        {"seq": rec["event"].get("seq"), "kind": rec["event"].get("kind"),
         "payload": rec["event"].get("payload") or {}}
        for rec in records
        if rec.get("kind") == "service_event"
    ]
    wait = next((rec for rec in records if rec.get("kind") == "terminal_finalization_wait"), None)
    terminal_record = next((rec for rec in records if rec.get("kind") == "terminal"), None)
    session = ((terminal_record or {}).get("snapshot") or {}).get("session") or {}

    def one(kind: str) -> dict | None:
        found = [event for event in events if event["kind"] == kind]
        return found[-1] if found else None

    def accounting_event() -> dict | None:
        """The terminal pass's accounting, from whichever event carried it.

        A pass that decoded the meeting and was then refused reports through
        `terminal_finalization_failed`, and its accounting is the same payload the completed
        event carries. Reading only the completed event would make a refused pass look like a
        pass that never ran - which is the one thing the M4 exit must not do.
        """

        carriers = [
            event for event in events
            if event["kind"] in {"terminal_finalization_completed", "terminal_finalization_failed"}
            and "tape_samples" in event["payload"]
        ]
        return carriers[-1] if carriers else None

    summary = json.loads(paths["summary"].read_text()) if paths["summary"].exists() else {}
    accepted = summary.get("accepted_samples")
    tape = one("session_tape_released")
    tape_payload = (tape or {}).get("payload") or {}
    expected_digest = (
        hashlib.sha256(pcm[: int(accepted) * 2]).hexdigest()
        if isinstance(accepted, int) and len(pcm) >= accepted * 2
        else None
    )
    terminal_revisions = [
        event for event in events
        if event["kind"] in {"text_revision_applied", "text_revision_refused"}
        and (event["payload"].get("source") == "terminal")
    ]
    published = [
        json.loads(line)
        for line in paths["live_hypothesis"].read_text().splitlines()
        if line.strip()
    ] if paths["live_hypothesis"].exists() else []

    facts = {
        "present": True,
        "summary": {
            key: summary.get(key)
            for key in (
                "status", "failure_kind", "accepted_samples", "accounted_samples",
                "frame_count", "finalization_status", "finalization_waited",
                "canonical_decode_rtf_p95",
            )
        },
        "wait": None if wait is None else {
            key: wait.get(key)
            for key in (
                "stop_finalization_status", "finalization_status", "waited", "polls",
                "elapsed_seconds", "deadline_seconds", "text_revision_version",
            )
        },
        "events": {
            "session_closed": one("session_closed"),
            "terminal_started": one("terminal_finalization_started"),
            "terminal_completed": one("terminal_finalization_completed"),
            "terminal_failed": one("terminal_finalization_failed"),
            "tape_released": tape,
            "terminal_accounting": accounting_event(),
            "terminal_revisions": terminal_revisions,
            "rolling_revisions": [
                event for event in events
                if event["kind"] == "text_revision_applied"
                and event["payload"].get("source") == "rolling"
            ],
            "kinds": sorted({event["kind"] for event in events}),
            "last_frame_seq": max(
                [rec.get("seq") for rec in records if rec.get("kind") == "frame_accepted"] or [-1]
            ),
        },
        "snapshot": {
            "finalization_status": session.get("finalization_status"),
            "text_revision_version": session.get("text_revision_version"),
            "accepted_samples": session.get("accepted_samples"),
            "accounted_samples": session.get("accounted_samples"),
            "retained_samples": session.get("retained_samples"),
            "authorities": sorted(
                {str(item.get("authority")) for item in (session.get("effective_transcript") or [])}
            ),
            "surface_segments": len(session.get("effective_transcript") or []),
        },
        "tape": {
            **{key: tape_payload.get(key) for key in (
                "sample_count", "through_sample", "gaps", "pcm_sha256", "peak_retained_bytes",
                "retained_bytes", "capacity_bytes", "complete", "degradation", "released",
                "refused_samples",
            )},
            "expected_pcm_sha256": expected_digest,
            "corpus_comparison": pcm_comparison(pcm, accepted, tape_payload.get("pcm_sha256")),
        },
        "file_sha256": m2.sha256_bytes(paths["file_hypothesis"]),
        "published_text": " ".join(str(row.get("text") or "") for row in published),
        "terminal_payload_strings": terminal_payload_strings(events),
    }
    facts["m2_session"] = m2_session_view(paths["trace"], duration_sec)
    return facts


def pcm_comparison(pcm: bytes, accepted: int | None, digest: str | None) -> dict:
    """What the corpus WAV says about the tape, beside the digest (preregistration §5 G-M4-0).

    Digest equality is the gate; this is what explains a G-M4-1 delta when the digest differs,
    so it is computed whether or not the digest matched.
    """

    if not isinstance(accepted, int) or len(pcm) < accepted * 2:
        return {"comparable": False}
    window = pcm[: accepted * 2]
    return {
        "comparable": True,
        "corpus_samples": len(pcm) // 2,
        "compared_samples": accepted,
        "corpus_pcm_sha256": hashlib.sha256(window).hexdigest(),
        "digest_matches": digest == hashlib.sha256(window).hexdigest(),
    }


def terminal_payload_strings(events: list[dict]) -> list[dict]:
    return [
        {"kind": event["kind"], "field": key, "value": value}
        for event in events
        if event["kind"] in TERMINAL_EVENT_KINDS
        for key, value in event["payload"].items()
        if isinstance(value, str)
    ]


def m2_session_view(trace: Path, duration_sec: float) -> dict:
    """The M2 exit's own reading of a session: queues, decode seconds, accounting."""

    node = m2.read_session(trace, duration_sec)
    canonical = node.get("canonical") or []
    rolling = node.get("rolling_completed") or []
    base_sec = sum(float(item["decode_elapsed_sec"] or 0.0) for item in canonical)
    witness_sec = sum(float(item["decode_elapsed_sec"] or 0.0) for item in rolling)
    queued = node.get("rolling_queued") or []
    return {
        "audio_sec": duration_sec,
        "base_decode_sec": round(base_sec, 6),
        "witness_decode_sec": round(witness_sec, 6),
        "combined_rtf": round((base_sec + witness_sec) / duration_sec, 6) if duration_sec else None,
        "rolling_max_depth": node.get("rolling_max_depth"),
        "rolling_final_depth": node.get("rolling_final_depth"),
        "admission_refusals": sum(1 for item in queued if not item["admitted"]),
        "stale_completions": max([int(item["stale_completions"] or 0) for item in rolling] or [0]),
        "windows_failed": [item["outcome"] for item in rolling if item["outcome"] not in {"applied", "refused"}],
        "windows_completed": len(rolling),
        "windows_planned": len(queued),
    }


# ------------------------------------------------------------------ batch order and readiness


def pass_clock(fresh_root: Path) -> dict[str, str]:
    """`{pass label: UTC start}`, from the clock the pass scripts themselves write.

    The drivers do not share one: the trio and single-case drivers stamp `provenance.timestamp`
    in local time and the five-minute driver stamps nothing at all. `runner.log` is written by
    the pass scripts for every pass in the batch, in UTC, in one format - so it is the batch's
    clock, and the driver stamps are kept beside it as a cross-check rather than as the order.
    """

    log = fresh_root / "console/runner.log"
    clock: dict[str, str] = {}
    if not log.exists():
        return clock
    for line in log.read_text().splitlines():
        match = re.match(r"^=== (\S+) START (\S+) ===$", line.strip())
        if match:
            clock.setdefault(match.group(1), match.group(2))
    return clock


def provenance_timestamp(paths: dict[str, Path]) -> str | None:
    if not paths["results"].exists():
        return None
    return (json.loads(paths["results"].read_text()).get("provenance") or {}).get("timestamp")


def case_order_in_pass(paths: dict[str, Path], case: str) -> int:
    """Where this case sits in the pass that produced it - the driver's own written order."""

    if not paths["results"].exists():
        return 0
    data = json.loads(paths["results"].read_text())
    if "cases" not in data:
        return 0
    for index, node in enumerate(data["cases"]):
        if node.get("case_id") == case:
            return index
    return 0


def case_arm_order(paths: dict[str, Path], case: str) -> list[str] | None:
    """Which arm this pass decoded first - the readiness reading needs to say what came before."""

    if not paths["results"].exists():
        return None
    data = json.loads(paths["results"].read_text())
    if "results" in data:
        return data.get("arm_order") or list(data["results"].keys())
    for node in data.get("cases", []):
        if node.get("case_id") == case:
            return list(node.get("arm_order") or [])
    return None


def service_restart(fresh_root: Path) -> dict:
    """The restart this batch was taken behind, from the artifact captured at restart time."""

    record = fresh_root / "restart-post-ps.txt"
    text = record.read_text() if record.exists() else ""
    line = next((row for row in text.splitlines()[1:] if row.strip()), "")
    started = line.strip().split("  ")[0] if line else ""
    match = re.search(r"^\s*(\d+)\s+(\w{3}\s+\w{3}\s+\d+\s+\d\d:\d\d:\d\d\s+\d{4})", line)
    return {
        "record": str(record.relative_to(fresh_root)) if record.exists() else None,
        "present": bool(match),
        "pid": match.group(1) if match else None,
        "started_at": match.group(2) if match else started,
        "started_at_utc": _read((fresh_root / "restart-utc.txt")),
        "descriptor_identical_across_restart": descriptor_identical(fresh_root),
    }


def _utc(stamp: str | None) -> "datetime | None":
    """One clock for the batch: the UTC stamps the restart and the pass scripts both wrote."""

    if not stamp:
        return None
    try:
        return datetime.strptime(stamp.strip(), "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def _restart_precedes_batch(restart: dict, order: list[dict]) -> bool | None:
    """Was every scored session captured after the restart that made session one cold?"""

    started = _utc(restart.get("started_at_utc"))
    stamps = [_utc(item.get("pass_started_at")) for item in order]
    if started is None or not stamps or any(stamp is None for stamp in stamps):
        return None
    return all(started < stamp for stamp in stamps)


def _read(path: Path) -> str | None:
    return path.read_text().strip() if path.exists() else None


def descriptor_identical(fresh_root: Path) -> bool | None:
    pre, post = fresh_root / "restart-pre.json", fresh_root / "restart-post.json"
    if not (pre.exists() and post.exists()):
        return None
    return json.loads(pre.read_text()) == json.loads(post.read_text())


# ------------------------------------------------------------------ collection


def collect(fresh_root: Path, three_minute_root: Path, run_instruments: bool = True) -> dict:
    quality = baseline.measure(fresh_root, three_minute_root)
    three_minute_rolling = read_three_minute_rolling()

    specs = baseline.m4_cases(three_minute_root)
    clock = pass_clock(fresh_root)
    sessions: dict[str, dict] = {}
    order: list[dict] = []
    for case in CASES:
        spec = specs[case]
        pcm, facts = corpus_pcm(spec["audio"])
        for run in RUNS:
            paths = case_paths(fresh_root, three_minute_root, case, run)
            key = f"{case}/{run}"
            sessions[key] = session_facts(paths, spec["duration_sec"], pcm)
            sessions[key]["audio"] = {**facts, "path": str(spec["audio"].relative_to(REPO))}
            order.append(
                {
                    "session": key,
                    "pass_label": paths["results"].parent.name,
                    "pass_started_at": clock.get(paths["results"].parent.name),
                    "provenance_timestamp": provenance_timestamp(paths),
                    "case_order_in_pass": case_order_in_pass(paths, case),
                    "arm_order": case_arm_order(paths, case),
                }
            )
    order.sort(key=lambda item: (item["pass_started_at"] or "9999", item["case_order_in_pass"]))
    for index, item in enumerate(order):
        item["ordinal"] = index

    evidence = {
        "fresh_root": str(fresh_root),
        "three_minute_root": str(three_minute_root),
        "quality": quality,
        "sessions": sessions,
        "order": order,
        "service_restart": service_restart(fresh_root),
        "file_mode_hypotheses": file_mode_hypotheses(fresh_root, three_minute_root),
        "three_minute_rolling": three_minute_rolling,
    }
    evidence["lifecycle"] = run_lifecycle() if run_instruments else {"skipped": True}
    evidence["already_finalized"] = run_named_tests() if run_instruments else {"skipped": True}
    evidence["file_mode_probe"] = run_file_mode_probe() if run_instruments else {"skipped": True}
    return evidence


def read_three_minute_rolling() -> dict:
    """The three-minute case's rolling arm, from the pass that acquired the case.

    A pass no longer records one: since the client waits for terminal finalization, the
    surface it writes to `live-hypothesis.jsonl` IS the terminal surface. The comparator the
    G-M4-3/G-M4-4 rows name therefore comes from iteration 23's paired passes, which are the
    same deployed rolling geometry and agreed with each other word for word.
    """

    spec = baseline.m4_cases(THREE_MINUTE_BUNDLE)[THREE_MINUTE_CASE]
    reference = [V2Segment(**row) for row in baseline.load_reference_rows(spec["reference"])]
    regions = speech_regions_from_wav(spec["audio"]) if spec["audio"].exists() else None
    node: dict = {"source": str(THREE_MINUTE_BUNDLE.relative_to(REPO)), "runs": {}}
    for run in RUNS:
        paths = baseline.three_minute_paths(THREE_MINUTE_BUNDLE, run)
        arms = baseline.arm_scores(paths["results"], THREE_MINUTE_CASE)
        if "live" not in arms:
            continue
        axes = baseline.deployed_axes(arms["live"])
        axes["v2"] = baseline.v2_axes(reference, paths["live_hypothesis"], regions)
        node["runs"][run] = axes
    values = list(node["runs"].values())
    node["runs_agree"] = len({json.dumps(item, sort_keys=True) for item in values}) == 1
    if values:
        # Read from run A and reported with both runs beside it. The two passes are word
        # identical on every gated axis and differ only in segment extents, which is the
        # difference iteration 23 measured at `3.3e-4` -- so `runs_agree` is false on the
        # whole node and true on everything a gate reads. Both facts are recorded.
        node["comparator_run"] = "A"
        node["wer"] = node["runs"]["A"]["wer"]
        node["content_recall"] = (node["runs"]["A"].get("v2") or {}).get("content_recall")
        node["matched_word_speaker_accuracy"] = (node["runs"]["A"].get("v2") or {}).get(
            "matched_word_speaker_accuracy"
        )
        gated = [
            {item["wer"] for item in values},
            {(item.get("v2") or {}).get("content_recall") for item in values},
            {(item.get("v2") or {}).get("matched_word_speaker_accuracy") for item in values},
        ]
        node["runs_agree_on_gated_axes"] = all(len(axis) == 1 for axis in gated)
    return node


def file_mode_hypotheses(fresh_root: Path, three_minute_root: Path) -> dict:
    """Every file arm this batch produced, against the checked-in comparator for its case.

    Every case the 2026-08-24 baseline holds a file arm for is compared, not only the five
    M4 gates: the diagnostic `acquired_*` case never enters a promotion denominator, but its
    file output is exactly as much a regression tripwire as the trio's (G-M2-8's own rule).
    The three-minute case has no pre-campaign baseline, so its comparator is the file arm of
    the pass that acquired it.
    """

    baseline_root = REPO / "prototypes/live-file-gap-baseline-20260824"
    comparators = {
        node["case_id"]: baseline_root / f"trio-60s/{node['case_id']}/file-hypothesis.jsonl"
        for node in json.loads((baseline_root / "trio-60s/results.json").read_text())["cases"]
    }
    comparators[FIVE_MINUTE_CASE] = baseline_root / "keyu-5m/file-hypothesis.jsonl"
    comparators[THREE_MINUTE_CASE] = baseline.three_minute_paths(THREE_MINUTE_BUNDLE, "A")["file_hypothesis"]

    rows: dict[str, dict] = {}
    for case, comparator in comparators.items():
        expected = m2.sha256_bytes(comparator)
        row = {"comparator": str(comparator.relative_to(REPO)), "expected": expected}
        for run in RUNS:
            paths = case_paths(fresh_root, three_minute_root, case, run)
            row[run] = m2.sha256_bytes(paths["file_hypothesis"])
        row["identical"] = expected is not None and all(row[run] == expected for run in RUNS)
        rows[case] = row
    return rows


def run_lifecycle() -> dict:
    """`verify_terminal_lifecycle.py`, run now: the failure arm no healthy pass can show."""

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "lifecycle.json"
        proc = subprocess.run(
            [sys.executable, str(LIFECYCLE_DRIVER), "--output", str(out)],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        document = json.loads(out.read_text()) if out.exists() else {}
    arms = document.get("arms") or {}
    return {
        "exit_code": proc.returncode,
        "passed": document.get("passed"),
        "failures": document.get("failures"),
        "decode_failure": {
            case: {
                "finalization_status": node["after"]["finalization_status"],
                "authorities": node["after"]["authorities"],
                "surface_segments": node["after"]["segments"],
                "surface_preserved": node["after_surface"] == node["at_stop_surface"],
                "scores_preserved": node["after_scores"] == node["at_stop_scores"],
                "failure_events": [
                    event["payload"].get("reason")
                    for event in node["events"]
                    if event["kind"] == "terminal_finalization_failed"
                ],
            }
            for case, node in (arms.get("decode_failure") or {}).items()
        },
        "healthy_second_pass": {
            case: {
                "finalization_status": (node.get("second_pass") or {}).get("finalization_status"),
                "surface_unchanged": (node.get("second_pass") or {}).get("surface_unchanged"),
                "text_revision_version": (node.get("second_pass") or {}).get("text_revision_version"),
                "after_text_revision_version": node["after"]["text_revision_version"],
            }
            for case, node in (arms.get("healthy") or {}).items()
        },
        "tail": proc.stdout.strip().splitlines()[-1:] or [proc.stderr[-200:]],
    }


def run_named_tests() -> dict:
    """The two T2 tests that name the `already_finalized` refusal G-M4-9 asks for."""

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *ALREADY_FINALIZED_TESTS, "-q"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    sources = "\n".join((REPO / test.split("::")[0]).read_text() for test in ALREADY_FINALIZED_TESTS)
    return {
        "exit_code": proc.returncode,
        "node_ids": list(ALREADY_FINALIZED_TESTS),
        "refusal_name_asserted": sources.count(f'"{ALREADY_FINALIZED}"'),
        "tail": proc.stdout.strip().splitlines()[-1:] or [proc.stderr[-200:]],
    }


def run_file_mode_probe() -> dict:
    proc = subprocess.run(
        [sys.executable, str(FILE_MODE_PROBE), str(REPO)], cwd=REPO, capture_output=True, text=True
    )
    if proc.returncode != 0:
        return {"exit_code": proc.returncode, "digest": None, "stderr": proc.stderr[-400:]}
    return {"exit_code": 0, "digest": hashlib.sha256(proc.stdout.encode()).hexdigest()}


# ------------------------------------------------------------------ small readers


def arm_axes(evidence: dict, case: str, run: str, arm: str) -> dict:
    return ((evidence["quality"]["cases"].get(case) or {}).get("runs") or {}).get(run, {}).get(arm) or {}


def per_run(evidence: dict):
    for case in CASES:
        for run in RUNS:
            yield case, run, f"{case}/{run}"


def rolling_wer_bound(evidence: dict, case: str) -> float | None:
    if case == THREE_MINUTE_CASE:
        return evidence["three_minute_rolling"].get("wer")
    return ROLLING_WER[case]


def rolling_v2_bounds(evidence: dict, case: str) -> tuple[float | None, float | None]:
    if case == THREE_MINUTE_CASE:
        node = evidence["three_minute_rolling"]
        return node.get("content_recall"), node.get("matched_word_speaker_accuracy")
    return ROLLING_V2[case]


# ------------------------------------------------------------------ gates


def evaluate(evidence: dict) -> dict:
    gates: dict[str, dict] = {}
    sessions = evidence["sessions"]

    # ---- G-M4-0  tape fidelity
    tape_rows = {}
    for _case, _run, key in per_run(evidence):
        node = sessions.get(key) or {}
        tape = node.get("tape") or {}
        summary = node.get("summary") or {}
        tape_rows[key] = {
            "accepted_samples": summary.get("accepted_samples"),
            "tape_samples": tape.get("sample_count"),
            "through_sample": tape.get("through_sample"),
            "gaps": tape.get("gaps"),
            "pcm_sha256": tape.get("pcm_sha256"),
            "expected_pcm_sha256": tape.get("expected_pcm_sha256"),
            "corpus_comparison": tape.get("corpus_comparison"),
            "faithful": (
                tape.get("sample_count") is not None
                and tape.get("sample_count") == summary.get("accepted_samples")
                and tape.get("through_sample") == summary.get("accepted_samples")
                and tape.get("gaps") == []
                and tape.get("pcm_sha256") is not None
                and tape.get("pcm_sha256") == tape.get("expected_pcm_sha256")
            ),
        }
    gates["G-M4-0"] = {
        "pass": bool(tape_rows) and all(row["faithful"] for row in tape_rows.values()),
        "arm": "terminal",
        "instrument": "deployed(fresh)",
        "bounds": {},
        "value": {
            "sessions": len(tape_rows),
            "faithful": sum(1 for row in tape_rows.values() if row["faithful"]),
            "per_session": tape_rows,
        },
    }

    # ---- G-M4-1  terminal WER within .010 of the paired file arm, per case
    # ---- G-M4-2  terminal DER within .020 of the paired file arm, per case
    for gate_id, axis, tolerance in (
        ("G-M4-1", "wer", G8_WER_TOLERANCE),
        ("G-M4-2", "der", TERMINAL_DER_TOLERANCE),
    ):
        rows = {}
        for case, run, key in per_run(evidence):
            live = arm_axes(evidence, case, run, "live").get(axis)
            file_arm = arm_axes(evidence, case, run, "file").get(axis)
            distance = None if live is None or file_arm is None else round(abs(live - file_arm), 6)
            rows[key] = {
                "terminal": live,
                "paired_file": file_arm,
                "distance": distance,
                "inside": distance is not None and distance <= tolerance,
            }
        gates[gate_id] = {
            "pass": bool(rows) and all(row["inside"] for row in rows.values()),
            "arm": "terminal",
            "instrument": "deployed(fresh)",
            "bounds": {"tolerance": tolerance},
            "value": {
                "max_distance": max([row["distance"] for row in rows.values() if row["distance"] is not None] or [None]),
                "per_session": rows,
            },
        }

    # ---- G-M4-3  terminal WER no worse than the rolling surface it replaces
    rows = {}
    for case, run, key in per_run(evidence):
        terminal = arm_axes(evidence, case, run, "live").get("wer")
        bound = rolling_wer_bound(evidence, case)
        rows[key] = {
            "terminal": terminal,
            "rolling": bound,
            "delta": None if terminal is None or bound is None else round(terminal - bound, 6),
            "no_worse": terminal is not None and bound is not None and terminal <= bound,
        }
    gates["G-M4-3"] = {
        "pass": bool(rows) and all(row["no_worse"] for row in rows.values()),
        "arm": "terminal vs rolling",
        "instrument": "deployed(fresh) vs deployed(M4-three-minute) for the 3-minute case",
        "bounds": {**ROLLING_WER, THREE_MINUTE_CASE: THREE_MINUTE_COMPARATOR},
        "value": {
            "three_minute_comparator": evidence["three_minute_rolling"].get("wer"),
            "failing": [key for key, row in rows.items() if not row["no_worse"]],
            "per_session": rows,
        },
    }

    # ---- G-M4-4  evaluator-v2 content recall and matched-word speaker accuracy, no regression
    rows = {}
    for case, run, key in per_run(evidence):
        v2 = arm_axes(evidence, case, run, "live").get("v2") or {}
        recall_bound, matched_bound = rolling_v2_bounds(evidence, case)
        recall, matched = v2.get("content_recall"), v2.get("matched_word_speaker_accuracy")
        rows[key] = {
            "content_recall": recall,
            "content_recall_bound": recall_bound,
            "matched_word_speaker_accuracy": matched,
            "matched_word_speaker_accuracy_bound": matched_bound,
            "no_regression": (
                recall is not None and recall_bound is not None and recall >= recall_bound
                and matched is not None and matched_bound is not None and matched >= matched_bound
            ),
        }
    gates["G-M4-4"] = {
        "pass": bool(rows) and all(row["no_regression"] for row in rows.values()),
        "arm": "terminal vs rolling",
        "instrument": "deployed(fresh) vs deployed(M4-three-minute) for the 3-minute case",
        "bounds": {
            **{f"{case}.content_recall": ROLLING_V2[case][0] for case in ROLLING_V2},
            **{f"{case}.matched_word": ROLLING_V2[case][1] for case in ROLLING_V2},
            THREE_MINUTE_CASE: THREE_MINUTE_COMPARATOR,
        },
        "value": {
            "three_minute_comparator": {
                "content_recall": evidence["three_minute_rolling"].get("content_recall"),
                "matched_word_speaker_accuracy": evidence["three_minute_rolling"].get(
                    "matched_word_speaker_accuracy"
                ),
            },
            "failing": [key for key, row in rows.items() if not row["no_regression"]],
            "per_session": rows,
        },
    }

    # ---- G-M4-5  accepted samples == terminal accounted samples, exactly
    rows = {}
    for _case, _run, key in per_run(evidence):
        node = sessions.get(key) or {}
        summary = node.get("summary") or {}
        snapshot = node.get("snapshot") or {}
        completed = ((node.get("events") or {}).get("terminal_accounting") or {}).get("payload") or {}
        accepted = summary.get("accepted_samples")
        rows[key] = {
            "accepted_samples": accepted,
            "accounted_samples": summary.get("accounted_samples"),
            "snapshot_accepted": snapshot.get("accepted_samples"),
            "snapshot_accounted": snapshot.get("accounted_samples"),
            "terminal_end_sample": completed.get("end_sample"),
            "terminal_decoded_audio_samples": completed.get("decoded_audio_samples"),
            "exact": (
                summary.get("status") == "succeeded"
                and accepted is not None
                and accepted == summary.get("accounted_samples")
                and snapshot.get("accepted_samples") == snapshot.get("accounted_samples")
                and completed.get("end_sample") == accepted
                and completed.get("decoded_audio_samples") == accepted
            ),
        }
    gates["G-M4-5"] = {
        "pass": bool(rows) and all(row["exact"] for row in rows.values()),
        "arm": "terminal",
        "instrument": "deployed(fresh)",
        "bounds": {},
        "value": {"failing": [key for key, row in rows.items() if not row["exact"]], "per_session": rows},
    }

    # ---- G-M4-6  the asynchronous lifecycle
    rows = {}
    for _case, _run, key in per_run(evidence):
        node = sessions.get(key) or {}
        events = node.get("events") or {}
        wait = node.get("wait") or {}
        started = (events.get("terminal_started") or {}).get("payload") or {}
        completed = (events.get("terminal_completed") or {}).get("payload") or {}
        rolling_statuses = {
            (event["payload"] or {}).get("finalization_status")
            for event in events.get("rolling_revisions") or []
        }
        rows[key] = {
            "not_started_before_stop": rolling_statuses == {"not_started"},
            "started_says_running": started.get("finalization_status") == "running",
            "stop_returned_before_completion": wait.get("stop_finalization_status") == "running",
            "polled_while_running": (wait.get("polls") or 0) >= 1 and bool(wait.get("waited")),
            "completed_says_final": completed.get("finalization_status") == "final",
            "snapshot_final": (node.get("snapshot") or {}).get("finalization_status") == "final",
            "lifecycle": (
                rolling_statuses == {"not_started"}
                and started.get("finalization_status") == "running"
                and wait.get("stop_finalization_status") == "running"
                and (wait.get("polls") or 0) >= 1
                and completed.get("finalization_status") == "final"
                and (node.get("snapshot") or {}).get("finalization_status") == "final"
            ),
        }
    gates["G-M4-6"] = {
        "pass": bool(rows) and all(row["lifecycle"] for row in rows.values()),
        "arm": "terminal",
        "instrument": "deployed(fresh)",
        "bounds": {},
        "value": {"failing": [key for key, row in rows.items() if not row["lifecycle"]], "per_session": rows},
    }

    # ---- G-M4-7  a terminal failure preserves and exports the rolling surface
    lifecycle = evidence["lifecycle"]
    failure_rows = lifecycle.get("decode_failure") or {}
    preserved = all(
        row["finalization_status"] == "failed"
        and row["authorities"] == ["rolling"]
        and row["surface_segments"] > 0
        and row["surface_preserved"]
        and row["scores_preserved"]
        and row["failure_events"]
        for row in failure_rows.values()
    )
    gates["G-M4-7"] = {
        "pass": bool(failure_rows) and preserved and lifecycle.get("exit_code") == 0,
        "arm": "terminal failure",
        "instrument": "in-memory(fresh)",
        "bounds": {},
        "value": {
            "driver_exit_code": lifecycle.get("exit_code"),
            "cases": failure_rows,
            "note": (
                "no healthy pass can show this: the arm is the decode-failure runtime "
                "verify_terminal_lifecycle.py builds, run fresh by this command"
            ),
        },
    }

    # ---- G-M4-8  cold and warm readiness, reported separately
    restart = evidence["service_restart"]
    readiness = {}
    for item in evidence["order"]:
        key = item["session"]
        node = sessions.get(key) or {}
        completed = ((node.get("events") or {}).get("terminal_accounting") or {}).get("payload") or {}
        wait = node.get("wait") or {}
        duration = ((node.get("m2_session") or {}).get("audio_sec")) or None
        decode = completed.get("decode_elapsed_sec")
        readiness[key] = {
            "ordinal": item["ordinal"],
            "pass_started_at": item["pass_started_at"],
            "readiness": "cold" if item["ordinal"] == 0 else "warm",
            "arm_order": item.get("arm_order"),
            "terminal_decode_elapsed_sec": decode,
            "finalization_status": completed.get("finalization_status"),
            "terminal_decode_rtf": None if decode is None or not duration else round(decode / duration, 6),
            "stop_to_final_sec": wait.get("elapsed_seconds"),
            "polls": wait.get("polls"),
        }
    restart_precedes_batch = _restart_precedes_batch(restart, evidence["order"])
    cold = [row for row in readiness.values() if row["readiness"] == "cold"]
    warm = [row for row in readiness.values() if row["readiness"] == "warm"]
    reported = all(
        row["terminal_decode_elapsed_sec"] is not None and row["stop_to_final_sec"] is not None
        for row in readiness.values()
    )
    gates["G-M4-8"] = {
        "pass": (
            bool(cold)
            and bool(warm)
            and reported
            and bool(restart.get("present"))
            and restart_precedes_batch is True
            and all(row["pass_started_at"] for row in readiness.values())
        ),
        "arm": "terminal",
        "instrument": "deployed(fresh)",
        "bounds": {},
        "value": {
            "service_restart": {**restart, "precedes_every_pass": restart_precedes_batch},
            "cold_sessions": [row["ordinal"] for row in cold],
            "what_preceded_the_cold_pass": [row.get("arm_order") for row in cold],
            "warm_sessions": len(warm),
            "cold": {
                "terminal_decode_elapsed_sec": [row["terminal_decode_elapsed_sec"] for row in cold],
                "stop_to_final_sec": [row["stop_to_final_sec"] for row in cold],
            },
            "warm": {
                "terminal_decode_rtf": m2.distribution(
                    [row["terminal_decode_rtf"] for row in warm if row["terminal_decode_rtf"] is not None]
                ),
                "stop_to_final_sec": m2.distribution(
                    [row["stop_to_final_sec"] for row in warm if row["stop_to_final_sec"] is not None]
                ),
            },
            "per_session": readiness,
        },
    }

    # ---- G-M4-9  terminal replaces the surface exactly once, from sample 0
    rows = {}
    for _case, _run, key in per_run(evidence):
        node = sessions.get(key) or {}
        events = node.get("events") or {}
        revisions = events.get("terminal_revisions") or []
        applied = [event for event in revisions if event["kind"] == "text_revision_applied"]
        payload = (applied[0]["payload"] if applied else {})
        accepted = (node.get("summary") or {}).get("accepted_samples")
        rows[key] = {
            "terminal_revisions": len(revisions),
            "applied": len(applied),
            "start_sample": payload.get("start_sample"),
            "end_sample": payload.get("end_sample"),
            "accepted_samples": accepted,
            "authorities": (node.get("snapshot") or {}).get("authorities"),
            "once_from_zero": (
                len(revisions) == 1
                and len(applied) == 1
                and payload.get("start_sample") == 0
                and payload.get("end_sample") == accepted
                and (node.get("snapshot") or {}).get("authorities") == ["terminal"]
            ),
        }
    second = evidence["already_finalized"]
    lifecycle_second = lifecycle.get("healthy_second_pass") or {}
    second_refused = second.get("exit_code") == 0 and (second.get("refusal_name_asserted") or 0) >= 2 and all(
        row["finalization_status"] == "final"
        and row["surface_unchanged"]
        and row["text_revision_version"] == row["after_text_revision_version"]
        for row in lifecycle_second.values()
    )
    gates["G-M4-9"] = {
        "pass": bool(rows) and all(row["once_from_zero"] for row in rows.values()) and second_refused,
        "arm": "terminal",
        "instrument": "deployed(fresh) + fresh-run + in-memory(fresh)",
        "bounds": {"refusal": ALREADY_FINALIZED},
        "value": {
            "failing": [key for key, row in rows.items() if not row["once_from_zero"]],
            "second_proposal_refused": second_refused,
            "already_finalized_tests": second,
            "healthy_second_pass": lifecycle_second,
            "per_session": rows,
        },
    }

    # ---- G-M4-10  complete-tape retention
    rows = {}
    for _case, _run, key in per_run(evidence):
        node = sessions.get(key) or {}
        events = node.get("events") or {}
        tape = node.get("tape") or {}
        released = events.get("tape_released") or {}
        completed = events.get("terminal_accounting") or {}
        accepted = (node.get("summary") or {}).get("accepted_samples")
        rows[key] = {
            "through_sample": tape.get("through_sample"),
            "accepted_samples": accepted,
            "released": tape.get("released"),
            "retained_bytes_after": tape.get("retained_bytes"),
            "snapshot_retained_samples": (node.get("snapshot") or {}).get("retained_samples"),
            "peak_retained_bytes": tape.get("peak_retained_bytes"),
            "capacity_bytes": tape.get("capacity_bytes"),
            "released_seq": released.get("seq"),
            "terminal_evidence_seq": completed.get("seq"),
            "retained": (
                tape.get("through_sample") == accepted
                and tape.get("released") is True
                and tape.get("retained_bytes") == ZERO
                and (node.get("snapshot") or {}).get("retained_samples") == ZERO
                and isinstance(tape.get("peak_retained_bytes"), int)
                and tape["peak_retained_bytes"] <= TAPE_CAPACITY_BYTES
                and released.get("seq") is not None
                and completed.get("seq") is not None
                and released["seq"] > completed["seq"]
            ),
        }
    gates["G-M4-10"] = {
        "pass": bool(rows) and all(row["retained"] for row in rows.values()),
        "arm": "terminal",
        "instrument": "deployed(fresh)",
        "bounds": {"peak_retained_bytes": TAPE_CAPACITY_BYTES, "surviving_tapes": NO_SURVIVING_TAPE},
        "value": {
            "max_peak_retained_bytes": max(
                [row["peak_retained_bytes"] for row in rows.values() if row["peak_retained_bytes"] is not None] or [None]
            ),
            "failing": [key for key, row in rows.items() if not row["retained"]],
            "per_session": rows,
        },
    }

    # ---- G-M4-11  terminal work never enters the capture clock
    rows = {}
    for _case, _run, key in per_run(evidence):
        node = sessions.get(key) or {}
        view = node.get("m2_session") or {}
        events = node.get("events") or {}
        closed = events.get("session_closed") or {}
        started = events.get("terminal_started") or {}
        rows[key] = {
            "combined_rtf": view.get("combined_rtf"),
            "base_rtf": None if not view.get("audio_sec") else round(
                (view.get("base_decode_sec") or 0.0) / view["audio_sec"], 6
            ),
            "rolling_max_depth": view.get("rolling_max_depth"),
            "admission_refusals": view.get("admission_refusals"),
            "stale_completions": view.get("stale_completions"),
            "windows_failed": view.get("windows_failed"),
            "session_closed_seq": closed.get("seq"),
            "terminal_started_seq": started.get("seq"),
            "last_frame_seq": events.get("last_frame_seq"),
            "off_the_capture_clock": (
                view.get("combined_rtf") is not None
                and view["combined_rtf"] < COMBINED_RTF_BOUND
                and (view.get("rolling_max_depth") or 0) <= ROLLING_DEPTH_BOUND
                and view.get("admission_refusals") == ZERO
                and view.get("stale_completions") == ZERO
                and not view.get("windows_failed")
                and closed.get("seq") is not None
                and started.get("seq") is not None
                and started["seq"] > closed["seq"]
            ),
        }
    gates["G-M4-11"] = {
        "pass": bool(rows) and all(row["off_the_capture_clock"] for row in rows.values()),
        "arm": "terminal + capture",
        "instrument": "deployed(fresh)",
        "bounds": {
            "combined_rtf": COMBINED_RTF_BOUND,
            "rolling_max_depth": ROLLING_DEPTH_BOUND,
            "admission_refusals": NO_ADMISSION_REFUSALS,
            "stale_completions": NO_STALE_COMPLETIONS,
            "windows_failed": NO_FAILED_WINDOWS,
        },
        "value": {
            "max_combined_rtf": max(
                [row["combined_rtf"] for row in rows.values() if row["combined_rtf"] is not None] or [None]
            ),
            "failing": [key for key, row in rows.items() if not row["off_the_capture_clock"]],
            "per_session": rows,
        },
    }

    # ---- G-M4-12  file mode byte-identical, both readings
    file_rows = evidence["file_mode_hypotheses"]
    probe = evidence["file_mode_probe"]
    gates["G-M4-12"] = {
        "pass": all(row["identical"] for row in file_rows.values())
        and probe.get("digest") == FILE_MODE_DECODER_DIGEST,
        "arm": "file",
        "instrument": "deployed(fresh) + fresh-run",
        "bounds": {"decoder_digest": FILE_MODE_DECODER_DIGEST},
        "value": {
            "a_hypotheses_byte_identical": all(row["identical"] for row in file_rows.values()),
            "b_decoder_digest": probe.get("digest"),
            "per_case": file_rows,
            "note": (
                "the three-minute case has no pre-campaign baseline: its comparator is the "
                "file arm of the pass that acquired it (iteration 23)"
            ),
        },
    }

    # ---- G-M4-13  no terminal event carries a word of the meeting
    rows = {}
    for _case, _run, key in per_run(evidence):
        node = sessions.get(key) or {}
        said = str(node.get("published_text") or "").split()
        runs_of_three = {tuple(said[index:index + 3]) for index in range(max(0, len(said) - 2))}
        leaks = []
        for item in node.get("terminal_payload_strings") or []:
            words = str(item["value"]).split()
            if any(tuple(words[index:index + 3]) in runs_of_three for index in range(max(0, len(words) - 2))):
                leaks.append({"kind": item["kind"], "field": item["field"]})
        rows[key] = {
            "published_three_word_runs": len(runs_of_three),
            "payload_strings": len(node.get("terminal_payload_strings") or []),
            "leaks": leaks,
            "clean": not leaks and len(runs_of_three) > 0,
        }
    gates["G-M4-13"] = {
        "pass": bool(rows) and all(row["clean"] for row in rows.values()),
        "arm": "terminal",
        "instrument": "deployed(fresh)",
        "bounds": {"leaks": NO_LEAK},
        "value": {
            "distinct_payload_strings": sorted(
                {item["value"] for key in rows for item in (sessions.get(key) or {}).get("terminal_payload_strings") or []}
            ),
            "failing": [key for key, row in rows.items() if not row["clean"]],
            "per_session": rows,
        },
    }
    return gates


def check_gate_set(gates: dict) -> dict:
    """The preregistration decides which gates exist, and the bounds must be quoted from it."""

    rows = parse_gate_rows()
    missing = sorted(set(rows) - set(gates))
    extra = sorted(set(gates) - set(rows))
    unstated: list[str] = []
    for gate_id, gate in gates.items():
        row = rows.get(gate_id, "")
        for name, bound in gate["bounds"].items():
            if not bound_stated_in_row(row, bound):
                unstated.append(f"{gate_id}.{name}={bound}")
    return {
        "pass": not missing and not extra and not unstated,
        "preregistered_gates": len(rows),
        "scored_gates": len(gates),
        "missing_from_scoring": missing,
        "scored_but_not_preregistered": extra,
        "bounds_not_quoted_from_the_row": unstated,
    }


# ------------------------------------------------------------------ selftest


def selftest_fixture(evidence: dict) -> dict:
    """The batch a fully converged deployment would have produced, for reaction testing only.

    A gate that is already failing cannot demonstrate that it reacts: it was never passing.
    Three gates fail on the scored batch, all on `lex_adam_frank`, all because that meeting's
    terminal proposal was refused rather than published. So the reaction fixture writes what
    the service would have written had the proposal been accepted - the file arm's own scores,
    a completed event, one applied revision covering the meeting - and, because `terminal ==
    file` then breaks the two no-regression gates on that same case by one and two words, it
    also moves that case's rolling comparator onto the file arm.

    That second edit is exactly the finding: on this case no batch can satisfy all fourteen
    preregistered gates at once, so the only all-pass fixture is a synthetic one. It is used
    for nothing but measuring reactions, and never for a scored number.
    """

    fixture = copy.deepcopy(evidence)
    for run in RUNS:
        key = f"{THREE_MINUTE_CASE}/{run}"
        node = fixture["sessions"][key]
        file_axes = copy.deepcopy(arm_axes(fixture, THREE_MINUTE_CASE, run, "file"))
        fixture["quality"]["cases"][THREE_MINUTE_CASE]["runs"][run]["live"] = file_axes
        accepted = (node.get("summary") or {}).get("accepted_samples")
        carrier = (node.get("events") or {}).get("terminal_accounting") or {"seq": 0, "payload": {}}
        completed = {
            "seq": carrier.get("seq"),
            "kind": "terminal_finalization_completed",
            "payload": {**carrier.get("payload", {}), "applied": True, "refusal": None,
                        "finalization_status": "final"},
        }
        node["events"]["terminal_completed"] = completed
        node["events"]["terminal_accounting"] = completed
        node["events"]["terminal_revisions"] = [
            {
                "seq": (carrier.get("seq") or 1) - 1,
                "kind": "text_revision_applied",
                "payload": {"source": "terminal", "start_sample": 0, "end_sample": accepted},
            }
        ]
        node["snapshot"]["finalization_status"] = "final"
        node["snapshot"]["authorities"] = ["terminal"]
        (node.get("wait") or {}).update(finalization_status="final")
    rolling = fixture["three_minute_rolling"]
    file_axes = arm_axes(fixture, THREE_MINUTE_CASE, "A", "file")
    rolling["wer"] = file_axes.get("wer")
    rolling["content_recall"] = (file_axes.get("v2") or {}).get("content_recall")
    rolling["matched_word_speaker_accuracy"] = (file_axes.get("v2") or {}).get(
        "matched_word_speaker_accuracy"
    )
    return fixture


def selftest(scored: dict) -> int:
    """Every gate must react to a value pushed past its own bound."""

    failures: list[str] = []
    scored_gates = evaluate(scored)
    already_failing = sorted(gate_id for gate_id, gate in scored_gates.items() if not gate["pass"])
    evidence = selftest_fixture(scored)
    baseline_gates = evaluate(evidence)
    for gate_id, gate in baseline_gates.items():
        if not gate["pass"]:
            failures.append(f"{gate_id} does not pass on the reaction fixture; its reaction is untested")
    print(f"gates failing on the scored batch: {already_failing or 'none'}")
    print("reactions are measured from the converged fixture, not from the scored batch")

    def expect_fail(gate_id: str, mutate) -> None:
        mutated = copy.deepcopy(evidence)
        mutate(mutated)
        if evaluate(mutated)[gate_id]["pass"]:
            failures.append(f"{gate_id} did not react")

    first = evidence["order"][0]["session"]
    last = evidence["order"][-1]["session"]

    def set_axis(node, case, run, arm, axis, value):
        node["quality"]["cases"][case]["runs"][run][arm][axis] = value

    expect_fail("G-M4-0", lambda e: e["sessions"][first]["tape"].update(pcm_sha256="0" * 64))
    expect_fail(
        "G-M4-1",
        lambda e: set_axis(e, THREE_MINUTE_CASE, "A", "live", "wer",
                           (arm_axes(e, THREE_MINUTE_CASE, "A", "file").get("wer") or 0) + G8_WER_TOLERANCE + 1e-6),
    )
    expect_fail(
        "G-M4-2",
        lambda e: set_axis(e, FIVE_MINUTE_CASE, "B", "live", "der",
                           (arm_axes(e, FIVE_MINUTE_CASE, "B", "file").get("der") or 0) + TERMINAL_DER_TOLERANCE + 1e-6),
    )
    expect_fail(
        "G-M4-3",
        lambda e: set_axis(e, "lex_bill_ackman", "A", "live", "wer", ROLLING_WER["lex_bill_ackman"] + 1e-6),
    )
    expect_fail(
        "G-M4-4",
        lambda e: e["quality"]["cases"]["lex_keyu_jin"]["runs"]["A"]["live"]["v2"].update(
            content_recall=ROLLING_V2["lex_keyu_jin"][0] - 1e-6
        ),
    )
    expect_fail("G-M4-5", lambda e: e["sessions"][first]["summary"].update(accounted_samples=1))
    expect_fail(
        "G-M4-6",
        lambda e: e["sessions"][first]["wait"].update(stop_finalization_status="final"),
    )
    expect_fail(
        "G-M4-7",
        lambda e: [
            row.update(surface_preserved=False)
            for row in e["lifecycle"]["decode_failure"].values()
        ],
    )
    expect_fail("G-M4-8", lambda e: e["service_restart"].update(present=False))
    expect_fail(
        "G-M4-9",
        lambda e: e["sessions"][last]["events"]["terminal_revisions"].append(
            {"seq": 999, "kind": "text_revision_applied", "payload": {"source": "terminal"}}
        ),
    )
    expect_fail(
        "G-M4-10",
        lambda e: e["sessions"][first]["tape"].update(peak_retained_bytes=TAPE_CAPACITY_BYTES + 1),
    )
    expect_fail(
        "G-M4-11",
        lambda e: e["sessions"][first]["m2_session"].update(combined_rtf=COMBINED_RTF_BOUND),
    )
    expect_fail("G-M4-12", lambda e: e["file_mode_probe"].update(digest="0" * 64))
    expect_fail(
        "G-M4-12",
        lambda e: e["file_mode_hypotheses"]["lex_keyu_jin"].update(identical=False),
    )
    expect_fail(
        "G-M4-13",
        lambda e: e["sessions"][first]["terminal_payload_strings"].append(
            {"kind": "terminal_finalization_completed", "field": "reason",
             "value": " ".join(str(e["sessions"][first]["published_text"]).split()[:5])}
        ),
    )

    # a second terminal proposal that is not refused must fail G-M4-9 too
    expect_fail("G-M4-9", lambda e: e["already_finalized"].update(exit_code=1))

    # the gate-set contract itself must react
    tampered = dict(baseline_gates)
    tampered["G-M4-1"] = dict(baseline_gates["G-M4-1"], bounds={"tolerance": 0.99})
    if check_gate_set(tampered)["pass"]:
        failures.append("gate-set contract accepted a bound the preregistration never states")
    if check_gate_set({k: v for k, v in baseline_gates.items() if k != "G-M4-0"})["pass"]:
        failures.append("gate-set contract accepted a missing gate")

    for line in failures:
        print("FAIL " + line)
    print(f"selftest: {len(failures)} failures over {len(baseline_gates)} gates")
    return 1 if failures else 0


# ------------------------------------------------------------------ rendering


def render(report: dict) -> str:
    gates = report["gates"]
    lines = ["", "M4 gate table (plan E4 rescoped) - PREREGISTRATION-M4.md §5", ""]
    lines.append(f"{'gate':<9} {'verdict':<7} {'arm':<22} {'instrument':<52} value")
    for gate_id in sorted(gates, key=lambda name: int(name.rsplit("-", 1)[1])):
        gate = gates[gate_id]
        value = gate["value"]
        shown = next(
            (f"{key}={value[key]}" for key in value if isinstance(value[key], (int, float, bool, str))),
            "see json",
        )
        lines.append(
            f"{gate_id:<9} {'PASS' if gate['pass'] else 'FAIL':<7} {gate['arm']:<22} "
            f"{gate['instrument']:<52} {shown}"
        )
    lines += ["", "per-case quality, both runs (terminal vs the paired file arm of the same pass)", ""]
    lines.append(f"{'case':<18} {'run':<4} {'terminal WER':>13} {'file WER':>10} {'terminal DER':>13} {'file DER':>10}")
    for case in CASES:
        for run in RUNS:
            live = (((report["quality"]["cases"].get(case) or {}).get("runs") or {}).get(run) or {}).get("live") or {}
            file_arm = (((report["quality"]["cases"].get(case) or {}).get("runs") or {}).get(run) or {}).get("file") or {}
            def fmt(value):
                return "-" if value is None else f"{value:.6f}"
            lines.append(
                f"{case:<18} {run:<4} {fmt(live.get('wer')):>13} {fmt(file_arm.get('wer')):>10} "
                f"{fmt(live.get('der')):>13} {fmt(file_arm.get('der')):>10}"
            )
    lines += ["", "gate-set contract", ""]
    for key, value in report["gate_set"].items():
        lines.append(f"  {key}: {value}")
    failing = [gate_id for gate_id, gate in gates.items() if not gate["pass"]]
    if failing:
        lines += ["", "failing gates, in full", ""]
        for gate_id in failing:
            lines.append(f"  {gate_id}: {json.dumps(gates[gate_id]['value'].get('failing') or gates[gate_id]['value'])[:400]}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fresh-root", required=True, type=Path)
    parser.add_argument("--three-minute-root", type=Path, default=None)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    fresh_root = args.fresh_root.resolve()
    three_minute_root = (args.three_minute_root or (fresh_root / "three-minute")).resolve()
    evidence = collect(fresh_root, three_minute_root)
    if args.selftest:
        return selftest(evidence)

    gates = evaluate(evidence)
    report = {
        "fresh_root": str(fresh_root),
        "three_minute_root": str(three_minute_root),
        "gates": gates,
        "gate_set": check_gate_set(gates),
        "quality": evidence["quality"],
        "order": evidence["order"],
        "service_restart": evidence["service_restart"],
        "three_minute_rolling": evidence["three_minute_rolling"],
    }
    if args.output:
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(render(report))
    ok = all(gate["pass"] for gate in gates.values()) and report["gate_set"]["pass"]
    print("\nM4 GATES PASS" if ok else "\nM4 GATE FAILURE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
