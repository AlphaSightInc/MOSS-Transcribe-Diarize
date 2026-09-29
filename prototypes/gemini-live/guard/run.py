"""P4 PROTOTYPE (throwaway): why live speaker identity collapses, and the smallest guard.

Run from worktree root ($0 — cached Gemini responses only; any uncached window raises):
  PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python \
    prototypes/gemini-live/guard/run.py diagnose A5bill      # window-by-window identity trace
  ... run.py sweep                                           # guard parameter sweep over all cases
Receipts: ~/Documents/Codex/2026-09-28/moss-gemini/evidence/P65/guard/.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "continuity"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

import measure  # noqa: E402
import c4  # noqa: E402
import c4_stop  # noqa: E402
import registry as reg  # noqa: E402
from common.corpus import clips  # noqa: E402

EVID_ROOT = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence")
OUT = EVID_ROOT / "P65" / "guard"
OUT.mkdir(parents=True, exist_ok=True)


def no_api(*_args, **_kwargs):
    raise RuntimeError("P4 is $0: window not cached")


c4_stop.call = no_api

# case key -> (tier, clip substring, S, L, evidence dir, role)
CASES = {
    "A5bill": ("long30m", "lex_bill_ackman", 15, 120, "P65/schedule", "collapsed"),
    "A3bill": ("long30m", "lex_bill_ackman", 30, 90, "P65/schedule", "collapsed"),
    "A3long60": ("long60", "long60", 30, 90, "P65/schedule", "collapsed"),
    "S20L60bill": ("long30m", "lex_bill_ackman", 20, 60, "P61", "collapsed"),
    "S20L120bill": ("long30m", "lex_bill_ackman", 20, 120, "P61", "collapsed"),
    "S20L120long60": ("long60", "long60", 20, 120, "P61", "collapsed"),
    "A0bill": ("long30m", "lex_bill_ackman", 15, 180, "P61", "passing"),
    "A0long60": ("long60", "long60", 15, 180, "P61", "passing"),
    "A0e1": ("e1", "e1", 15, 180, "P61", "passing"),
    "A2bill": ("long30m", "lex_bill_ackman", 15, 90, "P65/schedule", "passing"),
    "A2long60": ("long60", "long60", 15, 90, "P65/schedule", "passing"),
    "A2e1": ("e1", "e1", 15, 90, "P65/schedule", "passing"),
    "A6bill": ("long30m", "lex_bill_ackman", 15, 60, "P65/schedule", "candidate60"),
    "A6long60": ("long60", "long60", 15, 60, "P65/schedule", "candidate60"),
    "A6e1": ("e1", "e1", 15, 60, "P65/schedule", "candidate60"),
}
for s, l, ev in ((15, 180, "P61"), (15, 90, "P65/schedule")):
    for c in clips("accept6"):
        CASES[f"{'A0' if l == 180 else 'A2'}acc:{c.clip_id}"] = ("accept6", c.clip_id, s, l, ev, "passing")
for c in clips("accept6"):  # P5: can fingerprints carry identity at a 60 s window?
    CASES[f"A6acc:{c.clip_id}"] = ("accept6", c.clip_id, 15, 60, "P65/schedule", "candidate60")


def set_evidence(rel):
    path = EVID_ROOT / rel
    measure.EVIDENCE = c4.EVIDENCE = c4_stop.EVIDENCE = path


_LOADED = {}


def load(key):
    if key in _LOADED:
        return _LOADED[key]
    tier, sub, step, length, ev, _ = CASES[key]
    set_evidence(ev)
    clip = next(c for c in clips(tier) if sub in c.clip_id)
    pcm = c4.clip_pcm(clip, False)
    periodic = c4_stop.periodic_observations(clip, pcm, step, length, False)
    c4_stop.periodic_vectors(clip, periodic, step, length, False, pcm)
    stop = c4_stop.stop_observation(clip, pcm, step, length, 0, False, periodic[-1]["end"] if periodic else 0.0)
    reference = [] if clip.tier == "e1" else clip.reference_segments()
    excluded = [r for r in reference if (r["speaker"] == "<EXCLUDE>" or not r["text"].strip())]
    masks = [(r["start"], r["end"]) for r in excluded]
    reference = [r for r in reference if r not in excluded]
    _LOADED[key] = (clip, periodic + [stop], reference, masks)
    return _LOADED[key]


class GuardRegistry(reg.SpeakerRegistry):
    """Production-equivalent C1+C3+birth registry plus an optional fingerprint veto.

    Veto (T, M): after the overlap-first assignment, a label whose embedding is closer to
    another existing ID's centroid than to its assigned ID's centroid by >= M, with that
    cosine >= T, is re-assigned by solving the assignment on acoustic weights for the
    contested labels only. Everything else is unchanged.
    """

    veto_t = None
    veto_m = None
    veto_unknown_zero = False  # v2: an assigned ID with no centroid yet counts as cosine 0
    trace = None

    def observe_window(self, window_start_s, words, embeddings=None):
        field = reg.field
        labels = sorted({str(field(w, "speaker")) for w in words})
        groups = self._groups(words, labels, embeddings)
        group_by_label = {label: min(group) for group in groups for label in group}
        representatives = sorted({min(group) for group in groups})
        group_embeddings = {}
        if embeddings:
            for group in groups:
                vectors = [embeddings[label] for label in group if label in embeddings]
                if vectors:
                    group_embeddings[min(group)] = [sum(v[i] for v in vectors) / len(vectors)
                                                    for i in range(len(vectors[0]))]
        previous_ids = sorted({row[2] for row in self.previous if row[2] != "S00"})
        available_ids = sorted(set(previous_ids) | set(self.centroids))
        support = {(label, mid): 0.0 for label in representatives for mid in available_ids}
        for w in words:
            label = group_by_label[str(field(w, "speaker"))]
            start = window_start_s + float(field(w, "start"))
            end = window_start_s + float(field(w, "end"))
            candidates = [(min(end, pe) - max(start, ps), mid) for ps, pe, mid in self.previous]
            if candidates:
                duration, mid = max(candidates)
                if duration > 0 and mid != "S00":
                    support[(label, mid)] += duration
        acoustic = {(label, mid): (reg.cosine(group_embeddings[label], self.centroids[mid])
                                   if label in group_embeddings and mid in self.centroids else None)
                    for label in representatives for mid in available_ids}
        weights = []
        for label in representatives:
            row = []
            for mid in available_ids:
                overlap = support[(label, mid)]
                cos = acoustic[(label, mid)]
                if overlap >= self.min_overlap_s:
                    row.append(overlap)
                elif self.embedding_threshold is not None and cos is not None and cos >= self.embedding_threshold:
                    row.append(cos)
                else:
                    row.append(0.0)
            weights.append(row)
        chosen = list(reg.assignment(weights))
        vetoed = []
        if self.veto_t is not None and available_ids:
            contested = []
            for i, label in enumerate(representatives):
                col = chosen[i]
                if col is None or label not in group_embeddings:
                    continue
                assigned = acoustic[(label, available_ids[col])]
                if assigned is None and self.veto_unknown_zero:
                    assigned = 0.0
                best_mid, best = max(((mid, acoustic[(label, mid)]) for mid in available_ids
                                      if acoustic[(label, mid)] is not None),
                                     key=lambda x: x[1], default=(None, None))
                if (assigned is not None and best is not None and best_mid != available_ids[col]
                        and best >= self.veto_t and best - assigned >= self.veto_m):
                    contested.append(i)
            if contested:
                # Overlap evidence contradicts strong fingerprints: re-solve the whole window with
                # fingerprints first (cos >= T) for labels that have one; others keep their weights.
                weights2 = []
                for i, label in enumerate(representatives):
                    if label in group_embeddings:
                        weights2.append([(acoustic[(label, mid)] or 0.0)
                                         if (acoustic[(label, mid)] or 0.0) >= self.veto_t else 0.0
                                         for mid in available_ids])
                    else:
                        weights2.append(weights[i])
                before = list(chosen)
                chosen = list(reg.assignment(weights2))
                vetoed = [(representatives[i], None if b is None else available_ids[b],
                           None if a is None else available_ids[a])
                          for i, (b, a) in enumerate(zip(before, chosen)) if a != b]
        mapped_groups = {}
        for label, col in zip(representatives, chosen):
            if col is None:
                speech_s = sum(max(0.0, float(field(w, "end")) - float(field(w, "start")))
                               for w in words if group_by_label[str(field(w, "speaker"))] == label)
                if speech_s < self.birth_min_s:
                    closest = max(((support[(label, mid)], mid) for mid in available_ids), default=(0.0, None))
                    mapped_groups[label] = closest[1] if closest[0] > 0 else "S00"
                else:
                    mapped_groups[label] = f"M{self.next_id}"
                    self.next_id += 1
                    self.births += 1
            else:
                mapped_groups[label] = available_ids[col]
        mapped = {label: mapped_groups[group_by_label[label]] for label in labels}
        if self.trace is not None:
            self.trace.append({
                "start": window_start_s, "labels": representatives,
                "groups": {label: sorted(g) for g in groups for label in [min(g)]},
                "support": {f"{l}->{m}": round(v, 2) for (l, m), v in support.items() if v > 0},
                "acoustic": {f"{l}->{m}": round(v, 3) for (l, m), v in acoustic.items() if v is not None},
                "mapped": mapped_groups, "vetoed": vetoed})
        self.previous = [
            (window_start_s + float(field(w, "start")), window_start_s + float(field(w, "end")),
             mapped[str(field(w, "speaker"))])
            for w in words if mapped[str(field(w, "speaker"))] != "S00"]
        for label, vector in group_embeddings.items():
            mid = mapped_groups[label]
            if mid == "S00":
                continue
            old = self.centroids.get(mid)
            self.centroids[mid] = list(vector) if old is None else [0.8 * a + 0.2 * b for a, b in zip(old, vector)]
        return mapped, []


def replay(key, veto=(None, None), trace=False, unknown_zero=False):
    clip, obs, reference, masks = load(key)
    GuardRegistry.veto_t, GuardRegistry.veto_m = veto
    GuardRegistry.veto_unknown_zero = unknown_zero
    GuardRegistry.trace = [] if trace else None
    measure.SpeakerRegistry = GuardRegistry
    state = measure.evaluate([], obs, 0, .3, .46, .6, include_segments=True, stop_drain=True, birth_min_s=2)
    scored = c4.score_view(clip, reference, masks, state, "first")
    der = scored["metrics"]["der"] if scored else None
    return {"der": der, "ids": state["speaker_count"], "last_ids": state["last_speaker_count"],
            "S00_s": state["unattributed_s"], "state": state, "trace": GuardRegistry.trace,
            "clip": clip, "reference": reference}


def ref_speaker(reference, s, e):
    best, who = 0.0, None
    for r in reference:
        o = min(e, r["end"]) - max(s, r["start"])
        if o > best:
            best, who = o, r["speaker"]
    return who


def diagnose(key):
    out = replay(key, trace=True)
    clip, obs, reference, _ = load(key)
    print(f"{key}: DER {out['der']} IDs {out['ids']}/{out['last_ids']}")
    established = {}  # mid -> ref speaker (first 20 s of attributed speech)
    tally = defaultdict(Counter)
    lines = []
    first_bad = None
    for n, (o, t) in enumerate(zip(obs, out["trace"])):
        per_label = defaultdict(Counter)
        for w in o["words"]:
            who = ref_speaker(reference, o["start"] + w["start"], o["start"] + w["end"])
            per_label[w["speaker"]][who] += w["end"] - w["start"]
        rows = []
        for label in t["labels"]:
            group = t["groups"].get(label, [label])
            mix = Counter()
            for g in group:
                mix.update(per_label[g])
            dom, secs = (mix.most_common(1)[0] if mix else (None, 0))
            purity = secs / max(1e-9, sum(mix.values()))
            mid = t["mapped"][label]
            bad = None
            if mid not in ("S00",) and dom is not None and purity >= .7:
                if mid in established and established[mid] != dom:
                    bad = f"{mid} was {established[mid]}"
                owners = [m for m, r in established.items() if r == dom and m != mid]
                if mid not in established and owners:
                    bad = f"new {mid} for {dom} (owned by {owners})"
            if mid != "S00" and dom is not None and purity >= .7:
                tally[mid][dom] += secs
                if mid not in established and tally[mid][dom] >= 20:
                    established[mid] = dom
            rows.append(f"{label}({'+'.join(group)})={mid} ref={dom}:{purity:.2f}/{sum(mix.values()):.0f}s"
                        + (f" !!{bad}" if bad else ""))
            if bad and first_bad is None:
                first_bad = n
        lines.append(f"w{n+1:3d} [{o['start']:7.1f},{o['end']:7.1f}] " + " | ".join(rows)
                     + f"  sup={t['support']} cos={t['acoustic']}" + (f" veto={t['vetoed']}" if t["vetoed"] else ""))
    lo = max(0, (first_bad or 0) - 3)
    for line in lines[lo:(first_bad or 0) + 6]:
        print(line[:900])
    print("first bad window:", None if first_bad is None else first_bad + 1, "established:", established)
    (OUT / f"diagnose-{key}.txt").write_text("\n".join(lines))
    return first_bad


def sweep(grid, unknown_zero=False, name="sweep", role_filter=None):
    rows = []
    for key, (tier, *_rest) in CASES.items():
        role = CASES[key][5]
        if (role_filter is None and role == "candidate60") or (role_filter and role != role_filter):
            continue
        base = replay(key)
        entry = {"case": key, "role": role, "tier": tier, "base": {k: base[k] for k in ("der", "ids", "last_ids")}}
        for t, m in grid:
            r = replay(key, veto=(t, m), unknown_zero=unknown_zero)
            entry[f"T{t}M{m}"] = {k: r[k] for k in ("der", "ids", "last_ids")}
        rows.append(entry)
        print(json.dumps(entry), flush=True)
    (OUT / f"{name}.json").write_text(json.dumps(rows, indent=1))
    return rows


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "diagnose":
        for key in sys.argv[2:]:
            diagnose(key)
    elif cmd == "sweep":
        grid = [(t, m) for t in (.46, .60) for m in (.05, .20)]
        sweep(grid)
    elif cmd == "final":  # chosen guard: T .46 (existing C3 threshold), M .20
        sweep([(.46, .20)], name="final")
    elif cmd == "final60":  # P5: same guard on the S15/L60 candidate
        sweep([(.46, .20)], name="final60", role_filter="candidate60")
    elif cmd == "sweep2":  # v2 veto: unknown centroid = 0
        grid = [(t, m) for t in (.46, .60) for m in (.05, .20)]
        sweep(grid, unknown_zero=True, name="sweep2")
