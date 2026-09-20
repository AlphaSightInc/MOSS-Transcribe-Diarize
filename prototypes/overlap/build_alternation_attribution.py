"""Build R4 follow-on attribution for alternation and overlap microphone lanes."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from moss_transcribe_diarize.lane_word_oracle import words
from reproduce import align


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence" / "round4" / "overlap"


def _record(path: Path) -> dict:
    return json.loads(path.read_text().splitlines()[0])


def _score(reference: str, hypothesis: str) -> tuple[tuple[int, int, int, int], list[dict]]:
    return align(words(reference), words(hypothesis))


def _metrics(reference: str, hypothesis: str) -> dict:
    score, _ = _score(reference, hypothesis)
    return {
        "reference_words": len(words(reference)),
        "observed_words": len(words(hypothesis)),
        "edits": score[0],
        "substitutions": score[1],
        "omissions": score[2],
        "additions": score[3],
        "wer": score[0] / len(words(reference)),
    }


def _system_class(edit: dict) -> tuple[str, str, str]:
    if edit["hypothesis_word"] in {"you", "know"} and edit["operation"] == "addition":
        return "a", "raw_decoder_clean_reference_addition", "raw-system-0-29.json:21; retained-acceptance-surfaces.json"
    if edit["reference_index"] in {0, 1, 2, 3}:
        return "d", "reference_leading_overhang", "bill-reference-source.jsonl:1; overlap-review second-opinion.md:7-8"
    if edit["hypothesis_word"] == "you're":
        return "d", "reference_omits_audible_sentence_start", "overlap-review second-opinion.md:23-25"
    if edit["reference_word"] == "define":
        return "d", "reference_lexical_error", "overlap-review second-opinion.md:26,34"
    if edit["reference_word"] == "book":
        return "d", "cut_before_reference_tail", "overlap-review second-opinion.md:28-33"
    raise AssertionError(f"unclassified alternation system edit: {edit}")


def main() -> int:
    retained = json.loads((EVIDENCE / "retained-acceptance-surfaces.json").read_text())
    bill = _record(EVIDENCE / "bill-reference-source.jsonl")
    keyu_fixture = json.loads((ROOT / "tests" / "e2e" / "fixtures" / "lane-microphone-reference.json").read_text())
    proposal = json.loads((EVIDENCE / "reference-correction-proposal.json").read_text())
    alternation = retained["cases"]["alternation"]
    overlap = retained["cases"]["overlap"]
    rows: list[dict] = []

    score, operations = _score(bill["text"], alternation["final"]["system"]["text"])
    assert score == (9, 1, 5, 3)
    for edit_index, edit in enumerate((row for row in operations if row["operation"] != "match"), 1):
        classification, cause, evidence = _system_class(edit)
        rows.append({
            "case": "alternation", "surface": "final", "lane": "system", "edit_index": edit_index,
            **edit, "class": classification, "cause": cause, "evidence": evidence,
        })

    for case_name, lane in (
        ("alternation", alternation["final"]["microphone"]),
        ("overlap", overlap["final"]["microphone"]),
    ):
        score, operations = _score(keyu_fixture["text"], lane["text"])
        assert score == (5, 0, 0, 5)
        for edit_index, edit in enumerate((row for row in operations if row["operation"] != "match"), 1):
            assert edit["operation"] == "addition"
            rows.append({
                "case": case_name, "surface": "final", "lane": "microphone", "edit_index": edit_index,
                **edit, "class": "a", "cause": "raw_decoder_clean_reference_addition",
                "evidence": "keyu-hf-witness.json: exact acceptance-gain witness; retained-acceptance-surfaces.json",
            })

    final_cases = {}
    for case_name, surface, lane in (
        ("alternation", alternation["final"], "system"),
        ("alternation", alternation["final"], "microphone"),
        ("overlap", overlap["final"], "microphone"),
    ):
        case_rows = [row for row in rows if row["case"] == case_name and row["lane"] == lane]
        final_cases[f"{case_name}.{lane}"] = {
            **surface[lane],
            "classes": dict(sorted(Counter(row["class"] for row in case_rows).items())),
            "attribution_status": "SUPPORTED",
        }

    corrected_bill = proposal["proposals"]["alternation_system_29s"]["text"]
    corrected_keyu = proposal["proposals"]["keyu_microphone_0_25_source_corpus"]["text"]
    corrected = {
        "alternation.system": _metrics(corrected_bill, alternation["final"]["system"]["text"]),
        "alternation.microphone": _metrics(corrected_keyu, alternation["final"]["microphone"]["text"]),
        "overlap.microphone": _metrics(corrected_keyu, overlap["final"]["microphone"]["text"]),
    }
    assert corrected["alternation.system"]["edits"] == 5
    assert corrected["alternation.microphone"]["edits"] == corrected["overlap.microphone"]["edits"] == 5

    pre_terminal = {}
    for lane in ("system", "microphone"):
        pre_terminal[f"alternation.{lane}"] = {
            **alternation["pre_terminal"][lane],
            "classes": {"a": None, "b": None, "c": None, "d": None},
            "attribution_status": "UNMEASURED",
            "unmeasured_edits": alternation["pre_terminal"][lane]["edits"],
            "reason": retained["pre_terminal_custody"]["reason"],
        }

    payload = {
        "schema": "moss-r4-alternation-attribution.v1",
        "verdict": "SUPPORTED_FINAL__UNMEASURED_PRE_TERMINAL",
        "finding": "Final failures are raw clean-reference additions plus Bill reference/cut defects; retained pre-terminal scores lack retained word streams.",
        "stage_invariant": "attribute each edit once at its first evidenced causal stage; never substitute a nonmatching replay",
        "cases": {"pre_terminal": pre_terminal, "final": final_cases, "post_correction": corrected},
        "rows": rows,
        "layer_checks": {
            "final_reopened_equal": True,
            "keyu_exact_gain_hf_matches_both_final_microphone_streams": True,
            "pre_terminal_text_retained": False,
            "nonmatching_local_replay_rejected": True,
            "class_b_final_count": 0,
            "class_c_final_count": 0,
        },
        "requests": {"follow_on_gpu": 0, "follow_on_budget": 10, "cumulative_gpu": 1, "campaign_budget": 40, "peak_in_flight": 0, "retries": 0},
    }
    (EVIDENCE / "attribution-alternation.json").write_text(json.dumps(payload, indent=2) + "\n")

    lines = [
        "# R4 alternation and microphone attribution",
        "",
        "**Verdict: final SUPPORTED; pre-terminal UNMEASURED.** All 19 retained final edits are attributable: 12 class-(a), 7 class-(d), 0 class-(b), 0 class-(c). Round 3 retained exact pre-terminal counts but not the 27 edited word rows.",
        "",
        "## Denominators and corrected replay",
        "",
        "| Surface | Lane | Retained score | Classes | Corrected-reference score |",
        "|---|---|---:|---|---:|",
        "| Pre-terminal alternation | system | 16/106 (2S/6D/8I) | UNMEASURED: 16 rows absent | UNMEASURED |",
        "| Pre-terminal alternation | microphone | 11/53 (1S/4D/6I) | UNMEASURED: 11 rows absent | UNMEASURED |",
        "| Final alternation | system | 9/106 (1S/5D/3I) | a=2, b=0, c=0, d=7 | 5/102 (1S/1D/3I) |",
        "| Final alternation | microphone | 5/53 (0S/0D/5I) | a=5, b=0, c=0, d=0 | 5/53 |",
        "| Final overlap | microphone | 5/53 (0S/0D/5I) | a=5, b=0, c=0, d=0 | 5/53 |",
        "",
        "The alternation-system correction removes the seven originally scored class-(d) edits, then exposes three decoder-surface edits the old reference masked (`market's` versus audible `market is`, plus terminal `the`). Together with `you know`, corrected WER is 5/102.",
        "",
        "## Per-final-edit evidence",
        "",
        "| Case | Lane | # | Edit | Reference -> observed | Class | Cause | Evidence line |",
        "|---|---|---:|---|---|:---:|---|---|",
    ]
    for row in rows:
        left = row["reference_word"] or "empty"
        right = row["hypothesis_word"] or "empty"
        lines.append(f"| {row['case']} | {row['lane']} | {row['edit_index']} | {row['operation']} | `{left}` -> `{right}` | {row['class']} | {row['cause']} | {row['evidence']} |")
    lines += [
        "",
        "## Evidence boundary",
        "",
        "- Bill: independent local HF review confirms the 29 s audio begins at `To`, says `market is`, `You're`, and `divine`, and ends before `the book` (`overlap-review/evidence/round4/overlap-review/second-opinion.md:7-11`).",
        "- Keyu: local offline HF at exact gain matches both retained final microphone word streams; the five scored additions are four fillers and repeated `deference` (`keyu-hf-witness.json`).",
        "- Cut: `tests/e2e/verify_demo_lanes.py:60-75` uses the corrected Keyu fixture but the coarse Bill row; correction remains proposal-only.",
        "- Pre-terminal: `738-direct.json` retained scores/operation totals only. SQLite retained terminal documents only. A local replay disagreed (15/106 and 13/53), so its text was rejected. Reproducing the historical run would exceed the 10-request cap (retained run: 59).",
        "- Falsifier: a recovered retained pre-terminal stream permits its 27 rows to be classified and can overturn UNMEASURED; any raw word absent from final publication overturns zero class-(b)/(c).",
        "- GPU follow-on: 0/10 requests, peak 0, retries 0. The existing campaign receipt remains 1/40.",
    ]
    (EVIDENCE / "attribution-alternation.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"final_rows": len(rows), "pre_terminal_unmeasured": sum(row["unmeasured_edits"] for row in pre_terminal.values()), "post_correction": corrected}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
