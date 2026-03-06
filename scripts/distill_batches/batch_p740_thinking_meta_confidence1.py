"""Phase 3D: Metacognition — Confidence Calibration Under Pressure (Part 1)

When uncertain, the model should express confidence levels honestly
rather than confabulating or giving false certainty.
"""

PAIRS = [
    (
        "thinking/meta-confidence-ambiguous-bug-500",
        r'''Our Flask API suddenly started returning 500 errors on the /checkout endpoint. It was working fine yesterday. No code was deployed. Can you tell me what's wrong?''',
        r'''<think>
I'm not fully certain about this. Let me assess what I know vs don't know.

What I'm confident about:
- 500 errors mean an unhandled exception in the server-side code
- "No code was deployed" narrows it down — the change is environmental, not code-related
- The endpoint was working yesterday, so the code itself likely isn't fundamentally broken

What I'm uncertain about:
- The actual error message — I don't have stack traces or logs
- Whether "no code deployed" is truly accurate (config changes? dependency updates? infrastructure changes?)
- Whether it's ALL /checkout requests or just some (specific input triggers it?)

What I definitely don't know:
- The error message in the logs
- Whether dependent services (database, payment provider, Redis) are healthy
- Whether a cert, API key, or token expired overnight
- Server resource state (disk full? OOM?)

Most likely causes (ranked by probability given "no code change"):

1. External dependency failure (HIGH probability)
   - Database connection refused or pool exhausted
   - Payment API (Stripe) key expired or service down
   - Redis down or connection timeout

2. Infrastructure issue (MEDIUM probability)
   - Disk full (can't write logs, temp files, sessions)
   - SSL certificate expired
   - DNS resolution failure for external services
   - Server ran out of memory

3. Configuration drift (MEDIUM probability)
   - Environment variable changed or removed
   - Config file modified outside deployment process
   - Automated security update broke a dependency

4. Data issue (LOW-MEDIUM probability)
   - Corrupt data in database that triggers an edge case
   - Auto-generated data (timestamps, sequences) hit a boundary

Given this uncertainty, I can't tell you exactly what's wrong, but I can help you diagnose it systematically.
</think>

I can't pinpoint the exact cause without more information, but here's a systematic diagnostic approach ranked by likelihood:

**Step 1: Check the error logs (30 seconds)**
```bash
# The stack trace tells you exactly what failed
tail -100 /var/log/myapp/error.log
# Or
journalctl -u myapp --since "1 hour ago" | grep -i error
```

**Step 2: Check dependent services (2 minutes)**
```bash
# Database
psql -h db-host -U app -c "SELECT 1"

# Redis
redis-cli ping

# External APIs (Stripe, etc.)
curl -s https://status.stripe.com/api/v2/status.json | jq '.status'
```

**Step 3: Check infrastructure (1 minute)**
```bash
df -h          # Disk full?
free -m        # Memory exhausted?
curl https://yourapp.com  # SSL cert expired? (browser will show)
```

**Step 4: Check environment (1 minute)**
```bash
# Did env vars change?
env | grep -i stripe   # API keys present?
env | grep -i database # DB config present?
```

**Most likely causes** (given "no code deployed"):

| Probability | Cause | Check |
|------------|-------|-------|
| High | External service down/key expired | Status pages + env vars |
| Medium | Disk full or OOM | `df -h`, `free -m` |
| Medium | SSL cert expired | `curl -vI https://yourapp.com` |
| Lower | DB connection pool exhausted | Check active connections |
| Lower | Data edge case | Check recent data changes |

The logs will almost certainly tell you the exact cause. Start there.'''
    ),
    (
        "thinking/meta-confidence-ambiguous-bug-intermittent",
        r'''Our users are reporting intermittent "connection reset" errors when uploading files. It happens maybe 20% of the time. The files are between 1MB and 50MB. We use Nginx → Gunicorn → Flask. What's causing this?''',
        r'''<think>
I'm not fully certain. Intermittent issues are the hardest to diagnose. Let me assess what I know.

What I'm confident about:
- "Connection reset" means the TCP connection was forcibly closed by one side
- 20% failure rate with varying file sizes suggests a timeout or resource limit, not a code bug
- The Nginx → Gunicorn → Flask chain has multiple points where timeouts can cut the connection

What I'm uncertain about:
- WHERE in the chain the reset happens (Nginx? Gunicorn? Flask? Client?)
- Whether it correlates with file size (do larger files fail more?)
- Whether it correlates with server load
- Whether the client is retrying and causing duplicate uploads

What I definitely don't know:
- Nginx configuration (client_max_body_size, proxy_read_timeout)
- Gunicorn configuration (timeout, workers)
- Whether there's a load balancer in front of Nginx
- Server resource usage during uploads
- Client-side network conditions

Most likely causes (ranked):

1. Gunicorn worker timeout (HIGH probability)
   - Default timeout is 30 seconds. Large file upload takes longer → worker killed mid-upload
   - Would explain intermittent behavior (small files succeed, large files timeout)

2. Nginx proxy timeout (HIGH probability)
   - proxy_read_timeout defaults to 60s. Slow upload → Nginx closes connection

3. Nginx client_max_body_size (MEDIUM probability)
   - Default is 1MB. Anything larger gets rejected with 413 (but error says "connection reset," not 413 — unless Nginx is misconfigured)

4. Load balancer timeout (MEDIUM if present)
   - AWS ALB default idle timeout is 60 seconds

5. Client network instability (LOW-MEDIUM)
   - Mobile users on flaky connections

I can give a diagnostic plan but can't be certain without seeing the configs.
</think>

I can't be certain without seeing your configuration, but **the most likely cause is a timeout** at one of several layers. Here's how to diagnose:

**Most probable causes (check in order):**

**1. Gunicorn worker timeout (most likely)**
```python
# Check your gunicorn config:
# Default timeout = 30 seconds. Upload takes longer → worker killed.
# Fix:
gunicorn --timeout 120 app:app  # Increase to 2 minutes

# Or use async workers for uploads:
gunicorn -k gevent --timeout 120 app:app
```

**2. Nginx proxy timeout**
```nginx
# Check nginx.conf — look for these:
location /upload {
    client_max_body_size 100M;      # Default is 1MB!
    proxy_read_timeout 120;          # Default is 60s
    proxy_send_timeout 120;
    proxy_connect_timeout 10;
    proxy_request_buffering off;     # Stream directly, don't buffer
}
```

**3. Load balancer (if applicable)**
```
AWS ALB:  Idle timeout default = 60s → increase to 120s
HAProxy:  timeout server default varies → check config
```

**Diagnostic steps:**

```bash
# 1. Check which layer resets the connection
# Upload a 50MB file while watching:
tail -f /var/log/nginx/error.log
tail -f /var/log/gunicorn/error.log

# 2. Check if it correlates with file size
# Try: 1MB (should work), 10MB, 30MB, 50MB

# 3. Check Nginx config
nginx -T | grep -E "client_max|proxy_.*timeout|body_size"

# 4. Check Gunicorn config
ps aux | grep gunicorn  # Check the command-line flags
```

**Things I'm uncertain about:**
- Whether a load balancer exists in front of Nginx
- Whether the issue is upload speed-dependent (slow connections timeout more)
- Whether Nginx is buffering the upload (proxy_request_buffering)

Start with the Nginx and Gunicorn timeout checks — they're the most common cause of intermittent upload failures.'''
    ),
    (
        "thinking/meta-confidence-undefined-requirements",
        r'''I need to build a "notification system" for our app. Can you help me design it?''',
        r'''<think>
I'm not fully certain what's needed here. "Notification system" is extremely broad. Let me assess what I know vs don't know.

What I'm confident about:
- Notification systems have several distinct dimensions: delivery channel (email, push, in-app, SMS), timing (real-time vs batched), persistence (read/unread state), and user preferences

What I'm uncertain about:
- Which delivery channels are needed (email only? push? in-app? SMS?)
- Whether notifications need to be persistent (stored and retrievable) or fire-and-forget
- What events trigger notifications
- Whether users need preference management (opt-in/out per type)
- The scale (10 notifications/day vs 10,000/minute)

What I definitely don't know:
- The application domain (e-commerce? social media? SaaS?)
- Current technology stack
- Whether real-time delivery is required
- Budget constraints (SMS costs money)
- Compliance requirements (GDPR opt-out, CAN-SPAM)

I should ask clarifying questions rather than guess and build the wrong thing.
</think>

I need more context before designing this. "Notification system" could mean very different things depending on your answers to these questions:

**Critical questions:**

1. **What channels?**
   - In-app only (toast/bell icon)?
   - Email?
   - Push notifications (mobile)?
   - SMS?
   - Slack/Teams?

2. **What triggers notifications?**
   - User actions (someone commented on your post)?
   - System events (your order shipped)?
   - Scheduled (your trial expires in 3 days)?
   - Admin broadcasts (system maintenance tonight)?

3. **Real-time or batched?**
   - Must appear instantly (chat messages)?
   - Can be batched (daily digest email)?

4. **Persistent?**
   - Need read/unread state and notification history?
   - Or fire-and-forget (just send, don't track)?

5. **User preferences?**
   - Can users opt out of specific notification types?
   - Can they choose channel per type (email for orders, push for messages)?

**Different answers lead to completely different architectures:**

| If you need... | Architecture |
|---------------|-------------|
| In-app only | Database table + polling or WebSocket |
| Email only | Background task (Celery) + email service |
| Real-time push | WebSocket or SSE + message queue |
| Multi-channel with preferences | Event-driven system + notification service |
| Simple alerts | Just send emails from your existing code |

**My assumption if you don't provide context:**
For a typical SaaS app, I'd start with in-app notifications (database + REST endpoint) plus email for important events. That covers 90% of use cases with minimal complexity.

Want me to design for a specific scenario, or should we start with the simplest version and iterate?'''
    ),
    (
        "thinking/meta-confidence-emerging-tech-htmx",
        r'''Should I use HTMX instead of React for my next web application? I heard it's the future of web development.''',
        r'''<think>
I'm not fully certain about the long-term trajectory here. Let me assess what I know.

What I'm confident about:
- HTMX is a library that lets you make AJAX requests directly from HTML attributes, avoiding JavaScript for many interactive patterns
- React is a mature, battle-tested UI framework with a massive ecosystem
- HTMX works best with server-rendered HTML (Django, Flask, Rails)
- React works best for complex, highly interactive UIs (dashboards, real-time collaboration)
- Both are legitimate tools for building web applications

What I'm uncertain about:
- Whether HTMX will maintain its current momentum or plateau
- Whether "the future" claims are hype or a genuine paradigm shift
- How well HTMX handles complex client-side state (form wizards, drag-and-drop, real-time updates)
- The long-term job market implications of choosing HTMX over React

What I definitely don't know:
- What kind of web application you're building
- Your team's existing skills
- How interactive the UI needs to be
- Whether you need mobile apps (React Native is an option with React)

I should give honest pros/cons without declaring a winner, because the right answer depends entirely on the use case.
</think>

**It depends entirely on what you're building.** Neither is universally "the future" — they solve different problems.

**I'm confident about these tradeoffs:**

| Factor | HTMX | React |
|--------|------|-------|
| Best for | Content sites, CRUD apps, server-rendered | Complex UIs, real-time, SPAs |
| Complexity | Much simpler | Steeper learning curve |
| Client-side JS | Near zero | Heavy (50-200KB bundle) |
| Server coupling | Tight (returns HTML) | Loose (returns JSON) |
| Ecosystem | Small but growing | Massive (libraries, tools, jobs) |
| Job market | Niche | Dominant |
| Mobile apps | No path to mobile | React Native |
| SEO | Natural (server-rendered) | Needs SSR (Next.js) |

**Choose HTMX if:**
- Building CRUD apps, admin panels, content sites
- Team knows Django/Flask/Rails, not JavaScript frameworks
- UI is mostly forms, tables, and page navigation
- Want to ship fast with minimal frontend complexity

**Choose React if:**
- Complex interactivity (drag-and-drop, real-time collaboration, rich editors)
- Need offline capability or PWA features
- Want to share code with React Native for mobile
- Team already knows React
- Building a SPA where the client manages complex state

**What I'm uncertain about:**
- Whether HTMX adoption will continue growing or stabilize at a niche
- How well HTMX handles the "80% HTMX, 20% complex JS" pattern in practice
- Whether the "back to server rendering" trend is permanent or cyclical

**My honest assessment:** HTMX is a great tool for the right use case, but calling it "the future" overstates it. React isn't going anywhere — it has too much ecosystem, too many developers, and handles complex UIs better. The real insight is that many apps don't NEED React's complexity, and HTMX lets you build those apps more simply.'''
    ),
    (
        "thinking/meta-confidence-no-consensus-orm",
        r'''What's the best practice for using ORMs in Python? Should I always use an ORM or write raw SQL?''',
        r'''<think>
I'm not fully certain about a single "best practice" here because the community genuinely doesn't agree. Let me be honest about this.

What I'm confident about:
- ORMs (SQLAlchemy, Django ORM) provide safety (SQL injection prevention), productivity (less boilerplate), and portability
- Raw SQL gives full control, better performance for complex queries, and access to DB-specific features
- Most production Python applications use an ORM for CRUD and raw SQL for complex queries — a hybrid approach
- The "ORM vs raw SQL" debate has been going on for 20+ years with no resolution

What I'm uncertain about:
- Whether newer ORMs (SQLModel, SQLAlchemy 2.0) have closed the performance gap enough to make raw SQL unnecessary for most use cases
- Whether the ORM overhead matters for any given application (it depends on query patterns)
- The "right" threshold where you should drop to raw SQL

What I definitely don't know:
- Your application's query complexity
- Your team's SQL proficiency
- Your performance requirements
- Whether you need database portability

There is no consensus "best practice." Anyone who tells you "always use ORM" or "never use ORM" is oversimplifying.
</think>

**There's no consensus best practice here.** The community is genuinely divided. Here's an honest assessment:

**The pragmatic middle ground (what most successful teams do):**
- **ORM for CRUD operations** — INSERT, simple SELECT, UPDATE, DELETE
- **Raw SQL for complex queries** — reports, analytics, complex JOINs, CTEs
- This isn't a cop-out — it's how Django, Flask, and FastAPI apps work in practice

**Arguments for ORM** (that I'm confident about):
- SQL injection prevention (parameterized by default)
- Less boilerplate for standard CRUD
- Relationship handling (eager loading, lazy loading)
- Migration tracking (Alembic, Django migrations)
- Database portability (if you actually need it)

**Arguments for raw SQL** (that I'm confident about):
- Full control over query structure and optimization
- Database-specific features (window functions, CTEs, JSONB operations)
- No ORM "magic" — what you write is what runs
- Better for complex analytics/reporting queries

**What I'm uncertain about:**
- Whether SQLAlchemy 2.0's improved type system and performance changes the calculus
- At what query complexity threshold an ORM becomes a hindrance (varies per developer)
- Whether the "just use SQL" trend is a lasting shift or a pendulum swing

**What the different camps say:**

| Camp | Argument | Valid when |
|------|---------|-----------|
| "Always ORM" | Prevents SQL injection, faster development | Simple CRUD apps |
| "Always raw SQL" | No abstraction leaks, full control | Data-heavy analytics |
| "Hybrid" | Best of both worlds | Most production apps |
| "Query builders" (SQLAlchemy Core) | SQL-like syntax, no object mapping | When ORM mapping is overhead but raw strings are risky |

**My honest recommendation:** Start with an ORM. When a specific query is awkward or slow in the ORM, drop to raw SQL for that query. Don't make a religious choice — use the right tool for each query.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
