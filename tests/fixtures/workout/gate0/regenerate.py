"""Regenerate the Gate 0 goldens from the synthetic sessions next to this file.

Run from the repo root:  python tests/fixtures/workout/gate0/regenerate.py
Changing a golden after Gate 0 requires redoing at least Gate 0 step 2b on the Watch.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[3] / "lambda_functions"))

from shared.campus_workout import map_session  # noqa: E402


def main() -> None:
    for case in sorted(HERE.glob("*.json")):
        spec = json.loads(case.read_text(encoding="utf-8"))
        # `range_alerts` mirrors the RANGE_ALERTS_ENABLED switch (absent = off).
        result = map_session(spec["session"], guid=spec["guid"], range_alerts=spec.get("range_alerts", False))
        if not result.encodable:
            raise SystemExit(f"{case.name}: not encodable ({result.reason_code})")
        case.with_suffix(".workout").write_bytes(result.bytes)
        print(f"{case.stem}.workout  {len(result.bytes)} B  {result.summary}")


if __name__ == "__main__":
    main()
