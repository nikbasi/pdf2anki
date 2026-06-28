"""Tests for pdf2anki."""

from __future__ import annotations

import json
from pathlib import Path

import fitz
import genanki
import pytest

from pdf2anki.anki_export import export_apkg, export_colpkg, export_json, export_multideck_apkg, load_json_cards
from pdf2anki.config import load_config, save_config
from pdf2anki.models import BookConfig, CardType, Flashcard
from pdf2anki.pdf_reader import extract_chapters


def _make_sample_pdf(path: Path) -> None:
    doc = fitz.open()
    pages = [
        ("Luku 1\n\nHei! Minä olen Maria. Tervetuloa Suomeen.", 16),
        ("Luku 1 (continued)\n\nKiitos. Mitä kuuluu? Hyvää, kiitos.", 11),
        ("Luku 2\n\nPerheeni on suuri. Minulla on kaksi sisarusta.", 16),
    ]
    for text, size in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=size)
    doc.save(path)
    doc.close()


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    pdf = tmp_path / "book.pdf"
    _make_sample_pdf(pdf)
    return pdf


def test_extract_chapters_by_heading(sample_pdf: Path) -> None:
    config = BookConfig(source_language="fi", target_language="en")
    chapters = extract_chapters(sample_pdf, config)
    titles = [c.title for c in chapters]
    assert any("Luku 1" in t for t in titles)
    assert any("Luku 2" in t for t in titles)
    assert all(len(c.text) > 10 for c in chapters)


def test_manual_chapter_ranges(sample_pdf: Path) -> None:
    config = BookConfig(
        chapters=[
            {"title": "Part A", "page_start": 1, "page_end": 2},
            {"title": "Part B", "page_start": 3, "page_end": 3},
        ]
    )
    chapters = extract_chapters(sample_pdf, config)
    assert len(chapters) == 2
    assert "Maria" in chapters[0].text
    assert "Perheeni" in chapters[1].text


def test_config_roundtrip(tmp_path: Path) -> None:
    cfg_path = tmp_path / "book.yaml"
    original = BookConfig(deck_name="Test", source_language="fi")
    save_config(original, cfg_path)
    loaded = load_config(cfg_path)
    assert loaded.deck_name == "Test"
    assert loaded.source_language == "fi"


def test_export_apkg(tmp_path: Path) -> None:
    cards = [
        Flashcard(
            front="hei",
            back="hello",
            card_type=CardType.VOCABULARY,
            chapter="Luku 1",
            tags=["chapter:luku-1"],
        )
    ]
    config = BookConfig(deck_name="Test Deck")
    out = tmp_path / "deck.apkg"
    export_apkg(cards, config, out)
    assert out.exists()
    assert out.stat().st_size > 100

    # genanki produces valid sqlite zip
    import zipfile

    with zipfile.ZipFile(out) as zf:
        assert "collection.anki2" in zf.namelist()


def test_json_export_roundtrip(tmp_path: Path) -> None:
    cards = [Flashcard(front="a", back="b", chapter="Ch1")]
    path = tmp_path / "cards.json"
    export_json(cards, path)
    loaded = load_json_cards(path)
    assert loaded[0].front == "a"


def test_export_colpkg_multi_deck(tmp_path: Path) -> None:
    cards = [
        Flashcard(front="hei", back="hello", chapter="1 — Hei", tags=["1"]),
        Flashcard(front="moi", back="hi", chapter="2 — Moi", tags=["2"]),
    ]
    config = BookConfig(deck_name="Test Book")
    out = export_multideck_apkg(cards, config, tmp_path / "book.apkg")
    assert out.exists()
    assert out.suffix == ".apkg"

    import sqlite3
    import zipfile

    with zipfile.ZipFile(out) as zf:
        assert "collection.anki2" in zf.namelist()
        db = tmp_path / "col.db"
        db.write_bytes(zf.read("collection.anki2"))
    conn = sqlite3.connect(db)
    deck_count = len(json.loads(conn.execute("SELECT decks FROM col").fetchone()[0]))
    card_count = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
    assert deck_count >= 2
    assert card_count == 2
