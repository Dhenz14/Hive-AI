"""
Batch p1075: TypeScript/React production pairs - Runtime Validation
Topics: Zod-like schemas, type guards, discriminated unions, form validation, API validation
"""

PAIRS = [
    ("typescript/validation_schema", r'''<think>
Building a Zod-like schema validation library from scratch is a great way to demonstrate runtime validation with TypeScript type inference. The key challenge is making the schema definition infer the output type automatically - could this be done with just functions returning type guards? Hmm, type guards narrow existing types but do not construct new ones from schema definitions. So a class-based approach with generic type parameters is necessary.

I considered using a plain object DSL like `{ type: "string", min: 3 }` for schema definitions, but wait - that approach loses the type inference chain. You would need a separate step to map the schema definition to a TypeScript type. With classes, the generic parameter `Schema<Output>` carries the inferred type through every operation, and the `Infer<S>` utility type extracts it.

Core design:
1. Each schema type extends a base Schema class with a parse method - the generic Output parameter is the inferred type
2. Object schemas compose child schemas - this is where the inference gets interesting because we need to map over the shape's schema types to produce the output type
3. The parse method validates and returns typed data
4. Chaining methods for optional, default, transform - each returns a new Schema with a different Output type, so `s.string().optional()` infers `string | undefined`
</think>

Build a runtime schema validation library in TypeScript (similar to Zod) that infers output types from schema definitions, supporting primitives, objects, arrays, optional fields, and transformations.''', r'''<think>
I will build a minimal but functional schema validation library. Each schema type must carry its output type as a generic parameter so TypeScript can infer the validated type. The key is the Infer utility type that uses `S extends Schema<infer O> ? O : never` to extract the output type from any schema.

I initially thought about making parse return `T | null` to signal validation failure, but actually throwing a ValidationError is better because it carries structured error information (path, message, nested issues). The safeParse method can wrap this in a success/failure discriminated union for callers who prefer not to catch exceptions.

For the ObjectSchema, I need to collect ALL field errors rather than failing on the first one. I considered using Promise.allSettled-style batching, but wait - validation is synchronous here, so a simple loop accumulating errors into an array works. The combine static method on ValidationError merges multiple field errors into a single error with all issues listed.
</think>

// Base schema type that all validators extend
abstract class Schema<Output> {
  abstract parse(input: unknown): Output;

  safeParse(input: unknown): { success: true; data: Output } | { success: false; error: ValidationError } {
    try {
      const data = this.parse(input);
      return { success: true, data };
    } catch (err) {
      if (err instanceof ValidationError) {
        return { success: false, error: err };
      }
      throw err;
    }
  }

  optional(): OptionalSchema<Output> {
    return new OptionalSchema(this);
  }

  nullable(): NullableSchema<Output> {
    return new NullableSchema(this);
  }

  default(value: Output): DefaultSchema<Output> {
    return new DefaultSchema(this, value);
  }

  transform<T>(fn: (value: Output) => T): TransformSchema<Output, T> {
    return new TransformSchema(this, fn);
  }

  refine(predicate: (value: Output) => boolean, message?: string): RefinedSchema<Output> {
    return new RefinedSchema(this, predicate, message || "Validation failed");
  }

  pipe<T>(next: Schema<T>): PipeSchema<Output, T> {
    return new PipeSchema(this, next);
  }
}

// Utility type to extract the output type from a schema
type Infer<S extends Schema<any>> = S extends Schema<infer O> ? O : never;

class ValidationError extends Error {
  constructor(
    message: string,
    public path: (string | number)[] = [],
    public issues: Array<{ path: (string | number)[]; message: string }> = []
  ) {
    super(message);
    this.name = "ValidationError";
    if (issues.length === 0) {
      this.issues = [{ path, message }];
    }
  }

  static combine(errors: ValidationError[]): ValidationError {
    const issues = errors.flatMap((e) => e.issues);
    return new ValidationError(
      issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; "),
      [],
      issues
    );
  }
}

// Primitive schemas
class StringSchema extends Schema<string> {
  private checks: Array<(value: string) => string | null> = [];

  parse(input: unknown): string {
    if (typeof input !== "string") {
      throw new ValidationError(`Expected string, got ${typeof input}`);
    }
    for (const check of this.checks) {
      const error = check(input);
      if (error) throw new ValidationError(error);
    }
    return input;
  }

  min(length: number, message?: string): this {
    this.checks.push((v) =>
      v.length < length ? (message || `Minimum length is ${length}`) : null
    );
    return this;
  }

  max(length: number, message?: string): this {
    this.checks.push((v) =>
      v.length > length ? (message || `Maximum length is ${length}`) : null
    );
    return this;
  }

  email(message?: string): this {
    this.checks.push((v) =>
      /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) ? null : (message || "Invalid email")
    );
    return this;
  }

  url(message?: string): this {
    this.checks.push((v) => {
      try { new URL(v); return null; } catch { return message || "Invalid URL"; }
    });
    return this;
  }

  regex(pattern: RegExp, message?: string): this {
    this.checks.push((v) =>
      pattern.test(v) ? null : (message || `Does not match pattern ${pattern}`)
    );
    return this;
  }

  trim(): TransformSchema<string, string> {
    return this.transform((v) => v.trim());
  }
}

class NumberSchema extends Schema<number> {
  private checks: Array<(value: number) => string | null> = [];

  parse(input: unknown): number {
    const num = typeof input === "string" ? Number(input) : input;
    if (typeof num !== "number" || Number.isNaN(num)) {
      throw new ValidationError(`Expected number, got ${typeof input}`);
    }
    for (const check of this.checks) {
      const error = check(num);
      if (error) throw new ValidationError(error);
    }
    return num;
  }

  min(value: number): this {
    this.checks.push((v) => v < value ? `Must be >= ${value}` : null);
    return this;
  }

  max(value: number): this {
    this.checks.push((v) => v > value ? `Must be <= ${value}` : null);
    return this;
  }

  int(): this {
    this.checks.push((v) => Number.isInteger(v) ? null : "Must be an integer");
    return this;
  }

  positive(): this {
    this.checks.push((v) => v > 0 ? null : "Must be positive");
    return this;
  }
}

class BooleanSchema extends Schema<boolean> {
  parse(input: unknown): boolean {
    if (typeof input !== "boolean") {
      throw new ValidationError(`Expected boolean, got ${typeof input}`);
    }
    return input;
  }
}

// Object schema with inferred type from shape
class ObjectSchema<Shape extends Record<string, Schema<any>>> extends Schema<{
  [K in keyof Shape]: Infer<Shape[K]>;
}> {
  constructor(private shape: Shape) {
    super();
  }

  parse(input: unknown): { [K in keyof Shape]: Infer<Shape[K]> } {
    if (typeof input !== "object" || input === null || Array.isArray(input)) {
      throw new ValidationError(`Expected object, got ${typeof input}`);
    }
    const obj = input as Record<string, unknown>;
    const result: Record<string, unknown> = {};
    const errors: ValidationError[] = [];

    for (const [key, schema] of Object.entries(this.shape)) {
      try {
        result[key] = schema.parse(obj[key]);
      } catch (err) {
        if (err instanceof ValidationError) {
          errors.push(new ValidationError(err.message, [key, ...err.path]));
        } else {
          throw err;
        }
      }
    }

    if (errors.length > 0) {
      throw ValidationError.combine(errors);
    }
    return result as any;
  }

  partial(): ObjectSchema<{ [K in keyof Shape]: OptionalSchema<Infer<Shape[K]>> }> {
    const partialShape: Record<string, Schema<any>> = {};
    for (const [key, schema] of Object.entries(this.shape)) {
      partialShape[key] = schema.optional();
    }
    return new ObjectSchema(partialShape) as any;
  }

  pick<K extends keyof Shape>(...keys: K[]): ObjectSchema<Pick<Shape, K>> {
    const picked: Record<string, Schema<any>> = {};
    for (const key of keys) {
      picked[key as string] = this.shape[key];
    }
    return new ObjectSchema(picked) as any;
  }

  omit<K extends keyof Shape>(...keys: K[]): ObjectSchema<Omit<Shape, K>> {
    const omitted: Record<string, Schema<any>> = {};
    const keySet = new Set(keys as string[]);
    for (const [key, schema] of Object.entries(this.shape)) {
      if (!keySet.has(key)) omitted[key] = schema;
    }
    return new ObjectSchema(omitted) as any;
  }

  extend<E extends Record<string, Schema<any>>>(
    extension: E
  ): ObjectSchema<Shape & E> {
    return new ObjectSchema({ ...this.shape, ...extension }) as any;
  }
}

// Array schema
class ArraySchema<Item extends Schema<any>> extends Schema<Infer<Item>[]> {
  private minLen?: number;
  private maxLen?: number;

  constructor(private itemSchema: Item) {
    super();
  }

  parse(input: unknown): Infer<Item>[] {
    if (!Array.isArray(input)) {
      throw new ValidationError(`Expected array, got ${typeof input}`);
    }
    if (this.minLen !== undefined && input.length < this.minLen) {
      throw new ValidationError(`Array must have at least ${this.minLen} items`);
    }
    if (this.maxLen !== undefined && input.length > this.maxLen) {
      throw new ValidationError(`Array must have at most ${this.maxLen} items`);
    }
    const errors: ValidationError[] = [];
    const result = input.map((item, index) => {
      try {
        return this.itemSchema.parse(item);
      } catch (err) {
        if (err instanceof ValidationError) {
          errors.push(new ValidationError(err.message, [index, ...err.path]));
        }
        return undefined;
      }
    });
    if (errors.length > 0) throw ValidationError.combine(errors);
    return result as Infer<Item>[];
  }

  min(length: number): this { this.minLen = length; return this; }
  max(length: number): this { this.maxLen = length; return this; }
  nonempty(): this { this.minLen = 1; return this; }
}

// Wrapper schemas
class OptionalSchema<T> extends Schema<T | undefined> {
  constructor(private inner: Schema<T>) { super(); }
  parse(input: unknown): T | undefined {
    if (input === undefined) return undefined;
    return this.inner.parse(input);
  }
}

class NullableSchema<T> extends Schema<T | null> {
  constructor(private inner: Schema<T>) { super(); }
  parse(input: unknown): T | null {
    if (input === null) return null;
    return this.inner.parse(input);
  }
}

class DefaultSchema<T> extends Schema<T> {
  constructor(private inner: Schema<T>, private defaultValue: T) { super(); }
  parse(input: unknown): T {
    if (input === undefined) return this.defaultValue;
    return this.inner.parse(input);
  }
}

class TransformSchema<Input, Output> extends Schema<Output> {
  constructor(private inner: Schema<Input>, private fn: (v: Input) => Output) { super(); }
  parse(input: unknown): Output {
    return this.fn(this.inner.parse(input));
  }
}

class RefinedSchema<T> extends Schema<T> {
  constructor(private inner: Schema<T>, private pred: (v: T) => boolean, private msg: string) { super(); }
  parse(input: unknown): T {
    const value = this.inner.parse(input);
    if (!this.pred(value)) throw new ValidationError(this.msg);
    return value;
  }
}

class PipeSchema<A, B> extends Schema<B> {
  constructor(private first: Schema<A>, private second: Schema<B>) { super(); }
  parse(input: unknown): B {
    return this.second.parse(this.first.parse(input));
  }
}

// Factory functions
const s = {
  string: () => new StringSchema(),
  number: () => new NumberSchema(),
  boolean: () => new BooleanSchema(),
  object: <S extends Record<string, Schema<any>>>(shape: S) => new ObjectSchema(shape),
  array: <I extends Schema<any>>(item: I) => new ArraySchema(item),
};

export { s, Schema, Infer, ValidationError };
'''),

    ("typescript/validation_type_guards", r'''Build comprehensive TypeScript type guard patterns including narrowing with discriminated unions, assertion functions, branded type guards, and a type-safe exhaustive switch utility.''', r'''// Production type guard patterns for TypeScript

// Basic type guards with proper narrowing
function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isNumber(value: unknown): value is number {
  return typeof value === "number" && !Number.isNaN(value);
}

function isNonNull<T>(value: T | null | undefined): value is T {
  return value !== null && value !== undefined;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

// Assertion functions - throw instead of returning boolean
function assertNonNull<T>(
  value: T | null | undefined,
  message?: string
): asserts value is T {
  if (value === null || value === undefined) {
    throw new Error(message || "Expected non-null value");
  }
}

function assertString(value: unknown, name = "value"): asserts value is string {
  if (typeof value !== "string") {
    throw new TypeError(`Expected ${name} to be string, got ${typeof value}`);
  }
}

function assertInstanceOf<T>(
  value: unknown,
  constructor: new (...args: any[]) => T,
  message?: string
): asserts value is T {
  if (!(value instanceof constructor)) {
    throw new TypeError(
      message || `Expected instance of ${constructor.name}`
    );
  }
}

// Discriminated union patterns
interface LoadingState {
  status: "loading";
}

interface SuccessState<T> {
  status: "success";
  data: T;
  timestamp: number;
}

interface ErrorState {
  status: "error";
  error: Error;
  retryCount: number;
}

type AsyncState<T> = LoadingState | SuccessState<T> | ErrorState;

// Type guards for discriminated unions
function isLoading<T>(state: AsyncState<T>): state is LoadingState {
  return state.status === "loading";
}

function isSuccess<T>(state: AsyncState<T>): state is SuccessState<T> {
  return state.status === "success";
}

function isError<T>(state: AsyncState<T>): state is ErrorState {
  return state.status === "error";
}

// Exhaustive switch helper - compile error if a case is missing
function exhaustiveCheck(value: never): never {
  throw new Error(`Unhandled discriminant: ${JSON.stringify(value)}`);
}

function handleState<T>(state: AsyncState<T>): string {
  switch (state.status) {
    case "loading":
      return "Loading...";
    case "success":
      return `Data: ${JSON.stringify(state.data)}`;
    case "error":
      return `Error: ${state.error.message}`;
    default:
      return exhaustiveCheck(state);
  }
}

// Generic type guard factory
function createTypeGuard<T>(
  check: (value: unknown) => boolean
): (value: unknown) => value is T {
  return (value: unknown): value is T => check(value);
}

// Object shape guard - validates structure at runtime
type ShapeGuard<T> = {
  [K in keyof T]: (value: unknown) => value is T[K];
};

function createObjectGuard<T extends Record<string, unknown>>(
  shape: ShapeGuard<T>
): (value: unknown) => value is T {
  return (value: unknown): value is T => {
    if (!isRecord(value)) return false;
    for (const [key, guard] of Object.entries(shape)) {
      if (!(guard as (v: unknown) => boolean)(value[key])) {
        return false;
      }
    }
    return true;
  };
}

// Array guard
function isArrayOf<T>(
  guard: (value: unknown) => value is T
): (value: unknown) => value is T[] {
  return (value: unknown): value is T[] => {
    return Array.isArray(value) && value.every(guard);
  };
}

// Branded type guards
declare const __brand: unique symbol;
type Brand<T, B extends string> = T & { readonly [__brand]: B };

type PositiveNumber = Brand<number, "Positive">;
type NonEmptyString = Brand<string, "NonEmpty">;
type EmailAddress = Brand<string, "Email">;
type SafeInteger = Brand<number, "SafeInteger">;

function isPositive(n: number): n is PositiveNumber {
  return n > 0;
}

function isNonEmpty(s: string): s is NonEmptyString {
  return s.length > 0;
}

function isEmail(s: string): s is EmailAddress {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s);
}

function isSafeInteger(n: number): n is SafeInteger {
  return Number.isSafeInteger(n);
}

// Assertion versions for branded types
function assertPositive(n: number): asserts n is PositiveNumber {
  if (n <= 0) throw new RangeError(`Expected positive number, got ${n}`);
}

function assertEmail(s: string): asserts s is EmailAddress {
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s)) {
    throw new Error(`Invalid email: ${s}`);
  }
}

// Narrow union by checking for specific properties
function hasProperty<K extends string>(
  obj: unknown,
  key: K
): obj is Record<K, unknown> {
  return isRecord(obj) && key in obj;
}

function hasProperties<K extends string>(
  obj: unknown,
  ...keys: K[]
): obj is Record<K, unknown> {
  return isRecord(obj) && keys.every((key) => key in obj);
}

// Parse-don't-validate pattern
interface ParseResult<T> {
  success: boolean;
  data?: T;
  errors?: string[];
}

function parseUser(input: unknown): ParseResult<{
  name: NonEmptyString;
  email: EmailAddress;
  age: PositiveNumber;
}> {
  if (!isRecord(input)) {
    return { success: false, errors: ["Expected an object"] };
  }

  const errors: string[] = [];
  const name = input["name"];
  const email = input["email"];
  const age = input["age"];

  if (!isString(name) || !isNonEmpty(name)) {
    errors.push("name must be a non-empty string");
  }
  if (!isString(email) || !isEmail(email)) {
    errors.push("email must be a valid email address");
  }
  if (!isNumber(age) || !isPositive(age)) {
    errors.push("age must be a positive number");
  }

  if (errors.length > 0) {
    return { success: false, errors };
  }

  return {
    success: true,
    data: {
      name: name as NonEmptyString,
      email: email as EmailAddress,
      age: age as PositiveNumber,
    },
  };
}
'''),

    ("typescript/validation_discriminated_unions", r'''Build type-safe discriminated union patterns in TypeScript for API response handling, including exhaustive matching, union narrowing utilities, and a pattern matching library.''', r'''// Discriminated union patterns for production TypeScript

// API response discriminated union
type ApiResponse<T> =
  | { type: "pending" }
  | { type: "success"; data: T; meta: ResponseMeta }
  | { type: "error"; error: ApiError }
  | { type: "cancelled"; reason: string };

interface ResponseMeta {
  requestId: string;
  duration: number;
  cached: boolean;
}

interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
  retryable: boolean;
}

// Pattern matching utility with exhaustiveness checking
type MatchHandlers<U extends { type: string }, R> = {
  [T in U["type"]]: (value: Extract<U, { type: T }>) => R;
};

function match<U extends { type: string }, R>(
  value: U,
  handlers: MatchHandlers<U, R>
): R {
  const handler = handlers[value.type as keyof typeof handlers];
  return (handler as (v: U) => R)(value);
}

// Partial match with default case
type PartialMatchHandlers<U extends { type: string }, R> = Partial<
  MatchHandlers<U, R>
> & {
  _default: (value: U) => R;
};

function matchPartial<U extends { type: string }, R>(
  value: U,
  handlers: PartialMatchHandlers<U, R>
): R {
  const handler = handlers[value.type as keyof typeof handlers];
  if (handler) {
    return (handler as (v: U) => R)(value);
  }
  return handlers._default(value);
}

// Usage example
function renderResponse<T>(response: ApiResponse<T>): string {
  return match(response, {
    pending: () => "Loading...",
    success: ({ data, meta }) =>
      `Data loaded in ${meta.duration}ms (${meta.cached ? "cached" : "fresh"})`,
    error: ({ error }) =>
      `Error ${error.code}: ${error.message}${error.retryable ? " (retryable)" : ""}`,
    cancelled: ({ reason }) => `Cancelled: ${reason}`,
  });
}

// Nested discriminated unions for complex domain modeling
type Shape =
  | { kind: "circle"; radius: number }
  | { kind: "rectangle"; width: number; height: number }
  | { kind: "triangle"; base: number; height: number }
  | { kind: "polygon"; sides: number; sideLength: number };

function area(shape: Shape): number {
  return match(shape, {
    circle: ({ radius }) => Math.PI * radius * radius,
    rectangle: ({ width, height }) => width * height,
    triangle: ({ base, height }) => 0.5 * base * height,
    polygon: ({ sides, sideLength }) => {
      const apothem = sideLength / (2 * Math.tan(Math.PI / sides));
      return 0.5 * sides * sideLength * apothem;
    },
  });
}

// Discriminated union for message types
type WebSocketMessage =
  | { type: "connect"; userId: string; token: string }
  | { type: "disconnect"; userId: string; reason?: string }
  | { type: "message"; from: string; to: string; content: string; timestamp: number }
  | { type: "typing"; userId: string; channelId: string; isTyping: boolean }
  | { type: "presence"; userId: string; status: "online" | "away" | "offline" }
  | { type: "ack"; messageId: string; deliveredAt: number };

// Type-safe message handler registry
type MessageHandler<M extends WebSocketMessage, T extends M["type"]> = (
  message: Extract<M, { type: T }>
) => void | Promise<void>;

class MessageRouter<M extends { type: string }> {
  private handlers = new Map<string, Function[]>();

  on<T extends M["type"]>(
    type: T,
    handler: (message: Extract<M, { type: T }>) => void | Promise<void>
  ): () => void {
    const list = this.handlers.get(type as string) || [];
    list.push(handler);
    this.handlers.set(type as string, list);
    return () => {
      const current = this.handlers.get(type as string) || [];
      this.handlers.set(
        type as string,
        current.filter((h) => h !== handler)
      );
    };
  }

  async dispatch(message: M): Promise<void> {
    const type = (message as { type: string }).type;
    const handlers = this.handlers.get(type) || [];
    for (const handler of handlers) {
      await handler(message);
    }
  }
}

// Union narrowing utilities
type NarrowByType<U extends { type: string }, T extends U["type"]> = Extract<
  U,
  { type: T }
>;

type ExcludeByType<U extends { type: string }, T extends U["type"]> = Exclude<
  U,
  { type: T }
>;

type UnionTypes<U extends { type: string }> = U["type"];

// Builder for creating discriminated unions from a definition
type UnionDefinition = Record<string, Record<string, unknown>>;

type BuildUnion<D extends UnionDefinition, K extends string = "type"> = {
  [T in keyof D]: { [P in K]: T } & D[T];
}[keyof D];

// Define a union from a simple record
type NotificationDef = {
  email: { to: string; subject: string; body: string };
  sms: { phone: string; message: string };
  push: { deviceToken: string; title: string; body: string; badge?: number };
  webhook: { url: string; payload: Record<string, unknown>; headers?: Record<string, string> };
};

type Notification = BuildUnion<NotificationDef>;

// Result type as discriminated union
type Result<T, E = Error> =
  | { ok: true; value: T }
  | { ok: false; error: E };

function isOk<T, E>(result: Result<T, E>): result is { ok: true; value: T } {
  return result.ok === true;
}

function mapResult<T, U, E>(
  result: Result<T, E>,
  fn: (value: T) => U
): Result<U, E> {
  if (result.ok) {
    return { ok: true, value: fn(result.value) };
  }
  return result;
}

function flatMapResult<T, U, E>(
  result: Result<T, E>,
  fn: (value: T) => Result<U, E>
): Result<U, E> {
  if (result.ok) {
    return fn(result.value);
  }
  return result;
}

// Usage
const router = new MessageRouter<WebSocketMessage>();

router.on("message", async (msg) => {
  console.log(`${msg.from} -> ${msg.to}: ${msg.content}`);
});

router.on("presence", (msg) => {
  console.log(`${msg.userId} is now ${msg.status}`);
});

router.on("typing", (msg) => {
  if (msg.isTyping) {
    console.log(`${msg.userId} is typing in ${msg.channelId}`);
  }
});
'''),

    ("typescript/validation_forms", r'''Build a type-safe form validation system in TypeScript with field-level validators, cross-field validation, async validation support, and error message formatting.''', r'''// Type-safe form validation system

// Validator types
type SyncValidator<T> = (value: T) => string | null;
type AsyncValidator<T> = (value: T) => Promise<string | null>;
type Validator<T> = SyncValidator<T> | AsyncValidator<T>;

// Field configuration with type safety
interface FieldConfig<T> {
  validators: Validator<T>[];
  asyncValidators?: AsyncValidator<T>[];
  required?: boolean;
  requiredMessage?: string;
}

// Form configuration derived from a data shape
type FormConfig<T extends Record<string, unknown>> = {
  [K in keyof T]: FieldConfig<T[K]>;
};

// Validation result types
interface FieldError {
  field: string;
  message: string;
  type: "sync" | "async" | "required" | "cross-field";
}

interface ValidationResult<T> {
  valid: boolean;
  errors: FieldError[];
  errorsByField: Partial<Record<keyof T & string, string[]>>;
  data?: T;
}

// Built-in validators
const validators = {
  required: <T>(message = "This field is required"): SyncValidator<T> => {
    return (value: T) => {
      if (value === null || value === undefined || value === "") return message;
      if (Array.isArray(value) && value.length === 0) return message;
      return null;
    };
  },

  minLength: (min: number, message?: string): SyncValidator<string> => {
    return (value: string) => {
      if (value.length < min) return message || `Must be at least ${min} characters`;
      return null;
    };
  },

  maxLength: (max: number, message?: string): SyncValidator<string> => {
    return (value: string) => {
      if (value.length > max) return message || `Must be at most ${max} characters`;
      return null;
    };
  },

  pattern: (regex: RegExp, message: string): SyncValidator<string> => {
    return (value: string) => {
      if (!regex.test(value)) return message;
      return null;
    };
  },

  email: (message = "Invalid email address"): SyncValidator<string> => {
    return (value: string) => {
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) return message;
      return null;
    };
  },

  min: (minValue: number, message?: string): SyncValidator<number> => {
    return (value: number) => {
      if (value < minValue) return message || `Must be at least ${minValue}`;
      return null;
    };
  },

  max: (maxValue: number, message?: string): SyncValidator<number> => {
    return (value: number) => {
      if (value > maxValue) return message || `Must be at most ${maxValue}`;
      return null;
    };
  },

  oneOf: <T>(options: T[], message?: string): SyncValidator<T> => {
    return (value: T) => {
      if (!options.includes(value)) {
        return message || `Must be one of: ${options.join(", ")}`;
      }
      return null;
    };
  },

  matches: (fieldName: string, message?: string): SyncValidator<unknown> => {
    return (_value: unknown) => {
      // Cross-field validation handled separately
      return null;
    };
  },
};

// Cross-field validator
type CrossFieldValidator<T> = (values: T) => FieldError | null;

// Form validator class
class FormValidator<T extends Record<string, unknown>> {
  private fieldConfigs: FormConfig<T>;
  private crossFieldValidators: CrossFieldValidator<T>[] = [];

  constructor(config: FormConfig<T>) {
    this.fieldConfigs = config;
  }

  addCrossFieldValidator(validator: CrossFieldValidator<T>): this {
    this.crossFieldValidators.push(validator);
    return this;
  }

  validateField<K extends keyof T & string>(
    field: K,
    value: T[K]
  ): string[] {
    const config = this.fieldConfigs[field];
    if (!config) return [];

    const errors: string[] = [];

    // Check required
    if (config.required) {
      const requiredError = validators.required(config.requiredMessage)(value);
      if (requiredError) {
        errors.push(requiredError);
        return errors; // Skip other validators if required check fails
      }
    }

    // Run sync validators
    for (const validator of config.validators) {
      const result = validator(value);
      if (typeof result === "string") {
        errors.push(result);
      }
    }

    return errors;
  }

  async validateFieldAsync<K extends keyof T & string>(
    field: K,
    value: T[K]
  ): Promise<string[]> {
    const syncErrors = this.validateField(field, value);
    if (syncErrors.length > 0) return syncErrors;

    const config = this.fieldConfigs[field];
    if (!config?.asyncValidators) return [];

    const asyncErrors: string[] = [];
    const results = await Promise.allSettled(
      config.asyncValidators.map((v) => v(value))
    );

    for (const result of results) {
      if (result.status === "fulfilled" && result.value) {
        asyncErrors.push(result.value);
      } else if (result.status === "rejected") {
        asyncErrors.push("Validation check failed");
      }
    }

    return asyncErrors;
  }

  validate(values: T): ValidationResult<T> {
    const errors: FieldError[] = [];
    const errorsByField: Partial<Record<keyof T & string, string[]>> = {};

    // Validate each field
    for (const field of Object.keys(this.fieldConfigs) as (keyof T & string)[]) {
      const fieldErrors = this.validateField(field, values[field]);
      if (fieldErrors.length > 0) {
        errorsByField[field] = fieldErrors;
        for (const message of fieldErrors) {
          errors.push({ field, message, type: "sync" });
        }
      }
    }

    // Run cross-field validators
    for (const crossValidator of this.crossFieldValidators) {
      const error = crossValidator(values);
      if (error) {
        errors.push(error);
        const existing = errorsByField[error.field as keyof T & string] || [];
        existing.push(error.message);
        errorsByField[error.field as keyof T & string] = existing;
      }
    }

    return {
      valid: errors.length === 0,
      errors,
      errorsByField,
      data: errors.length === 0 ? values : undefined,
    };
  }

  async validateAsync(values: T): Promise<ValidationResult<T>> {
    const syncResult = this.validate(values);
    if (!syncResult.valid) return syncResult;

    const asyncErrors: FieldError[] = [];
    const errorsByField = { ...syncResult.errorsByField };

    for (const field of Object.keys(this.fieldConfigs) as (keyof T & string)[]) {
      const fieldErrors = await this.validateFieldAsync(field, values[field]);
      if (fieldErrors.length > 0) {
        errorsByField[field] = [...(errorsByField[field] || []), ...fieldErrors];
        for (const message of fieldErrors) {
          asyncErrors.push({ field, message, type: "async" });
        }
      }
    }

    const allErrors = [...syncResult.errors, ...asyncErrors];
    return {
      valid: allErrors.length === 0,
      errors: allErrors,
      errorsByField,
      data: allErrors.length === 0 ? values : undefined,
    };
  }
}

// Example usage
interface SignUpForm {
  username: string;
  email: string;
  password: string;
  confirmPassword: string;
  age: number;
  acceptTerms: boolean;
}

const signUpValidator = new FormValidator<SignUpForm>({
  username: {
    required: true,
    validators: [
      validators.minLength(3),
      validators.maxLength(20),
      validators.pattern(/^[a-zA-Z0-9_]+$/, "Only letters, numbers, and underscores"),
    ],
    asyncValidators: [
      async (username: string) => {
        // Simulate API check
        const taken = ["admin", "root", "system"];
        if (taken.includes(username.toLowerCase())) {
          return "Username is already taken";
        }
        return null;
      },
    ],
  },
  email: {
    required: true,
    validators: [validators.email()],
  },
  password: {
    required: true,
    validators: [
      validators.minLength(8, "Password must be at least 8 characters"),
      validators.pattern(/[A-Z]/, "Must contain an uppercase letter"),
      validators.pattern(/[0-9]/, "Must contain a number"),
    ],
  },
  confirmPassword: {
    required: true,
    validators: [],
  },
  age: {
    required: true,
    validators: [validators.min(13, "Must be at least 13 years old"), validators.max(150)],
  },
  acceptTerms: {
    required: true,
    requiredMessage: "You must accept the terms",
    validators: [],
  },
}).addCrossFieldValidator((values) => {
  if (values.password !== values.confirmPassword) {
    return { field: "confirmPassword", message: "Passwords do not match", type: "cross-field" };
  }
  return null;
});
'''),

    ("typescript/validation_api", r'''Build a type-safe API request/response validation middleware in TypeScript that validates incoming payloads against schemas and provides typed request handlers with automatic error responses.''', r'''// Type-safe API validation middleware

// Schema types (simplified for middleware focus)
interface SchemaLike<T> {
  parse(input: unknown): T;
  safeParse(input: unknown): { success: true; data: T } | { success: false; error: { message: string; issues: Array<{ path: string[]; message: string }> } };
}

// Validated request type
interface ValidatedRequest<
  Params = unknown,
  Query = unknown,
  Body = unknown
> {
  params: Params;
  query: Query;
  body: Body;
  headers: Record<string, string | undefined>;
  method: string;
  path: string;
}

// Endpoint definition with schemas
interface EndpointSchema<
  Params = unknown,
  Query = unknown,
  Body = unknown,
  Response = unknown
> {
  params?: SchemaLike<Params>;
  query?: SchemaLike<Query>;
  body?: SchemaLike<Body>;
  response?: SchemaLike<Response>;
}

// Handler type that receives validated request
type ValidatedHandler<
  Params,
  Query,
  Body,
  Response
> = (req: ValidatedRequest<Params, Query, Body>) => Promise<Response> | Response;

// HTTP response wrapper
interface HttpResponse<T = unknown> {
  status: number;
  headers: Record<string, string>;
  body: T;
}

// Error response format
interface ErrorResponse {
  error: {
    code: string;
    message: string;
    details?: Array<{ path: string; message: string }>;
  };
}

// Validation middleware factory
function createValidatedEndpoint<
  Params = unknown,
  Query = unknown,
  Body = unknown,
  Resp = unknown
>(
  schema: EndpointSchema<Params, Query, Body, Resp>,
  handler: ValidatedHandler<Params, Query, Body, Resp>
): (rawReq: RawRequest) => Promise<HttpResponse<Resp | ErrorResponse>> {
  return async (rawReq: RawRequest): Promise<HttpResponse<Resp | ErrorResponse>> => {
    // Validate params
    if (schema.params) {
      const result = schema.params.safeParse(rawReq.params);
      if (!result.success) {
        return {
          status: 400,
          headers: { "Content-Type": "application/json" },
          body: {
            error: {
              code: "INVALID_PARAMS",
              message: "Path parameter validation failed",
              details: result.error.issues.map((i) => ({
                path: i.path.join("."),
                message: i.message,
              })),
            },
          },
        };
      }
    }

    // Validate query
    if (schema.query) {
      const result = schema.query.safeParse(rawReq.query);
      if (!result.success) {
        return {
          status: 400,
          headers: { "Content-Type": "application/json" },
          body: {
            error: {
              code: "INVALID_QUERY",
              message: "Query parameter validation failed",
              details: result.error.issues.map((i) => ({
                path: i.path.join("."),
                message: i.message,
              })),
            },
          },
        };
      }
    }

    // Validate body
    if (schema.body) {
      const result = schema.body.safeParse(rawReq.body);
      if (!result.success) {
        return {
          status: 400,
          headers: { "Content-Type": "application/json" },
          body: {
            error: {
              code: "INVALID_BODY",
              message: "Request body validation failed",
              details: result.error.issues.map((i) => ({
                path: i.path.join("."),
                message: i.message,
              })),
            },
          },
        };
      }
    }

    // Build validated request
    const validatedReq: ValidatedRequest<Params, Query, Body> = {
      params: (schema.params?.parse(rawReq.params) ?? rawReq.params) as Params,
      query: (schema.query?.parse(rawReq.query) ?? rawReq.query) as Query,
      body: (schema.body?.parse(rawReq.body) ?? rawReq.body) as Body,
      headers: rawReq.headers,
      method: rawReq.method,
      path: rawReq.path,
    };

    try {
      const responseData = await handler(validatedReq);

      // Validate response in development
      if (schema.response && process.env.NODE_ENV !== "production") {
        const result = schema.response.safeParse(responseData);
        if (!result.success) {
          console.error("Response validation failed:", result.error);
        }
      }

      return {
        status: 200,
        headers: { "Content-Type": "application/json" },
        body: responseData,
      };
    } catch (error) {
      if (error instanceof HttpError) {
        return {
          status: error.statusCode,
          headers: { "Content-Type": "application/json" },
          body: {
            error: { code: error.code, message: error.message },
          },
        };
      }
      return {
        status: 500,
        headers: { "Content-Type": "application/json" },
        body: {
          error: { code: "INTERNAL_ERROR", message: "Internal server error" },
        },
      };
    }
  };
}

// Raw request type from the HTTP framework
interface RawRequest {
  method: string;
  path: string;
  params: Record<string, string>;
  query: Record<string, string | string[]>;
  body: unknown;
  headers: Record<string, string | undefined>;
}

// HTTP error class
class HttpError extends Error {
  constructor(
    public statusCode: number,
    message: string,
    public code: string = "HTTP_ERROR"
  ) {
    super(message);
    this.name = "HttpError";
  }

  static badRequest(message: string, code?: string) {
    return new HttpError(400, message, code || "BAD_REQUEST");
  }
  static unauthorized(message = "Unauthorized") {
    return new HttpError(401, message, "UNAUTHORIZED");
  }
  static forbidden(message = "Forbidden") {
    return new HttpError(403, message, "FORBIDDEN");
  }
  static notFound(message = "Not found") {
    return new HttpError(404, message, "NOT_FOUND");
  }
  static conflict(message: string) {
    return new HttpError(409, message, "CONFLICT");
  }
}

// Router that registers validated endpoints
class ValidatedRouter {
  private routes: Array<{
    method: string;
    path: string;
    handler: (req: RawRequest) => Promise<HttpResponse>;
  }> = [];

  get<P, Q, R>(
    path: string,
    schema: EndpointSchema<P, Q, never, R>,
    handler: ValidatedHandler<P, Q, never, R>
  ): this {
    this.routes.push({
      method: "GET",
      path,
      handler: createValidatedEndpoint(schema, handler) as any,
    });
    return this;
  }

  post<P, Q, B, R>(
    path: string,
    schema: EndpointSchema<P, Q, B, R>,
    handler: ValidatedHandler<P, Q, B, R>
  ): this {
    this.routes.push({
      method: "POST",
      path,
      handler: createValidatedEndpoint(schema, handler) as any,
    });
    return this;
  }

  put<P, Q, B, R>(
    path: string,
    schema: EndpointSchema<P, Q, B, R>,
    handler: ValidatedHandler<P, Q, B, R>
  ): this {
    this.routes.push({
      method: "PUT",
      path,
      handler: createValidatedEndpoint(schema, handler) as any,
    });
    return this;
  }

  delete<P, Q, R>(
    path: string,
    schema: EndpointSchema<P, Q, never, R>,
    handler: ValidatedHandler<P, Q, never, R>
  ): this {
    this.routes.push({
      method: "DELETE",
      path,
      handler: createValidatedEndpoint(schema, handler) as any,
    });
    return this;
  }

  async handle(req: RawRequest): Promise<HttpResponse> {
    const route = this.routes.find(
      (r) => r.method === req.method && this.matchPath(r.path, req.path)
    );
    if (!route) {
      return {
        status: 404,
        headers: { "Content-Type": "application/json" },
        body: { error: { code: "NOT_FOUND", message: `${req.method} ${req.path} not found` } },
      };
    }
    return route.handler(req);
  }

  private matchPath(pattern: string, actual: string): boolean {
    const patternParts = pattern.split("/");
    const actualParts = actual.split("/");
    if (patternParts.length !== actualParts.length) return false;
    return patternParts.every(
      (part, i) => part.startsWith(":") || part === actualParts[i]
    );
  }
}
'''),
]
