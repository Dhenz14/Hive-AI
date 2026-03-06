r"""Thinking-trace pairs: React component code review and refactoring."""

PAIRS = [
    ("thinking/code-review", r'''Review this React code and identify issues:

```jsx
import React, { useState, useEffect } from 'react';

function UserDashboard({ userId }) {
  const [user, setUser] = useState(null);
  const [posts, setPosts] = useState([]);
  const [comments, setComments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('posts');

  useEffect(() => {
    fetch(`/api/users/${userId}`)
      .then(res => res.json())
      .then(data => setUser(data));

    fetch(`/api/users/${userId}/posts`)
      .then(res => res.json())
      .then(data => setPosts(data));

    fetch(`/api/users/${userId}/comments`)
      .then(res => res.json())
      .then(data => {
        setComments(data);
        setLoading(false);
      });
  }, []);

  const handleDelete = (postId) => {
    fetch(`/api/posts/${postId}`, { method: 'DELETE' })
      .then(() => {
        const updated = posts.filter(p => p.id !== postId);
        setPosts(updated);
      });
  };

  if (loading) return <div>Loading...</div>;

  return (
    <div className="dashboard">
      <div className="user-info">
        <h1>{user.name}</h1>
        <p>{user.email}</p>
        <p>Posts: {posts.length} | Comments: {comments.length}</p>
      </div>

      <div className="tabs">
        <button onClick={() => setActiveTab('posts')}>Posts</button>
        <button onClick={() => setActiveTab('comments')}>Comments</button>
      </div>

      {activeTab === 'posts' && (
        <div className="posts">
          {posts.map(post => (
            <div className="post-card">
              <h3>{post.title}</h3>
              <p>{post.body.substring(0, 200)}...</p>
              <span>{new Date(post.createdAt).toLocaleDateString()}</span>
              <button onClick={() => handleDelete(post.id)}>Delete</button>
            </div>
          ))}
        </div>
      )}

      {activeTab === 'comments' && (
        <div className="comments">
          {comments.map(comment => (
            <div className="comment-card">
              <p>{comment.body}</p>
              <span>on {comment.postTitle}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default UserDashboard;
```''', r'''<think>
Let me review this React component carefully.

The useEffect dependency array is empty []. The effect uses userId from props, so I need to think about what happens when userId changes. Could the empty array be intentional if this component is only mounted once? Hmm, but this is a UserDashboard -- navigating between user profiles would change userId without remounting. With [], the effect never re-runs, so the component shows stale data from the first user. Should be [userId].

Looking at error handling -- none of the three fetch calls handle errors. I initially thought the loading state might catch this... but wait, setLoading(false) only fires in the comments callback. If the comments fetch fails, loading stays true forever and the user sees an infinite spinner. If the user fetch fails but comments succeeds, loading becomes false but user is still null, and then `user.name` crashes with "Cannot read properties of null." Actually, the loading logic is flawed in a deeper way: it only tracks whether comments finished, not whether all three requests completed. Posts and user data could still be in-flight when loading becomes false.

There are also race conditions here. Three parallel fetches update state independently. If userId changes rapidly (user navigating between profiles), old requests for the previous userId may resolve after new ones, overwriting fresh data with stale data. I considered whether React 18's automatic batching helps... but no, the core issue is that there is no cancellation mechanism like AbortController to discard in-flight requests when userId changes.

The posts.map and comments.map are missing key props on the outer div. React needs unique keys for efficient DOM reconciliation. Without them, React falls back to index-based comparison which can cause incorrect reuse of component instances.

handleDelete immediately sends a DELETE request with no confirmation dialog. Also, if the DELETE fails, the post is already optimistically removed from local state with no rollback. The component is also doing too much -- data fetching, tab state, rendering lists, and deletion logic all in one function component. This should be decomposed.
</think>

## Code Review: React UserDashboard Component

### CRITICAL - Missing userId Dependency

**DEP1: useEffect ignores userId changes (Severity: CRITICAL)**
```jsx
useEffect(() => {
  fetch(`/api/users/${userId}`)
  // ...
}, []);  // empty dependency array
```
The effect uses `userId` but the dependency array is `[]`. When userId changes (e.g., navigating between user profiles), the effect does not re-run. The component shows stale data from the first render. Fix:
```jsx
}, [userId]);
```

### CRITICAL - Null Crash on Failed Fetch

**NC1: user.name accessed without null check (Severity: CRITICAL)**
```jsx
if (loading) return <div>Loading...</div>;
// ...
<h1>{user.name}</h1>
```
If the user fetch fails, `user` remains `null`. After loading is set to false (by the comments callback), `user.name` throws "Cannot read properties of null". Add a null guard:
```jsx
if (loading || !user) return <div>Loading...</div>;
```

### HIGH - No Error Handling

**EH1: Fetch failures silently ignored (Severity: HIGH)**
None of the three fetch calls handle errors. Network failures, 404s, and 500s produce no user feedback. Add error handling:
```jsx
const [error, setError] = useState(null);

useEffect(() => {
  Promise.all([
    fetch(`/api/users/${userId}`).then(r => r.json()),
    fetch(`/api/users/${userId}/posts`).then(r => r.json()),
    fetch(`/api/users/${userId}/comments`).then(r => r.json()),
  ])
    .then(([userData, postsData, commentsData]) => {
      setUser(userData);
      setPosts(postsData);
      setComments(commentsData);
    })
    .catch(err => setError(err.message))
    .finally(() => setLoading(false));
}, [userId]);
```

### HIGH - Flawed Loading State

**LS1: Loading only tracks comments (Severity: HIGH)**
`setLoading(false)` is called only in the comments callback. If comments load first but user data is still pending, the component renders with `user === null`. All three fetches should complete before showing content. Use `Promise.all` as shown above.

### HIGH - Race Conditions

**RC1: Stale data from previous userId (Severity: HIGH)**
If userId changes while fetches are in-flight, old responses may arrive after new ones, overwriting fresh data with stale data. Use an AbortController:
```jsx
useEffect(() => {
  const controller = new AbortController();
  const signal = controller.signal;

  fetch(`/api/users/${userId}`, { signal })
    .then(r => r.json())
    .then(setUser);
  // ... same for other fetches

  return () => controller.abort();
}, [userId]);
```

### MEDIUM - Missing Key Props

**KP1: List items lack key prop (Severity: MEDIUM)**
```jsx
{posts.map(post => (
  <div className="post-card">  {/* no key */}
```
React requires unique `key` props for list items to efficiently update the DOM. Add `key={post.id}`.

### MEDIUM - No Delete Confirmation

**DC1: Immediate deletion without confirmation (Severity: MEDIUM)**
`handleDelete` sends a DELETE request immediately with no confirmation dialog. Also, if the DELETE fails, the post is already removed from local state (optimistic update without rollback):
```jsx
const handleDelete = async (postId) => {
  if (!window.confirm('Delete this post?')) return;
  try {
    await fetch(`/api/posts/${postId}`, { method: 'DELETE' });
    setPosts(posts.filter(p => p.id !== postId));
  } catch {
    alert('Failed to delete post');
  }
};
```

### LOW - Component Size

**CS1: Single component does too much (Severity: LOW)**
UserDashboard handles data fetching, tab state, post list, comment list, and deletion. Extract `PostList`, `CommentList`, and `UserInfo` components. Consider a custom hook `useUserDashboard(userId)` for the data fetching logic.'''),

    ("thinking/code-review", r'''Review this React code and identify issues:

```jsx
import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';

function DataTable({ data, columns, onRowClick, sortable, filterable }) {
  const [sortColumn, setSortColumn] = useState(null);
  const [sortDirection, setSortDirection] = useState('asc');
  const [filters, setFilters] = useState({});
  const [selectedRows, setSelectedRows] = useState(new Set());
  const tableRef = useRef(null);

  const filteredData = useMemo(() => {
    let result = [...data];
    Object.entries(filters).forEach(([key, value]) => {
      if (value) {
        result = result.filter(row =>
          String(row[key]).toLowerCase().includes(value.toLowerCase())
        );
      }
    });
    return result;
  }, [data, filters]);

  const sortedData = useMemo(() => {
    if (!sortColumn) return filteredData;
    return [...filteredData].sort((a, b) => {
      const aVal = a[sortColumn];
      const bVal = b[sortColumn];
      const modifier = sortDirection === 'asc' ? 1 : -1;
      if (typeof aVal === 'string') {
        return aVal.localeCompare(bVal) * modifier;
      }
      return (aVal - bVal) * modifier;
    });
  }, [filteredData, sortColumn, sortDirection]);

  const handleSort = (column) => {
    if (sortColumn === column) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(column);
      setSortDirection('asc');
    }
  };

  const handleFilter = (column, value) => {
    setFilters({ ...filters, [column]: value });
  };

  const handleSelectAll = () => {
    if (selectedRows.size === sortedData.length) {
      setSelectedRows(new Set());
    } else {
      setSelectedRows(new Set(sortedData.map(row => row.id)));
    }
  };

  const handleSelectRow = (id) => {
    const newSelected = new Set(selectedRows);
    if (newSelected.has(id)) {
      newSelected.delete(id);
    } else {
      newSelected.add(id);
    }
    setSelectedRows(newSelected);
  };

  const Row = ({ row }) => (
    <tr onClick={() => onRowClick?.(row)}
        className={selectedRows.has(row.id) ? 'selected' : ''}>
      <td>
        <input type="checkbox"
               checked={selectedRows.has(row.id)}
               onChange={() => handleSelectRow(row.id)} />
      </td>
      {columns.map(col => (
        <td key={col.key}>{col.render ? col.render(row[col.key], row) : row[col.key]}</td>
      ))}
    </tr>
  );

  return (
    <table ref={tableRef}>
      <thead>
        <tr>
          <th><input type="checkbox" onChange={handleSelectAll} /></th>
          {columns.map(col => (
            <th key={col.key}>
              <div onClick={() => sortable && handleSort(col.key)}>
                {col.title}
                {sortColumn === col.key && (sortDirection === 'asc' ? ' ^' : ' v')}
              </div>
              {filterable && (
                <input
                  placeholder={`Filter ${col.title}`}
                  onChange={e => handleFilter(col.key, e.target.value)}
                />
              )}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {sortedData.map(row => (
          <Row key={row.id} row={row} />
        ))}
      </tbody>
    </table>
  );
}

export default DataTable;
```''', r'''<think>
Let me review this React DataTable component carefully.

The Row component is defined inside DataTable's function body. At first I thought this might just be a style choice... but wait, this is actually a severe performance bug. On every render of DataTable, JavaScript creates a new Row function. React compares component types by reference, so it sees a "new" component type each time. That means ALL rows unmount and remount on every single render -- DOM elements are destroyed and recreated, internal state is lost, and animations reset. For a table with 1000 rows, every keystroke in a filter input triggers 1000 DOM teardowns and rebuilds. The fix is to either inline the JSX in the map or move Row outside DataTable as a memoized component.

The useMemo on filteredData and sortedData is good. But hmm, since Row is recreated each render anyway, the memoization partially goes to waste because React re-renders every row regardless of whether the data changed.

For selection behavior, I initially thought handleSelectAll looked correct... but actually there is a subtle inconsistency. selectedRows persists across filter changes. If you select all 100 rows, then filter to show 10, selectedRows still contains all 100 IDs. The "select all" checkbox checks `selectedRows.size === sortedData.length` (100 !== 10), so it shows unchecked even though all visible rows are selected. This is confusing UX.

The sort comparator checks `typeof aVal === 'string'` to decide between localeCompare and arithmetic. Could this be sufficient? No, because if aVal is null or undefined, `aVal.localeCompare(bVal)` throws a TypeError. Also if aVal is a string but bVal is null, localeCompare still runs against null which produces unpredictable results.

Performance for large datasets is a concern -- no virtualization means 10,000 rows create 10,000 DOM elements. And the filter input has no debouncing, so each keystroke triggers a full re-filter and re-render cycle. For accessibility, the sort headers use onClick on a div with no keyboard handler, no role="button", and no tabIndex. Screen readers will also read "^" and "v" as literal characters rather than sort direction indicators.
</think>

## Code Review: React DataTable Component

### CRITICAL - Row Component Defined Inside Render

**ROW1: Row remounts on every render (Severity: CRITICAL)**
```jsx
const Row = ({ row }) => (
  <tr onClick={() => onRowClick?.(row)}>
```
`Row` is defined as a component inside `DataTable`. On every render of DataTable, React creates a new function reference for `Row`. React compares component types by reference, so it sees a "new" component and unmounts/remounts ALL rows on every parent render. This means:
- Every keystroke in a filter input destroys and recreates all row DOM elements
- Input focus inside rows is lost
- Animations reset
- Terrible performance for large tables

Fix: Either inline the JSX directly in the map, or move Row outside:
```jsx
// Option 1: Inline JSX
<tbody>
  {sortedData.map(row => (
    <tr key={row.id} onClick={() => onRowClick?.(row)}>
      {/* ... */}
    </tr>
  ))}
</tbody>

// Option 2: External memoized component
const Row = React.memo(({ row, columns, selected, onSelect, onClick }) => (
  <tr onClick={() => onClick?.(row)}>
    {/* ... */}
  </tr>
));
```

### HIGH - No Virtualization for Large Datasets

**VIRT1: All rows rendered in DOM (Severity: HIGH)**
For 10,000 rows, 10,000 `<tr>` elements exist in the DOM simultaneously. This causes slow initial render, high memory usage, and janky scrolling. Use react-window or react-virtuoso for virtual scrolling that only renders visible rows.

### HIGH - Filter Input Not Debounced

**DB1: Every keystroke triggers full re-render (Severity: HIGH)**
```jsx
onChange={e => handleFilter(col.key, e.target.value)}
```
Each keystroke updates filters state, recalculates filteredData (via useMemo), recalculates sortedData, and re-renders all rows. For large datasets, this causes noticeable lag while typing. Debounce the filter input:
```jsx
import { useDeferredValue } from 'react';
// or use a debounced handler with setTimeout
```

### MEDIUM - Sort Null Handling

**SN1: Sort crashes on null values (Severity: MEDIUM)**
```jsx
if (typeof aVal === 'string') {
  return aVal.localeCompare(bVal) * modifier;
}
return (aVal - bVal) * modifier;
```
If `aVal` or `bVal` is null or undefined, `localeCompare` throws and arithmetic produces NaN. Add null guards:
```jsx
if (aVal == null) return 1;
if (bVal == null) return -1;
```

### MEDIUM - Selection State Inconsistency

**SS1: Selected rows persist across filter changes (Severity: MEDIUM)**
If a user selects all 100 rows, then filters to show 10, `selectedRows` still contains all 100 IDs. The "select all" checkbox shows unchecked (100 !== 10) even though all visible rows are selected. Consider:
- Clear selection when filters change
- Or check "select all" against visible rows: `sortedData.every(row => selectedRows.has(row.id))`

### MEDIUM - Accessibility

**A11Y1: Sort headers not keyboard accessible (Severity: MEDIUM)**
Sort is triggered by `onClick` on a `<div>` inside `<th>`. There is no `onKeyDown` handler, `role="button"`, or `tabIndex`. Keyboard users cannot sort columns. Use a `<button>` element inside the header.

**A11Y2: Sort indicators not screen-reader friendly (Severity: LOW)**
`' ^'` and `' v'` are visual-only. Use `aria-sort="ascending"` / `"descending"` on the `<th>` element.

### LOW - Missing Pagination

**PG1: No pagination support (Severity: LOW)**
All data is rendered at once. For server-side data sources with millions of rows, client-side rendering is impractical. Add pagination props or integrate with a server-side data fetching strategy.'''),

    ("thinking/code-review", r'''Review this React code and identify issues:

```jsx
import React, { useState, useEffect, useRef } from 'react';

function InfiniteScrollList({ fetchItems, renderItem, pageSize = 20 }) {
  const [items, setItems] = useState([]);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const observerRef = useRef(null);
  const loadingRef = useRef(null);

  useEffect(() => {
    loadMore();
  }, []);

  const loadMore = async () => {
    if (loading || !hasMore) return;
    setLoading(true);
    try {
      const newItems = await fetchItems(page, pageSize);
      setItems(prev => [...prev, ...newItems]);
      setHasMore(newItems.length === pageSize);
      setPage(page + 1);
    } catch (error) {
      console.error('Failed to load items:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    observerRef.current = new IntersectionObserver(
      entries => {
        if (entries[0].isIntersecting) {
          loadMore();
        }
      },
      { threshold: 0.5 }
    );

    if (loadingRef.current) {
      observerRef.current.observe(loadingRef.current);
    }

    return () => {
      if (observerRef.current) {
        observerRef.current.disconnect();
      }
    };
  }, []);

  return (
    <div className="scroll-list">
      {items.map((item, index) => (
        <div key={index} className="list-item">
          {renderItem(item)}
        </div>
      ))}
      {hasMore && (
        <div ref={loadingRef} className="loading-trigger">
          {loading ? 'Loading...' : 'Load more'}
        </div>
      )}
      {!hasMore && items.length > 0 && (
        <div className="end-message">No more items</div>
      )}
    </div>
  );
}

function ItemCard({ item }) {
  const [expanded, setExpanded] = useState(false);
  const [liked, setLiked] = useState(false);

  useEffect(() => {
    // Track impression
    fetch('/api/analytics/impression', {
      method: 'POST',
      body: JSON.stringify({ itemId: item.id }),
    });
  }, []);

  const handleLike = () => {
    setLiked(!liked);
    fetch('/api/items/' + item.id + '/like', {
      method: liked ? 'DELETE' : 'POST',
    });
  };

  return (
    <div className="item-card">
      <h3>{item.title}</h3>
      <p>{expanded ? item.description : item.description?.substring(0, 100)}</p>
      {item.description?.length > 100 && (
        <button onClick={() => setExpanded(!expanded)}>
          {expanded ? 'Less' : 'More'}
        </button>
      )}
      <button onClick={handleLike}>
        {liked ? 'Unlike' : 'Like'} ({item.likes + (liked ? 1 : 0)})
      </button>
    </div>
  );
}

export { InfiniteScrollList, ItemCard };
```''', r'''<think>
Let me review this React infinite scroll implementation.

The loadMore function is defined in the component body and captures `page`, `loading`, `hasMore` from the closure. The IntersectionObserver is created in a useEffect with an empty dependency array [], so it only runs once on mount. That means the observer callback captures the initial loadMore from the first render. When the observer triggers later, it calls a stale loadMore that still sees page=1, loading=false, hasMore=true from the initial render.

Wait, let me trace through this more carefully. First render: page=1, loadMore is created. Observer captures this loadMore. User scrolls, observer fires, calls loadMore(page=1). loadMore runs, fetches page 1 (again, since useEffect already did this), then calls setPage(page + 1) -- but page is 1 from the stale closure, so it always sets page to 2. Actually no, the first useEffect also calls loadMore on mount, which sets page to 2. But the observer's loadMore still has page=1. Every subsequent observer trigger tries to load page 1 again. This is the classic stale closure problem. The fix is to use a ref to hold the current loadMore or use functional state updaters.

I considered whether setPage(page + 1) might work with batched updates... but no, the page value in the closure is permanently frozen at the value from when loadMore was created. Also, if loadingRef.current is null when the observer effect runs (because hasMore conditional rendering has not committed yet), the observer observes nothing and infinite scroll never triggers.

For ItemCard, the useEffect with empty [] tracks impressions on mount. I initially thought this was fine... but hmm, if the component remounts due to key={index} recycling in the parent, impressions get double-counted. Also item.id is missing from the dependency array -- if the same ItemCard instance receives a different item prop, the new impression is never tracked.

handleLike has a subtle optimistic update bug. It reads `liked` from the closure to decide between POST and DELETE. If the user clicks rapidly, both clicks might read liked=false and both send POST requests. The like count display `item.likes + (liked ? 1 : 0)` is a client-side hack that drifts from the server value and has no rollback if the fetch fails. All loaded items also stay in the DOM permanently, causing unbounded memory growth after scrolling through many pages.
</think>

## Code Review: React Infinite Scroll Component

### CRITICAL - Stale Closure in IntersectionObserver

**SC1: loadMore always loads page 1 (Severity: CRITICAL)**
The IntersectionObserver is created once with `useEffect([], [])`. Its callback captures `loadMore` from the first render. That `loadMore` has `page=1`, `loading=false`, `hasMore=true` baked into its closure. Every time the observer fires, it calls this stale function, always requesting page 1.

Fix: Use a ref to hold the current loadMore function:
```jsx
const loadMoreRef = useRef(loadMore);
loadMoreRef.current = loadMore;

useEffect(() => {
  const observer = new IntersectionObserver(entries => {
    if (entries[0].isIntersecting) {
      loadMoreRef.current();
    }
  }, { threshold: 0.5 });
  // ...
}, []);
```

Or use `page` as state updated via the functional updater pattern:
```jsx
setPage(prev => prev + 1);
```
Combined with recreating the observer when dependencies change.

### HIGH - Page Counter Stale State

**PS1: setPage uses stale page value (Severity: HIGH)**
```jsx
setPage(page + 1);
```
Inside loadMore, `page` is captured from the render closure. With the stale observer callback, this always sets page to 2 (1+1). Use the functional updater:
```jsx
setPage(prev => {
  const nextPage = prev + 1;
  // Note: cannot use nextPage for fetch here
  return nextPage;
});
```
Better yet, derive the page from items length: `Math.floor(items.length / pageSize) + 1`.

### HIGH - Observer May Miss Load Trigger

**OB1: loadingRef may be null on first effect (Severity: HIGH)**
The IntersectionObserver effect runs after mount with `[]`. If `hasMore` initially renders the loading trigger, it should be available. However, if the initial `items` are empty and the first `loadMore` has not completed, there is a timing issue. Use a callback ref instead:
```jsx
const loadingRef = useCallback(node => {
  if (observerRef.current) observerRef.current.disconnect();
  if (node) {
    observerRef.current = new IntersectionObserver(...);
    observerRef.current.observe(node);
  }
}, [hasMore, loading]);
```

### HIGH - ItemCard Like Race Condition

**LK1: Rapid clicks send wrong API requests (Severity: HIGH)**
```jsx
const handleLike = () => {
  setLiked(!liked);
  fetch('/api/items/' + item.id + '/like', {
    method: liked ? 'DELETE' : 'POST',
  });
```
`liked` in the fetch call uses the pre-setState value (correct for the immediate call). But rapid double-clicks can cause: click1 reads liked=false, sends POST, sets liked=true. Click2 reads liked=true (if state updated), sends DELETE, sets liked=false. But if state has not updated between clicks, both reads see liked=false and both send POST. Use a ref or debounce:
```jsx
const likedRef = useRef(liked);
likedRef.current = liked;
```

### MEDIUM - Index Keys

**IK1: key={index} is fragile (Severity: MEDIUM)**
Using array index as key works for append-only lists but breaks if the list is modified (items removed, reordered). If the parent also re-renders causing list diffing, React may incorrectly reuse ItemCard instances. Use `item.id` as the key.

### MEDIUM - Missing Impression Dependency

**IM1: Impression not tracked when item changes (Severity: MEDIUM)**
```jsx
useEffect(() => {
  fetch('/api/analytics/impression', {
    method: 'POST',
    body: JSON.stringify({ itemId: item.id }),
  });
}, []);
```
If the same ItemCard is reused with a different `item` (due to key recycling), the impression for the new item is never tracked. Add `item.id` to dependencies.

### LOW - Memory Growth

**MG1: All loaded items stay in DOM (Severity: LOW)**
After loading 50 pages (1000 items), all DOM elements remain rendered. This causes increasing memory usage and slower scrolling. Consider virtualizing with react-window or windowing old items off-screen.'''),

    ("thinking/code-review", r'''Review this React code and identify issues:

```jsx
import React, { useState, useEffect, useRef, memo } from 'react';

const ExpensiveChart = memo(({ data, width, height, options }) => {
  const canvasRef = useRef(null);

  useEffect(() => {
    const ctx = canvasRef.current.getContext('2d');
    ctx.clearRect(0, 0, width, height);
    // Complex chart rendering logic
    data.forEach((point, i) => {
      const x = (i / data.length) * width;
      const y = height - (point.value / Math.max(...data.map(d => d.value))) * height;
      ctx.lineTo(x, y);
    });
    ctx.stroke();
  }, [data, width, height, options]);

  return <canvas ref={canvasRef} width={width} height={height} />;
});

function Dashboard() {
  const [chartData, setChartData] = useState([]);
  const [timeRange, setTimeRange] = useState('24h');
  const [refreshInterval, setRefreshInterval] = useState(5000);

  useEffect(() => {
    const fetchData = async () => {
      const response = await fetch(`/api/metrics?range=${timeRange}`);
      const data = await response.json();
      setChartData(data);
    };

    fetchData();
    const interval = setInterval(fetchData, refreshInterval);

    return () => clearInterval(interval);
  }, [timeRange, refreshInterval]);

  return (
    <div className="dashboard">
      <div className="controls">
        <select value={timeRange} onChange={e => setTimeRange(e.target.value)}>
          <option value="1h">1 Hour</option>
          <option value="24h">24 Hours</option>
          <option value="7d">7 Days</option>
        </select>
        <select value={refreshInterval} onChange={e => setRefreshInterval(e.target.value)}>
          <option value={1000}>1s</option>
          <option value={5000}>5s</option>
          <option value={30000}>30s</option>
        </select>
      </div>

      <ExpensiveChart
        data={chartData}
        width={800}
        height={400}
        options={{ showGrid: true, showLabels: true }}
      />

      <div className="stats">
        {chartData.length > 0 && (
          <>
            <div>Latest: {chartData[chartData.length - 1]?.value}</div>
            <div>Average: {(chartData.reduce((sum, d) => sum + d.value, 0) / chartData.length).toFixed(2)}</div>
            <div>Max: {Math.max(...chartData.map(d => d.value))}</div>
            <div>Min: {Math.min(...chartData.map(d => d.value))}</div>
          </>
        )}
      </div>
    </div>
  );
}

export default Dashboard;
```''', r'''<think>
Let me review this React dashboard with charting.

ExpensiveChart is wrapped in React.memo, which should prevent unnecessary re-renders. But looking at how Dashboard uses it -- `options={{ showGrid: true, showLabels: true }}` -- that is an inline object literal. Memo does shallow comparison, so a new object reference is created on every render of Dashboard. Wait, that means the memo is completely defeated. Every time Dashboard re-renders (from data fetch, time range change, anything), ExpensiveChart re-renders because options is always a "new" object. The memo wrapper is entirely useless here.

Inside the chart rendering useEffect, I see `Math.max(...data.map(d => d.value))` called inside the forEach loop. I initially thought this might be a small dataset where it does not matter... but actually this computes the max on every single iteration. For 1000 data points, that is 1000 * 1000 = 1,000,000 operations. This is O(n^2) when it should be O(n). Compute the max once before the loop.

Also, the canvas code calls ctx.lineTo() without ever calling ctx.beginPath() or ctx.moveTo(). Hmm, without beginPath(), the path accumulates from the previous render's state. And without moveTo() for the first point, lineTo starts from (0,0), drawing an unwanted line from the origin to the first data point.

The refreshInterval select is interesting. useState initializes it as a number (5000), but e.target.value is always a string. After the user changes the dropdown, refreshInterval becomes "5000" (string). I considered whether setInterval would handle this... and it does convert strings, but the select value matching might break since the option values are numbers but the state becomes a string after the first change.

The stats section computes reduce, Math.max, Math.min on every render even when chartData has not changed. These should be memoized. Actually, Math.max(...chartData.map(...)) is also dangerous for large arrays -- the spread operator passes all values as function arguments, and arrays over ~100,000 elements will overflow the call stack.
</think>

## Code Review: React Dashboard with Chart

### CRITICAL - memo Defeated by Inline Object

**MO1: options prop creates new reference every render (Severity: CRITICAL)**
```jsx
<ExpensiveChart
  options={{ showGrid: true, showLabels: true }}
/>
```
`memo` does shallow comparison. The inline object `{ showGrid: true, showLabels: true }` creates a new reference on every render, so `memo` always sees a "changed" prop and re-renders ExpensiveChart. The `memo` wrapper is completely ineffective.

Fix: Memoize the options object:
```jsx
const chartOptions = useMemo(() => ({
  showGrid: true, showLabels: true,
}), []);

<ExpensiveChart options={chartOptions} />
```

### HIGH - O(n^2) Chart Rendering

**ON2: Math.max computed inside loop (Severity: HIGH)**
```jsx
data.forEach((point, i) => {
  const y = height - (point.value / Math.max(...data.map(d => d.value))) * height;
});
```
`Math.max(...data.map(d => d.value))` runs inside forEach, computing the max for every data point. For 1000 points, this is 1,000,000 operations. Compute once:
```jsx
const maxValue = Math.max(...data.map(d => d.value));
data.forEach((point, i) => {
  const y = height - (point.value / maxValue) * height;
});
```

### HIGH - Canvas Path Not Initialized

**CP1: Missing beginPath and moveTo (Severity: HIGH)**
The chart drawing code calls `ctx.lineTo()` without `ctx.beginPath()` or `ctx.moveTo()` for the first point. This means:
- The path continues from the previous render's state
- The first line segment starts from (0,0) instead of the first data point

Fix:
```jsx
ctx.beginPath();
data.forEach((point, i) => {
  const x = ...;
  const y = ...;
  if (i === 0) ctx.moveTo(x, y);
  else ctx.lineTo(x, y);
});
ctx.stroke();
```

### MEDIUM - Type Mismatch on refreshInterval

**TM1: String vs number after select change (Severity: MEDIUM)**
```jsx
const [refreshInterval, setRefreshInterval] = useState(5000);
// ...
onChange={e => setRefreshInterval(e.target.value)}
```
`e.target.value` is always a string. After the user changes the dropdown, `refreshInterval` becomes `"5000"` (string). While `setInterval` converts it, strict equality comparisons and the select's value matching may behave unexpectedly. Parse the value:
```jsx
onChange={e => setRefreshInterval(Number(e.target.value))}
```

### MEDIUM - Stats Not Memoized

**SM1: Expensive calculations on every render (Severity: MEDIUM)**
```jsx
<div>Average: {(chartData.reduce((sum, d) => sum + d.value, 0) / chartData.length).toFixed(2)}</div>
<div>Max: {Math.max(...chartData.map(d => d.value))}</div>
```
These calculations run on every render (including when controls are interacted with). Memoize them:
```jsx
const stats = useMemo(() => {
  if (chartData.length === 0) return null;
  const values = chartData.map(d => d.value);
  return {
    latest: values[values.length - 1],
    average: (values.reduce((a, b) => a + b, 0) / values.length).toFixed(2),
    max: Math.max(...values),
    min: Math.min(...values),
  };
}, [chartData]);
```

**SM2: Math.max with spread can overflow stack (Severity: MEDIUM)**
`Math.max(...chartData.map(...))` passes all values as arguments. For arrays larger than ~100,000 elements, this exceeds the call stack size. Use a loop-based max calculation.

### LOW - No Error Feedback

**EF1: Fetch errors silently ignored (Severity: LOW)**
If the API returns an error, there is no user feedback. The interval keeps fetching, which is reasonable, but a transient error indicator would improve UX.'''),

    ("thinking/code-review", r'''Review this React code and identify issues:

```jsx
import React, { useState, useEffect, createContext, useContext } from 'react';

const ThemeContext = createContext();
const UserContext = createContext();
const CartContext = createContext();

function App() {
  const [theme, setTheme] = useState('light');
  const [user, setUser] = useState(null);
  const [cart, setCart] = useState([]);
  const [notifications, setNotifications] = useState([]);

  useEffect(() => {
    fetch('/api/me').then(r => r.json()).then(setUser);
    fetch('/api/cart').then(r => r.json()).then(setCart);
    fetch('/api/notifications').then(r => r.json()).then(setNotifications);
  }, []);

  const addToCart = (item) => {
    setCart([...cart, item]);
    fetch('/api/cart', {
      method: 'POST',
      body: JSON.stringify(item),
    });
  };

  const removeFromCart = (itemId) => {
    setCart(cart.filter(i => i.id !== itemId));
    fetch(`/api/cart/${itemId}`, { method: 'DELETE' });
  };

  const toggleTheme = () => {
    setTheme(theme === 'light' ? 'dark' : 'light');
  };

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      <UserContext.Provider value={{ user, setUser }}>
        <CartContext.Provider value={{ cart, addToCart, removeFromCart }}>
          <Header notifications={notifications} />
          <main>
            <ProductList />
            <CartSidebar />
          </main>
          <Footer />
        </CartContext.Provider>
      </UserContext.Provider>
    </ThemeContext.Provider>
  );
}

function Header({ notifications }) {
  const { theme, toggleTheme } = useContext(ThemeContext);
  const { user } = useContext(UserContext);
  const { cart } = useContext(CartContext);

  return (
    <header className={`header-${theme}`}>
      <h1>Store</h1>
      <nav>
        <span>Welcome, {user?.name}</span>
        <span>Cart ({cart.length})</span>
        <span>Notifications ({notifications.length})</span>
        <button onClick={toggleTheme}>Toggle Theme</button>
      </nav>
    </header>
  );
}

function ProductList() {
  const [products, setProducts] = useState([]);
  const { addToCart } = useContext(CartContext);

  useEffect(() => {
    fetch('/api/products').then(r => r.json()).then(setProducts);
  }, []);

  return (
    <div className="products">
      {products.map(product => (
        <ProductCard key={product.id} product={product} onAdd={addToCart} />
      ))}
    </div>
  );
}

function ProductCard({ product, onAdd }) {
  return (
    <div className="product-card">
      <img src={product.image} alt={product.name} />
      <h3>{product.name}</h3>
      <p>${product.price}</p>
      <button onClick={() => onAdd(product)}>Add to Cart</button>
    </div>
  );
}

function CartSidebar() {
  const { cart, removeFromCart } = useContext(CartContext);
  const total = cart.reduce((sum, item) => sum + item.price, 0);

  return (
    <aside className="cart-sidebar">
      <h2>Cart</h2>
      {cart.map(item => (
        <div key={item.id} className="cart-item">
          <span>{item.name}</span>
          <span>${item.price}</span>
          <button onClick={() => removeFromCart(item.id)}>Remove</button>
        </div>
      ))}
      <div className="total">Total: ${total.toFixed(2)}</div>
    </aside>
  );
}

function Footer() {
  const { theme } = useContext(ThemeContext);
  return <footer className={`footer-${theme}`}>Footer Content</footer>;
}

export default App;
```''', r'''<think>
Let me review this React application with context providers.

The three context providers in App each receive a value prop with an inline object -- `{ theme, toggleTheme }`, `{ user, setUser }`, `{ cart, addToCart, removeFromCart }`. Could React be smart enough to skip re-renders if the contents have not changed? No, because context uses reference equality. Every render of App creates new object references for all three provider values, which forces ALL consumers to re-render.

Wait, this means any state change in App triggers re-renders across the entire tree. For example, adding an item to cart changes cart state, which re-renders App, which creates a new ThemeContext value object, which re-renders Footer even though theme did not change at all. This is a cascade re-render problem. The fix is useMemo on each context value.

Looking at addToCart -- it does `setCart([...cart, item])` using the cart from the render closure. I initially thought this was standard React pattern... but actually, if the user clicks "Add to Cart" twice quickly, both calls see the same cart array from the same render. The second call overwrites the first addition because cart has not updated between clicks. Should use the functional updater: `setCart(prev => [...prev, item])`.

There is also no error handling on the optimistic updates. addToCart and removeFromCart update state immediately then fire a fetch. If the fetch fails (network error, server error), the UI shows the wrong cart state with no rollback mechanism.

Hmm, the cart duplicate handling is also problematic. Adding the same product twice creates two separate entries with the same item.id. Since the cart map uses item.id as key, React will warn about duplicate keys and may incorrectly reuse DOM elements. Typically you want quantity tracking, not duplicates.

The fetch POST calls use JSON.stringify on the body but do not set Content-Type: application/json. Many servers will not parse the body without that header and will treat it as text/plain.

Notifications are passed as a prop to Header while cart and user come via context -- inconsistent data flow pattern. And there are no loading states or error boundaries anywhere in the app.
</think>

## Code Review: React App with Context Providers

### HIGH - Context Values Cause Cascade Re-renders

**CR1: New context value objects on every render (Severity: HIGH)**
```jsx
<ThemeContext.Provider value={{ theme, toggleTheme }}>
  <CartContext.Provider value={{ cart, addToCart, removeFromCart }}>
```
Every render of App creates new object references for each context value. Any state change in App (theme, cart, user, or notifications) triggers re-renders of ALL context consumers, even unrelated ones. Adding an item to cart re-renders Footer (which only uses theme).

Fix: Memoize context values:
```jsx
const themeValue = useMemo(() => ({ theme, toggleTheme }), [theme]);
const cartValue = useMemo(() => ({ cart, addToCart, removeFromCart }), [cart]);

<ThemeContext.Provider value={themeValue}>
```
Also wrap addToCart and removeFromCart in useCallback to stabilize references.

### HIGH - Stale Closure in addToCart

**SC1: Cart state lost on rapid adds (Severity: HIGH)**
```jsx
const addToCart = (item) => {
  setCart([...cart, item]);
```
`cart` is captured from the render closure. If a user clicks "Add to Cart" twice quickly, both calls see the same `cart` array. The second call overwrites the first addition. Use the functional updater:
```jsx
const addToCart = useCallback((item) => {
  setCart(prev => [...prev, item]);
  fetch('/api/cart', { method: 'POST', body: JSON.stringify(item) });
}, []);
```

### HIGH - No Error Handling on Optimistic Updates

**OPT1: Failed API leaves UI in wrong state (Severity: HIGH)**
`addToCart` and `removeFromCart` update state immediately then fire fetch. If the API call fails, the cart UI shows incorrect data. Either:
- Add error handling that reverts the optimistic update
- Or make the API call first and update state on success

### MEDIUM - Duplicate Cart Items

**DUP1: Same product added multiple times (Severity: MEDIUM)**
Clicking "Add to Cart" twice adds two entries with the same product. Cart items use `item.id` as key, so duplicate keys cause React warnings and incorrect DOM updates. Either:
- Track quantities: find existing item and increment
- Or prevent duplicates: check if item already in cart

### MEDIUM - Missing Content-Type Header

**CT1: POST without Content-Type (Severity: MEDIUM)**
```jsx
fetch('/api/cart', {
  method: 'POST',
  body: JSON.stringify(item),
});
```
No `Content-Type: application/json` header. Many servers require this to parse JSON bodies:
```jsx
fetch('/api/cart', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(item),
});
```

### MEDIUM - Inconsistent Data Patterns

**IC1: Props vs context inconsistency (Severity: MEDIUM)**
Notifications are passed as a prop to Header while cart and user come from context. This makes the data flow hard to follow. Either move notifications into context or pass cart/user as props too.

### LOW - Performance

**P1: CartSidebar total not memoized (Severity: LOW)**
```jsx
const total = cart.reduce((sum, item) => sum + item.price, 0);
```
Recalculated on every render. Use useMemo:
```jsx
const total = useMemo(
  () => cart.reduce((sum, item) => sum + item.price, 0),
  [cart]
);
```

### LOW - No Loading/Error States

**LE1: No loading indicators or error boundaries (Severity: LOW)**
All fetch calls have no loading states. The user sees an empty page until data loads. Add loading states for initial data fetch and error boundaries for component failures.'''),
]
