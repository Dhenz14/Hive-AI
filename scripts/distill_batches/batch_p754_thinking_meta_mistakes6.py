"""Phase 3E: Metacognition — Learning From Mistakes (Part 6)

Additional pairs for scenarios 8-9: memory leaks, API breaking changes.
"""

PAIRS = [
    (
        "thinking/meta-mistakes-memory-leak-closure",
        r'''Our Python web scraper's memory grows without bound. We're processing millions of URLs:

```python
class Scraper:
    def __init__(self):
        self.results = []
        self.error_callbacks = []

    def scrape(self, url):
        try:
            response = requests.get(url, timeout=10)
            data = self.parse(response)
            self.results.append(data)
        except Exception as e:
            # Store callback for retry
            self.error_callbacks.append(lambda: self.scrape(url))

    def parse(self, response):
        soup = BeautifulSoup(response.text, 'html.parser')
        return {"title": soup.title.string, "html": response.text}
```

Memory keeps growing even though we process results in batches.''',
        r'''<think>
I made an error: there are TWO memory leaks here:
1. `self.results` accumulates forever — each result stores the FULL HTML (`response.text`) which could be megabytes
2. `self.error_callbacks` stores lambda closures that capture `self`, creating circular references and preventing garbage collection of the entire Scraper object and all its data

The mistake was: accumulating data in lists without bounds and creating closures that reference the parent object.

The root cause was: not thinking about object lifecycle and ownership. `self.results` grows linearly with the number of URLs processed. With millions of URLs and full HTML stored, this is hundreds of GB. The lambda closures are worse — each captures `self`, which means the Scraper object can't be garbage collected even if nothing else references it.

Generalizable lesson: Track object ownership and lifecycle explicitly. Lists that only append (never remove/clear) are memory leaks. Closures that capture large objects prevent garbage collection. Process and discard data in a streaming fashion instead of accumulating.

Checklist item: For any list/dict that grows during processing: "Is there an upper bound? Do old entries get removed? How large can this get?"

Similar situations where this lesson applies:
1. Logging frameworks that store log entries in memory
2. Caching without eviction (cache grows forever)
3. Observer patterns where callbacks hold references to large objects
</think>

**Two memory leaks:**

**Leak 1: `self.results` stores full HTML forever.**
Each URL adds megabytes of HTML. With millions of URLs: OOM.

**Leak 2: `self.error_callbacks` creates closures capturing `self`.**
The lambdas hold a reference to the Scraper, preventing garbage collection.

**Fix:**
```python
class Scraper:
    def __init__(self, batch_size=1000):
        self.batch = []
        self.batch_size = batch_size
        self.failed_urls = []  # Store URLs, not closures

    def scrape(self, url):
        try:
            response = requests.get(url, timeout=10)
            data = self.parse(response)
            self.batch.append(data)

            if len(self.batch) >= self.batch_size:
                self.flush_batch()
        except Exception:
            self.failed_urls.append(url)  # Just the URL, not a closure

    def parse(self, response):
        soup = BeautifulSoup(response.text, 'html.parser')
        return {"title": soup.title.string}  # Don't store full HTML

    def flush_batch(self):
        save_to_database(self.batch)
        self.batch.clear()  # Release memory
```

**Changes:**
- **Stream processing**: flush results in batches, don't accumulate forever
- **Store URLs, not closures**: `failed_urls.append(url)` instead of lambda
- **Don't store full HTML**: extract what you need, discard the rest

**The lesson: any list that only appends is a potential memory leak.** Either process in batches and clear, or use a generator/streaming pattern. And never store closures that capture large objects.'''
    ),
    (
        "thinking/meta-mistakes-memory-leak-cache-unbounded",
        r'''We added an in-memory cache to speed up our API, but after a few days the server OOM-kills:

```python
# Simple in-memory cache
_cache = {}

def get_user_profile(user_id):
    if user_id in _cache:
        return _cache[user_id]

    profile = db.query(User).get(user_id)
    _cache[user_id] = profile
    return profile
```

We have 2 million users. The cache just grows until the server runs out of memory.''',
        r'''<think>
I made an error: the cache has no eviction policy, no size limit, and no TTL. It will eventually store every user's profile in memory.

The mistake was: building a cache without considering its maximum size. With 2M users, even if each profile is 1KB, that's 2GB of memory — and profiles are usually larger.

The root cause was: thinking of caching as "just store it in a dict" without considering the full cache lifecycle: insertion, eviction, expiration, and maximum size. A cache without eviction is a memory leak.

Generalizable lesson: Every cache needs eviction. Either set a maximum size (LRU eviction), a TTL (time-based eviction), or both. An unbounded cache is just a memory leak with better read performance.

Checklist item: For any in-memory cache (dict, list, set used as cache): "What's the maximum size? What's the eviction policy? What's the TTL?"

Similar situations where this lesson applies:
1. Memoization decorators without max size
2. Connection pools without maximum connections
3. Any buffer that grows without bound
</think>

**An unbounded cache is a memory leak.** With 2M users, you'll eventually cache them all.

**Fix — use `functools.lru_cache` or a bounded cache:**
```python
from functools import lru_cache

@lru_cache(maxsize=10000)  # Keep only 10K most recent
def get_user_profile(user_id):
    return db.query(User).get(user_id)
```

**Or with TTL (time-based eviction):**
```python
from cachetools import TTLCache

_cache = TTLCache(maxsize=10000, ttl=300)  # 10K entries, 5 min TTL

def get_user_profile(user_id):
    if user_id in _cache:
        return _cache[user_id]
    profile = db.query(User).get(user_id)
    _cache[user_id] = profile
    return profile
```

**Or use Redis (external cache, doesn't eat app memory):**
```python
def get_user_profile(user_id):
    cached = redis.get(f"user:{user_id}")
    if cached:
        return json.loads(cached)
    profile = db.query(User).get(user_id)
    redis.setex(f"user:{user_id}", 300, json.dumps(profile.to_dict()))
    return profile
```

**Every cache needs these three properties:**
1. **Max size**: how many entries before eviction (LRU, LFU, FIFO)
2. **TTL**: how long before an entry expires
3. **Invalidation**: how to remove stale entries when data changes

**The lesson: a dict without eviction is not a cache — it's a memory leak.** Always use a bounded data structure with explicit eviction.'''
    ),
    (
        "thinking/meta-mistakes-memory-leak-django-queryset",
        r'''Our Django management command runs fine for small datasets but crashes with OOM on our production database (10M rows):

```python
class Command(BaseCommand):
    def handle(self, **options):
        users = User.objects.filter(is_active=True)
        for user in users:
            process_user(user)
            self.stdout.write(f"Processed {user.email}")
```

This works for 1K users in dev but crashes for 5M active users in production.''',
        r'''<think>
I made an error: `User.objects.filter(is_active=True)` evaluates the entire queryset into memory when iterated. For 5M users, this loads all 5M User objects into RAM at once.

The mistake was: not understanding Django's queryset evaluation behavior. Querysets are lazy until iterated, but once you start `for user in users`, Django fetches ALL results into a Python list internally.

The root cause was: assuming that `for user in queryset` streams results one at a time. It doesn't — Django's default queryset evaluation loads all rows. You need `iterator()` for streaming, and even then you need to be careful about prefetching.

Generalizable lesson: When processing large datasets, never load all rows into memory at once. Use streaming/chunking: Django's `iterator()`, SQL cursors, or manual pagination with `LIMIT/OFFSET`. Track object ownership — if you create objects in a loop, make sure they're released.

Checklist item: For any queryset in a loop over large data: "Am I using .iterator()? What's the memory footprint per row × total rows?"

Similar situations where this lesson applies:
1. SQLAlchemy `query.all()` on large tables
2. Pandas `read_csv()` on GB-sized files (use `chunksize`)
3. Any ORM query that materializes large result sets
</think>

**Django loads the entire queryset into memory when you iterate it.** 5M User objects × ~1KB each = ~5GB RAM.

**Fix — use `.iterator()` for streaming:**
```python
class Command(BaseCommand):
    def handle(self, **options):
        users = User.objects.filter(is_active=True).iterator(chunk_size=2000)
        for user in users:
            process_user(user)
```

`.iterator()` fetches rows in chunks from the database cursor instead of loading everything at once.

**Even better — use `.iterator()` + `only()` to fetch only needed fields:**
```python
users = (User.objects
    .filter(is_active=True)
    .only('id', 'email', 'name')  # Don't load all 20 columns
    .iterator(chunk_size=2000))
```

**For very long operations, also clear Django's query log:**
```python
from django import db

for i, user in enumerate(users):
    process_user(user)
    if i % 10000 == 0:
        db.reset_queries()  # Clear stored queries (DEBUG mode)
        gc.collect()         # Optional: force garbage collection
```

**The lesson: ORMs hide memory costs behind clean APIs.** `for user in Users.objects.all()` looks like streaming but it's not. Always use `.iterator()` for large datasets. Know your ORM's memory behavior.'''
    ),
    (
        "thinking/meta-mistakes-api-breaking-field-type",
        r'''We changed a field from string to integer in our API response and it broke mobile clients:

```json
// Before (v1):
{"user": {"id": "12345", "name": "Alice"}}

// After (v1 - same endpoint):
{"user": {"id": 12345, "name": "Alice"}}
```

We thought changing `"12345"` to `12345` was a minor cleanup. 500 mobile users started getting crashes because their Swift code expected a String.''',
        r'''<think>
I made an error: changing a field's type in an existing API response without versioning. String → integer seems trivial but it's a breaking change for any typed client.

The mistake was: thinking of the change from the server's perspective ("it's the same data, just a better type") instead of from the client's perspective ("the JSON contract changed and my parser crashes").

The root cause was: no API versioning from day one. Without versioning, every change to the response shape is potentially breaking. We had no way to ship the new format to new clients while keeping the old format for existing clients.

Generalizable lesson: Any change to an API response shape is a breaking change, including: type changes, field removals, field renames, and null/non-null changes. Version your API from day one, and only make additive changes (new fields) to existing versions.

Checklist item: Before modifying an API response: "Would a typed client (Swift, Kotlin, TypeScript) break if I made this change? Is this additive (new field) or breaking (changed/removed field)?"

Similar situations where this lesson applies:
1. Changing null to empty array (breaking for clients checking `== null`)
2. Renaming a field (response → data)
3. Changing date format (ISO string → Unix timestamp)
</think>

**Changing a field's type is a breaking change.** Even string → integer.

**Why this breaks clients:**
```swift
// Swift client expecting String:
let userId = json["user"]["id"].stringValue  // Crashes on integer
```
```kotlin
// Kotlin client:
val userId: String = json.getString("id")  // ClassCastException
```

**The fix — version from day one:**

**Option 1: URL versioning (recommended for REST):**
```
GET /v1/users/12345  → {"id": "12345", ...}  // Old format forever
GET /v2/users/12345  → {"id": 12345, ...}    // New format
```

**Option 2: Both types during transition:**
```json
{
  "user": {
    "id": 12345,
    "id_string": "12345",
    "name": "Alice"
  }
}
```
Deprecate `id_string` after clients migrate.

**Non-breaking vs breaking changes:**
| Change | Breaking? |
|--------|-----------|
| Add new field | No (additive) |
| Remove field | **Yes** |
| Rename field | **Yes** |
| Change type (string→int) | **Yes** |
| Change null to non-null | **Yes** |
| Change non-null to null | **Yes** |
| Add enum value | Maybe (if clients switch on it) |

**The lesson: version your API from day one, and only make additive changes to existing versions.** If you must make a breaking change, create a new version. "It's just a type change" doesn't exist — any shape change breaks typed clients.'''
    ),
    (
        "thinking/meta-mistakes-api-breaking-pagination",
        r'''We changed our list endpoint from returning all results to paginated results and it broke integrations:

```python
# Before:
# GET /api/products → [{"id": 1}, {"id": 2}, ..., {"id": 5000}]

# After:
# GET /api/products → {"data": [{"id": 1}, ...{"id": 20}], "next_cursor": "abc123", "total": 5000}
```

Partners who built integrations against our API are angry — their code expected a JSON array at the top level but now gets an object.''',
        r'''<think>
I made an error: wrapping the response in a pagination envelope changed the top-level JSON type from array to object. This is a breaking change — any client doing `response.json()[0]` now gets a KeyError.

The mistake was: not versioning this change. Pagination is necessary for scale, but the migration needed to be done without breaking existing clients.

The root cause was: not having pagination from day one. If the original API returned `{"data": [...], "total": N}` from the start, adding cursor/offset pagination later would only require adding new fields (additive, non-breaking). The real mistake was returning a bare array in v1.

Generalizable lesson: Always wrap API responses in an object envelope from day one, even for list endpoints. `{"data": [...]}` gives you room to add pagination, metadata, and errors later without breaking the response shape. If you didn't do this, version the endpoint.

Checklist item: For any list endpoint, always return `{"data": [...]}` — never a bare array. This leaves room for pagination and metadata.

Similar situations where this lesson applies:
1. Adding error details to a response that used to just return the data
2. Adding rate limit headers that clients don't expect
3. Changing from sync response to async (returning job ID instead of result)
</think>

**Changing array → object at the top level is a major breaking change.** Every existing client is parsing `response[0]` and now gets an error.

**How to fix this retroactively:**

**Option 1: Version the endpoint:**
```
GET /v1/api/products → [...]           # Keep forever for existing clients
GET /v2/api/products → {"data": [...]} # New paginated format
```

**Option 2: Opt-in pagination via query parameter:**
```
GET /api/products              → [...]  (legacy, all results)
GET /api/products?page=1       → {"data": [...], "next_cursor": "...", "total": 5000}
GET /api/products?cursor=abc   → {"data": [...], "next_cursor": "...", "total": 5000}
```

Existing clients are unaffected. New clients use pagination.

**The lesson: always design list endpoints for future pagination.**

**Day-one pattern:**
```json
{
  "data": [...],
  "meta": {
    "total": 5000,
    "page": 1,
    "per_page": 20,
    "next_cursor": null
  }
}
```

Even if page 1 returns all results initially, the envelope is there for when you need pagination. Adding `next_cursor` later is additive (non-breaking).

**Never return a bare JSON array from an API endpoint.** You can't add pagination, errors, or metadata to a bare array without breaking the contract.'''
    ),
    (
        "thinking/meta-mistakes-api-breaking-nullable",
        r'''We made a previously-nullable field required and it broke clients:

```python
# Old behavior:
# POST /api/users {"email": "alice@example.com"}
# Response: {"id": 1, "email": "alice@example.com", "phone": null}

# New behavior (after making phone required):
# POST /api/users {"email": "alice@example.com"}
# Response: 422 Unprocessable Entity - "phone is required"
```

Existing signup forms don't have a phone field and now all registrations fail.''',
        r'''<think>
I made an error: making a previously optional field required is a breaking change for all existing clients that don't send it.

The mistake was: tightening input validation on an existing endpoint without considering that clients are built against the current contract (phone is optional).

The root cause was: thinking about the API from a data quality perspective ("we need phone numbers") without considering backwards compatibility ("existing clients don't send phone numbers"). The right approach is to make it required only for new API versions, or add it as optional and enforce it elsewhere (onboarding flow, admin dashboard).

Generalizable lesson: You can LOOSEN validation (optional → required becomes required → optional) but you cannot TIGHTEN validation (optional → required) without breaking clients. Input changes that reject previously-accepted requests are breaking changes.

Checklist item: Before changing field requirements: "Will previously-valid requests now be rejected?" If yes, it's a breaking change — version it or find another way.

Similar situations where this lesson applies:
1. Adding stricter regex validation to a field that was free-form
2. Reducing max length of a string field
3. Removing an accepted enum value from an input field
</think>

**Making optional fields required is a breaking change.** Every existing client omitting `phone` now fails.

**Breaking vs non-breaking input changes:**
| Change | Breaking? |
|--------|-----------|
| Add optional field | No |
| Make required → optional | No (loosening) |
| Make optional → required | **Yes (tightening)** |
| Add new validation (regex) | **Yes** |
| Remove accepted value | **Yes** |

**Safe ways to require phone:**

**Option 1: Require only in new API version:**
```
POST /v1/api/users  — phone optional (forever)
POST /v2/api/users  — phone required
```

**Option 2: Require in the UI, not the API:**
Keep phone optional in the API. Require it in your frontend signup form. This gets the phone data without breaking integrations.

**Option 3: Progressive enforcement:**
```python
# Accept without phone, but mark account as incomplete
@app.post("/api/users")
def create_user(data):
    user = User.create(
        email=data["email"],
        phone=data.get("phone"),  # Still optional
        profile_complete=bool(data.get("phone"))
    )
    # Prompt for phone on next login if missing
```

**The lesson: you can loosen API contracts but never tighten them.** Adding optional fields is safe. Making optional things required is breaking. If you need to tighten, version the API.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
