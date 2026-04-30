"""
Centralised logging configuration.
Writes to logs/app.log + console.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

from src.config import LOG_FILE


def setup_logger(name: str = "dashboard", level: int = logging.INFO) -> logging.Logger:
    """Return a configured logger that writes to file + stderr."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured

    logger.setLevel(level)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(logging.WARNING)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    return logger


# Module-level convenience
log = setup_logger()
