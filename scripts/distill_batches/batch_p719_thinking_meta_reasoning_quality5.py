"""Phase 3B: Metacognition — Reasoning Quality Evaluation (Part 5)
Scenarios: Two deployment, caching, monitoring, and architecture approaches
"""

PAIRS = [
    (
        "thinking/meta-reasoning-monolith-vs-microservices",
        r'''Our startup has 5 developers and is building an MVP for a food delivery app. Compare:

Monolith:
```
food-delivery-app/
├── users/        (auth, profiles)
├── restaurants/  (menus, hours)
├── orders/       (cart, checkout)
├── delivery/     (tracking, dispatch)
├── payments/     (Stripe integration)
└── notifications/ (push, email, SMS)
```

Microservices:
```
user-service/        (Node.js)
restaurant-service/  (Python)
order-service/       (Go)
delivery-service/    (Python)
payment-service/     (Node.js)
notification-service/ (Python)
api-gateway/         (Kong)
message-broker/      (RabbitMQ)
```

Which architecture for our MVP?''',
        r'''<think>
Let me evaluate for a 5-developer startup building an MVP.

**Monolith for MVP:**
Pros:
- One codebase: all developers share context
- One deployment: `git push` → CI → deploy
- One database: JOINs instead of API calls
- Simple debugging: single process, one debugger, one log file
- Fast iteration: change anything, deploy everything
- Low infrastructure: one server, one CI pipeline

Cons:
- Scaling: can only scale the whole app, not individual parts
- Tech lock-in: one language/framework for everything
- Long-term: may become "big ball of mud" without discipline

**Microservices for MVP:**
Pros:
- Independent scaling (if needed later)
- Technology diversity (if needed)
- Team independence (if teams exist)

Cons:
- 5 developers, 6 services + gateway + message broker = each developer owns 1.5 services
- 6 separate CI/CD pipelines to maintain
- 6 separate databases to manage
- Distributed debugging (tracing across 6 services)
- Network latency between services
- Data consistency (distributed transactions for orders)
- DevOps overhead: Kubernetes or Docker Compose for 8 containers

**For an MVP specifically:**
MVP = validate business idea quickly. Speed of development is the #1 priority.

A monolith lets you ship features in hours. Microservices require days of infrastructure work before writing business logic.

"We might need to scale" — you won't, not yet. If the MVP succeeds and gets 10,000 users, a well-structured monolith handles that easily. You can extract services later when you have evidence of which parts need independence.

**Winner:** Monolith, overwhelmingly. An MVP with 5 developers should maximize development speed and minimize infrastructure. Extract services later when (if) you hit specific scaling bottlenecks.
</think>

**Monolith, overwhelmingly. An MVP needs development speed, not distributed systems complexity.**

### Evaluation

| Axis | Monolith | Microservices |
|------|---------|---------------|
| Time to first feature | Hours | Days (infrastructure first) |
| Deployment complexity | `git push` → deploy | 6 CI/CD pipelines, K8s |
| Debugging | One log file, one debugger | Distributed tracing across 6 services |
| Team per service | N/A | 5 devs / 6 services = understaffed |
| Data consistency | Database transactions | Distributed sagas |
| Infrastructure cost | $20/month VPS | $200+/month (K8s cluster) |
| Development speed | Fast (function calls) | Slow (API calls, contracts) |

### The startup math
```
Monolith MVP:
  Week 1: Build core features
  Week 2: Build more features
  Week 3: Launch MVP
  Cost: $20/month hosting

Microservices MVP:
  Week 1: Set up K8s, CI/CD for 6 services, API gateway
  Week 2: Set up message broker, service discovery, distributed tracing
  Week 3: Start building features
  Week 6: Launch MVP
  Cost: $200/month hosting + 3 weeks of DevOps
```

### When to extract services (later, with evidence)
```
Signal: "Order processing is CPU-heavy and slows down the rest of the app"
→ Extract order-processing into a worker service

Signal: "The notification system needs different scaling (bursts of 100K push notifications)"
→ Extract notification service

Signal: "Team grew to 20, merge conflicts are constant"
→ Split into team-owned services around domain boundaries
```

### The reasoning pattern
Architecture should match team size and maturity. Startups with < 10 developers almost never benefit from microservices — the operational overhead exceeds the organizational benefits. Start with a well-structured monolith (clean module boundaries), and extract services only when you have concrete evidence of scaling or organizational bottlenecks.'''
    ),
    (
        "thinking/meta-reasoning-redis-vs-memcached",
        r'''For caching API responses in a web application, compare:

Redis:
```python
import redis
import json

r = redis.Redis(host='localhost', port=6379)

def get_cached(key, fetch_fn, ttl=300):
    cached = r.get(key)
    if cached:
        return json.loads(cached)
    data = fetch_fn()
    r.setex(key, ttl, json.dumps(data))
    return data
```

Memcached:
```python
import memcache
import json

mc = memcache.Client(['localhost:11211'])

def get_cached(key, fetch_fn, ttl=300):
    cached = mc.get(key)
    if cached:
        return json.loads(cached)
    data = fetch_fn()
    mc.set(key, json.dumps(data), time=ttl)
    return data
```

For pure API response caching, does it matter which I use?''',
        r'''<think>
For PURE caching of API responses, let me compare.

**Functionality for basic caching:**
Both work identically for simple get/set with TTL. The code above is functionally equivalent.

**Performance:**
- Memcached: slightly faster for simple get/set (optimized for exactly this)
- Redis: slightly slower for simple operations but negligible difference
- Both: sub-millisecond for most operations

**Memory efficiency:**
- Memcached: uses slab allocator, very memory-efficient for uniform-sized values
- Redis: uses more memory per key (metadata overhead)
- For caching: Memcached typically uses 10-30% less memory for the same data

**Multi-threading:**
- Memcached: multi-threaded, uses all CPU cores naturally
- Redis: single-threaded (one core). Redis 7.0+ has I/O threading but core processing is still single-threaded

**Data structures:**
- Memcached: only strings. get/set/delete.
- Redis: strings, lists, sets, sorted sets, hashes, streams, hyperloglogs, geospatial...
- For pure caching: you only need strings, so Memcached is sufficient

**Persistence:**
- Memcached: no persistence. Data lost on restart.
- Redis: optional persistence (RDB snapshots, AOF log)
- For caching: persistence doesn't matter (cache can be rebuilt)

**Features beyond caching:**
- Redis: pub/sub, Lua scripting, transactions, streams, rate limiting, session storage...
- Memcached: only caching

**The real question:**
If you ONLY need caching, Memcached is simpler and slightly more efficient. But most applications eventually need Redis for other things (sessions, rate limiting, queues). Running both Memcached AND Redis is more infrastructure than just using Redis for everything.

**Winner:** Redis, because you'll probably need it for other things eventually, and the performance difference for caching is negligible. But if you're at scale where memory efficiency matters (hundreds of GB of cache), Memcached might be worth it.
</think>

**For pure caching, both work equally well. Redis wins overall because you'll inevitably need its extra features.**

### Evaluation

| Axis | Redis | Memcached |
|------|-------|-----------|
| Basic caching (get/set/TTL) | ✓ | ✓ |
| Performance | Sub-ms | Sub-ms (marginally faster) |
| Memory efficiency | Good | Better (10-30% less overhead) |
| Multi-threading | Single-threaded | Multi-threaded |
| Data structures | Lists, sets, hashes, etc. | Strings only |
| Persistence | Optional | None |
| Pub/sub | ✓ | ✗ |
| Rate limiting | ✓ (native) | ✗ |
| Session storage | ✓ | ✓ (but no persistence) |
| Operational complexity | Low | Low |

### Why Redis wins in practice
```
Month 1: "We need caching" → Redis or Memcached (both fine)
Month 3: "We need rate limiting" → Redis INCR + EXPIRE
Month 5: "We need session storage" → Redis (persistent)
Month 8: "We need a job queue" → Redis Streams or lists

If you started with Memcached, you now run Memcached + Redis.
If you started with Redis, you just use Redis.
```

### When Memcached IS the right choice
- Massive cache (100GB+) where memory efficiency matters
- Simple caching only, no other use cases, ever
- High-throughput cache where multi-threading helps
- Already running Redis for other things — Memcached for dedicated caching tier

### The reasoning pattern
When two technologies are equivalent for the immediate need, choose the one that covers MORE future needs. Redis and Memcached are equal for caching, but Redis covers caching + sessions + rate limiting + queues + pub/sub. The marginal cost of choosing Redis over Memcached is near zero, but the marginal benefit of having Redis's extra features available is significant.'''
    ),
    (
        "thinking/meta-reasoning-docker-compose-vs-k8s",
        r'''For deploying a web app with a database and Redis cache, compare:

Docker Compose:
```yaml
services:
  web:
    build: .
    ports: ["8000:8000"]
    depends_on: [db, redis]
  db:
    image: postgres:16
    volumes: ["pgdata:/var/lib/postgresql/data"]
  redis:
    image: redis:7-alpine
volumes:
  pgdata:
```

Kubernetes:
```yaml
# deployment.yaml, service.yaml, ingress.yaml,
# configmap.yaml, secret.yaml, pvc.yaml
# for EACH of: web, postgres, redis
# Total: ~15 YAML files, ~500 lines
```

Which deployment platform?''',
        r'''<think>
Let me evaluate for a web app + database + Redis.

**Docker Compose:**
Pros:
- 15 lines of YAML
- `docker compose up` → everything running
- Simple to understand
- Works on a single server
- Easy local development
- Minimal learning curve

Cons:
- Single server (no horizontal scaling across machines)
- No auto-healing (container dies → manual restart, unless using `restart: always`)
- No rolling updates (stops old, starts new → brief downtime)
- No load balancing across multiple instances
- No auto-scaling based on load

**Kubernetes:**
Pros:
- Auto-healing: container crashes → auto-restart
- Rolling updates: zero-downtime deployments
- Horizontal scaling: more replicas on demand
- Load balancing: built-in service discovery
- Multi-server: spans multiple machines
- Auto-scaling: scale based on CPU/memory

Cons:
- ~500 lines of YAML for the same setup
- Requires K8s cluster (managed: $70+/month, self-hosted: nightmare)
- Steep learning curve (pods, deployments, services, ingress, PVCs, configmaps, secrets, RBAC...)
- Overkill for single-server deployment
- PostgreSQL on K8s is complex (stateful workloads need careful handling)

**The key question:** Do you need multi-server, auto-scaling, and zero-downtime deployments?

For most web apps:
- < 10,000 daily users: single server handles it
- Occasional deployments: 30 seconds of downtime is acceptable
- No auto-scaling needed: traffic is predictable

Kubernetes overhead is justified when:
- High availability is critical (SLA requirements)
- Traffic is unpredictable (auto-scaling needed)
- Multiple services that scale independently
- Team has K8s expertise

**Winner:** Docker Compose for most web apps. Kubernetes when you genuinely need its orchestration features. The ~90% of web apps that are served by a single server don't need Kubernetes.
</think>

**Docker Compose for most web apps. Kubernetes only when you genuinely need auto-scaling, auto-healing, and multi-server orchestration.**

### Evaluation

| Axis | Docker Compose | Kubernetes |
|------|---------------|------------|
| Setup complexity | 15 lines YAML | ~500 lines YAML |
| Learning curve | 1 hour | Weeks/months |
| Infrastructure cost | $20/month VPS | $70+/month managed K8s |
| Deployment | `docker compose up -d` | `kubectl apply -f .` (after cluster setup) |
| Auto-healing | `restart: always` (basic) | ✓ Full (reschedule on healthy node) |
| Rolling updates | Brief downtime | Zero-downtime |
| Auto-scaling | ✗ | ✓ (HPA) |
| Multi-server | ✗ | ✓ |
| Running DB on platform | ✓ (simple) | Complex (StatefulSets) |

### The complexity cost
```
Docker Compose knowledge needed:
  - docker-compose.yml format
  - Volume mounts
  - Networking basics

Kubernetes knowledge needed:
  - Pods, Deployments, ReplicaSets
  - Services, Ingress, IngressController
  - ConfigMaps, Secrets
  - PersistentVolumes, PersistentVolumeClaims
  - StatefulSets (for databases)
  - RBAC, ServiceAccounts
  - Helm charts
  - kubectl, kustomize
  - Monitoring (Prometheus), Logging (EFK)
  - Network policies
  ...
```

### When K8s is worth it
| Signal | Docker Compose | Kubernetes |
|--------|---------------|------------|
| < 10K users | ✓ | Overkill |
| 10K-100K users | Consider | ✓ |
| > 100K users | Insufficient | ✓ |
| Single service | ✓ | Overkill |
| 10+ microservices | Difficult | ✓ |
| SLA > 99.9% | Hard | ✓ |
| Unpredictable traffic | Can't auto-scale | ✓ |

### The reasoning pattern
Infrastructure complexity should match application requirements. Most web applications don't need Kubernetes — a single server with Docker Compose serves 10,000+ concurrent users. Don't pay the complexity cost of K8s until you have evidence that simpler solutions are insufficient.'''
    ),
    (
        "thinking/meta-reasoning-websocket-vs-sse",
        r'''For a live dashboard that shows real-time metrics updates, compare:

WebSocket:
```javascript
const ws = new WebSocket('wss://api.example.com/metrics');
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    updateDashboard(data);
};
ws.onclose = () => setTimeout(connect, 3000);
```

Server-Sent Events (SSE):
```javascript
const source = new EventSource('/api/metrics/stream');
source.onmessage = (event) => {
    const data = JSON.parse(event.data);
    updateDashboard(data);
};
// Auto-reconnects built into the spec!
```

Which is better for a metrics dashboard?''',
        r'''<think>
For a METRICS DASHBOARD that shows real-time updates.

Key characteristic: the data flows ONE WAY — server → client. The client displays data but doesn't send data back.

**WebSocket:**
Pros:
- Bidirectional: server → client AND client → server
- Binary data support
- Lower latency (persistent connection)
- Works with any data format

Cons:
- More complex: connection management, heartbeats, reconnection logic
- Manual reconnection: `ws.onclose = () => setTimeout(connect, 3000)`
- Doesn't work through some HTTP proxies without upgrade support
- Can't use standard HTTP features (cookies, auth headers) without custom logic
- Load balancer stickiness needed

**SSE:**
Pros:
- ONE-WAY (server → client): perfect for dashboard
- Auto-reconnection: built into the EventSource spec!
- Uses HTTP: works through proxies, firewalls, load balancers
- Standard HTTP auth: cookies and headers work normally
- Simple: minimal client code
- Event types: can send different named events
- Last-Event-ID: automatic resume from where disconnected

Cons:
- One-way only: can't send data from client to server
- Text only (no binary)
- Limited browser connection count per domain (~6 in HTTP/1.1, more in HTTP/2)
- No native support in some corporate environments

**For a metrics dashboard:**
- Data flows one way: server → client ✓ SSE is sufficient
- Auto-reconnection is critical for dashboards that run 24/7 ✓ SSE has this built-in
- Works through corporate proxies ✓ SSE is standard HTTP
- No need for client → server communication ✓ SSE is simpler

**Winner:** SSE. The dashboard only needs server → client data flow, which is exactly what SSE is designed for. WebSocket's bidirectionality is unnecessary complexity for this use case.
</think>

**SSE is better for a metrics dashboard — it's simpler, auto-reconnects, and the data flow is server → client only.**

### Evaluation

| Axis | WebSocket | SSE |
|------|----------|-----|
| Data direction | Bidirectional | Server → client only |
| Auto-reconnect | Manual (must implement) | Built into spec |
| Resume on disconnect | Manual (must implement) | `Last-Event-ID` header |
| HTTP compatibility | Needs upgrade | Standard HTTP |
| Proxy/firewall | May be blocked | Works through all |
| Auth (cookies) | Complex | Standard HTTP cookies |
| Client complexity | Higher | Lower |
| Binary data | ✓ | ✗ (text only) |

### SSE auto-reconnect vs WebSocket manual
```javascript
// SSE: automatic reconnection built into EventSource spec
const source = new EventSource('/api/metrics/stream');
// Disconnects → auto-reconnects with Last-Event-ID → resumes seamlessly

// WebSocket: must implement yourself
const ws = new WebSocket('wss://api.example.com/metrics');
ws.onclose = () => {
    setTimeout(() => {
        const newWs = new WebSocket('wss://api.example.com/metrics');
        // Must re-register all handlers
        // Must track last received event ID manually
        // Must handle exponential backoff
        // Must handle max retry limit
    }, 3000);
};
```

### When WebSocket IS better
| Scenario | SSE | WebSocket |
|----------|-----|-----------|
| Dashboard (server → client) | ✓ Best | Overkill |
| Chat (bidirectional) | ✗ | ✓ Best |
| Gaming (bidirectional, low latency) | ✗ | ✓ Best |
| Collaborative editing | ✗ | ✓ Best |
| Live notifications | ✓ Best | Works too |
| File upload progress | ✓ Best | Works too |
| Binary streaming | ✗ | ✓ Best |

### The reasoning pattern
Choose the simplest technology that meets the requirements. If data flows one way (server → client), SSE is simpler and more robust than WebSocket. Only use WebSocket when you need bidirectional communication. Unnecessary bidirectionality adds complexity (reconnection, heartbeats, state management) without benefit.'''
    ),
    (
        "thinking/meta-reasoning-spa-vs-ssr",
        r'''For a content-heavy blog with 500 articles, compare:

SPA (React):
```javascript
// Client-side rendered
function BlogPost({ slug }) {
    const [post, setPost] = useState(null);
    useEffect(() => {
        fetch(`/api/posts/${slug}`).then(r => r.json()).then(setPost);
    }, [slug]);
    if (!post) return <Loading />;
    return <Article post={post} />;
}
```

SSR (Next.js):
```javascript
// Server-side rendered
export async function getServerSideProps({ params }) {
    const post = await fetchPost(params.slug);
    return { props: { post } };
}

function BlogPost({ post }) {
    return <Article post={post} />;
}
```

Which rendering strategy for a blog?''',
        r'''<think>
For a CONTENT-HEAVY BLOG with 500 articles, the key considerations are SEO, performance, and content delivery.

**SPA (client-side rendering):**
1. SEO: Search engine crawlers see an empty `<div id="root"></div>`. Google's crawler can execute JS, but not all search engines do, and it's slower to index. For a blog that depends on organic search traffic, this is a serious problem.

2. First paint: user sees a loading spinner, then the API call, then content. Time to meaningful content is: download JS bundle + execute + API call + render.

3. Sharing: social media previews (Open Graph tags) need server-rendered HTML. SPA returns empty HTML → no preview card on Twitter/Facebook.

**SSR (server-side rendering with Next.js):**
1. SEO: Search engines get fully rendered HTML with all content, meta tags, and structured data. Instant indexing.

2. First paint: Server sends complete HTML. User sees content immediately. No loading spinner. JS hydrates in the background.

3. Sharing: Open Graph tags are in the HTML. Social media previews work perfectly.

4. Performance: For a blog, SSG (Static Site Generation) is even better — pre-render all 500 pages at build time. No server needed, CDN-hosted, sub-100ms response times.

**For a blog specifically:**
Blogs are content-first. The primary audience is organic search traffic. SEO is critical. Content doesn't change frequently (500 articles updated occasionally). This is the PERFECT use case for SSG (static site generation), not even SSR.

With Next.js ISR (Incremental Static Regeneration), you get:
- Pre-rendered HTML for all 500 pages
- CDN-fast response times
- SEO perfect
- Revalidation when content changes

**Winner:** SSR/SSG (Next.js). A blog is the canonical use case for server rendering. SPAs are for interactive applications, not content sites.
</think>

**SSR/SSG is dramatically better for a blog — SEO, social sharing, and first-paint performance all require server-rendered HTML.**

### Evaluation

| Axis | SPA (client-rendered) | SSR/SSG (Next.js) |
|------|----------------------|-------------------|
| SEO | Poor (empty HTML for crawlers) | Perfect (full HTML) |
| First meaningful paint | Slow (JS + API + render) | Instant (HTML ready) |
| Social sharing (OG tags) | ✗ (no HTML content) | ✓ (meta tags in HTML) |
| Core Web Vitals (LCP) | Poor | Excellent |
| Offline capability | With service worker | With service worker |
| Interactivity | Full (after JS loads) | Full (after hydration) |
| Build complexity | Simple | SSG needs build step |

### The SEO test
```html
<!-- SPA: what Google sees -->
<html>
  <body>
    <div id="root"></div>
    <script src="/bundle.js"></script>
  </body>
</html>
<!-- Content? What content? -->

<!-- SSR: what Google sees -->
<html>
  <head>
    <title>How to Build a REST API - My Blog</title>
    <meta name="description" content="Learn REST API design..." />
    <meta property="og:title" content="How to Build a REST API" />
  </head>
  <body>
    <article>
      <h1>How to Build a REST API</h1>
      <p>REST APIs are the backbone of modern web applications...</p>
    </article>
  </body>
</html>
<!-- Full content, metadata, everything -->
```

### Best approach for a blog: SSG (Static Site Generation)
```javascript
// Next.js: pre-render all 500 pages at build time
export async function getStaticPaths() {
    const posts = await getAllPosts();
    return { paths: posts.map(p => ({ params: { slug: p.slug } })), fallback: 'blocking' };
}

export async function getStaticProps({ params }) {
    const post = await getPost(params.slug);
    return { props: { post }, revalidate: 3600 }; // rebuild hourly
}
```

Results: 500 static HTML files, served from CDN, sub-50ms response time, perfect SEO.

### When SPA IS the right choice
| Content type | SPA | SSR/SSG |
|-------------|-----|---------|
| Blog / documentation | ✗ | ✓ |
| E-commerce product pages | ✗ | ✓ |
| Landing pages | ✗ | ✓ |
| Admin dashboard | ✓ | Overkill |
| Internal tools | ✓ | Overkill |
| Real-time apps (chat, games) | ✓ | Hybrid |

### The reasoning pattern
Rendering strategy should match content type and audience. Content consumed via search engines (blogs, docs, e-commerce) needs server rendering for SEO. Interactive tools used by authenticated users (dashboards, admin panels) can use client-side rendering because SEO doesn't matter.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
