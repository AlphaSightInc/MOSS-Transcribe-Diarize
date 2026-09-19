"""Test acoustic terminal-to-live identity matching where time overlap is zero."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile

from moss_transcribe_diarize.app.live_identity_album import cosine_similarity
from moss_transcribe_diarize.app.live_provider_bundle import LiveProviderBundleConfig, _identity_encoder
from moss_transcribe_diarize.app.windowed_transcription import extract_window_wav

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
AUDIO = Path(
    "/private/tmp/moss-independent-assessment-20260918/.wp25runtime/"
    "20260919T033906530769Z/capacity-runtime/state/meeting-audio/"
    "Dp_cj6DoV5ofFG_AyP5xrv6RwNqAGBo1/L_Z-_FCVivrpL0TSLqon4B68/audio.mp3"
)

# Fresh terminal 30..180 s context decoded Jamie as S03 over 135.69..136.88.
TERMINAL_JAMIE = (165.69, 166.88)
# Live spans 72/150/228 labelled adjacent Jamie laughter S03; use distinct meeting times.
LIVE_JAMIE = ((167.08, 168.93), (347.08, 348.93), (527.08, 528.93))
# Source-adjudicated existing people, used only as runner-up controls.
LIVE_CONTROLS = {"Ben": (164.08, 165.59), "David": (169.44, 177.909)}


def main():
    config = LiveProviderBundleConfig.from_manifest(
        Path.home() / ".local/share/moss-transcribe-diarize/live/live-provider-manifest.json"
    )
    encoder = _identity_encoder(config, interval_workers=4)
    with tempfile.TemporaryDirectory(prefix="terminal-person-") as directory:
        wav = Path(directory) / "meeting.wav"
        extract_window_wav(AUDIO, wav, start_seconds=0, duration_seconds=600)
        terminal = tuple(encoder.embed(wav, [TERMINAL_JAMIE]))
        live = [tuple(encoder.embed(wav, [interval])) for interval in LIVE_JAMIE]
        controls = {name: tuple(encoder.embed(wav, [interval])) for name, interval in LIVE_CONTROLS.items()}
    scores = {"live-third": cosine_similarity(terminal, live[0]),
              **{name: cosine_similarity(terminal, vector) for name, vector in controls.items()}}
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    result = {
        "terminal_interval": TERMINAL_JAMIE,
        "live_third_intervals": LIVE_JAMIE,
        "time_overlap_seconds": 0.0,
        "repeated_live_third_cosines": [round(float(cosine_similarity(live[0], item)), 6) for item in live[1:]],
        "terminal_scores": {name: round(float(score), 6) for name, score in scores.items()},
        "winner": ranked[0][0],
        "winner_score": round(float(ranked[0][1]), 6),
        "runner_up_margin": round(float(ranked[0][1] - ranked[1][1]), 6),
        "match_floor": float(config.identity_config["min_match_score"]),
        "match_margin": float(config.identity_config["min_match_margin"]),
    }
    (HERE / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
