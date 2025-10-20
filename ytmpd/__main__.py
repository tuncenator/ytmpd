"""Entry point for ytmpd daemon."""

import logging
import sys

from ytmpd.config import load_config
from ytmpd.daemon import YTMPDaemon


def setup_logging(log_level: str, log_file: str) -> None:
    """Setup logging configuration.

    Args:
        log_level: Logging level (e.g., INFO, DEBUG, WARNING).
        log_file: Path to log file.
    """
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Create formatters
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
    )

    # File handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)


def main() -> None:
    """Main entry point for ytmpd daemon."""
    # Load configuration
    config = load_config()

    # Setup logging
    setup_logging(config["log_level"], config["log_file"])

    logger = logging.getLogger(__name__)
    logger.info("Starting ytmpd sync daemon...")

    try:
        # Create and start daemon
        daemon = YTMPDaemon()
        daemon.run()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Daemon error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
