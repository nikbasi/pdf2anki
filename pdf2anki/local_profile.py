"""Local LM settings — Qwen uses batched safe mode; Gemma uses full single-call generation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LocalProfile:
    context_length: int
    max_tokens: int
    max_input_chars: int
    cards_per_batch: int  # 0 = no cap (single call)
    batches_per_chapter: int
    cooldown_seconds: float
    max_retries: int


# Gemma 26B: one call per chapter, full prompt — stable on 24 GB Mac.
GEMMA_LOCAL = LocalProfile(
    context_length=8192,
    max_tokens=4096,
    max_input_chars=8000,
    cards_per_batch=0,
    batches_per_chapter=1,
    cooldown_seconds=0.0,
    max_retries=2,
)

# Qwen 27B: small batches to avoid OOM.
QWEN_LOCAL = LocalProfile(
    context_length=4096,
    max_tokens=1536,
    max_input_chars=3500,
    cards_per_batch=10,
    batches_per_chapter=2,
    cooldown_seconds=15.0,
    max_retries=1,
)


def profile_for_model(model: str) -> LocalProfile:
    if "qwen" in model.lower():
        return QWEN_LOCAL
    return GEMMA_LOCAL
