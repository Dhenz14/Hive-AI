"""Phase 4F: Self-Improvement — Quality Assurance (Part 8)

Quality checklists for database advice — ensuring database
recommendations are practical, safe, and performance-aware.
"""

PAIRS = [
    (
        "thinking/auto-qa-database-schema-design",
        r'''What quality checks should I apply when advising on database schema design to ensure my recommendations are practical and won't cause problems at scale?''',
        r'''<think>
Database schema design advice has long-lasting consequences because changing a schema in production is difficult and risky. Bad schema advice can lead to:
1. Performance problems that only appear at scale
2. Data integrity issues (missing constraints, bad normalization)
3. Migration nightmares (changing columns with millions of rows)
4. Application complexity (working around a bad schema)

**Quality dimensions to check:**
- Normalization level (appropriate for the use case)
- Data types (right size, right type)
- Constraints (foreign keys, NOT NULL, CHECK)
- Indexing strategy (for expected query patterns)
- Migration feasibility (can changes be applied safely?)
- Scalability (will this work with 100x the data?)
</think>

**Database Schema Design Quality Checklist**

**Before recommending any schema design:**

**Step 1: Data type verification**
```
□ APPROPRIATE TYPES:
  - IDs: Use UUID or BIGINT, not INT (INT maxes at ~2B)
  - Money: Use DECIMAL/NUMERIC, never FLOAT (rounding errors!)
  - Timestamps: Use TIMESTAMPTZ (timezone-aware), not TIMESTAMP
  - Status/enum: Use CHECK constraints or enum type, not free text
  - Email/URL: Use TEXT with CHECK constraint, not VARCHAR(255)
    (VARCHAR(255) is a MySQL legacy — PostgreSQL doesn't benefit)

□ NOT TOO SMALL:
  INT for IDs → will you exceed 2 billion rows ever?
  VARCHAR(50) for names → will any name be longer?
  Defaults should be generous. Storage is cheap; migrations are expensive.

□ NOT TOO LARGE:
  TEXT for a status field → should be an enum
  JSONB for everything → probably needs structure
  Use the most specific type that fits.
```

**Step 2: Constraint verification**
```
□ NOT NULL: Is every column that must have a value marked NOT NULL?
  Common mistake: forgetting NOT NULL on required fields.
  Later: "Why do we have rows with null email addresses?"

□ FOREIGN KEYS: Are all relationships enforced with FK constraints?
  Common mistake: "We'll enforce it in the application."
  Reality: Application bugs will create orphaned rows.

□ UNIQUE CONSTRAINTS: Are natural keys protected?
  If email should be unique → add UNIQUE constraint.
  If (user_id, product_id) should be unique → add composite unique.

□ CHECK CONSTRAINTS: Are domain rules enforced?
  - price >= 0 (no negative prices)
  - status IN ('active', 'inactive', 'suspended')
  - start_date < end_date

  "But we validate in the app!" → Application bugs happen.
     The database is the last line of defense.

□ DEFAULT VALUES: Are sensible defaults set?
  - created_at DEFAULT NOW()
  - status DEFAULT 'active'
  - is_deleted DEFAULT FALSE
```

**Step 3: Normalization check**
```
□ APPROPRIATE NORMALIZATION:
  Under-normalized (storing data redundantly):
    Orders table with customer_name, customer_email columns
    → When customer updates email, update ALL their orders? No.
    → Use a foreign key to customers table.

  Over-normalized (too many joins needed):
    Address split into street_id, city_id, state_id, country_id
    → 4 JOINs just to show an address? Probably excessive.
    → Store address fields directly (denormalize for read performance).

  Rule of thumb:
    Write-heavy data → normalize (single source of truth)
    Read-heavy data → denormalize (fewer joins, faster reads)
    OLTP → normalize
    Analytics/reporting → denormalize
```

**Step 4: Query pattern alignment**
```
□ INDEXES MATCH EXPECTED QUERIES:
  Think about how the table will be queried BEFORE finalizing schema.

  "We'll query users by email constantly"
    → CREATE INDEX idx_users_email ON users(email);

  "We'll query orders by user and date range"
    → CREATE INDEX idx_orders_user_date ON orders(user_id, created_at);

  "We'll do full-text search on product descriptions"
    → Add a tsvector column + GIN index

□ NO MISSING INDEXES ON FOREIGN KEYS:
  PostgreSQL does NOT auto-create indexes on foreign key columns.
  Every FK column needs an explicit index, or JOINs will be slow.

□ NO EXCESSIVE INDEXES:
  Each index slows down writes. Only index what you query.
  5-8 indexes per table is typical. 20+ is a red flag.
```

**Step 5: Scalability check**
```
□ WILL THIS WORK AT 100x CURRENT SIZE?
  - Table with 1M rows → will it work at 100M?
  - Column with TEXT → will 100M rows of text fit in RAM for indexes?
  - JOIN pattern → will it still perform with large tables?

□ PARTITIONING CONSIDERATION:
  Tables expected to exceed 100M rows → consider partitioning
  (by date, by tenant, by region) from the start.
  Adding partitioning later is painful.

□ ARCHIVAL STRATEGY:
  Is there a plan for old data?
  - Soft delete (is_deleted flag) + periodic archival?
  - Partition by date and drop old partitions?
  - Without a plan, the table grows forever.
```

**The meta-principle:** Schema design decisions are the hardest database decisions to reverse. A bad index can be dropped in seconds. A bad column type requires a migration that might lock the table. A bad normalization decision requires rewriting queries across the entire application. Invest extra time in schema review — it pays back exponentially.'''
    ),
    (
        "thinking/auto-qa-database-query-advice",
        r'''What quality checks should I apply when advising someone on SQL queries to make sure my advice actually improves their performance and doesn't introduce problems?''',
        r'''<think>
SQL query advice is high-stakes because:
1. A bad query can be 1000x slower than a good one
2. Query changes can affect other queries (lock contention, resource usage)
3. Performance depends heavily on data distribution and volume
4. What works on 1K rows may not work on 1M rows

**Common failure modes in SQL advice:**
- Suggesting an index without checking if it already exists
- Optimizing a query that isn't the bottleneck
- Recommending patterns that don't work in the specific database engine
- Ignoring write performance impact of new indexes
- Not considering concurrent access patterns
</think>

**SQL Query Advice Quality Checklist**

**Before giving any query optimization advice:**

**Step 1: Understand the context**
```
□ WHICH DATABASE ENGINE?
  SQL advice varies significantly between engines:
  - PostgreSQL: Use EXPLAIN ANALYZE, supports partial indexes, CTEs are optimized
  - MySQL: Use EXPLAIN, index hints may be needed, CTEs may not optimize well
  - SQLite: Different optimizer, limited concurrent writes

  Don't give PostgreSQL-specific advice for MySQL and vice versa.

□ DATA VOLUME?
  - 1K rows: Almost any query is fast. Don't optimize prematurely.
  - 100K rows: Indexes start to matter.
  - 1M+ rows: Query plan is critical. EXPLAIN is essential.
  - 100M+ rows: Partitioning, materialized views, read replicas.

□ WHAT'S THE ACTUAL PROBLEM?
  "This query is slow" → How slow? What's acceptable?
  A query that takes 500ms might be fine for a nightly report
  but unacceptable for an API endpoint.
```

**Step 2: Verify the diagnosis**
```
□ HAVE THEY RUN EXPLAIN ANALYZE?
  Never optimize without seeing the execution plan.

  Common mistake: Assuming the query is slow because of X
  when EXPLAIN shows it's actually slow because of Y.

  "I think I need an index on user_id"
  → "Run EXPLAIN ANALYZE first. The issue might not be
     user_id — it might be the JOIN or the sort."

□ IS THIS THE ACTUAL BOTTLENECK?
  If the application is slow, is this query the cause?
  Check: Is the query called once per request or in a loop?

  N+1 queries: One query per item in a list
  → The fix isn't optimizing the query; it's reducing query count.
  → Use a JOIN or WHERE id IN (...) instead.
```

**Step 3: Validate the optimization**
```
□ DOES THE INDEX HELP THIS QUERY?
  An index on (a, b) helps:
    WHERE a = 1               ✓ (uses leftmost column)
    WHERE a = 1 AND b = 2     ✓ (uses both columns)
    WHERE b = 2               ✗ (can't use, wrong order!)
    ORDER BY a, b             ✓ (matches index order)
    ORDER BY b, a             ✗ (wrong order)

  Composite index column order matters!

□ DOES THE OPTIMIZATION HURT WRITES?
  Every index slows INSERT/UPDATE/DELETE operations.
  Adding an index to a table with 10K writes/sec → measure the impact.

  "Add indexes on all columns you query" → BAD advice.
  "Add indexes on the specific columns used in your WHERE and JOIN" → GOOD.

□ IS THE QUERY CORRECT (not just fast)?
  Optimizations that change results are bugs, not optimizations.
  Common mistake: removing a JOIN that seems unnecessary but
  actually filters out rows.

  Verify: Does the optimized query return the same results
  as the original for the same data?
```

**Step 4: Common query advice patterns**

```
□ N+1 QUERY DETECTION:
  If you see a query executed inside a loop → flag it.
  Fix: Use a JOIN, subquery, or WHERE IN (...).

  BAD:
    for user in users:
        orders = db.query("SELECT * FROM orders WHERE user_id = %s", user.id)

  GOOD:
    all_orders = db.query("SELECT * FROM orders WHERE user_id IN %s", user_ids)

□ SELECT * WARNING:
  "SELECT *" retrieves all columns, even ones you don't use.
  For wide tables (20+ columns), this wastes I/O and memory.
  Recommend selecting only needed columns for performance-critical queries.

□ PAGINATION ADVICE:
  OFFSET/LIMIT is O(n) — OFFSET 100000 scans 100K rows.
  For large offsets, use cursor-based pagination:
    WHERE id > last_seen_id ORDER BY id LIMIT 20

□ COUNT(*) WARNING:
  COUNT(*) on a large table can be slow (full table scan).
  For approximate counts: use pg_class.reltuples (PostgreSQL)
  or maintain a counter table for exact counts.
```

**Step 5: Safety checks**
```
□ WILL THIS LOCK THE TABLE?
  ALTER TABLE on a large table can lock it for minutes/hours.
  In PostgreSQL, many ALTER TABLE operations are instant
  (adding nullable column, renaming). But adding a NOT NULL
  default or changing type requires a full rewrite.

  Always warn about lock implications for production databases.

□ IS THERE A ROLLBACK PLAN?
  "Add this index" → What if it makes things worse?
  CREATE INDEX CONCURRENTLY (PostgreSQL) allows dropping without downtime.
  Always recommend CONCURRENTLY for production index creation.

□ HAVE THEY TESTED ON REALISTIC DATA?
  Testing on 100 rows doesn't validate performance.
  "Test with production-scale data (or a copy) before deploying."
```

**The meta-principle:** SQL optimization advice without EXPLAIN output is guesswork. Always ask for the execution plan before recommending changes. And always verify that the optimization doesn't change correctness, doesn't hurt write performance unacceptably, and can be safely deployed to production. Fast but wrong or fast but risky is worse than slow but correct and safe.'''
    ),
    (
        "thinking/auto-qa-database-migration-safety",
        r'''What quality checks should I apply when advising on database migrations to ensure they're safe for production and won't cause downtime?''',
        r'''<think>
Database migrations in production are one of the highest-risk operations in software development. A bad migration can:
1. Lock tables for minutes/hours (downtime)
2. Corrupt data (irreversible without backups)
3. Break the application (schema mismatch)
4. Fill up disk space (during rewrite operations)

**Safety dimensions:**
- Lock duration (will it block reads/writes?)
- Reversibility (can we roll back if something goes wrong?)
- Data safety (is data preserved correctly?)
- Application compatibility (does the app work during migration?)
- Performance impact (does it affect running queries?)
</think>

**Database Migration Safety Checklist**

**Before recommending any migration:**

**Step 1: Lock impact assessment**
```
□ WILL THIS LOCK THE TABLE?

  PostgreSQL — generally safe (no lock or brief lock):
    ✓ ADD COLUMN (nullable, no default)
    ✓ ADD COLUMN with DEFAULT (PG 11+: instant, no rewrite)
    ✓ DROP COLUMN (marks invisible, no rewrite)
    ✓ RENAME COLUMN
    ✓ CREATE INDEX CONCURRENTLY
    ✓ ADD CONSTRAINT NOT VALID (validates later)

  PostgreSQL — LOCKS THE TABLE (dangerous):
    ✗ ADD COLUMN with DEFAULT (PG 10 and earlier: full rewrite)
    ✗ ALTER COLUMN TYPE (full rewrite)
    ✗ ADD CONSTRAINT (validates existing data — full scan)
    ✗ CREATE INDEX (without CONCURRENTLY — blocks writes)

  MySQL — generally locks more aggressively:
    ✗ Most ALTER TABLE operations acquire a metadata lock
    Consider using pt-online-schema-change or gh-ost for large tables.

□ HOW LARGE IS THE TABLE?
  < 100K rows: Most operations complete in seconds. Risk is low.
  100K - 10M rows: Careful planning needed. Test timing on staging.
  > 10M rows: Operations may take minutes to hours. Use online
              schema change tools.

□ IS THERE A CONCURRENT ALTERNATIVE?
  Instead of: CREATE INDEX idx ON large_table(col)
  Use: CREATE INDEX CONCURRENTLY idx ON large_table(col)

  Instead of: ALTER TABLE ADD CONSTRAINT fk FOREIGN KEY (col) REFERENCES other(id)
  Use: ALTER TABLE ADD CONSTRAINT fk FOREIGN KEY (col) REFERENCES other(id) NOT VALID;
       ALTER TABLE VALIDATE CONSTRAINT fk;
  (NOT VALID doesn't scan existing rows; VALIDATE scans without blocking writes)
```

**Step 2: Reversibility check**
```
□ CAN THIS MIGRATION BE ROLLED BACK?

  Reversible:
    ADD COLUMN → DROP COLUMN
    CREATE INDEX → DROP INDEX
    ADD CONSTRAINT → DROP CONSTRAINT
    RENAME COLUMN → RENAME back

  Irreversible:
    DROP COLUMN → data is gone
    DROP TABLE → data is gone
    ALTER COLUMN TYPE (with data truncation) → data is modified
    DELETE/UPDATE data → original data is gone

  For irreversible migrations:
    □ Is there a backup taken BEFORE the migration?
    □ Has the migration been tested on a copy of production data?
    □ Is there a written rollback plan (even if partial)?
```

**Step 3: Application compatibility**
```
□ DEPLOY ORDER: Application first or migration first?

  ADDING a column:
    1. Run migration (add column)
    2. Deploy new code (that uses the column)
    → Old code ignores the new column. Safe.

  REMOVING a column:
    1. Deploy new code (that doesn't use the column)
    2. Run migration (remove column)
    → If you drop first, old code crashes. Dangerous.

  RENAMING a column:
    Don't rename directly. Instead:
    1. Add new column
    2. Deploy code that writes to both columns
    3. Backfill new column from old column
    4. Deploy code that reads from new column
    5. Drop old column
    → This is called an "expand and contract" migration.

□ DOES THE APP HANDLE BOTH STATES?
  During a migration, the database is between two states.
  The application must handle both the old and new schema.
  If the app crashes on the intermediate state → you have a
  window of downtime.
```

**Step 4: Data safety**
```
□ DATA TRANSFORMATION: Is data being modified?
  If the migration transforms data (UPDATE, backfill):
  - Test on a copy first
  - Verify row counts before and after
  - Spot-check data values
  - Run in batches (not one giant UPDATE that locks the table)

  Batch update pattern:
    DO $$
    BEGIN
      LOOP
        UPDATE large_table SET new_col = old_col
        WHERE new_col IS NULL
        LIMIT 10000;
        EXIT WHEN NOT FOUND;
        PERFORM pg_sleep(0.1);  -- breathe between batches
      END LOOP;
    END $$;

□ BACKUP: Is a backup available?
  For any destructive migration (DROP, ALTER TYPE, data transformation):
  "Take a backup before running this migration.
   pg_dump -Fc dbname > backup_before_migration.dump"
```

**Step 5: Execution plan**
```
□ TIMING: When should this run?
  Low-risk migrations: Any time
  Locking migrations: During maintenance window / low traffic
  Data transformations: Off-peak hours, with monitoring

□ MONITORING: What to watch during migration?
  - Lock wait times (are queries queuing up?)
  - Table size (is a rewrite filling the disk?)
  - Query performance (are other queries affected?)
  - Application errors (is the app handling the schema change?)

□ ABORT CRITERIA: When to stop?
  - Lock wait exceeds 30 seconds
  - Disk usage exceeds 80%
  - Application error rate spikes
  Define these BEFORE starting the migration.
```

**The meta-principle:** Database migrations in production should be treated like surgery — plan carefully, have a rollback plan, monitor continuously, and have abort criteria defined before you start. Never run an untested migration on production data. Never run a locking migration during peak traffic. And always ask: "what's the worst thing that could happen if this goes wrong?"'''
    ),
    (
        "thinking/auto-qa-database-connection-management",
        r'''What quality checks should I apply when advising on database connection management? Connection issues seem to cause a disproportionate number of production problems.''',
        r'''<think>
Database connection management is one of the most common sources of production issues because:
1. Connections are expensive to create (TCP handshake + auth)
2. Database servers have connection limits
3. Connection leaks are silent until the pool is exhausted
4. Connection timeouts cause cascading failures
5. Wrong pool sizes either waste resources or bottleneck the app

**Common connection problems:**
- "Too many connections" (pool too large, or connections leaked)
- Connection timeouts (pool exhausted, all connections in use)
- Stale connections (connection was valid, server closed it)
- SSL/TLS connection errors (certificate issues)
- DNS resolution failures for database hostname
</think>

**Database Connection Management Quality Checklist**

**Before advising on connection setup:**

**Step 1: Connection pooling basics**
```
□ ARE THEY USING CONNECTION POOLING?
  If not → this is the first recommendation.

  Without pooling:
    Each request: Connect (50ms) → Query (5ms) → Disconnect
    10 requests/sec: 500ms wasted on connections alone

  With pooling:
    Request: Get connection from pool (0.1ms) → Query (5ms) → Return to pool
    10 requests/sec: 1ms on connections

  Every production application needs connection pooling.

□ WHICH POOLER?
  Application-level: SQLAlchemy pool, HikariCP, pgx pool
    Pros: Simple, no extra infrastructure
    Cons: Each app instance has its own pool

  External pooler: PgBouncer, pgcat
    Pros: Shared across all app instances, better connection management
    Cons: Extra infrastructure to manage

  For < 5 app instances: Application-level pooling is fine
  For > 5 app instances: Consider an external pooler
```

**Step 2: Pool size configuration**
```
□ POOL SIZE: Not too big, not too small?

  TOO SMALL (common mistake: pool_size=5 with 50 concurrent requests):
    → Requests queue up waiting for a connection
    → Latency spikes under load
    → Symptom: "Connection pool exhausted" errors

  TOO LARGE (common mistake: pool_size=100 per app instance):
    → 10 instances = 1000 connections to the database
    → Database has max_connections = 100 → crashes
    → Symptom: "Too many connections" errors

  FORMULA:
    pool_size = (number of CPU cores * 2) + number of spinning disks
    Source: PostgreSQL wiki, applies to most databases

    For cloud databases with SSDs: pool_size = CPU cores * 2 to 4

    But also check:
      Total connections = pool_size * number_of_app_instances
      Total connections must be < database max_connections - 10
      (Reserve 10 for admin/monitoring connections)

□ MAX OVERFLOW (for connection bursts):
  Allow temporary connections above pool size for traffic spikes.
  max_overflow = pool_size (double the pool temporarily)
  These extra connections are closed after use, not kept in pool.
```

**Step 3: Timeout configuration**
```
□ CONNECTION TIMEOUT: How long to wait for a connection from the pool?
  Default: Often infinite → request hangs forever if pool is exhausted
  Recommended: 5-10 seconds

  If your p99 query time is 500ms and pool_size is 10,
  a 5-second timeout means requests fail fast rather than
  queueing for minutes.

□ QUERY TIMEOUT: How long can a query run?
  Default: Often infinite → runaway queries hold connections forever
  Recommended: 30 seconds for web requests, longer for background jobs

  SET statement_timeout = '30s';  -- PostgreSQL

  A query running for 5 minutes in production is almost certainly
  a bug, not a legitimate query.

□ IDLE TIMEOUT: When to close idle connections?
  Connections sitting idle waste database resources.
  Close connections idle for more than 10-15 minutes.

  pool_recycle = 900  # SQLAlchemy: close connections older than 15min
```

**Step 4: Health and resilience**
```
□ CONNECTION HEALTH CHECKS:
  Stale connections cause "server closed the connection unexpectedly."

  Solution: Test connections before use:
    pool_pre_ping = True  # SQLAlchemy: tests connection with a SELECT 1
    validationQuery: "SELECT 1"  # HikariCP

  Performance cost: ~1ms per query. Worth it vs. random failures.

□ RETRY ON TRANSIENT FAILURES:
  Network blips happen. A single retry fixes most transient errors.

  Retry pattern:
    try:
        result = execute_query(sql)
    except OperationalError:
        time.sleep(0.1)
        result = execute_query(sql)  # retry once

  Do NOT retry indefinitely. One retry, then fail.

□ CIRCUIT BREAKER FOR DATABASE:
  If the database is down, stop hammering it with connections.
  After 5 consecutive failures: stop trying for 30 seconds.
  Then try one connection. If it works: resume. If not: wait again.
```

**Step 5: Monitoring**
```
□ KEY METRICS TO MONITOR:
  - Pool utilization: (active connections / pool size) × 100%
    > 80% sustained → increase pool size or optimize queries
  - Connection wait time: Time spent waiting for a pool connection
    > 100ms → pool is too small or queries are too slow
  - Active connections on database:
    > 80% of max_connections → reduce pool sizes or add a pooler
  - Connection errors per minute:
    > 0 sustained → investigate immediately

□ ALERTING:
  Alert on:
  - Pool utilization > 90% for 5 minutes
  - Connection errors > 5 per minute
  - Database active connections > 80% of max
  - Average query time > 2x normal
```

**The meta-principle:** Connection management is plumbing — invisible when it works, catastrophic when it fails. The three most common production connection issues are: pool too small (requests queue up), pool too large (database overwhelmed), and missing health checks (stale connections). Set appropriate pool sizes, add timeouts on everything, monitor utilization, and test connection health before use. These four measures prevent 90% of connection-related outages.'''
    ),
    (
        "thinking/auto-qa-database-backup-recovery",
        r'''What quality checks should I apply when advising on database backup and recovery strategies? This seems like an area where bad advice could be catastrophic.''',
        r'''<think>
Backup and recovery is the ultimate high-stakes area because:
1. You only discover backup problems when you need to restore
2. A backup that can't be restored is not a backup
3. Recovery time directly translates to business downtime
4. Data loss can be legally and financially catastrophic

**The fundamental rule:** Untested backups are not backups. If you've never restored from a backup, you don't know if it works.

**Quality dimensions:**
- Backup completeness (does it capture everything needed?)
- Backup frequency (how much data could you lose?)
- Backup testing (can you actually restore?)
- Recovery time (how long does restoration take?)
- Security (are backups encrypted? access-controlled?)
</think>

**Database Backup and Recovery Quality Checklist**

**Before advising on backup strategy:**

**Step 1: Define the requirements**
```
□ RPO (Recovery Point Objective):
  "How much data can you afford to lose?"

  RPO = 24 hours → daily backups are sufficient
  RPO = 1 hour → hourly backups or WAL archiving needed
  RPO = 0 (no data loss) → streaming replication + WAL archiving

  Don't guess. Ask: "If we restored from backup right now,
  how many hours of data loss would be acceptable?"

□ RTO (Recovery Time Objective):
  "How long can you be down?"

  RTO = 4 hours → cold backup restoration is fine
  RTO = 15 minutes → need hot standby with automatic failover
  RTO = 0 → need active-active or immediate failover

  RTO determines whether you need just backups or also
  high-availability (replication, failover).

□ RETENTION:
  "How far back do you need to be able to restore?"

  Common policy:
    - Daily backups: keep 7 days
    - Weekly backups: keep 4 weeks
    - Monthly backups: keep 12 months

  Regulatory requirements may mandate specific retention.
```

**Step 2: Backup completeness**
```
□ WHAT'S INCLUDED IN THE BACKUP?

  Must include:
  - All databases and schemas
  - All tables (including system tables if needed)
  - Stored procedures, functions, triggers
  - User permissions and roles
  - Configuration files (postgresql.conf, pg_hba.conf)
  - Extension installations

  Often forgotten:
  - Sequences (auto-increment values)
  - Large objects (BLOBs)
  - Tablespace locations
  - Replication slots

□ IS THE BACKUP CONSISTENT?
  A backup taken while the database is active must be consistent.

  pg_dump: Consistent by default (uses a snapshot)
  pg_basebackup: Consistent (uses WAL)
  File system copy: NOT consistent unless database is stopped
    or using a filesystem snapshot (ZFS, LVM)

  Never recommend copying data directory files while the
  database is running — you'll get a corrupted backup.
```

**Step 3: Backup testing (CRITICAL)**
```
□ HAS THE BACKUP BEEN RESTORED SUCCESSFULLY?
  This is the single most important check.

  "We have backups" means nothing if you've never tested restoration.

  Test protocol:
  1. Restore backup to a test server (monthly)
  2. Verify row counts match source
  3. Run application tests against restored database
  4. Measure restoration time (for RTO planning)
  5. Document the restoration procedure step by step

  If restoration has never been tested → the backup strategy
  is unverified and should be treated as unreliable.

□ IS THERE A DOCUMENTED RESTORATION PROCEDURE?
  During an incident is the worst time to figure out how to restore.

  Document:
  - Where are backups stored?
  - What credentials are needed to access them?
  - What are the exact commands to restore?
  - How long does restoration typically take?
  - Who is authorized to initiate a restore?
  - What's the verification step after restoration?
```

**Step 4: Backup security**
```
□ ARE BACKUPS ENCRYPTED?
  Database backups contain ALL your data — user credentials,
  PII, financial data. An unencrypted backup is a data breach
  waiting to happen.

  pg_dump | gpg -c --cipher-algo AES256 > backup.sql.gpg

  Or use native encryption in your backup tool.

□ ARE BACKUPS STORED OFF-SITE?
  Backup on the same server as the database → if the server
  dies, both the database AND backup are lost.

  Minimum: Different server / different cloud region
  Better: Different cloud provider
  Best: Cloud storage + local copy (3-2-1 rule)

  3-2-1 rule:
    3 copies of data
    2 different media types
    1 off-site copy

□ ACCESS CONTROL:
  Who can access the backups? Limit access strictly.
  Backups should be as protected as the production database.
```

**Step 5: Monitoring and alerting**
```
□ BACKUP MONITORING:
  Alert on:
  - Backup didn't complete on schedule
  - Backup size is significantly different from previous
    (could indicate data loss or corruption)
  - Backup storage is running low
  - Last successful backup test was more than 30 days ago

□ THE MOST IMPORTANT ALERT:
  "Last successful backup is older than [RPO]"

  If RPO is 1 hour and the last backup is 3 hours old,
  you're already in a potential data loss situation.
  This should be a high-priority alert.
```

**The meta-principle:** A backup strategy is only as good as its last tested restoration. The most common backup failure mode is not "we didn't have backups" — it's "we had backups but couldn't restore them" or "we had backups but they were 3 days old." Test your restores monthly, monitor backup completion daily, and always ask: "if we lost the database right now, how much data would we lose and how long would it take to recover?"'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
