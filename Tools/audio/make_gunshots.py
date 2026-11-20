"""Synthesises the gunner's weapon sounds: pistol, shotgun (with the pump), rifle, reload and weapon draw.

  python Tools/audio/make_gunshots.py

Writes Saved/Audio/WSPC2_Gun_<Name>.wav (mono, 48 kHz, 16 bit): Pistol, Shotgun, Rifle, Reload, Draw.
Import them with Tools/audio/import_gunshots.py.

Generated, not recorded: no third-party rights. A shot is four layers:
  crack   a few milliseconds of bright noise (the supersonic snap and the action),
  boom    low-passed noise that dies in 50-200 ms (the muzzle blast),
  thump   a falling sine (the chest punch),
  tail    a soft, slowly fading echo, as outdoors between buildings.
Mechanical noises (pump, magazine, slide) are short bursts of damped metallic resonances.
The random seed is fixed, so the same files come out every run.
"""
import os
import wave

import numpy as np

RATE = 48000
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(os.path.dirname(HERE)), "Saved", "Audio")
rng = np.random.default_rng(1977)


def shaped_noise(seconds, gain_of_freq):
    """White noise with its spectrum multiplied by gain_of_freq(f in Hz)."""
    n = int(RATE * seconds)
    spectrum = np.fft.rfft(rng.standard_normal(n))
    freqs = np.fft.rfftfreq(n, 1.0 / RATE)
    out = np.fft.irfft(spectrum * gain_of_freq(freqs), n)
    return out / (np.max(np.abs(out)) + 1e-9)


def lowpass(cut, order=2):
    return lambda f: 1.0 / np.sqrt(1.0 + (f / cut) ** (2 * order))


def band(low, high, order=2):
    return lambda f: (1.0 / np.sqrt(1.0 + (low / np.maximum(f, 1.0)) ** (2 * order))) / np.sqrt(1.0 + (f / high) ** (2 * order))


def envelope(n, attack, decay):
    """Rises in attack seconds, then falls by e every decay seconds."""
    t = np.arange(n) / RATE
    rise = np.clip(t / max(attack, 1e-4), 0.0, 1.0)
    return rise * np.exp(-np.maximum(t - attack, 0.0) / decay)


def place(buffer, sound, at, gain=1.0):
    start = int(at * RATE)
    end = min(len(buffer), start + len(sound))
    buffer[start:end] += gain * sound[:end - start]


def shot(length, crack_band, crack_decay, boom_cut, boom_decay, thump_from, thump_to, thump_decay, tail_cut, tail_decay,
         mix):
    n = int(RATE * length)
    crack = shaped_noise(length, band(*crack_band)) * envelope(n, 0.0003, crack_decay)
    boom = shaped_noise(length, lowpass(boom_cut, 2)) * envelope(n, 0.0008, boom_decay)
    t = np.arange(n) / RATE
    freq = thump_to + (thump_from - thump_to) * np.exp(-t / 0.03)
    thump = np.sin(2.0 * np.pi * np.cumsum(freq) / RATE) * envelope(n, 0.001, thump_decay)
    # the echo: quieter, duller, starts a moment later and fades slowly, with two late reflections
    tail = shaped_noise(length, lowpass(tail_cut, 1)) * envelope(n, 0.025, tail_decay)
    out = mix[0] * crack + mix[1] * boom + mix[2] * thump
    out[int(0.012 * RATE):] += mix[3] * tail[:n - int(0.012 * RATE)]
    place(out, (mix[1] * boom + mix[2] * thump) * 0.22, 0.083)
    place(out, (mix[1] * boom) * 0.12, 0.161)
    return out


def clack(freqs, decay, noise_cut=6000.0, length=0.09):
    """One metal-on-metal click: a noise tick plus a few damped resonances."""
    n = int(RATE * length)
    t = np.arange(n) / RATE
    out = shaped_noise(length, band(800.0, noise_cut)) * envelope(n, 0.0002, 0.004)
    for index, f in enumerate(freqs):
        out += (0.5 / (index + 1)) * np.sin(2.0 * np.pi * f * t + rng.uniform(0, 6.28)) * np.exp(-t / decay)
    return out


def slide(length, low=1500.0, high=7000.0):
    """Metal parts sliding: a short band of rough noise."""
    n = int(RATE * length)
    grain = 1.0 + 0.6 * np.sign(np.sin(2.0 * np.pi * 180.0 * np.arange(n) / RATE + rng.uniform(0, 6.28)))
    return shaped_noise(length, band(low, high)) * envelope(n, length * 0.3, length * 0.4) * grain * 0.35


def pistol():
    return shot(0.75, (1500.0, 9000.0), 0.0025, 2200.0, 0.045, 160.0, 70.0, 0.05, 1500.0, 0.16,
                (0.9, 1.0, 0.55, 0.16))


def rifle():
    # short tail: at 11 rounds a second the echoes of a burst must not turn into mush
    return shot(0.55, (2500.0, 12000.0), 0.0018, 3000.0, 0.035, 190.0, 80.0, 0.035, 1800.0, 0.11,
                (1.0, 0.95, 0.45, 0.14))


def shotgun():
    out = shot(1.3, (900.0, 7000.0), 0.004, 1300.0, 0.11, 120.0, 45.0, 0.09, 1000.0, 0.3,
               (0.7, 1.0, 0.8, 0.2))
    # the pump, back and forward, after the recoil
    out = np.concatenate([out, np.zeros(int(0.1 * RATE))])
    place(out, slide(0.08, 900.0, 5000.0), 0.50, 0.5)
    place(out, clack([1850.0, 3120.0, 4700.0], 0.018), 0.57, 0.55)
    place(out, slide(0.07, 900.0, 5000.0), 0.70, 0.45)
    place(out, clack([2300.0, 3500.0, 5200.0], 0.015), 0.76, 0.6)
    return out


def reload():
    out = np.zeros(int(1.4 * RATE))
    place(out, clack([2600.0, 4100.0], 0.012), 0.05, 0.45)              # release button
    place(out, slide(0.12, 1200.0, 6000.0), 0.08, 0.5)                  # magazine slides out
    place(out, slide(0.18, 1200.0, 6000.0), 0.62, 0.5)                  # new magazine goes in
    place(out, clack([1700.0, 2900.0, 4300.0], 0.02, 5000.0), 0.80, 0.8)  # seated
    place(out, slide(0.1, 1500.0, 8000.0), 1.05, 0.45)                  # slide / charging handle back
    place(out, clack([2100.0, 3600.0, 5600.0], 0.016), 1.17, 0.85)      # and home
    return out


def draw():
    out = np.zeros(int(0.45 * RATE))
    place(out, shaped_noise(0.25, band(300.0, 3000.0)) * envelope(int(0.25 * RATE), 0.08, 0.06), 0.0, 0.25)  # cloth
    place(out, clack([2400.0, 3900.0], 0.012), 0.2, 0.5)
    place(out, clack([1900.0, 3300.0, 5000.0], 0.014), 0.29, 0.6)
    return out


def write(name, signal, peak):
    signal = signal * (peak / (np.max(np.abs(signal)) + 1e-9))
    fade = int(0.01 * RATE)
    signal[-fade:] *= np.linspace(1.0, 0.0, fade)
    path = os.path.join(OUT, "WSPC2_Gun_%s.wav" % name)
    with wave.open(path, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes((np.clip(signal, -1.0, 1.0) * 32767.0).astype("<i2").tobytes())
    print("wrote %s: %.2f s" % (path, len(signal) / RATE))


def main():
    os.makedirs(OUT, exist_ok=True)
    write("Pistol", pistol(), 0.93)
    write("Shotgun", shotgun(), 0.97)
    write("Rifle", rifle(), 0.93)
    write("Reload", reload(), 0.7)
    write("Draw", draw(), 0.6)


if __name__ == "__main__":
    main()
