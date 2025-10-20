#!/bin/bash
#
# ytmpd Uninstallation Script
#
# This script removes ytmpd components installed by install.sh:
# - systemd user service
# - Binary symlinks from ~/.local/bin
# - Optionally: configuration data
#
# Note: This does not remove the project directory itself.

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

info "Starting ytmpd uninstallation..."

# Step 1: Stop and remove systemd service
info ""
info "=========================================="
info "systemd Service Removal"
info "=========================================="
info ""

SERVICE_FILE="$HOME/.config/systemd/user/ytmpd.service"
if [ -f "$SERVICE_FILE" ]; then
    info "Found systemd service, removing..."

    # Stop the service if running
    if systemctl --user is-active --quiet ytmpd.service; then
        systemctl --user stop ytmpd.service
        info "Service stopped"
    fi

    # Disable the service if enabled
    if systemctl --user is-enabled --quiet ytmpd.service 2>/dev/null; then
        systemctl --user disable ytmpd.service
        info "Service disabled"
    fi

    # Remove the service file
    rm "$SERVICE_FILE"
    info "Service file removed"

    # Reload systemd
    systemctl --user daemon-reload
    info "systemd daemon reloaded"
else
    info "No systemd service found, skipping"
fi

# Step 2: Remove binary symlinks
info ""
info "=========================================="
info "Binary Removal"
info "=========================================="
info ""

REMOVED_BINARIES=0
if [ -L "$HOME/.local/bin/ytmpctl" ]; then
    rm "$HOME/.local/bin/ytmpctl"
    info "Removed ytmpctl from ~/.local/bin"
    REMOVED_BINARIES=1
fi

if [ -L "$HOME/.local/bin/ytmpd-status" ]; then
    rm "$HOME/.local/bin/ytmpd-status"
    info "Removed ytmpd-status from ~/.local/bin"
    REMOVED_BINARIES=1
fi

if [ $REMOVED_BINARIES -eq 0 ]; then
    info "No binary symlinks found in ~/.local/bin"
fi

# Step 3: Ask about config data removal
info ""
info "=========================================="
info "Configuration Data"
info "=========================================="
info ""

CONFIG_DIR="$HOME/.config/ytmpd"
if [ -d "$CONFIG_DIR" ]; then
    info "Configuration directory found: $CONFIG_DIR"
    info "This contains:"
    info "  - YouTube Music authentication (browser.json)"
    info "  - Track cache database"
    info "  - Generated playlists"
    info ""
    read -p "Do you want to remove configuration data? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$CONFIG_DIR"
        info "Configuration data removed"
    else
        info "Configuration data preserved at $CONFIG_DIR"
    fi
else
    info "No configuration directory found"
fi

# Step 4: Uninstallation summary
info ""
info "=========================================="
info "Uninstallation Complete!"
info "=========================================="
info ""
info "ytmpd components have been removed."
info ""
info "To completely remove ytmpd:"
info "  1. Delete the project directory manually"
info "  2. Remove any i3/i3blocks configuration entries"
info ""
