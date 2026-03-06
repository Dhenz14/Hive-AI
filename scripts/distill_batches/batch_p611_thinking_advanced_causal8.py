"""Phase 2E: Advanced Reasoning — Causal & Counterfactual Analysis (Part 8/8)"""

PAIRS = [
    (
        "thinking/causal-memory-leak-node-event-listeners",
        "Our Node.js server's memory usage grows from 200MB to 2GB over 24 hours, then crashes with an OOM error. We restarted it and it starts climbing again. How do I find the leak?",
        r'''<think>
Node.js memory leak growing over 24 hours. Let me reason through likely causes.

**Causal chain analysis:**
Memory grows steadily over time → something is accumulating → objects are created but never garbage collected → something holds a reference preventing GC.

**Common Node.js memory leak causes (ordered by likelihood):**

1. **Event listener accumulation** — Most common in Node.js
   - Adding event listeners in request handlers without removing them
   - Each request adds a listener → listener count grows → references prevent GC
   - Node warns: "MaxListenersExceededWarning" (but many devs ignore this or increase the limit)

2. **Global/module-level caches without bounds**
   - `const cache = {}` that grows forever
   - Map or Set that accumulates entries without eviction
   - Global arrays that get `.push()` but never `.splice()` or truncated

3. **Closures capturing large objects**
   - A closure references a variable from outer scope → that variable can't be GC'd
   - Common with database connections, request objects held in callbacks

4. **Unresolved promises / timers**
   - setInterval without clearInterval
   - Promises that never resolve → handlers stay in memory
   - setTimeout chains that create circular references

5. **Stream not properly consumed/destroyed**
   - Readable streams created but not piped or consumed → backpressure builds up → buffers grow

**Diagnostic approach:**
1. Take heap snapshots at different times → compare to find what's growing
2. Use `--inspect` flag + Chrome DevTools
3. Look for increasing object counts between snapshots

**Counterfactual analysis:**
- If the leak were a simple cache: memory would grow proportional to unique keys (request paths, user IDs)
- If the leak were event listeners: memory would grow proportional to total requests handled
- If the leak were timers: memory would grow proportional to some scheduled operation count
- The 24-hour timeline suggests request-proportional growth (event listeners or per-request caches)
</think>

Let me trace the causal chain to systematically find your leak.

## Causal Analysis

```
Observation: 200MB → 2GB over 24 hours (10x growth, ~75MB/hour)

Causal chain:
  Memory grows steadily
  → Objects are being allocated but never freed
  → Something holds references, preventing garbage collection
  → Reference must be in a long-lived scope (global, module, closure)

Key question: Is growth proportional to REQUESTS or TIME?
  - Proportional to requests → per-request leak (event listeners, caches)
  - Proportional to time → timer/interval leak
  - Your 24-hour pattern → likely request-proportional (traffic dies at night?)
```

## Step 1: Take Heap Snapshots (Find What's Growing)

```javascript
// Add this to your server temporarily
const v8 = require('v8');
const fs = require('fs');

// Endpoint to trigger heap snapshot
app.get('/_debug/heapdump', (req, res) => {
    const filename = `/tmp/heap-${Date.now()}.heapsnapshot`;
    v8.writeHeapSnapshot(filename);
    res.json({ file: filename, heapUsed: process.memoryUsage().heapUsed });
});

// Or use --inspect flag and Chrome DevTools:
// node --inspect server.js
// Open chrome://inspect → Take heap snapshot at t=0, t=1h, t=4h
// Compare snapshots → sort by "Alloc. Size" delta → find what's growing
```

## Most Likely Cause: Event Listener Accumulation

```javascript
// ❌ COMMON LEAK: adding listeners in request handlers

const EventEmitter = require('events');
const bus = new EventEmitter();

app.get('/notifications', (req, res) => {
    // THIS LEAKS: a new listener is added PER REQUEST
    // and never removed
    bus.on('notification', (data) => {
        // This closure captures `res`, preventing it from being GC'd
        res.write(`data: ${JSON.stringify(data)}\n\n`);
    });
});

// After 10,000 requests: 10,000 listeners on `bus`
// Each listener holds a reference to its `res` object
// None are garbage collected

// ✅ FIXED: remove listener when connection closes
app.get('/notifications', (req, res) => {
    const handler = (data) => {
        res.write(`data: ${JSON.stringify(data)}\n\n`);
    };

    bus.on('notification', handler);

    req.on('close', () => {
        bus.removeListener('notification', handler);  // Clean up!
    });
});
```

## Second Most Likely: Unbounded Cache

```javascript
// ❌ LEAK: module-level object that grows forever
const userCache = {};  // Never evicted!

app.get('/users/:id', async (req, res) => {
    if (!userCache[req.params.id]) {
        userCache[req.params.id] = await db.getUser(req.params.id);
    }
    res.json(userCache[req.params.id]);
});

// After 100,000 unique users: 100,000 cached objects
// After 1,000,000 unique users: you're out of memory

// ✅ FIXED: bounded cache with eviction
const LRU = require('lru-cache');
const userCache = new LRU({
    max: 1000,               // Maximum 1000 entries
    ttl: 1000 * 60 * 5,      // Entries expire after 5 minutes
});
```

## Third Possibility: Uncleared Intervals

```javascript
// ❌ LEAK: setInterval in request scope
app.get('/start-monitor', (req, res) => {
    // Creates an interval that NEVER gets cleared
    setInterval(() => {
        checkHealth();  // Runs forever, holds references
    }, 1000);

    res.json({ status: 'monitoring started' });
});

// After 100 requests: 100 intervals running
// Each holds references to its closure scope

// ✅ FIXED: track and clear intervals
const monitors = new Map();

app.get('/start-monitor/:id', (req, res) => {
    // Clear existing interval for this ID
    if (monitors.has(req.params.id)) {
        clearInterval(monitors.get(req.params.id));
    }

    const interval = setInterval(() => checkHealth(req.params.id), 1000);
    monitors.set(req.params.id, interval);
    res.json({ status: 'monitoring started' });
});
```

## Diagnostic Checklist

```bash
# 1. Check for event listener warnings (often suppressed!)
node server.js 2>&1 | grep -i "MaxListeners"

# 2. Monitor memory over time
node -e "
  setInterval(() => {
    const mem = process.memoryUsage();
    console.log(JSON.stringify({
      rss: (mem.rss / 1024 / 1024).toFixed(1) + 'MB',
      heap: (mem.heapUsed / 1024 / 1024).toFixed(1) + 'MB',
      time: new Date().toISOString()
    }));
  }, 60000);  // Every minute
"

# 3. Search codebase for common leak patterns
grep -rn "\.on(" --include="*.js" | grep -v node_modules  # Event listeners
grep -rn "setInterval" --include="*.js" | grep -v node_modules  # Uncleaned timers
grep -rn "= {}" --include="*.js" | grep -v node_modules  # Module-level objects
grep -rn "\.push(" --include="*.js" | grep -v node_modules  # Growing arrays
```

## Counterfactual Verification

```
Once you find the suspected cause, verify with counterfactuals:

"If event listeners are the cause":
  → Memory growth should correlate with request count
  → bus.listenerCount('notification') should increase over time
  → Fix: remove listeners → memory should stabilize

"If cache is the cause":
  → Object.keys(cache).length should increase over time
  → Memory growth should correlate with unique cache keys
  → Fix: add LRU eviction → memory should plateau

"If timers are the cause":
  → Memory growth should correlate with timer-creating endpoint hits
  → process._getActiveHandles().length should increase
  → Fix: clear intervals → memory should stabilize
```'''
    ),
    (
        "thinking/causal-css-layout-breaking-on-content",
        "My CSS layout works perfectly with test data but breaks completely when we load real user content. Some cards are different heights, text overflows, and the grid falls apart. What's causing this?",
        r'''<think>
CSS layout breaking with real content — this is a classic content-driven layout failure. Let me trace the causal chain.

**Root cause analysis:**
Test data was uniform (same-length titles, similar images, same number of tags). Real data is variable. The layout was designed for ideal data, not real data.

**Specific causes:**

1. **Fixed heights on containers**
   - Cards have `height: 300px` — content longer than 300px overflows
   - Test data fit within 300px; real user content doesn't

2. **No text truncation/overflow handling**
   - Titles: test data "Product Name" (12 chars); real data "Premium Handcrafted Artisanal Organic Free-Range Widget V2.0" (60 chars)
   - Descriptions can be 10 words or 500 words

3. **Inconsistent image aspect ratios**
   - Test images all 16:9; real images are 1:1, 4:3, 9:16, tiny, or huge
   - Without `object-fit`, images stretch or squash

4. **Grid assuming equal heights**
   - CSS Grid with `grid-template-rows: 300px` breaks when content varies
   - Flexbox without `align-items: stretch` creates ragged bottoms

5. **Long unbreakable strings**
   - URLs, emails, product codes: "SKU-ABCDEFGHIJKLMNOPQRSTUVWXYZ-12345"
   - These don't word-wrap, they overflow their container

**Counterfactual test:**
If the test data had included: 1-word titles, 200-word descriptions, 1:1 and 9:16 images, and 50-character words — the layout would have broken immediately during development.

The root cause isn't CSS — it's testing with unrealistic data.
</think>

The root cause: **your layout was designed for ideal data, and real data isn't ideal**. Let me trace each specific failure.

## Causal Chain

```
Test data: uniform, short, predictable
Real data: variable lengths, weird images, long words

Layout designed for test data → works with test data
Real data arrives → content exceeds assumed constraints → layout breaks

This isn't a CSS bug — it's a missing contract between content and layout.
```

## Fix 1: Variable-Height Cards (The Most Common Issue)

```css
/* ❌ BREAKS: fixed height assumes content fits */
.card {
    height: 300px;  /* Content longer than 300px overflows */
}

/* ✅ FIXED: let content determine height, set minimum */
.card {
    min-height: 200px;  /* Minimum for visual consistency */
    /* No max-height — let it grow */
}

/* If you NEED fixed height: handle overflow */
.card {
    height: 300px;
    overflow: hidden;  /* Hide overflow */
}
.card-description {
    display: -webkit-box;
    -webkit-line-clamp: 3;      /* Show max 3 lines */
    -webkit-box-orient: vertical;
    overflow: hidden;
}
```

## Fix 2: Text Overflow and Truncation

```css
/* ❌ BREAKS: long titles push layout */
.card-title {
    font-size: 1.2rem;
    /* "Premium Handcrafted Artisanal Organic Widget V2.0"
       wraps to 3 lines, pushing everything down */
}

/* ✅ FIXED: single line truncation */
.card-title {
    font-size: 1.2rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;  /* "Premium Handcrafted Artisan..." */
}

/* ✅ FIXED: multi-line truncation (show up to 2 lines) */
.card-title {
    font-size: 1.2rem;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    /* "Premium Handcrafted
        Artisanal Organic..." */
}

/* ❌ BREAKS: long unbreakable strings (URLs, codes) */
/* "SKU-ABCDEFGHIJKLMNOPQRSTUVWXYZ" overflows container */

/* ✅ FIXED: force word break for long strings */
.card-description {
    overflow-wrap: break-word;   /* Break long words */
    word-break: break-word;      /* Fallback */
    hyphens: auto;               /* Add hyphens at break points */
}
```

## Fix 3: Inconsistent Images

```css
/* ❌ BREAKS: images stretch or squash */
.card img {
    width: 100%;
    height: 200px;
    /* 16:9 image → stretched to fill
       1:1 image → squashed to 200px tall
       Tall image → distorted */
}

/* ✅ FIXED: consistent aspect ratio with object-fit */
.card-image {
    width: 100%;
    height: 200px;
    object-fit: cover;     /* Crop to fill, maintain aspect ratio */
    /* All images appear as 200px tall rectangles
       regardless of original dimensions */
}

/* ✅ ALTERNATIVE: aspect-ratio (modern CSS) */
.card-image {
    width: 100%;
    aspect-ratio: 16 / 9;  /* Always 16:9 regardless of content */
    object-fit: cover;
}
```

## Fix 4: Grid/Flexbox for Variable Content

```css
/* ❌ BREAKS: grid with fixed row height */
.card-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    grid-template-rows: 300px;  /* All rows forced to 300px */
}

/* ✅ FIXED: auto rows (each row sized to tallest card) */
.card-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    grid-auto-rows: auto;      /* Rows size to content */
    gap: 1rem;
    align-items: start;         /* Cards don't stretch to row height */
}

/* ✅ ALTERNATIVE: Masonry-like layout (if unequal heights are desired) */
.card-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    grid-template-rows: masonry;  /* CSS Masonry (limited browser support) */
}

/* ✅ PRACTICAL: flexbox with consistent card heights */
.card-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
}
.card {
    flex: 0 1 calc(33.333% - 1rem);
    display: flex;
    flex-direction: column;
}
.card-description {
    flex: 1;  /* Description takes remaining space — cards align at bottom */
}
.card-footer {
    margin-top: auto;  /* Footer always at bottom regardless of content */
}
```

## The Real Fix: Test With Adversarial Data

```
Create test data that BREAKS your layout:

  Title: ""                          (empty)
  Title: "A"                         (1 character)
  Title: "Premium Handcrafted..."    (100 characters)
  Description: ""                    (empty)
  Description: (500 words)           (very long)
  Description: "aaaaaa...aaa"        (one long unbreakable word)
  Image: 16:9                        (landscape)
  Image: 1:1                         (square)
  Image: 9:16                        (portrait)
  Image: 50x50px                     (tiny)
  Image: 4000x3000px                 (huge)
  Image: none                        (missing)
  Tags: 0 tags                       (empty list)
  Tags: 20 tags                      (overflow)

If your layout survives ALL of these, it'll survive real users.
```

## Defensive CSS Checklist

```css
/* Apply these to ANY component that displays user content: */

.user-content-container {
    overflow-wrap: break-word;       /* Break long words */
    min-width: 0;                    /* Prevent flex/grid blowout */
}

.user-content-container img {
    max-width: 100%;                 /* Images don't exceed container */
    height: auto;                    /* Maintain aspect ratio */
}

.user-content-container pre {
    overflow-x: auto;               /* Code blocks scroll horizontally */
    max-width: 100%;
}
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
