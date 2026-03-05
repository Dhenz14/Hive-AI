"""URL shortener system design — base62 encoding, Snowflake IDs, redirect caching, analytics, custom aliases, rate limiting."""

PAIRS = [
    (
        "url-shortener/base62-encoding",
        "Implement base62 encoding for URL shortener short codes, with collision-free ID generation using a Snowflake-like distributed ID generator, and configurable code length.",
        '''Base62 encoding with Snowflake distributed ID generation for URL shortener:

```python
# id_generator.py — Snowflake ID + base62 encoding for short URL codes
import time
import threading
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Base62 alphabet: 0-9, A-Z, a-z (URL-safe, no ambiguous characters)
BASE62_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
BASE62_MAP = {c: i for i, c in enumerate(BASE62_ALPHABET)}


def base62_encode(num: int) -> str:
    """Convert a positive integer to a base62 string.

    Used to generate short URL codes from numeric IDs.
    6 characters = 62^6 = 56.8 billion unique codes.
    7 characters = 62^7 = 3.5 trillion unique codes.
    """
    if num == 0:
        return BASE62_ALPHABET[0]

    result = []
    while num > 0:
        num, remainder = divmod(num, 62)
        result.append(BASE62_ALPHABET[remainder])

    return "".join(reversed(result))


def base62_decode(code: str) -> int:
    """Convert a base62 string back to an integer."""
    num = 0
    for char in code:
        num = num * 62 + BASE62_MAP[char]
    return num


def base62_encode_padded(num: int, min_length: int = 7) -> str:
    """Encode with zero-padding to ensure minimum length."""
    encoded = base62_encode(num)
    return encoded.zfill(min_length) if len(encoded) < min_length else encoded


class SnowflakeIDGenerator:
    """Twitter Snowflake-inspired distributed ID generator.

    64-bit ID layout:
    ┌──────────────────────┬──────────┬───────────┐
    │  41 bits: timestamp  │ 10 bits: │ 12 bits:  │
    │  (ms since epoch)    │ worker   │ sequence  │
    └──────────────────────┴──────────┴───────────┘

    Properties:
    - Monotonically increasing within a worker
    - Unique across workers (worker_id differentiates)
    - ~69 years before timestamp overflow (41 bits of ms)
    - 4096 IDs per millisecond per worker
    - Sortable by time (most significant bits are timestamp)
    """

    # Custom epoch: 2024-01-01T00:00:00Z
    EPOCH_MS = 1704067200000

    TIMESTAMP_BITS = 41
    WORKER_BITS = 10
    SEQUENCE_BITS = 12

    MAX_WORKER_ID = (1 << WORKER_BITS) - 1      # 1023
    MAX_SEQUENCE = (1 << SEQUENCE_BITS) - 1       # 4095

    WORKER_SHIFT = SEQUENCE_BITS                   # 12
    TIMESTAMP_SHIFT = SEQUENCE_BITS + WORKER_BITS  # 22

    def __init__(self, worker_id: int = 0):
        if worker_id < 0 or worker_id > self.MAX_WORKER_ID:
            raise ValueError(f"Worker ID must be 0-{self.MAX_WORKER_ID}")

        self.worker_id = worker_id
        self._sequence = 0
        self._last_timestamp = -1
        self._lock = threading.Lock()

    def _current_ms(self) -> int:
        return int(time.time() * 1000) - self.EPOCH_MS

    def generate(self) -> int:
        """Generate a unique 64-bit ID (thread-safe)."""
        with self._lock:
            timestamp = self._current_ms()

            if timestamp < self._last_timestamp:
                # Clock went backwards — wait until it catches up
                logger.warning(
                    f"Clock moved backwards by {self._last_timestamp - timestamp}ms"
                )
                while timestamp <= self._last_timestamp:
                    timestamp = self._current_ms()

            if timestamp == self._last_timestamp:
                # Same millisecond: increment sequence
                self._sequence = (self._sequence + 1) & self.MAX_SEQUENCE
                if self._sequence == 0:
                    # Sequence exhausted: wait for next millisecond
                    while timestamp == self._last_timestamp:
                        timestamp = self._current_ms()
            else:
                self._sequence = 0

            self._last_timestamp = timestamp

            return (
                (timestamp << self.TIMESTAMP_SHIFT) |
                (self.worker_id << self.WORKER_SHIFT) |
                self._sequence
            )

    def generate_short_code(self, min_length: int = 7) -> str:
        """Generate a unique short code by encoding a Snowflake ID as base62."""
        snowflake_id = self.generate()
        return base62_encode_padded(snowflake_id, min_length)

    @staticmethod
    def extract_timestamp(snowflake_id: int) -> float:
        """Extract the Unix timestamp from a Snowflake ID."""
        timestamp_ms = (snowflake_id >> SnowflakeIDGenerator.TIMESTAMP_SHIFT)
        return (timestamp_ms + SnowflakeIDGenerator.EPOCH_MS) / 1000.0

    @staticmethod
    def extract_worker_id(snowflake_id: int) -> int:
        return (snowflake_id >> SnowflakeIDGenerator.WORKER_SHIFT) & SnowflakeIDGenerator.MAX_WORKER_ID


# ============================================================
# Alternative: Counter-based ID with base62
# ============================================================

class CounterIDGenerator:
    """Simple counter-based generator using Redis INCR.

    Simpler than Snowflake but requires a central coordinator (Redis).
    """

    def __init__(self, redis_client, counter_key: str = "url:id_counter", start: int = 100000):
        self.redis = redis_client
        self.counter_key = counter_key
        self._start = start

    async def initialize(self):
        """Set initial counter value if not exists."""
        exists = await self.redis.exists(self.counter_key)
        if not exists:
            await self.redis.set(self.counter_key, self._start)

    async def generate_short_code(self, min_length: int = 7) -> str:
        counter = await self.redis.incr(self.counter_key)
        return base62_encode_padded(counter, min_length)
```

ID generation comparison:

| Strategy | Throughput | Coordination | Ordering | Collision Risk |
|---|---|---|---|---|
| Snowflake ID + base62 | 4096/ms/worker | None (worker_id) | Time-ordered | Zero |
| Redis INCR + base62 | ~100K/s | Redis required | Sequential | Zero |
| Random base62 | Unlimited | None | None | ~1 in 62^7 per pair |
| UUID v4 + truncate | Unlimited | None | None | Higher (birthday paradox) |
| Hash(URL) + truncate | Unlimited | None | None | Medium (collisions) |

Key ID generation patterns:
- Snowflake IDs are time-sortable, enabling "recent links" queries without extra indices
- Base62 is URL-safe and more compact than base64 (no +, /, =)
- 7-character codes give 3.5 trillion unique values (enough for most services)
- Clock backwards protection prevents duplicate IDs during NTP adjustments
- Worker ID ensures uniqueness across multiple server instances
- Redis counter is simpler but adds a dependency and single point of failure
'''
    ),
    (
        "url-shortener/redirect-service",
        "Build the core URL shortener redirect service with Redis caching, database persistence, custom aliases, expiration support, and proper HTTP redirect handling (301 vs 302).",
        '''URL shortener redirect service with caching, custom aliases, and expiration:

```python
# shortener.py — Core URL shortener service with Redis cache + PostgreSQL persistence
import asyncio
import time
import hashlib
import re
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import asyncpg
import redis.asyncio as redis
from pydantic import BaseModel, Field, field_validator
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from id_generator import SnowflakeIDGenerator, base62_encode_padded

logger = logging.getLogger(__name__)

app = FastAPI()


# ============================================================
# Models
# ============================================================

class CreateShortURLRequest(BaseModel):
    url: str
    custom_alias: str | None = None     # Optional custom short code
    expires_at: datetime | None = None  # Optional expiration
    password: str | None = None         # Optional password protection
    max_clicks: int | None = None       # Optional click limit

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("URL must start with http:// or https://")
        if not parsed.netloc:
            raise ValueError("Invalid URL: missing domain")
        return v

    @field_validator("custom_alias")
    @classmethod
    def validate_alias(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not re.match(r"^[a-zA-Z0-9_-]{3,30}$", v):
            raise ValueError("Alias must be 3-30 alphanumeric characters, hyphens, or underscores")
        # Block reserved words
        reserved = {"api", "admin", "health", "metrics", "static", "docs"}
        if v.lower() in reserved:
            raise ValueError(f"Alias '{v}' is reserved")
        return v


class ShortURL(BaseModel):
    short_code: str
    original_url: str
    created_at: datetime
    expires_at: datetime | None = None
    click_count: int = 0
    max_clicks: int | None = None
    is_active: bool = True
    creator_ip: str = ""
    password_hash: str | None = None


class ShortURLResponse(BaseModel):
    short_code: str
    short_url: str
    original_url: str
    expires_at: datetime | None = None
    created_at: datetime


# ============================================================
# URL Shortener Service
# ============================================================

class URLShortenerService:
    """Core URL shortener with Redis cache-aside pattern and PostgreSQL persistence."""

    BASE_URL = "https://short.io"
    CACHE_TTL = 86400          # 24h cache for popular links
    CACHE_TTL_404 = 300        # 5 min negative cache for missing codes

    def __init__(self, pool: asyncpg.Pool, r: redis.Redis, worker_id: int = 0):
        self.pool = pool
        self.redis = r
        self.id_gen = SnowflakeIDGenerator(worker_id=worker_id)

    async def initialize(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS short_urls (
                    short_code    TEXT PRIMARY KEY,
                    original_url  TEXT NOT NULL,
                    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    expires_at    TIMESTAMPTZ,
                    click_count   BIGINT NOT NULL DEFAULT 0,
                    max_clicks    INTEGER,
                    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
                    creator_ip    TEXT NOT NULL DEFAULT '',
                    password_hash TEXT,
                    url_hash      TEXT NOT NULL  -- SHA256 of original URL for dedup
                );
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_url_hash ON short_urls(url_hash);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_expires ON short_urls(expires_at)
                WHERE expires_at IS NOT NULL AND is_active = TRUE;
            """)

    async def create_short_url(
        self,
        request: CreateShortURLRequest,
        creator_ip: str = "",
    ) -> ShortURLResponse:
        """Create a new short URL with optional custom alias."""
        url_hash = hashlib.sha256(request.url.encode()).hexdigest()

        # Check for custom alias
        if request.custom_alias:
            short_code = request.custom_alias
            # Verify alias not taken
            existing = await self._lookup_db(short_code)
            if existing:
                raise HTTPException(status_code=409, detail="Alias already taken")
        else:
            # Check if URL was already shortened (deduplication)
            existing_code = await self._find_by_url_hash(url_hash)
            if existing_code:
                return ShortURLResponse(
                    short_code=existing_code,
                    short_url=f"{self.BASE_URL}/{existing_code}",
                    original_url=request.url,
                    created_at=datetime.now(timezone.utc),
                )
            short_code = self.id_gen.generate_short_code(min_length=7)

        # Hash password if provided
        password_hash = None
        if request.password:
            password_hash = hashlib.sha256(request.password.encode()).hexdigest()

        # Persist to database
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO short_urls
                    (short_code, original_url, expires_at, max_clicks,
                     creator_ip, password_hash, url_hash)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """, short_code, request.url, request.expires_at,
                request.max_clicks, creator_ip, password_hash, url_hash)

        # Prime the cache
        await self._cache_set(short_code, request.url, request.expires_at)

        logger.info(f"Created short URL: {short_code} -> {request.url[:80]}")

        return ShortURLResponse(
            short_code=short_code,
            short_url=f"{self.BASE_URL}/{short_code}",
            original_url=request.url,
            expires_at=request.expires_at,
            created_at=datetime.now(timezone.utc),
        )

    async def resolve(self, short_code: str) -> str | None:
        """Resolve short code to original URL. Uses cache-aside pattern.

        Cache-aside: Check cache first. On miss, query DB and populate cache.
        This keeps the cache warm for popular links while the DB remains
        the source of truth.
        """
        # 1. Check Redis cache
        cached = await self.redis.get(f"url:{short_code}")
        if cached is not None:
            if cached == b"__404__":
                return None  # Negative cache hit
            return cached.decode()

        # 2. Cache miss — query database
        url = await self._lookup_db(short_code)
        if url is None:
            # Negative cache: prevent repeated DB lookups for invalid codes
            await self.redis.set(f"url:{short_code}", "__404__", ex=self.CACHE_TTL_404)
            return None

        # 3. Populate cache
        await self._cache_set(short_code, url)
        return url

    async def _lookup_db(self, short_code: str) -> str | None:
        """Query database for a short code."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT original_url, expires_at, is_active, max_clicks, click_count
                FROM short_urls
                WHERE short_code = $1
            """, short_code)

        if row is None:
            return None

        # Check if expired
        if row["expires_at"] and row["expires_at"] < datetime.now(timezone.utc):
            return None

        # Check if deactivated
        if not row["is_active"]:
            return None

        # Check click limit
        if row["max_clicks"] and row["click_count"] >= row["max_clicks"]:
            return None

        return row["original_url"]

    async def _find_by_url_hash(self, url_hash: str) -> str | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT short_code FROM short_urls WHERE url_hash = $1 AND is_active = TRUE",
                url_hash,
            )
        return row["short_code"] if row else None

    async def _cache_set(self, short_code: str, url: str, expires_at=None):
        ttl = self.CACHE_TTL
        if expires_at:
            remaining = (expires_at - datetime.now(timezone.utc)).total_seconds()
            ttl = max(60, min(ttl, int(remaining)))
        await self.redis.set(f"url:{short_code}", url, ex=ttl)

    async def increment_click(self, short_code: str):
        """Increment click counter (async, non-blocking to redirect)."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE short_urls SET click_count = click_count + 1 WHERE short_code = $1",
                short_code,
            )

    async def deactivate(self, short_code: str):
        """Soft-delete a short URL."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE short_urls SET is_active = FALSE WHERE short_code = $1",
                short_code,
            )
        await self.redis.delete(f"url:{short_code}")


# ============================================================
# HTTP Endpoints
# ============================================================

service: URLShortenerService | None = None


@app.post("/api/shorten", response_model=ShortURLResponse)
async def shorten_url(req: CreateShortURLRequest, request: Request):
    return await service.create_short_url(req, creator_ip=request.client.host)


@app.get("/{short_code}")
async def redirect(short_code: str):
    """Redirect short URL to original.

    Uses 301 (permanent) by default for SEO and caching.
    Use 302 (temporary) if analytics tracking needs every click
    to hit the server (301 may be cached by browsers).
    """
    url = await service.resolve(short_code)
    if url is None:
        raise HTTPException(status_code=404, detail="Short URL not found or expired")

    # Fire-and-forget click tracking (don't delay the redirect)
    asyncio.create_task(service.increment_click(short_code))

    # 302 for analytics (browser won't cache, every click hits server)
    # 301 for performance (browser caches, fewer server requests)
    return RedirectResponse(url=url, status_code=302)
```

| HTTP Status | Redirect Type | Browser Caches | Analytics | SEO |
|---|---|---|---|---|
| 301 Moved Permanently | Permanent | Yes (indefinitely) | Misses repeat visits | Passes PageRank |
| 302 Found | Temporary | No | Tracks every click | Does not pass PageRank |
| 307 Temporary Redirect | Temporary (preserves method) | No | Tracks every click | Does not pass PageRank |

Key URL shortener patterns:
- Cache-aside with negative caching prevents DB hammering for invalid codes
- URL deduplication via SHA-256 hash prevents duplicate short codes for the same URL
- Snowflake IDs guarantee uniqueness without DB coordination
- Custom alias validation blocks reserved words and enforces format
- Soft-delete (is_active flag) preserves analytics history
- Fire-and-forget click tracking keeps redirect latency < 5ms
'''
    ),
    (
        "url-shortener/analytics-tracking",
        "Build an analytics tracking system for URL shortener that captures click events with geo, device, referrer data, stores in a time-series format, and provides aggregated dashboards.",
        '''URL shortener analytics with click tracking, geo/device data, and aggregated dashboards:

```python
# analytics.py — Click analytics with geo, device, referrer tracking
import asyncio
import time
import hashlib
import logging
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any
from user_agents import parse as parse_ua

import asyncpg
import redis.asyncio as redis
from pydantic import BaseModel, Field
from fastapi import Request

logger = logging.getLogger(__name__)


class ClickEvent(BaseModel):
    """Single click event with context."""
    short_code: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ip_hash: str = ""            # SHA256 of IP (privacy-preserving)
    country: str = "unknown"
    city: str = "unknown"
    referrer: str = ""
    referrer_domain: str = ""
    user_agent: str = ""
    browser: str = "unknown"
    os: str = "unknown"
    device_type: str = "unknown" # desktop, mobile, tablet, bot
    is_unique: bool = True       # First click from this IP+code combo


class AnalyticsSummary(BaseModel):
    """Aggregated analytics for a short URL."""
    short_code: str
    total_clicks: int = 0
    unique_clicks: int = 0
    clicks_today: int = 0
    clicks_this_week: int = 0

    # Top breakdowns
    top_countries: list[dict[str, Any]] = Field(default_factory=list)
    top_referrers: list[dict[str, Any]] = Field(default_factory=list)
    top_browsers: list[dict[str, Any]] = Field(default_factory=list)
    top_os: list[dict[str, Any]] = Field(default_factory=list)
    device_breakdown: dict[str, int] = Field(default_factory=dict)

    # Time series (hourly clicks for last 7 days)
    hourly_clicks: list[dict[str, Any]] = Field(default_factory=list)


class AnalyticsService:
    """Tracks and aggregates click analytics for short URLs."""

    def __init__(self, pool: asyncpg.Pool, r: redis.Redis):
        self.pool = pool
        self.redis = r

    async def initialize(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS click_events (
                    id          BIGSERIAL,
                    short_code  TEXT NOT NULL,
                    clicked_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    ip_hash     TEXT NOT NULL,
                    country     TEXT NOT NULL DEFAULT 'unknown',
                    city        TEXT NOT NULL DEFAULT 'unknown',
                    referrer    TEXT NOT NULL DEFAULT '',
                    referrer_domain TEXT NOT NULL DEFAULT '',
                    browser     TEXT NOT NULL DEFAULT 'unknown',
                    os          TEXT NOT NULL DEFAULT 'unknown',
                    device_type TEXT NOT NULL DEFAULT 'unknown',
                    is_unique   BOOLEAN NOT NULL DEFAULT TRUE
                );
            """)

            # TimescaleDB hypertable for efficient time-range queries
            await conn.execute("""
                SELECT create_hypertable(
                    'click_events', 'clicked_at',
                    chunk_time_interval => INTERVAL '1 day',
                    if_not_exists => TRUE
                );
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_clicks_code_time
                ON click_events (short_code, clicked_at DESC);
            """)

            # Continuous aggregate: hourly rollups
            await conn.execute("""
                CREATE MATERIALIZED VIEW IF NOT EXISTS click_events_hourly
                WITH (timescaledb.continuous) AS
                SELECT
                    time_bucket('1 hour', clicked_at) AS bucket,
                    short_code,
                    COUNT(*) AS total_clicks,
                    COUNT(*) FILTER (WHERE is_unique) AS unique_clicks,
                    COUNT(DISTINCT country) AS country_count
                FROM click_events
                GROUP BY bucket, short_code
                WITH NO DATA;
            """)

            await conn.execute("""
                SELECT add_continuous_aggregate_policy('click_events_hourly',
                    start_offset => INTERVAL '3 hours',
                    end_offset => INTERVAL '1 hour',
                    schedule_interval => INTERVAL '30 minutes',
                    if_not_exists => TRUE
                );
            """)

    async def track_click(self, short_code: str, request: Request):
        """Record a click event with full context extraction."""
        # Extract client info
        ip = request.client.host
        ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:16]
        ua_string = request.headers.get("user-agent", "")
        referrer = request.headers.get("referer", "")

        # Parse user agent
        ua = parse_ua(ua_string)
        browser = f"{ua.browser.family}"
        os_name = f"{ua.os.family}"
        if ua.is_mobile:
            device_type = "mobile"
        elif ua.is_tablet:
            device_type = "tablet"
        elif ua.is_bot:
            device_type = "bot"
        else:
            device_type = "desktop"

        # Extract referrer domain
        referrer_domain = ""
        if referrer:
            from urllib.parse import urlparse
            parsed = urlparse(referrer)
            referrer_domain = parsed.netloc

        # Check uniqueness: has this IP clicked this code before?
        unique_key = f"click_unique:{short_code}:{ip_hash}"
        is_unique = not await self.redis.exists(unique_key)
        if is_unique:
            await self.redis.set(unique_key, "1", ex=86400 * 30)  # 30 day window

        # GeoIP lookup (placeholder — use MaxMind GeoIP2 in production)
        country = await self._geoip_lookup(ip)

        event = ClickEvent(
            short_code=short_code,
            ip_hash=ip_hash,
            country=country,
            referrer=referrer,
            referrer_domain=referrer_domain,
            user_agent=ua_string,
            browser=browser,
            os=os_name,
            device_type=device_type,
            is_unique=is_unique,
        )

        # Persist event (fire-and-forget for low latency)
        asyncio.create_task(self._persist_event(event))

        # Update real-time counters in Redis
        asyncio.create_task(self._update_counters(event))

    async def _persist_event(self, event: ClickEvent):
        """Insert click event into TimescaleDB."""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO click_events
                        (short_code, clicked_at, ip_hash, country, city,
                         referrer, referrer_domain, browser, os, device_type, is_unique)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                    event.short_code, event.timestamp, event.ip_hash,
                    event.country, event.city, event.referrer, event.referrer_domain,
                    event.browser, event.os, event.device_type, event.is_unique,
                )
        except Exception:
            logger.exception("Failed to persist click event")

    async def _update_counters(self, event: ClickEvent):
        """Update Redis counters for real-time dashboard."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        hour = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")

        async with self.redis.pipeline(transaction=False) as pipe:
            # Total clicks
            await pipe.incr(f"clicks:total:{event.short_code}")
            # Daily clicks
            await pipe.incr(f"clicks:daily:{event.short_code}:{today}")
            await pipe.expire(f"clicks:daily:{event.short_code}:{today}", 86400 * 7)
            # Hourly clicks
            await pipe.incr(f"clicks:hourly:{event.short_code}:{hour}")
            await pipe.expire(f"clicks:hourly:{event.short_code}:{hour}", 86400 * 2)
            # Country counter
            await pipe.hincrby(f"clicks:country:{event.short_code}", event.country, 1)
            # Referrer counter
            if event.referrer_domain:
                await pipe.hincrby(f"clicks:referrer:{event.short_code}", event.referrer_domain, 1)
            # Device counter
            await pipe.hincrby(f"clicks:device:{event.short_code}", event.device_type, 1)
            await pipe.execute()

    async def _geoip_lookup(self, ip: str) -> str:
        """GeoIP lookup. Replace with MaxMind GeoIP2 in production."""
        # Placeholder — in production:
        # import geoip2.database
        # reader = geoip2.database.Reader('/path/to/GeoLite2-City.mmdb')
        # response = reader.city(ip)
        # return response.country.iso_code
        return "US"

    async def get_summary(self, short_code: str) -> AnalyticsSummary:
        """Get aggregated analytics summary combining Redis counters and DB queries."""
        # Real-time counters from Redis
        total = int(await self.redis.get(f"clicks:total:{short_code}") or 0)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        clicks_today = int(await self.redis.get(f"clicks:daily:{short_code}:{today}") or 0)

        # Top breakdowns from Redis hashes
        countries = await self.redis.hgetall(f"clicks:country:{short_code}")
        referrers = await self.redis.hgetall(f"clicks:referrer:{short_code}")
        devices = await self.redis.hgetall(f"clicks:device:{short_code}")

        def sorted_breakdown(data: dict, limit: int = 10) -> list[dict]:
            items = [(k.decode(), int(v)) for k, v in data.items()]
            items.sort(key=lambda x: x[1], reverse=True)
            return [{"name": k, "count": v} for k, v in items[:limit]]

        # Hourly time series from continuous aggregate
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        async with self.pool.acquire() as conn:
            hourly = await conn.fetch("""
                SELECT bucket, total_clicks, unique_clicks
                FROM click_events_hourly
                WHERE short_code = $1 AND bucket >= $2
                ORDER BY bucket
            """, short_code, week_ago)

        # Unique clicks from DB
        async with self.pool.acquire() as conn:
            unique_row = await conn.fetchrow("""
                SELECT COUNT(*) FILTER (WHERE is_unique) AS unique_clicks,
                       COUNT(*) FILTER (WHERE clicked_at >= NOW() - INTERVAL '7 days') AS week_clicks
                FROM click_events
                WHERE short_code = $1
            """, short_code)

        return AnalyticsSummary(
            short_code=short_code,
            total_clicks=total,
            unique_clicks=unique_row["unique_clicks"] if unique_row else 0,
            clicks_today=clicks_today,
            clicks_this_week=unique_row["week_clicks"] if unique_row else 0,
            top_countries=sorted_breakdown(countries),
            top_referrers=sorted_breakdown(referrers),
            device_breakdown={k.decode(): int(v) for k, v in devices.items()},
            hourly_clicks=[
                {"time": row["bucket"].isoformat(), "total": row["total_clicks"], "unique": row["unique_clicks"]}
                for row in hourly
            ],
        )
```

| Analytics Layer | Data | Latency | Storage |
|---|---|---|---|
| Redis counters | Real-time totals, daily, hourly | < 1ms | Small (per-code counters) |
| Redis hashes | Top countries, referrers, devices | < 1ms | Medium (per-code hash) |
| TimescaleDB raw | Full click events | 5-50ms | Large (per-click rows) |
| Continuous aggregates | Hourly/daily rollups | 5-20ms | Medium (materialized) |

Key analytics patterns:
- IP hashing (SHA-256 truncated) preserves privacy while enabling uniqueness checks
- Fire-and-forget persistence keeps redirect latency under 5ms
- Redis counters provide instant real-time dashboards
- TimescaleDB continuous aggregates pre-compute hourly rollups automatically
- User-agent parsing extracts browser, OS, device type
- Uniqueness window (30 days) balances accuracy with storage
'''
    ),
    (
        "url-shortener/rate-limiting",
        "Implement rate limiting for a URL shortener API using token bucket and sliding window algorithms, with per-user and per-IP limits, burst handling, and Redis-based distributed rate limiting.",
        '''Distributed rate limiting with token bucket and sliding window algorithms:

```python
# rate_limiter.py — Distributed rate limiting for URL shortener API
import time
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

import redis.asyncio as redis
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


@dataclass
class RateLimitResult:
    allowed: bool
    limit: int               # Maximum requests in window
    remaining: int           # Remaining requests
    reset_at: float          # Unix timestamp when limit resets
    retry_after: float = 0   # Seconds until next request is allowed


class RateLimitTier(Enum):
    """Rate limit tiers for different user types."""
    ANONYMOUS = ("anon", 10, 60)        # 10 req/min
    FREE = ("free", 100, 60)            # 100 req/min
    PRO = ("pro", 1000, 60)             # 1000 req/min
    ENTERPRISE = ("enterprise", 10000, 60)  # 10K req/min

    def __init__(self, key_prefix: str, limit: int, window_seconds: int):
        self.key_prefix = key_prefix
        self.limit = limit
        self.window_seconds = window_seconds


# ============================================================
# 1. Sliding Window Counter (Redis MULTI)
# ============================================================

class SlidingWindowLimiter:
    """Sliding window rate limiter using Redis sorted sets.

    More accurate than fixed windows (no boundary burst problem).
    Each request is stored as a sorted set member with score = timestamp.
    Window is always relative to current time.
    """

    def __init__(self, r: redis.Redis):
        self.redis = r

    async def check(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult:
        """Check and consume one request from the sliding window.

        Atomic operation using Redis pipeline:
        1. Remove expired entries (outside window)
        2. Count current entries
        3. If under limit, add new entry
        4. Set TTL on the key
        """
        now = time.time()
        window_start = now - window_seconds

        async with self.redis.pipeline(transaction=True) as pipe:
            # Remove entries outside the window
            await pipe.zremrangebyscore(key, 0, window_start)
            # Count entries in the window
            await pipe.zcard(key)
            # Results of the above two commands
            results = await pipe.execute()

        current_count = results[1]

        if current_count >= limit:
            # Find when the oldest entry expires
            oldest = await self.redis.zrange(key, 0, 0, withscores=True)
            if oldest:
                retry_after = oldest[0][1] + window_seconds - now
            else:
                retry_after = window_seconds
            return RateLimitResult(
                allowed=False,
                limit=limit,
                remaining=0,
                reset_at=now + retry_after,
                retry_after=max(0, retry_after),
            )

        # Add new entry
        await self.redis.zadd(key, {f"{now}:{id(key)}": now})
        await self.redis.expire(key, window_seconds + 1)

        return RateLimitResult(
            allowed=True,
            limit=limit,
            remaining=limit - current_count - 1,
            reset_at=now + window_seconds,
        )


# ============================================================
# 2. Token Bucket (Redis Lua Script)
# ============================================================

class TokenBucketLimiter:
    """Token bucket rate limiter using a Redis Lua script for atomicity.

    Allows burst traffic up to bucket capacity, then limits to refill rate.
    Good for APIs that need to handle occasional traffic spikes.
    """

    # Lua script runs atomically on Redis (no race conditions)
    LUA_SCRIPT = """
    local key = KEYS[1]
    local capacity = tonumber(ARGV[1])
    local refill_rate = tonumber(ARGV[2])  -- tokens per second
    local now = tonumber(ARGV[3])
    local requested = tonumber(ARGV[4])

    -- Get current bucket state
    local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
    local tokens = tonumber(bucket[1])
    local last_refill = tonumber(bucket[2])

    -- Initialize if first request
    if tokens == nil then
        tokens = capacity
        last_refill = now
    end

    -- Refill tokens based on elapsed time
    local elapsed = now - last_refill
    local new_tokens = elapsed * refill_rate
    tokens = math.min(capacity, tokens + new_tokens)
    last_refill = now

    -- Check if we have enough tokens
    local allowed = 0
    local remaining = tokens

    if tokens >= requested then
        tokens = tokens - requested
        remaining = tokens
        allowed = 1
    end

    -- Save state
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', last_refill)
    redis.call('EXPIRE', key, math.ceil(capacity / refill_rate) + 1)

    -- Return: allowed, remaining, retry_after
    local retry_after = 0
    if allowed == 0 then
        retry_after = (requested - tokens) / refill_rate
    end

    return {allowed, math.floor(remaining), tostring(retry_after)}
    """

    def __init__(self, r: redis.Redis):
        self.redis = r
        self._script_sha: str | None = None

    async def _ensure_script(self):
        if self._script_sha is None:
            self._script_sha = await self.redis.script_load(self.LUA_SCRIPT)

    async def check(
        self,
        key: str,
        capacity: int,
        refill_rate: float,  # tokens per second
        tokens_requested: int = 1,
    ) -> RateLimitResult:
        """Check and consume tokens from the bucket.

        Args:
            capacity: Maximum tokens (burst size)
            refill_rate: Tokens added per second
            tokens_requested: Tokens to consume (1 for simple rate limiting)
        """
        await self._ensure_script()
        now = time.time()

        result = await self.redis.evalsha(
            self._script_sha,
            1,  # number of keys
            key,
            str(capacity),
            str(refill_rate),
            str(now),
            str(tokens_requested),
        )

        allowed = bool(result[0])
        remaining = int(result[1])
        retry_after = float(result[2])

        return RateLimitResult(
            allowed=allowed,
            limit=capacity,
            remaining=remaining,
            reset_at=now + (capacity - remaining) / refill_rate if refill_rate > 0 else now,
            retry_after=retry_after,
        )


# ============================================================
# 3. Composite Rate Limiter (multiple layers)
# ============================================================

class CompositeRateLimiter:
    """Applies multiple rate limit layers: per-IP, per-user, per-endpoint."""

    def __init__(self, r: redis.Redis):
        self.redis = r
        self.sliding_window = SlidingWindowLimiter(r)
        self.token_bucket = TokenBucketLimiter(r)

    async def check_request(
        self,
        request: Request,
        user_id: str | None = None,
        tier: RateLimitTier = RateLimitTier.ANONYMOUS,
    ) -> RateLimitResult:
        """Apply layered rate limiting."""
        ip = request.client.host
        endpoint = request.url.path

        # Layer 1: Global per-IP limit (prevent abuse from single IP)
        ip_result = await self.sliding_window.check(
            key=f"rl:ip:{ip}",
            limit=30,               # 30 requests per minute per IP
            window_seconds=60,
        )
        if not ip_result.allowed:
            return ip_result

        # Layer 2: Per-user tier limit
        if user_id:
            user_result = await self.token_bucket.check(
                key=f"rl:user:{user_id}",
                capacity=tier.limit,
                refill_rate=tier.limit / tier.window_seconds,
            )
            if not user_result.allowed:
                return user_result
        else:
            # Anonymous: stricter sliding window
            anon_result = await self.sliding_window.check(
                key=f"rl:anon:{ip}",
                limit=RateLimitTier.ANONYMOUS.limit,
                window_seconds=RateLimitTier.ANONYMOUS.window_seconds,
            )
            if not anon_result.allowed:
                return anon_result

        # Layer 3: Per-endpoint burst protection (e.g., /api/shorten is more expensive)
        if endpoint == "/api/shorten":
            endpoint_result = await self.sliding_window.check(
                key=f"rl:endpoint:{ip}:{endpoint}",
                limit=5,             # Max 5 shortens per minute per IP
                window_seconds=60,
            )
            if not endpoint_result.allowed:
                return endpoint_result

        return ip_result  # Return the first layer's result for headers


# ============================================================
# FastAPI Middleware
# ============================================================

class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that applies rate limiting and sets standard headers."""

    def __init__(self, app, redis_client: redis.Redis):
        super().__init__(app)
        self.limiter = CompositeRateLimiter(redis_client)

    async def dispatch(self, request: Request, call_next):
        # Skip health check and static files
        if request.url.path in ("/health", "/favicon.ico"):
            return await call_next(request)

        # Extract user from auth header (simplified)
        user_id = request.headers.get("X-User-ID")
        tier = RateLimitTier.ANONYMOUS
        if user_id:
            tier_header = request.headers.get("X-Rate-Tier", "free")
            tier = {
                "free": RateLimitTier.FREE,
                "pro": RateLimitTier.PRO,
                "enterprise": RateLimitTier.ENTERPRISE,
            }.get(tier_header, RateLimitTier.FREE)

        result = await self.limiter.check_request(request, user_id, tier)

        if not result.allowed:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded", "retry_after": result.retry_after},
                headers={
                    "X-RateLimit-Limit": str(result.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(result.reset_at)),
                    "Retry-After": str(int(result.retry_after)),
                },
            )

        response = await call_next(request)

        # Add rate limit headers to successful responses
        response.headers["X-RateLimit-Limit"] = str(result.limit)
        response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        response.headers["X-RateLimit-Reset"] = str(int(result.reset_at))

        return response
```

| Algorithm | Accuracy | Burst Handling | Memory | Complexity |
|---|---|---|---|---|
| Fixed window | Low (boundary burst) | None | O(1) per key | Simple |
| Sliding window log | Highest | None | O(N) per key | Medium |
| Sliding window counter (this) | High | Smooth | O(N) per key | Medium |
| Token bucket (this) | High | Configurable burst | O(1) per key | Medium (Lua) |
| Leaky bucket | High | Smooths to fixed rate | O(1) per key | Simple |

Key rate limiting patterns:
- Lua scripts ensure atomicity in Redis (no race conditions between check and update)
- Token bucket allows burst traffic up to capacity, then throttles to refill rate
- Sliding window avoids fixed-window boundary problem (double-burst at window edge)
- Composite layers: IP limit catches abuse, user limit enforces tier, endpoint limit protects expensive ops
- Standard headers (X-RateLimit-*, Retry-After) enable clients to self-throttle
- Middleware applies limits globally; endpoint decorators can override
'''
    ),
    (
        "url-shortener/custom-aliases",
        "Implement custom alias management for URL shortener with reservation, validation, profanity filtering, premium alias marketplace, and conflict resolution.",
        '''Custom alias system with validation, profanity filtering, and reservation:

```python
# aliases.py — Custom alias management with validation and reservations
import re
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

import asyncpg
import redis.asyncio as redis
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AliasStatus(str):
    AVAILABLE = "available"
    TAKEN = "taken"
    RESERVED = "reserved"
    BLOCKED = "blocked"       # Profanity, trademark, etc.
    PREMIUM = "premium"       # Requires paid plan


class AliasCheckResult(BaseModel):
    alias: str
    status: str
    reason: str = ""
    suggestions: list[str] = Field(default_factory=list)


class AliasReservation(BaseModel):
    alias: str
    user_id: str
    reserved_at: datetime
    expires_at: datetime
    claimed: bool = False


# Blocklist: profanity, offensive terms, trademarks, system paths
BLOCKED_PATTERNS: list[re.Pattern] = [
    re.compile(r"^(api|admin|static|health|docs|login|signup|settings)$", re.I),
    re.compile(r"^(www|mail|ftp|ssh|dns|smtp|pop3|imap)$", re.I),
    # Add profanity patterns here (use a library like better-profanity in production)
]

# Premium aliases: short (1-3 chars), dictionary words
PREMIUM_MAX_LENGTH = 3


class AliasValidator:
    """Validates custom aliases against rules, blocklists, and availability."""

    FORMAT_RULES = {
        "min_length": 3,
        "max_length": 30,
        "pattern": re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*[a-zA-Z0-9]$"),
        "no_consecutive_special": re.compile(r"[-_]{2,}"),
    }

    def validate_format(self, alias: str) -> tuple[bool, str]:
        """Check alias format against rules."""
        if len(alias) < self.FORMAT_RULES["min_length"]:
            return False, f"Alias must be at least {self.FORMAT_RULES['min_length']} characters"
        if len(alias) > self.FORMAT_RULES["max_length"]:
            return False, f"Alias must be at most {self.FORMAT_RULES['max_length']} characters"
        if not self.FORMAT_RULES["pattern"].match(alias):
            return False, "Alias must start and end with alphanumeric, containing only letters, numbers, hyphens, underscores"
        if self.FORMAT_RULES["no_consecutive_special"].search(alias):
            return False, "Alias cannot contain consecutive hyphens or underscores"
        return True, ""

    def check_blocklist(self, alias: str) -> tuple[bool, str]:
        """Check against blocked patterns (profanity, reserved, trademarks)."""
        for pattern in BLOCKED_PATTERNS:
            if pattern.search(alias):
                return True, "This alias is reserved or contains blocked content"
        return False, ""

    def is_premium(self, alias: str) -> bool:
        """Short aliases (1-3 chars) and dictionary words are premium."""
        if len(alias) <= PREMIUM_MAX_LENGTH:
            return True
        # In production: check against a dictionary
        return False

    def generate_suggestions(self, alias: str, count: int = 5) -> list[str]:
        """Generate alternative aliases when the requested one is taken."""
        suggestions = []
        # Append numbers
        for i in range(1, 100):
            candidate = f"{alias}{i}"
            if len(candidate) <= self.FORMAT_RULES["max_length"]:
                suggestions.append(candidate)
            if len(suggestions) >= count:
                break

        # Prefix/suffix variations
        variations = [f"my-{alias}", f"{alias}-link", f"go-{alias}", f"the-{alias}"]
        for v in variations:
            if self.FORMAT_RULES["pattern"].match(v) and len(v) <= self.FORMAT_RULES["max_length"]:
                suggestions.append(v)
            if len(suggestions) >= count * 2:
                break

        return suggestions[:count]


class AliasService:
    """Manages custom aliases: check, reserve, claim, release."""

    RESERVATION_DURATION = timedelta(minutes=10)  # Hold alias for 10 min

    def __init__(self, pool: asyncpg.Pool, r: redis.Redis):
        self.pool = pool
        self.redis = r
        self.validator = AliasValidator()

    async def initialize(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS alias_reservations (
                    alias       TEXT PRIMARY KEY,
                    user_id     TEXT NOT NULL,
                    reserved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    expires_at  TIMESTAMPTZ NOT NULL,
                    claimed     BOOLEAN NOT NULL DEFAULT FALSE
                );
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_reservation_expires
                ON alias_reservations(expires_at) WHERE claimed = FALSE;
            """)

    async def check_alias(
        self, alias: str, user_id: str | None = None
    ) -> AliasCheckResult:
        """Check if an alias is available and valid."""

        # 1. Validate format
        valid, reason = self.validator.validate_format(alias)
        if not valid:
            return AliasCheckResult(
                alias=alias,
                status=AliasStatus.BLOCKED,
                reason=reason,
                suggestions=self.validator.generate_suggestions(alias),
            )

        # 2. Check blocklist
        blocked, reason = self.validator.check_blocklist(alias)
        if blocked:
            return AliasCheckResult(
                alias=alias,
                status=AliasStatus.BLOCKED,
                reason=reason,
                suggestions=self.validator.generate_suggestions(alias),
            )

        # 3. Check premium
        if self.validator.is_premium(alias):
            return AliasCheckResult(
                alias=alias,
                status=AliasStatus.PREMIUM,
                reason="Short aliases require a Pro plan",
            )

        # 4. Check if already used as a short URL
        existing = await self.redis.get(f"url:{alias}")
        if existing:
            return AliasCheckResult(
                alias=alias,
                status=AliasStatus.TAKEN,
                reason="Alias is already in use",
                suggestions=self.validator.generate_suggestions(alias),
            )

        # 5. Check active reservations
        async with self.pool.acquire() as conn:
            reservation = await conn.fetchrow("""
                SELECT user_id, expires_at, claimed
                FROM alias_reservations
                WHERE alias = $1 AND (claimed = TRUE OR expires_at > NOW())
            """, alias)

        if reservation:
            if reservation["claimed"]:
                return AliasCheckResult(
                    alias=alias,
                    status=AliasStatus.TAKEN,
                    reason="Alias is already claimed",
                    suggestions=self.validator.generate_suggestions(alias),
                )
            if user_id and reservation["user_id"] == user_id:
                return AliasCheckResult(
                    alias=alias,
                    status=AliasStatus.RESERVED,
                    reason="You have this alias reserved",
                )
            return AliasCheckResult(
                alias=alias,
                status=AliasStatus.RESERVED,
                reason="Alias is temporarily reserved by another user",
                suggestions=self.validator.generate_suggestions(alias),
            )

        return AliasCheckResult(alias=alias, status=AliasStatus.AVAILABLE)

    async def reserve_alias(self, alias: str, user_id: str) -> AliasReservation:
        """Temporarily reserve an alias for a user (10-minute hold)."""
        check = await self.check_alias(alias, user_id)
        if check.status not in (AliasStatus.AVAILABLE, AliasStatus.RESERVED):
            raise ValueError(f"Cannot reserve alias: {check.reason}")

        now = datetime.now(timezone.utc)
        expires = now + self.RESERVATION_DURATION

        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO alias_reservations (alias, user_id, reserved_at, expires_at)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (alias) DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    reserved_at = EXCLUDED.reserved_at,
                    expires_at = EXCLUDED.expires_at,
                    claimed = FALSE
                WHERE alias_reservations.expires_at < NOW()
                   OR alias_reservations.user_id = EXCLUDED.user_id
            """, alias, user_id, now, expires)

        # Set Redis key for quick availability checks
        await self.redis.set(
            f"alias_reserved:{alias}",
            user_id,
            ex=int(self.RESERVATION_DURATION.total_seconds()),
        )

        return AliasReservation(
            alias=alias,
            user_id=user_id,
            reserved_at=now,
            expires_at=expires,
        )

    async def claim_alias(self, alias: str, user_id: str) -> bool:
        """Convert a reservation into a permanent claim."""
        async with self.pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE alias_reservations
                SET claimed = TRUE
                WHERE alias = $1
                  AND user_id = $2
                  AND expires_at > NOW()
                  AND claimed = FALSE
            """, alias, user_id)

        if result == "UPDATE 0":
            return False

        await self.redis.delete(f"alias_reserved:{alias}")
        return True

    async def release_alias(self, alias: str, user_id: str):
        """Release a reserved alias."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM alias_reservations
                WHERE alias = $1 AND user_id = $2 AND claimed = FALSE
            """, alias, user_id)
        await self.redis.delete(f"alias_reserved:{alias}")

    async def cleanup_expired_reservations(self):
        """Background job to clean up expired reservations."""
        async with self.pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM alias_reservations
                WHERE expires_at < NOW() AND claimed = FALSE
            """)
        logger.info(f"Cleaned up expired reservations: {result}")
```

Alias lifecycle:

```
User types alias
       |
  Validate format
  (3-30 chars, alphanumeric)
       |
  Check blocklist
  (profanity, reserved, trademarks)
       |
  Check availability
  (Redis cache + DB reservations)
       |
  ┌────┴────────┐
  |             |
Available     Taken
  |             |
Reserve       Suggest
(10 min hold) alternatives
  |
  Create short URL
  (claim reservation)
```

| Alias Status | Meaning | User Action |
|---|---|---|
| AVAILABLE | Free to use | Reserve immediately |
| TAKEN | Already in use as short URL | View suggestions |
| RESERVED | Held by another user (< 10 min) | Wait or choose alternative |
| BLOCKED | Matches blocklist | Choose different alias |
| PREMIUM | Short/valuable alias | Upgrade plan |

Key alias patterns:
- Two-phase commit: reserve then claim prevents race conditions
- 10-minute reservation window balances UX with availability
- Suggestions generate alternatives (append numbers, prefixes)
- Expired reservations are cleaned up by background job
- Redis provides fast availability checks; PostgreSQL is source of truth
- ON CONFLICT with condition allows re-reserving expired aliases
'''
    ),
    (
        "url-shortener/system-architecture",
        "Design the complete system architecture for a URL shortener that handles 100M URLs and 10B redirects per month, including service decomposition, database schema, caching strategy, and deployment topology.",
        '''Complete URL shortener system architecture for 100M URLs / 10B redirects per month:

```python
# architecture.py — System architecture documentation as code
from dataclasses import dataclass, field
from enum import Enum


# ============================================================
# Capacity Estimation
# ============================================================

@dataclass
class CapacityEstimate:
    """Back-of-envelope capacity planning."""

    # Traffic
    urls_per_month: int = 100_000_000        # 100M new URLs/month
    redirects_per_month: int = 10_000_000_000  # 10B redirects/month
    read_write_ratio: float = 100              # 100:1 reads to writes

    @property
    def urls_per_second(self) -> float:
        return self.urls_per_month / (30 * 24 * 3600)  # ~38.5 URL/s

    @property
    def redirects_per_second(self) -> float:
        return self.redirects_per_month / (30 * 24 * 3600)  # ~3,858 redirect/s

    @property
    def peak_redirects_per_second(self) -> float:
        return self.redirects_per_second * 3  # 3x peak = ~11,574 redirect/s

    # Storage (5 year retention)
    @property
    def total_urls_5_years(self) -> int:
        return self.urls_per_month * 12 * 5  # 6 billion URLs

    @property
    def url_record_bytes(self) -> int:
        return 500  # ~500 bytes per URL record (code + url + metadata)

    @property
    def total_storage_tb(self) -> float:
        return (self.total_urls_5_years * self.url_record_bytes) / (1024**4)  # ~2.7 TB

    @property
    def cache_storage_gb(self) -> float:
        # Cache top 20% of URLs (Pareto: 20% of URLs get 80% of traffic)
        hot_urls = self.total_urls_5_years * 0.2
        return (hot_urls * 200) / (1024**3)  # ~223 GB Redis

    def summary(self) -> str:
        return f"""
Capacity Estimates:
  Write rate: {self.urls_per_second:.1f} URLs/sec
  Read rate:  {self.redirects_per_second:.0f} redirects/sec
  Peak reads: {self.peak_redirects_per_second:.0f} redirects/sec
  Total URLs (5yr): {self.total_urls_5_years / 1e9:.1f}B
  Storage: {self.total_storage_tb:.1f} TB
  Cache: {self.cache_storage_gb:.0f} GB
"""


# ============================================================
# Service Architecture
# ============================================================

class ServiceComponent(Enum):
    API_GATEWAY = "api-gateway"
    REDIRECT_SERVICE = "redirect-service"
    URL_SERVICE = "url-service"
    ANALYTICS_SERVICE = "analytics-service"
    WORKER_SERVICE = "worker-service"


@dataclass
class ServiceSpec:
    name: str
    description: str
    instances: int
    cpu: str
    memory: str
    endpoints: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


ARCHITECTURE = {
    ServiceComponent.API_GATEWAY: ServiceSpec(
        name="API Gateway (Nginx/Envoy)",
        description="Load balancer, TLS termination, rate limiting, request routing",
        instances=3,
        cpu="4 vCPU",
        memory="8 GB",
        endpoints=["/*"],
        dependencies=[],
    ),
    ServiceComponent.REDIRECT_SERVICE: ServiceSpec(
        name="Redirect Service",
        description="Hot path: resolve short code -> 302 redirect. "
                    "Latency-critical, reads only from Redis cache, "
                    "falls back to DB on cache miss.",
        instances=10,
        cpu="2 vCPU",
        memory="4 GB",
        endpoints=["GET /{code}"],
        dependencies=["Redis Cluster", "PostgreSQL (read replica)"],
    ),
    ServiceComponent.URL_SERVICE: ServiceSpec(
        name="URL Service",
        description="CRUD for short URLs: create, update, delete, "
                    "custom aliases, validation. Write path.",
        instances=5,
        cpu="2 vCPU",
        memory="4 GB",
        endpoints=[
            "POST /api/shorten",
            "GET /api/urls/{code}",
            "DELETE /api/urls/{code}",
            "PUT /api/urls/{code}",
        ],
        dependencies=["Redis Cluster", "PostgreSQL (primary)", "Snowflake ID Generator"],
    ),
    ServiceComponent.ANALYTICS_SERVICE: ServiceSpec(
        name="Analytics Service",
        description="Click tracking, aggregation, dashboards. "
                    "Async processing via Kafka.",
        instances=3,
        cpu="4 vCPU",
        memory="8 GB",
        endpoints=[
            "GET /api/analytics/{code}",
            "GET /api/analytics/{code}/timeseries",
        ],
        dependencies=["Kafka", "TimescaleDB", "Redis (counters)"],
    ),
    ServiceComponent.WORKER_SERVICE: ServiceSpec(
        name="Worker Service",
        description="Background jobs: expired URL cleanup, "
                    "cache warming, analytics aggregation.",
        instances=2,
        cpu="2 vCPU",
        memory="4 GB",
        endpoints=[],
        dependencies=["PostgreSQL", "Redis", "Kafka"],
    ),
}


# ============================================================
# Database Schema
# ============================================================

DATABASE_SCHEMA = """
-- Primary PostgreSQL database with read replicas

-- Core URL table (partitioned by creation month for efficient cleanup)
CREATE TABLE short_urls (
    short_code      TEXT PRIMARY KEY,
    original_url    TEXT NOT NULL,
    url_hash        TEXT NOT NULL,          -- SHA256 for dedup index
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    click_count     BIGINT NOT NULL DEFAULT 0,
    max_clicks      INTEGER,
    creator_user_id TEXT,
    creator_ip      INET NOT NULL,
    password_hash   TEXT,
    custom_alias    BOOLEAN NOT NULL DEFAULT FALSE,
    metadata        JSONB DEFAULT '{}'
) PARTITION BY RANGE (created_at);

-- Monthly partitions (auto-created by pg_partman)
CREATE TABLE short_urls_2026_01 PARTITION OF short_urls
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

-- Indexes
CREATE INDEX idx_url_hash ON short_urls (url_hash);
CREATE INDEX idx_expires ON short_urls (expires_at)
    WHERE expires_at IS NOT NULL AND is_active = TRUE;
CREATE INDEX idx_creator ON short_urls (creator_user_id)
    WHERE creator_user_id IS NOT NULL;

-- Click events (TimescaleDB hypertable)
CREATE TABLE click_events (
    id              BIGSERIAL,
    short_code      TEXT NOT NULL,
    clicked_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ip_hash         TEXT NOT NULL,
    country         TEXT DEFAULT 'unknown',
    referrer_domain TEXT DEFAULT '',
    browser         TEXT DEFAULT 'unknown',
    os              TEXT DEFAULT 'unknown',
    device_type     TEXT DEFAULT 'unknown',
    is_unique       BOOLEAN DEFAULT TRUE
);

SELECT create_hypertable('click_events', 'clicked_at',
    chunk_time_interval => INTERVAL '1 day');

-- User accounts
CREATE TABLE users (
    user_id     TEXT PRIMARY KEY,
    email       TEXT UNIQUE NOT NULL,
    plan        TEXT NOT NULL DEFAULT 'free',
    api_key     TEXT UNIQUE NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    rate_limit  INTEGER NOT NULL DEFAULT 100  -- per minute
);
"""


# ============================================================
# Caching Strategy
# ============================================================

@dataclass
class CacheLayer:
    name: str
    technology: str
    data: str
    ttl: str
    hit_rate: str
    size: str


CACHE_STRATEGY = [
    CacheLayer(
        name="L1: CDN Edge Cache",
        technology="Cloudflare / CloudFront",
        data="302 redirects with Cache-Control headers",
        ttl="5 minutes (short to preserve analytics)",
        hit_rate="60-70% (repeat clicks within TTL)",
        size="Distributed (CDN manages)",
    ),
    CacheLayer(
        name="L2: Redis Cluster (hot URLs)",
        technology="Redis Cluster (6 nodes, 3 primary + 3 replica)",
        data="short_code -> original_url mapping",
        ttl="24 hours (LRU eviction at 80% memory)",
        hit_rate="95%+ (Pareto: 20% of URLs = 80% traffic)",
        size="256 GB total cluster",
    ),
    CacheLayer(
        name="L3: Redis (negative cache)",
        technology="Same Redis cluster, separate keyspace",
        data="Invalid short codes -> __404__",
        ttl="5 minutes",
        hit_rate="Prevents DB load from scanners/bots",
        size="Minimal",
    ),
    CacheLayer(
        name="L4: Application cache",
        technology="In-process LRU (lru_cache or cachetools)",
        data="Top 10K most-accessed URLs per instance",
        ttl="60 seconds",
        hit_rate="30-40% within single instance",
        size="~2 MB per instance",
    ),
]


# ============================================================
# Deployment Topology
# ============================================================

DEPLOYMENT = """
                    ┌─────────────────┐
                    │   CDN Edge      │  L1 Cache
                    │  (Cloudflare)   │  (302 redirects)
                    └────────┬────────┘
                             │
                    ┌────────┴────────┐
                    │  Load Balancer  │  SSL termination
                    │  (Nginx x3)    │  Rate limiting
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────┴──────┐  ┌───┴────────┐  ┌──┴──────────┐
     │ Redirect Svc  │  │  URL Svc   │  │ Analytics   │
     │  (x10 pods)   │  │  (x5 pods) │  │ Svc (x3)   │
     │  GET /{code}  │  │  POST/CRUD │  │ GET /stats  │
     └───────┬───────┘  └─────┬──────┘  └──────┬──────┘
             │                │                 │
     ┌───────┴────────────────┴─────────┐      │
     │         Redis Cluster            │      │
     │  (6 nodes, 256GB total)          │      │
     │  L2 Cache + Rate Limits          │      │
     └───────────────┬──────────────────┘      │
                     │                          │
     ┌───────────────┴──────────────────┐      │
     │      PostgreSQL                  │      │
     │  Primary + 2 Read Replicas       │      │
     │  (partitioned by month)          │      │
     └──────────────────────────────────┘      │
                                               │
     ┌─────────────────────────────────────────┴──┐
     │              Kafka                         │
     │  (click events stream)                     │
     └──────────────────┬─────────────────────────┘
                        │
     ┌──────────────────┴─────────────────────────┐
     │           TimescaleDB                      │
     │  (click_events hypertable)                 │
     │  (continuous aggregates)                   │
     └────────────────────────────────────────────┘
"""

estimate = CapacityEstimate()
print(estimate.summary())
```

| Component | Technology | Scaling Strategy | SLA Target |
|---|---|---|---|
| CDN | Cloudflare Workers | Global PoPs | 99.99% |
| Load Balancer | Nginx / Envoy | Active-passive HA | 99.99% |
| Redirect Service | Python/Go, stateless | Horizontal (10+ pods) | p99 < 10ms |
| URL Service | Python/Go, stateless | Horizontal (5+ pods) | p99 < 100ms |
| Redis Cluster | 6 nodes (3P+3R) | Resharding | 99.95% |
| PostgreSQL | Primary + 2 replicas | Read replicas | 99.95% |
| Analytics | Kafka + TimescaleDB | Partition by time | Best-effort |

Key architecture patterns:
- Redirect service is the hot path: optimized for latency (Redis first, DB fallback)
- Write path (URL creation) is 100x less frequent than reads: separate service
- Click analytics are decoupled via Kafka to avoid impacting redirect latency
- Monthly table partitions enable efficient data lifecycle (drop old partitions)
- CDN edge caching with short TTL (5 min) balances analytics accuracy with performance
- Snowflake ID generation is stateless: no coordination between URL service instances
'''
    ),
]
