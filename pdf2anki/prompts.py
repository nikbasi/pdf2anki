from __future__ import annotations

from pdf2anki.models import BookConfig, Chapter, GenerationStyle
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

FINNISH_SYSTEM_PROMPT_COMPREHENSIVE = """You create Anki flashcards for Finnish learners from textbook chapter text.

Goal: COMPLETE chapter coverage — every teachable item from the lesson becomes a card so the student can study the chapter without the textbook.

Include ALL of: every vocabulary word and translation, every phrase, every conjugation row, every case form taught, every grammar rule with examples, every dialogue line (as standalone sentence or production cards), every exercise Q&A that works without the book.

Card types: vocabulary, phrase, sentence, grammar, conjugation, case, cloze, production.
- conjugation: "puhua (minä)" → "puhun — I speak"
- case: "Suomi (elatiivi)" → "Suomesta — from Finland"
- cloze: "Minä ___ suomea." → "Minä puhun suomea."
- production: English cue → Finnish answer

Skip ONLY: picture/map drills (kuvassa), listening (Kuuntele), book-only deictic questions.
Do NOT skip vocabulary because a list is long. No upper limit on card count.
Backs: English, use <br>, 1–3 lines. No duplicate fronts.

Return ONLY JSON: {"cards": [{"front","back","card_type","context?"}]}"""

# Shorter prompt for local models — less RAM, faster inference.
FINNISH_SYSTEM_PROMPT_LOCAL = """Anki cards for Finnish learners from textbook text. Curate useful words, verbs, grammar, phrases.

Types: vocabulary, phrase, sentence, grammar, conjugation, case, cloze, production.
No picture/listening exercises. Backs in English with <br>. JSON only:
{"cards": [{"front","back","card_type"}]}"""

FINNISH_SYSTEM_PROMPT_LOCAL_COMPREHENSIVE = """Anki cards for Finnish learners. Cover ALL teachable content in the text section — every word, verb form, grammar rule, phrase, and dialogue line.

Types: vocabulary, phrase, sentence, grammar, conjugation, case, cloze, production.
No picture/listening exercises. No card limit. Backs in English with <br>. JSON only:
{"cards": [{"front","back","card_type"}]}"""

GENERIC_SYSTEM_PROMPT = """Create Anki flashcards from textbook chapters. No picture references. JSON only: {"cards": [...]}"""

GENERIC_SYSTEM_PROMPT_COMPREHENSIVE = """Create Anki flashcards from textbook chapters covering ALL teachable content — vocabulary, grammar, phrases, and exercises that work without the book. No card limit. No picture references. JSON only: {"cards": [...]}"""

_BATCH_FOCUS = {
    1: "verbs, conjugation tables, grammar rules, and case forms",
    2: "vocabulary, phrases, sentences, cloze, and production (English → Finnish)",
}

_COMPREHENSIVE_BATCH_FOCUS = {
    1: "vocabulary lists, word pairs, and dialogue lines",
    2: "conjugation tables, case forms, and grammar rules",
    3: "phrases, example sentences, cloze, production, and exercise Q&A",
}


def is_comprehensive(config: BookConfig) -> bool:
    return config.generation_style == GenerationStyle.COMPREHENSIVE


def system_prompt_for(config: BookConfig, *, local: bool = False) -> str:
    comprehensive = is_comprehensive(config)
    if config.source_language.lower() in {"fi", "fin", "finnish", "suomi"}:
        if comprehensive:
            return FINNISH_SYSTEM_PROMPT_LOCAL_COMPREHENSIVE if local else FINNISH_SYSTEM_PROMPT_COMPREHENSIVE
        return FINNISH_SYSTEM_PROMPT_LOCAL if local else FINNISH_SYSTEM_PROMPT
    if comprehensive:
        return GENERIC_SYSTEM_PROMPT_COMPREHENSIVE
    return GENERIC_SYSTEM_PROMPT


def _card_count_instruction(
    config: BookConfig,
    *,
    max_cards: int | None = None,
    chunk: int | None = None,
    total_chunks: int | None = None,
) -> str:
    if is_comprehensive(config):
        chunk_line = ""
        if chunk is not None and total_chunks is not None:
            chunk_line = f" Text section {chunk}/{total_chunks}."
        if max_cards is not None:
            return (
                f"Create up to {max_cards} cards for this batch — cover every teachable item "
                f"in this section that is not already listed.{chunk_line} No upper limit overall."
            )
        return (
            "Create a card for every teachable item in this section. "
            "Include every vocabulary word, not just highlights. No upper limit."
        )
    if max_cards is not None:
        return f"Create at most {max_cards} cards in this batch."
    if config.cards_per_chapter is None:
        return "Typical lesson: 15–30 cards total across batches. Quality over quantity."
    return f"Soft guide: ~{config.cards_per_chapter} cards for the full chapter."


def _extra_prompt_for(config: BookConfig) -> str:
    if is_comprehensive(config) and config.extra_prompt_comprehensive:
        return config.extra_prompt_comprehensive
    return config.extra_prompt


def build_user_prompt(
    chapter: Chapter,
    config: BookConfig,
    *,
    max_chars: int = 10000,
    batch: int | None = None,
    max_cards: int | None = None,
    existing_fronts: list[str] | None = None,
    chunk: int | None = None,
    total_chunks: int | None = None,
    text_override: str | None = None,
) -> str:
    types = ", ".join(t.value for t in config.card_types)
    text = text_override if text_override is not None else chapter.text
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[... truncated ...]"

    extra_text = _extra_prompt_for(config)
    extra = f"\n\nBook-specific notes:\n{extra_text}" if extra_text else ""
    label = chapter_label(chapter.title)
    count = _card_count_instruction(
        config, max_cards=max_cards, chunk=chunk, total_chunks=total_chunks
    )

    batch_line = ""
    if batch is not None:
        focus_map = _COMPREHENSIVE_BATCH_FOCUS if is_comprehensive(config) else _BATCH_FOCUS
        focus = focus_map.get(batch, "remaining content in this section")
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


def chunk_chapter_text(text: str, max_chars: int, overlap: int = 400) -> list[str]:
    """Split chapter text into overlapping chunks at paragraph boundaries."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return [text[:max_chars]]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    def flush() -> None:
        nonlocal current, current_len
        if current:
            chunks.append("\n\n".join(current))
            current = []
            current_len = 0

    def overlap_tail(paras: list[str]) -> list[str]:
        tail: list[str] = []
        tail_len = 0
        for para in reversed(paras):
            para_len = len(para) + 2
            if tail_len + para_len > overlap:
                break
            tail.insert(0, para)
            tail_len += para_len
        return tail

    for para in paragraphs:
        para_len = len(para) + (2 if current else 0)
        if para_len > max_chars:
            flush()
            for start in range(0, len(para), max_chars - overlap):
                chunks.append(para[start : start + max_chars])
            continue
        if current_len + para_len > max_chars:
            flush()
            if chunks:
                current = overlap_tail(chunks[-1].split("\n\n"))
                current_len = sum(len(p) + 2 for p in current) - (2 if current else 0)
        current.append(para)
        current_len += para_len

    flush()
    return chunks or [text[:max_chars]]
