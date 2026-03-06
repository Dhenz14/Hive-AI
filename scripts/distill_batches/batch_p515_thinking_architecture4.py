"""Phase 1D: Foundation Thinking — Architecture & Design (Part 4/4)
Distributed systems, consistency, observability, infrastructure patterns."""

PAIRS = [
    (
        "thinking/arch-distributed-locking",
        "Two instances of our background worker process the same job simultaneously, causing duplicate charges. The job system:\n\n```python\ndef process_pending_jobs():\n    jobs = db.execute(\n        \"SELECT * FROM jobs WHERE status = 'pending' LIMIT 10\"\n    ).fetchall()\n    \n    for job in jobs:\n        process_job(job)  # Both workers grab the same jobs!\n        db.execute(\n            \"UPDATE jobs SET status = 'completed' WHERE id = ?\",\n            (job['id'],)\n        )\n```\n\nTwo workers both SELECT the same pending jobs and process them in parallel.",
        r'''<think>
TOCTOU race between SELECT and UPDATE. Both workers see the same pending jobs. Need distributed locking or atomic claim.

Options:
1. SELECT ... FOR UPDATE SKIP LOCKED (PostgreSQL) — atomically claim jobs
2. Redis distributed lock — Redlock algorithm
3. UPDATE with atomic claim
</think>

## Fix: Atomic Job Claiming with `FOR UPDATE SKIP LOCKED`

```python
def process_pending_jobs():
    with db.begin():  # Transaction
        # Atomically claim jobs — SKIP LOCKED means other workers
        # skip rows already locked by this worker
        jobs = db.execute(
            "SELECT * FROM jobs WHERE status = 'pending' "
            "ORDER BY created_at "
            "LIMIT 10 "
            "FOR UPDATE SKIP LOCKED"
        ).fetchall()

        if not jobs:
            return

        job_ids = [j['id'] for j in jobs]
        db.execute(
            "UPDATE jobs SET status = 'processing', worker_id = ?, "
            "started_at = NOW() WHERE id = ANY(?)",
            (WORKER_ID, job_ids)
        )

    # Process outside the transaction (don't hold locks during work)
    for job in jobs:
        try:
            process_job(job)
            db.execute(
                "UPDATE jobs SET status = 'completed', completed_at = NOW() WHERE id = ?",
                (job['id'],)
            )
        except Exception as e:
            db.execute(
                "UPDATE jobs SET status = 'failed', error = ? WHERE id = ?",
                (str(e), job['id'])
            )
        db.commit()
```

**`FOR UPDATE SKIP LOCKED`** is the PostgreSQL secret weapon for job queues:
- `FOR UPDATE` — locks selected rows (other transactions can't grab them)
- `SKIP LOCKED` — if a row is already locked, skip it instead of waiting
- Result: each worker gets a unique set of jobs with zero contention'''
    ),
    (
        "thinking/arch-distributed-tracing",
        "Requests to our API sometimes take 10 seconds but we can't figure out which of our 8 microservices is slow. Each service has its own logs but there's no way to trace a request across services.",
        r'''<think>
Need distributed tracing — propagate a trace ID through all services so you can see the entire request flow and timing.
</think>

## Distributed Tracing Implementation

```python
# Middleware that propagates trace context
import uuid
import time
import logging
from flask import request, g

logger = logging.getLogger(__name__)

@app.before_request
def start_trace():
    # Propagate trace ID from upstream, or create new one
    g.trace_id = request.headers.get('X-Trace-ID', str(uuid.uuid4()))
    g.span_id = str(uuid.uuid4())[:8]
    g.parent_span = request.headers.get('X-Span-ID')
    g.start_time = time.perf_counter()

@app.after_request
def end_trace(response):
    duration = (time.perf_counter() - g.start_time) * 1000

    # Structured log with trace context
    logger.info(
        'request completed',
        extra={
            'trace_id': g.trace_id,
            'span_id': g.span_id,
            'parent_span': g.parent_span,
            'method': request.method,
            'path': request.path,
            'status': response.status_code,
            'duration_ms': round(duration, 2),
            'service': 'order-service',
        }
    )

    response.headers['X-Trace-ID'] = g.trace_id
    return response

# When calling other services, propagate trace context
def call_service(url, **kwargs):
    headers = kwargs.pop('headers', {})
    headers['X-Trace-ID'] = g.trace_id
    headers['X-Span-ID'] = g.span_id
    return requests.get(url, headers=headers, **kwargs)
```

**With OpenTelemetry (production-grade):**
```python
from opentelemetry import trace
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Auto-instrument Flask and requests
FlaskInstrumentor().instrument_app(app)
RequestsInstrumentor().instrument()

# Export traces to Jaeger/Tempo
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint="http://tempo:4317"))
)
```

**Now you can see:** `GET /api/orders` → 10s total → Order Service (50ms) → Payment Service (200ms) → **Inventory Service (9.5s)** ← bottleneck found!'''
    ),
    (
        "thinking/arch-structured-logging",
        "Our logs are unstructured text, making it impossible to query or aggregate:\n\n```\n2026-03-05 10:30:15 INFO User 123 placed order 456 for $99.99\n2026-03-05 10:30:16 ERROR Failed to process payment for order 456: timeout\n2026-03-05 10:30:17 INFO Retrying payment for order 456\n```\n\nDesign a structured logging system that supports querying like 'show all errors for order 456' or 'average response time per endpoint'.",
        r'''<think>
Structured logging: emit logs as key-value pairs (JSON) instead of free-form text. This enables querying, filtering, and aggregation.
</think>

## Structured Logging with `structlog`

```python
import structlog
import time

# Configure structlog
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.JSONRenderer(),  # Output as JSON
    ],
)

logger = structlog.get_logger()

# Usage — pass context as key-value pairs
@app.route('/api/orders', methods=['POST'])
def create_order():
    start = time.perf_counter()
    data = request.json

    log = logger.bind(
        user_id=current_user.id,
        endpoint='/api/orders',
        method='POST',
    )

    order = Order(user_id=current_user.id, total=data['total'])
    db.session.add(order)
    db.session.commit()

    log.info('order_created', order_id=order.id, total=data['total'])

    try:
        payment = process_payment(order)
        log.info('payment_processed', order_id=order.id, payment_id=payment.id)
    except PaymentError as e:
        log.error('payment_failed', order_id=order.id, error=str(e))
        raise

    duration = time.perf_counter() - start
    log.info('request_completed', duration_ms=round(duration * 1000, 2))
    return jsonify(order.to_dict())
```

**Output (JSON — machine-parseable):**
```json
{"event": "order_created", "user_id": 123, "order_id": 456, "total": 99.99, "level": "info", "timestamp": "2026-03-05T10:30:15Z"}
{"event": "payment_failed", "user_id": 123, "order_id": 456, "error": "timeout", "level": "error", "timestamp": "2026-03-05T10:30:16Z"}
```

**Now you can query:**
```
# Loki/Elasticsearch queries:
{level="error"} | json | order_id=456
{event="request_completed"} | json | avg(duration_ms) by (endpoint)
{user_id="123"} | json | event="payment_failed"
```'''
    ),
    (
        "thinking/arch-blue-green-deployment",
        "Our deployments cause 30 seconds of downtime. During deployment, the old version is stopped before the new version is ready:\n\n```bash\n# Current deployment process\nsystemctl stop myapp\ncp -r /deploy/new/* /opt/myapp/\nsystemctl start myapp\n# 30 seconds of downtime while new version starts up\n```\n\nDesign a zero-downtime deployment strategy.",
        r'''<think>
Blue-green deployment: run two identical environments. Blue is live, green is staging. Deploy to green, test it, then switch traffic.
</think>

## Blue-Green Deployment

```nginx
# nginx config — traffic routing
upstream blue {
    server 127.0.0.1:8001;
}

upstream green {
    server 127.0.0.1:8002;
}

# Symlink determines which is active
# /etc/nginx/conf.d/active.conf → blue.conf or green.conf

server {
    listen 80;
    location / {
        proxy_pass http://active;  # Points to blue or green
    }
}
```

```bash
#!/bin/bash
# deploy.sh — zero-downtime deployment

CURRENT=$(readlink /etc/nginx/conf.d/active.conf)
if [[ "$CURRENT" == *"blue"* ]]; then
    NEW_ENV="green"
    NEW_PORT=8002
else
    NEW_ENV="blue"
    NEW_PORT=8001
fi

echo "Deploying to $NEW_ENV (port $NEW_PORT)"

# 1. Deploy new version to inactive environment
cp -r /deploy/new/* /opt/myapp-$NEW_ENV/

# 2. Start new version
systemctl start myapp-$NEW_ENV

# 3. Wait for health check
for i in $(seq 1 30); do
    if curl -sf http://localhost:$NEW_PORT/healthz > /dev/null; then
        echo "Health check passed"
        break
    fi
    sleep 1
done

# 4. Switch traffic (atomic — nginx reload is graceful)
ln -sf /etc/nginx/conf.d/$NEW_ENV.conf /etc/nginx/conf.d/active.conf
nginx -s reload

echo "Traffic switched to $NEW_ENV"

# 5. Stop old version after drain period
sleep 10  # Allow in-flight requests to complete
systemctl stop myapp-$([[ "$NEW_ENV" == "blue" ]] && echo "green" || echo "blue")

echo "Deployment complete — zero downtime"
```

**Timeline:**
1. New version starts on inactive port (no impact on live traffic)
2. Health check confirms new version is ready
3. nginx reload switches traffic atomically (in-flight requests complete on old version)
4. Old version stops after drain period

**Rollback:** switch the symlink back and reload nginx — instant rollback.'''
    ),
    (
        "thinking/arch-secrets-rotation",
        "Our database passwords and API keys never change. If one is compromised, an attacker has indefinite access. Design a secret rotation strategy.",
        r'''<think>
Secret rotation: periodically change credentials so compromised secrets have limited lifetime.

Key challenges:
1. Rotating without downtime (both old and new credentials must work briefly)
2. Distributing new secrets to all services
3. Automating the process (manual rotation is error-prone)
</think>

## Automated Secret Rotation

```python
# Secret rotation manager
import boto3
import json
from datetime import datetime

class SecretRotator:
    def __init__(self):
        self.sm = boto3.client('secretsmanager')

    def rotate_db_password(self, secret_id):
        """Dual-password rotation for zero-downtime."""

        # Step 1: Create new password
        new_password = secrets.token_urlsafe(32)

        # Step 2: Add new password to database (BOTH passwords work)
        db_admin.execute(f"ALTER USER app_user SET PASSWORD '{new_password}'")

        # Step 3: Update secret in Secrets Manager
        self.sm.put_secret_value(
            SecretId=secret_id,
            SecretString=json.dumps({
                'password': new_password,
                'rotated_at': datetime.utcnow().isoformat(),
            }),
        )

        # Step 4: Services pick up new secret on next connection
        # (connection pools reconnect using new password)

        # Step 5: After all services have rotated, disable old password
        # (handled by the next rotation cycle)

    def rotate_api_key(self, service_name):
        """Dual-key rotation for API keys."""

        # Generate new key
        new_key = secrets.token_urlsafe(32)

        # Store both old and new (both valid during transition)
        current = self.sm.get_secret_value(SecretId=f'{service_name}/api-key')
        old_key = json.loads(current['SecretString'])['key']

        self.sm.put_secret_value(
            SecretId=f'{service_name}/api-key',
            SecretString=json.dumps({
                'key': new_key,
                'previous_key': old_key,  # Still valid during transition
                'rotated_at': datetime.utcnow().isoformat(),
            }),
        )

        return new_key
```

```python
# Application reads secrets dynamically (not hardcoded)
class DynamicConfig:
    def __init__(self, secret_id, refresh_interval=300):
        self.secret_id = secret_id
        self.refresh_interval = refresh_interval
        self._cache = None
        self._last_refresh = 0

    @property
    def value(self):
        if time.time() - self._last_refresh > self.refresh_interval:
            self._cache = sm.get_secret_value(SecretId=self.secret_id)
            self._last_refresh = time.time()
        return json.loads(self._cache['SecretString'])

db_config = DynamicConfig('myapp/db-password')

# Connection pool uses current password, auto-reconnects on rotation
def get_db_url():
    password = db_config.value['password']
    return f'postgresql://app:{password}@db.internal/myapp'
```

**Rotation schedule:**
| Secret Type | Rotation Period | Method |
|-------------|----------------|--------|
| DB passwords | 30 days | Dual-password |
| API keys | 90 days | Dual-key |
| JWT signing keys | 7 days | Key ID + rotation |
| TLS certificates | 60 days | Auto (Let's Encrypt) |'''
    ),
    (
        "thinking/arch-load-balancing-strategies",
        "Our load balancer uses round-robin, but some backend instances are slower than others. Fast instances finish quickly and sit idle while slow instances queue up requests. What load balancing strategy should we use?",
        r'''<think>
Round-robin doesn't account for backend capacity or current load. A slow instance gets the same number of requests as a fast one.

Better strategies:
1. Least connections — route to the instance with fewest active connections
2. Weighted round-robin — give faster instances more weight
3. Power of two choices — pick 2 random instances, choose the one with fewer connections
</think>

**Round-robin creates uneven load when backends have different capacity or response times.**

## Comparison of Strategies

| Strategy | How It Works | Best For |
|----------|-------------|----------|
| Round-robin | Equal distribution | Identical instances, uniform requests |
| Least connections | Route to least busy | Mixed response times |
| Weighted | Proportional to capacity | Different instance sizes |
| Least response time | Route to fastest responder | Latency-sensitive |

## Implementation: Least Connections

```nginx
# nginx — least_conn
upstream backend {
    least_conn;
    server backend-1:8000;
    server backend-2:8000;
    server backend-3:8000;
}
```

```python
# Custom load balancer (Python example)
import random
from collections import defaultdict

class LoadBalancer:
    def __init__(self, backends):
        self.backends = backends
        self.active_connections = defaultdict(int)

    def get_backend_least_conn(self):
        """Route to instance with fewest active connections."""
        return min(self.backends, key=lambda b: self.active_connections[b])

    def get_backend_p2c(self):
        """Power of two choices — O(1) with near-optimal distribution."""
        a, b = random.sample(self.backends, 2)
        return a if self.active_connections[a] <= self.active_connections[b] else b

    def track_request(self, backend):
        self.active_connections[backend] += 1

    def complete_request(self, backend):
        self.active_connections[backend] -= 1
```

**Recommendation:** Use **least connections** for most workloads. It naturally adapts to different instance speeds — fast instances complete requests quickly, freeing up connections, and receive more new requests as a result.'''
    ),
    (
        "thinking/arch-api-pagination-design",
        "Design a pagination API that handles the case where items are added or removed between page requests. With offset-based pagination, insertions cause items to be skipped or duplicated.",
        r'''<think>
Offset pagination breaks with concurrent mutations:
- Insert on page 1 → all subsequent items shift → user sees a duplicate on page 2
- Delete on page 1 → items shift up → user misses an item on page 2

Cursor-based pagination is stable because it uses the last seen item as a reference point.
</think>

## Cursor-Based Pagination (Stable Under Mutations)

```python
import base64
import json

@app.route('/api/products')
def list_products():
    limit = min(int(request.args.get('limit', 20)), 100)
    cursor = request.args.get('cursor')

    query = Product.query.order_by(Product.created_at.desc(), Product.id.desc())

    if cursor:
        # Decode cursor to get position
        cursor_data = json.loads(base64.b64decode(cursor))
        query = query.filter(
            db.or_(
                Product.created_at < cursor_data['created_at'],
                db.and_(
                    Product.created_at == cursor_data['created_at'],
                    Product.id < cursor_data['id'],
                ),
            )
        )

    products = query.limit(limit + 1).all()  # Fetch one extra to check for next page
    has_next = len(products) > limit
    products = products[:limit]

    # Build next cursor from last item
    next_cursor = None
    if has_next and products:
        last = products[-1]
        cursor_data = {'created_at': last.created_at.isoformat(), 'id': last.id}
        next_cursor = base64.b64encode(json.dumps(cursor_data).encode()).decode()

    return jsonify({
        'data': [p.to_dict() for p in products],
        'pagination': {
            'next_cursor': next_cursor,
            'has_next': has_next,
        },
    })
```

**Response:**
```json
{
    "data": [...20 products...],
    "pagination": {
        "next_cursor": "eyJjcmVhdGVkX2F0IjoiMjAyNi0wMy0wNVQxMDowMCIsImlkIjogNDV9",
        "has_next": true
    }
}
```

**Why this is stable:**
- **Insertions:** new items before the cursor don't affect subsequent pages (cursor points to a specific item, not an offset)
- **Deletions:** items removed before the cursor are already past — no shifting
- **Opaque cursor:** clients treat it as a token, can't manipulate it
- **Composite cursor** (timestamp + id): handles identical timestamps correctly'''
    ),
    (
        "thinking/arch-sidecar-pattern",
        "Every microservice needs logging, metrics, and service discovery. Each team implements these differently, causing inconsistency. Some services are in Python, some in Go, some in Node.js. How do we standardize cross-cutting concerns without requiring every team to use the same language or library?",
        r'''<think>
The sidecar pattern: run a separate process alongside each service that handles cross-cutting concerns. The service communicates with the sidecar over localhost.

Benefits:
- Language-agnostic (sidecar is the same regardless of service language)
- Consistent implementation across all services
- Services don't need to include logging/metrics/discovery libraries
</think>

## Sidecar Pattern

Deploy a standardized sidecar container alongside every service. The sidecar handles cross-cutting concerns, and the service communicates with it over localhost.

```yaml
# Kubernetes pod with sidecar
apiVersion: v1
kind: Pod
spec:
  containers:
    # Main application (any language)
    - name: app
      image: order-service:v1
      ports:
        - containerPort: 8000

    # Sidecar: handles logging, metrics, service discovery
    - name: sidecar
      image: platform-sidecar:v2
      ports:
        - containerPort: 9090  # Metrics
        - containerPort: 9091  # Admin
      env:
        - name: SERVICE_NAME
          value: order-service
        - name: LOG_FORMAT
          value: json
```

```python
# Application code — simple HTTP to localhost sidecar
# Works the same in Python, Go, Node.js, Java

import requests

# Structured logging via sidecar
def log(level, message, **context):
    requests.post('http://localhost:9091/log', json={
        'level': level,
        'message': message,
        **context,
    })

# Metrics via sidecar
def track_metric(name, value, tags=None):
    requests.post('http://localhost:9091/metrics', json={
        'name': name,
        'value': value,
        'tags': tags or {},
    })

# Service discovery via sidecar
def discover_service(name):
    resp = requests.get(f'http://localhost:9091/discover/{name}')
    return resp.json()['url']
```

**Standardized across all languages:**
| Concern | Without Sidecar | With Sidecar |
|---------|----------------|-------------|
| Logging | Different libs per language | HTTP POST to localhost |
| Metrics | Prometheus client per language | HTTP POST to localhost |
| Discovery | Custom per team | HTTP GET to localhost |
| mTLS | TLS in every app | Sidecar handles TLS |

The sidecar is maintained by the platform team. Application teams just make HTTP calls to localhost.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
