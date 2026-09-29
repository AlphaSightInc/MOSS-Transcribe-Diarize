"""Collect display-only tentative guesses and score them against timed public truth."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from moss_transcribe_diarize.evaluation import Segment, calculate_diarization
from moss_transcribe_diarize.transcript_parser import parse_transcript

RATE = 16000


@dataclass
class TentativeProbe:
    # A repeated 250 ms snapshot of the same preview must not enlarge its denominator.
    tbd: set[tuple[float, float, str]] = field(default_factory=set)
    guesses: dict[tuple[float, float, str], str] = field(default_factory=dict)

    def observe(self, snapshot: dict):
        session = snapshot["session"]
        preview = session.get("provisional")
        if not isinstance(preview, dict) or not preview.get("transcript", "").strip():
            return
        offset = int(preview["start_sample"]) / RATE
        for segment in parse_transcript(preview["transcript"]):
            if segment.text.strip():
                self.tbd.add((offset + segment.start, offset + segment.end, "system"))
        for span in preview.get("tentative_spans") or []:
            key = (int(span["start_sample"]) / RATE, int(span["end_sample"]) / RATE,
                   str(span["source_lane"]))
            if key not in self.guesses:
                self.guesses[key] = str(span["speaker"])

    def result(self, reference: list[dict], final_snapshot: dict):
        final_rows = final_snapshot["session"]["effective_transcript"]
        canonical = [Segment(float(row["start_sample"]) / RATE,
                             float(row["end_sample"]) / RATE,
                             str(row["canonical_speaker"]), str(row.get("text", "")))
                     for row in final_rows if row.get("canonical_speaker")]
        truth = [Segment(float(row["start"]), float(row["end"]), str(row["speaker"]),
                         str(row.get("text", ""))) for row in reference]
        mapping = calculate_diarization(truth, canonical)["speaker_mapping"] if canonical else {}
        # Sweep exact boundaries rather than adding repeated previews; each audio
        # interval contributes once even when successive previews overlap it.
        tbd_s = covered_s = scored_s = correct_s = 0.0
        lanes = {lane for _, _, lane in self.tbd}
        for lane in lanes:
            tbd_rows = [(start, end) for start, end, row_lane in self.tbd if row_lane == lane]
            guesses = [(start, end, speaker) for (start, end, row_lane), speaker in self.guesses.items()
                       if row_lane == lane]
            boundaries = sorted({point for start, end in tbd_rows for point in (start, end)}
                                | {point for start, end, _ in guesses for point in (start, end)}
                                | {point for row in truth for point in (row.start, row.end)})
            for start, end in zip(boundaries, boundaries[1:]):
                if not any(a < end and b > start for a, b in tbd_rows):
                    continue
                width = end - start
                tbd_s += width
                guess = next((speaker for a, b, speaker in guesses if a < end and b > start), None)
                if guess is None:
                    continue
                covered_s += width
                for row in truth:
                    if row.start < end and row.end > start:
                        scored_s += width
                        if mapping.get(row.speaker) == guess:
                            correct_s += width
        return {"tbd_seconds": round(tbd_s, 3), "guessed_seconds": round(covered_s, 3),
                "reference_scored_guess_seconds": round(scored_s, 3),
                "correct_guess_seconds": round(correct_s, 3),
                "coverage": None if tbd_s == 0 else round(covered_s / tbd_s, 6),
                "accuracy": None if scored_s == 0 else round(correct_s / scored_s, 6),
                "reference_to_canonical": mapping}


if __name__ == "__main__":
    probe = TentativeProbe()
    probe.tbd = {(0.0, 2.0, "system"), (2.0, 4.0, "system")}
    probe.tbd.add((0.0, 1.0, "system"))  # a changed preview must not inflate time
    probe.guesses = {(0.0, 2.0, "system"): "a"}
    reference = [{"start": 0, "end": 2, "speaker": "person-A"},
                 {"start": 2, "end": 4, "speaker": "person-B"}]
    final = {"session": {"effective_transcript": [
        {"start_sample": 0, "end_sample": 32000, "canonical_speaker": "a"},
        {"start_sample": 32000, "end_sample": 64000, "canonical_speaker": "b"}]}}
    import json
    print(json.dumps({"question": "Does first-shown guess coverage preserve both denominators?",
                      "hypothesis": "One correct guess on half the TBD speech gives coverage .5 and accuracy 1",
                      "falsifier": "Either ratio differs", "state": probe.result(reference, final)}, indent=2))
