"""Databases — SQLite, time-series databases, and graph databases."""

PAIRS = [
    (
        "database/sqlite-patterns",
        "Show SQLite patterns: connection management, WAL mode, FTS5, JSON support, and performance tuning.",
        '''SQLite patterns for application development:

```python
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any


# --- Connection with optimal settings ---

def create_connection(db_path: str | Path) -> sqlite3.Connection:
    """Create SQLite connection with production settings."""
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row  # Dict-like access

    # Performance pragmas
    conn.executescript("""
        PRAGMA journal_mode = WAL;          -- Write-ahead logging (concurrent reads)
        PRAGMA synchronous = NORMAL;        -- Safe with WAL mode
        PRAGMA foreign_keys = ON;           -- Enforce FK constraints
        PRAGMA busy_timeout = 5000;         -- Wait 5s on lock instead of failing
        PRAGMA cache_size = -64000;         -- 64MB cache
        PRAGMA temp_store = MEMORY;         -- Temp tables in memory
        PRAGMA mmap_size = 268435456;       -- 256MB memory-mapped I/O
    """)
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection):
    """Explicit transaction context manager."""
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# --- Schema with migrations ---

MIGRATIONS = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        data JSON,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
    """,
    """
    CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        tags JSON DEFAULT '[]',
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_posts_user ON posts(user_id);
    """,
]


def run_migrations(conn: sqlite3.Connection):
    conn.execute("CREATE TABLE IF NOT EXISTS _migrations (version INTEGER PRIMARY KEY)")
    current = conn.execute("SELECT COALESCE(MAX(version), 0) FROM _migrations").fetchone()[0]

    for i, sql in enumerate(MIGRATIONS[current:], start=current + 1):
        conn.executescript(sql)
        conn.execute("INSERT INTO _migrations (version) VALUES (?)", (i,))
    conn.commit()


# --- JSON support (SQLite 3.38+) ---

def json_queries(conn: sqlite3.Connection):
    # Insert JSON data
    conn.execute(
        "INSERT INTO users (email, name, data) VALUES (?, ?, json(?))",
        ("alice@example.com", "Alice", '{"role": "admin", "prefs": {"theme": "dark"}}'),
    )

    # Extract JSON fields
    rows = conn.execute("""
        SELECT name, json_extract(data, '$.role') as role,
               json_extract(data, '$.prefs.theme') as theme
        FROM users
        WHERE json_extract(data, '$.role') = 'admin'
    """).fetchall()

    # Update JSON field
    conn.execute("""
        UPDATE users
        SET data = json_set(data, '$.prefs.theme', 'light')
        WHERE email = ?
    """, ("alice@example.com",))

    # Query JSON arrays
    conn.execute("""
        SELECT * FROM posts
        WHERE EXISTS (
            SELECT 1 FROM json_each(tags)
            WHERE json_each.value = 'python'
        )
    """)


# --- Full-text search (FTS5) ---

def setup_fts(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE VIRTUAL TABLE IF NOT EXISTS posts_fts USING fts5(
            title, body, content=posts, content_rowid=id,
            tokenize='porter unicode61'
        );

        -- Triggers to keep FTS in sync
        CREATE TRIGGER IF NOT EXISTS posts_ai AFTER INSERT ON posts BEGIN
            INSERT INTO posts_fts(rowid, title, body)
            VALUES (new.id, new.title, new.body);
        END;

        CREATE TRIGGER IF NOT EXISTS posts_ad AFTER DELETE ON posts BEGIN
            INSERT INTO posts_fts(posts_fts, rowid, title, body)
            VALUES ('delete', old.id, old.title, old.body);
        END;

        CREATE TRIGGER IF NOT EXISTS posts_au AFTER UPDATE ON posts BEGIN
            INSERT INTO posts_fts(posts_fts, rowid, title, body)
            VALUES ('delete', old.id, old.title, old.body);
            INSERT INTO posts_fts(rowid, title, body)
            VALUES (new.id, new.title, new.body);
        END;
    """)


def search_posts(conn: sqlite3.Connection, query: str) -> list[dict]:
    """Full-text search with ranking."""
    rows = conn.execute("""
        SELECT p.*, rank
        FROM posts_fts fts
        JOIN posts p ON p.id = fts.rowid
        WHERE posts_fts MATCH ?
        ORDER BY rank
        LIMIT 20
    """, (query,)).fetchall()
    return [dict(r) for r in rows]
```

SQLite patterns:
1. **WAL mode** — enables concurrent readers with one writer
2. **`PRAGMA` tuning** — busy_timeout, cache_size, mmap for production use
3. **`json_extract()`** — query JSON columns without separate document store
4. **FTS5** — full-text search with Porter stemming and Unicode support
5. **Migration table** — track schema versions for incremental upgrades'''
    ),
    (
        "database/timeseries",
        "Show time-series database patterns: data modeling, downsampling, retention policies, and query patterns.",
        '''Time-series database patterns (using TimescaleDB/SQL):

```sql
-- --- TimescaleDB hypertable setup ---

-- Enable extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Create regular table
CREATE TABLE metrics (
    time        TIMESTAMPTZ NOT NULL,
    sensor_id   TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    value       DOUBLE PRECISION NOT NULL,
    tags        JSONB DEFAULT '{}'
);

-- Convert to hypertable (auto-partitions by time)
SELECT create_hypertable('metrics', 'time',
    chunk_time_interval => INTERVAL '1 day'
);

-- Composite index for common queries
CREATE INDEX idx_metrics_sensor_time
    ON metrics (sensor_id, time DESC);


-- --- Insert data ---

INSERT INTO metrics (time, sensor_id, metric_name, value, tags)
VALUES
    (NOW(), 'sensor-01', 'temperature', 23.5, '{"location": "room-a"}'),
    (NOW(), 'sensor-01', 'humidity', 45.2, '{"location": "room-a"}'),
    (NOW(), 'sensor-02', 'temperature', 21.8, '{"location": "room-b"}');


-- --- Time-bucket aggregations ---

-- Hourly averages
SELECT
    time_bucket('1 hour', time) AS bucket,
    sensor_id,
    AVG(value) AS avg_value,
    MIN(value) AS min_value,
    MAX(value) AS max_value,
    COUNT(*) AS samples
FROM metrics
WHERE metric_name = 'temperature'
  AND time > NOW() - INTERVAL '24 hours'
GROUP BY bucket, sensor_id
ORDER BY bucket DESC;

-- Daily rollups with gap filling
SELECT
    time_bucket_gapfill('1 day', time) AS day,
    sensor_id,
    AVG(value) AS avg_temp,
    locf(AVG(value)) AS avg_temp_filled  -- Last observation carried forward
FROM metrics
WHERE metric_name = 'temperature'
  AND time BETWEEN '2024-01-01' AND '2024-01-31'
GROUP BY day, sensor_id
ORDER BY day;


-- --- Continuous aggregates (materialized views) ---

CREATE MATERIALIZED VIEW hourly_metrics
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS bucket,
    sensor_id,
    metric_name,
    AVG(value) AS avg_value,
    MIN(value) AS min_value,
    MAX(value) AS max_value,
    COUNT(*) AS sample_count
FROM metrics
GROUP BY bucket, sensor_id, metric_name
WITH NO DATA;

-- Auto-refresh policy
SELECT add_continuous_aggregate_policy('hourly_metrics',
    start_offset    => INTERVAL '3 hours',
    end_offset      => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour'
);


-- --- Retention policies ---

-- Drop raw data older than 30 days
SELECT add_retention_policy('metrics', INTERVAL '30 days');

-- Keep hourly aggregates for 1 year
SELECT add_retention_policy('hourly_metrics', INTERVAL '1 year');


-- --- Compression ---

-- Enable compression on hypertable
ALTER TABLE metrics SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'sensor_id,metric_name',
    timescaledb.compress_orderby = 'time DESC'
);

-- Auto-compress chunks older than 7 days
SELECT add_compression_policy('metrics', INTERVAL '7 days');


-- --- Anomaly detection query ---

-- Find values more than 3 standard deviations from the mean
WITH stats AS (
    SELECT
        sensor_id,
        AVG(value) AS mean_val,
        STDDEV(value) AS std_val
    FROM metrics
    WHERE metric_name = 'temperature'
      AND time > NOW() - INTERVAL '7 days'
    GROUP BY sensor_id
)
SELECT m.time, m.sensor_id, m.value,
       s.mean_val, s.std_val,
       ABS(m.value - s.mean_val) / NULLIF(s.std_val, 0) AS z_score
FROM metrics m
JOIN stats s ON m.sensor_id = s.sensor_id
WHERE m.metric_name = 'temperature'
  AND ABS(m.value - s.mean_val) > 3 * s.std_val
ORDER BY m.time DESC;
```

Time-series patterns:
1. **Hypertables** — auto-partition by time for efficient range queries
2. **`time_bucket()`** — aggregate into fixed intervals (1min, 1hr, 1day)
3. **Continuous aggregates** — pre-computed rollups refreshed automatically
4. **Retention policies** — auto-drop old raw data, keep aggregates longer
5. **Compression** — 90%+ compression ratio on time-series data'''
    ),
    (
        "database/graph-neo4j",
        "Show graph database patterns with Neo4j: Cypher queries, relationship modeling, graph algorithms, and recommendations.",
        '''Graph database patterns with Neo4j Cypher:

```cypher
// --- Create nodes and relationships ---

// Create users
CREATE (alice:User {name: 'Alice', email: 'alice@example.com', joined: date('2024-01-15')})
CREATE (bob:User {name: 'Bob', email: 'bob@example.com', joined: date('2024-02-01')})
CREATE (carol:User {name: 'Carol', email: 'carol@example.com', joined: date('2024-03-10')})

// Create products
CREATE (laptop:Product {name: 'Laptop Pro', price: 1299.99, category: 'Electronics'})
CREATE (phone:Product {name: 'Phone X', price: 999.99, category: 'Electronics'})
CREATE (book:Product {name: 'Graph Databases', price: 49.99, category: 'Books'})

// Create relationships
CREATE (alice)-[:PURCHASED {date: date('2024-06-01'), quantity: 1}]->(laptop)
CREATE (alice)-[:PURCHASED {date: date('2024-06-15'), quantity: 1}]->(book)
CREATE (bob)-[:PURCHASED {date: date('2024-06-02'), quantity: 1}]->(laptop)
CREATE (bob)-[:PURCHASED {date: date('2024-06-10'), quantity: 1}]->(phone)
CREATE (alice)-[:FOLLOWS]->(bob)
CREATE (bob)-[:FOLLOWS]->(carol)
CREATE (carol)-[:FOLLOWS]->(alice)


// --- Basic queries ---

// Find all of Alice's purchases
MATCH (u:User {name: 'Alice'})-[p:PURCHASED]->(product:Product)
RETURN product.name, p.date, p.quantity
ORDER BY p.date DESC;

// Find friends of friends
MATCH (u:User {name: 'Alice'})-[:FOLLOWS*2]->(fof:User)
WHERE fof <> u
  AND NOT (u)-[:FOLLOWS]->(fof)
RETURN DISTINCT fof.name AS suggested_friend;


// --- Recommendation engine ---

// Collaborative filtering: "Users who bought X also bought..."
MATCH (u:User)-[:PURCHASED]->(p:Product)<-[:PURCHASED]-(other:User)-[:PURCHASED]->(rec:Product)
WHERE u.name = 'Alice'
  AND NOT (u)-[:PURCHASED]->(rec)
RETURN rec.name, rec.category, COUNT(DISTINCT other) AS score
ORDER BY score DESC
LIMIT 5;


// --- Shortest path ---

MATCH path = shortestPath(
    (a:User {name: 'Alice'})-[:FOLLOWS*..6]-(b:User {name: 'Carol'})
)
RETURN path, length(path) AS distance;

// All shortest paths
MATCH paths = allShortestPaths(
    (a:User {name: 'Alice'})-[:FOLLOWS*..6]-(b:User {name: 'Carol'})
)
RETURN paths;


// --- Aggregation and projection ---

// Most popular products
MATCH (u:User)-[:PURCHASED]->(p:Product)
RETURN p.name, p.category,
       COUNT(u) AS buyer_count,
       SUM(p.price) AS total_revenue
ORDER BY buyer_count DESC;

// User purchase graph
MATCH (u:User)-[:PURCHASED]->(p:Product)
WITH u, COLLECT(p.name) AS products, COUNT(p) AS total_purchases
RETURN u.name, products, total_purchases
ORDER BY total_purchases DESC;


// --- Graph algorithms (GDS library) ---

// PageRank — find influential users
// CALL gds.pageRank.stream('social-graph')
// YIELD nodeId, score
// RETURN gds.util.asNode(nodeId).name AS user, score
// ORDER BY score DESC;

// Community detection (Louvain)
// CALL gds.louvain.stream('social-graph')
// YIELD nodeId, communityId
// RETURN communityId, COLLECT(gds.util.asNode(nodeId).name) AS members
// ORDER BY SIZE(members) DESC;


// --- Indexes and constraints ---

CREATE CONSTRAINT user_email IF NOT EXISTS
FOR (u:User) REQUIRE u.email IS UNIQUE;

CREATE INDEX user_name IF NOT EXISTS
FOR (u:User) ON (u.name);

CREATE INDEX product_category IF NOT EXISTS
FOR (p:Product) ON (p.category);
```

```python
# --- Python driver usage ---

from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"))


def get_recommendations(user_name: str, limit: int = 5) -> list[dict]:
    with driver.session() as session:
        result = session.run("""
            MATCH (u:User {name: $name})-[:PURCHASED]->(p:Product)
                  <-[:PURCHASED]-(other:User)-[:PURCHASED]->(rec:Product)
            WHERE NOT (u)-[:PURCHASED]->(rec)
            RETURN rec.name AS product, rec.category AS category,
                   COUNT(DISTINCT other) AS score
            ORDER BY score DESC
            LIMIT $limit
        """, name=user_name, limit=limit)
        return [dict(record) for record in result]
```

Graph database patterns:
1. **Relationship-first modeling** — edges are first-class, not join tables
2. **Variable-length paths** — `[:FOLLOWS*2..6]` traverses 2-6 hops
3. **Collaborative filtering** — "also bought" via shared purchase relationships
4. **`shortestPath()`** — built-in graph traversal algorithms
5. **Indexes on lookup properties** — speed up MATCH starting points'''
    ),
]
"""
