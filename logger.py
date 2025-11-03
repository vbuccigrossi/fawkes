# fawkes/logger.py

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

try:
    import colorlog
    HAS_COLORLOG = True
except ImportError:
    HAS_COLORLOG = False


def setup_fawkes_logger(
    log_level=logging.DEBUG,
    log_to_file=True,
    log_to_console=False,
    max_bytes=5 * 1024 * 1024,
    backup_count=5,
    use_color=True
):
    logger = logging.getLogger("fawkes")
    logger.setLevel(log_level)

    # Clear existing handlers if rerun
    if logger.hasHandlers():
        logger.handlers.clear()

    # Only add console handler if requested
    if log_to_console:
        if use_color and HAS_COLORLOG:
            console_formatter = colorlog.ColoredFormatter(
                fmt="%(log_color)s[%(levelname)s]%(reset)s %(name)s - %(message)s",
                log_colors={
                    "DEBUG": "cyan",
                    "INFO": "green",
                    "WARNING": "yellow",
                    "ERROR": "red",
                    "CRITICAL": "bold_red",
                },
            )
            ch = logging.StreamHandler(sys.stdout)
            ch.setLevel(log_level)
            ch.setFormatter(console_formatter)
        else:
            ch = logging.StreamHandler(sys.stdout)
            ch.setLevel(log_level)
            fmt = logging.Formatter("[%(levelname)s] %(name)s - %(message)s")
            ch.setFormatter(fmt)
        logger.addHandler(ch)

    # file handler (rotating)
    if log_to_file:
        log_file = os.path.expanduser("~/.fawkes/fawkes.log")
        # RotatingFileHandler will rotate logs once they exceed max_bytes,
        # keeping up to backup_count old logs in the same directory
        fh = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        fh.setLevel(log_level)
        file_fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        fh.setFormatter(file_fmt)
        logger.addHandler(fh)

    logger.debug("Fawkes logger configured. Colorlog: %s, log_to_file: %s", HAS_COLORLOG, log_to_file)
    return logger

