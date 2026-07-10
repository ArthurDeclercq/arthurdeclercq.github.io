from pathlib import Path

import yaml

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


def test_load_ignored_reads_and_normalizes(tmp_path, monkeypatch):
    ignore_file = tmp_path / "publications_ignore.yml"
    ignore_file.write_text("- 10.ABC/Xyz\n- 10.def/2\n", encoding="utf-8")
    monkeypatch.setattr(fc, "IGNORE", ignore_file)
    assert fc.load_ignored() == {"10.abc/xyz", "10.def/2"}


def test_load_ignored_missing_file_returns_empty_set(tmp_path, monkeypatch):
    monkeypatch.setattr(fc, "IGNORE", tmp_path / "does_not_exist.yml")
    assert fc.load_ignored() == set()


def test_find_new_skips_ignored_doi():
    items = [
        {"DOI": "10.x/ignored", "title": ["Bad"]},
        {"DOI": "10.x/good", "title": ["Good"]},
    ]
    new = fc.find_new(items, known_dois={"10.x/ignored"})
    assert [n["DOI"] for n in new] == ["10.x/good"]


def test_append_only_preserves_existing_bytes():
    original_raw = fc.DATA.read_text(encoding="utf-8")
    original_entries = yaml.safe_load(original_raw) or []
    original_len = len(original_entries)

    synthetic_entry = {
        "title": "Synthetic Test Entry",
        "authors": "Arthur Declercq ∙ Lennart Martens",
        "venue_label": "Journal",
        "venue": "Journal of Synthetic Tests",
        "date": "2026-01",
        "first_author": True,
        "url": "https://doi.org/10.0000/synthetic",
        "link_text": "View Manuscript",
        "doi": "10.0000/synthetic",
        "abstract": "A synthetic abstract for append-only verification.",
    }

    existing_raw = original_raw
    if not existing_raw.endswith("\n"):
        existing_raw += "\n"

    result = existing_raw + fc.dump_entries([synthetic_entry])

    original_normalized = original_raw if original_raw.endswith("\n") else original_raw + "\n"
    assert result.startswith(original_normalized)

    result_entries = yaml.safe_load(result)
    assert len(result_entries) == original_len + 1
    assert result_entries[:original_len] == original_entries
    assert result_entries[-1] == synthetic_entry
