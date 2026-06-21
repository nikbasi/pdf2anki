from __future__ import annotations

from dataclasses import dataclass

from pdf2anki.models import BookConfig, CardType, Chapter
from pdf2anki.tags import chapter_label

# Full prompt for cloud APIs with plenty of context.
FINNISH_SYSTEM_PROMPT = """You create Anki flashcards for Finnish learners from textbook chapter text.

Goal: usable Finnish — words, grammar, and sentences that work without the textbook.

Curate high-value material (not every word in a list). Prioritize: core verbs + conjugation, reusable Q&A patterns, grammar taught in the lesson, useful dialogue lines rewritten as standalone sentences.

Card types: vocabulary, phrase, sentence, grammar, conjugation, case, cloze, production.
- conjugation: "puhua (minä)" → "puhun — I speak"
- case: "Suomi (elatiivi)" → "Suomesta — from Finland"
- cloze: "Minä ___ suomea." → "Minä puhun suomea."
- production: English cue → Finnish answer

Never: picture/map drills (kuvassa), listening (Kuuntele), book-only deictic questions.
Backs: English, use <br>, 1–3 lines. Chapter scope only. No duplicate fronts.

Return ONLY JSON: {"cards": [{"front","back","card_type","context?"}]}"""

# Shorter prompt for local models — less RAM, faster inference.
FINNISH_SYSTEM_PROMPT_LOCAL = """Anki cards for Finnish learners from textbook text. Curate useful words, verbs, grammar, phrases.

Types: vocabulary, phrase, sentence, grammar, conjugation, case, cloze, production.
No picture/listening exercises. Backs in English with <br>. JSON only:
{"cards": [{"front","back","card_type"}]}"""

GENERIC_SYSTEM_PROMPT = """Create Anki flashcards from textbook chapters. No picture references. JSON only: {"cards": [...]}"""

_BATCH_FOCUS = {
    1: "verbs, conjugation tables, grammar rules, and case forms",
    2: "vocabulary, phrases, sentences, cloze, and production (English → Finnish)",
}


def system_prompt_for(config: BookConfig, *, local: bool = False) -> str:
    if config.source_language.lower() in {"fi", "fin", "finnish", "suomi"}:
        return FINNISH_SYSTEM_PROMPT_LOCAL if local else FINNISH_SYSTEM_PROMPT
    return GENERIC_SYSTEM_PROMPT


def _card_count_instruction(config: BookConfig, *, max_cards: int | None = None) -> str:
    if max_cards is not None:
        return f"Create at most {max_cards} cards in this batch."
    if config.cards_per_chapter is None:
        return "Typical lesson: 15–30 cards total across batches. Quality over quantity."
    return f"Soft guide: ~{config.cards_per_chapter} cards for the full chapter."


def build_user_prompt(
    chapter: Chapter,
    config: BookConfig,
    *,
    max_chars: int = 10000,
    batch: int | None = None,
    max_cards: int | None = None,
    existing_fronts: list[str] | None = None,
) -> str:
    types = ", ".join(t.value for t in config.card_types)
    text = chapter.text
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[... truncated ...]"

    extra = f"\n\nBook-specific notes:\n{config.extra_prompt}" if config.extra_prompt else ""
    label = chapter_label(chapter.title)
    count = _card_count_instruction(config, max_cards=max_cards)

    batch_line = ""
    if batch is not None:
        focus = _BATCH_FOCUS.get(batch, "mixed content")
        batch_line = f"\nBatch {batch}: focus on {focus}."
        if existing_fronts:
            sample = existing_fronts[:20]
            batch_line += f"\nDo NOT duplicate these fronts: {sample}"
            if len(existing_fronts) > 20:
                batch_line += f" … and {len(existing_fronts) - 20} more"

    return f"""{config.source_language} → {config.target_language} | Chapter: {label}
Types: {types}
{count}{batch_line}

Chapter text:
---
{text}
---{extra}

Return {{"cards": [...]}} for "{label}". JSON only."""
