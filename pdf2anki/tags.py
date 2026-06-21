from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_TAVOITE = re.compile(r"^TAVOITE\s*(\d+)\s*:\s*(.+)$", re.I | re.DOTALL)


_NBSP = "\u202f"  # narrow no-break space — looks like a space but is valid in Anki tags


@dataclass(frozen=True)
class ChapterInfo:
    number: int
    short_title: str

    @property
    def label(self) -> str:
        return f"{self.number} — {self.short_title}"

    @property
    def tag(self) -> str:
        """Same as label visually; uses no-break spaces for Anki tag compatibility."""
        return self.label.replace(" ", _NBSP)


def _slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[\s_]+", "-", text.strip())
    return re.sub(r"-+", "-", text).strip("-")[:35]


def parse_chapter_title(chapter_title: str) -> ChapterInfo | None:
    """Parse Berlitz-style 'TAVOITE N: Topic - \"Quote\"' headings."""
    match = _TAVOITE.match(chapter_title.strip())
    if not match:
        return None

    number = int(match.group(1))
    rest = match.group(2).strip()

    if re.match(r"^kertaus$", rest, re.I):
        return ChapterInfo(number, "Kertaus")

    parts = re.split(r"\s+-\s+", rest, maxsplit=1)
    topic = parts[0].strip().strip("“”\"'")
    quote = parts[1].strip().strip("“”\"'") if len(parts) > 1 else ""

    if quote:
        quote = quote.strip("“”\"'")
        quote = re.split(r"\s+-\s*", quote, maxsplit=1)[0].strip("?!. ")
        if len(quote) > 50:
            quote = quote[:47].rsplit(" ", 1)[0] + "…"

    # Prefer the topic; append quote when it adds context (long topics or duplicates).
    if quote and (len(topic) > 28 or topic.lower() == "esittäytyminen"):
        short = f"{topic}: {quote}"
    else:
        short = topic or quote or f"Lesson {number}"

    return ChapterInfo(number, short)


def chapter_label(chapter_title: str) -> str:
    info = parse_chapter_title(chapter_title)
    if info:
        return info.label
    return chapter_title.strip()


def chapter_tag(chapter_title: str) -> str:
    info = parse_chapter_title(chapter_title)
    if info:
        return info.tag
    return chapter_title.strip().replace(" ", _NBSP)


def card_tags(chapter_title: str, card_type: str) -> list[str]:
    return [chapter_tag(chapter_title), f"type:{card_type}"]
