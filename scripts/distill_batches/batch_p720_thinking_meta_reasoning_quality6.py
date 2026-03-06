"""Phase 3B: Metacognition — Reasoning Quality Evaluation (Part 6)
Remaining scenarios to complete Phase 3B target.
"""

PAIRS = [
    (
        "thinking/meta-reasoning-sql-vs-nosql-social",
        r'''For a social media app with user profiles, posts, comments, likes, and follower relationships, compare:

PostgreSQL:
```sql
CREATE TABLE users (id SERIAL PRIMARY KEY, username VARCHAR(50), bio TEXT);
CREATE TABLE posts (id SERIAL PRIMARY KEY, user_id INT REFERENCES users(id), content TEXT, created_at TIMESTAMP);
CREATE TABLE comments (id SERIAL PRIMARY KEY, post_id INT REFERENCES posts(id), user_id INT REFERENCES users(id), body TEXT);
CREATE TABLE likes (user_id INT, post_id INT, PRIMARY KEY(user_id, post_id));
CREATE TABLE follows (follower_id INT, following_id INT, PRIMARY KEY(follower_id, following_id));
```

MongoDB:
```javascript
// posts collection
{
  _id: ObjectId("..."),
  author: { _id: "user123", username: "alice" },
  content: "Hello world",
  comments: [
    { user: { _id: "user456", username: "bob" }, body: "Nice!" },
  ],
  likes: ["user123", "user789"],
  likeCount: 2,
  createdAt: ISODate("...")
}
```

Which database for this social media app?''',
        r'''<think>
Let me evaluate for a social media app.

**PostgreSQL for social media:**

The follower/following relationship is a classic graph relationship. PostgreSQL handles this with a join table (`follows`) and can query "who does Alice follow?" or "who follows Alice?" efficiently with indexes.

Getting a user's feed (posts from people they follow):
```sql
SELECT p.* FROM posts p
JOIN follows f ON f.following_id = p.user_id
WHERE f.follower_id = :user_id
ORDER BY p.created_at DESC
LIMIT 20;
```
This is a well-indexed query that performs well.

Likes, comments, counts — all well-served by SQL aggregation.

Data integrity: foreign keys ensure posts can't reference non-existent users, comments can't reference non-existent posts. CASCADE delete handles cleanup.

**MongoDB for social media:**

Embedding comments and likes in the post document makes reading a post fast — one document fetch gets everything.

BUT:
1. Document size limit: MongoDB documents max at 16MB. A viral post with 100,000 comments can't embed them all.
2. Updating embedded arrays is expensive: adding a comment requires updating the entire post document.
3. Data denormalization: `author.username` is copied into every post. If Alice changes her username, you must update EVERY post and comment.
4. Cross-collection queries: "How many total likes does Alice have?" requires aggregation across all posts.
5. Follower graph: requires a separate collection anyway, losing the "document-first" advantage.

**For social media specifically:**
Social media is highly RELATIONAL — users follow users, users like posts, users comment on posts, posts belong to users. This is exactly what relational databases are designed for.

MongoDB's document model works for posts (embed recent comments), but the relationships between entities (follows, likes, cross-user queries) are a better fit for SQL.

**Winner:** PostgreSQL. Social media is fundamentally a graph of relationships, which is exactly what relational databases model. MongoDB's document model creates data denormalization headaches that grow worse as the app scales.
</think>

**PostgreSQL is better for social media — the data is fundamentally relational (users → follow → users, users → like → posts).**

### Evaluation

| Axis | PostgreSQL | MongoDB |
|------|-----------|---------|
| Relationship queries | ✓ Native JOINs | ✗ Manual cross-collection |
| Data integrity | Foreign keys, cascades | Manual enforcement |
| Schema evolution | ALTER TABLE (safe) | Flexible (but inconsistent data) |
| Read single post | JOIN (still fast) | One document fetch (fastest) |
| User feed query | ✓ JOIN follows + posts | ✗ Expensive aggregation |
| "All likes by user" | ✓ Simple query | ✗ Scan all posts |
| Username change | ✓ Update one row | ✗ Update every post/comment |
| Viral post (100K comments) | ✓ Separate table rows | ✗ 16MB document limit |

### The denormalization problem
```javascript
// MongoDB: Alice changes username
// Must update EVERY document where she's referenced:
db.posts.updateMany({"author._id": "alice"}, {$set: {"author.username": "alice_new"}});
db.posts.updateMany({"comments.user._id": "alice"}, {$set: {"comments.$.user.username": "alice_new"}});
// What about nested comments? Likes with user info? Messages?
// This is O(all_data_alice_touched)

// PostgreSQL: one row update
UPDATE users SET username = 'alice_new' WHERE id = 'alice';
-- Every JOIN automatically uses the new username
```

### When MongoDB IS better for social features
- Activity feeds (pre-computed, denormalized timelines)
- User profiles with flexible fields
- Content that's mostly read, rarely updated
- Analytics/event logging

### The reasoning pattern
Choose the database that matches the data's natural structure. Social media data is a web of RELATIONSHIPS (follows, likes, comments) — relational databases model this directly. Document databases excel at hierarchical, self-contained documents. When entities reference each other frequently, relational is almost always the better fit.'''
    ),
    (
        "thinking/meta-reasoning-polling-vs-webhook",
        r'''For integrating with a payment provider to know when payments are completed, compare:

Polling:
```python
import time

def check_payment_status(payment_id):
    while True:
        response = requests.get(f"https://payments.api/v1/payments/{payment_id}")
        status = response.json()["status"]

        if status == "completed":
            handle_payment_success(payment_id)
            break
        elif status == "failed":
            handle_payment_failure(payment_id)
            break

        time.sleep(5)  # check every 5 seconds
```

Webhook:
```python
@app.post("/webhooks/payment")
def payment_webhook(request):
    # Verify webhook signature
    signature = request.headers.get("X-Signature")
    if not verify_signature(request.body, signature, WEBHOOK_SECRET):
        return {"error": "Invalid signature"}, 401

    event = request.json
    if event["type"] == "payment.completed":
        handle_payment_success(event["payment_id"])
    elif event["type"] == "payment.failed":
        handle_payment_failure(event["payment_id"])

    return {"received": True}, 200
```

Which approach is better?''',
        r'''<think>
For payment status notifications from an external provider.

**Polling:**
Pros:
- Simple to implement (just a loop)
- No inbound network requirements (no public URL needed)
- Works behind firewalls
- No missed events (you check when ready)

Cons:
- Wasteful: 90% of requests get "still pending"
- Latency: up to 5 seconds delay between completion and detection
- Resource-intensive: dedicated thread/process per payment
- Rate limits: might hit API rate limits with many concurrent payments
- Scales poorly: 1000 pending payments = 200 requests/second (1000/5)

**Webhook:**
Pros:
- Instant notification: payment provider tells YOU when it's done
- Efficient: zero requests until something happens
- Scalable: provider pushes events, you handle them
- Standard: most payment providers support webhooks

Cons:
- Requires public URL (or tunneling for development)
- Must handle webhook security (signature verification)
- Must handle retries (provider will retry on failure)
- Must handle idempotency (same webhook might arrive twice)
- More complex error handling

**For payment processing:**
- Payments take seconds to minutes to complete
- Polling at 5s intervals for a payment that takes 30 seconds = 6 wasted requests
- With 1000 concurrent payments: polling = 200 req/sec, webhook = ~0 req/sec (just waiting)
- Payment providers (Stripe, PayPal) all support webhooks and recommend them

**The hybrid approach:**
Best practice is webhook + polling fallback:
1. Listen for webhooks (primary)
2. Periodic polling for payments where webhook was missed (fallback)

This handles the case where a webhook is lost (network glitch, server downtime).

**Winner:** Webhooks, with polling as a fallback for reliability.
</think>

**Webhooks are better — instant, efficient, and recommended by all payment providers. Use polling as a fallback.**

### Evaluation

| Axis | Polling | Webhook |
|------|---------|---------|
| Latency | Up to poll interval (5s) | Instant (~100ms) |
| Efficiency | Most requests return "pending" | Zero requests until event |
| Scalability | 1000 payments = 200 req/sec | 1000 payments = ~0 req/sec |
| Rate limits | Risk of hitting limits | No outbound requests |
| Complexity | Simple loop | Signature verification, idempotency |
| Network requirements | Outbound only | Needs public URL |
| Missed events | None (you check) | Possible (must handle retries) |

### The scale problem with polling
```
10 pending payments, 5s poll interval: 2 req/sec → fine
100 pending payments: 20 req/sec → concerning
1,000 pending payments: 200 req/sec → rate limited!
10,000 pending payments: 2,000 req/sec → provider blocks you
```

### Best practice: webhook + polling fallback
```python
# Primary: webhook handles 99% of events
@app.post("/webhooks/payment")
def payment_webhook(request):
    verify_signature(request)
    handle_event(request.json)
    return {"received": True}, 200

# Fallback: catch missed webhooks
@celery.task
def check_stale_payments():
    """Run every 15 minutes — catch payments where webhook was missed."""
    stale = Payment.query.filter(
        Payment.status == 'pending',
        Payment.created_at < datetime.utcnow() - timedelta(minutes=10)
    ).all()
    for payment in stale:
        status = check_payment_api(payment.id)
        if status != 'pending':
            handle_status_change(payment, status)
```

### Webhook security checklist
```python
def payment_webhook(request):
    # 1. Verify signature (prevent spoofed webhooks)
    verify_signature(request.body, request.headers["X-Signature"])

    # 2. Idempotency (handle duplicate deliveries)
    event_id = request.json["event_id"]
    if already_processed(event_id):
        return {"received": True}, 200

    # 3. Process event
    handle_event(request.json)
    mark_processed(event_id)

    # 4. Return 200 quickly (process async if slow)
    return {"received": True}, 200
```

### The reasoning pattern
For event notification between services, prefer push (webhooks) over pull (polling). Polling wastes resources checking for events that haven't happened. Webhooks deliver events instantly with zero wasted requests. Always implement polling as a fallback for reliability — webhooks can be lost due to network issues or server downtime.'''
    ),
    (
        "thinking/meta-reasoning-env-config-approaches",
        r'''Compare these two approaches for managing application configuration:

Environment variables:
```python
import os

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
SECRET_KEY = os.environ["SECRET_KEY"]
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
```

Config file (YAML):
```yaml
# config/production.yaml
database:
  url: "postgres://user:pass@db.prod.com/myapp"
  pool_size: 20
redis:
  url: "redis://cache.prod.com:6379"
security:
  secret_key: "super-secret-key-here"
logging:
  level: "WARNING"
  format: "json"
```
```python
import yaml
with open(f"config/{ENV}.yaml") as f:
    config = yaml.safe_load(f)
```

Which approach is better for production applications?''',
        r'''<think>
Let me evaluate both.

**Environment variables:**
Pros:
- 12-Factor App compliant: industry standard for cloud-native apps
- No secrets in code/files: set via deployment platform (Heroku, AWS, K8s)
- Platform-agnostic: works everywhere (Docker, K8s, VMs, serverless)
- Immutable per deployment: changing config = new deployment
- Simple: no file parsing, no format to learn

Cons:
- No structure: flat key-value only (no nesting, no types)
- No validation: typos in env var names silently use defaults
- Hard to see all config: scattered across platform settings
- No comments: can't document why a setting exists
- String-only: must convert types manually

**Config files (YAML):**
Pros:
- Structured: nested settings, typed values
- Documented: comments explain settings
- Visible: all config in one readable file
- Versioned: can diff config changes in git
- Rich types: numbers, booleans, lists, maps

Cons:
- Secrets in files: YAML files in git = secrets in git (SECURITY RISK!)
- Environment-specific files: config/dev.yaml, config/prod.yaml, config/staging.yaml...
- File management: must deploy config files alongside code
- Deserialization risks: yaml.load() can execute code (use safe_load!)

**The security issue with config files:**
```yaml
# config/production.yaml — checked into git!
security:
  secret_key: "super-secret-key-here"  # Now visible to everyone with repo access!
```

This is a common mistake. Secrets should NEVER be in config files that are version-controlled.

**Best approach: hybrid**
- Environment variables for SECRETS (database URLs, API keys, secret keys)
- Config files for NON-SECRET settings (log level, pool size, feature flags)
- Or: config files with env var interpolation

**Winner:** Environment variables for secrets + config files (without secrets) for structured settings. Pure env vars work well for small apps. Config files with secrets embedded are a security risk.
</think>

**Hybrid approach: environment variables for secrets, config files for non-secret structured settings.**

### Evaluation

| Axis | Environment variables | Config files (YAML) |
|------|----------------------|-------------------|
| Secrets management | ✓ (never in code) | ✗ (secrets in git!) |
| Structure/nesting | ✗ (flat key-value) | ✓ (nested, typed) |
| Documentation | ✗ (no comments) | ✓ (inline comments) |
| Type safety | ✗ (all strings) | ✓ (numbers, bools, lists) |
| Platform compatibility | ✓ (universal) | Needs file deployment |
| Visibility | Hard to see all at once | All in one file |
| 12-Factor compliance | ✓ | ✗ |

### The security problem
```yaml
# config/production.yaml — committed to git!
database:
  url: "postgres://admin:P@ssw0rd@db.prod.com/myapp"
  # This password is now in:
  # - Git history (forever, even after deletion)
  # - Every developer's local checkout
  # - CI/CD logs if printed
  # - Any git mirror or fork
```

### Best practice: hybrid approach
```python
import os
import yaml

# Load non-secret config from file
with open(f"config/{os.environ.get('ENV', 'development')}.yaml") as f:
    config = yaml.safe_load(f)

# Override with secrets from environment
config['database']['url'] = os.environ['DATABASE_URL']
config['security']['secret_key'] = os.environ['SECRET_KEY']
```

```yaml
# config/production.yaml — safe to commit!
database:
  pool_size: 20
  timeout: 30
logging:
  level: "WARNING"
  format: "json"
features:
  new_checkout: true
  dark_mode: false
```

### The reasoning pattern
Separate secrets from configuration. Secrets (passwords, keys, tokens) should NEVER be in version-controlled files — use environment variables or secret management services (AWS Secrets Manager, Vault). Non-secret settings (log levels, pool sizes, feature flags) can be in config files for better structure and documentation.'''
    ),
    (
        "thinking/meta-reasoning-class-vs-function-components",
        r'''Compare these React component patterns:

Class component:
```jsx
class UserProfile extends React.Component {
    constructor(props) {
        super(props);
        this.state = { user: null, loading: true };
    }

    componentDidMount() {
        fetch(`/api/users/${this.props.userId}`)
            .then(r => r.json())
            .then(user => this.setState({ user, loading: false }));
    }

    componentDidUpdate(prevProps) {
        if (prevProps.userId !== this.props.userId) {
            this.setState({ loading: true });
            fetch(`/api/users/${this.props.userId}`)
                .then(r => r.json())
                .then(user => this.setState({ user, loading: false }));
        }
    }

    render() {
        if (this.state.loading) return <Loading />;
        return <div>{this.state.user.name}</div>;
    }
}
```

Function component with hooks:
```jsx
function UserProfile({ userId }) {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        setLoading(true);
        fetch(`/api/users/${userId}`)
            .then(r => r.json())
            .then(user => { setUser(user); setLoading(false); });
    }, [userId]);

    if (loading) return <Loading />;
    return <div>{user.name}</div>;
}
```

Which pattern is better in 2024+?''',
        r'''<think>
In modern React (2024+), function components with hooks are the clear standard.

**Class components:**
- Verbose: constructor, super(props), this.setState, this.state, this.props
- Lifecycle duplication: fetch logic in BOTH componentDidMount and componentDidUpdate
- this binding issues: event handlers need .bind(this) or arrow functions
- Not supported by newer React features (Suspense, Server Components, use() hook)
- Legacy: React team recommends hooks for all new code

**Function components with hooks:**
- Concise: less boilerplate
- Single effect handles mount AND update (no duplication)
- No `this` confusion
- Custom hooks for logic reuse (much simpler than HOCs or render props)
- Works with all React features (Suspense, Server Components, Concurrent Mode)
- Standard: all React tutorials, docs, and libraries assume hooks

This isn't even a close comparison anymore. Function components with hooks are the standard, and class components are legacy.

**Winner:** Function components with hooks, overwhelmingly.
</think>

**Function components with hooks — this is not a debate in 2024+. Hooks are the React standard, and class components are legacy.**

### Evaluation

| Axis | Class components | Function + hooks |
|------|-----------------|-----------------|
| Boilerplate | High (constructor, super, this) | Low |
| Lifecycle logic | Duplicated across methods | Single useEffect |
| Logic reuse | HOCs, render props (complex) | Custom hooks (simple) |
| `this` binding | Constant gotcha | Not applicable |
| React Server Components | ✗ Not supported | ✓ |
| Suspense/Concurrent Mode | Limited | ✓ Full support |
| React team recommendation | Legacy | Current standard |
| New library support | Decreasing | Universal |

### The duplication problem
```jsx
// Class: fetch logic written TWICE
componentDidMount() { this.fetchUser(); }
componentDidUpdate(prev) {
    if (prev.userId !== this.props.userId) this.fetchUser();
}

// Hooks: fetch logic written ONCE
useEffect(() => { fetchUser(); }, [userId]);
```

### Custom hooks: logic reuse made simple
```jsx
// Extract reusable data fetching:
function useUser(userId) {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);
    useEffect(() => {
        fetch(`/api/users/${userId}`).then(r => r.json()).then(setUser);
        setLoading(false);
    }, [userId]);
    return { user, loading };
}

// Use anywhere:
function UserProfile({ userId }) {
    const { user, loading } = useUser(userId);
    if (loading) return <Loading />;
    return <div>{user.name}</div>;
}

function UserAvatar({ userId }) {
    const { user } = useUser(userId);
    return <img src={user?.avatar} />;
}
```

### The reasoning pattern
Technology choices should be evaluated in the context of the current ecosystem, not historical debates. Class components were the standard in 2015-2018. Hooks are the standard from 2019 onward. When a technology has been superseded by a clearly better alternative that's endorsed by the framework maintainers, the comparison is settled. Use function components with hooks for all new React code.'''
    ),
    (
        "thinking/meta-reasoning-eager-vs-lazy-loading",
        r'''For an e-commerce product listing page that shows 20 products with their categories, compare:

Eager loading:
```python
# One query with JOIN — loads everything upfront
products = (
    db.query(Product)
    .options(joinedload(Product.category))
    .limit(20)
    .all()
)
for p in products:
    print(f"{p.name} - {p.category.name}")  # No extra queries
```

Lazy loading (default ORM behavior):
```python
# Initial query — categories loaded on demand
products = db.query(Product).limit(20).all()
for p in products:
    print(f"{p.name} - {p.category.name}")  # Triggers query per product!
```

Which loading strategy should I use?''',
        r'''<think>
This is the classic N+1 query problem.

**Lazy loading (default):**
Query 1: `SELECT * FROM products LIMIT 20` → 20 products
Then for each product: `SELECT * FROM categories WHERE id = ?` → 20 more queries
Total: 21 queries!

**Eager loading (joinedload):**
Query 1: `SELECT p.*, c.* FROM products p JOIN categories c ON p.category_id = c.id LIMIT 20`
Total: 1 query!

For this case, eager loading is clearly better. We KNOW we need category names for every product.

But eager loading isn't always better:
- If you list products WITHOUT showing categories → eager loading wastes bandwidth
- If the relationship is large (product → 1000 reviews) → eager loading could OOM
- If you sometimes need the relationship and sometimes don't → lazy is more flexible

**Winner for this specific case:** Eager loading. When you know you'll access a relationship for every item in a collection, always eager-load to avoid N+1.
</think>

**Eager loading is better here — it replaces 21 queries with 1 query. This is the textbook N+1 fix.**

### Query comparison
```
Lazy loading:
  Query 1: SELECT * FROM products LIMIT 20
  Query 2: SELECT * FROM categories WHERE id = 1
  Query 3: SELECT * FROM categories WHERE id = 2
  ...
  Query 21: SELECT * FROM categories WHERE id = 20
  Total: 21 queries, ~21 round trips

Eager loading:
  Query 1: SELECT p.*, c.* FROM products p
           JOIN categories c ON p.category_id = c.id
           LIMIT 20
  Total: 1 query, 1 round trip
```

### Performance impact
| Products | Lazy queries | Eager queries | Speedup |
|----------|-------------|---------------|---------|
| 20 | 21 | 1 | ~10x |
| 100 | 101 | 1 | ~50x |
| 1000 | 1001 | 1 | ~200x |

### When to use each

| Scenario | Loading strategy |
|----------|-----------------|
| List products with categories | Eager (joinedload) |
| Product detail (1 product, 1 category) | Either (only 2 queries max) |
| Product list, category sometimes shown | Lazy (avoid unused JOINs) |
| Product with 1000 reviews | Subquery load or lazy (JOIN would duplicate rows) |
| API where client specifies fields | Lazy + explicit loading |

### SQLAlchemy loading strategies
```python
# joinedload: JOIN in same query (best for to-one)
.options(joinedload(Product.category))

# subqueryload: separate query with IN clause (best for to-many)
.options(subqueryload(Product.reviews))
# SELECT * FROM reviews WHERE product_id IN (1, 2, ..., 20)

# selectinload: same as subqueryload but uses SELECT IN
.options(selectinload(Product.tags))
```

### The reasoning pattern
Choose loading strategy based on whether you'll access the relationship: if YES for every item → eager load. If MAYBE → lazy load. If it's a large collection (one-to-many with many) → subquery load instead of join load to avoid row duplication. The key insight: N+1 queries are almost always worse than 1 query with a JOIN or 2 queries with an IN clause.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
