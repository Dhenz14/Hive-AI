"""
Batch P4 — Advanced TypeScript: type system, decorators, monorepos,
compiler API, functional programming with Effect-TS/fp-ts.
Target quality: >0.80 per v5 scorer.
"""

PAIRS = [
    # --- 1. Advanced TypeScript Type System ---
    (
        "typescript/advanced-type-system",
        "Explain advanced TypeScript type-level programming in depth — conditional types with infer keyword, template literal types for string manipulation, mapped types with key remapping, recursive types, and type-level arithmetic. Provide practical production examples including type-safe form validation, a fully-typed API client that infers response types from route definitions, and a type-safe event emitter with payload validation.",
        r"""# Advanced TypeScript Type System: Type-Level Programming for Production Code

## Why Type-Level Programming Matters

TypeScript's type system is **Turing-complete** — it can perform arbitrary computation at the type level. This is not merely an academic curiosity; because type-level programming lets you encode business rules, API contracts, and validation logic directly into the type system, entire categories of runtime bugs become impossible. The trade-off is complexity: advanced types can be difficult to read and debug, therefore you should use them judiciously where the safety benefits justify the cognitive overhead.

**Common mistake**: Writing complex types without understanding the fundamentals. The `infer` keyword, conditional types, and mapped types are building blocks — you must master each before combining them.

## Conditional Types and the `infer` Keyword

Conditional types follow the pattern `T extends U ? X : Y`. The `infer` keyword lets you **extract** types from within a conditional check — it declares a type variable that TypeScript infers from the matched structure.

```typescript
// --- Foundation: Extracting types with infer ---

// Extract the return type of any function
type ReturnOf<T> = T extends (...args: any[]) => infer R ? R : never;

// Extract the resolved type from a Promise
type Awaited<T> = T extends Promise<infer U>
  ? U extends Promise<infer V>
    ? Awaited<V>  // Recursively unwrap nested promises
    : U
  : T;

// Extract array element type
type ElementOf<T> = T extends readonly (infer E)[] ? E : never;

// Extract the first and rest of a tuple
type Head<T extends any[]> = T extends [infer H, ...any[]] ? H : never;
type Tail<T extends any[]> = T extends [any, ...infer R] ? R : [];

// Practical: Extract parameter types from an Express-style handler
type HandlerParams<T> = T extends (
  req: infer Req,
  res: infer Res,
  next: infer Next
) => any
  ? { request: Req; response: Res; next: Next }
  : never;

// --- Distributive conditional types ---
// When T is a union, the conditional distributes over each member

type ToArray<T> = T extends any ? T[] : never;
type Result = ToArray<string | number>;
// Result = string[] | number[]  (NOT (string | number)[])

// Prevent distribution by wrapping in a tuple
type ToArrayNonDist<T> = [T] extends [any] ? T[] : never;
type Result2 = ToArrayNonDist<string | number>;
// Result2 = (string | number)[]

// --- Filtering union types ---
type ExtractStrings<T> = T extends string ? T : never;
type OnlyStrings = ExtractStrings<string | number | boolean>;
// OnlyStrings = string

// Filter object keys by value type
type KeysOfType<T, V> = {
  [K in keyof T]: T[K] extends V ? K : never;
}[keyof T];

interface User {
  id: number;
  name: string;
  email: string;
  isActive: boolean;
}

type StringKeys = KeysOfType<User, string>;
// StringKeys = "name" | "email"
```

## Template Literal Types

Template literal types let you perform **string manipulation at the type level**. Combined with conditional types, they enable parsing and transforming string-based APIs into fully typed interfaces.

```typescript
// --- String manipulation utilities ---

type Uppercase<S extends string> = intrinsic;  // built-in
type Lowercase<S extends string> = intrinsic;
type Capitalize<S extends string> = intrinsic;
type Uncapitalize<S extends string> = intrinsic;

// Split a string by a delimiter
type Split<
  S extends string,
  D extends string
> = S extends `${infer Head}${D}${infer Tail}`
  ? [Head, ...Split<Tail, D>]
  : [S];

type Parts = Split<"hello-world-foo", "-">;
// Parts = ["hello", "world", "foo"]

// Convert kebab-case to camelCase
type KebabToCamel<S extends string> =
  S extends `${infer Head}-${infer Char}${infer Tail}`
    ? `${Head}${Uppercase<Char>}${KebabToCamel<Tail>}`
    : S;

type Camelized = KebabToCamel<"background-color-red">;
// Camelized = "backgroundColorRed"

// Convert snake_case to camelCase
type SnakeToCamel<S extends string> =
  S extends `${infer Head}_${infer Char}${infer Tail}`
    ? `${Head}${Uppercase<Char>}${SnakeToCamel<Tail>}`
    : S;

// Parse URL path parameters: "/users/:id/posts/:postId" -> { id: string; postId: string }
type ParseParams<S extends string> =
  S extends `${string}:${infer Param}/${infer Rest}`
    ? { [K in Param]: string } & ParseParams<Rest>
    : S extends `${string}:${infer Param}`
      ? { [K in Param]: string }
      : {};

type UserPostParams = ParseParams<"/users/:id/posts/:postId">;
// UserPostParams = { id: string } & { postId: string }

// --- Type-safe event names with template literals ---
type EventName<T extends string> = `on${Capitalize<T>}`;
type ClickEvent = EventName<"click">;  // "onClick"

// Generate getter/setter method names from object keys
type Getters<T> = {
  [K in keyof T as `get${Capitalize<string & K>}`]: () => T[K];
};

type Setters<T> = {
  [K in keyof T as `set${Capitalize<string & K>}`]: (value: T[K]) => void;
};

interface Config {
  host: string;
  port: number;
  debug: boolean;
}

type ConfigGetters = Getters<Config>;
// { getHost: () => string; getPort: () => number; getDebug: () => boolean }
```

## Mapped Types with Key Remapping

Mapped types iterate over keys and transform both keys and values. TypeScript 4.1+ added **key remapping** via `as`, which is essential for advanced transformations.

```typescript
// --- Mapped type fundamentals ---

// Make all properties optional and nullable
type Nullable<T> = {
  [K in keyof T]: T[K] | null;
};

// Deep partial — recursively makes all properties optional
type DeepPartial<T> = T extends object
  ? { [K in keyof T]?: DeepPartial<T[K]> }
  : T;

// Deep readonly — recursively makes all properties immutable
type DeepReadonly<T> = T extends object
  ? { readonly [K in keyof T]: DeepReadonly<T[K]> }
  : T;

// --- Key remapping with `as` ---

// Remove keys that have undefined values
type RemoveUndefined<T> = {
  [K in keyof T as T[K] extends undefined ? never : K]: T[K];
};

// Prefix all keys
type Prefixed<T, P extends string> = {
  [K in keyof T as `${P}${Capitalize<string & K>}`]: T[K];
};

type PrefixedUser = Prefixed<User, "user">;
// { userId: number; userName: string; userEmail: string; userIsActive: boolean }

// --- Practical: Type-safe form validation ---

interface FormSchema {
  username: { type: "string"; minLength: 3; maxLength: 20; required: true };
  email: { type: "email"; required: true };
  age: { type: "number"; min: 18; max: 120; required: false };
  bio: { type: "string"; maxLength: 500; required: false };
}

// Extract the TypeScript type from a field schema
type FieldType<F> =
  F extends { type: "string" | "email" } ? string :
  F extends { type: "number" } ? number :
  F extends { type: "boolean" } ? boolean :
  never;

// Build the form data type — required fields are non-optional
type FormData<S> = {
  [K in keyof S as S[K] extends { required: true } ? K : never]:
    FieldType<S[K]>;
} & {
  [K in keyof S as S[K] extends { required: true } ? never : K]?:
    FieldType<S[K]>;
};

type UserFormData = FormData<FormSchema>;
// { username: string; email: string; age?: number; bio?: string }

// Build validation error types from schema
type ValidationErrors<S> = {
  [K in keyof S]?: string[];
};

type UserFormErrors = ValidationErrors<FormSchema>;
// { username?: string[]; email?: string[]; age?: string[]; bio?: string[] }

// Runtime validator that is type-safe
function createValidator<S extends Record<string, { type: string; required?: boolean }>>(
  schema: S
): (data: unknown) => data is FormData<S> {
  return (data: unknown): data is FormData<S> => {
    if (typeof data !== "object" || data === null) return false;
    const record = data as Record<string, unknown>;
    for (const [key, field] of Object.entries(schema)) {
      if (field.required && !(key in record)) return false;
      if (key in record) {
        const value = record[key];
        if (field.type === "number" && typeof value !== "number") return false;
        if ((field.type === "string" || field.type === "email") &&
            typeof value !== "string") return false;
      }
    }
    return true;
  };
}
```

## Type-Safe API Client with Route Inference

This is where type-level programming truly shines in production. By defining your API routes as a type-level schema, the client **automatically infers** request and response types — no code generation needed.

```typescript
// --- API route definition ---

interface ApiRoutes {
  "GET /users": {
    query: { page?: number; limit?: number; search?: string };
    response: { users: User[]; total: number };
  };
  "GET /users/:id": {
    params: { id: string };
    response: User;
  };
  "POST /users": {
    body: { name: string; email: string };
    response: User;
  };
  "PUT /users/:id": {
    params: { id: string };
    body: Partial<Pick<User, "name" | "email">>;
    response: User;
  };
  "DELETE /users/:id": {
    params: { id: string };
    response: { deleted: boolean };
  };
}

// Extract method and path from route key
type ExtractMethod<R extends string> =
  R extends `${infer M} ${string}` ? M : never;

type ExtractPath<R extends string> =
  R extends `${string} ${infer P}` ? P : never;

// Build the typed fetch function
type ApiRequest<R extends keyof ApiRoutes> =
  (ApiRoutes[R] extends { params: infer P } ? { params: P } : {}) &
  (ApiRoutes[R] extends { query: infer Q } ? { query: Q } : {}) &
  (ApiRoutes[R] extends { body: infer B } ? { body: B } : {});

type ApiResponse<R extends keyof ApiRoutes> = ApiRoutes[R]["response"];

class TypedApiClient {
  constructor(private baseUrl: string) {}

  async request<R extends keyof ApiRoutes>(
    route: R,
    ...args: keyof ApiRequest<R> extends never ? [] : [ApiRequest<R>]
  ): Promise<ApiResponse<R>> {
    const [method, pathTemplate] = (route as string).split(" ");
    const options = args[0] as Record<string, any> | undefined;

    // Replace path params
    let path = pathTemplate;
    if (options && "params" in options) {
      for (const [key, value] of Object.entries(
        options.params as Record<string, string>
      )) {
        path = path.replace(`:${key}`, encodeURIComponent(value));
      }
    }

    // Build query string
    const url = new URL(path, this.baseUrl);
    if (options && "query" in options) {
      for (const [key, value] of Object.entries(
        options.query as Record<string, unknown>
      )) {
        if (value !== undefined) {
          url.searchParams.set(key, String(value));
        }
      }
    }

    const response = await fetch(url.toString(), {
      method,
      headers: { "Content-Type": "application/json" },
      body: options && "body" in options
        ? JSON.stringify(options.body)
        : undefined,
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status} ${response.statusText}`);
    }

    return response.json() as Promise<ApiResponse<R>>;
  }
}

// Usage — fully type-safe, no manual type annotations needed
const api = new TypedApiClient("https://api.example.com");

// TypeScript knows the return type is { users: User[]; total: number }
const users = await api.request("GET /users", {
  query: { page: 1, limit: 10 },
});

// TypeScript knows the return type is User
const user = await api.request("GET /users/:id", {
  params: { id: "123" },
});

// TypeScript enforces the body shape
const newUser = await api.request("POST /users", {
  body: { name: "Alice", email: "alice@example.com" },
});

// Compile error: missing required params
// api.request("GET /users/:id", {});  // Error!
```

## Type-Safe Event Emitter

```typescript
// --- Event emitter with payload type safety ---

interface EventMap {
  "user:login": { userId: string; timestamp: Date };
  "user:logout": { userId: string; reason: "manual" | "timeout" };
  "order:created": { orderId: string; total: number; items: string[] };
  "order:shipped": { orderId: string; trackingNumber: string };
  "error": { code: number; message: string; stack?: string };
}

type EventHandler<T> = (payload: T) => void | Promise<void>;

class TypedEventEmitter<Events extends Record<string, any>> {
  private handlers = new Map<string, Set<Function>>();

  on<E extends keyof Events & string>(
    event: E,
    handler: EventHandler<Events[E]>
  ): () => void {
    if (!this.handlers.has(event)) {
      this.handlers.set(event, new Set());
    }
    this.handlers.get(event)!.add(handler);

    // Return unsubscribe function
    return () => {
      this.handlers.get(event)?.delete(handler);
    };
  }

  async emit<E extends keyof Events & string>(
    event: E,
    payload: Events[E]
  ): Promise<void> {
    const eventHandlers = this.handlers.get(event);
    if (!eventHandlers) return;

    const promises = [...eventHandlers].map((handler) =>
      Promise.resolve(handler(payload))
    );
    await Promise.all(promises);
  }

  once<E extends keyof Events & string>(
    event: E,
    handler: EventHandler<Events[E]>
  ): () => void {
    const unsubscribe = this.on(event, (payload) => {
      unsubscribe();
      return handler(payload);
    });
    return unsubscribe;
  }
}

// Usage — TypeScript enforces correct payloads
const emitter = new TypedEventEmitter<EventMap>();

emitter.on("user:login", (payload) => {
  // payload is typed as { userId: string; timestamp: Date }
  console.log(`User ${payload.userId} logged in at ${payload.timestamp}`);
});

// Compile error: wrong payload shape
// emitter.emit("user:login", { wrong: "field" });  // Error!

// Compile error: unknown event name
// emitter.on("nonexistent", () => {});  // Error!

// Correct usage
emitter.emit("order:created", {
  orderId: "ORD-001",
  total: 99.99,
  items: ["item-a", "item-b"],
});
```

## Summary and Key Takeaways

**Best practice**: Start with simple generic constraints and build up complexity incrementally. Every advanced type should have a clear **purpose** — if a simpler approach achieves the same safety, prefer it.

**Pitfall**: Recursive types can cause compiler slowdowns. TypeScript has a recursion depth limit (~50 levels), therefore deeply recursive types like type-level JSON parsers may hit limits in production codebases. Use `// @ts-expect-error` sparingly and document why.

The **trade-off** with type-level programming is always **safety vs. complexity**. A type-safe API client eliminates an entire class of bugs (wrong endpoint, wrong payload, wrong response parsing), however the type definitions themselves require expertise to maintain. Therefore, encapsulate complex types in utility libraries and expose simple interfaces to consumers. The most valuable patterns — `FormData<Schema>`, typed API clients, typed event emitters — pay for their complexity many times over in prevented production bugs.
""",
    ),

    # --- 2. TypeScript Decorators and Metadata ---
    (
        "typescript/decorators-metadata-di",
        "Explain TypeScript decorators in depth — compare Stage 3 TC39 decorators versus legacy experimental decorators, show how to build method, class, property, and accessor decorators with practical examples. Build a complete dependency injection container using reflect-metadata, including constructor injection, singleton vs transient scopes, circular dependency detection, and integration with a web framework. Include proper typing and test examples.",
        r"""# TypeScript Decorators and Metadata: From Fundamentals to Dependency Injection

## The Two Decorator Standards

TypeScript currently has **two incompatible decorator implementations**, which is a common source of confusion. Understanding both is essential because legacy decorators dominate existing codebases (Angular, NestJS, TypeORM), while Stage 3 decorators are the future standard.

**Best practice**: For new projects, evaluate whether your framework supports Stage 3 decorators. If not, use legacy decorators with `experimentalDecorators: true` — they are stable and well-understood despite the "experimental" label.

### Legacy Decorators (experimentalDecorators)

Legacy decorators are functions that receive the **class prototype**, the **property name**, and a **property descriptor**. They modify behavior through mutation.

```typescript
// tsconfig.json requirements for legacy decorators:
// { "experimentalDecorators": true, "emitDecoratorMetadata": true }

// --- Method Decorator ---
// Signature: (target, propertyKey, descriptor) => void | descriptor

function Log(
  target: Object,
  propertyKey: string | symbol,
  descriptor: PropertyDescriptor
): PropertyDescriptor {
  const originalMethod = descriptor.value;

  descriptor.value = function (this: any, ...args: any[]) {
    const className = target.constructor.name;
    console.log(`[${className}.${String(propertyKey)}] Called with:`, args);
    const start = performance.now();
    const result = originalMethod.apply(this, args);
    const duration = performance.now() - start;
    console.log(
      `[${className}.${String(propertyKey)}] Returned:`,
      result,
      `(${duration.toFixed(2)}ms)`
    );
    return result;
  };

  return descriptor;
}

// --- Class Decorator ---
// Signature: (constructor) => void | constructor

function Sealed(constructor: Function): void {
  Object.seal(constructor);
  Object.seal(constructor.prototype);
}

// --- Property Decorator ---
// Signature: (target, propertyKey) => void
// Note: Property decorators CANNOT access or modify the value directly.
// They are used primarily for metadata registration.

function Required(target: Object, propertyKey: string | symbol): void {
  const requiredFields: (string | symbol)[] =
    Reflect.getMetadata("required_fields", target) ?? [];
  requiredFields.push(propertyKey);
  Reflect.defineMetadata("required_fields", requiredFields, target);
}

// --- Parameter Decorator ---
// Signature: (target, propertyKey, parameterIndex) => void

function Validate(
  target: Object,
  propertyKey: string | symbol,
  parameterIndex: number
): void {
  const validatedParams: number[] =
    Reflect.getMetadata("validated_params", target, propertyKey) ?? [];
  validatedParams.push(parameterIndex);
  Reflect.defineMetadata(
    "validated_params",
    validatedParams,
    target,
    propertyKey
  );
}

// --- Usage ---
@Sealed
class UserService {
  @Required
  name: string = "";

  @Log
  findUser(@Validate id: string): { id: string; name: string } | undefined {
    // Simulated DB lookup
    if (id === "1") return { id: "1", name: "Alice" };
    return undefined;
  }
}
```

### Stage 3 Decorators (TC39 Standard)

Stage 3 decorators have a **completely different API**. They receive a `context` object instead of positional parameters, and they use `addInitializer` hooks instead of direct mutation.

```typescript
// tsconfig.json: NO experimentalDecorators flag needed (TypeScript 5.0+)

// --- Stage 3 Method Decorator ---
// Signature: (originalMethod, context) => replacementMethod | void

function log<This, Args extends any[], Return>(
  originalMethod: (this: This, ...args: Args) => Return,
  context: ClassMethodDecoratorContext<
    This,
    (this: This, ...args: Args) => Return
  >
): (this: This, ...args: Args) => Return {
  const methodName = String(context.name);

  return function (this: This, ...args: Args): Return {
    console.log(`[${methodName}] Called with:`, args);
    const result = originalMethod.call(this, ...args);
    console.log(`[${methodName}] Returned:`, result);
    return result;
  };
}

// --- Stage 3 Class Decorator ---
function sealed<T extends new (...args: any[]) => any>(
  target: T,
  context: ClassDecoratorContext<T>
): T {
  Object.seal(target);
  Object.seal(target.prototype);

  // addInitializer runs after the class is fully defined
  context.addInitializer(function () {
    console.log(`${String(context.name)} class has been sealed`);
  });

  return target;
}

// --- Stage 3 Accessor Decorator (new in Stage 3!) ---
// The `accessor` keyword creates auto-implemented get/set pairs

function clamp(min: number, max: number) {
  return function <This>(
    target: ClassAccessorDecoratorTarget<This, number>,
    context: ClassAccessorDecoratorContext<This, number>
  ): ClassAccessorDecoratorResult<This, number> {
    return {
      get(this: This): number {
        return target.get.call(this);
      },
      set(this: This, value: number): void {
        const clamped = Math.max(min, Math.min(max, value));
        target.set.call(this, clamped);
      },
      init(value: number): number {
        return Math.max(min, Math.min(max, value));
      },
    };
  };
}

// --- Usage ---
@sealed
class Sensor {
  accessor temperature = 20;

  @clamp(0, 100)
  accessor humidity = 50;

  @log
  readSensor(): { temperature: number; humidity: number } {
    return {
      temperature: this.temperature,
      humidity: this.humidity,
    };
  }
}

const sensor = new Sensor();
sensor.humidity = 150;           // Clamped to 100
console.log(sensor.humidity);    // 100
sensor.readSensor();             // Logged automatically
```

## Building a Dependency Injection Container

Dependency injection is the **killer use case** for decorators and metadata. The pattern decouples object creation from object use, making code testable and modular. However, a common pitfall is building overly complex DI systems — the container below strikes a balance between power and simplicity.

```typescript
// --- DI Container with reflect-metadata (legacy decorators) ---

import "reflect-metadata";

// --- Token system for identifying dependencies ---

type Scope = "singleton" | "transient";

interface TokenMetadata {
  scope: Scope;
  factory?: () => any;
}

const INJECT_METADATA_KEY = Symbol("inject:params");
const INJECTABLE_KEY = Symbol("injectable");

// Token for non-class dependencies (interfaces, primitives)
class InjectionToken<T> {
  constructor(public readonly name: string) {}
  // Phantom type parameter ensures type safety
  private _phantom?: T;
}

// --- Decorators ---

function Injectable(scope: Scope = "singleton"): ClassDecorator {
  return (target: Function): void => {
    Reflect.defineMetadata(INJECTABLE_KEY, { scope } as TokenMetadata, target);
  };
}

function Inject(token: InjectionToken<any> | Function) {
  return (
    target: Object,
    propertyKey: string | symbol | undefined,
    parameterIndex: number
  ): void => {
    const existingTokens: Map<number, any> =
      Reflect.getMetadata(INJECT_METADATA_KEY, target) ?? new Map();
    existingTokens.set(parameterIndex, token);
    Reflect.defineMetadata(INJECT_METADATA_KEY, existingTokens, target);
  };
}

// --- Container ---

class Container {
  private bindings = new Map<any, TokenMetadata & { implementation: any }>();
  private singletons = new Map<any, any>();
  private resolving = new Set<any>();  // Circular dependency detection

  /**
   * Register a class as injectable.
   * The class must be decorated with @Injectable.
   */
  register<T>(target: new (...args: any[]) => T): void {
    const metadata: TokenMetadata | undefined = Reflect.getMetadata(
      INJECTABLE_KEY,
      target
    );
    if (!metadata) {
      throw new Error(
        `${target.name} is not decorated with @Injectable. ` +
        `Add @Injectable() to the class declaration.`
      );
    }
    this.bindings.set(target, { ...metadata, implementation: target });
  }

  /**
   * Bind a token (interface) to a concrete implementation.
   */
  bind<T>(
    token: InjectionToken<T>,
    implementation: new (...args: any[]) => T,
    scope: Scope = "singleton"
  ): void {
    this.bindings.set(token, { scope, implementation });
  }

  /**
   * Bind a token to a factory function for custom instantiation.
   */
  bindFactory<T>(
    token: InjectionToken<T>,
    factory: () => T,
    scope: Scope = "singleton"
  ): void {
    this.bindings.set(token, { scope, factory, implementation: null });
  }

  /**
   * Resolve a dependency — the core of the DI container.
   * Uses recursive resolution for constructor parameters.
   */
  resolve<T>(token: any): T {
    // Check for circular dependencies
    if (this.resolving.has(token)) {
      const name =
        token instanceof InjectionToken ? token.name : token.name ?? "unknown";
      throw new Error(
        `Circular dependency detected while resolving: ${name}. ` +
        `Use a factory binding or restructure your dependencies.`
      );
    }

    // Return existing singleton
    if (this.singletons.has(token)) {
      return this.singletons.get(token);
    }

    const binding = this.bindings.get(token);
    if (!binding) {
      const name =
        token instanceof InjectionToken ? token.name : token.name ?? "unknown";
      throw new Error(
        `No binding found for: ${name}. ` +
        `Call container.register() or container.bind() first.`
      );
    }

    this.resolving.add(token);

    try {
      let instance: T;

      if (binding.factory) {
        instance = binding.factory();
      } else {
        // Resolve constructor parameters automatically
        const paramTypes: any[] =
          Reflect.getMetadata(
            "design:paramtypes",
            binding.implementation
          ) ?? [];
        const customTokens: Map<number, any> =
          Reflect.getMetadata(
            INJECT_METADATA_KEY,
            binding.implementation
          ) ?? new Map();

        const resolvedParams = paramTypes.map(
          (type: any, index: number) => {
            const customToken = customTokens.get(index);
            return this.resolve(customToken ?? type);
          }
        );

        instance = new binding.implementation(...resolvedParams);
      }

      if (binding.scope === "singleton") {
        this.singletons.set(token, instance);
      }

      return instance;
    } finally {
      this.resolving.delete(token);
    }
  }

  /**
   * Clear all singletons — useful for testing.
   */
  reset(): void {
    this.singletons.clear();
  }
}

// --- Practical usage: Building a web service ---

// Define interfaces via tokens
const ILogger = new InjectionToken<Logger>("ILogger");
const IDatabase = new InjectionToken<Database>("IDatabase");
const IConfig = new InjectionToken<AppConfig>("IConfig");

interface AppConfig {
  dbUrl: string;
  logLevel: "debug" | "info" | "warn" | "error";
}

@Injectable("singleton")
class Logger {
  private level: string;
  constructor(@Inject(IConfig) config: AppConfig) {
    this.level = config.logLevel;
  }
  info(message: string): void {
    if (["debug", "info"].includes(this.level)) {
      console.log(`[INFO] ${message}`);
    }
  }
  error(message: string, err?: Error): void {
    console.error(`[ERROR] ${message}`, err?.stack ?? "");
  }
}

@Injectable("singleton")
class Database {
  private connected = false;
  constructor(
    @Inject(IConfig) private config: AppConfig,
    @Inject(ILogger) private logger: Logger
  ) {}

  async connect(): Promise<void> {
    this.logger.info(`Connecting to ${this.config.dbUrl}`);
    // Simulated connection
    this.connected = true;
  }

  async query<T>(sql: string, params?: unknown[]): Promise<T[]> {
    if (!this.connected) throw new Error("Database not connected");
    this.logger.info(`Query: ${sql}`);
    return [] as T[];
  }
}

@Injectable("transient")
class UserRepository {
  constructor(@Inject(IDatabase) private db: Database) {}

  async findById(id: string): Promise<{ id: string; name: string } | null> {
    const results = await this.db.query<{ id: string; name: string }>(
      "SELECT * FROM users WHERE id = ?",
      [id]
    );
    return results[0] ?? null;
  }
}

// --- Bootstrap ---
const container = new Container();

// Bind config (factory because it's a plain object)
container.bindFactory(IConfig, () => ({
  dbUrl: process.env.DATABASE_URL ?? "postgres://localhost:5432/app",
  logLevel: (process.env.LOG_LEVEL as AppConfig["logLevel"]) ?? "info",
}));

container.register(Logger);
container.register(Database);
container.register(UserRepository);

container.bind(ILogger, Logger);
container.bind(IDatabase, Database);

const userRepo = container.resolve<UserRepository>(UserRepository);
```

## Testing the DI Container

```typescript
import { describe, it, expect, beforeEach } from "vitest";

describe("Container", () => {
  let container: Container;

  beforeEach(() => {
    container = new Container();
  });

  it("should resolve a simple class with no dependencies", () => {
    @Injectable("transient")
    class SimpleService {
      getValue(): string { return "hello"; }
    }
    container.register(SimpleService);
    const instance = container.resolve<SimpleService>(SimpleService);
    expect(instance.getValue()).toBe("hello");
  });

  it("should return same instance for singleton scope", () => {
    @Injectable("singleton")
    class SingletonService {
      id = Math.random();
    }
    container.register(SingletonService);
    const a = container.resolve<SingletonService>(SingletonService);
    const b = container.resolve<SingletonService>(SingletonService);
    expect(a.id).toBe(b.id);
    expect(a).toBe(b);
  });

  it("should return different instances for transient scope", () => {
    @Injectable("transient")
    class TransientService {
      id = Math.random();
    }
    container.register(TransientService);
    const a = container.resolve<TransientService>(TransientService);
    const b = container.resolve<TransientService>(TransientService);
    expect(a.id).not.toBe(b.id);
    expect(a).not.toBe(b);
  });

  it("should detect circular dependencies", () => {
    @Injectable("singleton")
    class A { constructor(@Inject(B) b: any) {} }
    @Injectable("singleton")
    class B { constructor(@Inject(A) a: any) {} }

    container.register(A);
    container.register(B);

    expect(() => container.resolve(A)).toThrow(/Circular dependency/);
  });

  it("should throw for unregistered dependencies", () => {
    class NotRegistered {}
    expect(() => container.resolve(NotRegistered)).toThrow(/No binding found/);
  });

  it("should reset singletons for test isolation", () => {
    @Injectable("singleton")
    class Stateful { calls = 0; }
    container.register(Stateful);

    const first = container.resolve<Stateful>(Stateful);
    first.calls = 5;
    container.reset();

    const second = container.resolve<Stateful>(Stateful);
    expect(second.calls).toBe(0);
    expect(second).not.toBe(first);
  });
});
```

## Summary and Key Takeaways

The most important **best practice** is choosing the right decorator standard for your project. If you use Angular, NestJS, or TypeORM, you must use legacy decorators — these frameworks have deep integrations with `emitDecoratorMetadata` and `reflect-metadata` that Stage 3 decorators do not support yet. For new library code, Stage 3 decorators are the better choice because they are the official TC39 standard and will eventually be supported natively by JavaScript engines.

A critical **pitfall** with dependency injection is over-engineering. Not every class needs to be injectable — only use DI for dependencies that have multiple implementations (e.g., real database vs. test mock) or that manage expensive resources (connections, caches). The **trade-off** is that DI adds indirection: debugging requires understanding the container's resolution order, and errors surface at runtime rather than compile time.

However, the benefits are substantial for large applications: testability (swap real services for mocks without changing business logic), modularity (add new features without modifying existing code), and configurability (different dependency graphs for dev/staging/production environments).
""",
    ),

    # --- 3. TypeScript Monorepo with Turborepo ---
    (
        "typescript/monorepo-turborepo",
        "Explain how to set up and manage a production TypeScript monorepo with Turborepo — workspace configuration with pnpm, creating shared packages and internal libraries, configuring build pipelines with task dependencies, leveraging remote caching for CI/CD, handling TypeScript project references, and deployment strategies for multiple apps from one repo. Include complete configuration files and practical examples.",
        r"""# TypeScript Monorepo with Turborepo: From Setup to Production Deployment

## Why Monorepos with Turborepo

A monorepo contains multiple packages and applications in a single repository. The core benefit is **atomic changes**: when you update a shared library, you can update all consumers in the same commit and run all tests together. The trade-off is build complexity — without a task orchestrator like Turborepo, builds become painfully slow because every package rebuilds on every change.

Turborepo solves this with **content-aware hashing** and **task pipelines**. It only rebuilds packages whose source files (or dependencies) actually changed, and it caches build outputs both locally and remotely. In practice, this reduces CI build times from 20+ minutes to **under 2 minutes** for incremental changes.

**Common mistake**: Using `npm workspaces` without a task runner. Native workspaces handle dependency linking but have no concept of task ordering, caching, or parallelism. Therefore you always need Turborepo, Nx, or a similar orchestrator on top.

## Project Structure

```
my-monorepo/
  apps/
    web/                  # Next.js frontend application
      package.json
      tsconfig.json
      next.config.js
      src/
    api/                  # Express/Fastify backend API
      package.json
      tsconfig.json
      src/
    docs/                 # Documentation site (Astro/Docusaurus)
      package.json
  packages/
    ui/                   # Shared React component library
      package.json
      tsconfig.json
      src/
    shared/               # Shared types, utilities, constants
      package.json
      tsconfig.json
      src/
    eslint-config/        # Shared ESLint configuration
      package.json
      index.js
    tsconfig/             # Shared TypeScript configs
      base.json
      nextjs.json
      library.json
  turbo.json
  pnpm-workspace.yaml
  package.json
  tsconfig.json
```

## Configuration Files

### Root Configuration

```yaml
# pnpm-workspace.yaml — defines which directories contain packages
packages:
  - "apps/*"
  - "packages/*"
```

```json
// Root package.json — workspace-level scripts and devDependencies
{
  "name": "my-monorepo",
  "private": true,
  "scripts": {
    "build": "turbo run build",
    "dev": "turbo run dev",
    "lint": "turbo run lint",
    "test": "turbo run test",
    "typecheck": "turbo run typecheck",
    "clean": "turbo run clean && rm -rf node_modules",
    "format": "prettier --write \"**/*.{ts,tsx,md,json}\""
  },
  "devDependencies": {
    "turbo": "^2.3.0",
    "prettier": "^3.4.0",
    "typescript": "^5.6.0"
  },
  "packageManager": "pnpm@9.15.0",
  "engines": {
    "node": ">=20.0.0"
  }
}
```

```json
// turbo.json — the build pipeline definition (Turborepo v2 syntax)
{
  "$schema": "https://turbo.build/schema.json",
  "globalDependencies": [
    "**/.env.*local",
    ".env"
  ],
  "globalEnv": ["NODE_ENV", "CI"],
  "tasks": {
    "build": {
      "dependsOn": ["^build"],
      "inputs": ["src/**", "tsconfig.json", "package.json"],
      "outputs": ["dist/**", ".next/**", "!.next/cache/**"],
      "env": ["DATABASE_URL", "NEXT_PUBLIC_API_URL"]
    },
    "dev": {
      "cache": false,
      "persistent": true,
      "dependsOn": ["^build"]
    },
    "lint": {
      "dependsOn": ["^build"],
      "inputs": ["src/**", ".eslintrc.*", "tsconfig.json"]
    },
    "typecheck": {
      "dependsOn": ["^build"],
      "inputs": ["src/**", "tsconfig.json", "package.json"]
    },
    "test": {
      "dependsOn": ["build"],
      "inputs": ["src/**", "tests/**", "vitest.config.*"],
      "outputs": ["coverage/**"]
    },
    "clean": {
      "cache": false
    }
  }
}
```

The **critical concept** in turbo.json is `"dependsOn": ["^build"]`. The `^` prefix means "build all dependencies first" — if `apps/web` depends on `packages/ui`, Turborepo builds `packages/ui` before `apps/web`. Without the `^`, tasks run in parallel without ordering.

### Shared TypeScript Configuration

```json
// packages/tsconfig/base.json — shared base configuration
{
  "$schema": "https://json.schemastore.org/tsconfig",
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true,
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitOverride": true,
    "noPropertyAccessFromIndexSignature": true,
    "forceConsistentCasingInFileNames": true,
    "esModuleInterop": true,
    "isolatedModules": true,
    "skipLibCheck": true,
    "resolveJsonModule": true,
    "verbatimModuleSyntax": true
  },
  "exclude": ["node_modules", "dist", "coverage"]
}
```

```json
// packages/tsconfig/library.json — for shared packages
{
  "extends": "./base.json",
  "compilerOptions": {
    "outDir": "./dist",
    "rootDir": "./src",
    "composite": true,
    "declarationDir": "./dist"
  }
}
```

```json
// packages/tsconfig/nextjs.json — for Next.js apps
{
  "extends": "./base.json",
  "compilerOptions": {
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowJs": true,
    "jsx": "preserve",
    "noEmit": true,
    "plugins": [{ "name": "next" }]
  }
}
```

## Shared Packages

### Internal UI Library

```typescript
// packages/ui/package.json
{
  "name": "@myorg/ui",
  "version": "0.0.0",
  "private": true,
  "exports": {
    ".": {
      "types": "./dist/index.d.ts",
      "import": "./dist/index.js"
    },
    "./button": {
      "types": "./dist/components/button.d.ts",
      "import": "./dist/components/button.js"
    }
  },
  "scripts": {
    "build": "tsup src/index.ts --format esm --dts --clean",
    "dev": "tsup src/index.ts --format esm --dts --watch",
    "lint": "eslint src/",
    "typecheck": "tsc --noEmit"
  },
  "devDependencies": {
    "@myorg/tsconfig": "workspace:*",
    "tsup": "^8.3.0",
    "react": "^19.0.0",
    "@types/react": "^19.0.0"
  },
  "peerDependencies": {
    "react": "^18.0.0 || ^19.0.0"
  }
}
```

```typescript
// packages/ui/src/components/button.tsx
import { type ButtonHTMLAttributes, forwardRef } from "react";

/** Variant styles for the Button component */
const variants = {
  primary:
    "bg-blue-600 text-white hover:bg-blue-700 focus:ring-blue-500",
  secondary:
    "bg-gray-200 text-gray-900 hover:bg-gray-300 focus:ring-gray-500",
  danger:
    "bg-red-600 text-white hover:bg-red-700 focus:ring-red-500",
  ghost:
    "bg-transparent text-gray-700 hover:bg-gray-100 focus:ring-gray-500",
} as const;

const sizes = {
  sm: "px-3 py-1.5 text-sm",
  md: "px-4 py-2 text-base",
  lg: "px-6 py-3 text-lg",
} as const;

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: keyof typeof variants;
  size?: keyof typeof sizes;
  loading?: boolean;
}

/**
 * Shared Button component used across all applications.
 * Supports variants, sizes, loading state, and forwarded refs.
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    { variant = "primary", size = "md", loading, children, className, disabled, ...props },
    ref
  ) => {
    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        className={[
          "inline-flex items-center justify-center rounded-md font-medium",
          "transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2",
          "disabled:opacity-50 disabled:cursor-not-allowed",
          variants[variant],
          sizes[size],
          className,
        ]
          .filter(Boolean)
          .join(" ")}
        {...props}
      >
        {loading && (
          <svg
            className="animate-spin -ml-1 mr-2 h-4 w-4"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12" cy="12" r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
        )}
        {children}
      </button>
    );
  }
);

Button.displayName = "Button";
```

```typescript
// packages/shared/src/types/api.ts — Shared types used by both frontend and backend
export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  pageSize: number;
  hasNextPage: boolean;
}

export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, string[]>;
}

export interface User {
  id: string;
  email: string;
  name: string;
  role: "admin" | "user" | "viewer";
  createdAt: string;
}

export interface CreateUserRequest {
  email: string;
  name: string;
  role?: User["role"];
}

// packages/shared/src/validation/user.ts — Shared validation logic
import type { CreateUserRequest } from "../types/api.js";

export function validateCreateUser(
  data: unknown
): { success: true; data: CreateUserRequest } | { success: false; errors: Record<string, string[]> } {
  const errors: Record<string, string[]> = {};

  if (typeof data !== "object" || data === null) {
    return { success: false, errors: { _root: ["Invalid request body"] } };
  }

  const body = data as Record<string, unknown>;

  if (typeof body.email !== "string" || !body.email.includes("@")) {
    errors.email = ["Valid email is required"];
  }
  if (typeof body.name !== "string" || body.name.length < 2) {
    errors.name = ["Name must be at least 2 characters"];
  }

  if (Object.keys(errors).length > 0) {
    return { success: false, errors };
  }

  return {
    success: true,
    data: {
      email: body.email as string,
      name: body.name as string,
      role: (body.role as User["role"]) ?? "user",
    },
  };
}
```

## Remote Caching and CI/CD

```yaml
# .github/workflows/ci.yml — GitHub Actions with Turborepo remote caching
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  TURBO_TOKEN: ${{ secrets.TURBO_TOKEN }}
  TURBO_TEAM: ${{ vars.TURBO_TEAM }}

jobs:
  build-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2  # Needed for turbo to detect changes

      - uses: pnpm/action-setup@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: "pnpm"

      - run: pnpm install --frozen-lockfile

      # Turborepo automatically uses remote cache when TURBO_TOKEN is set
      - name: Build, lint, typecheck, test
        run: pnpm turbo run build lint typecheck test --concurrency=4

      # Only deploy if on main branch and all checks pass
      - name: Deploy web app
        if: github.ref == 'refs/heads/main'
        run: pnpm turbo run deploy --filter=web

      - name: Deploy API
        if: github.ref == 'refs/heads/main'
        run: pnpm turbo run deploy --filter=api
```

## Deployment Strategies

```typescript
// apps/api/Dockerfile — Multi-stage build for the API app
// Uses pnpm deploy to create a minimal production image

// Dockerfile content (represented as a config block):
/*
FROM node:20-slim AS base
RUN corepack enable && corepack prepare pnpm@9.15.0 --activate

FROM base AS builder
WORKDIR /app
COPY . .
RUN pnpm install --frozen-lockfile
RUN pnpm turbo run build --filter=api...
RUN pnpm deploy --filter=api --prod /app/deploy

FROM base AS runner
WORKDIR /app
COPY --from=builder /app/deploy .
ENV NODE_ENV=production
EXPOSE 3001
CMD ["node", "dist/index.js"]
*/
```

## Summary and Key Takeaways

**Best practice**: Start with the `^build` dependency pattern in turbo.json — this ensures shared packages are always built before their consumers. Use `"cache": false` only for `dev` and `clean` tasks.

The biggest **pitfall** in monorepo setups is incorrect `exports` fields in package.json. If your shared package's exports don't point to the right files, consumers will see cryptic "module not found" errors. Always use the `exports` map with both `types` and `import` conditions.

The **trade-off** with monorepos is initial setup complexity versus long-term velocity. Setting up the workspace, TypeScript references, and CI pipeline takes a few days, however once established, adding new packages takes minutes and atomic cross-package changes become trivial. Therefore, monorepos are best suited for teams with 3+ developers working on 2+ related applications that share significant code.

Remote caching is the single most impactful optimization — it turns 15-minute CI builds into 90-second cache hits. **Best practice**: enable remote caching from day one, because the ROI compounds with every PR.
""",
    ),

    # --- 4. TypeScript Compiler API ---
    (
        "typescript/compiler-api-codemods",
        "Explain how to use the TypeScript Compiler API for building custom linters, codemods, and AST transformations — cover ts.createProgram, ts.forEachChild for AST traversal, the type checker for semantic analysis, and ts.transform for code modifications. Build practical tools including a custom lint rule that detects unsafe type assertions, a codemod that migrates callback-based APIs to async/await, and an AST analyzer that generates API documentation from source code.",
        r"""# TypeScript Compiler API: Building Custom Linters, Codemods, and AST Tools

## Why Use the Compiler API Directly

The TypeScript Compiler API gives you **programmatic access** to the same parser, type checker, and code emitter that `tsc` uses internally. While tools like ESLint handle most linting needs, the Compiler API is essential when you need **semantic type information** — ESLint's AST is purely syntactic and cannot tell you the type of a variable or whether a function returns a Promise.

**Best practice**: Use ESLint for style and simple pattern rules. Use the TypeScript Compiler API when your analysis requires type information — for example, detecting that a variable is `any`, checking if an assertion narrows to an incompatible type, or finding all functions that return unhandled Promises.

**Common mistake**: Trying to do everything with regex or ESLint. Pattern-based tools cannot understand type relationships, therefore they produce false positives and miss real issues.

## Setting Up a TypeScript Compiler API Project

```typescript
// package.json
// { "dependencies": { "typescript": "^5.6.0" } }

import * as ts from "typescript";
import * as path from "path";
import * as fs from "fs";

/**
 * Create a TypeScript program from a tsconfig.json file.
 * The program gives access to the AST, type checker, and diagnostics
 * for ALL files in the project.
 */
function createProgramFromConfig(tsconfigPath: string): ts.Program {
  const configFile = ts.readConfigFile(tsconfigPath, ts.sys.readFile);
  if (configFile.error) {
    throw new Error(
      `Failed to read tsconfig: ${ts.flattenDiagnosticMessageText(
        configFile.error.messageText,
        "\n"
      )}`
    );
  }

  const parsedConfig = ts.parseJsonConfigFileContent(
    configFile.config,
    ts.sys,
    path.dirname(tsconfigPath)
  );

  return ts.createProgram({
    rootNames: parsedConfig.fileNames,
    options: parsedConfig.options,
  });
}

/**
 * Create a program from individual source files (useful for testing).
 */
function createProgramFromSource(
  files: Record<string, string>,
  options?: ts.CompilerOptions
): ts.Program {
  const defaultOptions: ts.CompilerOptions = {
    target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.ESNext,
    strict: true,
    ...options,
  };

  const host = ts.createCompilerHost(defaultOptions);
  const originalGetSourceFile = host.getSourceFile;

  host.getSourceFile = (
    fileName: string,
    languageVersion: ts.ScriptTarget
  ): ts.SourceFile | undefined => {
    if (fileName in files) {
      return ts.createSourceFile(
        fileName,
        files[fileName],
        languageVersion,
        true
      );
    }
    return originalGetSourceFile.call(host, fileName, languageVersion);
  };

  host.fileExists = (fileName: string): boolean =>
    fileName in files || ts.sys.fileExists(fileName);

  host.readFile = (fileName: string): string | undefined =>
    files[fileName] ?? ts.sys.readFile(fileName);

  return ts.createProgram(Object.keys(files), defaultOptions, host);
}
```

## AST Traversal Fundamentals

Every TypeScript source file is parsed into an **Abstract Syntax Tree** (AST). Understanding how to traverse it is the foundation for all compiler API work.

```typescript
/**
 * Recursively visit every node in a source file.
 * ts.forEachChild visits direct children; for full traversal,
 * you must recurse manually.
 */
function visitAllNodes(
  node: ts.Node,
  visitor: (node: ts.Node) => void
): void {
  visitor(node);
  ts.forEachChild(node, (child) => visitAllNodes(child, visitor));
}

/**
 * Get human-readable information about a node for debugging.
 */
function describeNode(node: ts.Node, sourceFile: ts.SourceFile): string {
  const { line, character } = sourceFile.getLineAndCharacterOfPosition(
    node.getStart(sourceFile)
  );
  return (
    `${ts.SyntaxKind[node.kind]} at ${sourceFile.fileName}:` +
    `${line + 1}:${character + 1} — "${node.getText(sourceFile).slice(0, 50)}"`
  );
}

// --- Practical: Count all node types in a project ---
function analyzeAstDistribution(program: ts.Program): Map<string, number> {
  const counts = new Map<string, number>();

  for (const sourceFile of program.getSourceFiles()) {
    if (sourceFile.isDeclarationFile) continue;  // Skip .d.ts files

    visitAllNodes(sourceFile, (node) => {
      const kind = ts.SyntaxKind[node.kind];
      counts.set(kind, (counts.get(kind) ?? 0) + 1);
    });
  }

  return new Map(
    [...counts.entries()].sort((a, b) => b[1] - a[1])
  );
}
```

## Custom Lint Rule: Detecting Unsafe Type Assertions

Type assertions (`value as SomeType`) bypass TypeScript's type checker. While sometimes necessary, they are a common source of runtime errors. This linter detects assertions that narrow to incompatible types — the most dangerous pattern.

```typescript
interface LintDiagnostic {
  file: string;
  line: number;
  column: number;
  message: string;
  severity: "error" | "warning";
}

/**
 * Detect type assertions where the asserted type is NOT assignable
 * to the original type AND the original type is NOT assignable to
 * the asserted type. This means the assertion is almost certainly wrong.
 *
 * Safe: (value as string) where value: string | number (narrowing)
 * Safe: (value as unknown) (widening is always safe)
 * Unsafe: (value as User) where value: string (incompatible types)
 */
function lintUnsafeAssertions(program: ts.Program): LintDiagnostic[] {
  const checker = program.getTypeChecker();
  const diagnostics: LintDiagnostic[] = [];

  for (const sourceFile of program.getSourceFiles()) {
    if (sourceFile.isDeclarationFile) continue;

    visitAllNodes(sourceFile, (node) => {
      // Check for "value as Type" syntax
      if (!ts.isAsExpression(node) && !ts.isTypeAssertionExpression(node)) {
        return;
      }

      const expression = ts.isAsExpression(node)
        ? node.expression
        : (node as ts.TypeAssertion).expression;

      const originalType = checker.getTypeAtLocation(expression);
      const assertedType = checker.getTypeAtLocation(node);

      // Skip assertions to/from 'any' or 'unknown' — these are intentional
      if (
        originalType.flags & ts.TypeFlags.Any ||
        assertedType.flags & ts.TypeFlags.Any ||
        assertedType.flags & ts.TypeFlags.Unknown
      ) {
        return;
      }

      // Check bidirectional assignability
      const originalAssignableToAsserted = checker.isTypeAssignableTo(
        originalType,
        assertedType
      );
      const assertedAssignableToOriginal = checker.isTypeAssignableTo(
        assertedType,
        originalType
      );

      if (!originalAssignableToAsserted && !assertedAssignableToOriginal) {
        const { line, character } =
          sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));

        diagnostics.push({
          file: sourceFile.fileName,
          line: line + 1,
          column: character + 1,
          severity: "error",
          message:
            `Unsafe type assertion: '${checker.typeToString(originalType)}' ` +
            `is not related to '${checker.typeToString(assertedType)}'. ` +
            `This assertion will bypass type safety. Consider using a ` +
            `type guard or validating the data at runtime.`,
        });
      }
    });
  }

  return diagnostics;
}

// --- Usage ---
const program = createProgramFromConfig("./tsconfig.json");
const issues = lintUnsafeAssertions(program);

for (const issue of issues) {
  console.log(
    `${issue.severity.toUpperCase()}: ${issue.file}:${issue.line}:${issue.column}`
  );
  console.log(`  ${issue.message}\n`);
}
```

## Codemod: Migrate Callbacks to Async/Await

This transformer finds callback-based patterns and converts them to async/await — a practical codemod for modernizing Node.js codebases.

```typescript
/**
 * Transform callback-based function calls to async/await.
 * Detects the pattern: fn(args..., (err, result) => { ... })
 * and converts to: const result = await fn(args...);
 *
 * This is a simplified version — a production codemod would also
 * handle error branches, nested callbacks, and conditional logic.
 */
function callbackToAsyncTransformer(
  context: ts.TransformationContext
): ts.Transformer<ts.SourceFile> {
  return (sourceFile: ts.SourceFile): ts.SourceFile => {
    const factory = context.factory;

    function visit(node: ts.Node): ts.Node {
      // Look for: someFunction(arg1, arg2, (err, result) => { ... })
      if (
        ts.isCallExpression(node) &&
        node.arguments.length > 0
      ) {
        const lastArg = node.arguments[node.arguments.length - 1];

        if (
          (ts.isArrowFunction(lastArg) || ts.isFunctionExpression(lastArg)) &&
          lastArg.parameters.length === 2
        ) {
          const [errParam, resultParam] = lastArg.parameters;
          const errName = errParam.name.getText(sourceFile);
          const resultName = resultParam.name.getText(sourceFile);

          // Only transform if first param looks like an error parameter
          if (
            errName === "err" ||
            errName === "error" ||
            errName === "e"
          ) {
            // Create: const result = await fn(args without callback)
            const argsWithoutCallback = node.arguments.slice(0, -1);

            const awaitExpr = factory.createAwaitExpression(
              factory.createCallExpression(
                node.expression,
                node.typeArguments,
                argsWithoutCallback as readonly ts.Expression[]
              )
            );

            const declaration = factory.createVariableStatement(
              undefined,
              factory.createVariableDeclarationList(
                [
                  factory.createVariableDeclaration(
                    resultName,
                    undefined,
                    undefined,
                    awaitExpr
                  ),
                ],
                ts.NodeFlags.Const
              )
            );

            return declaration;
          }
        }
      }

      return ts.visitEachChild(node, visit, context);
    }

    return ts.visitNode(sourceFile, visit) as ts.SourceFile;
  };
}

/**
 * Apply a transformer to source code and return the modified source.
 */
function applyTransform(
  sourceCode: string,
  fileName: string,
  transformer: (
    context: ts.TransformationContext
  ) => ts.Transformer<ts.SourceFile>
): string {
  const sourceFile = ts.createSourceFile(
    fileName,
    sourceCode,
    ts.ScriptTarget.ES2022,
    true,
    ts.ScriptKind.TS
  );

  const result = ts.transform(sourceFile, [transformer]);
  const printer = ts.createPrinter({ newLine: ts.NewLineKind.LineFeed });
  const transformedSource = printer.printFile(
    result.transformed[0] as ts.SourceFile
  );
  result.dispose();

  return transformedSource;
}

// --- Example usage ---
const input = `
import * as fs from "fs";

fs.readFile("data.txt", "utf-8", (err, data) => {
  if (err) throw err;
  console.log(data);
});
`;

const output = applyTransform(input, "example.ts", callbackToAsyncTransformer);
console.log(output);
// Output: const data = await fs.readFile("data.txt", "utf-8");
```

## AST Analyzer: Generate API Documentation

```typescript
interface ApiDocEntry {
  name: string;
  kind: "function" | "class" | "interface" | "type";
  description: string;
  parameters: Array<{ name: string; type: string; description: string }>;
  returnType: string;
  exported: boolean;
  filePath: string;
  line: number;
}

/**
 * Extract API documentation from JSDoc comments and type information.
 * Uses both the AST (for structure) and the type checker (for resolved types).
 */
function extractApiDocs(program: ts.Program): ApiDocEntry[] {
  const checker = program.getTypeChecker();
  const entries: ApiDocEntry[] = [];

  for (const sourceFile of program.getSourceFiles()) {
    if (sourceFile.isDeclarationFile) continue;

    ts.forEachChild(sourceFile, (node) => {
      // Process exported function declarations
      if (
        ts.isFunctionDeclaration(node) &&
        node.name &&
        hasExportModifier(node)
      ) {
        const symbol = checker.getSymbolAtLocation(node.name);
        const jsdoc = symbol
          ? ts.displayPartsToString(
              symbol.getDocumentationComment(checker)
            )
          : "";

        const signature = checker.getSignatureFromDeclaration(node);
        const returnType = signature
          ? checker.typeToString(
              checker.getReturnTypeOfSignature(signature)
            )
          : "void";

        const params = (node.parameters ?? []).map((param) => {
          const paramSymbol = checker.getSymbolAtLocation(param.name);
          const paramType = checker.getTypeAtLocation(param);
          const paramDoc = paramSymbol
            ? ts.displayPartsToString(
                paramSymbol.getDocumentationComment(checker)
              )
            : "";
          return {
            name: param.name.getText(sourceFile),
            type: checker.typeToString(paramType),
            description: paramDoc,
          };
        });

        const { line } = sourceFile.getLineAndCharacterOfPosition(
          node.getStart(sourceFile)
        );

        entries.push({
          name: node.name.getText(sourceFile),
          kind: "function",
          description: jsdoc,
          parameters: params,
          returnType,
          exported: true,
          filePath: sourceFile.fileName,
          line: line + 1,
        });
      }
    });
  }

  return entries;
}

function hasExportModifier(node: ts.Node): boolean {
  return (
    ts.canHaveModifiers(node) &&
    (ts.getModifiers(node) ?? []).some(
      (m) => m.kind === ts.SyntaxKind.ExportKeyword
    )
  );
}
```

## Testing Compiler API Tools

```typescript
import { describe, it, expect } from "vitest";

describe("lintUnsafeAssertions", () => {
  it("should detect incompatible type assertions", () => {
    const program = createProgramFromSource({
      "test.ts": `
        const name: string = "hello";
        const num = name as unknown as number;  // double assertion — sneaky
        const user = ("text" as any) as { id: number };  // any bypass
        const safe = (name as string | number);  // widening — safe
      `,
    });

    const diagnostics = lintUnsafeAssertions(program);
    // The linter should flag the incompatible assertion but allow
    // widening and any-bypass (those are separate concerns)
    expect(diagnostics.length).toBeGreaterThan(0);
    expect(diagnostics[0].severity).toBe("error");
    expect(diagnostics[0].message).toContain("not related to");
  });

  it("should allow safe narrowing assertions", () => {
    const program = createProgramFromSource({
      "test.ts": `
        const value: string | number = "hello";
        const str = value as string;  // narrowing — safe
      `,
    });

    const diagnostics = lintUnsafeAssertions(program);
    expect(diagnostics).toHaveLength(0);
  });
});

describe("callbackToAsyncTransformer", () => {
  it("should transform callback to await", () => {
    const input = `readFile("test.txt", (err, data) => { console.log(data); });`;
    const output = applyTransform(input, "test.ts", callbackToAsyncTransformer);
    expect(output).toContain("await");
    expect(output).toContain("const data");
    expect(output).not.toContain("callback");
  });
});
```

## Summary and Key Takeaways

The TypeScript Compiler API is the **most powerful tool** in the TypeScript ecosystem for code analysis and transformation. The key insight is that `ts.createProgram` + `checker.getTypeAtLocation` gives you access to the same type information that powers IDE features like "Go to Definition" and "Find All References."

**Pitfall**: The Compiler API has minimal documentation and changes between TypeScript versions. Therefore, always pin your TypeScript version in tools that use the compiler API, and write comprehensive tests. The AST node types and checker methods are stable, however internal APIs (prefixed with `_`) can change without notice.

**Best practice**: Build your tools incrementally. Start with `visitAllNodes` and `console.log` to understand the AST structure, then add type checker queries, then build transformations. The **trade-off** is development speed versus power — ESLint rules are faster to write but cannot access type information, while Compiler API tools require more effort but can perform analyses that are otherwise impossible.
""",
    ),

    # --- 5. Effect-TS / fp-ts Functional Programming ---
    (
        "typescript/effect-ts-fp-ts-functional",
        "Explain functional programming in TypeScript using Effect-TS and fp-ts — cover algebraic effects, the pipe/flow composition operators, monadic types (Either, Option, Task, TaskEither), railway-oriented error handling without exceptions, and how to build production services using the Effect pattern. Include complete examples showing HTTP API handlers, database access, configuration management, and testing with dependency injection via Effect layers.",
        r"""# Effect-TS and fp-ts: Functional Programming for Production TypeScript

## Why Functional Error Handling

Traditional TypeScript relies on `try/catch` for error handling, which has critical **pitfalls**:
1. **Errors are invisible in types** — a function signature `getUser(id: string): User` tells you nothing about what can go wrong
2. **Forgotten catch blocks** — nothing forces you to handle errors, therefore they propagate silently
3. **Mixing error types** — a single catch block receives `unknown`, losing all type information
4. **Side effects are implicit** — reading from a database, writing logs, and throwing errors all look the same as pure computation

Functional programming solves these problems by making errors **explicit in the type system** and side effects **trackable and composable**. The trade-off is a steeper learning curve, however the resulting code is more predictable, testable, and maintainable.

## fp-ts Fundamentals: Option, Either, and TaskEither

fp-ts provides the foundational algebraic types. Think of them as **containers that encode success, failure, or absence** directly in the type system.

```typescript
// --- Option: represents a value that may or may not exist ---
// Replaces: null checks, undefined checks, optional chaining

import * as O from "fp-ts/Option";
import * as E from "fp-ts/Either";
import * as TE from "fp-ts/TaskEither";
import * as T from "fp-ts/Task";
import * as A from "fp-ts/Array";
import { pipe, flow } from "fp-ts/function";

// Option<A> = None | Some<A>
// Either<E, A> = Left<E> | Right<A>
// TaskEither<E, A> = () => Promise<Either<E, A>>

// --- Option: Safe value access ---

interface UserProfile {
  name: string;
  email: string;
  address?: {
    street: string;
    city: string;
    zip?: string;
  };
}

/**
 * Safely extract the zip code from a user profile.
 * Instead of nested null checks, we use Option to represent
 * the possibility of missing data at each level.
 */
function getZipCode(profile: UserProfile): O.Option<string> {
  return pipe(
    O.fromNullable(profile.address),
    O.flatMap((addr) => O.fromNullable(addr.zip)),
    O.filter((zip) => zip.length > 0)  // Additional validation
  );
}

// Usage
const profile: UserProfile = { name: "Alice", email: "alice@example.com" };
const zip = getZipCode(profile);

// Pattern matching on Option — forces you to handle both cases
const displayZip: string = pipe(
  zip,
  O.match(
    () => "No zip code on file",           // None case
    (z) => `Zip: ${z}`                     // Some case
  )
);

// --- Either: Typed error handling ---
// Left = error, Right = success (mnemonic: "right" = "correct")

interface ValidationError {
  field: string;
  message: string;
}

function validateEmail(email: string): E.Either<ValidationError, string> {
  if (!email.includes("@")) {
    return E.left({ field: "email", message: "Must contain @" });
  }
  if (email.length > 254) {
    return E.left({ field: "email", message: "Too long" });
  }
  return E.right(email.toLowerCase().trim());
}

function validateAge(age: unknown): E.Either<ValidationError, number> {
  if (typeof age !== "number" || !Number.isFinite(age)) {
    return E.left({ field: "age", message: "Must be a number" });
  }
  if (age < 0 || age > 150) {
    return E.left({ field: "age", message: "Must be between 0 and 150" });
  }
  return E.right(age);
}

// Chain validations — short-circuits on first error
function validateRegistration(data: {
  email: string;
  age: unknown;
}): E.Either<ValidationError, { email: string; age: number }> {
  return pipe(
    E.Do,
    E.bind("email", () => validateEmail(data.email)),
    E.bind("age", () => validateAge(data.age))
  );
}
```

## The pipe and flow Operators

`pipe` and `flow` are the fundamental **composition operators** in fp-ts. Understanding them is essential because every fp-ts program is built from small functions composed together.

```typescript
// pipe: passes a value through a sequence of functions
// pipe(value, f1, f2, f3) === f3(f2(f1(value)))

const result = pipe(
  [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
  A.filter((n) => n % 2 === 0),         // [2, 4, 6, 8, 10]
  A.map((n) => n * n),                   // [4, 16, 36, 64, 100]
  A.reduce(0, (sum, n) => sum + n)       // 220
);

// flow: creates a new function from a sequence of functions
// flow(f1, f2, f3) === (value) => f3(f2(f1(value)))

const processNumbers = flow(
  A.filter((n: number) => n % 2 === 0),
  A.map((n) => n * n),
  A.reduce(0, (sum: number, n: number) => sum + n)
);

// Same result, but reusable
console.log(processNumbers([1, 2, 3, 4, 5]));  // 20 + 4 = 20
console.log(processNumbers([10, 20, 30]));      // 100 + 400 + 900 = 1400

// --- TaskEither: Async operations with typed errors ---
// TaskEither<E, A> = () => Promise<Either<E, A>>
// This is the workhorse type for production services

interface AppError {
  readonly _tag: "NetworkError" | "ParseError" | "NotFoundError" | "DbError";
  readonly message: string;
  readonly cause?: unknown;
}

function networkError(message: string, cause?: unknown): AppError {
  return { _tag: "NetworkError", message, cause };
}

function parseError(message: string, cause?: unknown): AppError {
  return { _tag: "ParseError", message, cause };
}

function notFoundError(message: string): AppError {
  return { _tag: "NotFoundError", message };
}

// Wrap a fetch call in TaskEither
function fetchJson<T>(url: string): TE.TaskEither<AppError, T> {
  return TE.tryCatch(
    async () => {
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      return (await response.json()) as T;
    },
    (error) => networkError(`Failed to fetch ${url}`, error)
  );
}

// Compose async operations with full error tracking
interface GithubUser {
  login: string;
  name: string;
  public_repos: number;
}

interface GithubRepo {
  name: string;
  stargazers_count: number;
}

function getTopRepos(
  username: string
): TE.TaskEither<AppError, GithubRepo[]> {
  return pipe(
    fetchJson<GithubUser>(`https://api.github.com/users/${username}`),
    TE.flatMap((user) =>
      fetchJson<GithubRepo[]>(
        `https://api.github.com/users/${user.login}/repos?sort=stars&per_page=5`
      )
    ),
    TE.map((repos) =>
      repos.filter((r) => r.stargazers_count > 0)
    )
  );
}

// Execute and handle the result
async function main(): Promise<void> {
  const result = await getTopRepos("microsoft")();

  pipe(
    result,
    E.match(
      (error) => {
        console.error(`Error (${error._tag}): ${error.message}`);
      },
      (repos) => {
        repos.forEach((r) =>
          console.log(`${r.name}: ${r.stargazers_count} stars`)
        );
      }
    )
  );
}
```

## Effect-TS: The Next Generation

Effect-TS (often just called "Effect") builds on fp-ts concepts but provides a **unified runtime** with built-in dependency injection, concurrency, resource management, and observability. It replaces fp-ts for new projects because it solves the composition and performance problems that fp-ts has at scale.

```typescript
// --- Effect-TS fundamentals ---
import { Effect, pipe, Layer, Context, Config, Console } from "effect";
import { Schema } from "effect";

// Effect<A, E, R> represents a program that:
//   - Produces a value of type A (success)
//   - Can fail with an error of type E
//   - Requires dependencies of type R (requirements)

// --- Define typed errors ---

class NetworkError extends Schema.TaggedError<NetworkError>()(
  "NetworkError",
  { url: Schema.String, status: Schema.Number }
) {}

class DatabaseError extends Schema.TaggedError<DatabaseError>()(
  "DatabaseError",
  { query: Schema.String, cause: Schema.Unknown }
) {}

class NotFoundError extends Schema.TaggedError<NotFoundError>()(
  "NotFoundError",
  { resource: Schema.String, id: Schema.String }
) {}

// --- Define service interfaces using Context.Tag ---

// Database service
class DatabaseService extends Context.Tag("DatabaseService")<
  DatabaseService,
  {
    readonly query: <T>(
      sql: string,
      params?: unknown[]
    ) => Effect.Effect<T[], DatabaseError>;
    readonly queryOne: <T>(
      sql: string,
      params?: unknown[]
    ) => Effect.Effect<T, DatabaseError | NotFoundError>;
  }
>() {}

// HTTP client service
class HttpClient extends Context.Tag("HttpClient")<
  HttpClient,
  {
    readonly get: <T>(url: string) => Effect.Effect<T, NetworkError>;
    readonly post: <T>(
      url: string,
      body: unknown
    ) => Effect.Effect<T, NetworkError>;
  }
>() {}

// Logger service
class AppLogger extends Context.Tag("AppLogger")<
  AppLogger,
  {
    readonly info: (message: string) => Effect.Effect<void>;
    readonly error: (
      message: string,
      cause?: unknown
    ) => Effect.Effect<void>;
  }
>() {}

// --- Build a production user service ---

interface User {
  id: string;
  name: string;
  email: string;
}

/**
 * UserService — depends on Database and Logger.
 * The dependency requirements are tracked in the type signature.
 * Effect will NOT compile if you forget to provide a dependency.
 */
function findUserById(
  id: string
): Effect.Effect<User, DatabaseError | NotFoundError, DatabaseService | AppLogger> {
  return pipe(
    AppLogger,
    Effect.flatMap((logger) => logger.info(`Looking up user: ${id}`)),
    Effect.flatMap(() => DatabaseService),
    Effect.flatMap((db) =>
      db.queryOne<User>("SELECT * FROM users WHERE id = $1", [id])
    )
  );
}

function createUser(
  data: { name: string; email: string }
): Effect.Effect<User, DatabaseError, DatabaseService | AppLogger> {
  return pipe(
    AppLogger,
    Effect.flatMap((logger) => logger.info(`Creating user: ${data.email}`)),
    Effect.flatMap(() => DatabaseService),
    Effect.flatMap((db) =>
      db.queryOne<User>(
        "INSERT INTO users (name, email) VALUES ($1, $2) RETURNING *",
        [data.name, data.email]
      )
    )
  );
}

// --- HTTP handler using Effect ---

function handleGetUser(
  request: { params: { id: string } }
): Effect.Effect<
  { status: number; body: unknown },
  never,
  DatabaseService | AppLogger
> {
  return pipe(
    findUserById(request.params.id),
    Effect.map((user) => ({ status: 200, body: { data: user } })),
    Effect.catchTags({
      NotFoundError: (err) =>
        Effect.succeed({
          status: 404,
          body: { error: `User ${err.id} not found` },
        }),
      DatabaseError: (err) =>
        Effect.succeed({
          status: 500,
          body: { error: "Internal server error" },
        }),
    })
  );
}
```

## Dependency Injection with Layers

Effect's **Layer** system is its dependency injection mechanism. Layers describe how to construct services, and they compose automatically.

```typescript
// --- Implement the services as Layers ---

// Console logger implementation
const ConsoleLoggerLive = Layer.succeed(
  AppLogger,
  {
    info: (message: string) => Console.log(`[INFO] ${message}`),
    error: (message: string, cause?: unknown) =>
      Console.error(`[ERROR] ${message}`, cause),
  }
);

// PostgreSQL database implementation
const PostgresLive = Layer.effect(
  DatabaseService,
  Effect.gen(function* () {
    const logger = yield* AppLogger;
    yield* logger.info("Initializing PostgreSQL connection");

    // In production, this would use pg or postgres.js
    return {
      query: <T>(sql: string, params?: unknown[]) =>
        Effect.tryPromise({
          try: async () => {
            // Simulated query
            return [] as T[];
          },
          catch: (cause) =>
            new DatabaseError({ query: sql, cause }),
        }),
      queryOne: <T>(sql: string, params?: unknown[]) =>
        pipe(
          Effect.tryPromise({
            try: async () => {
              return [] as T[];
            },
            catch: (cause) =>
              new DatabaseError({ query: sql, cause }),
          }),
          Effect.flatMap((results) =>
            results.length > 0
              ? Effect.succeed(results[0])
              : Effect.fail(
                  new NotFoundError({
                    resource: "record",
                    id: String(params?.[0] ?? "unknown"),
                  })
                )
          )
        ),
    };
  })
);

// Compose layers: Postgres depends on Logger, therefore we merge them
const AppLive = PostgresLive.pipe(
  Layer.provideMerge(ConsoleLoggerLive)
);

// --- Run the program ---
// Effect.runPromise provides the layers and executes the effect

const program = handleGetUser({ params: { id: "user-123" } });

// This is where all dependencies are provided and the program executes.
// If you forget a layer, TypeScript gives a compile error — not a runtime error.
Effect.runPromise(
  program.pipe(Effect.provide(AppLive))
).then(console.log);
```

## Testing with Effect

Because dependencies are tracked in the type system, testing becomes trivial — just swap the real layers for test layers.

```typescript
import { describe, it, expect } from "vitest";

// Test implementations
const TestLoggerLive = Layer.succeed(AppLogger, {
  info: (_message: string) => Effect.void,
  error: (_message: string, _cause?: unknown) => Effect.void,
});

const mockUsers: User[] = [
  { id: "1", name: "Alice", email: "alice@test.com" },
  { id: "2", name: "Bob", email: "bob@test.com" },
];

const TestDatabaseLive = Layer.succeed(DatabaseService, {
  query: <T>(_sql: string, _params?: unknown[]) =>
    Effect.succeed(mockUsers as unknown as T[]),
  queryOne: <T>(_sql: string, params?: unknown[]) => {
    const id = String(params?.[0]);
    const found = mockUsers.find((u) => u.id === id);
    return found
      ? Effect.succeed(found as unknown as T)
      : Effect.fail(new NotFoundError({ resource: "user", id }));
  },
});

const TestAppLive = Layer.mergeAll(TestLoggerLive, TestDatabaseLive);

describe("handleGetUser", () => {
  it("should return user when found", async () => {
    const result = await Effect.runPromise(
      handleGetUser({ params: { id: "1" } }).pipe(
        Effect.provide(TestAppLive)
      )
    );

    expect(result.status).toBe(200);
    expect((result.body as any).data.name).toBe("Alice");
  });

  it("should return 404 when user not found", async () => {
    const result = await Effect.runPromise(
      handleGetUser({ params: { id: "nonexistent" } }).pipe(
        Effect.provide(TestAppLive)
      )
    );

    expect(result.status).toBe(404);
    expect((result.body as any).error).toContain("nonexistent");
  });
});

describe("pipe and flow composition", () => {
  it("should compose array operations with pipe", () => {
    const result = pipe(
      [1, 2, 3, 4, 5],
      A.filter((n) => n > 2),
      A.map((n) => n * 10)
    );
    expect(result).toEqual([30, 40, 50]);
  });

  it("should create reusable pipelines with flow", () => {
    const doubleEvens = flow(
      A.filter((n: number) => n % 2 === 0),
      A.map((n) => n * 2)
    );
    expect(doubleEvens([1, 2, 3, 4])).toEqual([4, 8]);
    expect(doubleEvens([10, 11, 12])).toEqual([20, 24]);
  });
});
```

## Summary and Key Takeaways

**Best practice**: For new projects in 2025+, use Effect-TS rather than fp-ts. Effect provides a unified solution for error handling, dependency injection, concurrency, and resource management — replacing 5+ separate libraries. fp-ts remains valuable for understanding the underlying concepts and for projects that need only lightweight functional utilities.

The fundamental **trade-off** is learning curve versus correctness. Functional error handling with `Either` and `Effect` requires developers to learn new patterns (pipe, flatMap, match), however the payoff is enormous: **every possible failure is visible in the type signature**, dependency requirements are tracked at compile time, and testing becomes trivial because you simply swap layers.

A common **pitfall** is trying to convert an entire codebase at once. The best approach is to introduce Effect or fp-ts at the **boundary** — HTTP handlers, database queries, external API calls — where errors are most common and most costly. Pure business logic in the middle can remain as plain TypeScript functions. Therefore, adopt functional error handling incrementally, starting with the most error-prone layers of your application.
""",
    ),
]
