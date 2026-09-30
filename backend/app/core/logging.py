"""Structured logging configuration."""
import logging
import sys


def setup_logging() -> None:
    log_format = "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[logging.StreamHandler(sys.stdout)],
    )


logger = logging.getLogger("cardarena")
