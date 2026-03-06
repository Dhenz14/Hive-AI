"""Phase 3C: Metacognition — Confidence Calibration with Version-Specific Knowledge (Part 9)

Training the model to recognize when its knowledge may be outdated for
version-specific features, APIs, or configurations, and to flag this
uncertainty appropriately.
"""

PAIRS = [
    (
        "thinking/meta-confidence-version-specific-react",
        r'''How do I fetch data in React? I'm using React 19. Should I use useEffect or is there a better way now?''',
        r'''<think>
Let me carefully calibrate what I know about React data fetching across versions.

HIGH confidence (established patterns):
- useEffect + useState for data fetching (React 16.8+)
- React Query / TanStack Query as a popular library solution
- SWR as another popular data fetching library
- These patterns have been stable for years

MEDIUM confidence (React 18):
- Suspense for data fetching was partially available in React 18
- React 18 introduced useTransition and startTransition
- Server components were introduced experimentally

LOWER confidence (React 19 specifically):
- React 19 may have changed the recommended data fetching patterns
- The "use" hook was proposed for React 19
- Server components may be more mature in React 19
- The Actions API was proposed for React 19
- I'm not fully certain about the final API surface that shipped

I should be transparent that my React 19 knowledge may not reflect the final shipped version and recommend checking the official docs.
</think>

I want to be upfront about my confidence levels here, because React's data fetching story has been evolving rapidly.

**What I'm confident about (works in all recent React versions):**

```jsx
// Pattern 1: useEffect + useState (React 16.8+, still works in 19)
function ProductList() {
    const [products, setProducts] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetch('/api/products')
            .then(res => res.json())
            .then(data => {
                setProducts(data);
                setLoading(false);
            });
    }, []);

    if (loading) return <div>Loading...</div>;
    return <ul>{products.map(p => <li key={p.id}>{p.name}</li>)}</ul>;
}
```

This works. It's verbose, doesn't handle race conditions, and requires manual loading/error states — but it's reliable and well-documented.

**Pattern 2: TanStack Query (HIGH confidence, version-independent):**
```jsx
import { useQuery } from '@tanstack/react-query';

function ProductList() {
    const { data, isLoading, error } = useQuery({
        queryKey: ['products'],
        queryFn: () => fetch('/api/products').then(r => r.json()),
    });

    if (isLoading) return <div>Loading...</div>;
    if (error) return <div>Error: {error.message}</div>;
    return <ul>{data.map(p => <li key={p.id}>{p.name}</li>)}</ul>;
}
```

This handles caching, deduplication, refetching, and race conditions. Works with any React version.

**What I'm LESS certain about (React 19 specifics):**

React 19 was expected to introduce:
- The `use` hook for reading promises and context
- Enhanced Suspense for data fetching
- Server Components as a first-class feature
- The Actions API for mutations

```jsx
// This pattern MAY work in React 19 — verify against current docs:
import { use, Suspense } from 'react';

function ProductList({ productsPromise }) {
    const products = use(productsPromise);  // "use" hook
    return <ul>{products.map(p => <li key={p.id}>{p.name}</li>)}</ul>;
}

// Usage with Suspense:
<Suspense fallback={<div>Loading...</div>}>
    <ProductList productsPromise={fetchProducts()} />
</Suspense>
```

**I'm flagging this as uncertain because:**
- React 19's API may have changed between proposals and final release
- The exact `use` hook semantics may differ from what I've seen
- Server Components integration may have different patterns in your framework (Next.js vs Remix vs plain React)

**My recommendation:**

1. **Right now, reliably:** Use TanStack Query or SWR — they work in React 19 and handle all the complexity
2. **For React 19 features:** Check react.dev for the current documentation on `use` and Suspense patterns
3. **If using Next.js/Remix:** These frameworks have their own data fetching patterns that may be preferred over manual fetching

Don't use `useEffect` for data fetching in new code — it's the most error-prone approach. Whether you use a library or React 19's native features, both are better.'''
    ),
    (
        "thinking/meta-confidence-version-specific-python",
        r'''What's the best way to handle type hints in Python? I'm on Python 3.12 and want to use the latest features.''',
        r'''<think>
Python typing has evolved significantly across versions. Let me calibrate.

HIGH confidence (Python 3.9-3.10):
- Built-in generics: list[int] instead of List[int] (3.9+)
- Union syntax: X | Y instead of Union[X, Y] (3.10+)
- TypeGuard for type narrowing (3.10+)
- ParamSpec for decorator typing (3.10+)

MEDIUM-HIGH confidence (Python 3.11):
- Self type for methods returning self
- TypeVarTuple for variadic generics
- LiteralString for SQL injection prevention typing
- StrEnum

MEDIUM confidence (Python 3.12):
- type statement for type aliases (type Point = tuple[int, int])
- Improved TypeVar syntax (generic functions with [T] syntax)
- @override decorator from typing
- These were PEP 695 and PEP 698

LOWER confidence:
- Exact details of the PEP 695 syntax in 3.12
- Whether some of these features have been refined since initial release
- Interaction between 3.12 features and mypy/pyright current versions

I should present what I'm confident about and flag the 3.12-specific features as "verify the exact syntax."
</think>

Python's typing story has improved dramatically. Let me organize by confidence level, since some features are newer and my knowledge of exact syntax details may not be current.

**HIGH confidence — use these now (Python 3.10+):**

```python
# Modern union syntax (3.10+)
def process(value: int | str | None) -> str:
    ...

# Built-in generics (3.9+, no need for typing imports)
def first(items: list[int]) -> int | None:
    return items[0] if items else None

# Dict, tuple, set are also generic
config: dict[str, list[int]] = {"sizes": [1, 2, 3]}

# Type narrowing with isinstance works well with modern type checkers
def handle(x: int | str) -> None:
    if isinstance(x, int):
        print(x + 1)      # Type checker knows x is int here
    else:
        print(x.upper())  # Type checker knows x is str here
```

**MEDIUM-HIGH confidence — Python 3.11 features:**

```python
from typing import Self

class Builder:
    def set_name(self, name: str) -> Self:  # Returns the actual subclass type
        self.name = name
        return self

from typing import LiteralString

def execute_sql(query: LiteralString) -> None:
    # Type checker warns if query is built from user input
    ...

execute_sql("SELECT * FROM users")           # OK
execute_sql(f"SELECT * FROM {user_input}")    # Type checker warns!
```

**MEDIUM confidence — Python 3.12 features (verify syntax):**

Python 3.12 introduced a new syntax for generics and type aliases. My understanding:

```python
# New type alias syntax (PEP 695)
type Point = tuple[int, int]
type Matrix[T] = list[list[T]]

# New generic function syntax
def first[T](items: list[T]) -> T | None:  # T is declared inline
    return items[0] if items else None

# New generic class syntax
class Stack[T]:
    def __init__(self) -> None:
        self._items: list[T] = []

    def push(self, item: T) -> None:
        self._items.append(item)

    def pop(self) -> T:
        return self._items.pop()

# @override decorator (PEP 698)
from typing import override

class Child(Parent):
    @override
    def process(self) -> None:  # Type checker ensures Parent has this method
        ...
```

**I'd recommend verifying** the exact PEP 695 syntax against the Python 3.12 docs, as the generic syntax was a significant change and I want to make sure the details are exactly right.

**Practical recommendations (HIGH confidence):**

1. **Use a type checker:** mypy or pyright — type hints without a checker are just comments
2. **Start simple:** `int | str | None`, `list[int]`, `dict[str, Any]`
3. **Use `from __future__ import annotations`** if you need to support Python 3.9
4. **Don't over-type:** Start with function signatures, skip internal variables (they're inferred)
5. **Gradual typing is fine:** You don't need 100% coverage. Type the public API first.

```python
# Good starting point — type the public interface:
def get_user(user_id: int) -> User | None:
    # Internal code doesn't need annotations
    row = db.fetchone("...", user_id)
    if not row:
        return None
    return User(**row)
```'''
    ),
    (
        "thinking/meta-confidence-version-specific-nextjs",
        r'''Should I use the Pages Router or App Router in Next.js? I'm starting a new project today.''',
        r'''<think>
This is a topic where my knowledge may be slightly stale, and the Next.js ecosystem has been evolving rapidly.

HIGH confidence:
- Next.js has two routing systems: Pages Router (legacy) and App Router (new)
- App Router was introduced in Next.js 13 and is the recommended approach
- Pages Router uses getServerSideProps, getStaticProps, getInitialProps
- App Router uses React Server Components, server actions

MEDIUM confidence:
- App Router is now considered stable and the recommended default
- The Pages Router still works and will be supported
- App Router has a steeper learning curve
- Some patterns from Pages Router don't translate directly

LOWER confidence:
- The current state of App Router ecosystem compatibility
- Whether specific libraries (next-auth, prisma, etc.) fully support App Router
- Performance characteristics of App Router vs Pages Router in production
- Exact current best practices for caching/revalidation in App Router

The Next.js team clearly wants people to use App Router, but the ecosystem may still have gaps. I should recommend App Router while flagging potential issues.
</think>

For a new project in 2026, the App Router is the recommended choice. But let me be transparent about my confidence on the specifics.

**HIGH confidence — the general recommendation:**

```
New project → App Router
  - It's the actively developed router
  - New features go to App Router first
  - Official Next.js documentation defaults to App Router
  - React Server Components are only available in App Router

Existing project on Pages Router → no rush to migrate
  - Pages Router is still supported
  - Migration has real costs and can introduce bugs
  - Migrate incrementally if/when needed
```

**HIGH confidence — key differences:**

```
Pages Router (legacy):              App Router (new):
─────────────────────              ─────────────────────
/pages/about.tsx                    /app/about/page.tsx
getServerSideProps()                Server Components (default)
getStaticProps()                    fetch() with caching options
Client-side by default              Server-side by default
Familiar React patterns             New mental model required
```

```tsx
// Pages Router pattern:
export async function getServerSideProps() {
    const data = await fetchData();
    return { props: { data } };
}

export default function Page({ data }) {
    return <div>{data.title}</div>;
}

// App Router pattern:
// This component runs on the SERVER by default
export default async function Page() {
    const data = await fetchData();  // Direct fetch, no special function
    return <div>{data.title}</div>;
}
```

**MEDIUM confidence — practical advice:**

The App Router requires a mental model shift:
```
- Components are Server Components by default (no useState, no useEffect)
- Add "use client" directive when you need interactivity
- Data fetching happens directly in components (no special data functions)
- Layouts are nested and preserved across navigations
- Loading states use loading.tsx files, not manual state
```

```
app/
  layout.tsx        ← Root layout (wraps all pages)
  page.tsx          ← Home page
  about/
    page.tsx        ← /about
  products/
    page.tsx        ← /products
    [id]/
      page.tsx      ← /products/123
    loading.tsx     ← Loading state for /products/*
    error.tsx       ← Error boundary for /products/*
```

**What I'm LESS certain about (verify against current docs):**

- **Caching behavior:** Next.js App Router's caching strategy has been controversial and may have changed. Check the current defaults for `fetch()` caching.
- **Library compatibility:** Some popular libraries may have had updates for App Router compatibility since my knowledge cutoff. Check that your key dependencies (auth, ORM, etc.) support App Router.
- **Server Actions:** The exact syntax and best practices for server actions may have evolved. Verify against next.js.org.

**My recommendation:**

1. Use App Router for new projects — it's the future
2. Read the current Next.js docs (not blog posts from 2023, they're likely outdated)
3. Start with Server Components, add "use client" only when needed
4. If you hit a wall with App Router, the Pages Router still works — you can even use both in the same project during migration'''
    ),
    (
        "thinking/meta-confidence-version-specific-docker",
        r'''What's the best practice for Docker multi-stage builds? I want to minimize my Node.js image size. We're using Docker 25.''',
        r'''<think>
Docker multi-stage builds are well-established and I have high confidence here. The core patterns haven't changed much across Docker versions.

HIGH confidence:
- Multi-stage builds separate build and runtime stages
- Use node:alpine or node:slim for smaller images
- Copy only production node_modules and built artifacts
- Layer ordering matters for cache efficiency
- Docker 25 is recent but multi-stage build syntax hasn't changed

MEDIUM confidence:
- Docker 25 specific features (BuildKit improvements, etc.)
- Exact current Alpine/Slim image tags and their sizes
- Whether there are new Docker 25-specific optimizations

This is an area where I can be quite confident — the Dockerfile best practices are stable and well-documented. I should note that Docker 25 may have improvements I'm not aware of, but the core patterns are the same.
</think>

Multi-stage builds are well-established and I'm confident in these patterns. They work across all modern Docker versions including Docker 25.

**The pattern (HIGH confidence):**

```dockerfile
# Stage 1: Build
FROM node:20-alpine AS builder
WORKDIR /app

# Install dependencies first (cache layer)
COPY package.json package-lock.json ./
RUN npm ci

# Then copy source and build
COPY . .
RUN npm run build

# Prune dev dependencies
RUN npm ci --production --ignore-scripts


# Stage 2: Runtime (minimal image)
FROM node:20-alpine AS runner
WORKDIR /app

# Non-root user (security)
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 appuser

# Copy only what's needed to run
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./

USER appuser
EXPOSE 3000
CMD ["node", "dist/server.js"]
```

**Layer ordering for cache efficiency (HIGH confidence):**

```dockerfile
# WRONG ORDER — cache busted on every code change:
COPY . .                   # Any file change invalidates everything below
RUN npm ci                 # Reinstalls all deps even for a 1-line change
RUN npm run build

# RIGHT ORDER — deps cached unless package.json changes:
COPY package.json package-lock.json ./   # Changes rarely
RUN npm ci                               # Cached unless deps change
COPY . .                                 # Changes frequently
RUN npm run build                        # Only rebuilds app code
```

**Size comparison (approximate, verify exact numbers):**

```
Image                          Approximate size
──────────────────────────────────────────────
node:20                        ~1000MB
node:20-slim                   ~200MB
node:20-alpine                 ~130MB
Multi-stage with alpine        ~80-150MB (deps dependent)
Distroless                     ~50-100MB
```

**Additional optimizations (HIGH confidence):**

```dockerfile
# .dockerignore — prevent copying unnecessary files
node_modules
.git
*.md
.env*
dist
coverage
.next

# Use specific versions, not 'latest'
FROM node:20.11-alpine  # Reproducible builds

# Combine RUN commands to reduce layers
RUN addgroup --system nodejs && \
    adduser --system --uid 1001 appuser
```

**For even smaller images — distroless (MEDIUM confidence on exact syntax):**

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build && npm ci --production

# Google's distroless image — no shell, no package manager
FROM gcr.io/distroless/nodejs20-debian12
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./
CMD ["dist/server.js"]
```

**Docker 25 note:** The core multi-stage build syntax hasn't changed. Docker 25 likely has BuildKit improvements for build speed and caching, but the Dockerfile patterns above are stable across versions. Check Docker 25 release notes for any new optimization features I may not be aware of.

**Quick checklist:**
```
- [ ] Multi-stage: separate build and runtime
- [ ] Alpine or slim base image
- [ ] Copy package files before source (cache layers)
- [ ] Use npm ci (not npm install) for reproducibility
- [ ] .dockerignore prevents copying node_modules, .git
- [ ] Run as non-root user
- [ ] Pin specific base image versions
- [ ] Production deps only in runtime stage
```'''
    ),
    (
        "thinking/meta-confidence-version-specific-typescript",
        r'''How should I handle errors in TypeScript? I keep seeing different patterns — try/catch, Result types, throwing errors. What's the recommended approach in TypeScript 5.x?''',
        r'''<think>
Error handling in TypeScript is an area where the language itself hasn't prescribed a single pattern, but community best practices have evolved. Let me calibrate.

HIGH confidence:
- try/catch is the native JavaScript/TypeScript approach
- TypeScript catch blocks type errors as `unknown` since TS 4.4
- There's no built-in Result/Either type in TypeScript
- The community is split between throw-based and return-based error handling
- TypeScript 5.x hasn't changed error handling fundamentals

MEDIUM confidence:
- The trend in the TypeScript community toward Result types
- Libraries like neverthrow, fp-ts, Effect for typed error handling
- TypeScript's type system can express discriminated unions well for error handling
- The "throw or return" debate is ongoing with no clear winner

LOWER confidence:
- Whether TypeScript 5.x introduced any new error handling features
- Current community consensus (if any exists)
- Whether the "use" proposal in TC39 affects error handling patterns

I should present the options honestly, explain the tradeoffs, and let them choose based on their context. There's no single "recommended" approach.
</think>

There is no single "recommended" approach in TypeScript 5.x — the language doesn't prescribe one. The community is genuinely split. Let me present the options with honest confidence assessments.

**Option 1: try/catch (native, widely used)**

```typescript
// TypeScript types catch errors as 'unknown' (since TS 4.4)
async function getUser(id: string): Promise<User> {
    try {
        const response = await fetch(`/api/users/${id}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
    } catch (error: unknown) {
        if (error instanceof Error) {
            throw new AppError(`Failed to fetch user: ${error.message}`);
        }
        throw new AppError('Unknown error fetching user');
    }
}
```

Pros: Familiar, no libraries, works with async/await.
Cons: No type safety — callers don't know what errors are possible from the function signature.

**Option 2: Discriminated union / Result type (no library)**

```typescript
type Result<T, E = Error> =
    | { success: true; data: T }
    | { success: false; error: E };

async function getUser(id: string): Promise<Result<User, AppError>> {
    try {
        const response = await fetch(`/api/users/${id}`);
        if (!response.ok) {
            return { success: false, error: new AppError(`HTTP ${response.status}`) };
        }
        const user = await response.json();
        return { success: true, data: user };
    } catch {
        return { success: false, error: new AppError('Network error') };
    }
}

// Caller MUST handle the error (type system enforces it):
const result = await getUser('123');
if (!result.success) {
    console.error(result.error.message);
    return;
}
// TypeScript knows result.data is User here
console.log(result.data.name);
```

Pros: Error is visible in the type signature. Caller can't forget to handle it.
Cons: More verbose. Every function needs Result wrapping.

**Option 3: neverthrow library (popular, lightweight)**

```typescript
import { ok, err, Result } from 'neverthrow';

function parseAge(input: string): Result<number, string> {
    const age = parseInt(input, 10);
    if (isNaN(age)) return err('Invalid number');
    if (age < 0 || age > 150) return err('Age out of range');
    return ok(age);
}

// Chainable:
const result = parseAge(input)
    .map(age => age * 12)        // Transform success value
    .mapErr(e => `Parse error: ${e}`);  // Transform error

// Pattern matching:
result.match(
    months => console.log(`${months} months old`),
    error => console.error(error),
);
```

Pros: Clean API, type-safe, chainable. Cons: External dependency.

**My honest assessment (HIGH confidence on the tradeoffs):**

```
Team familiarity with FP concepts?
  Low  → Option 1 (try/catch) with custom error classes
  Med  → Option 2 (Result type, no library)
  High → Option 3 (neverthrow or similar)

Project size?
  Small script    → try/catch is fine
  Medium app      → Result type for critical paths, try/catch elsewhere
  Large codebase  → Consistent approach across the codebase matters most

What matters most?
  Simplicity      → try/catch
  Type safety     → Result type
  Composability   → neverthrow / Effect
```

**What TypeScript 5.x specifically offers:** The type system improvements in TS 5.x (better type inference, const type parameters, etc.) make all three patterns work better, but there's no new built-in error handling feature. The choice remains a team/project decision.

**My practical recommendation:** Start with Option 2 (simple Result type) for functions that can fail in expected ways. Use try/catch for truly unexpected errors. This gives you type safety without a library dependency.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
