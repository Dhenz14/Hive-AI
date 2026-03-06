"""Phase 2: Advanced Reasoning — Mixed Subcategories (Part 24)"""

PAIRS = [
    (
        "thinking/uncertainty-graphql-vs-rest",
        "Should we use GraphQL or REST for our new public API? We're building a developer platform and want a great developer experience.",
        r'''<think>
GraphQL vs REST for a public developer-facing API. This is actually one where REST wins for public APIs, though many assume GraphQL is always the better DX.

**REST for public APIs:**
Pros:
- Universal understanding (every developer knows REST)
- Cacheable by default (HTTP caching, CDNs, browsers)
- Simple to document (OpenAPI/Swagger is a mature standard)
- Easy to rate limit (per endpoint)
- Stable and predictable (endpoint = resource = documentation page)
- SDKs are straightforward to generate

Cons:
- Over/under-fetching (fixed response shapes)
- Multiple requests for related data
- Versioning challenges

**GraphQL for public APIs:**
Pros:
- Clients get exactly what they need (no over-fetching)
- Single endpoint
- Strong typing (schema is the documentation)
- Introspection
- Great for complex, nested data

Cons:
- Higher learning curve (not every developer knows GraphQL)
- Hard to cache (POST requests to single endpoint)
- Complex security (depth attacks, complexity attacks)
- Rate limiting is hard (what does "1 request" mean when queries vary?)
- Error handling is different from HTTP conventions
- Versioning is implicit (deprecation instead of versions)

**For a PUBLIC developer platform:**
Confidence: 70% REST. REST is the safer choice for public APIs because:
1. Lower barrier to entry (every developer knows REST)
2. Better caching (CDN, browser)
3. Simpler security model
4. Established tooling (Swagger, Postman, curl)

The 30% for GraphQL: if the data model is deeply nested and clients need very different subsets.
</think>

**70% confidence: REST for a public API.** GraphQL is often the better internal API, but for a public developer platform, REST has significant advantages.

## The Key Question: Who Are Your API Consumers?

```
PUBLIC API (developer platform):
  Consumers: thousands of external developers
  → They know REST already (every tutorial, every language, every tool)
  → They DON'T necessarily know GraphQL
  → They expect: GET /users/42, POST /orders, standard HTTP status codes
  → They use: curl, Postman, standard HTTP clients

  REST: "I know how to use this immediately"
  GraphQL: "I need to learn GraphQL first, then learn your schema"

INTERNAL API (your own frontend/mobile):
  Consumers: your team
  → They can learn GraphQL (and it's worth learning)
  → They need flexible queries (different views need different data)
  → They control both client and server

  GraphQL often wins internally.
```

## REST Advantages for Public APIs

```
1. CACHING (huge for developer platforms):
   REST:
     GET /api/products/42 → Cache-Control: max-age=300
     CDN caches this automatically. Browsers cache it.
     1 million requests → your server handles maybe 1000.

   GraphQL:
     POST /graphql { query: "{ product(id: 42) { name price } }" }
     POST requests are not cacheable by default.
     Every request hits your server.
     Caching requires custom infrastructure (persisted queries, etc.)

2. DOCUMENTATION:
   REST:
     OpenAPI/Swagger → interactive docs, auto-generated SDKs
     Each endpoint = one documentation page
     curl examples work directly

   GraphQL:
     Schema introspection + GraphiQL playground
     Good, but requires understanding GraphQL query language first

3. RATE LIMITING:
   REST:
     100 requests/minute per API key → clear, simple
     Each request = one operation = one rate limit hit

   GraphQL:
     What counts as "one request"?
     query { users { posts { comments { author } } } }
     → This is "one request" but could load millions of records
     → Need query cost analysis, not just request counting

4. SECURITY:
   REST: standard HTTP auth, CORS, per-endpoint permissions
   GraphQL: must handle depth attacks, complexity attacks, alias attacks
            (see GraphQL security discussion in earlier pairs)
```

## When GraphQL Wins

```
GRAPHQL IS BETTER WHEN:
  □ Clients need very different data shapes
    (mobile needs 3 fields, web needs 30, admin needs all)
  □ Data is deeply nested (social graph: users → friends → posts → comments)
  □ You control the clients (internal API)
  □ Multiple frontends with different needs
  □ Rapid frontend development (don't wait for backend to add endpoints)

REST IS BETTER WHEN:
  □ API is public-facing (lower barrier to entry)
  □ Caching is important (CDN, browser cache)
  □ Simple resource-based data model (CRUD operations)
  □ Security must be straightforward
  □ Rate limiting must be simple and fair
  □ You want maximum developer reach
```

## The Pragmatic Choice

```
FOR YOUR DEVELOPER PLATFORM:

  Start with REST:
  - Lower barrier to entry for external developers
  - Cacheable out of the box
  - Simple rate limiting and security
  - OpenAPI spec → auto-generate SDKs in every language
  - Every developer can test with curl

  Later, ADD GraphQL alongside REST (if needed):
  - Some platforms offer both (GitHub, Shopify)
  - REST for simple operations, GraphQL for complex queries
  - GraphQL as a power-user option

  DON'T start with GraphQL-only for a public API:
  - You'll lose developers who don't know GraphQL
  - You'll fight caching problems from day one
  - Rate limiting will be a constant challenge
```

**Uncertainty source:** If your data model is deeply nested (social network, knowledge graph) and clients genuinely need very different data shapes, GraphQL's flexibility could outweigh REST's simplicity. But for most developer platforms with CRUD-like operations, REST is the safer bet.'''
    ),
    (
        "thinking/causal-high-disk-usage-docker",
        "Our server's disk is 95% full. We have a 200GB disk and our application code is only 500MB. Where did all the space go?",
        r'''<think>
Server disk 95% full, application is only 500MB. 200GB disk. Something is consuming ~190GB that isn't the application code.

**Most common causes (in order of likelihood):**

1. **Docker images and volumes** — #1 cause on Docker servers
   - Old/unused Docker images accumulate (each can be 500MB-2GB)
   - Docker build cache
   - Anonymous volumes from stopped containers
   - Container logs (can grow unbounded)

2. **Log files** — #2 cause
   - Application logs without rotation
   - System logs (/var/log)
   - Docker container logs (JSON files in /var/lib/docker)

3. **Database data** — if running DB on same server
   - PostgreSQL WAL files
   - MySQL binary logs
   - Database backups

4. **Temp files / upload directories**
   - User uploads that were never cleaned up
   - Temp files from processing that weren't deleted

5. **Package manager caches**
   - npm cache, pip cache, apt cache

For a Docker-based deployment, the answer is almost always Docker + logs.
</think>

On a Docker-based server, the space is almost certainly consumed by **Docker artifacts and log files**. Let me show you how to find and fix it.

## Step 1: Find What's Using Space

```bash
# Overall disk usage summary
df -h /

# Find the biggest directories
du -h --max-depth=1 / 2>/dev/null | sort -rh | head -20

# Usually reveals:
# 80GB  /var/lib/docker     ← Docker images, containers, volumes
# 40GB  /var/log             ← Log files
# 30GB  /var/lib/postgresql  ← Database (if running locally)
# 20GB  /tmp or /uploads     ← Temp/upload files
```

## Most Likely Cause: Docker Bloat

```bash
# Check Docker disk usage
docker system df

# OUTPUT:
# TYPE            TOTAL    ACTIVE   SIZE     RECLAIMABLE
# Images          47       3        28.5GB   25.2GB (88%)
# Containers      12       2        15.3GB   14.8GB (96%)
# Local Volumes   23       4        45.1GB   38.7GB (85%)
# Build Cache     -        -        12.4GB   12.4GB

# 47 images but only 3 active → 44 unused images eating 25GB
# 23 volumes but only 4 active → 19 orphaned volumes eating 38GB
# Build cache → 12GB of old build layers

# FIX: clean up unused Docker resources
docker system prune -a --volumes
# Removes:
#   - All stopped containers
#   - All unused images (not just dangling)
#   - All unused volumes
#   - All build cache
# Can reclaim 50-100GB easily
```

## Second Most Likely: Container Logs

```bash
# Docker stores container logs as JSON files
# WITHOUT log rotation, they grow forever

# Find the biggest log files
find /var/lib/docker/containers -name "*.log" -exec du -h {} + | sort -rh | head

# OUTPUT:
# 45G /var/lib/docker/containers/abc123.../abc123...-json.log
# A single container's logs: 45GB!

# FIX 1: Truncate the current log
truncate -s 0 /var/lib/docker/containers/abc123.../abc123...-json.log

# FIX 2: Configure log rotation (prevent future growth)
# In docker-compose.yml:
services:
  app:
    image: your-app
    logging:
      driver: "json-file"
      options:
        max-size: "10m"    # Max 10MB per log file
        max-file: "3"      # Keep 3 rotated files
        # Total max: 30MB per container (instead of unlimited)

# OR globally in /etc/docker/daemon.json:
{
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "10m",
        "max-file": "3"
    }
}
# Restart Docker: systemctl restart docker
```

## Third: Application Logs

```bash
# Check /var/log
du -h --max-depth=1 /var/log | sort -rh

# Common offenders:
# syslog, kern.log, auth.log — usually managed by logrotate
# Your app's custom log files — might NOT be rotated

# Check if logrotate is configured for your app:
ls /etc/logrotate.d/

# Add logrotate config for your app:
cat > /etc/logrotate.d/myapp << 'EOF'
/var/log/myapp/*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
    copytruncate
}
EOF
```

## Prevention Checklist

```bash
# Run periodically (or add to cron):

# 1. Docker cleanup (safe — only removes unused resources)
docker system prune -f          # Remove stopped containers + dangling images
docker image prune -a -f        # Remove all unused images
docker volume prune -f          # Remove orphaned volumes

# 2. Add to crontab (weekly cleanup)
0 3 * * 0 docker system prune -af --volumes >> /var/log/docker-cleanup.log 2>&1

# 3. Monitor disk usage
# Alert when disk > 80%
df -h / | awk 'NR==2 {print $5}' | tr -d '%'
# If > 80 → alert
```

**Rule of thumb:** on a Docker server, run `docker system prune` monthly. Configure log rotation for all containers. These two steps prevent 90% of disk exhaustion issues.'''
    ),
    (
        "thinking/backtrack-orm-everywhere-to-mixed",
        "I've been using Django ORM for everything but some of my queries are extremely slow. My team lead says to use raw SQL for those but that feels wrong — shouldn't I stick with one approach?",
        r'''<think>
ORM everywhere vs raw SQL — this is a false dichotomy. The answer is to use each where it excels.

**Why the user feels it's wrong to mix:**
- Consistency (one approach throughout the codebase)
- Abstraction level (ORM abstracts SQL, why go back?)
- Fear of SQL injection (raw SQL = manual parameter handling)

**Why the ORM is slow for some queries:**
- Complex JOINs with aggregations
- Window functions
- Bulk operations
- CTEs (Common Table Expressions)
- Database-specific features (PostgreSQL's JSONB operations, full-text search)
- N+1 problems that are hard to solve with ORM

**The right mental model:**
- ORM = great for CRUD (Create, Read simple, Update, Delete)
- Raw SQL = great for complex queries (reports, analytics, bulk operations)
- This isn't a failure of the ORM — it's using the right tool for the job

**Backtrack from "ORM for everything" to "ORM for CRUD, SQL for complex queries"**
</think>

Using the ORM for everything is like using a Swiss Army knife for everything — it works, but sometimes you need a proper tool. **Mix them based on what each does best.**

## When ORM Excels (Keep Using It)

```python
# ✅ ORM is perfect for CRUD operations
# Simple, readable, database-agnostic, migration-friendly

# Create
user = User.objects.create(name="Dan", email="dan@example.com")

# Read (simple queries)
active_users = User.objects.filter(is_active=True)
user = User.objects.get(pk=42)

# Update
User.objects.filter(pk=42).update(name="Daniel")

# Delete
User.objects.filter(last_login__lt=one_year_ago).delete()

# Related objects
orders = user.orders.filter(status="pending").select_related("shipping_address")

# ORM handles: parameterization, SQL injection prevention,
# database compatibility, migrations, model validation
```

## When Raw SQL Is Better (Switch to It)

```python
# ❌ ORM: fighting the ORM to express a complex query
# "Top 10 customers by revenue in the last 30 days with running total"

# ORM attempt: awkward, slow, or impossible
from django.db.models import Sum, Window, F
from django.db.models.functions import Rank

# This might work but is hard to read and might generate bad SQL:
result = (Order.objects
    .filter(created_at__gte=thirty_days_ago)
    .values('user__name')
    .annotate(total=Sum('amount'))
    .annotate(rank=Window(expression=Rank(), order_by=F('total').desc()))
    .filter(rank__lte=10))
# Generated SQL may be suboptimal, hard to debug

# ✅ Raw SQL: clear, fast, uses database features directly
from django.db import connection

def top_customers_by_revenue(days=30):
    with connection.cursor() as cursor:
        cursor.execute("""
            WITH customer_revenue AS (
                SELECT
                    u.id,
                    u.name,
                    SUM(o.amount) as total_revenue,
                    COUNT(o.id) as order_count,
                    SUM(SUM(o.amount)) OVER (ORDER BY SUM(o.amount) DESC) as running_total
                FROM orders o
                JOIN users u ON u.id = o.user_id
                WHERE o.created_at >= NOW() - INTERVAL '%s days'
                GROUP BY u.id, u.name
                ORDER BY total_revenue DESC
                LIMIT 10
            )
            SELECT *,
                   ROUND(total_revenue * 100.0 / SUM(total_revenue) OVER (), 1) as pct
            FROM customer_revenue
        """, [days])  # Parameterized! No SQL injection risk

        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
```

## The Right Mental Model

```
USE ORM FOR:                     USE RAW SQL FOR:
  Simple CRUD                      Complex JOINs with aggregations
  Basic filtering                  Window functions
  Related objects (FK lookups)     CTEs (Common Table Expressions)
  Pagination                       Bulk operations (INSERT 10K rows)
  Most of your codebase (80%)      Reports and analytics
                                   Database-specific features
                                   Performance-critical queries
                                   The other 20%

THE RULE:
  If ORM generates clean, fast SQL → use ORM
  If you're fighting the ORM or it generates bad SQL → use raw SQL
  If in doubt, check EXPLAIN ANALYZE on the generated SQL
```

## Safe Raw SQL in Django

```python
# Always use parameterized queries (NEVER string formatting)

# ❌ DANGEROUS: SQL injection
cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")

# ✅ SAFE: parameterized
cursor.execute("SELECT * FROM users WHERE id = %s", [user_id])

# ✅ ALSO SAFE: Django's RawQuerySet (returns model instances)
users = User.objects.raw(
    "SELECT * FROM users WHERE email LIKE %s",
    ['%@company.com']
)

# Tip: wrap complex queries in a manager method
class OrderManager(models.Manager):
    def top_customers(self, days=30):
        return self.raw("""...""", [days])

# Usage remains clean:
Order.objects.top_customers(days=30)
```

There's no shame in raw SQL. The ORM is a tool for common cases. Raw SQL is a tool for complex cases. Use both where they shine.'''
    ),
    (
        "thinking/uncertainty-server-side-rendering-choice",
        "We're building a content-heavy marketing site with a blog, landing pages, and a small dashboard for logged-in users. Should we use Next.js with SSR, a traditional server-rendered approach like Django templates, or a SPA with React?",
        r'''<think>
Content-heavy marketing site + blog + landing pages + small dashboard. Let me analyze.

**Requirements breakdown:**
- Content-heavy pages → need SEO → need server-rendered HTML
- Blog → SEO critical, mostly static content
- Landing pages → SEO critical, mostly static
- Small dashboard → doesn't need SEO, can be client-rendered

**Options:**

1. **Next.js (SSR/SSG)**
   Good: SSG for blog/landing pages (fastest), SSR for dynamic pages, React for dashboard
   Bad: More complex deployment, JavaScript ecosystem overhead
   Best for: Teams that already know React, complex interactive pages

2. **Django templates (server-rendered)**
   Good: Simple, proven, fast for content sites, great admin panel built-in
   Bad: Less interactive without adding JS, dashboard would need separate JS framework or HTMX
   Best for: Content-first sites, Python teams, admin/CMS needs

3. **SPA (React only)**
   Good: Interactive dashboard experience
   Bad: Terrible for SEO (content rendered client-side), slower initial load
   Best for: Dashboard-only applications, NOT for content/marketing sites

**My recommendation:**
For content-heavy + blog + landing pages, this is primarily a CONTENT site.

If the team knows Python: Django + templates (with HTMX for interactivity)
If the team knows React: Next.js with static generation for content, SSR for dashboard

Confidence: 75% for "server-rendered approach" (Django templates OR Next.js SSG), 25% depends on team expertise.

SPA is wrong for this use case — SEO is critical for marketing/blog content.
</think>

**75% confidence: server-rendered (either Next.js SSG or Django templates), definitely NOT a pure SPA.**

Your site is primarily content — SEO is critical for marketing pages and blog.

## Why SPA Is Wrong for This

```
CONTENT-HEAVY MARKETING SITE NEEDS:
  ✓ Fast first paint (visitors bounce after 3 seconds)
  ✓ SEO (Google indexes your blog, landing pages, product pages)
  ✓ Social media previews (og:tags rendered server-side)
  ✓ Works without JavaScript (accessibility, crawlers)

SPA (Client-Side React):
  ✗ Blank page until JavaScript loads and executes
  ✗ Google MIGHT index it (unreliable)
  ✗ Social media crawlers see empty HTML (no previews)
  ✗ Slow first paint (download React + your code + API calls)

  SPA is for apps (dashboards, tools) — NOT for content sites.
```

## Option A: Next.js (If Your Team Knows React)

```
BLOG + LANDING PAGES:
  Static Generation (SSG) — HTML generated at build time
  → Fastest possible: pages served from CDN as static files
  → Perfect for content that changes infrequently

  // pages/blog/[slug].tsx
  export async function getStaticProps({ params }) {
    const post = await getPostBySlug(params.slug);
    return { props: { post }, revalidate: 3600 }; // Rebuild every hour
  }

DASHBOARD:
  Server-Side Rendering (SSR) — HTML generated per request
  → User-specific data, behind authentication
  → Still good SEO (not that dashboard needs it)

  // pages/dashboard.tsx
  export async function getServerSideProps(context) {
    const user = await getUser(context.req);
    return { props: { user } };
  }

PROS:
  ✓ One framework for everything
  ✓ React ecosystem for interactive components
  ✓ SSG for content (fast, CDN-cacheable)
  ✓ Vercel deployment is trivial

CONS:
  ✗ JavaScript ecosystem complexity
  ✗ Build times grow with content volume
  ✗ Overkill if the dashboard is simple
```

## Option B: Django Templates (If Your Team Knows Python)

```
BLOG + LANDING PAGES:
  Server-rendered HTML — fast, SEO-friendly, simple
  → Django's template system is battle-tested
  → Built-in admin panel for content management

  # views.py
  def blog_post(request, slug):
      post = get_object_or_404(BlogPost, slug=slug)
      return render(request, 'blog/post.html', {'post': post})

DASHBOARD:
  Django templates + HTMX for interactivity
  → No JavaScript framework needed for basic interactivity
  → HTMX: add dynamic behavior with HTML attributes

  <!-- dashboard.html -->
  <div hx-get="/api/stats" hx-trigger="load" hx-swap="innerHTML">
    Loading stats...
  </div>
  <!-- HTMX fetches /api/stats and inserts the HTML response -->

PROS:
  ✓ Simple and proven
  ✓ Built-in admin (great for blog CMS)
  ✓ Fast server rendering
  ✓ HTMX for interactivity without a JavaScript framework
  ✓ Python ecosystem (data processing, ML, automation)

CONS:
  ✗ Less interactive than React (for complex dashboard widgets)
  ✗ Need to add caching layer for high traffic (Django cache framework)
  ✗ If dashboard becomes complex, may need to add React anyway
```

## Decision Guide

```
YOUR TEAM KNOWS REACT:     → Next.js (SSG for content, SSR for dashboard)
YOUR TEAM KNOWS PYTHON:    → Django + templates + HTMX
YOUR TEAM KNOWS BOTH:      → Which is the dashboard more important?
                              Simple dashboard → Django
                              Complex dashboard → Next.js

CONTENT VOLUME:
  < 1000 pages:             → Either works fine
  > 10,000 pages:           → Django (no build step) or Next.js ISR

INTERACTIVITY NEEDS:
  Basic (forms, filters):   → Django + HTMX
  Complex (charts, drag-drop, real-time): → Next.js / React
```

**The 25% uncertainty:** if the dashboard is the primary product and will become highly interactive (charts, real-time updates, complex state), Next.js is the better investment even if the team currently knows Python. But for a "small dashboard" alongside a content site, Django + HTMX is the simpler path.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
