"""Unit tests for the coach_chat agent TOOL LOGIC (chantier A1+A2b).

Scope: the *data-access logic* behind the four pure Strands tools of
``src/agents/coach_chat_agent.py`` — i.e. the ``_*_impl`` helpers and the
serialization/formatting utilities. We do NOT exercise the AG-UI/FastAPI HTTP
layer nor Bedrock (network); those are integration concerns validated at deploy.

Import strategy
---------------
The agent module imports ``ag_ui``, ``ag_ui_strands`` and ``fastapi`` at module
level. These are deploy-time dependencies pinned in
``coach_chat_requirements.txt`` and are NOT part of the test venv. We therefore
stub the *missing* ones in ``sys.modules`` before importing the module, so the
tool logic can be tested in isolation without the heavy runtime stack. ``strands``
is used as-is when present (the real ``@tool`` decorator). DynamoDB is mocked at
the module's ``dynamodb`` resource attribute (same pattern as tests/unit/).
"""

import importlib.util
import json
import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "coach_chat"))


def _stub_package(top: str, submodules: tuple = ()) -> None:
    """Stub ``top`` and its submodules in ``sys.modules`` if ``top`` is absent.

    Only the top-level package is probed with ``find_spec`` (probing a dotted
    child would trigger import of the — now stubbed — parent). Each stub carries a
    ``__path__`` so the import machinery treats it as a package.
    """
    if importlib.util.find_spec(top) is not None:
        return  # real dependency present — use it as-is
    for name in (top, *submodules):
        if name not in sys.modules:
            mod = MagicMock(name=name)
            mod.__path__ = []  # mark as a package for ``from x.y import z``
            sys.modules[name] = mod


# Heavy deploy-only deps (pinned in coach_chat_requirements.txt, not in the test
# venv): stub whatever is missing so importing coach_chat_agent succeeds and we
# can reach the pure tool logic. ``strands`` is used as-is when installed.
_stub_package("ag_ui", ("ag_ui.core", "ag_ui.encoder"))
_stub_package("ag_ui_strands")
_stub_package("fastapi", ("fastapi.responses",))

import coach_chat_agent as cca  # noqa: E402


# --------------------------------------------------------------------------- #
# Fake DynamoDB plumbing
# --------------------------------------------------------------------------- #
class _FakeTable:
    """Minimal DynamoDB Table double.

    ``query``/``get_item``/``scan`` either return a canned response or raise a
    caller-provided exception (to simulate DynamoDB failures). ``query`` records
    the kwargs it was called with so tests can assert on the range expression.
    """

    def __init__(self, *, query_resp=None, item=None, scan_items=None, error=None,
                 query_pages=None, scan_pages=None):
        self._query_resp = query_resp or {"Items": []}
        self._item = item
        self._scan_items = scan_items or []
        self._error = error
        # Multi-page mode: list of {"Items": [...]} pages; LastEvaluatedKey is
        # injected automatically between pages to exercise pagination loops.
        self._query_pages = list(query_pages) if query_pages else None
        self._scan_pages = list(scan_pages) if scan_pages else None
        self.query_calls = []
        self.scan_calls = []

    @staticmethod
    def _next_page(pages: list, calls: list) -> dict:
        idx = len(calls) - 1
        page = dict(pages[min(idx, len(pages) - 1)])
        if idx < len(pages) - 1:
            page["LastEvaluatedKey"] = {"pk": f"page-{idx}"}
        return page

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        if self._error:
            raise self._error
        if self._query_pages is not None:
            return self._next_page(self._query_pages, self.query_calls)
        return self._query_resp

    def get_item(self, **kwargs):
        if self._error:
            raise self._error
        return {"Item": self._item} if self._item is not None else {}

    def scan(self, **kwargs):
        self.scan_calls.append(kwargs)
        if self._error:
            raise self._error
        if self._scan_pages is not None:
            return self._next_page(self._scan_pages, self.scan_calls)
        return {"Items": self._scan_items}


class _FakeDynamoResource:
    """Routes ``Table(name)`` to a pre-registered fake table."""

    def __init__(self, tables: dict):
        self._tables = tables

    def Table(self, name):  # noqa: N802 (boto3 API casing)
        if name not in self._tables:
            raise AssertionError(f"unexpected table access: {name}")
        return self._tables[name]


@pytest.fixture
def patch_dynamo(monkeypatch):
    """Install a fake dynamodb resource on the module; return a registrar."""

    def _install(**tables):
        monkeypatch.setattr(cca, "dynamodb", _FakeDynamoResource(tables))

    return _install


# --------------------------------------------------------------------------- #
# 1. _query_activities_impl — type + period filtering, sorting, empty user
# --------------------------------------------------------------------------- #
def _activity_item(user_id, created_at, atype, name, distance_m, moving_s):
    import json

    return {
        "user_id": user_id,
        "created_at": created_at,
        "activity_id": f"{atype}-{created_at}",
        "activity_data_json": json.dumps(
            {
                "type": atype,
                "name": name,
                "distance": distance_m,
                "moving_time": moving_s,
                "start_date_local": created_at,
            }
        ),
    }


def test_query_activities_filters_by_type(patch_dynamo):
    items = [
        _activity_item("42", "2026-07-10T08:00:00", "Run", "Seuil", 10000, 2400),
        _activity_item("42", "2026-07-11T18:00:00", "WeightTraining", "Upper A", 0, 3600),
        _activity_item("42", "2026-07-12T07:00:00", "Run", "Footing", 8000, 2700),
    ]
    patch_dynamo(**{cca.ACTIVITIES_TABLE: _FakeTable(query_resp={"Items": items})})

    result = cca._query_activities_impl("42", "Run", "", "")

    assert [r["type"] for r in result] == ["Run", "Run"]
    assert all("Upper A" != r["name"] for r in result)


def test_query_activities_french_alias_matches_strava_type(patch_dynamo):
    items = [
        _activity_item("42", "2026-07-10T08:00:00", "Run", "Seuil", 10000, 2400),
        _activity_item("42", "2026-07-11T18:00:00", "WeightTraining", "Upper A", 0, 3600),
    ]
    patch_dynamo(**{cca.ACTIVITIES_TABLE: _FakeTable(query_resp={"Items": items})})

    # "musculation" (FR) must resolve to the Strava "WeightTraining" type.
    result = cca._query_activities_impl("42", "musculation", "", "")

    assert [r["type"] for r in result] == ["WeightTraining"]
    # And "course" (FR) must resolve to "Run".
    result_run = cca._query_activities_impl("42", "course", "", "")
    assert [r["type"] for r in result_run] == ["Run"]


def test_query_activities_no_type_returns_all_sorted_desc(patch_dynamo):
    items = [
        _activity_item("42", "2026-07-10T08:00:00", "Run", "A", 10000, 2400),
        _activity_item("42", "2026-07-12T07:00:00", "Ride", "B", 30000, 3600),
        _activity_item("42", "2026-07-11T18:00:00", "WeightTraining", "C", 0, 3600),
    ]
    patch_dynamo(**{cca.ACTIVITIES_TABLE: _FakeTable(query_resp={"Items": items})})

    result = cca._query_activities_impl("42", "", "", "")

    # All three returned, most-recent date first.
    assert len(result) == 3
    assert [r["date"] for r in result] == ["2026-07-12", "2026-07-11", "2026-07-10"]


def test_query_activities_empty_user_returns_empty(patch_dynamo):
    # No table access should occur when user_id is empty.
    patch_dynamo()
    assert cca._query_activities_impl("", "Run", "", "") == []


def test_query_activities_filters_by_period_expands_range(patch_dynamo):
    table = _FakeTable(query_resp={"Items": []})
    patch_dynamo(**{cca.ACTIVITIES_TABLE: table})

    cca._query_activities_impl("42", "", "2026-07-01", "2026-07-07")

    # The GSI range query must have been issued once, scoped to UserActivitiesIndex.
    assert len(table.query_calls) == 1
    assert table.query_calls[0]["IndexName"] == "UserActivitiesIndex"


def test_query_activities_dynamodb_error_returns_empty(patch_dynamo):
    patch_dynamo(**{cca.ACTIVITIES_TABLE: _FakeTable(error=RuntimeError("ddb down"))})
    # Must degrade gracefully to [] rather than raising.
    assert cca._query_activities_impl("42", "Run", "", "") == []


def test_compact_activity_computes_run_pace_and_is_jsonable(patch_dynamo):
    items = [_activity_item("42", "2026-07-10T08:00:00", "Run", "Seuil", 10000, 2400)]
    patch_dynamo(**{cca.ACTIVITIES_TABLE: _FakeTable(query_resp={"Items": items})})

    (rec,) = cca._query_activities_impl("42", "Run", "", "")

    assert rec["distance_km"] == 10.0
    assert rec["duration_min"] == 40
    # 2400s / 10km = 240 s/km = 4:00/km
    assert rec["pace"] == "4:00/km"


def test_compact_activity_includes_truncated_description(patch_dynamo):
    item = _activity_item("42", "2026-07-10T08:00:00", "Run", "Seuil", 10000, 2400)
    item["original_description"] = "B" * 800  # athlete's own note, over the cap
    item["enhanced_description"] = "A" * 800  # published AI narrative, over the cap
    patch_dynamo(**{cca.ACTIVITIES_TABLE: _FakeTable(query_resp={"Items": [item]})})

    (rec,) = cca._query_activities_impl("42", "Run", "", "")

    # Both narrative fields exposed, each truncated to 500 chars, kept distinct.
    assert rec["description"] == "B" * 500
    assert rec["enhanced_description"] == "A" * 500


def test_compact_activity_omits_empty_description(patch_dynamo):
    items = [_activity_item("42", "2026-07-10T08:00:00", "Run", "Seuil", 10000, 2400)]
    patch_dynamo(**{cca.ACTIVITIES_TABLE: _FakeTable(query_resp={"Items": items})})

    (rec,) = cca._query_activities_impl("42", "Run", "", "")

    # No narrative stored → both keys omitted rather than empty strings.
    assert "description" not in rec
    assert "enhanced_description" not in rec


# --------------------------------------------------------------------------- #
# 2. _get_pace_zones_impl — reads user_config, empty user, DynamoDB error
# --------------------------------------------------------------------------- #
def test_get_pace_zones_reads_user_config(patch_dynamo):
    item = {
        "user_id": "42",
        "user_preferences": {
            "pace_zones": {"z2": "5:30", "z4": "4:10"},
            "personal_records": [{"distance": "10K", "time": "39:00"}],
            "max_hr": 190,
        },
        "athlete_zones": {"z1": [0, 120]},
        "best_efforts_prs": {"5k": "18:30"},
    }
    patch_dynamo(**{cca.USER_CONFIG_TABLE: _FakeTable(item=item)})

    result = cca._get_pace_zones_impl("42")

    assert result["pace_zones"] == {"z2": "5:30", "z4": "4:10"}
    assert result["personal_records"] == [{"distance": "10K", "time": "39:00"}]
    assert result["max_hr"] == 190
    assert result["athlete_zones"] == {"z1": [0, 120]}
    assert result["best_efforts_prs"] == {"5k": "18:30"}


def test_get_pace_zones_empty_user_returns_empty(patch_dynamo):
    patch_dynamo()
    assert cca._get_pace_zones_impl("") == {}


def test_get_pace_zones_missing_prefs_returns_defaults(patch_dynamo):
    patch_dynamo(**{cca.USER_CONFIG_TABLE: _FakeTable(item={"user_id": "42"})})
    result = cca._get_pace_zones_impl("42")
    assert result == {
        "pace_zones": {},
        "personal_records": [],
        "max_hr": None,
        "athlete_zones": {},
        "best_efforts_prs": {},
    }


def test_get_pace_zones_dynamodb_error_returns_empty(patch_dynamo):
    patch_dynamo(**{cca.USER_CONFIG_TABLE: _FakeTable(error=RuntimeError("ddb down"))})
    assert cca._get_pace_zones_impl("42") == {}


def test_get_pace_zones_serializes_decimals(patch_dynamo):
    item = {
        "user_id": "42",
        "user_preferences": {"max_hr": Decimal("188")},
    }
    patch_dynamo(**{cca.USER_CONFIG_TABLE: _FakeTable(item=item)})
    result = cca._get_pace_zones_impl("42")
    assert result["max_hr"] == 188
    assert isinstance(result["max_hr"], int)


# --------------------------------------------------------------------------- #
# 3. _get_campus_plan_impl — week selection, athlete-context split, error
# --------------------------------------------------------------------------- #
def test_get_campus_plan_selects_current_week_by_default(patch_dynamo):
    scan_items = [
        {"session_date": "2026-07-13", "title": "Seuil", "week_date_iso": "2026-W29", "is_current_week": True},
        {"session_date": "2026-07-20", "title": "VMA", "week_date_iso": "2026-W30", "is_future": True},
        {"session_date": "athlete-context", "goal": {"race": "semi"}, "assiduity": "high", "sport_profile": "runner"},
    ]
    patch_dynamo(**{cca.COACHING_SESSIONS_TABLE: _FakeTable(scan_items=scan_items)})

    result = cca._get_campus_plan_impl("")

    assert result["week_iso"] == "current"
    assert [s["title"] for s in result["sessions"]] == ["Seuil"]
    assert result["athlete_context"]["goal"] == {"race": "semi"}


def test_get_campus_plan_selects_requested_week(patch_dynamo):
    scan_items = [
        {"session_date": "2026-07-13", "title": "Seuil", "week_date_iso": "2026-W29", "is_current_week": True},
        {"session_date": "2026-07-20", "title": "VMA", "week_date_iso": "2026-W30", "is_future": True},
    ]
    patch_dynamo(**{cca.COACHING_SESSIONS_TABLE: _FakeTable(scan_items=scan_items)})

    result = cca._get_campus_plan_impl("2026-W30")

    assert result["week_iso"] == "2026-W30"
    assert [s["title"] for s in result["sessions"]] == ["VMA"]


def test_get_campus_plan_excludes_athlete_context_from_sessions(patch_dynamo):
    scan_items = [
        {"session_date": "athlete-context", "goal": {"race": "10K"}},
        {"session_date": "2026-07-13", "title": "Seuil", "week_date_iso": "2026-W29", "is_current_week": True},
    ]
    patch_dynamo(**{cca.COACHING_SESSIONS_TABLE: _FakeTable(scan_items=scan_items)})

    result = cca._get_campus_plan_impl("")

    assert all(s.get("title") != "" and "goal" not in s for s in result["sessions"])
    assert result["athlete_context"]["goal"] == {"race": "10K"}


def test_get_campus_plan_dynamodb_error_returns_empty_shape(patch_dynamo):
    patch_dynamo(**{cca.COACHING_SESSIONS_TABLE: _FakeTable(error=RuntimeError("scan boom"))})
    result = cca._get_campus_plan_impl("2026-W29")
    assert result == {"week_iso": "2026-W29", "sessions": [], "athlete_context": {}}


# --------------------------------------------------------------------------- #
# 4. _get_intervals_metrics_impl — series build, empty user, error, missing icu
# --------------------------------------------------------------------------- #
def _intervals_item(created_at, ctl, atl, form):
    import json

    return {
        "activity_id": f"act-{created_at}",
        "created_at": created_at,
        "activity_data_json": json.dumps({"start_date_local": created_at}),
        "intervals_icu_json": json.dumps(
            {"fitness": {"ctl": ctl, "atl": atl, "form": form}}
        ),
    }


def test_get_intervals_metrics_builds_series_sorted_with_latest(patch_dynamo):
    items = [
        _intervals_item("2026-07-12T07:00:00", 55, 60, -5),
        _intervals_item("2026-07-10T08:00:00", 50, 45, 5),
    ]
    patch_dynamo(**{cca.ACTIVITIES_TABLE: _FakeTable(query_resp={"Items": items})})

    result = cca._get_intervals_metrics_impl("42", "", "")

    assert [e["date"] for e in result["series"]] == ["2026-07-10", "2026-07-12"]
    assert result["latest"]["date"] == "2026-07-12"
    assert result["latest"]["ctl"] == 55


def test_get_intervals_metrics_skips_activities_without_icu(patch_dynamo):
    import json

    items = [
        {
            "activity_id": "no-icu",
            "created_at": "2026-07-10T08:00:00",
            "activity_data_json": json.dumps({"start_date_local": "2026-07-10T08:00:00"}),
        },
        _intervals_item("2026-07-12T07:00:00", 55, 60, -5),
    ]
    patch_dynamo(**{cca.ACTIVITIES_TABLE: _FakeTable(query_resp={"Items": items})})

    result = cca._get_intervals_metrics_impl("42", "", "")

    assert len(result["series"]) == 1
    assert result["series"][0]["ctl"] == 55


def test_get_intervals_metrics_empty_user_returns_empty_shape(patch_dynamo):
    patch_dynamo()
    assert cca._get_intervals_metrics_impl("", "", "") == {"series": [], "latest": {}}


def test_get_intervals_metrics_dynamodb_error_returns_empty_shape(patch_dynamo):
    patch_dynamo(**{cca.ACTIVITIES_TABLE: _FakeTable(error=RuntimeError("ddb down"))})
    assert cca._get_intervals_metrics_impl("42", "", "") == {"series": [], "latest": {}}


# --------------------------------------------------------------------------- #
# 5. Identity resolution + range normalization (pure helpers used by tools)
# --------------------------------------------------------------------------- #
def test_extract_user_id_from_jwt_reads_custom_strava_id():
    import base64
    import json

    payload = base64.urlsafe_b64encode(
        json.dumps({"custom:strava_id": "12345", "sub": "abc"}).encode()
    ).decode().rstrip("=")
    token = f"header.{payload}.sig"

    assert cca._extract_user_id_from_jwt(f"Bearer {token}") == "12345"


def test_extract_user_id_from_jwt_handles_malformed_input():
    assert cca._extract_user_id_from_jwt(None) == ""
    assert cca._extract_user_id_from_jwt("") == ""
    assert cca._extract_user_id_from_jwt("Bearer not-a-jwt") == ""


def test_resolve_user_id_prefers_contextvar_then_default(monkeypatch):
    monkeypatch.setattr(cca, "DEFAULT_USER_ID", "fallback")
    token = cca._USER_ID.set("ctx-user")
    try:
        assert cca._resolve_user_id() == "ctx-user"
    finally:
        cca._USER_ID.reset(token)
    # With no ContextVar value, falls back to DEFAULT_USER_ID.
    assert cca._resolve_user_id() == "fallback"


def test_normalize_range_expands_bare_dates():
    start, end = cca._normalize_range("2026-07-01", "2026-07-07")
    assert start == "2026-07-01T00:00:00"
    assert end == "2026-07-07T23:59:59.999999"


def test_normalize_range_defaults_lookback_when_empty():
    start, end = cca._normalize_range("", "")
    # Both bounds populated; start strictly before end.
    assert start and end
    assert start < end


# --------------------------------------------------------------------------- #
# Pagination (fix review m1: LastEvaluatedKey loops)
# --------------------------------------------------------------------------- #
def test_query_activities_follows_pagination(patch_dynamo):
    """All pages are aggregated, not just the first 1 MB page."""
    pages = [
        {"Items": [{"activity_id": "a1", "created_at": "2026-07-01T08:00:00Z",
                    "activity_data_json": json.dumps({"type": "Run", "name": "p1"})}]},
        {"Items": [{"activity_id": "a2", "created_at": "2026-07-02T08:00:00Z",
                    "activity_data_json": json.dumps({"type": "Run", "name": "p2"})}]},
        {"Items": [{"activity_id": "a3", "created_at": "2026-07-03T08:00:00Z",
                    "activity_data_json": json.dumps({"type": "Run", "name": "p3"})}]},
    ]
    table = _FakeTable(query_pages=pages)
    patch_dynamo(**{cca.ACTIVITIES_TABLE: table})

    results = cca._query_activities_impl("user1", "", "2026-07-01", "2026-07-31")

    assert [r["activity_id"] for r in results] == ["a3", "a2", "a1"]
    assert len(table.query_calls) == 3
    # Subsequent calls must carry the ExclusiveStartKey from the previous page.
    assert "ExclusiveStartKey" in table.query_calls[1]
    assert "ExclusiveStartKey" in table.query_calls[2]


def test_intervals_metrics_follows_pagination(patch_dynamo):
    def _icu_item(aid, date, ctl):
        return {
            "activity_id": aid,
            "created_at": f"{date}T08:00:00Z",
            "activity_data_json": json.dumps({"start_date_local": f"{date}T08:00:00Z"}),
            "intervals_icu_json": json.dumps({"fitness": {"ctl": ctl}}),
        }

    pages = [
        {"Items": [_icu_item("a1", "2026-07-01", 50)]},
        {"Items": [_icu_item("a2", "2026-07-02", 51)]},
    ]
    patch_dynamo(**{cca.ACTIVITIES_TABLE: _FakeTable(query_pages=pages)})

    result = cca._get_intervals_metrics_impl("user1", "2026-07-01", "2026-07-31")

    assert [e["ctl"] for e in result["series"]] == [50, 51]
    assert result["latest"]["ctl"] == 51


def test_campus_plan_scan_follows_pagination(patch_dynamo):
    pages = [
        {"Items": [{"session_date": "week-2026-W29", "title": "Seuil",
                    "week_date_iso": "2026-W29", "is_current_week": True}]},
        {"Items": [{"session_date": "athlete-context", "goal": {"name": "10K"}}]},
    ]
    table = _FakeTable(scan_pages=pages)
    patch_dynamo(**{cca.COACHING_SESSIONS_TABLE: table})

    result = cca._get_campus_plan_impl("")

    assert [s["title"] for s in result["sessions"]] == ["Seuil"]
    assert result["athlete_context"]["goal"] == {"name": "10K"}
    assert len(table.scan_calls) == 2


# --------------------------------------------------------------------------- #
# write_chat_to_memory (fix review m1: filters + datetime timestamp)
# --------------------------------------------------------------------------- #
class _FakeMemoryClient:
    def __init__(self):
        self.events = []

    def create_event(self, **kwargs):
        self.events.append(kwargs)


def _patch_memory(monkeypatch, memory_id="mem-123"):
    client = _FakeMemoryClient()
    monkeypatch.setattr(cca, "MEMORY_ID", memory_id)
    monkeypatch.setattr(cca.boto3, "client", lambda *a, **k: client)
    return client


def test_write_chat_to_memory_writes_substantial_exchange(monkeypatch):
    client = _patch_memory(monkeypatch)
    question = "Comment progresse mon allure seuil sur le mois ?"
    answer = "x" * 150

    cca.write_chat_to_memory("user1", question, answer)

    assert len(client.events) == 1
    event = client.events[0]
    assert event["actorId"] == "user1"
    assert event["sessionId"] == "coach-chat-user1"
    # Review fix #3: timestamp must be a datetime, not a float epoch.
    from datetime import datetime as _dt
    assert isinstance(event["eventTimestamp"], _dt)
    roles = [p["conversational"]["role"] for p in event["payload"]]
    assert roles == ["USER", "ASSISTANT"]


def test_write_chat_to_memory_skips_short_exchanges(monkeypatch):
    client = _patch_memory(monkeypatch)

    cca.write_chat_to_memory("user1", "salut", "x" * 150)   # question < 20 chars
    cca.write_chat_to_memory("user1", "q" * 30, "courte")   # answer < 100 chars

    assert client.events == []


def test_write_chat_to_memory_noop_without_memory_or_user(monkeypatch):
    client = _patch_memory(monkeypatch, memory_id="")
    cca.write_chat_to_memory("user1", "q" * 30, "x" * 150)
    assert client.events == []

    client = _patch_memory(monkeypatch)
    cca.write_chat_to_memory("", "q" * 30, "x" * 150)
    assert client.events == []


def test_write_chat_to_memory_truncates_answer(monkeypatch):
    client = _patch_memory(monkeypatch)
    cca.write_chat_to_memory("user1", "q" * 30, "y" * 900)
    stored = client.events[0]["payload"][1]["conversational"]["content"]["text"]
    assert len(stored) == 500


def test_system_prompt_includes_current_date(patch_dynamo):
    from datetime import datetime, timezone

    patch_dynamo(**{cca.USER_CONFIG_TABLE: _FakeTable(item={})})
    prompt = cca._build_system_prompt("42")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # The model must know the real date (and year) to build correct date filters.
    assert today in prompt
    assert "Date du jour" in prompt
