PAIRS = [
    (
        "architecture/chaos-engineering",
        r"""Explain chaos engineering principles including the discipline's philosophy, designing chaos experiments, blast radius control, steady-state hypothesis, common failure injections (latency, errors, resource exhaustion), and tools like Chaos Monkey and Litmus. Include a Python chaos testing framework.""",
        r"""## Chaos Engineering: Proactive Failure Testing for Resilient Systems

Chaos engineering is the discipline of experimenting on distributed systems to build confidence in their ability to withstand turbulent conditions. It's not about breaking things randomly — it's about scientifically testing failure hypotheses.

### The Chaos Engineering Process

```
1. Define steady state (normal behavior metrics)
2. Hypothesize: "The system will maintain steady state when X fails"
3. Design experiment with controlled blast radius
4. Run experiment in production (or staging)
5. Observe: did steady state hold?
6. Fix: if it didn't, improve resilience
7. Repeat
```

### Chaos Experiment Framework

```python
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Optional
import asyncio
import random
import logging

logger = logging.getLogger(__name__)


class ExperimentState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ABORTED = "aborted"


@dataclass
class SteadyStateMetric:
    """Define what 'normal' looks like."""
    name: str
    check: Callable  # Returns True if metric is within normal range
    description: str


@dataclass
class ChaosExperiment:
    """A structured chaos experiment."""
    name: str
    hypothesis: str
    steady_state_metrics: list[SteadyStateMetric]
    inject: Callable  # The chaos injection function
    rollback: Callable  # How to undo the injection
    duration_seconds: float = 60.0
    blast_radius: str = "single-instance"  # How much is affected
    state: ExperimentState = ExperimentState.PENDING
    results: dict = field(default_factory=dict)


class ChaosRunner:
    """Run chaos experiments safely with automatic rollback."""

    def __init__(self, abort_threshold: float = 0.5):
        self.abort_threshold = abort_threshold  # Abort if > 50% metrics fail
        self._active_experiment: Optional[ChaosExperiment] = None

    async def run(self, experiment: ChaosExperiment) -> dict:
        logger.info(f"Starting experiment: {experiment.name}")
        logger.info(f"Hypothesis: {experiment.hypothesis}")
        experiment.state = ExperimentState.RUNNING
        self._active_experiment = experiment

        # Phase 1: Verify steady state BEFORE injection
        pre_check = await self._check_steady_state(experiment)
        if not pre_check["all_passing"]:
            logger.error("Steady state NOT established before experiment — aborting")
            experiment.state = ExperimentState.ABORTED
            return {"aborted": True, "reason": "pre-check failed", **pre_check}

        # Phase 2: Inject chaos
        try:
            logger.info(f"Injecting chaos: {experiment.name}")
            await experiment.inject()

            # Phase 3: Observe during experiment
            observations = []
            check_interval = min(5.0, experiment.duration_seconds / 10)
            elapsed = 0.0

            while elapsed < experiment.duration_seconds:
                await asyncio.sleep(check_interval)
                elapsed += check_interval

                check = await self._check_steady_state(experiment)
                observations.append(check)

                # Safety: abort if too many metrics failing
                fail_rate = 1 - check["pass_rate"]
                if fail_rate > self.abort_threshold:
                    logger.warning(
                        f"Abort threshold exceeded ({fail_rate:.0%} failing) "
                        f"— rolling back immediately"
                    )
                    break

        finally:
            # Phase 4: ALWAYS rollback
            logger.info("Rolling back chaos injection")
            await experiment.rollback()
            self._active_experiment = None

        # Phase 5: Verify recovery
        await asyncio.sleep(10)  # Grace period for recovery
        post_check = await self._check_steady_state(experiment)

        experiment.state = ExperimentState.COMPLETED
        experiment.results = {
            "pre_check": pre_check,
            "observations": observations,
            "post_check": post_check,
            "hypothesis_held": all(
                obs["all_passing"] for obs in observations
            ),
            "recovered": post_check["all_passing"],
        }

        return experiment.results

    async def _check_steady_state(self, experiment: ChaosExperiment) -> dict:
        results = {}
        passing = 0
        for metric in experiment.steady_state_metrics:
            try:
                is_passing = await metric.check()
                results[metric.name] = {"passing": is_passing}
                if is_passing:
                    passing += 1
            except Exception as e:
                results[metric.name] = {"passing": False, "error": str(e)}

        total = len(experiment.steady_state_metrics)
        return {
            "metrics": results,
            "all_passing": passing == total,
            "pass_rate": passing / total if total > 0 else 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
```

### Common Chaos Injections

```python
import aiohttp
import os
import signal


class ChaosInjectors:
    """Library of chaos injection strategies."""

    @staticmethod
    async def inject_latency(
        proxy_url: str,
        target_service: str,
        latency_ms: int = 500,
    ):
        """Add artificial latency to service calls."""
        async with aiohttp.ClientSession() as session:
            await session.post(f"{proxy_url}/faults", json={
                "target": target_service,
                "type": "latency",
                "latency_ms": latency_ms,
                "percentage": 100,
            })

    @staticmethod
    async def inject_errors(
        proxy_url: str,
        target_service: str,
        error_rate: float = 0.5,
        status_code: int = 500,
    ):
        """Inject HTTP errors into service responses."""
        async with aiohttp.ClientSession() as session:
            await session.post(f"{proxy_url}/faults", json={
                "target": target_service,
                "type": "error",
                "status_code": status_code,
                "percentage": int(error_rate * 100),
            })

    @staticmethod
    async def kill_instance(instance_id: str, provider: str = "docker"):
        """Terminate a service instance (Chaos Monkey style)."""
        if provider == "docker":
            proc = await asyncio.create_subprocess_exec(
                "docker", "stop", instance_id,
                stdout=asyncio.subprocess.PIPE,
            )
            await proc.wait()

    @staticmethod
    async def exhaust_cpu(target_host: str, duration_seconds: int = 30):
        """Simulate CPU pressure via stress tool."""
        proc = await asyncio.create_subprocess_exec(
            "ssh", target_host,
            f"stress --cpu $(nproc) --timeout {duration_seconds}s",
            stdout=asyncio.subprocess.PIPE,
        )
        await proc.wait()

    @staticmethod
    async def fill_disk(target_host: str, size_mb: int = 500):
        """Simulate disk pressure."""
        proc = await asyncio.create_subprocess_exec(
            "ssh", target_host,
            f"dd if=/dev/zero of=/tmp/chaos_fill bs=1M count={size_mb}",
            stdout=asyncio.subprocess.PIPE,
        )
        await proc.wait()

    @staticmethod
    async def partition_network(
        container: str,
        target_network: str,
        duration_seconds: int = 30,
    ):
        """Simulate network partition between containers."""
        await asyncio.create_subprocess_exec(
            "docker", "network", "disconnect", target_network, container,
        )
        # Auto-reconnect after duration
        await asyncio.sleep(duration_seconds)
        await asyncio.create_subprocess_exec(
            "docker", "network", "connect", target_network, container,
        )


# Example experiment
async def run_database_latency_experiment():
    runner = ChaosRunner(abort_threshold=0.3)

    experiment = ChaosExperiment(
        name="database-latency-resilience",
        hypothesis="API maintains <2s p99 latency when database has 500ms added latency",
        steady_state_metrics=[
            SteadyStateMetric(
                name="api_p99_latency",
                check=lambda: check_api_latency(max_ms=2000),
                description="API p99 latency under 2 seconds",
            ),
            SteadyStateMetric(
                name="error_rate",
                check=lambda: check_error_rate(max_pct=1.0),
                description="Error rate below 1%",
            ),
            SteadyStateMetric(
                name="throughput",
                check=lambda: check_throughput(min_rps=100),
                description="Throughput above 100 req/s",
            ),
        ],
        inject=lambda: ChaosInjectors.inject_latency(
            "http://toxiproxy:8474", "postgres", 500
        ),
        rollback=lambda: remove_all_faults("http://toxiproxy:8474"),
        duration_seconds=120,
        blast_radius="single-database",
    )

    results = await runner.run(experiment)

    if results["hypothesis_held"]:
        print("PASS: System maintained steady state under database latency")
    else:
        print("FAIL: System degraded — investigate and improve resilience")
        print(f"Recovery: {'Yes' if results['recovered'] else 'No'}")
```

**Chaos engineering principles**: (1) Always start with a hypothesis and steady-state definition, (2) Start small — single instance, low blast radius, staging environment, (3) Automate rollback — never let a chaos experiment cause extended outage, (4) Run in production (eventually) — staging doesn't have real traffic patterns, (5) Common experiments: database latency, service instance death, network partition, disk full, CPU saturation."""
    ),
    (
        "architecture/deployment-strategies",
        r"""Explain deployment strategies including blue-green deployments, canary releases, rolling updates, feature flags for progressive rollout, A/B testing infrastructure, and rollback procedures. Include practical implementation patterns.""",
        r"""## Deployment Strategies: Blue-Green, Canary, Rolling, and Feature Flags

How you deploy code is as important as what you deploy. The right strategy minimizes risk while enabling rapid iteration.

### Blue-Green Deployments

Two identical environments; switch traffic atomically:

```
                    ┌──────────────┐
                    │  Load        │
                    │  Balancer    │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────┴─────┐           ┌─────┴─────┐
        │  BLUE     │           │  GREEN    │
        │  (v1.0)   │   ──→    │  (v1.1)   │
        │  ACTIVE   │           │  STAGING  │
        └───────────┘           └───────────┘

1. Deploy v1.1 to GREEN (inactive)
2. Run smoke tests on GREEN
3. Switch load balancer to GREEN (atomic)
4. GREEN becomes ACTIVE, BLUE becomes STANDBY
5. If problems: switch back to BLUE (instant rollback)
```

```python
class BlueGreenDeployer:
    """Blue-green deployment orchestrator."""

    def __init__(self, load_balancer, health_checker):
        self.lb = load_balancer
        self.health = health_checker

    async def deploy(self, new_version: str) -> dict:
        active = await self.lb.get_active_environment()
        inactive = "green" if active == "blue" else "blue"

        # Step 1: Deploy to inactive environment
        print(f"Deploying {new_version} to {inactive}")
        await self._deploy_to(inactive, new_version)

        # Step 2: Wait for health checks
        print(f"Waiting for {inactive} to become healthy...")
        healthy = await self._wait_for_healthy(inactive, timeout=300)
        if not healthy:
            return {"success": False, "reason": "Health check failed"}

        # Step 3: Run smoke tests
        print(f"Running smoke tests on {inactive}...")
        smoke_ok = await self._run_smoke_tests(inactive)
        if not smoke_ok:
            return {"success": False, "reason": "Smoke tests failed"}

        # Step 4: Switch traffic
        print(f"Switching traffic to {inactive}")
        await self.lb.switch_to(inactive)

        # Step 5: Verify
        await asyncio.sleep(10)
        post_switch_healthy = await self.health.check(inactive)

        return {
            "success": post_switch_healthy,
            "active": inactive,
            "standby": active,
            "version": new_version,
            "rollback_available": True,
        }

    async def rollback(self):
        """Instant rollback: switch back to standby."""
        active = await self.lb.get_active_environment()
        standby = "green" if active == "blue" else "blue"
        print(f"Rolling back: switching from {active} to {standby}")
        await self.lb.switch_to(standby)
```

### Canary Releases

Gradually shift traffic to new version while monitoring:

```python
import asyncio
from dataclasses import dataclass


@dataclass
class CanaryConfig:
    stages: list[dict]  # [{"percent": 5, "duration_min": 10}, ...]
    error_threshold: float = 0.01  # Max 1% error rate
    latency_threshold_ms: float = 500  # Max p99 latency
    auto_rollback: bool = True


class CanaryDeployer:
    """Progressive canary deployment with automatic rollback."""

    def __init__(self, router, metrics, config: CanaryConfig):
        self.router = router
        self.metrics = metrics
        self.config = config

    async def deploy(self, new_version: str) -> dict:
        # Deploy canary instances
        await self._deploy_canary(new_version)

        for stage in self.config.stages:
            percent = stage["percent"]
            duration = stage["duration_min"]

            print(f"Canary stage: {percent}% traffic for {duration} minutes")
            await self.router.set_canary_weight(percent)

            # Monitor during this stage
            ok = await self._monitor_stage(duration)

            if not ok:
                print(f"Canary failed at {percent}% — rolling back")
                await self.router.set_canary_weight(0)
                await self._teardown_canary()
                return {"success": False, "failed_at_percent": percent}

        # All stages passed — promote canary to production
        print("Canary successful — promoting to 100%")
        await self.router.set_canary_weight(100)
        await self._promote_canary(new_version)

        return {"success": True, "version": new_version}

    async def _monitor_stage(self, duration_min: float) -> bool:
        """Monitor metrics during a canary stage."""
        end_time = asyncio.get_event_loop().time() + duration_min * 60
        check_interval = 30  # Check every 30 seconds

        while asyncio.get_event_loop().time() < end_time:
            await asyncio.sleep(check_interval)

            canary_metrics = await self.metrics.get_canary_metrics()
            baseline_metrics = await self.metrics.get_baseline_metrics()

            # Compare error rates
            if canary_metrics["error_rate"] > self.config.error_threshold:
                print(f"Error rate too high: {canary_metrics['error_rate']:.2%}")
                return False

            # Compare latency
            if canary_metrics["p99_latency_ms"] > self.config.latency_threshold_ms:
                print(f"Latency too high: {canary_metrics['p99_latency_ms']:.0f}ms")
                return False

            # Statistical comparison with baseline
            if canary_metrics["error_rate"] > baseline_metrics["error_rate"] * 2:
                print("Canary error rate 2x higher than baseline")
                return False

        return True


# Canary stages example:
canary_config = CanaryConfig(
    stages=[
        {"percent": 1, "duration_min": 5},    # 1% for 5 min (catch crashes)
        {"percent": 5, "duration_min": 10},   # 5% for 10 min
        {"percent": 25, "duration_min": 15},  # 25% for 15 min
        {"percent": 50, "duration_min": 15},  # 50% for 15 min
        {"percent": 100, "duration_min": 0},  # Full rollout
    ],
    error_threshold=0.005,
    latency_threshold_ms=300,
)
```

### Feature Flags for Progressive Rollout

```python
from dataclasses import dataclass, field
from typing import Any
import hashlib
import json


@dataclass
class FeatureFlag:
    name: str
    enabled: bool = False
    rollout_percentage: float = 0.0  # 0-100
    allowed_users: set = field(default_factory=set)
    allowed_groups: set = field(default_factory=set)
    metadata: dict = field(default_factory=dict)


class FeatureFlagService:
    """Feature flag evaluation with progressive rollout."""

    def __init__(self, store):
        self.store = store  # Redis, config service, etc.

    async def is_enabled(
        self,
        flag_name: str,
        user_id: str = None,
        user_groups: list[str] = None,
        properties: dict = None,
    ) -> bool:
        flag = await self.store.get_flag(flag_name)
        if not flag:
            return False

        # Global kill switch
        if not flag.enabled:
            return False

        # User allowlist (for testing)
        if user_id and user_id in flag.allowed_users:
            return True

        # Group allowlist (e.g., "beta_testers", "employees")
        if user_groups:
            if flag.allowed_groups & set(user_groups):
                return True

        # Percentage rollout (deterministic per user)
        if flag.rollout_percentage > 0 and user_id:
            # Hash user_id + flag_name for consistent bucketing
            hash_input = f"{flag_name}:{user_id}"
            hash_value = int(
                hashlib.md5(hash_input.encode()).hexdigest(), 16
            )
            bucket = hash_value % 100
            return bucket < flag.rollout_percentage

        return flag.rollout_percentage >= 100


# Usage in application code:
flags = FeatureFlagService(flag_store)

async def handle_request(request):
    user = request.user

    if await flags.is_enabled("new_checkout_flow", user.id, user.groups):
        return await new_checkout(request)
    else:
        return await legacy_checkout(request)


# Progressive rollout plan:
# Day 1: Enable for internal employees (allowed_groups: ["employees"])
# Day 2: 5% rollout (rollout_percentage: 5)
# Day 3: 25% rollout
# Day 5: 50% rollout
# Day 7: 100% rollout
# Day 14: Remove flag and old code path
```

**Deployment strategy selection**: (1) **Blue-green** for stateless services where instant rollback is critical, (2) **Canary** for high-traffic services where you need gradual confidence, (3) **Feature flags** for new features that may need quick disable without a deploy, (4) **Rolling update** (Kubernetes default) for routine updates with zero downtime, (5) Always have a tested rollback procedure — the deploy isn't done until you can undo it."""
    ),
    (
        "architecture/schema-evolution-patterns",
        r"""Explain database schema evolution patterns including expand-and-contract migration, backward-compatible changes, online schema changes for zero-downtime deploys, versioned APIs with schema changes, and migration frameworks. Include practical PostgreSQL examples.""",
        r"""## Schema Evolution: Zero-Downtime Migrations and Backward Compatibility

Schema changes are one of the riskiest operations in production systems. A naive `ALTER TABLE` can lock a table for hours, breaking all queries. These patterns enable safe schema evolution.

### The Expand-and-Contract Pattern

The safest approach for any schema change — never a breaking change:

```sql
-- Goal: Rename column "name" to "full_name" in users table
-- WRONG: ALTER TABLE users RENAME COLUMN name TO full_name;
-- This breaks ALL queries referencing "name" instantly

-- PHASE 1: EXPAND — Add new column alongside old
ALTER TABLE users ADD COLUMN full_name TEXT;

-- Backfill existing data (in batches for large tables)
UPDATE users SET full_name = name WHERE full_name IS NULL AND id BETWEEN 1 AND 10000;
UPDATE users SET full_name = name WHERE full_name IS NULL AND id BETWEEN 10001 AND 20000;
-- ... continue in batches

-- Add trigger to keep columns in sync during transition
CREATE OR REPLACE FUNCTION sync_user_name()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.full_name IS NULL AND NEW.name IS NOT NULL THEN
        NEW.full_name := NEW.name;
    ELSIF NEW.name IS NULL AND NEW.full_name IS NOT NULL THEN
        NEW.name := NEW.full_name;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER sync_user_name_trigger
BEFORE INSERT OR UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION sync_user_name();

-- Deploy v2 code: reads from full_name, writes to both
-- Deploy v3 code: reads from full_name, writes only to full_name

-- PHASE 2: CONTRACT — Remove old column (after all code uses new column)
DROP TRIGGER sync_user_name_trigger ON users;
ALTER TABLE users DROP COLUMN name;
```

### Zero-Downtime Migrations in PostgreSQL

```sql
-- SAFE: Adding a nullable column (instant, no lock)
ALTER TABLE orders ADD COLUMN tracking_number TEXT;

-- SAFE: Adding a column with DEFAULT (PG 11+ is instant)
ALTER TABLE orders ADD COLUMN priority INTEGER DEFAULT 0;

-- SAFE: Adding an index CONCURRENTLY (doesn't lock writes)
CREATE INDEX CONCURRENTLY idx_orders_tracking
ON orders (tracking_number)
WHERE tracking_number IS NOT NULL;

-- DANGEROUS: Adding NOT NULL constraint (scans entire table)
-- SAFE alternative: add constraint as NOT VALID, then validate separately
ALTER TABLE orders ADD CONSTRAINT orders_tracking_nn
    CHECK (tracking_number IS NOT NULL) NOT VALID;
-- This returns immediately (only checks new rows)

-- Later, validate existing rows (acquires weaker lock):
ALTER TABLE orders VALIDATE CONSTRAINT orders_tracking_nn;

-- DANGEROUS: Changing column type (rewrites table)
-- SAFE alternative: add new column, backfill, swap
ALTER TABLE orders ADD COLUMN amount_numeric NUMERIC(12,2);
-- Backfill in batches:
UPDATE orders SET amount_numeric = amount::NUMERIC(12,2)
WHERE id BETWEEN 1 AND 10000 AND amount_numeric IS NULL;

-- DANGEROUS: Large table UPDATE (holds row locks)
-- SAFE: Batch updates with pg_sleep for breathing room
DO $$
DECLARE
    batch_size INT := 5000;
    affected INT;
BEGIN
    LOOP
        UPDATE orders
        SET amount_numeric = amount::NUMERIC(12,2)
        WHERE id IN (
            SELECT id FROM orders
            WHERE amount_numeric IS NULL
            LIMIT batch_size
            FOR UPDATE SKIP LOCKED
        );
        GET DIAGNOSTICS affected = ROW_COUNT;
        EXIT WHEN affected = 0;
        PERFORM pg_sleep(0.1);  -- Brief pause
        RAISE NOTICE 'Updated % rows', affected;
    END LOOP;
END $$;
```

### Migration Framework Pattern

```python
from dataclasses import dataclass
from pathlib import Path
import asyncpg
import hashlib
from datetime import datetime


@dataclass
class Migration:
    version: str
    description: str
    up_sql: str
    down_sql: str
    checksum: str = ""

    def __post_init__(self):
        self.checksum = hashlib.md5(self.up_sql.encode()).hexdigest()


class MigrationRunner:
    """Safe database migration runner with locking."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def initialize(self):
        """Create migration tracking table."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    applied_at TIMESTAMPTZ DEFAULT NOW(),
                    execution_time_ms INTEGER
                )
            """)

    async def migrate(self, migrations: list[Migration]):
        """Apply pending migrations with advisory lock."""
        async with self.pool.acquire() as conn:
            # Advisory lock prevents concurrent migrations
            lock_acquired = await conn.fetchval(
                "SELECT pg_try_advisory_lock(42)"
            )
            if not lock_acquired:
                raise RuntimeError("Another migration is in progress")

            try:
                applied = set()
                for row in await conn.fetch(
                    "SELECT version, checksum FROM schema_migrations ORDER BY version"
                ):
                    applied.add(row["version"])
                    # Verify checksum hasn't changed
                    migration = next(
                        (m for m in migrations if m.version == row["version"]), None
                    )
                    if migration and migration.checksum != row["checksum"]:
                        raise RuntimeError(
                            f"Migration {row['version']} has been modified! "
                            f"Expected {row['checksum']}, got {migration.checksum}"
                        )

                pending = [m for m in migrations if m.version not in applied]
                pending.sort(key=lambda m: m.version)

                for migration in pending:
                    print(f"Applying migration {migration.version}: {migration.description}")
                    start = datetime.now()

                    async with conn.transaction():
                        await conn.execute(migration.up_sql)
                        elapsed = (datetime.now() - start).total_seconds() * 1000
                        await conn.execute(
                            """INSERT INTO schema_migrations
                            (version, description, checksum, execution_time_ms)
                            VALUES ($1, $2, $3, $4)""",
                            migration.version, migration.description,
                            migration.checksum, int(elapsed),
                        )

                    print(f"  Applied in {elapsed:.0f}ms")

                print(f"Applied {len(pending)} migration(s)")

            finally:
                await conn.fetchval("SELECT pg_advisory_unlock(42)")

    async def rollback(self, migration: Migration):
        """Rollback a specific migration."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(migration.down_sql)
                await conn.execute(
                    "DELETE FROM schema_migrations WHERE version = $1",
                    migration.version,
                )


# Define migrations
migrations = [
    Migration(
        version="001",
        description="Create users table",
        up_sql="""
            CREATE TABLE users (
                id BIGSERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX idx_users_email ON users (email);
        """,
        down_sql="DROP TABLE IF EXISTS users;",
    ),
    Migration(
        version="002",
        description="Add phone to users (expand phase)",
        up_sql="""
            ALTER TABLE users ADD COLUMN phone TEXT;
            CREATE INDEX CONCURRENTLY idx_users_phone ON users (phone)
            WHERE phone IS NOT NULL;
        """,
        down_sql="""
            DROP INDEX IF EXISTS idx_users_phone;
            ALTER TABLE users DROP COLUMN IF EXISTS phone;
        """,
    ),
]
```

### API Versioning with Schema Changes

```python
# API response versioning alongside schema evolution

class UserSerializer:
    """Serialize user data for different API versions."""

    @staticmethod
    def v1(user: dict) -> dict:
        """API v1: uses 'name' field."""
        return {
            "id": user["id"],
            "name": user.get("full_name") or user.get("name", ""),
            "email": user["email"],
        }

    @staticmethod
    def v2(user: dict) -> dict:
        """API v2: uses 'full_name' field."""
        return {
            "id": user["id"],
            "full_name": user.get("full_name") or user.get("name", ""),
            "email": user["email"],
            "phone": user.get("phone"),
        }


# Route handler with version negotiation
from fastapi import APIRouter, Header

router = APIRouter()

@router.get("/users/{user_id}")
async def get_user(
    user_id: int,
    accept_version: str = Header(default="v2", alias="Accept-Version"),
):
    user = await fetch_user(user_id)

    serializers = {"v1": UserSerializer.v1, "v2": UserSerializer.v2}
    serialize = serializers.get(accept_version, UserSerializer.v2)

    return serialize(user)
```

**Schema evolution rules**: (1) Never make breaking changes in a single deploy — use expand-and-contract, (2) Always use `CREATE INDEX CONCURRENTLY` — regular `CREATE INDEX` locks writes, (3) Add `NOT NULL` constraints as `NOT VALID` first, validate separately, (4) Batch large backfills with `SKIP LOCKED` and pauses, (5) Use advisory locks to prevent concurrent migrations, (6) Keep migration SQL files versioned and checksummed — never modify applied migrations."""
    ),
    (
        "architecture/rate-limiting-patterns",
        r"""Explain rate limiting patterns including token bucket, sliding window, fixed window, leaky bucket algorithms, distributed rate limiting with Redis, per-user vs per-IP vs per-API-key limits, and graceful degradation. Include Python implementations.""",
        r"""## Rate Limiting Patterns: Algorithms, Distributed Implementation, and Graceful Degradation

Rate limiting protects services from abuse and overload. The choice of algorithm affects fairness, burst handling, and implementation complexity.

### Token Bucket Algorithm

Allows bursts up to bucket capacity, then limits to steady rate:

```python
import time
import asyncio
from dataclasses import dataclass


@dataclass
class TokenBucket:
    """In-memory token bucket rate limiter."""

    capacity: int        # Maximum tokens (burst size)
    rate: float          # Tokens added per second
    _tokens: float = 0
    _last_refill: float = 0

    def __post_init__(self):
        self._tokens = float(self.capacity)
        self._last_refill = time.monotonic()

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens. Returns True if allowed."""
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(
            self.capacity,
            self._tokens + elapsed * self.rate,
        )
        self._last_refill = now

    @property
    def remaining(self) -> int:
        self._refill()
        return int(self._tokens)


# Usage:
# Allow 100 requests/minute with bursts up to 20
limiter = TokenBucket(capacity=20, rate=100/60)

for request in requests:
    if limiter.consume():
        process(request)
    else:
        reject_with_429(request)
```

### Distributed Sliding Window (Redis)

```python
import redis
import time
from typing import NamedTuple


class RateLimitResult(NamedTuple):
    allowed: bool
    remaining: int
    reset_at: float
    retry_after: float


class DistributedRateLimiter:
    """Redis-based distributed rate limiter with sliding window."""

    def __init__(self, redis_client: redis.Redis):
        self.r = redis_client

        # Lua script for atomic sliding window check
        self._check_script = self.r.register_script("""
            local key = KEYS[1]
            local window = tonumber(ARGV[1])
            local limit = tonumber(ARGV[2])
            local now = tonumber(ARGV[3])
            local member = ARGV[4]

            -- Remove expired entries
            redis.call('ZREMRANGEBYSCORE', key, 0, now - window)

            -- Count current entries
            local count = redis.call('ZCARD', key)

            if count < limit then
                -- Add new entry
                redis.call('ZADD', key, now, member)
                redis.call('EXPIRE', key, window)
                return {1, limit - count - 1, 0}
            else
                -- Get oldest entry for retry-after calculation
                local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
                local retry_after = 0
                if #oldest > 0 then
                    retry_after = tonumber(oldest[2]) + window - now
                end
                return {0, 0, retry_after}
            end
        """)

    def check(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult:
        """Check if request is within rate limit."""
        now = time.time()
        member = f"{now}:{id(key)}"  # Unique member

        result = self._check_script(
            keys=[f"rl:{key}"],
            args=[window_seconds, limit, now, member],
        )

        allowed = bool(result[0])
        remaining = int(result[1])
        retry_after = float(result[2])

        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            reset_at=now + window_seconds,
            retry_after=max(0, retry_after),
        )


# Multi-tier rate limiting
class TieredRateLimiter:
    """Apply different limits based on client identity."""

    def __init__(self, redis_client: redis.Redis):
        self.limiter = DistributedRateLimiter(redis_client)

        self.tiers = {
            "free": {"per_minute": 20, "per_hour": 500, "per_day": 5000},
            "pro": {"per_minute": 100, "per_hour": 5000, "per_day": 100000},
            "enterprise": {"per_minute": 1000, "per_hour": 50000, "per_day": 1000000},
        }

    def check_all(self, client_id: str, tier: str = "free") -> RateLimitResult:
        """Check all rate limit windows for a client."""
        limits = self.tiers.get(tier, self.tiers["free"])

        # Check each window — fail if ANY limit is exceeded
        checks = [
            self.limiter.check(f"{client_id}:min", limits["per_minute"], 60),
            self.limiter.check(f"{client_id}:hour", limits["per_hour"], 3600),
            self.limiter.check(f"{client_id}:day", limits["per_day"], 86400),
        ]

        for result in checks:
            if not result.allowed:
                return result

        # All windows OK — return the tightest remaining
        return min(checks, key=lambda r: r.remaining)
```

### Rate Limiting Middleware

```python
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse


app = FastAPI()
rate_limiter = TieredRateLimiter(redis.Redis())


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Identify the client
    api_key = request.headers.get("X-API-Key")
    if api_key:
        client_id = f"key:{api_key}"
        tier = await get_tier_for_key(api_key)
    else:
        client_id = f"ip:{request.client.host}"
        tier = "free"

    # Check rate limit
    result = rate_limiter.check_all(client_id, tier)

    if not result.allowed:
        return JSONResponse(
            status_code=429,
            content={
                "error": "rate_limit_exceeded",
                "message": "Too many requests",
                "retry_after": result.retry_after,
            },
            headers={
                "Retry-After": str(int(result.retry_after)),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(result.reset_at)),
            },
        )

    # Process request
    response = await call_next(request)

    # Add rate limit headers to successful responses
    response.headers["X-RateLimit-Remaining"] = str(result.remaining)
    response.headers["X-RateLimit-Reset"] = str(int(result.reset_at))

    return response
```

### Graceful Degradation

```python
class GracefulDegradation:
    """Shed load gracefully instead of hard rejection."""

    def __init__(self, redis_client):
        self.limiter = DistributedRateLimiter(redis_client)

    async def handle_request(self, request, client_id: str):
        result = self.limiter.check_all(client_id)

        if result.allowed:
            # Full service
            return await full_response(request)

        # Check if we can serve a degraded response
        degraded_result = self.limiter.check(
            f"{client_id}:degraded",
            limit=100,
            window_seconds=60,
        )

        if degraded_result.allowed:
            # Serve from cache or simplified response
            return await degraded_response(request)

        # Truly rate limited
        return rate_limited_response(result)


async def degraded_response(request):
    """Return cached or simplified data instead of full computation."""
    cached = await cache.get(request.cache_key)
    if cached:
        return Response(
            content=cached,
            headers={"X-Served-From": "cache", "X-Degraded": "true"},
        )
    return Response(
        content='{"status": "service_busy", "data": null}',
        status_code=200,
        headers={"X-Degraded": "true"},
    )
```

**Rate limiting decisions**: (1) **Token bucket** for APIs that should allow bursts (e.g., batch operations), (2) **Sliding window** for fair, predictable limits (most common for APIs), (3) **Fixed window** is simpler but allows 2x burst at window boundaries, (4) Always return `Retry-After` header with 429 responses, (5) Implement tiered limits — free/pro/enterprise — at the application level, (6) Consider graceful degradation (cached responses) before hard rejection."""
    ),
]
