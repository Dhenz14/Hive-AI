"""PostgreSQL — extensions, partitioning, full-text search, and performance tuning."""

PAIRS = [
    (
        "database/postgres-extensions",
        "Show PostgreSQL extension patterns: pgvector for embeddings, pg_trgm for fuzzy search, and PostGIS basics.",
        """PostgreSQL extension patterns:

```sql
-- --- pgvector: vector similarity search ---

CREATE EXTENSION IF NOT EXISTS vector;

-- Store embeddings alongside data
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1536),  -- OpenAI ada-002 dimension
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast similarity search
CREATE INDEX idx_documents_embedding
    ON documents USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);  -- Number of clusters

-- Or HNSW index (better recall, more memory)
CREATE INDEX idx_documents_hnsw
    ON documents USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Nearest neighbor search
SELECT id, title,
       1 - (embedding <=> $1::vector) AS similarity  -- Cosine similarity
FROM documents
ORDER BY embedding <=> $1::vector  -- Cosine distance
LIMIT 10;

-- Filtered similarity search
SELECT id, title,
       1 - (embedding <=> $1::vector) AS similarity
FROM documents
WHERE created_at > NOW() - INTERVAL '30 days'
ORDER BY embedding <=> $1::vector
LIMIT 10;


-- --- pg_trgm: fuzzy text search ---

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- GIN index for trigram similarity
CREATE INDEX idx_users_name_trgm
    ON users USING gin (name gin_trgm_ops);

-- Fuzzy search (typo-tolerant)
SELECT name, similarity(name, 'Jonh Smith') AS sim
FROM users
WHERE name % 'Jonh Smith'  -- Default threshold 0.3
ORDER BY sim DESC
LIMIT 10;

-- Adjust similarity threshold
SET pg_trgm.similarity_threshold = 0.4;

-- Word similarity (better for partial matches)
SELECT name, word_similarity('Smith', name) AS wsim
FROM users
WHERE 'Smith' <% name  -- Word similarity operator
ORDER BY wsim DESC;

-- Combine with LIKE for autocomplete
SELECT name FROM users
WHERE name ILIKE '%' || $1 || '%'
ORDER BY similarity(name, $1) DESC
LIMIT 20;


-- --- Full-text search (built-in) ---

-- Add tsvector column
ALTER TABLE articles ADD COLUMN search_vector tsvector;

-- Populate and auto-update
CREATE OR REPLACE FUNCTION update_search_vector() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('english', COALESCE(NEW.title, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.summary, '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(NEW.body, '')), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER articles_search_update
    BEFORE INSERT OR UPDATE ON articles
    FOR EACH ROW EXECUTE FUNCTION update_search_vector();

-- GIN index
CREATE INDEX idx_articles_search ON articles USING gin(search_vector);

-- Search with ranking
SELECT id, title, ts_rank(search_vector, query) AS rank,
       ts_headline('english', body, query,
                   'StartSel=<mark>, StopSel=</mark>, MaxFragments=3') AS snippet
FROM articles,
     to_tsquery('english', 'python & (async | await)') AS query
WHERE search_vector @@ query
ORDER BY rank DESC
LIMIT 20;


-- --- Partitioning ---

-- Range partitioning by date
CREATE TABLE events (
    id BIGSERIAL,
    event_type TEXT NOT NULL,
    payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
) PARTITION BY RANGE (created_at);

-- Create monthly partitions
CREATE TABLE events_2024_01 PARTITION OF events
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
CREATE TABLE events_2024_02 PARTITION OF events
    FOR VALUES FROM ('2024-02-01') TO ('2024-03-01');

-- Auto-create future partitions (pg_partman extension)
-- SELECT partman.create_parent('public.events', 'created_at', 'native', 'monthly');
-- SELECT partman.run_maintenance();

-- Queries automatically prune irrelevant partitions
EXPLAIN SELECT * FROM events
WHERE created_at BETWEEN '2024-01-15' AND '2024-01-20';
-- Only scans events_2024_01 partition
```

PostgreSQL patterns:
1. **pgvector** — vector similarity with IVFFlat or HNSW indexes for embeddings
2. **pg_trgm** — fuzzy matching with trigram similarity (typo-tolerant search)
3. **Weighted tsvector** — title=A, summary=B, body=C for ranked full-text search
4. **`ts_headline()`** — generate search result snippets with highlighted matches
5. **Range partitioning** — auto-prune old data, partition-level vacuum and indexing"""
    ),
    (
        "database/postgres-performance",
        "Show PostgreSQL performance tuning: EXPLAIN ANALYZE, index strategies, connection tuning, and query optimization.",
        """PostgreSQL performance tuning:

```sql
-- --- EXPLAIN ANALYZE: understanding query plans ---

-- Basic explain
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT u.name, COUNT(o.id) AS order_count
FROM users u
JOIN orders o ON o.user_id = u.id
WHERE u.created_at > '2024-01-01'
GROUP BY u.id, u.name
ORDER BY order_count DESC
LIMIT 20;

-- Key things to look for:
-- Seq Scan  → missing index (may be OK for small tables)
-- Nested Loop → fine for small result sets, bad for large joins
-- Hash Join  → good for medium/large joins
-- Sort       → check if index can avoid sort
-- Buffers: shared hit vs read → cache effectiveness


-- --- Index strategies ---

-- Composite index (column order matters!)
CREATE INDEX idx_orders_user_date
    ON orders (user_id, created_at DESC);
-- Supports: WHERE user_id = X AND created_at > Y
-- Also supports: WHERE user_id = X (leading column)

-- Partial index (smaller, faster)
CREATE INDEX idx_orders_pending
    ON orders (created_at)
    WHERE status = 'pending';
-- Only indexes pending orders — much smaller than full index

-- Covering index (index-only scan)
CREATE INDEX idx_users_email_covering
    ON users (email) INCLUDE (name, created_at);
-- Reads name and created_at from index without touching table

-- Expression index
CREATE INDEX idx_users_lower_email
    ON users (LOWER(email));
-- Supports: WHERE LOWER(email) = 'alice@example.com'

-- BRIN index (for naturally ordered data like timestamps)
CREATE INDEX idx_events_time_brin
    ON events USING brin (created_at)
    WITH (pages_per_range = 32);
-- Much smaller than B-tree, great for time-series append-only tables


-- --- Query optimization patterns ---

-- Avoid: SELECT * (fetches unnecessary columns)
-- Better: SELECT only needed columns

-- Avoid: WHERE column IS NOT NULL with a function
-- Better: Use partial index

-- Avoid: OFFSET for pagination (scans and discards rows)
-- Better: Keyset pagination
SELECT * FROM products
WHERE (price, id) > (19.99, 1000)  -- Last seen values
ORDER BY price, id
LIMIT 20;

-- Avoid: COUNT(*) on huge tables
-- Better: Approximate count
SELECT reltuples::bigint AS estimate
FROM pg_class WHERE relname = 'events';

-- Avoid: NOT IN (subquery) — poor performance with NULLs
-- Better: NOT EXISTS
SELECT * FROM users u
WHERE NOT EXISTS (
    SELECT 1 FROM banned_users b WHERE b.email = u.email
);

-- Batch operations instead of row-by-row
-- Avoid: INSERT one row at a time in a loop
-- Better: Batch insert
INSERT INTO events (event_type, payload)
SELECT unnest($1::text[]), unnest($2::jsonb[]);


-- --- Configuration tuning ---

-- Memory (adjust based on available RAM)
-- shared_buffers = '4GB'           -- 25% of RAM for dedicated DB server
-- effective_cache_size = '12GB'    -- 75% of RAM (OS cache estimate)
-- work_mem = '256MB'               -- Per-sort/hash operation
-- maintenance_work_mem = '1GB'     -- For VACUUM, CREATE INDEX

-- WAL
-- wal_buffers = '64MB'
-- checkpoint_completion_target = 0.9
-- max_wal_size = '4GB'

-- Planner
-- random_page_cost = 1.1           -- SSD (default 4.0 is for spinning disk)
-- effective_io_concurrency = 200   -- SSD
-- default_statistics_target = 200  -- More accurate planner estimates


-- --- Monitoring queries ---

-- Slow queries (requires pg_stat_statements)
SELECT query, calls, mean_exec_time, total_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 20;

-- Index usage
SELECT schemaname, tablename, indexname,
       idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY idx_scan ASC;  -- Unused indexes at top

-- Table bloat estimate
SELECT schemaname, tablename,
       pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) AS total_size,
       n_dead_tup, last_vacuum, last_autovacuum
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC;

-- Active queries and locks
SELECT pid, state, wait_event_type, wait_event,
       now() - query_start AS duration, query
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY duration DESC;
```

PostgreSQL performance patterns:
1. **`EXPLAIN (ANALYZE, BUFFERS)`** — see actual execution time and buffer I/O
2. **Partial indexes** — index only the rows you query (e.g., `WHERE status = 'pending'`)
3. **Covering indexes** — `INCLUDE` columns for index-only scans
4. **Keyset pagination** — `WHERE (col, id) > (last_val, last_id)` instead of OFFSET
5. **`random_page_cost = 1.1`** — tell planner you have SSDs for better index usage"""
    ),
]
