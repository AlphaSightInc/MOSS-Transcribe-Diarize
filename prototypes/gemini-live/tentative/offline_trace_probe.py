"""Conditional, zero-provider quality check on attempt-1 preview timing.

Run: python prototypes/gemini-live/tentative/offline_trace_probe.py --trace <jsonl>
Uses the P61 causal canonical replay and cached real WeSpeaker 1 s vectors for
public long60. It tests the matching decision on observed preview buckets; it
cannot prove that the live HTTP lane publishes the needed canonical IDs.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import tentative  # noqa: E402
from moss_transcribe_diarize.app.gemini_tentative import GeminiTentativeLabeler  # noqa: E402

RATE = 16000
STEP = RATE // 2

class CachedEncoder:
    def __init__(self):
        self.vector = ()
    def embed(self, path, intervals):
        return self.vector


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--trace', type=Path, required=True)
    args = parser.parse_args()
    clip, = tentative.clips('long60')
    reference = clip.reference_segments()
    causal = tentative.canonical(clip, 2586)
    vectors = np.load(tentative.CACHE / 'long60-long60-W1.0.npz')
    cached = {round(float(t), 3): tuple(map(float, v))
              for t, v in zip(vectors['t'], vectors['v'])}
    pcm = tentative.read_wav(clip.audio)
    trace = [json.loads(line) for line in args.trace.read_text().splitlines()]
    first = {}
    for row in sorted(trace, key=lambda item: item['observed_wall_s']):
        for bucket in range(row['start_sample']//STEP, (row['end_sample']-1)//STEP+1):
            midpoint = bucket*STEP+STEP//2
            if row['start_sample'] <= midpoint < row['end_sample']:
                first.setdefault(bucket, row)
    votes = defaultdict(lambda: defaultdict(float))
    for start, end, speaker in causal['settled']:
        if speaker is None:
            continue
        truth = tentative.truth_at(reference, (start+end)/2)
        if truth is not None:
            votes[speaker][truth] += max(end-start, .05)
    mapping = {speaker:max(counts,key=counts.get) for speaker,counts in votes.items()}
    first_birth = {}
    for wall, frontier, centroids, *_ in causal['snaps']:
        for speaker in centroids:
            first_birth.setdefault(speaker, wall)
    encoder = CachedEncoder()
    labeler = GeminiTentativeLabeler(encoder)
    eligible = shown = correct = missing_vector = voiced = 0
    by_truth = defaultdict(lambda: {'eligible':0,'shown':0,'correct':0})
    from moss_transcribe_diarize.app.gemini_tentative import _webrtc_voiced
    for bucket,row in sorted(first.items()):
        t = (bucket+1)*.5
        truth = tentative.truth_at(reference, t-.25)
        if truth is None:
            continue
        eligible += 1
        by_truth[truth]['eligible'] += 1
        vector = cached.get(round(t,3))
        if vector is None:
            missing_vector += 1
            continue
        if not _webrtc_voiced(pcm[bucket*STEP:(bucket+1)*STEP].tobytes()):
            continue
        voiced += 1
        ready = [snap for snap in causal['snaps'] if snap[0] <= t]
        if not ready:
            continue
        centroids = {speaker:tuple(map(float, value)) for speaker,value in ready[-1][2].items()}
        encoder.vector = vector
        guess,_ = labeler._embed(pcm[max(0,(bucket-1)*STEP):(bucket+1)*STEP].tobytes(),centroids)
        if guess is None:
            continue
        shown += 1
        by_truth[truth]['shown'] += 1
        if mapping.get(guess) == truth:
            correct += 1
            by_truth[truth]['correct'] += 1
    labeler.close()
    result = {'schema':'wp4-offline-trace-conditional.v1','trace_rows':len(trace),
              'eligible_buckets':eligible,'voiced_buckets':voiced,
              'missing_cached_vector_buckets':missing_vector,
              'shown_buckets':shown,'correct_buckets':correct,
              'coverage':shown/eligible,'accuracy_when_shown':correct/shown if shown else None,
              'causal_centroid_birth_wall_s':first_birth,'canonical_to_reference':mapping,
              'by_reference':dict(by_truth),
              'qualification':'CONDITIONAL: P61 cached canonical output, not attempt-1 HTTP settled labels'}
    print(json.dumps(result,indent=2,sort_keys=True))

if __name__ == '__main__':
    main()
