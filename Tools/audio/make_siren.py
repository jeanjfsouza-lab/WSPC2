"""Synthesises the patrol car's siren: a dry, close-up electronic wail that loops without a seam.

  python Tools/audio/make_siren.py

Writes Saved/Audio/WSPC2_Siren_Wail.wav (mono, 48 kHz, 16 bit). Import it with Tools/audio/import_siren.py.

The City Sample siren recording is a distant street ambience (reverberant, stored at 1/8 volume), so on the
player's own car it sounded far away. This one is generated: no recording, no third-party rights.

The wail sweeps 650 Hz -> 1450 Hz and back in 4.6 s, like a mechanical-style electronic siren. The tone is a
band-limited square (odd harmonics) shaped like a horn loudspeaker: little bass, a strong 1-3 kHz band.
"""
import os
import wave

import numpy as np

RATE = 48000
CYCLE = 4.6            # seconds for one rise and fall
LOW, HIGH = 650.0, 1450.0
RISE = 0.42            # fraction of the cycle spent rising (the fall is slower, as on real units)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(os.path.dirname(HERE)), "Saved", "Audio")


def main():
    n = int(RATE * CYCLE)
    t = np.arange(n) / n

    # pitch moves on a musical (logarithmic) scale: smooth turn at the top and at the bottom
    up = 0.5 - 0.5 * np.cos(np.pi * np.clip(t / RISE, 0.0, 1.0))
    down = 0.5 + 0.5 * np.cos(np.pi * np.clip((t - RISE) / (1.0 - RISE), 0.0, 1.0))
    shape = np.where(t < RISE, up, down)
    freq = LOW * (HIGH / LOW) ** shape

    # make the loop seamless: the phase must advance by a whole number of turns over the cycle
    turns = np.sum(freq) / RATE
    freq *= np.round(turns) / turns
    phase = 2.0 * np.pi * np.cumsum(freq) / RATE

    signal = np.zeros(n)
    for harmonic in range(1, 16, 2):
        f = freq * harmonic
        # horn response: rolls off below ~700 Hz and above ~3.5 kHz, and nothing near Nyquist
        gain = (1.0 / harmonic) * (f / np.sqrt(f * f + 700.0 ** 2)) * (1.0 / np.sqrt(1.0 + (f / 3500.0) ** 4))
        gain = np.where(f < 0.45 * RATE, gain, 0.0)
        signal += gain * np.sin(harmonic * phase)

    # the driver gets a little louder as the pitch rises
    signal *= 0.8 + 0.2 * shape
    signal *= 0.89 / np.max(np.abs(signal))

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "WSPC2_Siren_Wail.wav")
    with wave.open(path, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes((signal * 32767.0).astype("<i2").tobytes())

    jump = abs(signal[0] - signal[-1])
    print("wrote %s: %.2f s, %d samples, loop seam step %.4f" % (path, n / RATE, n, jump))


if __name__ == "__main__":
    main()
