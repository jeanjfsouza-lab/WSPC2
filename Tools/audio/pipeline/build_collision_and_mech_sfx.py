"""Builds the collision and mechanical sound effects of the vehicles (CC0 foley + DSP synthesis).

Every file is 48 kHz, 16-bit PCM, mono. One-shots peak at -1 dBFS; loops are cut circularly (the tail is
crossfaded into the head with equal power), so they repeat without a seam, and sit at a common loudness.
Kenney's CC0 impact pack (fetch_free_sfx.py) gives the metal, plate, punch and glass hits; everything else
(sub-bass, metal modes, crackle, scraping, tyres, turbo, gears, backfire, diesel knock) is synthesised here.
The random generator is seeded per file, so a rebuild gives the same sounds.

  Saved/Audio/Pipeline/.venv/Scripts/python.exe Tools/audio/pipeline/build_collision_and_mech_sfx.py

Inputs:  Saved/Audio/Pipeline/raw_sfx/kenney_impact_sounds/**.ogg
Outputs: Saved/Audio/Pipeline/output/collisions/{impacts,crunch,glass,scrape}/WSPC2_Col_*.wav
         Saved/Audio/Pipeline/output/mechanical/WSPC2_Mech_*.wav
         Saved/Audio/Pipeline/output/CollisionAudioManifest.json (file, category, loop, length, peak, RMS, sources)
"""
import glob
import json
import os
import zlib

import numpy as np
import soundfile as sf
from scipy import signal

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
PIPE = os.path.join(ROOT, "Saved", "Audio", "Pipeline")
KENNEY = os.path.join(PIPE, "raw_sfx", "kenney_impact_sounds")
OUT_COL = os.path.join(PIPE, "output", "collisions")
OUT_MECH = os.path.join(PIPE, "output", "mechanical")
MANIFEST = os.path.join(PIPE, "output", "CollisionAudioManifest.json")

SR = 48000
ONE_SHOT_PEAK_DB = -1.0
LOOP_RMS_DB = -18.0
LOOP_PEAK_DB = -1.0
ENTRIES = []


# --- basic tools ------------------------------------------------------------------------------------------

def rng_for(name):
    return np.random.default_rng(zlib.crc32(name.encode()))


def t_axis(seconds):
    return np.arange(int(seconds * SR)) / SR


def db(x):
    return 10 ** (x / 20.0)


def sos(kind, freq, order=4):
    nyq = SR / 2
    if isinstance(freq, (list, tuple)):
        lo, hi = max(10.0, freq[0]), min(nyq * 0.98, freq[1])
        return signal.butter(order, [lo / nyq, hi / nyq], btype=kind, output="sos")
    return signal.butter(order, min(freq, nyq * 0.98) / nyq, btype=kind, output="sos")


def lp(x, f, order=4):
    return signal.sosfilt(sos("lowpass", f, order), x)


def hp(x, f, order=4):
    return signal.sosfilt(sos("highpass", f, order), x)


def bp(x, lo, hi, order=4):
    return signal.sosfilt(sos("bandpass", (lo, hi), order), x)


def resonator(x, freq, q):
    """Two-pole resonant band-pass (one metal mode)."""
    b, a = signal.iirpeak(min(freq, SR * 0.45) / (SR / 2), q)
    return signal.lfilter(b, a, x)


def pink(rng, n):
    white = rng.standard_normal(n)
    b = [0.049922035, -0.095993537, 0.050612699, -0.004408786]
    a = [1, -2.494956002, 2.017265875, -0.522189400]
    return signal.lfilter(b, a, white) * 6.0


def brown(rng, n):
    y = np.cumsum(rng.standard_normal(n))
    return hp(y - y.mean(), 20, 2) * 0.02


def env_exp(n, attack_s, decay_s):
    t = np.arange(n) / SR
    a = np.clip(t / max(attack_s, 1e-4), 0, 1)
    return a * np.exp(-np.maximum(t - attack_s, 0) / max(decay_s, 1e-4))


def fit(x, n):
    return x[:n] if len(x) >= n else np.pad(x, (0, n - len(x)))


def place(dst, src, start):
    start = int(start)
    if start < 0:
        src, start = src[-start:], 0
    if start >= len(dst) or len(src) == 0:
        return
    end = min(len(dst), start + len(src))
    dst[start:end] += src[:end - start]


def place_circular(dst, src, start):
    """Adds src at start, wrapping what runs past either end around the buffer (for loops)."""
    idx = (int(start) + np.arange(len(src))) % len(dst)
    np.add.at(dst, idx, src)


def saturate(x, drive):
    return np.tanh(x * drive) / np.tanh(drive)


def resample(x, ratio):
    """ratio < 1 lowers the pitch (and lengthens the sound)."""
    up, down = 1000, int(round(1000 * ratio))
    return signal.resample_poly(x, up, down)


_kenney_cache = {}


def kenney(family, index):
    files = sorted(glob.glob(os.path.join(KENNEY, "**", f"{family}_*.ogg"), recursive=True))
    if not files:
        raise SystemExit(f"Kenney family missing: {family} (run fetch_free_sfx.py)")
    path = files[index % len(files)]
    if path not in _kenney_cache:
        data, rate = sf.read(path, dtype="float64", always_2d=True)
        mono = data.mean(axis=1)
        if rate != SR:
            g = np.gcd(rate, SR)
            mono = signal.resample_poly(mono, SR // g, rate // g)
        _kenney_cache[path] = mono / max(1e-9, np.max(np.abs(mono)))
    return _kenney_cache[path].copy(), os.path.relpath(path, KENNEY).replace("\\", "/")


def metal_modes(rng, n, base_lo, base_hi, count, decay_lo, decay_hi, q_lo=30, q_hi=120):
    """Sum of decaying sinusoids at inharmonic frequencies: a struck sheet-metal panel."""
    t = np.arange(n) / SR
    out = np.zeros(n)
    for _ in range(count):
        f = rng.uniform(base_lo, base_hi)
        d = rng.uniform(decay_lo, decay_hi)
        out += rng.uniform(0.3, 1.0) * np.sin(2 * np.pi * f * t + rng.uniform(0, 6.28)) * np.exp(-t / d)
    return out / max(1, count) ** 0.5


def sub_drop(n, f_start, f_end, sweep_s, decay_s):
    """Pitched-down sub-bass thump (the mass of a car behind a hit)."""
    t = np.arange(n) / SR
    f = f_end + (f_start - f_end) * np.exp(-t / max(sweep_s / 3.0, 1e-3))
    phase = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(phase) * env_exp(n, 0.002, decay_s)


def make_loop(x, crossfade_s):
    """Circular loop: the extra tail is crossfaded (equal power) into the head."""
    xf = int(crossfade_s * SR)
    body, tail = x[:-xf], x[-xf:]
    fade = np.linspace(0, np.pi / 2, xf)
    body = body.copy()
    body[:xf] = body[:xf] * np.sin(fade) + tail * np.cos(fade)
    return body


def write(folder, name, x, category, loop=False, sources=(), meta=None):
    x = np.asarray(x, dtype=np.float64)
    x = x - np.mean(x) if loop else x
    if loop:
        rms = np.sqrt(np.mean(x ** 2))
        x = x * db(LOOP_RMS_DB) / max(rms, 1e-12)
        peak = np.max(np.abs(x))
        if peak > db(LOOP_PEAK_DB):
            x = x * db(LOOP_PEAK_DB) / peak
    else:
        fade = min(len(x), int(0.004 * SR))
        x[-fade:] *= np.linspace(1, 0, fade)
        x = x * db(ONE_SHOT_PEAK_DB) / max(np.max(np.abs(x)), 1e-12)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name + ".wav")
    sf.write(path, x.astype(np.float32), SR, subtype="PCM_16")
    rel = os.path.relpath(path, os.path.join(PIPE, "output")).replace("\\", "/")
    ENTRIES.append({"name": name, "file": rel, "category": category, "loop": loop,
                    "seconds": round(len(x) / SR, 3),
                    "peakDb": round(20 * np.log10(max(np.max(np.abs(x)), 1e-12)), 2),
                    "rmsDb": round(20 * np.log10(max(np.sqrt(np.mean(x ** 2)), 1e-12)), 2),
                    "sources": sorted(set(sources)), **(meta or {})})


# --- collisions -------------------------------------------------------------------------------------------

def impacts():
    folder = os.path.join(OUT_COL, "impacts")
    for tier, count in (("Light", 8), ("Medium", 8), ("Heavy", 8)):
        for i in range(count):
            name = f"WSPC2_Col_Impact_{tier}_{i + 1:02d}"
            rng = rng_for(name)
            src = []
            if tier == "Light":
                n = int(rng.uniform(0.45, 0.65) * SR)
                a, s1 = kenney("impactPlate_light", i)
                b, s2 = kenney("impactMetal_light", i + 2)
                out = fit(resample(a, rng.uniform(0.75, 0.9)), n) * 0.8 + fit(resample(b, rng.uniform(0.7, 0.85)), n) * 0.5
                out += metal_modes(rng, n, 500, 2600, 6, 0.04, 0.12) * 0.25
                out += lp(rng.standard_normal(n), 3000) * env_exp(n, 0.001, 0.02) * 0.3
                src += [s1, s2]
            elif tier == "Medium":
                n = int(rng.uniform(0.75, 1.0) * SR)
                a, s1 = kenney("impactMetal_medium", i)
                b, s2 = kenney("impactPlate_medium", i + 1)
                c, s3 = kenney("impactPunch_medium", i + 3)
                out = fit(resample(a, rng.uniform(0.6, 0.75)), n) * 0.7 + fit(resample(b, rng.uniform(0.6, 0.75)), n) * 0.6
                out += fit(resample(c, rng.uniform(0.7, 0.85)), n) * 0.6
                out += sub_drop(n, 150, 80, 0.06, 0.18) * 0.5
                out += metal_modes(rng, n, 300, 1800, 8, 0.08, 0.25) * 0.3
                out = saturate(out, 1.4)
                src += [s1, s2, s3]
            else:
                n = int(rng.uniform(1.1, 1.6) * SR)
                a, s1 = kenney("impactMetal_heavy", i)
                b, s2 = kenney("impactPunch_heavy", i + 2)
                c, s3 = kenney("impactPlate_heavy", i + 1)
                out = fit(resample(a, rng.uniform(0.5, 0.65)), n) * 0.8 + fit(resample(b, rng.uniform(0.6, 0.75)), n) * 0.7
                out += fit(resample(c, rng.uniform(0.55, 0.7)), n) * 0.5
                out += sub_drop(n, 105, 45, 0.09, 0.35) * 0.9
                crunch = bp(rng.standard_normal(n), 400, 4000) * env_exp(n, 0.002, 0.08)
                out += crunch * 0.35 + metal_modes(rng, n, 200, 1400, 10, 0.15, 0.45) * 0.35
                out = saturate(out, 2.2)
            write(folder, name, out, "impact_" + tier.lower(), sources=src)


def crunches():
    folder = os.path.join(OUT_COL, "crunch")
    for tier, count, length in (("Med", 8, (0.45, 0.9)), ("Heavy", 8, (0.75, 1.4))):
        for i in range(count):
            name = f"WSPC2_Col_MetalCrunch_{tier}_{i + 1:02d}"
            rng = rng_for(name)
            n = int(rng.uniform(*length) * SR)
            out = np.zeros(n)
            src = []
            # creaks: short metal pings and noise bursts, densest right after the attack
            grains = int(rng.uniform(18, 30) * (1.6 if tier == "Heavy" else 1.0))
            for _ in range(grains):
                pos = (rng.beta(1.2, 3.0)) * (n - int(0.12 * SR))
                g = int(rng.uniform(0.015, 0.07) * SR)
                ping = metal_modes(rng, g, 250, 3200, 3, 0.01, 0.05) * rng.uniform(0.4, 1.0)
                burst = bp(rng.standard_normal(g), rng.uniform(300, 900), rng.uniform(2500, 6000)) * env_exp(g, 0.001, 0.012)
                place(out, ping + burst * 0.6, pos)
            tin, s1 = kenney("impactTin_medium", i)
            metal, s2 = kenney("impactMetal_medium" if tier == "Med" else "impactMetal_heavy", i + 4)
            out += fit(resample(tin, rng.uniform(0.45, 0.6)), n) * 0.5 + fit(resample(metal, rng.uniform(0.4, 0.55)), n) * 0.5
            out *= env_exp(n, rng.uniform(0.010, 0.025), length[1] * 0.45)
            out = saturate(out, 1.6)
            src += [s1, s2]
            write(folder, name, out, "crunch_" + tier.lower(), sources=src)


def glass():
    folder = os.path.join(OUT_COL, "glass")
    for i in range(6):
        name = f"WSPC2_Col_Glass_Shatter_{i + 1:02d}"
        rng = rng_for(name)
        n = int(rng.uniform(0.55, 0.9) * SR)
        a, s1 = kenney("impactGlass_heavy", i)
        b, s2 = kenney("impactGlass_medium", i + 2)
        out = fit(a, n) * 0.8 + fit(resample(b, rng.uniform(0.9, 1.1)), n) * 0.6
        for _ in range(60):  # micro transients: bright glass cracks
            g = int(rng.uniform(0.003, 0.02) * SR)
            click = metal_modes(rng, g, 3000, 9000, 2, 0.002, 0.01, 60, 200)
            place(out, click * rng.uniform(0.2, 0.7), rng.beta(1.0, 4.0) * n * 0.7)
        out = hp(out, 300, 2)
        write(folder, name, out, "glass_shatter", sources=[s1, s2])
    for i in range(6):
        name = f"WSPC2_Col_Glass_Debris_{i + 1:02d}"
        rng = rng_for(name)
        n = int(rng.uniform(0.6, 1.4) * SR)
        out = np.zeros(n)
        tinkles = int(rng.uniform(70, 140))
        for _ in range(tinkles):
            g = int(rng.uniform(0.004, 0.03) * SR)
            tink = metal_modes(rng, g, 2000, 8000, 2, 0.003, 0.02, 80, 250)
            place(out, tink * rng.uniform(0.1, 0.8), rng.beta(1.0, 2.2) * (n - g))
        small, s1 = kenney("impactGlass_light", i)
        place(out, resample(small, rng.uniform(1.2, 1.6)) * 0.35, rng.uniform(0.05, 0.2) * n)
        out += hp(rng.standard_normal(n), 4000) * 0.02 * env_exp(n, 0.01, n / SR * 0.4)
        write(folder, name, out, "glass_debris", sources=[s1])


def scrape(name, seconds, band, roughness_hz, modes, mode_q, squeal, lowpass_hz, seed_extra=""):
    rng = rng_for(name + seed_extra)
    xf = 0.25
    n = int((seconds + xf) * SR)
    noise = bp(rng.standard_normal(n), *band)
    # roughness: random grain impulses filtered into short bursts, the texture of the surface
    grains = np.zeros(n)
    count = int(roughness_hz * n / SR)
    grains[rng.integers(0, n, count)] = rng.uniform(0.3, 1.0, count)
    grains = lp(grains, 1500, 2)
    am = 0.55 + 0.45 * np.abs(lp(grains, 60, 2) / max(1e-9, np.max(np.abs(lp(grains, 60, 2)))))
    out = noise * am + bp(grains * rng.standard_normal(n), 500, 7000) * 1.8
    body = np.zeros(n)
    for f in modes:  # sheet-metal resonances excited by the rub
        body += resonator(noise, f * rng.uniform(0.97, 1.03), mode_q)
    out += body * 0.6
    if squeal:
        t = np.arange(n) / SR
        wob = 1 + 0.01 * np.sin(2 * np.pi * rng.uniform(3, 7) * t) + 0.004 * lp(rng.standard_normal(n), 30, 2)
        f0 = rng.uniform(*squeal)
        out += np.sin(2 * np.pi * np.cumsum(f0 * wob) / SR) * 0.12 * (0.6 + 0.4 * am)
    out = lp(out, lowpass_hz)
    return make_loop(out, xf)


def scrapes():
    folder = os.path.join(OUT_COL, "scrape")
    specs = {
        "WSPC2_Col_Scrape_MetalOnAsphalt_Loop": dict(seconds=3.5, band=(700, 7000), roughness_hz=900,
                                                     modes=[620, 1130, 1780, 2450], mode_q=25, squeal=None, lowpass_hz=9000),
        "WSPC2_Col_Scrape_MetalOnMetal_Loop": dict(seconds=3.2, band=(900, 8000), roughness_hz=250,
                                                   modes=[1240, 1990, 2870, 3660, 4410], mode_q=90, squeal=(1500, 2600), lowpass_hz=11000),
        "WSPC2_Col_Scrape_MetalOnConcrete_Loop": dict(seconds=3.6, band=(500, 6000), roughness_hz=520,
                                                      modes=[540, 980, 1610], mode_q=20, squeal=None, lowpass_hz=7500),
        "WSPC2_Col_Scrape_PlasticOnAsphalt_Loop": dict(seconds=3.4, band=(250, 2800), roughness_hz=700,
                                                       modes=[380, 760], mode_q=8, squeal=None, lowpass_hz=3500),
        "WSPC2_Col_Scrape_MetalOnDirt_Loop": dict(seconds=3.8, band=(150, 2500), roughness_hz=1400,
                                                  modes=[420, 900], mode_q=10, squeal=None, lowpass_hz=3000),
    }
    for name, spec in specs.items():
        write(folder, name, scrape(name, **spec), "scrape", loop=True)


# --- mechanical -------------------------------------------------------------------------------------------

def tyres():
    rng = rng_for("WSPC2_Mech_Tire_Skid_Asphalt_Loop")
    xf, seconds = 0.25, 3.0
    n = int((seconds + xf) * SR)
    t = np.arange(n) / SR
    # stick-slip squeal: a harmonic tone whose pitch jitters, plus a hiss band
    jitter = lp(rng.standard_normal(n), 25, 2)
    jitter /= max(1e-9, np.max(np.abs(jitter)))
    f = 880 * (1 + 0.05 * jitter + 0.01 * np.sin(2 * np.pi * 5.5 * t))
    phase = 2 * np.pi * np.cumsum(f) / SR
    tone = np.sin(phase) + 0.45 * np.sin(2 * phase) + 0.2 * np.sin(3 * phase + 0.4)
    amp = 0.7 + 0.3 * np.abs(lp(rng.standard_normal(n), 12, 2)) / 0.3
    out = tone * np.clip(amp, 0.3, 1.2) * 0.6 + bp(rng.standard_normal(n), 1500, 6000) * 0.35
    write(OUT_MECH, "WSPC2_Mech_Tire_Skid_Asphalt_Loop", make_loop(out, xf), "tyre", loop=True,
          meta={"basePitchHz": 880})

    rng = rng_for("WSPC2_Mech_Tire_Skid_Dirt_Loop")
    n = int((3.4 + xf) * SR)
    grains = np.zeros(n)
    idx = rng.integers(0, n, int(2200 * n / SR))
    grains[idx] = rng.uniform(0.2, 1.0, len(idx))
    gravel = bp(signal.lfilter([1], [1, -0.97], grains * rng.standard_normal(n)), 300, 4000)
    rumble = lp(brown(rng, n), 180) * 4
    out = gravel * 1.0 + bp(rng.standard_normal(n), 200, 1800) * 0.4 + rumble
    write(OUT_MECH, "WSPC2_Mech_Tire_Skid_Dirt_Loop", make_loop(out, xf), "tyre", loop=True)


def turbo():
    rng = rng_for("WSPC2_Mech_Turbo_Spool_Loop")
    xf = 0.2
    n = int((2.5 + xf) * SR)
    t = np.arange(n) / SR
    f = 3200 * (1 + 0.003 * np.sin(2 * np.pi * 4 * t))
    whistle = np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.3 * np.sin(2 * np.pi * np.cumsum(2 * f) / SR)
    hiss = bp(rng.standard_normal(n), 2000, 7000) * 0.5
    write(OUT_MECH, "WSPC2_Mech_Turbo_Spool_Loop", make_loop(whistle * 0.5 + hiss, xf), "turbo", loop=True,
          meta={"basePitchHz": 3200})
    for i in range(4):
        name = f"WSPC2_Mech_Turbo_BOV_{i + 1:02d}"
        rng = rng_for(name)
        n = int(rng.uniform(0.35, 0.6) * SR)
        noise = rng.standard_normal(n)
        # sweep the band down as the pressure drops
        out = np.zeros(n)
        chunk = 512
        centre = np.geomspace(rng.uniform(4500, 6000), rng.uniform(1200, 1800), n // chunk + 1)
        for k in range(0, n, chunk):
            c = centre[k // chunk]
            seg = noise[max(0, k - 2048):k + chunk]
            seg = bp(seg, c * 0.6, c * 1.5, 2)[-min(chunk, n - k):]
            out[k:k + len(seg)] = seg
        out *= env_exp(n, 0.006, n / SR * 0.35)
        write(OUT_MECH, name, out, "turbo_bov")
    for i in range(4):
        name = f"WSPC2_Mech_Turbo_Flutter_{i + 1:02d}"
        rng = rng_for(name)
        n = int(rng.uniform(0.45, 0.8) * SR)
        t = np.arange(n) / SR
        rate = rng.uniform(16, 24) * (1 - 0.35 * t / t[-1])
        chuff = 0.5 + 0.5 * np.sign(np.sin(2 * np.pi * np.cumsum(rate) / SR))
        chuff = lp(chuff, 120, 2)
        out = bp(rng.standard_normal(n), 600, 4500) * chuff + lp(rng.standard_normal(n), 400) * chuff * 0.4
        out *= env_exp(n, 0.004, n / SR * 0.5)
        write(OUT_MECH, name, out, "turbo_flutter")


def whines():
    rng = rng_for("WSPC2_Mech_Supercharger_Whine_Loop")
    xf = 0.2
    n = int((2.5 + xf) * SR)
    t = np.arange(n) / SR
    f0 = 1800.0
    out = (np.sin(2 * np.pi * f0 * t) + 0.5 * np.sin(2 * np.pi * 2 * f0 * t + 0.3)
           + 0.25 * np.sin(2 * np.pi * 3 * f0 * t + 1.1)) * (1 + 0.04 * np.sin(2 * np.pi * 37 * t))
    out += bp(rng.standard_normal(n), 1200, 5000) * 0.2
    write(OUT_MECH, "WSPC2_Mech_Supercharger_Whine_Loop", make_loop(out, xf), "supercharger", loop=True,
          meta={"basePitchHz": f0})

    rng = rng_for("WSPC2_Mech_Gear_Whine_Loop")
    f0 = 720.0
    mesh = 1 + 0.15 * np.sin(2 * np.pi * 42 * t)  # tooth-mesh sidebands
    out = (np.sin(2 * np.pi * f0 * t) * mesh + 0.35 * np.sin(2 * np.pi * 2 * f0 * t)) + bp(rng.standard_normal(n), 400, 2500) * 0.15
    write(OUT_MECH, "WSPC2_Mech_Gear_Whine_Loop", make_loop(out, xf), "gear_whine", loop=True,
          meta={"basePitchHz": f0})

    for i in range(4):
        name = f"WSPC2_Mech_Gear_Shift_Clunk_{i + 1:02d}"
        rng = rng_for(name)
        n = int(rng.uniform(0.18, 0.3) * SR)
        out = sub_drop(n, rng.uniform(110, 140), rng.uniform(60, 75), 0.03, 0.06) * 0.8
        out += metal_modes(rng, n, 900, 3200, 4, 0.01, 0.04) * 0.5
        out += lp(rng.standard_normal(n), 1200) * env_exp(n, 0.0005, 0.015) * 0.4
        write(OUT_MECH, name, out, "gear_clunk")


def backfires():
    for i in range(6):
        name = f"WSPC2_Mech_Backfire_Pop_{i + 1:02d}"
        rng = rng_for(name)
        n = int(rng.uniform(0.18, 0.4) * SR)
        blast = lp(rng.standard_normal(n), rng.uniform(2200, 4000)) * env_exp(n, 0.0004, rng.uniform(0.02, 0.05))
        pipe = resonator(blast, rng.uniform(90, 180), 6) * 3 + resonator(blast, rng.uniform(300, 500), 10)
        punch, src = kenney("impactPunch_heavy", i)
        out = blast + pipe * 0.8 + fit(resample(punch, rng.uniform(0.8, 1.0)), n) * 0.25
        out = saturate(out, 2.5)
        write(OUT_MECH, name, out, "backfire", sources=[src])


def diesel_clatter():
    """Injector knock of a four-cylinder diesel at 1000 rpm (33.3 firings per second); pitch follows RPM."""
    rng = rng_for("WSPC2_Mech_Diesel_Clatter_Loop")
    ref_rpm, cylinders = 1000.0, 4
    firing_hz = ref_rpm / 60.0 * cylinders / 2.0
    cycles = int(round(2.4 * firing_hz))
    n = int(round(cycles * SR / firing_hz))
    out = np.zeros(n)
    period = SR / firing_hz
    for k in range(cycles):
        g = int(0.03 * SR)
        knock = metal_modes(rng, g, 1800, 5200, 4, 0.002, 0.008, 40, 120) * rng.uniform(0.7, 1.0)
        knock += hp(rng.standard_normal(g), 2500) * env_exp(g, 0.0002, 0.003) * 0.6
        place_circular(out, knock, k * period + rng.uniform(-0.0008, 0.0008) * SR)
    # whole firing cycles fill the file exactly, so the loop is seamless without a crossfade
    write(OUT_MECH, "WSPC2_Mech_Diesel_Clatter_Loop", out, "diesel_clatter", loop=True,
          meta={"referenceRpm": ref_rpm, "cylinders": cylinders})


def main():
    impacts()
    crunches()
    glass()
    scrapes()
    tyres()
    turbo()
    whines()
    backfires()
    diesel_clatter()
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump({"schemaVersion": 1, "sampleRate": SR, "files": ENTRIES}, f, indent=2)
    loops = sum(1 for e in ENTRIES if e["loop"])
    print(f"wrote {len(ENTRIES)} files ({loops} loops) and {MANIFEST}")


if __name__ == "__main__":
    main()
