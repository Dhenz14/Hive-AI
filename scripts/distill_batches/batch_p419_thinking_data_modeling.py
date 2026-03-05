"""Thinking-trace pairs: data modeling, schema design, and database architecture."""

PAIRS = [
    (
        "thinking/data-model-polymorphism",
        "We have a notification system that sends emails, SMS, and push notifications. Each type has different fields (email has subject/body/attachments, SMS has phone/text, push has device_token/title/payload). How should we model this in a relational database?",
        r'''<think>
This is the classic polymorphism-in-SQL problem. Let me evaluate the main approaches.

**The entities:**
- Notification (base): id, user_id, type, status, created_at
- EmailNotification: subject, body, attachments (JSON?), from_address
- SMSNotification: phone_number, message_text, provider_message_id
- PushNotification: device_token, title, body, payload (JSON), badge_count

**Approach 1: Single Table Inheritance (STI)**

One table with ALL columns from ALL types. Unused columns are NULL.

```sql
CREATE TABLE notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    type VARCHAR(20) NOT NULL,  -- 'email', 'sms', 'push'
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    -- Email fields
    subject VARCHAR(255),
    body TEXT,
    attachments JSONB,
    from_address VARCHAR(255),
    -- SMS fields
    phone_number VARCHAR(20),
    message_text VARCHAR(160),
    provider_message_id VARCHAR(100),
    -- Push fields
    device_token VARCHAR(255),
    title VARCHAR(255),
    push_body TEXT,
    payload JSONB,
    badge_count INTEGER
);
```

Pros:
- Simple queries: `SELECT * FROM notifications WHERE user_id = 5`
- No JOINs needed
- Single table to index

Cons:
- Lots of NULL columns (sparse data)
- Can't add NOT NULL constraints for type-specific fields (email's subject can't be NOT NULL because SMS rows won't have it)
- Adding a new notification type means ALTER TABLE adding more columns
- Table gets wide (15+ columns), wastes storage

Works well when: few types, few type-specific fields, querying across types is common.

**Approach 2: Table Per Type (TPT) / Class Table Inheritance**

Base table + one table per type, joined by foreign key.

```sql
CREATE TABLE notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    type VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE email_notifications (
    notification_id INTEGER PRIMARY KEY REFERENCES notifications(id),
    subject VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    attachments JSONB,
    from_address VARCHAR(255) NOT NULL
);

CREATE TABLE sms_notifications (
    notification_id INTEGER PRIMARY KEY REFERENCES notifications(id),
    phone_number VARCHAR(20) NOT NULL,
    message_text VARCHAR(160) NOT NULL,
    provider_message_id VARCHAR(100)
);

CREATE TABLE push_notifications (
    notification_id INTEGER PRIMARY KEY REFERENCES notifications(id),
    device_token VARCHAR(255) NOT NULL,
    title VARCHAR(255) NOT NULL,
    body TEXT,
    payload JSONB,
    badge_count INTEGER DEFAULT 0
);
```

Pros:
- Clean normalization — no NULL columns
- Type-specific NOT NULL constraints work
- Adding a new type = adding a new table (no ALTER TABLE on existing tables)
- Each table is narrow and compact

Cons:
- Queries need JOINs: `SELECT n.*, e.* FROM notifications n JOIN email_notifications e ON ...`
- Querying across types needs UNION or LEFT JOIN all type tables
- More complex INSERT (two tables in a transaction)

Works well when: types have very different fields, data integrity matters, types change over time.

**Approach 3: Table Per Concrete Type**

No base table. Each type gets its own fully independent table.

```sql
CREATE TABLE email_notifications (...all fields including common ones...);
CREATE TABLE sms_notifications (...all fields including common ones...);
CREATE TABLE push_notifications (...all fields including common ones...);
```

Pros:
- Simplest per-type queries (no JOINs)
- Each table is fully independent

Cons:
- Duplicated common columns (user_id, status, created_at in every table)
- Querying "all notifications for user 5" requires UNION across all tables
- Adding a common field means ALTER TABLE on ALL type tables
- Foreign keys from other tables can't reference "a notification" generically

Works well when: types are truly independent, rarely queried together.

**Approach 4: JSON/JSONB type-specific data**

Base table with a JSONB column for type-specific fields.

```sql
CREATE TABLE notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    type VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    data JSONB NOT NULL  -- Type-specific fields
);
```

Pros:
- Single table, no JOINs
- Flexible — add new types without schema changes
- PostgreSQL JSONB supports indexing (GIN index), querying, validation

Cons:
- No SQL-level constraint validation on the JSON structure
- IDE/tooling doesn't see the schema
- Queries on JSON fields are slightly slower than native columns

Works well when: types change frequently, schema flexibility matters, PostgreSQL is available.

**My recommendation for this case:**

Notifications are a good fit for **Approach 2 (Class Table Inheritance)** with a twist:

1. The types have VERY different fields (email has attachments, SMS has phone number, push has device token — no overlap)
2. We need NOT NULL constraints (email without a subject is a bug)
3. We'll query "all notifications for a user" often (the base table handles this without JOINs)
4. We might add new types later (webhook, in-app, slack) — each is a new table

But I'd also consider the **JSONB approach** if the team values simplicity and uses PostgreSQL. With CHECK constraints, we can validate the JSON structure:

```sql
ALTER TABLE notifications ADD CONSTRAINT valid_email_data
CHECK (type != 'email' OR (
    data ? 'subject' AND data ? 'body' AND data ? 'from_address'
));
```

For a notification system specifically, I'll go with Class Table Inheritance because the type-specific fields really are different and the NOT NULL constraints matter (you don't want to accidentally send an email with no subject).
</think>

### Recommendation: Class Table Inheritance

For notifications with very different per-type fields and strong data integrity needs.

### Schema

```sql
-- Base table: common fields, queryable without JOINs
CREATE TABLE notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    type VARCHAR(20) NOT NULL CHECK (type IN ('email', 'sms', 'push')),
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'sent', 'failed', 'delivered')),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    sent_at TIMESTAMP,
    error_message TEXT
);

CREATE INDEX idx_notifications_user ON notifications (user_id, created_at DESC);
CREATE INDEX idx_notifications_pending ON notifications (created_at)
    WHERE status = 'pending';  -- Partial index for the send queue

-- Type-specific tables with their own NOT NULL constraints
CREATE TABLE email_notifications (
    notification_id INTEGER PRIMARY KEY REFERENCES notifications(id) ON DELETE CASCADE,
    from_address VARCHAR(255) NOT NULL DEFAULT 'noreply@example.com',
    subject VARCHAR(255) NOT NULL,       -- Can't be NULL (email without subject = bug)
    body TEXT NOT NULL,
    attachments JSONB DEFAULT '[]'::jsonb
);

CREATE TABLE sms_notifications (
    notification_id INTEGER PRIMARY KEY REFERENCES notifications(id) ON DELETE CASCADE,
    phone_number VARCHAR(20) NOT NULL,   -- Can't be NULL (SMS without phone = bug)
    message_text VARCHAR(160) NOT NULL,
    provider_message_id VARCHAR(100)     -- Filled after sending
);

CREATE TABLE push_notifications (
    notification_id INTEGER PRIMARY KEY REFERENCES notifications(id) ON DELETE CASCADE,
    device_token VARCHAR(255) NOT NULL,
    title VARCHAR(255) NOT NULL,
    body TEXT,
    payload JSONB DEFAULT '{}'::jsonb,
    badge_count INTEGER DEFAULT 0
);
```

### Query patterns

```sql
-- All notifications for a user (no JOINs needed)
SELECT * FROM notifications WHERE user_id = 5 ORDER BY created_at DESC;

-- Email details (single JOIN)
SELECT n.*, e.subject, e.body, e.attachments
FROM notifications n
JOIN email_notifications e ON e.notification_id = n.id
WHERE n.id = 123;

-- Pending notifications to send (uses partial index)
SELECT n.id, n.type
FROM notifications n
WHERE n.status = 'pending'
ORDER BY n.created_at
LIMIT 100;

-- Full details for a specific notification (dynamic JOIN by type)
-- Best done in application code:
```

```python
async def get_notification(notification_id: int) -> dict:
    base = await db.fetch_one(
        "SELECT * FROM notifications WHERE id = $1", notification_id
    )
    if not base:
        return None

    type_table = {
        'email': 'email_notifications',
        'sms': 'sms_notifications',
        'push': 'push_notifications',
    }[base['type']]

    details = await db.fetch_one(
        f"SELECT * FROM {type_table} WHERE notification_id = $1",
        notification_id
    )

    return {**dict(base), **dict(details)}
```

### Creating notifications (transactional)

```python
async def create_email_notification(
    user_id: int, subject: str, body: str,
    from_address: str = 'noreply@example.com',
    attachments: list = None,
) -> int:
    async with db.transaction():
        # Insert base record
        notification_id = await db.fetch_val(
            """INSERT INTO notifications (user_id, type, status)
               VALUES ($1, 'email', 'pending') RETURNING id""",
            user_id
        )
        # Insert type-specific record
        await db.execute(
            """INSERT INTO email_notifications
               (notification_id, from_address, subject, body, attachments)
               VALUES ($1, $2, $3, $4, $5)""",
            notification_id, from_address, subject, body,
            json.dumps(attachments or [])
        )
        return notification_id
```

### Comparison of approaches

| Approach | NULLs | Constraints | JOINs | New types | Best for |
|----------|-------|------------|-------|-----------|----------|
| Single table | Many | Weak | None | ALTER TABLE | Few types, few fields |
| **Class table** | **None** | **Strong** | **1 JOIN** | **New table** | **Different schemas per type** |
| Concrete tables | None | Strong | UNION | New table | Independent types |
| JSONB column | None | CHECK only | None | No DDL | Rapid iteration |'''
    ),
    (
        "thinking/data-model-soft-delete",
        "Our team is debating whether to use soft deletes (setting a `deleted_at` timestamp) or hard deletes (actual DELETE). The main concern is audit compliance — we need to keep records for 7 years. What's the right approach?",
        r'''<think>
This is a common debate with strong opinions on both sides. Let me think through it carefully because the audit requirement changes the answer significantly.

**What soft delete means:**
```sql
-- "Delete" a user
UPDATE users SET deleted_at = NOW() WHERE id = 5;

-- All queries must filter:
SELECT * FROM users WHERE deleted_at IS NULL;
```

**What hard delete means:**
```sql
DELETE FROM users WHERE id = 5;
```

**Arguments for soft delete:**
1. Recovery: can "undelete" by setting deleted_at = NULL
2. Audit trail: deleted records are still in the database
3. Referential integrity: foreign keys to deleted records still resolve
4. Simple to implement

**Arguments against soft delete:**
1. EVERY query must include `WHERE deleted_at IS NULL`. Forget once → show deleted data to users. This is a HUGE source of bugs.
2. Unique constraints break: `UNIQUE(email)` now allows two rows with the same email (one active, one deleted). Need `UNIQUE(email) WHERE deleted_at IS NULL` (partial unique index, not supported in all databases).
3. Database grows forever — 7 years of "deleted" rows bloating the table. Performance degrades.
4. CASCADE behavior is wrong — deleting a user doesn't cascade-soft-delete their posts, orders, etc. You need manual cascade logic.
5. Indexes include deleted rows, making them larger and slower.

**The audit compliance angle:**

The requirement is "keep records for 7 years." But does that mean the records must be in the same table? No! It means you need a historical record of what existed and when it was removed.

An audit log or archive table satisfies compliance better than soft deletes because:
1. The audit log is append-only (can't be tampered with)
2. The audit log captures WHO deleted it and WHY (soft delete only captures WHEN)
3. The active tables stay clean and performant
4. The audit log can be stored in cheaper storage (S3, cold DB)

**My recommendation: Hard delete + audit log + archive table**

Three-layer approach:
1. **Active tables**: only current data. Hard deletes.
2. **Archive tables**: full copy of deleted records with metadata (who, when, why).
3. **Audit log**: every change (create, update, delete) as an append-only event log.

The archive table handles compliance. The audit log handles investigation. The active table handles performance.

For the soft-delete-is-simpler argument: it's only simpler until you have 50 queries and one of them forgets the WHERE clause. Then it's a data leak. The hidden cost of soft delete is maintaining the filter in EVERY query for the lifetime of the codebase.

A middle ground: use database views to hide the filter.

```sql
CREATE VIEW active_users AS
SELECT * FROM users WHERE deleted_at IS NULL;
```

But then you need to make sure everyone uses the view, not the table. And ORMs like Django/SQLAlchemy work with tables, not views, by default.

Actually, the cleanest middle ground in PostgreSQL is Row-Level Security:

```sql
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY active_only ON users
    FOR SELECT
    USING (deleted_at IS NULL);
```

This makes it impossible to accidentally query deleted rows. But it adds complexity and doesn't solve the table bloat issue.

**My final recommendation for this case:**

Given the 7-year audit requirement, the winning approach is:

1. Hard delete from active tables
2. Archive deleted records to a separate `_archive` table (or time-series table)
3. Maintain an audit log for compliance
4. Periodically move old archives to cold storage
</think>

### Recommendation: Hard delete + archive table + audit log

Soft delete creates more problems than it solves, and it doesn't actually satisfy audit compliance well (no who/why, only when).

### The three-layer approach

```
Active Table (users)           → Fast queries, clean data, hard deletes
Archive Table (users_archive)  → Full copy of deleted records + metadata
Audit Log (audit_events)       → Append-only: every create/update/delete
```

### Schema

```sql
-- Active table: clean, only current data
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Archive table: deleted records with context
CREATE TABLE users_archive (
    archive_id SERIAL PRIMARY KEY,
    original_id INTEGER NOT NULL,          -- The original users.id
    email VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL,         -- When the user was created
    deleted_at TIMESTAMP NOT NULL DEFAULT NOW(),  -- When it was deleted
    deleted_by INTEGER REFERENCES users(id),      -- WHO deleted it
    deletion_reason VARCHAR(255),                  -- WHY (compliance)
    original_data JSONB NOT NULL           -- Full snapshot at time of deletion
);

CREATE INDEX idx_archive_original_id ON users_archive (original_id);
CREATE INDEX idx_archive_deleted_at ON users_archive (deleted_at);

-- Audit log: immutable event stream (all changes, all tables)
CREATE TABLE audit_events (
    id BIGSERIAL PRIMARY KEY,
    table_name VARCHAR(100) NOT NULL,
    record_id INTEGER NOT NULL,
    action VARCHAR(10) NOT NULL CHECK (action IN ('INSERT', 'UPDATE', 'DELETE')),
    old_data JSONB,
    new_data JSONB,
    changed_by INTEGER,
    changed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    ip_address INET
);

CREATE INDEX idx_audit_table_record ON audit_events (table_name, record_id);
CREATE INDEX idx_audit_changed_at ON audit_events (changed_at);
```

### Automatic archiving with a trigger

```sql
-- PostgreSQL trigger: auto-archive on DELETE
CREATE OR REPLACE FUNCTION archive_user() RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO users_archive (original_id, email, name, created_at, original_data)
    VALUES (
        OLD.id, OLD.email, OLD.name, OLD.created_at,
        row_to_json(OLD)::jsonb
    );
    RETURN OLD;  -- Allow the DELETE to proceed
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_archive_user
    BEFORE DELETE ON users
    FOR EACH ROW EXECUTE FUNCTION archive_user();

-- Now DELETE just works — archive happens automatically
-- DELETE FROM users WHERE id = 5;
-- → Trigger copies row to users_archive, then deletes from users
```

### Application-level delete with context

```python
async def delete_user(user_id: int, deleted_by: int, reason: str):
    """Delete a user with full audit trail."""
    async with db.transaction():
        # Get the record before deletion
        user = await db.fetch_one("SELECT * FROM users WHERE id = $1", user_id)
        if not user:
            raise NotFoundError('User', user_id)

        # Archive with context (trigger handles the basic archive,
        # this adds who/why)
        await db.execute(
            """UPDATE users_archive
               SET deleted_by = $1, deletion_reason = $2
               WHERE original_id = $3 AND deleted_by IS NULL""",
            deleted_by, reason, user_id
        )
        # Or handle everything in application code instead of trigger

        # Hard delete
        await db.execute("DELETE FROM users WHERE id = $1", user_id)

        # Audit log
        await db.execute(
            """INSERT INTO audit_events
               (table_name, record_id, action, old_data, changed_by)
               VALUES ('users', $1, 'DELETE', $2, $3)""",
            user_id, json.dumps(dict(user)), deleted_by
        )
```

### Why NOT soft delete

| Problem | Impact | Frequency |
|---------|--------|-----------|
| Forgotten WHERE filter | Data leak (show deleted users) | Every new query |
| Broken UNIQUE constraints | `UNIQUE(email)` allows duplicates | Every constraint |
| Table bloat (7 years!) | Slower queries, bigger indexes | Continuous |
| No cascade | Delete user but posts remain "active" | Every FK relation |
| No who/why | Fails detailed audit requirements | Every compliance review |

### Compliance queries on the archive

```sql
-- "Show me everything about user 12345 for the audit"
SELECT 'active' AS state, row_to_json(u) AS data, u.created_at
FROM users u WHERE u.id = 12345
UNION ALL
SELECT 'deleted', original_data, deleted_at
FROM users_archive WHERE original_id = 12345
UNION ALL
SELECT action, COALESCE(new_data, old_data), changed_at
FROM audit_events WHERE table_name = 'users' AND record_id = 12345
ORDER BY created_at;

-- "Purge records older than 7 years" (after retention period)
DELETE FROM users_archive WHERE deleted_at < NOW() - INTERVAL '7 years';
DELETE FROM audit_events WHERE changed_at < NOW() - INTERVAL '7 years';
```

### If you really want soft delete: use it safely

```sql
-- PostgreSQL Row-Level Security makes forgotten filters impossible
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- Default policy: only see non-deleted rows
CREATE POLICY see_active ON users FOR SELECT
    USING (deleted_at IS NULL);

-- Admin policy: see everything (for archive/audit queries)
CREATE POLICY see_all ON users FOR SELECT TO admin_role
    USING (true);
```

This prevents the "forgotten WHERE" bug at the database level. But you still have table bloat and broken unique constraints.'''
    ),
]
