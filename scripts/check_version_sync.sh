#!/bin/bash
# Check that versions are in sync across pyproject.toml and __init__.py
#
# Usage: ./scripts/check_version_sync.sh
# Returns: 0 if in sync, 1 if not

set -e

PYPROJECT_VERSION=$(grep -E '^version = ' pyproject.toml | cut -d'"' -f2)
INIT_VERSION=$(grep -E '__version__ = ' ytmpd/__init__.py | cut -d'"' -f2)

echo "pyproject.toml: $PYPROJECT_VERSION"
echo "__init__.py:    $INIT_VERSION"

if [ "$PYPROJECT_VERSION" = "$INIT_VERSION" ]; then
    echo "✓ Versions are in sync"
    exit 0
else
    echo "✗ Version mismatch!"
    exit 1
fi
