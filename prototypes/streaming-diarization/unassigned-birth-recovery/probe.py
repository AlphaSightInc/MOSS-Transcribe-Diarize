"""Measure recurring short-person evidence at the proposed production seam."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile

from moss_transcribe_diarize.app.live_identity import LiveIdentityConfig
from moss_transcribe_diarize.app.live_identity_album import cosine_similarity
from moss_transcribe_diarize.app.live_identity_sweep import (
    SWEEP_MERGE_THRESHOLD,
    LiveIdentitySweeper,
)
from moss_transcribe_diarize.app.live_provider_bundle import (
    LiveProviderBundleConfig,
    _fingerprint_album,
    _identity_config,
    _identity_encoder,
)
from moss_transcribe_diarize.app.windowed_transcription import extract_window_wav

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CAPACITY_AUDIO = Path(
    "/private/tmp/moss-independent-assessment-20260918/.wp25runtime/"
    "20260919T033906530769Z/capacity-runtime/state/meeting-audio/"
    "Dp_cj6DoV5ofFG_AyP5xrv6RwNqAGBo1/L_Z-_FCVivrpL0TSLqon4B68/audio.mp3"
)
SOURCE_AUDIO = ROOT / "evidence/live-policy-sweep-20260825/corpus/discussion_jamie_dimon_180s/audio.wav"
DISTINCT_AUDIO = ROOT / "evidence/live-policy-sweep-20260825/corpus/discussion_rtfl_90s/audio.wav"
JAMIE = ((165.68, 166.46), (345.68, 346.46), (525.68, 526.46))
CONTROLS = {"Ben": (164.08, 165.59), "David": (169.44, 177.909)}
DISTINCT_SHORT = {
    "ENG_A": ((5.9175, 6.803333), (49.0575, 49.63)),
    "ENG_B": ((45.288462, 46.161875), (55.855, 56.694999)),
}


def support(seed, observations, threshold):
    return sum(duration for vector, duration in observations
               if cosine_similarity(seed, vector) >= threshold)


def main() -> None:
    config = LiveProviderBundleConfig.from_manifest(
        Path.home() / ".local/share/moss-transcribe-diarize/live/live-provider-manifest.json"
    )
    encoder = _identity_encoder(config, interval_workers=4)
    with tempfile.TemporaryDirectory(prefix="unassigned-birth-") as directory:
        scratch = Path(directory)
        retained = scratch / "retained.wav"
        source = scratch / "source.wav"
        distinct_source = scratch / "distinct-source.wav"
        extract_window_wav(CAPACITY_AUDIO, retained, start_seconds=0.0, duration_seconds=600.0)
        extract_window_wav(SOURCE_AUDIO, source, start_seconds=0.0, duration_seconds=180.0)
        extract_window_wav(DISTINCT_AUDIO, distinct_source, start_seconds=0.0, duration_seconds=90.0)
        jamie = [tuple(encoder.embed(retained, [interval])) for interval in JAMIE]
        controls = {name: tuple(encoder.embed(source, [interval])) for name, interval in CONTROLS.items()}
        distinct = {
            name: [(tuple(encoder.embed(distinct_source, [interval])), interval[1] - interval[0], interval)
                   for interval in intervals]
            for name, intervals in DISTINCT_SHORT.items()
        }

    pair_scores = [
        round(float(cosine_similarity(jamie[left], jamie[right])), 6)
        for left, right in ((0, 1), (0, 2), (1, 2))
    ]
    control_scores = {
        name: [round(float(cosine_similarity(vector, item)), 6) for item in jamie]
        for name, vector in controls.items()
    }
    distinct_same_person = {
        name: round(float(cosine_similarity(items[0][0], items[1][0])), 6)
        for name, items in distinct.items()
    }
    distinct_cross_person = [
        round(float(cosine_similarity(left[0], right[0])), 6)
        for left in distinct["ENG_A"] for right in distinct["ENG_B"]
    ]
    distinct_support = {
        name: [
            round(support(item[0], [(prior[0], prior[1]) for prior in items[:index + 1]], SWEEP_MERGE_THRESHOLD), 6)
            for index, item in enumerate(items)
        ]
        for name, items in distinct.items()
    }
    observations = []
    support_seconds = []
    for vector in jamie:
        observations.append((vector, 0.78))
        support_seconds.append(round(support(vector, observations, SWEEP_MERGE_THRESHOLD), 6))

    policy: LiveIdentityConfig = _identity_config(config.identity_config)
    album = _fingerprint_album(config.identity_provider)
    sweeper = LiveIdentitySweeper(album=album, config=policy)
    for span, vector in zip((71, 149, 227), jamie, strict=True):
        sweeper.record(span_id=span, local_speaker="S00", canonical_speaker=None,
                       vector=vector, duration_sec=0.78)
    album.observe(canonical_speaker="speaker-0003", vector=jamie[1], duration_sec=0.78, span_id=149)
    sweeper.record(span_id=149, local_speaker="S00", canonical_speaker="speaker-0003",
                   vector=jamie[1], duration_sec=0.78)
    revision = sweeper.sweep_now()

    result = {
        "birth_floor_seconds": float(config.identity_provider["birth_min_seconds"]),
        "compatibility_threshold": SWEEP_MERGE_THRESHOLD,
        "jamie_pair_cosines": pair_scores,
        "different_person_cosines": control_scores,
        "distinct_short_same_person_cosine": distinct_same_person,
        "distinct_short_cross_person_cosines": distinct_cross_person,
        "distinct_short_cumulative_compatible_seconds": distinct_support,
        "jamie_cumulative_compatible_seconds": support_seconds,
        "single_fragment_births": support_seconds[0] >= float(config.identity_provider["birth_min_seconds"]),
        "second_fragment_births": support_seconds[1] >= float(config.identity_provider["birth_min_seconds"]),
        "sweep": revision.to_dict(),
    }
    (HERE / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
