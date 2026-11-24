"""Downloads the free (CC0) source sounds for the collision and mechanical effects.

Kenney's "Impact Sounds" pack (CC0, https://kenney.nl/assets/impact-sounds): the page's own "Continue without
donating" flow is followed (the page's data-download-id goes to https://kenney.nl/download-link/<id>, which
answers with a fresh signed ZIP URL; old hashed media URLs just redirect back to the page). The archive is
checked (ZIP signature, SHA-256 recorded) and extracted. Everything lands in the git-ignored Saved/ tree; only the processed results of
build_collision_and_mech_sfx.py are imported into the game.

  Saved/Audio/Pipeline/.venv/Scripts/python.exe Tools/audio/pipeline/fetch_free_sfx.py

Inputs:  network (kenney.nl)
Outputs: Saved/Audio/Pipeline/raw_sfx/kenney_impact_sounds/** (OGG files + License.txt)
         Saved/Audio/Pipeline/raw_sfx/sources.json (URL, SHA-256, size, licence line per download)
"""
import hashlib
import json
import os
import re
import sys
import zipfile

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
RAW = os.path.join(ROOT, "Saved", "Audio", "Pipeline", "raw_sfx")
PAGE = "https://kenney.nl/assets/impact-sounds"
HEADERS = {"User-Agent": "audio-asset-pipeline/1.0"}


def find_zip_url(session, html):
    match = re.search(r"data-download-id='([0-9a-f]+)'", html) or re.search(r'data-download-id="([0-9a-f]+)"', html)
    if not match:
        sys.exit(f"no download id found on {PAGE}")
    reply = session.get("https://kenney.nl/download-link/" + match.group(1), timeout=30,
                        headers={"Referer": PAGE, "Accept": "application/json"})
    reply.raise_for_status()
    url = reply.json().get("url")
    if not url:
        sys.exit("the download-link endpoint returned no URL")
    return url


def main():
    os.makedirs(RAW, exist_ok=True)
    session = requests.Session()
    session.headers.update(HEADERS)
    page = session.get(PAGE, timeout=30)
    page.raise_for_status()
    url = find_zip_url(session, page.text)

    archive = os.path.join(RAW, "kenney_impact_sounds.zip")
    with session.get(url, timeout=120, stream=True) as r:
        r.raise_for_status()
        with open(archive, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
    with open(archive, "rb") as f:
        if f.read(2) != b"PK":
            sys.exit(f"download is not a ZIP archive: {url}")
    digest = hashlib.sha256(open(archive, "rb").read()).hexdigest()
    url = url.split("?")[0]  # keep the signature out of the record

    target = os.path.join(RAW, "kenney_impact_sounds")
    with zipfile.ZipFile(archive) as z:
        z.extractall(target)
    licence = ""
    for dirpath, _, files in os.walk(target):
        for name in files:
            if name.lower().startswith("license"):
                with open(os.path.join(dirpath, name), encoding="utf-8", errors="replace") as f:
                    licence = " ".join(line.strip() for line in f if "creative commons" in line.lower() or "cc0" in line.lower())[:200]
    oggs = sum(1 for _, _, files in os.walk(target) for n in files if n.lower().endswith(".ogg"))

    record = {"kenney_impact_sounds": {"page": PAGE, "url": url, "sha256": digest,
                                       "bytes": os.path.getsize(archive), "files": oggs, "licence": licence}}
    sources = os.path.join(RAW, "sources.json")
    data = json.load(open(sources, encoding="utf-8")) if os.path.exists(sources) else {}
    data.update(record)
    with open(sources, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
