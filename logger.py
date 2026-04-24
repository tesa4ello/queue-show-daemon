# logger.py
import logging
import sys
from config import cfg

def setup_logger(name: str = "proxy") -> logging.Logger:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if cfg.LOG_FILE:
        handlers.append(logging.FileHandler(cfg.LOG_FILE, encoding="utf-8"))

    logging.basicConfig(
        level=getattr(logging, cfg.LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)-7s] %(name)s | %(message)s",
        handlers=handlers,
        force=True,
    )
    return logging.getLogger(name)
