"""Phase 4E: Self-Improvement — Autonomous Improvement (Part 2)"""

PAIRS = [
    (
        "thinking/auto-autonomous-fact-checking",
        r'''I'm about to explain microservices to a junior developer. Let me check my explanation for common misconceptions before I deliver it.

My draft explanation: "Microservices are when you split your application into small services that each have their own database. They communicate via REST APIs. Microservices are better than monoliths because they scale better and let teams work independently. You should use microservices for any new project."''',
        r'''<think>
Let me fact-check my own explanation sentence by sentence:

1. "Split your application into small services that each have their own database" — Partially correct. Each microservice OWNS its data, but not every service needs its own database server. Some share a database server with separate schemas. The key principle is data ownership, not physical separation.

2. "They communicate via REST APIs" — Misleading. REST is one option. Many microservice architectures use gRPC, message queues (Kafka, RabbitMQ), or event-driven communication. Presenting REST as the only method is a common misconception.

3. "Microservices are better than monoliths" — This is outright wrong as stated. It is a common misconception I am about to spread. Monoliths are simpler, easier to debug, and perfectly fine for many applications.

4. "You should use microservices for any new project" — Dangerously wrong. This contradicts the "monolith first" advice from Martin Fowler and others. Premature decomposition is a well-known antipattern.

I need to correct all four issues while keeping the explanation accessible for a junior developer.
</think>

I caught several misconceptions in my own draft. Here is the corrected explanation:

**Misconceptions I almost spread:**

| My Original Claim | The Reality |
|---|---|
| Each service has its own database | Each service *owns its data* — but may share a DB server with schema isolation |
| They communicate via REST APIs | REST, gRPC, message queues, and event streams are all common |
| Microservices are better than monoliths | Neither is universally better; each has tradeoffs |
| Use microservices for any new project | Start with a monolith unless you have strong reasons not to |

**Corrected explanation:**

Microservices are an architectural style where an application is composed of small, independently deployable services. Each service is responsible for one business capability and owns its own data — meaning no other service reads or writes that data directly.

Services communicate through well-defined interfaces. Common options include REST for synchronous request/response, gRPC for high-performance internal calls, and message brokers like Kafka for asynchronous event-driven communication. The choice depends on latency requirements and coupling tolerance.

**Tradeoffs versus monoliths:**

Microservices give you independent deployment, technology diversity, and targeted scaling. But they introduce network latency, distributed debugging complexity, data consistency challenges, and operational overhead (you need service discovery, circuit breakers, distributed tracing).

**When to choose microservices:**
- Large team (50+ developers) where a monolith creates merge conflicts and deployment bottlenecks
- Parts of the system have drastically different scaling needs
- You need to deploy components independently on different schedules

**When to stay with a monolith:**
- Small team, early-stage product
- You are still discovering your domain boundaries
- You do not have the infrastructure maturity for distributed systems

The widely cited advice from Martin Fowler is "monolith first" — build a well-structured monolith, identify natural boundaries, then extract services only when the benefits justify the complexity.

By catching these misconceptions before delivering the explanation, I avoided reinforcing the harmful myth that microservices are always the right choice.'''
    ),
    (
        "thinking/auto-autonomous-deployment-verification",
        r'''I wrote a deployment guide for a Node.js app on an Ubuntu server:

1. SSH into the server
2. git pull origin main
3. npm install
4. npm run build
5. pm2 restart app

Let me verify each step actually works in practice before presenting this.''',
        r'''<think>
Let me walk through each step as if I were actually executing it on a fresh deployment:

Step 1: "SSH into the server" — Which user? What if SSH key authentication fails? No mention of the server address or how to obtain credentials.

Step 2: "git pull origin main" — Assumes the repo is already cloned, the remote is named "origin", and the branch is "main". What if there are local changes that cause merge conflicts? What if the working directory is not set?

Step 3: "npm install" — What Node.js version? If the server has Node 16 and the app requires Node 20, this silently installs wrong native modules. No `--production` flag, so devDependencies get installed too. No `npm ci` for reproducible installs.

Step 4: "npm run build" — What if the build fails? There is no error check. The old build artifacts might still be served.

Step 5: "pm2 restart app" — Assumes pm2 is installed and the app is already registered. A restart with no health check means if the new version crashes on startup, the service is down.

This guide would fail on a fresh server and has no error handling for an existing server. Let me fix it.
</think>

My deployment guide had critical gaps. Every step had at least one assumption that would break in practice. Here is the corrected version:

**Before (my original):** 5 bare commands with no error handling, no version pinning, no rollback.

**After (autonomously verified):**
```bash
#!/bin/bash
set -euo pipefail  # Exit on any error

APP_DIR="/var/www/myapp"
NODE_VERSION="20"
APP_NAME="myapp"

echo "=== Step 1: Verify environment ==="
node_major=$(node -v | cut -d. -f1 | tr -d 'v')
if [ "$node_major" -ne "$NODE_VERSION" ]; then
  echo "ERROR: Need Node $NODE_VERSION, found $(node -v)"
  exit 1
fi

echo "=== Step 2: Pull latest code ==="
cd "$APP_DIR"
git stash  # Save any local changes (e.g., .env edits)
git fetch origin main
PREV_COMMIT=$(git rev-parse HEAD)
git reset --hard origin/main
git stash pop || true  # Restore local changes if any

echo "=== Step 3: Install dependencies ==="
npm ci --production  # Clean install from lockfile, no devDependencies

echo "=== Step 4: Build with validation ==="
npm run build
if [ ! -d "dist" ]; then
  echo "ERROR: Build produced no dist/ directory"
  git checkout "$PREV_COMMIT"
  exit 1
fi

echo "=== Step 5: Restart with health check ==="
pm2 restart "$APP_NAME" --update-env
sleep 5
if ! pm2 show "$APP_NAME" | grep -q "online"; then
  echo "ERROR: App failed to start. Rolling back..."
  git checkout "$PREV_COMMIT"
  npm ci --production
  npm run build
  pm2 restart "$APP_NAME"
  exit 1
fi

echo "=== Deployed $(git rev-parse --short HEAD) ==="
```

**Issues I caught and fixed:**

| Problem | Original | Fixed |
|---|---|---|
| No working directory | Implicit | Explicit `cd $APP_DIR` |
| No Node version check | None | Validates major version before proceeding |
| `npm install` is non-deterministic | `npm install` | `npm ci --production` uses lockfile exactly |
| No build validation | None | Checks that `dist/` directory exists |
| No rollback on failure | None | Reverts to previous commit if app fails to start |
| No health check | Blind restart | Waits 5 seconds, checks pm2 status |
| No error propagation | None | `set -euo pipefail` stops on first error |

The original 5-step guide would silently deploy a broken build. The improved script fails loudly and rolls back automatically.'''
    ),
    (
        "thinking/auto-autonomous-devils-advocate",
        r'''I recommended the following tech stack for a new SaaS startup:
- Frontend: React + TypeScript
- Backend: Node.js + Express
- Database: MongoDB
- Hosting: AWS
- Auth: Firebase Auth

Let me challenge my own recommendation before presenting it.''',
        r'''<think>
Let me play devil's advocate against each of my own choices:

1. React + TypeScript — This is defensible. Large ecosystem, easy to hire for. But: is this a content-heavy site? If so, Next.js or even a server-rendered framework would give better SEO and initial load. I defaulted to React without asking about the product.

2. Node.js + Express — Express is essentially unmaintained (last major release years ago). Fastify is faster and actively maintained. More importantly: is JavaScript the right backend choice? If the product involves heavy computation, Python or Go would be better. I chose Node just because the frontend is JS.

3. MongoDB — This is the choice I am most worried about. SaaS products almost always have relational data: users, subscriptions, invoices, permissions. MongoDB was trendy in 2015 but a relational database (PostgreSQL) would be objectively better for structured business data. I fell into the "MongoDB is modern" trap.

4. AWS — Defensible for scale, but a startup might be better served by a simpler PaaS like Railway, Render, or Fly.io to avoid DevOps overhead. AWS has a steep learning curve and surprise billing.

5. Firebase Auth — Vendor lock-in risk. If they later want to self-host or switch clouds, migrating auth is painful. Auth0 or a self-hosted solution like Supabase Auth gives more flexibility.

My recommendation was "safe defaults" rather than actually thinking about this startup's needs.
</think>

I challenged every one of my own choices and found problems with three of them. Here is my revised recommendation:

**Challenges to my original stack:**

| My Choice | Challenge | Verdict |
|---|---|---|
| React + TS | Fine for a SaaS dashboard, but should be Next.js for SSR/SEO | **Changed** |
| Node + Express | Express is stagnant; chose it just because frontend is JS | **Changed** |
| MongoDB | SaaS data is relational: users, subscriptions, billing | **Changed** |
| AWS | Overkill for a startup; high DevOps overhead | **Changed** |
| Firebase Auth | Vendor lock-in risk for a critical system | **Changed** |

**Revised recommendation:**

- **Frontend:** Next.js + TypeScript — gives React's ecosystem plus SSR, API routes, and simpler deployment. A SaaS product needs landing pages (SEO) and a dashboard (interactivity); Next.js handles both.
- **Backend:** Next.js API routes + tRPC for type-safe internal calls. If a separate backend is needed later, extract to Fastify (actively maintained, 2x faster than Express).
- **Database:** PostgreSQL on Supabase — relational data model fits SaaS perfectly. Row-level security for multi-tenant isolation. Supabase gives you a managed Postgres with built-in auth and real-time subscriptions.
- **Hosting:** Vercel for the Next.js app, Supabase for database and auth. Total managed infrastructure with generous free tiers. Migrate to AWS only when you outgrow it.
- **Auth:** Supabase Auth — open-source, self-hostable, no vendor lock-in, integrates natively with the database's row-level security.

**Why the original was wrong:**

I was recommending "popular defaults" instead of reasoning about the specific use case. A SaaS startup needs: fast time-to-market, low DevOps burden, relational data modeling, and an easy path to scale later. My revised stack optimizes for all four. The original stack would have required a dedicated DevOps engineer and would have fought MongoDB's document model for every business query involving joins.

This is what autonomous devil's-advocate review looks like: I challenged every choice, found that 5 out of 5 had better alternatives for this specific context, and revised accordingly.'''
    ),
    (
        "thinking/auto-autonomous-perspective-shift",
        r'''I wrote this REST API design for a task management app:

POST   /api/tasks          — create task
GET    /api/tasks           — list all tasks
GET    /api/tasks/:id       — get task
PUT    /api/tasks/:id       — update task
DELETE /api/tasks/:id       — delete task
POST   /api/tasks/:id/assign — assign task to user
POST   /api/tasks/:id/status — change task status

Let me review this as if I were a frontend developer consuming this API.''',
        r'''<think>
Let me put on my "frontend developer" hat and try to build a UI against this API:

Scenario 1: Dashboard — I need tasks for the current user, filtered by status, sorted by due date.
- The API gives me GET /api/tasks which returns ALL tasks. I would need to filter client-side? That is terrible for performance. There are no query parameters for filtering.

Scenario 2: Kanban board — I need tasks grouped by status.
- Same problem. I have to fetch all tasks, then group them myself. The API should support ?status=in_progress.

Scenario 3: Assigning a task — POST /api/tasks/:id/assign
- What is the request body? Just a user_id? What if I want to assign multiple users? The endpoint name does not make this clear.

Scenario 4: Task detail page — I need the task plus the assignee's name and the project name.
- GET /api/tasks/:id probably returns user_id and project_id. Now I need two more API calls to get the user and project names. No way to expand related resources.

Scenario 5: Pagination — The task list could have thousands of items.
- No pagination parameters. GET /api/tasks returns everything.

Scenario 6: Bulk operations — User selects 10 tasks and marks them all "done."
- I have to make 10 separate POST /api/tasks/:id/status calls. No batch endpoint.

This API is designed from the server's perspective, not the consumer's.
</think>

Reviewing my API as a frontend consumer revealed six usability problems. Here is the redesign:

**Problems found during perspective shift:**

1. **No filtering** — `GET /api/tasks` returns everything; frontend cannot request "my tasks" or "open tasks"
2. **No pagination** — unbounded response for large task lists
3. **No resource expansion** — task detail returns IDs, forcing extra calls for names
4. **Unclear assignment model** — single or multiple assignees?
5. **No bulk operations** — common UI pattern (select-all, mark done) requires N requests
6. **Status change is a POST** — should be a PATCH on the task resource

**Redesigned API (consumer-first):**

```
# Core CRUD
POST   /api/tasks                    — create task
GET    /api/tasks?status=open&assignee=me&sort=due_date&page=1&limit=20
GET    /api/tasks/:id?expand=assignees,project
PATCH  /api/tasks/:id                — partial update (status, title, etc.)
DELETE /api/tasks/:id

# Bulk operations
PATCH  /api/tasks/bulk               — update multiple tasks at once
DELETE /api/tasks/bulk               — delete multiple tasks at once

# Assignees (sub-resource, supports multiple)
PUT    /api/tasks/:id/assignees      — replace assignee list
POST   /api/tasks/:id/assignees      — add an assignee
DELETE /api/tasks/:id/assignees/:uid — remove an assignee
```

**Key changes explained for the frontend developer:**

```
# Before: fetch all tasks, filter client-side
GET /api/tasks

# After: server filters, paginates, and expands
GET /api/tasks?status=open&assignee=me&sort=-due_date&page=1&limit=20&expand=assignees

# Response includes pagination metadata:
{
  "data": [...],
  "meta": { "page": 1, "limit": 20, "total": 147 }
}
```

```
# Before: 10 requests to mark 10 tasks done
POST /api/tasks/1/status  { "status": "done" }
POST /api/tasks/2/status  { "status": "done" }
...

# After: 1 request
PATCH /api/tasks/bulk
{ "ids": [1, 2, 3, ...], "changes": { "status": "done" } }
```

By reviewing from the consumer's perspective, I found that my original design would have required the frontend to make excessive API calls, implement client-side filtering, and build workarounds for missing batch operations. The redesign cuts typical page-load API calls from 5-10 down to 1-2.'''
    ),
    (
        "thinking/auto-autonomous-claim-verification",
        r'''I gave this performance advice to a developer:

"Use a hash map instead of a list for lookups — it's O(1) instead of O(n). Also, sort the list first and use binary search if you need ordering, that's O(log n). And caching is always faster than recomputing."

Let me verify my claims with actual complexity analysis before the developer acts on them.''',
        r'''<think>
Let me verify each claim rigorously:

Claim 1: "Hash map lookups are O(1) instead of O(n)"
- Average case: O(1) — correct.
- Worst case: O(n) with hash collisions. I should mention this.
- Also: O(1) is amortized. Resizing the hash map is O(n).
- For small collections (< ~50 elements), linear scan can be faster due to cache locality. A list fits in L1 cache; a hash map has pointer indirection.
- Verdict: Partially correct. I oversimplified.

Claim 2: "Sort first and use binary search — O(log n)"
- Binary search is O(log n) per query — correct.
- But sorting is O(n log n). If you only search once, sort + binary search is O(n log n) which is WORSE than linear scan O(n).
- This advice is only correct if you search many times after one sort.
- Verdict: Conditionally correct. I omitted the critical condition.

Claim 3: "Caching is always faster than recomputing"
- "Always" is wrong. Cache has overhead: memory allocation, key hashing, cache invalidation logic.
- If the computation is cheap (e.g., adding two numbers), caching is slower due to overhead.
- If the cache hit rate is low, you pay the cache overhead AND still recompute most of the time.
- Cache invalidation bugs can cause correctness issues, which is worse than being slow.
- Verdict: Wrong as stated. Should be "caching is faster when computation is expensive AND the hit rate is high."
</think>

I verified my three claims and found that all three were oversimplified or incorrect. Here are the corrections:

**Claim 1: "Hash map is O(1) vs list O(n)"**

Partially correct. The full picture:

| Scenario | Hash Map | List (scan) |
|---|---|---|
| Average lookup | O(1) amortized | O(n) |
| Worst case (collisions) | O(n) | O(n) |
| Small collection (< 50) | Slower (pointer chasing, hashing overhead) | Faster (L1 cache-friendly) |
| Memory | Higher (pointers, load factor ~0.75) | Lower (contiguous) |

**Corrected advice:** Use a hash map when the collection has more than ~50 elements and you need frequent lookups. For small collections, a linear scan over a list is often faster due to CPU cache effects.

**Claim 2: "Sort + binary search is O(log n)"**

Conditionally correct. I omitted the sort cost:

```
One-time search:    linear scan = O(n)
                    sort + search = O(n log n) + O(log n) = O(n log n)  ← WORSE

k searches:         linear scans = O(k * n)
                    sort once + k searches = O(n log n) + O(k * log n)
                    Break-even when k > log n
```

**Corrected advice:** Sort + binary search is only faster when you perform multiple searches on the same data. For a single lookup, linear scan is better. The break-even point is roughly `k > log(n)` searches.

**Claim 3: "Caching is always faster than recomputing"**

Wrong. Counterexamples:

1. **Cheap computation:** Caching `a + b` is slower than just computing it — hashing the key costs more than the addition.
2. **Low hit rate:** If 90% of accesses are cache misses, you pay the cache overhead AND recompute anyway.
3. **Memory pressure:** A large cache evicts other useful data from CPU cache, slowing down unrelated code.

**Corrected advice:** Caching is faster when (a) the computation is expensive relative to the cache lookup, (b) the same inputs recur frequently (high hit rate), and (c) you have memory budget. Profile before and after adding a cache.

**Summary:** Two of my three claims needed significant qualification, and one was wrong. Performance advice without nuance can lead developers to make their code slower, not faster. I should always include the conditions under which advice applies.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
