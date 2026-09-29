"""Freeze a 900-second long60 slice and verify the P1 cache before any live send."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import wave

RATE = 16000
MODEL = "gemini-3.5-transcribe"
CONFIG = {"transcription_config": {"mode": {"type": "verbatim",
           "diarization_mode": "speaker", "timestamp_granularities": ["word"]}}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--integration", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    integration = args.integration.resolve()
    sys.path.insert(0, str(integration))
    from moss_transcribe_diarize.app.gemini_provider import _wav
    source = integration / "prototypes/gemini-live/.cache/long60/audio.wav"
    cache = integration / "prototypes/gemini-live/.cache"
    args.out.mkdir(parents=True, exist_ok=True)
    prefix = args.out / "long60-first900.wav"
    with wave.open(str(source), "rb") as reader:
        assert (reader.getnchannels(), reader.getsampwidth(), reader.getframerate()) == (1, 2, RATE)
        pcm = reader.readframes(900 * RATE)
        assert len(pcm) == 900 * RATE * 2
    with wave.open(str(prefix), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(RATE)
        writer.writeframes(pcm)
    hits, misses = 0, []
    for end in range(15 * RATE, 900 * RATE + 1, 15 * RATE):
        start = max(0, end - 90 * RATE)
        audio = _wav(pcm[start*2:end*2])
        key = hashlib.sha256(audio + json.dumps([MODEL, CONFIG], sort_keys=True).encode()).hexdigest()
        if (cache / key[:2] / f"{key}.json").is_file():
            hits += 1
        else:
            misses.append({"start_sample": start, "end_sample": end, "key": key})
    record = {"source_wav": str(source), "prefix_wav": str(prefix),
              "source_wav_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "prefix_wav_sha256": hashlib.sha256(prefix.read_bytes()).hexdigest(),
              "prefix_pcm_sha256": hashlib.sha256(pcm).hexdigest(),
              "sample_count": 900 * RATE, "scheduled_cache_hits": hits,
              "scheduled_cache_misses": misses}
    (args.out / "input-preflight.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"sample_count": record["sample_count"],
                      "scheduled_cache_hits": hits, "scheduled_cache_misses": len(misses)},
                     sort_keys=True))
    if misses:
        raise SystemExit("scheduled window cache misses; do not launch paid replay")


if __name__ == "__main__":
    main()
