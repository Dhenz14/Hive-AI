"""
Batch p1084: TypeScript API type safety patterns.
Type-safe fetch wrappers, tRPC-like routers, OpenAPI codegen, GraphQL typed operations, API contract testing.
"""

PAIRS = [
    (
        "typescript/api-types",
        r'''Build a fully type-safe fetch wrapper in TypeScript that maps API routes to request/response types, supports path parameters, query strings, and request bodies with compile-time validation.''',
        r'''A type-safe fetch wrapper that maps routes to their request/response contracts:

```typescript
// Define API route map
interface ApiRoutes {
  "GET /users": {
    query: { page?: number; limit?: number; role?: "admin" | "user" };
    response: { users: User[]; total: number };
  };
  "GET /users/:id": {
    params: { id: string };
    response: User;
  };
  "POST /users": {
    body: CreateUserDto;
    response: User;
  };
  "PUT /users/:id": {
    params: { id: string };
    body: UpdateUserDto;
    response: User;
  };
  "DELETE /users/:id": {
    params: { id: string };
    response: { deleted: boolean };
  };
}

interface User {
  id: string;
  name: string;
  email: string;
  role: "admin" | "user";
}

interface CreateUserDto {
  name: string;
  email: string;
  role?: "admin" | "user";
}

interface UpdateUserDto {
  name?: string;
  email?: string;
  role?: "admin" | "user";
}

// Extract method and path from route key
type ExtractMethod<T extends string> = T extends `${infer M} ${string}` ? M : never;
type ExtractPath<T extends string> = T extends `${string} ${infer P}` ? P : never;

// Extract path parameter names
type PathParams<T extends string> = T extends `${string}:${infer Param}/${infer Rest}`
  ? Param | PathParams<Rest>
  : T extends `${string}:${infer Param}`
  ? Param
  : never;

// Build options type from route definition
type RequestOptions<TRoute extends keyof ApiRoutes> =
  (ApiRoutes[TRoute] extends { params: infer P } ? { params: P } : {}) &
  (ApiRoutes[TRoute] extends { query: infer Q } ? { query?: Q } : {}) &
  (ApiRoutes[TRoute] extends { body: infer B } ? { body: B } : {}) &
  { headers?: Record<string, string>; signal?: AbortSignal };

type ResponseType<TRoute extends keyof ApiRoutes> = ApiRoutes[TRoute] extends { response: infer R } ? R : never;

class ApiClientError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    public body: unknown
  ) {
    super(`API Error ${status}: ${statusText}`);
    this.name = "ApiClientError";
  }
}

function buildUrl(
  path: string,
  params?: Record<string, string>,
  query?: Record<string, unknown>
): string {
  let url = path;
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      url = url.replace(`:${key}`, encodeURIComponent(value));
    }
  }
  if (query) {
    const searchParams = new URLSearchParams();
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null) {
        searchParams.set(key, String(value));
      }
    }
    const qs = searchParams.toString();
    if (qs) url += `?${qs}`;
  }
  return url;
}

function createApiClient(baseUrl: string, defaultHeaders?: Record<string, string>) {
  async function request<TRoute extends keyof ApiRoutes>(
    route: TRoute,
    ...args: keyof RequestOptions<TRoute> extends never
      ? [options?: RequestOptions<TRoute>]
      : [options: RequestOptions<TRoute>]
  ): Promise<ResponseType<TRoute>> {
    const options = (args[0] || {}) as Record<string, unknown>;
    const [method, path] = (route as string).split(" ");

    const url = buildUrl(
      `${baseUrl}${path}`,
      options.params as Record<string, string> | undefined,
      options.query as Record<string, unknown> | undefined
    );

    const fetchOptions: RequestInit = {
      method,
      headers: {
        "Content-Type": "application/json",
        ...defaultHeaders,
        ...(options.headers as Record<string, string> | undefined),
      },
      signal: options.signal as AbortSignal | undefined,
    };

    if (options.body) {
      fetchOptions.body = JSON.stringify(options.body);
    }

    const response = await fetch(url, fetchOptions);

    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new ApiClientError(response.status, response.statusText, body);
    }

    return response.json() as Promise<ResponseType<TRoute>>;
  }

  return { request };
}

// Usage - all fully type-checked at compile time
const api = createApiClient("https://api.example.com", {
  Authorization: "Bearer token123",
});

async function demo() {
  // query params are type-checked
  const list = await api.request("GET /users", {
    query: { page: 1, limit: 20, role: "admin" },
  });
  console.log(list.users, list.total);

  // path params required
  const user = await api.request("GET /users/:id", {
    params: { id: "abc123" },
  });
  console.log(user.name, user.email);

  // body is type-checked
  const created = await api.request("POST /users", {
    body: { name: "Alice", email: "alice@test.com" },
  });

  // both params and body
  await api.request("PUT /users/:id", {
    params: { id: created.id },
    body: { name: "Alice Updated" },
  });
}
```

The route map acts as a single source of truth. Every call to `api.request` is validated at compile time for the correct method, path params, query shape, and body shape, and the return type is automatically inferred from the route definition.'''
    ),
    (
        "typescript/api-types",
        r'''<think>
The user wants a tRPC-like type-safe router implementation. I need to build the core abstraction: procedure definitions with input validation, middleware chaining, and router composition. The key insight in tRPC is that the client infers types directly from the server router definition without any codegen step. I should show:

1. A procedure builder with input/output typing
2. Router that groups procedures
3. A caller/client that infers all types from the router
4. Middleware support for auth context

Let me focus on the type-level machinery that makes this work - mapped types over the router definition to produce a typed client interface.
</think>
Implement a tRPC-inspired type-safe RPC layer in TypeScript. Include procedure definitions with input validation, router composition, middleware for auth context, and a client proxy that infers all types from the server router definition with zero codegen.''',
        r'''A minimal tRPC-like type-safe RPC system:

```typescript
// Schema validation primitive (simplified Zod-like)
interface Schema<T> {
  parse(data: unknown): T;
  _type: T;
}

function object<T extends Record<string, Schema<unknown>>>(
  shape: T
): Schema<{ [K in keyof T]: T[K]["_type"] }> {
  return {
    _type: {} as { [K in keyof T]: T[K]["_type"] },
    parse(data: unknown) {
      if (typeof data !== "object" || data === null) {
        throw new Error("Expected object");
      }
      const result: Record<string, unknown> = {};
      for (const [key, schema] of Object.entries(shape)) {
        result[key] = schema.parse((data as Record<string, unknown>)[key]);
      }
      return result as { [K in keyof T]: T[K]["_type"] };
    },
  };
}

function string(): Schema<string> {
  return {
    _type: "" as string,
    parse(data: unknown) {
      if (typeof data !== "string") throw new Error("Expected string");
      return data;
    },
  };
}

function number(): Schema<number> {
  return {
    _type: 0 as number,
    parse(data: unknown) {
      if (typeof data !== "number") throw new Error("Expected number");
      return data;
    },
  };
}

// Context and middleware types
interface BaseContext {
  req: { headers: Record<string, string> };
}

interface AuthContext extends BaseContext {
  userId: string;
  role: "admin" | "user";
}

type MiddlewareFn<TCtxIn, TCtxOut> = (ctx: TCtxIn) => Promise<TCtxOut>;

// Procedure builder
interface ProcedureDef<TCtx, TInput, TOutput> {
  _ctx: TCtx;
  _input: TInput;
  _output: TOutput;
  middlewares: MiddlewareFn<any, any>[];
  inputSchema?: Schema<TInput>;
  resolver: (opts: { ctx: TCtx; input: TInput }) => Promise<TOutput>;
}

class ProcedureBuilder<TCtx> {
  private middlewares: MiddlewareFn<any, any>[] = [];

  constructor(private baseMiddlewares: MiddlewareFn<any, any>[] = []) {
    this.middlewares = [...baseMiddlewares];
  }

  use<TNewCtx>(mw: MiddlewareFn<TCtx, TNewCtx>): ProcedureBuilder<TNewCtx> {
    const builder = new ProcedureBuilder<TNewCtx>([...this.middlewares, mw]);
    return builder;
  }

  input<TInput>(schema: Schema<TInput>) {
    const middlewares = this.middlewares;
    return {
      query<TOutput>(
        resolver: (opts: { ctx: TCtx; input: TInput }) => Promise<TOutput>
      ): ProcedureDef<TCtx, TInput, TOutput> {
        return { _ctx: {} as TCtx, _input: {} as TInput, _output: {} as TOutput, middlewares, inputSchema: schema, resolver };
      },
      mutation<TOutput>(
        resolver: (opts: { ctx: TCtx; input: TInput }) => Promise<TOutput>
      ): ProcedureDef<TCtx, TInput, TOutput> {
        return { _ctx: {} as TCtx, _input: {} as TInput, _output: {} as TOutput, middlewares, inputSchema: schema, resolver };
      },
    };
  }

  query<TOutput>(
    resolver: (opts: { ctx: TCtx; input: void }) => Promise<TOutput>
  ): ProcedureDef<TCtx, void, TOutput> {
    return { _ctx: {} as TCtx, _input: undefined as void, _output: {} as TOutput, middlewares: this.middlewares, resolver };
  }
}

// Router definition
type AnyProcedure = ProcedureDef<any, any, any>;
type RouterDef = Record<string, AnyProcedure>;

function router<T extends RouterDef>(procedures: T): T {
  return procedures;
}

// Infer client types from router
type InferInput<T> = T extends ProcedureDef<any, infer I, any> ? I : never;
type InferOutput<T> = T extends ProcedureDef<any, any, infer O> ? O : never;

type RouterClient<TRouter extends RouterDef> = {
  [K in keyof TRouter]: InferInput<TRouter[K]> extends void
    ? () => Promise<InferOutput<TRouter[K]>>
    : (input: InferInput<TRouter[K]>) => Promise<InferOutput<TRouter[K]>>;
};

// Execute procedure with middleware chain
async function executeProcedure(
  proc: AnyProcedure,
  baseCtx: BaseContext,
  rawInput: unknown
): Promise<unknown> {
  let ctx: unknown = baseCtx;
  for (const mw of proc.middlewares) {
    ctx = await mw(ctx);
  }
  const input = proc.inputSchema ? proc.inputSchema.parse(rawInput) : undefined;
  return proc.resolver({ ctx, input });
}

// Create typed client proxy
function createClient<TRouter extends RouterDef>(
  routerDef: TRouter,
  baseUrl: string
): RouterClient<TRouter> {
  return new Proxy({} as RouterClient<TRouter>, {
    get(_, procedureName: string) {
      return async (input?: unknown) => {
        const resp = await fetch(`${baseUrl}/rpc/${procedureName}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ input }),
        });
        if (!resp.ok) throw new Error(`RPC failed: ${resp.statusText}`);
        return resp.json();
      };
    },
  });
}

// Auth middleware
const authMiddleware: MiddlewareFn<BaseContext, AuthContext> = async (ctx) => {
  const token = ctx.req.headers["authorization"]?.replace("Bearer ", "");
  if (!token) throw new Error("Unauthorized");
  // In production, verify JWT here
  return { ...ctx, userId: "user_123", role: "admin" as const };
};

// Define procedures
const publicProcedure = new ProcedureBuilder<BaseContext>();
const protectedProcedure = publicProcedure.use(authMiddleware);

// Build the router
const appRouter = router({
  getUser: protectedProcedure
    .input(object({ id: string() }))
    .query(async ({ ctx, input }) => {
      return { id: input.id, name: "Alice", role: ctx.role };
    }),

  listUsers: publicProcedure.query(async () => {
    return { users: [{ id: "1", name: "Alice" }], total: 1 };
  }),

  createUser: protectedProcedure
    .input(object({ name: string(), email: string() }))
    .mutation(async ({ ctx, input }) => {
      return { id: "new_id", name: input.name, email: input.email, createdBy: ctx.userId };
    }),
});

type AppRouter = typeof appRouter;

// Client usage - fully typed from server definition
const client = createClient(appRouter, "https://api.example.com");

async function demo() {
  const user = await client.getUser({ id: "123" });
  // user is typed as { id: string; name: string; role: "admin" | "user" }

  const list = await client.listUsers();
  // list is typed as { users: { id: string; name: string }[]; total: number }

  const created = await client.createUser({ name: "Bob", email: "bob@test.com" });
  // created is typed as { id: string; name: string; email: string; createdBy: string }
}
```

The router definition is the single source of truth. The `RouterClient` mapped type walks each procedure and extracts its input/output types, so the client proxy is fully typed without any code generation step.'''
    ),
    (
        "typescript/api-types",
        r'''Create a TypeScript utility that generates fully typed API client code from an OpenAPI 3.0 schema definition object. The generator should produce typed interfaces for request/response bodies, path parameters, and a typed client class with methods for each endpoint.''',
        r'''An OpenAPI schema-driven typed client generator:

```typescript
// OpenAPI schema types (subset for demonstration)
interface OpenApiSchema {
  openapi: string;
  info: { title: string; version: string };
  paths: Record<string, PathItem>;
  components?: {
    schemas?: Record<string, SchemaObject>;
  };
}

interface PathItem {
  get?: Operation;
  post?: Operation;
  put?: Operation;
  delete?: Operation;
  patch?: Operation;
}

interface Operation {
  operationId: string;
  summary?: string;
  parameters?: Parameter[];
  requestBody?: RequestBody;
  responses: Record<string, ResponseDef>;
}

interface Parameter {
  name: string;
  in: "path" | "query" | "header";
  required?: boolean;
  schema: SchemaObject;
}

interface RequestBody {
  required?: boolean;
  content: Record<string, { schema: SchemaObject }>;
}

interface ResponseDef {
  description: string;
  content?: Record<string, { schema: SchemaObject }>;
}

interface SchemaObject {
  type?: string;
  properties?: Record<string, SchemaObject>;
  required?: string[];
  items?: SchemaObject;
  enum?: string[];
  $ref?: string;
}

// Code generator
class TypeScriptGenerator {
  private interfaces: string[] = [];
  private methods: string[] = [];
  private generatedTypes = new Set<string>();

  generate(spec: OpenApiSchema): string {
    const lines: string[] = [];
    lines.push("// Auto-generated from OpenAPI spec");
    lines.push(`// ${spec.info.title} v${spec.info.version}`);
    lines.push("");

    // Generate component schemas first
    if (spec.components?.schemas) {
      for (const [name, schema] of Object.entries(spec.components.schemas)) {
        lines.push(this.generateInterface(name, schema));
      }
    }

    // Generate endpoint types and methods
    for (const [path, pathItem] of Object.entries(spec.paths)) {
      for (const [method, operation] of Object.entries(pathItem)) {
        if (!operation || typeof operation !== "object" || !("operationId" in operation)) continue;
        const op = operation as Operation;
        lines.push(this.generateEndpointTypes(path, method, op));
        this.methods.push(this.generateMethod(path, method, op));
      }
    }

    // Generate the client class
    lines.push("");
    lines.push("class ApiClient {");
    lines.push("  constructor(private baseUrl: string, private headers: Record<string, string> = {}) {}");
    lines.push("");
    lines.push("  private async fetch<T>(url: string, init: RequestInit): Promise<T> {");
    lines.push("    const resp = await fetch(url, {");
    lines.push("      ...init,");
    lines.push('      headers: { "Content-Type": "application/json", ...this.headers, ...init.headers },');
    lines.push("    });");
    lines.push('    if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);');
    lines.push("    return resp.json() as Promise<T>;");
    lines.push("  }");
    lines.push("");
    for (const m of this.methods) {
      lines.push(m);
    }
    lines.push("}");

    return lines.join("\n");
  }

  private generateInterface(name: string, schema: SchemaObject): string {
    if (this.generatedTypes.has(name)) return "";
    this.generatedTypes.add(name);

    if (!schema.properties) {
      return `type ${name} = ${this.schemaToType(schema)};\n`;
    }

    const required = new Set(schema.required || []);
    const fields = Object.entries(schema.properties).map(([prop, propSchema]) => {
      const optional = required.has(prop) ? "" : "?";
      return `  ${prop}${optional}: ${this.schemaToType(propSchema)};`;
    });

    return `interface ${name} {\n${fields.join("\n")}\n}\n`;
  }

  private schemaToType(schema: SchemaObject): string {
    if (schema.$ref) {
      const refName = schema.$ref.split("/").pop()!;
      return refName;
    }
    if (schema.enum) {
      return schema.enum.map((v) => `"${v}"`).join(" | ");
    }
    switch (schema.type) {
      case "string": return "string";
      case "integer":
      case "number": return "number";
      case "boolean": return "boolean";
      case "array": return `${this.schemaToType(schema.items!)}[]`;
      case "object": {
        if (!schema.properties) return "Record<string, unknown>";
        const required = new Set(schema.required || []);
        const fields = Object.entries(schema.properties).map(([k, v]) => {
          const opt = required.has(k) ? "" : "?";
          return `${k}${opt}: ${this.schemaToType(v)}`;
        });
        return `{ ${fields.join("; ")} }`;
      }
      default: return "unknown";
    }
  }

  private generateEndpointTypes(path: string, method: string, op: Operation): string {
    const lines: string[] = [];
    const baseName = this.capitalize(op.operationId);

    // Path params interface
    const pathParams = (op.parameters || []).filter((p) => p.in === "path");
    if (pathParams.length > 0) {
      const fields = pathParams.map((p) => `  ${p.name}: ${this.schemaToType(p.schema)};`);
      lines.push(`interface ${baseName}Params {\n${fields.join("\n")}\n}\n`);
    }

    // Query params interface
    const queryParams = (op.parameters || []).filter((p) => p.in === "query");
    if (queryParams.length > 0) {
      const fields = queryParams.map((p) => {
        const opt = p.required ? "" : "?";
        return `  ${p.name}${opt}: ${this.schemaToType(p.schema)};`;
      });
      lines.push(`interface ${baseName}Query {\n${fields.join("\n")}\n}\n`);
    }

    return lines.join("\n");
  }

  private generateMethod(path: string, method: string, op: Operation): string {
    const baseName = this.capitalize(op.operationId);
    const params: string[] = [];
    const pathParams = (op.parameters || []).filter((p) => p.in === "path");
    const queryParams = (op.parameters || []).filter((p) => p.in === "query");

    if (pathParams.length > 0) params.push(`params: ${baseName}Params`);
    if (queryParams.length > 0) params.push(`query?: ${baseName}Query`);

    let bodyType = "void";
    if (op.requestBody?.content?.["application/json"]) {
      bodyType = this.schemaToType(op.requestBody.content["application/json"].schema);
      params.push(`body: ${bodyType}`);
    }

    // Determine response type
    let responseType = "void";
    const okResponse = op.responses["200"] || op.responses["201"];
    if (okResponse?.content?.["application/json"]) {
      responseType = this.schemaToType(okResponse.content["application/json"].schema);
    }

    // Build URL with path param substitution
    let urlExpr = "`${this.baseUrl}" + path.replace(/{(\w+)}/g, "${params.$1}") + "`";
    if (queryParams.length > 0) {
      urlExpr = `${urlExpr} + (query ? "?" + new URLSearchParams(query as any).toString() : "")`;
    }

    const fetchBody = bodyType !== "void" ? "body: JSON.stringify(body), " : "";
    const summary = op.summary ? `  /** ${op.summary} */\n` : "";

    return [
      summary + `  async ${op.operationId}(${params.join(", ")}): Promise<${responseType}> {`,
      `    return this.fetch<${responseType}>(${urlExpr}, {`,
      `      method: "${method.toUpperCase()}", ${fetchBody}`,
      "    });",
      "  }",
      "",
    ].join("\n");
  }

  private capitalize(s: string): string {
    return s.charAt(0).toUpperCase() + s.slice(1);
  }
}

// Example usage
const spec: OpenApiSchema = {
  openapi: "3.0.0",
  info: { title: "Users API", version: "1.0.0" },
  paths: {
    "/users": {
      get: {
        operationId: "listUsers",
        summary: "List all users with pagination",
        parameters: [
          { name: "page", in: "query", schema: { type: "integer" } },
          { name: "limit", in: "query", schema: { type: "integer" } },
        ],
        responses: {
          "200": {
            description: "User list",
            content: {
              "application/json": {
                schema: { type: "array", items: { $ref: "#/components/schemas/User" } },
              },
            },
          },
        },
      },
    },
  },
  components: {
    schemas: {
      User: {
        type: "object",
        required: ["id", "name", "email"],
        properties: {
          id: { type: "string" },
          name: { type: "string" },
          email: { type: "string" },
          role: { type: "string", enum: ["admin", "user", "moderator"] },
        },
      },
    },
  },
};

const generator = new TypeScriptGenerator();
console.log(generator.generate(spec));
```

This generator walks the OpenAPI spec tree and emits TypeScript interfaces for every component schema, endpoint parameter set, and response type. The client class methods have fully typed signatures derived from the spec, including path parameter interpolation and optional query string building.'''
    ),
    (
        "typescript/api-types",
        r'''<think>
The user wants typed GraphQL operations. The challenge is mapping GraphQL query strings to TypeScript types. In a real codebase this is done with codegen tools like graphql-codegen, but I can show how to build a typed document approach where you define the query alongside its expected result type. Key pieces:
1. A TypedDocumentNode concept that carries input/output types
2. A typed client that uses the document's generic params
3. Fragment composition with type merging
4. Type-safe variables

I should show a practical pattern that mirrors what graphql-codegen produces but is understandable on its own.
</think>
Implement a type-safe GraphQL client in TypeScript that uses typed document nodes to ensure query variables and result types are checked at compile time. Include fragment composition, error handling, and cache integration.''',
        r'''A typed GraphQL client with document nodes, fragments, and caching:

```typescript
// Core typed document node - carries variable and result types
interface TypedDocumentNode<TResult, TVariables = Record<string, never>> {
  __resultType: TResult;
  __variablesType: TVariables;
  query: string;
  fragmentDefs?: string[];
}

function gql<TResult, TVariables = Record<string, never>>(
  query: string,
  ...fragments: TypedDocumentNode<unknown, unknown>[]
): TypedDocumentNode<TResult, TVariables> {
  const fragmentDefs = fragments.flatMap((f) => f.fragmentDefs || [f.query]);
  return {
    __resultType: {} as TResult,
    __variablesType: {} as TVariables,
    query: [...fragmentDefs, query].join("\n\n"),
    fragmentDefs,
  };
}

// GraphQL response shape
interface GraphQLResponse<T> {
  data?: T;
  errors?: GraphQLError[];
}

interface GraphQLError {
  message: string;
  locations?: { line: number; column: number }[];
  path?: (string | number)[];
  extensions?: Record<string, unknown>;
}

class GraphQLClientError extends Error {
  constructor(
    public errors: GraphQLError[],
    public partialData?: unknown
  ) {
    super(errors.map((e) => e.message).join("; "));
    this.name = "GraphQLClientError";
  }
}

// Simple in-memory cache
class QueryCache {
  private store = new Map<string, { data: unknown; timestamp: number }>();
  private ttlMs: number;

  constructor(ttlMs: number = 60_000) {
    this.ttlMs = ttlMs;
  }

  private makeKey(query: string, variables: unknown): string {
    return JSON.stringify({ q: query, v: variables });
  }

  get<T>(query: string, variables: unknown): T | undefined {
    const key = this.makeKey(query, variables);
    const entry = this.store.get(key);
    if (!entry) return undefined;
    if (Date.now() - entry.timestamp > this.ttlMs) {
      this.store.delete(key);
      return undefined;
    }
    return entry.data as T;
  }

  set(query: string, variables: unknown, data: unknown): void {
    const key = this.makeKey(query, variables);
    this.store.set(key, { data, timestamp: Date.now() });
  }

  invalidate(pattern?: RegExp): void {
    if (!pattern) {
      this.store.clear();
      return;
    }
    for (const key of this.store.keys()) {
      if (pattern.test(key)) this.store.delete(key);
    }
  }
}

// The typed client
class GraphQLClient {
  private cache: QueryCache;

  constructor(
    private endpoint: string,
    private headers: Record<string, string> = {},
    cacheTtlMs?: number
  ) {
    this.cache = new QueryCache(cacheTtlMs);
  }

  async query<TResult, TVariables>(
    document: TypedDocumentNode<TResult, TVariables>,
    ...args: TVariables extends Record<string, never>
      ? [options?: { variables?: TVariables; skipCache?: boolean }]
      : [options: { variables: TVariables; skipCache?: boolean }]
  ): Promise<TResult> {
    const options = args[0] || {};
    const variables = (options as { variables?: TVariables }).variables;
    const skipCache = (options as { skipCache?: boolean }).skipCache;

    if (!skipCache) {
      const cached = this.cache.get<TResult>(document.query, variables);
      if (cached !== undefined) return cached;
    }

    const result = await this.execute<TResult>(document.query, variables);
    this.cache.set(document.query, variables, result);
    return result;
  }

  async mutate<TResult, TVariables>(
    document: TypedDocumentNode<TResult, TVariables>,
    ...args: TVariables extends Record<string, never>
      ? [options?: { variables?: TVariables }]
      : [options: { variables: TVariables }]
  ): Promise<TResult> {
    const variables = (args[0] as { variables?: TVariables } | undefined)?.variables;
    // Mutations always bypass and invalidate cache
    this.cache.invalidate();
    return this.execute<TResult>(document.query, variables);
  }

  private async execute<T>(query: string, variables?: unknown): Promise<T> {
    const resp = await fetch(this.endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...this.headers },
      body: JSON.stringify({ query, variables }),
    });

    if (!resp.ok) {
      throw new Error(`GraphQL HTTP error: ${resp.status}`);
    }

    const json = (await resp.json()) as GraphQLResponse<T>;

    if (json.errors?.length) {
      throw new GraphQLClientError(json.errors, json.data);
    }

    if (!json.data) {
      throw new Error("GraphQL response missing data");
    }

    return json.data;
  }
}

// Define typed fragments and queries
interface UserFields {
  id: string;
  name: string;
  email: string;
  avatarUrl: string;
}

const UserFragment = gql<UserFields>(`
  fragment UserFields on User {
    id
    name
    email
    avatarUrl
  }
`);

interface PostFields {
  id: string;
  title: string;
  body: string;
  createdAt: string;
  author: UserFields;
}

const PostFragment = gql<PostFields>(`
  fragment PostFields on Post {
    id
    title
    body
    createdAt
    author {
      ...UserFields
    }
  }
`, UserFragment);

// Queries with composed fragments
interface GetPostsResult {
  posts: {
    edges: { node: PostFields; cursor: string }[];
    pageInfo: { hasNextPage: boolean; endCursor: string };
  };
}

interface GetPostsVars {
  first: number;
  after?: string;
}

const GET_POSTS = gql<GetPostsResult, GetPostsVars>(`
  query GetPosts($first: Int!, $after: String) {
    posts(first: $first, after: $after) {
      edges {
        node { ...PostFields }
        cursor
      }
      pageInfo { hasNextPage endCursor }
    }
  }
`, PostFragment);

interface CreatePostResult {
  createPost: PostFields;
}

interface CreatePostVars {
  title: string;
  body: string;
}

const CREATE_POST = gql<CreatePostResult, CreatePostVars>(`
  mutation CreatePost($title: String!, $body: String!) {
    createPost(input: { title: $title, body: $body }) {
      ...PostFields
    }
  }
`, PostFragment);

// Usage - all type-safe
const client = new GraphQLClient("https://api.example.com/graphql", {
  Authorization: "Bearer token",
});

async function demo() {
  // Variables and result fully typed
  const data = await client.query(GET_POSTS, {
    variables: { first: 10 },
  });
  for (const edge of data.posts.edges) {
    console.log(edge.node.title, edge.node.author.name);
  }

  const created = await client.mutate(CREATE_POST, {
    variables: { title: "Hello", body: "World" },
  });
  console.log(created.createPost.id);
}
```

The `TypedDocumentNode` pattern carries result and variable types as generic parameters. Fragments compose by passing them to `gql`, which concatenates their definitions. The client methods use conditional types to only require `variables` when the document declares them.'''
    ),
    (
        "typescript/api-types",
        r'''Build a TypeScript API contract testing framework that validates runtime API responses against declared TypeScript interfaces. Include type assertion helpers, schema diffing for backward compatibility checks, and test runner integration with clear error reporting.''',
        r'''An API contract testing framework with runtime validation and backward compatibility:

```typescript
// Schema descriptor built from TypeScript interface shapes
type TypeDescriptor =
  | { kind: "string" }
  | { kind: "number" }
  | { kind: "boolean" }
  | { kind: "null" }
  | { kind: "array"; items: TypeDescriptor }
  | { kind: "object"; properties: Record<string, { descriptor: TypeDescriptor; required: boolean }> }
  | { kind: "union"; variants: TypeDescriptor[] }
  | { kind: "literal"; value: string | number | boolean };

// Build descriptors (normally generated from TS types, here manual)
function str(): TypeDescriptor { return { kind: "string" }; }
function num(): TypeDescriptor { return { kind: "number" }; }
function bool(): TypeDescriptor { return { kind: "boolean" }; }
function literal(v: string | number | boolean): TypeDescriptor { return { kind: "literal", value: v }; }
function arr(items: TypeDescriptor): TypeDescriptor { return { kind: "array", items }; }
function union(...variants: TypeDescriptor[]): TypeDescriptor { return { kind: "union", variants }; }

function obj(props: Record<string, TypeDescriptor | [TypeDescriptor, boolean]>): TypeDescriptor {
  const properties: Record<string, { descriptor: TypeDescriptor; required: boolean }> = {};
  for (const [key, val] of Object.entries(props)) {
    if (Array.isArray(val)) {
      properties[key] = { descriptor: val[0], required: val[1] };
    } else {
      properties[key] = { descriptor: val, required: true };
    }
  }
  return { kind: "object", properties };
}

// Validation engine
interface ValidationError {
  path: string;
  expected: string;
  received: string;
}

function validate(value: unknown, descriptor: TypeDescriptor, path: string = "$"): ValidationError[] {
  const errors: ValidationError[] = [];

  switch (descriptor.kind) {
    case "string":
      if (typeof value !== "string") {
        errors.push({ path, expected: "string", received: typeof value });
      }
      break;

    case "number":
      if (typeof value !== "number") {
        errors.push({ path, expected: "number", received: typeof value });
      }
      break;

    case "boolean":
      if (typeof value !== "boolean") {
        errors.push({ path, expected: "boolean", received: typeof value });
      }
      break;

    case "null":
      if (value !== null) {
        errors.push({ path, expected: "null", received: String(value) });
      }
      break;

    case "literal":
      if (value !== descriptor.value) {
        errors.push({ path, expected: `literal(${JSON.stringify(descriptor.value)})`, received: JSON.stringify(value) });
      }
      break;

    case "array":
      if (!Array.isArray(value)) {
        errors.push({ path, expected: "array", received: typeof value });
      } else {
        for (let i = 0; i < value.length; i++) {
          errors.push(...validate(value[i], descriptor.items, `${path}[${i}]`));
        }
      }
      break;

    case "object":
      if (typeof value !== "object" || value === null || Array.isArray(value)) {
        errors.push({ path, expected: "object", received: value === null ? "null" : typeof value });
      } else {
        const obj = value as Record<string, unknown>;
        for (const [key, prop] of Object.entries(descriptor.properties)) {
          if (prop.required && !(key in obj)) {
            errors.push({ path: `${path}.${key}`, expected: "present", received: "missing" });
          } else if (key in obj) {
            errors.push(...validate(obj[key], prop.descriptor, `${path}.${key}`));
          }
        }
      }
      break;

    case "union": {
      const allErrors = descriptor.variants.map((v) => validate(value, v, path));
      const anyMatch = allErrors.some((e) => e.length === 0);
      if (!anyMatch) {
        errors.push({
          path,
          expected: `one of ${descriptor.variants.length} union variants`,
          received: JSON.stringify(value).slice(0, 100),
        });
      }
      break;
    }
  }

  return errors;
}

// Backward compatibility checker
interface CompatibilityIssue {
  path: string;
  kind: "removed_required_field" | "type_changed" | "field_became_required" | "new_required_field";
  details: string;
}

function checkBackwardCompatibility(
  previous: TypeDescriptor,
  current: TypeDescriptor,
  path: string = "$"
): CompatibilityIssue[] {
  const issues: CompatibilityIssue[] = [];

  if (previous.kind !== current.kind) {
    issues.push({ path, kind: "type_changed", details: `${previous.kind} -> ${current.kind}` });
    return issues;
  }

  if (previous.kind === "object" && current.kind === "object") {
    // Check for removed required fields
    for (const [key, prop] of Object.entries(previous.properties)) {
      if (prop.required && !current.properties[key]) {
        issues.push({
          path: `${path}.${key}`,
          kind: "removed_required_field",
          details: `Required field "${key}" was removed`,
        });
      }
      if (current.properties[key]) {
        issues.push(...checkBackwardCompatibility(
          prop.descriptor, current.properties[key].descriptor, `${path}.${key}`
        ));
        // Check if optional became required
        if (!prop.required && current.properties[key].required) {
          issues.push({
            path: `${path}.${key}`,
            kind: "field_became_required",
            details: `Optional field "${key}" is now required`,
          });
        }
      }
    }
    // New required fields are breaking
    for (const [key, prop] of Object.entries(current.properties)) {
      if (prop.required && !previous.properties[key]) {
        issues.push({
          path: `${path}.${key}`,
          kind: "new_required_field",
          details: `New required field "${key}" added`,
        });
      }
    }
  }

  if (previous.kind === "array" && current.kind === "array") {
    issues.push(...checkBackwardCompatibility(previous.items, current.items, `${path}[]`));
  }

  return issues;
}

// Test runner
interface ContractTest {
  name: string;
  endpoint: string;
  method: "GET" | "POST" | "PUT" | "DELETE";
  headers?: Record<string, string>;
  body?: unknown;
  expectedStatus: number;
  responseSchema: TypeDescriptor;
}

interface TestResult {
  name: string;
  passed: boolean;
  duration: number;
  errors: ValidationError[];
  httpStatus?: number;
}

async function runContractTests(
  baseUrl: string,
  tests: ContractTest[],
  globalHeaders?: Record<string, string>
): Promise<{ results: TestResult[]; summary: { total: number; passed: number; failed: number } }> {
  const results: TestResult[] = [];

  for (const test of tests) {
    const start = performance.now();
    try {
      const resp = await fetch(`${baseUrl}${test.endpoint}`, {
        method: test.method,
        headers: { "Content-Type": "application/json", ...globalHeaders, ...test.headers },
        body: test.body ? JSON.stringify(test.body) : undefined,
      });

      const duration = performance.now() - start;

      if (resp.status !== test.expectedStatus) {
        results.push({
          name: test.name,
          passed: false,
          duration,
          httpStatus: resp.status,
          errors: [{ path: "$status", expected: String(test.expectedStatus), received: String(resp.status) }],
        });
        continue;
      }

      const body = await resp.json();
      const errors = validate(body, test.responseSchema);

      results.push({ name: test.name, passed: errors.length === 0, duration, httpStatus: resp.status, errors });
    } catch (err) {
      results.push({
        name: test.name,
        passed: false,
        duration: performance.now() - start,
        errors: [{ path: "$network", expected: "response", received: String(err) }],
      });
    }
  }

  const passed = results.filter((r) => r.passed).length;
  return {
    results,
    summary: { total: results.length, passed, failed: results.length - passed },
  };
}

// Define contracts
const UserSchema = obj({
  id: str(),
  name: str(),
  email: str(),
  role: union(literal("admin"), literal("user")),
  createdAt: str(),
});

const tests: ContractTest[] = [
  {
    name: "GET /users returns paginated list",
    endpoint: "/users?page=1&limit=10",
    method: "GET",
    expectedStatus: 200,
    responseSchema: obj({
      users: arr(UserSchema),
      total: num(),
      page: num(),
      limit: num(),
    }),
  },
  {
    name: "POST /users creates user",
    endpoint: "/users",
    method: "POST",
    body: { name: "Test", email: "test@test.com" },
    expectedStatus: 201,
    responseSchema: UserSchema,
  },
];

// Run and report
async function main() {
  const { results, summary } = await runContractTests("https://api.example.com", tests);
  for (const r of results) {
    const icon = r.passed ? "PASS" : "FAIL";
    console.log(`[${icon}] ${r.name} (${r.duration.toFixed(0)}ms)`);
    for (const e of r.errors) {
      console.log(`  ${e.path}: expected ${e.expected}, got ${e.received}`);
    }
  }
  console.log(`\n${summary.passed}/${summary.total} passed, ${summary.failed} failed`);
}
```

This framework provides three layers: runtime validation that checks API responses match declared shapes, backward compatibility checking that detects breaking changes between schema versions, and a test runner that exercises real endpoints and reports mismatches with precise JSON paths.'''
    ),
]
