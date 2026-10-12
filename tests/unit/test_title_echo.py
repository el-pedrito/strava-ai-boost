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


def test_preview_mode_writes_nothing(monkeypatch) -> None:
    """preview=True returns the content and never stores, marks Campus, or tracks strength."""
    from processing import content_generator as cg

    calls = []
    monkeypatch.setattr(cg, "retrieve_activity_data_from_dynamodb",
                        lambda _id: {"activity_data": {"sport_type": "WeightTraining"}})
    monkeypatch.setattr(cg, "get_user_configuration", lambda _u: {})
    monkeypatch.setattr(cg, "get_active_modules", lambda _c: [])
    monkeypatch.setattr(cg, "build_user_profile_from_config", lambda _c: None)
    monkeypatch.setattr(cg, "extract_enduraw_report", lambda _a: None)
    monkeypatch.setattr(cg, "apply_module_processing",
                        lambda *a, **k: [{"name": "campus_coach", "matched_session": {"title": "x"}}])
    monkeypatch.setattr(cg, "generate_enhanced_content", lambda *a, **k: {"title": "T", "description": "D"})
    monkeypatch.setattr(cg, "apply_content_guard", lambda content, *a, **k: (content, [], []))
    monkeypatch.setattr(cg, "store_generated_content", lambda *a: calls.append("store"))
    monkeypatch.setattr(cg, "mark_campus_session_done", lambda *a: calls.append("campus"))
    monkeypatch.setattr(cg, "_track_strength_history", lambda *a: calls.append("strength"))

    result = cg.handler({"activity_id": "1", "user_id": "u", "preview": True}, None)
    assert result["preview"] is True and result["enhanced_content"]["title"] == "T"
    assert calls == []
