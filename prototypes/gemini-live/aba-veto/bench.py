"""PROTOTYPE — A–B–A veto bench: rule A (shipped) vs B (>= 2 alternations) vs C (split disagreeing turns, then A).

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
            text = " ".join(r.get("text", "") for r in ref)
            if text.strip():
                with wave.open(str(c.audio), "rb") as w:
                    self.library.append((c, w.getnframes() / S, grams(text)))
        self.long60_ref = [json.loads(l) for l in (P69 / "fixture/reference.jsonl").read_text().splitlines() if l.strip()]
        self.long60_ref = [{**r, "speaker": r["speaker"]} for r in self.long60_ref if r["part"] == "long60"]

    def of_clip(self, c):
        ref = c.reference_segments()
        truth = c.true_speakers or (len({r["speaker"] for r in ref}) if ref else None)
        with wave.open(str(c.audio), "rb") as w:
            return {"fixture": c.clip_id, "audio": c.audio, "audio_s": w.getnframes() / S,
                    "reference": ref or None, "truth": truth, "score_until": None}

    def resolve(self, path: Path, duration, rows):
        end = max(r["end"] for r in rows)
        dur = duration or end
        summary = path.parent / "session-summary.json"
        if summary.is_file():
            ids = json.loads(summary.read_text()).get("source_ids") or []
            if len(ids) == 1 and ids[0] in self.clips:
                return self.of_clip(self.clips[ids[0]])
            if ids != ["long60"]:
                return {"fixture": "+".join(ids) or "unknown", "audio": None, "audio_s": dur, "reference": None,
                        "truth": None, "score_until": None}
        if abs(dur - 3930.9) < 3:
            return {"fixture": "p69-65min", "audio": P69 / "fixture/system.wav", "audio_s": 3930.9,
                    "reference": self.long60_ref, "truth": 8, "score_until": 2586.0}
        if abs(dur - 2586) < 3:
            return {"fixture": "long60", "audio": P69 / "fixture/long60.wav", "audio_s": 2586.0,
                    "reference": self.long60_ref, "truth": 5, "score_until": None}
        if abs(dur - 302) < 1 and E1_WAV.is_file():
            return {"fixture": "e1-system", "audio": E1_WAV, "audio_s": 302.0, "reference": None, "truth": 3,
                    "score_until": None}
        hyp = grams(" ".join(r["text"] for r in rows))
        best = max(((len(hyp & g) / max(1, len(hyp)), c) for c, d, g in self.library if abs(d - dur) <= 3),
                   default=(0, None), key=lambda x: x[0])
        if best[1] is not None and best[0] >= .3:
            return self.of_clip(best[1])
        return {"fixture": "unknown", "audio": None, "audio_s": dur, "reference": None, "truth": None,
                "score_until": None}


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
    chunks = []
    for k, (lo, stop, core_end) in enumerate(schedule(total_s)):
        words = []
        for i, r in enumerate(rows):
            a, b = max(r["start"], lo), min(r["end"], stop)
            if b - a <= 0:
                continue
            label = relabel.get((k, i), r["speaker"]) if relabel else r["speaker"]
            words.append(GeminiWord(r.get("text", ""), label, round(a * S), round(b * S)))
        chunks.append(TerminalChunk(k, round(lo * S), round(stop * S), round(core_end * S), tuple(words)))
    return chunks


def triple_counts(words) -> dict:
    """A–B–A alternations per label pair: speaker_turns (1.5 s) then gaps <= 2 s — the shipped veto's evidence."""
    turns = speaker_turns(tuple(GeminiSegment(w.start_sample, w.end_sample, w.text, w.speaker) for w in words))
    ordered = sorted(turns, key=lambda row: (row.start_sample, row.end_sample))
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for a, b, c in zip(ordered, ordered[1:], ordered[2:]):
        if (a.speaker == c.speaker and a.speaker != b.speaker and b.start_sample - a.end_sample <= 2 * S
                and c.start_sample - b.end_sample <= 2 * S):
            counts[tuple(sorted((a.speaker, b.speaker)))] += 1
    return counts


def stitch_rule(stitcher, chunks, min_triples: int):
    """Copy of LongFinalStitcher.stitch; ONLY change: a pair is vetoed at >= min_triples alternations in a chunk."""
    words_by_chunk, nodes, core = [], set(), []
    excluded: set[tuple[str, str]] = set()
    for chunk in chunks:
        tagged = tuple(GeminiWord(w.text, f"c{chunk.index}:{w.speaker}", w.start_sample, w.end_sample)
                       for w in chunk.words)
        words_by_chunk.append(tagged)
        nodes.update(w.speaker for w in tagged)
        core.extend(w for w in tagged if chunk.start_sample <= (w.start_sample + w.end_sample) / 2 < chunk.core_end_sample)
        excluded.update(pair for pair, n in triple_counts(tagged).items() if n >= min_triples)
    centroids = {}
    with tempfile.NamedTemporaryFile(suffix=".wav") as file:
        for tagged in words_by_chunk:
            for node in sorted({w.speaker for w in tagged}):
                intervals = FinalWordPolicy._intervals(tagged, node)
                if intervals:
                    vectors = stitcher.encoder.embed_intervals(file.name, intervals)
                    if vectors:
                        centroids[node] = FinalWordPolicy._unit(vectors)
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


def remap_rule(policy, words, min_triples: int):
    """Copy of FinalWordPolicy.remap; ONLY change: a pair is vetoed at >= min_triples alternations."""
    labels = sorted({w.speaker for w in words})
    if len(labels) < 2:
        return tuple(words)
    centroids = {}
    with tempfile.NamedTemporaryFile(suffix=".wav") as file:
        for label in labels:
            intervals = policy._intervals(words, label)
            if intervals:
                vectors = policy.encoder.embed_intervals(file.name, intervals)
                if vectors:
                    centroids[label] = policy._unit(vectors)
    ordered = sorted(words, key=lambda w: (w.start_sample, w.end_sample))
    turns: list[tuple[str, int, int]] = []
    for word in ordered:
        if turns and turns[-1][0] == word.speaker and word.start_sample - turns[-1][2] <= int(1.5 * S):
            label, start, end = turns[-1]
            turns[-1] = label, start, max(end, word.end_sample)
        else:
            turns.append((word.speaker, word.start_sample, word.end_sample))
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for a, b, c in zip(turns, turns[1:], turns[2:]):
        if a[0] == c[0] and a[0] != b[0] and b[1] - a[2] <= 2 * S and c[1] - b[2] <= 2 * S:
            counts[tuple(sorted((a[0], b[0])))] += 1
    excluded = {pair for pair, n in counts.items() if n >= min_triples}
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

    def embed_intervals(self, _path, intervals):
        valid = [(round(a, 4), round(b, 4)) for a, b in intervals if b > a]
        missing = [iv for iv in dict.fromkeys(valid) if iv not in self.cache]
        if missing:
            vectors = self.real.embed_intervals(self.wav, missing)
            self.calls += len(missing)
            if len(vectors) != len(missing):
                vectors = [self.real.embed_intervals(self.wav, [iv])[0] for iv in missing]
            self.cache.update(zip(missing, vectors))
        if not valid:
            raise ValueError("Tier B embedding intervals are empty.")
        return [self.cache[iv] for iv in valid]


def run_rule(rule: str, rows, total_s: float, encoder, relabel=None):
    chunks = pseudo_chunks(rows, total_s, relabel)
    if len(chunks) == 1:
        policy, words = FinalWordPolicy(encoder), chunks[0].words
        if rule == "production":
            return policy.remap(words, b"")
        return remap_rule(policy, words, 2 if rule == "B" else 1)
    stitcher = LongFinalStitcher(encoder)
    if rule == "production":
        return stitcher.stitch(chunks, b"")
    return stitch_rule(stitcher, chunks, 2 if rule == "B" else 1)


def split_relabel(rows, total_s: float, encoder):
    """Rule C: (chunk, row) -> new label for turns >= 2 s whose voice scores < SPLIT_FLOOR against their label."""
    relabel, audit = {}, []
    for k, chunk in enumerate(pseudo_chunks(rows, total_s)):
        index = {}
        j = 0
        for i, r in enumerate(rows):
            lo, stop, _ = schedule(total_s)[k]
            if min(r["end"], stop) - max(r["start"], lo) > 0:
                index[j] = i
                j += 1
        centroids = {}
        for label in sorted({w.speaker for w in chunk.words}):
            intervals = FinalWordPolicy._intervals(chunk.words, label)
            if intervals:
                centroids[label] = FinalWordPolicy._unit(encoder.embed_intervals("", intervals))
        for j, w in enumerate(chunk.words):
            seconds = (w.end_sample - w.start_sample) / S
            if seconds < 2 or w.speaker not in centroids:
                continue
            a = w.start_sample / S
            vector = FinalWordPolicy._unit(encoder.embed_intervals("", [(a, min(w.end_sample / S, a + 10))]))
            cosine = _cosine(vector, centroids[w.speaker])
            audit.append({"chunk": k, "row": index[j], "start": round(a, 1), "seconds": round(seconds, 1),
                          "label": w.speaker, "own_cosine": round(cosine, 3)})
            if cosine < SPLIT_FLOOR:
                relabel[(k, index[j])] = f"{w.speaker}~{index[j]}"
    return relabel, audit


# ------------------------------------------------------------------ measurement
def overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def measure(words, fx, rows) -> dict:
    out_rows = [{"start": w.start_sample / S, "end": w.end_sample / S, "speaker": w.speaker, "text": ""} for w in words]
    result = {"groups": len({r["speaker"] for r in out_rows})}
    if fx["reference"]:
        until = fx["score_until"]
        hyp = [{**r, "end": min(r["end"], until)} for r in out_rows if r["start"] < until] if until else out_rows
        m = score(fx["reference"], hyp, with_text=False)
        result.update({"der": m["der"], "confusion": m["speaker_confusion"], "groups_scored_part": m["hyp_speakers"],
                       "ref_speakers_scored_part": m["ref_speakers"]})
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


def fidelity(rows, words, total_s) -> dict:
    """Does the rule-A replay keep the saved grouping? saved label -> replay groups, replay group -> saved labels."""
    saved_to, group_to = defaultdict(set), defaultdict(set)
    spans = [(r["start"], r["end"], r["speaker"]) for r in rows]
    for w in words:
        mid = (w.start_sample + w.end_sample) / 2 / S
        label = next((s for a, b, s in spans if a <= mid <= b), None)
        if label is not None:
            saved_to[label].add(w.speaker)
            group_to[w.speaker].add(label)
    return {"extra_merges": sum(1 for v in group_to.values() if len(v) > 1),
            "replay_splits": sum(1 for v in saved_to.values() if len(v) > 1)}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fixtures = Fixtures()
    real = _identity_encoder(LiveProviderBundleConfig.from_manifest(MANIFEST), interval_workers=3)
    encoders: dict[str, FixtureEncoder] = {}
    cases: dict[tuple, dict] = {}
    skipped = collections.Counter()
    for path in sorted(EVID.rglob("*.json")):
        text = str(path)
        if "/bench-aba/" in text or "/state" in text or "/file-work" in text:
            continue
        loaded = lane_rows(path)
        if loaded is None:
            continue
        kind, duration, lanes = loaded
        for lane, rows in lanes.items():
            fx = (fixtures.resolve(path, duration, rows) if lane == "system"
                  else {"fixture": "mic-lane", "audio": None, "audio_s": duration or max(r["end"] for r in rows),
                        "reference": None, "truth": None, "score_until": None})
            key = (fx["fixture"], lane, signature(rows))
            case = cases.setdefault(key, {"fixture": fx["fixture"], "lane": lane, "kind": kind, "rows": rows, "fx": fx,
                                          "paths": []})
            case["paths"].append(str(path.relative_to(EVID)))
    results = []
    for key, case in sorted(cases.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[1]["paths"][0])):
        rows, fx = case["rows"], case["fx"]
        total_s = fx["audio_s"]
        chunks = pseudo_chunks(rows, total_s)
        counts = {f"c{c.index}": {" / ".join(p): n for p, n in sorted(triple_counts(c.words).items())} for c in chunks}
        exactly_one = [f"c{c.index}: {' / '.join(p)}" for c in chunks for p, n in sorted(triple_counts(c.words).items()) if n == 1]
        row = {"fixture": case["fixture"], "lane": case["lane"], "kind": case["kind"], "audio_s": round(total_s, 1),
               "chunks": len(chunks), "site": "stitcher" if len(chunks) > 1 else "short-policy",
               "saved_labels": len({r["speaker"] for r in rows}), "truth": fx["truth"], "turns": len(rows),
               "runs": len(case["paths"]), "first_path": case["paths"][0], "paths": case["paths"],
               "alternations": counts, "pairs_with_exactly_one": exactly_one}
        if fx["audio"] is None:
            row["A_vs_B"] = "identical (no pair with exactly one alternation)" if not exactly_one else "UNDETERMINED (no audio)"
            results.append(row)
            continue
        encoder = encoders.setdefault(str(fx["audio"]), FixtureEncoder(real, fx["audio"]))
        production = run_rule("production", rows, total_s, encoder)
        a = run_rule("A", rows, total_s, encoder)
        assert [(w.speaker, w.start_sample) for w in production] == [(w.speaker, w.start_sample) for w in a], key
        row["A"] = {**measure(a, fx, rows), **fidelity(rows, a, total_s)}
        if exactly_one:
            row["B"] = measure(run_rule("B", rows, total_s, encoder), fx, rows)
            row["A_vs_B"] = "replayed"
        else:
            row["B"] = {k: v for k, v in row["A"].items() if k not in ("extra_merges", "replay_splits")}
            row["A_vs_B"] = "identical (no pair with exactly one alternation)"
        relabel, audit = split_relabel(rows, total_s, encoder)
        row["C"] = {**measure(run_rule("A", rows, total_s, encoder, relabel), fx, rows), "turns_split": len(relabel),
                    "turns_tested": len(audit),
                    "own_cosine_min": min((x["own_cosine"] for x in audit), default=None),
                    "split_turns": [x for x in audit if x["own_cosine"] < SPLIT_FLOOR][:12]}
        row["own_cosines"] = sorted(x["own_cosine"] for x in audit)
        results.append(row)
        print(json.dumps({k: row[k] for k in ("fixture", "lane", "site", "runs", "truth", "saved_labels",
                                              "pairs_with_exactly_one", "A", "B", "A_vs_B")} | {
            "C": {k: v for k, v in row["C"].items() if k != "split_turns"}}), flush=True)
    (OUT / "results.json").write_text(json.dumps({"schema": "aba-veto-bench.v1", "der_margin": DER_MARGIN,
                                                  "split_floor": SPLIT_FLOOR, "cases": results}, indent=1) + "\n")
    print(json.dumps({"cases": len(results), "with_audio": sum(1 for r in results if "A" in r),
                      "encoder_intervals": sum(e.calls for e in encoders.values())}))


if __name__ == "__main__":
    main()
