"""Zero-send C4 registry and public-snapshot parity against the product runtime.

Run from the prototype worktree root:
PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python \
  prototypes/gemini-live/continuity/parity.py

Both registries and the real product LiveSession consume retained S15/L180/H0
Gemini words and numeric WeSpeaker vectors. No provider or encoder is called.
"""
from __future__ import annotations

import json
import inspect
import hashlib
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

RUNTIME = Path("/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-gemini-runtime")
sys.path.insert(0, str(RUNTIME))
from moss_transcribe_diarize.app.gemini_continuity_registry import ContinuityRegistry  # noqa: E402
from moss_transcribe_diarize.app.gemini_provider import GeminiWord  # noqa: E402
from moss_transcribe_diarize.app.gemini_hybrid_engine import (  # noqa: E402
    GeminiHybridEngine, GrowingContextWindowScheduler, attributed_embedding_intervals)
from moss_transcribe_diarize.app.gemini_live_runtime import (  # noqa: E402
    GeminiLiveRuntime, ScriptedGeminiEngine)
from moss_transcribe_diarize.app.live_service_runtime import (  # noqa: E402
    LiveServiceBounds, LiveServiceConfigHashes, LiveServiceDescriptor)
from moss_transcribe_diarize.app.live_session import AudioFrame  # noqa: E402

from c4 import observation_path
from measure import EVIDENCE, embedding_intervals, note, segmentize
from registry import SpeakerRegistry

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common.corpus import clips  # noqa: E402

sys.path.insert(0, str(HERE.parent / "harness"))
from h1_offline import score_case  # noqa: E402
from measure import measured_score  # noqa: E402
from score_support import mask_words  # noqa: E402

SAMPLE_RATE = 16_000
STEP = 15
LENGTH = 180


def canonical(value):
    if value in (None, "S00"):
        return "S00"
    if value.startswith("speaker-"):
        return f"M{int(value.rsplit('-', 1)[1])}"
    return value


def paths(clip, mix):
    suffix = f"{clip.tier}-{clip.clip_id}-S{STEP}-L{LENGTH}{'-mix' if mix else ''}"
    safe = clip.clip_id.replace(":", "_")
    stop_suffix = f"{clip.tier}-{safe}-S{STEP}-L{LENGTH}-H0{'-mix' if mix else ''}"
    return (observation_path(clip, STEP, LENGTH, mix),
            EVIDENCE / f"vectors-span2s-{suffix}.json",
            EVIDENCE / f"c4-stop-observation-{stop_suffix}.json",
            EVIDENCE / f"c4-stop-vectors-{stop_suffix}.json",
            EVIDENCE / f"c4-stop-score-{clip.tier}-{safe}-S{STEP}-L{LENGTH}"
                       f"{'-mix' if mix else ''}.json")


def load(clip, mix):
    observation_file, vector_file, stop_file, stop_vector_file, score_file = paths(clip, mix)
    baseline = json.loads(score_file.read_text())
    periodic_count = baseline["periodic_windows"]
    periodic = [json.loads(line) for line in observation_file.read_text().splitlines()]
    # Early C4 receipts also contain a superseded full-context final call.
    periodic = periodic[:periodic_count]
    vector_rows = json.loads(vector_file.read_text())[:periodic_count]
    if len(periodic) != periodic_count or len(vector_rows) != periodic_count:
        raise ValueError(f"missing periodic receipt: {clip.clip_id} mix={mix}")
    for row, vector in zip(periodic, vector_rows):
        if (row["start"], row["end"]) != (vector["start"], vector["end"]):
            raise ValueError(f"vector schedule mismatch: {clip.clip_id}")
        row["embeddings"] = vector["embeddings"]
    stop = json.loads(stop_file.read_text())
    stop_vectors = json.loads(stop_vector_file.read_text())
    if (stop["start"], stop["end"]) != (stop_vectors["start"], stop_vectors["end"]):
        raise ValueError(f"Stop vector mismatch: {clip.clip_id}")
    stop["embeddings"] = stop_vectors["embeddings"]
    observations = periodic + [stop]
    if len(observations) != baseline["by_hold"]["H0"]["windows"]:
        raise ValueError(f"window count mismatch: {clip.clip_id}")
    return observations, baseline


def product_words(observation):
    start_sample = round(observation["start"] * SAMPLE_RATE)
    return tuple(GeminiWord(word["text"], word["speaker"],
                            start_sample + round(word["start"] * SAMPLE_RATE),
                            start_sample + round(word["end"] * SAMPLE_RATE))
                 for word in observation["words"])


def absolute_words(observation, mapping):
    start = observation["start"]
    return [{"start": start + word["start"], "end": start + word["end"],
             "speaker": canonical(mapping[word["speaker"]]), "text": word["text"]}
            for word in observation["words"]]


def product_embedding_interval(observation, label):
    """Use the product's selected spans without calling its encoder."""
    intervals = attributed_embedding_intervals(
        product_words(observation), round(observation["start"] * SAMPLE_RATE))
    return [(start / SAMPLE_RATE, end / SAMPLE_RATE)
            for start, end in intervals.get(label, [])]


def snapshot_segments(observations, baseline):
    """Publish cached words through the real product LiveSession; zero provider calls."""
    duration = round(baseline["duration_s"])
    descriptor = LiveServiceDescriptor(
        source_revision="P61-parity", provider_name="gemini", provider_revision="cached",
        provider_manifest_hash=hashlib.sha256(b"P61-parity").hexdigest(),
        config_hashes=LiveServiceConfigHashes.from_parts(
            endpoint_config={}, identity_config={}, decoder_config={}),
        bounds=LiveServiceBounds(max_frame_samples=SAMPLE_RATE, max_queue_depth=4,
                                 max_retained_samples=(duration + 1) * SAMPLE_RATE,
                                 max_identity_speakers=64, max_events=128,
                                 max_tape_bytes=(duration + 1) * SAMPLE_RATE * 2),
        frame_samples=SAMPLE_RATE)

    class Unused:
        def words(self, _pcm, *, deadline):
            raise AssertionError("parity must not call Gemini Live")

        def diarize(self, _pcm, *, deadline, kind, diarize=True):
            raise AssertionError("parity must not call Gemini batch")

        def transcribe(self, _tape):
            raise AssertionError("parity must not run final")

    with tempfile.TemporaryDirectory(prefix="moss-p61-parity-") as directory:
        runtime = GeminiLiveRuntime(
            descriptor=descriptor, tape_storage_root=Path(directory),
            engine_factory=lambda _id, publish, _usage: ScriptedGeminiEngine(
                publish, batches=[], terminal=()))
        runtime.create(session_id="parity")
        for sequence in range(duration):
            runtime.accept_frame("parity", AudioFrame(
                sequence=sequence, pcm=bytes(2 * SAMPLE_RATE), sample_count=SAMPLE_RATE))
        cached_vectors = {}
        engine = GeminiHybridEngine(
            lambda update: runtime.publish_update("parity", update),
            word_source=Unused(),
            window_scheduler=GrowingContextWindowScheduler(max_seconds=LENGTH,
                                                            stride_seconds=STEP),
            registry=ContinuityRegistry(embedding_threshold=.46,
                                        within_window_threshold=.6,
                                        birth_min_seconds=2),
            diarizer=Unused(), terminal=Unused(),
            embedding_source=lambda _pcm, _start, _words: cached_vectors)
        try:
            for observation in observations:
                cached_vectors = {label: (tuple(vector), 2.0)
                                  for label, vector in observation["embeddings"].items()}
                start = round(observation["start"] * SAMPLE_RATE)
                end = round(observation["end"] * SAMPLE_RATE)
                words = tuple(replace(word,
                                      start_sample=word.start_sample - start,
                                      end_sample=word.end_sample - start)
                              for word in product_words(observation))
                engine._publish_window(start, end, bytes((end - start) * 2), words)
            rows = runtime.snapshot("parity").to_dict()["session"]["effective_transcript"]
            return [{"start": row["start_sample"] / SAMPLE_RATE,
                     "end": row["end_sample"] / SAMPLE_RATE,
                     "speaker": canonical(row["canonical_speaker"]),
                     "text": row["text"]} for row in rows]
        finally:
            engine.close()


def score_words(clip, words):
    if clip.tier not in ("accept6", "e1"):
        words, _, _ = mask_words(words, [])
    return score_segments(clip, segmentize(words))


def score_segments(clip, segments):
    if clip.tier == "e1":
        return None
    if clip.tier == "accept6":
        rows = [word for word in segments if word["end"] > word["start"]]
        return score_case(clip.clip_id, immediate=rows, settled=rows, final=[])["metrics"]["settled"]["der"]
    return measured_score(clip.reference_segments(), segments)["der"]


def intervals_agree(left, right):
    return len(left) == len(right) and all(
        abs(a - c) <= 2 / SAMPLE_RATE and abs(b - d) <= 2 / SAMPLE_RATE
        for (a, b), (c, d) in zip(left, right))


def run_case(clip, mix=False):
    observations, baseline = load(clip, mix)
    prototype = SpeakerRegistry(min_overlap_s=.3, embedding_threshold=.46,
                                within_window_threshold=.6, birth_min_s=2)
    # Match phase2_web_cli.system_factory and the runtime's selected .3 s default.
    product = ContinuityRegistry(embedding_threshold=.46,
                                 within_window_threshold=.6, birth_min_seconds=2)
    scheduler = GrowingContextWindowScheduler(max_seconds=LENGTH, stride_seconds=STEP)
    first_prototype, first_product = [], []
    seen_prototype, seen_product = set(), set()
    window_rows = []
    first_difference = None
    first_ownership_difference = None
    first_positive_ownership_difference = None
    frontier = 0.0
    last_periodic_end = 0
    product_local_merges = 0
    embedding_interval_mismatches = 0
    embedding_eligibility_mismatches = 0
    first_embedding_interval_difference = None
    for index, observation in enumerate(observations, 1):
        start, end = observation["start"], observation["end"]
        is_stop = index == len(observations)
        if is_stop:
            expected_start = last_periodic_end / SAMPLE_RATE
            if (start, end) != (expected_start, baseline["duration_s"]):
                raise ValueError(f"short Stop schedule mismatch: {clip.clip_id}")
        else:
            scheduled = scheduler.next_window(round(end * SAMPLE_RATE), last_periodic_end)
            expected = (round(start * SAMPLE_RATE), round(end * SAMPLE_RATE),
                        round(end * SAMPLE_RATE))
            if scheduled != expected:
                raise ValueError(f"product periodic scheduler mismatch: {clip.clip_id} window {index}")
            last_periodic_end = round(end * SAMPLE_RATE)

        words = product_words(observation)
        vectors = observation["embeddings"]
        previous_prototype = list(prototype.previous)
        previous_product = list(product._previous)
        for label in sorted({word["speaker"] for word in observation["words"]}):
            prototype_intervals = embedding_intervals(start, observation["words"], label)
            runtime_intervals = product_embedding_interval(observation, label)
            if not intervals_agree(prototype_intervals, runtime_intervals):
                embedding_interval_mismatches += 1
                embedding_eligibility_mismatches += bool(prototype_intervals) != bool(runtime_intervals)
                if first_embedding_interval_difference is None:
                    first_embedding_interval_difference = {
                        "window": index, "start": start, "end": end, "label": label,
                        "prototype_intervals": prototype_intervals,
                        "product_intervals": runtime_intervals}
        pmap, _ = prototype.observe_window(start, observation["words"], vectors)
        # The duration is journal metadata; both registries see the identical vector.
        product_vectors = {label: (tuple(vector), 2.0)
                           for label, vector in vectors.items()}
        groups = product._groups(words, sorted({word.speaker for word in words}),
                                 {label: value[0] for label, value in product_vectors.items()})
        product_local_merges += len({word.speaker for word in words}) - len(groups)
        rmap, _ = product.observe_window(start, words, product_vectors,
                                         committed_through_sample=round(end * SAMPLE_RATE))
        rmap = {label: canonical(mid) for label, mid in rmap.items()}
        pmap = {label: canonical(mid) for label, mid in pmap.items()}
        labels = sorted(set(pmap) | set(rmap))
        agreement = all(pmap.get(label) == rmap.get(label) for label in labels)
        if not agreement and first_difference is None:
            different = [label for label in labels if pmap.get(label) != rmap.get(label)]
            overlap = {}
            for label in different:
                proto_words = [word for word in observation["words"]
                               if word["speaker"] == label]
                overlaps = {}
                for local_word in proto_words:
                    word_start = start + local_word["start"]
                    word_end = start + local_word["end"]
                    for old_start, old_end, mid in previous_prototype:
                        amount = min(word_end, old_end) - max(word_start, old_start)
                        if amount > 0:
                            overlaps[mid] = overlaps.get(mid, 0.0) + amount
                overlap[label] = {mid: round(value, 6) for mid, value in overlaps.items()}
            first_difference = {"window": index, "start": start, "end": end,
                                "prototype": pmap, "product": rmap,
                                "different_labels": different,
                                "prototype_overlap_support_s": overlap,
                                "prototype_previous": len(previous_prototype),
                                "product_previous": len(previous_product),
                                "prototype_centroids": sorted(prototype.centroids),
                                "product_centroids": sorted(map(canonical, product._centroids))}
        absolute_prototype = absolute_words(observation, pmap)
        absolute_product = absolute_words(observation, rmap)
        new_frontier = end
        fresh_prototype = [word for word in absolute_prototype
                           if frontier < word["end"] <= new_frontier]
        # The fixed product and C4 both own completed words by end frontier.
        fresh_product = [word for word in absolute_product
                         if frontier < word["end"] <= new_frontier]
        if first_ownership_difference is None and fresh_prototype != fresh_product:
            prototype_only = next((word for word in fresh_prototype
                                   if word not in fresh_product), None)
            product_only = next((word for word in fresh_product
                                 if word not in fresh_prototype), None)
            first_ownership_difference = {
                "window": index, "start": start, "end": end, "prior_frontier": frontier,
                "prototype_only_word": prototype_only,
                "product_only_word": product_only,
                "cause": "sample rounding or registry assignment differs under end-owned frontier"}
        positive_prototype = [word for word in fresh_prototype if word["end"] > word["start"]]
        positive_product = [word for word in fresh_product if word["end"] > word["start"]]
        if first_positive_ownership_difference is None and positive_prototype != positive_product:
            first_positive_ownership_difference = {
                "window": index, "start": start, "end": end, "prior_frontier": frontier,
                "prototype_only_word": next((word for word in positive_prototype
                                              if word not in positive_product), None),
                "product_only_word": next((word for word in positive_product
                                            if word not in positive_prototype), None)}
        first_prototype.extend(fresh_prototype)
        first_product.extend(fresh_product)
        seen_prototype.update(word["speaker"] for word in fresh_prototype if word["speaker"] != "S00")
        seen_product.update(word["speaker"] for word in fresh_product if word["speaker"] != "S00")
        window_rows.append({"window": index, "start": start, "end": end,
                            "stop": is_stop, "labels": labels,
                            "prototype": pmap, "product": rmap,
                            "agree": agreement,
                            "prototype_births": prototype.births,
                            "product_births": product._next_id - 1,
                            "prototype_local_merges": prototype.local_merges,
                            "product_local_merges": product_local_merges,
                            "prototype_displayed_ids": len(seen_prototype),
                            "product_displayed_ids": len(seen_product),
                            "prototype_committed_words": len(fresh_prototype),
                            "product_committed_words": len(fresh_product)})
        frontier = new_frontier
    first_prototype.sort(key=lambda word: (word["start"], word["end"]))
    first_product.sort(key=lambda word: (word["start"], word["end"]))
    published_product = snapshot_segments(observations, baseline)
    result = {"case": clip.clip_id, "tier": clip.tier, "mix": mix,
              "windows": len(window_rows),
              "assignment_agreement_windows": sum(row["agree"] for row in window_rows),
              "first_difference": first_difference,
              "first_ownership_difference": first_ownership_difference,
              "first_positive_ownership_difference": first_positive_ownership_difference,
              "embedding_interval_mismatches": embedding_interval_mismatches,
              "embedding_eligibility_mismatches": embedding_eligibility_mismatches,
              "first_embedding_interval_difference": first_embedding_interval_difference,
              "prototype_births": prototype.births,
              "product_births": product._next_id - 1,
              "prototype_min_overlap_s": prototype.min_overlap_s,
              "product_min_overlap_s": product.min_overlap_samples / SAMPLE_RATE,
              "prototype_local_merges": prototype.local_merges,
              "product_local_merges": product_local_merges,
              "prototype_displayed_ids": len(seen_prototype),
              "product_displayed_ids": len(seen_product),
              "prototype_committed_words": len(first_prototype),
              "product_committed_words": len(first_product),
              "prototype_settled_der": score_words(clip, first_prototype),
              "product_word_projection_der": score_words(clip, first_product),
              "product_snapshot_settled_der": score_segments(clip, published_product),
              "product_snapshot_segments": len(published_product),
              "product_snapshot_displayed_ids": len({row["speaker"] for row in published_product
                                                     if row["speaker"] != "S00"}),
              "c4_recorded_ids": baseline["by_hold"]["H0"]["variants"]["C1_C3_local_birth2"]["speaker_count"],
              "c4_recorded_der": (None if clip.tier == "e1" else
                                  baseline["by_hold"]["H0"]["variants"]["C1_C3_local_birth2"]["first"]["metrics"]["der"]),
              "windows_detail": window_rows}
    return result


def main():
    chosen = ([(clip, False) for clip in clips("accept6")] +
              [(clip, mix) for clip in clips("e1") for mix in (False, True)] +
              [(clip, False) for tier in ("long30m", "long60") for clip in clips(tier)
               if tier == "long60" or "lex_bill_ackman" in clip.clip_id])
    results = []
    for clip, mix in chosen:
        result = run_case(clip, mix)
        results.append(result)
        print(json.dumps({key: value for key, value in result.items()
                          if key != "windows_detail"}), flush=True)
        note(f"PARITY {clip.clip_id} {'mix' if mix else 'system'}: "
             f"assignments {result['assignment_agreement_windows']}/{result['windows']}, "
             f"births proto/product {result['prototype_births']}/{result['product_births']}, "
             f"IDs {result['prototype_displayed_ids']}/{result['product_displayed_ids']}, "
             f"DER prototype/product-word/product-snapshot "
             f"{result['prototype_settled_der']}/{result['product_word_projection_der']}/"
             f"{result['product_snapshot_settled_der']}; "
             f"first difference {result['first_difference']}")
    path = EVIDENCE / "parity-S15-L180-H0.json"
    path.write_text(json.dumps({"runtime": str(RUNTIME),
                                "registry_source": inspect.getfile(ContinuityRegistry),
                                "scheduler_source": inspect.getfile(GrowingContextWindowScheduler),
                                "comparison": "identical cached words/vectors; direct registry maps plus real product LiveSession snapshot",
                                "S": STEP, "Lmax": LENGTH, "H": 0, "cases": results}, indent=2))
    print(f"receipt {path}")


if __name__ == "__main__":
    main()
