"""Thinking-trace pairs: graceful degradation patterns."""

PAIRS = [
    (
        "thinking/error-handling",
        r'''How do I implement fallback strategies for when external services are unavailable? I want my application to continue functioning with reduced capabilities rather than failing completely.''',
        r'''<think>
Fallback strategies provide degraded but functional responses when dependencies fail. The key patterns are:
1. Cached fallback: return stale cached data
2. Default value: return a safe default
3. Alternative service: try a backup provider
4. Queue for later: accept the request and process it when the service recovers
5. Feature reduction: disable non-critical features

My first thought was to just return None or a default on failure, but that is too simplistic -- the caller needs to know whether they got real data or a fallback. Otherwise a cached price from yesterday could be treated as today's price, which could be a costly mistake.

I considered whether the fallback chain should be primary -> cache -> secondary -> default. But wait, the secondary service is more likely to have fresh data than the cache, so it should come before cache. Actually, it depends on latency -- if the secondary is also slow/unreliable, hitting the cache first avoids cascading failures. Hmm, for most cases the right order is: primary -> secondary -> cache -> default, because freshness matters more than speed when you have a working backup provider. The cache is your last resort before the static default.
</think>

Fallback strategies let your application continue operating when dependencies are down. Here is a comprehensive fallback system:

```python
import asyncio
import json
import time
import logging
from typing import Any, Callable, Optional, TypeVar
from dataclasses import dataclass
from functools import wraps

logger = logging.getLogger(__name__)
T = TypeVar("T")

# ============================================================
# FALLBACK CHAIN: Try multiple strategies in order
# ============================================================

@dataclass
class FallbackResult:
    """Track which strategy provided the result."""
    value: Any
    source: str  # "primary", "secondary", "cache", "default"
    is_degraded: bool
    timestamp: float = 0.0

    def __post_init__(self):
        self.timestamp = time.time()


class FallbackChain:
    """Execute a chain of fallback strategies."""

    def __init__(self, name: str):
        self.name = name
        self._strategies = []

    def add(self, name: str, func: Callable, is_degraded: bool = False):
        """Add a fallback strategy to the chain."""
        self._strategies.append((name, func, is_degraded))
        return self

    async def execute(self, *args, **kwargs) -> FallbackResult:
        """Try each strategy in order until one succeeds."""
        last_error = None

        for strategy_name, func, is_degraded in self._strategies:
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)

                if is_degraded:
                    logger.warning(
                        "[%s] Using degraded fallback: %s",
                        self.name, strategy_name,
                    )
                else:
                    logger.debug(
                        "[%s] Strategy succeeded: %s",
                        self.name, strategy_name,
                    )

                return FallbackResult(
                    value=result,
                    source=strategy_name,
                    is_degraded=is_degraded,
                )
            except Exception as e:
                last_error = e
                logger.warning(
                    "[%s] Strategy '%s' failed: %s",
                    self.name, strategy_name, e,
                )

        raise FallbackExhaustedError(
            f"All {len(self._strategies)} strategies for '{self.name}' failed. "
            f"Last error: {last_error}"
        )


class FallbackExhaustedError(Exception):
    """All fallback strategies failed."""
    pass


# ============================================================
# CACHE-BASED FALLBACK
# ============================================================

class StaleCache:
    """Cache that serves stale data when the source is unavailable."""

    def __init__(self, ttl: float = 300, stale_ttl: float = 3600):
        self._cache = {}
        self.ttl = ttl          # Fresh data TTL
        self.stale_ttl = stale_ttl  # How long to keep stale data

    def get(self, key: str) -> Optional[Any]:
        entry = self._cache.get(key)
        if entry is None:
            return None
        value, stored_at = entry
        age = time.time() - stored_at
        if age > self.stale_ttl:
            del self._cache[key]
            return None
        return value

    def set(self, key: str, value: Any):
        self._cache[key] = (value, time.time())

    def is_fresh(self, key: str) -> bool:
        entry = self._cache.get(key)
        if entry is None:
            return False
        _, stored_at = entry
        return (time.time() - stored_at) < self.ttl


# ============================================================
# USAGE: Product catalog with fallback chain
# ============================================================

product_cache = StaleCache(ttl=300, stale_ttl=7200)  # 5min fresh, 2hr stale

async def get_product(product_id: str) -> FallbackResult:
    """Get product data with multiple fallback levels."""

    chain = FallbackChain("product-lookup")

    # Strategy 1: Fresh cache (not degraded)
    def try_fresh_cache(pid):
        if product_cache.is_fresh(pid):
            return product_cache.get(pid)
        raise LookupError("Cache miss or stale")

    # Strategy 2: Primary API
    async def try_primary_api(pid):
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://api.example.com/products/{pid}",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                product_cache.set(pid, data)  # Update cache
                return data

    # Strategy 3: Secondary/backup API
    async def try_backup_api(pid):
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://backup-api.example.com/products/{pid}",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                data = await resp.json()
                return data

    # Strategy 4: Stale cache (degraded but functional)
    def try_stale_cache(pid):
        data = product_cache.get(pid)
        if data is None:
            raise LookupError("No cached data available")
        return data

    # Strategy 5: Default product data (most degraded)
    def default_product(pid):
        return {
            "id": pid,
            "name": "Product unavailable",
            "price": None,
            "available": False,
            "_degraded": True,
        }

    chain.add("fresh_cache", try_fresh_cache, is_degraded=False)
    chain.add("primary_api", try_primary_api, is_degraded=False)
    chain.add("backup_api", try_backup_api, is_degraded=True)
    chain.add("stale_cache", try_stale_cache, is_degraded=True)
    chain.add("default", default_product, is_degraded=True)

    result = await chain.execute(product_id)

    # Add degradation info to the response
    if result.is_degraded:
        if isinstance(result.value, dict):
            result.value["_source"] = result.source
            result.value["_degraded"] = True

    return result


# ============================================================
# PARTIAL FAILURE HANDLING
# ============================================================

async def get_order_details(order_id: str) -> dict:
    """Compose order details from multiple services.
    Each service failure degrades the response, not breaks it.
    """
    order = await db.get_order(order_id)

    # Fetch enrichment data with individual fallbacks
    user_result = await get_user_safely(order["user_id"])
    product_results = await asyncio.gather(
        *[get_product(pid) for pid in order["product_ids"]],
        return_exceptions=True,
    )

    # Build response with whatever succeeded
    response = {
        "order_id": order_id,
        "status": order["status"],
        "user": user_result.value if not isinstance(user_result, Exception) else {"id": order["user_id"]},
        "products": [],
        "_degraded_fields": [],
    }

    for i, result in enumerate(product_results):
        if isinstance(result, Exception):
            response["products"].append({
                "id": order["product_ids"][i],
                "_error": "unavailable",
            })
            response["_degraded_fields"].append(f"products[{i}]")
        elif isinstance(result, FallbackResult) and result.is_degraded:
            response["products"].append(result.value)
            response["_degraded_fields"].append(f"products[{i}]")
        else:
            response["products"].append(
                result.value if isinstance(result, FallbackResult) else result
            )

    return response


# ============================================================
# QUEUE-FOR-LATER PATTERN
# ============================================================

class DeferredProcessor:
    """Accept work now, process when the service recovers."""

    def __init__(self, name: str, queue_path: str = "/tmp/deferred"):
        self.name = name
        self.queue_path = queue_path
        import os
        os.makedirs(queue_path, exist_ok=True)

    def defer(self, operation: str, payload: dict) -> str:
        """Queue an operation for later processing."""
        import uuid
        job_id = str(uuid.uuid4())
        job = {
            "id": job_id,
            "operation": operation,
            "payload": payload,
            "deferred_at": time.time(),
            "status": "pending",
        }
        path = f"{self.queue_path}/{job_id}.json"
        with open(path, "w") as f:
            json.dump(job, f)

        logger.info("[%s] Deferred operation '%s' as %s", self.name, operation, job_id)
        return job_id

    async def process_pending(self, handler: Callable):
        """Process all pending deferred operations."""
        import os
        pending = sorted(os.listdir(self.queue_path))
        for filename in pending:
            path = f"{self.queue_path}/{filename}"
            with open(path) as f:
                job = json.load(f)

            try:
                await handler(job["operation"], job["payload"])
                os.unlink(path)
                logger.info("[%s] Processed deferred job %s", self.name, job["id"])
            except Exception as e:
                logger.warning("[%s] Deferred job %s still failing: %s", self.name, job["id"], e)

# Usage:
# deferred = DeferredProcessor("notifications")
# try:
#     await send_notification(user_id, message)
# except ServiceUnavailable:
#     job_id = deferred.defer("send_notification", {"user_id": user_id, "message": message})
#     return {"status": "notification_queued", "job_id": job_id}
```

**Fallback strategy priority:**
1. Fresh cache (no degradation)
2. Primary service
3. Secondary/backup service (slightly degraded)
4. Stale cache (degraded but functional)
5. Queue for later (deferred processing)
6. Default value (most degraded but never fails)''',
    ),
    (
        "thinking/error-handling",
        r'''How do I implement feature flags to control graceful degradation in production? I want to be able to disable features quickly when they cause problems.''',
        r'''<think>
Feature flags for graceful degradation need:
1. Fast evaluation (checked on every request)
2. Dynamic updates (change without redeployment)
3. Default-safe behavior (features off if flag service is down)
4. Percentage-based rollouts
5. User/group targeting
6. Kill switches for emergencies

I initially considered just using environment variables for feature flags, but that requires a redeploy to change them. Wait -- you could use config file watching to pick up changes without redeployment. But actually, for kill switches in an emergency, even file-based updates are too slow since they depend on deployment pipelines. Therefore some kind of dynamic backend (database, Redis, or a dedicated service) is necessary for production use.

Implementation options:
- Simple: config file or environment variables (fine for development, too rigid for production)
- Medium: database-backed with caching (good balance of flexibility and complexity)
- Full: dedicated feature flag service (LaunchDarkly, Unleash)

Hmm, what should happen when the flag service itself is down? If you default to "feature enabled," a degraded flag service could accidentally enable unfinished features. Therefore the safe default should always be "feature disabled" -- this means new features are gated behind explicit enablement, which is the safer failure mode.

Let me show a practical in-process implementation.
</think>

Feature flags enable quick feature toggling in production without redeployment. Here is a practical implementation for graceful degradation:

```python
import json
import time
import hashlib
import threading
import logging
from typing import Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps

logger = logging.getLogger(__name__)


class FlagState(Enum):
    ON = "on"
    OFF = "off"
    PERCENTAGE = "percentage"


@dataclass
class FeatureFlag:
    name: str
    state: FlagState = FlagState.OFF
    percentage: float = 0.0  # 0-100, used when state is PERCENTAGE
    description: str = ""
    updated_at: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)


class FeatureFlagManager:
    """In-process feature flag system with file-based config."""

    def __init__(self, config_path: str = "feature_flags.json"):
        self._flags: dict[str, FeatureFlag] = {}
        self._config_path = config_path
        self._last_loaded = 0.0
        self._reload_interval = 10.0  # Reload config every 10 seconds
        self._lock = threading.Lock()
        self._load_config()

    def _load_config(self):
        """Load flags from config file."""
        try:
            with open(self._config_path) as f:
                data = json.load(f)
            with self._lock:
                for name, config in data.items():
                    self._flags[name] = FeatureFlag(
                        name=name,
                        state=FlagState(config.get("state", "off")),
                        percentage=config.get("percentage", 0),
                        description=config.get("description", ""),
                        metadata=config.get("metadata", {}),
                    )
            self._last_loaded = time.time()
        except FileNotFoundError:
            logger.warning("Feature flag config not found: %s", self._config_path)
        except Exception as e:
            logger.error("Error loading feature flags: %s", e)

    def _maybe_reload(self):
        """Reload config if stale."""
        if time.time() - self._last_loaded > self._reload_interval:
            self._load_config()

    def is_enabled(
        self,
        flag_name: str,
        user_id: Optional[str] = None,
        default: bool = False,
    ) -> bool:
        """Check if a feature flag is enabled.

        Args:
            flag_name: Name of the feature flag
            user_id: Optional user ID for percentage-based rollouts
            default: Default value if flag is not defined
        """
        self._maybe_reload()

        with self._lock:
            flag = self._flags.get(flag_name)

        if flag is None:
            return default

        if flag.state == FlagState.ON:
            return True
        elif flag.state == FlagState.OFF:
            return False
        elif flag.state == FlagState.PERCENTAGE:
            if user_id is None:
                # No user context -- use random
                import random
                return random.random() * 100 < flag.percentage
            # Deterministic: same user always gets same result
            hash_input = f"{flag_name}:{user_id}".encode()
            hash_val = int(hashlib.sha256(hash_input).hexdigest()[:8], 16)
            bucket = hash_val % 100
            return bucket < flag.percentage
        return default

    def set_flag(self, name: str, state: str, percentage: float = 0):
        """Update a flag at runtime (for emergency kill switches)."""
        with self._lock:
            if name in self._flags:
                self._flags[name].state = FlagState(state)
                self._flags[name].percentage = percentage
                self._flags[name].updated_at = time.time()
            else:
                self._flags[name] = FeatureFlag(
                    name=name, state=FlagState(state), percentage=percentage,
                )
        logger.info("Feature flag '%s' set to %s (%.0f%%)", name, state, percentage)

    def get_all_flags(self) -> dict:
        """Get all flag states for debugging."""
        with self._lock:
            return {
                name: {"state": f.state.value, "percentage": f.percentage}
                for name, f in self._flags.items()
            }


# Global instance
flags = FeatureFlagManager()


# ============================================================
# DECORATOR: Feature flag gate
# ============================================================

def feature_gate(
    flag_name: str,
    fallback: Optional[Callable] = None,
    default: bool = False,
):
    """Decorator to gate a function behind a feature flag."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Extract user_id from kwargs if available
            user_id = kwargs.get("user_id") or (
                args[0] if args else None
            )

            if flags.is_enabled(flag_name, user_id=str(user_id) if user_id else None, default=default):
                return func(*args, **kwargs)
            elif fallback:
                return fallback(*args, **kwargs)
            else:
                logger.debug("Feature '%s' is disabled", flag_name)
                return None

        wrapper.flag_name = flag_name
        return wrapper
    return decorator


# ============================================================
# USAGE: Graceful degradation with feature flags
# ============================================================

# feature_flags.json:
# {
#     "recommendation_engine": {"state": "on"},
#     "new_checkout_flow": {"state": "percentage", "percentage": 25},
#     "social_feed": {"state": "off"},
#     "heavy_analytics": {"state": "on"}
# }

def simple_recommendations(user_id, limit=5):
    """Fallback: return popular items instead of personalized ones."""
    return [{"id": i, "name": f"Popular Item {i}"} for i in range(limit)]

@feature_gate("recommendation_engine", fallback=simple_recommendations)
def get_recommendations(user_id, limit=5):
    """Full personalized recommendations (can be disabled)."""
    return recommendation_service.get_personalized(user_id, limit)


@feature_gate("new_checkout_flow", default=False)
def use_new_checkout(user_id):
    """New checkout experience (percentage rollout)."""
    return True


# ============================================================
# KILL SWITCH: Emergency feature disabling
# ============================================================

def handle_emergency(service_name: str):
    """Disable a feature instantly during an incident."""
    flag_mapping = {
        "recommendation_service": "recommendation_engine",
        "analytics_service": "heavy_analytics",
        "social_service": "social_feed",
    }
    flag_name = flag_mapping.get(service_name)
    if flag_name:
        flags.set_flag(flag_name, "off")
        logger.critical(
            "KILL SWITCH: Disabled '%s' due to %s incident",
            flag_name, service_name,
        )

# In your monitoring/alerting:
# if error_rate > 50%:
#     handle_emergency("recommendation_service")


# ============================================================
# API endpoint for flag management
# ============================================================

from fastapi import FastAPI

app = FastAPI()

@app.get("/admin/flags")
async def list_flags():
    return flags.get_all_flags()

@app.put("/admin/flags/{name}")
async def update_flag(name: str, state: str, percentage: float = 0):
    flags.set_flag(name, state, percentage)
    return {"status": "updated", "flag": name, "state": state}

# curl -X PUT "http://localhost:8000/admin/flags/recommendation_engine?state=off"
```

**Feature flag best practices:**
1. Default to OFF for new features (safe by default)
2. Use percentage rollouts for gradual deployments
3. Keep kill switches for all non-critical features
4. Reload flags without restart (file-based or API-based)
5. Log all flag changes for audit trail
6. Clean up old flags after features are fully rolled out''',
    ),
    (
        "thinking/error-handling",
        r'''How do I implement progressive enhancement for API responses? When some data sources fail, I want to return a partial response with degradation markers instead of a complete failure.''',
        r'''<think>
Progressive enhancement for APIs means:
1. The response always has a stable base structure
2. Optional enrichment data is fetched in parallel
3. Failed enrichments are marked in the response, not omitted silently
4. The client can check degradation markers to adjust its behavior
5. Partial success is better than total failure

Could I just omit failed fields from the response entirely? That seems simpler, but wait -- if the client expects a field and it is missing, it might crash or show a blank UI. Actually, silently omitting data is worse than explicitly marking it as unavailable, because the client cannot distinguish "this data does not exist" from "this data could not be fetched right now." Therefore we need degradation markers.

This is different from simple fallbacks -- we actively tell the client what is degraded. I considered using HTTP status codes (like 206 Partial Content) to signal degradation, but that only gives a binary signal at the response level. Per-field degradation markers are more useful since the client can decide which degraded fields matter for its current use case.
</think>

Progressive enhancement returns partial results with explicit degradation markers, letting the client adapt:

```python
import asyncio
import time
import logging
from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class DataQuality(Enum):
    FRESH = "fresh"        # Real-time data from source
    CACHED = "cached"      # Cached data (may be stale)
    DEFAULT = "default"    # Default/placeholder data
    UNAVAILABLE = "unavailable"  # Could not retrieve


@dataclass
class EnrichedField:
    """A response field with quality metadata."""
    value: Any
    quality: DataQuality
    source: str
    cached_at: Optional[float] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        result = {"value": self.value, "quality": self.quality.value}
        if self.quality == DataQuality.CACHED and self.cached_at:
            age = int(time.time() - self.cached_at)
            result["cache_age_seconds"] = age
        if self.error:
            result["error"] = self.error
        return result


@dataclass
class ProgressiveResponse:
    """API response with degradation metadata."""
    data: dict = field(default_factory=dict)
    _fields: dict = field(default_factory=dict)
    _degraded: list = field(default_factory=list)

    def set_field(
        self,
        path: str,
        value: Any,
        quality: DataQuality = DataQuality.FRESH,
        source: str = "primary",
        cached_at: Optional[float] = None,
        error: Optional[str] = None,
    ):
        """Set a field value with quality metadata."""
        self._fields[path] = EnrichedField(
            value=value, quality=quality, source=source,
            cached_at=cached_at, error=error,
        )
        # Set value in the data dict
        keys = path.split(".")
        obj = self.data
        for key in keys[:-1]:
            obj = obj.setdefault(key, {})
        obj[keys[-1]] = value

        if quality in (DataQuality.CACHED, DataQuality.DEFAULT, DataQuality.UNAVAILABLE):
            self._degraded.append(path)

    def to_response(self) -> dict:
        """Build the API response with degradation metadata."""
        response = {**self.data}

        # Add metadata about response quality
        response["_meta"] = {
            "degraded": len(self._degraded) > 0,
            "degraded_fields": self._degraded,
            "field_quality": {
                path: field.to_dict()
                for path, field in self._fields.items()
                if field.quality != DataQuality.FRESH
            },
            "timestamp": time.time(),
        }
        return response


# ============================================================
# USAGE: Order details with progressive enhancement
# ============================================================

async def get_order_progressive(order_id: str) -> dict:
    """Fetch order with progressive enrichment."""
    response = ProgressiveResponse()

    # Core data (must succeed -- no fallback)
    order = await db.get_order(order_id)
    response.set_field("order_id", order["id"])
    response.set_field("status", order["status"])
    response.set_field("total", order["total"])
    response.set_field("created_at", order["created_at"])

    # Enrichment data (fetched in parallel, each can fail independently)
    results = await asyncio.gather(
        enrich_user(response, order["user_id"]),
        enrich_products(response, order["product_ids"]),
        enrich_shipping(response, order_id),
        enrich_recommendations(response, order["user_id"]),
        return_exceptions=True,
    )

    # Log any unexpected errors from enrichment
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error("Enrichment %d failed unexpectedly: %s", i, result)

    return response.to_response()


async def enrich_user(response: ProgressiveResponse, user_id: str):
    """Enrich with user data (with cache fallback)."""
    try:
        user = await user_service.get_user(user_id)
        response.set_field("user.name", user["name"])
        response.set_field("user.email", user["email"])
    except Exception as e:
        # Try cache
        cached = user_cache.get(user_id)
        if cached:
            response.set_field(
                "user.name", cached["name"],
                quality=DataQuality.CACHED,
                source="cache",
                cached_at=cached.get("_cached_at"),
            )
            response.set_field(
                "user.email", cached["email"],
                quality=DataQuality.CACHED,
                source="cache",
            )
        else:
            response.set_field(
                "user.name", None,
                quality=DataQuality.UNAVAILABLE,
                error=str(e),
            )


async def enrich_products(response: ProgressiveResponse, product_ids: list):
    """Enrich with product details."""
    products = []
    for pid in product_ids:
        try:
            product = await product_service.get_product(pid)
            products.append(product)
        except Exception:
            products.append({"id": pid, "name": "Product details unavailable"})

    response.set_field("products", products)


async def enrich_shipping(response: ProgressiveResponse, order_id: str):
    """Enrich with shipping tracking."""
    try:
        tracking = await shipping_service.get_tracking(order_id)
        response.set_field("shipping.status", tracking["status"])
        response.set_field("shipping.eta", tracking["eta"])
    except Exception as e:
        response.set_field(
            "shipping.status", "unknown",
            quality=DataQuality.DEFAULT,
            error="Shipping service unavailable",
        )


async def enrich_recommendations(response: ProgressiveResponse, user_id: str):
    """Enrich with recommendations (non-critical)."""
    try:
        recs = await recommendation_service.get_recs(user_id, limit=3)
        response.set_field("recommendations", recs)
    except Exception:
        response.set_field(
            "recommendations", [],
            quality=DataQuality.DEFAULT,
            source="disabled",
        )


# ============================================================
# EXAMPLE RESPONSE
# ============================================================

# {
#     "order_id": "ORD-12345",
#     "status": "shipped",
#     "total": 99.99,
#     "created_at": "2024-01-15T10:00:00Z",
#     "user": {"name": "Alice", "email": "alice@example.com"},
#     "products": [
#         {"id": "P1", "name": "Blue Shirt", "price": 29.99},
#         {"id": "P2", "name": "Product details unavailable"}
#     ],
#     "shipping": {"status": "unknown"},
#     "recommendations": [],
#     "_meta": {
#         "degraded": true,
#         "degraded_fields": ["shipping.status", "recommendations"],
#         "field_quality": {
#             "shipping.status": {
#                 "value": "unknown",
#                 "quality": "default",
#                 "error": "Shipping service unavailable"
#             },
#             "recommendations": {
#                 "value": [],
#                 "quality": "default"
#             }
#         },
#         "timestamp": 1705312800.0
#     }
# }
```

**Progressive enhancement rules:**
1. Core data must always be present (fail the request if it cannot be retrieved)
2. Enrichment data is optional -- failures are degraded, not fatal
3. Always include `_meta` so clients know what is degraded
4. Fetch enrichments in parallel for performance
5. The `quality` field tells clients how fresh/reliable the data is
6. Clients can check `_meta.degraded` to show a "partial data" banner''',
    ),
    (
        "thinking/error-handling",
        r'''How do I handle partial failures in batch operations? When processing a batch of 100 items, some might succeed and some might fail. I want to report results per item without losing the successful ones.''',
        r'''<think>
Batch partial failure handling needs:
1. Process each item independently
2. Collect results (success and failure) for each item
3. Continue processing after individual item failures
4. Report detailed results to the caller
5. Support rollback of individual items if needed
6. Handle the overall batch status (partial success)

Key design decisions:
- Should the batch stop on first failure or continue? My instinct says continue, since the caller submitted all items expecting results for each. But wait -- if the failure indicates a systemic issue (like database down), continuing would just accumulate identical failures. Actually, a good implementation should distinguish between item-specific errors (bad data) and systemic errors (infrastructure down), and only stop early for systemic ones.
- Should successful items be committed or rolled back on partial failure? This depends on the domain. For importing CSV rows, keeping successful items is fine. For financial transfers, you might need all-or-nothing. Therefore the API should let the caller choose the strategy.
- How to report per-item results? I considered just returning a list of errors, but that loses the mapping between items and their outcomes. A per-item result object with status, value, and error is cleaner because the caller can iterate the results in the same order as the input.
</think>

Partial failure handling in batch operations requires per-item error tracking and clear reporting:

```python
import asyncio
import time
import logging
from typing import Any, Callable, Optional, TypeVar
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)
T = TypeVar("T")


class ItemStatus(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class BatchItemResult:
    """Result for a single item in a batch."""
    item_id: str
    status: ItemStatus
    result: Optional[Any] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    duration_ms: float = 0.0


@dataclass
class BatchResult:
    """Aggregate result for a batch operation."""
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    items: list = field(default_factory=list)
    duration_ms: float = 0.0

    @property
    def is_complete_success(self) -> bool:
        return self.failed == 0 and self.skipped == 0

    @property
    def is_complete_failure(self) -> bool:
        return self.succeeded == 0

    @property
    def is_partial_success(self) -> bool:
        return self.succeeded > 0 and self.failed > 0

    @property
    def success_rate(self) -> float:
        return self.succeeded / self.total * 100 if self.total > 0 else 0

    def to_dict(self) -> dict:
        return {
            "summary": {
                "total": self.total,
                "succeeded": self.succeeded,
                "failed": self.failed,
                "skipped": self.skipped,
                "success_rate": f"{self.success_rate:.1f}%",
                "duration_ms": self.duration_ms,
            },
            "items": [
                {
                    "id": item.item_id,
                    "status": item.status.value,
                    "error": item.error,
                    "duration_ms": item.duration_ms,
                }
                for item in self.items
                if item.status != ItemStatus.SUCCESS  # Only include failures
            ],
        }


# ============================================================
# BATCH PROCESSOR: Process items with per-item error handling
# ============================================================

class BatchProcessor:
    """Process batch items with individual error handling."""

    def __init__(
        self,
        name: str,
        max_concurrent: int = 10,
        stop_on_failure_rate: float = 50.0,
        continue_on_error: bool = True,
    ):
        self.name = name
        self.max_concurrent = max_concurrent
        self.stop_on_failure_rate = stop_on_failure_rate
        self.continue_on_error = continue_on_error

    async def process(
        self,
        items: list[dict],
        processor: Callable,
        id_field: str = "id",
    ) -> BatchResult:
        """Process all items and collect per-item results."""
        start_time = time.time()
        result = BatchResult(total=len(items))
        semaphore = asyncio.Semaphore(self.max_concurrent)
        should_stop = False

        async def process_one(item):
            nonlocal should_stop
            if should_stop:
                item_result = BatchItemResult(
                    item_id=str(item.get(id_field, "unknown")),
                    status=ItemStatus.SKIPPED,
                    error="Batch stopped due to high failure rate",
                )
                result.skipped += 1
                result.items.append(item_result)
                return

            async with semaphore:
                item_start = time.time()
                item_id = str(item.get(id_field, "unknown"))
                try:
                    if asyncio.iscoroutinefunction(processor):
                        item_value = await processor(item)
                    else:
                        item_value = processor(item)

                    item_result = BatchItemResult(
                        item_id=item_id,
                        status=ItemStatus.SUCCESS,
                        result=item_value,
                        duration_ms=(time.time() - item_start) * 1000,
                    )
                    result.succeeded += 1
                except Exception as e:
                    item_result = BatchItemResult(
                        item_id=item_id,
                        status=ItemStatus.FAILED,
                        error=str(e),
                        error_type=type(e).__name__,
                        duration_ms=(time.time() - item_start) * 1000,
                    )
                    result.failed += 1

                    # Check if we should stop the batch
                    processed = result.succeeded + result.failed
                    if processed > 5:  # Wait for a minimum sample
                        failure_rate = result.failed / processed * 100
                        if failure_rate >= self.stop_on_failure_rate:
                            should_stop = True
                            logger.error(
                                "[%s] Stopping batch: %.0f%% failure rate",
                                self.name, failure_rate,
                            )

                result.items.append(item_result)

        # Process all items concurrently (with semaphore limit)
        await asyncio.gather(
            *[process_one(item) for item in items],
            return_exceptions=True,
        )

        result.duration_ms = (time.time() - start_time) * 1000

        logger.info(
            "[%s] Batch complete: %d/%d succeeded (%.1f%%) in %.0fms",
            self.name, result.succeeded, result.total,
            result.success_rate, result.duration_ms,
        )
        return result


# ============================================================
# USAGE
# ============================================================

processor = BatchProcessor(
    name="order-import",
    max_concurrent=5,
    stop_on_failure_rate=50.0,
)

async def import_order(order_data: dict):
    """Import a single order (may fail)."""
    # Validate
    if not order_data.get("customer_id"):
        raise ValueError("Missing customer_id")
    # Process
    result = await db.insert_order(order_data)
    return result

orders = [
    {"id": "1", "customer_id": "C1", "amount": 100},
    {"id": "2", "customer_id": None, "amount": 200},  # Will fail
    {"id": "3", "customer_id": "C3", "amount": 300},
]

result = await processor.process(orders, import_order)
print(json.dumps(result.to_dict(), indent=2))

# Output:
# {
#     "summary": {
#         "total": 3,
#         "succeeded": 2,
#         "failed": 1,
#         "skipped": 0,
#         "success_rate": "66.7%",
#         "duration_ms": 150.0
#     },
#     "items": [
#         {
#             "id": "2",
#             "status": "failed",
#             "error": "Missing customer_id",
#             "duration_ms": 1.2
#         }
#     ]
# }

# HTTP response status:
# - 200 if all succeeded
# - 207 (Multi-Status) if partial success
# - 422 if all failed
```

**Batch processing rules:**
1. Never let one item's failure stop the entire batch (unless failure rate is too high)
2. Report per-item results with clear success/failure status
3. Use HTTP 207 Multi-Status for partial success responses
4. Set a failure rate threshold to stop processing a poisoned batch
5. Include timing information for performance debugging''',
    ),
    (
        "thinking/error-handling",
        r'''What are good patterns for choosing and providing default values when operations fail? I want to ensure my defaults are safe and do not mask bugs.''',
        r'''<think>
Default values on error are tricky because:
1. Bad defaults can mask bugs (returning 0 for a price when the DB is down)
2. Defaults should be distinguishable from real values
3. Some fields should never have defaults (security-related)
4. Defaults should match the expected type

I initially thought "just use None as the default everywhere," but actually None conflates three different states: "value is absent," "value was not fetched," and "value was fetched and is legitimately null." Therefore we need distinct sentinels for different missing-value semantics.

Could you use Optional types to handle this? Hmm, Optional[T] only distinguishes "has value" from "no value" -- it cannot express why the value is missing. A Result type (Ok/Err) is better because it carries the error information, letting the caller decide how to handle the failure rather than silently accepting a default.

Patterns:
1. Sentinel values (None, NOT_SET, MISSING) -- but be careful, since None is often a valid value in the domain
2. Type-safe defaults with Option/Result types
3. Default factories (computed defaults)
4. Config-driven defaults
5. Explicit "unknown" values -- wait, these can propagate through calculations and produce nonsense results (e.g., "unknown" + 5). Therefore unknown values should block computation, not silently participate in it.
</think>

Default values in error handling must be carefully designed to avoid masking bugs. Here are the safe patterns:

```python
from typing import TypeVar, Generic, Optional, Callable, Any
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)
T = TypeVar("T")

# ============================================================
# ANTI-PATTERN: Dangerous defaults that mask bugs
# ============================================================

# BAD: Using 0 as default price -- silently shows wrong price
def get_price_bad(product_id):
    try:
        return db.get_price(product_id)
    except Exception:
        return 0  # Customer sees $0.00 -- terrible!

# BAD: Empty string hides missing data
def get_username_bad(user_id):
    try:
        return db.get_username(user_id)
    except Exception:
        return ""  # UI shows empty name, nobody notices

# BAD: False hides permission check failures
def is_admin_bad(user_id):
    try:
        return auth_service.check_admin(user_id)
    except Exception:
        return False  # If auth is down, nobody can admin -- or worse, True!


# ============================================================
# PATTERN 1: Result type (explicit success/failure)
# ============================================================

class Result(Generic[T]):
    """Either a value or an error -- never ambiguous."""

    def __init__(self, value: Optional[T] = None, error: Optional[str] = None):
        self._value = value
        self._error = error
        self._is_ok = error is None

    @classmethod
    def ok(cls, value: T) -> "Result[T]":
        return cls(value=value)

    @classmethod
    def fail(cls, error: str) -> "Result[T]":
        return cls(error=error)

    @property
    def is_ok(self) -> bool:
        return self._is_ok

    def unwrap(self) -> T:
        """Get the value or raise if error."""
        if not self._is_ok:
            raise ValueError(f"Unwrap on error result: {self._error}")
        return self._value

    def unwrap_or(self, default: T) -> T:
        """Get the value or return default on error."""
        return self._value if self._is_ok else default

    def unwrap_or_else(self, func: Callable[[], T]) -> T:
        """Get the value or compute default on error."""
        return self._value if self._is_ok else func()

    @property
    def error(self) -> Optional[str]:
        return self._error


def get_price(product_id: str) -> Result[float]:
    try:
        price = db.get_price(product_id)
        return Result.ok(price)
    except Exception as e:
        logger.error("Failed to get price for %s: %s", product_id, e)
        return Result.fail(f"Price unavailable: {e}")

# Usage -- caller MUST handle the error case:
result = get_price("P123")
if result.is_ok:
    display_price(result.unwrap())
else:
    display_price_unavailable(result.error)

# ============================================================
# PATTERN 2: Sentinel values (distinguishable from real data)
# ============================================================

class _Sentinel:
    """Unique sentinel value that cannot be confused with real data."""
    def __init__(self, name):
        self.name = name
    def __repr__(self):
        return f"<{self.name}>"
    def __bool__(self):
        return False  # Falsy like None

MISSING = _Sentinel("MISSING")
NOT_LOADED = _Sentinel("NOT_LOADED")
UNAVAILABLE = _Sentinel("UNAVAILABLE")

def get_user_profile(user_id):
    profile = {
        "name": MISSING,
        "email": MISSING,
        "avatar": MISSING,
        "preferences": NOT_LOADED,
    }

    try:
        user = user_service.get(user_id)
        profile["name"] = user.get("name", MISSING)
        profile["email"] = user.get("email", MISSING)
        profile["avatar"] = user.get("avatar")
    except Exception:
        profile["name"] = UNAVAILABLE
        profile["email"] = UNAVAILABLE

    return profile

# Template can check: if profile["name"] is UNAVAILABLE: show_error()
#                      if profile["name"] is MISSING: show_placeholder()

# ============================================================
# PATTERN 3: Safe defaults with explicit markers
# ============================================================

@dataclass
class SafeDefault:
    """A default value that marks itself as non-authoritative."""
    value: Any
    is_default: bool = True
    reason: str = ""

    def __repr__(self):
        if self.is_default:
            return f"SafeDefault({self.value!r}, reason={self.reason!r})"
        return repr(self.value)

def get_config_value(key: str, safe_default: Any = None) -> SafeDefault:
    try:
        value = config_store.get(key)
        return SafeDefault(value=value, is_default=False)
    except Exception as e:
        logger.warning("Config '%s' unavailable, using default: %s", key, e)
        return SafeDefault(
            value=safe_default,
            is_default=True,
            reason=str(e),
        )

# ============================================================
# PATTERN 4: Default policy by field category
# ============================================================

class DefaultPolicy(Enum):
    NEVER = "never"          # No default -- must fail if unavailable
    SAFE_ZERO = "safe_zero"  # 0 or empty is safe
    CACHED = "cached"        # Use last known value
    COMPUTED = "computed"     # Compute from other data

FIELD_POLICIES = {
    # Financial fields: NEVER use defaults
    "price": DefaultPolicy.NEVER,
    "balance": DefaultPolicy.NEVER,
    "tax_amount": DefaultPolicy.NEVER,

    # Display fields: safe to default
    "display_name": DefaultPolicy.SAFE_ZERO,
    "description": DefaultPolicy.SAFE_ZERO,
    "thumbnail_url": DefaultPolicy.SAFE_ZERO,

    # Status fields: use cache
    "inventory_count": DefaultPolicy.CACHED,
    "order_status": DefaultPolicy.CACHED,

    # Computed fields
    "estimated_delivery": DefaultPolicy.COMPUTED,
}

def get_field_with_policy(field_name, fetch_func, **kwargs):
    policy = FIELD_POLICIES.get(field_name, DefaultPolicy.NEVER)

    try:
        return fetch_func(**kwargs)
    except Exception as e:
        if policy == DefaultPolicy.NEVER:
            raise  # No default allowed -- propagate error
        elif policy == DefaultPolicy.SAFE_ZERO:
            logger.warning("Using empty default for %s", field_name)
            return ""
        elif policy == DefaultPolicy.CACHED:
            cached = cache.get(field_name, kwargs)
            if cached is not None:
                return cached
            raise  # No cache available
        elif policy == DefaultPolicy.COMPUTED:
            return compute_default(field_name, kwargs)

# ============================================================
# PATTERN 5: Never default security-critical values
# ============================================================

def check_permission(user_id: str, resource: str) -> bool:
    """Permission checks must NEVER default to a value."""
    try:
        return auth_service.check(user_id, resource)
    except Exception as e:
        # DO NOT return True or False -- deny access explicitly
        logger.error("Auth service unavailable: %s", e)
        raise PermissionError(
            "Cannot verify permissions -- access denied"
        ) from e
    # If auth is down, the SAFE choice is to deny access,
    # but we do it by RAISING, not by returning False.
    # Returning False would silently deny when we should fail loudly.
```

**Default value rules:**
1. **Financial data**: Never default -- always fail explicitly
2. **Security data**: Never default -- deny access by raising, not returning
3. **Display data**: Safe to default to empty/placeholder values
4. **Status data**: Use cached values with staleness markers
5. Always make defaults **distinguishable** from real data (sentinel values, Result type)
6. Log every time a default is used -- if defaults fire too often, something is wrong''',
    ),
]
