import json
from collections import Counter
from pathlib import Path

import pytest

from moss_transcribe_diarize.lane_word_oracle import words


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence" / "round4" / "overlap"


def _attribution() -> dict:
    return json.loads((EVIDENCE / "attribution-alternation.json").read_text())


@pytest.mark.xfail(
    strict=True,
    reason="R4 follow-on: the source Keyu row omits the audible five-word leading sentence tail",
)
def test_r4_keyu_source_reference_matches_audited_audio_population() -> None:
    current = json.loads((EVIDENCE / "keyu-reference-source.jsonl").read_text())
    proposal = json.loads((EVIDENCE / "reference-correction-proposal.json").read_text())
    corrected = proposal["proposals"]["keyu_microphone_0_25_source_corpus"]
    assert (current["start"], current["end"], words(current["text"])) == (
        corrected["start"],
        corrected["end"],
        words(corrected["text"]),
    )


def test_r4_final_attribution_has_exact_lane_denominators_and_classes() -> None:
    result = _attribution()
    cases = result["cases"]["final"]
    assert (cases["alternation.system"]["edits"], cases["alternation.system"]["reference_words"]) == (9, 106)
    assert cases["alternation.system"]["classes"] == {"a": 2, "d": 7}
    for name in ("alternation.microphone", "overlap.microphone"):
        assert (cases[name]["edits"], cases[name]["reference_words"]) == (5, 53)
        assert cases[name]["classes"] == {"a": 5}
    assert Counter(row["class"] for row in result["rows"]) == {"a": 12, "d": 7}
    assert len(result["rows"]) == 19
    assert all(row["evidence"] for row in result["rows"])


def test_r4_corrected_reference_scores_keep_decoder_surface_edits() -> None:
    corrected = _attribution()["cases"]["post_correction"]
    assert corrected["alternation.system"] == {
        "reference_words": 102,
        "observed_words": 104,
        "edits": 5,
        "substitutions": 1,
        "omissions": 1,
        "additions": 3,
        "wer": 5 / 102,
    }
    for name in ("alternation.microphone", "overlap.microphone"):
        assert corrected[name]["edits"] == 5
        assert corrected[name]["reference_words"] == 53


def test_r4_pre_terminal_counts_are_preserved_without_invented_rows() -> None:
    result = _attribution()
    pre = result["cases"]["pre_terminal"]
    assert (pre["alternation.system"]["edits"], pre["alternation.system"]["unmeasured_edits"]) == (16, 16)
    assert (pre["alternation.microphone"]["edits"], pre["alternation.microphone"]["unmeasured_edits"]) == (11, 11)
    assert all(row["attribution_status"] == "UNMEASURED" for row in pre.values())
    assert result["layer_checks"]["nonmatching_local_replay_rejected"] is True
