"""
Batch P1214 -- TypeScript error handling: Result types, error boundaries,
typed error classes, exhaustive switch, discriminated unions for errors.
Target: JS/TS rebalancing. 2 thinking + 3 direct pairs.
"""

pairs = [
    # --- 1. thinking: Result type pattern ---
    {
        "instruction": r'''How do I implement a Result type in TypeScript like Rust has, to handle errors without throwing exceptions?''',
        "output": r'''<think>
The Result type encodes success/failure in the type system. Instead of
throw/catch (which TypeScript cannot type-check), return Result<T, E>
and the caller must handle both cases. I will use discriminated union
approach since it is more idiomatic in TS than class-based monads.
Key benefit: errors visible in function signatures.
</think>

A Result type makes errors explicit in return types, forcing callers to handle both cases:

```typescript
type Result<T, E = Error> =
  | { ok: true; value: T }
  | { ok: false; error: E };

function Ok<T>(value: T): Result<T, never> { return { ok: true, value }; }
function Err<E>(error: E): Result<never, E> { return { ok: false, error }; }

// Wrap throwing functions
function tryCatch<T>(fn: () => T): Result<T, Error> {
  try { return Ok(fn()); }
  catch (e) { return Err(e instanceof Error ? e : new Error(String(e))); }
}

// Typed error hierarchy
type ApiError =
  | { code: "NOT_FOUND"; resource: string }
  | { code: "VALIDATION"; fields: Record<string, string> }
  | { code: "UNAUTHORIZED" }
  | { code: "NETWORK"; message: string };

async function fetchUser(id: string): Promise<Result<User, ApiError>> {
  const res = await fetch(`/api/users/${id}`);
  if (res.status === 404) return Err({ code: "NOT_FOUND", resource: `user:${id}` });
  if (res.status === 401) return Err({ code: "UNAUTHORIZED" });
  if (!res.ok) return Err({ code: "NETWORK", message: `HTTP ${res.status}` });
  return Ok(await res.json());
}

// Caller must handle both cases
const result = await fetchUser("123");
if (!result.ok) {
  switch (result.error.code) {
    case "NOT_FOUND": console.log(result.error.resource); break;
    case "VALIDATION": console.log(result.error.fields); break;
    case "UNAUTHORIZED": redirectToLogin(); break;
    case "NETWORK": showRetry(result.error.message); break;
  }
  return;
}
// result.value is typed as User here
renderUser(result.value);

interface User { id: string; name: string; }
function redirectToLogin() {}
function showRetry(m: string) {}
function renderUser(u: User) {}
```

Unlike try/catch, the error type is visible in the function signature and cannot be silently ignored.'''
    },

    # --- 2. direct: React error boundaries ---
    {
        "instruction": r'''How do I implement error boundaries in React with TypeScript, including fallback UI and error recovery?''',
        "output": r'''Error boundaries catch rendering errors in child components. Must be class components:

```typescript
import { Component, ErrorInfo, ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode | ((error: Error, reset: () => void) => ReactNode);
  onError?: (error: Error, info: ErrorInfo) => void;
}

class ErrorBoundary extends Component<Props, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) { return { error }; }

  componentDidCatch(error: Error, info: ErrorInfo) {
    this.props.onError?.(error, info);
  }

  reset = () => this.setState({ error: null });

  render() {
    if (this.state.error) {
      const { fallback } = this.props;
      if (typeof fallback === "function") return fallback(this.state.error, this.reset);
      return fallback ?? (
        <div role="alert">
          <h2>Something went wrong</h2>
          <pre>{this.state.error.message}</pre>
          <button onClick={this.reset}>Try Again</button>
        </div>
      );
    }
    return this.props.children;
  }
}

// Usage: wrap sections independently
function App() {
  return (
    <div>
      <ErrorBoundary
        onError={(e) => reportToSentry(e)}
        fallback={(err, reset) => (
          <div><p>Failed: {err.message}</p><button onClick={reset}>Retry</button></div>
        )}
      >
        <Dashboard />
      </ErrorBoundary>
      <ErrorBoundary fallback={<p>Sidebar unavailable</p>}>
        <Sidebar />
      </ErrorBoundary>
    </div>
  );
}

function reportToSentry(e: Error) {}
function Dashboard() { return <div>Dashboard</div>; }
function Sidebar() { return <div>Sidebar</div>; }
```

Error boundaries catch render/lifecycle errors. They do NOT catch event handler or async errors -- use try/catch for those.'''
    },

    # --- 3. direct: typed error classes ---
    {
        "instruction": r'''Show how to create a typed error class hierarchy in TypeScript for a web application with proper instanceof checks.''',
        "output": r'''Build typed error classes with a readonly `code` for programmatic matching:

```typescript
abstract class AppError extends Error {
  abstract readonly code: string;
  abstract readonly statusCode: number;

  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = this.constructor.name;
    Object.setPrototypeOf(this, new.target.prototype); // fix instanceof
  }

  toJSON() { return { code: this.code, message: this.message }; }
}

class NotFoundError extends AppError {
  readonly code = "NOT_FOUND" as const;
  readonly statusCode = 404;
  constructor(public readonly resource: string, public readonly id: string) {
    super(`${resource} '${id}' not found`);
  }
}

class ValidationError extends AppError {
  readonly code = "VALIDATION" as const;
  readonly statusCode = 400;
  constructor(public readonly fields: Record<string, string[]>) {
    super(`Validation failed on ${Object.keys(fields).length} field(s)`);
  }
}

class RateLimitError extends AppError {
  readonly code = "RATE_LIMIT" as const;
  readonly statusCode = 429;
  constructor(public readonly retryAfterMs: number) {
    super(`Rate limited. Retry after ${retryAfterMs}ms`);
  }
}

// Error handler
function handleError(err: unknown): { status: number; body: object } {
  if (err instanceof AppError) return { status: err.statusCode, body: err.toJSON() };
  console.error("Unhandled:", err);
  return { status: 500, body: { code: "INTERNAL", message: "Unexpected error" } };
}

// instanceof narrowing gives typed access
try { /* ... */ } catch (err) {
  if (err instanceof NotFoundError) console.log(err.resource, err.id);
  else if (err instanceof RateLimitError) setTimeout(retry, err.retryAfterMs);
}
function retry() {}
```

The `Object.setPrototypeOf` call fixes `instanceof` checks when transpiling `extends Error`.'''
    },

    # --- 4. thinking: exhaustive switch ---
    {
        "instruction": r'''How do I make TypeScript enforce exhaustive switch statements so adding a new union member causes a compile error?''',
        "output": r'''<think>
The trick is the "never" check in the default case. After all union
members are handled, the variable narrows to never. If a new member is
added without handling it, the narrowing fails and the compile error
points to the assertNever call. This turns runtime "unhandled case"
bugs into compile-time errors.
</think>

Use the `never` type to catch unhandled cases at compile time:

```typescript
function assertNever(value: never, msg?: string): never {
  throw new Error(msg ?? `Unhandled: ${JSON.stringify(value)}`);
}

type OrderStatus =
  | { status: "pending"; createdAt: Date }
  | { status: "shipped"; trackingId: string }
  | { status: "delivered"; deliveredAt: Date }
  | { status: "cancelled"; reason: string };

function getMessage(order: OrderStatus): string {
  switch (order.status) {
    case "pending": return "Order pending";
    case "shipped": return `Tracking: ${order.trackingId}`;
    case "delivered": return `Delivered ${order.deliveredAt.toISOString()}`;
    case "cancelled": return `Cancelled: ${order.reason}`;
    default: return assertNever(order);
    // If you add "refunded" to the union without a case here,
    // compile error: '{ status: "refunded" }' not assignable to 'never'
  }
}

// Alternative: exhaustive Record (no switch needed)
const LABELS: Record<OrderStatus["status"], string> = {
  pending: "Pending",
  shipped: "Shipped",
  delivered: "Delivered",
  cancelled: "Cancelled",
  // Missing key = compile error
};

// Works with reducers too
type Action = { type: "INC"; by: number } | { type: "DEC"; by: number } | { type: "RESET" };

function reducer(state: number, action: Action): number {
  switch (action.type) {
    case "INC": return state + action.by;
    case "DEC": return state - action.by;
    case "RESET": return 0;
    default: return assertNever(action);
  }
}
```

After all members are handled, the variable narrows to `never`. Adding a new member without handling it breaks the narrowing, producing a compile error.'''
    },

    # --- 5. direct: discriminated unions for errors ---
    {
        "instruction": r'''Show how to use TypeScript discriminated unions to model different error states in an application, with type narrowing.''',
        "output": r'''Discriminated unions model error states as data, making every error visible in types:

```typescript
type FetchResult<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; data: T; fetchedAt: number }
  | { status: "error"; error: AppError };

type AppError =
  | { kind: "network"; message: string; retryable: boolean }
  | { kind: "auth"; expired: boolean }
  | { kind: "validation"; fields: { path: string; message: string }[] }
  | { kind: "notFound"; resource: string; id: string };

function renderError(error: AppError): string {
  switch (error.kind) {
    case "network":
      return error.retryable ? `${error.message} (retry available)` : error.message;
    case "auth":
      return error.expired ? "Session expired" : "Not authorized";
    case "validation":
      return error.fields.map((f) => `${f.path}: ${f.message}`).join("; ");
    case "notFound":
      return `${error.resource} '${error.id}' not found`;
  }
}

function renderResult<T>(result: FetchResult<T>, show: (d: T) => string): string {
  switch (result.status) {
    case "idle": return "Ready";
    case "loading": return "Loading...";
    case "success": return show(result.data);
    case "error": return renderError(result.error);
  }
}

// React usage
import { useState, useEffect } from "react";

function UserProfile({ id }: { id: string }) {
  const [result, setResult] = useState<FetchResult<{ name: string }>>({ status: "idle" });
  useEffect(() => {
    setResult({ status: "loading" });
    fetch(`/api/users/${id}`)
      .then(async (res) => {
        if (res.status === 404) setResult({ status: "error", error: { kind: "notFound", resource: "User", id } });
        else if (res.ok) setResult({ status: "success", data: await res.json(), fetchedAt: Date.now() });
        else setResult({ status: "error", error: { kind: "network", message: `HTTP ${res.status}`, retryable: true } });
      })
      .catch(() => setResult({ status: "error", error: { kind: "network", message: "Offline", retryable: true } }));
  }, [id]);
  return <div>{renderResult(result, (u) => u.name)}</div>;
}
```

The `status` and `kind` fields are discriminants. TypeScript narrows after checking them, ensuring correct property access in each branch.'''
    },
]
