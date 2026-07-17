#!/usr/bin/env python
"""Convert the V1 regression fixtures into an AgentCore Evaluations dataset.

The 8 fixtures in tests/regression/fixtures/ stay the single source of truth
(shared by the V1 harness and this V2 managed pipeline). Each fixture becomes
a single-turn PredefinedScenario; the V1 `eval` block is translated into
natural-language assertions consumed by Builtin.GoalSuccessRate.
See docs/design/regression-evals.md (V2 section).

Usage:
    ./venv/bin/python scripts/build_eval_dataset.py [--output .regression/dataset.json]
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = REPO_ROOT / "tests" / "regression" / "fixtures"

_EMOJI_ASSERTION = {
    "none": "La réponse ne contient aucun emoji.",
    "minimal": "La réponse contient au maximum 2 emojis au total, titre inclus.",
    "moderate": "La réponse contient au maximum 5 emojis au total.",
}


def build_assertions(fixture: Dict[str, Any]) -> List[str]:
    """Translate the V1 eval block + classification into NL assertions."""
    eval_cfg = fixture["eval"]
    agent_input = fixture["agent_input"]
    assertions = [
        "La réponse est un JSON avec un titre et une description d'activité Strava.",
    ]
    if eval_cfg.get("language") == "fr":
        assertions.append("Le titre et la description sont rédigés en français.")
    assertions.append(
        f"La description fait au maximum {eval_cfg['max_chars']} caractères."
    )
    emoji_assertion = _EMOJI_ASSERTION.get(eval_cfg.get("emoji_policy", ""))
    if emoji_assertion:
        assertions.append(emoji_assertion)

    classification = agent_input.get("workout_classification") or {}
    label = classification.get("label")
    if label and classification.get("type") not in ("unknown", None):
        assertions.append(
            f"Le titre et la description décrivent une séance de type « {label} » "
            "et n'utilisent pas les mots « fractionné » ou « intervalles » sauf si ce type est un fractionné."
        )
    return assertions


def build_dataset() -> Dict[str, Any]:
    scenarios = []
    for path in sorted(FIXTURES_DIR.glob("*.json")):
        fixture = json.loads(path.read_text(encoding="utf-8"))
        scenarios.append(
            {
                "schema_type": "AGENTCORE_EVALUATION_PREDEFINED_V1",
                "scenario_id": fixture["name"],
                "turns": [{"input": fixture["agent_input"]}],
                "assertions": build_assertions(fixture),
                "metadata": {
                    "fixture": fixture["name"],
                    "source": "tests/regression/fixtures",
                    "eval": fixture["eval"],
                },
            }
        )
    return {"scenarios": scenarios}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(REPO_ROOT / ".regression" / "dataset.json"))
    args = parser.parse_args()

    dataset = build_dataset()
    out = Path(args.output)
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(dataset, indent=2, ensure_ascii=False))
    print(f"{len(dataset['scenarios'])} scenarios -> {out}")


if __name__ == "__main__":
    main()
