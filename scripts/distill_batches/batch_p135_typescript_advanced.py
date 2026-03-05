"""Advanced TypeScript — utility types, module patterns, and type-level programming."""

PAIRS = [
    (
        "typescript/utility-types",
        "Show TypeScript utility type patterns: mapped types, conditional types, template literals, and type inference.",
        '''TypeScript utility type patterns:

```typescript
// --- Mapped types ---

// Make all properties optional recursively
type DeepPartial<T> = {
  [P in keyof T]?: T[P] extends object ? DeepPartial<T[P]> : T[P];
};

// Make specific keys required, rest optional
type RequireKeys<T, K extends keyof T> = Omit<Partial<T>, K> & Pick<T, K>;

// Usage:
interface Config {
  host: string;
  port: number;
  ssl: { cert: string; key: string };
}
type PartialConfig = DeepPartial<Config>;
// { host?: string; port?: number; ssl?: { cert?: string; key?: string } }

type MinConfig = RequireKeys<Config, "host">;
// { host: string; port?: number; ssl?: ... }


// --- Conditional types ---

// Extract return type of async functions
type AsyncReturnType<T extends (...args: any[]) => Promise<any>> =
  T extends (...args: any[]) => Promise<infer R> ? R : never;

// Usage:
async function fetchUser(id: string) { return { id, name: "Alice" }; }
type User = AsyncReturnType<typeof fetchUser>; // { id: string; name: string }


// Extract event payload type from event map
type EventPayload<
  T extends Record<string, any>,
  K extends keyof T,
> = T[K] extends (...args: infer A) => any ? A[0] : T[K];


// --- Template literal types ---

type HTTPMethod = "GET" | "POST" | "PUT" | "DELETE" | "PATCH";
type APIRoute = `/${string}`;
type Endpoint = `${HTTPMethod} ${APIRoute}`;

// "GET /users" | "POST /users" | ...

// Auto-generate event names
type ModelName = "user" | "order" | "product";
type CRUDEvent = `${ModelName}.${"created" | "updated" | "deleted"}`;
// "user.created" | "user.updated" | ... | "product.deleted"

// Snake_case to camelCase
type CamelCase<S extends string> =
  S extends `${infer P}_${infer R}`
    ? `${P}${Capitalize<CamelCase<R>>}`
    : S;

type Test = CamelCase<"user_first_name">; // "userFirstName"


// --- Discriminated unions (tagged unions) ---

type Result<T, E = Error> =
  | { ok: true; value: T }
  | { ok: false; error: E };

function divide(a: number, b: number): Result<number, string> {
  if (b === 0) return { ok: false, error: "Division by zero" };
  return { ok: true, value: a / b };
}

const result = divide(10, 3);
if (result.ok) {
  console.log(result.value); // TypeScript knows value exists
} else {
  console.log(result.error); // TypeScript knows error exists
}


// --- Builder pattern with type accumulation ---

type BuilderState = {
  host?: string;
  port?: number;
  ssl?: boolean;
};

class ServerBuilder<T extends BuilderState = {}> {
  private config: T;

  constructor(config: T = {} as T) {
    this.config = config;
  }

  host(h: string): ServerBuilder<T & { host: string }> {
    return new ServerBuilder({ ...this.config, host: h });
  }

  port(p: number): ServerBuilder<T & { port: number }> {
    return new ServerBuilder({ ...this.config, port: p });
  }

  ssl(): ServerBuilder<T & { ssl: true }> {
    return new ServerBuilder({ ...this.config, ssl: true as const });
  }

  build(this: ServerBuilder<{ host: string; port: number }>): T {
    return this.config;
  }
}

// const server = new ServerBuilder()
//   .host("localhost")
//   .port(3000)
//   .build(); // OK

// const bad = new ServerBuilder()
//   .host("localhost")
//   .build(); // Error: port is required


// --- Branded types (nominal typing) ---

type Brand<T, B extends string> = T & { readonly __brand: B };

type USD = Brand<number, "USD">;
type EUR = Brand<number, "EUR">;
type UserId = Brand<string, "UserId">;
type OrderId = Brand<string, "OrderId">;

function usd(amount: number): USD { return amount as USD; }
function eur(amount: number): EUR { return amount as EUR; }

function addUSD(a: USD, b: USD): USD {
  return (a + b) as USD;
}

// addUSD(usd(10), eur(5)); // Error! Can't mix USD and EUR
// addUSD(usd(10), usd(5)); // OK


// --- Exhaustive switch checking ---

function assertNever(x: never): never {
  throw new Error(`Unexpected value: ${x}`);
}

type Shape =
  | { kind: "circle"; radius: number }
  | { kind: "rect"; width: number; height: number }
  | { kind: "triangle"; base: number; height: number };

function area(shape: Shape): number {
  switch (shape.kind) {
    case "circle": return Math.PI * shape.radius ** 2;
    case "rect": return shape.width * shape.height;
    case "triangle": return 0.5 * shape.base * shape.height;
    default: return assertNever(shape); // Compile error if case missing
  }
}
```

TypeScript utility patterns:
1. **`DeepPartial<T>`** — recursive partial for nested config/update objects
2. **Template literal types** — type-safe string patterns like `"GET /users"`
3. **Branded types** — prevent mixing USD/EUR or UserId/OrderId at compile time
4. **Builder with type accumulation** — `.build()` only compiles when required fields set
5. **`assertNever()`** — exhaustive switch/case checking catches missing variants'''
    ),
    (
        "typescript/module-patterns",
        "Show TypeScript module and project patterns: barrel exports, dependency injection, and plugin systems.",
        '''TypeScript module and project patterns:

```typescript
// --- Barrel exports (index.ts re-exports) ---

// src/models/index.ts
export { User, type UserDTO } from "./user";
export { Order, type OrderDTO } from "./order";
export { Product, type ProductDTO } from "./product";

// Consumer: import { User, Order } from "@/models"
// NOT: import { User } from "@/models/user"


// --- Dependency injection (no framework) ---

// Define interfaces for dependencies
interface Logger {
  info(msg: string, ...args: any[]): void;
  error(msg: string, ...args: any[]): void;
}

interface UserRepository {
  findById(id: string): Promise<User | null>;
  save(user: User): Promise<void>;
}

interface EmailService {
  send(to: string, subject: string, body: string): Promise<void>;
}

// Service depends on interfaces, not implementations
class UserService {
  constructor(
    private readonly repo: UserRepository,
    private readonly email: EmailService,
    private readonly logger: Logger,
  ) {}

  async registerUser(email: string, name: string): Promise<User> {
    this.logger.info("Registering user: %s", email);

    const existing = await this.repo.findById(email);
    if (existing) throw new Error("User already exists");

    const user = new User(email, name);
    await this.repo.save(user);
    await this.email.send(email, "Welcome!", `Hello ${name}`);

    return user;
  }
}

// Composition root (wire up dependencies)
function createApp() {
  const logger = new ConsoleLogger();
  const db = new PostgresPool(process.env.DATABASE_URL!);
  const repo = new PgUserRepository(db);
  const email = new SmtpEmailService(process.env.SMTP_URL!);
  const userService = new UserService(repo, email, logger);

  return { userService, db };
}


// --- Plugin system ---

interface Plugin<TContext = any> {
  name: string;
  version: string;
  init(ctx: TContext): Promise<void>;
  destroy?(): Promise<void>;
}

class PluginManager<TContext> {
  private plugins: Map<string, Plugin<TContext>> = new Map();

  register(plugin: Plugin<TContext>): this {
    if (this.plugins.has(plugin.name)) {
      throw new Error(`Plugin "${plugin.name}" already registered`);
    }
    this.plugins.set(plugin.name, plugin);
    return this;
  }

  async initAll(ctx: TContext): Promise<void> {
    for (const [name, plugin] of this.plugins) {
      console.log(`Initializing plugin: ${name} v${plugin.version}`);
      await plugin.init(ctx);
    }
  }

  async destroyAll(): Promise<void> {
    // Destroy in reverse order
    const plugins = [...this.plugins.values()].reverse();
    for (const plugin of plugins) {
      await plugin.destroy?.();
    }
  }

  get<T extends Plugin<TContext>>(name: string): T {
    const plugin = this.plugins.get(name);
    if (!plugin) throw new Error(`Plugin "${name}" not found`);
    return plugin as T;
  }
}

// Usage:
// const manager = new PluginManager<AppContext>();
// manager.register(new AuthPlugin());
// manager.register(new CachePlugin());
// await manager.initAll(appContext);


// --- Type-safe event emitter ---

type EventMap = Record<string, any>;

class TypedEventEmitter<T extends EventMap> {
  private listeners: {
    [K in keyof T]?: Array<(payload: T[K]) => void>;
  } = {};

  on<K extends keyof T>(event: K, listener: (payload: T[K]) => void): () => void {
    const list = (this.listeners[event] ??= []);
    list.push(listener);
    return () => {
      const idx = list.indexOf(listener);
      if (idx >= 0) list.splice(idx, 1);
    };
  }

  emit<K extends keyof T>(event: K, payload: T[K]): void {
    this.listeners[event]?.forEach(fn => fn(payload));
  }
}

// Define events with typed payloads
interface AppEvents {
  "user:login": { userId: string; timestamp: Date };
  "user:logout": { userId: string };
  "order:created": { orderId: string; total: number };
}

const events = new TypedEventEmitter<AppEvents>();

events.on("user:login", ({ userId, timestamp }) => {
  // userId is string, timestamp is Date — fully typed!
  console.log(`${userId} logged in at ${timestamp}`);
});

// events.emit("user:login", { userId: "123" });
// Error: missing 'timestamp'


// --- Service container with type inference ---

type ServiceFactory<T> = () => T;

class Container {
  private factories = new Map<string, ServiceFactory<any>>();
  private instances = new Map<string, any>();

  register<T>(name: string, factory: ServiceFactory<T>): void {
    this.factories.set(name, factory);
  }

  resolve<T>(name: string): T {
    if (this.instances.has(name)) {
      return this.instances.get(name);
    }
    const factory = this.factories.get(name);
    if (!factory) throw new Error(`Service "${name}" not registered`);
    const instance = factory();
    this.instances.set(name, instance);
    return instance;
  }
}
```

TypeScript module patterns:
1. **Barrel exports** — `index.ts` re-exports for clean import paths
2. **Constructor injection** — depend on interfaces, wire in composition root
3. **Plugin system** — `register/init/destroy` lifecycle with typed context
4. **`TypedEventEmitter`** — compile-time checked event names and payloads
5. **Service container** — lazy singleton instantiation with `resolve<T>()`'''
    ),
]
"""
