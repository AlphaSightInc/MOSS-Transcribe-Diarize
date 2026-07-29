#!/usr/bin/env python3
"""Reduce a live-canary.sh / live-soak.sh (or F1) evidence directory to the PRD's CERTIFICATION
clauses, one section per clause, with the number that decides each one.

live-canary-analyze.py answers a different question - did the two lanes carry different content.
This reducer answers the clauses that decide a certification run:

  * did the meeting stay alive, or did a lane fault end it (Phase M's whole subject);
  * user-visible p95 against the run's gate, with its two components stated SEPARATELY, because
    the plan's Phase F procedure requires that and because only one of them is fixable in code -
    and only when the app-owned probe's own validity flags say the number is admissible. A run
    the probe disqualifies (too few committed advances, no mixer origin, no number at all) is
    UNDECIDED, never RED: "the gate was missed" and "the run cannot answer the gate" are
    different verdicts and must not share a word (candidate 57);
  * decoder p95 RTF, and - since candidate 50 / D-c - the token cap actually in force and how
    many spans hit it;
  * per-span COMMIT LAG measured off the event stream, which is what showed that F1's latency
    tail was two runaway spans stalling a serial queue rather than a floor;
  * accepted / accounted / committed equality and published-vs-accepted frames (zero loss, zero
    double count);
  * the lane-health timeline, printed only where it CHANGES, so a degradation or a refusal is
    visible without reading a thousand identical status lines;
  * and, for a SOAK directory (one that carries view-checks.tsv), the 16-minute clause word by
    word: periodic accepted audio every wall-clock minute, the SAME view authority answering
    after the retired 900 s expiry, and a clean stop revoking it immediately.

A directory whose snapshot or event layout this reducer does not understand loses only the
sections that read those files, by name, and the run then exits 2 - never 0. Reading half a
directory is useful; letting a half-read directory look like a pass is not.

Everything it reads is already non-secret: counts, states, timings and a transcript the driver
itself spoke. It prints no token and reads no audio.

Usage:  live-canary-clauses.py <evidence-dir> [--user-visible-gate-ms 4000] [--rtf-gate 1.0]
                                              [--min-minute-audio-s 30]
Exit:   0 every clause it can decide is green   3 at least one is red
        2 nothing to read, or a clause could not be decided
"""
import argparse
import json
import os
import statistics
import sys
from collections import Counter

SAMPLE_RATE = 16000        # canonical live sample rate  (domain contract)
FRAME_SAMPLES = 8000       # live frame size, 0.5 s      (domain contract)
VIEW_CLAUSE_AGE = 900.0    # the RETIRED fixed expiry; the clause is "still works after it"


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


def codes_in_column_two(rows):
    """True when column 2 really is an HTTP status code.

    The pre-repo F3 soak driver wrote (t, age, code, projection), so its second column is an
    elapsed time. Reading that as a status code produces a plausible-looking and completely
    meaningless histogram, which is worse than refusing.
    """
    if not rows:
        return False
    return sum(1 for r in rows if r[1].isdigit() and len(r[1]) == 3) >= len(rows) // 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("evidence_dir")
    ap.add_argument("--user-visible-gate-ms", type=float, default=4000.0,
                    help="PRD gate for this run: 4000 for the 60 s canary, 6000 for the 300 s "
                         "certification and the soak")
    ap.add_argument("--rtf-gate", type=float, default=1.0)
    ap.add_argument("--interrupt-report",
                    help="F2 only: the JSON written by live-cert-interrupt.sh on the server. "
                         "Without it the 5 s network-interruption clause is not asserted at all; "
                         "with it, a report that cannot be read is UNDECIDED, never silence.")
    ap.add_argument("--min-minute-audio-s", type=float, default=30.0,
                    help="soak only: the floor a wall-clock minute's accepted audio must clear "
                         "for 'periodic accepted audio'. Not a PRD constant - F3's healthy "
                         "minutes measured 56-62 s, so 30 s is half of what a live meeting "
                         "produced.")
    args = ap.parse_args()
    d = args.evidence_dir
    red = []
    green = []
    undecided = []

    times = read_env(os.path.join(d, "times.env"))
    t0 = float(times.get("T_START") or 0)
    t_audio0 = float(times.get("T_AUDIO0") or t0)
    print(f"== {times.get('LABEL', '?')}  session={times.get('SID', '?')}  "
          f"output_mode={times.get('OUTPUT_MODE', '?')}")

    # The F2 interruption window, loaded HERE rather than in section 10, because section 1 has to
    # know about it. An F2 run causes its own refusals on purpose: without this, the reducer would
    # call the run RED for the outage the run exists to produce - candidate 57's defect exactly,
    # a verdict word naming something it does not decide. The two hosts' wall clocks are
    # independent and the SERVER's steps ~1.5 s backwards every ~32 s (candidate 56), so the
    # window is widened by INT_SKEW on both sides: this asks "was this poll during the outage",
    # not "when exactly".
    INT_SKEW = 6.0
    interrupt = load_json(args.interrupt_report) if args.interrupt_report else None
    int_w0 = float((interrupt or {}).get("t_drop_begin_wall") or 0)
    int_w1 = float((interrupt or {}).get("t_drop_end_wall") or 0)

    def in_interrupt(t):
        return bool(int_w0) and (int_w0 - INT_SKEW) <= float(t) <= (int_w1 + INT_SKEW)

    snap_rows = read_tsv(os.path.join(d, "snapshot.tsv"), 3)
    ev_rows = read_tsv(os.path.join(d, "events.tsv"), 3)
    view_rows = read_tsv(os.path.join(d, "view-checks.tsv"), 6)
    is_soak = bool(view_rows)

    # A layout this reducer cannot read costs only the sections that read it, and it costs the
    # run its green: `undecided` forces rc=2 at the end.
    snap_ok = codes_in_column_two(snap_rows)
    ev_ok = codes_in_column_two(ev_rows)
    if not snap_rows:
        print("\n-- snapshot.tsv --\n   ABSENT or unreadable")
        undecided.append("snapshot.tsv absent: sections 1-4 undecided")
    elif not snap_ok:
        print("\n-- snapshot.tsv --\n   REFUSED: column 2 is not an HTTP status code. This "
              "reducer reads the live-canary.sh / live-soak.sh / F1 layout (t, code, body); the "
              "pre-repo F3 soak driver wrote (t, age, code, projection). Sections 1-4 and the "
              "per-minute soak clause are skipped rather than mis-read.")
        undecided.append("snapshot.tsv layout not understood: sections 1-4 undecided")
    if ev_rows and not ev_ok:
        print("\n-- events.tsv --\n   REFUSED: column 2 is not an HTTP status code (same "
              "layout mismatch). Sections 5-6 are skipped rather than mis-read.")
        undecided.append("events.tsv layout not understood: sections 5-6 undecided")

    last = None
    if snap_ok:
        # ------------------------------------------------------ 1. poll health
        codes = Counter(r[1] for r in snap_rows)
        ev_codes = Counter(r[1] for r in ev_rows) if ev_ok else {}
        during_int = [r for r in snap_rows if r[1] != "200" and in_interrupt(r[0])]
        first_bad = next((float(r[0]) - t0 for r in snap_rows
                          if r[1] != "200" and not in_interrupt(r[0])), None)
        print(f"\n-- 1. portal polls --\n   snapshot {dict(codes)}   events {dict(ev_codes)}")
        print(f"   poll window t+{float(snap_rows[0][0]) - t0:.1f}s .. "
              f"t+{float(snap_rows[-1][0]) - t0:.1f}s")
        if during_int:
            # Said out loud, never subtracted silently: an excluded refusal is still a refusal,
            # and section 10 is where it has to earn its keep as evidence the outage was real.
            print(f"   {len(during_int)} non-200 polls fall inside the armed interruption window "
                  f"and are EXCLUDED from this clause - they are the outage this run caused on "
                  f"purpose, and section 10 decides them")
        if first_bad is None:
            suffix = (f" (outside the {len(during_int)} polls of the armed interruption)"
                      if during_int else "")
            green.append(f"every portal poll answered 200 for the whole run{suffix}")
            print("   every poll 200 - view authority held for the whole run")
        else:
            # A soak STOPS the session on purpose, so polls after T_STOP are expected to refuse.
            t_stop = float(times.get("T_STOP") or 0)
            if t_stop and first_bad + t0 > t_stop:
                green.append(f"every portal poll answered 200 until the clean stop "
                             f"(first non-200 at t+{first_bad:.1f}s, {first_bad + t0 - t_stop:.1f}s "
                             f"after stop)")
                print(f"   first non-200 at t+{first_bad:.1f}s, which is "
                      f"{first_bad + t0 - t_stop:.1f}s AFTER the clean stop - that is the "
                      f"revocation, not a death")
            else:
                red.append(f"the portal stopped answering 200 at t+{first_bad:.1f}s")
                print(f"   FIRST NON-200 AT t+{first_bad:.1f}s  <-- the session or the "
                      f"authority died here")

        # ------------------------------------------------ 2. transcript growth
        print("\n-- 2. continuously updating transcript (only polls where it changed) --")
        print(f"   {'t+s':>7} {'ver':>5} {'spans':>5} {'accepted':>9} {'committed':>9} "
              f"{'spk':>3}  status")
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
            print("   FATAL: no 200 snapshot carried a session")
            undecided.append("no 200 snapshot carried a session")

    if last is not None:
        # ----------------------------------------------------- 3. final state
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
                  f"failure_code={lane.get('failure_code')} "
                  f"failed_samples={lane.get('failed_samples')} "
                  f"accepted={lane.get('accepted_samples')} retained={lane.get('retained_samples')}")
        if v2.get("terminal_reason"):
            red.append(f"v2 session terminal_reason={v2.get('terminal_reason')}")

        # -------------------------------------------------- 4. the accounting
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
                  f"retained={retained} at a still-ACTIVE session: that is the pending tail, not "
                  f"a loss. INCONCLUSIVE here - the equality is a stopped-session clause.")
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

    first_seen = {}          # (kind, span_id) -> poll wall clock it first appeared in
    if ev_ok:
        # -------------------------------------- 5. decoder, and D-c's token cap
        seen = set()
        rtf, elapsed, caps, capped, notable = [], [], [], 0, []
        per_span_decode = {}
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

        # --------------------------------------------- 6. per-span commit lag
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
        # Candidate 57. "the gate was missed" and "the run cannot answer the gate" are different
        # verdicts and must not share a word. This clause used to fold `sufficientSamples` into the
        # threshold comparison, so iteration 26's two cut-short canaries printed
        # `USER-VISIBLE p95 = 3970.7 ms vs gate 4000 ms  RED` - a comparison that PASSED, labelled
        # with the word for failing it. A reader trusting the verdict line learned the opposite of
        # the truth. Same shape as iteration 22's finding that the reducer printed F1's lane
        # failure and decided nothing.
        #
        # The split, and where the rule comes from: the app-owned probe already publishes its own
        # validity flags (CaptureLatencyProbe.report), so the reducer reads them rather than
        # re-deriving the probe's minimum here - a second copy of that constant would drift.
        #   mixerOriginResolved false -> committed latency has no capture origin to be measured
        #                                against, so the number is not the gated quantity.
        #   sufficientSamples   false -> fewer committed advances than the probe's own minimum;
        #                                its docstring says this is "a sample, not a distribution".
        #   userVisibleMS       null  -> one of the two components was never measured.
        # Any of those three: UNDECIDED, and the threshold comparison is NOT asserted at all.
        #   timelineIntact      false -> NOT a disqualifier. The probe latches it and rejects every
        #                                later advance (rejectedAfterTimelineBreak), so the samples
        #                                that survive are real and sufficientSamples already decides
        #                                whether enough of them remain - but they cover a PREFIX of
        #                                the run, so the caveat travels with the verdict.
        disqualifiers = []
        if uv is None:
            disqualifiers.append("userVisibleMS is null - committed p95 or the render bound was "
                                 "never measured")
        if not rep.get("mixerOriginResolved"):
            disqualifiers.append("mixerOriginResolved=false - committed latency has no capture "
                                 "origin to be measured against")
        if not rep.get("sufficientSamples"):
            disqualifiers.append(f"sufficientSamples=false - {com.get('count')} committed advances "
                                 f"is below the probe's own minimum; that is a sample, not a "
                                 f"distribution")
        caveat = ""
        if not rep.get("timelineIntact"):
            caveat = (" [timelineIntact=false: the probe stopped accepting advances mid-run, so "
                      "this covers a PREFIX of the meeting]")
        if disqualifiers:
            shown = f"{uv:.1f} ms" if uv is not None else "(none)"
            print(f"   USER-VISIBLE p95 = {shown}  NOT A QUALIFIED MEASUREMENT - this run does "
                  f"NOT decide the {args.user_visible_gate_ms:.0f} ms gate, either way")
            for why in disqualifiers:
                print(f"     - {why}")
            undecided.append(
                f"user-visible latency clause UNPROVEN, not failed"
                + (f" (the run's own number, {uv:.0f} ms, is not admissible)" if uv is not None
                   else "")
                + ": " + "; ".join(disqualifiers) + caveat)
        else:
            ok = uv <= args.user_visible_gate_ms
            (green if ok else red).append(
                f"user-visible p95 {uv:.0f} ms vs gate {args.user_visible_gate_ms:.0f} ms" + caveat)
            print(f"   USER-VISIBLE p95 = {uv:.1f} ms vs gate {args.user_visible_gate_ms:.0f} ms"
                  f"  {'GREEN' if ok else 'RED'}{caveat}")
    else:
        # Saying nothing here would let a directory with no latency report reduce to rc=0 on the
        # strength of the clauses it DOES carry - the omission this reducer exists to prevent.
        print("   (no latency report in this evidence directory)")
        undecided.append("no latency-final.json in this evidence directory - the user-visible "
                         "latency clause is UNPROVEN, not failed")

    # ------------------------------------------------- 8. lane health timeline
    # This section used to PRINT the client's own verdict and decide nothing, so F1's evidence
    # directory - whose system lane goes failed at t+86.0s, its red zero-loss sub-clause - reduced
    # to rc=0. The timeline is now read as clauses, using the shipped contracts to decide which
    # transition is a fault and which is a designed survival:
    #   lane failed          -> RED. Since D-a an overrun is a DEGRADATION, so a failed lane means
    #                           the lane genuinely stopped producing audio.
    #   lane degraded        -> reported, not red. D-a's whole point is that the meeting survives.
    #   sessionRefusal       -> RED. K4: the session the client is publishing to is gone.
    #   outboxDegradation    -> RED. B2: the typed overflow state is accepted-audio loss.
    #   pumpFailure          -> reported, not red. 53 deliberately leaves the publish verdict
    #                           standing while the heartbeat keeps the meeting alive.
    print("\n-- 8. lane health, printed only where it CHANGES --")
    prev = None
    lane_failed = {}         # lane -> (t+s, code) first time it reported failed
    lane_degraded = {}
    first_refusal = None     # (t+s, refusal) first non-null sessionRefusal
    first_outbox = None
    first_pump = None
    for t, body in read_tsv(os.path.join(d, "status.tsv"), 2):
        try:
            s = json.loads(body)
        except Exception:
            print(f"   {float(t) - t0:>7.1f}  {body[:150]}")
            continue
        rel = float(t) - t0
        lanes = {l["lane"]: (l.get("state"), l.get("failureCode")) for l in (s.get("lanes") or [])}
        for name, (state, code) in lanes.items():
            if state == "failed" and name not in lane_failed:
                lane_failed[name] = (rel, code)
            if state == "degraded" and name not in lane_degraded:
                lane_degraded[name] = (rel, code)
        if s.get("sessionRefusal") and first_refusal is None:
            first_refusal = (rel, s["sessionRefusal"])
        if s.get("outboxDegradation") and first_outbox is None:
            first_outbox = (rel, s["outboxDegradation"])
        if s.get("pumpFailure") and first_pump is None:
            first_pump = (rel, s["pumpFailure"])
        sig = (s.get("running"), tuple(sorted(lanes.items())), s.get("sessionRefusal"),
               s.get("pumpFailure"), s.get("outboxDegradation"))
        if sig != prev:
            prev = sig
            print(f"   {rel:>7.1f}  running={s.get('running')} lanes={lanes} "
                  f"refusal={s.get('sessionRefusal')} pump={s.get('pumpFailure')} "
                  f"outbox={s.get('outboxDegradation')} frames={s.get('publishedFrameCount')}")
    for name, (rel, code) in sorted(lane_failed.items()):
        red.append(f"lane {name} reported FAILED at t+{rel:.1f}s ({code})")
    for name, (rel, code) in sorted(lane_degraded.items()):
        print(f"   lane {name} degraded at t+{rel:.1f}s ({code}) - designed to survive (D-a), "
              f"not a clause failure; the dropped count is the report")
    if first_refusal:
        red.append(f"sessionRefusal {first_refusal[1]} at t+{first_refusal[0]:.1f}s - the "
                   f"session the client was publishing to was gone")
    if first_outbox:
        red.append(f"outboxDegradation {first_outbox[1]} at t+{first_outbox[0]:.1f}s - "
                   f"accepted audio the client could not deliver")
    if first_pump:
        print(f"   pumpFailure {first_pump[1]} first at t+{first_pump[0]:.1f}s - reported, not a "
              f"clause failure: 53 keeps the heartbeat alive through a failing publish")

    # ------------------------------------------------------ 9. the soak clause
    # "capture remains active with periodic accepted audio and /live polling; the same view
    #  authority works after minute 15, then clean stop immediately revokes it."
    # Only a directory that carries view-checks.tsv is a soak; a 60 s canary has no such clause
    # and must not acquire one here.
    if is_soak:
        t_stop = float(times.get("T_STOP") or 0)
        clause_age = float(times.get("VIEW_CLAUSE_AGE") or VIEW_CLAUSE_AGE)
        print("\n-- 9. the 16-minute soak clause --")

        # (a) periodic accepted audio, per wall-clock minute
        if snap_ok:
            minutes = {}     # minute index -> (last accepted_samples, last committed span count)
            for t, code, body in snap_rows:
                if code != "200":
                    continue
                try:
                    sess = json.loads(body)["snapshot"]["session"]
                except Exception:
                    continue
                m = int((float(t) - t0) // 60)
                minutes[m] = (sess.get("accepted_samples") or 0,
                              len(sess.get("committed") or []))
            keys = sorted(minutes)
            thin, silent = [], []
            print(f"   {'minute':>6} {'accepted_s':>11} {'new_spans':>10}")
            prev_acc, prev_spans = 0, 0
            for m in keys:
                acc, spans = minutes[m]
                d_acc = (acc - prev_acc) / SAMPLE_RATE
                d_spans = spans - prev_spans
                prev_acc, prev_spans = acc, spans
                # The final minute is a partial one (the run stops inside it), so it cannot be
                # held to a full minute's floor.
                partial = m == keys[-1]
                flag = ""
                if not partial and d_acc < args.min_minute_audio_s:
                    thin.append((m, d_acc))
                    flag = "  <-- below the floor"
                if not partial and d_spans <= 0:
                    silent.append(m)
                    flag += "  <-- no new committed span"
                print(f"   {m:>6} {d_acc:>11.1f} {d_spans:>10}{flag}"
                      + ("   (partial)" if partial else ""))
            if not keys:
                undecided.append("no 200 snapshot minutes to measure periodic audio")
            elif thin or silent:
                red.append(f"periodic accepted audio: {len(thin)} minute(s) below "
                           f"{args.min_minute_audio_s:.0f}s, {len(silent)} with no new span")
            else:
                green.append(f"every full wall-clock minute carried >= "
                             f"{args.min_minute_audio_s:.0f}s of accepted audio and a new "
                             f"committed span ({len(keys) - 1} full minutes)")
        else:
            undecided.append("periodic-accepted-audio clause undecided: snapshot layout")

        # (b) the same view authority, after the retired 900 s expiry
        print(f"\n   view-authority checks (the clause boundary is {clause_age:.0f}s):")
        print(f"   {'tag':>12} {'t+s':>8} {'age_s':>8} {'snap':>5} {'events':>7} {'portal':>7}")
        late_ok, post_stop = [], []
        for tag, t, age, snap_code, ev_code, portal_code in view_rows:
            when = float(t)
            print(f"   {tag:>12} {when - t0:>8.1f} {float(age):>8.1f} {snap_code:>5} "
                  f"{ev_code:>7} {portal_code:>7}")
            if t_stop and when > t_stop:
                post_stop.append((tag, when, snap_code, ev_code))
            elif float(age) >= clause_age:
                late_ok.append((tag, float(age), snap_code, ev_code))
        good_late = [c for c in late_ok if c[2] == "200" and c[3] == "200"]
        if good_late:
            tag, age, _, _ = good_late[-1]
            green.append(f"the same view authority answered 200/200 at age {age:.1f}s "
                         f"(> {clause_age:.0f}s), check '{tag}'")
        elif late_ok:
            tag, age, sc, ec = late_ok[-1]
            # UNPROVEN IS NOT DISPROVEN, and F3 is why this distinction is in the reducer. Its
            # post-900s check answered 401 - but the client had already reported sessionDisowned
            # 148 s earlier, so the check measured a DEAD SESSION, not an expired authority. The
            # session's death is red on its own (section 8 raises it); calling the authority red
            # as well would record a refutation the evidence does not contain.
            if first_refusal and first_refusal[0] <= age:
                undecided.append(
                    f"view authority at age {age:.1f}s answered snapshot={sc} events={ec}, but "
                    f"the session was already refused ({first_refusal[1]}) at "
                    f"t+{first_refusal[0]:.1f}s - the 'works after minute 15' clause is UNPROVEN "
                    f"on this run, not disproven")
            else:
                red.append(f"view authority refused past {clause_age:.0f}s with the session "
                           f"still alive: check '{tag}' at age {age:.1f}s answered "
                           f"snapshot={sc} events={ec}")
        else:
            undecided.append(f"no view check ran at age >= {clause_age:.0f}s before the stop - "
                             f"the 'works after minute 15' clause is UNPROVEN, not disproven")

        # (c) a clean stop revokes it immediately
        if post_stop:
            tag, when, sc, ec = post_stop[-1]
            latency = when - t_stop
            revoked = sc != "200" and ec != "200"
            print(f"\n   revoke: check '{tag}' ran {latency:.1f}s after the clean stop and "
                  f"answered snapshot={sc} events={ec}")
            (green if revoked else red).append(
                f"clean stop {'revoked' if revoked else 'DID NOT revoke'} the view authority "
                f"within {latency:.1f}s (snapshot={sc} events={ec})")
        elif t_stop:
            undecided.append("no view check after the clean stop - the revoke clause is unproven")
        else:
            undecided.append("no T_STOP in times.env - the revoke clause is unproven")

    # -------------------------------------------- 10. the F2 interruption clause
    # "a 5-second network interruption ... zero accepted-audio loss".
    #
    # THE CLAUSE IS NOT ASSERTED UNLESS THE RUN CARRIES A REPORT. A canary or soak directory has
    # no interruption in it, and printing "no interruption found - RED" over those would be the
    # same defect candidate 57 fixed: a verdict word naming something it does not decide. So the
    # section is silent without --interrupt-report, and UNDECIDED - never silent - when the flag
    # is given and the report cannot be read.
    #
    # THE POSITIVE CONTROL IS THE POINT OF THIS SECTION. A run where the network never actually
    # went down would pass every other clause in this file trivially, and would look exactly like
    # a run that survived an outage. So the interruption must be OBSERVED from the client side -
    # at least one view poll refused inside the window - before survival is credited to anything.
    if args.interrupt_report is not None:
        print("\n-- 10. the 5 s network interruption (F2) --")
        rep = interrupt
        t_stop_i = float(times.get("T_STOP") or 0)
        if not rep:
            undecided.append(f"interrupt report {args.interrupt_report} absent or unreadable - "
                             f"the 5 s network-interruption clause is UNPROVEN, not failed")
            print("   ABSENT or unreadable")
        else:
            nominal = float(rep.get("nominal_duration_s") or 0)
            measured = rep.get("measured_duration_s")
            w0, w1 = int_w0, int_w1
            still = rep.get("rule_still_present")
            print(f"   server window: nominal {nominal:.0f}s, measured "
                  f"{measured if measured is None else f'{float(measured):.3f}'}s on "
                  f"CLOCK_MONOTONIC (wall {float(rep.get('wall_duration_s') or 0):.3f}s), "
                  f"deletes={rep.get('deletes')} rule_still_present={still}")
            print(f"   chain after: {rep.get('chain_after')}")
            if still == "yes":
                red.append("the interruption rule was STILL PRESENT after the window - the live "
                           "port is blocked and the server needs the recorded rollback")
            if measured is None:
                undecided.append("interrupt report carries no measured duration - the clause is "
                                 "UNPROVEN")
            elif float(measured) + 1.0 < nominal:
                undecided.append(
                    f"the network was down {float(measured):.2f}s, short of the {nominal:.0f}s "
                    f"the clause names - the run measured a WEAKER interruption than the PRD "
                    f"asks for, so it is UNPROVEN rather than passed")
            # Correlate against the client's own polls. The two hosts' wall clocks are
            # independent and the SERVER's steps ~1.5 s backwards every ~32 s (candidate 56), so
            # the correlation window is deliberately loose: this is asking "did this client see
            # an outage around then", not "when exactly".
            skew = INT_SKEW
            if not (w0 and t0 and w0 > t0 and (not t_stop_i or w0 < t_stop_i)):
                undecided.append(
                    f"the interruption window (wall {w0:.0f}) does not fall inside the meeting "
                    f"({t0:.0f}..{t_stop_i:.0f}) - it was armed for the wrong moment and the "
                    f"clause is UNPROVEN")
            elif not snap_ok:
                undecided.append("interruption clause undecided: snapshot layout")
            else:
                inside = [(float(t) - t0, c) for t, c, _ in snap_rows
                          if w0 - skew <= float(t) <= w1 + skew]
                after = [(float(t) - t0, c) for t, c, _ in snap_rows if float(t) > w1 + skew]
                refused = [x for x in inside if x[1] != "200"]
                resumed = [x for x in after if x[1] == "200"]
                print(f"   client view polls in the window +/-{skew:.0f}s: {len(inside)} "
                      f"({len(refused)} refused), after: {len(after)} ({len(resumed)} back to 200)")
                if not inside:
                    undecided.append("no client view poll fell inside the interruption window - "
                                     "the clause is UNPROVEN on this run")
                elif not refused:
                    undecided.append(
                        f"the server dropped inbound tcp for {float(measured or 0):.2f}s but all "
                        f"{len(inside)} client polls in that window answered 200 - THE CLIENT "
                        f"NEVER SAW THE OUTAGE, so surviving it proves nothing. UNPROVEN.")
                elif not resumed:
                    red.append("the client never got a 200 back after the interruption - the "
                               "session did not survive the outage")
                else:
                    green.append(
                        f"a {float(measured):.2f}s network interruption was seen by the client "
                        f"({len(refused)} refused polls) and the session resumed "
                        f"(first 200 at t+{resumed[0][0]:.1f}s)")
            # The outbox is the mechanism the zero-loss clause rests on: accepted audio must be
            # RETAINED while the link is down and drained after. The authoritative loss test is
            # section 1's accepted==accounted==committed; this is the mechanism showing its work,
            # so never seeing retention is REPORTED and not red - a 1 Hz sampler can miss a
            # window this short.
            # The peak is measured INSIDE the window, not across the run. A canary's ordinary
            # start-up backlog would otherwise be credited to an outage it happened 40 s before,
            # which is a claim the evidence does not support.
            peak, peak_at, tail = 0, None, None
            run_peak = 0
            for t, body in read_tsv(os.path.join(d, "status.tsv"), 2):
                try:
                    s = json.loads(body)
                except Exception:
                    continue
                r = s.get("outboxRetainedFrames")
                if not isinstance(r, int):
                    continue
                tail = r
                run_peak = max(run_peak, r)
                if in_interrupt(t) and r > peak:
                    peak, peak_at = r, float(t) - t0
            print(f"   outbox retained: peak {peak} frames inside the window"
                  + (f" at t+{peak_at:.1f}s" if peak_at is not None else "")
                  + f"; run-wide peak {run_peak}; last sample {tail}")
            if tail:
                red.append(f"the outbox still held {tail} frames at the last status sample - "
                           f"accepted audio that never reached the server")
            elif peak:
                green.append(f"the outbox retained {peak} frames across the interruption and "
                             f"drained back to 0")
            else:
                print("   retention never observed above 0 inside the window - reported, not a "
                      "clause failure: at 1 Hz a 5 s outage can pass between samples. Zero loss "
                      "is decided by section 1's accounting, not here.")

    # ------------------------------------------------------------- the verdict
    print("\n-- verdict --")
    for g in green:
        print(f"   GREEN  {g}")
    for r in red:
        print(f"   RED    {r}")
    for u in undecided:
        print(f"   UNDECIDED  {u}")
    rc = 3 if red else (2 if undecided else 0)
    print(f"   rc={rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
