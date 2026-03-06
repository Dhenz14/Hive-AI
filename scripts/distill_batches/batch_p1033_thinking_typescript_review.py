r"""Thinking-trace pairs: TypeScript code review and refactoring."""

PAIRS = [
    ("thinking/code-review", r'''Review this TypeScript code and identify issues:

```typescript
interface User {
  id: number;
  name: string;
  email: string;
  role: string;
  settings: any;
  metadata: object;
}

interface ApiResponse<T> {
  data: T;
  error: string | null;
  status: number;
}

async function fetchUser(id: number): Promise<ApiResponse<User>> {
  const response = await fetch(`/api/users/${id}`);
  const data = await response.json();
  return { data, error: null, status: response.status };
}

function updateUser(user: User, updates: Partial<User>): User {
  return { ...user, ...updates };
}

function getUserRole(user: User): string {
  return user.role;
}

function isAdmin(user: User): boolean {
  return user.role === 'admin' || user.role === 'superadmin' || user.role === 'root';
}

function formatUser(user: User): string {
  return `${user.name} (${user.email}) - ${user.role}`;
}

type EventHandler = (event: any) => void;

class EventBus {
  private handlers: { [key: string]: EventHandler[] } = {};

  on(event: string, handler: EventHandler): void {
    if (!this.handlers[event]) {
      this.handlers[event] = [];
    }
    this.handlers[event].push(handler);
  }

  emit(event: string, data?: any): void {
    (this.handlers[event] || []).forEach(h => h(data));
  }

  off(event: string, handler: EventHandler): void {
    this.handlers[event] = (this.handlers[event] || []).filter(h => h !== handler);
  }
}

function processItems<T>(items: T[], processor: (item: T) => T): T[] {
  const results: T[] = [];
  for (let i = 0; i < items.length; i++) {
    results.push(processor(items[i]));
  }
  return results;
}

type Config = {
  apiUrl: string;
  timeout: number;
  retries: number;
  debug: boolean;
  features: { [key: string]: boolean };
  headers: { [key: string]: string };
};

function createConfig(overrides: Partial<Config>): Config {
  const defaults: Config = {
    apiUrl: 'http://localhost:3000',
    timeout: 5000,
    retries: 3,
    debug: false,
    features: {},
    headers: {},
  };
  return { ...defaults, ...overrides };
}
```''', r'''<think>
Let me review this TypeScript code for type safety issues.

1. `any` type usage:
- User.settings is typed as `any`. This completely bypasses TypeScript's type checking. Any operation on settings is unchecked. Should define a proper interface.
- User.metadata is typed as `object`. This is almost as bad as any -- you can assign any object but cannot access any properties without casting.
- EventHandler uses `(event: any) => void`. All type information about events is lost.
- EventBus.emit takes `data?: any`. No type connection between event names and their data shapes.

2. Role as string:
- User.role is `string`. The isAdmin function compares against specific string values ('admin', 'superadmin', 'root'). Using a string union type or enum would catch typos at compile time:
```typescript
type Role = 'admin' | 'superadmin' | 'root' | 'user' | 'viewer';
```

3. fetchUser error handling:
- If the response is not OK (4xx, 5xx), the function still tries to parse JSON and returns error: null. The error field is never populated. Need to check response.ok.
- response.json() can throw if the response is not valid JSON. No try-catch.

4. updateUser type safety:
- Partial<User> allows updating the `id` field, which should typically be immutable. Should use Omit or a specific update type:
```typescript
type UserUpdate = Partial<Omit<User, 'id'>>;
```

5. EventBus is not type-safe:
- Any string can be used as an event name. Any data type can be passed. No compile-time checking that the correct data type is emitted for a given event. Could use a typed event map:
```typescript
interface EventMap {
  'user:login': { userId: number };
  'user:logout': void;
}
class TypedEventBus<T extends Record<string, any>> {
  on<K extends keyof T>(event: K, handler: (data: T[K]) => void): void;
}
```

6. processItems is just Array.map:
- The function reimplements Array.prototype.map with a for loop. Should just use map.

7. Config shallow merge:
- `{ ...defaults, ...overrides }` does a shallow merge. If overrides has `features: { newFeature: true }`, it replaces the entire features object instead of merging with default features. Nested objects need deep merge.

8. Index signatures vs Record:
- `{ [key: string]: boolean }` is equivalent to `Record<string, boolean>`. The Record utility type is more idiomatic.

Let me write the review.
</think>

## Code Review: TypeScript Type Safety

### HIGH - Pervasive `any` Usage

**ANY1: User.settings typed as any (Severity: HIGH)**
```typescript
settings: any;
```
`any` disables all type checking. Code like `user.settings.nonExistent.deep.path` compiles without error but crashes at runtime. Define a proper interface:
```typescript
interface UserSettings {
  theme: 'light' | 'dark';
  notifications: boolean;
  language: string;
}
interface User {
  settings: UserSettings;
}
```

**ANY2: metadata typed as object (Severity: HIGH)**
`object` type means "any non-primitive" -- you cannot access any properties without unsafe casting. Use `Record<string, unknown>` or a specific interface.

**ANY3: EventHandler and EventBus lose all type info (Severity: HIGH)**
`EventHandler = (event: any) => void` and `emit(event: string, data?: any)` mean the event bus has zero type safety. Wrong event names and wrong data types are not caught. Use a typed event map pattern:
```typescript
interface Events {
  'user:created': { id: number; name: string };
  'order:placed': { orderId: number; total: number };
}

class TypedEventBus<T extends Record<string, unknown>> {
  on<K extends keyof T>(event: K, handler: (data: T[K]) => void): void { ... }
  emit<K extends keyof T>(event: K, data: T[K]): void { ... }
}

const bus = new TypedEventBus<Events>();
bus.emit('user:created', { id: 1, name: 'Alice' }); // type-checked
bus.emit('user:created', { wrong: true }); // compile error
```

### HIGH - String Role Without Union Type

**RL1: Role as plain string (Severity: HIGH)**
```typescript
role: string;
// ...
user.role === 'admin' || user.role === 'superadmin' || user.role === 'root'
```
A typo like `user.role === 'amdin'` compiles without error. Use a union type:
```typescript
type UserRole = 'admin' | 'superadmin' | 'root' | 'user' | 'viewer';
interface User {
  role: UserRole;
}
```
Then `isAdmin` can use a Set for cleaner checking:
```typescript
const ADMIN_ROLES: ReadonlySet<UserRole> = new Set(['admin', 'superadmin', 'root']);
function isAdmin(user: User): boolean {
  return ADMIN_ROLES.has(user.role);
}
```

### HIGH - fetchUser Ignores Errors

**FE1: Error response treated as success (Severity: HIGH)**
```typescript
async function fetchUser(id: number): Promise<ApiResponse<User>> {
  const response = await fetch(`/api/users/${id}`);
  const data = await response.json();
  return { data, error: null, status: response.status };
}
```
If the response is 404 or 500, `error` is still null and `data` contains the error body (not a User). Check response.ok:
```typescript
if (!response.ok) {
  return { data: null as any, error: `HTTP ${response.status}`, status: response.status };
}
```
Better: use a discriminated union for the return type:
```typescript
type ApiResult<T> =
  | { ok: true; data: T; status: number }
  | { ok: false; error: string; status: number };
```

### MEDIUM - updateUser Allows ID Change

**UP1: Partial<User> includes id (Severity: MEDIUM)**
```typescript
function updateUser(user: User, updates: Partial<User>): User {
  return { ...user, ...updates };
}
// This compiles: updateUser(user, { id: 999 })
```
Use Omit to prevent id changes:
```typescript
type UserUpdate = Partial<Omit<User, 'id'>>;
```

### MEDIUM - Shallow Config Merge

**CM1: Nested objects overwritten instead of merged (Severity: MEDIUM)**
```typescript
return { ...defaults, ...overrides };
```
If `overrides = { features: { darkMode: true } }`, the default features are completely replaced. Use deep merge for nested properties.

### LOW - Redundant processItems

**PI1: Reimplements Array.map (Severity: LOW)**
`processItems` is functionally identical to `items.map(processor)`. Remove it and use the built-in method.'''),

    ("thinking/code-review", r'''Review this TypeScript code and identify issues:

```typescript
type Status = 'pending' | 'active' | 'suspended' | 'deleted';

type BaseEntity = {
  id: string;
  createdAt: Date;
  updatedAt: Date;
};

type Product = BaseEntity & {
  name: string;
  price: number;
  status: Status;
  variants: ProductVariant[];
};

type ProductVariant = {
  id: string;
  sku: string;
  size: string;
  color: string;
  stock: number;
  price?: number;
};

type CreateProductDTO = Omit<Product, 'id' | 'createdAt' | 'updatedAt'>;
type UpdateProductDTO = Partial<CreateProductDTO>;

type FilterOperator = 'eq' | 'neq' | 'gt' | 'gte' | 'lt' | 'lte' | 'contains' | 'in';

type Filter<T> = {
  field: keyof T;
  operator: FilterOperator;
  value: any;
};

type QueryOptions<T> = {
  filters?: Filter<T>[];
  sort?: { field: keyof T; direction: 'asc' | 'desc' };
  pagination?: { page: number; pageSize: number };
};

class Repository<T extends BaseEntity> {
  private items: T[] = [];

  async findAll(options?: QueryOptions<T>): Promise<T[]> {
    let result = [...this.items];

    if (options?.filters) {
      for (const filter of options.filters) {
        result = result.filter(item => {
          const value = item[filter.field];
          switch (filter.operator) {
            case 'eq': return value === filter.value;
            case 'neq': return value !== filter.value;
            case 'gt': return value > filter.value;
            case 'gte': return value >= filter.value;
            case 'lt': return value < filter.value;
            case 'lte': return value <= filter.value;
            case 'contains': return String(value).includes(filter.value);
            case 'in': return filter.value.includes(value);
          }
        });
      }
    }

    if (options?.sort) {
      result.sort((a, b) => {
        const aVal = a[options.sort!.field];
        const bVal = b[options.sort!.field];
        const dir = options.sort!.direction === 'asc' ? 1 : -1;
        return aVal > bVal ? dir : aVal < bVal ? -dir : 0;
      });
    }

    if (options?.pagination) {
      const { page, pageSize } = options.pagination;
      result = result.slice((page - 1) * pageSize, page * pageSize);
    }

    return result;
  }

  async findById(id: string): Promise<T | undefined> {
    return this.items.find(item => item.id === id);
  }

  async create(data: Omit<T, keyof BaseEntity>): Promise<T> {
    const entity = {
      ...data,
      id: crypto.randomUUID(),
      createdAt: new Date(),
      updatedAt: new Date(),
    } as T;
    this.items.push(entity);
    return entity;
  }

  async update(id: string, data: Partial<T>): Promise<T | undefined> {
    const index = this.items.findIndex(item => item.id === id);
    if (index === -1) return undefined;
    this.items[index] = { ...this.items[index], ...data, updatedAt: new Date() };
    return this.items[index];
  }

  async delete(id: string): Promise<boolean> {
    const index = this.items.findIndex(item => item.id === id);
    if (index === -1) return false;
    this.items.splice(index, 1);
    return true;
  }
}
```''', r'''<think>
Let me review this TypeScript code for type safety, generic usage, and design issues.

1. Filter type safety:
- `Filter<T>` has `value: any`. This means you can filter a numeric field with a string value, or use 'contains' on a Date. No type safety between the field, operator, and value.
- Ideally, the value type should depend on the field type and operator. This requires conditional types or discriminated unions, which are complex.

2. Generic constraints:
- `Repository<T extends BaseEntity>` is good. But `create(data: Omit<T, keyof BaseEntity>)` -- the `as T` cast is unsafe. The spread `{...data, id: ..., createdAt: ..., updatedAt: ...}` creates a plain object that may not satisfy T if T has methods or specific prototype.

3. UpdateProductDTO:
- `Partial<CreateProductDTO>` makes every field optional, including nested `variants`. But you probably cannot partially update a variant -- you need to replace the whole array. The Partial<> nesting is shallow, so variants would be `ProductVariant[] | undefined`, not `Partial<ProductVariant>[]`.

4. QueryOptions and sorting:
- The sort options use `options.sort!.field` with non-null assertion. While the `if (options?.sort)` check ensures it exists, the non-null assertion inside the sort callback is necessary because TypeScript cannot narrow inside callback closures. This is correct but fragile.

5. In-memory repository:
- This is an in-memory implementation. In a real application, the filter/sort/pagination logic would be done by the database. This pattern is useful for testing but should not be used in production.
- The items array is not thread-safe (not relevant in JS, but relevant if used in a worker context).

6. Delete implementation:
- splice mutates the array. If anyone holds a reference to the items array (e.g., a previous findAll result holds references to the same objects), deleting does not affect those references. This is fine for the delete use case.

7. Comparison operators:
- `value > filter.value` works for numbers and strings (lexicographic) but not for Dates (which need getTime() comparison). The generic approach does not handle type-specific comparisons.

8. Missing features:
- No count method for pagination (total count needed for UI).
- findById returns undefined instead of throwing. This is fine but callers must check.

Let me write the review.
</think>

## Code Review: TypeScript Generic Repository

### HIGH - Filter Value Not Type-Safe

**FV1: any type in Filter defeats type checking (Severity: HIGH)**
```typescript
type Filter<T> = {
  field: keyof T;
  operator: FilterOperator;
  value: any;  // no type safety
};
```
You can filter a numeric field with a string value or use 'contains' on a Date without any compile-time error. While fully type-safe filters are complex, you can improve significantly:
```typescript
type Filter<T> = {
  [K in keyof T]: {
    field: K;
    operator: FilterOperator;
    value: T[K] | T[K][];
  };
}[keyof T];
```
This ensures the value type matches the field type. For operator-specific constraints, use discriminated unions:
```typescript
type Filter<T> =
  | { field: keyof T; operator: 'eq' | 'neq'; value: T[keyof T] }
  | { field: keyof T; operator: 'gt' | 'lt'; value: number }
  | { field: keyof T; operator: 'contains'; value: string }
  | { field: keyof T; operator: 'in'; value: T[keyof T][] };
```

### HIGH - Unsafe Type Assertion in create()

**TC1: as T cast may produce invalid objects (Severity: HIGH)**
```typescript
const entity = {
  ...data,
  id: crypto.randomUUID(),
  createdAt: new Date(),
  updatedAt: new Date(),
} as T;
```
`as T` tells TypeScript to trust that this object satisfies T. If T has methods, getters, or a specific prototype chain, the spread produces a plain object that is not actually a valid T. This compiles but can fail at runtime. The fundamental issue is that generic `create` cannot construct an arbitrary T from spread.

For a data-only pattern (no methods), this works. Document the constraint:
```typescript
class Repository<T extends BaseEntity & Record<string, unknown>> {
```

### MEDIUM - Date Comparison

**DC1: Comparison operators fail for Dates (Severity: MEDIUM)**
```typescript
case 'gt': return value > filter.value;
```
`Date > Date` does an implicit conversion via `valueOf()` which works. But `Date === Date` checks reference equality, not value equality. Two Date objects representing the same time are not `===`. Use `.getTime()` for reliable comparison:
```typescript
const normalize = (v: unknown) => v instanceof Date ? v.getTime() : v;
case 'eq': return normalize(value) === normalize(filter.value);
```

### MEDIUM - Partial Nesting is Shallow

**PN1: UpdateProductDTO does not deeply partial (Severity: MEDIUM)**
```typescript
type UpdateProductDTO = Partial<CreateProductDTO>;
```
`Partial<>` only makes top-level properties optional. `variants` becomes `ProductVariant[] | undefined` -- you either provide the full array or nothing. For deep partial updates:
```typescript
type DeepPartial<T> = {
  [K in keyof T]?: T[K] extends object ? DeepPartial<T[K]> : T[K];
};
```

### MEDIUM - update Allows id/timestamp Overwrite

**UP1: Partial<T> includes base entity fields (Severity: MEDIUM)**
```typescript
async update(id: string, data: Partial<T>): Promise<T | undefined> {
```
`Partial<T>` includes `id` and `createdAt`. A caller can overwrite the ID or creation timestamp:
```typescript
repo.update('123', { id: '456', createdAt: new Date(0) });
```
Restrict the update type:
```typescript
async update(id: string, data: Partial<Omit<T, keyof BaseEntity>>): Promise<T | undefined> {
```

### LOW - Missing Count Method

**CM1: No total count for pagination (Severity: LOW)**
`findAll` returns a paginated slice but does not report the total count. UI components need the total for page navigation. Add a `count` method or return metadata:
```typescript
type PaginatedResult<T> = {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
};
```'''),

    ("thinking/code-review", r'''Review this TypeScript code and identify issues:

```typescript
enum HttpMethod {
  GET = 'GET',
  POST = 'POST',
  PUT = 'PUT',
  DELETE = 'DELETE',
  PATCH = 'PATCH',
}

interface RequestConfig {
  method: HttpMethod;
  url: string;
  data?: unknown;
  headers?: Record<string, string>;
  params?: Record<string, string | number>;
  timeout?: number;
}

interface Interceptor {
  onRequest?: (config: RequestConfig) => RequestConfig | Promise<RequestConfig>;
  onResponse?: (response: Response) => Response | Promise<Response>;
  onError?: (error: Error) => Error | Promise<Error>;
}

class HttpClient {
  private baseUrl: string;
  private defaultHeaders: Record<string, string>;
  private interceptors: Interceptor[] = [];
  private timeout: number;

  constructor(config: { baseUrl: string; headers?: Record<string, string>; timeout?: number }) {
    this.baseUrl = config.baseUrl;
    this.defaultHeaders = config.headers || {};
    this.timeout = config.timeout || 30000;
  }

  addInterceptor(interceptor: Interceptor): void {
    this.interceptors.push(interceptor);
  }

  async get<T>(url: string, params?: Record<string, string | number>): Promise<T> {
    return this.request<T>({ method: HttpMethod.GET, url, params });
  }

  async post<T>(url: string, data?: unknown): Promise<T> {
    return this.request<T>({ method: HttpMethod.POST, url, data });
  }

  async put<T>(url: string, data?: unknown): Promise<T> {
    return this.request<T>({ method: HttpMethod.PUT, url, data });
  }

  async delete<T>(url: string): Promise<T> {
    return this.request<T>({ method: HttpMethod.DELETE, url });
  }

  private async request<T>(config: RequestConfig): Promise<T> {
    let finalConfig = { ...config };

    for (const interceptor of this.interceptors) {
      if (interceptor.onRequest) {
        finalConfig = await interceptor.onRequest(finalConfig);
      }
    }

    const queryString = finalConfig.params
      ? '?' + Object.entries(finalConfig.params).map(([k, v]) => `${k}=${v}`).join('&')
      : '';

    const response = await fetch(`${this.baseUrl}${finalConfig.url}${queryString}`, {
      method: finalConfig.method,
      headers: { ...this.defaultHeaders, ...finalConfig.headers },
      body: finalConfig.data ? JSON.stringify(finalConfig.data) : undefined,
    });

    for (const interceptor of this.interceptors) {
      if (interceptor.onResponse) {
        await interceptor.onResponse(response);
      }
    }

    if (!response.ok) {
      const error = new Error(`HTTP ${response.status}: ${response.statusText}`);
      for (const interceptor of this.interceptors) {
        if (interceptor.onError) {
          await interceptor.onError(error);
        }
      }
      throw error;
    }

    return response.json() as Promise<T>;
  }
}

const api = new HttpClient({
  baseUrl: 'https://api.example.com',
  headers: { 'Content-Type': 'application/json' },
});

api.addInterceptor({
  onRequest: (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers = { ...config.headers, Authorization: `Bearer ${token}` };
    }
    return config;
  },
});
```''', r'''<think>
Let me review this TypeScript HTTP client.

1. Type safety of response:
- `response.json() as Promise<T>` is an unsafe type assertion. The actual JSON response could be anything -- there is no runtime validation that it matches T. This silently succeeds even if the server returns completely different data.

2. Query string encoding:
- `${k}=${v}` does not URL-encode the values. If a parameter value contains `&`, `=`, or special characters, the URL is malformed. Should use `encodeURIComponent`.

3. Timeout not implemented:
- The constructor accepts a `timeout` parameter and stores it, but it is never used in the request method. Requests can hang indefinitely.

4. Response interceptor issues:
- `await interceptor.onResponse(response)` passes the response but ignores the return value. The interceptor cannot modify the response. Should be `response = await interceptor.onResponse(response)`.
- The response body can only be read once. If an interceptor reads the body (e.g., for logging), the main code cannot read it again.
- Error interceptors also ignore the return value.

5. Interceptor mutation:
- The onRequest interceptor mutates the config object directly (`config.headers = { ... }`). Since finalConfig is a shallow copy, this is fine for top-level properties. But if interceptors depend on order or expect the original config, mutation can cause issues.

6. Missing features:
- No request cancellation (AbortController)
- No retry logic
- No request/response type narrowing (all methods return Promise<T> with the same unsafe cast)

7. Response body handling:
- Always calls response.json(). What about non-JSON responses (204 No Content, text responses, binary data)? A 204 response has no body, and response.json() will fail.

8. Error handling:
- Error interceptors are called for HTTP errors but not for network errors (fetch throws). Should wrap the entire fetch in try-catch.

Let me write the review.
</think>

## Code Review: TypeScript HTTP Client

### HIGH - Unsafe Type Assertion on Response

**TA1: response.json() cast to T is unchecked (Severity: HIGH)**
```typescript
return response.json() as Promise<T>;
```
This tells TypeScript to trust that the JSON response matches type T. If the server returns different data (different API version, error format, schema change), the code operates on wrong data with no error. Use a runtime validator:
```typescript
import { z } from 'zod';

async get<T>(url: string, schema: z.ZodType<T>, params?): Promise<T> {
  const json = await response.json();
  return schema.parse(json);  // throws if shape is wrong
}
// Usage:
const UserSchema = z.object({ id: z.number(), name: z.string() });
const user = await api.get('/users/1', UserSchema);
```

### HIGH - Missing URL Encoding

**UE1: Query parameters not encoded (Severity: HIGH)**
```typescript
Object.entries(finalConfig.params).map(([k, v]) => `${k}=${v}`).join('&')
```
Values are interpolated without encoding. A parameter like `{ q: 'hello world&page=1' }` produces `q=hello world&page=1`, corrupting the URL. Use `encodeURIComponent`:
```typescript
Object.entries(params)
  .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
  .join('&')
```
Or use `URLSearchParams`:
```typescript
const queryString = new URLSearchParams(
  Object.entries(params).map(([k, v]) => [k, String(v)])
).toString();
```

### HIGH - Timeout Not Implemented

**TO1: timeout config stored but never used (Severity: HIGH)**
The constructor accepts and stores `timeout` but the fetch call has no AbortController timeout. Requests can hang indefinitely. Implement:
```typescript
const controller = new AbortController();
const timeoutId = setTimeout(() => controller.abort(), finalConfig.timeout || this.timeout);
try {
  const response = await fetch(url, { ...options, signal: controller.signal });
} finally {
  clearTimeout(timeoutId);
}
```

### HIGH - Response Interceptors Broken

**RI1: Return values ignored (Severity: HIGH)**
```typescript
await interceptor.onResponse(response);
```
The return value is discarded. If an interceptor modifies the response (adds headers, transforms body), the changes are lost. Assign the result:
```typescript
for (const interceptor of this.interceptors) {
  if (interceptor.onResponse) {
    response = await interceptor.onResponse(response);
  }
}
```
Same issue exists for onError interceptors.

### MEDIUM - 204 No Content Crashes

**NC1: Always calls response.json() (Severity: MEDIUM)**
A 204 No Content response has no body. `response.json()` throws "Unexpected end of JSON input". Check the status:
```typescript
if (response.status === 204) return undefined as unknown as T;
const contentType = response.headers.get('content-type');
if (contentType?.includes('application/json')) {
  return response.json();
}
```

### MEDIUM - Network Errors Not Intercepted

**NE1: fetch throw not caught (Severity: MEDIUM)**
If the network is down, `fetch` throws a TypeError. Error interceptors are only called for HTTP errors (after a response is received). Wrap the entire request:
```typescript
try {
  const response = await fetch(...);
  // ... process response
} catch (error) {
  for (const interceptor of this.interceptors) {
    if (interceptor.onError) await interceptor.onError(error);
  }
  throw error;
}
```

### LOW - Content-Type Hardcoded

**CT1: JSON Content-Type set for all requests (Severity: LOW)**
`'Content-Type': 'application/json'` is set as a default header. This is wrong for file uploads (multipart/form-data) or GET requests (which should not have a body). Set Content-Type conditionally when a body is present.'''),

    ("thinking/code-review", r'''Review this TypeScript code and identify issues:

```typescript
type Result<T, E = Error> = { ok: true; value: T } | { ok: false; error: E };

function ok<T>(value: T): Result<T, never> {
  return { ok: true, value };
}

function err<E>(error: E): Result<never, E> {
  return { ok: false, error };
}

async function tryCatch<T>(fn: () => Promise<T>): Promise<Result<T>> {
  try {
    return ok(await fn());
  } catch (e) {
    return err(e instanceof Error ? e : new Error(String(e)));
  }
}

type Validator<T> = (value: unknown) => Result<T, string>;

const isString: Validator<string> = (value) =>
  typeof value === 'string' ? ok(value) : err('Expected string');

const isNumber: Validator<number> = (value) =>
  typeof value === 'number' && !isNaN(value) ? ok(value) : err('Expected number');

const isArray = <T>(itemValidator: Validator<T>): Validator<T[]> =>
  (value) => {
    if (!Array.isArray(value)) return err('Expected array');
    const results: T[] = [];
    for (const item of value) {
      const result = itemValidator(item);
      if (!result.ok) return err(`Array item: ${result.error}`);
      results.push(result.value);
    }
    return ok(results);
  };

type Schema<T> = { [K in keyof T]: Validator<T[K]> };

function validate<T>(schema: Schema<T>, data: unknown): Result<T, string[]> {
  if (typeof data !== 'object' || data === null) {
    return err(['Expected object']);
  }
  const result: any = {};
  const errors: string[] = [];

  for (const key in schema) {
    const validator = schema[key];
    const value = (data as any)[key];
    const validation = validator(value);
    if (validation.ok) {
      result[key] = validation.value;
    } else {
      errors.push(`${key}: ${validation.error}`);
    }
  }

  return errors.length > 0 ? err(errors) : ok(result as T);
}

interface UserInput {
  name: string;
  age: number;
  tags: string[];
}

const userSchema: Schema<UserInput> = {
  name: isString,
  age: isNumber,
  tags: isArray(isString),
};

async function processUserInput(rawData: unknown): Promise<Result<UserInput, string[]>> {
  return validate(userSchema, rawData);
}

function pipe<A, B>(fn1: (a: A) => Result<B, string>): (a: A) => Result<B, string>;
function pipe<A, B, C>(fn1: (a: A) => Result<B, string>, fn2: (b: B) => Result<C, string>): (a: A) => Result<C, string>;
function pipe(...fns: Function[]) {
  return (input: any) => {
    let result: Result<any, string> = ok(input);
    for (const fn of fns) {
      if (!result.ok) return result;
      result = fn(result.value);
    }
    return result;
  };
}
```''', r'''<think>
Let me review this TypeScript Result type and validation code.

1. Result type design:
- The Result type is well-designed as a discriminated union. The `ok` field acts as the discriminant. This is a good pattern.
- `ok<T>(value: T): Result<T, never>` and `err<E>(error: E): Result<never, E>` correctly use `never` for the unused type parameter. Good.

2. tryCatch:
- Catches unknown errors and wraps them in Error. But the error type is always `Error`, losing any custom error type information. If a function throws a specific error class (e.g., ValidationError), it is wrapped in a generic Error.

3. Validator issues:
- isNumber rejects NaN which is good, but also accepts Infinity and -Infinity. Depending on the use case, these may be invalid.
- No isBoolean, isDate, isEmail, or other common validators.
- Validators return `Result<T, string>` (single error string). The `validate` function returns `Result<T, string[]>` (array of errors). The error type mismatch is handled by wrapping, but it makes the API inconsistent.

4. validate function:
- Uses `result: any = {}` and `(data as any)[key]` -- these lose type safety inside the validation function itself. While the output is correctly typed via the return, the internal implementation is unsafe.
- Only validates keys present in the schema. Extra keys in data are silently ignored (no strict mode option).
- Does not handle optional fields. Every field in the schema must be present in the data.

5. pipe function:
- The overloads only handle 1-2 functions. For 3+ functions, there is no overload and TypeScript falls back to the implementation signature which uses `any`. To properly type a pipe with N functions, you would need many overloads or conditional types.
- The implementation uses `Function` and `any` everywhere, losing type safety.

6. Schema type:
- `Schema<T> = { [K in keyof T]: Validator<T[K]> }` requires all keys of T. No support for optional properties. If T has `email?: string`, the schema still requires an `email` validator.

7. Missing features:
- No way to compose validators (e.g., isString AND minLength(3))
- No optional field support
- No default values
- No nested object validation (beyond arrays)

These are design limitations rather than bugs. The implementation is largely correct but limited.

Let me write the review.
</think>

## Code Review: TypeScript Result Type and Validation

### MEDIUM - Type Safety Lost Inside validate()

**TS1: Internal any usage in validate (Severity: MEDIUM)**
```typescript
const result: any = {};
const value = (data as any)[key];
```
While the function's return type is correctly typed, the internal implementation uses `any`, bypassing TypeScript's checking. If the validation logic has a bug (wrong key access, incorrect assignment), TypeScript will not catch it. Improve with better internal typing:
```typescript
const record = data as Record<string, unknown>;
const value: unknown = record[key as string];
```

### MEDIUM - No Optional Field Support

**OF1: All schema fields are required (Severity: MEDIUM)**
```typescript
type Schema<T> = { [K in keyof T]: Validator<T[K]> };
```
If `T` has optional properties (e.g., `email?: string`), the schema still requires a validator. There is no way to express "this field may be absent." Add optional support:
```typescript
const optional = <T>(validator: Validator<T>): Validator<T | undefined> =>
  (value) => value === undefined ? ok(undefined) : validator(value);
```

### MEDIUM - Extra Fields Silently Ignored

**EF1: Unknown keys in data not reported (Severity: MEDIUM)**
The validate function iterates schema keys only. Extra keys in the data (e.g., typos like `nmae` instead of `name`) are silently accepted. Add strict mode:
```typescript
const dataKeys = Object.keys(data as object);
const schemaKeys = Object.keys(schema) as string[];
const extraKeys = dataKeys.filter(k => !schemaKeys.includes(k));
if (strict && extraKeys.length > 0) {
  errors.push(`Unknown fields: ${extraKeys.join(', ')}`);
}
```

### MEDIUM - pipe Loses Types Beyond 2 Functions

**PT1: No overload for 3+ argument pipe (Severity: MEDIUM)**
```typescript
function pipe<A, B>(fn1): ...;
function pipe<A, B, C>(fn1, fn2): ...;
function pipe(...fns: Function[]) { // any types
```
With 3 or more validator functions, TypeScript uses the implementation signature which has `Function` and `any`. Add more overloads or use a recursive conditional type approach. For practical use, 5-6 overloads usually suffice:
```typescript
function pipe<A, B, C, D>(
  fn1: (a: A) => Result<B, string>,
  fn2: (b: B) => Result<C, string>,
  fn3: (c: C) => Result<D, string>,
): (a: A) => Result<D, string>;
```

### LOW - isNumber Accepts Infinity

**IN1: Infinity passes numeric validation (Severity: LOW)**
```typescript
typeof value === 'number' && !isNaN(value) ? ok(value) : err('Expected number')
```
`Infinity` and `-Infinity` pass this check. For most data validation, these are invalid. Add `isFinite`:
```typescript
typeof value === 'number' && isFinite(value) ? ok(value) : err('Expected finite number')
```

### LOW - tryCatch Wraps Custom Errors

**CE1: Custom error types lost (Severity: LOW)**
```typescript
return err(e instanceof Error ? e : new Error(String(e)));
```
If a function throws a `ValidationError extends Error`, the Result type is `Result<T, Error>` not `Result<T, ValidationError>`. The specific error class is preserved at runtime but not in the type. Accept a generic error type:
```typescript
async function tryCatch<T, E extends Error = Error>(
  fn: () => Promise<T>,
  errorMapper?: (e: unknown) => E
): Promise<Result<T, E>> {
```

### Good Patterns

The codebase demonstrates several good TypeScript patterns:
- Discriminated union for Result type with proper `never` in constructors
- Generic validators composable with `isArray`
- Schema type that maps object keys to validators
- Short-circuit evaluation in pipe (stops on first error)

These are solid foundations. The main improvements needed are around completeness (optional fields, nested objects, more validators) rather than correctness.'''),

    ("thinking/code-review", r'''Review this TypeScript code and identify issues:

```typescript
declare module 'express' {
  interface Request {
    user?: {
      id: string;
      role: string;
    };
  }
}

type DeepReadonly<T> = {
  readonly [K in keyof T]: T[K] extends object ? DeepReadonly<T[K]> : T[K];
};

type RequireAtLeastOne<T, Keys extends keyof T = keyof T> = Pick<T, Exclude<keyof T, Keys>> &
  { [K in Keys]-?: Required<Pick<T, K>> & Partial<Pick<T, Exclude<Keys, K>>> }[Keys];

type Brand<T, B extends string> = T & { __brand: B };

type UserId = Brand<string, 'UserId'>;
type OrderId = Brand<string, 'OrderId'>;
type Currency = Brand<number, 'Currency'>;

function createUserId(id: string): UserId {
  return id as UserId;
}

function createOrderId(id: string): OrderId {
  return id as OrderId;
}

function createCurrency(amount: number): Currency {
  return Math.round(amount * 100) / 100 as Currency;
}

function getUser(id: UserId): Promise<User> {
  return fetch(`/api/users/${id}`).then(r => r.json());
}

function getOrder(id: OrderId): Promise<Order> {
  return fetch(`/api/orders/${id}`).then(r => r.json());
}

type EventMap = {
  'user:login': { userId: UserId; timestamp: number };
  'user:logout': { userId: UserId };
  'order:created': { orderId: OrderId; total: Currency };
  'order:cancelled': { orderId: OrderId; reason: string };
};

class TypedEmitter<T extends Record<string, unknown>> {
  private listeners: Map<string, Set<Function>> = new Map();

  on<K extends keyof T>(event: K, handler: (data: T[K]) => void): () => void {
    const key = event as string;
    if (!this.listeners.has(key)) {
      this.listeners.set(key, new Set());
    }
    this.listeners.get(key)!.add(handler);
    return () => this.listeners.get(key)?.delete(handler);
  }

  emit<K extends keyof T>(event: K, data: T[K]): void {
    const key = event as string;
    this.listeners.get(key)?.forEach(fn => fn(data));
  }
}

const emitter = new TypedEmitter<EventMap>();
emitter.on('user:login', (data) => {
  console.log(data.userId);
});
```''', r'''<think>
Let me review this TypeScript code for advanced type patterns.

1. Module augmentation:
- The express module augmentation adds `user` to Request. This is a common pattern. However, `role: string` should be a union type for type safety. Also, this augmentation affects ALL express requests in the project -- even routes that do not have auth middleware.

2. DeepReadonly:
- `T[K] extends object` -- this checks if the value extends object. But arrays are objects, functions are objects, Dates are objects. This makes arrays readonly (good) but also tries to make Dates and Functions deeply readonly, which does not work meaningfully.
- Also, `null extends object` is false in strict mode, so null values are handled correctly. But `T[K] extends object` is true for arrays, which then recursively applies DeepReadonly to array elements. This is usually desired but the recursion can be infinite for circular types.

3. RequireAtLeastOne:
- This is a complex utility type. The `-?` removes optionality. The intersection ensures at least one of the specified keys is present. This is a valid but complex pattern. Hard to read and maintain.

4. Branded types:
- UserId and OrderId are branded strings, preventing accidental mixing. This is a good pattern. But:
  - `__brand` is an actual property in the type (though it does not exist at runtime). This can leak into JSON serialization or Object.keys.
  - Actually, branded types only exist in the type system. Since `as UserId` does not add a runtime property, `__brand` never exists on the value. But TypeScript thinks it does, which can be confusing.
  - createCurrency does `Math.round(amount * 100) / 100` -- this has floating point issues. 0.1 + 0.2 = 0.30000000000000004, and Math.round(0.30000000000000004 * 100) / 100 = 0.3. This specific rounding works but the Currency brand suggests precision matters, and using floating point for currency is an antipattern.

5. TypedEmitter:
- Good pattern! Event names and data types are connected. `on('user:login', data => ...)` correctly infers data type.
- The internal Map uses `string` as key and `Function` as handler. This loses type safety internally but is acceptable since the public API is typed.
- The `on` method returns an unsubscribe function. Good pattern.
- `listeners.get(key)!.add(handler)` -- non-null assertion is safe here because the line above sets the key if missing.

6. getUser and getOrder:
- Both functions call `.then(r => r.json())` without checking response.ok or validating the response shape. The return type is Promise<User> but there is no runtime guarantee.

7. Missing runtime validation:
- Brand types like UserId prevent mixing at compile time but not at runtime. `createUserId("")` creates a valid UserId with an empty string. No runtime validation.

Let me write the review.
</think>

## Code Review: TypeScript Advanced Type Patterns

### HIGH - Floating Point Currency

**FP1: Number-based Currency type has precision issues (Severity: HIGH)**
```typescript
type Currency = Brand<number, 'Currency'>;
function createCurrency(amount: number): Currency {
  return Math.round(amount * 100) / 100 as Currency;
}
```
Using floating-point numbers for currency is a well-known antipattern. While the rounding mitigates display issues, arithmetic operations on Currency values accumulate errors:
```typescript
const price = createCurrency(19.99);
const quantity = 3;
price * quantity // 59.97000000000001 -- no longer a valid Currency
```
Store currency as integer cents:
```typescript
type CurrencyInCents = Brand<number, 'CurrencyInCents'>;
function createCurrency(dollars: number): CurrencyInCents {
  return Math.round(dollars * 100) as CurrencyInCents;
}
function toDollars(cents: CurrencyInCents): number {
  return cents / 100;
}
```

### HIGH - No Runtime Validation for Branded Types

**BV1: Brands are compile-time only (Severity: HIGH)**
```typescript
function createUserId(id: string): UserId {
  return id as UserId;
}
```
`createUserId("")` or `createUserId(null as any)` produces a "valid" UserId with no runtime check. Add validation:
```typescript
function createUserId(id: string): UserId {
  if (!id || id.length === 0) throw new Error('Invalid user ID');
  return id as UserId;
}
```

### MEDIUM - DeepReadonly Limitations

**DR1: Applies recursively to non-plain objects (Severity: MEDIUM)**
```typescript
type DeepReadonly<T> = {
  readonly [K in keyof T]: T[K] extends object ? DeepReadonly<T[K]> : T[K];
};
```
`extends object` is true for Arrays, Dates, Maps, Sets, and Functions. DeepReadonly applied to a Date makes its methods "readonly" which is meaningless. Exclude special types:
```typescript
type DeepReadonly<T> = T extends Date | RegExp | Function
  ? T
  : T extends Array<infer U>
    ? ReadonlyArray<DeepReadonly<U>>
    : T extends object
      ? { readonly [K in keyof T]: DeepReadonly<T[K]> }
      : T;
```

### MEDIUM - Module Augmentation Scope

**MA1: Express Request augmentation affects all routes (Severity: MEDIUM)**
```typescript
declare module 'express' {
  interface Request { user?: { id: string; role: string }; }
}
```
Every route handler sees `req.user` as possibly defined, even unauthenticated routes. This can lead to accessing `req.user.id` without checking auth middleware was applied. Consider a separate AuthenticatedRequest type:
```typescript
interface AuthenticatedRequest extends Request {
  user: { id: UserId; role: UserRole };
}
function requireAuth(req: Request): asserts req is AuthenticatedRequest {
  if (!req.user) throw new UnauthorizedError();
}
```

### MEDIUM - Unvalidated API Responses

**AR1: fetch responses unsafely typed (Severity: MEDIUM)**
```typescript
function getUser(id: UserId): Promise<User> {
  return fetch(`/api/users/${id}`).then(r => r.json());
}
```
`r.json()` returns `Promise<any>`, which is silently cast to `Promise<User>`. No response.ok check, no runtime validation. The branded UserId parameter adds false security if the response does not match the User type.

### Good Patterns

Several patterns in this code are well-implemented:
- **Branded types** for UserId/OrderId prevent mixing different ID types at compile time
- **TypedEmitter** connects event names to their data shapes, providing autocomplete and type checking
- **Unsubscribe via return value** from `on()` is cleaner than a separate `off()` method
- **RequireAtLeastOne** utility type is correctly implemented for ensuring partial update DTOs have at least one field'''),
]
