from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import fitz

from pdf2anki.models import BookConfig, Chapter


@dataclass
class TextBlock:
    text: str
    page: int
    size: float
    is_bold: bool


def _block_info(block: dict, page_num: int) -> TextBlock | None:
    text = block.get("text", "").strip()
    if not text:
        return None
    spans = block.get("lines", [{}])[0].get("spans", [])
    if not spans:
        return TextBlock(text=text, page=page_num, size=12.0, is_bold=False)
    span = spans[0]
    flags = span.get("flags", 0)
    return TextBlock(
        text=text,
        page=page_num,
        size=round(span.get("size", 12.0), 1),
        is_bold=bool(flags & 2**4),
    )


def extract_blocks(pdf_path: str | Path) -> list[TextBlock]:
    path = Path(pdf_path)
    blocks: list[TextBlock] = []
    with fitz.open(path) as doc:
        for page_num, page in enumerate(doc, start=1):
            data = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
            for block in data.get("blocks", []):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    line_text = "".join(span.get("text", "") for span in line.get("spans", []))
                    line_text = line_text.strip()
                    if not line_text:
                        continue
                    spans = line.get("spans", [])
                    if spans:
                        span = spans[0]
                        flags = span.get("flags", 0)
                        blocks.append(
                            TextBlock(
                                text=line_text,
                                page=page_num,
                                size=round(span.get("size", 12.0), 1),
                                is_bold=bool(flags & 2**4),
                            )
                        )
    return blocks


def _body_font_size(blocks: list[TextBlock]) -> float:
    sizes = [b.size for b in blocks if len(b.text) > 20]
    if not sizes:
        sizes = [b.size for b in blocks]
    if not sizes:
        return 12.0
    return Counter(sizes).most_common(1)[0][0]


def _is_heading(block: TextBlock, body_size: float, patterns: list[str]) -> bool:
    if len(block.text) > 120:
        return False
    for pattern in patterns:
        if re.match(pattern, block.text, re.IGNORECASE):
            return True
    if block.size >= body_size + 1.5 and (block.is_bold or block.size >= body_size + 3):
        return True
    return False


def _blocks_to_text(blocks: list[TextBlock]) -> str:
    paragraphs: list[str] = []
    current: list[str] = []
    for block in blocks:
        if block.text.endswith("-") and not block.text.endswith("--"):
            current.append(block.text[:-1])
            continue
        current.append(block.text)
        if block.text.endswith((".", "!", "?", "…", ".")):
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return "\n\n".join(paragraphs)


def split_by_headings(blocks: list[TextBlock], config: BookConfig) -> list[Chapter]:
    body_size = _body_font_size(blocks)
    headings: list[tuple[int, str, int]] = []
    for i, block in enumerate(blocks):
        if _is_heading(block, body_size, config.chapter_patterns):
            headings.append((i, block.text.strip(), block.page))

    if not headings:
        full_text = _blocks_to_text(blocks)
        last_page = blocks[-1].page if blocks else 1
        return [Chapter(title="Full book", page_start=1, page_end=last_page, text=full_text)]

    chapters: list[Chapter] = []
    for idx, (start_i, title, page) in enumerate(headings):
        end_i = headings[idx + 1][0] if idx + 1 < len(headings) else len(blocks)
        chapter_blocks = blocks[start_i:end_i]
        page_end = chapter_blocks[-1].page if chapter_blocks else page
        chapters.append(
            Chapter(
                title=title,
                page_start=page,
                page_end=page_end,
                text=_blocks_to_text(chapter_blocks),
            )
        )
    return chapters


def split_by_manual_ranges(pdf_path: str | Path, ranges: list[dict]) -> list[Chapter]:
    path = Path(pdf_path)
    chapters: list[Chapter] = []
    with fitz.open(path) as doc:
        for spec in ranges:
            start = int(spec["page_start"]) - 1
            end = int(spec["page_end"])
            title = spec.get("title", f"Pages {start + 1}-{end}")
            pages_text: list[str] = []
            for page_num in range(start, min(end, len(doc))):
                pages_text.append(doc[page_num].get_text())
            chapters.append(
                Chapter(
                    title=title,
                    page_start=start + 1,
                    page_end=min(end, len(doc)),
                    text="\n".join(pages_text).strip(),
                )
            )
    return chapters


def split_by_page_markers(
    pdf_path: str | Path,
    marker_pattern: str,
) -> list[Chapter]:
    """Split PDF at page lines matching a regex (e.g. Berlitz TAVOITE headings)."""
    path = Path(pdf_path)
    pattern = re.compile(marker_pattern, re.IGNORECASE | re.MULTILINE)
    markers: list[tuple[int, str, int]] = []  # (lesson_num or order, title, page)

    with fitz.open(path) as doc:
        for page_num, page in enumerate(doc, start=1):
            text = page.get_text()
            for line in text.splitlines():
                line = line.strip()
                m = pattern.search(line)
                if not m:
                    continue
                title = line.strip()
                num = int(m.group(1)) if m.lastindex and m.group(1).isdigit() else len(markers)
                if any(existing_num == num for existing_num, _, _ in markers):
                    continue
                markers.append((num, title.strip(), page_num))
                break

        if not markers:
            return []

        markers.sort(key=lambda item: item[2])
        chapters: list[Chapter] = []
        for idx, (num, title, page_start) in enumerate(markers):
            page_end = markers[idx + 1][2] - 1 if idx + 1 < len(markers) else len(doc)
            pages_text = [doc[p - 1].get_text() for p in range(page_start, page_end + 1)]
            chapters.append(
                Chapter(
                    title=title,
                    page_start=page_start,
                    page_end=page_end,
                    text="\n".join(pages_text).strip(),
                )
            )
    return chapters


def extract_chapters(pdf_path: str | Path, config: BookConfig) -> list[Chapter]:
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    if config.chapters:
        return split_by_manual_ranges(path, config.chapters)

    if config.chapter_marker_pattern:
        chapters = split_by_page_markers(path, config.chapter_marker_pattern)
        return [c for c in chapters if len(c.text.strip()) > 50]

    blocks = extract_blocks(path)
    chapters = split_by_headings(blocks, config)
    return [c for c in chapters if len(c.text.strip()) > 50]
