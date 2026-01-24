"""
Logging Configuration for ABQ Daily Intelligence

Configures loguru for file and console output with rotation.
"""
import sys
from pathlib import Path
from loguru import logger


def configure_logging(
    log_dir: Path,
    date_str: str,
    console_level: str = "INFO",
    file_level: str = "DEBUG",
    rotation: str = "1 week",
    retention: str = "1 month"
) -> None:
    """
    Configure loguru for daily pipeline execution.

    Args:
        log_dir: Directory for log files
        date_str: Current date for log file naming
        console_level: Minimum level for console output
        file_level: Minimum level for file output
        rotation: Log rotation policy
        retention: Log retention policy
    """
    # Ensure log directory exists
    log_dir.mkdir(parents=True, exist_ok=True)

    # Remove default handler
    logger.remove()

    # Console handler (colorized)
    logger.add(
        sink=sys.stderr,
        level=console_level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        colorize=True
    )

    # Main log file (all levels)
    logger.add(
        sink=log_dir / f"daily_{date_str}.log",
        level=file_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation=rotation,
        retention=retention,
        encoding="utf-8"
    )

    # Error log file (ERROR+ only)
    logger.add(
        sink=log_dir / f"errors_{date_str}.log",
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}\n{exception}",
        rotation=rotation,
        retention=retention,
        encoding="utf-8"
    )

    logger.debug(f"Logging configured: console={console_level}, file={file_level}")
