"""Run the implemented resolver on the retained paired spans and source-score its output."""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import replace
import json
from pathlib import Path
import tempfile

from scipy.optimize import linear_sum_assignment

from moss_transcribe_diarize.app.file_identity_album import AlbumIdentityResolver
from moss_transcribe_diarize.app.windowed_transcription import WindowPlan, extract_window_wav
from moss_transcribe_diarize.transcript_parser import TranscriptSegment

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RUNTIME = Path("/private/tmp/moss-independent-assessment-20260918/.wp25runtime/20260919T033906530769Z")
OWNED = ((0.0, 135.0), (135.0, 255.0), (255.0, 375.0))


def overlap(a, b):
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def score(windows, groups, reference, owned_ranges):
    labels = sorted({segment.speaker for group in groups for segment in group if segment.speaker != "S00"})
    people = sorted({row["speaker"] for row in reference})
    support = {(person, label): 0.0 for person in people for label in labels}
    projected = []
    for window, group, own in zip(windows, groups, owned_ranges, strict=True):
        for segment in group:
            absolute = (window.start + segment.start, window.start + segment.end)
            owned = (max(absolute[0], own[0]), min(absolute[1], own[1]))
            if owned[1] <= owned[0]:
                continue
            projected.append((owned, segment.speaker))
            if segment.speaker == "S00":
                continue
            for row in reference:
                support[row["speaker"], segment.speaker] += overlap(owned, (row["start"], row["end"]))
    matrix = [[-support[person, label] for label in labels] for person in people]
    rows, columns = linear_sum_assignment(matrix)
    person_of = {labels[column]: people[row] for row, column in zip(rows, columns, strict=True)}
    outcomes = {person: defaultdict(float) for person in people}
    reference_seconds = defaultdict(float)
    for row in reference:
        for own in owned_ranges:
            reference_seconds[row["speaker"]] += overlap((row["start"], row["end"]), own)
    for owned, label in projected:
        for row in reference:
            seconds = overlap(owned, (row["start"], row["end"]))
            if not seconds:
                continue
            if label == "S00":
                outcomes[row["speaker"]]["unknown"] += seconds
            elif person_of[label] == row["speaker"]:
                outcomes[row["speaker"]]["correct"] += seconds
            else:
                outcomes[row["speaker"]]["confused"] += seconds
    result = {}
    for person in people:
        covered = sum(outcomes[person].values())
        outcomes[person]["missed"] = max(0.0, reference_seconds[person] - covered)
        result[person] = {key: round(outcomes[person][key], 6) for key in ("correct", "confused", "unknown", "missed")}
    return {"canonical_person": person_of, "people": result}


def baseline_groups(resolution, windows, groups):
    labels = {}
    for state in resolution.diagnostics["windows"]:
        labels.update({(state["window"], local): canonical for local, canonical in state["mapping"].items()})
    for correction in resolution.diagnostics["sweep"]["corrections"]:
        labels[correction["span_id"], correction["local_speaker"]] = correction["canonical_speaker"]
    return [[replace(segment, speaker=labels.get((window.index, segment.speaker), "S00"))
             for segment in group] for window, group in zip(windows, groups, strict=True)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--full-retained", action="store_true")
    args = parser.parse_args()
    retained = json.loads((HERE / "results.json").read_text())
    reference = [json.loads(line) for line in (RUNTIME / "files/media/reference.jsonl").read_text().splitlines()]
    output = []
    with tempfile.TemporaryDirectory(prefix="verify-interval-refinement-") as directory:
        scratch = Path(directory)
        for arm in ("wav", "mp3"):
            cases = [item for item in retained["cases"] if item["case"].startswith(f"composite-{arm}-")]
            windows, groups, paths = [], [], []
            for index, case in enumerate(cases):
                start = float(case["source_start"])
                path = scratch / f"{arm}-{index}.wav"
                extract_window_wav(case["source"], path, start_seconds=start, duration_seconds=150.0)
                windows.append(WindowPlan(index, start, start + 150.0, OWNED[index][0], OWNED[index][1]))
                groups.append([TranscriptSegment(**segment) for segment in case["segments"]])
                paths.append(path)
            resolution = AlbumIdentityResolver().resolve(windows, groups, window_audio_paths=paths)
            baseline = baseline_groups(resolution, windows, groups)
            output.append({"arm": arm, "summary": resolution.summary,
                           "refinement": resolution.diagnostics["interval_refinement"],
                           "baseline_source_score": score(windows, baseline, reference, OWNED),
                           "candidate_source_score": score(windows, resolution.relabeled_results, reference, OWNED)})
        retained_output = []
        if args.full_retained:
            for minutes in (6, 30):
                fixture = json.loads((ROOT / f"evidence/mvpfix/wp28/fixture-{minutes}.json").read_text())
                windows = [WindowPlan(**row) for row in fixture["windows"]]
                groups = [[TranscriptSegment(**segment) for segment in group] for group in fixture["local_results"]]
                paths = []
                audio = RUNTIME / f"files/media/{'six' if minutes == 6 else 'long'}.wav"
                for window in windows:
                    path = scratch / f"retained-{minutes}-{window.index}.wav"
                    extract_window_wav(audio, path, start_seconds=window.start, duration_seconds=window.duration)
                    paths.append(path)
                resolution = AlbumIdentityResolver().resolve(windows, groups, window_audio_paths=paths)
                owned = tuple((window.own_start, window.own_end) for window in windows)
                baseline = baseline_groups(resolution, windows, groups)
                retained_output.append({"minutes": minutes, "summary": resolution.summary,
                                        "refinement": resolution.diagnostics["interval_refinement"],
                                        "baseline_source_score": score(windows, baseline, reference, owned),
                                        "candidate_source_score": score(windows, resolution.relabeled_results, reference, owned)})
    result = {"implementation": output, "retained_wav": retained_output}
    (HERE / "implementation-results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
