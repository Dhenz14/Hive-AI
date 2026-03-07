"""Code translation pairs: Between PostgreSQL, MySQL, and SQLite dialects."""

PAIRS = [
    (
        "code-translation/sql-dialects",
        r'''Convert this PostgreSQL query using window functions and CTEs to MySQL 5.7 (which lacks CTEs and has limited window function support):

WITH monthly_sales AS (
    SELECT
        salesperson_id,
        DATE_TRUNC('month', sale_date) AS month,
        SUM(amount) AS total
    FROM sales
    GROUP BY salesperson_id, DATE_TRUNC('month', sale_date)
),
ranked AS (
    SELECT
        *,
        RANK() OVER (PARTITION BY month ORDER BY total DESC) AS rnk,
        LAG(total) OVER (PARTITION BY salesperson_id ORDER BY month) AS prev_month
    FROM monthly_sales
)
SELECT * FROM ranked WHERE rnk <= 3;''',
        r'''<think>
This is tricky. MySQL 5.7 does NOT support CTEs (WITH ... AS) or window functions (RANK, LAG). Both were added in MySQL 8.0. So I need to rewrite everything using subqueries and user variables.

For RANK() OVER (PARTITION BY month ORDER BY total DESC):
- In MySQL 5.7, the classic approach uses user variables with ORDER BY in a subquery
- @rank resets when the partition key changes

For LAG() -- accessing the previous row's value:
- No window function available, so I need a self-join or correlated subquery to get the previous month's total

For DATE_TRUNC('month', date):
- MySQL doesn't have DATE_TRUNC. Use DATE_FORMAT(sale_date, '%Y-%m-01') or LAST_DAY / DATE_SUB tricks

CTEs just become derived tables (subqueries in FROM).

Let me be careful with the variable-based ranking -- the order of evaluation of SET and SELECT in the same statement is technically undefined in MySQL, but it's a widely used pattern.
</think>

```sql
-- MySQL 5.7 equivalent (no CTEs, no window functions)

-- Step 1: monthly_sales as a derived table
-- Step 2: ranking via user variables
-- Step 3: previous month via correlated subquery

SELECT ranked.*
FROM (
    SELECT
        ms.*,
        @rnk := IF(@cur_month = ms.month, @rnk + 1, 1) AS rnk,
        @cur_month := ms.month AS _dummy
    FROM (
        SELECT
            salesperson_id,
            DATE_FORMAT(sale_date, '%Y-%m-01') AS month,
            SUM(amount) AS total
        FROM sales
        GROUP BY salesperson_id, DATE_FORMAT(sale_date, '%Y-%m-01')
    ) ms,
    (SELECT @rnk := 0, @cur_month := '') AS vars
    ORDER BY ms.month, ms.total DESC
) ranked
WHERE ranked.rnk <= 3;

-- Note: LAG() equivalent requires a separate self-join:
-- SELECT r.*, prev.total AS prev_month
-- FROM ranked r
-- LEFT JOIN monthly_sales prev
--   ON prev.salesperson_id = r.salesperson_id
--   AND prev.month = DATE_SUB(r.month, INTERVAL 1 MONTH);
```

Key dialect differences:

- `DATE_TRUNC('month', d)` (Postgres) -> `DATE_FORMAT(d, '%Y-%m-01')` (MySQL)
- `WITH ... AS` (CTE) -> inline derived tables in FROM clause
- `RANK() OVER (PARTITION BY ...)` -> user variables `@rnk` with `IF()` to detect partition boundaries
- `LAG() OVER (...)` -> self-join on the previous month, since MySQL 5.7 has no way to reference previous rows inline
- Variable-based ranking requires careful ORDER BY in the subquery to ensure correct evaluation order''',
    ),
    (
        "code-translation/sql-dialects",
        r'''Translate this SQLite schema and queries to PostgreSQL, taking advantage of Postgres features:

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    data TEXT,  -- JSON stored as text
    created_at TEXT DEFAULT (datetime('now'))
);

INSERT INTO users (name, email, data)
VALUES ('Alice', 'alice@example.com', '{"role": "admin", "prefs": {"theme": "dark"}}');

-- Query JSON field
SELECT name, json_extract(data, '$.role') AS role
FROM users
WHERE json_extract(data, '$.prefs.theme') = 'dark';

-- Upsert
INSERT INTO users (name, email, data)
VALUES ('Alice', 'alice@example.com', '{"role": "admin"}')
ON CONFLICT(email) DO UPDATE SET
    data = excluded.data,
    created_at = datetime('now');''',
        r'''```sql
-- PostgreSQL equivalent with native JSON support

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    data JSONB,  -- native JSONB type instead of TEXT
    created_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO users (name, email, data)
VALUES (
    'Alice',
    'alice@example.com',
    '{"role": "admin", "prefs": {"theme": "dark"}}'::jsonb
);

-- Query JSON field using -> and ->> operators
SELECT name, data->>'role' AS role
FROM users
WHERE data->'prefs'->>'theme' = 'dark';

-- Upsert using ON CONFLICT (same syntax, different datetime)
INSERT INTO users (name, email, data)
VALUES ('Alice', 'alice@example.com', '{"role": "admin"}'::jsonb)
ON CONFLICT (email) DO UPDATE SET
    data = EXCLUDED.data,
    created_at = NOW();
```

Key dialect differences:

- `INTEGER PRIMARY KEY AUTOINCREMENT` -> `SERIAL PRIMARY KEY` (or `BIGSERIAL`, or `GENERATED ALWAYS AS IDENTITY` in modern Postgres)
- `TEXT` for JSON -> `JSONB` native type with indexing support. JSONB validates JSON on insert and enables GIN indexes for fast queries
- `json_extract(col, '$.path')` -> `->>` operator for text extraction, `->` for JSON sub-objects
- `datetime('now')` -> `NOW()` returning `TIMESTAMPTZ`
- `excluded.data` -> `EXCLUDED.data` (Postgres uses uppercase EXCLUDED, though lowercase works too)
- Postgres JSONB also supports containment operators: `data @> '{"role":"admin"}'` is faster than path extraction with an index''',
    ),
    (
        "code-translation/sql-dialects",
        r'''Convert this PostgreSQL full-text search setup to SQLite:

-- Postgres full-text search
ALTER TABLE articles ADD COLUMN search_vector tsvector;

UPDATE articles SET search_vector =
    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(body, '')), 'B');

CREATE INDEX idx_search ON articles USING GIN(search_vector);

CREATE TRIGGER update_search BEFORE INSERT OR UPDATE ON articles
FOR EACH ROW EXECUTE FUNCTION
    tsvector_update_trigger(search_vector, 'pg_catalog.english', title, body);

-- Search query
SELECT title, ts_rank(search_vector, query) AS rank
FROM articles, to_tsquery('english', 'database & optimization') AS query
WHERE search_vector @@ query
ORDER BY rank DESC
LIMIT 10;''',
        r'''<think>
PostgreSQL full-text search to SQLite. These are very different approaches:

Postgres has built-in tsvector/tsquery types with GIN indexes, stemming, ranking, and triggers. SQLite has FTS5 (Full-Text Search) as an extension module, which uses a virtual table approach.

Key differences:
1. Postgres adds a tsvector column to existing table; SQLite creates a separate FTS5 virtual table
2. Postgres uses GIN index; FTS5 has its own internal indexing
3. Postgres supports weighted search (A, B weights for title vs body); FTS5 has a similar feature via column weights in bm25()
4. Postgres trigger auto-updates the search vector; FTS5 needs manual sync or triggers
5. Query syntax: Postgres `to_tsquery('database & optimization')` vs FTS5 `"database AND optimization"` or `"database optimization"` (implicit AND)

I should note that FTS5 is an extension that must be compiled in -- most SQLite distributions include it but it's not guaranteed.
</think>

```sql
-- SQLite FTS5 equivalent

-- Create a virtual FTS5 table (separate from the main table)
CREATE VIRTUAL TABLE articles_fts USING fts5(
    title,
    body,
    content='articles',      -- link to source table
    content_rowid='id'       -- map to articles.id
);

-- Populate the FTS index from existing data
INSERT INTO articles_fts(rowid, title, body)
SELECT id, title, body FROM articles;

-- Keep FTS in sync with triggers
CREATE TRIGGER articles_ai AFTER INSERT ON articles BEGIN
    INSERT INTO articles_fts(rowid, title, body)
    VALUES (new.id, new.title, new.body);
END;

CREATE TRIGGER articles_au AFTER UPDATE ON articles BEGIN
    INSERT INTO articles_fts(articles_fts, rowid, title, body)
    VALUES ('delete', old.id, old.title, old.body);
    INSERT INTO articles_fts(rowid, title, body)
    VALUES (new.id, new.title, new.body);
END;

CREATE TRIGGER articles_ad AFTER DELETE ON articles BEGIN
    INSERT INTO articles_fts(articles_fts, rowid, title, body)
    VALUES ('delete', old.id, old.title, old.body);
END;

-- Search query with ranking
-- bm25() weights: negative = higher importance
SELECT a.title, bm25(articles_fts, -2.0, -1.0) AS rank
FROM articles_fts
JOIN articles a ON a.id = articles_fts.rowid
WHERE articles_fts MATCH 'database AND optimization'
ORDER BY rank
LIMIT 10;
```

Key differences:

- Postgres `tsvector` column on same table -> SQLite FTS5 virtual table (separate structure)
- `GIN` index -> FTS5 has built-in inverted index, no separate CREATE INDEX
- `setweight(..., 'A')` title boosting -> `bm25(fts, -2.0, -1.0)` column weights (more negative = higher weight)
- `to_tsquery('database & optimization')` -> FTS5 `MATCH 'database AND optimization'`
- Postgres single trigger -> SQLite needs three triggers (INSERT, UPDATE, DELETE) with FTS5's special delete syntax
- `ts_rank()` higher is better; FTS5 `bm25()` lower (more negative) is better, hence `ORDER BY rank` without DESC''',
    ),
    (
        "code-translation/sql-dialects",
        r'''Convert this MySQL stored procedure with cursors to PostgreSQL:

DELIMITER //
CREATE PROCEDURE update_prices(IN category_id INT, IN pct DECIMAL(5,2))
BEGIN
    DECLARE done INT DEFAULT 0;
    DECLARE pid INT;
    DECLARE old_price DECIMAL(10,2);
    DECLARE cur CURSOR FOR
        SELECT product_id, price FROM products WHERE cat_id = category_id;
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = 1;

    START TRANSACTION;

    OPEN cur;
    read_loop: LOOP
        FETCH cur INTO pid, old_price;
        IF done THEN
            LEAVE read_loop;
        END IF;

        UPDATE products
        SET price = old_price * (1 + pct / 100),
            updated_at = NOW()
        WHERE product_id = pid;

        INSERT INTO price_audit (product_id, old_price, new_price, changed_at)
        VALUES (pid, old_price, old_price * (1 + pct / 100), NOW());
    END LOOP;
    CLOSE cur;

    COMMIT;
END //
DELIMITER ;''',
        r'''```sql
-- PostgreSQL equivalent
-- Note: In Postgres, this cursor loop is overkill -- a simple
-- UPDATE + INSERT with RETURNING would be more idiomatic.
-- But here is the direct cursor translation first:

CREATE OR REPLACE FUNCTION update_prices(
    p_category_id INT,
    p_pct NUMERIC(5,2)
) RETURNS VOID AS $$
DECLARE
    rec RECORD;
    cur CURSOR FOR
        SELECT product_id, price FROM products
        WHERE cat_id = p_category_id;
BEGIN
    OPEN cur;
    LOOP
        FETCH cur INTO rec;
        EXIT WHEN NOT FOUND;

        UPDATE products
        SET price = rec.price * (1 + p_pct / 100),
            updated_at = NOW()
        WHERE product_id = rec.product_id;

        INSERT INTO price_audit (product_id, old_price, new_price, changed_at)
        VALUES (
            rec.product_id,
            rec.price,
            rec.price * (1 + p_pct / 100),
            NOW()
        );
    END LOOP;
    CLOSE cur;
END;
$$ LANGUAGE plpgsql;

-- Idiomatic Postgres: no cursor needed, use a CTE with UPDATE ... RETURNING
-- WITH updated AS (
--     UPDATE products
--     SET price = price * (1 + p_pct / 100), updated_at = NOW()
--     WHERE cat_id = p_category_id
--     RETURNING product_id, price / (1 + p_pct / 100) AS old_price, price AS new_price
-- )
-- INSERT INTO price_audit (product_id, old_price, new_price, changed_at)
-- SELECT product_id, old_price, new_price, NOW() FROM updated;
```

Key dialect differences:

- `DELIMITER //` not needed in Postgres -- use `$$ ... $$ LANGUAGE plpgsql` block quoting
- MySQL `PROCEDURE` -> Postgres `FUNCTION ... RETURNS VOID` (Postgres procedures exist since v11 but functions are more common)
- `DECLARE done INT; CONTINUE HANDLER FOR NOT FOUND` -> simply `EXIT WHEN NOT FOUND` in the loop
- MySQL `FETCH cur INTO pid, old_price` (separate vars) -> Postgres `FETCH cur INTO rec` (RECORD type)
- `START TRANSACTION / COMMIT` inside procedure -> Postgres functions run inside the caller's transaction by default
- MySQL `IN category_id INT` -> Postgres `p_category_id INT` (prefix to avoid column name collision)''',
    ),
    (
        "code-translation/sql-dialects",
        r'''Translate this PostgreSQL array and LATERAL join query to MySQL:

SELECT
    u.name,
    u.tags,  -- text[] array column
    t.tag
FROM users u,
LATERAL unnest(u.tags) AS t(tag)
WHERE 'premium' = ANY(u.tags);

-- Also translate this array aggregation:
SELECT
    department,
    ARRAY_AGG(name ORDER BY hire_date) AS team_members,
    ARRAY_AGG(DISTINCT skill) FILTER (WHERE skill IS NOT NULL) AS skills
FROM employees
GROUP BY department;''',
        r'''```sql
-- MySQL equivalent
-- MySQL has no native array type. Common workarounds:
-- 1. Comma-separated string with FIND_IN_SET
-- 2. JSON array column with JSON_TABLE
-- Using JSON approach (MySQL 8.0+):

-- Schema change: tags TEXT[] -> tags JSON
-- Store as: '["premium", "verified", "active"]'

-- Unnest equivalent using JSON_TABLE
SELECT
    u.name,
    u.tags,
    t.tag
FROM users u
JOIN JSON_TABLE(
    u.tags,
    '$[*]' COLUMNS (tag VARCHAR(255) PATH '$')
) AS t
WHERE JSON_CONTAINS(u.tags, '"premium"');

-- Array aggregation equivalent
-- MySQL has GROUP_CONCAT instead of ARRAY_AGG
-- and JSON_ARRAYAGG for JSON output

SELECT
    department,
    GROUP_CONCAT(name ORDER BY hire_date SEPARATOR ', ') AS team_members,
    JSON_ARRAYAGG(skill) AS skills
FROM employees
WHERE skill IS NOT NULL
GROUP BY department;

-- Notes:
-- GROUP_CONCAT returns a string, not an array
-- GROUP_CONCAT has a default max length of 1024 bytes
--   (increase with SET GROUP_CONCAT_MAX_LEN = ...)
-- MySQL has no FILTER (WHERE ...) clause on aggregates
--   so we move the condition to the WHERE clause
--   (this changes semantics if you need departments
--   with NULL skills to still appear -- use a subquery then)
-- JSON_ARRAYAGG does not support DISTINCT or ORDER BY
```

Key dialect differences:

- Postgres `text[]` array type -> MySQL `JSON` column storing arrays (no native array type)
- `LATERAL unnest(array_col)` -> `JSON_TABLE(col, '$[*]' COLUMNS (...))` in MySQL 8.0+
- `ANY(array)` containment check -> `JSON_CONTAINS(col, value)`
- `ARRAY_AGG(col ORDER BY ...)` -> `GROUP_CONCAT(col ORDER BY ... SEPARATOR)` for strings, or `JSON_ARRAYAGG(col)` for JSON
- `AGGREGATE(...) FILTER (WHERE cond)` -> no MySQL equivalent; must filter in WHERE or use IF/CASE inside the aggregate
- Postgres arrays support indexing (`tags[1]`), slicing, and operators (`@>`, `&&`); MySQL JSON requires function calls for everything''',
    ),
]
