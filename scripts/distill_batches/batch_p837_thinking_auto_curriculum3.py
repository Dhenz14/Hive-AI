"""Phase 4C: Self-Improvement -- Curriculum Design (Part 3)

Designing comprehensive backend development learning curricula.
"""

PAIRS = [
    (
        "thinking/auto-curriculum-backend-beginner",
        r'''Design a backend development curriculum for someone who knows basic Python but has never built a web application. They want to become a backend developer in 6 months.''',
        r'''<think>
Designing a backend curriculum for a Python beginner:

**Current level:** Knows Python basics (variables, functions, loops, classes)
**Goal:** Backend developer capable of building and deploying web applications
**Timeline:** 6 months

**Key milestones:**
1. Month 1: HTTP, APIs, and first web framework (Flask)
2. Month 2: Databases and data modeling
3. Month 3: Authentication, security, and testing
4. Month 4: Advanced patterns and architecture
5. Month 5: Deployment, DevOps basics, and monitoring
6. Month 6: Capstone project + interview prep

**Principles:**
- Every week must produce something runnable
- Theory follows practice (build first, understand why later)
- Each concept builds on the previous one
- Real-world tools and patterns from day one
</think>

**6-Month Backend Development Curriculum**

**Prerequisites checklist (must know before starting):**
- [ ] Python: variables, functions, loops, conditionals
- [ ] Python: classes, modules, file I/O
- [ ] Command line basics (cd, ls, mkdir, pip)
- [ ] Git basics (clone, add, commit, push)

---

**Month 1: HTTP, APIs, and Flask**

```
Week 1: How the web works
  - What happens when you type a URL (DNS, HTTP, response)
  - HTTP methods: GET, POST, PUT, DELETE
  - Status codes: 200, 201, 301, 400, 401, 404, 500
  - Practice: Use curl to call public APIs (GitHub, JSONPlaceholder)
  - Project: Build an HTTP request logger that explains each part

Week 2: First Flask application
  - Hello World with Flask
  - Routes and URL parameters
  - Request and response objects
  - JSON responses
  - Project: Build a REST API for a to-do list (in-memory, no database)

Week 3: REST API design
  - Resource-based URLs (nouns, not verbs)
  - CRUD operations mapped to HTTP methods
  - Request validation and error responses
  - API versioning
  - Project: Extend to-do API with proper REST conventions

Week 4: Third-party API integration
  - Making HTTP requests with requests library
  - API keys and authentication
  - Rate limiting and error handling
  - Project: Build a weather dashboard API that aggregates data from
    OpenWeatherMap + geocoding APIs
```

**Month 2: Databases**

```
Week 5: SQL fundamentals
  - PostgreSQL setup and psql
  - CREATE TABLE, INSERT, SELECT, UPDATE, DELETE
  - WHERE, ORDER BY, LIMIT, GROUP BY
  - JOINs (INNER, LEFT, RIGHT)
  - Project: Write SQL queries for a bookstore database

Week 6: SQLAlchemy ORM
  - Models and table definitions
  - CRUD operations with ORM
  - Relationships (one-to-many, many-to-many)
  - Migrations with Alembic
  - Project: Replace in-memory to-do list with PostgreSQL

Week 7: Data modeling
  - Normalization (1NF, 2NF, 3NF)
  - When to denormalize
  - Indexes and query performance
  - EXPLAIN ANALYZE
  - Project: Design and implement a blog database (users, posts,
    comments, tags)

Week 8: Advanced database
  - Transactions and ACID
  - Connection pooling
  - Full-text search
  - Database seeding and fixtures
  - Project: Build a product catalog API with search and filtering
```

**Month 3: Auth, Security, and Testing**

```
Week 9: Authentication
  - Password hashing (bcrypt)
  - Session-based auth
  - JWT tokens
  - Login/register/logout flow
  - Project: Add user authentication to the blog API

Week 10: Authorization and security
  - Role-based access control
  - Input validation and sanitization
  - SQL injection prevention
  - CORS and CSRF protection
  - Rate limiting
  - Project: Add admin/user roles and secure all endpoints

Week 11: Testing
  - Unit tests with pytest
  - Testing Flask endpoints with test client
  - Fixtures and factories
  - Mocking external services
  - Test coverage
  - Project: Add tests to the blog API (aim for 80%+ coverage)

Week 12: Error handling and logging
  - Structured error responses
  - Application logging (Python logging module)
  - Exception handling strategies
  - Health check endpoints
  - Project: Add comprehensive error handling and logging to blog API
```

**Month 4: Advanced Patterns**

```
Week 13: Background tasks
  - Why background processing matters
  - Celery with Redis
  - Task queues and workers
  - Scheduled tasks (cron-like)
  - Project: Add email sending and report generation as background tasks

Week 14: Caching
  - In-memory caching (functools.lru_cache)
  - Redis caching
  - Cache invalidation strategies
  - HTTP caching headers
  - Project: Add Redis caching to the product catalog API

Week 15: File handling and storage
  - File uploads and validation
  - Cloud storage (S3)
  - Image processing and thumbnails
  - Serving static files
  - Project: Add profile picture upload to blog API

Week 16: WebSockets and real-time
  - WebSocket protocol
  - Flask-SocketIO
  - Real-time notifications
  - Project: Add real-time comment notifications to blog
```

**Month 5: Deployment and DevOps**

```
Week 17: Containerization
  - Docker basics (Dockerfile, docker-compose)
  - Containerizing a Flask app
  - Multi-container setup (app + database + Redis)
  - Project: Dockerize the blog application

Week 18: Deployment
  - Cloud deployment options (Heroku, Render, AWS)
  - Environment variables and configuration
  - SSL/HTTPS
  - Domain setup
  - Project: Deploy blog to production

Week 19: CI/CD
  - GitHub Actions
  - Automated testing pipeline
  - Automated deployment
  - Database migrations in production
  - Project: Set up CI/CD pipeline for blog

Week 20: Monitoring and observability
  - Application metrics (Prometheus)
  - Log aggregation
  - Error tracking (Sentry)
  - Uptime monitoring
  - Project: Add monitoring to deployed blog
```

**Month 6: Capstone and Job Prep**

```
Weeks 21-23: Capstone project
  Build a complete SaaS application from scratch:
  - User management with roles
  - Core business logic
  - REST API with documentation
  - Background task processing
  - Deployed with CI/CD
  - Monitored in production

  Suggested projects:
  - Project management tool (like Trello)
  - Invoice management system
  - URL shortener with analytics
  - Event booking platform

Week 24: Interview prep
  - System design basics
  - Common backend interview questions
  - Code review practice
  - Portfolio and resume review
```

**Resources per month:**
| Month | Primary resource | Practice |
|-------|-----------------|----------|
| 1 | Flask documentation + tutorial | Build 4 small APIs |
| 2 | SQLAlchemy docs + PostgreSQL tutorial | Design 3 schemas |
| 3 | OWASP Top 10 + pytest docs | Write 100+ tests |
| 4 | Redis docs + Celery tutorial | Add features to existing projects |
| 5 | Docker docs + cloud provider tutorial | Deploy 2 projects |
| 6 | System design primer | Build capstone |'''
    ),
    (
        "thinking/auto-curriculum-backend-api-design-path",
        r'''Design a learning path specifically for API design. A developer can build basic CRUD endpoints but their APIs are inconsistent and hard to use. What should they learn and in what order?''',
        r'''<think>
This developer can build APIs but they lack design skills. The gap is between "it works" and "it's well-designed."

**Key areas to cover:**
1. REST conventions and consistency
2. Error handling and status codes
3. Pagination, filtering, sorting
4. Versioning and evolution
5. Documentation
6. Authentication patterns
7. Advanced patterns (HATEOAS, batch operations)

**The order matters -- each concept builds on the previous:**
1. Naming and URL conventions (foundation)
2. Status codes and error responses (communication)
3. Input validation (robustness)
4. Pagination and filtering (scalability)
5. Authentication and authorization (security)
6. Documentation (usability)
7. Versioning and evolution (long-term maintenance)
8. Advanced patterns (mastery)
</think>

**API Design Learning Path**

*For developers who can build CRUD but want professional, consistent, developer-friendly APIs.*

**Phase 1: Foundations (Week 1-2)**

```
1. URL and naming conventions:
   Bad:  GET /getUsers, POST /createUser, GET /user_by_id?id=1
   Good: GET /users, POST /users, GET /users/1

   Rules to internalize:
   - URLs are nouns (resources), not verbs
   - Plural nouns: /users not /user
   - Hierarchy: /users/1/orders (user 1's orders)
   - Consistent casing: kebab-case for URLs, camelCase or snake_case for JSON

   Practice: Redesign 3 existing APIs to follow conventions.

2. HTTP methods as verbs:
   GET    = Read (safe, idempotent)
   POST   = Create (not idempotent)
   PUT    = Replace entirely (idempotent)
   PATCH  = Partial update (idempotent)
   DELETE = Remove (idempotent)

   Practice: Identify incorrect method usage in existing code.

3. Status codes (memorize these):
   200 OK, 201 Created, 204 No Content
   301 Moved, 304 Not Modified
   400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found
   409 Conflict, 422 Unprocessable Entity, 429 Too Many Requests
   500 Internal Server Error, 503 Service Unavailable

   Practice: Audit your existing endpoints for correct status codes.
```

**Phase 2: Error Handling (Week 3)**

```
4. Structured error responses:
   Every error should include:
   - HTTP status code (correct one, not always 500)
   - Machine-readable error code (VALIDATION_ERROR, NOT_FOUND)
   - Human-readable message
   - Details (which field failed, why)
   - Request ID (for debugging)

   {
     "error": {
       "code": "VALIDATION_ERROR",
       "message": "Request validation failed",
       "details": [
         {"field": "email", "message": "Invalid email format"}
       ]
     },
     "request_id": "req_abc123"
   }

   Practice: Implement a consistent error handler for all endpoints.

5. Input validation:
   - Validate at the API boundary (before business logic)
   - Return ALL validation errors at once (not one at a time)
   - Use schemas (Pydantic, Marshmallow, JSON Schema)
   - Distinguish client errors (4xx) from server errors (5xx)

   Practice: Add schema validation to every endpoint.
```

**Phase 3: Data Retrieval Patterns (Week 4-5)**

```
6. Pagination:
   - Offset pagination: ?page=2&per_page=20 (simple, good for admin UIs)
   - Cursor pagination: ?after=cursor_xyz (stable for feeds/timelines)
   - Always include metadata: total, has_next, page_count
   - Set maximum per_page (prevent abuse)

7. Filtering and sorting:
   - Consistent conventions: ?status=active&sort=-created_at
   - Multi-value filters: ?tag=python,javascript
   - Range filters: ?price_min=10&price_max=100
   - Search: ?q=search+term
   - Whitelist allowed filter/sort fields (security)

8. Field selection and expansion:
   - Sparse fields: ?fields=id,name,email (return only requested fields)
   - Related resources: ?include=orders,profile (include nested data)
   - Default to minimal response, expand on request

   Practice: Build a product catalog API with full filtering,
   sorting, pagination, and field selection.
```

**Phase 4: Security Patterns (Week 6-7)**

```
9. Authentication:
   - API keys (server-to-server)
   - JWT (user sessions)
   - OAuth 2.0 (third-party access)
   - When to use each

10. Authorization:
    - Role-based access control (RBAC)
    - Resource-level permissions (can only edit own resources)
    - Consistent 401 vs 403 usage
    - Rate limiting per user/tier

    Practice: Implement RBAC with tiered rate limits.
```

**Phase 5: Documentation and DX (Week 8)**

```
11. API documentation:
    - OpenAPI/Swagger specification
    - Auto-generated docs from code (flask-smorest, FastAPI)
    - Runnable examples (curl commands)
    - Error response documentation
    - Authentication guide

12. Developer experience:
    - Consistent naming across ALL endpoints
    - Predictable behavior (same patterns everywhere)
    - Helpful error messages (not "Bad Request" but "email field is required")
    - SDKs and client libraries

    Practice: Generate OpenAPI docs and have someone else
    try to use your API with only the docs.
```

**Phase 6: Evolution (Week 9-10)**

```
13. Versioning:
    - URL versioning (/v1/users)
    - Header versioning (Accept: application/vnd.api.v2+json)
    - Additive changes (non-breaking)
    - Deprecation process (Sunset headers, migration guides)

14. Breaking vs non-breaking changes:
    - Adding a field = safe
    - Removing a field = breaking
    - Changing a type = breaking
    - Making optional required = breaking

    Practice: Evolve an existing API from v1 to v2 with a migration plan.
```

**Phase 7: Advanced Patterns (Week 11-12)**

```
15. Batch operations:
    - Bulk create/update/delete
    - Partial success handling
    - Async operations with polling

16. Webhooks:
    - Event-driven integrations
    - Webhook security (signatures)
    - Retry policies
    - Webhook management endpoints

17. API design review checklist:
    - Consistent naming? Y
    - Correct status codes? Y
    - Structured errors? Y
    - Pagination on list endpoints? Y
    - Input validation? Y
    - Authentication on all endpoints? Y
    - Rate limiting? Y
    - Documentation? Y
    - Versioning strategy? Y

    Practice: Review and critique 3 public APIs
    (Stripe, GitHub, Twilio) -- what do they do well?
```

**Recommended reading order:**
1. Stripe API documentation (gold standard of API design)
2. GitHub API documentation (excellent REST implementation)
3. "API Design Patterns" by JJ Geewax
4. Zalando RESTful API Guidelines (comprehensive style guide)'''
    ),
    (
        "thinking/auto-curriculum-backend-database-mastery",
        r'''Design a curriculum for a developer who uses databases but doesn't really understand them. They can write basic SELECT queries but struggle with schema design, query optimization, and choosing the right database for a task.''',
        r'''<think>
This is a common gap -- many developers treat databases as black boxes. The curriculum needs to build deep understanding, not just syntax knowledge.

**Current state:** Can write SELECT, INSERT, UPDATE, DELETE. Uses an ORM for most things.
**Target state:** Can design schemas, optimize queries, choose databases, and troubleshoot performance.

**Key areas:**
1. Data modeling and schema design
2. Query optimization (indexes, EXPLAIN)
3. Transactions and consistency
4. Scaling strategies
5. NoSQL alternatives and when to use them
6. Operations (backup, monitoring, migration)

**Ordering principle:** Each level builds understanding that the next level requires.
</think>

**Database Mastery Curriculum**

*From "I can SELECT" to "I can design, optimize, and scale databases."*

**Level 1: Foundations -- How Databases Actually Work (Weeks 1-2)**

```
Goal: Understand what happens UNDER the hood when you run a query.

Topics:
1. Storage: How data is stored on disk (pages, rows, heap)
2. Indexes: What an index actually IS (B-tree data structure)
   - Without index: scan every row (sequential scan)
   - With index: jump directly to matching rows (index scan)
   - Why indexes make reads faster but writes slower

3. Query execution: What happens when you run a query
   - Parser -> Planner -> Executor
   - The query planner CHOOSES how to execute (not you)
   - EXPLAIN shows you the plan

4. Practical exercises:
   - Create a table with 1M rows
   - Run a query WITHOUT an index, note the time
   - Add an index, run the same query, note the improvement
   - Read the EXPLAIN output and understand each line

Milestone: Can explain why adding an index made a query faster,
using correct terminology (sequential scan vs index scan).
```

**Level 2: Schema Design (Weeks 3-5)**

```
Goal: Design database schemas that are correct, efficient, and maintainable.

Topics:
1. Normalization:
   - 1NF: No repeating groups (each cell has one value)
   - 2NF: No partial dependencies (every non-key depends on FULL key)
   - 3NF: No transitive dependencies
   - When to break normalization (read-heavy, reporting)

2. Relationships:
   - One-to-one (user -> profile)
   - One-to-many (user -> orders)
   - Many-to-many (students <-> courses via junction table)
   - Self-referential (employee -> manager)

3. Data types matter:
   - INT vs BIGINT (2B limit vs 9 quintillion)
   - VARCHAR(255) vs TEXT (does length matter?)
   - TIMESTAMP vs TIMESTAMPTZ (always use TIMESTAMPTZ)
   - UUID vs SERIAL for primary keys (tradeoffs)
   - JSONB for semi-structured data

4. Constraints:
   - PRIMARY KEY, FOREIGN KEY, UNIQUE, NOT NULL, CHECK
   - Cascading deletes (ON DELETE CASCADE vs RESTRICT)
   - Default values

5. Design exercises:
   - Design an e-commerce schema (users, products, orders, reviews)
   - Design a social media schema (users, posts, follows, likes)
   - Design a multi-tenant SaaS schema
   - Review and critique each other's designs

Milestone: Can design a normalized schema for a given business domain,
explain relationship choices, and justify data type selections.
```

**Level 3: Query Optimization (Weeks 6-8)**

```
Goal: Write efficient queries and fix slow ones.

Topics:
1. EXPLAIN ANALYZE deep dive:
   - Seq Scan, Index Scan, Index Only Scan, Bitmap Scan
   - Nested Loop, Hash Join, Merge Join
   - Cost estimates vs actual time
   - Reading the plan like a tree (innermost first)

2. Index design:
   - Single-column vs composite indexes
   - Column order in composite indexes (equality first, range last)
   - Covering indexes (INCLUDE clause)
   - Partial indexes (WHERE clause in index)
   - When NOT to index (low cardinality columns)

3. Query anti-patterns:
   - N+1 queries (the most common performance bug)
   - SELECT * (fetches unnecessary data)
   - Functions in WHERE clause (prevents index use)
   - OR conditions (often prevents index use)
   - Large OFFSET pagination (use cursor instead)

4. Window functions and CTEs:
   - ROW_NUMBER, RANK, DENSE_RANK
   - LAG, LEAD for comparing adjacent rows
   - Running totals and moving averages
   - Common Table Expressions (WITH clause)

5. Exercises:
   - Given 5 slow queries, use EXPLAIN to diagnose and fix each
   - Rewrite N+1 ORM code as efficient JOINs
   - Design indexes for a given query workload

Milestone: Can diagnose a slow query using EXPLAIN, identify the
cause, and fix it (add index, rewrite query, or restructure code).
```

**Level 4: Transactions and Consistency (Weeks 9-10)**

```
Goal: Understand data consistency and write correct concurrent code.

Topics:
1. ACID properties:
   - Atomicity: All or nothing
   - Consistency: Rules are always enforced
   - Isolation: Concurrent transactions don't interfere
   - Durability: Committed data survives crashes

2. Isolation levels:
   - Read Uncommitted (dirty reads)
   - Read Committed (default in PostgreSQL)
   - Repeatable Read
   - Serializable (strongest, slowest)

3. Common concurrency bugs:
   - Lost updates (read-modify-write without locking)
   - Phantom reads
   - Deadlocks (and how to avoid them)

4. Practical patterns:
   - SELECT ... FOR UPDATE (pessimistic locking)
   - Optimistic locking with version columns
   - Advisory locks for distributed coordination

5. Exercises:
   - Simulate a double-spend bug and fix it with transactions
   - Create a deadlock and resolve it
   - Implement optimistic locking for a counter

Milestone: Can explain why "UPDATE SET balance = balance - 100"
is safe but "read balance, calculate, write new balance" is not.
```

**Level 5: Scaling (Weeks 11-12)**

```
Goal: Know when and how to scale databases.

Topics:
1. Read scaling:
   - Read replicas
   - Connection pooling (PgBouncer)
   - Caching (Redis) to reduce database load

2. Write scaling:
   - Partitioning (range, hash, list)
   - Sharding strategies and tradeoffs
   - Write-ahead log and replication

3. Schema evolution:
   - Zero-downtime migrations
   - Adding columns without locking
   - Backfilling data safely
   - Blue-green database migrations

4. Monitoring:
   - pg_stat_statements (slow query log)
   - Connection count monitoring
   - Disk space and table bloat
   - VACUUM and maintenance

Milestone: Can plan a database scaling strategy for a growing
application, including when each technique is appropriate.
```

**Level 6: Beyond Relational (Week 13-14)**

```
Goal: Know when NOT to use PostgreSQL.

Topics:
1. Redis: Caching, sessions, rate limiting, pub/sub
2. MongoDB: Document storage, when schema flexibility matters
3. Elasticsearch: Full-text search, log analysis
4. Time-series databases: InfluxDB, TimescaleDB for metrics
5. Graph databases: Neo4j for relationship-heavy queries

Decision framework:
| Need | Best choice |
|------|-------------|
| Structured data with relationships | PostgreSQL |
| Caching and sessions | Redis |
| Full-text search | Elasticsearch |
| Flexible schemas with nested documents | MongoDB |
| Time-series metrics | TimescaleDB |
| Highly connected graph data | Neo4j |
| Default choice | PostgreSQL (it does most things well) |

Milestone: Can evaluate a new project's data needs and recommend
the right database(s) with specific reasoning.
```'''
    ),
    (
        "thinking/auto-curriculum-backend-scalability",
        r'''Design a learning path for understanding web application scalability. The learner can build a working web app but has no idea how to handle 10,000+ concurrent users.''',
        r'''<think>
Scalability is intimidating but follows predictable patterns. The key is teaching WHEN each technique is needed, not just how they work.

**Current level:** Can build and deploy a web app for small traffic
**Target level:** Can architect and scale for high traffic

**The progression should mirror how applications actually scale:**
1. Single server optimizations (get the most from what you have)
2. Database scaling (usually the first bottleneck)
3. Horizontal scaling (multiple app servers)
4. Caching strategies
5. Asynchronous processing
6. CDN and edge optimization
7. Microservices (only when needed)
</think>

**Web Application Scalability Learning Path**

*From "works for 100 users" to "works for 100,000 users"*

**Level 0: Baseline -- Understand Your Current Limits (Week 1)**

```
Before optimizing, measure what you have:

1. Load testing basics:
   - Use k6, locust, or hey to simulate traffic
   - Measure: requests/second, response time (p50, p95, p99)
   - Find: at what concurrency does performance degrade?

   Example:
   hey -n 10000 -c 100 http://your-app/api/endpoint
   -> 500 req/s at 200ms average? That handles ~40M requests/day

2. Identify your bottleneck:
   - CPU-bound? (high CPU, fast I/O) -> optimize code or add CPUs
   - I/O-bound? (low CPU, slow responses) -> optimize database or external calls
   - Memory-bound? (high memory, OOM) -> reduce memory usage or add RAM
   - Connection-bound? (connection pool exhausted) -> tune pool settings

3. The rule of thumb:
   - 1 server + PostgreSQL can handle 1,000-10,000 concurrent users
   - Most startups never need more than this
   - Optimize BEFORE scaling out

Milestone: Can load test your app and identify the bottleneck type.
```

**Level 1: Single Server Optimization (Weeks 2-3)**

```
Get 10x more from your single server:

1. Database optimization:
   - Add indexes for slow queries (use EXPLAIN)
   - Fix N+1 queries (use JOINs or eager loading)
   - Add connection pooling (PgBouncer)
   - Result: 5x-50x improvement on database-bound endpoints

2. Application optimization:
   - Profile your code (cProfile, py-spy)
   - Cache expensive computations (functools.lru_cache)
   - Use async for I/O-bound operations
   - Reduce response payload size (return only needed fields)
   - Result: 2x-5x improvement

3. Web server tuning:
   - Use gunicorn with multiple workers (not Flask dev server!)
   - Workers = 2 * CPU cores + 1
   - Use nginx as reverse proxy (static files, compression, buffering)
   - Enable gzip compression
   - Result: 3x-10x improvement

4. Practical exercise:
   - Deploy a Flask app behind nginx + gunicorn
   - Load test before and after each optimization
   - Document the improvement at each step

Milestone: Can take a slow single-server app from 50 req/s to 500+ req/s
through database, application, and server-level optimizations.
```

**Level 2: Caching (Weeks 4-5)**

```
The fastest request is one you don't have to process:

1. Response caching with Redis:
   - Cache full API responses for repeated queries
   - TTL-based expiration (5 min for product listings, 30s for user data)
   - Cache key design: include relevant parameters
   - Cache invalidation: delete on write, or use short TTLs

2. Database query caching:
   - Cache expensive aggregations (dashboard stats, report data)
   - Materialized views for complex queries
   - Application-level query result caching

3. HTTP caching:
   - Cache-Control headers for static assets
   - ETag and If-None-Match for conditional requests
   - CDN caching for static content (images, CSS, JS)

4. Cache hit rate monitoring:
   - Track hits vs misses
   - Target: >90% hit rate for cached endpoints
   - If hit rate is low, review TTL and key strategy

Typical result: 10x-100x improvement for cached endpoints
(from 200ms to <5ms)

Milestone: Can implement Redis caching with proper invalidation
and achieve >90% cache hit rate on appropriate endpoints.
```

**Level 3: Horizontal Scaling (Weeks 6-7)**

```
Multiple application servers behind a load balancer:

1. Stateless applications:
   - Sessions stored in Redis (not in-memory)
   - File uploads go to S3 (not local disk)
   - No server-specific state
   - Any request can go to any server

2. Load balancing:
   - nginx, HAProxy, or cloud load balancer (ALB)
   - Health checks (remove unhealthy servers)
   - Algorithms: round-robin, least connections, IP hash

3. Database scaling for reads:
   - Read replicas (writes to primary, reads from replicas)
   - Connection pooling per server
   - Read/write splitting in application code

4. Auto-scaling:
   - Scale based on CPU, memory, or request count
   - Minimum instances for availability
   - Maximum instances for cost control
   - Scale-down cooldown to prevent thrashing

Architecture:
   [Load Balancer]
      +-- [App Server 1]--+
      +-- [App Server 2]--+-- [Primary DB]
      +-- [App Server 3]--+      |
              |                   +-- [Read Replica]
              +-- [Redis Cache]

Milestone: Can deploy an auto-scaling application behind a load
balancer with read replicas and centralized session storage.
```

**Level 4: Async Processing (Weeks 8-9)**

```
Move slow work out of the request cycle:

1. Task queues (Celery + Redis/RabbitMQ):
   - Email sending
   - Report generation
   - Image processing
   - Data imports/exports
   - Webhook delivery

2. Event-driven architecture:
   - Publish events when things happen (order created, user signed up)
   - Consumers process events asynchronously
   - Decouple producers from consumers

3. Patterns:
   - Request -> create task -> return 202 Accepted -> poll for result
   - Request -> publish event -> consumers update their own data
   - Scheduled tasks (daily reports, cleanup jobs)

4. Practical exercise:
   - Move email sending to a background task
   - Implement a report generation endpoint that returns immediately
     and notifies the user when the report is ready
   - Handle task failures and retries

Milestone: Can identify which operations should be async and
implement a task queue with proper error handling and retries.
```

**Level 5: Advanced Scaling Patterns (Weeks 10-12)**

```
For when you truly need massive scale:

1. Database sharding:
   - When: single database can't handle write volume
   - How: partition data across multiple databases by shard key
   - Tradeoffs: cross-shard queries are hard, transactions limited
   - Alternatives: vertical partitioning, table partitioning first

2. CDN and edge computing:
   - Cache static assets at the edge (CloudFront, Cloudflare)
   - Cache API responses at the edge
   - Edge functions for simple logic (redirects, A/B testing)

3. Message queues for resilience:
   - Kafka for high-volume event streaming
   - RabbitMQ for reliable task delivery
   - Dead letter queues for failed messages
   - Idempotent consumers (handle duplicates safely)

4. Rate limiting and backpressure:
   - Protect your system from traffic spikes
   - Graceful degradation (serve cached/stale data under load)
   - Circuit breakers (stop calling failing services)
   - Queue-based load leveling

5. When to consider microservices:
   - Team is >15 developers
   - Different parts need different scaling
   - Independent deployment cycles needed
   - NOT just because it's "modern architecture"

Milestone: Can design a system architecture that handles 100K+
concurrent users with clear reasoning for each component.
```'''
    ),
    (
        "thinking/auto-curriculum-backend-system-design",
        r'''Design a curriculum specifically for system design interviews. The developer has 2 years of experience and struggles with the open-ended nature of system design questions.''',
        r'''<think>
System design interviews are different from coding interviews. The challenge is not technical knowledge but structured thinking under ambiguity.

**Common mistakes:**
1. Jumping to solutions without understanding requirements
2. Over-engineering (adding unnecessary complexity)
3. Not discussing tradeoffs
4. Focusing on one component and ignoring the full picture
5. Not considering scale from the start

**The curriculum needs:**
1. A repeatable framework for approaching any design question
2. Building blocks (databases, caches, queues, load balancers)
3. Practice with common questions
4. Estimation skills (back-of-envelope math)
</think>

**System Design Interview Curriculum**

*For developers who know how to build but struggle with designing at scale.*

**Phase 1: The Framework (Week 1)**

```
Learn a repeatable approach for ANY system design question:

Step 1: Clarify requirements (5 minutes)
   - Who are the users? How many?
   - What are the core features? (list 3-5, not 15)
   - What are the non-functional requirements? (latency, availability, consistency)
   - What's the scale? (requests/sec, data volume, growth rate)

Step 2: Back-of-envelope estimation (5 minutes)
   - Users -> requests/second
   - Data size -> storage requirements
   - Read/write ratio -> scaling strategy
   - Bandwidth -> CDN needs

Step 3: High-level design (10 minutes)
   - Draw the major components (clients, servers, databases, caches)
   - Show data flow for the main use case
   - Don't go deep yet -- get the big picture right

Step 4: Detailed design (15 minutes)
   - Dive into 2-3 critical components
   - Database schema for core entities
   - API design for main endpoints
   - Caching strategy

Step 5: Discuss tradeoffs and bottlenecks (5 minutes)
   - What are the single points of failure?
   - What happens when traffic 10x?
   - What did you trade off and why?

Practice: Use this framework on 3 different problems this week.
```

**Phase 2: Building Blocks (Weeks 2-3)**

```
Master the components you'll use in every design:

1. Load balancers:
   - What they do: distribute traffic across servers
   - Algorithms: round-robin, least connections
   - Layer 4 (TCP) vs Layer 7 (HTTP)
   - When to use: always for production web apps

2. Databases:
   - SQL vs NoSQL decision framework
   - Replication: primary-replica for read scaling
   - Partitioning: horizontal (sharding) for write scaling
   - When to use which: start SQL, add NoSQL for specific needs

3. Caching:
   - Cache-aside pattern (check cache, miss -> fetch, store)
   - Write-through (write to cache and DB together)
   - Write-behind (write to cache, async to DB)
   - Eviction: LRU, TTL
   - Technologies: Redis, Memcached, CDN

4. Message queues:
   - Decouple producers from consumers
   - Handle traffic spikes (queue absorbs burst)
   - Technologies: Kafka (high throughput), RabbitMQ (reliable delivery)
   - When to use: any async processing, cross-service communication

5. CDN:
   - Cache static content at edge locations
   - Reduce latency for geographically distributed users
   - When to use: always for static assets, optionally for API responses

6. Estimation reference card:
   | Resource | Approximate value |
   |----------|------------------|
   | Memory read | 100 ns |
   | SSD read | 100 us |
   | Network round trip | 500 us |
   | Disk read | 10 ms |
   | 1 server handles | 1K-10K req/s |
   | 1M users, 10% daily active | 100K DAU |
   | 100K DAU, avg 10 requests | 1M req/day = ~12 req/s |
```

**Phase 3: Common Design Problems (Weeks 4-7)**

```
Practice one design per week, using the framework:

Week 4: URL shortener (beginner)
   - Hash function for short URLs
   - Database: key-value or SQL
   - Redirect performance (cache hot URLs)
   - Analytics (click counting)
   - Scale: billions of URLs, thousands of redirects/sec

Week 5: Twitter/social feed (intermediate)
   - Fan-out on write vs fan-out on read
   - Feed generation and ranking
   - Social graph storage
   - Scale: millions of users, thousands of tweets/sec

Week 6: Chat system (intermediate)
   - WebSocket connections
   - Message storage and delivery
   - Online status tracking
   - Group chats
   - Scale: millions of concurrent connections

Week 7: Video streaming (advanced)
   - Upload pipeline (transcode, store, CDN)
   - Adaptive bitrate streaming
   - Recommendation system (high level)
   - Scale: petabytes of video, millions of concurrent viewers

For each design, write up:
   - Requirements and estimations
   - Architecture diagram
   - Key design decisions and tradeoffs
   - How it scales from 1K to 1M users
```

**Phase 4: Deep Dives (Weeks 8-9)**

```
Interviewers will pick components to dig into. Be ready for:

1. Database deep dive:
   - Schema design choices and tradeoffs
   - Indexing strategy
   - Sharding key selection
   - Consistency vs availability tradeoffs (CAP theorem in practice)

2. Caching deep dive:
   - Cache invalidation strategies
   - Thundering herd prevention
   - Cache consistency with database
   - Multi-level caching (L1 app cache -> L2 Redis -> database)

3. Consistency deep dive:
   - Strong vs eventual consistency
   - When eventual consistency is acceptable (likes, view counts)
   - When strong consistency is required (payments, inventory)
   - Distributed transactions and their alternatives (Saga pattern)

4. Availability deep dive:
   - Failover strategies
   - Data replication across regions
   - Graceful degradation (serve stale data when database is down)
   - Chaos engineering concepts
```

**Phase 5: Mock Interviews (Weeks 10-12)**

```
Practice under realistic conditions:

1. Time yourself (40 minutes per design)
2. Practice with a partner (take turns being interviewer)
3. Record yourself and review:
   - Did you clarify requirements first?
   - Did you estimate scale?
   - Did you discuss tradeoffs?
   - Did you identify bottlenecks?

Common feedback points:
   - "You jumped to microservices without justifying why"
   - "You didn't consider the read/write ratio"
   - "You designed for Google scale but the problem is Etsy scale"
   - "You mentioned caching but didn't discuss invalidation"

4. Do at least 6 mock designs before your interview:
   - Design a rate limiter
   - Design a notification system
   - Design a search autocomplete
   - Design a file storage service (like Dropbox)
   - Design a payment system
   - Design a metrics/monitoring system
```

**Interview day checklist:**
- [ ] Bring a framework (clarify -> estimate -> design -> detail -> tradeoffs)
- [ ] Ask clarifying questions (don't assume)
- [ ] State your assumptions explicitly
- [ ] Discuss tradeoffs, not just solutions
- [ ] Draw diagrams (even in virtual interviews)
- [ ] Start simple, add complexity as needed
- [ ] Don't try to impress with jargon -- explain clearly'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
