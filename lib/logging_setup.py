"""
shared/logging_setup.py
========================
Shared logger factory for all automations.

Usage:
    from lib.logging_setup import get_logger, archive_artifact
    logger = get_logger(__name__, log_file="logs/my_automation/2026-04-29.log")
    archive_artifact("my_automation", "data/some_output.png")
"""

import logging
import shutil
import sys
from datetime import datetime
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


def archive_artifact(automation: str, src_path: str | Path,
                     subdir: str | None = None) -> Path | None:
    """Copy a generated artifact (image / PDF / report) into the per-day
    logs folder for ``automation`` so every run leaves a complete audit trail
    alongside its log file.

    Layout:  ``logs/<automation>/<YYYY-MM-DD>/<HHMM>_<original_name>``

    Returns the destination path on success, or None on failure / missing src.
    Failure is non-fatal — the data/ copy remains the canonical output.
    """
    src = Path(src_path)
    if not src.exists() or not src.is_file():
        return None
    now = datetime.now()
    base = Path("logs") / automation / now.strftime("%Y-%m-%d")
    if subdir:
        base = base / subdir
    try:
        base.mkdir(parents=True, exist_ok=True)
        dst = base / f"{now.strftime('%H%M')}_{src.name}"
        shutil.copy2(src, dst)
        return dst
    except Exception as exc:  # pragma: no cover - archival is best-effort
        logging.getLogger(__name__).warning(
            f"archive_artifact failed for {src}: {exc}"
        )
        return None


def archive_artifacts(automation: str, paths: list[str | Path]) -> list[Path]:
    """Bulk variant of :func:`archive_artifact`."""
    out: list[Path] = []
    for p in paths:
        if not p:
            continue
        d = archive_artifact(automation, p)
        if d:
            out.append(d)
    return out
