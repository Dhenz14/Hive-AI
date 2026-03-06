"""Phase 3B: Metacognition — Reasoning Quality Evaluation (Part 3)
Scenarios: Authentication, monitoring, concurrency, code organization
"""

PAIRS = [
    (
        "thinking/meta-reasoning-session-vs-jwt",
        r'''Compare these two authentication approaches for a web application:

Session-based:
```python
# Login
@app.post("/login")
def login(credentials):
    user = authenticate(credentials)
    session["user_id"] = user.id
    return {"message": "Logged in"}

# Auth check
@app.get("/api/profile")
def profile():
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "Not authenticated"}, 401
    return get_user(user_id)

# Logout
@app.post("/logout")
def logout():
    session.clear()
    return {"message": "Logged out"}
```

JWT-based:
```python
# Login
@app.post("/login")
def login(credentials):
    user = authenticate(credentials)
    token = jwt.encode({"user_id": user.id, "exp": datetime.utcnow() + timedelta(hours=1)},
                       SECRET, algorithm="HS256")
    return {"token": token}

# Auth check
@app.get("/api/profile")
def profile():
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    try:
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return {"error": "Not authenticated"}, 401
    return get_user(payload["user_id"])
```

Which is better for a standard web app?''',
        r'''<think>
Let me evaluate both for a standard web application (server-rendered or SPA with one backend).

**Session-based:**
Pros:
- Server-side control: can invalidate sessions instantly (logout, ban user)
- Simple: session middleware handles cookie management
- Secure by default: HttpOnly cookies, SameSite, can't be accessed by JS
- Small cookies: session ID is a random string (~32 bytes)

Cons:
- Server state: sessions stored on server (memory, Redis, or database)
- Horizontal scaling: need shared session store (Redis) for multiple servers
- CSRF vulnerability: cookies sent automatically, need CSRF tokens
- Not suitable for mobile/API-only (no cookie support in some contexts)

**JWT-based:**
Pros:
- Stateless: no server-side session storage needed
- Scales easily: any server can verify the token
- Cross-domain: can be used with multiple services/APIs
- Works with mobile apps and SPAs

Cons:
- Can't invalidate: once issued, token is valid until expiration. Logout doesn't really work (token still valid). User banned? Token still valid.
- Token size: JWTs are large (~500 bytes for a typical payload vs 32-byte session ID)
- Stored in JS: must store in localStorage (XSS risk) or httpOnly cookie (then you need CSRF protection anyway, negating the "stateless" benefit)
- Key management: SECRET rotation requires invalidating all tokens
- Refresh token complexity: short-lived access + long-lived refresh tokens add complexity

**For a standard web app specifically:**
- Users log in and out regularly → need real logout (session)
- Account compromise requires instant session invalidation (session)
- One backend serves the frontend → no need for cross-service auth (session)
- CSRF is manageable with SameSite cookies (session)

**The JWT trap:**
People choose JWT for "statelessness" but then realize they need:
- A token blacklist (for logout/ban) → now you have server state anyway
- Refresh tokens → now you have TWO tokens to manage
- CSRF protection if tokens are in cookies → same problem as sessions

**Winner for standard web app:** Session-based. JWT is better for distributed systems, microservices, and API-only backends serving mobile clients.
</think>

**For a standard web app, session-based auth is better — simpler, more secure, and provides features (real logout, instant invalidation) that JWT requires workarounds for.**

### Evaluation

| Axis | Sessions | JWT |
|------|----------|-----|
| Logout | Instant (delete session) | Impossible (token valid until expiry) |
| Ban user | Instant (delete session) | Must maintain blacklist (server state!) |
| Cookie size | ~32 bytes | ~500+ bytes (every request!) |
| Server state | Yes (Redis/DB) | "None" (until you need blacklist) |
| XSS exposure | HttpOnly cookie (safe) | localStorage (vulnerable) |
| Cross-service auth | Requires shared store | ✓ Any service can verify |
| Mobile API | Possible but awkward | ✓ Natural fit |
| CSRF risk | Yes (mitigated by SameSite) | Only if stored in cookie |
| Key rotation | Session IDs are random | Must invalidate ALL tokens |

### The JWT trap
```
Step 1: "We'll use JWT for stateless auth!"
Step 2: "Wait, we need real logout." → Add token blacklist
Step 3: "Blacklist must be checked every request." → Server-side state (Redis)
Step 4: "We need refresh tokens for security." → Now managing 2 tokens
Step 5: "We're basically reimplementing sessions, but worse."
```

### When JWT IS the right choice
| Scenario | Session | JWT |
|----------|---------|-----|
| Traditional web app | ✓ | Overkill |
| SPA + single API | ✓ (HttpOnly cookie) | Works too |
| Mobile app + API | Awkward | ✓ |
| Microservices (inter-service) | ✗ | ✓ |
| Third-party API access | ✗ | ✓ (or OAuth) |
| Single sign-on (SSO) | Possible | ✓ |

### The reasoning pattern
Authentication strategy should match architecture. Single-server web apps don't benefit from JWT's statelessness but pay its costs (no real logout, token management, XSS risk). Distributed systems and API-serving-mobile architectures benefit from JWT's portability. Don't choose JWT because it's "modern" — choose it when you actually need cross-service token verification.'''
    ),
    (
        "thinking/meta-reasoning-two-monitoring-approaches",
        r'''Compare these two approaches for monitoring a production web application:

Approach A (logs-based):
```python
import logging

logger = logging.getLogger(__name__)

@app.route("/api/orders", methods=["POST"])
def create_order(data):
    logger.info(f"Creating order for user {data['user_id']}")
    start = time.time()

    try:
        order = OrderService.create(data)
        duration = time.time() - start
        logger.info(f"Order {order.id} created in {duration:.2f}s")
        return {"order_id": order.id}
    except Exception as e:
        logger.error(f"Order creation failed: {e}", exc_info=True)
        raise
```

Approach B (metrics + structured logging):
```python
from prometheus_client import Counter, Histogram
import structlog

logger = structlog.get_logger()

order_created = Counter('orders_created_total', 'Total orders', ['status'])
order_duration = Histogram('order_creation_seconds', 'Order creation time')

@app.route("/api/orders", methods=["POST"])
def create_order(data):
    with order_duration.time():
        try:
            order = OrderService.create(data)
            order_created.labels(status='success').inc()
            logger.info("order_created", order_id=order.id, user_id=data['user_id'])
            return {"order_id": order.id}
        except Exception as e:
            order_created.labels(status='error').inc()
            logger.error("order_creation_failed", error=str(e), user_id=data['user_id'])
            raise
```

Which provides better observability?''',
        r'''<think>
Let me evaluate both approaches.

**Approach A (logs-based):**
- Uses standard Python logging
- Free-text log messages (human-readable but hard to query)
- Manual timing with `time.time()`
- Error logging with traceback

Problems:
- Free-text logs are hard to search/aggregate ("how many orders failed today?" requires regex parsing)
- No metrics for dashboards or alerting
- Manual timing is error-prone (might miss error paths)
- Log format varies by developer (inconsistent)
- No percentile latency tracking (only individual request times)

**Approach B (metrics + structured logging):**
- Prometheus metrics: counters and histograms
- Structured logging (key-value pairs, JSON-serializable)
- Automatic timing with histogram context manager
- Consistent log format

Benefits:
- Prometheus Counter: "How many orders were created/failed?" → instant dashboard
- Histogram: p50, p95, p99 latency without any aggregation code
- Structured logs: easily searchable in ELK/Loki (`user_id=12345`)
- Alerting: "alert if order_creation_error_rate > 1% in 5 minutes"

**For production monitoring:**
The key question is: "When something goes wrong at 3 AM, which approach helps the on-call engineer faster?"

Approach A: Engineer greps through gigabytes of logs. "How many errors in the last hour?" → `grep "failed" app.log | wc -l`. Approximate and slow.

Approach B: Engineer opens Grafana dashboard. Sees error rate spike at 2:47 AM. Clicks through to see affected user_ids in structured logs. Has the answer in 30 seconds.

**Winner:** Approach B. The combination of metrics (for dashboards and alerting) + structured logging (for investigation) is the industry standard for production observability.
</think>

**Approach B is significantly better — metrics enable dashboards and alerting, structured logs enable efficient investigation.**

### Evaluation

| Axis | Logs-based (A) | Metrics + Structured (B) |
|------|---------------|-------------------------|
| "How many errors today?" | grep + count (slow, approximate) | Prometheus query (instant, exact) |
| p99 latency | Not available | Histogram provides percentiles |
| Alerting | Regex-based log alerts (brittle) | Metric thresholds (reliable) |
| Dashboard | Not possible without parsing | Native Grafana integration |
| Investigation | Free-text grep | Key-value search (user_id=123) |
| Consistency | Varies by developer | Enforced by structlog |
| Setup cost | Zero (stdlib) | Medium (Prometheus + Grafana) |

### The 3 AM test
```
Approach A at 3 AM:
$ grep "failed" /var/log/app.log | tail -100
# Hundreds of lines of unstructured text
# "Is this normal? How many is too many?"
# No historical baseline to compare against

Approach B at 3 AM:
→ Open Grafana
→ Error rate graph: spike from 0.1% to 15% at 2:47 AM
→ Click "affected requests" → structured logs with user_ids, error types
→ Root cause identified in 2 minutes
```

### The three pillars of observability
```
1. Metrics (Prometheus/Datadog) → WHAT is happening?
   "Error rate is 15%, p99 latency is 2s"

2. Logs (structured) → WHY is it happening?
   {"event": "order_failed", "user_id": 123, "error": "inventory_unavailable"}

3. Traces (Jaeger/Zipkin) → WHERE in the system?
   "Request spent 1.8s in inventory service, 0.1s in payment service"
```

### When simple logging IS enough
- Development and debugging
- Small internal tools with < 100 users
- Scripts and batch jobs (not long-running services)
- Prototypes and MVPs

### The reasoning pattern
Monitoring strategy should answer two questions: "Is something wrong?" (metrics + alerting) and "What went wrong?" (structured logs + traces). Free-text logging only partially answers the second question and can't answer the first at all. As a system grows, the observability gap between approaches A and B widens dramatically.'''
    ),
    (
        "thinking/meta-reasoning-two-concurrency-models",
        r'''I need to process 10,000 image files: read each file, resize it, and save the result. Compare:

Approach A (multiprocessing):
```python
from multiprocessing import Pool
from PIL import Image

def resize_image(path):
    img = Image.open(path)
    img = img.resize((800, 600))
    output = path.replace('/originals/', '/resized/')
    img.save(output)
    return output

with Pool(processes=8) as pool:
    results = pool.map(resize_image, image_paths)
```

Approach B (asyncio):
```python
import asyncio
import aiofiles
from PIL import Image

async def resize_image(path):
    async with aiofiles.open(path, 'rb') as f:
        data = await f.read()
    img = Image.open(io.BytesIO(data))
    img = img.resize((800, 600))
    output = path.replace('/originals/', '/resized/')
    buf = io.BytesIO()
    img.save(buf, format='JPEG')
    async with aiofiles.open(output, 'wb') as f:
        await f.write(buf.getvalue())
    return output

async def main():
    tasks = [resize_image(p) for p in image_paths]
    results = await asyncio.gather(*tasks)
```

Which is better for image processing?''',
        r'''<think>
Image resizing is CPU-BOUND work. The PIL/Pillow resize operation involves pixel computation — it's not waiting for I/O, it's crunching numbers.

**Approach A (multiprocessing):**
- Creates 8 OS processes, each with its own Python interpreter and GIL
- Each process can use one CPU core fully
- On an 8-core machine: 8 images resized truly in parallel
- Overhead: process creation, memory duplication, IPC for results
- Perfect fit: CPU-bound work bypasses the GIL

**Approach B (asyncio):**
- Single thread, single process
- aiofiles makes FILE I/O async (non-blocking reads/writes)
- BUT: `Image.open()` and `img.resize()` are synchronous CPU operations
- The resize computation BLOCKS the event loop!
- While one image is being resized, no other task can run
- Effectively SEQUENTIAL for the CPU-bound part

The asyncio version gains nothing from async for the resize step. The file I/O is async, but reading a file from local disk is already fast (buffered by OS). The bottleneck is CPU computation (resize), which asyncio can't parallelize because it's single-threaded.

Actually, `Image.open(io.BytesIO(data))` and `img.resize()` are synchronous Pillow operations. They block the event loop for the duration of the computation. `asyncio.gather` would schedule all tasks, but they'd run one at a time for the CPU-bound parts.

**Winner:** Approach A (multiprocessing). Image resizing is CPU-bound, and multiprocessing is the right tool for CPU-bound parallelism in Python.

**If it were network-bound** (downloading images from URLs), asyncio would be better. The concurrency model must match the bottleneck type.
</think>

**Multiprocessing (A) is dramatically better — image resizing is CPU-bound work, which asyncio can't parallelize.**

### Evaluation

| Axis | Multiprocessing (A) | Asyncio (B) |
|------|-------------------|-------------|
| CPU utilization | 8 cores used | 1 core used |
| True parallelism | Yes (8 processes) | No (single thread) |
| Resize throughput | 8× sequential | ~1× sequential (!) |
| Memory per worker | ~50MB (process overhead) | ~1KB (coroutine) |
| GIL bypass | Yes | No |
| I/O efficiency | Standard file I/O | Async file I/O (minor benefit) |

### Why asyncio fails here
```python
async def resize_image(path):
    async with aiofiles.open(path, 'rb') as f:
        data = await f.read()        # async I/O (fast, ~1ms)

    img = Image.open(io.BytesIO(data))
    img = img.resize((800, 600))     # BLOCKS event loop! (~50ms CPU work)
    img.save(buf, format='JPEG')     # BLOCKS event loop! (~30ms CPU work)

    async with aiofiles.open(output, 'wb') as f:
        await f.write(buf.getvalue()) # async I/O (fast, ~1ms)
```

The resize and save are synchronous CPU operations. `asyncio.gather` can't interleave them — each task blocks the event loop during computation. 10,000 tasks execute essentially sequentially.

### Performance comparison (10,000 images, 8-core machine)
```
Sequential:     10,000 × 80ms = 800 seconds
Asyncio:        10,000 × 80ms = ~800 seconds (still sequential!)
Multiprocessing: 10,000 × 80ms / 8 = 100 seconds
```

### The decision matrix
| Bottleneck | Best tool | Example |
|------------|-----------|---------|
| CPU computation | multiprocessing | Image resize, video encoding, ML inference |
| Network I/O | asyncio/threading | API calls, web scraping, downloads |
| Disk I/O | threading | File processing (if I/O-bound) |
| Mixed CPU + I/O | multiprocessing + asyncio per process | Download then process images |

### The reasoning pattern
Always identify the bottleneck type FIRST, then choose the concurrency model. asyncio is for I/O-bound work (waiting for network/disk). multiprocessing is for CPU-bound work (computation). Using asyncio for CPU-bound work gives the complexity of async code with the performance of sequential code — the worst of both worlds.'''
    ),
    (
        "thinking/meta-reasoning-two-code-organizations",
        r'''Compare these two code organization patterns for a web API:

Pattern A (layered / horizontal):
```
src/
├── controllers/
│   ├── user_controller.py
│   ├── order_controller.py
│   └── product_controller.py
├── services/
│   ├── user_service.py
│   ├── order_service.py
│   └── product_service.py
├── models/
│   ├── user.py
│   ├── order.py
│   └── product.py
├── repositories/
│   ├── user_repository.py
│   ├── order_repository.py
│   └── product_repository.py
└── schemas/
    ├── user_schema.py
    ├── order_schema.py
    └── product_schema.py
```

Pattern B (feature / vertical):
```
src/
├── users/
│   ├── controller.py
│   ├── service.py
│   ├── model.py
│   ├── repository.py
│   └── schema.py
├── orders/
│   ├── controller.py
│   ├── service.py
│   ├── model.py
│   ├── repository.py
│   └── schema.py
└── products/
    ├── controller.py
    ├── service.py
    ├── model.py
    ├── repository.py
    └── schema.py
```

Which organization pattern is better?''',
        r'''<think>
Let me evaluate both on practical criteria.

**Pattern A (layered / horizontal):**
"I want to change how we handle users" → Edit files across 5 directories:
- controllers/user_controller.py
- services/user_service.py
- models/user.py
- repositories/user_repository.py
- schemas/user_schema.py

"I want to see all controllers" → Open one directory: controllers/

Pros:
- Easy to see all controllers/services/models at a glance
- Clear separation of concerns by layer
- Familiar to developers from MVC background
- Easy to enforce layer boundaries (controllers can't import repositories)

Cons:
- Feature changes touch many directories (high "coupling scatter")
- Hard to reason about a feature end-to-end (files spread everywhere)
- Hard to delete a feature (must find files in 5 directories)
- Cross-feature dependencies are hard to track

**Pattern B (feature / vertical):**
"I want to change how we handle users" → Edit files in ONE directory: users/

"I want to see all controllers" → Must check multiple directories.

Pros:
- Feature changes are localized (one directory)
- Easy to reason about a feature end-to-end
- Easy to delete a feature (delete one directory)
- Low coupling scatter
- Scales better with team size (team per feature module)

Cons:
- Harder to enforce layer boundaries within modules
- Cross-feature operations might create circular imports
- Repetitive file names (every module has controller.py, service.py)
- Less familiar to some developers

**For a growing web API:**
The key question is: what changes more often — layers or features? Features change much more often. You add a new field to users, fix a bug in orders, add a new feature to products. These changes are vertical (touch controller, service, model for ONE feature).

You almost never change "all controllers" or "all repositories" at once. Layer-wide changes are rare.

**Winner:** Pattern B (feature/vertical) for most web APIs. It aligns directory structure with change patterns, making development more efficient. Pattern A is fine for very small apps where the overhead is minimal.

BUT: shared concerns (auth middleware, database connection, error handling) should still be in a common `shared/` or `core/` directory.
</think>

**Pattern B (feature/vertical) is better for most web APIs — it aligns code organization with how features actually change.**

### Evaluation

| Axis | Layered (A) | Feature (B) |
|------|------------|-------------|
| "Change user feature" | Edit 5 directories | Edit 1 directory |
| "Delete user feature" | Find files in 5 dirs | Delete 1 directory |
| "See all of users" | Navigate 5 directories | Open 1 directory |
| "See all controllers" | Open 1 directory | Check N directories |
| Scale with features | More files per directory | More directories |
| Scale with team | Merge conflicts in shared dirs | Teams own feature dirs |
| Coupling visibility | Hard to see feature deps | Clear feature boundaries |

### The change pattern argument
```
Typical week of changes:
Monday:    "Add phone field to users" → users/ only
Tuesday:   "Fix order total calculation" → orders/ only
Wednesday: "Add product search" → products/ only
Thursday:  "User can save favorite products" → users/ + products/
Friday:    "Fix auth middleware" → shared/

Pattern B: 4/5 changes touch ONE directory
Pattern A: 4/5 changes touch 3-5 directories each
```

### Best of both: feature modules with shared core
```
src/
├── core/                  # shared infrastructure
│   ├── database.py
│   ├── auth.py
│   ├── middleware.py
│   └── exceptions.py
├── users/                 # feature module
│   ├── routes.py          # controller/endpoints
│   ├── service.py         # business logic
│   ├── models.py          # database models
│   └── schemas.py         # API schemas
├── orders/
│   ├── routes.py
│   ├── service.py
│   ├── models.py
│   └── schemas.py
└── products/
    └── ...
```

### When layered (A) IS better
- Very small apps (< 3 features) where the overhead is negligible
- Libraries/frameworks where the layer IS the organizing concept
- When enforcing strict layer boundaries is critical (e.g., hexagonal architecture)

### The reasoning pattern
Organize code by what changes together, not by what looks similar. If features change independently and frequently, group by feature. If layers change independently (rare in web apps), group by layer. The goal of code organization is to minimize the number of directories you touch for the most common changes.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
