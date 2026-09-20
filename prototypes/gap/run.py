"""R4-3 offline replay: retained S17 state + production CPU WeSpeaker identity path."""
from __future__ import annotations

import argparse
import json
import math
import re
import tempfile
import wave
from pathlib import Path

from moss_transcribe_diarize.app.live_identity import (
    BoundedCausalIdentityPreparer,
    LiveIdentityConfig,
)
from moss_transcribe_diarize.app.live_identity_album import (
    FingerprintAlbum,
    cosine_similarity,
)
from moss_transcribe_diarize.app.live_provider_bundle import WeSpeakerLiveEvidenceProvider
from moss_transcribe_diarize.app.live_session import FrozenSpan, LiveIdentitySnapshot
from moss_transcribe_diarize.app.live_span_bounds import span_segments
from moss_transcribe_diarize.app.speaker_identity import _OnnxWeSpeakerEmbedder


RATE = 16_000
BYTES_PER_SAMPLE = 2
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RETAINED = ROOT / "evidence/round4/gap/retained"
DEFAULT_CORPUS = Path(
    "/Users/gao/Desktop/AI_Projects/Github_Projects/"
    "MOSS-Transcribe-Diarize/evidence/live-policy-sweep-20260825/corpus"
)
DEFAULT_MODEL = Path(
    "/Users/gao/.local/share/moss-transcribe-diarize/live/"
    "voxceleb_resnet152_LM.onnx"
)


class RecordingAlbum(FingerprintAlbum):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.last_observation = None

    def observe(self, **kwargs):
        disposition = super().observe(**kwargs)
        self.last_observation = {
            "canonical_speaker": kwargs["canonical_speaker"],
            "duration_sec": kwargs["duration_sec"],
            "span_id": kwargs["span_id"],
            "disposition": disposition,
        }
        return disposition


def read_pcm(path: Path, start: float, end: float) -> bytes:
    with wave.open(str(path), "rb") as audio:
        assert (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) == (
            RATE,
            1,
            BYTES_PER_SAMPLE,
        )
        audio.setpos(round(start * RATE))
        return audio.readframes(round((end - start) * RATE))


def gap_pcm(corpus: Path) -> bytes:
    source = corpus / "interview_adam_frank_180s/audio.wav"
    adam = read_pcm(source, 49.0, 109.0)
    return adam[: 25 * RATE * 2] + bytes(10 * RATE * 2) + adam[35 * RATE * 2 :]


def write_wav(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(RATE)
        audio.writeframes(pcm)


def album_state(album: FingerprintAlbum) -> dict:
    return {
        speaker: {
            "exemplars": [
                {"span_id": item.span_id, "duration_sec": item.duration_sec}
                for item in album.exemplars(speaker)
            ],
            "provisional": album.has_provisional(speaker),
        }
        for speaker in album.speakers()
    }


def local_durations(transcript: str, sample_count: int) -> dict[str, float]:
    totals: dict[str, float] = {}
    for segment in span_segments(transcript, sample_count=sample_count):
        totals[segment.speaker] = totals.get(segment.speaker, 0.0) + (
            segment.end - segment.start
        )
    return totals


def scores_for_pending(provider, album, span_id: int) -> dict[str, dict[str, float]]:
    scores = {}
    for local, (vector, _seconds) in provider._pending_vectors.get(span_id, {}).items():
        scores[local] = {
            speaker: score
            for speaker in album.speakers()
            if (score := cosine_similarity(vector, album.reference(speaker))) is not None
        }
    return scores


def replay_causal(gap: dict, pcm: bytes, embedder, manifest: dict):
    policy = manifest["identity_config"]
    provider_config = manifest["identity_provider"]
    album = RecordingAlbum(
        admission_seconds=provider_config["album_admission_seconds"]
    )
    provider = WeSpeakerLiveEvidenceProvider(
        encoder=embedder,
        min_segment_samples=provider_config["min_segment_samples"],
        birth_min_seconds=provider_config["birth_min_seconds"],
        album=album,
    )
    preparer = BoundedCausalIdentityPreparer(
        config=LiveIdentityConfig(
            policy["max_speakers"],
            policy["min_match_score"],
            policy["min_match_margin"],
        ),
        evidence_provider=provider,
    )
    snapshot = LiveIdentitySnapshot()
    decisions = []
    for retained in gap["final"]["snapshot"]["session"]["committed"]:
        span = FrozenSpan(
            retained["span_id"],
            0,
            retained["start_sample"],
            retained["end_sample"],
            "retained_s17",
        )
        raw_transcript = retained["transcript"]
        span_pcm = pcm[span.start_sample * 2 : span.end_sample * 2]
        base = {
            "span_id": span.id,
            "start_sec": span.start_sample / RATE,
            "end_sec": span.end_sample / RATE,
            "span_sec": span.sample_count / RATE,
            "retained_transcript": raw_transcript,
            "thresholds": {
                "min_segment_samples": provider.min_segment_samples,
                "min_segment_sec": provider.min_segment_samples / RATE,
                "birth_min_sec": provider.birth_min_seconds,
                "album_admission_sec": album.admission_seconds,
                "min_match_score": policy["min_match_score"],
                "min_match_margin": policy["min_match_margin"],
            },
            "album_before": album_state(album),
        }
        if not any(span_pcm):
            decisions.append(
                {**base, "decision": "digital_silence_guard", "album_after": album_state(album)}
            )
            continue
        if "[S00]" in raw_transcript:
            decisions.append(
                {
                    **base,
                    "decision": "retained_unattributed_local_trace_unavailable",
                    "album_after": album_state(album),
                }
            )
            continue
        transcript = re.sub(r"\[S(\d\d)\]", r"[S1\1]", raw_transcript)
        durations = local_durations(transcript, span.sample_count)
        preparation = preparer.prepare(
            span=span,
            pcm=span_pcm,
            transcript=transcript,
            base_snapshot=snapshot,
        )
        scores = scores_for_pending(provider, album, span.id)
        diagnostics = dict(preparation.proposed_snapshot.diagnostics)
        snapshot = preparation.proposed_snapshot
        album.last_observation = None
        provider.reconcile_committed(snapshot)
        decisions.append(
            {
                **base,
                "local_speech_sec": durations,
                "scores_before_commit": scores,
                "status": preparation.status,
                "diagnostics": diagnostics,
                "album_observation": album.last_observation,
                "album_after": album_state(album),
            }
        )
    provider.finalize_identity(base_snapshot=snapshot)
    return decisions, album, provider, preparer, snapshot


def overlap(left: dict, right: dict) -> float:
    return max(0.0, min(left["end_sample"], right["end_sample"]) - max(left["start_sample"], right["start_sample"]))


def replay_saved(gap: dict, pcm: bytes, wav_path: Path, embedder, album, preparer, snapshot, manifest):
    policy = manifest["identity_config"]
    min_samples = manifest["identity_provider"]["min_segment_samples"]
    pre = gap["pre"]["snapshot"]["session"]["effective_transcript"]
    saved = gap["final"]["snapshot"]["session"]["effective_transcript"]
    rows = []
    for index, segment in enumerate(saved, 1):
        samples = segment["end_sample"] - segment["start_sample"]
        covered = any(
            item["source_lane"] == segment["source_lane"]
            and item["canonical_speaker"] is not None
            and overlap(segment, item) > 0
            for item in pre
        )
        scores = {}
        if samples >= min_samples:
            vector = embedder.embed(
                wav_path,
                [(segment["start_sample"] / RATE, segment["end_sample"] / RATE)],
            )
            scores = {
                speaker: score
                for speaker in album.speakers()
                if (score := cosine_similarity(vector, album.reference(speaker))) is not None
            }
        row = {
            "saved_span": f"seg_{index:04d}",
            "start_sec": segment["start_sample"] / RATE,
            "end_sec": segment["end_sample"] / RATE,
            "duration_sec": samples / RATE,
            "text": segment["text"],
            "observed_canonical": segment["canonical_speaker"],
            "pre_terminal_covered": covered,
            "eligible_samples": samples,
            "min_segment_samples": min_samples,
            "scores": scores,
            "match_score_threshold": policy["min_match_score"],
            "match_margin_threshold": policy["min_match_margin"],
            "album": album_state(album),
        }
        if segment["canonical_speaker"] is None:
            span = FrozenSpan(
                10_000 + index,
                0,
                segment["start_sample"],
                segment["end_sample"],
                "terminal_uncovered" if not covered else "terminal_unassigned",
            )
            preparation = preparer.prepare_revision(
                span=span,
                pcm=pcm[span.start_sample * 2 : span.end_sample * 2],
                transcript=f"[0][S01]{segment['text']}[{samples / RATE}]",
                base_snapshot=snapshot,
                allowed_speakers=snapshot.canonical_speakers,
            )
            proposed_label = span_segments(
                preparation.relabeled_transcript, sample_count=samples
            )[0].speaker
            proposed_index = int(proposed_label[1:]) - 1
            row.update(
                {
                    "fallback_status": preparation.status,
                    "fallback_diagnostics": dict(preparation.proposed_snapshot.diagnostics),
                    "fallback_display_label": proposed_label,
                    "projected_canonical": (
                        snapshot.canonical_speakers[proposed_index]
                        if 0 <= proposed_index < len(snapshot.canonical_speakers)
                        else None
                    ),
                    "decision": "terminal_probe_below_evidence_floor_then_unprojectable_birth",
                }
            )
        else:
            row["decision"] = "terminal_partition_mapping_or_acoustic_match"
        rows.append(row)
    return rows


def remedy_controls(embedder, wav_path: Path, album, corpus: Path, manifest: dict):
    threshold = manifest["identity_config"]["min_match_score"]
    reference = album.reference("speaker-0001")
    adam_vector = embedder.embed(wav_path, [(50.81, 53.99)])
    keyu_path = corpus / "interview_keyu_jin_60s/audio.wav"
    keyu_vector = embedder.embed(keyu_path, [(0.0, 3.18)])
    adam_score = cosine_similarity(adam_vector, reference)
    keyu_score = cosine_similarity(keyu_vector, reference)
    return {
        "candidate": "aggregate eligible intervals only within one terminal-local partition",
        "invariants": {
            "individual_interval_floor_samples": manifest["identity_provider"]["min_segment_samples"],
            "match_score": threshold,
            "match_margin": manifest["identity_config"]["min_match_margin"],
            "no_temporal_neighbor_assignment": True,
        },
        "healthy_control": {
            "voice": "Adam",
            "intervals_sec": [[50.81, 53.99]],
            "score_to_adam_album": adam_score,
            "decision": "match" if adam_score is not None and adam_score >= threshold else "abstain",
        },
        "falsifier_control": {
            "voice": "Keyu",
            "intervals_sec": [[0.0, 3.18]],
            "score_to_adam_album": keyu_score,
            "decision": "match" if keyu_score is not None and keyu_score >= threshold else "abstain",
        },
        "s17_raw_terminal_partition": "UNMEASURED: decoder-local labels were not retained",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retained", type=Path, default=DEFAULT_RETAINED)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    gap = json.loads((args.retained / "gap.json").read_text())
    manifest = json.loads((args.retained / "manifest.json").read_text())
    pcm = gap_pcm(args.corpus)
    embedder = _OnnxWeSpeakerEmbedder(args.model, device="cpu")
    embedder.load()
    with tempfile.TemporaryDirectory(prefix="moss-r4-gap-") as directory:
        wav_path = Path(directory) / "gap.wav"
        write_wav(wav_path, pcm)
        causal, album, _provider, preparer, snapshot = replay_causal(
            gap, pcm, embedder, manifest
        )
        saved = replay_saved(
            gap, pcm, wav_path, embedder, album, preparer, snapshot, manifest
        )
        controls = remedy_controls(embedder, wav_path, album, args.corpus, manifest)
    offending = next(row for row in saved if row["observed_canonical"] is None)
    report = {
        "schema": "moss-r4-gap-diagnosis.v1",
        "model": str(args.model),
        "model_expected_sha256": manifest["assets"][0]["sha256"],
        "decoder_requests": 0,
        "causal_spans": causal,
        "saved_spans": saved,
        "hypotheses": {
            "a_evidence_or_admission_floor": {
                "verdict": "SUPPORTED_min_segment_only",
                "state": {
                    "duration_sec": offending["duration_sec"],
                    "samples": offending["eligible_samples"],
                    "min_segment_samples": offending["min_segment_samples"],
                    "album_admission_sec": manifest["identity_provider"]["album_admission_seconds"],
                },
            },
            "b_birth_floor": {
                "verdict": "EXCLUDED_as_guard_at_revision_seam",
                "state": {
                    "duration_sec": offending["duration_sec"],
                    "birth_min_sec": manifest["identity_provider"]["birth_min_seconds"],
                    "revision_reader_has_album": False,
                    "fallback_assignment": offending["fallback_diagnostics"].get("assignments"),
                },
            },
            "c_match_score_margin": {
                "verdict": "EXCLUDED_no_vector_no_score",
                "state": {
                    "scores": offending["scores"],
                    "min_match_score": manifest["identity_config"]["min_match_score"],
                    "min_match_margin": manifest["identity_config"]["min_match_margin"],
                },
            },
            "d_deferred_birth": {
                "verdict": "EXCLUDED_revision_reader_has_no_album_deferral",
                "state": offending["fallback_diagnostics"],
            },
            "e_terminal_mapping": {
                "verdict": "SUPPORTED",
                "state": {
                    "pre_terminal_covered": offending["pre_terminal_covered"],
                    "fallback_display_label": offending["fallback_display_label"],
                    "projected_canonical": offending["projected_canonical"],
                },
            },
            "f_silence_reseed": {
                "verdict": "EXCLUDED",
                "state": {
                    "canonical_after_first_speech": causal[0]["album_after"],
                    "canonical_after_silence": next(
                        row["album_after"] for row in causal if row["start_sec"] >= 34.9
                    ),
                },
            },
        },
        "mechanism": (
            "terminal-only uncovered 0.27 s segment -> below 8000-sample evidence floor -> "
            "no score -> revision-only temporary birth -> label index absent from settled "
            "canonical set -> None/S00"
        ),
        "remedy_controls": controls,
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    print(rendered, end="")
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)


if __name__ == "__main__":
    main()
