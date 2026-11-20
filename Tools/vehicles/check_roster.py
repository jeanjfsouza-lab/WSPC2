"""Checks the vehicle roster against what is installed and against the campaign.

  python -P Tools/vehicles/check_roster.py

Input:  Tools/vehicles/vehicle_roster.json; Content/ (the packs, the imported vehicles); ASSETS TO USE/01_Preparados/
        manifest.json; ASSETS TO USE/bay_city_3d/dados/cenarios_bay_city.json (the campaign's units and targets);
        Source/WSPC2/WSPC2VehicleProfile.cpp (the built-in presets)
Output: prints, per vehicle, whether its assets are there; the preset ids the roster needs that the code lacks; the
        prepared ids still to import (a ready line for import_vehicles.py); licences that must not ship; every
        operation's unit and target with the vehicle that plays it; the traffic mix by band. Exit code 1 when a
        restricted licence is in use or a campaign unit/target has no vehicle and no listed gap.
Writes nothing.
"""
import collections
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
ROSTER = os.path.join(ROOT, "Tools", "vehicles", "vehicle_roster.json")
MANIFEST = os.path.join(ROOT, "ASSETS TO USE", "01_Preparados", "manifest.json")
CAMPAIGN = os.path.join(ROOT, "ASSETS TO USE", "bay_city_3d", "dados", "cenarios_bay_city.json")
PROFILES = os.path.join(ROOT, "Source", "WSPC2", "WSPC2VehicleProfile.cpp")
RESTRICTED = ("FORZA", "CC-BY-ND", "NON-COMMERCIAL", "-NC", "GAME-RIP", "GAME RIP")


def content_exists(rel):
    """A Content/ folder or asset (without extension)."""
    path = os.path.join(ROOT, "Content", *rel.split("/"))
    return os.path.isdir(path) or os.path.exists(path + ".uasset")


def main():
    roster = json.load(open(ROSTER, encoding="utf-8"))
    manifest = {m["id"]: m for m in json.load(open(MANIFEST, encoding="utf-8"))} if os.path.exists(MANIFEST) else {}
    presets = set(re.findall(r'FName\("(\w+)"\)', open(PROFILES, encoding="utf-8").read())) if os.path.exists(PROFILES) else set()
    problems, to_import, missing_presets = [], [], []
    by_role = collections.Counter()
    print("ROSTER %d vehicles, %d gaps, %d excluded" % (len(roster["vehicles"]), len(roster.get("gaps", [])), len(roster.get("excluded", []))))
    for v in roster["vehicles"]:
        for r in v["roles"]:
            by_role[r] += 1
        state = []
        if v.get("content"):
            state.append("content %s" % ("ok" if content_exists(v["content"]) else "MISSING (optional pack not installed)"))
        if v.get("prepared"):
            m = manifest.get(v["prepared"])
            if m is None and v.get("status") != "make":
                state.append("prepared %s NOT IN MANIFEST" % v["prepared"])
                problems.append("%s: prepared id %s not in the manifest" % (v["id"], v["prepared"]))
            else:
                cat = m["category"] if m else "03_Traffic"
                imported = os.path.isdir(os.path.join(ROOT, "Content", "Vehicles", "Imported", cat, v["prepared"]))
                state.append("prepared %s %s" % (v["prepared"], "imported" if imported else "to import"))
                if not imported and v.get("status") in ("import", "ready") and m:
                    to_import.append(v["prepared"])
        if v.get("preset") and v["preset"] not in presets:
            missing_presets.append(v["preset"])
            state.append("preset %s NOT IN CODE" % v["preset"])
        lic = (v.get("license") or "").upper()
        if any(t in lic for t in RESTRICTED):
            problems.append("%s: restricted licence %s" % (v["id"], v["license"]))
        print("ROSTER %-18s %-28s %-10s %s" % (v["id"], "+".join(v["roles"]), v.get("status", ""), "; ".join(state)))
    for e in roster.get("excluded", []):
        if e.get("prepared") and any(e["prepared"] == v.get("prepared") for v in roster["vehicles"]):
            problems.append("excluded %s is also in use" % e["prepared"])
    print("ROSTER roles: %s" % ", ".join("%s %d" % kv for kv in by_role.most_common()))
    # the campaign: every unit and target played by a vehicle or listed as a gap
    names = collections.defaultdict(list)
    for v in roster["vehicles"]:
        for c in v.get("campaign", []):
            names[c.lower()].append(v["id"])
    gaps = {g["campaign"].lower(): g for g in roster.get("gaps", [])}
    if os.path.exists(CAMPAIGN):
        ops = json.load(open(CAMPAIGN, encoding="utf-8"))["operations"]
        for o in ops:
            row = []
            for what in ("unit", "target"):
                name = o.get(what) or ""
                who = names.get(name.lower())
                if who:
                    row.append("%s %s -> %s" % (what, name, "/".join(who)))
                elif name.lower() in gaps:
                    row.append("%s %s -> GAP (stand-in %s)" % (what, name, gaps[name.lower()].get("stand_in")))
                else:
                    row.append("%s %s -> NOTHING" % (what, name))
                    problems.append("%s: %s '%s' has no vehicle" % (o["code"], what, name))
            print("CAMPAIGN %-12s %s" % (o["code"], " | ".join(row)))
    # the traffic mix
    bands = collections.defaultdict(float)
    for v in roster["vehicles"]:
        t = v.get("traffic")
        if t and t.get("weight"):
            bands[t["band"]] += t["weight"]
    total = sum(bands.values()) or 1.0
    print("TRAFFIC weight %.1f: %s" % (total, ", ".join("%s %.0f%%" % (b, 100 * w / total) for b, w in sorted(bands.items()))))
    if missing_presets:
        print("PRESETS to add to WSPC2VehicleProfile.cpp: %s" % ", ".join(sorted(set(missing_presets))))
    if to_import:
        print("IMPORT $env:WSPC2_VEHICLE_IDS = \"%s\"" % ",".join(sorted(set(to_import))))
    for p in problems:
        print("PROBLEM " + p)
    print("ROSTER %s" % ("ok" if not problems else "%d problems" % len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
