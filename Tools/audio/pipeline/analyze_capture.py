"""Measures a game audio capture: loudness over time, the engine's firing frequency and clicks.

For each second of Saved/Audio/Pipeline/capture/<name>.wav (front left + right) it prints the level, the
low band (30-400 Hz, where the engine's firing frequency lives) and the strongest frequency there, then counts
click candidates (a sample step 25x larger than the motion around it), which is what a restarting loop leaves
behind. The AudioTrace lines of <name>.log are matched by time to show the RPM the game reported.

  Saved/Audio/Pipeline/.venv/Scripts/python.exe Tools/audio/pipeline/analyze_capture.py patrol_bank [patrol_stems ...]

Inputs:  Saved/Audio/Pipeline/capture/<name>.wav and <name>.log
Outputs: a table per capture and Saved/Audio/Pipeline/capture/<name>.json (summary)
"""
import json
import os
import re
import sys

import numpy as np
import pyloudnorm
import soundfile as sf
from scipy import signal

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
CAPTURE = os.path.join(ROOT, "Saved", "Audio", "Pipeline", "capture")


def rpm_trace(log_path):
    rpms = []
    if os.path.exists(log_path):
        for line in open(log_path, encoding="utf-8", errors="replace"):
            m = re.search(r"AudioTrace: .*?local=1", line)
            if m:
                r = re.search(r"rpm=(\d+)", line)
                g = re.search(r"gain=([\d.]+)", line)
                rpms.append((int(r.group(1)), float(g.group(1))))
    return rpms


def analyze(name):
    data, sr = sf.read(os.path.join(CAPTURE, name + ".wav"), always_2d=True)
    front = data[:, :2].mean(axis=1) if data.shape[1] >= 2 else data[:, 0]
    low = signal.sosfilt(signal.butter(4, [30 / (sr / 2), 400 / (sr / 2)], btype="band", output="sos"), front)
    trace = rpm_trace(os.path.join(CAPTURE, name + ".log"))
    print(f"== {name}: {len(front) / sr:.1f} s, {data.shape[1]} channels, peak {20 * np.log10(np.abs(data).max() + 1e-12):.1f} dBFS")
    print("  t   level dB  low dB  peak<400Hz   trace rpm/gain")
    seconds = []
    for i in range(int(len(front) / sr)):
        seg = front[i * sr:(i + 1) * sr]
        spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
        f = np.fft.rfftfreq(len(seg), 1 / sr)
        band = (f > 25) & (f < 400)
        level = 20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-12)
        low_db = 20 * np.log10(np.sqrt(np.mean(low[i * sr:(i + 1) * sr] ** 2)) + 1e-12)
        peak_f = float(f[band][np.argmax(spec[band])])
        rpm, gain = trace[i] if i < len(trace) else (None, None)
        seconds.append({"t": i, "levelDb": round(level, 1), "lowDb": round(low_db, 1), "lowPeakHz": round(peak_f, 1), "rpm": rpm})
        print(f"{i:3d}  {level:8.1f}  {low_db:6.1f}  {peak_f:8.1f}   {rpm if rpm is not None else '-'}/{gain if gain is not None else '-'}")
    step = np.abs(np.diff(front))
    local = np.convolve(step, np.ones(480) / 480, mode="same") + 1e-6
    clicks = np.where((step > 25 * local) & (step > 1e-3))[0]
    lufs = pyloudnorm.Meter(sr).integrated_loudness(front)
    summary = {"name": name, "seconds": round(len(front) / sr, 1), "integratedLufs": round(float(lufs), 1),
               "clickCandidates": int(len(clicks)), "clickTimes": [round(c / sr, 2) for c in clicks[:20]], "perSecond": seconds}
    with open(os.path.join(CAPTURE, name + ".json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1)
    print(f"  integrated {lufs:.1f} LUFS, click candidates {len(clicks)} {summary['clickTimes'][:8]}")


if __name__ == "__main__":
    for capture_name in sys.argv[1:]:
        analyze(capture_name)
