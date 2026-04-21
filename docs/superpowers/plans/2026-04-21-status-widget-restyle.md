# i3blocks `ytmpd-status` widget restyle — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reskin the `bin/ytmpd-status` i3blocks widget with a Tokyonight-adjacent cyan/pink palette and unify the progress bar glyph to `█░` for both YouTube and local tracks.

**Architecture:** Pure default-value change — no new features, flags, or logic branches. Updates argparse defaults (palette), hardcoded hex strings in auth-error branches, the docstring's "Color Codes" section, and the auto-bar-style branch (three sites) to always return `"blocks"`. Existing tests that hardcode the old defaults are updated to match; no new test files.

**Tech Stack:** Python 3, pytest. Worktree uses the main checkout's venv:
`/home/tunc/Sync/Programs/ytmpd/.venv/bin/pytest`. Tests load `bin/ytmpd-status` by path from the worktree root — so running pytest from the worktree picks up the correct script.

**Worktree:** `~/.config/superpowers/worktrees/ytmpd/status-widget-restyle/`
**Branch:** `feature/status-widget-restyle`

---

## Palette reference (new defaults)

| State | Old | New |
|---|---|---|
| YouTube playing | `#FF6B35` | `#f7768e` |
| YouTube paused | `#FFB84D` | `#d9677b` |
| Local playing | `#00FF00` | `#7dcfff` |
| Local paused | `#FFFF00` | `#5ab3dd` |
| Stopped | `#808080` | `#565f89` |
| Auth invalid | `#FF0000` | `#ff5577` |
| Auth refresh failing | `#FFA500` | `#e0af68` |

---

### Task 1: Commit the design spec and preview tooling

The worktree currently has two new untracked files produced during brainstorming:
- `bin/ytmpd-status-preview` — standalone 256-color ANSI preview for palette/bar iteration
- `docs/superpowers/specs/2026-04-21-status-widget-restyle-design.md` — the approved design spec
- `docs/superpowers/plans/2026-04-21-status-widget-restyle.md` — this plan

Commit them first so the repo has a clean "design in place, implementation pending" checkpoint.

**Files:**
- Add: `bin/ytmpd-status-preview`
- Add: `docs/superpowers/specs/2026-04-21-status-widget-restyle-design.md`
- Add: `docs/superpowers/plans/2026-04-21-status-widget-restyle.md`

- [ ] **Step 1: Verify untracked files are all expected**

Run (from the worktree root):
```bash
cd ~/.config/superpowers/worktrees/ytmpd/status-widget-restyle
git status --short
```

Expected output (order may differ):
```
?? bin/ytmpd-status-preview
?? docs/superpowers/plans/2026-04-21-status-widget-restyle.md
?? docs/superpowers/specs/2026-04-21-status-widget-restyle-design.md
```

If additional files appear, stop and investigate.

- [ ] **Step 2: Smoke-test the preview script**

Run:
```bash
./bin/ytmpd-status-preview --only palettes --bar blocks | head -30
```

Expected: printed output with ANSI escape sequences, no Python traceback. Confirms the script is syntactically valid and imports cleanly.

- [ ] **Step 3: Commit**

```bash
git add bin/ytmpd-status-preview docs/superpowers/specs/2026-04-21-status-widget-restyle-design.md docs/superpowers/plans/2026-04-21-status-widget-restyle.md
git commit -m "chore: add status-widget-restyle design spec, plan, and preview tool

bin/ytmpd-status-preview is a standalone palette/bar-glyph preview renderer
used to validate the design before touching the live widget. It uses 24-bit
ANSI and has zero dependencies beyond stdlib.

docs/superpowers/specs/... captures the approved palette (Tokyonight
cyan/pink duo) and scope. docs/superpowers/plans/... is this implementation
plan."
```

---

### Task 2: Update test assertions to the new palette (red stage)

Replace all hardcoded old-palette hex values in test files with the new palette. After this step the tests will fail against the still-old widget code — that's the expected red state before Task 3.

**Files:**
- Modify: `tests/test_ytmpd_status_cli.py:58-62`
- Modify: `tests/test_ytmpd_status_idle.py:229-233`, `:265`, `:271`, `:285`
- Modify: `tests/test_ytmpd_status.py:268`, `:294`, `:320`, `:346`, `:361`, `:379`

- [ ] **Step 1: Update `test_ytmpd_status_cli.py` default-color assertions**

In `tests/test_ytmpd_status_cli.py`, replace the block currently at lines 58-62:

```python
            # Color defaults
            assert args.color_youtube_playing == "#FF6B35"
            assert args.color_youtube_paused == "#FFB84D"
            assert args.color_local_playing == "#00FF00"
            assert args.color_local_paused == "#FFFF00"
            assert args.color_stopped == "#808080"
```

with:

```python
            # Color defaults
            assert args.color_youtube_playing == "#f7768e"
            assert args.color_youtube_paused == "#d9677b"
            assert args.color_local_playing == "#7dcfff"
            assert args.color_local_paused == "#5ab3dd"
            assert args.color_stopped == "#565f89"
```

No other blocks in this file need changes — lines 115-126 pass `#FF0000`/`#FFFF00`/`#FF00FF` as CLI overrides (testing the override mechanism), which is unrelated to defaults. Lines 319/327/337 use `#FF6B35` as a validator input — still a valid hex string, leave untouched.

- [ ] **Step 2: Update `test_ytmpd_status_idle.py` mocks**

In `tests/test_ytmpd_status_idle.py`, change lines 229-233 from:

```python
        mock_args.color_local_playing = "#00FF00"
        mock_args.color_local_paused = "#FFFF00"
        mock_args.color_youtube_playing = "#FF6B35"
        mock_args.color_youtube_paused = "#FFB84D"
        mock_args.color_stopped = "#808080"
```

to:

```python
        mock_args.color_local_playing = "#7dcfff"
        mock_args.color_local_paused = "#5ab3dd"
        mock_args.color_youtube_playing = "#f7768e"
        mock_args.color_youtube_paused = "#d9677b"
        mock_args.color_stopped = "#565f89"
```

Then update the assertion at line 249 (same function) from:
```python
        assert "#00FF00" in captured.out
```
to:
```python
        assert "#7dcfff" in captured.out
```

Then at line 265, change:
```python
        mock_args.color_stopped = "#808080"
```
to:
```python
        mock_args.color_stopped = "#565f89"
```

At line 271, change:
```python
        assert "#808080" in captured.out
```
to:
```python
        assert "#565f89" in captured.out
```

At line 285, change:
```python
        mock_args.color_stopped = "#808080"
```
to:
```python
        mock_args.color_stopped = "#565f89"
```

- [ ] **Step 3: Update `test_ytmpd_status.py` end-to-end color assertions**

In `tests/test_ytmpd_status.py`, change these assertions:

Line 268:
```python
        assert lines[2] == "#FF6B35"  # Orange for YouTube playing
```
→
```python
        assert lines[2] == "#f7768e"  # Pink for YouTube playing
```

Line 294:
```python
        assert lines[2] == "#FFB84D"  # Light orange for YouTube paused
```
→
```python
        assert lines[2] == "#d9677b"  # Deeper pink for YouTube paused
```

Line 320:
```python
        assert lines[2] == "#00FF00"  # Green for local playing
```
→
```python
        assert lines[2] == "#7dcfff"  # Cyan for local playing
```

Line 346:
```python
        assert lines[2] == "#FFFF00"  # Yellow for local paused
```
→
```python
        assert lines[2] == "#5ab3dd"  # Deeper cyan for local paused
```

Lines 361 and 379 (both in `test_mpd_not_running` and `test_mpd_stopped`):
```python
        assert lines[2] == "#808080"  # Gray
```
→
```python
        assert lines[2] == "#565f89"  # Slate
```

- [ ] **Step 4: Run the updated tests to confirm they now fail against the old widget code**

Run:
```bash
cd ~/.config/superpowers/worktrees/ytmpd/status-widget-restyle
/home/tunc/Sync/Programs/ytmpd/.venv/bin/pytest tests/test_ytmpd_status_cli.py tests/test_ytmpd_status.py tests/test_ytmpd_status_idle.py -v 2>&1 | tail -40
```

Expected: several failures, specifically:
- `test_ytmpd_status_cli.py::TestDefaultValues::test_no_args_uses_defaults` fails on the new palette assertions
- `test_ytmpd_status.py::TestColorSelection::test_youtube_playing_color` fails asserting `#f7768e` but finding `#FF6B35`
- similar failures for `test_youtube_paused_color`, `test_local_playing_color`, `test_local_paused_color`, `test_mpd_not_running`, `test_mpd_stopped`
- `test_ytmpd_status_idle.py::...::test_display_status_local_playing` fails asserting `#7dcfff` but finding `#00FF00`

If you see failures matching this pattern, the red stage is correctly set up. Do **not** commit yet — tests must be green first.

---

### Task 3: Update widget palette defaults (green stage)

Update `bin/ytmpd-status` so the new defaults match the tests.

**Files:**
- Modify: `bin/ytmpd-status:22-27` (docstring color-codes section)
- Modify: `bin/ytmpd-status:819-845` (five argparse color defaults)
- Modify: `bin/ytmpd-status:1366`, `:1370`, `:1400`, `:1404`, `:1449`, `:1451` (six hardcoded auth-error hex values)

- [ ] **Step 1: Update docstring color table**

In `bin/ytmpd-status`, replace the block at lines 22-27:

```python
Color Codes (for i3blocks):
    YouTube Playing: #FF6B35 (orange)
    YouTube Paused: #FFB84D (light orange)
    Local Playing: #00FF00 (green)
    Local Paused: #FFFF00 (yellow)
    Stopped: #808080 (gray)
"""
```

with:

```python
Color Codes (for i3blocks):
    YouTube Playing: #f7768e (pink)
    YouTube Paused: #d9677b (deeper pink)
    Local Playing: #7dcfff (cyan)
    Local Paused: #5ab3dd (deeper cyan)
    Stopped: #565f89 (slate)
    Auth Invalid: #ff5577 (warning pink)
    Auth Refresh Failing: #e0af68 (amber)
"""
```

(Closing `"""` line is unchanged.)

- [ ] **Step 2: Update the five argparse color defaults**

In `bin/ytmpd-status`, update the `color_group` arguments in `parse_arguments()`.

At line 819:
```python
        default=os.environ.get("YTMPD_STATUS_COLOR_YOUTUBE_PLAYING", "#FF6B35"),
```
→
```python
        default=os.environ.get("YTMPD_STATUS_COLOR_YOUTUBE_PLAYING", "#f7768e"),
```

At line 820:
```python
        help="Color for YouTube playing (default: #FF6B35)",
```
→
```python
        help="Color for YouTube playing (default: #f7768e)",
```

At line 825:
```python
        default=os.environ.get("YTMPD_STATUS_COLOR_YOUTUBE_PAUSED", "#FFB84D"),
```
→
```python
        default=os.environ.get("YTMPD_STATUS_COLOR_YOUTUBE_PAUSED", "#d9677b"),
```

At line 826:
```python
        help="Color for YouTube paused (default: #FFB84D)",
```
→
```python
        help="Color for YouTube paused (default: #d9677b)",
```

At line 831:
```python
        default=os.environ.get("YTMPD_STATUS_COLOR_LOCAL_PLAYING", "#00FF00"),
```
→
```python
        default=os.environ.get("YTMPD_STATUS_COLOR_LOCAL_PLAYING", "#7dcfff"),
```

At line 832:
```python
        help="Color for local playing (default: #00FF00)",
```
→
```python
        help="Color for local playing (default: #7dcfff)",
```

At line 837:
```python
        default=os.environ.get("YTMPD_STATUS_COLOR_LOCAL_PAUSED", "#FFFF00"),
```
→
```python
        default=os.environ.get("YTMPD_STATUS_COLOR_LOCAL_PAUSED", "#5ab3dd"),
```

At line 838:
```python
        help="Color for local paused (default: #FFFF00)",
```
→
```python
        help="Color for local paused (default: #5ab3dd)",
```

At line 843:
```python
        default=os.environ.get("YTMPD_STATUS_COLOR_STOPPED", "#808080"),
```
→
```python
        default=os.environ.get("YTMPD_STATUS_COLOR_STOPPED", "#565f89"),
```

At line 844:
```python
        help="Color for stopped (default: #808080)",
```
→
```python
        help="Color for stopped (default: #565f89)",
```

Line numbers are approximate; use the exact text matches above to locate each edit.

- [ ] **Step 3: Update hardcoded auth-error hex strings**

In `bin/ytmpd-status`, there are three pairs of hardcoded `#FF0000` / `#FFA500` strings — at approximately lines 1366/1370, 1400/1404, and 1449/1451. Replace every occurrence of `#FF0000` in these auth-handling branches with `#ff5577`, and every occurrence of `#FFA500` with `#e0af68`.

Use `Edit` with `replace_all=true` for each — both strings are only used in the auth-color branches, so global replace is safe. Spot-check by running:

```bash
grep -n "#FF0000\|#FFA500\|#ff5577\|#e0af68" bin/ytmpd-status
```

Expected after replacement: three occurrences of `#ff5577`, three of `#e0af68`, zero of the old values. The existing comments beside each site (`# Red color for auth error`, `# Orange for refresh failures`, etc.) can be updated in passing but are not required to change for correctness.

- [ ] **Step 4: Run tests to verify green**

Run:
```bash
cd ~/.config/superpowers/worktrees/ytmpd/status-widget-restyle
/home/tunc/Sync/Programs/ytmpd/.venv/bin/pytest tests/test_ytmpd_status_cli.py tests/test_ytmpd_status.py tests/test_ytmpd_status_idle.py -v 2>&1 | tail -20
```

Expected: all previously failing tests from Task 2 Step 4 now pass. No regressions in other tests. Output ends with something like `N passed, M skipped`.

If any test still fails, inspect the failure — most likely either a missed hex-replacement or a typo in one of the new hex values.

- [ ] **Step 5: Commit**

```bash
git add bin/ytmpd-status tests/test_ytmpd_status_cli.py tests/test_ytmpd_status.py tests/test_ytmpd_status_idle.py
git commit -m "refactor(status): restyle i3blocks widget with Tokyonight cyan/pink palette

Replaces the harsh RGB-primary defaults with a refined Tokyonight-adjacent
palette that harmonizes with neighbor widgets in the bottom bar.

  YouTube playing  #FF6B35 -> #f7768e (pink)
  YouTube paused   #FFB84D -> #d9677b (deeper pink)
  Local playing    #00FF00 -> #7dcfff (cyan)
  Local paused     #FFFF00 -> #5ab3dd (deeper cyan)
  Stopped          #808080 -> #565f89 (slate)
  Auth invalid     #FF0000 -> #ff5577
  Auth refresh     #FFA500 -> #e0af68

Warm = YouTube, cool = local. Deeper hue indicates paused.

No behavioural changes. All --color-* CLI overrides and YTMPD_STATUS_COLOR_*
env vars still work as before; only defaults move. Existing palette tests
updated to match."
```

---

### Task 4: Unify the progress bar glyph (always `blocks` in auto mode)

Replace the three `"smooth" if track_type == "youtube" else "blocks"` auto-detect branches with a plain `"blocks"`. The `--bar-style` CLI flag and `YTMPD_STATUS_BAR_STYLE` env var still accept `smooth`, `simple`, `blocks`, `auto` — only the `auto` fallback changes.

**Files:**
- Modify: `bin/ytmpd-status:1125` (inside `display_status()`, custom-format branch)
- Modify: `bin/ytmpd-status:1471` (inside `main()`, custom-format branch)
- Modify: `bin/ytmpd-status:1525` (inside `main()`, default-format branch)

- [ ] **Step 1: Update the three auto-select sites**

In `bin/ytmpd-status`, locate each of the three sites. Each currently reads:

```python
                                style = "smooth" if track_type == "youtube" else "blocks"
```

or inline:
```python
                            else ("smooth" if track_type == "youtube" else "blocks")
```

Replace each conditional expression with the literal `"blocks"`:

At line ~1125 (inside `display_status`):
```python
                                style = "smooth" if track_type == "youtube" else "blocks"
```
→
```python
                                style = "blocks"
```

At line ~1471 (inside `main`, custom-format branch):
```python
                        style = (
                            bar_style
                            if bar_style
                            else ("smooth" if track_type == "youtube" else "blocks")
                        )
```
→
```python
                        style = bar_style if bar_style else "blocks"
```

At line ~1525 (inside `main`, default-format branch):
```python
                        if bar_style:
                            style = bar_style
                        else:
                            style = "smooth" if track_type == "youtube" else "blocks"
```
→
```python
                        if bar_style:
                            style = bar_style
                        else:
                            style = "blocks"
```

Spot-check after:
```bash
grep -n 'track_type == "youtube"' bin/ytmpd-status
```

Expected: only matches inside the color-selection if/else blocks (at lines ~1038, ~1044, ~1432, ~1438 — the palette lookup uses `track_type` and must remain intact). Zero matches referring to bar style.

- [ ] **Step 2: Update the docstring "Progress Bar Styles" section**

In `bin/ytmpd-status`, lines 17-20 currently read:

```python
Progress Bar Styles:
    blocks: █████░░░░░ (used for local tracks)
    smooth: ▰▰▰▰▰▱▱▱▱▱ (used for YouTube tracks)
    simple: #####----- (ASCII fallback)
```

Replace with:

```python
Progress Bar Styles:
    blocks: █████░░░░░ (default for all tracks)
    smooth: ▰▰▰▰▰▱▱▱▱▱ (opt-in via --bar-style smooth)
    simple: #####----- (ASCII fallback)
```

- [ ] **Step 3: Run the full test suite for the status script**

Run:
```bash
cd ~/.config/superpowers/worktrees/ytmpd/status-widget-restyle
/home/tunc/Sync/Programs/ytmpd/.venv/bin/pytest tests/test_ytmpd_status_cli.py tests/test_ytmpd_status.py tests/test_ytmpd_status_idle.py -v 2>&1 | tail -15
```

Expected: same green result as end of Task 3 (no test covers the auto-style branch directly, so no new passes or failures).

- [ ] **Step 4: Manual smoke-test against the live widget**

Run the script against the running ytmpd/MPD instance (if available):

```bash
./bin/ytmpd-status --bar-length 12 --fixed-bar-length --max-length 65 --show-position
```

Expected output shape (three lines, last is the colour):
```
▶ Artist - Title [1:23 █████░░░░░░░ 4:56] [3/42]
▶ Artist - Title [1:23 █████░░░░░░░ 4:56] [3/42]
#f7768e
```

Confirm:
- Third line is one of the new palette hexes, not the old ones.
- Middle bracketed portion uses `█`/`░` glyphs regardless of whether the current track is YT-proxied or a local file.
- `--bar-style smooth` still produces `▰▱` glyphs (quick one-shot CLI verification of the override path):
  ```bash
  ./bin/ytmpd-status --bar-style smooth --bar-length 12 --fixed-bar-length
  ```

If MPD is stopped, you'll see `⏹ Stopped` on line 1 and `#565f89` on line 3 — also valid confirmation of the restyle.

- [ ] **Step 5: Commit**

```bash
git add bin/ytmpd-status
git commit -m "refactor(status): unify progress-bar glyph to blocks for all tracks

The auto-detect branch previously picked 'smooth' (▰▱) for YouTube tracks
and 'blocks' (█░) for local tracks. Since the palette already signals
track type (warm=YT, cool=local), glyph differentiation is redundant visual
noise.

All three auto-detect sites now unconditionally return 'blocks'. The
--bar-style CLI flag and YTMPD_STATUS_BAR_STYLE env var still accept
smooth/simple/blocks/auto; only the fallback changes.

Docstring updated to match."
```

---

### Task 5: Final verification and push

- [ ] **Step 1: Run the full test suite for peace of mind**

Run:
```bash
cd ~/.config/superpowers/worktrees/ytmpd/status-widget-restyle
/home/tunc/Sync/Programs/ytmpd/.venv/bin/pytest -v 2>&1 | tail -10
```

Expected: same pass/skip counts as a clean main checkout (no new failures introduced).

- [ ] **Step 2: Inspect the branch's commit history**

Run:
```bash
git log --oneline main..HEAD
```

Expected: three commits, in order:
```
<hash> refactor(status): unify progress-bar glyph to blocks for all tracks
<hash> refactor(status): restyle i3blocks widget with Tokyonight cyan/pink palette
<hash> chore: add status-widget-restyle design spec, plan, and preview tool
```

- [ ] **Step 3: Hand off to the user**

Report to the user:
- Branch is ready at `feature/status-widget-restyle` (worktree: `~/.config/superpowers/worktrees/ytmpd/status-widget-restyle/`).
- Three commits, all tests passing.
- Next step is up to them: merge with `--no-ff` into `main`, open a PR, or review further. Do not merge or push without explicit instruction.
