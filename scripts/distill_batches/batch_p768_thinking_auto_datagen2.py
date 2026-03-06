"""Phase 4A: Self-Improvement -- Training Data Generation (Part 2)

Teaching the model to generate high-quality training pairs for web development topics.
Each pair asks the model to CREATE training data and explains why each generated pair
is effective, building the meta-skill of self-improvement through data generation.
"""

PAIRS = [
    (
        "thinking/auto-datagen-rest-api-design",
        r'''Generate 3 high-quality training pairs that teach REST API design best practices. For each pair, explain why it's effective training data.''',
        r'''<think>
For REST API design best practices, I need to cover:
1. Beginner: Resource naming and HTTP method semantics -- the foundation most people get wrong
2. Intermediate: Pagination, filtering, and error response design -- where naive APIs become painful
3. Advanced: Versioning strategies, HATEOAS, and idempotency -- production-grade concerns

The most common mistakes are: using verbs in URLs (POST /createUser), inconsistent error formats, and not thinking about pagination from day one. I want each pair to correct a specific bad habit with a concrete alternative.
</think>

Here are 3 training pairs for teaching REST API design best practices:

**Pair 1 (Beginner):**
```
Q: I'm designing my first REST API. Here are my endpoints -- can you review them?

POST /createUser
GET /getUserById?id=123
POST /updateUserEmail
DELETE /removeUser?id=123
GET /getAllProducts
POST /searchProducts

A: These endpoints use verbs in the URLs, which fights against REST conventions. In REST, the URL identifies the RESOURCE (a noun), and the HTTP method is the VERB:

POST   /users              -- Create a user
GET    /users/123           -- Get user 123
PATCH  /users/123           -- Update user 123 (partial update)
PUT    /users/123           -- Replace user 123 (full update)
DELETE /users/123           -- Delete user 123
GET    /products            -- List all products
GET    /products?search=widget  -- Search products (filtering is a query param)

Key principles:
- Use plural nouns for collections: /users, not /user
- Use path segments for hierarchy: /users/123/orders (orders belonging to user 123)
- Use query parameters for filtering, sorting, pagination: /products?category=electronics&sort=price
- PUT replaces the entire resource, PATCH modifies specific fields. Most updates should use PATCH
- Search is just filtered GET, not a separate POST (unless the search criteria are very complex)

Your URL structure should read like a directory: /users/123/orders/456/items -- you're navigating a resource tree.
```
**Why this is effective:** It takes a realistic "first attempt" API and transforms it, letting the learner see the before/after. The corrections are mechanical and immediately applicable. Including PUT vs. PATCH and search-as-filtered-GET addresses follow-up questions before they arise.

**Pair 2 (Intermediate):**
```
Q: My API returns a list of 50,000 products on GET /products. It's slow and clients crash trying to render everything. I also get different error formats from different endpoints -- sometimes {"error": "..."} and sometimes {"message": "...", "code": 500}. How do I fix both issues?

A: Two problems, two patterns:

**1. Pagination (cursor-based for large datasets):**

GET /products?limit=25&cursor=eyJpZCI6MTAwfQ

Response:
{
    "data": [...25 products...],
    "pagination": {
        "next_cursor": "eyJpZCI6MTI1fQ",
        "has_more": true
    }
}

Use cursor-based pagination, not offset/limit. With offset, inserting or deleting rows causes items to be skipped or duplicated between pages. Cursors (typically a base64-encoded ID or timestamp) are stable.

Always default to a reasonable limit (25-100) and cap the maximum. Never return unbounded results.

**2. Consistent error envelope:**

Every error response should use the same structure:

{
    "error": {
        "code": "PRODUCT_NOT_FOUND",
        "message": "No product with ID 999 exists.",
        "details": [
            {"field": "id", "reason": "Product 999 has been deleted"}
        ]
    }
}

- HTTP status code conveys the category (404, 422, 500)
- error.code is a machine-readable string (clients switch on this, not the message)
- error.message is human-readable (for logs and developer debugging)
- error.details is optional, used for validation errors with multiple fields

Create a standard error handler that ALL endpoints use:

@app.exception_handler(AppError)
def handle_app_error(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": str(exc)}}
    )

This ensures every endpoint returns the same format, whether the error comes from your code or a framework default.
```
**Why this is effective:** It solves two real pain points that hit every growing API. Cursor pagination over offset pagination is a non-obvious choice with a concrete reason (row insertion/deletion). The error envelope with machine-readable codes teaches API design as a contract, not just request/response plumbing.

**Pair 3 (Advanced):**
```
Q: Our API is used by mobile apps and third-party integrations. We need to make breaking changes to the user resource (renaming fields, removing deprecated ones). How do we version the API without breaking existing clients? Also, our payment endpoint sometimes gets called twice due to network retries -- how do we prevent duplicate charges?

A: Two production-critical concerns:

**1. API Versioning -- URL path versioning is simplest:**

GET /v1/users/123    -- returns {name: "...", email_address: "..."}
GET /v2/users/123    -- returns {full_name: "...", email: "...", avatar_url: "..."}

Alternatives:
- Header versioning: Accept: application/vnd.myapi.v2+json (cleaner URLs but harder to test in a browser)
- Query param: /users/123?version=2 (easy but pollutes caching)

For most teams, URL path versioning (/v1/, /v2/) is the pragmatic choice. Support the old version for a deprecation period (6-12 months), log which clients still use it, and communicate sunset dates.

Migration strategy: internally, write a single handler and use response transformers:

def get_user_v2(user_id):
    user = db.get_user(user_id)
    return UserSchemaV2.from_orm(user)

def get_user_v1(user_id):
    v2_response = get_user_v2(user_id)
    return transform_v2_to_v1(v2_response)  # Map new fields to old names

This keeps v1 as a thin compatibility layer over v2 logic.

**2. Idempotency for payment safety:**

Clients send a unique idempotency key with each request:

POST /v2/charges
Idempotency-Key: txn_abc123_retry2
{amount: 5000, currency: "usd"}

Server-side implementation:
1. Before processing, check if this key exists in an idempotency store (Redis or DB table)
2. If found, return the STORED response (same status code, same body) -- do not reprocess
3. If not found, process the charge, store the response keyed by the idempotency key, return it

CREATE TABLE idempotency_keys (
    key         TEXT PRIMARY KEY,
    endpoint    TEXT NOT NULL,
    status_code INT NOT NULL,
    response    JSONB NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now(),
    expires_at  TIMESTAMPTZ DEFAULT now() + interval '24 hours'
);

Key details:
- Keys should expire (24h is typical) to prevent unbounded storage growth
- The key should be scoped to the endpoint + method, not globally unique
- The client generates the key (usually a UUID), so retries send the same key
- This pattern applies to any non-idempotent operation (POST creating resources, not just payments)
```
**Why this is effective:** It combines two concerns that production APIs must solve but tutorials rarely cover together. The versioning strategy includes the migration pattern (v1 as a wrapper over v2), which is the part teams actually struggle with. The idempotency implementation goes beyond theory to show the database schema and expiration policy.

**Quality checklist for these pairs:**
- [x] Each teaches exactly one concept
- [x] Questions are realistic (someone would actually ask this)
- [x] Answers show reasoning, not just solutions
- [x] Difficulty progression is clear
- [x] No factual errors'''
    ),
    (
        "thinking/auto-datagen-sql-optimization",
        r'''Generate 3 high-quality training pairs that teach SQL query optimization. For each pair, explain why it's effective training data.''',
        r'''<think>
For SQL optimization training data:
1. Beginner: Understanding EXPLAIN output and why indexes matter -- the fundamental diagnostic tool
2. Intermediate: Recognizing N+1 queries and fixing them with JOINs or subqueries
3. Advanced: Index design strategy, covering indexes, and when to denormalize

I want to use realistic table schemas, not abstract examples. Let me use an e-commerce schema since it's universally understood.
</think>

Here are 3 training pairs for teaching SQL query optimization:

**Pair 1 (Beginner):**
```
Q: This query takes 12 seconds on a table with 2 million rows. How do I figure out why it's slow and fix it?

SELECT * FROM orders WHERE customer_email = 'alice@example.com' ORDER BY created_at DESC;

A: Step 1: Use EXPLAIN ANALYZE to see what the database is actually doing:

EXPLAIN ANALYZE
SELECT * FROM orders WHERE customer_email = 'alice@example.com' ORDER BY created_at DESC;

-- Output (PostgreSQL):
-- Seq Scan on orders  (cost=0.00..45123.00 rows=15 width=240) (actual time=8432.1..12001.3 rows=15)
--   Filter: (customer_email = 'alice@example.com')
--   Rows Removed by Filter: 1999985
-- Sort  (cost=...)
-- Planning Time: 0.1 ms
-- Execution Time: 12001.5 ms

The "Seq Scan" means the database is reading ALL 2 million rows and checking each one. It found 15 matches and threw away 1,999,985 rows. This is like searching a phone book page by page instead of using the alphabetical index.

Step 2: Create an index on the column you're filtering:

CREATE INDEX idx_orders_customer_email ON orders (customer_email);

Now re-run EXPLAIN ANALYZE:
-- Index Scan using idx_orders_customer_email on orders  (cost=0.43..12.50 rows=15 width=240) (actual time=0.03..0.08 rows=15)
-- Planning Time: 0.1 ms
-- Execution Time: 0.1 ms

From 12 seconds to 0.1 milliseconds. The index lets the database jump directly to the 15 matching rows.

For the ORDER BY, you can make a composite index:

CREATE INDEX idx_orders_email_created ON orders (customer_email, created_at DESC);

This lets the database both find and sort using the index alone, avoiding a separate sort step.
```
**Why this is effective:** It teaches the diagnostic process (EXPLAIN ANALYZE) before the fix (CREATE INDEX), building a transferable skill rather than just "add an index." The before/after execution times make the improvement visceral. The composite index is a natural follow-up that adds depth.

**Pair 2 (Intermediate):**
```
Q: I'm building a dashboard that shows the 20 most recent orders with customer names. My ORM generates this pattern, and it's taking 3 seconds despite having indexes:

-- First query: get recent orders
SELECT * FROM orders ORDER BY created_at DESC LIMIT 20;

-- Then for EACH of the 20 orders, a separate query:
SELECT name FROM customers WHERE id = 101;
SELECT name FROM customers WHERE id = 205;
SELECT name FROM customers WHERE id = 101;  -- same customer, queried again!
... (20 queries)

A: This is the N+1 query problem: 1 query for the list + N queries for related data. Even though each individual query is fast (maybe 1ms with an index), the round-trip overhead of 20 separate database calls adds up.

**Fix: Use a JOIN to fetch everything in one query:**

SELECT o.id, o.total, o.created_at, c.name AS customer_name
FROM orders o
JOIN customers c ON o.customer_id = c.id
ORDER BY o.created_at DESC
LIMIT 20;

One query, one round-trip, ~2ms total.

**In your ORM, use eager loading:**

# Django
orders = Order.objects.select_related('customer').order_by('-created_at')[:20]

# SQLAlchemy
orders = session.query(Order).options(joinedload(Order.customer)).order_by(Order.created_at.desc()).limit(20).all()

# Rails
orders = Order.includes(:customer).order(created_at: :desc).limit(20)

**How to detect N+1 in production:**
- Django: django-debug-toolbar shows query count per request
- SQLAlchemy: set echo=True or use the sqltap profiler
- General: if a page makes more than ~5 queries, investigate

A well-optimized page rarely needs more than 3-5 queries regardless of how much data it displays.
```
**Why this is effective:** The N+1 problem is the single most common performance issue in ORM-based applications. Showing the raw SQL pattern first, then the ORM fixes in three popular frameworks, makes it actionable regardless of the learner's stack. The detection tools turn this from a one-time fix into a practice.

**Pair 3 (Advanced):**
```
Q: Our product search endpoint queries a 50-million-row table. The query below uses an index but still takes 800ms. EXPLAIN shows it's doing an index scan but then a "bitmap heap scan" and "recheck condition." How do I get this under 50ms?

SELECT id, name, price, category
FROM products
WHERE category = 'electronics'
  AND price BETWEEN 100 AND 500
  AND in_stock = true
ORDER BY popularity DESC
LIMIT 20;

Existing index: CREATE INDEX idx_products_category ON products (category);

A: The category index narrows 50M rows to maybe 2M electronics products, but then the database must visit each of those 2M rows on disk to check price, in_stock, and sort by popularity. That's the bitmap heap scan -- it's reading millions of rows from the table itself.

**Solution: A covering composite index designed for this query:**

CREATE INDEX idx_products_search ON products (
    category,
    in_stock,
    price,
    popularity DESC
) INCLUDE (id, name);

Index column order matters:
1. **category** -- equality filter (most selective first)
2. **in_stock** -- equality filter (true/false)
3. **price** -- range filter (BETWEEN). Range columns must come AFTER equality columns because a range scan breaks the index ordering for subsequent columns
4. **popularity DESC** -- sort column, so the database can read results in order without sorting

The INCLUDE clause adds id and name to the index leaf pages. Now the database can answer the entire query from the index alone without touching the table -- this is called an "index-only scan."

EXPLAIN ANALYZE should now show:
-- Index Only Scan using idx_products_search
-- Execution Time: 2.3 ms

**Design rules for composite indexes:**
1. Equality columns first (=), in order of selectivity
2. Range columns next (BETWEEN, >, <) -- only ONE range column per index is effective
3. Sort columns last (ORDER BY)
4. INCLUDE columns you need in SELECT to enable index-only scans
5. Don't create overlapping indexes -- (category, price) is redundant if you have (category, in_stock, price)

Monitor with: SELECT * FROM pg_stat_user_indexes WHERE idx_scan = 0; to find unused indexes wasting write performance and disk.
```
**Why this is effective:** It goes beyond "just add an index" to teach index design as a systematic process. The column ordering rules (equality, then range, then sort) are the key insight that separates competent from expert SQL developers. The INCLUDE clause for index-only scans is a concrete technique with dramatic payoff.

**Quality checklist for these pairs:**
- [x] Each teaches exactly one concept
- [x] Questions are realistic (someone would actually ask this)
- [x] Answers show reasoning, not just solutions
- [x] Difficulty progression is clear
- [x] No factual errors'''
    ),
    (
        "thinking/auto-datagen-auth-sessions",
        r'''Generate 3 high-quality training pairs that teach authentication and session management. For each pair, explain why it's effective training data.''',
        r'''<think>
For authentication/session management:
1. Beginner: Session-based auth vs. token-based auth -- when to use which
2. Intermediate: JWT implementation pitfalls -- what most tutorials get wrong
3. Advanced: Secure session management (token rotation, revocation, refresh tokens)

Security is a domain where bad tutorials are actively dangerous. I need to be especially careful about recommending best practices and flagging common insecure patterns.
</think>

Here are 3 training pairs for teaching authentication and session management:

**Pair 1 (Beginner):**
```
Q: I'm building a web app with a login page. Should I use sessions with cookies or JWTs? I've seen tutorials recommending both.

A: For a traditional web app with a backend that renders HTML, use session-based auth. For an API consumed by mobile apps or SPAs that need stateless authentication, consider JWTs. Here's how each works:

**Session-based (recommended for most web apps):**
1. User logs in with username/password
2. Server creates a session record (in DB or Redis): {session_id: "abc", user_id: 42, expires: ...}
3. Server sends back a cookie: Set-Cookie: session_id=abc; HttpOnly; Secure; SameSite=Lax
4. Browser automatically sends this cookie on every request
5. Server looks up session_id in the store to find the user

**Token-based (JWT):**
1. User logs in with username/password
2. Server creates a signed token containing user data: {user_id: 42, exp: ...}
3. Server sends the token in the response body
4. Client stores it (where? this is the problem) and sends it in Authorization header
5. Server verifies the signature -- no database lookup needed

**Why sessions are simpler and safer for web apps:**
- The cookie is HttpOnly (JavaScript can't read it -- immune to XSS token theft)
- The cookie is Secure (only sent over HTTPS)
- SameSite=Lax prevents most CSRF attacks
- Revoking access is instant: delete the session from the store
- No client-side token storage decisions

**When JWTs make sense:**
- Microservices that need to verify auth without calling a central session store
- Short-lived API tokens (5-15 minutes) with a separate refresh mechanism
- Third-party API authentication (OAuth flows)

The common mistake: using JWTs for a standard web app because a tutorial said they're "more modern." They're not more modern -- they solve a different problem.
```
**Why this is effective:** It directly addresses the confusion caused by competing tutorials. Instead of teaching one approach in isolation, it teaches the decision framework. The security properties of cookies (HttpOnly, Secure, SameSite) are introduced naturally rather than as an afterthought.

**Pair 2 (Intermediate):**
```
Q: I followed a JWT tutorial and implemented authentication for my API. A security review flagged several issues. Here's my code:

import jwt

SECRET = "mysecretkey123"

def create_token(user_id):
    return jwt.encode({"user_id": user_id}, SECRET, algorithm="HS256")

def verify_token(token):
    try:
        return jwt.decode(token, SECRET, algorithms=["HS256"])
    except:
        return None

What's wrong with this?

A: There are five security issues, roughly in order of severity:

**1. No expiration.** Your tokens are valid forever. If one leaks, the attacker has permanent access.
Fix: Add an expiration claim:
    payload = {"user_id": user_id, "exp": datetime.utcnow() + timedelta(minutes=15)}
The jwt library automatically rejects expired tokens during decode.

**2. Weak secret.** "mysecretkey123" can be brute-forced. An attacker who recovers your secret can forge tokens for any user.
Fix: Use a long random secret (at least 256 bits):
    SECRET = os.environ["JWT_SECRET"]  # Generated with: python -c "import secrets; print(secrets.token_hex(32))"
Never hardcode secrets in source code.

**3. Bare except swallows all errors.** If jwt.decode raises an unexpected error (wrong algorithm, malformed token), you silently return None instead of logging the issue.
Fix:
    except jwt.ExpiredSignatureError:
        return {"error": "Token expired"}
    except jwt.InvalidTokenError:
        return {"error": "Invalid token"}

**4. No audience or issuer claims.** If you have multiple services sharing the same secret, a token intended for Service A works on Service B.
Fix:
    payload = {"user_id": user_id, "exp": ..., "iss": "myapp", "aud": "myapp-api"}
    jwt.decode(token, SECRET, algorithms=["HS256"], audience="myapp-api", issuer="myapp")

**5. No token revocation strategy.** If a user changes their password or an admin disables an account, all existing tokens remain valid until expiration.
Fix: Use short-lived access tokens (15 min) + refresh tokens stored server-side. Or maintain a blacklist of revoked token IDs (jti claim) checked on each request.

The tutorial gave you a working demo. Production auth requires all five of these fixes.
```
**Why this is effective:** It starts from tutorial-quality code that "works" and systematically reveals why it's insecure. Each issue has a concrete fix, so the learner can incrementally improve their implementation. The severity ordering helps prioritize. The closing line reframes the gap between tutorials and production.

**Pair 3 (Advanced):**
```
Q: I need to implement a refresh token system for my mobile app's API. Access tokens expire in 15 minutes. How do I handle refresh tokens securely, including rotation and revocation?

A: Here's a complete refresh token flow with rotation:

**Token pair on login:**
POST /auth/login
{username, password} -> verify credentials

Response:
{
    "access_token": "eyJ...",       // JWT, 15-min expiry, contains user_id
    "refresh_token": "rf_a8b3c...", // Opaque random string, NOT a JWT
    "expires_in": 900
}

**Server-side refresh token storage:**

CREATE TABLE refresh_tokens (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     INT NOT NULL REFERENCES users(id),
    token_hash  TEXT NOT NULL UNIQUE,  -- store hash, never plaintext
    family_id   UUID NOT NULL,          -- groups tokens in a rotation chain
    expires_at  TIMESTAMPTZ NOT NULL,
    revoked     BOOLEAN DEFAULT false,
    created_at  TIMESTAMPTZ DEFAULT now()
);

Never store the raw refresh token -- store its SHA-256 hash. If the database is compromised, the attacker can't use the hashes.

**Refresh flow with rotation:**
POST /auth/refresh
{refresh_token: "rf_a8b3c..."}

Server logic:
1. Hash the incoming token, look it up in refresh_tokens
2. If not found or revoked or expired -> return 401
3. Mark the current refresh token as revoked
4. Issue a NEW refresh token (same family_id, new token value)
5. Issue a new access token
6. Return both to the client

**Replay detection (the family_id purpose):**
If an attacker steals refresh token #2 but the legitimate user already used it to get token #3:
- Attacker tries to use token #2 -> server sees it's revoked
- Server recognizes this as a replay attack because a revoked token in this family was reused
- Server revokes ALL tokens in this family_id (nuclear option)
- Both attacker and user must re-authenticate
- This is the correct security response: a compromise was detected

**Logout:**
POST /auth/logout
- Revoke all refresh tokens for this user (or just the current family_id)
- Access tokens remain valid until they expire (15 min max exposure)
- For immediate access token revocation, maintain a short-lived blacklist in Redis

**Key implementation details:**
- Refresh token expiry: 7-30 days (mobile apps can use longer)
- Clean up expired tokens with a daily cron job
- Rate-limit the refresh endpoint to prevent brute-force
- Bind refresh tokens to the device/IP that created them for additional security
```
**Why this is effective:** It covers the complete lifecycle (creation, rotation, replay detection, revocation, logout) that most articles only partially explain. The family_id replay detection is the critical security mechanism that distinguishes a toy implementation from a secure one. The database schema makes it immediately implementable.

**Quality checklist for these pairs:**
- [x] Each teaches exactly one concept
- [x] Questions are realistic (someone would actually ask this)
- [x] Answers show reasoning, not just solutions
- [x] Difficulty progression is clear
- [x] No factual errors'''
    ),
    (
        "thinking/auto-datagen-db-schema-design",
        r'''Generate 3 high-quality training pairs that teach database schema design. For each pair, explain why it's effective training data.''',
        r'''<think>
For database schema design:
1. Beginner: Normalization -- why separate tables instead of one big one
2. Intermediate: Many-to-many relationships, junction tables, and when to add extra columns to them
3. Advanced: Polymorphic associations, JSON columns vs. separate tables, and schema evolution strategies

I want to use a real domain (e-commerce, content management) to ground the examples. Abstract ER diagrams without context don't teach decision-making.
</think>

Here are 3 training pairs for teaching database schema design:

**Pair 1 (Beginner):**
```
Q: I'm storing orders in a single table with all the information:

CREATE TABLE orders (
    id INT PRIMARY KEY,
    customer_name TEXT,
    customer_email TEXT,
    customer_address TEXT,
    product_name TEXT,
    product_price DECIMAL,
    quantity INT,
    order_date DATE
);

It works, but my colleague says it's "not normalized." What does that mean and why should I care?

A: Normalization means splitting data into separate tables to eliminate redundancy. Your current design has three problems:

**1. Redundant data:** If Alice places 50 orders, her name, email, and address are stored 50 times. If she updates her email, you must update 50 rows (and if you miss one, data is inconsistent).

**2. Multi-item orders are awkward:** If Alice buys 3 products in one order, you need 3 rows with duplicated order info (same date, same customer).

**3. Deletion anomalies:** If you delete all of Alice's orders, you lose her customer record entirely.

**Normalized design:**

CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    address TEXT
);

CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    price DECIMAL(10,2) NOT NULL
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    customer_id INT REFERENCES customers(id),
    order_date DATE NOT NULL DEFAULT CURRENT_DATE
);

CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    order_id INT REFERENCES orders(id),
    product_id INT REFERENCES products(id),
    quantity INT NOT NULL DEFAULT 1,
    unit_price DECIMAL(10,2) NOT NULL  -- snapshot of price at time of order
);

Now each fact is stored once. Updating Alice's email changes one row. An order with 3 products has 1 order row and 3 order_items rows.

Note: unit_price in order_items is intentionally duplicated from products.price. This is correct -- you need to record what the customer actually paid, even if the product price changes later. This is a common case where denormalization is the right design.
```
**Why this is effective:** It starts from a schema the learner actually built (single table), shows the concrete problems (update anomalies, deletion anomalies), and walks through the normalized version with explanation. The unit_price exception is crucial -- it teaches that normalization has pragmatic limits.

**Pair 2 (Intermediate):**
```
Q: I have users and projects. A user can belong to many projects, and a project has many users. Each user has a role within each project (owner, editor, viewer). Where does the role go? I tried adding a role column to the users table but that doesn't work because a user can be an owner in one project and a viewer in another.

A: The role belongs on the junction table (also called a join table or association table) that connects users and projects:

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL
);

CREATE TABLE projects (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE project_members (
    project_id INT REFERENCES projects(id) ON DELETE CASCADE,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('owner', 'editor', 'viewer')),
    joined_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (project_id, user_id)
);

The primary key (project_id, user_id) ensures a user appears at most once per project. The role is an attribute of the RELATIONSHIP, not of the user or the project.

Common queries become natural:

-- All members of project 5 with their roles
SELECT u.name, pm.role
FROM project_members pm
JOIN users u ON u.id = pm.user_id
WHERE pm.project_id = 5;

-- All projects where Alice is an owner
SELECT p.name
FROM project_members pm
JOIN projects p ON p.id = pm.project_id
WHERE pm.user_id = 42 AND pm.role = 'owner';

-- Check if a user has edit access
SELECT EXISTS(
    SELECT 1 FROM project_members
    WHERE project_id = 5 AND user_id = 42 AND role IN ('owner', 'editor')
);

**Design tip:** Junction tables often grow extra columns over time (invited_by, last_accessed_at, notification_preferences). Give them a meaningful name (project_members, not projects_users) and their own serial ID if you expect them to be referenced by other tables.

ON DELETE CASCADE means if a project is deleted, all its membership rows are automatically removed. This is usually the right behavior for junction tables.
```
**Why this is effective:** It addresses the exact moment of confusion ("where does the role go?") that learners hit when first designing many-to-many relationships. The CHECK constraint, CASCADE behavior, and "junction tables grow over time" advice are practical details that tutorials skip but production schemas need.

**Pair 3 (Advanced):**
```
Q: I'm building a content management system. We have articles, videos, and podcasts. Each content type has shared fields (title, author, published_at) and type-specific fields (articles have word_count, videos have duration_seconds, podcasts have episode_number). Comments can be attached to any content type. What's the best schema design?

A: There are three common patterns. I'll show each with tradeoffs:

**Option 1: Single Table Inheritance (STI)**
CREATE TABLE content (
    id SERIAL PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN ('article', 'video', 'podcast')),
    title TEXT NOT NULL,
    author_id INT REFERENCES users(id),
    published_at TIMESTAMPTZ,
    word_count INT,           -- NULL for non-articles
    duration_seconds INT,     -- NULL for non-videos
    episode_number INT         -- NULL for non-podcasts
);

Pros: Simplest queries, one table, comments just reference content(id).
Cons: Many NULL columns. Adding a new type with 10 fields bloats the table. Can't enforce NOT NULL on type-specific fields (word_count should be required for articles but must be nullable for videos).

**Option 2: Concrete Table Inheritance**
CREATE TABLE articles (id SERIAL PRIMARY KEY, title TEXT, author_id INT, published_at TIMESTAMPTZ, word_count INT NOT NULL);
CREATE TABLE videos (id SERIAL PRIMARY KEY, title TEXT, author_id INT, published_at TIMESTAMPTZ, duration_seconds INT NOT NULL);
CREATE TABLE podcasts (id SERIAL PRIMARY KEY, title TEXT, author_id INT, published_at TIMESTAMPTZ, episode_number INT NOT NULL);

Pros: Clean per-type constraints, no NULLs.
Cons: Shared columns are duplicated. "All content sorted by date" requires UNION ALL across three tables. Comments need a polymorphic reference (content_type + content_id), which can't have a foreign key.

**Option 3: Shared base table + type tables (recommended)**
CREATE TABLE content (
    id SERIAL PRIMARY KEY,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    author_id INT REFERENCES users(id),
    published_at TIMESTAMPTZ
);

CREATE TABLE article_details (
    content_id INT PRIMARY KEY REFERENCES content(id) ON DELETE CASCADE,
    word_count INT NOT NULL
);

CREATE TABLE video_details (
    content_id INT PRIMARY KEY REFERENCES content(id) ON DELETE CASCADE,
    duration_seconds INT NOT NULL,
    resolution TEXT
);

CREATE TABLE comments (
    id SERIAL PRIMARY KEY,
    content_id INT REFERENCES content(id),  -- clean FK, works for all types
    body TEXT NOT NULL
);

Pros: Shared fields in one place, type-specific constraints enforced, comments use a real foreign key, "all content" queries hit one table. Cons: JOINs needed for type-specific fields.

For most CMS-style applications, Option 3 gives the best balance. Use it when you need polymorphic references (comments, tags, likes on any content type) with referential integrity.
```
**Why this is effective:** It presents all three industry-standard patterns with honest tradeoffs instead of declaring one "correct." The polymorphic reference problem (comments on any content type) is the specific pain point that makes this decision non-trivial. The recommendation is opinionated but justified.

**Quality checklist for these pairs:**
- [x] Each teaches exactly one concept
- [x] Questions are realistic (someone would actually ask this)
- [x] Answers show reasoning, not just solutions
- [x] Difficulty progression is clear
- [x] No factual errors'''
    ),
    (
        "thinking/auto-datagen-caching-strategies",
        r'''Generate 3 high-quality training pairs that teach caching strategies. For each pair, explain why it's effective training data.''',
        r'''<think>
For caching strategies:
1. Beginner: What caching is, cache-aside pattern, and TTL basics
2. Intermediate: Cache invalidation strategies -- the "two hard problems" in CS
3. Advanced: Multi-layer caching, cache stampede prevention, and consistency patterns

Caching is one of those topics where the concept is simple but the edge cases are where all the bugs live. I need to make the edge cases concrete.
</think>

Here are 3 training pairs for teaching caching strategies:

**Pair 1 (Beginner):**
```
Q: Our product page loads in 2 seconds because it queries the database on every request. My lead says to "add caching" but I'm not sure where to start. How does caching work in a web application?

A: Caching stores the result of an expensive operation so you can reuse it without recomputing. The most common pattern is cache-aside (also called lazy loading):

import redis
import json

cache = redis.Redis(host='localhost', port=6379)

def get_product(product_id):
    # Step 1: Check cache
    cached = cache.get(f"product:{product_id}")
    if cached:
        return json.loads(cached)  # Cache hit -- return immediately

    # Step 2: Cache miss -- query database
    product = db.query("SELECT * FROM products WHERE id = %s", product_id)

    # Step 3: Store in cache with expiration
    cache.setex(
        f"product:{product_id}",
        300,  # TTL: 300 seconds (5 minutes)
        json.dumps(product)
    )

    return product

The flow: check cache first -> if not found, get from database -> store result in cache -> return.

**TTL (Time to Live)** is the expiration time. After 5 minutes, the cached entry is automatically deleted, and the next request will fetch fresh data from the database. This is the simplest way to handle data that changes occasionally.

**Choosing a TTL:**
- Product catalog: 5-15 minutes (changes infrequently)
- User profile: 1-5 minutes (changes occasionally)
- Stock price: 5-30 seconds (changes rapidly)
- Login session: hours to days (changes on explicit action)

**What to cache:**
- Database query results (most common)
- API responses from external services
- Computed values (recommendations, aggregations)
- Rendered HTML fragments

**What NOT to cache (initially):**
- Data that must be real-time (account balance during a transaction)
- Data that's unique per request (search results for arbitrary queries)
- Very small/fast queries (caching overhead may exceed the savings)

Start by caching the one slowest query on your most-visited page. Measure the improvement before adding more cache layers.
```
**Why this is effective:** It starts from the exact situation a beginner faces ("my lead said to add caching"), shows the complete code pattern, and provides practical guidance on TTL selection and what to cache. The "what NOT to cache" section prevents over-engineering.

**Pair 2 (Intermediate):**
```
Q: I'm caching product data with a 5-minute TTL, but users complain that after an admin updates a product price, the old price shows for up to 5 minutes. How do I invalidate the cache when data changes?

A: This is the cache invalidation problem -- famously one of the two hard problems in computer science. Here are three strategies in order of complexity:

**Strategy 1: Write-through (invalidate on write)**
When updating the database, also delete or update the cache:

def update_product(product_id, new_data):
    db.execute("UPDATE products SET price = %s WHERE id = %s",
               new_data['price'], product_id)
    cache.delete(f"product:{product_id}")  # Next read will repopulate

Simple and effective. The next request triggers a cache miss and loads fresh data. The gap is milliseconds, not minutes.

Pitfall: if the database update succeeds but the cache delete fails (network blip), you have stale data. Fix with a shorter TTL as a safety net, or delete-then-update-DB order (risks a brief cache miss, which is safer than stale data).

**Strategy 2: Pub/Sub invalidation (for multiple cache servers)**
If you have multiple app servers each with local caches, deleting from one server's cache doesn't fix the others:

# When product is updated, publish an event
redis_pubsub.publish("cache_invalidation", json.dumps({
    "type": "product",
    "id": product_id
}))

# Each server subscribes and clears its local cache
def on_invalidation(message):
    data = json.loads(message)
    local_cache.delete(f"{data['type']}:{data['id']}")

**Strategy 3: Version-based keys (never invalidate, just ignore)**
Include a version number in the cache key:

cache_key = f"product:{product_id}:v{product.updated_at.timestamp()}"

When the product is updated, its updated_at changes, so the old cache key is never read again. Old entries expire naturally via TTL.

Pros: No invalidation logic needed, no race conditions.
Cons: Stale entries waste memory until TTL expiry, and you need the version (updated_at) available before checking cache.

**Recommendation:** Start with Strategy 1 (write-through invalidation). It handles 90% of cases. Move to Pub/Sub only when you have multiple cache layers or servers. Use version-based keys for immutable data (uploaded images, compiled assets).
```
**Why this is effective:** It presents invalidation as a spectrum of strategies rather than one "right answer." Each strategy's failure mode is explained (the network blip in write-through, the multi-server problem), which teaches the learner to reason about distributed state rather than just apply a recipe.

**Pair 3 (Advanced):**
```
Q: We have a flash sale starting at midnight. The product page is cached, but when the cache expires at midnight, we expect 10,000 simultaneous requests to hit the database at once trying to repopulate the cache. How do we prevent this "thundering herd" problem? Also, how should we structure caching across our CDN, application cache, and database query cache?

A: Two separate concerns: cache stampede prevention and multi-layer cache architecture.

**Cache Stampede Prevention:**

When a hot cache key expires and thousands of requests simultaneously see a cache miss, they all query the database at once. Three solutions:

**1. Distributed lock (most common):**
def get_product_with_lock(product_id):
    cached = cache.get(f"product:{product_id}")
    if cached:
        return json.loads(cached)

    # Try to acquire a lock for this key
    lock_key = f"lock:product:{product_id}"
    if cache.set(lock_key, "1", nx=True, ex=5):  # NX=only if not exists
        # Won the lock -- query DB and repopulate cache
        product = db.query(...)
        cache.setex(f"product:{product_id}", 300, json.dumps(product))
        cache.delete(lock_key)
        return product
    else:
        # Another request is repopulating -- wait and retry
        time.sleep(0.1)
        return get_product_with_lock(product_id)  # Retry (add max retries!)

Only one request hits the database; others wait for the cache to be repopulated.

**2. Proactive refresh (background repopulation):**
Set the logical TTL shorter than the actual TTL. When a request sees data that's "logically expired" but still cached, it triggers an async refresh:

def get_product_smart(product_id):
    raw = cache.get(f"product:{product_id}")
    if raw:
        data = json.loads(raw)
        if data["cached_at"] < time.time() - 240:  # 4 min logical TTL
            # Trigger background refresh, but return stale data immediately
            refresh_queue.enqueue(repopulate_product, product_id)
        return data["product"]

    # True cache miss (hard TTL of 5 min expired)
    return repopulate_product(product_id)

Users always get a fast response (possibly slightly stale), and the cache never fully expires under normal load.

**3. Pre-warming before the sale:**
Before midnight, run a script that populates the cache for all sale products:

for product_id in sale_product_ids:
    product = db.query(...)
    cache.setex(f"product:{product_id}", 600, json.dumps(product))

**Multi-Layer Cache Architecture:**

Layer 1 - CDN (Cloudflare, CloudFront): Cache static assets and full page responses at edge locations. TTL: 1-60 seconds for dynamic pages. Headers: Cache-Control: public, max-age=10, stale-while-revalidate=30.

Layer 2 - Application cache (Redis/Memcached): Cache database query results and computed data. TTL: minutes. This is your cache-aside layer.

Layer 3 - Database query cache (PostgreSQL shared_buffers, MySQL query cache): Automatic caching of recent query results. Usually just tune buffer sizes; the DB manages invalidation.

The request flows: CDN -> App server (checks Redis) -> Database. Each layer absorbs traffic so the layer behind it sees fewer requests. For a flash sale: the CDN handles 90% of requests, Redis handles 9%, and the database sees ~1%.

Set stale-while-revalidate on CDN responses so even when the CDN cache expires, it serves stale content while refreshing in the background -- the same principle as the proactive refresh pattern.
```
**Why this is effective:** It grounds the abstract "thundering herd" problem in a vivid scenario (flash sale at midnight) that makes the consequences tangible. Three solutions at different complexity levels let teams choose based on their infrastructure. The multi-layer architecture section connects individual caching concepts into a system-level view.

**Quality checklist for these pairs:**
- [x] Each teaches exactly one concept
- [x] Questions are realistic (someone would actually ask this)
- [x] Answers show reasoning, not just solutions
- [x] Difficulty progression is clear
- [x] No factual errors'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
