PAIRS = [
    ("projects/logging-pipeline", r'''<think>
A structured logging system needs JSON-formatted output with consistent
field naming, context propagation, and multiple output destinations.
I will build on Python's logging module but add structured formatting.
</think>
Build a structured logging pipeline with JSON output, contextual fields, and configurable log levels.''', r'''import json
import logging
import os
import sys
import time
import threading
from typing import Any, Dict, Optional


class StructuredFormatter(logging.Formatter):
    """Formats log records as JSON with consistent field names."""

    def __init__(self, service_name: str = "", extra_fields: Optional[dict] = None):
        super().__init__()
        self._service_name = service_name
        self._extra_fields = extra_fields or {}

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
            "service": self._service_name,
        }

        # Add location info
        if record.levelno >= logging.WARNING:
            log_entry["file"] = record.pathname
            log_entry["line"] = record.lineno
            log_entry["function"] = record.funcName

        # Add exception info
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info),
            }

        # Add extra fields from the record
        for key in ("correlation_id", "request_id", "user_id", "duration_ms"):
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)

        # Add any custom extra fields
        log_entry.update(self._extra_fields)

        # Add fields from the context
        ctx = LogContext.get_context()
        if ctx:
            log_entry.update(ctx)

        return json.dumps(log_entry, default=str)


class LogContext:
    """Thread-local logging context for propagating fields across calls."""

    _local = threading.local()

    @classmethod
    def set(cls, **kwargs) -> None:
        if not hasattr(cls._local, "context"):
            cls._local.context = {}
        cls._local.context.update(kwargs)

    @classmethod
    def get_context(cls) -> dict:
        return getattr(cls._local, "context", {})

    @classmethod
    def clear(cls) -> None:
        cls._local.context = {}

    @classmethod
    def bind(cls, **kwargs):
        """Context manager for temporary context."""
        class ContextBinder:
            def __init__(self, fields):
                self._fields = fields
                self._old_values = {}

            def __enter__(self):
                ctx = LogContext.get_context()
                self._old_values = {k: ctx.get(k) for k in self._fields}
                LogContext.set(**self._fields)
                return self

            def __exit__(self, *args):
                ctx = LogContext.get_context()
                for k, v in self._old_values.items():
                    if v is None:
                        ctx.pop(k, None)
                    else:
                        ctx[k] = v

        return ContextBinder(kwargs)


class LogPipeline:
    """Configures and manages the logging pipeline."""

    def __init__(self, service_name: str = "app"):
        self._service_name = service_name
        self._root_logger = logging.getLogger()

    def configure(
        self,
        level: str = "INFO",
        json_output: bool = True,
        log_file: Optional[str] = None,
        extra_fields: Optional[dict] = None,
    ) -> None:
        """Configure the logging pipeline."""
        self._root_logger.setLevel(getattr(logging, level.upper()))
        self._root_logger.handlers.clear()

        formatter = StructuredFormatter(self._service_name, extra_fields) if json_output else logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )

        # Console handler
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        self._root_logger.addHandler(console)

        # File handler
        if log_file:
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(formatter)
            self._root_logger.addHandler(file_handler)

    def get_logger(self, name: str) -> logging.Logger:
        return logging.getLogger(name)


def timed_operation(logger_instance, operation_name: str):
    """Context manager that logs operation duration."""
    class Timer:
        def __enter__(self):
            self.start = time.perf_counter()
            logger_instance.info(f"Starting {operation_name}")
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            duration = (time.perf_counter() - self.start) * 1000
            if exc_type:
                logger_instance.error(
                    f"Failed {operation_name}",
                    extra={"duration_ms": duration},
                    exc_info=(exc_type, exc_val, exc_tb),
                )
            else:
                logger_instance.info(
                    f"Completed {operation_name}",
                    extra={"duration_ms": duration},
                )
            return False

    return Timer()
'''),
    ("projects/logging-pipeline", r'''Implement log rotation with size and time-based policies, and log compression.''', r'''import gzip
import logging
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


class SizeRotatingHandler(logging.FileHandler):
    """File handler that rotates logs based on file size."""

    def __init__(
        self,
        filename: str,
        max_bytes: int = 10 * 1024 * 1024,  # 10 MB
        backup_count: int = 5,
        compress: bool = True,
        encoding: str = "utf-8",
    ):
        self._max_bytes = max_bytes
        self._backup_count = backup_count
        self._compress = compress
        self._base_filename = filename
        super().__init__(filename, encoding=encoding)

    def shouldRollover(self, record: logging.LogRecord) -> bool:
        if self._max_bytes <= 0:
            return False
        if self.stream is None:
            return False
        self.stream.seek(0, 2)  # Seek to end
        return self.stream.tell() >= self._max_bytes

    def doRollover(self) -> None:
        if self.stream:
            self.stream.close()

        # Rotate existing backups
        for i in range(self._backup_count - 1, 0, -1):
            src = self._get_backup_name(i)
            dst = self._get_backup_name(i + 1)
            if os.path.exists(src):
                if os.path.exists(dst):
                    os.remove(dst)
                os.rename(src, dst)

        # Move current to backup 1
        backup_1 = self._get_backup_name(1)
        if os.path.exists(self._base_filename):
            os.rename(self._base_filename, backup_1)
            if self._compress:
                self._compress_file(backup_1)

        # Remove excess backups
        for i in range(self._backup_count + 1, self._backup_count + 10):
            path = self._get_backup_name(i)
            if os.path.exists(path):
                os.remove(path)
            gz_path = path + ".gz"
            if os.path.exists(gz_path):
                os.remove(gz_path)

        self.stream = self._open()

    def _get_backup_name(self, index: int) -> str:
        return f"{self._base_filename}.{index}"

    def _compress_file(self, filepath: str) -> None:
        gz_path = filepath + ".gz"
        with open(filepath, "rb") as f_in:
            with gzip.open(gz_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        os.remove(filepath)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if self.shouldRollover(record):
                self.doRollover()
            super().emit(record)
        except Exception:
            self.handleError(record)


class TimeRotatingHandler(logging.FileHandler):
    """File handler that rotates logs based on time intervals."""

    def __init__(
        self,
        filename: str,
        when: str = "midnight",  # midnight, hourly
        backup_count: int = 30,
        compress: bool = True,
        encoding: str = "utf-8",
    ):
        self._when = when
        self._backup_count = backup_count
        self._compress = compress
        self._base_filename = filename
        self._next_rollover = self._compute_next_rollover()
        super().__init__(filename, encoding=encoding)

    def _compute_next_rollover(self) -> float:
        now = datetime.now()
        if self._when == "midnight":
            tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0)
            from datetime import timedelta
            tomorrow += timedelta(days=1)
            return tomorrow.timestamp()
        elif self._when == "hourly":
            next_hour = now.replace(minute=0, second=0, microsecond=0)
            from datetime import timedelta
            next_hour += timedelta(hours=1)
            return next_hour.timestamp()
        return time.time() + 86400

    def shouldRollover(self, record: logging.LogRecord) -> bool:
        return time.time() >= self._next_rollover

    def doRollover(self) -> None:
        if self.stream:
            self.stream.close()

        # Generate timestamped backup name
        now = datetime.now()
        if self._when == "midnight":
            suffix = now.strftime("%Y-%m-%d")
        else:
            suffix = now.strftime("%Y-%m-%d_%H")

        backup_name = f"{self._base_filename}.{suffix}"
        if os.path.exists(self._base_filename):
            if os.path.exists(backup_name):
                os.remove(backup_name)
            os.rename(self._base_filename, backup_name)
            if self._compress:
                gz_path = backup_name + ".gz"
                with open(backup_name, "rb") as f_in:
                    with gzip.open(gz_path, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
                os.remove(backup_name)

        # Cleanup old backups
        self._cleanup_old_backups()

        self._next_rollover = self._compute_next_rollover()
        self.stream = self._open()

    def _cleanup_old_backups(self) -> None:
        log_dir = Path(self._base_filename).parent
        base_name = Path(self._base_filename).name
        backups = sorted(log_dir.glob(f"{base_name}.*"))

        while len(backups) > self._backup_count:
            oldest = backups.pop(0)
            oldest.unlink()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if self.shouldRollover(record):
                self.doRollover()
            super().emit(record)
        except Exception:
            self.handleError(record)
'''),
    ("projects/logging-pipeline", r'''Implement remote log shipping to a central log aggregator with batching and retry.''', r'''import json
import logging
import queue
import threading
import time
import urllib.request
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class RemoteLogShipper(logging.Handler):
    """Ships log entries to a remote log aggregation service."""

    def __init__(
        self,
        endpoint_url: str,
        batch_size: int = 100,
        flush_interval: float = 5.0,
        max_retries: int = 3,
        auth_token: Optional[str] = None,
        buffer_size: int = 10000,
    ):
        super().__init__()
        self._url = endpoint_url
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._max_retries = max_retries
        self._auth_token = auth_token
        self._buffer: queue.Queue = queue.Queue(maxsize=buffer_size)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._dropped_count = 0
        self._shipped_count = 0

    def start(self) -> None:
        """Start the background shipping thread."""
        self._running = True
        self._thread = threading.Thread(target=self._ship_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop shipping and flush remaining entries."""
        self._running = False
        self._flush()
        if self._thread:
            self._thread.join(timeout=10.0)

    def emit(self, record: logging.LogRecord) -> None:
        """Add a log record to the shipping buffer."""
        try:
            log_entry = self._format_entry(record)
            self._buffer.put_nowait(log_entry)
        except queue.Full:
            self._dropped_count += 1

    def _format_entry(self, record: logging.LogRecord) -> dict:
        """Format a log record for shipping."""
        entry = {
            "timestamp": record.created,
            "level": record.levelname,
            "logger": record.name,
            "message": self.format(record) if self.formatter else record.getMessage(),
            "hostname": self._get_hostname(),
            "pid": record.process,
            "thread": record.thread,
        }

        if record.exc_info and record.exc_info[0]:
            entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
            }

        return entry

    def _get_hostname(self) -> str:
        import socket
        try:
            return socket.gethostname()
        except Exception:
            return "unknown"

    def _ship_loop(self) -> None:
        """Background loop that batches and ships log entries."""
        while self._running:
            time.sleep(self._flush_interval)
            self._flush()

    def _flush(self) -> None:
        """Collect entries from buffer and ship them."""
        batch = []
        while not self._buffer.empty() and len(batch) < self._batch_size:
            try:
                entry = self._buffer.get_nowait()
                batch.append(entry)
            except queue.Empty:
                break

        if batch:
            self._ship_batch(batch)

    def _ship_batch(self, batch: List[dict]) -> None:
        """Send a batch of log entries to the remote endpoint."""
        payload = json.dumps({"logs": batch}).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "Content-Length": str(len(payload)),
        }
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"

        for attempt in range(self._max_retries):
            try:
                req = urllib.request.Request(
                    self._url,
                    data=payload,
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status == 200:
                        self._shipped_count += len(batch)
                        return

            except Exception as e:
                if attempt < self._max_retries - 1:
                    delay = 2 ** attempt
                    time.sleep(delay)
                else:
                    self._dropped_count += len(batch)
                    logger.error(f"Failed to ship {len(batch)} log entries: {e}")

    @property
    def stats(self) -> dict:
        return {
            "buffer_size": self._buffer.qsize(),
            "shipped": self._shipped_count,
            "dropped": self._dropped_count,
        }
'''),
    ("projects/logging-pipeline", r'''<think>
Correlation IDs are critical for distributed tracing. They allow tracking
a single request across multiple services. I need middleware that generates
or extracts correlation IDs and propagates them through the logging context.
</think>
Implement correlation ID propagation for distributed request tracing across services.''', r'''import uuid
import threading
import logging
import functools
from typing import Any, Callable, Dict, Optional
from contextvars import ContextVar

# Use contextvars for async-safe context propagation
_correlation_id: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)
_request_context: ContextVar[Dict[str, Any]] = ContextVar("request_context", default={})

logger = logging.getLogger(__name__)


def get_correlation_id() -> Optional[str]:
    """Get the current correlation ID."""
    return _correlation_id.get()


def set_correlation_id(cid: Optional[str] = None) -> str:
    """Set a correlation ID. Generates one if not provided."""
    if cid is None:
        cid = str(uuid.uuid4())
    _correlation_id.set(cid)
    return cid


def get_request_context() -> Dict[str, Any]:
    """Get the full request context."""
    return dict(_request_context.get())


def set_request_context(**kwargs) -> None:
    """Set request context values."""
    ctx = dict(_request_context.get())
    ctx.update(kwargs)
    _request_context.set(ctx)


class CorrelationIDFilter(logging.Filter):
    """Logging filter that adds correlation ID to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id() or "none"
        ctx = get_request_context()
        for key, value in ctx.items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return True


class CorrelationMiddleware:
    """ASGI/WSGI middleware that manages correlation IDs per request."""

    HEADER_NAME = "X-Correlation-ID"

    def __init__(self, app):
        self._app = app

    async def __call__(self, scope, receive, send):
        """ASGI middleware entry point."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        # Extract or generate correlation ID
        headers = dict(scope.get("headers", []))
        header_key = self.HEADER_NAME.lower().encode()
        cid = None
        for h_name, h_value in scope.get("headers", []):
            if h_name == header_key:
                cid = h_value.decode()
                break

        cid = set_correlation_id(cid)
        set_request_context(
            correlation_id=cid,
            method=scope.get("method", ""),
            path=scope.get("path", ""),
        )

        # Add correlation ID to response headers
        async def send_with_correlation(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((self.HEADER_NAME.encode(), cid.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self._app(scope, receive, send_with_correlation)
        finally:
            _correlation_id.set(None)
            _request_context.set({})


def with_correlation(func: Callable) -> Callable:
    """Decorator to propagate correlation ID into background tasks."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        cid = get_correlation_id()
        ctx = get_request_context()

        def run():
            if cid:
                set_correlation_id(cid)
            if ctx:
                _request_context.set(ctx)
            return func(*args, **kwargs)

        return run()

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        cid = get_correlation_id()
        ctx = get_request_context()

        if cid:
            set_correlation_id(cid)
        if ctx:
            _request_context.set(ctx)
        return await func(*args, **kwargs)

    import asyncio
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return wrapper


class RequestLogger:
    """Structured request logging with correlation tracking."""

    def __init__(self, logger_name: str = "request"):
        self._logger = logging.getLogger(logger_name)

    def log_request_start(self, method: str, path: str, **extra) -> None:
        self._logger.info(
            f"{method} {path} started",
            extra={"method": method, "path": path, **extra},
        )

    def log_request_end(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        **extra,
    ) -> None:
        level = logging.INFO if status_code < 400 else logging.WARNING
        if status_code >= 500:
            level = logging.ERROR

        self._logger.log(
            level,
            f"{method} {path} -> {status_code} ({duration_ms:.1f}ms)",
            extra={
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": duration_ms,
                **extra,
            },
        )

    def log_error(self, error: Exception, **extra) -> None:
        self._logger.error(
            f"Request error: {type(error).__name__}: {error}",
            extra=extra,
            exc_info=True,
        )
'''),
    ("projects/logging-pipeline", r'''Implement log level management with dynamic level changes and per-module log level configuration.''', r'''import logging
import json
import threading
import time
from typing import Callable, Dict, List, Optional


class LogLevelManager:
    """Manages log levels dynamically with per-module configuration."""

    def __init__(self):
        self._module_levels: Dict[str, int] = {}
        self._default_level = logging.INFO
        self._lock = threading.Lock()
        self._change_callbacks: List[Callable] = []

    def set_default_level(self, level: str) -> None:
        """Set the default log level for all loggers."""
        numeric_level = getattr(logging, level.upper(), logging.INFO)
        self._default_level = numeric_level
        logging.getLogger().setLevel(numeric_level)
        self._notify_change("*", level)

    def set_module_level(self, module: str, level: str) -> None:
        """Set the log level for a specific module."""
        numeric_level = getattr(logging, level.upper(), logging.INFO)
        with self._lock:
            self._module_levels[module] = numeric_level
        logger = logging.getLogger(module)
        logger.setLevel(numeric_level)
        self._notify_change(module, level)

    def get_module_level(self, module: str) -> str:
        """Get the effective log level for a module."""
        with self._lock:
            level = self._module_levels.get(module)
        if level is None:
            level = logging.getLogger(module).getEffectiveLevel()
        return logging.getLevelName(level)

    def reset_module_level(self, module: str) -> None:
        """Reset a module's log level to inherit from parent."""
        with self._lock:
            self._module_levels.pop(module, None)
        logger = logging.getLogger(module)
        logger.setLevel(logging.NOTSET)

    def load_from_config(self, config: dict) -> None:
        """Load log levels from a configuration dictionary.

        Expected format:
        {
            "default": "INFO",
            "modules": {
                "app.database": "DEBUG",
                "app.api": "WARNING",
            }
        }
        """
        default = config.get("default", "INFO")
        self.set_default_level(default)

        modules = config.get("modules", {})
        for module, level in modules.items():
            self.set_module_level(module, level)

    def on_change(self, callback: Callable) -> None:
        """Register a callback for log level changes."""
        self._change_callbacks.append(callback)

    def _notify_change(self, module: str, level: str) -> None:
        for cb in self._change_callbacks:
            try:
                cb(module, level)
            except Exception:
                pass

    def get_all_levels(self) -> Dict[str, str]:
        """Get all configured module levels."""
        result = {"_default": logging.getLevelName(self._default_level)}
        with self._lock:
            for module, level in self._module_levels.items():
                result[module] = logging.getLevelName(level)
        return result

    def enable_debug_mode(self, modules: Optional[List[str]] = None) -> None:
        """Enable DEBUG level for specific modules or all."""
        if modules:
            for module in modules:
                self.set_module_level(module, "DEBUG")
        else:
            self.set_default_level("DEBUG")

    def disable_debug_mode(self) -> None:
        """Reset to INFO level."""
        self.set_default_level("INFO")
        with self._lock:
            debug_modules = [m for m, l in self._module_levels.items() if l == logging.DEBUG]
        for module in debug_modules:
            self.reset_module_level(module)


class SampledLogger:
    """Logger that samples messages to reduce volume in production."""

    def __init__(self, logger_name: str, sample_rate: float = 1.0):
        self._logger = logging.getLogger(logger_name)
        self._sample_rate = sample_rate
        self._counters: Dict[str, int] = {}
        self._lock = threading.Lock()

    def _should_log(self, key: str) -> bool:
        """Determine if this message should be logged based on sampling."""
        if self._sample_rate >= 1.0:
            return True

        with self._lock:
            count = self._counters.get(key, 0) + 1
            self._counters[key] = count

        interval = int(1.0 / self._sample_rate)
        return count % interval == 0

    def info(self, message: str, *args, sample_key: Optional[str] = None, **kwargs) -> None:
        key = sample_key or message[:50]
        if self._should_log(key):
            self._logger.info(message, *args, **kwargs)

    def warning(self, message: str, *args, **kwargs) -> None:
        self._logger.warning(message, *args, **kwargs)

    def error(self, message: str, *args, **kwargs) -> None:
        self._logger.error(message, *args, **kwargs)

    def debug(self, message: str, *args, sample_key: Optional[str] = None, **kwargs) -> None:
        key = sample_key or message[:50]
        if self._should_log(key):
            self._logger.debug(message, *args, **kwargs)


class AuditLogger:
    """Specialized logger for audit trail events."""

    def __init__(self, logger_name: str = "audit"):
        self._logger = logging.getLogger(logger_name)
        self._logger.setLevel(logging.INFO)

    def log_action(
        self,
        action: str,
        user_id: str,
        resource_type: str,
        resource_id: str,
        details: Optional[dict] = None,
        outcome: str = "success",
    ) -> None:
        """Log an auditable action."""
        self._logger.info(
            f"AUDIT: {action} on {resource_type}/{resource_id} by {user_id}",
            extra={
                "audit": True,
                "action": action,
                "user_id": user_id,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "outcome": outcome,
                "details": details or {},
                "audit_timestamp": time.time(),
            },
        )
'''),
]
