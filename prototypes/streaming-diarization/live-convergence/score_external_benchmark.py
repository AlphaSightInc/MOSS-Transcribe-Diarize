"""Score LiveTranscribe and ProjectClerk file-mode outputs with THIS repo's evaluators.

Post-campaign step-7 benchmark (docs/handoffs/handoff-8YIE4C.md): the two external systems
ran on m4mbp over the SAME audio bytes as this repo's golden cases; their raw outputs are
converted to this repo's hypothesis shape and scored by the deployed scorer
(calculate_tbsa / calculate_diarization / score_live_speaker_accuracy) and by evaluator v2
(reference-interval speech regions), so every number in the benchmark report comes from one
instrument. MOSS arms are NOT rescored here: they are read from the checked-in M4 exit
bundle (evidence/live-convergence-0824/M4-e4-exit-2/gates.json), which two fresh paired
batches already reproduce.

Inputs (produced on m4mbp, copied back verbatim):
  LT:  <lt-root>/<case>/transcripts.jsonl (+ post_cluster_relabels.jsonl applied by
       utteranceID when row counts match; the divergence count is reported either way)
  PC:  <pc-root>/<case>/hyp.json  ({"segments": [{speaker,start,end,text}...]})

Usage:
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
    prototypes/streaming-diarization/live-convergence/score_external_benchmark.py \
    --lt-root <dir> --pc-root <dir> --walls <json> \
    --output evidence/live-convergence-0824/benchmark/results.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from moss_transcribe_diarize import live_speaker_accuracy as lsa  # noqa: E402
from moss_transcribe_diarize.evaluation import (  # noqa: E402
    Segment,
    calculate_diarization,
    calculate_tbsa,
)
from evaluator_v2 import Segment as V2Segment, score_v2  # noqa: E402

REAL = REPO / "prototypes/streaming-diarization/data/real"
CASES = {
    "lex_bill_ackman": REAL / "benchmark_diarization_1min/samples/lex_bill_ackman/reference.jsonl",
    "lex_javier_milei": REAL / "benchmark_diarization_1min/samples/lex_javier_milei/reference.jsonl",
    "lex_keyu_jin_1m": REAL / "benchmark_diarization_1min/samples/lex_keyu_jin/reference.jsonl",
    "lex_adam_frank_3m": REAL / "calibration_diarization_3min/samples/lex_adam_frank/reference.jsonl",
    "lex_keyu_jin_5m": REAL / "benchmark_5m/lex_keyu_jin/reference.jsonl",
}
# The M4 exit bundle names the same audio by these keys.
MOSS_KEYS = {
    "lex_bill_ackman": "lex_bill_ackman",
    "lex_javier_milei": "lex_javier_milei",
    "lex_keyu_jin_1m": "lex_keyu_jin",
    "lex_adam_frank_3m": "lex_adam_frank",
    "lex_keyu_jin_5m": "keyu-5m",
}


def load_lt(case_dir: Path) -> tuple[list, dict]:
    rows = [json.loads(l) for l in (case_dir / "transcripts.jsonl").open()]
    relabel_path = case_dir / "post_cluster_relabels.jsonl"
    meta = {"rows": len(rows), "relabels_applied": False, "relabels_changed": 0}
    if relabel_path.exists():
        relabels = [json.loads(l) for l in relabel_path.open()]
        if len(relabels) == len(rows):
            changed = 0
            for row, rel in zip(rows, relabels):
                if rel["newSpeakerID"] != row["speaker"]:
                    changed += 1
                row["speaker"] = rel["newSpeakerID"]
            meta.update(relabels_applied=True, relabels_changed=changed)
    segs = [
        {"start": r["start_sec"], "end": r["end_sec"], "speaker": r["speaker"], "text": r["text"]}
        for r in rows
        if r.get("text", "").strip()
    ]
    return segs, meta


def load_pc(case_dir: Path) -> tuple[list, dict]:
    payload = json.loads((case_dir / "hyp.json").read_text())
    segs = [
        {"start": s["start"], "end": s["end"], "speaker": s["speaker"], "text": s["text"]}
        for s in payload["segments"]
        if s.get("text", "").strip()
    ]
    return segs, {"rows": len(segs)}


def score(reference_path: Path, segs: list) -> dict:
    ref_t = lsa.load_reference_jsonl(reference_path)
    ref_a = lsa.load_reference_speaker_activity_jsonl(reference_path)
    to_eval = lambda items: [  # noqa: E731
        Segment(start=float(s.start), end=float(s.end), speaker=str(s.speaker), text=str(s.text))
        for s in items
    ]
    # Route through the same loader the paired drivers use so validation rules match.
    tmp = [json.dumps(s) for s in segs]
    import tempfile, os
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
        fh.write("\n".join(tmp) + "\n")
        tmp_path = fh.name
    try:
        hyp = lsa.load_reference_jsonl(tmp_path)
    finally:
        os.unlink(tmp_path)
    ref_eval, hyp_eval = to_eval(ref_t), to_eval(hyp)
    tbsa = calculate_tbsa(ref_eval, hyp_eval)
    diar = calculate_diarization(ref_eval, hyp_eval)
    spk = lsa.score_live_speaker_accuracy(
        list(ref_a), [lsa.SpeakerActivityInterval(s.start, s.end, s.speaker) for s in hyp]
    )
    v2 = score_v2(
        [V2Segment(start=float(s.start), end=float(s.end), speaker=str(s.speaker), text=str(s.text)) for s in ref_t],
        [V2Segment(start=float(s.start), end=float(s.end), speaker=str(s.speaker), text=str(s.text)) for s in hyp],
    )
    return {
        "wer": round(tbsa["wer"], 6),
        "tbsa_composite": round(tbsa["composite"], 6),
        "text_coverage": round(tbsa["text_coverage"], 6),
        "der": round(diar["der"], 6),
        "speaker_accuracy": round(spk["speaker_accuracy"], 6),
        "v2_content_recall": round(v2["content_recall"], 6),
        "v2_matched_word_speaker": round(
            v2["matched_word_speaker"]["matched_word_speaker_accuracy"], 6),
        "segments": len(hyp),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lt-root", required=True)
    ap.add_argument("--pc-root", required=True)
    ap.add_argument("--walls", help="JSON {system: {case: seconds}} measured on m4mbp")
    ap.add_argument("--moss-gates", default=str(
        REPO / "evidence/live-convergence-0824/M4-e4-exit-2/gates.json"))
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    walls = json.loads(args.walls) if args.walls else {}
    moss = json.load(open(args.moss_gates))["quality"]["cases"]
    out = {"cases": {}, "provenance": {
        "scored_by": "MOSS-Transcribe-Diarize deployed scorer + evaluator v2 (one instrument)",
        "moss_numbers_from": str(Path(args.moss_gates).relative_to(REPO)),
        "walls_measured_on": "m4mbp (M4 MacBook Pro), sequential, one system at a time",
    }}
    for case, ref in CASES.items():
        lt_segs, lt_meta = load_lt(Path(args.lt_root) / case)
        pc_segs, pc_meta = load_pc(Path(args.pc_root) / case)
        mk = MOSS_KEYS[case]
        mcase = moss[mk]
        row = {
            "livetranscribe": {**score(ref, lt_segs), **{"convert": lt_meta},
                               "wall_s": walls.get("lt", {}).get(case)},
            "projectclerk": {**score(ref, pc_segs), **{"convert": pc_meta},
                             "wall_s": walls.get("pc", {}).get(case)},
            # runs A and B agree to 6 dp in the bundle (runs_agree recorded); A is canonical.
            "moss_live_terminal": mcase["runs"]["A"]["live"],
            "moss_file": mcase["runs"]["A"]["file"],
            "moss_runs_agree": mcase.get("runs_agree"),
        }
        out["cases"][case] = row
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    for case, row in out["cases"].items():
        lt, pc = row["livetranscribe"], row["projectclerk"]
        print(f"{case}: LT wer={lt['wer']} der={lt['der']} | PC wer={pc['wer']} der={pc['der']}")
    print(f"written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
