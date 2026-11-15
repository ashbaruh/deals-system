"""Synthesize an upbeat, royalty-free 124 BPM house loop (no samples, no copyright).

    python -m video.music out/loop.wav
16 bars, C - G - Am - F, four-on-the-floor kick, claps, open hats, offbeat chord stabs, bass and a pluck lead.
"""
from __future__ import annotations

import sys
import wave

import numpy as np

SR = 44100
BPM = 124
BEAT = 60 / BPM
BARS = 16
N = int(SR * BEAT * 4 * BARS)
rng = np.random.default_rng(7)


def midi(m):
    return 440 * 2 ** ((m - 69) / 12)


def env(n, a=0.002, d=0.2, s=0.0, r=0.0):
    t = np.arange(n) / SR
    e = np.where(t < a, t / max(a, 1e-6), s + (1 - s) * np.exp(-(t - a) / max(d, 1e-6)))
    return e


def lowpass(x, cutoff):
    from scipy.signal import butter, lfilter
    b, a = butter(2, cutoff / (SR / 2))
    return lfilter(b, a, x)


def highpass(x, cutoff):
    from scipy.signal import butter, lfilter
    b, a = butter(2, cutoff / (SR / 2), btype="high")
    return lfilter(b, a, x)


def saw(f, n, detune=(0.0,)):
    t = np.arange(n) / SR
    return sum(2 * ((t * f * (1 + d)) % 1) - 1 for d in detune) / len(detune)


def add(buf, sig, start):
    i = int(start * SR)
    j = min(len(buf), i + len(sig))
    buf[i:j] += sig[: j - i]


def kick():
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    f = 50 + 110 * np.exp(-t * 30)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7) * 1.0


def clap():
    n = int(0.25 * SR)
    x = highpass(rng.standard_normal(n), 900) * env(n, 0.001, 0.07)
    return x * 0.35


def hat(open_=False):
    n = int((0.18 if open_ else 0.05) * SR)
    return highpass(rng.standard_normal(n), 7000) * env(n, 0.001, 0.06 if open_ else 0.015) * 0.18


PROG = [(60, [60, 64, 67]), (55, [55, 59, 62]), (57, [57, 60, 64]), (53, [53, 57, 60])]   # C G Am F


def main(path: str) -> None:
    L = np.zeros(N + SR)
    R = np.zeros(N + SR)
    bar = BEAT * 4
    for b in range(BARS):
        root, chord = PROG[b % 4]
        t0 = b * bar
        for k in range(4):
            add(L, kick() * 0.9, t0 + k * BEAT); add(R, kick() * 0.9, t0 + k * BEAT)
            if k in (1, 3):
                c = clap(); add(L, c, t0 + k * BEAT); add(R, c * 0.9, t0 + k * BEAT)
            h = hat(open_=True); add(L, h * 0.7, t0 + k * BEAT + BEAT / 2); add(R, h, t0 + k * BEAT + BEAT / 2)
            for q in (0.25, 0.75):
                h2 = hat(); add(L, h2, t0 + k * BEAT + BEAT * q); add(R, h2 * 0.7, t0 + k * BEAT + BEAT * q)
            # offbeat chord stab
            n = int(BEAT * 0.45 * SR)
            st = sum(saw(midi(m + 12), n, (-0.004, 0.0, 0.005)) for m in chord) / 3
            st = lowpass(st, 3200) * env(n, 0.004, 0.09) * 0.22
            add(L, st, t0 + k * BEAT + BEAT / 2); add(R, st, t0 + k * BEAT + BEAT / 2)
            # bass: 8ths, octave bounce
            for e, oct_ in ((0, 0), (0.5, 12)):
                n = int(BEAT * 0.45 * SR)
                bs = lowpass(saw(midi(root - 24 + oct_), n), 700) * env(n, 0.003, 0.12, 0.3) * 0.32
                add(L, bs, t0 + k * BEAT + e * BEAT); add(R, bs, t0 + k * BEAT + e * BEAT)
        # pluck lead in the second half of every 8 bars
        if b % 8 >= 4:
            notes = [chord[2] + 12, chord[1] + 12, chord[0] + 12, chord[1] + 12, chord[2] + 12, chord[0] + 24, chord[2] + 12, chord[1] + 12]
            for i, m in enumerate(notes):
                n = int(BEAT * 0.5 * SR)
                t = np.arange(n) / SR
                p = (np.sin(2 * np.pi * midi(m) * t) + 0.3 * np.sin(4 * np.pi * midi(m) * t)) * env(n, 0.002, 0.11) * 0.14
                add(L, p * 0.8, t0 + i * BEAT / 2); add(R, p, t0 + i * BEAT / 2 + 0.012)
    L, R = L[:N], R[:N]
    # sidechain-style pump on everything except the kick is approximated by a gentle global pump
    t = np.arange(N) / SR
    pump = 0.75 + 0.25 * np.clip(((t % BEAT) / BEAT) * 3, 0, 1)
    L, R = L * pump, R * pump
    mx = max(np.abs(L).max(), np.abs(R).max())
    L, R = np.tanh(L / mx * 1.4) * 0.8, np.tanh(R / mx * 1.4) * 0.8
    data = (np.stack([L, R], 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(data.tobytes())


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "loop.wav")
