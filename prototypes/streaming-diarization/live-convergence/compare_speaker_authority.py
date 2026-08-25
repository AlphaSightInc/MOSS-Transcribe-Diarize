#!/usr/bin/env python3
"""PROTOTYPE -- throwaway. Plan §11.1 / campaign M3: does a witness that owns its own speaker
evidence (S1) name voices better than the projection from the 2.5 s base spans (S0)?

Preregistered in `PREREGISTRATION-M3.md` -- arms, 14 gates, seven predictions, the selection
and disposition rules, all written in iteration 19 before this file existed. Nothing here may
be changed to make a number pass, and no threshold in the identity stack moves: album
`min_match_score`, `min_match_margin`, the 2.0 s admission floor, the 1.0 s birth floor, the
0.5 s evidence floor and the 2.5 s hard cap are all read from the DEPLOYED provider manifest
rather than spelled here.

**What the two arms are.**

* **S0** -- what the deployment serves today. The rolling witness publishes its words with
  `canonical_speaker=None`, and `LiveSession._build_effective_transcript` projects a label onto
  each of them from the base segments it overlaps. This arm is not recomputed here: it is read
  from the checked-in M2 exit passes through the production export
  (`hypothesis_from_live_snapshot`), and the run refuses unless that export reproduces the
  pass's own `live-hypothesis.jsonl` byte-for-byte.
* **S1** -- plan §11.1. Each 10 s witness decode carries its own local speaker labels. Their
  owned intervals -- and nothing else, D5 -- are embedded with the production WeSpeaker encoder
  and matched against the meeting album with the production matcher (`assign_speakers`). A
  local speaker that matches gets that canonical identity; one that does not is left alone, and
  the session's projection answers for it exactly as it does today. The witness never *births*
  a canonical speaker: plan §6 M4 step 5 says "return stable meeting identity or abstain", and
  birth is the base path's, calibrated by ADR-0002 on 2.5 s spans.

So S1 is a strict refinement of S0: it changes a label only where witness-owned evidence gives
an answer, which is what makes "no per-case regression" a meaningful bar rather than a coin
flip on a rewritten surface.

**Where the audio comes from, and what that costs in fidelity.** The witness decode is a MOSS
request, and plan §11.1 requires each witness be decoded once and reused. The §10.2 grid
already decoded exactly this geometry (10 s windows on a 10 s stride, same audio, same model,
same token cap), so those decodes are read from its on-disk cache and the trio costs **zero**
MOSS requests. A cached decode is not guaranteed identical to the one the deployed service
made -- greedy decoding on this stack has a measured flip rate -- so every window is checked
against the surface the deployment published and the disagreements are reported, not hidden.
Windows missing from the cache are decoded through the production runner only with
`--allow-decode` (one in-flight request, results cached).

**The album is rebuilt causally, from production parts.** A window that completes at sample E
may only see evidence the base path had already committed and reconciled by then. The album is
therefore fed span by span -- each committed span's published labels, its intervals, its
embedding -- and the span whose vectors are still pending at E is held back, because in
production a span's vectors reach the album only when the *next* span's preparation reconciles
them. `FingerprintAlbum` itself is the production class; this file does not restate any of its
admission rules.

One command:

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \\
      prototypes/streaming-diarization/live-convergence/compare_speaker_authority.py \\
      --cases lex_bill_ackman,lex_javier_milei,lex_keyu_jin \\
      --output /tmp/moss-speaker-authority.json

Exit 0 iff the bench validates (the S0 control reproduces the deployed export and the deployed
scorer's own DER to 6 dp) and no D5 violation is found. The arm verdict is printed, never
enforced here: the preregistered gates are scored on the deployed passes, not on this bench.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import statistics
import sys
import tempfile
import time
import wave
from pathlib import Path
from typing import Any, Iterable, Sequence

REPO = Path(__file__).resolve().parents[3]
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from measure_m3_baseline import (  # noqa: E402
    base_span_seconds,
    mixed_window_collapse,
    unattributed,
)
from evaluator_v2 import Segment as V2Segment, score_v2, speech_regions_from_wav  # noqa: E402
from verify_m2_exit import (  # noqa: E402
    CASE_DURATION_SEC,
    FIVE_MINUTE_CASE,
    RUNS,
    TRIO_CASES,
    case_paths,
    corpus_contract,
    load_reference_rows,
)
from moss_transcribe_diarize import live_speaker_accuracy as lsa  # noqa: E402
from moss_transcribe_diarize.evaluation import (  # noqa: E402
    Segment,
    calculate_diarization,
    calculate_tbsa,
)
from moss_transcribe_diarize.live_surface import UNATTRIBUTED_SPEAKER  # noqa: E402
from moss_transcribe_diarize.app.live_identity import (  # noqa: E402
    LiveIdentityConfig,
    LiveIdentityError,
    LiveSpeakerEvidence,
    assign_speakers,
)
from moss_transcribe_diarize.app.live_identity_album import (  # noqa: E402
    ALBUM_BIRTH_MIN_SECONDS,
    ALBUM_EXEMPLARS_PER_SPEAKER,
    FingerprintAlbum,
)
from moss_transcribe_diarize.app.live_provider_bundle import (  # noqa: E402
    _cosine_similarity,
    _intervals_duration,
    _speaker_intervals_by_label,
    _vector_values,
    _write_pcm_wav,
)
from moss_transcribe_diarize.app.live_session import FrozenSpan  # noqa: E402
from moss_transcribe_diarize.app.live_span_bounds import span_segments  # noqa: E402
from moss_transcribe_diarize.app.live_transcript_convergence import (  # noqa: E402
    DEFAULT_ROLLING_GEOMETRY,
)

SAMPLE_RATE = 16000
DEFAULT_PASSES = REPO / "evidence/live-convergence-0824/M2-e2-exit/passes"
DEFAULT_DECODE_CACHE = Path("/tmp/moss-rolling-grid-cache-20260825/run0.json")
DEFAULT_EMBED_CACHE = Path("/tmp/moss-speaker-authority-embed-cache-v1.json")
DEPLOYED_MANIFEST = Path.home() / ".local/share/moss-transcribe-diarize/live/live-provider-manifest.json"
ARMS = ("s0", "s1")


class BenchRefusal(RuntimeError):
    """A measurement precondition this bench will not paper over."""


# ------------------------------------------------------------------ deployment rules


def deployed_rules(manifest_path: Path) -> dict[str, Any]:
    """Every identity rule this bench applies, read from the deployment that will run S1.

    No defaults. Iteration 19's lesson, and the reason its sliding-window screen was wrong for
    one run: a measurement that supplies its own value for a deployed rule can disagree with
    the deployment silently, and a plausible table is worse than a crash.
    """

    if not manifest_path.exists():
        raise BenchRefusal(f"no deployed provider manifest at {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    identity_config = manifest.get("identity_config") or {}
    provider = manifest.get("identity_provider") or {}
    assets = {asset["name"]: asset for asset in manifest.get("assets", [])}
    state = assets.get("identity-state")
    for key, source in (
        ("max_speakers", identity_config),
        ("min_match_score", identity_config),
        ("min_match_margin", identity_config),
    ):
        if source.get(key) is None:
            raise BenchRefusal(f"deployed manifest states no identity_config.{key}")
    for key in ("min_segment_samples", "album_admission_seconds", "birth_min_seconds"):
        if provider.get(key) is None:
            raise BenchRefusal(f"deployed manifest states no identity_provider.{key}")
    if state is None:
        raise BenchRefusal("deployed manifest declares no identity-state asset")
    onnx = manifest_path.parent / state["path"]
    if not onnx.exists():
        raise BenchRefusal(f"deployed identity-state asset missing: {onnx}")
    return {
        "manifest": str(manifest_path),
        "onnx": onnx,
        "onnx_sha256": state["sha256"],
        "identity_config": LiveIdentityConfig(
            max_speakers=int(identity_config["max_speakers"]),
            min_match_score=float(identity_config["min_match_score"]),
            min_match_margin=float(identity_config["min_match_margin"]),
        ),
        "min_segment_samples": int(provider["min_segment_samples"]),
        "album_admission_seconds": float(provider["album_admission_seconds"]),
        "birth_min_seconds": float(provider["birth_min_seconds"]),
        "hard_cap_samples": int((manifest.get("endpoint_config") or {}).get("hard_cap_samples", 0)),
    }


# ------------------------------------------------------------------ encoder + embedding cache


class EmbeddingBank:
    """The production encoder, with plan §11.1's caching rule and its accounting.

    "Cache an embedding only when its exact sample interval and channel content are unchanged"
    -- so the key is the audio's hash plus the exact absolute sample intervals, and changed
    segmentation misses by construction. Hits and misses are counted because the plan requires
    them printed: a cache that silently answered for a *different* interval would make S1 look
    free and would be measuring the wrong audio.
    """

    def __init__(self, *, onnx: Path, cache_path: Path | None):
        self.cache_path = cache_path
        self.entries: dict[str, list[float]] = {}
        if cache_path is not None and cache_path.exists():
            payload = json.loads(cache_path.read_text())
            if payload.get("schema") != "moss-speaker-authority-embed-cache.v1":
                raise BenchRefusal(f"embedding cache schema mismatch: {cache_path}")
            self.entries = payload["entries"]
        self.hits = 0
        self.misses = 0
        self.encode_seconds = 0.0
        self.encoded_audio_seconds = 0.0
        # Split by what asked for the vector. The album's embeddings are the BASE path's work
        # and are already inside the deployed RTF; only the witness's are what S1 adds, and a
        # marginal cost reported as a total is a marginal cost nobody has measured.
        self.by_tag: dict[str, dict[str, float]] = {}
        self._adapter = None
        self._onnx = onnx

    @property
    def adapter(self):
        if self._adapter is None:
            from moss_transcribe_diarize.app.speaker_identity import WeSpeakerResNet152LmAdapter

            adapter = WeSpeakerResNet152LmAdapter(self._onnx)
            preflight = adapter.preflight()
            if not preflight.available:
                raise BenchRefusal(f"production encoder preflight failed: {preflight.reason}")
            self._adapter = adapter
        return self._adapter

    def embed(
        self,
        *,
        audio_sha: str,
        pcm: bytes,
        origin_sample: int,
        intervals: Sequence[tuple[float, float]],
        tag: str,
    ) -> tuple[tuple[float, ...], bool]:
        """One evidence unit's vector, and whether the cache answered.

        `pcm` is the enclosing unit of audio (a base span, or a rolling window) and `intervals`
        are relative to its first sample -- exactly what `WeSpeakerLiveEvidenceProvider.score`
        hands the encoder. `origin_sample` only enters the cache key, so two identical intervals
        at different meeting times are still different evidence.
        """

        absolute = [
            (
                origin_sample + int(round(start * SAMPLE_RATE)),
                origin_sample + int(round(end * SAMPLE_RATE)),
            )
            for start, end in intervals
        ]
        key = hashlib.sha256(
            f"{audio_sha}:{absolute}".encode("utf-8")
        ).hexdigest()
        node = self.by_tag.setdefault(tag, {"hits": 0, "misses": 0, "seconds": 0.0, "audio_seconds": 0.0})
        cached = self.entries.get(key)
        if cached is not None:
            self.hits += 1
            node["hits"] += 1
            return tuple(cached), True
        self.misses += 1
        node["misses"] += 1
        seconds = sum(end - start for start, end in intervals)
        with tempfile.TemporaryDirectory(prefix="moss-speaker-authority-") as directory:
            wav_path = Path(directory) / "evidence.wav"
            _write_pcm_wav(wav_path, pcm)
            started = time.monotonic()
            vector = _vector_values(self.adapter.embed(wav_path, list(intervals)))
            elapsed = time.monotonic() - started
        self.encode_seconds += elapsed
        self.encoded_audio_seconds += seconds
        node["seconds"] += elapsed
        node["audio_seconds"] += seconds
        self.entries[key] = list(vector)
        return vector, False

    def save(self) -> None:
        if self.cache_path is None:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps(
                {"schema": "moss-speaker-authority-embed-cache.v1", "entries": self.entries},
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    def accounting(self) -> dict[str, Any]:
        return {
            "cache_hits": self.hits,
            "cache_misses": self.misses,
            "encoder_seconds": round(self.encode_seconds, 6),
            "encoded_audio_seconds": round(self.encoded_audio_seconds, 6),
            "seconds_per_embed": (
                round(self.encode_seconds / self.misses, 6) if self.misses else None
            ),
            "by_tag": {
                tag: {
                    "cache_hits": int(node["hits"]),
                    "cache_misses": int(node["misses"]),
                    "encoder_seconds": round(node["seconds"], 6),
                    "encoded_audio_seconds": round(node["audio_seconds"], 6),
                    "seconds_per_embed": (
                        round(node["seconds"] / node["misses"], 6) if node["misses"] else None
                    ),
                }
                for tag, node in sorted(self.by_tag.items())
            },
        }


# ------------------------------------------------------------------ reading one pass


def read_trace(path: Path) -> tuple[dict, list[dict]]:
    """The pass's terminal snapshot record and its rolling-window events."""

    candidates = [path, path.with_suffix(path.suffix + ".gz")]
    source = next((candidate for candidate in candidates if candidate.exists()), None)
    if source is None:
        raise BenchRefusal(f"no trace beside the pass: {path}")
    opener = gzip.open if source.suffix == ".gz" else open
    snapshot: dict | None = None
    windows: list[dict] = []
    with opener(source, "rt", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if "snapshot" in record and record.get("kind") != "session_created":
                snapshot = record
            event = record.get("event")
            if isinstance(event, dict) and event.get("kind") == "rolling_decode_completed":
                windows.append(event["payload"])
    if snapshot is None:
        raise BenchRefusal(f"trace carries no terminal snapshot: {source}")
    return snapshot, windows


def read_pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as source:
        state = (
            source.getnchannels(),
            source.getsampwidth(),
            source.getframerate(),
            source.getcomptype(),
        )
        if state != (1, 2, SAMPLE_RATE, "NONE"):
            raise BenchRefusal(f"audio contract violated by {path}: {state}")
        return source.readframes(source.getnframes())


class WitnessDecodes:
    """The 10 s window decodes, from the §10.2 grid's cache or -- opted into -- from vLLM."""

    def __init__(self, *, cache_path: Path, model: str, allow_decode: bool):
        self.cache_path = cache_path
        self.model = model
        self.allow_decode = allow_decode
        self.entries: dict[str, dict] = {}
        if cache_path.exists():
            payload = json.loads(cache_path.read_text())
            if payload.get("schema") != "moss-context-arms-decode-cache.v2":
                raise BenchRefusal(f"decode cache schema mismatch: {cache_path}")
            self.entries = payload["entries"]
        self.hits = 0
        self.fresh = 0
        self._decoder = None

    def _key(self, audio_sha: str, start: int, end: int, token_cap: int) -> str:
        from moss_transcribe_diarize.inference_utils import DEFAULT_PROMPT

        prompt_sha = hashlib.sha256(DEFAULT_PROMPT.encode("utf-8")).hexdigest()[:16]
        return f"{audio_sha}:{start}:{end}:{self.model}:{token_cap}:{prompt_sha}"

    def transcript(
        self,
        *,
        audio_sha: str,
        audio_path: Path,
        pcm: bytes,
        start: int,
        end: int,
        token_cap: int,
    ) -> str:
        key = self._key(audio_sha, start, end, token_cap)
        entry = self.entries.get(key)
        if entry is not None:
            self.hits += 1
            return str(entry["transcript"])
        if not self.allow_decode:
            raise BenchRefusal(
                f"window [{start},{end}) of {audio_path.parent.name} is not in the decode cache; "
                "re-run with --allow-decode to spend a MOSS request on it."
            )
        entry = self._decode(pcm=pcm, start=start, end=end, token_cap=token_cap)
        self.entries[key] = entry
        self.fresh += 1
        self._save()
        return str(entry["transcript"])

    def _decode(self, *, pcm: bytes, start: int, end: int, token_cap: int) -> dict:
        if self._decoder is None:
            from moss_transcribe_diarize.app.vllm_runner import VllmRunner

            self._decoder = VllmRunner(
                base_url="http://127.0.0.1:18000/v1",
                model=self.model,
                api_key=None,
                timeout=1800,
            )
        runner = self._decoder
        from moss_transcribe_diarize.inference_utils import DEFAULT_PROMPT

        with tempfile.TemporaryDirectory(prefix="moss-witness-decode-") as directory:
            wav_path = Path(directory) / "window.wav"
            _write_pcm_wav(wav_path, pcm[start * 2 : end * 2])
            response = runner.transcribe(wav_path, prompt=DEFAULT_PROMPT, max_new_tokens=token_cap)
        return {"transcript": str(response.text), "generated_tokens": int(response.generated_tokens)}

    def _save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps(
                {"schema": "moss-context-arms-decode-cache.v2", "entries": self.entries},
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    def accounting(self) -> dict[str, Any]:
        return {"cache_hits": self.hits, "fresh_moss_requests": self.fresh}


# ------------------------------------------------------------------ the causal album


class CausalAlbum:
    """The meeting album as it stood when a given window's decode came back.

    Fed one committed span at a time, in order, from what that span *published*: production
    offers the album exactly the assignments a prepared preparation made, and a published
    label is that assignment (`S0k` is canonical speaker `k-1`; `S00` is an abstention nobody
    enrolled). Rebuilding from published labels therefore reproduces the deployed album
    without re-deciding any identity -- this bench never re-runs the base path's matcher.
    """

    def __init__(
        self,
        *,
        canonical_speakers: tuple[str, ...],
        admission_seconds: float,
        min_segment_samples: int,
        bank: EmbeddingBank,
        audio_sha: str,
        pcm: bytes,
    ):
        self.canonical_speakers = canonical_speakers
        self.album = FingerprintAlbum(
            admission_seconds=admission_seconds,
            exemplars_per_speaker=ALBUM_EXEMPLARS_PER_SPEAKER,
        )
        self.min_segment_samples = min_segment_samples
        self.bank = bank
        self.audio_sha = audio_sha
        self.pcm = pcm
        self.observations: list[dict] = []
        self.established: list[str] = []
        self._reconciled_through = -1

    def feed_through(self, spans: list[dict], end_sample: int) -> None:
        """Observe every span whose vectors production would already have reconciled by `end_sample`.

        The last span that fits is held back: a span's vectors reach the album only when the
        NEXT span's preparation reconciles them, so at the instant a window completes the most
        recent committed span is still pending.
        """

        eligible = [
            index
            for index, span in enumerate(spans)
            if span["end_sample"] <= end_sample
        ]
        if len(eligible) < 2:
            return
        for index in eligible[:-1]:
            if index <= self._reconciled_through:
                continue
            self._observe(spans[index])
            self._reconciled_through = index

    def _observe(self, span: dict) -> None:
        transcript = span.get("revised_transcript") or span["transcript"]
        sample_count = span["end_sample"] - span["start_sample"]
        segments = span_segments(transcript, sample_count=sample_count)
        frozen = FrozenSpan(
            id=int(span["span_id"]),
            epoch=0,
            start_sample=int(span["start_sample"]),
            end_sample=int(span["end_sample"]),
            reason="replayed",
        )
        intervals = _speaker_intervals_by_label(frozen, segments, self.min_segment_samples)
        for label, owned in sorted(intervals.items()):
            canonical = self._canonical_of(label)
            if canonical is None:
                continue
            vector, cached = self.bank.embed(
                audio_sha=self.audio_sha,
                pcm=self.pcm[span["start_sample"] * 2 : span["end_sample"] * 2],
                origin_sample=int(span["start_sample"]),
                intervals=owned,
                tag="album",
            )
            duration = _intervals_duration(owned)
            disposition = self.album.observe(
                canonical_speaker=canonical,
                vector=vector,
                duration_sec=duration,
                span_id=frozen.id,
            )
            if canonical not in self.established:
                self.established.append(canonical)
            self.observations.append(
                {
                    "span_id": frozen.id,
                    "published_label": label,
                    "canonical_speaker": canonical,
                    "seconds": round(duration, 6),
                    "disposition": disposition,
                    "cached": cached,
                }
            )

    def _canonical_of(self, label: str) -> str | None:
        """The production reading of a published label: `S00` names nobody, `S0k` names the kth."""

        if label == UNATTRIBUTED_SPEAKER or not label.startswith("S"):
            return None
        try:
            index = int(label[1:]) - 1
        except ValueError:
            return None
        if 0 <= index < len(self.canonical_speakers):
            return self.canonical_speakers[index]
        return None

    def references(self) -> list[tuple[str, tuple[float, ...]]]:
        out = []
        for canonical in self.established:
            reference = self.album.reference(canonical)
            if reference is not None:
                out.append((canonical, tuple(reference)))
        return out


# ------------------------------------------------------------------ the S1 resolver


def resolve_window(
    *,
    window: dict,
    transcript: str,
    pcm: bytes,
    audio_sha: str,
    album: CausalAlbum,
    bank: EmbeddingBank,
    rules: dict[str, Any],
) -> dict[str, Any]:
    """Plan §6 M4 for one witness: owned intervals in, meeting identities or an abstention out.

    The five steps are the module's, in order -- select owned intervals, apply the evidence
    floor, embed, reconcile against the album, return identity or abstain -- and every rule
    they apply is production's: `_speaker_intervals_by_label` is the floor, `assign_speakers`
    is the matcher (one-to-one, `min_match_score`, `min_match_margin`, ambiguity raises), and
    `FingerprintAlbum.reference` is the vector a voice is compared with.

    No birth. A local speaker the album cannot name keeps no answer, and the session's
    projection publishes what it publishes today.
    """

    start, end = int(window["owned_start_sample"]), int(window["owned_end_sample"])
    sample_count = end - start
    frozen = FrozenSpan(id=int(window["item_id"]), epoch=0, start_sample=start, end_sample=end, reason="rolling")
    segments = span_segments(transcript, sample_count=sample_count)
    owned = _speaker_intervals_by_label(frozen, segments, rules["min_segment_samples"])
    window_pcm = pcm[start * 2 : end * 2]
    if len(window_pcm) != sample_count * 2:
        raise BenchRefusal(f"window [{start},{end}) is not inside the corpus audio")

    embedded: dict[str, tuple[float, ...]] = {}
    units: list[dict] = []
    for label, intervals in sorted(owned.items()):
        vector, cached = bank.embed(
            audio_sha=audio_sha,
            pcm=window_pcm,
            origin_sample=start,
            intervals=intervals,
            tag="witness",
        )
        embedded[label] = vector
        units.append(
            {
                "local_speaker": label,
                "intervals_seconds": [[round(lo, 3), round(hi, 3)] for lo, hi in intervals],
                "intervals_samples": [
                    [start + int(round(lo * SAMPLE_RATE)), start + int(round(hi * SAMPLE_RATE))]
                    for lo, hi in intervals
                ],
                "seconds": round(_intervals_duration(intervals), 6),
                "cache_hit": cached,
            }
        )

    references = album.references()
    evidence: list[LiveSpeakerEvidence] = []
    for label, vector in sorted(embedded.items()):
        for canonical, reference in references:
            evidence.append(
                LiveSpeakerEvidence(
                    local_speaker=label,
                    canonical_speaker=canonical,
                    score=_cosine_similarity(vector, reference),
                    evidence_id=f"witness:{frozen.id}:{label}:{canonical}",
                )
            )
    mapping: dict[str, str] = {}
    abstention: str | None = None
    if embedded and references:
        try:
            mapping = dict(
                assign_speakers(
                    local_speakers=tuple(sorted(embedded)),
                    canonical_speakers=tuple(canonical for canonical, _ in references),
                    evidence=tuple(evidence),
                    config=rules["identity_config"],
                )
            )
        except LiveIdentityError as exc:
            mapping = {}
            abstention = str(exc)
    elif not references:
        abstention = "album_has_no_reference"
    elif not embedded:
        abstention = "no_interval_cleared_evidence_floor"

    return {
        "window_index": int(window["window_index"]),
        "start_sample": start,
        "end_sample": end,
        "local_speakers": sorted({segment.speaker for segment in segments}),
        "embedded_units": units,
        "album_references": [canonical for canonical, _ in references],
        "evidence": [
            {
                "local_speaker": item.local_speaker,
                "canonical_speaker": item.canonical_speaker,
                "score": round(item.score, 6),
            }
            for item in evidence
        ],
        "mapping": mapping,
        "abstention": abstention,
        "unmapped_locals": sorted(set(embedded) - set(mapping)),
        "segments": [
            {
                "start_sample": start + int(round(segment.start * SAMPLE_RATE)),
                "end_sample": start + int(round(segment.end * SAMPLE_RATE)),
                "local_speaker": segment.speaker,
                "text": segment.text,
            }
            for segment in segments
        ],
    }


def d5_violations(window: dict[str, Any]) -> list[dict[str, Any]]:
    """G-M3-0, checked from the arm's own per-embedding log rather than asserted in prose.

    Three ways a vector could carry audio that is not one local speaker's: an interval that
    reaches outside the window (context or prefix), one that is not exactly a segment this
    local speaker published (a merged or padded interval), and one that overlaps a segment
    another local speaker owns (mixed-window audio).
    """

    by_local: dict[str, list[tuple[int, int]]] = {}
    for segment in window["segments"]:
        by_local.setdefault(segment["local_speaker"], []).append(
            (segment["start_sample"], segment["end_sample"])
        )
    violations: list[dict[str, Any]] = []
    for unit in window["embedded_units"]:
        local = unit["local_speaker"]
        for lo, hi in unit["intervals_samples"]:
            if lo < window["start_sample"] or hi > window["end_sample"]:
                violations.append({"window": window["window_index"], "local": local, "interval": [lo, hi], "reason": "outside_window"})
            if not any(lo >= slo and hi <= shi for slo, shi in by_local.get(local, [])):
                violations.append({"window": window["window_index"], "local": local, "interval": [lo, hi], "reason": "not_inside_one_owned_segment"})
            for other, spans in by_local.items():
                if other == local:
                    continue
                if any(min(hi, shi) - max(lo, slo) > 0 for slo, shi in spans):
                    violations.append({"window": window["window_index"], "local": local, "interval": [lo, hi], "reason": f"overlaps_local_{other}"})
    return violations


# ------------------------------------------------------------------ applying S1 to the surface


def apply_s1(session: dict, resolved: list[dict[str, Any]]) -> tuple[dict, dict[str, Any]]:
    """The S1 surface: S0's words, with the labels witness-owned evidence could answer for.

    In production each surface segment IS a witness segment and carries its own local speaker,
    so no association is needed. Here the witness is a cached replica of the decode the service
    made, and greedy decoding on this stack flips occasionally, so a segment is associated with
    the local speaker whose own segments overlap it most. Windows where the replica and the
    served surface disagree are counted and reported: an association that had to guess is a
    fidelity cost of the bench, not a property of S1.
    """

    surface = [dict(segment) for segment in session["effective_transcript"]]
    changed: list[dict[str, Any]] = []
    kept = 0
    exact_windows = 0
    for window in resolved:
        rolling = [
            segment
            for segment in surface
            if segment["authority"] == "rolling"
            and window["start_sample"] <= segment["start_sample"] < window["end_sample"]
        ]
        witness_texts = [segment["text"].strip() for segment in window["segments"]]
        if witness_texts == [segment["text"].strip() for segment in rolling]:
            exact_windows += 1
        for segment in rolling:
            local = _dominant_local(segment, window["segments"])
            canonical = window["mapping"].get(local) if local else None
            if canonical is None:
                kept += 1
                continue
            if canonical != segment.get("canonical_speaker"):
                changed.append(
                    {
                        "window_index": window["window_index"],
                        "start_seconds": round(segment["start_sample"] / SAMPLE_RATE, 3),
                        "end_seconds": round(segment["end_sample"] / SAMPLE_RATE, 3),
                        "local_speaker": local,
                        "projection_said": segment.get("canonical_speaker"),
                        "witness_says": canonical,
                        "text": segment["text"][:80],
                    }
                )
            segment["canonical_speaker"] = canonical
    revised = dict(session)
    revised["effective_transcript"] = surface
    return revised, {
        "segments_relabelled": len(changed),
        "relabelled": changed,
        "segments_left_to_projection": kept,
        "windows_witness_matches_surface": exact_windows,
        "windows": len(resolved),
    }


def _dominant_local(segment: dict, witness_segments: list[dict]) -> str | None:
    best: tuple[float, str] | None = None
    for candidate in witness_segments:
        overlap = min(segment["end_sample"], candidate["end_sample"]) - max(
            segment["start_sample"], candidate["start_sample"]
        )
        if overlap <= 0:
            continue
        if best is None or overlap > best[0]:
            best = (overlap, candidate["local_speaker"])
    return None if best is None else best[1]


# ------------------------------------------------------------------ scoring


def score_surface(
    *,
    snapshot_record: dict,
    session: dict,
    reference_transcript: list,
    reference_activity: list,
    duration: float,
) -> tuple[dict[str, Any], list]:
    """The deployed scorer's axes, through the deployed export, for one surface."""

    payload = {"snapshot": dict(snapshot_record["snapshot"])}
    payload["snapshot"]["session"] = session
    hypothesis = list(
        lsa.hypothesis_from_live_snapshot(
            payload, corpus_start_sample=0, corpus_duration_sec=duration
        )
    )
    reference_eval = [
        Segment(start=float(item.start), end=float(item.end), speaker=str(item.speaker), text=str(item.text))
        for item in reference_transcript
    ]
    hypothesis_eval = [
        Segment(start=float(item.start), end=float(item.end), speaker=str(item.speaker), text=str(item.text))
        for item in hypothesis
    ]
    tbsa = calculate_tbsa(reference_eval, hypothesis_eval)
    diarization = calculate_diarization(reference_eval, hypothesis_eval)
    confusion = confusion_attribution(reference_eval, hypothesis_eval, diarization["speaker_mapping"])
    speaker = lsa.score_live_speaker_accuracy(
        list(reference_activity),
        [lsa.SpeakerActivityInterval(item.start, item.end, item.speaker) for item in hypothesis],
    )
    return (
        {
            "der": diarization["der"],
            "miss": diarization["miss"],
            "false_alarm": diarization["false_alarm"],
            "speaker_confusion": diarization["speaker_confusion"],
            "speaker_accuracy": speaker["speaker_accuracy"],
            "wer": tbsa["wer"],
            "text_speaker_accuracy": tbsa["text_speaker_accuracy"],
            "segments": len(hypothesis),
            "published_speakers": sorted({item.speaker for item in hypothesis}),
            "speaker_mapping": diarization["speaker_mapping"],
            "confusion_attribution": confusion,
        },
        hypothesis,
    )


def confusion_attribution(reference_eval, hypothesis_eval, mapping: dict) -> dict[str, Any]:
    """Which published seconds the scorer counts as the wrong voice, and where they are.

    Post-hoc, and deliberately outside every arm: `resolve_window` never sees a reference.
    A confusion total tells a milestone how much room it has; this tells it *which segments*
    hold the room, which is the difference between "S1 tied" and "S1 tied because the seconds
    it could have fixed are not the seconds that are wrong".
    """

    rows: list[dict[str, Any]] = []
    for ref in reference_eval:
        for hyp in hypothesis_eval:
            overlap = min(ref.end, hyp.end) - max(ref.start, hyp.start)
            if overlap <= 0.0 or mapping.get(ref.speaker) == hyp.speaker:
                continue
            voices = {
                other.speaker
                for other in reference_eval
                if min(other.end, hyp.end) - max(other.start, hyp.start) > 0.0
            }
            rows.append(
                {
                    "seconds": round(overlap, 3),
                    "reference_speaker": ref.speaker,
                    "published_speaker": hyp.speaker,
                    "published_interval": [round(hyp.start, 3), round(hyp.end, 3)],
                    "reference_voices_in_segment": sorted(voices),
                    "class": _confusion_class(hyp, voices),
                    "text": hyp.text[:80],
                }
            )
    rows.sort(key=lambda row: row["seconds"], reverse=True)
    by_class: dict[str, float] = {}
    for row in rows:
        by_class[row["class"]] = round(by_class.get(row["class"], 0.0) + row["seconds"], 3)
    return {
        "confused_seconds": round(sum(row["seconds"] for row in rows), 3),
        "confused_segments": len({tuple(row["published_interval"]) for row in rows}),
        "seconds_by_class": by_class,
        "rows": rows,
    }


def _confusion_class(hypothesis_segment, reference_voices: set[str]) -> str:
    """Which of three different problems this confused second actually is.

    Only one of them is a speaker-authority question, and the decomposition is what tells a
    milestone whether its arm had anything to win:

    * `segment_straddles_turn` -- the published segment contains audio from two reference
      speakers. Whatever single label it carries, part of it is wrong. This is a **segment
      extent** defect, owned by whatever chose the segment boundaries, and no label from any
      authority can remove it.
    * `unattributed` -- the segment was published as `S00`. Nobody claimed it; the scorer
      counts it against whichever speaker it overlaps. A speaker authority *can* fix this,
      by naming it correctly.
    * `misattributed` -- a segment that holds exactly one reference speaker's audio and was
      published as somebody else. The only class a better voice match wins outright.
    """

    if len(reference_voices) >= 2:
        return "segment_straddles_turn"
    if hypothesis_segment.speaker == UNATTRIBUTED_SPEAKER:
        return "unattributed"
    return "misattributed"


def deployed_reference_axes(results: Path, case: str) -> dict[str, Any]:
    """What the deployed run recorded for this case's live arm -- the control S0 must reproduce."""

    if not results.exists():
        raise BenchRefusal(f"pass has no results.json: {results}")
    data = json.loads(results.read_text())
    arms = data["results"] if "results" in data else None
    if arms is None:
        for node in data.get("cases", []):
            if node["case_id"] == case:
                arms = node["arms"]
                break
    if not arms or "live" not in arms:
        raise BenchRefusal(f"pass results carry no live arm for {case}: {results}")
    scores = arms["live"]["scores"]
    return {
        "der": scores["diarization"]["der"],
        "speaker_accuracy": scores["speaker"]["speaker_accuracy"],
        "wer": scores["tbsa"]["wer"],
    }


# ------------------------------------------------------------------ one case, one run


def run_case(
    *,
    case: str,
    run: str,
    passes_root: Path,
    contract: dict,
    rules: dict[str, Any],
    bank: EmbeddingBank,
    decodes: WitnessDecodes,
    speech_regions,
) -> dict[str, Any]:
    from moss_transcribe_diarize.app.live_adapters import canonical_decode_token_cap

    paths = case_paths(passes_root, case, run)
    duration = CASE_DURATION_SEC.get(case, 60.0)
    snapshot_record, window_events = read_trace(paths["trace"])
    session = snapshot_record["snapshot"]["session"]
    audio = REPO / contract[case]["audio"]
    pcm = read_pcm(audio)
    audio_sha = hashlib.sha256(audio.read_bytes()).hexdigest()
    reference_transcript = lsa.load_reference_jsonl(REPO / contract[case]["reference"])
    reference_activity = lsa.load_reference_speaker_activity_jsonl(REPO / contract[case]["reference"])
    reference_v2 = [V2Segment(**row) for row in load_reference_rows(REPO / contract[case]["reference"])]

    s0_axes, s0_hypothesis = score_surface(
        snapshot_record=snapshot_record,
        session=session,
        reference_transcript=reference_transcript,
        reference_activity=reference_activity,
        duration=duration,
    )
    control = deployed_reference_axes(paths["results"], case)
    exported = [
        json.loads(line)
        for line in paths["live_hypothesis"].read_text().splitlines()
        if line.strip()
    ]
    export_matches = len(exported) == len(s0_hypothesis) and all(
        abs(item.start - row["start"]) < 1e-9
        and abs(item.end - row["end"]) < 1e-9
        and item.speaker == row["speaker"]
        and item.text == row["text"]
        for item, row in zip(s0_hypothesis, exported)
    )
    control_matches = all(
        abs(s0_axes[key] - control[key]) < 1e-6 for key in ("der", "speaker_accuracy", "wer")
    )

    canonical_speakers = tuple(session["identity_snapshot"]["canonical_speakers"])
    album = CausalAlbum(
        canonical_speakers=canonical_speakers,
        admission_seconds=rules["album_admission_seconds"],
        min_segment_samples=rules["min_segment_samples"],
        bank=bank,
        audio_sha=audio_sha,
        pcm=pcm,
    )
    spans = sorted(session["committed"], key=lambda span: span["start_sample"])
    resolved: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    witness_disagreements: list[dict[str, Any]] = []
    embed_started = bank.encode_seconds
    for window in sorted(window_events, key=lambda item: item["window_index"]):
        if not window.get("applied"):
            continue
        start, end = int(window["owned_start_sample"]), int(window["owned_end_sample"])
        album.feed_through(spans, end)
        transcript = decodes.transcript(
            audio_sha=audio_sha,
            audio_path=audio,
            pcm=pcm,
            start=start,
            end=end,
            token_cap=canonical_decode_token_cap(sample_count=end - start),
        )
        record = resolve_window(
            window=window,
            transcript=transcript,
            pcm=pcm,
            audio_sha=audio_sha,
            album=album,
            bank=bank,
            rules=rules,
        )
        violations.extend(d5_violations(record))
        resolved.append(record)
    encoder_seconds = bank.encode_seconds - embed_started

    s1_session, application = apply_s1(session, resolved)
    s1_axes, s1_hypothesis = score_surface(
        snapshot_record=snapshot_record,
        session=s1_session,
        reference_transcript=reference_transcript,
        reference_activity=reference_activity,
        duration=duration,
    )
    hop = base_span_seconds(paths["trace"].parent.parent / "replay-manifest.json")
    geometry_window = DEFAULT_ROLLING_GEOMETRY.window_samples / SAMPLE_RATE

    node: dict[str, Any] = {
        "duration_sec": duration,
        "canonical_speakers": list(canonical_speakers),
        "bench_control": {
            "export_reproduces_pass": export_matches,
            "s0_reproduces_deployed_scores": control_matches,
            "deployed": control,
        },
        "album": {
            "observations": album.observations,
            "references": [canonical for canonical, _ in album.references()],
        },
        "windows": resolved,
        "d5_violations": violations,
        "application": application,
        "witness_disagreements": witness_disagreements,
        "encoder_seconds": round(encoder_seconds, 6),
        "encoder_rtf": round(encoder_seconds / duration, 6),
        "arms": {},
    }
    for arm, axes, hypothesis in (("s0", s0_axes, s0_hypothesis), ("s1", s1_axes, s1_hypothesis)):
        v2_hypothesis = [
            V2Segment(start=item.start, end=item.end, speaker=item.speaker, text=item.text)
            for item in hypothesis
        ]
        scored = score_v2(
            reference_v2,
            v2_hypothesis,
            speech_regions=speech_regions,
            speech_regions_source="webrtcvad_mode1_10ms" if speech_regions else "reference_intervals",
        )
        node["arms"][arm] = dict(axes)
        node["arms"][arm]["matched_word_speaker_accuracy"] = scored["matched_word_speaker"][
            "matched_word_speaker_accuracy"
        ]
        node["arms"][arm]["unattributed"] = unattributed(v2_hypothesis)
        node["arms"][arm]["collapse_sliding"] = mixed_window_collapse(
            reference_v2, v2_hypothesis, duration, geometry_window, hop, ALBUM_BIRTH_MIN_SECONDS
        )
    return node


# ------------------------------------------------------------------ report


def summarize(report: dict) -> dict[str, Any]:
    def mean(values: Iterable[float | None]) -> float | None:
        usable = [value for value in values if value is not None]
        return round(sum(usable) / len(usable), 6) if usable else None

    def axis(case: str, arm: str, key: str) -> float | None:
        return mean(
            [
                (report["cases"][case]["runs"].get(run) or {}).get("arms", {}).get(arm, {}).get(key)
                for run in report["runs"]
            ]
        )

    trio = [case for case in report["cases"] if case in TRIO_CASES]
    summary: dict[str, Any] = {"per_case": {}, "trio_mean": {}}
    for case in report["cases"]:
        summary["per_case"][case] = {
            arm: {
                key: axis(case, arm, key)
                for key in ("der", "miss", "speaker_confusion", "speaker_accuracy", "wer", "matched_word_speaker_accuracy")
            }
            | {
                "unattributed_seconds": mean(
                    [
                        ((report["cases"][case]["runs"].get(run) or {})
                         .get("arms", {}).get(arm, {}).get("unattributed") or {}).get("seconds")
                        for run in report["runs"]
                    ]
                ),
                "collapsed_windows": mean(
                    [
                        ((report["cases"][case]["runs"].get(run) or {})
                         .get("arms", {}).get(arm, {}).get("collapse_sliding") or {}).get("collapsed_windows")
                        for run in report["runs"]
                    ]
                ),
            }
            for arm in ARMS
        }
        summary["per_case"][case]["der_delta_s1_minus_s0"] = (
            None
            if summary["per_case"][case]["s1"]["der"] is None
            else round(summary["per_case"][case]["s1"]["der"] - summary["per_case"][case]["s0"]["der"], 6)
        )
    for arm in ARMS:
        summary["trio_mean"][arm] = {
            key: mean([axis(case, arm, key) for case in trio])
            for key in ("der", "speaker_accuracy", "wer", "matched_word_speaker_accuracy")
        }
    if summary["trio_mean"]["s0"]["der"] is not None and summary["trio_mean"]["s1"]["der"] is not None:
        summary["trio_mean"]["der_delta_s1_minus_s0"] = round(
            summary["trio_mean"]["s1"]["der"] - summary["trio_mean"]["s0"]["der"], 6
        )
    return summary


def print_report(report: dict) -> None:
    print("\n== bench controls ==")
    for case, node in report["cases"].items():
        for run, run_node in node["runs"].items():
            control = run_node["bench_control"]
            print(
                f"  {case:<18} {run}  export_reproduces_pass={control['export_reproduces_pass']!s:<5} "
                f"s0_reproduces_deployed_scores={control['s0_reproduces_deployed_scores']}"
            )
    print("\n== D5 (G-M3-0): every embedding input inside one witness-owned local speaker interval ==")
    total = sum(
        len(run_node["d5_violations"])
        for node in report["cases"].values()
        for run_node in node["runs"].values()
    )
    embedded = sum(
        len(window["embedded_units"])
        for node in report["cases"].values()
        for run_node in node["runs"].values()
        for window in run_node["windows"]
    )
    print(f"  embedded units={embedded}  violations={total}")
    print("\n== per case (mean of runs) ==")
    header = (
        f"  {'case':<18} {'arm':<4} {'DER':>9} {'miss':>9} {'conf':>9} {'spk_acc':>9} "
        f"{'v2_word':>9} {'WER':>9} {'S00 s':>7} {'collapse':>8}"
    )
    print(header)
    for case, node in report["summary"]["per_case"].items():
        for arm in ARMS:
            row = node[arm]
            print(
                f"  {case:<18} {arm:<4} "
                + " ".join(
                    f"{(row[key] if row[key] is not None else float('nan')):>9.6f}"
                    for key in ("der", "miss", "speaker_confusion", "speaker_accuracy", "matched_word_speaker_accuracy", "wer")
                )
                + f" {(row['unattributed_seconds'] or 0.0):>7.2f} {(row['collapsed_windows'] or 0.0):>8.1f}"
            )
        print(f"  {'':<18} Δder(s1-s0) = {node['der_delta_s1_minus_s0']}")
    print("\n== trio mean ==")
    for arm in ARMS:
        row = report["summary"]["trio_mean"][arm]
        print(
            f"  {arm:<4} der={row['der']} speaker_accuracy={row['speaker_accuracy']} "
            f"v2_word={row['matched_word_speaker_accuracy']} wer={row['wer']}"
        )
    print(f"  Δder(s1-s0) = {report['summary']['trio_mean'].get('der_delta_s1_minus_s0')}")
    print("\n== witness resolution ==")
    for case, node in report["cases"].items():
        for run, run_node in node["runs"].items():
            application = run_node["application"]
            abstentions = [
                window["abstention"] for window in run_node["windows"] if window["abstention"]
            ]
            unmapped = sum(len(window["unmapped_locals"]) for window in run_node["windows"])
            print(
                f"  {case:<18} {run}  windows={application['windows']} "
                f"relabelled={application['segments_relabelled']} "
                f"kept_projection={application['segments_left_to_projection']} "
                f"unmapped_locals={unmapped} abstentions={len(abstentions)} "
                f"witness==surface {application['windows_witness_matches_surface']}/{application['windows']} "
                f"encoder_rtf={run_node['encoder_rtf']}"
            )
    print("\n== what the remaining confusion is (post-hoc; no arm reads truth) ==")
    for case, node in report["cases"].items():
        for run, run_node in node["runs"].items():
            for arm in ARMS:
                attribution = run_node["arms"][arm]["confusion_attribution"]
                print(
                    f"  {case:<18} {run} {arm:<3} confused={attribution['confused_seconds']:>6.2f}s "
                    f"{json.dumps(attribution['seconds_by_class'])}"
                )
    print("\n== cost ==")
    print(f"  embeddings: {json.dumps(report['embedding_accounting'])}")
    print(f"  witness decodes: {json.dumps(report['decode_accounting'])}")


# ------------------------------------------------------------------ selftest


def selftest() -> int:
    """Prove the derived quantities react before any of them is believed.

    Four checks, each over the smallest object that can carry the mistake it names.
    """

    failures: list[str] = []

    # 1. D5 catches context audio, a padded interval, and mixed-speaker audio.
    window = {
        "window_index": 0,
        "start_sample": 0,
        "end_sample": 160000,
        "segments": [
            {"start_sample": 0, "end_sample": 80000, "local_speaker": "S01", "text": "a"},
            {"start_sample": 80000, "end_sample": 160000, "local_speaker": "S02", "text": "b"},
        ],
        "embedded_units": [
            {"local_speaker": "S01", "intervals_samples": [[0, 80000]]},
        ],
    }
    if d5_violations(window):
        failures.append("d5: a clean witness-owned interval was reported as a violation")
    for mutated, reason in (
        ([[-8000, 80000]], "prefix context"),
        ([[0, 120000]], "audio of two local speakers"),
        ([[16000, 96000]], "an interval crossing into the next speaker"),
    ):
        probe = dict(window, embedded_units=[{"local_speaker": "S01", "intervals_samples": mutated}])
        if not d5_violations(probe):
            failures.append(f"d5: {reason} was not reported")

    # 2. The label application changes exactly the segments the mapping answers for.
    session = {
        "effective_transcript": [
            {"start_sample": 0, "end_sample": 40000, "text": "one", "canonical_speaker": "speaker-0001", "authority": "rolling"},
            {"start_sample": 40000, "end_sample": 80000, "text": "two", "canonical_speaker": "speaker-0001", "authority": "rolling"},
            {"start_sample": 160000, "end_sample": 200000, "text": "three", "canonical_speaker": "speaker-0001", "authority": "provisional"},
        ]
    }
    resolved = [
        {
            "window_index": 0,
            "start_sample": 0,
            "end_sample": 160000,
            "mapping": {"S02": "speaker-0002"},
            "segments": [
                {"start_sample": 0, "end_sample": 40000, "local_speaker": "S01", "text": "one"},
                {"start_sample": 40000, "end_sample": 80000, "local_speaker": "S02", "text": "two"},
            ],
        }
    ]
    revised, application = apply_s1(session, resolved)
    surface = revised["effective_transcript"]
    if surface[0]["canonical_speaker"] != "speaker-0001":
        failures.append("apply_s1: an unmapped local speaker lost the projection's answer")
    if surface[1]["canonical_speaker"] != "speaker-0002":
        failures.append("apply_s1: a mapped local speaker did not take the witness's answer")
    if surface[2]["canonical_speaker"] != "speaker-0001":
        failures.append("apply_s1: a provisional (non-rolling) segment was relabelled")
    if application["segments_relabelled"] != 1 or application["segments_left_to_projection"] != 1:
        failures.append(f"apply_s1: accounting is wrong: {application}")

    # 3. The album holds back the span whose vectors production has not reconciled yet.
    class _Bank:
        hits = misses = 0
        encode_seconds = encoded_audio_seconds = 0.0

        by_tag: dict = {}

        def embed(self, **kwargs):
            return (1.0, 0.0), True

    album = CausalAlbum(
        canonical_speakers=("speaker-0001",),
        admission_seconds=2.0,
        min_segment_samples=8000,
        bank=_Bank(),
        audio_sha="x",
        pcm=b"\x00" * 400000,
    )
    spans = [
        {"span_id": index, "start_sample": index * 40000, "end_sample": (index + 1) * 40000,
         "transcript": "[0.00][S01]hello there friend[2.50]", "revised_transcript": None}
        for index in range(3)
    ]
    album.feed_through(spans, 40000)
    if album.observations:
        failures.append("album: the only committed span was observed while its vectors were pending")
    album.feed_through(spans, 120000)
    if [item["span_id"] for item in album.observations] != [0, 1]:
        failures.append(f"album: wrong spans reconciled at 120000: {album.observations}")

    # 4. An unattributed published label never enters the album.
    album2 = CausalAlbum(
        canonical_speakers=("speaker-0001",),
        admission_seconds=2.0,
        min_segment_samples=8000,
        bank=_Bank(),
        audio_sha="x",
        pcm=b"\x00" * 400000,
    )
    silent = [
        {"span_id": index, "start_sample": index * 40000, "end_sample": (index + 1) * 40000,
         "transcript": f"[0.00][{UNATTRIBUTED_SPEAKER}]hello there friend[2.50]", "revised_transcript": None}
        for index in range(3)
    ]
    album2.feed_through(silent, 120000)
    if album2.observations:
        failures.append("album: an S00 span was enrolled as a canonical speaker")

    for failure in failures:
        print(f"FAIL {failure}")
    print(f"selftest: {len(failures)} failures")
    return 1 if failures else 0


# ------------------------------------------------------------------ main


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--passes-root", type=Path, default=DEFAULT_PASSES)
    parser.add_argument("--cases", default=",".join(TRIO_CASES))
    parser.add_argument("--runs", default=",".join(RUNS))
    parser.add_argument("--decode-cache", type=Path, default=DEFAULT_DECODE_CACHE)
    parser.add_argument("--embed-cache", type=Path, default=DEFAULT_EMBED_CACHE)
    parser.add_argument("--manifest", type=Path, default=DEPLOYED_MANIFEST)
    parser.add_argument("--model", default="OpenMOSS-Team/MOSS-Transcribe-Diarize")
    parser.add_argument("--allow-decode", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--selftest", action="store_true")
    cli = parser.parse_args()
    if cli.selftest:
        return selftest()

    rules = deployed_rules(cli.manifest)
    bank = EmbeddingBank(onnx=rules["onnx"], cache_path=cli.embed_cache)
    decodes = WitnessDecodes(
        cache_path=cli.decode_cache, model=cli.model, allow_decode=cli.allow_decode
    )
    contract = corpus_contract()
    cases = [case.strip() for case in cli.cases.split(",") if case.strip()]
    runs = [run.strip() for run in cli.runs.split(",") if run.strip()]
    report: dict[str, Any] = {
        "passes_root": str(cli.passes_root),
        "runs": runs,
        "rules": {
            "manifest": rules["manifest"],
            "onnx_sha256": rules["onnx_sha256"],
            "min_segment_samples": rules["min_segment_samples"],
            "album_admission_seconds": rules["album_admission_seconds"],
            "birth_min_seconds": rules["birth_min_seconds"],
            "min_match_score": rules["identity_config"].min_match_score,
            "min_match_margin": rules["identity_config"].min_match_margin,
            "max_speakers": rules["identity_config"].max_speakers,
            "rolling_window_samples": DEFAULT_ROLLING_GEOMETRY.window_samples,
            "rolling_stride_samples": DEFAULT_ROLLING_GEOMETRY.stride_samples,
        },
        "cases": {},
    }
    for case in cases:
        if case not in contract:
            raise BenchRefusal(f"unknown case: {case}")
        audio = REPO / contract[case]["audio"]
        regions = speech_regions_from_wav(audio) if audio.exists() else None
        node: dict[str, Any] = {"runs": {}}
        for run in runs:
            started = time.monotonic()
            node["runs"][run] = run_case(
                case=case,
                run=run,
                passes_root=cli.passes_root,
                contract=contract,
                rules=rules,
                bank=bank,
                decodes=decodes,
                speech_regions=regions,
            )
            print(
                f"[{case} {run}] scored in {time.monotonic() - started:.1f}s  "
                f"s0 der={node['runs'][run]['arms']['s0']['der']:.6f} "
                f"s1 der={node['runs'][run]['arms']['s1']['der']:.6f}",
                flush=True,
            )
            bank.save()
        report["cases"][case] = node
    report["embedding_accounting"] = bank.accounting()
    report["decode_accounting"] = decodes.accounting()
    report["summary"] = summarize(report)
    print_report(report)
    if cli.output:
        cli.output.parent.mkdir(parents=True, exist_ok=True)
        cli.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"\nwrote {cli.output}")

    controls_ok = all(
        run_node["bench_control"]["export_reproduces_pass"]
        and run_node["bench_control"]["s0_reproduces_deployed_scores"]
        for node in report["cases"].values()
        for run_node in node["runs"].values()
    )
    violations = sum(
        len(run_node["d5_violations"])
        for node in report["cases"].values()
        for run_node in node["runs"].values()
    )
    print(f"\nbench_controls_pass={controls_ok} d5_violations={violations}")
    return 0 if controls_ok and violations == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BenchRefusal as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        raise SystemExit(2)
