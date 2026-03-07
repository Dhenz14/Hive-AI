"""
Frontend thinking pairs - React performance optimization decisions
"""

pairs = [
    {
        "instruction": r'''Should I wrap every callback in useCallback? My coworker says it is a best practice to always use useCallback for any function passed as a prop.''',
        "output": r'''<think>
"Always useCallback" is one of those cargo-cult React patterns. Let me think about when it actually helps vs when it is useless overhead.

useCallback memoizes a function reference so it is stable across renders. It helps in exactly one scenario: when the function is passed as a prop to a component that is wrapped in React.memo. Without React.memo on the child, the child re-renders anyway (because its parent re-rendered), so a stable function reference is pointless.

Wait, there is a second scenario: when the function is a dependency of useEffect or useMemo. A new function reference on every render would cause the effect to re-run. But even then, if the effect just calls the function and does not do expensive work, re-running is cheap.

So the cases where useCallback matters:
1. Function passed to React.memo child (prevents unnecessary re-render)
2. Function in useEffect dependency array (prevents unnecessary effect execution)
3. Function passed to a large list of items (new reference means all items re-render)

Cases where useCallback is WASTED:
- Function passed to native DOM elements (button onClick) -- DOM elements do not check for referential equality
- Function passed to non-memoized children -- they re-render anyway
- Simple components where re-renders are cheap

Hmm, actually there is a cost to useCallback itself. React has to compare the dependency array on every render. For simple functions with no dependencies, this comparison is overhead that buys you nothing unless the child is memoized.

I initially thought "it does not hurt to use it everywhere" but it actually does: it adds cognitive overhead (developers have to track dependencies), it clutters the code, and the comparison cost adds up in hot paths. Kent C. Dodds wrote about this -- premature optimization makes code harder to maintain for negligible benefit.

The right approach: do not use useCallback by default. Add it when you have a MEASURED performance problem, specifically when a memoized child is re-rendering unnecessarily because of unstable function references.
</think>

No, wrapping every callback in useCallback is not a best practice -- it is premature optimization that adds complexity without benefit in most cases.

```tsx
// CASE 1: useCallback is USELESS here
// onClick on native elements does not check referential equality
function SearchBar() {
  const [query, setQuery] = useState('');

  // This function is recreated every render -- AND THAT IS FINE
  // The <button> does not care about function identity
  const handleSearch = () => {
    console.log('Searching:', query);
  };

  return (
    <div>
      <input value={query} onChange={e => setQuery(e.target.value)} />
      <button onClick={handleSearch}>Search</button>
    </div>
  );
}

// CASE 2: useCallback is USELESS without React.memo on child
function Parent() {
  const [count, setCount] = useState(0);

  // useCallback keeps the reference stable...
  const handleClick = useCallback(() => {
    console.log('clicked');
  }, []);

  // ...but ChildComponent re-renders anyway because Parent re-rendered
  // useCallback did NOTHING here
  return (
    <div>
      <button onClick={() => setCount(c => c + 1)}>+</button>
      <ChildComponent onClick={handleClick} />
    </div>
  );
}

// Not memoized -- re-renders every time parent renders regardless
function ChildComponent({ onClick }: { onClick: () => void }) {
  return <button onClick={onClick}>Click me</button>;
}

// CASE 3: useCallback MATTERS -- child is memoized
function ParentWithMemoChild() {
  const [count, setCount] = useState(0);

  // Stable reference prevents ExpensiveChild from re-rendering
  const handleClick = useCallback(() => {
    console.log('clicked');
  }, []);

  return (
    <div>
      <button onClick={() => setCount(c => c + 1)}>
        Count: {count}
      </button>
      {/* THIS child checks props with shallow compare */}
      <ExpensiveChild onClick={handleClick} />
    </div>
  );
}

// React.memo means: only re-render if props changed
// NOW useCallback on the parent's handler actually prevents re-renders
const ExpensiveChild = memo(function ExpensiveChild({
  onClick,
}: {
  onClick: () => void;
}) {
  // Expensive rendering logic here
  return <button onClick={onClick}>Expensive operation</button>;
});

// CASE 4: useCallback MATTERS -- large list items
function ItemList({ items }: { items: Item[] }) {
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // Without useCallback: new function on every render
  // means ALL 1000 MemoizedItem components re-render
  const toggleItem = useCallback((id: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }, []);

  return (
    <div>
      {items.map(item => (
        <MemoizedItem
          key={item.id}
          item={item}
          isSelected={selected.has(item.id)}
          onToggle={toggleItem}
        />
      ))}
    </div>
  );
}

const MemoizedItem = memo(function MemoizedItem({
  item,
  isSelected,
  onToggle,
}: {
  item: Item;
  isSelected: boolean;
  onToggle: (id: string) => void;
}) {
  return (
    <div
      className={isSelected ? 'item selected' : 'item'}
      onClick={() => onToggle(item.id)}
    >
      {item.name}
    </div>
  );
});
```

The rule: **useCallback only helps when paired with React.memo or as a useEffect dependency.** Without one of those, it is wasted complexity.'''
    },
    {
        "instruction": r'''My React app has a page that imports 50 components and takes 4 seconds to load. How do I implement code splitting?''',
        "output": r'''<think>
4 seconds to load because of 50 components -- the user is loading everything upfront in one big bundle. Code splitting is the answer, but I need to think about WHERE to split.

The common approach is route-based code splitting: each page is a separate chunk loaded on demand. This is the biggest win because users only download the code for the page they are visiting.

React.lazy + Suspense is the built-in way to do this. But wait, there are gotchas:
1. React.lazy only works with default exports
2. Suspense needs a fallback UI (loading spinner)
3. Error boundaries are needed for network failures
4. SSR does not support React.lazy (need loadable-components or Next.js dynamic)

For 50 components on one page, route-based splitting alone might not be enough. Some of those components might be conditionally rendered (modals, tabs, advanced features). Those should be split too.

Hmm, I should also mention: before code splitting, check if the bundle is actually large or if the 4-second load is due to something else (slow API calls, large images, render blocking). Use the browser DevTools Network tab or webpack-bundle-analyzer to confirm the JS bundle size is the problem.

I initially thought I should show webpack configuration, but actually with modern tooling (Next.js, Vite, CRA), code splitting is mostly about using React.lazy correctly. The bundler handles the chunk creation automatically.

The tradeoff with code splitting: more network requests (one per chunk), waterfall loading if chunks depend on each other, and flash of loading state. Prefetching helps with the UX impact.
</think>

Code splitting breaks your 50-component monolith into smaller chunks loaded on demand. The two main strategies are route-based and component-based splitting.

```tsx
// STEP 1: Route-based splitting (biggest win)
// Each page becomes its own JS chunk
import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';

// lazy() tells the bundler to create a separate chunk
// These are NOT downloaded until the route is visited
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Products = lazy(() => import('./pages/Products'));
const Analytics = lazy(() => import('./pages/Analytics'));
const Settings = lazy(() => import('./pages/Settings'));
const UserManagement = lazy(() => import('./pages/UserManagement'));

function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<PageSkeleton />}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/products" element={<Products />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/users" element={<UserManagement />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}

// STEP 2: Component-based splitting for heavy conditional content
// Modals, tabs, and features that not every user sees
function ProductPage() {
  const [showChart, setShowChart] = useState(false);
  const [showExport, setShowExport] = useState(false);

  // Heavy charting library -- only load when user clicks "Show Chart"
  const PriceChart = lazy(
    () => import('./components/PriceChart')
  );

  // Heavy export modal with xlsx library
  const ExportModal = lazy(
    () => import('./components/ExportModal')
  );

  return (
    <div>
      <h1>Product Details</h1>
      <button onClick={() => setShowChart(true)}>
        Show Price History
      </button>
      <button onClick={() => setShowExport(true)}>
        Export Data
      </button>

      <Suspense fallback={<div>Loading chart...</div>}>
        {showChart && <PriceChart productId="abc" />}
      </Suspense>

      <Suspense fallback={<div>Loading export...</div>}>
        {showExport && (
          <ExportModal
            onClose={() => setShowExport(false)}
          />
        )}
      </Suspense>
    </div>
  );
}

// STEP 3: Prefetch chunks on hover for instant navigation
function NavLink({ to, children }: { to: string; children: string }) {
  const prefetch = () => {
    // Trigger the dynamic import on hover so the chunk
    // is already cached when the user clicks
    switch (to) {
      case '/analytics':
        import('./pages/Analytics');
        break;
      case '/settings':
        import('./pages/Settings');
        break;
    }
  };

  return (
    <a
      href={to}
      onMouseEnter={prefetch}
      onFocus={prefetch}
    >
      {children}
    </a>
  );
}

// STEP 4: Error boundary for failed chunk loads (network errors)
import { Component, ReactNode } from 'react';

interface ErrorBoundaryState {
  hasError: boolean;
}

class ChunkErrorBoundary extends Component<
  { children: ReactNode },
  ErrorBoundaryState
> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div>
          <p>Failed to load this section.</p>
          <button onClick={() => window.location.reload()}>
            Reload page
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
```

Before splitting, verify JS bundle size is the actual problem:
- Run `npx vite-bundle-visualizer` (Vite) or `npx webpack-bundle-analyzer` to see what is in your bundle
- Check Chrome DevTools -> Network tab to confirm large JS download
- A 4-second load might also be slow API calls or unoptimized images, not bundle size'''
    },
    {
        "instruction": r'''I have a table with 10,000 rows and it is extremely laggy when scrolling. What is the best way to handle this in React?''',
        "output": r'''<think>
10,000 rows in a table -- this is a classic virtualization problem. Rendering 10,000 DOM nodes is expensive regardless of React. The browser has to maintain layout, paint, and composite for every single row even if most are off-screen.

The solution is virtualization (also called windowing): only render the rows that are visible in the viewport, plus a small overscan buffer above and below. As the user scrolls, rows enter and exit the rendered set.

Libraries for this:
- @tanstack/react-virtual (modern, lightweight, headless)
- react-window (popular, slightly older)
- react-virtuoso (feature-rich, handles variable heights well)

Hmm, for a TABLE specifically, there are extra considerations:
1. Sticky header -- the column headers should stay visible during scroll
2. Column alignment -- virtualized rows must align with the header columns
3. Variable row heights -- some rows might be taller than others
4. Selection state -- selecting a row should not cause all 10,000 to re-render

Wait, should I recommend a full table library instead? Like TanStack Table (formerly React Table)? It handles sorting, filtering, pagination, AND virtualization. But the user asked specifically about scroll performance, so let me focus on virtualization.

I initially thought react-window would be the recommendation, but @tanstack/react-virtual is newer, smaller, and gives more control. It is also from the same team that builds TanStack Table, so they work well together.

The tradeoff with virtualization: absolute positioning means accessibility can be tricky (screen readers might not understand the table structure), and dynamic row heights require measurement passes. If the user can paginate instead (show 50 rows per page), that is much simpler and more accessible.

Actually, I should ask: does the user NEED 10,000 visible rows? Often the answer is no -- pagination or infinite scroll with a smaller window is better UX. But I will show both approaches.
</think>

Render 10,000 DOM nodes and the browser will struggle regardless of framework. The fix is virtualization -- only render the ~30 rows visible in the viewport.

```tsx
import { useVirtualizer } from '@tanstack/react-virtual';
import { useRef, useMemo } from 'react';

interface Row {
  id: string;
  name: string;
  email: string;
  role: string;
  status: 'active' | 'inactive';
}

interface VirtualTableProps {
  data: Row[];
}

function VirtualTable({ data }: VirtualTableProps) {
  const parentRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: data.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 48, // row height in px
    overscan: 10, // render 10 extra rows above/below viewport
  });

  return (
    <div>
      {/* Fixed header -- always visible */}
      <div className="table-header">
        <div className="th" style={{ width: 200 }}>Name</div>
        <div className="th" style={{ width: 250 }}>Email</div>
        <div className="th" style={{ width: 120 }}>Role</div>
        <div className="th" style={{ width: 100 }}>Status</div>
      </div>

      {/* Scrollable body with virtualization */}
      <div
        ref={parentRef}
        className="table-body"
        style={{ height: 600, overflow: 'auto' }}
      >
        <div
          style={{
            height: virtualizer.getTotalSize(),
            position: 'relative',
          }}
        >
          {virtualizer.getVirtualItems().map(virtualRow => {
            const row = data[virtualRow.index];
            return (
              <div
                key={row.id}
                className="table-row"
                style={{
                  position: 'absolute',
                  top: 0,
                  transform: "translateY(" + virtualRow.start + "px)",
                  height: 48,
                  width: '100%',
                  display: 'flex',
                }}
              >
                <div style={{ width: 200 }}>{row.name}</div>
                <div style={{ width: 250 }}>{row.email}</div>
                <div style={{ width: 120 }}>{row.role}</div>
                <div style={{ width: 100 }}>
                  <span className={"badge " + row.status}>
                    {row.status}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="table-footer">
        Showing {data.length.toLocaleString()} rows
      </div>
    </div>
  );
}
```

```css
.table-header {
  display: flex;
  background: #f8fafc;
  border-bottom: 2px solid #e2e8f0;
  position: sticky;
  top: 0;
  z-index: 1;
}

.th {
  padding: 12px 16px;
  font-weight: 600;
  color: #475569;
  font-size: 0.875rem;
}

.table-body {
  border: 1px solid #e2e8f0;
}

.table-row {
  border-bottom: 1px solid #f1f5f9;
  align-items: center;
}

.table-row > div {
  padding: 0 16px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.badge {
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 0.75rem;
}

.badge.active { background: #dcfce7; color: #166534; }
.badge.inactive { background: #fee2e2; color: #991b1b; }
```

Performance comparison:
- **Without virtualization**: 10,000 DOM nodes, ~400ms render, laggy scroll
- **With virtualization**: ~50 DOM nodes, ~5ms render, smooth 60fps scroll

Consider simpler alternatives:
- **Pagination** (50 rows per page) -- simpler code, better accessibility, and usually better UX than scrolling through 10,000 rows
- **Infinite scroll** -- load 50 rows at a time as user scrolls, with a maximum DOM limit of ~200 rows (remove old ones from the top)
- **Server-side filtering** -- if users are searching, fetch only matching rows from the server instead of loading all 10,000'''
    },
    {
        "instruction": r'''I am using useMemo to memoize a simple string concatenation. Is that worth it or am I overusing it?''',
        "output": r'''<think>
String concatenation memoized with useMemo -- let me think about whether this makes sense.

useMemo has a cost: on every render, React must compare the dependency array values (shallow equality check on each dep) and store the memoized value. For this to be worth it, the computation being memoized must be MORE expensive than the comparison.

String concatenation is... extremely cheap. Like, nanoseconds. Comparing the dependency array values to decide whether to reuse the cached string probably costs MORE than just concatenating the string again.

Wait, let me think about when useMemo IS worth it:
1. Expensive computations: filtering/sorting large arrays, complex math, parsing
2. Referential stability: creating objects/arrays passed to memoized children (they need the same reference to skip re-render)
3. Expensive derived state: computing aggregates from large datasets

For a string concatenation like:
const fullName = useMemo(() => firstName + ' ' + lastName, [firstName, lastName]);

vs just:
const fullName = firstName + ' ' + lastName;

The non-memoized version is simpler, equally fast (or faster!), and easier to read. The memoized version adds complexity for negative performance benefit.

Hmm, I initially thought there might be edge cases where string memoization matters (like a very long string built from many pieces), but even building a 1000-character string from 50 parts is sub-microsecond. useMemo's overhead is in the microsecond range for dependency comparison. So it is literally slower to memoize than to just recompute.

The principle: useMemo is for expensive computations (milliseconds, not microseconds) or referential stability (preventing child re-renders). String concatenation is neither.
</think>

You are overusing it. Memoizing a string concatenation costs MORE than just doing the concatenation. useMemo has overhead from comparing dependencies on every render.

```tsx
// BAD: useMemo for trivial computation
// The dependency comparison is MORE expensive than the concatenation
function UserBadge({ firstName, lastName, role }: UserProps) {
  const fullName = useMemo(
    () => firstName + ' ' + lastName,
    [firstName, lastName]
  );
  const initials = useMemo(
    () => firstName[0] + lastName[0],
    [firstName, lastName]
  );
  const displayRole = useMemo(
    () => role.charAt(0).toUpperCase() + role.slice(1),
    [role]
  );

  return (
    <div>
      <span>{fullName}</span>
      <span>{initials}</span>
      <span>{displayRole}</span>
    </div>
  );
}

// GOOD: Just compute it. It is nanoseconds.
function UserBadge({ firstName, lastName, role }: UserProps) {
  const fullName = firstName + ' ' + lastName;
  const initials = firstName[0] + lastName[0];
  const displayRole = role.charAt(0).toUpperCase() + role.slice(1);

  return (
    <div>
      <span>{fullName}</span>
      <span>{initials}</span>
      <span>{displayRole}</span>
    </div>
  );
}

// WHEN useMemo IS worth it:

// 1. Expensive computation (milliseconds, not microseconds)
function Analytics({ transactions }: { transactions: Transaction[] }) {
  // Sorting 10,000 items is ~5ms. Worth memoizing.
  const sorted = useMemo(
    () => [...transactions].sort((a, b) => b.amount - a.amount),
    [transactions]
  );

  // Aggregating 10,000 items is measurable. Worth memoizing.
  const totals = useMemo(() => {
    return transactions.reduce(
      (acc, t) => ({
        revenue: acc.revenue + (t.type === 'sale' ? t.amount : 0),
        expenses: acc.expenses + (t.type === 'expense' ? t.amount : 0),
        count: acc.count + 1,
      }),
      { revenue: 0, expenses: 0, count: 0 }
    );
  }, [transactions]);

  return <div>{/* render sorted + totals */}</div>;
}

// 2. Referential stability for memoized children
function Parent() {
  const [filter, setFilter] = useState('');
  const [items] = useState(generateItems(1000));

  // Without useMemo: new array reference every render
  // causes MemoizedList to re-render even if results are the same
  const filtered = useMemo(
    () => items.filter(i => i.name.includes(filter)),
    [items, filter]
  );

  return <MemoizedList items={filtered} />;
}

const MemoizedList = memo(function MemoizedList({
  items,
}: {
  items: Item[];
}) {
  return (
    <ul>
      {items.map(i => (
        <li key={i.id}>{i.name}</li>
      ))}
    </ul>
  );
});
```

Decision rule for useMemo:
- **Computation takes < 1ms** (string ops, simple math, one-liner transforms) --> do not memoize
- **Computation takes > 1ms** (sorting/filtering large arrays, complex aggregations) --> memoize
- **Result is an object/array passed to a React.memo child** --> memoize for referential stability
- **Not sure?** Profile with React DevTools before adding useMemo. The default should be no memoization.'''
    },
    {
        "instruction": r'''My React app re-renders the entire page when I update a single item in a list. The list has 200 items. How do I isolate re-renders?''',
        "output": r'''<think>
This is a common React performance issue. When one item in a list changes (e.g., toggling a checkbox, updating a counter), the parent component that owns the list state re-renders, which causes all 200 list items to re-render even though only one changed.

Let me think about the re-render flow:
1. User clicks "like" on item #42
2. This calls setState on the parent (which owns the items array)
3. Parent re-renders with new items array
4. Parent renders 200 ItemComponent elements
5. ALL 200 ItemComponents re-render because parent re-rendered

The fix involves two things working together:
1. React.memo on the item component (so it skips re-render if props did not change)
2. Stable prop references (so React.memo's shallow comparison actually works)

But wait, there is a subtle issue. If the items array is updated immutably (which it should be), every item object in the new array might be a new reference even if only one changed. Like:
items.map(item => item.id === targetId ? { ...item, liked: true } : item)

This creates new references only for the changed item. The unchanged items keep their references. So React.memo WILL work here -- 199 items have the same reference and skip re-render.

Hmm, but what about the callback prop? If the parent passes onClick={() => handleLike(item.id)}, that creates a new function on every render for every item. React.memo sees a new function reference and re-renders anyway. This is where useCallback matters -- but you cannot call useCallback in a loop.

The solution: pass the handler with a stable reference and let the child call it with its own id. Instead of onClick={() => handleLike(item.id)}, pass onLike={handleLike} and have the child do onClick={() => onLike(item.id).

I initially thought this was purely a React.memo problem, but it is really about the COMBINATION of memo + stable references for both data and callbacks.
</think>

The problem is the parent re-renders all 200 children when it updates one item. The fix is React.memo on the child plus stable prop references.

```tsx
import { useState, useCallback, memo } from 'react';

interface Item {
  id: string;
  title: string;
  liked: boolean;
  likeCount: number;
}

// Parent component
function ItemList() {
  const [items, setItems] = useState<Item[]>(generateItems(200));

  // useCallback with functional update -- reference never changes
  // because there are NO dependencies (setItems is stable)
  const toggleLike = useCallback((id: string) => {
    setItems(prev =>
      prev.map(item =>
        item.id === id
          ? { ...item, liked: !item.liked, likeCount: item.likeCount + (item.liked ? -1 : 1) }
          : item // unchanged items keep same reference
      )
    );
  }, []);

  const deleteItem = useCallback((id: string) => {
    setItems(prev => prev.filter(item => item.id !== id));
  }, []);

  return (
    <ul className="item-list">
      {items.map(item => (
        <MemoizedItem
          key={item.id}
          item={item}
          onToggleLike={toggleLike}
          onDelete={deleteItem}
        />
      ))}
    </ul>
  );
}

// Memoized child -- only re-renders when ITS props change
const MemoizedItem = memo(function ItemRow({
  item,
  onToggleLike,
  onDelete,
}: {
  item: Item;
  onToggleLike: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  // You can verify this works by adding:
  // console.log('Rendering item:', item.id);
  // Only the clicked item should log

  return (
    <li className="item-row">
      <span>{item.title}</span>
      <button
        onClick={() => onToggleLike(item.id)}
        className={item.liked ? 'liked' : ''}
      >
        {item.liked ? 'Unlike' : 'Like'} ({item.likeCount})
      </button>
      <button onClick={() => onDelete(item.id)}>Delete</button>
    </li>
  );
});
```

Why this works -- step by step:

```
User clicks "Like" on item #42
  |
  v
toggleLike("42") called
  |
  v
setItems(prev => prev.map(...))
  - Item #42 gets a NEW object: { ...item, liked: true }
  - Items #1-41, #43-200 keep their SAME object references
  |
  v
Parent re-renders, maps over 200 items
  |
  v
React.memo on MemoizedItem compares props:
  - Item #42: new item reference --> RE-RENDERS (correct)
  - Item #1: same item reference, same onToggleLike, same onDelete
    --> SKIPS re-render (199 items skip)
```

Critical details that make this work:
1. **React.memo** on the child component enables the shallow prop comparison
2. **useCallback with empty deps** on handlers -- stable references across renders
3. **Functional state update** (`setItems(prev => ...)`) so the callback does not need `items` in its dependency array
4. **Immutable update** in map -- unchanged items keep the same object reference, which is what memo checks

Without ALL three pieces working together, the optimization fails. Memo without stable callbacks re-renders everything. Stable callbacks without memo have no effect. Immutable updates without memo are also wasted.'''
    },
]
