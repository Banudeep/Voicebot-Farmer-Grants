"""
Logging Configuration for USDA Voicebot

Provides centralized, configurable logging with:
- Console and file output
- Log level configuration via config.DEBUG
- Structured formatting for production
"""

import logging
import os
import sys
from pathlib import Path
from typing import Optional

# Log levels mapping
LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

# Get debug setting from config (import lazily to avoid circular imports)
def _get_debug_setting():
    try:
        import config
        return config.DEBUG
    except ImportError:
        return os.getenv("DEBUG", "false").lower() == "true"

# Default log level based on config.DEBUG
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Log file path (optional)
# Path: src/logging_config.py -> src -> root
BASE_DIR = Path(__file__).parent.parent
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = os.getenv("LOG_FILE", "")  # Set to enable file logging


def get_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """
    Get a configured logger instance.
    
    Args:
        name: Logger name (typically __name__ of the calling module)
        level: Optional log level override ("DEBUG", "INFO", "WARNING", "ERROR")
    
    Returns:
        Configured logging.Logger instance
    """
    logger = logging.getLogger(name)
    
    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger
    
    # Determine log level: explicit override > config.DEBUG > INFO
    if level:
        log_level = LOG_LEVELS.get(level.upper(), logging.INFO)
    elif _get_debug_setting():
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO
    
    logger.setLevel(log_level)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    logger.addHandler(console_handler)
    
    # File handler (optional)
    if LOG_FILE:
        LOG_DIR.mkdir(exist_ok=True)
        file_handler = logging.FileHandler(LOG_DIR / LOG_FILE, encoding="utf-8")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
        logger.addHandler(file_handler)
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    return logger


# Convenience loggers for common modules
def get_llm_logger() -> logging.Logger:
    """Get logger for LLM stream module"""
    return get_logger("voicebot.llm")


def get_tool_logger(tool_name: str) -> logging.Logger:
    """Get logger for a specific tool"""
    return get_logger(f"voicebot.tools.{tool_name}")


def get_api_logger() -> logging.Logger:
    """Get logger for API calls"""
    return get_logger("voicebot.api")


# Emoji mappings for log levels (for visual debugging)
EMOJI_MAP = {
    "DEBUG": "🔍",
    "INFO": "ℹ️",
    "WARNING": "⚠️",
    "ERROR": "❌",
    "CRITICAL": "🚨",
    "SUCCESS": "✅",
    "TOOL": "🔧",
    "API": "🌐",
}


def log_with_emoji(logger: logging.Logger, level: str, emoji_key: str, message: str):
    """Log a message with an emoji prefix for visual debugging"""
    emoji = EMOJI_MAP.get(emoji_key, "")
    log_method = getattr(logger, level.lower(), logger.info)
    log_method(f"{emoji} {message}")


if __name__ == "__main__":
    # Test logging configuration
    logger = get_logger("test")
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
    print("✓ Logging configuration test complete")
