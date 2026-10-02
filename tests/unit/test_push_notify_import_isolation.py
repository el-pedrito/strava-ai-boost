"""shared.push_notify imports and runs without the PushSend environment.

Invariant 8: a module imported for a pure function must not require anything from its
environment at load time. StravaUpdater imports shared.push_notify but does not define
PUSH_SUBSCRIPTIONS_TABLE / VAPID_SECRET; this test replays an environment stripped of
those vars in a subprocess -- the import must succeed and the async invoke must fire.
"""

import os
import subprocess
import sys

LAMBDA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))
PUSH_ONLY = ("PUSH_SUBSCRIPTIONS_TABLE", "VAPID_SECRET", "VAPID_SUBJECT")

SCRIPT = "\n".join(
    [
        "import sys",
        "sys.path.insert(0, sys.argv[1])",
        "import boto3",
        "calls = []",
        "class FakeLambda:",
        "    def invoke(self, **kw): calls.append(kw); return {'StatusCode': 202}",
        "boto3.client = lambda *a, **k: FakeLambda()",
        "from shared.push_notify import notify_activity_enriched",
        "notify_activity_enriched(user_id='12345678', activity_id='1', title='T', body='B')",
        "assert len(calls) == 1, calls",
        "assert calls[0]['FunctionName'] == 'StravaAIBoost-PushSend', calls[0]",
        "print('dispatched')",
    ]
)


def test_notify_imports_without_push_env():
    env = {k: v for k, v in os.environ.items() if k not in PUSH_ONLY}
    env["AWS_DEFAULT_REGION"] = "us-east-1"
    env["PUSH_SEND_FUNCTION"] = "StravaAIBoost-PushSend"
    proc = subprocess.run(
        [sys.executable, "-c", SCRIPT, LAMBDA_DIR],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr[-800:]
    assert proc.stdout.strip().splitlines()[-1] == "dispatched"
