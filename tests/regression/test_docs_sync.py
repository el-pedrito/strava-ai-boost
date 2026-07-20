"""Anti-drift guard for documentation claims.

Key numeric claims in reader-facing docs (README, AGENTS, architecture) must
match the code. When you add a stack/Lambda/runtime, this test fails until
the docs are updated — the docs freshness contract of docs/architecture.md.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DOC_FILES = ["README.md", "AGENTS.md", "docs/architecture.md"]

# Files carrying test-count claims (superset of DOC_FILES).
TEST_COUNT_FILES = DOC_FILES + ["tests/README.md", "docs/ROADMAP.md", "BACKLOG.md"]

_TEST_DEF_RE = re.compile(r"^\s*def test_", re.M)


def _code_stack_count() -> int:
    app = (REPO_ROOT / "app.py").read_text()
    return len(re.findall(r'"StravaAIBoost-[A-Za-z]+"', app))


def _unit_test_count() -> int:
    """Collected count for tests/unit — one test per def (no parametrize)."""
    total = 0
    for path in (REPO_ROOT / "tests/unit").glob("test_*.py"):
        text = path.read_text()
        assert "parametrize" not in text, (
            f"{path.name} uses parametrize — adapt _unit_test_count (def count != collected count)"
        )
        total += len(_TEST_DEF_RE.findall(text))
    return total


def _regression_test_count() -> int:
    """Collected count for tests/regression — test defs, expanding the single
    fixtures parametrize (1 def -> 1 case per fixture JSON)."""
    total = 0
    parametrized = 0
    for path in (REPO_ROOT / "tests/regression").glob("test_*.py"):
        text = path.read_text()
        total += len(_TEST_DEF_RE.findall(text))
        parametrized += len(re.findall(r"^\s*@pytest\.mark\.parametrize\(", text, re.M))
    assert parametrized == 1, (
        "counting logic assumes exactly one parametrize (the fixtures glob in "
        "test_evaluators.py) — adapt _regression_test_count"
    )
    n_fixtures = len(list((REPO_ROOT / "tests/regression/fixtures").glob("*.json")))
    return total - 1 + n_fixtures


def _frontend_test_count() -> int:
    """Collected count for the frontend Vitest suite — it()/test() blocks."""
    total = 0
    for path in (REPO_ROOT / "frontend/src").rglob("*.test.ts*"):
        text = path.read_text()
        assert ".each(" not in text, (
            f"{path.name} uses .each — adapt _frontend_test_count (block count != collected count)"
        )
        total += len(re.findall(r"^\s*(?:it|test)\(", text, re.M))
    return total


def _code_lambda_count() -> int:
    names = set()
    for stack in (REPO_ROOT / "stacks").glob("*.py"):
        names |= set(re.findall(r'function_name="(StravaAIBoost-[A-Za-z]+)"', stack.read_text()))
    return len(names)


class TestDocsSync:
    def test_stack_count_claims(self):
        actual = _code_stack_count()
        offenders = []
        for doc in DOC_FILES:
            text = (REPO_ROOT / doc).read_text()
            for claim in re.findall(r"(\d+)\s+CDK\s+[Ss]tacks", text):
                if int(claim) != actual:
                    offenders.append(f"{doc}: claims {claim} CDK stacks, code has {actual}")
        assert not offenders, "\n".join(offenders)

    def test_lambda_count_claims(self):
        actual = _code_lambda_count()
        offenders = []
        for doc in DOC_FILES:
            text = (REPO_ROOT / doc).read_text()
            for claim in re.findall(r"(\d+)\s+Lambda\s+[Ff]unctions", text):
                if int(claim) != actual:
                    offenders.append(f"{doc}: claims {claim} Lambda functions, code has {actual}")
        assert not offenders, "\n".join(offenders)

    def test_no_decommissioned_components_as_current(self):
        """Decommissioned components must not appear outside historical notes."""
        banned = ["CampusCoachInvoker", "coach_ask_api", "CoachAskAPI", "coach_stream"]
        allowed_context = re.compile(r"decommission|décommission|legacy|replaced|superseded|removed|retir", re.I)
        offenders = []
        for doc in DOC_FILES:
            for i, line in enumerate((REPO_ROOT / doc).read_text().splitlines(), 1):
                for term in banned:
                    if term in line and not allowed_context.search(line):
                        offenders.append(f"{doc}:{i}: '{term}' without decommission context")
        assert not offenders, "\n".join(offenders)

    def test_single_memory_claim(self):
        """The project has exactly one AgentCore Memory (content_gen_mem)."""
        for doc in DOC_FILES:
            text = (REPO_ROOT / doc).read_text()
            assert not re.search(r"2\s+(LTM\s+)?[Mm]emories", text), (
                f"{doc}: claims 2 memories — there is one shared content_gen_mem "
                "(strava_ai_boost_coach_mem was an empty relic, deleted 2026-07-17)"
            )

    def test_test_count_claims(self):
        """Test-count claims in docs must match the actual suites.

        Covers both per-suite mentions (`Lambda unit tests (N tests…)`) and the
        composite summary `TOTAL tests (U backend unit + R regression + F frontend)`.
        """
        unit = _unit_test_count()
        regression = _regression_test_count()
        frontend = _frontend_test_count()
        total = unit + regression + frontend

        suite_claims = {
            "unit": (unit, [
                r"[Ll]ambda [Uu]nit [Tt]ests \((\d+) tests",
                r"(\d+) mocked Lambda unit tests",
                r"\((\d+) mocked tests in `tests/unit/`",
            ]),
            "regression": (regression, [
                r"registry sync \((\d+) tests",
                r"regression harness \((\d+) tests",
                r"(\d+) prompt-regression",
            ]),
            "frontend": (frontend, [
                r"[Ff]rontend (?:[Uu]nit )?[Tt]ests \((\d+) tests",
            ]),
        }
        composite = re.compile(
            r"(\d+)[^(\n]{0,25}\((\d+) backend unit \+ (\d+) "
            r"(?:regression|régression)[^+\n]{0,30}\+ (\d+) frontend"
        )

        offenders = []
        for doc in TEST_COUNT_FILES:
            text = (REPO_ROOT / doc).read_text()
            for suite, (actual, patterns) in suite_claims.items():
                for pattern in patterns:
                    for claim in re.findall(pattern, text):
                        if int(claim) != actual:
                            offenders.append(
                                f"{doc}: claims {claim} {suite} tests, suite has {actual}"
                            )
            for tot, u, r, f in composite.findall(text):
                if (int(tot), int(u), int(r), int(f)) != (total, unit, regression, frontend):
                    offenders.append(
                        f"{doc}: claims {tot} tests ({u}+{r}+{f}), "
                        f"code has {total} ({unit}+{regression}+{frontend})"
                    )
        assert not offenders, "\n".join(offenders)
