#!/bin/bash
#
# ytmpd Installation Script
#
# This script automates the installation of ytmpd (YouTube Music MPD daemon).
# It handles:
# - Installing uv (if needed)
# - Creating a virtual environment
# - Installing ytmpd and dependencies
# - Setting up YouTube Music authentication
# - Optionally installing systemd service
# - Adding binaries to PATH

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

# Check if running on Linux
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    error "This script is designed for Linux. For other systems, please install manually."
fi

info "Starting ytmpd installation..."

# Get the directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Step 1: Install uv if needed
if command -v uv &> /dev/null; then
    info "uv is already installed ($(uv --version))"
else
    info "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Source the shell profile to get uv in PATH
    if [ -f "$HOME/.cargo/env" ]; then
        source "$HOME/.cargo/env"
    fi

    # Verify installation
    if ! command -v uv &> /dev/null; then
        error "uv installation failed. Please install manually: https://astral.sh/uv/"
    fi

    info "uv installed successfully"
fi

# Step 2: Create virtual environment
if [ -d ".venv" ]; then
    warn "Virtual environment already exists, skipping creation"
else
    info "Creating virtual environment..."
    uv venv
    info "Virtual environment created"
fi

# Step 3: Activate virtual environment
info "Activating virtual environment..."
source .venv/bin/activate

# Step 4: Install ytmpd with dependencies
info "Installing ytmpd and dependencies..."
uv pip install -e ".[dev]"
info "ytmpd installed successfully"

# Step 5: Setup YouTube Music authentication
info ""
info "=========================================="
info "YouTube Music Authentication Setup"
info "=========================================="
info ""
info "ytmpd requires YouTube Music authentication via browser headers."
info "The next step will guide you through extracting these headers."
info ""
read -p "Do you want to set up authentication now? [Y/n] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
    python -m ytmpd.ytmusic setup-browser

    # Check if authentication was successful
    if [ -f "$HOME/.config/ytmpd/browser.json" ]; then
        info "Authentication setup complete!"
    else
        warn "Authentication setup was skipped or failed. You can run it later with:"
        warn "  source .venv/bin/activate && python -m ytmpd.ytmusic setup-browser"
    fi
else
    warn "Skipping authentication setup. Run this command later:"
    warn "  source .venv/bin/activate && python -m ytmpd.ytmusic setup-browser"
fi

# Step 6: Optionally install systemd service
info ""
info "=========================================="
info "systemd Service Installation (Optional)"
info "=========================================="
info ""
info "You can install a systemd user service to start ytmpd automatically."
info ""
read -p "Do you want to install the systemd service? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    if [ ! -f "ytmpd.service" ]; then
        error "ytmpd.service file not found. Please create it first."
    fi

    # Create systemd user directory if needed
    mkdir -p "$HOME/.config/systemd/user"

    # Detect music directory from config
    MUSIC_DIR="$HOME/Music"  # Default
    if [ -f "$HOME/.config/ytmpd/config.yaml" ]; then
        # Try to read mpd_music_directory from config
        CONFIG_MUSIC_DIR=$(grep "^mpd_music_directory:" "$HOME/.config/ytmpd/config.yaml" | sed 's/^mpd_music_directory:[[:space:]]*//' | sed 's/#.*//' | tr -d '"' | tr -d "'")
        if [ -n "$CONFIG_MUSIC_DIR" ]; then
            # Expand ~ to $HOME
            MUSIC_DIR="${CONFIG_MUSIC_DIR/#\~/$HOME}"
        fi
    fi

    info "Detected music directory: $MUSIC_DIR"

    # Copy and customize service file
    SERVICE_FILE="$HOME/.config/systemd/user/ytmpd.service"
    sed -e "s|/path/to/ytmpd|$SCRIPT_DIR|g" \
        -e "s|%h/Music|$MUSIC_DIR|g" \
        ytmpd.service > "$SERVICE_FILE"

    info "systemd service installed to $SERVICE_FILE"
    info "To enable and start the service, run:"
    info "  systemctl --user enable ytmpd.service"
    info "  systemctl --user start ytmpd.service"
else
    info "Skipping systemd service installation"
fi

# Step 7: Install binaries
info ""
info "=========================================="
info "Binary Installation"
info "=========================================="
info ""
info "ytmpd provides two executables:"
info "  - ytmpctl: Command-line client"
info "  - ytmpd-status: i3blocks status script"
info ""
read -p "Do you want to install binaries to ~/.local/bin? [Y/n] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
    # Create ~/.local/bin if it doesn't exist
    mkdir -p "$HOME/.local/bin"

    # Create symlinks
    ln -sf "$SCRIPT_DIR/bin/ytmpctl" "$HOME/.local/bin/ytmpctl"
    ln -sf "$SCRIPT_DIR/bin/ytmpd-status" "$HOME/.local/bin/ytmpd-status"

    info "Binaries installed to ~/.local/bin"
    info "Note: ~/.local/bin should be in your PATH (usually added by default)"
    info "If not, add this to your shell RC file:"
    info "  export PATH=\"\$HOME/.local/bin:\$PATH\""
else
    info "Skipping binary installation. You can use absolute paths:"
    info "  $SCRIPT_DIR/bin/ytmpctl"
    info "  $SCRIPT_DIR/bin/ytmpd-status"
fi

# Step 8: Installation summary
info ""
info "=========================================="
info "Installation Complete!"
info "=========================================="
info ""
info "ytmpd has been successfully installed to: $SCRIPT_DIR"
info ""
info "Quick Start:"
info "  1. Start daemon: source .venv/bin/activate && python -m ytmpd &"
info "  2. Control playback: $SCRIPT_DIR/bin/ytmpctl play \"hey jude beatles\""
info "  3. Check status: $SCRIPT_DIR/bin/ytmpctl status"
info ""
info "For i3 integration, see examples:"
info "  - examples/i3-config (keybindings)"
info "  - examples/i3blocks-config (status display)"
info ""
info "Documentation: README.md"
info "Troubleshooting: See 'Troubleshooting' section in README.md"
info ""
