#!/usr/bin/env python3
"""Settle D-c's second half: does a CAPPED span still commit its words?

WHY THIS EXISTS
Iteration 24 measured what the cap costs in wall clock -- 8.129 s at the pre-D-c 2048 bound
against 1.074 s at the deployed cap of 286 -- but recorded, as limitation (c), that it could
NOT verify the other half of the D-c ruling. Its trigger (`temperature=2.0`) produced output
that is unparseable at *any* length, so the capped and the uncapped decode both committed
empty and there were no words either way. That half of D-c still rested on the unit tests.

F1's real runaways were a different shape and are still on disk: well-formed
`[t][Sxx]text[t]` fragment loops, 2024 / 2019 generated tokens, committed in full because
the only bound then in force was `VllmRunner.transcribe`'s 2048 default. Those transcripts
are exactly the input the ruling is about, and they are what this probe truncates.

WHY THIS IS MEASURABLE WITHOUT THE CAPTURE MAC AND WITHOUT RE-RUNNING THE ENGINE
The live decode is greedy: `VllmRunner._build_fields` sends `temperature` 0.0 unless the
caller asks for `decoding="sample"`, and the live path never does. So the token sequence a
decode produces under a cap of N is the N-token PREFIX of the sequence the same decode
produced under 2048 -- the cap changes when generation stops, not what it generates. The
transcript a capped decode would have returned is therefore

    detokenize(tokenize(<the uncapped transcript>)[:cap])

computed with the DEPLOYED decoder's own tokenizer (the same `/tokenize` endpoint iteration
16 derived the cap with and iteration 23 checked its headroom with), never with a guess at
where the boundary falls.

TWO MEASUREMENTS, AND THE SECOND IS THE ONE THAT GENERALISES
  (1) AT THE CAP -- truncate each recorded runaway at the product's own
      `canonical_decode_token_cap(sample_count=<that span's own count>)`, imported rather
      than restated, and run the result through the real live path.
  (2) AT EVERY CUT POINT -- the token boundary is one cut out of thousands and the next
      runaway will not land on the same one, so every character prefix is classified too.
      The durable claim is about the shape of the parse, not about one number.

WHAT "THE REAL LIVE PATH" MEANS HERE
The product's own classification chain, not a restatement of it:
`LiveCoordinator.prepare_work_item` -> `_empty_transcript_reason` ->
`BoundedCausalIdentityPreparer.prepare` -> `LiveCoordinator.submit_prepared_work` ->
`LiveSession.submit_*`. Only the decoder is stubbed, and only so it returns the truncated
text -- which is the quantity under test. Note this is deliberately NOT
`LiveProvider.decode_canonical` / `_validated_segments`: that seam belongs to the batch
provider, and reading it instead of the coordinator's would answer a question about code the
live meeting never runs.

READ-ONLY. Creates no device, no session, no pairing, no file on any host. Makes at most two
HTTP calls to the resident vLLM's tokenizer routes, which do no GPU work.

USAGE
  python3 decode-cap-truncation-probe.py --spans-json <file|-> [--checkout <path>]
      [--tokenizer-url http://127.0.0.1:8000] [--model <name>] [--sweep-stride 1]

  --spans-json takes `[{"span_id":.., "sample_count":.., "transcript":".."}, ...]`; the
  companion `--evidence-dir` reads them straight out of a canary/F1 `snapshot.tsv`.
  Without --tokenizer-url only measurement (2) runs, which needs no host at all.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path


# --------------------------------------------------------------------------------------
# Product imports. The probe imports the product's own cap function and its own coordinator
# rather than restating either, so a probe that drifts from the service fails loudly here
# instead of quietly measuring itself (iteration 23's lesson, one costume further on).
# --------------------------------------------------------------------------------------
def _load_product(checkout: Path):
    sys.path.insert(0, str(checkout))
    from moss_transcribe_diarize.app.live_adapters import (  # noqa: E402
        InferenceTranscript,
        canonical_decode_token_cap,
    )
    from moss_transcribe_diarize.app.live_arbiter import InferenceArbiter  # noqa: E402
    from moss_transcribe_diarize.app.live_coordinator import LiveCoordinator  # noqa: E402
    from moss_transcribe_diarize.app.live_endpoint import (  # noqa: E402
        EndpointPolicy,
        EndpointPolicyConfig,
        SpeechObservation,
    )
    from moss_transcribe_diarize.app.live_identity import (  # noqa: E402
        BoundedCausalIdentityPreparer,
        LiveIdentityConfig,
    )
    from moss_transcribe_diarize.app.live_session import AudioFrame, LiveSession  # noqa: E402
    from moss_transcribe_diarize.app.live_span_bounds import span_segments  # noqa: E402

    return {
        "span_segments": span_segments,
        "InferenceTranscript": InferenceTranscript,
        "canonical_decode_token_cap": canonical_decode_token_cap,
        "LiveCoordinator": LiveCoordinator,
        "EndpointPolicy": EndpointPolicy,
        "EndpointPolicyConfig": EndpointPolicyConfig,
        "BoundedCausalIdentityPreparer": BoundedCausalIdentityPreparer,
        "LiveIdentityConfig": LiveIdentityConfig,
        "InferenceArbiter": InferenceArbiter,
        "AudioFrame": AudioFrame,
        "LiveSession": LiveSession,
        "SpeechObservation": SpeechObservation,
    }


# Deployed contract values, named so a reader can check them against prd.md's list.
LIVE_SAMPLE_RATE = 16000
DEPLOYED_HARD_CAP_SAMPLES = 40000       # 2.5 s
DEPLOYED_MIN_SILENCE_SAMPLES = 8000     # 0.5 s
DEPLOYED_MAX_RETAINED_SAMPLES = 960000  # 60 s
DEPLOYED_MAX_IDENTITY_SPEAKERS = 16
DEPLOYED_MIN_MATCH_SCORE = 0.5
DEPLOYED_MIN_MATCH_MARGIN = 0.1


def _classify_through_live_path(product, *, transcript: str, sample_count: int) -> dict:
    """Run one candidate transcript through the coordinator and name what the meeting does.

    Returns the outcome as the product decided it, never as this probe would have. The four
    outcomes are the only four the live path has, and the third amendment's rule is that the
    last of them must not be reachable from a truncation.
    """

    P = product

    class _TruncatedDecoder:
        max_samples = DEPLOYED_HARD_CAP_SAMPLES

        def transcribe_pcm(self, *, span, pcm):
            del span, pcm
            return P["InferenceTranscript"](
                transcript=transcript,
                generated_tokens=1,
                elapsed_sec=0.0,
                token_cap=1,
                capped=True,
            )

    class _AlwaysSilent:
        """One observation per accepted range; silence, so the endpointer closes the span."""

        def observe(self, *, frame, start_sample, end_sample):
            del frame
            return (
                P["SpeechObservation"](
                    start_sample=start_sample,
                    end_sample=end_sample,
                    speech_present=False,
                ),
            )

    coordinator = P["LiveCoordinator"](
        session_key="dc-truncation-probe",
        session=P["LiveSession"](max_retained_samples=DEPLOYED_MAX_RETAINED_SAMPLES),
        endpoint_policy=P["EndpointPolicy"](
            P["EndpointPolicyConfig"](
                min_speech_samples=1600,
                min_silence_samples=DEPLOYED_MIN_SILENCE_SAMPLES,
                hard_cap_samples=None,
            )
        ),
        speech_provider=_AlwaysSilent(),
        decoder=_TruncatedDecoder(),
        identity_preparer=P["BoundedCausalIdentityPreparer"](
            config=P["LiveIdentityConfig"](
                max_speakers=DEPLOYED_MAX_IDENTITY_SPEAKERS,
                min_match_score=DEPLOYED_MIN_MATCH_SCORE,
                min_match_margin=DEPLOYED_MIN_MATCH_MARGIN,
            )
        ),
        arbiter=P["InferenceArbiter"](),
    )

    try:
        coordinator.accept_frame(
            P["AudioFrame"](
                sequence=0,
                pcm=b"\x11\x22" * sample_count,
                sample_count=sample_count,
                sample_rate=LIVE_SAMPLE_RATE,
            )
        )
        item_ids = coordinator.flush_endpoint()
        if len(item_ids) != 1:
            return {"outcome": "no_span_frozen", "detail": f"{len(item_ids)} work items"}
        work = coordinator.capture_work_item(coordinator.arbiter.next_work())
        prepared = coordinator.prepare_work_item(work)
        result = coordinator.submit_prepared_work(prepared)
    except BaseException as exc:  # noqa: BLE001 -- naming the escape IS the measurement
        return {
            "outcome": "raised",
            "exception": type(exc).__name__,
            "message": str(exc)[:200],
        }

    snapshot = coordinator.session.snapshot()
    committed = [span for span in snapshot.committed if span.span_id == prepared.span.id]
    published = committed[0].transcript if committed else ""
    segments = product["span_segments"](published, sample_count=sample_count)
    # Alphanumeric, not merely non-empty: F1's runaway fragments carry the literal text
    # "..." , which is three characters of nothing. Counting raw length would score a
    # content-free fragment loop as a span that kept its words.
    word_chars = sum(sum(1 for ch in segment.text if ch.isalnum()) for segment in segments)
    if not result.submitted:
        outcome = "not_submitted"
    elif word_chars > 0:
        outcome = "committed_with_words"
    elif published.strip():
        # Segments survived but every one of them is empty of speech. D-c's ruling is about
        # *words*, so this is deliberately not counted as one: F1's own runaways are
        # `[t][Sxx]...[t]` fragment loops and hold no transcript content at any length.
        outcome = "committed_without_words"
    else:
        outcome = "committed_empty"
    return {
        "outcome": outcome,
        "empty_reason": prepared.empty_reason,
        "identity_status": result.identity_status,
        "identity_reason": result.identity_reason,
        "published_chars": len(published),
        "published_segments": len(segments),
        "published_word_chars": word_chars,
        "published": published,
        "committed_samples": snapshot.committed_samples,
    }


def _post_json(url: str, payload: dict, timeout: float = 30.0) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _tokenize(base: str, model: str, text: str) -> list[int]:
    answer = _post_json(
        base.rstrip("/") + "/tokenize",
        {"model": model, "prompt": text, "add_special_tokens": False},
    )
    return list(answer.get("tokens") or [])


def _detokenize(base: str, model: str, tokens: list[int]) -> str:
    answer = _post_json(
        base.rstrip("/") + "/detokenize",
        {"model": model, "tokens": tokens},
    )
    return str(answer.get("prompt", ""))


def _sweep(product, *, transcript: str, sample_count: int, stride: int) -> dict:
    counts: dict[str, int] = {}
    first_cut: dict[str, int] = {}
    last_cut: dict[str, int] = {}
    escapes: list[dict] = []
    first_words_cut = None
    for cut in range(1, len(transcript) + 1, stride):
        verdict = _classify_through_live_path(
            product, transcript=transcript[:cut], sample_count=sample_count
        )
        key = verdict["outcome"]
        if key == "raised":
            key = f"raised:{verdict['exception']}"
            if len(escapes) < 5:
                escapes.append({"cut": cut, **verdict})
        counts[key] = counts.get(key, 0) + 1
        first_cut.setdefault(key, cut)
        last_cut[key] = cut
        if first_words_cut is None and verdict["outcome"] == "committed_with_words":
            first_words_cut = cut
    return {
        "cuts_examined": sum(counts.values()),
        "stride": stride,
        "counts": counts,
        "first_cut": first_cut,
        "last_cut": last_cut,
        "first_cut_that_commits_words": first_words_cut,
        "escapes": escapes,
        "terminal_or_unclassified_cuts": sum(
            value for key, value in counts.items() if key.startswith("raised:") or key == "not_submitted"
        ),
    }


def _spans_from_evidence_dir(directory: Path) -> list[dict]:
    """Committed spans out of a canary/F1 `snapshot.tsv`, from its last 200 body."""

    rows = []
    for line in (directory / "snapshot.tsv").read_text().splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3 and parts[1] == "200":
            rows.append(parts[2])
    if not rows:
        raise SystemExit(f"no 200 snapshot rows in {directory}/snapshot.tsv")
    best: list[dict] = []
    for row in rows:
        committed = json.loads(row)["snapshot"]["session"].get("committed") or []
        if len(committed) > len(best):
            best = committed
    return [
        {
            "span_id": span["span_id"],
            "sample_count": span["end_sample"] - span["start_sample"],
            "transcript": span["transcript"],
        }
        for span in best
    ]


def _wordy_runaway(product, spans: list[dict], *, sample_count: int, target_chars: int) -> dict:
    """A runaway built from the evidence's OWN real speech, so "its words" is not vacuous.

    F1's two recorded runaways are `[t][Sxx]...[t]` loops: hundreds of fragments holding no
    transcript content whatsoever. Truncating one therefore cannot demonstrate that a capped
    span keeps its words -- there were none, at any length. That is the same trap iteration
    24 fell into from the other side, and naming it is not the same as escaping it.

    So this builds the shape F1 measured -- a degenerate loop of fragments oscillating inside
    a narrow timestamp band, alternating between two local speakers -- and fills it with the
    fragment texts the SAME run really transcribed. The result is the input D-c's ruling is
    actually about: a decode long enough for the cap to bite, whose every fragment holds
    words the meeting would lose if truncation broke the parse.
    """

    words: list[str] = []
    for span in spans:
        for segment in product["span_segments"](span["transcript"], sample_count=span["sample_count"]):
            text = segment.text.strip()
            if text:
                words.append(text)
    if not words:
        raise SystemExit("no span in the evidence holds transcribed words; cannot synthesize")

    duration = sample_count / LIVE_SAMPLE_RATE
    pieces: list[str] = []
    index = 0
    while sum(len(piece) for piece in pieces) < target_chars:
        start = round(0.05 + (index % 20) * 0.01, 2)
        end = round(start + 0.2, 2)
        speaker = f"S{(index % 2) + 6:02d}"
        pieces.append(f"[{min(start, duration)}][{speaker}]{words[index % len(words)]}[{min(end, duration)}]")
        index += 1
    return {
        "span_id": -1,
        "sample_count": sample_count,
        "transcript": "".join(pieces),
        "synthesized_from": len(words),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--spans-json", help="file of [{span_id, sample_count, transcript}], or - for stdin")
    source.add_argument("--evidence-dir", help="a canary/F1 evidence directory holding snapshot.tsv")
    parser.add_argument("--checkout", default=".", help="checkout to import the product from")
    parser.add_argument("--tokenizer-url", default=None, help="e.g. http://127.0.0.1:8000 (enables the cap measurement)")
    parser.add_argument("--model", default="OpenMOSS-Team/MOSS-Transcribe-Diarize")
    parser.add_argument("--min-chars", type=int, default=1000, help="only examine spans at least this long")
    parser.add_argument("--span", type=int, action="append", default=None, help="restrict to these span ids")
    parser.add_argument(
        "--synthesize-wordy-runaway",
        type=int,
        default=0,
        metavar="CHARS",
        help="also examine a runaway of this many characters built from the evidence's own transcribed words",
    )
    parser.add_argument("--sweep-stride", type=int, default=1)
    parser.add_argument("--no-sweep", action="store_true")
    parser.add_argument("--out", default=None, help="write the JSON report here as well as to stdout")
    args = parser.parse_args()

    checkout = Path(args.checkout).expanduser().resolve()
    product = _load_product(checkout)
    cap_of = product["canonical_decode_token_cap"]

    if args.evidence_dir:
        spans = _spans_from_evidence_dir(Path(args.evidence_dir).expanduser())
    else:
        raw = sys.stdin.read() if args.spans_json == "-" else Path(args.spans_json).read_text()
        spans = json.loads(raw)

    selected = [
        span
        for span in spans
        if (args.span is None or span["span_id"] in args.span)
        and len(span["transcript"]) >= args.min_chars
    ]
    if args.synthesize_wordy_runaway > 0:
        selected.append(
            _wordy_runaway(
                product,
                spans,
                sample_count=DEPLOYED_HARD_CAP_SAMPLES,
                target_chars=args.synthesize_wordy_runaway,
            )
        )
    if not selected:
        raise SystemExit("no span matched the selection; nothing to measure")

    report: dict = {
        "checkout": str(checkout),
        "cap_source": "product-function",
        "tokenizer_url": args.tokenizer_url,
        "spans": [],
    }

    for span in selected:
        sample_count = int(span["sample_count"])
        full = span["transcript"]
        cap = cap_of(sample_count=sample_count)
        entry: dict = {
            "span_id": span["span_id"],
            "sample_count": sample_count,
            "duration_sec": round(sample_count / LIVE_SAMPLE_RATE, 4),
            "token_cap": cap,
            "full_chars": len(full),
            "full": _classify_through_live_path(product, transcript=full, sample_count=sample_count),
        }
        entry["full"].pop("published", None)

        if args.tokenizer_url:
            tokens = _tokenize(args.tokenizer_url, args.model, full)
            entry["full_tokens"] = len(tokens)
            entry["cap_bites"] = len(tokens) > cap
            if entry["cap_bites"]:
                truncated = _detokenize(args.tokenizer_url, args.model, tokens[:cap])
                verdict = _classify_through_live_path(
                    product, transcript=truncated, sample_count=sample_count
                )
                verdict.pop("published", None)
                entry["at_cap"] = {
                    "truncated_chars": len(truncated),
                    "truncated_tail": truncated[-60:],
                    "round_trips": _tokenize(args.tokenizer_url, args.model, truncated)[: cap] == tokens[:cap],
                    **verdict,
                }
            else:
                entry["at_cap"] = {"skipped": "the recorded transcript is already under the cap"}

        if not args.no_sweep:
            entry["sweep"] = _sweep(
                product,
                transcript=full,
                sample_count=sample_count,
                stride=max(1, args.sweep_stride),
            )
        report["spans"].append(entry)

    report["verdict"] = {
        "spans_examined": len(report["spans"]),
        "any_cut_terminal_or_unclassified": any(
            entry.get("sweep", {}).get("terminal_or_unclassified_cuts", 0) > 0
            for entry in report["spans"]
        ),
        "at_cap_outcomes": [
            entry.get("at_cap", {}).get("outcome")
            for entry in report["spans"]
            if "at_cap" in entry
        ],
    }

    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.out:
        Path(args.out).expanduser().write_text(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
