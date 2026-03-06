"""Hive blockchain training pairs: performance optimization."""

PAIRS = [
    (
        "hive/batch-api-calls",
        r'''How do I batch multiple API calls to the Hive blockchain for better performance?''',
        r'''Batching API calls reduces network round trips and significantly improves throughput. Here is how to implement efficient batching:

```python
import requests
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

API_NODE = "https://api.hive.blog"

def batch_rpc_call(calls, node=API_NODE, timeout=15):
    """Send multiple JSON-RPC calls in a single HTTP request.

    Hive API nodes support JSON-RPC batch requests (array of calls).
    """
    batch = []
    for i, (method, params) in enumerate(calls):
        batch.append({
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": i + 1
        })

    resp = requests.post(node, json=batch, timeout=timeout)
    resp.raise_for_status()
    results = resp.json()

    # Sort results by id to match input order
    if isinstance(results, list):
        results.sort(key=lambda x: x.get("id", 0))
        return [r.get("result") for r in results]
    return [results.get("result")]

# Example: Get multiple accounts in one call
def get_accounts_batch(account_names):
    """Get multiple accounts efficiently."""
    # condenser_api.get_accounts already accepts a list
    resp = requests.post(API_NODE, json={
        "jsonrpc": "2.0",
        "method": "condenser_api.get_accounts",
        "params": [account_names],
        "id": 1
    }, timeout=15)
    return resp.json().get("result", [])

# Example: Get multiple blocks in parallel
def get_blocks_parallel(block_numbers, max_workers=5):
    """Fetch multiple blocks in parallel."""
    calls = [
        ("block_api.get_block", {"block_num": bn})
        for bn in block_numbers
    ]

    # Split into batches of 50
    batch_size = 50
    all_results = []

    for i in range(0, len(calls), batch_size):
        chunk = calls[i:i + batch_size]
        results = batch_rpc_call(chunk)
        all_results.extend(results)

    return all_results

# Example: Batch account + RC + delegation queries
def get_full_account_info(account_names):
    """Get comprehensive info for multiple accounts in minimal calls."""
    calls = [
        # Get accounts
        ("condenser_api.get_accounts", [account_names]),
        # Get RC for all accounts
        ("rc_api.find_rc_accounts", {"accounts": account_names}),
        # Get global properties (shared context)
        ("condenser_api.get_dynamic_global_properties", []),
    ]

    # Add delegation queries for each account
    for name in account_names:
        calls.append((
            "database_api.find_vesting_delegations",
            {"account": name}
        ))

    results = batch_rpc_call(calls)

    accounts = results[0] if results[0] else []
    rc_data = results[1].get("rc_accounts", []) if results[1] else []
    props = results[2] if results[2] else {}

    # Merge data
    merged = {}
    for acct in accounts:
        name = acct["name"]
        merged[name] = {
            "account": acct,
            "props": props
        }

    for rc in rc_data:
        name = rc["account"]
        if name in merged:
            merged[name]["rc"] = rc

    # Add delegation data
    for i, name in enumerate(account_names):
        deleg_idx = 3 + i
        if deleg_idx < len(results) and results[deleg_idx]:
            merged.setdefault(name, {})["delegations"] = (
                results[deleg_idx].get("delegations", [])
            )

    return merged

# Performance comparison
def benchmark():
    accounts = ["blocktrades", "hiveio", "smooth", "gtg", "arcange"]

    # Sequential approach
    start = time.time()
    for name in accounts:
        requests.post(API_NODE, json={
            "jsonrpc": "2.0",
            "method": "condenser_api.get_accounts",
            "params": [[name]], "id": 1
        }, timeout=10)
    sequential_time = time.time() - start

    # Batched approach
    start = time.time()
    get_accounts_batch(accounts)
    batch_time = time.time() - start

    print(f"Sequential ({len(accounts)} calls): {sequential_time:.3f}s")
    print(f"Batched (1 call):                   {batch_time:.3f}s")
    print(f"Speedup: {sequential_time / batch_time:.1f}x")

# benchmark()
# info = get_full_account_info(["blocktrades", "hiveio"])
```

Batching reduces latency from N round trips to 1 round trip. For the best performance, combine batching with connection pooling and use multiple API nodes with client-side load balancing. Most Hive API nodes support batch requests up to 50-100 calls per batch.
'''
    ),
    (
        "hive/connection-pooling",
        r'''How do I implement connection pooling for Hive API calls in a production dApp?''',
        r'''Connection pooling with persistent HTTP sessions dramatically reduces overhead for repeated API calls. Here is a production-ready implementation:

```python
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import json
import time
import threading
from collections import deque

class HiveConnectionPool:
    """High-performance connection pool for Hive API nodes."""

    def __init__(self, nodes, pool_size=10, max_retries=3):
        self.nodes = nodes
        self.node_index = 0
        self.lock = threading.Lock()

        # Create a session with connection pooling
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"]
        )
        adapter = HTTPAdapter(
            pool_connections=pool_size,
            pool_maxsize=pool_size,
            max_retries=retry_strategy
        )
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update({
            "Content-Type": "application/json",
            "Connection": "keep-alive"
        })

        # Track node performance
        self.node_latency = {node: deque(maxlen=100) for node in nodes}
        self.node_errors = {node: 0 for node in nodes}

    def _get_best_node(self):
        """Get the node with lowest average latency."""
        with self.lock:
            best_node = self.nodes[0]
            best_avg = float("inf")

            for node in self.nodes:
                if self.node_errors[node] > 10:
                    continue  # Skip unhealthy nodes
                latencies = self.node_latency[node]
                if latencies:
                    avg = sum(latencies) / len(latencies)
                    if avg < best_avg:
                        best_avg = avg
                        best_node = node

            return best_node

    def call(self, method, params=None, timeout=10):
        """Make an API call with automatic node selection."""
        node = self._get_best_node()
        payload = json.dumps({
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": 1
        })

        start = time.time()
        try:
            resp = self.session.post(node, data=payload, timeout=timeout)
            latency = time.time() - start
            self.node_latency[node].append(latency)
            self.node_errors[node] = max(0, self.node_errors[node] - 1)

            data = resp.json()
            if "error" in data:
                raise Exception(f"RPC error: {data['error']}")
            return data.get("result")

        except Exception as e:
            self.node_errors[node] = self.node_errors.get(node, 0) + 1
            # Try next node
            for fallback in self.nodes:
                if fallback != node:
                    try:
                        resp = self.session.post(
                            fallback, data=payload, timeout=timeout
                        )
                        return resp.json().get("result")
                    except Exception:
                        continue
            raise

    def batch_call(self, calls, timeout=15):
        """Batch multiple calls in one request."""
        node = self._get_best_node()
        batch = [
            {"jsonrpc": "2.0", "method": m, "params": p, "id": i+1}
            for i, (m, p) in enumerate(calls)
        ]
        resp = self.session.post(
            node, json=batch, timeout=timeout
        )
        results = resp.json()
        if isinstance(results, list):
            results.sort(key=lambda x: x.get("id", 0))
            return [r.get("result") for r in results]
        return [results.get("result")]

    def get_stats(self):
        """Get connection pool statistics."""
        stats = {}
        for node in self.nodes:
            latencies = self.node_latency[node]
            stats[node] = {
                "avg_latency_ms": (sum(latencies) / len(latencies) * 1000
                                   if latencies else 0),
                "requests": len(latencies),
                "errors": self.node_errors[node]
            }
        return stats

# Thread-safe global pool
_pool = None

def get_pool():
    global _pool
    if _pool is None:
        _pool = HiveConnectionPool([
            "https://api.hive.blog",
            "https://api.deathwing.me",
            "https://api.openhive.network"
        ])
    return _pool

# Usage
pool = get_pool()
props = pool.call("condenser_api.get_dynamic_global_properties")
accounts = pool.call("condenser_api.get_accounts", [["hiveio"]])

# Batch calls
results = pool.batch_call([
    ("condenser_api.get_accounts", [["alice", "bob"]]),
    ("condenser_api.get_dynamic_global_properties", []),
])

print("Pool stats:", json.dumps(pool.get_stats(), indent=2))
```

Connection pooling with keep-alive connections avoids TCP handshake and TLS negotiation overhead on every request. Combined with automatic node selection based on latency, this provides both performance and reliability for production dApps.
'''
    ),
    (
        "hive/caching-strategies",
        r'''What caching strategies should I use for Hive blockchain data in my dApp?''',
        r'''Caching Hive data requires understanding what changes and how often. Here is a tiered caching strategy:

```python
import time
import json
import hashlib
from functools import wraps
from collections import OrderedDict

class HiveCache:
    """Multi-tier cache for Hive blockchain data."""

    def __init__(self, max_items=10000):
        self.cache = OrderedDict()
        self.max_items = max_items
        self.hits = 0
        self.misses = 0

    def get(self, key):
        if key in self.cache:
            entry = self.cache[key]
            if time.time() < entry["expires"]:
                self.hits += 1
                self.cache.move_to_end(key)
                return entry["value"]
            else:
                del self.cache[key]
        self.misses += 1
        return None

    def set(self, key, value, ttl):
        if len(self.cache) >= self.max_items:
            self.cache.popitem(last=False)
        self.cache[key] = {
            "value": value,
            "expires": time.time() + ttl
        }

    def hit_rate(self):
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0

# TTL configuration based on data volatility
CACHE_TTLS = {
    # Static data (rarely changes)
    "chain_config": 86400,        # 24 hours
    "account_keys": 3600,         # 1 hour
    "witness_list": 300,          # 5 minutes

    # Semi-dynamic data
    "account_info": 30,           # 30 seconds
    "account_balance": 10,        # 10 seconds
    "global_props": 3,            # 3 seconds (1 block)
    "rc_info": 15,                # 15 seconds

    # Dynamic data (short TTL or no cache)
    "head_block": 1,              # 1 second
    "pending_transactions": 0,    # Never cache
    "vote_state": 3,              # 3 seconds
}

class CachedHiveClient:
    """Hive API client with intelligent caching."""

    def __init__(self, pool):
        self.pool = pool
        self.cache = HiveCache(max_items=50000)

    def _cache_key(self, method, params):
        """Generate a deterministic cache key."""
        key_str = f"{method}:{json.dumps(params, sort_keys=True)}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def call(self, method, params=None, ttl=None):
        """API call with caching."""
        if ttl is None:
            # Auto-determine TTL based on method
            for pattern, default_ttl in CACHE_TTLS.items():
                if pattern in method:
                    ttl = default_ttl
                    break
            else:
                ttl = 5  # Default 5 seconds

        if ttl <= 0:
            return self.pool.call(method, params)

        key = self._cache_key(method, params)
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        result = self.pool.call(method, params)
        self.cache.set(key, result, ttl)
        return result

    def get_account(self, name):
        """Get account with appropriate caching."""
        return self.call(
            "condenser_api.get_accounts",
            [[name]],
            ttl=CACHE_TTLS["account_info"]
        )

    def get_global_props(self):
        """Get global properties (cached per block)."""
        return self.call(
            "condenser_api.get_dynamic_global_properties",
            [],
            ttl=CACHE_TTLS["global_props"]
        )

    def get_rc(self, account):
        """Get RC info with short cache."""
        return self.call(
            "rc_api.find_rc_accounts",
            {"accounts": [account]},
            ttl=CACHE_TTLS["rc_info"]
        )

    def invalidate(self, method=None, params=None):
        """Invalidate cache entries."""
        if method and params:
            key = self._cache_key(method, params)
            if key in self.cache.cache:
                del self.cache.cache[key]
        elif method is None:
            self.cache.cache.clear()

    def stats(self):
        """Get cache performance statistics."""
        return {
            "hit_rate": f"{self.cache.hit_rate():.1f}%",
            "hits": self.cache.hits,
            "misses": self.cache.misses,
            "entries": len(self.cache.cache)
        }

# Usage with decorator pattern for custom functions
def cached(ttl=30):
    """Decorator to cache function results."""
    _cache = {}

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = f"{func.__name__}:{args}:{kwargs}"
            now = time.time()
            if key in _cache and now < _cache[key]["expires"]:
                return _cache[key]["value"]
            result = func(*args, **kwargs)
            _cache[key] = {"value": result, "expires": now + ttl}
            return result
        return wrapper
    return decorator

@cached(ttl=60)
def get_top_witnesses(limit=21):
    """Get top witnesses (cached for 60 seconds)."""
    # pool.call(...)
    pass

# client = CachedHiveClient(pool)
# account = client.get_account("hiveio")
# print(client.stats())
```

Key caching rules for Hive data: global properties change every 3 seconds (1 block), account balances can change any block, RC regenerates continuously, and chain configuration rarely changes. Cache aggressively for read-heavy operations but always serve fresh data for financial operations.
'''
    ),
    (
        "hive/efficient-account-lookups",
        r'''How do I efficiently look up large numbers of Hive accounts for analytics or batch processing?''',
        r'''Looking up thousands of accounts requires careful batching and parallelization. Here is an optimized approach:

```python
import requests
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import islice

API_NODES = [
    "https://api.hive.blog",
    "https://api.deathwing.me",
    "https://api.openhive.network"
]

def chunk_list(lst, size):
    """Split a list into chunks of given size."""
    for i in range(0, len(lst), size):
        yield lst[i:i + size]

def get_accounts_batch(names, node=None):
    """Get multiple accounts in a single API call.

    condenser_api.get_accounts accepts up to ~1000 names.
    """
    node = node or API_NODES[0]
    resp = requests.post(node, json={
        "jsonrpc": "2.0",
        "method": "condenser_api.get_accounts",
        "params": [names],
        "id": 1
    }, timeout=30)
    return resp.json().get("result", [])

def get_accounts_parallel(all_names, batch_size=100, max_workers=5):
    """Look up thousands of accounts in parallel batches."""
    results = []
    total = len(all_names)
    processed = 0
    start = time.time()

    chunks = list(chunk_list(all_names, batch_size))

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        # Distribute chunks across nodes
        futures = {}
        for i, chunk in enumerate(chunks):
            node = API_NODES[i % len(API_NODES)]
            future = pool.submit(get_accounts_batch, chunk, node)
            futures[future] = chunk

        for future in as_completed(futures):
            try:
                accounts = future.result()
                results.extend(accounts)
                processed += len(futures[future])
                elapsed = time.time() - start
                rate = processed / elapsed if elapsed > 0 else 0
                if processed % 1000 == 0:
                    print(f"  {processed}/{total} accounts "
                          f"({rate:.0f}/sec)")
            except Exception as e:
                print(f"  Batch error: {e}")

    elapsed = time.time() - start
    print(f"Fetched {len(results)} accounts in {elapsed:.1f}s "
          f"({len(results)/elapsed:.0f}/sec)")
    return results

def lookup_accounts_by_prefix(prefix, limit=1000):
    """Find accounts starting with a prefix (for search/autocomplete)."""
    resp = requests.post(API_NODES[0], json={
        "jsonrpc": "2.0",
        "method": "condenser_api.lookup_accounts",
        "params": [prefix, limit],
        "id": 1
    }, timeout=15)
    names = resp.json().get("result", [])
    return names

def paginate_all_accounts(callback, batch_size=1000):
    """Iterate through ALL accounts on Hive."""
    last_account = ""
    total = 0

    while True:
        names = lookup_accounts_by_prefix(last_account, batch_size)
        if not names:
            break

        # Remove the first result if it matches last_account (overlap)
        if names[0] == last_account:
            names = names[1:]
        if not names:
            break

        # Fetch full account data
        accounts = get_accounts_batch(names)
        for acct in accounts:
            callback(acct)

        total += len(accounts)
        last_account = names[-1]
        print(f"  Processed {total} accounts (last: @{last_account})")

    print(f"Total accounts processed: {total}")

# Extract specific fields for analytics
def extract_account_metrics(accounts):
    """Extract key metrics from account data for analysis."""
    metrics = []
    for acct in accounts:
        vests = float(str(acct.get("vesting_shares", "0")).split()[0])
        balance = float(str(acct.get("balance", "0")).split()[0])
        hbd = float(str(acct.get("hbd_balance", "0")).split()[0])

        metrics.append({
            "name": acct["name"],
            "vests": vests,
            "balance_hive": balance,
            "balance_hbd": hbd,
            "post_count": acct.get("post_count", 0),
            "created": acct.get("created", ""),
            "last_post": acct.get("last_post", ""),
            "reputation": acct.get("reputation", 0),
        })
    return metrics

# Usage: Look up 5000 accounts efficiently
# names = ["user" + str(i) for i in range(5000)]
# accounts = get_accounts_parallel(names, batch_size=100, max_workers=5)

# Search accounts by prefix
# matches = lookup_accounts_by_prefix("dan", limit=20)
# print(f"Accounts starting with 'dan': {matches}")
```

Performance tips for bulk lookups: batch names in groups of 100 (API limit varies by node), distribute batches across multiple API nodes, use thread pools for parallelism, and extract only the fields you need to reduce memory usage. For full-chain analytics, consider using a HAF database instead of API calls.
'''
    ),
    (
        "hive/pagination-patterns",
        r'''How do I implement efficient pagination when querying Hive blockchain data?''',
        r'''Pagination on Hive differs by API method. Some use offset-based pagination, others use cursor-based (last-item) pagination. Here are the correct patterns:

```python
import requests
import json

API_NODE = "https://api.hive.blog"

def rpc(method, params):
    resp = requests.post(API_NODE, json={
        "jsonrpc": "2.0", "method": method,
        "params": params, "id": 1
    }, timeout=15)
    return resp.json().get("result")

# Pattern 1: Account history pagination (cursor-based)
def paginate_account_history(account, op_types=None, batch_size=1000):
    """Paginate through all account history.

    account_history uses descending index (newest first).
    Start with -1 (latest) and work backwards.
    """
    all_ops = []
    start_index = -1  # -1 means latest

    while True:
        history = rpc("condenser_api.get_account_history", [
            account, start_index, min(batch_size, 1000)
        ])

        if not history:
            break

        for entry in history:
            idx = entry[0]
            op = entry[1]
            op_type = op["op"][0] if isinstance(op["op"], list) else op["op"]["type"]

            if op_types is None or op_type in op_types:
                all_ops.append({
                    "index": idx,
                    "block": op.get("block"),
                    "timestamp": op.get("timestamp"),
                    "type": op_type,
                    "data": op["op"][1] if isinstance(op["op"], list) else op["op"]
                })

        # Move cursor to before the oldest entry we received
        oldest_index = history[0][0]
        if oldest_index <= 0 or len(history) < batch_size:
            break
        start_index = oldest_index - 1

        print(f"  Fetched {len(all_ops)} ops (index: {oldest_index})")

    return all_ops

# Pattern 2: Bridge posts pagination (cursor-based)
def paginate_posts(sort="created", tag="", limit=100):
    """Paginate through ranked posts using bridge API."""
    all_posts = []
    last_author = ""
    last_permlink = ""

    while len(all_posts) < limit:
        batch_size = min(20, limit - len(all_posts))

        params = {
            "sort": sort,
            "tag": tag,
            "limit": batch_size,
            "observer": ""
        }

        # For subsequent pages, use the last post as cursor
        if last_author and last_permlink:
            params["start_author"] = last_author
            params["start_permlink"] = last_permlink

        result = rpc("bridge.get_ranked_posts", params)

        if not result:
            break

        # Skip the first result on subsequent pages (it is the cursor)
        start_idx = 1 if last_author else 0
        new_posts = result[start_idx:]

        if not new_posts:
            break

        all_posts.extend(new_posts)
        last_author = new_posts[-1]["author"]
        last_permlink = new_posts[-1]["permlink"]

        print(f"  Page: {len(all_posts)} posts fetched")

    return all_posts[:limit]

# Pattern 3: Witness list pagination
def paginate_witnesses(limit=200):
    """Paginate through all witnesses."""
    all_witnesses = []
    last_name = ""

    while len(all_witnesses) < limit:
        batch = min(100, limit - len(all_witnesses))
        result = rpc("database_api.list_witnesses", {
            "start": last_name if last_name else "",
            "limit": batch,
            "order": "by_name"
        })

        witnesses = result.get("witnesses", [])
        if not witnesses:
            break

        # Skip first if it is the cursor
        if last_name and witnesses[0]["owner"] == last_name:
            witnesses = witnesses[1:]

        all_witnesses.extend(witnesses)
        if witnesses:
            last_name = witnesses[-1]["owner"]
        else:
            break

    return all_witnesses[:limit]

# Pattern 4: Community subscribers pagination
def paginate_subscribers(community, limit=500):
    """Paginate through community subscribers."""
    all_subs = []
    last_account = ""

    while len(all_subs) < limit:
        result = rpc("bridge.list_subscribers", {
            "community": community,
            "last": last_account,
            "limit": 100
        })

        if not result:
            break

        all_subs.extend(result)
        last_account = result[-1][0] if result else ""

        if len(result) < 100:
            break

    return all_subs[:limit]

# Usage
# history = paginate_account_history("blocktrades", op_types=["transfer"], batch_size=500)
# posts = paginate_posts(sort="trending", tag="hive-dev", limit=50)
# witnesses = paginate_witnesses(limit=100)
# subs = paginate_subscribers("hive-163521", limit=200)
```

Key pagination rules on Hive:
- Account history: Use descending index, start at -1 for latest
- Bridge posts: Use start_author/start_permlink as cursor
- Database API lists: Use the last item's key as the start parameter
- Always handle the overlap (cursor item appears in both pages)
- Batch sizes vary by endpoint; 1000 for account_history, 20 for bridge posts
'''
    ),
]
