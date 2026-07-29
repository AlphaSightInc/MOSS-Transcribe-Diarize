#!/usr/bin/env python3
"""Derive - and then enforce - the decoder-RTF clause's meaningfulness floor (Q2 / candidate 64).

The ninth amendment: "state a minimum span duration below which RTF is not a meaningful ratio
(fixed per-request overhead dominates), derive that bound from measurement rather than choosing it
to pass, and always report the excluded count alongside the p95 so an exclusion can never be
silent."

THE MODEL.  RTF = decode_elapsed / span_duration, and decode_elapsed = C + W(duration), where C is
the fixed cost of asking the decoder anything at all (request, prefill setup, response) and W is
the audio-proportional work.  So RTF = C/duration + W/duration.  The second term is the decoder's
real-time factor; the first is an artifact of the denominator.  For a span shorter than C the
ratio is forced above any gate by arithmetic alone, however fast the decoder is.

THE DERIVATION, in four independent readings, all reproduced below from real evidence:
  (1) ARITHMETIC   - no decode in the corpus ever completed faster than C_min seconds, so no span
                     at or below C_min can read RTF < 1 whatever the decoder does.
  (2) EMPIRICAL    - every span shorter than the floor read RTF >= 1, and the SHORTEST span that
                     ever read RTF < 1 is exactly at the floor.  Below it the ratio has never
                     discriminated; its verdict is a restatement of the span's length.
  (3) DOMINATION   - a robust fit of elapsed on duration puts C/m (where overhead stops being the
                     MAJORITY term - the amendment's own parenthetical) far ABOVE the floor, so
                     the floor is on the conservative side of the criterion it implements.
  (4) INSENSITIVE  - every floor from the arithmetic one up to the domination one gives the same
                     GREEN/RED verdict on every run in the corpus.  The value is therefore NOT
                     load-bearing, which is what makes "chosen to pass" impossible: the weakest
                     defensible floor already does the whole job and the strongest buys nothing.

WHICH READING GOVERNS.  A larger floor excludes more spans and therefore flatters the gate, so
where the readings disagree the rule takes the one that excludes the FEWEST spans - the EMPIRICAL
boundary (0.13 s) over the domination point the amendment's parenthetical would have allowed
(0.93 s), 7.2x fewer exclusions.  That is the whole of conservatism's work here; it is not a
licence to sit BELOW the boundary, which would leave in spans that also never discriminated and
under-apply the definition rather than apply it carefully.  Checks (1) and (2) fence both
directions: only 0.12-0.13 s passes all nine.

WHY NOT PER-RUN SELF-CALIBRATION.  The same robust fit applied to each run alone puts C/m between
0.59 s and 2.01 s - a 60 s canary has ~50 spans and the fit is dominated by whichever runaway
decodes it happened to see.  A self-calibrating floor would move with the noise it is supposed to
be immune to, so the floor is stated once from the pooled corpus and this probe re-checks it.

It reads only evidence directories this loop produced: counts, durations and timings.  No token,
no audio, no host, no session.

Usage:  rtf-floor-probe.py [--floor-sec X] [dir ...]
Exit:   0 every check passes   1 a check failed   2 not enough corpus to decide
"""
import argparse
import importlib.util
import itertools
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# The floor has ONE definition, and it lives in the reducer that applies it.  This probe imports
# it rather than restating it, so an edit to the constant is caught here instead of drifting.
_spec = importlib.util.spec_from_file_location(
    "live_canary_clauses", os.path.join(HERE, "live-canary-clauses.py"))
_reducer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_reducer)

# The five real certification directories on this host, two builds (`42abc5a` and `7a4f59c`).
# A missing one is skipped, not faked; the probe refuses below a stated corpus size.
DEFAULT_DIRS = [
    ("F1 it.30 (7a4f59c, the RED)", "/tmp/i30-f1-evidence/ralph-canary"),
    ("F1 it.6  (42abc5a, GREEN)", "/tmp/i6-f1-evidence/ralph-canary"),
    ("F2 it.1  (7a4f59c)", "/tmp/i1-f2-evidence/ralph-cert"),
    ("F3 it.12 (7a4f59c)", "/tmp/i12-f3-evidence/ralph-soak"),
    ("F3 it.9  (42abc5a)", "/tmp/i9-f3-evidence/ralph-soak"),
]
MIN_DIRS = 3
MIN_SPANS = 300


def spans(directory):
    """(elapsed, rtf, duration) per DISTINCT canonical_processed event.

    `since_seq` is inclusive, so every poll re-delivers the previous poll's highest event - the
    dedup by seq is the same one candidate 67 had to add to the pipeline probe.
    """
    seen, rows = set(), []
    path = os.path.join(directory, "events.tsv")
    if not os.path.exists(path):
        return rows
    for line in open(path):
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 3 or parts[1] != "200":
            continue
        try:
            evs = json.loads(parts[2])["events"]
        except Exception:
            continue
        for e in evs:
            if e.get("seq") in seen:
                continue
            seen.add(e.get("seq"))
            if e.get("kind") != "canonical_processed":
                continue
            p = e.get("payload") or {}
            el = p.get("canonical_decode_elapsed_sec")
            rtf = p.get("canonical_decode_rtf")
            dur = p.get("frozen_span_duration_sec")
            if el is None or rtf is None or dur is None:
                continue
            rows.append((el, rtf, dur))
    return rows


def theil_sen(points):
    slopes = [(y2 - y1) / (x2 - x1)
              for (x1, y1), (x2, y2) in itertools.combinations(points, 2) if abs(x2 - x1) > 1e-9]
    m = statistics.median(slopes)
    return statistics.median(y - m * x for x, y in points), m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="*", help="evidence directories; default = this host's five")
    ap.add_argument("--floor-sec", type=float, default=_reducer.RTF_FLOOR_SEC,
                    help="the floor under test; defaults to the reducer's own constant")
    ap.add_argument("--rtf-gate", type=float, default=1.0)
    args = ap.parse_args()

    named = ([(d, d) for d in args.dirs] if args.dirs else DEFAULT_DIRS)
    corpus, present = {}, []
    for label, d in named:
        rows = spans(d)
        if rows:
            corpus[label] = rows
            present.append(label)
        else:
            print(f"   (skipped, no readable events: {d})")
    pool = [r for rows in corpus.values() for r in rows]
    if len(present) < MIN_DIRS or len(pool) < MIN_SPANS:
        print(f"REFUSED: {len(present)} directories / {len(pool)} spans is below the stated "
              f"corpus of {MIN_DIRS} directories and {MIN_SPANS} spans. A floor derived from one "
              f"run is a floor fitted to that run's noise - see WHY NOT PER-RUN SELF-CALIBRATION.")
        return 2

    floor = args.floor_sec
    checks = []

    def check(ok, name, detail):
        checks.append((bool(ok), name, detail))

    print(f"CORPUS: {len(present)} directories, {len(pool)} spans, floor under test = {floor:g}s\n")

    # ---------------------------------------------------------------- 0. the duration is measured
    worst = max(abs(du - el / rtf) for el, rtf, du in pool if rtf)
    check(worst < 1e-6, "duration is MEASURED, not inferred",
          f"frozen_span_duration_sec reconciles with elapsed/rtf to {worst:.2e} on all "
          f"{len(pool)} spans - the classification is not a function of the number classified")

    # -------------------------------------------------------------------- 1. the arithmetic floor
    c_min = min(el for el, _, _ in pool)
    check(floor > c_min, "(1) ARITHMETIC - the floor clears the fastest decode ever observed",
          f"fastest decode {c_min:.4f}s; a span at or below it cannot read RTF < 1 whatever the "
          f"decoder does, and the floor {floor:g}s is above that")

    # ---------------------------------------------------------------------- 2. the empirical wall
    below = [(el, rtf, du) for el, rtf, du in pool if du < floor]
    never = [x for x in below if x[1] < args.rtf_gate]
    passing = sorted((x for x in pool if x[1] < args.rtf_gate), key=lambda x: x[2])
    check(below and not never,
          "(2) EMPIRICAL - no span below the floor has ever discriminated",
          (f"all {len(below)} spans shorter than {floor:g}s read RTF >= {args.rtf_gate} "
           f"(range {min(x[1] for x in below):.3f}-{max(x[1] for x in below):.3f})") if below else
          (f"NO span in the corpus is shorter than {floor:g}s, so the floor excludes nothing and "
           f"this reading cannot support it - a floor that removes no observation is not a "
           f"derived boundary, it is a no-op"))
    check(passing and passing[0][2] >= floor,
          "(2) EMPIRICAL - the floor sits AT the discrimination boundary, not above it",
          f"the shortest span that ever read RTF < {args.rtf_gate} is {passing[0][2]:.3f}s "
          f"(elapsed {passing[0][0]:.4f}s, RTF {passing[0][1]:.3f}); a floor above it would be "
          f"excluding spans the ratio demonstrably CAN measure")

    # ----------------------------------------------------------------------- 3. the domination pt
    pts = [(du, el) for el, _, du in pool]
    C, m = theil_sen(pts)
    dom = C / m
    check(floor < dom, "(3) DOMINATION - the floor is conservative against the amendment's own "
                       "criterion",
          f"robust fit elapsed = {C:.4f} + {m:.4f} * duration, so fixed overhead is the MAJORITY "
          f"term below {dom:.3f}s. The amendment's parenthetical would allow a floor "
          f"{('%.1fx' % (dom / floor)) if floor else 'infinitely'} "
          f"larger; this one excludes far fewer spans")

    # ----------------------------------------------------------------- 4. the value is not binding
    grid = [round(c_min + i * (dom - c_min) / 24, 4) for i in range(25)]
    verdicts, rows = {}, []
    for label, rs in corpus.items():
        seq = []
        for f in grid:
            gated = [rtf for _, rtf, du in rs if du >= f]
            seq.append(None if not gated else (_reducer.pct(gated, 95) < args.rtf_gate))
        verdicts[label] = seq
    stable = all(len(set(v)) == 1 for v in verdicts.values())
    check(stable, "(4) INSENSITIVE - the floor's exact value decides nothing",
          f"across 25 floors spanning {grid[0]:g}s..{grid[-1]:g}s (arithmetic floor to domination "
          f"point) every one of the {len(corpus)} runs keeps the SAME verdict. The weakest "
          f"defensible floor already does the whole job; the strongest buys nothing")

    # ------------------------------------------------------- 5. what the floor does, run by run
    print("PER RUN, at the floor under test:")
    for label, rs in corpus.items():
        inc = [rtf for _, rtf, du in rs if du >= floor]
        exc = [(rtf, du) for _, rtf, du in rs if du < floor]
        share = len(exc) / len(rs)
        agg = sum(el for el, _, _ in rs) / sum(du for _, _, du in rs)
        raw95, gat95 = _reducer.pct([r[1] for r in rs], 95), _reducer.pct(inc, 95)
        rows.append((label, len(rs), raw95, gat95, len(exc), share, agg, len(inc)))
        print(f"   {label:28s} n={len(rs):4d}  p95(all)={raw95:6.3f} -> gated={gat95:6.3f}  "
              f"excluded={len(exc):3d} ({100 * share:4.1f}%)  aggregate RTF={agg:.3f}")
    print()

    # The guard is on the SURVIVING population, not on the share removed - see the reducer's
    # RTF_MIN_GATED_SPANS block for why the share cap that stood here first was wrong.
    check(all(r[7] >= _reducer.RTF_MIN_GATED_SPANS for r in rows),
          "(5) every run keeps enough gated spans for a p95 to mean anything",
          f"smallest gated population {min(r[7] for r in rows)} against the "
          f"{_reducer.RTF_MIN_GATED_SPANS} a nearest-rank p95 needs to differ from the maximum; "
          f"largest exclusion is {100 * max(r[5] for r in rows):.1f}% and is REPORTED, not capped")
    check(all(r[6] < args.rtf_gate for r in rows),
          "(5) AGGREGATE RTF is under the gate on every run, nothing excluded",
          f"total decode seconds over total audio seconds ranges "
          f"{min(r[6] for r in rows):.3f}-{max(r[6] for r in rows):.3f}; this is the throughput "
          f"claim no exclusion can touch, and it is gated beside the p95")

    # --------------------------------------------- 6. the effect on the record, stated not hidden
    flipped = [r[0] for r in rows if r[2] >= args.rtf_gate > r[3]]
    unchanged = [r[0] for r in rows if not (r[2] >= args.rtf_gate > r[3])]
    print(f"EFFECT ON THE RECORD (stated, not hidden): the definition turns {len(flipped)} run(s) "
          f"from RED to GREEN - {', '.join(flipped) or 'none'} - and leaves {len(unchanged)} "
          f"unchanged.")
    check(len(flipped) <= 1,
          "(6) the definition changes at most one run's verdict",
          f"a rule that re-coloured several runs at once would be a filter wearing a definition's "
          f"clothes; this one moves {len(flipped)}")

    print()
    bad = 0
    for ok, name, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}\n        {detail}")
        bad += 0 if ok else 1
    print(f"\n{len(checks) - bad}/{len(checks)} checks pass")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
