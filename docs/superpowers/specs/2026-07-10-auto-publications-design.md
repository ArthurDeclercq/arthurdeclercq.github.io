# Design: YAML-driven publications with monthly Crossref PR

Date: 2026-07-10
Status: Approved (pending spec review)

## Problem

Each publication on `index.qmd` is a hand-written `.publication-item` HTML block
(currently 16 blocks, lines ~191-514). Adding a paper means copying the template,
filling every field, and preserving fiddly details (co-first `&`, rich abstract
HTML, `Book` vs `Journal` label, `View Book Chapter` link text). This is tedious
and error-prone.

The visual layout, the automatic "New" flag, first-author grouping, sorting, and
gold divider must all stay exactly as they are today.

## Scope

In scope:
- Move publication content into a single YAML data file.
- Generate the HTML blocks from that file at build time.
- A monthly GitHub Action that discovers new publications from Crossref and opens
  a pull request appending them to the YAML file.

In scope (added):
- Auto-deploy on merge to `main` via a GitHub Action (replaces the manual
  `quarto publish gh-pages`).
- The GitHub repo settings required for the Actions to push `gh-pages` and open
  PRs.

Out of scope:
- Changing the client-side JS (toggle abstract, New tag, sort, divider color).
  These continue to run unchanged on the generated DOM.
- Migrating GitHub Pages off the `gh-pages` branch. Pages keeps serving from
  `gh-pages`; the deploy Action just pushes that branch in CI instead of you
  running the command locally.

## What stays identical

The four `DOMContentLoaded` scripts at the bottom of `index.qmd` operate on
`.publication-item` elements and their `data-year` / `data-first-author`
attributes. As long as the generated blocks carry those attributes and match the
existing markup, behavior is unchanged:
- "New" tag: any pub within 200 days of today (`newThreshold = 200`).
- Sort: first-author items first, then date descending.
- Gold divider (`#c9933a`) after the last first-author pub.
- Abstract expand/collapse via `toggleAbstract`.

## Components

### 1. `publications.yml` (source of truth)

One list entry per paper. Fields:

| Field | Meaning | Drives |
|-------|---------|--------|
| `title` | Publication title | `.publication-title` |
| `authors` | Full author string, keep `∙` separators and co-first `&` | `.publication-authors` |
| `venue_label` | `Journal` or `Book` | `<strong>` label |
| `venue` | Journal / book name | journal line |
| `date` | `YYYY-MM` (or `YYYY`) | `data-year`, "New" flag, sort, displayed "Month Year" |
| `first_author` | boolean | `data-first-author`, gold-divider grouping |
| `url` | Manuscript / DOI URL | `manuscript-link` href |
| `link_text` | e.g. `View Manuscript`, `View Book Chapter` | link label |
| `abstract` | Raw HTML allowed (`<strong>`, `<br>`, `<a>`) as a block scalar | `.abstract-text` |
| `doi` | DOI (bare, e.g. `10.1021/...`) | dedup key for the fetch job |

Rich abstracts (e.g. the `<strong>Background:</strong><br>...` metaproteomics
entry) are stored verbatim using YAML block scalars (`|`) so existing formatting
is preserved.

The displayed "Month Year" string (e.g. "February 2025") is derived from `date`
by the render script, so it never drifts from `data-year`.

### 2. `scripts/render_publications.py`

- Reads `publications.yml`.
- For each entry, renders one `.publication-item` block followed by one
  `<div class="divider"></div>`, matching `templates/manuscript_template.html`
  exactly.
- Writes the concatenated output to `_publications.html`.
- Pure Python + `pyyaml`. No Jupyter kernel.
- Registered as a Quarto **pre-render** step in `_quarto.yml`, so it runs on every
  `quarto render` / `quarto preview` / `quarto publish`.

`_publications.html` is git-ignored and regenerated on every build, so review
diffs show only clean YAML changes.

### 3. `index.qmd` change

Replace the 16 inline blocks (the content between the `Publications` title and the
closing `</div></section>`, currently lines ~191-514) with:

```
{{< include _publications.html >}}
```

The `<section id="publications">` wrapper, `.max-widht` container, the
`Publications` heading, and all four scripts stay in place.

### 4. `scripts/fetch_crossref.py`

- Queries Crossref works filtered by ORCID `0000-0002-9376-1399`.
- Loads existing `publications.yml`, builds a set of known DOIs.
- For each returned work whose DOI is not already present:
  - Extract title, container-title (venue), issued date (-> `YYYY-MM`), DOI, URL.
  - `first_author = (author[0] family name == "Declercq")`. Co-first `&` cannot be
    auto-detected; left for human review in the PR.
  - Abstract lookup order: Crossref `abstract` (JATS, tags stripped) -> Europe PMC
    by DOI (`abstractText`) -> empty string with a `# TODO: abstract` YAML comment.
  - `venue_label` defaults to `Journal`; `link_text` defaults to `View Manuscript`.
    Both are review points.
- Appends new entries to `publications.yml`. Never modifies existing entries.
- Idempotent: re-running with no new DOIs leaves the file unchanged.

Author disambiguation relies on the ORCID filter, so unrelated "Declercq A"
papers are not pulled.

### 5. `.github/workflows/update-publications.yml`

- Trigger: `schedule` (monthly cron) plus `workflow_dispatch` for manual runs.
- Steps: checkout `main`, set up Python, `pip install pyyaml requests`, run
  `scripts/fetch_crossref.py`.
- If `publications.yml` changed, open a pull request via
  `peter-evans/create-pull-request` with a body listing the added titles.
- Arthur reviews (co-first `&`, blank abstracts, `venue_label`, `link_text`),
  edits in the PR if needed, merges.
- Merge to `main` triggers the deploy Action (component 6) automatically.

### 6. `.github/workflows/deploy.yml`

- Trigger: `push` to `main` (plus `workflow_dispatch`).
- Steps: checkout, set up Quarto (`quarto-dev/quarto-actions/setup`), set up Python
  + `pip install pyyaml requests` (the pre-render step needs them), then
  `quarto-dev/quarto-actions/publish` with `target: gh-pages`.
- The publish action runs `quarto render` (firing `render_publications.py`
  pre-render) and pushes `_site` to the `gh-pages` branch using `GITHUB_TOKEN`.
- Pages continues serving from `gh-pages`; `CNAME` survives via the existing
  `resources:` entry, so `arthurdeclercq.bio` keeps working.
- Concurrency guard so overlapping merges do not race the deploy.

## GitHub repo settings required

Repo: `ArthurDeclercq/arthurdeclercq.github.io` (public).

1. Actions -> General -> Workflow permissions: **Read and write permissions**
   (lets the deploy Action push `gh-pages`) and **Allow GitHub Actions to create
   and approve pull requests** (lets the monthly Action open the PR).
   Applied via `gh api` (see below).
2. Pages -> Build and deployment -> Source: **Deploy from a branch**, branch
   `gh-pages` / root. Already configured (site is live); no change.

These are applied during implementation, not assumed manual.

## Data flow

```
Crossref (ORCID filter)                         monthly
        |                                          |
        v                                          v
fetch_crossref.py  --append-->  publications.yml  (PR, human review, merge)
                                        |
                    quarto render/publish (pre-render)
                                        v
                            render_publications.py
                                        |
                                        v
                               _publications.html  (git-ignored)
                                        |
                          {{< include >}} in index.qmd
                                        v
                        _site/index.html  (client JS: New tag, sort, dividers)
```

## Migration

One-time: extract all 16 existing blocks in `index.qmd` into `publications.yml`,
preserving abstract HTML, co-first `&`, `Book`/`Journal` labels, and custom link
text. Verify the rendered `_publications.html` reproduces the current page
(visual diff via `quarto preview`) before removing the inline blocks.

## Error handling

- Crossref/Europe PMC network error: fetch script exits non-zero, Action fails, no
  PR opened. No partial writes to the YAML.
- Missing abstract: entry still added with empty abstract and a `# TODO` marker so
  the PR review catches it.
- Malformed `date`: render script falls back to using the raw string for
  `data-year` (the existing JS already handles both `YYYY-MM` and `YYYY`).
- Duplicate DOI: skipped by the known-DOI set.

## Testing

- `render_publications.py`: unit test that a sample YAML entry produces markup
  matching the template (attributes present, abstract HTML preserved,
  `Book` label + custom link text honored).
- Migration check: rendered output for the 16 existing entries visually matches
  the current live page.
- `fetch_crossref.py`: test DOI-dedup (no new entries when all DOIs known) and
  first-author computation on a fixture Crossref response.

## Dependencies

- Python 3, `pyyaml`, `requests`.
- Quarto pre-render support (already a `type: website` project).
- GitHub Action: `actions/checkout`, `actions/setup-python`,
  `peter-evans/create-pull-request`.
