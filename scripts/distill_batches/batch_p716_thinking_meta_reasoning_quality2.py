"""Phase 3B: Metacognition — Reasoning Quality Evaluation (Part 2)
Scenarios: API designs, deployment strategies, state management, clever vs obvious
"""

PAIRS = [
    (
        "thinking/meta-reasoning-rest-vs-graphql",
        r'''Our team is building a dashboard that displays data from multiple entities (users, orders, products, analytics). We're deciding between REST and GraphQL for our API:

REST:
```
GET /api/users/{id}
GET /api/users/{id}/orders
GET /api/orders/{id}
GET /api/products?category=electronics
GET /api/analytics/daily
```

GraphQL:
```graphql
query DashboardData {
  user(id: "123") {
    name
    orders(last: 5) {
      total
      status
      items { productName }
    }
  }
  products(category: "electronics", limit: 10) {
    name
    price
    stock
  }
  analytics {
    daily { revenue, visitors }
  }
}
```

Which is better for our dashboard?''',
        r'''<think>
Let me evaluate both for a dashboard specifically.

**Dashboard-specific considerations:**
A dashboard page needs data from MULTIPLE entities in ONE page load. This is the key factor.

**REST for the dashboard:**
```
Page load requires:
1. GET /api/users/123          → user info
2. GET /api/users/123/orders   → recent orders
3. GET /api/products?cat=elec  → product list
4. GET /api/analytics/daily    → analytics
= 4 HTTP requests (minimum)
```
- Over-fetching: each endpoint returns ALL fields, even if the dashboard only shows name and email
- Under-fetching: to get order items, need ANOTHER request per order (N+1)
- Multiple round trips: 4+ sequential or parallel requests per page load
- Simple caching: each endpoint can be cached independently

**GraphQL for the dashboard:**
```
Page load requires:
1. POST /graphql (single query above)
= 1 HTTP request
```
- Exact data: specify exactly which fields you need (no over/under-fetching)
- Single round trip: one request gets everything
- Complex caching: can't use simple HTTP cache (all requests go to same endpoint)
- N+1 on backend: resolvers can cause N+1 queries if not using DataLoader

**Developer experience:**
- REST: multiple endpoints, simple tooling, curl-friendly, easy caching
- GraphQL: schema-first, type-safe, introspection, playground, but steeper learning curve

**Backend complexity:**
- REST: simple to implement, well-understood patterns
- GraphQL: requires schema definition, resolvers, DataLoader for N+1, query complexity analysis to prevent abuse

**For a dashboard specifically:**
Dashboards are the BEST use case for GraphQL. They aggregate data from many entities, each needing specific fields. The "one request, exact data" model is perfect.

REST would work but requires:
- Either many round trips (N endpoints)
- Or custom "dashboard" endpoints that aggregate multiple resources (breaks REST principles)
- BFF (Backend for Frontend) pattern to reduce round trips

**Winner for dashboard:** GraphQL. But with caveats about backend complexity and the need for DataLoader.
</think>

**For a dashboard that aggregates multiple entities, GraphQL is the better choice — one request with exact data instead of 4+ REST round trips.**

### Evaluation

| Axis | REST | GraphQL |
|------|------|---------|
| Requests per page load | 4+ round trips | 1 request |
| Over-fetching | Returns all fields | Returns exactly requested fields |
| Under-fetching | N+1 for nested data | Nested queries in one request |
| Caching | Simple (HTTP cache per endpoint) | Complex (single endpoint) |
| Backend complexity | Simple controllers | Schema + resolvers + DataLoader |
| Learning curve | Low (familiar pattern) | Medium (new paradigm) |
| Type safety | Depends on docs | Built-in schema |
| Mobile bandwidth | Wasteful (over-fetching) | Efficient (exact data) |

### Why GraphQL wins for dashboards
```
REST dashboard page load:
  GET /users/123              → 50KB (need 2KB)
  GET /users/123/orders       → 100KB (need 5KB)
  GET /products?cat=elec      → 200KB (need 10KB)
  GET /analytics/daily        → 30KB (need 3KB)
  Total: 4 requests, 380KB transferred, 20KB actually used

GraphQL:
  POST /graphql               → 20KB (exactly what's needed)
  Total: 1 request, 20KB transferred
```

### When REST is still better
| Scenario | Winner |
|----------|--------|
| Dashboard (multi-entity) | GraphQL |
| Single-resource CRUD | REST (simpler) |
| Public API (third parties) | REST (more discoverable) |
| File upload/download | REST |
| Real-time data | Neither (use WebSocket) |
| Microservices internal | gRPC |
| Mobile app with varied views | GraphQL |

### The reasoning pattern
API design depends on access patterns. Dashboards have multi-entity, partial-field access patterns that match GraphQL perfectly. Simple CRUD with full-resource access patterns match REST better. Don't pick based on "modern vs traditional" — pick based on how clients actually consume data.'''
    ),
    (
        "thinking/meta-reasoning-blue-green-vs-canary",
        r'''Compare these two deployment strategies for our production web application:

Blue-Green Deployment:
- Maintain two identical environments (blue and green)
- Deploy new version to inactive environment
- Switch router to point to new environment
- Keep old environment as instant rollback

Canary Deployment:
- Deploy new version to small subset of servers (5%)
- Monitor error rates, latency, and business metrics
- Gradually increase traffic (5% → 25% → 50% → 100%)
- Roll back if any metric degrades

Which is better for a high-traffic e-commerce platform?''',
        r'''<think>
Let me evaluate both for a high-traffic e-commerce platform.

**Blue-Green:**
Pros:
- Instant rollback (just switch the router back)
- Full environment tested before any production traffic
- Simple mental model (either blue or green is live)
- Zero-downtime deployment
- Can run smoke tests on the inactive environment before switching

Cons:
- Requires 2x infrastructure (cost!)
- All-or-nothing: 100% of traffic switches at once
- If a bug only manifests under high load, you won't catch it until all traffic hits the new version
- Database migrations are complex (both environments share the same DB)

**Canary:**
Pros:
- Only a small percentage of users affected if there's a bug
- Real production traffic validates the new version
- Can detect load-related bugs that don't appear in staging
- No extra infrastructure needed (just route some traffic differently)
- Business metrics validation (conversion rate, revenue per user)

Cons:
- Slower rollout (takes time to gradually increase traffic)
- More complex routing logic
- Must handle running two versions simultaneously
- Database schema must be compatible with both versions
- Rollback is slower (must drain traffic and redirect)

**For a high-traffic e-commerce platform specifically:**
- High traffic means bugs affect many users quickly
- Revenue impact of bugs is significant
- Blue-green's all-or-nothing switch is risky — a subtle bug in the checkout flow could affect millions of transactions
- Canary's gradual rollout limits blast radius — 5% of traffic catches issues before they affect 100%
- E-commerce has clear business metrics to monitor (conversion rate, average order value, cart abandonment)

**Database considerations:**
Both have the database migration challenge. With canary, you MUST have backward-compatible schema changes (both versions run simultaneously). With blue-green, the switch is atomic but if you need to roll back, the database might have already been migrated.

**Winner for high-traffic e-commerce:** Canary deployment. The gradual rollout with real production traffic catches bugs that testing can't, and limits blast radius in a domain where bugs mean lost revenue.

BUT: blue-green is simpler and better for teams just starting with deployment automation.
</think>

**For a high-traffic e-commerce platform, canary deployment is better — it limits blast radius and validates with real production traffic.**

### Evaluation

| Axis | Blue-Green | Canary |
|------|-----------|--------|
| Blast radius | 100% users at once | 5% → 25% → 50% → 100% |
| Rollback speed | Instant (switch router) | Fast (redirect traffic) |
| Bug detection | Pre-deploy testing only | Real production traffic |
| Infrastructure cost | 2x (double environments) | Minimal (same servers) |
| Complexity | Simple (binary switch) | Complex (traffic splitting) |
| Load testing | Must simulate separately | Production load validates |
| Database migrations | Tricky (shared DB) | Must be backward-compatible |

### Why canary wins for e-commerce

```
Blue-green failure scenario:
1. Deploy v2 to green
2. Smoke tests pass (low traffic)
3. Switch 100% traffic to green
4. v2 has a subtle checkout bug under high concurrency
5. 100% of users affected immediately
6. Revenue loss while engineers diagnose and rollback

Canary failure scenario:
1. Deploy v2 to 5% of servers
2. Monitor: conversion rate drops 2% on canary servers
3. Automatic rollback triggers
4. Only 5% of users were briefly affected
5. Engineers investigate at leisure
```

### Canary metrics to watch for e-commerce
```python
canary_checks = {
    "error_rate": {"threshold": 0.01, "action": "rollback"},
    "p99_latency_ms": {"threshold": 500, "action": "pause"},
    "conversion_rate": {"threshold": -0.05, "action": "rollback"},  # 5% drop
    "cart_abandonment": {"threshold": 0.10, "action": "pause"},
    "revenue_per_user": {"threshold": -0.03, "action": "rollback"},
}
```

### When blue-green IS better
- Small team just starting with deployment automation (simpler)
- Low-traffic internal tools (blast radius is small anyway)
- Stateless applications with no database migrations
- When instant rollback is critical and canary is too slow

### The reasoning pattern
Deployment strategy depends on: traffic volume (higher = more risk from all-at-once), business impact of bugs (financial = use canary), team capability (small team = start with blue-green), and infrastructure budget (blue-green costs 2x). For high-stakes production systems, canary's gradual rollout with real traffic validation is safer than blue-green's binary switch.'''
    ),
    (
        "thinking/meta-reasoning-clever-vs-obvious",
        r'''Compare these two implementations of FizzBuzz:

Clever:
```python
def fizzbuzz_clever(n):
    return ['FizzBuzz'[i%3*4:i%5*8^12or 4:] or str(i) for i in range(1, n+1)]
```

Obvious:
```python
def fizzbuzz_obvious(n):
    results = []
    for i in range(1, n + 1):
        if i % 15 == 0:
            results.append("FizzBuzz")
        elif i % 3 == 0:
            results.append("Fizz")
        elif i % 5 == 0:
            results.append("Buzz")
        else:
            results.append(str(i))
    return results
```

Which is better?''',
        r'''<think>
Let me evaluate both.

**Correctness:**
Both produce the same output. The clever version uses bit manipulation and string slicing tricks to achieve the same result. Let me verify...

`'FizzBuzz'[i%3*4:i%5*8^12or 4:]`
- When i%3==0 and i%5==0: `'FizzBuzz'[0:8^12 or 4]` = `'FizzBuzz'[0:4]`... wait, I'm not sure this is even correct without tracing it carefully. That's already a problem.

Actually, let me not even try to verify it. The fact that verifying correctness requires careful bit-by-bit tracing IS the argument against it.

**Readability:**
- Clever: I cannot tell if it's correct by reading it. Requires mental simulation.
- Obvious: I can verify correctness in 5 seconds. Each branch is clear.

**Maintainability:**
- Clever: Adding "Jazz" for multiples of 7 requires completely rethinking the approach.
- Obvious: Adding "Jazz" = one more `elif i % 7 == 0` branch.

**Performance:**
- Both are O(n). The clever version might be slightly faster (list comprehension vs loop), but FizzBuzz performance is never a concern.

**Debugging:**
- Clever: If there's a bug for a specific number, where do you put a breakpoint? How do you inspect intermediate state?
- Obvious: Add a `print(i)` or breakpoint at any branch.

**Code review:**
- Clever: Every reviewer must spend time understanding it, and might not catch bugs.
- Obvious: Instantly reviewable.

**Winner:** Obvious, overwhelmingly. The clever version is a fun exercise but has no place in production code. Code is read far more than it's written — optimize for the reader.
</think>

**The obvious version is better by every measure except "how impressed will Reddit be?"**

### Evaluation

| Axis | Clever | Obvious |
|------|--------|---------|
| Correctness | Hard to verify (try reading it!) | Immediately verifiable |
| Readability | Requires mental simulation | Self-documenting |
| Maintainability | Add a rule = rewrite everything | Add a rule = one elif |
| Debugging | Where do you set a breakpoint? | Each branch is inspectable |
| Performance | Same O(n) | Same O(n) |
| Code review | Every reviewer wastes time parsing it | Instantly reviewable |
| Onboarding | New developer is confused | New developer understands instantly |

### The modification test
"Add 'Jazz' for multiples of 7, and 'FizzJazz' for multiples of 21."

```python
# Obvious: 30 seconds, zero risk
elif i % 21 == 0:
    results.append("FizzJazz")
elif i % 7 == 0:
    results.append("Jazz")

# Clever: complete rewrite needed.
# How do you fit a third word into the bit manipulation trick?
```

### When IS clever code justified?
| Scenario | Clever OK? |
|----------|-----------|
| Performance-critical inner loop | Yes (if measurably faster) |
| Code golf / puzzle | Yes (that's the point) |
| Interview showing off | No (shows poor judgment) |
| Production code | Almost never |
| Library internals with comments | Maybe (if well-documented) |

### The rule
```
If clever code is 10x faster → use it (with comments explaining why)
If clever code is same speed → use obvious version
If you can't tell if clever code is correct → definitely use obvious version
```

### The reasoning pattern
"Clever" code optimizes for the writer's satisfaction, not the reader's understanding. Code is read 10x more than it's written. When comparing approaches of equal correctness and performance, always choose the one that's easier to read, modify, and debug. Cleverness has a maintenance cost that compounds over time.'''
    ),
    (
        "thinking/meta-reasoning-library-vs-handrolled",
        r'''I need to validate user input in my Express.js API. Compare:

Hand-rolled:
```javascript
function validateCreateUser(req, res, next) {
    const { name, email, age } = req.body;

    if (!name || typeof name !== 'string' || name.length < 2 || name.length > 50) {
        return res.status(400).json({ error: 'Name must be 2-50 characters' });
    }
    if (!email || !email.match(/^[^\s@]+@[^\s@]+\.[^\s@]+$/)) {
        return res.status(400).json({ error: 'Invalid email format' });
    }
    if (age !== undefined && (typeof age !== 'number' || age < 0 || age > 150)) {
        return res.status(400).json({ error: 'Age must be 0-150' });
    }

    next();
}
```

Library (Joi):
```javascript
const Joi = require('joi');

const createUserSchema = Joi.object({
    name: Joi.string().min(2).max(50).required(),
    email: Joi.string().email().required(),
    age: Joi.number().integer().min(0).max(150).optional(),
});

function validateCreateUser(req, res, next) {
    const { error } = createUserSchema.validate(req.body);
    if (error) {
        return res.status(400).json({ error: error.details[0].message });
    }
    next();
}
```

Which approach is better?''',
        r'''<think>
Let me evaluate both.

**Correctness:**
- Hand-rolled: The email regex is basic — it allows `a@b.c` which might be technically valid but suspicious. It misses many edge cases (international domains, plus addressing, etc.).
- Joi: `Joi.string().email()` uses a well-tested email validation that handles edge cases correctly. Battle-tested by thousands of projects.

**Completeness:**
- Hand-rolled: Only validates name, email, and age. What about extra fields? If someone sends `{ name: "Alice", email: "...", isAdmin: true }`, the extra `isAdmin` is silently passed through.
- Joi: `Joi.object()` can be configured to strip unknown fields (`stripUnknown: true`) or reject them.

**Error messages:**
- Hand-rolled: Custom messages per field, but must be written manually for each validation.
- Joi: Auto-generates clear error messages, consistent format across all endpoints.

**Scalability:**
- Hand-rolled: With 20 endpoints, each with 5-10 fields, you write 100-200 validation rules manually. Each is a potential bug.
- Joi: Schemas are declarative, composable, and reusable. Define once, use across endpoints.

**Dependency cost:**
- Hand-rolled: No dependencies. No version updates, no security advisories for the library.
- Joi: 30KB dependency. Updates needed. But validation is complex enough that a library is warranted.

**Type coercion:**
- Hand-rolled: Must handle type coercion manually. What if `age` comes as string "25" from a form?
- Joi: Can auto-coerce types (`Joi.number()` converts "25" to 25).

**For this use case:**
Input validation is a solved problem with well-known edge cases (Unicode, email formats, number ranges). A library has already handled all these edge cases. Writing it by hand means rediscovering and solving each edge case yourself.

**Winner:** Joi (library). The dependency cost (one well-maintained package) is far less than the maintenance cost of hand-written validation across an entire API.
</think>

**The library (Joi) is better — input validation has too many edge cases to hand-roll reliably, and the dependency cost is low compared to the maintenance cost.**

### Evaluation

| Axis | Hand-rolled | Joi (library) |
|------|------------|---------------|
| Correctness | Basic (regex email validation) | Thorough (battle-tested patterns) |
| Edge cases | Must discover each one | Already handled |
| Code volume | 10-20 lines per endpoint | 3-5 lines per endpoint |
| Error messages | Manual per field | Auto-generated, consistent |
| Type coercion | Manual | Built-in (`"25"` → 25) |
| Extra field handling | Silent pass-through | Strip or reject unknown fields |
| Dependencies | Zero | One library (~30KB) |
| Scalability | O(n) effort per endpoint | Declarative schemas, composable |

### What hand-rolling misses
```javascript
// Hand-rolled allows:
validateCreateUser({
    name: "Alice",
    email: "alice@test.com",
    isAdmin: true,     // passes through! security risk!
    role: "superuser"  // passes through!
});

// Joi blocks:
createUserSchema.validate(body, { allowUnknown: false });
// → "\"isAdmin\" is not allowed"
```

### When to hand-roll
| Scenario | Hand-roll? |
|----------|-----------|
| 1-2 simple fields | Maybe (but library is still easier) |
| Complex validation across many endpoints | No — use a library |
| Zero-dependency requirement | Yes |
| Custom domain-specific validation | Both (library for structure, custom for business rules) |
| Performance-critical hot path | Profile first — libraries are usually fast enough |

### The decision framework
```
Library cost = dependency management + learning curve + bundle size
Hand-roll cost = implementation time + edge case discovery + maintenance

For validation: library cost ≪ hand-roll cost
For simple string formatting: hand-roll cost ≪ library cost
```

### The reasoning pattern
Prefer libraries when: (1) the problem is well-defined with known edge cases, (2) a well-maintained library exists, (3) the dependency cost is proportional to the problem complexity. Hand-roll when: (1) the problem is trivial, (2) no good library exists, (3) the dependency cost exceeds the problem complexity. Validation, date handling, and cryptography should almost always use libraries.'''
    ),
    (
        "thinking/meta-reasoning-two-state-management",
        r'''For a React e-commerce app with cart, user authentication, and product browsing, compare:

Approach A (Redux Toolkit):
```javascript
// store/cartSlice.js
const cartSlice = createSlice({
    name: 'cart',
    initialState: { items: [], total: 0 },
    reducers: {
        addItem(state, action) {
            state.items.push(action.payload);
            state.total += action.payload.price;
        },
        removeItem(state, action) {
            state.items = state.items.filter(i => i.id !== action.payload);
            state.total = state.items.reduce((sum, i) => sum + i.price, 0);
        }
    }
});

// Components access via useSelector/useDispatch
```

Approach B (React Context + useReducer):
```javascript
const CartContext = createContext();

function cartReducer(state, action) {
    switch (action.type) {
        case 'ADD_ITEM':
            return { ...state, items: [...state.items, action.payload] };
        case 'REMOVE_ITEM':
            return { ...state, items: state.items.filter(i => i.id !== action.payload) };
        default:
            return state;
    }
}

function CartProvider({ children }) {
    const [state, dispatch] = useReducer(cartReducer, { items: [] });
    return (
        <CartContext.Provider value={{ state, dispatch }}>
            {children}
        </CartContext.Provider>
    );
}
```

Which is better for this e-commerce app?''',
        r'''<think>
Let me evaluate both for an e-commerce app specifically.

**Approach A (Redux Toolkit):**
Pros:
- DevTools: Time-travel debugging, action log, state inspection
- Middleware: thunks for async operations (API calls for cart sync)
- Immer built-in: Can write "mutating" code that's actually immutable
- Ecosystem: RTK Query for API caching, Redux Persist for cart persistence
- Predictable: All state changes go through reducers, easy to trace
- Performance: connect/useSelector has built-in memoization

Cons:
- Boilerplate: slices, actions, selectors (though RTK reduces this)
- Learning curve: actions, reducers, selectors, middleware
- Bundle size: ~10KB for redux + RTK

**Approach B (React Context + useReducer):**
Pros:
- Built-in: No external dependencies
- Simple: Less boilerplate for small apps
- Familiar: Standard React patterns

Cons:
- Re-render performance: Context causes ALL consumers to re-render when ANY part of the state changes. In a cart context, changing the cart re-renders the header, sidebar, and every component that consumes CartContext — even if they only care about the user's name.
- No middleware: Async operations (sync cart to server, persist to localStorage) require custom solutions
- No DevTools: Debugging state changes is manual
- No built-in persistence: Must manually implement cart persistence
- Scaling: Multiple contexts for different concerns (auth, cart, UI) leads to provider hell

**For an e-commerce app specifically:**
E-commerce has complex state needs:
- Cart state must persist across page navigations
- Cart state may need to sync with server (for logged-in users)
- Multiple components read cart state (header badge, cart page, checkout)
- User auth state is needed everywhere
- Product state may be cached

Context's re-rendering issue is a real problem: every time an item is added to the cart, the entire app re-renders.

**Winner:** Redux Toolkit. The e-commerce use case has enough complexity (async sync, persistence, DevTools debugging, performance) to justify the additional dependency. Context is better for simple state like theme or locale.
</think>

**Redux Toolkit is better for an e-commerce app — the complexity of cart management (persistence, async sync, DevTools, performance) justifies the dependency.**

### Evaluation

| Axis | Redux Toolkit | Context + useReducer |
|------|-------------|---------------------|
| Re-render performance | Selective (useSelector) | ALL consumers re-render |
| DevTools | Time-travel debugging ✓ | None |
| Async operations | Thunks/sagas built-in | Must implement manually |
| Cart persistence | Redux Persist (one line) | Manual localStorage logic |
| Server sync | RTK Query | Custom fetch logic |
| Bundle size | ~10KB | 0KB (built-in) |
| Boilerplate | Medium (RTK reduces it) | Low |
| Learning curve | Medium | Low |

### The re-rendering problem with Context
```jsx
// Context: CartContext changes → EVERYTHING re-renders
<CartContext.Provider value={{ cart, user, ui }}>
  <Header />      // re-renders on cart change (only needs user)
  <ProductList />  // re-renders on cart change (doesn't need cart!)
  <CartSidebar />  // re-renders on cart change (correct)
</CartContext.Provider>

// Redux: only connected components re-render
const cartCount = useSelector(state => state.cart.items.length);
// Only re-renders if items.length actually changes
```

### When Context IS the right choice
| State type | Context | Redux |
|-----------|---------|-------|
| Theme (light/dark) | ✓ (rarely changes) | Overkill |
| Auth (logged in/out) | ✓ (rarely changes) | Fine either way |
| Locale (en/fr) | ✓ (rarely changes) | Overkill |
| Shopping cart | ✗ (changes often, many consumers) | ✓ |
| Form state | ✗ (use local state or React Hook Form) | ✗ |
| Server cache | ✗ | RTK Query or React Query |

### The reasoning pattern
State management choice depends on: frequency of updates (frequent = need selective re-rendering), number of consumers (many = Context causes performance issues), need for middleware (async, persistence, logging), and debugging requirements (DevTools). Context works for infrequent, simple state. Redux/Zustand/Jotai are better for frequent, complex state with many consumers.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
