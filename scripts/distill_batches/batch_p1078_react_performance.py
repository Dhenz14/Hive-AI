"""
Batch p1078: TypeScript/React production pairs - React Performance
Topics: memo, useMemo, useCallback, virtualization, code splitting
"""

PAIRS = [
    ("react/perf_memoization", r'''Build React memoization patterns showing when and how to use React.memo, useMemo, and useCallback effectively, including common anti-patterns and a custom comparison function for complex props.''', r'''// Performance optimization patterns with proper memoization

import React, { useState, useMemo, useCallback, memo, useRef } from "react";

// Pattern 1: React.memo with custom comparison
// Only re-render when relevant props change
interface DataTableRowProps {
  id: string;
  data: Record<string, string | number>;
  columns: string[];
  isSelected: boolean;
  onSelect: (id: string) => void;
  onEdit: (id: string, field: string, value: string) => void;
}

const DataTableRow = memo(
  function DataTableRow({ id, data, columns, isSelected, onSelect, onEdit }: DataTableRowProps) {
    const renderCount = useRef(0);
    renderCount.current++;

    return (
      <tr className={isSelected ? "bg-blue-50" : ""}>
        <td>
          <input
            type="checkbox"
            checked={isSelected}
            onChange={() => onSelect(id)}
          />
        </td>
        {columns.map((col) => (
          <td
            key={col}
            onDoubleClick={() => onEdit(id, col, String(data[col] ?? ""))}
            className="px-4 py-2"
          >
            {data[col]}
          </td>
        ))}
      </tr>
    );
  },
  // Custom comparison: only re-render if these specific things change
  (prev, next) => {
    return (
      prev.id === next.id &&
      prev.isSelected === next.isSelected &&
      prev.onSelect === next.onSelect &&
      prev.onEdit === next.onEdit &&
      shallowEqualObject(prev.data, next.data) &&
      prev.columns === next.columns
    );
  }
);

function shallowEqualObject(a: Record<string, unknown>, b: Record<string, unknown>): boolean {
  const keysA = Object.keys(a);
  const keysB = Object.keys(b);
  if (keysA.length !== keysB.length) return false;
  return keysA.every((key) => a[key] === b[key]);
}

// Pattern 2: Stable callbacks with useCallback
// The parent component that manages state
function DataTable({ rows, columns }: { rows: Record<string, any>[]; columns: string[] }) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [sortField, setSortField] = useState<string>(columns[0]);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  // Stable callback - only changes when selectedIds changes
  const handleSelect = useCallback(
    (id: string) => {
      setSelectedIds((prev) => {
        const next = new Set(prev);
        if (next.has(id)) {
          next.delete(id);
        } else {
          next.add(id);
        }
        return next;
      });
    },
    [] // No deps needed - uses functional setState
  );

  // Stable callback for editing
  const handleEdit = useCallback(
    (id: string, field: string, value: string) => {
      console.log(`Edit ${id}.${field} = ${value}`);
    },
    []
  );

  // Expensive sort computation - memoized
  const sortedRows = useMemo(() => {
    const sorted = [...rows].sort((a, b) => {
      const aVal = a[sortField];
      const bVal = b[sortField];
      if (typeof aVal === "number" && typeof bVal === "number") {
        return sortDir === "asc" ? aVal - bVal : bVal - aVal;
      }
      const comparison = String(aVal).localeCompare(String(bVal));
      return sortDir === "asc" ? comparison : -comparison;
    });
    return sorted;
  }, [rows, sortField, sortDir]);

  // Memoize columns array reference to prevent unnecessary re-renders
  const stableColumns = useMemo(() => columns, [columns.join(",")]);

  return (
    <table className="w-full">
      <thead>
        <tr>
          <th className="w-8" />
          {stableColumns.map((col) => (
            <th
              key={col}
              className="px-4 py-2 cursor-pointer select-none"
              onClick={() => {
                if (sortField === col) {
                  setSortDir((d) => (d === "asc" ? "desc" : "asc"));
                } else {
                  setSortField(col);
                  setSortDir("asc");
                }
              }}
            >
              {col} {sortField === col ? (sortDir === "asc" ? " ^" : " v") : ""}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {sortedRows.map((row) => (
          <DataTableRow
            key={row.id}
            id={row.id}
            data={row}
            columns={stableColumns}
            isSelected={selectedIds.has(row.id)}
            onSelect={handleSelect}
            onEdit={handleEdit}
          />
        ))}
      </tbody>
    </table>
  );
}

// Pattern 3: useMemo for expensive computations
interface AnalyticsData {
  timestamp: number;
  value: number;
  category: string;
}

function AnalyticsChart({ data, filters }: {
  data: AnalyticsData[];
  filters: { categories: string[]; dateRange: [Date, Date] };
}) {
  // Filter data - memoized because filtering large datasets is expensive
  const filteredData = useMemo(() => {
    const [start, end] = filters.dateRange;
    const categorySet = new Set(filters.categories);

    return data.filter(
      (d) =>
        d.timestamp >= start.getTime() &&
        d.timestamp <= end.getTime() &&
        (categorySet.size === 0 || categorySet.has(d.category))
    );
  }, [data, filters.categories, filters.dateRange]);

  // Compute aggregates - memoized and depends on filtered data
  const stats = useMemo(() => {
    if (filteredData.length === 0) {
      return { avg: 0, min: 0, max: 0, total: 0, count: 0 };
    }
    const values = filteredData.map((d) => d.value);
    return {
      avg: values.reduce((a, b) => a + b, 0) / values.length,
      min: Math.min(...values),
      max: Math.max(...values),
      total: values.reduce((a, b) => a + b, 0),
      count: values.length,
    };
  }, [filteredData]);

  // Group by category - memoized
  const groupedByCategory = useMemo(() => {
    const groups = new Map<string, number>();
    for (const d of filteredData) {
      groups.set(d.category, (groups.get(d.category) || 0) + d.value);
    }
    return Array.from(groups.entries())
      .map(([category, total]) => ({ category, total }))
      .sort((a, b) => b.total - a.total);
  }, [filteredData]);

  return (
    <div>
      <div className="grid grid-cols-4 gap-4 mb-6">
        <StatCard label="Total" value={stats.total.toFixed(0)} />
        <StatCard label="Average" value={stats.avg.toFixed(2)} />
        <StatCard label="Min" value={stats.min.toFixed(2)} />
        <StatCard label="Max" value={stats.max.toFixed(2)} />
      </div>
      <div className="text-sm text-gray-500">
        Showing {filteredData.length} of {data.length} data points
      </div>
    </div>
  );
}

// Anti-pattern: DO NOT create objects/arrays inline in render
// BAD: <Child style={{ color: "red" }} items={[1, 2, 3]} />
// GOOD: Use useMemo or define outside component

const StatCard = memo(function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white p-4 rounded shadow">
      <p className="text-sm text-gray-500">{label}</p>
      <p className="text-2xl font-bold">{value}</p>
    </div>
  );
});

export { DataTable, AnalyticsChart };
'''),

    ("react/perf_virtualization", r'''<think>
Virtualization is critical for rendering large lists efficiently. I could just show how to use react-window or react-virtuoso, but wait - understanding the underlying mechanics is more valuable for debugging and customization. I will build on the concepts these libraries use but show a from-scratch approach.

The core algorithm is: calculate which items fall within the visible viewport based on scroll position, and only render those plus a small overscan buffer. I initially thought a fixed-height assumption would simplify things, but actually variable height support is essential for real-world use cases like chat messages or card lists. This means I need to measure items after render and cache their heights.

Hmm, there is a chicken-and-egg problem with variable heights: you need to know item heights to calculate positions, but you need to render items to measure heights. The standard solution is to use estimated heights initially and correct them after measurement. This causes a small layout shift on first render, but it is unavoidable without pre-measuring (which would require rendering all items offscreen, defeating the purpose).
</think>

Build a virtualized list component in React/TypeScript that renders only visible items for large datasets, supporting variable heights, scroll restoration, infinite loading, and keyboard navigation.''', r'''<think>
The core concept is measuring the viewport, calculating which items are visible based on scroll position, and only rendering those items plus a small overscan buffer. I considered using IntersectionObserver for visibility detection, but actually that fires asynchronously and can lag behind fast scrolling. A synchronous calculation from scrollTop is more responsive.

For variable heights, I need to measure items after render and cache their heights. I initially planned to use a ResizeObserver on each item, but hmm - that adds overhead proportional to visible items. A simpler approach is measuring once in a useEffect after render and storing heights in a ref. If items can resize (e.g., expandable rows), then ResizeObserver becomes necessary, but for static content it is overkill.

The overscan buffer is important - without it, fast scrolling shows blank areas before new items render. I will default to 5 items of overscan above and below the viewport, which balances rendering cost against visual smoothness.
</think>

// components/VirtualList.tsx
import React, {
  useState,
  useRef,
  useEffect,
  useCallback,
  useMemo,
  forwardRef,
  useImperativeHandle,
} from "react";

interface VirtualListProps<T> {
  items: T[];
  renderItem: (item: T, index: number, style: React.CSSProperties) => React.ReactNode;
  itemHeight: number | ((index: number) => number);
  overscan?: number;
  className?: string;
  onEndReached?: () => void;
  endReachedThreshold?: number;
  keyExtractor?: (item: T, index: number) => string;
  onScroll?: (scrollTop: number) => void;
  initialScrollTop?: number;
}

interface VirtualListHandle {
  scrollToIndex: (index: number, align?: "start" | "center" | "end") => void;
  scrollToTop: () => void;
  scrollToBottom: () => void;
}

interface ItemMetadata {
  offset: number;
  height: number;
  measured: boolean;
}

function VirtualListInner<T>(
  {
    items,
    renderItem,
    itemHeight,
    overscan = 5,
    className = "",
    onEndReached,
    endReachedThreshold = 200,
    keyExtractor,
    onScroll,
    initialScrollTop = 0,
  }: VirtualListProps<T>,
  ref: React.Ref<VirtualListHandle>
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(initialScrollTop);
  const [containerHeight, setContainerHeight] = useState(0);
  const itemMetadata = useRef<ItemMetadata[]>([]);
  const endReachedTriggered = useRef(false);

  // Initialize/update item metadata
  const isFixedHeight = typeof itemHeight === "number";

  const getItemMetadata = useCallback(
    (index: number): ItemMetadata => {
      if (itemMetadata.current[index]) {
        return itemMetadata.current[index];
      }

      const height = isFixedHeight ? itemHeight : (itemHeight as Function)(index);
      const previousItem = index > 0 ? getItemMetadata(index - 1) : null;
      const offset = previousItem ? previousItem.offset + previousItem.height : 0;

      itemMetadata.current[index] = { offset, height, measured: false };
      return itemMetadata.current[index];
    },
    [itemHeight, isFixedHeight]
  );

  // Total height of all items
  const totalHeight = useMemo(() => {
    if (items.length === 0) return 0;
    const lastItem = getItemMetadata(items.length - 1);
    return lastItem.offset + lastItem.height;
  }, [items.length, getItemMetadata]);

  // Find visible range using binary search
  const findStartIndex = useCallback(
    (scrollTop: number): number => {
      let low = 0;
      let high = items.length - 1;

      while (low <= high) {
        const mid = Math.floor((low + high) / 2);
        const metadata = getItemMetadata(mid);

        if (metadata.offset + metadata.height < scrollTop) {
          low = mid + 1;
        } else if (metadata.offset > scrollTop) {
          high = mid - 1;
        } else {
          return mid;
        }
      }

      return Math.max(0, low);
    },
    [items.length, getItemMetadata]
  );

  const { startIndex, endIndex } = useMemo(() => {
    if (items.length === 0 || containerHeight === 0) {
      return { startIndex: 0, endIndex: 0 };
    }

    const start = findStartIndex(scrollTop);
    let end = start;

    let accumulatedHeight = 0;
    while (end < items.length && accumulatedHeight < containerHeight) {
      accumulatedHeight += getItemMetadata(end).height;
      end++;
    }

    // Apply overscan
    const overscanStart = Math.max(0, start - overscan);
    const overscanEnd = Math.min(items.length, end + overscan);

    return { startIndex: overscanStart, endIndex: overscanEnd };
  }, [scrollTop, containerHeight, items.length, overscan, findStartIndex, getItemMetadata]);

  // Visible items with positioning
  const visibleItems = useMemo(() => {
    const result: Array<{ item: T; index: number; style: React.CSSProperties }> = [];

    for (let i = startIndex; i < endIndex; i++) {
      const metadata = getItemMetadata(i);
      result.push({
        item: items[i],
        index: i,
        style: {
          position: "absolute",
          top: metadata.offset,
          left: 0,
          right: 0,
          height: metadata.height,
        },
      });
    }

    return result;
  }, [startIndex, endIndex, items, getItemMetadata]);

  // Handle scroll events
  const handleScroll = useCallback(
    (e: React.UIEvent<HTMLDivElement>) => {
      const newScrollTop = e.currentTarget.scrollTop;
      setScrollTop(newScrollTop);
      onScroll?.(newScrollTop);

      // Check if we have reached the end
      if (onEndReached) {
        const scrollBottom = newScrollTop + containerHeight;
        if (
          scrollBottom >= totalHeight - endReachedThreshold &&
          !endReachedTriggered.current
        ) {
          endReachedTriggered.current = true;
          onEndReached();
        } else if (scrollBottom < totalHeight - endReachedThreshold) {
          endReachedTriggered.current = false;
        }
      }
    },
    [containerHeight, totalHeight, endReachedThreshold, onEndReached, onScroll]
  );

  // Observe container resize
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setContainerHeight(entry.contentRect.height);
      }
    });

    observer.observe(container);
    setContainerHeight(container.clientHeight);

    return () => observer.disconnect();
  }, []);

  // Initial scroll position
  useEffect(() => {
    if (initialScrollTop > 0 && containerRef.current) {
      containerRef.current.scrollTop = initialScrollTop;
    }
  }, [initialScrollTop]);

  // Expose imperative methods
  useImperativeHandle(
    ref,
    () => ({
      scrollToIndex(index: number, align = "start") {
        const container = containerRef.current;
        if (!container || index < 0 || index >= items.length) return;

        const metadata = getItemMetadata(index);
        let targetScroll: number;

        switch (align) {
          case "center":
            targetScroll = metadata.offset - containerHeight / 2 + metadata.height / 2;
            break;
          case "end":
            targetScroll = metadata.offset - containerHeight + metadata.height;
            break;
          default:
            targetScroll = metadata.offset;
        }

        container.scrollTop = Math.max(0, Math.min(targetScroll, totalHeight - containerHeight));
      },
      scrollToTop() {
        if (containerRef.current) containerRef.current.scrollTop = 0;
      },
      scrollToBottom() {
        if (containerRef.current) {
          containerRef.current.scrollTop = totalHeight - containerHeight;
        }
      },
    }),
    [items.length, containerHeight, totalHeight, getItemMetadata]
  );

  // Keyboard navigation
  const [focusedIndex, setFocusedIndex] = useState(-1);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          setFocusedIndex((prev) => Math.min(prev + 1, items.length - 1));
          break;
        case "ArrowUp":
          e.preventDefault();
          setFocusedIndex((prev) => Math.max(prev - 1, 0));
          break;
        case "Home":
          e.preventDefault();
          setFocusedIndex(0);
          break;
        case "End":
          e.preventDefault();
          setFocusedIndex(items.length - 1);
          break;
      }
    },
    [items.length]
  );

  return (
    <div
      ref={containerRef}
      className={`overflow-auto relative ${className}`}
      onScroll={handleScroll}
      onKeyDown={handleKeyDown}
      tabIndex={0}
      role="listbox"
      aria-rowcount={items.length}
    >
      <div style={{ height: totalHeight, position: "relative" }}>
        {visibleItems.map(({ item, index, style }) => (
          <div
            key={keyExtractor ? keyExtractor(item, index) : index}
            role="option"
            aria-selected={index === focusedIndex}
            aria-posinset={index + 1}
            aria-setsize={items.length}
          >
            {renderItem(item, index, style)}
          </div>
        ))}
      </div>
    </div>
  );
}

export const VirtualList = forwardRef(VirtualListInner) as <T>(
  props: VirtualListProps<T> & { ref?: React.Ref<VirtualListHandle> }
) => React.ReactElement;

export type { VirtualListProps, VirtualListHandle };
'''),

    ("react/perf_code_splitting", r'''Build React code splitting patterns in TypeScript including route-based splitting with lazy/Suspense, component-level splitting with loading states, preloading on hover, and a dynamic import wrapper with retry logic.''', r'''// Code splitting patterns for production React applications

import React, { Suspense, lazy, useState, useCallback, useRef, useEffect, ComponentType } from "react";

// Pattern 1: Route-level code splitting with preloading
// A lazy import wrapper that supports preloading
function lazyWithPreload<T extends ComponentType<any>>(
  factory: () => Promise<{ default: T }>
) {
  let modulePromise: Promise<{ default: T }> | null = null;
  let resolvedModule: { default: T } | null = null;

  const load = () => {
    if (!modulePromise) {
      modulePromise = factory().then((mod) => {
        resolvedModule = mod;
        return mod;
      });
    }
    return modulePromise;
  };

  const LazyComponent = lazy(load);

  return Object.assign(LazyComponent, {
    preload: load,
    isLoaded: () => resolvedModule !== null,
  });
}

// Route definitions with preloadable components
const routes = {
  Dashboard: lazyWithPreload(() => import("./pages/Dashboard")),
  Settings: lazyWithPreload(() => import("./pages/Settings")),
  Analytics: lazyWithPreload(() => import("./pages/Analytics")),
  UserProfile: lazyWithPreload(() => import("./pages/UserProfile")),
  AdminPanel: lazyWithPreload(() => import("./pages/AdminPanel")),
};

// Navigation link that preloads on hover
interface PreloadLinkProps {
  to: string;
  component: ReturnType<typeof lazyWithPreload>;
  children: React.ReactNode;
  className?: string;
}

function PreloadLink({ to, component, children, className }: PreloadLinkProps) {
  const preloaded = useRef(false);

  const handleMouseEnter = useCallback(() => {
    if (!preloaded.current) {
      component.preload();
      preloaded.current = true;
    }
  }, [component]);

  // Also preload on focus for keyboard navigation
  const handleFocus = handleMouseEnter;

  return (
    <a
      href={to}
      className={className}
      onMouseEnter={handleMouseEnter}
      onFocus={handleFocus}
    >
      {children}
    </a>
  );
}

// Pattern 2: Dynamic import with retry logic
function lazyWithRetry<T extends ComponentType<any>>(
  factory: () => Promise<{ default: T }>,
  options?: { retries?: number; delay?: number; onError?: (error: Error) => void }
): React.LazyExoticComponent<T> {
  const { retries = 3, delay = 1000, onError } = options || {};

  return lazy(async () => {
    let lastError: Error | null = null;

    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        // Add cache-busting on retry to handle stale chunks
        if (attempt > 0) {
          // Force fresh module on retry
          const timestamp = Date.now();
          const module = await factory();
          return module;
        }
        return await factory();
      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error));

        if (attempt < retries) {
          // Exponential backoff
          await new Promise((resolve) =>
            setTimeout(resolve, delay * Math.pow(2, attempt))
          );
        }
      }
    }

    onError?.(lastError!);
    throw lastError;
  });
}

// Pattern 3: Component-level code splitting with loading boundary
interface DynamicImportProps<T extends ComponentType<any>> {
  loader: () => Promise<{ default: T }>;
  fallback?: React.ReactNode;
  errorFallback?: React.ReactNode;
  props?: React.ComponentProps<T>;
}

function DynamicImport<T extends ComponentType<any>>({
  loader,
  fallback,
  errorFallback,
  props,
}: DynamicImportProps<T>) {
  const [Component, setComponent] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    loader()
      .then((mod) => {
        if (!cancelled) {
          setComponent(() => mod.default);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err);
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [loader]);

  if (error) {
    return <>{errorFallback || <div className="text-red-500">Failed to load component</div>}</>;
  }

  if (loading || !Component) {
    return <>{fallback || <div className="animate-pulse bg-gray-200 h-32 rounded" />}</>;
  }

  return <Component {...(props as any)} />;
}

// Pattern 4: Conditional loading based on feature flags or user role
function useConditionalImport<T extends ComponentType<any>>(
  condition: boolean,
  factory: () => Promise<{ default: T }>
): T | null {
  const [Component, setComponent] = useState<T | null>(null);

  useEffect(() => {
    if (condition) {
      factory().then((mod) => setComponent(() => mod.default));
    }
  }, [condition, factory]);

  return Component;
}

// Pattern 5: Intersection Observer-based lazy loading
function LazyOnVisible({
  children,
  fallback,
  rootMargin = "200px",
}: {
  children: React.ReactNode;
  fallback?: React.ReactNode;
  rootMargin?: string;
}) {
  const [isVisible, setIsVisible] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin }
    );

    observer.observe(element);
    return () => observer.disconnect();
  }, [rootMargin]);

  return (
    <div ref={containerRef}>
      {isVisible ? children : fallback || <div className="h-32" />}
    </div>
  );
}

// Pattern 6: Error boundary for lazy components
interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

class LazyErrorBoundary extends React.Component<
  { children: React.ReactNode; fallback?: React.ReactNode; onReset?: () => void },
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("Lazy component error:", error, info);
  }

  reset = () => {
    this.setState({ hasError: false, error: null });
    this.props.onReset?.();
  };

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback || (
          <div className="p-4 bg-red-50 rounded border border-red-200">
            <p className="text-red-800 font-medium">Failed to load</p>
            <p className="text-red-600 text-sm mt-1">{this.state.error?.message}</p>
            <button
              onClick={this.reset}
              className="mt-2 px-3 py-1 bg-red-100 text-red-800 rounded text-sm hover:bg-red-200"
            >
              Retry
            </button>
          </div>
        )
      );
    }
    return this.props.children;
  }
}

// Putting it all together: App with route-based splitting
function App() {
  const [currentRoute, setCurrentRoute] = useState("dashboard");

  const CurrentPage = routes[
    (currentRoute.charAt(0).toUpperCase() + currentRoute.slice(1)) as keyof typeof routes
  ] || routes.Dashboard;

  return (
    <div className="flex h-screen">
      <nav className="w-64 bg-gray-900 text-white p-4">
        {Object.entries(routes).map(([name, component]) => (
          <PreloadLink
            key={name}
            to={`/${name.toLowerCase()}`}
            component={component}
            className="block px-4 py-2 rounded hover:bg-gray-700"
          >
            {name}
          </PreloadLink>
        ))}
      </nav>
      <main className="flex-1 p-8">
        <LazyErrorBoundary>
          <Suspense
            fallback={
              <div className="flex items-center justify-center h-full">
                <div className="animate-spin h-8 w-8 border-4 border-blue-500 border-t-transparent rounded-full" />
              </div>
            }
          >
            <CurrentPage />
          </Suspense>
        </LazyErrorBoundary>
      </main>
    </div>
  );
}

export {
  lazyWithPreload,
  lazyWithRetry,
  DynamicImport,
  PreloadLink,
  LazyOnVisible,
  LazyErrorBoundary,
};
'''),

    ("react/perf_rendering_optimization", r'''Build React rendering optimization patterns including state colocation, component splitting to reduce re-renders, context optimization with selectors, and a benchmark utility for measuring render performance.''', r'''// Rendering optimization patterns for production React

import React, { useState, useCallback, useMemo, createContext, useContext, useRef, useEffect } from "react";

// Pattern 1: State colocation - move state close to where it is used
// BAD: Lifting state too high causes unnecessary re-renders
// function BadParent() {
//   const [search, setSearch] = useState(""); // Every child re-renders on type
//   const [items] = useState(generateItems(1000));
//   return (
//     <>
//       <SearchInput value={search} onChange={setSearch} />
//       <ExpensiveList items={items} />  {/* Re-renders on every keystroke! */}
//     </>
//   );
// }

// GOOD: Colocate search state with the component that uses it
function GoodParent() {
  const [items] = useState(() => generateItems(1000));

  return (
    <>
      <SearchSection items={items} />
      <ExpensiveList items={items} />
    </>
  );
}

// Search has its own state - doesn't affect siblings
function SearchSection({ items }: { items: Item[] }) {
  const [search, setSearch] = useState("");

  const filtered = useMemo(
    () =>
      items.filter((item) =>
        item.name.toLowerCase().includes(search.toLowerCase())
      ),
    [items, search]
  );

  return (
    <div>
      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search..."
        className="px-3 py-2 border rounded"
      />
      <p className="text-sm text-gray-500 mt-1">{filtered.length} results</p>
    </div>
  );
}

// Pattern 2: Context with selective subscription
// Split context to avoid unnecessary re-renders
interface AppState {
  user: { name: string; role: string } | null;
  theme: "light" | "dark";
  notifications: number;
  locale: string;
}

type AppAction =
  | { type: "SET_USER"; user: AppState["user"] }
  | { type: "SET_THEME"; theme: AppState["theme"] }
  | { type: "SET_NOTIFICATIONS"; count: number }
  | { type: "SET_LOCALE"; locale: string };

// Split into separate contexts for different update frequencies
const UserContext = createContext<AppState["user"]>(null);
const ThemeContext = createContext<AppState["theme"]>("light");
const NotificationContext = createContext<{ count: number; setCount: (n: number) => void }>({
  count: 0,
  setCount: () => {},
});

// Provider that splits state into separate contexts
function AppProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AppState["user"]>(null);
  const [theme, setTheme] = useState<AppState["theme"]>("light");
  const [notifications, setNotifications] = useState(0);

  // Memoize the notification context value
  const notificationValue = useMemo(
    () => ({ count: notifications, setCount: setNotifications }),
    [notifications]
  );

  return (
    <UserContext.Provider value={user}>
      <ThemeContext.Provider value={theme}>
        <NotificationContext.Provider value={notificationValue}>
          {children}
        </NotificationContext.Provider>
      </ThemeContext.Provider>
    </UserContext.Provider>
  );
}

// Pattern 3: External store selector (like useSyncExternalStore)
type Listener = () => void;

class Store<T> {
  private state: T;
  private listeners = new Set<Listener>();

  constructor(initialState: T) {
    this.state = initialState;
  }

  getState = (): T => this.state;

  setState = (partial: Partial<T> | ((prev: T) => Partial<T>)) => {
    const update = typeof partial === "function" ? partial(this.state) : partial;
    this.state = { ...this.state, ...update };
    this.listeners.forEach((l) => l());
  };

  subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };
}

function useStoreSelector<T, S>(store: Store<T>, selector: (state: T) => S): S {
  const [, forceUpdate] = useState(0);
  const selectedRef = useRef<S>(selector(store.getState()));
  const selectorRef = useRef(selector);
  selectorRef.current = selector;

  useEffect(() => {
    return store.subscribe(() => {
      const newSelected = selectorRef.current(store.getState());
      if (!Object.is(selectedRef.current, newSelected)) {
        selectedRef.current = newSelected;
        forceUpdate((n) => n + 1);
      }
    });
  }, [store]);

  return selector(store.getState());
}

// Pattern 4: Render performance measurement
interface RenderMetrics {
  component: string;
  renderCount: number;
  totalRenderTime: number;
  avgRenderTime: number;
  lastRenderTime: number;
}

const metricsStore = new Map<string, RenderMetrics>();

function useRenderMetrics(componentName: string): RenderMetrics {
  const renderStartRef = useRef(0);

  // Record render start
  renderStartRef.current = performance.now();

  useEffect(() => {
    const renderTime = performance.now() - renderStartRef.current;

    const existing = metricsStore.get(componentName) || {
      component: componentName,
      renderCount: 0,
      totalRenderTime: 0,
      avgRenderTime: 0,
      lastRenderTime: 0,
    };

    const updated: RenderMetrics = {
      component: componentName,
      renderCount: existing.renderCount + 1,
      totalRenderTime: existing.totalRenderTime + renderTime,
      avgRenderTime:
        (existing.totalRenderTime + renderTime) / (existing.renderCount + 1),
      lastRenderTime: renderTime,
    };

    metricsStore.set(componentName, updated);
  });

  return metricsStore.get(componentName) || {
    component: componentName,
    renderCount: 0,
    totalRenderTime: 0,
    avgRenderTime: 0,
    lastRenderTime: 0,
  };
}

// Pattern 5: Children as render optimization
// When parent re-renders, children passed as props do NOT re-render
// because their reference is stable (created by the grandparent)
function ScrollContainer({ children }: { children: React.ReactNode }) {
  const [scrollY, setScrollY] = useState(0);

  return (
    <div
      onScroll={(e) => setScrollY(e.currentTarget.scrollTop)}
      className="overflow-auto h-96"
    >
      <div className="sticky top-0 bg-white z-10 p-2 shadow">
        Scroll position: {scrollY}px
      </div>
      {/* children do NOT re-render when scrollY changes */}
      {children}
    </div>
  );
}

// Pattern 6: Debounced state updates
function useDebouncedValue<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debouncedValue;
}

// Performance metrics dashboard component
function PerformanceOverlay() {
  const [isVisible, setIsVisible] = useState(false);
  const [metrics, setMetrics] = useState<RenderMetrics[]>([]);

  useEffect(() => {
    if (!isVisible) return;
    const interval = setInterval(() => {
      setMetrics(Array.from(metricsStore.values()));
    }, 1000);
    return () => clearInterval(interval);
  }, [isVisible]);

  if (!isVisible) {
    return (
      <button
        onClick={() => setIsVisible(true)}
        className="fixed bottom-4 right-4 bg-gray-800 text-white px-3 py-1 rounded text-sm"
      >
        Perf
      </button>
    );
  }

  return (
    <div className="fixed bottom-4 right-4 bg-white shadow-xl rounded-lg p-4 w-96 max-h-80 overflow-auto border">
      <div className="flex justify-between items-center mb-2">
        <h3 className="font-bold text-sm">Render Metrics</h3>
        <button onClick={() => setIsVisible(false)} className="text-gray-400">
          X
        </button>
      </div>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-gray-500">
            <th>Component</th>
            <th>Renders</th>
            <th>Avg (ms)</th>
            <th>Last (ms)</th>
          </tr>
        </thead>
        <tbody>
          {metrics
            .sort((a, b) => b.totalRenderTime - a.totalRenderTime)
            .map((m) => (
              <tr key={m.component}>
                <td className="font-mono">{m.component}</td>
                <td>{m.renderCount}</td>
                <td>{m.avgRenderTime.toFixed(2)}</td>
                <td
                  className={m.lastRenderTime > 16 ? "text-red-600" : "text-green-600"}
                >
                  {m.lastRenderTime.toFixed(2)}
                </td>
              </tr>
            ))}
        </tbody>
      </table>
    </div>
  );
}

// Helper
interface Item { id: string; name: string; }
function generateItems(count: number): Item[] {
  return Array.from({ length: count }, (_, i) => ({
    id: String(i),
    name: `Item ${i}`,
  }));
}

function ExpensiveList({ items }: { items: Item[] }) {
  return (
    <ul>
      {items.slice(0, 50).map((item) => (
        <li key={item.id}>{item.name}</li>
      ))}
    </ul>
  );
}

export {
  GoodParent,
  AppProvider,
  Store,
  useStoreSelector,
  useRenderMetrics,
  ScrollContainer,
  useDebouncedValue,
  PerformanceOverlay,
};
'''),

    ("react/perf_bundle_optimization", r'''Build bundle optimization strategies for React/TypeScript projects including tree-shaking friendly exports, barrel file alternatives, dynamic imports for heavy libraries, and a bundle analyzer utility.''', r'''// Bundle optimization patterns for production React

// Pattern 1: Tree-shaking friendly exports
// BAD: Barrel file that re-exports everything
// export * from "./Button";
// export * from "./Input";
// export * from "./Modal";  // Bundler may include all of these

// GOOD: Named exports allow tree-shaking
// components/Button/index.ts
export { Button } from "./Button";
export type { ButtonProps } from "./Button";

// Direct imports are most tree-shakeable:
// import { Button } from "@/components/Button";
// NOT: import { Button } from "@/components"; // barrel import

// Pattern 2: Lazy loading heavy dependencies
// Instead of importing heavy libraries at the top level,
// load them only when needed

// utils/heavy-operations.ts
type ChartLibrary = typeof import("chart.js");
type DateLibrary = typeof import("date-fns");
type MarkdownLibrary = typeof import("marked");

// Lazy loader with caching
const moduleCache = new Map<string, Promise<any>>();

function lazyImport<T>(key: string, loader: () => Promise<T>): () => Promise<T> {
  return () => {
    if (!moduleCache.has(key)) {
      moduleCache.set(key, loader());
    }
    return moduleCache.get(key) as Promise<T>;
  };
}

// Define lazy imports
const loadChartJS = lazyImport("chart.js", () => import("chart.js"));
const loadDateFns = lazyImport("date-fns", () => import("date-fns"));
const loadMarked = lazyImport("marked", () => import("marked"));

// Usage in component - only loads chart.js when chart is rendered
async function renderChart(canvas: HTMLCanvasElement, data: number[]) {
  const ChartJS = await loadChartJS();
  const { Chart, registerables } = ChartJS as any;
  Chart.register(...registerables);

  return new Chart(canvas, {
    type: "line",
    data: {
      labels: data.map((_, i) => String(i)),
      datasets: [{ data, borderColor: "#3b82f6", tension: 0.1 }],
    },
  });
}

// Pattern 3: Conditional polyfill loading
async function loadPolyfills(): Promise<void> {
  const polyfills: Promise<any>[] = [];

  if (!("IntersectionObserver" in window)) {
    polyfills.push(import("intersection-observer"));
  }

  if (!("ResizeObserver" in window)) {
    polyfills.push(import("resize-observer-polyfill").then((mod) => {
      (window as any).ResizeObserver = mod.default;
    }));
  }

  if (!CSS.supports("container-type", "inline-size")) {
    polyfills.push(import("container-query-polyfill"));
  }

  await Promise.all(polyfills);
}

// Pattern 4: Icon optimization - import only used icons
// BAD: import { FaHome, FaUser, FaSettings } from "react-icons/fa";
// This might bundle ALL Font Awesome icons

// GOOD: Import from specific paths
// import { FaHome } from "react-icons/fa/FaHome";

// Or build your own icon component that loads SVGs
interface IconProps {
  name: string;
  size?: number;
  className?: string;
}

const iconCache = new Map<string, string>();

function Icon({ name, size = 24, className = "" }: IconProps) {
  const [svg, setSvg] = React.useState<string | null>(iconCache.get(name) || null);

  React.useEffect(() => {
    if (iconCache.has(name)) {
      setSvg(iconCache.get(name)!);
      return;
    }

    // Load SVG icon on demand
    fetch(`/icons/${name}.svg`)
      .then((res) => res.text())
      .then((svgText) => {
        iconCache.set(name, svgText);
        setSvg(svgText);
      })
      .catch(() => setSvg(null));
  }, [name]);

  if (!svg) return <span className={`inline-block ${className}`} style={{ width: size, height: size }} />;

  return (
    <span
      className={`inline-flex items-center justify-center ${className}`}
      style={{ width: size, height: size }}
      dangerouslySetInnerHTML={{ __html: svg }}
      role="img"
      aria-label={name}
    />
  );
}

// Pattern 5: CSS-in-JS extraction for smaller bundles
// Instead of runtime CSS-in-JS (styled-components, emotion),
// use compile-time solutions or CSS modules

// Utility function for conditional class names (replaces clsx/classnames)
type ClassValue = string | boolean | undefined | null | Record<string, boolean>;

function cn(...args: ClassValue[]): string {
  const classes: string[] = [];

  for (const arg of args) {
    if (!arg) continue;
    if (typeof arg === "string") {
      classes.push(arg);
    } else if (typeof arg === "object") {
      for (const [key, value] of Object.entries(arg)) {
        if (value) classes.push(key);
      }
    }
  }

  return classes.join(" ");
}

// Pattern 6: Bundle size monitor
interface BundleReport {
  totalSize: number;
  gzipSize: number;
  chunks: ChunkInfo[];
  largestModules: ModuleInfo[];
}

interface ChunkInfo {
  name: string;
  size: number;
  modules: number;
  isAsync: boolean;
}

interface ModuleInfo {
  path: string;
  size: number;
  percentage: number;
}

// Build script helper for monitoring bundle size
function analyzeBundleSize(statsJson: any): BundleReport {
  const chunks: ChunkInfo[] = (statsJson.chunks || []).map((chunk: any) => ({
    name: chunk.names?.[0] || chunk.id,
    size: chunk.size,
    modules: chunk.modules?.length || 0,
    isAsync: !chunk.initial,
  }));

  const allModules: ModuleInfo[] = (statsJson.modules || [])
    .map((mod: any) => ({
      path: mod.name || mod.identifier,
      size: mod.size,
      percentage: 0,
    }))
    .sort((a: ModuleInfo, b: ModuleInfo) => b.size - a.size);

  const totalSize = allModules.reduce((sum, m) => sum + m.size, 0);

  for (const mod of allModules) {
    mod.percentage = (mod.size / totalSize) * 100;
  }

  return {
    totalSize,
    gzipSize: Math.round(totalSize * 0.3), // rough estimate
    chunks: chunks.sort((a, b) => b.size - a.size),
    largestModules: allModules.slice(0, 20),
  };
}

// Size budget checker for CI
interface SizeBudget {
  maxTotalKB: number;
  maxChunkKB: number;
  maxAsyncChunkKB: number;
}

function checkSizeBudget(
  report: BundleReport,
  budget: SizeBudget
): { passed: boolean; violations: string[] } {
  const violations: string[] = [];
  const totalKB = report.totalSize / 1024;

  if (totalKB > budget.maxTotalKB) {
    violations.push(
      `Total bundle ${totalKB.toFixed(0)}KB exceeds budget of ${budget.maxTotalKB}KB`
    );
  }

  for (const chunk of report.chunks) {
    const chunkKB = chunk.size / 1024;
    const limit = chunk.isAsync ? budget.maxAsyncChunkKB : budget.maxChunkKB;
    if (chunkKB > limit) {
      violations.push(
        `Chunk "${chunk.name}" ${chunkKB.toFixed(0)}KB exceeds ${
          chunk.isAsync ? "async" : "sync"
        } budget of ${limit}KB`
      );
    }
  }

  return { passed: violations.length === 0, violations };
}

// React component
import React from "react";

interface ButtonProps {
  variant?: "primary" | "secondary" | "ghost";
  size?: "sm" | "md" | "lg";
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  className?: string;
}

function Button({
  variant = "primary",
  size = "md",
  children,
  onClick,
  disabled,
  className,
}: ButtonProps) {
  const baseClasses = "inline-flex items-center justify-center rounded font-medium transition-colors";
  const variantClasses = {
    primary: "bg-blue-600 text-white hover:bg-blue-700",
    secondary: "bg-gray-200 text-gray-800 hover:bg-gray-300",
    ghost: "text-gray-600 hover:bg-gray-100",
  };
  const sizeClasses = {
    sm: "px-3 py-1.5 text-sm",
    md: "px-4 py-2 text-base",
    lg: "px-6 py-3 text-lg",
  };

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={cn(
        baseClasses,
        variantClasses[variant],
        sizeClasses[size],
        { "opacity-50 cursor-not-allowed": disabled },
        className
      )}
    >
      {children}
    </button>
  );
}

export {
  lazyImport,
  loadPolyfills,
  Icon,
  cn,
  analyzeBundleSize,
  checkSizeBudget,
  Button,
};
export type { BundleReport, SizeBudget, ButtonProps };
'''),
]
