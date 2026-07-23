from __future__ import annotations

import pytest

from moss_transcribe_diarize.app.live_endpoint import (
    EndpointPolicy,
    EndpointPolicyConfig,
    EndpointPolicyError,
    EndpointSpan,
    SpeechObservation,
)


def obs(start: int, end: int, speech: bool, *, provider_endpoint_sample: int | None = None) -> SpeechObservation:
    return SpeechObservation(
        start_sample=start,
        end_sample=end,
        speech_present=speech,
        provider_endpoint_sample=provider_endpoint_sample,
        provider_reason="provider_end" if provider_endpoint_sample is not None else None,
    )


def assert_exact_partition(spans: tuple[EndpointSpan, ...], expected: list[tuple[int, int, str]]) -> None:
    assert [(span.start_sample, span.end_sample, span.reason) for span in spans] == expected
    for previous, current in zip(spans, spans[1:]):
        assert previous.end_sample == current.start_sample


def test_speech_observations_create_gap_free_padded_partitions():
    policy = EndpointPolicy(
        EndpointPolicyConfig(
            min_speech_samples=2,
            min_silence_samples=3,
            pre_speech_padding_samples=1,
            post_speech_padding_samples=1,
        )
    )

    assert policy.observe(obs(0, 5, False)) == ()
    leading = policy.observe(obs(5, 9, True))
    speech = policy.observe(obs(9, 12, False))
    trailing = policy.flush()

    assert_exact_partition(
        leading + speech + trailing,
        [
            (0, 4, "leading_silence"),
            (4, 10, "end_silence"),
            (10, 12, "flush"),
        ],
    )
    snapshot = policy.snapshot()
    assert snapshot.accepted_until_sample == 12
    assert snapshot.open_start_sample == 12


def test_provider_endpoint_hint_does_not_commit_a_span():
    policy = EndpointPolicy(
        EndpointPolicyConfig(
            min_speech_samples=1,
            min_silence_samples=2,
            post_speech_padding_samples=0,
        )
    )

    hinted = policy.observe(obs(0, 4, True, provider_endpoint_sample=3))
    assert hinted == ()

    ended = policy.observe(obs(4, 6, False))
    assert_exact_partition(ended, [(0, 4, "end_silence")])


def test_hard_cap_takes_precedence_over_speech_endpoint_and_flush():
    policy = EndpointPolicy(
        EndpointPolicyConfig(
            min_speech_samples=1,
            min_silence_samples=4,
            post_speech_padding_samples=0,
            hard_cap_samples=5,
        )
    )

    first = policy.observe(obs(0, 4, True))
    capped = policy.observe(obs(4, 9, False))
    flushed = policy.flush()

    assert first == ()
    assert_exact_partition(capped + flushed, [(0, 5, "hard_cap"), (5, 9, "flush")])


def test_reset_and_stop_close_exact_open_partitions_without_overlap():
    policy = EndpointPolicy(EndpointPolicyConfig(min_speech_samples=1, min_silence_samples=1))

    policy.observe(obs(0, 3, False))
    reset = policy.reset()
    policy.observe(obs(3, 7, True))
    stop = policy.stop()

    assert_exact_partition(reset + stop, [(0, 3, "reset"), (3, 7, "stop_flush")])
    assert policy.snapshot().stopped is True
    with pytest.raises(EndpointPolicyError, match="stopped"):
        policy.observe(obs(7, 8, False))


def test_observations_must_be_ordered_gap_free_and_valid():
    policy = EndpointPolicy(EndpointPolicyConfig(min_speech_samples=0, min_silence_samples=0))

    policy.observe(obs(0, 2, False))
    with pytest.raises(EndpointPolicyError, match="ordered and gap-free"):
        policy.observe(obs(3, 4, False))
    with pytest.raises(EndpointPolicyError, match="must advance"):
        policy.observe(obs(2, 2, False))
    with pytest.raises(EndpointPolicyError, match="provider endpoint hint"):
        policy.observe(obs(2, 4, False, provider_endpoint_sample=5))
