"""processing.strava_updater imports without the PushSend environment.

StravaUpdater gained a push trigger (shared.push_notify + a lazy push import inside the
helper). This test replays StravaUpdater's own environment (ACTIVITIES_TABLE +
STRAVA_OAUTH_SECRET only, no PUSH_SUBSCRIPTIONS_TABLE / VAPID_SECRET) in a subprocess:
importing the module must succeed, proving no push env var is read at load time.
"""

import os
import subprocess
import sys

LAMBDA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))
PUSH_ONLY = ("PUSH_SUBSCRIPTIONS_TABLE", "VAPID_SECRET", "VAPID_SUBJECT", "PUSH_ENABLED")

SCRIPT = "\n".join(
    [
        "import os, sys",
        "sys.path.insert(0, sys.argv[1])",
        "os.environ['ACTIVITIES_TABLE'] = 'test-activities'",
        "os.environ['STRAVA_OAUTH_SECRET'] = 'test-oauth-secret'",
        "import processing.strava_updater as su",
        "assert hasattr(su, '_maybe_push_completed')",
        "print('imported')",
    ]
)


def test_strava_updater_imports_without_push_env():
    env = {k: v for k, v in os.environ.items() if k not in PUSH_ONLY}
    env["AWS_DEFAULT_REGION"] = "us-east-1"
    proc = subprocess.run(
        [sys.executable, "-c", SCRIPT, LAMBDA_DIR],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr[-800:]
    assert proc.stdout.strip().splitlines()[-1] == "imported"
