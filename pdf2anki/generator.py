from __future__ import annotations

import json
import os
import re
from typing import Iterable

from openai import OpenAI

from pdf2anki.models import BookConfig, CardType, Chapter, Flashcard

SYSTEM_PROMPT = """You are an expert language tutor creating Anki flashcards from textbook chapters.

Given a chapter excerpt from a language-learning book, produce high-quality flashcards for memorization.

Card types:
- vocabulary: single word or short lexical item → translation + brief usage note
- phrase: common expression or collocation → translation + when to use it
- sentence: full example sentence → translation (use for natural usage)
- grammar: grammar point or pattern → explanation with 1-2 examples

Rules:
- Use the SOURCE language on the front and TARGET language on the back (unless grammar cards work better reversed).
- Prefer items that actually appear in the chapter text.
- Include articles, case forms, or conjugations when relevant for the language.
- Keep fronts concise; backs can have 1-3 short lines separated by <br>.
- Avoid duplicate or near-duplicate cards.
- Return ONLY valid JSON object with a "cards" array. Each item: front, back, card_type, context (optional).

card_type must be one of: vocabulary, phrase, sentence, grammar"""


def _build_user_prompt(chapter: Chapter, config: BookConfig) -> str:
    types = ", ".join(t.value for t in config.card_types)
    text = chapter.text
    if len(text) > 12000:
        text = text[:12000] + "\n\n[... truncated ...]"

    extra = f"\n\nAdditional instructions:\n{config.extra_prompt}" if config.extra_prompt else ""

    return f"""Source language: {config.source_language}
Target language: {config.target_language}
Chapter: {chapter.title}
Requested card types: {types}
Target number of cards: {config.cards_per_chapter}

Chapter text:
---
{text}
---{extra}

Return a JSON object: {{"cards": [...]}} with up to {config.cards_per_chapter} flashcards."""


def _parse_cards(raw: str, chapter: Chapter) -> list[Flashcard]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("Expected JSON array of cards")

    cards: list[Flashcard] = []
    slug = re.sub(r"[^\w]+", "-", chapter.title.lower()).strip("-")[:40]
    for item in data:
        card_type = CardType(item.get("card_type", "vocabulary"))
        tags = [f"chapter:{slug}", f"type:{card_type.value}"]
        cards.append(
            Flashcard(
                front=item["front"],
                back=item["back"],
                card_type=card_type,
                chapter=chapter.title,
                tags=tags,
                context=item.get("context"),
            )
        )
    return cards


def _clean_json_text(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", raw)
    return raw.strip()


def _extract_json_payload(content: str) -> list:
    raw = _clean_json_text(content)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            raise
        parsed = json.loads(_clean_json_text(match.group(0)))

    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict) and "cards" in parsed:
        return parsed["cards"]
    if isinstance(parsed, dict):
        for value in parsed.values():
            if isinstance(value, list):
                return value
    raise ValueError("Expected JSON object with a cards array")


def generate_cards_for_chapter(
    chapter: Chapter,
    config: BookConfig,
    *,
    model: str = "gpt-4o-mini",
    api_key: str | None = None,
    base_url: str | None = None,
) -> list[Flashcard]:
    client = OpenAI(
        api_key=api_key or os.environ.get("OPENAI_API_KEY") or "lm-studio",
        base_url=base_url or os.environ.get("OPENAI_BASE_URL"),
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(chapter, config)},
    ]

    kwargs: dict = {
        "model": model,
        "messages": messages,
        "temperature": 0.4,
    }
    use_json_mode = not (base_url or os.environ.get("OPENAI_BASE_URL", "")).startswith(
        "http://127.0.0.1"
    ) and not (base_url or os.environ.get("OPENAI_BASE_URL", "")).startswith(
        "http://localhost"
    )
    if use_json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = client.chat.completions.create(**kwargs)
    content = response.choices[0].message.content or "{}"
    try:
        parsed = _extract_json_payload(content)
    except (json.JSONDecodeError, ValueError):
        retry = client.chat.completions.create(
            model=model,
            messages=messages
            + [
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": "Your previous reply was not valid JSON. Reply again with ONLY a JSON object: {\"cards\": [...]}",
                },
            ],
            temperature=0.2,
        )
        content = retry.choices[0].message.content or "{}"
        parsed = _extract_json_payload(content)
    return _parse_cards(json.dumps(parsed), chapter)


def generate_cards(
    chapters: Iterable[Chapter],
    config: BookConfig,
    *,
    model: str = "gpt-4o-mini",
    api_key: str | None = None,
    base_url: str | None = None,
    chapter_filter: str | None = None,
) -> list[Flashcard]:
    all_cards: list[Flashcard] = []
    for chapter in chapters:
        if chapter_filter and chapter_filter.lower() not in chapter.title.lower():
            continue
        if len(chapter.text.strip()) < 50:
            continue
        cards = generate_cards_for_chapter(
            chapter,
            config,
            model=model,
            api_key=api_key,
            base_url=base_url,
        )
        all_cards.extend(cards)
    return all_cards
