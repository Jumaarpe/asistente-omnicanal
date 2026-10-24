import logging
import sys
from app.core.config import settings


def setup_logger(name: str = "asistente-omnicanal") -> logging.Logger:
    """
    Configura y devuelve un logger estructurado con formato consistente para la aplicación.
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
        logger.setLevel(level)

        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)

        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-7s | [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


logger = setup_logger()
