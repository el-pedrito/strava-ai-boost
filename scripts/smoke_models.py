#!/usr/bin/env python
"""Smoke test of the model contract (MODEL_PROFILES) against real Bedrock.

Lot 2 of docs/design/reliability-plan-2026-10.md. For every registry model it
makes real Converse calls and checks that the profile in
src/config/llm_config.py matches what Bedrock actually does:

  1. text      short answer with the profile's thinking_off -> end_turn + text
  2. json      tiny JSON answer with thinking_off -> json.loads works
  3. temp      a call sending `temperature` -> rejected iff accepts_temperature=False
  4. budget    reasoning ON with default_max_tokens -> end_turn + text
               (the reasoning shares maxTokens, so a too-small budget shows here)

With --runtimes it also invokes the deployed content_gen AgentCore runtime with
the run_easy regression fixture and checks the production parser gets a title
and a description out of it. The coach_chat runtime is skipped: it only accepts
a Cognito JWT (customJWT authorizer), which this script does not hold.

Exit code is non-zero on any failure. Cost: ~0.05 USD per model run (the
runtime smoke adds one content generation).

Usage:
    export AWS_PROFILE=<profile>          # optional, default credential chain
    export AWS_REGION=us-east-1           # optional, default us-east-1
    venv/bin/python scripts/smoke_models.py
    venv/bin/python scripts/smoke_models.py --runtimes   # after deploy_agentcore_agents.sh
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Optional

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from config.llm_config import ALL_MODEL_IDS, DEFAULT_MODEL_IDS, model_profile  # noqa: E402
from run_prompt_regression import discover_agent_arn, invoke_runtime, parse_output  # noqa: E402

REGION = os.environ.get("AWS_REGION", "us-east-1")
RUN_EASY_FIXTURE = REPO_ROOT / "tests" / "regression" / "fixtures" / "run_easy.json"

# Short calls: fail fast, a couple of retries for throttling only.
BEDROCK_CONFIG = BotoConfig(read_timeout=120, retries={"max_attempts": 3, "mode": "standard"})
# One content generation runs 50-150s; never let botocore retry mid-generation
# on a read timeout shorter than that (duplicate call, cf. 2026-10-08).
RUNTIME_CONFIG = BotoConfig(read_timeout=300, retries={"max_attempts": 2, "mode": "standard"})

SHORT_MAX_TOKENS = 300


class SmokeFailure(Exception):
    """A check whose outcome contradicts the model contract."""


def _text(response: dict) -> str:
    blocks = response.get("output", {}).get("message", {}).get("content", [])
    return "".join(block.get("text", "") for block in blocks if "text" in block)


def _usage(response: dict) -> dict:
    usage = response.get("usage", {})
    return {"in": usage.get("inputTokens", 0), "out": usage.get("outputTokens", 0)}


def _expect_text_answer(response: dict, check: str) -> str:
    stop = response.get("stopReason")
    text = _text(response).strip()
    if stop != "end_turn":
        raise SmokeFailure(f"{check}: stopReason={stop!r} (expected end_turn), text={text[:80]!r}")
    if not text:
        raise SmokeFailure(f"{check}: no text block in the answer (reasoning ate the budget?)")
    return text


def _converse(client, model_id: str, prompt: str, max_tokens: int,
              extra_fields: Optional[dict] = None, temperature: Optional[float] = None) -> dict:
    inference: dict[str, Any] = {"maxTokens": max_tokens}
    if temperature is not None:
        inference["temperature"] = temperature
    kwargs: dict[str, Any] = {
        "modelId": model_id,
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": inference,
    }
    if extra_fields:
        kwargs["additionalModelRequestFields"] = extra_fields
    return client.converse(**kwargs)


def check_text(client, model_id: str, profile: dict) -> dict:
    response = _converse(client, model_id, "Réponds uniquement par le mot : bonjour.",
                         SHORT_MAX_TOKENS, extra_fields=profile["thinking_off"])
    text = _expect_text_answer(response, "text")
    return {"usage": _usage(response), "detail": repr(text[:40])}


def check_json(client, model_id: str, profile: dict) -> dict:
    prompt = ('Return ONLY this JSON object, no prose and no code fence: '
              '{"ok": true, "n": 3}')
    response = _converse(client, model_id, prompt, SHORT_MAX_TOKENS,
                         extra_fields=profile["thinking_off"])
    text = _expect_text_answer(response, "json")
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise SmokeFailure(f"json: not parsable ({exc}): {text[:120]!r}") from exc
    if not isinstance(payload, dict):
        raise SmokeFailure(f"json: expected an object, got {type(payload).__name__}")
    return {"usage": _usage(response), "detail": json.dumps(payload)}


def check_temperature(client, model_id: str, profile: dict) -> dict:
    accepts = profile["accepts_temperature"]
    try:
        response = _converse(client, model_id, "Réponds : ok.", 50,
                             extra_fields=profile["thinking_off"], temperature=0.2)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code != "ValidationException":
            raise
        if accepts:
            raise SmokeFailure(f"temp: rejected but profile says accepts_temperature=True: {exc}") from exc
        return {"usage": {"in": 0, "out": 0}, "detail": "rejected, as the profile says"}
    if not accepts:
        raise SmokeFailure("temp: accepted but profile says accepts_temperature=False")
    return {"usage": _usage(response), "detail": "accepted, as the profile says"}


def check_budget(client, model_id: str, profile: dict) -> dict:
    # Reasoning ON (no thinking_off): the default behaviour of the agents.
    response = _converse(client, model_id, "En une phrase : quelle est la capitale de la France ?",
                         profile["default_max_tokens"])
    text = _expect_text_answer(response, "budget")
    return {"usage": _usage(response), "detail": repr(text[:40])}


CHECKS: list[tuple[str, Callable[..., dict]]] = [
    ("text", check_text),
    ("json", check_json),
    ("temp", check_temperature),
    ("budget", check_budget),
]


def models_to_check() -> list[str]:
    """Registry defaults plus any env override, deduplicated, in order."""
    seen: list[str] = []
    for model_id in [*DEFAULT_MODEL_IDS, *ALL_MODEL_IDS]:
        if model_id not in seen:
            seen.append(model_id)
    return seen


def smoke_models(client) -> int:
    failures = 0
    total_in = total_out = 0
    for model_id in models_to_check():
        print(f"=== {model_id} ===")
        try:
            profile = model_profile(model_id)
        except KeyError as exc:
            print(f"  FAIL profile: {exc}")
            failures += 1
            continue
        for name, check in CHECKS:
            try:
                result = check(client, model_id, profile)
            except SmokeFailure as exc:
                print(f"  FAIL {name:<6} {exc}")
                failures += 1
                continue
            except (ClientError, BotoCoreError) as exc:
                print(f"  FAIL {name:<6} {type(exc).__name__}: {exc}")
                failures += 1
                continue
            usage = result["usage"]
            total_in += usage["in"]
            total_out += usage["out"]
            print(f"  ok   {name:<6} in={usage['in']:<5} out={usage['out']:<5} {result['detail']}")
    print(f"\nTokens: in={total_in} out={total_out}")
    return failures


def smoke_runtimes(agent_arn_arg: Optional[str]) -> int:
    print("\n=== runtimes ===")
    print("  skip coach_chat: customJWT runtime (Cognito ID token required), not invokable with IAM")
    try:
        agent_arn = discover_agent_arn(agent_arn_arg)
    except SystemExit as exc:
        print(f"  FAIL content_gen: {exc}")
        return 1
    region = agent_arn.split(":")[3] if agent_arn.count(":") >= 4 else REGION
    client = boto3.client("bedrock-agentcore", region_name=region, config=RUNTIME_CONFIG)
    fixture = json.loads(RUN_EASY_FIXTURE.read_text(encoding="utf-8"))
    # invoke_runtime opens a fresh session; the fixture's user_id
    # (regression_eval) keeps AgentCore memory isolated from the athlete's.
    try:
        completion = invoke_runtime(client, agent_arn, fixture["agent_input"])
        parsed = parse_output(completion, fixture)
    except (ClientError, BotoCoreError, ValueError, KeyError) as exc:
        print(f"  FAIL content_gen: {type(exc).__name__}: {exc}")
        return 1
    title = (parsed.get("title") or "").strip()
    description = (parsed.get("description") or "").strip()
    if not title or not description:
        print(f"  FAIL content_gen: title={title[:60]!r} description={description[:60]!r}")
        return 1
    print(f"  ok   content_gen title={title[:60]!r} description={len(description)} chars")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--runtimes", action="store_true",
                        help="also invoke the deployed content_gen runtime (run_easy fixture)")
    parser.add_argument("--agent-arn", help="content_gen runtime ARN (default: discovered)")
    args = parser.parse_args()

    print(f"Region: {REGION}")
    client = boto3.client("bedrock-runtime", region_name=REGION, config=BEDROCK_CONFIG)
    failures = smoke_models(client)
    if args.runtimes:
        failures += smoke_runtimes(args.agent_arn)

    if failures:
        print(f"\nSMOKE FAILED: {failures} check(s)")
        return 1
    print("\nSMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
