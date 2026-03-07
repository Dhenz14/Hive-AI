"""
Batch P1206 -- Advanced TypeScript patterns: builder pattern, dependency
injection, type-safe event emitter, branded types, variance.
Target: JS/TS rebalancing. 2 thinking + 3 direct pairs.
"""

pairs = [
    # --- 1. thinking: builder pattern ---
    {
        "instruction": r'''How do I implement a type-safe builder pattern in TypeScript where the compiler enforces that all required fields are set before build() can be called?''',
        "output": r'''<think>
Use a generic type parameter that tracks which fields have been set.
Each setter returns a builder with that field added to the phantom type.
The build() method is only available when the phantom type satisfies
all required fields. This turns runtime checks into compile errors.
</think>

Track set fields in a generic parameter. `build()` is only callable when all required fields are present:

```typescript
interface QueryConfig {
  table: string;
  columns: string[];
  where: string;
  limit: number;
}

type RequiredFields = "table" | "columns";

class QueryBuilder<Set extends string = never> {
  private config: Partial<QueryConfig> = {};

  table(name: string): QueryBuilder<Set | "table"> {
    this.config.table = name;
    return this as any;
  }

  columns(...cols: string[]): QueryBuilder<Set | "columns"> {
    this.config.columns = cols;
    return this as any;
  }

  where(clause: string): QueryBuilder<Set | "where"> {
    this.config.where = clause;
    return this as any;
  }

  limit(n: number): QueryBuilder<Set | "limit"> {
    this.config.limit = n;
    return this as any;
  }

  build(
    this: QueryBuilder<Set & RequiredFields extends RequiredFields ? Set : never>
  ): QueryConfig {
    return this.config as QueryConfig;
  }
}

// Works -- required fields set
const q = new QueryBuilder()
  .table("users")
  .columns("id", "name")
  .where("active = true")
  .build();

// Compile error -- missing .columns()
// new QueryBuilder().table("users").build();
```

The generic `Set` accumulates field names as a union. The conditional type on `build()` ensures it only resolves when all required fields are present.'''
    },

    # --- 2. direct: dependency injection ---
    {
        "instruction": r'''Implement a simple TypeScript dependency injection container without decorators.''',
        "output": r'''A lightweight DI container using token-based registration and type inference:

```typescript
type Token<T> = { __type: T; key: string };

function createToken<T>(key: string): Token<T> {
  return { key } as Token<T>;
}

class Container {
  private factories = new Map<string, () => unknown>();
  private singletons = new Map<string, unknown>();

  register<T>(token: Token<T>, factory: (c: Container) => T): void {
    this.factories.set(token.key, () => factory(this));
  }

  singleton<T>(token: Token<T>, factory: (c: Container) => T): void {
    this.factories.set(token.key, () => {
      if (!this.singletons.has(token.key)) {
        this.singletons.set(token.key, factory(this));
      }
      return this.singletons.get(token.key);
    });
  }

  resolve<T>(token: Token<T>): T {
    const factory = this.factories.get(token.key);
    if (!factory) throw new Error(`No registration: ${token.key}`);
    return factory() as T;
  }
}

interface Logger { log(msg: string): void; }
interface UserService { getUser(id: string): Promise<unknown>; }

const LOGGER = createToken<Logger>("Logger");
const USER_SVC = createToken<UserService>("UserService");

const container = new Container();
container.singleton(LOGGER, () => ({
  log: (msg: string) => console.log(`[LOG] ${msg}`),
}));
container.register(USER_SVC, (c) => ({
  getUser: async (id) => {
    c.resolve(LOGGER).log(`Fetching user ${id}`);
    return { id, name: "Alice" };
  },
}));

const svc = container.resolve(USER_SVC); // typed as UserService
```

The `Token<T>` pattern carries type information through the container without decorators or reflect-metadata.'''
    },

    # --- 3. direct: type-safe event emitter ---
    {
        "instruction": r'''Build a type-safe event emitter in TypeScript where event names and their payload types are enforced at compile time.''',
        "output": r'''Use a generic event map to enforce payload types per event name:

```typescript
type EventMap = Record<string, unknown>;

class TypedEmitter<Events extends EventMap> {
  private listeners = new Map<keyof Events, Set<Function>>();

  on<E extends keyof Events>(
    event: E, cb: (payload: Events[E]) => void
  ): () => void {
    if (!this.listeners.has(event)) this.listeners.set(event, new Set());
    this.listeners.get(event)!.add(cb);
    return () => { this.listeners.get(event)?.delete(cb); };
  }

  emit<E extends keyof Events>(event: E, payload: Events[E]): void {
    this.listeners.get(event)?.forEach((cb) => (cb as any)(payload));
  }

  once<E extends keyof Events>(
    event: E, cb: (payload: Events[E]) => void
  ): void {
    const unsub = this.on(event, (p) => { unsub(); cb(p); });
  }
}

interface AppEvents {
  "user:login": { userId: string; timestamp: number };
  "user:logout": { userId: string };
  "order:created": { orderId: string; total: number };
}

const bus = new TypedEmitter<AppEvents>();

bus.on("user:login", (p) => {
  console.log(p.userId);    // string -- autocomplete works
  console.log(p.timestamp); // number
});

bus.emit("order:created", { orderId: "abc", total: 99.99 });
// bus.emit("order:created", { orderId: "abc" }); // compile error
// bus.emit("unknown", {}); // compile error
```

The `Events` generic constrains both `on()` and `emit()` so the compiler catches mismatched event names and payloads at compile time.'''
    },

    # --- 4. thinking: branded types ---
    {
        "instruction": r'''What are branded types in TypeScript and when should I use them? Show practical examples.''',
        "output": r'''<think>
Branded types solve a structural typing problem: "userId" and "orderId"
are both strings, but swapping them is a bug. Branding adds a phantom
property making them incompatible. The brand is erased at runtime --
zero overhead. I should show the brand utility, smart constructors
with validation, and practical usage.
</think>

Branded types make structurally identical types incompatible to prevent mixing them up:

```typescript
declare const __brand: unique symbol;
type Brand<T, B extends string> = T & { readonly [__brand]: B };

type UserId = Brand<string, "UserId">;
type OrderId = Brand<string, "OrderId">;
type Email = Brand<string, "Email">;
type PositiveInt = Brand<number, "PositiveInt">;

// Smart constructors -- validate and brand
function userId(id: string): UserId {
  if (!id.match(/^usr_[a-z0-9]{12}$/)) {
    throw new Error("Invalid user ID format");
  }
  return id as UserId;
}

function email(value: string): Email {
  if (!value.includes("@")) throw new Error("Invalid email");
  return value.toLowerCase() as Email;
}

function positiveInt(n: number): PositiveInt {
  if (!Number.isInteger(n) || n <= 0) throw new Error("Must be positive int");
  return n as PositiveInt;
}

// Functions require specific branded types
function getUser(id: UserId): Promise<unknown> {
  return fetch(`/api/users/${id}`).then((r) => r.json());
}

const uid = userId("usr_abc123def456");
const oid = "ord_xyz" as OrderId;

getUser(uid);          // OK
// getUser(oid);       // compile error -- OrderId is not UserId
// getUser("raw");     // compile error -- string is not UserId

// Branded types still work as their base type
const upper: string = uid.toUpperCase(); // OK
```

Use branded types when mixing up same-shaped values causes bugs: IDs, currencies, validated strings. Zero runtime overhead.'''
    },

    # --- 5. direct: variance annotations ---
    {
        "instruction": r'''Explain TypeScript variance annotations (in/out keywords) with examples. When do they matter?''',
        "output": r'''TypeScript 4.7 added explicit variance annotations for generic type parameters:

```typescript
// out = covariant (producer) -- T only in output positions
interface ReadonlyBox<out T> { get(): T; }

// in = contravariant (consumer) -- T only in input positions
interface Writer<in T> { write(value: T): void; }

// in out = invariant -- T in both positions
interface MutableBox<in out T> { get(): T; set(value: T): void; }

// Covariance: safe for reading
declare let strBox: ReadonlyBox<string>;
declare let unkBox: ReadonlyBox<unknown>;
unkBox = strBox; // OK -- string extends unknown

// Contravariance: safe for writing
declare let strWriter: Writer<string>;
declare let unkWriter: Writer<unknown>;
strWriter = unkWriter; // OK -- accepts unknown, so accepts string

// Invariance: neither direction safe
declare let strMut: MutableBox<string>;
declare let unkMut: MutableBox<unknown>;
// unkMut = strMut; // Error -- set(unknown) breaks string box
// strMut = unkMut; // Error -- get() returns unknown not string

// Catch misuse at declaration site
// interface Bad<out T> { accept(value: T): void; } // Error!

// Performance: with annotations, TS skips structural comparison
// and uses declared variance. Speeds up compilation in large codebases.
```

Use `out` for producers (iterators, readonly collections). Use `in` for consumers (comparators, writers). Use `in out` for types that do both.'''
    },
]
