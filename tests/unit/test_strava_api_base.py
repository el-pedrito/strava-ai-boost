"""The Strava API base URL has one source.

Strava's changelog (2026-06-01) moves the V3 API from https://www.strava.com/api/v3
to https://api-v3.strava.com, available from 2027-01-04. The switch must be one
environment value, so no Lambda module may hardcode the base again.
"""

import importlib
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
LAMBDA_DIR = ROOT / "lambda_functions"
HARDCODED = re.compile(r"https://www\.strava\.com/api/v3")


def test_no_lambda_module_hardcodes_the_api_base():
    offenders = []
    for path in LAMBDA_DIR.rglob("*.py"):
        if path.name == "strava_oauth.py" or "__pycache__" in path.parts:
            continue
        if HARDCODED.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_default_base_is_the_current_host(monkeypatch):
    monkeypatch.delenv("STRAVA_API_BASE", raising=False)
    import shared.strava_oauth as mod
    mod = importlib.reload(mod)
    assert mod.STRAVA_API_BASE == "https://www.strava.com/api/v3"


def test_env_overrides_base_and_trailing_slash_is_dropped(monkeypatch):
    monkeypatch.setenv("STRAVA_API_BASE", "https://api-v3.strava.com/")
    import shared.strava_oauth as mod
    mod = importlib.reload(mod)
    try:
        assert mod.STRAVA_API_BASE == "https://api-v3.strava.com"
    finally:
        monkeypatch.delenv("STRAVA_API_BASE", raising=False)
        importlib.reload(mod)


def test_empty_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("STRAVA_API_BASE", "")
    import shared.strava_oauth as mod
    mod = importlib.reload(mod)
    try:
        assert mod.STRAVA_API_BASE == "https://www.strava.com/api/v3"
    finally:
        monkeypatch.delenv("STRAVA_API_BASE", raising=False)
        importlib.reload(mod)
