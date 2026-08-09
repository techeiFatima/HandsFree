"""Synthesize media/beat_track.wav — the demo song.

32 seconds at 120 BPM: four-on-the-floor kick, offbeat hats, a two-bar bass
line. Deliberately mechanical — the point is a beat so obvious the LED pulse
reads from the back of the room, and no copyright surprises on a stream.

    python -m handsfree.make_demo_track
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

SR = 44100
BPM = 120.0
SECONDS = 32.0
OUT = Path(__file__).resolve().parents[1] / "media" / "beat_track.wav"


def _kick(t: np.ndarray) -> np.ndarray:
    # pitch-swept sine with a fast decay
    f = 120.0 * np.exp(-t * 18.0) + 45.0
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9.0)


def _hat(t: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    return rng.standard_normal(t.size) * np.exp(-t * 60.0) * 0.25


def main() -> Path:
    rng = np.random.default_rng(9)
    n = int(SR * SECONDS)
    out = np.zeros(n)
    beat_s = 60.0 / BPM

    hit_t = np.arange(0, 0.35, 1 / SR)
    kick = _kick(hit_t)
    hat = _hat(hit_t, rng)

    b = 0.0
    while b < SECONDS - 0.4:
        i = int(b * SR)
        out[i:i + kick.size] += kick
        j = int((b + beat_s / 2) * SR)
        if j + hat.size < n:
            out[j:j + hat.size] += hat
        b += beat_s

    # two-bar bass line, root then fifth
    tt = np.arange(n) / SR
    bar = 4 * beat_s
    freq = np.where((tt // bar) % 2 == 0, 55.0, 82.4)
    out += 0.22 * np.sign(np.sin(2 * np.pi * freq * tt)) * (0.5 + 0.5 * np.sin(2 * np.pi * tt / bar))

    out /= np.max(np.abs(out)) * 1.05

    import soundfile as sf
    OUT.parent.mkdir(exist_ok=True)
    sf.write(OUT, out.astype(np.float32), SR)
    print(f"[make_demo_track] wrote {OUT} ({SECONDS:.0f}s @ {BPM:.0f} BPM)")
    return OUT


if __name__ == "__main__":
    main()
