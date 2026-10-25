#!/usr/bin/env python3
"""Render publications.yml into _publications.qmd (raw HTML publication blocks).

Runs as a Quarto pre-render step. Emits one .publication-item + .divider per
entry, in file order. Ordering, the "New" tag, and the gold divider are handled
client-side by the existing scripts in index.qmd.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "publications.yml"
OUT = ROOT / "_publications.qmd"

MONTHS = [
    "", "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
]


def format_date(d: str) -> str:
    """'YYYY-MM' -> 'Month YYYY'; 'YYYY' -> 'YYYY'; anything else returned as-is."""
    parts = str(d).split("-")
    if len(parts) >= 2 and parts[1].isdigit() and 1 <= int(parts[1]) <= 12:
        return f"{MONTHS[int(parts[1])]} {parts[0]}"
    return str(d)


def render_item(p: dict) -> str:
    first = "true" if p.get("first_author") else "false"
    label = p.get("venue_label", "Journal")
    link_text = p.get("link_text", "View Manuscript")
    display_date = format_date(p["date"])
    abstract = p.get("abstract", "") or ""
    return (
        f'    <div class="publication-item" data-year="{p["date"]}" data-first-author="{first}">\n'
        f'      <h3 class="publication-title">{p["title"]}</h3>\n'
        f'      <p class="publication-authors">\n'
        f'        <strong>Authors:</strong> {p["authors"]}\n'
        f'      </p>\n'
        f'      <p class="publication-journal">\n'
        f'        <strong>{label}:</strong> {p["venue"]}<span>|</span> <strong>Year:</strong> {display_date} <span>|</span>\n'
        f'        <span class="abstract-container" onclick="toggleAbstract(this)">\n'
        f'          Abstract\n'
        f'          <img src="icons/document.png" alt="abstract Icon" class="abstract-icon">\n'
        f'        </span>\n'
        f'      </p>\n'
        f'      <div class="abstract">\n'
        f'        <p class="abstract-text">{abstract}</p>\n'
        f'        <a href="{p["url"]}" target="_blank" class="manuscript-link">\n'
        f'          {link_text}\n'
        f'        </a>\n'
        f'      </div>\n'
        f'    </div>\n'
        f'    <div class="divider"></div>'
    )


def render(pubs: list[dict]) -> str:
    return "\n".join(render_item(p) for p in pubs) + "\n"


def main() -> int:
    pubs = yaml.safe_load(DATA.read_text(encoding="utf-8")) or []
    OUT.write_text(render(pubs), encoding="utf-8")
    print(f"Rendered {len(pubs)} publications -> {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
