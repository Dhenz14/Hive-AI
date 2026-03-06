"""Phase 1D: Foundation Thinking — Architecture & Design (Part 2/4)
API design, data consistency, scalability patterns."""

PAIRS = [
    (
        "thinking/arch-rest-api-design-principles",
        "Review this API design for an e-commerce product catalog and identify all the issues:\n\n```\nPOST /api/getProducts              → Get all products\nGET  /api/product/delete/123       → Delete product 123\nPOST /api/createProduct            → Create product\nGET  /api/product?id=123           → Get product by ID\nPOST /api/updateProduct            → Update product (ID in body)\nGET  /api/searchProducts?q=phone   → Search products\nPOST /api/product/123/activate     → Activate product\nPOST /api/product/123/deactivate   → Deactivate product\n```",
        r'''<think>
Multiple REST API design violations:

1. POST for reads (getProducts) — GET is for reads
2. GET for deletes — GET should be safe and idempotent
3. Verbs in URLs (getProducts, createProduct, updateProduct) — REST uses nouns
4. Inconsistent resource naming (product vs products)
5. ID in query param vs path (product?id=123 vs product/123)
6. Missing HTTP methods (not using PUT/PATCH/DELETE)
7. activate/deactivate could be a PATCH on a status field
</think>

## Issues Found

1. **POST for reads** — `POST /getProducts` should be `GET /products`
2. **GET for delete** — `GET /product/delete/123` should be `DELETE /products/123`
3. **Verbs in URLs** — `createProduct`, `updateProduct` → RESTful resources use nouns
4. **Inconsistent naming** — `product` vs `products` (use plural consistently)
5. **ID in query vs path** — `product?id=123` vs `product/123` (use path for resource identity)
6. **Missing HTTP methods** — not using PUT, PATCH, DELETE
7. **Separate activate/deactivate** — could be one PATCH endpoint

## Corrected API

```
GET    /api/products                → List products (with pagination)
GET    /api/products/123            → Get product by ID
POST   /api/products                → Create product
PUT    /api/products/123            → Full update (replace)
PATCH  /api/products/123            → Partial update (e.g., activate/deactivate)
DELETE /api/products/123            → Delete product
GET    /api/products?q=phone        → Search (query parameter on collection)
```

```python
# Activate/deactivate = PATCH the status field
@app.route('/api/products/<int:product_id>', methods=['PATCH'])
def update_product(product_id):
    product = Product.query.get_or_404(product_id)
    data = request.json

    if 'active' in data:
        product.active = data['active']
    if 'price' in data:
        product.price = data['price']

    db.session.commit()
    return jsonify(product.to_dict())
```

**REST principles:** resources are nouns, HTTP methods are verbs, consistent plural naming, IDs in paths.'''
    ),
    (
        "thinking/arch-api-versioning-strategy",
        "Our API has 500+ consumers. We need to make breaking changes to the User resource (renaming fields, changing response structure). What's the best versioning strategy that doesn't break existing clients?",
        r'''<think>
API versioning strategies:
1. URL path: `/api/v1/users`, `/api/v2/users`
2. Query parameter: `/api/users?version=2`
3. Header: `Accept: application/vnd.myapi.v2+json`
4. Content negotiation: `Accept: application/json; version=2`

For 500+ consumers, the Strangler Fig approach is best: introduce v2 alongside v1, gradually migrate consumers, then deprecate v1.

URL path versioning is the most common and easiest for clients to understand/implement.
</think>

## Strategy: URL Versioning + Gradual Migration

```python
# v1 and v2 coexist — no big bang migration
from flask import Blueprint

v1 = Blueprint('v1', __name__, url_prefix='/api/v1')
v2 = Blueprint('v2', __name__, url_prefix='/api/v2')

# v1: original response (keep for existing consumers)
@v1.route('/users/<int:user_id>')
def get_user_v1(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify({
        'id': user.id,
        'first_name': user.first_name,  # Old field name
        'last_name': user.last_name,
        'email_address': user.email,    # Old field name
    })

# v2: new structure (for new and migrated consumers)
@v2.route('/users/<int:user_id>')
def get_user_v2(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify({
        'id': user.id,
        'name': {'first': user.first_name, 'last': user.last_name},
        'email': user.email,
        'created_at': user.created_at.isoformat(),
    })

app.register_blueprint(v1)
app.register_blueprint(v2)
```

## Migration Timeline

```
Month 1: Release v2 alongside v1. Announce deprecation.
Month 2-6: Work with top consumers to migrate to v2.
Month 6: v1 returns Deprecation header:
  Deprecation: true
  Sunset: 2026-12-01
  Link: <https://docs.api.com/migration>; rel="deprecation"
Month 9: v1 returns 301 redirects to v2 equivalent
Month 12: v1 returns 410 Gone
```

**Key principles:**
1. Never break existing consumers without warning
2. Run old and new versions in parallel
3. Communicate timeline clearly (Deprecation + Sunset headers)
4. Monitor v1 usage — know which consumers haven't migrated'''
    ),
    (
        "thinking/arch-eventual-consistency-patterns",
        "Our order service creates an order in its database, then publishes an event for the inventory service to update stock. Sometimes the event is lost and inventory gets out of sync. How do we guarantee consistency?",
        r'''<think>
The problem: the order service needs to (1) write to its DB and (2) publish an event. These are two separate operations — if the app crashes between them, or the message broker loses the event, the systems are inconsistent.

Solutions:
1. **Transactional Outbox** — write the event to a DB table in the same transaction as the order. A separate process reads the outbox and publishes events.
2. **Change Data Capture (CDC)** — use the database's transaction log to detect changes and publish events.
3. **Event Sourcing** — the events ARE the database. No separate publishing needed.

Transactional Outbox is the most practical approach.
</think>

## Transactional Outbox Pattern

The order and its event are written in the **same database transaction**. A separate process publishes events from the outbox table.

```python
# Step 1: Write order + event in ONE transaction
def create_order(order_data):
    order = Order(**order_data)
    event = OutboxEvent(
        aggregate_type='Order',
        aggregate_id=order.id,
        event_type='OrderCreated',
        payload=json.dumps({
            'order_id': order.id,
            'items': order_data['items'],
            'user_id': order_data['user_id'],
        }),
    )

    # SINGLE transaction — both succeed or both fail
    db.session.add(order)
    db.session.add(event)
    db.session.commit()

    return order

# Step 2: Background publisher reads outbox and publishes
async def publish_outbox_events():
    while True:
        events = OutboxEvent.query.filter_by(
            published=False
        ).order_by(OutboxEvent.created_at).limit(100).all()

        for event in events:
            try:
                await message_broker.publish(
                    topic=event.event_type,
                    message=event.payload,
                )
                event.published = True
                event.published_at = datetime.utcnow()
            except Exception as e:
                logger.error(f'Failed to publish event {event.id}: {e}')
                break  # Retry from this event next iteration

        db.session.commit()
        await asyncio.sleep(0.1)  # Poll every 100ms
```

```sql
-- Outbox table
CREATE TABLE outbox_events (
    id BIGSERIAL PRIMARY KEY,
    aggregate_type VARCHAR(100),
    aggregate_id VARCHAR(100),
    event_type VARCHAR(100),
    payload JSONB,
    published BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    published_at TIMESTAMP
);

CREATE INDEX idx_outbox_unpublished ON outbox_events (published, created_at)
WHERE published = FALSE;
```

**Why this works:**
1. Order + event are in the same DB transaction — atomic
2. If the app crashes after commit, the event is in the outbox — it will be published on restart
3. If publishing fails, the event stays in the outbox — retry on next poll
4. Events are published in order (ORDER BY created_at)
5. Consumers must be idempotent (events may be published more than once)'''
    ),
    (
        "thinking/arch-health-check-design",
        "Our Kubernetes liveness probe keeps killing pods that are actually healthy but under temporary load. The current health check:\n\n```python\n@app.route('/health')\ndef health_check():\n    # Check everything\n    db.execute('SELECT 1')  # DB check\n    redis.ping()            # Redis check\n    requests.get(EXTERNAL_API + '/status')  # External service check\n    return jsonify(status='healthy'), 200\n```",
        r'''<think>
The health check tests DB, Redis, AND an external API. If any fails, Kubernetes kills the pod. Problems:

1. External API being slow/down causes the pod to be killed — even though the pod itself is fine
2. Under load, the DB check might be slow (pool exhausted) — pod killed during traffic spike
3. One health endpoint for both liveness and readiness — different purposes!

Kubernetes has different probe types:
- **Liveness**: "Is the process alive?" If no → restart pod. Should only check the process itself.
- **Readiness**: "Can the pod serve traffic?" If no → remove from load balancer. Can check dependencies.
- **Startup**: "Has the app finished starting?" Prevents liveness from killing slow-starting pods.
</think>

**One health endpoint checking everything, used as liveness probe.** External service down → pod killed → all pods killed → total outage.

## Fix: Separate Liveness and Readiness Probes

```python
@app.route('/healthz')
def liveness():
    """Am I alive? Only checks the process itself."""
    return jsonify(status='alive'), 200

@app.route('/readyz')
def readiness():
    """Can I serve traffic? Checks dependencies."""
    checks = {}

    # Check database (with timeout)
    try:
        db.execute('SELECT 1')
        checks['database'] = 'ok'
    except Exception as e:
        checks['database'] = str(e)

    # Check Redis
    try:
        redis.ping()
        checks['redis'] = 'ok'
    except Exception as e:
        checks['redis'] = str(e)

    # DON'T check external services — their outage shouldn't affect YOUR readiness
    all_ok = all(v == 'ok' for v in checks.values())
    status = 200 if all_ok else 503
    return jsonify(status='ready' if all_ok else 'not_ready', checks=checks), status
```

```yaml
# Kubernetes pod spec
livenessProbe:
  httpGet:
    path: /healthz
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 10
  failureThreshold: 3       # Kill after 3 consecutive failures

readinessProbe:
  httpGet:
    path: /readyz
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 5
  failureThreshold: 2       # Remove from LB after 2 failures

startupProbe:
  httpGet:
    path: /healthz
    port: 8000
  failureThreshold: 30      # 30 × 10s = 5 min to start
  periodSeconds: 10
```

**Key rules:**
- **Liveness:** only checks "is my process running" — never dependencies
- **Readiness:** checks "can I serve requests" — database, cache
- **Never check external services** in any probe — their outage shouldn't cascade to you'''
    ),
    (
        "thinking/arch-webhook-delivery-reliability",
        "Our webhook delivery system loses events. When a recipient's server is down, we retry a few times and give up. Design a reliable webhook delivery system.",
        r'''<think>
Reliable webhook delivery needs:
1. Persistent event storage (don't lose events if our system restarts)
2. Exponential backoff retries
3. Delivery tracking and status
4. Dead letter queue for permanently failed deliveries
5. Idempotency (recipients should handle duplicates)
6. Webhook signing (recipients verify authenticity)
</think>

## Reliable Webhook Delivery System

```python
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta

# Retry schedule: 1m, 5m, 30m, 2h, 12h, 24h, 48h
RETRY_DELAYS = [60, 300, 1800, 7200, 43200, 86400, 172800]

class WebhookDelivery:
    def queue_event(self, webhook_url, secret, event_type, payload):
        """Persist event for reliable delivery."""
        event = {
            'id': str(uuid.uuid4()),
            'webhook_url': webhook_url,
            'secret': secret,
            'event_type': event_type,
            'payload': payload,
            'attempts': 0,
            'max_attempts': len(RETRY_DELAYS) + 1,
            'next_attempt_at': datetime.utcnow(),
            'status': 'pending',
        }
        db.execute(
            'INSERT INTO webhook_deliveries (id, url, secret, event_type, '
            'payload, attempts, max_attempts, next_attempt_at, status) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (event['id'], webhook_url, secret, event_type,
             json.dumps(payload), 0, event['max_attempts'],
             event['next_attempt_at'], 'pending')
        )
        db.commit()

    def deliver(self, delivery):
        """Attempt to deliver a webhook."""
        payload_json = json.dumps(delivery['payload'], sort_keys=True)

        # Sign the payload
        signature = hmac.new(
            delivery['secret'].encode(),
            payload_json.encode(),
            hashlib.sha256,
        ).hexdigest()

        headers = {
            'Content-Type': 'application/json',
            'X-Webhook-ID': delivery['id'],
            'X-Webhook-Signature': f'sha256={signature}',
            'X-Webhook-Timestamp': str(int(time.time())),
        }

        try:
            resp = requests.post(
                delivery['url'],
                data=payload_json,
                headers=headers,
                timeout=10,
            )

            if 200 <= resp.status_code < 300:
                self._mark_delivered(delivery['id'])
                return True
            elif resp.status_code >= 400 and resp.status_code < 500:
                # Client error — don't retry (bad URL, auth issue)
                self._mark_failed(delivery['id'], f'Client error: {resp.status_code}')
                return False
            else:
                # Server error — retry
                self._schedule_retry(delivery)
                return False

        except requests.Timeout:
            self._schedule_retry(delivery)
            return False
        except requests.ConnectionError:
            self._schedule_retry(delivery)
            return False

    def _schedule_retry(self, delivery):
        attempts = delivery['attempts'] + 1
        if attempts >= delivery['max_attempts']:
            self._mark_failed(delivery['id'], 'Max retries exceeded')
            return

        delay = RETRY_DELAYS[min(attempts - 1, len(RETRY_DELAYS) - 1)]
        next_at = datetime.utcnow() + timedelta(seconds=delay)

        db.execute(
            'UPDATE webhook_deliveries SET attempts = ?, next_attempt_at = ?, '
            'status = ? WHERE id = ?',
            (attempts, next_at, 'retrying', delivery['id'])
        )
        db.commit()

    # Background worker polls for pending deliveries
    async def worker(self):
        while True:
            deliveries = db.execute(
                'SELECT * FROM webhook_deliveries '
                'WHERE status IN (?, ?) AND next_attempt_at <= ? '
                'ORDER BY next_attempt_at LIMIT 100',
                ('pending', 'retrying', datetime.utcnow())
            ).fetchall()

            for d in deliveries:
                self.deliver(d)

            await asyncio.sleep(5)
```

**Key features:**
1. **Persistent storage** — events survive restarts
2. **Exponential backoff** — 1m, 5m, 30m, 2h, 12h, 24h, 48h
3. **HMAC signature** — recipients verify authenticity
4. **Idempotency ID** — `X-Webhook-ID` lets recipients deduplicate
5. **Smart retry logic** — don't retry 4xx (client errors)
6. **Dead letter** — permanently failed deliveries flagged for investigation'''
    ),
    (
        "thinking/arch-feature-flag-system",
        "We need to release features gradually — canary releases to 1% of users, A/B tests, and kill switches for broken features. Design a feature flag system.",
        r'''<think>
Feature flag requirements:
1. Percentage-based rollout (1%, 10%, 50%, 100%)
2. User targeting (specific users, groups)
3. Kill switch (instant disable)
4. A/B testing (multiple variants)
5. Low latency (checked on every request)
6. Easy management (UI or config file)
</think>

## Feature Flag System

```python
import hashlib
import json
import redis

r = redis.Redis()

class FeatureFlags:
    def __init__(self):
        self._cache = {}  # Local cache for <1ms checks

    def is_enabled(self, flag_name: str, user_id: str = None, default: bool = False) -> bool:
        flag = self._get_flag(flag_name)
        if not flag:
            return default

        # Kill switch — instantly disable
        if not flag.get('enabled', True):
            return False

        # User allowlist — always enabled for specific users
        if user_id and user_id in flag.get('allowed_users', []):
            return True

        # User blocklist — always disabled for specific users
        if user_id and user_id in flag.get('blocked_users', []):
            return False

        # Percentage rollout — deterministic per user
        percentage = flag.get('percentage', 0)
        if percentage >= 100:
            return True
        if percentage <= 0:
            return False

        if user_id:
            # Consistent hash — same user always gets same result
            hash_input = f'{flag_name}:{user_id}'
            hash_val = int(hashlib.md5(hash_input.encode()).hexdigest(), 16) % 100
            return hash_val < percentage

        return default

    def get_variant(self, flag_name: str, user_id: str) -> str:
        """For A/B tests: returns which variant the user is in."""
        flag = self._get_flag(flag_name)
        if not flag or not flag.get('enabled'):
            return 'control'

        variants = flag.get('variants', {'control': 50, 'treatment': 50})
        hash_val = int(hashlib.md5(f'{flag_name}:{user_id}'.encode()).hexdigest(), 16) % 100

        cumulative = 0
        for variant, weight in variants.items():
            cumulative += weight
            if hash_val < cumulative:
                return variant
        return 'control'

    def _get_flag(self, name: str):
        # Check local cache (refreshed every 10 seconds)
        if name in self._cache:
            return self._cache[name]
        raw = r.get(f'feature_flag:{name}')
        if raw:
            flag = json.loads(raw)
            self._cache[name] = flag
            return flag
        return None

flags = FeatureFlags()

# Usage
@app.route('/api/dashboard')
def dashboard():
    user_id = str(current_user.id)

    if flags.is_enabled('new_dashboard', user_id):
        return render_new_dashboard()
    return render_old_dashboard()

# A/B test
@app.route('/api/checkout')
def checkout():
    variant = flags.get_variant('checkout_redesign', str(current_user.id))
    if variant == 'treatment':
        return render_new_checkout()
    return render_old_checkout()
```

**Flag configuration (stored in Redis):**
```json
{
    "enabled": true,
    "percentage": 10,
    "allowed_users": ["user_123", "user_456"],
    "blocked_users": [],
    "variants": {"control": 50, "treatment_a": 25, "treatment_b": 25}
}
```

**Key design decisions:**
- **Consistent hashing** — same user always sees the same variant (no flickering)
- **Local cache** — flag checks are <0.01ms (no Redis call per request)
- **Kill switch** — set `enabled: false` to instantly disable any feature'''
    ),
    (
        "thinking/arch-database-migration-strategy",
        "We need to rename a column from `username` to `display_name` in a table with 50 million rows. The table is accessed by 3 services. A simple `ALTER TABLE RENAME COLUMN` would break services that still use the old name. Design a zero-downtime migration.",
        r'''<think>
Can't rename the column in one shot — services would break. Need a multi-phase approach:

1. Add new column alongside old
2. Dual-write to both columns
3. Backfill old data to new column
4. Migrate services to read from new column
5. Remove old column

This is the "expand-contract" pattern.
</think>

## Expand-Contract Migration (Zero Downtime)

### Phase 1: Expand — Add New Column
```sql
-- Safe: adds column without locking the table (PostgreSQL)
ALTER TABLE users ADD COLUMN display_name VARCHAR(255);

-- Trigger: keeps both columns in sync during migration
CREATE OR REPLACE FUNCTION sync_username_display_name()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.display_name IS NULL AND NEW.username IS NOT NULL THEN
        NEW.display_name = NEW.username;
    END IF;
    IF NEW.username IS NULL AND NEW.display_name IS NOT NULL THEN
        NEW.username = NEW.display_name;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_sync_names
BEFORE INSERT OR UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION sync_username_display_name();
```

### Phase 2: Backfill Existing Data
```sql
-- Batch update to avoid locking entire table
DO $$
DECLARE
    batch_size INT := 10000;
    updated INT;
BEGIN
    LOOP
        UPDATE users
        SET display_name = username
        WHERE display_name IS NULL
        AND id IN (
            SELECT id FROM users WHERE display_name IS NULL LIMIT batch_size
        );
        GET DIAGNOSTICS updated = ROW_COUNT;
        IF updated = 0 THEN EXIT; END IF;
        PERFORM pg_sleep(0.1);  -- Don't overwhelm the DB
    END LOOP;
END $$;
```

### Phase 3: Migrate Services (One at a Time)
```python
# Service code reads from BOTH columns during migration
def get_user_display_name(user):
    return user.display_name or user.username  # Fallback to old column
```

### Phase 4: Contract — Remove Old Column
```sql
-- After ALL services are migrated and verified
DROP TRIGGER trg_sync_names ON users;
DROP FUNCTION sync_username_display_name();
ALTER TABLE users DROP COLUMN username;

-- Add NOT NULL constraint
ALTER TABLE users ALTER COLUMN display_name SET NOT NULL;
```

**Timeline:**
1. Phase 1 (Day 1): Add column + trigger
2. Phase 2 (Day 1-2): Backfill
3. Phase 3 (Week 1-4): Migrate services one by one
4. Phase 4 (Week 5): Drop old column after all services confirmed'''
    ),
    (
        "thinking/arch-bulkhead-pattern",
        "Our API has 10 endpoints. One endpoint (`/api/reports`) runs expensive queries that consume all database connections. When it's overloaded, the other 9 endpoints (including health-critical ones) also fail. Design a bulkhead pattern.",
        r'''<think>
Bulkhead pattern: isolate resources so one failing component doesn't take down everything. Named after ship bulkheads that prevent a leak in one compartment from flooding the whole ship.

For this case: separate connection pools for reports vs other endpoints. Reports can only use their allocated connections, leaving the rest for critical endpoints.
</think>

**One endpoint consumes all resources, starving the rest.** The bulkhead pattern isolates resource pools.

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import threading

# Separate connection pools — reports can't starve other endpoints
critical_engine = create_engine(
    'postgresql://...', pool_size=15, max_overflow=5
)
reports_engine = create_engine(
    'postgresql://...', pool_size=5, max_overflow=2  # Limited!
)

CriticalSession = sessionmaker(bind=critical_engine)
ReportsSession = sessionmaker(bind=reports_engine)

# Thread pool bulkhead — limit concurrent report requests
reports_semaphore = threading.Semaphore(3)  # Max 3 concurrent reports

@app.route('/api/users')
def get_users():
    session = CriticalSession()  # Uses the 15-connection pool
    try:
        return jsonify(session.query(User).all())
    finally:
        session.close()

@app.route('/api/reports')
def generate_report():
    if not reports_semaphore.acquire(timeout=5):
        return jsonify(error='Report generation is busy, try later'), 503

    try:
        session = ReportsSession()  # Uses the 5-connection pool
        try:
            result = session.execute(expensive_report_query).fetchall()
            return jsonify(result)
        finally:
            session.close()
    finally:
        reports_semaphore.release()
```

**Bulkhead isolation:**
- **Critical endpoints:** 15 connections, unaffected by report load
- **Reports endpoint:** 5 connections max, 3 concurrent requests max
- Reports overload → 503 for reports only, other endpoints unaffected

**Applied broadly:**
| Resource | Critical | Reports | Background |
|----------|----------|---------|------------|
| DB connections | 15 | 5 | 3 |
| Thread pool | 20 | 3 | 5 |
| Memory | 2 GB | 500 MB | 500 MB |'''
    ),
    (
        "thinking/arch-graceful-degradation",
        "Our e-commerce site depends on 5 services. When the recommendation service is down, the entire product page returns a 500 error. Design graceful degradation.",
        r'''<think>
Graceful degradation: when a non-critical dependency fails, the system continues working with reduced functionality rather than failing completely.

For a product page: recommendations are nice-to-have, not essential. Product details and pricing are essential. The page should load without recommendations rather than failing entirely.
</think>

**A non-critical service (recommendations) brings down the entire page.** The product page should work without recommendations — show a placeholder instead.

```python
async def get_product_page(product_id):
    # Critical: must succeed or the page can't render
    try:
        product = await product_service.get(product_id)
    except Exception:
        raise  # Product not found → 404 is correct

    try:
        pricing = await pricing_service.get(product_id)
    except Exception:
        raise  # Can't show a product without a price

    # Non-critical: failure is acceptable, degrade gracefully
    recommendations = await _safe_call(
        recommendation_service.get(product_id),
        default=[],
        timeout=2.0,
        label='recommendations',
    )

    reviews = await _safe_call(
        review_service.get(product_id),
        default={'reviews': [], 'average_rating': None},
        timeout=2.0,
        label='reviews',
    )

    recently_viewed = await _safe_call(
        recently_viewed_service.get(current_user.id),
        default=[],
        timeout=1.0,
        label='recently_viewed',
    )

    return {
        'product': product,
        'pricing': pricing,
        'recommendations': recommendations,
        'reviews': reviews,
        'recently_viewed': recently_viewed,
        '_degraded': [],  # List of degraded services for debugging
    }

async def _safe_call(coro, default, timeout, label):
    """Call a service with timeout and fallback."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(f'{label} timed out after {timeout}s')
        return default
    except Exception as e:
        logger.warning(f'{label} failed: {e}')
        return default
```

**Degradation levels:**
| Service | Failure Impact | Degraded Behavior |
|---------|---------------|-------------------|
| Product details | Page can't render | Return 404 |
| Pricing | Can't sell the product | Return error |
| Recommendations | Less engagement | Show "Popular Products" from cache |
| Reviews | Less trust | Show "Reviews loading..." |
| Recently viewed | Minor feature | Hide the section |'''
    ),
    (
        "thinking/arch-data-partitioning-sharding",
        "Our PostgreSQL database has 500 million rows in the orders table. Queries are getting slower, even with proper indexes. Single-server vertical scaling is at its limit (128GB RAM, 32 cores). What's the next step?",
        r'''<think>
Options when a single server can't handle the data:
1. Partitioning (within one server) — split table by range/hash/list
2. Read replicas — for read scaling (doesn't help write scaling)
3. Sharding (across servers) — split data across multiple DB servers
4. Archive old data — reduce active dataset

For 500M rows: first try partitioning (native PostgreSQL feature, least operational complexity), then sharding if needed.
</think>

## Step 1: Table Partitioning (Least Disruptive)

```sql
-- Partition by date range — most orders queries filter by date
CREATE TABLE orders (
    id BIGSERIAL,
    user_id BIGINT,
    total NUMERIC,
    created_at TIMESTAMP,
    status VARCHAR(20)
) PARTITION BY RANGE (created_at);

-- One partition per month
CREATE TABLE orders_2025_01 PARTITION OF orders
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
CREATE TABLE orders_2025_02 PARTITION OF orders
    FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');
-- ... auto-generate future partitions

-- Queries with date filters only scan relevant partitions
SELECT * FROM orders
WHERE created_at >= '2026-02-01' AND created_at < '2026-03-01'
-- Only scans orders_2026_02 partition (~15M rows instead of 500M)
```

## Step 2: Archive Old Data

```sql
-- Move orders older than 2 years to archive
CREATE TABLE orders_archive (LIKE orders INCLUDING ALL);

INSERT INTO orders_archive
SELECT * FROM orders WHERE created_at < NOW() - INTERVAL '2 years';

-- Drop old partitions
DROP TABLE orders_2023_01;
-- Active dataset: ~200M rows instead of 500M
```

## Step 3: Sharding (If Still Not Enough)

```python
# Application-level sharding by user_id
SHARD_COUNT = 4

def get_shard(user_id: int) -> str:
    shard_id = user_id % SHARD_COUNT
    return f'postgresql://orders-shard-{shard_id}:5432/orders'

engines = {
    i: create_engine(f'postgresql://orders-shard-{i}:5432/orders')
    for i in range(SHARD_COUNT)
}

def get_user_orders(user_id):
    shard = user_id % SHARD_COUNT
    engine = engines[shard]
    with engine.connect() as conn:
        return conn.execute(
            'SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC',
            (user_id,)
        ).fetchall()
```

**Decision tree:**
1. **Partition first** (native, zero application changes) → handles most cases
2. **Archive old data** (reduces active dataset 50-80%)
3. **Read replicas** (for read scaling)
4. **Shard** only when write throughput exceeds single-server capacity'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
