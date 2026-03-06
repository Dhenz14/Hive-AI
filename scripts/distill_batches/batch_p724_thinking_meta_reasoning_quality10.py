"""Phase 3B: Metacognition — Reasoning Quality Evaluation (Part 10)"""

PAIRS = [
    (
        "thinking/meta-reasoning-redis-pub-sub-vs-rabbitmq",
        r'''I need a message queue for my Python microservices. Should I use Redis Pub/Sub or RabbitMQ? Here are my two approaches:

Approach A — Redis Pub/Sub:
```python
import redis

r = redis.Redis()

# Publisher
def publish_event(channel, message):
    r.publish(channel, json.dumps(message))

# Subscriber
def subscribe(channel, callback):
    pubsub = r.pubsub()
    pubsub.subscribe(channel)
    for message in pubsub.listen():
        if message['type'] == 'message':
            callback(json.loads(message['data']))
```

Approach B — RabbitMQ with pika:
```python
import pika

connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
channel = connection.channel()
channel.queue_declare(queue='tasks', durable=True)

# Publisher
def publish_event(queue, message):
    channel.basic_publish(
        exchange='',
        routing_key=queue,
        body=json.dumps(message),
        properties=pika.BasicProperties(delivery_mode=2)
    )

# Consumer
def consume(queue, callback):
    channel.basic_consume(queue=queue, on_message_callback=callback)
    channel.start_consuming()
```

Which should I choose?''',
        r'''<think>
Let me evaluate both message queue approaches for Python microservices.

Approach A — Redis Pub/Sub:
- Fire-and-forget: if no subscriber is listening, the message is LOST
- No persistence, no acknowledgment, no retry
- Very fast, very simple
- No message routing beyond channel names
- Already have Redis? Zero additional infrastructure

Approach B — RabbitMQ:
- Messages are persisted (durable=True, delivery_mode=2)
- Has acknowledgments — failed consumers don't lose messages
- Supports complex routing (exchanges, bindings, dead letter queues)
- Additional infrastructure to manage
- More complex but handles failure scenarios

Multi-axis evaluation:

Reliability: RabbitMQ wins decisively. Redis Pub/Sub silently drops messages if no subscriber is active. For microservices that process orders, payments, or any important events, this is a dealbreaker.

Performance: Redis Pub/Sub is faster for high-throughput low-importance messages (like real-time metrics). RabbitMQ adds overhead for persistence and acking.

Complexity: Redis is simpler — fewer concepts, no exchanges/bindings. RabbitMQ has a steeper learning curve but that complexity maps to real needs.

Operational: Redis Pub/Sub needs no extra infra if you already use Redis. RabbitMQ means another service to deploy, monitor, and maintain.

Scalability: RabbitMQ supports competing consumers (multiple workers on one queue). Redis Pub/Sub broadcasts to ALL subscribers — no load balancing.

The critical factor: microservices implies business-critical messages between services. Losing messages silently is unacceptable in production.

Winner: RabbitMQ for microservices communication.
BUT: Redis Pub/Sub is perfect for real-time notifications, cache invalidation, or metrics where occasional loss is acceptable.
</think>

**RabbitMQ is the right choice for microservice communication.** The deciding factor is reliability.

**Why Redis Pub/Sub is dangerous for microservices:**
- Messages are **lost** if no subscriber is listening at publish time
- No acknowledgments — if a consumer crashes mid-processing, the message vanishes
- No retry, no dead letter queue, no persistence
- Broadcasts to all subscribers instead of load-balancing across workers

**Why RabbitMQ fits:**
- Durable queues + persistent messages survive broker restarts
- Consumer acknowledgments ensure at-least-once delivery
- Competing consumers allow horizontal scaling of workers
- Dead letter queues catch poison messages
- Complex routing when you need topic/fanout exchanges

**Use Redis Pub/Sub for:**
- Real-time dashboards, live notifications
- Cache invalidation signals
- Ephemeral events where loss is acceptable
- When you already have Redis and need simple broadcast

**Comparison:**

| Axis | Redis Pub/Sub | RabbitMQ |
|------|--------------|----------|
| Reliability | Fire-and-forget | At-least-once delivery |
| Performance | ~100K msg/s | ~20K msg/s |
| Persistence | None | Yes (durable) |
| Load balancing | Broadcast only | Competing consumers |
| Complexity | Minimal | Moderate |
| Extra infra | None if using Redis | Separate service |

For critical microservice events: **RabbitMQ**. For real-time ephemeral signals: **Redis Pub/Sub**.'''
    ),
    (
        "thinking/meta-reasoning-flat-files-vs-db-config",
        r'''For storing application configuration that changes at runtime (feature flags, rate limits, UI toggles), should I use flat files (JSON/YAML) or a database table?

Approach A — JSON config file:
```python
import json
from pathlib import Path
from watchdog.observers import Observer

CONFIG_PATH = Path("config/features.json")

def load_config():
    return json.loads(CONFIG_PATH.read_text())

def update_config(key, value):
    config = load_config()
    config[key] = value
    CONFIG_PATH.write_text(json.dumps(config, indent=2))

# File watcher reloads on change
class ConfigHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path == str(CONFIG_PATH):
            app.config.update(load_config())
```

Approach B — Database table:
```python
from sqlalchemy import Column, String, Text, DateTime
from datetime import datetime

class ConfigEntry(Base):
    __tablename__ = 'config'
    key = Column(String(255), primary_key=True)
    value = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow)

def get_config(key, default=None):
    entry = session.query(ConfigEntry).get(key)
    return json.loads(entry.value) if entry else default

def set_config(key, value):
    entry = session.merge(ConfigEntry(
        key=key, value=json.dumps(value), updated_at=datetime.utcnow()
    ))
    session.commit()
```

Which is better for runtime config?''',
        r'''<think>
Evaluating flat files vs database for runtime configuration...

Approach A — JSON config file:
- Simple, human-readable, easy to version control
- File watcher pattern works for single-server setups
- BUT: write conflicts if multiple processes update simultaneously
- File watchers can miss changes (race conditions, network drives)
- Multi-server: need to sync files across instances (NFS? rsync?)
- No audit trail of who changed what when

Approach B — Database table:
- Natural multi-server consistency — all instances read same DB
- Audit trail with updated_at (could add updated_by)
- Atomic updates via transactions
- But adds DB dependency for config reads (latency, availability)
- Need caching layer to avoid hitting DB on every request
- Harder to version control or review changes

Multi-axis evaluation:

Multi-server: Database wins easily. Files require distributed filesystem or sync mechanism. Database is naturally centralized.

Simplicity: Files win for single-server. JSON is readable, editable, no schema needed.

Consistency: Database wins. No race conditions on concurrent writes. No stale file watcher issues.

Performance: Files win for reads (filesystem cache), but database with in-memory cache is comparable. Both need caching for hot-path config reads.

Auditability: Database wins with timestamps and potential audit log. Files need git commits for history.

Operational safety: Files win — you can git revert a bad config change. Database needs a rollback mechanism you build yourself.

The critical factor: "runtime configuration that changes at runtime" + most production setups are multi-server. The moment you have >1 instance, files become a headache.

Winner: Database for production runtime config.
BUT: for single-server or developer-facing config, flat files are simpler and more appropriate.
</think>

**Database is better for runtime configuration** in any multi-instance production setup.

**Why flat files break down:**
- **Concurrent writes**: Two processes updating the JSON simultaneously = data loss
- **Multi-server sync**: Need NFS, rsync, or custom sync — all fragile
- **File watcher reliability**: `watchdog` can miss rapid changes or have race conditions
- **No atomicity**: Partial writes create corrupted JSON

**Why database fits runtime config:**
- All instances read the same source of truth
- Atomic updates via transactions
- Built-in timestamps for audit trail
- Easy to add admin UI, API endpoints, access control
- Natural caching with TTL (read from DB every 30s, cache in memory)

**Recommended pattern** — database with local cache:

```python
import time

_cache = {}
_cache_ttl = 30  # seconds

def get_config(key, default=None):
    now = time.time()
    if key in _cache and now - _cache[key][1] < _cache_ttl:
        return _cache[key][0]
    entry = session.query(ConfigEntry).get(key)
    value = json.loads(entry.value) if entry else default
    _cache[key] = (value, now)
    return value
```

**Use flat files when:**
- Single server, simple deployment
- Config rarely changes at runtime
- You want git-versioned config (deploy-time, not runtime)
- Developer tooling or local development

| Axis | Flat Files | Database |
|------|-----------|----------|
| Multi-server | Painful | Natural |
| Concurrent writes | Unsafe | Atomic |
| Auditability | Via git | Via timestamps |
| Simplicity | Simpler | Needs schema + cache |
| Rollback | git revert | Build it yourself |'''
    ),
    (
        "thinking/meta-reasoning-dataclass-vs-pydantic",
        r'''For my Python API models, should I use dataclasses or Pydantic?

Approach A — dataclasses:
```python
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

@dataclass
class User:
    name: str
    email: str
    age: int
    created_at: datetime = field(default_factory=datetime.utcnow)
    bio: Optional[str] = None

    def __post_init__(self):
        if not isinstance(self.name, str):
            raise TypeError("name must be str")
        if self.age < 0 or self.age > 150:
            raise ValueError("invalid age")
```

Approach B — Pydantic:
```python
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

class User(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    age: int = Field(ge=0, le=150)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    bio: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
```

Which should I use for API models?''',
        r'''<think>
Comparing dataclasses vs Pydantic for API models specifically...

Approach A — dataclasses:
- Standard library, no dependency
- No automatic type coercion — you get what you pass in
- Validation requires manual __post_init__ code
- No JSON serialization built in (need custom encoder)
- No schema generation
- Fast instantiation (no validation overhead)

Approach B — Pydantic:
- Automatic validation on instantiation
- Type coercion (string "42" → int 42)
- JSON serialization/deserialization built in
- OpenAPI/JSON Schema generation
- EmailStr validates email format automatically
- Field constraints (min_length, ge, le) declarative
- from_attributes=True allows ORM model → Pydantic conversion

Multi-axis evaluation:

Validation: Pydantic wins massively. Dataclass validation requires manual code for every field. Pydantic is declarative and comprehensive.

API integration: Pydantic wins — it's what FastAPI, Django Ninja, and most modern Python API frameworks expect. JSON schema generation is automatic.

Performance: Dataclasses are faster for instantiation (no validation). But for API models, you WANT validation, so comparing unvalidated dataclass to validated Pydantic is apples to oranges. Adding equivalent validation to dataclasses makes them slower.

Dependencies: Dataclasses win — stdlib, zero dependencies. Pydantic is an external dependency (though very stable and widely used).

Serialization: Pydantic has model_dump(), model_dump_json(). Dataclasses need dataclasses.asdict() + custom JSON encoder for datetime, etc.

Type safety: Pydantic's coercion can be surprising (silently converting types). Dataclasses preserve exact types. For internal data structures, this strictness is good. For API input, coercion is usually what you want.

The critical factor: "API models" — this means parsing untrusted input, serializing responses, generating documentation. Pydantic was literally designed for this.

Winner: Pydantic for API models.
BUT: dataclasses are better for internal data structures where you want simplicity, no dependencies, and no magic coercion.
</think>

**Pydantic is the clear choice for API models.** It was purpose-built for this exact use case.

**Why Pydantic wins for APIs:**
- **Declarative validation**: `Field(ge=0, le=150)` vs manual `__post_init__` checks
- **Email validation**: `EmailStr` validates format. Dataclass needs regex or library
- **JSON serialization**: `model.model_dump_json()` handles datetime, enums, nested models
- **Schema generation**: Auto-generates OpenAPI/JSON Schema for docs
- **Framework integration**: FastAPI, Django Ninja, LiteStar all use Pydantic natively
- **ORM compatibility**: `from_attributes=True` converts SQLAlchemy models directly

**Why dataclasses are wrong here:**
```python
# Dataclass silently accepts bad data:
user = User(name=123, email="not-an-email", age=-5)
# No error until your __post_init__ catches it (if you wrote checks)

# Pydantic catches everything immediately:
user = User(name=123, email="not-an-email", age=-5)
# ValidationError with detailed messages for each field
```

**Use dataclasses when:**
- Internal data structures (not API boundaries)
- No validation needed (trusted internal data)
- Zero-dependency requirement
- Simple DTOs between your own modules
- Performance-critical paths that instantiate millions of objects

| Axis | dataclasses | Pydantic |
|------|------------|----------|
| Validation | Manual | Automatic + declarative |
| JSON support | DIY | Built-in |
| API schema | None | OpenAPI generation |
| Dependencies | stdlib | External (stable) |
| Type coercion | None | Automatic |
| Raw speed | Faster (no validation) | Slower (validates) |

**Rule of thumb**: Pydantic at system boundaries (APIs, config, external data), dataclasses for internal models.'''
    ),
    (
        "thinking/meta-reasoning-thread-pool-vs-asyncio",
        r'''I need to make 500 HTTP requests to different APIs concurrently in Python. Compare these two approaches:

Approach A — ThreadPoolExecutor:
```python
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

def fetch(url):
    response = requests.get(url, timeout=10)
    return response.json()

def fetch_all(urls):
    results = []
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = {executor.submit(fetch, url): url for url in urls}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                print(f"Failed {futures[future]}: {e}")
    return results
```

Approach B — asyncio with aiohttp:
```python
import asyncio
import aiohttp

async def fetch(session, url):
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
        return await response.json()

async def fetch_all(urls):
    async with aiohttp.ClientSession() as session:
        tasks = [fetch(session, url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in results if not isinstance(r, Exception)]
```

Which is better for 500 concurrent HTTP requests?''',
        r'''<think>
Comparing thread pool vs asyncio for 500 concurrent HTTP requests...

Approach A — ThreadPoolExecutor:
- Uses OS threads — each thread has ~8MB stack
- 50 workers × 8MB = ~400MB memory overhead
- Thread scheduling overhead from OS context switching
- Simple to understand — synchronous code in each thread
- requests library is battle-tested, well-documented
- max_workers=50 means only 50 concurrent at a time (others queue)
- GIL doesn't matter here — threads release GIL during I/O

Approach B — asyncio + aiohttp:
- Single thread, event loop — minimal memory overhead
- 500 coroutines use negligible memory vs 500 threads
- All 500 requests fire concurrently (no worker pool limit)
- aiohttp reuses connections via session
- BUT: no backpressure — 500 simultaneous connections might overwhelm targets
- Need semaphore for rate limiting
- async/await infects the entire call chain

Multi-axis evaluation:

Memory: asyncio wins decisively. 500 coroutines ≈ a few MB. 500 threads (if you raised max_workers) ≈ 4GB.

Throughput: asyncio wins. Thread pool with 50 workers processes in batches of 50. asyncio fires all 500 (or uses semaphore for controlled concurrency).

Simplicity: Thread pool wins. Synchronous code in each thread, no async/await coloring, works with any library. asyncio requires async-compatible libraries (aiohttp not requests).

Error handling: Thread pool is slightly easier — standard try/except. asyncio's gather with return_exceptions requires filtering results.

Scalability: asyncio wins at scale. Going from 500 to 5000 requests is trivial with asyncio but thread pool hits OS limits.

Ecosystem: requests has richer middleware, auth handlers, retry adapters. aiohttp is good but less mature ecosystem.

Pitfall in approach B: no concurrency limit. 500 simultaneous connections may trigger rate limits or exhaust file descriptors. Should add:
```python
sem = asyncio.Semaphore(50)
async def fetch(session, url):
    async with sem:
        ...
```

The critical factor: 500 HTTP requests is I/O-bound work. asyncio is specifically designed for this. The memory and throughput advantages compound as request count grows.

Winner: asyncio for 500+ concurrent HTTP requests.
BUT: thread pool is fine for <100 requests or when you need synchronous library compatibility.
</think>

**asyncio + aiohttp is better for 500 concurrent HTTP requests.** This is exactly what async I/O was designed for.

**Why asyncio wins here:**
- **Memory**: 500 coroutines ≈ few MB vs 500 threads ≈ 4GB
- **Throughput**: True concurrency for all 500 (vs batches of 50 with thread pool)
- **Connection reuse**: Single `ClientSession` efficiently pools connections
- **Scalability**: 500 → 5000 → 50000 with minimal resource increase

**Critical fix needed for Approach B** — add a semaphore:

```python
async def fetch_all(urls):
    sem = asyncio.Semaphore(50)  # Limit concurrent connections

    async def bounded_fetch(session, url):
        async with sem:
            return await fetch(session, url)

    async with aiohttp.ClientSession() as session:
        tasks = [bounded_fetch(session, url) for url in urls]
        return await asyncio.gather(*tasks, return_exceptions=True)
```

Without the semaphore, 500 simultaneous connections may exhaust file descriptors or trigger rate limits.

**When ThreadPoolExecutor is better:**
- <100 requests (overhead doesn't matter)
- Need synchronous libraries (requests, specific auth middleware)
- Existing synchronous codebase you can't convert to async
- Quick script where simplicity > performance

| Axis | ThreadPoolExecutor | asyncio + aiohttp |
|------|-------------------|-------------------|
| Memory (500 req) | ~400MB | ~5MB |
| Max concurrency | Limited by workers | Limited by semaphore |
| Library ecosystem | requests (rich) | aiohttp (good) |
| Code complexity | Simpler | async/await coloring |
| Scalability | OS thread limits | Thousands of coroutines |
| Error handling | try/except | return_exceptions pattern |

**Bottom line**: For I/O-bound bulk HTTP work, asyncio is the right tool. Use thread pool for compatibility with sync code or small-scale work.'''
    ),
    (
        "thinking/meta-reasoning-composition-vs-inheritance",
        r'''For sharing behavior between Python classes, compare inheritance vs composition:

Approach A — Inheritance:
```python
class BaseRepository:
    def __init__(self, db):
        self.db = db

    def find_by_id(self, id):
        return self.db.query(self.model).filter_by(id=id).first()

    def find_all(self):
        return self.db.query(self.model).all()

    def save(self, entity):
        self.db.add(entity)
        self.db.commit()
        return entity

class UserRepository(BaseRepository):
    model = User

    def find_by_email(self, email):
        return self.db.query(User).filter_by(email=email).first()

class OrderRepository(BaseRepository):
    model = Order

    def find_by_user(self, user_id):
        return self.db.query(Order).filter_by(user_id=user_id).all()
```

Approach B — Composition:
```python
class QueryExecutor:
    def __init__(self, db, model):
        self.db = db
        self.model = model

    def find_by_id(self, id):
        return self.db.query(self.model).filter_by(id=id).first()

    def find_all(self):
        return self.db.query(self.model).all()

    def save(self, entity):
        self.db.add(entity)
        self.db.commit()
        return entity

class UserRepository:
    def __init__(self, db):
        self.query = QueryExecutor(db, User)

    def find_by_id(self, id):
        return self.query.find_by_id(id)

    def find_by_email(self, email):
        return self.query.db.query(User).filter_by(email=email).first()

class OrderRepository:
    def __init__(self, db):
        self.query = QueryExecutor(db, Order)

    def find_by_user(self, user_id):
        return self.query.db.query(Order).filter_by(user_id=user_id).all()
```

Which pattern is better for repository classes?''',
        r'''<think>
Comparing inheritance vs composition for repository classes...

Approach A — Inheritance:
- Less boilerplate — UserRepository automatically has find_by_id, find_all, save
- Clear "is-a" relationship: UserRepository IS a repository
- Simple, obvious, widely understood pattern
- BUT: fragile base class problem (changing BaseRepository affects all children)
- Single inheritance chain — can't mix in different behaviors easily
- model attribute is implicit class variable (somewhat magic)

Approach B — Composition:
- Explicit delegation — every method call is visible
- BUT: lots of boilerplate wrapping (find_by_id just delegates)
- `self.query.db.query(User)` is leaking internal structure (Law of Demeter violation)
- More flexible in theory — can swap QueryExecutor implementations
- BUT: in practice, how often do you swap the query executor?

Multi-axis evaluation:

Boilerplate: Inheritance wins. No wrapper methods needed. Subclasses just add their specific methods.

Flexibility: Composition wins in theory — can compose different behaviors. But for repositories, this flexibility is rarely needed.

Readability: Inheritance wins. UserRepository(BaseRepository) immediately communicates intent. The composition version requires reading through delegation methods.

Encapsulation: Composition wins in principle, but the implementation shown breaks it — `self.query.db.query(User)` reaches through two objects.

Testability: Roughly equal. Both can mock the db. Composition makes it slightly easier to mock QueryExecutor independently.

Coupling: Inheritance couples more tightly to BaseRepository. But for repositories that are genuinely the same pattern, this coupling is appropriate.

Maintainability: For THIS specific case (repositories with shared CRUD), inheritance is cleaner. The entities ARE repositories. The behavior IS the same pattern.

Hmm, is this one of those cases where the "favor composition" dogma misleads? For repository patterns, inheritance is the standard approach across frameworks (Spring Data, Django's generic views, SQLAlchemy mixins). The "is-a" relationship genuinely holds.

The critical factor: repositories are a textbook example where inheritance works well. The base class is stable, the relationship is genuine, and composition adds boilerplate without real benefit.

Winner: Inheritance for this repository pattern.
BUT: if you need to mix multiple independent behaviors (caching + auditing + soft-delete), composition/mixins are better than deep inheritance chains.
</think>

**Inheritance is better for this repository pattern.** This is one of the cases where "favor composition over inheritance" doesn't apply.

**Why inheritance works here:**
- Repositories genuinely ARE the same thing with model-specific extensions
- Base class is stable — CRUD operations rarely change
- Zero boilerplate: subclasses automatically get find_by_id, find_all, save
- Pattern is universally understood (Spring Data, Django generics, etc.)

**Why the composition version is worse:**
```python
# Boilerplate delegation that adds nothing:
def find_by_id(self, id):
    return self.query.find_by_id(id)  # Just forwarding

# Law of Demeter violation:
self.query.db.query(User)  # Reaching through two objects
```

**When to favor composition instead:**
- **Multiple independent behaviors**: Need caching + auditing + soft-delete? Don't build a 4-level inheritance chain
- **Behavior varies independently**: If CRUD logic and caching logic change for different reasons
- **Diamond problem**: Multiple inheritance paths conflict

**Better composition for mixed behaviors:**
```python
class UserRepository:
    def __init__(self, db):
        self.crud = CrudMixin(db, User)
        self.cache = CacheMixin(ttl=300)
        self.audit = AuditMixin(db)

    def find_by_id(self, id):
        return self.cache.get_or(
            f"user:{id}", lambda: self.crud.find_by_id(id)
        )
```

**The rule of thumb:**

| Use | When |
|-----|------|
| Inheritance | Genuine "is-a", stable base, single behavior axis |
| Composition | Multiple independent behaviors, unstable base, "has-a" |
| Mixins | Orthogonal capabilities (cacheable, auditable, soft-deletable) |

For standard repository patterns: **inheritance**. For complex behavior mixing: **composition**.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
