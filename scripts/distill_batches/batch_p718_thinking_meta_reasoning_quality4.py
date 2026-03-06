"""Phase 3B: Metacognition — Reasoning Quality Evaluation (Part 4)
Scenarios: Two algorithms, two auth schemes, two testing approaches (more)
"""

PAIRS = [
    (
        "thinking/meta-reasoning-two-search-algorithms",
        r'''I need to search for products in a catalog of 1 million items. Compare:

Approach A (database full-text search):
```python
def search_products(query):
    return db.execute("""
        SELECT id, name, description, ts_rank(search_vector, q) AS rank
        FROM products, to_tsquery('english', %s) q
        WHERE search_vector @@ q
        ORDER BY rank DESC
        LIMIT 20
    """, (query,)).fetchall()
```

Approach B (Elasticsearch):
```python
def search_products(query):
    result = es.search(index="products", body={
        "query": {
            "multi_match": {
                "query": query,
                "fields": ["name^3", "description", "category"],
                "fuzziness": "AUTO"
            }
        },
        "size": 20
    })
    return [hit["_source"] for hit in result["hits"]["hits"]]
```

Which is better for product search?''',
        r'''<think>
Let me evaluate both for e-commerce product search.

**PostgreSQL full-text search (A):**
Pros:
- No extra infrastructure (uses existing DB)
- ACID-consistent with product data (no sync lag)
- Simple setup (just add a tsvector column + GIN index)
- Good for basic keyword search
- Built-in stemming, stop words, ranking

Cons:
- Limited relevance tuning
- No fuzzy matching by default
- No "did you mean?" suggestions
- Limited language support
- Performance degrades with complex queries on large datasets
- No faceted search (filter by category + price range + brand)
- No autocomplete/type-ahead

**Elasticsearch (B):**
Pros:
- Fuzzy matching ("iphne" → "iPhone")
- Field boosting (name^3 means name matches rank 3× higher)
- Faceted search (filter by category, price range, brand, etc.)
- Autocomplete/suggestions
- Synonym support ("laptop" matches "notebook")
- Scalable to billions of documents
- Rich aggregations for analytics

Cons:
- Separate infrastructure (cluster to maintain)
- Data sync needed (eventual consistency between DB and ES)
- More complex setup and operations
- Higher cost (RAM-hungry)
- Must handle sync failures

**For e-commerce product search:**
Users expect:
- "Did you mean" suggestions → ES
- Fuzzy matching (typo tolerance) → ES
- Faceted filtering (brand, price, rating) → ES
- Autocomplete → ES
- Relevant results with boost factors → ES

PostgreSQL full-text can handle basic keyword search, but product search UX requirements go far beyond basic.

**Winner for product search:** Elasticsearch. The features that make product search good (fuzzy matching, facets, autocomplete, relevance tuning) are native to ES and would require extensive custom code with PostgreSQL.

**BUT:** If you have < 10,000 products and simple search needs, PostgreSQL is perfectly fine and avoids the operational complexity of Elasticsearch.
</think>

**Elasticsearch is better for product search — the UX features users expect (fuzzy matching, facets, autocomplete) are native to ES.**

### Evaluation

| Feature | PostgreSQL FTS | Elasticsearch |
|---------|---------------|---------------|
| Basic keyword search | ✓ | ✓ |
| Fuzzy matching (typos) | ✗ (manual trigram) | ✓ (`fuzziness: AUTO`) |
| Field boosting | Limited | ✓ (`name^3`) |
| Faceted search | ✗ (manual queries) | ✓ (aggregations) |
| Autocomplete | ✗ | ✓ (completion suggester) |
| "Did you mean?" | ✗ | ✓ (phrase suggester) |
| Synonyms | Limited | ✓ (synonym filter) |
| Operational complexity | Zero (existing DB) | High (separate cluster) |
| Data consistency | Real-time | Eventual (sync delay) |
| Scale limit | ~1M documents (practical) | Billions |

### When PostgreSQL FTS is enough
- < 10,000 documents
- Basic keyword search only
- Can't justify Elasticsearch infrastructure
- Data consistency is critical (no sync delay)
- Internal tools (users tolerate basic search)

### When Elasticsearch is worth it
- User-facing product search (expectations are high)
- Need fuzzy matching, facets, autocomplete
- > 100,000 documents
- Search is a core feature, not an afterthought

### The reasoning pattern
Search technology should match search UX requirements. Basic keyword lookup → database. Rich search experience (the kind users expect from Amazon/Google) → purpose-built search engine. The operational overhead of Elasticsearch is justified when search quality directly impacts revenue.'''
    ),
    (
        "thinking/meta-reasoning-oauth-vs-api-keys",
        r'''Compare these authentication schemes for a third-party API:

API Keys:
```
GET /api/data
Authorization: Bearer sk_live_abc123xyz
```
- Simple: one key per client
- Revocable: delete the key to revoke access
- No expiration handling needed

OAuth 2.0:
```
POST /oauth/token
grant_type=client_credentials
client_id=xxx&client_secret=yyy

GET /api/data
Authorization: Bearer eyJhbGci...
```
- Standards-based
- Scoped access (read-only, write, admin)
- Short-lived tokens with refresh

Which is better for our public API?''',
        r'''<think>
Let me evaluate for a public API (third-party developers will integrate with it).

**API Keys:**
Pros:
- Dead simple: one header per request
- Easy to implement (check key against database)
- Easy for developers to use (copy-paste key)
- Good for server-to-server communication

Cons:
- All-or-nothing access: key grants ALL permissions, can't scope
- Long-lived: if leaked, attacker has access until key is rotated
- No user context: key identifies the APPLICATION, not the user
- Can't act on behalf of users (no delegated access)
- Embedded in code: developers put keys in source code, config files

**OAuth 2.0:**
Pros:
- Scoped access: "this app can only read, not write"
- Short-lived tokens: leaked token expires quickly
- Delegated access: app can act on behalf of a user
- Standards-based: developers know the flow, tools support it
- Refresh tokens: long-lived access without long-lived credentials
- User consent: user explicitly grants permission

Cons:
- Complex: multiple grant types, token endpoints, redirect flows
- More requests: token exchange before API calls
- Implementation cost: higher for both API provider and consumer
- Over-engineered for simple server-to-server use cases

**For a public API:**
It depends on the USE CASE:

1. Server-to-server (analytics API, payment API) → API keys are fine
   - No user context needed
   - Server environments are trusted
   - Simplicity is valued

2. User-delegated access (social login, data access) → OAuth required
   - App needs to act as the user
   - User controls permissions
   - Revocation per-app needed

3. Mixed (both server and user-delegated) → API keys + OAuth
   - API keys for server admin operations
   - OAuth for user-delegated access

**Winner:** Depends on the use case! API keys for simple server-to-server APIs. OAuth for APIs where apps need user-delegated access or fine-grained permissions.
</think>

**It depends on the use case: API keys for simple server-to-server access, OAuth for user-delegated access or fine-grained permissions.**

### Evaluation

| Axis | API Keys | OAuth 2.0 |
|------|---------|-----------|
| Implementation complexity | Low | High |
| Developer onboarding | Copy-paste key | Learn OAuth flow |
| Permission scoping | All-or-nothing | Granular scopes |
| Token lifetime | Long-lived (risk) | Short-lived (safer) |
| User-delegated access | Not possible | Core feature |
| Server-to-server | Perfect fit | Over-engineered |
| Key rotation | Manual | Automatic (refresh tokens) |

### Decision matrix
| API type | Best choice | Why |
|----------|-------------|-----|
| Weather data API | API keys | Simple reads, no user context |
| Payment processing (Stripe) | API keys | Server-to-server, high trust |
| Social login ("Login with X") | OAuth | User-delegated access |
| File storage (Google Drive API) | OAuth | User's files, user consent needed |
| Internal microservice-to-microservice | mTLS or API keys | No user context |
| Mixed public API | Both | Keys for admin, OAuth for user access |

### Can API keys be scoped?
Yes — many APIs offer scoped API keys as a middle ground:
```
sk_live_readonly_abc123   → read-only access
sk_live_write_xyz789      → read + write access
sk_live_admin_def456      → full admin access
```
This gives some permission control without OAuth's complexity.

### The reasoning pattern
Authentication mechanism should match the trust model and access pattern. If the API consumer IS the resource owner (server-to-server), API keys are sufficient. If the API consumer is ACTING ON BEHALF of a resource owner (user-delegated), OAuth is required. Don't use OAuth's complexity when a simpler mechanism provides adequate security.'''
    ),
    (
        "thinking/meta-reasoning-unit-vs-integration-db",
        r'''Compare these approaches for testing database queries:

Approach A (mock the database):
```python
def test_get_active_users():
    mock_db = Mock()
    mock_db.execute.return_value = [
        {"id": 1, "name": "Alice", "active": True},
        {"id": 2, "name": "Bob", "active": True},
    ]

    service = UserService(mock_db)
    users = service.get_active_users()

    assert len(users) == 2
    mock_db.execute.assert_called_with(
        "SELECT * FROM users WHERE active = true"
    )
```

Approach B (test against real database):
```python
@pytest.fixture
def test_db():
    db = create_test_database()
    yield db
    db.rollback()

def test_get_active_users(test_db):
    # Setup: insert test data
    test_db.execute("INSERT INTO users (name, active) VALUES ('Alice', true)")
    test_db.execute("INSERT INTO users (name, active) VALUES ('Bob', true)")
    test_db.execute("INSERT INTO users (name, active) VALUES ('Charlie', false)")

    service = UserService(test_db)
    users = service.get_active_users()

    assert len(users) == 2
    assert {u.name for u in users} == {"Alice", "Bob"}
```

Which gives more confidence that the queries work?''',
        r'''<think>
This is specifically about testing DATABASE QUERIES. The purpose of these tests is to verify that the SQL is correct.

**Approach A (mock):**
The mock test asserts that `execute` was called with a specific SQL string. What does this actually test?
- Tests that the service CALLS the database with the right SQL
- Does NOT test that the SQL is correct
- Does NOT test that the SQL returns the right data
- Tests the IMPLEMENTATION, not the BEHAVIOR

If someone refactors the SQL to use a JOIN or a different WHERE clause that returns the same results, the mock test FAILS even though the behavior is correct. And if someone writes WRONG SQL, the mock test PASSES because it only checks the string.

**Approach B (real database):**
The integration test inserts real data and verifies the query returns the right results.
- Tests that the SQL actually works against a real database
- Tests that the query returns the correct rows
- Tests behavior (what comes back), not implementation (what SQL was sent)
- Catches SQL syntax errors, wrong column names, wrong conditions

If someone refactors the SQL, the test still passes as long as the right results come back. If someone writes wrong SQL, the test catches it.

**Performance:**
- Mock: ~1ms per test (no database)
- Real DB: ~10-50ms per test (with SQLite) or ~50-200ms (with PostgreSQL)

**Winner for testing database queries:** Approach B (real database), definitively. The entire point of testing queries is to verify they produce correct results. Mocking the database means you're testing that your code sends a string, not that the string is correct SQL.

The mock test is essentially: "assert that the code contains the right SQL string." You could just read the code for that.
</think>

**Approach B (real database) is far better for testing queries — mocking a database tests that SQL was sent, not that it's correct.**

### Evaluation

| Axis | Mock DB (A) | Real DB (B) |
|------|-----------|-------------|
| Catches SQL syntax errors | No | Yes |
| Catches wrong WHERE clause | No | Yes |
| Catches wrong JOIN | No | Yes |
| Catches column type issues | No | Yes |
| Refactoring safe | No (tests SQL string) | Yes (tests results) |
| Speed | ~1ms | ~10-50ms |
| Setup complexity | Low | Medium |

### Why mocking DB queries is almost useless
```python
# Mock test passes even with this WRONG SQL:
def get_active_users(self):
    return self.db.execute("SELECT * FROM users WHERE active = true")
    # Bug: should be "WHERE active = TRUE AND deleted_at IS NULL"

# Mock assertion just checks the string:
mock_db.execute.assert_called_with("SELECT * FROM users WHERE active = true")
# ✓ Passes! The test verified the bug, not the correctness!

# Real DB test catches it:
# Charlie (active=true, deleted_at='2024-01-01') appears in results
# assert {u.name for u in users} == {"Alice", "Bob"} → FAILS!
```

### Use SQLite for fast DB tests
```python
@pytest.fixture
def test_db():
    # In-memory SQLite — fast, no cleanup needed
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.rollback()
```

### When mocking IS appropriate for data layer
- Mocking external APIs (payment gateway, email service)
- Testing service logic that USES query results (mock the repository, not the DB)
- Testing error handling (simulate database connection failure)

### The reasoning pattern
Test at the right abstraction level. For database queries, the question is "does this SQL return the right data?" — which can only be answered by a real database. Mock at system boundaries (external services), test against real implementations at internal boundaries (your own database). The testing strategy should target where bugs actually occur.'''
    ),
    (
        "thinking/meta-reasoning-two-api-versioning",
        r'''Compare these two approaches for API versioning:

URL versioning:
```
GET /api/v1/users
GET /api/v2/users
```

Header versioning:
```
GET /api/users
Accept: application/vnd.myapi.v1+json

GET /api/users
Accept: application/vnd.myapi.v2+json
```

Which approach is better for a public REST API?''',
        r'''<think>
Let me evaluate both for a public REST API.

**URL versioning:**
Pros:
- Visible and obvious: developers see the version in the URL
- Easy to test: paste URL in browser, curl, Postman
- Simple routing: `/api/v1/*` vs `/api/v2/*`
- Easy caching: different URLs → different cache entries
- Documentation: version is part of the URL, clear in docs
- Load balancing: can route v1 to old servers, v2 to new servers

Cons:
- "Not RESTful": purists argue the URL identifies the resource, not the representation
- URL changes: upgrading v1→v2 means changing all client URLs
- Code duplication: maintaining v1 and v2 route handlers
- URL proliferation: /api/v1/users, /api/v2/users, /api/v3/users...

**Header versioning:**
Pros:
- "More RESTful": URL identifies the resource, Accept header selects representation
- Same URL for all versions (cleaner API surface)
- Can version individual resources independently
- Content negotiation is how HTTP was designed to work

Cons:
- Invisible: not obvious from the URL which version you're using
- Hard to test: can't paste URL in browser (need to set headers)
- Harder caching: same URL, different responses → need Vary header
- Documentation: harder to document (URLs don't show version)
- Load balancing: more complex routing (inspect headers)
- Easy to forget: developers forget the Accept header and get unexpected version

**For a PUBLIC REST API:**
Public APIs serve developers who may be unfamiliar with your system. They need:
- Clear documentation (URL versioning is self-documenting)
- Easy testing (paste URL in browser)
- Simple migration path (change v1 to v2)
- Low learning curve

Header versioning is technically "more RESTful" but creates friction for developers. Every API call requires remembering to set the Accept header. Forgetting it might give you the wrong version silently.

**Winner for public API:** URL versioning. It's simpler, more discoverable, easier to test, and easier to document. The "not RESTful" criticism is academic — pragmatism wins for developer experience.

Major APIs that use URL versioning: GitHub, Stripe, Twitter, Google.
</think>

**URL versioning is better for a public API — it's more discoverable, easier to test, and simpler for third-party developers.**

### Evaluation

| Axis | URL versioning | Header versioning |
|------|---------------|-------------------|
| Discoverability | Version visible in URL | Hidden in headers |
| Browser testing | Paste URL → works | Need header tool |
| Documentation | Self-documenting URLs | Must explain header format |
| Caching | Natural (different URLs) | Complex (Vary header) |
| Load balancing | Simple (route by path) | Complex (inspect headers) |
| "RESTful" purity | Less pure | More pure |
| Developer friction | Low | Medium |
| Adoption | GitHub, Stripe, Google | Few major APIs |

### The developer experience test
```bash
# URL versioning — just works:
curl https://api.example.com/v2/users

# Header versioning — must remember the header:
curl -H "Accept: application/vnd.myapi.v2+json" https://api.example.com/users
# Forgot the header? Get v1 silently? Get an error? Depends on implementation.
```

### Implementation tips for URL versioning
```python
# Route organization:
app.include_router(v1_router, prefix="/api/v1")
app.include_router(v2_router, prefix="/api/v2")

# Default to latest for unversioned:
@app.get("/api/users")
def redirect_to_latest():
    return RedirectResponse("/api/v2/users")

# Sunset old versions:
@v1_router.get("/users")
def v1_users():
    response.headers["Sunset"] = "2025-06-01"
    response.headers["Deprecation"] = "true"
    return get_users_v1()
```

### The reasoning pattern
For public APIs, developer experience trumps theoretical purity. URL versioning wins on discoverability, testability, and documentation — the things third-party developers care about most. Header versioning is more "correct" per REST theory but adds friction that hurts adoption. Choose what makes your API easiest to consume.'''
    ),
    (
        "thinking/meta-reasoning-orm-vs-raw-sql",
        r'''Compare these approaches for a complex reporting query:

ORM (SQLAlchemy):
```python
def get_sales_report(start_date, end_date):
    return (
        db.session.query(
            Product.category,
            func.sum(OrderItem.quantity).label('total_sold'),
            func.sum(OrderItem.quantity * OrderItem.unit_price).label('revenue'),
            func.count(distinct(Order.id)).label('order_count')
        )
        .join(OrderItem, Product.id == OrderItem.product_id)
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.created_at.between(start_date, end_date))
        .filter(Order.status == 'completed')
        .group_by(Product.category)
        .order_by(desc('revenue'))
        .all()
    )
```

Raw SQL:
```python
def get_sales_report(start_date, end_date):
    return db.execute("""
        SELECT
            p.category,
            SUM(oi.quantity) AS total_sold,
            SUM(oi.quantity * oi.unit_price) AS revenue,
            COUNT(DISTINCT o.id) AS order_count
        FROM products p
        JOIN order_items oi ON p.id = oi.product_id
        JOIN orders o ON o.id = oi.order_id
        WHERE o.created_at BETWEEN :start AND :end
        AND o.status = 'completed'
        GROUP BY p.category
        ORDER BY revenue DESC
    """, {"start": start_date, "end": end_date}).fetchall()
```

Which is better for this reporting query?''',
        r'''<think>
Let me evaluate both for a complex reporting query.

**ORM approach:**
Pros:
- Type safety: IDE auto-completes column names, catches typos
- Composable: can build queries programmatically (add filters conditionally)
- Database-agnostic: works on PostgreSQL, MySQL, SQLite
- Consistent style with the rest of the codebase

Cons:
- Harder to read for SQL-literate developers
- Harder to optimize: must understand ORM → SQL translation
- Can't use database-specific features (window functions, CTEs, etc.) without raw SQL fallback
- Debugging: must inspect generated SQL to understand performance

**Raw SQL approach:**
Pros:
- Readable: any developer who knows SQL can read this immediately
- Optimizable: can copy-paste into pgAdmin, EXPLAIN ANALYZE, tune directly
- Full database features: CTEs, window functions, lateral joins, etc.
- Predictable: what you write is what gets executed

Cons:
- String-based: typos in column names caught at runtime, not compile time
- Not composable: adding optional filters means string concatenation (SQL injection risk!)
- Database-specific: switching from PostgreSQL to MySQL might require rewriting
- No automatic relationship traversal

**For this specific reporting query:**
This is a complex analytical query with:
- Multi-table joins
- Aggregate functions
- Filtering and grouping
- Ordering by computed column

The ORM version is functional but not significantly more readable than the SQL version. Both do the same thing, but the SQL version is immediately recognizable to anyone who knows SQL, while the ORM version requires knowing SQLAlchemy's specific API.

For CRUD operations (simple reads, inserts, updates), the ORM is clearly better. But for complex analytical queries, raw SQL is often more readable and easier to optimize.

**Winner for reporting queries:** Raw SQL. It's more readable, easier to optimize (paste into DB tools), and gives access to database-specific features. BUT use parameterized queries (`:start` not f-strings) to prevent injection.

**For CRUD operations:** ORM is better (type safety, automatic relationships, less boilerplate).
</think>

**For this complex reporting query, raw SQL is better — more readable, easier to optimize, and gives access to full database features.**

### Evaluation

| Axis | ORM (SQLAlchemy) | Raw SQL |
|------|-----------------|---------|
| Readability | Requires SQLAlchemy knowledge | Any SQL developer can read |
| Optimizability | Must inspect generated SQL | Copy-paste into EXPLAIN ANALYZE |
| Composability | ✓ (add filters programmatically) | ✗ (string manipulation = risky) |
| Type safety | ✓ (IDE catches typos) | ✗ (runtime errors) |
| DB features | Limited (no CTEs, window functions) | Full access |
| Portability | Multi-database | Database-specific |

### When to use each

| Query type | ORM | Raw SQL |
|-----------|-----|---------|
| Simple CRUD (get user by ID) | ✓ Best | Overkill |
| List with filters/pagination | ✓ Best | OK |
| Complex reports/analytics | OK | ✓ Best |
| CTEs, window functions | ✗ Limited | ✓ Best |
| Bulk operations | ✗ Slow (N queries) | ✓ Best (one query) |
| Dynamic query building | ✓ Best | ✗ SQL injection risk |

### Hybrid approach (best of both)
```python
# CRUD: use ORM
user = db.session.query(User).get(user_id)

# Reports: use raw SQL
report = db.execute(text("""
    SELECT p.category, SUM(oi.quantity * oi.unit_price) AS revenue
    FROM products p
    JOIN order_items oi ON p.id = oi.product_id
    WHERE oi.created_at BETWEEN :start AND :end
    GROUP BY p.category
    ORDER BY revenue DESC
"""), {"start": start_date, "end": end_date}).fetchall()
```

### The reasoning pattern
Match the tool to the query complexity. ORMs excel at CRUD and simple queries where type safety and composability matter. Raw SQL excels at complex analytical queries where readability, performance tuning, and database-specific features matter. Using exclusively one or the other misses the strengths of each.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
