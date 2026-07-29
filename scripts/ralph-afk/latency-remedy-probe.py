#!/usr/bin/env python3
"""Iteration 15 - price the plan's SECOND ordered latency remedy (0.5 s poll
interval) against the three real certification runs, and prove the two
constants it lives in are not tied to each other by anything.

Iteration 16 adds section 5: WHOSE request rate each of those two constants
actually changes. Iteration 15's honest limit named the wrong request stream,
and the answer sharpens candidate 68 rather than softening it.

ITERATION 23 (Phase Q item Q3) APPLIED THE REMEDY, so section 3's checks are
INVERTED: they used to assert that nothing tied the two constants together,
which was the defect, and a probe that keeps asserting a defect exists is a
probe asserting the fix did not land. They now assert the tie. That inversion
IS the red-before/green-after evidence and needs no other instrument: at
dafcae1 the four checks below read the other way and this file passed 20/20;
`git show dafcae1 -- scripts/ralph-afk/latency-remedy-probe.py` is that reading.
Section 1 still reads `portalCycleMS == 1000` because it reads F3's real
report, which was measured BEFORE the remedy and does not change retroactively.

No product change, no host, no session. Reads one real evidence directory and
three tracked source files."""
import json, re, subprocess, sys, pathlib

REPO = pathlib.Path("/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize")
F3DIR = pathlib.Path("/tmp/i12-f3-evidence/ralph-soak")
F3 = F3DIR / "latency-final.json"
fail = []

for needed in (F3, F3DIR / "times.env", F3DIR / "snapshot.tsv", F3DIR / "events.tsv"):
    if not needed.exists():
        print(f"REFUSED: this probe reads run 20260729-094359 iteration 12's F3 evidence and "
              f"{needed} is absent. That directory is under /tmp and does not survive a reboot; "
              f"re-run F3 or point F3DIR at another soak directory. Not a failure - unmeasured.")
        sys.exit(6)

def check(name, ok, detail=""):
    print(f"  [{'OK ' if ok else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")
    if not ok:
        fail.append(name)

print("1. THE IDENTITY, ON F3's REAL latency-final.json (run 20260729-094359 it. 12)")
d = json.load(F3.open())["latency"]
cycle = d["portalCycleMS"]; snap = d["snapshotFetch"]["p95MS"]; ev = d["eventsFetch"]["p95MS"]
render = d["renderBoundMS"]; committed = d["committedLatency"]["p95MS"]; uv = d["userVisibleMS"]
print(f"     portalCycleMS={cycle}  snapshotP95={snap:.6f}  eventsP95={ev:.6f}")
print(f"     renderBoundMS={render:.6f}  committedP95={committed:.6f}  userVisibleMS={uv:.6f}")
check("renderBound == portalCycle + snapshotP95 + eventsP95",
      abs(render - (cycle + snap + ev)) < 1e-6, f"residual {render-(cycle+snap+ev):.9f} ms")
check("userVisible == committedP95 + renderBound",
      abs(uv - (committed + render)) < 1e-6, f"residual {uv-(committed+render):.9f} ms")
check("the portal-cycle term was a whole 1000.0 ms of the gated number (PRE-remedy)",
      cycle == 1000, f"{100.0*cycle/uv:.1f} % of userVisibleMS")

print("\n2. THE COUNTERFACTUAL - portalCycle 1000 -> 500 subtracts exactly 500.0 ms")
runs = [("F1 on 7a4f59c (it. 30 of 20260729-025318)", 4150.8, 4000.0),
        ("F2 on 7a4f59c (it. 1 of 20260729-094359)",  4078.6, 6000.0),
        ("F3 on 7a4f59c (it. 12 of 20260729-094359)", uv,     6000.0)]
print(f"     {'run':<44} {'measured':>10} {'at 0.5 s':>10} {'gate':>7}  verdict now -> then")
for name, meas, gate in runs:
    then = meas - 500.0
    print(f"     {name:<44} {meas:>10.1f} {then:>10.1f} {gate:>7.0f}  "
          f"{'RED ' if meas>gate else 'GREEN'} -> {'RED' if then>gate else 'GREEN'}"
          f"   (margin {gate-then:+.1f} ms)")
check("F1's RED closes with margin to spare", 4150.8-500.0 < 4000.0,
      f"miss was 150.8 ms; the remedy is worth 500.0 ms = {500.0/150.8:.1f}x the miss")

print("\n3. THE TWO CONSTANTS, AND WHAT NOW TIES THEM (inverted by Q3, iteration 23)")
portal = (REPO/"moss_transcribe_diarize/app/live_portal.py").read_text()
m = re.search(r"const pollDelayMs = (\d+);", portal)
check("server portal schedules its next cycle at pollDelayMs", bool(m),
      f"live_portal.py pollDelayMs = {m.group(1) if m else '?'}")
swift = (REPO/"macos/MOSSCapture/Sources/MOSSCaptureCore/CaptureLatencyProbe.swift").read_text()
m2 = re.search(r"portalCycleSeconds: Double = ([0-9.]+)", swift)
check("app's gate constant asserts the same cadence independently", bool(m2),
      f"CaptureLatencyProbe.swift portalCycleSeconds = {m2.group(1) if m2 else '?'}")
check("the two agree", m and m2 and float(m.group(1))/1000.0 == float(m2.group(1)),
      f"{m.group(1)} ms vs {float(m2.group(1))*1000:.0f} ms")
check("and the remedy is APPLIED - both halves at 0.5 s, neither alone",
      m and m2 and float(m.group(1)) == 500.0 and float(m2.group(1)) == 0.5,
      f"pollDelayMs={m.group(1)} ms, portalCycleSeconds={m2.group(1)} s")

def rg(pattern, *paths):
    """Tracked source only. A plain `grep -rn` here also reads `macos/.build`
    and `__pycache__`, so `portalCycleSeconds` scored 37 sites (34 of them the
    string baked into a test binary) and every 'nothing references this' check
    was one stale build artifact away from a false RED."""
    r = subprocess.run(["git","grep","-n","--",pattern,*paths], cwd=REPO,
                       capture_output=True, text=True)
    return [l for l in r.stdout.splitlines() if l.strip()]

py_refs = rg("pollDelayMs", "tests")
check("a python test asserts the portal's poll cadence", bool(py_refs),
      f"{len(py_refs)} hits in tests/")
# The tie has to hold from BOTH sides: one node alone leaves the other language free to move.
swift_side = rg("pollDelayMs", "macos/MOSSCapture/Tests")
python_side = rg("portalCycleSeconds", "tests")
check("the tie is asserted from BOTH sides of the language boundary",
      bool(swift_side) and bool(python_side),
      f"{len(swift_side)} swift-reads-portal, {len(python_side)} python-reads-swift")
selfref = rg("portalCycleMS, 1_000", "macos/MOSSCapture/Tests")
check("no assertion on the term compares the constant to itself any more", not selfref,
      f"{len(selfref)} self-comparisons left")

print("\n4. IS THE PORTAL POLL A DOMAIN-CONTRACT VALUE? (prd.md Constraints)")
prd = (REPO/"scripts/ralph-afk/prd.md").read_text()
block = prd.split("**Domain-contract values.**")[1].split("\n- **")[0]
block = re.sub(r"\s+", " ", block)   # the bullet is line-wrapped: "pump\n  interval"
for term, expect in [("hard_cap_samples", True), ("pump interval", True),
                     ("poll", False), ("portal", False), ("pollDelayMs", False)]:
    present = term in block
    check(f"contract list {'names' if expect else 'does NOT name'} {term!r}",
          present == expect, f"present={present}")

print("\n5. WHOSE REQUEST RATE DOES EACH CONSTANT CHANGE? (iteration 16)")
main_swift = (REPO/"macos/MOSSCapture/Sources/MOSSCaptureApp/main.swift").read_text()
m3 = re.search(r"pollInterval: TimeInterval = ([0-9.]+)", swift)
probe_hz = float(m3.group(1)) if m3 else None
check("the app probe has its OWN fetch cadence constant", bool(m3),
      f"CaptureLatencyContract.pollInterval = {m3.group(1) if m3 else '?'} s")
check("and THAT is what schedules its fetches",
      "interval: CaptureLatencyContract.pollInterval" in main_swift,
      "main.swift builds RepeatingCaptureSchedulerAdapter(interval: pollInterval)")

# Every site of each constant, and whether any of them is a scheduling site.
SCHEDULING = ("scheduler", "schedule", "sleep", "timer", "interval:")
cycle_sites = rg("portalCycleSeconds", "macos")
cycle_sched = [l for l in cycle_sites if any(k in l.lower() for k in SCHEDULING)]
check("portalCycleSeconds reaches NO scheduling site - it is arithmetic only",
      cycle_sites and not cycle_sched,
      f"{len(cycle_sites)} sites (decl, report default, renderBound sum), {len(cycle_sched)} scheduling")
poll_sites = rg("pollDelayMs", "moss_transcribe_diarize")
check("pollDelayMs schedules the BROWSER's next cycle and nothing else",
      any("schedulePoll(pollDelayMs)" in l for l in poll_sites)
      and all("live_portal.py" in l for l in poll_sites),
      f"{len(poll_sites)} sites, all in live_portal.py's served script")
# Scoped to Sources since Q3, and comments excluded: the enforcing node reads the portal on
# purpose and the constant's doc comment NAMES the server's copy on purpose - what must stay true
# is that no measurement CODE reads it, which is a different claim from "the token is absent".
def code_lines(hits):
    return [h for h in hits
            if not h.split(":", 2)[-1].lstrip().startswith(("//", "#"))]

poll_in_sources = code_lines(rg("pollDelayMs", "macos/MOSSCapture/Sources"))
check("pollDelayMs appears NOWHERE in the measurement path",
      not poll_in_sources,
      f"0 code hits under macos/MOSSCapture/Sources ({len(rg('pollDelayMs', 'macos/MOSSCapture/Sources'))} "
      f"in comments, naming the tie); {len(swift_side)} in Tests (the enforcing node)")

# The real report says which stream the gated p95s come from.
times = dict(l.split("=", 1) for l in (F3DIR/"times.env").read_text().splitlines() if "=" in l)
wall = float(times["T_SOAK_END"]) - float(times["T_SOAK_START"])
n_probe = d["snapshotFetch"]["count"]
driver_polls = len((F3DIR/"snapshot.tsv").read_text().splitlines())
implied = wall / n_probe
print(f"     F3 soak wall {wall:.3f} s; probe fetches {n_probe}; driver polls {driver_polls}")
print(f"     implied probe interval {implied:.4f} s   driver interval {wall/driver_polls:.4f} s")
check("the gated p95s are measured at the PROBE's cadence, not the portal's",
      probe_hz and abs(implied - probe_hz) / probe_hz < 0.05,
      f"{implied:.4f} s vs pollInterval {probe_hz} s ({100*(implied-probe_hz)/probe_hz:+.1f} %)")
check("snapshot and events are fetched serially in the same cycle",
      d["snapshotFetch"]["count"] == d["eventsFetch"]["count"], f"{n_probe} == {n_probe}")
check("the driver's poll stream is a DIFFERENT stream from the gated one",
      driver_polls != n_probe and abs(wall/driver_polls - 1.0) > 0.5,
      f"{driver_polls} driver polls at {wall/driver_polls:.2f} s is neither the probe's "
      f"{n_probe} nor a 1.0 s portal cadence")

print("     => moving pollDelayMs alone: gated number moves 0.0 ms, a browser waits 500 ms less")
print("     => moving portalCycleSeconds alone: gated number moves -500.0 ms, nobody waits less")
print("     => SINCE Q3 neither is possible alone: two nodes, one per language, fail on either")

print(f"\n{'FAILED: ' + ', '.join(fail) if fail else 'ALL CHECKS PASSED'}")
sys.exit(1 if fail else 0)
