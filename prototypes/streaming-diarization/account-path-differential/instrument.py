import os
"""Observation only: record identity inputs and outputs; preserve provider call order."""
import json, os, time
from pathlib import Path
from moss_transcribe_diarize.app.live_provider_bundle import WeSpeakerLiveEvidenceProvider, _speaker_intervals_by_label
_original = WeSpeakerLiveEvidenceProvider.score
def measured(self, *, span, pcm, segments, base_snapshot):
    before = time.monotonic()
    result = _original(self, span=span, pcm=pcm, segments=segments, base_snapshot=base_snapshot)
    record = {
        "span_id": span.id, "start_sample": span.start_sample, "end_sample": span.end_sample,
        "existing_speaker_count": len(base_snapshot.canonical_speakers),
        "intervals": _speaker_intervals_by_label(span, segments, self.min_segment_samples),
        "evidence": [{"local": x.local_speaker, "canonical": x.canonical_speaker, "score": x.score} for x in result],
        "elapsed_seconds": time.monotonic() - before,
    }
    with (Path(os.environ["MOSS_DIFFERENTIAL_SCRATCH"]) / ("identity-" + str(os.getpid()) + ".jsonl")).open("a") as output:
        output.write(json.dumps(record) + "\n")
    return result
WeSpeakerLiveEvidenceProvider.score = measured
