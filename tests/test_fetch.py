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
