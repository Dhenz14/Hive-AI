"""State management — Zustand, Jotai, React Query, and state patterns."""

PAIRS = [
    (
        "react/zustand",
        "Show Zustand state management: stores, slices, middleware, and TypeScript patterns.",
        """Zustand state management:

```typescript
import { create } from 'zustand';
import { devtools, persist, subscribeWithSelector } from 'zustand/middleware';
import { immer } from 'zustand/middleware/immer';

// --- Basic store ---

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  updateProfile: (updates: Partial<User>) => void;
}

const useAuthStore = create<AuthState>()(
  devtools(
    persist(
      (set, get) => ({
        user: null,
        token: null,
        isAuthenticated: false,

        login: async (email, password) => {
          const res = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
          });
          if (!res.ok) throw new Error('Login failed');
          const data = await res.json();
          set({
            user: data.user,
            token: data.token,
            isAuthenticated: true,
          });
        },

        logout: () => set({
          user: null, token: null, isAuthenticated: false,
        }),

        updateProfile: (updates) => set((state) => ({
          user: state.user ? { ...state.user, ...updates } : null,
        })),
      }),
      { name: 'auth-storage', partialize: (state) => ({ token: state.token }) },
    ),
    { name: 'AuthStore' },
  ),
);


// --- Store with immer (mutable updates) ---

interface CartState {
  items: CartItem[];
  addItem: (product: Product) => void;
  removeItem: (productId: string) => void;
  updateQuantity: (productId: string, qty: number) => void;
  clear: () => void;
  totalItems: () => number;
  totalPrice: () => number;
}

const useCartStore = create<CartState>()(
  immer((set, get) => ({
    items: [],

    addItem: (product) => set((state) => {
      const existing = state.items.find(i => i.productId === product.id);
      if (existing) {
        existing.quantity += 1;  // Direct mutation with immer
      } else {
        state.items.push({
          productId: product.id,
          name: product.name,
          price: product.price,
          quantity: 1,
        });
      }
    }),

    removeItem: (productId) => set((state) => {
      state.items = state.items.filter(i => i.productId !== productId);
    }),

    updateQuantity: (productId, qty) => set((state) => {
      const item = state.items.find(i => i.productId === productId);
      if (item) {
        item.quantity = Math.max(0, qty);
        if (item.quantity === 0) {
          state.items = state.items.filter(i => i.productId !== productId);
        }
      }
    }),

    clear: () => set({ items: [] }),

    // Computed values (called as functions)
    totalItems: () => get().items.reduce((sum, i) => sum + i.quantity, 0),
    totalPrice: () => get().items.reduce((sum, i) => sum + i.price * i.quantity, 0),
  })),
);


// --- Slice pattern (for large stores) ---

interface UISlice {
  sidebarOpen: boolean;
  theme: 'light' | 'dark';
  toggleSidebar: () => void;
  setTheme: (theme: 'light' | 'dark') => void;
}

interface NotificationSlice {
  notifications: Notification[];
  addNotification: (msg: string, type: string) => void;
  dismiss: (id: string) => void;
}

type AppStore = UISlice & NotificationSlice;

const createUISlice = (set: any): UISlice => ({
  sidebarOpen: true,
  theme: 'light',
  toggleSidebar: () => set((s: UISlice) => ({ sidebarOpen: !s.sidebarOpen })),
  setTheme: (theme) => set({ theme }),
});

const createNotificationSlice = (set: any): NotificationSlice => ({
  notifications: [],
  addNotification: (msg, type) => set((s: NotificationSlice) => ({
    notifications: [...s.notifications, {
      id: crypto.randomUUID(), message: msg, type, timestamp: Date.now(),
    }],
  })),
  dismiss: (id) => set((s: NotificationSlice) => ({
    notifications: s.notifications.filter(n => n.id !== id),
  })),
});

const useAppStore = create<AppStore>()((...args) => ({
  ...createUISlice(...args),
  ...createNotificationSlice(...args),
}));


// --- Usage in components ---

// Select specific state (prevents re-renders from unrelated changes)
function CartBadge() {
  const itemCount = useCartStore(state => state.totalItems());
  return <span className="badge">{itemCount}</span>;
}

function Header() {
  const { user, logout } = useAuthStore();
  const { sidebarOpen, toggleSidebar } = useAppStore();
  // ...
}

// Subscribe outside React
const unsub = useCartStore.subscribe(
  (state) => state.items.length,
  (count) => console.log('Cart items:', count),
);
```

Zustand patterns:
1. **Selectors** — `useStore(state => state.field)` prevents unnecessary re-renders
2. **Immer middleware** — write "mutable" updates that produce immutable state
3. **Persist middleware** — auto-save to localStorage
4. **Slice pattern** — split large stores into composable pieces
5. **Subscribe outside React** — react to state changes in non-component code"""
    ),
    (
        "react/react-query",
        "Show React Query (TanStack Query) patterns: queries, mutations, optimistic updates, and infinite scroll.",
        """TanStack Query (React Query) patterns:

```tsx
import {
  useQuery, useMutation, useInfiniteQuery,
  useQueryClient, QueryClient, QueryClientProvider,
} from '@tanstack/react-query';

// --- Query client setup ---

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,   // 5 minutes
      gcTime: 10 * 60 * 1000,     // 10 minutes (was cacheTime)
      retry: 2,
      refetchOnWindowFocus: false,
    },
  },
});


// --- Basic query ---

function useUser(userId: string) {
  return useQuery({
    queryKey: ['user', userId],
    queryFn: async () => {
      const res = await fetch(`/api/users/${userId}`);
      if (!res.ok) throw new Error('User not found');
      return res.json() as Promise<User>;
    },
    enabled: !!userId,  // Don't fetch if no userId
  });
}

function UserProfile({ userId }: { userId: string }) {
  const { data: user, isLoading, error } = useUser(userId);

  if (isLoading) return <Skeleton />;
  if (error) return <ErrorMessage error={error} />;
  return <div>{user.name}</div>;
}


// --- Dependent queries ---

function useUserOrders(userId: string) {
  const { data: user } = useUser(userId);

  return useQuery({
    queryKey: ['orders', userId],
    queryFn: () => fetchOrders(userId),
    enabled: !!user,  // Only fetch after user is loaded
  });
}


// --- Mutation with optimistic update ---

function useUpdateUser() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ userId, updates }: {
      userId: string; updates: Partial<User>;
    }) => {
      const res = await fetch(`/api/users/${userId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
      });
      if (!res.ok) throw new Error('Update failed');
      return res.json();
    },

    // Optimistic update
    onMutate: async ({ userId, updates }) => {
      await queryClient.cancelQueries({ queryKey: ['user', userId] });
      const previous = queryClient.getQueryData(['user', userId]);
      queryClient.setQueryData(['user', userId], (old: User) => ({
        ...old, ...updates,
      }));
      return { previous };
    },

    onError: (err, variables, context) => {
      // Rollback on error
      queryClient.setQueryData(
        ['user', variables.userId],
        context?.previous,
      );
    },

    onSettled: (data, error, { userId }) => {
      // Always refetch to ensure consistency
      queryClient.invalidateQueries({ queryKey: ['user', userId] });
    },
  });
}


// --- Infinite scroll ---

function useInfiniteProducts(category: string) {
  return useInfiniteQuery({
    queryKey: ['products', category],
    queryFn: async ({ pageParam }) => {
      const res = await fetch(
        `/api/products?category=${category}&cursor=${pageParam || ''}&limit=20`
      );
      return res.json() as Promise<{
        items: Product[];
        nextCursor: string | null;
      }>;
    },
    initialPageParam: '',
    getNextPageParam: (lastPage) => lastPage.nextCursor,
  });
}

function ProductInfiniteList({ category }: { category: string }) {
  const {
    data, fetchNextPage, hasNextPage, isFetchingNextPage,
  } = useInfiniteProducts(category);

  const products = data?.pages.flatMap(page => page.items) ?? [];

  return (
    <div>
      {products.map(product => (
        <ProductCard key={product.id} product={product} />
      ))}
      {hasNextPage && (
        <button
          onClick={() => fetchNextPage()}
          disabled={isFetchingNextPage}
        >
          {isFetchingNextPage ? 'Loading...' : 'Load More'}
        </button>
      )}
    </div>
  );
}


// --- Prefetching ---

function ProductLink({ product }: { product: Product }) {
  const queryClient = useQueryClient();

  return (
    <Link
      href={`/products/${product.id}`}
      onMouseEnter={() => {
        // Prefetch on hover
        queryClient.prefetchQuery({
          queryKey: ['product', product.id],
          queryFn: () => fetchProduct(product.id),
          staleTime: 60_000,
        });
      }}
    >
      {product.name}
    </Link>
  );
}
```

React Query patterns:
1. **Query keys** — `['entity', id, filters]` for automatic cache management
2. **Optimistic updates** — update UI immediately, rollback on error
3. **`enabled`** — conditional/dependent queries
4. **Infinite queries** — cursor-based pagination with `getNextPageParam`
5. **Prefetch on hover** — load data before user clicks for instant navigation"""
    ),
]
