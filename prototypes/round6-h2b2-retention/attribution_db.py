"""Read-only, content-free replay of quarantined H1 terminal documents."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from moss_transcribe_diarize.evaluation import Segment, calculate_diarization
from moss_transcribe_diarize.live_speaker_accuracy import load_reference_jsonl

EXPORT = Path("/Users/gao/Documents/Codex/2026-09-23/moss-round6/evidence/r6-h1-20260923T051306Z/attempt-store/x")
HOST = EXPORT.parent.parent / "20260923T051605Z-f7fe4ad" / "raw"
OUT = Path("/Users/gao/Documents/Codex/2026-09-23/moss-round6/evidence/h2b-quality/attribution-db.jsonl")
ORDER = (
    "mono_javier_intro_50s",
    "interview_bill_ackman_60s",
    "interview_keyu_jin_60s",
    "interview_adam_frank_180s",
    "discussion_jamie_dimon_180s",
    "discussion_rtfl_90s",
)
DURATIONS_MS = {ORDER[0]: 50076, ORDER[1]: 60084, ORDER[2]: 60084,
                ORDER[3]: 180072, ORDER[4]: 180072, ORDER[5]: 90072}
RATE = 16000


def _overlap(a: Segment, b: Segment) -> float:
    return max(0.0, min(a.end, b.end) - max(a.start, b.start))


def _score(reference: list[Segment], hypothesis: list[Segment]) -> dict[str, float]:
    current = calculate_diarization(reference, hypothesis)
    ref_duration = sum(row.duration for row in reference)
    s00_confusion = sum(
        _overlap(ref, hyp)
        for ref in reference for hyp in hypothesis
        if hyp.speaker == "S00" and current["speaker_mapping"].get(ref.speaker) != hyp.speaker
    ) / ref_duration
    return {
        "der": current["der"],
        "miss": current["miss"],
        "false_alarm": current["false_alarm"],
        "speaker_confusion": current["speaker_confusion"],
        "s00_confusion": round(s00_confusion, 9),
        "der_without_s00_confusion": round(current["der"] - s00_confusion, 9),
        "named_residual_der": round(current["der"] - s00_confusion, 9),
    }


def main() -> None:
    corpus = EXPORT / "qualification-corpus"
    manifest_bytes = (corpus / "corpus-manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    assert hashlib.sha256(manifest_bytes).hexdigest() == "80fc15bd730f7aa44d8a69aa6e7e00aaf43ed54e2af8a03abc2c8934d7438d7c"
    cases = {case["case_id"]: case for case in manifest["cases"]}
    assert set(cases) == set(ORDER)
    references = {}
    for case_id in ORDER:
        path = corpus / case_id / "reference.jsonl"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == cases[case_id]["reference_sha256"]
        references[case_id] = [Segment(x.start, x.end, x.speaker, "") for x in load_reference_jsonl(path)]

    uri = f"file:{EXPORT / 'candidate-database.sqlite3'}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    rows = connection.execute("""
        SELECT m.created_at_ms, a.duration_ms, t.document_json
        FROM meetings m JOIN meeting_audio a USING(account_id, meeting_id)
        JOIN meeting_transcripts t USING(account_id, meeting_id)
        WHERE m.status = 'completed' ORDER BY m.created_at_ms
    """).fetchall()
    outputs = []
    for layer, lower, upper in (("deployed", 1790141900000, 1790143160000),
                                ("pre_admission", 1790145680000, 1790146950000)):
        selected = [row for row in rows if lower < row[0] < upper]
        order = ORDER + tuple(reversed(ORDER))
        assert len(selected) == len(order), (layer, len(selected))
        host = json.loads((HOST / f"{layer}-collector" / f"{layer}--G4--quality_corpus.json").read_text())
        retained = {(r["pass"], r["case_id"]): r for r in host["raw"]["per_case"]}
        assert len(retained) == 12
        for index, ((created, duration_ms, document), case_id) in enumerate(zip(selected, order, strict=True)):
            assert duration_ms == DURATIONS_MS[case_id]
            segments = json.loads(document)["segments"]
            hypothesis = [Segment(float(s["start"]), float(s["end"]),
                                  str(s["speaker"]), "") for s in segments]
            pass_number = 1 if index < 6 else 2
            expected = retained[(pass_number, case_id)]["metrics"]["final"]
            scored = _score(references[case_id], hypothesis)
            assert abs(scored["der"] - expected["der"]) < 1e-9, (layer, pass_number, case_id)
            assert len(segments) == expected["segments"]
            outputs.append({"kind": "case", "layer": layer, "pass": pass_number,
                            "case_id": case_id, "surface": "post_stop_final",
                            "created_at_ms": created, "duration_ms": duration_ms,
                            "reference_sha256": cases[case_id]["reference_sha256"],
                            "hypothesis_intervals": len(segments),
                            "s00_intervals": sum(s.speaker == "S00" for s in hypothesis),
                            "retained_final_reference_speech_der": expected["reference_speech_der"],
                            **scored})
        layer_rows = [row for row in outputs if row["layer"] == layer]
        macro = {field: sum(row[field] for row in layer_rows) / 12
                 for field in ("der", "s00_confusion", "der_without_s00_confusion", "named_residual_der")}
        outputs.append({"kind": "macro", "layer": layer, "surface": "post_stop_final",
                        "cases": 6, "passes": 2, "sessions": 12,
                        "retained_final_der": sum(float(row["metrics"]["final"]["der"])
                                                  for row in retained.values()) / 12,
                        "retained_settled_der": host["raw"]["macro"]["diarization_error_rate"],
                        "retained_final_reference_speech_der": sum(
                            float(row["metrics"]["final"]["reference_speech_der"])
                            for row in retained.values()) / 12,
                        "retained_settled_reference_speech_der": host["raw"]["macro"]["reference_speech_der"],
                        "reference_speech_der_counterfactual": "UNMEASURED: WAV bytes absent from export",
                        "round16_final_der": "UNMEASURED: report retains settled DER only",
                        **macro})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in outputs))
    for row in outputs:
        if row["kind"] == "macro":
            print(json.dumps(row, sort_keys=True))


if __name__ == "__main__":
    main()
