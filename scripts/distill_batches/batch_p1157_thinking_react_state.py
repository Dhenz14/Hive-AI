"""
Frontend thinking pairs - React state management decisions
"""

pairs = [
    {
        "instruction": r'''I have a shopping cart with items, quantities, discount codes, and shipping method. Should I use useState or useReducer?''',
        "output": r'''<think>
Let me think about this. The shopping cart has multiple related pieces of state: items (array), quantities (per item), discount codes (array or string), shipping method (enum). These all interact with each other -- applying a discount code might depend on which items are in the cart, changing shipping method affects the total which depends on items and discounts.

With useState, I would need multiple state variables:
- const [items, setItems] = useState([])
- const [discounts, setDiscounts] = useState([])
- const [shipping, setShipping] = useState('standard')

The problem: when I add an item, I might also need to recalculate whether a discount still applies (e.g., "10% off orders over $50"). With separate useState calls, I have to coordinate updates carefully and might end up with intermediate invalid states.

With useReducer, all the state lives in one object and all transitions are explicit actions. Adding an item dispatches ADD_ITEM, which the reducer can handle atomically -- updating items, recalculating totals, validating discounts, all in one state transition.

Hmm, wait, could I just use a single useState with an object? Like useState({ items: [], discounts: [], shipping: 'standard' }). That works for simple cases, but the update logic gets messy -- you end up with big inline functions in event handlers. useReducer is cleaner because the logic lives in the reducer function, not scattered across components.

I initially thought this was borderline and either would work, but actually the key signal is: do state transitions have BUSINESS LOGIC? Adding an item is not just "append to array" -- it might merge quantities if the item already exists, validate inventory, apply discount rules. That logic belongs in a reducer, not in onClick handlers.

The tradeoff is: useReducer has more boilerplate (action types, switch statement), but the logic is centralized, testable, and predictable. useState is less code but the logic scatters across the component.
</think>

useReducer is the right choice here. Your cart has interdependent state and business logic in the transitions -- that is exactly what reducers are designed for.

```tsx
import { useReducer, useMemo } from 'react';

// State shape
interface CartItem {
  id: string;
  name: string;
  price: number;
  quantity: number;
}

interface CartState {
  items: CartItem[];
  discountCode: string | null;
  discountPercent: number;
  shipping: 'standard' | 'express' | 'overnight';
}

// Actions -- each one is a complete state transition
type CartAction =
  | { type: 'ADD_ITEM'; item: Omit<CartItem, 'quantity'> }
  | { type: 'REMOVE_ITEM'; itemId: string }
  | { type: 'UPDATE_QUANTITY'; itemId: string; quantity: number }
  | { type: 'APPLY_DISCOUNT'; code: string }
  | { type: 'REMOVE_DISCOUNT' }
  | { type: 'SET_SHIPPING'; method: CartState['shipping'] }
  | { type: 'CLEAR_CART' };

const DISCOUNT_CODES: Record<string, number> = {
  SAVE10: 10,
  SAVE20: 20,
  HALF: 50,
};

const SHIPPING_COSTS = {
  standard: 0,
  express: 9.99,
  overnight: 24.99,
};

function cartReducer(state: CartState, action: CartAction): CartState {
  switch (action.type) {
    case 'ADD_ITEM': {
      const existing = state.items.find(i => i.id === action.item.id);
      if (existing) {
        // Merge: increment quantity instead of duplicating
        return {
          ...state,
          items: state.items.map(i =>
            i.id === action.item.id
              ? { ...i, quantity: i.quantity + 1 }
              : i
          ),
        };
      }
      return {
        ...state,
        items: [...state.items, { ...action.item, quantity: 1 }],
      };
    }
    case 'REMOVE_ITEM':
      return {
        ...state,
        items: state.items.filter(i => i.id !== action.itemId),
      };
    case 'UPDATE_QUANTITY': {
      if (action.quantity <= 0) {
        return {
          ...state,
          items: state.items.filter(i => i.id !== action.itemId),
        };
      }
      return {
        ...state,
        items: state.items.map(i =>
          i.id === action.itemId
            ? { ...i, quantity: action.quantity }
            : i
        ),
      };
    }
    case 'APPLY_DISCOUNT': {
      const percent = DISCOUNT_CODES[action.code.toUpperCase()];
      if (!percent) return state; // Invalid code, no change
      return {
        ...state,
        discountCode: action.code.toUpperCase(),
        discountPercent: percent,
      };
    }
    case 'REMOVE_DISCOUNT':
      return { ...state, discountCode: null, discountPercent: 0 };
    case 'SET_SHIPPING':
      return { ...state, shipping: action.method };
    case 'CLEAR_CART':
      return initialState;
    default:
      return state;
  }
}

const initialState: CartState = {
  items: [],
  discountCode: null,
  discountPercent: 0,
  shipping: 'standard',
};

// Usage in component
function useCart() {
  const [state, dispatch] = useReducer(cartReducer, initialState);

  const totals = useMemo(() => {
    const subtotal = state.items.reduce(
      (sum, item) => sum + item.price * item.quantity,
      0
    );
    const discount = subtotal * (state.discountPercent / 100);
    const shippingCost = SHIPPING_COSTS[state.shipping];
    const total = subtotal - discount + shippingCost;
    return { subtotal, discount, shippingCost, total };
  }, [state.items, state.discountPercent, state.shipping]);

  return { state, dispatch, totals };
}
```

Why useReducer wins here:
- **Atomic transitions**: ADD_ITEM handles "merge if exists" logic in one place instead of scattered across onClick handlers
- **Testable**: You can unit test `cartReducer` with plain objects -- no React needed
- **No invalid intermediate states**: Each dispatch produces a complete, valid next state
- **Self-documenting**: The action types describe exactly what can happen to the cart'''
    },
    {
        "instruction": r'''When should I reach for a state management library like Zustand or Redux instead of just using React context?''',
        "output": r'''<think>
This comes up constantly. Let me think about what Context actually is and where it falls short.

React Context is a dependency injection mechanism, not a state management solution. It broadcasts a value to all descendants. When that value changes, ALL consumers re-render. There is no way to subscribe to a slice of the context value.

So if I put { user, theme, notifications, cart } in a single context, changing the notification count re-renders every component that reads the user object. That is wasteful. You can split into multiple contexts, but that gets unwieldy fast.

Zustand (and Redux with selectors) solve this with selective subscriptions. A component can subscribe to just store.cart.itemCount, and it only re-renders when that specific value changes. This is fundamentally different from Context.

Hmm, but wait -- for most apps, does this performance difference actually matter? If your context value changes rarely (user login, theme toggle), the mass re-render is fine. The problem only shows up when state changes frequently (typing in a form, real-time data updates, drag-and-drop coordinates).

I initially thought "just use Zustand for everything" but that is over-engineering for simple cases. Context works great for:
- Authentication state (changes on login/logout -- very infrequent)
- Theme/locale settings (changes on user action -- infrequent)
- Feature flags (set once on app load)

Zustand/Redux is needed for:
- Shopping carts, form state, filters that update on every keystroke
- State shared across many unrelated components
- State that needs to be accessed outside React (in API interceptors, event handlers)
- Complex state transitions that benefit from middleware (logging, persistence)

The tradeoff is: Context is zero-dependency and built-in. Zustand is ~1KB but adds a dependency. Redux is larger but has DevTools, middleware, and a huge ecosystem.
</think>

Context works well for infrequently-changing global values. Reach for a library when state changes frequently or you need selective subscriptions.

**When Context is enough:**

```tsx
// Auth context -- changes on login/logout (rare)
const AuthContext = createContext<AuthState | null>(null);

function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);

  const login = async (credentials: Credentials) => {
    const user = await api.login(credentials);
    setUser(user);
  };

  const logout = () => setUser(null);

  return (
    <AuthContext.Provider value={{ user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
```

**When you need Zustand:**

```tsx
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

// Cart store -- updates frequently, many consumers,
// needs persistence, accessed outside React
interface CartStore {
  items: CartItem[];
  addItem: (product: Product) => void;
  removeItem: (id: string) => void;
  updateQuantity: (id: string, qty: number) => void;
  total: () => number;
}

const useCartStore = create<CartStore>()(
  persist(
    (set, get) => ({
      items: [],
      addItem: (product) =>
        set((state) => {
          const existing = state.items.find(i => i.id === product.id);
          if (existing) {
            return {
              items: state.items.map(i =>
                i.id === product.id
                  ? { ...i, quantity: i.quantity + 1 }
                  : i
              ),
            };
          }
          return {
            items: [...state.items, { ...product, quantity: 1 }],
          };
        }),
      removeItem: (id) =>
        set((state) => ({
          items: state.items.filter(i => i.id !== id),
        })),
      updateQuantity: (id, qty) =>
        set((state) => ({
          items: state.items.map(i =>
            i.id === id ? { ...i, quantity: qty } : i
          ),
        })),
      total: () =>
        get().items.reduce(
          (sum, i) => sum + i.price * i.quantity,
          0
        ),
    }),
    { name: 'cart-storage' } // Auto-persists to localStorage
  )
);

// Component only re-renders when itemCount changes,
// NOT when other cart state changes
function CartBadge() {
  const itemCount = useCartStore(
    (state) => state.items.length
  );
  return <span className="badge">{itemCount}</span>;
}

// Access cart outside React (e.g., in an API interceptor)
const currentItems = useCartStore.getState().items;
```

Decision checklist:
- State changes < once per minute? --> Context is fine
- State changes on every keystroke or frame? --> Use Zustand
- Only 1-2 consumers? --> Context or even prop drilling
- 10+ consumers across the tree? --> Zustand with selectors
- Need access outside React components? --> Zustand (Context only works inside the tree)
- Need middleware (logging, persistence, undo)? --> Zustand or Redux
- Team already knows Redux? --> Redux Toolkit is great, do not switch just because Zustand is trendy'''
    },
    {
        "instruction": r'''I have a form with 15 fields. Every keystroke causes the entire form to re-render. How do I handle this? Should I use controlled or uncontrolled inputs?''',
        "output": r'''<think>
15 fields re-rendering on every keystroke -- this is a classic form performance problem. Let me think through the options.

Controlled inputs: each input has value={state.field} and onChange updates state. Every keystroke updates state, which re-renders the entire form component, which re-renders all 15 inputs. For a simple form this is fine, but with 15 fields and possibly complex validation, it can feel sluggish.

Uncontrolled inputs: no value prop, use refs or FormData to read values on submit. No re-renders during typing. But you lose real-time validation, conditional fields, and the ability to show computed values based on input.

Hmm, wait -- there is a middle ground. React Hook Form uses uncontrolled inputs internally (via refs) but gives you a controlled-like API. It only re-renders the specific field that changed, not the entire form. This is the best of both worlds.

I initially thought "just use uncontrolled inputs" but that is too simplistic. Real forms need:
- Real-time validation (show error as user types)
- Conditional fields (show field B only if field A has value X)
- Computed values (show total based on price and quantity fields)

For these features, you need SOME reactivity. But you do not need the ENTIRE form to re-render when ONE field changes.

The solution depends on form complexity:
- Simple forms (3-5 fields, no validation): controlled useState is fine
- Medium forms (5-15 fields): useReducer or React Hook Form
- Complex forms (15+ fields, validation, conditional logic): React Hook Form or Formik

Actually, Formik has fallen out of favor because it re-renders the whole form by default. React Hook Form is the modern standard because it isolates re-renders per field.

The tradeoff: React Hook Form has a learning curve (register, watch, control concepts) but dramatically reduces re-renders. For 15 fields, it is worth it.
</think>

For 15 fields, use React Hook Form. It uses uncontrolled inputs internally but gives you validation and conditional logic without re-rendering every field on every keystroke.

```tsx
import { useForm, useWatch } from 'react-hook-form';

interface OrderForm {
  firstName: string;
  lastName: string;
  email: string;
  phone: string;
  company: string;
  address: string;
  city: string;
  state: string;
  zip: string;
  country: string;
  shippingMethod: 'standard' | 'express';
  notes: string;
  quantity: number;
  pricePerUnit: number;
  couponCode: string;
}

function OrderFormPage() {
  const {
    register,
    handleSubmit,
    control,
    formState: { errors, isSubmitting },
  } = useForm<OrderForm>({
    defaultValues: {
      country: 'US',
      shippingMethod: 'standard',
      quantity: 1,
      pricePerUnit: 0,
    },
  });

  const onSubmit = async (data: OrderForm) => {
    await fetch('/api/orders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)}>
      {/* register() uses refs -- no re-render on typing */}
      <input
        {...register('firstName', { required: 'First name is required' })}
        placeholder="First name"
      />
      {errors.firstName && (
        <span className="error">{errors.firstName.message}</span>
      )}

      <input
        {...register('email', {
          required: 'Email is required',
          pattern: {
            value: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
            message: 'Invalid email address',
          },
        })}
        placeholder="Email"
      />
      {errors.email && (
        <span className="error">{errors.email.message}</span>
      )}

      <input
        {...register('quantity', {
          valueAsNumber: true,
          min: { value: 1, message: 'Minimum quantity is 1' },
        })}
        type="number"
        placeholder="Quantity"
      />

      {/* Only THIS component re-renders when quantity or price changes */}
      <OrderTotal control={control} />

      <button type="submit" disabled={isSubmitting}>
        {isSubmitting ? 'Submitting...' : 'Place Order'}
      </button>
    </form>
  );
}

// Isolated component -- only re-renders when watched fields change
function OrderTotal({ control }: { control: any }) {
  const quantity = useWatch({ control, name: 'quantity' });
  const pricePerUnit = useWatch({ control, name: 'pricePerUnit' });
  const total = (quantity || 0) * (pricePerUnit || 0);

  return (
    <div className="order-total">
      Total: ${total.toFixed(2)}
    </div>
  );
}
```

Why this beats controlled useState for 15 fields:
- **Typing in field 1** does NOT re-render fields 2-15 (refs, not state)
- **Validation runs per-field** on blur or submit, not on every keystroke
- **useWatch** isolates computed values to their own re-render scope
- **Built-in** error handling, validation rules, and submit management
- **80% less code** than manual useState + validation + error tracking

For comparison, the naive controlled approach would need 15 useState calls (or a big state object), 15 onChange handlers, 15 validation checks, and the entire form re-renders on every single keystroke in any field.'''
    },
    {
        "instruction": r'''I am using useState for a boolean that toggles a modal. My coworker says I should use useReducer instead. Is he right?''',
        "output": r'''<think>
A single boolean toggle -- this is the simplest possible state. useReducer for a boolean? Let me think about whether that makes any sense.

useState for a boolean:
const [isOpen, setIsOpen] = useState(false);
const open = () => setIsOpen(true);
const close = () => setIsOpen(false);
const toggle = () => setIsOpen(prev => !prev);

That is crystal clear. Anyone reading the code understands it immediately.

useReducer for a boolean:
const [isOpen, dispatch] = useReducer((state, action) => {
  switch (action.type) {
    case 'OPEN': return true;
    case 'CLOSE': return false;
    case 'TOGGLE': return !state;
  }
}, false);

That is more code for zero benefit. The reducer adds indirection without adding clarity. There is no complex state transition logic to encapsulate -- it is just true/false.

Hmm, could there be a case where useReducer IS better even for a simple boolean? Wait, actually there is ONE scenario: if the modal open/close logic needs to coordinate with other state. Like if opening the modal also needs to lock body scroll, or closing the modal needs to reset a form inside it. In that case, a reducer that manages { isOpen, formData, scrollLocked } makes sense. But that is not a boolean anymore -- it is a compound state.

I initially thought the coworker might have a point, but no -- for a standalone boolean, useReducer is over-engineering. The coworker might be applying a rule they read ("use useReducer for complex state") too broadly.

The principle: useReducer shines when state transitions involve LOGIC (if this then that). A boolean has no logic -- it is just flip. useState is the right tool.
</think>

Your coworker is wrong for a simple boolean. useState is the correct choice here. useReducer would add complexity with zero benefit.

```tsx
// CORRECT: useState for simple boolean
import { useState, useCallback } from 'react';

function Dashboard() {
  const [isModalOpen, setModalOpen] = useState(false);

  // Simple, clear, obvious
  const openModal = useCallback(() => setModalOpen(true), []);
  const closeModal = useCallback(() => setModalOpen(false), []);

  return (
    <div>
      <button onClick={openModal}>Open Settings</button>
      {isModalOpen && (
        <Modal onClose={closeModal}>
          <SettingsForm />
        </Modal>
      )}
    </div>
  );
}
```

```tsx
// OVERKILL: useReducer for a boolean -- do not do this
function DashboardOverEngineered() {
  const [isModalOpen, dispatch] = useReducer(
    (state: boolean, action: { type: string }) => {
      switch (action.type) {
        case 'OPEN': return true;
        case 'CLOSE': return false;
        case 'TOGGLE': return !state;
        default: return state;
      }
    },
    false
  );

  // More code, more indirection, same result
  return (
    <div>
      <button onClick={() => dispatch({ type: 'OPEN' })}>
        Open Settings
      </button>
      {isModalOpen && (
        <Modal onClose={() => dispatch({ type: 'CLOSE' })}>
          <SettingsForm />
        </Modal>
      )}
    </div>
  );
}
```

```tsx
// WHEN useReducer IS justified: modal + coordinated state
// Opening the modal loads data, closing it resets the form
interface ModalState {
  isOpen: boolean;
  formData: FormData | null;
  loading: boolean;
  error: string | null;
}

type ModalAction =
  | { type: 'OPEN'; initialData: FormData }
  | { type: 'CLOSE' }
  | { type: 'SET_LOADING'; loading: boolean }
  | { type: 'SET_ERROR'; error: string };

function modalReducer(state: ModalState, action: ModalAction): ModalState {
  switch (action.type) {
    case 'OPEN':
      return { isOpen: true, formData: action.initialData, loading: false, error: null };
    case 'CLOSE':
      return { isOpen: false, formData: null, loading: false, error: null };
    case 'SET_LOADING':
      return { ...state, loading: action.loading };
    case 'SET_ERROR':
      return { ...state, error: action.error };
    default:
      return state;
  }
}

// NOW useReducer makes sense -- opening coordinates multiple state fields,
// closing resets everything atomically
```

The rule: **use useReducer when the NEXT state depends on LOGIC about the CURRENT state and action.** A boolean flip has no logic. A modal with coordinated loading, form data, and error states does.'''
    },
    {
        "instruction": r'''What is the difference between putting state in a URL (query params / route params) vs keeping it in React state? When should I use the URL?''',
        "output": r'''<think>
This is an underappreciated topic. URL state vs React state -- they serve fundamentally different purposes but people often default to React state for everything.

URL state is shareable, bookmarkable, and survives page refreshes. React state is ephemeral -- gone on refresh, not shareable via link.

When should state be in the URL? The test is: "Should a user be able to share a link to this exact view?" If yes, it belongs in the URL.

Examples that should be in the URL:
- Search query: /products?q=laptop&sort=price&page=2
- Active tab: /settings/billing
- Filter selections: /jobs?location=remote&level=senior
- Selected item: /products/abc-123

Examples that should NOT be in the URL:
- Modal open/close state (you do not share "open modal" links)
- Form input values mid-typing
- Hover/focus states
- Temporary UI state (loading, animation progress)

Hmm, wait -- actually modal state IS sometimes URL-worthy. If a product page has a "quick view" modal, you might want /products?quickview=abc-123 so the modal opens when someone shares the link. It depends on whether the modal content is the primary thing the user might want to share.

I initially thought this was clear-cut, but there is a gray area. Accordion open/close state -- should it be in the URL? Probably not for most apps, but for a FAQ page where someone wants to link to a specific question, maybe yes.

The key tradeoff: URL state adds complexity (parsing, serialization, history management) but gives you shareability and persistence for free. React state is simpler to manage but ephemeral.

For Next.js / React Router, the pattern is to use the URL as the source of truth for navigation-related state, and derive React state from it when needed.
</think>

The rule of thumb: **if a user should be able to share a link to this exact view, put it in the URL.** Otherwise, keep it in React state.

```tsx
// URL STATE: Search filters -- shareable, bookmarkable, back-button friendly
// URL: /products?q=laptop&category=electronics&sort=price&page=2
import { useSearchParams } from 'react-router-dom';

function ProductSearch() {
  const [searchParams, setSearchParams] = useSearchParams();

  // Read state FROM the URL
  const query = searchParams.get('q') || '';
  const category = searchParams.get('category') || 'all';
  const sort = searchParams.get('sort') || 'relevance';
  const page = parseInt(searchParams.get('page') || '1', 10);

  // Write state TO the URL
  const updateFilters = (updates: Record<string, string>) => {
    const next = new URLSearchParams(searchParams);
    Object.entries(updates).forEach(([key, value]) => {
      if (value) {
        next.set(key, value);
      } else {
        next.delete(key);
      }
    });
    // Reset to page 1 when filters change
    if (!updates.page) next.set('page', '1');
    setSearchParams(next);
  };

  return (
    <div>
      <input
        value={query}
        onChange={e => updateFilters({ q: e.target.value })}
        placeholder="Search products..."
      />
      <select
        value={category}
        onChange={e => updateFilters({ category: e.target.value })}
      >
        <option value="all">All Categories</option>
        <option value="electronics">Electronics</option>
        <option value="clothing">Clothing</option>
      </select>
      <select
        value={sort}
        onChange={e => updateFilters({ sort: e.target.value })}
      >
        <option value="relevance">Relevance</option>
        <option value="price">Price</option>
        <option value="newest">Newest</option>
      </select>

      <ProductGrid query={query} category={category} sort={sort} page={page} />

      <Pagination
        currentPage={page}
        onPageChange={p => updateFilters({ page: String(p) })}
      />
    </div>
  );
}

// REACT STATE: UI-only state that should NOT be in the URL
function ProductCard({ product }: { product: Product }) {
  // These are ephemeral UI states -- no one shares a link to
  // "product card with hover effect active"
  const [isHovered, setIsHovered] = useState(false);
  const [showQuickAdd, setShowQuickAdd] = useState(false);
  const [addedToCart, setAddedToCart] = useState(false);

  return (
    <div
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <img src={product.imageUrl} alt={product.name} />
      <h3>{product.name}</h3>
      {isHovered && (
        <button onClick={() => setShowQuickAdd(true)}>
          Quick Add
        </button>
      )}
    </div>
  );
}
```

Decision matrix:
| State type | URL? | Why |
|---|---|---|
| Search query, filters, sort | Yes | User shares "laptops sorted by price" link |
| Current page / pagination | Yes | User bookmarks page 3 of results |
| Selected tab | Yes | User links to "billing settings" tab |
| Modal open/close | Usually no | Exception: product quick-view modals |
| Form values mid-typing | No | Ephemeral, not worth persisting |
| Loading / error states | No | Transient UI state |
| Hover / focus | No | Interaction state, not application state |

Benefits of URL state:
- **Free persistence** -- survives page refresh without localStorage hacks
- **Back button works** -- browser history tracks filter changes
- **Shareable** -- "look at this search" is just copying the URL
- **SEO** -- search engines can index filtered views'''
    },
]
