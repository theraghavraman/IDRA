"""Operational logs contain error codes, never telemetry payloads."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from idra.storage.files import private_dir


def configure(root: Path):
    private_dir(root)
    target = root / "application.log"
    handler = RotatingFileHandler(target, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    target.chmod(0o600)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger = logging.getLogger("idra")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.propagate = False
    return logger
