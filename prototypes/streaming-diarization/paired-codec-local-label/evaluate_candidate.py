"""Offline candidate replay on the freshly retained WAV/MP3 decoder spans."""
from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile

from moss_transcribe_diarize.app.live_identity import LiveSpeakerEvidence, assign_speakers
from moss_transcribe_diarize.app.live_identity_album import cosine_similarity
from moss_transcribe_diarize.app.live_provider_bundle import (
    LiveProviderBundleConfig, _birth_min_seconds, _fingerprint_album, _identity_config, _identity_encoder,
)
from moss_transcribe_diarize.app.speaker_identity import _mean_unit_vector, _normalized_vector, _run_onnx_embedding, _slice_interval
from moss_transcribe_diarize.app.windowed_transcription import extract_window_wav

HERE = Path(__file__).resolve().parent
RUNTIME = Path("/private/tmp/moss-independent-assessment-20260918/.wp25runtime/20260919T033906530769Z")


def overlap(a, b):
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def embed_intervals(embedder, path, intervals):
    session = embedder._load_session()
    samples, rate = embedder._load_audio(path)
    clips = [_slice_interval(samples, rate, start, end) for start, end in intervals]
    def one(values):
        return tuple(_normalized_vector(_run_onnx_embedding(session, embedder._features(values))))
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(one, clips))


def match(vector, references, floor, margin):
    scores = sorted(((speaker, cosine_similarity(vector, reference)) for speaker, reference in references.items()),
                    key=lambda item: (-item[1], item[0]))
    if not scores or scores[0][1] < floor or (len(scores) > 1 and scores[0][1] - scores[1][1] < margin):
        return None
    return scores[0][0]


def evaluate(arm, cases, reference, config, adapter):
    policy = _identity_config(config.identity_config)
    album = _fingerprint_album(config.identity_provider)
    minimum = int(config.identity_provider["min_segment_samples"]) / 16000.0
    observations = []
    mappings = {}
    label_truth = defaultdict(lambda: defaultdict(float))
    with tempfile.TemporaryDirectory(prefix=f"candidate-{arm}-") as directory:
        scratch = Path(directory)
        for index, case in enumerate(cases):
            path = scratch / f"{index}.wav"
            extract_window_wav(case["source"], path, start_seconds=case["source_start"], duration_seconds=case["duration"])
            local = tuple(sorted({segment["speaker"] for segment in case["segments"] if segment["speaker"] != "S00"}))
            means, durations, per_label = {}, {}, {}
            for speaker in local:
                selected = [(position, float(segment["start"]), float(segment["end"]))
                            for position, segment in enumerate(case["segments"])
                            if segment["speaker"] == speaker and float(segment["end"])-float(segment["start"]) >= minimum]
                vectors = embed_intervals(adapter._get_embedder(), path, [(start, end) for _, start, end in selected])
                per_label[speaker] = list(zip(selected, vectors, strict=True))
                means[speaker] = tuple(_mean_unit_vector(vectors))
                durations[speaker] = sum(end-start for _, start, end in selected)
            evidence = []
            for speaker in local:
                for canonical in album.speakers():
                    evidence.append(LiveSpeakerEvidence(speaker, canonical, cosine_similarity(means[speaker], album.reference(canonical))))
            mapping = dict(assign_speakers(local_speakers=local, canonical_speakers=album.speakers(), evidence=evidence, config=policy))
            births = [speaker for speaker in local if speaker not in mapping and durations[speaker] >= _birth_min_seconds(config.identity_provider)]
            for offset, speaker in enumerate(births, start=len(album.speakers())+1):
                mapping[speaker] = f"S{offset:02d}"
            for speaker in local:
                if speaker in mapping:
                    album.observe(canonical_speaker=mapping[speaker], vector=means[speaker], duration_sec=durations[speaker], span_id=index)
                    mappings[index, speaker] = mapping[speaker]
                for (position, start, end), vector in per_label[speaker]:
                    observations.append((index, case, position, speaker, start, end, vector))
                    absolute = (case["source_start"]+start, case["source_start"]+end)
                    for item in reference:
                        seconds = overlap(absolute, (item["start"], item["end"]))
                        if seconds:
                            label_truth[mapping[speaker]][item["speaker"]] += seconds
    references = {speaker: album.reference(speaker) for speaker in album.speakers()}
    canonical_person = {speaker: max(support, key=support.get) for speaker, support in label_truth.items()}
    totals = defaultdict(float)
    decisions = []
    own = ((0.0, 135.0), (135.0, 255.0), (255.0, 375.0))
    for index, case, position, local, start, end, vector in observations:
        absolute = (case["source_start"]+start, case["source_start"]+end)
        owned = (max(absolute[0], own[index][0]), min(absolute[1], own[index][1]))
        if owned[1] <= owned[0]:
            continue
        truth = defaultdict(float)
        for item in reference:
            seconds = overlap(owned, (item["start"], item["end"]))
            if seconds:
                truth[item["speaker"]] += seconds
        if not truth:
            continue
        person = max(truth, key=truth.get)
        weight = sum(truth.values())
        current = mappings[index, local]
        candidate = match(vector, references, policy.min_match_score, policy.min_match_margin)
        totals["scored_seconds"] += weight
        totals["current_correct_seconds" if canonical_person[current] == person else "current_confused_seconds"] += weight
        key = "candidate_unknown_seconds" if candidate is None else ("candidate_correct_seconds" if canonical_person[candidate] == person else "candidate_confused_seconds")
        totals[key] += weight
        if candidate != current:
            decisions.append({"window": index, "segment": position, "local": local, "truth": person,
                              "current": current, "candidate": candidate, "seconds": round(weight, 6)})
    return {"arm": arm, "mappings": [{"window": i, "local": l, "canonical": c} for (i,l),c in sorted(mappings.items())],
            "canonical_person": canonical_person, "totals": {key: round(value, 6) for key,value in sorted(totals.items())},
            "changed": decisions}


def main():
    payload = json.loads((HERE / "results.json").read_text())
    reference = [json.loads(line) for line in (RUNTIME / "files/media/reference.jsonl").read_text().splitlines()]
    config = LiveProviderBundleConfig.from_manifest(Path.home()/".local/share/moss-transcribe-diarize/live/live-provider-manifest.json")
    adapter = _identity_encoder(config, interval_workers=4)
    output = []
    for arm in ("wav", "mp3"):
        cases = [item for item in payload["cases"] if item["case"].startswith(f"composite-{arm}-")]
        output.append(evaluate(arm, cases, reference, config, adapter))
    result = {"arms": output}
    (HERE / "candidate-results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
