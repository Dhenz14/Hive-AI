"""Phase 2: Advanced Reasoning — Mixed Subcategories (Part 17)"""

PAIRS = [
    (
        "thinking/uncertainty-kubernetes-vs-docker-compose",
        "Should we use Kubernetes or Docker Compose for our production deployment? We're a 5-person startup with 3 microservices.",
        r'''<think>
Kubernetes vs Docker Compose for a 5-person startup with 3 microservices.

**Kubernetes:**
Pros: auto-scaling, self-healing, rolling deploys, service discovery, massive ecosystem
Cons: enormous complexity, needs dedicated DevOps knowledge, expensive (managed K8s clusters), overkill for 3 services

**Docker Compose:**
Pros: simple, easy to understand, fast to set up, cheap (single server), everyone can manage it
Cons: no auto-scaling, no self-healing, no rolling deploys out of the box, single-server limitation

**For a 5-person startup with 3 services:**
The answer is almost certainly Docker Compose (or a managed platform) — at least for now.

Kubernetes solves problems they don't have yet:
- Auto-scaling? They probably have <1000 users
- Multi-region? Not yet
- Zero-downtime deploys? Nice but not critical at their stage

The complexity cost of K8s is MASSIVE for a small team. Easily 20-30% of one person's time just maintaining the cluster.

**Confidence: 85% Docker Compose / managed PaaS**

The 15% uncertainty is if they have specific scaling requirements (ML inference, real-time processing, regulatory requirements for high availability).

**Alternative middle ground:** Managed platforms like Railway, Fly.io, Render — Docker-simple with some K8s-like features.
</think>

**85% confidence: Docker Compose (or a managed platform like Railway/Fly.io), not Kubernetes.**

## The Analysis

```
YOUR SITUATION:
  5-person team + 3 microservices + startup

KUBERNETES SOLVES:
  ✓ Auto-scaling (10→10,000 pods)
  ✓ Self-healing (restart crashed containers)
  ✓ Rolling deployments (zero downtime)
  ✓ Service mesh (inter-service communication)
  ✓ Multi-region deployment

YOU PROBABLY NEED:
  ✓ Deploy 3 services reliably
  ✓ Easy to update when you push code
  ✓ Reasonable uptime
  ✗ Auto-scaling (you have <1000 users?)
  ✗ Multi-region (not yet)
  ✗ Service mesh (3 services don't need it)
```

## The Hidden Cost of Kubernetes

```
KUBERNETES OPERATIONAL TAX:
  - Learning curve: 2-3 months before team is comfortable
  - YAML management: hundreds of lines of config per service
  - Cluster maintenance: upgrades, node pools, networking, RBAC
  - Debugging: "why is this pod in CrashLoopBackOff?" → 45 minutes
  - Cost: managed K8s ($73/mo minimum on GKE) + node VMs + load balancers
  - DevOps time: ~20-30% of one engineer's time

  For a 5-person team, that's 4-6% of your TOTAL engineering capacity
  spent on infrastructure instead of product.

DOCKER COMPOSE OPERATIONAL TAX:
  - Learning curve: 1-2 days
  - Config: one docker-compose.yml file (50-100 lines)
  - Maintenance: occasional docker system prune
  - Debugging: docker logs service_name
  - Cost: one VPS ($20-80/mo)
  - DevOps time: ~2-5% of one engineer's time
```

## Docker Compose for Production (Yes, It Works)

```yaml
# docker-compose.prod.yml — your entire infrastructure
version: "3.8"

services:
  api:
    image: your-registry/api:${VERSION}
    restart: always          # Self-healing (basic)
    ports:
      - "8080:8080"
    environment:
      - DATABASE_URL=postgres://db:5432/app
    depends_on:
      - db
      - redis
    deploy:
      resources:
        limits:
          memory: 512M

  worker:
    image: your-registry/worker:${VERSION}
    restart: always
    environment:
      - REDIS_URL=redis://redis:6379

  frontend:
    image: your-registry/frontend:${VERSION}
    restart: always
    ports:
      - "80:80"
      - "443:443"

  db:
    image: postgres:16
    restart: always
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    restart: always

volumes:
  pgdata:

# Deploy: ssh server "cd /app && docker compose pull && docker compose up -d"
# That's it. Your entire deploy is one command.
```

## When You Actually Need Kubernetes

```
UPGRADE TO KUBERNETES WHEN (any of these):
  □ You have >10 services (compose becomes unwieldy)
  □ You need auto-scaling (traffic varies 10x+)
  □ You need zero-downtime deploys (99.9% SLA)
  □ You have a dedicated DevOps/platform engineer
  □ You're spending >$500/mo on infrastructure
  □ You need multi-region deployment
  □ Regulatory requirements mandate HA

UNTIL THEN: Docker Compose on a single beefy server
  ($40/mo for 8GB RAM handles a LOT of traffic)
```

## The Middle Ground (My Actual Recommendation)

```
Consider managed platforms instead of either:

  Railway / Render / Fly.io:
    - Deploy from Dockerfile (as simple as Compose)
    - Auto-scaling (like K8s)
    - Managed databases
    - $5-25/service/month
    - Zero infrastructure management

  These give you K8s-like features with Compose-like simplicity.
  Perfect for startups until you hit $500+/mo and want more control.
```

**Uncertainty sources:** If you have ML inference workloads, real-time requirements, or compliance needs, the calculus changes. But for a typical web startup with 3 services, Kubernetes is almost always premature.'''
    ),
    (
        "thinking/causal-npm-install-slow",
        "Our npm install takes 8 minutes in CI. It used to take 30 seconds. We haven't changed our dependencies recently. What happened?",
        r'''<think>
npm install going from 30 seconds to 8 minutes without dependency changes. Let me reason through possible causes.

**Key clue: "haven't changed dependencies recently"**
So the package.json and package-lock.json are (probably) the same. What else could cause this?

**Possible causes (ordered by likelihood):**

1. **Cache invalidation** — CI cache was cleared or expired
   - Most CI systems cache node_modules or ~/.npm between runs
   - If the cache key changed (different OS, Node version bump, lockfile hash change), full reinstall
   - This is the #1 cause of sudden npm slowdowns in CI

2. **npm registry slowdown or CDN issue**
   - If npm's registry is slow, every package download takes longer
   - Rare but happens, especially with custom registries (Artifactory, Verdaccio)

3. **Node.js version change**
   - Node version bump → different native module compilation → longer install
   - e.g., Node 18→20 requires recompiling node-sass, sharp, bcrypt, etc.

4. **Lock file changes**
   - Even without explicit dependency changes, a lockfile regeneration (different npm version) can change resolution
   - npm 8 vs npm 9 vs npm 10 generate different lock formats

5. **Transitive dependency explosion**
   - A dependency you didn't change updated ITS dependencies
   - If lockfile wasn't committed, npm resolves latest → could pull way more packages

6. **CI runner resource change**
   - Runner downgraded (less CPU/RAM/bandwidth)
   - Different region/provider

**Most likely: cache miss.** The 30s→8min ratio strongly suggests going from cached→uncached install.
</think>

The jump from 30s to 8min almost certainly means your **CI cache stopped working**. A cached npm install is fast; an uncached one downloads everything from scratch.

## Most Likely Cause: Cache Miss

```
BEFORE (30 seconds):
  CI cache hit → node_modules already present
  → npm install checks lock file → "everything installed" → done

AFTER (8 minutes):
  CI cache MISS → empty node_modules
  → npm install downloads ALL packages from registry
  → installs everything from scratch → 8 minutes

WHY the cache miss happened:
  1. Cache key changed (most common)
  2. Cache expired (TTL exceeded)
  3. CI configuration changed
  4. Someone cleared the cache manually
```

## Diagnosis

```bash
# 1. Check if cache is being used at all
# In your CI config, look for cache configuration:
# GitHub Actions:
- uses: actions/cache@v3
  with:
    path: ~/.npm  # or node_modules
    key: ${{ runner.os }}-node-${{ hashFiles('**/package-lock.json') }}
    #                                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    # If package-lock.json changed → cache key changed → cache miss

# 2. Check if lock file changed (even without dependency changes)
git log --oneline -10 -- package-lock.json
# If someone ran `npm install` with a different npm version,
# the lock file format may have changed → new cache key

# 3. Check Node.js version in CI
node --version
# If this changed (CI image updated), native modules need recompilation

# 4. Check npm version
npm --version
# npm 8→9→10 changes lock file format
```

## Fixes

```yaml
# GitHub Actions — proper caching
- name: Cache node modules
  uses: actions/cache@v4
  with:
    path: |
      ~/.npm
      node_modules
    key: ${{ runner.os }}-node-${{ hashFiles('**/package-lock.json') }}
    restore-keys: |
      ${{ runner.os }}-node-
      # ↑ Fallback: use ANY previous cache, even if lock file changed
      # Partial cache hit is much faster than no cache

- name: Install dependencies
  run: npm ci  # Use npm ci, NOT npm install (faster, respects lock file)
```

```yaml
# GitLab CI
cache:
  key:
    files:
      - package-lock.json
  paths:
    - node_modules/
  policy: pull-push  # Read cache AND write updated cache
```

## Other Optimizations

```bash
# 1. Use npm ci instead of npm install
npm ci        # Clean install from lock file — faster, deterministic
# vs
npm install   # Resolves dependencies — slower, may update lock file

# 2. Skip optional dependencies (saves time on native modules)
npm ci --ignore-scripts --no-optional
# Run scripts only for packages that need them:
npm rebuild sharp  # Only rebuild what you need

# 3. Pin your Node.js version in CI
# .nvmrc or .node-version
18.19.0
# This prevents surprise Node upgrades that invalidate caches

# 4. Pin your npm version
# package.json
"engines": {
    "node": "18.19.0",
    "npm": "10.2.4"
}
```

## Quick Diagnostic Checklist

```
□ Did the CI cache key change? (check package-lock.json git log)
□ Did the Node.js version change? (check CI image/runner)
□ Did the npm version change? (lock file format difference)
□ Is CI using npm ci or npm install? (ci is faster)
□ Are you caching node_modules or just ~/.npm?
□ Did someone clear the CI cache manually?
□ Is the npm registry responsive? (npm ping)
```'''
    ),
    (
        "thinking/abstraction-error-handling-to-resilience",
        "How should I handle errors in my Express.js API? Right now I have try/catch in every route handler and it's repetitive.",
        r'''<think>
Error handling in Express — let me ladder from the concrete problem to the abstraction.

**Concrete: try/catch in every route**
The user has something like:
```
app.get('/users', async (req, res) => {
    try {
        const users = await getUsers();
        res.json(users);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});
```
Repeated 50 times.

**Pattern: centralized error middleware**
Express has a built-in error handling pattern — error middleware with 4 parameters. This eliminates per-route try/catch.

**Principle: error handling as a cross-cutting concern**
Errors should be handled at the right LEVEL:
- Individual function: handle recoverable errors (retry, fallback)
- Route/controller: handle business logic errors (validation, not found)
- Global middleware: handle unexpected errors (log, return 500)

**Policy: error classification and response strategy**
Operational errors (expected, recoverable) vs programmer errors (bugs, crash).
Different error types get different responses.
</think>

Let me build from your repetitive try/catch up to a proper error architecture.

## Level 1: Concrete — Centralize Error Handling

```javascript
// ❌ BEFORE: try/catch in EVERY route (50+ copies)
app.get('/users', async (req, res) => {
    try {
        const users = await db.getUsers();
        res.json(users);
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: 'Internal server error' });
    }
});

app.get('/users/:id', async (req, res) => {
    try {
        const user = await db.getUser(req.params.id);
        if (!user) return res.status(404).json({ error: 'Not found' });
        res.json(user);
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: 'Internal server error' });
    }
});
// ... repeated 50 times

// ✅ AFTER: async wrapper + error middleware
// Step 1: wrap async routes to forward errors automatically
const asyncHandler = (fn) => (req, res, next) =>
    Promise.resolve(fn(req, res, next)).catch(next);

// Step 2: clean route handlers (no try/catch needed)
app.get('/users', asyncHandler(async (req, res) => {
    const users = await db.getUsers();
    res.json(users);  // If db.getUsers() throws, asyncHandler catches and calls next(err)
}));

app.get('/users/:id', asyncHandler(async (req, res) => {
    const user = await db.getUser(req.params.id);
    if (!user) throw new NotFoundError('User not found');
    res.json(user);
}));

// Step 3: ONE global error handler (at the end of your middleware chain)
app.use((err, req, res, next) => {
    console.error(err);
    const status = err.statusCode || 500;
    res.status(status).json({
        error: err.message || 'Internal server error',
    });
});
```

## Level 2: Pattern — Custom Error Classes

```javascript
// Define error types that carry their own status codes
class AppError extends Error {
    constructor(message, statusCode) {
        super(message);
        this.statusCode = statusCode;
        this.isOperational = true;  // Expected error, not a bug
    }
}

class NotFoundError extends AppError {
    constructor(message = 'Resource not found') {
        super(message, 404);
    }
}

class ValidationError extends AppError {
    constructor(message, fields = {}) {
        super(message, 400);
        this.fields = fields;
    }
}

class UnauthorizedError extends AppError {
    constructor(message = 'Authentication required') {
        super(message, 401);
    }
}

// Route handlers throw the right error type:
app.put('/users/:id', asyncHandler(async (req, res) => {
    if (!req.body.email) throw new ValidationError('Email required', { email: 'required' });

    const user = await db.getUser(req.params.id);
    if (!user) throw new NotFoundError('User not found');

    if (user.id !== req.user.id) throw new UnauthorizedError('Not your account');

    const updated = await db.updateUser(req.params.id, req.body);
    res.json(updated);
}));

// Global handler knows how to format each type:
app.use((err, req, res, next) => {
    if (err.isOperational) {
        // Expected error — send clean message to client
        return res.status(err.statusCode).json({
            error: err.message,
            ...(err.fields && { fields: err.fields }),
        });
    }

    // Unexpected error (bug) — log full details, send generic message
    console.error('UNEXPECTED ERROR:', err);
    res.status(500).json({ error: 'Internal server error' });
});
```

## Level 3: Principle — Operational vs Programmer Errors

```
TWO KINDS OF ERRORS:

OPERATIONAL (expected, recoverable):
  - User not found (404)
  - Invalid input (400)
  - Auth failed (401)
  - Rate limited (429)
  - External service down (503)
  → Handle gracefully, return meaningful error to client

PROGRAMMER (bugs, not recoverable):
  - TypeError: cannot read property of undefined
  - RangeError: array out of bounds
  - Logic errors in your code
  → Log with full stack trace, return generic 500, alert the team

Your error handler should DISTINGUISH between these:
  Operational → send clean error response
  Programmer → log everything, generic response, consider crashing (Node.js)
```

## Level 4: Policy — Error Handling Architecture

```
LAYER          HANDLES                        EXAMPLE
─────────────────────────────────────────────────────────────────
Validation     Input errors BEFORE processing  "email is required"
middleware     (Joi, Zod, express-validator)

Route          Business logic errors           "user not found"
handler        (throw custom AppError)

Service        Recoverable failures            "payment retry succeeded"
layer          (retry, fallback, circuit break)

Global error   Everything that falls through   Log + 500 response
middleware     (unexpected errors, bugs)

Process        Fatal errors                    "unhandledRejection"
handler        (log, alert, graceful shutdown)

// Process-level handler for unrecoverable errors
process.on('unhandledRejection', (err) => {
    console.error('UNHANDLED REJECTION:', err);
    // Graceful shutdown: stop accepting requests, finish in-flight, exit
    server.close(() => process.exit(1));
});
```

The abstraction ladder: repetitive try/catch → asyncHandler + error middleware → custom error classes → operational vs programmer error distinction → layered error architecture.'''
    ),
    (
        "thinking/analogy-docker-containers-shipping",
        "I keep hearing about Docker containers but I don't get why they matter. My app runs fine on my machine. Why would I need Docker?",
        r'''<think>
Docker explanation via the shipping container analogy — this is actually where the name comes from.

**The problem Docker solves:**
"Works on my machine" → "doesn't work on the server"

Why? Because your machine and the server have:
- Different OS versions
- Different installed libraries
- Different Python/Node/Java versions
- Different file paths
- Different environment variables

**Shipping container analogy:**
Before standardized shipping containers, loading a cargo ship was a nightmare:
- Every item was a different shape and size
- Had to be individually loaded and unloaded
- Fragile items mixed with heavy items
- Different ports had different loading equipment
- Theft and damage were common

After shipping containers:
- Everything goes in a standard box
- Any crane can lift any container
- Any ship can carry any container
- Any truck can transport any container
- Contents don't matter — the interface is the container

Docker does the same for software:
- Package your app + all dependencies in a standard "container"
- Any server that runs Docker can run your container
- Contents don't matter — the interface is the container
</think>

Docker is named after actual shipping containers — and the analogy is perfect.

## The Problem

```
YOUR MACHINE:
  Python 3.11, PostgreSQL 15, Redis 7, Ubuntu 22.04
  libssl 3.0, numpy 1.24, specific locale settings
  → App works perfectly ✅

PRODUCTION SERVER:
  Python 3.9, PostgreSQL 14, no Redis, CentOS 8
  libssl 1.1, numpy not installed, different locale
  → App crashes ❌

COWORKER'S MACHINE:
  Python 3.12, PostgreSQL 16, Redis 6, macOS
  → App works but with different behavior ⚠️

NEW HIRE:
  "I've been setting up my environment for 2 days and I still
   can't get the app to run. Which version of Node do I need?"
```

## The Shipping Container Analogy

```
BEFORE SHIPPING CONTAINERS (1950s):
  Loading a cargo ship:
  → Bags of coffee, barrels of wine, crates of machine parts
  → Each item different shape and size
  → Each port has different loading equipment
  → Takes DAYS to load/unload
  → Damage, theft, chaos

  = Before Docker:
  → Each app needs different languages, libraries, configs
  → Each server has different OS, tools, versions
  → Each developer's machine is set up differently
  → Takes DAYS to set up a new environment
  → "Works on my machine" chaos

AFTER SHIPPING CONTAINERS (1960s+):
  Everything goes in a STANDARD BOX (8x8x20 feet)
  → Any crane lifts any container
  → Any ship carries any container
  → Any truck transports any container
  → Port doesn't care what's inside
  → Loading/unloading takes HOURS, not days

  = After Docker:
  → App + all dependencies go in a STANDARD CONTAINER
  → Any server runs any container
  → Any developer runs any container
  → Server doesn't care what's inside
  → Setup takes MINUTES, not days
```

## In Practice

```dockerfile
# Dockerfile — the "packing instructions" for your container
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y libpq-dev

# Install Python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy your application code
COPY . /app
WORKDIR /app

# Run the app
CMD ["python", "app.py"]
```

```bash
# Build the container (pack the box)
docker build -t myapp .

# Run it ANYWHERE (your machine, server, CI, coworker's laptop)
docker run myapp

# It works IDENTICALLY everywhere because the container
# includes EVERYTHING: Python 3.11, all libraries, your code,
# system dependencies — all in one package.
```

## Why It Matters

```
WITHOUT DOCKER:
  New developer joins:
    "Install Python 3.11, PostgreSQL 15, Redis 7,
     set up virtualenv, install requirements,
     configure environment variables, set up SSL certs..."
    → 1-2 days before they can run the app

WITH DOCKER:
  New developer joins:
    docker compose up
    → App running in 30 seconds

WITHOUT DOCKER:
  Deploy to production:
    "Make sure the server has the right Python version,
     install dependencies, hope nothing conflicts,
     pray it works the same as dev..."
    → Anxiety

WITH DOCKER:
  Deploy to production:
    docker pull myapp:latest && docker run myapp
    → Same container that passed CI tests is what runs in production
    → If it worked in CI, it works in production (same container)
```

## The Key Mental Model

```
Docker container = your app frozen in time with everything it needs

It doesn't matter if the host runs Ubuntu, CentOS, Amazon Linux, or macOS.
The container carries its OWN operating system, libraries, and config.

Think of it as: instead of shipping instructions ("install X, configure Y"),
you ship the finished product, pre-assembled and tested.
```'''
    ),
    (
        "thinking/backtrack-manual-state-to-state-machine",
        "I have a complex order processing flow with statuses: pending, confirmed, processing, shipped, delivered, cancelled, refunded. My code has tons of if/else checking the current status before allowing transitions. It's buggy and hard to maintain.",
        r'''<think>
Complex status transitions with if/else everywhere — this is the classic state machine problem.

**Initial approach (what they have):**
Scattered if/else throughout the codebase:
- `if order.status == 'pending' and action == 'confirm': ...`
- `if order.status == 'shipped' and action == 'deliver': ...`
- `if order.status == 'cancelled': raise Error("can't modify cancelled")`

Problems:
- Valid transitions aren't explicit — buried in conditionals
- Easy to miss a transition or allow an invalid one
- Business rules scattered across many files
- Adding a new status requires finding all the if/else blocks

**Backtrack to: explicit state machine**
The order statuses and transitions form a finite state machine. Make the states and transitions EXPLICIT rather than implicit in if/else.

Benefits:
- All valid transitions defined in one place
- Invalid transitions automatically rejected
- Easy to visualize and reason about
- Adding a new state/transition is a data change, not a code change
</think>

Your if/else blocks are an implicit state machine. Make it **explicit**.

## The Problem

```python
# ❌ SCATTERED IF/ELSE: transitions buried in business logic
class OrderService:
    def confirm_order(self, order):
        if order.status == 'pending':
            order.status = 'confirmed'
        elif order.status == 'cancelled':
            raise ValueError("Cannot confirm cancelled order")
        else:
            raise ValueError(f"Cannot confirm order in {order.status} state")

    def ship_order(self, order):
        if order.status == 'processing':
            order.status = 'shipped'
        elif order.status in ('cancelled', 'refunded'):
            raise ValueError("Cannot ship")
        elif order.status == 'pending':
            raise ValueError("Must confirm first")
        # Did I cover all states? Who knows...

    def cancel_order(self, order):
        if order.status in ('pending', 'confirmed'):
            order.status = 'cancelled'
        elif order.status == 'shipped':
            raise ValueError("Already shipped, use refund instead")
        # What about 'processing'? Bug: we forgot it.
```

## Backtrack: Explicit State Machine

```python
# ✅ AFTER: all transitions defined in ONE place
from enum import Enum

class OrderStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"

# Define ALL valid transitions explicitly
TRANSITIONS = {
    OrderStatus.PENDING: {
        "confirm": OrderStatus.CONFIRMED,
        "cancel": OrderStatus.CANCELLED,
    },
    OrderStatus.CONFIRMED: {
        "start_processing": OrderStatus.PROCESSING,
        "cancel": OrderStatus.CANCELLED,
    },
    OrderStatus.PROCESSING: {
        "ship": OrderStatus.SHIPPED,
        "cancel": OrderStatus.CANCELLED,  # Can still cancel during processing
    },
    OrderStatus.SHIPPED: {
        "deliver": OrderStatus.DELIVERED,
        "refund": OrderStatus.REFUNDED,   # Shipped but returned
    },
    OrderStatus.DELIVERED: {
        "refund": OrderStatus.REFUNDED,   # Post-delivery refund
    },
    OrderStatus.CANCELLED: {},   # Terminal state — no transitions out
    OrderStatus.REFUNDED: {},    # Terminal state — no transitions out
}

class OrderStateMachine:
    def __init__(self, initial_status=OrderStatus.PENDING):
        self.status = initial_status

    def transition(self, action: str) -> OrderStatus:
        valid_actions = TRANSITIONS.get(self.status, {})

        if action not in valid_actions:
            valid = list(valid_actions.keys()) or ["none — terminal state"]
            raise InvalidTransition(
                f"Cannot '{action}' from '{self.status.value}'. "
                f"Valid actions: {valid}"
            )

        old_status = self.status
        self.status = valid_actions[action]
        return self.status

    def can(self, action: str) -> bool:
        return action in TRANSITIONS.get(self.status, {})

    @property
    def available_actions(self) -> list[str]:
        return list(TRANSITIONS.get(self.status, {}).keys())


# Usage:
class Order:
    def __init__(self):
        self.state = OrderStateMachine()

    def confirm(self):
        self.state.transition("confirm")
        self.send_confirmation_email()

    def cancel(self):
        self.state.transition("cancel")  # Raises if not allowed
        self.process_refund_if_paid()

    @property
    def status(self):
        return self.state.status.value

# Clear error messages:
order = Order()
order.confirm()   # pending → confirmed ✅
order.confirm()   # InvalidTransition: Cannot 'confirm' from 'confirmed'.
                  # Valid actions: ['start_processing', 'cancel']
```

## Why This Is Better

```
BEFORE (implicit):
  - Valid transitions scattered across 10 files
  - Missing a case = silent bug
  - Adding a status = hunting through all if/else blocks
  - Can't answer "what can I do from this state?" easily

AFTER (explicit):
  - ALL transitions visible in one dictionary
  - Missing a case = clear error message
  - Adding a status = add one entry to TRANSITIONS dict
  - available_actions tells you exactly what's valid

  Visual map (derivable from the TRANSITIONS dict):
  pending → confirmed → processing → shipped → delivered
    ↓          ↓            ↓           ↓          ↓
  cancelled  cancelled   cancelled   refunded   refunded
```

## Adding Side Effects (Hooks)

```python
# State machines often need actions on transitions:
HOOKS = {
    ("pending", "confirmed"): [send_confirmation_email, reserve_inventory],
    ("confirmed", "processing"): [notify_warehouse],
    ("processing", "shipped"): [send_tracking_email, update_inventory],
    ("shipped", "delivered"): [send_delivery_confirmation],
    ("*", "cancelled"): [process_refund, release_inventory, send_cancellation],
}

def transition(self, action):
    old = self.status
    new = TRANSITIONS[old][action]  # Raises if invalid

    # Run hooks for this specific transition
    key = (old.value, new.value)
    for hook in HOOKS.get(key, []):
        hook(self.order)

    # Run wildcard hooks
    for hook in HOOKS.get(("*", new.value), []):
        hook(self.order)

    self.status = new
```

The pattern: when you have more than 3-4 states with conditional transitions, extract an explicit state machine. Your transition rules become data instead of scattered code.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
