#!/usr/bin/env python3
"""Iteration 15 - price the plan's SECOND ordered latency remedy (0.5 s poll
interval) against the three real certification runs, and prove the two
constants it lives in are not tied to each other by anything.

No product change, no host, no session. Reads one real evidence directory and
two tracked source files."""
import json, re, subprocess, sys, pathlib

REPO = pathlib.Path("/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize")
F3 = pathlib.Path("/tmp/i12-f3-evidence/ralph-soak/latency-final.json")
fail = []

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
check("the portal-cycle term is a whole 1000.0 ms of the gated number",
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

print("\n3. THE TWO CONSTANTS, AND NOTHING TIES THEM")
portal = (REPO/"moss_transcribe_diarize/app/live_portal.py").read_text()
m = re.search(r"const pollDelayMs = (\d+);", portal)
check("server portal schedules its next cycle at pollDelayMs", bool(m),
      f"live_portal.py pollDelayMs = {m.group(1) if m else '?'}")
swift = (REPO/"macos/MOSSCapture/Sources/MOSSCaptureCore/CaptureLatencyProbe.swift").read_text()
m2 = re.search(r"portalCycleSeconds: Double = ([0-9.]+)", swift)
check("app's gate constant asserts the same cadence independently", bool(m2),
      f"CaptureLatencyProbe.swift portalCycleSeconds = {m2.group(1) if m2 else '?'}")
check("the two agree TODAY", m and m2 and float(m.group(1))/1000.0 == float(m2.group(1)),
      f"{m.group(1)} ms vs {float(m2.group(1))*1000:.0f} ms")

def rg(pattern, *paths):
    r = subprocess.run(["grep","-rn",pattern,*paths], cwd=REPO,
                       capture_output=True, text=True)
    return [l for l in r.stdout.splitlines() if l.strip()]

py_refs = rg("pollDelayMs", "tests")
check("NO python test asserts the portal's poll cadence", not py_refs,
      f"{len(py_refs)} hits in tests/")
cross = [l for l in rg("pollDelayMs", "macos") + rg("portalCycleSeconds", "tests",
                       "moss_transcribe_diarize")]
check("NO test or source crosses the language boundary between them", not cross,
      f"{len(cross)} cross-language hits")
selfref = rg("portalCycleMS, 1_000", "macos/MOSSCapture/Tests")
check("the ONLY assertion on the term compares the constant to itself", bool(selfref),
      selfref[0].split(":")[0] if selfref else "none found")

print("\n4. IS THE PORTAL POLL A DOMAIN-CONTRACT VALUE? (prd.md Constraints)")
prd = (REPO/"scripts/ralph-afk/prd.md").read_text()
block = prd.split("**Domain-contract values.**")[1].split("\n- **")[0]
block = re.sub(r"\s+", " ", block)   # the bullet is line-wrapped: "pump\n  interval"
for term, expect in [("hard_cap_samples", True), ("pump interval", True),
                     ("poll", False), ("portal", False), ("pollDelayMs", False)]:
    present = term in block
    check(f"contract list {'names' if expect else 'does NOT name'} {term!r}",
          present == expect, f"present={present}")

print(f"\n{'FAILED: ' + ', '.join(fail) if fail else 'ALL CHECKS PASSED'}")
sys.exit(1 if fail else 0)
