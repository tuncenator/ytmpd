# i3blocks `ytmpd-status` widget restyle

**Date:** 2026-04-21
**Branch:** `feature/status-widget-restyle`

## Context

The `bin/ytmpd-status` script renders an MPD-playback widget for i3blocks. Its default palette uses harsh RGB primaries (`#00FF00`, `#FFFF00`, `#FF0000`) that clash with the refined neighbor widgets in the bottom bar (`#b0235c` raspberry, `#2eec99` mint, `#ff3366` pink). It also uses two different progress-bar glyph families (`█░` for local, `▰▱` for YouTube) — adding visual noise when color already signals track type.

This spec redefines the defaults to a Tokyonight-adjacent cyan/pink palette and unifies the bar glyph. No behavioral or feature changes.

## Design

### Palette

Warm = YouTube, cool = local. Deeper hue indicates paused.

| State | Hex |
|---|---|
| YouTube playing | `#f7768e` |
| YouTube paused | `#d9677b` |
| Local playing | `#7dcfff` |
| Local paused | `#5ab3dd` |
| Stopped | `#565f89` |
| Auth invalid | `#ff5577` |
| Auth refresh failing | `#e0af68` |

### Progress bar

Always render with `blocks` style (`█` filled, `░` empty). The YT-vs-local glyph distinction is removed — color alone signals track type.

### Scope of code change (`bin/ytmpd-status`)

1. Update the five `--color-*` argparse defaults (in `parse_arguments`) to the new palette values.
2. Replace hardcoded `#FF0000` (auth invalid) with `#ff5577` and `#FFA500` (refresh failing) with `#e0af68` at every occurrence in `main()` and any other callers.
3. In the three bar-style auto-detect sites (`display_status` and `main`), replace `"smooth" if track_type == "youtube" else "blocks"` with a plain `"blocks"`.
4. Update the module docstring's "Color Codes" and "Progress Bar Styles" sections to match the new defaults.

### Out of scope

- No new CLI flags, env vars, or config formats.
- No logic changes (auth polling, MPD interaction, click handling, truncation, playlist context — all untouched).
- The `bar_style` CLI argument still accepts `blocks | smooth | simple | auto`, so a user who wants `smooth` can still pass `--bar-style smooth`. Only the `auto` branch is simplified.
- `bin/ytmpd-status-preview` stays as a standalone exploration tool; it is not wired into the widget.

## Success criteria

- Run `/home/tunc/Sync/Programs/ytmpd/bin/ytmpd-status` with no args and visually confirm the new colors.
- Trigger playing and paused states for both YouTube and local tracks; each state displays its intended color from the table above.
- Confirm the progress bar uses `█░` for both track types.
- Confirm `--bar-style smooth` still produces `▰▱` (CLI override path preserved).
- `i3blocks` bottom bar renders the widget harmoniously alongside existing neighbors (visual judgment).

## Files touched

- `bin/ytmpd-status` — palette and bar defaults (this is the sole code change)
- `bin/ytmpd-status-preview` — already added in this branch; kept as-is for future palette iteration
