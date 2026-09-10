"""Standing-bench measurement of the accepted production rule; no threshold search.

Run with the standing bench Python:
  python prototypes/streaming-diarization/voice-profile-matching/measure_production_rule.py \
    --assets /path/to/existing/prototypes/streaming-diarization/data --output /tmp/moss-g8.json
Fresh embeddings only. Terminal groups retain the bench's truth-aligned limitation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import prototype_voice_profile_match as bench

sys.path.insert(0, str(bench.REPO))
from moss_transcribe_diarize.app.phase2_voiceprint_match import VoiceprintProfile, match_voiceprint, normalized_mean


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    bench.harness.ONNX = args.assets / "voxceleb_resnet152_LM.onnx"
    model_sha = bench.file_sha256(bench.harness.ONNX)
    if model_sha != bench.MODEL_SHA256:
        raise SystemExit("Standing bench model does not match accepted asset")
    adapter = bench.harness.load_production_embedder()
    album = bench.load_album_module()
    evidence = []
    for name in ("acquired_jamie_dimon", "lex_bill_ackman"):
        case = bench.Case(name, args.assets / "real" / "benchmark_30m" / name)
        evidence.extend(bench.evidence_from_cache(case, bench.extract_fresh(case, adapter)))
    profiles = bench.build_profiles(album, evidence)
    bank = tuple(VoiceprintProfile(p.profile_id, p.speaker_name, "pinned-wespeaker",
                 normalized_mean([s.vector for s in p.samples])) for p in profiles.values())
    surfaces = {
        "causal": [(o.evidence_id, o.profile_id, o.vector, o.evidence_seconds)
                   for o in evidence if o.start_sec >= bench.PROBE_START_SECONDS and o.profile_id in profiles],
        "terminal_truth_aligned": [],
    }
    for observation in bench.terminal_observations(album, evidence, profiles, "arithmetic_mean"):
        sample = bench.album_sample(album, observation.true_profile_id,
            [e for e in evidence if e.case_id == observation.case_id],
            window_start=observation.start_sec, window_end=observation.end_sec)
        surfaces["terminal_truth_aligned"].append((observation.observation_id, observation.true_profile_id,
                                                  sample.vector, sample.sample_seconds))
    results = {}
    for surface, probes in surfaces.items():
        counts = dict(total=len(probes), known_correct=0, known_abstain=0, known_wrong=0, unknown_abstain=0, unknown_false=0)
        rows = []
        for probe_id, truth, vector, seconds in probes:
            obs = SimpleNamespace(centroid=vector, sample_seconds=seconds, provisional=False, embedder_id="pinned-wespeaker")
            known = match_voiceprint(obs, bank)
            unknown = match_voiceprint(obs, tuple(p for p in bank if p.voiceprint_id != truth))
            counts["known_abstain" if known is None else "known_correct" if known.voiceprint_id == truth else "known_wrong"] += 1
            counts["unknown_abstain" if unknown is None else "unknown_false"] += 1
            rows.append({"id": probe_id, "truth": truth, "seconds": seconds,
                         "known": None if known is None else known.voiceprint_id,
                         "unknown": None if unknown is None else unknown.voiceprint_id})
        results[surface] = {"counts": counts, "observations": rows}
    report = {"fresh_embeddings": True, "production_rule": True, "model_sha256": model_sha,
              "profiles": len(bank), "enrollment_samples": sum(len(p.samples) for p in profiles.values()),
              "deployed_qualification": False, "results": results,
              "limits": "Five speakers, two English recordings; terminal groups truth-aligned, not end-to-end clustering quality."}
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "results": {key: result["counts"] for key, result in results.items()}}))


if __name__ == "__main__":
    main()
