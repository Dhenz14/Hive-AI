"""TypeScript — advanced type patterns, utility types, and type-level programming."""

PAIRS = [
    (
        "typescript/advanced-types",
        "Show advanced TypeScript patterns: conditional types, mapped types, template literals, and type inference.",
        """Advanced TypeScript type patterns:

```typescript
// --- Conditional types ---

type IsString<T> = T extends string ? true : false;
// IsString<"hello"> = true
// IsString<42> = false

// Extract / Exclude (built-in)
type OnlyStrings = Extract<string | number | boolean, string>;  // string
type NoStrings = Exclude<string | number | boolean, string>;    // number | boolean

// Infer keyword (extract from pattern)
type ReturnType<T> = T extends (...args: any[]) => infer R ? R : never;
type ArrayElement<T> = T extends (infer E)[] ? E : never;

type UnwrapPromise<T> = T extends Promise<infer U> ? UnwrapPromise<U> : T;
// UnwrapPromise<Promise<Promise<string>>> = string


// --- Mapped types ---

type Readonly<T> = { readonly [K in keyof T]: T[K] };
type Optional<T> = { [K in keyof T]?: T[K] };
type Nullable<T> = { [K in keyof T]: T[K] | null };

// Remap keys with `as`
type Getters<T> = {
  [K in keyof T as `get${Capitalize<string & K>}`]: () => T[K];
};

interface User {
  name: string;
  age: number;
}
// Getters<User> = { getName: () => string; getAge: () => number }

// Filter keys by value type
type StringKeys<T> = {
  [K in keyof T as T[K] extends string ? K : never]: T[K];
};
// StringKeys<User> = { name: string }


// --- Template literal types ---

type EventName = `on${Capitalize<"click" | "focus" | "blur">}`;
// "onClick" | "onFocus" | "onBlur"

type HTTPMethod = "GET" | "POST" | "PUT" | "DELETE";
type APIRoute = `/${string}`;
type Endpoint = `${HTTPMethod} ${APIRoute}`;
// "GET /users" | "POST /orders" etc.

// Parse route params from string
type ExtractParams<T extends string> =
  T extends `${infer _}:${infer Param}/${infer Rest}`
    ? { [K in Param | keyof ExtractParams<Rest>]: string }
    : T extends `${infer _}:${infer Param}`
      ? { [K in Param]: string }
      : {};

// ExtractParams<"/users/:id/posts/:postId"> = { id: string; postId: string }


// --- Discriminated unions ---

type Result<T, E = Error> =
  | { success: true; data: T }
  | { success: false; error: E };

function handleResult(result: Result<User>) {
  if (result.success) {
    console.log(result.data.name); // TypeScript knows data exists
  } else {
    console.error(result.error);   // TypeScript knows error exists
  }
}

// Exhaustive switch
type Shape =
  | { kind: "circle"; radius: number }
  | { kind: "rect"; width: number; height: number }
  | { kind: "triangle"; base: number; height: number };

function area(shape: Shape): number {
  switch (shape.kind) {
    case "circle": return Math.PI * shape.radius ** 2;
    case "rect": return shape.width * shape.height;
    case "triangle": return 0.5 * shape.base * shape.height;
    default:
      const _exhaustive: never = shape; // Compile error if case missing
      return _exhaustive;
  }
}


// --- Branded/opaque types ---

type Brand<T, B extends string> = T & { __brand: B };

type UserId = Brand<string, "UserId">;
type OrderId = Brand<string, "OrderId">;

function createUserId(id: string): UserId {
  return id as UserId;
}

function getUser(id: UserId): User { /* ... */ }

// getUser("raw-string");           // Error!
// getUser(createUserId("abc123")); // OK


// --- Builder pattern with types ---

type Builder<T, Built extends keyof T = never> = {
  [K in Exclude<keyof T, Built>]-?: (
    value: T[K]
  ) => Builder<T, Built | K>;
} & (keyof T extends Built
  ? { build: () => T }
  : {});

// All required fields must be set before build() is available


// --- Utility type composition ---

type DeepPartial<T> = {
  [K in keyof T]?: T[K] extends object ? DeepPartial<T[K]> : T[K];
};

type DeepReadonly<T> = {
  readonly [K in keyof T]: T[K] extends object ? DeepReadonly<T[K]> : T[K];
};

type RequireAtLeastOne<T> = {
  [K in keyof T]-?: Required<Pick<T, K>> & Partial<Pick<T, Exclude<keyof T, K>>>;
}[keyof T];
```

TypeScript type patterns:
1. **`infer`** — extract types from patterns (return types, array elements)
2. **Mapped types with `as`** — transform/filter keys (getters, string keys only)
3. **Template literal types** — type-safe string patterns and route parsing
4. **Discriminated unions** — `kind` field enables exhaustive pattern matching
5. **Branded types** — prevent mixing `UserId` and `OrderId` at compile time"""
    ),
    (
        "typescript/type-safe-apis",
        "Show TypeScript patterns for type-safe API layers: Zod validation, type-safe fetch, and generic CRUD.",
        """Type-safe API patterns:

```typescript
import { z } from 'zod';

// --- Zod schemas (runtime validation + type inference) ---

const UserSchema = z.object({
  id: z.string().uuid(),
  name: z.string().min(1).max(100),
  email: z.string().email(),
  role: z.enum(["admin", "user", "viewer"]),
  metadata: z.record(z.string(), z.unknown()).optional(),
  createdAt: z.string().datetime(),
});

const CreateUserSchema = UserSchema.omit({ id: true, createdAt: true });
const UpdateUserSchema = CreateUserSchema.partial();  // All fields optional
const UserListSchema = z.array(UserSchema);

// Infer TypeScript types from schemas
type User = z.infer<typeof UserSchema>;
type CreateUser = z.infer<typeof CreateUserSchema>;
type UpdateUser = z.infer<typeof UpdateUserSchema>;


// --- Type-safe fetch wrapper ---

class ApiError extends Error {
  constructor(
    public status: number,
    public body: unknown,
    message?: string,
  ) {
    super(message || `API error: ${status}`);
  }
}

async function typedFetch<T>(
  url: string,
  schema: z.ZodSchema<T>,
  options?: RequestInit,
): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!res.ok) {
    throw new ApiError(res.status, await res.json().catch(() => null));
  }

  const data = await res.json();
  return schema.parse(data); // Validate response at runtime
}


// --- Generic CRUD client ---

interface CrudClient<T, CreateDTO, UpdateDTO> {
  list(params?: Record<string, string>): Promise<T[]>;
  get(id: string): Promise<T>;
  create(data: CreateDTO): Promise<T>;
  update(id: string, data: UpdateDTO): Promise<T>;
  delete(id: string): Promise<void>;
}

function createCrudClient<
  T,
  CreateDTO,
  UpdateDTO,
>(
  baseUrl: string,
  schemas: {
    item: z.ZodSchema<T>;
    list: z.ZodSchema<T[]>;
    createInput: z.ZodSchema<CreateDTO>;
  },
): CrudClient<T, CreateDTO, UpdateDTO> {
  return {
    async list(params) {
      const query = params
        ? '?' + new URLSearchParams(params).toString()
        : '';
      return typedFetch(`${baseUrl}${query}`, schemas.list);
    },

    async get(id) {
      return typedFetch(`${baseUrl}/${id}`, schemas.item);
    },

    async create(data) {
      const validated = schemas.createInput.parse(data);
      return typedFetch(`${baseUrl}`, schemas.item, {
        method: 'POST',
        body: JSON.stringify(validated),
      });
    },

    async update(id, data) {
      return typedFetch(`${baseUrl}/${id}`, schemas.item, {
        method: 'PATCH',
        body: JSON.stringify(data),
      });
    },

    async delete(id) {
      await fetch(`${baseUrl}/${id}`, { method: 'DELETE' });
    },
  };
}

// Usage:
const users = createCrudClient<User, CreateUser, UpdateUser>(
  '/api/users',
  {
    item: UserSchema,
    list: UserListSchema,
    createInput: CreateUserSchema,
  },
);

// Fully typed:
// const user = await users.create({ name: "Alice", email: "...", role: "user" });
// user.id   // string
// user.role // "admin" | "user" | "viewer"


// --- Type-safe query params ---

const SearchParamsSchema = z.object({
  q: z.string().optional(),
  page: z.coerce.number().int().positive().default(1),
  limit: z.coerce.number().int().min(1).max(100).default(20),
  sort: z.enum(["name", "date", "relevance"]).default("relevance"),
  order: z.enum(["asc", "desc"]).default("desc"),
});

type SearchParams = z.infer<typeof SearchParamsSchema>;

function parseSearchParams(url: URL): SearchParams {
  const raw = Object.fromEntries(url.searchParams);
  return SearchParamsSchema.parse(raw);
}


// --- Type-safe environment variables ---

const EnvSchema = z.object({
  DATABASE_URL: z.string().url(),
  JWT_SECRET: z.string().min(32),
  PORT: z.coerce.number().default(3000),
  NODE_ENV: z.enum(["development", "production", "test"]).default("development"),
  LOG_LEVEL: z.enum(["debug", "info", "warn", "error"]).default("info"),
});

export const env = EnvSchema.parse(process.env);
// env.PORT is number (coerced from string)
// env.NODE_ENV is "development" | "production" | "test"
```

Type-safe API patterns:
1. **Zod schemas** — single source of truth for runtime validation + TypeScript types
2. **`z.infer<typeof Schema>`** — derive TypeScript types from Zod schemas
3. **`typedFetch()`** — validates API responses against schema at runtime
4. **Generic CRUD** — reusable client with full type safety per resource
5. **`z.coerce.number()`** — parse string query params to numbers safely"""
    ),
    (
        "typescript/utility-patterns",
        "Show TypeScript utility patterns: type guards, assertion functions, pattern matching, and safe access.",
        """TypeScript utility patterns:

```typescript
// --- Type guards ---

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isUser(value: unknown): value is User {
  return (
    typeof value === "object" &&
    value !== null &&
    "id" in value &&
    "name" in value &&
    "email" in value
  );
}

// Usage in narrowing:
function process(input: unknown) {
  if (isUser(input)) {
    console.log(input.name); // TypeScript knows it's User
  }
}

// Array type guard
function isNonEmpty<T>(arr: T[]): arr is [T, ...T[]] {
  return arr.length > 0;
}


// --- Assertion functions ---

function assertDefined<T>(
  value: T | null | undefined,
  message?: string,
): asserts value is T {
  if (value === null || value === undefined) {
    throw new Error(message || "Expected value to be defined");
  }
}

function assertNever(value: never): never {
  throw new Error(`Unexpected value: ${value}`);
}

// Usage:
// const user = await findUser(id);
// assertDefined(user, `User ${id} not found`);
// user.name // TypeScript knows user is non-null


// --- Safe object access ---

function getNestedValue<T>(
  obj: Record<string, any>,
  path: string,
  fallback?: T,
): T | undefined {
  const keys = path.split(".");
  let current: any = obj;

  for (const key of keys) {
    if (current == null) return fallback;
    current = current[key];
  }

  return (current as T) ?? fallback;
}

// Or use optional chaining:
// const city = user?.address?.city ?? "Unknown";


// --- Exhaustive pattern matching ---

type Action =
  | { type: "ADD"; payload: { item: string } }
  | { type: "REMOVE"; payload: { id: string } }
  | { type: "CLEAR" };

function match<T extends { type: string }, R>(
  action: T,
  handlers: { [K in T["type"]]: (action: Extract<T, { type: K }>) => R },
): R {
  const handler = handlers[action.type as T["type"]];
  return handler(action as any);
}

// Usage:
const result = match(action, {
  ADD: (a) => `Added ${a.payload.item}`,
  REMOVE: (a) => `Removed ${a.payload.id}`,
  CLEAR: () => "Cleared all",
});


// --- Pipe / compose ---

type Fn<A = any, B = any> = (a: A) => B;

function pipe<A, B>(fn1: Fn<A, B>): Fn<A, B>;
function pipe<A, B, C>(fn1: Fn<A, B>, fn2: Fn<B, C>): Fn<A, C>;
function pipe<A, B, C, D>(
  fn1: Fn<A, B>, fn2: Fn<B, C>, fn3: Fn<C, D>,
): Fn<A, D>;
function pipe(...fns: Fn[]): Fn {
  return (arg) => fns.reduce((acc, fn) => fn(acc), arg);
}

const processUser = pipe(
  (id: string) => fetchUser(id),       // string → Promise<User>
  (user) => user.name,                   // User → string
  (name) => name.toUpperCase(),          // string → string
);


// --- Type-safe event emitter ---

type EventMap = {
  "user:login": { userId: string; timestamp: number };
  "user:logout": { userId: string };
  "error": { message: string; code: number };
};

class TypedEmitter<Events extends Record<string, any>> {
  private handlers = new Map<string, Set<Function>>();

  on<K extends keyof Events>(
    event: K,
    handler: (payload: Events[K]) => void,
  ): () => void {
    const set = this.handlers.get(event as string) || new Set();
    set.add(handler);
    this.handlers.set(event as string, set);
    return () => set.delete(handler); // Unsubscribe function
  }

  emit<K extends keyof Events>(event: K, payload: Events[K]): void {
    this.handlers.get(event as string)?.forEach((fn) => fn(payload));
  }
}

const emitter = new TypedEmitter<EventMap>();
emitter.on("user:login", ({ userId }) => {
  // userId is string (typed!)
});
emitter.emit("user:login", { userId: "abc", timestamp: Date.now() });
// emitter.emit("user:login", { wrong: true }); // Type error!
```

TypeScript utility patterns:
1. **Type guards** — `value is Type` narrows types in control flow
2. **Assertion functions** — `asserts value is T` for throw-on-invalid
3. **Exhaustive matching** — compile error if handler missing for union member
4. **Typed event emitter** — event names and payloads checked at compile time
5. **`pipe()`** — compose functions with type-safe chaining"""
    ),
]
