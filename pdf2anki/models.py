from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class CardType(str, Enum):
    VOCABULARY = "vocabulary"
    PHRASE = "phrase"
    SENTENCE = "sentence"
    GRAMMAR = "grammar"
    CONJUGATION = "conjugation"
    CASE = "case"
    CLOZE = "cloze"
    PRODUCTION = "production"


class Flashcard(BaseModel):
    front: str
    back: str
    card_type: CardType = CardType.VOCABULARY
    chapter: str = ""
    tags: list[str] = Field(default_factory=list)
    context: Optional[str] = None


class Chapter(BaseModel):
    title: str
    page_start: int
    page_end: int
    text: str = ""


class BookConfig(BaseModel):
    """Optional YAML config for a book."""

    title: str = "Language Book"
    deck_name: str = "Language Book"
    source_language: str = "fi"
    target_language: str = "en"
    chapter_patterns: list[str] = Field(
        default_factory=lambda: [
            r"^Chapter\s+\d+",
            r"^Luku\s+\d+",
            r"^Kappale\s+\d+",
            r"^Unit\s+\d+",
            r"^Lesson\s+\d+",
            r"^\d+\.\s+[A-ZÅÄÖ]",
        ]
    )
    chapters: Optional[list[dict]] = None  # manual: [{title, page_start, page_end}]
    chapter_marker_pattern: Optional[str] = None  # e.g. Berlitz "TAVOITE 1:"
    cards_per_chapter: int | None = None  # optional soft hint only
    card_types: list[CardType] = Field(
        default_factory=lambda: [
            CardType.VOCABULARY,
            CardType.PHRASE,
            CardType.SENTENCE,
            CardType.GRAMMAR,
            CardType.CONJUGATION,
            CardType.CASE,
            CardType.CLOZE,
            CardType.PRODUCTION,
        ]
    )
    extra_prompt: str = ""
