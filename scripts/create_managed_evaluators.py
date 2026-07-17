#!/usr/bin/env python
"""Create/update the custom AgentCore Evaluations evaluators (idempotent).

Reads every JSON config in tests/regression/evaluators_managed/ and creates or
updates the corresponding evaluator via bedrock-agentcore-control.
See docs/design/regression-evals.md (V2 section).

Usage:
    export AWS_PROFILE=<profile>
    ./venv/bin/python scripts/create_managed_evaluators.py [--region us-east-1]
"""

import argparse
import json
from pathlib import Path

import boto3

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIGS_DIR = REPO_ROOT / "tests" / "regression" / "evaluators_managed"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()

    client = boto3.client("bedrock-agentcore-control", region_name=args.region)

    existing = {}
    token = None
    while True:
        kwargs = {"maxResults": 50, **({"nextToken": token} if token else {})}
        resp = client.list_evaluators(**kwargs)
        for e in resp.get("evaluators", []):
            existing[e["evaluatorName"]] = e["evaluatorId"]
        token = resp.get("nextToken")
        if not token:
            break

    for path in sorted(CONFIGS_DIR.glob("*.json")):
        config = json.loads(path.read_text(encoding="utf-8"))
        name = config["evaluatorName"]
        if name in existing:
            evaluator_id = existing[name]
            client.update_evaluator(
                evaluatorId=evaluator_id,
                description=config.get("description", ""),
                evaluatorConfig=config["evaluatorConfig"],
            )
            print(f"updated  {name} ({evaluator_id})")
        else:
            resp = client.create_evaluator(
                evaluatorName=name,
                description=config.get("description", ""),
                level=config["level"],
                evaluatorConfig=config["evaluatorConfig"],
            )
            evaluator_id = resp["evaluatorId"]
            print(f"created  {name} ({evaluator_id})")


if __name__ == "__main__":
    main()
