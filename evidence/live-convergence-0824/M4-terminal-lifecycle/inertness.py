"""Do the instruments that share the driver still reproduce their CHECKED-IN artifacts?

The shared driver (`verify_runtime_rolling.py`) changed twice this iteration: `build_runtime`
gained two optional parameters (`terminal_finalizer`, `terminal_scheduler`, both `None`
unless a caller asks) and `run_case`'s frame loop moved into `feed_meeting`, which `run_case`
now calls and which `verify_terminal_lifecycle.py` calls too. Neither change is supposed to
move a number, in any of the SIX instruments that share the driver.

Compared field by field, excluding four categories of value that a rerun moves on its own.
Each exclusion is a category, named with its reason, not a hand-picked field that differed:

  recorded_at                                     when the run happened
  decode_elapsed_sec, completion_queue_wait_ms,   wall-clock readings of this machine
  completion_rtf
  retained_high_water_samples,                    the rolling ring's high-water mark, which
  rolling_high_water_observed, peak_retained_bytes  two identical runs already disagree on
                                                  (verify_terminal_tape.py G6 documents it)
  text_revision_versions                          WHICH poll a driver happened to catch;
                                                  verify_portal_surface.py documents the
                                                  sequence as evidence, not an expectation
  findings                                        Python set-repr ordering inside a rejected
                                                  arm's message string (the sets are equal;
                                                  every gate id in them is compared below)

Every instrument's own exit code is reported beside the comparison: an instrument that
reproduced its artifact but stopped passing its gates would be the same defect.
"""
import json, re, subprocess, sys, tempfile
from pathlib import Path

REPO = Path("/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize")
PROTO = REPO / "prototypes/streaming-diarization/live-convergence"
EV = REPO / "evidence/live-convergence-0824"
NOISE = {
    "recorded_at",
    "decode_elapsed_sec", "completion_queue_wait_ms", "completion_rtf",
    "retained_high_water_samples", "rolling_high_water_observed", "peak_retained_bytes",
    "text_revision_versions",
    "findings",
}
CASES = [
    ("verify_runtime_rolling.py", EV / "M2-runtime-wiring/verify.json"),
    ("verify_rolling_events.py", EV / "M2-event-serialization/verify.json"),
    ("verify_portal_surface.py", EV / "M2-portal-surface/verify.json"),
    ("verify_export_surface.py", EV / "M2-export-switch/verify.json"),
    ("verify_terminal_tape.py", EV / "M4-terminal-tape/verify.json"),
    ("verify_terminal_finalizer.py", EV / "M4-terminal-finalizer/verify.json"),
]

def strip(value):
    if isinstance(value, dict):
        return {k: strip(v) for k, v in value.items() if k not in NOISE}
    if isinstance(value, list):
        return [strip(v) for v in value]
    return value

def gate_ids(value, found=None):
    """Every gate id named in an artifact's message strings, so an excluded `findings`
    list is still compared for WHAT it found rather than skipped."""
    found = set() if found is None else found
    if isinstance(value, str):
        found |= set(re.findall(r"\bG\d+\b", value))
    elif isinstance(value, dict):
        for item in value.values():
            gate_ids(item, found)
    elif isinstance(value, list):
        for item in value:
            gate_ids(item, found)
    return found

print(__doc__)
ok = True
for name, artifact in CASES:
    out = Path(tempfile.mkstemp(suffix=".json")[1])
    proc = subprocess.run(
        [str(REPO / ".venv/bin/python"), str(PROTO / name), "--output", str(out)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not out.read_text().strip():
        print(f"{name:<32} RUN FAILED exit={proc.returncode}")
        ok = False
        continue
    fresh_raw, checked_raw = json.loads(out.read_text()), json.loads(artifact.read_text())
    fresh, checked = strip(fresh_raw), strip(checked_raw)
    same = fresh == checked and gate_ids(fresh_raw) == gate_ids(checked_raw)
    ok = ok and same
    print(f"{name:<32} vs {artifact.relative_to(REPO)}")
    print(f"{'':<32}    identical: {same}   instrument exit: {proc.returncode}   "
          f"gate ids: {'==' if gate_ids(fresh_raw) == gate_ids(checked_raw) else '!='}")
    if not same:
        for key in sorted(set(fresh) | set(checked)):
            if fresh.get(key) != checked.get(key):
                print(f"{'':<36}differs at {key!r}")
print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
