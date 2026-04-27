"""
MediSync — Centralized Logger
Writes to both console and a rotating log file.
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Log directory — medisync/logs/
LOG_DIR  = Path(__file__).resolve().parents[3] / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "medisync_backend.log"

# ── Format ────────────────────────────────────────────────
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ── Root logger ───────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format=LOG_FORMAT,
    datefmt=DATE_FORMAT,
    handlers=[
        # Console
        logging.StreamHandler(),
        # Rotating file: 5 MB × 3 backups
        RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=3, encoding="utf-8"),
    ],
)

logger = logging.getLogger("medisync")
logger.info(f"Logger initialized — writing to {LOG_FILE}")
