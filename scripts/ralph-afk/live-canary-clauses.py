#!/usr/bin/env python3
"""Reduce a live-canary.sh (or F1/F3 driver) evidence directory to the PRD's CERTIFICATION
clauses, one section per clause, with the number that decides each one.

live-canary-analyze.py answers a different question - did the two lanes carry different content.
This reducer answers the clauses that decide a certification run:

  * did the meeting stay alive, or did a lane fault end it (Phase M's whole subject);
  * user-visible p95 against the run's gate, with its two components stated SEPARATELY, because
    the plan's Phase F procedure requires that and because only one of them is fixable in code;
  * decoder p95 RTF, and - since candidate 50 / D-c - the token cap actually in force and how
    many spans hit it;
  * per-span COMMIT LAG measured off the event stream, which is what showed that F1's latency
    tail was two runaway spans stalling a serial queue rather than a floor;
  * accepted / accounted / committed equality and published-vs-accepted frames (zero loss, zero
    double count);
  * the lane-health timeline, printed only where it CHANGES, so a degradation or a refusal is
    visible without reading a thousand identical status lines.

Everything it reads is already non-secret: counts, states, timings and a transcript the driver
itself spoke. It prints no token and reads no audio.

Usage:  live-canary-clauses.py <evidence-dir> [--user-visible-gate-ms 4000] [--rtf-gate 1.0]
Exit:   0 every clause it can decide is green   3 at least one is red   2 nothing to read
"""
import argparse
import json
import os
import statistics
import sys
from collections import Counter

SAMPLE_RATE = 16000        # canonical live sample rate  (domain contract)
FRAME_SAMPLES = 8000       # live frame size, 0.5 s      (domain contract)


def pct(values, p):
    """The same nearest-rank p95 the app-owned probe and the earlier reducers use."""
    if not values:
        return None
    s = sorted(values)
    idx = max(0, -(-len(s) * p // 100) - 1)
    return s[idx]


def read_env(path):
    out = {}
    if os.path.exists(path):
        for line in open(path):
            k, _, v = line.strip().partition("=")
            if k:
                out[k] = v
    return out


def read_tsv(path, columns):
    """Rows of `columns` fields; a truncated final line (the driver was killed) is skipped."""
    rows = []
    if not os.path.exists(path):
        return rows
    for line in open(path):
        parts = line.rstrip("\n").split("\t", columns - 1)
        if len(parts) == columns:
            rows.append(parts)
    return rows


def load_json(path):
    try:
        return json.load(open(path))
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("evidence_dir")
    ap.add_argument("--user-visible-gate-ms", type=float, default=4000.0,
                    help="PRD gate for this run: 4000 for the 60 s canary, 6000 for the 300 s "
                         "certification and the soak")
    ap.add_argument("--rtf-gate", type=float, default=1.0)
    args = ap.parse_args()
    d = args.evidence_dir
    red = []
    green = []

    times = read_env(os.path.join(d, "times.env"))
    t0 = float(times.get("T_START") or 0)
    t_audio0 = float(times.get("T_AUDIO0") or t0)
    print(f"== {times.get('LABEL', '?')}  session={times.get('SID', '?')}  "
          f"output_mode={times.get('OUTPUT_MODE', '?')}")

    snap_rows = read_tsv(os.path.join(d, "snapshot.tsv"), 3)
    ev_rows = read_tsv(os.path.join(d, "events.tsv"), 3)
    if not snap_rows:
        print("FATAL: no snapshot polls to read")
        return 2

    # ---------------------------------------------------------- 1. poll health
    # The F3 soak driver writes a COMPACT JQ PROJECTION with a different column layout, so its
    # second column is not a status code. Say that instead of printing a thousand-entry
    # histogram of timestamps, which is what a naive read of that file produces.
    if sum(1 for r in snap_rows if r[1].isdigit() and len(r[1]) == 3) < len(snap_rows) // 2:
        print("FATAL: snapshot.tsv's second column is not an HTTP status code. This reducer "
              "reads the live-canary.sh / F1 layout (t, code, body); the F3 soak driver writes "
              "a compact projection - use its own reducer for that directory.")
        return 2
    codes = Counter(r[1] for r in snap_rows)
    ev_codes = Counter(r[1] for r in ev_rows)
    first_bad = next((float(r[0]) - t0 for r in snap_rows if r[1] != "200"), None)
    print(f"\n-- 1. portal polls --\n   snapshot {dict(codes)}   events {dict(ev_codes)}")
    print(f"   poll window t+{float(snap_rows[0][0]) - t0:.1f}s .. "
          f"t+{float(snap_rows[-1][0]) - t0:.1f}s")
    if first_bad is None:
        green.append("every portal poll answered 200 for the whole run")
        print("   every poll 200 - view authority held for the whole run")
    else:
        red.append(f"the portal stopped answering 200 at t+{first_bad:.1f}s")
        print(f"   FIRST NON-200 AT t+{first_bad:.1f}s  <-- the session or the authority died here")

    # ---------------------------------------------------- 2. transcript growth
    print("\n-- 2. continuously updating transcript (only polls where it changed) --")
    print(f"   {'t+s':>7} {'ver':>5} {'spans':>5} {'accepted':>9} {'committed':>9} "
          f"{'spk':>3}  status")
    last = None
    prev_sig = None
    for t, code, body in snap_rows:
        if code != "200":
            continue
        try:
            payload = json.loads(body)
            sess = payload["snapshot"]["session"]
        except Exception:
            continue
        last = payload
        ident = sess.get("identity_snapshot") or {}
        sig = (sess.get("version"), len(sess.get("committed") or []))
        if sig != prev_sig:
            prev_sig = sig
            print(f"   {float(t) - t0:>7.1f} {sess.get('version'):>5} "
                  f"{len(sess.get('committed') or []):>5} {sess.get('accepted_samples'):>9} "
                  f"{sess.get('committed_samples'):>9} "
                  f"{len(ident.get('canonical_speakers') or []):>3}  {sess.get('status')}")
    if last is None:
        print("FATAL: no 200 snapshot carried a session")
        return 2

    # --------------------------------------------------------- 3. final state
    sess = last["snapshot"]["session"]
    bounds = ((last.get("descriptor") or {}).get("bounds") or {})
    print("\n-- 3. final snapshot --")
    print(f"   status={sess.get('status')}  version={sess.get('version')}  "
          f"failure_reason={sess.get('failure_reason')}  "
          f"terminal_failure={json.dumps(last['snapshot'].get('terminal_failure'))}")
    accepted = sess.get("accepted_samples")
    accounted = sess.get("accounted_samples")
    committed = sess.get("committed_samples")
    retained = sess.get("retained_samples")
    max_ret = bounds.get("max_retained_samples")
    print(f"   accepted={accepted} accounted={accounted} committed={committed} "
          f"retained={retained}" + (f" of {max_ret} "
          f"({100.0 * retained / max_ret:.1f}%)" if max_ret and retained is not None else ""))
    # `v2_session.lanes` is a MAPPING keyed by lane name, not a list.
    v2 = last.get("v2_session") or {}
    v2_lanes = v2.get("lanes") or {}
    lane_records = list(v2_lanes.values()) if isinstance(v2_lanes, dict) else list(v2_lanes)
    lane_accepted = 0
    for lane in lane_records:
        lane_accepted += lane.get("accepted_samples") or 0
        print(f"   v2 lane {str(lane.get('lane')):<11} health={lane.get('health')} "
              f"failure_code={lane.get('failure_code')} failed_samples={lane.get('failed_samples')} "
              f"accepted={lane.get('accepted_samples')} retained={lane.get('retained_samples')}")
    if v2.get("terminal_reason"):
        red.append(f"v2 session terminal_reason={v2.get('terminal_reason')}")

    # ------------------------------------------------------ 4. the accounting
    # The session counters live on the MIXED canonical timeline; the per-lane counters are the
    # two ingress streams. Comparing published frames against the session's accepted samples
    # would be off by the lane count, which is why the lane sum is what the frame check uses.
    print("\n-- 4. accounting (zero loss, zero double count) --")
    running = sess.get("status") == "active"
    if accepted == accounted == committed:
        green.append(f"accepted == accounted == committed == {accepted}")
        print(f"   accepted == accounted == committed == {accepted}  GREEN")
    elif running:
        gap = (accepted or 0) - (accounted or 0)
        print(f"   accepted-accounted = {gap} samples ({gap / SAMPLE_RATE:.2f} s) with "
              f"retained={retained} at a still-ACTIVE session: that is the pending tail, not a "
              f"loss. INCONCLUSIVE here - the equality is a stopped-session clause.")
        if retained is not None and gap > retained + FRAME_SAMPLES:
            red.append(f"accepted-accounted {gap} exceeds retained {retained}")
    else:
        red.append(f"accounting split at a stopped session: accepted={accepted} "
                   f"accounted={accounted} committed={committed}")
        print(f"   SPLIT: accepted={accepted} accounted={accounted} committed={committed}  RED")
    final_status = load_json(os.path.join(d, "status-final.json")) or {}
    stop_status = load_json(os.path.join(d, "stop.json")) or {}
    published = final_status.get("publishedFrameCount")
    if published is not None and lane_accepted:
        print(f"   client published {published} frames; server lane-accepted "
              f"{lane_accepted} samples = {lane_accepted / FRAME_SAMPLES:.1f} frames "
              f"(snapshot taken mid-flight, so read the exact equality off the server's own "
              f"POST /frames tally for this session)")
    print(f"   stop drain: retained={stop_status.get('outboxRetainedFrames')} "
          f"lanes={[(l.get('lane'), l.get('state')) for l in (stop_status.get('lanes') or [])]} "
          f"refusal={stop_status.get('sessionRefusal')}")

    # ------------------------------------------ 5. decoder, and D-c's token cap
    seen = set()
    rtf, elapsed, caps, capped, notable = [], [], [], 0, []
    per_span_decode = {}
    first_seen = {}          # (kind, span_id) -> poll wall clock it first appeared in
    for t, code, body in ev_rows:
        if code != "200":
            continue
        try:
            evs = json.loads(body)["events"]
        except Exception:
            continue
        for e in evs:
            if e["seq"] in seen:
                continue
            seen.add(e["seq"])
            p = e.get("payload") or {}
            span = p.get("span_id")
            if e["kind"] in ("span_frozen", "canonical_processed") and span is not None:
                first_seen.setdefault((e["kind"], span), float(t))
            if e["kind"] == "canonical_processed":
                if p.get("canonical_decode_rtf") is not None:
                    rtf.append(p["canonical_decode_rtf"])
                if p.get("canonical_decode_elapsed_sec") is not None:
                    elapsed.append(p["canonical_decode_elapsed_sec"])
                    per_span_decode[span] = (p.get("canonical_decode_elapsed_sec"),
                                             p.get("canonical_decode_rtf"),
                                             p.get("canonical_decode_token_cap"),
                                             p.get("canonical_decode_capped"))
                if p.get("canonical_decode_token_cap") is not None:
                    caps.append(p["canonical_decode_token_cap"])
                if p.get("canonical_decode_capped"):
                    capped += 1
                if (p.get("identity_status") != "prepared" or p.get("empty_reason")
                        or p.get("submission_refusal")):
                    notable.append((p.get("span_id"), p.get("identity_status"),
                                    p.get("identity_reason"), p.get("empty_reason"),
                                    p.get("submission_refusal")))
            elif e["kind"] not in ("frame_accepted", "canonical_queued", "canonical_started",
                                   "canonical_ready", "snapshot_advanced", "span_frozen",
                                   "session_created"):
                notable.append((e["kind"], json.dumps(p)[:200]))
    print(f"\n-- 5. decoder ({len(seen)} unique events) --")
    if rtf:
        p95 = pct(rtf, 95)
        ok = p95 < args.rtf_gate
        (green if ok else red).append(f"decoder p95 RTF {p95:.3f} < {args.rtf_gate}")
        print(f"   rtf n={len(rtf)} min={min(rtf):.3f} p50={statistics.median(rtf):.3f} "
              f"p95={p95:.3f} max={max(rtf):.3f}   "
              f"{'GREEN' if ok else 'RED'} vs < {args.rtf_gate}")
        print(f"   decode seconds: total={sum(elapsed):.1f} max={max(elapsed):.2f} "
              f"p95={pct(elapsed, 95):.2f}")
    if caps:
        print(f"   D-c token cap in force: {sorted(set(caps))}  spans capped: {capped} of "
              f"{len(caps)}")
    else:
        print("   D-c token cap ABSENT from the event stream - this run did not exercise "
              "candidate 50's fix (an old server, or an old event schema)")
    worst = sorted(per_span_decode.items(), key=lambda kv: -(kv[1][0] or 0))[:5]
    if worst:
        print("   slowest spans (span: elapsed_s rtf cap capped):")
        for span, (el, r, cap, cp) in worst:
            print(f"     {span:>4}: {el:.2f}s rtf={r:.3f} cap={cap} capped={cp}")
    if notable:
        print(f"   notable events ({len(notable)}):")
        for n in notable[:15]:
            print("     ", n)

    # ------------------------------------------------- 6. per-span commit lag
    # The poll interval quantises this to ~1 s, which is far below the 8.5 s tail F1 measured,
    # so it is the right instrument for "is the queue stalled" and the wrong one for a floor.
    lags = []
    for (kind, span), t in first_seen.items():
        if kind != "span_frozen":
            continue
        done = first_seen.get(("canonical_processed", span))
        if done is not None:
            lags.append((span, done - t))
    print("\n-- 6. commit lag per span (span_frozen -> canonical_processed, portal polls) --")
    if lags:
        vals = [v for _, v in lags]
        print(f"   n={len(vals)} p50={statistics.median(vals):.1f}s p95={pct(vals, 95):.1f}s "
              f"max={max(vals):.1f}s")
        late = sorted(lags, key=lambda kv: -kv[1])[:5]
        print("   latest: " + "  ".join(f"span {s}:{v:.1f}s" for s, v in late))
    else:
        print("   (no span pairs observed)")

    # ------------------------------------------------- 7. the latency clause
    print("\n-- 7. user-visible latency (the plan's Phase F components, stated separately) --")
    rep = (load_json(os.path.join(d, "latency-final.json")) or {}).get("latency") or {}
    if rep:
        com = rep.get("committedLatency") or {}
        uv = rep.get("userVisibleMS")
        print(f"   committed p50={com.get('p50MS')} p95={com.get('p95MS')} max={com.get('maxMS')} "
              f"n={com.get('count')}")
        print(f"   render bound={rep.get('renderBoundMS')} "
              f"(portal cycle {rep.get('portalCycleMS')} + snapshot p95 "
              f"{(rep.get('snapshotFetch') or {}).get('p95MS')} + events p95 "
              f"{(rep.get('eventsFetch') or {}).get('p95MS')})")
        print(f"   sufficientSamples={rep.get('sufficientSamples')} "
              f"mixerOriginResolved={rep.get('mixerOriginResolved')} "
              f"timelineIntact={rep.get('timelineIntact')} "
              f"fetchFailures={rep.get('fetchFailures')} "
              f"rejected={rep.get('rejectedNegative')}/{rep.get('rejectedClockRegression')}/"
              f"{rep.get('rejectedAfterTimelineBreak')}")
        if uv is not None:
            ok = uv <= args.user_visible_gate_ms and rep.get("sufficientSamples")
            (green if ok else red).append(
                f"user-visible p95 {uv:.0f} ms vs gate {args.user_visible_gate_ms:.0f} ms")
            print(f"   USER-VISIBLE p95 = {uv:.1f} ms vs gate {args.user_visible_gate_ms:.0f} ms"
                  f"  {'GREEN' if ok else 'RED'}")
    else:
        print("   (no latency report in this evidence directory)")

    # ------------------------------------------------- 8. lane health timeline
    print("\n-- 8. lane health, printed only where it CHANGES --")
    prev = None
    for t, body in read_tsv(os.path.join(d, "status.tsv"), 2):
        try:
            s = json.loads(body)
        except Exception:
            print(f"   {float(t) - t0:>7.1f}  {body[:150]}")
            continue
        lanes = {l["lane"]: (l.get("state"), l.get("failureCode")) for l in (s.get("lanes") or [])}
        sig = (s.get("running"), tuple(sorted(lanes.items())), s.get("sessionRefusal"),
               s.get("pumpFailure"), s.get("outboxDegradation"))
        if sig != prev:
            prev = sig
            print(f"   {float(t) - t0:>7.1f}  running={s.get('running')} lanes={lanes} "
                  f"refusal={s.get('sessionRefusal')} pump={s.get('pumpFailure')} "
                  f"outbox={s.get('outboxDegradation')} frames={s.get('publishedFrameCount')}")

    # ------------------------------------------------------------- the verdict
    print("\n-- verdict --")
    for g in green:
        print(f"   GREEN  {g}")
    for r in red:
        print(f"   RED    {r}")
    rc = 3 if red else 0
    print(f"   rc={rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
