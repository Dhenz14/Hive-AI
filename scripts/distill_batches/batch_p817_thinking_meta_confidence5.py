"""Phase 3C: Metacognition — Calibrating Confidence on Unfamiliar Frameworks (Part 5)

Training the model to recognize when it encounters frameworks or libraries
it has limited training data on, and to calibrate confidence accordingly.
"""

PAIRS = [
    (
        "thinking/meta-confidence-unfamiliar-framework-htmx",
        r'''I want to build a real-time dashboard using HTMX with SSE (Server-Sent Events). Should I use hx-sse or the new ext-sse extension? What are the performance implications for 1000+ concurrent connections?''',
        r'''<think>
Let me assess my confidence on this topic carefully.

What I know with HIGH confidence:
- HTMX is a library for building dynamic UIs with HTML attributes
- SSE is a standard browser API for server-to-client streaming
- 1000+ concurrent SSE connections is a meaningful server-side challenge
- SSE connections hold open HTTP connections, consuming server resources

What I know with MEDIUM confidence:
- HTMX had an hx-sse attribute that was deprecated in favor of an extension
- The ext-sse extension provides similar functionality with a cleaner API
- The migration happened around HTMX 1.x to 2.x transition

What I'm UNCERTAIN about:
- The exact current API surface of ext-sse in the latest HTMX version
- Specific performance benchmarks for HTMX SSE vs raw SSE
- Whether HTMX adds meaningful overhead on top of native EventSource
- The exact configuration options available in ext-sse

I should be transparent about my knowledge boundaries here. The HTMX ecosystem evolves quickly and my training data may not reflect the latest extension APIs. I can speak confidently about SSE architecture patterns but should caveat HTMX-specific implementation details.
</think>

**Honest confidence assessment:** I'm well-versed in SSE architecture patterns but my knowledge of HTMX's SSE extension specifics may be slightly outdated. Here's what I can tell you with varying confidence levels.

**HIGH confidence — SSE Architecture for 1000+ connections:**

The server-side challenge is real regardless of HTMX:
```
Each SSE connection = 1 persistent HTTP connection
1000 connections = 1000 open file descriptors + memory per connection
```

You need an async server (not thread-per-connection):
```python
# FastAPI/Starlette example — handles thousands of connections
from sse_starlette.sse import EventSourceResponse

async def dashboard_stream(request: Request):
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            data = await get_dashboard_metrics()
            yield {"event": "metrics", "data": json.dumps(data)}
            await asyncio.sleep(1)
    return EventSourceResponse(event_generator())
```

**MEDIUM confidence — HTMX SSE extension:**

The `hx-sse` attribute was deprecated. The extension-based approach is:
```html
<div hx-ext="sse" sse-connect="/dashboard/stream">
    <div sse-swap="metrics">
        <!-- replaced when "metrics" event arrives -->
    </div>
</div>
```

**I'd recommend verifying** the exact extension API against the current HTMX docs, as the extension interface has changed between versions.

**HIGH confidence — Performance recommendation:**

For 1000+ connections, focus on:
1. Use an async framework (FastAPI, Go, Node.js) — not Flask/Django sync
2. Put a reverse proxy (nginx) in front with connection pooling
3. Consider a fan-out service (Redis pub/sub) for distributing updates
4. Monitor with `ss -s` for connection counts

The HTMX client-side overhead is negligible — it's just wrapping native `EventSource`. The bottleneck is always server-side connection management.'''
    ),
    (
        "thinking/meta-confidence-unfamiliar-framework-solidjs",
        r'''How do I implement fine-grained reactivity in SolidJS compared to React? I want to update a single cell in a large table (10,000 rows) without re-rendering the entire component.''',
        r'''<think>
Let me calibrate my confidence on SolidJS vs React reactivity.

HIGH confidence areas:
- React's reconciliation model: virtual DOM diffing, re-renders from state changes
- React's performance patterns: React.memo, useMemo, useCallback, virtualization
- The conceptual difference: React re-renders components, Solid updates DOM directly
- SolidJS uses signals and fine-grained reactivity (similar to MobX/Vue internals)

MEDIUM confidence areas:
- SolidJS signal API: createSignal, createEffect, createMemo
- SolidJS store API for nested reactive objects
- How SolidJS <For> component works for list rendering
- The compilation model (Solid compiles JSX to direct DOM operations)

LOWER confidence areas:
- Exact performance benchmarks between Solid and React for this specific case
- Edge cases in SolidJS store reconciliation
- Whether SolidJS has changed its API surface significantly recently
- Advanced patterns like reconcile() and produce() utilities

I can speak authoritatively about the architectural differences and React side, and reasonably well about SolidJS core patterns. I should note where I'm extrapolating from architectural knowledge vs direct experience.
</think>

This is a great question that highlights fundamental architectural differences. I'm very confident about the React side and the conceptual model; my SolidJS specifics are solid but I'd recommend verifying exact API details against current docs.

**React approach (what you're fighting against):**

React re-renders the component when state changes, then diffs the virtual DOM:
```jsx
// Even with optimization, React must diff to know what changed
function Table({ data }) {
    // Changing one cell triggers this entire function
    return (
        <table>
            {data.map(row => (
                <MemoizedRow key={row.id} row={row} />
            ))}
        </table>
    );
}

// React.memo helps, but the parent still re-runs
const MemoizedRow = React.memo(({ row }) => (
    <tr>{row.cells.map(cell => <td key={cell.id}>{cell.value}</td>)}</tr>
));
```

For 10,000 rows, you'd also need virtualization (react-window/tanstack-virtual).

**SolidJS approach (fine-grained by default):**

SolidJS components run once. Only the specific DOM nodes that depend on changed signals update:
```jsx
import { createStore } from "solid-js/store";
import { For } from "solid-js";

function Table() {
    const [data, setData] = createStore(initialRows);

    function updateCell(rowIndex, cellIndex, value) {
        // Only the specific <td> that reads this path updates
        setData(rowIndex, "cells", cellIndex, "value", value);
    }

    return (
        <table>
            <For each={data}>
                {(row, rowIdx) => (
                    <tr>
                        <For each={row.cells}>
                            {(cell, cellIdx) => (
                                <td onClick={() =>
                                    updateCell(rowIdx(), cellIdx(), "new")
                                }>
                                    {cell.value}  {/* Only THIS td updates */}
                                </td>
                            )}
                        </For>
                    </tr>
                )}
            </For>
        </table>
    );
}
```

**Key architectural difference (HIGH confidence):**
| Aspect | React | SolidJS |
|--------|-------|---------|
| Update unit | Component function re-runs | Individual DOM node |
| Tracking | Explicit (memo, deps arrays) | Automatic (signal subscriptions) |
| 1 cell change in 10K rows | Parent re-renders + diff | Only that `<td>` updates |
| Virtualization needed? | Yes, for 10K rows | Often not, since no diffing cost |

**Caveat:** While SolidJS handles reactivity efficiently, 10,000 real DOM nodes still consume memory. For very large tables, even Solid benefits from virtualization for initial render performance.'''
    ),
    (
        "thinking/meta-confidence-unfamiliar-framework-temporal",
        r'''We're evaluating Temporal.io for our workflow orchestration. How does it handle the "exactly once" execution guarantee? Can activities fail and retry without duplicating side effects?''',
        r'''<think>
Let me carefully assess what I know about Temporal.io.

HIGH confidence:
- Temporal is a workflow orchestration platform (evolved from Uber's Cadence)
- It provides durable execution — workflows survive process crashes
- It separates workflow logic (deterministic) from activities (side effects)
- Activities can be retried automatically with configurable policies
- Workflow state is event-sourced — replayed from history on recovery

MEDIUM confidence:
- Temporal achieves "effectively once" execution of workflows through event sourcing
- Activities are "at least once" — they can be retried, so side effects may repeat
- Idempotency of activities is the developer's responsibility
- The workflow function itself must be deterministic (no random, no time, no I/O)
- Temporal uses a concept of "workflow task" for scheduling decisions

LOWER confidence:
- Exact SDK API details for the latest versions
- Specific cluster architecture and scaling characteristics
- How exactly the history pagination and continuation-as-new work at scale
- Performance characteristics under specific load patterns

I should be clear that "exactly once" is a nuanced claim in distributed systems and explain what Temporal actually guarantees vs what the developer must handle.
</think>

This is a nuanced distributed systems question. I have strong confidence in the architectural model but want to be precise about what "exactly once" actually means here.

**What Temporal actually guarantees (HIGH confidence):**

Temporal provides **effectively-once semantics for workflow logic**, not truly "exactly once" for activities. The distinction matters:

```
Workflow function: Executes deterministically, replayed from event history
                   → Guaranteed to reach the same decisions on replay
                   → "Effectively once" execution semantics

Activities:        Executed AT LEAST ONCE
                   → Can be retried on failure/timeout
                   → Side effects MAY duplicate
                   → YOU must make them idempotent
```

**How it works architecturally:**

```
1. Workflow code runs deterministically
2. When it calls an activity, Temporal records the INTENT in event history
3. Activity executes (makes API calls, writes DB, sends emails)
4. Result is recorded in event history
5. If workflow worker crashes and replays, it sees the recorded result
   → Does NOT re-execute the activity
6. If ACTIVITY worker crashes mid-execution (before recording result)
   → Activity IS retried → side effects may repeat
```

**Your responsibility — idempotent activities:**

```python
# BAD: Not idempotent — retry creates duplicate charge
@activity.defn
async def charge_customer(order_id: str, amount: float):
    await stripe.charges.create(amount=amount, customer=cust_id)

# GOOD: Idempotent — uses idempotency key
@activity.defn
async def charge_customer(order_id: str, amount: float):
    await stripe.charges.create(
        amount=amount,
        customer=cust_id,
        idempotency_key=f"order-{order_id}",  # Safe to retry
    )
```

**Common patterns for idempotency (HIGH confidence):**
1. **Idempotency keys** for payment APIs (Stripe supports this natively)
2. **Upsert instead of insert** for database writes
3. **Check-then-act** with unique constraints
4. **Deduplication tokens** for message queues

**What I'm less certain about:** The exact retry policy configuration syntax in the latest Temporal SDK versions. The conceptual model is stable, but verify the API:
```python
# Verify this against current SDK docs
@workflow.defn
class OrderWorkflow:
    @workflow.run
    async def run(self, order: Order):
        result = await workflow.execute_activity(
            charge_customer,
            args=[order.id, order.total],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
```

**Bottom line:** Temporal is excellent for workflow orchestration, but "exactly once" is marketing shorthand. Plan for idempotent activities from day one.'''
    ),
    (
        "thinking/meta-confidence-unfamiliar-framework-effect-ts",
        r'''I'm considering using Effect-TS for error handling in our TypeScript backend. How does it compare to fp-ts and is it production-ready? Our team has no FP experience.''',
        r'''<think>
Let me calibrate carefully on Effect-TS.

HIGH confidence:
- fp-ts is a well-established functional programming library for TypeScript
- Effect-TS (formerly @effect/io) is a newer, more ambitious project
- Both use algebraic data types for error handling (Either, Option, etc.)
- TypeScript's type system can express these patterns well
- Team FP experience is a critical adoption factor

MEDIUM confidence:
- Effect-TS provides a broader runtime system (not just data types)
- Effect-TS includes dependency injection, concurrency, streaming
- Effect-TS has been gaining traction and has corporate backing
- fp-ts is more "library," Effect-TS is more "framework/platform"
- Effect-TS has a steeper learning curve than fp-ts

LOWER confidence:
- Current production adoption numbers for Effect-TS
- The exact current API stability status
- How the 1.0/2.0 release changed the API surface
- Specific performance characteristics vs plain TypeScript
- Whether the Effect-TS ecosystem (HTTP, SQL, etc.) is mature enough

I should be honest that this is a rapidly evolving space and my knowledge of the latest Effect-TS release status may be outdated. The FP experience concern is something I can speak to confidently.
</think>

I want to be upfront about my confidence levels here. I know fp-ts well and understand Effect-TS architecturally, but the Effect-TS ecosystem is evolving rapidly and my knowledge of its latest release status may not be current.

**What I'm confident about — the core tradeoff:**

| Factor | fp-ts | Effect-TS |
|--------|-------|-----------|
| Scope | Library (data types) | Platform (runtime + ecosystem) |
| Learning curve | Steep | Steeper |
| Maturity | Stable, widely used | Newer, actively evolving |
| Bundle size | Pick what you need | Larger footprint |
| Team adoption risk | Moderate | Higher |

**For a team with no FP experience (HIGH confidence):**

This is the critical factor. Both libraries require understanding:
- Algebraic data types (Either, Option)
- Function composition and pipelines
- Effect systems and lazy evaluation
- Monadic chaining (flatMap/chain)

```typescript
// What your team sees today:
async function getUser(id: string): Promise<User> {
    const user = await db.findUser(id);
    if (!user) throw new NotFoundError("User not found");
    return user;
}

// What fp-ts looks like:
const getUser = (id: string): TaskEither<AppError, User> =>
    pipe(
        findUser(id),
        TE.fromOption(() => new NotFoundError("User not found"))
    );

// What Effect-TS looks like:
const getUser = (id: string): Effect<User, AppError, DbService> =>
    pipe(
        DbService,
        Effect.flatMap(db => db.findUser(id)),
        Effect.flatMap(Effect.fromOption(() => new NotFoundError()))
    );
```

**My honest recommendation (HIGH confidence on reasoning, MEDIUM on Effect-TS specifics):**

For a team with no FP experience, I would **not** recommend either library as a starting point. Instead:

1. **Start with TypeScript's built-in patterns:**
```typescript
// Result type — simple, no library needed
type Result<T, E = Error> = { ok: true; value: T } | { ok: false; error: E };

function getUser(id: string): Promise<Result<User, NotFoundError>> {
    const user = await db.findUser(id);
    if (!user) return { ok: false, error: new NotFoundError() };
    return { ok: true, value: user };
}
```

2. **If you outgrow that**, consider neverthrow (simpler Result type with chainable API)

3. **Only then** evaluate fp-ts or Effect-TS when the team is comfortable with the patterns

**What I'm uncertain about:** Effect-TS's current production-readiness status. It has been progressing rapidly and may have reached 1.0 stability. Check the official docs and GitHub for the current state before making a decision.'''
    ),
    (
        "thinking/meta-confidence-unfamiliar-framework-bun",
        r'''Should we migrate our Node.js Express API to Bun? We have 200+ Express routes, use TypeScript, and our main performance bottleneck is JSON serialization of large payloads.''',
        r'''<think>
Let me calibrate my confidence on Bun carefully.

HIGH confidence:
- Bun is a JavaScript/TypeScript runtime (alternative to Node.js)
- It includes a bundler, test runner, and package manager
- It's written in Zig and uses JavaScriptCore (not V8)
- Bun claims significantly faster startup and some runtime performance gains
- Express is a Node.js framework — compatibility with Bun varies
- JSON serialization performance depends on the JS engine internals

MEDIUM confidence:
- Bun has an Express-compatible HTTP server (Bun.serve)
- Bun's native APIs differ from Node.js (e.g., Bun.file vs fs)
- Many npm packages work with Bun but some don't (native addons especially)
- Bun's JSON.stringify performance may differ from V8's
- Express works on Bun but may not get Bun's full performance benefits

LOWER confidence:
- The current state of Bun's Node.js API compatibility (it's been improving)
- Whether Bun's performance advantage holds specifically for JSON serialization
- Production stability for large-scale deployments
- Specific incompatibilities with Express middleware ecosystem
- Current Bun version's maturity for production use

The JSON serialization bottleneck is interesting — the answer might not be "switch runtimes" but rather "use a faster serializer." I should present multiple options.
</think>

I want to separate what I'm confident about from where I'd be speculating.

**HIGH confidence — the JSON serialization bottleneck:**

Before migrating runtimes, this is likely solvable without changing anything else:

```typescript
// Option 1: fast-json-stringify (schema-based, 2-5x faster)
import fastJson from 'fast-json-stringify';

const stringify = fastJson({
    type: 'object',
    properties: {
        id: { type: 'integer' },
        name: { type: 'string' },
        items: {
            type: 'array',
            items: { type: 'object', properties: { /* ... */ } }
        }
    }
});

// Instead of JSON.stringify(payload)
const json = stringify(payload);  // 2-5x faster for known schemas

// Option 2: Streaming JSON for very large payloads
import { Readable } from 'stream';
app.get('/large-data', (req, res) => {
    res.setHeader('Content-Type', 'application/json');
    const stream = createJsonStream(largeDataset);  // Don't serialize all at once
    stream.pipe(res);
});

// Option 3: Pagination — don't send large payloads at all
// Often the real fix for "large JSON payload" problems
```

**MEDIUM confidence — Bun migration assessment:**

| Factor | Assessment | Confidence |
|--------|-----------|------------|
| Express compatibility | Works but may not leverage Bun.serve speed | Medium |
| npm ecosystem | Most packages work; native addons may not | Medium |
| TypeScript | Runs TS natively (no tsc step) | High |
| JSON.stringify speed | May be faster on JSC vs V8, but not guaranteed | Low |
| Production stability | Improving but less battle-tested than Node 20+ | Medium |

**What I'd recommend (HIGH confidence on approach):**

1. **Don't migrate for JSON performance** — use fast-json-stringify first. It's a 1-hour change, not a migration project.

2. **If you still want to evaluate Bun**, run a pilot:
```bash
# Test your existing Express app on Bun
bun run src/server.ts  # May just work

# Benchmark the specific bottleneck
# Compare: Node + JSON.stringify vs Node + fast-json-stringify vs Bun
```

3. **200+ routes is a significant migration risk.** Test for:
   - Native addon compatibility (bcrypt, sharp, etc.)
   - Stream handling differences
   - Middleware that relies on Node.js internals
   - Your test suite passing fully on Bun

**What I'm NOT confident about:** Whether Bun's current version (check bun.sh for latest) has resolved the Node.js compatibility gaps that existed earlier. The project moves fast. Run your test suite on Bun and see what breaks — that's more reliable than any prediction I can make.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
