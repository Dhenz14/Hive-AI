"""Documentation generation training pairs: meaningful inline comments for complex code."""

pairs = [
    {
        "instruction": r'''Add meaningful inline comments to this rate limiter implementation. Don't comment obvious things -- focus on the WHY, not the WHAT.

class SlidingWindowRateLimiter:
    def __init__(self, redis_client, max_requests, window_seconds):
        self.redis = redis_client
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    def is_allowed(self, key):
        now = time.time()
        window_start = now - self.window_seconds
        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, self.window_seconds)
        results = pipe.execute()
        current_count = results[2]
        return current_count <= self.max_requests

    def get_remaining(self, key):
        now = time.time()
        window_start = now - self.window_seconds
        self.redis.zremrangebyscore(key, 0, window_start)
        count = self.redis.zcard(key)
        return max(0, self.max_requests - count)

    def get_retry_after(self, key):
        oldest = self.redis.zrange(key, 0, 0, withscores=True)
        if not oldest:
            return 0
        oldest_score = oldest[0][1]
        retry_after = oldest_score + self.window_seconds - time.time()
        return max(0, retry_after)''',
        "output": r'''```python
class SlidingWindowRateLimiter:
    def __init__(self, redis_client, max_requests, window_seconds):
        self.redis = redis_client
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    def is_allowed(self, key):
        now = time.time()
        window_start = now - self.window_seconds

        # Use a pipeline to make the check-and-increment atomic.
        # Without pipelining, a burst of concurrent requests could
        # all read the count before any of them increment it.
        pipe = self.redis.pipeline()

        # Sorted set stores one member per request, scored by timestamp.
        # Remove all entries older than the window -- they no longer count.
        pipe.zremrangebyscore(key, 0, window_start)

        # Add this request. Using str(now) as the member means two requests
        # at the exact same timestamp would merge into one entry. In practice
        # time.time() has enough precision that collisions are negligible,
        # and a collision only makes the limiter slightly more permissive.
        pipe.zadd(key, {str(now): now})

        # Count how many requests fall within the current window
        pipe.zcard(key)

        # Auto-expire the key so we don't leak memory for inactive clients.
        # The TTL equals the window size -- after that, the key is irrelevant.
        pipe.expire(key, self.window_seconds)

        results = pipe.execute()
        current_count = results[2]

        # Use <= because we already added the current request to the set.
        # If count == max_requests, this request is the last allowed one.
        return current_count <= self.max_requests

    def get_remaining(self, key):
        now = time.time()
        window_start = now - self.window_seconds
        # Clean up expired entries first so the count is accurate
        self.redis.zremrangebyscore(key, 0, window_start)
        count = self.redis.zcard(key)
        return max(0, self.max_requests - count)

    def get_retry_after(self, key):
        # The oldest entry in the set is the first one that will expire.
        # Once it expires, one slot opens up. So retry_after = when that
        # entry falls outside the window.
        oldest = self.redis.zrange(key, 0, 0, withscores=True)
        if not oldest:
            return 0
        oldest_score = oldest[0][1]
        retry_after = oldest_score + self.window_seconds - time.time()
        return max(0, retry_after)
```'''
    },
    {
        "instruction": r'''Add inline comments explaining the non-obvious parts of this consensus algorithm implementation:

class RaftNode:
    def __init__(self, node_id, peers):
        self.id = node_id
        self.peers = peers
        self.state = "follower"
        self.current_term = 0
        self.voted_for = None
        self.log = []
        self.commit_index = -1
        self.last_applied = -1
        self.leader_id = None
        self.votes_received = set()
        self.next_index = {}
        self.match_index = {}

    def start_election(self):
        self.state = "candidate"
        self.current_term += 1
        self.voted_for = self.id
        self.votes_received = {self.id}

        last_log_index = len(self.log) - 1
        last_log_term = self.log[-1]["term"] if self.log else 0

        for peer in self.peers:
            self.send_request_vote(peer, self.current_term,
                                   last_log_index, last_log_term)

    def handle_vote_response(self, term, granted):
        if term > self.current_term:
            self.current_term = term
            self.state = "follower"
            self.voted_for = None
            return

        if self.state != "candidate":
            return

        if granted:
            self.votes_received.add(term)
            if len(self.votes_received) > len(self.peers) // 2:
                self.become_leader()

    def become_leader(self):
        self.state = "leader"
        self.leader_id = self.id
        for peer in self.peers:
            self.next_index[peer] = len(self.log)
            self.match_index[peer] = -1
        self.send_heartbeats()''',
        "output": r'''<think>
Simplified Raft consensus. I should focus on the WHY: term increments for vote freshness, log comparison for election restriction, step-down on higher term, and proactive leader state initialization.
</think>

```python
class RaftNode:
    def __init__(self, node_id, peers):
        self.id = node_id
        self.peers = peers
        self.state = "follower"
        self.current_term = 0
        self.voted_for = None
        self.log = []
        # Separate from commit_index: "committed" = replicated to majority,
        # "applied" = processed by state machine. Application can lag.
        self.commit_index = -1
        self.last_applied = -1
        self.leader_id = None
        self.votes_received = set()
        self.next_index = {}   # leader-only: next log entry to send per peer
        self.match_index = {}  # leader-only: highest replicated entry per peer

    def start_election(self):
        self.state = "candidate"
        # New term invalidates stale vote responses from previous elections
        self.current_term += 1
        # Vote for self; also prevents voting for another candidate this term
        self.voted_for = self.id
        self.votes_received = {self.id}

        last_log_index = len(self.log) - 1
        # Voters compare log freshness to enforce the "election restriction":
        # a candidate with a stale log cannot win, ensuring the leader
        # always has all committed entries
        last_log_term = self.log[-1]["term"] if self.log else 0

        for peer in self.peers:
            self.send_request_vote(peer, self.current_term,
                                   last_log_index, last_log_term)

    def handle_vote_response(self, term, granted):
        # Higher term in any RPC -> step down (Raft safety invariant)
        if term > self.current_term:
            self.current_term = term
            self.state = "follower"
            self.voted_for = None
            return

        # Ignore late votes if we already won or stepped down
        if self.state != "candidate":
            return

        if granted:
            self.votes_received.add(term)
            # Majority quorum: > half of all nodes (including self)
            if len(self.votes_received) > len(self.peers) // 2:
                self.become_leader()

    def become_leader(self):
        self.state = "leader"
        self.leader_id = self.id
        for peer in self.peers:
            # Optimistic: assume peer is caught up. Decremented on
            # AppendEntries failure until the actual match point is found.
            self.next_index[peer] = len(self.log)
            self.match_index[peer] = -1
        # Must send immediately to prevent election timeout on other nodes
        self.send_heartbeats()
```'''
    },
    {
        "instruction": r'''Add comments to this bloom filter explaining the math and design choices:

class BloomFilter:
    def __init__(self, expected_items, false_positive_rate=0.01):
        self.size = self._optimal_size(expected_items, false_positive_rate)
        self.hash_count = self._optimal_hashes(self.size, expected_items)
        self.bit_array = bytearray(self.size // 8 + 1)
        self.count = 0

    def _optimal_size(self, n, p):
        return int(-n * math.log(p) / (math.log(2) ** 2))

    def _optimal_hashes(self, m, n):
        return max(1, int(m / n * math.log(2)))

    def _get_hashes(self, item):
        h1 = mmh3.hash(item, 0) % self.size
        h2 = mmh3.hash(item, 1) % self.size
        return [(h1 + i * h2) % self.size for i in range(self.hash_count)]

    def add(self, item):
        for pos in self._get_hashes(item):
            self.bit_array[pos // 8] |= (1 << (pos % 8))
        self.count += 1

    def might_contain(self, item):
        return all(
            self.bit_array[pos // 8] & (1 << (pos % 8))
            for pos in self._get_hashes(item)
        )''',
        "output": r'''```python
class BloomFilter:
    def __init__(self, expected_items, false_positive_rate=0.01):
        self.size = self._optimal_size(expected_items, false_positive_rate)
        self.hash_count = self._optimal_hashes(self.size, expected_items)
        # Store bits packed into bytes. +1 handles the case where
        # size is not evenly divisible by 8.
        self.bit_array = bytearray(self.size // 8 + 1)
        self.count = 0

    def _optimal_size(self, n, p):
        # Derives from the formula: m = -(n * ln(p)) / (ln(2))^2
        # where m = bit array size, n = expected items, p = target FP rate.
        # For 1M items at 1% FP rate, this gives ~9.6M bits (~1.2 MB).
        return int(-n * math.log(p) / (math.log(2) ** 2))

    def _optimal_hashes(self, m, n):
        # k = (m/n) * ln(2) minimizes the false positive probability
        # for a given bit array size and item count. Typically yields
        # 7 hash functions for a 1% FP rate.
        return max(1, int(m / n * math.log(2)))

    def _get_hashes(self, item):
        # Kirsch-Mitzenmacker optimization: instead of computing k
        # independent hash functions, use two hashes (h1, h2) and
        # derive the rest as h1 + i*h2. This is provably equivalent
        # in false positive rate but much cheaper to compute.
        h1 = mmh3.hash(item, 0) % self.size
        h2 = mmh3.hash(item, 1) % self.size
        return [(h1 + i * h2) % self.size for i in range(self.hash_count)]

    def add(self, item):
        for pos in self._get_hashes(item):
            # Set the bit at position pos. We pack 8 bits per byte,
            # so byte index = pos // 8, bit offset = pos % 8.
            self.bit_array[pos // 8] |= (1 << (pos % 8))
        self.count += 1

    def might_contain(self, item):
        # "might_contain" (not "contains") because bloom filters
        # can return false positives but never false negatives.
        # If ANY bit is unset, the item was definitely not added.
        return all(
            self.bit_array[pos // 8] & (1 << (pos % 8))
            for pos in self._get_hashes(item)
        )
```'''
    },
    {
        "instruction": r'''Comment this B-tree node splitting implementation. Focus on the invariants being maintained.

class BTreeNode:
    def __init__(self, order, leaf=True):
        self.order = order
        self.leaf = leaf
        self.keys = []
        self.children = []

    def split(self):
        mid = len(self.keys) // 2
        median_key = self.keys[mid]

        right = BTreeNode(self.order, self.leaf)
        right.keys = self.keys[mid + 1:]

        if not self.leaf:
            right.children = self.children[mid + 1:]

        self.keys = self.keys[:mid]

        if not self.leaf:
            self.children = self.children[:mid + 1]

        return median_key, right

    def insert_non_full(self, key):
        i = len(self.keys) - 1

        if self.leaf:
            self.keys.append(None)
            while i >= 0 and key < self.keys[i]:
                self.keys[i + 1] = self.keys[i]
                i -= 1
            self.keys[i + 1] = key
        else:
            while i >= 0 and key < self.keys[i]:
                i -= 1
            i += 1

            if len(self.children[i].keys) == 2 * self.order - 1:
                median, new_child = self.children[i].split()
                self.keys.insert(i, median)
                self.children.insert(i + 1, new_child)
                if key > median:
                    i += 1

            self.children[i].insert_non_full(key)''',
        "output": r'''<think>
B-tree splitting maintains several invariants:
1. Each node (except root) has between ceil(order/2)-1 and order-1 keys
2. Internal nodes with k keys have k+1 children
3. All leaves are at the same depth
4. Keys within a node are sorted

The split operation divides a full node, promotes the median key to the parent, and preserves the children-to-keys relationship. I should comment on these invariants rather than restating what each line does.
</think>

```python
class BTreeNode:
    def __init__(self, order, leaf=True):
        self.order = order
        self.leaf = leaf
        self.keys = []
        self.children = []

    def split(self):
        # Split a full node into two half-full nodes, returning the
        # median key to be promoted into the parent.
        # INVARIANT: after split, both halves have >= ceil(order/2)-1 keys,
        # satisfying the minimum occupancy requirement.
        mid = len(self.keys) // 2
        median_key = self.keys[mid]

        # Right sibling gets keys after median. Median itself moves up
        # to parent -- it is NOT kept in either child node.
        right = BTreeNode(self.order, self.leaf)
        right.keys = self.keys[mid + 1:]

        if not self.leaf:
            # Partition children so each node keeps len(keys)+1 children
            right.children = self.children[mid + 1:]

        self.keys = self.keys[:mid]

        if not self.leaf:
            self.children = self.children[:mid + 1]

        return median_key, right

    def insert_non_full(self, key):
        # PRECONDITION: this node is guaranteed not full. The caller
        # (parent or root handler) splits full nodes before descending.
        i = len(self.keys) - 1

        if self.leaf:
            # Insertion sort: shift keys right to maintain sorted order
            self.keys.append(None)
            while i >= 0 and key < self.keys[i]:
                self.keys[i + 1] = self.keys[i]
                i -= 1
            self.keys[i + 1] = key
        else:
            while i >= 0 and key < self.keys[i]:
                i -= 1
            i += 1  # i = index of child subtree where key belongs

            # Proactive split: split child BEFORE descending, so the
            # "not full" precondition holds at every level (no backtracking)
            if len(self.children[i].keys) == 2 * self.order - 1:
                median, new_child = self.children[i].split()
                # Promoting median + inserting new_child preserves
                # the invariant: len(children) == len(keys) + 1
                self.keys.insert(i, median)
                self.children.insert(i + 1, new_child)
                if key > median:
                    i += 1

            self.children[i].insert_non_full(key)
```'''
    },
    {
        "instruction": r'''Add comments to this lock-free concurrent queue explaining the memory ordering and CAS logic:

class LockFreeQueue:
    def __init__(self):
        sentinel = Node(None)
        self.head = AtomicRef(sentinel)
        self.tail = AtomicRef(sentinel)

    def enqueue(self, value):
        new_node = Node(value)
        while True:
            tail = self.tail.load()
            next_node = tail.next.load()
            if tail == self.tail.load():
                if next_node is None:
                    if tail.next.compare_and_swap(None, new_node):
                        self.tail.compare_and_swap(tail, new_node)
                        return
                else:
                    self.tail.compare_and_swap(tail, next_node)

    def dequeue(self):
        while True:
            head = self.head.load()
            tail = self.tail.load()
            first = head.next.load()
            if head == self.head.load():
                if head == tail:
                    if first is None:
                        return None
                    self.tail.compare_and_swap(tail, first)
                else:
                    value = first.value
                    if self.head.compare_and_swap(head, first):
                        return value''',
        "output": r'''```python
class LockFreeQueue:
    # Michael-Scott lock-free queue. Uses a sentinel (dummy) node so that
    # head and tail are never null, simplifying the empty-queue case.

    def __init__(self):
        sentinel = Node(None)
        self.head = AtomicRef(sentinel)
        self.tail = AtomicRef(sentinel)

    def enqueue(self, value):
        new_node = Node(value)
        while True:
            tail = self.tail.load()
            next_node = tail.next.load()

            # Consistency: verify tail unchanged between the two loads
            if tail == self.tail.load():
                if next_node is None:
                    # Tail is truly last. CAS link our node; losers retry.
                    if tail.next.compare_and_swap(None, new_node):
                        # Swing tail forward. If CAS fails, another thread
                        # already advanced it for us (helping pattern below).
                        self.tail.compare_and_swap(tail, new_node)
                        return
                else:
                    # Tail is lagging -- another thread linked a node but
                    # hasn't updated tail yet. Help advance it.
                    self.tail.compare_and_swap(tail, next_node)

    def dequeue(self):
        while True:
            head = self.head.load()
            tail = self.tail.load()
            first = head.next.load()

            if head == self.head.load():
                if head == tail:
                    if first is None:
                        return None  # truly empty
                    # Tail lagging behind enqueue -- help advance it
                    self.tail.compare_and_swap(tail, first)
                else:
                    # Read value BEFORE CAS -- after CAS another thread
                    # could dequeue and free the node
                    value = first.value
                    # Swing head forward; first becomes new sentinel
                    if self.head.compare_and_swap(head, first):
                        return value
```'''
    },
]
