from __future__ import annotations

from dataclasses import dataclass


class EndpointPolicyError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SpeechObservation:
    start_sample: int
    end_sample: int
    speech_present: bool
    confidence: float | None = None
    provider_endpoint_sample: int | None = None
    provider_reason: str | None = None


@dataclass(frozen=True, slots=True)
class EndpointPolicyConfig:
    min_speech_samples: int
    min_silence_samples: int
    pre_speech_padding_samples: int = 0
    post_speech_padding_samples: int = 0
    hard_cap_samples: int | None = None


@dataclass(frozen=True, slots=True)
class EndpointSpan:
    start_sample: int
    end_sample: int
    reason: str

    @property
    def sample_count(self) -> int:
        return self.end_sample - self.start_sample


@dataclass(frozen=True, slots=True)
class EndpointPolicySnapshot:
    accepted_until_sample: int
    open_start_sample: int
    speech_active: bool
    stopped: bool


class EndpointPolicy:
    """Application-owned endpoint state for exact sample partitions."""

    def __init__(self, config: EndpointPolicyConfig):
        _validate_config(config)
        self.config = config
        self._accepted_until = 0
        self._open_start = 0
        self._speech_candidate_start: int | None = None
        self._speech_candidate_samples = 0
        self._speech_active = False
        self._last_speech_end: int | None = None
        self._stopped = False

    def observe(self, observation: SpeechObservation) -> tuple[EndpointSpan, ...]:
        self._ensure_open()
        _validate_observation(observation)
        if observation.start_sample != self._accepted_until:
            raise EndpointPolicyError("speech observations must be ordered and gap-free.")

        spans: list[EndpointSpan] = []
        start = observation.start_sample
        while start < observation.end_sample:
            hard_boundary = self._next_hard_boundary()
            end = observation.end_sample
            hit_hard_cap = hard_boundary is not None and start < hard_boundary <= observation.end_sample
            if hit_hard_cap:
                end = hard_boundary

            spans.extend(self._process_piece(start, end, observation.speech_present))
            if hit_hard_cap:
                spans.append(self._emit_until(end, "hard_cap"))
                self._reset_speech_state()
            start = end

        return tuple(spans)

    def flush(self) -> tuple[EndpointSpan, ...]:
        self._ensure_open()
        return self._close_open_partition("flush")

    def reset(self) -> tuple[EndpointSpan, ...]:
        self._ensure_open()
        spans = self._close_open_partition("reset")
        self._reset_speech_state()
        return spans

    def stop(self) -> tuple[EndpointSpan, ...]:
        self._ensure_open()
        spans = self._close_open_partition("stop_flush")
        self._reset_speech_state()
        self._stopped = True
        return spans

    def snapshot(self) -> EndpointPolicySnapshot:
        return EndpointPolicySnapshot(
            accepted_until_sample=self._accepted_until,
            open_start_sample=self._open_start,
            speech_active=self._speech_active,
            stopped=self._stopped,
        )

    def _process_piece(self, start: int, end: int, speech_present: bool) -> tuple[EndpointSpan, ...]:
        self._accepted_until = end
        if speech_present:
            return self._observe_speech(start, end)
        return self._observe_silence(start, end)

    def _observe_speech(self, start: int, end: int) -> tuple[EndpointSpan, ...]:
        if self._speech_candidate_start is None:
            self._speech_candidate_start = start
            self._speech_candidate_samples = 0
        self._speech_candidate_samples += end - start

        spans: list[EndpointSpan] = []
        if not self._speech_active and self._speech_candidate_samples >= self.config.min_speech_samples:
            assert self._speech_candidate_start is not None
            padded_start = max(
                self._open_start,
                self._speech_candidate_start - self.config.pre_speech_padding_samples,
            )
            if padded_start > self._open_start:
                spans.append(self._emit_until(padded_start, "leading_silence"))
            self._speech_active = True

        if self._speech_active:
            self._last_speech_end = end
        return tuple(spans)

    def _observe_silence(self, start: int, end: int) -> tuple[EndpointSpan, ...]:
        del start
        if not self._speech_active:
            self._speech_candidate_start = None
            self._speech_candidate_samples = 0
            return ()

        assert self._last_speech_end is not None
        observed_silence = end - self._last_speech_end
        required = max(self.config.min_silence_samples, self.config.post_speech_padding_samples)
        if observed_silence < required:
            return ()

        endpoint = self._last_speech_end + self.config.post_speech_padding_samples
        span = self._emit_until(endpoint, "end_silence")
        self._reset_speech_state()
        return (span,)

    def _close_open_partition(self, reason: str) -> tuple[EndpointSpan, ...]:
        spans: list[EndpointSpan] = []
        while True:
            hard_boundary = self._next_hard_boundary()
            if hard_boundary is None or hard_boundary >= self._accepted_until:
                break
            spans.append(self._emit_until(hard_boundary, "hard_cap"))
            self._reset_speech_state()
        if self._accepted_until > self._open_start:
            spans.append(self._emit_until(self._accepted_until, reason))
        return tuple(spans)

    def _emit_until(self, end_sample: int, reason: str) -> EndpointSpan:
        if end_sample <= self._open_start:
            raise EndpointPolicyError("endpoint span must advance.")
        if end_sample > self._accepted_until:
            raise EndpointPolicyError("endpoint span cannot exceed observed samples.")
        span = EndpointSpan(self._open_start, end_sample, reason)
        self._open_start = end_sample
        return span

    def _next_hard_boundary(self) -> int | None:
        if self.config.hard_cap_samples is None:
            return None
        return self._open_start + self.config.hard_cap_samples

    def _reset_speech_state(self) -> None:
        self._speech_candidate_start = None
        self._speech_candidate_samples = 0
        self._speech_active = False
        self._last_speech_end = None

    def _ensure_open(self) -> None:
        if self._stopped:
            raise EndpointPolicyError("endpoint policy is stopped.")


def _validate_config(config: EndpointPolicyConfig) -> None:
    for name in ("min_speech_samples", "min_silence_samples", "pre_speech_padding_samples", "post_speech_padding_samples"):
        value = getattr(config, name)
        if value < 0:
            raise ValueError(f"{name} must be non-negative.")
    if config.hard_cap_samples is not None and config.hard_cap_samples <= 0:
        raise ValueError("hard_cap_samples must be positive when provided.")


def _validate_observation(observation: SpeechObservation) -> None:
    if observation.start_sample < 0:
        raise EndpointPolicyError("observation start_sample must be non-negative.")
    if observation.end_sample <= observation.start_sample:
        raise EndpointPolicyError("observation end_sample must advance.")
    if observation.provider_endpoint_sample is not None:
        if not observation.start_sample <= observation.provider_endpoint_sample <= observation.end_sample:
            raise EndpointPolicyError("provider endpoint hint must fall inside the observation.")
