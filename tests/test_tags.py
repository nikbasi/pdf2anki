from pdf2anki.tags import chapter_label, chapter_tag, card_tags, parse_chapter_title


def test_parse_berlitz_chapter() -> None:
    info = parse_chapter_title('TAVOITE  2: Esittäytyminen - ”Puhutko suomea?”')
    assert info
    assert info.number == 2
    assert info.short_title == "Esittäytyminen: Puhutko suomea"
    assert info.label == "2 — Esittäytyminen: Puhutko suomea"
    assert info.tag == info.label.replace(" ", "\u202f")
    assert chapter_tag('TAVOITE  2: Esittäytyminen - ”Puhutko suomea?”') == info.tag


def test_parse_chapter_one() -> None:
    info = parse_chapter_title('TAVOITE 1: Esittäytyminen - ”Hauska tavata! -Samoin!”')
    assert info
    assert info.short_title == "Esittäytyminen: Hauska tavata"
    assert info.tag == "1\u202f—\u202fEsittäytyminen:\u202fHauska\u202ftavata"


def test_parse_kertaus() -> None:
    info = parse_chapter_title("TAVOITE 10: Kertaus")
    assert info
    assert info.label == "10 — Kertaus"
    assert info.tag == "10\u202f—\u202fKertaus"


def test_parse_simple_topic() -> None:
    info = parse_chapter_title('TAVOITE 9: Kello - ”Paljonko kello on?”')
    assert info
    assert info.short_title == "Kello"
    assert chapter_tag('TAVOITE 9: Kello - ”Paljonko kello on?”') == "9\u202f—\u202fKello"


def test_card_tags_match_label() -> None:
    title = "TAVOITE 3: Esittely ja kuulumiset - ”Tässä on minun kollega Saara!”"
    label = "3 — Esittely ja kuulumiset"
    assert chapter_label(title) == label
    assert card_tags(title, "vocabulary") == [label.replace(" ", "\u202f"), "type:vocabulary"]
