PAIRS = [
    (
        "edge-computing/cloudflare-workers-durable-objects-kv",
        "Explain Cloudflare Workers edge computing architecture including V8 isolate model, Durable Objects for stateful edge logic, Workers KV for global key-value storage, and D1 serverless SQL with practical implementation patterns and performance characteristics",
        r"""# Cloudflare Workers: Stateful Edge Computing

## The V8 Isolate Model

Cloudflare Workers run in **V8 isolates**, not containers or VMs. Each isolate starts in under 5ms (vs 50-500ms for containers) and consumes only ~5MB of memory. This is critical **because** it enables per-request compute at 300+ global edge locations without cold start penalties. **However**, isolates have strict constraints: 128MB memory limit, 30 second CPU time (50ms on free tier), and no persistent filesystem.

### Workers Fundamentals and KV Storage

```javascript
// --- Basic Worker with KV storage ---
// Workers KV: eventually consistent, global key-value store
// Best practice: use KV for read-heavy, write-infrequent data
// Trade-off: KV writes propagate globally in ~60 seconds

// wrangler.toml bindings:
// [[kv_namespaces]]
// binding = "CACHE"
// id = "abc123"

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (url.pathname === "/api/config") {
      // KV read — served from nearest edge PoP
      // Pitfall: KV reads are eventually consistent
      // Don't use for data requiring strong consistency
      const config = await env.CACHE.get("app-config", { type: "json" });
      if (config) {
        return new Response(JSON.stringify(config), {
          headers: {
            "Content-Type": "application/json",
            "Cache-Control": "public, max-age=60",
            "CF-Cache-Status": "HIT",
          },
        });
      }
      // Cache miss — fetch from origin
      const origin = await fetch("https://api.example.com/config");
      const data = await origin.json();
      // Write-back to KV with TTL
      // Common mistake: not setting expiration, causing stale data
      ctx.waitUntil(
        env.CACHE.put("app-config", JSON.stringify(data), {
          expirationTtl: 300, // 5 minutes
        })
      );
      return new Response(JSON.stringify(data), {
        headers: { "Content-Type": "application/json" },
      });
    }

    // Geolocation-based routing — zero-latency geo lookup
    // Therefore, edge workers can make routing decisions
    // without calling an external GeoIP service
    const country = request.cf?.country || "US";
    const continent = request.cf?.continent || "NA";
    const city = request.cf?.city || "unknown";

    if (url.pathname === "/api/nearest") {
      const origins = {
        NA: "https://us-east.api.example.com",
        EU: "https://eu-west.api.example.com",
        AS: "https://ap-south.api.example.com",
      };
      const origin = origins[continent] || origins.NA;
      return fetch(new Request(origin + url.pathname, request));
    }

    return new Response("Not Found", { status: 404 });
  },
};
```

### Durable Objects for Stateful Edge Logic

Durable Objects solve the hardest problem in edge computing: **consistent state at the edge**. Each Durable Object is a single-threaded JavaScript class that lives on one Cloudflare server, with its own persistent storage. **Therefore**, it provides strong consistency guarantees that KV cannot.

```javascript
// --- Durable Object: Rate Limiter with sliding window ---
// Each Durable Object instance handles one logical entity
// (e.g., one user, one room, one counter)

export class RateLimiter {
  constructor(state, env) {
    this.state = state;
    this.env = env;
    // In-memory cache of request timestamps
    // Durable Object is single-threaded — no race conditions
    this.requests = [];
    this.initialized = false;
  }

  async initialize() {
    if (this.initialized) return;
    // Load persisted state — survives Durable Object eviction
    const stored = await this.state.storage.get("requests");
    if (stored) {
      this.requests = stored;
    }
    this.initialized = true;
  }

  async fetch(request) {
    await this.initialize();
    const url = new URL(request.url);

    if (url.pathname === "/check") {
      const windowMs = 60000; // 1 minute
      const maxRequests = 100;
      const now = Date.now();

      // Sliding window — remove expired entries
      this.requests = this.requests.filter((t) => now - t < windowMs);

      if (this.requests.length >= maxRequests) {
        const retryAfter = Math.ceil(
          (this.requests[0] + windowMs - now) / 1000
        );
        return new Response(
          JSON.stringify({
            allowed: false,
            remaining: 0,
            retryAfter,
          }),
          {
            status: 429,
            headers: {
              "Content-Type": "application/json",
              "Retry-After": String(retryAfter),
            },
          }
        );
      }

      this.requests.push(now);

      // Persist asynchronously — best practice for durability
      // Trade-off: storage.put() is durable but adds ~1ms latency
      this.state.storage.put("requests", this.requests);

      return new Response(
        JSON.stringify({
          allowed: true,
          remaining: maxRequests - this.requests.length,
          resetAt: this.requests[0] + windowMs,
        }),
        {
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    return new Response("Not Found", { status: 404 });
  }
}

// --- Durable Object: Collaborative Document (CRDT-like) ---
export class CollaborativeDocument {
  constructor(state, env) {
    this.state = state;
    this.env = env;
    this.sessions = new Map(); // WebSocket connections
    this.document = { content: "", version: 0 };
  }

  async fetch(request) {
    if (request.headers.get("Upgrade") === "websocket") {
      // WebSocket handling — Durable Object as WebSocket hub
      // However, all connections to this document route to ONE DO instance
      // Therefore, we get strong consistency for collaborative editing
      const [client, server] = Object.values(new WebSocketPair());

      server.accept();
      const sessionId = crypto.randomUUID();
      this.sessions.set(sessionId, server);

      server.addEventListener("message", async (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === "edit") {
          this.document.content = msg.content;
          this.document.version++;
          // Persist document state
          await this.state.storage.put("document", this.document);
          // Broadcast to all other sessions
          const broadcast = JSON.stringify({
            type: "update",
            content: this.document.content,
            version: this.document.version,
            author: sessionId,
          });
          for (const [id, ws] of this.sessions) {
            if (id !== sessionId) {
              try {
                ws.send(broadcast);
              } catch (e) {
                this.sessions.delete(id);
              }
            }
          }
        }
      });

      server.addEventListener("close", () => {
        this.sessions.delete(sessionId);
      });

      return new Response(null, { status: 101, webSocket: client });
    }

    // HTTP fallback — return current document state
    const doc = (await this.state.storage.get("document")) || this.document;
    return new Response(JSON.stringify(doc), {
      headers: { "Content-Type": "application/json" },
    });
  }
}

// --- Worker routing to Durable Objects ---
export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname.startsWith("/api/rate-limit/")) {
      const userId = url.pathname.split("/").pop();
      // Durable Object ID from user — ensures same user always
      // routes to same instance globally
      const id = env.RATE_LIMITER.idFromName(userId);
      const stub = env.RATE_LIMITER.get(id);
      return stub.fetch(new Request(url.origin + "/check", request));
    }

    if (url.pathname.startsWith("/api/doc/")) {
      const docId = url.pathname.split("/").pop();
      const id = env.DOCUMENT.idFromName(docId);
      const stub = env.DOCUMENT.get(id);
      return stub.fetch(request);
    }

    return new Response("Not Found", { status: 404 });
  },
};
```

### D1 Serverless SQL and Edge Patterns

D1 brings **SQLite at the edge** — read replicas in every Cloudflare PoP with a single writer. The **pitfall** is that writes have higher latency (~50-100ms) because they route to the primary, while reads from replicas are sub-millisecond.

```javascript
// --- D1 Serverless SQL patterns ---

// Best practice: design schemas for read-heavy edge workloads
// Common mistake: treating D1 like a traditional RDBMS with
// heavy write workloads — it's optimized for read replicas

async function handleD1Request(request, env) {
  const url = new URL(request.url);

  if (url.pathname === "/api/users" && request.method === "GET") {
    // Read — served from nearest edge replica (fast)
    const page = parseInt(url.searchParams.get("page") || "1");
    const perPage = 20;
    const offset = (page - 1) * perPage;

    const { results, meta } = await env.DB.prepare(
      "SELECT id, name, email, created_at FROM users " +
        "ORDER BY created_at DESC LIMIT ? OFFSET ?"
    )
      .bind(perPage, offset)
      .all();

    return new Response(
      JSON.stringify({
        users: results,
        meta: {
          page,
          perPage,
          queryTimeMs: meta.duration,
          rowsRead: meta.rows_read,
        },
      }),
      { headers: { "Content-Type": "application/json" } }
    );
  }

  if (url.pathname === "/api/users" && request.method === "POST") {
    // Write — routes to primary (higher latency)
    const body = await request.json();

    // Therefore, batch writes when possible to amortize round-trip
    const stmt = env.DB.prepare(
      "INSERT INTO users (name, email) VALUES (?, ?) RETURNING id"
    );

    const result = await stmt.bind(body.name, body.email).first();

    return new Response(JSON.stringify({ id: result.id }), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    });
  }

  // Batch operations — D1 supports batched statements
  if (url.pathname === "/api/users/batch" && request.method === "POST") {
    const { users } = await request.json();
    const stmt = env.DB.prepare(
      "INSERT INTO users (name, email) VALUES (?, ?)"
    );
    // Batch all inserts in single round-trip to primary
    const results = await env.DB.batch(
      users.map((u) => stmt.bind(u.name, u.email))
    );
    return new Response(
      JSON.stringify({ inserted: results.length }),
      { headers: { "Content-Type": "application/json" } }
    );
  }

  return new Response("Not Found", { status: 404 });
}
```

## Summary and Key Takeaways

- **V8 isolates** start in <5ms with ~5MB memory — orders of magnitude faster than container cold starts
- **Workers KV** is eventually consistent (60s propagation) — use for read-heavy config/cache, not for data requiring strong consistency
- **Durable Objects** provide strong consistency at the edge through single-threaded execution — ideal for rate limiting, collaborative editing, and stateful WebSocket hubs
- A **common mistake** is using KV for write-heavy workloads — it's optimized for reads with rare updates
- The **trade-off** of D1 is fast reads from edge replicas vs higher write latency routing to the primary
- **Best practice**: use `ctx.waitUntil()` for non-blocking background work (KV writes, analytics) to avoid adding latency to responses
- The **pitfall** of Durable Objects is that each instance lives on ONE server — if that datacenter has issues, the DO is temporarily unavailable"""
    ),
    (
        "edge-computing/serverless-patterns-lambda-cold-starts",
        "Describe serverless architecture patterns including AWS Lambda cold start mitigation with provisioned concurrency and SnapStart, function composition with Step Functions, event-driven patterns with EventBridge, and cost optimization strategies for high-throughput workloads",
        r"""# Serverless Architecture: Lambda Patterns and Optimization

## Cold Start Anatomy

The biggest **pitfall** of serverless is cold starts — the initialization overhead when a new execution environment is created. **Because** Lambda provisions environments on demand, the first invocation after idle time (or during traffic spikes) pays a penalty: ~200ms for Python/Node, 1-3s for Java/.NET (JVM/CLR startup). Understanding where time goes is essential for mitigation.

### Cold Start Mitigation Strategies

```python
import json
import os
import time
import logging
from typing import Any, Optional, Callable
from dataclasses import dataclass, field
from functools import lru_cache

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# --- Module-level initialization (runs once per cold start) ---
# Best practice: move expensive initialization OUTSIDE the handler
# Therefore, it runs once and is reused across warm invocations

# These are initialized at import time (cold start):
import boto3

# Connection reuse — critical for warm start performance
# Common mistake: creating new clients inside handler
_dynamodb_client = boto3.resource("dynamodb")
_table = _dynamodb_client.Table(os.environ.get("TABLE_NAME", "users"))
_s3_client = boto3.client("s3")

# Pre-compiled patterns, loaded configs, etc.
@lru_cache(maxsize=1)
def get_config() -> dict:
    # Cached config — only fetched once per environment
    ssm = boto3.client("ssm")
    response = ssm.get_parameter(
        Name="/app/config", WithDecryption=True
    )
    return json.loads(response["Parameter"]["Value"])

# --- Lambda handler with cold start tracking ---

_cold_start = True

def handler(event: dict, context: Any) -> dict:
    global _cold_start
    start_time = time.perf_counter()

    is_cold = _cold_start
    _cold_start = False  # Subsequent invocations are warm

    try:
        # Route based on event source
        if "httpMethod" in event:
            result = handle_api_gateway(event, context)
        elif "Records" in event:
            result = handle_sqs(event, context)
        elif "detail-type" in event:
            result = handle_eventbridge(event, context)
        else:
            result = {"statusCode": 400, "body": "Unknown event type"}

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "Request completed",
            extra={
                "cold_start": is_cold,
                "duration_ms": round(elapsed_ms, 2),
                "remaining_ms": context.get_remaining_time_in_millis(),
                "memory_mb": int(context.memory_limit_in_mb),
                "request_id": context.aws_request_id,
            },
        )
        return result

    except Exception as e:
        logger.exception("Handler error: %s", e)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }

def handle_api_gateway(event: dict, context: Any) -> dict:
    method = event["httpMethod"]
    path = event["path"]

    if method == "GET" and path == "/users":
        # DynamoDB query — connection reused from module level
        response = _table.scan(Limit=20)
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"users": response.get("Items", [])}),
        }

    if method == "POST" and path == "/users":
        body = json.loads(event.get("body", "{}"))
        _table.put_item(Item={
            "id": context.aws_request_id,
            "name": body.get("name", ""),
            "email": body.get("email", ""),
        })
        return {"statusCode": 201, "body": json.dumps({"id": context.aws_request_id})}

    return {"statusCode": 404, "body": "Not found"}

def handle_sqs(event: dict, context: Any) -> dict:
    # Trade-off: SQS batch processing is more cost-effective
    # but requires idempotent processing (at-least-once delivery)
    failures = []
    for record in event["Records"]:
        try:
            body = json.loads(record["body"])
            process_message(body)
        except Exception as e:
            logger.error("Failed to process record %s: %s", record["messageId"], e)
            failures.append({"itemIdentifier": record["messageId"]})

    # Partial batch failure reporting
    return {"batchItemFailures": failures}

def handle_eventbridge(event: dict, context: Any) -> dict:
    detail_type = event["detail-type"]
    detail = event["detail"]
    logger.info("EventBridge: %s -> %s", detail_type, json.dumps(detail)[:200])
    return {"processed": True}

def process_message(body: dict) -> None:
    pass  # Business logic here
```

### Step Functions for Complex Workflows

**However**, complex workflows with branching, parallel execution, retries, and human approval steps should not be crammed into a single Lambda. AWS Step Functions provide a **state machine** that orchestrates Lambda functions with built-in error handling, retries, and timeouts.

```python
# --- Step Function definition (ASL — Amazon States Language) ---

STEP_FUNCTION_DEFINITION = {
    "Comment": "Order processing workflow",
    "StartAt": "ValidateOrder",
    "States": {
        "ValidateOrder": {
            "Type": "Task",
            "Resource": "arn:aws:lambda:us-east-1:123:function:validate-order",
            "Retry": [
                {
                    "ErrorEquals": ["States.TaskFailed"],
                    "IntervalSeconds": 2,
                    "MaxAttempts": 3,
                    "BackoffRate": 2.0,
                }
            ],
            "Catch": [
                {
                    "ErrorEquals": ["ValidationError"],
                    "Next": "NotifyValidationFailure",
                }
            ],
            "Next": "ParallelProcessing",
        },
        "ParallelProcessing": {
            # Parallel branches — run inventory check and payment simultaneously
            # Therefore, total time = max(inventory, payment) not sum
            "Type": "Parallel",
            "Branches": [
                {
                    "StartAt": "CheckInventory",
                    "States": {
                        "CheckInventory": {
                            "Type": "Task",
                            "Resource": "arn:aws:lambda:us-east-1:123:function:check-inventory",
                            "End": True,
                        }
                    },
                },
                {
                    "StartAt": "ProcessPayment",
                    "States": {
                        "ProcessPayment": {
                            "Type": "Task",
                            "Resource": "arn:aws:lambda:us-east-1:123:function:process-payment",
                            "Retry": [
                                {
                                    "ErrorEquals": ["PaymentGatewayTimeout"],
                                    "IntervalSeconds": 5,
                                    "MaxAttempts": 2,
                                }
                            ],
                            "End": True,
                        }
                    },
                },
            ],
            "Next": "FulfillOrder",
        },
        "FulfillOrder": {
            "Type": "Task",
            "Resource": "arn:aws:lambda:us-east-1:123:function:fulfill-order",
            "Next": "NotifyCustomer",
        },
        "NotifyCustomer": {
            "Type": "Task",
            "Resource": "arn:aws:lambda:us-east-1:123:function:notify-customer",
            "End": True,
        },
        "NotifyValidationFailure": {
            "Type": "Task",
            "Resource": "arn:aws:lambda:us-east-1:123:function:notify-failure",
            "End": True,
        },
    },
}

# --- Cost optimization patterns ---

@dataclass
class LambdaCostEstimate:
    invocations_per_month: int
    avg_duration_ms: float
    memory_mb: int
    architecture: str = "arm64"  # 20% cheaper than x86

    @property
    def gb_seconds(self) -> float:
        return (self.memory_mb / 1024) * (self.avg_duration_ms / 1000) * self.invocations_per_month

    @property
    def monthly_cost(self) -> float:
        # Pricing: $0.0000166667 per GB-second (arm64)
        # Pitfall: forgetting that higher memory also gets more CPU
        # 1769 MB = 1 full vCPU, 10240 MB = 6 vCPU
        price_per_gb_sec = 0.0000133334 if self.architecture == "arm64" else 0.0000166667
        request_cost = self.invocations_per_month * 0.0000002  # $0.20 per 1M
        compute_cost = self.gb_seconds * price_per_gb_sec
        return request_cost + compute_cost

class CostOptimizer:
    # Best practice: right-size Lambda memory using power tuning
    # More memory = more CPU = shorter duration = sometimes CHEAPER

    @staticmethod
    def find_optimal_memory(
        base_duration_ms: float,
        invocations: int,
        test_configs: list[tuple[int, float]] = None,
    ) -> dict:
        if test_configs is None:
            # Simulate power tuning results
            # (memory_mb, measured_duration_ms)
            test_configs = [
                (128, base_duration_ms * 4.0),
                (256, base_duration_ms * 2.0),
                (512, base_duration_ms * 1.2),
                (1024, base_duration_ms * 0.8),
                (1769, base_duration_ms * 0.6),  # 1 full vCPU
                (3008, base_duration_ms * 0.5),
            ]

        results = []
        for mem, dur in test_configs:
            estimate = LambdaCostEstimate(
                invocations_per_month=invocations,
                avg_duration_ms=dur,
                memory_mb=mem,
            )
            results.append({
                "memory_mb": mem,
                "duration_ms": dur,
                "monthly_cost": round(estimate.monthly_cost, 2),
                "gb_seconds": round(estimate.gb_seconds, 2),
            })

        # Find cheapest option
        optimal = min(results, key=lambda r: r["monthly_cost"])
        return {
            "optimal": optimal,
            "all_configs": results,
            "savings_vs_min_memory": round(
                (results[0]["monthly_cost"] - optimal["monthly_cost"])
                / results[0]["monthly_cost"] * 100, 1
            ),
        }

# Demo
optimizer = CostOptimizer()
result = optimizer.find_optimal_memory(
    base_duration_ms=500, invocations=1_000_000
)
print(f"Optimal config: {result['optimal']}")
print(f"Savings vs 128MB: {result['savings_vs_min_memory']}%")
```

## Summary and Key Takeaways

- **Module-level initialization** runs once per cold start — move SDK clients, DB connections, and config loading outside the handler
- **Provisioned concurrency** eliminates cold starts entirely but costs ~$15/month per pre-warmed instance
- A **common mistake** is creating new boto3 clients inside the handler — this adds 100-200ms to every invocation
- **Step Functions** are the **best practice** for multi-step workflows — they handle retries, timeouts, and parallel branches declaratively
- The **trade-off** of Lambda memory sizing: more memory = more CPU = faster execution = sometimes lower cost
- **arm64 (Graviton2)** provides 20% cost reduction and often 10-20% better performance than x86
- The **pitfall** of SQS triggers is at-least-once delivery — every message handler must be idempotent
- **Power tuning** (testing multiple memory configs) often reveals that the cheapest option is NOT the lowest memory"""
    ),
    (
        "edge-computing/webrtc-real-time-communication",
        "Explain WebRTC architecture including ICE candidate gathering, STUN/TURN servers, SDP offer-answer exchange, peer-to-peer data channels, and media stream handling with a signaling server implementation and practical connection establishment patterns",
        r"""# WebRTC: Real-Time Peer-to-Peer Communication

## The WebRTC Connection Stack

WebRTC enables **direct peer-to-peer** communication between browsers (or native apps) for audio, video, and arbitrary data. The stack has three main components: **ICE** for connectivity establishment, **DTLS** for encryption, and **SRTP** for media transport. Understanding the connection establishment flow is critical **because** it involves multiple asynchronous steps that fail silently if any step is misconfigured.

### Signaling Server and Connection Flow

```python
import asyncio
import json
import uuid
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum

# --- Signaling server (WebSocket-based) ---
# WebRTC doesn't define signaling — you build your own
# Best practice: use WebSockets for real-time signaling

class MessageType(Enum):
    JOIN = "join"
    OFFER = "offer"
    ANSWER = "answer"
    ICE_CANDIDATE = "ice_candidate"
    LEAVE = "leave"

@dataclass
class Peer:
    peer_id: str
    room_id: str
    websocket: object  # WebSocket connection
    joined_at: float = 0.0

@dataclass
class Room:
    room_id: str
    peers: dict[str, Peer] = field(default_factory=dict)
    max_peers: int = 10

    def add_peer(self, peer: Peer) -> bool:
        if len(self.peers) >= self.max_peers:
            return False
        self.peers[peer.peer_id] = peer
        return True

    def remove_peer(self, peer_id: str) -> Optional[Peer]:
        return self.peers.pop(peer_id, None)

    def get_other_peers(self, exclude_id: str) -> list[Peer]:
        return [p for pid, p in self.peers.items() if pid != exclude_id]

class SignalingServer:
    # Handles SDP offer/answer exchange and ICE candidate relay
    # Trade-off: centralized signaling vs mesh signaling
    # Centralized is simpler but is a single point of failure

    def __init__(self):
        self.rooms: dict[str, Room] = {}
        self.peer_to_room: dict[str, str] = {}

    async def handle_message(self, websocket, raw_message: str) -> None:
        try:
            msg = json.loads(raw_message)
        except json.JSONDecodeError:
            await self._send(websocket, {"type": "error", "message": "Invalid JSON"})
            return

        msg_type = msg.get("type")
        peer_id = msg.get("peerId", str(uuid.uuid4()))

        if msg_type == MessageType.JOIN.value:
            await self._handle_join(websocket, peer_id, msg.get("roomId", "default"))

        elif msg_type == MessageType.OFFER.value:
            # Relay SDP offer to target peer
            target_id = msg.get("targetId")
            if target_id:
                await self._relay_to_peer(target_id, {
                    "type": "offer",
                    "sdp": msg.get("sdp"),
                    "fromId": peer_id,
                })

        elif msg_type == MessageType.ANSWER.value:
            target_id = msg.get("targetId")
            if target_id:
                await self._relay_to_peer(target_id, {
                    "type": "answer",
                    "sdp": msg.get("sdp"),
                    "fromId": peer_id,
                })

        elif msg_type == MessageType.ICE_CANDIDATE.value:
            # Relay ICE candidates — these trickle in asynchronously
            # Pitfall: candidates can arrive before remote description is set
            # Therefore, queue them and apply after setRemoteDescription
            target_id = msg.get("targetId")
            if target_id:
                await self._relay_to_peer(target_id, {
                    "type": "ice_candidate",
                    "candidate": msg.get("candidate"),
                    "fromId": peer_id,
                })

        elif msg_type == MessageType.LEAVE.value:
            await self._handle_leave(peer_id)

    async def _handle_join(self, websocket, peer_id: str, room_id: str) -> None:
        # Create room if needed
        if room_id not in self.rooms:
            self.rooms[room_id] = Room(room_id=room_id)

        room = self.rooms[room_id]
        peer = Peer(peer_id=peer_id, room_id=room_id, websocket=websocket)

        if not room.add_peer(peer):
            await self._send(websocket, {"type": "error", "message": "Room full"})
            return

        self.peer_to_room[peer_id] = room_id

        # Notify existing peers about new arrival
        existing_peers = room.get_other_peers(peer_id)
        for existing in existing_peers:
            await self._send(existing.websocket, {
                "type": "peer_joined",
                "peerId": peer_id,
            })

        # Send list of existing peers to new joiner
        # Common mistake: not sending existing peer list — new peer
        # doesn't know who to create offers for
        await self._send(websocket, {
            "type": "room_joined",
            "peerId": peer_id,
            "roomId": room_id,
            "existingPeers": [p.peer_id for p in existing_peers],
        })

    async def _handle_leave(self, peer_id: str) -> None:
        room_id = self.peer_to_room.pop(peer_id, None)
        if room_id and room_id in self.rooms:
            room = self.rooms[room_id]
            room.remove_peer(peer_id)
            for peer in room.peers.values():
                await self._send(peer.websocket, {
                    "type": "peer_left",
                    "peerId": peer_id,
                })
            if not room.peers:
                del self.rooms[room_id]

    async def _relay_to_peer(self, target_id: str, message: dict) -> None:
        room_id = self.peer_to_room.get(target_id)
        if room_id and room_id in self.rooms:
            peer = self.rooms[room_id].peers.get(target_id)
            if peer:
                await self._send(peer.websocket, message)

    async def _send(self, websocket, message: dict) -> None:
        try:
            # In production, use actual WebSocket send
            pass  # websocket.send(json.dumps(message))
        except Exception:
            pass
```

### Client-Side Connection Establishment

The connection flow is: 1) Create RTCPeerConnection, 2) Create offer/answer SDP, 3) Exchange SDPs via signaling, 4) Trickle ICE candidates, 5) Connection established. **However**, NAT traversal often requires a TURN relay server for ~15% of connections that can't establish direct P2P.

```javascript
// --- WebRTC client implementation ---

class WebRTCClient {
  constructor(signalingUrl, roomId) {
    this.roomId = roomId;
    this.localStream = null;
    this.peers = new Map(); // peerId -> { connection, dataChannel }
    this.peerId = crypto.randomUUID();

    // ICE server configuration
    // Best practice: include both STUN (free, for NAT discovery)
    // and TURN (paid, for relay when P2P fails)
    this.iceConfig = {
      iceServers: [
        { urls: "stun:stun.l.google.com:19302" },
        {
          urls: "turn:turn.example.com:3478",
          username: "user",
          credential: "pass",
        },
      ],
      // Trade-off: 'all' tries P2P first then TURN
      // 'relay' forces TURN (more reliable, higher latency)
      iceTransportPolicy: "all",
    };

    // Signaling WebSocket
    this.ws = new WebSocket(signalingUrl);
    this.ws.onmessage = (event) => this.handleSignaling(JSON.parse(event.data));
    this.ws.onopen = () => this.join();

    // Pending ICE candidates (received before remote description set)
    this.pendingCandidates = new Map(); // peerId -> candidate[]
  }

  async join() {
    // Get local media stream
    this.localStream = await navigator.mediaDevices.getUserMedia({
      video: { width: 1280, height: 720, frameRate: 30 },
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    this.ws.send(
      JSON.stringify({ type: "join", peerId: this.peerId, roomId: this.roomId })
    );
  }

  async handleSignaling(msg) {
    switch (msg.type) {
      case "room_joined":
        // Create offers to all existing peers
        // Therefore, the new joiner initiates connections
        for (const existingPeerId of msg.existingPeers) {
          await this.createOffer(existingPeerId);
        }
        break;

      case "peer_joined":
        // Wait for their offer — don't create one
        // Common mistake: both sides creating offers simultaneously
        // causes "glare" — only one side should offer
        break;

      case "offer":
        await this.handleOffer(msg.fromId, msg.sdp);
        break;

      case "answer":
        await this.handleAnswer(msg.fromId, msg.sdp);
        break;

      case "ice_candidate":
        await this.handleIceCandidate(msg.fromId, msg.candidate);
        break;

      case "peer_left":
        this.removePeer(msg.peerId);
        break;
    }
  }

  async createOffer(targetPeerId) {
    const pc = this.createPeerConnection(targetPeerId);

    // Create data channel BEFORE creating offer
    // Pitfall: data channels must be created before SDP generation
    // or they won't be included in the offer
    const dc = pc.createDataChannel("messages", { ordered: true });
    this.peers.get(targetPeerId).dataChannel = dc;
    this.setupDataChannel(dc, targetPeerId);

    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);

    this.ws.send(
      JSON.stringify({
        type: "offer",
        sdp: pc.localDescription,
        targetId: targetPeerId,
        peerId: this.peerId,
      })
    );
  }

  async handleOffer(fromPeerId, sdp) {
    const pc = this.createPeerConnection(fromPeerId);

    // Handle incoming data channel
    pc.ondatachannel = (event) => {
      this.peers.get(fromPeerId).dataChannel = event.channel;
      this.setupDataChannel(event.channel, fromPeerId);
    };

    await pc.setRemoteDescription(new RTCSessionDescription(sdp));

    // Apply pending ICE candidates
    const pending = this.pendingCandidates.get(fromPeerId) || [];
    for (const candidate of pending) {
      await pc.addIceCandidate(new RTCIceCandidate(candidate));
    }
    this.pendingCandidates.delete(fromPeerId);

    const answer = await pc.createAnswer();
    await pc.setLocalDescription(answer);

    this.ws.send(
      JSON.stringify({
        type: "answer",
        sdp: pc.localDescription,
        targetId: fromPeerId,
        peerId: this.peerId,
      })
    );
  }

  async handleAnswer(fromPeerId, sdp) {
    const peer = this.peers.get(fromPeerId);
    if (peer) {
      await peer.connection.setRemoteDescription(
        new RTCSessionDescription(sdp)
      );
      // Apply pending candidates
      const pending = this.pendingCandidates.get(fromPeerId) || [];
      for (const candidate of pending) {
        await peer.connection.addIceCandidate(new RTCIceCandidate(candidate));
      }
      this.pendingCandidates.delete(fromPeerId);
    }
  }

  async handleIceCandidate(fromPeerId, candidate) {
    const peer = this.peers.get(fromPeerId);
    if (peer && peer.connection.remoteDescription) {
      await peer.connection.addIceCandidate(new RTCIceCandidate(candidate));
    } else {
      // Queue candidate — remote description not set yet
      if (!this.pendingCandidates.has(fromPeerId)) {
        this.pendingCandidates.set(fromPeerId, []);
      }
      this.pendingCandidates.get(fromPeerId).push(candidate);
    }
  }

  createPeerConnection(peerId) {
    const pc = new RTCPeerConnection(this.iceConfig);

    this.peers.set(peerId, { connection: pc, dataChannel: null });

    // Add local tracks
    if (this.localStream) {
      for (const track of this.localStream.getTracks()) {
        pc.addTrack(track, this.localStream);
      }
    }

    // ICE candidate trickle
    pc.onicecandidate = (event) => {
      if (event.candidate) {
        this.ws.send(
          JSON.stringify({
            type: "ice_candidate",
            candidate: event.candidate,
            targetId: peerId,
            peerId: this.peerId,
          })
        );
      }
    };

    // Remote stream handling
    pc.ontrack = (event) => {
      // Emit event for UI to display remote video
      console.log("Remote track from", peerId, event.streams[0]);
    };

    pc.onconnectionstatechange = () => {
      console.log("Connection state:", peerId, pc.connectionState);
      if (pc.connectionState === "failed") {
        this.removePeer(peerId);
      }
    };

    return pc;
  }

  setupDataChannel(dc, peerId) {
    dc.onopen = () => console.log("Data channel open with", peerId);
    dc.onmessage = (event) => console.log("Message from", peerId, event.data);
    dc.onclose = () => console.log("Data channel closed with", peerId);
  }

  removePeer(peerId) {
    const peer = this.peers.get(peerId);
    if (peer) {
      peer.connection.close();
      this.peers.delete(peerId);
    }
  }

  sendMessage(peerId, message) {
    const peer = this.peers.get(peerId);
    if (peer && peer.dataChannel && peer.dataChannel.readyState === "open") {
      peer.dataChannel.send(JSON.stringify(message));
    }
  }
}
```

## Summary and Key Takeaways

- WebRTC requires a **signaling server** (not defined by the protocol) to exchange SDP offers/answers and ICE candidates
- **ICE candidates trickle** asynchronously — the **pitfall** is receiving candidates before `setRemoteDescription`, so queue them
- Include both **STUN** (free, for NAT discovery) and **TURN** (paid relay) servers — ~15% of connections need TURN
- A **common mistake** is both peers creating offers simultaneously ("glare") — establish a consistent initiator (e.g., the joiner offers to existing peers)
- **Data channels** must be created BEFORE `createOffer()` to be included in the SDP
- The **trade-off** of `iceTransportPolicy: "relay"` forces all traffic through TURN — more reliable but higher latency and server cost
- **Best practice**: monitor `connectionstatechange` and `iceconnectionstatechange` events to detect and recover from connection failures"""
    ),
]
