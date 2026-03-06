"""Phase 3A: Metacognition — Error Recognition in Own Output (Part 5)
Scenarios: Under-engineering, wrong abstractions, incorrect library assumptions
"""

PAIRS = [
    (
        "thinking/meta-error-missing-edge-cases-parser",
        r'''I wrote this email validation function:

```python
def is_valid_email(email: str) -> bool:
    if '@' not in email:
        return False
    local, domain = email.split('@')
    if not local or not domain:
        return False
    if '.' not in domain:
        return False
    return True
```

Is this validation sufficient?''',
        r'''<think>
Let me think about what email addresses this allows and rejects...

What it correctly handles:
- `user@example.com` → True (correct)
- `@example.com` → False (correct, no local part)
- `user@` → False (correct, no domain)
- `user.example.com` → False (correct, no @)
- `user@example` → False (correct, no dot in domain)

What it gets WRONG:

1. Multiple @ signs: `user@name@example.com` — `email.split('@')` returns 3 parts, but we unpack into 2 variables. This would raise `ValueError: too many values to unpack`! The function CRASHES instead of returning False.

2. `user@.com` — has a dot in domain but domain starts with dot. Invalid, but returns True.

3. `user@example..com` — consecutive dots. Invalid, but returns True.

4. `"user name"@example.com` — valid according to RFC 5321 (quoted local parts). This would be rejected or handled oddly.

5. `user+tag@example.com` — valid (plus addressing). This one actually passes correctly.

6. `user@192.168.1.1` — IP address domain. No dot required in some formats. Edge case.

7. `user@example.c` — single-char TLD. Currently passes. Actually valid per RFC.

The most critical bug is #1 — the function raises an unhandled exception on emails with multiple @ signs, which an attacker could easily trigger to crash the application.

This is classic under-engineering: the function handles the happy path and a few obvious error cases, but misses edge cases that cause crashes or accept invalid input. The split('@') without maxsplit is the most dangerous issue.

My error: I assumed the input would be "well-formed enough" for basic parsing, but a validation function's entire purpose is handling malformed input. The least trusted input requires the most robust handling.
</think>

**This validation has a crash bug on multiple @ signs and accepts several invalid formats.**

### Critical Bug: Crash on multiple @ signs
```python
email = "user@name@example.com"
local, domain = email.split('@')  # ValueError: too many values to unpack!
```

The function crashes instead of returning False. An attacker can trigger this trivially.

### Other missed edge cases
```python
is_valid_email("user@.com")        # True — domain starts with dot
is_valid_email("user@example..com") # True — consecutive dots
is_valid_email(".user@example.com") # True — local starts with dot
is_valid_email("user@example.com.") # True — trailing dot
is_valid_email("a" * 500 + "@x.com") # True — absurdly long
```

### Improved version
```python
import re

def is_valid_email(email: str) -> bool:
    if not email or len(email) > 254:
        return False
    # Split on LAST @ to handle edge cases
    if '@' not in email:
        return False
    local, _, domain = email.rpartition('@')
    if not local or len(local) > 64:
        return False
    if not domain or len(domain) > 253:
        return False
    # Domain: labels separated by dots, each 1-63 chars
    if domain.startswith('.') or domain.endswith('.'):
        return False
    if '..' in domain:
        return False
    domain_regex = re.compile(
        r'^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?'
        r'(\.[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)*'
        r'\.[a-zA-Z]{2,}$'
    )
    return bool(domain_regex.match(domain))
```

Or better yet, use a battle-tested library:
```python
from email_validator import validate_email, EmailNotValidError

def is_valid_email(email: str) -> bool:
    try:
        validate_email(email, check_deliverability=False)
        return True
    except EmailNotValidError:
        return False
```

### The meta-lesson
Validation functions exist specifically to handle malformed input — they're the one place where "this input will be reasonable" is guaranteed to be wrong. Always test with adversarial inputs: empty strings, extreme lengths, repeated special characters, and characters in unexpected positions. And prefer `rpartition` over `split` when you need exactly two parts from input that may contain extra delimiters.'''
    ),
    (
        "thinking/meta-error-leaky-abstraction-db-wrapper",
        r'''I created this database abstraction layer to make it easy to switch databases later:

```python
class DatabaseWrapper:
    def __init__(self, connection_string):
        if 'postgres' in connection_string:
            import psycopg2
            self.conn = psycopg2.connect(connection_string)
            self.db_type = 'postgres'
        elif 'mysql' in connection_string:
            import mysql.connector
            self.conn = mysql.connector.connect(connection_string)
            self.db_type = 'mysql'
        elif 'sqlite' in connection_string:
            import sqlite3
            self.conn = sqlite3.connect(connection_string)
            self.db_type = 'sqlite'

    def query(self, sql, params=None):
        cursor = self.conn.cursor()
        cursor.execute(sql, params or ())
        return cursor.fetchall()

    def insert(self, table, data: dict):
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['%s'] * len(data))
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        cursor = self.conn.cursor()
        cursor.execute(sql, list(data.values()))
        self.conn.commit()
```

This abstracts away the database differences nicely, right?''',
        r'''<think>
Let me examine this "abstraction" layer...

First, the abstraction claims to let you "switch databases later." But does it actually abstract the differences?

1. **Placeholder syntax differs:** PostgreSQL and MySQL use `%s`, but SQLite uses `?`. The `insert` method hardcodes `%s` — it will fail on SQLite immediately!

2. **SQL dialect differences leak through:** The `query` method takes raw SQL. If I write `SELECT * FROM users LIMIT 10`, that works in PostgreSQL and MySQL but SQLite also supports it. But `SELECT TOP 10 * FROM users` is SQL Server. `RETURNING id` works in PostgreSQL but not MySQL. The abstraction doesn't abstract SQL dialects at all — callers must still know which database they're targeting.

3. **Table name injection:** `f"INSERT INTO {table}"` — the table name is interpolated directly into SQL. If `table` comes from user input, this is SQL injection. Even if it doesn't, this pattern is fragile.

4. **No connection pooling:** Each `DatabaseWrapper` holds a single connection. In a web server, concurrent requests would share one connection or each create their own (no pooling).

5. **No transaction management:** `commit()` after every insert. No support for multi-statement transactions. If you need to insert into 3 tables atomically, you can't.

6. **No context manager / cleanup:** No `close()` method, no `__enter__`/`__exit__`. Connections leak.

The core error is building a wrong abstraction. This wrapper doesn't actually abstract the meaningful differences (SQL dialects, placeholder syntax, transaction semantics) while adding indirection that makes it harder to use database-specific features you actually need.

This is a classic "leaky abstraction" — it pretends to be database-agnostic but leaks implementation details everywhere. And YAGNI: "switch databases later" almost never happens, but the abstraction cost is paid immediately.
</think>

**This abstraction is leaky, broken on SQLite, and doesn't abstract the things that actually differ between databases.**

### Bug 1: Breaks on SQLite
```python
placeholders = ', '.join(['%s'] * len(data))
# PostgreSQL/MySQL: INSERT INTO users (name) VALUES (%s)  ✓
# SQLite: INSERT INTO users (name) VALUES (%s)  ✗ — SQLite uses ? not %s!
```

### Bug 2: SQL injection via table name
```python
sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
# table = "users; DROP TABLE users; --"
```

### Bug 3: The abstraction doesn't abstract the real differences
```python
# Caller code STILL needs to know the database:
db.query("SELECT * FROM users LIMIT 10")           # fails on SQL Server
db.query("SELECT * FROM users RETURNING id")        # fails on MySQL
db.query("SELECT * FROM users WHERE name ILIKE %s") # fails on SQLite/MySQL
```

The `query()` method takes raw SQL, so all dialect differences leak through. The abstraction only hides the *connection* (the easy part) while exposing the *SQL dialect* (the hard part).

### What's actually wrong with this design
The abstraction boundary is in the wrong place. You're abstracting connection creation (trivial, do it once) while not abstracting query building (the actual difference between databases). This is why ORMs like SQLAlchemy exist — they abstract at the query level:

```python
# SQLAlchemy: truly database-agnostic
from sqlalchemy import create_engine, Table, select

engine = create_engine(connection_string)  # handles all DB types
with engine.connect() as conn:
    result = conn.execute(
        select(users).where(users.c.name == name).limit(10)
    )
```

### The meta-lesson
A wrong abstraction is worse than no abstraction. If callers need to know implementation details to use your abstraction correctly, it's not abstracting — it's just adding indirection. Before building an abstraction, identify what ACTUALLY varies (SQL dialects, not connection calls) and abstract THAT. And ask: "Will we actually switch databases?" If the answer is "probably not," skip the abstraction entirely and use the database-specific features that make your code better.'''
    ),
    (
        "thinking/meta-error-wrong-pandas-merge-assumption",
        r'''I wrote this data pipeline using pandas to join user data with their transactions:

```python
import pandas as pd

def generate_report(users_df, transactions_df):
    # Join users with their transactions
    merged = users_df.merge(transactions_df, on='user_id')

    # Calculate total spending per user
    report = merged.groupby('user_id').agg(
        name=('name', 'first'),
        total_spent=('amount', 'sum'),
        transaction_count=('amount', 'count')
    ).reset_index()

    return report
```

I ran this and got 10x more rows than expected in `merged`. What happened?''',
        r'''<think>
Let me think about why the merge produces too many rows...

`users_df.merge(transactions_df, on='user_id')` — this does an inner join on `user_id`. If user_id is unique in both DataFrames, you get at most min(len(users), len(transactions)) rows.

But the user says they got 10x more rows. That means there are DUPLICATE user_id values in one or both DataFrames!

Common scenario: the users DataFrame has duplicate entries (maybe loaded from a denormalized export where each user appears per department, or the CSV had duplicate rows).

If users_df has:
| user_id | name  |
|---------|-------|
| 1       | Alice |
| 1       | Alice |  (duplicate!)

And transactions_df has:
| user_id | amount |
|---------|--------|
| 1       | 50     |
| 1       | 30     |

The merge produces a CROSS product of matching rows:
| user_id | name  | amount |
|---------|-------|--------|
| 1       | Alice | 50     |
| 1       | Alice | 30     |
| 1       | Alice | 50     |  (from second Alice row)
| 1       | Alice | 30     |  (from second Alice row)

4 rows instead of 2! With many duplicates, this explodes to 10x.

The error is not validating that the join key is unique on the "one" side of the relationship. In a users-to-transactions join, user_id should be unique in users_df (one-to-many), not duplicated (many-to-many).

The fix: either deduplicate before joining, or use the `validate` parameter:
```python
merged = users_df.merge(transactions_df, on='user_id', validate='one_to_many')
```
This raises an error if user_id isn't unique in users_df.
</think>

**The `user_id` column has duplicates in `users_df`, causing a many-to-many join that produces a cartesian product of matching rows.**

### What happened
```python
# If users_df has 2 rows for user_id=1, and transactions has 5:
# merge produces 2 × 5 = 10 rows for that user alone!
merged = users_df.merge(transactions_df, on='user_id')
```

Pandas `merge` does a SQL-style join. If the join key isn't unique on either side, it produces the cross product of all matching rows. With duplicates in `users_df`, every user row matches every transaction row.

### The fix: validate before merge
```python
def generate_report(users_df, transactions_df):
    # Option 1: Validate join cardinality (raises if duplicates exist)
    merged = users_df.merge(
        transactions_df,
        on='user_id',
        validate='one_to_many'  # user_id must be unique in users_df
    )

    # Option 2: Deduplicate first
    users_deduped = users_df.drop_duplicates(subset='user_id')
    merged = users_deduped.merge(transactions_df, on='user_id')

    report = merged.groupby('user_id').agg(
        name=('name', 'first'),
        total_spent=('amount', 'sum'),
        transaction_count=('amount', 'count')
    ).reset_index()

    return report
```

### Always check after merge
```python
print(f"Users: {len(users_df)}, Transactions: {len(transactions_df)}")
print(f"Merged: {len(merged)}")
# If merged > len(transactions_df), you have a many-to-many join!
```

### The meta-lesson
When joining datasets, always know the expected cardinality: one-to-one, one-to-many, or many-to-many. Use `validate` parameter to enforce it. Unexpected row count explosion after a merge almost always means duplicate join keys creating an unintended cross product.'''
    ),
    (
        "thinking/meta-error-wrong-concurrency-model-io",
        r'''I'm processing 1000 API calls to fetch user data. I used multiprocessing to speed it up:

```python
from multiprocessing import Pool
import requests

def fetch_user(user_id):
    response = requests.get(f"https://api.example.com/users/{user_id}")
    return response.json()

def fetch_all_users(user_ids):
    with Pool(processes=8) as pool:
        results = pool.map(fetch_user, user_ids)
    return results
```

It's faster than sequential, but still takes a while. Is this the right approach?''',
        r'''<think>
Let me think about what kind of work this is...

Each call to `fetch_user` makes an HTTP request and waits for the response. This is I/O-bound work — the CPU is idle while waiting for network responses. The bottleneck is network latency, not CPU computation.

`multiprocessing.Pool` creates 8 separate OS processes. Each process has its own Python interpreter, its own memory space, and its own GIL. This is designed for CPU-bound work where the GIL prevents threads from running in parallel.

For I/O-bound work, multiprocessing is the WRONG tool:
1. Each process uses ~30-50MB of memory (Python interpreter overhead)
2. Process creation/teardown is expensive (fork + interpreter initialization)
3. Inter-process communication adds overhead (pickling results)
4. With only 8 processes, you can only have 8 concurrent requests

The right tools for I/O-bound concurrency:
1. **Threading** — `concurrent.futures.ThreadPoolExecutor` with 50-100 threads. Threads share memory, are lightweight, and the GIL is released during I/O operations (socket reads).
2. **asyncio** — `aiohttp` with `asyncio.gather()`. Even lighter than threads, can handle thousands of concurrent requests with a single thread.

With threading, 100 threads can have 100 concurrent requests. With asyncio, a single thread can have 1000 concurrent requests (one per user_id).

With multiprocessing using 8 processes: 1000 requests / 8 concurrent = 125 sequential batches. If each request takes 200ms, that's 125 × 200ms = 25 seconds.

With asyncio and 100 concurrent requests: 1000 requests / 100 concurrent = 10 batches × 200ms = 2 seconds.

My error: I chose the concurrency model based on "make it parallel" without analyzing whether the work is CPU-bound or I/O-bound. For I/O-bound work, threading or asyncio is dramatically better than multiprocessing.
</think>

**Multiprocessing is the wrong concurrency model for I/O-bound work. Use threading or asyncio instead — they'll be 10-50x faster for this workload.**

### Why multiprocessing is wrong here
| Factor | Multiprocessing | Threading/Asyncio |
|--------|----------------|-------------------|
| Memory per worker | ~30-50MB (full interpreter) | ~50KB (thread) or ~1KB (coroutine) |
| Practical concurrency | 8-16 processes | 100-1000 threads or 10000 coroutines |
| Startup cost | High (fork + init) | Low |
| Best for | CPU-bound (number crunching) | I/O-bound (network, disk) |

With 8 processes, you get 8 concurrent requests. With asyncio, you get 1000.

### Fix 1: ThreadPoolExecutor (simplest change)
```python
from concurrent.futures import ThreadPoolExecutor
import requests

def fetch_all_users(user_ids):
    with ThreadPoolExecutor(max_workers=50) as executor:
        results = list(executor.map(fetch_user, user_ids))
    return results
```

### Fix 2: asyncio + aiohttp (fastest)
```python
import asyncio
import aiohttp

async def fetch_user(session, user_id):
    async with session.get(f"https://api.example.com/users/{user_id}") as resp:
        return await resp.json()

async def fetch_all_users(user_ids):
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_user(session, uid) for uid in user_ids]
        # Limit concurrency to avoid overwhelming the API
        semaphore = asyncio.Semaphore(100)
        async def limited(uid):
            async with semaphore:
                return await fetch_user(session, uid)
        results = await asyncio.gather(*[limited(uid) for uid in user_ids])
    return results
```

### Performance comparison (1000 requests, 200ms each)
- Sequential: 1000 × 200ms = **200 seconds**
- Multiprocessing (8 workers): 125 batches × 200ms = **25 seconds**
- Threading (50 workers): 20 batches × 200ms = **4 seconds**
- Asyncio (100 concurrent): 10 batches × 200ms = **2 seconds**

### The meta-lesson
Always ask "is this CPU-bound or I/O-bound?" before choosing a concurrency model. The GIL makes threads bad for CPU work, but I/O operations release the GIL — so threads (and asyncio) are perfect for network/disk operations. Multiprocessing pays a huge overhead cost that's only justified when you need true parallel CPU computation.'''
    ),
    (
        "thinking/meta-error-wrong-tradeoff-premature-microservices",
        r'''Our team of 3 developers is starting a new project — an internal tool for managing employee time-off requests. I proposed this architecture:

- Auth Service (Node.js) — handles SSO/OAuth
- User Service (Python) — manages employee profiles
- Request Service (Go) — handles time-off requests
- Notification Service (Python) — sends emails/Slack messages
- API Gateway (Kong) — routes requests
- Message Queue (RabbitMQ) — async communication between services
- Kubernetes cluster for deployment

Is this a good architecture for our project?''',
        r'''<think>
Let me evaluate this architecture against the actual requirements...

The project: internal tool for managing time-off requests.
Team: 3 developers.
Scope: SSO login, employee profiles, time-off requests, notifications.

This is a CRUD application with some notification logic. Let me count the infrastructure:
- 4 microservices in 3 different languages
- API Gateway
- Message queue
- Kubernetes cluster
- Plus: 4 separate CI/CD pipelines, 4 separate databases (probably), service discovery, distributed logging, distributed tracing...

For a team of 3, each developer would be responsible for ~1.3 services plus shared infrastructure. Context-switching between Node.js, Python, and Go means everyone needs to be proficient in 3 languages. Debugging a time-off request means tracing through 4 services and a message queue.

What does this architecture optimize for?
- Independent deployment of services → but 3 developers can just coordinate
- Language-specific optimization → but nothing here needs Go's performance or Node's event loop
- Team isolation → but there's no team isolation with 3 developers
- Scale individual services → but an internal tool for employees doesn't need to scale

What does this architecture cost?
- Network latency between services (what was a function call is now an HTTP/RPC call)
- Distributed transaction complexity (what if Request Service succeeds but Notification Service fails?)
- Operational overhead: Kubernetes, service mesh, monitoring, logging aggregation
- Development complexity: 3x the CI/CD pipelines, 3x the test environments
- Debugging complexity: distributed tracing required for basic flow understanding

The right architecture for a 3-person team building an internal CRUD tool is a MONOLITH. One codebase, one deployment, one database. When the team grows to 20+ and the product grows in complexity, THEN consider extracting services.

My error: I chose the architecture based on what's "modern" and "scalable" rather than what matches the team size and project complexity. This is a textbook case of over-engineering — paying enterprise-grade infrastructure costs for a team tool.
</think>

**This is massively over-engineered. A 3-person team building an internal CRUD tool doesn't need 4 microservices, 3 languages, a message queue, and Kubernetes.**

### The cost of this architecture for your team

| What you're adding | Operational cost |
|--------------------|--------------------|
| 4 services, 3 languages | Everyone must context-switch between Node/Python/Go |
| API Gateway (Kong) | Another system to configure, monitor, update |
| RabbitMQ | Message ordering, dead letters, queue monitoring |
| Kubernetes | Cluster management, YAML manifests, networking |
| 4 CI/CD pipelines | 4x build configs, 4x test environments |
| Distributed debugging | Need Jaeger/Zipkin tracing, log aggregation |

You'll spend more time on infrastructure than on the actual time-off logic.

### What you actually need
```
One Django/Rails/FastAPI monolith:
├── auth/        (SSO integration — one library)
├── users/       (employee profiles — one model)
├── requests/    (time-off requests — one model + business logic)
├── notifications/ (send email/Slack — one background task)
└── deploy via a single Dockerfile on a $20/month VPS
```

- **One codebase**: all 3 developers work in the same repo
- **One database**: joins instead of API calls between services
- **One deployment**: `git push` → CI → deploy
- **Function calls, not HTTP**: `send_notification(request)` instead of publishing to RabbitMQ

### When to consider microservices
- Team grows beyond ~10-15 developers (coordination cost exceeds monolith cost)
- A specific component needs independent scaling (e.g., notification sending at 10x the rate)
- A component needs a fundamentally different technology (ML model serving)
- Deployment coupling becomes a bottleneck (multiple daily deploys conflicting)

None of these apply to a 3-person team building an internal tool.

### The meta-lesson
Architecture should match team size and project complexity, not industry trends. Start with a monolith — you can always extract services later when you have evidence that specific components need independence. The cost of premature microservices is paid immediately (infrastructure complexity), while the benefits only materialize at scale you may never reach. A well-structured monolith is not a "bad architecture" — it's the right architecture for most projects.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
