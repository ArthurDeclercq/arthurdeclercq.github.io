import re
from datetime import datetime

import render_arluxis as ra


def photo(id, place, taken, r=0.6667, **extra):
    return dict(id=id, place=place, taken=datetime.fromisoformat(taken), r=r, **extra)


def order(gallery):
    """Photo ids per plate, in page order."""
    html = ra.plates(sorted(gallery, key=lambda p: p["taken"], reverse=True))
    return [tuple(re.findall(r'alt="(\w+)"', block)) for block in re.split(r'^      <div class="plate[ "]', html, flags=re.M)[1:]]


def fake_figure(p, indent):
    return f'{indent}<img alt="{p["id"]}">'


def test_upright_photos_from_one_place_are_paired(monkeypatch):
    monkeypatch.setattr(ra, "figure", fake_figure)
    gallery = [
        photo("a", "Ghent", "2026-01-01T10:00"),
        photo("b", "Ghent", "2026-01-01T11:00"),
        photo("c", "Ghent", "2026-01-01T11:05"),
        photo("d", "Ghent", "2026-01-01T12:00", r=1.5),
        photo("e", "Rome", "2026-01-01T09:00"),
    ]
    # b and c are closest in time; a stays alone; landscapes and other places are not paired
    assert order(gallery) == [("d",), ("c", "b"), ("a",), ("e",)]


def test_pair_overrides(monkeypatch):
    monkeypatch.setattr(ra, "figure", fake_figure)
    gallery = [
        photo("a", "Ghent", "2026-01-01T10:00", pair_at="older"),
        photo("b", "Ghent", "2026-01-01T11:00", r=1.5),
        photo("c", "Ghent", "2026-01-01T12:00"),
        photo("d", "Ghent", "2026-01-01T13:00", single=True),
    ]
    # The pair waits for its older photo, so the landscape comes first
    assert order(gallery) == [("d",), ("b",), ("c", "a")]


def test_current_page_renders():
    photos = ra.load()
    html = ra.render(photos)
    assert html.count("<figure") == len(photos)
    for key, *_ in ra.GALLERIES:
        assert f'id="{key}"' in html
