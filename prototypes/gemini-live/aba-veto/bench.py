"""PROTOTYPE — A–B–A veto bench: rule A (shipped) vs B (>= 2 alternations) vs C (split disagreeing turns, then A)
vs V (exploratory, added after the first run: an alternation counts only if its >= 2 s turns match their labels).

Zero provider calls. Replays the PRODUCTION LongFinalStitcher / FinalWordPolicy on every saved terminal/File
turn set under the evidence root (label = chunk x saved name). Contract and gates: NOTES.md beside this file.

  PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r4-n.venv/bin/python prototypes/gemini-live/aba-veto/bench.py
"""
from __future__ import annotations

import collections
import hashlib
import json
import math
import re
import sys
import tempfile
import wave
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "prototypes/gemini-live/common"))
from corpus import clips  # noqa: E402
from score import score  # noqa: E402
from moss_transcribe_diarize.app.gemini_final_policy import FinalWordPolicy  # noqa: E402
from moss_transcribe_diarize.app.gemini_live_runtime import GeminiSegment  # noqa: E402
from moss_transcribe_diarize.app.gemini_long_final import LongFinalStitcher, TAU, _cosine  # noqa: E402
from moss_transcribe_diarize.app.gemini_provider import GeminiWord, TerminalChunk, speaker_turns  # noqa: E402
from moss_transcribe_diarize.app.live_provider_bundle import LiveProviderBundleConfig, _identity_encoder  # noqa: E402

S = 16000
EVID = Path.home() / "Documents/Codex/2026-09-28/moss-gemini/evidence"
P69 = EVID / "P69/r4-long"
OUT = P69 / "bench-aba"
MANIFEST = Path.home() / ".local/share/moss-transcribe-diarize/live/live-provider-manifest.json"
E1_WAV = Path("/Users/gao/Documents/Codex/2026-09-23/moss-round6/evidence/dx-replay/fixture/system.wav")
SPLIT_FLOOR = .46  # rule C: existing "this voice is that speaker" floor (gemini_live_runtime)
DER_MARGIN = .005
NARRATION = [(6.0, 47.0), (1802.0, 1848.5), (2114.0, 2311.0), (2427.0, 2449.0)]
UNKNOWN = {None, "", "S00", "Speaker TBD"}
TOK = re.compile(r"[a-z0-9']+")


# ------------------------------------------------------------------ inventory
def lane_rows(path: Path):
    """-> (kind, duration_s | None, {lane: [row]}) for a saved terminal/File turn set, else None."""
    try:
        if path.stat().st_size > 8_000_000:
            return None
        d = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict):
        return None
    lanes: dict[str, list[dict]] = defaultdict(list)
    if isinstance(d.get("transcript"), dict) and isinstance(d["transcript"].get("segments"), list) and d.get("mode"):
        if d.get("status") != "completed" or not (d["mode"] == "file" or d.get("refinement_state") == "done"):
            return None
        for r in d["transcript"]["segments"]:
            label = r.get("speaker_entity_id") or r.get("speaker")
            if label in UNKNOWN or float(r["end"]) <= float(r["start"]):
                continue
            lanes[r.get("source_lane") or "system"].append(
                {"start": float(r["start"]), "end": float(r["end"]), "speaker": str(label), "text": r.get("text", "")})
        duration = ((d.get("audio") or {}).get("duration_ms") or 0) / 1000 or None
        kind = "file" if d["mode"] == "file" else "live-cleanup"
    else:
        snap = d.get("snapshot") if isinstance(d.get("snapshot"), dict) else d
        session = snap.get("session") if isinstance(snap, dict) else None
        if not isinstance(session, dict) or session.get("finalization_status") != "final":
            return None
        for r in session.get("effective_transcript") or []:
            if r.get("authority") != "terminal" or r.get("canonical_speaker") in UNKNOWN:
                continue
            if r["end_sample"] <= r["start_sample"]:
                continue
            lanes[r.get("source_lane") or "system"].append(
                {"start": r["start_sample"] / S, "end": r["end_sample"] / S, "speaker": str(r["canonical_speaker"]),
                 "text": r.get("text", "")})
        duration = (session.get("accepted_samples") or 0) / S or None
        kind = "live-cleanup"
    lanes = {k: sorted(v, key=lambda r: (r["start"], r["end"])) for k, v in lanes.items() if v}
    return (kind, duration, lanes) if lanes else None


def signature(rows) -> str:
    index: dict[str, int] = {}
    parts = [(round(r["start"], 1), round(r["end"], 1), index.setdefault(r["speaker"], len(index))) for r in rows]
    return hashlib.sha1(json.dumps(parts).encode()).hexdigest()[:12]


def grams(text: str) -> set:
    t = TOK.findall(text.lower())
    return {" ".join(t[i:i + 4]) for i in range(len(t) - 3)}


class Fixtures:
    def __init__(self):
        self.clips = {c.clip_id: c for c in clips()}
        self.library = []
        for c in self.clips.values():
            ref = c.reference_segments()
            if any(r.get("text", "").strip() for r in ref):
                with wave.open(str(c.audio), "rb") as w:
                    self.library.append((c, w.getnframes() / S, ref))
        self.long60_ref = [json.loads(l) for l in (P69 / "fixture/reference.jsonl").read_text().splitlines() if l.strip()]
        self.long60_ref = [r for r in self.long60_ref if r["part"] == "long60"]
        e1 = json.loads((EVID / "P68/r4-smoke/runs/recheck-e1/run/snapshot.json").read_text())["session"]
        self.e1_grams = grams(" ".join(r["text"] for r in e1["effective_transcript"] if r.get("source_lane") != "microphone"))
        (OUT / "fixtures").mkdir(parents=True, exist_ok=True)

    def of_clip(self, c, until=None):
        ref = c.reference_segments()
        with wave.open(str(c.audio), "rb") as w:
            audio_s = w.getnframes() / S
        if until is not None and until < audio_s - 3:
            ref = [{**r, "end": min(r["end"], until)} for r in ref if r["start"] < until]
            audio_s = until
        truth = c.true_speakers if until is None and c.true_speakers else (len({r["speaker"] for r in ref}) if ref else None)
        covered = sum(r["end"] - r["start"] for r in ref) / audio_s if ref else 0
        return {"fixture": c.clip_id + ("" if until is None or until >= audio_s else f"[0-{round(until)}s]"),
                "audio": c.audio, "audio_s": audio_s, "reference": ref or None, "truth": truth, "score_until": None,
                "reference_complete": covered >= .8}

    def overlap_mix(self, ids, db):
        """stress/scenarios.py 'overlap': a + (a_rms / b_rms) * gain * b, clipped."""
        import numpy as np
        import soundfile as sf
        target = OUT / "fixtures" / f"overlap_{'0db' if db == 0 else 'minus10db'}.wav"
        if not target.is_file():
            a, _ = sf.read(self.clips[ids[0]].audio, dtype="int16")
            b, _ = sf.read(self.clips[ids[1]].audio, dtype="int16")
            n = min(len(a), len(b))
            a_rms = math.sqrt(float(np.mean(a[:n].astype(np.float64) ** 2)))
            b_rms = math.sqrt(float(np.mean(b[:n].astype(np.float64) ** 2)))
            mix = np.clip(a[:n].astype(np.float64) + a_rms / b_rms * 10 ** (db / 20) * b[:n], -32768, 32767).astype(np.int16)
            sf.write(target, mix, S, subtype="PCM_16")
        return target

    def qmic(self, variant):
        """Rebuild the public 300 s mic fixture (micfixture/build.py, deterministic) outside the worktree."""
        import importlib.util
        home = OUT / "fixtures" / "micfixture"
        if not (home / "out" / "reference.json").is_file():
            spec = importlib.util.spec_from_file_location("micfixture_build", ROOT / "prototypes/gemini-live/micfixture/build.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            home.mkdir(parents=True, exist_ok=True)
            module.HERE = home
            module.main()
        reference = json.loads((home / "out" / "reference.json").read_text())
        return home / "out" / reference["variants"][variant]["microphone"]

    def resolve(self, path: Path, duration, rows, lane="system"):
        end = max(r["end"] for r in rows)
        dur = duration or end
        none = {"audio": None, "audio_s": dur, "reference": None, "truth": None, "score_until": None,
                "reference_complete": False}
        if lane != "system":
            if "/qmic/" in str(path):
                wav = self.qmic(path.parent.name)
                turns = json.loads((wav.parent / "reference.json").read_text())["local_turns"]
                return {**none, "fixture": f"qmic-mic:{path.parent.name}", "audio": wav, "audio_s": 300.0,
                        "reference": turns, "truth": 2, "reference_complete": True}
            return {**none, "fixture": "mic-lane"}
        summary = path.parent / "session-summary.json"
        if summary.is_file():
            meta = json.loads(summary.read_text())
            ids = meta.get("source_ids") or []
            if len(ids) == 1 and ids[0] in self.clips:
                return self.of_clip(self.clips[ids[0]], dur)
            if len(ids) == 2 and all(i in self.clips for i in ids):
                db = meta.get("input_ratio_db")
                voices = {r["speaker"] for i in ids for r in self.clips[i].reference_segments()}
                return {**none, "fixture": f"overlap({db} dB):" + "+".join(i.split(":")[1] for i in ids),
                        "audio": self.overlap_mix(ids, db), "audio_s": 300.0, "truth": len(voices)}
            if ids != ["long60"]:
                return {**none, "fixture": "+".join(ids) or "unknown"}
        if abs(dur - 3930.9) < 3:
            return {"fixture": "p69-65min", "audio": P69 / "fixture/system.wav", "audio_s": 3930.9,
                    "reference": self.long60_ref, "truth": 8, "score_until": 2586.0, "reference_complete": True}
        if abs(dur - 2586) < 3:
            return {"fixture": "long60", "audio": P69 / "fixture/long60.wav", "audio_s": 2586.0,
                    "reference": self.long60_ref, "truth": 5, "score_until": None, "reference_complete": True}
        hyp = grams(" ".join(r["text"] for r in rows))
        if 295 <= dur <= 310 and E1_WAV.is_file() and len(hyp & self.e1_grams) / max(1, len(hyp)) >= .3:
            return {**none, "fixture": "e1-system", "audio": E1_WAV, "audio_s": 302.0, "truth": 3}
        best = (0, None, None)
        for c, d, ref in self.library:
            if d < dur - 8:
                continue
            until = None if d <= dur + 3 else dur
            text = " ".join(r.get("text", "") for r in ref if until is None or r["start"] < until)
            share = len(hyp & grams(text)) / max(1, len(hyp))
            if share > best[0]:
                best = (share, c, until)
        if best[1] is not None and best[0] >= .3:
            return self.of_clip(best[1], best[2])
        return {**none, "fixture": "unknown"}


# ------------------------------------------------------------------ rules
def schedule(total_s: float):
    out, start = [], 0.0
    while start < total_s:
        stop = min(total_s, start + 900.0)
        out.append((start, stop, total_s if stop == total_s else stop - 30.0))
        if stop == total_s:
            break
        start = stop - 30.0
    return out


def pseudo_chunks(rows, total_s: float, relabel=None):
    """One pseudo-word per saved turn, clipped to each 900 s / 30 s chunk; label = saved name."""
    chunks = []
    for k, (lo, stop, core_end) in enumerate(schedule(total_s)):
        words = []
        for i, r in enumerate(rows):
            a, b = max(r["start"], lo), min(r["end"], stop)
            if b - a <= 0:
                continue
            label = relabel.get((k, i), r["speaker"]) if relabel else r["speaker"]
            words.append(GeminiWord(str(i), label, round(a * S), round(b * S)))
        chunks.append(TerminalChunk(k, round(lo * S), round(stop * S), round(core_end * S), tuple(words)))
    return chunks


def alternations(words):
    """A–B–A triples, exactly the shipped evidence (turns joined at <= 1.5 s, both gaps <= 2 s)."""
    turns = speaker_turns(tuple(GeminiSegment(w.start_sample, w.end_sample, w.text, w.speaker) for w in words))
    ordered = sorted(turns, key=lambda row: (row.start_sample, row.end_sample))
    return [(a, b, c) for a, b, c in zip(ordered, ordered[1:], ordered[2:])
            if a.speaker == c.speaker and a.speaker != b.speaker and b.start_sample - a.end_sample <= 2 * S
            and c.start_sample - b.end_sample <= 2 * S]


def own_cosine(turn, centroids, encoder):
    seconds = (turn.end_sample - turn.start_sample) / S
    if seconds < 2 or turn.speaker not in centroids:
        return None
    a = turn.start_sample / S
    vector = FinalWordPolicy._unit(encoder.embed_intervals("", [(a, min(turn.end_sample / S, a + 10))]))
    return _cosine(vector, centroids[turn.speaker])


def vetoes(words, rule: str, centroids, encoder) -> set:
    triples = alternations(words)
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for a, b, c in triples:
        if rule == "V":  # an alternation counts unless one of its >= 2 s turns disagrees with its own label
            scores = [own_cosine(t, centroids, encoder) for t in (a, b, c)]
            if any(x is not None and x < SPLIT_FLOOR for x in scores):
                continue
        counts[tuple(sorted((a.speaker, b.speaker)))] += 1
    return {pair for pair, n in counts.items() if n >= (2 if rule == "B" else 1)}


def node_centroids(encoder, tagged) -> dict:
    out = {}
    for node in sorted({w.speaker for w in tagged}):
        intervals = FinalWordPolicy._intervals(tagged, node)
        if intervals:
            vectors = encoder.embed_intervals("", intervals)
            if vectors:
                out[node] = FinalWordPolicy._unit(vectors)
    return out


def stitch_rule(stitcher, chunks, rule: str):
    """Copy of LongFinalStitcher.stitch (397f7357); ONLY the veto set differs by rule (A = shipped)."""
    words_by_chunk, nodes, core, centroids = [], set(), [], {}
    for chunk in chunks:
        tagged = tuple(GeminiWord(w.text, f"c{chunk.index}:{w.speaker}", w.start_sample, w.end_sample)
                       for w in chunk.words)
        words_by_chunk.append(tagged)
        nodes.update(w.speaker for w in tagged)
        core.extend(w for w in tagged if chunk.start_sample <= (w.start_sample + w.end_sample) / 2 < chunk.core_end_sample)
        centroids.update(node_centroids(stitcher.encoder, tagged))
    excluded = set()
    for tagged in words_by_chunk:
        excluded |= vetoes(tagged, rule, centroids, stitcher.encoder)
    groups = {node: {node} for node in nodes}
    member = {node: node for node in nodes}

    def compatible(a, b):
        return not any(tuple(sorted((l, r))) in excluded for l in groups[a] for r in groups[b])

    def union(a, b):
        groups[a].update(groups.pop(b))
        for node in groups[a]:
            member[node] = a

    for index in range(1, len(chunks)):
        prior, current = chunks[index - 1], chunks[index]
        left = [w for w in words_by_chunk[index - 1] if w.end_sample > current.start_sample and w.start_sample < prior.end_sample]
        right = [w for w in words_by_chunk[index] if w.end_sample > current.start_sample and w.start_sample < prior.end_sample]
        weights: dict[tuple[str, str], int] = defaultdict(int)
        for a in left:
            for b in right:
                shared = min(a.end_sample, b.end_sample) - max(a.start_sample, b.start_sample)
                if shared > 0:
                    weights[(a.speaker, b.speaker)] += shared
        used_left, used_right = set(), set()
        for (a, b), weight in sorted(weights.items(), key=lambda item: (-item[1], item[0])):
            if weight <= 0 or a in used_left or b in used_right:
                continue
            used_left.add(a)
            used_right.add(b)
            if a in centroids and b in centroids and _cosine(centroids[a], centroids[b]) < TAU:
                continue
            ga, gb = member[a], member[b]
            if ga != gb and compatible(ga, gb):
                union(ga, gb)
    eligible = sorted(centroids)
    pairs = [(_cosine(centroids[a], centroids[b]), a, b) for i, a in enumerate(eligible) for b in eligible[i + 1:]]
    for similarity, a, b in sorted(pairs, key=lambda item: (-item[0], item[1], item[2])):
        if similarity < TAU:
            break
        ga, gb = member[a], member[b]
        if ga != gb and compatible(ga, gb):
            union(ga, gb)
    stable, result = {}, []
    for word in core:
        root = member[word.speaker]
        stable.setdefault(root, f"terminal-{len(stable) + 1:04d}")
        result.append(GeminiWord(word.text, stable[root], word.start_sample, word.end_sample))
    return tuple(result)


def remap_rule(policy, words, rule: str):
    """Copy of FinalWordPolicy.remap (397f7357); ONLY the veto set differs by rule (A = shipped)."""
    labels = sorted({w.speaker for w in words})
    if len(labels) < 2:
        return tuple(words)
    centroids = node_centroids(policy.encoder, words)
    excluded = vetoes(words, rule, centroids, policy.encoder)
    groups = {label: {label} for label in labels}
    member = {label: label for label in labels}
    eligible = sorted(centroids)
    pairs = [(sum(x * y for x, y in zip(centroids[a], centroids[b])), a, b)
             for i, a in enumerate(eligible) for b in eligible[i + 1:]]
    for cosine, a, b in sorted(pairs, key=lambda x: (-x[0], x[1], x[2])):
        if cosine < .65:
            break
        ga, gb = member[a], member[b]
        if ga == gb or any(tuple(sorted((x, y))) in excluded for x in groups[ga] for y in groups[gb]):
            continue
        groups[ga].update(groups.pop(gb))
        for label in groups[ga]:
            member[label] = ga
    return tuple(GeminiWord(w.text, member[w.speaker], w.start_sample, w.end_sample) for w in words)


class FixtureEncoder:
    """The production encoder on the fixture's own samples; ignores the temp path; caches per interval."""

    def __init__(self, real, wav: Path):
        self.real, self.wav, self.cache, self.calls = real, str(wav), {}, 0

    def prefetch(self, intervals):
        missing = [iv for iv in dict.fromkeys((round(a, 4), round(b, 4)) for a, b in intervals if b > a)
                   if iv not in self.cache]
        for at in range(0, len(missing), 64):
            batch = missing[at:at + 64]
            vectors = self.real.embed_intervals(self.wav, batch)
            if len(vectors) != len(batch):
                vectors = [self.real.embed_intervals(self.wav, [iv])[0] for iv in batch]
            self.calls += len(batch)
            self.cache.update(zip(batch, vectors))

    def embed_intervals(self, _path, intervals):
        valid = [(round(a, 4), round(b, 4)) for a, b in intervals if b > a]
        if not valid:
            raise ValueError("Tier B embedding intervals are empty.")
        self.prefetch(valid)
        return [self.cache[iv] for iv in valid]


def run_rule(rule: str, rows, total_s: float, encoder, relabel=None):
    chunks = pseudo_chunks(rows, total_s, relabel)
    if len(chunks) == 1:
        policy, words = FinalWordPolicy(encoder), chunks[0].words
        return policy.remap(words, b"") if rule == "production" else remap_rule(policy, words, rule)
    stitcher = LongFinalStitcher(encoder)
    return stitcher.stitch(chunks, b"") if rule == "production" else stitch_rule(stitcher, chunks, rule)


def turn_audit(rows, total_s: float, encoder, fx):
    """Every saved turn >= 2 s against its own label's centroid, per chunk; truth-tagged when a reference exists."""
    audit = []
    ref = fx["reference"] if fx.get("reference_complete") else None

    def truth_of(spans):
        seconds = collections.Counter()
        for a, b in spans:
            for r in ref:
                seconds[r["speaker"]] += overlap(a, b, r["start"], r["end"])
        return seconds.most_common(1)[0][0] if seconds and max(seconds.values()) > 0 else None

    for chunk in pseudo_chunks(rows, total_s):
        centroids = node_centroids(encoder, chunk.words)
        encoder.prefetch([(w.start_sample / S, min(w.end_sample / S, w.start_sample / S + 10)) for w in chunk.words
                          if w.end_sample - w.start_sample >= 2 * S])
        label_truth = {}
        if ref:
            for label in centroids:
                label_truth[label] = truth_of([(w.start_sample / S, w.end_sample / S) for w in chunk.words if w.speaker == label])
        for w in chunk.words:
            cosine = own_cosine(w, centroids, encoder)
            if cosine is None:
                continue
            item = {"chunk": chunk.index, "row": int(w.text), "start": round(w.start_sample / S, 1),
                    "seconds": round((w.end_sample - w.start_sample) / S, 1), "label": w.speaker,
                    "own_cosine": round(cosine, 3)}
            if ref and (not fx["score_until"] or w.end_sample / S <= fx["score_until"]):
                mine = truth_of([(w.start_sample / S, w.end_sample / S)])
                item["mislabelled"] = None if mine is None or label_truth.get(w.speaker) is None else mine != label_truth[w.speaker]
            audit.append(item)
    return audit


# ------------------------------------------------------------------ measurement
def overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def measure(words, fx) -> dict:
    out_rows = [{"start": w.start_sample / S, "end": w.end_sample / S, "speaker": w.speaker, "text": ""} for w in words]
    result = {"groups": len({r["speaker"] for r in out_rows})}
    if fx["reference"]:
        until = fx["score_until"]
        hyp = [{**r, "end": min(r["end"], until)} for r in out_rows if r["start"] < until] if until else out_rows
        m = score(fx["reference"], hyp, with_text=False)
        result.update({"der": m["der"], "confusion": m["speaker_confusion"], "groups_scored_part": m["hyp_speakers"]})
    if fx["fixture"] == "p69-65min":
        host = [(r["start"], r["end"]) for r in fx["reference"] if r["speaker"] == "long60:Lex Fridman"]

        def tally(spans):
            seconds = collections.Counter()
            for r in out_rows:
                seconds[r["speaker"]] += sum(overlap(r["start"], r["end"], a, b) for a, b in spans)
            return seconds.most_common(1)[0][0]
        narr = [(max(a, lo), min(b, hi)) for a, b in host for lo, hi in NARRATION if overlap(a, b, lo, hi) > 0]
        conv = []
        for a, b in host:
            parts = [(a, b)]
            for lo, hi in NARRATION:
                parts = [q for x, y in parts for q in ((x, min(y, lo)), (max(x, hi), y)) if q[1] > q[0]]
            conv += parts
        result["host_one_group"] = tally(narr) == tally(conv)
    return result


def fidelity(rows, words) -> dict:
    """Does the rule-A replay keep the saved grouping? (pseudo-word text = saved row index)"""
    saved_to, group_to = defaultdict(set), defaultdict(set)
    for w in words:
        label = rows[int(w.text)]["speaker"]
        saved_to[label].add(w.speaker)
        group_to[w.speaker].add(label)
    return {"extra_merges": sorted(sorted(v) for v in group_to.values() if len(v) > 1),
            "replay_splits": sorted(k for k, v in saved_to.items() if len(v) > 1)}


def p53_raw_labels() -> list[dict]:
    """Exact A vs B on the RAW provider labels P53 recorded (centroids + alternation counts + truth), 27 clips."""
    base = EVID / "P53"
    vectors = json.loads((base / "final-policy-vectors.json").read_text())
    tune = json.loads((base / "final-policy-tune.json").read_text())
    test = json.loads((base / "final-policy-test.json").read_text())
    audit = json.loads((base / "final-policy-pair-audit.json").read_text())
    policies = {(p["tau"], p["gap_s"], p["constraint"], p["order"]): p for p in tune["policies"]}
    selected = {c["clip_id"]: c for c in policies[(0.65, 2.0, True, "single")]["cases"]}
    no_veto = {c["clip_id"]: c for c in policies[(0.65, 0.0, False, "single")]["cases"]}
    selected.update({c["clip_id"]: c for c in test["arms"]["selected"]["cases"]})
    relation = {(clip, tuple(sorted(p["labels"]))): p["truth_relation"]
                for part in ("tune", "test") for clip, pairs in audit[part].items() for p in pairs}

    def partition(clip, counts, need):
        cent = {l: v["centroid"] for l, v in vectors[clip].items()}
        labels = sorted(cent)
        excluded = {tuple(sorted(k.split("|"))) for k, n in counts.items() if n >= need}
        groups = {l: {l} for l in labels}
        member = {l: l for l in labels}
        pairs = [(sum(x * y for x, y in zip(cent[a], cent[b])), a, b) for i, a in enumerate(labels) for b in labels[i + 1:]]
        merged = []
        for cosine, a, b in sorted(pairs, key=lambda x: (-x[0], x[1], x[2])):
            if cosine < .65:
                break
            ga, gb = member[a], member[b]
            if ga == gb or any(tuple(sorted((x, y))) in excluded for x in groups[ga] for y in groups[gb]):
                continue
            groups[ga].update(groups.pop(gb))
            merged.append((a, b, round(cosine, 3)))
            for l in groups[ga]:
                member[l] = ga
        return sorted(sorted(g) for g in groups.values()), member, merged

    out = []
    for clip, case in selected.items():
        counts = case["motif_counts"]
        part_a, member_a, _ = partition(clip, counts, 1)
        part_b, _member_b, merged_b = partition(clip, counts, 2)
        part_n, _m, _x = partition(clip, counts, 10 ** 9)
        recorded = defaultdict(set)
        for label, root in case["mapping"].items():
            if label in member_a:
                recorded[root].add(label)
        new = [{"labels": [a, b], "cosine": cosine, "truth_relation": relation.get((clip, tuple(sorted((a, b)))), "unrecorded")}
               for a, b, cosine in merged_b if member_a[a] != member_a[b]]
        labels_out = lambda part: case["input_labels"] - sum(len(g) for g in part) + len(part)
        der_b = case["der"] if part_b == part_a else (no_veto[clip]["der"] if clip in no_veto and part_b == part_n else None)
        out.append({"clip": clip, "truth": case["truth_speakers"], "raw_labels": case["input_labels"],
                    "A_matches_recorded": part_a == sorted(sorted(g) for g in recorded.values()),
                    "pairs_with_exactly_one": sum(1 for n in counts.values() if n == 1),
                    "A": {"labels_out": labels_out(part_a), "der": case["der"]},
                    "B": {"labels_out": labels_out(part_b), "der": der_b,
                          "der_basis": "= A" if part_b == part_a else ("recorded no-veto arm (same grouping)" if der_b is not None else "UNMEASURED (no words on disk)")},
                    "B_new_merges": new})
    return out


def gates(cases, raw) -> dict:
    out = {}
    for rule in ("B", "C", "V"):
        scored = [c for c in cases if rule in c and "der" in c["A"] and "der" in c[rule]]
        worse = [{"fixture": c["fixture"], "first_path": c["first_path"], "A": c["A"]["der"], rule: c[rule]["der"]}
                 for c in scored if c[rule]["der"] - c["A"]["der"] > DER_MARGIN]
        counted = [c for c in cases if rule in c and c["truth"]]
        away = [{"fixture": c["fixture"], "first_path": c["first_path"], "truth": c["truth"], "A": c["A"]["groups"],
                 rule: c[rule]["groups"]} for c in counted
                if abs(c[rule]["groups"] - c["truth"]) > abs(c["A"]["groups"] - c["truth"])]
        long = [c for c in cases if c["fixture"] == "p69-65min" and rule in c]
        g3 = bool(long) and all(c[rule].get("host_one_group") and c[rule]["der"] <= .060 for c in long)
        entry = {"G1_no_harm": {"pass": not worse, "cases_scored": len(scored), "worse": worse},
                 "G2_count": {"pass": not away, "cases_with_truth": len(counted), "moved_away": away},
                 "G3_repair_65min": {"pass": g3, "values": [{"der": c[rule]["der"], "host_one_group": c[rule].get("host_one_group")} for c in long]}}
        if rule == "B":
            false_merges = [{"clip": r["clip"], **m} for r in raw for m in r["B_new_merges"] if m["truth_relation"] == "different"]
            raw_worse = [{"clip": r["clip"], "A": r["A"]["der"], "B": r["B"]["der"]} for r in raw
                         if r["B"]["der"] is not None and r["B"]["der"] - r["A"]["der"] > DER_MARGIN]
            entry["G1_no_harm"]["raw_label_worse"] = raw_worse
            entry["G2_count"]["raw_label_false_merges"] = false_merges
            entry["G1_no_harm"]["pass"] = entry["G1_no_harm"]["pass"] and not raw_worse
            entry["G2_count"]["pass"] = entry["G2_count"]["pass"] and not false_merges
        else:
            entry["raw_label_evidence"] = "UNMEASURED: P53 keeps centroids and counts, not turns; rule needs the raw words"
        entry["all_pass"] = all(entry[k]["pass"] for k in ("G1_no_harm", "G2_count", "G3_repair_65min"))
        out[rule] = entry
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fixtures = Fixtures()
    real = _identity_encoder(LiveProviderBundleConfig.from_manifest(MANIFEST), interval_workers=3)
    encoders: dict[str, FixtureEncoder] = {}
    cases: dict[tuple, dict] = {}
    for path in sorted(EVID.rglob("*.json")):
        text = str(path)
        if "/bench-aba/" in text or "/state" in text or "/file-work" in text:
            continue
        loaded = lane_rows(path)
        if loaded is None:
            continue
        kind, duration, lanes = loaded
        for lane, rows in lanes.items():
            fx = fixtures.resolve(path, duration, rows, lane)
            key = (fx["fixture"], lane, signature(rows))
            case = cases.setdefault(key, {"fixture": fx["fixture"], "lane": lane, "kind": kind, "rows": rows, "fx": fx,
                                          "paths": []})
            case["paths"].append(str(path.relative_to(EVID)))
    results = []
    for key, case in sorted(cases.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[1]["paths"][0])):
        rows, fx = case["rows"], case["fx"]
        total_s = fx["audio_s"]
        chunks = pseudo_chunks(rows, total_s)
        counts = {}
        for c in chunks:
            per = collections.Counter(tuple(sorted((a.speaker, b.speaker))) for a, b, _c in alternations(c.words))
            counts[f"c{c.index}"] = {" / ".join(p): n for p, n in sorted(per.items())}
        exactly_one = [f"{k}: {p}" for k, per in counts.items() for p, n in per.items() if n == 1]
        row = {"fixture": case["fixture"], "lane": case["lane"], "kind": case["kind"], "audio_s": round(total_s, 1),
               "chunks": len(chunks), "site": "stitcher" if len(chunks) > 1 else "short-policy",
               "saved_labels": len({r["speaker"] for r in rows}), "truth": fx["truth"], "turns": len(rows),
               "runs": len(case["paths"]), "first_path": case["paths"][0], "paths": case["paths"],
               "reference": ("complete" if fx.get("reference_complete") else "incomplete") if fx["reference"] else None,
               "alternations": counts, "pairs_with_exactly_one": exactly_one}
        if fx["audio"] is None:
            row["A_vs_B"] = "identical (no pair with exactly one alternation)" if not exactly_one else "UNDETERMINED (no audio)"
            results.append(row)
            continue
        encoder = encoders.setdefault(str(fx["audio"]), FixtureEncoder(real, fx["audio"]))
        production = run_rule("production", rows, total_s, encoder)
        a = run_rule("A", rows, total_s, encoder)
        assert [(w.speaker, w.start_sample) for w in production] == [(w.speaker, w.start_sample) for w in a], key
        row["A"] = {**measure(a, fx), **fidelity(rows, a)}
        if exactly_one:
            row["B"] = measure(run_rule("B", rows, total_s, encoder), fx)
            row["A_vs_B"] = "replayed"
        else:
            row["B"] = {k: v for k, v in row["A"].items() if k not in ("extra_merges", "replay_splits")}
            row["A_vs_B"] = "identical (no pair with exactly one alternation)"
        audit = turn_audit(rows, total_s, encoder, fx)
        relabel = {(x["chunk"], x["row"]): f"{x['label']}~{x['row']}" for x in audit if x["own_cosine"] < SPLIT_FLOOR}
        row["C"] = {**measure(run_rule("A", rows, total_s, encoder, relabel), fx), "turns_split": len(relabel),
                    "turns_tested": len(audit)}
        row["V"] = measure(run_rule("V", rows, total_s, encoder), fx)
        row["turn_audit"] = audit
        results.append(row)
        print(json.dumps({k: row[k] for k in ("fixture", "lane", "site", "runs", "truth", "saved_labels",
                                              "pairs_with_exactly_one", "A", "B", "C", "V", "A_vs_B")}), flush=True)
    raw = p53_raw_labels()
    summary = gates(results, raw)
    (OUT / "results.json").write_text(json.dumps({"schema": "aba-veto-bench.v2", "der_margin": DER_MARGIN,
                                                  "split_floor": SPLIT_FLOOR, "gates": summary,
                                                  "p53_raw_labels": raw, "cases": results}, indent=1) + "\n")
    print(json.dumps({"cases": len(results), "with_audio": sum(1 for r in results if "A" in r),
                      "undetermined": sum(1 for r in results if r["A_vs_B"].startswith("UNDETERMINED")),
                      "encoder_intervals": sum(e.calls for e in encoders.values()),
                      "gates": {k: {g: v[g]["pass"] for g in ("G1_no_harm", "G2_count", "G3_repair_65min")} for k, v in summary.items()}}))


if __name__ == "__main__":
    main()
