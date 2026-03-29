"""
shared/logging_setup.py
========================
Shared logger factory for all automations.

Usage:
    from lib.logging_setup import get_logger
    logger = get_logger(__name__, log_file="data/my_automation.log")
"""

import logging
import sys
from pathlib import Path


def get_logger(name: str, log_file: str | None = None,
               level: int = logging.INFO) -> logging.Logger:
    """
    Return a named logger with a StreamHandler (stdout) and an optional
    FileHandler.  Safe to call multiple times — handlers are not added twice.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured

    logger.setLevel(level)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s")

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger
