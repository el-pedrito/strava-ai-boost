#!/bin/bash

# Build the Web Push Lambda layer (pywebpush + its compiled deps).
# Required before `cdk synth/deploy` with push_enabled=true: synth refuses an
# unbuilt layer, and scripts/deploy.sh runs this script when cdk.json enables push.

set -e

echo "🔧 Building Web Push Lambda layer..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"

rm -rf "$SCRIPT_DIR/python/"
mkdir -p "$SCRIPT_DIR/python"

WHEELHOUSE="$(mktemp -d)"
trap 'rm -rf "$WHEELHOUSE"' EXIT

# http-ece ships only a source archive, which --only-binary refuses. It is pure
# Python, so build it once into a portable py3-none-any wheel...
HTTP_ECE_PIN="$(grep -E '^http-ece==' "$REQUIREMENTS")"
pip wheel --no-deps --no-binary :all: -w "$WHEELHOUSE" "$HTTP_ECE_PIN"

# ...then install everything for the Lambda runtime (CPython 3.12, x86_64,
# manylinux). cryptography, cffi and aiohttp are compiled: --only-binary=:all:
# takes their Linux wheels instead of the build host's, and fails loudly if one
# is missing rather than silently building a host-native extension.
pip install \
    --platform manylinux2014_x86_64 \
    --python-version 3.12 \
    --implementation cp \
    --only-binary=:all: \
    --find-links "$WHEELHOUSE" \
    -r "$REQUIREMENTS" \
    -t "$SCRIPT_DIR/python/"

find "$SCRIPT_DIR/python" -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true

# Guard: every native extension must target the Lambda interpreter (cp312 or abi3)
# on Linux x86_64. A macOS or other-interpreter .so would only fail at runtime.
BAD_EXT="$(find "$SCRIPT_DIR/python" -name '*.so' \
    ! -name '*cpython-312-x86_64-linux-gnu.so' ! -name '*abi3.so' -print)"
if [ -n "$BAD_EXT" ]; then
    echo "❌ Native extensions built for the wrong platform:"
    echo "$BAD_EXT"
    exit 1
fi
if [ ! -f "$SCRIPT_DIR/python/pywebpush/__init__.py" ]; then
    echo "❌ pywebpush is missing from the built layer"
    exit 1
fi

echo "✅ Web Push layer built in $SCRIPT_DIR/python"
