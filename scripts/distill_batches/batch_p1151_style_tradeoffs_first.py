"""
Response variety training pairs - Lead with tradeoffs
Opens with options and pros/cons before recommending one approach.
"""

pairs = [
    {
        "instruction": r'''Should I use Redis or Memcached for caching in my Python web app?''',
        "output": r'''There are a few approaches here, each with different tradeoffs:

**Option 1: Redis**
- Pros: Rich data structures (lists, sets, sorted sets, hashes), persistence options, pub/sub, Lua scripting, built-in replication
- Cons: Slightly more memory overhead per key, single-threaded (though very fast), more complex to configure

**Option 2: Memcached**
- Pros: Dead simple, multi-threaded so it scales well on multi-core, slightly less memory per key for plain string caching, battle-tested for decades
- Cons: Only supports string values, no persistence, no pub/sub, no built-in replication

**Option 3: Application-level cache (e.g., cachetools or lru_cache)**
- Pros: Zero infrastructure, no network round-trip, trivial to set up
- Cons: Not shared across processes/servers, lost on restart, eats into your app's memory

My recommendation: go with Redis unless you have a specific reason not to. Here's why and a quick setup:

```python
import redis
from functools import wraps
import json

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

def cached(ttl=300, prefix='cache'):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = f"{prefix}:{func.__name__}:{args}:{kwargs}"
            result = r.get(key)
            if result is not None:
                return json.loads(result)
            result = func(*args, **kwargs)
            r.setex(key, ttl, json.dumps(result))
            return result
        return wrapper
    return decorator

@cached(ttl=600)
def get_user_profile(user_id):
    # expensive database query
    return db.query(User).filter_by(id=user_id).first().to_dict()
```

Redis wins for most web apps because you'll almost certainly want more than simple key-value caching eventually -- rate limiting, session storage, job queues -- and Redis handles all of those. Memcached only makes sense if you're doing massive-scale simple string caching and need multi-threaded performance.'''
    },
    {
        "instruction": r'''I need to add background job processing to my Django app. What should I use?''',
        "output": r'''There are a few approaches here, each with different tradeoffs:

**Option 1: Celery + Redis/RabbitMQ**
- Pros: Industry standard, massive ecosystem, supports schedules/retries/chaining, scales horizontally, great monitoring (Flower)
- Cons: Complex setup, requires a separate broker, worker processes, can be overkill for simple needs

**Option 2: Django-Q2**
- Pros: Django-native, uses your existing database as a broker (no extra infra), simple API, admin integration
- Cons: Database-as-broker doesn't scale as well, smaller community, fewer advanced features

**Option 3: Huey**
- Pros: Lightweight, minimal dependencies, Redis-backed, simple API, good for small-medium projects
- Cons: Smaller ecosystem than Celery, fewer monitoring tools

My recommendation: if you're already running Redis (for caching, sessions, etc.), go with Celery. If you want minimal infrastructure, Django-Q2 is excellent for getting started.

Here's a minimal Celery setup:

```python
# myproject/celery.py
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
app = Celery('myproject')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# settings.py
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'

# myapp/tasks.py
from celery import shared_task

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_welcome_email(self, user_id):
    try:
        user = User.objects.get(id=user_id)
        send_email(user.email, 'Welcome!', render_template('welcome.html'))
    except Exception as exc:
        raise self.retry(exc=exc)

# In your view
from myapp.tasks import send_welcome_email
send_welcome_email.delay(user.id)
```

Start the worker with: `celery -A myproject worker -l info`

The key insight: don't pass Django model instances to tasks -- pass IDs and re-fetch. Objects can change between when you enqueue and when the task runs.'''
    },
    {
        "instruction": r'''What's the best way to deploy a Python API -- containers, serverless, or a traditional VM?''',
        "output": r'''There are a few approaches here, each with different tradeoffs:

**Option 1: Containers (Docker + Kubernetes/ECS)**
- Pros: Consistent environments, horizontal scaling, portable across clouds, great for microservices, good CI/CD story
- Cons: Operational complexity (especially K8s), need to manage cluster infrastructure, container image management
- Best for: Teams with DevOps capacity, microservice architectures, medium-to-large scale

**Option 2: Serverless (AWS Lambda, Google Cloud Functions)**
- Pros: Zero server management, pay-per-invocation (cheap at low traffic), auto-scales to zero, fast deployment
- Cons: Cold starts (especially Python), 15-min execution limit, vendor lock-in, hard to run locally, connection pooling headaches with databases
- Best for: Event-driven workloads, low-to-medium traffic APIs, teams without ops expertise

**Option 3: Traditional VM/VPS (EC2, DigitalOcean Droplet)**
- Pros: Simple mental model, full control, easy debugging (SSH in), no cold starts, cheapest at consistent load
- Cons: Manual scaling, you manage updates/security patches, single point of failure without extra work
- Best for: Early-stage startups, predictable traffic, simple deployments

My recommendation depends on your scale, but for most teams starting out I'd suggest containers on a managed platform:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["gunicorn", "main:app", "-w", "4", "-k", "uvicorn.UvicornWorker", "-b", "0.0.0.0:8000"]
```

Deploy this to AWS ECS Fargate, Google Cloud Run, or Railway. You get container benefits without managing Kubernetes. Cloud Run in particular gives you scale-to-zero like serverless but with regular containers -- best of both worlds for many use cases.

Start with a single container service, add a load balancer when you need horizontal scaling. Only move to full Kubernetes when you have multiple services that need to communicate.'''
    },
    {
        "instruction": r'''Should I use a monorepo or polyrepo for my team's projects?''',
        "output": r'''There are a few approaches here, each with different tradeoffs:

**Option 1: Monorepo (all projects in one repository)**
- Pros: Atomic cross-project changes, shared tooling/configs, easier code reuse, single CI pipeline, simplified dependency management
- Cons: Requires specialized tooling at scale (Nx, Turborepo, Bazel), slower git operations as it grows, blast radius of bad commits is larger, access control is coarser
- Best for: Tightly coupled services, shared libraries, teams that frequently make cross-cutting changes

**Option 2: Polyrepo (separate repo per project)**
- Pros: Clear ownership boundaries, independent release cycles, faster git operations, granular access control, simpler CI per repo
- Cons: Diamond dependency hell, harder to make cross-repo changes, duplicated configs/tooling, versioning coordination overhead
- Best for: Independent teams/services, open-source projects, loosely coupled architectures

**Option 3: Hybrid (monorepo for related services, separate repos for independent ones)**
- Pros: Pragmatic balance, group tightly coupled code together while keeping unrelated projects separate
- Cons: Need to decide where the boundaries are, two sets of tooling to maintain

My recommendation: start with a monorepo using Turborepo (for JS/TS) or a simple Makefile-based approach (for Python):

```
mycompany/
  packages/
    shared-utils/
      pyproject.toml
      src/
    api-service/
      pyproject.toml
      src/
    worker-service/
      pyproject.toml
      src/
  Makefile
  .github/workflows/ci.yml
```

```makefile
# Makefile -- run affected services only
.PHONY: test-all test-api test-worker

test-api:
	cd packages/api-service && pytest

test-worker:
	cd packages/worker-service && pytest

test-all: test-api test-worker

lint:
	ruff check packages/

format:
	ruff format packages/
```

The key insight: monorepo vs polyrepo is less about the repo structure and more about your team structure. If your teams share code and make coordinated changes frequently, a monorepo reduces friction. If teams are autonomous and rarely touch each other's code, polyrepo gives cleaner boundaries.'''
    },
    {
        "instruction": r'''I need to add full-text search to my app. Should I use PostgreSQL's built-in search, Elasticsearch, or something else?''',
        "output": r'''There are a few approaches here, each with different tradeoffs:

**Option 1: PostgreSQL full-text search (tsvector/tsquery)**
- Pros: No extra infrastructure, ACID-compliant, GIN indexes are fast, supports ranking
- Cons: Limited relevance tuning, no fuzzy matching, struggles above ~10M documents
- Best for: Apps already on Postgres with < 5M searchable documents

**Option 2: Elasticsearch/OpenSearch**
- Pros: Fuzzy matching, faceted search, scales to billions, excellent relevance tuning
- Cons: Separate cluster (expensive), data sync complexity, JVM memory hungry
- Best for: Search-heavy apps, e-commerce, log analytics

**Option 3: Meilisearch or Typesense**
- Pros: Lightweight, typo-tolerant by default, simple REST API, easy to self-host
- Cons: Less mature, fewer advanced features, still needs sync infrastructure
- Best for: Small-medium apps wanting great search UX without Elasticsearch complexity

My recommendation: start with PostgreSQL.

```sql
ALTER TABLE articles ADD COLUMN search_vector tsvector;

UPDATE articles SET search_vector =
    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(body, '')), 'B');

CREATE INDEX idx_articles_search ON articles USING GIN(search_vector);

-- Auto-update trigger
CREATE OR REPLACE FUNCTION update_search_vector() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('english', coalesce(NEW.title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(NEW.body, '')), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER articles_search_update
    BEFORE INSERT OR UPDATE ON articles
    FOR EACH ROW EXECUTE FUNCTION update_search_vector();

-- Query with ranking
SELECT title, ts_rank(search_vector, query) AS rank
FROM articles, plainto_tsquery('english', 'python async') AS query
WHERE search_vector @@ query
ORDER BY rank DESC LIMIT 20;
```

This covers 90% of search needs. Only move to Elasticsearch when you need fuzzy matching, facets, or hit performance walls with millions of documents.'''
    },
]
