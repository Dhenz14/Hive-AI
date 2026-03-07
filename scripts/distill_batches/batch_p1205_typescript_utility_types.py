"""
Batch P1205 -- TypeScript utility types: Pick, Omit, Record, Extract,
Exclude, template literal types, mapped types, conditional types.
Target: JS/TS rebalancing. 2 thinking + 3 direct pairs.
"""

pairs = [
    # --- 1. thinking: Pick and Omit for API boundaries ---
    {
        "instruction": r'''How do I use TypeScript Pick and Omit to create different views of a User type for API request/response boundaries?''',
        "output": r'''<think>
The user wants Pick and Omit for API boundary types. A full User type
with subsets for create, update, and public response. I should show
combining with Partial for updates and warn about Omit not constraining
keys unless you build a StrictOmit.
</think>

Use `Pick` and `Omit` to derive API types from a single source of truth:

```typescript
interface User {
  id: string;
  email: string;
  passwordHash: string;
  displayName: string;
  role: "admin" | "user";
  createdAt: Date;
}

// Creation -- only client-sent fields
type CreateUserRequest = Pick<User, "email" | "displayName" | "role">;

// Update -- partial subset, exclude immutable fields
type UpdateUserRequest = Partial<Omit<User, "id" | "createdAt" | "passwordHash">>;

// Public response -- hide sensitive fields
type UserResponse = Omit<User, "passwordHash">;

// StrictOmit catches typos in excluded keys
type StrictOmit<T, K extends keyof T> = Pick<T, Exclude<keyof T, K>>;
// type Bad = StrictOmit<User, "nonexistent">; // compile error

function createUser(body: CreateUserRequest): UserResponse {
  const user: User = {
    id: crypto.randomUUID(),
    ...body,
    passwordHash: "",
    createdAt: new Date(),
  };
  const { passwordHash, ...response } = user;
  return response;
}
```

`Pick<T, K>` selects keys, `Omit<T, K>` removes them. Both produce new types at compile time with zero runtime cost.'''
    },

    # --- 2. direct: Record and mapped types ---
    {
        "instruction": r'''Show me how Record and mapped types work in TypeScript with practical examples.''',
        "output": r'''`Record<K, V>` creates an object type with keys `K` and values `V`. Mapped types generalize this:

```typescript
type HttpStatus = 200 | 301 | 404 | 500;
const statusMessages: Record<HttpStatus, string> = {
  200: "OK",
  301: "Moved Permanently",
  404: "Not Found",
  500: "Internal Server Error",
};

// Record with union keys ensures exhaustiveness
type Theme = "light" | "dark" | "system";
type ThemeColors = Record<Theme, { bg: string; fg: string }>;

// Custom mapped type -- make all properties nullable
type Nullable<T> = { [K in keyof T]: T[K] | null };

// Key remapping (TS 4.1+)
type Getters<T> = {
  [K in keyof T as `get${Capitalize<string & K>}`]: () => T[K];
};

interface Config { host: string; port: number; }
// Produces: { getHost: () => string; getPort: () => number }
type ConfigGetters = Getters<Config>;

// Filter keys by value type
type OnlyStrings<T> = {
  [K in keyof T as T[K] extends string ? K : never]: T[K];
};
type StringFields = OnlyStrings<Config>; // { host: string }
```

`Record<K, V>` is sugar for `{ [P in K]: V }`. Custom mapped types transform keys, filter by value type, and add modifiers like `readonly`.'''
    },

    # --- 3. direct: Extract, Exclude, and conditional types ---
    {
        "instruction": r'''Explain TypeScript Extract and Exclude utility types. When should I use them vs Pick/Omit?''',
        "output": r'''`Extract` and `Exclude` operate on **union types**. `Pick` and `Omit` operate on **object properties**.

```typescript
type AllEvents = "click" | "scroll" | "keydown" | "keyup" | "focus";

type KeyEvents = Extract<AllEvents, "keydown" | "keyup">;
// "keydown" | "keyup"

type NonKeyEvents = Exclude<AllEvents, "keydown" | "keyup">;
// "click" | "scroll" | "focus"

// Filter discriminated union members
type ApiResponse =
  | { status: "success"; data: unknown }
  | { status: "error"; message: string }
  | { status: "loading" };

type ActiveStates = Extract<ApiResponse, { status: "success" | "error" }>;

// Extract function property names from a class
type FunctionKeys<T> = {
  [K in keyof T]: T[K] extends Function ? K : never;
}[keyof T];

class UserService {
  name = "";
  greet(): string { return this.name; }
  save(): Promise<void> { return Promise.resolve(); }
}

type MethodNames = FunctionKeys<UserService>; // "greet" | "save"
type Methods<T> = Pick<T, FunctionKeys<T>>;
```

Rule: `Extract`/`Exclude` filter **union members**, `Pick`/`Omit` select **object keys**.'''
    },

    # --- 4. thinking: template literal types ---
    {
        "instruction": r'''How can I use TypeScript template literal types to build a type-safe CSS utility class generator?''',
        "output": r'''<think>
Template literal types build string types by interpolation. Unions
inside them distribute automatically giving the cartesian product.
For a CSS utility generator I can type spacing classes like "p-1",
"m-2", "px-4". Combined with Capitalize and other intrinsic string
types this enables compile-time string manipulation.
</think>

Template literal types (TS 4.1+) construct string types via interpolation. Unions distribute automatically:

```typescript
type Direction = "t" | "r" | "b" | "l" | "x" | "y" | "";
type Size = 0 | 1 | 2 | 4 | 8;
type Property = "p" | "m";

// Produces "p-0" | "pt-1" | "mx-8" | ... (many combinations)
type SpacingClass = `${Property}${Direction}-${Size}`;

type Color = "red" | "blue" | "green";
type Shade = 100 | 300 | 500 | 700 | 900;
type ColorClass = `text-${Color}-${Shade}` | `bg-${Color}-${Shade}`;

// Responsive prefixes
type Breakpoint = "sm" | "md" | "lg" | "xl";
type Responsive<T extends string> = T | `${Breakpoint}:${T}`;

function cn(...classes: Array<SpacingClass | ColorClass>): string {
  return classes.join(" ");
}
const result = cn("p-4", "mt-2", "text-blue-500");

// Parse with template literal inference
type ExtractParts<S extends string> =
  S extends `${infer P}-${infer N}` ? { prop: P; size: N } : never;

// Event handler naming
type DomEvent = "click" | "focus" | "blur";
type HandlerName = `on${Capitalize<DomEvent>}`;
// "onClick" | "onFocus" | "onBlur"

type EventHandlers = {
  [E in DomEvent as `on${Capitalize<E>}`]?: (e: Event) => void;
};
```

Unions inside template literals give the cartesian product. Combined with `Capitalize`, `Lowercase`, etc., they enable compile-time string manipulation with full IDE autocomplete.'''
    },

    # --- 5. direct: conditional types with infer ---
    {
        "instruction": r'''Show practical TypeScript conditional types with the infer keyword for extracting nested types.''',
        "output": r'''Conditional types follow `T extends U ? X : Y`. The `infer` keyword captures part of a type structure:

```typescript
// Unwrap nested promises
type UnwrapPromise<T> =
  T extends Promise<infer U> ? UnwrapPromise<U> : T;
type A = UnwrapPromise<Promise<Promise<string>>>; // string

// Array element type
type ElementOf<T> = T extends readonly (infer E)[] ? E : T;
type B = ElementOf<string[]>; // string

// Tuple head and tail
type Head<T extends any[]> = T extends [infer H, ...any[]] ? H : never;
type Tail<T extends any[]> = T extends [any, ...infer R] ? R : [];
type C = Head<[1, 2, 3]>; // 1
type D = Tail<[1, 2, 3]>; // [2, 3]

// Extract route params from URL pattern
type ExtractParams<T extends string> =
  T extends `${string}:${infer Param}/${infer Rest}`
    ? Param | ExtractParams<`/${Rest}`>
    : T extends `${string}:${infer Param}`
      ? Param
      : never;

type Params = ExtractParams<"/users/:userId/posts/:postId">;
// "userId" | "postId"

type RouteParams<T extends string> = {
  [K in ExtractParams<T>]: string;
};
// { userId: string; postId: string }

function handleRoute<T extends string>(
  route: T, params: RouteParams<T>
): void { /* ... */ }

handleRoute("/users/:userId/posts/:postId", {
  userId: "123",
  postId: "456",
});
```

`infer` only works inside the `extends` clause of a conditional type. It captures a type variable for use in the true branch.'''
    },
]
