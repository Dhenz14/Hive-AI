"""Thinking-trace pairs: Python-specific real-world requests."""

PAIRS = [
    (
        "thinking/practical",
        r'''rewrite this class to be more Pythonic

public class UserManager {
    private List<User> users;

    public UserManager() {
        this.users = new ArrayList<>();
    }

    public void addUser(User user) {
        this.users.add(user);
    }

    public User getUserById(int id) {
        for (User user : this.users) {
            if (user.getId() == id) {
                return user;
            }
        }
        return null;
    }

    public List<User> getActiveUsers() {
        List<User> active = new ArrayList<>();
        for (User user : this.users) {
            if (user.getIsActive()) {
                active.add(user);
            }
        }
        return active;
    }

    public List<String> getUserEmails() {
        List<String> emails = new ArrayList<>();
        for (User user : this.users) {
            emails.add(user.getEmail());
        }
        return emails;
    }

    public int getActiveUserCount() {
        int count = 0;
        for (User user : this.users) {
            if (user.getIsActive()) {
                count++;
            }
        }
        return count;
    }

    public User getUserByEmail(String email) {
        for (User user : this.users) {
            if (user.getEmail().equals(email)) {
                return user;
            }
        }
        return null;
    }

    public void setUserActive(int id, boolean active) {
        User user = this.getUserById(id);
        if (user != null) {
            user.setIsActive(active);
        }
    }

    public void removeUser(int id) {
        User user = this.getUserById(id);
        if (user != null) {
            this.users.remove(user);
        }
    }
}''',
        r'''<think>
This is Java-style Python with several anti-patterns I need to fix:

1. Java-style getters/setters (getEmail, setIsActive) -- Python uses properties and direct attribute access
2. Manual loops for filtering/mapping -- Python uses list comprehensions and built-in functions
3. No type hints -- modern Python should use type annotations
4. Returning null/None for "not found" -- Python should raise exceptions (or use Optional explicitly)
5. ArrayList -> just use Python lists
6. No __repr__, __len__, or other dunder methods
7. Linear search for by-ID lookups -- should use a dict for O(1) lookups
8. User class probably also has Java-style getters/setters

I should also replace the User class with a dataclass, which eliminates all the boilerplate. And the UserManager should use a dict keyed by ID for efficient lookups.

The key Python principles to apply:
- "We're all consenting adults" -- no private fields with getters/setters
- Use built-in data structures effectively (dict for lookups)
- List comprehensions over manual loops
- Dataclasses over boilerplate __init__
- Properties only when you need computed values or validation
- Raise exceptions instead of returning None for "not found"
</think>

Here is the Pythonic rewrite. The key changes: dataclasses replace boilerplate, dict replaces linear search, comprehensions replace loops, direct attribute access replaces getters/setters.

```python
# models.py
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class User:
    """A dataclass replaces the Java-style User with getters/setters.
    Attributes are accessed directly: user.email, not user.getEmail()."""
    id: int
    email: str
    name: str
    is_active: bool = True

    # Properties only when you need computed values or validation
    @property
    def display_name(self) -> str:
        return self.name or self.email.split("@")[0]
```

```python
# manager.py
from dataclasses import dataclass, field
from typing import Iterator
from models import User


class UserNotFoundError(KeyError):
    """Raised when a user lookup fails. Better than returning None."""
    def __init__(self, identifier):
        super().__init__(f"No user found with identifier: {identifier}")


class UserManager:
    """Manages a collection of users with O(1) lookups by ID and email."""

    def __init__(self) -> None:
        self._by_id: dict[int, User] = {}
        self._by_email: dict[str, User] = {}

    # --- Pythonic collection interface ---

    def __len__(self) -> int:
        return len(self._by_id)

    def __contains__(self, user_id: int) -> bool:
        return user_id in self._by_id

    def __iter__(self) -> Iterator[User]:
        return iter(self._by_id.values())

    def __repr__(self) -> str:
        return f"UserManager({len(self)} users)"

    # --- Core operations ---

    def add(self, user: User) -> None:
        """Add a user. Raises ValueError if ID or email already exists."""
        if user.id in self._by_id:
            raise ValueError(f"User with ID {user.id} already exists")
        if user.email in self._by_email:
            raise ValueError(f"User with email {user.email} already exists")
        self._by_id[user.id] = user
        self._by_email[user.email] = user

    def remove(self, user_id: int) -> User:
        """Remove and return a user. Raises UserNotFoundError if not found."""
        user = self.get(user_id)
        del self._by_id[user.id]
        del self._by_email[user.email]
        return user

    def get(self, user_id: int) -> User:
        """Get user by ID. Raises UserNotFoundError if not found."""
        try:
            return self._by_id[user_id]
        except KeyError:
            raise UserNotFoundError(user_id)

    def get_by_email(self, email: str) -> User:
        """Get user by email. Raises UserNotFoundError if not found."""
        try:
            return self._by_email[email]
        except KeyError:
            raise UserNotFoundError(email)

    def find(self, user_id: int) -> User | None:
        """Get user by ID, returning None if not found.
        Use this when absence is expected, not exceptional."""
        return self._by_id.get(user_id)

    # --- Queries using comprehensions instead of manual loops ---

    @property
    def active(self) -> list[User]:
        """All active users."""
        return [u for u in self if u.is_active]

    @property
    def active_count(self) -> int:
        """Count of active users (without building a list)."""
        return sum(1 for u in self if u.is_active)

    @property
    def emails(self) -> list[str]:
        """All user emails."""
        return [u.email for u in self]

    def filter(self, **criteria) -> list[User]:
        """Generic filter: manager.filter(is_active=True, name='Alice')"""
        return [
            u for u in self
            if all(getattr(u, k) == v for k, v in criteria.items())
        ]
```

**Usage comparison:**

```python
# Java-style (BEFORE):
manager = UserManager()
manager.addUser(User(1, "alice@example.com", "Alice", True))
user = manager.getUserById(1)  # returns None if not found
if user is not None:
    email = user.getEmail()
active = manager.getActiveUsers()
count = manager.getActiveUserCount()
emails = manager.getUserEmails()
manager.setUserActive(1, False)

# Pythonic (AFTER):
manager = UserManager()
manager.add(User(id=1, email="alice@example.com", name="Alice"))
user = manager.get(1)          # raises UserNotFoundError if not found
email = user.email             # direct attribute access
active = manager.active        # property, reads like English
count = manager.active_count   # no need to build a list just to count
emails = manager.emails
user.is_active = False         # direct attribute assignment

# Python collection protocols work:
len(manager)                   # how many users
1 in manager                   # membership test
for user in manager:           # iteration
    print(user.name)

# Generic filtering:
admins = manager.filter(is_active=True, name="Alice")
```

**What changed and why:**

| Java Pattern | Python Pattern | Why |
|-------------|---------------|-----|
| `getEmail()` / `setEmail()` | `user.email` | Python does not need accessor boilerplate |
| `return null` | `raise UserNotFoundError` | Exceptions prevent "forgot to check None" bugs |
| Manual for-loop to filter | List comprehension | Shorter, faster, more readable |
| `getActiveUserCount()` loop | `sum(1 for ...)` generator | No intermediate list, single expression |
| No `__len__`, `__contains__` | Dunder methods | Makes the class work with `len()`, `in`, `for` |
| Linear scan for ID lookup | Dict with O(1) lookup | O(1) instead of O(n) for every access |
| Mutable with no validation | `add()` checks for duplicates | Prevents silent data corruption |'''
    ),
    (
        "thinking/practical",
        r'''I'm confused about when to use async vs threading vs multiprocessing''',
        r'''<think>
This is one of the most common Python concurrency questions. The answer depends on the TYPE of work:

1. I/O-bound (waiting for network, disk, database): Use async (asyncio) or threading
2. CPU-bound (computation, image processing, math): Use multiprocessing
3. Mixed: Use a combination

The key concept is the GIL (Global Interpreter Lock):
- Python's GIL prevents multiple threads from executing Python bytecode simultaneously
- This means threading does NOT speed up CPU-bound work
- But threading DOES speed up I/O-bound work because the GIL is released during I/O waits
- Multiprocessing bypasses the GIL by using separate processes with separate memory

When to use each:
- asyncio: Many concurrent I/O operations (thousands of connections, API calls). Single-threaded, cooperative multitasking. Best for web servers, API clients, web scrapers.
- threading: I/O-bound work with libraries that are not async-compatible. Simpler mental model than async. Good for file I/O, legacy library calls.
- multiprocessing: CPU-bound work. Image processing, data transformation, ML training.

I should give concrete examples of each with realistic use cases.
</think>

Here is the decision framework with concrete examples of each approach.

**The one-line rule:**
- Waiting for stuff (network, disk, database)? Use **asyncio** (or threading if the library is not async)
- Computing stuff (math, image processing, parsing)? Use **multiprocessing**

**Why it matters -- the GIL:**

```
Python's Global Interpreter Lock (GIL) means:
- Only ONE thread can execute Python code at a time
- Threads take turns, not run in parallel
- BUT: the GIL is released during I/O operations (network, disk, sleep)

So:
- Threading helps I/O-bound work (threads wait for I/O, GIL released)
- Threading does NOT help CPU-bound work (all threads compete for one GIL)
- Multiprocessing helps CPU-bound work (each process has its own GIL)
- Asyncio helps I/O-bound work (single thread, cooperative switching, no GIL overhead)
```

**Example 1: asyncio -- fetching many URLs concurrently**

```python
# Use asyncio when: you have MANY concurrent I/O operations
# and the libraries support async (httpx, aiohttp, asyncpg, etc.)

import asyncio
import httpx
import time


async def fetch_url(client: httpx.AsyncClient, url: str) -> dict:
    response = await client.get(url)
    return {"url": url, "status": response.status_code, "size": len(response.content)}


async def fetch_all_async(urls: list[str]) -> list[dict]:
    """Fetch 100 URLs concurrently in ~1 second (not 100 seconds)."""
    async with httpx.AsyncClient() as client:
        tasks = [fetch_url(client, url) for url in urls]
        return await asyncio.gather(*tasks)


# 100 URLs, each takes ~1 second to respond
urls = [f"https://httpbin.org/delay/1?id={i}" for i in range(100)]

start = time.time()
results = asyncio.run(fetch_all_async(urls))
print(f"Async: {len(results)} URLs in {time.time() - start:.1f}s")
# Output: Async: 100 URLs in ~1.5s (all concurrent)

# Compare to sequential:
# Sequential: 100 URLs in ~100s (one at a time)
```

**Example 2: threading -- I/O with non-async libraries**

```python
# Use threading when: you have I/O-bound work but the library
# does not support async (legacy SDKs, file I/O, some database drivers)

from concurrent.futures import ThreadPoolExecutor, as_completed
import requests  # requests is not async, so we use threading
import time


def fetch_url_sync(url: str) -> dict:
    response = requests.get(url, timeout=10)
    return {"url": url, "status": response.status_code}


def fetch_all_threaded(urls: list[str], max_workers: int = 20) -> list[dict]:
    """Fetch URLs concurrently using threads."""
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_url = {
            executor.submit(fetch_url_sync, url): url
            for url in urls
        }

        # Collect results as they complete
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                results.append({"url": url, "error": str(e)})

    return results


# Also great for file I/O:
def process_files_threaded(file_paths: list[str]) -> list[dict]:
    """Read and parse many files concurrently."""
    def process_one(path: str) -> dict:
        with open(path) as f:
            content = f.read()
        return {"path": path, "lines": content.count("\n"), "size": len(content)}

    with ThreadPoolExecutor(max_workers=10) as executor:
        return list(executor.map(process_one, file_paths))
```

**Example 3: multiprocessing -- CPU-bound work**

```python
# Use multiprocessing when: you need to DO computation, not wait for I/O
# Each process gets its own Python interpreter and GIL

from concurrent.futures import ProcessPoolExecutor
from multiprocessing import cpu_count
import time


def compute_heavy(data: bytes) -> dict:
    """CPU-intensive work: hashing, compression, image processing, etc."""
    import hashlib
    # Simulate heavy computation
    result = hashlib.pbkdf2_hmac("sha256", data, b"salt", 100_000)
    return {"hash": result.hex(), "input_size": len(data)}


def process_batch_parallel(items: list[bytes]) -> list[dict]:
    """Process items across all CPU cores."""
    # Use cpu_count - 1 to leave one core for the OS
    workers = max(1, cpu_count() - 1)

    with ProcessPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(compute_heavy, items))

    return results


# 100 heavy computations
items = [f"data_{i}".encode() for i in range(100)]

start = time.time()
results = process_batch_parallel(items)
print(f"Parallel: {len(results)} items in {time.time() - start:.1f}s")
# Output on 8-core machine: ~12x faster than sequential


# Real-world example: parallel image processing
from PIL import Image
from pathlib import Path


def resize_image(args: tuple[str, str, tuple[int, int]]) -> str:
    """Resize a single image. Runs in a separate process."""
    input_path, output_path, size = args
    img = Image.open(input_path)
    img.thumbnail(size)
    img.save(output_path, quality=85)
    return output_path


def resize_batch(
    image_dir: str,
    output_dir: str,
    size: tuple[int, int] = (800, 800),
) -> list[str]:
    """Resize all images in a directory using all CPU cores."""
    input_dir = Path(image_dir)
    out_dir = Path(output_dir)
    out_dir.mkdir(exist_ok=True)

    tasks = [
        (str(p), str(out_dir / p.name), size)
        for p in input_dir.glob("*.jpg")
    ]

    with ProcessPoolExecutor() as executor:
        return list(executor.map(resize_image, tasks))
```

**Example 4: Combining approaches for real applications**

```python
# Real apps often need both I/O concurrency and CPU parallelism

import asyncio
from concurrent.futures import ProcessPoolExecutor


async def process_api_data_pipeline(api_urls: list[str]) -> list[dict]:
    """
    1. Fetch data from many APIs concurrently (I/O-bound -> asyncio)
    2. Process each response with heavy computation (CPU-bound -> multiprocessing)
    """
    # Step 1: Fetch all data concurrently with asyncio
    async with httpx.AsyncClient() as client:
        tasks = [client.get(url) for url in api_urls]
        responses = await asyncio.gather(*tasks)

    raw_data = [r.json() for r in responses]

    # Step 2: Process data in parallel with multiprocessing
    # Use run_in_executor to call ProcessPoolExecutor from async code
    loop = asyncio.get_event_loop()
    with ProcessPoolExecutor() as pool:
        processed = await loop.run_in_executor(
            pool,
            process_batch_sync,  # regular function, runs in process pool
            raw_data,
        )

    return processed


def process_batch_sync(data_list: list[dict]) -> list[dict]:
    """CPU-heavy processing (runs in a separate process)."""
    return [heavy_transform(item) for item in data_list]
```

**Decision table:**

| Situation | Use | Why |
|-----------|-----|-----|
| 100+ API calls | asyncio | Thousands of concurrent connections, minimal memory |
| File reads with sync library | threading | GIL released during I/O, simple API |
| Image/video processing | multiprocessing | CPU-bound, bypasses GIL |
| Web server handling requests | asyncio (FastAPI/uvicorn) | Handles thousands of concurrent connections |
| Data pipeline (fetch + process) | asyncio + multiprocessing | I/O for fetch, CPU for transform |
| Simple script, few tasks | threading | Easiest to understand, good enough |
| ML model training | multiprocessing (or GPU) | Pure CPU/GPU computation |

**Common mistake: using threading for CPU-bound work**

```python
# This does NOT speed up CPU work due to the GIL:
from concurrent.futures import ThreadPoolExecutor
with ThreadPoolExecutor(max_workers=8) as executor:
    results = list(executor.map(cpu_heavy_function, items))
# Still runs on ONE core! Threads take turns holding the GIL.

# Fix: swap ThreadPoolExecutor for ProcessPoolExecutor:
from concurrent.futures import ProcessPoolExecutor
with ProcessPoolExecutor(max_workers=8) as executor:
    results = list(executor.map(cpu_heavy_function, items))
# Actually uses 8 cores!
```'''
    ),
    (
        "thinking/practical",
        r'''this script works but it's really slow, can you optimize it?

import sqlite3
import json

def analyze_logs(db_path, start_date, end_date):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all users
    cursor.execute("SELECT id, email FROM users")
    users = cursor.fetchall()

    results = []
    for user_id, email in users:
        # Get this user's logs in date range
        cursor.execute(
            "SELECT * FROM activity_logs WHERE user_id = ? AND created_at BETWEEN ? AND ?",
            (user_id, start_date, end_date)
        )
        logs = cursor.fetchall()

        if len(logs) == 0:
            continue

        # Count actions by type
        action_counts = {}
        for log in logs:
            action = log[3]  # action column
            if action in action_counts:
                action_counts[action] = action_counts[action] + 1
            else:
                action_counts[action] = 1

        # Find most common action
        most_common = None
        max_count = 0
        for action, count in action_counts.items():
            if count > max_count:
                max_count = count
                most_common = action

        # Get user's tags
        cursor.execute("SELECT tag FROM user_tags WHERE user_id = ?", (user_id,))
        tags = [row[0] for row in cursor.fetchall()]

        # Check if user is in any of the target segments
        target_segments = ['power_user', 'enterprise', 'beta_tester']
        in_target = False
        for tag in tags:
            if tag in target_segments:
                in_target = True
                break

        results.append({
            'user_id': user_id,
            'email': email,
            'total_actions': len(logs),
            'most_common_action': most_common,
            'action_breakdown': json.dumps(action_counts),
            'tags': json.dumps(tags),
            'in_target_segment': in_target,
        })

    # Sort by total actions descending
    for i in range(len(results)):
        for j in range(i + 1, len(results)):
            if results[j]['total_actions'] > results[i]['total_actions']:
                results[i], results[j] = results[j], results[i]

    conn.close()
    return results''',
        r'''<think>
Let me identify all the performance problems in this code, from most impactful to least:

1. N+1 query problem (CRITICAL): For each user, it makes 2 separate queries (activity_logs + user_tags). With 10,000 users, that is 20,000+ queries. This is the biggest bottleneck by far. Should be done in 2-3 queries total using JOINs and GROUP BY.

2. Fetching ALL columns from activity_logs with SELECT *: If the table has large columns (like a JSON payload), this wastes memory and I/O. Only need user_id, action, and created_at.

3. Manual bubble sort at the end: O(n^2) sorting algorithm. Python's built-in sorted() uses TimSort which is O(n log n).

4. Manual counting instead of collections.Counter: Not a performance issue but readability/maintenance issue.

5. No index hints mentioned: The query on activity_logs needs an index on (user_id, created_at) to be fast.

6. Loading all users even if they have no logs: Should filter users to only those with activity in the date range.

7. Manual "find most common" loop: Counter.most_common(1) does this.

8. Linear search for target segments: Using a list instead of a set for membership testing.

Let me rewrite this to:
- Use 1-2 SQL queries instead of N+1
- Let the database do the aggregation (GROUP BY, COUNT)
- Use Python built-ins (Counter, sorted, set)
- Add proper indexes
</think>

This script has several performance problems. The biggest one (N+1 queries) is likely making it 100-1000x slower than it needs to be. Here is the fix, in priority order.

**Problem 1 (CRITICAL): N+1 queries -- one query per user**

Your code runs `2 * N + 1` queries where N is the number of users. With 10,000 users, that is 20,001 database round-trips. This should be 2-3 queries total.

**Problem 2: Fetching all columns with SELECT ***

If activity_logs has a large payload column, you are loading all that data just to count action types.

**Problem 3: Bubble sort -- O(n^2)**

The manual nested loop sort is O(n^2). Python's built-in `sorted()` is O(n log n).

**Problem 4: No database indexes**

Without indexes, every query does a full table scan.

**Here is the optimized version:**

```python
import sqlite3
import json
from collections import Counter, defaultdict


def analyze_logs(db_path: str, start_date: str, end_date: str) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # access columns by name, not index
    cursor = conn.cursor()

    # Ensure indexes exist (run once, huge impact on query speed)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_activity_logs_user_date
        ON activity_logs (user_id, created_at)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_tags_user
        ON user_tags (user_id)
    """)

    # ONE query to get all action counts, grouped by user
    # The database does the filtering, counting, and grouping
    cursor.execute("""
        SELECT
            u.id AS user_id,
            u.email,
            al.action,
            COUNT(*) AS action_count
        FROM users u
        INNER JOIN activity_logs al ON al.user_id = u.id
        WHERE al.created_at BETWEEN ? AND ?
        GROUP BY u.id, u.email, al.action
    """, (start_date, end_date))

    # Build per-user data from the grouped results
    user_data: dict[int, dict] = {}
    for row in cursor.fetchall():
        uid = row["user_id"]
        if uid not in user_data:
            user_data[uid] = {
                "user_id": uid,
                "email": row["email"],
                "action_counts": Counter(),
                "total_actions": 0,
            }
        user_data[uid]["action_counts"][row["action"]] = row["action_count"]
        user_data[uid]["total_actions"] += row["action_count"]

    if not user_data:
        conn.close()
        return []

    # ONE query to get all tags for the relevant users
    user_ids = list(user_data.keys())
    placeholders = ",".join("?" * len(user_ids))
    cursor.execute(
        f"SELECT user_id, tag FROM user_tags WHERE user_id IN ({placeholders})",
        user_ids,
    )

    user_tags: dict[int, list[str]] = defaultdict(list)
    for row in cursor.fetchall():
        user_tags[row["user_id"]].append(row["tag"])

    conn.close()

    # Build final results using Python built-ins
    target_segments = {"power_user", "enterprise", "beta_tester"}  # set, not list

    results = []
    for uid, data in user_data.items():
        tags = user_tags.get(uid, [])
        action_counts = data["action_counts"]

        results.append({
            "user_id": uid,
            "email": data["email"],
            "total_actions": data["total_actions"],
            "most_common_action": action_counts.most_common(1)[0][0],
            "action_breakdown": json.dumps(dict(action_counts)),
            "tags": json.dumps(tags),
            "in_target_segment": bool(target_segments & set(tags)),
        })

    # Built-in sorted is O(n log n), your bubble sort was O(n^2)
    results.sort(key=lambda r: r["total_actions"], reverse=True)

    return results
```

**Performance comparison:**

```
Scenario: 10,000 users, 500,000 log entries, date range matches 100,000

BEFORE:
  Queries:        20,001 (1 + 10,000 for logs + 10,000 for tags)
  Sort:           O(n^2) bubble sort
  Memory:         Loads full rows with SELECT *
  Estimated time: 30-120 seconds

AFTER:
  Queries:        3 (1 index check + 1 grouped query + 1 tags query)
  Sort:           O(n log n) built-in TimSort
  Memory:         Only loads needed columns
  Estimated time: 0.5-2 seconds
```

**What changed and why:**

| Before | After | Speedup |
|--------|-------|---------|
| 1 query per user (N+1) | 2 total queries with JOIN + GROUP BY | 100-1000x |
| `SELECT *` (all columns) | Only select needed columns | 2-5x less memory |
| Manual counting loop | `Counter` (C-optimized) | Cleaner, slightly faster |
| Manual max finding | `Counter.most_common(1)` | Cleaner |
| List membership check | Set intersection | O(1) vs O(n) per check |
| Bubble sort O(n^2) | `list.sort()` O(n log n) | 100x+ for large lists |
| Column access by index `log[3]` | `row["action"]` via Row factory | No more magic numbers |

**If it is still too slow (millions of rows), add these optimizations:**

```python
# 1. Let the database do ALL the work (including "most common action")
cursor.execute("""
    WITH action_stats AS (
        SELECT
            user_id,
            action,
            COUNT(*) as cnt,
            ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY COUNT(*) DESC) as rn
        FROM activity_logs
        WHERE created_at BETWEEN ? AND ?
        GROUP BY user_id, action
    )
    SELECT
        u.id, u.email,
        a.action AS most_common_action,
        a.cnt AS most_common_count,
        total.total_actions
    FROM users u
    INNER JOIN action_stats a ON a.user_id = u.id AND a.rn = 1
    INNER JOIN (
        SELECT user_id, SUM(cnt) as total_actions
        FROM action_stats
        GROUP BY user_id
    ) total ON total.user_id = u.id
    ORDER BY total.total_actions DESC
""", (start_date, end_date))

# 2. Stream results instead of loading everything into memory
def analyze_logs_streaming(db_path, start_date, end_date):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(big_query, (start_date, end_date))

    # Yield one row at a time instead of building a huge list
    for row in cursor:
        yield {
            "user_id": row["id"],
            "email": row["email"],
            "total_actions": row["total_actions"],
        }

    conn.close()
```'''
    ),
    (
        "thinking/practical",
        r'''how do I make this into a proper package that others can pip install?''',
        r'''<think>
The user wants to turn their Python project into an installable package. The modern way is pyproject.toml with the src layout. I need to cover:

1. Directory structure (src layout)
2. pyproject.toml (replaces setup.py, setup.cfg, MANIFEST.in)
3. How to build and publish to PyPI
4. How to handle CLI entry points
5. How to pin vs range dependencies
6. How to include data files
7. How to test the package before publishing

I should give them a complete, copy-paste-ready setup that follows current best practices (2024+).
</think>

Here is the complete setup to make your project pip-installable, from directory structure to publishing on PyPI.

**Step 1: Directory structure (src layout)**

```
mypackage/
    src/
        mypackage/
            __init__.py       # version and top-level imports
            core.py           # your main code
            utils.py
            cli.py            # command-line interface (optional)
            py.typed          # empty file, enables type checking for users
            data/
                defaults.json # data files shipped with the package
    tests/
        __init__.py
        test_core.py
        test_utils.py
    pyproject.toml            # THE key file -- replaces setup.py entirely
    README.md
    LICENSE
    .gitignore
```

**Step 2: pyproject.toml (the only config file you need)**

```toml
[build-system]
requires = ["setuptools>=69.0", "setuptools-scm>=8.0"]
build-backend = "setuptools.build_meta"

[project]
name = "mypackage"
version = "0.1.0"
description = "A short description of what your package does"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.10"
authors = [
    {name = "Your Name", email = "you@example.com"},
]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Typing :: Typed",
]

# Dependencies: use ranges, not pins (pins belong in applications, not libraries)
dependencies = [
    "requests>=2.28.0",
    "pydantic>=2.0,<3.0",
    "click>=8.0",
]

[project.optional-dependencies]
# Users install these with: pip install mypackage[dev]
dev = [
    "pytest>=8.0",
    "pytest-cov>=4.0",
    "ruff>=0.2.0",
    "mypy>=1.8",
]

# Optional feature sets: pip install mypackage[cli]
cli = [
    "rich>=13.0",
]

[project.urls]
Homepage = "https://github.com/you/mypackage"
Documentation = "https://mypackage.readthedocs.io"
Repository = "https://github.com/you/mypackage"
Issues = "https://github.com/you/mypackage/issues"

# CLI entry points: creates a 'mypackage' command when installed
[project.scripts]
mypackage = "mypackage.cli:main"

# Tell setuptools where to find packages
[tool.setuptools.packages.find]
where = ["src"]

# Include data files
[tool.setuptools.package-data]
mypackage = ["data/*.json", "py.typed"]

# Ruff config
[tool.ruff]
line-length = 88
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

# Pytest config
[tool.pytest.ini_options]
testpaths = ["tests"]

# Mypy config
[tool.mypy]
python_version = "3.10"
strict = true
```

**Step 3: The __init__.py (define your public API)**

```python
# src/mypackage/__init__.py
"""MyPackage: a short description."""

__version__ = "0.1.0"

# Explicitly define what users get when they do "from mypackage import ..."
from mypackage.core import MyClient, process_data
from mypackage.utils import format_output

__all__ = ["MyClient", "process_data", "format_output", "__version__"]
```

**Step 4: CLI entry point**

```python
# src/mypackage/cli.py
"""Command-line interface for mypackage."""

import click
from mypackage import MyClient, __version__


@click.group()
@click.version_option(version=__version__)
def main():
    """MyPackage CLI tool."""
    pass


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output", "-o", default="-", help="Output file (default: stdout)")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def process(input_file: str, output: str, verbose: bool):
    """Process an input file."""
    client = MyClient()
    result = client.process_file(input_file)

    if output == "-":
        click.echo(result)
    else:
        with open(output, "w") as f:
            f.write(result)
        if verbose:
            click.echo(f"Output written to {output}")


# When installed, users can run:
# $ mypackage process data.json --output results.json
```

**Step 5: Include package data files**

```python
# src/mypackage/core.py
"""Access data files shipped with the package."""

from importlib.resources import files
import json


def load_defaults() -> dict:
    """Load default configuration shipped with the package.
    This works regardless of how/where the package is installed."""
    data_dir = files("mypackage") / "data"
    defaults_path = data_dir / "defaults.json"
    return json.loads(defaults_path.read_text())
```

**Step 6: Build, test, and publish**

```bash
# Install build tools
pip install build twine

# Install your package in development mode (editable)
pip install -e ".[dev]"

# Run tests to make sure everything works
pytest

# Run type checking
mypy src/

# Run linter
ruff check src/ tests/

# Build the package (creates dist/ directory)
python -m build

# This creates:
# dist/mypackage-0.1.0.tar.gz      (source distribution)
# dist/mypackage-0.1.0-py3-none-any.whl  (wheel -- what pip installs)

# Check the built package for common issues
twine check dist/*

# Test upload to TestPyPI first (create account at test.pypi.org)
twine upload --repository testpypi dist/*

# Test installing from TestPyPI
pip install --index-url https://test.pypi.org/simple/ mypackage

# If everything works, upload to real PyPI
twine upload dist/*

# Now anyone can: pip install mypackage
```

**Step 7: Automate publishing with GitHub Actions**

```yaml
# .github/workflows/publish.yml
name: Publish to PyPI
on:
  release:
    types: [published]

jobs:
  publish:
    runs-on: ubuntu-latest
    permissions:
      id-token: write  # for trusted publishing
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install build tools
        run: pip install build

      - name: Build package
        run: python -m build

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        # Uses trusted publishing (no API token needed)
        # Configure at pypi.org/manage/project/mypackage/settings/publishing/
```

**Checklist before publishing:**

```
[ ] Package installs cleanly: pip install -e .
[ ] Tests pass: pytest
[ ] Types check: mypy src/
[ ] Lint passes: ruff check src/
[ ] Build succeeds: python -m build
[ ] twine check dist/* passes
[ ] README renders correctly (check on TestPyPI)
[ ] License file included
[ ] .gitignore includes dist/, *.egg-info/, build/
[ ] Version number updated in __init__.py and pyproject.toml
```'''
    ),
    (
        "thinking/practical",
        r'''I keep getting circular import errors and I don't understand why

# models.py
from services import UserService

class User:
    def __init__(self, id, name, email):
        self.id = id
        self.name = name
        self.email = email

    def get_orders(self):
        svc = UserService()
        return svc.get_orders_for_user(self.id)


# services.py
from models import User

class UserService:
    def get_user(self, user_id: int) -> User:
        data = db.query("SELECT * FROM users WHERE id = ?", user_id)
        return User(data['id'], data['name'], data['email'])

    def get_orders_for_user(self, user_id: int) -> list:
        return db.query("SELECT * FROM orders WHERE user_id = ?", user_id)''',
        r'''<think>
The user has a circular import: models.py imports from services.py, and services.py imports from models.py. Python fails because when loading models.py, it tries to load services.py, which tries to load models.py, which is not finished loading yet.

The root cause is that the User model has a method that calls UserService. This creates a dependency cycle: models depend on services, services depend on models.

There are several ways to fix this:

1. Move the import inside the method (lazy import) -- quick fix but not great
2. Remove the dependency from models -> services (best fix)
3. Use dependency injection
4. Create a third module that both import from

The best fix here is #2: the User model should NOT know about UserService. Models should be plain data objects. The "get_orders" behavior belongs in the service layer, not the model. This is a separation of concerns issue.

I should explain:
- WHY circular imports happen (Python's module loading mechanism)
- The quick fix (lazy import)
- The proper fix (dependency inversion / separate concerns)
- General rules to prevent this
</think>

Circular imports happen when module A imports module B and module B imports module A. Python cannot finish loading either one because each depends on the other.

**Here is what happens step by step:**

```
1. Python starts loading models.py
2. First line: "from services import UserService"
3. Python pauses models.py, starts loading services.py
4. services.py first line: "from models import User"
5. Python tries to get User from models.py, but models.py is not done loading yet
6. ImportError: cannot import name 'User' from partially initialized module 'models'
```

**Quick fix (lazy import inside the method):**

```python
# models.py -- move the import inside the method
class User:
    def __init__(self, id, name, email):
        self.id = id
        self.name = name
        self.email = email

    def get_orders(self):
        from services import UserService  # import here, not at module level
        svc = UserService()
        return svc.get_orders_for_user(self.id)
```

This works because by the time `get_orders()` is called, both modules are fully loaded. But it is a band-aid. Here is the proper fix.

**Proper fix: Remove the circular dependency entirely**

The root problem is that your User model calls a service. Models should be plain data objects -- they should not know about services, databases, or business logic. The "get_orders" behavior belongs in the service layer.

```python
# models.py -- clean, no imports from services
class User:
    """Plain data object. No business logic, no service calls."""
    def __init__(self, id: int, name: str, email: str):
        self.id = id
        self.name = name
        self.email = email

    def __repr__(self) -> str:
        return f"User(id={self.id}, name={self.name!r})"


class Order:
    def __init__(self, id: int, user_id: int, total: float):
        self.id = id
        self.user_id = user_id
        self.total = total
```

```python
# services.py -- depends on models (one-way dependency)
from models import User, Order

class UserService:
    def get_user(self, user_id: int) -> User:
        data = db.query("SELECT * FROM users WHERE id = ?", user_id)
        return User(data["id"], data["name"], data["email"])

    def get_orders_for_user(self, user_id: int) -> list[Order]:
        rows = db.query("SELECT * FROM orders WHERE user_id = ?", user_id)
        return [Order(r["id"], r["user_id"], r["total"]) for r in rows]

    def get_user_with_orders(self, user_id: int) -> tuple[User, list[Order]]:
        """If you need both, call the service, not the model."""
        user = self.get_user(user_id)
        orders = self.get_orders_for_user(user_id)
        return user, orders
```

```python
# Usage in your application code:
service = UserService()
user, orders = service.get_user_with_orders(42)
```

**The dependency now flows one way: services -> models. No cycle.**

```
BEFORE (circular):
  models.py  --imports-->  services.py
  services.py --imports-->  models.py

AFTER (one-way):
  services.py --imports-->  models.py
  models.py imports nothing from the project
```

**For more complex cases: use interfaces (Protocol)**

If you truly need models to DO something that requires a service, use dependency injection with a Protocol:

```python
# interfaces.py -- defines contracts, imports nothing from the project
from typing import Protocol


class OrderFetcher(Protocol):
    """Any class that can fetch orders for a user."""
    def get_orders_for_user(self, user_id: int) -> list: ...
```

```python
# models.py -- imports only from interfaces, not services
from interfaces import OrderFetcher


class User:
    def __init__(self, id: int, name: str, email: str):
        self.id = id
        self.name = name
        self.email = email

    def get_orders(self, fetcher: OrderFetcher) -> list:
        """Orders are fetched by an injected dependency, not a hardcoded service."""
        return fetcher.get_orders_for_user(self.id)
```

```python
# services.py -- imports from models (one-way)
from models import User


class UserService:
    def get_user(self, user_id: int) -> User:
        data = db.query("SELECT * FROM users WHERE id = ?", user_id)
        return User(data["id"], data["name"], data["email"])

    def get_orders_for_user(self, user_id: int) -> list:
        return db.query("SELECT * FROM orders WHERE user_id = ?", user_id)
```

```python
# Usage: inject the service into the model method
service = UserService()
user = service.get_user(42)
orders = user.get_orders(service)  # service implements OrderFetcher protocol
```

**Dependency flow with Protocol:**

```
interfaces.py (imported by models and services, imports nothing)
     ^                    ^
     |                    |
  models.py          services.py
```

**Rules to prevent circular imports:**

1. **Models should be dumb data objects** -- no business logic, no service calls
2. **Dependencies flow one way:** routes -> services -> repositories -> models
3. **Never import "up" the dependency chain** (models should not import services)
4. **If two modules need each other, extract the shared concept into a third module** (interfaces.py, types.py)
5. **Use TYPE_CHECKING for type-hint-only imports** that would otherwise create cycles:

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # This import only runs during type checking, not at runtime
    from services import UserService
```'''
    ),
]
