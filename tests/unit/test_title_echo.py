"""The description must not open by restating the title (shown just above it on Strava)."""

from processing.content_generator import _strip_title_echo


def test_strips_real_echo_from_2026_10_09() -> None:
    title = "Footing EF du vendredi, 6,66 km en zone 2"
    desc = "Footing EF du vendredi, 6,66 km en 40:10.\n\n📋 Séance Campus Coach: Endurance Fondamentale."
    assert _strip_title_echo(title, desc) == "📋 Séance Campus Coach: Endurance Fondamentale."


def test_keeps_athlete_opening_that_differs_from_title() -> None:
    title = "3x10min @4:35 avec pré-fatigue en début de séance"
    desc = "Allures semi avec pré-fatigue au programme, et elles passent bien ! Bonnes jambes."
    assert _strip_title_echo(title, desc) == desc


def test_shared_first_word_is_not_an_echo() -> None:
    title = "Footing EF du vendredi"
    desc = "Footing tranquille sous la pluie. Rien à signaler."
    assert _strip_title_echo(title, desc) == desc


def test_never_empties_the_description() -> None:
    title = "Footing EF du vendredi"
    desc = "Footing EF du vendredi."
    assert _strip_title_echo(title, desc) == desc


def test_empty_inputs() -> None:
    assert _strip_title_echo("", "Texte.") == "Texte."
    assert _strip_title_echo("Titre", "") == ""
