"""Phase 2C: Advanced Reasoning — Analogical Reasoning (Part 10)"""

PAIRS = [
    (
        "thinking/analogy-database-connection-pool-to-taxi-fleet",
        "I keep getting 'too many database connections' errors in production. Someone said I need connection pooling. What is it and why do I need it?",
        r'''<think>
Database connection pooling — the taxi fleet analogy works perfectly.

**Without pooling:**
Every request creates a new database connection. This is like every passenger buying a car for one trip, then throwing it away. Expensive, wasteful, and eventually you run out of parking (max connections).

**With pooling:**
A pool of reusable connections is maintained. When a request needs the DB, it borrows a connection from the pool, uses it, and returns it. Like a taxi fleet — taxis serve multiple passengers, nobody buys a car for one trip.

**Where it maps:**
- Creating a connection = buying a car (expensive: TCP handshake, TLS, authentication, ~50-100ms)
- Using a connection = riding in a car
- Closing a connection = scrapping a car
- Connection pool = taxi fleet (fixed number of taxis serving many passengers)
- Pool exhaustion = all taxis busy (new passengers must wait)
- Pool size = fleet size (too few → passengers wait, too many → parking costs)

**Where it breaks down:**
- Taxis are physical; connections are virtual (but still have resource cost)
- Taxis serve one passenger at a time; some DB connections can multiplex
- The analogy doesn't capture connection validation (is this connection still alive?)
</think>

Think of database connection pooling like a **taxi fleet** instead of everyone buying their own car.

## The Analogy

```
WITHOUT CONNECTION POOLING (buying a car for each trip):
  Request 1: Buy car → drive to destination → scrap car
  Request 2: Buy car → drive to destination → scrap car
  Request 3: Buy car → drive to destination → scrap car

  Each "car" (connection) costs:
    TCP handshake:     ~10ms
    TLS negotiation:   ~20ms
    Authentication:    ~10ms
    Total setup:       ~50ms per request (BEFORE any query runs)

  At 100 requests/second: buying and scrapping 100 cars per second.
  Database: "I can only handle 100 parked cars (max_connections)!"

WITH CONNECTION POOLING (taxi fleet):
  Pool starts: 10 taxis (connections) ready and waiting
  Request 1: Get taxi → ride → return taxi to pool
  Request 2: Get taxi → ride → return taxi to pool
  Request 3: Get taxi → ride → return taxi to pool

  Setup cost: 0ms (taxi already running)
  At 100 requests/second: 10 taxis serve all 100 requests
  Database: 10 connections, happy.
```

## Why You're Getting "Too Many Connections"

```
YOUR SITUATION:

  Each web request creates a NEW database connection:
    Request → connect() → query → close()
    Request → connect() → query → close()
    × 100 requests/second = 100 connections at any moment

  PostgreSQL default: max_connections = 100
  At 100+ concurrent requests → "too many connections" error

WITH POOLING:

  Pool of 20 connections, reused across all requests:
    Request → borrow from pool → query → return to pool
    20 connections serve 100+ requests/second

  How? Each query takes ~5ms. In 1 second, one connection handles ~200 queries.
  20 connections × 200 queries = 4,000 queries/second capacity.
```

## Implementation

```python
# ❌ WITHOUT POOL: new connection per request
import psycopg2

def get_user(user_id):
    conn = psycopg2.connect("postgresql://localhost/mydb")  # 50ms setup!
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    conn.close()  # Connection thrown away
    return user


# ✅ WITH POOL: reuse connections
from psycopg2 import pool

# Create pool once at app startup
db_pool = pool.ThreadedConnectionPool(
    minconn=5,     # Keep at least 5 connections ready
    maxconn=20,    # Never exceed 20 connections
    dsn="postgresql://localhost/mydb"
)

def get_user(user_id):
    conn = db_pool.getconn()  # Borrow from pool (~0ms)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        return cursor.fetchone()
    finally:
        db_pool.putconn(conn)  # Return to pool (NOT closed)


# ✅ WITH SQLALCHEMY (recommended — handles pooling automatically)
from sqlalchemy import create_engine

engine = create_engine(
    "postgresql://localhost/mydb",
    pool_size=20,              # 20 connections in pool
    max_overflow=10,           # Allow 10 extra under heavy load
    pool_timeout=30,           # Wait 30s for a connection before error
    pool_recycle=3600,         # Recreate connections after 1 hour
    pool_pre_ping=True,        # Check if connection is alive before using
)
```

## Pool Sizing (How Many Taxis?)

```
TOO FEW connections (fleet too small):
  Pool size: 5, Load: 200 requests/second
  Requests wait in queue for a free connection
  Latency spikes: p99 goes from 10ms to 500ms
  Pool exhaustion errors if queue fills up

TOO MANY connections (fleet too large):
  Pool size: 500
  Database overwhelmed: each connection costs ~10MB RAM on the DB server
  500 connections × 10MB = 5GB RAM just for connections
  Context switching overhead kills DB performance

JUST RIGHT (rule of thumb):
  Pool size = (2 × number_of_cpu_cores) + number_of_disks
  For most setups: 10-30 connections per application instance

  Example:
    4-core database server → pool_size = (2 × 4) + 1 = 9
    3 application instances → each gets pool_size = 9 → 27 total connections
    Database max_connections: 30 (27 + headroom for admin)
```

## Where the Analogy Breaks Down

```
1. STALE CONNECTIONS:
   A taxi in a fleet doesn't "go stale" — but a DB connection can.
   Network timeout, server restart, firewall rule → connection is dead.
   Solution: pool_pre_ping=True (check if connection works before using)

2. CONNECTION STATE:
   A taxi doesn't remember the last passenger's destination.
   A DB connection might have: open transactions, changed settings,
   temp tables from the previous user.
   Solution: pool resets connections when returned (RESET ALL in Postgres)

3. MULTIPLEXING:
   Real taxis carry one passenger at a time.
   Some DB proxies (PgBouncer) multiplex: one connection serves
   multiple clients by sharing at the transaction level.
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
