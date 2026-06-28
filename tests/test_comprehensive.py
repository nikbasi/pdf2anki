"""Tests for comprehensive chapter deck generation."""

from __future__ import annotations

from pdf2anki.models import BookConfig, Chapter, GenerationStyle
from pdf2anki.prompts import (
    build_user_prompt,
    chunk_chapter_text,
    is_comprehensive,
    system_prompt_for,
)


def test_is_comprehensive() -> None:
    curated = BookConfig(generation_style=GenerationStyle.CURATED)
    comprehensive = BookConfig(generation_style=GenerationStyle.COMPREHENSIVE)
    assert not is_comprehensive(curated)
    assert is_comprehensive(comprehensive)


def test_comprehensive_system_prompt_differs() -> None:
    config = BookConfig(source_language="fi")
    curated = system_prompt_for(config)
    config.generation_style = GenerationStyle.COMPREHENSIVE
    comprehensive = system_prompt_for(config)
    assert "COMPLETE chapter coverage" in comprehensive
    assert "Curate high-value" in curated


def test_comprehensive_user_prompt_no_card_limit() -> None:
    chapter = Chapter(title="TAVOITE 1: Hei", page_start=1, page_end=5, text="Hei! Minä olen Maria.")
    config = BookConfig(source_language="fi", generation_style=GenerationStyle.COMPREHENSIVE)
    prompt = build_user_prompt(chapter, config)
    assert "No upper limit" in prompt
    assert "15–30" not in prompt


def test_comprehensive_uses_extra_prompt_comprehensive() -> None:
    chapter = Chapter(title="Ch1", page_start=1, page_end=1, text="text")
    config = BookConfig(
        generation_style=GenerationStyle.COMPREHENSIVE,
        extra_prompt="curate only",
        extra_prompt_comprehensive="cover everything",
    )
    prompt = build_user_prompt(chapter, config)
    assert "cover everything" in prompt
    assert "curate only" not in prompt


def test_chunk_chapter_text_short() -> None:
    text = "Short chapter text."
    assert chunk_chapter_text(text, max_chars=1000) == [text]


def test_chunk_chapter_text_splits_long() -> None:
    paragraphs = [f"Paragraph {i}.\n" + ("word " * 50) for i in range(20)]
    text = "\n\n".join(paragraphs)
    chunks = chunk_chapter_text(text, max_chars=500, overlap=100)
    assert len(chunks) > 1
    assert all(len(c) <= 500 + 50 for c in chunks)  # small slack for long single paras
    joined = " ".join(chunks)
    assert "Paragraph 0" in joined
    assert "Paragraph 19" in joined
