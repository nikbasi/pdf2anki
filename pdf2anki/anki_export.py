from __future__ import annotations

import json
import random
from pathlib import Path

import genanki

from pdf2anki.models import BookConfig, Flashcard

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


def export_apkg(
    cards: list[Flashcard],
    config: BookConfig,
    output_path: str | Path,
    *,
    deck_id: int | None = None,
) -> Path:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    deck = genanki.Deck(deck_id or random.randrange(1 << 30), config.deck_name)
    model = _note_model()

    for card in cards:
        note = genanki.Note(
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
        deck.add_note(note)

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
