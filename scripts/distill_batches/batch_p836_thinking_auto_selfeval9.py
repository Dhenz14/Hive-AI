"""Phase 4B: Self-Improvement — Self-Evaluation (Part 9)

Evaluating own architecture advice for soundness and appropriateness.
"""

PAIRS = [
    (
        "thinking/auto-selfeval-arch-microservices-recommendation",
        r'''A startup founder asked me about their architecture. They have 3 developers, 1 product, and 500 users. I'm about to recommend microservices. Let me evaluate whether that's appropriate:

My draft: "You should split your application into microservices: a User Service, an Order Service, a Notification Service, and an API Gateway. Use Kubernetes for orchestration, gRPC for inter-service communication, and Kafka for event streaming."''',
        r'''<think>
Let me evaluate this architecture recommendation:

**The context:**
- 3 developers
- 1 product
- 500 users
- Startup (presumably limited budget and time)

**My recommendation:** Microservices + Kubernetes + gRPC + Kafka

**Is this appropriate? ABSOLUTELY NOT.**

**Problem 1: Team size vs architecture complexity**
- Microservices require AT MINIMUM 1 developer per service for ownership
- With 3 developers and 4+ services, each person owns multiple services
- Operational overhead (monitoring, deployment, debugging) multiplies with each service
- A team of 3 should not operate Kubernetes

**Problem 2: Scale mismatch**
- 500 users can be served by a single $20/month server
- Kubernetes minimum: ~$200/month for a basic cluster
- Kafka minimum: ~$100/month managed, or significant ops overhead
- The infrastructure cost alone exceeds what 500 users justify

**Problem 3: Development speed**
- Microservices slow down development for small teams
- Every feature that crosses service boundaries requires coordinating multiple deployments
- Debugging distributed systems is dramatically harder
- A startup's priority is shipping features fast, not architectural elegance

**Problem 4: Premature optimization**
- "You should split into microservices" assumes they have scaling problems they don't have
- 500 users = maybe 5 requests per second = any framework on any hardware handles this

**What they actually need:**
- A monolith (Django, Rails, Laravel, or Next.js)
- A single database (PostgreSQL)
- A simple deployment (Heroku, Railway, or a single VPS)
- Focus on product-market fit, not infrastructure

**Verdict:** My recommendation would waste 6+ months of a 3-person team's time on infrastructure instead of product development. This could kill the startup.
</think>

**Self-evaluation: Microservices for a 3-person startup with 500 users is TERRIBLE advice. Rating: 1/10.**

**Why this recommendation could kill the startup:**

| Factor | Monolith | My microservices recommendation |
|--------|----------|-------------------------------|
| Time to deploy first feature | 1 day | 2-4 weeks (setup infrastructure first) |
| Monthly infrastructure cost | $20-50 | $300-500+ |
| Developers needed for ops | 0 (managed hosting) | 1 full-time (33% of the team!) |
| Debugging a bug | Read one log file | Trace across 4 services + API gateway |
| Adding a feature spanning user + orders | One code change | Coordinate 2 service deploys |

**What I should recommend instead:**

"For a 3-person team with 500 users, use a monolith:

```
Architecture: Django/Rails/Next.js monolith
Database:     PostgreSQL (single instance)
Hosting:      Heroku, Railway, or Render ($20-50/month)
Deployment:   git push (automatic)
```

**Why a monolith is RIGHT for you:**
1. Ship features in hours, not weeks
2. One codebase = everyone can work on everything
3. One deployment = no coordination overhead
4. $20/month vs $300/month on infrastructure
5. You can always extract microservices LATER when you actually need them

**When to consider microservices (not now):**
- 15+ developers stepping on each other in the same codebase
- 50,000+ users with different scaling needs per component
- Different parts of the system need different technology stacks
- You have a dedicated platform/DevOps team

The classic mistake is solving scaling problems you don't have yet."

**Self-evaluation lesson:** Always consider the team size, user scale, and business stage before recommending architecture. The best architecture is the one that lets the team ship the fastest with the resources they have.'''
    ),
    (
        "thinking/auto-selfeval-arch-database-choice",
        r'''A user is building a social media app and asked what database to use. I'm about to recommend MongoDB. Let me evaluate whether that's the right choice:

My draft: "Use MongoDB. It's great for social media because it's flexible (no schema), scales horizontally, and handles JSON natively. You can store user profiles, posts, and comments as documents."''',
        r'''<think>
Let me evaluate MongoDB for a social media app:

**What I said is correct:**
- MongoDB is schemaless (flexible) ✓
- MongoDB can scale horizontally (sharding) ✓
- MongoDB handles JSON/BSON natively ✓

**But is it the RIGHT recommendation?**

**Social media data patterns:**
1. User profiles — key-value, fits document model ✓
2. Posts with comments — nested documents ✓
3. Followers/following — MANY-TO-MANY relationships ✗
4. Likes — MANY-TO-MANY relationships ✗
5. Feed generation — complex JOINs across users, posts, follows ✗
6. Friend suggestions — graph traversal ✗
7. Trending topics — aggregations across all posts ✗

**The problem:** Social media is fundamentally about RELATIONSHIPS between entities. Who follows whom, who liked what, mutual friends, feed generation — these are all relationship queries.

**MongoDB's weakness is exactly relationships:**
- No JOINs (or expensive $lookup)
- Denormalization leads to data inconsistency (update a username? Update it in every post, comment, and like)
- "Get all posts from people I follow" requires multiple queries

**PostgreSQL would be better because:**
- Excellent at JOINs (followers, likes, comments all involve JOINs)
- JSONB column for flexible fields (schema flexibility when needed)
- Full-text search (built-in)
- Materialized views for feed generation
- Transactions for consistency (unlike MongoDB's eventual consistency for multi-document)

**Or even better:**
- PostgreSQL for core data (users, posts, follows)
- Redis for feed caching and real-time features
- Elasticsearch for search (if needed)

**Verdict:** MongoDB is a reasonable choice but not the best one. Social media's core challenge is relationships, and relational databases handle relationships better.
</think>

**Self-evaluation: MongoDB is not the best fit for social media. The core challenge is relationships, which is a relational database's strength. Rating: 4/10.**

**The mismatch:**
| Social media feature | Data pattern | MongoDB | PostgreSQL |
|---------------------|-------------|---------|------------|
| User profiles | Document | Great | Good (JSONB) |
| Posts with nested comments | Document | Great | Good |
| Followers/Following | Many-to-many | Weak | Excellent |
| News feed | JOINs across follows + posts | Very weak | Excellent |
| Likes | Many-to-many | Weak | Excellent |
| Friend suggestions | Graph query | Very weak | Good (recursive CTE) |
| Trending topics | Aggregation | Good | Excellent |

**What I should recommend instead:**

"For a social media app, I'd recommend **PostgreSQL** as your primary database:

```sql
-- Core tables (relational data):
CREATE TABLE users (id SERIAL PRIMARY KEY, name TEXT, profile JSONB);
CREATE TABLE posts (id SERIAL PRIMARY KEY, user_id INT REFERENCES users, content TEXT, created_at TIMESTAMPTZ);
CREATE TABLE follows (follower_id INT REFERENCES users, following_id INT REFERENCES users, PRIMARY KEY (follower_id, following_id));
CREATE TABLE likes (user_id INT REFERENCES users, post_id INT REFERENCES posts, PRIMARY KEY (user_id, post_id));

-- Feed query (posts from people I follow):
SELECT p.* FROM posts p
JOIN follows f ON f.following_id = p.user_id
WHERE f.follower_id = :current_user_id
ORDER BY p.created_at DESC
LIMIT 20;
-- This is a single, fast query with proper indexes
```

**Why PostgreSQL over MongoDB for social media:**
1. Follower/following queries are natural JOINs
2. Feed generation is a JOIN + sort (one query)
3. JSONB gives you schema flexibility when needed
4. Transactions keep like counts, follower counts consistent
5. Full-text search is built in

**Add Redis later for:**
- Caching pre-computed feeds
- Real-time notifications
- Session storage
- Rate limiting"

**Self-evaluation lesson:** Don't recommend a database because it's popular or "trendy." Match the database to the data access patterns. Social media = relationships = relational database.'''
    ),
    (
        "thinking/auto-selfeval-arch-caching-layer",
        r'''I recommended adding Redis caching to a user's application to fix slow response times. Let me evaluate whether I addressed the root cause:

User's problem: "Our API responses take 3-5 seconds. We have 100 concurrent users."

My draft: "Add Redis caching in front of your database queries. Cache the results for 5 minutes. This will bring response times down to <50ms for cached queries."''',
        r'''<think>
Let me evaluate my recommendation:

**What I said:**
- Add Redis caching ✓ (will help for repeated queries)
- Cache for 5 minutes ✓ (reasonable TTL)
- Response times <50ms for cached queries ✓ (accurate for cache hits)

**But did I address the ROOT CAUSE?**

**The problem:** 3-5 second response times with 100 concurrent users.

**My recommendation addresses the SYMPTOM, not the CAUSE.**

I don't know WHY the responses take 3-5 seconds. Possible causes:
1. **Slow database queries** — missing indexes, N+1 queries, full table scans
2. **Slow external API calls** — blocking on third-party services
3. **Insufficient server resources** — CPU/memory bottleneck
4. **Connection pool exhaustion** — database connections maxed out
5. **Synchronous processing** — not using async for I/O-bound work
6. **Large response payloads** — serializing too much data

**If I don't know the cause, caching might:**
- Mask the real problem (it's still 3-5s on cache miss)
- Add complexity without fixing the underlying issue
- Introduce cache invalidation bugs
- Give a false sense of "we fixed it" while cache misses are still awful

**What I should have done FIRST:**
1. Ask what the endpoint does (database? external API? computation?)
2. Ask for profiling data (where is the time spent?)
3. Recommend measuring BEFORE prescribing solutions

**Verdict:** I prescribed a solution without diagnosing the problem. Caching might help, but it's a band-aid if the underlying query takes 5 seconds.
</think>

**Self-evaluation: I prescribed a treatment without diagnosing the disease. Rating: 4/10.**

**The problem with jumping to caching:**
- First cache miss is STILL 3-5 seconds
- Cache invalidation adds complexity
- Users who see uncached responses still have a bad experience
- The real problem (why is it slow?) remains unfixed

**What I should have said:**

"Before adding caching, let's find out WHY responses take 3-5 seconds. The fix depends on the cause:

**Step 1: Profile the endpoint**
```python
import time

@app.route('/api/data')
def get_data():
    t0 = time.perf_counter()
    db_result = fetch_from_database()     # How long?
    t1 = time.perf_counter()
    api_result = call_external_api()       # How long?
    t2 = time.perf_counter()
    response = serialize(db_result, api_result)  # How long?
    t3 = time.perf_counter()

    print(f'DB: {t1-t0:.2f}s, API: {t2-t1:.2f}s, Serialize: {t3-t2:.2f}s')
    return jsonify(response)
```

**Step 2: Fix based on what's slow:**

| If slow part is... | Fix | Before caching? |
|--------------------|----|----------------|
| Database query (3s) | Add indexes, fix N+1, use EXPLAIN | Yes, fix first |
| External API (3s) | Add timeout, make async, add fallback | Cache is appropriate here |
| Serialization (3s) | Return fewer fields, paginate | Yes, fix first |
| Everything (1s each) | Multiple issues, fix individually | Then cache if still needed |

**Step 3: THEN consider caching if needed**

After fixing the root cause, if responses are 200-500ms and you need <50ms:
```python
# NOW caching makes sense — cache misses are 200ms, not 5 seconds
@app.route('/api/data')
def get_data():
    cached = redis.get('data:key')
    if cached:
        return cached  # <1ms

    result = fetch_data()  # 200ms (after optimization)
    redis.setex('data:key', 300, json.dumps(result))
    return jsonify(result)
```"

**Self-evaluation lesson:** Never prescribe solutions before diagnosing causes. "It's slow, add caching" is like "it hurts, take painkillers" — it might help symptoms but misses the broken bone underneath. Always profile first.'''
    ),
    (
        "thinking/auto-selfeval-arch-technology-stack",
        r'''A developer asked me what tech stack to use for their new project — a B2B SaaS application for project management. I'm about to recommend my favorite stack. Let me evaluate whether it's actually right for their needs:

My draft: "Use React + Next.js for the frontend, Go for the backend, and CockroachDB for the database. Deploy on Kubernetes with Terraform for infrastructure-as-code."''',
        r'''<think>
Let me evaluate this stack recommendation:

**The project:** B2B SaaS project management tool
**My recommendation:** React + Next.js, Go backend, CockroachDB, Kubernetes, Terraform

**Is this appropriate?**

**Problem 1: I'm recommending what I LIKE, not what FITS**
This reads like a "cool tech" stack, not a "right for this project" stack. Let me check each choice:

- **Go backend** — Go is great for high-performance services, but project management apps are CRUD-heavy, not performance-critical. Go requires more boilerplate for CRUD compared to Django or Rails.
- **CockroachDB** — Distributed SQL database designed for global scale. A project management SaaS doesn't need global distribution. PostgreSQL does everything needed at 1/10th the complexity.
- **Kubernetes** — Massive operational overhead for a new SaaS product. Unless they already have a DevOps team, this will consume weeks of setup time.
- **Terraform** — Good practice but premature for a new product that might pivot.
- **React + Next.js** — Actually reasonable for a SaaS frontend.

**Problem 2: I didn't ask about the team**
- What languages does the team know?
- How many developers?
- What's their timeline?
- What's their budget?

If it's 2 developers who know Python, recommending Go means they need to learn a new language while building their product.

**Problem 3: I didn't consider hiring**
B2B SaaS companies need to hire. The stack should use common technologies with large talent pools.

**Problem 4: Time to market**
A B2B SaaS needs to ship fast to validate the idea. Go + CockroachDB + K8s is an infrastructure project before it's a product.

**Better stack:** Something boring and productive.
- Next.js (frontend) or Rails/Django (full-stack)
- PostgreSQL
- Vercel/Render/Railway for hosting
- Stripe for billing
</think>

**Self-evaluation: I'm recommending my personal favorites, not what's right for the project. Rating: 3/10.**

**The problem:** I recommended a "cool tech" stack instead of a "ship fast" stack.

| My recommendation | What it optimizes for | What the project needs |
|-------------------|----------------------|----------------------|
| Go backend | Raw performance | Developer productivity |
| CockroachDB | Global distribution | Simple CRUD storage |
| Kubernetes | Massive scale | Quick deployment |
| Terraform | Infrastructure automation | Getting to market |

**What I should recommend instead:**

"For a B2B SaaS project management tool, optimize for **shipping speed** and **developer productivity**, not performance:

**Option A: Full-stack JavaScript (if team knows JS)**
```
Frontend: Next.js (React)
Backend:  Next.js API routes + Prisma ORM
Database: PostgreSQL
Auth:     NextAuth.js or Clerk
Payments: Stripe
Hosting:  Vercel + managed PostgreSQL (Neon/Supabase)
```
Time to MVP: 4-6 weeks

**Option B: Python full-stack (if team knows Python)**
```
Frontend: Django templates + htmx (or React SPA)
Backend:  Django
Database: PostgreSQL
Auth:     Django built-in auth
Payments: Stripe + Django
Hosting:  Railway or Render
```
Time to MVP: 3-5 weeks

**Option C: Ruby on Rails (fastest to MVP)**
```
Full stack: Rails 7 with Hotwire
Database:   PostgreSQL
Auth:       Devise
Payments:   Stripe
Hosting:    Render or Heroku
```
Time to MVP: 2-4 weeks

**Why these over Go + CockroachDB + K8s:**
- 10x faster to build CRUD features
- No infrastructure setup (managed hosting)
- Easy to hire for (huge talent pools)
- PostgreSQL handles 10,000+ concurrent users easily
- You can always migrate to more complex infrastructure AFTER product-market fit

**The startup graveyard is full of products with perfect architecture and zero users.** Ship first, optimize later."

**Self-evaluation lesson:** When recommending tech stacks, ask: What does the TEAM know? How fast do they need to ship? What's the actual scale? Then recommend the most BORING technology that meets those needs. Boring is a compliment in infrastructure.'''
    ),
    (
        "thinking/auto-selfeval-arch-api-design-pattern",
        r'''I recommended GraphQL for a new project. Let me evaluate whether REST would have been more appropriate:

Context: Internal tool with 3 pages, used by 20 people, built by 1 developer.

My draft: "Use GraphQL with Apollo Server. It gives you a strongly-typed schema, lets the client request exactly the data it needs, and provides automatic documentation with GraphQL Playground."''',
        r'''<think>
Let me evaluate GraphQL vs REST for this project:

**The context:**
- Internal tool (not public API)
- 3 pages
- 20 users
- 1 developer building it

**My recommendation: GraphQL + Apollo Server**

**What GraphQL gives you:**
- Strongly-typed schema ✓
- Client requests exactly what it needs ✓
- Auto-documentation ✓
- Flexible queries ✓

**What GraphQL COSTS:**
- Learning curve if the developer doesn't know it
- Schema definition overhead (types, resolvers, mutations)
- N+1 query problem (DataLoader needed)
- More complex error handling
- More complex caching (no HTTP caching by default)
- Apollo Server adds dependency weight

**For THIS project:**
- 3 pages = maybe 6-10 API endpoints. REST handles this trivially.
- 20 users = no performance concerns at all
- 1 developer = every hour spent on GraphQL infrastructure is an hour not spent on features
- Internal tool = no need for flexible client queries (the developer controls both frontend and backend)

**GraphQL excels when:**
- Multiple clients need different data shapes (mobile, web, third-party)
- Complex data with many relationships that clients query variably
- Public APIs where you can't predict client needs
- Large teams where frontend/backend develop independently

**None of those apply here.**

**REST for this project:**
- 6-10 simple endpoints
- No learning curve
- Built-in HTTP caching
- Simpler debugging (just curl)
- Done in a day instead of a week

**Verdict:** GraphQL is massive overkill. REST is the right choice for an internal tool this small.
</think>

**Self-evaluation: GraphQL is massive overkill for a 3-page internal tool built by 1 developer. Rating: 2/10.**

**Complexity comparison for this project:**

| Factor | REST | GraphQL |
|--------|------|---------|
| Setup time | 1 hour | 1-2 days |
| Endpoints for 3 pages | ~8 simple routes | Schema + resolvers + types |
| Learning curve | None (developer knows it) | Significant if new to GraphQL |
| N+1 prevention | Standard ORM patterns | Need DataLoader |
| Caching | Built-in HTTP caching | Manual implementation |
| Debugging | curl + browser | GraphQL Playground |
| Dependencies | None (framework built-in) | Apollo Server + client |

**What I should recommend:**

"For a 3-page internal tool used by 20 people, use simple REST endpoints:

```python
# That's it. 8 endpoints. Done in an afternoon.
GET  /api/projects          # List projects
POST /api/projects          # Create project
GET  /api/projects/:id      # Get project details
PUT  /api/projects/:id      # Update project
GET  /api/projects/:id/tasks   # List tasks for project
POST /api/projects/:id/tasks   # Create task
PUT  /api/tasks/:id         # Update task
GET  /api/stats             # Dashboard statistics
```

**Why not GraphQL:**
- You control both frontend and backend — you don't need query flexibility
- 20 users — no performance optimization needed
- 3 pages — the data requirements are simple and known
- 1 developer — every hour on infrastructure is an hour not on features

**When to upgrade to GraphQL:**
- You add a mobile app that needs different data from the web app
- You open your API to third-party integrators
- You have 50+ interconnected entities with variable query patterns
- You have separate frontend and backend teams"

**Self-evaluation lesson:** The best technology choice is the SIMPLEST one that meets the requirements. GraphQL solves real problems, but those problems don't exist in a 3-page internal tool.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
