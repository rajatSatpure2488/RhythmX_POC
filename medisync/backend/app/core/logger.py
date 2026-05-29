"""
MediSync — Centralized Logger
Writes to both console and a single rotating log file (backend + frontend events).
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Log directory — medisync/logs/
LOG_DIR  = Path(__file__).resolve().parents[3] / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "medisync.log"

LOG_FORMAT  = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# force=True so we win against uvicorn's default handlers.
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt=DATE_FORMAT,
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=3, encoding="utf-8"),
    ],
    force=True,
)

# Quiet down the chattiest third parties so the file stays readable.
logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
logging.getLogger("watchfiles").setLevel(logging.WARNING)

logger = logging.getLogger("medisync")
logger.info(f"Logger initialized — writing to {LOG_FILE}")
