"""Phase 2A: Advanced Reasoning — Backtracking & Dead-End Recovery (Part 9/9)"""

PAIRS = [
    (
        "thinking/backtrack-shared-state-to-event-sourcing",
        "We have a shared mutable state problem. Multiple services write to the same 'orders' table and the data keeps getting corrupted. Service A updates the status, Service B updates the shipping address, and sometimes they overwrite each other's changes. How do I fix this?",
        r'''<think>
Shared mutable state across services — classic distributed data problem. Let me think through approaches.

**First approach: Database locks**
Use SELECT FOR UPDATE to lock the row while modifying:
```sql
BEGIN;
SELECT * FROM orders WHERE id = 123 FOR UPDATE;
-- Make changes
UPDATE orders SET status = 'shipped' WHERE id = 123;
COMMIT;
```
This prevents concurrent writes. But:
- Services now WAIT for each other (performance bottleneck)
- Deadlocks possible if two services lock rows in different order
- Doesn't solve the fundamental problem: WHO owns this data?

**Second approach: Optimistic locking with version numbers**
```sql
UPDATE orders SET status = 'shipped', version = version + 1
WHERE id = 123 AND version = 5;
-- If 0 rows affected → someone else modified it → retry
```
Better — no blocking. But still has the same fundamental problem: multiple writers to the same data. Retries add complexity and can loop.

Let me backtrack. Both approaches try to make shared writes SAFE. But maybe shared writes are the wrong architecture.

**Third approach (backtracking): data ownership**
Each service OWNS the data it writes. No shared mutable state.
- Order Service owns: order_id, items, total, status
- Shipping Service owns: shipping_address, tracking_number, shipped_at
- Payment Service owns: payment_id, paid_at, payment_method

They write to THEIR OWN tables/columns, never to each other's. No conflicts possible.

But how do they coordinate? Events.
- Order Service publishes "order.created"
- Payment Service subscribes, processes payment, publishes "payment.completed"
- Shipping Service subscribes to "payment.completed", handles shipping

This is essentially event sourcing / CQRS for the coordination, with clear data ownership for the state.
</think>

Each approach I considered before landing on the right one:

**Attempt 1:** Database locks → blocks concurrent requests, deadlock risk.
**Attempt 2:** Optimistic locking → retry loops, still shared writes.
**Backtrack:** The problem isn't HOW to share writes — it's that multiple services shouldn't write to the same data.

## The Fix: Data Ownership + Events

```
BEFORE (shared mutable state — conflicts):
  Service A writes → orders table ← Service B writes
  Service C writes ↗               ← Service D writes
  Everyone writes everywhere. Overwrites. Corruption.

AFTER (owned state + events — no conflicts):
  Order Service    → OWNS orders.status, orders.items, orders.total
  Payment Service  → OWNS payments.* (separate table)
  Shipping Service → OWNS shipments.* (separate table)

  Coordination via events, not shared writes:
  Order created → event → Payment processes → event → Shipping ships
```

## Implementation

```python
# BEFORE: All services write to the same orders table
# ❌ Service A:
db.execute("UPDATE orders SET status = 'paid' WHERE id = %s", order_id)
# ❌ Service B (simultaneously):
db.execute("UPDATE orders SET address = %s WHERE id = %s", new_addr, order_id)
# Race condition: one overwrites the other's changes


# AFTER: Each service owns its data

# Order Service — owns order lifecycle
class OrderService:
    async def create_order(self, user_id, items):
        order = await self.db.insert("orders", {
            "user_id": user_id,
            "items": items,
            "status": "pending",
        })
        # Tell the world — don't update other services' data directly
        await events.publish("order.created", {
            "order_id": order.id,
            "user_id": user_id,
            "total": order.total,
        })
        return order

    async def update_status(self, order_id, new_status):
        # ONLY Order Service can change order status
        await self.db.execute(
            "UPDATE orders SET status = %s WHERE id = %s",
            new_status, order_id
        )
        await events.publish("order.status_changed", {
            "order_id": order_id,
            "status": new_status,
        })


# Payment Service — owns payment data
class PaymentService:
    @events.subscribe("order.created")
    async def handle_order_created(self, event):
        payment = await self.charge(event["order_id"], event["total"])
        # Write to OUR payments table, not the orders table
        await self.db.insert("payments", {
            "order_id": event["order_id"],
            "payment_id": payment.id,
            "status": "completed",
            "paid_at": datetime.utcnow(),
        })
        # Notify other services
        await events.publish("payment.completed", {
            "order_id": event["order_id"],
            "payment_id": payment.id,
        })


# Shipping Service — owns shipment data
class ShippingService:
    @events.subscribe("payment.completed")
    async def handle_payment_completed(self, event):
        shipment = await self.create_shipment(event["order_id"])
        # Write to OUR shipments table
        await self.db.insert("shipments", {
            "order_id": event["order_id"],
            "tracking_number": shipment.tracking,
            "status": "preparing",
        })


# Read side: compose data from multiple services
async def get_order_details(order_id):
    """API endpoint that reads from all services."""
    order = await order_db.get("orders", order_id)
    payment = await payment_db.get_by("payments", order_id=order_id)
    shipment = await shipment_db.get_by("shipments", order_id=order_id)
    return {
        "order": order,
        "payment": payment,
        "shipment": shipment,
    }
```

## The Data Ownership Rule

| Data | Owner | Others Can |
|------|-------|-----------|
| Order status, items, total | Order Service | READ only |
| Payment status, amount, method | Payment Service | READ only |
| Shipping address, tracking, dates | Shipping Service | READ only |
| User profile, preferences | User Service | READ only |

**The rule: services can READ anyone's data but only WRITE their own.**

## What Changed

| Before | After |
|--------|-------|
| 4 services write to orders table | Each service has its own table |
| Race conditions on shared columns | No shared writes, no races |
| Lost updates (overwrites) | Each service controls its own data |
| Tight coupling (services know each other's schema) | Loose coupling (communicate via events) |
| Debugging: "who changed this field?" → unknown | Debugging: clear ownership, audit trail via events |

The backtracking insight: when multiple writers corrupt shared data, the fix isn't better locking — it's eliminating shared writes entirely through data ownership.'''
    ),
    (
        "thinking/backtrack-manual-deployment-to-gitops",
        "Our deployment process involves SSHing into servers, pulling code, running migrations, and restarting services manually. We've had incidents where someone forgot to run migrations or restarted the wrong service. I tried writing a bash deployment script but it keeps breaking in new ways. How do I make deployments reliable?",
        r'''<think>
Manual deployment → bash script → still breaks. Let me think through the evolution.

**First approach: Manual SSH deployment**
The user's current state. Error-prone because it relies on human memory:
- SSH to correct server
- cd to correct directory
- git pull correct branch
- run migrations
- restart correct service
- verify it's working
Each step can go wrong. Different developers do it differently.

**Second approach: Bash deployment script**
The user tried this. Better but still fragile because:
- Script assumes specific server state (directory exists, git repo initialized)
- Error handling in bash is painful
- No rollback on failure
- Runs on a developer's machine (what if their laptop dies mid-deploy?)
- No audit trail

**Third approach: CI/CD pipeline**
Move deployment from a human-run script to an automated pipeline triggered by git push. GitHub Actions, GitLab CI, or similar.

This is better because:
- Consistent environment (runs in CI, not on dev laptops)
- Triggered by git (not by memory)
- Has logs and audit trail
- Can add approval gates

But still has issues for their case:
- SSH-based deploys from CI are fragile (network issues, auth issues)
- Rollback is still manual
- Multiple servers = complexity

**Fourth approach (after more thought): Containerized deployment**
Instead of SSHing and pulling code, build a Docker image in CI and deploy the image. The image IS the deployment — it includes the code, dependencies, everything.

- Build image → push to registry → pull and run on servers
- Same image in staging and production
- Rollback = run the previous image
- No SSH, no git pull on servers

But this requires Docker infrastructure. Let me think about what's realistic for their current state...

For a team currently doing manual SSH deploys, going straight to GitOps might be too big a jump. Let me recommend an incremental path.
</think>

Each approach before landing on the right one:

**Attempt 1:** Bash script → fragile, no rollback, runs on dev laptop.
**Attempt 2:** CI/CD pipeline with SSH → better but SSH deploys are still fragile.
**Backtrack:** The issue is SSH-based deployment itself. Ship artifacts (images), not code pulls.

## The Evolution: Where You Are → Where You Should Be

```
Level 1 (you now):  SSH → git pull → migrate → restart  (manual, error-prone)
Level 2 (quick win): CI/CD pipeline → SSH deploy script   (automated, still fragile)
Level 3 (proper):    CI/CD → Docker image → deploy image  (reliable, rollbackable)
Level 4 (ideal):     GitOps — git push = deployment        (declarative, auditable)
```

## Level 2: CI/CD Pipeline (Implement This Week)

```yaml
# .github/workflows/deploy.yml
name: Deploy to Production

on:
  push:
    branches: [main]  # Deploy on merge to main

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -r requirements.txt
      - run: python -m pytest

  deploy:
    needs: test  # Only deploy if tests pass
    runs-on: ubuntu-latest
    environment: production  # Requires manual approval
    steps:
      - uses: actions/checkout@v4

      - name: Deploy to production
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.PROD_HOST }}
          username: deploy
          key: ${{ secrets.SSH_KEY }}
          script: |
            set -e  # Stop on any error
            cd /opt/myapp
            git fetch origin main
            git reset --hard origin/main
            source venv/bin/activate
            pip install -r requirements.txt
            python manage.py migrate --no-input
            sudo systemctl restart myapp
            # Verify the deploy worked
            sleep 5
            curl -f http://localhost:8000/health || (sudo systemctl restart myapp-previous && exit 1)
```

**What this fixes:**
- No manual SSH (CI does it)
- Tests must pass before deploy
- Manual approval gate for production
- Stops on any error
- Basic health check after deploy

## Level 3: Docker-Based Deployment (Implement This Month)

```dockerfile
# Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python manage.py collectstatic --noinput
EXPOSE 8000
CMD ["gunicorn", "myapp.wsgi", "--bind", "0.0.0.0:8000", "--workers", "4"]
```

```yaml
# .github/workflows/deploy.yml
name: Build and Deploy

on:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build Docker image
        run: |
          docker build -t myapp:${{ github.sha }} .
          docker tag myapp:${{ github.sha }} registry.example.com/myapp:${{ github.sha }}
          docker tag myapp:${{ github.sha }} registry.example.com/myapp:latest
          docker push registry.example.com/myapp:${{ github.sha }}
          docker push registry.example.com/myapp:latest

  deploy:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - name: Deploy new image
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.PROD_HOST }}
          username: deploy
          key: ${{ secrets.SSH_KEY }}
          script: |
            # Pull new image
            docker pull registry.example.com/myapp:${{ github.sha }}
            # Run migrations
            docker run --rm --env-file /opt/myapp/.env \
              registry.example.com/myapp:${{ github.sha }} \
              python manage.py migrate --no-input
            # Swap containers (zero-downtime)
            docker stop myapp-old || true
            docker rename myapp myapp-old || true
            docker run -d --name myapp --env-file /opt/myapp/.env \
              -p 8000:8000 registry.example.com/myapp:${{ github.sha }}
            # Health check
            sleep 5
            curl -f http://localhost:8000/health || {
              docker stop myapp
              docker rename myapp-old myapp
              docker start myapp
              exit 1
            }
            docker rm myapp-old
```

**What this adds:**
- **Rollback is instant:** `docker run registry.example.com/myapp:<previous-sha>`
- **Consistent environment:** same image in staging and production
- **No git on servers:** server just runs Docker images
- **Immutable deploys:** can't accidentally modify code on the server

## What Each Level Solves

| Problem | Manual | CI/CD + SSH | Docker |
|---------|--------|-------------|--------|
| Forgot to run migrations | ❌ | ✅ (automated) | ✅ |
| Wrong server/service | ❌ | ✅ (config-driven) | ✅ |
| "Works on my machine" | ❌ | ❌ | ✅ |
| Rollback | ❌ (manual) | ❌ (reverse git) | ✅ (previous image) |
| Audit trail | ❌ | ✅ (CI logs) | ✅ |
| Zero-downtime | ❌ | ❌ | ✅ |

Start with Level 2 (CI/CD pipeline) today — it takes 1-2 hours to set up and immediately eliminates "I forgot" errors. Graduate to Level 3 (Docker) when you're ready for reliable rollbacks and consistent environments.'''
    ),
    (
        "thinking/backtrack-api-versioning-mess-to-additive",
        "We've been versioning our API by copying the entire codebase into v1/, v2/, v3/ directories. Now we have three copies of everything, bugs get fixed in v3 but not v1, and adding a new endpoint means adding it in three places. How do I fix this without breaking existing clients?",
        r'''<think>
Three copies of the entire codebase for API versioning. This is the worst-case versioning strategy. Let me think through how to untangle it.

**The mess they have:**
```
api/
  v1/
    users.py       # Copy 1
    orders.py      # Copy 1
    products.py    # Copy 1
  v2/
    users.py       # Copy 2 (slightly different)
    orders.py      # Copy 2
    products.py    # Copy 2
  v3/
    users.py       # Copy 3 (current)
    orders.py      # Copy 3
    products.py    # Copy 3
```
Bug fix in v3/users.py? Must also fix in v1/users.py and v2/users.py. Usually doesn't happen → v1 has unfixed bugs.

**First approach: merge into one codebase with version switches**
```python
def get_user(user_id, version):
    user = db.get_user(user_id)
    if version == 'v1':
        return serialize_v1(user)
    elif version == 'v2':
        return serialize_v2(user)
    else:
        return serialize_v3(user)
```
This eliminates duplication of business logic but adds version branching everywhere. With 3 versions, every function has a 3-way if/else. Messy.

**Second approach: shared business logic, version-specific serialization**
Separate concerns: the BUSINESS LOGIC is the same for all versions. Only the API CONTRACT (request/response format) differs between versions.

```
shared/
  services/       # Business logic (one copy)
    user_service.py
    order_service.py
api/
  v1/serializers.py  # Only serialization differs
  v2/serializers.py
  v3/serializers.py
```

This is better. Fix a bug in the service layer → all versions are fixed. But still maintaining 3 serializer sets.

**Third approach (backtracking further): additive-only API evolution**
What if most endpoints DON'T need versioning? If you only make additive changes (add new fields, never remove or rename), no versioning is needed.

Looking at what typically CHANGES between API versions:
- New fields added → additive, backward compatible
- Fields renamed → breaking
- Fields removed → breaking
- Response structure changed → breaking

If breaking changes are rare, you could:
1. Make most changes additive (no version bump needed)
2. Only version the specific endpoints that have breaking changes
3. Deprecate old versions with a sunset timeline

This is the approach Stripe, GitHub, and Twilio use.
</think>

Three codebases is unmaintainable. Let me trace through the fix:

**Attempt 1:** Version switches in every function → version spaghetti in business logic.
**Attempt 2:** Shared logic + version-specific serializers → better but still 3 serializer copies.
**Backtrack:** Most endpoints DON'T need versioning. Use additive-only changes and only version what actually breaks.

## The Migration Plan

### Step 1: Consolidate Business Logic (Week 1-2)

```python
# BEFORE: 3 copies of the same logic
# v1/users.py
def get_user(user_id):
    user = db.query("SELECT * FROM users WHERE id = %s", user_id)
    return {"id": user.id, "name": user.name}

# v3/users.py (same logic, different response)
def get_user(user_id):
    user = db.query("SELECT * FROM users WHERE id = %s", user_id)
    return {"id": user.id, "name": user.name, "email": user.email, "avatar": user.avatar}


# AFTER: One service, version-specific serializers
# services/user_service.py (ONE copy of business logic)
class UserService:
    def get_user(self, user_id: int) -> User:
        return db.query(User).get(user_id)
    # Bug fixes go here → all versions get the fix

# serializers/user.py
def serialize_user_v1(user: User) -> dict:
    return {"id": user.id, "name": user.name}

def serialize_user_v3(user: User) -> dict:
    return {
        "id": user.id, "name": user.name,
        "email": user.email, "avatar": user.avatar_url,
    }
```

### Step 2: Single Route Layer With Version Dispatch

```python
# routes/users.py — ONE route file, not three
from services.user_service import UserService
from serializers.user import serialize_user_v1, serialize_user_v3

service = UserService()

@app.get("/api/v1/users/<int:user_id>")
def get_user_v1(user_id):
    user = service.get_user(user_id)  # Same business logic
    return jsonify(serialize_user_v1(user))  # V1 response format

@app.get("/api/v3/users/<int:user_id>")
def get_user_v3(user_id):
    user = service.get_user(user_id)  # Same business logic
    return jsonify(serialize_user_v3(user))  # V3 response format

# Most endpoints are IDENTICAL across versions → no version suffix needed
@app.get("/api/v1/products/<int:product_id>")
@app.get("/api/v3/products/<int:product_id>")
def get_product(product_id):
    """Same response for all versions — no breaking changes here."""
    product = service.get_product(product_id)
    return jsonify(serialize_product(product))
```

### Step 3: Adopt Additive-Only Changes Going Forward

```python
# INSTEAD of creating v4 for new fields:
# Just ADD the field to the existing response

# Before:
{"id": 1, "name": "Alice"}

# After (additive, backward compatible):
{"id": 1, "name": "Alice", "avatar_url": "https://..."}

# Clients that don't know about avatar_url simply ignore it.
# No new version needed. No breaking change.

# ONLY create a new version when you MUST:
# - Remove a field (rare)
# - Change a field type (rare)
# - Restructure the response (rare)
```

### Step 4: Deprecate Old Versions

```python
# Add deprecation headers to v1
@app.after_request
def add_deprecation_headers(response):
    if request.path.startswith('/api/v1/'):
        response.headers['Deprecation'] = 'true'
        response.headers['Sunset'] = 'Sat, 01 Jan 2025 00:00:00 GMT'
        response.headers['Link'] = '</api/v3/>; rel="successor-version"'
    return response

# Log v1 usage to track migration
@app.before_request
def track_version_usage():
    if request.path.startswith('/api/v1/'):
        metrics.increment("api.deprecated_version_calls", tags={"version": "v1"})
```

## Final Architecture

```
services/              # Business logic (ONE copy)
  user_service.py
  order_service.py
  product_service.py

serializers/           # Version-specific response formats
  user.py              # serialize_user_v1(), serialize_user_v3()
  order.py             # Only for endpoints that DIFFER between versions

routes/                # ONE route file per resource
  users.py             # Routes for all versions
  orders.py
  products.py
```

## Migration Checklist

```markdown
For each endpoint across v1/v2/v3:

1. [ ] Is the business logic identical? → Consolidate to shared service
2. [ ] Is the response format identical? → Use one route for all versions
3. [ ] Only serialization differs? → Shared service + version serializer
4. [ ] Logic differs? → Keep version-specific handler (rare, document why)

Expected result:
  - ~80% of endpoints are identical → one implementation
  - ~15% differ only in serialization → shared service + serializer
  - ~5% have actual logic differences → version-specific (document these)
```

The backtracking insight: full codebase versioning creates an N×M maintenance nightmare. Most API changes are additive and don't need versioning at all.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
