"""Audits every generated vehicle WAV and balances the loudness of the engine banks.

Checks each file under Saved/Audio/Pipeline/output/{engines,collisions,mechanical}: 48 kHz, mono, PCM16, no
NaN/Inf, RMS above -55 dBFS, peak at or below -0.5 dBFS and, for loops, a seamless wrap (the jump from the last
sample to the first must stay within 3x the 95th-percentile step of the 2000 samples on either side of the wrap). Integrated loudness (LUFS,
ITU-R BS.1770 via pyloudnorm) is reported for files long enough to measure.

Automatic fixes: a file (or an engine bank, scaled as a whole so the load steps keep their difference) that peaks
above -0.5 dBFS is scaled down. Engine banks also get a loudness trim so every archetype sits at the same
reference loudness (mean of its 45 % load loops); the runtime applies it as the profile's gain.

  Saved/Audio/Pipeline/.venv/Scripts/python.exe Tools/audio/pipeline/validate_wavs.py

Inputs:  Saved/Audio/Pipeline/output/**.wav, output/engines/*/EngineAudioBank.json
Outputs: Saved/Audio/Pipeline/output/validation_report.json (per file metrics, failures, engine trims)
         exit code 1 when a failure could not be fixed
"""
import glob
import json
import os
import sys

import numpy as np
import pyloudnorm
import soundfile as sf

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
OUT = os.path.join(ROOT, "Saved", "Audio", "Pipeline", "output")
REPORT = os.path.join(OUT, "validation_report.json")

SR = 48000
MAX_PEAK_DB = -0.5
FIX_PEAK_DB = -1.0
MIN_RMS_DB = -55.0
# mean loudness of the 45 % load loops after the trim; -13.5 puts the Patrol's engine-sim bank at the level of the
# CitySample stems it replaces (A/B capture of the same test drive: -30.0 LUFS at -20.0 here, stems -23.5 LUFS)
ENGINE_REFERENCE_LUFS = -13.5
METER = pyloudnorm.Meter(SR)


def to_db(x):
    return float(20 * np.log10(max(x, 1e-12)))


def measure(path, loop):
    info = sf.info(path)
    data, rate = sf.read(path, dtype="float64", always_2d=True)
    x = data[:, 0]
    m = {"file": os.path.relpath(path, OUT).replace("\\", "/"), "rate": rate, "channels": info.channels,
         "subtype": info.subtype, "seconds": round(len(x) / rate, 3), "loop": loop}
    m["finite"] = bool(np.all(np.isfinite(data)))
    m["peakDb"] = round(to_db(np.max(np.abs(x))), 2)
    m["rmsDb"] = round(to_db(np.sqrt(np.mean(x ** 2))), 2)
    m["lufs"] = round(float(METER.integrated_loudness(x)), 2) if len(x) >= int(0.5 * rate) else None
    if loop:
        # the wrap step against the motion right around the wrap (a seam is a jump larger than its neighbourhood)
        k = min(2000, len(x) // 4)
        around = np.concatenate([x[-k:], x[:k]])
        motion = np.percentile(np.abs(np.diff(around)), 95) + 1e-6
        seam = abs(x[0] - x[-1])
        m["seamRatio"] = round(float(seam / motion), 2)
    problems = []
    if rate != SR:
        problems.append(f"rate {rate}")
    if info.channels != 1:
        problems.append(f"{info.channels} channels")
    if info.subtype != "PCM_16":
        problems.append(f"subtype {info.subtype}")
    if not m["finite"]:
        problems.append("NaN/Inf")
    if m["rmsDb"] < MIN_RMS_DB:
        problems.append(f"too quiet ({m['rmsDb']} dBFS RMS)")
    if loop and m["seamRatio"] > 3:
        problems.append(f"loop seam {m['seamRatio']}x the step size around the wrap")
    m["problems"] = problems
    return m, x


def rescale(path, gain):
    data, rate = sf.read(path, dtype="float64", always_2d=True)
    sf.write(path, (data[:, 0] * gain).astype(np.float32), rate, subtype="PCM_16")


def main():
    files, failures, fixes, trims = [], [], [], {}

    # engine banks: scale a whole bank at once so the loudness steps between loads survive
    for bank_json in sorted(glob.glob(os.path.join(OUT, "engines", "*", "EngineAudioBank.json"))):
        bank_dir = os.path.dirname(bank_json)
        bank = json.load(open(bank_json, encoding="utf-8"))
        arch = os.path.basename(bank_dir)
        clips = [(os.path.join(bank_dir, s["clip"]), True, s) for s in bank["states"]]
        clips += [(os.path.join(bank_dir, bank[k]), False, None) for k in ("startClip", "shutdownClip")]
        peak = max(np.max(np.abs(sf.read(p, dtype="float64")[0])) for p, _, _ in clips if os.path.exists(p))
        if to_db(peak) > MAX_PEAK_DB:
            gain = 10 ** (FIX_PEAK_DB / 20) / peak
            for p, _, _ in clips:
                rescale(p, gain)
            fixes.append(f"{arch}: bank scaled by {to_db(gain):.2f} dB (peak was {to_db(peak):.2f} dBFS)")
        mid_lufs = []
        for path, loop, state in clips:
            if not os.path.exists(path):
                failures.append(f"{arch}: missing {os.path.basename(path)}")
                continue
            m, _ = measure(path, loop)
            m["bank"] = arch
            files.append(m)
            if state and abs(state["load"] - 0.45) < 0.01 and m["lufs"] is not None:
                mid_lufs.append(m["lufs"])
        if mid_lufs:
            trims[arch] = round(ENGINE_REFERENCE_LUFS - float(np.mean(mid_lufs)), 2)

    # one-shots and loops of the collision / mechanical set
    manifest = json.load(open(os.path.join(OUT, "CollisionAudioManifest.json"), encoding="utf-8"))
    for entry in manifest["files"]:
        path = os.path.join(OUT, entry["file"])
        m, x = measure(path, entry["loop"])
        if m["peakDb"] > MAX_PEAK_DB:
            rescale(path, 10 ** (FIX_PEAK_DB / 20) / np.max(np.abs(x)))
            fixes.append(f"{entry['name']}: peak {m['peakDb']} dBFS scaled to {FIX_PEAK_DB}")
            m, _ = measure(path, entry["loop"])
        files.append(m)

    for m in files:
        for problem in m["problems"]:
            failures.append(f"{m['file']}: {problem}")
        if m["peakDb"] > MAX_PEAK_DB:
            failures.append(f"{m['file']}: peak {m['peakDb']} dBFS")

    report = {"files": len(files), "engineFiles": sum(1 for m in files if "bank" in m),
              "loops": sum(1 for m in files if m["loop"]), "failures": failures, "fixes": fixes,
              "engineLoudnessReferenceLufs": ENGINE_REFERENCE_LUFS, "engineTrimsDb": trims, "metrics": files}
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"{len(files)} files checked ({report['engineFiles']} engine, {report['loops']} loops), "
          f"{len(fixes)} fixed, {len(failures)} failures")
    for line in fixes + failures:
        print("  " + line)
    print("engine loudness trims (dB):", json.dumps(trims))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
