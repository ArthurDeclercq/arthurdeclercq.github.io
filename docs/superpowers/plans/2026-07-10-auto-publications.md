# Auto-Publications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move publication content into a single `publications.yml`, generate the HTML blocks at Quarto build time, and add a monthly GitHub Action that pulls new papers from Crossref into a review PR, plus a deploy-on-merge Action.

**Architecture:** `publications.yml` is the single source of truth. A pre-render Python script (`render_publications.py`) turns it into `_publications.qmd` (git-ignored, raw HTML) that `index.qmd` includes. A fetch script (`fetch_crossref.py`) appends newly-discovered papers to the YAML. Two workflows: one opens a monthly PR, one deploys `main` to `gh-pages`. The existing client-side JS (New tag, sort, gold divider, abstract toggle) is untouched and keeps working on the generated DOM.

**Tech Stack:** Python 3.12 (`pyyaml`, `requests`), pytest, Quarto website project, GitHub Actions (`quarto-dev/quarto-actions`, `peter-evans/create-pull-request`).

## Global Constraints

- Generated blocks MUST carry `data-year="YYYY-MM"` (or `YYYY`) and `data-first-author="true|false"` exactly, and match `templates/manuscript_template.html` markup, or the client JS breaks.
- ORCID for fetch: `0000-0002-9376-1399`. Author family match: `declercq` (case-insensitive).
- `_publications.qmd` is generated and git-ignored — never edited by hand, never committed.
- Deploy target stays the `gh-pages` branch; `CNAME` survives via the existing `resources:` entry in `_quarto.yml`. Do not change Pages source.
- Author separator in the `authors` string is `∙` (U+2219). Co-first authors use `&`. Preserve both verbatim on migration.
- Repo: `ArthurDeclercq/arthurdeclercq.github.io`. Workflow permissions already set to `write` + PR-creation `true`.
- Scripts live in `scripts/`, tests in `tests/`. Run tests with `python -m pytest`.

---

### Task 1: Render script + template test

**Files:**
- Create: `scripts/render_publications.py`
- Create: `tests/conftest.py`
- Create: `tests/test_render.py`

**Interfaces:**
- Produces: `render_item(p: dict) -> str`, `render(pubs: list[dict]) -> str`, `format_date(d: str) -> str`, module constants `DATA` (Path to `publications.yml`), `OUT` (Path to `_publications.qmd`), `main() -> int`.

- [ ] **Step 1: Create `tests/conftest.py` so tests can import scripts**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_render.py
import render_publications as rp


def test_format_date_month():
    assert rp.format_date("2025-02") == "February 2025"


def test_format_date_year_only():
    assert rp.format_date("2022") == "2022"


def test_render_item_core_attributes():
    p = {
        "title": "My Paper",
        "authors": "Arthur Declercq ∙ Someone Else",
        "venue_label": "Journal",
        "venue": "Journal of Proteome Research",
        "date": "2025-02",
        "first_author": True,
        "url": "https://example.org/doi",
        "link_text": "View Manuscript",
        "abstract": "Short abstract.",
    }
    html = rp.render_item(p)
    assert 'data-year="2025-02"' in html
    assert 'data-first-author="true"' in html
    assert "<h3 class=\"publication-title\">My Paper</h3>" in html
    assert "<strong>Journal:</strong> Journal of Proteome Research" in html
    assert "February 2025" in html
    assert 'href="https://example.org/doi"' in html
    assert "View Manuscript" in html
    assert "Short abstract." in html
    assert 'class="divider"' in html


def test_render_item_book_and_custom_link_and_html_abstract():
    p = {
        "title": "Chapter",
        "authors": "Arthur Declercq",
        "venue_label": "Book",
        "venue": "Some Book",
        "date": "2024-06",
        "first_author": False,
        "url": "https://example.org/chapter",
        "link_text": "View Book Chapter",
        "abstract": "<strong>Background:</strong><br>Text with <a href=\"x\">link</a>.",
    }
    html = rp.render_item(p)
    assert 'data-first-author="false"' in html
    assert "<strong>Book:</strong> Some Book" in html
    assert "View Book Chapter" in html
    assert "<strong>Background:</strong><br>" in html  # abstract HTML preserved verbatim
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'render_publications'`.

- [ ] **Step 4: Write the implementation**

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_render.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add scripts/render_publications.py tests/conftest.py tests/test_render.py
git commit -m "feat: add publications render script with tests"
```

---

### Task 2: Migrate existing 15 publications into `publications.yml`

**Files:**
- Create: `publications.yml`
- Read (source of content): `index.qmd:191-514`

**Interfaces:**
- Produces: `publications.yml` — a YAML list; each item has keys `title, authors, venue_label, venue, date, first_author, url, link_text, doi, abstract`.

This task transcribes the 15 existing blocks. The content already lives in `index.qmd`; copy each field verbatim (especially abstract HTML, `∙` separators, co-first `&`). Use this mapping (source line = the `<div class="publication-item"` line):

| # | Paper | Source lines | first_author | venue_label | link_text |
|---|-------|-------------|--------------|-------------|-----------|
| 1 | TIMS²Rescore | 192-209 | true | Journal | View Manuscript |
| 2 | MHCquant2 | 213-231 | false | Journal | View Manuscript |
| 3 | IM2Deep | 235-253 | false | Journal | View Manuscript |
| 4 | MS2Rescore metaproteomics | 257-278 | false | Journal | View Manuscript |
| 5 | Bacterial epitope discovery | 283-301 | false | Journal | View Manuscript |
| 6 | MS2Rescore (MCP) | 305-323 | true | Journal | View Manuscript |
| 7 | MS2Rescore 3.0 (MS Amanda) | 327-345 | true | Journal | View Manuscript |
| 8 | MS²PIP web server | 348-366 | true | Journal | View Manuscript |
| 9 | Thunder-DDA-PASEF | 369-387 | false | Journal | View Manuscript |
| 10 | Single-cell book chapter | 390-408 | true | Book | View Book Chapter |
| 11 | psm_utils | 411-429 | false | Journal | View Manuscript |
| 12 | ionmob | 432-450 | false | Journal | View Manuscript |
| 13 | TargetDecoy (QC target-decoy) | 453-471 | false | Journal | View Manuscript |
| 14 | protein-nucleic acid cross-links | 475-493 | false | Journal | View Manuscript |
| 15 | Transfer learning in DeepLC | 496-514 | false | Journal | View Manuscript |

Field rules:
- `date`: use the existing `data-year` value from each block (e.g. `2025-02`). Quote it (`date: "2025-02"`) so YAML does not parse it oddly.
- `venue`: the text after `<strong>Journal:</strong>` / `<strong>Book:</strong>` (e.g. `Research Square`, `Biorxiv`, `Nature Communications`).
- `abstract`: everything inside `<p class="abstract-text">...</p>`, verbatim, as a YAML literal block scalar (`|`). Keep inner `<strong>`, `<br>`, `<a ...>` tags.
- `url`: the `href` of the `manuscript-link` anchor.
- `doi`: the DOI extracted from `url` when present (e.g. `10.1021/acs.jproteome.4c00609` from an ACS URL; `10.1101/2025.02.18.638865` from a biorxiv URL). This is the dedup key for Task 4 — populate it wherever a DOI is derivable so Crossref does not re-add the paper. Entry #4's URL is the literal placeholder `MANUSCRIPT_LINK`; set its `doi` to `""` and leave `url` as `MANUSCRIPT_LINK` (a known TODO; the monthly PR may resurface it for a real link).

- [ ] **Step 1: Create `publications.yml` — first two entries fully worked as the pattern**

```yaml
- title: "TIMS²Rescore: A DDA-PASEF optimized data-driven rescoring pipeline based on MS²Rescore"
  authors: "Arthur Declercq & Robbe Devreese ∙ Jonas Scheid ∙ Caroline Jachmann ∙ Tim Van Den Bossche ∙ Annica Preikschat ∙ David Gomez-Zepeda ∙ Jeewan Babu Rijal ∙ Aurélie Hirschler ∙ Jonathan R Krieger ∙ Tharan Srikumar ∙ George Rosenberger ∙ Dennis Trede ∙ Christine Carapito ∙ Stefan Tenzer ∙ Juliane S Walz ∙ Sven Degroeve ∙ Robbin Bouwmeester ∙ Lennart Martens ∙ Ralf Gabriels"
  venue_label: "Journal"
  venue: "Journal of Proteome Research"
  date: "2025-02"
  first_author: true
  url: "https://pubs.acs.org/doi/10.1021/acs.jproteome.4c00609"
  link_text: "View Manuscript"
  doi: "10.1021/acs.jproteome.4c00609"
  abstract: |
    The high throughput analysis of proteins with mass spectrometry (MS) is highly valuable for understanding human biology, discovering disease biomarkers, identifying therapeutic targets, and exploring pathogen interactions. To achieve these goals, specialized proteomics subfields – such as plasma proteomics, immunopeptidomics, and metaproteomics – must tackle specific analytical challenges, such as an increased identification ambiguity compared to routine proteomics experiments. Technical advancements in MS instrumentation can counter these issues by acquiring more discerning information at higher sensitivity levels, as is exemplified by the incorporation of ion mobility and parallel accumulation - serial fragmentation (PASEF) technologies in timsTOF instruments. In addition, AI-based bioinformatics solutions can help overcome ambiguity issues by integrating more data into the identification workflow. Here, we introduce TIMS2Rescore, a data-driven rescoring workflow optimized for DDA-PASEF data from timsTOF instruments. This platform includes new timsTOF MS2PIP spectrum prediction models and IM2Deep, a new deep learning-based peptide ion mobility predictor. Furthermore, to fully streamline data throughput, TIMS2Rescore directly accepts Bruker raw mass spectrometry data, and search results from ProteoScape and many other search engines, including MS Amanda and PEAKS. We showcase TIMS2Rescore performance on plasma proteomics, immunopeptidomics (HLA class I and II), and metaproteomics data sets. TIMS2Rescore is open-source and freely available at <a href="https://github.com/compomics/tims2rescore" target="_blank" class="abstract-link">https://github.com/compomics/tims2rescore.</a>

- title: "MHCquant2 refines immunopeptidomics tumor antigen discovery"
  authors: "Jonas Scheid ∙ Steffen Lemke ∙ Naomi Hoenisch-Gravel ∙ Anna Dengler ∙ Timo Sachsenberg ∙ Arthur Declerq ∙ Ralf Gabriels ∙ Jens Bauer ∙ Marcel Wacker ∙ Leon Bichmann ∙ Lennart Martens ∙ Marissa L. Dubbelaar ∙ Sven Nahnsen ∙ Juliane S. Walz"
  venue_label: "Journal"
  venue: "Research Square"
  date: "2024-12"
  first_author: false
  url: "https://www.researchsquare.com/article/rs-5560023/v1"
  link_text: "View Manuscript"
  doi: "10.21203/rs.3.rs-5560023/v1"
  abstract: |
    The identification of human leukocyte antigen (HLA)-presented peptides as targets of anti-cancer T cell response is pivotal for the development of novel immunotherapies. Mass spectrometry (MS)-based immunopeptidomics enables the detection of these peptides, yet confident identifications and thus implementation in immunotherapy design are hampered by the high diversity and low abundance of naturally presented HLA peptides. Here, we introduce MHCquant2, a Nextflow-based open-source pipeline that leverages OpenMS tools and peptide property predictors (DeepLC, MS2PIP) for highly sensitive and scalable HLA peptide identification and quantification across various MS platforms. MHCquant2 increased peptide identifications up to 27% with a significant expansion of low-abundant peptides, outperforming state-of-the-art pipelines. Using MHCquant2 we build a comprehensive benign tissue repository comprising re-analyzed data from available benign immunopeptidomes and a novel benignMHCquant2 dataset, adding more than 160,000 novel naturally presented HLA peptides. First applications of this benign repository and the MHCquant2 pipeline enabled (i) the refinement of tumor-associated antigens, (ii) the detection of novel, high-frequent tumor-exclusive peptide antigens for multiple tumor entities, and (iii) the identification and quantification of mutation-derived low-abundant neoepitopes. MHCquant2 refines tumor antigen discovery in immunopeptidomics, paving the way for the implementation of off-the-shelf and personalized immunotherapy design.
```

- [ ] **Step 2: Transcribe the remaining 13 entries (#3-#15)**

For each row in the mapping table, read the block at its source lines in `index.qmd` and add a YAML entry following the exact pattern from Step 1. Copy `title`, `authors`, `venue`, `abstract` verbatim. Set `date` from the block's `data-year`, `first_author`/`venue_label`/`link_text` from the table, `url` from the anchor href, `doi` derived from the URL. For entry #4 (metaproteomics) set `url: "MANUSCRIPT_LINK"` and `doi: ""`.

- [ ] **Step 3: Validate YAML parses and count is 15**

Run:
```bash
python -c "import yaml; d=yaml.safe_load(open('publications.yml',encoding='utf-8')); print(len(d)); assert len(d)==15; assert all({'title','authors','venue','date','first_author','url','link_text','doi','abstract'} <= set(x) for x in d)"
```
Expected: prints `15`, no assertion error.

- [ ] **Step 4: Render and confirm all 15 blocks generate**

Run:
```bash
python scripts/render_publications.py
python -c "print(open('_publications.qmd',encoding='utf-8').read().count('publication-item'))"
```
Expected: first prints `Rendered 15 publications -> _publications.qmd`; second prints `15`.

- [ ] **Step 5: Commit**

```bash
git add publications.yml
git commit -m "feat: migrate 15 publications into publications.yml"
```

---

### Task 3: Wire pre-render + include into the site

**Files:**
- Modify: `_quarto.yml:1-2` (project block)
- Modify: `index.qmd:191-514` (replace inline blocks with include)
- Modify: `.gitignore` (ignore generated file)

**Interfaces:**
- Consumes: `scripts/render_publications.py` (Task 1), `publications.yml` (Task 2).
- Produces: `_publications.qmd` at build time; `index.qmd` renders identically to before.

- [ ] **Step 1: Add the pre-render step to `_quarto.yml`**

Replace:
```yaml
project:
  type: website
```
with:
```yaml
project:
  type: website
  pre-render: scripts/render_publications.py
```

- [ ] **Step 2: Ignore the generated file**

Add a line to `.gitignore`:
```
_publications.qmd
```

- [ ] **Step 3: Replace the inline blocks in `index.qmd` with the include**

Delete lines 191-514 (everything from `<!-- Tims²Rescore -->` through the final `<div class="divider"></div>` at line 514) and put in their place:

```
{{< include _publications.qmd >}}
```

The result around the publications section must read:
```
    <h2 class="publications-title">Publications</h2>

{{< include _publications.qmd >}}

  </div>
  </section>
```
(The `<section>`, `.max-widht` div, heading, and all `<script>` blocks stay unchanged.)

- [ ] **Step 4: Render the site and verify publications appear**

Run:
```bash
python scripts/render_publications.py
quarto render index.qmd
python -c "print(open('_site/index.html',encoding='utf-8').read().count('publication-item'))"
```
Expected: prints `15`.

- [ ] **Step 5: Visual check**

Run: `quarto preview index.qmd`
Expected: Publications section looks identical to before — 15 papers, abstracts toggle open, first-author papers grouped on top, gold divider after the last first-author paper, "New" tag on any paper within 200 days of today. Stop the preview when confirmed.

- [ ] **Step 6: Commit**

```bash
git add _quarto.yml .gitignore index.qmd
git commit -m "feat: generate publications section from publications.yml at build"
```

---

### Task 4: Crossref fetch script

**Files:**
- Create: `scripts/fetch_crossref.py`
- Create: `tests/test_fetch.py`

**Interfaces:**
- Consumes: `publications.yml` (Task 2) for the known-DOI set.
- Produces: appends new entries to `publications.yml` with the same key set as Task 2. Testable pure functions: `issued_to_date(item: dict) -> str`, `is_first_author(item: dict) -> bool`, `strip_jats(text: str) -> str`, `normalize_doi(doi: str) -> str`, `find_new(items: list[dict], known_dois: set[str]) -> list[dict]`, `to_entry(item: dict) -> dict`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fetch.py
import fetch_crossref as fc


def test_issued_to_date_year_month():
    assert fc.issued_to_date({"issued": {"date-parts": [[2025, 2, 18]]}}) == "2025-02"


def test_issued_to_date_year_only():
    assert fc.issued_to_date({"issued": {"date-parts": [[2022]]}}) == "2022"


def test_issued_to_date_missing():
    assert fc.issued_to_date({}) == ""


def test_is_first_author_by_sequence():
    item = {"author": [
        {"family": "Declercq", "given": "Arthur", "sequence": "first"},
        {"family": "Martens", "given": "Lennart", "sequence": "additional"},
    ]}
    assert fc.is_first_author(item) is True


def test_is_first_author_false_when_other_leads():
    item = {"author": [
        {"family": "Scheid", "given": "Jonas", "sequence": "first"},
        {"family": "Declercq", "given": "Arthur", "sequence": "additional"},
    ]}
    assert fc.is_first_author(item) is False


def test_is_first_author_fallback_to_position_zero():
    item = {"author": [
        {"family": "Declercq", "given": "Arthur"},
        {"family": "Martens", "given": "Lennart"},
    ]}
    assert fc.is_first_author(item) is True


def test_strip_jats():
    assert fc.strip_jats("<jats:p>Hello <jats:italic>world</jats:italic></jats:p>") == "Hello world"


def test_normalize_doi_lowercases_and_strips():
    assert fc.normalize_doi("  10.1021/ACS.Jproteome  ") == "10.1021/acs.jproteome"


def test_find_new_skips_known_and_untitled():
    items = [
        {"DOI": "10.1/known", "title": ["Known"]},
        {"DOI": "10.2/new", "title": ["New"]},
        {"DOI": "10.3/notitle", "title": []},
        {"DOI": "10.2/new", "title": ["Dup in batch"]},
    ]
    new = fc.find_new(items, {"10.1/known"})
    assert [n["DOI"] for n in new] == ["10.2/new"]


def test_to_entry_shape():
    item = {
        "DOI": "10.9/x",
        "title": ["A Title"],
        "container-title": ["Journal X"],
        "URL": "https://doi.org/10.9/x",
        "issued": {"date-parts": [[2026, 1]]},
        "author": [{"family": "Declercq", "given": "Arthur", "sequence": "first"}],
        "abstract": "<jats:p>Abs.</jats:p>",
    }
    e = fc.to_entry(item)
    assert e["title"] == "A Title"
    assert e["venue"] == "Journal X"
    assert e["date"] == "2026-01"
    assert e["first_author"] is True
    assert e["doi"] == "10.9/x"
    assert e["venue_label"] == "Journal"
    assert e["link_text"] == "View Manuscript"
    assert e["abstract"] == "Abs."
    assert "Arthur Declercq" in e["authors"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_fetch.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fetch_crossref'`.

- [ ] **Step 3: Write the implementation**

```python
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


def main() -> int:
    existing = load_existing()
    known = {normalize_doi(p.get("doi", "")) for p in existing if p.get("doi")}
    items = crossref_works(ORCID)
    new_items = find_new(items, known)
    if not new_items:
        print("No new publications.")
        return 0
    new_entries = [to_entry(it) for it in new_items]
    combined = existing + new_entries
    DATA.write_text(
        yaml.safe_dump(combined, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    for e in new_entries:
        print(f"Added: {e['title']} ({e['date']}, first_author={e['first_author']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_fetch.py -v`
Expected: PASS (10 tests).

- [ ] **Step 5: Live smoke test (idempotency)**

Run:
```bash
python scripts/fetch_crossref.py
git diff --stat publications.yml
```
Expected: prints new-paper lines or `No new publications.`. If `publications.yml` changed, inspect the diff. Then run once more:
```bash
python scripts/fetch_crossref.py
```
Expected: second run prints `No new publications.` (idempotent — every DOI now known). Discard any experimental change with `git checkout -- publications.yml` unless the additions are genuine and reviewed.

- [ ] **Step 6: Commit**

```bash
git add scripts/fetch_crossref.py tests/test_fetch.py
git commit -m "feat: add Crossref fetch script with tests"
```

---

### Task 5: Deploy-on-merge workflow

**Files:**
- Create: `.github/workflows/deploy.yml`

**Interfaces:**
- Consumes: `_quarto.yml` pre-render (Task 3). Uses `GITHUB_TOKEN` to push `gh-pages`.

- [ ] **Step 1: Write the workflow**

```yaml
# .github/workflows/deploy.yml
name: Deploy site

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: deploy-gh-pages
  cancel-in-progress: false

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: quarto-dev/quarto-actions/setup@v2

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install pre-render dependencies
        run: pip install pyyaml requests

      - name: Render and publish to gh-pages
        uses: quarto-dev/quarto-actions/publish@v2
        with:
          target: gh-pages
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

- [ ] **Step 2: Lint the YAML**

Run:
```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/deploy.yml',encoding='utf-8')); print('ok')"
```
Expected: prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "ci: deploy to gh-pages on merge to main"
```

- [ ] **Step 4: Verify on GitHub (post-merge, manual)**

After this branch merges to `main`, open the repo Actions tab. Expected: "Deploy site" run succeeds and `https://arthurdeclercq.bio/` reflects the change. If the first run fails on token/permissions, confirm workflow permissions are `write` (already set) and re-run. Alternatively trigger manually via the "Run workflow" button (`workflow_dispatch`).

---

### Task 6: Monthly Crossref PR workflow

**Files:**
- Create: `.github/workflows/update-publications.yml`

**Interfaces:**
- Consumes: `scripts/fetch_crossref.py` (Task 4). Uses `peter-evans/create-pull-request`.

- [ ] **Step 1: Write the workflow**

```yaml
# .github/workflows/update-publications.yml
name: Update publications

on:
  schedule:
    - cron: "0 6 1 * *"   # 06:00 UTC on the 1st of each month
  workflow_dispatch:

permissions:
  contents: write
  pull-requests: write

jobs:
  fetch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install pyyaml requests

      - name: Fetch new publications from Crossref
        run: python scripts/fetch_crossref.py

      - name: Open pull request if publications.yml changed
        uses: peter-evans/create-pull-request@v6
        with:
          commit-message: "chore: add new publications from Crossref"
          branch: auto/update-publications
          delete-branch: true
          title: "Add new publications from Crossref"
          body: |
            Automated monthly Crossref pull. Review before merge:

            - Co-first authors: add ` & ` between the co-first names in `authors`.
            - `first_author` flag (Crossref position 0 heuristic — verify).
            - Abstracts marked `TODO: add abstract` (Crossref + Europe PMC had none).
            - `venue_label` (`Journal` vs `Book`) and `link_text`.
            - `venue` wording and `url`.
          labels: publications
```

- [ ] **Step 2: Lint the YAML**

Run:
```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/update-publications.yml',encoding='utf-8')); print('ok')"
```
Expected: prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/update-publications.yml
git commit -m "ci: monthly Crossref publications PR"
```

- [ ] **Step 4: Verify on GitHub (post-merge, manual)**

After merge to `main`, open Actions -> "Update publications" -> "Run workflow" (`workflow_dispatch`) to trigger once without waiting for the cron. Expected: run succeeds; if new DOIs exist, a PR titled "Add new publications from Crossref" appears with the review checklist. If none, the run reports "No new publications." and opens no PR.

---

## Integration verification (after all tasks)

- [ ] `python -m pytest -v` — all tests pass.
- [ ] `python scripts/render_publications.py && quarto render index.qmd` — site builds, `_site/index.html` has 15 `publication-item` blocks.
- [ ] `quarto preview index.qmd` — publications section visually identical to the pre-migration page (grouping, gold divider, New tag, abstract toggle).
- [ ] Merge to `main` triggers "Deploy site"; `arthurdeclercq.bio` updates.
- [ ] Manual `workflow_dispatch` of "Update publications" behaves correctly (PR or no-op).
