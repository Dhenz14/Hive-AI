"""Modern databases 2026 — Drizzle ORM, Neon serverless Postgres, and Deno 2."""

PAIRS = [
    (
        "databases/drizzle-orm",
        "Show Drizzle ORM patterns: schema definition, type-safe queries, migrations, and relations.",
        """Drizzle ORM patterns (TypeScript):

```typescript
// --- Schema definition (schema.ts) ---

import {
  pgTable, serial, text, varchar, integer, boolean,
  timestamp, uuid, pgEnum, index, uniqueIndex,
  primaryKey,
} from "drizzle-orm/pg-core";
import { relations } from "drizzle-orm";
import { createInsertSchema, createSelectSchema } from "drizzle-zod";

// Enum
export const roleEnum = pgEnum("role", ["user", "admin", "moderator"]);

// Users table
export const users = pgTable("users", {
  id: uuid("id").primaryKey().defaultRandom(),
  email: varchar("email", { length: 255 }).notNull().unique(),
  name: varchar("name", { length: 100 }).notNull(),
  role: roleEnum("role").default("user").notNull(),
  active: boolean("active").default(true).notNull(),
  createdAt: timestamp("created_at", { withTimezone: true })
    .defaultNow().notNull(),
  updatedAt: timestamp("updated_at", { withTimezone: true })
    .defaultNow().notNull(),
}, (table) => [
  index("users_email_idx").on(table.email),
  index("users_created_idx").on(table.createdAt),
]);

// Posts table
export const posts = pgTable("posts", {
  id: serial("id").primaryKey(),
  title: varchar("title", { length: 255 }).notNull(),
  content: text("content").notNull(),
  published: boolean("published").default(false).notNull(),
  authorId: uuid("author_id").notNull().references(() => users.id, {
    onDelete: "cascade",
  }),
  createdAt: timestamp("created_at", { withTimezone: true })
    .defaultNow().notNull(),
});

// Tags (many-to-many)
export const tags = pgTable("tags", {
  id: serial("id").primaryKey(),
  name: varchar("name", { length: 50 }).notNull().unique(),
});

export const postTags = pgTable("post_tags", {
  postId: integer("post_id").notNull().references(() => posts.id),
  tagId: integer("tag_id").notNull().references(() => tags.id),
}, (table) => [
  primaryKey({ columns: [table.postId, table.tagId] }),
]);


// --- Relations (for query builder) ---

export const usersRelations = relations(users, ({ many }) => ({
  posts: many(posts),
}));

export const postsRelations = relations(posts, ({ one, many }) => ({
  author: one(users, {
    fields: [posts.authorId],
    references: [users.id],
  }),
  tags: many(postTags),
}));


// --- Zod schemas (auto-generated validation) ---

export const insertUserSchema = createInsertSchema(users);
export const selectUserSchema = createSelectSchema(users);


// --- Database client (db.ts) ---

import { drizzle } from "drizzle-orm/node-postgres";
import { Pool } from "pg";
import * as schema from "./schema";

const pool = new Pool({ connectionString: process.env.DATABASE_URL });
export const db = drizzle(pool, { schema });


// --- Type-safe queries ---

import { eq, and, or, like, desc, sql, inArray, count } from "drizzle-orm";

// Select with filter
const activeUsers = await db
  .select()
  .from(users)
  .where(and(
    eq(users.active, true),
    eq(users.role, "admin"),
  ))
  .orderBy(desc(users.createdAt))
  .limit(10);
// Type: { id: string; email: string; name: string; ... }[]

// Select specific columns
const emails = await db
  .select({ email: users.email, name: users.name })
  .from(users)
  .where(like(users.email, "%@company.com"));
// Type: { email: string; name: string }[]

// Join
const postsWithAuthors = await db
  .select({
    postTitle: posts.title,
    authorName: users.name,
    authorEmail: users.email,
  })
  .from(posts)
  .innerJoin(users, eq(posts.authorId, users.id))
  .where(eq(posts.published, true));

// Relational query (like Prisma include)
const usersWithPosts = await db.query.users.findMany({
  with: {
    posts: {
      where: eq(posts.published, true),
      orderBy: desc(posts.createdAt),
      limit: 5,
    },
  },
});

// Aggregation
const stats = await db
  .select({
    role: users.role,
    total: count(),
  })
  .from(users)
  .groupBy(users.role);

// Insert
const [newUser] = await db.insert(users).values({
  email: "alice@example.com",
  name: "Alice",
}).returning();

// Upsert
await db.insert(users).values({
  email: "alice@example.com",
  name: "Alice Updated",
}).onConflictDoUpdate({
  target: users.email,
  set: { name: "Alice Updated", updatedAt: new Date() },
});

// Update
await db.update(users)
  .set({ active: false })
  .where(eq(users.id, userId));

// Delete
await db.delete(posts)
  .where(eq(posts.authorId, userId));

// Transaction
await db.transaction(async (tx) => {
  const [user] = await tx.insert(users).values({ email, name }).returning();
  await tx.insert(posts).values({
    title: "Welcome",
    content: "First post!",
    authorId: user.id,
    published: true,
  });
});
```

```bash
# Migrations
npx drizzle-kit generate   # Generate migration from schema changes
npx drizzle-kit migrate    # Apply pending migrations
npx drizzle-kit push       # Push schema directly (dev only)
npx drizzle-kit studio     # Visual database browser
```

Drizzle ORM patterns:
1. **Schema-as-code** — TypeScript table definitions generate types, migrations, and Zod schemas
2. **Type-safe queries** — `select()`, `where()`, `join()` all fully typed with inference
3. **Relational queries** — `db.query.users.findMany({ with: { posts: true } })` like Prisma
4. **Zero abstraction** — queries map 1:1 to SQL, no magic (SQL-in-TypeScript philosophy)
5. **`drizzle-kit`** — migration generation, push for dev, and visual Studio browser"""
    ),
    (
        "databases/neon-serverless-postgres",
        "Show Neon serverless Postgres patterns: branching, connection pooling, serverless driver, and Edge deployment.",
        """Neon serverless Postgres patterns:

```typescript
// --- Neon serverless driver (HTTP, not TCP) ---
// Works in Edge runtimes (Vercel Edge, Cloudflare Workers, Deno Deploy)
// where TCP connections aren't available

import { neon, neonConfig } from "@neondatabase/serverless";

// HTTP-based queries (stateless, no connection pool needed)
const sql = neon(process.env.DATABASE_URL!);

// Simple query
const users = await sql`SELECT * FROM users WHERE active = true LIMIT 10`;

// Parameterized (safe from SQL injection)
const user = await sql`
  SELECT * FROM users
  WHERE id = ${userId}
  AND email = ${email}
`;

// Transaction over HTTP
const result = await sql.transaction([
  sql`INSERT INTO users (name, email) VALUES (${name}, ${email}) RETURNING id`,
  sql`INSERT INTO audit_log (action, user_email) VALUES ('create', ${email})`,
]);


// --- Connection pooling (for serverless functions) ---

// Option 1: Neon's built-in pooler (recommended for serverless)
// Connection string: postgres://user:pass@ep-xxx.us-east-2.aws.neon.tech/db?sslmode=require
// Pooler string:     postgres://user:pass@ep-xxx-pooler.us-east-2.aws.neon.tech/db?sslmode=require
//                                              ^^^^^^^^ add -pooler

import { Pool } from "@neondatabase/serverless";

// For serverless functions (Lambda, Vercel, etc.)
const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  max: 10,
});

// Use pool in request handler
export async function GET(request: Request) {
  const client = await pool.connect();
  try {
    const { rows } = await client.query("SELECT * FROM users LIMIT 10");
    return Response.json(rows);
  } finally {
    client.release();  // Return to pool (NOT close)
  }
}


// --- Drizzle + Neon ---

import { drizzle } from "drizzle-orm/neon-http";
import { neon } from "@neondatabase/serverless";

const queryClient = neon(process.env.DATABASE_URL!);
const db = drizzle(queryClient);

// Type-safe queries over HTTP
const activeUsers = await db
  .select()
  .from(users)
  .where(eq(users.active, true));


// --- Next.js App Router + Neon ---

// app/api/users/route.ts
import { neon } from "@neondatabase/serverless";

// This runs on Edge runtime — no cold starts!
export const runtime = "edge";

const sql = neon(process.env.DATABASE_URL!);

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const query = searchParams.get("q");

  const users = query
    ? await sql`SELECT * FROM users WHERE name ILIKE ${`%${query}%`} LIMIT 20`
    : await sql`SELECT * FROM users LIMIT 20`;

  return Response.json(users);
}


// --- Branching (database branches like git branches) ---

// Neon CLI
// neon branches create --name feature/auth --parent main
// neon branches list
// neon branches delete feature/auth

// Each branch is a full copy-on-write Postgres database
// Use cases:
//   - Preview deployments: each PR gets its own database branch
//   - Testing: branch → run tests → delete branch
//   - Migrations: test migration on branch before applying to main

// Vercel integration: automatic branch per preview deployment
// vercel.json:
// {
//   "env": {
//     "DATABASE_URL": "@neon_database_url"
//   }
// }

// Neon automatically creates a branch matching the git branch name
// and sets DATABASE_URL for that preview deployment


// --- Autoscaling and scale-to-zero ---

// Neon compute scales automatically:
//   - Scale to zero: no compute charges when idle
//   - Cold start: ~500ms for first query after idle
//   - Auto-scale: 0.25 to 8 vCPU based on load

// For latency-sensitive apps, keep minimum compute:
// neon compute set --min-cu 0.25 --max-cu 4

// For batch jobs, scale up temporarily:
// neon compute set --min-cu 4 --max-cu 8
// ... run batch job ...
// neon compute set --min-cu 0.25 --max-cu 4
```

Neon serverless Postgres patterns:
1. **HTTP driver** — `@neondatabase/serverless` works in Edge runtimes (no TCP needed)
2. **Database branching** — copy-on-write branches for preview deployments and testing
3. **Scale to zero** — no charges when idle, ~500ms cold start on first query
4. **Pooler URL** — add `-pooler` to hostname for connection pooling in serverless
5. **Drizzle integration** — `drizzle-orm/neon-http` for type-safe queries over HTTP"""
    ),
    (
        "runtime/deno-2",
        "Show Deno 2 patterns: Node compatibility, npm imports, permissions, KV storage, and Deploy.",
        """Deno 2 patterns:

```typescript
// --- Deno 2: Node-compatible, secure by default ---
//
// Key changes in Deno 2:
//   - Full Node.js/npm compatibility (most npm packages just work)
//   - package.json support (optional)
//   - node: specifiers (import from "node:fs")
//   - deno.json replaces tsconfig.json
//   - Built-in: TypeScript, formatter, linter, test runner, KV, Cron


// --- deno.json (project config) ---

// {
//   "tasks": {
//     "dev": "deno run --watch --allow-net --allow-read main.ts",
//     "start": "deno run --allow-net --allow-read --allow-env main.ts",
//     "test": "deno test --allow-net",
//     "lint": "deno lint",
//     "fmt": "deno fmt"
//   },
//   "imports": {
//     "@std/http": "jsr:@std/http@1",
//     "@std/path": "jsr:@std/path@1",
//     "hono": "npm:hono@4"
//   },
//   "compilerOptions": {
//     "strict": true,
//     "jsx": "react-jsx",
//     "jsxImportSource": "npm:react"
//   }
// }


// --- HTTP server (std library) ---

import { serveDir } from "@std/http/file-server";

Deno.serve({ port: 8000 }, async (request: Request) => {
  const url = new URL(request.url);

  // API routes
  if (url.pathname.startsWith("/api/")) {
    return handleAPI(request);
  }

  // Static files
  return serveDir(request, { fsRoot: "./public" });
});

async function handleAPI(request: Request): Promise<Response> {
  const url = new URL(request.url);

  if (url.pathname === "/api/users" && request.method === "GET") {
    const users = await getUsers();
    return Response.json(users);
  }

  if (url.pathname === "/api/users" && request.method === "POST") {
    const body = await request.json();
    const user = await createUser(body);
    return Response.json(user, { status: 201 });
  }

  return new Response("Not Found", { status: 404 });
}


// --- npm packages work directly ---

import express from "npm:express@5";
import { PrismaClient } from "npm:@prisma/client";
import chalk from "npm:chalk@5";

// Or with import map in deno.json:
import { Hono } from "hono";  // Mapped to npm:hono@4

const app = new Hono();

app.get("/", (c) => c.text("Hello from Deno 2!"));
app.get("/api/users", async (c) => {
  const users = await db.user.findMany();
  return c.json(users);
});

Deno.serve(app.fetch);


// --- Node.js built-in modules ---

import { readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { createHash } from "node:crypto";

const content = await readFile("data.txt", "utf-8");
const hash = createHash("sha256").update(content).digest("hex");


// --- Deno KV (built-in key-value store) ---

const kv = await Deno.openKv();  // Local SQLite or Deno Deploy's distributed KV

// Set
await kv.set(["users", "user-123"], {
  name: "Alice",
  email: "alice@example.com",
  role: "admin",
});

// Get
const entry = await kv.get<User>(["users", "user-123"]);
if (entry.value) {
  console.log(entry.value.name);  // "Alice"
}

// List by prefix
const iter = kv.list<User>({ prefix: ["users"] });
for await (const entry of iter) {
  console.log(entry.key, entry.value);
}

// Atomic transactions
const result = await kv.atomic()
  .check({ key: ["users", "user-123"], versionstamp: entry.versionstamp })
  .set(["users", "user-123"], { ...entry.value, role: "moderator" })
  .set(["audit", Date.now().toString()], { action: "role_change" })
  .commit();

if (!result.ok) {
  console.log("Conflict — another write happened first");
}

// Expiring keys (TTL)
await kv.set(["sessions", sessionId], sessionData, {
  expireIn: 3600_000, // 1 hour in ms
});


// --- Deno Cron (built-in scheduling) ---

Deno.cron("cleanup expired sessions", "0 * * * *", async () => {
  // Runs every hour
  const iter = kv.list({ prefix: ["sessions"] });
  for await (const entry of iter) {
    if (isExpired(entry.value)) {
      await kv.delete(entry.key);
    }
  }
});

Deno.cron("daily report", "0 6 * * *", async () => {
  const stats = await generateDailyStats();
  await sendReport(stats);
});


// --- Permissions (security by default) ---

// Deno requires explicit permissions:
// deno run --allow-net=api.example.com --allow-read=./data main.ts
//
// Permission flags:
//   --allow-net=host:port   Network access (specific hosts)
//   --allow-read=path       File system read
//   --allow-write=path      File system write
//   --allow-env=VAR         Environment variables
//   --allow-run=cmd         Subprocess execution
//   --allow-ffi             Foreign function interface
//   --allow-all / -A        All permissions (dev only)


// --- Testing (built-in) ---

import { assertEquals, assertRejects } from "@std/assert";

Deno.test("createUser returns user with id", async () => {
  const user = await createUser({ name: "Alice", email: "a@b.com" });
  assertEquals(typeof user.id, "string");
  assertEquals(user.name, "Alice");
});

Deno.test("duplicate email throws", async () => {
  await createUser({ name: "Bob", email: "dup@test.com" });
  await assertRejects(
    () => createUser({ name: "Bob2", email: "dup@test.com" }),
    Error,
    "already exists",
  );
});

// Run: deno test --allow-net --allow-read
```

Deno 2 patterns:
1. **Node compatibility** — `npm:` specifiers and `node:` built-ins work out of the box
2. **Deno KV** — built-in key-value store with atomic transactions and TTL
3. **Deno.cron** — built-in cron scheduling, no external job queue needed
4. **Permissions** — `--allow-net=host`, `--allow-read=path` for security by default
5. **Built-in tooling** — `deno fmt`, `deno lint`, `deno test`, `deno bench` with zero config"""
    ),
]
