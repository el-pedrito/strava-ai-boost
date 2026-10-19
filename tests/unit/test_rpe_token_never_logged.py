"""RPE athlete input: the task token never reaches a log ("Jeton et stream DynamoDB").

The activities table stream (NEW_AND_OLD_IMAGES) carries input_task_token while
the window is open. Its only consumer, voice_debrief_generator, must never log a
whole event, record or image; InputWait must never log its event (it carries the
token). Static AST check on the logging calls.
"""

from __future__ import annotations

import ast
import os

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions")
FORBIDDEN_NAMES = {"event", "record", "records", "new_image", "old_image", "task_token"}
FORBIDDEN_KEYS = {"NewImage", "OldImage", "dynamodb", "task_token", "input_task_token"}
LOG_METHODS = {"debug", "info", "warning", "error", "exception", "critical"}


def _log_calls(path):
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in LOG_METHODS
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "logger"):
            yield node


def _offending(call):
    for sub in ast.walk(call):
        if isinstance(sub, ast.Name) and sub.id in FORBIDDEN_NAMES:
            # len(records) is a count, not the content.
            return sub.id
        if isinstance(sub, ast.Constant) and sub.value in FORBIDDEN_KEYS:
            return sub.value
    return None


def _counted_names(call):
    """Names only used inside len(...) are counts, allowed."""
    allowed = set()
    for sub in ast.walk(call):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id == "len":
            for arg in sub.args:
                if isinstance(arg, ast.Name):
                    allowed.add(id(arg))
    return allowed


def _violations(relative):
    path = os.path.join(ROOT, relative)
    found = []
    for call in _log_calls(path):
        counted = _counted_names(call)
        for sub in ast.walk(call):
            if isinstance(sub, ast.Name) and sub.id in FORBIDDEN_NAMES and id(sub) not in counted:
                found.append((call.lineno, sub.id))
            if isinstance(sub, ast.Constant) and sub.value in FORBIDDEN_KEYS:
                found.append((call.lineno, sub.value))
    return found


def test_stream_consumer_never_logs_images():
    assert _violations("processing/voice_debrief_generator.py") == []


def test_input_wait_never_logs_event_or_token():
    assert _violations("athlete_input/input_wait.py") == []


def test_input_wait_has_no_log_event_decorator():
    with open(os.path.join(ROOT, "athlete_input", "input_wait.py"), encoding="utf-8") as handle:
        assert "log_event" not in handle.read().replace("No log_event", "")


def test_fetcher_and_error_handler_never_log_the_token():
    assert [v for v in _violations("processing/activity_fetcher.py") if v[1] in {"task_token", "input_task_token"}] == []
    assert [v for v in _violations("support/stepfunctions_error_handler.py")
            if v[1] in {"task_token", "input_task_token"}] == []
