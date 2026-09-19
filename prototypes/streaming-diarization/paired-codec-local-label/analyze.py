"""Offline source alignment and production-encoder analysis of retained probe results."""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import tempfile

from moss_transcribe_diarize.app.live_identity_album import cosine_similarity
from moss_transcribe_diarize.app.live_provider_bundle import LiveProviderBundleConfig, _identity_encoder
from moss_transcribe_diarize.app.windowed_transcription import extract_window_wav

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RUNTIME = Path("/private/tmp/moss-independent-assessment-20260918/.wp25runtime/20260919T033906530769Z")


def overlap(a, b):
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def main() -> None:
    payload = json.loads((HERE / "results.json").read_text())
    reference = [json.loads(line) for line in (RUNTIME / "files/media/reference.jsonl").read_text().splitlines()]
    config = LiveProviderBundleConfig.from_manifest(
        Path.home() / ".local/share/moss-transcribe-diarize/live/live-provider-manifest.json"
    )
    encoder = _identity_encoder(config, interval_workers=4)
    minimum = int(config.identity_provider["min_segment_samples"]) / 16000.0
    rows = []
    vectors = {}
    with tempfile.TemporaryDirectory(prefix="paired-codec-analysis-") as directory:
        scratch = Path(directory)
        for index, case in enumerate(payload["cases"]):
            if not case["case"].startswith("composite-"):
                continue
            path = scratch / f"{index}.wav"
            extract_window_wav(
                case["source"], path,
                start_seconds=float(case["source_start"]), duration_seconds=float(case["duration"]),
            )
            for local in sorted({segment["speaker"] for segment in case["segments"]}):
                intervals = [(float(segment["start"]), float(segment["end"]))
                             for segment in case["segments"] if segment["speaker"] == local
                             and float(segment["end"]) - float(segment["start"]) >= minimum]
                vectors[(case["case"], local)] = tuple(encoder.embed(path, intervals))
                truth = defaultdict(float)
                for segment in case["segments"]:
                    if segment["speaker"] != local:
                        continue
                    absolute = (float(case["source_start"]) + float(segment["start"]),
                                float(case["source_start"]) + float(segment["end"]))
                    for item in reference:
                        seconds = overlap(absolute, (float(item["start"]), float(item["end"])))
                        if seconds:
                            truth[item["speaker"]] += seconds
                total = sum(truth.values())
                rows.append({
                    "case": case["case"], "local": local,
                    "truth_seconds": {name: round(value, 6) for name, value in sorted(truth.items())},
                    "majority_fraction": round(max(truth.values(), default=0.0) / total if total else 0.0, 6),
                })
    pairs = []
    for start in (0, 120, 240):
        for local in ("S01", "S02", "S03"):
            wav = vectors[(f"composite-wav-{start}", local)]
            mp3 = vectors[(f"composite-mp3-{start}", local)]
            pairs.append({"start": start, "local": local,
                          "wav_mp3_cosine": round(float(cosine_similarity(wav, mp3)), 6)})
    output = {"local_truth": rows, "paired_vector_similarity": pairs}
    (HERE / "analysis.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
