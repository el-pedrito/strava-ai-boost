#!/bin/bash
# Vendor the coach streaming Lambda's pure-Python deps (Starlette + uvicorn) into
# lambda_functions/ so they ship with Code.from_asset (project convention — see
# README "Known Issue #2"). Starlette/uvicorn have no compiled extensions, so a
# plain `pip install -t` works on any platform (no Docker, no manylinux concerns).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="$ROOT/lambda_functions"
REQ="$TARGET/coach_stream/requirements.txt"

echo "Installing coach stream deps into $TARGET ..."
pip install --no-cache-dir -r "$REQ" -t "$TARGET" --upgrade

echo "Running pip-audit on vendored deps (security policy §10) ..."
if command -v pip-audit >/dev/null 2>&1; then
    pip-audit -r "$REQ" || echo "WARNING: pip-audit reported findings — review before deploy"
else
    echo "pip-audit not installed; skipping (install: pip install pip-audit)"
fi

echo "Done. Vendored: starlette, uvicorn (+ pure-python transitive deps)."
