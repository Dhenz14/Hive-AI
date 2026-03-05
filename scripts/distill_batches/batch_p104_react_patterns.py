"""React — advanced hooks, state management, and component patterns."""

PAIRS = [
    (
        "frontend/react-hooks-advanced",
        "Show advanced React hook patterns: custom hooks, useReducer, useSyncExternalStore, and hook composition.",
        '''Advanced React hook patterns:

```typescript
import {
  useState, useEffect, useCallback, useMemo, useRef,
  useReducer, useSyncExternalStore, useId, useDeferredValue,
} from 'react';


// --- useReducer for complex state ---

type State = {
  items: Item[];
  loading: boolean;
  error: string | null;
  filter: string;
  page: number;
};

type Action =
  | { type: 'FETCH_START' }
  | { type: 'FETCH_SUCCESS'; items: Item[] }
  | { type: 'FETCH_ERROR'; error: string }
  | { type: 'SET_FILTER'; filter: string }
  | { type: 'NEXT_PAGE' }
  | { type: 'ADD_ITEM'; item: Item }
  | { type: 'REMOVE_ITEM'; id: string };

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'FETCH_START':
      return { ...state, loading: true, error: null };
    case 'FETCH_SUCCESS':
      return { ...state, loading: false, items: action.items };
    case 'FETCH_ERROR':
      return { ...state, loading: false, error: action.error };
    case 'SET_FILTER':
      return { ...state, filter: action.filter, page: 1 };
    case 'NEXT_PAGE':
      return { ...state, page: state.page + 1 };
    case 'ADD_ITEM':
      return { ...state, items: [...state.items, action.item] };
    case 'REMOVE_ITEM':
      return { ...state, items: state.items.filter(i => i.id !== action.id) };
  }
}


// --- Custom hooks ---

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debounced;
}


function useLocalStorage<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(() => {
    try {
      const stored = localStorage.getItem(key);
      return stored ? JSON.parse(stored) : initial;
    } catch {
      return initial;
    }
  });

  useEffect(() => {
    localStorage.setItem(key, JSON.stringify(value));
  }, [key, value]);

  return [value, setValue] as const;
}


function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(
    () => window.matchMedia(query).matches
  );

  useEffect(() => {
    const mql = window.matchMedia(query);
    const handler = (e: MediaQueryListEvent) => setMatches(e.matches);
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, [query]);

  return matches;
}


function useOnClickOutside(
  ref: React.RefObject<HTMLElement>,
  handler: () => void,
) {
  useEffect(() => {
    const listener = (event: MouseEvent | TouchEvent) => {
      if (!ref.current || ref.current.contains(event.target as Node)) {
        return;
      }
      handler();
    };

    document.addEventListener('mousedown', listener);
    document.addEventListener('touchstart', listener);
    return () => {
      document.removeEventListener('mousedown', listener);
      document.removeEventListener('touchstart', listener);
    };
  }, [ref, handler]);
}


function usePrevious<T>(value: T): T | undefined {
  const ref = useRef<T>();
  useEffect(() => {
    ref.current = value;
  }, [value]);
  return ref.current;
}


// --- useIntersectionObserver (lazy loading) ---

function useIntersectionObserver(
  options?: IntersectionObserverInit,
): [React.RefObject<HTMLElement>, boolean] {
  const ref = useRef<HTMLElement>(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    const observer = new IntersectionObserver(
      ([entry]) => setIsVisible(entry.isIntersecting),
      options,
    );

    observer.observe(element);
    return () => observer.disconnect();
  }, [options]);

  return [ref, isVisible];
}


// --- useFetch with abort ---

function useFetch<T>(url: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
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
        if (err.name !== 'AbortError') setError(err);
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  }, [url]);

  return { data, error, loading };
}


// Usage:
// const { data: users, loading } = useFetch<User[]>('/api/users');
// const isMobile = useMediaQuery('(max-width: 768px)');
// const [theme, setTheme] = useLocalStorage('theme', 'light');
```

React hook patterns:
1. **`useReducer`** — complex state with typed actions (like mini-Redux)
2. **`useDebounce`** — delay value updates for search input
3. **`useLocalStorage`** — persist state to localStorage with lazy init
4. **`useIntersectionObserver`** — detect element visibility for lazy loading
5. **AbortController cleanup** — cancel in-flight fetch on unmount'''
    ),
    (
        "frontend/react-state",
        "Show React state management patterns: Context, Zustand, and server state with TanStack Query.",
        '''React state management patterns:

```typescript
// --- Context + useReducer (built-in) ---

import { createContext, useContext, useReducer, type ReactNode } from 'react';

interface AuthState {
  user: User | null;
  token: string | null;
  loading: boolean;
}

type AuthAction =
  | { type: 'LOGIN'; user: User; token: string }
  | { type: 'LOGOUT' }
  | { type: 'SET_LOADING'; loading: boolean };

const AuthContext = createContext<{
  state: AuthState;
  dispatch: React.Dispatch<AuthAction>;
} | null>(null);

function authReducer(state: AuthState, action: AuthAction): AuthState {
  switch (action.type) {
    case 'LOGIN':
      return { user: action.user, token: action.token, loading: false };
    case 'LOGOUT':
      return { user: null, token: null, loading: false };
    case 'SET_LOADING':
      return { ...state, loading: action.loading };
  }
}

function AuthProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(authReducer, {
    user: null, token: null, loading: true,
  });

  return (
    <AuthContext.Provider value={{ state, dispatch }}>
      {children}
    </AuthContext.Provider>
  );
}

function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be inside AuthProvider');
  return ctx;
}


// --- Zustand (lightweight store) ---

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface CartStore {
  items: CartItem[];
  addItem: (item: CartItem) => void;
  removeItem: (id: string) => void;
  updateQuantity: (id: string, qty: number) => void;
  clear: () => void;
  total: () => number;
}

const useCartStore = create<CartStore>()(
  persist(
    (set, get) => ({
      items: [],

      addItem: (item) => set((state) => {
        const existing = state.items.find(i => i.id === item.id);
        if (existing) {
          return {
            items: state.items.map(i =>
              i.id === item.id
                ? { ...i, quantity: i.quantity + item.quantity }
                : i
            ),
          };
        }
        return { items: [...state.items, item] };
      }),

      removeItem: (id) => set((state) => ({
        items: state.items.filter(i => i.id !== id),
      })),

      updateQuantity: (id, qty) => set((state) => ({
        items: state.items.map(i =>
          i.id === id ? { ...i, quantity: qty } : i
        ),
      })),

      clear: () => set({ items: [] }),

      total: () => get().items.reduce(
        (sum, item) => sum + item.price * item.quantity, 0
      ),
    }),
    { name: 'cart-storage' }, // Persist to localStorage
  )
);

// Usage:
// const { items, addItem, total } = useCartStore();
// const itemCount = useCartStore(state => state.items.length); // Selector


// --- TanStack Query (server state) ---

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

function useUsers(search?: string) {
  return useQuery({
    queryKey: ['users', { search }],
    queryFn: () => fetch(`/api/users?q=${search || ''}`).then(r => r.json()),
    staleTime: 60_000,         // Consider fresh for 60s
    gcTime: 300_000,           // Keep in cache for 5 min
    placeholderData: (prev) => prev, // Keep old data while refetching
  });
}

function useCreateUser() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateUserInput) =>
      fetch('/api/users', {
        method: 'POST',
        body: JSON.stringify(data),
        headers: { 'Content-Type': 'application/json' },
      }).then(r => r.json()),

    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });
}

function UserList() {
  const [search, setSearch] = useState('');
  const { data: users, isLoading, error } = useUsers(search);
  const createUser = useCreateUser();

  if (isLoading) return <Spinner />;
  if (error) return <Error message={error.message} />;

  return (
    <div>
      <input value={search} onChange={e => setSearch(e.target.value)} />
      {users.map((user: User) => (
        <UserCard key={user.id} user={user} />
      ))}
      <button
        onClick={() => createUser.mutate({ name: 'New User', email: '...' })}
        disabled={createUser.isPending}
      >
        {createUser.isPending ? 'Creating...' : 'Add User'}
      </button>
    </div>
  );
}
```

State management patterns:
1. **Context + useReducer** — built-in, good for auth/theme (low-frequency updates)
2. **Zustand** — minimal boilerplate, selector-based re-rendering, middleware
3. **`persist` middleware** — auto-save/restore state to localStorage
4. **TanStack Query** — server state with caching, refetching, and optimistic updates
5. **`queryKey` arrays** — cache keys enable granular invalidation'''
    ),
    (
        "frontend/react-component-patterns",
        "Show React component patterns: compound components, render props, HOCs, and error boundaries.",
        '''React component patterns:

```typescript
import {
  createContext, useContext, useState, useCallback, type ReactNode,
  Component, type ErrorInfo,
} from 'react';


// --- Compound components ---

interface TabsContextType {
  activeTab: string;
  setActiveTab: (id: string) => void;
}

const TabsContext = createContext<TabsContextType | null>(null);

function Tabs({ defaultTab, children }: {
  defaultTab: string;
  children: ReactNode;
}) {
  const [activeTab, setActiveTab] = useState(defaultTab);
  return (
    <TabsContext.Provider value={{ activeTab, setActiveTab }}>
      <div className="tabs">{children}</div>
    </TabsContext.Provider>
  );
}

function TabList({ children }: { children: ReactNode }) {
  return <div className="tab-list" role="tablist">{children}</div>;
}

function Tab({ id, children }: { id: string; children: ReactNode }) {
  const ctx = useContext(TabsContext)!;
  return (
    <button
      role="tab"
      aria-selected={ctx.activeTab === id}
      onClick={() => ctx.setActiveTab(id)}
      className={ctx.activeTab === id ? 'active' : ''}
    >
      {children}
    </button>
  );
}

function TabPanel({ id, children }: { id: string; children: ReactNode }) {
  const ctx = useContext(TabsContext)!;
  if (ctx.activeTab !== id) return null;
  return <div role="tabpanel">{children}</div>;
}

// Attach sub-components
Tabs.List = TabList;
Tabs.Tab = Tab;
Tabs.Panel = TabPanel;

// Usage:
// <Tabs defaultTab="profile">
//   <Tabs.List>
//     <Tabs.Tab id="profile">Profile</Tabs.Tab>
//     <Tabs.Tab id="settings">Settings</Tabs.Tab>
//   </Tabs.List>
//   <Tabs.Panel id="profile"><ProfileForm /></Tabs.Panel>
//   <Tabs.Panel id="settings"><SettingsForm /></Tabs.Panel>
// </Tabs>


// --- Render prop / children as function ---

interface AsyncDataProps<T> {
  url: string;
  children: (state: {
    data: T | null;
    loading: boolean;
    error: Error | null;
    refetch: () => void;
  }) => ReactNode;
}

function AsyncData<T>({ url, children }: AsyncDataProps<T>) {
  const { data, error, loading, refetch } = useFetch<T>(url);
  return <>{children({ data, loading, error, refetch })}</>;
}

// Usage:
// <AsyncData<User[]> url="/api/users">
//   {({ data, loading }) =>
//     loading ? <Spinner /> : data?.map(u => <div>{u.name}</div>)
//   }
// </AsyncData>


// --- Error Boundary ---

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

  reset = () => {
    this.setState({ error: null });
  };

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
//   onError={(error) => reportError(error)}
// >
//   <App />
// </ErrorBoundary>


// --- Polymorphic component (as prop) ---

type BoxProps<C extends React.ElementType> = {
  as?: C;
  children?: ReactNode;
} & React.ComponentPropsWithoutRef<C>;

function Box<C extends React.ElementType = 'div'>({
  as, children, ...props
}: BoxProps<C>) {
  const Component = as || 'div';
  return <Component {...props}>{children}</Component>;
}

// <Box as="section" className="hero">...</Box>
// <Box as="a" href="/home">Home</Box>
// <Box as={Link} to="/about">About</Box>
```

React component patterns:
1. **Compound components** — `Tabs.Tab` + `Tabs.Panel` share state via Context
2. **Render props** — `children` as function for flexible rendering
3. **Error Boundary** — catch render errors, show fallback with reset
4. **Polymorphic `as` prop** — render as any HTML element or component
5. **Context isolation** — compound component state hidden from consumers'''
    ),
]
"""
