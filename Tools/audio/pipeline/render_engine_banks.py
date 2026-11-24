"""Probes or renders the WSPC2 engine banks with the engine-sim-unity-audio generator.

For every archetype in Tools/audio/pipeline/engine_archetypes.json it runs EngineAudioGenerator.exe (built from
Saved/Audio/Pipeline/repos/engine-sim-unity-audio with Build-Generator.ps1, or with CMake and the
"Visual Studio 18 2026" generator on this PC) over the archetype's RPM grid and the three loads. Each bank gets
start.wav, shutdown.wav, rpm_####/load_###.wav (48 kHz mono PCM16 loops cut on whole four-stroke cycles) and
EngineAudioBank.json. It calls the generator directly instead of Generate-All.ps1 because the presets live in
Tools/audio/pipeline/presets, outside the generator's repository. The generator writes its wrapper script into
the runtime folder, so parallel jobs each get their own copy of the runtime (Saved/Audio/Pipeline/runtime_slots).

  Saved/Audio/Pipeline/.venv/Scripts/python.exe Tools/audio/pipeline/render_engine_banks.py --probe
  Saved/Audio/Pipeline/.venv/Scripts/python.exe Tools/audio/pipeline/render_engine_banks.py [--only arch_x ...] [--jobs 3]

Inputs:  Tools/audio/pipeline/engine_archetypes.json, Tools/audio/pipeline/presets/*.mr
Outputs: Saved/Audio/Pipeline/output/engines/<archetype>/ (bank) and <archetype>.log (generator output)
"""
import argparse
import concurrent.futures
import json
import os
import queue
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
TOOL = os.path.join(ROOT, "Saved", "Audio", "Pipeline", "repos", "engine-sim-unity-audio")
GENERATOR = os.path.join(TOOL, "bin", "Release", "EngineAudioGenerator.exe")
RUNTIME = os.path.join(TOOL, "ThirdParty", "engine-sim-runtime")
MANIFEST = os.path.join(ROOT, "Tools", "audio", "pipeline", "engine_archetypes.json")
OUTPUT = os.path.join(ROOT, "Saved", "Audio", "Pipeline", "output", "engines")
SLOTS = os.path.join(ROOT, "Saved", "Audio", "Pipeline", "runtime_slots")


def runtime_slots(count):
    """One private copy of the runtime per parallel job (the generator writes engine_audio_main.mr into it)."""
    slots = queue.Queue()
    for i in range(count):
        path = os.path.join(SLOTS, f"slot_{i}")
        if not os.path.exists(os.path.join(path, "es", "engine_sim.mr")):
            shutil.rmtree(path, ignore_errors=True)
            shutil.copytree(RUNTIME, path, ignore=shutil.ignore_patterns("engine_audio_main.mr", "*.log"))
        slots.put(path)
    return slots


def arguments(settings, arch, probe, runtime):
    num = lambda x: repr(float(x))
    args = [GENERATOR,
            "--preset", os.path.join(ROOT, arch["preset"]),
            "--runtime-root", runtime,
            "--entry", arch["entry"],
            "--name", arch["displayName"],
            "--module-id", arch["id"],
            "--sample-rate", str(settings["sampleRate"]),
            "--idle-rpm", str(arch["idleRpm"]),
            "--rpm-points", str(len(arch["rpms"])),
            "--loads", ",".join(num(x) for x in settings["loads"]),
            "--stabilize", num(settings["stabilizeSeconds"]),
            "--capture", num(settings["captureSeconds"]),
            "--start-crank", num(settings["startup"]["crankSeconds"]),
            "--start-catch", num(settings["startup"]["catchSeconds"]),
            "--start-settle", num(settings["startup"]["settleSeconds"]),
            "--force-idle-rpm", str(arch["idleRpm"]),
            "--rpms", ",".join(str(r) for r in arch["rpms"])]
    args += ["--probe"] if probe else ["--output", os.path.join(OUTPUT, arch["id"])]
    return args


def run(settings, arch, probe, slots):
    os.makedirs(OUTPUT, exist_ok=True)
    started = time.time()
    runtime = slots.get()
    try:
        proc = subprocess.run(arguments(settings, arch, probe, runtime), capture_output=True, text=True, cwd=TOOL)
    finally:
        slots.put(runtime)
    log = os.path.join(OUTPUT, arch["id"] + (".probe.log" if probe else ".log"))
    with open(log, "w", encoding="utf-8") as f:
        f.write(proc.stdout)
        f.write(proc.stderr)
    return arch["id"], proc.returncode, time.time() - started, proc.stdout, proc.stderr


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", action="store_true", help="compile the presets only")
    parser.add_argument("--only", nargs="*", default=[], help="archetype ids to run")
    parser.add_argument("--jobs", type=int, default=3)
    opts = parser.parse_args()

    if not os.path.exists(GENERATOR):
        sys.exit(f"generator not built: {GENERATOR}")
    settings = json.load(open(MANIFEST, encoding="utf-8"))
    archs = [a for a in settings["archetypes"] if not opts.only or a["id"] in opts.only]

    failures = 0
    jobs = max(1, min(opts.jobs, len(archs)))
    slots = runtime_slots(jobs)
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(run, settings, a, opts.probe, slots) for a in archs]
        for fut in concurrent.futures.as_completed(futures):
            arch_id, code, seconds, out, err = fut.result()
            if code != 0:
                failures += 1
                tail = (err or out).strip().splitlines()[-6:]
                print(f"FAIL {arch_id} (exit {code}, {seconds:.0f} s)\n    " + "\n    ".join(tail))
            elif opts.probe:
                info = {}
                for line in out.splitlines():
                    key, sep, value = line.partition("=")
                    if sep and key.isupper():
                        info[key] = value
                print(f"ok   {arch_id}: {info.get('ENGINE_NAME')} cyl={info.get('CYLINDERS')} "
                      f"redline={info.get('REDLINE_RPM')} sim={info.get('SIMULATION_HZ')}")
            else:
                print(f"ok   {arch_id} ({seconds:.0f} s)")
    print(f"{len(archs) - failures}/{len(archs)} succeeded")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
