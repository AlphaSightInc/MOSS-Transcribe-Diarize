"""The documented quality exception: admitted, bounded, and always named.

The release mandate rules that a fully finalized, clean quality run whose macro lands within
5 % relative of its bound is a documented exception rather than a rejection.  These tests pin
that ruling to the numbers it was made about, and pin the boundary it must not exceed.
"""

from __future__ import annotations

import math

import pytest

from moss_transcribe_diarize import phase2_acceptance as acceptance
from moss_transcribe_diarize.phase2_acceptance import (
    QUALITY_BOUNDS,
    QUALITY_EXCEPTION_RELATIVE_TOLERANCE,
    quality_bound_status,
    quality_exception_records,
)

# Reported by the 2026-09-13 pre-admission run on both layers.  Every one of these was ruled an
# approved exception long before the evaluator could express it.
OBSERVED_2026_09_13 = (
    ("diarization_error_rate", 0.16254775),
    ("diarization_error_rate", 0.162575333333),
    ("matched_speaker_accuracy", 0.911502),
    ("matched_speaker_accuracy", 0.911478416667),
    ("reference_speech_der", 0.135589583333),
    ("reference_speech_der", 0.135626416667),
)


def _macro_within_bounds() -> dict[str, float]:
    return {name: bound for name, (_, bound) in QUALITY_BOUNDS.items()}


def _payload(macro: dict[str, object]) -> dict[str, object]:
    return {"predicates": [{"id": "quality_corpus", "gate": "G4", "raw": {"macro": macro}}]}


def test_a_macro_exactly_on_its_bound_is_strict_not_an_exception():
    for name, (_, bound) in QUALITY_BOUNDS.items():
        assert quality_bound_status(name, bound) == "strict"


@pytest.mark.parametrize(("name", "value"), OBSERVED_2026_09_13)
def test_the_ruled_exceptions_are_admitted(name, value):
    assert quality_bound_status(name, value) == "exception"


@pytest.mark.parametrize(("name", "value"), OBSERVED_2026_09_13)
def test_the_ruled_exceptions_are_named_in_the_record(name, value):
    macro = _macro_within_bounds()
    macro[name] = value
    records = quality_exception_records(_payload(macro), layer="deployed")
    assert len(records) == 1
    assert records[0].startswith(f"deployed:G4:quality_corpus:{name}=")
    assert "relative tolerance" in records[0]


def test_a_clean_run_inside_every_bound_records_no_exception():
    assert quality_exception_records(_payload(_macro_within_bounds()), layer="deployed") == []


def test_the_tolerance_boundary_is_inclusive_and_is_a_cliff():
    for name, (comparison, bound) in QUALITY_BOUNDS.items():
        direction = 1 if comparison == "max" else -1
        at = bound * (1 + direction * QUALITY_EXCEPTION_RELATIVE_TOLERANCE)
        beyond = bound * (1 + direction * (QUALITY_EXCEPTION_RELATIVE_TOLERANCE + 1e-4))
        assert quality_bound_status(name, at) == "exception", name
        assert quality_bound_status(name, beyond) == "failed", name


@pytest.mark.parametrize(
    "value", (math.nan, math.inf, -math.inf, True, False, None, "0.1", [], {})
)
def test_a_macro_that_is_not_a_real_number_fails(value):
    assert quality_bound_status("diarization_error_rate", value) == "failed"


def test_a_wildly_wrong_macro_still_fails_in_both_directions():
    assert quality_bound_status("diarization_error_rate", 0.9) == "failed"
    assert quality_bound_status("matched_speaker_accuracy", 0.1) == "failed"


def test_an_admitted_exception_is_not_reported_as_a_failure_reason():
    """A run that fails structurally must not blame a metric the mandate admits."""

    macro = _macro_within_bounds()
    macro["diarization_error_rate"] = 0.16254775  # admitted exception
    macro["final_wer"] = 0.5  # a genuine, large miss
    details = acceptance._quality_failure_details({"raw": {"macro": macro}})
    assert any("final_wer" in line for line in details)
    assert not any("diarization_error_rate" in line for line in details)


def test_exception_records_ignore_payloads_without_a_quality_predicate():
    assert quality_exception_records(None, layer="deployed") == []
    assert quality_exception_records({}, layer="deployed") == []
    assert quality_exception_records({"predicates": []}, layer="deployed") == []
    assert quality_exception_records(
        {"predicates": [{"id": "four_session_capacity", "raw": {"macro": {}}}]},
        layer="deployed",
    ) == []


def test_the_tolerance_is_the_ruled_five_percent():
    assert QUALITY_EXCEPTION_RELATIVE_TOLERANCE == 0.05
