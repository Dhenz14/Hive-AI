"""
Multi-turn conversation training pairs - Performance optimization
Covers: profiling -> identify bottleneck -> fix -> verify -> next bottleneck
Mix of backend and frontend performance
"""

pairs = [
    {
        "instruction": r'''[Previous conversation]
User: My Python API endpoint takes 3-4 seconds to respond. It fetches user data with their recent orders and recommendations. How do I figure out what is slow?
Assistant: Start by profiling to identify the bottleneck rather than guessing. Use cProfile for CPU profiling and line_profiler for line-by-line analysis. You can also add simple timing decorators to measure each section.

[Current message]
User: Show me how to profile my Flask endpoint. Here is the code:

@app.route('/api/dashboard/<int:user_id>')
def user_dashboard(user_id):
    user = User.query.get(user_id)
    orders = Order.query.filter_by(user_id=user_id).order_by(Order.created_at.desc()).limit(20).all()
    for order in orders:
        order.items = OrderItem.query.filter_by(order_id=order.id).all()
        for item in order.items:
            item.product = Product.query.get(item.product_id)
    recommendations = get_recommendations(user_id)
    return jsonify({
        'user': user.to_dict(),
        'orders': [o.to_dict() for o in orders],
        'recommendations': recommendations,
    })''',
        "output": r'''I can already spot the problem, but let me show you how to profile systematically so you can diagnose future issues.

Add a timing context manager to your Flask app:

```python
import time
import functools
import logging

logger = logging.getLogger(__name__)

class Timer:
    def __init__(self, timings, label):
        self.timings = timings
        self.label = label

    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.timings[self.label] = time.perf_counter() - self.start
```

Now instrument your endpoint:

```python
@app.route('/api/dashboard/<int:user_id>')
def user_dashboard(user_id):
    timings = {}

    with Timer(timings, 'fetch_user'):
        user = User.query.get(user_id)

    with Timer(timings, 'fetch_orders'):
        orders = Order.query.filter_by(user_id=user_id) \
            .order_by(Order.created_at.desc()).limit(20).all()

    with Timer(timings, 'fetch_order_items'):
        for order in orders:
            order.items = OrderItem.query.filter_by(order_id=order.id).all()
            for item in order.items:
                item.product = Product.query.get(item.product_id)

    with Timer(timings, 'recommendations'):
        recommendations = get_recommendations(user_id)

    with Timer(timings, 'serialize'):
        result = jsonify({
            'user': user.to_dict(),
            'orders': [o.to_dict() for o in orders],
            'recommendations': recommendations,
        })

    breakdown = ' | '.join(
        '%s: %.3fs' % (k, v) for k, v in timings.items()
    )
    logger.info('Dashboard timings: %s', breakdown)
    return result
```

You will see output like:

```
Dashboard timings: fetch_user: 0.002s | fetch_orders: 0.015s | fetch_order_items: 2.800s | recommendations: 0.580s | serialize: 0.024s
```

The `fetch_order_items` section is almost certainly your bottleneck. This is the classic N+1 query problem -- for 20 orders with 5 items each, you make 20 + 100 = 120 separate database queries. Each query has network overhead even if the query itself is fast. The fix is eager loading with SQLAlchemy's joinedload or subqueryload.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: I profiled my dashboard endpoint and you were right -- fetch_order_items takes 2.8 seconds because of the N+1 query problem. It runs 120+ SQL queries for 20 orders.
Assistant: The fix is eager loading -- use SQLAlchemy's joinedload or subqueryload to fetch related data in one or two queries instead of 120. For nested relationships like orders -> items -> products, subqueryload is usually better for the one-to-many side.

[Current message]
User: Show me how to fix the N+1 problem in my dashboard endpoint. I have orders, each with order_items, each with a product.''',
        "output": r'''Since we identified 120+ queries coming from the nested loop, here is the fix using eager loading.

Before (your current code -- 120+ queries):

```python
orders = Order.query.filter_by(user_id=user_id).limit(20).all()
for order in orders:
    order.items = OrderItem.query.filter_by(order_id=order.id).all()
    for item in order.items:
        item.product = Product.query.get(item.product_id)
```

After (3 queries total):

```python
from sqlalchemy.orm import joinedload, subqueryload

orders = (
    Order.query
    .filter_by(user_id=user_id)
    .options(
        subqueryload(Order.items)
        .joinedload(OrderItem.product)
    )
    .order_by(Order.created_at.desc())
    .limit(20)
    .all()
)
```

Why these specific strategies:

- **subqueryload(Order.items)** -- fires a second query with IN clause: `SELECT * FROM order_items WHERE order_id IN (1, 2, ..., 20)`. Better for one-to-many because a JOIN would duplicate order rows.

- **joinedload(OrderItem.product)** -- adds a JOIN to the items query. Better for many-to-one (each item has one product) since it adds no extra rows.

Your complete fixed endpoint:

```python
@app.route('/api/dashboard/<int:user_id>')
def user_dashboard(user_id):
    user = User.query.get_or_404(user_id)

    orders = (
        Order.query
        .filter_by(user_id=user_id)
        .options(
            subqueryload(Order.items)
            .joinedload(OrderItem.product)
        )
        .order_by(Order.created_at.desc())
        .limit(20)
        .all()
    )

    recommendations = get_recommendations(user_id)

    return jsonify({
        'user': user.to_dict(),
        'orders': [o.to_dict() for o in orders],
        'recommendations': recommendations,
    })
```

Expected result: fetch_order_items drops from 2.8s to about 0.05s. Total queries drop from 120+ to 3. Re-run profiling to confirm, then we can tackle get_recommendations() which was taking 0.58s.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: The eager loading fix worked. fetch_order_items went from 2.8s to 0.04s. Now the bottleneck is get_recommendations() at 0.58s.
Assistant: Let me see the code for that function so we can profile it.

User: Here it is:

def get_recommendations(user_id):
    user_orders = Order.query.filter_by(user_id=user_id).all()
    purchased_ids = set()
    for order in user_orders:
        for item in order.items:
            purchased_ids.add(item.product_id)
    all_products = Product.query.all()
    scores = []
    for product in all_products:
        if product.id in purchased_ids:
            continue
        score = calculate_similarity(product, purchased_ids)
        scores.append((product, score))
    scores.sort(key=lambda x: x[1], reverse=True)
    return [p.to_dict() for p, s in scores[:10]]

[Current message]
User: How do I optimize this? We have about 5000 products in the database.''',
        "output": r'''Since we have already optimized the database queries in the dashboard endpoint, the recommendations function has two problems: it loads all 5000 products into Python and it computes similarity scores in a Python loop. Here is how to fix both.

Problem 1 -- Loading all products just to score them:

```python
# SLOW: loads 5000 Product ORM objects into memory
all_products = Product.query.all()
```

Problem 2 -- Python loop over 5000 items for something the database could do.

Solution -- Cache recommendations and move heavy computation out of the request:

```python
import redis
import json
from datetime import timedelta

cache = redis.Redis(host='localhost', port=6379, db=0)

def get_recommendations(user_id):
    # Check cache first
    cache_key = 'recs:%d' % user_id
    cached = cache.get(cache_key)
    if cached:
        return json.loads(cached)

    # Get products the user already bought (single query)
    purchased_ids = set(
        row[0] for row in
        db.session.query(OrderItem.product_id)
        .join(Order, OrderItem.order_id == Order.id)
        .filter(Order.user_id == user_id)
        .distinct()
        .all()
    )

    # Get top-selling products the user has NOT bought
    # Let the database do the heavy lifting
    top_products = (
        db.session.query(
            Product,
            db.func.count(OrderItem.id).label('popularity')
        )
        .join(OrderItem, OrderItem.product_id == Product.id)
        .filter(Product.id.notin_(purchased_ids) if purchased_ids else True)
        .group_by(Product.id)
        .order_by(db.text('popularity DESC'))
        .limit(10)
        .all()
    )

    result = [p.to_dict() for p, _ in top_products]

    # Cache for 1 hour -- recommendations do not need to be real-time
    cache.setex(cache_key, timedelta(hours=1), json.dumps(result))

    return result
```

Key improvements:

1. **Single query for purchased IDs** -- instead of loading full Order objects and looping, one query gets just the product IDs.

2. **Database-side ranking** -- instead of loading 5000 products into Python and scoring them, let PostgreSQL count and sort. The database is much faster at this.

3. **Redis caching** -- recommendations change slowly, so caching for 1 hour means most requests skip the computation entirely. Cache response time is under 1ms vs 580ms.

4. **Invalidate on purchase** -- when a user places a new order, clear their cache:

```python
def place_order(user_id, items):
    # ... save order logic ...
    cache.delete('recs:%d' % user_id)
```

After these changes, the recommendations function should take under 5ms (cache hit) or under 50ms (cache miss with database query). Combined with the eager loading fix, your dashboard endpoint should be under 100ms total.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: My React app is slow on initial load. Lighthouse says Time to Interactive is 8 seconds. The JavaScript bundle is 2.4 MB.
Assistant: 2.4 MB is way too large. The first step is to analyze what is in the bundle. Use webpack-bundle-analyzer or the built-in tools for Vite/CRA to visualize which packages are taking up space.

[Current message]
User: I ran the bundle analyzer. Here are the biggest chunks: moment.js (500KB), lodash (300KB), chart.js (250KB), and my own code is about 400KB. The rest is React and other dependencies. What should I fix first?''',
        "output": r'''Since the bundle analyzer showed your biggest offenders, let us tackle them in order of impact.

1. **Replace moment.js (500KB -> 2KB)**

moment.js includes every locale by default. Replace it with day.js, which has the same API but is 2KB:

```bash
npm install dayjs
npm uninstall moment
```

```javascript
// Before
import moment from 'moment';
const formatted = moment(date).format('MMM D, YYYY');
const relative = moment(date).fromNow();

// After
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
dayjs.extend(relativeTime);

const formatted = dayjs(date).format('MMM D, YYYY');
const relative = dayjs(date).fromNow();
```

2. **Tree-shake lodash (300KB -> ~10KB)**

You are probably importing all of lodash. Switch to individual imports:

```javascript
// WRONG: imports entire 300KB library
import _ from 'lodash';
_.debounce(fn, 300);

// RIGHT: imports only what you use (~2KB)
import debounce from 'lodash/debounce';
debounce(fn, 300);

// Or use lodash-es for automatic tree-shaking
// npm install lodash-es
import { debounce } from 'lodash-es';
```

3. **Lazy-load chart.js (250KB -> 0KB initial)**

Charts are probably not visible on first load, so lazy-load them:

```javascript
// Before: chart.js is in the main bundle
import { Chart } from 'chart.js';

// After: chart.js loads only when the chart component mounts
import { lazy, Suspense } from 'react';

const ChartDashboard = lazy(() => import('./ChartDashboard'));

function Dashboard() {
    return (
        <div>
            <UserInfo />
            <OrderList />
            <Suspense fallback={<div>Loading charts...</div>}>
                <ChartDashboard />
            </Suspense>
        </div>
    );
}
```

4. **Split your own code (400KB) with route-based code splitting:**

```javascript
import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';

const Home = lazy(() => import('./pages/Home'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Settings = lazy(() => import('./pages/Settings'));
const AdminPanel = lazy(() => import('./pages/AdminPanel'));

function App() {
    return (
        <BrowserRouter>
            <Suspense fallback={<div>Loading...</div>}>
                <Routes>
                    <Route path="/" element={<Home />} />
                    <Route path="/dashboard" element={<Dashboard />} />
                    <Route path="/settings" element={<Settings />} />
                    <Route path="/admin" element={<AdminPanel />} />
                </Routes>
            </Suspense>
        </BrowserRouter>
    );
}
```

Expected results:
- moment.js -> dayjs: saves 498KB
- lodash tree-shaking: saves ~290KB
- chart.js lazy load: saves 250KB from initial load
- Route splitting: saves ~200KB from initial load

Your initial bundle should drop from 2.4MB to about 700KB, which should bring TTI under 3 seconds.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: I reduced my React bundle from 2.4MB to 750KB by replacing moment.js, tree-shaking lodash, and adding code splitting. TTI is down to 3.5 seconds. Can I do better?
Assistant: Nice progress. The next optimizations are: enable gzip/brotli compression on your server, add proper cache headers, and look at render performance. Compression alone can cut that 750KB to about 200KB over the wire.

User: I enabled brotli compression on nginx and the transferred size is now 210KB. TTI is 2.8 seconds. But the page still feels sluggish -- there is a visible delay when switching between tabs on the dashboard.
Assistant: That sounds like a rendering performance issue, not a loading issue. The tab switching might be re-rendering expensive components. Let me help you profile the React rendering.

[Current message]
User: How do I profile React rendering performance? The Dashboard component has a lot of data tables and charts.''',
        "output": r'''Since the loading performance is now good at 210KB transferred, the sluggishness when switching tabs is a rendering issue. Here is how to diagnose and fix it.

Step 1 -- Use React DevTools Profiler:

Open Chrome DevTools -> Profiler tab (from React DevTools extension). Click Record, switch tabs a few times, then stop. Look for:
- Components that re-render when they should not
- Components with long render times (red/yellow bars)

Step 2 -- Add a render counter to suspect components:

```javascript
import { useRef } from 'react';

function useRenderCount(componentName) {
    const count = useRef(0);
    count.current += 1;
    console.log(componentName + ' rendered: ' + count.current + ' times');
}

function DataTable({ data, columns }) {
    useRenderCount('DataTable');
    // ... renders a big table
}
```

Step 3 -- Common fix: memoize expensive components:

```javascript
import { memo, useMemo, useCallback } from 'react';

// Wrap components that receive the same props but re-render anyway
const DataTable = memo(function DataTable({ data, columns, onRowClick }) {
    // Only re-renders when data, columns, or onRowClick actually change
    const sortedData = useMemo(() => {
        return [...data].sort((a, b) => a.name.localeCompare(b.name));
    }, [data]);

    return (
        <table>
            <thead>
                <tr>
                    {columns.map(col => (
                        <th key={col.key}>{col.label}</th>
                    ))}
                </tr>
            </thead>
            <tbody>
                {sortedData.map(row => (
                    <tr key={row.id} onClick={() => onRowClick(row.id)}>
                        {columns.map(col => (
                            <td key={col.key}>{row[col.key]}</td>
                        ))}
                    </tr>
                ))}
            </tbody>
        </table>
    );
});
```

Step 4 -- Fix the tab switching issue specifically:

```javascript
function Dashboard() {
    const [activeTab, setActiveTab] = useState('overview');

    // WRONG: re-creates callback on every render, breaking memo
    // const handleRowClick = (id) => navigate('/order/' + id);

    // RIGHT: stable reference
    const handleRowClick = useCallback((id) => {
        navigate('/order/' + id);
    }, []);

    return (
        <div>
            <TabBar active={activeTab} onChange={setActiveTab} />

            {/* Only render the active tab's content */}
            {activeTab === 'overview' && <OverviewPanel />}
            {activeTab === 'orders' && (
                <DataTable
                    data={orders}
                    columns={orderColumns}
                    onRowClick={handleRowClick}
                />
            )}
            {activeTab === 'analytics' && <AnalyticsCharts />}
        </div>
    );
}
```

Step 5 -- For very large tables (1000+ rows), use virtualization:

```javascript
import { useVirtual } from '@tanstack/react-virtual';

function VirtualizedTable({ data, columns }) {
    const parentRef = useRef(null);

    const rowVirtualizer = useVirtual({
        size: data.length,
        parentRef,
        estimateSize: useCallback(() => 40, []),
    });

    return (
        <div ref={parentRef} style={{ height: '500px', overflow: 'auto' }}>
            <div style={{ height: rowVirtualizer.totalSize + 'px', position: 'relative' }}>
                {rowVirtualizer.virtualItems.map(virtualRow => {
                    const row = data[virtualRow.index];
                    return (
                        <div
                            key={row.id}
                            style={{
                                position: 'absolute',
                                top: virtualRow.start + 'px',
                                height: '40px',
                                width: '100%',
                            }}
                        >
                            {columns.map(col => (
                                <span key={col.key}>{row[col.key]}</span>
                            ))}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
```

Virtualization renders only the visible rows (maybe 15-20) instead of all 1000+. This is usually the single biggest rendering performance win for data-heavy pages.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: My Python backend processes uploaded CSV files. Users upload files with 100K-1M rows. The processing takes 30-60 seconds and the request times out.
Assistant: Processing large files synchronously in a web request is a bad pattern. You should move the processing to a background task queue like Celery. The upload endpoint accepts the file, enqueues a task, and returns immediately with a task ID. The client polls for status.

User: I set up Celery with Redis as the broker. But the actual CSV processing is still slow -- 45 seconds for 500K rows. Can we make the processing itself faster?
Assistant: What does the processing involve? The bottleneck is usually in how you read and transform the data, not in Celery itself.

[Current message]
User: Here is the processing code:

import csv

def process_csv(filepath):
    results = []
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            cleaned = clean_row(row)
            if validate_row(cleaned):
                transformed = transform_row(cleaned)
                results.append(transformed)
    save_to_database(results)
    return len(results)

Each row needs cleaning (strip whitespace, normalize dates), validation, and transformation. What can I do to speed this up?''',
        "output": r'''Since the processing is already in a Celery background task, we need to optimize the processing itself. There are several problems with the current approach.

Problem 1 -- csv.DictReader is slow. It creates a new dict for every row.
Problem 2 -- Building a list of 500K transformed rows in memory.
Problem 3 -- Single save_to_database call with 500K rows.

Here is the optimized version:

```python
import csv
import io
from itertools import islice

def process_csv(filepath):
    total = 0
    batch = []
    batch_size = 5000

    with open(filepath, 'r', buffering=1024*1024) as f:
        # Read header once
        reader = csv.reader(f)
        header = next(reader)
        col_map = {name: idx for idx, name in enumerate(header)}

        for row in reader:
            cleaned = clean_row_fast(row, col_map)
            if cleaned is None:
                continue
            batch.append(cleaned)

            if len(batch) >= batch_size:
                save_batch(batch)
                total += len(batch)
                batch = []

    # Save remaining rows
    if batch:
        save_batch(batch)
        total += len(batch)

    return total

def clean_row_fast(row, col_map):
    # Access by index instead of dict key -- much faster
    try:
        name = row[col_map['name']].strip()
        email = row[col_map['email']].strip().lower()
        date_str = row[col_map['date']].strip()

        if not name or not email:
            return None

        # Inline validation instead of separate function call
        if '@' not in email:
            return None

        return (name, email, normalize_date(date_str))
    except (IndexError, ValueError):
        return None

def save_batch(batch):
    # Use executemany or COPY for bulk insert
    from psycopg2.extras import execute_values
    conn = get_db_connection()
    cur = conn.cursor()
    execute_values(
        cur,
        'INSERT INTO imports (name, email, date) VALUES %s '
        'ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name',
        batch,
        page_size=1000
    )
    conn.commit()
    cur.close()
```

If you need even more speed, use pandas:

```python
import pandas as pd

def process_csv_pandas(filepath):
    # Read in chunks to limit memory usage
    total = 0
    for chunk in pd.read_csv(filepath, chunksize=50000):
        # Vectorized operations -- process all rows at once
        chunk['name'] = chunk['name'].str.strip()
        chunk['email'] = chunk['email'].str.strip().str.lower()

        # Filter invalid rows (vectorized)
        valid = chunk[
            chunk['name'].notna() &
            chunk['email'].str.contains('@', na=False)
        ]

        # Bulk insert the chunk
        from sqlalchemy import create_engine
        engine = create_engine(DATABASE_URL)
        valid.to_sql('imports', engine, if_exists='append',
                     index=False, method='multi', chunksize=1000)

        total += len(valid)

    return total
```

Performance comparison for 500K rows:
- Original (csv.DictReader + single insert): ~45 seconds
- Optimized csv.reader + batch insert: ~8 seconds
- Pandas with chunked read: ~5 seconds

The key wins are: csv.reader is 2-3x faster than DictReader, batch inserts with execute_values are 10x faster than individual inserts, and processing in chunks limits memory to about 50MB instead of loading everything into a list.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: My API response times are good (under 200ms) but the server can only handle about 50 concurrent requests before response times spike to 5+ seconds. I am using Flask with gunicorn, 4 workers.
Assistant: With 4 synchronous gunicorn workers, you can handle exactly 4 concurrent requests. Request 5 waits until one of the first 4 finishes. For I/O-bound workloads, switch to async workers or increase worker count. What does your server have for CPU and RAM?

User: 4 CPU cores, 8GB RAM. Most endpoints do database queries and external API calls -- definitely I/O-bound.
Assistant: For I/O-bound work, you have two good options: gevent workers (monkey-patched async) or switch to an async framework. Gevent is the easiest since you keep your Flask code. With gevent each worker can handle hundreds of concurrent connections.

[Current message]
User: Show me how to configure gunicorn with gevent workers. Also, are there any gotchas I should know about?''',
        "output": r'''Since your workload is I/O-bound with database queries and external API calls, gevent workers will dramatically increase concurrency. Here is the setup.

Step 1 -- Install gevent:

```bash
pip install gevent
```

Step 2 -- Create a gunicorn config file:

```python
# gunicorn.conf.py

# Worker class -- gevent for async I/O
worker_class = 'gevent'

# Number of worker processes (1-2x CPU cores)
workers = 4

# Concurrent connections per worker
worker_connections = 200

# Total capacity: 4 workers * 200 connections = 800 concurrent requests

# Bind address
bind = '0.0.0.0:5000'

# Timeout for worker response (increase for long-running requests)
timeout = 120

# Graceful restart timeout
graceful_timeout = 30

# Max requests before worker restart (prevents memory leaks)
max_requests = 2000
max_requests_jitter = 200

# Logging
accesslog = '-'
errorlog = '-'
loglevel = 'info'

# Preload app for faster worker startup and shared memory
preload_app = True
```

Step 3 -- Run it:

```bash
gunicorn -c gunicorn.conf.py app:app
```

Step 4 -- Important gotchas and fixes:

```python
# Gotcha 1: psycopg2 is not gevent-compatible by default
# Use psycogreen to patch it
# pip install psycogreen

# In your app startup:
from psycogreen.gevent import patch_psycopg
patch_psycopg()

# Gotcha 2: Connection pool sizing
# With gevent, one worker can have 200 concurrent greenlets
# Each might need a database connection
# Set pool_size to match expected concurrent DB queries

from sqlalchemy import create_engine
engine = create_engine(
    DATABASE_URL,
    pool_size=20,        # Base pool connections
    max_overflow=10,     # Extra connections when pool is full
    pool_timeout=10,     # Wait up to 10s for a connection
    pool_pre_ping=True,  # Verify connections are alive
)

# Gotcha 3: Monkey patching must happen FIRST
# If using gevent, add this at the very top of your entry point
from gevent import monkey
monkey.patch_all()
# This must be before importing anything else

# Gotcha 4: requests library works with gevent but has a gotcha
# Set timeouts on ALL external API calls
import requests
response = requests.get(url, timeout=(5, 30))
# (connect_timeout, read_timeout) -- without this, a hanging
# external service blocks a greenlet forever
```

Step 5 -- Update your Dockerfile:

```dockerfile
CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:app"]
```

Before: 4 sync workers = 4 concurrent requests.
After: 4 gevent workers * 200 connections = 800 concurrent requests.

The server uses the same 4 CPU cores and similar RAM. Gevent uses cooperative multitasking (greenlets), so while one greenlet waits for a database response, another greenlet handles a different request. This is why it works so well for I/O-bound workloads.

Monitor with: `curl localhost:5000/health` under load and watch `top` for CPU and memory. If CPU hits 100%, you are CPU-bound and need more workers or a faster framework.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: My API endpoint returns a large JSON response (2MB) for a data export feature. It takes 3 seconds to serialize and transfer. How can I make this faster?
Assistant: 2MB of JSON is a lot. Several approaches: streaming the response instead of building it all in memory, compressing the response with gzip, paginating the data, or using a more efficient format like CSV for bulk exports.

User: The client needs JSON format. Can I at least stream it so the response starts immediately instead of waiting 3 seconds?
Assistant: Yes -- Flask supports streaming responses with generators. Instead of building the entire JSON array in memory, you can stream it chunk by chunk. The client starts receiving data immediately.

[Current message]
User: Show me how to stream a large JSON response in Flask. The data comes from a database query that returns about 50,000 rows.''',
        "output": r'''Since the client needs JSON and we want to avoid building 2MB in memory, here is how to stream the response.

```python
import json
from flask import Response, stream_with_context

@app.route('/api/export/orders')
def export_orders():
    def generate():
        # Start the JSON array
        yield '[\n'

        # Query with server-side cursor to avoid loading all rows
        query = (
            Order.query
            .options(
                subqueryload(Order.items)
                .joinedload(OrderItem.product)
            )
            .order_by(Order.created_at.desc())
            .yield_per(500)  # Fetch 500 rows at a time
        )

        first = True
        for order in query:
            if not first:
                yield ',\n'
            first = False

            row = {
                'id': order.id,
                'date': order.created_at.isoformat(),
                'total': float(order.total),
                'items': [
                    {
                        'product': item.product.name,
                        'quantity': item.quantity,
                        'price': float(item.price),
                    }
                    for item in order.items
                ],
            }
            yield json.dumps(row)

        yield '\n]'

    return Response(
        stream_with_context(generate()),
        mimetype='application/json',
        headers={
            'Content-Disposition': 'attachment; filename=orders.json',
            'X-Content-Type-Options': 'nosniff',
        }
    )
```

Add gzip compression for the streamed response:

```python
import gzip

@app.route('/api/export/orders')
def export_orders():
    def generate():
        yield '[\n'
        first = True
        for order in Order.query.yield_per(500):
            if not first:
                yield ',\n'
            first = False
            yield json.dumps(order.to_export_dict())
        yield '\n]'

    def compress(gen):
        # Compress chunks as they are generated
        buf = b''
        compressor = gzip.open(io.BytesIO(), 'wb')
        for chunk in gen:
            buf += chunk.encode('utf-8')
            if len(buf) >= 8192:
                yield gzip.compress(buf)
                buf = b''
        if buf:
            yield gzip.compress(buf)

    # Check if client accepts gzip
    from flask import request
    if 'gzip' in request.headers.get('Accept-Encoding', ''):
        return Response(
            stream_with_context(compress(generate())),
            mimetype='application/json',
            headers={
                'Content-Encoding': 'gzip',
                'Content-Disposition': 'attachment; filename=orders.json',
            }
        )

    return Response(
        stream_with_context(generate()),
        mimetype='application/json',
    )
```

Even simpler -- use Flask's built-in after_request compression or let nginx handle gzip. But the streaming approach alone gives you these benefits:

1. **Time to first byte** drops from 3 seconds to under 100ms -- the client starts receiving data immediately.

2. **Memory usage** stays constant regardless of data size -- you never hold all 50K rows in memory. `yield_per(500)` tells SQLAlchemy to fetch rows in batches of 500 using a server-side cursor.

3. **2MB JSON with gzip** compresses to about 200-300KB over the wire.

For truly large exports (millions of rows), consider generating a file asynchronously with Celery and giving the user a download link when it is ready, rather than streaming from a web request.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: My Django app has a page that shows aggregated statistics -- total sales per day for the last 90 days, top 10 products, and active user count. It takes 4 seconds to load.
Assistant: Aggregation queries on large tables are inherently expensive. The typical solution is to pre-compute the aggregates and serve them from cache or a materialized view. Let me see the queries.

User: Here are the three queries:
1. SELECT date_trunc('day', created_at) as day, SUM(total) FROM orders WHERE created_at > now() - interval '90 days' GROUP BY 1 ORDER BY 1
2. SELECT product_id, SUM(quantity) as total_qty FROM order_items GROUP BY product_id ORDER BY total_qty DESC LIMIT 10
3. SELECT COUNT(DISTINCT user_id) FROM sessions WHERE last_active > now() - interval '30 minutes'

Each takes about 1.2-1.5 seconds.

[Current message]
User: How do I cache these statistics? They do not need to be real-time -- 5-minute-old data is fine.''',
        "output": r'''Since 5-minute staleness is acceptable for all three queries, we can use a combination of Django's cache framework and PostgreSQL materialized views.

Option 1 -- Django cache (simplest):

```python
# stats/services.py
from django.core.cache import cache
from django.db import connection

STATS_CACHE_TTL = 300  # 5 minutes

def get_daily_sales():
    cache_key = 'stats:daily_sales_90d'
    result = cache.get(cache_key)
    if result is not None:
        return result

    with connection.cursor() as cur:
        cur.execute("""
            SELECT date_trunc('day', created_at)::date AS day,
                   SUM(total)::float AS revenue
            FROM orders
            WHERE created_at > NOW() - INTERVAL '90 days'
            GROUP BY 1 ORDER BY 1
        """)
        result = [
            {'day': str(row[0]), 'revenue': row[1]}
            for row in cur.fetchall()
        ]

    cache.set(cache_key, result, STATS_CACHE_TTL)
    return result

def get_top_products():
    cache_key = 'stats:top_products'
    result = cache.get(cache_key)
    if result is not None:
        return result

    with connection.cursor() as cur:
        cur.execute("""
            SELECT p.id, p.name, SUM(oi.quantity)::int AS total_qty
            FROM order_items oi
            JOIN products p ON oi.product_id = p.id
            GROUP BY p.id, p.name
            ORDER BY total_qty DESC
            LIMIT 10
        """)
        result = [
            {'id': row[0], 'name': row[1], 'quantity': row[2]}
            for row in cur.fetchall()
        ]

    cache.set(cache_key, result, STATS_CACHE_TTL)
    return result

def get_active_users():
    cache_key = 'stats:active_users'
    result = cache.get(cache_key)
    if result is not None:
        return result

    with connection.cursor() as cur:
        cur.execute("""
            SELECT COUNT(DISTINCT user_id)
            FROM sessions
            WHERE last_active > NOW() - INTERVAL '30 minutes'
        """)
        result = cur.fetchone()[0]

    cache.set(cache_key, result, STATS_CACHE_TTL)
    return result
```

Option 2 -- Pre-warm the cache with a periodic task (better):

```python
# stats/tasks.py
from celery import shared_task

@shared_task
def refresh_dashboard_stats():
    # Force refresh -- delete old cache and recompute
    from django.core.cache import cache
    cache.delete('stats:daily_sales_90d')
    cache.delete('stats:top_products')
    cache.delete('stats:active_users')

    # These calls will recompute and cache
    get_daily_sales()
    get_top_products()
    get_active_users()
```

```python
# celery beat schedule in settings.py
CELERY_BEAT_SCHEDULE = {
    'refresh-dashboard-stats': {
        'task': 'stats.tasks.refresh_dashboard_stats',
        'schedule': 300.0,  # Every 5 minutes
    },
}
```

Option 3 -- PostgreSQL materialized views (best for complex queries):

```sql
CREATE MATERIALIZED VIEW mv_daily_sales AS
SELECT date_trunc('day', created_at)::date AS day,
       SUM(total) AS revenue,
       COUNT(*) AS order_count
FROM orders
WHERE created_at > NOW() - INTERVAL '90 days'
GROUP BY 1
ORDER BY 1;

CREATE UNIQUE INDEX ON mv_daily_sales(day);

-- Refresh every 5 minutes via pg_cron or Celery
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_sales;
```

The CONCURRENTLY keyword means reads are not blocked during refresh. The unique index is required for concurrent refresh.

I would use Option 2 for your case -- Celery beat pre-warms the cache every 5 minutes, so no user ever hits a cold cache. The dashboard loads in under 10ms (three Redis cache lookups) instead of 4 seconds.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: My Python function processes a list of 100,000 items and it is slow. It takes about 15 seconds. I am checking each item against a set of rules.
Assistant: Without seeing the code, common causes are: O(n^2) algorithms hidden in the logic, unnecessary object creation, or calling slow functions in a loop. Can you share the code?

User: Here it is:

def process_items(items, rules):
    results = []
    for item in items:
        matches = []
        for rule in rules:
            if rule_matches(item, rule):
                matches.append(rule['name'])
        if matches:
            results.append({'item': item, 'matched_rules': matches})
    return results

We have about 500 rules. So 100,000 items * 500 rules = 50 million checks.

[Current message]
User: 50 million checks in Python sounds bad. How do I speed this up without rewriting in C?''',
        "output": r'''Since you have 100K items times 500 rules = 50M iterations in pure Python, there are several strategies to dramatically speed this up without leaving Python.

Strategy 1 -- Reduce iterations with rule indexing:

```python
from collections import defaultdict

def build_rule_index(rules):
    # Group rules by their primary check field
    # Instead of checking all 500 rules per item,
    # only check rules that could possibly match
    index = defaultdict(list)
    for rule in rules:
        key_field = rule.get('field', '_default')
        key_value = rule.get('value')
        if key_value is not None:
            index[(key_field, key_value)].append(rule)
        else:
            index['_default'].append(rule)
    return index

def process_items_indexed(items, rules):
    rule_index = build_rule_index(rules)
    default_rules = rule_index.get('_default', [])
    results = []

    for item in items:
        matches = []

        # Only check rules that match this item's fields
        for field, value in item.items():
            key = (field, value)
            if key in rule_index:
                for rule in rule_index[key]:
                    if rule_matches(item, rule):
                        matches.append(rule['name'])

        # Always check default (non-indexed) rules
        for rule in default_rules:
            if rule_matches(item, rule):
                matches.append(rule['name'])

        if matches:
            results.append({'item': item, 'matched_rules': matches})

    return results
```

If each item matches only a few rule groups, this can turn 50M checks into 1-5M checks.

Strategy 2 -- Use numpy/pandas for vectorized rule evaluation:

```python
import pandas as pd
import numpy as np

def process_items_vectorized(items, rules):
    df = pd.DataFrame(items)

    matched = pd.DataFrame(index=df.index)

    for rule in rules:
        field = rule['field']
        op = rule['operator']
        value = rule['value']

        if op == 'equals':
            mask = df[field] == value
        elif op == 'greater_than':
            mask = df[field] > value
        elif op == 'contains':
            mask = df[field].str.contains(value, na=False)
        elif op == 'in':
            mask = df[field].isin(value)
        else:
            continue

        matched[rule['name']] = mask

    # Find rows with at least one match
    has_match = matched.any(axis=1)
    results = []
    for idx in matched[has_match].index:
        rule_names = list(matched.columns[matched.loc[idx]])
        results.append({
            'item': items[idx],
            'matched_rules': rule_names,
        })

    return results
```

Pandas operations are implemented in C and operate on entire columns at once. A single `df[field] > value` evaluates 100K comparisons in microseconds vs milliseconds in a Python loop.

Strategy 3 -- Multiprocessing for CPU-bound work:

```python
from multiprocessing import Pool
from functools import partial

def process_chunk(chunk, rules):
    results = []
    for item in chunk:
        matches = []
        for rule in rules:
            if rule_matches(item, rule):
                matches.append(rule['name'])
        if matches:
            results.append({'item': item, 'matched_rules': matches})
    return results

def process_items_parallel(items, rules, num_workers=4):
    chunk_size = len(items) // num_workers
    chunks = [
        items[i:i + chunk_size]
        for i in range(0, len(items), chunk_size)
    ]

    worker = partial(process_chunk, rules=rules)

    with Pool(num_workers) as pool:
        chunk_results = pool.map(worker, chunks)

    # Flatten results
    return [r for chunk in chunk_results for r in chunk]
```

Expected speedups from 15 seconds baseline:
- Rule indexing alone: 2-5 seconds (depends on rule structure)
- Pandas vectorized: 1-2 seconds
- Multiprocessing (4 cores): 4 seconds (linear speedup)
- Indexing + multiprocessing: under 1 second

Start with rule indexing -- it often gives the biggest win because it reduces the algorithmic complexity, not just the constant factor.'''
    },
]
