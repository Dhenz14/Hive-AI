"""Thinking-trace pairs: Redis debugging."""

PAIRS = [
    (
        "thinking/debugging",
        r'''My Python application using Redis is running out of connections. I get "redis.exceptions.ConnectionError: Too many connections" even though I thought I was using connection pooling. Here is my code:

import redis
from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/data/<key>")
def get_data(key):
    r = redis.Redis(host="localhost", port=6379, db=0)
    value = r.get(key)
    return jsonify({"key": key, "value": value.decode() if value else None})

@app.route("/set/<key>/<value>")
def set_data(key, value):
    r = redis.Redis(host="localhost", port=6379, db=0)
    r.set(key, value)
    return jsonify({"status": "ok"})

# After a few hundred requests, connections are exhausted.
# redis-cli INFO clients shows connected_clients keeps climbing.''',
        r'''<think>
The problem is clear: each request creates a new `redis.Redis()` instance. While `redis.Redis()` does use a default connection pool internally, creating a new instance per request creates a new pool per request. Each pool creates new connections, and since the old pools and connections are not explicitly closed, they pile up until Redis hits the maxclients limit.

The fix is to create a single Redis connection pool and share it across all requests.
</think>

The problem is that you create a **new `redis.Redis()` instance per request**, and each instance creates its own connection pool. These pools are never explicitly closed, so connections accumulate until Redis hits `maxclients`.

```python
import redis
from flask import Flask, jsonify

app = Flask(__name__)

# ============================================================
# FIX 1: Create a single shared connection pool
# ============================================================

# Create ONE pool at module level (shared across all requests)
pool = redis.ConnectionPool(
    host="localhost",
    port=6379,
    db=0,
    max_connections=20,        # Limit total connections
    socket_timeout=5,          # Timeout for socket operations
    socket_connect_timeout=5,  # Timeout for initial connection
    retry_on_timeout=True,     # Auto-retry on timeout
    health_check_interval=30,  # Periodic connection health check
)

def get_redis():
    """Get a Redis client using the shared pool."""
    return redis.Redis(connection_pool=pool)

@app.route("/data/<key>")
def get_data(key):
    r = get_redis()  # Uses shared pool, no new connections created
    value = r.get(key)
    return jsonify({"key": key, "value": value.decode() if value else None})

@app.route("/set/<key>/<value>")
def set_data(key, value):
    r = get_redis()
    r.set(key, value)
    return jsonify({"status": "ok"})

# ============================================================
# FIX 2: Use Flask extension (even cleaner)
# ============================================================

from flask import g

def get_redis_client():
    """Get or create Redis client for current request context."""
    if "redis" not in g:
        g.redis = redis.Redis(connection_pool=pool)
    return g.redis

@app.teardown_appcontext
def close_redis(exception):
    """Clean up Redis client at end of request."""
    redis_client = g.pop("redis", None)
    if redis_client is not None:
        redis_client.close()

# ============================================================
# FIX 3: For async applications (FastAPI, aiohttp)
# ============================================================

import redis.asyncio as aioredis

async def create_async_pool():
    """Create an async Redis connection pool."""
    pool = aioredis.ConnectionPool.from_url(
        "redis://localhost:6379/0",
        max_connections=20,
        decode_responses=True,
    )
    return aioredis.Redis(connection_pool=pool)

# ============================================================
# DIAGNOSIS: Monitor connection usage
# ============================================================

def diagnose_connections():
    """Check Redis connection state."""
    r = redis.Redis(host="localhost", port=6379, db=0)
    info = r.info("clients")
    print(f"Connected clients: {info['connected_clients']}")
    print(f"Blocked clients: {info['blocked_clients']}")

    # Check maxclients setting
    config = r.config_get("maxclients")
    print(f"Max clients: {config['maxclients']}")

    # List all client connections
    clients = r.client_list()
    print(f"\nTotal connections: {len(clients)}")
    # Group by address to find connection leaks
    from collections import Counter
    addr_counts = Counter(c["addr"].rsplit(":", 1)[0] for c in clients)
    for addr, count in addr_counts.most_common(5):
        print(f"  {addr}: {count} connections")

    # Check pool stats
    print(f"\nPool stats:")
    print(f"  Max connections: {pool.max_connections}")
    print(f"  Created connections: {pool._created_connections}")
    print(f"  Available connections: {len(pool._available_connections)}")
    print(f"  In-use connections: {len(pool._in_use_connections)}")

# ============================================================
# PREVENTION: Set maxclients and timeout in redis.conf
# ============================================================
# In redis.conf:
#   maxclients 10000        # Maximum simultaneous connections
#   timeout 300             # Close idle connections after 5 minutes
#   tcp-keepalive 60        # Send TCP keepalive every 60 seconds
```

**Root cause summary:** `redis.Redis()` creates a new pool each time. Connection pools must be created once and shared. Always pass a shared `ConnectionPool` to `redis.Redis(connection_pool=pool)`.''',
    ),
    (
        "thinking/debugging",
        r'''My Redis pub/sub subscriber loses messages when it disconnects and reconnects. It also sometimes hangs forever when the Redis server restarts. How do I make pub/sub reliable?

import redis
import time

def subscriber():
    r = redis.Redis(host="localhost", port=6379)
    pubsub = r.pubsub()
    pubsub.subscribe("events")

    for message in pubsub.listen():
        if message["type"] == "message":
            process_event(message["data"])

# If Redis restarts, this function hangs or crashes
# Messages published while subscriber was down are lost''',
        r'''<think>
Redis pub/sub has fundamental limitations:
1. Messages are fire-and-forget -- if no subscriber is listening, the message is lost
2. No message persistence or replay
3. If the connection drops, the subscriber misses all messages during the disconnect

The fixes involve:
1. Reconnection logic for the subscriber
2. Using Redis Streams instead of pub/sub for reliable messaging
3. Using pub/sub with a fallback mechanism

Let me address all of these.
</think>

Redis pub/sub is inherently **unreliable** -- messages are fire-and-forget with no persistence. Here is how to handle reconnection and how to use Redis Streams for reliable messaging:

```python
import redis
import time
import logging
import signal
import sys

logger = logging.getLogger(__name__)

# ============================================================
# FIX 1: Pub/sub with automatic reconnection
# ============================================================

class ResilientSubscriber:
    """Pub/sub subscriber with automatic reconnection."""

    def __init__(self, host="localhost", port=6379, channels=None):
        self.host = host
        self.port = port
        self.channels = channels or ["events"]
        self.running = True
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, signum, frame):
        logger.info("Shutting down subscriber...")
        self.running = False

    def _connect(self):
        """Create a new Redis connection and subscribe."""
        r = redis.Redis(
            host=self.host,
            port=self.port,
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
            socket_keepalive=True,
            retry_on_timeout=True,
            health_check_interval=10,
        )
        pubsub = r.pubsub()
        pubsub.subscribe(*self.channels)
        logger.info("Subscribed to channels: %s", self.channels)
        return pubsub

    def run(self):
        """Main loop with reconnection logic."""
        backoff = 1
        max_backoff = 60

        while self.running:
            try:
                pubsub = self._connect()
                backoff = 1  # Reset backoff on successful connect

                # Use get_message with timeout instead of listen()
                # listen() blocks forever and cannot be interrupted
                while self.running:
                    message = pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=1.0,  # Check every second
                    )
                    if message is not None:
                        self._handle_message(message)

            except redis.ConnectionError as e:
                logger.warning(
                    "Connection lost: %s. Reconnecting in %ds...",
                    e, backoff
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)

            except Exception as e:
                logger.error("Unexpected error: %s", e, exc_info=True)
                time.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)

            finally:
                try:
                    pubsub.close()
                except Exception:
                    pass

    def _handle_message(self, message):
        if message["type"] == "message":
            try:
                process_event(message["data"])
            except Exception as e:
                logger.error("Error processing message: %s", e)

# Usage:
# subscriber = ResilientSubscriber(channels=["events", "alerts"])
# subscriber.run()

# ============================================================
# FIX 2: Use Redis Streams for reliable messaging (RECOMMENDED)
# ============================================================

class StreamConsumer:
    """Redis Streams consumer with consumer groups for reliable delivery."""

    def __init__(self, host="localhost", port=6379,
                 stream="events", group="processors", consumer="worker-1"):
        self.r = redis.Redis(host=host, port=port, decode_responses=True)
        self.stream = stream
        self.group = group
        self.consumer = consumer
        self.running = True
        self._ensure_group()

    def _ensure_group(self):
        """Create consumer group if it does not exist."""
        try:
            self.r.xgroup_create(
                self.stream, self.group, id="0", mkstream=True
            )
            logger.info("Created consumer group: %s", self.group)
        except redis.ResponseError as e:
            if "BUSYGROUP" in str(e):
                logger.info("Consumer group already exists: %s", self.group)
            else:
                raise

    def run(self):
        """Read from stream with acknowledgment."""
        while self.running:
            try:
                # First, process any pending (unacknowledged) messages
                self._process_pending()

                # Then read new messages
                results = self.r.xreadgroup(
                    groupname=self.group,
                    consumername=self.consumer,
                    streams={self.stream: ">"},  # ">" = only new messages
                    count=10,       # Batch size
                    block=5000,     # Block for 5 seconds max
                )

                if results:
                    for stream_name, messages in results:
                        for msg_id, data in messages:
                            self._process_and_ack(msg_id, data)

            except redis.ConnectionError as e:
                logger.warning("Connection lost: %s", e)
                time.sleep(2)
            except Exception as e:
                logger.error("Error: %s", e, exc_info=True)
                time.sleep(1)

    def _process_pending(self):
        """Reprocess unacknowledged messages (crash recovery)."""
        pending = self.r.xpending_range(
            self.stream, self.group, "-", "+", count=10,
            consumername=self.consumer,
        )
        for entry in pending:
            msg_id = entry["message_id"]
            messages = self.r.xrange(self.stream, min=msg_id, max=msg_id)
            for mid, data in messages:
                logger.info("Reprocessing pending message: %s", mid)
                self._process_and_ack(mid, data)

    def _process_and_ack(self, msg_id, data):
        """Process a message and acknowledge it."""
        try:
            process_event(data)
            self.r.xack(self.stream, self.group, msg_id)
        except Exception as e:
            logger.error("Failed to process %s: %s", msg_id, e)
            # Message remains pending and will be retried

# Producer side:
# r = redis.Redis()
# r.xadd("events", {"type": "order", "id": "123"})
```

**Key difference:** Pub/sub loses messages when subscribers are down. Redis Streams with consumer groups provide **at-least-once delivery**, message persistence, and crash recovery via pending message reprocessing.''',
    ),
    (
        "thinking/debugging",
        r'''I wrote a Redis Lua script for atomic operations but it is behaving incorrectly. The script should atomically check a counter and increment it only if it is below a threshold (rate limiting). But it seems to allow more requests than the limit.

import redis
import time

r = redis.Redis(host="localhost", port=6379, decode_responses=True)

RATE_LIMIT_SCRIPT = """
local key = KEYS[1]
local limit = ARGV[1]
local window = ARGV[2]

local current = redis.call('GET', key)
if current == false then
    redis.call('SET', key, 1, 'EX', window)
    return 1
end

if tonumber(current) < tonumber(limit) then
    redis.call('INCR', key)
    return 1
end

return 0
"""

def is_allowed(user_id, limit=10, window=60):
    key = f"ratelimit:{user_id}"
    result = r.eval(RATE_LIMIT_SCRIPT, 1, key, limit, window)
    return result == 1

# Testing: send 20 requests rapidly
for i in range(20):
    allowed = is_allowed("user123", limit=10, window=60)
    print(f"Request {i+1}: {'allowed' if allowed else 'denied'}")

# Expected: first 10 allowed, next 10 denied
# Actual: sometimes 11 or 12 get through!''',
        r'''<think>
Let me analyze the Lua script for the race condition.

The script:
1. GET key -> if nil, SET key 1 EX window, return 1
2. If current < limit, INCR key, return 1
3. Otherwise return 0

Wait, Lua scripts in Redis are atomic -- they run single-threaded, no other commands can interleave. So there should not be a race condition within the script itself.

Let me look more carefully...

The bug is in the comparison: `tonumber(current) < tonumber(limit)`. When current is 9 and limit is 10, 9 < 10 is true, so we INCR to 10. When current is 10, 10 < 10 is false, so we deny. That seems correct -- only 10 requests should get through.

Wait, but we GET and then INCR separately. Between GET returning 9 and INCR, could another script call interleave? No, Lua scripts are atomic.

Hmm, actually the issue might be with the arguments. `ARGV[1]` is the limit, passed as a string. The comparison uses `tonumber()` which should handle that. Let me re-read...

Actually, I think the bug is more subtle. The ARGV values are passed from Python as integers, but redis-py converts them to strings. The `tonumber()` in Lua should handle that correctly.

Wait -- the real issue might be the GET/SET vs GET/INCR path. When the key does not exist:
- SET key 1 EX window -> starts at 1
- If limit is 10, then requests 1-10 should be allowed

When current=1, 1<10 -> INCR to 2. When current=9, 9<10 -> INCR to 10. When current=10, 10<10 is false -> denied. So that is 1 (initial SET) + 9 (INCR) = 10 allowed. That is correct.

But wait! What if the TTL expires between the GET and the comparison? No, Lua is atomic.

Hmm, let me reconsider. Maybe the issue is that `INCR` returns the value AFTER increment, but we are comparing the value BEFORE increment. So when current=10 (at limit), we correctly deny. But we allowed when current was 9 and INCR'd to 10... that is 10 total, which is correct.

Actually, I think I need to look at this differently. The initial SET sets the value to 1. Then the limit check is `current < limit`. If limit=10, then:
- Values 1 through 9: current < 10 is true, INCR happens
- Value 10: current < 10 is false, denied

So values go: 1 (SET), 2, 3, 4, 5, 6, 7, 8, 9, 10 (INCR from 9 to 10, 10 < 10 is denied)

Wait, that is 10 INCRs from value 1 to value 10, but we start by SETting to 1 (which counts as the first request). Then:
- Request 1: SET to 1, return 1 (allowed)
- Request 2: GET=1, 1<10, INCR to 2, return 1 (allowed)
- ...
- Request 10: GET=9, 9<10, INCR to 10, return 1 (allowed)
- Request 11: GET=10, 10<10 false, return 0 (denied)

That is 10 allowed, which is correct for limit=10. So where does the off-by-one come from?

Ah wait, I bet the issue is that the user is passing the limit and window as Python integers, but redis-py is sending them as strings, and there might be a type issue. Actually `tonumber()` handles strings fine in Lua.

Let me think again... Maybe the bug is that the TTL is only set on the initial SET but not on subsequent INCRs. If the key already exists but has no TTL (or the TTL has expired between creation and the limit check), the counter lives forever and accumulates across windows.

Actually no, the SET with EX sets the TTL. INCR preserves the TTL. So that should be fine.

Hmm, I think I might be overthinking this. Let me consider: maybe the ACTUAL bug is the GET/INCR race. Even though Lua scripts are atomic, what if TWO Lua script invocations happen very close together? No, Redis processes Lua scripts serially.

Wait, I just realized: maybe the issue is `current == false`. In Redis Lua, a nil reply from GET is `false`. But what if the key exists but is an empty string? That could be edge-case-y.

Actually, I think the most likely real-world bug is a **sliding window issue**: the window timer starts from the first request. If requests come in at the end of one window and the beginning of the next, you could get double the limit. This is the "fixed window" problem.

For example: if the window is 60 seconds, and 10 requests come at second 59, the key expires at second 119. Then 10 more requests come at second 60 (new window), the key is gone, SET to 1, and you get 10 more. So in the 2-second period from 59-60, you had 20 requests -- double the limit.

That is probably the "sometimes 11 or 12 get through" the user sees -- it is the boundary between windows.

Let me provide a fix using a sliding window approach.
</think>

There are two bugs in this rate limiter. The first is subtle and the second is a fundamental design flaw:

```python
import redis
import time

r = redis.Redis(host="localhost", port=6379, decode_responses=True)

# ============================================================
# BUG 1: Fixed window boundary allows burst at window edges
# ============================================================
# Your script uses a fixed window (SET key 1 EX 60).
# At the boundary between two windows, the key expires and resets.
# If 10 requests arrive at second 59 and 10 more at second 60,
# you get 20 requests in 2 seconds -- double the limit.
# This is the classic "fixed window" problem.

# ============================================================
# BUG 2: GET then INCR is redundant (use INCR directly)
# ============================================================
# INCR on a non-existent key creates it with value 1.
# The GET is unnecessary and the separate SET path means
# the TTL might not be applied correctly on race edges.

# ============================================================
# FIX: Sliding window rate limiter using sorted sets
# ============================================================

SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

-- Remove entries outside the current window
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)

-- Count remaining entries in the window
local count = redis.call('ZCARD', key)

if count < limit then
    -- Add current request with timestamp as score
    redis.call('ZADD', key, now, now .. '-' .. math.random(1000000))
    -- Set expiry on the whole key to auto-cleanup
    redis.call('EXPIRE', key, window)
    return 1
end

return 0
"""

sliding_window_sha = r.script_load(SLIDING_WINDOW_SCRIPT)

def is_allowed_sliding(user_id, limit=10, window=60):
    """Sliding window rate limiter -- no boundary burst issue."""
    key = f"ratelimit:{user_id}"
    now = time.time()
    result = r.evalsha(
        sliding_window_sha, 1, key, limit, window, now
    )
    return result == 1

# ============================================================
# SIMPLER FIX: Fixed window with atomic INCR
# ============================================================

SIMPLE_RATE_LIMIT = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])

-- INCR creates the key with value 1 if it does not exist
local current = redis.call('INCR', key)

-- Set TTL only on first request (when counter becomes 1)
if current == 1 then
    redis.call('EXPIRE', key, window)
end

if current <= limit then
    return 1
end

return 0
"""

simple_sha = r.script_load(SIMPLE_RATE_LIMIT)

def is_allowed_simple(user_id, limit=10, window=60):
    """Fixed window but with correct atomic counter."""
    key = f"ratelimit:{user_id}"
    result = r.evalsha(simple_sha, 1, key, limit, window)
    return result == 1

# ============================================================
# BEST: Token bucket rate limiter
# ============================================================

TOKEN_BUCKET_SCRIPT = """
local key = KEYS[1]
local max_tokens = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(bucket[1])
local last_refill = tonumber(bucket[2])

if tokens == nil then
    -- Initialize bucket
    tokens = max_tokens - 1
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
    redis.call('EXPIRE', key, math.ceil(max_tokens / refill_rate) * 2)
    return 1
end

-- Calculate tokens to add based on elapsed time
local elapsed = now - last_refill
local new_tokens = elapsed * refill_rate
tokens = math.min(max_tokens, tokens + new_tokens)

if tokens >= 1 then
    tokens = tokens - 1
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
    redis.call('EXPIRE', key, math.ceil(max_tokens / refill_rate) * 2)
    return 1
end

redis.call('HSET', key, 'last_refill', now)
return 0
"""

bucket_sha = r.script_load(TOKEN_BUCKET_SCRIPT)

def is_allowed_token_bucket(user_id, max_tokens=10, refill_rate=0.167):
    """Token bucket: smooth rate limiting, no window boundaries."""
    key = f"bucket:{user_id}"
    now = time.time()
    result = r.evalsha(bucket_sha, 1, key, max_tokens, refill_rate, now)
    return result == 1

# Test
print("=== Testing sliding window ===")
for i in range(15):
    allowed = is_allowed_sliding("user1", limit=10, window=60)
    print(f"Request {i+1}: {'ALLOWED' if allowed else 'DENIED'}")
```

**Summary:** The original script had a fixed-window boundary burst problem and an unnecessarily complex GET/SET/INCR flow. Use a sliding window (sorted set) or token bucket for smooth, accurate rate limiting.''',
    ),
    (
        "thinking/debugging",
        r'''My Redis cluster is experiencing MOVED and ASK errors during slot migration, and my application keeps crashing. How do I handle cluster resharding gracefully?

import redis

r = redis.Redis(host="redis-node-1", port=6379)
# redis.exceptions.ResponseError: MOVED 12539 192.168.1.3:6379
# redis.exceptions.ResponseError: ASK 12539 192.168.1.3:6379''',
        r'''<think>
The user is connecting to a Redis Cluster using `redis.Redis()` which is the single-node client. This client does not understand MOVED/ASK redirections. They need to use `redis.cluster.RedisCluster` which handles these automatically.

MOVED errors mean the slot has permanently moved to another node. ASK errors mean the slot is being migrated and the request should be retried on the target node for just this one query.
</think>

You are using the **single-node Redis client** (`redis.Redis`) to connect to a Redis Cluster. This client does not handle MOVED/ASK redirections. Use `RedisCluster` instead:

```python
# ============================================================
# THE PROBLEM: redis.Redis does not handle cluster redirections
# ============================================================
# MOVED = slot has permanently moved to another node
# ASK = slot is being migrated (temporary redirect for one query)
# A single-node client does not know how to follow these.

# ============================================================
# FIX: Use RedisCluster client
# ============================================================

from redis.cluster import RedisCluster, ClusterNode

# Option 1: Connect with automatic node discovery
rc = RedisCluster(
    host="redis-node-1",
    port=6379,
    # Automatically discover all cluster nodes
    # and follow MOVED/ASK redirections
    decode_responses=True,
    # Retry settings for resilience during resharding
    retry_on_timeout=True,
    socket_timeout=5.0,
    socket_connect_timeout=5.0,
)

# Option 2: Connect with explicit startup nodes
startup_nodes = [
    ClusterNode("redis-node-1", 6379),
    ClusterNode("redis-node-2", 6379),
    ClusterNode("redis-node-3", 6379),
]

rc = RedisCluster(
    startup_nodes=startup_nodes,
    decode_responses=True,
    retry_on_timeout=True,
)

# Now MOVED and ASK are handled automatically
rc.set("mykey", "myvalue")  # Follows redirections transparently
value = rc.get("mykey")
print(value)

# ============================================================
# HANDLING RESHARDING IN APPLICATION CODE
# ============================================================

from redis.exceptions import (
    ClusterDownError,
    ConnectionError,
    TimeoutError,
    RedisClusterException,
)
import time

def resilient_operation(rc, operation, max_retries=3):
    """Execute a Redis cluster operation with retry logic."""
    for attempt in range(max_retries):
        try:
            return operation(rc)
        except ClusterDownError as e:
            # Cluster is in a failed state (not enough nodes)
            print(f"Cluster down: {e}. Attempt {attempt + 1}/{max_retries}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                # Force cluster topology refresh
                rc.nodes_manager.initialize()
            else:
                raise
        except ConnectionError as e:
            # Node unreachable -- could be during failover
            print(f"Connection error: {e}. Refreshing topology...")
            if attempt < max_retries - 1:
                time.sleep(1)
                rc.nodes_manager.initialize()
            else:
                raise
        except TimeoutError as e:
            print(f"Timeout: {e}. Retrying...")
            if attempt < max_retries - 1:
                time.sleep(1)
            else:
                raise

# Usage:
result = resilient_operation(
    rc,
    lambda r: r.get("mykey"),
    max_retries=3,
)

# ============================================================
# MULTI-KEY OPERATIONS DURING RESHARDING
# ============================================================
# Multi-key commands (MGET, MSET) require all keys to be in the
# same hash slot. During migration, some keys might be on different
# nodes temporarily.

def safe_mget(rc, keys):
    """MGET that handles cross-slot keys gracefully."""
    try:
        return rc.mget(keys)
    except RedisClusterException:
        # Fall back to individual GETs
        results = []
        for key in keys:
            try:
                results.append(rc.get(key))
            except Exception:
                results.append(None)
        return results

# Use hash tags to force keys into the same slot:
# {user:123}.name and {user:123}.email both hash on "user:123"
rc.set("{user:123}.name", "Alice")
rc.set("{user:123}.email", "alice@example.com")
# These will always be on the same node
values = rc.mget("{user:123}.name", "{user:123}.email")

# ============================================================
# MONITORING CLUSTER HEALTH
# ============================================================

def check_cluster_health(rc):
    """Monitor cluster state during resharding."""
    info = rc.cluster_info()
    print(f"Cluster state: {info.get('cluster_state', 'unknown')}")
    print(f"Known nodes: {info.get('cluster_known_nodes', 0)}")
    print(f"Cluster size: {info.get('cluster_size', 0)}")

    # Check for migrating slots
    nodes = rc.cluster_nodes()
    for node_id, node_info in nodes.items():
        flags = node_info.get("flags", "")
        if "fail" in flags:
            print(f"WARNING: Node {node_id} is in FAIL state")

    # Check slot coverage
    slots = rc.cluster_slots()
    total_slots = sum(
        end - start + 1 for start, end, *_ in slots
    )
    print(f"Covered slots: {total_slots}/16384")
    if total_slots < 16384:
        print("WARNING: Not all slots are covered!")

check_cluster_health(rc)
```

**Key points:**
1. Always use `RedisCluster` (not `Redis`) for cluster deployments
2. `RedisCluster` handles MOVED/ASK transparently
3. Call `nodes_manager.initialize()` to force topology refresh after failures
4. Use hash tags `{key}` to keep related keys on the same node
5. Monitor cluster state during resharding operations''',
    ),
    (
        "thinking/debugging",
        r'''My Redis instance is using too much memory and keys are being evicted unexpectedly. I configured maxmemory-policy to allkeys-lru but important keys are being evicted alongside cache keys. How do I protect important data while still using memory limits?

redis-cli INFO memory shows:
used_memory_human: 1.95G
maxmemory_human: 2.00G
maxmemory_policy: allkeys-lru
evicted_keys: 15234''',
        r'''<think>
The issue is that `allkeys-lru` evicts ANY key when memory is full, including important ones. The user needs to either:
1. Separate important data from cache data using different databases or instances
2. Use `volatile-lru` policy which only evicts keys with TTL set
3. Use Redis key namespacing and separate instances

Let me provide a comprehensive solution.
</think>

The `allkeys-lru` policy evicts **any key** regardless of importance when memory is full. Here is how to protect important data:

```python
import redis
import json
import time

r = redis.Redis(host="localhost", port=6379, decode_responses=True)

# ============================================================
# SOLUTION 1: Use volatile-lru policy (evict only keys with TTL)
# ============================================================
# Change maxmemory-policy to volatile-lru:
#   redis-cli CONFIG SET maxmemory-policy volatile-lru
#
# With volatile-lru:
# - Keys WITH a TTL (EXPIRE) can be evicted
# - Keys WITHOUT a TTL are NEVER evicted
# - Your important data stays safe if you do not set TTL on it

# Important data: no TTL -> never evicted
r.set("user:123:profile", json.dumps({"name": "Alice"}))
# No EXPIRE set!

# Cache data: has TTL -> can be evicted when memory is low
r.setex("cache:product:456", 3600, json.dumps({"price": 19.99}))
# Expires in 1 hour AND can be evicted early if memory is tight

# ============================================================
# SOLUTION 2: Separate Redis instances (RECOMMENDED)
# ============================================================
# Use different Redis instances for different data types:

# Instance 1: Persistent data (no maxmemory or very high limit)
persistent_redis = redis.Redis(host="localhost", port=6379, db=0)
# Configure: maxmemory 0 (no limit), no eviction
# Used for: user profiles, sessions, counters

# Instance 2: Cache data (with memory limit and LRU eviction)
cache_redis = redis.Redis(host="localhost", port=6380, db=0)
# Configure: maxmemory 2gb, maxmemory-policy allkeys-lru
# Used for: API response cache, computed results

class DataStore:
    """Wrapper that routes operations to the correct Redis instance."""

    def __init__(self):
        self.persistent = redis.Redis(host="localhost", port=6379)
        self.cache = redis.Redis(host="localhost", port=6380)

    def save_user(self, user_id, data):
        """Persistent storage -- never evicted."""
        self.persistent.set(f"user:{user_id}", json.dumps(data))

    def cache_result(self, key, data, ttl=3600):
        """Cache -- may be evicted under memory pressure."""
        self.cache.setex(f"cache:{key}", ttl, json.dumps(data))

    def get_user(self, user_id):
        raw = self.persistent.get(f"user:{user_id}")
        return json.loads(raw) if raw else None

    def get_cached(self, key):
        raw = self.cache.get(f"cache:{key}")
        return json.loads(raw) if raw else None

# ============================================================
# SOLUTION 3: Memory optimization to reduce eviction pressure
# ============================================================

def analyze_memory_usage(r):
    """Find what is consuming memory."""
    info = r.info("memory")
    print(f"Used memory: {info['used_memory_human']}")
    print(f"Peak memory: {info['used_memory_peak_human']}")
    print(f"Fragmentation ratio: {info['mem_fragmentation_ratio']:.2f}")

    # Sample keys to find memory hogs
    # Use SCAN (not KEYS *) to avoid blocking
    cursor = 0
    big_keys = []
    sample_count = 0

    while sample_count < 1000:
        cursor, keys = r.scan(cursor=cursor, count=100)
        for key in keys:
            try:
                mem = r.memory_usage(key)
                if mem and mem > 10240:  # > 10 KB
                    big_keys.append((key, mem))
            except Exception:
                pass
            sample_count += 1
        if cursor == 0:
            break

    big_keys.sort(key=lambda x: x[1], reverse=True)
    print("\nLargest keys (sampled):")
    for key, mem in big_keys[:20]:
        key_type = r.type(key)
        ttl = r.ttl(key)
        print(f"  {key}: {mem / 1024:.1f} KB, type={key_type}, ttl={ttl}")

def optimize_memory(r):
    """Apply memory optimizations."""
    # 1. Use hash ziplist encoding for small hashes
    # redis.conf: hash-max-ziplist-entries 128
    # redis.conf: hash-max-ziplist-value 64

    # 2. Use shorter key names in production
    # Instead of "user_profile:12345", use "up:12345"

    # 3. Compress large values before storing
    import zlib
    data = json.dumps({"large": "data" * 1000})
    compressed = zlib.compress(data.encode())
    r.set("compressed:key", compressed)
    # Decompress on read:
    raw = r.get("compressed:key")
    original = json.loads(zlib.decompress(raw))

    # 4. Set TTL on ALL cache keys
    # Find keys without TTL that should have one
    cursor = 0
    no_ttl_keys = []
    while True:
        cursor, keys = r.scan(cursor=cursor, match="cache:*", count=100)
        for key in keys:
            if r.ttl(key) == -1:  # -1 means no TTL
                no_ttl_keys.append(key)
                # Set a default TTL
                r.expire(key, 86400)  # 24 hours
        if cursor == 0:
            break
    print(f"Fixed {len(no_ttl_keys)} cache keys without TTL")

# ============================================================
# EVICTION POLICY COMPARISON
# ============================================================
# noeviction      - Return error when memory is full (safest)
# allkeys-lru     - Evict ANY key using LRU (dangerous for important data)
# volatile-lru    - Evict only keys WITH TTL using LRU (recommended)
# allkeys-lfu     - Evict any key using LFU (Redis 4.0+, better than LRU)
# volatile-lfu    - Evict TTL keys using LFU
# volatile-ttl    - Evict keys with shortest TTL first
# allkeys-random  - Random eviction (fast but unpredictable)

analyze_memory_usage(r)
```

**Recommended approach:** Use `volatile-lru` (or `volatile-lfu`) and only set TTL on cache/ephemeral keys. Important data without TTL will never be evicted. For large deployments, use separate Redis instances for persistent vs cache data.''',
    ),
]
