"""Phase 3B: Metacognition — Reasoning Quality Evaluation (Part 9)
Final batch covering remaining scenario categories.
"""

PAIRS = [
    (
        "thinking/meta-reasoning-event-sourcing-vs-crud-db",
        r'''For tracking order history in an e-commerce system, compare:

CRUD (update in place):
```sql
UPDATE orders SET status = 'shipped', shipped_at = NOW() WHERE id = 123;
```

Event sourcing:
```python
# Store events, derive current state
events = [
    OrderCreated(order_id=123, items=[...], total=99.99, at="2024-01-10"),
    PaymentReceived(order_id=123, amount=99.99, at="2024-01-10"),
    OrderShipped(order_id=123, tracking="UPS123", at="2024-01-12"),
]

# Current state = replay all events
def get_order_state(events):
    state = {}
    for event in events:
        state = apply_event(state, event)
    return state
```

Which is better for order tracking?''',
        r'''<think>
For order tracking specifically, let me compare.

**CRUD:**
- Only stores current state: `status='shipped'`
- "When was it paid?" → need separate `paid_at` column
- "What was the status history?" → need a separate audit log
- Simple queries: `SELECT * FROM orders WHERE status = 'shipped'`
- Easy to implement

**Event sourcing:**
- Complete history by design: every state change is an event
- "When was it paid?" → find PaymentReceived event
- "Was the order modified after payment?" → events tell the whole story
- Can rebuild state at any point in time
- Can answer questions you didn't anticipate
- More complex queries (aggregate events to get current state)

**For ORDER TRACKING:**
Orders have a natural lifecycle with meaningful transitions:
Created → Paid → Processing → Shipped → Delivered → (possibly) Returned → Refunded

Each transition has important metadata (tracking numbers, payment IDs, timestamps). Users want to see order history ("your order was shipped on Jan 12").

Event sourcing naturally captures this history. CRUD requires building it separately (status_history table).

BUT: event sourcing for EVERYTHING is over-engineering. Most data (user profiles, product catalog) doesn't need full event history.

**Winner for order tracking:** Event sourcing fits naturally BUT a simpler solution (CRUD + status_history table) gives 90% of the benefit with 20% of the complexity.

Let me give a nuanced answer.
</think>

**Event sourcing fits order tracking naturally, but CRUD + a status history table gives 90% of the benefit with far less complexity.**

### Evaluation

| Axis | CRUD | Event sourcing |
|------|------|---------------|
| Implementation complexity | Low | High |
| Order history | ✗ (must add audit table) | ✓ (built-in) |
| Current state queries | ✓ (simple SELECT) | Complex (replay events) |
| Time-travel ("state at time X") | ✗ | ✓ |
| Analytics on transitions | Limited | Rich (any question answerable) |
| Storage | Lower | Higher (all events forever) |
| Learning curve | Low | High (new paradigm) |

### The practical middle ground
```sql
-- CRUD + history table (simple, covers 90% of needs)
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    status VARCHAR(20),
    total DECIMAL(10,2),
    updated_at TIMESTAMP
);

CREATE TABLE order_events (
    id SERIAL PRIMARY KEY,
    order_id INT REFERENCES orders(id),
    event_type VARCHAR(50),
    data JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Write: update current + append event
UPDATE orders SET status = 'shipped' WHERE id = 123;
INSERT INTO order_events (order_id, event_type, data)
VALUES (123, 'shipped', '{"tracking": "UPS123"}');
```

### When full event sourcing IS justified
- Financial systems (audit trail legally required)
- Complex workflows with many state transitions
- Need to answer historical questions not anticipated at design time
- CQRS architecture already in place

### The reasoning pattern
Event sourcing is powerful but complex. Before adopting it, ask: "Can I get what I need with CRUD + an audit/history table?" If yes, use the simpler approach. Reserve full event sourcing for domains where complete event history is a core requirement, not a nice-to-have.'''
    ),
    (
        "thinking/meta-reasoning-lambda-vs-container",
        r'''For a REST API backend, compare:

AWS Lambda (serverless):
```python
# handler.py
def lambda_handler(event, context):
    path = event['path']
    method = event['httpMethod']
    if path == '/api/users' and method == 'GET':
        return get_users()
    elif path == '/api/users' and method == 'POST':
        return create_user(json.loads(event['body']))
```

Container (ECS/Docker):
```python
# app.py
from fastapi import FastAPI
app = FastAPI()

@app.get("/api/users")
def get_users():
    return db.query(User).all()

@app.post("/api/users")
def create_user(data: UserCreate):
    user = User(**data.dict())
    db.add(user)
    db.commit()
    return user
```

Which is better for a typical REST API?''',
        r'''<think>
For a REST API backend, comparing serverless vs containers.

**Lambda (serverless):**
Pros:
- No server management: no patching, no scaling decisions
- Auto-scaling: 0 to thousands of instances automatically
- Pay-per-request: zero cost when idle
- Good for bursty traffic

Cons:
- Cold starts: first request after idle takes 1-5 seconds (with DB connection)
- 15-minute timeout limit
- Stateless: can't maintain DB connection pools
- Complex local development (need SAM/Serverless framework)
- Vendor lock-in (AWS-specific patterns)
- Debugging: CloudWatch logs are harder than local logs
- Cost at scale: continuous traffic is MORE expensive than containers

**Container (ECS/Docker):**
Pros:
- Persistent connections: DB connection pooling works naturally
- No cold starts: always running
- Standard framework (FastAPI, Django, Express)
- Easy local development (same Docker image)
- Predictable pricing at steady load
- Full control over runtime

Cons:
- Must manage scaling (auto-scaling rules, min/max instances)
- Pays even when idle
- Must manage infrastructure (ECS tasks, load balancer)
- More operational overhead

**For a typical REST API:**
- REST APIs typically have steady traffic, not bursty
- APIs need database connections (Lambda cold starts kill DB connections)
- APIs need consistent low latency (cold starts are unacceptable for p99)
- Standard frameworks (FastAPI, Django) work naturally in containers

**Winner:** Container for a typical REST API. Lambda for event-driven functions (webhooks, cron jobs, file processing).
</think>

**Containers are better for a typical REST API — consistent latency, persistent DB connections, and standard framework support.**

### Evaluation

| Axis | Lambda (serverless) | Container (ECS) |
|------|-------------------|----------------|
| Cold start latency | 1-5 seconds | None |
| DB connection pooling | ✗ (stateless) | ✓ |
| Auto-scaling | Automatic | Must configure |
| Cost when idle | $0 | Pays for min instances |
| Cost at steady load | Higher | Lower |
| Local development | Complex (SAM) | Simple (Docker) |
| Framework support | Limited | Full (FastAPI, Django) |
| Max request duration | 15 minutes | Unlimited |

### The cold start problem for APIs
```
Lambda API (user experience):
  First request: 3.2 seconds (cold start + DB connect)
  Second request: 50ms (warm)
  After 15 min idle: 3.2 seconds again!

Container API:
  Every request: 50ms (always warm)
```

### When Lambda IS the right choice
| Use case | Lambda | Container |
|----------|--------|-----------|
| REST API (steady traffic) | ✗ | ✓ |
| Webhook handler (sporadic) | ✓ | Overkill |
| Cron job (daily report) | ✓ | Overkill |
| Image processing (upload trigger) | ✓ | Fine |
| Real-time WebSocket | ✗ | ✓ |
| Background job queue | Maybe | ✓ |

### The reasoning pattern
Compute model should match workload pattern. Serverless excels at event-driven, sporadic, bursty workloads where pay-per-request and auto-scaling matter. Containers excel at persistent, steady workloads where connection pooling, consistent latency, and framework familiarity matter. Don't use Lambda for a workload that's always running — you'll pay more and get cold starts.'''
    ),
    (
        "thinking/meta-reasoning-next-vs-remix",
        r'''For a new full-stack web application, compare two React meta-frameworks:

Next.js:
```jsx
// app/posts/[id]/page.tsx (App Router)
export default async function Post({ params }) {
    const post = await fetchPost(params.id);
    return <Article post={post} />;
}

// Server Actions
async function createComment(formData) {
    'use server';
    await db.insert(comments).values({
        postId: formData.get('postId'),
        body: formData.get('body'),
    });
    revalidatePath('/posts/' + formData.get('postId'));
}
```

Remix:
```jsx
// app/routes/posts.$id.tsx
export async function loader({ params }) {
    return json(await fetchPost(params.id));
}

export async function action({ request }) {
    const form = await request.formData();
    await db.insert(comments).values({
        postId: form.get('postId'),
        body: form.get('body'),
    });
    return redirect(`/posts/${form.get('postId')}`);
}

export default function Post() {
    const post = useLoaderData();
    return <Article post={post} />;
}
```

For a typical web application, which framework?''',
        r'''<think>
Both are excellent React meta-frameworks. Let me compare for a typical web app.

**Next.js:**
- Market leader: largest community, most job postings, most tutorials
- Vercel backing: excellent hosting platform, optimized for Next.js
- App Router: React Server Components, streaming, server actions
- Ecosystem: huge library ecosystem compatible with Next.js
- ISR (Incremental Static Regeneration): unique feature for content sites
- Learning curve: moderate (App Router is newer, has quirks)

**Remix:**
- Web standards-first: uses native Form, FormData, Request/Response
- Progressive enhancement: works without JavaScript
- Nested routing with parallel data loading
- Better error boundaries and loading states
- Simpler mental model: loaders + actions (like PHP/Rails)
- Smaller community but very active
- Recently acquired by Shopify

**For a typical web application:**
Both handle the same use cases well. The main differences:

1. **Ecosystem and community**: Next.js has 10x more tutorials, libraries, and Stack Overflow answers
2. **Deployment**: Next.js is optimized for Vercel, works everywhere. Remix works everywhere equally.
3. **Mental model**: Remix is simpler (loader/action), Next.js is more complex (RSC, server actions, client/server boundaries)
4. **Progressive enhancement**: Remix forms work without JS. Next.js requires JS for most interactions.

**Winner:** Next.js for most teams, because the ecosystem advantage (tutorials, libraries, hiring) outweighs Remix's technical elegance. Remix is excellent for teams that value web standards and progressive enhancement.
</think>

**Next.js for most teams — the ecosystem, community, and deployment advantages outweigh Remix's technical elegance.**

### Evaluation

| Axis | Next.js | Remix |
|------|---------|-------|
| Community size | Very large | Growing |
| Tutorial/learning resources | Abundant | Moderate |
| Job market | More positions | Fewer positions |
| Progressive enhancement | Limited | ✓ (works without JS) |
| Mental model | Complex (RSC, boundaries) | Simpler (loader/action) |
| Deployment | Optimized for Vercel | Platform-agnostic |
| Static generation | ✓ (ISR, SSG) | Limited |
| Nested routes | ✓ | ✓ (with parallel loading) |
| Error handling | OK | Better (nested boundaries) |
| Web standards | Moving toward | Core principle |

### When to choose each
| Factor | Next.js | Remix |
|--------|---------|-------|
| Team familiarity | Most React devs know it | Less familiar |
| Content-heavy site | ✓ (ISR/SSG) | Works but fewer options |
| SaaS application | ✓ | ✓ |
| E-commerce | ✓ (Shopify Hydrogen uses Remix though!) | ✓ |
| Progressive enhancement critical | Consider Remix | ✓ |
| Deploy to Vercel | ✓ (optimized) | Works |
| Deploy to non-Vercel | Fine | Equally fine |

### The reasoning pattern
When two technologies are close in capability, ecosystem advantages (community size, tutorials, hiring pool, third-party libraries) often tip the balance. Next.js and Remix are both excellent — but Next.js's larger ecosystem makes it the safer default choice. Choose Remix when its specific strengths (web standards, progressive enhancement, simpler mental model) align with your project's priorities.'''
    ),
    (
        "thinking/meta-reasoning-playwright-vs-cypress",
        r'''For end-to-end testing of a web application, compare:

Cypress:
```javascript
describe('Login', () => {
    it('logs in successfully', () => {
        cy.visit('/login');
        cy.get('[data-testid="email"]').type('alice@test.com');
        cy.get('[data-testid="password"]').type('password123');
        cy.get('[data-testid="submit"]').click();
        cy.url().should('include', '/dashboard');
        cy.contains('Welcome, Alice');
    });
});
```

Playwright:
```javascript
test('logs in successfully', async ({ page }) => {
    await page.goto('/login');
    await page.getByTestId('email').fill('alice@test.com');
    await page.getByTestId('password').fill('password123');
    await page.getByTestId('submit').click();
    await expect(page).toHaveURL(/dashboard/);
    await expect(page.getByText('Welcome, Alice')).toBeVisible();
});
```

Which E2E testing tool is better?''',
        r'''<think>
Both are modern E2E testing tools. Let me compare on key axes.

**Cypress:**
- Chrome-focused (Chromium, Firefox, Edge, but NOT Safari/WebKit)
- Runs in-browser (same process as app)
- Excellent developer experience (time-travel debugging, live reloading)
- Component testing support
- Dashboard for CI integration (paid)
- Established community

**Playwright:**
- True cross-browser (Chromium, Firefox, WebKit/Safari)
- Runs out-of-browser (CDP/WebSocket)
- Multi-tab, multi-origin support
- API testing built-in
- Trace viewer for debugging (free)
- Microsoft backing (VS Code integration)
- Faster execution (parallel by default)

**Key differences:**
1. **Safari testing**: Playwright supports WebKit (Safari engine). Cypress doesn't. For web apps that must work on iOS Safari, this is critical.

2. **Multi-tab/origin**: Cypress can't test flows that span multiple tabs or origins. Playwright can.

3. **Parallelism**: Playwright runs tests in parallel by default. Cypress runs sequentially (parallel requires paid Dashboard).

4. **Speed**: Playwright is typically 2-3x faster due to parallelism and out-of-browser architecture.

5. **DX**: Cypress has slightly better interactive debugging (time-travel UI). Playwright's trace viewer is catching up.

**Winner:** Playwright. Cross-browser support (especially Safari), multi-tab capability, built-in parallelism, and speed advantages make it the better choice for most projects. Cypress's DX advantage is narrowing as Playwright improves.
</think>

**Playwright is the better choice — cross-browser support (including Safari), faster execution, and multi-tab testing give it clear advantages.**

### Evaluation

| Axis | Cypress | Playwright |
|------|---------|-----------|
| Chrome/Edge | ✓ | ✓ |
| Firefox | ✓ | ✓ |
| Safari/WebKit | ✗ | ✓ |
| Parallel execution | Paid (Dashboard) | Free (built-in) |
| Multi-tab testing | ✗ | ✓ |
| Multi-origin | ✗ | ✓ |
| Speed | Slower (sequential) | Faster (parallel) |
| Interactive debugging | ✓ (time-travel) | ✓ (trace viewer) |
| API testing | Plugin needed | Built-in |
| Component testing | ✓ | ✓ |
| Auto-waiting | ✓ | ✓ |
| Community | Established | Growing fast |

### The Safari gap
```
"Our app works in Chrome but breaks in Safari."
Cypress: "We can't test Safari. Hope for the best!"
Playwright: "We test WebKit (Safari's engine) in CI. Bug caught before production."
```

### Speed comparison (100 tests)
```
Cypress (sequential):   ~10 minutes
Playwright (parallel):  ~3 minutes (running on 4 workers)
```

### When Cypress IS still good
- Team already experienced with Cypress
- Simple app with Chrome-only users
- Value Cypress Dashboard's CI integration
- Component testing (Cypress component testing is mature)

### The reasoning pattern
For E2E testing tools, evaluate: browser coverage (does your user base include Safari?), parallelism (CI speed matters), and capability gaps (multi-tab, multi-origin). Playwright's technical advantages are significant and its DX is rapidly catching up to Cypress. For new projects, Playwright is the stronger default choice.'''
    ),
    (
        "thinking/meta-reasoning-sqlite-vs-postgres-small",
        r'''For a small internal tool used by 10 employees, compare:

SQLite:
```python
import sqlite3

conn = sqlite3.connect('app.db')  # file-based, zero config
cursor = conn.cursor()
cursor.execute("SELECT * FROM tasks WHERE assignee = ?", (user_id,))
tasks = cursor.fetchall()
```

PostgreSQL:
```python
import psycopg2

conn = psycopg2.connect("postgresql://user:pass@db-server:5432/app")
cursor = conn.cursor()
cursor.execute("SELECT * FROM tasks WHERE assignee = %s", (user_id,))
tasks = cursor.fetchall()
```

Which database for a small internal tool?''',
        r'''<think>
For a small internal tool with 10 users.

**SQLite:**
- Zero configuration: just a file on disk
- No server to run: embedded in the application
- No separate process: no connection management
- Backup: copy the file
- Deployment: just include the .db file
- Performance: excellent for read-heavy, low-concurrency workloads
- Concurrent writes: limited (file-level locking, WAL mode helps)

**PostgreSQL:**
- Requires server setup, maintenance, backups
- Connection management needed
- Far more features (JSONB, full-text search, window functions)
- Better concurrent write support
- Requires network connectivity
- More operational overhead

**For 10 employees using an internal tool:**
- Concurrency: 10 users making occasional requests. SQLite handles this easily (WAL mode supports concurrent reads + one writer).
- Data volume: internal tool, probably < 100K rows. SQLite handles millions of rows.
- Features needed: basic CRUD. SQLite provides all needed SQL features.
- Deployment: SQLite = deploy one file. PostgreSQL = maintain a database server.
- Maintenance: SQLite = zero maintenance. PostgreSQL = updates, backups, monitoring.

**Winner:** SQLite, overwhelmingly. It's simpler, has zero operational overhead, and handles this workload with ease. PostgreSQL would be significant operational overhead for zero benefit.
</think>

**SQLite, overwhelmingly. Zero operational overhead for a workload that doesn't need a database server.**

### Evaluation

| Axis | SQLite | PostgreSQL |
|------|--------|-----------|
| Setup | Zero (just a file) | Install + configure server |
| Maintenance | None | Updates, backups, monitoring |
| Deployment | Copy file | Maintain server |
| 10 concurrent users | ✓ (WAL mode) | ✓ (overkill) |
| Backup | Copy the .db file | pg_dump or streaming replication |
| Cost | $0 | Server costs |
| Advanced SQL | Most features | All features |
| Operational overhead | Zero | Significant |

### SQLite handles more than people think
```
SQLite capabilities:
- Concurrent reads: unlimited (WAL mode)
- Concurrent writes: one at a time (usually fine for internal tools)
- Database size: tested up to 281 TB
- Rows: handles billions
- Queries per second: 100,000+ reads
```

### When to upgrade to PostgreSQL
| Signal | Time to upgrade? |
|--------|-----------------|
| 10 users, basic CRUD | No (SQLite is perfect) |
| 100 users, some concurrent writes | Maybe |
| Need full-text search | Maybe (PostgreSQL FTS > SQLite FTS5) |
| Need JSONB queries | Yes |
| Multiple servers need same DB | Yes |
| > 1000 concurrent writes/sec | Yes |

### The reasoning pattern
Database choice should match workload scale. For small internal tools, SQLite eliminates an entire category of operational work (server management, backups, connection pooling, monitoring) while providing more than enough capability. Don't introduce infrastructure you don't need — it's not "just" a database server, it's an ongoing maintenance commitment.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
