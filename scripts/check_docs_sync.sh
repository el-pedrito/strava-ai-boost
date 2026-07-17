#!/bin/bash
# Docs freshness guard — wired as a Kiro `stop` hook (and usable standalone/CI).
#
# Runs the documentation anti-drift tests (tests/regression/test_docs_sync.py):
# doc claims (stack/lambda counts, single memory, no decommissioned components
# presented as current) are checked against the code. Exits silently when not
# in this repo so the hook is a safe no-op elsewhere.
#
# See docs/architecture.md § Documentation map & freshness contract.

set -u

# Only run inside the strava-ai-boost repo (hook cwd = wherever Kiro runs).
[ -f "tests/regression/test_docs_sync.py" ] || exit 0
[ -x "venv/bin/python" ] || exit 0

output=$(venv/bin/python -m pytest tests/regression/test_docs_sync.py -q 2>&1)
if [ $? -ne 0 ]; then
    echo "⚠️  Docs out of sync with code (test_docs_sync.py):" >&2
    echo "$output" | grep -E "AssertionError|claims|FAILED" | head -6 >&2
    echo "→ update README.md / AGENTS.md / docs/architecture.md" >&2
    exit 1
fi
exit 0
