"""Signal observations, not an echo-suppression policy.

The WP3 bench falsified suppression at 99% explained energy on quiet local speech.
Keep the measured statistic available for attended capture; never alter nonzero PCM.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import correlate


def observe_capture_span(system, microphone, *, sample_rate: int, correlation: bool = False) -> dict[str, object]:
    """Observe already aligned lane samples; search the bench's measured 0–60 ms lag.

    Each span is independent. Echo arriving from before its left edge is unmodelled;
    this and nonlinear AEC can reduce the fraction. Neither value proves leakage.
    """
    system_nonzero = any(system)
    microphone_nonzero = any(microphone)
    result: dict[str, object] = {
        "system": {"decision": "decode" if system_nonzero else "skip-zero"},
        "microphone": {"decision": "decode" if microphone_nonzero else "skip-zero"},
        "playback_explained_fraction": None,
        "playback_delay_samples": None,
        "playback_gain": None,
        "leak_suppression": False,
    }
    if not correlation or not microphone_nonzero or not system_nonzero:
        return result
    system = np.asarray(system, dtype=np.float64)
    microphone = np.asarray(microphone, dtype=np.float64)
    energy = float(np.dot(microphone, microphone))
    max_delay = min(len(system) - 1, sample_rate * 60 // 1000)
    covariance = correlate(microphone, system, mode="full", method="fft")[
        len(system) - 1:len(system) + max_delay
    ]
    reference_energy = np.cumsum(system ** 2)[len(system) - 1 - np.arange(len(covariance))]
    explained = np.divide(covariance ** 2, reference_energy * energy,
                          out=np.zeros_like(covariance), where=reference_energy > 0)
    delay = int(np.argmax(explained))
    result.update(
        playback_explained_fraction=min(1.0, float(explained[delay])),
        playback_delay_samples=delay,
        playback_gain=float(covariance[delay] / reference_energy[delay]) if reference_energy[delay] else 0.0,
    )
    return result
