"""
Hive blockchain thinking pairs - dApp design decisions
"""

pairs = [
    {
        "instruction": r'''I am building a frontend for a Hive dApp. Should I use a traditional REST API backend that talks to Hive, or have the frontend talk to Hive API nodes directly?''',
        "output": r'''<think>
Frontend architecture for a Hive dApp -- this is a fundamental design decision. Let me think through both approaches.

Direct frontend-to-Hive approach: The JavaScript frontend makes RPC calls directly to Hive API nodes (api.hive.blog, etc.). For signing transactions, it uses Hive Keychain (browser extension) or HiveSigner.

Backend-mediated approach: The frontend talks to your REST API backend, which in turn talks to Hive. The backend might also maintain its own database for indexed data.

Hmm, let me think about the tradeoffs. Direct approach: simpler architecture, no backend to maintain, truly decentralized. But: no caching layer, no custom business logic server-side, every user hits public API nodes directly (which may rate limit), and you cannot aggregate or transform data efficiently.

Backend approach: you control the data pipeline, can cache aggressively, aggregate data, handle rate limiting centrally. But: adds infrastructure, introduces a central point of failure (your server), and you need to handle user authentication carefully (never handle private keys server-side).

I initially thought the direct approach was better for decentralization, but actually most successful Hive dApps use a hybrid. PeakD, Ecency, and Hive.blog all have backends that index and serve data. The frontend talks to the backend for reads and uses Hive Keychain for signing transactions.

Wait, that is the key insight: reads through backend, writes through Keychain. The backend never needs private keys. Reads benefit from caching and indexing. Writes are signed client-side and broadcast either directly or through the backend as a proxy.

The tradeoff is: pure client-side (maximally decentralized, limited functionality) vs hybrid (practical, performant, most of the decentralization benefits). The hybrid approach wins for almost all real applications.
</think>

Use a hybrid architecture: reads through your backend (cached, indexed), writes signed client-side via Hive Keychain:

```python
# === Architecture Overview ===
#
# Frontend (React/Vue/etc.)
#   |
#   +--> Your Backend API (reads, caching, aggregation)
#   |       |
#   |       +--> Hive API nodes (blockchain queries)
#   |       +--> PostgreSQL (indexed app data)
#   |
#   +--> Hive Keychain (transaction signing, direct broadcast)
#
# Key principle: Backend handles reads, Keychain handles writes
# Backend NEVER touches private keys

# === Backend API (FastAPI example) ===

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from beem import Hive
from beem.account import Account
from beem.comment import Comment
import json
import time
from functools import lru_cache
from collections import OrderedDict

app = FastAPI(title="Hive dApp API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://mydapp.com"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

hive = Hive(node=[
    "https://api.hive.blog",
    "https://api.deathwing.me"
])


# === Caching Layer ===

class TTLCache:
    def __init__(self, max_size=1000):
        self.cache = OrderedDict()
        self.max_size = max_size

    def get(self, key, ttl=60):
        if key in self.cache:
            value, timestamp = self.cache[key]
            if time.time() - timestamp < ttl:
                return value
            del self.cache[key]
        return None

    def set(self, key, value):
        self.cache[key] = (value, time.time())
        if len(self.cache) > self.max_size:
            self.cache.popitem(last=False)

cache = TTLCache()


# === API Endpoints (Read-only, cached) ===

@app.get("/api/account/{username}")
async def get_account(username: str):
    """Get account data with caching."""
    cached = cache.get(f"account:{username}", ttl=30)
    if cached:
        return cached

    try:
        acc = Account(username, blockchain_instance=hive)
        data = {
            "name": username,
            "reputation": float(acc.get_reputation()),
            "hive_power": float(acc.get_hive_power()),
            "voting_power": acc.get_voting_power(),
            "balances": {
                "hive": float(acc.get_balance("available", "HIVE")),
                "hbd": float(acc.get_balance("available", "HBD")),
            },
            "profile": json.loads(
                acc.get("posting_json_metadata", "{}") or "{}"
            ).get("profile", {})
        }
        cache.set(f"account:{username}", data)
        return data
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/feed/{username}")
async def get_feed(username: str,
                   sort: str = Query("created",
                                     regex="^(trending|created|hot)$"),
                   limit: int = Query(20, ge=1, le=50)):
    """Get user's feed with server-side aggregation."""
    cache_key = f"feed:{username}:{sort}:{limit}"
    cached = cache.get(cache_key, ttl=60)
    if cached:
        return cached

    import requests
    resp = requests.post("https://api.hive.blog", json={
        "jsonrpc": "2.0",
        "method": "bridge.get_ranked_posts",
        "params": {"sort": sort, "tag": "", "limit": limit,
                   "observer": username},
        "id": 1
    })
    posts = resp.json().get("result", [])

    # Transform for frontend consumption
    feed = []
    for post in posts:
        feed.append({
            "author": post["author"],
            "permlink": post["permlink"],
            "title": post.get("title", ""),
            "body_preview": post.get("body", "")[:300],
            "created": post.get("created", ""),
            "votes": post.get("stats", {}).get("total_votes", 0),
            "payout": post.get("payout", 0),
            "community": post.get("community", ""),
            "author_avatar": (
                post.get("author_data", {}).get("profile_image", "")
            ),
        })

    cache.set(cache_key, feed)
    return feed


@app.get("/api/post/{author}/{permlink}")
async def get_post(author: str, permlink: str):
    """Get full post data."""
    cache_key = f"post:{author}/{permlink}"
    cached = cache.get(cache_key, ttl=120)
    if cached:
        return cached

    try:
        post = Comment(f"@{author}/{permlink}",
                      blockchain_instance=hive)
        post.refresh()
        data = {
            "author": author,
            "permlink": permlink,
            "title": post.get("title", ""),
            "body": post.get("body", ""),
            "created": str(post.get("created", "")),
            "net_votes": post.get("net_votes", 0),
            "pending_payout": str(post.get("pending_payout_value", "")),
            "replies": post.get("children", 0),
            "json_metadata": json.loads(
                post.get("json_metadata", "{}") or "{}"
            ),
        }
        cache.set(cache_key, data)
        return data
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


# === Transaction Preparation (for client-side signing) ===

@app.post("/api/prepare/vote")
async def prepare_vote(voter: str, author: str, permlink: str,
                       weight: int = 10000):
    """Prepare a vote operation for client-side signing.

    The frontend sends this to Hive Keychain for signing.
    We NEVER handle private keys.
    """
    return {
        "operation": ["vote", {
            "voter": voter,
            "author": author,
            "permlink": permlink,
            "weight": weight
        }],
        "required_key": "posting",
        "sign_with": "keychain"
    }


# === Frontend Integration (JavaScript) ===
#
# // Read data from your backend
# const account = await fetch('/api/account/myuser').then(r => r.json());
#
# // Sign transactions with Keychain (client-side)
# if (window.hive_keychain) {
#     hive_keychain.requestVote(
#         'myuser',           // voter
#         'author',           // post author
#         'permlink',         // post permlink
#         '10000',            // weight (100%)
#         function(response) {
#             console.log('Vote result:', response);
#         }
#     );
# }
```

This architecture gives you: fast reads via caching (30-120s TTL per data type), no private key handling on the server, reduced load on public API nodes, and the ability to add custom business logic (aggregations, search, analytics) without being limited by the Hive API. The frontend remains decentralized for writes through Keychain.'''
    },
    {
        "instruction": r'''My Hive dApp needs to show real-time updates when new posts or votes come in. Should I use polling, WebSockets, or Server-Sent Events?''',
        "output": r'''<think>
Real-time updates for a Hive dApp frontend. Let me think about the data flow.

Hive produces a block every 3 seconds. Within that block, there could be new posts, votes, transfers, etc. The question is how to push this to the frontend efficiently.

Option 1: Polling. The frontend periodically asks the backend "any new data?" This is simple but wasteful if there are no updates, and has up to 1 polling-interval latency.

Option 2: WebSockets. Bidirectional persistent connection. The backend pushes updates to the frontend immediately. Lower latency, more efficient, but more complex infrastructure (need WebSocket support in backend and load balancer).

Option 3: Server-Sent Events (SSE). Unidirectional server-to-client stream over HTTP. Simpler than WebSockets (no special protocol), works through standard HTTP infrastructure, auto-reconnects. But only server-to-client, and limited browser connection pool (6 per domain in HTTP/1.1, unlimited in HTTP/2).

Hmm, for a Hive dApp, the data flow is primarily server-to-client (blockchain events pushed to user). The client rarely needs to push data TO the server (they use Keychain for transactions). So SSE's unidirectional nature is actually fine.

I initially thought WebSockets would be better because of lower latency, but the 3-second block time of Hive means we can never be faster than that anyway. SSE gives us near-instant delivery within a block cycle with much simpler infrastructure.

Wait, but what about scale? If I have 10,000 connected users, that is 10,000 open SSE connections. Each connection is long-lived but lightweight (just an HTTP stream). For comparison, WebSocket connections also stay open. The memory footprint is similar.

The tradeoff is: polling (simplest, highest latency, most bandwidth) vs SSE (simple, low latency, efficient, server-to-client only) vs WebSockets (complex, lowest latency, bidirectional). For Hive dApps, SSE is the sweet spot.

Actually, I should also consider: what events are we streaming? All blockchain events would be too much. The backend should filter to events relevant to the connected user (their posts being voted on, replies to their content, etc.) or to the current view (new posts in a community).
</think>

Use Server-Sent Events (SSE) for Hive dApp real-time updates. SSE is simpler than WebSockets and Hive's 3-second block time makes bidirectional communication unnecessary:

```python
# === Backend: SSE Stream with Block Monitoring ===

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from beem import Hive
from beem.blockchain import Blockchain
import json
import asyncio
import time
from collections import defaultdict
from threading import Thread, Lock

app = FastAPI()

hive = Hive(node=[
    "https://api.hive.blog",
    "https://api.deathwing.me"
])


class EventBus:
    """Distribute blockchain events to connected SSE clients."""

    def __init__(self):
        self.subscribers = defaultdict(list)  # channel -> [queues]
        self.lock = Lock()

    def subscribe(self, channel):
        """Create a new subscriber queue for a channel."""
        queue = asyncio.Queue(maxsize=100)
        with self.lock:
            self.subscribers[channel].append(queue)
        return queue

    def unsubscribe(self, channel, queue):
        """Remove a subscriber queue."""
        with self.lock:
            if queue in self.subscribers[channel]:
                self.subscribers[channel].remove(queue)

    def publish(self, channel, event_type, data):
        """Publish an event to all subscribers of a channel."""
        message = {
            "type": event_type,
            "data": data,
            "timestamp": time.time()
        }
        with self.lock:
            dead_queues = []
            for queue in self.subscribers[channel]:
                try:
                    queue.put_nowait(message)
                except asyncio.QueueFull:
                    dead_queues.append(queue)
            for q in dead_queues:
                self.subscribers[channel].remove(q)


event_bus = EventBus()


# === Blockchain Monitor (background thread) ===

def monitor_blockchain():
    """Stream blocks and publish relevant events."""
    chain = Blockchain(blockchain_instance=hive)

    for op in chain.stream(opNames=["comment", "vote", "transfer",
                                     "custom_json"]):
        op_type = op.get("type", "")

        if op_type == "comment":
            author = op.get("author", "")
            parent = op.get("parent_author", "")

            if not parent:
                # New post
                event_bus.publish("global", "new_post", {
                    "author": author,
                    "permlink": op.get("permlink", ""),
                    "title": op.get("title", ""),
                })
                # Community-specific event
                community = op.get("parent_permlink", "")
                if community.startswith("hive-"):
                    event_bus.publish(
                        f"community:{community}", "new_post",
                        {"author": author,
                         "permlink": op.get("permlink", "")}
                    )
            else:
                # Reply notification
                event_bus.publish(f"user:{parent}", "new_reply", {
                    "author": author,
                    "permlink": op.get("permlink", ""),
                    "parent_permlink": op.get("parent_permlink", ""),
                })

        elif op_type == "vote":
            post_author = op.get("author", "")
            voter = op.get("voter", "")
            weight = op.get("weight", 0)

            event_bus.publish(f"user:{post_author}", "vote_received", {
                "voter": voter,
                "permlink": op.get("permlink", ""),
                "weight": weight,
            })

            event_bus.publish(
                f"post:{post_author}/{op.get('permlink', '')}",
                "new_vote",
                {"voter": voter, "weight": weight}
            )

        elif op_type == "transfer":
            to_account = op.get("to", "")
            event_bus.publish(f"user:{to_account}", "transfer_in", {
                "from": op.get("from", ""),
                "amount": op.get("amount", ""),
                "memo": op.get("memo", ""),
            })


# Start monitor in background thread
monitor_thread = Thread(target=monitor_blockchain, daemon=True)
monitor_thread.start()


# === SSE Endpoints ===

async def event_stream(channel):
    """Generate SSE events for a channel."""
    queue = event_bus.subscribe(channel)
    try:
        while True:
            try:
                event = await asyncio.wait_for(
                    queue.get(), timeout=30
                )
                yield (f"event: {event['type']}\n"
                       f"data: {json.dumps(event['data'])}\n\n")
            except asyncio.TimeoutError:
                # Send keepalive
                yield ": keepalive\n\n"
    finally:
        event_bus.unsubscribe(channel, queue)


@app.get("/events/user/{username}")
async def user_events(username: str):
    """SSE stream for user-specific events (votes, replies, transfers)."""
    return StreamingResponse(
        event_stream(f"user:{username}"),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        }
    )


@app.get("/events/community/{community}")
async def community_events(community: str):
    """SSE stream for community events (new posts)."""
    return StreamingResponse(
        event_stream(f"community:{community}"),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"}
    )


@app.get("/events/post/{author}/{permlink}")
async def post_events(author: str, permlink: str):
    """SSE stream for post-specific events (new votes)."""
    return StreamingResponse(
        event_stream(f"post:{author}/{permlink}"),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"}
    )


@app.get("/events/global")
async def global_events():
    """SSE stream for global events (new posts across all communities)."""
    return StreamingResponse(
        event_stream("global"),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"}
    )


# === Frontend JavaScript ===
#
# // Subscribe to user events
# const events = new EventSource('/events/user/myusername');
#
# events.addEventListener('vote_received', (e) => {
#     const data = JSON.parse(e.data);
#     showNotification(`${data.voter} voted on your post!`);
# });
#
# events.addEventListener('new_reply', (e) => {
#     const data = JSON.parse(e.data);
#     showNotification(`${data.author} replied to your post`);
# });
#
# // Auto-reconnects on disconnect (built into EventSource)
# events.onerror = () => console.log('SSE reconnecting...');
```

Why SSE over WebSockets for Hive: data flows one way (chain to user), 3-second block time means sub-second latency is unnecessary, SSE auto-reconnects on disconnect, works through standard HTTP/2 infrastructure, and simpler to implement and debug. The channel-based event bus lets clients subscribe to exactly the events they need (user notifications, community feed, post activity).'''
    },
    {
        "instruction": r'''How should I handle state management in my Hive dApp when the blockchain is the source of truth but reads are slow and writes have confirmation delay?''',
        "output": r'''<think>
State management with blockchain as source of truth -- this is the classic optimistic update pattern. The challenge is:

1. Reading state from the blockchain is slow (API calls, 100-500ms each)
2. Writing state (broadcasting a transaction) takes 3+ seconds to confirm
3. Users expect instant UI feedback

If I wait for blockchain confirmation before updating the UI, the app feels sluggish. But if I update the UI optimistically and the transaction fails, I need to revert.

Let me think about the state management architecture. The app has three "layers" of state:
- Server state: what is actually on the blockchain (authoritative but slow)
- Cached state: local copy of blockchain state (fast but potentially stale)
- Optimistic state: predicted state after pending transactions (instant but unconfirmed)

The UI should show: cached_state + optimistic_mutations. When a transaction confirms, the optimistic mutation is replaced by the real blockchain state. If a transaction fails, the optimistic mutation is reverted.

Hmm, this is similar to how Apollo Client handles GraphQL mutations with optimistic responses. Or how Redux handles offline-first patterns.

I initially thought I could just use React Query or SWR for caching and manually handle optimistic updates, but there is a subtlety with blockchain: the "confirmed" state might not exactly match the optimistic prediction. For example, if I vote 100% on a post, the optimistic update might show +$0.05 payout increase, but the actual increase depends on the current reward pool and total rshares, which I cannot compute exactly client-side.

The tradeoff is: simple optimistic updates (fast UI, might show slightly wrong numbers temporarily) vs no optimistic updates (slow UI, always accurate). For most actions (voting, posting, following), simple optimistic updates are fine because the user cares more about "did my action work?" than the exact payout number.

Actually, there is another issue: what about multiple pending transactions? If the user votes on three posts rapidly, each optimistic update should stack on top of the previous ones, including reducing the displayed voting power.
</think>

Use a three-layer state model with optimistic mutations that reconcile against blockchain confirmations:

```python
# This is a Python backend + conceptual frontend pattern.
# The backend provides the caching layer; the frontend handles
# optimistic updates.

# === Backend: State Cache with Version Tracking ===

from fastapi import FastAPI
from beem import Hive
from beem.account import Account
from beem.comment import Comment
import json
import time
from collections import OrderedDict

app = FastAPI()
hive = Hive(node=["https://api.hive.blog"])


class BlockchainStateCache:
    """Cache blockchain state with version tracking for reconciliation."""

    def __init__(self, max_size=5000):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.pending_mutations = {}  # tx_id -> mutation data

    def get(self, key, ttl=30):
        if key in self.cache:
            value, timestamp, version = self.cache[key]
            age = time.time() - timestamp
            if age < ttl:
                return {"data": value, "age": age, "version": version}
        return None

    def set(self, key, value, version=None):
        v = version or int(time.time() * 1000)
        self.cache[key] = (value, time.time(), v)
        if len(self.cache) > self.max_size:
            self.cache.popitem(last=False)
        return v

    def invalidate(self, key):
        self.cache.pop(key, None)

    def register_pending(self, tx_id, affected_keys, mutation):
        """Register a pending transaction for reconciliation."""
        self.pending_mutations[tx_id] = {
            "keys": affected_keys,
            "mutation": mutation,
            "submitted_at": time.time()
        }

    def confirm_pending(self, tx_id):
        """Transaction confirmed -- invalidate affected cache keys."""
        if tx_id in self.pending_mutations:
            pending = self.pending_mutations.pop(tx_id)
            for key in pending["keys"]:
                self.invalidate(key)

    def reject_pending(self, tx_id):
        """Transaction failed -- remove from pending."""
        self.pending_mutations.pop(tx_id, None)

    def cleanup_stale_pending(self, max_age=120):
        """Remove pending mutations older than max_age seconds."""
        now = time.time()
        stale = [
            tx_id for tx_id, data in self.pending_mutations.items()
            if now - data["submitted_at"] > max_age
        ]
        for tx_id in stale:
            self.reject_pending(tx_id)


state_cache = BlockchainStateCache()


# === Backend Endpoints ===

@app.get("/api/state/account/{username}")
async def get_account_state(username: str):
    """Get account state with cache metadata."""
    cached = state_cache.get(f"account:{username}", ttl=15)
    if cached:
        return {
            "source": "cache",
            "data": cached["data"],
            "age_seconds": cached["age"],
            "version": cached["version"]
        }

    acc = Account(username, blockchain_instance=hive)
    data = {
        "name": username,
        "voting_power": acc.get_voting_power(),
        "hive_power": float(acc.get_hive_power()),
        "reputation": float(acc.get_reputation()),
        "vote_value": float(acc.get_vote_value()),
    }
    version = state_cache.set(f"account:{username}", data)

    return {
        "source": "blockchain",
        "data": data,
        "age_seconds": 0,
        "version": version
    }


@app.post("/api/state/pending")
async def register_pending_tx(tx_id: str, mutation_type: str,
                               affected_keys: list, mutation: dict):
    """Register a pending transaction for state reconciliation.

    Called by frontend after broadcasting via Keychain.
    """
    state_cache.register_pending(tx_id, affected_keys, mutation)
    return {"status": "registered", "tx_id": tx_id}


@app.post("/api/state/confirm/{tx_id}")
async def confirm_tx(tx_id: str):
    """Confirm a transaction -- invalidate affected caches."""
    state_cache.confirm_pending(tx_id)
    return {"status": "confirmed"}


# === Frontend State Management Pattern (Python pseudocode) ===

class OptimisticStateManager:
    """Frontend-side state management with optimistic updates.

    In a real app, this would be JavaScript (React/Vue/Svelte).
    Shown in Python for training purposes.
    """

    def __init__(self):
        self.server_state = {}    # last known blockchain state
        self.pending_txs = {}     # tx_id -> optimistic mutation
        self.ui_state = {}        # computed: server + pending

    def fetch_state(self, key, api_url):
        """Fetch state from backend cache."""
        # response = await fetch(f'{api_url}/api/state/{key}')
        # data = await response.json()
        # self.server_state[key] = data['data']
        # self._recompute_ui()
        pass

    def apply_optimistic_mutation(self, tx_id, mutation):
        """Apply an optimistic update before confirmation.

        mutation: dict describing the expected state change
        Example: {"type": "vote", "account": "user",
                  "vp_change": -2.0, "post": "auth/perm",
                  "vote_added": True}
        """
        self.pending_txs[tx_id] = mutation
        self._recompute_ui()

    def confirm_transaction(self, tx_id):
        """Transaction confirmed -- remove optimistic mutation,
        refresh server state.
        """
        self.pending_txs.pop(tx_id, None)
        # Trigger re-fetch of affected state from backend
        self._recompute_ui()

    def reject_transaction(self, tx_id):
        """Transaction failed -- revert optimistic mutation."""
        self.pending_txs.pop(tx_id, None)
        self._recompute_ui()
        # Show error notification to user

    def _recompute_ui(self):
        """Compute UI state by applying pending mutations to server state."""
        import copy
        self.ui_state = copy.deepcopy(self.server_state)

        for tx_id, mutation in self.pending_txs.items():
            if mutation["type"] == "vote":
                account_key = f"account:{mutation['account']}"
                if account_key in self.ui_state:
                    self.ui_state[account_key]["voting_power"] += \
                        mutation["vp_change"]

                post_key = f"post:{mutation['post']}"
                if post_key in self.ui_state:
                    self.ui_state[post_key]["net_votes"] += 1
                    self.ui_state[post_key]["user_has_voted"] = True

    def get_display_state(self, key):
        """Get state for UI rendering."""
        state = self.ui_state.get(key, self.server_state.get(key))
        has_pending = any(
            key in str(m) for m in self.pending_txs.values()
        )
        return {
            "data": state,
            "is_pending": has_pending,
            "is_stale": key not in self.server_state
        }


# === Example Flow ===
#
# 1. User loads page -> fetch state from backend (cached)
# 2. User clicks "Vote" -> apply optimistic mutation (instant UI update)
# 3. Keychain signs and broadcasts -> register pending TX with backend
# 4a. TX confirms -> remove optimistic mutation, re-fetch real state
# 4b. TX fails -> revert optimistic mutation, show error
#
# The UI always shows: server_state + pending_mutations
# Pending mutations have a visual indicator (spinner, lighter color)
```

The three-layer model (blockchain truth, server cache, optimistic UI) provides instant feedback while maintaining correctness. Key patterns: optimistic mutations are keyed by transaction ID for clean reconciliation, cache invalidation on confirmation forces a fresh fetch from blockchain, and stale pending mutations are auto-cleaned after a timeout to prevent state drift.'''
    },
    {
        "instruction": r'''I want to build a Hive dApp that works offline and syncs when connectivity is restored. What patterns should I use?''',
        "output": r'''<think>
Offline-first for a blockchain app -- this is challenging because blockchains are inherently online systems. You cannot broadcast transactions offline. But you can queue transactions and broadcast them when connectivity returns.

Let me think about what can work offline:
- Reading previously cached data (posts, account info)
- Composing new posts/comments (stored locally, broadcast later)
- Preparing vote operations (queued, broadcast later)
- Browsing cached content

What cannot work offline:
- Broadcasting any transaction
- Fetching new data from the chain
- Getting real-time notifications

Hmm, but there are some important considerations. Hive transactions have an expiration time (default 30 seconds, max 1 hour). If you pre-sign a transaction offline, it will expire before you can broadcast it. So you CANNOT pre-sign transactions offline.

Wait, this means the offline flow has to be: queue the INTENT (not the signed transaction), and when connectivity returns, construct and sign the transaction fresh and broadcast it. This requires having the signing key available at sync time.

I initially thought about storing signed transactions, but the expiration issue kills that approach. The alternative is to store the operation parameters and sign at broadcast time.

The tradeoff is: pre-signed (works with Keychain but expires quickly) vs intent-based (requires key at sync time but no expiration issue). For a mobile app where the user's key is stored in secure storage, intent-based works. For a web app relying on Keychain, the user needs to be present when the queue syncs.

Another consideration: order matters. If the user wrote a post offline and then voted on someone else's post, the post should be broadcast first because the vote might reference a permlink that does not exist yet.

For data caching, Service Workers (in web apps) or local database (in mobile apps) can store fetched blockchain data for offline access.
</think>

Use an intent queue with local storage for offline operation, and batch-sync when connectivity returns:

```python
# === Offline-First Architecture for Hive dApp ===

import json
import time
import os
import sqlite3
from datetime import datetime
from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Comment, Vote, Custom_json

# Local database for offline state
DB_PATH = "hive_offline.db"


class OfflineStore:
    """SQLite-based local store for offline data and pending operations."""

    def __init__(self, db_path=DB_PATH):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        self.conn.executescript("""
            -- Cached blockchain data for offline reading
            CREATE TABLE IF NOT EXISTS cached_posts (
                author TEXT,
                permlink TEXT,
                title TEXT,
                body TEXT,
                json_metadata TEXT,
                created_at TEXT,
                cached_at REAL,
                PRIMARY KEY (author, permlink)
            );

            CREATE TABLE IF NOT EXISTS cached_accounts (
                account TEXT PRIMARY KEY,
                data TEXT,
                cached_at REAL
            );

            -- Pending operations queue
            CREATE TABLE IF NOT EXISTS pending_ops (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                op_type TEXT NOT NULL,
                op_params TEXT NOT NULL,
                priority INTEGER DEFAULT 0,
                created_at REAL NOT NULL,
                status TEXT DEFAULT 'pending',
                error TEXT,
                tx_id TEXT
            );

            -- Sync log
            CREATE TABLE IF NOT EXISTS sync_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                synced_at REAL,
                ops_synced INTEGER,
                ops_failed INTEGER
            );
        """)
        self.conn.commit()


class OfflineOperationQueue:
    """Queue operations while offline, sync when connected."""

    # Operation priorities (lower number = broadcast first)
    PRIORITY_POST = 10      # posts first (others may reference them)
    PRIORITY_COMMENT = 20   # comments after posts
    PRIORITY_VOTE = 30      # votes last
    PRIORITY_CUSTOM = 25    # custom_json middle

    def __init__(self, store):
        self.store = store

    def queue_post(self, author, title, body, tags, community=""):
        """Queue a post for later broadcast."""
        permlink = self._generate_permlink(title)
        params = {
            "author": author,
            "permlink": permlink,
            "title": title,
            "body": body,
            "tags": tags,
            "community": community,
        }
        self.store.conn.execute(
            """INSERT INTO pending_ops (op_type, op_params, priority, created_at)
               VALUES (?, ?, ?, ?)""",
            ("post", json.dumps(params), self.PRIORITY_POST, time.time())
        )
        self.store.conn.commit()

        # Also save to local cache for offline reading
        self.store.conn.execute(
            """INSERT OR REPLACE INTO cached_posts
               (author, permlink, title, body, json_metadata, created_at, cached_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (author, permlink, title, body,
             json.dumps({"tags": tags}),
             datetime.utcnow().isoformat(), time.time())
        )
        self.store.conn.commit()
        return permlink

    def queue_vote(self, voter, author, permlink, weight=10000):
        """Queue a vote for later broadcast."""
        params = {
            "voter": voter,
            "author": author,
            "permlink": permlink,
            "weight": weight,
        }
        self.store.conn.execute(
            """INSERT INTO pending_ops (op_type, op_params, priority, created_at)
               VALUES (?, ?, ?, ?)""",
            ("vote", json.dumps(params), self.PRIORITY_VOTE, time.time())
        )
        self.store.conn.commit()

    def queue_custom_json(self, account, op_id, payload):
        """Queue a custom_json for later broadcast."""
        params = {
            "account": account,
            "id": op_id,
            "payload": payload,
        }
        self.store.conn.execute(
            """INSERT INTO pending_ops (op_type, op_params, priority, created_at)
               VALUES (?, ?, ?, ?)""",
            ("custom_json", json.dumps(params),
             self.PRIORITY_CUSTOM, time.time())
        )
        self.store.conn.commit()

    def get_pending_count(self):
        """Get number of pending operations."""
        row = self.store.conn.execute(
            "SELECT COUNT(*) FROM pending_ops WHERE status = 'pending'"
        ).fetchone()
        return row[0]

    def _generate_permlink(self, title):
        slug = title.lower()
        slug = "".join(c if c.isalnum() or c == " " else "" for c in slug)
        slug = slug.strip().replace(" ", "-")[:200]
        return f"{slug}-{int(time.time())}"


class SyncManager:
    """Sync pending operations when connectivity is restored."""

    def __init__(self, store, posting_key=None, active_key=None):
        self.store = store
        self.posting_key = posting_key
        self.active_key = active_key

    def is_online(self):
        """Check if we can reach a Hive API node."""
        import requests
        try:
            resp = requests.post(
                "https://api.hive.blog",
                json={"jsonrpc": "2.0", "method":
                      "condenser_api.get_dynamic_global_properties",
                      "params": [], "id": 1},
                timeout=5
            )
            return resp.status_code == 200
        except Exception:
            return False

    def sync(self):
        """Broadcast all pending operations in priority order."""
        if not self.is_online():
            print("Offline -- cannot sync")
            return {"synced": 0, "failed": 0}

        hive = Hive(
            node=["https://api.hive.blog", "https://api.deathwing.me"],
            keys=[k for k in [self.posting_key, self.active_key] if k]
        )

        # Get pending ops sorted by priority, then creation time
        rows = self.store.conn.execute(
            """SELECT id, op_type, op_params FROM pending_ops
               WHERE status = 'pending'
               ORDER BY priority ASC, created_at ASC"""
        ).fetchall()

        synced = 0
        failed = 0

        for row in rows:
            op_id = row["id"]
            op_type = row["op_type"]
            params = json.loads(row["op_params"])

            try:
                tx_id = self._broadcast_op(hive, op_type, params)
                self.store.conn.execute(
                    """UPDATE pending_ops SET status = 'synced', tx_id = ?
                       WHERE id = ?""",
                    (tx_id, op_id)
                )
                synced += 1
                print(f"Synced {op_type}: {tx_id}")
                time.sleep(3)  # wait for block
            except Exception as e:
                error_msg = str(e)
                # Check if it is a permanent error
                if "already voted" in error_msg.lower():
                    self.store.conn.execute(
                        "UPDATE pending_ops SET status = 'skipped', error = ? WHERE id = ?",
                        (error_msg, op_id)
                    )
                else:
                    self.store.conn.execute(
                        "UPDATE pending_ops SET status = 'failed', error = ? WHERE id = ?",
                        (error_msg, op_id)
                    )
                    failed += 1
                print(f"Failed {op_type}: {error_msg}")

        self.store.conn.commit()

        # Log sync result
        self.store.conn.execute(
            "INSERT INTO sync_log (synced_at, ops_synced, ops_failed) VALUES (?, ?, ?)",
            (time.time(), synced, failed)
        )
        self.store.conn.commit()

        return {"synced": synced, "failed": failed}

    def _broadcast_op(self, hive, op_type, params):
        """Construct and broadcast a single operation."""
        tx = TransactionBuilder(blockchain_instance=hive)

        if op_type == "post":
            tx.appendOps(Comment(**{
                "parent_author": "",
                "parent_permlink": params.get("community") or params["tags"][0],
                "author": params["author"],
                "permlink": params["permlink"],
                "title": params["title"],
                "body": params["body"],
                "json_metadata": json.dumps({
                    "tags": params["tags"],
                    "app": "myapp/1.0"
                })
            }))
            tx.appendSigner(params["author"], "posting")

        elif op_type == "vote":
            tx.appendOps(Vote(**{
                "voter": params["voter"],
                "author": params["author"],
                "permlink": params["permlink"],
                "weight": params["weight"]
            }))
            tx.appendSigner(params["voter"], "posting")

        elif op_type == "custom_json":
            tx.appendOps(Custom_json(**{
                "required_auths": [],
                "required_posting_auths": [params["account"]],
                "id": params["id"],
                "json": json.dumps(params["payload"])
            }))
            tx.appendSigner(params["account"], "posting")

        tx.sign()
        result = tx.broadcast()
        return result["id"]


# === Usage ===

store = OfflineStore()
queue = OfflineOperationQueue(store)
sync = SyncManager(store, posting_key="5YourPostingKey")

# While offline: queue operations
queue.queue_post("myuser", "My Offline Post",
                 "Written without internet!", ["hive-dev"])
queue.queue_vote("myuser", "author", "some-post", 10000)

print(f"Pending operations: {queue.get_pending_count()}")

# When connectivity returns
result = sync.sync()
print(f"Synced: {result['synced']}, Failed: {result['failed']}")
```

Key design decisions: operations are stored as intents (not signed transactions) because Hive transactions expire. Priority ordering ensures posts are broadcast before votes that might reference them. Idempotent error handling (e.g., "already voted" is skipped, not retried). Local SQLite cache enables reading previously fetched content offline. Sync is triggered explicitly -- never automatically with background sync that might surprise the user.'''
    },
    {
        "instruction": r'''My Hive dApp frontend needs to display markdown-rendered posts that include images, tables, and custom HTML. What rendering pipeline should I use?''',
        "output": r'''<think>
Hive post rendering -- posts are stored as Markdown on the blockchain but can contain raw HTML, images hosted on various services, and custom elements. This is a security-sensitive area because rendering arbitrary HTML can lead to XSS attacks.

Let me think about the rendering pipeline. The raw body from the blockchain needs to be:
1. Parsed as Markdown
2. Have images processed (proxied for privacy, lazy-loaded)
3. Have custom Hive elements handled (user mentions, post links)
4. Sanitized to remove dangerous HTML (script tags, event handlers)
5. Rendered to safe HTML

For a Python backend that pre-renders content:
- markdown or mistune library for Markdown parsing
- bleach for HTML sanitization
- Custom transformations for Hive-specific patterns

Hmm, but should rendering happen on the backend or frontend? If backend, I send rendered HTML to the frontend (simpler frontend, consistent rendering). If frontend, I send raw Markdown and the frontend renders it (more flexible, less backend work).

I initially thought frontend rendering would be better (less server load), but sanitization is critical for security and should not be trusted to the frontend. A compromised or modified frontend could skip sanitization. Backend rendering with sanitization is safer.

Wait, but many Hive frontends do render client-side. PeakD renders Markdown in the browser. The sanitization can happen client-side with libraries like DOMPurify. The tradeoff is: backend rendering (centralized security, more server load) vs client-side rendering (less server load, security depends on client library).

For a hybrid approach: backend strips known-dangerous elements and sends pre-sanitized Markdown. Frontend renders the sanitized Markdown. This gives two layers of protection.

Another consideration: Hive posts can be quite large (up to 64KB). Rendering should handle this efficiently. Also, images in posts can be from any domain, which raises privacy concerns (tracking pixels). Image proxying solves this.
</think>

Use a backend sanitization + rendering pipeline that handles Hive-specific patterns and security concerns:

```python
import re
import json
from urllib.parse import urlparse, quote
import bleach
import markdown
from markupsafe import Markup

# === Hive Post Rendering Pipeline ===


class HivePostRenderer:
    """Render Hive blockchain posts safely."""

    # Allowed HTML tags (after sanitization)
    ALLOWED_TAGS = [
        "h1", "h2", "h3", "h4", "h5", "h6",
        "p", "br", "hr",
        "strong", "em", "b", "i", "u", "s", "del",
        "a", "img",
        "ul", "ol", "li",
        "blockquote", "pre", "code",
        "table", "thead", "tbody", "tr", "th", "td",
        "div", "span", "center",
        "sub", "sup",
    ]

    ALLOWED_ATTRIBUTES = {
        "a": ["href", "title", "rel", "class"],
        "img": ["src", "alt", "title", "width", "height", "class"],
        "td": ["align"],
        "th": ["align"],
        "div": ["class"],
        "span": ["class"],
        "code": ["class"],  # for syntax highlighting
    }

    # Image proxy URL (protects user privacy)
    IMAGE_PROXY = "https://images.hive.blog/0x0/"

    def __init__(self, image_proxy=None, max_image_width=800):
        self.image_proxy = image_proxy or self.IMAGE_PROXY
        self.max_image_width = max_image_width
        self.md = markdown.Markdown(
            extensions=["tables", "fenced_code", "nl2br"]
        )

    def render(self, raw_body, author=None):
        """Full rendering pipeline for a Hive post body."""
        text = raw_body

        # Step 1: Pre-process Hive-specific patterns
        text = self._process_mentions(text)
        text = self._process_post_links(text)
        text = self._process_youtube(text)
        text = self._process_threespeak(text)

        # Step 2: Convert Markdown to HTML
        html = self.md.convert(text)
        self.md.reset()

        # Step 3: Sanitize HTML (remove dangerous elements)
        html = self._sanitize(html)

        # Step 4: Post-process (image proxy, lazy loading)
        html = self._proxy_images(html)
        html = self._add_lazy_loading(html)
        html = self._add_link_security(html)

        return html

    def _process_mentions(self, text):
        """Convert @username mentions to profile links."""
        def replace_mention(match):
            username = match.group(1)
            return f'<a href="/@{username}" class="mention">@{username}</a>'

        # Match @username but not email addresses
        return re.sub(
            r'(?<!\w)@([a-z][a-z0-9.-]{2,15})(?!\w)',
            replace_mention,
            text
        )

    def _process_post_links(self, text):
        """Convert Hive post URLs to proper links."""
        # Match various Hive frontend URLs
        hive_url_pattern = (
            r'https?://(?:hive\.blog|peakd\.com|ecency\.com)'
            r'(?:/[a-z0-9-]+)?/@([a-z][a-z0-9.-]+)/([a-z0-9-]+)'
        )

        def replace_link(match):
            author = match.group(1)
            permlink = match.group(2)
            url = f"/@{author}/{permlink}"
            return f'<a href="{url}" class="post-link">{match.group(0)}</a>'

        return re.sub(hive_url_pattern, replace_link, text)

    def _process_youtube(self, text):
        """Convert YouTube URLs to embedded players."""
        yt_pattern = (
            r'(?:https?://)?(?:www\.)?'
            r'(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})'
        )

        def replace_yt(match):
            video_id = match.group(1)
            return (
                f'<div class="video-embed">'
                f'<iframe src="https://www.youtube.com/embed/{video_id}" '
                f'frameborder="0" allowfullscreen loading="lazy"></iframe>'
                f'</div>'
            )

        return re.sub(yt_pattern, replace_yt, text)

    def _process_threespeak(self, text):
        """Handle 3Speak video embeds."""
        ts_pattern = r'https?://3speak\.tv/watch\?v=([a-z0-9.-]+)/([a-z0-9-]+)'

        def replace_ts(match):
            author = match.group(1)
            permlink = match.group(2)
            return (
                f'<div class="video-embed">'
                f'<iframe src="https://3speak.tv/embed?v={author}/{permlink}" '
                f'frameborder="0" allowfullscreen loading="lazy"></iframe>'
                f'</div>'
            )

        return re.sub(ts_pattern, replace_ts, text)

    def _sanitize(self, html):
        """Remove dangerous HTML while preserving safe elements."""
        return bleach.clean(
            html,
            tags=self.ALLOWED_TAGS,
            attributes=self.ALLOWED_ATTRIBUTES,
            protocols=["http", "https", "mailto"],
            strip=True  # strip disallowed tags instead of escaping
        )

    def _proxy_images(self, html):
        """Route images through a proxy for privacy and caching."""
        def proxy_src(match):
            original_src = match.group(1)
            # Do not proxy already-proxied images
            if original_src.startswith(self.image_proxy):
                return match.group(0)
            # Do not proxy data URIs
            if original_src.startswith("data:"):
                return match.group(0)
            proxied = f"{self.image_proxy}{quote(original_src, safe=':/')}"
            return f'src="{proxied}"'

        return re.sub(r'src="([^"]+)"', proxy_src, html)

    def _add_lazy_loading(self, html):
        """Add lazy loading to images."""
        return html.replace("<img ", '<img loading="lazy" ')

    def _add_link_security(self, html):
        """Add rel="noopener nofollow" to external links."""
        def secure_link(match):
            href = match.group(1)
            parsed = urlparse(href)
            if parsed.scheme in ("http", "https") and parsed.netloc:
                return (f'href="{href}" rel="noopener nofollow" '
                        f'target="_blank"')
            return match.group(0)

        return re.sub(r'href="([^"]+)"', secure_link, html)


# === Usage ===

renderer = HivePostRenderer()

raw_post = """# My Hive Post

Hello @username! Check out this post on https://peakd.com/@author/cool-post

Here is an image:
![My Photo](https://example.com/photo.jpg)

And a YouTube video:
https://www.youtube.com/watch?v=dQw4w9WgXcQ

| Column A | Column B |
|----------|----------|
| Data 1   | Data 2   |

```python
print("Hello Hive!")
```
"""

safe_html = renderer.render(raw_post)
print(safe_html)
```

Pipeline summary: pre-process Hive-specific patterns (mentions, post links, video embeds), convert Markdown to HTML, sanitize with bleach (whitelist approach -- only allow known-safe tags and attributes), proxy images through a privacy-preserving CDN, add lazy loading and link security attributes. This prevents XSS while supporting the rich content Hive posts commonly use.'''
    },
]
