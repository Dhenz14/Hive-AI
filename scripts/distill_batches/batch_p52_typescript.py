"""TypeScript — advanced types, utility types, patterns, and type-level programming."""

PAIRS = [
    (
        "typescript/advanced-types",
        "Show advanced TypeScript type patterns: conditional types, mapped types, template literals, and type guards.",
        '''Advanced TypeScript type patterns:

```typescript
// --- Conditional types ---

type IsString<T> = T extends string ? true : false;
type A = IsString<"hello">;  // true
type B = IsString<42>;       // false

// Extract return type of async functions
type AsyncReturnType<T extends (...args: any[]) => Promise<any>> =
  T extends (...args: any[]) => Promise<infer R> ? R : never;

type UserData = AsyncReturnType<typeof fetchUser>;  // User


// --- Mapped types ---

// Make all properties optional and nullable
type Nullable<T> = { [K in keyof T]: T[K] | null };

// Make specific keys required
type RequireKeys<T, K extends keyof T> =
  Omit<T, K> & Required<Pick<T, K>>;

// Deep readonly
type DeepReadonly<T> = {
  readonly [K in keyof T]: T[K] extends object
    ? DeepReadonly<T[K]>
    : T[K];
};

// Deep partial
type DeepPartial<T> = {
  [K in keyof T]?: T[K] extends object
    ? DeepPartial<T[K]>
    : T[K];
};


// --- Template literal types ---

type HTTPMethod = "GET" | "POST" | "PUT" | "DELETE" | "PATCH";
type APIRoute = `/api/${string}`;
type EventName = `on${Capitalize<string>}`;

// Generate getter names from object keys
type Getters<T> = {
  [K in keyof T as `get${Capitalize<string & K>}`]: () => T[K];
};

interface User {
  name: string;
  age: number;
  email: string;
}

type UserGetters = Getters<User>;
// { getName: () => string; getAge: () => number; getEmail: () => string }


// --- Discriminated unions ---

type Result<T, E = Error> =
  | { ok: true; value: T }
  | { ok: false; error: E };

function divide(a: number, b: number): Result<number, string> {
  if (b === 0) return { ok: false, error: "Division by zero" };
  return { ok: true, value: a / b };
}

const result = divide(10, 2);
if (result.ok) {
  console.log(result.value);  // TypeScript knows value exists
} else {
  console.log(result.error);  // TypeScript knows error exists
}


// --- Type guards ---

interface Dog { type: "dog"; bark(): void }
interface Cat { type: "cat"; meow(): void }
interface Fish { type: "fish"; swim(): void }
type Animal = Dog | Cat | Fish;

function isDog(animal: Animal): animal is Dog {
  return animal.type === "dog";
}

// Exhaustive type checking
function handleAnimal(animal: Animal): string {
  switch (animal.type) {
    case "dog": return "Woof!";
    case "cat": return "Meow!";
    case "fish": return "Blub!";
    default: {
      const _exhaustive: never = animal;
      return _exhaustive;
    }
  }
}


// --- Branded types (nominal typing) ---

type Brand<T, B extends string> = T & { readonly __brand: B };

type USD = Brand<number, "USD">;
type EUR = Brand<number, "EUR">;
type UserID = Brand<string, "UserID">;
type OrderID = Brand<string, "OrderID">;

function usd(amount: number): USD { return amount as USD; }
function eur(amount: number): EUR { return amount as EUR; }

function addUSD(a: USD, b: USD): USD {
  return (a + b) as USD;
}

// addUSD(usd(10), eur(20));  // Type error! Can't mix currencies
addUSD(usd(10), usd(20));    // OK


// --- Utility type patterns ---

// Pick only functions from an object type
type FunctionKeys<T> = {
  [K in keyof T]: T[K] extends (...args: any[]) => any ? K : never;
}[keyof T];

// Merge two types (second overrides first)
type Merge<A, B> = Omit<A, keyof B> & B;

// Make all properties mutable
type Mutable<T> = { -readonly [K in keyof T]: T[K] };

// Extract promise value type
type Awaited<T> = T extends Promise<infer R> ? Awaited<R> : T;

// Tuple to union
type TupleToUnion<T extends readonly any[]> = T[number];
type Colors = TupleToUnion<["red", "green", "blue"]>;  // "red" | "green" | "blue"
```

TypeScript type patterns:
1. **Conditional types** — `T extends U ? X : Y` for type-level branching
2. **Mapped types** — transform all properties of a type
3. **Template literals** — string manipulation at the type level
4. **Discriminated unions** — tagged unions with exhaustive matching
5. **Branded types** — nominal typing for type-safe IDs and units'''
    ),
    (
        "typescript/patterns",
        "Show TypeScript design patterns: dependency injection, repository pattern, event emitter, and builder.",
        '''TypeScript design patterns:

```typescript
// --- Dependency injection with interfaces ---

interface Logger {
  info(message: string, data?: Record<string, unknown>): void;
  error(message: string, error?: Error): void;
}

interface UserRepository {
  findById(id: string): Promise<User | null>;
  findByEmail(email: string): Promise<User | null>;
  create(data: CreateUserDTO): Promise<User>;
  update(id: string, data: Partial<User>): Promise<User>;
  delete(id: string): Promise<void>;
}

interface EmailService {
  send(to: string, subject: string, body: string): Promise<void>;
}

// Use case with injected dependencies
class RegisterUserUseCase {
  constructor(
    private users: UserRepository,
    private email: EmailService,
    private logger: Logger,
  ) {}

  async execute(input: RegisterUserInput): Promise<User> {
    this.logger.info("Registering user", { email: input.email });

    const existing = await this.users.findByEmail(input.email);
    if (existing) {
      throw new ConflictError(`Email already registered: ${input.email}`);
    }

    const user = await this.users.create({
      email: input.email.toLowerCase(),
      name: input.name,
      passwordHash: await hashPassword(input.password),
    });

    await this.email.send(
      user.email,
      "Welcome!",
      `Hi ${user.name}, welcome to our platform!`,
    );

    this.logger.info("User registered", { userId: user.id });
    return user;
  }
}


// --- Type-safe event emitter ---

type EventMap = {
  "user:created": { userId: string; email: string };
  "user:deleted": { userId: string };
  "order:placed": { orderId: string; total: number };
  "order:shipped": { orderId: string; trackingNumber: string };
};

class TypedEventEmitter<Events extends Record<string, any>> {
  private listeners = new Map<string, Set<Function>>();

  on<E extends keyof Events>(
    event: E,
    handler: (data: Events[E]) => void,
  ): () => void {
    const handlers = this.listeners.get(event as string) ?? new Set();
    handlers.add(handler);
    this.listeners.set(event as string, handlers);

    // Return unsubscribe function
    return () => handlers.delete(handler);
  }

  emit<E extends keyof Events>(event: E, data: Events[E]): void {
    const handlers = this.listeners.get(event as string);
    handlers?.forEach((handler) => handler(data));
  }

  once<E extends keyof Events>(
    event: E,
    handler: (data: Events[E]) => void,
  ): void {
    const unsub = this.on(event, (data) => {
      handler(data);
      unsub();
    });
  }
}

const events = new TypedEventEmitter<EventMap>();

// Type-safe: TypeScript knows the data shape
events.on("user:created", ({ userId, email }) => {
  console.log(`User ${userId} created with ${email}`);
});

// events.emit("user:created", { orderId: "123" });  // Type error!
events.emit("user:created", { userId: "1", email: "a@b.com" });  // OK


// --- Builder pattern ---

class QueryBuilder<T> {
  private filters: string[] = [];
  private sortField?: string;
  private sortDir: "ASC" | "DESC" = "ASC";
  private limitVal?: number;
  private offsetVal?: number;

  where(field: keyof T & string, op: "=" | ">" | "<" | "LIKE", value: unknown): this {
    this.filters.push(`${field} ${op} ?`);
    return this;
  }

  orderBy(field: keyof T & string, direction: "ASC" | "DESC" = "ASC"): this {
    this.sortField = field;
    this.sortDir = direction;
    return this;
  }

  limit(n: number): this {
    this.limitVal = n;
    return this;
  }

  offset(n: number): this {
    this.offsetVal = n;
    return this;
  }

  build(): { sql: string; params: unknown[] } {
    let sql = "SELECT * FROM table";
    if (this.filters.length) sql += ` WHERE ${this.filters.join(" AND ")}`;
    if (this.sortField) sql += ` ORDER BY ${this.sortField} ${this.sortDir}`;
    if (this.limitVal) sql += ` LIMIT ${this.limitVal}`;
    if (this.offsetVal) sql += ` OFFSET ${this.offsetVal}`;
    return { sql, params: [] };
  }
}


// --- Middleware pattern ---

type Context = { request: Request; response?: Response; user?: User };
type Next = () => Promise<void>;
type MiddlewareFn = (ctx: Context, next: Next) => Promise<void>;

class MiddlewareStack {
  private middlewares: MiddlewareFn[] = [];

  use(fn: MiddlewareFn): this {
    this.middlewares.push(fn);
    return this;
  }

  async execute(ctx: Context): Promise<void> {
    let index = 0;
    const next = async (): Promise<void> => {
      if (index < this.middlewares.length) {
        const fn = this.middlewares[index++];
        await fn(ctx, next);
      }
    };
    await next();
  }
}

const stack = new MiddlewareStack();
stack
  .use(async (ctx, next) => {
    const start = Date.now();
    await next();
    console.log(`${ctx.request.method} took ${Date.now() - start}ms`);
  })
  .use(async (ctx, next) => {
    const token = ctx.request.headers.get("Authorization");
    if (token) ctx.user = await verifyToken(token);
    await next();
  });
```

TypeScript patterns:
1. **Interface-based DI** — depend on abstractions, inject implementations
2. **Typed events** — compile-time checked event names and payloads
3. **Builder** — `this` return type enables fluent chaining
4. **Middleware** — compose request processing as a stack
5. **Generic constraints** — `keyof T & string` for type-safe field access'''
    ),
]
"""
