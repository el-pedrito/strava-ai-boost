"""Unit tests for build_converse_messages — Bedrock Converse history normalization.

Covers the Converse/Claude contract enforced by the helper: first message must be
``user``, roles strictly alternate, current question is always the trailing user
message, with role whitelisting, asymmetric truncation, a 10-entry history cap, and
graceful single-turn degradation on invalid input.
"""

import os
import sys

import pytest  # noqa: F401  (kept consistent with sibling test modules)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

from shared.coach_context import build_converse_messages  # noqa: E402


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _roles(messages: list) -> list:
    return [m["role"] for m in messages]


def _text(message: dict) -> str:
    return message["content"][0]["text"]


def _assert_valid_shape(messages: list) -> None:
    """Every message must be {'role': 'user'|'assistant', 'content': [{'text': str}]}."""
    assert isinstance(messages, list) and messages
    for m in messages:
        assert set(m.keys()) == {"role", "content"}
        assert m["role"] in ("user", "assistant")
        assert isinstance(m["content"], list) and len(m["content"]) == 1
        assert set(m["content"][0].keys()) == {"text"}
        assert isinstance(m["content"][0]["text"], str)


def _assert_strict_alternation(messages: list) -> None:
    """First message is user and roles strictly alternate (Converse/Claude contract)."""
    assert messages[0]["role"] == "user"
    for prev, curr in zip(messages, messages[1:]):
        assert prev["role"] != curr["role"], f"non-alternating roles: {_roles(messages)}"


# --------------------------------------------------------------------------- #
# 1. Empty / null / non-list history -> single-turn
# --------------------------------------------------------------------------- #
def test_empty_history_returns_single_turn():
    result = build_converse_messages([], "Comment je progresse ?")
    assert result == [{"role": "user", "content": [{"text": "Comment je progresse ?"}]}]


def test_none_history_returns_single_turn():
    result = build_converse_messages(None, "Ma prochaine séance ?")
    assert result == [{"role": "user", "content": [{"text": "Ma prochaine séance ?"}]}]


def test_non_list_history_returns_single_turn():
    result = build_converse_messages("not-a-list", "Question")
    assert result == [{"role": "user", "content": [{"text": "Question"}]}]


def test_history_of_only_invalid_entries_returns_single_turn():
    history = [
        "string-entry",
        123,
        {"role": "user"},  # missing content
        {"content": "no role"},  # missing role
        {"role": "user", "content": 42},  # non-string content
        {"role": "user", "content": "   "},  # empty after strip
        {"role": 5, "content": "bad role type"},  # non-string role
    ]
    result = build_converse_messages(history, "Q")
    assert result == [{"role": "user", "content": [{"text": "Q"}]}]


# --------------------------------------------------------------------------- #
# 2. Invalid role 'system' is ignored
# --------------------------------------------------------------------------- #
def test_system_role_is_dropped():
    history = [
        {"role": "system", "content": "You are a coach"},
        {"role": "user", "content": "Salut"},
        {"role": "assistant", "content": "Bonjour"},
    ]
    result = build_converse_messages(history, "Question finale")
    # The system entry must not leak into any message.
    assert all("You are a coach" not in _text(m) for m in result)
    _assert_strict_alternation(result)
    _assert_valid_shape(result)


# --------------------------------------------------------------------------- #
# 3. Leading assistant message(s) dropped
# --------------------------------------------------------------------------- #
def test_leading_assistant_is_dropped():
    history = [
        {"role": "assistant", "content": "Message d'ouverture du coach"},
        {"role": "user", "content": "Ma vraie première question"},
        {"role": "assistant", "content": "Réponse"},
    ]
    result = build_converse_messages(history, "Question courante")
    assert result[0]["role"] == "user"
    assert "Message d'ouverture du coach" not in _text(result[0])
    assert "Ma vraie première question" in _text(result[0])
    _assert_strict_alternation(result)


def test_multiple_leading_assistants_all_dropped():
    history = [
        {"role": "assistant", "content": "A1"},
        {"role": "assistant", "content": "A2"},
        {"role": "user", "content": "U1"},
    ]
    result = build_converse_messages(history, "Q")
    assert result[0]["role"] == "user"
    assert "A1" not in _text(result[0]) and "A2" not in _text(result[0])
    assert "U1" in _text(result[0])


# --------------------------------------------------------------------------- #
# 4. Consecutive same-role messages are merged
# --------------------------------------------------------------------------- #
def test_consecutive_user_messages_merged():
    history = [
        {"role": "user", "content": "Première partie"},
        {"role": "user", "content": "Deuxième partie"},
        {"role": "assistant", "content": "Réponse"},
    ]
    result = build_converse_messages(history, "Question")
    # First two users collapse into one message joined by a newline.
    assert result[0]["role"] == "user"
    assert _text(result[0]) == "Première partie\nDeuxième partie"
    _assert_strict_alternation(result)


def test_consecutive_assistant_messages_merged():
    history = [
        {"role": "user", "content": "U"},
        {"role": "assistant", "content": "A-part1"},
        {"role": "assistant", "content": "A-part2"},
    ]
    result = build_converse_messages(history, "Q")
    assistant_msgs = [m for m in result if m["role"] == "assistant"]
    assert len(assistant_msgs) == 1
    assert _text(assistant_msgs[0]) == "A-part1\nA-part2"
    _assert_strict_alternation(result)


# --------------------------------------------------------------------------- #
# 5. Asymmetric truncation: user 500, assistant 2500
# --------------------------------------------------------------------------- #
def test_user_content_truncated_to_500():
    long_user = "u" * 800
    history = [
        {"role": "user", "content": long_user},
        {"role": "assistant", "content": "short"},
    ]
    result = build_converse_messages(history, "Q")
    assert _text(result[0]) == "u" * 500


def test_assistant_content_truncated_to_2500():
    long_assistant = "a" * 4000
    history = [
        {"role": "user", "content": "U"},
        {"role": "assistant", "content": long_assistant},
    ]
    result = build_converse_messages(history, "Q")
    assistant_msgs = [m for m in result if m["role"] == "assistant"]
    assert _text(assistant_msgs[0]) == "a" * 2500


# --------------------------------------------------------------------------- #
# 6. History capped at 10 most-recent entries
# --------------------------------------------------------------------------- #
def test_history_capped_at_10_entries():
    # 14 strictly alternating entries starting with user ([m0], [a1], [m2], ... [a13]).
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"[m{i}]"}
        for i in range(14)
    ]
    result = build_converse_messages(history, "current-question")
    joined = " ".join(_text(m) for m in result)
    # Only the last 10 entries ([m4]..[m13]) survive; [m0]..[m3] are dropped.
    for i in range(4):
        assert f"[m{i}]" not in joined, f"[m{i}] should have been dropped by the 10-entry cap"
    for i in range(4, 14):
        assert f"[m{i}]" in joined
    # 10 kept history entries (already alternating) + trailing user question.
    assert len(result) == 11
    _assert_strict_alternation(result)


# --------------------------------------------------------------------------- #
# 7. Final ordering: first=user, strict alternation (fuzz-ish scenarios)
# --------------------------------------------------------------------------- #
def test_final_alternation_and_first_user_various_shapes():
    scenarios = [
        [{"role": "assistant", "content": "A"}, {"role": "assistant", "content": "B"}],
        [{"role": "user", "content": "U1"}, {"role": "user", "content": "U2"}],
        [
            {"role": "assistant", "content": "lead"},
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": "a"},
            {"role": "assistant", "content": "a2"},
            {"role": "system", "content": "ignored"},
            {"role": "user", "content": "u2"},
        ],
    ]
    for history in scenarios:
        result = build_converse_messages(history, "final-q")
        _assert_valid_shape(result)
        _assert_strict_alternation(result)


# --------------------------------------------------------------------------- #
# 8. current_question is always the last user message
# --------------------------------------------------------------------------- #
def test_current_question_is_last_message_when_history_ends_with_assistant():
    history = [
        {"role": "user", "content": "U"},
        {"role": "assistant", "content": "A"},
    ]
    result = build_converse_messages(history, "QUESTION-FINALE")
    assert result[-1]["role"] == "user"
    assert _text(result[-1]) == "QUESTION-FINALE"


def test_current_question_merged_into_trailing_user():
    history = [
        {"role": "user", "content": "U"},
        {"role": "assistant", "content": "A"},
        {"role": "user", "content": "dernier-user"},
    ]
    result = build_converse_messages(history, "QUESTION-FINALE")
    assert result[-1]["role"] == "user"
    # Merged: previous trailing user + newline + current question.
    assert _text(result[-1]) == "dernier-user\nQUESTION-FINALE"
    _assert_strict_alternation(result)


def test_current_question_present_even_when_history_all_invalid():
    result = build_converse_messages([{"role": "system", "content": "x"}], "seule-question")
    assert result[-1]["role"] == "user"
    assert _text(result[-1]) == "seule-question"


# --------------------------------------------------------------------------- #
# 9. Output format contract
# --------------------------------------------------------------------------- #
def test_output_format_shape():
    history = [
        {"role": "user", "content": "Bonjour"},
        {"role": "assistant", "content": "Salut"},
    ]
    result = build_converse_messages(history, "Ça va ?")
    _assert_valid_shape(result)
    assert result == [
        {"role": "user", "content": [{"text": "Bonjour"}]},
        {"role": "assistant", "content": [{"text": "Salut"}]},
        {"role": "user", "content": [{"text": "Ça va ?"}]},
    ]


def test_role_case_insensitive_normalization():
    history = [
        {"role": "USER", "content": "maj"},
        {"role": "Assistant", "content": "mixte"},
    ]
    result = build_converse_messages(history, "q")
    assert _roles(result) == ["user", "assistant", "user"]
