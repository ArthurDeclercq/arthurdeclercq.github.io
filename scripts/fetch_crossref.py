#!/usr/bin/env python3
"""Fetch new publications from Crossref by ORCID and append them to publications.yml.

Discovery is scoped by ORCID so unrelated "Declercq A" papers are not pulled.
Existing entries are never modified. Abstract lookup order: Crossref JATS ->
Europe PMC by DOI -> a visible 'TODO: add abstract' placeholder for PR review.
Network errors abort with a non-zero exit and no partial write.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import requests
import yaml

ORCID = "0000-0002-9376-1399"
FAMILY = "declercq"
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "publications.yml"
IGNORE = ROOT / "publications_ignore.yml"
CROSSREF = "https://api.crossref.org/works"
EUROPEPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
MAILTO = "arthur.declercq@ugent.be"
TIMEOUT = 30
ABSTRACT_TODO = "TODO: add abstract"


# Keep long / multi-line strings readable as literal block scalars in the diff.
def _str_presenter(dumper, data):
    if "\n" in data or len(data) > 120:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


yaml.add_representer(str, _str_presenter, Dumper=yaml.SafeDumper)


def normalize_doi(doi: str) -> str:
    return (doi or "").strip().lower()


def strip_jats(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def issued_to_date(item: dict) -> str:
    parts = (item.get("issued", {}).get("date-parts") or [[]])[0]
    if not parts:
        return ""
    year = parts[0]
    if len(parts) >= 2:
        return f"{year:04d}-{parts[1]:02d}"
    return f"{year:04d}"


def is_first_author(item: dict) -> bool:
    authors = item.get("author") or []
    for a in authors:
        if a.get("sequence") == "first":
            return FAMILY in a.get("family", "").lower()
    if authors:
        return FAMILY in authors[0].get("family", "").lower()
    return False


def europepmc_abstract(doi: str) -> str:
    if not doi:
        return ""
    params = {"query": f"DOI:{doi}", "resultType": "core", "format": "json"}
    try:
        r = requests.get(EUROPEPMC, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        results = r.json().get("resultList", {}).get("result", [])
        if results:
            return (results[0].get("abstractText") or "").strip()
    except requests.RequestException:
        pass
    return ""


def to_entry(item: dict) -> dict:
    doi = item.get("DOI", "")
    abstract = strip_jats(item.get("abstract", "")) or europepmc_abstract(doi) or ABSTRACT_TODO
    authors = " ∙ ".join(
        f"{a.get('given', '')} {a.get('family', '')}".strip()
        for a in (item.get("author") or [])
    )
    return {
        "title": (item.get("title") or [""])[0],
        "authors": authors,
        "venue_label": "Journal",
        "venue": (item.get("container-title") or [""])[0],
        "date": issued_to_date(item),
        "first_author": is_first_author(item),
        "url": item.get("URL") or (f"https://doi.org/{doi}" if doi else ""),
        "link_text": "View Manuscript",
        "doi": doi,
        "abstract": abstract,
    }


def find_new(items: list[dict], known_dois: set[str]) -> list[dict]:
    seen: set[str] = set()
    new: list[dict] = []
    for it in items:
        doi = normalize_doi(it.get("DOI", ""))
        title = (it.get("title") or [""])[0]
        if not doi or not title or doi in known_dois or doi in seen:
            continue
        seen.add(doi)
        new.append(it)
    return new


def crossref_works(orcid: str) -> list[dict]:
    params = {"filter": f"orcid:{orcid}", "rows": 200, "mailto": MAILTO}
    r = requests.get(CROSSREF, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()["message"]["items"]


def load_existing() -> list[dict]:
    if DATA.exists():
        return yaml.safe_load(DATA.read_text(encoding="utf-8")) or []
    return []


def load_ignored() -> set[str]:
    """Normalized DOIs that must never be imported (hand-maintained blocklist)."""
    if IGNORE.exists():
        data = yaml.safe_load(IGNORE.read_text(encoding="utf-8")) or []
        return {normalize_doi(d) for d in data if d}
    return set()


def dump_entries(entries: list) -> str:
    """Serialize entries to a YAML list fragment (block scalars for long/multiline strings)."""
    return yaml.safe_dump(entries, allow_unicode=True, sort_keys=False, width=1000)


def main() -> int:
    existing = load_existing()
    known = {normalize_doi(p.get("doi", "")) for p in existing if p.get("doi")}
    known |= load_ignored()
    items = crossref_works(ORCID)
    new_items = find_new(items, known)
    if not new_items:
        print("No new publications.")
        return 0
    new_entries = [to_entry(it) for it in new_items]

    if DATA.exists():
        existing_raw = DATA.read_text(encoding="utf-8")
    else:
        existing_raw = ""

    if existing_raw.strip():
        if not existing_raw.endswith("\n"):
            existing_raw += "\n"
        DATA.write_text(existing_raw + dump_entries(new_entries), encoding="utf-8")
    else:
        DATA.write_text(dump_entries(new_entries), encoding="utf-8")

    for e in new_entries:
        print(f"Added: {e['title']} ({e['date']}, first_author={e['first_author']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
