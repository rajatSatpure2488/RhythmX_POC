"""
Loguru setup for the standalone DrChrono backend.
"""

import sys
from pathlib import Path

from loguru import logger


BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "dr_chrono_backend.log"


def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(
        sys.stderr,
        level="DEBUG",
        colorize=True,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )
    logger.add(
        LOG_FILE,
        level="DEBUG",
        rotation="10 MB",
        retention="10 days",
        compression="zip",
        enqueue=True,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    )
    logger.success("DrChrono backend logging initialized. log_file={}", LOG_FILE)
    return LOG_FILE
