"""
Batch p1073: TypeScript/React production pairs - Advanced Generics
Topics: conditional types, mapped types, template literal types, type inference, recursive types
"""

PAIRS = [
    ("typescript/generics_conditional", r'''Build advanced TypeScript conditional types that implement a deep type transformation system, including DeepReadonly, DeepPartial, DeepRequired, and a type-level pattern matching utility.''', r'''// Deep recursive utility types with conditional type distribution

// DeepReadonly - recursively makes all properties readonly
type DeepReadonly<T> = T extends Function
  ? T
  : T extends Map<infer K, infer V>
  ? ReadonlyMap<DeepReadonly<K>, DeepReadonly<V>>
  : T extends Set<infer V>
  ? ReadonlySet<DeepReadonly<V>>
  : T extends Array<infer U>
  ? ReadonlyArray<DeepReadonly<U>>
  : T extends object
  ? { readonly [K in keyof T]: DeepReadonly<T[K]> }
  : T;

// DeepPartial - recursively makes all properties optional
type DeepPartial<T> = T extends Function
  ? T
  : T extends Array<infer U>
  ? Array<DeepPartial<U>>
  : T extends object
  ? { [K in keyof T]?: DeepPartial<T[K]> }
  : T;

// DeepRequired - recursively makes all properties required and non-nullable
type DeepRequired<T> = T extends Function
  ? T
  : T extends Array<infer U>
  ? Array<DeepRequired<U>>
  : T extends object
  ? { [K in keyof T]-?: DeepRequired<NonNullable<T[K]>> }
  : NonNullable<T>;

// Type-level pattern matching using conditional types
type Match<T, Cases extends [any, any][]> =
  Cases extends [[infer Pattern, infer Result], ...infer Rest extends [any, any][]]
    ? T extends Pattern
      ? Result
      : Match<T, Rest>
    : never;

// Extract nested property type with dot-notation path
type DeepGet<T, Path extends string> =
  Path extends `${infer Head}.${infer Tail}`
    ? Head extends keyof T
      ? DeepGet<T[Head], Tail>
      : never
    : Path extends keyof T
      ? T[Path]
      : never;

// Flatten nested object type to single level with dot-notation keys
type FlattenObject<T, Prefix extends string = ""> = {
  [K in keyof T & string as T[K] extends object
    ? T[K] extends Array<any> | Function | Date
      ? `${Prefix}${K}`
      : keyof FlattenObject<T[K], `${Prefix}${K}.`> & string
    : `${Prefix}${K}`
  ]: T[K] extends object
    ? T[K] extends Array<any> | Function | Date
      ? T[K]
      : FlattenObject<T[K], `${Prefix}${K}.`>[keyof FlattenObject<T[K], `${Prefix}${K}.`>]
    : T[K];
};

// Usage examples with real-world types
interface UserProfile {
  id: string;
  name: string;
  email: string;
  address: {
    street: string;
    city: string;
    country: {
      code: string;
      name: string;
    };
  };
  preferences: {
    theme: "light" | "dark";
    notifications: boolean;
  };
}

// These correctly resolve at compile time:
type ReadonlyProfile = DeepReadonly<UserProfile>;
type PartialProfile = DeepPartial<UserProfile>;
type RequiredProfile = DeepRequired<Partial<UserProfile>>;

// DeepGet extracts nested types:
type CountryCode = DeepGet<UserProfile, "address.country.code">; // string
type Theme = DeepGet<UserProfile, "preferences.theme">; // "light" | "dark"

// Conditional extraction utility
type ExtractByType<T, U> = {
  [K in keyof T as T[K] extends U ? K : never]: T[K];
};

type StringFields = ExtractByType<UserProfile, string>;
// { id: string; name: string; email: string }

// Mutable version - removes readonly
type DeepMutable<T> = T extends Function
  ? T
  : T extends ReadonlyArray<infer U>
  ? Array<DeepMutable<U>>
  : T extends ReadonlyMap<infer K, infer V>
  ? Map<DeepMutable<K>, DeepMutable<V>>
  : T extends object
  ? { -readonly [K in keyof T]: DeepMutable<T[K]> }
  : T;

// Type-safe merge that preserves specific types from both objects
type DeepMerge<A, B> = {
  [K in keyof A | keyof B]: K extends keyof B
    ? K extends keyof A
      ? A[K] extends object
        ? B[K] extends object
          ? DeepMerge<A[K], B[K]>
          : B[K]
        : B[K]
      : B[K]
    : K extends keyof A
      ? A[K]
      : never;
};
'''),

    ("typescript/generics_mapped", r'''<think>
Mapped types in TypeScript are powerful for transforming existing types. I should demonstrate advanced patterns like key remapping, template literal type manipulation with mapped types, and creating type-safe form builders using mapped types.

The key concepts to cover:
1. Key remapping with `as` clause
2. Template literal types for generating method names
3. Mapped type modifiers (+/- readonly, +/- optional)
4. Conditional mapped types that vary behavior per property
</think>

Build advanced TypeScript mapped types for a type-safe API layer including getter/setter generation, event handler types, and a form field builder that derives validation from the source type.''', r'''<think>
I will show practical mapped type patterns that solve real problems: auto-generating getter/setter interfaces, creating event handler types from a state shape, and building form field definitions from a data model. Each pattern demonstrates key remapping and template literal types.
</think>

// Auto-generate getter/setter interface from a plain object type
type Getters<T> = {
  [K in keyof T & string as `get${Capitalize<K>}`]: () => T[K];
};

type Setters<T> = {
  [K in keyof T & string as `set${Capitalize<K>}`]: (value: T[K]) => void;
};

type WithAccessors<T> = T & Getters<T> & Setters<T>;

// Event handler types derived from state shape
type EventHandlers<State> = {
  [K in keyof State & string as `on${Capitalize<K>}Change`]: (
    newValue: State[K],
    oldValue: State[K]
  ) => void;
};

// Form field builder derived from data model
type FieldType<T> = T extends string
  ? "text" | "email" | "password" | "textarea" | "select"
  : T extends number
  ? "number" | "range" | "slider"
  : T extends boolean
  ? "checkbox" | "switch" | "toggle"
  : T extends Date
  ? "date" | "datetime" | "time"
  : T extends Array<infer U>
  ? "multiselect" | "tags" | "checklist"
  : "custom";

type FormFieldConfig<T> = {
  [K in keyof T]: {
    name: K;
    type: FieldType<T[K]>;
    label: string;
    required: undefined extends T[K] ? false : true;
    defaultValue?: T[K];
    validate?: (value: T[K]) => string | null;
    transform?: (raw: unknown) => T[K];
  };
};

// Builder pattern type - tracks which required fields have been set
type RequiredKeys<T> = {
  [K in keyof T]-?: undefined extends T[K] ? never : K;
}[keyof T];

type OptionalKeys<T> = {
  [K in keyof T]-?: undefined extends T[K] ? K : never;
}[keyof T];

// Type-safe builder that enforces all required fields are set
type BuilderState<T, Set extends keyof T = never> = {
  [K in keyof T & string as K extends Set ? never : K]-?: (
    value: T[K]
  ) => BuilderState<T, Set | K>;
} & (RequiredKeys<T> extends Set | RequiredKeys<T>
  ? { build: () => T }
  : {});

// Discriminated union from a record of types
type DiscriminatedUnion<
  T extends Record<string, Record<string, unknown>>,
  D extends string = "type"
> = {
  [K in keyof T]: { [P in D]: K } & T[K];
}[keyof T];

// API endpoint type mapping
type HttpMethods = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

interface EndpointDef {
  params?: Record<string, string>;
  query?: Record<string, string | number | boolean>;
  body?: Record<string, unknown>;
  response: unknown;
}

type ApiEndpoints = {
  "/users": {
    GET: { query: { page: number; limit: number }; response: User[] };
    POST: { body: CreateUserDto; response: User };
  };
  "/users/:id": {
    GET: { params: { id: string }; response: User };
    PUT: { params: { id: string }; body: UpdateUserDto; response: User };
    DELETE: { params: { id: string }; response: void };
  };
};

interface User {
  id: string;
  name: string;
  email: string;
}

interface CreateUserDto {
  name: string;
  email: string;
}

interface UpdateUserDto {
  name?: string;
  email?: string;
}

// Type-safe API client derived from endpoint definitions
type ApiClient<Endpoints extends Record<string, Record<string, EndpointDef>>> = {
  [Path in keyof Endpoints & string]: {
    [Method in keyof Endpoints[Path] & string]: Endpoints[Path][Method] extends EndpointDef
      ? (
          ...args: Endpoints[Path][Method]["body"] extends Record<string, unknown>
            ? [options: {
                params?: Endpoints[Path][Method]["params"];
                query?: Endpoints[Path][Method]["query"];
                body: Endpoints[Path][Method]["body"];
              }]
            : Endpoints[Path][Method]["params"] extends Record<string, string>
            ? [options: {
                params: Endpoints[Path][Method]["params"];
                query?: Endpoints[Path][Method]["query"];
              }]
            : Endpoints[Path][Method]["query"] extends Record<string, unknown>
            ? [options?: { query?: Endpoints[Path][Method]["query"] }]
            : [options?: {}]
        ) => Promise<Endpoints[Path][Method]["response"]>
      : never;
  };
};

// Readonly subset - make only specific keys readonly
type ReadonlyPick<T, K extends keyof T> = Omit<T, K> & Readonly<Pick<T, K>>;

// Rename keys using template literals
type PrefixKeys<T, P extends string> = {
  [K in keyof T & string as `${P}${K}`]: T[K];
};

type SuffixKeys<T, S extends string> = {
  [K in keyof T & string as `${K}${S}`]: T[K];
};
'''),

    ("typescript/generics_inference", r'''Build TypeScript type inference patterns including function overloads with infer, extracting types from complex generic structures, and creating a type-safe dependency injection container with automatic type resolution.''', r'''// Advanced type inference patterns for production TypeScript

// Infer return types from async functions
type UnwrapPromise<T> = T extends Promise<infer U> ? UnwrapPromise<U> : T;

// Infer function parameters and return types
type ParamsOf<T> = T extends (...args: infer P) => any ? P : never;
type ReturnOf<T> = T extends (...args: any[]) => infer R ? R : never;
type AsyncReturnOf<T> = T extends (...args: any[]) => Promise<infer R> ? R : ReturnOf<T>;

// Extract element type from arrays, sets, maps
type ElementOf<T> =
  T extends Array<infer E> ? E :
  T extends Set<infer E> ? E :
  T extends Map<any, infer V> ? V :
  T extends ReadonlyArray<infer E> ? E :
  never;

// Infer constructor parameters
type ConstructorParams<T> = T extends new (...args: infer P) => any ? P : never;
type InstanceOf<T> = T extends new (...args: any[]) => infer I ? I : never;

// Type-safe dependency injection container
type ServiceFactory<T> = () => T;
type ServiceClass<T> = new (...args: any[]) => T;
type ServiceToken<T> = symbol & { __type: T };

function createToken<T>(name: string): ServiceToken<T> {
  return Symbol(name) as ServiceToken<T>;
}

// Registry that tracks bindings at the type level
interface ServiceBinding<T> {
  token: ServiceToken<T>;
  factory: ServiceFactory<T>;
  singleton: boolean;
}

class Container {
  private factories = new Map<symbol, ServiceFactory<any>>();
  private singletons = new Map<symbol, any>();
  private isSingleton = new Set<symbol>();

  bind<T>(token: ServiceToken<T>): BindingBuilder<T> {
    return new BindingBuilder<T>(this, token);
  }

  registerFactory<T>(token: ServiceToken<T>, factory: ServiceFactory<T>,
                     singleton: boolean): void {
    this.factories.set(token as unknown as symbol, factory);
    if (singleton) {
      this.isSingleton.add(token as unknown as symbol);
    }
  }

  resolve<T>(token: ServiceToken<T>): T {
    const sym = token as unknown as symbol;
    if (this.isSingleton.has(sym) && this.singletons.has(sym)) {
      return this.singletons.get(sym) as T;
    }

    const factory = this.factories.get(sym);
    if (!factory) {
      throw new Error(`No binding found for token: ${String(sym)}`);
    }

    const instance = factory() as T;
    if (this.isSingleton.has(sym)) {
      this.singletons.set(sym, instance);
    }
    return instance;
  }

  // Resolve multiple dependencies at once with type safety
  resolveAll<Tokens extends ServiceToken<any>[]>(
    ...tokens: Tokens
  ): { [K in keyof Tokens]: Tokens[K] extends ServiceToken<infer T> ? T : never } {
    return tokens.map((token) => this.resolve(token)) as any;
  }
}

class BindingBuilder<T> {
  constructor(
    private container: Container,
    private token: ServiceToken<T>
  ) {}

  toFactory(factory: ServiceFactory<T>): ScopeBuilder<T> {
    return new ScopeBuilder(this.container, this.token, factory);
  }

  toClass(cls: new (...args: any[]) => T, deps: ServiceToken<any>[] = []): ScopeBuilder<T> {
    const factory = () => {
      const resolvedDeps = deps.map((dep) => this.container.resolve(dep));
      return new cls(...resolvedDeps);
    };
    return new ScopeBuilder(this.container, this.token, factory);
  }

  toValue(value: T): void {
    this.container.registerFactory(this.token, () => value, true);
  }
}

class ScopeBuilder<T> {
  constructor(
    private container: Container,
    private token: ServiceToken<T>,
    private factory: ServiceFactory<T>
  ) {}

  asSingleton(): void {
    this.container.registerFactory(this.token, this.factory, true);
  }

  asTransient(): void {
    this.container.registerFactory(this.token, this.factory, false);
  }
}

// Type-safe pipe function with inferred types through the chain
type PipeFn<A, B> = (input: A) => B;

function pipe<A>(value: A): A;
function pipe<A, B>(value: A, fn1: PipeFn<A, B>): B;
function pipe<A, B, C>(value: A, fn1: PipeFn<A, B>, fn2: PipeFn<B, C>): C;
function pipe<A, B, C, D>(
  value: A, fn1: PipeFn<A, B>, fn2: PipeFn<B, C>, fn3: PipeFn<C, D>
): D;
function pipe(value: any, ...fns: Function[]): any {
  return fns.reduce((acc, fn) => fn(acc), value);
}

// Usage with full type inference
interface LoggerService {
  log(message: string): void;
}

interface DatabaseService {
  query(sql: string): Promise<any[]>;
}

const LoggerToken = createToken<LoggerService>("Logger");
const DatabaseToken = createToken<DatabaseService>("Database");

const container = new Container();
container.bind(LoggerToken).toValue({ log: console.log });
container.bind(DatabaseToken).toFactory(() => ({
  query: async (sql: string) => []
})).asSingleton();

// Type is correctly inferred as [LoggerService, DatabaseService]
const [logger, db] = container.resolveAll(LoggerToken, DatabaseToken);
'''),

    ("typescript/generics_template_literal", r'''Build TypeScript template literal types for a type-safe routing system that extracts path parameters, validates route patterns, and generates type-safe link builder functions.''', r'''// Type-safe routing with template literal types

// Extract path parameter names from a route pattern
type ExtractParams<Path extends string> =
  Path extends `${string}:${infer Param}/${infer Rest}`
    ? Param | ExtractParams<`/${Rest}`>
    : Path extends `${string}:${infer Param}`
      ? Param
      : never;

// Build a params object from extracted parameter names
type RouteParams<Path extends string> = {
  [K in ExtractParams<Path>]: string;
};

// Validate route patterns at the type level
type ValidSegment = string;
type ValidRoute<T extends string> =
  T extends `/${ValidSegment}`
    ? T
    : T extends `/${ValidSegment}/${infer Rest}`
      ? `/${ValidSegment}/${Rest}` extends T ? T : never
      : never;

// Route definition with typed params, query, and response
interface RouteDefinition<
  Path extends string,
  Query extends Record<string, string | number | boolean> = {},
  Response = unknown
> {
  path: Path;
  query?: Query;
  response: Response;
}

// Type-safe route registry
type RouteRegistry = {
  "/users": RouteDefinition<"/users", { page?: number; limit?: number }, User[]>;
  "/users/:id": RouteDefinition<"/users/:id", {}, User>;
  "/users/:id/posts": RouteDefinition<"/users/:id/posts", { status?: string }, Post[]>;
  "/users/:userId/posts/:postId": RouteDefinition<
    "/users/:userId/posts/:postId", {}, Post
  >;
  "/teams/:teamId/members/:memberId/roles": RouteDefinition<
    "/teams/:teamId/members/:memberId/roles", {}, Role[]
  >;
};

interface User { id: string; name: string; email: string; }
interface Post { id: string; title: string; content: string; authorId: string; }
interface Role { id: string; name: string; permissions: string[]; }

// Link builder that enforces correct params for each route
type LinkBuilder<Routes extends Record<string, RouteDefinition<any, any, any>>> = {
  [Path in keyof Routes & string]: ExtractParams<Path> extends never
    ? (query?: Routes[Path] extends RouteDefinition<any, infer Q, any> ? Q : never) => string
    : (
        params: RouteParams<Path>,
        query?: Routes[Path] extends RouteDefinition<any, infer Q, any> ? Q : never
      ) => string;
};

// Implementation of the link builder
function createLinkBuilder<
  Routes extends Record<string, RouteDefinition<any, any, any>>
>(routes: (keyof Routes)[]): LinkBuilder<Routes> {
  const builder: Record<string, Function> = {};

  for (const path of routes) {
    builder[path as string] = (...args: any[]) => {
      const pathStr = path as string;
      const hasParams = pathStr.includes(":");

      let params: Record<string, string> = {};
      let query: Record<string, unknown> = {};

      if (hasParams) {
        params = args[0] || {};
        query = args[1] || {};
      } else {
        query = args[0] || {};
      }

      let result = pathStr;
      for (const [key, value] of Object.entries(params)) {
        result = result.replace(`:${key}`, encodeURIComponent(value));
      }

      const queryParts = Object.entries(query)
        .filter(([, v]) => v !== undefined)
        .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);

      if (queryParts.length > 0) {
        result += `?${queryParts.join("&")}`;
      }

      return result;
    };
  }

  return builder as LinkBuilder<Routes>;
}

// Type-safe event names from nested object keys
type NestedKeyOf<T, Prefix extends string = ""> = T extends object
  ? {
      [K in keyof T & string]: T[K] extends object
        ? NestedKeyOf<T[K], `${Prefix}${K}.`>
        : `${Prefix}${K}`;
    }[keyof T & string]
  : never;

// CSS class name builder with type safety
type BEMBlock<Block extends string> = Block;
type BEMElement<Block extends string, Element extends string> = `${Block}__${Element}`;
type BEMModifier<
  Base extends string,
  Modifier extends string
> = `${Base}--${Modifier}`;

type BEM<
  Block extends string,
  Elements extends string = never,
  Modifiers extends string = never
> =
  | BEMBlock<Block>
  | BEMElement<Block, Elements>
  | BEMModifier<Block, Modifiers>
  | BEMModifier<BEMElement<Block, Elements>, Modifiers>;

// Usage: type ButtonClasses = BEM<"btn", "icon" | "text", "primary" | "disabled">;
// Produces: "btn" | "btn__icon" | "btn__text" | "btn--primary" | "btn--disabled"
//         | "btn__icon--primary" | "btn__icon--disabled" | "btn__text--primary" | ...

// SQL query builder types
type SelectFields<T> = (keyof T & string) | `${keyof T & string} AS ${string}`;
type WhereClause<T> = `${keyof T & string} ${"=" | "!=" | ">" | "<" | ">=" | "<=" | "LIKE"} ?`;
type OrderDirection = "ASC" | "DESC";
type OrderClause<T> = `${keyof T & string} ${OrderDirection}`;

// Usage example
const links = createLinkBuilder<RouteRegistry>([
  "/users",
  "/users/:id",
  "/users/:id/posts",
  "/users/:userId/posts/:postId",
  "/teams/:teamId/members/:memberId/roles",
]);

// All fully type-checked:
const userList = links["/users"]({ page: 1, limit: 20 });
const userDetail = links["/users/:id"]({ id: "123" });
const userPosts = links["/users/:id/posts"]({ id: "123" }, { status: "published" });
const specificPost = links["/users/:userId/posts/:postId"]({
  userId: "123",
  postId: "456",
});
'''),

    ("typescript/generics_recursive", r'''Build recursive TypeScript types for a type-safe JSON schema validator, including nested object validation, array constraints, union discrimination, and error path tracking.''', r'''// Recursive types for a JSON schema validation system

// Schema definition types (recursive)
type Schema =
  | StringSchema
  | NumberSchema
  | BooleanSchema
  | ObjectSchema
  | ArraySchema
  | UnionSchema
  | LiteralSchema
  | NullableSchema;

interface StringSchema {
  type: "string";
  minLength?: number;
  maxLength?: number;
  pattern?: string;
  enum?: readonly string[];
}

interface NumberSchema {
  type: "number";
  min?: number;
  max?: number;
  integer?: boolean;
}

interface BooleanSchema {
  type: "boolean";
}

interface ObjectSchema {
  type: "object";
  properties: Record<string, Schema>;
  required?: readonly string[];
}

interface ArraySchema {
  type: "array";
  items: Schema;
  minItems?: number;
  maxItems?: number;
}

interface UnionSchema {
  type: "union";
  schemas: readonly Schema[];
  discriminator?: string;
}

interface LiteralSchema {
  type: "literal";
  value: string | number | boolean;
}

interface NullableSchema {
  type: "nullable";
  inner: Schema;
}

// Infer TypeScript type from schema definition (recursive)
type InferSchema<S extends Schema> =
  S extends StringSchema
    ? S["enum"] extends readonly string[]
      ? S["enum"][number]
      : string
    : S extends NumberSchema
      ? number
      : S extends BooleanSchema
        ? boolean
        : S extends LiteralSchema
          ? S["value"]
          : S extends NullableSchema
            ? InferSchema<S["inner"]> | null
            : S extends ArraySchema
              ? InferSchema<S["items"]>[]
              : S extends ObjectSchema
                ? InferObject<S>
                : S extends UnionSchema
                  ? InferUnion<S["schemas"]>
                  : never;

// Infer object type with required/optional handling
type InferObject<S extends ObjectSchema> =
  S["required"] extends readonly string[]
    ? {
        [K in keyof S["properties"] & S["required"][number]]: InferSchema<S["properties"][K]>;
      } & {
        [K in Exclude<keyof S["properties"], S["required"][number]>]?: InferSchema<S["properties"][K]>;
      }
    : {
        [K in keyof S["properties"]]?: InferSchema<S["properties"][K]>;
      };

// Infer union from tuple of schemas
type InferUnion<Schemas extends readonly Schema[]> =
  Schemas extends readonly [infer First extends Schema, ...infer Rest extends Schema[]]
    ? InferSchema<First> | InferUnion<Rest>
    : never;

// Validation error with path tracking
interface ValidationError {
  path: string[];
  message: string;
  expected: string;
  received: string;
}

// Runtime validator using the schema types
class SchemaValidator {
  validate<S extends Schema>(schema: S, value: unknown, path: string[] = []): ValidationError[] {
    switch (schema.type) {
      case "string":
        return this.validateString(schema, value, path);
      case "number":
        return this.validateNumber(schema, value, path);
      case "boolean":
        return this.validateBoolean(value, path);
      case "literal":
        return this.validateLiteral(schema, value, path);
      case "nullable":
        if (value === null) return [];
        return this.validate(schema.inner, value, path);
      case "array":
        return this.validateArray(schema, value, path);
      case "object":
        return this.validateObject(schema, value, path);
      case "union":
        return this.validateUnion(schema, value, path);
      default:
        return [{ path, message: "Unknown schema type", expected: "valid schema", received: typeof value }];
    }
  }

  private validateString(schema: StringSchema, value: unknown, path: string[]): ValidationError[] {
    const errors: ValidationError[] = [];
    if (typeof value !== "string") {
      return [{ path, message: "Expected string", expected: "string", received: typeof value }];
    }
    if (schema.minLength !== undefined && value.length < schema.minLength) {
      errors.push({ path, message: `Minimum length ${schema.minLength}`, expected: `>=${schema.minLength} chars`, received: `${value.length} chars` });
    }
    if (schema.maxLength !== undefined && value.length > schema.maxLength) {
      errors.push({ path, message: `Maximum length ${schema.maxLength}`, expected: `<=${schema.maxLength} chars`, received: `${value.length} chars` });
    }
    if (schema.pattern && !new RegExp(schema.pattern).test(value)) {
      errors.push({ path, message: `Pattern mismatch`, expected: schema.pattern, received: value });
    }
    if (schema.enum && !schema.enum.includes(value)) {
      errors.push({ path, message: `Not in enum`, expected: schema.enum.join(" | "), received: value });
    }
    return errors;
  }

  private validateNumber(schema: NumberSchema, value: unknown, path: string[]): ValidationError[] {
    const errors: ValidationError[] = [];
    if (typeof value !== "number" || Number.isNaN(value)) {
      return [{ path, message: "Expected number", expected: "number", received: typeof value }];
    }
    if (schema.integer && !Number.isInteger(value)) {
      errors.push({ path, message: "Expected integer", expected: "integer", received: String(value) });
    }
    if (schema.min !== undefined && value < schema.min) {
      errors.push({ path, message: `Minimum ${schema.min}`, expected: `>=${schema.min}`, received: String(value) });
    }
    if (schema.max !== undefined && value > schema.max) {
      errors.push({ path, message: `Maximum ${schema.max}`, expected: `<=${schema.max}`, received: String(value) });
    }
    return errors;
  }

  private validateBoolean(value: unknown, path: string[]): ValidationError[] {
    if (typeof value !== "boolean") {
      return [{ path, message: "Expected boolean", expected: "boolean", received: typeof value }];
    }
    return [];
  }

  private validateLiteral(schema: LiteralSchema, value: unknown, path: string[]): ValidationError[] {
    if (value !== schema.value) {
      return [{ path, message: `Expected literal ${schema.value}`, expected: String(schema.value), received: String(value) }];
    }
    return [];
  }

  private validateArray(schema: ArraySchema, value: unknown, path: string[]): ValidationError[] {
    if (!Array.isArray(value)) {
      return [{ path, message: "Expected array", expected: "array", received: typeof value }];
    }
    const errors: ValidationError[] = [];
    if (schema.minItems !== undefined && value.length < schema.minItems) {
      errors.push({ path, message: `Min items ${schema.minItems}`, expected: `>=${schema.minItems}`, received: String(value.length) });
    }
    if (schema.maxItems !== undefined && value.length > schema.maxItems) {
      errors.push({ path, message: `Max items ${schema.maxItems}`, expected: `<=${schema.maxItems}`, received: String(value.length) });
    }
    for (let i = 0; i < value.length; i++) {
      errors.push(...this.validate(schema.items, value[i], [...path, String(i)]));
    }
    return errors;
  }

  private validateObject(schema: ObjectSchema, value: unknown, path: string[]): ValidationError[] {
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
      return [{ path, message: "Expected object", expected: "object", received: typeof value }];
    }
    const errors: ValidationError[] = [];
    const obj = value as Record<string, unknown>;
    const required = new Set(schema.required || []);
    for (const [key, propSchema] of Object.entries(schema.properties)) {
      if (key in obj) {
        errors.push(...this.validate(propSchema, obj[key], [...path, key]));
      } else if (required.has(key)) {
        errors.push({ path: [...path, key], message: "Required field missing", expected: "present", received: "undefined" });
      }
    }
    return errors;
  }

  private validateUnion(schema: UnionSchema, value: unknown, path: string[]): ValidationError[] {
    for (const subSchema of schema.schemas) {
      const errors = this.validate(subSchema, value, path);
      if (errors.length === 0) return [];
    }
    return [{ path, message: "No matching union variant", expected: "one of union types", received: typeof value }];
  }
}

// Type-safe schema builder with full inference
function string(opts?: Omit<StringSchema, "type">): StringSchema {
  return { type: "string", ...opts };
}
function number(opts?: Omit<NumberSchema, "type">): NumberSchema {
  return { type: "number", ...opts };
}
function boolean(): BooleanSchema {
  return { type: "boolean" };
}
function object<P extends Record<string, Schema>, R extends readonly (keyof P & string)[]>(
  properties: P, required?: R
): ObjectSchema & { properties: P; required: R } {
  return { type: "object", properties, required } as any;
}
function array<S extends Schema>(items: S, opts?: { minItems?: number; maxItems?: number }): ArraySchema & { items: S } {
  return { type: "array", items, ...opts } as any;
}
'''),
]
