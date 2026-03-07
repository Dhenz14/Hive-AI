"""
Real-world project help training pairs - Performance tuning real apps
"""

pairs = [
    {
        "instruction": r'''Our Django REST API has an endpoint that takes 4 seconds to respond. It returns a list of products with their categories, reviews, and pricing tiers. I've checked and there are 47 database queries for a page of 20 products. How do I reduce this?''',
        "output": r'''47 queries for 20 products is a textbook N+1 problem. You're loading related objects one at a time instead of in bulk.

Let me guess your current code looks something like this:

```python
class ProductSerializer(serializers.ModelSerializer):
    category = CategorySerializer()
    reviews = ReviewSerializer(many=True)
    pricing_tiers = PricingTierSerializer(many=True)

    class Meta:
        model = Product
        fields = ["id", "name", "category", "reviews", "pricing_tiers"]

class ProductListView(generics.ListAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
```

The problem: DRF serializes each product, which triggers lazy loading for category (1 query per product), reviews (1 query per product), and pricing_tiers (1 query per product). That's 1 + 20*3 = 61 queries minimum. You're seeing 47, so some might be cached.

Fix -- use `select_related` for ForeignKey and `prefetch_related` for reverse/M2M:

```python
class ProductListView(generics.ListAPIView):
    serializer_class = ProductSerializer

    def get_queryset(self):
        return Product.objects.select_related(
            "category",          # ForeignKey -- JOIN
        ).prefetch_related(
            "reviews",           # Reverse FK -- separate query, but just 1
            "pricing_tiers",     # Reverse FK -- separate query, but just 1
        )
```

This reduces 47 queries to exactly 3:
1. SELECT products JOIN categories
2. SELECT reviews WHERE product_id IN (1,2,3,...20)
3. SELECT pricing_tiers WHERE product_id IN (1,2,3,...20)

If you also need nested relations (e.g., review -> user):

```python
from django.db.models import Prefetch

def get_queryset(self):
    return Product.objects.select_related(
        "category",
    ).prefetch_related(
        Prefetch("reviews", queryset=Review.objects.select_related("user").order_by("-created_at")[:5]),
        "pricing_tiers",
    )
```

Verify with django-debug-toolbar or add this to settings for dev:

```python
# settings.py (dev only)
LOGGING = {
    "version": 1,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"django.db.backends": {"handlers": ["console"], "level": "DEBUG"}},
}
```

Expected result: 4 seconds -> under 200ms.'''
    },
    {
        "instruction": r'''I profiled my Python script and found that a function processing a large CSV takes 80% of the time. It loops through 2 million rows, does a dict lookup, and builds an output list. Here's the core loop:

result = []
for row in data:
    key = row['account_id'] + '_' + row['date']
    if key in lookup_dict:
        merged = {**row, **lookup_dict[key]}
        merged['total'] = float(row['amount']) + float(lookup_dict[key].get('adjustment', 0))
        result.append(merged)

The lookup_dict has about 500k entries. This loop takes 45 seconds for 2M rows.''',
        "output": r'''<think>
2M rows, 45 seconds. Let me look at the bottlenecks:
1. String concatenation for the key -- creating a new string each iteration
2. Dict unpacking {**row, **lookup_dict[key]} -- creates a new dict every time
3. float() conversion on every iteration
4. .append() to a list that grows to potentially 2M entries

Let me identify the biggest wins.
</think>

Several targeted optimizations here, no pandas needed:

1. Use a tuple key instead of string concatenation (avoids allocating a new string each iteration):

```python
# BEFORE: key = row['account_id'] + '_' + row['date']
# AFTER:
key = (row['account_id'], row['date'])
```

Rebuild your lookup_dict with tuple keys too:

```python
lookup_dict = {(r['account_id'], r['date']): r for r in lookup_data}
```

2. Avoid repeated dict lookups -- cache the lookup result:

```python
for row in data:
    key = (row['account_id'], row['date'])
    match = lookup_dict.get(key)  # one lookup instead of two
    if match is not None:
        ...
```

3. Avoid double dict unpacking. Only copy what you need:

```python
# BEFORE: merged = {**row, **lookup_dict[key]}  -- copies both dicts
# AFTER: mutate the row dict directly if you don't need the original
row.update(match)
row['total'] = float(row['amount']) + float(match.get('adjustment', 0))
result.append(row)
```

Or if you need the original data intact, copy just once:

```python
merged = row.copy()
merged.update(match)
```

4. Pre-convert amounts to float when loading data, not in the hot loop:

```python
# Do this once during data loading:
for row in data:
    row['amount'] = float(row['amount'])
for key, val in lookup_dict.items():
    if 'adjustment' in val:
        val['adjustment'] = float(val['adjustment'])
```

5. Pre-allocate the result list if you know the approximate size:

```python
result = []
# Not much gain here, but if you want:
# result = [None] * estimated_size  # then use index assignment
```

Putting it all together:

```python
# Pre-convert floats once
for row in data:
    row['amount'] = float(row['amount'])

# Optimized loop
result = []
get = lookup_dict.get  # local variable lookup is faster than attribute lookup
for row in data:
    match = get((row['account_id'], row['date']))
    if match is not None:
        row.update(match)
        row['total'] = row['amount'] + match.get('adjustment', 0.0)
        result.append(row)
```

Expected improvement: 45s down to roughly 8-12 seconds. The biggest wins are the tuple key (no string alloc), single dict lookup via .get(), and avoiding double unpacking.

If you need it even faster, consider using pandas merge -- it uses vectorized C operations internally and would do this in about 1-2 seconds for 2M rows.'''
    },
    {
        "instruction": r'''Our React app has gotten sluggish. The main dashboard re-renders constantly -- React DevTools Profiler shows the component tree re-rendering 8-12 times when I just click one filter button. How do I track down unnecessary re-renders and fix them?''',
        "output": r'''The Profiler is the right tool. Here's a systematic approach to diagnose and fix.

Step 1: Identify WHAT is re-rendering unnecessarily. In React DevTools Profiler:
- Record a single filter click
- Look at the flame chart -- components highlighted in yellow/orange are re-rendering
- Check "Why did this render?" (enable in Profiler settings)

Common causes:

Step 2: Fix inline object/array creation in props:

```jsx
// BAD -- creates a new object every render, child always re-renders
<Chart options={{ showGrid: true, color: "blue" }} data={data} />

// GOOD -- stable reference
const chartOptions = useMemo(() => ({
    showGrid: true,
    color: "blue",
}), []);

<Chart options={chartOptions} data={data} />
```

Step 3: Fix inline function props:

```jsx
// BAD -- new function reference every render
<FilterButton onClick={() => setFilter("active")} />

// GOOD -- stable callback
const handleFilterClick = useCallback(() => {
    setFilter("active");
}, []);

<FilterButton onClick={handleFilterClick} />
```

Step 4: Memoize expensive child components:

```jsx
// If FilterPanel re-renders when it shouldn't:
const FilterPanel = React.memo(function FilterPanel({ filters, onChange }) {
    // Only re-renders when filters or onChange actually change
    return (
        <div>
            {filters.map(f => (
                <button key={f.id} onClick={() => onChange(f.id)}>
                    {f.label}
                </button>
            ))}
        </div>
    );
});
```

Step 5: Fix Redux selector issues. If you're using useSelector, make sure you're not creating new objects:

```jsx
// BAD -- creates a new array every time store updates
const activeUsers = useSelector(state =>
    state.users.filter(u => u.active)
);

// GOOD -- memoized selector
import { createSelector } from "@reduxjs/toolkit";

const selectActiveUsers = createSelector(
    state => state.users,
    users => users.filter(u => u.active)
);

const activeUsers = useSelector(selectActiveUsers);
```

Step 6: Split state to avoid cascade re-renders:

```jsx
// BAD -- one big state object, any change re-renders everything
const [dashState, setDashState] = useState({
    filters: {},
    sortBy: "date",
    page: 1,
    selectedId: null,
});

// GOOD -- separate state for independent concerns
const [filters, setFilters] = useState({});
const [sortBy, setSortBy] = useState("date");
const [page, setPage] = useState(1);
const [selectedId, setSelectedId] = useState(null);
```

Start with the Redux selectors and inline objects -- those cause the most unnecessary re-renders in typical dashboard apps.'''
    },
    {
        "instruction": r'''I have a Python API endpoint that generates PDF reports. It takes about 12 seconds per request. The profiler shows most time is spent in the PDF library (ReportLab) rendering tables with 500+ rows. I can't switch libraries. How do I make this bearable for users?''',
        "output": r'''You have two strategies: make it faster, and make it feel faster. Do both.

Make it feel faster -- move to async generation:

```python
from fastapi import BackgroundTasks
from uuid import uuid4
import json

# In-memory store (use Redis in production)
report_status = {}

@app.post("/api/reports")
async def request_report(params: ReportParams, background_tasks: BackgroundTasks):
    report_id = str(uuid4())
    report_status[report_id] = {"status": "processing", "progress": 0}

    background_tasks.add_task(generate_report_async, report_id, params)

    return {"report_id": report_id, "status_url": f"/api/reports/{report_id}/status"}

@app.get("/api/reports/{report_id}/status")
async def report_status_check(report_id: str):
    status = report_status.get(report_id)
    if not status:
        raise HTTPException(404, "Report not found")
    return status

def generate_report_async(report_id, params):
    try:
        pdf_path = generate_pdf(params, progress_callback=lambda p:
            report_status.update({report_id: {"status": "processing", "progress": p}}))
        report_status[report_id] = {
            "status": "complete",
            "download_url": f"/api/reports/{report_id}/download",
        }
    except Exception as e:
        report_status[report_id] = {"status": "error", "message": str(e)}
```

Make it actually faster -- optimize the PDF generation:

```python
# 1. Reduce table rows per page -- ReportLab is slower with huge tables
def generate_pdf(params, progress_callback=None):
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []

    # Split data into chunks instead of one massive table
    chunk_size = 50
    for i in range(0, len(data), chunk_size):
        chunk = data[i:i + chunk_size]
        table = Table(chunk, colWidths=col_widths)
        table.setStyle(table_style)  # reuse style object
        elements.append(table)
        elements.append(PageBreak())

        if progress_callback:
            progress_callback(int((i / len(data)) * 100))

    doc.build(elements)
```

```python
# 2. Cache the table style -- creating TableStyle is expensive
TABLE_STYLE = TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
    ("FONTSIZE", (0, 0), (-1, -1), 8),
    ("PADDING", (0, 0), (-1, -1), 4),
])
# Reuse this object for every table -- don't recreate it in the loop
```

```python
# 3. Use Platypus flowables efficiently -- avoid Paragraph for simple text
# SLOW: Paragraph(str(value), style)  -- parses HTML/XML
# FAST: str(value)  -- plain string in table cells is fine
table_data = [[str(cell) for cell in row] for row in data]
```

These optimizations typically cut ReportLab time by 40-60%. Combined with async generation and progress reporting, the user experience goes from "broken" to "acceptable."'''
    },
    {
        "instruction": r'''Our PostgreSQL queries are slow and I need to understand why. I know about EXPLAIN but the output is confusing. Can you show me how to actually read an EXPLAIN ANALYZE output and identify the problem?''',
        "output": r'''<think>
Practical EXPLAIN ANALYZE reading. Let me use a realistic example and walk through what each part means and what to look for.
</think>

Let me walk through a real example. Say you have this slow query:

```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT o.id, o.total, u.email, u.name
FROM orders o
JOIN users u ON u.id = o.user_id
WHERE o.created_at > '2024-01-01'
AND o.status = 'completed'
ORDER BY o.created_at DESC
LIMIT 50;
```

Sample output:

```
Limit  (cost=15234.56..15234.70 rows=50 width=89) (actual time=3842.119..3842.135 rows=50 loops=1)
  ->  Sort  (cost=15234.56..15487.23 rows=101068 width=89) (actual time=3842.117..3842.127 rows=50 loops=1)
        Sort Key: o.created_at DESC
        Sort Method: top-N heapsort  Memory: 32kB
        ->  Hash Join  (cost=1234.56..12456.78 rows=101068 width=89) (actual time=45.223..3621.445 rows=98542 loops=1)
              Hash Cond: (o.user_id = u.id)
              ->  Seq Scan on orders o  (cost=0.00..9876.54 rows=101068 width=52) (actual time=0.023..3401.234 rows=98542 loops=1)
                    Filter: ((created_at > '2024-01-01') AND (status = 'completed'))
                    Rows Removed by Filter: 1901458
                    Buffers: shared hit=2345 read=45678
              ->  Hash  (cost=934.56..934.56 rows=50000 width=41) (actual time=44.567..44.567 rows=50000 loops=1)
                    Buckets: 65536
                    ->  Seq Scan on users u  (cost=0.00..934.56 rows=50000 width=41) (actual time=0.012..22.345 rows=50000 loops=1)
```

How to read it -- bottom up, inside out:

1. Look at actual time vs rows. The orders Seq Scan takes 3401ms and scans 2M rows (`Rows Removed by Filter: 1901458`) to find 98k matches. That's your bottleneck.

2. "Seq Scan" on a large table with a filter = missing index. Fix:

```sql
CREATE INDEX idx_orders_status_created ON orders (status, created_at DESC);
```

3. After adding the index, the plan should change to:

```
Index Scan using idx_orders_status_created on orders o
    (actual time=0.034..12.567 rows=98542 loops=1)
```

Key things to look for in any EXPLAIN output:
- **Seq Scan on large tables with filters** -- needs an index
- **actual time** much larger than expected -- that node is the bottleneck
- **Rows Removed by Filter** is high -- scanning too much data
- **Buffers: read=** high number -- reading from disk, not cache
- **estimated rows vs actual rows** differ wildly -- stale statistics, run `ANALYZE tablename`
- **Nested Loop** with high loops count -- might need a Hash Join instead (usually means missing index on join column)

Quick cheat sheet:

```
Seq Scan         = full table scan (bad on large tables)
Index Scan       = using an index (good)
Index Only Scan  = answered entirely from index (best)
Bitmap Scan      = index + heap fetch (good for medium selectivity)
Hash Join        = build hash table, probe it (good for large joins)
Nested Loop      = loop per row (good for small result sets, bad for large)
```'''
    },
]
