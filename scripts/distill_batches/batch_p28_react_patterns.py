"""React patterns — hooks, state management, performance, server components, testing."""

PAIRS = [
    (
        "react/custom-hooks",
        "Show advanced React custom hooks: data fetching, debouncing, intersection observer, local storage sync, and media queries.",
        '''Advanced custom hooks for React applications:

```typescript
import { useState, useEffect, useRef, useCallback, useMemo } from 'react';

// --- useFetch with caching and abort ---

interface FetchState<T> {
    data: T | null;
    error: Error | null;
    loading: boolean;
}

const cache = new Map<string, { data: any; timestamp: number }>();

function useFetch<T>(url: string, options?: RequestInit & { cacheTTL?: number }): FetchState<T> {
    const [state, setState] = useState<FetchState<T>>({
        data: null, error: null, loading: true,
    });
    const abortRef = useRef<AbortController>();
    const cacheTTL = options?.cacheTTL ?? 60000;

    useEffect(() => {
        // Check cache
        const cached = cache.get(url);
        if (cached && Date.now() - cached.timestamp < cacheTTL) {
            setState({ data: cached.data, error: null, loading: false });
            return;
        }

        abortRef.current?.abort();
        const controller = new AbortController();
        abortRef.current = controller;

        setState(prev => ({ ...prev, loading: true }));

        fetch(url, { ...options, signal: controller.signal })
            .then(res => {
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return res.json();
            })
            .then(data => {
                cache.set(url, { data, timestamp: Date.now() });
                setState({ data, error: null, loading: false });
            })
            .catch(err => {
                if (err.name !== 'AbortError') {
                    setState({ data: null, error: err, loading: false });
                }
            });

        return () => controller.abort();
    }, [url]);

    return state;
}

// --- useDebounce ---

function useDebounce<T>(value: T, delay: number): T {
    const [debouncedValue, setDebouncedValue] = useState(value);

    useEffect(() => {
        const timer = setTimeout(() => setDebouncedValue(value), delay);
        return () => clearTimeout(timer);
    }, [value, delay]);

    return debouncedValue;
}

function useDebouncedCallback<T extends (...args: any[]) => any>(
    callback: T,
    delay: number,
): T {
    const callbackRef = useRef(callback);
    callbackRef.current = callback;
    const timerRef = useRef<ReturnType<typeof setTimeout>>();

    return useCallback(
        ((...args: any[]) => {
            clearTimeout(timerRef.current);
            timerRef.current = setTimeout(() => callbackRef.current(...args), delay);
        }) as T,
        [delay],
    );
}

// --- useIntersectionObserver ---

function useIntersectionObserver(
    options: IntersectionObserverInit = {},
): [React.RefObject<HTMLElement>, boolean] {
    const ref = useRef<HTMLElement>(null);
    const [isVisible, setIsVisible] = useState(false);

    useEffect(() => {
        const element = ref.current;
        if (!element) return;

        const observer = new IntersectionObserver(([entry]) => {
            setIsVisible(entry.isIntersecting);
        }, options);

        observer.observe(element);
        return () => observer.disconnect();
    }, [options.threshold, options.rootMargin]);

    return [ref, isVisible];
}

// Usage: lazy load component
function LazyImage({ src, alt }: { src: string; alt: string }) {
    const [ref, isVisible] = useIntersectionObserver({ rootMargin: '200px' });
    return (
        <div ref={ref}>
            {isVisible ? <img src={src} alt={alt} /> : <div className="placeholder" />}
        </div>
    );
}

// --- useLocalStorage ---

function useLocalStorage<T>(key: string, initialValue: T): [T, (value: T | ((prev: T) => T)) => void] {
    const [storedValue, setStoredValue] = useState<T>(() => {
        try {
            const item = window.localStorage.getItem(key);
            return item ? JSON.parse(item) : initialValue;
        } catch {
            return initialValue;
        }
    });

    const setValue = useCallback((value: T | ((prev: T) => T)) => {
        setStoredValue(prev => {
            const newValue = value instanceof Function ? value(prev) : value;
            window.localStorage.setItem(key, JSON.stringify(newValue));
            return newValue;
        });
    }, [key]);

    // Sync across tabs
    useEffect(() => {
        const handleStorage = (e: StorageEvent) => {
            if (e.key === key && e.newValue) {
                setStoredValue(JSON.parse(e.newValue));
            }
        };
        window.addEventListener('storage', handleStorage);
        return () => window.removeEventListener('storage', handleStorage);
    }, [key]);

    return [storedValue, setValue];
}

// --- useMediaQuery ---

function useMediaQuery(query: string): boolean {
    const [matches, setMatches] = useState(() =>
        window.matchMedia(query).matches
    );

    useEffect(() => {
        const mql = window.matchMedia(query);
        const handler = (e: MediaQueryListEvent) => setMatches(e.matches);
        mql.addEventListener('change', handler);
        return () => mql.removeEventListener('change', handler);
    }, [query]);

    return matches;
}

// Usage:
// const isMobile = useMediaQuery('(max-width: 768px)');
// const prefersColorScheme = useMediaQuery('(prefers-color-scheme: dark)');

// --- usePrevious ---

function usePrevious<T>(value: T): T | undefined {
    const ref = useRef<T>();
    useEffect(() => { ref.current = value; });
    return ref.current;
}
```

Hook rules:
1. **Only call at top level** — no conditionals, loops, or nested functions
2. **Only call from React functions** — components or other hooks
3. **Name with `use` prefix** — convention that enables lint rules
4. **Return stable references** — useCallback/useMemo for objects/functions'''
    ),
    (
        "react/performance-optimization",
        "Show React performance optimization: memo, useMemo, useCallback, virtualization, code splitting, and profiling techniques.",
        '''React performance patterns for production apps:

```typescript
import React, { memo, useMemo, useCallback, lazy, Suspense, startTransition } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';

// --- React.memo (prevent unnecessary re-renders) ---

// Only re-renders if props change (shallow comparison)
const ExpensiveItem = memo(function ExpensiveItem({
    item,
    onSelect,
}: {
    item: Item;
    onSelect: (id: string) => void;
}) {
    return (
        <div onClick={() => onSelect(item.id)}>
            <h3>{item.name}</h3>
            <p>{item.description}</p>
        </div>
    );
});

// Custom comparison for complex props
const ChartComponent = memo(
    function Chart({ data, config }: ChartProps) {
        return <canvas ref={drawChart(data, config)} />;
    },
    (prev, next) => {
        // Only re-render if data length changes or config changes
        return prev.data.length === next.data.length &&
               prev.config.type === next.config.type;
    },
);

// --- Stable callbacks with useCallback ---

function ParentComponent({ items }: { items: Item[] }) {
    const [selectedId, setSelectedId] = useState<string | null>(null);

    // BAD: new function every render → children always re-render
    // const handleSelect = (id: string) => setSelectedId(id);

    // GOOD: stable reference
    const handleSelect = useCallback((id: string) => {
        setSelectedId(id);
    }, []); // Empty deps = never changes

    // Memoize derived data
    const sortedItems = useMemo(
        () => [...items].sort((a, b) => a.name.localeCompare(b.name)),
        [items],
    );

    return (
        <div>
            {sortedItems.map(item => (
                <ExpensiveItem
                    key={item.id}
                    item={item}
                    onSelect={handleSelect}
                />
            ))}
        </div>
    );
}

// --- Virtualization (render only visible items) ---

function VirtualList({ items }: { items: Item[] }) {
    const parentRef = React.useRef<HTMLDivElement>(null);

    const virtualizer = useVirtualizer({
        count: items.length,
        getScrollElement: () => parentRef.current,
        estimateSize: () => 60,  // Estimated row height
        overscan: 5,  // Render 5 extra items above/below viewport
    });

    return (
        <div ref={parentRef} style={{ height: '600px', overflow: 'auto' }}>
            <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
                {virtualizer.getVirtualItems().map(virtualRow => (
                    <div
                        key={virtualRow.key}
                        style={{
                            position: 'absolute',
                            top: 0,
                            left: 0,
                            width: '100%',
                            transform: `translateY(${virtualRow.start}px)`,
                        }}
                    >
                        <ItemRow item={items[virtualRow.index]} />
                    </div>
                ))}
            </div>
        </div>
    );
}

// --- Code Splitting with lazy/Suspense ---

const Dashboard = lazy(() => import('./Dashboard'));
const Settings = lazy(() => import('./Settings'));
const Analytics = lazy(() =>
    import('./Analytics').then(mod => ({ default: mod.AnalyticsPage }))
);

function App() {
    return (
        <Suspense fallback={<LoadingSpinner />}>
            <Routes>
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="/analytics" element={<Analytics />} />
            </Routes>
        </Suspense>
    );
}

// --- useTransition (non-blocking state updates) ---

function SearchWithTransition() {
    const [query, setQuery] = useState('');
    const [results, setResults] = useState<Item[]>([]);
    const [isPending, startTransition] = useTransition();

    const handleSearch = (e: React.ChangeEvent<HTMLInputElement>) => {
        const value = e.target.value;
        setQuery(value);  // Urgent: update input immediately

        startTransition(() => {
            // Non-urgent: search can be interrupted
            setResults(filterItems(value));
        });
    };

    return (
        <div>
            <input value={query} onChange={handleSearch} />
            {isPending && <Spinner />}
            <ResultList items={results} />
        </div>
    );
}
```

Performance checklist:
1. **Profile first** — React DevTools Profiler, why-did-you-render
2. **Avoid premature optimization** — measure before memoizing
3. **memo + useCallback** — stabilize props for child components
4. **Virtualize long lists** — @tanstack/react-virtual for 1000+ items
5. **Code split routes** — lazy() + Suspense for route-level splitting
6. **useTransition** — keep UI responsive during heavy updates
7. **Keys** — stable, unique keys prevent unnecessary DOM recreation'''
    ),
    (
        "react/state-management",
        "Compare React state management approaches: useState, useReducer, Context, Zustand, and when to use each. Show practical examples.",
        '''React state management — choosing the right tool:

```typescript
// --- 1. useState: Simple local state ---

function Counter() {
    const [count, setCount] = useState(0);
    return <button onClick={() => setCount(c => c + 1)}>{count}</button>;
}

// --- 2. useReducer: Complex local state with actions ---

interface TodoState {
    todos: Todo[];
    filter: 'all' | 'active' | 'done';
}

type TodoAction =
    | { type: 'ADD'; text: string }
    | { type: 'TOGGLE'; id: string }
    | { type: 'DELETE'; id: string }
    | { type: 'SET_FILTER'; filter: TodoState['filter'] };

function todoReducer(state: TodoState, action: TodoAction): TodoState {
    switch (action.type) {
        case 'ADD':
            return {
                ...state,
                todos: [...state.todos, { id: crypto.randomUUID(), text: action.text, done: false }],
            };
        case 'TOGGLE':
            return {
                ...state,
                todos: state.todos.map(t =>
                    t.id === action.id ? { ...t, done: !t.done } : t
                ),
            };
        case 'DELETE':
            return {
                ...state,
                todos: state.todos.filter(t => t.id !== action.id),
            };
        case 'SET_FILTER':
            return { ...state, filter: action.filter };
    }
}

function TodoApp() {
    const [state, dispatch] = useReducer(todoReducer, { todos: [], filter: 'all' });
    const filtered = useMemo(() => {
        if (state.filter === 'all') return state.todos;
        return state.todos.filter(t => state.filter === 'done' ? t.done : !t.done);
    }, [state.todos, state.filter]);

    return (
        <>
            <input onKeyDown={e => {
                if (e.key === 'Enter') dispatch({ type: 'ADD', text: e.currentTarget.value });
            }} />
            {filtered.map(t => (
                <TodoItem key={t.id} todo={t} dispatch={dispatch} />
            ))}
        </>
    );
}

// --- 3. Context: Shared state for subtree (low-frequency updates) ---

interface AuthContextType {
    user: User | null;
    login: (credentials: Credentials) => Promise<void>;
    logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

function useAuth() {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error('useAuth must be within AuthProvider');
    return ctx;
}

function AuthProvider({ children }: { children: React.ReactNode }) {
    const [user, setUser] = useState<User | null>(null);

    const login = useCallback(async (creds: Credentials) => {
        const user = await api.login(creds);
        setUser(user);
    }, []);

    const logout = useCallback(() => {
        api.logout();
        setUser(null);
    }, []);

    const value = useMemo(() => ({ user, login, logout }), [user, login, logout]);
    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// --- 4. Zustand: Global state (simple, scalable) ---

import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';

interface CartStore {
    items: CartItem[];
    addItem: (product: Product, quantity: number) => void;
    removeItem: (productId: string) => void;
    updateQuantity: (productId: string, quantity: number) => void;
    clearCart: () => void;
    total: () => number;
}

const useCartStore = create<CartStore>()(
    devtools(
        persist(
            (set, get) => ({
                items: [],

                addItem: (product, quantity) => set(state => {
                    const existing = state.items.find(i => i.productId === product.id);
                    if (existing) {
                        return {
                            items: state.items.map(i =>
                                i.productId === product.id
                                    ? { ...i, quantity: i.quantity + quantity }
                                    : i
                            ),
                        };
                    }
                    return {
                        items: [...state.items, {
                            productId: product.id,
                            name: product.name,
                            price: product.price,
                            quantity,
                        }],
                    };
                }),

                removeItem: (productId) => set(state => ({
                    items: state.items.filter(i => i.productId !== productId),
                })),

                updateQuantity: (productId, quantity) => set(state => ({
                    items: state.items.map(i =>
                        i.productId === productId ? { ...i, quantity } : i
                    ),
                })),

                clearCart: () => set({ items: [] }),

                total: () => get().items.reduce(
                    (sum, item) => sum + item.price * item.quantity, 0
                ),
            }),
            { name: 'cart-storage' }, // localStorage persistence
        ),
    ),
);

// Selectors for minimal re-renders
function CartCount() {
    const count = useCartStore(state => state.items.length);
    return <span>{count} items</span>;
}

function CartTotal() {
    const total = useCartStore(state => state.total());
    return <span>${total.toFixed(2)}</span>;
}
```

Decision guide:
| Need | Tool | Why |
|------|------|-----|
| Component-local | useState | Simplest, no sharing needed |
| Complex local logic | useReducer | Action-based updates, testable |
| Theme/auth/locale | Context | Low-frequency, tree-wide |
| UI state (cart, modals) | Zustand | Simple API, selective re-renders |
| Server data | TanStack Query | Caching, dedup, background refresh |
| Forms | React Hook Form | Uncontrolled for performance |'''
    ),
    (
        "react/testing-patterns",
        "Show React component testing with Testing Library. Include user interaction testing, async testing, and mocking patterns.",
        '''React Testing Library patterns for reliable tests:

```typescript
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { rest } from 'msw';
import { setupServer } from 'msw/node';

// --- Basic component testing ---

function Greeting({ name }: { name: string }) {
    return <h1>Hello, {name}!</h1>;
}

test('renders greeting with name', () => {
    render(<Greeting name="Alice" />);
    expect(screen.getByRole('heading')).toHaveTextContent('Hello, Alice!');
});

// --- User interaction testing ---

function LoginForm({ onSubmit }: { onSubmit: (data: LoginData) => void }) {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (!email.includes('@')) {
            setError('Invalid email');
            return;
        }
        onSubmit({ email, password });
    };

    return (
        <form onSubmit={handleSubmit}>
            <label htmlFor="email">Email</label>
            <input id="email" type="email" value={email}
                   onChange={e => setEmail(e.target.value)} />
            <label htmlFor="password">Password</label>
            <input id="password" type="password" value={password}
                   onChange={e => setPassword(e.target.value)} />
            {error && <div role="alert">{error}</div>}
            <button type="submit">Log in</button>
        </form>
    );
}

test('submits login form with valid data', async () => {
    const user = userEvent.setup();
    const handleSubmit = jest.fn();
    render(<LoginForm onSubmit={handleSubmit} />);

    await user.type(screen.getByLabelText('Email'), 'alice@test.com');
    await user.type(screen.getByLabelText('Password'), 'password123');
    await user.click(screen.getByRole('button', { name: 'Log in' }));

    expect(handleSubmit).toHaveBeenCalledWith({
        email: 'alice@test.com',
        password: 'password123',
    });
});

test('shows error for invalid email', async () => {
    const user = userEvent.setup();
    render(<LoginForm onSubmit={jest.fn()} />);

    await user.type(screen.getByLabelText('Email'), 'invalid');
    await user.click(screen.getByRole('button', { name: 'Log in' }));

    expect(screen.getByRole('alert')).toHaveTextContent('Invalid email');
});

// --- Async testing with MSW (Mock Service Worker) ---

const server = setupServer(
    rest.get('/api/users', (req, res, ctx) => {
        return res(ctx.json([
            { id: '1', name: 'Alice' },
            { id: '2', name: 'Bob' },
        ]));
    }),
    rest.post('/api/users', async (req, res, ctx) => {
        const body = await req.json();
        return res(ctx.status(201), ctx.json({ id: '3', ...body }));
    }),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function UserList() {
    const [users, setUsers] = useState<User[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetch('/api/users')
            .then(res => res.json())
            .then(data => { setUsers(data); setLoading(false); });
    }, []);

    if (loading) return <div>Loading...</div>;
    return (
        <ul>
            {users.map(u => <li key={u.id}>{u.name}</li>)}
        </ul>
    );
}

test('loads and displays users', async () => {
    render(<UserList />);

    // Loading state
    expect(screen.getByText('Loading...')).toBeInTheDocument();

    // Wait for data
    await waitFor(() => {
        expect(screen.getByText('Alice')).toBeInTheDocument();
        expect(screen.getByText('Bob')).toBeInTheDocument();
    });
});

test('handles API error', async () => {
    server.use(
        rest.get('/api/users', (req, res, ctx) => {
            return res(ctx.status(500));
        }),
    );

    render(<UserList />);
    await waitFor(() => {
        expect(screen.getByText(/error/i)).toBeInTheDocument();
    });
});

// --- Testing with context providers ---

function renderWithProviders(ui: React.ReactElement, options?: {
    user?: User;
    route?: string;
}) {
    const Wrapper = ({ children }: { children: React.ReactNode }) => (
        <AuthProvider initialUser={options?.user}>
            <MemoryRouter initialEntries={[options?.route || '/']}>
                {children}
            </MemoryRouter>
        </AuthProvider>
    );
    return render(ui, { wrapper: Wrapper });
}

test('shows admin panel for admin users', () => {
    renderWithProviders(<Dashboard />, {
        user: { id: '1', name: 'Admin', role: 'admin' },
        route: '/dashboard',
    });
    expect(screen.getByText('Admin Panel')).toBeInTheDocument();
});
```

Testing principles:
1. **Query by accessibility** — getByRole, getByLabelText, getByText
2. **User-centric** — test what users see and do, not implementation
3. **Avoid implementation details** — no testing state, refs, or internal methods
4. **MSW for API mocking** — intercepts at network level, realistic
5. **userEvent over fireEvent** — simulates real user interactions'''
    ),
]
