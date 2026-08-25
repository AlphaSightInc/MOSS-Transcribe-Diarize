"""What a live span whose decode the grammar rejected is allowed to publish (plan §9.3, M1).

The table below is the whole measured surface: over the 184-span corpus of plan §9.2 -- the
1-minute trio, `acquired_jamie_dimon`, and `lex_adam_frank` simulated at the live grid --
exactly ten decodes parse to zero segments. Every one of them is here, with the decision the
gate comparison of `evidence/live-convergence-0824/M1a-salvage-gate-comparison/` measured for
it. The other 174 spans parse and never reach the classifier at all, which is why the salvage
surface is small enough to enumerate rather than sample.

Provenance: raw decoder answers from `prototypes/live-file-gap-emptyspan/out/d3.json` and
`out/p1-lex_adam_frank.json`; span bounds and freeze reasons from the checked-in baseline
`prototypes/live-file-gap-baseline-20260824/`. The rows are written out here rather than read
from those files so the decoder's actual answers are visible to a reader of this test, and
`test_the_table_still_matches_the_measurement_corpus` proves the two have not drifted.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from moss_transcribe_diarize.app.live_span_bounds import (
    LiveTranscriptDisposition,
    classify_live_transcript,
    render_segments,
    span_segments,
)

D = LiveTranscriptDisposition
REPO = Path(__file__).resolve().parents[1]
EMPTYSPAN = REPO / "prototypes/live-file-gap-emptyspan/out"

# case, span id, raw decode, span samples, freeze reason, expected disposition, published text
ZERO_PARSE_CORPUS = (
    (
        "lex_bill_ackman",
        2,
        "[S01] The difference between,[S01] you said the stock market.",
        40000,
        "hard_cap",
        D.SALVAGED,
        "[0][S01]The difference between, you said the stock market.[2.5]",
    ),
    (
        "acquired_jamie_dimon",
        22,
        "[0.15][S01] Last year, we had you on the video board at Chase.",
        40000,
        "hard_cap",
        D.SALVAGED,
        "[0.15][S01]Last year, we had you on the video board at Chase.[2.5]",
    ),
    # The six observed hallucinations. Every one sits on a span the endpointer froze for
    # silence, which is why the freeze-reason gate refuses them all without a phrase list.
    (
        "lex_javier_milei",
        3,
        "[0.00][S01]I'm sorry, I can't assist with that request.",
        23840,
        "leading_silence",
        D.REFUSED_GATE,
        "",
    ),
    (
        "lex_javier_milei",
        13,
        "[0.00][S01]I'm sorry, I can't assist with that request.",
        960,
        "leading_silence",
        D.REFUSED_GATE,
        "",
    ),
    (
        "acquired_jamie_dimon",
        6,
        "[0.00][S01]I'm sorry, I can't assist with that request.",
        4960,
        "leading_silence",
        D.REFUSED_GATE,
        "",
    ),
    (
        "lex_adam_frank",
        18,
        "[0.00][S01]I'm sorry, I can't assist with that request.",
        13920,
        "leading_silence",
        D.REFUSED_GATE,
        "",
    ),
    (
        "lex_adam_frank",
        47,
        "[0.00][S01]I'm sorry, I can't assist with that request.",
        640,
        "leading_silence",
        D.REFUSED_GATE,
        "",
    ),
    (
        "lex_adam_frank",
        62,
        "[0.00][S01]I'm sorry, I can't assist with that request.",
        4800,
        "leading_silence",
        D.REFUSED_GATE,
        "",
    ),
    # Real words on a silence-frozen span, refused with the hallucinations. The gate is a
    # statement about the span, not about how plausible the sentence reads.
    ("lex_javier_milei", 5, "[0.00][S01]Okay.", 25280, "leading_silence", D.REFUSED_GATE, ""),
    # The one span where gating on the freeze reason and gating on a recomputed speech ratio
    # disagree (plan §9.1). Publishing "And." earns no matched word and moves WER only by an
    # alignment accident; the campaign gates on words recovered, so it stays refused.
    ("lex_javier_milei", 31, "[0.00][S01]And.", 3840, "stop_flush", D.REFUSED_GATE, ""),
)

# Two-speaker hard-cap spans the saved corpus does not contain (plan §9.2 asks for them
# explicitly). They are where the interior-boundary rule is decided.
CONSTRUCTED_SPANS = (
    (
        "one turn the decoder labelled twice",
        "[S01] The difference between,[S01] you said the stock market.",
        D.SALVAGED,
        1,
    ),
    (
        "two speakers with the boundary the decoder emitted",
        "[S01] I think so[1.20][S02] and I agree",
        D.SALVAGED,
        2,
    ),
    ("two speakers, no boundary between them", "[0.10][S01] I think so[S02] and I agree", D.REFUSED_INTERIOR_BOUNDARY, 0),
    ("two speakers, no timestamps at all", "[S01] I think so[S02] and I agree", D.REFUSED_INTERIOR_BOUNDARY, 0),
    ("three speakers, one boundary missing", "[S01] first[1.00][S02] second[S03] third", D.REFUSED_INTERIOR_BOUNDARY, 0),
)

HARD_CAP_SAMPLES = 40000


@pytest.mark.parametrize("case,span_id,raw,samples,reason,expected,published", ZERO_PARSE_CORPUS)
def test_every_zero_parse_decode_in_the_corpus_gets_its_measured_decision(
    case, span_id, raw, samples, reason, expected, published
):
    outcome = classify_live_transcript(raw, sample_count=samples, freeze_reason=reason)

    assert outcome.disposition is expected, f"{case}#{span_id}: {outcome.reason}"
    assert outcome.transcript == published, f"{case}#{span_id}"
    assert outcome.publishes is bool(published), f"{case}#{span_id}"


@pytest.mark.parametrize("name,raw,expected,segment_count", CONSTRUCTED_SPANS)
def test_a_boundary_between_two_speakers_is_never_invented(name, raw, expected, segment_count):
    """The rule that keeps plan D5 true: identity may only ever see intervals the decoder drew.

    A guessed cross-speaker boundary is not a small timing error. The interval on either side
    of it holds the other voice's audio, and that audio becomes speaker evidence -- so a span
    the decoder left ambiguous is refused whole rather than split on a guess.
    """

    outcome = classify_live_transcript(raw, sample_count=HARD_CAP_SAMPLES, freeze_reason="hard_cap")

    assert outcome.disposition is expected, name
    assert len(outcome.segments) == segment_count, name


def test_the_two_speaker_salvage_publishes_disjoint_intervals_on_the_emitted_boundary():
    outcome = classify_live_transcript(
        "[S01] I think so[1.20][S02] and I agree", sample_count=HARD_CAP_SAMPLES, freeze_reason="hard_cap"
    )

    assert [(s.start, s.end, s.speaker) for s in outcome.segments] == [
        (0.0, 1.2, "S01"),
        (1.2, 2.5, "S02"),
    ]


def test_a_transcript_the_grammar_already_accepts_is_returned_untouched():
    """Salvage repairs; it does not rewrite. A parsing decode must survive the classifier."""

    text = "[0.51][S01]To figure out what something's worth.[1.77][2.22][S01]And you have[2.5]"

    outcome = classify_live_transcript(text, sample_count=HARD_CAP_SAMPLES, freeze_reason="hard_cap")

    assert outcome.disposition is D.PARSED
    assert outcome.transcript == text
    assert outcome.segments == span_segments(text, sample_count=HARD_CAP_SAMPLES)


def test_the_gate_is_what_refuses_the_hallucinations_not_the_words():
    """Move the same words onto a hard-cap span and they publish; the gate carries the load.

    Stated as a test because it is the one thing that could quietly stop being true. The
    module ships no list of refusal sentences -- measured over the corpus a phrase table
    refused nothing the gate had not already refused, and a table of English apologies is a
    fact about one decoder in one language, not a rule. What guards the meeting is that a
    span frozen on silence is never salvaged.
    """

    apology = "[0.00][S01]I'm sorry, I can't assist with that request."

    on_silence = classify_live_transcript(apology, sample_count=4960, freeze_reason="leading_silence")
    on_hard_cap = classify_live_transcript(apology, sample_count=HARD_CAP_SAMPLES, freeze_reason="hard_cap")

    assert on_silence.disposition is D.REFUSED_GATE
    # The residual the gate accepts, recorded rather than hidden: 0 of the 163 hard-cap spans
    # in the corpus produced boilerplate, because a hard cap is 2.5 s of unbroken speech by
    # construction. If that ever stops holding, this line is where it will be seen to.
    assert on_hard_cap.disposition is D.SALVAGED


@pytest.mark.parametrize(
    "raw,expected",
    (
        ("", D.EMPTY_TEXT),
        ("   ", D.EMPTY_TEXT),
        ("silence", D.REFUSED_GRAMMAR),
        ("[0.10]bare words[S01] then a speaker", D.REFUSED_GRAMMAR),
        ("[0.10][not a token]hello", D.REFUSED_GRAMMAR),
        ("[0.10][S01]", D.REFUSED_GRAMMAR),
    ),
)
def test_an_answer_in_no_grammar_at_all_is_refused_rather_than_guessed_at(raw, expected):
    assert classify_live_transcript(raw, sample_count=HARD_CAP_SAMPLES, freeze_reason="hard_cap").disposition is expected


def test_every_salvaged_transcript_is_a_parse_render_parse_fixed_point():
    """The published text must mean the same thing to the next reader as to this one.

    A live transcript is re-parsed and re-rendered downstream -- the identity sweep relabels
    by rendering a span again -- so a salvaged string that does not survive the round trip
    would drift words rather than labels the first time it was corrected.
    """

    for _, _, raw, samples, reason, expected, _ in ZERO_PARSE_CORPUS:
        if expected is not D.SALVAGED:
            continue
        outcome = classify_live_transcript(raw, sample_count=samples, freeze_reason=reason)
        reparsed = span_segments(outcome.transcript, sample_count=samples)
        assert reparsed, raw
        assert render_segments(reparsed, lambda segment: segment.speaker) == outcome.transcript


def test_a_salvaged_span_never_reaches_outside_its_own_audio():
    for _, _, raw, samples, reason, expected, _ in ZERO_PARSE_CORPUS:
        if expected is not D.SALVAGED:
            continue
        outcome = classify_live_transcript(raw, sample_count=samples, freeze_reason=reason)
        duration = samples / 16000.0
        assert all(0.0 <= s.start <= s.end <= duration for s in outcome.segments), raw


def test_the_table_still_matches_the_measurement_corpus():
    """The rows above are the corpus, not a paraphrase of it."""

    if not (EMPTYSPAN / "d3.json").is_file():
        pytest.skip("measurement corpus not present in this checkout")
    saved = {
        (row["case"], row["span_id"]): row["raw_text"]
        for row in json.loads((EMPTYSPAN / "d3.json").read_text(encoding="utf-8"))["raw"]
    }
    simulated = json.loads((EMPTYSPAN / "p1-lex_adam_frank.json").read_text(encoding="utf-8"))["spans"]
    saved.update(
        {("lex_adam_frank", span["span_id"]): span["raw_text"] for span in simulated if span["parsed_segments"] == 0}
    )

    table = {(case, span_id): raw for case, span_id, raw, *_ in ZERO_PARSE_CORPUS}
    assert table == saved
