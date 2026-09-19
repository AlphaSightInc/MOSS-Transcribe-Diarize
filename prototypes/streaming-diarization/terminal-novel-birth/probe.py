"""Measure unchanged live birth semantics on retained terminal voice evidence."""
from __future__ import annotations

import json
from pathlib import Path

from moss_transcribe_diarize.app.live_identity import (
    LiveIdentityError,
    LiveSpeakerEvidence,
    assign_speakers,
)
from moss_transcribe_diarize.app.live_identity_album import cosine_similarity
from moss_transcribe_diarize.app.live_provider_bundle import (
    LiveProviderBundleConfig,
    _birth_min_seconds,
    _fingerprint_album,
    _identity_config,
    _identity_encoder,
)
from moss_transcribe_diarize.app.speaker_identity import _mean_unit_vector


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
AUDIO = ROOT / "evidence/live-policy-sweep-20260825/corpus/discussion_jamie_dimon_180s/audio.wav"
MANIFEST = Path.home() / ".local/share/moss-transcribe-diarize/live/live-provider-manifest.json"

# Each enrollment observation is one decoder-emitted terminal segment of known source identity.
ENROLLMENT = {
    "speaker-ben": (
        (135.78, 138.61),
        (138.61, 142.40),
        (143.78, 146.78),
        (146.78, 149.75),
        (149.75, 151.82),
        (160.00, 162.16),
    ),
    "speaker-david": (
        (120.64, 125.15),
        (125.15, 130.78),
        (130.78, 135.42),
    ),
}

# Each probe is one local-speaker evidence unit. Multiple intervals reproduce the decoder-local
# grouping of two adjacent short segments before the real encoder reduces them to one vector.
PROBES = {
    "known_ben_1.00": {"truth": "speaker-ben", "intervals": ((163.52, 164.52),)},
    "known_ben_1.03": {"truth": "speaker-ben", "intervals": ((178.97, 180.00),)},
    "known_david_1.37": {
        "truth": "speaker-david",
        "intervals": ((169.47, 170.34), (170.34, 170.84)),
    },
    "known_david_1.35": {"truth": "speaker-david", "intervals": ((174.87, 176.22),)},
    "terminal_novel_exact_1.19": {"truth": None, "intervals": ((165.69, 166.88),)},
    "terminal_novel_trim_left_1.09": {"truth": None, "intervals": ((165.79, 166.88),)},
    "terminal_novel_trim_right_1.09": {"truth": None, "intervals": ((165.69, 166.78),)},
    # Diagnostics only: the coarse source row may contain boundary contamination.
    "boundary_left_1.19": {"truth": None, "intervals": ((165.60, 166.79),)},
    "boundary_right_1.19": {"truth": None, "intervals": ((168.24, 169.43),)},
    "boundary_coarse_3.83": {"truth": None, "intervals": ((165.60, 169.43),)},
    "adjacent_live_laugh_1.85": {"truth": None, "intervals": ((167.08, 168.93),)},
}


def duration(intervals: tuple[tuple[float, float], ...]) -> float:
    return sum(end - start for start, end in intervals)


def embed_units(encoder) -> dict[str, tuple[float, ...]]:
    units: list[tuple[str, tuple[tuple[float, float], ...]]] = []
    for speaker, intervals in ENROLLMENT.items():
        for index, interval in enumerate(intervals):
            units.append((f"enroll:{speaker}:{index}", (interval,)))
    units.extend((f"probe:{name}", row["intervals"]) for name, row in PROBES.items())

    flattened = [interval for _name, intervals in units for interval in intervals]
    vectors = encoder.embed_intervals(AUDIO, flattened)
    output: dict[str, tuple[float, ...]] = {}
    cursor = 0
    for name, intervals in units:
        width = len(intervals)
        output[name] = tuple(_mean_unit_vector(vectors[cursor : cursor + width]))
        cursor += width
    if cursor != len(vectors):
        raise RuntimeError("encoder vector count did not match retained interval plan")
    return output


def fresh_album(config, vectors):
    album = _fingerprint_album(config.identity_provider)
    dispositions = {}
    span_id = 0
    for speaker, intervals in ENROLLMENT.items():
        for index, interval in enumerate(intervals):
            span_id += 1
            dispositions[f"{speaker}:{index}"] = album.observe(
                canonical_speaker=speaker,
                vector=vectors[f"enroll:{speaker}:{index}"],
                duration_sec=duration((interval,)),
                span_id=span_id,
            )
    return album, dispositions


def apply_unchanged_policy(name, row, *, config, vectors):
    album, enrollment = fresh_album(config, vectors)
    policy = _identity_config(config.identity_config)
    vector = vectors[f"probe:{name}"]
    evidence = tuple(
        LiveSpeakerEvidence(
            local_speaker="terminal-local",
            canonical_speaker=speaker,
            score=float(cosine_similarity(vector, album.reference(speaker))),
        )
        for speaker in album.speakers()
    )
    scores = {item.canonical_speaker: item.score for item in evidence}
    try:
        mapping = dict(
            assign_speakers(
                local_speakers=("terminal-local",),
                canonical_speakers=album.speakers(),
                evidence=evidence,
                config=policy,
            )
        )
    except LiveIdentityError as error:
        return {
            "duration_sec": round(duration(row["intervals"]), 6),
            "truth": row["truth"],
            "scores": {key: round(value, 6) for key, value in scores.items()},
            "outcome": "abstain",
            "reason": str(error),
            "enrollment": enrollment,
        }

    seconds = duration(row["intervals"])
    matched = mapping.get("terminal-local")
    if matched is not None:
        disposition = album.observe(
            canonical_speaker=matched,
            vector=vector,
            duration_sec=seconds,
            span_id=100,
        )
        return {
            "duration_sec": round(seconds, 6),
            "truth": row["truth"],
            "scores": {key: round(value, 6) for key, value in scores.items()},
            "outcome": "matched",
            "canonical_speaker": matched,
            "album_disposition": disposition,
            "enrollment": enrollment,
        }

    birth_floor = _birth_min_seconds(config.identity_provider)
    if seconds < birth_floor:
        return {
            "duration_sec": round(seconds, 6),
            "truth": row["truth"],
            "scores": {key: round(value, 6) for key, value in scores.items()},
            "outcome": "deferred_birth",
            "birth_floor_sec": birth_floor,
            "enrollment": enrollment,
        }
    new_speaker = "speaker-terminal-new"
    disposition = album.observe(
        canonical_speaker=new_speaker,
        vector=vector,
        duration_sec=seconds,
        span_id=100,
    )
    return {
        "duration_sec": round(seconds, 6),
        "truth": row["truth"],
        "scores": {key: round(value, 6) for key, value in scores.items()},
        "outcome": "birth",
        "canonical_speaker": new_speaker,
        "album_disposition": disposition,
        "birth_floor_sec": birth_floor,
        "enrollment": enrollment,
    }


def main() -> None:
    config = LiveProviderBundleConfig.from_manifest(MANIFEST)
    encoder = _identity_encoder(config, interval_workers=4)
    vectors = embed_units(encoder)
    probes = {
        name: apply_unchanged_policy(name, row, config=config, vectors=vectors)
        for name, row in PROBES.items()
    }
    exact = vectors["probe:terminal_novel_exact_1.19"]
    sensitivity = {
        name: round(float(cosine_similarity(exact, vectors[f"probe:{name}"])), 6)
        for name in (
            "terminal_novel_trim_left_1.09",
            "terminal_novel_trim_right_1.09",
            "boundary_left_1.19",
            "boundary_right_1.19",
            "boundary_coarse_3.83",
            "adjacent_live_laugh_1.85",
        )
    }
    known = {name: row for name, row in probes.items() if name.startswith("known_")}
    candidate = probes["terminal_novel_exact_1.19"]
    assertions = {
        "all_known_short_controls_match_truth": all(
            row["outcome"] == "matched" and row["canonical_speaker"] == row["truth"]
            for row in known.values()
        ),
        "known_short_false_births_zero": sum(row["outcome"] == "birth" for row in known.values()) == 0,
        "terminal_candidate_births": candidate["outcome"] == "birth",
        "terminal_candidate_uses_existing_provisional_tier": candidate.get("album_disposition")
        == "provisional",
    }
    result = {
        "config": {
            "min_match_score": config.identity_config["min_match_score"],
            "min_match_margin": config.identity_config["min_match_margin"],
            "birth_min_seconds": _birth_min_seconds(config.identity_provider),
            "album_admission_seconds": config.identity_provider["album_admission_seconds"],
        },
        "probes": probes,
        "terminal_exact_boundary_sensitivity": sensitivity,
        "assertions": assertions,
        "supported": all(assertions.values()),
    }
    (HERE / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
