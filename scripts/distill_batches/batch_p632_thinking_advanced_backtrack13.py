"""Phase 2A: Advanced Reasoning — Backtracking & Dead-End Recovery (Part 13)"""

PAIRS = [
    (
        "thinking/backtrack-regex-to-proper-parser",
        "I'm trying to parse markdown-like syntax from user input using regex. It works for simple cases but breaks on nested formatting like **bold with *italic* inside**. Should I write more complex regex?",
        r'''<think>
Regex for parsing nested structures. My first thought: more complex regex. But this is a known dead end.

**Why regex fails for nested structures:**
Regular expressions (by definition) cannot match arbitrary nesting. They can't count — they can't match N opening brackets with N closing brackets. This is a fundamental limitation from formal language theory (regular languages vs context-free languages).

You CAN add features (lookahead, backreferences, recursive patterns in PCRE) but the regex becomes unreadable, unmaintainable, and fragile.

**Let me backtrack from "better regex" to "proper parsing."**

For markdown-like syntax, you need:
1. A tokenizer/lexer: split input into tokens (**, *, text, newline)
2. A parser: build a tree from tokens (bold node containing italic node)

But for this specific use case (markdown-like formatting), you probably don't need to write a parser from scratch. Libraries exist:
- markdown-it (JS)
- Python-Markdown
- marked (JS)
- Or a simpler approach: iterative state machine

The right answer depends on complexity:
- Simple (just bold/italic): state machine or iterative replacement
- Medium (full markdown): use a library
- Complex (custom syntax): write a recursive descent parser
</think>

More complex regex is a dead end. Let me show why, and the correct alternatives.

## Why Regex Fails for Nested Structures

```python
# Works for simple cases:
import re
text = "This is **bold** text"
result = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
# ✓ "This is <b>bold</b> text"

# Breaks on nesting:
text = "This is **bold with *italic* inside** text"
result = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
result = re.sub(r'\*(.*?)\*', r'<i>\1</i>', result)
# ✗ Matches wrong — italic * matches bold ** boundaries

# The fundamental problem: regex can't COUNT.
# It can't match "N opening markers with N closing markers."
# This is a mathematical limitation, not a skill issue.
```

## Solution 1: Use a Library (Usually the Right Answer)

```python
# For actual markdown: don't parse it yourself
import markdown
result = markdown.markdown("**bold with *italic* inside**")
# <p><strong>bold with <em>italic</em> inside</strong></p>

# JavaScript:
# import { marked } from 'marked';
# const result = marked.parse('**bold with *italic* inside**');
```

## Solution 2: Simple State Machine (For Custom Syntax)

```python
def parse_inline(text):
    """Parse bold (**) and italic (*) with proper nesting."""
    tokens = []
    i = 0
    while i < len(text):
        if text[i:i+2] == '**':
            tokens.append(('bold_marker', '**'))
            i += 2
        elif text[i] == '*':
            tokens.append(('italic_marker', '*'))
            i += 1
        else:
            # Collect plain text
            j = i
            while j < len(text) and text[j] != '*':
                j += 1
            tokens.append(('text', text[i:j]))
            i = j

    # Build tree from tokens using a stack
    result = []
    stack = []  # Track open markers

    for token_type, value in tokens:
        if token_type == 'bold_marker':
            if stack and stack[-1][0] == 'bold':
                # Closing bold
                content = stack.pop()[1]
                node = f'<b>{content}</b>'
                if stack:
                    stack[-1] = (stack[-1][0], stack[-1][1] + node)
                else:
                    result.append(node)
            else:
                stack.append(('bold', ''))
        elif token_type == 'italic_marker':
            if stack and stack[-1][0] == 'italic':
                content = stack.pop()[1]
                node = f'<i>{content}</i>'
                if stack:
                    stack[-1] = (stack[-1][0], stack[-1][1] + node)
                else:
                    result.append(node)
            else:
                stack.append(('italic', ''))
        else:
            if stack:
                stack[-1] = (stack[-1][0], stack[-1][1] + value)
            else:
                result.append(value)

    return ''.join(result)

# parse_inline("**bold with *italic* inside**")
# → "<b>bold with <i>italic</i> inside</b>"  ✓ Correct!
```

## When to Use Each Approach

```
SIMPLE PATTERNS (no nesting):
  Use regex. "Find all URLs", "extract email addresses", "validate phone number"
  These are REGULAR languages — regex is perfect.

NESTED STRUCTURES:
  Use a parser. Markdown, HTML, JSON, programming languages, math expressions.
  These are CONTEXT-FREE languages — regex fundamentally can't handle them.

EXISTING FORMAT:
  Use a library. Markdown, JSON, YAML, XML, CSV — all have mature parsers.
  Don't write your own unless you have a custom format.

CUSTOM FORMAT:
  Write a recursive descent parser or use a parser generator (PEG.js, Lark, ANTLR).
```'''
    ),
    (
        "thinking/backtrack-premature-optimization-to-profiling",
        "Our Python web app is slow. Response times are 500ms-2s. A colleague says we should rewrite the hot path in C or Rust. Another says we should add caching. Nobody has profiled anything. What should we do?",
        r'''<think>
Performance problem without profiling. Both suggestions (rewrite in C, add caching) are premature without data.

**First instinct: rewriting in C/Rust**
This is almost always wrong at this stage. Python web apps are rarely CPU-bound. They spend most time waiting for I/O (database, network, file system). Rewriting CPU code in C when the bottleneck is a 400ms database query saves 0ms.

**Second instinct: add caching**
Better instinct — caching helps many apps. But WHERE do you cache? What if the bottleneck isn't a repeated read but a slow write? Caching the wrong thing wastes effort.

**Let me backtrack to: profile first.**

Step 1: Where is time spent? Profiling tells us:
- 80% in database queries → optimize queries, add indexes
- 80% in external API calls → cache or parallelize
- 80% in CPU processing → then consider algorithmic optimization (not C rewrite)
- 80% in template rendering → cache rendered output

Without profiling, any optimization is a guess. And optimizing the wrong thing is wasted effort.

The golden rule: "Measure, don't guess."
</think>

Both suggestions are premature. **Profile first.** Let me show why and how.

## Why Guessing Doesn't Work

```
COMMON WEB APP TIME BREAKDOWN:

  Your 500ms response time might be:
    Database query:      400ms  (80%)  ← Optimize THIS
    Template rendering:   50ms  (10%)
    Business logic:       30ms  (6%)
    Python overhead:      20ms  (4%)

  Rewriting Python in C saves: 20ms (4%)
  Optimizing the DB query saves: 350ms (70%)

  The C rewrite takes 2 months for 4% improvement.
  Adding a DB index takes 5 minutes for 70% improvement.

  WITHOUT PROFILING, YOU DON'T KNOW WHERE THE 500ms IS SPENT.
```

## Step 1: Profile Your Application

```python
# Quick profiling: add timing middleware
import time
import logging

logger = logging.getLogger("performance")

@app.middleware("http")
async def timing_middleware(request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = (time.perf_counter() - start) * 1000

    if duration > 200:  # Log slow requests
        logger.warning(f"SLOW {request.method} {request.url.path}: {duration:.0f}ms")
    return response


# Profile database queries (Django/SQLAlchemy)
# Django: install django-debug-toolbar or django-silk
# SQLAlchemy: enable echo=True or use event listeners

from sqlalchemy import event

@event.listens_for(engine, "before_cursor_execute")
def before_execute(conn, cursor, statement, parameters, context, executemany):
    conn.info["query_start"] = time.perf_counter()

@event.listens_for(engine, "after_cursor_execute")
def after_execute(conn, cursor, statement, parameters, context, executemany):
    duration = (time.perf_counter() - conn.info["query_start"]) * 1000
    if duration > 50:  # Log queries over 50ms
        logger.warning(f"SLOW QUERY ({duration:.0f}ms): {statement[:200]}")
```

```bash
# Python profiling tools:
# 1. cProfile (built-in, function-level)
python -m cProfile -s cumulative app.py

# 2. py-spy (sampling profiler, attach to running process)
pip install py-spy
py-spy top --pid $(pgrep python)        # Live view
py-spy record -o profile.svg --pid $(pgrep python)  # Flame graph

# 3. line_profiler (line-by-line timing)
pip install line_profiler
@profile  # Decorate the slow function
def process_order(data):
    ...
# Run: kernprof -l -v app.py
```

## Step 2: Fix What's Actually Slow

```python
# COMMON FINDING 1: N+1 queries (most common performance killer)
# Profile shows: 100 database queries per request

# ❌ N+1: one query per user, per order, per item
def get_dashboard():
    users = User.query.all()                    # 1 query
    for user in users:
        orders = user.orders                     # N queries (one per user!)
        for order in orders:
            items = order.items                   # N*M queries!
    # 100 users × 10 orders × 5 items = 5,000 queries = 2 seconds

# ✅ Fixed: eager loading
def get_dashboard():
    users = User.query.options(
        joinedload(User.orders).joinedload(Order.items)
    ).all()
    # 1 query with JOINs = 50ms


# COMMON FINDING 2: Missing database index
# Profile shows: one query takes 400ms

# ❌ Full table scan
SELECT * FROM orders WHERE customer_email = 'alice@example.com';
-- Scans 1M rows: 400ms

# ✅ Add index
CREATE INDEX idx_orders_customer_email ON orders(customer_email);
-- Index lookup: 2ms


# COMMON FINDING 3: Synchronous external API calls
# Profile shows: external API call takes 300ms

# ❌ Sequential calls
def get_page_data():
    user = fetch_user_api(user_id)           # 100ms
    orders = fetch_orders_api(user_id)       # 100ms
    recommendations = fetch_recs_api(user_id) # 100ms
    # Total: 300ms (sequential)

# ✅ Parallel calls
import asyncio

async def get_page_data():
    user, orders, recommendations = await asyncio.gather(
        fetch_user_api(user_id),              # 100ms ─┐
        fetch_orders_api(user_id),            # 100ms ─┤ parallel
        fetch_recs_api(user_id),              # 100ms ─┘
    )
    # Total: 100ms (parallel)
```

## Step 3: THEN Consider Caching (With Data)

```python
# Only cache what profiling shows is slow AND frequently accessed

# Profile shows: /products endpoint called 1000x/min, takes 200ms
# The query results change once per hour → perfect cache candidate

@app.get("/products")
async def get_products(category: str):
    cache_key = f"products:{category}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)  # 1ms instead of 200ms

    products = await db.query_products(category)  # 200ms
    await redis.setex(cache_key, 300, json.dumps(products))
    return products
```

## Decision Tree

```
Response time > 200ms?
  │
  ├─ PROFILE FIRST (always)
  │
  ├─ Database queries slow?
  │   ├─ N+1 queries → add eager loading
  │   ├─ Missing indexes → add indexes
  │   └─ Complex queries → optimize or denormalize
  │
  ├─ External API calls slow?
  │   ├─ Multiple calls → parallelize with asyncio
  │   └─ Same data fetched repeatedly → cache responses
  │
  ├─ Template rendering slow?
  │   └─ Cache rendered output (fragment or full page)
  │
  ├─ CPU-bound processing slow?
  │   ├─ Algorithmic improvement first (O(n²) → O(n log n))
  │   ├─ Then: cache the computation result
  │   └─ Last resort: offload to C extension or background worker
  │
  └─ Rewrite in C/Rust?
      └─ Only after ALL above are exhausted AND profiling shows
         CPU is the bottleneck AND the operation can't be cached.
         (This is almost never the answer for web apps.)
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
