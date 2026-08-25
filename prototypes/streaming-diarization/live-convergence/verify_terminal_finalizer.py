#!/usr/bin/env python3
"""Handed the paired file arm's own decode, does the terminal adapter publish the file arm's surface?

Plan E4's prize is arithmetic: terminal replaces the rolling surface with a 150/120 pass over
the same audio, which on the trio is the *same call* file mode makes, so trio mean WER goes
`.131357 -> .103946` if it lands. Two very different things can stop it landing -- the decoder
(measured non-deterministic, M0d/R3) or the adapter between the tape and the session. This
verifier isolates the second and answers it exactly:

    the meeting, frame by frame, through the real runtime   (verify_runtime_rolling.run_case)
      -> the complete tape production kept, captured as production released it
        -> TerminalTranscriptFinalizer -> the real 150/120 WindowedRunner
          -> a delegate that replays THE PAIRED FILE ARM'S OWN DECODE for this case
            -> LiveSession.apply_text_revision -> snapshot().effective_transcript
              -> the same scorer, against the same reference

If every gate below passes, then a terminal delta against the file arm is a statement about
the decoder and never about this adapter -- which is what R3 asks the M4 exit to be able to
say. The decode is replayed rather than requested: zero MOSS traffic, no GPU, runnable by a
reviewer as-is.

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \\
      prototypes/streaming-diarization/live-convergence/verify_terminal_finalizer.py

Exit 0 iff every gate passes. Gates and the one selection rule are fixed before the run.

- G1 the pass reads the meeting: the WAV handed to the runner is `[0, meeting_end)` of the
  tape, byte-identical to the corpus PCM, and the tape production released reports the same
  digest (so re-taping the captured bytes is checked, not assumed).
- G2 one terminal revision, from sample 0, exactly once: it applies, the surface is entirely
  `terminal` authority, `finalization_status` is `final`, `canonical_through_sample ==
  accepted_samples`, and a second terminal proposal is refused `already_finalized`.
- G3 the published words ARE the file arm's words: segment for segment, the terminal surface's
  text and its sample bounds equal the file hypothesis of the same pass.
- G4 the published speakers are the file arm's PARTITION, renamed: the map from the file arm's
  speaker to the published label is one-to-one and total, so no terminal speaker was split or
  merged, and no segment is published unattributed.
- G5 the scores are the file arm's scores: WER, DER, speaker accuracy and coverage of the
  terminal surface equal the file arm's, through one scorer, to 1e-12. This is `G-M4-1` and
  `G-M4-2` at delta 0 *conditional on the decode*, and the M4 exit still scores them on a
  fresh deployed pass with a real decoder.
- G6 terminal is better than what it replaced: per-case WER below the rolling surface of the
  same run (the campaign's `G-M4-3` read on this arm).
- G7 exact accounting and a released tape: `accepted == accounted`, no terminal failure, and
  the meeting's own tape reports zero retained bytes.
- G8 the terminal accounting carries no transcript text: every string in it is a name from a
  vocabulary read out of production, or an exception type.
- G9 zero fresh MOSS requests.

**The one policy this run selects** (plan §12.3 step 5, stated before the numbers). Both ways
of naming the terminal decoder's speakers are run over the same meetings:

  * `mapped` -- the adapter's per-speaker one-to-one assignment (`terminal_speaker_mapping`);
  * `projected` -- every segment published with no speaker, so the session's existing
    per-segment projection decides, exactly as it does for a rolling window.

The rule: ship the arm that PRESERVES the terminal pass's own partition (G4) and reproduces
the paired file arm's speaker scores (G5). If both do, ship `projected`, because it is the
rule the session already has and the adapter would need none. Both arms' numbers are
published either way; the loser's cost is the finding.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "prototypes/live-file-gap-context"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import proto_context_arms as bench  # noqa: E402
import verify_runtime_rolling as runtime_rolling  # noqa: E402
from moss_transcribe_diarize.app.live_span_bounds import render_segments  # noqa: E402
from moss_transcribe_diarize.app.model_runner import TranscriptionResult  # noqa: E402
from moss_transcribe_diarize.app.live_session import (  # noqa: E402
    LIVE_SAMPLE_RATE,
    UNATTRIBUTED_SPEAKER,
)
from moss_transcribe_diarize.app.live_transcript_convergence import (  # noqa: E402
    RollingStatus,
    TerminalOutcome,
    TerminalTranscriptFinalizer,
)
from moss_transcribe_diarize.app.speaker_identity import IdentityResolver  # noqa: E402
from moss_transcribe_diarize.app.vllm_runner import DEFAULT_PROMPT  # noqa: E402
from moss_transcribe_diarize.app.windowed_transcription import WindowedRunner  # noqa: E402
from moss_transcribe_diarize.transcript_parser import TranscriptSegment  # noqa: E402

GRID = REPO / "evidence/live-convergence-0824/M2-rolling-grid"
#: The paired pass every M4 bound is written against (PREREGISTRATION-M4 §1). Its file arm is
#: the comparator; its rolling arm is what terminal has to beat.
PAIRED = REPO / "evidence/live-convergence-0824/M2-e2-exit/passes/trio-A"
SCORE_KEYS = ("wer", "der", "coverage", "text_speaker_accuracy", "content_recall")
PLACES = 12
ARMS = ("mapped", "projected")


class TerminalCacheMiss(RuntimeError):
    """The finalizer asked for a decode of audio this run never recorded. No GPU call is made."""


class FileArmDelegate:
    """A MOSS stand-in that answers one whole meeting with the paired file arm's own decode.

    Keyed on the audio itself, so it can only answer for bytes it was given: a tape that is
    not the meeting produces a miss rather than a plausible transcript. The answer is the
    file hypothesis of the same paired pass, re-rendered into the transcript grammar by
    production's own renderer -- `render_segments`, the inverse of the parser the finalizer
    reads with -- so no second serializer is introduced between the two arms.
    """

    model_path = "OpenMOSS-Team/MOSS-Transcribe-Diarize"

    def __init__(self, answers: dict[str, str]):
        self.answers = answers
        self.requests = 0
        self.fresh_requests = 0
        self.last_audio_sha256: str | None = None
        self.last_kwargs: dict[str, Any] | None = None

    def transcribe(self, audio_path, **kwargs: Any):
        self.requests += 1
        pcm = runtime_rolling._wav_pcm(Path(audio_path))
        digest = hashlib.sha256(pcm).hexdigest()
        self.last_audio_sha256 = digest
        self.last_kwargs = dict(kwargs)
        text = self.answers.get(digest)
        if text is None:
            self.fresh_requests += 1
            raise TerminalCacheMiss(f"no recorded file-arm decode for {len(pcm) // 2} samples.")
        return TranscriptionResult(
            text=text,
            prompt_len=0,
            generated_tokens=max(1, len(text) // 4),
            elapsed_sec=0.0,
            model=self.model_path,
            audio=str(audio_path),
            decoding=str(kwargs.get("decoding") or "greedy"),
            temperature=None,
        )


def file_hypothesis(case: str) -> list[TranscriptSegment]:
    path = PAIRED / case / "file-hypothesis.jsonl"
    return [
        TranscriptSegment(
            start=float(item["start"]),
            end=float(item["end"]),
            speaker=str(item["speaker"]),
            text=str(item["text"]),
        )
        for item in (json.loads(line) for line in path.read_text().splitlines() if line.strip())
    ]


def file_answers(cases: list[str]) -> dict[str, str]:
    """Every case's file-arm decode, keyed by the PCM a terminal pass would hand a runner."""

    answers: dict[str, str] = {}
    for case in cases:
        pcm = bench.read_pcm(bench.CORPUS / case / "audio.wav")
        answers[hashlib.sha256(pcm).hexdigest()] = render_segments(
            file_hypothesis(case), lambda segment: segment.speaker
        )
    return answers


def file_scores(case: str) -> dict[str, Any]:
    """The file arm scored on this verifier's own instrument, so G5 compares like with like."""

    segments = file_hypothesis(case)
    duration = len(bench.read_pcm(bench.CORPUS / case / "audio.wav")) / 2 / LIVE_SAMPLE_RATE
    hypothesis = bench.normalise(
        [bench.Segment(item.start, item.end, item.speaker, item.text) for item in segments],
        duration,
    )
    return bench.score(bench.load_reference(case), hypothesis)


def flat_scores(scores: dict[str, Any]) -> dict[str, float]:
    """The gated axes, from the bench's own scorer -- both arms and the file arm through one."""

    return {key: scores[key] for key in SCORE_KEYS}


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for child in value.values() for item in _strings(child)]
    if isinstance(value, (list, tuple)):
        return [item for child in value for item in _strings(child)]
    return []


def accounting_vocabulary() -> set[str]:
    """Every name a terminal accounting may carry, read from production rather than listed."""

    return (
        {item.value for item in TerminalOutcome}
        | {item.finalization_status for item in TerminalOutcome}
        | {item.value for item in RollingStatus}
    )


def build_finalizer(answers: dict[str, str], delegate: FileArmDelegate) -> TerminalTranscriptFinalizer:
    """File mode's own runner, built exactly as `app/server.py` builds it, around the delegate."""

    return TerminalTranscriptFinalizer(
        runner=WindowedRunner(delegate, identity_resolver=IdentityResolver()),
        transcribe_kwargs={"prompt": DEFAULT_PROMPT, "decoding": "greedy"},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default=",".join(bench.CASES))
    parser.add_argument("--cache", type=Path, default=GRID / "decode-cache/run0.json")
    parser.add_argument("--output", type=Path, default=None)
    cli = parser.parse_args()

    names = [item for item in cli.cases.split(",") if item]
    config = runtime_rolling.deployed_configuration()
    base_runner = runtime_rolling.ReplayRunner(
        runtime_rolling.load_replay_entries(cli.cache, names)
    )
    answers = file_answers(names)
    delegate = FileArmDelegate(answers)
    finalizer = build_finalizer(answers, delegate)
    tape_bytes = 300 * LIVE_SAMPLE_RATE * 2

    document: dict[str, Any] = {
        "schema": "moss-live-convergence-terminal-finalizer.v1",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "modules": [
            "moss_transcribe_diarize/app/live_transcript_convergence.py",
            "moss_transcribe_diarize/app/live_adapters.py",
        ],
        "paired_pass": str(PAIRED.relative_to(REPO)),
        "accounting_vocabulary": sorted(accounting_vocabulary()),
        "file_arm": {case: flat_scores(file_scores(case)) for case in names},
        "arms": {arm: {} for arm in ARMS},
    }
    for case in names:
        for arm in ARMS:
            run = runtime_rolling.run_case(
                config,
                base_runner,
                case,
                rolling=True,
                tape_bytes=tape_bytes,
                terminal=finalizer,
                terminal_canonical=(arm == "mapped"),
            )
            # What the *delegate* was actually handed, read off the delegate rather than off
            # the runner that wrapped it: G1 is the claim that the 150/120 pipeline decoded
            # the tape and not some other audio, and only the delegate can answer it.
            if isinstance(run.get("terminal"), dict):
                run["terminal"]["decoded_wav_sha256"] = delegate.last_audio_sha256
            document["arms"][arm][case] = run
    document["decode_cost"] = {
        "base_requests": base_runner.requests,
        "base_fresh_requests": base_runner.fresh_requests,
        "terminal_requests": delegate.requests,
        "terminal_fresh_requests": delegate.fresh_requests,
    }
    document["terminal_kwargs"] = delegate.last_kwargs

    failures: list[str] = []
    # G4 and G5 are the two readings the §12.3 step 5 selection is made from, so they are
    # collected per arm rather than thrown straight onto the exit path: the arm that loses
    # the selection is a measured finding, not a broken build. Every other gate is a property
    # of the pass itself and must hold in both arms.
    policy_failures: dict[str, list[str]] = {arm: [] for arm in ARMS}
    partition: dict[str, dict[str, Any]] = {arm: {} for arm in ARMS}
    for case in names:
        expected = file_hypothesis(case)
        expected_bounds = [
            (round(item.start * LIVE_SAMPLE_RATE), round(item.end * LIVE_SAMPLE_RATE), item.text)
            for item in expected
        ]
        for arm in ARMS:
            run = document["arms"][arm][case]
            terminal = run.get("terminal") or {}
            tag = f"{arm}/{case}"
            if "refused" in terminal:
                failures.append(f"G1 {tag} no terminal pass ran: {terminal['refused']}")
                continue
            accounting = terminal["accounting"]

            # G1 -- the pass read the meeting.
            corpus_sha = run["tape"]["audio_sha256"]
            if terminal["tape"]["captured_sha256"] != corpus_sha:
                failures.append(f"G1 {tag} the captured tape is not the corpus audio")
            if terminal["tape"]["retaped_sha256"] != corpus_sha:
                failures.append(f"G1 {tag} re-taping the captured bytes changed them")
            released = terminal["tape"]["released_accounting"] or {}
            if released.get("pcm_sha256") != corpus_sha:
                failures.append(f"G1 {tag} the released tape reports a different digest")
            if terminal["decoded_wav_sha256"] != corpus_sha:
                failures.append(f"G1 {tag} the runner was handed audio that is not the tape")
            if accounting["tape_samples"] != run["accepted_samples"]:
                failures.append(
                    f"G1 {tag} decoded {accounting['tape_samples']} of {run['accepted_samples']} samples"
                )
            if (accounting["window_seconds"], accounting["stride_seconds"]) != (150.0, 120.0):
                failures.append(f"G1 {tag} the pass did not run the 150/120 windowing")
            if accounting["window_count"] != 1:
                failures.append(f"G1 {tag} a 60 s meeting planned {accounting['window_count']} windows")

            # G2 -- one revision, from sample 0, exactly once.
            if accounting["outcome"] != TerminalOutcome.FINALIZED.value or terminal["applied"] is not True:
                failures.append(f"G2 {tag} the terminal revision did not apply: {accounting['reason']}")
            if terminal["finalization_status"] != "final":
                failures.append(f"G2 {tag} finalization_status is {terminal['finalization_status']}")
            if terminal["authorities"] != ["terminal"]:
                failures.append(f"G2 {tag} the surface is not all terminal: {terminal['authorities']}")
            if terminal["canonical_through_sample"] != run["accepted_samples"]:
                failures.append(f"G2 {tag} terminal owns {terminal['canonical_through_sample']} samples")
            if terminal["second_refusal"] != "already_finalized" or terminal["second_applied"] is not False:
                failures.append(f"G2 {tag} a second terminal pass was not refused already_finalized")
            if terminal["committed_prefix_hash"] != run["committed_prefix_hash"]:
                failures.append(f"G2 {tag} terminal moved the committed chain")

            # G3 -- the published words are the file arm's words.
            published = [(item[0], item[1], item[3]) for item in terminal["surface"]]
            if published != expected_bounds:
                first = next(
                    (index for index, pair in enumerate(zip(published, expected_bounds)) if pair[0] != pair[1]),
                    min(len(published), len(expected_bounds)),
                )
                failures.append(
                    f"G3 {tag} surface differs from the file arm at segment {first} "
                    f"({len(published)} vs {len(expected_bounds)} segments)"
                )

            # G4 -- the file arm's partition, renamed one-to-one.
            pairs = sorted({(item.speaker, row[2]) for item, row in zip(expected, terminal["surface"])})
            by_file = {file: {label for name, label in pairs if name == file} for file, _ in pairs}
            partition[arm][case] = {
                "pairs": [list(pair) for pair in pairs],
                "unattributed_segments": sum(
                    1 for row in terminal["surface"] if row[2] == UNATTRIBUTED_SPEAKER
                ),
            }
            if len(published) == len(expected_bounds):
                if any(len(labels) != 1 for labels in by_file.values()):
                    policy_failures[arm].append(f"G4 {tag} a file-arm speaker was split across labels: {by_file}")
                if len({label for _, label in pairs}) != len(by_file):
                    policy_failures[arm].append(f"G4 {tag} two file-arm speakers were merged: {by_file}")
                if partition[arm][case]["unattributed_segments"]:
                    policy_failures[arm].append(
                        f"G4 {tag} {partition[arm][case]['unattributed_segments']} segments published S00"
                    )

            # G5 -- the file arm's scores.
            terminal_scores = flat_scores(terminal["scores"])
            deltas = {
                key: round(terminal_scores[key] - document["file_arm"][case][key], PLACES)
                for key in SCORE_KEYS
            }
            terminal["score_delta_vs_file"] = deltas
            for key, value in deltas.items():
                if value != 0:
                    policy_failures[arm].append(
                        f"G5 {tag} {key} differs from the file arm by {value:+.12f}"
                    )

            # G6 -- better than what it replaced.
            rolling_wer = flat_scores(run["scores"])["wer"]
            terminal["rolling_wer"] = rolling_wer
            if terminal_scores["wer"] > rolling_wer:
                failures.append(
                    f"G6 {tag} terminal WER {terminal_scores['wer']:.6f} > rolling {rolling_wer:.6f}"
                )

            # G7 -- accounting and a released tape.
            if terminal["accepted_samples"] != terminal["accounted_samples"]:
                failures.append(f"G7 {tag} accepted != accounted after terminal")
            if run["terminal_failure"] is not None:
                failures.append(f"G7 {tag} the meeting failed: {run['terminal_failure']}")
            if (released.get("retained_bytes"), released.get("released")) != (0, True):
                failures.append(f"G7 {tag} the tape survived the meeting")

            # G8 -- names only.
            for text in _strings(accounting):
                if text not in accounting_vocabulary() and not text.endswith("Error"):
                    failures.append(f"G8 {tag} terminal accounting carries {text!r}")

    document["partition"] = partition
    if document["decode_cost"]["base_fresh_requests"] or document["decode_cost"]["terminal_fresh_requests"]:
        failures.append(f"G9 fresh MOSS requests: {document['decode_cost']}")

    # The §12.3 step 5 selection, applied to what the two arms actually did. The rule and the
    # tie-break were fixed in this file's docstring before the run.
    verdicts = {
        arm: {
            "preserves_partition": not any(
                item.startswith("G4 ") for item in policy_failures[arm]
            ),
            "reproduces_file_scores": not any(
                item.startswith("G5 ") for item in policy_failures[arm]
            ),
            "findings": policy_failures[arm],
        }
        for arm in ARMS
    }
    qualified = [
        arm
        for arm in ARMS
        if verdicts[arm]["preserves_partition"] and verdicts[arm]["reproduces_file_scores"]
    ]
    selected = "projected" if "projected" in qualified else ("mapped" if "mapped" in qualified else None)
    document["speaker_policy"] = {"arms": verdicts, "qualified": qualified, "selected": selected}
    if selected is None:
        failures.append("G4/G5 no speaker-naming policy preserves the terminal partition")
    else:
        # Only the SHIPPED arm's readings are gates; the other arm's are the finding that
        # made the selection, and are published in full beside it.
        failures.extend(policy_failures[selected])

    document["failures"] = failures
    document["verdict"] = "PASS" if not failures else "FAIL"
    if cli.output is not None:
        cli.output.parent.mkdir(parents=True, exist_ok=True)
        cli.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for arm in ARMS:
        for case in names:
            terminal = (document["arms"][arm][case].get("terminal") or {})
            if "refused" in terminal:
                print(f"{arm:<10} {case:<18} REFUSED {terminal['refused']}")
                continue
            scores = flat_scores(terminal["scores"])
            file_arm = document["file_arm"][case]
            print(
                f"{arm:<10} {case:<18} wer={scores['wer']:.6f} (file {file_arm['wer']:.6f}, "
                f"rolling {terminal['rolling_wer']:.6f})  der={scores['der']:.6f} "
                f"(file {file_arm['der']:.6f})  tsa={scores['text_speaker_accuracy']:.6f} "
                f"(file {file_arm['text_speaker_accuracy']:.6f})  "
                f"recall={scores['content_recall']:.6f} (file {file_arm['content_recall']:.6f})  "
                f"S00={partition[arm][case]['unattributed_segments']}"
            )
    policy = document["speaker_policy"]
    print(f"speaker policy selected: {policy['selected']} (qualified: {policy['qualified'] or 'none'})")
    for arm in ARMS:
        verdict = policy["arms"][arm]
        print(
            f"  {arm:<10} preserves_partition={verdict['preserves_partition']!s:<5} "
            f"reproduces_file_scores={verdict['reproduces_file_scores']!s:<5} "
            f"findings={len(verdict['findings'])}"
        )
    print("decode cost:", json.dumps(document["decode_cost"], sort_keys=True))
    print("terminal kwargs:", json.dumps(document["terminal_kwargs"], sort_keys=True))
    for failure in failures:
        print("FAIL", failure)
    print(document["verdict"])
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
