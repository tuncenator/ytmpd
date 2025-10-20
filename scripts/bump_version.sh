#!/bin/bash
# Version bump script - keeps pyproject.toml, __init__.py, and git tags in sync
#
# Usage:
#   ./scripts/bump_version.sh [major|minor|patch] "commit message"
#
# Examples:
#   ./scripts/bump_version.sh patch "Fix stream resolution bug"
#   ./scripts/bump_version.sh minor "Add radio search feature"
#   ./scripts/bump_version.sh major "Breaking API changes"

set -e

BUMP_TYPE=${1:-patch}
COMMIT_MSG=${2:-"Bump version"}

if [[ ! "$BUMP_TYPE" =~ ^(major|minor|patch)$ ]]; then
    echo "Error: First argument must be 'major', 'minor', or 'patch'"
    exit 1
fi

# Get current version from pyproject.toml
CURRENT_VERSION=$(grep -E '^version = ' pyproject.toml | cut -d'"' -f2)
echo "Current version: $CURRENT_VERSION"

# Parse version parts
IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT_VERSION"

# Bump version based on type
case $BUMP_TYPE in
    major)
        MAJOR=$((MAJOR + 1))
        MINOR=0
        PATCH=0
        ;;
    minor)
        MINOR=$((MINOR + 1))
        PATCH=0
        ;;
    patch)
        PATCH=$((PATCH + 1))
        ;;
esac

NEW_VERSION="$MAJOR.$MINOR.$PATCH"
echo "New version: $NEW_VERSION"

# Update pyproject.toml
sed -i "s/^version = \".*\"/version = \"$NEW_VERSION\"/" pyproject.toml

# Update __init__.py
sed -i "s/__version__ = \".*\"/__version__ = \"$NEW_VERSION\"/" ytmpd/__init__.py

# Verify changes
echo ""
echo "Updated files:"
git diff pyproject.toml ytmpd/__init__.py

# Stage, commit, and tag
echo ""
read -p "Commit and tag version $NEW_VERSION? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    git add pyproject.toml ytmpd/__init__.py
    git commit -m "$COMMIT_MSG

Version bumped from $CURRENT_VERSION to $NEW_VERSION"
    git tag -a "v$NEW_VERSION" -m "Release version $NEW_VERSION"
    echo ""
    echo "✓ Created commit and tag v$NEW_VERSION"
    echo ""
    echo "To push: git push && git push --tags"
else
    echo "Aborted. Changes not committed."
    git restore pyproject.toml ytmpd/__init__.py
fi
