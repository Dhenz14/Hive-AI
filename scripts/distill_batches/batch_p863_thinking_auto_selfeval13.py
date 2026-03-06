"""Phase 4B: Self-Improvement -- Self-Evaluation (Part 13)

Evaluating own data modeling suggestions for correctness and appropriateness.
"""

PAIRS = [
    (
        "thinking/auto-selfeval-datamodel-nosql-for-everything",
        r'''A developer building a financial accounting system asks what database to use. I am about to recommend MongoDB. Let me evaluate whether this is appropriate:

My draft: "Use MongoDB. It's flexible, scales horizontally, and you don't need to define a schema upfront. You can store invoices, transactions, and ledger entries as documents."''',
        r'''<think>
Let me evaluate my database recommendation:

**The context:** Financial accounting system.

**My recommendation:** MongoDB for invoices, transactions, and ledger entries.

**Is this appropriate? THIS IS DANGEROUS ADVICE.**

**Problem 1: Financial data requires ACID transactions**
- Accounting follows double-entry bookkeeping: every debit must have a matching credit
- If a write fails halfway, the books are imbalanced
- MongoDB historically had weak transaction support (multi-document transactions added in 4.0 but with limitations)
- PostgreSQL has had robust ACID transactions for 25+ years

**Problem 2: Financial data is inherently relational**
- Invoices have line items (one-to-many)
- Transactions reference accounts (many-to-one)
- Ledger entries must balance across accounts (cross-document consistency)
- Audit trails require immutable, ordered records with references
- These are JOIN-heavy, consistency-critical operations

**Problem 3: Regulatory and audit requirements**
- Financial systems must maintain an audit trail
- Data must be consistent at all times (not eventually consistent)
- Regulatory audits require querying across accounts, time periods, and transaction types
- SQL is the standard for financial reporting

**Problem 4: "Flexible schema" is a liability for financial data**
- Financial data has a STRICT schema (amounts, currencies, dates, account codes)
- Schema flexibility means an invoice could be missing required fields
- A relational database enforces that every transaction has an amount, date, and account

**What financial systems actually use:**
- PostgreSQL (most common for startups)
- Oracle/SQL Server (enterprise)
- Never MongoDB for core financial data

**Verdict:** Recommending MongoDB for a financial system could lead to data integrity issues, regulatory violations, and incorrect financial reports. Rating: 1/10.
</think>

**Self-evaluation: MongoDB for financial accounting is one of the worst database recommendations possible. Rating: 1/10.**

**Why this is dangerous:**
| Requirement | PostgreSQL | MongoDB |
|-------------|-----------|---------|
| ACID transactions | Full support, battle-tested | Added in 4.0, limitations exist |
| Referential integrity | Foreign keys enforce it | Application must enforce |
| Double-entry balance | CHECK constraints + triggers | Hope and prayer |
| Audit trail | Immutable append, triggers | Manual implementation |
| Financial reporting | SQL aggregation, window functions | Aggregation pipeline (clunkier) |
| Regulatory compliance | Industry standard | Would raise auditor eyebrows |

**What I should recommend instead:**

"For a financial accounting system, use PostgreSQL:

```sql
-- Strict schema enforces data integrity:
CREATE TABLE accounts (
    id SERIAL PRIMARY KEY,
    code VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(20) NOT NULL CHECK (type IN ('asset', 'liability', 'equity', 'revenue', 'expense'))
);

CREATE TABLE transactions (
    id SERIAL PRIMARY KEY,
    description TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by INTEGER NOT NULL REFERENCES users(id)
);

CREATE TABLE ledger_entries (
    id SERIAL PRIMARY KEY,
    transaction_id INTEGER NOT NULL REFERENCES transactions(id),
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    amount_cents BIGINT NOT NULL,  -- Positive = debit, negative = credit
    -- NEVER use float for money!
);

-- Enforce double-entry bookkeeping:
-- Every transaction's entries must sum to zero
CREATE FUNCTION check_balanced_transaction() RETURNS TRIGGER AS $$
BEGIN
    IF (SELECT SUM(amount_cents) FROM ledger_entries
        WHERE transaction_id = NEW.transaction_id) != 0 THEN
        RAISE EXCEPTION 'Transaction is not balanced';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

The database PREVENTS invalid financial data. MongoDB would let it through."

**Self-evaluation lesson:** Match the database to the data requirements, not to personal preference. Financial data demands strict consistency, referential integrity, and ACID transactions -- the exact strengths of relational databases.'''
    ),
    (
        "thinking/auto-selfeval-datamodel-over-normalization",
        r'''A developer shows me their database schema for a blog platform. They have 15 tables for what seems like a simple system. I am about to say the schema looks good because it is well normalized. Let me evaluate whether over-normalization is a problem here:

Their schema includes: posts, post_titles, post_bodies, post_metadata, post_categories, categories, post_tags, tags, tag_categories, authors, author_profiles, author_social_links, comments, comment_authors, comment_metadata.''',
        r'''<think>
Let me evaluate this schema:

**The system:** A blog platform.
**Their schema:** 15 tables.

**Is this well-designed? NO. This is over-normalized.**

**Tables that should NOT be separate:**

1. `post_titles` and `post_bodies` should be columns in `posts`
   - A post always has exactly one title and one body
   - Separating them creates unnecessary JOINs for every query
   - No benefit: you never query titles without posts

2. `post_metadata` should be a JSONB column on `posts`
   - Metadata (word count, read time, SEO fields) is always read with the post
   - Separate table means a JOIN for every page load

3. `author_profiles` should be merged with `authors`
   - Every author has one profile
   - Separate table is a JOIN for every author display

4. `author_social_links` might be a JSONB column on `authors`
   - Social links are always read as a group
   - A separate table is only justified if you query by social platform

5. `comment_authors` and `comment_metadata` should be on `comments`
   - Same issue as posts: 1:1 relationships don't need separate tables

6. `tag_categories` is probably unnecessary
   - Tags categorizing tags is a sign of over-engineering

**Tables that ARE correctly separated:**
- `posts` and `comments` (one-to-many)
- `posts` and `categories` with `post_categories` (many-to-many)
- `posts` and `tags` with `post_tags` (many-to-many)
- `posts` and `authors` (many-to-one)

**Verdict:** About half the tables are unnecessary 1:1 splits that add complexity and slow down queries without any benefit. Rating: 4/10 (for agreeing it looks good).
</think>

**Self-evaluation: Agreeing that 15 tables for a blog is "well normalized" shows I am confusing more tables with better design. Rating: 4/10.**

**What I should recommend instead:**

"Your schema is over-normalized. Let's simplify:

**Current (15 tables):**
```
posts, post_titles, post_bodies, post_metadata,
post_categories, categories, post_tags, tags, tag_categories,
authors, author_profiles, author_social_links,
comments, comment_authors, comment_metadata
```

**Simplified (7 tables):**
```sql
-- Authors (merged profiles and social links)
CREATE TABLE authors (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    bio TEXT,
    avatar_url TEXT,
    social_links JSONB DEFAULT '{}'  -- {"twitter": "...", "github": "..."}
);

-- Posts (merged titles, bodies, metadata)
CREATE TABLE posts (
    id SERIAL PRIMARY KEY,
    author_id INTEGER NOT NULL REFERENCES authors(id),
    title VARCHAR(500) NOT NULL,
    slug VARCHAR(500) UNIQUE NOT NULL,
    body TEXT NOT NULL,
    excerpt TEXT,
    status VARCHAR(20) DEFAULT 'draft',
    published_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}'  -- {word_count, read_time, seo_description}
);

-- Categories
CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL
);

-- Tags
CREATE TABLE tags (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL
);

-- Many-to-many: posts <-> categories
CREATE TABLE post_categories (
    post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
    category_id INTEGER REFERENCES categories(id) ON DELETE CASCADE,
    PRIMARY KEY (post_id, category_id)
);

-- Many-to-many: posts <-> tags
CREATE TABLE post_tags (
    post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
    tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (post_id, tag_id)
);

-- Comments (merged author info and metadata)
CREATE TABLE comments (
    id SERIAL PRIMARY KEY,
    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    author_name VARCHAR(255) NOT NULL,
    author_email VARCHAR(255),
    body TEXT NOT NULL,
    approved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Impact:**
| Metric | 15 tables | 7 tables |
|--------|----------|---------|
| JOINs to load a blog post | 6-8 | 2-3 |
| Query complexity | High | Simple |
| Tables to maintain | 15 | 7 |
| Data integrity | Same | Same (constraints still enforced) |

**The rule:** Separate tables for 1:many and many:many relationships. Keep 1:1 data in the same table (or use JSONB for semi-structured attributes)."

**Self-evaluation lesson:** Normalization is a tool, not a goal. Over-normalization creates unnecessary complexity. The right question is not "can this be a separate table?" but "does this NEED to be a separate table?"'''
    ),
    (
        "thinking/auto-selfeval-datamodel-float-for-money",
        r'''A developer shows me their order model and I notice they are using FLOAT for prices. I am about to suggest switching to DECIMAL. Let me evaluate whether my advice is complete:

My draft: "Don't use FLOAT for money. Use DECIMAL(10,2) instead. Floating point numbers have precision issues that can cause rounding errors in financial calculations."''',
        r'''<think>
Let me evaluate my data modeling recommendation:

**The problem:** Using FLOAT for money.
**My recommendation:** Switch to DECIMAL(10,2).

**Is this correct? PARTIALLY. DECIMAL is better than FLOAT, but there are better approaches.**

**What I got right:**
- FLOAT for money is indeed wrong (0.1 + 0.2 = 0.30000000000000004)
- This causes real bugs in financial calculations
- DECIMAL is a significant improvement

**What I should also mention:**

**Option 1: DECIMAL(10,2)** -- OK but has limitations
```sql
-- Problem: What about currencies with 3 decimal places (Kuwaiti Dinar)?
-- Problem: What about sub-cent calculations (tax rates, discounts)?
-- Problem: What precision do you actually need?

CREATE TABLE orders (
    total DECIMAL(10,2)  -- Max $99,999,999.99
);
```

**Option 2: Integer cents (preferred by many developers)**
```sql
-- Store money as the smallest currency unit (cents)
CREATE TABLE orders (
    total_cents INTEGER  -- $49.99 stored as 4999
);

-- Advantages:
-- No decimal arithmetic issues
-- Faster than DECIMAL
-- Clear and unambiguous
-- Works for all currencies (just change the divisor)
```

**Option 3: BIGINT with known precision**
```sql
-- For very large amounts or sub-cent precision:
CREATE TABLE orders (
    total_microdollars BIGINT  -- $49.99 stored as 49990000
);
```

**I should also mention:**
- The application layer matters too (Python Decimal, not float)
- Display formatting should be separate from storage
- Currency should be stored alongside the amount
- Comparison/sorting works correctly with all three approaches

**Verdict:** My advice is correct but incomplete. I should present the integer cents approach as the preferred option and explain the trade-offs. Rating: 6/10.
</think>

**Self-evaluation: Correct direction but incomplete. I should present integer cents as the preferred approach. Rating: 6/10.**

**What I should recommend instead:**

"FLOAT for money is a critical bug. Here are the proper alternatives:

**Recommended approach: Integer cents**
```sql
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    price_cents INTEGER NOT NULL,      -- $49.99 = 4999
    currency CHAR(3) NOT NULL DEFAULT 'USD'  -- Always store currency!
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    subtotal_cents INTEGER NOT NULL,
    tax_cents INTEGER NOT NULL,
    total_cents INTEGER NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'USD'
);
```

**Why integer cents over DECIMAL:**
| Factor | FLOAT | DECIMAL(10,2) | Integer cents |
|--------|-------|---------------|--------------|
| 0.1 + 0.2 | 0.30000004 | 0.30 | 30 (correct) |
| Performance | Fast | Slow | Fast |
| Sub-cent math | Precision loss | Limited precision | Exact |
| Multi-currency | Ambiguous | Assumed 2 decimals | Explicit |
| Application code | Use Decimal class! | Natural | Simple math |

**Application layer:**
```python
# Python: NEVER use float for money
price = 49.99  # BAD: float

from decimal import Decimal
price = Decimal('49.99')  # OK: string to Decimal

price_cents = 4999  # BEST: integer

# Display:
def format_money(cents, currency='USD'):
    if currency in ('USD', 'EUR', 'GBP'):
        return f'${cents / 100:.2f}'
    elif currency in ('JPY', 'KRW'):  # No decimals
        return f'{cents}'
    elif currency in ('KWD', 'BHD'):  # 3 decimals
        return f'{cents / 1000:.3f}'
```

**The float bug in action:**
```python
# This actually happens:
float_total = sum(0.01 for _ in range(100))
print(float_total)  # 0.9999999999999998 (not 1.00!)

int_total = sum(1 for _ in range(100))
print(int_total)  # 100 (always correct)
print(f'${int_total / 100:.2f}')  # $1.00
```"

**Self-evaluation lesson:** When fixing a critical bug (FLOAT for money), present the best solution (integer cents) with a clear comparison, not just a better-but-not-best alternative (DECIMAL).'''
    ),
    (
        "thinking/auto-selfeval-datamodel-enum-as-string",
        r'''A developer asks how to store status values (pending, active, suspended, deleted) in their database. I am about to recommend using string columns. Let me evaluate this approach:

My draft: "Use a VARCHAR column for status. Store the status as a readable string like 'active' or 'pending'. This makes the data self-documenting when you query the database directly."''',
        r'''<think>
Let me evaluate my recommendation:

**The problem:** How to store enum-like status values.
**My recommendation:** VARCHAR column with string values.

**Is this good advice? IT DEPENDS, but my reasoning is incomplete.**

**Arguments for VARCHAR strings:**
- Self-documenting (readable in raw queries)
- Easy to add new values (just use a new string)
- Works across all databases
- ORM-friendly (maps to Python strings directly)

**Arguments against VARCHAR strings:**
- No constraint on valid values (typo: "actve" instead of "active")
- Larger storage than integer (7 bytes vs 4 bytes per row)
- Slower comparisons (string vs integer)
- Inconsistency risk (some code uses "Active", some "active", some "ACTIVE")

**What I should have recommended:**
There are several approaches, each with trade-offs:

1. VARCHAR with CHECK constraint (my recommendation should include this)
2. Database ENUM type
3. Integer with lookup table
4. Integer with application-level mapping

**What I missed completely:**
- The CHECK constraint that makes VARCHAR safe
- Case sensitivity issues
- The foreign key to a lookup table approach
- PostgreSQL's native ENUM type

**Verdict:** VARCHAR without constraints is a data integrity risk. I need to at minimum add a CHECK constraint or recommend alternatives. Rating: 4/10.
</think>

**Self-evaluation: VARCHAR without constraints is a soft recommendation that will lead to data integrity issues. Rating: 4/10.**

**What I should recommend instead:**

"There are several good approaches. Choose based on your needs:

**Option 1: VARCHAR with CHECK constraint (recommended for most cases)**
```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'active', 'suspended', 'deleted'))
);

-- Adding a new status later:
ALTER TABLE users DROP CONSTRAINT users_status_check;
ALTER TABLE users ADD CONSTRAINT users_status_check
    CHECK (status IN ('pending', 'active', 'suspended', 'deleted', 'archived'));
```
Pro: Readable, constrained, easy to add values.
Con: Altering constraints requires migration.

**Option 2: PostgreSQL ENUM type**
```sql
CREATE TYPE user_status AS ENUM ('pending', 'active', 'suspended', 'deleted');

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    status user_status NOT NULL DEFAULT 'pending'
);

-- Adding a new value (easy):
ALTER TYPE user_status ADD VALUE 'archived';
-- Removing a value: NOT possible without recreating the type (limitation!)
```
Pro: Type-safe, self-documenting, compact storage.
Con: Cannot remove values, PostgreSQL-specific.

**Option 3: Lookup table with foreign key**
```sql
CREATE TABLE user_statuses (
    id SERIAL PRIMARY KEY,
    name VARCHAR(20) UNIQUE NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE
);

INSERT INTO user_statuses (name) VALUES
    ('pending'), ('active'), ('suspended'), ('deleted');

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    status_id INTEGER NOT NULL REFERENCES user_statuses(id)
);
```
Pro: Can add metadata (description, sort order), soft-delete statuses.
Con: Requires JOIN to read status name.

**Decision guide:**
| Scenario | Best option |
|----------|-------------|
| Simple status, rarely changes | VARCHAR + CHECK |
| PostgreSQL, need type safety | ENUM type |
| Status needs metadata (description, color) | Lookup table |
| Many different status-like columns | Lookup table pattern |
| Cross-database compatibility needed | VARCHAR + CHECK |

**In all cases, also define the enum in your application code:**
```python
from enum import Enum

class UserStatus(str, Enum):
    PENDING = 'pending'
    ACTIVE = 'active'
    SUSPENDED = 'suspended'
    DELETED = 'deleted'

# Use the enum in code, never raw strings:
user.status = UserStatus.ACTIVE  # Not user.status = 'active'
```"

**Self-evaluation lesson:** When recommending data types, always consider data integrity. An unconstrained VARCHAR is just a string column -- it does not enforce valid values. The constraint (CHECK, ENUM, or FK) is what makes it a proper enumeration.'''
    ),
    (
        "thinking/auto-selfeval-datamodel-soft-delete",
        r'''A developer asks how to implement "deleting" records while keeping them for audit purposes. I am about to recommend a simple is_deleted boolean column. Let me evaluate whether this is complete:

My draft: "Add an is_deleted boolean column to your table. When a user deletes a record, set is_deleted = true instead of actually deleting it. Then add WHERE is_deleted = false to all your queries."''',
        r'''<think>
Let me evaluate my soft delete recommendation:

**My recommendation:** Add `is_deleted` boolean, filter all queries.

**Is this correct? The basic approach is right but the implementation is dangerously incomplete.**

**Problem 1: "Add WHERE is_deleted = false to all your queries"**
- This means EVERY query must remember to include this filter
- Missing it in ONE query leaks "deleted" data
- As the codebase grows, this becomes increasingly error-prone
- It is a global invariant enforced by developer discipline (fragile)

**Problem 2: Unique constraints break**
```sql
-- User deletes their account (email: alice@example.com)
UPDATE users SET is_deleted = true WHERE email = 'alice@example.com';
-- Now alice wants to re-register with the same email:
INSERT INTO users (email, name) VALUES ('alice@example.com', 'Alice');
-- ERROR: duplicate key value violates unique constraint!
-- The "deleted" row still holds the unique email!
```

**Problem 3: Performance impact**
- Every query scans deleted rows
- If 90% of rows are "deleted", queries are 10x slower
- Index on is_deleted has low selectivity (only 2 values)

**Problem 4: Cascade behavior**
- If a user is soft-deleted, what about their orders, comments, etc.?
- Foreign key ON DELETE CASCADE does not trigger for soft deletes
- Must manually handle cascading soft deletes

**What I should have recommended:**
- Use a deleted_at timestamp instead of boolean (more useful)
- Use a database view or default scope to hide deleted records
- Handle unique constraints
- Consider alternatives (audit table, event sourcing)

**Verdict:** My advice will work for the simple case but will cause bugs in any non-trivial application. Rating: 4/10.
</think>

**Self-evaluation: A simple is_deleted boolean is the naive implementation that breaks in real applications. Rating: 4/10.**

**What I should recommend instead:**

"Soft delete is more nuanced than it appears. Here is a robust implementation:

**Step 1: Use deleted_at timestamp, not boolean**
```sql
ALTER TABLE users ADD COLUMN deleted_at TIMESTAMPTZ DEFAULT NULL;
-- NULL = active, timestamp = when it was deleted
-- This gives you WHEN it was deleted, not just IF
```

**Step 2: Create a view that hides deleted records**
```sql
-- Instead of adding WHERE to every query, create a view:
CREATE VIEW active_users AS
SELECT * FROM users WHERE deleted_at IS NULL;

-- Application queries use the view:
SELECT * FROM active_users WHERE email = 'alice@example.com';
-- Deleted records are automatically excluded

-- Admin/audit queries use the table directly:
SELECT * FROM users WHERE deleted_at IS NOT NULL;  -- All deleted users
```

**Step 3: Fix unique constraints**
```sql
-- Option A: Partial unique index (PostgreSQL)
CREATE UNIQUE INDEX idx_users_email_active ON users(email)
    WHERE deleted_at IS NULL;
-- Only active users must have unique emails
-- Deleted users can share emails with active users

-- Option B: Include deleted_at in unique constraint
CREATE UNIQUE INDEX idx_users_email ON users(email, deleted_at);
-- Each (email, deleted_at) combination is unique
```

**Step 4: Handle cascading**
```python
def soft_delete_user(user_id):
    now = datetime.utcnow()
    with db.transaction():
        db.execute('UPDATE users SET deleted_at = %s WHERE id = %s', (now, user_id))
        db.execute('UPDATE orders SET deleted_at = %s WHERE user_id = %s', (now, user_id))
        db.execute('UPDATE comments SET deleted_at = %s WHERE user_id = %s', (now, user_id))
```

**Step 5: Consider if soft delete is even the right approach**

| Requirement | Best approach |
|-------------|---------------|
| Undo delete (recycle bin) | Soft delete with deleted_at |
| Audit trail (who deleted what when) | Audit log table |
| Legal retention (keep data N years) | Archive table |
| GDPR right to erasure | Hard delete (soft delete violates GDPR!) |
| Analytics on historical data | Event sourcing or archive |

**Important: Soft delete may violate GDPR.** If a user requests data deletion under GDPR, a soft-deleted record that is still in the database is NOT deleted. You may need to anonymize or actually delete the data."

**Self-evaluation lesson:** Soft delete seems simple but has subtle consequences for unique constraints, query filtering, cascade behavior, and legal compliance. Always consider whether soft delete is the right pattern for the specific use case.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
