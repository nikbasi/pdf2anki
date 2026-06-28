from pdf2anki.tags import (
    card_tags,
    chapter_deck_name,
    chapter_filename_slug,
    chapter_label,
    chapter_tag,
    parse_chapter_title,
)


def test_parse_berlitz_chapter() -> None:
    info = parse_chapter_title('TAVOITE  2: Esittäytyminen - ”Puhutko suomea?”')
    assert info
    assert info.number == 2
    assert info.short_title == "Esittäytyminen: Puhutko suomea"
    assert info.label == "02 — Esittäytyminen: Puhutko suomea"
    assert info.tag == info.label.replace(" ", "\u202f")
    assert chapter_tag('TAVOITE  2: Esittäytyminen - ”Puhutko suomea?”') == info.tag


def test_parse_chapter_one() -> None:
    info = parse_chapter_title('TAVOITE 1: Esittäytyminen - ”Hauska tavata! -Samoin!”')
    assert info
    assert info.short_title == "Esittäytyminen: Hauska tavata"
    assert info.tag == "01\u202f—\u202fEsittäytyminen:\u202fHauska\u202ftavata"


def test_parse_kertaus() -> None:
    info = parse_chapter_title("TAVOITE 10: Kertaus")
    assert info
    assert info.label == "10 — Kertaus"
    assert info.tag == "10\u202f—\u202fKertaus"


def test_parse_simple_topic() -> None:
    info = parse_chapter_title('TAVOITE 9: Kello - ”Paljonko kello on?”')
    assert info
    assert info.short_title == "Kello"
    assert chapter_tag('TAVOITE 9: Kello - ”Paljonko kello on?”') == "09\u202f—\u202fKello"


def test_card_tags_match_label() -> None:
    title = "TAVOITE 3: Esittely ja kuulumiset - ”Tässä on minun kollega Saara!”"
    label = "03 — Esittely ja kuulumiset"
    assert chapter_label(title) == label
    assert card_tags(title, "vocabulary") == [label.replace(" ", "\u202f"), "type:vocabulary"]


def test_chapter_label_pads_existing() -> None:
    assert chapter_label("1 — Esittäytyminen: Hauska tavata") == "01 — Esittäytyminen: Hauska tavata"
    assert chapter_label("10 — Kertaus") == "10 — Kertaus"


def test_chapter_filename_slug_from_tavoite() -> None:
    slug = chapter_filename_slug('TAVOITE 2: Esittäytyminen - ”Puhutko suomea?”')
    assert slug == "02-esittaytyminen-puhutko-suomea"


def test_chapter_filename_slug_from_label() -> None:
    slug = chapter_filename_slug("2 — Esittäytyminen")
    assert slug == "02-esittaytyminen"


def test_chapter_deck_name() -> None:
    name = chapter_deck_name("Berlitz Suomi 1", 'TAVOITE 2: Esittäytyminen - ”Puhutko suomea?”')
    assert name == "Berlitz Suomi 1 :: 02 — Esittäytyminen: Puhutko suomea"
    assert (
        chapter_deck_name("Berlitz Suomi 1", "1 — Esittäytyminen: Hauska tavata")
        == "Berlitz Suomi 1 :: 01 — Esittäytyminen: Hauska tavata"
    )
