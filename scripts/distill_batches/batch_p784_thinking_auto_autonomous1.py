"""Phase 4E: Self-Improvement — Autonomous Improvement (Part 1)"""

PAIRS = [
    (
        "thinking/auto-autonomous-refactor-readability",
        r'''I just wrote this Python function for processing user orders:

def proc(d, t, u):
    r = []
    for i in d:
        if i['type'] == t and i['uid'] == u:
            if i['status'] != 'cancelled' and i['total'] > 0:
                r.append({'id': i['id'], 'total': i['total'], 'date': i['created']})
    r.sort(key=lambda x: x['date'], reverse=True)
    return r

It works, but let me autonomously improve it before I present it.''',
        r'''<think>
Let me critically review my own output before presenting it. I need to check:
1. Naming — are the variable names meaningful?
2. Structure — can I reduce nesting?
3. Type hints — are they present?
4. Documentation — is the purpose clear?
5. Pythonic idioms — am I using the language well?

Issues I spot:
- `proc`, `d`, `t`, `u`, `r`, `i` are all cryptic single-letter names
- Three levels of nesting when I could combine conditions or use a comprehension
- No type hints, no docstring
- The return type is implicit — caller has no idea what shape to expect
- I'm building a list with append inside a loop — a list comprehension would be cleaner
- No edge case handling for missing keys

Let me fix all of these systematically.
</think>

I reviewed my own function and found several problems. Here is the improved version with explanations:

**Before (my original):**
```python
def proc(d, t, u):
    r = []
    for i in d:
        if i['type'] == t and i['uid'] == u:
            if i['status'] != 'cancelled' and i['total'] > 0:
                r.append({'id': i['id'], 'total': i['total'], 'date': i['created']})
    r.sort(key=lambda x: x['date'], reverse=True)
    return r
```

**After (autonomously improved):**
```python
from typing import TypedDict

class OrderSummary(TypedDict):
    id: str
    total: float
    date: str

def get_active_orders(
    orders: list[dict],
    order_type: str,
    user_id: str,
) -> list[OrderSummary]:
    """Return non-cancelled orders for a user, sorted newest first."""
    active = [
        OrderSummary(id=order["id"], total=order["total"], date=order["created"])
        for order in orders
        if order["type"] == order_type
        and order["uid"] == user_id
        and order["status"] != "cancelled"
        and order["total"] > 0
    ]
    return sorted(active, key=lambda o: o["date"], reverse=True)
```

**What I changed and why:**

1. **Renamed `proc` to `get_active_orders`** — the function name now describes what it does.
2. **Replaced single-letter params** — `d` became `orders`, `t` became `order_type`, `u` became `user_id`.
3. **Added type hints and a `TypedDict`** — callers now know the exact shape of returned data.
4. **Added a docstring** — one line explaining the purpose and sort order.
5. **Collapsed nested `if` into a list comprehension** — reduced nesting from 3 levels to 1, combined conditions with `and`.
6. **Used `sorted()` instead of in-place `.sort()`** — avoids mutating a local variable before returning, making the data flow clearer.

This is an example of autonomous self-review: I wrote the first version to get the logic right, then immediately reviewed it for readability before anyone asked me to.'''
    ),
    (
        "thinking/auto-autonomous-query-optimization",
        r'''I generated this SQL query for finding users who placed orders in the last 30 days along with their total spend:

SELECT u.name, u.email, SUM(o.amount) as total_spend
FROM users u, orders o
WHERE u.id = o.user_id
AND o.created_at > NOW() - INTERVAL '30 days'
AND o.status IN ('completed', 'shipped')
GROUP BY u.name, u.email
ORDER BY total_spend DESC;

Let me check it for performance issues before presenting.''',
        r'''<think>
Let me review my own query before presenting it. Performance checklist:
1. Join syntax — am I using implicit joins? That's outdated and less clear.
2. Index usage — will the WHERE clauses hit indexes?
3. GROUP BY — am I grouping on non-indexed text columns?
4. SELECT — am I pulling unnecessary data?
5. Correctness — could grouping by name/email produce wrong results if two users share a name?

Issues found:
- Implicit join (`FROM users u, orders o WHERE u.id = o.user_id`) — should use explicit JOIN
- Grouping by `u.name, u.email` instead of `u.id` — if two users share a name, their spend merges incorrectly
- No index hint considerations for `o.created_at` and `o.status`
- `NOW()` is evaluated per-row in some databases; should use a parameter or CTE
- Missing LIMIT — could return millions of rows
</think>

I found several issues in my own query. Here is the corrected version:

**Before (my original):**
```sql
SELECT u.name, u.email, SUM(o.amount) as total_spend
FROM users u, orders o
WHERE u.id = o.user_id
AND o.created_at > NOW() - INTERVAL '30 days'
AND o.status IN ('completed', 'shipped')
GROUP BY u.name, u.email
ORDER BY total_spend DESC;
```

**After (autonomously improved):**
```sql
SELECT u.id, u.name, u.email, SUM(o.amount) AS total_spend
FROM orders o
JOIN users u ON u.id = o.user_id
WHERE o.created_at > NOW() - INTERVAL '30 days'
  AND o.status IN ('completed', 'shipped')
GROUP BY u.id, u.name, u.email
ORDER BY total_spend DESC
LIMIT 100;
```

**Recommended index:**
```sql
CREATE INDEX idx_orders_recent_active
ON orders (created_at, status)
INCLUDE (user_id, amount);
```

**What I fixed:**

1. **Explicit JOIN** — replaced the implicit comma-join with `JOIN ... ON`. This is clearer and prevents accidental cross-joins.
2. **GROUP BY u.id** — two users named "Jane Smith" would have had their spend merged. Grouping by primary key `u.id` ensures correctness, with `name` and `email` kept for display.
3. **Added LIMIT 100** — without a limit, a table with millions of users returns an unbounded result set. The caller can paginate.
4. **Leading table is `orders`** — starting FROM the filtered table helps the planner apply the date filter early.
5. **Covering index suggestion** — the composite index on `(created_at, status)` with `INCLUDE (user_id, amount)` lets the query satisfy the WHERE, JOIN, and SUM without touching the heap.

This self-review caught a correctness bug (the GROUP BY issue) and two performance problems before the query reached production.'''
    ),
    (
        "thinking/auto-autonomous-error-handling-completeness",
        r'''I wrote error handling for a file upload endpoint:

@app.post("/upload")
async def upload_file(file: UploadFile):
    try:
        contents = await file.read()
        path = f"/uploads/{file.filename}"
        with open(path, "wb") as f:
            f.write(contents)
        return {"status": "ok", "path": path}
    except IOError:
        raise HTTPException(status_code=500, detail="Failed to save file")

Let me check if I covered all failure modes before presenting this.''',
        r'''<think>
Let me enumerate every failure mode for a file upload endpoint:
1. File too large — could exhaust memory with `file.read()`
2. Invalid/malicious filename — path traversal via `../../etc/passwd`
3. Disk full — IOError is caught but the message is generic
4. File type validation — no check on content type or extension
5. Empty file — should we accept zero-byte uploads?
6. Concurrent writes — two uploads with the same filename race
7. Filename encoding — non-ASCII or null bytes in filename
8. Read timeout — slow client could hold the connection

My original code only catches IOError. That is woefully incomplete. I need to address at least the critical security and reliability issues.
</think>

My error handling was dangerously incomplete. Here is the improved version:

**Before (my original):** Only caught `IOError` — missed 7 other failure modes.

**After (autonomously hardened):**
```python
import os
import uuid
from pathlib import Path

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".csv"}
UPLOAD_DIR = Path("/uploads")

@app.post("/upload")
async def upload_file(file: UploadFile):
    # 1. Validate filename exists
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    # 2. Check extension whitelist
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"File type '{ext}' not allowed")

    # 3. Read with size limit (stream in chunks)
    chunks = []
    total = 0
    while chunk := await file.read(8192):
        total += len(chunk)
        if total > MAX_FILE_SIZE:
            raise HTTPException(413, "File exceeds 10 MB limit")
        chunks.append(chunk)
    contents = b"".join(chunks)

    # 4. Reject empty files
    if total == 0:
        raise HTTPException(400, "Empty file")

    # 5. Generate safe filename (prevent path traversal + collisions)
    safe_name = f"{uuid.uuid4().hex}{ext}"
    dest = UPLOAD_DIR / safe_name

    # 6. Write to disk
    try:
        dest.write_bytes(contents)
    except OSError as exc:
        raise HTTPException(500, f"Storage error: {exc.strerror}")

    return {"status": "ok", "path": str(dest), "size": total}
```

**Failure modes now covered:**

| # | Failure Mode | Fix |
|---|---|---|
| 1 | Memory exhaustion from large file | Stream in 8 KB chunks, enforce 10 MB cap |
| 2 | Path traversal (`../../etc/passwd`) | UUID-based filename ignores user input |
| 3 | Dangerous file types | Extension whitelist |
| 4 | Empty uploads | Explicit zero-byte check |
| 5 | Filename collisions | UUID guarantees uniqueness |
| 6 | Disk full / permission errors | `OSError` catch with specific message |
| 7 | Missing filename | Explicit validation |

This autonomous review turned a single-catch handler into defense-in-depth covering security, validation, and reliability.'''
    ),
    (
        "thinking/auto-autonomous-data-structure-review",
        r'''I suggested using a list of dictionaries to store user sessions:

sessions = [
    {"session_id": "abc", "user_id": 1, "created": "2025-01-01", "data": {...}},
    {"session_id": "def", "user_id": 1, "created": "2025-01-02", "data": {...}},
    {"session_id": "ghi", "user_id": 2, "created": "2025-01-01", "data": {...}},
]

The access patterns are: look up session by ID, find all sessions for a user, and delete expired sessions. Let me verify this is the right structure.''',
        r'''<think>
Let me analyze each access pattern against my chosen data structure:

1. Look up by session_id — requires O(n) linear scan through the list. Bad.
2. Find all sessions for a user — also O(n) scan. Bad for frequent use.
3. Delete expired sessions — O(n) scan plus O(n) list rebuild. Acceptable but not great.

A list of dicts is the worst choice for lookup-by-key patterns. I should have used:
- A dict keyed by session_id for O(1) lookup
- A secondary index (dict of lists) keyed by user_id for O(1) user lookups
- Possibly a sorted structure by creation time for expiry sweeps

Let me redesign this properly.
</think>

My original suggestion was wrong for the stated access patterns. Here is the corrected design:

**Before (my original):**
```python
# O(n) for every lookup — bad for all three access patterns
sessions = [
    {"session_id": "abc", "user_id": 1, "created": "...", "data": {}},
    ...
]
```

**After (autonomously redesigned):**
```python
from dataclasses import dataclass, field
from collections import defaultdict

@dataclass
class Session:
    session_id: str
    user_id: int
    created: float  # timestamp for easy comparison
    data: dict = field(default_factory=dict)

class SessionStore:
    def __init__(self):
        self._by_id: dict[str, Session] = {}
        self._by_user: dict[int, set[str]] = defaultdict(set)

    def add(self, session: Session):
        self._by_id[session.session_id] = session
        self._by_user[session.user_id].add(session.session_id)

    def get(self, session_id: str) -> Session | None:
        return self._by_id.get(session_id)          # O(1)

    def get_user_sessions(self, user_id: int) -> list[Session]:
        ids = self._by_user.get(user_id, set())
        return [self._by_id[sid] for sid in ids]     # O(k), k = user's sessions

    def delete_expired(self, cutoff: float) -> int:
        expired = [s for s in self._by_id.values() if s.created < cutoff]
        for s in expired:
            del self._by_id[s.session_id]
            self._by_user[s.user_id].discard(s.session_id)
        return len(expired)
```

**Complexity comparison:**

| Operation | List of dicts | SessionStore |
|---|---|---|
| Lookup by ID | O(n) | O(1) |
| User's sessions | O(n) | O(k) |
| Delete expired | O(n) + rebuild | O(n) scan + O(e) deletes |
| Memory | 1x | ~1.3x (secondary index) |

The memory overhead of the secondary index (`_by_user`) is a set of string references — negligible compared to the session data itself.

**Key lesson from this self-review:** I defaulted to the simplest data structure (list of dicts) without considering the access patterns. The right approach is to start from the operations, then choose the structure. Two dictionary-based indexes give O(1) for the two most frequent operations at trivial memory cost.'''
    ),
    (
        "thinking/auto-autonomous-test-quality-review",
        r'''I just wrote tests for a discount calculator:

def test_discount():
    assert calculate_discount(100, 10) == 90
    assert calculate_discount(50, 0) == 50
    assert calculate_discount(200, 50) == 100

def test_no_discount():
    assert calculate_discount(100, 0) == 100

Let me check if these tests actually test the right things.''',
        r'''<think>
Let me evaluate my tests against a test quality checklist:
1. Edge cases — do I test boundaries? No: negative prices, negative discounts, 100% discount, discount > price.
2. Floating point — do I test decimal amounts? No: all integers.
3. Error cases — do I test invalid inputs? No: what happens with None, strings, negative values?
4. Test names — are they descriptive? "test_discount" tells me nothing about what scenario it covers.
5. Redundancy — `test_no_discount` duplicates the second assertion in `test_discount`.
6. Independence — the tests are independent, good.
7. Assertions — I only test the happy path. No tests for the unhappy path.

My tests would pass for a function that simply does `price - (price * discount / 100)` but also for a buggy function that accidentally works for these specific values. I need more diverse inputs.
</think>

My tests were superficial. They only covered the happy path with round numbers. Here is the improved test suite:

**Before (my original):** 4 assertions, all happy-path integers, one redundant.

**After (autonomously improved):**
```python
import pytest
from decimal import Decimal

class TestCalculateDiscount:
    """Tests for calculate_discount(price, discount_percent)."""

    # --- Happy path ---
    def test_ten_percent_off_100(self):
        assert calculate_discount(100, 10) == 90.0

    def test_fifty_percent_off_200(self):
        assert calculate_discount(200, 50) == 100.0

    def test_zero_discount_returns_original(self):
        assert calculate_discount(75.50, 0) == 75.50

    def test_full_discount_returns_zero(self):
        assert calculate_discount(100, 100) == 0.0

    # --- Floating point ---
    def test_fractional_discount(self):
        result = calculate_discount(99.99, 15)
        assert result == pytest.approx(84.99, abs=0.01)

    def test_one_cent_price(self):
        result = calculate_discount(0.01, 50)
        assert result == pytest.approx(0.005, abs=0.001)

    # --- Edge cases ---
    def test_zero_price(self):
        assert calculate_discount(0, 25) == 0.0

    # --- Invalid inputs ---
    def test_negative_price_raises(self):
        with pytest.raises(ValueError, match="price must be non-negative"):
            calculate_discount(-10, 10)

    def test_negative_discount_raises(self):
        with pytest.raises(ValueError, match="discount must be between 0 and 100"):
            calculate_discount(100, -5)

    def test_discount_over_100_raises(self):
        with pytest.raises(ValueError, match="discount must be between 0 and 100"):
            calculate_discount(100, 110)

    def test_none_input_raises(self):
        with pytest.raises(TypeError):
            calculate_discount(None, 10)
```

**What changed and why:**

1. **Descriptive test names** — each name states the scenario, not just "test_discount."
2. **Removed redundancy** — the original had `calculate_discount(50, 0)` and a separate `test_no_discount` doing the same thing.
3. **Added boundary tests** — 0% discount, 100% discount, zero price, one cent.
4. **Added floating point tests** — using `pytest.approx` instead of exact equality, which would be fragile.
5. **Added error case tests** — negative price, negative discount, discount over 100%, None input. These define the contract.
6. **Grouped into a class** — makes it clear these all test the same function.

The original 4 assertions gave false confidence. The improved 11 assertions define the function's full contract: valid ranges, boundary behavior, and error handling.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
