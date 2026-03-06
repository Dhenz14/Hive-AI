"""Phase 3C: Metacognition — Socratic Self-Questioning (Part 2)

Scenarios: "What would break this in production?" and
"Am I confusing correlation with causation?"
"""

PAIRS = [
    (
        "thinking/meta-socratic-production-break-file-upload",
        r'''Here's my file upload endpoint for a Flask app:

```python
import os
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files['file']
    filename = file.filename
    filepath = os.path.join('uploads', filename)
    file.save(filepath)
    return jsonify({'path': filepath})
```

Does this look good?''',
        r'''<think>
My initial approach: The basic structure looks correct — receives a file, saves it to uploads/.

Wait — let me ask myself what would break this in production:

Q: What would break this in production? Can I think of attack vectors?
A: Multiple critical issues:
  1. Path traversal: filename could be "../../../etc/passwd" — os.path.join('uploads', '../../../etc/passwd') writes outside the uploads directory
  2. No file size limit — a user can upload a 50GB file and fill the disk
  3. No file type validation — can upload .exe, .php, .sh files
  4. Filename collisions — two users uploading "report.csv" overwrite each other
  5. No authentication — anyone can upload files

Q: What happens under concurrent load?
A: Two users uploading the same filename simultaneously = race condition. One file gets overwritten.

Q: What if the uploads directory doesn't exist?
A: os.path.join works but file.save() will fail with FileNotFoundError.

Q: What happens if disk is full?
A: file.save() will raise an IOError. No error handling, so the user gets a 500 error with a stack trace (information disclosure).

Q: Is the response safe?
A: Returning the filesystem path in the response leaks server directory structure. Should return a URL or file ID instead.

Q: What about the filename encoding?
A: Filenames with special characters (spaces, unicode, null bytes) can cause issues on different operating systems.

This endpoint has at least 6 production-breaking issues. The code "works" locally but is dangerous in production.
</think>

This has **6 critical production issues**. Here's the fixed version:

```python
import os
import uuid
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB limit
UPLOAD_DIR = 'uploads'
ALLOWED_EXTENSIONS = {'.pdf', '.png', '.jpg', '.csv', '.txt'}

os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'Empty filename'}), 400

    # Sanitize filename and check extension
    safe_name = secure_filename(file.filename)
    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({'error': f'File type {ext} not allowed'}), 400

    # Unique filename prevents collisions
    unique_name = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR, unique_name)
    file.save(filepath)

    return jsonify({'file_id': unique_name})  # Don't expose server path
```

**Issues fixed:**

| Issue | Original | Fixed |
|-------|----------|-------|
| Path traversal | `../../../etc/passwd` | `secure_filename()` sanitizes |
| No size limit | Unlimited upload | `MAX_CONTENT_LENGTH = 10MB` |
| No type check | Any file type | `ALLOWED_EXTENSIONS` whitelist |
| Name collision | Overwrites files | UUID-based unique names |
| Info disclosure | Returns server path | Returns file ID only |
| Missing directory | Crashes if no `uploads/` | `os.makedirs(exist_ok=True)` |'''
    ),
    (
        "thinking/meta-socratic-production-break-session",
        r'''I'm storing user sessions in Flask's built-in session:

```python
from flask import Flask, session

app = Flask(__name__)
app.secret_key = 'mysecretkey123'

@app.route('/login', methods=['POST'])
def login():
    user = authenticate(request.form['username'], request.form['password'])
    if user:
        session['user_id'] = user.id
        session['role'] = user.role
        return redirect('/dashboard')
    return 'Invalid credentials', 401

@app.route('/admin')
def admin():
    if session.get('role') == 'admin':
        return render_template('admin.html')
    return 'Forbidden', 403
```

This works in development. Any issues for production?''',
        r'''<think>
My initial approach: The auth flow looks standard — store user info in session, check role for access.

Q: What would break this in production?

Q: Is the secret key secure?
A: 'mysecretkey123' is terrible. Flask sessions are signed cookies — if someone guesses the secret key, they can forge ANY session, making themselves admin. This is a critical vulnerability. Need a long random key from os.urandom() or environment variable.

Q: Wait — Flask sessions are CLIENT-SIDE cookies. What does that mean for security?
A: The session data is stored in the cookie itself (base64-encoded, signed but NOT encrypted). This means:
  1. Users can READ their session data (they can see role='user')
  2. The signature prevents MODIFICATION, but only if the secret key is strong
  3. Session data is sent with every request (bandwidth)
  4. No server-side session invalidation — you can't force-logout a user

Q: Can I invalidate a compromised session?
A: No. With client-side sessions, if a user's cookie is stolen, you can't invalidate it server-side. The only option is to change the secret key, which logs out ALL users.

Q: What about scaling to multiple servers?
A: Client-side sessions work across multiple servers (no shared state needed). But for server-side sessions, you'd need Redis or a database.

Q: Is storing role in the session safe?
A: If a user's role changes (admin demoted to user), the session still says 'admin' until they re-login. Role should be checked from the database on each request, not cached in the session.

Q: What about session fixation attacks?
A: After successful login, the session ID should be regenerated. Flask doesn't do this automatically.

Multiple production issues found.
</think>

Several production issues, some critical:

**Critical: Weak secret key**
```python
# DANGEROUS: guessable secret key = anyone can forge admin sessions
app.secret_key = 'mysecretkey123'

# Fix: use a strong random key from environment
app.secret_key = os.environ['FLASK_SECRET_KEY']
# Generate with: python -c "import secrets; print(secrets.token_hex(32))"
```

**Critical: Client-side sessions expose data**
Flask's default session stores data IN the cookie (base64-encoded, signed but **not encrypted**). Users can decode and read `role='admin'`.

**Issue: Stale role in session**
```python
# If admin is demoted, session still says role='admin'
# Fix: check role from database, not session
@app.route('/admin')
def admin():
    user = User.query.get(session.get('user_id'))
    if user and user.role == 'admin':  # Fresh from DB
        return render_template('admin.html')
    return 'Forbidden', 403
```

**Issue: No session invalidation**
With client-side sessions, you can't force-logout a compromised user. Fix: use server-side sessions:

```python
from flask_session import Session

app.config['SESSION_TYPE'] = 'redis'
app.config['SESSION_REDIS'] = redis.Redis()
Session(app)
# Now sessions are stored server-side — you can delete them
```

**Issue: No session regeneration after login**
```python
@app.route('/login', methods=['POST'])
def login():
    user = authenticate(...)
    if user:
        session.clear()  # Prevent session fixation
        session['user_id'] = user.id
        return redirect('/dashboard')
```

**Production checklist:**
1. Strong random secret key (from env var)
2. Server-side sessions (Redis/database) for invalidation
3. Check roles from database, not session cache
4. Regenerate session on login
5. Set `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SECURE=True`'''
    ),
    (
        "thinking/meta-socratic-correlation-causation-perf",
        r'''After deploying a new caching layer, our API response times dropped from 200ms to 50ms. But we also notice our database CPU usage went from 80% to 30%. The caching is clearly reducing database load. Should we add caching to all our endpoints?''',
        r'''<think>
My initial approach: The data shows caching improved response time and reduced DB load. Adding it everywhere seems logical.

Wait — let me challenge my causal reasoning:

Q: Am I confusing correlation with causation? Did the caching CAUSE the DB CPU reduction?
A: Not necessarily. What ELSE changed during the deployment?
  - Was there a database index added in the same release?
  - Did traffic patterns change (time of day, day of week)?
  - Was there a slow query fixed in the same PR?
  - Did the infrastructure team scale up the database?
  - Did a traffic spike end around the same time?

The DB CPU could have dropped for reasons completely unrelated to caching.

Q: Even if caching helped, should I cache ALL endpoints?
A: No. Caching has costs:
  - Cache invalidation complexity (the "two hard problems" of CS)
  - Stale data served to users
  - Memory/Redis costs
  - Cache stampede on expiry
  - Debugging difficulty (is the bug in the cache or the source?)

Q: Which endpoints actually benefit from caching?
A: Endpoints that are:
  - Read-heavy (not writes)
  - Expensive to compute
  - Tolerant of stale data
  - Called frequently with the same parameters

An endpoint that returns user-specific data updated every second doesn't benefit from caching.

Q: What's the actual evidence?
A: We have correlation (deployed caching → metrics improved) but not causation. To establish causation, we'd need:
  - A/B test with and without caching
  - OR: remove the caching and see if metrics revert
  - OR: check if the specific cached endpoints show improvement vs uncached ones

Q: What would the next maintainer think if every endpoint is cached?
A: They'd be dealing with stale data bugs, cache invalidation logic in every write path, and an inability to understand which data is fresh. It's a maintenance nightmare.
</think>

**Slow down — you're making a correlation-causation error.** The data shows two things happened at the same time, not that one caused the other.

**Before caching everything, verify the cause:**

1. **What else changed in that deployment?** Did you also:
   - Add database indexes?
   - Fix slow queries?
   - Reduce N+1 queries?
   - Change connection pool settings?

2. **Did external factors change?**
   - Traffic volume at different time of day?
   - End of a traffic spike?
   - Database instance auto-scaled?

3. **How to verify caching is the cause:**
   ```
   Check metrics for SPECIFICALLY the cached endpoints:
   - Did cached endpoint response time drop? (expected: yes)
   - Did uncached endpoint response time also drop? (if yes: something else helped)
   - Did DB queries-per-second drop for cached queries? (this confirms cache hits)
   ```

**Even if caching IS the cause, don't cache everything:**

| Cache this | Don't cache this |
|-----------|-----------------|
| Public product listings | User-specific dashboards |
| Static reference data | Real-time inventory counts |
| Expensive aggregations | Write-heavy endpoints |
| Infrequently changing data | Data with strict freshness needs |

**Costs of over-caching:**
- **Stale data bugs**: User updates profile → still sees old data
- **Invalidation complexity**: Every write must know which caches to clear
- **Debugging difficulty**: "Is this a bug or stale cache?"
- **Cache stampede**: Popular cache key expires → 1000 requests hit DB simultaneously

**Recommendation**: Identify the 3-5 highest-impact endpoints (slow + frequent + read-heavy) and cache those. Measure the impact. Don't blanket-cache everything.'''
    ),
    (
        "thinking/meta-socratic-anchored-first-idea-search",
        r'''I need to implement search functionality for our e-commerce product catalog (50,000 products). I'm thinking of using Elasticsearch. Can you help me set it up?''',
        r'''<think>
My initial approach: Set up Elasticsearch with a product index, configure mappings, write search queries.

Wait — let me challenge my assumptions:

Q: Am I anchored on the user's first idea? They said Elasticsearch — is that the right tool here?
A: Elasticsearch is powerful but is it proportionate? Let me check:
  - 50,000 products — this is a SMALL dataset
  - Elasticsearch is designed for millions/billions of documents
  - Running Elasticsearch for 50K products is like driving a semi truck to the grocery store

Q: What are the alternatives for 50K products?
A:
  - PostgreSQL full-text search: Built-in, no extra infrastructure, handles 50K trivially
  - SQLite FTS5: If using SQLite
  - Meilisearch/Typesense: Simpler alternatives to Elasticsearch
  - Even LIKE queries: At 50K rows with an index, LIKE '%term%' might be fast enough

Q: What search features do they actually need?
A: "Search functionality for product catalog" could mean:
  - Simple keyword match (PostgreSQL tsvector is perfect)
  - Fuzzy matching / typo tolerance (Elasticsearch or Meilisearch)
  - Faceted search (category, price range, brand filters)
  - Autocomplete/suggestions
  - Relevance ranking

For basic keyword search on 50K products, PostgreSQL is the right answer. The user doesn't need an entire search infrastructure.

Q: What's the operational cost of Elasticsearch?
A: Running Elasticsearch means:
  - JVM heap tuning (minimum 2GB RAM)
  - Index management, mapping updates
  - Data synchronization between primary DB and Elasticsearch
  - Another service to monitor, secure, and maintain
  - Cluster management for production (3 nodes recommended)

For 50K products, this operational overhead far exceeds the benefit.

Q: When WOULD Elasticsearch be justified?
A: At 1M+ products, when you need complex faceted search, fuzzy matching, autocomplete, and analytics on search queries.
</think>

**Elasticsearch is overkill for 50,000 products.** PostgreSQL full-text search handles this trivially with zero extra infrastructure.

**PostgreSQL full-text search (recommended):**

```sql
-- Add search vector column
ALTER TABLE products ADD COLUMN search_vector tsvector;

UPDATE products SET search_vector =
    setweight(to_tsvector('english', coalesce(name, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(description, '')), 'B') ||
    setweight(to_tsvector('english', coalesce(category, '')), 'C');

CREATE INDEX idx_products_search ON products USING GIN (search_vector);
```

```python
# Flask/SQLAlchemy query
from sqlalchemy import func

def search_products(query, limit=20):
    tsquery = func.plainto_tsquery('english', query)
    return (
        Product.query
        .filter(Product.search_vector.match(query))
        .order_by(func.ts_rank(Product.search_vector, tsquery).desc())
        .limit(limit)
        .all()
    )
```

**Why PostgreSQL wins here:**
- Already in your stack — no new infrastructure
- 50K products is trivial for PostgreSQL FTS
- Weighted ranking (name > description > category)
- No data synchronization needed
- GIN index makes queries sub-millisecond

**When to graduate to Elasticsearch:**
- 1M+ products
- Need fuzzy matching / typo tolerance
- Need autocomplete with complex suggestions
- Need search analytics (what are users searching for?)
- Need complex faceted search with real-time aggregations

**Middle ground** — if you need typo tolerance without Elasticsearch:
- **Meilisearch**: Easy to set up, built-in typo tolerance, great for e-commerce
- **Typesense**: Similar to Meilisearch, open source

**The progression:**
1. PostgreSQL FTS (50K products) ← **you are here**
2. Meilisearch/Typesense (500K products, need fuzzy search)
3. Elasticsearch (1M+ products, complex analytics)'''
    ),
    (
        "thinking/meta-socratic-blind-spots-api-design",
        r'''I'm designing a REST API for a task management app. Here are my endpoints:

```
POST   /tasks          - Create task
GET    /tasks          - List all tasks
GET    /tasks/:id      - Get task
PUT    /tasks/:id      - Update task
DELETE /tasks/:id      - Delete task
POST   /tasks/:id/complete  - Mark complete
```

Looks good to me. Am I missing anything?''',
        r'''<think>
My initial approach: The CRUD endpoints look standard. The /complete action endpoint is reasonable.

Q: What am I not considering? Let me systematically check blind spots.

Q: Authentication and authorization — who can access what?
A: No mention of auth. Can anyone delete any task? In a multi-user app, tasks belong to users. Need:
  - User scoping: GET /tasks should return only MY tasks, not everyone's
  - Authorization: Can't update/delete another user's task
  - This changes the API design fundamentally

Q: Pagination — what happens when there are 10,000 tasks?
A: GET /tasks returns ALL tasks. Need pagination: GET /tasks?page=1&per_page=20 or cursor-based.

Q: Filtering and sorting — how do users find tasks?
A: No way to filter by status, due date, priority, or assignee. Need: GET /tasks?status=pending&sort=due_date

Q: Bulk operations — can I complete 10 tasks at once?
A: Only single-task operations. Bulk complete, bulk delete are common needs. POST /tasks/bulk-complete with a list of IDs.

Q: What about uncompleting a task?
A: POST /tasks/:id/complete exists but no way to undo it. Need POST /tasks/:id/uncomplete or make it a PATCH on the status field.

Q: What about subtasks, comments, attachments?
A: Maybe out of scope for v1, but the API should be extensible. GET /tasks/:id/comments, GET /tasks/:id/subtasks.

Q: Error responses — what format?
A: No error format defined. Need consistent error responses:
  - 404 for missing task
  - 403 for unauthorized access
  - 422 for validation errors
  - JSON error body with message and error code

Q: Versioning — how will the API evolve?
A: No versioning strategy. /v1/tasks or Accept header versioning.

Q: Rate limiting — can a client hammer the API?
A: No rate limiting mentioned.

Found at least 7 blind spots in a "looks good" API design.
</think>

Several important gaps. Here's what you're missing:

**1. User scoping (critical)**
```
# Current: returns ALL tasks in the system
GET /tasks

# Needed: scoped to authenticated user
GET /tasks  (implicitly filtered by auth token's user)
# Authorization: users can only access their own tasks
```

**2. Pagination**
```
GET /tasks?page=1&per_page=20
# Or cursor-based:
GET /tasks?cursor=abc123&limit=20
```

**3. Filtering and sorting**
```
GET /tasks?status=pending&priority=high&sort=-due_date
GET /tasks?due_before=2024-03-01&assignee=me
```

**4. Undo for complete**
```
POST /tasks/:id/complete     ← exists
POST /tasks/:id/reopen       ← missing (or DELETE /tasks/:id/complete)
# Alternative: PATCH /tasks/:id with { "status": "pending" }
```

**5. Bulk operations**
```
POST /tasks/bulk   { "action": "complete", "ids": [1, 2, 3] }
DELETE /tasks/bulk  { "ids": [1, 2, 3] }
```

**6. Error format**
```json
{
    "error": {
        "code": "TASK_NOT_FOUND",
        "message": "Task 42 does not exist",
        "status": 404
    }
}
```

**7. Response envelope with metadata**
```json
{
    "data": [...],
    "meta": {
        "total": 150,
        "page": 1,
        "per_page": 20
    }
}
```

**Revised endpoint list:**
```
POST   /tasks                    - Create task
GET    /tasks?status=X&page=N    - List tasks (paginated, filtered)
GET    /tasks/:id                - Get task
PATCH  /tasks/:id                - Partial update (prefer over PUT)
DELETE /tasks/:id                - Delete task
POST   /tasks/:id/complete       - Mark complete
POST   /tasks/:id/reopen         - Undo complete
POST   /tasks/bulk               - Bulk operations
```

Start with these. Add subtasks, comments, and attachments when needed.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
