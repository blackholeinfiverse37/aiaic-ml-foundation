"""
Structured JSON logger for the AIAIC ML Foundation service.

Every log line is a valid JSON object so it can be ingested by any
log aggregator (Datadog, CloudWatch, ELK) without parsing.

Usage:
    from src.observability.logger import get_logger
    logger = get_logger(__name__)
    logger.info("prediction made", extra={"request_id": "abc123"})
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict


class StructuredFormatter(logging.Formatter):
    """
    Formats every log record as a single-line JSON object.
    Standard fields: timestamp, level, logger, message.
    Extra fields from the `extra` dict are merged at the top level.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_object: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Merge any extra fields passed via logger.info(..., extra={...})
        for key, value in record.__dict__.items():
            if key not in (
                "timestamp", "level", "logger", "message",
                "msg", "args", "exc_info", "exc_text", "stack_info",
                "levelname", "levelno", "pathname", "filename",
                "module", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "name",
                "lineno",
            ):
                log_object[key] = value

        if record.exc_info:
            log_object["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_object, default=str)


def setup_structured_logging(level: str = "INFO") -> None:
    """
    Call once at application startup to configure structured logging
    globally. After this, every logger in the process emits JSON.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))


def get_logger(name: str) -> logging.Logger:
    """Convenience wrapper — use instead of logging.getLogger() directly."""
    return logging.getLogger(name)