"""Anti-drift guard for documentation claims.

Key numeric claims in reader-facing docs (README, AGENTS, architecture) must
match the code. When you add a stack/Lambda/runtime, this test fails until
the docs are updated — the docs freshness contract of docs/architecture.md.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DOC_FILES = ["README.md", "AGENTS.md", "docs/architecture.md"]


def _code_stack_count() -> int:
    app = (REPO_ROOT / "app.py").read_text()
    return len(re.findall(r'"StravaAIBoost-[A-Za-z]+"', app))


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
