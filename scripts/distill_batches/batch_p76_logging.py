"""Python — structured logging, log configuration, and observability."""

PAIRS = [
    (
        "python/logging-advanced",
        "Show advanced Python logging patterns: structured logging, JSON formatters, context propagation, and log aggregation.",
        '''Advanced Python logging:

```python
import logging
import logging.config
import json
import sys
import time
import traceback
from contextvars import ContextVar
from functools import wraps
from typing import Any

# --- Context variables for request tracking ---

request_id_var: ContextVar[str] = ContextVar("request_id", default="")
user_id_var: ContextVar[str] = ContextVar("user_id", default="")


# --- JSON formatter for structured logging ---

class JSONFormatter(logging.Formatter):
    """Output logs as single-line JSON for log aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add context variables
        if rid := request_id_var.get():
            log_data["request_id"] = rid
        if uid := user_id_var.get():
            log_data["user_id"] = uid

        # Add extra fields
        if hasattr(record, "extra_data"):
            log_data.update(record.extra_data)

        # Add exception info
        if record.exc_info and record.exc_info[0]:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info),
            }

        return json.dumps(log_data, default=str)


# --- Context-aware logger ---

class ContextLogger:
    """Logger that automatically includes context variables."""

    def __init__(self, name: str):
        self._logger = logging.getLogger(name)

    def _log(self, level: int, msg: str, **kwargs):
        extra_data = kwargs.pop("extra_data", {})
        record = self._logger.makeRecord(
            self._logger.name, level, "", 0, msg, (), None,
        )
        record.extra_data = extra_data
        self._logger.handle(record)

    def info(self, msg: str, **kwargs):
        self._log(logging.INFO, msg, **kwargs)

    def error(self, msg: str, **kwargs):
        self._log(logging.ERROR, msg, **kwargs)

    def warning(self, msg: str, **kwargs):
        self._log(logging.WARNING, msg, **kwargs)


# --- Logging configuration (dict-based) ---

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": JSONFormatter,
        },
        "console": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "console",
            "stream": "ext://sys.stdout",
        },
        "file_json": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "json",
            "filename": "app.log",
            "maxBytes": 10_485_760,  # 10MB
            "backupCount": 5,
        },
    },
    "loggers": {
        "app": {
            "level": "INFO",
            "handlers": ["console", "file_json"],
        },
        "app.db": {
            "level": "WARNING",  # Less verbose for DB
        },
        "uvicorn": {
            "level": "INFO",
            "handlers": ["console"],
        },
    },
    "root": {
        "level": "WARNING",
        "handlers": ["console"],
    },
}

# Apply config
logging.config.dictConfig(LOGGING_CONFIG)


# --- Performance logging decorator ---

def log_execution(logger: logging.Logger):
    """Decorator that logs function entry, exit, and duration."""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.perf_counter()
            logger.info("Starting %s", func.__name__)
            try:
                result = await func(*args, **kwargs)
                elapsed = time.perf_counter() - start
                logger.info("%s completed in %.3fs", func.__name__, elapsed)
                return result
            except Exception:
                elapsed = time.perf_counter() - start
                logger.exception("%s failed after %.3fs", func.__name__, elapsed)
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.perf_counter()
            logger.info("Starting %s", func.__name__)
            try:
                result = func(*args, **kwargs)
                elapsed = time.perf_counter() - start
                logger.info("%s completed in %.3fs", func.__name__, elapsed)
                return result
            except Exception:
                elapsed = time.perf_counter() - start
                logger.exception("%s failed after %.3fs", func.__name__, elapsed)
                raise

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


# --- Sensitive data filter ---

class SensitiveDataFilter(logging.Filter):
    """Redact sensitive fields from log records."""

    SENSITIVE_KEYS = {"password", "token", "secret", "api_key", "ssn"}

    def filter(self, record: logging.LogRecord) -> bool:
        if hasattr(record, "extra_data"):
            record.extra_data = self._redact(record.extra_data)
        record.msg = self._redact_string(str(record.msg))
        return True

    def _redact(self, data: dict) -> dict:
        return {
            k: "***REDACTED***" if k.lower() in self.SENSITIVE_KEYS else v
            for k, v in data.items()
        }

    def _redact_string(self, msg: str) -> str:
        import re
        return re.sub(
            r'(password|token|secret|api_key)=["\']?[^"\'\\s]+',
            r'\\1=***REDACTED***',
            msg,
            flags=re.IGNORECASE,
        )
```

Logging patterns:
1. **JSON formatter** — structured logs for ELK/Datadog/CloudWatch ingestion
2. **ContextVar** — propagate request_id/user_id across async call chains
3. **Dict config** — centralized logging configuration, per-logger levels
4. **RotatingFileHandler** — prevent log files from filling disk
5. **SensitiveDataFilter** — automatically redact passwords/tokens from logs'''
    ),
]
"""
