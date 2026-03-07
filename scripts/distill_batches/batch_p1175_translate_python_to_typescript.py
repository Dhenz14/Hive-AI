"""Code translation pairs: Python functions/classes to TypeScript."""

PAIRS = [
    (
        "code-translation/python-to-typescript",
        r'''Convert this Python data validation class to TypeScript:

class UserValidator:
    def __init__(self, min_age=0, max_age=150):
        self.min_age = min_age
        self.max_age = max_age
        self.errors = []

    def validate(self, data):
        self.errors = []
        if not isinstance(data.get("name"), str) or len(data["name"]) < 1:
            self.errors.append("name must be a non-empty string")
        if not isinstance(data.get("email"), str) or "@" not in data["email"]:
            self.errors.append("email must contain @")
        age = data.get("age")
        if not isinstance(age, int) or age < self.min_age or age > self.max_age:
            self.errors.append(f"age must be between {self.min_age} and {self.max_age}")
        return len(self.errors) == 0

    def get_errors(self):
        return self.errors.copy()''',
        r'''<think>
Translating this Python class to TypeScript. Key differences to handle:

1. Python uses duck typing with dict.get() -- in TypeScript I need to define an interface for the input data. The data parameter is a dict with optional keys, so I should use Partial or optional fields.

2. isinstance() checks -- TypeScript uses typeof for primitives. But typeof null === "object" is a gotcha I need to watch for.

3. Python f-strings in error messages -- I'll use template literals in TS.

4. The errors list is typed as string[] in TS. Python's list is untyped by default.

5. data.get("name") returns None if missing in Python. In TS with optional fields, it would be undefined. Both are falsy so the logic translates, but I need to be careful with the "@" in check -- if email is undefined, "undefined".includes("@") is false, which works out.

6. The copy() on errors -- in TS I'll use spread or .slice() to return a shallow copy.

Let me also add proper access modifiers since TypeScript has them.
</think>

```typescript
interface UserData {
  name?: string;
  email?: string;
  age?: number;
}

class UserValidator {
  private minAge: number;
  private maxAge: number;
  private errors: string[];

  constructor(minAge: number = 0, maxAge: number = 150) {
    this.minAge = minAge;
    this.maxAge = maxAge;
    this.errors = [];
  }

  validate(data: UserData): boolean {
    this.errors = [];

    if (typeof data.name !== "string" || data.name.length < 1) {
      this.errors.push("name must be a non-empty string");
    }

    if (typeof data.email !== "string" || !data.email.includes("@")) {
      this.errors.push("email must contain @");
    }

    const age = data.age;
    if (typeof age !== "number" || !Number.isInteger(age)
        || age < this.minAge || age > this.maxAge) {
      this.errors.push(
        `age must be between ${this.minAge} and ${this.maxAge}`
      );
    }

    return this.errors.length === 0;
  }

  getErrors(): string[] {
    return [...this.errors];
  }
}
```

Key differences from the Python version:

- Added a `UserData` interface since TypeScript needs explicit types for the input shape
- `isinstance(x, int)` becomes `typeof x !== "number" || !Number.isInteger(x)` -- Python's `int` check excludes floats, but JS `typeof` returns "number" for both, so we add the `isInteger` guard
- `dict.get("key")` returning `None` maps to optional interface fields returning `undefined`
- Python `list.copy()` becomes spread syntax `[...this.errors]`
- Methods use camelCase per TypeScript convention (getErrors vs get_errors)''',
    ),
    (
        "code-translation/python-to-typescript",
        r'''Translate this Python async HTTP client to TypeScript:

import aiohttp
import asyncio
from typing import Optional

class ApiClient:
    def __init__(self, base_url: str, token: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.session = None

    async def __aenter__(self):
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self.session = aiohttp.ClientSession(headers=headers)
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    async def get(self, path: str) -> dict:
        async with self.session.get(f"{self.base_url}/{path}") as resp:
            resp.raise_for_status()
            return await resp.json()

    async def post(self, path: str, data: dict) -> dict:
        async with self.session.post(f"{self.base_url}/{path}", json=data) as resp:
            resp.raise_for_status()
            return await resp.json()''',
        r'''```typescript
// Using the built-in fetch API (Node 18+ or browser)

interface RequestOptions {
  method: string;
  headers: Record<string, string>;
  body?: string;
}

class ApiClient {
  private baseUrl: string;
  private headers: Record<string, string>;

  constructor(baseUrl: string, token?: string) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.headers = { "Content-Type": "application/json" };
    if (token) {
      this.headers["Authorization"] = `Bearer ${token}`;
    }
  }

  private async request(method: string, path: string, data?: unknown): Promise<unknown> {
    const opts: RequestOptions = {
      method,
      headers: { ...this.headers },
    };
    if (data !== undefined) {
      opts.body = JSON.stringify(data);
    }

    const resp = await fetch(`${this.baseUrl}/${path}`, opts);
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
    }
    return resp.json();
  }

  async get(path: string): Promise<unknown> {
    return this.request("GET", path);
  }

  async post(path: string, data: Record<string, unknown>): Promise<unknown> {
    return this.request("POST", path, data);
  }

  // No close() needed -- fetch does not use persistent sessions
  // For connection pooling in Node, use an Agent with keepAlive
}

// Usage:
// const client = new ApiClient("https://api.example.com", "my-token");
// const users = await client.get("users");
// const created = await client.post("users", { name: "Alice" });
```

Notable translation differences:

- Python's `async with` context manager pattern has no direct TS equivalent. The fetch API is stateless so no session lifecycle is needed
- `aiohttp.ClientSession` manages connection pooling; fetch handles this internally in Node 18+
- `raise_for_status()` becomes a manual `resp.ok` check -- fetch does not throw on HTTP error codes
- Return types use `unknown` instead of `dict` since TypeScript has no built-in dict type for JSON. You could narrow these with generics if desired''',
    ),
    (
        "code-translation/python-to-typescript",
        r'''Convert this Python decorator-based caching to TypeScript:

import time
from functools import wraps

def cache(ttl_seconds=60):
    def decorator(func):
        store = {}
        @wraps(func)
        def wrapper(*args):
            key = str(args)
            now = time.time()
            if key in store:
                value, timestamp = store[key]
                if now - timestamp < ttl_seconds:
                    return value
            result = func(*args)
            store[key] = (result, now)
            return result
        return wrapper
    return decorator

@cache(ttl_seconds=30)
def fetch_user(user_id):
    print(f"Fetching user {user_id} from DB")
    return {"id": user_id, "name": "Alice"}''',
        r'''<think>
Python decorators with arguments are a common pattern but TypeScript doesn't have decorator support in the same way. Well, TypeScript has experimental decorators for class methods, but they're different from Python's function decorator pattern.

The cleanest translation is to use a higher-order function. The cache store uses str(args) as the key -- in TypeScript I can use JSON.stringify for the same effect.

One gotcha: Python's time.time() returns seconds, while Date.now() returns milliseconds. I need to adjust the TTL comparison accordingly.

Another consideration: Python's *args captures all positional arguments. In TypeScript, I'll use rest parameters with ...args: unknown[].

The functools.wraps decorator preserves the function name and docstring -- there's no direct TS equivalent, but it's not critical for functionality.

Should I use the experimental TS decorator syntax? No -- it only works on class methods and has different semantics. A plain HOF is more idiomatic and portable.
</think>

```typescript
function cache<T>(ttlSeconds: number = 60) {
  return function (fn: (...args: unknown[]) => T): (...args: unknown[]) => T {
    const store = new Map<string, { value: T; timestamp: number }>();

    return function (...args: unknown[]): T {
      const key = JSON.stringify(args);
      const now = Date.now();

      const cached = store.get(key);
      if (cached && now - cached.timestamp < ttlSeconds * 1000) {
        return cached.value;
      }

      const result = fn(...args);
      store.set(key, { value: result, timestamp: now });
      return result;
    };
  };
}

// Usage -- no @ syntax, just wrap the function
const fetchUser = cache<Record<string, unknown>>(30)(
  function fetchUser(userId: unknown): Record<string, unknown> {
    console.log(`Fetching user ${userId} from DB`);
    return { id: userId, name: "Alice" };
  }
);

// fetchUser(1); -- hits "DB"
// fetchUser(1); -- returns cached (within 30s)
```

Key differences:

- Python `@decorator` syntax has no function-level equivalent in TS -- we use a higher-order function call instead
- `time.time()` returns seconds; `Date.now()` returns milliseconds, so we multiply ttlSeconds by 1000
- `str(args)` becomes `JSON.stringify(args)` for cache key serialization
- Used `Map` instead of a plain object for the cache store -- Map handles arbitrary string keys better and has O(1) `.get()` / `.set()`
- Generic `<T>` preserves the return type through the wrapper''',
    ),
    (
        "code-translation/python-to-typescript",
        r'''Translate this Python generator pipeline to TypeScript:

def read_lines(filename):
    with open(filename) as f:
        for line in f:
            yield line.strip()

def filter_nonempty(lines):
    for line in lines:
        if line:
            yield line

def parse_csv_row(lines):
    for line in lines:
        yield line.split(",")

def process_file(filename):
    lines = read_lines(filename)
    nonempty = filter_nonempty(lines)
    rows = parse_csv_row(nonempty)
    for row in rows:
        print(row)''',
        r'''```typescript
import { createReadStream } from "fs";
import { createInterface } from "readline";

// TypeScript generator functions use function* syntax just like Python
function* filterNonempty(lines: Iterable<string>): Generator<string> {
  for (const line of lines) {
    if (line.trim()) {
      yield line;
    }
  }
}

function* parseCsvRow(lines: Iterable<string>): Generator<string[]> {
  for (const line of lines) {
    yield line.split(",");
  }
}

// File reading in Node is async, so we need an async generator
async function* readLines(filename: string): AsyncGenerator<string> {
  const rl = createInterface({
    input: createReadStream(filename),
    crlfDelay: Infinity,
  });
  for await (const line of rl) {
    yield line.trim();
  }
}

// The pipeline must be async because readLines is async
async function processFile(filename: string): Promise<void> {
  const lines = readLines(filename);

  // Cannot mix sync generators with async source directly,
  // so we inline the pipeline using for-await
  for await (const line of lines) {
    if (!line.trim()) continue;
    const row = line.split(",");
    console.log(row);
  }
}

// processFile("data.csv");
```

Key differences from Python:

- Python's `open()` with `for line in f` is synchronous; Node file reading is inherently async, so `readLines` becomes an `async function*` returning `AsyncGenerator`
- Once the source is async, the whole pipeline must use `for await` instead of plain `for...of`, so the clean composable pipeline pattern breaks down somewhat
- Python generators compose trivially; in TS, mixing sync `Generator` with `AsyncGenerator` requires care -- you cannot pass an AsyncGenerator to a function expecting `Iterable`
- An alternative approach would be Node streams with `.pipe()` or a library like `rxjs`, but generators are the closest match to the Python pattern''',
    ),
    (
        "code-translation/python-to-typescript",
        r'''Convert this Python dataclass with validation to TypeScript:

from dataclasses import dataclass, field
from typing import List
from datetime import datetime

@dataclass
class Task:
    title: str
    description: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    completed: bool = False

    def __post_init__(self):
        if len(self.title) < 1:
            raise ValueError("title cannot be empty")
        if len(self.title) > 200:
            raise ValueError("title too long (max 200 chars)")
        self.tags = [t.lower().strip() for t in self.tags]

    def mark_complete(self):
        self.completed = True

    def add_tag(self, tag: str):
        normalized = tag.lower().strip()
        if normalized and normalized not in self.tags:
            self.tags.append(normalized)''',
        r'''<think>
Python dataclasses auto-generate __init__, __repr__, __eq__ from field declarations. TypeScript has no direct equivalent, but a plain class with a constructor does the same job.

Key translation decisions:

1. default_factory=list -> I need to create a new array in the constructor, not share a reference. Same footgun as the Python mutable default.

2. datetime -> Date in JavaScript/TypeScript.

3. __post_init__ validation -> runs in constructor after field assignment. I'll put validation at the end of the constructor.

4. List[str] -> string[] in TypeScript.

5. The list comprehension for tag normalization -> I'll use .map() which is idiomatic TS/JS.

I could also use a library like zod or class-validator, but the user probably wants a plain TypeScript translation without extra deps.
</think>

```typescript
class Task {
  title: string;
  description: string;
  tags: string[];
  createdAt: Date;
  completed: boolean;

  constructor(params: {
    title: string;
    description?: string;
    tags?: string[];
    createdAt?: Date;
    completed?: boolean;
  }) {
    this.title = params.title;
    this.description = params.description ?? "";
    this.tags = (params.tags ?? []).map((t) => t.toLowerCase().trim());
    this.createdAt = params.createdAt ?? new Date();
    this.completed = params.completed ?? false;

    // Validation (mirrors __post_init__)
    if (this.title.length < 1) {
      throw new Error("title cannot be empty");
    }
    if (this.title.length > 200) {
      throw new Error("title too long (max 200 chars)");
    }
  }

  markComplete(): void {
    this.completed = true;
  }

  addTag(tag: string): void {
    const normalized = tag.toLowerCase().trim();
    if (normalized && !this.tags.includes(normalized)) {
      this.tags.push(normalized);
    }
  }
}

// Usage:
// const task = new Task({ title: "Fix bug", tags: ["URGENT", " Backend "] });
// task.tags --> ["urgent", "backend"]
// task.addTag("urgent"); --> no duplicate added
```

Translation notes:

- Dataclass field declarations with defaults become a constructor params object with optional fields and `??` fallback values
- `default_factory=list` becomes `params.tags ?? []` -- each instance gets its own array, avoiding shared-reference bugs
- `__post_init__` validation moves into the constructor body after field assignment
- Python `ValueError` becomes `Error` in TypeScript (or you could define a custom ValidationError)
- `not in self.tags` becomes `!this.tags.includes(normalized)` -- O(n) in both languages for arrays''',
    ),
]
