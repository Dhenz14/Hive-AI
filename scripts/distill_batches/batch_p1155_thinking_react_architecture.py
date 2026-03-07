"""
Frontend thinking pairs - React component architecture
"""

pairs = [
    {
        "instruction": r'''I have a dashboard with 6 different widget components that all need access to the same user data and theme settings. Should I use prop drilling, context, or something else?''',
        "output": r'''<think>
Hmm, let me think about this carefully. Six widgets all needing user data and theme -- that is a classic case where prop drilling gets painful fast. But wait, actually the answer depends on how deep the component tree is and how often the data changes.

If the dashboard is flat -- like a DashboardPage that directly renders Widget1, Widget2, etc. -- then prop drilling is only one level deep and is totally fine. I initially thought context is the obvious answer, but passing props one level is not really "drilling."

But the user said "dashboard with 6 widgets" which usually means there is a layout component, maybe tabs or grid containers, so it is probably 2-3 levels deep. That changes things.

For theme, React Context is the standard answer -- it rarely changes and many components need it. For user data, could be context too, but wait, if user data changes frequently (like real-time notifications count), putting it in context would re-render ALL 6 widgets on every update. That is wasteful.

The tradeoff is: Context is simple but causes broad re-renders. A state manager like Zustand gives selective subscriptions. For theme + user data that updates infrequently, context is fine. For frequently changing data, you want something with selectors.

I think the best approach is a layered solution: Context for theme (changes rarely), context for user data (changes on login/logout), and if any widget needs real-time data, use a separate hook with its own subscription.
</think>

The right answer depends on how often the data changes and how deep the tree is. Here is a layered approach that scales well:

```tsx
import { createContext, useContext, ReactNode } from 'react';

// Theme context -- changes very rarely (user toggles dark mode)
interface ThemeContextValue {
  mode: 'light' | 'dark';
  colors: Record<string, string>;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be inside ThemeProvider');
  return ctx;
}

// User context -- changes on login/logout/profile update
interface UserContextValue {
  id: string;
  name: string;
  role: 'admin' | 'viewer';
  avatarUrl: string;
}

const UserContext = createContext<UserContextValue | null>(null);

function useUser() {
  const ctx = useContext(UserContext);
  if (!ctx) throw new Error('useUser must be inside UserProvider');
  return ctx;
}

// Providers wrap the dashboard once
function AppProviders({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<ThemeContextValue>({
    mode: 'light',
    colors: { primary: '#3b82f6', bg: '#ffffff' },
  });
  const [user, setUser] = useState<UserContextValue | null>(null);

  return (
    <ThemeContext.Provider value={theme}>
      <UserContext.Provider value={user}>
        {children}
      </UserContext.Provider>
    </ThemeContext.Provider>
  );
}

// Each widget only subscribes to what it needs
function StatsWidget() {
  const user = useUser();
  const theme = useTheme();
  // Only re-renders when user or theme context changes
  return (
    <div style={{ background: theme.colors.bg }}>
      <h3>Stats for {user.name}</h3>
      {/* ... */}
    </div>
  );
}

// Split contexts to avoid unnecessary re-renders.
// If theme changes, only widgets using useTheme re-render.
// If user changes, only widgets using useUser re-render.
// Both change rarely so context is fine here.
```

Key architecture decisions:
- **Separate contexts** for theme vs user so changes to one do not re-render consumers of the other
- **Custom hooks** (useTheme, useUser) for clean error messages and type safety
- **Flat prop passing** is fine for 1 level -- do not over-engineer with context if widgets are direct children
- If you later need **frequently changing data** (live notifications, WebSocket updates), use Zustand with selectors instead of context to avoid re-rendering all 6 widgets'''
    },
    {
        "instruction": r'''My React app has a ProductCard component that is used in 4 different pages but each page needs slightly different behavior -- one has a "Add to Cart" button, another has "Compare", another has "Edit", and the last one has no actions at all. How should I structure this?''',
        "output": r'''<think>
This is a composition problem. The user has a shared UI component that needs different actions depending on context. Let me think about the patterns available.

Option 1: Pass a `variant` prop like variant="cart" | "compare" | "edit" | "readonly". But wait, this means ProductCard needs to know about all possible variants. Every time a new page needs a different action, you modify ProductCard. That violates open/closed principle. I initially thought this was fine for 4 variants, but it does not scale.

Option 2: Render props or children slot for the action area. The card handles layout and display, the parent decides what actions to render. This is much more flexible -- could be anything, even empty.

Option 3: Compound component pattern. But that might be overkill here since the structure is consistent -- only the actions change.

Hmm, actually option 2 is the cleanest. The card is a presentational component with a slot for actions. Each page passes its own action buttons. But I should also consider: do the different pages need different data from the product? The cart page needs price, the compare page needs specs. Wait, actually the card probably shows the same product info everywhere -- it is just the actions that differ.

The tradeoff is: render props give maximum flexibility but can make the API verbose. A simple children or `actions` prop that accepts ReactNode is simpler and sufficient here since the actions do not need access to internal card state.

If actions needed access to card state (like hover state or selected state), I would use render props. But buttons are independent, so ReactNode is enough.
</think>

Use the **slot pattern** -- ProductCard handles layout and the parent injects actions via a prop. This keeps the card component closed for modification but open for extension.

```tsx
import { ReactNode, memo } from 'react';

interface Product {
  id: string;
  name: string;
  price: number;
  imageUrl: string;
  description: string;
}

interface ProductCardProps {
  product: Product;
  actions?: ReactNode;  // Slot for page-specific actions
  onClick?: () => void;
}

const ProductCard = memo(function ProductCard({
  product,
  actions,
  onClick,
}: ProductCardProps) {
  return (
    <div className="product-card" onClick={onClick}>
      <img src={product.imageUrl} alt={product.name} />
      <h3>{product.name}</h3>
      <p className="price">${product.price.toFixed(2)}</p>
      <p className="desc">{product.description}</p>
      {actions && (
        <div className="product-card__actions">{actions}</div>
      )}
    </div>
  );
});

// Page 1: Shop page with Add to Cart
function ShopPage({ products }: { products: Product[] }) {
  const addToCart = (id: string) => { /* ... */ };
  return (
    <div className="grid">
      {products.map(p => (
        <ProductCard
          key={p.id}
          product={p}
          actions={
            <button onClick={() => addToCart(p.id)}>
              Add to Cart
            </button>
          }
        />
      ))}
    </div>
  );
}

// Page 2: Compare page with checkbox
function ComparePage({ products }: { products: Product[] }) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const toggle = (id: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };
  return (
    <div className="grid">
      {products.map(p => (
        <ProductCard
          key={p.id}
          product={p}
          actions={
            <label>
              <input
                type="checkbox"
                checked={selected.has(p.id)}
                onChange={() => toggle(p.id)}
              />
              Compare
            </label>
          }
        />
      ))}
    </div>
  );
}

// Page 3: Admin page with Edit button
function AdminPage({ products }: { products: Product[] }) {
  return (
    <div className="grid">
      {products.map(p => (
        <ProductCard
          key={p.id}
          product={p}
          actions={
            <a href={"/admin/products/" + p.id + "/edit"}>
              Edit Product
            </a>
          }
        />
      ))}
    </div>
  );
}

// Page 4: Gallery page with no actions
function GalleryPage({ products }: { products: Product[] }) {
  return (
    <div className="grid">
      {products.map(p => (
        <ProductCard key={p.id} product={p} />
      ))}
    </div>
  );
}
```

Why this works better than a `variant` prop:
- **ProductCard never changes** when you add new pages or actions
- Each page **owns its behavior** -- no switch statements inside the card
- The `actions` slot accepts any ReactNode so it works with buttons, links, checkboxes, or complex multi-button layouts
- Use **render props** instead if the actions need access to internal card state (like hover or expanded)'''
    },
    {
        "instruction": r'''When should I split a React component into smaller ones? My UserProfile component is about 300 lines and renders the avatar, bio, stats, recent posts, and a settings form. Is that too big?''',
        "output": r'''<think>
300 lines with 5 distinct sections -- that is definitely worth splitting, but let me think about why and where to draw the lines.

The naive answer is "split everything into tiny components." But wait, actually splitting too aggressively creates its own problems: prop threading between siblings, harder to trace data flow, indirection overhead for readers.

The better question is: what are the signals that a component should be split?

1. Independent state -- if the settings form has its own form state that the avatar section does not care about, they should be separate. Right now, a keystroke in the settings form re-renders the avatar, bio, stats, and posts sections unnecessarily.

2. Reusability -- could the stats section be used on other pages? If yes, extract it.

3. Readability -- can you understand what the component does by reading the return statement? If you have to scroll through 300 lines of JSX, probably not.

4. Different update frequencies -- recent posts might poll every 30 seconds while avatar is static. Separating them means the polling re-render only affects the posts section.

Hmm, I initially thought all 5 should be separate components, but actually avatar + bio might belong together since they are both static profile info that changes together (when user edits profile). Splitting them apart would just add indirection.

The principle: split along state boundaries and data fetching boundaries, not just visual boundaries. The settings form definitely needs its own component because it has complex form state. Recent posts needs its own component if it has its own data fetching. Avatar + bio + stats could stay together if they share the same data source.
</think>

300 lines with 5 distinct sections is a clear candidate for splitting, but split along **state and data boundaries**, not just visual ones.

```tsx
// Split decision framework:
// 1. Does this section have its OWN state? --> Extract it
// 2. Does this section fetch its OWN data? --> Extract it
// 3. Does this section update at a DIFFERENT frequency? --> Extract it
// 4. Is this section reused elsewhere? --> Extract it
// 5. Is it just static display of the same data? --> Keep together

// UserProfile.tsx -- the orchestrator (now ~40 lines)
import { ProfileHeader } from './ProfileHeader';
import { UserStats } from './UserStats';
import { RecentPosts } from './RecentPosts';
import { SettingsForm } from './SettingsForm';

interface UserProfileProps {
  userId: string;
}

export function UserProfile({ userId }: UserProfileProps) {
  const { data: user, isLoading } = useUser(userId);

  if (isLoading || !user) return <ProfileSkeleton />;

  return (
    <div className="user-profile">
      {/* Static display -- shares same user data, keep together */}
      <ProfileHeader user={user} />

      {/* Has its own derived calculations but no independent state */}
      <UserStats
        postCount={user.postCount}
        followers={user.followers}
        following={user.following}
      />

      {/* Fetches its own data, updates independently */}
      <RecentPosts userId={userId} />

      {/* Has complex form state -- definitely extract */}
      <SettingsForm user={user} />
    </div>
  );
}

// ProfileHeader.tsx -- avatar + bio together (~50 lines)
// They display the same user object, no independent state
export function ProfileHeader({ user }: { user: User }) {
  return (
    <div className="profile-header">
      <img
        src={user.avatarUrl}
        alt={user.name}
        className="avatar"
      />
      <h1>{user.name}</h1>
      <p className="bio">{user.bio}</p>
      <span className="joined">
        Joined {user.joinDate}
      </span>
    </div>
  );
}

// RecentPosts.tsx -- own data fetching, own loading state (~80 lines)
export function RecentPosts({ userId }: { userId: string }) {
  const { data: posts, isLoading } = useRecentPosts(userId);
  // This component re-renders on its own schedule
  // without affecting the rest of the profile
  if (isLoading) return <PostsSkeleton />;
  return (
    <section>
      <h2>Recent Posts</h2>
      {posts.map(post => (
        <PostPreview key={post.id} post={post} />
      ))}
    </section>
  );
}

// SettingsForm.tsx -- complex form state (~120 lines)
export function SettingsForm({ user }: { user: User }) {
  const [formData, setFormData] = useState({
    name: user.name,
    bio: user.bio,
    email: user.email,
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  // All the form state, validation, submission logic
  // lives here without polluting the parent
  return <form>{/* ... */}</form>;
}
```

Rules of thumb:
- **Do not split** purely for line count -- a 200-line component with no state is fine
- **Always split** when a section has its own useState, useEffect, or data fetching
- **Avatar + bio** stay together because they render the same data object with no independent state
- **SettingsForm** is the clearest extraction target -- form state should never live in the same component as display-only sections'''
    },
    {
        "instruction": r'''I keep hearing about "lifting state up" in React but also "colocating state." These seem contradictory. When do I do which?''',
        "output": r'''<think>
This is a great conceptual question. Let me think through when each principle applies because they really do seem contradictory at first.

"Lift state up" means: when two sibling components need the same data, move the state to their closest common parent. This is React 101.

"Colocate state" means: keep state as close to where it is used as possible. Do not put state in a parent component if only one child needs it.

Wait, actually these are not contradictory at all -- they are two sides of the same coin. The rule is: state should live at the LOWEST common ancestor of all components that need it. If only one component needs it, that component IS the lowest common ancestor (colocate). If two siblings need it, their parent is the lowest common ancestor (lift up).

The mistake people make is lifting state TOO high. They put everything in a top-level AppState because "what if something else needs it later?" That causes unnecessary re-renders everywhere.

Hmm, but there is a subtlety. Sometimes you lift state up and then realize the parent is re-rendering children that do not care about that state. At that point you either: (a) push the state back down (colocate), (b) split the state into multiple pieces, or (c) use React.memo on the unaffected children.

The real principle is: state should live at the lowest point in the tree that satisfies all current consumers. Not higher, not lower. And you should actively push state DOWN when requirements change and fewer components need it.
</think>

They are not contradictory -- they are the same principle viewed from different directions. The unified rule is: **state lives at the lowest common ancestor of all its consumers.**

```tsx
// COLOCATE: Only SearchBox needs the input value
// DO NOT lift this to the parent page
function SearchBox({ onSearch }: { onSearch: (q: string) => void }) {
  // This state belongs HERE, not in a parent
  const [query, setQuery] = useState('');

  return (
    <input
      value={query}
      onChange={e => setQuery(e.target.value)}
      onKeyDown={e => {
        if (e.key === 'Enter') onSearch(query);
      }}
    />
  );
}

// LIFT UP: Both ProductList and CartSummary need selectedItems
// State must live in their common parent
function ShopPage() {
  // Lifted here because two children need it
  const [selectedItems, setSelectedItems] = useState<string[]>([]);

  return (
    <div>
      <ProductList
        selectedItems={selectedItems}
        onToggle={id =>
          setSelectedItems(prev =>
            prev.includes(id)
              ? prev.filter(x => x !== id)
              : [...prev, id]
          )
        }
      />
      <CartSummary selectedItems={selectedItems} />
    </div>
  );
}

// PUSH BACK DOWN: You lifted too high
// BAD -- filter state is in App but only ProductList uses it
function AppBad() {
  const [user, setUser] = useState(null);
  const [filter, setFilter] = useState('all'); // Only ProductList needs this!
  return (
    <div>
      <Header user={user} />
      {/* Header re-renders when filter changes for no reason */}
      <ProductList filter={filter} onFilterChange={setFilter} />
    </div>
  );
}

// GOOD -- push filter state back down into ProductList
function AppGood() {
  const [user, setUser] = useState(null);
  return (
    <div>
      <Header user={user} />
      <ProductList /> {/* Manages its own filter state */}
    </div>
  );
}
```

Decision flowchart:
1. **How many components need this state?**
   - Just one --> colocate it in that component
   - Multiple siblings --> lift to their closest common parent
   - Many components across the tree --> consider context or external store

2. **Did you lift it and now unrelated children re-render?**
   - Push the state back down if possible
   - Or split the parent into a stateful wrapper and a pure layout component
   - Or use React.memo on unaffected children (last resort)

3. **Are you lifting "just in case" something might need it later?**
   - Do not. Colocate now, lift later when the need is real. Moving state up is a quick refactor.'''
    },
    {
        "instruction": r'''I have a list of 500 items that each render a complex card. The page is slow. My senior says "just add React.memo everywhere" but that does not feel right. What is the actual approach?''',
        "output": r'''<think>
The senior's advice is a common knee-jerk reaction. React.memo can help, but "add it everywhere" is not a real performance strategy. Let me think about why.

React.memo does a shallow comparison of props. If you are passing new object or array references on every render (which is extremely common), React.memo's comparison returns false every time and it does NOTHING except add overhead from the comparison itself.

For 500 complex cards, the real question is: why are all 500 re-rendering? Common causes:

1. Parent re-renders and passes new prop references (inline objects, callbacks without useCallback)
2. The list itself is being filtered/sorted and creates a new array every render
3. State changes in the parent (like a search input) trigger re-render of all 500 cards
4. CSS animations or intersection observer callbacks causing state updates

Wait, actually even if we fix the re-render problem, rendering 500 complex cards on initial mount is also slow. The user might be experiencing TWO problems: slow initial render AND slow re-renders.

For initial render: virtualization. Only render the ~20 cards visible in the viewport. react-window or @tanstack/virtual are the standard solutions.

For re-renders: stable references (useMemo for data, useCallback for handlers) THEN React.memo on the card component. The order matters -- memo without stable references is useless.

Hmm, but could be that the cards themselves are doing expensive work (parsing dates, formatting currency, computing derived data). In that case, useMemo inside each card helps.

The tradeoff is: virtualization adds complexity (dynamic heights are tricky, scroll position restoration, accessibility concerns). If the list is paginated and never actually shows 500 at once, pagination is simpler than virtualization.
</think>

"React.memo everywhere" without fixing the underlying cause is like putting a bandaid on a broken pipe. Here is the systematic approach:

```tsx
// STEP 1: Virtualize -- only render visible items
// This is the single biggest win for 500+ items
import { useVirtualizer } from '@tanstack/react-virtual';
import { useRef, useCallback, useMemo } from 'react';

function ProductList({ products }: { products: Product[] }) {
  const parentRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: products.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 280, // estimated card height in px
    overscan: 5, // render 5 extra above/below viewport
  });

  return (
    <div
      ref={parentRef}
      style={{ height: '100vh', overflow: 'auto' }}
    >
      <div
        style={{
          height: virtualizer.getTotalSize(),
          position: 'relative',
        }}
      >
        {virtualizer.getVirtualItems().map(virtualRow => (
          <div
            key={virtualRow.key}
            style={{
              position: 'absolute',
              top: 0,
              transform: `translateY(${virtualRow.start}px)`,
              width: '100%',
            }}
          >
            <ProductCard product={products[virtualRow.index]} />
          </div>
        ))}
      </div>
    </div>
  );
}

// STEP 2: Stable references BEFORE applying React.memo
// Memo is useless if you pass new objects every render
function ProductListWithStableProps({
  products,
  onAddToCart,
}: {
  products: Product[];
  onAddToCart: (id: string) => void;
}) {
  // useCallback so the function reference stays stable
  const handleAdd = useCallback(
    (id: string) => onAddToCart(id),
    [onAddToCart]
  );

  // useMemo for derived data
  const sortedProducts = useMemo(
    () => [...products].sort((a, b) => a.name.localeCompare(b.name)),
    [products]
  );

  return (
    <div>
      {sortedProducts.map(p => (
        <MemoizedCard
          key={p.id}
          product={p}
          onAdd={handleAdd}
        />
      ))}
    </div>
  );
}

// STEP 3: NOW React.memo makes sense -- props are stable
const MemoizedCard = memo(function ProductCard({
  product,
  onAdd,
}: {
  product: Product;
  onAdd: (id: string) => void;
}) {
  // Expensive formatting? Memoize inside the card too
  const formattedPrice = useMemo(
    () => new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
    }).format(product.price),
    [product.price]
  );

  return (
    <div className="product-card">
      <img src={product.imageUrl} alt={product.name} />
      <h3>{product.name}</h3>
      <span>{formattedPrice}</span>
      <button onClick={() => onAdd(product.id)}>
        Add to Cart
      </button>
    </div>
  );
});
```

Priority order for fixing list performance:
1. **Virtualize** -- renders ~20 items instead of 500 (biggest single win)
2. **Stabilize references** -- useCallback for handlers, useMemo for derived arrays
3. **Then React.memo** -- now the shallow comparison actually works
4. **Paginate** if virtualization adds too much complexity (dynamic heights, accessibility)
5. **Profile first** -- use React DevTools Profiler to confirm WHERE the slowness is before optimizing'''
    },
]
