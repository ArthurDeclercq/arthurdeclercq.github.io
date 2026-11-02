#!/usr/bin/env python3
"""Add new photos to arluxis.yml.

Put the camera JPGs in the gallery folders under images/arluxis/
(landscape_photography for Nature, sports_photography, street_photography),
then run:

    python scripts/add_arluxis_photos.py

For every JPG that is not yet in arluxis.yml, this script
  - shrinks the JPG to 3000 px on the long side (quality 85) if it is larger,
  - writes the 1800 px WebP preview to images/arluxis_webp/,
  - reads the camera details with exiftool,
  - appends an entry to arluxis.yml with `place: TODO`.

Fill in each `place`, then render or preview the site. It also lists entries
whose JPG no longer exists, so they can be removed from arluxis.yml.

Needs ImageMagick 7 (`magick`) and `exiftool` on the PATH. Run it locally;
the deploy workflow only needs scripts/render_arluxis.py.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "arluxis.yml"
PHOTOS = ROOT / "images" / "arluxis"
PREVIEWS = ROOT / "images" / "arluxis_webp"
FOLDERS = ["landscape_photography", "sports_photography", "street_photography"]

FULL_SIZE = 3000  # long side of the JPG opened in the viewer
FULL_QUALITY = 85
PREVIEW_SIZE = 1800  # long side of the WebP shown on the page
PREVIEW_QUALITY = 92


def run(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def entry(jpg: Path) -> str:
    e = json.loads(run(
        "exiftool", "-j", "-DateTimeOriginal", "-Model", "-LensModel", "-FocalLength",
        "-FNumber", "-ExposureTime", "-ISO", "-FilmMode", str(jpg),
    ))[0]
    taken = datetime.strptime(e["DateTimeOriginal"], "%Y:%m:%d %H:%M:%S")
    lines = [
        f"- file: {jpg.parent.name}/{jpg.name}",
        "  place: TODO",
        f"  taken: {taken.isoformat()}",
        f"  camera: {e.get('Model', '')}",
        f"  lens: {e.get('LensModel', '')}",
        f"  focal_length: {round(float(str(e['FocalLength']).split()[0]))}",
        f"  aperture: {float(e['FNumber']):g}",
        f"  shutter: \"{e['ExposureTime']}\"",
        f"  iso: {e['ISO']}",
    ]
    film = e.get("FilmMode")
    if film and film != "-":
        # 'F2/Fujichrome (Velvia)' -> 'Velvia'
        film = re.sub(r"^.*\((.*)\)$", r"\1", film)
        lines.append(f"  film: {film}")
    return "\n".join(lines)


def main() -> None:
    for tool in ("magick", "exiftool"):
        if not shutil.which(tool):
            sys.exit(f"{tool} not found on the PATH")

    listed = {e["file"] for e in yaml.safe_load(DATA.read_text(encoding="utf-8")) or []}
    on_disk = {
        f"{folder}/{p.name}": p
        for folder in FOLDERS
        for p in sorted((PHOTOS / folder).iterdir())
        if p.suffix.lower() in (".jpg", ".jpeg")
    }

    new = [p for f, p in on_disk.items() if f not in listed]
    entries = []
    for jpg in new:
        print(f"adding {jpg.parent.name}/{jpg.name}")
        # Read the details before resizing, while the file is untouched
        entries.append(entry(jpg))
        tmp = jpg.with_suffix(".tmp.jpg")
        run("magick", str(jpg), "-auto-orient", "-resize", f"{FULL_SIZE}x{FULL_SIZE}>",
            "-quality", str(FULL_QUALITY), str(tmp))
        tmp.replace(jpg)
        webp = PREVIEWS / jpg.parent.name / f"{jpg.stem}.webp"
        webp.parent.mkdir(parents=True, exist_ok=True)
        run("magick", str(jpg), "-resize", f"{PREVIEW_SIZE}x{PREVIEW_SIZE}>", "-strip",
            "-quality", str(PREVIEW_QUALITY), str(webp))

    if entries:
        text = DATA.read_text(encoding="utf-8").rstrip("\n")
        text += f"\n\n# Added {date.today().isoformat()}: fill in each place\n" + "\n".join(entries) + "\n"
        DATA.write_text(text, encoding="utf-8", newline="\n")
        print(f"Added {len(entries)} photos to {DATA.name}. Fill in each `place: TODO`.")
    else:
        print("No new photos.")

    gone = sorted(listed - on_disk.keys())
    if gone:
        print("These entries have no JPG any more; remove them from arluxis.yml:")
        for f in gone:
            print(f"  {f}")


if __name__ == "__main__":
    main()
