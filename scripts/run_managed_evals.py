#!/usr/bin/env python
"""Managed regression evals — AgentCore Evaluations dataset runner (V2).

Replays the regression dataset against the DEPLOYED content_gen runtime and
scores the traces with managed evaluators (LLM-as-a-Judge): 3 built-ins +
2 custom (VoixAuthentiqueFR, FideliteDonneesActivite).
See docs/design/regression-evals.md (V2 section).

COST: ~1.0-1.3 $ per full run (agent invocations + judge tokens) and ~4-5 min
(180 s CloudWatch ingestion wait). The deterministic V1 harness
(scripts/run_prompt_regression.py) stays the cheap first line of defense.

Usage:
    export AWS_PROFILE=<profile>
    ./venv/bin/python scripts/run_managed_evals.py                 # full run
    ./venv/bin/python scripts/run_managed_evals.py --scenarios run_easy,ride
    ./venv/bin/python scripts/run_managed_evals.py --update-baseline
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

from bedrock_agentcore.evaluation import (  # noqa: E402
    CloudWatchAgentSpanCollector,
    EvaluationRunConfig,
    EvaluatorConfig,
    FileDatasetProvider,
    OnDemandEvaluationDatasetRunner,
)
from bedrock_agentcore.evaluation.runner.dataset_types import Dataset  # noqa: E402
from bedrock_agentcore.evaluation.runner.invoker_types import (  # noqa: E402
    AgentInvokerInput,
    AgentInvokerOutput,
)

DATASET_PATH = REPO_ROOT / ".regression" / "dataset.json"
BASELINE_PATH = REPO_ROOT / ".regression" / "baseline_managed.json"
REGION_DEFAULT = "us-east-1"

BUILTIN_EVALUATORS = [
    "Builtin.GoalSuccessRate",
    "Builtin.InstructionFollowing",
    "Builtin.Faithfulness",
]
CUSTOM_EVALUATOR_NAMES = ["VoixAuthentiqueFR", "FideliteDonneesActivite"]

# Custom judge outcomes mapped to severities. Customs are TREND SIGNALS only
# (warn at worst), never binary gates: live runs demonstrated judge arithmetic
# errors (e.g. per-lap pace computed over 1000m for an 1100m lap → false
# "CHIFFRE_INVENTE"). The real gates stay the deterministic V1 checks.
CUSTOM_SEVERITY = {
    "VoixAuthentiqueFR": {"VOIX_IA": "warn", "MITIGE": "warn"},
}
FIDELITE_WARN_BELOW = 0.5


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
    raise SystemExit("Agent ARN not found (--agent-arn / CONTENT_GENERATION_AGENT_ARN / .env.agentcore).")


def resolve_custom_evaluator_ids(control, names: list[str]) -> list[str]:
    """Resolve custom evaluator names to their ids; fail if missing."""
    existing = {}
    token = None
    while True:
        kwargs = {"maxResults": 50, **({"nextToken": token} if token else {})}
        resp = control.list_evaluators(**kwargs)
        for e in resp.get("evaluators", []):
            existing[e["evaluatorName"]] = e["evaluatorId"]
        token = resp.get("nextToken")
        if not token:
            break
    missing = [n for n in names if n not in existing]
    if missing:
        raise SystemExit(
            f"Custom evaluators missing: {missing}. Run scripts/create_managed_evaluators.py first."
        )
    return [existing[n] for n in names]


def make_agent_invoker(agent_arn: str, region: str):
    client = boto3.client("bedrock-agentcore", region_name=region)

    def invoke(invoker_input: AgentInvokerInput) -> AgentInvokerOutput:
        session_id = invoker_input.session_id or f"managed-eval-{uuid.uuid4()}"
        response = client.invoke_agent_runtime(
            agentRuntimeArn=agent_arn,
            runtimeSessionId=session_id,
            payload=json.dumps(invoker_input.payload, default=str).encode("utf-8"),
        )
        body = response.get("response")
        if hasattr(body, "read"):
            output = body.read().decode("utf-8")
        else:
            output = "".join(
                chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk) for chunk in body
            )
        return AgentInvokerOutput(agent_output=output)

    return invoke


def classify(evaluator_id: str, value, label) -> str:
    """Map an evaluator outcome to ok/warn using V1 semantics (customs never fail)."""
    name = evaluator_id.split("-")[0]
    if name == "VoixAuthentiqueFR":
        return CUSTOM_SEVERITY[name].get(str(label), "ok")
    if name == "FideliteDonneesActivite":
        try:
            return "warn" if float(value) < FIDELITE_WARN_BELOW else "ok"
        except (TypeError, ValueError):
            return "warn"
    # Built-ins: informational trend signal only.
    return "ok"


def run(args) -> int:
    agent_arn = discover_agent_arn(args.agent_arn)
    region = agent_arn.split(":")[3] if agent_arn.count(":") >= 4 else REGION_DEFAULT
    runtime_id = agent_arn.rsplit("/", 1)[-1]
    log_group = f"/aws/bedrock-agentcore/runtimes/{runtime_id}-DEFAULT"

    control = boto3.client("bedrock-agentcore-control", region_name=region)
    custom_ids = resolve_custom_evaluator_ids(control, CUSTOM_EVALUATOR_NAMES)
    evaluator_ids = BUILTIN_EVALUATORS + custom_ids

    dataset = FileDatasetProvider(str(DATASET_PATH)).get_dataset()
    if args.scenarios:
        wanted = set(args.scenarios.split(","))
        dataset = Dataset(scenarios=[s for s in dataset.scenarios if s.scenario_id in wanted])
        if not dataset.scenarios:
            raise SystemExit(f"No scenario matched {wanted}")

    print(f"Runtime    : {agent_arn}")
    print(f"Log group  : {log_group}")
    print(f"Evaluators : {evaluator_ids}")
    print(f"Scenarios  : {[s.scenario_id for s in dataset.scenarios]}")
    print("Running (agent invocations + ~180s CloudWatch ingestion wait)...\n")

    runner = OnDemandEvaluationDatasetRunner(region=region)
    result = runner.run(
        config=EvaluationRunConfig(
            evaluator_config=EvaluatorConfig(evaluator_ids=evaluator_ids),
        ),
        dataset=dataset,
        agent_invoker=make_agent_invoker(agent_arn, region),
        span_collector=CloudWatchAgentSpanCollector(log_group_name=log_group, region=region),
    )

    report = {"run_at": datetime.now(timezone.utc).isoformat(), "agent_arn": agent_arn, "scenarios": {}}
    totals = {"fail": 0, "warn": 0}

    for scenario in result.scenario_results:
        rows = []
        print(f"=== {scenario.scenario_id} ({scenario.status}) ===")
        if scenario.error:
            print(f"  ERROR: {scenario.error}")
            totals["fail"] += 1
        for ev in scenario.evaluator_results or []:
            for r in ev.results or []:
                value = r.get("value")
                label = r.get("label")
                explanation = r.get("explanation") or r.get("errorMessage") or ""
                sev = classify(ev.evaluator_id, value, label)
                if sev in totals:
                    totals[sev] += 1
                mark = {"ok": "OK  ", "warn": "WARN", "fail": "FAIL"}[sev]
                print(f"  [{mark}] {ev.evaluator_id}: value={value} label={label}")
                if sev != "ok" and explanation:
                    print(f"         {explanation[:200]}")
                rows.append({
                    "evaluator_id": ev.evaluator_id,
                    "value": value,
                    "label": label,
                    "severity": sev,
                    "explanation": explanation,
                })
        print()
        report["scenarios"][scenario.scenario_id] = {
            "status": scenario.status,
            "error": scenario.error,
            "results": rows,
        }

    print(f"TOTAL: {totals['fail']} fail(s), {totals['warn']} warn(s) across {len(result.scenario_results)} scenario(s)")

    delta = 0
    if BASELINE_PATH.exists() and not args.update_baseline:
        baseline = json.loads(BASELINE_PATH.read_text())
        base_fails = sum(
            1
            for sc in baseline.get("scenarios", {}).values()
            for r in sc.get("results", [])
            if r.get("severity") == "fail"
        ) + sum(1 for sc in baseline.get("scenarios", {}).values() if sc.get("error"))
        delta = totals["fail"] - base_fails
        print(f"Baseline: {base_fails} fail(s) ({baseline.get('run_at', '?')}) → delta {delta:+d}")
    if args.update_baseline:
        BASELINE_PATH.parent.mkdir(exist_ok=True)
        BASELINE_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        print(f"Baseline updated: {BASELINE_PATH}")
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        print(f"Report written: {args.report}")

    return 1 if delta > 0 else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenarios", help="Comma-separated scenario ids (default: all)")
    parser.add_argument("--agent-arn", help="content_gen runtime ARN (default: env/.env.agentcore)")
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--report", help="Write JSON report to this path")
    args = parser.parse_args()
    sys.exit(run(args))


if __name__ == "__main__":
    main()
