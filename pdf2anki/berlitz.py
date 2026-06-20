from __future__ import annotations

import re

from pdf2anki.models import CardType, Chapter, Flashcard

_SKIP_LINE = re.compile(
    r"^(TAVOITE|TAV \d|SISÄLLYSLUETTELO|Muistiinpanot|Kuuntele|\d+\.\s+(Esittely|Kysymykset|Dialogi|Extra|Harjoittele))",
    re.I,
)
_DIALOGUE = re.compile(r"^[A-ZÅÄÖa-zåäö]+(?:\s+[A-ZÅÄÖa-zåäö]+)?\s*:\s*(.+)$")
_VOCAB_PAIR = re.compile(r"^([A-Za-zÅÄÖåäö0-9][\w\s\-]{0,35}?)\s+-\s+(.+)$")
_DRILL_NUM = re.compile(r"^([IVX]+)\.\s+(.+)$")
_SECTION = re.compile(r"^[A-ZÅÄÖ][A-ZÅÄÖa-zåäö\s\?]+$")


def _slug(title: str) -> str:
    m = re.search(r"tavoite\s*(\d+)", title, re.I)
    return f"tavoite-{m.group(1)}" if m else re.sub(r"[^\w]+", "-", title.lower()).strip("-")[:40]


def _add(cards: list[Flashcard], seen: set[str], card: Flashcard) -> None:
    key = (card.front.strip().lower(), card.card_type.value)
    if key in seen or len(card.front.strip()) < 2:
        return
    seen.add(key)
    cards.append(card)


def _is_section_header(line: str) -> bool:
    return bool(_SECTION.match(line)) and len(line) < 45 and not line.endswith(".")


def _parse_drill_sections(lines: list[str]) -> list[tuple[str, str]]:
    """Pair Berlitz KYSYMYS/VASTAUS drill blocks (MAA, NIMI, etc.)."""
    start = next((i for i, ln in enumerate(lines) if re.match(r"^2\.\s+Kysymykset", ln, re.I)), None)
    if start is None:
        return []

    block = lines[start + 1 :]
    stop = next(
        (
            i
            for i, ln in enumerate(block)
            if re.match(r"^3\.\s+", ln) or ln.startswith("Hei!") or ln.startswith("Hanna:")
        ),
        len(block),
    )
    block = block[:stop]

    questions: dict[str, dict[str, str]] = {}
    answers: dict[str, dict[str, str]] = {}
    seen_sections: set[str] = set()
    current_section = ""

    for line in block:
        if _is_section_header(line):
            current_section = line.strip()
            if current_section in seen_sections:
                answers.setdefault(current_section, {})
            else:
                seen_sections.add(current_section)
                questions.setdefault(current_section, {})
            continue

        m = _DRILL_NUM.match(line)
        if not m or not current_section:
            continue
        num, text = m.group(1), m.group(2).strip()
        if current_section in answers:
            answers[current_section][num] = text
        else:
            questions[current_section][num] = text

    pairs: list[tuple[str, str]] = []
    for section, qmap in questions.items():
        amap = answers.get(section, {})
        for num, question in qmap.items():
            if not question.endswith("?"):
                continue
            answer = amap.get(num)
            if answer:
                pairs.append((question, answer))
    return pairs


def extract_berlitz_cards(chapter: Chapter) -> list[Flashcard]:
    """Rule-based flashcard extraction for Berlitz Suomi-style chapters."""
    lines = [ln.strip() for ln in chapter.text.splitlines() if ln.strip()]
    slug = _slug(chapter.title)
    base_tags = [f"chapter:{slug}", "berlitz"]
    cards: list[Flashcard] = []
    seen: set[str] = set()

    for question, answer in _parse_drill_sections(lines):
        _add(
            cards,
            seen,
            Flashcard(
                front=question,
                back=answer,
                card_type=CardType.PHRASE,
                chapter=chapter.title,
                tags=base_tags + ["type:phrase", "drill"],
            ),
        )

    i = 0
    while i < len(lines):
        line = lines[i]

        if _SKIP_LINE.match(line) or line.isdigit() or len(line) <= 2:
            i += 1
            continue

        if line.endswith("?") and i + 1 < len(lines) and lines[i + 1].startswith("-"):
            answer_parts = []
            j = i + 1
            while j < len(lines) and lines[j].startswith("-"):
                part = lines[j].lstrip("-").strip()
                if part:
                    answer_parts.append(part)
                j += 1
                if j < len(lines) and not lines[j].startswith("-"):
                    if re.match(r"^\d+\.", lines[j]) or _is_section_header(lines[j]):
                        break
            answer = " ".join(answer_parts).strip()
            if answer and len(answer) < 300:
                _add(
                    cards,
                    seen,
                    Flashcard(
                        front=line,
                        back=answer,
                        card_type=CardType.PHRASE,
                        chapter=chapter.title,
                        tags=base_tags + ["type:phrase"],
                    ),
                )
            i = j
            continue

        dm = _DIALOGUE.match(line)
        if dm and len(dm.group(1)) > 4:
            utterance = dm.group(1).strip()
            if not utterance.lower().startswith("kuuntele"):
                _add(
                    cards,
                    seen,
                    Flashcard(
                        front=utterance,
                        back="(dialogue — recall meaning / respond)",
                        card_type=CardType.SENTENCE,
                        chapter=chapter.title,
                        tags=base_tags + ["type:sentence", "dialogue"],
                    ),
                )

        vm = _VOCAB_PAIR.match(line)
        if vm and not vm.group(1).endswith("?"):
            left, right = vm.group(1).strip(), vm.group(2).strip()
            if left and right and len(left) < 35 and len(right) < 50 and "?" not in left:
                _add(
                    cards,
                    seen,
                    Flashcard(
                        front=left,
                        back=right,
                        card_type=CardType.VOCABULARY,
                        chapter=chapter.title,
                        tags=base_tags + ["type:vocabulary"],
                    ),
                )

        if (line.startswith("“") or line.startswith('"')) and len(line) > 15:
            quote = line.strip("“”\"")
            _add(
                cards,
                seen,
                Flashcard(
                    front=quote,
                    back="(example from lesson — translate / explain)",
                    card_type=CardType.SENTENCE,
                    chapter=chapter.title,
                    tags=base_tags + ["type:sentence", "example"],
                ),
            )

        i += 1

    return cards
