"""Phase 3C: Metacognition — Adjusting Confidence Based on Question Complexity (Part 7)

Training the model to recognize when a question has hidden complexity that
should lower initial confidence, and when apparent complexity is actually
straightforward.
"""

PAIRS = [
    (
        "thinking/meta-confidence-complexity-simple-seeming",
        r'''How do I center a div in CSS?''',
        r'''<think>
This seems like a simple question, but let me consider the complexity honestly.

On the surface: This is a meme-level "easy" question in web development. But it actually depends on:
- Center horizontally, vertically, or both?
- Within a fixed-size parent or a flexible one?
- Is the div fixed-size or content-sized?
- What CSS layout mode (flexbox, grid, positioning, margin auto)?
- Does it need to work in older browsers?

My confidence is HIGH on the modern solutions (flexbox/grid) and MEDIUM on edge cases with older approaches. The question's apparent simplicity hides genuine complexity — that's why it became a meme.

I should give the clean modern answer first, then acknowledge the nuances.
</think>

This question is famously "simple" but actually has nuance depending on context. Here are the solutions from most to least modern:

**Both axes — the modern answer (HIGH confidence):**
```css
/* Flexbox — works for any content */
.parent {
    display: flex;
    justify-content: center;  /* horizontal */
    align-items: center;      /* vertical */
}

/* Grid — even shorter */
.parent {
    display: grid;
    place-items: center;
}
```

**Horizontal only:**
```css
/* Block element with known width */
.child {
    width: 300px;
    margin: 0 auto;
}

/* Inline or inline-block content */
.parent {
    text-align: center;
}
```

**Absolute centering (when you need it out of flow):**
```css
.child {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
}
```

**Which to use:**
- Default choice: Flexbox (`display: flex` + `justify-content` + `align-items`)
- Single item centering: Grid (`place-items: center`)
- Horizontal only for block elements: `margin: 0 auto`
- Overlay/modal positioning: Absolute + transform

The reason this question is a meme is that before flexbox, every approach had caveats. The modern answer is genuinely simple.'''
    ),
    (
        "thinking/meta-confidence-complexity-deceptive",
        r'''Can you write a function to check if two strings are anagrams?''',
        r'''<think>
This looks like a simple coding question, but let me think about the hidden complexity layers:

Level 1 (trivial): Sort both strings, compare. O(n log n).
Level 2 (better): Use character frequency counting. O(n).
Level 3 (tricky): What about case sensitivity? "Listen" vs "Silent"?
Level 4 (harder): What about Unicode? Accented characters? "café" vs "face" — these have different character counts.
Level 5 (subtle): What about Unicode normalization? "é" can be represented as one codepoint (U+00E9) or two (e + combining accent U+0301).
Level 6 (edge): What about whitespace and punctuation? "Astronomer" vs "Moon starer"?

My confidence levels:
- ASCII solution: Very high confidence
- Unicode-aware solution: High confidence on approach, medium on exact implementation
- Full internationalized solution: Medium confidence

The right response depends on the context — if this is a coding interview, the sorted approach or frequency counting is fine. If it's production code, Unicode matters.

I'll provide the clean solution with progressive levels of sophistication.
</think>

This question has more depth than it appears. Let me provide solutions at increasing levels of correctness.

**Level 1 — Interview answer (simple, correct for ASCII):**
```python
def are_anagrams(s1: str, s2: str) -> bool:
    return sorted(s1.lower()) == sorted(s2.lower())
```

**Level 2 — Better performance, O(n):**
```python
from collections import Counter

def are_anagrams(s1: str, s2: str) -> bool:
    return Counter(s1.lower()) == Counter(s2.lower())
```

**Level 3 — Production-grade (handles real-world input):**
```python
from collections import Counter
import unicodedata

def are_anagrams(s1: str, s2: str) -> bool:
    def normalize(s: str) -> str:
        # Unicode normalize, lowercase, strip non-letters
        s = unicodedata.normalize('NFC', s)
        return ''.join(c.lower() for c in s if c.isalpha())

    n1, n2 = normalize(s1), normalize(s2)
    return Counter(n1) == Counter(n2)

# Now handles:
are_anagrams("Listen", "Silent")         # True
are_anagrams("Astronomer", "Moon starer") # True
are_anagrams("café", "face")             # False (different letters)
```

**Hidden complexity I want to flag:**
- Unicode normalization (NFC vs NFD) affects character counting
- Some languages have locale-specific sorting rules
- For a coding interview, Level 1 or 2 is sufficient
- For production internationalized software, Level 3 is the minimum

The deceptive part of "simple" string questions is that strings are never simple once Unicode enters the picture.'''
    ),
    (
        "thinking/meta-confidence-complexity-distributed",
        r'''How do I implement a distributed counter that can handle 100K increments per second across 10 servers?''',
        r'''<think>
This looks like it could be simple (just use Redis INCR!) but the complexity depends entirely on the requirements I need to clarify:

Questions that change the difficulty dramatically:
1. Does the counter need to be exactly accurate in real-time? (Easy: no, Hard: yes)
2. What's the acceptable staleness? (seconds? minutes?)
3. Is this a single counter or per-user/per-resource counters?
4. What happens if a node goes down — can we lose some increments?
5. Is 100K/s the peak or sustained rate?

My confidence assessment:
- Redis INCR approach: HIGH confidence — this is the standard solution for moderate scale
- Local buffering + periodic flush: HIGH confidence on the pattern
- Whether Redis can handle 100K INCR/s: HIGH — single Redis instance can do 100K+ ops/s
- CRDTs for distributed counting: MEDIUM confidence on implementation details
- Exact distributed counting without coordination: This is a known hard problem (CAP theorem territory)

The honest answer is: this is probably simpler than it sounds if you can accept approximate counting, and much harder than it sounds if you need exact real-time accuracy.
</think>

My confidence on this depends heavily on your accuracy requirements. Let me walk through solutions from simplest to most complex.

**If approximate is OK (HIGH confidence — this is probably what you need):**

```python
# Single Redis counter — handles 100K+/s easily
import redis
r = redis.Redis()

def increment():
    r.incr("global_counter")

def get_count():
    return int(r.get("global_counter") or 0)
```

A single Redis instance handles 100K+ ops/s. This is likely your answer. Done.

**If Redis becomes a bottleneck (HIGH confidence on pattern):**

Buffer locally on each server, flush periodically:
```python
import threading
import time

class BufferedCounter:
    def __init__(self, redis_client, key, flush_interval=1.0):
        self.redis = redis_client
        self.key = key
        self.local_count = 0
        self.lock = threading.Lock()
        self._start_flusher(flush_interval)

    def increment(self):
        with self.lock:
            self.local_count += 1  # Fast, no network call

    def _flush(self):
        with self.lock:
            to_flush = self.local_count
            self.local_count = 0
        if to_flush > 0:
            self.redis.incrby(self.key, to_flush)  # One network call per flush

    def _start_flusher(self, interval):
        def run():
            while True:
                time.sleep(interval)
                self._flush()
        t = threading.Thread(target=run, daemon=True)
        t.start()
```

10 servers, 10K increments each, flushing once per second = 10 Redis operations/s instead of 100K.

**If you need exact real-time accuracy across all nodes (LOWER confidence — genuinely hard):**

This is a distributed consensus problem. Options:
1. **Serialization through Redis** — still works at 100K/s, adds latency
2. **CRDT G-Counter** — each node maintains its own counter, merge on read
3. **Database with serializable isolation** — too slow for 100K/s

```
CRDT G-Counter concept:
  Node A: 25,000
  Node B: 31,000
  Node C: 44,000
  Total = sum of all nodes = 100,000 (eventually consistent)
```

**My honest recommendation:**

Start with plain Redis INCR. A single Redis instance on modern hardware handles 100-200K operations per second. You only need the more complex solutions if:
- Redis becomes a network bottleneck (unlikely at 100K/s)
- You need the counter to survive Redis downtime
- You're actually doing 1M+/s sustained

Don't over-engineer distributed counters. Most "distributed counter" problems are solved by a single Redis INCR.'''
    ),
    (
        "thinking/meta-confidence-complexity-timezone",
        r'''How do I store and display times correctly for users in different timezones in my web app?''',
        r'''<think>
This question SEEMS straightforward but is genuinely one of the hardest problems in software engineering. Let me assess complexity honestly.

Layers of complexity:
1. Basic: Store as UTC, convert on display — sounds simple
2. Medium: DST transitions — clocks spring forward/fall back, some times don't exist or exist twice
3. Hard: Historical timezone changes — countries change their UTC offset, split/merge timezones
4. Harder: Recurring events — "every Tuesday at 3pm" in a timezone that changes DST
5. Hardest: Past/future event display — what timezone rules applied when the event was created?

My confidence:
- "Store UTC, display local": HIGH — this is the correct core principle
- Handling DST correctly: HIGH on the concept, MEDIUM on all edge cases
- Recurring events across DST: MEDIUM — this is a known source of bugs
- Historical timezone data: HIGH confidence that it exists (IANA tz database) but MEDIUM on implementation details
- "Just use moment.js/luxon/date-fns-tz": HIGH that these help, but they don't eliminate all edge cases

I should present the clean answer but not pretend timezone handling is simple. The complexity is real and well-documented.
</think>

This is one of those questions where the "simple" answer is correct but incomplete, and the full answer is genuinely hard. Let me be clear about both.

**The core principle (HIGH confidence):**

```
STORE:   Always UTC (or Unix timestamp)
SEND:    UTC in API responses (ISO 8601)
DISPLAY: Convert to user's timezone in the frontend
```

**Backend — always store UTC:**
```python
from datetime import datetime, timezone

# Store this in your database
event_time = datetime.now(timezone.utc)
# → 2024-03-10T07:00:00+00:00

# In PostgreSQL: use TIMESTAMPTZ (not TIMESTAMP)
# CREATE TABLE events (
#     created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
# );
```

**API — always send UTC:**
```json
{
    "created_at": "2024-03-10T07:00:00Z",
    "user_timezone": "America/New_York"
}
```

**Frontend — convert for display:**
```javascript
// Modern browsers handle this well
const utcDate = new Date("2024-03-10T07:00:00Z");
const display = utcDate.toLocaleString('en-US', {
    timeZone: 'America/New_York',
    dateStyle: 'medium',
    timeStyle: 'short'
});
// → "Mar 10, 2024, 3:00 AM"
```

**Where it gets genuinely hard (MEDIUM confidence — here be dragons):**

**1. Recurring events across DST:**
```
"Team standup every day at 9:00 AM Eastern"
- Most of the year: 9:00 AM EDT (UTC-4) = 13:00 UTC
- Winter: 9:00 AM EST (UTC-5) = 14:00 UTC
- You CANNOT store this as a fixed UTC time
- Store: { time: "09:00", timezone: "America/New_York", rrule: "FREQ=DAILY" }
- Resolve to UTC at query time using current timezone rules
```

**2. The "impossible time" problem:**
```
March 10, 2024 at 2:30 AM Eastern DOES NOT EXIST
(Clocks jump from 2:00 AM to 3:00 AM)

November 3, 2024 at 1:30 AM Eastern EXISTS TWICE
(Clocks fall back from 2:00 AM to 1:00 AM)
```

**3. Store the timezone NAME, not the offset:**
```
WRONG: store UTC-5 (is that EST? CDT? Colombia?)
RIGHT: store "America/New_York" (IANA timezone ID)
```

**Practical checklist:**
- Use TIMESTAMPTZ in PostgreSQL (not TIMESTAMP)
- Store user's IANA timezone (not UTC offset)
- Use libraries: Luxon (JS), pytz/zoneinfo (Python), java.time (Java)
- Test with users in timezones with unusual DST rules (Arizona, India, Lord Howe Island)
- For recurring events, store local time + timezone, resolve to UTC dynamically'''
    ),
    (
        "thinking/meta-confidence-complexity-rate-limiting",
        r'''I need to add rate limiting to my API. Should I use a token bucket or sliding window algorithm? We get about 1000 requests per second.''',
        r'''<think>
Let me assess my confidence on rate limiting algorithms.

HIGH confidence:
- Token bucket: tokens added at fixed rate, consumed per request. Allows bursts up to bucket size.
- Sliding window: counts requests in a rolling time window. More precise but slightly more complex.
- Fixed window: simpler but has boundary burst problem (2x rate at window edges)
- At 1000 req/s, any algorithm works — this isn't a scale challenge
- Redis is the standard backing store for distributed rate limiting

MEDIUM confidence:
- Sliding window log: stores each request timestamp, most accurate, most memory
- Sliding window counter: hybrid of fixed window and sliding, good tradeoff
- Token bucket allows controlled bursting, which is often desirable
- Leaky bucket: similar to token bucket but smooths output rate

HIGH confidence on practical advice:
- For most APIs, the algorithm matters less than the implementation
- Use an existing library (rate-limiter-flexible for Node, limits for Python)
- The harder problem is: what do you rate limit on? (IP? API key? User? Endpoint?)
- 1000 req/s is moderate — single Redis instance handles this trivially

The question implies this is harder than it usually is. For most applications, using an existing library with sensible defaults is the right answer. The algorithm choice is secondary.
</think>

Good question, but I want to reframe it slightly: the algorithm choice matters less than you might think. At 1000 req/s, both work fine. Here's how to decide.

**Quick comparison (HIGH confidence):**

| Factor | Token Bucket | Sliding Window |
|--------|-------------|----------------|
| Allows bursts | Yes (up to bucket size) | No (strict rate) |
| Memory per key | O(1) — just token count + timestamp | O(1) for counter variant |
| Precision | Approximate | More precise |
| Implementation | Simpler | Slightly more complex |
| Best for | APIs where bursts are OK | Strict rate enforcement |

**My recommendation: Token bucket for most APIs.**

Why: Users expect to make a few quick requests in succession (burst), then slow down. Token bucket naturally supports this. Sliding window is stricter than most use cases require.

**Practical implementation (HIGH confidence):**

Rather than implementing from scratch, use a battle-tested library:

```python
# Python with Redis — using a library
from redis import Redis
from limits import parse, storage, strategies

store = storage.RedisStorage("redis://localhost:6379")
limiter = strategies.MovingWindowRateLimiter(store)
rate = parse("100/minute")  # Per user

def check_rate_limit(user_id: str) -> bool:
    return limiter.hit(rate, user_id)
```

```javascript
// Node.js
const { RateLimiterRedis } = require('rate-limiter-flexible');

const limiter = new RateLimiterRedis({
    storeClient: redisClient,
    points: 100,        // requests
    duration: 60,       // per 60 seconds
    keyPrefix: 'rl',
});

async function rateLimit(req, res, next) {
    try {
        await limiter.consume(req.user.id);
        next();
    } catch (e) {
        res.status(429).json({ error: 'Too many requests' });
    }
}
```

**The harder questions (where the real complexity lives):**

1. **What's the rate limit key?**
   - Unauthenticated: IP address (careful with shared IPs/NAT)
   - Authenticated: User ID or API key
   - Consider per-endpoint limits (writes stricter than reads)

2. **What are the limits?**
   - Start generous, tighten based on data
   - Different tiers for different users/plans

3. **How do you communicate limits?**
```http
HTTP/1.1 200 OK
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 73
X-RateLimit-Reset: 1710086400
Retry-After: 30  (only on 429 responses)
```

4. **Distributed rate limiting?**
   - Redis handles this naturally — all servers share the same counter
   - At 1000 req/s, a single Redis instance is more than sufficient

**Bottom line:** Use token bucket via an existing library, back it with Redis, and spend your time on the policy decisions (who, what limits, what key) rather than the algorithm.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
