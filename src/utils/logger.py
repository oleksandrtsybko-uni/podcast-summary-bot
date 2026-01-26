"""
Logging configuration for the application.
"""

import logging
import sys
from typing import Optional


def setup_logger(
    name: str = "podcast_bot",
    level: str = "INFO",
    format_string: Optional[str] = None
) -> logging.Logger:
    """
    Set up and configure a logger.
    
    Args:
        name: Logger name
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_string: Custom format string (optional)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger
    
    # Set level
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level)
    
    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    
    # Create formatter
    if format_string is None:
        format_string = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    
    formatter = logging.Formatter(format_string, datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(handler)
    
    return logger


# Default application logger
logger = setup_logger()


def get_logger(name: str = "podcast_bot") -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)
