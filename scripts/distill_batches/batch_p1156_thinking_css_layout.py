"""
Frontend thinking pairs - CSS layout decisions
"""

pairs = [
    {
        "instruction": r'''I need to build a product grid that shows 4 items per row on desktop, 2 on tablet, and 1 on mobile. Should I use Flexbox or CSS Grid?''',
        "output": r'''<think>
This is a layout grid -- equal-sized items in rows and columns. Let me think about which CSS approach fits best.

Flexbox can do this with flex-wrap and percentage widths (25% for 4 columns, 50% for 2, 100% for 1). But you have to manually calculate widths, subtract gap, and handle the last row alignment. If the last row has 2 items on a 4-column layout, they stretch or you need tricks to prevent stretching.

CSS Grid with grid-template-columns: repeat(4, 1fr) handles this much more cleanly. The auto-fill/minmax pattern can even make it responsive WITHOUT media queries. Hmm, wait -- auto-fill with minmax is nice but gives you less precise control over exact breakpoints. The items might be 3 per row at some width, which might not match the designer's intent.

I initially thought auto-fill was the way to go, but actually if the spec says exactly 4/2/1, explicit media queries with grid-template-columns are more predictable. The auto-fill approach is better when you just want "as many as fit."

The tradeoff is: auto-fill = fluid and adaptive but less controlled. Explicit breakpoints = matches design specs exactly but requires more CSS.

For a product grid, I would use Grid with explicit breakpoints because product pages typically have very specific layout requirements from design. If this were a photo gallery where "whatever fits" is fine, I would use auto-fill.
</think>

CSS Grid is the better choice here. It gives you direct control over column count at each breakpoint, and handles the last-row alignment problem that Flexbox struggles with.

```css
/* Explicit breakpoints -- matches design specs exactly */
.product-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 24px;
  padding: 16px;
}

@media (min-width: 640px) {
  .product-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (min-width: 1024px) {
  .product-grid {
    grid-template-columns: repeat(4, 1fr);
  }
}
```

```tsx
function ProductGrid({ products }: { products: Product[] }) {
  return (
    <div className="product-grid">
      {products.map(p => (
        <ProductCard key={p.id} product={p} />
      ))}
    </div>
  );
}
```

If you want a fluid approach (items fill available space without fixed breakpoints):

```css
/* Auto-fill -- responsive without media queries */
.product-grid-fluid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 24px;
}
```

Why Grid over Flexbox for this:
- **Last row alignment**: Grid leaves empty cells. Flexbox stretches items or requires invisible spacer elements.
- **No width math**: Grid's `1fr` handles gaps automatically. Flexbox needs `calc(25% - 18px)` nonsense.
- **Consistent card sizes**: All cards in a Grid column are the same width by default. Flexbox items can vary if content pushes them.

Use Flexbox when items should have **variable widths** based on content (like a tag list or a toolbar with different-sized buttons).'''
    },
    {
        "instruction": r'''I am building a sidebar layout where the sidebar is 280px wide and the main content fills the rest. The sidebar should collapse on mobile. What is the cleanest CSS approach?''',
        "output": r'''<think>
Classic sidebar + main content layout. Let me think through the options.

Option 1: Flexbox with flex: 1 on the main area. The sidebar has a fixed width, main content gets the rest. Simple and widely used.

Option 2: CSS Grid with grid-template-columns: 280px 1fr. Also clean, slightly more semantic since it is a 2D layout.

Option 3: CSS Grid with named areas. More verbose but readable when the layout gets complex (header, sidebar, main, footer).

Hmm, for a simple two-panel layout, both Flexbox and Grid work equally well. The difference shows up in the mobile collapse behavior.

For mobile collapse, there are two common patterns:
- Sidebar disappears entirely and is triggered by a hamburger menu (overlay or push)
- Sidebar stacks on top of the content (column direction)

Wait, actually the stacking approach is simpler for CSS-only solutions but bad for UX if the sidebar is tall -- the user has to scroll past all the navigation to reach content. An off-canvas sidebar that slides in is better UX but requires JavaScript for the toggle.

I think I should show Grid for the desktop layout (cleanest two-column syntax) and then handle mobile with a simple media query that either stacks or hides the sidebar. I will also show the JavaScript toggle pattern for the hamburger menu since that is what most real apps need.

The tradeoff is: pure CSS stacking is simpler but worse UX. JS-toggled off-canvas is better UX but needs state management.
</think>

CSS Grid gives the cleanest syntax for this. Here is the full pattern with mobile off-canvas sidebar:

```css
.layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  min-height: 100vh;
}

.sidebar {
  background: #1e293b;
  color: white;
  padding: 24px 16px;
  overflow-y: auto;
}

.main-content {
  padding: 24px 32px;
  overflow-y: auto;
}

/* Mobile: sidebar becomes an off-canvas overlay */
@media (max-width: 768px) {
  .layout {
    grid-template-columns: 1fr; /* Single column */
  }

  .sidebar {
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    width: 280px;
    z-index: 40;
    transform: translateX(-100%);
    transition: transform 0.3s ease;
  }

  .sidebar[data-open="true"] {
    transform: translateX(0);
  }

  .sidebar-overlay {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    z-index: 30;
  }

  .sidebar-overlay[data-open="true"] {
    display: block;
  }
}

/* Hide hamburger on desktop */
.menu-toggle {
  display: none;
}

@media (max-width: 768px) {
  .menu-toggle {
    display: block;
    position: fixed;
    top: 16px;
    left: 16px;
    z-index: 50;
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 8px 12px;
    cursor: pointer;
  }
}
```

```tsx
import { useState } from 'react';

function AppLayout({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="layout">
      <button
        className="menu-toggle"
        onClick={() => setSidebarOpen(true)}
        aria-label="Open menu"
      >
        Menu
      </button>

      <div
        className="sidebar-overlay"
        data-open={sidebarOpen}
        onClick={() => setSidebarOpen(false)}
      />

      <aside className="sidebar" data-open={sidebarOpen}>
        <nav>
          <a href="/dashboard">Dashboard</a>
          <a href="/products">Products</a>
          <a href="/settings">Settings</a>
        </nav>
      </aside>

      <main className="main-content">{children}</main>
    </div>
  );
}
```

Key decisions:
- **Grid over Flexbox** because `280px 1fr` is more readable than `flex: 0 0 280px` plus `flex: 1`
- **Off-canvas over stacking** because stacking forces users to scroll past the nav to reach content
- **data-open attribute** over toggling class names -- works cleanly with CSS attribute selectors and keeps the HTML semantic'''
    },
    {
        "instruction": r'''My CSS is a mess -- I have 3000 lines in one file, tons of specificity battles, and my button styles break whenever I add new components. How should I restructure it?''',
        "output": r'''<think>
This is a CSS architecture problem, not a layout problem. 3000 lines in one file with specificity battles -- classic symptoms of having no naming convention and no organizational strategy.

Let me think about the options:

1. BEM (Block Element Modifier) -- naming convention that avoids nesting and specificity issues. .block__element--modifier. Works well but verbose.

2. CSS Modules -- scoped styles per component. No specificity battles because class names are hashed. Works great with React.

3. Utility-first (Tailwind) -- classes like "flex items-center p-4". Eliminates the CSS file entirely. But this is a big migration.

4. ITCSS (Inverted Triangle CSS) -- layered architecture from generic to specific. Good organizational model.

Hmm, the user has 3000 lines already. A full migration to Tailwind is a lot of work. CSS Modules would be the most pragmatic approach for a React project because you can migrate incrementally -- one component at a time.

Wait, but the user might not be using React. They just said "components" which could be any framework. Let me provide a framework-agnostic approach AND a React-specific approach.

Actually, the key insight is: the problem is not which methodology to pick. The problem is that styles are not scoped to components. Any approach that scopes styles to their component solves the specificity battles. CSS Modules, Shadow DOM, Tailwind, even just disciplined BEM naming -- all fix it.

I initially thought I should recommend one specific approach, but actually I should explain the underlying principle (scoping) and then show how CSS Modules implements it since the question mentions React components.

The other thing they need is a token system for shared values (colors, spacing, font sizes) so buttons look consistent everywhere.
</think>

The root cause is that your styles have no scope boundaries. Every class is global, so any new component can accidentally override button styles. Here is the fix in two parts: tokens for consistency, and CSS Modules for scoping.

**Part 1: Design tokens in CSS custom properties**

```css
/* tokens.css -- the ONLY global stylesheet */
:root {
  /* Colors */
  --color-primary: #3b82f6;
  --color-primary-hover: #2563eb;
  --color-danger: #ef4444;
  --color-text: #1e293b;
  --color-text-muted: #64748b;
  --color-bg: #ffffff;
  --color-border: #e2e8f0;

  /* Spacing scale */
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 32px;

  /* Typography */
  --font-sans: system-ui, -apple-system, sans-serif;
  --text-sm: 0.875rem;
  --text-base: 1rem;
  --text-lg: 1.125rem;

  /* Borders */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
}
```

**Part 2: CSS Modules -- scoped per component**

```css
/* Button.module.css */
.button {
  font-family: var(--font-sans);
  font-size: var(--text-sm);
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-md);
  border: 1px solid transparent;
  cursor: pointer;
  transition: background 0.15s ease;
}

.primary {
  background: var(--color-primary);
  color: white;
}

.primary:hover {
  background: var(--color-primary-hover);
}

.danger {
  background: var(--color-danger);
  color: white;
}

.outline {
  background: transparent;
  border-color: var(--color-border);
  color: var(--color-text);
}
```

```tsx
// Button.tsx -- styles are scoped, no specificity leaks
import styles from './Button.module.css';

type Variant = 'primary' | 'danger' | 'outline';

interface ButtonProps {
  variant?: Variant;
  children: React.ReactNode;
  onClick?: () => void;
}

export function Button({
  variant = 'primary',
  children,
  onClick,
}: ButtonProps) {
  const className = [
    styles.button,
    styles[variant],
  ].join(' ');

  return (
    <button className={className} onClick={onClick}>
      {children}
    </button>
  );
}
```

**Migration plan** (do not rewrite everything at once):
1. Extract tokens.css first -- replace all hardcoded colors and spacing with variables
2. Migrate one component at a time to CSS Modules, starting with the most broken ones (your buttons)
3. Delete styles from the 3000-line file as you migrate each component
4. The monolith shrinks naturally until it is gone

Why CSS Modules:
- Each class name is hashed at build time (`.button` becomes `.Button_button_x7k2`), so **no specificity battles**
- You can migrate incrementally -- old global CSS and new modules coexist
- No runtime cost (unlike CSS-in-JS solutions)
- Works with any React bundler (Vite, Next.js, CRA all support it out of the box)'''
    },
    {
        "instruction": r'''When should I use position: sticky vs position: fixed for a navigation bar? I keep getting confused about when each one works.''',
        "output": r'''<think>
This is a common point of confusion. Let me think about the key differences.

position: fixed -- element is positioned relative to the viewport. It is ALWAYS in the same spot on screen regardless of scroll. Removed from document flow, so content flows behind it.

position: sticky -- element is positioned relative to its scroll container. It behaves like position: relative until it hits a threshold (like top: 0), then it "sticks" and behaves like fixed -- but only within its parent container. Once the parent scrolls out of view, the sticky element goes with it.

Wait, there is a crucial gotcha I should mention. Sticky does not work if ANY ancestor has overflow: hidden, overflow: auto, or overflow: scroll (in certain cases). This trips people up constantly. They set position: sticky and nothing happens, and they spend hours debugging before realizing a parent div has overflow: hidden.

Hmm, actually the overflow thing is more nuanced. Sticky fails when the overflow property creates a new scroll context that is not the one the user expects. If the nearest scrolling ancestor has overflow: auto AND is the intended scroll container, sticky works fine. The problem is when there is an INTERMEDIATE ancestor with overflow: hidden that clips the sticky element.

For a main site navigation bar, fixed is usually the right choice because you want it visible at all times regardless of page structure. For a section header within a scrollable area (like an alphabetical contacts list where the letter headers stick), sticky is the right choice.

I initially thought sticky is always better because it does not need a spacer element. But actually fixed is more predictable and has fewer edge cases. The tradeoff: fixed needs a spacer, sticky needs ancestor audit.
</think>

The key difference: **fixed** is relative to the viewport and always visible. **Sticky** is relative to its scroll container and only sticks within its parent's bounds.

```css
/* FIXED navbar -- always visible, viewport-relative */
.navbar-fixed {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 64px;
  background: white;
  z-index: 100;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

/* IMPORTANT: Fixed removes the element from flow.
   You need a spacer so content is not hidden behind it. */
.page-content {
  margin-top: 64px; /* Same as navbar height */
}
```

```css
/* STICKY navbar -- sticks until parent scrolls away */
.navbar-sticky {
  position: sticky;
  top: 0;
  height: 64px;
  background: white;
  z-index: 100;
}

/* No spacer needed -- sticky stays in document flow */
```

```tsx
// When sticky SILENTLY FAILS -- the #1 debugging headache
// This will NOT work:
function BrokenStickyExample() {
  return (
    // overflow: hidden on ANY ancestor kills sticky
    <div style={{ overflow: 'hidden' }}>
      <nav className="navbar-sticky">Logo | Nav</nav>
      <main>Content here</main>
    </div>
  );
}

// Fix: remove overflow: hidden from ancestors,
// or restructure so the sticky element is not inside
// an overflow container.

// Sticky is perfect for section headers in scrollable lists
function ContactList({ contacts }: { contacts: Contact[] }) {
  const grouped = groupByLetter(contacts);
  return (
    <div className="contact-list">
      {Object.entries(grouped).map(([letter, group]) => (
        <section key={letter}>
          {/* This header sticks while its section is visible,
              then scrolls away when the next section arrives */}
          <h2 style={{ position: 'sticky', top: 0, background: '#f1f5f9' }}>
            {letter}
          </h2>
          {group.map(c => (
            <div key={c.id} className="contact-row">{c.name}</div>
          ))}
        </section>
      ))}
    </div>
  );
}
```

When to use which:
- **Fixed**: Main site header, floating action buttons, toast notifications -- things that should ALWAYS be visible regardless of scroll position
- **Sticky**: Section headers in lists, table headers that stick during scroll, sidebar nav that sticks until footer arrives
- **Sticky gotcha**: Check ALL ancestor elements for `overflow: hidden/auto/scroll` -- any one of them can silently break sticky positioning
- **Fixed gotcha**: You must add a spacer (margin/padding) equal to the element height so it does not cover content'''
    },
    {
        "instruction": r'''I need to vertically and horizontally center a modal dialog on the page. There seem to be 5 different ways to do this in CSS. Which one should I actually use?''',
        "output": r'''<think>
Centering in CSS -- the classic meme question. But there are legitimately multiple approaches and they have different tradeoffs. Let me think through them.

1. Flexbox on parent: display: flex; align-items: center; justify-content: center. Simple and widely supported. Works great for centering within a container.

2. Grid on parent: display: grid; place-items: center. Even shorter. Same effect.

3. position: fixed + transform: top: 50%; left: 50%; transform: translate(-50%, -50%). The classic approach for modals specifically. Works regardless of parent layout.

4. position: fixed + margin: auto with inset: 0. Modern approach, needs explicit width/height.

5. position: fixed + flexbox on body. Can conflict with other body styles.

For a modal specifically, I need to consider:
- The modal should be on top of everything (z-index layer)
- It needs a backdrop/overlay behind it
- It should be centered in the viewport, not a parent container
- It should handle content of varying heights (could be short or tall)

Hmm, the fixed + transform approach is the most battle-tested for modals. But wait, actually for a modal with an overlay backdrop, the best pattern is: overlay is fixed covering the viewport, overlay has display: flex to center the modal within it. This way the overlay handles both the backdrop AND the centering.

I initially thought transform was the way to go, but the flex-on-overlay approach is cleaner because it handles both the backdrop and centering in one element, and naturally handles variable content height without the modal going off-screen (you can add max-height + overflow-y: auto).

The tradeoff: transform centering can cause blurry text on some browsers due to sub-pixel rendering. Flexbox centering avoids this.
</think>

For a modal dialog, use **flexbox on the overlay**. It handles centering, backdrop, and overflow in one clean pattern.

```css
/* The overlay IS the centering container */
.modal-overlay {
  position: fixed;
  inset: 0; /* top: 0; right: 0; bottom: 0; left: 0 */
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
  z-index: 1000;
  padding: 24px; /* Prevents modal from touching screen edges */
}

.modal {
  background: white;
  border-radius: 12px;
  padding: 24px;
  width: 100%;
  max-width: 520px;
  max-height: calc(100vh - 48px); /* Account for overlay padding */
  overflow-y: auto;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

/* Fade-in animation */
.modal-overlay {
  animation: fadeIn 0.15s ease;
}

.modal {
  animation: slideUp 0.2s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
```

```tsx
import { useEffect, useRef } from 'react';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}

function Modal({ open, onClose, title, children }: ModalProps) {
  const modalRef = useRef<HTMLDivElement>(null);

  // Close on Escape key
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, onClose]);

  // Trap focus inside modal (accessibility)
  useEffect(() => {
    if (open && modalRef.current) {
      modalRef.current.focus();
    }
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="modal-overlay"
      onClick={onClose}
      role="presentation"
    >
      <div
        ref={modalRef}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        tabIndex={-1}
        onClick={e => e.stopPropagation()}
      >
        <h2 id="modal-title">{title}</h2>
        {children}
        <button onClick={onClose}>Close</button>
      </div>
    </div>
  );
}
```

Why flexbox-on-overlay beats other centering methods:
- **No blurry text** -- transform: translate(-50%, -50%) can cause sub-pixel rendering issues; flexbox avoids this
- **Handles overflow** -- tall content scrolls within the modal, never goes off-screen
- **One element does two jobs** -- the overlay is both the backdrop and the centering container
- **Padding on overlay** prevents the modal from ever touching viewport edges on small screens'''
    },
]
