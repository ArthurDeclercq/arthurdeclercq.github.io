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


def test_strip_jats_drops_abstract_heading_and_collapses_whitespace():
    raw = "<jats:title>Abstract</jats:title>\n      <jats:p>Line one\n      line two.</jats:p>"
    assert fc.strip_jats(raw) == "Line one line two."


def test_clean_title_superscript_and_newlines():
    assert fc.clean_title("TIMS\n   <sup>2</sup>\n   Rescore: A pipeline") == "TIMS²Rescore: A pipeline"
    assert fc.clean_title("narrowPASEF:\nA Sample-Aware\nStrategy") == "narrowPASEF: A Sample-Aware Strategy"
    assert fc.clean_title("Using <i>in vivo</i> data") == "Using in vivo data"


def test_title_key_ignores_case_markup_and_superscripts():
    assert fc.title_key("TIMS²Rescore: A Pipeline") == fc.title_key("TIMS\n<sup>2</sup>\nRescore: a pipeline")


def test_find_new_skips_preprint_of_published_work():
    items = [
        {"DOI": "10.1101/pre", "title": ["Pre"], "type": "posted-content",
         "relation": {"is-preprint-of": [{"id": "10.1/pub"}]}},
        {"DOI": "10.1/pub", "title": ["Pub"], "type": "journal-article"},
    ]
    assert [n["DOI"] for n in fc.find_new(items, set())] == ["10.1/pub"]


def test_find_new_skips_preprint_listed_by_journal_has_preprint():
    items = [
        {"DOI": "10.1101/pre", "title": ["Different preprint title"], "type": "posted-content"},
        {"DOI": "10.1/pub", "title": ["Pub"], "type": "journal-article",
         "relation": {"has-preprint": [{"id": "10.1101/pre"}]}},
    ]
    assert [n["DOI"] for n in fc.find_new(items, set())] == ["10.1/pub"]


def test_find_new_skips_all_versions_of_superseded_preprint():
    items = [
        {"DOI": "10.26434/chemrxiv.1/v1", "title": ["Old title"], "type": "posted-content"},
        {"DOI": "10.26434/chemrxiv.1/v3", "title": ["New title"], "type": "posted-content",
         "relation": {"is-preprint-of": [{"id": "10.1/pub"}]}},
        {"DOI": "10.1/pub", "title": ["New title"], "type": "journal-article"},
    ]
    assert [n["DOI"] for n in fc.find_new(items, set())] == ["10.1/pub"]


def test_find_new_keeps_latest_preprint_version_only():
    items = [
        {"DOI": "10.26434/chemrxiv.1/v1", "title": ["T"], "type": "posted-content"},
        {"DOI": "10.26434/chemrxiv.1/v2", "title": ["T revised"], "type": "posted-content"},
    ]
    assert [n["DOI"] for n in fc.find_new(items, set())] == ["10.26434/chemrxiv.1/v2"]


def test_find_new_skips_new_version_of_known_preprint():
    items = [{"DOI": "10.21203/rs.3.rs-1/v2", "title": ["T"], "type": "posted-content"}]
    assert fc.find_new(items, {"10.21203/rs.3.rs-1/v1"}) == []


def test_find_new_prefers_journal_over_preprint_with_same_title():
    items = [
        {"DOI": "10.1101/pre", "title": ["iDeepLC: chemical structure"], "type": "posted-content"},
        {"DOI": "10.1/pub", "title": ["iDeepLC: Chemical Structure"], "type": "journal-article"},
    ]
    assert [n["DOI"] for n in fc.find_new(items, set())] == ["10.1/pub"]


def test_find_new_skips_title_already_listed():
    items = [{"DOI": "10.1101/pre", "title": ["MS\n<sup>2</sup>\nRescore: Boosts"], "type": "posted-content"}]
    assert fc.find_new(items, set(), known_titles={fc.title_key("MS²Rescore: boosts")}) == []


def test_to_entry_uses_preprint_server_as_venue():
    base = {"title": ["T"], "issued": {"date-parts": [[2025, 2]]}, "abstract": "<jats:p>A</jats:p>",
            "type": "posted-content", "container-title": []}
    assert fc.to_entry({**base, "DOI": "10.1101/x", "institution": [{"name": "bioRxiv"}]})["venue"] == "bioRxiv"
    assert fc.to_entry({**base, "DOI": "10.26434/chemrxiv.1/v2"})["venue"] == "ChemRxiv"


def test_find_new_keeps_journal_version_of_listed_preprint_title():
    items = [{"DOI": "10.1/pub", "title": ["Same Title"], "type": "journal-article"}]
    new = fc.find_new(items, {"10.1101/pre"}, known_titles={fc.title_key("Same title")})
    assert [n["DOI"] for n in new] == ["10.1/pub"]


def test_strip_jats_drops_plain_abstract_prefix():
    assert fc.strip_jats("<jats:p>Abstract Major histocompatibility</jats:p>") == "Major histocompatibility"


RAW = '''- title: "Old preprint"
  venue: "Biorxiv"
  doi: "10.1101/2025.01.01.1"

- title: "Journal paper"
  venue: "Journal X"
  doi: "10.1/j"
'''


def test_preprint_match_by_has_preprint_relation():
    existing = yaml.safe_load(RAW)
    item = {"DOI": "10.2/new", "title": ["Renamed on publication"], "type": "journal-article",
            "relation": {"has-preprint": [{"id": "10.1101/2025.01.01.1"}]}}
    assert fc.preprint_match(item, existing) == 0


def test_preprint_match_by_title_only_for_preprint_entries():
    existing = yaml.safe_load(RAW)
    pub = {"DOI": "10.2/new", "title": ["OLD PREPRINT"], "type": "journal-article"}
    assert fc.preprint_match(pub, existing) == 0
    same_as_journal = {"DOI": "10.2/new", "title": ["Journal paper"], "type": "journal-article"}
    assert fc.preprint_match(same_as_journal, existing) is None


def test_preprint_match_ignores_preprint_items():
    existing = yaml.safe_load(RAW)
    item = {"DOI": "10.1101/x", "title": ["Old preprint"], "type": "posted-content"}
    assert fc.preprint_match(item, existing) is None


def test_merge_replaces_in_place_and_appends_rest():
    new = {"title": "Published", "doi": "10.2/new"}
    extra = {"title": "Extra", "doi": "10.3/x"}
    out = fc.merge_text(RAW, {0: new}, [extra])
    entries = yaml.safe_load(out)
    assert [e["title"] for e in entries] == ["Published", "Journal paper", "Extra"]
    # Untouched entries keep their exact bytes.
    assert '- title: "Journal paper"\n  venue: "Journal X"\n  doi: "10.1/j"\n' in out
    assert "Old preprint" not in out
