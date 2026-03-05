"""Micro-frontends — Module Federation, single-spa."""

PAIRS = [
    (
        "frontend/webpack-module-federation",
        "Demonstrate Webpack Module Federation for micro-frontends including remote module loading, shared dependencies, and dynamic federation.",
        '''Webpack Module Federation allows multiple independently-deployed applications to share code at runtime, enabling micro-frontend architectures where each team owns and deploys their feature independently.

```typescript
// --- Host (shell) application configuration ---

// webpack.config.js (host/shell)
const { ModuleFederationPlugin } = require('webpack').container;

module.exports = {
  entry: './src/index.tsx',
  output: {
    publicPath: 'auto',
    uniqueName: 'shell',
  },
  plugins: [
    new ModuleFederationPlugin({
      name: 'shell',
      remotes: {
        // Remote apps loaded at runtime
        // Format: "internalName@remoteURL/remoteEntry.js"
        catalog: 'catalog@https://catalog.example.com/remoteEntry.js',
        checkout: 'checkout@https://checkout.example.com/remoteEntry.js',
        account: 'account@https://account.example.com/remoteEntry.js',
      },
      shared: {
        // Dependencies shared between host and remotes
        react: {
          singleton: true,         // only one instance
          requiredVersion: '^19.0.0',
          eager: true,             // loaded immediately (shell)
        },
        'react-dom': {
          singleton: true,
          requiredVersion: '^19.0.0',
          eager: true,
        },
        'react-router-dom': {
          singleton: true,
          requiredVersion: '^7.0.0',
        },
        // Shared state library
        zustand: {
          singleton: true,
          requiredVersion: '^5.0.0',
        },
      },
    }),
  ],
};


// --- Remote application configuration ---

// webpack.config.js (catalog remote)
module.exports = {
  entry: './src/index.tsx',
  output: {
    publicPath: 'auto',
    uniqueName: 'catalog',
  },
  plugins: [
    new ModuleFederationPlugin({
      name: 'catalog',
      filename: 'remoteEntry.js',  // entry point for the host
      exposes: {
        // Components/modules this remote makes available
        './ProductList': './src/components/ProductList',
        './ProductDetail': './src/pages/ProductDetail',
        './SearchBar': './src/components/SearchBar',
        './catalogStore': './src/store/catalogStore',
      },
      shared: {
        react: { singleton: true, requiredVersion: '^19.0.0' },
        'react-dom': { singleton: true, requiredVersion: '^19.0.0' },
        'react-router-dom': { singleton: true, requiredVersion: '^7.0.0' },
        zustand: { singleton: true, requiredVersion: '^5.0.0' },
      },
    }),
  ],
};
```

```typescript
// --- Loading remote components in the host ---

// src/remotes.d.ts — type declarations for remote modules
declare module 'catalog/ProductList' {
  import type { FC } from 'react';
  interface ProductListProps {
    category?: string;
    onProductClick: (id: string) => void;
  }
  const ProductList: FC<ProductListProps>;
  export default ProductList;
}

declare module 'catalog/ProductDetail' {
  import type { FC } from 'react';
  interface ProductDetailProps {
    productId: string;
  }
  const ProductDetail: FC<ProductDetailProps>;
  export default ProductDetail;
}

declare module 'checkout/Cart' {
  import type { FC } from 'react';
  const Cart: FC;
  export default Cart;
}

declare module 'account/UserProfile' {
  import type { FC } from 'react';
  const UserProfile: FC;
  export default UserProfile;
}


// src/App.tsx — lazy-loading remote components
import React, { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ErrorBoundary } from 'react-error-boundary';

// Lazy-load remote components
const ProductList = lazy(() => import('catalog/ProductList'));
const ProductDetail = lazy(() => import('catalog/ProductDetail'));
const Cart = lazy(() => import('checkout/Cart'));
const UserProfile = lazy(() => import('account/UserProfile'));

function RemoteWrapper({
  children,
  fallback,
  name,
}: {
  children: React.ReactNode;
  fallback?: React.ReactNode;
  name: string;
}) {
  return (
    <ErrorBoundary
      fallback={
        fallback ?? (
          <div className="remote-error">
            <p>Failed to load {name} module.</p>
            <button onClick={() => window.location.reload()}>Retry</button>
          </div>
        )
      }
    >
      <Suspense fallback={<ModuleSkeleton name={name} />}>
        {children}
      </Suspense>
    </ErrorBoundary>
  );
}

function App() {
  return (
    <BrowserRouter>
      <Shell>
        <Routes>
          <Route
            path="/"
            element={
              <RemoteWrapper name="Catalog">
                <ProductList onProductClick={(id) => navigate(`/product/${id}`)} />
              </RemoteWrapper>
            }
          />
          <Route
            path="/product/:id"
            element={
              <RemoteWrapper name="Product Detail">
                <ProductDetail productId={useParams().id!} />
              </RemoteWrapper>
            }
          />
          <Route
            path="/cart"
            element={
              <RemoteWrapper name="Cart">
                <Cart />
              </RemoteWrapper>
            }
          />
          <Route
            path="/account"
            element={
              <RemoteWrapper name="Account">
                <UserProfile />
              </RemoteWrapper>
            }
          />
        </Routes>
      </Shell>
    </BrowserRouter>
  );
}
```

```typescript
// --- Dynamic Module Federation (runtime discovery) ---

// Instead of hardcoding remote URLs in webpack config,
// load them dynamically at runtime

interface RemoteConfig {
  name: string;
  url: string;
  scope: string;
  module: string;
}

// Fetch remote configuration from a service registry
async function getRemoteConfig(): Promise<RemoteConfig[]> {
  const response = await fetch('/api/micro-frontends/registry');
  return response.json();
}

// Dynamic remote loading
async function loadRemoteModule(
  url: string,
  scope: string,
  module: string,
): Promise<any> {
  // Load the remote entry script
  await new Promise<void>((resolve, reject) => {
    const script = document.createElement('script');
    script.src = url;
    script.type = 'text/javascript';
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error(`Failed to load remote: ${url}`));
    document.head.appendChild(script);
  });

  // Initialize the shared scope
  await __webpack_init_sharing__('default');
  const container = (window as any)[scope];
  await container.init(__webpack_share_scopes__.default);

  // Get the module factory
  const factory = await container.get(module);
  return factory();
}


// Dynamic remote component loader
function useDynamicRemote(config: RemoteConfig) {
  const [Component, setComponent] = useState<React.ComponentType | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    loadRemoteModule(config.url, config.scope, config.module)
      .then(module => {
        if (!cancelled) {
          setComponent(() => module.default || module);
          setLoading(false);
        }
      })
      .catch(err => {
        if (!cancelled) {
          setError(err);
          setLoading(false);
        }
      });

    return () => { cancelled = true; };
  }, [config.url, config.scope, config.module]);

  return { Component, error, loading };
}

// Usage
function DynamicMicrofrontend({ config }: { config: RemoteConfig }) {
  const { Component, error, loading } = useDynamicRemote(config);

  if (loading) return <ModuleSkeleton name={config.name} />;
  if (error) return <ModuleError name={config.name} error={error} />;
  if (!Component) return null;

  return <Component />;
}


// --- Vite equivalent: Module Federation via vite-plugin ---

// vite.config.ts
/*
import { defineConfig } from 'vite';
import federation from '@originjs/vite-plugin-federation';

export default defineConfig({
  plugins: [
    federation({
      name: 'shell',
      remotes: {
        catalog: 'https://catalog.example.com/assets/remoteEntry.js',
      },
      shared: ['react', 'react-dom'],
    }),
  ],
});
*/
```

| Configuration | Shell (Host) | Remote (Feature) |
|---|---|---|
| `name` | Application identifier | Application identifier |
| `remotes` | URLs to remote entry points | Not needed |
| `exposes` | Not needed | Modules available to host |
| `filename` | Not needed | `remoteEntry.js` |
| `shared` | Shared dependencies | Same shared dependencies |
| `singleton` | One instance per app | Must match host setting |
| `eager` | Load immediately (shell) | Load on demand |

| Sharing Mode | Behavior | Use Case |
|---|---|---|
| `singleton: true` | Only one version loaded globally | React, state libraries |
| `eager: true` | Included in initial bundle | Shell-critical libraries |
| `requiredVersion` | Version constraint | Prevent incompatible versions |
| `strictVersion: true` | Error if version mismatch | Critical shared dependencies |
| `shareScope` | Separate share scope | Multiple apps with different React versions |

Key patterns:
1. Shell app defines `remotes`; feature apps define `exposes` and `filename`
2. `singleton: true` for React ensures one React instance (avoids hooks crash)
3. Wrap remote components in `ErrorBoundary` + `Suspense` for resilience
4. Dynamic federation loads remote configs from a service registry at runtime
5. Type declarations (`declare module`) provide type safety for remote imports
6. `eager: true` in the shell for critical shared deps; lazy in remotes
7. Each remote deploys independently — only `remoteEntry.js` URL must be stable'''
    ),
    (
        "frontend/single-spa-orchestration",
        "Demonstrate single-spa for micro-frontend orchestration including application registration, routing, shared state, and framework-agnostic composition.",
        '''single-spa is a framework for orchestrating multiple micro-frontends (even different frameworks) in a single page application, managing their lifecycle (bootstrap, mount, unmount) based on routing.

```typescript
// --- Root config (orchestrator) ---

// src/root-config.ts
import { registerApplication, start, LifeCycles } from 'single-spa';

// Register micro-frontends with route-based activation

// React micro-frontend
registerApplication({
  name: '@acme/navbar',
  app: () => System.import<LifeCycles>('@acme/navbar'),
  activeWhen: ['/'],  // always active (layout component)
  customProps: {
    authToken: () => getAuthToken(),
  },
});

// React micro-frontend
registerApplication({
  name: '@acme/dashboard',
  app: () => System.import<LifeCycles>('@acme/dashboard'),
  activeWhen: ['/dashboard'],
});

// Vue micro-frontend
registerApplication({
  name: '@acme/settings',
  app: () => System.import<LifeCycles>('@acme/settings'),
  activeWhen: ['/settings'],
});

// Angular micro-frontend
registerApplication({
  name: '@acme/analytics',
  app: () => System.import<LifeCycles>('@acme/analytics'),
  activeWhen: (location) => location.pathname.startsWith('/analytics'),
});

// Advanced: activity function with auth check
registerApplication({
  name: '@acme/admin',
  app: () => System.import<LifeCycles>('@acme/admin'),
  activeWhen: (location) => {
    return location.pathname.startsWith('/admin') && isUserAdmin();
  },
});

// Start single-spa after all applications are registered
start({
  urlRerouteOnly: true,  // only trigger on URL changes
});
```

```typescript
// --- React micro-frontend lifecycle ---

// packages/dashboard/src/root.component.tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import singleSpaReact from 'single-spa-react';
import { DashboardApp } from './DashboardApp';

// Wrap the React app with single-spa lifecycle hooks
const lifecycles = singleSpaReact({
  React,
  ReactDOM,
  rootComponent: DashboardApp,
  // Mount into a specific DOM element
  domElementGetter: () => document.getElementById('dashboard-container')!,
  errorBoundary(err: Error, info: React.ErrorInfo, props: Record<string, unknown>) {
    return (
      <div className="mfe-error">
        <h2>Dashboard Error</h2>
        <p>{err.message}</p>
        <button onClick={() => window.location.reload()}>Reload</button>
      </div>
    );
  },
});

export const bootstrap = lifecycles.bootstrap;
export const mount = lifecycles.mount;
export const unmount = lifecycles.unmount;


// packages/dashboard/src/DashboardApp.tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom';

interface DashboardAppProps {
  authToken?: () => string;
}

export function DashboardApp({ authToken }: DashboardAppProps) {
  return (
    <BrowserRouter basename="/dashboard">
      <Routes>
        <Route path="/" element={<DashboardHome />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/metrics" element={<Metrics />} />
      </Routes>
    </BrowserRouter>
  );
}


// --- Vue micro-frontend lifecycle ---

// packages/settings/src/main.ts
import { createApp, h, type App as VueApp } from 'vue';
import singleSpaVue from 'single-spa-vue';
import SettingsApp from './SettingsApp.vue';
import { createRouter, createWebHistory } from 'vue-router';
import { routes } from './routes';

const vueLifecycles = singleSpaVue({
  createApp,
  appOptions: {
    render() {
      return h(SettingsApp, {
        // Props from single-spa
      });
    },
  },
  handleInstance(app: VueApp) {
    // Add plugins
    const router = createRouter({
      history: createWebHistory('/settings'),
      routes,
    });
    app.use(router);
  },
});

export const bootstrap = vueLifecycles.bootstrap;
export const mount = vueLifecycles.mount;
export const unmount = vueLifecycles.unmount;
```

```typescript
// --- Import map and layout engine ---

// index.html — SystemJS import map
/*
<script type="systemjs-importmap">
{
  "imports": {
    "@acme/root-config": "https://shell.example.com/root-config.js",
    "@acme/navbar": "https://navbar.example.com/main.js",
    "@acme/dashboard": "https://dashboard.example.com/main.js",
    "@acme/settings": "https://settings.example.com/main.js",
    "@acme/analytics": "https://analytics.example.com/main.js",
    "@acme/admin": "https://admin.example.com/main.js",
    "react": "https://cdn.jsdelivr.net/npm/react@19/umd/react.production.min.js",
    "react-dom": "https://cdn.jsdelivr.net/npm/react-dom@19/umd/react-dom.production.min.js"
  }
}
</script>
*/


// --- Layout engine (single-spa-layout) ---

// Declarative layout definition
/*
<single-spa-router>
  <nav>
    <application name="@acme/navbar" />
  </nav>
  <main>
    <route path="dashboard">
      <application name="@acme/dashboard" />
    </route>
    <route path="settings">
      <application name="@acme/settings" />
    </route>
    <route path="analytics">
      <application name="@acme/analytics" />
    </route>
    <route default>
      <h1>404 - Page Not Found</h1>
    </route>
  </main>
  <footer>
    <p>© 2025 Acme Corp</p>
  </footer>
</single-spa-router>
*/

import { constructRoutes, constructApplications, constructLayoutEngine } from 'single-spa-layout';

// Construct routes from the HTML template
const routes = constructRoutes(document.querySelector('#single-spa-layout')!);
const applications = constructApplications({
  routes,
  loadApp: ({ name }) => System.import(name),
});

const layoutEngine = constructLayoutEngine({ routes, applications });

// Register all applications from the layout
applications.forEach(registerApplication);
layoutEngine.activate();
start();


// --- Shared utility module pattern ---

// packages/shared-utils/src/index.ts
// Shared as a SystemJS module, not embedded in each MFE

export function formatCurrency(amount: number, currency: string = 'USD'): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(amount);
}

export function formatDate(date: Date): string {
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(date);
}

export function getAuthToken(): string {
  return localStorage.getItem('auth_token') ?? '';
}

export function isUserAdmin(): boolean {
  try {
    const token = getAuthToken();
    if (!token) return false;
    const payload = JSON.parse(atob(token.split('.')[1]));
    return payload.role === 'admin';
  } catch {
    return false;
  }
}
```

| Feature | single-spa | Module Federation | iframes |
|---|---|---|---|
| Framework mixing | Yes (React + Vue + Angular) | Yes (any) | Yes (isolation) |
| Shared dependencies | SystemJS import map | webpack shared config | None (full isolation) |
| Routing | Activity functions | Host router | postMessage |
| Communication | Custom events, shared state | Shared modules | postMessage only |
| CSS isolation | Manual (CSS modules, shadow DOM) | Manual | Complete (iframe boundary) |
| Bundle size overhead | ~5 KB (single-spa core) | Webpack runtime | Browser native |
| Performance | Single page | Single page | Multiple page contexts |
| Deployment | Independent per MFE | Independent per MFE | Independent |
| Complexity | Medium-high | Medium | Low |

| Lifecycle Hook | When | Purpose |
|---|---|---|
| `bootstrap` | First time app is loaded | One-time initialization |
| `mount` | Route activates | Render the app into DOM |
| `unmount` | Route deactivates | Clean up, remove from DOM |
| `unload` (optional) | Manual trigger | Full cleanup (rare) |

Key patterns:
1. `registerApplication` with `activeWhen` ties micro-frontends to URL patterns
2. Each MFE exports `bootstrap`, `mount`, `unmount` lifecycle hooks
3. Use `single-spa-react`, `single-spa-vue`, etc. for framework-specific wrappers
4. Import maps (SystemJS or native) manage module URLs for independent deployment
5. Layout engine provides declarative HTML-based routing configuration
6. Shared utilities are deployed as separate modules referenced via import map
7. Wrap each MFE in an error boundary so one failure does not crash the entire shell'''
    ),
    (
        "frontend/microfrontend-communication",
        "Show micro-frontend communication patterns including custom events, shared state, and pub/sub messaging between independently deployed modules.",
        '''Micro-frontends need to communicate without tight coupling. The main patterns are custom events (loosely coupled), shared state stores (for coordinated state), and a pub/sub event bus.

```typescript
// --- Pattern 1: Custom Events (loosest coupling) ---

// events.ts — shared event type definitions (published as a shared package)
interface AppEvents {
  'cart:item-added': { productId: string; quantity: number; price: number };
  'cart:item-removed': { productId: string };
  'cart:cleared': undefined;
  'auth:login': { userId: string; token: string };
  'auth:logout': undefined;
  'navigation:navigate': { path: string; params?: Record<string, string> };
  'notification:show': { message: string; type: 'success' | 'error' | 'info' };
}

// Type-safe event emitter
function emitEvent<K extends keyof AppEvents>(
  type: K,
  detail: AppEvents[K],
): void {
  window.dispatchEvent(
    new CustomEvent(type, { detail, bubbles: true })
  );
}

function onEvent<K extends keyof AppEvents>(
  type: K,
  handler: (event: CustomEvent<AppEvents[K]>) => void,
): () => void {
  const listener = (e: Event) => handler(e as CustomEvent<AppEvents[K]>);
  window.addEventListener(type, listener);
  return () => window.removeEventListener(type, listener);
}


// --- Usage in Catalog MFE ---

function AddToCartButton({ product }: { product: Product }) {
  function handleAddToCart() {
    emitEvent('cart:item-added', {
      productId: product.id,
      quantity: 1,
      price: product.price,
    });

    emitEvent('notification:show', {
      message: `${product.name} added to cart`,
      type: 'success',
    });
  }

  return <button onClick={handleAddToCart}>Add to Cart</button>;
}


// --- Usage in Cart MFE (listening) ---

function CartWidget() {
  const [itemCount, setItemCount] = useState(0);

  useEffect(() => {
    const unsubAdd = onEvent('cart:item-added', (e) => {
      setItemCount(prev => prev + e.detail.quantity);
    });

    const unsubRemove = onEvent('cart:item-removed', () => {
      setItemCount(prev => Math.max(0, prev - 1));
    });

    const unsubClear = onEvent('cart:cleared', () => {
      setItemCount(0);
    });

    return () => {
      unsubAdd();
      unsubRemove();
      unsubClear();
    };
  }, []);

  return <span className="cart-badge">{itemCount}</span>;
}
```

```typescript
// --- Pattern 2: Shared State Store ---

// A shared Zustand store exposed as a SystemJS module
// or included in Module Federation's shared config

import { createStore, type StoreApi } from 'zustand/vanilla';

// shared-store/src/auth-store.ts
interface AuthState {
  user: { id: string; name: string; email: string; role: string } | null;
  token: string | null;
  isAuthenticated: boolean;
  login: (token: string, user: AuthState['user']) => void;
  logout: () => void;
  updateUser: (updates: Partial<NonNullable<AuthState['user']>>) => void;
}

// Vanilla Zustand store (works outside React)
export const authStore = createStore<AuthState>((set) => ({
  user: null,
  token: null,
  isAuthenticated: false,

  login: (token, user) => set({
    token,
    user,
    isAuthenticated: true,
  }),

  logout: () => {
    set({ token: null, user: null, isAuthenticated: false });
    localStorage.removeItem('auth_token');
  },

  updateUser: (updates) => set((state) => ({
    user: state.user ? { ...state.user, ...updates } : null,
  })),
}));


// shared-store/src/cart-store.ts
interface CartItem {
  productId: string;
  name: string;
  price: number;
  quantity: number;
}

interface CartState {
  items: CartItem[];
  totalItems: number;
  totalPrice: number;
  addItem: (item: Omit<CartItem, 'quantity'>) => void;
  removeItem: (productId: string) => void;
  updateQuantity: (productId: string, quantity: number) => void;
  clear: () => void;
}

export const cartStore = createStore<CartState>((set, get) => ({
  items: [],
  totalItems: 0,
  totalPrice: 0,

  addItem: (item) => set((state) => {
    const existing = state.items.find(i => i.productId === item.productId);
    let items: CartItem[];

    if (existing) {
      items = state.items.map(i =>
        i.productId === item.productId
          ? { ...i, quantity: i.quantity + 1 }
          : i
      );
    } else {
      items = [...state.items, { ...item, quantity: 1 }];
    }

    return {
      items,
      totalItems: items.reduce((sum, i) => sum + i.quantity, 0),
      totalPrice: items.reduce((sum, i) => sum + i.price * i.quantity, 0),
    };
  }),

  removeItem: (productId) => set((state) => {
    const items = state.items.filter(i => i.productId !== productId);
    return {
      items,
      totalItems: items.reduce((sum, i) => sum + i.quantity, 0),
      totalPrice: items.reduce((sum, i) => sum + i.price * i.quantity, 0),
    };
  }),

  updateQuantity: (productId, quantity) => set((state) => {
    const items = state.items.map(i =>
      i.productId === productId ? { ...i, quantity } : i
    );
    return {
      items,
      totalItems: items.reduce((sum, i) => sum + i.quantity, 0),
      totalPrice: items.reduce((sum, i) => sum + i.price * i.quantity, 0),
    };
  }),

  clear: () => set({ items: [], totalItems: 0, totalPrice: 0 }),
}));


// React hook for consuming shared stores in any MFE
import { useSyncExternalStore } from 'react';

function useStore<T, S>(
  store: StoreApi<T>,
  selector: (state: T) => S,
): S {
  return useSyncExternalStore(
    store.subscribe,
    () => selector(store.getState()),
    () => selector(store.getState()),
  );
}

// Usage in any MFE:
function CartIcon() {
  const totalItems = useStore(cartStore, (s) => s.totalItems);
  return <span>{totalItems}</span>;
}
```

```typescript
// --- Pattern 3: Pub/Sub Event Bus ---

// A typed publish/subscribe system for decoupled communication

type EventHandler<T = unknown> = (data: T) => void;

interface EventBus {
  publish: <K extends keyof AppEvents>(event: K, data: AppEvents[K]) => void;
  subscribe: <K extends keyof AppEvents>(
    event: K,
    handler: EventHandler<AppEvents[K]>,
  ) => () => void;
  subscribeOnce: <K extends keyof AppEvents>(
    event: K,
    handler: EventHandler<AppEvents[K]>,
  ) => () => void;
  clear: (event?: keyof AppEvents) => void;
}

function createEventBus(): EventBus {
  const handlers = new Map<string, Set<EventHandler>>();

  return {
    publish<K extends keyof AppEvents>(event: K, data: AppEvents[K]): void {
      const eventHandlers = handlers.get(event as string);
      if (eventHandlers) {
        eventHandlers.forEach(handler => {
          try {
            handler(data);
          } catch (error) {
            console.error(`Error in event handler for "${String(event)}":`, error);
          }
        });
      }
    },

    subscribe<K extends keyof AppEvents>(
      event: K,
      handler: EventHandler<AppEvents[K]>,
    ): () => void {
      if (!handlers.has(event as string)) {
        handlers.set(event as string, new Set());
      }
      handlers.get(event as string)!.add(handler as EventHandler);

      return () => {
        handlers.get(event as string)?.delete(handler as EventHandler);
      };
    },

    subscribeOnce<K extends keyof AppEvents>(
      event: K,
      handler: EventHandler<AppEvents[K]>,
    ): () => void {
      const wrapper: EventHandler<AppEvents[K]> = (data) => {
        handler(data);
        unsubscribe();
      };
      const unsubscribe = this.subscribe(event, wrapper);
      return unsubscribe;
    },

    clear(event?: keyof AppEvents): void {
      if (event) {
        handlers.delete(event as string);
      } else {
        handlers.clear();
      }
    },
  };
}

// Singleton event bus (shared via SystemJS or Module Federation)
export const eventBus = createEventBus();


// React hook for event bus
function useEventBus<K extends keyof AppEvents>(
  event: K,
  handler: EventHandler<AppEvents[K]>,
): void {
  useEffect(() => {
    const unsubscribe = eventBus.subscribe(event, handler);
    return unsubscribe;
  }, [event, handler]);
}

// Usage
function NotificationCenter() {
  const [notifications, setNotifications] = useState<
    Array<{ id: string; message: string; type: string }>
  >([]);

  useEventBus('notification:show', useCallback((data) => {
    setNotifications(prev => [
      ...prev,
      { id: crypto.randomUUID(), message: data.message, type: data.type },
    ]);
  }, []));

  return (
    <div className="notifications">
      {notifications.map(n => (
        <div key={n.id} className={`notification notification-${n.type}`}>
          {n.message}
        </div>
      ))}
    </div>
  );
}
```

| Pattern | Coupling | Complexity | Best For |
|---|---|---|---|
| Custom Events (DOM) | Very loose | Low | Simple notifications, fire-and-forget |
| Event Bus (pub/sub) | Loose | Low-Medium | Typed events across MFEs |
| Shared State Store | Medium | Medium | Coordinated state (cart, auth) |
| URL/Query Params | Loose | Low | Navigation-driven state |
| Shared Module (import) | Tight | Low | Utilities, formatters |
| postMessage (iframes) | Very loose | Medium | Iframe-based isolation |

| Decision | Recommendation |
|---|---|
| Auth state | Shared store (singleton, all MFEs need it) |
| Cart state | Shared store + events for notifications |
| Navigation | URL-based (react-router, single-spa routing) |
| Notifications | Event bus or custom events |
| Theme/locale | Shared store or CSS custom properties |
| Analytics tracking | Event bus (fire-and-forget) |
| Error reporting | Shared utility module |

Key patterns:
1. Custom DOM events are the loosest coupling: `window.dispatchEvent(new CustomEvent(...))`
2. Shared Zustand stores work across frameworks via `useSyncExternalStore`
3. Event bus provides typed pub/sub with automatic cleanup via `subscribe` return value
4. Prefer events for fire-and-forget notifications; shared state for coordinated data
5. Always wrap event handlers in try/catch to prevent one MFE from crashing others
6. React hooks (`useEventBus`, `useStore`) encapsulate subscription lifecycle
7. Define shared event types in a separate package consumed by all MFEs'''
    ),
    (
        "frontend/microfrontend-deployment",
        "Show deployment and versioning strategies for micro-frontends including independent deployment, version management, and rollback.",
        '''Micro-frontends are deployed independently, each with its own CI/CD pipeline. The key challenges are version coordination, rollback, and ensuring compatibility between the shell and remotes.

```typescript
// --- Independent deployment pipeline ---

// Each MFE has its own CI/CD pipeline that produces:
// 1. A versioned bundle (main.[hash].js)
// 2. A stable entry point (remoteEntry.js for Module Federation)
// 3. A manifest file with version metadata

// ci/deploy.ts — deployment script for a micro-frontend
interface DeployConfig {
  name: string;
  version: string;
  commitHash: string;
  environment: 'staging' | 'production';
  cdnBucket: string;
  registryUrl: string;
}

async function deployMicrofrontend(config: DeployConfig): Promise<void> {
  const { name, version, commitHash, environment, cdnBucket, registryUrl } = config;

  // 1. Build the application
  console.log(`Building ${name}@${version}...`);
  // execSync('npm run build');

  // 2. Upload to CDN with versioned path
  const cdnPath = `${name}/${version}`;
  const cdnUrl = `https://${cdnBucket}/${cdnPath}`;

  console.log(`Uploading to CDN: ${cdnUrl}`);
  // Upload dist/ contents to CDN

  // 3. Generate manifest
  const manifest: MFEManifest = {
    name,
    version,
    commitHash,
    deployedAt: new Date().toISOString(),
    entryUrl: `${cdnUrl}/remoteEntry.js`,
    integrity: await computeIntegrity(`dist/remoteEntry.js`),
    dependencies: {
      react: '^19.0.0',
      'react-dom': '^19.0.0',
    },
  };

  // 4. Register in the service registry
  console.log(`Registering in service registry...`);
  await fetch(`${registryUrl}/api/mfe/${name}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      environment,
      manifest,
    }),
  });

  // 5. Verify health check
  const healthResponse = await fetch(`${cdnUrl}/remoteEntry.js`, {
    method: 'HEAD',
  });

  if (!healthResponse.ok) {
    throw new Error(`Health check failed for ${name}@${version}`);
  }

  console.log(`Successfully deployed ${name}@${version} to ${environment}`);
}


// --- Manifest / service registry ---

interface MFEManifest {
  name: string;
  version: string;
  commitHash: string;
  deployedAt: string;
  entryUrl: string;
  integrity: string;
  dependencies: Record<string, string>;
}

interface ServiceRegistry {
  getManifest(name: string, env: string): Promise<MFEManifest>;
  getAllManifests(env: string): Promise<MFEManifest[]>;
  rollback(name: string, env: string, version: string): Promise<void>;
}

// Server-side registry endpoint
// GET  /api/mfe/:name?env=production -> MFEManifest
// GET  /api/mfe?env=production       -> MFEManifest[]
// PUT  /api/mfe/:name                -> register new version
// POST /api/mfe/:name/rollback       -> rollback to previous version
```

```typescript
// --- Dynamic import map generation ---

// The shell app fetches the service registry to build
// an import map at runtime

// shell/src/bootstrap.ts
async function generateImportMap(): Promise<void> {
  const registryUrl = process.env.REGISTRY_URL ?? '/api/mfe';
  const env = process.env.NODE_ENV === 'production' ? 'production' : 'staging';

  try {
    const response = await fetch(`${registryUrl}?env=${env}`);
    const manifests: MFEManifest[] = await response.json();

    const importMap = {
      imports: Object.fromEntries(
        manifests.map(m => [m.name, m.entryUrl])
      ),
    };

    // Inject the import map
    const script = document.createElement('script');
    script.type = 'importmap';
    script.textContent = JSON.stringify(importMap);
    document.head.appendChild(script);
  } catch (error) {
    console.error('Failed to load MFE registry, using fallback:', error);
    // Fallback to hardcoded import map
    useFallbackImportMap();
  }
}

// Call before single-spa/Module Federation bootstraps
await generateImportMap();


// --- Version compatibility checking ---

interface CompatibilityCheck {
  compatible: boolean;
  issues: string[];
}

function checkCompatibility(
  shellDeps: Record<string, string>,
  remoteDeps: Record<string, string>,
): CompatibilityCheck {
  const issues: string[] = [];

  for (const [dep, requiredRange] of Object.entries(remoteDeps)) {
    const shellVersion = shellDeps[dep];
    if (!shellVersion) {
      issues.push(`Missing shared dependency: ${dep}@${requiredRange}`);
      continue;
    }

    if (!semverSatisfies(shellVersion, requiredRange)) {
      issues.push(
        `Version mismatch for ${dep}: shell has ${shellVersion}, remote requires ${requiredRange}`
      );
    }
  }

  return {
    compatible: issues.length === 0,
    issues,
  };
}

// Check before loading a remote
async function safeLoadRemote(manifest: MFEManifest): Promise<void> {
  const shellDeps = getShellDependencyVersions();
  const compat = checkCompatibility(shellDeps, manifest.dependencies);

  if (!compat.compatible) {
    console.warn(`Compatibility issues with ${manifest.name}:`, compat.issues);
    // Decide: load anyway, skip, or load a fallback version
  }

  // Load with integrity check
  await loadScript(manifest.entryUrl, { integrity: manifest.integrity });
}
```

```typescript
// --- Rollback strategies ---

// 1. Instant rollback via service registry
async function rollbackMFE(
  name: string,
  targetVersion: string,
  env: string,
): Promise<void> {
  const registryUrl = process.env.REGISTRY_URL!;

  // Update registry to point to the previous version
  await fetch(`${registryUrl}/api/mfe/${name}/rollback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ version: targetVersion, environment: env }),
  });

  // The next page load will fetch the rolled-back version
  // For immediate effect on active users:
  await notifyActiveClients(name, targetVersion);
}

// 2. Notify active clients to reload the MFE
async function notifyActiveClients(name: string, version: string): Promise<void> {
  // Via WebSocket or Server-Sent Events
  // broadcast({ type: 'MFE_UPDATED', name, version })

  // Or via the service worker
  const registration = await navigator.serviceWorker.ready;
  registration.active?.postMessage({
    type: 'INVALIDATE_MFE',
    name,
    version,
  });
}


// 3. Canary deployments — gradual rollout
interface CanaryConfig {
  name: string;
  canaryVersion: string;
  stableVersion: string;
  canaryPercentage: number;  // 0-100
  canaryRules?: {
    userIds?: string[];
    regions?: string[];
    userAgents?: RegExp[];
  };
}

function resolveVersion(canary: CanaryConfig, userId: string): string {
  // Check specific user targeting
  if (canary.canaryRules?.userIds?.includes(userId)) {
    return canary.canaryVersion;
  }

  // Percentage-based rollout (consistent per user)
  const hash = simpleHash(userId + canary.name);
  const bucket = hash % 100;

  return bucket < canary.canaryPercentage
    ? canary.canaryVersion
    : canary.stableVersion;
}

function simpleHash(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;  // convert to 32-bit integer
  }
  return Math.abs(hash);
}


// --- CI/CD pipeline configuration ---

// .github/workflows/deploy-mfe.yml equivalent
const pipelineSteps = `
  1. Checkout code
  2. Install dependencies (npm ci)
  3. Run linting (npm run lint)
  4. Run unit tests (npm test)
  5. Build (npm run build)
  6. Run integration tests against staging shell
  7. Upload bundle to CDN (versioned path)
  8. Update service registry (staging)
  9. Run E2E tests against staging
  10. Promote to production (update registry)
  11. Monitor error rates for 15 minutes
  12. Auto-rollback if error rate > threshold
`;
```

| Strategy | Speed | Risk | Complexity |
|---|---|---|---|
| Blue-green (swap URL) | Instant | Low (full rollback) | Low |
| Canary (% rollout) | Gradual | Very low | Medium |
| Feature flags | Instant toggle | Low | Medium |
| Service registry swap | Instant | Low | Low |
| Import map update | Next page load | Low | Low |
| Full redeploy | Minutes | Medium | Low |

| Versioning Approach | Description | Use Case |
|---|---|---|
| Semantic versioning | Major.minor.patch | Breaking changes tracked |
| Git hash | Commit SHA as version | Continuous deployment |
| Timestamp | Deploy timestamp | Simple, always increasing |
| Feature branch | Branch name in URL | Preview deployments |
| Canary + stable | Two live versions | Gradual rollout |

Key patterns:
1. Each MFE deploys independently with its own CI/CD pipeline and CDN path
2. Service registry maps MFE names to their current entry point URLs
3. Dynamic import maps are generated at runtime from the service registry
4. Rollback is instant: update the registry to point to the previous version
5. Canary deployments gradually roll out new versions to a percentage of users
6. Version compatibility checks prevent loading MFEs with incompatible shared deps
7. Monitor error rates after deployment and auto-rollback if thresholds are exceeded'''
    ),

    # --- 5. Web Components for Micro-Frontend Isolation ---
    (
        "frontend/web-components-mfe-isolation",
        "Build a micro-frontend isolation layer using Web Components (Custom Elements + Shadow DOM) "
        "that enables independently developed micro-apps to coexist without CSS or JavaScript "
        "conflicts. Show how to wrap React, Vue, and vanilla micro-apps in web component shells "
        "with shared event communication.",
        """\
# Web Components for Micro-Frontend Isolation

## Why Web Components for Micro-Frontends?

```
Problem: Multiple teams ship micro-apps into one page.
  - Team A uses React 19 + Tailwind
  - Team B uses Vue 3 + Vuetify
  - Team C uses vanilla JS + custom CSS

Without isolation:
  - CSS leaks between micro-apps (global styles)
  - JS globals collide (window.X, event listeners)
  - React/Vue version conflicts

Web Components solve this:
  - Shadow DOM encapsulates CSS completely
  - Custom Elements provide a standard mount/unmount lifecycle
  - No framework dependency for the shell
  - Works with Module Federation, import maps, or any loader
```

## Base Micro-Frontend Shell

```typescript
// lib/mfe-shell.ts

// Generic shell that wraps any micro-frontend in a Custom Element
// with Shadow DOM isolation and lifecycle management.

interface MicroFrontendConfig {
  name: string;           // Custom element tag name (must have hyphen)
  mountFn: (container: HTMLElement, props: Record<string, any>) => void;
  unmountFn: (container: HTMLElement) => void;
  styles?: string;        // Scoped CSS to inject into shadow root
  attributes?: string[];  // Observed attributes that map to props
}

function registerMicroFrontend(config: MicroFrontendConfig) {
  const {
    name, mountFn, unmountFn, styles = "", attributes = [],
  } = config;

  class MFEElement extends HTMLElement {
    private mountPoint: HTMLDivElement | null = null;
    private shadow: ShadowRoot;
    private mounted = false;

    static get observedAttributes() {
      return attributes;
    }

    constructor() {
      super();
      this.shadow = this.attachShadow({ mode: "open" });
    }

    connectedCallback() {
      // Inject scoped styles
      if (styles) {
        const styleEl = document.createElement("style");
        styleEl.textContent = styles;
        this.shadow.appendChild(styleEl);
      }

      // Create mount point inside shadow DOM
      this.mountPoint = document.createElement("div");
      this.mountPoint.id = "mfe-root";
      this.shadow.appendChild(this.mountPoint);

      // Mount the micro-frontend
      mountFn(this.mountPoint, this.getProps());
      this.mounted = true;
    }

    disconnectedCallback() {
      if (this.mountPoint && this.mounted) {
        unmountFn(this.mountPoint);
        this.mounted = false;
      }
    }

    attributeChangedCallback(
      attr: string, _old: string | null, newVal: string | null
    ) {
      if (!this.mounted || !this.mountPoint) return;
      // Re-mount with updated props
      unmountFn(this.mountPoint);
      mountFn(this.mountPoint, this.getProps());
    }

    private getProps(): Record<string, any> {
      const props: Record<string, any> = {};
      for (const attr of attributes) {
        const val = this.getAttribute(attr);
        if (val !== null) {
          try { props[attr] = JSON.parse(val); }
          catch { props[attr] = val; }
        }
      }
      return props;
    }
  }

  customElements.define(name, MFEElement);
}

export { registerMicroFrontend };
export type { MicroFrontendConfig };
```

## Wrapping a React App

```tsx
// mfe-react-dashboard/register.ts
import { createRoot, type Root } from "react-dom/client";
import { registerMicroFrontend } from "../lib/mfe-shell";
import { Dashboard } from "./Dashboard";

let root: Root | null = null;

registerMicroFrontend({
  name: "mfe-dashboard",
  attributes: ["user-id", "theme"],

  mountFn(container, props) {
    root = createRoot(container);
    root.render(<Dashboard userId={props["user-id"]} theme={props.theme} />);
  },

  unmountFn() {
    root?.unmount();
    root = null;
  },

  styles: `
    :host {
      display: block;
      contain: layout style;
      font-family: system-ui, sans-serif;
    }
    /* These styles are scoped to this shadow root only */
    .dashboard { padding: 1rem; }
    .card { background: var(--mfe-card-bg, white); border-radius: 8px; }
  `,
});

// Usage in host page HTML:
// <mfe-dashboard user-id="123" theme="dark"></mfe-dashboard>
```

## Cross-MFE Event Communication

```typescript
// lib/mfe-event-bus.ts

// Typed event bus for micro-frontend communication.
// Uses CustomEvents on a shared DOM element (document.body)
// so it works across Shadow DOM boundaries.

type MFEEvents = {
  "cart:item-added": { productId: string; quantity: number };
  "cart:updated": { itemCount: number; total: number };
  "auth:login": { userId: string; token: string };
  "auth:logout": {};
  "nav:route-change": { path: string; params: Record<string, string> };
  "theme:change": { mode: "light" | "dark" | "system" };
};

class MFEEventBus {
  private target: EventTarget;

  constructor() {
    // Use a dedicated EventTarget (or document.body for broader compat)
    this.target =
      typeof EventTarget === "function"
        ? new EventTarget()
        : document.createElement("div");

    // Make globally accessible
    (window as any).__mfe_event_bus = this;
  }

  static getInstance(): MFEEventBus {
    if (!(window as any).__mfe_event_bus) {
      new MFEEventBus();
    }
    return (window as any).__mfe_event_bus;
  }

  emit<K extends keyof MFEEvents>(event: K, detail: MFEEvents[K]) {
    this.target.dispatchEvent(
      new CustomEvent(event, { detail, bubbles: false })
    );
  }

  on<K extends keyof MFEEvents>(
    event: K,
    handler: (detail: MFEEvents[K]) => void
  ): () => void {
    const listener = (e: Event) => {
      handler((e as CustomEvent).detail);
    };
    this.target.addEventListener(event, listener);
    return () => this.target.removeEventListener(event, listener);
  }
}

export { MFEEventBus };
export type { MFEEvents };
```

## Host Page: Composing Micro-Frontends

```html
<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
  <meta charset="UTF-8" />
  <title>Micro-Frontend Host</title>
  <style>
    /* Host-level layout only; MFE styles are encapsulated */
    .mfe-grid {
      display: grid;
      grid-template-columns: 250px 1fr;
      grid-template-rows: 60px 1fr;
      height: 100vh;
    }
    .mfe-header { grid-column: 1 / -1; }
    .mfe-sidebar { grid-row: 2; }
    .mfe-main { grid-row: 2; overflow-y: auto; }

    /* CSS custom properties pass through Shadow DOM */
    :root {
      --mfe-card-bg: #ffffff;
      --mfe-text-primary: #1a1a1a;
    }
    [data-theme="dark"] {
      --mfe-card-bg: #1e1e1e;
      --mfe-text-primary: #f0f0f0;
    }
  </style>
</head>
<body>
  <div class="mfe-grid">
    <header class="mfe-header">
      <mfe-nav theme="light"></mfe-nav>
    </header>
    <aside class="mfe-sidebar">
      <mfe-sidebar user-id="123"></mfe-sidebar>
    </aside>
    <main class="mfe-main">
      <mfe-dashboard user-id="123" theme="light"></mfe-dashboard>
    </main>
  </div>

  <!-- Load MFE bundles (could be from different CDNs/teams) -->
  <script type="module" src="https://cdn.team-a.com/mfe-nav/register.js"></script>
  <script type="module" src="https://cdn.team-b.com/mfe-sidebar/register.js"></script>
  <script type="module" src="https://cdn.team-c.com/mfe-dashboard/register.js"></script>
</body>
</html>
```

| Isolation Method | CSS Isolation | JS Isolation | Framework Agnostic | DX |
|---|---|---|---|---|
| Shadow DOM | Full (encapsulated) | Partial (shadow scope) | Yes | Good |
| iframe | Full (separate document) | Full (separate context) | Yes | Poor (sizing, comms) |
| CSS Modules / scoped | Naming only | None | Framework-specific | Good |
| Tailwind prefix | Naming only | None | Yes | Medium |

Key patterns:
1. Shadow DOM fully encapsulates CSS; no styles leak in or out of the micro-app
2. CSS custom properties (--mfe-*) pass through Shadow DOM for shared theming
3. Custom Elements provide standard mount/unmount lifecycle for any framework
4. The event bus uses CustomEvent for typed cross-MFE communication
5. `contain: layout style` on :host improves rendering performance
6. Observed attributes let the host page pass props via HTML attributes
7. Each MFE team ships an independent bundle with its own registerMicroFrontend call"""
    ),
]
