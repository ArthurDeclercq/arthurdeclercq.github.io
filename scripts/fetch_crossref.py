#!/usr/bin/env python3
"""Fetch new publications from Crossref by ORCID and append them to publications.yml.

Discovery is scoped by ORCID so unrelated "Declercq A" papers are not pulled.
Existing entries are never modified. Preprints superseded by a journal version
(Crossref is-preprint-of / has-preprint relations, or a matching title) and older
preprint versions are skipped. Abstract lookup order: Crossref JATS ->
Europe PMC by DOI -> a visible 'TODO: add abstract' placeholder for PR review.
Network errors abort with a non-zero exit and no partial write.
"""
from __future__ import annotations

import re
import sys
import unicodedata
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
PREPRINT_SERVERS = {"10.26434/chemrxiv": "ChemRxiv"}
SUPERSCRIPT = str.maketrans("0123456789+-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻")


# Keep long / multi-line strings readable as literal block scalars in the diff.
def _str_presenter(dumper, data):
    if "\n" in data or len(data) > 120:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


yaml.add_representer(str, _str_presenter, Dumper=yaml.SafeDumper)


def normalize_doi(doi: str) -> str:
    return (doi or "").strip().lower()


def strip_jats(text: str) -> str:
    text = re.sub(r"<jats:title>.*?</jats:title>", "", text or "", flags=re.S)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"^Abstract\b[:.]?\s*", "", text)


def _superscript(m: re.Match) -> str:
    inner = m.group(1).strip()
    return inner.translate(SUPERSCRIPT) if re.fullmatch(r"[0-9+-]+", inner) else inner


def clean_title(title: str) -> str:
    """Crossref titles can carry JATS/HTML markup and hard line breaks."""
    title = re.sub(r"\s*<(?:jats:)?sup>(.*?)</(?:jats:)?sup>\s*", _superscript, title or "", flags=re.S)
    return strip_jats(title)


def title_key(title: str) -> str:
    """Comparison key: case-, markup-, punctuation- and superscript-insensitive."""
    folded = unicodedata.normalize("NFKC", clean_title(title)).casefold()
    return re.sub(r"[^0-9a-z]+", "", folded)


def version_base(doi: str) -> str:
    """Strip a trailing preprint version ('/v2') so all versions share one key."""
    return re.sub(r"/v\d+$", "", normalize_doi(doi))


def version_number(doi: str) -> int:
    m = re.search(r"/v(\d+)$", normalize_doi(doi))
    return int(m.group(1)) if m else 0


def related_dois(item: dict, kind: str) -> set[str]:
    return {normalize_doi(r.get("id", "")) for r in (item.get("relation") or {}).get(kind, [])}


def is_preprint(item: dict) -> bool:
    return item.get("type") == "posted-content"


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
        "title": clean_title((item.get("title") or [""])[0]),
        "authors": authors,
        "venue_label": "Journal",
        "venue": venue(item),
        "date": issued_to_date(item),
        "first_author": is_first_author(item),
        "url": item.get("URL") or (f"https://doi.org/{doi}" if doi else ""),
        "link_text": "View Manuscript",
        "doi": doi,
        "abstract": abstract,
    }


def venue(item: dict) -> str:
    container = (item.get("container-title") or [""])[0]
    if container or not is_preprint(item):
        return container
    institution = (item.get("institution") or [{}])[0].get("name", "")
    if institution:
        return institution
    doi = normalize_doi(item.get("DOI", ""))
    return next((name for prefix, name in PREPRINT_SERVERS.items() if doi.startswith(prefix)), "")


def find_new(items: list[dict], known_dois: set[str], known_titles: set[str] = frozenset()) -> list[dict]:
    """Items not yet listed, keeping one record per work (journal > latest preprint version)."""
    # Preprints that have a journal version, from either side of the Crossref relation.
    superseded: set[str] = set()
    for it in items:
        if related_dois(it, "is-preprint-of"):
            superseded.add(normalize_doi(it.get("DOI", "")))
        superseded |= related_dois(it, "has-preprint")
    skip_bases = {version_base(d) for d in superseded | set(known_dois)}

    candidates = []
    for i, it in enumerate(items):
        doi = normalize_doi(it.get("DOI", ""))
        title = (it.get("title") or [""])[0]
        if not doi or not title or version_base(doi) in skip_bases:
            continue
        # A listed title only blocks preprints: a journal article with that title
        # is the published version of a listed preprint.
        if is_preprint(it) and title_key(title) in known_titles:
            continue
        candidates.append((i, it))

    # Journal articles first, then the newest preprint version, so those win ties.
    ranked = sorted(candidates, key=lambda c: (is_preprint(c[1]), -version_number(c[1]["DOI"]), c[0]))
    taken_titles: set[str] = set()
    taken_bases: set[str] = set()
    keep: set[int] = set()
    for i, it in ranked:
        key, base = title_key(it["title"][0]), version_base(it["DOI"])
        if key in taken_titles or base in taken_bases:
            continue
        taken_titles.add(key)
        taken_bases.add(base)
        keep.add(i)
    return [it for i, it in candidates if i in keep]


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
    known_titles = {title_key(p["title"]) for p in existing if p.get("title")}
    items = crossref_works(ORCID)
    new_items = find_new(items, known, known_titles)
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

    known_bases = {version_base(d) for d in known}
    for it, e in zip(new_items, new_entries):
        print(f"Added: {e['title']} ({e['date']}, first_author={e['first_author']})")
        for pre in sorted(related_dois(it, "has-preprint")):
            if version_base(pre) in known_bases:
                print(f"  Note: published version of listed preprint {pre}; consider removing that entry.")
        if "\ufffd" in e["title"] + e["abstract"]:
            print("  Note: Crossref text contains a replacement character (\ufffd); fix by hand.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
