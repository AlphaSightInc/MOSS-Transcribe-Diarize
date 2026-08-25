"""Score the 14 preregistered M3 gates and check the D-M3-2 disposition against the tree.

`PREREGISTRATION-M3.md` fixed 14 gates before any S1 arm existed. Iteration 20 built the arm
and measured it: **every gated quality axis ties S0 to six decimal places**. This driver is the
scoring half - it reads the checked-in evidence, scores each gate, and states which arm and
which instrument produced each number, so that "M3's gates pass" can never be read as "E3
delivered something".

The disposition it records is D-M3-2 = **O3, ship nothing**, and it checks that claim against
the working tree rather than asserting it: no production module may import a speaker encoder
into the rolling converger, and `moss_transcribe_diarize/` must be unchanged since the M2 exit
passes were taken (otherwise those passes are not a fresh run of the served surface).

Three properties keep the scoring honest:

  * the gate id set is **parsed out of the preregistration**, both directions, so editing the
    table without editing this driver fails the command;
  * every numeric bound this driver applies must appear **verbatim in that gate's own row**, so
    a threshold cannot be tuned here to make a gate pass;
  * `--selftest` pushes each gate's input past its bound and requires the gate to flip.

Instruments, named per gate and never blended:

  deployed(M2-e2-exit)     the four warm-decoder passes of iteration 18, served surface (= S0)
  offline-replay(M3-s1)    iteration 20's arm, replayed over those same passes, bench-controlled
  fresh-run                run by this command now (pytest floor, file-mode decoder probe)
  projected                deployed measurement + the arm's separately measured marginal cost

Usage:
  python verify_m3_disposition.py [--output out.json]
  python verify_m3_disposition.py --selftest

No GPU, no service, no MOSS request.  Exit 0 iff every gate passes and every disposition check
holds.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

PREREGISTRATION = HERE / "PREREGISTRATION-M3.md"
S1_BUNDLE = REPO / "evidence/live-convergence-0824/M3-s1-prototype"
M2_EXIT = REPO / "evidence/live-convergence-0824/M2-e2-exit"
IDENTITY_FLOOR_TEST = REPO / "tests/test_live_identity_real_corpus.py"
FILE_MODE_PROBE = HERE / "probe_file_mode_decode_identity.py"
CONVERGER = REPO / "moss_transcribe_diarize/app/live_transcript_convergence.py"

TRIO = ("lex_bill_ackman", "lex_javier_milei", "lex_keyu_jin")
FIVE_MINUTE = "keyu-5m"
RUNS = ("A", "B")

# The commit whose tree the M2 exit passes were taken from (iteration 18). The served surface
# is a fresh measurement only while `moss_transcribe_diarize/` has not moved since.
M2_EXIT_COMMIT = "0a40ac3"

# Every bound below is checked against the preregistration row it claims to come from; see
# `bound_stated_in_row`. Nothing here is tunable without failing the command.
PRD_TRIO_DER = 0.1393
M2_TRIO_DER = 0.111278
PRD_TRIO_SPK_ACC = 0.8437
M2_TRIO_SPK_ACC = 0.888722
PRD_FIVE_MINUTE_DER = 0.0947
M2_FIVE_MINUTE_DER = 0.088600
PER_CASE_DER = {"lex_bill_ackman": 0.127333, "lex_javier_milei": 0.117333, "lex_keyu_jin": 0.089167}
PER_CASE_MATCHED_WORD = {
    "lex_bill_ackman": 0.920455,
    "lex_javier_milei": 0.920000,
    "lex_keyu_jin": 0.985612,
    FIVE_MINUTE: 0.954856,
}
PER_CASE_COLLAPSE = {"lex_bill_ackman": 1, "lex_javier_milei": 0, "lex_keyu_jin": 0, FIVE_MINUTE: 0}
PER_CASE_S00_SECONDS = {"lex_bill_ackman": 0.73, "lex_javier_milei": 0.00, "lex_keyu_jin": 0.00, FIVE_MINUTE: 0.56}
COMBINED_RTF_BOUND = 1.0
ROLLING_DEPTH_BOUND = 1
CORRECTION_P95_BOUND_SEC = 8.756675
FILE_MODE_DECODER_DIGEST = "ad381d8bd247e4a8ebe56240dfbc29c0b5a86ffb35a2fcb411c07bbd5b7707f2"


# ------------------------------------------------------------------ the preregistered table


def parse_gate_rows(preregistration: Path) -> dict[str, str]:
    """`{gate id: the whole row text}` for every row of the preregistration's §4 table."""

    rows: dict[str, str] = {}
    for line in preregistration.read_text().splitlines():
        match = re.match(r"^\|\s*(G-M3-\d+)\b", line)
        if match:
            rows[match.group(1)] = line
    return rows


def _renderings(value: float | int | str) -> list[str]:
    """Every way the preregistration might legitimately have written this bound."""

    if isinstance(value, str):
        return [value]
    if isinstance(value, int) or float(value).is_integer():
        return [str(int(value)), f"{float(value):.2f}", f"{float(value):.2f}".lstrip("0")]
    out: set[str] = set()
    for places in (2, 4, 6):
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


# ------------------------------------------------------------------ evidence readers


def load_s1_bundle() -> dict:
    return json.loads((S1_BUNDLE / "s1-all.json").read_text())


def load_timed_bundles() -> dict[str, dict]:
    return {
        "trio": json.loads((S1_BUNDLE / "s1-trio-timed.json").read_text()),
        FIVE_MINUTE: json.loads((S1_BUNDLE / "s1-5m-timed.json").read_text()),
    }


def load_m2_gates() -> dict:
    return json.loads((M2_EXIT / "gates.json").read_text())["gates"]


def bundle_integrity() -> dict:
    """Every file the disposition reads, hashed against the bundle's own manifest."""

    checked: dict[str, bool] = {}
    for line in (S1_BUNDLE / "sha256.txt").read_text().splitlines():
        if not line.strip():
            continue
        digest, name = line.split()
        path = S1_BUNDLE / name
        checked[name] = path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == digest
    return checked


def s1_axis(bundle: dict, case: str, axis: str, arm: str = "s1") -> float:
    return bundle["summary"]["per_case"][case][arm][axis]


def s1_trio_mean(bundle: dict, axis: str, arm: str = "s1") -> float:
    return bundle["summary"]["trio_mean"][arm][axis]


def witness_rtf(timed: dict[str, dict]) -> dict[str, float]:
    """WeSpeaker seconds spent on witness-owned intervals, per audio-second. Album embeddings
    are excluded on purpose: those are the base path's existing work, already inside the M2
    exit's measured combined RTF."""

    out = {}
    for key, report in timed.items():
        witness = report["embedding_accounting"]["by_tag"]["witness"]
        audio_seconds = sum(
            run["duration_sec"]
            for node in report["cases"].values()
            for run in node["runs"].values()
            if run["encoder_seconds"] > 0
        )
        out[key] = round(witness["encoder_seconds"] / audio_seconds, 6) if audio_seconds else None
    return out


def run_identity_floor() -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(IDENTITY_FLOOR_TEST), "-q"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    return {"exit_code": proc.returncode, "tail": proc.stdout.strip().splitlines()[-1:] or [proc.stderr[-200:]]}


def run_file_mode_probe() -> dict:
    proc = subprocess.run(
        [sys.executable, str(FILE_MODE_PROBE), str(REPO)], cwd=REPO, capture_output=True, text=True
    )
    if proc.returncode != 0:
        return {"exit_code": proc.returncode, "digest": None, "stderr": proc.stderr[-400:]}
    digest = hashlib.sha256(proc.stdout.encode()).hexdigest()
    return {"exit_code": 0, "digest": digest}


def production_untouched_since_m2_exit() -> dict:
    proc = subprocess.run(
        ["git", "diff", "--stat", f"{M2_EXIT_COMMIT}..HEAD", "--", "moss_transcribe_diarize/"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    return {"exit_code": proc.returncode, "diff": proc.stdout.strip()}


def converger_has_no_speaker_encoder() -> dict:
    """`ship nothing` read off the tree: the rolling converger must still be text-only."""

    source = CONVERGER.read_text()
    hits = sorted(
        {
            token
            for token in ("wespeaker", "WeSpeaker", "embedder", "Embedder", "embedding", "live_identity_album")
            if token in source
        }
    )
    return {"matches": hits, "module": str(CONVERGER.relative_to(REPO))}


# ------------------------------------------------------------------ gates


def evaluate(evidence: dict) -> dict:
    s1 = evidence["s1"]
    m2 = evidence["m2_gates"]
    gates: dict[str, dict] = {}

    # ---- G-M3-0  D5 structural
    violations = {
        f"{case}/{run}": len(node["runs"][run]["d5_violations"])
        for case, node in s1["cases"].items()
        for run in node["runs"]
    }
    gates["G-M3-0"] = {
        "pass": sum(violations.values()) == 0,
        "arm": "S1",
        "instrument": "offline-replay(M3-s1)",
        "bounds": {},
        "value": {"total_violations": sum(violations.values()), "per_session": violations},
    }

    # ---- G-M3-1  trio mean DER
    trio_der = s1_trio_mean(s1, "der")
    gates["G-M3-1"] = {
        "pass": trio_der <= min(PRD_TRIO_DER, M2_TRIO_DER),
        "arm": "S1",
        "instrument": "offline-replay(M3-s1)",
        "bounds": {"prd": PRD_TRIO_DER, "m2_exit": M2_TRIO_DER},
        "value": trio_der,
    }

    # ---- G-M3-2  per-case DER, no regression
    per_case_der = {case: s1_axis(s1, case, "der") for case in TRIO}
    gates["G-M3-2"] = {
        "pass": all(per_case_der[case] <= PER_CASE_DER[case] for case in TRIO),
        "arm": "S1",
        "instrument": "offline-replay(M3-s1)",
        "bounds": dict(PER_CASE_DER),
        "value": per_case_der,
    }

    # ---- G-M3-3  trio mean speaker accuracy
    trio_spk = s1_trio_mean(s1, "speaker_accuracy")
    gates["G-M3-3"] = {
        "pass": trio_spk >= max(PRD_TRIO_SPK_ACC, M2_TRIO_SPK_ACC),
        "arm": "S1",
        "instrument": "offline-replay(M3-s1)",
        "bounds": {"prd": PRD_TRIO_SPK_ACC, "m2_exit": M2_TRIO_SPK_ACC},
        "value": trio_spk,
    }

    # ---- G-M3-4  five-minute DER
    five_der = s1_axis(s1, FIVE_MINUTE, "der")
    gates["G-M3-4"] = {
        "pass": five_der <= min(PRD_FIVE_MINUTE_DER, M2_FIVE_MINUTE_DER),
        "arm": "S1",
        "instrument": "offline-replay(M3-s1)",
        "bounds": {"prd": PRD_FIVE_MINUTE_DER, "m2_exit": M2_FIVE_MINUTE_DER},
        "value": five_der,
    }

    # ---- G-M3-5  evaluator-v2 matched-word speaker accuracy, per case
    matched = {case: s1_axis(s1, case, "matched_word_speaker_accuracy") for case in PER_CASE_MATCHED_WORD}
    gates["G-M3-5"] = {
        "pass": all(matched[case] >= bound for case, bound in PER_CASE_MATCHED_WORD.items()),
        "arm": "S1",
        "instrument": "offline-replay(M3-s1)",
        "bounds": dict(PER_CASE_MATCHED_WORD),
        "value": matched,
    }

    # ---- G-M3-6  9-clip identity floor
    floor = evidence["identity_floor"]
    gates["G-M3-6"] = {
        "pass": floor["exit_code"] == 0,
        "arm": "served",
        "instrument": "fresh-run",
        "bounds": {},
        "value": floor,
    }

    # ---- G-M3-7  no speaker collapse, sliding screen
    collapse = {case: s1_axis(s1, case, "collapsed_windows") for case in PER_CASE_COLLAPSE}
    gates["G-M3-7"] = {
        "pass": all(collapse[case] <= bound for case, bound in PER_CASE_COLLAPSE.items()),
        "arm": "S1",
        "instrument": "offline-replay(M3-s1)",
        "bounds": dict(PER_CASE_COLLAPSE),
        "value": collapse,
    }

    # ---- G-M3-8  S00 duration does not increase
    s00 = {case: s1_axis(s1, case, "unattributed_seconds") for case in PER_CASE_S00_SECONDS}
    gates["G-M3-8"] = {
        "pass": all(s00[case] <= bound + 1e-9 for case, bound in PER_CASE_S00_SECONDS.items()),
        "arm": "S1",
        "instrument": "offline-replay(M3-s1)",
        "bounds": dict(PER_CASE_S00_SECONDS),
        "value": s00,
        "note": (
            "passes, and iteration 20 measured WHY it passes on lex_bill_ackman: S1 puts a "
            "confident wrong name on the two sub-quarter-second fragments the projection "
            "honestly abstained on, so S00 falls .73 -> .33 while misattributed seconds rise "
            ".48 -> .88. The gate cannot see that trade; the decomposition can."
        ),
    }

    # ---- G-M3-9  one-to-one mapping or abstain
    many_to_one = []
    for case, node in s1["cases"].items():
        for run, run_node in node["runs"].items():
            for window in run_node["windows"]:
                mapping = window["mapping"]
                identities = [identity for identity in mapping.values() if identity]
                if len(identities) != len(set(identities)):
                    many_to_one.append({"case": case, "run": run, "window": window["window_index"], "mapping": mapping})
    gates["G-M3-9"] = {
        "pass": not many_to_one,
        "arm": "S1",
        "instrument": "offline-replay(M3-s1)",
        "bounds": {},
        "value": {"many_to_one_maps": len(many_to_one), "examples": many_to_one[:3]},
    }

    # ---- G-M3-10  combined RTF < 1 and bounded queues
    deployed_rtf = m2["G_M2_5_combined_rtf_bounded_queues"]
    per_session = {
        key: {
            "deployed_combined_rtf": node["combined_rtf"],
            "witness_wespeaker_rtf": evidence["witness_rtf"]["trio" if not key.startswith(FIVE_MINUTE) else FIVE_MINUTE],
            "rolling_max_depth": node["rolling_max_depth"],
        }
        for key, node in deployed_rtf["per_session"].items()
    }
    for node in per_session.values():
        node["projected_combined_rtf"] = round(node["deployed_combined_rtf"] + node["witness_wespeaker_rtf"], 6)
    queues_bounded = deployed_rtf["pass"] and all(
        node["rolling_max_depth"] <= ROLLING_DEPTH_BOUND for node in per_session.values()
    )
    gates["G-M3-10"] = {
        "pass": queues_bounded and all(node["projected_combined_rtf"] < COMBINED_RTF_BOUND for node in per_session.values()),
        "arm": "served + S1 marginal cost",
        "instrument": "projected(deployed M2-e2-exit + offline-replay cost)",
        "bounds": {"combined_rtf": COMBINED_RTF_BOUND, "rolling_max_depth": ROLLING_DEPTH_BOUND},
        "value": {
            "max_projected_combined_rtf": max(node["projected_combined_rtf"] for node in per_session.values()),
            "per_session": per_session,
        },
    }

    # ---- G-M3-11  correction p95 does not increase
    served_p95 = m2["G_M2_4_correction_p95"]["p95_sec"]
    gates["G-M3-11"] = {
        "pass": served_p95 <= CORRECTION_P95_BOUND_SEC,
        "arm": "served",
        "instrument": "deployed(M2-e2-exit)",
        "bounds": {"p95_sec": CORRECTION_P95_BOUND_SEC},
        "value": served_p95,
        "note": (
            "passes only because nothing shipped: this IS the M2 exit's own already-unsigned "
            "number. Iteration 20 priced the arm at 1.02-1.14 s per witness embed; run serially "
            "inside the witness path (O1) that lands on this clock, which is why the fallback "
            "option was always the label seam after the text revision (O2)."
        ),
    }

    # ---- G-M3-12  file mode byte-identical, both readings
    probe = evidence["file_mode_probe"]
    gates["G-M3-12"] = {
        "pass": m2["G_M2_8_file_mode_byte_identical"]["pass"] and probe.get("digest") == FILE_MODE_DECODER_DIGEST,
        "arm": "served",
        "instrument": "deployed(M2-e2-exit) + fresh-run",
        "bounds": {"decoder_digest": FILE_MODE_DECODER_DIGEST},
        "value": {
            "a_hypotheses_byte_identical": m2["G_M2_8_file_mode_byte_identical"]["pass"],
            "b_decoder_digest": probe.get("digest"),
            "probe_exit_code": probe.get("exit_code"),
        },
    }

    # ---- G-M3-13  accepted == accounted
    accounting = m2["G_M2_7_exact_sample_accounting"]
    gates["G-M3-13"] = {
        "pass": accounting["pass"],
        "arm": "served",
        "instrument": "deployed(M2-e2-exit)",
        "bounds": {},
        "value": {"sessions": len(accounting["per_session"]), "all_equal": accounting["pass"]},
    }
    return gates


# ------------------------------------------------------------------ disposition


def disposition_checks(evidence: dict) -> dict:
    s1 = evidence["s1"]
    integrity = evidence["bundle_integrity"]
    controls = {
        f"{case}/{run}": node["runs"][run]["bench_control"]
        for case, node in s1["cases"].items()
        for run in node["runs"]
    }
    axes = ("der", "speaker_accuracy", "matched_word_speaker_accuracy", "wer")
    deltas = {
        case: {axis: round(node["s1"][axis] - node["s0"][axis], 9) for axis in axes}
        for case, node in s1["summary"]["per_case"].items()
    }
    encoder = evidence["converger_encoder"]
    tree = evidence["production_untouched"]
    checks = {
        "s1_bundle_intact": {
            "pass": all(integrity.values()),
            "value": integrity,
        },
        "s1_bench_controls_green": {
            "pass": all(node["s0_reproduces_deployed_scores"] and node["export_reproduces_pass"] for node in controls.values()),
            "value": controls,
        },
        "s1_ties_s0_on_every_gated_axis": {
            "pass": all(value == 0 for case in deltas for value in deltas[case].values()),
            "value": deltas,
        },
        "nothing_shipped": {
            "pass": not encoder["matches"],
            "value": encoder,
        },
        "served_surface_unchanged_since_the_passes": {
            "pass": tree["exit_code"] == 0 and tree["diff"] == "",
            "value": tree,
        },
    }
    return checks


DISPOSITION = {
    "decision": "D-M3-2 = O3: record E3-S1 as measured-neutral, ship nothing, leave the plan §18 E3 row unsigned.",
    "why_not_O1_or_O2": [
        "The preregistration §6.2 says a passing S1 ships even on a tie, and gives one reason: "
        "'D5's ownership is the architecture E4 builds on'. Plan §12.3 steps 4-5 falsify it - the "
        "terminal pass runs the existing 150/120 WindowedRunner over the mixed tape and resolves "
        "terminal identities there, so E4 does not call the rolling resolver. The premise, not the "
        "gate, is what failed.",
        "S1's only two output changes on the whole bench are wrong: lex_bill_ackman 39.84-40.00 "
        "'Right?' and 49.75-49.99 'You know.', both named speaker-0002 where the reference says "
        "Bill. Misattributed seconds .48 -> .88. Shipping it makes the product measurably worse on "
        "the only segments it touches and better on none.",
        "The upside was measured before the arm existed and again after: the label-only ceiling is "
        ".00672 trio mean DER (63 % of remaining confusion is segments straddling a reference turn, "
        "27 % is sub-floor microfragments), and S1 realises 0.000000 of it.",
        "Cost is real: .1306 RTF trio / .1371 five-minute of extra WeSpeaker work, and 1.02-1.14 s "
        "per window against a correction p95 that is already unsigned at 8.756675 s.",
    ],
    "what_the_gates_do_and_do_not_certify": (
        "Every M3 gate is a no-regression gate - by construction, since §1 bound each one to the "
        "stricter of the PRD bound and the M2 exit measurement. So a build that ships nothing passes "
        "all 14. These results certify that the served speaker surface did not regress and that the "
        "S1 arm is structurally correct (D5 clean, one-to-one or abstain, label-invariant). They do "
        "NOT certify that E3 delivered quality, because it did not: the delta is 0.000000 everywhere.",
    ),
    "row": "plan §18 E3 stays UNSIGNED, with this bundle and M3-s1-prototype as its evidence - the "
    "same disposition M0(d) G2, M1 G-M1-1 and M2 G-M2-4 received.",
    "not_a_stop": "No plan §15 global stop condition fired: no case-level WER regression, file mode "
    "unchanged, accounting exact, scorer self-tests green, no truth read during reconciliation.",
    "handoff": "The speaker seconds that remain are owned by segment EXTENTS (E2's frozen text "
    "geometry) and by plan §11.4 microfragments. Both belong in the §18 record so the next campaign "
    "starts from the decomposition rather than from the confusion total.",
}


# ------------------------------------------------------------------ driver


def collect() -> dict:
    return {
        "s1": load_s1_bundle(),
        "m2_gates": load_m2_gates(),
        "witness_rtf": witness_rtf(load_timed_bundles()),
        "bundle_integrity": bundle_integrity(),
        "identity_floor": run_identity_floor(),
        "file_mode_probe": run_file_mode_probe(),
        "production_untouched": production_untouched_since_m2_exit(),
        "converger_encoder": converger_has_no_speaker_encoder(),
    }


def check_gate_set(gates: dict) -> dict:
    """The preregistration decides which gates exist, and the bounds must be quoted from it."""

    rows = parse_gate_rows(PREREGISTRATION)
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


def selftest() -> int:
    """Every gate must react to a value pushed past its own bound."""

    failures: list[str] = []
    base = collect()
    baseline = evaluate(base)
    if not all(gate["pass"] for gate in baseline.values()):
        failures.append("baseline is not all-pass; selftest cannot measure reaction")

    def perturbed(mutate) -> dict:
        evidence = json.loads(json.dumps(base))
        mutate(evidence)
        return evaluate(evidence)

    def expect_fail(gate_id: str, mutate) -> None:
        gates = perturbed(mutate)
        if gates[gate_id]["pass"]:
            failures.append(f"{gate_id} did not react")

    def set_case(evidence, case, axis, value, arm="s1"):
        evidence["s1"]["summary"]["per_case"][case][arm][axis] = value

    expect_fail("G-M3-0", lambda e: e["s1"]["cases"]["lex_bill_ackman"]["runs"]["A"]["d5_violations"].append({"why": "x"}))
    expect_fail("G-M3-1", lambda e: e["s1"]["summary"]["trio_mean"]["s1"].update(der=M2_TRIO_DER + 1e-6))
    expect_fail("G-M3-2", lambda e: set_case(e, "lex_javier_milei", "der", PER_CASE_DER["lex_javier_milei"] + 1e-6))
    expect_fail("G-M3-3", lambda e: e["s1"]["summary"]["trio_mean"]["s1"].update(speaker_accuracy=M2_TRIO_SPK_ACC - 1e-6))
    expect_fail("G-M3-4", lambda e: set_case(e, FIVE_MINUTE, "der", M2_FIVE_MINUTE_DER + 1e-6))
    expect_fail("G-M3-5", lambda e: set_case(e, "lex_keyu_jin", "matched_word_speaker_accuracy", 0.5))
    expect_fail("G-M3-6", lambda e: e["identity_floor"].update(exit_code=1))
    expect_fail("G-M3-7", lambda e: set_case(e, "lex_javier_milei", "collapsed_windows", 1.0))
    expect_fail("G-M3-8", lambda e: set_case(e, "lex_bill_ackman", "unattributed_seconds", 0.74))
    expect_fail(
        "G-M3-9",
        lambda e: e["s1"]["cases"]["lex_bill_ackman"]["runs"]["A"]["windows"][0]["mapping"].update(
            S01="speaker-0001", S02="speaker-0001"
        ),
    )
    expect_fail("G-M3-10", lambda e: e["witness_rtf"].update(trio=0.95))
    expect_fail("G-M3-11", lambda e: e["m2_gates"]["G_M2_4_correction_p95"].update(p95_sec=CORRECTION_P95_BOUND_SEC + 1e-6))
    expect_fail("G-M3-12", lambda e: e["file_mode_probe"].update(digest="0" * 64))
    expect_fail("G-M3-13", lambda e: e["m2_gates"]["G_M2_7_exact_sample_accounting"].update({"pass": False}))

    # the gate-set contract itself must react to an unquoted bound
    tampered = dict(baseline)
    tampered["G-M3-1"] = dict(baseline["G-M3-1"], bounds={"prd": 0.99})
    if check_gate_set(tampered)["pass"]:
        failures.append("gate-set contract accepted a bound the preregistration never states")
    if check_gate_set({k: v for k, v in baseline.items() if k != "G-M3-0"})["pass"]:
        failures.append("gate-set contract accepted a missing gate")

    # the disposition checks must react too
    for name, mutate in (
        ("nothing_shipped", lambda e: e["converger_encoder"].update(matches=["WeSpeaker"])),
        ("served_surface_unchanged_since_the_passes", lambda e: e["production_untouched"].update(diff="x | 1 +")),
        (
            "s1_ties_s0_on_every_gated_axis",
            lambda e: e["s1"]["summary"]["per_case"]["lex_keyu_jin"]["s1"].update(der=0.0),
        ),
        ("s1_bundle_intact", lambda e: e["bundle_integrity"].update({"s1-all.json": False})),
        (
            "s1_bench_controls_green",
            lambda e: e["s1"]["cases"]["lex_keyu_jin"]["runs"]["A"]["bench_control"].update(
                s0_reproduces_deployed_scores=False
            ),
        ),
    ):
        evidence = json.loads(json.dumps(base))
        mutate(evidence)
        if disposition_checks(evidence)[name]["pass"]:
            failures.append(f"disposition check {name} did not react")

    for line in failures:
        print("FAIL " + line)
    print(f"selftest: {len(failures)} failures")
    return 1 if failures else 0


def render(report: dict) -> str:
    lines = ["", "M3 gate table (plan E3 rescoped) - PREREGISTRATION-M3.md §4", ""]
    lines.append(f"{'gate':<9} {'verdict':<7} {'arm':<28} {'instrument':<46} value")
    for gate_id, gate in report["gates"].items():
        value = gate["value"]
        if isinstance(value, dict):
            shown = next(
                (f"{k}={v}" for k, v in value.items() if isinstance(v, (int, float, bool, str))),
                "see json",
            )
        else:
            shown = value
        lines.append(
            f"{gate_id:<9} {'PASS' if gate['pass'] else 'FAIL':<7} {gate['arm']:<28} {gate['instrument']:<46} {shown}"
        )
    lines += ["", "disposition checks", ""]
    for name, check in report["disposition_checks"].items():
        lines.append(f"  [{'PASS' if check['pass'] else 'FAIL'}] {name}")
    lines += ["", "gate-set contract", ""]
    for key, value in report["gate_set"].items():
        lines.append(f"  {key}: {value}")
    lines += ["", "D-M3-2", "", "  " + report["disposition"]["decision"], ""]
    for reason in report["disposition"]["why_not_O1_or_O2"]:
        lines.append("  - " + reason)
    lines += ["", "  " + report["disposition"]["what_the_gates_do_and_do_not_certify"][0], ""]
    lines.append("  " + report["disposition"]["row"])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return selftest()

    evidence = collect()
    gates = evaluate(evidence)
    report = {
        "gates": gates,
        "gate_set": check_gate_set(gates),
        "disposition_checks": disposition_checks(evidence),
        "disposition": DISPOSITION,
        "witness_wespeaker_rtf": evidence["witness_rtf"],
    }
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(render(report))

    ok = (
        all(gate["pass"] for gate in gates.values())
        and report["gate_set"]["pass"]
        and all(check["pass"] for check in report["disposition_checks"].values())
    )
    print("\nM3 GATES PASS, DISPOSITION HOLDS" if ok else "\nM3 DISPOSITION FAILURE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
