from pdf2anki.filters import is_picture_dependent
from pdf2anki.models import CardType, Flashcard


def test_filters_picture_cards() -> None:
    assert is_picture_dependent(
        Flashcard(front="Kuka on kuvassa?", back="Who is in the picture?")
    )
    assert is_picture_dependent(
        Flashcard(front="Onko tämä Englanti?", back="Is this England?")
    )
    assert is_picture_dependent(
        Flashcard(front="Katso tuota jakkua.", back="Look at that jacket.")
    )
    assert not is_picture_dependent(
        Flashcard(front="Mistä sinä olet kotoisin?", back="Where are you from?")
    )
    assert not is_picture_dependent(
        Flashcard(front="puhua", back="to speak<br>minä puhun, sinä puhut")
    )
    assert not is_picture_dependent(
        Flashcard(
            front="tämä",
            back="this (demonstrative)",
            card_type=CardType.VOCABULARY,
        )
    )
