"""
Frontend thinking pairs - CSS-in-JS and styling approaches
"""

pairs = [
    {
        "instruction": r'''My team is starting a new React project and we need to pick a styling approach. Should we use Tailwind, CSS Modules, or styled-components? We have 5 developers with varying CSS experience.''',
        "output": r'''<think>
This is a team decision that depends heavily on context. Let me think through each option for a team of 5 with varying CSS skill levels.

Tailwind CSS:
- Utility classes applied directly in JSX: className="flex items-center p-4 bg-blue-500"
- No separate CSS files, no naming things
- Enforces a design system through the config (spacing scale, color palette)
- Low-skill CSS developers can be productive quickly because they choose from predefined options
- Downside: JSX gets verbose with many classes
- Downside: learning the utility class names takes time upfront
- Runtime cost: none (compiled at build time, unused utilities stripped)

CSS Modules:
- Scoped CSS files per component: Button.module.css
- Developers write regular CSS, but class names are scoped
- Familiar to anyone who knows CSS
- No library dependency (built into Vite, Next.js, CRA)
- Downside: no built-in design system enforcement -- developers can use any values
- Downside: still need to name things (classes, selectors)

styled-components:
- CSS-in-JS, write CSS in tagged template literals
- Dynamic styles based on props
- Scoped by default
- Downside: runtime cost (generates styles at render time)
- Downside: React Server Components do NOT support styled-components (RSC limitation)
- Downside: larger bundle size

Hmm, for a team with varying CSS experience, Tailwind has an interesting advantage: it constrains choices. Instead of letting developers pick arbitrary pixel values (padding: 13px? 17px?), Tailwind forces them into a scale (p-3 = 12px, p-4 = 16px). This creates consistency without design system documentation.

Wait, but I should also consider: is this a Next.js App Router project? If yes, styled-components is problematic because it relies on React context and client-side rendering. Server Components do not support it. That might eliminate it from consideration.

I initially thought CSS Modules was the safest choice, but actually Tailwind has become the most popular choice for new projects. The productivity gains from not context-switching between CSS and JSX files are significant.

The tradeoff: Tailwind has the highest initial learning curve (memorizing utility names) but the lowest ongoing cost. CSS Modules has the lowest learning curve but no guardrails for consistency. styled-components has the most powerful dynamic styling but runtime overhead and RSC incompatibility.

For a team of 5 with varying CSS skill, I would recommend Tailwind because it enforces consistency and reduces decision fatigue. But I should present all options fairly.
</think>

For a 5-person team with varying CSS skills, I recommend Tailwind CSS. It enforces design consistency through its configuration and reduces the "naming things" problem. Here is why, with comparisons:

```tsx
// TAILWIND: Utility classes, no separate CSS files
// Consistency enforced through tailwind.config.ts

function ProductCard({ product }: { product: Product }) {
  return (
    <div className="rounded-lg border border-gray-200 p-4 shadow-sm hover:shadow-md transition-shadow">
      <img
        src={product.imageUrl}
        alt={product.name}
        className="w-full h-48 object-cover rounded-md"
      />
      <h3 className="mt-3 text-lg font-semibold text-gray-900">
        {product.name}
      </h3>
      <p className="mt-1 text-sm text-gray-500">
        {product.description}
      </p>
      <div className="mt-4 flex items-center justify-between">
        <span className="text-xl font-bold text-blue-600">
          ${product.price}
        </span>
        <button className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
          Add to Cart
        </button>
      </div>
    </div>
  );
}
```

```tsx
// CSS MODULES: Scoped CSS, familiar syntax
// ProductCard.module.css
/*
.card {
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  padding: 16px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);
}
.card:hover {
  box-shadow: 0 4px 6px rgba(0,0,0,0.1);
}
.image { width: 100%; height: 192px; object-fit: cover; }
.title { margin-top: 12px; font-size: 1.125rem; font-weight: 600; }
.price { font-size: 1.25rem; font-weight: 700; color: #2563eb; }
*/

import styles from './ProductCard.module.css';

function ProductCard({ product }: { product: Product }) {
  return (
    <div className={styles.card}>
      <img className={styles.image} src={product.imageUrl} alt={product.name} />
      <h3 className={styles.title}>{product.name}</h3>
      <span className={styles.price}>${product.price}</span>
    </div>
  );
}
```

```tsx
// STYLED-COMPONENTS: CSS-in-JS with dynamic props
// WARNING: Not compatible with React Server Components
import styled from 'styled-components';

const Card = styled.div`
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  padding: 16px;
  &:hover { box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
`;

const Price = styled.span<{ discounted?: boolean }>`
  font-size: 1.25rem;
  font-weight: 700;
  color: ${props => props.discounted ? '#dc2626' : '#2563eb'};
`;

function ProductCard({ product }: { product: Product }) {
  return (
    <Card>
      <h3>{product.name}</h3>
      <Price discounted={product.onSale}>${product.price}</Price>
    </Card>
  );
}
```

Comparison for your team:

| Factor | Tailwind | CSS Modules | styled-components |
|---|---|---|---|
| Learning curve | Medium (new syntax) | Low (regular CSS) | Medium (template literals) |
| Consistency enforcement | Strong (config) | Weak (any values) | Weak (any values) |
| Junior-friendly | Yes (constrained choices) | Yes (familiar CSS) | Medium |
| Bundle size impact | Small (purged unused) | Small (no runtime) | Larger (runtime JS) |
| Server Components | Works | Works | Does NOT work |
| Dynamic styles | Conditional classes | CSS variables | Props-based (powerful) |
| File organization | No CSS files | One CSS file per component | No CSS files |

My recommendation for your team:
- **Tailwind** if you want consistency and fast development. Junior devs pick from predefined utilities instead of inventing arbitrary values.
- **CSS Modules** if your team is already strong in CSS and prefers writing traditional stylesheets.
- **Avoid styled-components** for new projects -- the React Server Components incompatibility is a dealbreaker for Next.js App Router.'''
    },
    {
        "instruction": r'''How do I implement a consistent design token system in my React project? I want colors, spacing, and typography to be defined in one place and used everywhere.''',
        "output": r'''<think>
Design tokens are the single source of truth for visual design values. The question is how to implement them in a way that works across the styling approach the team uses.

The most framework-agnostic approach is CSS custom properties (variables). They work with any styling solution -- Tailwind, CSS Modules, styled-components, inline styles. And they support theming (dark mode) via CSS cascade.

But wait, there is also the option of a TypeScript/JavaScript token file that exports values. This is useful for styled-components and inline styles but redundant if you are using CSS custom properties.

Hmm, the best approach is BOTH:
1. CSS custom properties as the runtime source of truth (theming, cascade, browser)
2. A TypeScript constants file for type-safe access in JS when needed

For Tailwind specifically, tokens are defined in tailwind.config.ts and compiled into utility classes. You do not need separate CSS variables because Tailwind IS the token system.

I initially thought CSS custom properties alone were sufficient, but for TypeScript projects, having type-safe token access prevents typos. If a developer writes --color-primry (typo), CSS silently falls back. A TypeScript import would catch the error at compile time.

The tradeoff: CSS custom properties work everywhere but have no type safety. TypeScript tokens have type safety but add an import. Using both gives you the best of both worlds at the cost of slight duplication.

For dark mode, CSS custom properties are the clear winner because you can swap an entire theme by changing properties at the :root level. No JavaScript needed.
</think>

Use CSS custom properties as the runtime layer and a TypeScript file for type safety. This works with any styling approach.

```css
/* tokens.css -- THE source of truth for all design values */
:root {
  /* Color palette */
  --color-primary-50: #eff6ff;
  --color-primary-100: #dbeafe;
  --color-primary-500: #3b82f6;
  --color-primary-600: #2563eb;
  --color-primary-700: #1d4ed8;

  --color-gray-50: #f8fafc;
  --color-gray-100: #f1f5f9;
  --color-gray-200: #e2e8f0;
  --color-gray-500: #64748b;
  --color-gray-700: #334155;
  --color-gray-900: #0f172a;

  --color-success: #22c55e;
  --color-warning: #f59e0b;
  --color-error: #ef4444;

  /* Semantic colors (reference palette colors) */
  --color-text: var(--color-gray-900);
  --color-text-muted: var(--color-gray-500);
  --color-bg: #ffffff;
  --color-bg-secondary: var(--color-gray-50);
  --color-border: var(--color-gray-200);

  /* Spacing scale (4px base) */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-10: 40px;
  --space-12: 48px;
  --space-16: 64px;

  /* Typography */
  --font-sans: 'Inter', system-ui, -apple-system, sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;

  --text-xs: 0.75rem;    /* 12px */
  --text-sm: 0.875rem;   /* 14px */
  --text-base: 1rem;     /* 16px */
  --text-lg: 1.125rem;   /* 18px */
  --text-xl: 1.25rem;    /* 20px */
  --text-2xl: 1.5rem;    /* 24px */
  --text-3xl: 1.875rem;  /* 30px */

  --leading-tight: 1.25;
  --leading-normal: 1.5;
  --leading-relaxed: 1.75;

  /* Borders */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-full: 9999px;

  /* Shadows */
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);
  --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.07);
  --shadow-lg: 0 10px 25px rgba(0, 0, 0, 0.1);
}

/* Dark mode -- just swap the semantic tokens */
[data-theme="dark"] {
  --color-text: #f1f5f9;
  --color-text-muted: #94a3b8;
  --color-bg: #0f172a;
  --color-bg-secondary: #1e293b;
  --color-border: #334155;
}
```

```tsx
// tokens.ts -- TypeScript constants for type-safe access
// Use this when you need token values in JavaScript

export const tokens = {
  color: {
    primary500: 'var(--color-primary-500)',
    primary600: 'var(--color-primary-600)',
    text: 'var(--color-text)',
    textMuted: 'var(--color-text-muted)',
    error: 'var(--color-error)',
  },
  space: {
    1: 'var(--space-1)',
    2: 'var(--space-2)',
    4: 'var(--space-4)',
    6: 'var(--space-6)',
    8: 'var(--space-8)',
  },
  radius: {
    sm: 'var(--radius-sm)',
    md: 'var(--radius-md)',
    lg: 'var(--radius-lg)',
    full: 'var(--radius-full)',
  },
} as const;

// Type-safe token access
type ColorToken = keyof typeof tokens.color;
type SpaceToken = keyof typeof tokens.space;
```

```tsx
// Usage in components -- works with ANY styling approach

// With CSS Modules:
/* Card.module.css */
/*
.card {
  padding: var(--space-6);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
  background: var(--color-bg);
}
.title {
  font-size: var(--text-xl);
  color: var(--color-text);
}
*/

// With inline styles:
function Badge({ children, variant }: { children: string; variant: 'success' | 'error' }) {
  return (
    <span style={{
      padding: 'var(--space-1) var(--space-2)',
      borderRadius: 'var(--radius-full)',
      fontSize: 'var(--text-xs)',
      background: variant === 'success' ? 'var(--color-success)' : 'var(--color-error)',
      color: 'white',
    }}>
      {children}
    </span>
  );
}

// Dark mode toggle
function ThemeToggle() {
  const [dark, setDark] = useState(false);

  const toggle = () => {
    setDark(!dark);
    document.documentElement.setAttribute(
      'data-theme',
      dark ? 'light' : 'dark'
    );
  };

  return (
    <button onClick={toggle}>
      {dark ? 'Light Mode' : 'Dark Mode'}
    </button>
  );
}
```

Key benefits of this approach:
- **One file to change** when updating the design (tokens.css)
- **Dark mode for free** by swapping semantic tokens at the root
- **No JavaScript runtime** -- CSS custom properties are resolved by the browser
- **Works everywhere** -- CSS Modules, Tailwind (map to config), inline styles, any library
- **Type safety optional** -- import from tokens.ts when you need autocomplete in JS'''
    },
    {
        "instruction": r'''I am using Tailwind but my className strings are getting insanely long. Some components have 20+ utility classes. How do I keep this maintainable?''',
        "output": r'''<think>
Long Tailwind class strings are the #1 complaint about Tailwind. Let me think about the strategies to manage this.

Option 1: Extract components. Instead of repeating the same class string in 10 places, create a React component that encapsulates those classes. This is the primary Tailwind-recommended approach.

Option 2: Use clsx/cn utility for conditional classes. Makes the className prop more readable.

Option 3: Use @apply in a CSS file to create custom utility classes. But wait -- the Tailwind team actually DISCOURAGES @apply because it defeats the purpose of utility-first CSS. They say "just make a component" instead.

Option 4: Use a class variance authority (CVA) library. This is great for components with variants (like buttons with size/color options). It organizes the classes into a structured config.

Hmm, I think the real answer is: long class strings are a SIGNAL that you should extract a component. If a div has 20 utility classes, it is doing something important and reusable. Extract it into a <Card>, <Badge>, or <Input> component.

I initially thought @apply was a good escape hatch, but actually it creates the same problems as regular CSS (naming, specificity) while losing Tailwind's strengths (colocation, deletability). The better escape hatch is component extraction.

There is also a practical tip: use the tailwind-merge library with clsx. This handles class conflicts when merging (e.g., parent passes className that overrides a child's default styling).

The tradeoff: extracting components adds indirection (more files, more jumping around), but it is the same tradeoff as any component extraction. The long class string problem goes away because each component has its own manageable set of classes.
</think>

Long class strings signal that you need to extract components and use a utility like CVA (Class Variance Authority) for variant-based styling.

```tsx
// PROBLEM: 20+ utilities on one element
function BadProductCard({ product }: { product: Product }) {
  return (
    <div className="relative flex flex-col overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm transition-all duration-200 hover:shadow-md hover:border-gray-300 group cursor-pointer">
      <img className="h-48 w-full object-cover transition-transform duration-300 group-hover:scale-105" src={product.imageUrl} alt={product.name} />
      <div className="flex flex-1 flex-col p-4 gap-2">
        <h3 className="text-base font-semibold text-gray-900 line-clamp-2 leading-tight">{product.name}</h3>
        <span className="mt-auto text-lg font-bold text-blue-600">${product.price}</span>
      </div>
    </div>
  );
}
```

```tsx
// FIX 1: Extract reusable components
// Each component has a manageable number of classes

import { ReactNode } from 'react';

function Card({
  children,
  className = '',
  hoverable = false,
}: {
  children: ReactNode;
  className?: string;
  hoverable?: boolean;
}) {
  return (
    <div className={[
      'rounded-lg border border-gray-200 bg-white shadow-sm overflow-hidden',
      hoverable && 'transition-shadow hover:shadow-md hover:border-gray-300 cursor-pointer',
      className,
    ].filter(Boolean).join(' ')}>
      {children}
    </div>
  );
}

function CardImage({ src, alt }: { src: string; alt: string }) {
  return (
    <img
      className="h-48 w-full object-cover"
      src={src}
      alt={alt}
    />
  );
}

function CardBody({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2 p-4">{children}</div>
  );
}

// Now the ProductCard is clean and readable
function ProductCard({ product }: { product: Product }) {
  return (
    <Card hoverable>
      <CardImage src={product.imageUrl} alt={product.name} />
      <CardBody>
        <h3 className="text-base font-semibold text-gray-900 line-clamp-2">
          {product.name}
        </h3>
        <span className="mt-auto text-lg font-bold text-blue-600">
          ${product.price}
        </span>
      </CardBody>
    </Card>
  );
}
```

```tsx
// FIX 2: CVA for components with multiple variants
// npm install class-variance-authority
import { cva, type VariantProps } from 'class-variance-authority';

// Define all variants in a structured config
const buttonVariants = cva(
  // Base classes (always applied)
  'inline-flex items-center justify-center rounded-md font-medium transition-colors focus-visible:outline-none focus-visible:ring-2',
  {
    variants: {
      variant: {
        primary: 'bg-blue-600 text-white hover:bg-blue-700',
        secondary: 'bg-gray-100 text-gray-900 hover:bg-gray-200',
        danger: 'bg-red-600 text-white hover:bg-red-700',
        ghost: 'text-gray-700 hover:bg-gray-100',
      },
      size: {
        sm: 'h-8 px-3 text-sm',
        md: 'h-10 px-4 text-sm',
        lg: 'h-12 px-6 text-base',
      },
    },
    defaultVariants: {
      variant: 'primary',
      size: 'md',
    },
  }
);

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof buttonVariants>;

function Button({ variant, size, className, ...props }: ButtonProps) {
  return (
    <button
      className={buttonVariants({ variant, size, className })}
      {...props}
    />
  );
}

// Clean usage:
<Button variant="primary" size="lg">Save</Button>
<Button variant="danger" size="sm">Delete</Button>
<Button variant="ghost">Cancel</Button>
```

```tsx
// FIX 3: cn() utility for merging/overriding classes
// npm install clsx tailwind-merge
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// tailwind-merge resolves conflicts:
cn('px-4 py-2', 'px-6')
// Result: 'py-2 px-6' (px-6 wins over px-4)

// Conditional classes are clean:
cn(
  'rounded-md border px-4 py-2',
  isActive && 'bg-blue-600 text-white',
  isDisabled && 'opacity-50 cursor-not-allowed',
  className // Allow parent to override
)
```

Strategy summary:
1. **Extract components** when you see 10+ utilities on one element
2. **Use CVA** for components with size/color/variant props
3. **Use cn()** (clsx + tailwind-merge) for conditional and overridable classes
4. **Avoid @apply** -- it creates the same problems as regular CSS without the benefits of Tailwind'''
    },
    {
        "instruction": r'''How do I handle responsive design with Tailwind? I have a layout that needs to be completely different on mobile vs desktop -- not just "smaller."''',
        "output": r'''<think>
Responsive design with Tailwind uses breakpoint prefixes: sm:, md:, lg:, xl:. Tailwind is mobile-first, so unprefixed classes apply to mobile and breakpoint prefixes override for larger screens.

For layouts that are "completely different" on mobile vs desktop, the challenge is that you might end up with so many responsive classes that the component becomes unreadable. Let me think about approaches.

Approach 1: Breakpoint prefixes on every utility. Works but can get verbose:
className="flex flex-col md:flex-row gap-4 md:gap-8 p-4 md:p-8"

Approach 2: Separate components for mobile and desktop, rendered conditionally. But wait, this does not work well because you would need to use JS to detect screen size, and the component renders before JS runs (flash of wrong layout). Also, both components ship JS to the client.

Approach 3: CSS display/visibility tricks. Render both layouts, hide one with responsive classes:
className="block md:hidden" for mobile-only content
className="hidden md:block" for desktop-only content
But this renders both DOMs which can be wasteful.

Hmm, for truly different layouts (not just rearranging the same elements), approach 3 is actually fine if the hidden content is lightweight. For complex content, you might want a custom hook like useMediaQuery, but that has hydration issues with SSR.

I initially thought approach 1 (responsive prefixes) was always enough, but for COMPLETELY different layouts (sidebar navigation on desktop, bottom tab bar on mobile), you really do need different component trees. The show/hide approach is the simplest and most reliable.

The tradeoff: responsive utilities handle simple changes (column to row, padding adjustments). For fundamentally different layouts, use show/hide or separate components with a CSS-based approach to avoid hydration mismatches.
</think>

Tailwind is mobile-first -- unprefixed classes apply to mobile, breakpoint prefixes override for larger screens. For completely different layouts, use the show/hide pattern.

```tsx
// SIMPLE: Responsive modifications (same structure, different styling)
function ProductGrid({ products }: { products: Product[] }) {
  return (
    <div className={[
      // Mobile: single column, compact padding
      'grid grid-cols-1 gap-4 p-4',
      // Tablet: 2 columns, more gap
      'sm:grid-cols-2 sm:gap-6',
      // Desktop: 3 columns, generous padding
      'lg:grid-cols-3 lg:gap-8 lg:p-8',
      // Wide: 4 columns
      'xl:grid-cols-4',
    ].join(' ')}>
      {products.map(p => (
        <ProductCard key={p.id} product={p} />
      ))}
    </div>
  );
}

// COMPLEX: Completely different layouts at different breakpoints
// Use show/hide to render different component trees
function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen">
      {/* MOBILE: Bottom tab bar navigation */}
      <div className="md:hidden">
        <main className="pb-16">{children}</main>
        <nav className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 flex justify-around py-2 z-50">
          <NavTab icon="home" label="Home" href="/" />
          <NavTab icon="search" label="Search" href="/search" />
          <NavTab icon="cart" label="Cart" href="/cart" />
          <NavTab icon="profile" label="Profile" href="/profile" />
        </nav>
      </div>

      {/* DESKTOP: Sidebar navigation */}
      <div className="hidden md:flex">
        <aside className="w-64 min-h-screen bg-gray-900 text-white p-6 flex-shrink-0">
          <div className="text-xl font-bold mb-8">MyApp</div>
          <nav className="flex flex-col gap-2">
            <SidebarLink icon="home" label="Dashboard" href="/" />
            <SidebarLink icon="products" label="Products" href="/products" />
            <SidebarLink icon="analytics" label="Analytics" href="/analytics" />
            <SidebarLink icon="settings" label="Settings" href="/settings" />
          </nav>
        </aside>
        <main className="flex-1 p-8">{children}</main>
      </div>
    </div>
  );
}

// RESPONSIVE COMPONENT: Different display depending on screen
function StatsSection({ stats }: { stats: Stats }) {
  return (
    <div>
      {/* Mobile: Horizontal scroll cards */}
      <div className="flex gap-4 overflow-x-auto pb-4 snap-x md:hidden">
        <StatCard label="Revenue" value={stats.revenue} className="min-w-[200px] snap-start" />
        <StatCard label="Users" value={stats.users} className="min-w-[200px] snap-start" />
        <StatCard label="Orders" value={stats.orders} className="min-w-[200px] snap-start" />
      </div>

      {/* Desktop: Grid layout */}
      <div className="hidden md:grid md:grid-cols-3 md:gap-6">
        <StatCard label="Revenue" value={stats.revenue} />
        <StatCard label="Users" value={stats.users} />
        <StatCard label="Orders" value={stats.orders} />
      </div>
    </div>
  );
}
```

```tsx
// RESPONSIVE TEXT: Different sizes and line clamping
function ArticlePreview({ article }: { article: Article }) {
  return (
    <article className="p-4 md:p-6">
      {/* Mobile: smaller title, 1 line; Desktop: larger, 2 lines */}
      <h2 className="text-lg font-bold line-clamp-1 md:text-2xl md:line-clamp-2">
        {article.title}
      </h2>

      {/* Mobile: hide description; Desktop: show 3 lines */}
      <p className="hidden md:block md:mt-2 md:text-gray-600 md:line-clamp-3">
        {article.description}
      </p>

      {/* Mobile: compact meta; Desktop: spread out */}
      <div className="mt-2 flex items-center gap-2 text-sm text-gray-500 md:mt-4 md:gap-4">
        <span>{article.author}</span>
        <span className="hidden md:inline">|</span>
        <span>{article.date}</span>
        {/* Only show read time on desktop */}
        <span className="hidden md:inline">{article.readTime} min read</span>
      </div>
    </article>
  );
}
```

Tailwind breakpoint reference:
- No prefix: 0px+ (mobile first -- this is the BASE)
- `sm:` -- 640px+ (large phones, small tablets)
- `md:` -- 768px+ (tablets)
- `lg:` -- 1024px+ (desktops)
- `xl:` -- 1280px+ (wide desktops)
- `2xl:` -- 1536px+ (ultra-wide)

Key patterns:
- **Simple changes** (size, spacing, columns): responsive prefixes on the same element
- **Completely different layouts**: render both, use `hidden md:block` / `md:hidden` to show the right one
- **Mobile-first**: always start with the mobile design (no prefix), then add desktop overrides
- **Avoid JS-based detection** (useMediaQuery) for layout -- it causes hydration mismatches with SSR'''
    },
    {
        "instruction": r'''I need to implement dark mode in my React app. What is the best approach -- CSS variables, Tailwind dark mode, or a theme context?''',
        "output": r'''<think>
Dark mode implementation -- let me think about the options.

Option 1: CSS custom properties with a data attribute. Define semantic color tokens, swap them for dark mode. Works with any styling approach.

Option 2: Tailwind dark: prefix. Built into Tailwind, uses the dark: variant. Can be driven by system preference or a class/attribute on html.

Option 3: Theme context in React. Store theme in React state, pass via context, use in styled-components or inline styles.

For option 1 and 2, the theme is controlled by CSS (class or attribute on the root element). For option 3, it is controlled by React state.

Hmm, the CSS approach is better because:
- No re-render of the entire app when switching themes
- Works with SSR (no flash of wrong theme if you read from localStorage before hydration)
- No React context overhead

The React context approach causes the entire tree to re-render when the theme changes. CSS approach just swaps some variables and the browser repaints -- no React involved.

Wait, there is the flash-of-wrong-theme (FART) problem. If the user prefers dark mode but your app defaults to light, there is a flash of light theme before JavaScript loads and applies dark mode. The fix is a small inline script in the HTML head that reads localStorage and sets the data attribute BEFORE the page renders.

I initially thought Tailwind dark: was the obvious choice for Tailwind projects, but it depends on the strategy. Tailwind supports two modes:
1. media strategy: follows system preference (prefers-color-scheme)
2. class/selector strategy: controlled by a class on html element

For apps where users can toggle dark mode (not just follow system), the class strategy is needed.

The tradeoff: system-preference-only (media strategy) is zero JS but users cannot override it. Class strategy requires a small amount of JS to read/set the preference but gives user control.

Let me recommend the class strategy with CSS custom properties for the most flexible approach.
</think>

Use CSS custom properties with a class/attribute toggle on the HTML element. This avoids re-rendering React and prevents the flash of wrong theme.

```tsx
// Step 1: Anti-flash script in your HTML head
// This runs BEFORE React hydrates, preventing light flash for dark mode users
// In Next.js: app/layout.tsx or pages/_document.tsx
// In plain React: public/index.html

function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: `
          (function() {
            var theme = localStorage.getItem('theme');
            if (theme === 'dark' || (!theme && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
              document.documentElement.classList.add('dark');
            }
          })();
        `}} />
      </head>
      <body>{children}</body>
    </html>
  );
}
```

```css
/* Step 2: Define light/dark tokens with CSS custom properties */
/* globals.css */
:root {
  --color-bg: #ffffff;
  --color-bg-secondary: #f8fafc;
  --color-text: #0f172a;
  --color-text-muted: #64748b;
  --color-border: #e2e8f0;
  --color-primary: #3b82f6;
  --color-primary-hover: #2563eb;
  --color-card-bg: #ffffff;
  --color-card-shadow: rgba(0, 0, 0, 0.05);
}

.dark {
  --color-bg: #0f172a;
  --color-bg-secondary: #1e293b;
  --color-text: #f1f5f9;
  --color-text-muted: #94a3b8;
  --color-border: #334155;
  --color-primary: #60a5fa;
  --color-primary-hover: #93bbfd;
  --color-card-bg: #1e293b;
  --color-card-shadow: rgba(0, 0, 0, 0.3);
}

body {
  background-color: var(--color-bg);
  color: var(--color-text);
  transition: background-color 0.2s ease, color 0.2s ease;
}
```

```tsx
// Step 3: Theme toggle component
'use client';

import { useState, useEffect } from 'react';

type Theme = 'light' | 'dark' | 'system';

function useTheme() {
  const [theme, setTheme] = useState<Theme>('system');

  useEffect(() => {
    const stored = localStorage.getItem('theme') as Theme | null;
    if (stored) setTheme(stored);
  }, []);

  useEffect(() => {
    const root = document.documentElement;

    if (theme === 'system') {
      localStorage.removeItem('theme');
      const prefersDark = window.matchMedia(
        '(prefers-color-scheme: dark)'
      ).matches;
      root.classList.toggle('dark', prefersDark);
    } else {
      localStorage.setItem('theme', theme);
      root.classList.toggle('dark', theme === 'dark');
    }
  }, [theme]);

  return { theme, setTheme };
}

function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  return (
    <select
      value={theme}
      onChange={e => setTheme(e.target.value as Theme)}
      aria-label="Color theme"
      className="rounded border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-1"
    >
      <option value="light">Light</option>
      <option value="dark">Dark</option>
      <option value="system">System</option>
    </select>
  );
}
```

```tsx
// Step 4: Components automatically use tokens -- no theme prop needed
function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{
      background: 'var(--color-card-bg)',
      border: '1px solid var(--color-border)',
      borderRadius: 12,
      padding: 24,
      boxShadow: '0 2px 8px var(--color-card-shadow)',
    }}>
      <h3 style={{ color: 'var(--color-text)' }}>{title}</h3>
      <p style={{ color: 'var(--color-text-muted)' }}>{children}</p>
    </div>
  );
}
// This Card works in BOTH light and dark mode without any props or context
```

Why this beats a React context approach:
- **No re-render** -- switching themes changes a CSS class, not React state. Zero component re-renders.
- **No flash** -- the inline script sets the theme before React loads
- **No context provider** -- no wrapping the app in ThemeProvider
- **Works with SSR** -- the script runs before hydration
- **Works with any styling** -- CSS Modules, Tailwind, inline styles, all reference the same variables'''
    },
]
