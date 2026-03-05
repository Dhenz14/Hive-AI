"""Feature flag patterns and progressive delivery."""

PAIRS = [
    (
        "feature-flags/patterns-kill-switch-experiment-rollout",
        "Implement feature flag patterns including kill switches, experiment flags, release flags, and percentage rollouts with a type-safe Python SDK supporting local evaluation and real-time updates.",
        '''Feature flag patterns with type-safe SDK:

```python
# --- Feature flag SDK with local evaluation ---

from __future__ import annotations

import hashlib
import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Generic, Optional, TypeVar, Union

logger = logging.getLogger(__name__)
T = TypeVar("T")


class FlagType(str, Enum):
    BOOLEAN = "boolean"
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    JSON = "json"


class RolloutStrategy(str, Enum):
    ALL = "all"                          # On for everyone
    NONE = "none"                        # Off for everyone (kill switch)
    PERCENTAGE = "percentage"            # Gradual rollout by hash
    USER_LIST = "user_list"              # Specific users
    ATTRIBUTE_MATCH = "attribute_match"  # Rule-based targeting
    EXPERIMENT = "experiment"            # A/B test with tracking


@dataclass
class EvaluationContext:
    """Context for flag evaluation decisions."""
    user_id: str
    tenant_id: str = ""
    environment: str = "production"
    user_email: str = ""
    user_role: str = ""
    country: str = ""
    device_type: str = ""
    app_version: str = ""
    custom_attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def targeting_key(self) -> str:
        return self.user_id


@dataclass
class FlagVariant:
    """A specific variant/value of a feature flag."""
    name: str
    value: Any
    weight: float = 0.0  # For percentage rollouts
    description: str = ""


@dataclass
class TargetingRule:
    """Rule for targeting specific users or segments."""
    attribute: str
    operator: str  # eq, neq, in, not_in, contains, gt, lt, regex
    value: Any
    variant: str  # Which variant to serve if rule matches


@dataclass
class FlagDefinition:
    """Complete feature flag definition."""
    key: str
    flag_type: FlagType
    description: str
    default_variant: str
    variants: list[FlagVariant]
    rollout_strategy: RolloutStrategy
    rollout_percentage: float = 0.0
    targeting_rules: list[TargetingRule] = field(default_factory=list)
    enabled: bool = True
    owner: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: str = ""
    stale_after_days: int = 90


class FlagEvaluator:
    """Local flag evaluation engine with deterministic hashing."""

    def evaluate(
        self,
        flag: FlagDefinition,
        context: EvaluationContext,
    ) -> tuple[str, Any, str]:
        """Evaluate a flag and return (variant_name, value, reason)."""
        if not flag.enabled:
            return self._get_variant(flag, flag.default_variant), "disabled"

        # Check targeting rules first (highest priority)
        for rule in flag.targeting_rules:
            if self._matches_rule(rule, context):
                return self._get_variant(flag, rule.variant), "targeting_rule"

        # Apply rollout strategy
        if flag.rollout_strategy == RolloutStrategy.ALL:
            on_variant = self._find_on_variant(flag)
            return self._get_variant(flag, on_variant), "rollout_all"

        if flag.rollout_strategy == RolloutStrategy.NONE:
            return self._get_variant(flag, flag.default_variant), "rollout_none"

        if flag.rollout_strategy == RolloutStrategy.PERCENTAGE:
            bucket = self._hash_to_bucket(flag.key, context.targeting_key)
            if bucket < flag.rollout_percentage:
                on_variant = self._find_on_variant(flag)
                return self._get_variant(flag, on_variant), "rollout_percentage"
            return self._get_variant(flag, flag.default_variant), "rollout_percentage_miss"

        if flag.rollout_strategy == RolloutStrategy.EXPERIMENT:
            variant = self._select_experiment_variant(flag, context)
            return self._get_variant(flag, variant), "experiment"

        return self._get_variant(flag, flag.default_variant), "default"

    def _hash_to_bucket(self, flag_key: str, targeting_key: str) -> float:
        """Deterministic hash for consistent percentage rollouts."""
        combined = f"{flag_key}:{targeting_key}"
        hash_val = int(hashlib.sha256(combined.encode()).hexdigest()[:8], 16)
        return (hash_val % 10000) / 100.0  # 0.00 - 99.99

    def _matches_rule(
        self, rule: TargetingRule, context: EvaluationContext
    ) -> bool:
        actual = getattr(context, rule.attribute, None)
        if actual is None:
            actual = context.custom_attributes.get(rule.attribute)
        if actual is None:
            return False

        op = rule.operator
        if op == "eq":
            return actual == rule.value
        if op == "neq":
            return actual != rule.value
        if op == "in":
            return actual in rule.value
        if op == "not_in":
            return actual not in rule.value
        if op == "contains":
            return rule.value in str(actual)
        if op == "gt":
            return float(actual) > float(rule.value)
        if op == "lt":
            return float(actual) < float(rule.value)
        return False

    def _select_experiment_variant(
        self, flag: FlagDefinition, context: EvaluationContext
    ) -> str:
        """Select variant based on weighted distribution."""
        bucket = self._hash_to_bucket(flag.key, context.targeting_key)
        cumulative = 0.0
        for variant in flag.variants:
            cumulative += variant.weight
            if bucket < cumulative:
                return variant.name
        return flag.default_variant

    def _find_on_variant(self, flag: FlagDefinition) -> str:
        for v in flag.variants:
            if v.name != flag.default_variant:
                return v.name
        return flag.default_variant

    def _get_variant(
        self, flag: FlagDefinition, variant_name: str
    ) -> tuple[str, Any]:
        for v in flag.variants:
            if v.name == variant_name:
                return variant_name, v.value
        return flag.default_variant, flag.variants[0].value


class FeatureFlagClient:
    """High-level client with caching and real-time updates."""

    def __init__(
        self,
        flags: dict[str, FlagDefinition],
        evaluator: Optional[FlagEvaluator] = None,
    ) -> None:
        self._flags = flags
        self._evaluator = evaluator or FlagEvaluator()
        self._listeners: list[Callable[[str, Any], None]] = []
        self._cache: dict[str, tuple[str, Any, float]] = {}
        self._cache_ttl = 60.0  # seconds
        self._lock = threading.Lock()

    def get_boolean(
        self, key: str, context: EvaluationContext, default: bool = False
    ) -> bool:
        _, value, _ = self._evaluate(key, context)
        return bool(value) if value is not None else default

    def get_string(
        self, key: str, context: EvaluationContext, default: str = ""
    ) -> str:
        _, value, _ = self._evaluate(key, context)
        return str(value) if value is not None else default

    def get_integer(
        self, key: str, context: EvaluationContext, default: int = 0
    ) -> int:
        _, value, _ = self._evaluate(key, context)
        return int(value) if value is not None else default

    def _evaluate(
        self, key: str, context: EvaluationContext
    ) -> tuple[str, Any, str]:
        cache_key = f"{key}:{context.targeting_key}"
        with self._lock:
            if cache_key in self._cache:
                variant, value, ts = self._cache[cache_key]
                if time.time() - ts < self._cache_ttl:
                    return variant, value, "cache"

        flag = self._flags.get(key)
        if flag is None:
            logger.warning("Unknown flag '%s', returning default", key)
            return "default", None, "not_found"

        variant_name, value, reason = self._evaluator.evaluate(flag, context)
        with self._lock:
            self._cache[cache_key] = (variant_name, value, time.time())
        return variant_name, value, reason

    def update_flag(self, key: str, flag: FlagDefinition) -> None:
        self._flags[key] = flag
        with self._lock:
            keys_to_remove = [k for k in self._cache if k.startswith(f"{key}:")]
            for k in keys_to_remove:
                del self._cache[k]
        for listener in self._listeners:
            listener(key, flag)

    def on_change(self, callback: Callable[[str, Any], None]) -> None:
        self._listeners.append(callback)
```

```python
# --- Kill switch and circuit breaker integration ---

from dataclasses import dataclass
from typing import Any, Optional
import time
import logging

logger = logging.getLogger(__name__)


@dataclass
class KillSwitch:
    """Emergency kill switch backed by feature flags."""
    flag_key: str
    description: str
    affects: list[str]  # Components affected when killed
    fallback_behavior: str  # What happens when killed

    def is_killed(self, client: "FeatureFlagClient", context: "EvaluationContext") -> bool:
        return not client.get_boolean(self.flag_key, context, default=True)


class KillSwitchRegistry:
    """Registry of all kill switches for operational visibility."""

    def __init__(self, client: "FeatureFlagClient") -> None:
        self.client = client
        self._switches: dict[str, KillSwitch] = {}

    def register(self, switch: KillSwitch) -> None:
        self._switches[switch.flag_key] = switch

    def check_all(self, context: "EvaluationContext") -> dict[str, bool]:
        """Check all kill switches and return their status."""
        return {
            key: switch.is_killed(self.client, context)
            for key, switch in self._switches.items()
        }

    def get_active_kills(self, context: "EvaluationContext") -> list[KillSwitch]:
        """Get list of currently activated kill switches."""
        return [
            switch for key, switch in self._switches.items()
            if switch.is_killed(self.client, context)
        ]


# Kill switch definitions
KILL_SWITCHES = [
    KillSwitch(
        flag_key="kill.payments.processing",
        description="Disable payment processing",
        affects=["checkout", "subscriptions", "refunds"],
        fallback_behavior="Show maintenance message, queue for retry",
    ),
    KillSwitch(
        flag_key="kill.notifications.email",
        description="Disable email notifications",
        affects=["transactional_email", "marketing_email"],
        fallback_behavior="Queue emails for later delivery",
    ),
    KillSwitch(
        flag_key="kill.search.elasticsearch",
        description="Disable Elasticsearch, fall back to DB",
        affects=["product_search", "autocomplete"],
        fallback_behavior="Use PostgreSQL full-text search fallback",
    ),
    KillSwitch(
        flag_key="kill.ai.recommendations",
        description="Disable AI recommendation engine",
        affects=["homepage_recs", "cart_suggestions"],
        fallback_behavior="Show popularity-based fallback recommendations",
    ),
]


class ProgressiveRollout:
    """Manage progressive feature rollouts with automatic rollback."""

    def __init__(
        self,
        client: "FeatureFlagClient",
        flag_key: str,
        error_threshold: float = 0.05,
        check_interval: int = 300,
    ) -> None:
        self.client = client
        self.flag_key = flag_key
        self.error_threshold = error_threshold
        self.check_interval = check_interval
        self._stage_percentages = [1, 5, 10, 25, 50, 100]
        self._current_stage = 0
        self._errors: list[float] = []

    def advance(self) -> Optional[float]:
        """Advance to next rollout stage if error rate is acceptable."""
        error_rate = self._calculate_error_rate()
        if error_rate > self.error_threshold:
            logger.warning(
                "Flag '%s' error rate %.2f%% exceeds threshold %.2f%%, "
                "rolling back to 0%%",
                self.flag_key, error_rate * 100, self.error_threshold * 100,
            )
            self._rollback()
            return 0.0

        if self._current_stage < len(self._stage_percentages) - 1:
            self._current_stage += 1
            new_pct = self._stage_percentages[self._current_stage]
            logger.info(
                "Flag '%s' advancing to %d%% rollout",
                self.flag_key, new_pct,
            )
            return float(new_pct)
        return float(self._stage_percentages[-1])

    def _rollback(self) -> None:
        self._current_stage = 0
        logger.error("Flag '%s' rolled back to 0%%", self.flag_key)

    def _calculate_error_rate(self) -> float:
        if not self._errors:
            return 0.0
        recent = self._errors[-100:]
        return sum(recent) / len(recent)

    def record_result(self, success: bool) -> None:
        self._errors.append(0.0 if success else 1.0)
        if len(self._errors) > 10000:
            self._errors = self._errors[-5000:]
```

```python
# --- Feature flag middleware for FastAPI ---

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Any, Callable
import json
import time


class FeatureFlagMiddleware(BaseHTTPMiddleware):
    """Inject feature flag evaluation into request context."""

    def __init__(self, app: FastAPI, client: "FeatureFlagClient") -> None:
        super().__init__(app)
        self.client = client

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        # Build evaluation context from request
        context = EvaluationContext(
            user_id=request.headers.get("X-User-ID", "anonymous"),
            tenant_id=request.headers.get("X-Tenant-ID", ""),
            environment=request.headers.get("X-Environment", "production"),
            country=request.headers.get("X-Country", ""),
            device_type=request.headers.get("X-Device-Type", ""),
            app_version=request.headers.get("X-App-Version", ""),
        )
        request.state.flag_context = context
        request.state.flag_client = self.client

        # Evaluate active experiments and add to response headers
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Add flag evaluation metadata for debugging
        response.headers["X-Feature-Flags-Time-Ms"] = f"{elapsed_ms:.1f}"
        return response


def feature_flag(
    flag_key: str,
    default: Any = None,
) -> Callable:
    """Dependency injection for feature flag values in FastAPI routes."""
    from fastapi import Depends

    async def _get_flag(request: Request) -> Any:
        client: FeatureFlagClient = request.state.flag_client
        context: EvaluationContext = request.state.flag_context
        return client.get_boolean(flag_key, context, default=default)

    return Depends(_get_flag)


# --- Usage example ---
#
# app = FastAPI()
# app.add_middleware(FeatureFlagMiddleware, client=flag_client)
#
# @app.get("/products")
# async def list_products(
#     use_new_ranking: bool = feature_flag("new-product-ranking", default=False),
# ):
#     if use_new_ranking:
#         return await new_ranking_algorithm()
#     return await legacy_ranking()
```

| Flag Type | Lifespan | Use Case | Cleanup |
|-----------|----------|----------|---------|
| Kill switch | Permanent | Emergency disable of features | Never remove |
| Release flag | Days-weeks | Gate incomplete features | Remove after 100% rollout |
| Experiment flag | Weeks-months | A/B testing | Remove after analysis |
| Ops flag | Permanent | Operational tuning | Review quarterly |
| Permission flag | Permanent | Entitlement/tier gating | Managed by billing |

Key patterns for feature flags:

1. **Deterministic hashing** -- hash flag_key + user_id for consistent percentage rollouts across requests and servers
2. **Kill switches** -- permanent flags for emergency circuit breaking; never remove, always default to "on"
3. **Progressive rollout** -- advance through stages (1%, 5%, 10%, 25%, 50%, 100%) with automatic rollback on error spikes
4. **Targeting rules** -- evaluate attribute-based rules before percentage rollout for beta users, internal testers, and tenant overrides
5. **Type-safe API** -- provide get_boolean/get_string/get_integer methods to avoid casting errors in application code
6. **Cache with invalidation** -- cache evaluations per user+flag with TTL, flush on flag update for real-time changes
7. **Evaluation context** -- pass user, tenant, environment, and custom attributes to enable rich targeting decisions'''
    ),
    (
        "feature-flags/openfeature-specification",
        "Implement the OpenFeature specification for a vendor-neutral feature flag SDK with providers, hooks, evaluation context, and event handling to avoid vendor lock-in.",
        '''OpenFeature specification implementation:

```python
# --- OpenFeature-compliant SDK ---

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Generic, Optional, TypeVar, Union

logger = logging.getLogger(__name__)
T = TypeVar("T")


class ErrorCode(str, Enum):
    PROVIDER_NOT_READY = "PROVIDER_NOT_READY"
    FLAG_NOT_FOUND = "FLAG_NOT_FOUND"
    PARSE_ERROR = "PARSE_ERROR"
    TYPE_MISMATCH = "TYPE_MISMATCH"
    TARGETING_KEY_MISSING = "TARGETING_KEY_MISSING"
    GENERAL = "GENERAL"


class Reason(str, Enum):
    STATIC = "STATIC"
    DEFAULT = "DEFAULT"
    TARGETING_MATCH = "TARGETING_MATCH"
    SPLIT = "SPLIT"
    CACHED = "CACHED"
    DISABLED = "DISABLED"
    UNKNOWN = "UNKNOWN"
    ERROR = "ERROR"


class ProviderEvent(str, Enum):
    READY = "PROVIDER_READY"
    ERROR = "PROVIDER_ERROR"
    CONFIGURATION_CHANGED = "PROVIDER_CONFIGURATION_CHANGED"
    STALE = "PROVIDER_STALE"


@dataclass
class EvaluationContext:
    """OpenFeature evaluation context."""
    targeting_key: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)

    def merge(self, other: EvaluationContext) -> EvaluationContext:
        """Merge contexts; other takes precedence."""
        merged_attrs = {**self.attributes, **other.attributes}
        return EvaluationContext(
            targeting_key=other.targeting_key or self.targeting_key,
            attributes=merged_attrs,
        )


@dataclass
class ResolutionDetails(Generic[T]):
    """Result of flag resolution from a provider."""
    value: T
    variant: str = ""
    reason: Reason = Reason.UNKNOWN
    error_code: Optional[ErrorCode] = None
    error_message: str = ""
    flag_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class HookContext:
    """Context passed to hooks during flag evaluation."""
    flag_key: str
    flag_type: str
    default_value: Any
    evaluation_context: EvaluationContext
    provider_metadata: dict[str, Any] = field(default_factory=dict)
    client_metadata: dict[str, Any] = field(default_factory=dict)


class Hook(ABC):
    """OpenFeature hook interface for evaluation lifecycle."""

    def before(
        self, ctx: HookContext, hints: dict[str, Any]
    ) -> Optional[EvaluationContext]:
        return None

    def after(
        self, ctx: HookContext, details: ResolutionDetails, hints: dict[str, Any]
    ) -> None:
        pass

    def error(
        self, ctx: HookContext, exception: Exception, hints: dict[str, Any]
    ) -> None:
        pass

    def finally_after(
        self, ctx: HookContext, hints: dict[str, Any]
    ) -> None:
        pass


class FeatureProvider(ABC):
    """OpenFeature provider interface (vendor-specific backend)."""

    @abstractmethod
    def get_metadata(self) -> dict[str, str]:
        ...

    @abstractmethod
    def resolve_boolean(
        self, flag_key: str, default: bool, context: EvaluationContext
    ) -> ResolutionDetails[bool]:
        ...

    @abstractmethod
    def resolve_string(
        self, flag_key: str, default: str, context: EvaluationContext
    ) -> ResolutionDetails[str]:
        ...

    @abstractmethod
    def resolve_integer(
        self, flag_key: str, default: int, context: EvaluationContext
    ) -> ResolutionDetails[int]:
        ...

    @abstractmethod
    def resolve_float(
        self, flag_key: str, default: float, context: EvaluationContext
    ) -> ResolutionDetails[float]:
        ...

    @abstractmethod
    def resolve_object(
        self, flag_key: str, default: dict, context: EvaluationContext
    ) -> ResolutionDetails[dict]:
        ...

    def initialize(self, context: EvaluationContext) -> None:
        pass

    def shutdown(self) -> None:
        pass


class OpenFeatureClient:
    """OpenFeature client with hooks, context, and provider."""

    def __init__(
        self,
        provider: FeatureProvider,
        name: str = "",
        version: str = "",
    ) -> None:
        self._provider = provider
        self._name = name
        self._version = version
        self._hooks: list[Hook] = []
        self._context = EvaluationContext()
        self._event_handlers: dict[ProviderEvent, list[Callable]] = {}

    def add_hooks(self, *hooks: Hook) -> None:
        self._hooks.extend(hooks)

    def set_context(self, context: EvaluationContext) -> None:
        self._context = context

    def get_boolean_value(
        self,
        flag_key: str,
        default: bool,
        context: Optional[EvaluationContext] = None,
    ) -> bool:
        details = self.get_boolean_details(flag_key, default, context)
        return details.value

    def get_boolean_details(
        self,
        flag_key: str,
        default: bool,
        context: Optional[EvaluationContext] = None,
    ) -> ResolutionDetails[bool]:
        merged = self._merge_context(context)
        hook_ctx = HookContext(
            flag_key=flag_key,
            flag_type="boolean",
            default_value=default,
            evaluation_context=merged,
            provider_metadata=self._provider.get_metadata(),
            client_metadata={"name": self._name, "version": self._version},
        )
        return self._evaluate(
            hook_ctx, lambda: self._provider.resolve_boolean(flag_key, default, merged),
            default,
        )

    def get_string_value(
        self,
        flag_key: str,
        default: str,
        context: Optional[EvaluationContext] = None,
    ) -> str:
        details = self.get_string_details(flag_key, default, context)
        return details.value

    def get_string_details(
        self,
        flag_key: str,
        default: str,
        context: Optional[EvaluationContext] = None,
    ) -> ResolutionDetails[str]:
        merged = self._merge_context(context)
        hook_ctx = HookContext(
            flag_key=flag_key,
            flag_type="string",
            default_value=default,
            evaluation_context=merged,
            provider_metadata=self._provider.get_metadata(),
            client_metadata={"name": self._name, "version": self._version},
        )
        return self._evaluate(
            hook_ctx, lambda: self._provider.resolve_string(flag_key, default, merged),
            default,
        )

    def _evaluate(
        self,
        hook_ctx: HookContext,
        resolver: Callable[[], ResolutionDetails],
        default: Any,
    ) -> ResolutionDetails:
        hints: dict[str, Any] = {}

        # Before hooks
        for hook in self._hooks:
            try:
                updated_ctx = hook.before(hook_ctx, hints)
                if updated_ctx:
                    hook_ctx.evaluation_context = updated_ctx
            except Exception as exc:
                logger.warning("Hook before failed: %s", exc)

        try:
            details = resolver()
            # After hooks
            for hook in self._hooks:
                try:
                    hook.after(hook_ctx, details, hints)
                except Exception as exc:
                    logger.warning("Hook after failed: %s", exc)
            return details
        except Exception as exc:
            # Error hooks
            for hook in self._hooks:
                try:
                    hook.error(hook_ctx, exc, hints)
                except Exception:
                    pass
            return ResolutionDetails(
                value=default,
                reason=Reason.ERROR,
                error_code=ErrorCode.GENERAL,
                error_message=str(exc),
            )
        finally:
            for hook in self._hooks:
                try:
                    hook.finally_after(hook_ctx, hints)
                except Exception:
                    pass

    def _merge_context(self, context: Optional[EvaluationContext]) -> EvaluationContext:
        if context:
            return self._context.merge(context)
        return self._context

    def on(self, event: ProviderEvent, handler: Callable) -> None:
        self._event_handlers.setdefault(event, []).append(handler)
```

```python
# --- LaunchDarkly provider implementation ---

class LaunchDarklyProvider(FeatureProvider):
    """OpenFeature provider backed by LaunchDarkly."""

    def __init__(self, sdk_key: str) -> None:
        import ldclient
        from ldclient.config import Config
        self._client = ldclient.LDClient(Config(sdk_key))

    def get_metadata(self) -> dict[str, str]:
        return {"name": "launchdarkly", "version": "1.0.0"}

    def resolve_boolean(
        self, flag_key: str, default: bool, context: EvaluationContext
    ) -> ResolutionDetails[bool]:
        ld_context = self._build_ld_context(context)
        detail = self._client.variation_detail(flag_key, ld_context, default)
        return ResolutionDetails(
            value=bool(detail.value),
            variant=str(detail.variation_index or ""),
            reason=self._map_reason(detail.reason),
        )

    def resolve_string(
        self, flag_key: str, default: str, context: EvaluationContext
    ) -> ResolutionDetails[str]:
        ld_context = self._build_ld_context(context)
        detail = self._client.variation_detail(flag_key, ld_context, default)
        return ResolutionDetails(
            value=str(detail.value),
            variant=str(detail.variation_index or ""),
            reason=self._map_reason(detail.reason),
        )

    def resolve_integer(
        self, flag_key: str, default: int, context: EvaluationContext
    ) -> ResolutionDetails[int]:
        ld_context = self._build_ld_context(context)
        detail = self._client.variation_detail(flag_key, ld_context, default)
        return ResolutionDetails(
            value=int(detail.value),
            variant=str(detail.variation_index or ""),
            reason=self._map_reason(detail.reason),
        )

    def resolve_float(
        self, flag_key: str, default: float, context: EvaluationContext
    ) -> ResolutionDetails[float]:
        ld_context = self._build_ld_context(context)
        detail = self._client.variation_detail(flag_key, ld_context, default)
        return ResolutionDetails(
            value=float(detail.value),
            variant=str(detail.variation_index or ""),
            reason=self._map_reason(detail.reason),
        )

    def resolve_object(
        self, flag_key: str, default: dict, context: EvaluationContext
    ) -> ResolutionDetails[dict]:
        ld_context = self._build_ld_context(context)
        detail = self._client.variation_detail(flag_key, ld_context, default)
        return ResolutionDetails(
            value=dict(detail.value) if isinstance(detail.value, dict) else default,
            variant=str(detail.variation_index or ""),
            reason=self._map_reason(detail.reason),
        )

    def _build_ld_context(self, context: EvaluationContext) -> Any:
        import ldclient
        return ldclient.Context.builder(context.targeting_key).set(
            "email", context.attributes.get("email", "")
        ).build()

    def _map_reason(self, reason: Any) -> Reason:
        kind = getattr(reason, "kind", "")
        mapping = {
            "OFF": Reason.DISABLED,
            "TARGET_MATCH": Reason.TARGETING_MATCH,
            "RULE_MATCH": Reason.TARGETING_MATCH,
            "FALLTHROUGH": Reason.DEFAULT,
        }
        return mapping.get(kind, Reason.UNKNOWN)

    def shutdown(self) -> None:
        self._client.close()


# --- Logging and metrics hook ---

class TelemetryHook(Hook):
    """Hook that logs evaluations and records metrics."""

    def __init__(self) -> None:
        self._eval_count = 0

    def after(
        self, ctx: HookContext, details: ResolutionDetails, hints: dict[str, Any]
    ) -> None:
        self._eval_count += 1
        logger.info(
            "Flag evaluated: key=%s variant=%s reason=%s",
            ctx.flag_key, details.variant, details.reason.value,
        )

    def error(
        self, ctx: HookContext, exception: Exception, hints: dict[str, Any]
    ) -> None:
        logger.error(
            "Flag evaluation error: key=%s error=%s",
            ctx.flag_key, str(exception),
        )
```

```yaml
# --- OpenFeature flagd configuration (self-hosted provider) ---
# flagd-config.yaml

apiVersion: core.openfeature.dev/v1beta1
kind: FeatureFlagSource
metadata:
  name: flag-source
spec:
  sources:
    - source: flag-config
      provider: kubernetes

---
apiVersion: core.openfeature.dev/v1beta1
kind: FeatureFlag
metadata:
  name: flag-config
spec:
  flagSpec:
    flags:
      new-checkout-flow:
        state: ENABLED
        variants:
          "on": true
          "off": false
        defaultVariant: "off"
        targeting:
          if:
            - in:
                - var: email
                - ["beta@company.com", "pm@company.com"]
            - "on"
            - fractional:
                - - "on"
                  - 25
                - - "off"
                  - 75

      pricing-model:
        state: ENABLED
        variants:
          flat: "flat-rate"
          usage: "usage-based"
          hybrid: "hybrid"
        defaultVariant: flat
        targeting:
          if:
            - in:
                - var: tier
                - ["enterprise"]
            - "hybrid"
            - fractional:
                - - "flat"
                  - 50
                - - "usage"
                  - 30
                - - "hybrid"
                  - 20

---
# Kubernetes operator for flag injection
apiVersion: core.openfeature.dev/v1beta1
kind: FlagSourceConfiguration
metadata:
  name: flagd-sidecar
spec:
  metricsPort: 8014
  port: 8013
  evaluator: json
  sources:
    - source: flag-config
      provider: kubernetes
  probesEnabled: true
```

| Feature | OpenFeature | LaunchDarkly SDK | Unleash SDK | Flagsmith SDK |
|---------|-------------|-----------------|-------------|---------------|
| Vendor neutral | Yes | No | No | No |
| Hook system | Yes (lifecycle) | Limited | No | No |
| Context merging | Yes (layered) | Implicit | Manual | Manual |
| Event system | Yes (standard) | Yes (custom) | Yes (custom) | Yes (custom) |
| Provider swap | Yes (interface) | N/A | N/A | N/A |
| Kubernetes native | Yes (flagd) | No | No | No |
| Type safety | Yes (generic) | Yes | Partial | Partial |

Key patterns for OpenFeature:

1. **Provider abstraction** -- implement FeatureProvider interface to swap LaunchDarkly, Unleash, flagd, or custom backends without changing application code
2. **Hook lifecycle** -- use before/after/error/finally hooks for logging, metrics, validation, and context enrichment across all evaluations
3. **Context merging** -- layer global, client, and invocation contexts with clear precedence rules
4. **Resolution details** -- return variant name, reason, and error code alongside the value for observability and debugging
5. **Event-driven updates** -- subscribe to PROVIDER_READY and CONFIGURATION_CHANGED events for real-time flag sync
6. **flagd sidecar** -- deploy the OpenFeature flagd sidecar in Kubernetes for GitOps-managed flag configuration
7. **Type-safe resolution** -- use separate resolve methods per type (boolean, string, int, float, object) to catch mismatches at evaluation time'''
    ),
    (
        "feature-flags/cleanup-tech-debt",
        "Design a feature flag lifecycle management system that detects stale flags, automates cleanup, tracks flag dependencies, and generates removal pull requests to prevent tech debt accumulation.",
        '''Feature flag cleanup and tech debt management:

```python
# --- Feature flag lifecycle and staleness detection ---

from __future__ import annotations

import ast
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class FlagLifecycleState(str, Enum):
    ACTIVE = "active"
    RAMPING = "ramping"             # Being rolled out
    FULLY_ROLLED = "fully_rolled"   # 100% but not cleaned up
    STALE = "stale"                 # Past cleanup deadline
    PERMANENT = "permanent"         # Kill switch / ops flag


@dataclass
class FlagMetadata:
    """Metadata for tracking flag lifecycle."""
    key: str
    owner: str
    team: str
    created_at: datetime
    description: str
    flag_type: str  # release, experiment, ops, kill_switch, permission
    jira_ticket: str = ""
    cleanup_deadline: Optional[datetime] = None
    last_evaluated: Optional[datetime] = None
    evaluation_count_30d: int = 0
    code_references: list[str] = field(default_factory=list)
    rollout_percentage: float = 0.0
    is_permanent: bool = False

    @property
    def lifecycle_state(self) -> FlagLifecycleState:
        if self.is_permanent:
            return FlagLifecycleState.PERMANENT
        if self.rollout_percentage >= 100.0:
            if self.cleanup_deadline and datetime.now(timezone.utc) > self.cleanup_deadline:
                return FlagLifecycleState.STALE
            return FlagLifecycleState.FULLY_ROLLED
        if self.rollout_percentage > 0:
            return FlagLifecycleState.RAMPING
        return FlagLifecycleState.ACTIVE

    @property
    def days_since_creation(self) -> int:
        return (datetime.now(timezone.utc) - self.created_at).days

    @property
    def days_until_cleanup(self) -> Optional[int]:
        if self.cleanup_deadline:
            delta = self.cleanup_deadline - datetime.now(timezone.utc)
            return delta.days
        return None


class FlagCodeScanner:
    """Scan codebase for feature flag references."""

    FLAG_PATTERNS = [
        # Python SDK calls
        r'get_boolean\(\s*["\']([^"\']+)["\']',
        r'get_string\(\s*["\']([^"\']+)["\']',
        r'get_integer\(\s*["\']([^"\']+)["\']',
        r'feature_flag\(\s*["\']([^"\']+)["\']',
        r'is_enabled\(\s*["\']([^"\']+)["\']',
        # TypeScript/JS patterns
        r'useFeatureFlag\(\s*["\']([^"\']+)["\']',
        r'client\.getBooleanValue\(\s*["\']([^"\']+)["\']',
        # Generic patterns
        r'FLAG_([A-Z_]+)',
        r'feature[_.]flags?\[["\']([^"\']+)["\']',
    ]

    def __init__(self, repo_root: str, exclude_dirs: Optional[list[str]] = None) -> None:
        self.repo_root = Path(repo_root)
        self.exclude_dirs = exclude_dirs or [
            "node_modules", ".git", "__pycache__", "venv", ".venv",
            "dist", "build", ".tox",
        ]

    def scan_for_flag(self, flag_key: str) -> list[dict[str, Any]]:
        """Find all references to a specific flag in the codebase."""
        references: list[dict[str, Any]] = []
        for ext in ("*.py", "*.ts", "*.tsx", "*.js", "*.jsx", "*.go"):
            for filepath in self.repo_root.rglob(ext):
                if any(d in filepath.parts for d in self.exclude_dirs):
                    continue
                try:
                    content = filepath.read_text(encoding="utf-8")
                    for i, line in enumerate(content.splitlines(), 1):
                        if flag_key in line:
                            references.append({
                                "file": str(filepath.relative_to(self.repo_root)),
                                "line": i,
                                "content": line.strip(),
                                "context": self._get_context(content, i),
                            })
                except (OSError, UnicodeDecodeError):
                    continue
        return references

    def find_all_flags(self) -> set[str]:
        """Discover all flag keys referenced in the codebase."""
        flags: set[str] = set()
        for ext in ("*.py", "*.ts", "*.tsx", "*.js", "*.jsx"):
            for filepath in self.repo_root.rglob(ext):
                if any(d in filepath.parts for d in self.exclude_dirs):
                    continue
                try:
                    content = filepath.read_text(encoding="utf-8")
                    for pattern in self.FLAG_PATTERNS:
                        flags.update(re.findall(pattern, content))
                except (OSError, UnicodeDecodeError):
                    continue
        return flags

    def _get_context(self, content: str, line_num: int, window: int = 3) -> str:
        lines = content.splitlines()
        start = max(0, line_num - window - 1)
        end = min(len(lines), line_num + window)
        return "\n".join(lines[start:end])


class StalenesssDetector:
    """Detect stale flags that need cleanup."""

    def __init__(
        self,
        default_stale_days: int = 90,
        experiment_stale_days: int = 30,
        release_stale_days: int = 14,
    ) -> None:
        self.stale_thresholds = {
            "release": release_stale_days,
            "experiment": experiment_stale_days,
            "ops": default_stale_days,
            "kill_switch": None,  # Never stale
            "permission": None,  # Never stale
        }

    def check_staleness(
        self, flags: list[FlagMetadata]
    ) -> dict[str, list[FlagMetadata]]:
        """Categorize flags by staleness severity."""
        results: dict[str, list[FlagMetadata]] = {
            "stale": [],
            "approaching_deadline": [],
            "fully_rolled_no_cleanup": [],
            "orphaned": [],  # In code but not in flag service
            "healthy": [],
        }

        for flag in flags:
            threshold = self.stale_thresholds.get(flag.flag_type)
            if threshold is None:
                results["healthy"].append(flag)
                continue

            state = flag.lifecycle_state
            if state == FlagLifecycleState.STALE:
                results["stale"].append(flag)
            elif state == FlagLifecycleState.FULLY_ROLLED:
                days_at_100 = flag.days_since_creation
                if days_at_100 > threshold:
                    results["fully_rolled_no_cleanup"].append(flag)
                elif flag.days_until_cleanup and flag.days_until_cleanup < 7:
                    results["approaching_deadline"].append(flag)
                else:
                    results["healthy"].append(flag)
            elif flag.evaluation_count_30d == 0 and flag.days_since_creation > 30:
                results["orphaned"].append(flag)
            else:
                results["healthy"].append(flag)

        return results

    def generate_report(
        self, flags: list[FlagMetadata]
    ) -> str:
        """Generate human-readable staleness report."""
        categories = self.check_staleness(flags)
        lines = ["# Feature Flag Health Report", ""]

        for category, items in categories.items():
            if items:
                lines.append(f"## {category.replace('_', ' ').title()} ({len(items)})")
                for flag in items:
                    lines.append(
                        f"- **{flag.key}** (owner: {flag.owner}, "
                        f"age: {flag.days_since_creation}d, "
                        f"rollout: {flag.rollout_percentage}%, "
                        f"evals/30d: {flag.evaluation_count_30d})"
                    )
                lines.append("")

        return "\n".join(lines)
```

```python
# --- Automated flag removal PR generator ---

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class FlagRemovalPlan:
    """Plan for removing a feature flag from the codebase."""
    flag_key: str
    target_value: Any  # The value to hardcode (the winning variant)
    files_to_modify: list[dict[str, Any]]
    tests_to_update: list[str]
    config_to_clean: list[str]
    estimated_lines_removed: int = 0

    def to_pr_description(self) -> str:
        return (
            f"## Remove feature flag: `{self.flag_key}`\\n\\n"
            f"### Changes\\n"
            f"- Hardcode winning variant: `{self.target_value}`\\n"
            f"- Files modified: {len(self.files_to_modify)}\\n"
            f"- Tests updated: {len(self.tests_to_update)}\\n"
            f"- Lines removed: ~{self.estimated_lines_removed}\\n\\n"
            f"### Checklist\\n"
            f"- [ ] Flag removed from flag service\\n"
            f"- [ ] Dead code paths removed\\n"
            f"- [ ] Tests updated to not mock flag\\n"
            f"- [ ] Monitoring confirms no issues\\n"
        )


class FlagRemovalGenerator:
    """Generate code changes to remove a feature flag."""

    def __init__(self, repo_root: str) -> None:
        self.repo_root = Path(repo_root)
        self.scanner = FlagCodeScanner(repo_root)

    def plan_removal(
        self, flag: FlagMetadata, winning_value: Any
    ) -> FlagRemovalPlan:
        """Create a removal plan for a flag."""
        references = self.scanner.scan_for_flag(flag.key)
        files_to_modify = []
        tests_to_update = []
        lines_removed = 0

        for ref in references:
            filepath = ref["file"]
            if "test" in filepath.lower() or "spec" in filepath.lower():
                tests_to_update.append(filepath)
            else:
                files_to_modify.append(ref)
                lines_removed += self._estimate_removable_lines(ref, winning_value)

        return FlagRemovalPlan(
            flag_key=flag.key,
            target_value=winning_value,
            files_to_modify=files_to_modify,
            tests_to_update=tests_to_update,
            config_to_clean=[f"flags/{flag.key}.yaml"],
            estimated_lines_removed=lines_removed,
        )

    def generate_removal_diff(
        self, plan: FlagRemovalPlan
    ) -> dict[str, str]:
        """Generate file diffs for flag removal."""
        diffs: dict[str, str] = {}

        for ref in plan.files_to_modify:
            filepath = self.repo_root / ref["file"]
            try:
                content = filepath.read_text(encoding="utf-8")
                new_content = self._remove_flag_from_content(
                    content, plan.flag_key, plan.target_value
                )
                if new_content != content:
                    diffs[ref["file"]] = new_content
            except OSError:
                logger.warning("Cannot read file: %s", filepath)

        return diffs

    def _remove_flag_from_content(
        self, content: str, flag_key: str, winning_value: Any
    ) -> str:
        """Remove flag checks and replace with winning value."""
        lines = content.splitlines()
        result_lines = []
        skip_else = False
        indent_to_remove = ""

        for line in lines:
            if flag_key in line:
                # Simple boolean check: if feature_flag("key"):
                if re.match(r'\s*if\s+.*' + re.escape(flag_key), line):
                    if winning_value:
                        # Keep the if body, remove the check
                        indent_to_remove = re.match(r'(\s*)', line).group(1)
                        skip_else = True
                        continue
                    else:
                        # Skip to else branch
                        continue
            result_lines.append(line)

        return "\n".join(result_lines)

    def _estimate_removable_lines(
        self, ref: dict[str, Any], winning_value: Any
    ) -> int:
        context = ref.get("context", "")
        return max(3, len(context.splitlines()))

    def create_pr(self, plan: FlagRemovalPlan) -> str:
        """Create a PR for flag removal using GitHub CLI."""
        branch = f"cleanup/remove-flag-{plan.flag_key}"
        diffs = self.generate_removal_diff(plan)

        commands = [
            f"git checkout -b {branch}",
        ]
        for filepath, content in diffs.items():
            full_path = self.repo_root / filepath
            full_path.write_text(content, encoding="utf-8")
            commands.append(f"git add {filepath}")

        commands.extend([
            f'git commit -m "chore: remove stale feature flag {plan.flag_key}"',
            f"git push -u origin {branch}",
            (
                f'gh pr create --title "chore: remove flag {plan.flag_key}" '
                f'--body "{plan.to_pr_description()}"'
            ),
        ])
        return "\n".join(commands)
```

```yaml
# --- Flag lifecycle CI/CD pipeline ---
# .github/workflows/flag-hygiene.yml

name: Feature Flag Hygiene
on:
  schedule:
    - cron: "0 9 * * 1"  # Weekly Monday 9am
  workflow_dispatch:

jobs:
  flag-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install httpx pyyaml

      - name: Scan codebase for flag references
        run: |
          python scripts/flag_scanner.py \
            --repo-root . \
            --output flag-references.json

      - name: Check flag service for stale flags
        env:
          FLAG_SERVICE_URL: ${{ secrets.FLAG_SERVICE_URL }}
          FLAG_SERVICE_TOKEN: ${{ secrets.FLAG_SERVICE_TOKEN }}
        run: |
          python scripts/flag_staleness.py \
            --references flag-references.json \
            --stale-days 90 \
            --output staleness-report.json

      - name: Generate cleanup PRs for stale flags
        if: always()
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          python scripts/flag_cleanup.py \
            --report staleness-report.json \
            --auto-pr \
            --max-prs 3

      - name: Post report to Slack
        if: always()
        uses: slackapi/slack-github-action@v1
        with:
          channel-id: "C0FLAGTEAM"
          payload-file-path: staleness-report.json
        env:
          SLACK_BOT_TOKEN: ${{ secrets.SLACK_BOT_TOKEN }}

      - name: Fail if critical stale flags exist
        run: |
          python -c "
          import json, sys
          report = json.load(open('staleness-report.json'))
          stale = report.get('stale', [])
          if len(stale) > 5:
              print(f'CRITICAL: {len(stale)} stale flags exceed threshold')
              sys.exit(1)
          print(f'OK: {len(stale)} stale flags within threshold')
          "
```

| Cleanup Strategy | Trigger | Action | Risk |
|-----------------|---------|--------|------|
| Auto-PR on deadline | Flag reaches cleanup_deadline | Generate removal PR | Low (reviewed by humans) |
| Forced removal | 2x past deadline | Auto-merge removal PR | Medium (may break code) |
| Orphan detection | No evaluations in 30d | Alert owner, create ticket | Low |
| Dependency scan | Weekly CI | Report flags used in other flags | Low |
| Code coverage | On PR | Flag unused code paths from flags | Low |

Key patterns for feature flag cleanup:

1. **Mandatory cleanup deadlines** -- set cleanup_deadline at flag creation; escalate when deadlines pass
2. **Code scanning** -- use regex patterns to find all flag references across the codebase including tests
3. **Staleness tiers** -- release flags stale after 14 days at 100%, experiments after 30 days, ops flags after 90 days
4. **Automated PR generation** -- generate removal PRs that hardcode the winning variant and delete dead code paths
5. **Weekly hygiene CI** -- run scheduled pipeline to audit flags, generate reports, and auto-create cleanup PRs
6. **Orphan detection** -- flags with zero evaluations in 30 days are likely dead code; alert the owner
7. **Flag budget** -- limit total active non-permanent flags per team (e.g., max 20) to force cleanup discipline'''
    ),
    (
        "feature-flags/trunk-based-development",
        "Design a trunk-based development workflow using feature flags for safe continuous deployment, including branch-by-abstraction, dark launching, and flag-driven testing strategies.",
        '''Trunk-based development with feature flags:

```python
# --- Branch-by-abstraction with feature flags ---

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Generic, Optional, TypeVar

logger = logging.getLogger(__name__)
T = TypeVar("T")


class PaymentProcessor(ABC):
    """Abstract interface for branch-by-abstraction pattern."""

    @abstractmethod
    async def charge(self, amount: float, currency: str, token: str) -> dict[str, Any]:
        ...

    @abstractmethod
    async def refund(self, transaction_id: str, amount: float) -> dict[str, Any]:
        ...

    @abstractmethod
    async def get_transaction(self, transaction_id: str) -> dict[str, Any]:
        ...


class LegacyStripeProcessor(PaymentProcessor):
    """Existing payment processor (to be replaced)."""

    async def charge(self, amount: float, currency: str, token: str) -> dict[str, Any]:
        logger.info("Legacy Stripe charge: %s %s", amount, currency)
        # ... existing Stripe v1 API integration ...
        return {"id": "ch_legacy_123", "status": "succeeded", "provider": "stripe_v1"}

    async def refund(self, transaction_id: str, amount: float) -> dict[str, Any]:
        return {"id": "re_legacy_456", "status": "succeeded"}

    async def get_transaction(self, transaction_id: str) -> dict[str, Any]:
        return {"id": transaction_id, "provider": "stripe_v1"}


class NewAdyenProcessor(PaymentProcessor):
    """New payment processor being migrated to."""

    async def charge(self, amount: float, currency: str, token: str) -> dict[str, Any]:
        logger.info("Adyen charge: %s %s", amount, currency)
        # ... new Adyen API integration ...
        return {"id": "adyen_psp_789", "status": "Authorised", "provider": "adyen"}

    async def refund(self, transaction_id: str, amount: float) -> dict[str, Any]:
        return {"id": "adyen_ref_012", "status": "Received"}

    async def get_transaction(self, transaction_id: str) -> dict[str, Any]:
        return {"id": transaction_id, "provider": "adyen"}


class FlaggedPaymentRouter(PaymentProcessor):
    """Route payment calls based on feature flag with shadow traffic."""

    def __init__(
        self,
        legacy: PaymentProcessor,
        new: PaymentProcessor,
        flag_client: Any,  # FeatureFlagClient
    ) -> None:
        self.legacy = legacy
        self.new = new
        self.flag_client = flag_client

    async def charge(self, amount: float, currency: str, token: str) -> dict[str, Any]:
        context = self._get_context()
        use_new = self.flag_client.get_boolean("payments.use-adyen", context)
        shadow = self.flag_client.get_boolean("payments.shadow-adyen", context)

        if use_new:
            return await self.new.charge(amount, currency, token)

        # Shadow mode: call both, return legacy result
        result = await self.legacy.charge(amount, currency, token)
        if shadow:
            try:
                shadow_result = await self.new.charge(amount, currency, token)
                self._compare_results("charge", result, shadow_result)
            except Exception as exc:
                logger.error("Shadow charge failed: %s", exc)
        return result

    async def refund(self, transaction_id: str, amount: float) -> dict[str, Any]:
        context = self._get_context()
        use_new = self.flag_client.get_boolean("payments.use-adyen", context)
        if use_new:
            return await self.new.refund(transaction_id, amount)
        return await self.legacy.refund(transaction_id, amount)

    async def get_transaction(self, transaction_id: str) -> dict[str, Any]:
        context = self._get_context()
        use_new = self.flag_client.get_boolean("payments.use-adyen", context)
        if use_new:
            return await self.new.get_transaction(transaction_id)
        return await self.legacy.get_transaction(transaction_id)

    def _get_context(self) -> Any:
        from contextvars import ContextVar
        return ContextVar("flag_context").get(None)

    def _compare_results(
        self, operation: str, legacy: dict, new: dict
    ) -> None:
        """Compare shadow results for validation."""
        differences = {
            k: {"legacy": legacy.get(k), "new": new.get(k)}
            for k in set(legacy) | set(new)
            if legacy.get(k) != new.get(k) and k not in ("id", "provider")
        }
        if differences:
            logger.warning(
                "Shadow mismatch in %s: %s", operation, differences
            )
```

```python
# --- Dark launch and flag-driven testing ---

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class DarkLaunchConfig:
    """Configuration for dark launching a new feature."""
    feature_name: str
    flag_key: str
    shadow_flag_key: str  # Run both paths, compare results
    metrics_prefix: str
    comparison_keys: list[str] = field(default_factory=list)
    max_shadow_latency_ms: float = 500.0
    log_mismatches: bool = True
    alert_on_mismatch_rate: float = 0.05  # 5% mismatch threshold


class DarkLaunchManager:
    """Manage dark launches with shadow traffic and comparison."""

    def __init__(self, flag_client: Any) -> None:
        self.flag_client = flag_client
        self._mismatch_count = 0
        self._total_shadow_count = 0

    async def execute_with_shadow(
        self,
        config: DarkLaunchConfig,
        context: Any,
        primary_fn: Callable,
        shadow_fn: Callable,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute primary function, optionally run shadow for comparison."""
        use_new = self.flag_client.get_boolean(config.flag_key, context)
        run_shadow = self.flag_client.get_boolean(config.shadow_flag_key, context)

        if use_new:
            return await shadow_fn(*args, **kwargs)

        primary_result = await primary_fn(*args, **kwargs)

        if run_shadow:
            self._total_shadow_count += 1
            try:
                shadow_start = time.perf_counter()
                shadow_result = await asyncio.wait_for(
                    shadow_fn(*args, **kwargs),
                    timeout=config.max_shadow_latency_ms / 1000,
                )
                shadow_ms = (time.perf_counter() - shadow_start) * 1000

                mismatches = self._compare(
                    primary_result, shadow_result, config.comparison_keys
                )
                if mismatches:
                    self._mismatch_count += 1
                    if config.log_mismatches:
                        logger.warning(
                            "Dark launch mismatch for %s: %s (shadow: %.1fms)",
                            config.feature_name, mismatches, shadow_ms,
                        )
            except asyncio.TimeoutError:
                logger.warning(
                    "Shadow timed out for %s (limit: %.0fms)",
                    config.feature_name, config.max_shadow_latency_ms,
                )
            except Exception as exc:
                logger.error("Shadow failed for %s: %s", config.feature_name, exc)

        return primary_result

    def _compare(
        self, primary: Any, shadow: Any, keys: list[str]
    ) -> list[dict[str, Any]]:
        mismatches = []
        if isinstance(primary, dict) and isinstance(shadow, dict):
            for key in keys or primary.keys():
                if primary.get(key) != shadow.get(key):
                    mismatches.append({
                        "key": key,
                        "primary": primary.get(key),
                        "shadow": shadow.get(key),
                    })
        return mismatches

    @property
    def mismatch_rate(self) -> float:
        if self._total_shadow_count == 0:
            return 0.0
        return self._mismatch_count / self._total_shadow_count


class FlagDrivenTestStrategy:
    """Testing patterns for flag-gated features."""

    @staticmethod
    def create_test_matrix(
        flag_key: str, scenarios: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Generate test matrix covering both flag states."""
        matrix = []
        for scenario in scenarios:
            # Test with flag ON
            on_case = {**scenario, "flag_state": True, "flag_key": flag_key}
            on_case["test_name"] = f"{scenario.get('name', 'test')}__flag_on"
            matrix.append(on_case)

            # Test with flag OFF
            off_case = {**scenario, "flag_state": False, "flag_key": flag_key}
            off_case["test_name"] = f"{scenario.get('name', 'test')}__flag_off"
            matrix.append(off_case)
        return matrix

    @staticmethod
    def pytest_parametrize_flags(
        flag_keys: list[str],
    ) -> list[dict[str, bool]]:
        """Generate pytest parametrize combinations for multiple flags."""
        import itertools
        combinations = list(itertools.product([True, False], repeat=len(flag_keys)))
        return [
            dict(zip(flag_keys, combo))
            for combo in combinations
        ]
```

```yaml
# --- Trunk-based development CI pipeline with flag awareness ---
# .github/workflows/trunk-deploy.yml

name: Trunk-Based Deploy
on:
  push:
    branches: [main]

concurrency:
  group: deploy-production
  cancel-in-progress: false

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        include:
          # Test with all flags off (baseline)
          - flag-set: "baseline"
            flag-overrides: "{}"
          # Test with new flags on (upcoming features)
          - flag-set: "next-release"
            flag-overrides: '{"payments.use-adyen": true, "new-search": true}'
    steps:
      - uses: actions/checkout@v4

      - name: Run tests with flag configuration
        env:
          FLAG_OVERRIDES: ${{ matrix.flag-overrides }}
        run: |
          pytest tests/ \
            --flag-overrides="$FLAG_OVERRIDES" \
            -v --tb=short

      - name: Run integration tests
        env:
          FLAG_OVERRIDES: ${{ matrix.flag-overrides }}
        run: |
          pytest tests/integration/ \
            --flag-overrides="$FLAG_OVERRIDES" \
            -v

  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Deploy to production
        run: |
          # Deploy the code - flags control feature visibility
          kubectl set image deployment/api \
            api=${{ env.REGISTRY }}/api:${{ github.sha }}

      - name: Verify deployment health
        run: |
          kubectl rollout status deployment/api --timeout=300s

      - name: Run smoke tests
        run: |
          python scripts/smoke_test.py \
            --endpoint https://api.production.internal \
            --flag-aware

      - name: Notify deploy complete
        if: success()
        run: |
          curl -X POST "$SLACK_WEBHOOK" \
            -d "{\"text\": \"Deployed ${{ github.sha }} to production. Active flags: $(python scripts/list_active_flags.py)\"}"

  flag-validation:
    needs: deploy
    runs-on: ubuntu-latest
    steps:
      - name: Validate flag consistency
        run: |
          python scripts/validate_flags.py \
            --check-stale \
            --check-orphaned \
            --check-conflicts \
            --max-active-flags 50

      - name: Check shadow traffic results
        if: always()
        run: |
          python scripts/shadow_report.py \
            --window 30m \
            --mismatch-threshold 0.05
```

| Strategy | When to Use | Implementation | Risk Level |
|----------|-------------|---------------|------------|
| Branch by abstraction | Replacing major subsystem | Interface + flag router | Low |
| Dark launch / shadow | Validating new backend | Dual execution, compare results | Low |
| Feature toggle | Simple on/off feature | Boolean flag check | Low |
| Experiment | A/B testing behavior | Weighted variants + analytics | Medium |
| Kill switch | Emergency disable | Permanent boolean, defaults ON | Low |
| Percentage rollout | Gradual release | Hash-based bucketing | Low |
| Canary + flag | Infrastructure + feature | Deploy canary, enable flag for canary | Medium |

| Approach | Trunk-Based + Flags | Long-Lived Feature Branches |
|----------|--------------------|-----------------------------|
| Merge frequency | Daily / per-commit | Weekly / monthly |
| Merge conflicts | Rare (small diffs) | Common (large diffs) |
| Integration risk | Low (continuous) | High (big-bang merge) |
| Rollback speed | Instant (toggle flag) | Revert + redeploy |
| Code review | Small, focused PRs | Large, hard-to-review PRs |
| CI/CD pipeline | Simple (one branch) | Complex (per-branch envs) |
| Feature isolation | Via flags | Via branches |
| Tech debt risk | Stale flags | Stale branches |

Key patterns for trunk-based development with flags:

1. **Branch by abstraction** -- introduce an interface, implement new behavior behind a flag, swap at runtime without merge conflicts
2. **Dark launching** -- shadow traffic to new systems, compare results against the legacy path before switching over
3. **Flag-driven test matrix** -- test both flag states in CI to ensure both paths work before and after rollout
4. **Trunk CI with flag configs** -- run tests with flags off (baseline) and flags on (next release) in parallel matrix builds
5. **Instant rollback** -- toggle a flag off in seconds instead of reverting a deploy and waiting for a rollout
6. **Shadow comparison** -- set timeout and mismatch thresholds for shadow traffic to catch behavioral differences early
7. **Deploy code daily, release features weekly** -- separate deployment (infrastructure) from release (feature visibility) using flags'''
    ),
]
"""
