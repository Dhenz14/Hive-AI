"""Phase 3F: Metacognition -- Code Quality Judgment (Part 10)

Rate code review decisions (approve/request changes/block) and API design
quality across real-world scenarios: migration PRs, large refactors, REST
endpoint design, error response formats, and WebSocket event schemas.
"""

PAIRS = [
    # ------------------------------------------------------------------ 1
    (
        "thinking/meta-quality-code-review-migration-indexes",
        r'''You are reviewing a PR that adds 4 new database indexes to improve query performance on a PostgreSQL production database with 200M+ rows. The PR includes:

```sql
-- migration 0047_add_performance_indexes.sql
CREATE INDEX CONCURRENTLY idx_orders_customer_date ON orders (customer_id, created_at);
CREATE INDEX CONCURRENTLY idx_orders_status ON orders (status) WHERE status IN ('pending', 'processing');
CREATE INDEX CONCURRENTLY idx_line_items_order ON line_items (order_id, product_id);
CREATE INDEX CONCURRENTLY idx_products_category ON products (category_id, is_active);
```

The PR description says "Adds indexes identified by pg_stat_statements analysis. Tested on staging." There is no rollback migration, no deployment runbook, and no mention of index build time or disk space impact.

Should you: Approve / Request Changes / Block?''',
        r'''<think>
Let me evaluate this PR across multiple review dimensions.

Code correctness: The SQL itself looks reasonable. CONCURRENTLY is used, which is good -- it avoids locking the table during index creation. The partial index on status is a nice optimization. Column ordering in composite indexes seems logical (high-cardinality column first for customer_id + created_at).

Missing rollback: This is the key concern. With 200M+ rows, if one of these indexes causes problems (disk space exhaustion, replication lag, unexpected query plan changes), there is no documented way to reverse. The rollback is simple (DROP INDEX), but it should be explicit in a down migration file.

Deployment risk on 200M+ rows: CREATE INDEX CONCURRENTLY on a 200M row table can take hours, consume significant I/O, and increase replication lag. The PR does not mention expected build time, disk space requirements, or whether this should be run during low-traffic periods.

No deployment runbook: For this kind of change, you want: (1) estimated build time from staging, (2) disk space needed, (3) monitoring during rollout, (4) order of index creation if one fails, (5) whether to run in a maintenance window.

Testing claim: "Tested on staging" is vague. Does staging have comparable data volume? Were query plans verified with EXPLAIN ANALYZE before and after?

Should this be blocked? No. The indexes themselves are correct and CONCURRENTLY is used. This is not a data-loss risk. But deploying without a rollback plan and operational context is risky enough to warrant changes before merge.

Verdict: Request Changes -- the SQL is fine but the operational safety net is missing.
</think>

**Verdict: Request Changes**

This is not a block -- the SQL is well-written and `CONCURRENTLY` avoids table locks. But deploying index changes to 200M+ row tables without operational safeguards is asking for trouble.

| Review Criterion              | Assessment | Notes                                     |
|-------------------------------|------------|-------------------------------------------|
| SQL correctness               | Good       | CONCURRENTLY used; column order reasonable |
| Partial index usage           | Good       | WHERE clause on status is efficient        |
| Rollback migration            | Missing    | No down migration with DROP INDEX          |
| Deployment documentation      | Missing    | No build time estimate or disk impact      |
| Testing evidence              | Weak       | "Tested on staging" with no details        |
| Risk level                    | Medium     | No data loss risk, but operational risk    |

**Changes to request:**

1. **Add a rollback migration:**
```sql
-- migration 0047_add_performance_indexes_down.sql
DROP INDEX CONCURRENTLY IF EXISTS idx_orders_customer_date;
DROP INDEX CONCURRENTLY IF EXISTS idx_orders_status;
DROP INDEX CONCURRENTLY IF EXISTS idx_line_items_order;
DROP INDEX CONCURRENTLY IF EXISTS idx_products_category;
```

2. **Add a deployment runbook in the PR description:**
   - Expected build time per index (measured on staging)
   - Estimated disk space increase
   - Recommended deployment window (off-peak)
   - Monitoring: watch `pg_stat_activity` for long-running index builds, check replication lag

3. **Include EXPLAIN ANALYZE evidence** showing query plan improvements on staging, so reviewers can verify the indexes actually help the intended queries.

4. **Consider sequential deployment** -- create indexes one at a time across separate deployments so that if one causes problems, it is easy to identify and revert.

A PR that adds these safeguards is an easy Approve.'''
    ),
    # ------------------------------------------------------------------ 2
    (
        "thinking/meta-quality-code-review-large-refactor",
        r'''You are reviewing a PR titled "Refactor: Extract Repository Pattern across all services." The diff touches 50 files across 8 microservices:

- Every service's database access is moved from inline queries to `Repository` classes
- The new `BaseRepository` generic class is 200 lines with type-parameterized CRUD
- All 50 files are production code changes
- Zero test files are modified or added
- The PR description says "No behavioral changes, just structural refactoring"
- CI pipeline passes (but the project has only 12% test coverage)

Example change in one file:
```python
# Before
class UserService:
    def get_user(self, user_id: str) -> User:
        row = db.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        return User(**row)

# After
class UserService:
    def __init__(self, repo: UserRepository):
        self.repo = repo

    def get_user(self, user_id: str) -> User:
        return self.repo.find_by_id(user_id)
```

Should you: Approve / Request Changes / Block?''',
        r'''<think>
This is a large-scale structural refactoring PR. Let me evaluate systematically.

Scope and risk: 50 files across 8 microservices is a massive blast radius. Even if each individual change is small, the cumulative risk of introducing a bug somewhere in 50 files is high. The claim of "no behavioral changes" is plausible for a repository extraction, but unverifiable without tests.

Test coverage: 12% test coverage means the existing test suite barely validates anything. CI passing means almost nothing -- it just proves the code compiles and the 12% of covered paths still work. The 88% of uncovered code paths could have regressions.

No tests added: This is the critical issue. The PR introduces a BaseRepository with 200 lines of new code (generic CRUD operations), and adds zero tests for it. The repository pattern is the foundation for all 8 services going forward -- if BaseRepository has a bug in its query building, every service is affected.

Also, the refactoring changes constructor signatures (adding repo dependency injection), which means all instantiation sites must be updated. Any missed callsite would fail at runtime, not at import time, and the test suite is too thin to catch this.

Positive aspects: The direction is good. Moving from inline SQL to repository pattern improves testability and maintainability. Dependency injection via constructor is the right approach. The code change shown is clean.

Can this be split? Absolutely. 50 files across 8 services should be 8 separate PRs (one per service), ideally with the BaseRepository extracted first as its own PR with thorough tests.

Verdict: Block. Not because the direction is wrong, but because the risk-to-verification ratio is unacceptable. A 50-file change with no tests and 12% existing coverage cannot be safely merged.
</think>

**Verdict: Block**

The architectural direction is excellent, but merging 50 files of structural changes with zero test coverage is reckless, regardless of CI passing.

| Review Criterion              | Assessment | Notes                                      |
|-------------------------------|------------|--------------------------------------------|
| Architectural direction       | Excellent  | Repository pattern is the right call        |
| Blast radius                  | Critical   | 50 files across 8 services in one PR       |
| Test coverage of changes      | Zero       | No new tests; 12% existing coverage         |
| Confidence CI catches bugs    | Very low   | 88% of code paths are unverified            |
| Behavioral correctness claim  | Unverifiable| "No changes" is plausible but not proven   |
| Reviewability                 | Poor       | 50 files is too large to review carefully   |

**Why Block, not Request Changes:**

Request Changes implies the PR is close and needs minor fixes. This PR needs a fundamental restructuring of its delivery strategy. Specifically:

1. **Split into incremental PRs:**
   - PR 1: `BaseRepository` class + comprehensive unit tests for it
   - PRs 2-9: One PR per microservice, each with tests for its Repository subclass
   - Each PR is independently reviewable, revertable, and deployable

2. **Every PR must include tests:**
   - `BaseRepository` needs unit tests for all CRUD operations, edge cases (not found, duplicate key, connection failure)
   - Each service Repository needs at least integration tests verifying SQL correctness
   - The refactored Service classes need tests verifying they delegate to the repository correctly

3. **Verify constructor injection sites:**
   - With the new `__init__(self, repo: UserRepository)` signature, every place that instantiates `UserService()` must be updated
   - Without tests, silent `TypeError` at runtime is likely in at least one of 50 files

**Feedback to the author:**

"Great direction -- the repository pattern will significantly improve our codebase. But this needs to land incrementally. Start with `BaseRepository` + tests as a standalone PR. Then migrate one service at a time, each with its own tests. With 12% test coverage, we cannot safely merge 50-file refactors without adding verification. Happy to pair on the test strategy."'''
    ),
    # ------------------------------------------------------------------ 3
    (
        "thinking/meta-quality-api-design-post-search",
        r'''Rate the API design quality of this search endpoint (1-10):

```
POST /api/v2/products/search
Content-Type: application/json

{
    "query": "wireless headphones",
    "filters": {
        "price_range": {"min": 20, "max": 200},
        "brands": ["Sony", "Bose", "JBL"],
        "ratings": {"min": 4.0},
        "in_stock": true,
        "categories": [
            {"id": "electronics", "subcategories": ["audio", "accessories"]}
        ]
    },
    "sort": {"field": "relevance", "order": "desc"},
    "pagination": {"page": 1, "per_page": 25},
    "facets": ["brand", "price_range", "rating"],
    "fields": ["id", "name", "price", "thumbnail_url"]
}

Response 200:
{
    "results": [...],
    "facets": {"brand": [{"value": "Sony", "count": 42}, ...]},
    "pagination": {"page": 1, "per_page": 25, "total": 387}
}
```''',
        r'''<think>
Let me evaluate this search API design across standard API design dimensions.

HTTP method choice -- POST for search: This is the most controversial aspect. REST purists would say search is a read operation and should use GET. However, there is a practical reason to use POST: the filter object is complex and deeply nested. Encoding nested category objects with subcategory arrays into query parameters is ugly and hits URL length limits (2048 chars in many browsers/proxies). Elasticsearch, GitHub's GraphQL API, and many production search systems use POST for search. This is a pragmatic and defensible choice.

Request body design: Well-structured with clear separation of concerns -- query, filters, sort, pagination, facets, and field selection are all distinct top-level keys. The filter structure supports range queries, multi-value filters, and nested category hierarchies. This is flexible and composable.

Pagination: Uses page/per_page which is simple and well-understood. Response includes total count. Cursor-based pagination would be better for deep pagination (page 1000+), but page-based is fine for search results where users rarely go past page 10.

Field selection: The "fields" parameter allows clients to request only needed fields, reducing payload size. Good practice.

Faceted search: Requesting facets in the query and receiving aggregated counts in the response is the standard pattern for e-commerce search. Well-designed.

Response structure: Clean and predictable. Results, facets, and pagination are clearly separated.

Missing aspects: No mention of caching strategy (POST requests are not cached by default -- this is a real downside). No request ID for tracing. No indication of search latency (some APIs include a "took_ms" field). No error response examples.

Versioning: Uses URL path versioning (/api/v2/), which is simple and explicit.

Score: 7/10 -- Well-designed search API with a pragmatic POST choice, but POST has caching implications that are not addressed.
</think>

**API Design Quality: 7/10**

| Criterion                     | Score | Notes                                           |
|-------------------------------|-------|-------------------------------------------------|
| HTTP method appropriateness   | 6/10  | POST for search is pragmatic but has trade-offs  |
| Request body structure        | 9/10  | Clean separation: query, filters, sort, pages    |
| Response structure            | 8/10  | Clear results + facets + pagination              |
| Filter expressiveness         | 9/10  | Ranges, multi-value, nested categories           |
| Cacheability                  | 3/10  | POST is not cached by HTTP infrastructure        |
| Field selection               | 9/10  | Sparse fieldsets reduce payload                  |
| Pagination design             | 7/10  | Page-based is fine for search; cursor better for deep pages |

**What is done well:**
- Request body is highly composable -- clients can include only the fields they need (filters, facets, fields are all optional)
- Faceted search response follows the established pattern (value + count pairs)
- Nested filter objects handle complex queries that would be painful as query params
- API versioning is present in the URL path

**Legitimate concerns with POST for search:**

1. **No HTTP caching** -- GET requests with the same URL are cached by browsers, CDNs, and proxies. POST requests are not. For a high-traffic search endpoint, this means every request hits your backend.

2. **Not bookmarkable/shareable** -- A GET URL with query params can be shared; a POST body cannot.

3. **Not idempotent by convention** -- Intermediaries (proxies, load balancers) may treat POST differently for retries.

**Recommendations to improve:**

```
# 1. Support GET for simple queries (cacheable, shareable)
GET /api/v2/products/search?q=wireless+headphones&brand=Sony&min_price=20&page=1

# 2. Keep POST for complex queries (practical necessity)
POST /api/v2/products/search
# Add cache headers for identical request bodies
X-Request-Fingerprint: sha256_of_body

# 3. Add operational metadata to responses
{
    "results": [...],
    "meta": {
        "took_ms": 47,
        "request_id": "req_abc123",
        "cache_hit": false
    }
}
```

Supporting both GET (simple) and POST (complex) gives you the best of both worlds and is a pattern used by Elasticsearch and Algolia.'''
    ),
    # ------------------------------------------------------------------ 4
    (
        "thinking/meta-quality-api-design-error-responses",
        r'''Rate the API design quality of these error responses (1-10):

```
POST /api/users
{"email": "invalid"}

Response 400:
{"error": true, "message": "Something went wrong"}

---

GET /api/users/999

Response 404:
{"error": true, "message": "Something went wrong"}

---

POST /api/orders
{"items": []}

Response 422:
{"error": true, "message": "Something went wrong"}

---

DELETE /api/users/5
(insufficient permissions)

Response 403:
{"error": true, "message": "Something went wrong"}
```''',
        r'''<think>
Let me evaluate these error responses across API design dimensions.

Error differentiation: Every single error response returns the exact same body: {"error": true, "message": "Something went wrong"}. The only differentiator is the HTTP status code. This is extremely poor. A 400 for invalid email, a 404 for missing resource, a 422 for empty items, and a 403 for permissions all return identical bodies. The client has no way to programmatically determine what went wrong or how to fix it.

Machine readability: The "error": true boolean is redundant -- the client already knows it is an error from the HTTP status code (4xx). The message is a generic string with no structured information. There are no error codes, no field-level validation errors, no documentation links.

Developer experience: A developer integrating this API will have a terrible debugging experience. When their request fails, they see "Something went wrong" and have to guess what they did wrong. No indication of which field failed validation, no hint about what the correct format should be.

Security consideration: There is one potential argument for generic messages -- avoiding information leakage. But this goes too far. You can provide structured error information without revealing internals. "email field must be a valid email address" is safe; "SQL syntax error at line 47" is not.

HTTP status code usage: The status codes themselves (400, 404, 422, 403) are appropriate for each scenario. That is the one thing done correctly.

Consistency: The response shape is consistent (same fields every time), but consistently useless.

Score: 1/10 -- HTTP status codes are correct, but the response bodies are completely worthless for debugging or programmatic error handling.
</think>

**API Design Quality: 1/10**

| Criterion                     | Score | Notes                                           |
|-------------------------------|-------|-------------------------------------------------|
| Error differentiation         | 0/3   | Identical message for all 4 error types          |
| Machine-readable error codes  | 0/2   | No error codes; no structured detail             |
| Field-level validation detail | 0/2   | 400 and 422 give no indication of which field    |
| Developer experience          | 0/2   | "Something went wrong" is zero-information       |
| HTTP status code usage        | 1/1   | Status codes (400/404/422/403) are appropriate   |

**This is the worst common API anti-pattern.** Identical generic error messages make the API nearly unusable for client developers. The only useful signal is the HTTP status code, which alone cannot tell you *what* went wrong.

**What a well-designed error response looks like:**

```json
// 400 - Validation error
{
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "Request validation failed",
        "details": [
            {
                "field": "email",
                "code": "INVALID_FORMAT",
                "message": "Must be a valid email address",
                "received": "invalid"
            }
        ]
    },
    "request_id": "req_abc123"
}

// 404 - Not found
{
    "error": {
        "code": "RESOURCE_NOT_FOUND",
        "message": "User with id '999' does not exist",
        "resource_type": "user",
        "resource_id": "999"
    },
    "request_id": "req_def456"
}

// 422 - Business logic error
{
    "error": {
        "code": "EMPTY_ORDER",
        "message": "Orders must contain at least one item",
        "details": [
            {"field": "items", "code": "MIN_LENGTH", "minimum": 1, "received": 0}
        ]
    },
    "request_id": "req_ghi789"
}

// 403 - Authorization error
{
    "error": {
        "code": "INSUFFICIENT_PERMISSIONS",
        "message": "You do not have permission to delete this user",
        "required_permission": "users:delete",
        "your_role": "viewer"
    },
    "request_id": "req_jkl012"
}
```

**Key principles for error responses:**
1. **Unique error codes** (`VALIDATION_ERROR`, `RESOURCE_NOT_FOUND`) -- clients can switch on these programmatically
2. **Human-readable messages** that explain what went wrong specifically
3. **Field-level details** for validation errors so forms can show inline errors
4. **Request ID** for correlating client errors with server logs
5. **Consistent envelope** (`error` object) but varying detail per error type'''
    ),
    # ------------------------------------------------------------------ 5
    (
        "thinking/meta-quality-api-design-websocket-events",
        r'''Rate the API design quality of these WebSocket events (1-10):

```javascript
// Event 1: New message
{"type": "msg", "d": {"txt": "Hello", "u": "user123", "ts": 1709654400}}

// Event 2: User joins channel
{"event_name": "USER_JOINED", "payload": {"userId": "user123", "channelId": "general"}}

// Event 3: Typing indicator
{"action": "typing_start", "data": {"user": "user123", "channel": "general"}}

// Event 4: Message deleted
{"t": "MESSAGE_DELETE", "d": {"message_id": "msg_456", "channel_id": "general"}}

// Event 5: Presence update
{"op": 3, "data": {"user_id": "user123", "status": "online"}}

// Event 6: Error
{"error": true, "reason": "rate_limited"}
```''',
        r'''<think>
Let me analyze these WebSocket events systematically.

Naming consistency: This is catastrophically inconsistent. Six events use six different conventions for the event type field:
- "type": "msg" (abbreviated)
- "event_name": "USER_JOINED" (SCREAMING_CASE)
- "action": "typing_start" (snake_case)
- "t": "MESSAGE_DELETE" (abbreviated key, SCREAMING_CASE value)
- "op": 3 (numeric opcode)
- "error": true (boolean flag, no type field at all)

The type field name changes between type, event_name, action, t, and op. This is not just inconsistent -- it means the client cannot write a single generic event router.

Payload field naming: Also inconsistent:
- "d" (abbreviated)
- "payload" (full word)
- "data" (different full word)
- "d" again

And within payloads, field naming varies: "u" vs "userId" vs "user" vs "user_id". Also "txt" vs full words. And camelCase (userId, channelId) vs snake_case (message_id, channel_id, user_id) within the same API.

Schema documentation: The user says "no schema documentation," which means clients have to reverse-engineer these formats. With the inconsistency shown, that would be extremely painful.

Timestamps: Only event 1 has a timestamp. There is no way to order events 2-6 or detect delayed delivery.

Sequence numbering: No sequence numbers, so the client cannot detect dropped messages or request replay.

Error handling: The error event (event 6) uses a completely different shape from all other events. There is no type/event field, no error code enum, and "reason" is a flat string.

This looks like 6 different developers each designed one event without coordination.

Score: 1/10 -- There is essentially no coherent design here, just accumulated ad-hoc events.
</think>

**API Design Quality: 1/10**

| Criterion                     | Score | Notes                                            |
|-------------------------------|-------|--------------------------------------------------|
| Naming consistency            | 0/3   | 6 different conventions for event type field     |
| Envelope structure            | 0/2   | type/event_name/action/t/op -- no standard       |
| Payload field naming          | 0/2   | camelCase, snake_case, and abbreviations mixed   |
| Schema documentation          | 0/1   | None                                             |
| Operational metadata          | 0/1   | No timestamps, no sequence numbers               |
| Error event design            | 1/1   | At least errors are distinguishable (barely)     |

**The inconsistencies catalogued:**

| Event          | Type field    | Type value       | Payload field | Field casing   |
|----------------|---------------|------------------|---------------|----------------|
| New message    | `type`        | `"msg"`          | `d`           | abbreviated    |
| User joined    | `event_name`  | `"USER_JOINED"`  | `payload`     | camelCase      |
| Typing         | `action`      | `"typing_start"` | `data`        | snake_case     |
| Msg deleted    | `t`           | `"MESSAGE_DELETE"`| `d`           | snake_case     |
| Presence       | `op`          | `3`              | `data`        | snake_case     |
| Error          | `error`       | `true`           | *(flat)*      | snake_case     |

A client cannot even write a generic event dispatcher because the type field name changes every time.

**Well-designed WebSocket protocol:**

```javascript
// Consistent envelope for ALL events
{
    "type": "message.created",       // always "type", always dot-notation
    "seq": 42,                       // monotonic sequence for gap detection
    "timestamp": "2025-03-01T12:00:00Z",  // always present
    "data": {                        // always "data"
        "message_id": "msg_123",     // always snake_case
        "text": "Hello",             // no abbreviations
        "user_id": "user_123",
        "channel_id": "general"
    }
}

// Same envelope for every event type
{"type": "channel.user_joined", "seq": 43, "timestamp": "...", "data": {"user_id": "...", "channel_id": "..."}}
{"type": "typing.started",      "seq": 44, "timestamp": "...", "data": {"user_id": "...", "channel_id": "..."}}
{"type": "message.deleted",     "seq": 45, "timestamp": "...", "data": {"message_id": "...", "channel_id": "..."}}
{"type": "presence.updated",    "seq": 46, "timestamp": "...", "data": {"user_id": "...", "status": "online"}}

// Errors use the same envelope
{"type": "error", "seq": 47, "timestamp": "...", "data": {"code": "RATE_LIMITED", "message": "Too many requests", "retry_after_ms": 5000}}
```

**Design rules to enforce:**
1. **One envelope shape** -- `type`, `seq`, `timestamp`, `data` on every event
2. **Dot-notation event names** -- `resource.action` (e.g., `message.created`)
3. **snake_case everywhere** -- fields, event names, no abbreviations
4. **Sequence numbers** -- monotonic integers so clients detect gaps and request replay
5. **Schema registry** -- publish JSON Schema or AsyncAPI spec for every event type'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
