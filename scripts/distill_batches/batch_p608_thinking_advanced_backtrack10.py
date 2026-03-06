"""Phase 2A: Advanced Reasoning — Backtracking & Dead-End Recovery (Part 10/10)"""

PAIRS = [
    (
        "thinking/backtrack-polling-to-webhooks-to-streaming",
        "Our frontend polls the server every 2 seconds to check for new notifications. It works but it's hammering our API. How do I make this real-time?",
        r'''<think>
Frontend polling for notifications — classic problem. Let me think through the approaches and their trade-offs.

**Current approach: Polling**
- Frontend calls GET /notifications every 2 seconds
- Simple to implement
- Wastes bandwidth when there are no new notifications (99% of requests return nothing)
- At 1000 users: 500 requests/second just for notification checks
- Latency: up to 2 seconds delay

**First approach: Long polling**
Client makes a request, server holds it open until there's data or timeout:
```
Client: GET /notifications?since=last_id
Server: (holds connection open... waits... notification arrives!)
Server: 200 OK [{new notification}]
Client: immediately makes another request
```

Pros: Near real-time, fewer wasted requests
Cons: Still one connection per client held open, server needs to manage open connections, load balancer timeout issues

Actually, this is a solid middle ground but let me think about whether it's the best for notifications specifically.

**Second approach: WebSockets**
Persistent bidirectional connection. Server pushes notifications instantly.

Pros: True real-time, efficient, bidirectional
Cons: Stateful connections (doesn't scale horizontally as easily), need sticky sessions or pub/sub, more complex infrastructure, reconnection logic needed

Wait — for NOTIFICATIONS (server → client only), WebSockets are overkill. We don't need bidirectional communication. Let me reconsider.

**Third approach (backtracking from WebSockets): Server-Sent Events (SSE)**
Unidirectional: server → client stream over HTTP. Perfect for notifications.

```
Client: GET /notifications/stream
        Accept: text/event-stream

Server: (keeps connection open, sends events as they happen)
        data: {"type": "notification", "message": "New comment on your PR"}

        data: {"type": "notification", "message": "Build succeeded"}
```

Pros:
- Simpler than WebSockets (plain HTTP, works with existing infrastructure)
- Auto-reconnection built into browser EventSource API
- Works with HTTP/2 multiplexing
- Unidirectional is exactly what notifications need
- No special load balancer configuration
- Text-based, easy to debug

Cons:
- Unidirectional only (fine for notifications)
- Limited to ~6 connections per domain in HTTP/1.1 (HTTP/2 solves this)
- Need to handle reconnection state (Last-Event-ID header)

SSE is the right choice here. I initially jumped to WebSockets because it's the "real-time" default, but for server-push-only use cases, SSE is simpler and more appropriate.
</think>

My first instinct was WebSockets, but I backtracked to **Server-Sent Events (SSE)** — it's the right tool for server-to-client notifications.

## Why I Backtracked from WebSockets

```
Notifications are ONE-DIRECTIONAL: server → client

WebSocket: ←→ bidirectional    (overkill for this)
SSE:       →  server-to-client (exactly this)

WebSocket adds complexity you don't need:
  - Custom protocol upgrade handling
  - Sticky sessions or Redis pub/sub for horizontal scaling
  - Manual reconnection logic
  - Binary framing overhead
  - Special load balancer/proxy configuration

SSE gives you real-time push over plain HTTP.
```

## The Solution: Server-Sent Events

```python
# Backend (Flask/FastAPI example)
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import asyncio

app = FastAPI()

# In production: use Redis pub/sub or similar for cross-instance delivery
notification_queues: dict[str, asyncio.Queue] = {}

async def event_stream(user_id: str):
    queue = notification_queues.setdefault(user_id, asyncio.Queue())
    try:
        while True:
            # Wait for notification (blocks until one arrives)
            notification = await queue.get()
            yield f"id: {notification['id']}\n"
            yield f"data: {json.dumps(notification)}\n\n"
    except asyncio.CancelledError:
        del notification_queues[user_id]

@app.get("/notifications/stream")
async def notification_stream(request: Request, user_id: str):
    return StreamingResponse(
        event_stream(user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )
```

```javascript
// Frontend — built-in browser API, auto-reconnects!
const events = new EventSource('/notifications/stream?user_id=42');

events.onmessage = (event) => {
    const notification = JSON.parse(event.data);
    showNotification(notification);
};

events.onerror = () => {
    // Browser automatically reconnects with Last-Event-ID header
    console.log('Connection lost, reconnecting...');
};

// That's it. No library needed. No reconnection logic.
// Browser handles reconnection automatically.
```

## Comparison: All Three Approaches

```
                    Polling         SSE              WebSocket
────────────────────────────────────────────────────────────────
Latency             0-2 sec         Instant          Instant
Wasted requests     ~99%            0%               0%
Direction           Client→Server   Server→Client    Bidirectional
Complexity          Low             Low-Medium       Medium-High
Browser support     Universal       Universal*       Universal
Auto-reconnect      N/A             Built-in         Manual
HTTP/2 compatible   Yes             Yes (multiplexed) Separate
Load balancer       Standard        Standard         Needs config
Server resources    Per-request     1 conn/client    1 conn/client

* EventSource API works in all modern browsers
```

## When Each Approach Is Right

```
Polling:     Checking something every few minutes (not real-time)
             Example: checking build status, refreshing dashboards

SSE:         Server pushes data to client (one-way real-time)
             Example: notifications, live feeds, stock tickers, logs

WebSocket:   Bidirectional real-time communication
             Example: chat, collaborative editing, gaming, trading
```

Your notifications need server→client push. SSE is the simplest path from polling to real-time.'''
    ),
    (
        "thinking/backtrack-microservice-per-entity-to-bounded-context",
        "We're breaking our monolith into microservices. We have Users, Orders, Products, Payments, Shipping, and Reviews. Should each table become its own microservice?",
        r'''<think>
One microservice per database table — this is the classic mistake. Let me work through why it seems logical and why it fails.

**First approach: one service per entity**
- UserService, OrderService, ProductService, PaymentService, ShippingService, ReviewService
- 6 services for 6 tables
- Clean separation, right?

Problems:
1. **Distributed transactions everywhere**: Creating an order requires: check user exists (UserService) → check product stock (ProductService) → create order (OrderService) → charge payment (PaymentService) → update stock (ProductService). That's 5 service calls for one business operation. Any failure requires distributed rollback.

2. **Chatty communication**: Every business operation crosses multiple services. An order detail page needs: order from OrderService + user from UserService + products from ProductService + payment from PaymentService + shipping from ShippingService + reviews from ReviewService. 6 network calls for one page load.

3. **Coupled deployment**: You can't change the order creation flow without deploying OrderService, ProductService, and PaymentService together. They're not independently deployable.

This is a "distributed monolith" — you got the complexity of microservices without the benefits.

**Let me backtrack. What's the right decomposition?**

The answer is bounded contexts from Domain-Driven Design. Group things by business capability, not by data entity.

**Better approach: bounded contexts**

What are the actual business capabilities?
1. **Commerce** (Orders + Order Items + Payments) — "buying things"
2. **Catalog** (Products + Categories + Pricing) — "what we sell"
3. **Identity** (Users + Authentication + Profiles) — "who our users are"
4. **Fulfillment** (Shipping + Tracking + Returns) — "delivering things"
5. **Engagement** (Reviews + Ratings + Recommendations) — "user feedback"

Now: 5 services instead of 6, but the boundaries are MUCH better.

Creating an order: Commerce service handles the entire operation internally (order + payment in one transaction). It only needs to ASK Catalog "does this product exist and what's the price?" — a simple read.

This is the key insight: services should encapsulate BUSINESS OPERATIONS, not data tables.
</think>

No — one service per table is the most common microservices mistake. I initially considered it before backtracking to **bounded contexts**.

## Why "One Service Per Table" Fails

```
Your 6 services: User, Order, Product, Payment, Shipping, Review

Creating a single order requires:
  1. UserService:    → validate user exists
  2. ProductService: → check stock, get price
  3. OrderService:   → create order record
  4. PaymentService: → charge card
  5. ProductService: → decrement stock
  6. ShippingService:→ create shipment

  = 6 network calls across 5 services
  = distributed transaction (any step can fail)
  = if payment succeeds but stock decrement fails: inconsistent state
  = you need saga pattern / compensating transactions for EVERY operation

This is a "distributed monolith" — all the complexity of microservices
with none of the benefits (independent deployment, team autonomy).
```

## The Right Approach: Bounded Contexts

```
Group by BUSINESS CAPABILITY, not by database table:

┌─ Commerce Service ──────────────────────┐
│  Orders + Order Items + Payments         │
│  "Everything about buying things"        │
│  CREATE ORDER = one local transaction    │
│  (no distributed transaction needed!)    │
└──────────────────────────────────────────┘

┌─ Catalog Service ───────────────────────┐
│  Products + Categories + Pricing         │
│  "Everything about what we sell"         │
│  Product CRUD, search, inventory         │
└──────────────────────────────────────────┘

┌─ Identity Service ──────────────────────┐
│  Users + Auth + Profiles + Preferences   │
│  "Everything about who our users are"    │
│  Login, registration, profile management │
└──────────────────────────────────────────┘

┌─ Fulfillment Service ──────────────────┐
│  Shipping + Tracking + Returns           │
│  "Everything about delivering things"    │
│  Triggered AFTER order is confirmed      │
└──────────────────────────────────────────┘

┌─ Engagement Service ───────────────────┐
│  Reviews + Ratings + Recommendations     │
│  "Everything about user feedback"        │
│  Can be eventually consistent            │
└──────────────────────────────────────────┘
```

## How This Changes the Order Flow

```
PER-TABLE approach (distributed nightmare):
  Browser → API Gateway → UserService → ProductService
                        → OrderService → PaymentService
                        → ProductService → ShippingService
  6 network calls, distributed transaction, coupled deployment

BOUNDED CONTEXT approach (clean):
  Browser → API Gateway → Commerce Service (creates order + payment
                            in ONE local database transaction)
                        → publishes event: "order.created"
                        → Catalog Service handles stock (async)
                        → Fulfillment Service creates shipment (async)

  1 synchronous call + 2 async events
  No distributed transaction needed!
```

## The Litmus Test

```
Ask yourself for each proposed service boundary:

  "Can this service complete its PRIMARY operation
   without synchronously calling another service?"

  Per-table OrderService:
    Create order → needs UserService + ProductService + PaymentService
    Answer: NO → bad boundary

  Bounded-context Commerce Service:
    Create order → has orders + payments in same DB
    Answer: YES (just needs a read from Catalog for price) → good boundary

  Rule of thumb:
    If Service A can't do anything without calling Service B,
    they should be ONE service.
```

## Data Duplication Is OK

```
Each service owns its data and may COPY what it needs:

Commerce Service stores:
  - order.customer_name (copied from Identity at order time)
  - order.product_name, order.price (copied from Catalog at order time)

Why? Because the order record should reflect what was true AT ORDER TIME.
If the user changes their name or the product price changes later,
the order should still show the original values.

This isn't denormalization — it's recording a business fact:
"On March 5, Alice bought Widget X for $29.99"
```'''
    ),
    (
        "thinking/backtrack-env-files-to-secrets-manager",
        "We store all our secrets in .env files committed to a private repo. The team says it's fine because the repo is private. Should I push for a secrets manager?",
        r'''<think>
Secrets in .env files in a private repo. The team thinks it's fine. Let me think about whether they're right or wrong.

**First thought: it's not that bad**
- Private repo means only team members have access
- .env files are simple to use — just load them
- Every developer knows how to use them
- For a small team with a private repo, the risk might be acceptable

Let me think harder about the actual risks though.

**Actual risks of secrets in git:**
1. Git history is forever. Even if you rotate a secret, the old one is in git history. `git log -p` reveals everything ever committed.
2. Clone = all secrets. Anyone who clones the repo (new hire, CI system, contractor) gets every secret ever.
3. Private repos aren't permanent. Repos get made public by accident (happened to Uber, exposed 57M records). Organizations get acquired, repos get transferred.
4. No audit trail. Who accessed which secret? When? No way to know.
5. No rotation mechanism. Changing a secret means commit, merge, deploy. Manual and error-prone.
6. Blast radius. One compromised developer laptop = all secrets from all environments.
7. Environment coupling. Same file has dev and prod secrets? Or separate files? Gets messy.

OK, so the "it's fine" argument doesn't hold up. But is a full secrets manager the right step, or is there an intermediate option?

**Let me consider the middle ground:**
- .env files but NOT committed (in .gitignore) + shared via secure channel → better, but manual management
- Encrypted .env files (git-crypt, SOPS) → secrets in repo but encrypted, need key management
- Full secrets manager (Vault, AWS Secrets Manager) → proper solution but operational overhead

For a small team, the jump from .env-in-git to HashiCorp Vault is huge. Let me think about what's proportionate.

**My recommendation path:**
1. Immediate: Remove .env from git, add to .gitignore, rotate ALL exposed secrets
2. Short term: Use cloud provider's secrets manager (AWS SSM Parameter Store, GCP Secret Manager) — much simpler than Vault
3. Future: Full secrets manager if you need cross-cloud, dynamic secrets, or audit trails

I should NOT recommend Vault for a small team. That's over-engineering. Cloud-native secrets management is the right middle ground.
</think>

The team's reasoning — "private repo = safe" — has real holes. But the answer isn't necessarily a full secrets manager immediately. Let me trace my thinking.

## Why "Private Repo Is Fine" Is Wrong

```
Risk 1: GIT HISTORY IS PERMANENT
  You committed DB_PASSWORD=hunter2 in 2023.
  You rotated it in 2024 and committed DB_PASSWORD=new_pass.
  hunter2 is still in: git log -p -- .env
  Every clone has every secret you EVER committed.

Risk 2: CLONE = ALL SECRETS
  New hire clones repo → gets production database password
  CI system clones repo → secrets in build environment
  Contractor gets "read" access → gets every secret ever

Risk 3: PRIVATE ISN'T PERMANENT
  - Uber accidentally exposed a private repo → 57M records breached
  - Repos get transferred during acquisitions
  - Someone adds a GitHub Action that logs environment variables
  - Team member forks to personal account

Risk 4: NO AUDIT TRAIL
  Q: "Who accessed the production database password?"
  A: "Everyone who ever cloned the repo. We have no idea."

Risk 5: ALL ENVIRONMENTS, ONE FILE
  .env often has dev AND staging AND prod secrets.
  Junior dev with repo access = has production credentials.
```

## The Migration Path (Proportionate to Team Size)

```
DON'T jump straight to HashiCorp Vault. That's over-engineering for most teams.

Step 1: IMMEDIATE (today)
  ├── Remove .env from git tracking
  ├── Add .env to .gitignore
  ├── ROTATE every secret that was ever committed
  │   (they're in git history forever — consider them compromised)
  └── Commit a .env.example with placeholder values

Step 2: SHORT TERM (this sprint)
  ├── Use your cloud provider's built-in secrets management:
  │   ├── AWS: SSM Parameter Store (free) or Secrets Manager ($0.40/secret/month)
  │   ├── GCP: Secret Manager
  │   ├── Azure: Key Vault
  │   └── Heroku/Railway/Fly: built-in env var management
  └── App reads secrets from the secrets service, not files

Step 3: IF NEEDED LATER
  └── HashiCorp Vault / full secrets management
      (dynamic secrets, automatic rotation, detailed audit logs)
      Only if you have compliance requirements or 50+ secrets
```

## Practical Implementation

```python
# Before: .env file committed to repo
# DB_PASSWORD=hunter2
# STRIPE_KEY=sk_live_abc123
# JWT_SECRET=mysecretkey

import os
from dotenv import load_dotenv
load_dotenv()  # Reads from .env file
db_password = os.environ['DB_PASSWORD']


# After: secrets from cloud provider (AWS example)
import boto3

def get_secret(name):
    ssm = boto3.client('ssm')
    param = ssm.get_parameter(Name=name, WithDecryption=True)
    return param['Parameter']['Value']

db_password = get_secret('/myapp/prod/DB_PASSWORD')

# Or simpler: just use environment variables set by your platform
# (Heroku, Railway, ECS task definitions, K8s secrets)
db_password = os.environ['DB_PASSWORD']  # Set by platform, not .env file
```

```bash
# Step 1: Remove .env from git (keep the file locally)
echo ".env" >> .gitignore
git rm --cached .env
git commit -m "Remove .env from tracking — secrets should not be in git"

# Step 2: Create .env.example for developers
cat > .env.example << 'EOF'
# Copy this to .env and fill in real values
# Get secrets from the team's password manager
DB_HOST=localhost
DB_PASSWORD=<ask-team-lead>
STRIPE_KEY=<use-test-key-from-stripe-dashboard>
JWT_SECRET=<generate-with: openssl rand -hex 32>
EOF
git add .env.example
git commit -m "Add .env.example with placeholder values"

# Step 3: ROTATE EVERYTHING (critical!)
# Every secret that was ever in .env is in git history.
# Generate new passwords, new API keys, new JWT secrets.
# Old ones must be considered compromised.
```

## Responding to the Team's Pushback

```
"It's a private repo, only we have access"
→ Git history means every secret EVER committed is accessible
  to everyone who EVER had access. Including that intern from 2022.

"We'll just be careful"
→ One git push to wrong remote, one repo visibility toggle,
  one GitHub Action that prints env vars = breach.

"A secrets manager is overkill"
→ Agree! Don't use Vault. Just use your cloud platform's built-in
  env vars or parameter store. It's the same effort as .env files
  but without the git history risk.

"We'd have to change our workflow"
→ The workflow change is minimal:
  Before: copy .env from repo
  After: copy .env.example, fill from password manager
  (or: platform sets env vars automatically, no .env at all)
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
