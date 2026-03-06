"""TypeScript Advanced Types — conditional types, template literals, branded types, discriminated unions, recursive types."""

PAIRS = [
    (
        "typescript/production",
        r'''Explain and demonstrate TypeScript conditional types for API response mapping. Show how to map different API endpoints to their response types at the type level, with practical production patterns.''',
        r'''# TypeScript Conditional Types for API Response Mapping

Conditional types let you express type-level branching: given an input type, derive an output type. This is invaluable for mapping API endpoints to their response shapes without maintaining parallel type definitions.

## Core Mechanism

```typescript
// Basic conditional type syntax: T extends U ? X : Y

// Map endpoint paths to their response types
type ApiResponse<T extends string> =
  T extends "/users" ? UserListResponse :
  T extends `/users/${string}` ? UserDetailResponse :
  T extends "/orders" ? OrderListResponse :
  T extends `/orders/${string}` ? OrderDetailResponse :
  never;

interface UserListResponse {
  users: User[];
  total: number;
  page: number;
  perPage: number;
}

interface UserDetailResponse {
  user: User;
  permissions: Permission[];
}

interface OrderListResponse {
  orders: Order[];
  cursor: string | null;
}

interface OrderDetailResponse {
  order: Order;
  lineItems: LineItem[];
  shipments: Shipment[];
}
```

## Production Pattern: Type-Safe API Client

```typescript
// Infer method + path combinations
type HttpMethod = "GET" | "POST" | "PUT" | "DELETE";

type EndpointConfig = {
  "GET /users": { response: UserListResponse; query: { page?: number; search?: string } };
  "GET /users/:id": { response: UserDetailResponse; query: never };
  "POST /users": { response: UserDetailResponse; body: CreateUserPayload };
  "PUT /users/:id": { response: UserDetailResponse; body: UpdateUserPayload };
  "DELETE /users/:id": { response: { success: boolean }; body: never };
  "GET /orders": { response: OrderListResponse; query: { cursor?: string } };
  "POST /orders": { response: OrderDetailResponse; body: CreateOrderPayload };
};

// Extract response type for a given endpoint key
type ResponseFor<K extends keyof EndpointConfig> = EndpointConfig[K]["response"];

// Extract body type if it exists
type BodyFor<K extends keyof EndpointConfig> =
  EndpointConfig[K] extends { body: infer B } ? B : never;

// Extract query type if it exists
type QueryFor<K extends keyof EndpointConfig> =
  EndpointConfig[K] extends { query: infer Q } ? Q : never;

// Split "GET /users" into method and path
type ExtractMethod<K extends string> =
  K extends `${infer M} ${string}` ? M : never;

type ExtractPath<K extends string> =
  K extends `${string} ${infer P}` ? P : never;

// Build the type-safe fetcher
class ApiClient {
  private baseUrl: string;
  private headers: HeadersInit;

  constructor(baseUrl: string, headers: HeadersInit = {}) {
    this.baseUrl = baseUrl;
    this.headers = headers;
  }

  async request<K extends keyof EndpointConfig>(
    endpoint: K,
    ...args: BodyFor<K> extends never
      ? QueryFor<K> extends never
        ? [options?: { signal?: AbortSignal }]
        : [options: { query: QueryFor<K>; signal?: AbortSignal }]
      : [options: { body: BodyFor<K>; signal?: AbortSignal }]
  ): Promise<ResponseFor<K>> {
    const [method, path] = (endpoint as string).split(" ");
    const options = args[0] as Record<string, unknown> | undefined;

    const url = new URL(path, this.baseUrl);
    if (options && "query" in options && options.query) {
      const query = options.query as Record<string, string>;
      Object.entries(query).forEach(([k, v]) => {
        if (v !== undefined) url.searchParams.set(k, String(v));
      });
    }

    const response = await fetch(url.toString(), {
      method,
      headers: {
        "Content-Type": "application/json",
        ...this.headers,
      },
      body: options && "body" in options ? JSON.stringify(options.body) : undefined,
      signal: options?.signal as AbortSignal | undefined,
    });

    if (!response.ok) {
      throw new ApiError(response.status, await response.text());
    }

    return response.json() as Promise<ResponseFor<K>>;
  }
}

// Usage — fully type-safe, no generics at call site
const api = new ApiClient("https://api.example.com");

// TypeScript knows this returns UserListResponse
const users = await api.request("GET /users", {
  query: { page: 1, search: "dan" },
});
console.log(users.users[0].name); // autocomplete works

// TypeScript knows this returns OrderDetailResponse and requires a body
const order = await api.request("POST /orders", {
  body: { items: [{ sku: "ABC", quantity: 2 }] },
});
console.log(order.lineItems); // autocomplete works
```

## Distributive Conditional Types

```typescript
// Conditional types distribute over unions automatically
type NonNullableFields<T> = {
  [K in keyof T]: T[K] extends null | undefined ? never : K;
}[keyof T];

// Extract only the endpoints that accept a body
type EndpointsWithBody = {
  [K in keyof EndpointConfig]: EndpointConfig[K] extends { body: infer B }
    ? B extends never ? never : K
    : never;
}[keyof EndpointConfig];
// Result: "POST /users" | "PUT /users/:id" | "POST /orders"
```

## Common Pitfalls

1. **Forgetting `never` propagation**: `never extends X ? Y : Z` evaluates to `never` (distributes over empty union). Wrap in tuple to prevent: `[T] extends [never] ? ... : ...`
2. **Excessive nesting**: More than 3-4 levels of conditional types become unreadable. Extract intermediate types.
3. **Performance**: Deeply nested conditional types slow down the compiler. Use indexed access types (`EndpointConfig[K]["response"]`) instead of conditionals when a simple lookup suffices.

Conditional types are the backbone of type-level programming in TypeScript. When combined with template literal types and `infer`, they let you build APIs where incorrect usage is caught entirely at compile time.
''',
    ),
    (
        "typescript/production",
        r'''Show how to use TypeScript template literal types for type-safe route parameters. Include parsing dynamic segments from URL patterns and building type-safe route helpers.''',
        r'''# Template Literal Types for Type-Safe Route Parameters

Template literal types let you parse and manipulate string types at the type level. This is particularly powerful for routing, where you want to extract dynamic segments like `:id` from a path and enforce that the correct parameters are provided.

## Extracting Route Params

```typescript
// Parse ":param" segments from a route string
type ExtractRouteParams<T extends string> =
  T extends `${string}:${infer Param}/${infer Rest}`
    ? Param | ExtractRouteParams<Rest>
    : T extends `${string}:${infer Param}`
      ? Param
      : never;

// Test it
type UserEditParams = ExtractRouteParams<"/users/:userId/posts/:postId/edit">;
// Result: "userId" | "postId"

// Build a params object from the union
type RouteParams<T extends string> =
  ExtractRouteParams<T> extends never
    ? Record<string, never>
    : Record<ExtractRouteParams<T>, string>;

// Result for "/users/:userId/posts/:postId/edit":
// { userId: string; postId: string }
```

## Production Pattern: Type-Safe Router

```typescript
// Define all application routes
type AppRoutes = {
  "/dashboard": Record<string, never>;
  "/users": Record<string, never>;
  "/users/:userId": { userId: string };
  "/users/:userId/settings": { userId: string };
  "/teams/:teamId/members/:memberId": { teamId: string; memberId: string };
  "/orgs/:orgId/projects/:projectId/tasks/:taskId": {
    orgId: string;
    projectId: string;
    taskId: string;
  };
};

// Build a URL from a route pattern and params
function buildPath<T extends keyof AppRoutes>(
  pattern: T,
  ...args: AppRoutes[T] extends Record<string, never>
    ? []
    : [params: AppRoutes[T]]
): string {
  const params = args[0] as Record<string, string> | undefined;
  if (!params) return pattern as string;

  let result: string = pattern as string;
  for (const [key, value] of Object.entries(params)) {
    result = result.replace(`:${key}`, encodeURIComponent(value));
  }
  return result;
}

// Usage — type errors if params are missing or wrong
const dashboardUrl = buildPath("/dashboard"); // no params needed
const userUrl = buildPath("/users/:userId", { userId: "abc-123" });
const taskUrl = buildPath(
  "/orgs/:orgId/projects/:projectId/tasks/:taskId",
  { orgId: "org-1", projectId: "proj-2", taskId: "task-3" }
);

// Type error: Property 'teamId' is missing
// buildPath("/teams/:teamId/members/:memberId", { memberId: "m-1" });
```

## Automatic Param Extraction (No Manual Mapping)

```typescript
// Eliminate the manual AppRoutes mapping — derive params automatically
type AutoRouteParams<T extends string> =
  ExtractRouteParams<T> extends never
    ? []
    : [params: Record<ExtractRouteParams<T>, string>];

function navigate<T extends string>(
  pattern: T,
  ...args: AutoRouteParams<T>
): void {
  let url: string = pattern;
  const params = args[0] as Record<string, string> | undefined;
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      url = url.replace(`:${key}`, encodeURIComponent(value));
    }
  }
  window.history.pushState(null, "", url);
}

// Fully inferred — no route registry needed
navigate("/users/:userId", { userId: "abc" }); // OK
navigate("/dashboard"); // OK, no params required
// navigate("/users/:userId"); // Error: expected params argument
// navigate("/users/:userId", { wrong: "x" }); // Error: missing userId
```

## Query String Type Safety

```typescript
// Extend to handle query parameters
type QueryConfig = {
  "/users": { search?: string; page?: string; role?: "admin" | "user" };
  "/orders": { status?: "pending" | "shipped" | "delivered"; cursor?: string };
};

function buildUrl<T extends keyof AppRoutes & keyof QueryConfig>(
  pattern: T,
  ...args: AppRoutes[T] extends Record<string, never>
    ? [query?: QueryConfig[T]]
    : [params: AppRoutes[T], query?: QueryConfig[T]]
): string {
  // Implementation builds path then appends query string
  let paramIndex = 0;
  let queryIndex = 1;
  if (
    (args[0] && typeof args[0] === "object" && Object.keys(args[0] as object).length > 0)
    === false
  ) {
    queryIndex = 0;
  }

  let path: string = pattern as string;
  const params = paramIndex === 0 ? (args[0] as Record<string, string>) : undefined;
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      path = path.replace(`:${key}`, encodeURIComponent(value));
    }
  }

  const query = args[queryIndex] as Record<string, string> | undefined;
  if (query) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined) qs.set(k, v);
    }
    const str = qs.toString();
    if (str) path += `?${str}`;
  }

  return path;
}
```

## Common Pitfalls

1. **Recursive depth limits**: TypeScript caps template literal recursion at ~45-50 levels. Routes with many segments can hit this; keep routes under 10 dynamic segments (not a practical problem).
2. **String literal widening**: `const route = "/users/" + id` produces `string`, not a literal. Use template literals: `` `/users/${id}` as const `` does NOT work at runtime. Keep patterns as literals and substitute at the value level.
3. **Performance**: Large unions of route strings can slow the language server. Group routes by feature module if you have 100+ routes.

Template literal types turn your router into a compile-time contract. Mistyped URLs, missing parameters, and invalid query values are all caught before the code runs.
''',
    ),
    (
        "typescript/production",
        r'''Demonstrate branded/opaque types in TypeScript for type-safe IDs. Show how to prevent mixing up UserId and OrderId even though both are strings at runtime.''',
        r'''# Branded (Opaque) Types for Type-Safe IDs

Branded types add a phantom type tag to a primitive so that `UserId` and `OrderId` are incompatible at compile time, even though both are `string` at runtime. This eliminates an entire class of bugs where IDs get swapped.

## The Branding Pattern

```typescript
// Declare a unique symbol for each brand
declare const __brand: unique symbol;

// Generic branded type
type Brand<T, B extends string> = T & { readonly [__brand]: B };

// Define your ID types
type UserId = Brand<string, "UserId">;
type OrderId = Brand<string, "OrderId">;
type TeamId = Brand<string, "TeamId">;
type ProductId = Brand<string, "ProductId">;

// Constructor functions — the ONLY way to create branded values
function UserId(id: string): UserId {
  if (!id || id.length === 0) throw new Error("UserId cannot be empty");
  return id as UserId;
}

function OrderId(id: string): OrderId {
  if (!id || id.length === 0) throw new Error("OrderId cannot be empty");
  return id as OrderId;
}

function TeamId(id: string): TeamId {
  return id as TeamId;
}

function ProductId(id: string): ProductId {
  return id as ProductId;
}
```

## Why This Matters

```typescript
// Without branded types — this compiles and causes a bug
function getUser(id: string): Promise<User> { /* ... */ }
function getOrder(id: string): Promise<Order> { /* ... */ }

const orderId = "order-abc-123";
getUser(orderId); // No error! Silent bug — querying users table with order ID

// With branded types — compile-time error
function getUserBranded(id: UserId): Promise<User> { /* ... */ }
function getOrderBranded(id: OrderId): Promise<Order> { /* ... */ }

const userId = UserId("user-xyz-789");
const myOrderId = OrderId("order-abc-123");

getUserBranded(userId);     // OK
getOrderBranded(myOrderId); // OK
// getUserBranded(myOrderId); // Error: Argument of type 'OrderId' is not assignable to 'UserId'
// getOrderBranded(userId);   // Error: Argument of type 'UserId' is not assignable to 'OrderId'
```

## Production Pattern: Full Entity Layer

```typescript
// Validated branded types with format checks
type Email = Brand<string, "Email">;
type Slug = Brand<string, "Slug">;
type Url = Brand<string, "Url">;
type NonEmptyString = Brand<string, "NonEmptyString">;

function Email(value: string): Email {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(value)) {
    throw new ValidationError(`Invalid email: ${value}`);
  }
  return value.toLowerCase() as Email;
}

function Slug(value: string): Slug {
  const slugRegex = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
  if (!slugRegex.test(value)) {
    throw new ValidationError(`Invalid slug: ${value}`);
  }
  return value as Slug;
}

// Use in domain models
interface User {
  id: UserId;
  email: Email;
  teamId: TeamId;
  name: NonEmptyString;
}

interface Order {
  id: OrderId;
  userId: UserId;        // Cannot accidentally use OrderId here
  products: ProductId[]; // Cannot mix in UserIds
  status: OrderStatus;
}

// Repository with branded IDs
interface UserRepository {
  findById(id: UserId): Promise<User | null>;
  findByEmail(email: Email): Promise<User | null>;
  findByTeam(teamId: TeamId): Promise<User[]>;
}

class PostgresUserRepository implements UserRepository {
  async findById(id: UserId): Promise<User | null> {
    // id is still a string at runtime — zero overhead
    const row = await this.db.query("SELECT * FROM users WHERE id = $1", [id]);
    return row ? this.toDomain(row) : null;
  }

  async findByEmail(email: Email): Promise<User | null> {
    const row = await this.db.query("SELECT * FROM users WHERE email = $1", [email]);
    return row ? this.toDomain(row) : null;
  }

  async findByTeam(teamId: TeamId): Promise<User[]> {
    const rows = await this.db.query("SELECT * FROM users WHERE team_id = $1", [teamId]);
    return rows.map((r) => this.toDomain(r));
  }

  private toDomain(row: UserRow): User {
    return {
      id: UserId(row.id),
      email: Email(row.email),
      teamId: TeamId(row.team_id),
      name: row.name as NonEmptyString,
    };
  }
}
```

## Integration with Zod

```typescript
import { z } from "zod";

// Zod schemas that produce branded types
const userIdSchema = z.string().uuid().transform((val) => UserId(val));
const orderIdSchema = z.string().uuid().transform((val) => OrderId(val));
const emailSchema = z.string().email().transform((val) => Email(val));

// Use in API request validation
const createOrderSchema = z.object({
  userId: userIdSchema,
  productIds: z.array(z.string().uuid().transform((v) => ProductId(v))).min(1),
  shippingAddress: z.string().min(1),
});

type CreateOrderInput = z.infer<typeof createOrderSchema>;
// { userId: UserId; productIds: ProductId[]; shippingAddress: string }

// API handler — IDs are branded from the moment they enter the system
async function handleCreateOrder(req: Request): Promise<Response> {
  const parsed = createOrderSchema.safeParse(await req.json());
  if (!parsed.success) {
    return Response.json({ errors: parsed.error.flatten() }, { status: 400 });
  }
  const { userId, productIds } = parsed.data;
  // userId is UserId, productIds is ProductId[] — fully type-safe downstream
  const order = await orderService.create(userId, productIds);
  return Response.json(order, { status: 201 });
}
```

## Common Pitfalls

1. **Serialization**: Branded types serialize to plain strings in JSON. When deserializing, always pass through the constructor to re-brand.
2. **Comparison**: `userId === orderId` still compiles because TypeScript structural typing allows comparison. Use ESLint `@typescript-eslint/no-unnecessary-condition` or strict equality wrappers if needed.
3. **Overuse**: Brand domain-critical IDs and validated strings. Do not brand every string in your codebase — it adds friction without proportional safety.

Branded types cost zero bytes at runtime while catching ID-swap bugs that would otherwise reach production.
''',
    ),
    (
        "typescript/production",
        r'''Demonstrate TypeScript discriminated unions for modeling state machines. Show a real example like an async data flow or multi-step wizard, with exhaustive pattern matching.''',
        r'''# Discriminated Unions for State Machines

Discriminated unions model states where each state carries exactly the data it needs. The discriminant field (usually `status` or `kind`) lets TypeScript narrow the type automatically in switch/if branches, making illegal states unrepresentable.

## Core Pattern: Async Data State

```typescript
// Each state has ONLY the fields that make sense for it
type AsyncState<T, E = Error> =
  | { status: "idle" }
  | { status: "loading"; abortController: AbortController }
  | { status: "success"; data: T; fetchedAt: number }
  | { status: "error"; error: E; retryCount: number };

// Exhaustive handler — TypeScript enforces you handle every state
function renderAsync<T>(state: AsyncState<T>, render: (data: T) => React.ReactNode): React.ReactNode {
  switch (state.status) {
    case "idle":
      return null;
    case "loading":
      return <LoadingSkeleton />;
    case "success":
      return render(state.data); // state.data is available, state.error is NOT
    case "error":
      return <ErrorBanner message={state.error.message} />;
    // No default needed — TypeScript errors if a case is missing
  }
}

// The never trick for exhaustiveness checking
function assertNever(x: never): never {
  throw new Error(`Unexpected value: ${JSON.stringify(x)}`);
}

function getStatusMessage<T>(state: AsyncState<T>): string {
  switch (state.status) {
    case "idle": return "Ready";
    case "loading": return "Loading...";
    case "success": return `Loaded at ${new Date(state.fetchedAt).toISOString()}`;
    case "error": return `Failed (attempt ${state.retryCount})`;
    default: return assertNever(state); // Compile error if a case is missing
  }
}
```

## Production Pattern: Multi-Step Checkout

```typescript
// Each step carries its own validated data
type CheckoutState =
  | {
      step: "cart";
      items: CartItem[];
      couponCode: string | null;
    }
  | {
      step: "shipping";
      items: CartItem[];
      couponCode: string | null;
      shippingAddress: ShippingAddress;
    }
  | {
      step: "payment";
      items: CartItem[];
      couponCode: string | null;
      shippingAddress: ShippingAddress;
      shippingMethod: ShippingMethod;
      totals: OrderTotals;
    }
  | {
      step: "confirmation";
      orderId: OrderId;
      estimatedDelivery: Date;
    }
  | {
      step: "error";
      previousStep: "cart" | "shipping" | "payment";
      error: CheckoutError;
      recovery: CheckoutState; // State to return to on retry
    };

// Transitions — each function takes the CURRENT state and returns the NEXT state
type CheckoutAction =
  | { type: "SET_SHIPPING"; address: ShippingAddress }
  | { type: "SELECT_SHIPPING_METHOD"; method: ShippingMethod }
  | { type: "CONFIRM_PAYMENT"; paymentMethodId: string }
  | { type: "GO_BACK" }
  | { type: "RETRY" };

function checkoutReducer(state: CheckoutState, action: CheckoutAction): CheckoutState {
  switch (action.type) {
    case "SET_SHIPPING": {
      if (state.step !== "cart") return state;
      return {
        step: "shipping",
        items: state.items,
        couponCode: state.couponCode,
        shippingAddress: action.address,
      };
    }

    case "SELECT_SHIPPING_METHOD": {
      if (state.step !== "shipping") return state;
      return {
        step: "payment",
        items: state.items,
        couponCode: state.couponCode,
        shippingAddress: state.shippingAddress,
        shippingMethod: action.method,
        totals: calculateTotals(state.items, state.couponCode, action.method),
      };
    }

    case "GO_BACK": {
      switch (state.step) {
        case "shipping":
          return { step: "cart", items: state.items, couponCode: state.couponCode };
        case "payment":
          return {
            step: "shipping",
            items: state.items,
            couponCode: state.couponCode,
            shippingAddress: state.shippingAddress,
          };
        default:
          return state;
      }
    }

    case "RETRY": {
      if (state.step !== "error") return state;
      return state.recovery;
    }

    default:
      return state;
  }
}

// React component — TypeScript narrows in each branch
function CheckoutWizard({ state, dispatch }: {
  state: CheckoutState;
  dispatch: React.Dispatch<CheckoutAction>;
}) {
  switch (state.step) {
    case "cart":
      return <CartReview items={state.items} onCheckout={(addr) =>
        dispatch({ type: "SET_SHIPPING", address: addr })
      } />;
    case "shipping":
      return <ShippingSelector
        address={state.shippingAddress}
        onSelect={(method) => dispatch({ type: "SELECT_SHIPPING_METHOD", method })}
        onBack={() => dispatch({ type: "GO_BACK" })}
      />;
    case "payment":
      return <PaymentForm
        totals={state.totals}
        onConfirm={(pmId) => dispatch({ type: "CONFIRM_PAYMENT", paymentMethodId: pmId })}
        onBack={() => dispatch({ type: "GO_BACK" })}
      />;
    case "confirmation":
      return <OrderConfirmation orderId={state.orderId} delivery={state.estimatedDelivery} />;
    case "error":
      return <CheckoutErrorView error={state.error} onRetry={() => dispatch({ type: "RETRY" })} />;
  }
}
```

## Type-Safe Event System

```typescript
// Domain events with discriminated unions
type DomainEvent =
  | { kind: "user.created"; userId: UserId; email: string; timestamp: number }
  | { kind: "user.verified"; userId: UserId; timestamp: number }
  | { kind: "order.placed"; orderId: OrderId; userId: UserId; total: number; timestamp: number }
  | { kind: "order.shipped"; orderId: OrderId; trackingNumber: string; timestamp: number }
  | { kind: "order.delivered"; orderId: OrderId; timestamp: number };

// Type-safe event handler registry
type EventHandler<E extends DomainEvent["kind"]> = (
  event: Extract<DomainEvent, { kind: E }>
) => Promise<void>;

class EventBus {
  private handlers = new Map<string, Array<(event: DomainEvent) => Promise<void>>>();

  on<E extends DomainEvent["kind"]>(kind: E, handler: EventHandler<E>): () => void {
    const existing = this.handlers.get(kind) ?? [];
    existing.push(handler as (event: DomainEvent) => Promise<void>);
    this.handlers.set(kind, existing);
    return () => {
      const arr = this.handlers.get(kind);
      if (arr) this.handlers.set(kind, arr.filter((h) => h !== handler));
    };
  }

  async emit(event: DomainEvent): Promise<void> {
    const handlers = this.handlers.get(event.kind) ?? [];
    await Promise.allSettled(handlers.map((h) => h(event)));
  }
}

// Usage — handler receives the correctly narrowed type
const bus = new EventBus();
bus.on("order.placed", async (event) => {
  // event is { kind: "order.placed"; orderId: OrderId; userId: UserId; total: number; timestamp: number }
  console.log(`Order ${event.orderId} placed by ${event.userId} for $${event.total}`);
});
```

## Common Pitfalls

1. **Using optional fields instead of unions**: `{ data?: T; error?: E; loading?: boolean }` allows `{ data: x, error: y, loading: true }` — an impossible state. Discriminated unions prevent this.
2. **Forgetting `as const`**: If the discriminant comes from a variable (`const status = "idle"`), TypeScript infers `string` not `"idle"`. Use `as const` or inline the literal.
3. **Default branches hiding bugs**: Using `default: return state` in a switch silently swallows new states added later. Prefer the `assertNever` pattern for exhaustiveness.
''',
    ),
    (
        "typescript/production",
        r'''Show how to build recursive types in TypeScript for nested data structures. Include JSON types, tree structures, and deeply nested path accessors.''',
        r'''# Recursive Types for Nested Data Structures

Recursive types reference themselves in their definition, letting you model arbitrarily nested data: JSON values, file trees, configuration objects, and deeply nested path accessors.

## JSON Type

```typescript
// The canonical recursive type — models any valid JSON value
type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

// Type-safe JSON parse wrapper
function parseJson(text: string): JsonValue {
  return JSON.parse(text) as JsonValue;
}

// Constrain to JSON-serializable types
type JsonSerializable<T> = T extends JsonValue ? T : never;

function sendToApi<T extends JsonValue>(endpoint: string, body: T): Promise<Response> {
  return fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
```

## Tree Structures

```typescript
// Generic tree node
interface TreeNode<T> {
  value: T;
  children: TreeNode<T>[];
}

// File system tree
type FileSystemNode =
  | { kind: "file"; name: string; size: number; mimeType: string }
  | { kind: "directory"; name: string; children: FileSystemNode[] };

// Type-safe tree operations
function findInTree<T>(
  node: TreeNode<T>,
  predicate: (value: T) => boolean
): TreeNode<T> | null {
  if (predicate(node.value)) return node;
  for (const child of node.children) {
    const found = findInTree(child, predicate);
    if (found) return found;
  }
  return null;
}

function mapTree<T, U>(node: TreeNode<T>, fn: (value: T) => U): TreeNode<U> {
  return {
    value: fn(node.value),
    children: node.children.map((child) => mapTree(child, fn)),
  };
}

// Flatten a tree to array with depth info
function flattenTree<T>(
  node: TreeNode<T>,
  depth: number = 0
): Array<{ value: T; depth: number }> {
  return [
    { value: node.value, depth },
    ...node.children.flatMap((child) => flattenTree(child, depth + 1)),
  ];
}

// Production example: comment thread
interface Comment {
  id: string;
  authorId: string;
  body: string;
  createdAt: Date;
  replies: Comment[]; // Recursive!
}

function countTotalReplies(comment: Comment): number {
  return comment.replies.reduce(
    (sum, reply) => sum + 1 + countTotalReplies(reply),
    0
  );
}
```

## Deep Path Accessor Type

```typescript
// Given a nested object type, derive all valid dot-separated paths
type DeepPaths<T, Prefix extends string = ""> = T extends object
  ? {
      [K in keyof T & string]: T[K] extends object
        ? `${Prefix}${K}` | DeepPaths<T[K], `${Prefix}${K}.`>
        : `${Prefix}${K}`;
    }[keyof T & string]
  : never;

// Get the type at a given path
type DeepValue<T, P extends string> =
  P extends `${infer Head}.${infer Tail}`
    ? Head extends keyof T
      ? DeepValue<T[Head], Tail>
      : never
    : P extends keyof T
      ? T[P]
      : never;

// Example schema
interface AppConfig {
  database: {
    host: string;
    port: number;
    credentials: {
      username: string;
      password: string;
    };
  };
  cache: {
    ttl: number;
    maxSize: number;
  };
  features: {
    darkMode: boolean;
    beta: {
      newCheckout: boolean;
      aiSearch: boolean;
    };
  };
}

// All valid paths
type ConfigPath = DeepPaths<AppConfig>;
// "database" | "database.host" | "database.port" | "database.credentials" |
// "database.credentials.username" | "database.credentials.password" |
// "cache" | "cache.ttl" | "cache.maxSize" | "features" | "features.darkMode" |
// "features.beta" | "features.beta.newCheckout" | "features.beta.aiSearch"

// Type-safe getter
function getConfig<P extends DeepPaths<AppConfig>>(
  config: AppConfig,
  path: P
): DeepValue<AppConfig, P> {
  const keys = (path as string).split(".");
  let result: unknown = config;
  for (const key of keys) {
    result = (result as Record<string, unknown>)[key];
  }
  return result as DeepValue<AppConfig, P>;
}

// Usage — return type is inferred correctly
const host = getConfig(config, "database.host"); // string
const port = getConfig(config, "database.port"); // number
const darkMode = getConfig(config, "features.darkMode"); // boolean
// getConfig(config, "database.nonexistent"); // Error: not assignable to DeepPaths<AppConfig>
```

## Recursive Schema Validation

```typescript
// Recursive type for a form validation schema
type ValidationRule<T> = {
  validate: (value: T) => boolean;
  message: string;
};

type ValidationSchema<T> = {
  [K in keyof T]?: T[K] extends object
    ? ValidationSchema<T[K]> | ValidationRule<T[K]>[] // Recurse into nested objects
    : ValidationRule<T[K]>[];
};

// Example
const configSchema: ValidationSchema<AppConfig> = {
  database: {
    host: [
      { validate: (v) => v.length > 0, message: "Host is required" },
      { validate: (v) => !v.includes(" "), message: "Host cannot contain spaces" },
    ],
    port: [
      { validate: (v) => v >= 1 && v <= 65535, message: "Port must be 1-65535" },
    ],
    credentials: {
      password: [
        { validate: (v) => v.length >= 12, message: "Password must be 12+ chars" },
      ],
    },
  },
};

// Recursive validator
function validateRecursive<T extends Record<string, unknown>>(
  data: T,
  schema: ValidationSchema<T>,
  path: string = ""
): string[] {
  const errors: string[] = [];

  for (const key of Object.keys(schema) as Array<keyof T & string>) {
    const rules = schema[key];
    const value = data[key];
    const fullPath = path ? `${path}.${key}` : key;

    if (Array.isArray(rules)) {
      for (const rule of rules as ValidationRule<unknown>[]) {
        if (!rule.validate(value)) {
          errors.push(`${fullPath}: ${rule.message}`);
        }
      }
    } else if (rules && typeof rules === "object" && typeof value === "object" && value !== null) {
      errors.push(
        ...validateRecursive(
          value as Record<string, unknown>,
          rules as ValidationSchema<Record<string, unknown>>,
          fullPath
        )
      );
    }
  }

  return errors;
}
```

## Common Pitfalls

1. **Infinite recursion**: TypeScript limits recursive type instantiation depth. `DeepPaths` works for 4-5 levels; beyond that, add a depth counter: `type DeepPaths<T, Prefix, Depth extends unknown[] = []> = Depth["length"] extends 5 ? never : ...`
2. **Performance**: Recursive types over large interfaces generate huge unions. Use them for config/schema types (dozens of fields), not for types with hundreds of keys.
3. **`readonly` arrays**: `readonly T[]` and `T[]` are different. Use `ReadonlyArray<TreeNode<T>>` for immutable trees; otherwise tree operations that push/splice will fail to type-check.

Recursive types let you model reality — data is nested, and your types should be too.
''',
    ),
]
