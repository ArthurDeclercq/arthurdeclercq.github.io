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
