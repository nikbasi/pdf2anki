from __future__ import annotations

import re

from pdf2anki.models import Flashcard

# Cards that only make sense with a textbook image, map, or audio exercise.
_PICTURE_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r"\bkuv(a|assa|an|aa|assa)\b",
        r"\bpicture\b",
        r"\b(katso|look at)\s+(tuota|tätä|tuo|tämä|that|this)\b",
        r"\bkuuntele\b",
        r"\blisten\b",
        r"\b(diagram|map|photo|image|illustration)\b",
        r"^mikä maa tämä on\??$",
        r"^onko tämä [A-Za-zÅÄÖåäö]+(?:\s+vai\s+[A-Za-zÅÄÖåäö]+)?\??$",
        r"^onko (hän|tämä henkilö) [A-ZÅÄÖ]",
        r"^ketk?ä ovat kuvassa\??$",
        r"^kuka on kuvassa\??$",
        r"^mikä huone tämä on\??$",
        r"^onko tämä (olohuone|keittiö|makuuhuone|kylpyhuone|koulu|kauppakeskus|tavaratalo)\??$",
        r"^missä (nojatuoli|sohva|televisio|kaukosäädin) on\??$",
        r"^tunnistatko\b",
        r"^valitse\b",
    ]
]

# Demonstratives used alone to point at book visuals, not as teachable vocabulary.
_DEMO_ONLY = re.compile(
    r"^(mikä|mitä|onko|kuka|ketkä|missä|mikä huone).*(tämä|tuo|tuota|tätä)\??$",
    re.I,
)


def is_picture_dependent(card: Flashcard) -> bool:
    front = card.front.strip()
    text = f"{front} {card.context or ''}".strip()
    if any(p.search(front) or p.search(text) for p in _PICTURE_PATTERNS):
        return True
    if _DEMO_ONLY.search(front):
        # Keep vocabulary that explicitly teaches tämä/tuo contrasts.
        if card.card_type.value == "vocabulary" and "→" in card.back:
            return False
        if re.search(r"\b(this|that|demonstrative)\b", card.back, re.I):
            return False
        return True
    return False


def filter_cards(cards: list[Flashcard]) -> list[Flashcard]:
    return [c for c in cards if not is_picture_dependent(c)]
