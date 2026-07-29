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

     THE DECODER REWRITES A RARE NOUN PHONETICALLY, so the word is matched three ways and the
     reader is told which one answered. `cardamom` has come back as `Cockamom`, `Pardon me`,
     `Cardinal` and `cardigan` in runs whose marker demonstrably landed; an exact string
     comparison called every one of those absent (candidate 59). See MATCH TIERS below.
  2. ECHO - repeated identical text inside one span, which is the echo's fingerprint.
  3. SPEAKER INFLATION - canonical speakers against the number of real voices.

Reading a directory whose snapshot.tsv is PRUNED. `live-cert.sh` and `live-soak.sh` project each
poll down to `{span_id}` (SNAP_PRUNE) because a 16-minute run's full bodies are quadratic; the
untouched snapshot survives only in the periodic `snap-full-NNNN.json` files. So the spans are read
from the richest source available and the reader is told which one it was, because the newest full
snapshot is written every FULL_SNAPSHOT_EVERY polls and therefore covers a PREFIX of the run. A
marker that is absent from a prefix which does not reach the marker's own phase is UNDECIDED, not
missing - the two mean opposite things and only one of them is a defect.

MATCH TIERS, weakest last. Only the first two decide anything.

  VERBATIM      the marker word appears literally in a committed span. A rare noun matched
                exactly is proof by itself and needs no corroboration.
  REWRITTEN     a fragment inside a phase that DECLARES this marker, whose whole text is one
                token n-gram repeated (the driver delivers the marker isolated and repeated, at
                a slowed rate, precisely because a rare noun survives that way), whose consonant
                skeleton is within REWRITE_MIN_SIMILARITY of the marker's. Two independent
                signals - the delivery SHAPE and the SOUND - have to agree.
  CORROBORATING a phonetic near-match anywhere inside a declared phase. Printed with its score,
                never decisive: it is what a human would look at next, not a verdict.

Exit:  0 both codewords reached the transcript (verbatim or rewritten)
       3 the system codeword did not reach the transcript
       4 the room codeword did not reach the transcript
       5 neither did
       2 the run produced nothing to read
       6 REFUSED - the layout carries spans this reducer cannot read (named, never a traceback)
       7 at least one marker is UNDECIDED - the evidence stops before that marker's phase

3/4/5 deliberately carry no cause. They used to read "3 system marker missing (mute killed the
tap)" and "4 room marker missing (no independent microphone content)", which is the same
over-claim candidates 57 and 62 were: "the marker WORD was not transcribed" and "nothing from
that lane reached the transcript" are different findings and were sharing one code's
parenthetical. The cause is in the verdict section, where the evidence for it is.
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


def tokens(text):
    return normalize(text).split()


# ---------------------------------------------------------------- the phonetic key
# A coarse consonant skeleton: vowels and the letters that carry no consonant sound are dropped,
# the remaining letters collapse into equivalence classes, and a class repeated with no vowel
# between (the doubled letter of `cockamom`) collapses to one symbol. Deliberately cruder than a
# metaphone - the question is only "could the decoder have written this while hearing the marker",
# and a crude key with a corroborating delivery shape beats a precise key used alone.
PHONETIC_DIGRAPHS = (("ph", "f"), ("ck", "k"), ("sh", "s"), ("ch", "k"), ("th", "t"))
PHONETIC_CLASS = {"b": "P", "p": "P", "f": "F", "v": "F", "c": "K", "k": "K", "q": "K", "g": "K",
                  "d": "T", "t": "T", "s": "S", "z": "S", "x": "S", "j": "S",
                  "l": "L", "m": "M", "n": "M", "r": "R"}

# MEASURED on the six real evidence directories this loop has produced (637 committed spans):
#   the REWRITTEN tier's true positives score 0.60 (`cockamom`, F1 span 15), 0.80 (`pardon me`,
#   F2 span 29) and 1.00 (`cardamom`, F3 span 5); the ONLY other fragment in the whole corpus
#   with the repeated-delivery shape scores 0.29 (`and parking`, F3 span 215). A 0.60 floor sits
#   in the middle of a 0.29 -> 0.60 gap, not on a cliff edge.
#   The shape is what makes 0.60 safe, and that is not a guess either: WITHOUT it, 0.60 also
#   admits `we return` and `continuous` inside F1's own marker phase - i.e. score alone cannot
#   tell the rewrite from the program around it. Raising the score instead does not work: at 0.80
#   the room marker `obsidian` matches the program's own word `system` (0.75) two hundredths
#   below the line, and F3's `curtains` (0.80) would outrank nothing at all.
REWRITE_MIN_SIMILARITY = 0.60
CORROBORATION_MIN_SIMILARITY = 0.80   # printed only; `cardigan` 0.80 and `cardinal` 0.80 land here
MAX_NGRAM = 3                         # a one-word marker can be rewritten as two: `pardon me`


def phonetic_skeleton(text):
    text = re.sub(r"[^a-z]+", " ", text.lower())
    for pair, single in PHONETIC_DIGRAPHS:
        text = text.replace(pair, single)
    out, prev = [], None
    for ch in text:
        cls = PHONETIC_CLASS.get(ch)
        if cls is None:          # a vowel, h/w/y, or a separator: it breaks a doubled consonant
            prev = None
            continue
        if cls != prev:
            out.append(cls)
        prev = cls
    return "".join(out)


def _levenshtein(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def phonetic_similarity(a, b):
    """1.0 identical, 0.0 nothing in common. Normalising by the LONGER skeleton is what keeps a
    short marker strict: `obsidian` is 4 symbols, so one wrong symbol already costs it 0.25."""
    if not a or not b:
        return 0.0
    return 1.0 - _levenshtein(a, b) / max(len(a), len(b))


def tiled_ngrams(toks):
    """(ngram, repeats) when the fragment is one n-gram repeated >= 2 times and NOTHING else.
    A trailing partial repeat is allowed - the endpointer can cut the last one - but a repetition
    buried in a sentence is not a marker delivery and must not match ('Stir, stir, and then turn
    the circuit.' stays out)."""
    for n in range(1, MAX_NGRAM + 1):
        if len(toks) < 2 * n:
            break
        ngram, reps, i = toks[:n], 0, 0
        while toks[i:i + n] == ngram:
            reps += 1
            i += n
        if reps >= 2 and toks[i:] == ngram[:len(toks) - i]:
            yield " ".join(ngram), reps


def sliding_ngrams(toks):
    for n in range(1, MAX_NGRAM + 1):
        for i in range(len(toks) - n + 1):
            yield " ".join(toks[i:i + n])


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

    # Every labelled fragment, once, with the phases its span touches. The marker search below
    # works on FRAGMENTS rather than whole spans because the delivery shape it looks for - the
    # marker alone, repeated - is a property of one fragment; a span can hold several.
    fragments = []
    for s in spans:
        t_start = t_audio0 + s["start_sample"] / SAMPLE_RATE
        t_end = t_audio0 + s["end_sample"] / SAMPLE_RATE
        where = [p["name"] for p in phases if p["t0"] - 1.0 <= t_end and t_start <= p["t1"] + 1.0]
        for frag in FRAGMENT.findall(s.get("transcript") or ""):
            fragments.append({"span": s["span_id"], "off": round(t_start - t_audio0, 1),
                              "speaker": frag[1], "text": frag[2], "phases": set(where)})

    # ---------------------------------------------------------------- 1. markers
    print("\n-- 1. marker placement (the lane-separation evidence) --")
    print("   matched VERBATIM, then REWRITTEN (the isolated-and-repeated delivery shape plus a "
          "consonant skeleton), then printed-only CORROBORATING near-matches. The decoder rewrites "
          "a rare noun, so an exact comparison alone under-reports - see MATCH TIERS.")
    marker_names = {"system": times.get("MARKER_SYSTEM", ""), "room": times.get("MARKER_ROOM", "")}
    hits = {}        # marker -> verbatim occurrences
    rewrites = {}    # marker -> phonetic occurrences carrying the delivery shape
    undecided = {}   # marker -> the delivery phases the evidence never reached
    beyond = {}      # marker -> the delivery phases past the readable audio, decided or not
    for kind, marker in marker_names.items():
        if not marker:
            continue
        key = phonetic_skeleton(marker)
        # The phases that DELIVER this marker, named by the driver in phases.tsv. Every phonetic
        # match is confined to them: `pardon me` scores 0.60 against `obsidian` as well, and only
        # its position - inside a phase that declares `cardamom`, not one that declares
        # `obsidian` - keeps it from answering the wrong question.
        declared = [p for p in phases if marker.lower() in (p["marker"] or "").lower()]
        declared_names = {p["name"] for p in declared}

        found = []
        for s in spans:
            if marker.lower() in (s.get("transcript") or "").lower():
                t_start = t_audio0 + s["start_sample"] / SAMPLE_RATE
                t_end = t_audio0 + s["end_sample"] / SAMPLE_RATE
                where = [p["name"] for p in phases if p["t0"] - 1.0 <= t_end and t_start <= p["t1"] + 1.0]
                found.append((s["span_id"], round(t_start - t_audio0, 1), where))
        hits[kind] = found

        rewritten, corroborating = [], {}
        for fr in fragments:
            if not (fr["phases"] & declared_names):
                continue
            toks = tokens(fr["text"])
            for ngram, reps in tiled_ngrams(toks):
                score = phonetic_similarity(key, phonetic_skeleton(ngram))
                if score >= REWRITE_MIN_SIMILARITY and marker.lower() not in ngram:
                    rewritten.append((score, ngram, reps, fr))
            for ngram in sliding_ngrams(toks):
                if marker.lower() in ngram:
                    continue
                score = phonetic_similarity(key, phonetic_skeleton(ngram))
                if score >= CORROBORATION_MIN_SIMILARITY and score > corroborating.get(ngram, (0,))[0]:
                    corroborating[ngram] = (score, fr)
        rewritten.sort(key=lambda r: -r[0])
        rewrites[kind] = rewritten
        for _score, ngram, _reps, _fr in rewritten:   # a rewrite is not also its own near-match
            corroborating.pop(ngram, None)
        # Coverage is a property of the directory, not of the answer, so it is measured whether or
        # not the marker was found: a run that landed its marker in phase A and never got to read
        # phase D still has an unmeasured phase D, and dropping that line when the verdict happens
        # to be positive is the silent-omission failure this reducer exists to avoid.
        beyond[kind] = [p["name"] for p in declared if p["t1"] > t_cover]
        covered = [p["name"] for p in declared if p["t1"] <= t_cover]

        for span_id, off, where in found:
            print(f"   {kind:6} {marker!r}: VERBATIM span {span_id} at t+{off}s  "
                  f"phase={where or ['(outside every phase)']}")
        for score, ngram, reps, fr in rewritten:
            print(f"   {kind:6} {marker!r}: REWRITTEN as {ngram!r} x{reps} "
                  f"(skeleton {phonetic_skeleton(ngram)} vs {key}, similarity {score:.2f}) "
                  f"span {fr['span']} at t+{fr['off']}s  phase={sorted(fr['phases'])}")
        for ngram, (score, fr) in sorted(corroborating.items(), key=lambda kv: -kv[1][0])[:4]:
            print(f"   {kind:6} {marker!r}: corroborating near-match {ngram!r} ({score:.2f}) "
                  f"span {fr['span']} at t+{fr['off']}s - printed, NOT decisive")
        if found or rewritten:
            continue
        # An absence is only a measurement where the evidence reaches. The phases that DELIVER
        # this marker are named in phases.tsv, so the question is whether the readable audio
        # covers any of them: absent from a delivery window this directory CAN see is a finding;
        # absent from a run whose delivery windows all fall past the evidence is a statement
        # about the directory. The last full snapshot always precedes the last phase, so the
        # strict reading ("any uncovered phase -> undecided") would fire on every pruned run and
        # therefore decide nothing - which is the failure mode a check that always trips has.
        # Coverage is coverage, whatever ended it: a pruned projection and a session that died at
        # t+13.9s leave the same ignorance about a phase that was never transcribed, so this is
        # NOT gated on is_prefix. Two runs of iteration 26 are exactly that case.
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
            print(f"   {kind:6} {marker!r}: NOT TRANSCRIBED - no verbatim occurrence, and no "
                  f"fragment in {', '.join(sorted(declared_names)) or '(no declared phase)'} "
                  f"carries the repeated delivery shape within {REWRITE_MIN_SIMILARITY:.2f} of "
                  f"its skeleton {key}{note}")

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

    def how(kind):
        """Which tier answered - so 'the marker landed' never hides 'as a different word'."""
        if hits.get(kind):
            return "verbatim"
        r = rewrites.get(kind)
        return (f"phonetically REWRITTEN as {r[0][1]!r} x{r[0][2]} (similarity {r[0][0]:.2f}), "
                f"not verbatim") if r else ""

    sys_ok = bool(hits.get("system")) or bool(rewrites.get("system"))
    room_ok = bool(hits.get("room")) or bool(rewrites.get("room"))
    muted_run = times.get("OUTPUT_MODE") == "muted"
    if sys_ok and muted_run:
        print(f"   system marker present ({how('system')}) in a MUTED run -> the process tap is "
              "UPSTREAM of the output mute; muting is a valid lane-separation mechanism.")
    elif sys_ok:
        print(f"   system marker present ({how('system')}), but OUTPUT_MODE was not 'muted', so "
              "this says nothing about where the tap sits relative to the output volume.")
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
            print(f"   system marker NOT TRANSCRIBED, but the system phases still produced "
                  f"{sys_text} labelled fragments in a MUTED run -> the tap IS upstream of the "
                  "output mute and the mechanism works; what failed is the marker WORD. The "
                  "rewrite search above already looked for it phonetically and found nothing "
                  "carrying the repeated delivery shape, so read the corroborating near-matches "
                  "and the program sentences by hand before concluding the mute is at fault.")
        else:
            print("   system marker ABSENT and the system phases produced no text -> either the "
                  "tap is downstream of the output mute (the mechanism is wrong), or the program "
                  "never decoded.")
    if room_ok:
        print(f"   room marker present ({how('room')}) -> the microphone lane carried content of "
              "its own; the two lanes are genuinely different.")
    elif "room" in undecided:
        print(f"   room marker UNDECIDED -> absent from the readable spans, but "
              f"{', '.join(undecided['room'])} deliver it after the evidence ends at "
              f"t+{t_cover - t_audio0:.1f}s. Not a measurement of the microphone lane.")
    else:
        # Symmetrically to the system branch, and for the same reason: this is a statement about
        # the WORD. The microphone lane is always live, so fragments during the room window are
        # not evidence the room was heard - only the codeword is. "Absent" therefore means the
        # room's own content is UNPROVEN, which is not the same as proven absent.
        print("   room marker NOT TRANSCRIBED, verbatim or phonetically -> the microphone lane's "
              "own content is UNPROVEN. The run still separates the lanes (program vs room), but "
              "nothing here shows the room reached the transcript.")
    for kind, names in beyond.items():
        if names and kind not in undecided:
            print(f"   coverage caveat: the {kind} phases {', '.join(names)} run past the "
                  f"readable audio (t+{t_cover - t_audio0:.1f}s) and did not contribute to the "
                  f"verdict above.")
    # An UNDECIDED marker outranks a missing one: 3/4/5 assert that a codeword did not reach the
    # transcript, and that assertion is exactly what a prefix cannot support. Same rule as
    # candidates 57, 59 and 62 - the verdict word has to name what it decides. A REWRITTEN match
    # counts as reaching the transcript: the clause the marker exists to answer is "did this
    # lane's audio get decoded", and a phonetic rewrite answers it. Which tier answered is
    # printed above and in the verdict line, so nothing is claimed as verbatim that was not.
    if undecided:
        rc = 7
    else:
        rc = 0 if (sys_ok and room_ok) else 5 if not (sys_ok or room_ok) else 3 if not sys_ok else 4
    print(f"   rc={rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
