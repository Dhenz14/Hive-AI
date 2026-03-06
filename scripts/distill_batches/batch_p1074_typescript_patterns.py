"""
Batch p1074: TypeScript/React production pairs - TypeScript Design Patterns
Topics: builder, result type, branded types, phantom types, type-safe event emitter
"""

PAIRS = [
    ("typescript/patterns_builder", r'''Build a type-safe builder pattern in TypeScript that tracks which required fields have been set at the type level, preventing build() from being called until all required fields are provided.''', r'''// Type-safe builder that enforces required fields at compile time

// Utility: check if all required keys are satisfied
type HasAllRequired<Required extends string, Provided extends string> =
  Required extends Provided ? true : false;

// The builder type changes its type parameter as fields are set
class TypedBuilder<
  T extends Record<string, unknown>,
  Required extends keyof T & string,
  Provided extends string = never
> {
  private data: Partial<T> = {};

  private constructor(data: Partial<T>) {
    this.data = { ...data };
  }

  static create<
    T extends Record<string, unknown>,
    R extends keyof T & string = never
  >(requiredKeys?: R[]): TypedBuilder<T, R, never> {
    return new TypedBuilder<T, R, never>({});
  }

  set<K extends keyof T & string>(
    key: K,
    value: T[K]
  ): TypedBuilder<T, Required, Provided | (K & Required)> {
    const newData = { ...this.data, [key]: value };
    return new TypedBuilder<T, Required, Provided | (K & Required)>(newData);
  }

  // build() is only available when all required fields have been provided
  build(
    this: TypedBuilder<T, Required, Required>
  ): T {
    return this.data as T;
  }
}

// Example: User with required and optional fields
interface UserConfig {
  name: string;
  email: string;
  age: number;
  bio?: string;
  avatar?: string;
}

// Step builder pattern - enforces a specific order of operations
interface StepBuilder {
  withName(name: string): StepBuilderWithName;
}

interface StepBuilderWithName {
  withEmail(email: string): StepBuilderWithEmail;
}

interface StepBuilderWithEmail {
  withAge(age: number): StepBuilderComplete;
}

interface StepBuilderComplete {
  withBio(bio: string): StepBuilderComplete;
  withAvatar(avatar: string): StepBuilderComplete;
  build(): UserConfig;
}

class UserBuilder implements StepBuilder {
  private config: Partial<UserConfig> = {};

  withName(name: string): StepBuilderWithName {
    this.config.name = name;
    return this as unknown as StepBuilderWithName;
  }

  withEmail(email: string): StepBuilderWithEmail {
    this.config.email = email;
    return this as unknown as StepBuilderWithEmail;
  }

  withAge(age: number): StepBuilderComplete {
    this.config.age = age;
    return this as unknown as StepBuilderComplete;
  }

  withBio(bio: string): StepBuilderComplete {
    this.config.bio = bio;
    return this as unknown as StepBuilderComplete;
  }

  withAvatar(avatar: string): StepBuilderComplete {
    this.config.avatar = avatar;
    return this as unknown as StepBuilderComplete;
  }

  build(): UserConfig {
    return this.config as UserConfig;
  }
}

// Fluent query builder with type accumulation
interface QueryState {
  table: string | null;
  selected: string[];
  conditions: string[];
  ordered: string[];
  limited: number | null;
}

class QueryBuilder<State extends Partial<QueryState> = {}> {
  private state: QueryState = {
    table: null,
    selected: [],
    conditions: [],
    ordered: [],
    limited: null,
  };

  from<Table extends string>(
    table: Table
  ): QueryBuilder<State & { table: Table }> {
    this.state.table = table;
    return this as any;
  }

  select<Fields extends string[]>(
    ...fields: Fields
  ): QueryBuilder<State & { selected: Fields }> {
    this.state.selected = fields;
    return this as any;
  }

  where(condition: string): QueryBuilder<State & { conditions: string[] }> {
    this.state.conditions.push(condition);
    return this as any;
  }

  orderBy(field: string, dir: "ASC" | "DESC" = "ASC"): this {
    this.state.ordered.push(`${field} ${dir}`);
    return this;
  }

  limit(n: number): this {
    this.state.limited = n;
    return this;
  }

  // Only allow build when table is set
  toSQL(
    this: QueryBuilder<{ table: string }>
  ): string {
    const parts: string[] = [];
    const fields = this.state.selected.length > 0
      ? this.state.selected.join(", ")
      : "*";
    parts.push(`SELECT ${fields} FROM ${this.state.table}`);
    if (this.state.conditions.length > 0) {
      parts.push(`WHERE ${this.state.conditions.join(" AND ")}`);
    }
    if (this.state.ordered.length > 0) {
      parts.push(`ORDER BY ${this.state.ordered.join(", ")}`);
    }
    if (this.state.limited !== null) {
      parts.push(`LIMIT ${this.state.limited}`);
    }
    return parts.join(" ");
  }
}

// Usage - type errors if build() called without required steps
const user = new UserBuilder()
  .withName("Alice")
  .withEmail("alice@example.com")
  .withAge(30)
  .withBio("Developer")
  .build();

const sql = new QueryBuilder()
  .from("users")
  .select("id", "name", "email")
  .where("active = true")
  .orderBy("name")
  .limit(10)
  .toSQL();
'''),

    ("typescript/patterns_result", r'''<think>
The Result type (also called Either) is a crucial pattern for error handling without exceptions. I could implement this as a simple union type `{ ok: true, value: T } | { ok: false, error: E }`, but wait - that would not support method chaining. To get a fluent API with map/flatMap, I need class instances.

I considered using a single Result class with a discriminant field, but actually separate Ok and Err classes give better type narrowing. When you check `result.isOk()`, TypeScript can narrow the type to Ok<T, E> and expose `.value` without a cast. With a single class you would need manual assertion.

Hmm, one tricky design question: should flatMap on Err skip the callback or throw? It should skip - that is the whole point of monadic chaining. The error propagates automatically through the chain without the caller checking at each step. This is why Result is so powerful compared to try/catch.

Key methods needed:
- map/mapErr for transforming the inner values
- flatMap/andThen for chaining fallible operations
- match for exhaustive pattern matching
- unwrapOr for safe default extraction
- fromPromise for converting async operations
</think>

Build a comprehensive Result type in TypeScript with Ok/Err variants, functional combinators (map, flatMap, match), async support, and error accumulation for collecting multiple validation errors.''', r'''<think>
I will implement a discriminated union Result type with a rich API for functional error handling. The key is making the type narrow correctly in each branch - I initially planned to use a `kind` string discriminant, but actually using boolean `ok` and `err` fields is more ergonomic since you can write `if (result.ok)` directly.

For the Ok class, methods like mapErr and flatMap's error path need to preserve the error type parameter even though they do not use it. I considered omitting the E parameter from Ok entirely, but wait - that would break the Result<T, E> union since Ok and Err need compatible type signatures. Therefore Ok<T, E> carries E as a phantom type.

I also need a collectAll utility for error accumulation - this is different from flatMap chaining because we want ALL errors, not just the first one. This is critical for form validation where showing all field errors at once is better UX.
</think>

// Discriminated union Result type
type Result<T, E = Error> = Ok<T, E> | Err<T, E>;

class Ok<T, E = Error> {
  readonly ok = true;
  readonly err = false;

  constructor(readonly value: T) {}

  map<U>(fn: (value: T) => U): Result<U, E> {
    return new Ok(fn(this.value));
  }

  mapErr<F>(_fn: (error: E) => F): Result<T, F> {
    return new Ok(this.value);
  }

  flatMap<U>(fn: (value: T) => Result<U, E>): Result<U, E> {
    return fn(this.value);
  }

  match<U>(handlers: { ok: (value: T) => U; err: (error: E) => U }): U {
    return handlers.ok(this.value);
  }

  unwrap(): T {
    return this.value;
  }

  unwrapOr(_defaultValue: T): T {
    return this.value;
  }

  unwrapOrElse(_fn: (error: E) => T): T {
    return this.value;
  }

  isOk(): this is Ok<T, E> {
    return true;
  }

  isErr(): this is Err<T, E> {
    return false;
  }

  // Combine with another Result - both must succeed
  and<U>(other: Result<U, E>): Result<U, E> {
    return other;
  }

  or(_other: Result<T, E>): Result<T, E> {
    return this;
  }

  tap(fn: (value: T) => void): Result<T, E> {
    fn(this.value);
    return this;
  }
}

class Err<T, E = Error> {
  readonly ok = false;
  readonly err = true;

  constructor(readonly error: E) {}

  map<U>(_fn: (value: T) => U): Result<U, E> {
    return new Err(this.error);
  }

  mapErr<F>(fn: (error: E) => F): Result<T, F> {
    return new Err(fn(this.error));
  }

  flatMap<U>(_fn: (value: T) => Result<U, E>): Result<U, E> {
    return new Err(this.error);
  }

  match<U>(handlers: { ok: (value: T) => U; err: (error: E) => U }): U {
    return handlers.err(this.error);
  }

  unwrap(): never {
    throw this.error instanceof Error ? this.error : new Error(String(this.error));
  }

  unwrapOr(defaultValue: T): T {
    return defaultValue;
  }

  unwrapOrElse(fn: (error: E) => T): T {
    return fn(this.error);
  }

  isOk(): this is Ok<T, E> {
    return false;
  }

  isErr(): this is Err<T, E> {
    return true;
  }

  and<U>(_other: Result<U, E>): Result<U, E> {
    return new Err(this.error);
  }

  or(other: Result<T, E>): Result<T, E> {
    return other;
  }

  tap(_fn: (value: T) => void): Result<T, E> {
    return this;
  }
}

// Factory functions
function ok<T>(value: T): Ok<T, never> {
  return new Ok(value);
}

function err<E>(error: E): Err<never, E> {
  return new Err(error);
}

// Async Result utilities
async function fromPromise<T, E = Error>(
  promise: Promise<T>,
  errorMapper?: (error: unknown) => E
): Promise<Result<T, E>> {
  try {
    const value = await promise;
    return ok(value);
  } catch (error) {
    const mapped = errorMapper
      ? errorMapper(error)
      : (error as E);
    return err(mapped);
  }
}

function tryCatch<T, E = Error>(
  fn: () => T,
  errorMapper?: (error: unknown) => E
): Result<T, E> {
  try {
    return ok(fn());
  } catch (error) {
    return err(errorMapper ? errorMapper(error) : (error as E));
  }
}

// Collect multiple Results - returns all values or all errors
function collectAll<T, E>(results: Result<T, E>[]): Result<T[], E[]> {
  const values: T[] = [];
  const errors: E[] = [];

  for (const result of results) {
    if (result.isOk()) {
      values.push(result.value);
    } else {
      errors.push(result.error);
    }
  }

  return errors.length > 0 ? err(errors) : ok(values);
}

// Validation with error accumulation
interface ValidationErr {
  field: string;
  message: string;
}

class Validator<T> {
  private checks: Array<(value: T) => Result<T, ValidationErr>> = [];

  check(
    field: string,
    predicate: (value: T) => boolean,
    message: string
  ): Validator<T> {
    this.checks.push((value) =>
      predicate(value) ? ok(value) : err({ field, message })
    );
    return this;
  }

  validate(value: T): Result<T, ValidationErr[]> {
    const errors: ValidationErr[] = [];
    for (const check of this.checks) {
      const result = check(value);
      if (result.isErr()) {
        errors.push(result.error);
      }
    }
    return errors.length > 0 ? err(errors) : ok(value);
  }
}

// Usage example with chaining
interface ParsedConfig {
  host: string;
  port: number;
  secure: boolean;
}

function parseHost(raw: string): Result<string, string> {
  return raw.length > 0 ? ok(raw) : err("Host cannot be empty");
}

function parsePort(raw: string): Result<number, string> {
  const port = parseInt(raw, 10);
  if (isNaN(port)) return err("Invalid port number");
  if (port < 1 || port > 65535) return err("Port out of range");
  return ok(port);
}

function parseConfig(raw: Record<string, string>): Result<ParsedConfig, string[]> {
  const results = collectAll([
    parseHost(raw["host"] || "").map((h) => ({ host: h })),
    parsePort(raw["port"] || "").map((p) => ({ port: p })),
  ]);

  return results.map((parts) =>
    Object.assign({ secure: raw["secure"] === "true" }, ...parts) as ParsedConfig
  );
}
'''),

    ("typescript/patterns_branded", r'''Build branded types and phantom types in TypeScript for domain modeling, including type-safe IDs, validated strings, currency amounts, and units of measure that prevent mixing incompatible values.''', r'''// Branded types for type-safe domain modeling

// Brand utility - creates a nominal type from a structural type
declare const __brand: unique symbol;
type Brand<T, B extends string> = T & { readonly [__brand]: B };

// Type-safe IDs - cannot accidentally mix user IDs with post IDs
type UserId = Brand<string, "UserId">;
type PostId = Brand<string, "PostId">;
type CommentId = Brand<string, "CommentId">;
type OrderId = Brand<string, "OrderId">;

// Smart constructors for branded types
function userId(id: string): UserId {
  if (!id.startsWith("usr_")) {
    throw new Error("User ID must start with usr_");
  }
  return id as UserId;
}

function postId(id: string): PostId {
  if (!id.startsWith("post_")) {
    throw new Error("Post ID must start with post_");
  }
  return id as PostId;
}

// Validated string types
type Email = Brand<string, "Email">;
type URL = Brand<string, "URL">;
type PhoneNumber = Brand<string, "PhoneNumber">;
type NonEmptyString = Brand<string, "NonEmptyString">;
type Slug = Brand<string, "Slug">;

function email(value: string): Email {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(value)) {
    throw new Error(`Invalid email: ${value}`);
  }
  return value as Email;
}

function nonEmpty(value: string): NonEmptyString {
  if (value.trim().length === 0) {
    throw new Error("String cannot be empty");
  }
  return value as NonEmptyString;
}

function slug(value: string): Slug {
  const slugRegex = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
  if (!slugRegex.test(value)) {
    throw new Error(`Invalid slug: ${value}`);
  }
  return value as Slug;
}

// Currency amounts - prevent mixing dollars with euros
type USD = Brand<number, "USD">;
type EUR = Brand<number, "EUR">;
type GBP = Brand<number, "GBP">;

function usd(amount: number): USD {
  return Math.round(amount * 100) / 100 as unknown as USD;
}

function eur(amount: number): EUR {
  return Math.round(amount * 100) / 100 as unknown as EUR;
}

// Type-safe arithmetic for same-currency operations
function addCurrency<T extends Brand<number, string>>(a: T, b: T): T {
  return ((a as unknown as number) + (b as unknown as number)) as unknown as T;
}

function subtractCurrency<T extends Brand<number, string>>(a: T, b: T): T {
  return ((a as unknown as number) - (b as unknown as number)) as unknown as T;
}

function multiplyCurrency<T extends Brand<number, string>>(amount: T, factor: number): T {
  const result = (amount as unknown as number) * factor;
  return (Math.round(result * 100) / 100) as unknown as T;
}

// Units of measure using phantom types
type Meters = Brand<number, "Meters">;
type Kilometers = Brand<number, "Kilometers">;
type Miles = Brand<number, "Miles">;
type Seconds = Brand<number, "Seconds">;
type Hours = Brand<number, "Hours">;
type MetersPerSecond = Brand<number, "MetersPerSecond">;
type KilometersPerHour = Brand<number, "KilometersPerHour">;

function meters(value: number): Meters {
  return value as unknown as Meters;
}

function kilometers(value: number): Kilometers {
  return value as unknown as Kilometers;
}

function metersToKilometers(m: Meters): Kilometers {
  return ((m as unknown as number) / 1000) as unknown as Kilometers;
}

function kilometersToMeters(km: Kilometers): Meters {
  return ((km as unknown as number) * 1000) as unknown as Meters;
}

function speed(distance: Meters, time: Seconds): MetersPerSecond {
  return ((distance as unknown as number) / (time as unknown as number)) as unknown as MetersPerSecond;
}

// Phantom type for state tracking
type Unvalidated = { readonly _state: "unvalidated" };
type Validated = { readonly _state: "validated" };
type Submitted = { readonly _state: "submitted" };

interface Form<State> {
  data: Record<string, unknown>;
  _phantom?: State;
}

function createForm(data: Record<string, unknown>): Form<Unvalidated> {
  return { data };
}

function validateForm(form: Form<Unvalidated>): Form<Validated> {
  // Run validation logic
  for (const [key, value] of Object.entries(form.data)) {
    if (value === undefined || value === null || value === "") {
      throw new Error(`Field ${key} is required`);
    }
  }
  return form as unknown as Form<Validated>;
}

function submitForm(form: Form<Validated>): Form<Submitted> {
  // Only validated forms can be submitted
  console.log("Submitting:", form.data);
  return form as unknown as Form<Submitted>;
}

// Type-safe database operations with phantom state
type Connected = { readonly _dbState: "connected" };
type Disconnected = { readonly _dbState: "disconnected" };
type InTransaction = { readonly _dbState: "in_transaction" };

interface DbClient<State> {
  _phantom?: State;
}

function connect(): DbClient<Connected> {
  return {} as DbClient<Connected>;
}

function beginTransaction(client: DbClient<Connected>): DbClient<InTransaction> {
  return client as unknown as DbClient<InTransaction>;
}

function query(client: DbClient<Connected> | DbClient<InTransaction>, sql: string): unknown[] {
  console.log("Executing:", sql);
  return [];
}

function commit(client: DbClient<InTransaction>): DbClient<Connected> {
  return client as unknown as DbClient<Connected>;
}

function rollback(client: DbClient<InTransaction>): DbClient<Connected> {
  return client as unknown as DbClient<Connected>;
}

function disconnect(client: DbClient<Connected>): DbClient<Disconnected> {
  return client as unknown as DbClient<Disconnected>;
}

// These would be compile errors:
// submitForm(createForm({})); // Error: Form<Unvalidated> is not Form<Validated>
// query(disconnect(connect()), "SELECT 1"); // Error: Disconnected client
// commit(connect()); // Error: Connected is not InTransaction
// addCurrency(usd(10), eur(20)); // Error: USD is not EUR
'''),

    ("typescript/patterns_event_emitter", r'''Build a type-safe event emitter in TypeScript where event names and their payload types are enforced at compile time, with support for once listeners, wildcards, and async handlers.''', r'''// Type-safe event emitter with full compile-time checking

// Event map defines allowed events and their payload types
interface EventMap {
  [event: string]: unknown;
}

type EventHandler<T> = (payload: T) => void | Promise<void>;
type WildcardHandler<Events extends EventMap> = (
  event: keyof Events & string,
  payload: Events[keyof Events]
) => void | Promise<void>;

interface ListenerEntry<T> {
  handler: EventHandler<T>;
  once: boolean;
  priority: number;
}

class TypedEventEmitter<Events extends EventMap> {
  private listeners = new Map<string, ListenerEntry<any>[]>();
  private wildcardListeners: Array<{
    handler: WildcardHandler<Events>;
    priority: number;
  }> = [];
  private maxListeners = 50;

  on<E extends keyof Events & string>(
    event: E,
    handler: EventHandler<Events[E]>,
    options?: { priority?: number }
  ): () => void {
    return this.addListener(event, handler, false, options?.priority ?? 0);
  }

  once<E extends keyof Events & string>(
    event: E,
    handler: EventHandler<Events[E]>
  ): () => void {
    return this.addListener(event, handler, true, 0);
  }

  onAny(handler: WildcardHandler<Events>, priority = 0): () => void {
    this.wildcardListeners.push({ handler, priority });
    this.wildcardListeners.sort((a, b) => b.priority - a.priority);
    return () => {
      this.wildcardListeners = this.wildcardListeners.filter(
        (l) => l.handler !== handler
      );
    };
  }

  off<E extends keyof Events & string>(
    event: E,
    handler?: EventHandler<Events[E]>
  ): void {
    if (!handler) {
      this.listeners.delete(event);
      return;
    }
    const entries = this.listeners.get(event) || [];
    this.listeners.set(
      event,
      entries.filter((e) => e.handler !== handler)
    );
  }

  async emit<E extends keyof Events & string>(
    event: E,
    payload: Events[E]
  ): Promise<void> {
    const entries = [...(this.listeners.get(event) || [])];
    entries.sort((a, b) => b.priority - a.priority);

    const toRemove: EventHandler<any>[] = [];

    for (const entry of entries) {
      try {
        await entry.handler(payload);
      } catch (error) {
        console.error(`Error in event handler for "${event}":`, error);
      }
      if (entry.once) {
        toRemove.push(entry.handler);
      }
    }

    // Remove once listeners
    if (toRemove.length > 0) {
      const current = this.listeners.get(event) || [];
      this.listeners.set(
        event,
        current.filter((e) => !toRemove.includes(e.handler))
      );
    }

    // Notify wildcard listeners
    for (const { handler } of this.wildcardListeners) {
      try {
        await handler(event, payload);
      } catch (error) {
        console.error(`Error in wildcard handler for "${event}":`, error);
      }
    }
  }

  // Synchronous emit for performance-critical paths
  emitSync<E extends keyof Events & string>(
    event: E,
    payload: Events[E]
  ): void {
    const entries = [...(this.listeners.get(event) || [])];
    const toRemove: EventHandler<any>[] = [];

    for (const entry of entries) {
      entry.handler(payload);
      if (entry.once) {
        toRemove.push(entry.handler);
      }
    }

    if (toRemove.length > 0) {
      const current = this.listeners.get(event) || [];
      this.listeners.set(
        event,
        current.filter((e) => !toRemove.includes(e.handler))
      );
    }

    for (const { handler } of this.wildcardListeners) {
      handler(event, payload);
    }
  }

  // Wait for the next occurrence of an event
  waitFor<E extends keyof Events & string>(
    event: E,
    timeout?: number
  ): Promise<Events[E]> {
    return new Promise<Events[E]>((resolve, reject) => {
      let timeoutId: ReturnType<typeof setTimeout> | undefined;

      const unsubscribe = this.once(event, (payload) => {
        if (timeoutId) clearTimeout(timeoutId);
        resolve(payload);
      });

      if (timeout !== undefined) {
        timeoutId = setTimeout(() => {
          unsubscribe();
          reject(new Error(`Timeout waiting for event "${event}"`));
        }, timeout);
      }
    });
  }

  listenerCount<E extends keyof Events & string>(event: E): number {
    return (this.listeners.get(event) || []).length;
  }

  eventNames(): (keyof Events & string)[] {
    return Array.from(this.listeners.keys()) as (keyof Events & string)[];
  }

  removeAllListeners(): void {
    this.listeners.clear();
    this.wildcardListeners = [];
  }

  private addListener<E extends keyof Events & string>(
    event: E,
    handler: EventHandler<Events[E]>,
    once: boolean,
    priority: number
  ): () => void {
    const entries = this.listeners.get(event) || [];

    if (entries.length >= this.maxListeners) {
      console.warn(
        `MaxListenersExceeded: ${entries.length} listeners for "${event}"`
      );
    }

    const entry: ListenerEntry<Events[E]> = { handler, once, priority };
    entries.push(entry);
    entries.sort((a, b) => b.priority - a.priority);
    this.listeners.set(event, entries);

    return () => this.off(event, handler);
  }
}

// Middleware support for event processing
type EventMiddleware<Events extends EventMap> = <E extends keyof Events & string>(
  event: E,
  payload: Events[E],
  next: () => Promise<void>
) => Promise<void>;

class EventBus<Events extends EventMap> extends TypedEventEmitter<Events> {
  private middleware: EventMiddleware<Events>[] = [];

  use(mw: EventMiddleware<Events>): void {
    this.middleware.push(mw);
  }

  override async emit<E extends keyof Events & string>(
    event: E,
    payload: Events[E]
  ): Promise<void> {
    let index = 0;
    const mws = this.middleware;
    const superEmit = super.emit.bind(this);

    const next = async (): Promise<void> => {
      if (index < mws.length) {
        const mw = mws[index++];
        await mw(event, payload, next);
      } else {
        await superEmit(event, payload);
      }
    };

    await next();
  }
}

// Usage with strongly typed events
interface AppEvents {
  "user:login": { userId: string; timestamp: number };
  "user:logout": { userId: string };
  "post:created": { postId: string; title: string; authorId: string };
  "post:deleted": { postId: string; deletedBy: string };
  "error": { code: string; message: string; stack?: string };
  "metrics": { name: string; value: number; tags: Record<string, string> };
}

const bus = new EventBus<AppEvents>();

// Logging middleware
bus.use(async (event, payload, next) => {
  console.log(`[EVENT] ${event}`, payload);
  const start = Date.now();
  await next();
  console.log(`[EVENT] ${event} processed in ${Date.now() - start}ms`);
});

// All handlers are fully type-checked
bus.on("user:login", async ({ userId, timestamp }) => {
  console.log(`User ${userId} logged in at ${new Date(timestamp)}`);
});

bus.on("post:created", ({ postId, title }) => {
  console.log(`New post: ${title} (${postId})`);
}, { priority: 10 });

// Wildcard handler gets union of all payloads
bus.onAny((event, payload) => {
  console.log(`[AUDIT] ${event}:`, payload);
});
'''),

    ("typescript/patterns_phantom_state", r'''Build a type-safe finite state machine in TypeScript using phantom types to enforce valid state transitions at compile time, with support for guards, actions, and context updates.''', r'''// Compile-time enforced state machine using phantom types

// State definitions as literal types
type StateId = string;
type EventId = string;

// Phantom type wrapper for state tracking
type MachineInState<S extends StateId> = {
  readonly currentState: S;
  readonly _phantom?: S;
};

// Transition definition
interface TransitionDef<
  From extends StateId,
  Event extends EventId,
  To extends StateId,
  Context
> {
  from: From;
  event: Event;
  to: To;
  guard?: (context: Context) => boolean;
  action?: (context: Context) => Context;
}

// Machine configuration built from transition definitions
type TransitionMap<Context> = {
  [From in StateId]?: {
    [Event in EventId]?: {
      to: StateId;
      guard?: (context: Context) => boolean;
      action?: (context: Context) => Context;
    };
  };
};

// Builder for defining state machines with type safety
class StateMachineBuilder<
  States extends StateId,
  Events extends EventId,
  Context,
  Initial extends States = never
> {
  private transitions: TransitionMap<Context> = {};
  private initialState: States | null = null;
  private stateEnterActions = new Map<string, (ctx: Context) => Context>();
  private stateExitActions = new Map<string, (ctx: Context) => Context>();

  initial<S extends States>(
    state: S
  ): StateMachineBuilder<States, Events, Context, S> {
    this.initialState = state;
    return this as any;
  }

  transition<F extends States, E extends Events, T extends States>(
    from: F,
    event: E,
    to: T,
    options?: {
      guard?: (context: Context) => boolean;
      action?: (context: Context) => Context;
    }
  ): StateMachineBuilder<States, Events, Context, Initial> {
    if (!this.transitions[from]) {
      this.transitions[from] = {};
    }
    this.transitions[from]![event] = {
      to,
      guard: options?.guard,
      action: options?.action,
    };
    return this;
  }

  onEnter<S extends States>(
    state: S,
    action: (context: Context) => Context
  ): StateMachineBuilder<States, Events, Context, Initial> {
    this.stateEnterActions.set(state, action);
    return this;
  }

  onExit<S extends States>(
    state: S,
    action: (context: Context) => Context
  ): StateMachineBuilder<States, Events, Context, Initial> {
    this.stateExitActions.set(state, action);
    return this;
  }

  build(
    this: StateMachineBuilder<States, Events, Context, States>,
    initialContext: Context
  ): StateMachine<States, Events, Context> {
    if (!this.initialState) {
      throw new Error("Initial state must be set");
    }
    return new StateMachine(
      this.initialState,
      initialContext,
      this.transitions,
      this.stateEnterActions,
      this.stateExitActions
    );
  }
}

// Runtime state machine with full transition logic
class StateMachine<
  States extends StateId,
  Events extends EventId,
  Context
> {
  private _currentState: States;
  private _context: Context;
  private _history: Array<{ from: States; event: Events; to: States; timestamp: number }> = [];
  private changeListeners: Array<(from: States, to: States, event: Events) => void> = [];

  constructor(
    initialState: States,
    initialContext: Context,
    private transitions: TransitionMap<Context>,
    private enterActions: Map<string, (ctx: Context) => Context>,
    private exitActions: Map<string, (ctx: Context) => Context>
  ) {
    this._currentState = initialState;
    this._context = initialContext;

    const enterAction = this.enterActions.get(initialState);
    if (enterAction) {
      this._context = enterAction(this._context);
    }
  }

  get state(): States {
    return this._currentState;
  }

  get context(): Readonly<Context> {
    return this._context;
  }

  get history() {
    return [...this._history];
  }

  can(event: Events): boolean {
    const stateTransitions = this.transitions[this._currentState];
    if (!stateTransitions) return false;
    const transition = stateTransitions[event];
    if (!transition) return false;
    if (transition.guard && !transition.guard(this._context)) return false;
    return true;
  }

  send(event: Events): boolean {
    const stateTransitions = this.transitions[this._currentState];
    if (!stateTransitions) {
      console.warn(`No transitions from state: ${this._currentState}`);
      return false;
    }

    const transition = stateTransitions[event];
    if (!transition) {
      console.warn(`No transition for event "${event}" in state "${this._currentState}"`);
      return false;
    }

    if (transition.guard && !transition.guard(this._context)) {
      console.warn(`Guard rejected transition: ${this._currentState} -> ${transition.to}`);
      return false;
    }

    const from = this._currentState;
    const to = transition.to as States;

    // Execute exit action
    const exitAction = this.exitActions.get(from);
    if (exitAction) {
      this._context = exitAction(this._context);
    }

    // Execute transition action
    if (transition.action) {
      this._context = transition.action(this._context);
    }

    // Update state
    this._currentState = to;

    // Execute enter action
    const enterAction = this.enterActions.get(to);
    if (enterAction) {
      this._context = enterAction(this._context);
    }

    // Record history
    this._history.push({ from, event, to, timestamp: Date.now() });

    // Notify listeners
    for (const listener of this.changeListeners) {
      listener(from, to, event);
    }

    return true;
  }

  onChange(listener: (from: States, to: States, event: Events) => void): () => void {
    this.changeListeners.push(listener);
    return () => {
      this.changeListeners = this.changeListeners.filter((l) => l !== listener);
    };
  }

  matches(state: States): boolean {
    return this._currentState === state;
  }
}

// Example: Order processing state machine
type OrderState = "draft" | "submitted" | "paid" | "shipped" | "delivered" | "cancelled";
type OrderEvent = "submit" | "pay" | "ship" | "deliver" | "cancel";

interface OrderContext {
  orderId: string;
  total: number;
  paidAt: number | null;
  shippedAt: number | null;
  cancelledAt: number | null;
}

const orderMachine = new StateMachineBuilder<OrderState, OrderEvent, OrderContext>()
  .initial("draft")
  .transition("draft", "submit", "submitted")
  .transition("submitted", "pay", "paid", {
    guard: (ctx) => ctx.total > 0,
    action: (ctx) => ({ ...ctx, paidAt: Date.now() }),
  })
  .transition("paid", "ship", "shipped", {
    action: (ctx) => ({ ...ctx, shippedAt: Date.now() }),
  })
  .transition("shipped", "deliver", "delivered")
  .transition("draft", "cancel", "cancelled", {
    action: (ctx) => ({ ...ctx, cancelledAt: Date.now() }),
  })
  .transition("submitted", "cancel", "cancelled", {
    action: (ctx) => ({ ...ctx, cancelledAt: Date.now() }),
  })
  .onEnter("submitted", (ctx) => {
    console.log(`Order ${ctx.orderId} submitted for review`);
    return ctx;
  })
  .build({
    orderId: "ORD-001",
    total: 99.99,
    paidAt: null,
    shippedAt: null,
    cancelledAt: null,
  });
'''),
]
