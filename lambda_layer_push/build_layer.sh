#!/bin/bash

# Build the Web Push Lambda layer (pywebpush + its compiled deps).
# Run before `cdk deploy` when push is enabled.

set -e

echo "🔧 Building Web Push Lambda layer..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

rm -rf "$SCRIPT_DIR/python/"
mkdir -p "$SCRIPT_DIR/python"

# cryptography and cffi are compiled: install the wheels built for the Lambda
# runtime (CPython 3.12, x86_64, manylinux) rather than the build host's.
# --only-binary=:all: fails loudly if a wheel is missing for that target.
pip install \
    --platform manylinux2014_x86_64 \
    --python-version 3.12 \
    --implementation cp \
    --only-binary=:all: \
    -r "$SCRIPT_DIR/requirements.txt" \
    -t "$SCRIPT_DIR/python/"

find "$SCRIPT_DIR/python" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

echo "✅ Web Push layer built in $SCRIPT_DIR/python"
