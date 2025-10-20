# Version Management Guide

This project uses [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`

- **MAJOR**: Breaking changes (e.g., incompatible API changes)
- **MINOR**: New features (backwards-compatible)
- **PATCH**: Bug fixes (backwards-compatible)

## Quick Start

### Bump Version (Recommended Method)

Use the automated script:

```bash
# Patch release (1.2.0 → 1.2.1)
./scripts/bump_version.sh patch "Fix stream resolution bug"

# Minor release (1.2.0 → 1.3.0)
./scripts/bump_version.sh minor "Add radio search feature"

# Major release (1.2.0 → 2.0.0)
./scripts/bump_version.sh major "Redesign API"
```

This will:
1. Update `pyproject.toml`
2. Update `ytmpd/__init__.py`
3. Create a commit
4. Create a git tag (`vX.Y.Z`)

Then push:
```bash
git push && git push --tags
```

### Manual Version Bump

If you prefer to do it manually:

1. Update version in `pyproject.toml`
2. Update `__version__` in `ytmpd/__init__.py`
3. Commit: `git commit -m "Bump version to X.Y.Z"`
4. Tag: `git tag -a vX.Y.Z -m "Release version X.Y.Z"`
5. Push: `git push && git push --tags`

### Check Version Sync

```bash
./scripts/check_version_sync.sh
```

Returns exit code 0 if versions match, 1 if they don't.

## Version Sources

The version is stored in two places:

1. **`pyproject.toml`** (source of truth for packaging)
   ```toml
   version = "1.2.0"
   ```

2. **`ytmpd/__init__.py`** (programmatic access)
   ```python
   __version__ = "1.2.0"
   ```

Both must always match!

## Automated Checks

### Pre-commit Hook (Optional)

Install pre-commit hooks to automatically check version sync:

```bash
pip install pre-commit
pre-commit install
```

Now the version check runs before every commit.

### CI Check (Future)

Add to your CI pipeline:
```yaml
- name: Check version sync
  run: ./scripts/check_version_sync.sh
```

## Reading Version in Code

```python
from ytmpd import __version__
print(f"ytmpd version: {__version__}")
```

Or dynamically from installed package:
```python
from importlib.metadata import version
print(f"ytmpd version: {version('ytmpd')}")
```

## Release Checklist

- [ ] Run tests: `pytest`
- [ ] Update CHANGELOG (if you have one)
- [ ] Bump version: `./scripts/bump_version.sh <type> "message"`
- [ ] Push: `git push && git push --tags`
- [ ] Create GitHub release (optional)
- [ ] Publish to PyPI (optional): `python -m build && twine upload dist/*`

## Common Scenarios

### Hotfix on Released Version

```bash
# Fix the bug
git add .
./scripts/bump_version.sh patch "Fix critical bug in stream resolver"
git push && git push --tags
```

### Feature Release

```bash
# Add the feature
git add .
./scripts/bump_version.sh minor "Add support for playlist radio"
git push && git push --tags
```

### After Forgetting to Bump

If you forgot to bump and already committed:

```bash
# Update versions
./scripts/bump_version.sh patch "Forgot to bump version"
# This creates a new commit with the version bump
```
