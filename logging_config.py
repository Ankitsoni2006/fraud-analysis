"""
ivc/logging_config.py
=====================
Structured logging with JSON (production) and coloured text (dev) output.

Usage:
    from ivc.logging_config import get_logger
    log = get_logger(__name__)
    log.info("Speed violation detected", packer="PKR001", velocity_ms=42.3)
"""
from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any


class _StructuredAdapter(logging.LoggerAdapter):
    """
    Wraps stdlib Logger so callers can pass structured keyword args:
        log.info("msg", key=value, ...)
    These are serialised into the message in text mode or into JSON fields.
    """

    def process(self, msg: str, kwargs: dict) -> tuple:
        # Pull out any 'extra' kwargs the caller passed as keywords
        extra_fields = {
            k: v for k, v in kwargs.items()
            if k not in ("exc_info", "stack_info", "stacklevel")
        }
        # Remove them from kwargs so stdlib doesn't choke
        for k in extra_fields:
            kwargs.pop(k, None)

        # Store them for the formatter to access
        kwargs.setdefault("extra", {})["_structured"] = extra_fields
        return msg, kwargs


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base: dict[str, Any] = {
            "ts":      time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level":   record.levelname,
            "logger":  record.name,
            "message": record.getMessage(),
        }
        structured = getattr(record, "_structured", {})
        base.update(structured)
        if record.exc_info:
            base["exception"] = self.formatException(record.exc_info)
        return json.dumps(base, default=str)


class _TextFormatter(logging.Formatter):
    COLOURS = {
        "DEBUG":    "\033[36m",
        "INFO":     "\033[32m",
        "WARNING":  "\033[33m",
        "ERROR":    "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        colour = self.COLOURS.get(record.levelname, "")
        ts     = time.strftime("%H:%M:%S", time.localtime(record.created))
        structured = getattr(record, "_structured", {})
        extra_str  = ""
        if structured:
            extra_str = "  " + "  ".join(f"{k}={v}" for k, v in structured.items())
        return (
            f"{colour}{ts} [{record.levelname:<8}] "
            f"{record.name}: {record.getMessage()}{extra_str}{self.RESET}"
        )


def _build_handler(fmt: str) -> logging.Handler:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter() if fmt == "json" else _TextFormatter())
    return handler


def get_logger(name: str) -> _StructuredAdapter:
    from config import LOG_LEVEL, LOG_FORMAT
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.addHandler(_build_handler(LOG_FORMAT))
        logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
        logger.propagate = False
    return _StructuredAdapter(logger, {})
