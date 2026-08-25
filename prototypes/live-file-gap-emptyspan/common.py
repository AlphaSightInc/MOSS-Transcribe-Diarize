"""Shared helpers for the H3 empty-span investigation (throwaway prototype)."""
from __future__ import annotations

import json
import math
import sys
import wave
from dataclasses import dataclass
from pathlib import Path

REPO = Path("/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize")
BASELINE = Path(
    "/private/tmp/claude-501/-Users-gao-Desktop-AI-Projects-Github-Projects-MOSS-Transcribe-Diarize"
    "/bd3632af-da27-408f-8e03-ecd56a586e8d/scratchpad/remeasure-20260824T160130"
)
HERE = Path(__file__).resolve().parent
SR = 16000
TRIO = ("lex_bill_ackman", "lex_javier_milei", "lex_keyu_jin")
SECONDARY = ("acquired_jamie_dimon",)
CORPUS_1MIN = REPO / "prototypes/streaming-diarization/data/real/benchmark_diarization_1min/samples"
CORPUS_3MIN = REPO / "prototypes/streaming-diarization/data/real/calibration_diarization_3min/samples"

sys.path.insert(0, str(REPO))


def case_dir(case: str) -> Path:
    for root in (CORPUS_1MIN, CORPUS_3MIN):
        if (root / case).is_dir():
            return root / case
    raise FileNotFoundError(case)


@dataclass(frozen=True)
class Span:
    case: str
    span_id: int
    start_sample: int
    end_sample: int
    reason: str
    empty_reason: str | None
    transcript: str

    @property
    def start_s(self) -> float:
        return self.start_sample / SR

    @property
    def end_s(self) -> float:
        return self.end_sample / SR

    @property
    def dur_s(self) -> float:
        return (self.end_sample - self.start_sample) / SR

    @property
    def key(self) -> str:
        return f"{self.case}#{self.span_id}"


def load_spans(case: str) -> list[Span]:
    path = BASELINE / case / "live/run-001/trace.jsonl"
    frozen: dict[int, dict] = {}
    processed: dict[int, dict] = {}
    committed: dict[int, dict] = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("kind") == "service_event" and isinstance(rec.get("event"), dict):
            ev = rec["event"]
            payload = ev.get("payload") or {}
            if ev.get("kind") == "span_frozen":
                frozen[payload["span_id"]] = payload
            elif ev.get("kind") == "canonical_processed":
                processed[payload["span_id"]] = payload
        elif rec.get("kind") == "terminal":
            for item in rec["snapshot"]["session"].get("committed", []):
                committed[item["span_id"]] = item
    # The terminal snapshot is authoritative: the final span is frozen by stop-flush after the
    # last `span_frozen` event is traced, so `frozen` misses it in every run that ends mid-span.
    spans = []
    for span_id in sorted(committed):
        c = committed[span_id]
        f = frozen.get(span_id, {})
        p = processed.get(span_id, {})
        spans.append(
            Span(
                case=case,
                span_id=span_id,
                start_sample=c["start_sample"],
                end_sample=c["end_sample"],
                reason=f.get("reason", "stop_flush(untraced)"),
                empty_reason=p.get("empty_reason"),
                transcript=c.get("transcript") or "",
            )
        )
    return spans


def read_pcm(case: str) -> bytes:
    with wave.open(str(case_dir(case) / "audio.wav"), "rb") as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getframerate() == SR
        return w.readframes(w.getnframes())


def write_wav(path: Path, pcm: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)


def slice_pcm(pcm: bytes, start_sample: int, end_sample: int) -> bytes:
    start_sample = max(0, start_sample)
    end_sample = min(len(pcm) // 2, end_sample)
    return pcm[start_sample * 2 : end_sample * 2]


def rms_dbfs(pcm: bytes) -> tuple[float, float]:
    import numpy as np

    x = np.frombuffer(pcm, dtype="<i2").astype("float64") / 32768.0
    if x.size == 0:
        return (-999.0, -999.0)
    rms = math.sqrt(float((x * x).mean()))
    peak = float(abs(x).max())
    to_db = lambda v: 20.0 * math.log10(v) if v > 0 else -999.0
    return (to_db(rms), to_db(peak))


def vad_speech_ratio(pcm: bytes, *, mode: int = 1, frame_samples: int = 160) -> float:
    """Deployed live VAD settings: webrtcvad mode 1, 10 ms frames at 16 kHz."""
    import webrtcvad

    vad = webrtcvad.Vad(mode)
    fb = frame_samples * 2
    n = len(pcm) // fb
    if n == 0:
        return 0.0
    voiced = sum(1 for i in range(n) if vad.is_speech(pcm[i * fb : (i + 1) * fb], SR))
    return voiced / n


def load_reference(case: str):
    from moss_transcribe_diarize.evaluation import Segment

    segs = []
    for line in (case_dir(case) / "reference.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        segs.append(Segment(float(r["start"]), float(r["end"]), str(r["speaker"]), str(r["text"])))
    return segs


def load_hyp(path: Path):
    from moss_transcribe_diarize.evaluation import Segment

    segs = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        segs.append(Segment(float(r["start"]), float(r["end"]), str(r["speaker"]), str(r["text"])))
    return segs


def dump_hyp(path: Path, segs) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for s in sorted(segs, key=lambda s: (s.start, s.end, s.speaker, s.text)):
            fh.write(json.dumps({"start": s.start, "end": s.end, "speaker": s.speaker, "text": s.text}) + "\n")


def tbsa(case: str, hyp):
    from moss_transcribe_diarize.evaluation import calculate_tbsa

    return calculate_tbsa(load_reference(case), hyp)


def make_runner():
    from moss_transcribe_diarize.app.vllm_runner import VllmRunner

    return VllmRunner(base_url="http://127.0.0.1:18000/v1", model="OpenMOSS-Team/MOSS-Transcribe-Diarize")


def raw_decode(wav_path: Path, *, sample_count: int, prompt: str | None = None, token_cap: int | None = None):
    """Same request as the live path, but returns what the model *actually* emitted.

    `VllmRunner.transcribe` raises `EmptyTranscriptionError` for three different endings --
    zero generated tokens, empty text, unparseable text -- and the live path cannot tell them
    apart. This bypasses that validation so the diagnosis can.
    """
    import time

    from moss_transcribe_diarize.app.live_adapters import canonical_decode_token_cap
    from moss_transcribe_diarize.app.vllm_runner import _media_to_wav_bytes
    from moss_transcribe_diarize.inference_utils import DEFAULT_PROMPT
    from moss_transcribe_diarize.transcript_parser import parse_transcript

    cap = token_cap if token_cap is not None else canonical_decode_token_cap(sample_count=sample_count)
    runner = make_runner()
    fields = runner._build_fields(
        prompt=(prompt if prompt is not None else DEFAULT_PROMPT),
        max_new_tokens=cap,
        decoding="greedy",
        temperature=None,
    )
    started = time.monotonic()
    response = runner._post_multipart(
        runner._transcriptions_url(),
        fields=fields,
        file_field="file",
        filename="audio.wav",
        content_type="audio/wav",
        file_bytes=_media_to_wav_bytes(wav_path),
        max_new_tokens=cap,
    )
    elapsed = time.monotonic() - started
    text = response.get("text")
    text = text if isinstance(text, str) else ""
    usage = response.get("usage") or {}
    segs = parse_transcript(text.strip()) if text.strip() else []
    return {
        "raw_text": text,
        "stripped": text.strip(),
        "generated_tokens": int(usage.get("completion_tokens") or 0),
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "parsed_segments": len(segs),
        "elapsed_s": round(elapsed, 3),
        "token_cap": cap,
        "live_would_be_empty": (
            int(usage.get("completion_tokens") or 0) <= 0 or not text.strip() or not segs
        ),
    }


def live_decode(wav_path: Path, *, sample_count: int, prompt: str | None = None):
    """Exact live-path request shape: greedy, token cap = 68 + ceil(86.4 * seconds).

    Returns (text, generated_tokens, elapsed_sec, token_cap, empty_flag).
    """
    from moss_transcribe_diarize.app.live_adapters import canonical_decode_token_cap
    from moss_transcribe_diarize.inference_utils import DEFAULT_PROMPT
    from moss_transcribe_diarize.app.transcription_outcome import EmptyTranscriptionError

    import time

    cap = canonical_decode_token_cap(sample_count=sample_count)
    runner = make_runner()
    kwargs = {"max_new_tokens": cap, "decoding": "greedy"}
    if prompt is not None:
        kwargs["prompt"] = prompt
    started = time.monotonic()
    try:
        result = runner.transcribe(wav_path, **kwargs)
    except EmptyTranscriptionError as exc:
        return ("", 0, time.monotonic() - started, cap, str(exc))
    return (
        str(result.text),
        int(result.generated_tokens or 0),
        time.monotonic() - started,
        cap,
        None,
    )
