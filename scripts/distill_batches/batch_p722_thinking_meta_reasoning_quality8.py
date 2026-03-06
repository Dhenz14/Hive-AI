"""Phase 3B: Metacognition — Reasoning Quality Evaluation (Part 8)
Final batch to reach Phase 3B target.
"""

PAIRS = [
    (
        "thinking/meta-reasoning-trunk-vs-gitflow",
        r'''Compare these Git branching strategies for a SaaS product deployed continuously:

Trunk-based development:
- All developers commit to main (trunk) daily
- Feature flags for incomplete features
- Short-lived branches (< 1 day)
- CI/CD deploys main after every merge

Git Flow:
- main, develop, feature/*, release/*, hotfix/* branches
- Feature branches last days/weeks
- Release branches for stabilization
- Merge to develop, then to main

Which is better for continuous deployment?''',
        r'''<think>
For a SaaS product with continuous deployment.

**Trunk-based:**
- Developers integrate daily → integration issues caught early
- Feature flags: partially-complete features hidden from users
- Short branches: minimal merge conflicts
- CI/CD runs on every commit: always deployable
- Forces small, incremental changes

**Git Flow:**
- Long-lived feature branches: merge conflicts accumulate
- Release branches: adds stabilization time
- develop branch: extra integration step
- More ceremony: PRs between branches
- Designed for software with release cycles (v1.0, v2.0)

**For continuous deployment (SaaS):**
The goal is to deploy multiple times per day. Git Flow was designed for software with versioned releases (desktop apps, libraries). Its release branches and develop branch add overhead that slows continuous deployment.

Trunk-based development is designed for exactly this use case: small changes, continuous integration, feature flags for gating.

**Winner:** Trunk-based development for SaaS with CD.
</think>

**Trunk-based development is better for continuous deployment — Git Flow was designed for versioned releases, not continuous delivery.**

### Evaluation

| Axis | Trunk-based | Git Flow |
|------|------------|----------|
| Deploy frequency | Multiple times/day | Every few weeks |
| Integration conflicts | Minimal (daily merge) | Frequent (long branches) |
| Branch lifetime | < 1 day | Days to weeks |
| Merge complexity | Simple (small diffs) | Complex (large feature merges) |
| Feature gating | Feature flags | Branches |
| CI/CD pipeline | Simple (one branch) | Complex (multiple branch rules) |
| Designed for | Continuous deployment (SaaS) | Versioned releases (libraries) |

### Why Git Flow is wrong for CD
```
Git Flow release cycle:
  feature/login ─(2 weeks)──→ develop ──→ release/1.5 ──→ main
  feature/cart  ─(3 weeks)──→ develop ──→ release/1.5 ──→ main
  Time from commit to production: 3-4 weeks

Trunk-based:
  small change → main → production (via CI/CD)
  Time from commit to production: minutes to hours
```

### When Git Flow IS appropriate
- Open-source libraries with versioned releases (v1.0, v2.0)
- Mobile apps with App Store review (release branches for stabilization)
- Embedded software with long QA cycles
- Regulatory environments requiring release documentation

### The reasoning pattern
Branching strategy should match deployment cadence. Continuous deployment → trunk-based (minimize branch lifetime). Versioned releases → Git Flow (stabilize before release). The branching model is a means to an end — match it to how you actually ship software.'''
    ),
    (
        "thinking/meta-reasoning-pagination-strategies",
        r'''Compare these pagination strategies for an API listing thousands of items:

Offset pagination:
```python
@app.get("/api/posts")
def list_posts(page: int = 1, per_page: int = 20):
    offset = (page - 1) * per_page
    posts = db.execute(
        "SELECT * FROM posts ORDER BY created_at DESC LIMIT %s OFFSET %s",
        (per_page, offset)
    ).fetchall()
    total = db.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    return {"data": posts, "page": page, "total_pages": total // per_page + 1}
```

Cursor pagination:
```python
@app.get("/api/posts")
def list_posts(cursor: str = None, limit: int = 20):
    if cursor:
        cursor_date = decode_cursor(cursor)
        posts = db.execute(
            "SELECT * FROM posts WHERE created_at < %s ORDER BY created_at DESC LIMIT %s",
            (cursor_date, limit + 1)
        ).fetchall()
    else:
        posts = db.execute(
            "SELECT * FROM posts ORDER BY created_at DESC LIMIT %s",
            (limit + 1,)
        ).fetchall()

    has_next = len(posts) > limit
    posts = posts[:limit]
    next_cursor = encode_cursor(posts[-1].created_at) if has_next else None
    return {"data": posts, "next_cursor": next_cursor}
```

Which is better for a high-traffic API?''',
        r'''<think>
For a high-traffic API listing thousands of items.

**Offset pagination:**
Pros:
- Simple to implement and understand
- Clients can jump to any page (page 50 directly)
- Easy to show total pages and page numbers
- Standard pattern (most developers know it)

Cons:
- SLOW at deep pages: `OFFSET 10000` means the DB scans 10,000 rows then discards them
- Inconsistent: if items are added/deleted between requests, items can be skipped or duplicated
- COUNT(*) is expensive: `SELECT COUNT(*)` on large tables is slow

Performance of OFFSET:
- Page 1: scan 20 rows → fast
- Page 100: scan 2,000 rows, discard 1,980 → slow
- Page 1000: scan 20,000 rows, discard 19,980 → very slow

**Cursor pagination:**
Pros:
- Consistent performance: always a simple WHERE + LIMIT (no offset scan)
- No duplicates or skips: cursor is a stable point in the dataset
- Efficient: uses index on created_at for fast lookup
- Scales: page 1 and page 1000 are equally fast

Cons:
- Can't jump to arbitrary pages (no "go to page 50")
- Can't show total pages (no COUNT needed, but total unknown)
- More complex client code (must track cursor)
- Harder to implement (cursor encoding/decoding)

**For a high-traffic API:**
If the dataset is large (100K+ items), offset pagination degrades at deep pages. Social media feeds, log viewers, and activity streams should use cursor pagination.

If the dataset is small (< 10K items) and users need page numbers, offset is simpler and fast enough.

**Winner:** Cursor pagination for high-traffic APIs with large datasets. Offset for small datasets where page jumping is important.
</think>

**Cursor pagination for high-traffic APIs with large datasets — consistent O(1) performance regardless of page depth.**

### Evaluation

| Axis | Offset | Cursor |
|------|--------|--------|
| Page 1 performance | Fast | Fast |
| Page 1000 performance | Very slow (scans 20K rows) | Fast (same as page 1) |
| Jump to page N | ✓ Easy | ✗ Must traverse |
| Total page count | ✓ (but COUNT is expensive) | ✗ Unknown |
| Data consistency | ✗ (skips/duplicates on changes) | ✓ (stable cursor) |
| Implementation | Simple | Moderate |
| Client complexity | Low (page number) | Medium (cursor tracking) |

### The performance cliff
```sql
-- Offset: page 1 (fast)
SELECT * FROM posts ORDER BY created_at DESC LIMIT 20 OFFSET 0;
-- Scans: 20 rows

-- Offset: page 500 (slow!)
SELECT * FROM posts ORDER BY created_at DESC LIMIT 20 OFFSET 9980;
-- Scans: 10,000 rows, discards 9,980

-- Cursor: any page (always fast)
SELECT * FROM posts WHERE created_at < '2024-01-15' ORDER BY created_at DESC LIMIT 20;
-- Uses index, scans exactly 20 rows
```

### When to use each
| Scenario | Offset | Cursor |
|----------|--------|--------|
| Admin table (< 10K rows) | ✓ | Overkill |
| Social media feed | ✗ | ✓ |
| Search results | ✓ (up to 1000 results) | ✓ |
| Log/event stream | ✗ | ✓ |
| E-commerce catalog | ✓ (if paginated search) | ✓ |

### The reasoning pattern
Pagination strategy depends on dataset size and access pattern. Small datasets where users need page numbers → offset (simple, fast enough). Large datasets or infinite scroll → cursor (consistent performance, no data skipping). Many APIs use offset up to a threshold (e.g., max 100 pages) then fall back to cursor for deeper access.'''
    ),
    (
        "thinking/meta-reasoning-error-codes-vs-exceptions-api",
        r'''For an API that needs to communicate specific error conditions to clients, compare:

HTTP status codes + error body:
```python
@app.post("/api/orders")
def create_order(data):
    if not data.get("items"):
        return jsonify({"error": "EMPTY_CART", "message": "Cart is empty"}), 400

    user = get_user(data["user_id"])
    if not user:
        return jsonify({"error": "USER_NOT_FOUND", "message": "User does not exist"}), 404

    if not user.payment_method:
        return jsonify({"error": "NO_PAYMENT_METHOD", "message": "Add a payment method"}), 422

    if not check_inventory(data["items"]):
        return jsonify({"error": "OUT_OF_STOCK", "message": "Some items unavailable"}), 409
```

Machine-readable error objects:
```python
@app.post("/api/orders")
def create_order(data):
    errors = validate_order(data)
    if errors:
        return jsonify({
            "errors": [
                {
                    "code": e.code,
                    "field": e.field,
                    "message": e.message,
                    "details": e.details
                } for e in errors
            ]
        }), 400
```

Which gives better error communication?''',
        r'''<think>
Both approaches communicate errors, but they differ in structure and richness.

**Approach 1 (HTTP status + error body):**
- Uses different HTTP status codes (400, 404, 409, 422) for different error types
- Single error per response
- Error code + message in body
- Status code helps HTTP-level tooling (monitoring, retries)

**Approach 2 (machine-readable error objects):**
- Single status code (400) for all validation errors
- Multiple errors per response (can report all issues at once)
- Structured error objects with field, code, message, details
- Better for form validation (show all errors at once)

**The right answer is BOTH combined:**
- Use HTTP status codes for the ERROR CATEGORY (4xx client, 5xx server)
- Use structured error body for SPECIFIC ERROR DETAILS
- Support multiple errors per response for validation

**For an API:**
The first approach is better for distinct error conditions (user not found vs out of stock). The second is better for validation errors (multiple fields invalid). A good API uses both patterns.
</think>

**Combine both: HTTP status codes for error category, structured body for details. Support multiple errors for validation.**

### Evaluation

| Axis | Status codes + body | Structured error objects |
|------|-------------------|------------------------|
| Error category | ✓ (4xx, 5xx) | Weak (single 400) |
| Multiple errors | ✗ (one at a time) | ✓ (all validation errors) |
| Field-level errors | ✗ | ✓ (which field failed) |
| Machine readability | Good (code + message) | Better (code + field + details) |
| Monitoring/alerting | ✓ (status code metrics) | Weak (all are 400) |

### Best practice: combine both
```python
@app.post("/api/orders")
def create_order(data):
    # Validation errors: 422 with multiple error objects
    errors = validate_order(data)
    if errors:
        return jsonify({
            "type": "validation_error",
            "errors": [{"code": e.code, "field": e.field, "message": e.message}
                       for e in errors]
        }), 422

    # Business errors: specific status codes
    user = get_user(data["user_id"])
    if not user:
        return jsonify({"code": "USER_NOT_FOUND", "message": "User does not exist"}), 404

    if not check_inventory(data["items"]):
        return jsonify({
            "code": "OUT_OF_STOCK",
            "message": "Some items are unavailable",
            "details": {"unavailable_items": [...]}
        }), 409

    order = create_order(data)
    return jsonify(order.to_dict()), 201
```

### Error response structure (RFC 7807 Problem Details)
```json
{
    "type": "https://api.example.com/errors/out-of-stock",
    "title": "Out of Stock",
    "status": 409,
    "detail": "Product 'Widget' is out of stock (0 remaining)",
    "instance": "/api/orders/create",
    "errors": [
        {"field": "items[0].product_id", "code": "OUT_OF_STOCK", "message": "0 remaining"}
    ]
}
```

### The reasoning pattern
Error communication serves two audiences: machines (status codes, error codes) and humans (messages, details). HTTP status codes tell infrastructure (load balancers, monitoring) the error category. Structured error bodies tell client code how to respond. Support both, and use multiple errors for validation to avoid frustrating "fix one error, discover another" loops.'''
    ),
    (
        "thinking/meta-reasoning-ddd-vs-simple-crud",
        r'''For a new feature in our codebase — user registration with email verification — compare:

Simple CRUD approach:
```python
@app.post("/api/register")
def register(data):
    if db.query(User).filter_by(email=data["email"]).first():
        return {"error": "Email taken"}, 409

    user = User(name=data["name"], email=data["email"],
                password_hash=hash_password(data["password"]),
                verified=False)
    db.add(user)
    db.commit()

    token = create_verification_token(user.id)
    send_verification_email(user.email, token)
    return {"id": user.id}, 201
```

Domain-Driven Design approach:
```python
# domain/user.py
class UserAggregate:
    def __init__(self, name, email, password):
        self._validate(name, email, password)
        self.events = [UserRegisteredEvent(name, email)]

    def _validate(self, name, email, password):
        if not EmailVO(email).is_valid():
            raise InvalidEmailError()
        if not PasswordVO(password).meets_policy():
            raise WeakPasswordError()

# application/register_user_command.py
class RegisterUserCommandHandler:
    def __init__(self, user_repo, email_service, event_bus):
        self.user_repo = user_repo
        self.email_service = email_service
        self.event_bus = event_bus

    def handle(self, command):
        if self.user_repo.exists_by_email(command.email):
            raise DuplicateEmailError()
        user = UserAggregate(command.name, command.email, command.password)
        self.user_repo.save(user)
        self.event_bus.publish(user.events)

# infrastructure/event_handlers.py
class SendVerificationEmailHandler:
    def handle(self, event: UserRegisteredEvent):
        token = self.token_service.create(event.user_id)
        self.email_service.send_verification(event.email, token)
```

Which approach is appropriate?''',
        r'''<think>
For USER REGISTRATION WITH EMAIL VERIFICATION — a straightforward feature.

**Simple CRUD:**
- 15 lines of code
- Clear flow: validate → create → send email
- Easy to read, debug, and modify
- All logic in one place
- No architectural ceremony

**DDD:**
- 40+ lines across 4+ files
- UserAggregate, EmailVO, PasswordVO, RegisterUserCommandHandler, UserRegisteredEvent, SendVerificationEmailHandler...
- 6+ classes for a simple registration
- Indirect flow: command → handler → aggregate → event → event handler
- Requires understanding DDD concepts (aggregates, value objects, domain events)

For this specific feature, the DDD approach is massively over-engineered. Registration is:
1. Check if email exists
2. Create user
3. Send email

This is CRUD. There's no complex domain logic, no business rules that change over time, no invariants to protect across multiple entities.

DDD adds value when:
- Complex business rules that change frequently
- Multiple entities that must maintain consistency (aggregates)
- Domain events that trigger complex workflows
- Business logic that's hard to express in CRUD

Registration has none of these. The "domain events" (UserRegisteredEvent → send email) could just be a function call.

**Winner:** Simple CRUD. Use DDD when the domain complexity justifies it, not for every feature.
</think>

**Simple CRUD is the right approach here. DDD adds 4x the code for a feature with no complex domain logic.**

### Evaluation

| Axis | Simple CRUD | DDD |
|------|------------|-----|
| Lines of code | ~15 | ~40+ across 4+ files |
| Files involved | 1 | 4+ (aggregate, command, handler, events) |
| Time to understand | 30 seconds | 5+ minutes (must understand DDD) |
| Time to implement | 15 minutes | 1+ hour |
| Time to debug | Straightforward | Follow event chain across files |
| Flexibility for change | Moderate | High |
| Appropriate complexity | ✓ | ✗ (over-engineered) |

### The complexity cost
```
Simple CRUD: "Where does registration happen?"
→ register endpoint → done

DDD: "Where does registration happen?"
→ API endpoint → RegisterUserCommand → RegisterUserCommandHandler
→ UserAggregate constructor → UserRegisteredEvent
→ Event bus → SendVerificationEmailHandler → EmailService
→ "Wait, where's the actual database save?"
```

### When DDD IS appropriate
| Feature | CRUD | DDD |
|---------|------|-----|
| User registration | ✓ | Overkill |
| Simple CRUD API | ✓ | Overkill |
| Insurance claim processing | Too simple | ✓ (complex rules) |
| Financial trading engine | Too simple | ✓ (many invariants) |
| Multi-step workflow with approvals | Messy | ✓ (state machine) |
| E-commerce pricing engine | Messy | ✓ (discount rules, tax) |

### The rule of thumb
```
If your "domain logic" is:
  validate → save → notify
→ Use CRUD

If your "domain logic" is:
  apply business rules → check invariants across entities →
  calculate derived values → trigger conditional workflows
→ Consider DDD
```

### The reasoning pattern
Architectural patterns have a complexity cost. DDD's cost (aggregates, value objects, domain events, command handlers) is justified when the domain itself is complex — when business rules are numerous, change frequently, and involve multiple entities. For simple CRUD operations, DDD is ceremony without substance. Match architecture complexity to domain complexity.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
