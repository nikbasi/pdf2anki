from __future__ import annotations

import json
import random
import re
import zlib
from pathlib import Path

import genanki

from pdf2anki.models import BookConfig, Flashcard
from pdf2anki.tags import chapter_deck_name

MODEL_ID = 1607392319


def _note_model() -> genanki.Model:
    return genanki.Model(
        MODEL_ID,
        "PDF2Anki Language Model",
        fields=[
            {"name": "Front"},
            {"name": "Back"},
            {"name": "Context"},
            {"name": "Chapter"},
            {"name": "CardType"},
        ],
        templates=[
            {
                "name": "Card",
                "qfmt": """
<div class="chapter">{{Chapter}}</div>
<div class="type">{{CardType}}</div>
<div class="front">{{Front}}</div>
""",
                "afmt": """
{{FrontSide}}
<hr id="answer">
<div class="back">{{Back}}</div>
{{#Context}}<div class="context"><i>{{Context}}</i></div>{{/Context}}
""",
            }
        ],
        css="""
.card { font-family: arial; font-size: 20px; text-align: center; color: black; background-color: white; }
.chapter { font-size: 12px; color: #666; margin-bottom: 8px; }
.type { font-size: 11px; color: #999; text-transform: uppercase; margin-bottom: 12px; }
.front { font-size: 22px; }
.back { font-size: 18px; margin-top: 12px; }
.context { font-size: 14px; color: #444; margin-top: 16px; }
""",
    )


def _deck_id(name: str) -> int:
    return zlib.adler32(name.encode("utf-8")) & 0x7FFFFFFF


def _chapter_sort_key(chapter_name: str) -> tuple[int, str]:
    match = re.match(r"^(\d+)", chapter_name.strip())
    if match:
        return (int(match.group(1)), chapter_name)
    return (9999, chapter_name)


def _note_for_card(card: Flashcard, model: genanki.Model, config: BookConfig) -> genanki.Note:
    return genanki.Note(
        model=model,
        fields=[
            card.front,
            card.back,
            card.context or "",
            card.chapter,
            card.card_type.value,
        ],
        tags=card.tags + [config.source_language, config.target_language],
    )


def _build_multideck_package(
    cards: list[Flashcard],
    config: BookConfig,
    out: Path,
) -> Path:
    by_chapter: dict[str, list[Flashcard]] = {}
    for card in cards:
        by_chapter.setdefault(card.chapter, []).append(card)

    model = _note_model()
    decks: list[genanki.Deck] = []
    for chapter_name in sorted(by_chapter, key=_chapter_sort_key):
        deck_name = chapter_deck_name(config.deck_name, chapter_name)
        deck = genanki.Deck(_deck_id(deck_name), deck_name)
        for card in by_chapter[chapter_name]:
            deck.add_note(_note_for_card(card, model, config))
        decks.append(deck)

    genanki.Package(decks).write_to_file(str(out))
    return out


def export_multideck_apkg(
    cards: list[Flashcard],
    config: BookConfig,
    output_path: str | Path,
) -> Path:
    """Bundle all chapter decks into one importable .apkg (merges into existing collection)."""
    out = Path(output_path)
    if out.suffix != ".apkg":
        out = out.with_suffix(".apkg")
    out.parent.mkdir(parents=True, exist_ok=True)
    return _build_multideck_package(cards, config, out)


def export_colpkg(
    cards: list[Flashcard],
    config: BookConfig,
    output_path: str | Path,
) -> Path:
    """Bundle all chapter decks into one collection package (.colpkg)."""
    out = Path(output_path)
    if out.suffix != ".colpkg":
        out = out.with_suffix(".colpkg")
    out.parent.mkdir(parents=True, exist_ok=True)
    return _build_multideck_package(cards, config, out)


def export_apkg(
    cards: list[Flashcard],
    config: BookConfig,
    output_path: str | Path,
    *,
    deck_id: int | None = None,
    deck_name: str | None = None,
) -> Path:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    deck = genanki.Deck(deck_id or random.randrange(1 << 30), deck_name or config.deck_name)
    model = _note_model()

    for card in cards:
        deck.add_note(_note_for_card(card, model, config))

    package = genanki.Package(deck)
    package.write_to_file(str(out))
    return out


def export_json(cards: list[Flashcard], output_path: str | Path) -> Path:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = [c.model_dump(mode="json") for c in cards]
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def load_json_cards(path: str | Path) -> list[Flashcard]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Flashcard.model_validate(item) for item in data]
