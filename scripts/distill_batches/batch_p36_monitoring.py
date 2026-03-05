"""Monitoring — Prometheus, Grafana, alerting, SLOs, and dashboard design."""

PAIRS = [
    (
        "devops/prometheus-monitoring",
        "Show Prometheus monitoring patterns: metric types, recording rules, alerting rules, and Python instrumentation.",
        '''Prometheus monitoring and alerting:

```python
# --- Python instrumentation with prometheus_client ---

from prometheus_client import (
    Counter, Histogram, Gauge, Summary, Info,
    generate_latest, CONTENT_TYPE_LATEST,
    CollectorRegistry, multiprocess,
)
from functools import wraps
import time

# Create metrics
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

IN_PROGRESS = Gauge(
    "http_requests_in_progress",
    "Number of HTTP requests currently in progress",
    ["method"],
)

DB_POOL_SIZE = Gauge(
    "db_connection_pool_size",
    "Current database connection pool size",
    ["state"],  # active, idle, total
)

CACHE_HITS = Counter(
    "cache_operations_total",
    "Cache operations",
    ["operation"],  # hit, miss, error
)

BUSINESS_METRIC = Counter(
    "orders_created_total",
    "Total orders created",
    ["payment_method", "country"],
)


# --- FastAPI middleware ---

from fastapi import FastAPI, Request, Response

app = FastAPI()

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    method = request.method
    endpoint = request.url.path

    IN_PROGRESS.labels(method=method).inc()
    start = time.perf_counter()

    try:
        response = await call_next(request)
        REQUEST_COUNT.labels(
            method=method, endpoint=endpoint,
            status=response.status_code,
        ).inc()
        return response
    except Exception as e:
        REQUEST_COUNT.labels(
            method=method, endpoint=endpoint, status=500,
        ).inc()
        raise
    finally:
        duration = time.perf_counter() - start
        REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)
        IN_PROGRESS.labels(method=method).dec()

@app.get("/metrics")
async def metrics():
    return Response(
        generate_latest(), media_type=CONTENT_TYPE_LATEST,
    )


# --- Decorator for timing functions ---

def track_duration(metric: Histogram, **labels):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            with metric.labels(**labels).time():
                return await func(*args, **kwargs)
        return wrapper
    return decorator

@track_duration(REQUEST_DURATION, method="internal", endpoint="process_order")
async def process_order(order_id: str):
    ...
```

```yaml
# --- Prometheus recording rules ---
# prometheus/rules/api.yml

groups:
  - name: api_rules
    interval: 30s
    rules:
      # Request rate (per second, 5-minute window)
      - record: api:request_rate:5m
        expr: rate(http_requests_total[5m])

      # Error rate (percentage)
      - record: api:error_rate:5m
        expr: |
          sum(rate(http_requests_total{status=~"5.."}[5m]))
          /
          sum(rate(http_requests_total[5m]))

      # P99 latency
      - record: api:latency_p99:5m
        expr: |
          histogram_quantile(0.99,
            sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
          )

      # Apdex score (target: 0.5s tolerable: 2s)
      - record: api:apdex:5m
        expr: |
          (
            sum(rate(http_request_duration_seconds_bucket{le="0.5"}[5m]))
            + sum(rate(http_request_duration_seconds_bucket{le="2.0"}[5m]))
          ) / 2
          / sum(rate(http_request_duration_seconds_count[5m]))

  # --- Alerting rules ---
  - name: api_alerts
    rules:
      - alert: HighErrorRate
        expr: api:error_rate:5m > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate ({{ $value | humanizePercentage }})"
          description: "Error rate above 5% for 5 minutes"

      - alert: HighLatency
        expr: api:latency_p99:5m > 2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "P99 latency above 2s ({{ $value | humanize }}s)"

      - alert: HighMemoryUsage
        expr: |
          container_memory_usage_bytes / container_spec_memory_limit_bytes > 0.85
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Memory usage above 85% for {{ $labels.container }}"
```

Metric types:
1. **Counter** — monotonically increasing (requests, errors, bytes)
2. **Histogram** — value distribution in buckets (latency, sizes)
3. **Gauge** — value that goes up and down (connections, queue depth)
4. **Summary** — pre-calculated quantiles (use histogram instead when possible)

Best practices:
- Label cardinality: keep label combinations under 1000
- Recording rules: pre-compute expensive queries
- Alert on symptoms (latency, errors), not causes (CPU, memory)'''
    ),
    (
        "devops/slo-sli-patterns",
        "Show SLO/SLI patterns: defining service level objectives, error budgets, burn rate alerting, and SLO dashboards.",
        '''SLO/SLI patterns for reliability:

```python
# --- SLI/SLO definitions ---

from dataclasses import dataclass
from typing import Optional

@dataclass
class SLI:
    """Service Level Indicator — a measurement."""
    name: str
    description: str
    query: str  # PromQL query that returns a ratio (0-1)

@dataclass
class SLO:
    """Service Level Objective — a target for an SLI."""
    name: str
    sli: SLI
    target: float           # e.g., 0.999 (99.9%)
    window: str             # e.g., "30d"
    burn_rate_alert: bool = True

# --- Common SLIs ---

SLIS = {
    "availability": SLI(
        name="Availability",
        description="Proportion of successful requests",
        query="""
            sum(rate(http_requests_total{status!~"5.."}[{{window}}]))
            /
            sum(rate(http_requests_total[{{window}}]))
        """,
    ),
    "latency": SLI(
        name="Latency",
        description="Proportion of requests faster than threshold",
        query="""
            sum(rate(http_request_duration_seconds_bucket{le="0.5"}[{{window}}]))
            /
            sum(rate(http_request_duration_seconds_count[{{window}}]))
        """,
    ),
    "throughput": SLI(
        name="Throughput",
        description="Successful operations per second",
        query="""
            sum(rate(orders_created_total[{{window}}]))
        """,
    ),
}

SLOS = [
    SLO(name="API Availability", sli=SLIS["availability"],
        target=0.999, window="30d"),
    SLO(name="API Latency P50", sli=SLIS["latency"],
        target=0.99, window="30d"),
]
```

```yaml
# --- Burn rate alerting ---
# Multi-window, multi-burn-rate alerts (Google SRE approach)

groups:
  - name: slo_burn_rate
    rules:
      # Error budget: 1 - SLO target
      # 99.9% SLO = 0.1% error budget over 30 days = 43.2 minutes

      # Fast burn (14.4x) — exhausts budget in 2 days
      # Short window: 1h, Long window: 5m
      - alert: SLO_HighBurnRate_Critical
        expr: |
          (
            1 - (sum(rate(http_requests_total{status!~"5.."}[1h]))
                 / sum(rate(http_requests_total[1h])))
          ) > (14.4 * 0.001)
          and
          (
            1 - (sum(rate(http_requests_total{status!~"5.."}[5m]))
                 / sum(rate(http_requests_total[5m])))
          ) > (14.4 * 0.001)
        for: 2m
        labels:
          severity: critical
          slo: api-availability
        annotations:
          summary: "SLO burn rate 14.4x — budget exhausted in 2 days"

      # Medium burn (6x) — exhausts budget in 5 days
      - alert: SLO_MediumBurnRate_Warning
        expr: |
          (
            1 - (sum(rate(http_requests_total{status!~"5.."}[6h]))
                 / sum(rate(http_requests_total[6h])))
          ) > (6 * 0.001)
          and
          (
            1 - (sum(rate(http_requests_total{status!~"5.."}[30m]))
                 / sum(rate(http_requests_total[30m])))
          ) > (6 * 0.001)
        for: 5m
        labels:
          severity: warning
          slo: api-availability

      # Slow burn (1x) — on track to exhaust budget
      - alert: SLO_SlowBurnRate_Info
        expr: |
          (
            1 - (sum(rate(http_requests_total{status!~"5.."}[3d]))
                 / sum(rate(http_requests_total[3d])))
          ) > (1 * 0.001)
        for: 1h
        labels:
          severity: info
          slo: api-availability

      # --- Error budget remaining ---
      - record: slo:error_budget_remaining:ratio
        expr: |
          1 - (
            (1 - (
              sum(rate(http_requests_total{status!~"5.."}[30d]))
              / sum(rate(http_requests_total[30d]))
            )) / 0.001
          )
        # Returns: 1.0 = full budget, 0.0 = budget exhausted, <0 = over budget
```

```python
# --- Error budget calculation ---

def calculate_error_budget(
    total_requests: int,
    failed_requests: int,
    slo_target: float,
    window_days: int = 30,
) -> dict:
    """Calculate error budget status."""
    if total_requests == 0:
        return {"status": "no_data"}

    actual_availability = (total_requests - failed_requests) / total_requests
    error_budget_total = (1 - slo_target) * total_requests
    error_budget_used = failed_requests
    error_budget_remaining = error_budget_total - error_budget_used

    return {
        "slo_target": f"{slo_target:.3%}",
        "actual": f"{actual_availability:.4%}",
        "budget_total": int(error_budget_total),
        "budget_used": error_budget_used,
        "budget_remaining": int(max(0, error_budget_remaining)),
        "budget_remaining_pct": max(0, error_budget_remaining / error_budget_total * 100),
        "budget_exhausted": error_budget_remaining <= 0,
    }

# Example:
# 10M requests, 500 failures, 99.9% SLO
# Budget: 10,000 allowed failures
# Used: 500 (5%), Remaining: 9,500 (95%)
```

SLO framework:
1. **SLI** — measure what users experience (availability, latency, correctness)
2. **SLO** — set targets with error budget (99.9% = 43min downtime/month)
3. **Burn rate alerts** — alert when consuming budget too fast, not on thresholds
4. **Error budget** — spend on velocity (deploys, experiments); freeze when exhausted
5. **Multi-window** — combine long window (trend) + short window (still happening)'''
    ),
    (
        "devops/config-management",
        "Show configuration management patterns: environment-based config, secrets handling, feature flags, and 12-factor app config.",
        '''Configuration management following 12-factor app principles:

```python
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
import os
import json

# --- Environment-based config with validation ---

@dataclass
class DatabaseConfig:
    url: str
    pool_size: int = 10
    pool_timeout: int = 30
    echo: bool = False

@dataclass
class RedisConfig:
    url: str = "redis://localhost:6379/0"
    max_connections: int = 20

@dataclass
class AuthConfig:
    secret_key: str = ""
    token_ttl: int = 900  # 15 minutes
    refresh_ttl: int = 604800  # 7 days

@dataclass
class AppConfig:
    env: str = "development"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"
    allowed_origins: list[str] = field(default_factory=lambda: ["*"])
    database: DatabaseConfig = field(default_factory=lambda: DatabaseConfig(url=""))
    redis: RedisConfig = field(default_factory=RedisConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)

    def validate(self):
        errors = []
        if not self.database.url:
            errors.append("DATABASE_URL is required")
        if not self.auth.secret_key:
            errors.append("SECRET_KEY is required")
        if self.env == "production":
            if self.debug:
                errors.append("DEBUG must be False in production")
            if "*" in self.allowed_origins:
                errors.append("Wildcard CORS not allowed in production")
        if errors:
            raise ValueError(f"Config errors: {'; '.join(errors)}")


def load_config() -> AppConfig:
    """Load config from environment variables."""

    def env(key: str, default: str = "", cast=str):
        value = os.environ.get(key, default)
        if cast == bool:
            return value.lower() in ("true", "1", "yes")
        if cast == int:
            return int(value) if value else 0
        if cast == list:
            return [s.strip() for s in value.split(",") if s.strip()]
        return cast(value)

    config = AppConfig(
        env=env("APP_ENV", "development"),
        debug=env("DEBUG", "false", bool),
        host=env("HOST", "0.0.0.0"),
        port=env("PORT", "8000", int),
        log_level=env("LOG_LEVEL", "info"),
        allowed_origins=env("CORS_ORIGINS", "*", list),
        database=DatabaseConfig(
            url=env("DATABASE_URL"),
            pool_size=env("DB_POOL_SIZE", "10", int),
            echo=env("DB_ECHO", "false", bool),
        ),
        redis=RedisConfig(
            url=env("REDIS_URL", "redis://localhost:6379/0"),
        ),
        auth=AuthConfig(
            secret_key=env("SECRET_KEY"),
            token_ttl=env("TOKEN_TTL", "900", int),
        ),
    )

    config.validate()
    return config


# --- Feature flags ---

class FeatureFlags:
    """Simple feature flag system backed by Redis or config."""

    def __init__(self, store=None, defaults: dict[str, bool] = None):
        self.store = store  # Redis client
        self.defaults = defaults or {}

    async def is_enabled(self, flag: str, user_id: str = None) -> bool:
        """Check if feature is enabled, optionally for specific user."""
        # Check user-specific override
        if user_id and self.store:
            override = await self.store.hget(f"flags:{flag}", user_id)
            if override is not None:
                return override == "1"

        # Check global flag
        if self.store:
            global_flag = await self.store.get(f"flag:{flag}")
            if global_flag is not None:
                return global_flag == "1"

        # Check percentage rollout
        if user_id and self.store:
            pct = await self.store.get(f"flag:{flag}:pct")
            if pct is not None:
                # Deterministic: same user always gets same result
                user_hash = hash(f"{flag}:{user_id}") % 100
                return user_hash < int(pct)

        return self.defaults.get(flag, False)

    async def enable(self, flag: str, user_id: str = None):
        if user_id:
            await self.store.hset(f"flags:{flag}", user_id, "1")
        else:
            await self.store.set(f"flag:{flag}", "1")

    async def disable(self, flag: str, user_id: str = None):
        if user_id:
            await self.store.hset(f"flags:{flag}", user_id, "0")
        else:
            await self.store.set(f"flag:{flag}", "0")

    async def set_rollout(self, flag: str, percentage: int):
        """Gradual rollout to percentage of users."""
        await self.store.set(f"flag:{flag}:pct", str(percentage))


# Usage:
# flags = FeatureFlags(redis_client, defaults={"new_ui": False})
# if await flags.is_enabled("new_ui", user_id=current_user.id):
#     return new_ui_response()
# else:
#     return legacy_response()
```

```bash
# --- .env file (development only, never commit) ---
# .env
APP_ENV=development
DEBUG=true
DATABASE_URL=postgresql://app:secret@localhost:5432/appdb
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=dev-secret-change-in-production
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
LOG_LEVEL=debug
```

12-factor config rules:
1. **Environment variables** — config in env, not files or code
2. **Validation on startup** — fail fast with clear error messages
3. **No secrets in code** — use env vars, vault, or secret managers
4. **Feature flags** — decouple deploy from release
5. **Sensible defaults** — development should work with minimal config'''
    ),
]
"""
