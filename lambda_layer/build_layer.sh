#!/bin/bash

# Build Lambda Layer for Strava AI Boost
# This script creates a clean Lambda Layer with all dependencies

set -e

echo "🔧 Building Lambda Layer for Strava AI Boost..."

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Clean previous build
rm -rf "$SCRIPT_DIR/python/"
mkdir -p "$SCRIPT_DIR/python"

# Install dependencies in the layer
echo "📦 Installing dependencies..."
pip install -r "$SCRIPT_DIR/requirements.txt" -t "$SCRIPT_DIR/python/" --platform linux_x86_64 --only-binary=:all:

# Clean up unnecessary files
echo "🧹 Cleaning up unnecessary files..."
find "$SCRIPT_DIR/python/" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$SCRIPT_DIR/python/" -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
find "$SCRIPT_DIR/python/" -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
find "$SCRIPT_DIR/python/" -type f -name "*.pyc" -delete 2>/dev/null || true
find "$SCRIPT_DIR/python/" -type f -name "*.pyo" -delete 2>/dev/null || true

# Create zip file for layer
echo "📦 Creating layer zip file..."
cd "$SCRIPT_DIR/python"
zip -r "../strava-ai-boost-dependencies-layer.zip" . -q
cd "$SCRIPT_DIR"

echo "✅ Lambda Layer built successfully!"
echo "📁 Layer zip: $SCRIPT_DIR/strava-ai-boost-dependencies-layer.zip"
echo "📊 Layer size: $(du -h "$SCRIPT_DIR/strava-ai-boost-dependencies-layer.zip" | cut -f1)"