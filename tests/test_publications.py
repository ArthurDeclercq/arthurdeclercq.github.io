import yaml

import fetch_crossref as fc
import render_publications as rp


def test_to_entry_cleans_crossref_record():
    item = {
        "DOI": "10.1101/2024.05.29.596400",
        "type": "posted-content",
        "institution": [{"name": "bioRxiv"}],
        "title": ["TIMS\n   <sup>2</sup>\n   Rescore: A DDA-PASEF\n   pipeline"],
        "abstract": "<jats:title>Abstract</jats:title>\n  <jats:p>Line one\n  line <jats:italic>two</jats:italic>.</jats:p>",
        "issued": {"date-parts": [[2024, 6, 1]]},
        "author": [
            {"given": "Arthur", "family": "Declercq", "sequence": "first"},
            {"given": "Lennart", "family": "Martens", "sequence": "additional"},
        ],
    }
    e = fc.to_entry(item)
    assert e["title"] == "TIMS²Rescore: A DDA-PASEF pipeline"
    assert e["abstract"] == "Line one line two."
    assert e["venue"] == "bioRxiv"
    assert e["date"] == "2024-06"
    assert e["authors"] == "Arthur Declercq ∙ Lennart Martens"
    assert e["first_author"] is True
    assert e["url"] == "https://doi.org/10.1101/2024.05.29.596400"



def test_to_entry_book_chapter():
    item = {"DOI": "10.1007/978-1-0716-4832-2_5", "type": "book-chapter", "title": ["Chapter"],
            "container-title": ["Methods in Molecular Biology", "Immunoproteomics"],
            "abstract": "<jats:p>A.</jats:p>", "issued": {"date-parts": [[2025, 10]]}}
    e = fc.to_entry(item)
    assert (e["venue_label"], e["venue"], e["link_text"]) == ("Book", "Immunoproteomics", "View Book Chapter")


def test_openalex_dois_keeps_publications_only(monkeypatch):
    results = [
        {"doi": "https://doi.org/10.1186/S40793-026-00962-Z", "type": "article"},
        {"doi": "https://doi.org/10.1007/978-1-0716-4832-2_5", "type": "book-chapter"},
        {"doi": "https://doi.org/10.5281/zenodo.18757265", "type": "article"},
        {"doi": "https://doi.org/10.5281/zenodo.7669701", "type": "dataset"},
        {"doi": None, "type": "article"},
    ]

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"results": results}

    monkeypatch.setattr(fc.requests, "get", lambda *a, **k: Response())
    assert fc.openalex_dois(fc.ORCID) == {"10.1186/s40793-026-00962-z", "10.1007/978-1-0716-4832-2_5"}


def test_first_author_only_when_declercq_leads():
    other_leads = {"author": [
        {"family": "Scheid", "sequence": "first"},
        {"family": "Declercq", "sequence": "additional"},
    ]}
    no_sequence = {"author": [{"family": "Declercq"}, {"family": "Martens"}]}
    assert fc.is_first_author(other_leads) is False
    assert fc.is_first_author(no_sequence) is True


def test_find_new_keeps_one_record_per_work():
    items = [
        # ChemRxiv versions of a published paper: all dropped for the journal version.
        {"DOI": "10.26434/chemrxiv.1/v1", "title": ["Hardware synergy"], "type": "posted-content"},
        {"DOI": "10.26434/chemrxiv.1/v3", "title": ["Instrument synergy"], "type": "posted-content",
         "relation": {"is-preprint-of": [{"id": "10.1021/pub1"}]}},
        {"DOI": "10.1021/pub1", "title": ["Instrument synergy"], "type": "journal-article"},
        # Preprint known only from the journal side of the relation.
        {"DOI": "10.1101/pre2", "title": ["Renamed preprint"], "type": "posted-content"},
        {"DOI": "10.1021/pub2", "title": ["Published title"], "type": "journal-article",
         "relation": {"has-preprint": [{"id": "10.1101/pre2"}]}},
        # No relation, same title: journal wins.
        {"DOI": "10.1101/pre3", "title": ["iDeepLC: chemical structure"], "type": "posted-content"},
        {"DOI": "10.1021/pub3", "title": ["iDeepLC: Chemical Structure"], "type": "journal-article"},
        # Unpublished preprint with two versions: latest wins.
        {"DOI": "10.26434/chemrxiv.4/v1", "title": ["Draft"], "type": "posted-content"},
        {"DOI": "10.26434/chemrxiv.4/v2", "title": ["Draft revised"], "type": "posted-content"},
        {"DOI": "10.9/untitled", "title": []},
    ]
    new = fc.find_new(items, set())
    assert [n["DOI"] for n in new] == [
        "10.1021/pub1", "10.1021/pub2", "10.1021/pub3", "10.26434/chemrxiv.4/v2",
    ]


def test_find_new_skips_listed_works():
    items = [
        {"DOI": "10.1/known", "title": ["Known"], "type": "journal-article"},
        {"DOI": "10.21203/rs.3.rs-1/v2", "title": ["New version"], "type": "posted-content"},
        {"DOI": "10.1101/pre", "title": ["MS\n<sup>2</sup>\nRescore: boosts"], "type": "posted-content"},
        {"DOI": "10.1/pub", "title": ["Listed preprint title"], "type": "journal-article"},
    ]
    known_dois = {"10.1/known", "10.21203/rs.3.rs-1/v1"}
    known_titles = {fc.title_key("MS²Rescore: Boosts"), fc.title_key("Listed preprint title")}
    new = fc.find_new(items, known_dois, known_titles)
    # A journal article with a listed title is the published version of that preprint.
    assert [n["DOI"] for n in new] == ["10.1/pub"]


RAW = '''- title: "Old preprint"
  venue: "Biorxiv"
  doi: "10.1101/2025.01.01.1"

- title: "Journal paper"
  venue: "Journal X"
  doi: "10.1/j"
'''


def test_preprint_match():
    existing = yaml.safe_load(RAW)
    by_relation = {"DOI": "10.2/a", "title": ["Renamed"], "type": "journal-article",
                   "relation": {"has-preprint": [{"id": "10.1101/2025.01.01.1"}]}}
    by_title = {"DOI": "10.2/b", "title": ["OLD PREPRINT"], "type": "journal-article"}
    journal_title = {"DOI": "10.2/c", "title": ["Journal paper"], "type": "journal-article"}
    preprint_item = {"DOI": "10.1101/x", "title": ["Old preprint"], "type": "posted-content"}
    assert fc.preprint_match(by_relation, existing) == 0
    assert fc.preprint_match(by_title, existing) == 0
    assert fc.preprint_match(journal_title, existing) is None
    assert fc.preprint_match(preprint_item, existing) is None


def test_merge_text_replaces_in_place_and_appends():
    out = fc.merge_text(RAW, {0: {"title": "Published", "doi": "10.2/a"}}, [{"title": "Extra"}])
    assert [e["title"] for e in yaml.safe_load(out)] == ["Published", "Journal paper", "Extra"]
    assert '- title: "Journal paper"\n  venue: "Journal X"\n  doi: "10.1/j"\n' in out


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
