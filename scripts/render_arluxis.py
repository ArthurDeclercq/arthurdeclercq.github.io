#!/usr/bin/env python3
"""Render arluxis.yml into _arluxis_galleries.qmd (gallery tabs and photo plates).

Runs as a Quarto pre-render step and needs only PyYAML. arluxis.qmd includes
the output. Within each gallery the photos run newest first. Two upright
photos from the same place share a row (a "spread"); with three or more, the
two taken closest together are paired first. Per-photo keys in arluxis.yml
can override this:

  pair_with: DSCF1234   pair with this photo instead
  single: true          never pair this photo
  pair_at: older        place the pair where its older photo falls

New photos are added with scripts/add_arluxis_photos.py.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime
from html import escape
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "arluxis.yml"
OUT = ROOT / "_arluxis_galleries.qmd"

# Gallery key, title, image folder. Tabs and chapters follow this order.
GALLERIES = [
    ("nature", "Nature", "landscape_photography"),
    ("sports", "Sports", "sports_photography"),
    ("street", "Street", "street_photography"),
]


def webp_size(path: Path) -> tuple[int, int]:
    """Width and height from a WebP header."""
    b = path.read_bytes()[:40]
    chunk = b[12:16]
    if chunk == b"VP8X":
        return int.from_bytes(b[24:27], "little") + 1, int.from_bytes(b[27:30], "little") + 1
    if chunk == b"VP8 ":
        return int.from_bytes(b[26:28], "little") & 0x3FFF, int.from_bytes(b[28:30], "little") & 0x3FFF
    if chunk == b"VP8L":
        v = int.from_bytes(b[21:25], "little")
        return (v & 0x3FFF) + 1, ((v >> 14) & 0x3FFF) + 1
    raise ValueError(f"not a WebP file: {path}")


def fmt_lens(lens: str) -> str:
    """'XF18-55mmF2.8-4 R LM OIS' -> 'XF18-55mm F2.8-4'."""
    m = re.match(r"^(XF[\d\-]+mm)F([\d.\-]+)", lens or "")
    return f"{m.group(1)} F{m.group(2)}" if m else (lens or "")


def viewer_exif(p: dict) -> str:
    """Pipe-separated camera details shown in the viewer."""
    items = [p.get("camera", ""), fmt_lens(p.get("lens", ""))]
    if re.match(r"^XF\d+-\d+mm", p.get("lens", "")):
        items.append(f"{p['focal_length']} mm")
    items += [f"f/{p['aperture']:g}", f"{p['shutter']} s", f"ISO {p['iso']}"]
    if p.get("film"):
        items.append(p["film"])
    return "|".join(str(i) for i in items if i)


def settings(p: dict) -> list[str]:
    """Short settings line shown under each photo."""
    return [f"{p['focal_length']} mm", f"f/{p['aperture']:g}", f"{p['shutter']} s", f"ISO {p['iso']}"]


def load() -> list[dict]:
    entries = yaml.safe_load(DATA.read_text(encoding="utf-8")) or []
    folders = {folder: key for key, _, folder in GALLERIES}
    photos = []
    for e in entries:
        folder, name = e["file"].split("/")
        if folder not in folders:
            sys.exit(f"arluxis.yml: unknown folder in {e['file']}")
        if not e.get("place") or e["place"] == "TODO":
            sys.exit(f"arluxis.yml: no place for {e['file']}")
        stem = Path(name).stem
        webp = f"images/arluxis_webp/{folder}/{stem}.webp"
        if not (ROOT / webp).exists():
            sys.exit(f"arluxis.yml: no preview {webp}; run scripts/add_arluxis_photos.py or remove {e['file']}")
        w, h = webp_size(ROOT / webp)
        taken = datetime.fromisoformat(str(e["taken"]))
        p = dict(e)
        p.update(
            id=stem,
            gallery=folders[folder],
            webp=webp,
            full=f"images/arluxis/{e['file']}",
            w=w,
            h=h,
            r=round(w / h, 4),
            taken=taken,
            month=taken.strftime("%B %Y"),
            aperture=float(e["aperture"]),
        )
        photos.append(p)
    photos.sort(key=lambda p: p["taken"], reverse=True)
    return photos


def pairs_for(gallery: list[dict]) -> dict[str, str]:
    """Map each paired photo id to its partner."""
    by_id = {p["id"]: p for p in gallery}
    partner = {}
    for p in gallery:
        other = p.get("pair_with")
        if other:
            if other not in by_id:
                sys.exit(f"arluxis.yml: {p['id']} pairs with {other}, which is not in the same gallery")
            partner[p["id"]], partner[other] = other, p["id"]

    groups: dict[str, list[dict]] = {}
    for p in sorted(gallery, key=lambda p: p["taken"]):
        if p["r"] < 1 and p["id"] not in partner and not p.get("single"):
            groups.setdefault(p["place"], []).append(p)
    for group in groups.values():
        while len(group) > 1:
            gap, i = min((b["taken"] - a["taken"], i) for i, (a, b) in enumerate(zip(group, group[1:])))
            a, b = group[i], group[i + 1]
            partner[a["id"]], partner[b["id"]] = b["id"], a["id"]
            del group[i : i + 2]
    return partner


def figure(p: dict, indent: str) -> str:
    label = f"{escape(p['place'])}, {p['month']}"
    alt = escape(p.get("alt") or f"{p['place']}, {p['month']}")
    spans = "".join(f"<span>{escape(s)}</span>" for s in settings(p))
    return (
        f'{indent}<figure class="plate__figure" style="--r:{p["r"]}" data-full="{p["full"]}" data-exif="{escape(viewer_exif(p))}">\n'
        f'{indent}  <button class="plate__open" type="button"><img class="plate__img" src="{p["webp"]}" '
        f'width="{p["w"]}" height="{p["h"]}" alt="{alt}" loading="lazy" decoding="async"></button>\n'
        f'{indent}  <figcaption class="plate__caption"><span class="plate__place">{label}</span>'
        f'<span class="plate__settings">{spans}</span></figcaption>\n'
        f"{indent}</figure>"
    )


def plates(gallery: list[dict]) -> str:
    by_id = {p["id"]: p for p in gallery}
    partner = pairs_for(gallery)
    late = {p["id"] for p in gallery if p.get("pair_at") == "older"}
    late |= {partner[i] for i in late if i in partner}
    blocks, done, waiting = [], set(), set()
    for p in gallery:
        if p["id"] in done:
            continue
        if p["id"] not in partner:
            blocks.append(f'      <div class="plate" style="--r:{p["r"]}">\n{figure(p, "        ")}\n      </div>')
            continue
        # A pair sits where its newer photo falls, newer photo on the left,
        # unless it is marked to wait for its older photo
        a, b = p, by_id[partner[p["id"]]]
        if a["id"] in late and b["id"] not in waiting:
            waiting.add(a["id"])
            continue
        if b["id"] in waiting:
            a, b = b, a
        done.add(b["id"])
        blocks.append(
            f'      <div class="plate plate--spread" style="--r:{round(a["r"] + b["r"], 4)}">\n'
            f'        <div class="plate__pair">\n'
            f'{figure(a, "          ")}\n{figure(b, "          ")}\n'
            f"        </div>\n      </div>"
        )
    return "\n".join(blocks)


def render(photos: list[dict]) -> str:
    out = ["<!-- Generated by scripts/render_arluxis.py from arluxis.yml. Do not edit. -->", "```{=html}"]
    out.append('<nav class="galleries" id="galleries" aria-label="Galleries">\n  <div class="galleries__inner">')
    for key, title, _ in GALLERIES:
        n = sum(p["gallery"] == key for p in photos)
        out.append(
            f'    <a class="galleries__link" href="#{key}" data-gallery="{key}">{title}'
            f'<span class="galleries__count">{n}</span></a>'
        )
    out.append("  </div>\n</nav>\n\n<div role=\"main\">")
    for i, (key, title, _) in enumerate(GALLERIES):
        nkey, ntitle, _ = GALLERIES[(i + 1) % len(GALLERIES)]
        out.append(
            f"\n  <!-- {title} -->\n"
            f'  <section class="chapter" id="{key}" data-gallery="{key}" aria-labelledby="{key}-title">\n'
            f'    <header class="chapter__head">\n'
            f'      <h2 class="chapter__title" tabindex="-1" id="{key}-title">{title}</h2>\n'
            f"    </header>\n"
            f"{plates([p for p in photos if p['gallery'] == key])}\n"
            f'    <p class="chapter__end"><a href="#{nkey}" data-gallery="{nkey}">Next gallery: {ntitle}</a>'
            f'<a href="#top">Back to top</a></p>\n'
            f"  </section>"
        )
    out.append("\n</div>\n```\n")
    return "\n".join(out)


def main() -> None:
    photos = load()
    OUT.write_text(render(photos), encoding="utf-8", newline="\n")
    print(f"Rendered {len(photos)} photos -> {OUT.name}")


if __name__ == "__main__":
    main()
