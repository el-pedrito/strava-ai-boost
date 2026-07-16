"""Unit tests for the prompt regression evaluators (free, no AWS)."""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from tests.regression.evaluators import (
    BANNED_CLICHES,
    check_banned_cliches,
    check_emoji_policy,
    check_forbidden_dashes,
    check_language,
    check_length,
    check_parsed_ok,
    check_spaced_hyphen,
    check_title_not_generic,
    evaluate_output,
    normalize,
)

FIXTURES_DIR = REPO_ROOT / "tests" / "regression" / "fixtures"


class TestBannedCliches:
    def test_clean_text_passes(self):
        assert check_banned_cliches("Footing tranquille, jambes lourdes au départ.")["passed"]

    def test_cliche_detected(self):
        r = check_banned_cliches("La machine est lancée, les kilomètres défilent.")
        assert not r["passed"]
        assert "la machine" in r["detail"]

    def test_accent_and_case_insensitive(self):
        r = check_banned_cliches("LE CORPS SE REVEILLE doucement ce matin")
        assert not r["passed"]

    def test_curly_apostrophe(self):
        r = check_banned_cliches("les jambes se sont lib\u00e9r\u00e9es aujourd\u2019hui")
        assert not r["passed"]


class TestClichesSyncWithPrompt:
    """Each BANNED_CLICHES entry must appear in the prompt source text.

    If a cliché is removed/reworded in embedded_prompts.py, this test fails and
    forces updating the constant (and vice versa). The prompt is the source of
    truth — never rebuild it from the constant.
    """

    def test_every_cliche_is_in_prompt(self):
        prompt_text = normalize(
            (REPO_ROOT / "src" / "agents" / "embedded_prompts.py").read_text(encoding="utf-8")
        )
        missing = [c for c in BANNED_CLICHES if normalize(c) not in prompt_text]
        assert not missing, f"BANNED_CLICHES out of sync with embedded_prompts.py: {missing}"


class TestDashesAndHyphens:
    def test_em_dash_flagged(self):
        assert not check_forbidden_dashes("FC \u00e0 155 \u2014 j'\u00e9tais bien")["passed"]

    def test_en_dash_flagged(self):
        assert not check_forbidden_dashes("10 \u2013 12 km")["passed"]

    def test_clean_passes(self):
        assert check_forbidden_dashes("FC \u00e0 155, j'\u00e9tais bien")["passed"]

    def test_spaced_hyphen_flagged(self):
        assert not check_spaced_hyphen("Bonne s\u00e9ance - un peu dur au d\u00e9but")["passed"]

    def test_bullet_list_allowed(self):
        assert check_spaced_hyphen("Bilan :\n - 5km\n - 25min")["passed"]


class TestLengthAndEmoji:
    def test_length_ok(self):
        assert check_length("x" * 100, 200)["passed"]

    def test_length_exceeded(self):
        assert not check_length("x" * 300, 200)["passed"]

    def test_emoji_none_policy(self):
        assert not check_emoji_policy("Bien couru \U0001F3C3", "none")["passed"]
        assert check_emoji_policy("Bien couru", "none")["passed"]

    def test_emoji_minimal_policy(self):
        assert check_emoji_policy("Top \U0001F4AA\U0001F525", "minimal")["passed"]
        assert not check_emoji_policy("\U0001F4AA\U0001F525\U0001F680", "minimal")["passed"]


class TestParsedAndTitle:
    def test_parsed_ok(self):
        assert check_parsed_ok("Titre", "Description")["passed"]

    def test_missing_title_fails(self):
        assert not check_parsed_ok("", "Description")["passed"]
        assert not check_parsed_ok(None, "Description")["passed"]

    def test_generic_title_flagged(self):
        assert not check_title_not_generic("Morning Run")["passed"]
        assert not check_title_not_generic("course \u00e0 pied")["passed"]

    def test_specific_title_passes(self):
        assert check_title_not_generic("8 bornes avant le caf\u00e9, mode diesel")["passed"]


class TestLanguage:
    def test_french_text_passes(self):
        text = "Une sortie tranquille dans le froid, avec les jambes un peu lourdes mais du plaisir."
        assert check_language(text, "fr")["passed"]

    def test_english_text_fails_fr_check(self):
        text = "This was a great run with the crew and it was not that hard for me."
        assert not check_language(text, "fr")["passed"]

    def test_other_language_skipped(self):
        assert check_language("whatever", "en")["passed"]


class TestEvaluateOutput:
    def test_unparseable_short_circuits(self):
        results = evaluate_output(None, None, {})
        assert len(results) == 1
        assert results[0]["criterion"] == "json_parseable"
        assert not results[0]["passed"]

    def test_full_run_all_criteria(self):
        results = evaluate_output(
            "8 bornes tranquilles",
            "Footing cool du matin, rien \u00e0 signaler. Les jambes r\u00e9pondaient bien apr\u00e8s la muscu d'hier.",
            {"language": "fr", "max_chars": 1200, "emoji_policy": "minimal"},
        )
        by_id = {r["criterion"]: r for r in results}
        assert len(results) == 8
        assert all(r["passed"] for r in results), [r for r in results if not r["passed"]]
        assert by_id["no_banned_cliche"]["severity"] == "fail"
        assert by_id["no_forbidden_dashes"]["severity"] == "warn"


class TestFixtures:
    """Smoke tests: fixtures are valid and complete (no LLM)."""

    def test_fixtures_exist(self):
        fixtures = sorted(FIXTURES_DIR.glob("*.json"))
        assert len(fixtures) >= 6

    @pytest.mark.parametrize("path", sorted(FIXTURES_DIR.glob("*.json")), ids=lambda p: p.stem)
    def test_fixture_shape(self, path):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["name"] == path.stem
        assert {"language", "max_chars", "emoji_policy"} <= set(data["eval"].keys())
        agent_input = data["agent_input"]
        assert agent_input["action"] == "generate_content"
        assert agent_input["user_id"] == "regression_eval", "fixtures must use the dedicated eval user"
        activity = agent_input["activity_data"]
        assert activity["id"] >= 90000000000, "fixtures must use synthetic activity ids"
        assert "start_date_local" in activity
