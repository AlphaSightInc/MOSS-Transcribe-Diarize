"""Seeded, locally generated microphone-noise events (no recorded audio; throwaway)."""
from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfilt, fftconvolve

RATE = 16_000


def db(x: float) -> float:
    return 10 ** (x / 20)


def _band(x, lo, hi):
    sos = butter(4, [lo, hi], btype="band", fs=RATE, output="sos")
    return sosfilt(sos, x)


def _low(x, hi):
    return sosfilt(butter(4, hi, btype="low", fs=RATE, output="sos"), x)


def _rms_to(x, dbfs):
    r = np.sqrt(np.mean(x ** 2)) or 1.0
    return x * db(dbfs) / r


def _peak_to(x, dbfs):
    p = np.max(np.abs(x)) or 1.0
    return x * db(dbfs) / p


def pink(n, rng):
    spectrum = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / RATE)
    f[0] = f[1]
    return np.fft.irfft(spectrum / np.sqrt(f), n)


def room_tone(n, rng, dbfs=-60.0):
    return _rms_to(pink(n, rng), dbfs)


def fan(n, rng, dbfs=-48.0):
    brown = np.cumsum(rng.standard_normal(n))
    brown = _band(brown - np.mean(brown), 40, 2000)
    t = np.arange(n) / RATE
    hum = sum(np.sin(2 * np.pi * h * t) / k for k, h in enumerate((120, 240, 360), 1))
    return _rms_to(_rms_to(brown, 0) + 0.3 * hum, dbfs)


def breath(rng, peak_dbfs=-42.0):
    dur = rng.uniform(.5, 1.1)
    n = int(dur * RATE)
    env = np.sin(np.linspace(0, np.pi, n)) ** 2
    x = _band(rng.standard_normal(n), 250, 3500) * env
    return _peak_to(x, peak_dbfs)


def keystrokes(rng, peak_dbfs=-26.0):
    keys = rng.integers(6, 22)
    out = []
    for _ in range(keys):
        gap = int(rng.uniform(.07, .28) * RATE)
        click = np.zeros(gap)
        m = int(.012 * RATE)
        burst = rng.standard_normal(m) * np.exp(-np.arange(m) / (.002 * RATE))
        burst = _band(np.concatenate([burst, np.zeros(64)]), 800, 7000)[:m]
        thump = np.sin(2 * np.pi * rng.uniform(90, 180) * np.arange(m) / RATE) * np.exp(-np.arange(m) / (.004 * RATE))
        click[:m] += burst + .4 * thump
        out.append(click * rng.uniform(.5, 1.0))
    return _peak_to(np.concatenate(out), peak_dbfs)


def cough(rng, peak_dbfs=-24.0):
    n = int(rng.uniform(.18, .35) * RATE)
    env = np.exp(-np.arange(n) / (.07 * RATE)) * (1 - np.exp(-np.arange(n) / (.005 * RATE)))
    src = rng.standard_normal(n) + .5 * np.sin(2 * np.pi * rng.uniform(110, 220) * np.arange(n) / RATE)
    x = sum(_band(src, f * .8, f * 1.2) * g for f, g in ((500, 1), (1500, .6), (2500, .3))) * env
    return _peak_to(x, peak_dbfs)


def throat(rng, peak_dbfs=-30.0):
    n = int(rng.uniform(.3, .6) * RATE)
    t = np.arange(n) / RATE
    f0 = rng.uniform(90, 140)
    x = np.sign(np.sin(2 * np.pi * f0 * t)) * (1 + .3 * rng.standard_normal(n))
    x = _band(x, 150, 1200) * np.sin(np.linspace(0, np.pi, n))
    return _peak_to(x, peak_dbfs)


def smack(rng, peak_dbfs=-34.0):
    n = int(.02 * RATE)
    x = _band(rng.standard_normal(n), 1000, 6000) * np.exp(-np.arange(n) / (.003 * RATE))
    return _peak_to(x, peak_dbfs)


def creak(rng, peak_dbfs=-32.0):
    n = int(rng.uniform(.25, .6) * RATE)
    t = np.arange(n) / RATE
    f = np.linspace(rng.uniform(150, 300), rng.uniform(400, 900), n)
    pulses = (np.sin(2 * np.pi * np.cumsum(f) / RATE) > .95).astype(float)
    x = _band(pulses + .2 * rng.standard_normal(n), 100, 3000) * np.hanning(n)
    return _peak_to(x, peak_dbfs)


def reverb(x, rng, rt60=.6):
    n = int(rt60 * RATE)
    ir = rng.standard_normal(n) * np.exp(-6.9 * np.arange(n) / n)
    ir[0] = 3
    return fftconvolve(x, ir)[:len(x)]


def distant(speech, rng, dbfs=-40.0):
    """Other people or a TV at a distance: low-passed, reverberant, quiet speech."""
    return _rms_to(reverb(_low(speech, 1800), rng), dbfs)


def aec_residual(system, rng, dbfs=-38.0):
    """Echo left after browser echo cancellation: short surviving fragments of far-end speech."""
    n = len(system)
    gate = np.zeros(n)
    i = 0
    while i < n:
        i += int(rng.uniform(.3, 1.5) * RATE)
        m = int(rng.uniform(.06, .25) * RATE)
        gate[i:i + m] = np.hanning(min(m, max(0, n - i)))
        i += m
    x = _band(system, 300, 3400) * gate
    return _rms_to(x, dbfs) if np.any(x) else x


EVENTS = {"breath": breath, "keys": keystrokes, "cough": cough, "throat": throat,
          "smack": smack, "creak": creak}


def scatter(n, rng, kinds, *, every=(2.0, 6.0), avoid=()):
    """Place events at random gaps, never inside `avoid` [(start_s, end_s)] local-speech turns."""
    out = np.zeros(n)
    events = []
    t = rng.uniform(.3, 2.0)
    while t < n / RATE - 1.5:
        kind = kinds[rng.integers(len(kinds))]
        x = EVENTS[kind](rng)
        end = t + len(x) / RATE
        if not any(a - .5 < end and t < b + .5 for a, b in avoid):
            s = int(t * RATE)
            x = x[:n - s]
            out[s:s + len(x)] += x
            events.append({"kind": kind, "start_s": round(t, 3), "end_s": round(end, 3)})
        t = end + rng.uniform(*every)
    return out, events
