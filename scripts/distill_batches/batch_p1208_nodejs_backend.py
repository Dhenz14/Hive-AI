"""
Batch P1208 -- Node.js backend: Express middleware, Fastify plugins,
Node.js streams, worker_threads, cluster module.
Target: JS/TS rebalancing. 2 thinking + 3 direct pairs.
"""

pairs = [
    # --- 1. thinking: Express middleware chain ---
    {
        "instruction": r'''How do I structure Express middleware properly in a production TypeScript app? Show error handling, auth, and request validation middleware.''',
        "output": r'''<think>
Express middleware is the core request processing pattern. I need to cover
typed request augmentation, async error handling (Express 4 does not catch
rejected promises), auth middleware, validation with Zod, and proper
ordering. Error middleware must have exactly 4 parameters.
</think>

Production Express middleware in TypeScript:

```typescript
import express, { Request, Response, NextFunction } from "express";
import { z, ZodSchema } from "zod";

declare module "express" {
  interface Request {
    user?: { id: string; role: "admin" | "user" };
  }
}

// Async wrapper -- Express 4 does not catch promise rejections
const asyncHandler = (fn: (req: Request, res: Response, next: NextFunction) => Promise<void>) =>
  (req: Request, res: Response, next: NextFunction) => fn(req, res, next).catch(next);

// Auth middleware
function authenticate(req: Request, res: Response, next: NextFunction) {
  const token = req.headers.authorization?.replace("Bearer ", "");
  if (!token) { res.status(401).json({ error: "Missing token" }); return; }
  try {
    const payload = JSON.parse(Buffer.from(token.split(".")[1], "base64url").toString());
    req.user = { id: payload.sub, role: payload.role };
    next();
  } catch { res.status(401).json({ error: "Invalid token" }); }
}

// Validation factory
function validate(schema: ZodSchema) {
  return (req: Request, res: Response, next: NextFunction) => {
    const result = schema.safeParse(req.body);
    if (!result.success) {
      res.status(400).json({ error: "Validation failed", details: result.error.flatten() });
      return;
    }
    req.body = result.data;
    next();
  };
}

// Error handler (MUST have 4 params)
function errorHandler(err: Error, _req: Request, res: Response, _next: NextFunction) {
  console.error(err.stack);
  res.status(500).json({ error: "Internal server error" });
}

const app = express();
app.use(express.json());

app.post("/api/users", authenticate, validate(z.object({
  email: z.string().email(), name: z.string().min(1),
})), asyncHandler(async (req, res) => {
  res.status(201).json({ id: crypto.randomUUID(), ...req.body });
}));

app.use(errorHandler); // must be last
```

Middleware runs in registration order. Auth before validation before handlers. Error handler always last.'''
    },

    # --- 2. direct: Fastify plugins ---
    {
        "instruction": r'''Show how to build a Fastify plugin with TypeScript, including typed decorators and encapsulation.''',
        "output": r'''Fastify plugins use encapsulation -- each plugin gets its own context. Use `fastify-plugin` to break encapsulation when sharing decorators:

```typescript
import Fastify, { FastifyPluginAsync } from "fastify";
import fp from "fastify-plugin";

declare module "fastify" {
  interface FastifyInstance {
    db: { query: (sql: string) => Promise<unknown[]> };
  }
}

// DB plugin -- fp() makes decorator visible to siblings
const dbPlugin: FastifyPluginAsync<{ connStr: string }> = async (fastify, opts) => {
  fastify.decorate("db", { query: async (sql: string) => [] });
  fastify.addHook("onClose", async () => console.log("DB pool closed"));
};

const userRoutes: FastifyPluginAsync = async (fastify) => {
  fastify.post<{ Body: { email: string; name: string } }>(
    "/users",
    {
      schema: {
        body: {
          type: "object",
          required: ["email", "name"],
          properties: {
            email: { type: "string", format: "email" },
            name: { type: "string", minLength: 1 },
          },
        },
      },
    },
    async (request) => {
      await fastify.db.query("SELECT 1");
      return { id: crypto.randomUUID(), email: request.body.email };
    }
  );
};

const app = Fastify({ logger: true });
app.register(fp(dbPlugin), { connStr: "postgres://..." });
app.register(userRoutes, { prefix: "/api" });
app.listen({ port: 3000 });
```

Fastify plugins are encapsulated by default. Use `fastify-plugin` only when decorators must be shared across sibling plugins.'''
    },

    # --- 3. direct: Node.js streams ---
    {
        "instruction": r'''Show how to use Node.js streams (Readable, Transform, pipeline) for processing large files without loading them into memory.''',
        "output": r'''Streams process data in chunks. Use `pipeline()` for error handling and backpressure:

```javascript
import { createReadStream, createWriteStream } from "node:fs";
import { pipeline } from "node:stream/promises";
import { Transform } from "node:stream";
import { createGzip } from "node:zlib";

// Transform: CSV lines to JSON
class CsvToJson extends Transform {
  #headers = null;
  #buffer = "";

  constructor() { super({ objectMode: true }); }

  _transform(chunk, encoding, cb) {
    this.#buffer += chunk.toString();
    const lines = this.#buffer.split("\n");
    this.#buffer = lines.pop();
    for (const line of lines) {
      if (!line.trim()) continue;
      const vals = line.split(",").map((v) => v.trim());
      if (!this.#headers) { this.#headers = vals; continue; }
      const obj = {};
      this.#headers.forEach((h, i) => { obj[h] = vals[i]; });
      this.push(JSON.stringify(obj) + "\n");
    }
    cb();
  }

  _flush(cb) {
    if (this.#buffer.trim() && this.#headers) {
      const vals = this.#buffer.split(",").map((v) => v.trim());
      const obj = {};
      this.#headers.forEach((h, i) => { obj[h] = vals[i]; });
      this.push(JSON.stringify(obj) + "\n");
    }
    cb();
  }
}

// Pipeline: CSV -> JSON -> gzip -> file
await pipeline(
  createReadStream("data.csv"),
  new CsvToJson(),
  createGzip(),
  createWriteStream("data.jsonl.gz")
);
```

Always use `pipeline()` (not `.pipe()`) -- it handles errors, destroys streams on failure, and respects backpressure. The `stream/promises` version returns an awaitable promise.'''
    },

    # --- 4. thinking: worker_threads ---
    {
        "instruction": r'''How do I use Node.js worker_threads for CPU-intensive tasks? Show the communication pattern between main thread and workers.''',
        "output": r'''<think>
worker_threads runs JS in parallel OS threads. The main thread stays
responsive while workers handle heavy computation. I should show a
practical worker pool pattern since that is the most common production
use. Communication is via postMessage. Workers cannot access main
thread variables directly.
</think>

`worker_threads` runs JavaScript in parallel threads for CPU-bound work:

```javascript
// === worker.mjs ===
import { parentPort } from "node:worker_threads";
import { createHash } from "node:crypto";

parentPort.on("message", (data) => {
  let hash = data;
  for (let i = 0; i < 100_000; i++) {
    hash = createHash("sha256").update(hash).digest("hex");
  }
  parentPort.postMessage(hash);
});

// === pool.mjs -- reusable worker pool ===
import { Worker } from "node:worker_threads";
import { cpus } from "node:os";

class WorkerPool {
  #workers; #queue = []; #active = new Map();

  constructor(path, size = cpus().length) {
    this.#workers = Array.from({ length: size }, () => {
      const w = new Worker(path);
      w.on("message", (result) => {
        this.#active.get(w)(result);
        this.#active.delete(w);
        this.#drain(w);
      });
      return w;
    });
  }

  exec(data) {
    return new Promise((resolve) => {
      const idle = this.#workers.find((w) => !this.#active.has(w));
      if (idle) { this.#active.set(idle, resolve); idle.postMessage(data); }
      else this.#queue.push({ data, resolve });
    });
  }

  #drain(w) {
    if (this.#queue.length) {
      const { data, resolve } = this.#queue.shift();
      this.#active.set(w, resolve);
      w.postMessage(data);
    }
  }
}

const pool = new WorkerPool("./worker.mjs", 4);
const results = await Promise.all(
  ["pw1", "pw2", "pw3", "pw4"].map((p) => pool.exec(p))
);
```

Use `worker_threads` for CPU-bound work (hashing, parsing, compression). For I/O-bound work, async/await is sufficient.'''
    },

    # --- 5. direct: cluster module ---
    {
        "instruction": r'''Show how to use the Node.js cluster module to scale an HTTP server across CPU cores with graceful shutdown.''',
        "output": r'''The `cluster` module forks the process to use all CPU cores:

```javascript
import cluster from "node:cluster";
import http from "node:http";
import { cpus } from "node:os";
import process from "node:process";

if (cluster.isPrimary) {
  const n = cpus().length;
  console.log(`Primary ${process.pid} forking ${n} workers`);
  for (let i = 0; i < n; i++) cluster.fork();

  cluster.on("exit", (worker, code) => {
    if (code !== 0) {
      console.log(`Worker ${worker.process.pid} died, restarting`);
      cluster.fork();
    }
  });

  // Graceful shutdown
  let stopping = false;
  function shutdown() {
    if (stopping) return;
    stopping = true;
    const workers = Object.values(cluster.workers);
    workers.forEach((w) => w.send("shutdown"));
    setTimeout(() => {
      workers.forEach((w) => w.kill("SIGKILL"));
      process.exit(1);
    }, 30_000);
  }
  process.on("SIGTERM", shutdown);
  process.on("SIGINT", shutdown);

} else {
  const server = http.createServer((req, res) => {
    res.writeHead(200);
    res.end(`Worker ${process.pid}\n`);
  });
  server.listen(3000);

  process.on("message", (msg) => {
    if (msg === "shutdown") {
      server.close(() => process.exit(0));
    }
  });
}
```

The OS load-balances connections across workers. For most deployments, use PM2 or container orchestration instead of raw `cluster`.'''
    },
]
