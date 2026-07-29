#!/usr/bin/env python3
"""Exercise live-soak.sh's abort decision against REAL recorded snapshot bodies.

WHY THIS EXISTS. `scripts/ralph-afk/live-soak.sh` is the F3 driver (gate step (d) of the fifth
amendment).  It was written in run 20260728-181020 iteration 22 and has NEVER BEEN EXECUTED -
m4mbp has been off the tailnet ever since.  Its per-minute loop carries an early-abort check whose
whole job is "stop a 17-minute soak the moment the meeting is dead".  A defect there is not a
cosmetic one: it either burns the run's seventeen minutes or, worse, ends the run at minute 1 and
reports a red soak that never happened.  `bash -n` cannot see any of that.

WHAT IT MEASURES, AND ON WHAT.  The probe does not restate the driver's logic - it EXTRACTS the
shipped bytes between the `# >>> soak-abort-decision` / `# <<< soak-abort-decision` markers, and
the shipped `SNAP_PRUNE` jq filter, and runs them under bash against every snapshot body a real
run recorded.  The default corpus is F1's own evidence directory, which is the ideal input because
it contains BOTH controls already:

  * 54 polls of a completely healthy meeting  (terminal_failure null, v2 status active, both lanes
    active)                                                  -> the decision MUST NOT abort
  *  2 polls taken across F1's real system-lane fault         (lanes failed,active; session still
    active, terminal_failure still null)                     -> the decision MUST NOT abort either,
    because Phase M's governing rule is that a fault on ONE LANE MUST NOT END THE MEETING.  A soak
    that aborts there destroys the very evidence that 53/48/49/D-a keep a meeting alive.

Genuinely-dead states never occurred inside F1's polling window (its canary stopped before the
lease expired), so those are supplied as controls SYNTHESISED BY MUTATING A REAL BODY - the
mutation is named in the report and the unmutated original is one of the healthy rows above.

EXIT CODE.  0 only if every expectation holds.  2 if the markers or the filter cannot be found,
so a refactor that moves them can never make this probe vacuously green (iteration 23's lesson:
an instrument that stops collecting the field cannot measure it).

Usage:
  python3 scripts/ralph-afk/soak-abort-probe.py                       # F1's directory
  python3 scripts/ralph-afk/soak-abort-probe.py --evidence-dir DIR --script PATH --json OUT
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

BEGIN = "# >>> soak-abort-decision"
END = "# <<< soak-abort-decision"


# --------------------------------------------------------------------------- extraction


def extract_region(script_text: str) -> str:
    lines = script_text.splitlines()
    starts = [i for i, ln in enumerate(lines) if BEGIN in ln]
    ends = [i for i, ln in enumerate(lines) if END in ln]
    if len(starts) != 1 or len(ends) != 1 or ends[0] <= starts[0]:
        raise SystemExit(
            f"FATAL: expected exactly one {BEGIN!r} ... {END!r} region in the script; "
            f"found {len(starts)} begin / {len(ends)} end markers. The probe refuses to run "
            "rather than measure nothing."
        )
    return "\n".join(lines[starts[0] + 1 : ends[0]])


def extract_snap_prune(script_text: str) -> str:
    marker = "SNAP_PRUNE='"
    idx = script_text.find(marker)
    if idx < 0:
        raise SystemExit("FATAL: SNAP_PRUNE assignment not found in the script.")
    rest = script_text[idx + len(marker) :]
    end = rest.find("'")
    if end < 0:
        raise SystemExit("FATAL: SNAP_PRUNE assignment is not closed.")
    return rest[:end]


def region_mode(region: str) -> str:
    """`function` when the region defines abort_reason(), else `legacy` (sets $ABORT)."""
    return "function" if "abort_reason()" in region else "legacy"


# --------------------------------------------------------------------------- the harness


HARNESS_FUNCTION = """set -uo pipefail
SNAPSHOT_TSV="$1"
last=$(cat "$2")
snaplast=$(cat "$3")
__REGION__
abort_reason "$last" "$snaplast"
"""

HARNESS_LEGACY = """set -uo pipefail
SNAPSHOT_TSV="$1"
last=$(cat "$2")
snaplast=$(cat "$3")
ABORT=
__REGION__
printf '%s\\n' "${ABORT:-}"
"""


def run_decision(harness: str, tsv: str, last: str, snaplast: str, tmp: str) -> str:
    last_p = os.path.join(tmp, "last.txt")
    snap_p = os.path.join(tmp, "snap.txt")
    with open(last_p, "w") as fh:
        fh.write(last)
    with open(snap_p, "w") as fh:
        fh.write(snaplast)
    proc = subprocess.run(
        ["bash", os.path.join(tmp, "harness.sh"), tsv, last_p, snap_p],
        capture_output=True,
        text=True,
    )
    out = proc.stdout.strip()
    if proc.returncode != 0 and not out:
        out = f"<harness rc={proc.returncode}: {proc.stderr.strip()[:160]}>"
    return out


# --------------------------------------------------------------------------- corpus


def prune(body: str, filt: str) -> str:
    """Apply the driver's own SNAP_PRUNE, with the driver's own fallback to the raw body."""
    proc = subprocess.run(
        ["jq", "-c", filt], input=body, capture_output=True, text=True
    )
    pruned = proc.stdout.replace("\n", "")
    return pruned if pruned else body.replace("\n", "")


def classify(body: str) -> str:
    """Classify a RAW recorded body independently of the decision under test."""
    try:
        doc = json.loads(body)
    except Exception:
        return "unparseable"
    if doc.get("snapshot", {}).get("terminal_failure") is not None:
        return "dead"
    v2 = doc.get("v2_session") or {}
    if v2.get("status") not in (None, "active"):
        return "dead"
    lanes = v2.get("lanes") or {}
    healths = [
        (lane.get("health") if isinstance(lane, dict) else None) for lane in lanes.values()
    ]
    if any(h not in (None, "active") for h in healths):
        return "lane-fault"
    return "healthy"


def load_polls(evidence_dir: str):
    path = os.path.join(evidence_dir, "snapshot.tsv")
    if not os.path.exists(path):
        raise SystemExit(f"FATAL: no snapshot.tsv in {evidence_dir}")
    rows = []
    with open(path) as fh:
        for n, line in enumerate(fh, 1):
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            rows.append({"n": n, "t": parts[0], "code": parts[1], "body": "\t".join(parts[2:])})
    return rows


def classify_status(status: str) -> str:
    """Classify a RAW recorded client status line independently of the decision under test.

    A real canary directory supplies both controls for free: the LAST line of a stopped run says
    `running:false` (the capture is genuinely gone -> must abort), and the lines taken across a
    lane fault say `running:true` with a lane `failed` (the meeting continues -> must not).
    """
    try:
        doc = json.loads(status)
    except Exception:
        return "status-unparseable"
    if doc.get("running") is False:
        return "status-stopped"
    lanes = doc.get("lanes") or []
    states = [ln.get("state") for ln in lanes if isinstance(ln, dict)]
    if any(s not in (None, "capturing", "starting") for s in states):
        return "status-lane-fault"
    return "status-running"


def load_status(evidence_dir: str):
    path = os.path.join(evidence_dir, "status.tsv")
    if not os.path.exists(path):
        return []
    out = []
    with open(path) as fh:
        for n, line in enumerate(fh, 1):
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2 and parts[1].strip():
                text = "\t".join(parts[1:])
                out.append({"n": n, "status": text, "class": classify_status(text)})
    return out


def mutate(body: str, fn) -> str:
    doc = json.loads(body)
    fn(doc)
    return json.dumps(doc, separators=(",", ":"))


# --------------------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--script", default=os.path.join(here, "live-soak.sh"))
    ap.add_argument("--evidence-dir", default="/tmp/ralph-f1-evidence")
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    if not shutil.which("jq"):
        raise SystemExit("FATAL: jq is required (the driver's prune and decision both use it).")

    with open(args.script) as fh:
        script_text = fh.read()
    region = extract_region(script_text)
    filt = extract_snap_prune(script_text)
    mode = region_mode(region)

    polls = load_polls(args.evidence_dir)
    statuses = load_status(args.evidence_dir)
    if not polls:
        raise SystemExit(f"FATAL: no usable polls in {args.evidence_dir}/snapshot.tsv")

    healthy_body = next((p["body"] for p in polls if classify(p["body"]) == "healthy"), None)
    if healthy_body is None:
        raise SystemExit("FATAL: the corpus has no healthy poll to build controls from.")
    healthy_status = next(
        (s["status"] for s in statuses if s["class"] == "status-running"),
        '{"ok":true,"running":true}',
    )

    tmp = tempfile.mkdtemp(prefix="soak-abort-probe-")
    try:
        harness = (HARNESS_FUNCTION if mode == "function" else HARNESS_LEGACY).replace(
            "__REGION__", region
        )
        with open(os.path.join(tmp, "harness.sh"), "w") as fh:
            fh.write(harness)

        # A snapshot.tsv whose tail is three healthy 200 rows: the shape a live soak has.
        good_tsv = os.path.join(tmp, "snapshot-good.tsv")
        with open(good_tsv, "w") as fh:
            for p in polls[-3:]:
                fh.write(f"{p['t']}\t{p['code']}\t{p['body']}\n")
        # ...and one whose tail is three refusals, which is how F3's death looked on the wire.
        dead_tsv = os.path.join(tmp, "snapshot-401.tsv")
        with open(dead_tsv, "w") as fh:
            for p in polls[-3:]:
                fh.write(f"{p['t']}\t401\t{{\"detail\":\"view authority is not valid\"}}\n")

        cases = []

        # ---- 1. every real recorded poll, with the run's own healthy status line
        for p in polls:
            kind = classify(p["body"])
            expect_abort = kind == "dead"
            cases.append(
                {
                    "case": f"recorded-poll-{p['n']}",
                    "class": kind,
                    "source": "real",
                    "tsv": good_tsv,
                    "status": healthy_status,
                    "body": p["body"],
                    "expect_abort": expect_abort,
                }
            )

        # ---- 2. every real recorded client status line, against a healthy snapshot
        for s in statuses:
            cases.append(
                {
                    "case": f"recorded-status-{s['n']}",
                    "class": s["class"],
                    "source": "real",
                    "tsv": good_tsv,
                    "status": s["status"],
                    "body": healthy_body,
                    "expect_abort": s["class"] == "status-stopped",
                }
            )

        # ---- 3. controls: states that MUST abort, synthesised by mutating a real body
        def set_terminal_failure(doc):
            doc["snapshot"]["terminal_failure"] = {
                "code": "helper_lease_expired",
                "detail": "helper lease expired",
            }

        def set_v2_terminal(doc):
            doc["v2_session"]["status"] = "terminal"
            doc["v2_session"]["terminal_reason"] = "helper_lease_expired"

        cases.append(
            {
                "case": "ctl-session-terminal-failure",
                "class": "control-dead",
                "source": "synthetic (real body + snapshot.terminal_failure set)",
                "tsv": good_tsv,
                "status": healthy_status,
                "body": mutate(healthy_body, set_terminal_failure),
                "expect_abort": True,
            }
        )
        cases.append(
            {
                "case": "ctl-v2-session-terminal",
                "class": "control-dead",
                "source": "synthetic (real body + v2_session.status=terminal)",
                "tsv": good_tsv,
                "status": healthy_status,
                "body": mutate(healthy_body, set_v2_terminal),
                "expect_abort": True,
            }
        )
        cases.append(
            {
                "case": "ctl-client-running-false",
                "class": "control-dead",
                "source": "synthetic (real status line with running flipped to false)",
                "tsv": good_tsv,
                "status": healthy_status.replace('"running":true', '"running":false').replace(
                    '"running" : true', '"running" : false'
                ),
                "body": healthy_body,
                "expect_abort": True,
            }
        )
        cases.append(
            {
                "case": "ctl-snapshot-refused-x3",
                "class": "control-dead",
                "source": "synthetic (three 401 rows in the snapshot.tsv tail, F3's own shape)",
                "tsv": dead_tsv,
                "status": healthy_status,
                "body": '{"detail":"view authority is not valid"}',
                "expect_abort": True,
            }
        )

        # ---- run them
        results = []
        for c in cases:
            pruned = prune(c["body"], filt)
            reason = run_decision(harness, c["tsv"], c["status"], pruned, tmp)
            aborted = bool(reason)
            results.append(
                {
                    "case": c["case"],
                    "class": c["class"],
                    "source": c["source"],
                    "expect_abort": c["expect_abort"],
                    "aborted": aborted,
                    "reason": reason,
                    "ok": aborted == c["expect_abort"],
                }
            )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # ---- report
    by_class = {}
    for r in results:
        b = by_class.setdefault(r["class"], {"n": 0, "aborted": 0, "wrong": 0, "reasons": {}})
        b["n"] += 1
        b["aborted"] += 1 if r["aborted"] else 0
        b["wrong"] += 0 if r["ok"] else 1
        if r["reason"]:
            b["reasons"][r["reason"][:110]] = b["reasons"].get(r["reason"][:110], 0) + 1

    wrong = [r for r in results if not r["ok"]]
    print(f"script          : {args.script}")
    print(f"region mode     : {mode}  ({len(region.splitlines())} lines between the markers)")
    print(f"evidence dir    : {args.evidence_dir}")
    print(f"cases           : {len(results)}")
    print("")
    print(f"{'class':<18} {'n':>5} {'aborted':>8} {'wrong':>6}   representative reason")
    for name in sorted(by_class):
        b = by_class[name]
        rep = max(b["reasons"].items(), key=lambda kv: kv[1])[0] if b["reasons"] else "-"
        print(f"{name:<18} {b['n']:>5} {b['aborted']:>8} {b['wrong']:>6}   {rep}")
    print("")
    for r in wrong[:12]:
        want = "abort" if r["expect_abort"] else "continue"
        got = "abort" if r["aborted"] else "continue"
        print(f"  WRONG {r['case']:<28} class={r['class']:<14} want={want:<8} got={got:<8} {r['reason'][:90]}")
    if len(wrong) > 12:
        print(f"  ... and {len(wrong) - 12} more")

    verdict = "PASS" if not wrong else "FAIL"
    print("")
    print(f"VERDICT: {verdict}  ({len(results) - len(wrong)}/{len(results)} cases behave as the ruling requires)")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(
                {
                    "script": args.script,
                    "evidence_dir": args.evidence_dir,
                    "region_mode": mode,
                    "verdict": verdict,
                    "by_class": by_class,
                    "results": results,
                },
                fh,
                indent=2,
            )
        print(f"json: {args.json}")
    return 0 if not wrong else 1


if __name__ == "__main__":
    sys.exit(main())
