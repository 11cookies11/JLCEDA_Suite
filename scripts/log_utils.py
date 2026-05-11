"""Centralized logging configuration for JLCEDA Suite server scripts.

Usage:
    from log_utils import setup_logging, log

    logger = setup_logging()
    logger.info("server started")
    logger.debug("processing request")
    logger.warning("something suspicious")
    logger.error("operation failed")
"""

from __future__ import annotations

import logging
import os
import sys

_logger: logging.Logger | None = None


def setup_logging(name: str = "jlceda-suite") -> logging.Logger:
    """Configure and return a logger for the given name.

    Log level is controlled by BRIDGE_LOG_LEVEL (default: INFO).
    Valid levels: DEBUG, INFO, WARNING, ERROR.
    """
    global _logger

    if _logger is not None:
        return _logger

    level_name = os.environ.get("BRIDGE_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-7s] %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(fmt)

    _logger = logging.getLogger(name)
    _logger.setLevel(level)
    _logger.addHandler(handler)
    _logger.propagate = False

    return _logger


def get_logger() -> logging.Logger:
    """Return the configured logger, creating it if necessary."""
    global _logger
    if _logger is None:
        return setup_logging()
    return _logger


# Convenience alias
log = get_logger
