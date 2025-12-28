from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


def configure_logger(
    name: str = "web2mp3",
    log_file: Optional[str | Path] = None,
    *,
    console: bool = True,
    level: int = logging.INFO,
    max_bytes: int = 5_000_000,
    backup_count: int = 3,
) -> logging.Logger:
    """Create/configure a standard library logger.

    Safe to call multiple times: it avoids adding duplicate handlers for the same destination.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(process)d] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    def _has_handler(handler_type, predicate=None) -> bool:
        for h in logger.handlers:
            if isinstance(h, handler_type) and (predicate(h) if predicate else True):
                return True
        return False

    if console and not _has_handler(logging.StreamHandler, lambda h: getattr(h, "_web2mp3_console", False)):
        sh = logging.StreamHandler()
        sh.setLevel(level)
        sh.setFormatter(formatter)
        sh._web2mp3_console = True  # type: ignore[attr-defined]
        logger.addHandler(sh)

    if log_file is not None:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        def same_file(h: logging.Handler) -> bool:
            return getattr(h, "baseFilename", None) == str(log_file)

        if not _has_handler(RotatingFileHandler, same_file):
            fh = RotatingFileHandler(
                str(log_file),
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            fh.setLevel(level)
            fh.setFormatter(formatter)
            logger.addHandler(fh)

    return logger
