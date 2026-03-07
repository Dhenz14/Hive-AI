"""
Batch P1212 -- TypeScript fullstack: tRPC, Zod schemas shared
client/server, type-safe API routes, Prisma typed queries.
Target: JS/TS rebalancing. 2 thinking + 3 direct pairs.
"""

pairs = [
    # --- 1. thinking: tRPC setup ---
    {
        "instruction": r'''How do I set up tRPC for end-to-end type safety between a React frontend and Node.js backend? Show router definition, client setup, and usage.''',
        "output": r'''<think>
tRPC gives type-safe API calls without code generation. TypeScript infers
types from the router definition. The key is exporting the AppRouter type
and using it in the client. I will use tRPC v11 with React Query
integration, showing a user CRUD with auth middleware.
</think>

tRPC infers client types from the server router -- no codegen needed:

```typescript
// server/trpc.ts
import { initTRPC, TRPCError } from "@trpc/server";
import { z } from "zod";

interface Context { userId: string | null; }

const t = initTRPC.context<Context>().create();

const isAuthed = t.middleware(({ ctx, next }) => {
  if (!ctx.userId) throw new TRPCError({ code: "UNAUTHORIZED" });
  return next({ ctx: { ...ctx, userId: ctx.userId } });
});

export const router = t.router;
export const publicProcedure = t.procedure;
export const protectedProcedure = t.procedure.use(isAuthed);

// server/routers/user.ts
const userRouter = router({
  list: publicProcedure
    .input(z.object({ page: z.number().positive().default(1) }))
    .query(async ({ input }) => {
      return [{ id: "1", name: "Alice", email: "a@b.com" }];
    }),

  create: protectedProcedure
    .input(z.object({ name: z.string().min(1), email: z.string().email() }))
    .mutation(async ({ input }) => {
      return { id: crypto.randomUUID(), ...input };
    }),
});

// server/root.ts
export const appRouter = router({ user: userRouter });
export type AppRouter = typeof appRouter;

// client/trpc.ts
import { createTRPCReact } from "@trpc/react-query";
import type { AppRouter } from "../server/root";
export const trpc = createTRPCReact<AppRouter>();

// client/UserList.tsx
function UserList() {
  const { data } = trpc.user.list.useQuery({ page: 1 });
  const utils = trpc.useUtils();
  const create = trpc.user.create.useMutation({
    onSuccess: () => utils.user.list.invalidate(),
  });
  return (
    <div>
      {data?.map((u) => <div key={u.id}>{u.name}</div>)}
      <button onClick={() => create.mutate({ name: "New", email: "n@t.com" })}>Add</button>
    </div>
  );
}
```

TypeScript follows the type chain from `AppRouter` through the router. Zero runtime overhead -- all erased at compile time.'''
    },

    # --- 2. direct: shared Zod schemas ---
    {
        "instruction": r'''How do I share Zod validation schemas between client and server in a TypeScript monorepo for consistent validation?''',
        "output": r'''Put shared schemas in a package both apps import. Zod defines validation and types in one place:

```typescript
// packages/shared/src/schemas/user.ts
import { z } from "zod";

export const CreateUserSchema = z.object({
  name: z.string().min(1, "Required").max(100),
  email: z.string().email("Invalid email"),
  role: z.enum(["admin", "user", "moderator"]),
});

export const UpdateUserSchema = CreateUserSchema.partial().extend({
  id: z.string().uuid(),
});

export type CreateUser = z.infer<typeof CreateUserSchema>;
export type UpdateUser = z.infer<typeof UpdateUserSchema>;

// Server usage (apps/api)
import { CreateUserSchema } from "@myapp/shared";

app.post("/api/users", async (req, res) => {
  const result = CreateUserSchema.safeParse(req.body);
  if (!result.success) {
    return res.status(400).json({ errors: result.error.flatten() });
  }
  // result.data is typed as CreateUser
  res.json({ id: crypto.randomUUID(), ...result.data });
});

// Client usage (apps/web)
import { CreateUserSchema, type CreateUser } from "@myapp/shared";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

function UserForm({ onSubmit }: { onSubmit: (d: CreateUser) => void }) {
  const form = useForm<CreateUser>({
    resolver: zodResolver(CreateUserSchema),
    defaultValues: { role: "user" },
  });
  return (
    <form onSubmit={form.handleSubmit(onSubmit)}>
      <input {...form.register("name")} />
      {form.formState.errors.name && <span>{form.formState.errors.name.message}</span>}
      <button type="submit">Create</button>
    </form>
  );
}
```

Identical validation on both sides. Change the schema and TypeScript catches all broken references at compile time.'''
    },

    # --- 3. direct: Prisma typed queries ---
    {
        "instruction": r'''Show how Prisma provides type-safe database queries in TypeScript and how to handle relations and transactions.''',
        "output": r'''Prisma generates TypeScript types from your schema. Every query is fully typed:

```typescript
import { PrismaClient } from "@prisma/client";
const prisma = new PrismaClient();

// Basic CRUD -- return type is User
async function createUser(email: string, name: string) {
  return prisma.user.create({ data: { email, name } });
}

// Relations with include -- return type includes Post[]
async function getUserWithPosts(id: string) {
  return prisma.user.findUnique({
    where: { id },
    include: {
      posts: { where: { published: true }, orderBy: { createdAt: "desc" }, take: 10 },
    },
  });
}

// Select narrows the return type automatically
async function getEmails() {
  // Return type: { email: string }[]
  return prisma.user.findMany({ select: { email: true } });
}

// Transactions -- atomic operations
async function transferPost(postId: string, newAuthorId: string) {
  return prisma.$transaction(async (tx) => {
    const post = await tx.post.findUniqueOrThrow({ where: { id: postId } });
    await tx.post.update({
      where: { id: postId },
      data: { authorId: newAuthorId },
    });
  });
}

// Type-safe filters
import { Prisma } from "@prisma/client";
async function search(filters: Prisma.UserWhereInput) {
  return prisma.user.findMany({ where: filters });
}

const users = await search({
  OR: [
    { email: { contains: "example.com" } },
    { name: { startsWith: "A" } },
  ],
  posts: { some: { published: true } },
});
```

Run `npx prisma generate` after schema changes. All type errors surface at compile time.'''
    },

    # --- 4. thinking: type-safe API contract ---
    {
        "instruction": r'''How do I build a fully type-safe REST API in TypeScript where the client knows all endpoint types without code generation?''',
        "output": r'''<think>
Define an API contract as a TypeScript type mapping HTTP method + path
to request/response types. Build a thin typed client that infers shapes
from this map. No codegen -- just TypeScript inference. The contract is
shared between client and server as a type-only import.
</think>

Define a contract type, then build a client that infers types from it:

```typescript
// shared/contract.ts
import { z } from "zod";

const endpoints = {
  "GET /users": {
    query: z.object({ page: z.number().optional() }),
    response: z.array(z.object({ id: z.string(), name: z.string() })),
  },
  "POST /users": {
    body: z.object({ name: z.string(), email: z.string() }),
    response: z.object({ id: z.string(), name: z.string() }),
  },
  "GET /users/:id": {
    params: z.object({ id: z.string() }),
    response: z.object({ id: z.string(), name: z.string() }),
  },
} as const;

type Endpoints = typeof endpoints;
type EndpointKey = keyof Endpoints;
type InferResponse<K extends EndpointKey> = z.infer<Endpoints[K]["response"]>;

// client/api.ts
class ApiClient {
  constructor(private base: string) {}

  async request<K extends EndpointKey>(
    endpoint: K,
    opts?: { params?: Record<string, string>; query?: Record<string, unknown>; body?: unknown }
  ): Promise<InferResponse<K>> {
    const [method, pathTpl] = (endpoint as string).split(" ");
    let path = pathTpl;
    if (opts?.params) {
      for (const [k, v] of Object.entries(opts.params)) {
        path = path.replace(`:${k}`, encodeURIComponent(v));
      }
    }
    let url = `${this.base}${path}`;
    if (opts?.query) {
      const qs = new URLSearchParams();
      for (const [k, v] of Object.entries(opts.query)) {
        if (v !== undefined) qs.set(k, String(v));
      }
      url += `?${qs}`;
    }
    const res = await fetch(url, {
      method,
      headers: opts?.body ? { "Content-Type": "application/json" } : {},
      body: opts?.body ? JSON.stringify(opts.body) : undefined,
    });
    if (!res.ok) throw new Error(`API ${res.status}`);
    return res.json();
  }
}

const api = new ApiClient("http://localhost:3000/api");
const users = await api.request("GET /users", { query: { page: 1 } });
// users is typed as { id: string; name: string }[]
```

The contract is shared as a type-only import -- zero runtime code generation.'''
    },

    # --- 5. direct: type-safe env vars ---
    {
        "instruction": r'''How do I handle environment variables in a type-safe way in TypeScript so missing variables are caught at startup, not at runtime?''',
        "output": r'''Validate env vars at startup with Zod. Crash immediately on missing/invalid values:

```typescript
// src/env.ts
import { z } from "zod";

const envSchema = z.object({
  NODE_ENV: z.enum(["development", "production", "test"]),
  DATABASE_URL: z.string().url(),
  JWT_SECRET: z.string().min(32, "Must be 32+ chars"),
  PORT: z.coerce.number().int().positive().default(3000),
  LOG_LEVEL: z.enum(["debug", "info", "warn", "error"]).default("info"),
  REDIS_URL: z.string().url().optional(),
});

const parsed = envSchema.safeParse(process.env);

if (!parsed.success) {
  console.error("Invalid environment variables:");
  for (const [key, errors] of Object.entries(parsed.error.flatten().fieldErrors)) {
    console.error(`  ${key}: ${errors?.join(", ")}`);
  }
  process.exit(1);
}

export const env = parsed.data;
// Type: {
//   NODE_ENV: "development" | "production" | "test";
//   DATABASE_URL: string;
//   JWT_SECRET: string;
//   PORT: number;
//   LOG_LEVEL: "debug" | "info" | "warn" | "error";
//   REDIS_URL?: string;
// }

// Usage everywhere
import { env } from "./env";
app.listen(env.PORT); // number, not string
console.log(`Mode: ${env.NODE_ENV}`); // typed literal union
```

Import `env` instead of `process.env` directly. The app crashes on startup if anything is missing, not at an unpredictable point during runtime.'''
    },
]
