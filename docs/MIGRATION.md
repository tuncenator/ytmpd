# Migration Guide: ytmpd v1 → v2 (MPD Integration)

This guide helps you migrate from the old ytmpd architecture (socket-based command server) to the new MPD integration architecture.

## What Changed

### Architecture

**Old (v1):**
```
ytmpctl → Unix socket → ytmpd daemon → ytmusicapi → YouTube Music
                              ↓
                        Player State
                              ↓
                        (No actual audio)
```

**New (v2):**
```
YouTube Music Playlists
         ↓
   ytmpd sync daemon (periodic + manual trigger)
         ↓ (python-mpd2)
   MPD server (local Unix socket)
         ↓
   mpc commands (existing i3 keybindings)
         ↓
   Audio output
```

### Key Changes

1. **ytmpd is now a sync daemon**, not a command server
   - Periodically syncs YouTube Music playlists to MPD (default: every 30 minutes)
   - No longer manages playback state directly

2. **Playback handled by MPD**, not ytmpd
   - Use `mpc` commands for all playback control
   - YouTube playlists appear in MPD with "YT: " prefix
   - Leverage MPD's robust audio backend

3. **ytmpctl now focuses on sync operations**, not playback
   - `ytmpctl sync` - trigger immediate sync
   - `ytmpctl status` - check sync status and statistics
   - `ytmpctl list-playlists` - list YouTube playlists
   - **Removed**: play, pause, resume, stop, next, prev, queue, search

4. **Socket protocol changed**
   - Old socket: `~/.config/ytmpd/socket` (removed)
   - New socket: `~/.config/ytmpd/sync_socket` (sync commands only)
   - Simple JSON-based sync protocol

5. **State file format changed**
   - Old: `~/.config/ytmpd/state.json` (player state)
   - New: `~/.config/ytmpd/sync_state.json` (sync statistics)

## Migration Steps

### 1. Prerequisites

**Install MPD and mpc:**

```bash
# Arch/Manjaro
sudo pacman -S mpd mpc

# Ubuntu/Debian
sudo apt install mpd mpc

# Enable and start MPD
systemctl --user enable mpd
systemctl --user start mpd

# Verify MPD is running
mpc status
```

### 2. Stop Old ytmpd

```bash
# Find and kill old ytmpd process
pkill -f "python -m ytmpd"

# Or if you used a different method to start it
ps aux | grep ytmpd
kill <PID>

# Clean up old socket
rm ~/.config/ytmpd/socket
```

### 3. Update Dependencies

```bash
cd /path/to/ytmpd
source .venv/bin/activate
uv pip install -e ".[dev]"
```

This installs new dependencies:
- `python-mpd2` - MPD client library
- `yt-dlp` - Stream URL resolver

### 4. Update Configuration

Edit `~/.config/ytmpd/config.yaml` to add MPD settings:

```yaml
# Existing settings (keep these)
log_level: INFO
log_file: ~/.config/ytmpd/ytmpd.log

# New MPD integration settings (add these)
mpd_socket_path: ~/.config/mpd/socket
sync_interval_minutes: 30
enable_auto_sync: true
playlist_prefix: "YT: "
stream_cache_hours: 5
```

**Note**: If you don't have a config file, it will be created automatically with defaults on first run.

### 5. Start New ytmpd

```bash
source .venv/bin/activate
python -m ytmpd &
```

Watch the logs to verify successful startup:
```bash
tail -f ~/.config/ytmpd/ytmpd.log
```

Expected output:
```
[INFO] Starting ytmpd daemon...
[INFO] Configuration loaded
[INFO] Successfully authenticated with YouTube Music
[INFO] Connected to MPD
[INFO] Starting sync...
[INFO] Sync complete: X playlists, Y tracks
```

### 6. Update i3 Keybindings

Edit `~/.config/i3/config` and replace ytmpctl commands with mpc:

**Old keybindings (remove):**
```
bindsym $mod+Shift+p exec --no-startup-id /path/to/ytmpd/bin/ytmpctl pause
bindsym $mod+Shift+r exec --no-startup-id /path/to/ytmpd/bin/ytmpctl resume
bindsym $mod+Shift+s exec --no-startup-id /path/to/ytmpd/bin/ytmpctl stop
bindsym $mod+Shift+n exec --no-startup-id /path/to/ytmpd/bin/ytmpctl next
bindsym $mod+Shift+b exec --no-startup-id /path/to/ytmpd/bin/ytmpctl prev
```

**New keybindings (add):**
```
# MPD playback controls (ytmpd playlists)
bindsym $mod+Shift+p exec --no-startup-id mpc toggle
bindsym $mod+Shift+s exec --no-startup-id mpc stop
bindsym $mod+Shift+n exec --no-startup-id mpc next
bindsym $mod+Shift+b exec --no-startup-id mpc prev

# Refresh i3blocks after control
bindsym $mod+Shift+p exec --no-startup-id killall -SIGUSR1 i3blocks
bindsym $mod+Shift+n exec --no-startup-id killall -SIGUSR1 i3blocks
```

Reload i3:
```bash
i3-msg reload
```

### 7. Update i3blocks Configuration (if applicable)

The `ytmpd-status` script should still work, but now displays MPD status instead of ytmpd player state.

If you need to update your i3blocks config:

```ini
[ytmpd]
command=/path/to/ytmpd/bin/ytmpd-status
interval=5
separator_block_width=15
```

Reload i3blocks:
```bash
killall -SIGUSR1 i3blocks
```

### 8. Verify Everything Works

**Check sync status:**
```bash
ytmpctl status
```

Expected output:
```
=== ytmpd Sync Status ===

Last sync: 2025-10-17 10:00:05
Daemon started: 2025-10-17 10:00:00

Status: Last sync successful

=== Last Sync Statistics ===
Playlists synced: 5
Tracks added: 150
Tracks failed: 3
```

**List YouTube playlists:**
```bash
ytmpctl list-playlists
```

**List MPD playlists:**
```bash
mpc lsplaylists | grep "^YT:"
```

You should see your YouTube playlists with "YT: " prefix.

**Load and play a playlist:**
```bash
mpc load "YT: Favorites"
mpc play
mpc status
```

You should see playback start!

## Breaking Changes

### Removed ytmpctl Commands

The following commands are no longer available in ytmpctl:

- `ytmpctl play <query>` → Use `mpc load "YT: <playlist>"; mpc play`
- `ytmpctl pause` → Use `mpc pause`
- `ytmpctl resume` → Use `mpc play` or `mpc toggle`
- `ytmpctl stop` → Use `mpc stop`
- `ytmpctl next` → Use `mpc next`
- `ytmpctl prev` → Use `mpc prev`
- `ytmpctl queue` → Use `mpc playlist`
- `ytmpctl search <query>` → Use YouTube Music directly or `mpc search`

### Socket Protocol Changes

**Old protocol (v1):**
```
Client sends:  play <video_id_or_query>
Server responds: OK
```

**New protocol (v2):**
```
Client sends:  sync
Server responds: {"success": true, "message": "Sync triggered", ...}
```

If you have scripts that communicate with the old socket, they will need to be updated.

### State File Changes

**Old state file (`~/.config/ytmpd/state.json`):**
```json
{
  "state": "playing",
  "current_song": {...},
  "queue": [...],
  "position": 45.2
}
```

**New state file (`~/.config/ytmpd/sync_state.json`):**
```json
{
  "last_sync": "2025-10-17T10:00:05Z",
  "last_sync_result": {
    "success": true,
    "playlists_synced": 5,
    "tracks_added": 150
  }
}
```

The old state file is no longer used. Playback state is managed by MPD.

## Backward Compatibility

### Config File

Old config files (without MPD settings) will still load. Missing fields use default values:

```yaml
# Old config (still works)
socket_path: ~/.config/ytmpd/socket
state_file: ~/.config/ytmpd/state.json
log_level: INFO
log_file: ~/.config/ytmpd/ytmpd.log

# New fields added automatically with defaults
mpd_socket_path: ~/.config/mpd/socket
sync_interval_minutes: 30
enable_auto_sync: true
playlist_prefix: "YT: "
stream_cache_hours: 5
```

### Authentication

Browser authentication (`~/.config/ytmpd/browser.json`) remains the same. No need to re-authenticate.

## Troubleshooting

### "MPD connection refused"

**Cause**: MPD is not running or socket path is incorrect.

**Solution**:
```bash
# Check MPD status
systemctl --user status mpd

# Start MPD if not running
systemctl --user start mpd

# Verify socket exists
ls ~/.config/mpd/socket

# Check MPD config
cat ~/.config/mpd/mpd.conf | grep bind_to_address
```

### "No playlists synced"

**Cause**: Sync may have failed or YouTube authentication expired.

**Solution**:
```bash
# Check logs
tail -f ~/.config/ytmpd/ytmpd.log

# Trigger manual sync
ytmpctl sync

# If authentication errors, refresh browser auth
python -m ytmpd.ytmusic setup-browser
```

### "Old ytmpctl commands don't work"

**Cause**: Commands removed in v2.

**Solution**: Use `mpc` commands instead (see "Removed ytmpctl Commands" section above).

### "i3blocks status not updating"

**Cause**: Script may need update or MPD connection issue.

**Solution**:
```bash
# Test script directly
bin/ytmpd-status

# Check MPD is accessible
mpc status

# Reload i3blocks
killall -SIGUSR1 i3blocks
```

## FAQ

### Can I run v1 and v2 side-by-side?

No, not recommended. They use different architectures and would conflict. Choose one version.

### Do I need to keep my old state.json?

No, the old state file is no longer used. You can delete it:
```bash
rm ~/.config/ytmpd/state.json
```

### Will my YouTube playlists sync automatically?

Yes! By default, ytmpd syncs every 30 minutes. You can also trigger manual sync with `ytmpctl sync`.

### What happens if YouTube URLs expire?

YouTube stream URLs expire after ~6 hours. ytmpd:
- Caches URLs for 5 hours (1-hour buffer)
- Auto-syncs every 30 minutes to refresh URLs
- You can manually sync anytime with `ytmpctl sync`

### Can I change the "YT: " prefix?

Yes, edit `~/.config/ytmpd/config.yaml`:
```yaml
playlist_prefix: "YouTube: "  # or any prefix you want
```

Then restart ytmpd.

### Can I disable auto-sync?

Yes, edit config:
```yaml
enable_auto_sync: false
```

Then use `ytmpctl sync` for manual syncing.

## Getting Help

If you encounter issues during migration:

1. Check logs: `tail -f ~/.config/ytmpd/ytmpd.log`
2. Check README troubleshooting section
3. File an issue on GitHub with:
   - Migration step you're on
   - Error message
   - Relevant log excerpts

## Benefits of v2

### Why migrate?

1. **Actual audio playback** - MPD plays audio, v1 didn't
2. **Standard tools** - Use mpc, ncmpcpp, or any MPD client
3. **Robust backend** - Leverage MPD's proven audio architecture
4. **Wider compatibility** - MPD works with many clients and apps
5. **Better error handling** - Failed tracks don't stop sync
6. **URL caching** - Reduces yt-dlp overhead
7. **State persistence** - Track sync history and statistics

## Timeline

- **v1** (old): Socket-based command server (pre-2025-10-17)
- **v2** (current): MPD sync daemon (2025-10-17 onwards)

Support for v1 has ended. Please migrate to v2 for continued updates and bug fixes.
