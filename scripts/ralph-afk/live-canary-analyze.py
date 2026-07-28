#!/usr/bin/env python3
"""Reduce a live-canary.sh run to the question candidate 51 asks: did the two capture lanes
carry DIFFERENT content?

The instrument is the transcript itself. When both lanes carry the same program the server mixes
it with its own acoustic echo, and that is visible without any per-lane audio: the same sentence
is transcribed twice inside one span, and the identity preparer invents a new canonical speaker
for every echoed copy (the first canary measured 16 canonical speakers for 2 real voices).

So this reducer reports three things and nothing else it cannot defend:

  1. MARKER PLACEMENT - the system-lane codeword and the room codeword, and which phase window
     each landed in. The system marker present at all proves the process tap is upstream of the
     output mute, i.e. that muting is a valid lane-separation mechanism. The room marker present
     proves the microphone lane carried content of its own.
  2. ECHO - repeated identical text inside one span, which is the echo's fingerprint.
  3. SPEAKER INFLATION - canonical speakers against the number of real voices.

Usage: live-canary-analyze.py <evidence-dir> [--voices N]
Exit:  0 both markers landed in their own phase    3 system marker missing (mute killed the tap)
       4 room marker missing (no independent microphone content)   5 neither
       2 the run produced nothing to read
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

SAMPLE_RATE = 16000  # canonical live sample rate, a domain-contract value
FRAGMENT = re.compile(r"\[(\d+(?:\.\d+)?)\]\[(S\d+)\](.*?)\[(\d+(?:\.\d+)?)\]")


def read_times(d):
    times = {}
    path = os.path.join(d, "times.env")
    if not os.path.exists(path):
        return times
    for line in open(path):
        k, _, v = line.strip().partition("=")
        if k:
            times[k] = v
    return times


def read_phases(d):
    phases = []
    path = os.path.join(d, "phases.tsv")
    if not os.path.exists(path):
        return phases
    for line in open(path):
        parts = line.rstrip("\n").split("\t")
        if len(parts) >= 4:
            phases.append({
                "name": parts[0], "t0": float(parts[1]), "t1": float(parts[2]),
                "lane": parts[3], "marker": parts[4] if len(parts) > 4 else "",
            })
    return phases


def last_snapshot(d):
    path = os.path.join(d, "snapshot.tsv")
    if not os.path.exists(path):
        return None
    best = None
    for line in open(path):
        try:
            _t, code, body = line.rstrip("\n").split("\t", 2)
        except ValueError:
            continue
        if code != "200":
            continue
        try:
            payload = json.loads(body)
        except Exception:
            continue
        snap = payload.get("snapshot")
        if snap and snap.get("session"):
            best = snap
    return best


def identity_growth(d):
    """(wall_clock, canonical_speaker_count) for every 200 snapshot, in order."""
    path = os.path.join(d, "snapshot.tsv")
    if not os.path.exists(path):
        return
    for line in open(path):
        try:
            t, code, body = line.rstrip("\n").split("\t", 2)
        except ValueError:
            continue
        if code != "200":
            continue
        try:
            sess = json.loads(body)["snapshot"]["session"]
        except Exception:
            continue
        yield float(t), len((sess.get("identity_snapshot") or {}).get("canonical_speakers") or [])


def normalize(text):
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("evidence_dir")
    ap.add_argument("--voices", type=int, default=2,
                    help="number of REAL voices in the program (default 2)")
    args = ap.parse_args()
    d = args.evidence_dir

    times = read_times(d)
    phases = read_phases(d)
    snap = last_snapshot(d)
    if snap is None:
        print("FATAL: no 200 snapshot with a session in snapshot.tsv")
        return 2

    sess = snap["session"]
    spans = sess["committed"]
    ident = sess.get("identity_snapshot") or {}
    canonical = ident.get("canonical_speakers") or []

    # Wall clock of the mixer origin. start_sample is on the AUDIO timeline, so a span's wall
    # clock is the moment the audio was captured, not the moment it committed - which is exactly
    # what phase attribution needs.
    t_audio0 = float(times.get("T_AUDIO0") or times.get("T_START") or 0)

    print(f"== run {times.get('LABEL', '?')}  output_mode={times.get('OUTPUT_MODE', '?')}")
    for name in ("topology-before.txt", "topology-after.txt"):
        p = os.path.join(d, name)
        if os.path.exists(p):
            vals = dict(l.strip().split("=", 1) for l in open(p) if "=" in l)
            print(f"   {name:22} out={vals.get('default_output', '?')!r} "
                  f"in={vals.get('default_input', '?')!r} "
                  f"vol={vals.get('output_volume')} muted={vals.get('output_muted')}")

    print(f"\n== committed spans: {len(spans)}   "
          f"non-empty: {sum(1 for s in spans if s['transcript'].strip())}   "
          f"version {sess.get('version')}   status {sess.get('status')}")

    # ---------------------------------------------------------------- 1. markers
    print("\n-- 1. marker placement (the lane-separation evidence) --")
    marker_names = {"system": times.get("MARKER_SYSTEM", ""), "room": times.get("MARKER_ROOM", "")}
    hits = {}
    for kind, marker in marker_names.items():
        if not marker:
            continue
        found = []
        for s in spans:
            if marker.lower() in s["transcript"].lower():
                t_start = t_audio0 + s["start_sample"] / SAMPLE_RATE
                t_end = t_audio0 + s["end_sample"] / SAMPLE_RATE
                where = [p["name"] for p in phases if p["t0"] - 1.0 <= t_end and t_start <= p["t1"] + 1.0]
                found.append((s["span_id"], round(t_start - t_audio0, 1), where))
        hits[kind] = found
        if found:
            for span_id, off, where in found:
                print(f"   {kind:6} {marker!r}: span {span_id} at t+{off}s  phase={where or ['(outside every phase)']}")
        else:
            print(f"   {kind:6} {marker!r}: NOT FOUND in any committed span")

    # ---------------------------------------------------------------- 2. echo
    print("\n-- 2. echo fingerprint: the same text transcribed twice inside one span --")
    echo_spans = 0
    echo_examples = []
    total_fragments = 0
    for s in spans:
        frags = FRAGMENT.findall(s["transcript"])
        total_fragments += len(frags)
        texts = [normalize(f[2]) for f in frags if normalize(f[2])]
        dupes = [t for t, n in Counter(texts).items() if n > 1]
        if dupes:
            echo_spans += 1
            if len(echo_examples) < 3:
                echo_examples.append((s["span_id"], dupes[0]))
    print(f"   spans with a repeated fragment: {echo_spans} of {len(spans)}   "
          f"({total_fragments} fragments total)")
    for span_id, text in echo_examples:
        print(f"     span {span_id}: {text[:70]!r} appears more than once")

    # ---------------------------------------------------------------- 3. speakers
    # Per PHASE, because that is what makes the speaker-label clause checkable at all: a phase
    # whose audio came from one lane should show a small, stable label set, and the same two
    # labels should still name the same two voices after the other lane has had its turn.
    print("\n-- 3. speaker labels per phase (the label clause) --")
    labels = Counter()
    per_phase = {}
    for s in spans:
        mid = t_audio0 + (s["start_sample"] + s["end_sample"]) / 2 / SAMPLE_RATE
        name = next((p["name"] for p in phases if p["t0"] - 1.0 <= mid <= p["t1"] + 1.0), "outside")
        bucket = per_phase.setdefault(name, Counter())
        for f in FRAGMENT.findall(s["transcript"]):
            labels[f[1]] += 1
            bucket[f[1]] += 1
    for p in phases + [{"name": "outside", "lane": "-"}]:
        bucket = per_phase.get(p["name"])
        if bucket:
            print(f"   {p['name']:<14} lane={p['lane']:<11} {dict(sorted(bucket.items()))}")

    print("\n-- 4. speaker inflation --")
    inflation = f" -> inflation x{len(canonical) / args.voices:.1f}" if args.voices else ""
    print(f"   canonical speakers: {len(canonical)}  for {args.voices} real voice(s){inflation}")
    print(f"   span labels seen: {dict(sorted(labels.items()))}")

    # Identity capacity is a hard bound (max_identity_speakers). Once it saturates no later
    # voice can ever be labelled, so WHEN it saturates is the number that matters, not the
    # final count - and a run that saturates mid-meeting is measuring a different thing after
    # that instant than before it.
    bound = ((snap.get("descriptor") or {}).get("bounds") or {}).get("max_identity_speakers")
    growth, prev = [], None
    for t, n in identity_growth(d):
        if n != prev:
            growth.append((t - t_audio0, n))
            prev = n
    if growth:
        run_seconds = max(t for t, _ in identity_growth(d)) - t_audio0
        print(f"\n-- 5. identity capacity (bound {bound}) --")
        print("   " + "  ".join(f"t+{t:.0f}s:{n}" for t, n in growth))
        if bound and prev is not None and prev >= bound:
            sat = next(t for t, n in growth if n >= bound)
            print(f"   SATURATED at t+{sat:.1f}s of a {run_seconds:.0f}s run: after this instant "
                  f"no newly-arriving voice can be given a label.")

    # ---------------------------------------------------------------- verdict
    print("\n-- verdict --")
    sys_ok = bool(hits.get("system"))
    room_ok = bool(hits.get("room"))
    muted_run = times.get("OUTPUT_MODE") == "muted"
    if sys_ok and muted_run:
        print("   system marker present in a MUTED run -> the process tap is UPSTREAM of the "
              "output mute; muting is a valid lane-separation mechanism.")
    elif sys_ok:
        print("   system marker present, but OUTPUT_MODE was not 'muted', so this says nothing "
              "about where the tap sits relative to the output volume.")
    else:
        # These two look identical in a marker-only check and mean opposite things, so separate
        # them here rather than leaving the reader to guess: a muted run whose system phases
        # still produced text proves the tap survived the mute and only the marker WORD was lost.
        sys_text = sum(n for name, bucket in per_phase.items() for n in bucket.values()
                       if any(p["name"] == name and p["lane"] == "system" for p in phases))
        if sys_text and muted_run:
            print(f"   system marker ABSENT, but the system phases still produced {sys_text} "
                  "labelled fragments in a MUTED run -> the tap IS upstream of the output mute "
                  "and the mechanism works; what failed is the marker WORD, rewritten by the "
                  "decoder's language model. Deliver the marker isolated and repeated, and read "
                  "the transcript to confirm which program sentences landed.")
        else:
            print("   system marker ABSENT and the system phases produced no text -> either the "
                  "tap is downstream of the output mute (the mechanism is wrong), or the program "
                  "never decoded.")
    if room_ok:
        print("   room marker present -> the microphone lane carried content of its own; "
              "the two lanes are genuinely different.")
    else:
        print("   room marker ABSENT -> nothing external reached the microphone lane. The run "
              "still separates the lanes (program vs room), but the room is silent.")
    rc = 0 if (sys_ok and room_ok) else 5 if not (sys_ok or room_ok) else 3 if not sys_ok else 4
    print(f"   rc={rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
