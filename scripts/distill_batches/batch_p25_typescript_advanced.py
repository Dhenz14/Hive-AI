"""TypeScript advanced — type system, generics, utility types, type-safe patterns."""

PAIRS = [
    (
        "typescript/advanced-type-system",
        "Show advanced TypeScript type patterns: conditional types, mapped types, template literal types, and type-level programming.",
        '''Advanced TypeScript type system for type-safe APIs:

```typescript
// --- Conditional Types ---

type IsString<T> = T extends string ? true : false;
type A = IsString<"hello">;  // true
type B = IsString<42>;        // false

// Extract return type from async functions
type UnwrapPromise<T> = T extends Promise<infer U> ? U : T;
type Result = UnwrapPromise<Promise<string>>;  // string

// Conditional extraction
type ExtractArray<T> = T extends (infer U)[] ? U : never;
type Elem = ExtractArray<string[]>;  // string

// --- Mapped Types ---

type Readonly<T> = { readonly [K in keyof T]: T[K] };
type Optional<T> = { [K in keyof T]?: T[K] };
type Nullable<T> = { [K in keyof T]: T[K] | null };

// Transform property types
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

// Filter properties by type
type StringKeys<T> = {
    [K in keyof T as T[K] extends string ? K : never]: T[K];
};

type UserStrings = StringKeys<User>;
// { name: string; email: string }

// --- Template Literal Types ---

type HTTPMethod = "GET" | "POST" | "PUT" | "DELETE" | "PATCH";
type APIPath = `/api/${string}`;
type Endpoint = `${HTTPMethod} ${APIPath}`;

// Valid: "GET /api/users", "POST /api/orders"
// Invalid: "CONNECT /api/users", "GET /users"

type EventName<T extends string> = `on${Capitalize<T>}`;
type ClickEvent = EventName<"click">;  // "onClick"

// Parse string types
type ParsePath<S extends string> =
    S extends `${infer Segment}/${infer Rest}`
        ? [Segment, ...ParsePath<Rest>]
        : [S];

type Parsed = ParsePath<"api/users/123">;
// ["api", "users", "123"]

// --- Type-safe API client ---

interface APIRoutes {
    "GET /users": { response: User[]; query: { page?: number; limit?: number } };
    "GET /users/:id": { response: User; params: { id: string } };
    "POST /users": { response: User; body: Omit<User, "id"> };
    "PUT /users/:id": { response: User; params: { id: string }; body: Partial<User> };
    "DELETE /users/:id": { response: void; params: { id: string } };
}

type RouteConfig<K extends keyof APIRoutes> = APIRoutes[K];

// Extract params from path pattern
type ExtractParams<T extends string> =
    T extends `${string}:${infer Param}/${infer Rest}`
        ? { [K in Param | keyof ExtractParams<Rest>]: string }
        : T extends `${string}:${infer Param}`
            ? { [K in Param]: string }
            : {};

type UserParams = ExtractParams<"GET /users/:id">;  // { id: string }

// --- Discriminated Unions (exhaustive pattern matching) ---

type Shape =
    | { kind: "circle"; radius: number }
    | { kind: "rectangle"; width: number; height: number }
    | { kind: "triangle"; base: number; height: number };

function area(shape: Shape): number {
    switch (shape.kind) {
        case "circle":
            return Math.PI * shape.radius ** 2;
        case "rectangle":
            return shape.width * shape.height;
        case "triangle":
            return 0.5 * shape.base * shape.height;
        default:
            // Exhaustiveness check — error if we miss a case
            const _exhaustive: never = shape;
            return _exhaustive;
    }
}

// --- Builder Pattern with Type Safety ---

type RequiredFields = "name" | "email";

class UserBuilder<Built extends string = never> {
    private data: Partial<User> = {};

    name(name: string): UserBuilder<Built | "name"> {
        this.data.name = name;
        return this as any;
    }

    email(email: string): UserBuilder<Built | "email"> {
        this.data.email = email;
        return this as any;
    }

    age(age: number): UserBuilder<Built | "age"> {
        this.data.age = age;
        return this as any;
    }

    // build() only available when all required fields are set
    build(this: UserBuilder<RequiredFields>): User {
        return this.data as User;
    }
}

// Type-safe:
new UserBuilder().name("Alice").email("alice@test.com").build();  // OK
// new UserBuilder().name("Alice").build();  // Error: email required

// --- Branded Types (nominal typing) ---

type Brand<T, B extends string> = T & { readonly __brand: B };

type UserId = Brand<string, "UserId">;
type OrderId = Brand<string, "OrderId">;

function getUser(id: UserId): User { /* ... */ }
function getOrder(id: OrderId): Order { /* ... */ }

const userId = "user-123" as UserId;
const orderId = "order-456" as OrderId;

getUser(userId);    // OK
// getUser(orderId);  // Error! OrderId not assignable to UserId

// --- Utility type implementations ---

// DeepPartial — recursive optional
type DeepPartial<T> = T extends object
    ? { [K in keyof T]?: DeepPartial<T[K]> }
    : T;

// DeepReadonly — recursive readonly
type DeepReadonly<T> = T extends object
    ? { readonly [K in keyof T]: DeepReadonly<T[K]> }
    : T;

// Paths — all dot-notation paths through an object
type Paths<T, Prefix extends string = ""> = T extends object
    ? { [K in keyof T & string]:
        Prefix extends ""
            ? K | Paths<T[K], K>
            : `${Prefix}.${K}` | Paths<T[K], `${Prefix}.${K}`>
    }[keyof T & string]
    : never;

type UserPaths = Paths<{ name: string; address: { city: string; zip: string } }>;
// "name" | "address" | "address.city" | "address.zip"
```

Key patterns:
- **Conditional types** — type-level if/else with `infer`
- **Mapped types** — transform object types property by property
- **Template literals** — string manipulation at type level
- **Discriminated unions** — exhaustive pattern matching
- **Branded types** — prevent mixing IDs of different entities'''
    ),
    (
        "typescript/generic-patterns",
        "Show practical TypeScript generic patterns: constrained generics, generic factories, type-safe event emitters, and generic React components.",
        '''Practical generic patterns in TypeScript:

```typescript
// --- Constrained generics ---

// Ensure T has an id property
function findById<T extends { id: string }>(items: T[], id: string): T | undefined {
    return items.find(item => item.id === id);
}

// Key constraint — K must be a key of T
function pick<T, K extends keyof T>(obj: T, keys: K[]): Pick<T, K> {
    const result = {} as Pick<T, K>;
    for (const key of keys) {
        result[key] = obj[key];
    }
    return result;
}

// Constrained to comparable types
function max<T extends number | string | Date>(a: T, b: T): T {
    return a > b ? a : b;
}

// --- Generic Factory ---

interface Repository<T extends { id: string }> {
    findById(id: string): Promise<T | null>;
    findAll(filter?: Partial<T>): Promise<T[]>;
    create(data: Omit<T, "id">): Promise<T>;
    update(id: string, data: Partial<T>): Promise<T>;
    delete(id: string): Promise<void>;
}

function createRepository<T extends { id: string }>(
    tableName: string,
    db: Database
): Repository<T> {
    return {
        async findById(id) {
            return db.query<T>(`SELECT * FROM ${tableName} WHERE id = $1`, [id]);
        },
        async findAll(filter) {
            const conditions = filter
                ? Object.entries(filter)
                    .map(([k], i) => `${k} = $${i + 1}`)
                    .join(" AND ")
                : "TRUE";
            return db.queryAll<T>(
                `SELECT * FROM ${tableName} WHERE ${conditions}`,
                filter ? Object.values(filter) : []
            );
        },
        async create(data) {
            const keys = Object.keys(data);
            const values = Object.values(data);
            const placeholders = keys.map((_, i) => `$${i + 1}`);
            return db.query<T>(
                `INSERT INTO ${tableName} (${keys.join(", ")}) VALUES (${placeholders.join(", ")}) RETURNING *`,
                values
            );
        },
        async update(id, data) {
            const entries = Object.entries(data);
            const sets = entries.map(([k], i) => `${k} = $${i + 2}`);
            return db.query<T>(
                `UPDATE ${tableName} SET ${sets.join(", ")} WHERE id = $1 RETURNING *`,
                [id, ...entries.map(([, v]) => v)]
            );
        },
        async delete(id) {
            await db.query(`DELETE FROM ${tableName} WHERE id = $1`, [id]);
        },
    };
}

// Usage:
interface User { id: string; name: string; email: string }
const userRepo = createRepository<User>("users", db);
const user = await userRepo.findById("123");  // User | null

// --- Type-safe Event Emitter ---

type EventMap = Record<string, any>;

class TypedEmitter<Events extends EventMap> {
    private handlers: {
        [K in keyof Events]?: Array<(data: Events[K]) => void>;
    } = {};

    on<K extends keyof Events>(event: K, handler: (data: Events[K]) => void): void {
        if (!this.handlers[event]) {
            this.handlers[event] = [];
        }
        this.handlers[event]!.push(handler);
    }

    emit<K extends keyof Events>(event: K, data: Events[K]): void {
        this.handlers[event]?.forEach(handler => handler(data));
    }

    off<K extends keyof Events>(event: K, handler: (data: Events[K]) => void): void {
        const list = this.handlers[event];
        if (list) {
            this.handlers[event] = list.filter(h => h !== handler);
        }
    }
}

// Usage:
interface AppEvents {
    "user:login": { userId: string; timestamp: Date };
    "user:logout": { userId: string };
    "order:created": { orderId: string; total: number };
}

const emitter = new TypedEmitter<AppEvents>();

emitter.on("user:login", (data) => {
    console.log(data.userId);     // string — fully typed!
    console.log(data.timestamp);  // Date
});

// emitter.emit("user:login", { userId: "123" });  // Error: missing timestamp

// --- Generic Result type (no exceptions) ---

type Result<T, E = Error> =
    | { ok: true; value: T }
    | { ok: false; error: E };

function ok<T>(value: T): Result<T, never> {
    return { ok: true, value };
}

function err<E>(error: E): Result<never, E> {
    return { ok: false, error };
}

async function safeParse<T>(
    schema: { parse: (data: unknown) => T },
    data: unknown
): Promise<Result<T, string>> {
    try {
        return ok(schema.parse(data));
    } catch (e) {
        return err(String(e));
    }
}

// Usage:
const result = await safeParse(UserSchema, rawData);
if (result.ok) {
    console.log(result.value.name);  // T is narrowed
} else {
    console.error(result.error);     // string
}

// --- Generic pipe/compose ---

type Fn<A, B> = (a: A) => B;

function pipe<A, B>(fn1: Fn<A, B>): Fn<A, B>;
function pipe<A, B, C>(fn1: Fn<A, B>, fn2: Fn<B, C>): Fn<A, C>;
function pipe<A, B, C, D>(fn1: Fn<A, B>, fn2: Fn<B, C>, fn3: Fn<C, D>): Fn<A, D>;
function pipe(...fns: Function[]): Function {
    return (x: any) => fns.reduce((acc, fn) => fn(acc), x);
}

// Type-safe pipeline:
const process = pipe(
    (s: string) => s.trim(),
    (s: string) => s.toLowerCase(),
    (s: string) => s.split(" "),
);  // (s: string) => string[]
```

Generic best practices:
1. **Name generics meaningfully** — `TItem`, `TResponse`, not just `T`
2. **Constrain generics** — `T extends object` over unconstrained `T`
3. **Prefer utility types** — `Partial`, `Pick`, `Omit` over manual mapping
4. **Default generics** — `<T = string>` for common cases
5. **Avoid over-generalization** — concrete types when generic adds no value'''
    ),
]
