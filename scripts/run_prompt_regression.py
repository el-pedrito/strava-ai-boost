#!/usr/bin/env python
"""Prompt regression runner — invokes the DEPLOYED content_gen AgentCore runtime.

Replays synthetic fixtures against the production runtime and scores the
outputs with deterministic evaluators. Compares against the committed baseline.
See docs/design/regression-evals.md.

Usage:
    export AWS_PROFILE=<profile>
    ./venv/bin/python scripts/run_prompt_regression.py                    # all fixtures
    ./venv/bin/python scripts/run_prompt_regression.py --fixtures run_easy,ride
    ./venv/bin/python scripts/run_prompt_regression.py --update-baseline  # accept new state

The agent ARN is discovered from (in order): --agent-arn, the
CONTENT_GENERATION_AGENT_ARN env var, then .env.agentcore at the repo root.
Memory isolation: fixtures use user_id="regression_eval" and the agent runs
with memory hooks disabled at generation time (read-only) — no pollution.
"""

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import boto3

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "lambda_functions"))

from tests.regression.evaluators import evaluate_output  # noqa: E402

FIXTURES_DIR = REPO_ROOT / "tests" / "regression" / "fixtures"
BASELINE_PATH = REPO_ROOT / ".regression" / "baseline.json"
REGION_DEFAULT = "us-east-1"


def discover_agent_arn(cli_arn: str | None) -> str:
    import os

    if cli_arn:
        return cli_arn
    if os.environ.get("CONTENT_GENERATION_AGENT_ARN"):
        return os.environ["CONTENT_GENERATION_AGENT_ARN"]
    env_file = REPO_ROOT / ".env.agentcore"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("CONTENT_GENERATION_AGENT_ARN="):
                return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit(
        "Agent ARN not found. Pass --agent-arn, set CONTENT_GENERATION_AGENT_ARN, "
        "or run scripts/configure_agentcore_integration.sh to generate .env.agentcore."
    )


def load_fixtures(names_filter: list[str] | None) -> list[dict]:
    fixtures = []
    for path in sorted(FIXTURES_DIR.glob("*.json")):
        if names_filter and path.stem not in names_filter:
            continue
        fixtures.append(json.loads(path.read_text(encoding="utf-8")))
    if not fixtures:
        raise SystemExit(f"No fixtures matched in {FIXTURES_DIR}")
    return fixtures


def invoke_runtime(client, agent_arn: str, agent_input: dict) -> str:
    """Invoke the deployed runtime; return the raw completion text."""
    from processing.content_generator import _process_agent_response

    session_id = f"regression-eval-{uuid.uuid4()}"
    response = client.invoke_agent_runtime(
        agentRuntimeArn=agent_arn,
        runtimeSessionId=session_id,
        payload=json.dumps(agent_input, default=str).encode("utf-8"),
    )
    return _process_agent_response(response)


def parse_output(completion: str, fixture: dict) -> dict:
    from processing.content_generator import _parse_agent_response

    return _parse_agent_response(
        completion,
        fixture["agent_input"].get("workout_classification"),
        fixture["agent_input"].get("active_modules", []),
    )


def run(args) -> int:
    agent_arn = discover_agent_arn(args.agent_arn)
    region = agent_arn.split(":")[3] if agent_arn.count(":") >= 4 else REGION_DEFAULT
    client = boto3.client("bedrock-agentcore", region_name=region)
    fixtures = load_fixtures(args.fixtures.split(",") if args.fixtures else None)

    print(f"Runtime : {agent_arn}")
    print(f"Fixtures: {[f['name'] for f in fixtures]}\n")

    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "agent_arn": agent_arn,
        "fixtures": {},
    }
    total_fail = 0
    total_warn = 0

    for fixture in fixtures:
        name = fixture["name"]
        print(f"=== {name} ===")
        try:
            completion = invoke_runtime(client, agent_arn, fixture["agent_input"])
            parsed = parse_output(completion, fixture)
            title = parsed.get("title")
            description = parsed.get("description")
        except Exception as exc:  # noqa: BLE001 — report and continue with other fixtures
            print(f"  INVOCATION ERROR: {exc}\n")
            report["fixtures"][name] = {"error": str(exc), "results": []}
            total_fail += 1
            continue

        results = evaluate_output(title, description, fixture["eval"])
        fails = [r for r in results if not r["passed"] and r["severity"] == "fail"]
        warns = [r for r in results if not r["passed"] and r["severity"] == "warn"]
        total_fail += len(fails)
        total_warn += len(warns)

        print(f"  title: {title!r}")
        for r in results:
            mark = "OK  " if r["passed"] else ("FAIL" if r["severity"] == "fail" else "WARN")
            detail = f" — {r['detail']}" if r["detail"] and not r["passed"] else ""
            print(f"  [{mark}] {r['criterion']}{detail}")
        print()

        report["fixtures"][name] = {
            "title": title,
            "description_chars": len(description or ""),
            "results": results,
        }

    print(f"TOTAL: {total_fail} fail(s), {total_warn} warn(s) across {len(fixtures)} fixture(s)")

    # Baseline comparison / update
    baseline_fail_delta = 0
    if BASELINE_PATH.exists() and not args.update_baseline:
        baseline = json.loads(BASELINE_PATH.read_text())
        base_fails = _count_fails(baseline)
        baseline_fail_delta = total_fail - base_fails
        print(f"Baseline: {base_fails} fail(s) ({baseline.get('run_at', '?')}) → delta {baseline_fail_delta:+d}")
    if args.update_baseline:
        BASELINE_PATH.parent.mkdir(exist_ok=True)
        BASELINE_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"Baseline updated: {BASELINE_PATH}")

    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"Report written: {args.report}")

    return 1 if (total_fail > 0 and baseline_fail_delta > 0) or (total_fail > 0 and not BASELINE_PATH.exists() and not args.update_baseline) else 0


def _count_fails(report: dict) -> int:
    count = 0
    for fx in report.get("fixtures", {}).values():
        if fx.get("error"):
            count += 1
        for r in fx.get("results", []):
            if not r["passed"] and r["severity"] == "fail":
                count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fixtures", help="Comma-separated fixture names (default: all)")
    parser.add_argument("--agent-arn", help="content_gen runtime ARN (default: env/.env.agentcore)")
    parser.add_argument("--update-baseline", action="store_true", help="Accept current results as the new baseline")
    parser.add_argument("--report", help="Write the JSON report to this path")
    args = parser.parse_args()
    sys.exit(run(args))


if __name__ == "__main__":
    main()
