# i3blocks Integration Guide for ytmpd-status

This guide explains how to integrate `ytmpd-status` with i3blocks for a dynamic music status display in your i3 window manager status bar.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Configuration](#configuration)
  - [Idle Mode (Recommended)](#idle-mode-recommended)
  - [Polling Mode](#polling-mode)
  - [Click Handlers](#click-handlers)
  - [Display Customization](#display-customization)
- [Advanced Usage](#advanced-usage)
- [Troubleshooting](#troubleshooting)
- [Performance](#performance)

---

## Overview

`ytmpd-status` is a Python script that displays MPD playback status for i3blocks, with special handling for YouTube-streamed tracks via ytmpd. It provides:

- **Idle mode**: Efficient monitoring using MPD's idle protocol (minimal CPU usage)
- **Click handlers**: Control playback directly from the status bar
- **Track classification**: Different colors/icons for YouTube vs local tracks
- **Progress bars**: Visual playback progress with multiple styles
- **Sync status**: Shows when YouTube tracks are being resolved
- **Playlist context**: Optional display of next/previous tracks

---

## Quick Start

**Minimum configuration** (add to `~/.config/i3blocks/config`):

```ini
[ytmpd-status]
command=/path/to/ytmpd-status --idle --handle-clicks
interval=persist
signal=10
```

Replace `/path/to/ytmpd-status` with the actual path to the script (e.g., `~/Sync/Programs/ytmpd/bin/ytmpd-status`).

Reload i3blocks:
```bash
pkill -SIGUSR1 i3blocks
```

---

## Installation

### Prerequisites

- **i3blocks**: Status bar for i3wm
- **MPD**: Music Player Daemon (running on port 6601 by default for ytmpd)
- **python-mpd2**: Python library for MPD (installed with ytmpd)
- **ytmpd**: For YouTube track streaming (optional, works with regular MPD too)

### Steps

1. **Ensure ytmpd-status is executable**:
   ```bash
   chmod +x ~/Sync/Programs/ytmpd/bin/ytmpd-status
   ```

2. **Test the script manually**:
   ```bash
   ~/Sync/Programs/ytmpd/bin/ytmpd-status
   ```

   You should see output like:
   ```
   ▶ Artist Name - Song Title ▰▰▰▰▱▱▱▱▱▱ 2:30/5:00]
   ▶ Artist Name - Song Title ▰▰▰▰▱▱▱▱▱▱ 2:30/5:00]
   #FF6B35
   ```

3. **Add to i3blocks config** (see [Configuration](#configuration))

4. **Reload i3blocks**:
   ```bash
   pkill -SIGUSR1 i3blocks
   ```

---

## Configuration

### Idle Mode (Recommended)

Idle mode runs continuously and updates automatically when MPD state changes. This is the most efficient approach.

**Basic idle mode**:
```ini
[ytmpd-status]
command=/path/to/ytmpd-status --idle --handle-clicks
interval=persist
signal=10
markup=none
```

**With display options**:
```ini
[ytmpd-status]
command=/path/to/ytmpd-status --idle --handle-clicks --bar-length 15 --show-next
interval=persist
signal=10
markup=none
```

**Compact mode**:
```ini
[ytmpd-status]
command=/path/to/ytmpd-status --idle --handle-clicks --compact
interval=persist
signal=10
markup=none
```

### Polling Mode

Polling mode runs the script at regular intervals. Less efficient but simpler.

**Poll every 2 seconds**:
```ini
[ytmpd-status]
command=/path/to/ytmpd-status --handle-clicks
interval=2
signal=10
markup=none
```

**Poll every 5 seconds** (lower CPU usage):
```ini
[ytmpd-status]
command=/path/to/ytmpd-status --handle-clicks
interval=5
signal=10
markup=none
```

### Click Handlers

Click handlers require the `--handle-clicks` flag. They work in both idle and polling modes.

**Supported actions**:
- **Left click (button 1)**: Toggle play/pause
- **Middle click (button 2)**: Stop playback
- **Scroll up (button 4)**: Next track
- **Scroll down (button 5)**: Previous track
- **Right click (button 3)**: Reserved for future use

**Example**:
```ini
[ytmpd-status]
command=/path/to/ytmpd-status --idle --handle-clicks
interval=persist
signal=10
markup=none
```

### Display Customization

#### Bar Length

Control progress bar length:
```bash
ytmpd-status --bar-length 20  # Default: 10
```

#### Bar Style

Choose progress bar style:
```bash
ytmpd-status --bar-style blocks  # █████░░░░░ (default for local)
ytmpd-status --bar-style smooth  # ▰▰▰▰▰▱▱▱▱▱ (default for YouTube)
ytmpd-status --bar-style simple  # #####----- (ASCII fallback)
ytmpd-status --bar-style auto    # Auto-detect based on track type
```

#### Hide Progress Bar

```bash
ytmpd-status --no-show-bar
```

#### Maximum Length

Control total output length:
```bash
ytmpd-status --max-length 60  # Default: 50
```

#### Show Next/Previous Tracks

```bash
ytmpd-status --show-next   # Show next track
ytmpd-status --show-prev   # Show previous track
ytmpd-status --show-next --show-prev  # Show both
```

#### Custom Format String

Complete control over output format:
```bash
ytmpd-status --format "{icon} {title} - {artist} {bar}"
ytmpd-status --format "{icon} {title} ({elapsed}/{duration})"
ytmpd-status --format "{artist} - {title} {bar} [{position}/{total}]"
```

**Available placeholders**:
- `{icon}` - Play/pause/stop icon
- `{artist}` - Track artist
- `{title}` - Track title
- `{album}` - Album name
- `{elapsed}` - Current position (MM:SS)
- `{duration}` - Total duration (MM:SS)
- `{bar}` - Progress bar
- `{position}` - Position in playlist
- `{total}` - Total tracks in playlist
- `{next}` - Next track info
- `{prev}` - Previous track info

#### Custom Colors

```bash
ytmpd-status \
  --color-youtube-playing "#FF0000" \
  --color-youtube-paused "#FFB84D" \
  --color-local-playing "#00FF00" \
  --color-local-paused "#FFFF00" \
  --color-stopped "#808080"
```

#### Custom Icons

```bash
ytmpd-status \
  --icon-playing "▶️" \
  --icon-paused "⏸️" \
  --icon-stopped "⏹️"
```

---

## Advanced Usage

### Manual Refresh

Manually trigger a refresh (useful for debugging or scripting):

```bash
pkill -RTMIN+10 ytmpd-status
```

The signal number (10) matches the `signal=` value in i3blocks config.

### Different MPD Port

If your MPD runs on a different port:

```bash
ytmpd-status --port 6600  # Default MPD port
```

### Different MPD Host

For remote MPD servers:

```bash
ytmpd-status --host 192.168.1.100 --port 6600
```

### Verbose Mode

Enable verbose output for debugging:

```bash
ytmpd-status --idle --verbose
```

View logs:
```bash
journalctl --user -f | grep ytmpd-status
```

Or redirect stderr to a file in i3blocks config:
```ini
[ytmpd-status]
command=/path/to/ytmpd-status --idle --verbose 2>>/tmp/ytmpd-status.log
interval=persist
signal=10
```

### Multiple MPD Instances

Run separate blocks for different MPD servers:

```ini
[ytmpd-main]
command=/path/to/ytmpd-status --idle --handle-clicks --port 6601
interval=persist
signal=10

[ytmpd-secondary]
command=/path/to/ytmpd-status --idle --handle-clicks --port 6602
interval=persist
signal=11
```

---

## Troubleshooting

### Block doesn't appear

1. **Check if MPD is running**:
   ```bash
   systemctl --user status mpd
   # or
   ps aux | grep mpd
   ```

2. **Test the script manually**:
   ```bash
   /path/to/ytmpd-status
   ```

3. **Check i3blocks logs**:
   ```bash
   journalctl --user -f | grep i3blocks
   ```

4. **Verify the script path is correct** in i3blocks config

### Click handlers don't work

1. **Ensure `--handle-clicks` flag is set** in i3blocks config

2. **Check `$BLOCK_BUTTON` environment variable**:
   ```bash
   BLOCK_BUTTON=1 /path/to/ytmpd-status --handle-clicks
   ```

3. **Check MPD permissions** (ensure you can control playback)

### Idle mode not updating

1. **Check if process is running**:
   ```bash
   ps aux | grep ytmpd-status
   ```

2. **Kill old instances**:
   ```bash
   pkill ytmpd-status
   pkill -SIGUSR1 i3blocks  # Reload
   ```

3. **Check MPD idle support**:
   ```bash
   mpc idle player  # Should block until playback changes
   ```

### Colors not showing

1. **Verify `markup=none`** in i3blocks config (not `markup=pango`)

2. **Check color codes** are valid `#RRGGBB` format

3. **Test color output**:
   ```bash
   /path/to/ytmpd-status | tail -n 1
   # Should output: #RRGGBB
   ```

### High CPU usage

1. **Use idle mode** instead of polling:
   ```ini
   interval=persist  # Not interval=1
   command=... --idle
   ```

2. **Increase polling interval** if not using idle mode:
   ```ini
   interval=5  # Instead of interval=1
   ```

3. **Check for runaway processes**:
   ```bash
   ps aux | grep ytmpd-status
   # Kill duplicates if found
   ```

### Connection refused

1. **Check MPD is running**:
   ```bash
   systemctl --user status mpd
   ```

2. **Verify port** (ytmpd uses 6601 by default):
   ```bash
   netstat -tlnp | grep 6601
   # or
   ss -tlnp | grep 6601
   ```

3. **Check MPD config** (`~/.config/mpd/mpd.conf`):
   ```
   bind_to_address "localhost"
   port "6601"
   ```

### Database not found

If you see "Database not available" or tracks aren't classified correctly:

1. **Ensure ytmpd is installed and configured**

2. **Check database path**:
   ```bash
   ls -la ~/.config/ytmpd/track_mapping.db
   ```

3. **Works with regular MPD too** - ytmpd database is optional

---

## Performance

### Idle Mode (Recommended)

- **CPU usage**: ~0.1% (nearly idle)
- **Memory**: ~20MB
- **Updates**: Instant (triggered by MPD events)
- **Battery impact**: Minimal

### Polling Mode

- **CPU usage**: ~0.5-2% (depends on interval)
- **Memory**: Minimal (process runs and exits)
- **Updates**: Every N seconds
- **Battery impact**: Moderate (frequent process spawning)

### Click Handlers

- **Overhead**: Negligible
- **Response time**: <50ms

### Comparison with Bash Scripts

| Metric | ytmpd-status (idle) | Old bash scripts |
|--------|---------------------|------------------|
| CPU usage | ~0.1% | ~2-5% |
| Memory | ~20MB | ~5MB (but multiple processes) |
| Update latency | <50ms | 1-5 seconds |
| Click support | Yes | No |
| Code maintainability | High | Low |

---

## Example Configurations

### Minimal (Display Only)

```ini
[ytmpd-status]
command=/path/to/ytmpd-status --idle
interval=persist
signal=10
```

### Full Featured

```ini
[ytmpd-status]
command=/path/to/ytmpd-status --idle --handle-clicks --show-next --bar-length 15
interval=persist
signal=10
markup=none
```

### Custom Format

```ini
[ytmpd-status]
command=/path/to/ytmpd-status --idle --handle-clicks --format "{icon} {title} {bar}"
interval=persist
signal=10
markup=none
```

### Compact with Colors

```ini
[ytmpd-status]
command=/path/to/ytmpd-status --idle --handle-clicks --compact \
  --color-youtube-playing "#FF6B35" \
  --color-local-playing "#00FF00"
interval=persist
signal=10
markup=none
```

---

## See Also

- `ytmpd-status --help` - Complete list of command-line arguments
- `examples/i3blocks.conf` - Additional configuration examples
- i3blocks documentation: https://github.com/vivien/i3blocks
- MPD documentation: https://www.musicpd.org/doc/
- ytmpd documentation: See main README

---

## Support

For issues or questions:
1. Check this troubleshooting guide
2. Run with `--verbose` to see detailed logs
3. Check MPD logs: `journalctl --user -xe -u mpd`
4. File an issue on GitHub (if applicable)
