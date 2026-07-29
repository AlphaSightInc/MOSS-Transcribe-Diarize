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

Reading a directory whose snapshot.tsv is PRUNED. `live-cert.sh` and `live-soak.sh` project each
poll down to `{span_id}` (SNAP_PRUNE) because a 16-minute run's full bodies are quadratic; the
untouched snapshot survives only in the periodic `snap-full-NNNN.json` files. So the spans are read
from the richest source available and the reader is told which one it was, because the newest full
snapshot is written every FULL_SNAPSHOT_EVERY polls and therefore covers a PREFIX of the run. A
marker that is absent from a prefix which does not reach the marker's own phase is UNDECIDED, not
missing - the two mean opposite things and only one of them is a defect.

Usage: live-canary-analyze.py <evidence-dir> [--voices N]
Exit:  0 both markers landed in their own phase    3 system marker missing (mute killed the tap)
       4 room marker missing (no independent microphone content)   5 neither
       2 the run produced nothing to read
       6 REFUSED - the layout carries spans this reducer cannot read (named, never a traceback)
       7 at least one marker is UNDECIDED - the evidence stops before that marker's phase
"""
import argparse
import glob
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


def tsv_snapshots(d):
    """(wall_clock, payload) for every 200 row of snapshot.tsv that carries a session."""
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
            payload = json.loads(body)
        except Exception:
            continue
        snap = payload.get("snapshot")
        if snap and snap.get("session"):
            yield float(t), payload


def full_snapshots(d):
    """(filename, payload) for every snap-full-NNNN.json that carries a session, oldest first
    by the session version it recorded - which is what makes 'the richest' well defined."""
    out = []
    for path in sorted(glob.glob(os.path.join(d, "snap-full-*.json"))):
        try:
            payload = json.load(open(path))
        except Exception:
            continue
        sess = (payload.get("snapshot") or {}).get("session")
        if sess:
            out.append((os.path.basename(path), payload))
    out.sort(key=lambda fp: (fp[1]["snapshot"]["session"].get("version") or 0,
                             len(fp[1]["snapshot"]["session"].get("committed") or [])))
    return out


# What this reducer needs off a committed span. SNAP_PRUNE keeps only `span_id`, so a pruned row
# satisfies none of the other two and the phase attribution below cannot be computed at all.
SPAN_FIELDS = ("transcript", "start_sample", "end_sample")


def spans_readable(spans):
    return all(all(f in s for f in SPAN_FIELDS) for s in spans)


def bounds_of(payload):
    """`bounds` moved when the projection did: the raw response carries it under
    snapshot.descriptor, SNAP_PRUNE lifts it to the top level (and nulls it)."""
    for holder in (payload.get("snapshot") or {}, payload):
        b = (holder.get("descriptor") or {}).get("bounds")
        if b:
            return b
    return None


def identity_growth(d):
    """(wall_clock, canonical_speaker_count) for every 200 snapshot, in order. Survives pruning:
    SNAP_PRUNE keeps identity_snapshot untouched."""
    for t, payload in tsv_snapshots(d):
        sess = payload["snapshot"]["session"]
        yield t, len((sess.get("identity_snapshot") or {}).get("canonical_speakers") or [])


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

    # The END of the run is whatever the last 200 poll said - pruned or not, that row is
    # authoritative for the final version and the final span COUNT (SNAP_PRUNE keeps every
    # span_id). The span BODIES may have to come from somewhere else; see below.
    final_payload = None
    for _t, payload in tsv_snapshots(d):
        final_payload = payload
    fulls = full_snapshots(d)
    final_source = "snapshot.tsv"
    if final_payload is None:
        if not fulls:
            print("FATAL: no 200 snapshot with a session in snapshot.tsv")
            return 2
        final_payload = fulls[-1][1]
        final_source = f"{fulls[-1][0]} (snapshot.tsv absent or unreadable)"

    sess = final_payload["snapshot"]["session"]
    final_spans = sess.get("committed") or []
    ident = sess.get("identity_snapshot") or {}
    canonical = ident.get("canonical_speakers") or []
    bound = (bounds_of(final_payload) or {}).get("max_identity_speakers")

    # Where the span bodies come from. A pruned row carries only `span_id`, so the marker, echo
    # and label sections cannot be computed from it at all - the untouched bodies survive only in
    # the periodic snap-full-NNNN.json files, and the newest of those covers a PREFIX of the run.
    spans, spans_source, spans_payload = final_spans, final_source, final_payload
    if not spans_readable(spans):
        pick = next((fp for fp in reversed(fulls)
                     if spans_readable((fp[1]["snapshot"]["session"].get("committed") or []))), None)
        if pick is None:
            missing = sorted(set(SPAN_FIELDS) - set().union(*(set(s) for s in spans)))
            print(f"REFUSED: {len(spans)} committed spans in {final_source} carry no "
                  f"{', '.join(missing)}. This directory's snapshot.tsv is a PRUNED projection "
                  f"(SNAP_PRUNE in live-cert.sh / live-soak.sh) and the {len(fulls)} "
                  f"snap-full-*.json file(s) beside it hold no readable spans either, so there is "
                  f"nothing to read the markers, the echo or the labels out of. This is a refusal, "
                  f"not a verdict: it says the EVIDENCE is unreadable, not that the lanes failed.")
            return 6
        spans, spans_source, spans_payload = (pick[1]["snapshot"]["session"]["committed"],
                                              pick[0], pick[1])
        bound = bound or (bounds_of(pick[1]) or {}).get("max_identity_speakers")

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

    span_ver = spans_payload["snapshot"]["session"].get("version")
    final_ver = sess.get("version")
    is_prefix = len(spans) < len(final_spans) or (span_ver or 0) < (final_ver or 0)
    # The last instant of AUDIO any readable span covers - the boundary past which this directory
    # can say nothing, and therefore the boundary every absence below has to be judged against.
    t_cover = t_audio0 + max((s["end_sample"] for s in spans), default=0) / SAMPLE_RATE

    print(f"\n== committed spans: {len(spans)}"
          + (f" of the run's final {len(final_spans)}" if is_prefix else "")
          + f"   non-empty: {sum(1 for s in spans if (s.get('transcript') or '').strip())}"
          + f"   version {span_ver}" + (f" of {final_ver}" if is_prefix else "")
          + f"   status {sess.get('status')}")
    print(f"   spans read from {spans_source}")
    if is_prefix:
        print(f"   PREFIX: snapshot.tsv keeps only span_id, so every section below sees audio "
              f"through t+{t_cover - t_audio0:.1f}s only. What happened after that instant is "
              f"not measurable from this directory.")

    # ---------------------------------------------------------------- 1. markers
    print("\n-- 1. marker placement (the lane-separation evidence) --")
    marker_names = {"system": times.get("MARKER_SYSTEM", ""), "room": times.get("MARKER_ROOM", "")}
    hits = {}
    undecided = {}   # marker -> the delivery phases the evidence never reached
    beyond = {}      # marker -> the delivery phases past the readable audio, decided or not
    for kind, marker in marker_names.items():
        if not marker:
            continue
        found = []
        for s in spans:
            if marker.lower() in (s.get("transcript") or "").lower():
                t_start = t_audio0 + s["start_sample"] / SAMPLE_RATE
                t_end = t_audio0 + s["end_sample"] / SAMPLE_RATE
                where = [p["name"] for p in phases if p["t0"] - 1.0 <= t_end and t_start <= p["t1"] + 1.0]
                found.append((s["span_id"], round(t_start - t_audio0, 1), where))
        hits[kind] = found
        if found:
            for span_id, off, where in found:
                print(f"   {kind:6} {marker!r}: span {span_id} at t+{off}s  phase={where or ['(outside every phase)']}")
            continue
        # An absence is only a measurement where the evidence reaches. The phases that DELIVER
        # this marker are named in phases.tsv, so the question is whether the readable audio
        # covers any of them: absent from a delivery window this directory CAN see is a finding;
        # absent from a run whose delivery windows all fall past the evidence is a statement
        # about the directory. The last full snapshot always precedes the last phase, so the
        # strict reading ("any uncovered phase -> undecided") would fire on every pruned run and
        # therefore decide nothing - which is the failure mode a check that always trips has.
        declared = [p for p in phases if marker.lower() in (p["marker"] or "").lower()]
        # Coverage is coverage, whatever ended it: a pruned projection and a session that died at
        # t+13.9s leave the same ignorance about a phase that was never transcribed, so this is
        # NOT gated on is_prefix. Two runs of iteration 26 are exactly that case.
        covered = [p["name"] for p in declared if p["t1"] <= t_cover]
        beyond[kind] = [p["name"] for p in declared if p["t1"] > t_cover]
        if not covered and (declared or is_prefix):
            undecided[kind] = beyond[kind] or ["(no phase declares this marker)"]
            print(f"   {kind:6} {marker!r}: UNDECIDED - absent from the readable spans, and the "
                  f"evidence stops at t+{t_cover - t_audio0:.1f}s before every phase that "
                  f"delivers it ({', '.join(undecided[kind])}). Absence is not measurable here.")
        else:
            note = ""
            if beyond[kind]:
                note = (f" - measured across {len(covered)} of {len(declared)} delivery phases; "
                        f"{', '.join(beyond[kind])} run past t+{t_cover - t_audio0:.1f}s and are "
                        f"not measured here")
            print(f"   {kind:6} {marker!r}: NOT FOUND in any committed span{note}")

    # ---------------------------------------------------------------- 2. echo
    print("\n-- 2. echo fingerprint: the same text transcribed twice inside one span --")
    echo_spans = 0
    echo_examples = []
    total_fragments = 0
    for s in spans:
        frags = FRAGMENT.findall(s.get("transcript") or "")
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
        for f in FRAGMENT.findall(s.get("transcript") or ""):
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
    # that instant than before it. `bound` was resolved with the spans, because SNAP_PRUNE nulls
    # descriptor.bounds and only the full snapshots still carry it.
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
        if "system" in undecided:
            # The remedy differs by cause, so name the cause: a pruned directory can be made
            # readable by keeping a full snapshot later, a run that DIED before its first system
            # phase can only be run again.
            remedy = ("re-run with FULL_SNAPSHOT_EVERY small enough that a full snapshot lands "
                      "after a system phase" if is_prefix else
                      "the session produced no audio past that instant, so this can only be "
                      "answered by another run")
            print(f"   system marker UNDECIDED -> it is absent from the {len(spans)} readable "
                  f"spans, but every phase that delivers it ({', '.join(undecided['system'])}) "
                  f"falls after the evidence ends at t+{t_cover - t_audio0:.1f}s. This directory "
                  f"cannot answer the lane-separation question either way; {remedy}.")
        elif sys_text and muted_run:
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
    elif "room" in undecided:
        print(f"   room marker UNDECIDED -> absent from the readable spans, but "
              f"{', '.join(undecided['room'])} deliver it after the evidence ends at "
              f"t+{t_cover - t_audio0:.1f}s. Not a measurement of the microphone lane.")
    else:
        print("   room marker ABSENT -> nothing external reached the microphone lane. The run "
              "still separates the lanes (program vs room), but the room is silent.")
    for kind, names in beyond.items():
        if names and kind not in undecided:
            print(f"   coverage caveat: the {kind} phases {', '.join(names)} run past the "
                  f"readable audio (t+{t_cover - t_audio0:.1f}s) and did not contribute to the "
                  f"verdict above.")
    # An UNDECIDED marker outranks a missing one: 3/4/5 assert that a marker did not land, and
    # that assertion is exactly what a prefix cannot support. Same rule as candidates 57 and 62 -
    # the verdict word has to name what it decides.
    if undecided:
        rc = 7
    else:
        rc = 0 if (sys_ok and room_ok) else 5 if not (sys_ok or room_ok) else 3 if not sys_ok else 4
    print(f"   rc={rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
