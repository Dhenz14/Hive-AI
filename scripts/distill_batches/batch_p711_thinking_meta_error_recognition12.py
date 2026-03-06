"""Phase 3A: Metacognition — Error Recognition in Own Output (Part 12)
Scenarios: Wrong tradeoffs, logic errors, under-engineering, performance
"""

PAIRS = [
    (
        "thinking/meta-error-premature-optimization-db-index",
        r'''I added indexes to every column in my users table for fast lookups:

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL,
    first_name VARCHAR(50),
    last_name VARCHAR(50),
    phone VARCHAR(20),
    address TEXT,
    city VARCHAR(50),
    state VARCHAR(2),
    zip VARCHAR(10),
    bio TEXT,
    avatar_url VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_username ON users(username);
CREATE INDEX idx_email ON users(email);
CREATE INDEX idx_first_name ON users(first_name);
CREATE INDEX idx_last_name ON users(last_name);
CREATE INDEX idx_phone ON users(phone);
CREATE INDEX idx_city ON users(city);
CREATE INDEX idx_state ON users(state);
CREATE INDEX idx_zip ON users(zip);
CREATE INDEX idx_created_at ON users(created_at);
CREATE INDEX idx_updated_at ON users(updated_at);
```

More indexes = faster queries, right?''',
        r'''<think>
Let me evaluate this indexing strategy...

Indexes have costs:

1. **Write performance**: Every INSERT, UPDATE, and DELETE must update EVERY index. With 10 indexes, each insert does 10 index updates. For a table with frequent writes (user updates, profile changes), this can be devastating.

2. **Storage**: Each index is a separate B-tree data structure. 10 indexes on a 1-million-row table might double or triple the storage requirement.

3. **Index maintenance**: The database must maintain these B-trees. More indexes = more work for VACUUM, ANALYZE, and background maintenance.

4. **Query planner confusion**: Too many indexes can cause the query planner to choose suboptimal execution plans. It spends more time evaluating index options.

Now, which of these indexes are actually useful?

- `idx_username` — likely used for login lookups. ✓ Should be UNIQUE
- `idx_email` — likely used for login/registration. ✓ Should be UNIQUE
- `idx_first_name` — when would you query by first_name alone? Maybe for search, but LIKE '%john%' can't use a B-tree index anyway
- `idx_last_name` — same problem
- `idx_phone` — maybe for duplicate checking, but rare
- `idx_city`, `idx_state`, `idx_zip` — rarely queried alone. Maybe a composite index for geo queries
- `idx_created_at` — useful for sorting recent users
- `idx_updated_at` — rarely needed independently

Out of 10 indexes, maybe 3 are useful (username, email, created_at). The rest cost write performance without benefiting reads.

My error: I treated indexes as "free" optimizations with no downside. In reality, each index is a tradeoff: faster reads on that column vs. slower writes on the whole table.
</think>

**More indexes does NOT mean faster. Each index slows down writes and uses storage. Most of these indexes will never be used.**

### The costs of 10 indexes
```
INSERT INTO users (...) VALUES (...):
  1. Insert row into table    → 1 operation
  2. Update idx_username      → 1 B-tree insert
  3. Update idx_email         → 1 B-tree insert
  4. Update idx_first_name    → 1 B-tree insert
  5. Update idx_last_name     → 1 B-tree insert
  6. ... (6 more indexes)
  Total: 11 operations instead of 1!
```

### Which indexes are actually useful?

| Index | Used for | Verdict |
|-------|----------|---------|
| username | Login, unique check | ✓ UNIQUE index |
| email | Login, unique check | ✓ UNIQUE index |
| first_name | Search? LIKE won't use it | ✗ Remove |
| last_name | Search? LIKE won't use it | ✗ Remove |
| phone | Rare lookups | ✗ Remove |
| city, state, zip | Geo queries? | Maybe composite |
| created_at | Sort recent users | ✓ Keep |
| updated_at | Rarely queried alone | ✗ Remove |

### Right approach: index based on actual queries
```sql
-- Only indexes that match real query patterns:
CREATE UNIQUE INDEX idx_username ON users(username);
CREATE UNIQUE INDEX idx_email ON users(email);
CREATE INDEX idx_created_at ON users(created_at DESC);

-- Add later ONLY if you have queries that need them:
-- EXPLAIN ANALYZE your slow queries first!
```

### How to find which indexes to add
```sql
-- PostgreSQL: find slow queries
SELECT query, calls, mean_time
FROM pg_stat_statements
ORDER BY mean_time DESC LIMIT 20;

-- Check if existing indexes are used
SELECT indexrelname, idx_scan
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY idx_scan ASC;  -- indexes with 0 scans are wasted
```

### The meta-lesson
Indexes are a tradeoff, not a free lunch. Add indexes based on actual query patterns (EXPLAIN ANALYZE), not speculation. Start with the minimum (primary key + unique constraints), monitor for slow queries, and add indexes surgically. Remove unused indexes — they cost writes without benefiting reads.'''
    ),
    (
        "thinking/meta-error-logic-string-comparison-version",
        r'''I wrote this version comparison function:

```python
def is_newer(version_a, version_b):
    """Return True if version_a is newer than version_b."""
    return version_a > version_b

# Tests
print(is_newer("1.2.0", "1.1.0"))   # True ✓
print(is_newer("2.0.0", "1.9.0"))   # True ✓
print(is_newer("1.10.0", "1.9.0"))  # ???
```

String comparison works for version numbers, right?''',
        r'''<think>
Let me trace through the string comparison...

Python compares strings lexicographically (character by character):

"1.2.0" > "1.1.0": Compare '1'='1', '.'='.', '2'>'1' → True ✓
"2.0.0" > "1.9.0": Compare '2'>'1' → True ✓
"1.10.0" > "1.9.0": Compare '1'='1', '.'='.', '1'<'9' → False!

WRONG! Version 1.10.0 IS newer than 1.9.0, but string comparison says 1.10.0 < 1.9.0 because the character '1' < '9'.

This is because string comparison compares character by character, not number by number. "10" < "9" as strings because '1' < '9'.

This is a classic bug that works for single-digit version components but fails for double-digit ones. It would also fail for:
- "1.2.10" vs "1.2.9" → says 1.2.10 < 1.2.9
- "10.0.0" vs "9.0.0" → says 10.0.0 < 9.0.0

The fix: split by dots, convert to integers, compare as tuples.
</think>

**String comparison fails when version components exceed single digits: `"1.10.0" < "1.9.0"` because `'1' < '9'`.**

### The bug
```python
"1.10.0" > "1.9.0"   # False! (compares '1' vs '9', not 10 vs 9)
"1.2.10" > "1.2.9"   # False! (same problem)
"10.0.0" > "9.0.0"   # False! ('1' < '9')
```

String comparison is lexicographic (character by character), not numeric.

### Fix: compare as integer tuples
```python
def parse_version(version_str):
    return tuple(int(x) for x in version_str.split('.'))

def is_newer(version_a, version_b):
    return parse_version(version_a) > parse_version(version_b)

# Now correct:
is_newer("1.10.0", "1.9.0")   # True ✓ — (1,10,0) > (1,9,0)
is_newer("10.0.0", "9.0.0")   # True ✓ — (10,0,0) > (9,0,0)
```

### Or use the standard library
```python
from packaging.version import Version

Version("1.10.0") > Version("1.9.0")  # True
# Also handles: pre-releases, dev versions, etc.
```

### The meta-lesson
Strings that LOOK like numbers don't BEHAVE like numbers when compared. Any time you compare version numbers, IP addresses, dates-as-strings, or any other "numbers encoded as text," convert to a numeric representation first. String comparison only works for fixed-width zero-padded formats (like ISO dates: "2024-01-15" < "2024-02-01").'''
    ),
    (
        "thinking/meta-error-missing-input-validation-api",
        r'''I wrote this API endpoint for creating a new product:

```python
@app.post("/api/products")
async def create_product(data: dict):
    product = Product(
        name=data["name"],
        price=data["price"],
        quantity=data["quantity"],
        description=data.get("description", "")
    )
    db.add(product)
    db.commit()
    return {"id": product.id}
```

Clean and simple. Any concerns?''',
        r'''<think>
Let me think about what could go wrong with this endpoint...

1. **No input validation**: The endpoint accepts ANY dict. What if:
   - `data["name"]` is an empty string? A 10,000 character string? Contains HTML/scripts?
   - `data["price"]` is negative? Zero? A string? A list? `float('inf')`?
   - `data["quantity"]` is -100? 999999999? A float like 1.5?
   - What if `data` doesn't have "name" at all? → KeyError → 500 Internal Server Error (ugly)

2. **No authentication**: Anyone can create products. No `Depends(get_current_user)` or `Depends(require_admin)`.

3. **No rate limiting**: An attacker can flood the database with millions of fake products.

4. **KeyError produces 500**: If `data["name"]` is missing, the server returns a 500 error instead of a 400 with a useful message. This looks like a server bug to the client.

5. **Extra fields silently ignored**: If someone sends `{"name": "X", "price": 10, "quantity": 5, "is_admin": true}`, the extra fields are ignored, but this could be an attack vector if the Product model has additional columns.

6. **SQL injection via ORM?**: SQLAlchemy parameterizes queries, so this is safe from SQL injection. ✓

7. **Type confusion**: `data["price"]` could be a string "free" or a negative number. If the database column is DECIMAL and receives a string, the ORM might crash with an IntegrityError.

The core issue: accepting raw `dict` with no validation is essentially trusting all user input. This is the #1 OWASP vulnerability category.
</think>

**No input validation, no authentication, and KeyErrors produce unhelpful 500 errors.**

### What can go wrong
```python
# Missing fields → 500 Internal Server Error
POST {"price": 10}  # KeyError: 'name'

# Wrong types → database error or data corruption
POST {"name": 123, "price": "free", "quantity": -5}

# Malicious values
POST {"name": "<script>alert('xss')</script>", "price": -0.01, "quantity": 999999}

# Injection via extra fields
POST {"name": "x", "price": 1, "quantity": 1, "id": 1}  # overwrite existing?
```

### Fix: use Pydantic validation
```python
from pydantic import BaseModel, Field, validator

class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    price: float = Field(gt=0, le=999999.99)
    quantity: int = Field(ge=0, le=100000)
    description: str = Field(default="", max_length=5000)

    @validator('name')
    def sanitize_name(cls, v):
        return v.strip()

    @validator('price')
    def round_price(cls, v):
        return round(v, 2)

@app.post("/api/products")
async def create_product(
    data: ProductCreate,
    current_user: User = Depends(require_admin)  # auth!
):
    product = Product(**data.dict())
    db.add(product)
    db.commit()
    return {"id": product.id}
```

### What Pydantic gives you for free
```python
POST {"price": "free"}
# → 422: "value is not a valid float"

POST {"name": "", "price": 10, "quantity": 5}
# → 422: "ensure this value has at least 1 characters"

POST {"name": "Widget", "price": -5, "quantity": 1}
# → 422: "ensure this value is greater than 0"
```

### The meta-lesson
Never accept raw `dict` from user input. Use a schema (Pydantic, marshmallow, dataclass) that defines expected types, constraints, and required vs optional fields. The schema serves as documentation, validation, and security boundary all in one.'''
    ),
    (
        "thinking/meta-error-orm-update-race",
        r'''I wrote this endpoint to increment a product's view count:

```python
@app.post("/api/products/{product_id}/view")
def track_view(product_id: int):
    product = db.query(Product).get(product_id)
    product.view_count += 1
    db.commit()
    return {"views": product.view_count}
```

Simple counter increment. Any issues?''',
        r'''<think>
Let me trace what happens with concurrent requests...

Thread A: reads product.view_count = 100
Thread B: reads product.view_count = 100 (concurrent!)
Thread A: sets view_count = 100 + 1 = 101, commits
Thread B: sets view_count = 100 + 1 = 101, commits

Result: view_count = 101, but TWO views were tracked. Lost update!

This is the classic read-modify-write race condition. The application reads the value, adds 1 in Python, then writes it back. Between the read and write, another request can read the stale value.

This is often called a "lost update" or "write skew" in database terminology.

The fix: use an atomic SQL UPDATE instead of read-modify-write:
```sql
UPDATE products SET view_count = view_count + 1 WHERE id = ?
```

This is atomic — the database handles the increment in a single operation, no race window.

In SQLAlchemy:
```python
db.query(Product).filter(Product.id == product_id).update(
    {Product.view_count: Product.view_count + 1}
)
```

Or use `F()` expressions in Django:
```python
Product.objects.filter(id=product_id).update(view_count=F('view_count') + 1)
```

Other options:
- SELECT FOR UPDATE (pessimistic locking)
- Optimistic locking with version column
- Use Redis INCR for high-frequency counters
</think>

**This is a lost-update race condition. Concurrent requests read the same count, both increment by 1, and one update is lost.**

### The race
```
Thread A: SELECT view_count → 100
Thread B: SELECT view_count → 100
Thread A: UPDATE view_count = 101  ✓
Thread B: UPDATE view_count = 101  ✗ (should be 102!)
```

Two views tracked, but count only increased by 1.

### Fix: atomic SQL increment
```python
@app.post("/api/products/{product_id}/view")
def track_view(product_id: int):
    # Atomic increment — no read-modify-write gap
    db.query(Product).filter(Product.id == product_id).update(
        {Product.view_count: Product.view_count + 1}
    )
    db.commit()

    product = db.query(Product).get(product_id)
    return {"views": product.view_count}
```

This generates: `UPDATE products SET view_count = view_count + 1 WHERE id = ?`

The increment happens inside the database engine — atomic and race-free.

### For high-frequency counters, use Redis
```python
import redis
r = redis.Redis()

@app.post("/api/products/{product_id}/view")
def track_view(product_id: int):
    count = r.incr(f"views:{product_id}")  # atomic, ~100K ops/sec
    return {"views": count}

# Periodically sync to database
def sync_views():
    for key in r.scan_iter("views:*"):
        product_id = key.decode().split(":")[1]
        count = int(r.getset(key, 0) or 0)
        db.execute(
            "UPDATE products SET view_count = view_count + %s WHERE id = %s",
            (count, product_id)
        )
```

### The meta-lesson
Any time you see `read → modify in application code → write back`, there's a race condition window between read and write. The fix is always to push the modification into the data store: `UPDATE ... SET x = x + 1` (SQL), `INCR` (Redis), `atomicAdd` (MongoDB). Never read a value into application code just to increment it and write it back.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
