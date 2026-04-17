# ytmpd — YouTube Music → MPD sync daemon

A background sync daemon that pulls your YouTube Music library into MPD so you
can drive playback with standard MPD tooling (`mpc`, `ncmpcpp`, mobile MPD
clients, i3 keybindings). Optional extras extend it with AirPlay multi-room
routing via OwnTone.

```
YouTube Music  →  ytmpd daemon  →  MPD  →  mpc / ncmpcpp / AirPlay (optional)
```

## Features

- **Playlist sync** — pulls your YouTube Music playlists into MPD on a timer
  and on demand (`ytmpctl sync`). Playlists appear as `YT: <name>`.
- **XSPF playlists** — optional format that gives MPD separate artist/title
  fields and duration, for proper ncmpcpp display.
- **Radio** — generate a personalised radio playlist seeded from the current
  track (`ytmpctl radio`).
- **Search** — interactive search across YouTube Music with play/enqueue/radio
  actions (`ytmpctl search`).
- **Likes / dislikes** — toggle ratings from any MPD environment; changes sync
  back to YouTube Music (`ytmpctl like|dislike`).
- **Like indicator** — visually tag liked tracks inside playlists (e.g.
  `Artist - Title [+1]`).
- **History reporting** — feed completed plays back to YouTube Music so its
  recommendation engine stays warm.
- **Auto-authentication** — refresh YouTube Music credentials automatically by
  reading cookies from your Firefox profile; no manual header pasting.
- **i3 integration** — status script with adaptive truncation for i3blocks.
- **AirPlay bridge (optional)** — see [`extras/airplay-bridge/`](extras/airplay-bridge/)
  for atomic speaker routing, metadata forwarding, and smart volume keys on
  top of OwnTone.

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) for environment management
- MPD + `mpc`
- YouTube Music account (free or premium)

### MPD setup

```bash
# Arch / Manjaro
sudo pacman -S mpd mpc

# Debian / Ubuntu
sudo apt install mpd mpc

systemctl --user enable --now mpd
mpc status  # sanity check
```

## Installation

```bash
git clone <repo> ytmpd
cd ytmpd
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

## Authentication

ytmpd needs a YouTube Music session. Two options:

### One-shot browser headers

```bash
python -m ytmpd.ytmusic setup-browser
```

Follow the prompts: log in to YouTube Music in your browser, open devtools →
Network, copy request headers from any `music.youtube.com` call, paste in. This
writes `~/.config/ytmpd/browser.json` and is good for ~2 years.

### Auto-auth (recommended)

Let ytmpd rebuild `browser.json` periodically from your Firefox cookie
database:

```yaml
# ~/.config/ytmpd/config.yaml
auto_auth:
  enabled: true
  browser: firefox-dev   # or "firefox"
  container: null        # or Multi-Account-Containers name
  profile: null          # null = auto-detect
  refresh_interval_hours: 12
```

Trigger a one-off extraction without the daemon:

```bash
ytmpctl auth --auto
```

If cookies go stale (cleared data, logged out, browser long unused) you'll get
a desktop notification; the i3blocks widget flags it as orange/red. Log back
into YouTube Music in Firefox and the next refresh cycle will pick it up.

## Usage

### Start the daemon

```bash
source .venv/bin/activate
python -m ytmpd &
```

On startup ytmpd runs an initial sync, then auto-syncs every
`sync_interval_minutes` (default 30). Logs land in
`~/.config/ytmpd/ytmpd.log`.

### `ytmpctl`

`ytmpctl` drives the daemon for everything except playback:

| Command                   | What it does |
|---------------------------|--------------|
| `ytmpctl sync`            | Force an immediate sync |
| `ytmpctl status`          | Sync state + stats |
| `ytmpctl list-playlists`  | List YouTube Music playlists |
| `ytmpctl search`          | Interactive search (play / enqueue / radio) |
| `ytmpctl radio [--apply]` | Radio from current track; `--apply` also loads & plays |
| `ytmpctl like`            | Toggle like on the currently playing track |
| `ytmpctl dislike`         | Toggle dislike on the currently playing track |
| `ytmpctl auth --auto`     | One-off Firefox cookie extraction |

### Playback via `mpc`

```bash
mpc load "YT: Favorites"
mpc play
mpc next / mpc prev / mpc toggle / mpc stop
```

Stream URLs expire after ~6 hours; ytmpd caches them for 5 hours and refreshes
on the next sync cycle. If a track fails to play, run `ytmpctl sync`.

## Radio & search

**Radio** generates a 25-track recommendation playlist seeded from the current
YouTube Music track:

```bash
ytmpctl radio            # write to ~/Music/_youtube/YT: Radio.xspf
ytmpctl radio --apply    # write + load + play
```

Configurable via `radio_playlist_limit` (10–50).

**Search** offers fuzzy search with inline actions:

```bash
$ ytmpctl search
Search YouTube Music:
> miles davis kind of blue
  1. So What - Miles Davis (9:22)
  2. Freddie Freeloader - Miles Davis (9:33)
  ...
> 2
Actions: 1) Play now  2) Add to queue  3) Start radio  4) Cancel
```

## Likes & dislikes

```bash
ytmpctl like        # toggle like on current track
ytmpctl dislike     # toggle dislike on current track
```

Behaviour is idempotent per direction and cross-cancels the opposite rating:

| Current state | `like`   | `dislike` |
|---------------|----------|-----------|
| Neutral       | Liked    | Disliked  |
| Liked         | Neutral  | Disliked  |
| Disliked      | Liked    | Neutral   |

Liking a track immediately triggers a sync so the liked-songs playlist updates
without waiting for the next interval.

**Known quirk:** YouTube Music's API reports disliked tracks as neutral, so
`dislike` twice will dislike twice rather than toggle off. Use `like` to clear
a dislike explicitly.

### Like indicator

Tag liked tracks inside playlists so you can spot them at a glance:

```yaml
like_indicator:
  enabled: true
  tag: "+1"           # shown as [+1]; "*", "LIKED", etc. work too
  alignment: right    # "left" or "right"
```

Applies to every playlist except `YT: Liked Songs` itself (redundant there).
Radio playlists get the same treatment.

## History reporting

Feed completed plays back to YouTube Music so recommendations reflect what you
actually listen to:

```yaml
history_reporting:
  enabled: false         # opt-in
  min_play_seconds: 30   # tracks shorter than this count as skips
```

Runs as a background thread inside the daemon: watches MPD player state, times
actual play duration (excluding pauses), calls YouTube Music's history API on
each qualifying track.

## Playlist format

Two formats are supported; set `playlist_format` in config:

- **`m3u`** — traditional, single `Name` field per track.
- **`xspf`** — XML with separate `<creator>` / `<title>` / `<duration>` fields.
  Requires `mpd_music_directory` (XSPF files go in `<music_dir>/_youtube/`).
  Recommended for ncmpcpp users — you get colour-coded artist/title columns.

## AirPlay bridge (optional)

`extras/airplay-bridge/` ships a complete AirPlay stack built on
[OwnTone](https://owntone.github.io/owntone-server/). It's independent of the
ytmpd daemon — install it only if you want multi-room AirPlay + proper
metadata on your receivers.

**What you get:**

- `speaker laptop|denon|kitchen|multi|status|list` — atomic routing across MPD
  outputs, OwnTone speaker selection, and the PipeWire default sink. Handles
  cold receivers (retries selection while an AVR wakes from standby).
- `speaker-rofi` — rofi-driven speaker picker that discovers reachable AirPlay
  receivers dynamically.
- `vol-wrap up|down|mute` — routes volume keys to OwnTone when AirPlay is
  active, PipeWire otherwise; does ratio-anchored scaling for multi-room.
- `mpd_owntone_metadata.py` — systemd user service that bridges MPD metadata
  (artist / title / album art) into OwnTone's metadata pipe, so receivers show
  the current song instead of "mpd.pcm / Unknown artist". Album art is
  resolved from MPD-embedded tags, folder art, then cached iTunes /
  MusicBrainz lookups for YouTube tracks.

**Install:**

```bash
cd extras/airplay-bridge
./install.sh --check     # report what's missing, no changes
./install.sh             # idempotent install (Arch/Manjaro; uses yay)
```

The installer sets up `~/.config/mpd-owntone-bridge/config.env`, drops the
systemd user unit, wires up the PipeWire RAOP discovery dropin, and augments
your `~/.i3/config` inside sentinel markers. Populate `SPEAKER_DENON` /
`SPEAKER_KITCHEN` with the output IDs discovered during install.

## i3 integration

### Keybindings

```text
# Playback (mpd)
bindsym $mod+Shift+p exec --no-startup-id mpc toggle
bindsym $mod+Shift+s exec --no-startup-id mpc stop
bindsym $mod+Shift+n exec --no-startup-id mpc next
bindsym $mod+Shift+b exec --no-startup-id mpc prev

# Ratings
bindsym $mod+plus  exec --no-startup-id ytmpctl like
bindsym $mod+minus exec --no-startup-id ytmpctl dislike

# Refresh i3blocks after a control change
bindsym $mod+Shift+p exec --no-startup-id killall -SIGUSR1 i3blocks
```

### i3blocks status

```ini
[ytmpd]
command=/path/to/ytmpd/bin/ytmpd-status
interval=5
separator_block_width=15
```

Output examples:

- `▶ Queen - Bohemian Rhapsody [2:34/5:55]` (green, playing)
- `⏸ The Beatles - Hey Jude [1:23/7:06]` (yellow, paused)
- `⏹ MPD` (grey, stopped)

Truncates adaptively under width pressure: timestamps stay, progress bar
shrinks, song name ellipsises last.

See `examples/i3blocks.conf` for a full setup.

## Configuration

Config lives at `~/.config/ytmpd/config.yaml` and is created with defaults on
first run. Full documentation of every option is in
[`examples/config.yaml`](examples/config.yaml). Key settings:

| Setting                 | Default                  | Notes |
|-------------------------|--------------------------|-------|
| `mpd_socket_path`       | `~/.config/mpd/socket`   | Unix socket path or `host:port` |
| `mpd_music_directory`   | `~/Music`                | Required if `playlist_format: xspf` |
| `sync_interval_minutes` | `30`                     | Set `enable_auto_sync: false` to disable |
| `playlist_prefix`       | `"YT: "`                 | Prefix for synced playlists in MPD |
| `playlist_format`       | `m3u`                    | `m3u` or `xspf` |
| `stream_cache_hours`    | `5`                      | Buffer before 6-hour URL expiry |
| `radio_playlist_limit`  | `25`                     | 10–50 |
| `auto_auth.enabled`     | `false`                  | Firefox cookie auto-refresh |
| `history_reporting.enabled` | `false`              | Report plays to YT Music |
| `like_indicator.enabled`    | `false`              | Tag liked tracks in playlists |

## Troubleshooting

### Daemon won't start

- `mpc status` — is MPD up? `systemctl --user start mpd` if not.
- `ls ~/.config/mpd/socket` — does the socket ytmpd targets actually exist?
- `ls ~/.config/ytmpd/browser.json` — auth file present? Run `python -m
  ytmpd.ytmusic setup-browser` or `ytmpctl auth --auto`.
- `tail -f ~/.config/ytmpd/ytmpd.log`.

### No playlists in MPD

- `ytmpctl sync` then `ytmpctl status` — did it succeed?
- `mpc lsplaylists | grep '^YT:'` — are they actually there under the prefix?
- `grep ERROR ~/.config/ytmpd/ytmpd.log`.

### Playback silent

- `mpc outputs` — is any output enabled? `mpc enable <n>` to toggle one on.
- AirPlay via the bridge: `extras/airplay-bridge/speaker status` — any
  receiver still selected? If not, the receiver likely dropped the RTSP
  session (standby, source switch, network blip). Re-pick it.

### Stream URLs expired

YouTube URLs die at ~6 hours. The daemon refreshes them on every sync cycle;
force one with `ytmpctl sync`.

### Authentication failures

- With auto-auth on: check you're still logged into YouTube Music in Firefox,
  then `ytmpctl auth --auto` to force a cookie re-extract.
- Without: re-run `python -m ytmpd.ytmusic setup-browser` and paste fresh
  headers.

### i3blocks stale

- `killall -SIGUSR1 i3blocks` forces a refresh.
- `bin/ytmpd-status` directly to check the script output.
- `chmod +x bin/ytmpd-status` if permissions are off.

## How it works

MPD doesn't speak YouTube, so ytmpd runs a local HTTP helper on
`localhost:8080` that re-serves each track's yt-dlp-resolved stream with
injected ICY metadata. Synced playlists point MPD at `http://localhost:8080/
proxy/<video_id>`; the proxy fetches the upstream audio, prepends ICY headers,
and streams back. This is an implementation detail — you don't configure it
day-to-day — but it's how MPD knows what to display in the playlist view and
how the history reporter identifies YouTube tracks.

Expired URLs are re-resolved in the background; the proxy falls back to the
cached URL if refresh fails.

## Development

```bash
pytest                                      # full suite
pytest --cov=ytmpd --cov-report=term-missing
pytest tests/integration/                   # integration only

mypy ytmpd/
ruff check --fix ytmpd/
ruff format ytmpd/
```

## Project structure

```
ytmpd/
├── ytmpd/                       # Main package
│   ├── __main__.py              # Daemon entry point
│   ├── config.py                # Config load/validate
│   ├── cookie_extract.py        # Firefox cookie extraction
│   ├── daemon.py                # Sync loop + background threads
│   ├── history_reporter.py      # MPD → YT Music history
│   ├── icy_proxy.py             # Local stream + metadata proxy
│   ├── mpd_client.py            # python-mpd2 wrapper
│   ├── notify.py                # Desktop notifications
│   ├── rating.py                # Like / dislike logic
│   ├── stream_resolver.py       # Video ID → stream URL (yt-dlp)
│   ├── sync_engine.py           # Sync orchestration
│   ├── track_store.py           # SQLite track metadata store
│   ├── xspf_generator.py        # XSPF playlist writer
│   ├── ytmusic.py               # YouTube Music API wrapper
│   └── exceptions.py            # Custom exceptions
├── bin/
│   ├── ytmpctl                  # Sync / rating / search CLI
│   └── ytmpd-status             # i3blocks status script
├── extras/
│   └── airplay-bridge/          # Optional OwnTone AirPlay stack
│       ├── install.sh
│       ├── speaker              # Routing tool
│       ├── speaker-rofi         # rofi speaker picker
│       ├── vol-wrap             # Smart volume key router
│       └── mpd_owntone_metadata.py  # Metadata pipe bridge
├── examples/
│   ├── config.yaml              # Documented full config
│   └── i3blocks.conf            # Example i3blocks block
├── docs/                        # Design docs + migration notes
└── tests/                       # Unit + integration tests
```

## Migration from v1

If you're coming from the old command-server architecture, see
[`docs/MIGRATION.md`](docs/MIGRATION.md). Summary: ytmpctl is now a sync tool,
not a playback tool; MPD owns playback.

## License

MIT

## Acknowledgments

- [ytmusicapi](https://github.com/sigma67/ytmusicapi) by sigma67
- [python-mpd2](https://github.com/Mic92/python-mpd2)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [OwnTone](https://owntone.github.io/owntone-server/) for the AirPlay bridge
- [MPD](https://www.musicpd.org/) itself
