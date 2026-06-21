from __future__ import annotations

import json
import os
import re
import time
from typing import Iterable

from openai import BadRequestError, OpenAI

from pdf2anki.filters import filter_cards
from pdf2anki.lmstudio import ensure_model_loaded
from pdf2anki.local_profile import LocalProfile, profile_for_model
from pdf2anki.tags import card_tags, chapter_label
from pdf2anki.models import BookConfig, CardType, Chapter, Flashcard
from pdf2anki.prompts import build_user_prompt, system_prompt_for

LOCAL_LM_HOSTS = ("http://127.0.0.1", "http://localhost")
_QWEN_ASSISTANT_PREFILL = " \n"


def _is_local_lm(base_url: str) -> bool:
    return any(base_url.startswith(host) for host in LOCAL_LM_HOSTS)


def _resolve_model_id(client: OpenAI, model: str) -> str:
    try:
        models = client.models.list().data
    except Exception:
        return model
    if not models:
        return model
    for entry in models:
        mid = entry.id
        if mid == model or model in mid or mid in model:
            return mid
    if "qwen" in model.lower():
        for entry in models:
            if "qwen" in entry.id.lower():
                return entry.id
    return models[0].id


def _parse_cards(raw: str, chapter: Chapter) -> list[Flashcard]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("Expected JSON array of cards")

    cards: list[Flashcard] = []
    for item in data:
        if not isinstance(item, dict) or "front" not in item or "back" not in item:
            continue
        try:
            card_type = CardType(item.get("card_type", "vocabulary"))
        except ValueError:
            card_type = CardType.VOCABULARY
        tags = card_tags(chapter.title, card_type.value)
        cards.append(
            Flashcard(
                front=item["front"],
                back=item["back"],
                card_type=card_type,
                chapter=chapter_label(chapter.title),
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
    for pattern in (
        re.compile(r"<\s*think\s*>[\s\S]*?<\s*/\s*think\s*>", re.I),
        re.compile(
            r"<\|redacted_thinking\|>[\s\S]*?<\|(?:redacted_im_end|/redacted_thinking)\|>",
            re.I,
        ),
    ):
        raw = pattern.sub("", raw)
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


def _messages_for_local_lm(messages: list[dict]) -> list[dict]:
    if messages and messages[-1].get("role") != "assistant":
        return [*messages, {"role": "assistant", "content": _QWEN_ASSISTANT_PREFILL}]
    return messages


def _completion_kwargs(
    model: str,
    messages: list[dict],
    *,
    base_url: str,
    temperature: float,
    profile: LocalProfile | None = None,
) -> dict:
    if _is_local_lm(base_url):
        messages = _messages_for_local_lm(messages)
    kwargs: dict = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if _is_local_lm(base_url):
        kwargs["max_tokens"] = profile.max_tokens if profile else 2048
    else:
        kwargs["response_format"] = {"type": "json_object"}
    return kwargs


def _create_completion(
    client: OpenAI,
    kwargs: dict,
    *,
    profile: LocalProfile,
    model: str,
) -> object:
    retries = profile.max_retries
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return client.chat.completions.create(**kwargs)
        except BadRequestError as exc:
            last_err = exc
            err = str(exc).lower()
            if attempt >= retries or not any(
                k in err for k in ("crashed", "503", "502", "504", "no models loaded")
            ):
                raise
            ensure_model_loaded(model, context_length=profile.context_length)
            time.sleep(profile.cooldown_seconds)
    if last_err:
        raise last_err
    raise RuntimeError("completion failed")


def _single_completion(
    client: OpenAI,
    *,
    model: str,
    messages: list[dict],
    base_url: str,
    profile: LocalProfile,
    chapter: Chapter,
    temperature: float = 0.35,
) -> list[Flashcard]:
    kwargs = _completion_kwargs(
        model, messages, base_url=base_url, temperature=temperature, profile=profile
    )
    response = _create_completion(client, kwargs, profile=profile, model=model)
    content = response.choices[0].message.content or "{}"
    try:
        parsed = _extract_json_payload(content)
    except (json.JSONDecodeError, ValueError):
        retry = _create_completion(
            client,
            _completion_kwargs(
                model,
                messages
                + [
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": 'Output ONLY valid JSON: {"cards": [...]}. No markdown.',
                    },
                ],
                base_url=base_url,
                temperature=0.2,
                profile=profile,
            ),
            profile=profile,
            model=model,
        )
        content = retry.choices[0].message.content or "{}"
        parsed = _extract_json_payload(content)
    return filter_cards(_parse_cards(json.dumps(parsed), chapter))


def _generate_local_single(
    chapter: Chapter,
    config: BookConfig,
    *,
    client: OpenAI,
    model: str,
    base_url: str,
    profile: LocalProfile,
) -> list[Flashcard]:
    """One LLM call per chapter with the full prompt (Gemma and similar)."""
    messages = [
        {"role": "system", "content": system_prompt_for(config, local=False)},
        {
            "role": "user",
            "content": build_user_prompt(chapter, config, max_chars=profile.max_input_chars),
        },
    ]
    return _single_completion(
        client,
        model=model,
        messages=messages,
        base_url=base_url,
        profile=profile,
        chapter=chapter,
    )


def _generate_local_batched(
    chapter: Chapter,
    config: BookConfig,
    *,
    client: OpenAI,
    model: str,
    base_url: str,
    profile: LocalProfile,
) -> list[Flashcard]:
    """Two small LLM calls per chapter — keeps peak memory low."""
    all_cards: list[Flashcard] = []
    seen: set[str] = set()

    for batch in range(1, profile.batches_per_chapter + 1):
        messages = [
            {"role": "system", "content": system_prompt_for(config, local=True)},
            {
                "role": "user",
                "content": build_user_prompt(
                    chapter,
                    config,
                    max_chars=profile.max_input_chars,
                    batch=batch,
                    max_cards=profile.cards_per_batch or None,
                    existing_fronts=list(seen) if seen else None,
                ),
            },
        ]
        batch_cards = _single_completion(
            client,
            model=model,
            messages=messages,
            base_url=base_url,
            profile=profile,
            chapter=chapter,
        )
        for card in batch_cards:
            key = card.front.strip().lower()
            if key not in seen:
                seen.add(key)
                all_cards.append(card)
        if batch < profile.batches_per_chapter:
            time.sleep(profile.cooldown_seconds)

    return all_cards


def generate_cards_for_chapter(
    chapter: Chapter,
    config: BookConfig,
    *,
    model: str = "gpt-4o-mini",
    api_key: str | None = None,
    base_url: str | None = None,
) -> list[Flashcard]:
    effective_url = base_url or os.environ.get("OPENAI_BASE_URL") or ""
    profile = profile_for_model(model) if _is_local_lm(effective_url) else None

    client = OpenAI(
        api_key=api_key or os.environ.get("OPENAI_API_KEY") or "lm-studio",
        base_url=base_url or os.environ.get("OPENAI_BASE_URL"),
    )
    if _is_local_lm(effective_url):
        ensure_model_loaded(model, context_length=profile.context_length)
        model = _resolve_model_id(client, model)
        if profile.batches_per_chapter > 1:
            return _generate_local_batched(
                chapter, config, client=client, model=model, base_url=effective_url, profile=profile
            )
        return _generate_local_single(
            chapter, config, client=client, model=model, base_url=effective_url, profile=profile
        )

    messages = [
        {"role": "system", "content": system_prompt_for(config, local=False)},
        {
            "role": "user",
            "content": build_user_prompt(chapter, config, max_chars=12000),
        },
    ]
    cloud_profile = LocalProfile(4096, 4096, 12000, 30, 1, 0, 1)
    return _single_completion(
        client,
        model=model,
        messages=messages,
        base_url=effective_url,
        profile=cloud_profile,
        chapter=chapter,
    )


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
