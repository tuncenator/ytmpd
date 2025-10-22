"""Configuration management for ytmpd."""

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def get_config_dir() -> Path:
    """Get the ytmpd configuration directory.

    Returns:
        Path to the configuration directory (~/.config/ytmpd/).
    """
    config_dir = Path.home() / ".config" / "ytmpd"
    return config_dir


def load_config() -> dict[str, Any]:
    """Load configuration from config file, creating defaults if needed.

    Returns:
        Dictionary containing configuration values.
    """
    config_dir = get_config_dir()
    config_file = config_dir / "config.yaml"

    # Create config directory if it doesn't exist
    if not config_dir.exists():
        logger.info(f"Creating config directory: {config_dir}")
        config_dir.mkdir(parents=True, exist_ok=True)

    # Default configuration
    default_config = {
        "socket_path": str(config_dir / "socket"),
        "state_file": str(config_dir / "state.json"),
        "log_level": "INFO",
        "log_file": str(config_dir / "ytmpd.log"),
        # MPD integration settings
        "mpd_socket_path": str(Path.home() / ".config" / "mpd" / "socket"),
        "mpd_playlist_directory": str(Path.home() / ".config" / "mpd" / "playlists"),
        "sync_interval_minutes": 30,
        "enable_auto_sync": True,
        "playlist_prefix": "YT: ",
        "stream_cache_hours": 5,
        # Liked songs settings
        "sync_liked_songs": True,
        "liked_songs_playlist_name": "Liked Songs",
        # Playlist format settings
        "playlist_format": "m3u",  # "m3u" or "xspf"
        "mpd_music_directory": str(Path.home() / "Music"),  # Required for XSPF
        # ICY Proxy settings
        "proxy_enabled": True,
        "proxy_host": "localhost",
        "proxy_port": 8080,
        "proxy_track_mapping_db": str(config_dir / "track_mapping.db"),
        # Radio feature settings
        "radio_playlist_limit": 25,
    }

    # Load existing config or create default
    if config_file.exists():
        logger.info(f"Loading config from: {config_file}")
        try:
            with open(config_file) as f:
                user_config = yaml.safe_load(f) or {}
            # Merge user config with defaults (user config takes precedence)
            config = {**default_config, **user_config}
        except Exception as e:
            logger.warning(f"Error loading config file, using defaults: {e}")
            config = default_config
    else:
        logger.info(f"Config file not found, creating default: {config_file}")
        config = default_config
        try:
            # Try to copy example config file if it exists
            example_config = Path(__file__).parent.parent / "examples" / "config.yaml"
            if example_config.exists():
                import shutil

                logger.info(f"Copying example config from: {example_config}")
                shutil.copy(example_config, config_file)
            else:
                # Fall back to simple YAML dump if example not found
                logger.info("Example config not found, generating basic config")
                with open(config_file, "w") as f:
                    yaml.safe_dump(config, f, default_flow_style=False)
        except Exception as e:
            logger.error(f"Error creating config file: {e}")

    # Validate and normalize config
    config = _validate_config(config)

    return config


def _validate_config(config: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize configuration values.

    Args:
        config: Configuration dictionary to validate.

    Returns:
        Validated and normalized configuration.

    Raises:
        ValueError: If configuration is invalid.
    """
    # Expand ~ in path fields
    path_fields = [
        "socket_path",
        "state_file",
        "log_file",
        "mpd_socket_path",
        "mpd_playlist_directory",
        "mpd_music_directory",
        "proxy_track_mapping_db",
    ]
    for field in path_fields:
        if field in config:
            config[field] = str(Path(config[field]).expanduser())

    # Validate sync_interval_minutes is positive
    if "sync_interval_minutes" in config:
        interval = config["sync_interval_minutes"]
        if not isinstance(interval, int | float) or interval <= 0:
            raise ValueError(f"sync_interval_minutes must be a positive number, got: {interval}")

    # Validate stream_cache_hours is positive
    if "stream_cache_hours" in config:
        cache_hours = config["stream_cache_hours"]
        if not isinstance(cache_hours, int | float) or cache_hours <= 0:
            raise ValueError(f"stream_cache_hours must be a positive number, got: {cache_hours}")

    # Ensure playlist_prefix is a string (can be empty)
    if "playlist_prefix" in config:
        if not isinstance(config["playlist_prefix"], str):
            raise ValueError(
                f"playlist_prefix must be a string, got: {type(config['playlist_prefix'])}"
            )

    # Ensure enable_auto_sync is a boolean
    if "enable_auto_sync" in config:
        if not isinstance(config["enable_auto_sync"], bool):
            raise ValueError(
                f"enable_auto_sync must be a boolean, got: {type(config['enable_auto_sync'])}"
            )

    # Ensure sync_liked_songs is a boolean
    if "sync_liked_songs" in config:
        if not isinstance(config["sync_liked_songs"], bool):
            raise ValueError(
                f"sync_liked_songs must be a boolean, got: {type(config['sync_liked_songs'])}"
            )

    # Ensure liked_songs_playlist_name is a string
    if "liked_songs_playlist_name" in config:
        if not isinstance(config["liked_songs_playlist_name"], str):
            playlist_name_type = type(config["liked_songs_playlist_name"])
            raise ValueError(
                f"liked_songs_playlist_name must be a string, got: {playlist_name_type}"
            )

    # Validate proxy settings
    if "proxy_enabled" in config:
        if not isinstance(config["proxy_enabled"], bool):
            raise ValueError(
                f"proxy_enabled must be a boolean, got: {type(config['proxy_enabled'])}"
            )

    if "proxy_port" in config:
        port = config["proxy_port"]
        if not isinstance(port, int) or port < 1 or port > 65535:
            raise ValueError(f"proxy_port must be an integer between 1 and 65535, got: {port}")

    if "proxy_host" in config:
        if not isinstance(config["proxy_host"], str):
            raise ValueError(f"proxy_host must be a string, got: {type(config['proxy_host'])}")

    # Validate playlist_format
    if "playlist_format" in config:
        fmt = config["playlist_format"]
        if not isinstance(fmt, str):
            raise ValueError(f"playlist_format must be a string, got: {type(fmt)}")
        if fmt.lower() not in ("m3u", "xspf"):
            raise ValueError(f"playlist_format must be 'm3u' or 'xspf', got: {fmt}")
        # Normalize to lowercase
        config["playlist_format"] = fmt.lower()

    # Validate XSPF requirements
    if config.get("playlist_format") == "xspf":
        if not config.get("mpd_music_directory"):
            raise ValueError(
                "mpd_music_directory is required when playlist_format is 'xspf'. "
                "Please configure mpd_music_directory in config.yaml."
            )

    # Validate radio_playlist_limit
    if "radio_playlist_limit" in config:
        limit = config["radio_playlist_limit"]
        if not isinstance(limit, int) or limit < 10 or limit > 50:
            raise ValueError(
                f"radio_playlist_limit must be an integer between 10 and 50, got: {limit}"
            )

    return config
