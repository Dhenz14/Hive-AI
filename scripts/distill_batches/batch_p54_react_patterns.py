"""React — hooks, patterns, state management, and performance optimization."""

PAIRS = [
    (
        "react/hooks-patterns",
        "Show React hooks patterns: custom hooks, useReducer, useCallback, useMemo, and refs.",
        '''React hooks patterns:

```tsx
import {
  useState, useEffect, useReducer, useCallback, useMemo,
  useRef, useId, useDeferredValue, useTransition,
  type ReactNode, type Dispatch,
} from 'react';


// --- useReducer for complex state ---

interface TodoState {
  items: Todo[];
  filter: 'all' | 'active' | 'completed';
  loading: boolean;
}

type TodoAction =
  | { type: 'ADD'; payload: string }
  | { type: 'TOGGLE'; payload: string }
  | { type: 'DELETE'; payload: string }
  | { type: 'SET_FILTER'; payload: TodoState['filter'] }
  | { type: 'SET_LOADING'; payload: boolean }
  | { type: 'LOAD'; payload: Todo[] };

function todoReducer(state: TodoState, action: TodoAction): TodoState {
  switch (action.type) {
    case 'ADD':
      return {
        ...state,
        items: [...state.items, {
          id: crypto.randomUUID(),
          text: action.payload,
          completed: false,
        }],
      };
    case 'TOGGLE':
      return {
        ...state,
        items: state.items.map(item =>
          item.id === action.payload
            ? { ...item, completed: !item.completed }
            : item
        ),
      };
    case 'DELETE':
      return {
        ...state,
        items: state.items.filter(item => item.id !== action.payload),
      };
    case 'SET_FILTER':
      return { ...state, filter: action.payload };
    case 'SET_LOADING':
      return { ...state, loading: action.payload };
    case 'LOAD':
      return { ...state, items: action.payload, loading: false };
    default:
      return state;
  }
}


// --- Custom hooks ---

function useFetch<T>(url: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);

    fetch(url, { signal: controller.signal })
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(setData)
      .catch(err => {
        if (err.name !== 'AbortError') setError(err.message);
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  }, [url]);

  return { data, error, loading };
}


function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debounced;
}


function useLocalStorage<T>(key: string, initialValue: T) {
  const [value, setValue] = useState<T>(() => {
    try {
      const stored = localStorage.getItem(key);
      return stored ? JSON.parse(stored) : initialValue;
    } catch {
      return initialValue;
    }
  });

  useEffect(() => {
    localStorage.setItem(key, JSON.stringify(value));
  }, [key, value]);

  return [value, setValue] as const;
}


function useIntersectionObserver(
  ref: React.RefObject<HTMLElement>,
  options: IntersectionObserverInit = {},
) {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    if (!ref.current) return;
    const observer = new IntersectionObserver(
      ([entry]) => setIsVisible(entry.isIntersecting),
      options,
    );
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, [ref, options.threshold, options.rootMargin]);

  return isVisible;
}


function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(
    () => window.matchMedia(query).matches,
  );

  useEffect(() => {
    const mq = window.matchMedia(query);
    const handler = (e: MediaQueryListEvent) => setMatches(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, [query]);

  return matches;
}


// --- Performance: useCallback + useMemo ---

function ProductList({ products, onSelect }: Props) {
  // Memoize filtered list
  const [search, setSearch] = useState('');
  const deferredSearch = useDeferredValue(search);

  const filtered = useMemo(
    () => products.filter(p =>
      p.name.toLowerCase().includes(deferredSearch.toLowerCase())
    ),
    [products, deferredSearch],
  );

  // Stable callback reference
  const handleSelect = useCallback((id: string) => {
    onSelect(id);
  }, [onSelect]);

  return (
    <div>
      <input value={search} onChange={e => setSearch(e.target.value)} />
      {filtered.map(product => (
        <ProductCard
          key={product.id}
          product={product}
          onSelect={handleSelect}
        />
      ))}
    </div>
  );
}
```

Hook patterns:
1. **`useReducer`** — complex state with multiple sub-values or actions
2. **Custom hooks** — extract and reuse stateful logic (`useFetch`, `useDebounce`)
3. **`useCallback`** — stable function reference for child component memoization
4. **`useMemo`** — cache expensive computations
5. **`useDeferredValue`** — keep UI responsive during heavy filtering'''
    ),
    (
        "react/component-patterns",
        "Show React component patterns: compound components, render props, HOCs, and error boundaries.",
        '''React component patterns:

```tsx
import {
  createContext, useContext, useState, useCallback,
  type ReactNode, type ComponentType,
  Component, type ErrorInfo,
} from 'react';


// --- Compound components ---

interface TabsContextType {
  activeTab: string;
  setActiveTab: (tab: string) => void;
}

const TabsContext = createContext<TabsContextType | null>(null);

function Tabs({ children, defaultTab }: { children: ReactNode; defaultTab: string }) {
  const [activeTab, setActiveTab] = useState(defaultTab);
  return (
    <TabsContext.Provider value={{ activeTab, setActiveTab }}>
      <div className="tabs">{children}</div>
    </TabsContext.Provider>
  );
}

function TabList({ children }: { children: ReactNode }) {
  return <div role="tablist" className="tab-list">{children}</div>;
}

function Tab({ value, children }: { value: string; children: ReactNode }) {
  const ctx = useContext(TabsContext);
  if (!ctx) throw new Error('Tab must be inside Tabs');
  return (
    <button
      role="tab"
      aria-selected={ctx.activeTab === value}
      className={ctx.activeTab === value ? 'active' : ''}
      onClick={() => ctx.setActiveTab(value)}
    >
      {children}
    </button>
  );
}

function TabPanel({ value, children }: { value: string; children: ReactNode }) {
  const ctx = useContext(TabsContext);
  if (!ctx) throw new Error('TabPanel must be inside Tabs');
  if (ctx.activeTab !== value) return null;
  return <div role="tabpanel">{children}</div>;
}

Tabs.List = TabList;
Tabs.Tab = Tab;
Tabs.Panel = TabPanel;

// Usage:
// <Tabs defaultTab="overview">
//   <Tabs.List>
//     <Tabs.Tab value="overview">Overview</Tabs.Tab>
//     <Tabs.Tab value="settings">Settings</Tabs.Tab>
//   </Tabs.List>
//   <Tabs.Panel value="overview">Overview content</Tabs.Panel>
//   <Tabs.Panel value="settings">Settings content</Tabs.Panel>
// </Tabs>


// --- Slot pattern (flexible layouts) ---

interface CardProps {
  header?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
}

function Card({ header, footer, children }: CardProps) {
  return (
    <div className="card">
      {header && <div className="card-header">{header}</div>}
      <div className="card-body">{children}</div>
      {footer && <div className="card-footer">{footer}</div>}
    </div>
  );
}


// --- Error boundary ---

interface ErrorBoundaryProps {
  fallback: ReactNode | ((error: Error, reset: () => void) => ReactNode);
  children: ReactNode;
  onError?: (error: Error, info: ErrorInfo) => void;
}

interface ErrorBoundaryState {
  error: Error | null;
}

class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    this.props.onError?.(error, info);
  }

  reset = () => this.setState({ error: null });

  render() {
    if (this.state.error) {
      const { fallback } = this.props;
      if (typeof fallback === 'function') {
        return fallback(this.state.error, this.reset);
      }
      return fallback;
    }
    return this.props.children;
  }
}

// Usage:
// <ErrorBoundary
//   fallback={(error, reset) => (
//     <div>
//       <p>Something went wrong: {error.message}</p>
//       <button onClick={reset}>Try Again</button>
//     </div>
//   )}
//   onError={(error) => reportToSentry(error)}
// >
//   <App />
// </ErrorBoundary>


// --- Polymorphic component ---

type PolymorphicProps<C extends React.ElementType> = {
  as?: C;
  children: ReactNode;
} & React.ComponentPropsWithoutRef<C>;

function Box<C extends React.ElementType = 'div'>({
  as, children, ...props
}: PolymorphicProps<C>) {
  const Component = as || 'div';
  return <Component {...props}>{children}</Component>;
}

// <Box>div by default</Box>
// <Box as="section">renders as section</Box>
// <Box as="a" href="/link">renders as anchor with href</Box>
```

Component patterns:
1. **Compound components** — parent manages state, children render parts (Tabs, Accordion)
2. **Slot pattern** — named ReactNode props for flexible layouts
3. **Error boundary** — catch render errors, show fallback, allow retry
4. **Polymorphic `as` prop** — component renders as different HTML elements
5. **Context + Provider** — share state without prop drilling'''
    ),
    (
        "react/nextjs-patterns",
        "Show Next.js App Router patterns: server components, data fetching, caching, and route handlers.",
        '''Next.js App Router patterns:

```tsx
// --- Server Component (default) ---
// app/products/page.tsx

import { Suspense } from 'react';
import { ProductList } from './product-list';
import { ProductFilters } from './product-filters';

interface SearchParams {
  category?: string;
  sort?: string;
  page?: string;
}

export default async function ProductsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;

  return (
    <div className="flex gap-4">
      <ProductFilters currentCategory={params.category} />

      <Suspense fallback={<ProductsSkeleton />}>
        <ProductList
          category={params.category}
          sort={params.sort || 'newest'}
          page={Number(params.page) || 1}
        />
      </Suspense>
    </div>
  );
}

// Server component with data fetching
async function ProductList({ category, sort, page }: {
  category?: string; sort: string; page: number;
}) {
  const products = await getProducts({ category, sort, page });

  return (
    <div className="grid grid-cols-3 gap-4">
      {products.items.map(product => (
        <ProductCard key={product.id} product={product} />
      ))}
      <Pagination total={products.total} page={page} perPage={20} />
    </div>
  );
}


// --- Data fetching with caching ---
// lib/data.ts

async function getProducts(params: {
  category?: string; sort: string; page: number;
}) {
  const url = new URL('https://api.example.com/products');
  if (params.category) url.searchParams.set('category', params.category);
  url.searchParams.set('sort', params.sort);
  url.searchParams.set('page', String(params.page));

  const res = await fetch(url.toString(), {
    next: { revalidate: 60 },  // ISR: revalidate every 60s
  });

  if (!res.ok) throw new Error('Failed to fetch products');
  return res.json();
}

async function getProduct(id: string) {
  const res = await fetch(`https://api.example.com/products/${id}`, {
    next: { tags: [`product-${id}`] },  // Tag-based revalidation
  });
  if (!res.ok) throw new Error('Product not found');
  return res.json();
}


// --- Server Action ---
// app/products/actions.ts
'use server';

import { revalidateTag, revalidatePath } from 'next/cache';
import { redirect } from 'next/navigation';

export async function createProduct(formData: FormData) {
  const name = formData.get('name') as string;
  const price = parseFloat(formData.get('price') as string);

  if (!name || name.length < 2) {
    return { error: 'Name must be at least 2 characters' };
  }

  const product = await db.products.create({ name, price });
  revalidatePath('/products');
  redirect(`/products/${product.id}`);
}

export async function updateProduct(id: string, formData: FormData) {
  await db.products.update(id, {
    name: formData.get('name') as string,
    price: parseFloat(formData.get('price') as string),
  });
  revalidateTag(`product-${id}`);
}


// --- Client Component ---
// app/products/product-filters.tsx
'use client';

import { useRouter, useSearchParams, usePathname } from 'next/navigation';
import { useTransition } from 'react';

export function ProductFilters({ currentCategory }: { currentCategory?: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();

  function setCategory(category: string) {
    startTransition(() => {
      const params = new URLSearchParams(searchParams.toString());
      if (category) {
        params.set('category', category);
      } else {
        params.delete('category');
      }
      params.delete('page');
      router.push(`${pathname}?${params.toString()}`);
    });
  }

  return (
    <div className={isPending ? 'opacity-50' : ''}>
      {categories.map(cat => (
        <button
          key={cat}
          onClick={() => setCategory(cat)}
          className={currentCategory === cat ? 'active' : ''}
        >
          {cat}
        </button>
      ))}
    </div>
  );
}


// --- Route Handler (API) ---
// app/api/products/route.ts

import { NextRequest, NextResponse } from 'next/server';

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const page = Number(searchParams.get('page')) || 1;

  const products = await db.products.findMany({
    skip: (page - 1) * 20,
    take: 20,
  });

  return NextResponse.json(products);
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  const product = await db.products.create({ data: body });
  return NextResponse.json(product, { status: 201 });
}
```

Next.js patterns:
1. **Server Components** — fetch data directly in components, zero client JS
2. **`Suspense`** — streaming with loading fallbacks
3. **Server Actions** — form mutations with `revalidatePath`/`revalidateTag`
4. **`'use client'`** — opt into client interactivity only when needed
5. **`useTransition`** — non-blocking navigation with pending states'''
    ),
]
"""
