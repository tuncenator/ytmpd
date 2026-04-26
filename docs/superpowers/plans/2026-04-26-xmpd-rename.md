# xmpd Rename Implementation Plan (Phase A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename `ytmpd` → `xmpd` end-to-end, push to a new GitHub repo with full git history preserved, archive the old repo with a redirect notice.

**Architecture:** Clone the existing `ytmpd` repo to a new local working directory `xmpd`, perform a single mechanical rename commit (covering Python package, CLI binaries, systemd unit, config-dir defaults, docs, examples, and the airplay-bridge source marker), push to new GitHub remote `tuncenator/xmpd`, then archive `tuncenator/ytmpd` with a notice in its README.

**Tech Stack:** git, gh CLI, sed, bash, pytest (for verification only — no new tests in this phase).

**Reference spec:** `docs/superpowers/specs/2026-04-26-xmpd-tidal-design.md` (Phase A section).

**Working directories:**
- Old (read source from here, archive at end): `~/Sync/Programs/ytmpd/`
- New (all work happens here after Task 3): `~/Sync/Programs/xmpd/`

**Commit strategy:** This phase produces exactly ONE commit on the new `xmpd` repo (the rename) and ONE commit on the old `ytmpd` repo (the archive notice). Tasks 4–18 modify the working tree; Task 19 commits the entire result as a single change. Do NOT commit intermediate tasks.

---

## Pre-flight tasks

### Task 1: Verify prerequisite state in old repo

**Files:**
- Inspect: `~/Sync/Programs/ytmpd/`

- [ ] **Step 1: Verify on main and clean**

```bash
cd ~/Sync/Programs/ytmpd
git status -sb
git rev-parse --abbrev-ref HEAD
```

Expected output:
```
## main...origin/main
main
```

If not on `main` or there are uncommitted changes, STOP and resolve before continuing.

- [ ] **Step 2: Verify gh authenticated and repo reachable**

```bash
gh auth status
gh repo view tuncenator/ytmpd --json name
```

Expected: `{"name":"ytmpd"}` and gh shows authenticated.

- [ ] **Step 3: Verify pytest passes on current code**

```bash
cd ~/Sync/Programs/ytmpd
source .venv/bin/activate 2>/dev/null || true
pytest -q
```

Expected: all tests pass. This baseline is what we'll re-verify after the rename.

If tests fail here, STOP. The rename should not be done on a broken state.

### Task 2: Clean up dead worktree and drop superseded branch

**Files:**
- Modify: git worktree state

- [ ] **Step 1: Prune the prunable status-widget-restyle worktree**

```bash
cd ~/Sync/Programs/ytmpd
git worktree list
git worktree prune
git worktree list
```

Expected: the `~/.config/superpowers/worktrees/ytmpd/status-widget-restyle [prunable]` entry disappears after prune.

- [ ] **Step 2: Drop the refactor/icy-refactor branch (superseded planning docs)**

```bash
cd ~/Sync/Programs/ytmpd
git branch -D refactor/icy-refactor
```

Expected: `Deleted branch refactor/icy-refactor`. The branch only contained planning docs subsumed by the new spec; no useful code is lost.

- [ ] **Step 3: Optional cleanup of stale-merged feature branches**

These are local-only refs whose content is already on main. Safe to delete.

```bash
cd ~/Sync/Programs/ytmpd
for b in feature/auto-auth feature/history-reporting feature/i3blocks-status \
         feature/like-indicator feature/likes-dislikes feature/radio-search \
         feature/status-widget-restyle fixes/like-status; do
  git branch -d "$b" 2>/dev/null && echo "deleted $b" || echo "skipped $b"
done
```

Expected: most show `deleted`; some may show `skipped` if `git branch -d` refuses (run `git branch -D <name>` to force if confident). This task is optional housekeeping; the rename works either way.

---

## Clone to new working directory

### Task 3: Clone ytmpd into ~/Sync/Programs/xmpd

**Files:**
- Create: `~/Sync/Programs/xmpd/` (full clone)

- [ ] **Step 1: Clone the local ytmpd repo to a new location**

```bash
cd ~/Sync/Programs
git clone ytmpd xmpd
cd xmpd
```

Expected: `Cloning into 'xmpd'...` then `done.` The new directory contains a full copy with `.git/`.

- [ ] **Step 2: Verify the clone has correct history**

```bash
git log --oneline -5
```

Expected: the same 5 most recent commits as `~/Sync/Programs/ytmpd/`. Top commit should be `fd9f3c5 Merge feature/local-album-art` (or whatever the current HEAD of ytmpd is).

- [ ] **Step 3: Detach from old origin**

```bash
git remote -v
git remote remove origin
git remote -v
```

Expected: after removal, `git remote -v` prints nothing. The new working dir has no remote yet.

---

## Mechanical renames (Tasks 4–18)

All operations modify the working tree without committing. The single commit happens in Task 19.

### Task 4: git mv top-level package, binaries, and service

**Files:**
- Rename: `ytmpd/` → `xmpd/`
- Rename: `bin/ytmpctl` → `bin/xmpctl`
- Rename: `bin/ytmpd-status` → `bin/xmpd-status`
- Rename: `bin/ytmpd-status-preview` → `bin/xmpd-status-preview`
- Rename: `ytmpd.service` → `xmpd.service`

- [ ] **Step 1: Run the renames**

```bash
cd ~/Sync/Programs/xmpd
git mv ytmpd xmpd
git mv bin/ytmpctl bin/xmpctl
git mv bin/ytmpd-status bin/xmpd-status
git mv bin/ytmpd-status-preview bin/xmpd-status-preview
git mv ytmpd.service xmpd.service
```

Expected: no errors. Each command silently moves the file.

- [ ] **Step 2: Verify status shows the renames**

```bash
git status -s
```

Expected: many lines like `R  ytmpd/foo.py -> xmpd/foo.py`, plus `R  bin/ytmpctl -> bin/xmpctl` etc. No `??` (untracked) entries from this step.

### Task 5: Delete superseded artifacts

**Files:**
- Delete: `ytmpd.egg-info/` (regenerates on install)
- Delete: `docs/agent/icy-refactor/` (superseded planning docs)
- Delete: `docs/ICY_PROXY.md` (will be replaced by `docs/STREAM_PROXY.md` in plan 2)

- [ ] **Step 1: Remove egg-info and superseded docs**

```bash
cd ~/Sync/Programs/xmpd
git rm -rf ytmpd.egg-info
git rm -rf docs/agent/icy-refactor
git rm docs/ICY_PROXY.md
```

Expected: each command prints `rm '<path>'` lines. No errors.

- [ ] **Step 2: Verify removal**

```bash
ls ytmpd.egg-info docs/agent/icy-refactor docs/ICY_PROXY.md 2>&1
```

Expected: three "No such file or directory" lines.

### Task 6: Update Python imports across all .py files

**Files:**
- Modify: every `*.py` file under `xmpd/`, `bin/`, `tests/`, `extras/` referencing `from ytmpd` or `import ytmpd`

- [ ] **Step 1: Run sed across all relevant Python files**

```bash
cd ~/Sync/Programs/xmpd
find . -path ./.git -prune -o \
       -path ./.venv -prune -o \
       -path ./htmlcov -prune -o \
       -path ./.mypy_cache -prune -o \
       -path ./.pytest_cache -prune -o \
       -path ./.ruff_cache -prune -o \
       -path ./MagicMock -prune -o \
       -path ./xmpd.egg-info -prune -o \
       -name '*.py' -print | \
xargs sed -i \
  -e 's/\bfrom ytmpd\b/from xmpd/g' \
  -e 's/\bimport ytmpd\b/import xmpd/g'
```

- [ ] **Step 2: Verify no `ytmpd` imports remain**

```bash
grep -rn "from ytmpd\|import ytmpd" --include='*.py' . 2>/dev/null
```

Expected: no output (zero matches).

### Task 7: Update string-literal `ytmpd` references in source code

**Files:**
- Modify: `xmpd/*.py` source files where `ytmpd` appears as a literal string

- [ ] **Step 1: Identify candidate occurrences for review**

```bash
cd ~/Sync/Programs/xmpd
grep -rn "ytmpd\|YTMPD" --include='*.py' xmpd/ bin/ extras/ 2>/dev/null
```

Expected: a list of remaining `ytmpd` string-literal occurrences. These typically include log message prefixes, default config-path strings, User-Agents, and module docstrings.

- [ ] **Step 2: Replace `ytmpd` strings in xmpd/ source files**

Use word-boundary sed to replace `ytmpd` (lowercase) with `xmpd` in source files. The replacement is safe because `ytmpd` does not appear as a substring of any other meaningful identifier.

```bash
cd ~/Sync/Programs/xmpd
find xmpd bin extras -name '*.py' -print0 | \
xargs -0 sed -i \
  -e 's/\bytmpd\b/xmpd/g' \
  -e 's/\bYTMPD\b/XMPD/g'
```

- [ ] **Step 3: Replace path-strings `~/.config/ytmpd/` with `~/.config/xmpd/`**

```bash
cd ~/Sync/Programs/xmpd
find xmpd bin extras tests examples docs \
     -type f \( -name '*.py' -o -name '*.sh' -o -name '*.toml' -o -name '*.service' -o -name '*.yaml' -o -name '*.md' -o -name '*.conf' \) \
     -print0 | \
xargs -0 sed -i \
  -e 's|~/.config/ytmpd/|~/.config/xmpd/|g' \
  -e 's|/.config/ytmpd/|/.config/xmpd/|g' \
  -e 's|ytmpd\.log|xmpd.log|g'
```

- [ ] **Step 4: Verify no stale ytmpd path references remain in source**

```bash
grep -rn "\.config/ytmpd\|ytmpd\.log" \
  --include='*.py' --include='*.sh' --include='*.toml' --include='*.service' \
  --include='*.yaml' --include='*.md' --include='*.conf' \
  xmpd bin extras tests examples docs 2>/dev/null
```

Expected: no output.

### Task 8: Update tests/ for renamed identifiers and paths

**Files:**
- Modify: `tests/**/*.py`

- [ ] **Step 1: Apply same string sed to tests directory**

```bash
cd ~/Sync/Programs/xmpd
find tests -name '*.py' -print0 | \
xargs -0 sed -i \
  -e 's/\bytmpd\b/xmpd/g' \
  -e 's/\bYTMPD\b/XMPD/g' \
  -e 's|~/.config/ytmpd/|~/.config/xmpd/|g'
```

- [ ] **Step 2: Rename test files whose names embed ytmpd**

```bash
cd ~/Sync/Programs/xmpd
git mv tests/test_ytmpd_status_idle.py tests/test_xmpd_status_idle.py 2>/dev/null
git mv tests/test_ytmpd_status_cli.py tests/test_xmpd_status_cli.py 2>/dev/null
git mv tests/test_ytmpd_status.py tests/test_xmpd_status.py 2>/dev/null
git mv tests/test_ytmpctl.py tests/test_xmpctl.py 2>/dev/null
git mv tests/integration/test_ytmpd_status_integration.py tests/integration/test_xmpd_status_integration.py 2>/dev/null
ls tests/test_xmpd_status*.py tests/test_xmpctl.py tests/integration/test_xmpd_status_integration.py
```

Expected: the five renamed test files exist under their new names. Any 2>/dev/null silenced errors mean the file already had the new name or doesn't exist; Step 3 verifies the final state.

- [ ] **Step 3: Verify no test file still has ytmpd in its name**

```bash
find tests -name '*ytmpd*' -o -name '*ytmpctl*'
```

Expected: no output.

### Task 9: Update pyproject.toml

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Read current state**

```bash
cd ~/Sync/Programs/xmpd
cat pyproject.toml
```

Note the current `name`, `[project.scripts]` entries, and any other `ytmpd` references.

- [ ] **Step 2: Replace package name and script entries**

```bash
cd ~/Sync/Programs/xmpd
sed -i \
  -e 's/^name = "ytmpd"$/name = "xmpd"/' \
  -e 's/^ytmpctl = "ytmpd\./xmpctl = "xmpd./' \
  -e 's/ytmpd-status = "ytmpd\./xmpd-status = "xmpd./' \
  -e 's/ytmpd-status-preview = "ytmpd\./xmpd-status-preview = "xmpd./' \
  -e 's/^\[project\.scripts\]$/[project.scripts]/' \
  pyproject.toml
```

If the existing pyproject.toml uses different syntax for entry points (e.g., `python -m ytmpd`), adjust the sed accordingly after reading the file.

- [ ] **Step 3: Verify pyproject.toml has no `ytmpd` left**

```bash
grep -n "ytmpd" pyproject.toml
```

Expected: no output. If anything remains, edit by hand.

### Task 10: Rewrite xmpd.service

**Files:**
- Modify: `xmpd.service`

- [ ] **Step 1: Read current state**

```bash
cd ~/Sync/Programs/xmpd
cat xmpd.service
```

- [ ] **Step 2: Replace ytmpd references**

```bash
cd ~/Sync/Programs/xmpd
sed -i \
  -e 's|YouTube Music MPD daemon|Multi-source music daemon (xmpd)|g' \
  -e 's|github.com/tuncenator/ytmpd|github.com/tuncenator/xmpd|g' \
  -e 's|/path/to/ytmpd/|/path/to/xmpd/|g' \
  -e 's|python -m ytmpd|python -m xmpd|g' \
  -e 's|%h/.config/ytmpd|%h/.config/xmpd|g' \
  xmpd.service
```

- [ ] **Step 3: Verify**

```bash
grep -n "ytmpd" xmpd.service
cat xmpd.service
```

Expected first command: no output. Expected `cat`: a unit file describing `Multi-source music daemon (xmpd)` that points at `python -m xmpd` with `ReadWritePaths=%h/.config/xmpd %h/Music`.

### Task 11: Update install.sh and uninstall.sh

**Files:**
- Modify: `install.sh`, `uninstall.sh`

- [ ] **Step 1: Apply identifier sed to both scripts**

```bash
cd ~/Sync/Programs/xmpd
sed -i \
  -e 's/\bytmpd\b/xmpd/g' \
  -e 's/\bYTMPD\b/XMPD/g' \
  -e 's/\bytmpctl\b/xmpctl/g' \
  -e 's/ytmpd-status/xmpd-status/g' \
  install.sh uninstall.sh
```

- [ ] **Step 2: Verify no stale references**

```bash
grep -nE "\bytmpd\b|\bytmpctl\b|ytmpd-status" install.sh uninstall.sh
```

Expected: no output.

- [ ] **Step 3: Make sure install.sh remains executable**

```bash
ls -l install.sh uninstall.sh
chmod +x install.sh uninstall.sh
```

Expected: both files have executable permission.

### Task 12: Update bin/ scripts

**Files:**
- Modify: `bin/xmpctl`, `bin/xmpd-status`, `bin/xmpd-status-preview`

- [ ] **Step 1: Run sed on bin scripts**

```bash
cd ~/Sync/Programs/xmpd
sed -i \
  -e 's/\bfrom ytmpd\b/from xmpd/g' \
  -e 's/\bimport ytmpd\b/import xmpd/g' \
  -e 's/\bytmpd\b/xmpd/g' \
  -e 's/\bYTMPD\b/XMPD/g' \
  -e 's/\bytmpctl\b/xmpctl/g' \
  -e 's/ytmpd-status/xmpd-status/g' \
  bin/xmpctl bin/xmpd-status bin/xmpd-status-preview
```

- [ ] **Step 2: Verify**

```bash
grep -nE "\bytmpd\b|\bytmpctl\b" bin/xmpctl bin/xmpd-status bin/xmpd-status-preview
```

Expected: no output.

- [ ] **Step 3: Ensure executable**

```bash
chmod +x bin/xmpctl bin/xmpd-status bin/xmpd-status-preview
ls -l bin/
```

### Task 13: Update README.md

**Files:**
- Modify: `README.md`

This is a partial update for plan 1. Plan 2 will rewrite the README for the multi-source story. For now, change identifier references and update the title to reflect the rename, leaving the YT-only description intact. The provider abstraction and Tidal sections come later.

- [ ] **Step 1: Apply identifier sed**

```bash
cd ~/Sync/Programs/xmpd
sed -i \
  -e 's/\bytmpd\b/xmpd/g' \
  -e 's/\bYTMPD\b/XMPD/g' \
  -e 's/\bytmpctl\b/xmpctl/g' \
  -e 's/ytmpd-status/xmpd-status/g' \
  -e 's|github.com/tuncenator/ytmpd|github.com/tuncenator/xmpd|g' \
  README.md
```

- [ ] **Step 2: Update the title manually if needed**

If the title reads `# ytmpd — YouTube Music → MPD sync daemon`, the sed above turns it into `# xmpd — YouTube Music → MPD sync daemon`. That's fine for now (still accurate; multi-source comes in plan 2).

```bash
head -3 README.md
```

Expected: title line says `xmpd`; subtitle still references YouTube Music. OK.

- [ ] **Step 3: Verify**

```bash
grep -nE "\bytmpd\b|\bytmpctl\b" README.md
```

Expected: no output.

### Task 14: Update CHANGELOG.md

**Files:**
- Modify: `CHANGELOG.md`

Preserve historical entries verbatim. Add a new top entry for the rename. Do NOT sed the historical entries.

- [ ] **Step 1: Read current top of CHANGELOG**

```bash
cd ~/Sync/Programs/xmpd
head -30 CHANGELOG.md
```

- [ ] **Step 2: Insert a new top entry**

Edit `CHANGELOG.md` and prepend a new section under the title. Use a text editor or this `cat` redirect approach (preserving existing content):

```bash
cd ~/Sync/Programs/xmpd
{
  head -1 CHANGELOG.md
  echo
  echo "## Unreleased"
  echo
  echo "### Changed"
  echo
  echo "- Project renamed from \`ytmpd\` to \`xmpd\`. The Python package, CLI"
  echo "  binaries (\`xmpctl\`, \`xmpd-status\`, \`xmpd-status-preview\`), systemd"
  echo "  unit (\`xmpd.service\`), and default config dir (\`~/.config/xmpd/\`) all"
  echo "  follow the new name. The provider abstraction and Tidal integration"
  echo "  follow in subsequent commits."
  echo
  tail -n +2 CHANGELOG.md
} > CHANGELOG.md.new && mv CHANGELOG.md.new CHANGELOG.md
```

- [ ] **Step 3: Verify entry placement and historical preservation**

```bash
head -20 CHANGELOG.md
grep -c "ytmpd v1.0.0\|Initial release" CHANGELOG.md
```

Expected: the top entry is the new "Unreleased" section. Historical "ytmpd v1.0.0 / Initial release" entries are still present (count > 0).

### Task 15: Update airplay-bridge

**Files:**
- Modify: `extras/airplay-bridge/mpd_owntone_metadata.py`
- Modify: `extras/airplay-bridge/install.sh` (if it exists and references ytmpd)
- Modify: `extras/airplay-bridge/README.md` (if it exists and references ytmpd)

The most consequential change: the User-Agent constant and the `_classify_album` source-marker string.

- [ ] **Step 1: Update User-Agent constant**

```bash
cd ~/Sync/Programs/xmpd
sed -i \
  -e 's|ytmpd-airplay-bridge/1\.0|xmpd-airplay-bridge/1.0|g' \
  -e 's|github.com/tyildirim/ytmpd|github.com/tuncenator/xmpd|g' \
  -e 's|github.com/tuncenator/ytmpd|github.com/tuncenator/xmpd|g' \
  extras/airplay-bridge/mpd_owntone_metadata.py
```

- [ ] **Step 2: Update the source-marker string in `_classify_album`**

Find the `return "ytmpd"` line in `_classify_album` and replace with `return "xmpd-yt"`. The function classifies tracks by source; this is data, not just docstring.

```bash
cd ~/Sync/Programs/xmpd
grep -n 'return "ytmpd"' extras/airplay-bridge/mpd_owntone_metadata.py
sed -i 's|return "ytmpd"|return "xmpd-yt"|g' extras/airplay-bridge/mpd_owntone_metadata.py
grep -n 'return "xmpd-yt"\|return "ytmpd"' extras/airplay-bridge/mpd_owntone_metadata.py
```

Expected: the original grep finds one line; after sed, the same line returns `"xmpd-yt"`. Plan 2 will further extend the classifier to add `"xmpd-tidal"`.

- [ ] **Step 3: Update remaining identifier-string references in airplay-bridge**

```bash
cd ~/Sync/Programs/xmpd
sed -i \
  -e 's/\bytmpd\b/xmpd/g' \
  -e 's/\bytmpctl\b/xmpctl/g' \
  extras/airplay-bridge/mpd_owntone_metadata.py
[ -f extras/airplay-bridge/install.sh ] && sed -i \
  -e 's/\bytmpd\b/xmpd/g' \
  -e 's/\bytmpctl\b/xmpctl/g' \
  extras/airplay-bridge/install.sh
[ -f extras/airplay-bridge/README.md ] && sed -i \
  -e 's/\bytmpd\b/xmpd/g' \
  -e 's/\bytmpctl\b/xmpctl/g' \
  extras/airplay-bridge/README.md
```

- [ ] **Step 4: Verify**

```bash
grep -rnE "\bytmpd\b|tyildirim" extras/airplay-bridge/
```

Expected: no output.

### Task 16: Update examples/

**Files:**
- Modify: `examples/config.yaml`, `examples/i3blocks.conf`

- [ ] **Step 1: Apply identifier sed to examples**

```bash
cd ~/Sync/Programs/xmpd
sed -i \
  -e 's/\bytmpd\b/xmpd/g' \
  -e 's/\bytmpctl\b/xmpctl/g' \
  -e 's/ytmpd-status/xmpd-status/g' \
  -e 's|~/.config/ytmpd/|~/.config/xmpd/|g' \
  examples/config.yaml examples/i3blocks.conf
```

- [ ] **Step 2: Verify**

```bash
grep -nE "\bytmpd\b|\bytmpctl\b" examples/config.yaml examples/i3blocks.conf
```

Expected: no output.

### Task 17: Update docs/

**Files:**
- Modify: `docs/i3blocks-integration.md`, `docs/MIGRATION.md`, `docs/SECURITY_FIXES.md`, `docs/version-management.md`, `docs/agent/mpd-integration/QUICKSTART.md`, prior specs in `docs/superpowers/specs/`

The historical specs in `docs/superpowers/specs/` describe past work and may legitimately reference `ytmpd`. Update path/identifier references but DO NOT alter narrative descriptions of past states.

- [ ] **Step 1: Apply identifier sed to docs**

```bash
cd ~/Sync/Programs/xmpd
find docs -name '*.md' -print0 | \
xargs -0 sed -i \
  -e 's/\bytmpctl\b/xmpctl/g' \
  -e 's/ytmpd-status/xmpd-status/g' \
  -e 's|~/.config/ytmpd/|~/.config/xmpd/|g' \
  -e 's|github.com/tuncenator/ytmpd|github.com/tuncenator/xmpd|g'
```

Note: this deliberately does NOT replace the bare `ytmpd` token in docs, preserving historical-narrative references in old specs (e.g. "ytmpd was the YT-only daemon"). Only paths, command names, and the GitHub URL are updated.

- [ ] **Step 2: Hand-update top-of-file references where needed**

Inspect the most user-facing doc:

```bash
head -10 docs/MIGRATION.md
head -10 docs/i3blocks-integration.md
```

If either has a stale top heading like `# ytmpd migration`, update it manually:

```bash
sed -i '1 s|^# ytmpd|# xmpd|' docs/MIGRATION.md docs/i3blocks-integration.md docs/version-management.md docs/SECURITY_FIXES.md docs/agent/mpd-integration/QUICKSTART.md 2>/dev/null
```

(`sed '1 s|...|...|'` only edits line 1 in each file.)

### Task 18: Update .pre-commit-config.yaml

**Files:**
- Modify: `.pre-commit-config.yaml`

- [ ] **Step 1: Read current state**

```bash
cd ~/Sync/Programs/xmpd
cat .pre-commit-config.yaml
```

- [ ] **Step 2: Replace `ytmpd` references (typically tool names that key on the package)**

```bash
cd ~/Sync/Programs/xmpd
sed -i \
  -e 's/\bytmpd\b/xmpd/g' \
  -e 's/\bytmpctl\b/xmpctl/g' \
  .pre-commit-config.yaml
```

- [ ] **Step 3: Verify**

```bash
grep -n "ytmpd\|ytmpctl" .pre-commit-config.yaml
```

Expected: no output.

---

## Verification (Tasks 19–21)

### Task 19: Final sweep — verify no stale identifiers anywhere

**Files:**
- Inspect: entire working tree

- [ ] **Step 1: Grep for any remaining lowercase `ytmpd` or `ytmpctl` tokens**

```bash
cd ~/Sync/Programs/xmpd
grep -rnE "\bytmpd\b|\bytmpctl\b" \
  --exclude-dir=.git \
  --exclude-dir=.venv \
  --exclude-dir=htmlcov \
  --exclude-dir=.mypy_cache \
  --exclude-dir=.pytest_cache \
  --exclude-dir=.ruff_cache \
  --exclude-dir=MagicMock \
  --exclude='uv.lock' \
  --exclude='.coverage' \
  . 2>/dev/null
```

Expected: occurrences only in:
- `CHANGELOG.md` (historical entries — INTENDED, "ytmpd v1.0.0" stays)
- `docs/superpowers/specs/*.md` (historical specs that described past work — INTENDED narrative)
- Any other place that explicitly describes the rename ("renamed from ytmpd")

If you find any other matches, update them and re-grep.

- [ ] **Step 2: Verify no `~/.config/ytmpd` paths remain**

```bash
cd ~/Sync/Programs/xmpd
grep -rn "config/ytmpd" \
  --exclude-dir=.git --exclude-dir=.venv --exclude-dir=htmlcov \
  --exclude='uv.lock' . 2>/dev/null
```

Expected: only matches inside narrative text in CHANGELOG / migration docs (e.g. "old config dir was `~/.config/ytmpd/`"). No active code paths reference it.

- [ ] **Step 3: Verify status looks like a clean rename**

```bash
git status -sb | head -40
git diff --shortstat
```

Expected: many modifications and renames; `(working tree clean)` is NOT expected at this stage. Numerous renames (`R `) and modifications (`M `).

### Task 20: Run pytest to verify behavior preserved

**Files:**
- Test: full suite

- [ ] **Step 1: Set up a fresh venv for the new name**

```bash
cd ~/Sync/Programs/xmpd
rm -rf .venv
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Expected: install succeeds. `pip list | grep xmpd` shows `xmpd` package installed.

- [ ] **Step 2: Run pytest**

```bash
cd ~/Sync/Programs/xmpd
source .venv/bin/activate
pytest -q 2>&1 | tail -30
```

Expected: same pass count as Task 1 step 3 (the pre-flight baseline). Any new failures must be diagnosed and fixed before commit.

- [ ] **Step 3: Run mypy and ruff if configured**

```bash
cd ~/Sync/Programs/xmpd
source .venv/bin/activate
mypy xmpd/ 2>&1 | tail -10
ruff check xmpd/ 2>&1 | tail -10
```

Expected: same warnings/errors as the original codebase (the rename should not introduce new lint or type errors). Fix any new issues introduced by the rename.

### Task 21: Smoke-test the daemon

**Files:**
- Test: actual daemon startup

- [ ] **Step 1: Stop any running ytmpd daemon (avoid socket conflicts)**

```bash
systemctl --user stop ytmpd 2>/dev/null || true
```

- [ ] **Step 2: Set up a test config dir for xmpd**

```bash
mkdir -p ~/.config/xmpd-test
cp -n ~/.config/ytmpd/config.yaml ~/.config/xmpd-test/config.yaml 2>/dev/null
cp -n ~/.config/ytmpd/browser.json ~/.config/xmpd-test/browser.json 2>/dev/null
cp -n ~/.config/ytmpd/track_mapping.db ~/.config/xmpd-test/track_mapping.db 2>/dev/null
sed -i 's|~/.config/ytmpd/|~/.config/xmpd-test/|g; s|.config/ytmpd/|.config/xmpd-test/|g' ~/.config/xmpd-test/config.yaml 2>/dev/null
```

- [ ] **Step 3: Run the new daemon briefly with the test config**

```bash
cd ~/Sync/Programs/xmpd
source .venv/bin/activate
XDG_CONFIG_HOME=~/.config XMPD_CONFIG=~/.config/xmpd-test/config.yaml \
  timeout 10 python -m xmpd 2>&1 | tail -30
```

Expected: daemon starts, logs show "Starting xmpd sync daemon..." or similar, then exits after 10 seconds (timeout). No tracebacks.

- [ ] **Step 4: Smoke-test the CLI**

```bash
cd ~/Sync/Programs/xmpd
source .venv/bin/activate
./bin/xmpctl --help 2>&1 | head -20
./bin/xmpd-status --help 2>&1 | head -20
```

Expected: both print help text without traceback.

- [ ] **Step 5: Clean up the test config**

```bash
rm -rf ~/.config/xmpd-test
```

---

## Commit and push (Tasks 22–24)

### Task 22: Single rename commit

**Files:**
- Commit: all changes accumulated in Tasks 4–18

- [ ] **Step 1: Verify the staging area**

```bash
cd ~/Sync/Programs/xmpd
git status -s | head -20
git diff --shortstat
```

Expected: many renames and modifications staged or unstaged.

- [ ] **Step 2: Stage everything**

```bash
cd ~/Sync/Programs/xmpd
git add -A
git status -s | head -20
```

Expected: all changes staged. No `??` (unstaged untracked) entries.

- [ ] **Step 3: Create the rename commit**

```bash
cd ~/Sync/Programs/xmpd
git commit -m "$(cat <<'EOF'
rename: ytmpd to xmpd for multi-source support

Mechanical rename of the Python package, CLI binaries, systemd unit,
and config dir from ytmpd to xmpd. No behavioral changes; the
provider abstraction and Tidal integration follow in subsequent commits.

- Python package: ytmpd/ to xmpd/
- CLI: ytmpctl to xmpctl
- Status: ytmpd-status to xmpd-status (and -preview)
- systemd: ytmpd.service to xmpd.service
- Default config dir: ~/.config/ytmpd/ to ~/.config/xmpd/
- airplay-bridge: User-Agent and internal source marker updated
- Drops superseded docs/agent/icy-refactor/ planning docs
- Drops docs/ICY_PROXY.md (replaced by docs/STREAM_PROXY.md in plan 2)
EOF
)"
```

Expected: commit succeeds. `git log -1 --stat | head -20` shows the rename commit at HEAD with hundreds of files touched.

- [ ] **Step 4: Verify HEAD is on top of original history**

```bash
cd ~/Sync/Programs/xmpd
git log --oneline -5
```

Expected: top entry is the new rename commit; below it, the original ytmpd commits in their original SHAs.

### Task 23: Create new GitHub repo and push

**Files:**
- Create: `tuncenator/xmpd` on GitHub
- Push: full history

- [ ] **Step 1: Create the new repo**

```bash
gh repo create tuncenator/xmpd --public \
  --description "Multi-source music daemon: syncs YouTube Music + Tidal libraries to MPD"
```

Expected: `Created repository tuncenator/xmpd on GitHub` (or similar).

- [ ] **Step 2: Add remote and push**

```bash
cd ~/Sync/Programs/xmpd
git remote add origin git@github.com:tuncenator/xmpd.git
git remote -v
git push -u origin main --tags
```

Expected: push completes; remote shows the full main history.

- [ ] **Step 3: Verify the remote state**

```bash
gh repo view tuncenator/xmpd --json name,visibility,defaultBranchRef
```

Expected: `{"name":"xmpd","visibility":"PUBLIC","defaultBranchRef":{"name":"main"}}`.

### Task 24: Update old repo's README and archive

**Files:**
- Modify: `~/Sync/Programs/ytmpd/README.md`
- Archive: `tuncenator/ytmpd` on GitHub

- [ ] **Step 1: Switch to old repo**

```bash
cd ~/Sync/Programs/ytmpd
git status -sb
```

Expected: still on main, clean.

- [ ] **Step 2: Prepend redirect notice to README**

```bash
cd ~/Sync/Programs/ytmpd
{
  echo "> **This project has moved.** ytmpd is now [xmpd](https://github.com/tuncenator/xmpd),"
  echo "> a multi-source music daemon that adds Tidal alongside YouTube Music. This repo"
  echo "> is preserved for historical reference and will not receive updates."
  echo
  cat README.md
} > README.md.new && mv README.md.new README.md
head -5 README.md
```

Expected: top three lines are the new notice, then a blank line, then the original README content (starting with `# ytmpd ...`).

- [ ] **Step 3: Commit and push**

```bash
cd ~/Sync/Programs/ytmpd
git add README.md
git commit -m "docs: project renamed to xmpd; this repo archived"
git push origin main
```

Expected: commit + push succeed.

- [ ] **Step 4: Archive the repo on GitHub**

```bash
gh repo archive tuncenator/ytmpd --yes
gh repo view tuncenator/ytmpd --json isArchived
```

Expected final output: `{"isArchived":true}`.

---

## Acceptance criteria (whole plan)

After all tasks complete, the following are true:

- `~/Sync/Programs/xmpd/` is a working clone of the renamed project. `pytest` passes. `python -m xmpd` starts successfully against a copy of the user's existing config (with `~/.config/ytmpd/` paths swapped to `~/.config/xmpd/`).
- `tuncenator/xmpd` exists on GitHub with the full git history; HEAD is the rename commit. The repo's description reflects the multi-source intent.
- `tuncenator/ytmpd` is archived. Its README has a redirect notice at the top.
- `~/Sync/Programs/ytmpd/` (local) still exists as a fallback; the user will delete it manually after confirming xmpd works in plan 2.
- The user has not yet run `install.sh` for xmpd. That happens in plan 2 (which adds the config-shape migration logic). For now, the CLI and tests work but the user's running ytmpd daemon is untouched.

The next plan (`2026-04-27-xmpd-multi-source.md`) builds on this one to add the provider abstraction, Tidal provider, AirPlay bridge updates, and install/migration polish.
