"""Logging — structured logging, log levels, rotation, and observability patterns."""

PAIRS = [
    (
        "python/logging-configuration",
        "Show Python logging best practices: configuration, handlers, formatters, structured logging, and log aggregation.",
        '''Production Python logging configuration:

```python
import logging
import logging.config
import json
import sys
from datetime import datetime, timezone
from typing import Any
from contextvars import ContextVar

# Context variable for request tracking
request_id_var: ContextVar[str] = ContextVar("request_id", default="")

# --- Structured JSON formatter ---

class JSONFormatter(logging.Formatter):
    """Output logs as JSON for log aggregation (ELK, Datadog, etc)."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add request context
        request_id = request_id_var.get("")
        if request_id:
            log_data["request_id"] = request_id

        # Add extra fields
        if hasattr(record, "extra_data"):
            log_data.update(record.extra_data)

        # Add exception info
        if record.exc_info and record.exc_info[0]:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info),
            }

        return json.dumps(log_data, default=str)


# --- Logging configuration ---

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "app.logging.JSONFormatter",
        },
        "console": {
            "format": "%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
            "datefmt": "%H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "console",
            "stream": "ext://sys.stdout",
        },
        "json_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "json",
            "filename": "/var/log/app/app.log",
            "maxBytes": 10_485_760,  # 10MB
            "backupCount": 5,
        },
        "error_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "json",
            "filename": "/var/log/app/error.log",
            "maxBytes": 10_485_760,
            "backupCount": 10,
            "level": "ERROR",
        },
    },
    "loggers": {
        "app": {
            "level": "INFO",
            "handlers": ["console", "json_file", "error_file"],
            "propagate": False,
        },
        "uvicorn": {
            "level": "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
        "sqlalchemy.engine": {
            "level": "WARNING",
            "handlers": ["console"],
            "propagate": False,
        },
    },
    "root": {
        "level": "WARNING",
        "handlers": ["console"],
    },
}

def setup_logging(env: str = "development"):
    """Configure logging based on environment."""
    if env == "production":
        # JSON output for log aggregation
        LOGGING_CONFIG["handlers"]["console"]["formatter"] = "json"
    logging.config.dictConfig(LOGGING_CONFIG)


# --- Contextual logger ---

class AppLogger:
    """Logger with automatic context injection."""

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)

    def _log(self, level: int, message: str, **kwargs):
        extra_data = kwargs
        self.logger.log(
            level, message,
            extra={"extra_data": extra_data},
        )

    def info(self, message: str, **kwargs):
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs):
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs):
        self._log(logging.ERROR, message, **kwargs)

    def exception(self, message: str, **kwargs):
        self.logger.exception(
            message,
            extra={"extra_data": kwargs},
        )

# Usage:
logger = AppLogger("app.orders")
logger.info("Order created",
    order_id="ord-123",
    user_id="user-456",
    total=99.99,
    items_count=3,
)
# Output (JSON):
# {"timestamp": "...", "level": "INFO", "message": "Order created",
#  "order_id": "ord-123", "user_id": "user-456", "total": 99.99, ...}


# --- Log level guide ---

# DEBUG — detailed diagnostic information (only in development)
logger.logger.debug("SQL query: SELECT * FROM users WHERE id = %s", user_id)

# INFO — general operational events
logger.info("User logged in", user_id=user_id, method="oauth")

# WARNING — something unexpected but handled
logger.warning("Rate limit approaching", current=95, limit=100)

# ERROR — operation failed, needs attention
logger.error("Payment failed", order_id=order_id, error=str(e))

# CRITICAL — system-level failure
logger.logger.critical("Database connection pool exhausted")
```

Best practices:
1. **Structured logging** — JSON format for machine parsing and search
2. **Context propagation** — request_id in every log for tracing
3. **Log levels** — DEBUG in dev, INFO in staging, WARNING+ in production
4. **Extra fields** — use kwargs for structured data, not string formatting
5. **Rotation** — `RotatingFileHandler` prevents disk filling up
6. **Separate error log** — easier to monitor for failures'''
    ),
]
