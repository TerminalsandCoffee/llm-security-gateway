#!/usr/bin/env bash
# Build Lambda deployment package (deployment.zip)
# Usage: bash scripts/package.sh
#
# Creates a zip with:
# - Python dependencies installed to package/
# - src/ application code
# - Outputs deployment.zip in project root

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/.build"
OUTPUT="$PROJECT_ROOT/deployment.zip"

echo "==> Cleaning previous build..."
rm -rf "$BUILD_DIR" "$OUTPUT"
mkdir -p "$BUILD_DIR"

echo "==> Installing dependencies..."
pip install \
    --target "$BUILD_DIR" \
    --platform manylinux2014_x86_64 \
    --implementation cp \
    --python-version 3.12 \
    --only-binary=:all: \
    -r "$PROJECT_ROOT/requirements.txt" \
    --quiet

echo "==> Copying application code..."
cp -r "$PROJECT_ROOT/src" "$BUILD_DIR/src"

echo "==> Creating deployment.zip..."
cd "$BUILD_DIR"
zip -r "$OUTPUT" . -x "*.pyc" "__pycache__/*" "*.dist-info/*" "bin/*" -q

echo "==> Cleaning build directory..."
rm -rf "$BUILD_DIR"

SIZE=$(du -h "$OUTPUT" | cut -f1)
echo "==> Done: deployment.zip ($SIZE)"
