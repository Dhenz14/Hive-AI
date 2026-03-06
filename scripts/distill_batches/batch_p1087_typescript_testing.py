"""
Batch p1087: TypeScript testing patterns.
Type-level testing (expect-type), generic test utilities, mock type safety, fixture typing, type-safe test builders.
"""

PAIRS = [
    (
        "typescript/testing",
        r'''Build a TypeScript type-level testing library similar to expect-type that can assert type equality, assignability, extension, and detect never/any types. Include compile-time assertions that produce clear error messages on failure.''',
        r'''A type-level testing library with compile-time assertions:

```typescript
// Core type equality check using mutual extends
type IsExact<A, B> = [A] extends [B] ? ([B] extends [A] ? true : false) : false;

// Check if A is assignable to B
type IsAssignable<A, B> = [A] extends [B] ? true : false;

// Detect special types
type IsNever<T> = [T] extends [never] ? true : false;
type IsAny<T> = 0 extends (1 & T) ? true : false;
type IsUnknown<T> = IsAny<T> extends true ? false : unknown extends T ? true : false;

// Branded error types for clear compile-time messages
declare const MISMATCH: unique symbol;

interface TypeMismatchError<Expected, Actual> {
  [MISMATCH]: "Type assertion failed";
  expected: Expected;
  actual: Actual;
}

// Assertion functions that produce compile-time errors
// When the assertion passes, these resolve to void
// When it fails, they require an impossible argument

type AssertTrue<T extends true> = T;
type AssertFalse<T extends false> = T;

// ExpectType API
interface ExpectType<T> {
  toEqual: <U>() => IsExact<T, U> extends true ? void : TypeMismatchError<U, T>;
  toExtend: <U>() => [T] extends [U] ? void : TypeMismatchError<`extends ${string & U}`, T>;
  toBe: {
    never: IsNever<T> extends true ? void : TypeMismatchError<never, T>;
    any: IsAny<T> extends true ? void : TypeMismatchError<any, T>;
    unknown: IsUnknown<T> extends true ? void : TypeMismatchError<unknown, T>;
    string: [T] extends [string] ? void : TypeMismatchError<string, T>;
    number: [T] extends [number] ? void : TypeMismatchError<number, T>;
    boolean: [T] extends [boolean] ? void : TypeMismatchError<boolean, T>;
    null: IsExact<T, null> extends true ? void : TypeMismatchError<null, T>;
    undefined: IsExact<T, undefined> extends true ? void : TypeMismatchError<undefined, T>;
  };
  toBeCallable: T extends (...args: any[]) => any ? void : TypeMismatchError<"callable", T>;
  toAccept: <U>() => [U] extends [T] ? void : TypeMismatchError<`accepts ${string}`, T>;
  not: {
    toEqual: <U>() => IsExact<T, U> extends true ? TypeMismatchError<`not ${string}`, T> : void;
    toExtend: <U>() => [T] extends [U] ? TypeMismatchError<`not extends ${string}`, T> : void;
    toBe: {
      never: IsNever<T> extends true ? TypeMismatchError<"not never", T> : void;
      any: IsAny<T> extends true ? TypeMismatchError<"not any", T> : void;
    };
  };
}

// Factory function (no runtime cost - only used for type checking)
declare function expectType<T>(): ExpectType<T>;

// Helper for testing function return types
type ReturnOf<T> = T extends (...args: any[]) => infer R ? R : never;
type ParamsOf<T> = T extends (...args: infer P) => any ? P : never;

// Helper for testing promise unwrapping
type Awaited<T> = T extends Promise<infer U> ? Awaited<U> : T;

// ============================================
// Test suite examples
// ============================================

// Basic type equality tests
{
  // These compile successfully (assertions pass)
  const _1: AssertTrue<IsExact<string, string>> = true;
  const _2: AssertTrue<IsExact<{ a: number; b: string }, { a: number; b: string }>> = true;
  const _3: AssertFalse<IsExact<string, number>> = false;
  const _4: AssertTrue<IsNever<never>> = true;
  const _5: AssertFalse<IsNever<string>> = false;
  const _6: AssertTrue<IsAny<any>> = true;
  const _7: AssertFalse<IsAny<unknown>> = false;
}

// Testing generic function types
{
  function identity<T>(value: T): T {
    return value;
  }

  type IdentityReturn = ReturnOf<typeof identity>;
  // identity returns T, which is generic - we can test specific instantiations

  const strResult = identity("hello");
  const _: AssertTrue<IsExact<typeof strResult, string>> = true;

  const numResult = identity(42);
  const __: AssertTrue<IsExact<typeof numResult, number>> = true;
}

// Testing mapped types
{
  type ReadonlyDeep<T> = {
    readonly [K in keyof T]: T[K] extends object ? ReadonlyDeep<T[K]> : T[K];
  };

  interface Nested {
    a: { b: { c: number } };
    d: string;
  }

  type DeepReadonly = ReadonlyDeep<Nested>;

  // Verify the nested property is readonly
  const _1: AssertTrue<IsExact<DeepReadonly["d"], string>> = true;
  const _2: AssertTrue<IsExact<DeepReadonly["a"]["b"]["c"], number>> = true;

  // Verify readonly modifier is applied
  type HasReadonlyA = Readonly<Pick<DeepReadonly, "a">>;
  const _3: AssertTrue<IsExact<HasReadonlyA, { readonly a: ReadonlyDeep<{ b: { c: number } }> }>> = true;
}

// Testing discriminated unions
{
  type Shape =
    | { kind: "circle"; radius: number }
    | { kind: "rect"; width: number; height: number }
    | { kind: "triangle"; base: number; height: number };

  // Extract specific variants
  type Circle = Extract<Shape, { kind: "circle" }>;
  const _1: AssertTrue<IsExact<Circle, { kind: "circle"; radius: number }>> = true;

  // Exclude variants
  type NonCircle = Exclude<Shape, { kind: "circle" }>;
  const _2: AssertTrue<
    IsExact<NonCircle, { kind: "rect"; width: number; height: number } | { kind: "triangle"; base: number; height: number }>
  > = true;

  // Test kind literals
  type ShapeKind = Shape["kind"];
  const _3: AssertTrue<IsExact<ShapeKind, "circle" | "rect" | "triangle">> = true;
}

// Testing conditional types
{
  type NonNullableDeep<T> = T extends null | undefined
    ? never
    : T extends object
    ? { [K in keyof T]: NonNullableDeep<T[K]> }
    : T;

  interface MaybeNull {
    name: string | null;
    address: {
      city: string | undefined;
      zip: number | null;
    } | null;
  }

  type Cleaned = NonNullableDeep<MaybeNull>;

  const _1: AssertTrue<IsExact<Cleaned["name"], string>> = true;
  // address is cleaned recursively
  const _2: AssertFalse<IsExact<Cleaned, MaybeNull>> = false;
}

// Testing template literal types
{
  type HttpMethod = "GET" | "POST" | "PUT" | "DELETE";
  type ApiPath = "/users" | "/posts" | "/comments";
  type Endpoint = `${HttpMethod} ${ApiPath}`;

  const _1: AssertTrue<IsAssignable<"GET /users", Endpoint>> = true;
  const _2: AssertFalse<IsAssignable<"PATCH /users", Endpoint>> = false;

  // Count union members (type-level length)
  type UnionToIntersection<U> = (U extends any ? (x: U) => void : never) extends (x: infer I) => void ? I : never;
  type LastOf<T> = UnionToIntersection<T extends any ? () => T : never> extends () => infer R ? R : never;
  type UnionSize<T, Acc extends any[] = []> = [T] extends [never]
    ? Acc["length"]
    : UnionSize<Exclude<T, LastOf<T>>, [...Acc, any]>;

  // 4 methods * 3 paths = 12 endpoints
  type EndpointCount = UnionSize<Endpoint>;
  const _3: AssertTrue<IsExact<EndpointCount, 12>> = true;
}

// Testing async function types
{
  async function fetchUser(id: string): Promise<{ id: string; name: string }> {
    return { id, name: "Test" };
  }

  type FetchUserReturn = ReturnOf<typeof fetchUser>;
  const _1: AssertTrue<IsExact<FetchUserReturn, Promise<{ id: string; name: string }>>> = true;

  type FetchUserData = Awaited<FetchUserReturn>;
  const _2: AssertTrue<IsExact<FetchUserData, { id: string; name: string }>> = true;

  type FetchUserParams = ParamsOf<typeof fetchUser>;
  const _3: AssertTrue<IsExact<FetchUserParams, [id: string]>> = true;
}

// Testing class types
{
  class EventEmitter<TEvents extends Record<string, unknown[]>> {
    on<K extends keyof TEvents>(event: K, handler: (...args: TEvents[K]) => void): this {
      return this;
    }
    emit<K extends keyof TEvents>(event: K, ...args: TEvents[K]): void {}
  }

  interface AppEvents {
    login: [userId: string];
    error: [code: number, message: string];
    data: [payload: { items: string[] }];
  }

  type Emitter = EventEmitter<AppEvents>;

  // Verify the on method accepts correct event names
  type OnParams = ParamsOf<Emitter["on"]>;
  // First param should be one of the event names
  const _1: AssertTrue<IsAssignable<"login", OnParams[0]>> = true;
  const _2: AssertTrue<IsAssignable<"error", OnParams[0]>> = true;
}

console.log("All type-level tests passed at compile time");
```

This library uses TypeScript conditional types and the distributive properties of mapped types to perform compile-time assertions. The `IsExact` check uses mutual extends to verify bidirectional assignability, `IsAny` exploits the intersection trick (`0 extends 1 & T`), and branded error types produce meaningful messages when assertions fail. All checks are zero-cost at runtime since they operate purely at the type level.'''
    ),
    (
        "typescript/testing",
        r'''<think>
The user wants generic test utilities - things like type-safe builders for test data, typed mock factories, and assertion helpers that leverage TypeScript's type system. Let me build:

1. A test data builder with DeepPartial support
2. Typed factory functions that generate realistic test data
3. Assertion helpers that narrow types
4. A fixture system with typed overrides

I should make these practical utilities that actually help in testing, not just type exercises.
</think>
Create a set of TypeScript generic test utilities including: a type-safe test data builder with DeepPartial overrides, a factory function system with sequences and traits, and typed assertion helpers that narrow types in test blocks.''',
        r'''Generic test utilities with builders, factories, and typed assertions:

```typescript
// ============================================
// DeepPartial and merge utilities
// ============================================

type DeepPartial<T> = T extends object
  ? T extends Array<infer U>
    ? Array<DeepPartial<U>>
    : { [K in keyof T]?: DeepPartial<T[K]> }
  : T;

function deepMerge<T extends Record<string, unknown>>(base: T, overrides: DeepPartial<T>): T {
  const result = { ...base };

  for (const key of Object.keys(overrides) as (keyof T)[]) {
    const overrideVal = overrides[key];
    const baseVal = base[key];

    if (
      overrideVal !== undefined &&
      typeof overrideVal === "object" &&
      overrideVal !== null &&
      !Array.isArray(overrideVal) &&
      typeof baseVal === "object" &&
      baseVal !== null &&
      !Array.isArray(baseVal)
    ) {
      result[key] = deepMerge(
        baseVal as Record<string, unknown>,
        overrideVal as DeepPartial<Record<string, unknown>>
      ) as T[keyof T];
    } else if (overrideVal !== undefined) {
      result[key] = overrideVal as T[keyof T];
    }
  }

  return result;
}

// ============================================
// Test Data Builder
// ============================================

class TestDataBuilder<T extends Record<string, unknown>> {
  private data: T;
  private afterBuildHooks: ((data: T) => T)[] = [];

  constructor(private defaults: () => T) {
    this.data = defaults();
  }

  with(overrides: DeepPartial<T>): this {
    this.data = deepMerge(this.data, overrides);
    return this;
  }

  set<K extends keyof T>(key: K, value: T[K]): this {
    this.data[key] = value;
    return this;
  }

  afterBuild(hook: (data: T) => T): this {
    this.afterBuildHooks.push(hook);
    return this;
  }

  build(): T {
    let result = { ...this.data };
    for (const hook of this.afterBuildHooks) {
      result = hook(result);
    }
    // Reset for next build
    this.data = this.defaults();
    this.afterBuildHooks = [];
    return result;
  }

  buildMany(count: number, varying?: (index: number) => DeepPartial<T>): T[] {
    return Array.from({ length: count }, (_, i) => {
      const builder = new TestDataBuilder(this.defaults);
      if (varying) {
        builder.with(varying(i));
      }
      return builder.build();
    });
  }
}

function buildFrom<T extends Record<string, unknown>>(defaults: () => T): TestDataBuilder<T> {
  return new TestDataBuilder(defaults);
}

// ============================================
// Factory System with Sequences and Traits
// ============================================

class Sequence {
  private counters = new Map<string, number>();

  next(name: string = "default"): number {
    const current = this.counters.get(name) || 0;
    const next = current + 1;
    this.counters.set(name, next);
    return next;
  }

  reset(name?: string): void {
    if (name) {
      this.counters.delete(name);
    } else {
      this.counters.clear();
    }
  }
}

const globalSequence = new Sequence();

interface FactoryConfig<T, TTraits extends string = never> {
  defaults: (seq: Sequence) => T;
  traits?: Record<TTraits, (base: T, seq: Sequence) => Partial<T>>;
  afterCreate?: (entity: T) => T | Promise<T>;
}

class Factory<T extends Record<string, unknown>, TTraits extends string = never> {
  private seq: Sequence;

  constructor(private config: FactoryConfig<T, TTraits>) {
    this.seq = new Sequence();
  }

  create(overrides?: DeepPartial<T>): T {
    const base = this.config.defaults(this.seq);
    const result = overrides ? deepMerge(base, overrides) : base;
    return result;
  }

  createWithTraits(traits: TTraits[], overrides?: DeepPartial<T>): T {
    let base = this.config.defaults(this.seq);

    for (const trait of traits) {
      const traitFn = this.config.traits?.[trait];
      if (traitFn) {
        base = { ...base, ...traitFn(base, this.seq) };
      }
    }

    return overrides ? deepMerge(base, overrides) : base;
  }

  createMany(count: number, overrides?: DeepPartial<T> | ((index: number) => DeepPartial<T>)): T[] {
    return Array.from({ length: count }, (_, i) => {
      const o = typeof overrides === "function" ? overrides(i) : overrides;
      return this.create(o);
    });
  }

  async createAsync(overrides?: DeepPartial<T>): Promise<T> {
    const entity = this.create(overrides);
    if (this.config.afterCreate) {
      return this.config.afterCreate(entity);
    }
    return entity;
  }

  reset(): void {
    this.seq.reset();
  }
}

function defineFactory<T extends Record<string, unknown>, TTraits extends string = never>(
  config: FactoryConfig<T, TTraits>
): Factory<T, TTraits> {
  return new Factory(config);
}

// ============================================
// Typed Assertion Helpers
// ============================================

class AssertionError extends Error {
  constructor(message: string, public actual: unknown, public expected: unknown) {
    super(message);
    this.name = "AssertionError";
  }
}

function assertDefined<T>(value: T | null | undefined, message?: string): asserts value is T {
  if (value === null || value === undefined) {
    throw new AssertionError(
      message || `Expected value to be defined, got ${value}`,
      value,
      "defined"
    );
  }
}

function assertType<T>(
  value: unknown,
  guard: (v: unknown) => v is T,
  message?: string
): asserts value is T {
  if (!guard(value)) {
    throw new AssertionError(
      message || `Type assertion failed for value: ${JSON.stringify(value)}`,
      value,
      "matching type guard"
    );
  }
}

function assertShape<T extends Record<string, unknown>>(
  value: unknown,
  shape: { [K in keyof T]: (v: unknown) => v is T[K] }
): asserts value is T {
  if (typeof value !== "object" || value === null) {
    throw new AssertionError("Expected an object", value, "object");
  }

  const obj = value as Record<string, unknown>;
  for (const [key, guard] of Object.entries(shape)) {
    if (!(key in obj)) {
      throw new AssertionError(`Missing property: ${key}`, obj, `object with ${key}`);
    }
    if (!(guard as (v: unknown) => boolean)(obj[key])) {
      throw new AssertionError(
        `Property "${key}" failed type check`,
        obj[key],
        `valid ${key}`
      );
    }
  }
}

// Type guard factories
const isString = (v: unknown): v is string => typeof v === "string";
const isNumber = (v: unknown): v is number => typeof v === "number";
const isBoolean = (v: unknown): v is boolean => typeof v === "boolean";
const isArray = <T>(guard: (v: unknown) => v is T) =>
  (v: unknown): v is T[] => Array.isArray(v) && v.every(guard);
const isOneOf = <T extends string>(...values: T[]) =>
  (v: unknown): v is T => values.includes(v as T);

// ============================================
// Usage examples
// ============================================

// Domain types
interface User {
  id: string;
  email: string;
  name: string;
  role: "admin" | "user" | "moderator";
  profile: {
    bio: string;
    avatarUrl: string;
    settings: {
      theme: "light" | "dark";
      notifications: boolean;
    };
  };
  createdAt: Date;
}

interface Post {
  id: string;
  title: string;
  body: string;
  authorId: string;
  status: "draft" | "published" | "archived";
  tags: string[];
  publishedAt: Date | null;
}

// Factories
const userFactory = defineFactory<User, "admin" | "inactive">({
  defaults: (seq) => ({
    id: `user_${seq.next("user")}`,
    email: `user${seq.next("email")}@test.com`,
    name: `Test User ${seq.next("name")}`,
    role: "user",
    profile: {
      bio: "A test user",
      avatarUrl: `https://avatars.test.com/${seq.next("avatar")}`,
      settings: {
        theme: "light",
        notifications: true,
      },
    },
    createdAt: new Date("2024-01-01"),
  }),
  traits: {
    admin: (base) => ({
      role: "admin" as const,
      email: base.email.replace("user", "admin"),
    }),
    inactive: () => ({
      profile: {
        bio: "",
        avatarUrl: "",
        settings: { theme: "light" as const, notifications: false },
      },
    }),
  },
});

const postFactory = defineFactory<Post, "published" | "archived">({
  defaults: (seq) => ({
    id: `post_${seq.next("post")}`,
    title: `Test Post ${seq.next("title")}`,
    body: "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
    authorId: "user_1",
    status: "draft",
    tags: ["test"],
    publishedAt: null,
  }),
  traits: {
    published: () => ({
      status: "published" as const,
      publishedAt: new Date("2024-06-15"),
    }),
    archived: () => ({
      status: "archived" as const,
      publishedAt: new Date("2024-01-15"),
    }),
  },
});

// Test examples
describe("User management", () => {
  afterEach(() => {
    userFactory.reset();
    postFactory.reset();
  });

  it("creates users with builder", () => {
    const user = buildFrom(() => userFactory.create())
      .with({ name: "Alice", role: "admin" })
      .with({ profile: { settings: { theme: "dark" } } })
      .build();

    expect(user.name).toBe("Alice");
    expect(user.role).toBe("admin");
    expect(user.profile.settings.theme).toBe("dark");
    // Unmodified fields keep defaults
    expect(user.profile.settings.notifications).toBe(true);
  });

  it("creates admin users with traits", () => {
    const admin = userFactory.createWithTraits(["admin"]);
    expect(admin.role).toBe("admin");
    expect(admin.email).toContain("admin");
  });

  it("creates many users with varying data", () => {
    const users = userFactory.createMany(5, (i) => ({
      name: `User ${i}`,
      role: i === 0 ? ("admin" as const) : ("user" as const),
    }));

    expect(users).toHaveLength(5);
    expect(users[0].role).toBe("admin");
    expect(users[1].role).toBe("user");
  });

  it("validates API response shape", () => {
    const response: unknown = {
      id: "user_1",
      email: "test@test.com",
      name: "Test",
      role: "admin",
    };

    assertShape<{ id: string; email: string; name: string; role: "admin" | "user" }>(
      response,
      {
        id: isString,
        email: isString,
        name: isString,
        role: isOneOf("admin", "user"),
      }
    );

    // After assertion, response is narrowed to the correct type
    expect(response.id).toBe("user_1");
    expect(response.role).toBe("admin");
  });
});

// Declare test framework types for the example
declare function describe(name: string, fn: () => void): void;
declare function it(name: string, fn: () => void): void;
declare function afterEach(fn: () => void): void;
declare function expect(value: unknown): {
  toBe(expected: unknown): void;
  toContain(expected: string): void;
  toHaveLength(expected: number): void;
};
```

The builder supports nested `DeepPartial` overrides so you can modify deeply nested properties without reconstructing the whole object. Factories use sequences for unique IDs and emails, traits for common presets (admin, published), and `createMany` for bulk generation. The assertion helpers use TypeScript `asserts` return types to narrow types within test blocks after validation.'''
    ),
    (
        "typescript/testing",
        r'''Implement a type-safe mock system for TypeScript that creates mock objects matching interface shapes, tracks calls with typed arguments, supports typed return value configuration, and verifies call expectations with proper type inference.''',
        r'''A type-safe mock system with call tracking and typed expectations:

```typescript
// Core types for mock system
type AnyFunction = (...args: any[]) => any;

interface CallRecord<TArgs extends any[] = any[], TReturn = any> {
  args: TArgs;
  returnValue: TReturn;
  timestamp: number;
  callIndex: number;
}

interface MockFunction<TFn extends AnyFunction> {
  (...args: Parameters<TFn>): ReturnType<TFn>;
  mockReturnValue(value: ReturnType<TFn>): MockFunction<TFn>;
  mockReturnValueOnce(value: ReturnType<TFn>): MockFunction<TFn>;
  mockImplementation(fn: TFn): MockFunction<TFn>;
  mockImplementationOnce(fn: TFn): MockFunction<TFn>;
  mockResolvedValue<T>(this: MockFunction<(...args: any[]) => Promise<T>>, value: T): MockFunction<TFn>;
  mockRejectedValue(error: Error): MockFunction<TFn>;
  calls: CallRecord<Parameters<TFn>, ReturnType<TFn>>[];
  callCount: number;
  lastCall: CallRecord<Parameters<TFn>, ReturnType<TFn>> | undefined;
  calledWith(...args: Parameters<TFn>): boolean;
  nthCall(n: number): CallRecord<Parameters<TFn>, ReturnType<TFn>> | undefined;
  reset(): void;
}

function createMockFunction<TFn extends AnyFunction>(
  name: string = "mock"
): MockFunction<TFn> {
  let defaultReturn: ReturnType<TFn> | undefined;
  let defaultImpl: TFn | undefined;
  const oneTimeReturns: ReturnType<TFn>[] = [];
  const oneTimeImpls: TFn[] = [];
  const callRecords: CallRecord<Parameters<TFn>, ReturnType<TFn>>[] = [];
  let callCounter = 0;

  const mockFn = function (this: unknown, ...args: Parameters<TFn>): ReturnType<TFn> {
    let returnValue: ReturnType<TFn>;

    if (oneTimeImpls.length > 0) {
      const impl = oneTimeImpls.shift()!;
      returnValue = impl.apply(this, args);
    } else if (oneTimeReturns.length > 0) {
      returnValue = oneTimeReturns.shift()!;
    } else if (defaultImpl) {
      returnValue = defaultImpl.apply(this, args);
    } else {
      returnValue = defaultReturn as ReturnType<TFn>;
    }

    const record: CallRecord<Parameters<TFn>, ReturnType<TFn>> = {
      args,
      returnValue,
      timestamp: Date.now(),
      callIndex: callCounter++,
    };
    callRecords.push(record);

    return returnValue;
  } as MockFunction<TFn>;

  Object.defineProperty(mockFn, "calls", {
    get: () => [...callRecords],
  });

  Object.defineProperty(mockFn, "callCount", {
    get: () => callRecords.length,
  });

  Object.defineProperty(mockFn, "lastCall", {
    get: () => callRecords[callRecords.length - 1],
  });

  mockFn.mockReturnValue = (value: ReturnType<TFn>) => {
    defaultReturn = value;
    return mockFn;
  };

  mockFn.mockReturnValueOnce = (value: ReturnType<TFn>) => {
    oneTimeReturns.push(value);
    return mockFn;
  };

  mockFn.mockImplementation = (fn: TFn) => {
    defaultImpl = fn;
    return mockFn;
  };

  mockFn.mockImplementationOnce = (fn: TFn) => {
    oneTimeImpls.push(fn);
    return mockFn;
  };

  mockFn.mockResolvedValue = function <T>(
    this: MockFunction<(...args: any[]) => Promise<T>>,
    value: T
  ) {
    defaultReturn = Promise.resolve(value) as unknown as ReturnType<TFn>;
    return mockFn;
  };

  mockFn.mockRejectedValue = (error: Error) => {
    defaultReturn = Promise.reject(error) as unknown as ReturnType<TFn>;
    return mockFn;
  };

  mockFn.calledWith = (...expectedArgs: Parameters<TFn>) => {
    return callRecords.some((record) =>
      record.args.length === expectedArgs.length &&
      record.args.every((arg, i) => deepEqual(arg, expectedArgs[i]))
    );
  };

  mockFn.nthCall = (n: number) => callRecords[n];

  mockFn.reset = () => {
    callRecords.length = 0;
    callCounter = 0;
    oneTimeReturns.length = 0;
    oneTimeImpls.length = 0;
    defaultReturn = undefined;
    defaultImpl = undefined;
  };

  return mockFn;
}

function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (a === null || b === null) return false;
  if (typeof a !== typeof b) return false;
  if (typeof a !== "object") return false;

  const aObj = a as Record<string, unknown>;
  const bObj = b as Record<string, unknown>;
  const aKeys = Object.keys(aObj);
  const bKeys = Object.keys(bObj);

  if (aKeys.length !== bKeys.length) return false;
  return aKeys.every((key) => deepEqual(aObj[key], bObj[key]));
}

// Mock object creator - creates a mock matching an interface
type MockObject<T> = {
  [K in keyof T]: T[K] extends AnyFunction ? MockFunction<T[K]> : T[K];
};

function createMock<T extends Record<string, unknown>>(
  overrides?: Partial<{ [K in keyof T]: T[K] extends AnyFunction ? Partial<MockFunction<T[K]>> | T[K] : T[K] }>
): MockObject<T> {
  const handler: ProxyHandler<Record<string, unknown>> = {
    get(target, prop: string) {
      if (prop in target) return target[prop];

      // Auto-create mock functions for unknown properties
      const mockFn = createMockFunction(prop);
      target[prop] = mockFn;
      return mockFn;
    },
  };

  const base: Record<string, unknown> = {};
  if (overrides) {
    for (const [key, value] of Object.entries(overrides)) {
      base[key] = value;
    }
  }

  return new Proxy(base, handler) as MockObject<T>;
}

// Expectation builder for verification
interface MockExpectation<TFn extends AnyFunction> {
  toHaveBeenCalled(): void;
  toHaveBeenCalledTimes(count: number): void;
  toHaveBeenCalledWith(...args: Parameters<TFn>): void;
  toHaveBeenLastCalledWith(...args: Parameters<TFn>): void;
  toHaveBeenNthCalledWith(n: number, ...args: Parameters<TFn>): void;
  toHaveReturned(value: ReturnType<TFn>): void;
  not: MockExpectation<TFn>;
}

function expectMock<TFn extends AnyFunction>(mock: MockFunction<TFn>): MockExpectation<TFn> {
  let negated = false;

  function assert(condition: boolean, message: string) {
    const shouldPass = negated ? !condition : condition;
    if (!shouldPass) {
      throw new Error(negated ? `Expected NOT: ${message}` : message);
    }
  }

  const expectation: MockExpectation<TFn> = {
    toHaveBeenCalled() {
      assert(mock.callCount > 0, `Expected mock to have been called, but it was not`);
    },

    toHaveBeenCalledTimes(count: number) {
      assert(
        mock.callCount === count,
        `Expected ${count} calls, received ${mock.callCount}`
      );
    },

    toHaveBeenCalledWith(...args: Parameters<TFn>) {
      assert(
        mock.calledWith(...args),
        `Expected mock to have been called with ${JSON.stringify(args)}, calls: ${JSON.stringify(mock.calls.map((c) => c.args))}`
      );
    },

    toHaveBeenLastCalledWith(...args: Parameters<TFn>) {
      const last = mock.lastCall;
      assert(
        last !== undefined && deepEqual(last.args, args),
        `Expected last call with ${JSON.stringify(args)}, got ${JSON.stringify(last?.args)}`
      );
    },

    toHaveBeenNthCalledWith(n: number, ...args: Parameters<TFn>) {
      const call = mock.nthCall(n);
      assert(
        call !== undefined && deepEqual(call.args, args),
        `Expected call #${n} with ${JSON.stringify(args)}, got ${JSON.stringify(call?.args)}`
      );
    },

    toHaveReturned(value: ReturnType<TFn>) {
      const hasReturn = mock.calls.some((c) => deepEqual(c.returnValue, value));
      assert(hasReturn, `Expected mock to have returned ${JSON.stringify(value)}`);
    },

    get not() {
      negated = !negated;
      return expectation;
    },
  };

  return expectation;
}

// ============================================
// Usage example
// ============================================

// Service interface to mock
interface UserRepository {
  findById(id: string): Promise<{ id: string; name: string } | null>;
  findByEmail(email: string): Promise<{ id: string; name: string } | null>;
  save(user: { name: string; email: string }): Promise<{ id: string; name: string; email: string }>;
  delete(id: string): Promise<boolean>;
}

interface EmailService {
  send(to: string, subject: string, body: string): Promise<void>;
}

// Test
function testUserRegistration() {
  const repo = createMock<UserRepository>();
  const emailSvc = createMock<EmailService>();

  // Configure mock behavior - all types are inferred
  repo.findByEmail.mockResolvedValue(null); // No existing user
  repo.save.mockImplementation(async (user) => ({
    id: "new_id",
    ...user,
  }));
  emailSvc.send.mockResolvedValue(undefined);

  // Run the code under test (simplified inline)
  async function registerUser(name: string, email: string) {
    const existing = await repo.findByEmail(email);
    if (existing) throw new Error("Email taken");

    const user = await repo.save({ name, email });
    await emailSvc.send(email, "Welcome", `Hello ${name}`);
    return user;
  }

  registerUser("Alice", "alice@test.com").then((user) => {
    // Verify mock interactions - all type-safe
    expectMock(repo.findByEmail).toHaveBeenCalledWith("alice@test.com");
    expectMock(repo.save).toHaveBeenCalledWith({ name: "Alice", email: "alice@test.com" });
    expectMock(emailSvc.send).toHaveBeenCalledWith("alice@test.com", "Welcome", "Hello Alice");
    expectMock(repo.delete).not.toHaveBeenCalled();

    console.log("All mock verifications passed");
  });
}

testUserRegistration();
```

The mock system preserves full type safety: `mockReturnValue` only accepts the function's actual return type, `calledWith` requires the correct parameter types, and `createMock` auto-generates typed mock functions for every method on an interface via `Proxy`. The expectation API mirrors Jest conventions but with strict TypeScript typing throughout.'''
    ),
    (
        "typescript/testing",
        r'''Build a TypeScript fixture system for integration tests that manages typed test data lifecycle: creation with dependencies, automatic cleanup in reverse order, snapshot comparison with type-aware diffing, and scoped fixtures for nested test suites.''',
        r'''A fixture system with dependency management, cleanup, and typed diffing:

```typescript
// ============================================
// Fixture lifecycle management
// ============================================

type CleanupFn = () => void | Promise<void>;

interface FixtureDef<T> {
  name: string;
  create: (deps: Record<string, unknown>) => T | Promise<T>;
  cleanup?: (value: T) => void | Promise<void>;
  dependsOn?: string[];
}

interface FixtureInstance<T> {
  name: string;
  value: T;
  cleanup?: CleanupFn;
  scope: string;
}

class FixtureScope {
  private instances: FixtureInstance<unknown>[] = [];
  private registry = new Map<string, FixtureDef<unknown>>();
  private resolved = new Map<string, unknown>();
  private childScopes: FixtureScope[] = [];

  constructor(
    public readonly name: string,
    private parent?: FixtureScope
  ) {}

  register<T>(def: FixtureDef<T>): void {
    this.registry.set(def.name, def as FixtureDef<unknown>);
  }

  async resolve<T>(name: string): Promise<T> {
    // Check if already resolved in this scope
    if (this.resolved.has(name)) {
      return this.resolved.get(name) as T;
    }

    // Check parent scope
    if (this.parent && !this.registry.has(name)) {
      return this.parent.resolve<T>(name);
    }

    const def = this.registry.get(name);
    if (!def) {
      throw new Error(`Fixture "${name}" not registered in scope "${this.name}"`);
    }

    // Resolve dependencies first
    const deps: Record<string, unknown> = {};
    if (def.dependsOn) {
      for (const depName of def.dependsOn) {
        deps[depName] = await this.resolve(depName);
      }
    }

    // Create the fixture
    const value = await def.create(deps);
    this.resolved.set(name, value);

    // Track for cleanup
    const instance: FixtureInstance<unknown> = {
      name,
      value,
      scope: this.name,
    };

    if (def.cleanup) {
      const cleanupFn = def.cleanup;
      instance.cleanup = () => cleanupFn(value);
    }

    this.instances.push(instance);
    return value as T;
  }

  createChild(name: string): FixtureScope {
    const child = new FixtureScope(name, this);
    this.childScopes.push(child);
    return child;
  }

  async teardown(): Promise<void> {
    // Teardown children first
    for (const child of this.childScopes.reverse()) {
      await child.teardown();
    }

    // Cleanup in reverse creation order
    for (const instance of this.instances.reverse()) {
      if (instance.cleanup) {
        try {
          await instance.cleanup();
        } catch (err) {
          console.error(`Cleanup failed for fixture "${instance.name}":`, err);
        }
      }
    }

    this.instances = [];
    this.resolved.clear();
    this.childScopes = [];
  }
}

// ============================================
// Typed snapshot diffing
// ============================================

interface DiffEntry {
  path: string;
  type: "added" | "removed" | "changed" | "type_changed";
  expected?: unknown;
  actual?: unknown;
}

function typedDiff(expected: unknown, actual: unknown, path: string = "$"): DiffEntry[] {
  const diffs: DiffEntry[] = [];

  // Type mismatch
  if (typeof expected !== typeof actual) {
    diffs.push({
      path,
      type: "type_changed",
      expected: `${typeof expected}(${JSON.stringify(expected)})`,
      actual: `${typeof actual}(${JSON.stringify(actual)})`,
    });
    return diffs;
  }

  // Null checks
  if (expected === null || actual === null) {
    if (expected !== actual) {
      diffs.push({ path, type: "changed", expected, actual });
    }
    return diffs;
  }

  // Primitives
  if (typeof expected !== "object") {
    if (expected !== actual) {
      diffs.push({ path, type: "changed", expected, actual });
    }
    return diffs;
  }

  // Arrays
  if (Array.isArray(expected) && Array.isArray(actual)) {
    const maxLen = Math.max(expected.length, actual.length);
    for (let i = 0; i < maxLen; i++) {
      if (i >= expected.length) {
        diffs.push({ path: `${path}[${i}]`, type: "added", actual: actual[i] });
      } else if (i >= actual.length) {
        diffs.push({ path: `${path}[${i}]`, type: "removed", expected: expected[i] });
      } else {
        diffs.push(...typedDiff(expected[i], actual[i], `${path}[${i}]`));
      }
    }
    return diffs;
  }

  // Date comparison
  if (expected instanceof Date && actual instanceof Date) {
    if (expected.getTime() !== actual.getTime()) {
      diffs.push({ path, type: "changed", expected: expected.toISOString(), actual: actual.toISOString() });
    }
    return diffs;
  }

  // Objects
  const expectedObj = expected as Record<string, unknown>;
  const actualObj = actual as Record<string, unknown>;
  const allKeys = new Set([...Object.keys(expectedObj), ...Object.keys(actualObj)]);

  for (const key of allKeys) {
    const childPath = `${path}.${key}`;
    if (!(key in expectedObj)) {
      diffs.push({ path: childPath, type: "added", actual: actualObj[key] });
    } else if (!(key in actualObj)) {
      diffs.push({ path: childPath, type: "removed", expected: expectedObj[key] });
    } else {
      diffs.push(...typedDiff(expectedObj[key], actualObj[key], childPath));
    }
  }

  return diffs;
}

// Snapshot storage and comparison
class SnapshotManager {
  private snapshots = new Map<string, string>();
  private updateMode: boolean;

  constructor(updateMode: boolean = false) {
    this.updateMode = updateMode;
  }

  assert<T>(name: string, value: T, serializer?: (v: T) => string): void {
    const serialized = serializer ? serializer(value) : JSON.stringify(value, null, 2);

    if (this.updateMode || !this.snapshots.has(name)) {
      this.snapshots.set(name, serialized);
      return;
    }

    const expected = this.snapshots.get(name)!;
    if (serialized !== expected) {
      const expectedParsed = JSON.parse(expected);
      const actualParsed = JSON.parse(serialized);
      const diffs = typedDiff(expectedParsed, actualParsed);

      const diffReport = diffs
        .map((d) => {
          switch (d.type) {
            case "added": return `  + ${d.path}: ${JSON.stringify(d.actual)}`;
            case "removed": return `  - ${d.path}: ${JSON.stringify(d.expected)}`;
            case "changed": return `  ~ ${d.path}: ${JSON.stringify(d.expected)} -> ${JSON.stringify(d.actual)}`;
            case "type_changed": return `  ! ${d.path}: type ${d.expected} -> ${d.actual}`;
          }
        })
        .join("\n");

      throw new Error(`Snapshot "${name}" mismatch:\n${diffReport}`);
    }
  }
}

// ============================================
// Integration: test suite helper
// ============================================

interface TestContext {
  fixtures: FixtureScope;
  snapshots: SnapshotManager;
}

function createTestSuite(name: string) {
  const rootScope = new FixtureScope(name);
  const snapshots = new SnapshotManager();

  return {
    fixture<T>(def: FixtureDef<T>): void {
      rootScope.register(def);
    },

    describe(suiteName: string, fn: (ctx: TestContext) => void): void {
      const childScope = rootScope.createChild(suiteName);
      const ctx: TestContext = { fixtures: childScope, snapshots };

      // In a real test runner, this would integrate with beforeEach/afterEach
      console.log(`Suite: ${suiteName}`);
      fn(ctx);
    },

    async teardownAll(): Promise<void> {
      await rootScope.teardown();
    },
  };
}

// ============================================
// Usage example
// ============================================

interface TestUser { id: string; name: string; email: string }
interface TestProject { id: string; name: string; ownerId: string }
interface TestTask { id: string; title: string; projectId: string; assigneeId: string }

const suite = createTestSuite("integration");

// Register fixtures with dependencies
suite.fixture<TestUser>({
  name: "user",
  create: async () => {
    // In reality, this would insert into a test database
    const user = { id: "u1", name: "Test User", email: "test@test.com" };
    console.log("Created user fixture");
    return user;
  },
  cleanup: async (user) => {
    console.log(`Cleaning up user ${user.id}`);
  },
});

suite.fixture<TestProject>({
  name: "project",
  dependsOn: ["user"],
  create: async (deps) => {
    const user = deps.user as TestUser;
    const project = { id: "p1", name: "Test Project", ownerId: user.id };
    console.log(`Created project fixture (owner: ${user.id})`);
    return project;
  },
  cleanup: async (project) => {
    console.log(`Cleaning up project ${project.id}`);
  },
});

suite.fixture<TestTask>({
  name: "task",
  dependsOn: ["project", "user"],
  create: async (deps) => {
    const project = deps.project as TestProject;
    const user = deps.user as TestUser;
    const task = { id: "t1", title: "Test Task", projectId: project.id, assigneeId: user.id };
    console.log(`Created task fixture (project: ${project.id}, assignee: ${user.id})`);
    return task;
  },
  cleanup: async (task) => {
    console.log(`Cleaning up task ${task.id}`);
  },
});

// Use in tests
suite.describe("task management", async (ctx) => {
  const user = await ctx.fixtures.resolve<TestUser>("user");
  const project = await ctx.fixtures.resolve<TestProject>("project");
  const task = await ctx.fixtures.resolve<TestTask>("task");

  console.log("Task assignee:", task.assigneeId);
  console.log("Project owner:", project.ownerId);

  // Snapshot testing with typed diff
  ctx.snapshots.assert("task-shape", task);

  // On subsequent runs, any change in shape produces a clear diff report
});

// Cleanup happens in reverse: task -> project -> user
suite.teardownAll().then(() => console.log("All fixtures cleaned up"));
```

The fixture system resolves dependencies automatically via topological ordering (resolving `task` triggers `project` which triggers `user`), cleans up in reverse creation order, and supports scoped fixtures for nested test suites where child fixtures are torn down before parent ones. The snapshot diff engine produces path-annotated reports showing exactly which fields changed, were added, or were removed.'''
    ),
    (
        "typescript/testing",
        r'''Create a TypeScript type-safe test fixture builder for API endpoint testing that generates typed request/response pairs, validates response schemas, and supports parameterized test cases with inference from endpoint definitions.''',
        r'''A type-safe API test fixture builder with endpoint definitions and parameterized cases:

```typescript
// ============================================
// Endpoint definition types
// ============================================

interface EndpointDef<
  TMethod extends string = string,
  TPath extends string = string,
  TParams = void,
  TQuery = void,
  TBody = void,
  TResponse = unknown,
  TErrors extends Record<number, unknown> = {}
> {
  method: TMethod;
  path: TPath;
  _params: TParams;
  _query: TQuery;
  _body: TBody;
  _response: TResponse;
  _errors: TErrors;
}

function endpoint<
  TMethod extends "GET" | "POST" | "PUT" | "DELETE" | "PATCH",
  TPath extends string
>(method: TMethod, path: TPath) {
  type Def = EndpointDef<TMethod, TPath>;
  return {
    params<P>() {
      return this as unknown as EndpointBuilder<TMethod, TPath, P, void, void, unknown, {}>;
    },
    query<Q>() {
      return this as unknown as EndpointBuilder<TMethod, TPath, void, Q, void, unknown, {}>;
    },
    body<B>() {
      return this as unknown as EndpointBuilder<TMethod, TPath, void, void, B, unknown, {}>;
    },
    response<R>() {
      return this as unknown as EndpointBuilder<TMethod, TPath, void, void, void, R, {}>;
    },
  } as EndpointBuilder<TMethod, TPath, void, void, void, unknown, {}>;
}

interface EndpointBuilder<TMethod, TPath, TParams, TQuery, TBody, TResponse, TErrors extends Record<number, unknown>> {
  params<P>(): EndpointBuilder<TMethod, TPath, P, TQuery, TBody, TResponse, TErrors>;
  query<Q>(): EndpointBuilder<TMethod, TPath, TParams, Q, TBody, TResponse, TErrors>;
  body<B>(): EndpointBuilder<TMethod, TPath, TParams, TQuery, B, TResponse, TErrors>;
  response<R>(): EndpointBuilder<TMethod, TPath, TParams, TQuery, TBody, R, TErrors>;
  errors<E extends Record<number, unknown>>(): EndpointBuilder<TMethod, TPath, TParams, TQuery, TBody, TResponse, E>;
  build(): EndpointDef<TMethod & string, TPath & string, TParams, TQuery, TBody, TResponse, TErrors>;
}

// ============================================
// Test case builder
// ============================================

interface TestCase<TEndpoint extends EndpointDef> {
  name: string;
  description?: string;
  request: RequestShape<TEndpoint>;
  expectedStatus: number;
  expectedResponse?: TEndpoint["_response"];
  expectedError?: unknown;
  setup?: () => Promise<void>;
  teardown?: () => Promise<void>;
  assertions?: (response: unknown, status: number) => void;
}

type RequestShape<TEndpoint extends EndpointDef> =
  (TEndpoint["_params"] extends void ? {} : { params: TEndpoint["_params"] }) &
  (TEndpoint["_query"] extends void ? {} : { query: TEndpoint["_query"] }) &
  (TEndpoint["_body"] extends void ? {} : { body: TEndpoint["_body"] }) &
  { headers?: Record<string, string> };

class EndpointTestBuilder<TEndpoint extends EndpointDef> {
  private cases: TestCase<TEndpoint>[] = [];
  private globalSetup?: () => Promise<void>;
  private globalTeardown?: () => Promise<void>;
  private baseHeaders: Record<string, string> = {};

  constructor(
    private endpointDef: TEndpoint,
    private baseUrl: string
  ) {}

  withAuth(token: string): this {
    this.baseHeaders["Authorization"] = `Bearer ${token}`;
    return this;
  }

  withHeader(key: string, value: string): this {
    this.baseHeaders[key] = value;
    return this;
  }

  beforeAll(fn: () => Promise<void>): this {
    this.globalSetup = fn;
    return this;
  }

  afterAll(fn: () => Promise<void>): this {
    this.globalTeardown = fn;
    return this;
  }

  testCase(tc: TestCase<TEndpoint>): this {
    this.cases.push(tc);
    return this;
  }

  // Parameterized test cases
  parameterized<TParam>(
    name: string,
    params: TParam[],
    buildCase: (param: TParam, index: number) => Omit<TestCase<TEndpoint>, "name">
  ): this {
    for (let i = 0; i < params.length; i++) {
      const tc = buildCase(params[i], i);
      this.cases.push({
        ...tc,
        name: `${name} [${i}]: ${JSON.stringify(params[i]).slice(0, 80)}`,
      } as TestCase<TEndpoint>);
    }
    return this;
  }

  private buildUrl(request: RequestShape<TEndpoint>): string {
    let path: string = (this.endpointDef as { path: string }).path;

    // Replace path params
    if ("params" in request && request.params) {
      const params = request.params as Record<string, string>;
      for (const [key, value] of Object.entries(params)) {
        path = path.replace(`:${key}`, encodeURIComponent(value));
      }
    }

    // Add query params
    if ("query" in request && request.query) {
      const query = request.query as Record<string, unknown>;
      const searchParams = new URLSearchParams();
      for (const [key, value] of Object.entries(query)) {
        if (value !== undefined) searchParams.set(key, String(value));
      }
      const qs = searchParams.toString();
      if (qs) path += `?${qs}`;
    }

    return `${this.baseUrl}${path}`;
  }

  async run(): Promise<TestReport> {
    const results: TestResult[] = [];

    if (this.globalSetup) await this.globalSetup();

    for (const tc of this.cases) {
      const result = await this.runCase(tc);
      results.push(result);
    }

    if (this.globalTeardown) await this.globalTeardown();

    const passed = results.filter((r) => r.passed).length;
    return {
      endpoint: `${(this.endpointDef as { method: string }).method} ${(this.endpointDef as { path: string }).path}`,
      total: results.length,
      passed,
      failed: results.length - passed,
      results,
    };
  }

  private async runCase(tc: TestCase<TEndpoint>): Promise<TestResult> {
    const startTime = performance.now();

    try {
      if (tc.setup) await tc.setup();

      const url = this.buildUrl(tc.request);
      const method = (this.endpointDef as { method: string }).method;

      const fetchInit: RequestInit = {
        method,
        headers: {
          "Content-Type": "application/json",
          ...this.baseHeaders,
          ...("headers" in tc.request ? (tc.request as { headers?: Record<string, string> }).headers : {}),
        },
      };

      if ("body" in tc.request && (tc.request as { body?: unknown }).body) {
        fetchInit.body = JSON.stringify((tc.request as { body: unknown }).body);
      }

      const response = await fetch(url, fetchInit);
      const status = response.status;
      const body = await response.json().catch(() => null);
      const duration = performance.now() - startTime;

      // Check status
      if (status !== tc.expectedStatus) {
        return {
          name: tc.name,
          passed: false,
          duration,
          error: `Expected status ${tc.expectedStatus}, got ${status}`,
        };
      }

      // Check response body
      if (tc.expectedResponse !== undefined) {
        const diffs = diffObjects(tc.expectedResponse, body);
        if (diffs.length > 0) {
          return {
            name: tc.name,
            passed: false,
            duration,
            error: `Response mismatch:\n${diffs.join("\n")}`,
          };
        }
      }

      // Run custom assertions
      if (tc.assertions) {
        tc.assertions(body, status);
      }

      if (tc.teardown) await tc.teardown();

      return { name: tc.name, passed: true, duration };
    } catch (err) {
      return {
        name: tc.name,
        passed: false,
        duration: performance.now() - startTime,
        error: err instanceof Error ? err.message : String(err),
      };
    }
  }
}

function diffObjects(expected: unknown, actual: unknown, path: string = "$"): string[] {
  const diffs: string[] = [];

  if (expected === actual) return diffs;
  if (expected === null || actual === null || typeof expected !== typeof actual) {
    diffs.push(`${path}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
    return diffs;
  }

  if (typeof expected !== "object") {
    if (expected !== actual) {
      diffs.push(`${path}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
    }
    return diffs;
  }

  if (Array.isArray(expected) && Array.isArray(actual)) {
    const maxLen = Math.max(expected.length, actual.length);
    for (let i = 0; i < maxLen; i++) {
      diffs.push(...diffObjects(expected[i], actual[i], `${path}[${i}]`));
    }
    return diffs;
  }

  const exp = expected as Record<string, unknown>;
  const act = actual as Record<string, unknown>;
  const keys = new Set([...Object.keys(exp), ...Object.keys(act)]);
  for (const key of keys) {
    diffs.push(...diffObjects(exp[key], act[key], `${path}.${key}`));
  }

  return diffs;
}

interface TestResult {
  name: string;
  passed: boolean;
  duration: number;
  error?: string;
}

interface TestReport {
  endpoint: string;
  total: number;
  passed: number;
  failed: number;
  results: TestResult[];
}

function testEndpoint<TEndpoint extends EndpointDef>(
  def: TEndpoint,
  baseUrl: string
): EndpointTestBuilder<TEndpoint> {
  return new EndpointTestBuilder(def, baseUrl);
}

// ============================================
// Usage
// ============================================

// Define endpoints
interface User { id: string; name: string; email: string; role: string }
interface CreateUserBody { name: string; email: string; role?: string }
interface ListUsersQuery { page?: number; limit?: number; role?: string }

const getUserEndpoint = {
  method: "GET" as const,
  path: "/users/:id",
  _params: {} as { id: string },
  _query: void 0 as void,
  _body: void 0 as void,
  _response: {} as User,
  _errors: {} as { 404: { message: string } },
};

const listUsersEndpoint = {
  method: "GET" as const,
  path: "/users",
  _params: void 0 as void,
  _query: {} as ListUsersQuery,
  _body: void 0 as void,
  _response: {} as { users: User[]; total: number },
  _errors: {},
};

const createUserEndpoint = {
  method: "POST" as const,
  path: "/users",
  _params: void 0 as void,
  _query: void 0 as void,
  _body: {} as CreateUserBody,
  _response: {} as User,
  _errors: {} as { 400: { message: string; fields: Record<string, string> } },
};

// Build test suites
const getUserTests = testEndpoint(getUserEndpoint, "https://api.test.com")
  .withAuth("test-token")
  .testCase({
    name: "returns user by ID",
    request: { params: { id: "user_1" } },
    expectedStatus: 200,
    expectedResponse: { id: "user_1", name: "Alice", email: "alice@test.com", role: "admin" },
  })
  .testCase({
    name: "returns 404 for unknown user",
    request: { params: { id: "nonexistent" } },
    expectedStatus: 404,
  });

const createUserTests = testEndpoint(createUserEndpoint, "https://api.test.com")
  .withAuth("admin-token")
  .parameterized(
    "validates required fields",
    [
      { body: { name: "", email: "test@test.com" }, expectStatus: 400 },
      { body: { name: "Test", email: "" }, expectStatus: 400 },
      { body: { name: "Test", email: "invalid" }, expectStatus: 400 },
      { body: { name: "Test", email: "test@test.com" }, expectStatus: 201 },
    ],
    (param) => ({
      request: { body: param.body as CreateUserBody },
      expectedStatus: param.expectStatus,
    })
  );

// Run all tests
async function runAllTests() {
  const reports = await Promise.all([
    getUserTests.run(),
    createUserTests.run(),
  ]);

  for (const report of reports) {
    console.log(`\n${report.endpoint}: ${report.passed}/${report.total} passed`);
    for (const r of report.results) {
      const status = r.passed ? "PASS" : "FAIL";
      console.log(`  [${status}] ${r.name} (${r.duration.toFixed(0)}ms)`);
      if (r.error) console.log(`    Error: ${r.error}`);
    }
  }
}
```

The endpoint definitions carry their types as phantom fields (`_params`, `_body`, `_response`), and the test builder enforces that request shapes match the endpoint definition. The `parameterized` method generates named test cases from data arrays, and the runner validates both status codes and response body shapes with path-level diff reporting.'''
    ),
]
