#!/usr/bin/env bash
# airplay-bridge installer and readiness checker.
#
# Usage:
#   install.sh               # install (idempotent; run with sudo access)
#   install.sh --check       # no changes; just report what's missing
#
# Targets Arch/Manjaro. Assumes yay is available for AUR packages.

set -u -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RED=$'\033[0;31m'; GRN=$'\033[0;32m'; YLW=$'\033[1;33m'; NC=$'\033[0m'
ok()    { printf '[%sOK%s]      %s\n'      "$GRN" "$NC" "$*"; }
miss()  { printf '[%sMISSING%s] %s\n'      "$YLW" "$NC" "$*"; }
info()  { printf '[%sINFO%s]    %s\n'      "$GRN" "$NC" "$*"; }
warn()  { printf '[%sWARN%s]    %s\n'      "$YLW" "$NC" "$*"; }
fatal() { printf '[%sFATAL%s]   %s\n'      "$RED" "$NC" "$*" >&2; exit 1; }

BEGIN_MARK='### airplay-bridge:begin (managed; do not edit between markers)'
END_MARK='### airplay-bridge:end'

MODE="install"
[[ "${1:-}" == "--check" ]] && MODE="check"

OWNTONE_API="http://localhost:3689/api"
CFG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/mpd-owntone-bridge"
CFG_FILE="$CFG_DIR/config.env"
MPD_CONF="${HOME}/.mpd/mpd.conf"
I3_CONF="${HOME}/.i3/config"
SYSTEMD_UNIT="${HOME}/.config/systemd/user/mpd-owntone-metadata.service"
PW_DROPIN="${HOME}/.config/pipewire/pipewire-pulse.conf.d/20-raop-discover.conf"

# -------- helpers --------

has_cmd()  { command -v "$1" >/dev/null 2>&1; }
pkg_installed() { pacman -Q "$1" >/dev/null 2>&1; }
in_group() { id -nG "$USER" | tr ' ' '\n' | grep -qx "$1"; }
file_has()  { [[ -f "$1" ]] && grep -qF "$2" "$1"; }

remove_block() {
  # Remove sentinel-bounded block from $1. No-op if block absent.
  local f="$1"
  [[ -f "$f" ]] || return 0
  sed -i "/$BEGIN_MARK/,/$END_MARK/d" "$f"
}

append_block() {
  # Append begin..content..end to $1.
  local f="$1" content="$2"
  {
    printf '\n%s\n' "$BEGIN_MARK"
    printf '%s\n' "$content"
    printf '%s\n' "$END_MARK"
  } >> "$f"
}

replace_block() {
  remove_block "$1"
  append_block "$@"
}

wait_for_owntone_api() {
  local i
  for i in {1..20}; do
    command curl --silent --max-time 1 "$OWNTONE_API/outputs" >/dev/null && return 0
    sleep 0.5
  done
  return 1
}

# -------- checks --------

check_pkg() {
  # $1 = package name
  if pkg_installed "$1"; then ok "pkg: $1"; else miss "pkg: $1 (yay -S $1)"; fi
}

check_dir() {
  if [[ -d "$1" ]]; then ok "dir: $1"; else miss "dir: $1"; fi
}

check_fifo() {
  if [[ -p "$1" ]]; then ok "fifo: $1"; else miss "fifo: $1"; fi
}

check_owntone_conf() {
  if file_has /etc/owntone.conf '/var/lib/owntone-stream'; then
    ok "/etc/owntone.conf has our library dir"
  else
    miss "/etc/owntone.conf library dir not set to /var/lib/owntone-stream"
  fi
  if grep -Eq '^\s*type\s*=\s*"disabled"' /etc/owntone.conf 2>/dev/null; then
    ok "/etc/owntone.conf local audio is disabled"
  else
    miss "/etc/owntone.conf local audio not disabled"
  fi
}

check_service() {
  if [[ -f "$SYSTEMD_UNIT" ]]; then ok "systemd unit: $SYSTEMD_UNIT"; else miss "systemd unit missing"; fi
  if systemctl --user is-enabled --quiet mpd-owntone-metadata 2>/dev/null; then
    ok "mpd-owntone-metadata enabled"
  else
    miss "mpd-owntone-metadata not enabled"
  fi
}

run_checks() {
  echo "== Packages =="
  check_pkg mpd
  check_pkg owntone-server
  check_pkg pipewire-zeroconf
  check_pkg jq
  check_pkg avahi
  check_pkg rofi

  echo; echo "== System state =="
  check_dir /var/lib/owntone-stream
  check_fifo /var/lib/owntone-stream/mpd.pcm
  check_fifo /var/lib/owntone-stream/mpd.pcm.metadata
  if [[ -f /var/log/owntone.log ]]; then ok "/var/log/owntone.log"; else miss "/var/log/owntone.log"; fi
  check_owntone_conf
  if in_group owntone; then ok "user in owntone group (may need re-login after first add)"
  else miss "user not in owntone group"; fi

  echo; echo "== Per-machine config =="
  if [[ -f "$CFG_FILE" ]]; then
    ok "$CFG_FILE"
    # shellcheck source=/dev/null
    (. "$CFG_FILE"; [[ -n "${SPEAKER_DENON:-}" ]] && ok "  SPEAKER_DENON=$SPEAKER_DENON" || miss "  SPEAKER_DENON empty"
                    [[ -n "${PIPEWIRE_LAPTOP_SINK:-}" ]] && ok "  PIPEWIRE_LAPTOP_SINK=$PIPEWIRE_LAPTOP_SINK" || miss "  PIPEWIRE_LAPTOP_SINK empty")
  else
    miss "$CFG_FILE"
  fi

  echo; echo "== User integrations =="
  check_service
  if file_has "$MPD_CONF" "$BEGIN_MARK"; then ok "mpd.conf has bridge block"; else miss "mpd.conf lacks bridge block"; fi
  if file_has "$I3_CONF" "$BEGIN_MARK"; then ok "i3 config has bridge bindings"; else miss "i3 config lacks bridge bindings"; fi
  if [[ -f "$PW_DROPIN" ]]; then ok "pipewire raop drop-in"; else miss "pipewire raop drop-in"; fi

  echo; echo "== Runtime =="
  if systemctl is-active --quiet owntone; then ok "owntone.service running"; else miss "owntone.service not running"; fi
  if systemctl --user is-active --quiet mpd-owntone-metadata; then ok "mpd-owntone-metadata running"; else miss "mpd-owntone-metadata not running"; fi
  if command curl --silent --max-time 1 "$OWNTONE_API/outputs" >/dev/null; then
    ok "owntone API reachable"
    local n_ap
    n_ap=$(command curl --silent "$OWNTONE_API/outputs" | jq '[.outputs[] | select(.type|startswith("AirPlay"))] | length')
    info "  $n_ap AirPlay receiver(s) discovered"
  else
    miss "owntone API unreachable"
  fi
}

# -------- install actions --------

install_packages() {
  local needed=()
  for p in owntone-server pipewire-zeroconf jq avahi rofi; do
    pkg_installed "$p" || needed+=("$p")
  done
  if (( ${#needed[@]} == 0 )); then
    info "all packages already installed"
    return
  fi
  has_cmd yay || fatal "yay is required for AUR packages (install yay first)"
  info "installing packages: ${needed[*]}"
  yay -S --needed --noconfirm "${needed[@]}" || fatal "package install failed"
}

bootstrap_owntone_state() {
  info "ensuring /var/lib/owntone-stream and FIFOs"
  sudo install -d -o owntone -g owntone -m 2775 /var/lib/owntone-stream
  [[ -p /var/lib/owntone-stream/mpd.pcm ]] || sudo -u owntone mkfifo -m 666 /var/lib/owntone-stream/mpd.pcm
  [[ -p /var/lib/owntone-stream/mpd.pcm.metadata ]] || sudo -u owntone mkfifo -m 666 /var/lib/owntone-stream/mpd.pcm.metadata

  info "ensuring /var/log/owntone.log"
  sudo install -o owntone -g owntone -m 644 /dev/null /var/log/owntone.log

  info "patching /etc/owntone.conf (library dir, local audio off, mpd listener off)"
  sudo sed -i -E 's|^\s*directories\s*=\s*\{\s*"[^"]+"\s*\}|\tdirectories = { "/var/lib/owntone-stream" }|' /etc/owntone.conf
  if ! grep -Eq '^\s*type\s*=\s*"disabled"' /etc/owntone.conf; then
    sudo sed -i 's|^#\ttype = "alsa"|\ttype = "disabled"|' /etc/owntone.conf
  fi
  if ! grep -Eq '^\s*port\s*=\s*0\s*$' /etc/owntone.conf; then
    sudo sed -i 's|^#\tport = 6600|\tport = 0|' /etc/owntone.conf
  fi

  if ! in_group owntone; then
    info "adding $USER to owntone group (re-login required for it to take effect in new sessions)"
    sudo usermod -aG owntone "$USER"
  fi

  info "starting owntone"
  sudo systemctl enable --now owntone
}

discover_and_configure() {
  info "waiting for owntone API..."
  wait_for_owntone_api || fatal "owntone API did not come up within 10s"

  info "discovering AirPlay receivers"
  local outputs_json
  outputs_json=$(command curl --silent "$OWNTONE_API/outputs")
  local airplay
  airplay=$(jq -c '.outputs[] | select(.type|startswith("AirPlay")) | {id,name,type}' <<< "$outputs_json")
  if [[ -z "$airplay" ]]; then
    warn "no AirPlay receivers found. Power on your Denon/Home 150 and rerun."
    fatal "cannot continue without at least one AirPlay receiver"
  fi

  echo
  echo "Discovered AirPlay receivers:"
  local i=0
  local -a IDS=() NAMES=()
  while IFS= read -r line; do
    local id name
    id=$(jq -r .id   <<< "$line")
    name=$(jq -r .name <<< "$line")
    IDS+=("$id"); NAMES+=("$name")
    printf "  [%d] %s (%s)\n" "$i" "$name" "$(jq -r .type <<< "$line")"
    i=$((i+1))
  done <<< "$airplay"

  local pick_denon pick_kitchen
  echo
  read -rp "Main AirPlay AVR (Denon) — index: " pick_denon
  read -rp "Kitchen speaker index (blank to skip): " pick_kitchen

  local denon_id="${IDS[$pick_denon]}"
  local kitchen_id=""
  if [[ -n "$pick_kitchen" ]]; then kitchen_id="${IDS[$pick_kitchen]}"; fi

  # Laptop sink autodetect: first analog-stereo sink.
  local laptop_sink
  laptop_sink=$(pactl list sinks short 2>/dev/null | awk '/analog-stereo/ {print $2; exit}')

  mkdir -p "$CFG_DIR"
  sed -e "s|^SPEAKER_DENON=.*|SPEAKER_DENON=\"$denon_id\"|" \
      -e "s|^SPEAKER_KITCHEN=.*|SPEAKER_KITCHEN=\"$kitchen_id\"|" \
      -e "s|^PIPEWIRE_LAPTOP_SINK=.*|PIPEWIRE_LAPTOP_SINK=\"$laptop_sink\"|" \
      "$SCRIPT_DIR/config.env.template" > "$CFG_FILE"
  info "wrote $CFG_FILE"
}

install_systemd_unit() {
  info "installing systemd user unit -> $SYSTEMD_UNIT"
  mkdir -p "$(dirname "$SYSTEMD_UNIT")"
  sed -e "s|@SCRIPT_DIR@|$SCRIPT_DIR|g" "$SCRIPT_DIR/mpd-owntone-metadata.service.template" > "$SYSTEMD_UNIT"
  systemctl --user daemon-reload
  systemctl --user enable --now mpd-owntone-metadata
}

patch_mpd_conf() {
  info "patching $MPD_CONF (adding Owntone Bridge output)"
  [[ -f "$MPD_CONF" ]] || fatal "$MPD_CONF not found; create your MPD config first"
  local block
  block=$(cat <<'EOF'
audio_output {
	type   "fifo"
	name   "Owntone Bridge"
	path   "/var/lib/owntone-stream/mpd.pcm"
	format "44100:16:2"
}
EOF
  )
  replace_block "$MPD_CONF" "$block"
  info "reload MPD to pick up changes: systemctl --user restart mpd"
}

patch_i3_conf() {
  info "patching $I3_CONF (vol-wrap + speaker-rofi keybindings)"
  [[ -f "$I3_CONF" ]] || { warn "$I3_CONF not found; skipping"; return 0; }
  local block
  block=$(cat <<EOF
bindsym XF86AudioRaiseVolume exec $SCRIPT_DIR/vol-wrap up
bindsym XF86AudioLowerVolume exec $SCRIPT_DIR/vol-wrap down
bindsym XF86AudioMute        exec $SCRIPT_DIR/vol-wrap mute
bindsym Mode_switch+z        exec $SCRIPT_DIR/vol-wrap down
bindsym Mode_switch+c        exec $SCRIPT_DIR/vol-wrap up
bindsym Mode_switch+x        exec $SCRIPT_DIR/vol-wrap mute
bindsym \$mod+Shift+s        exec $SCRIPT_DIR/speaker-rofi
EOF
  )
  replace_block "$I3_CONF" "$block"
  info "reload i3: i3-msg reload"
}

install_pipewire_dropin() {
  info "installing pipewire raop discovery drop-in"
  mkdir -p "$(dirname "$PW_DROPIN")"
  cat > "$PW_DROPIN" <<'EOF'
pulse.cmd = [
    { cmd = "load-module" args = "module-raop-discover" }
]
EOF
}

make_executable() {
  chmod +x "$SCRIPT_DIR"/mpd_owntone_metadata.py \
           "$SCRIPT_DIR"/vol-wrap \
           "$SCRIPT_DIR"/speaker \
           "$SCRIPT_DIR"/speaker-rofi
}

# -------- main --------

if [[ "$MODE" == "check" ]]; then
  run_checks
  exit 0
fi

info "airplay-bridge install starting"
info "script dir: $SCRIPT_DIR"

has_cmd sudo || fatal "sudo required"
has_cmd pactl || warn "pactl not found; PipeWire sink autodetection will fail"

make_executable
install_packages
bootstrap_owntone_state
discover_and_configure
install_pipewire_dropin
install_systemd_unit
patch_mpd_conf
patch_i3_conf

echo
info "install complete."
info "you may need to:"
info "  - log out/in if you were just added to the owntone group"
info "  - systemctl --user restart mpd (to pick up the new fifo output)"
info "  - i3-msg reload (to activate new keybindings)"
info
info "run '$0 --check' any time to audit state."
