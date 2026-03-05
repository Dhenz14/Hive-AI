"""CSS — Grid, Flexbox, container queries, and modern layout patterns."""

PAIRS = [
    (
        "frontend/css-grid",
        "Show CSS Grid patterns: template areas, auto-fit/auto-fill, subgrid, and responsive layouts without media queries.",
        """CSS Grid layout patterns:

```css
/* --- Grid template areas (named layout) --- */

.dashboard {
  display: grid;
  grid-template-areas:
    "header  header  header"
    "sidebar content aside"
    "footer  footer  footer";
  grid-template-columns: 250px 1fr 200px;
  grid-template-rows: auto 1fr auto;
  min-height: 100vh;
  gap: 1rem;
}

.header  { grid-area: header; }
.sidebar { grid-area: sidebar; }
.content { grid-area: content; }
.aside   { grid-area: aside; }
.footer  { grid-area: footer; }

/* Responsive: stack on mobile */
@media (max-width: 768px) {
  .dashboard {
    grid-template-areas:
      "header"
      "content"
      "sidebar"
      "aside"
      "footer";
    grid-template-columns: 1fr;
  }
}


/* --- auto-fit / auto-fill (responsive without media queries) --- */

.card-grid {
  display: grid;
  /* auto-fit: stretches items to fill row */
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1.5rem;
}

/* auto-fill: keeps empty tracks (doesn't stretch) */
.gallery {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 1rem;
}


/* --- Subgrid (align nested grids to parent) --- */

.product-card {
  display: grid;
  grid-template-rows: subgrid;  /* Inherit parent's row tracks */
  grid-row: span 3;            /* Span 3 rows of parent grid */
}

/* Parent grid */
.product-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  grid-template-rows: auto 1fr auto;  /* image, description, price */
  grid-auto-rows: auto 1fr auto;      /* Repeat pattern */
  gap: 1rem;
}


/* --- Overlapping grid items --- */

.hero {
  display: grid;
  grid-template: 1fr / 1fr;  /* Single cell */
}

.hero > * {
  grid-area: 1 / 1;  /* All items overlap */
}

.hero-image {
  z-index: 1;
}

.hero-overlay {
  z-index: 2;
  background: linear-gradient(transparent, rgba(0,0,0,0.7));
  align-self: end;
  padding: 2rem;
  color: white;
}


/* --- Dense packing (fill gaps) --- */

.masonry-like {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  grid-auto-flow: dense;  /* Fill holes left by large items */
  gap: 1rem;
}

.masonry-like .wide { grid-column: span 2; }
.masonry-like .tall { grid-row: span 2; }


/* --- Container queries (component-level responsive) --- */

.card-container {
  container-type: inline-size;
  container-name: card;
}

@container card (min-width: 400px) {
  .card {
    display: grid;
    grid-template-columns: 200px 1fr;
    gap: 1rem;
  }
}

@container card (max-width: 399px) {
  .card {
    display: flex;
    flex-direction: column;
  }
  .card img {
    width: 100%;
    aspect-ratio: 16 / 9;
    object-fit: cover;
  }
}
```

CSS Grid patterns:
1. **`grid-template-areas`** — named regions for readable layout definitions
2. **`repeat(auto-fit, minmax(...))`** — responsive columns without media queries
3. **`subgrid`** — align nested grid children to parent track lines
4. **`grid-auto-flow: dense`** — fill gaps in masonry-like layouts
5. **Container queries** — component-level responsive design, independent of viewport"""
    ),
    (
        "frontend/css-flexbox",
        "Show advanced CSS Flexbox patterns: centering, sticky footer, holy grail layout, and responsive patterns.",
        """Advanced CSS Flexbox patterns:

```css
/* --- Perfect centering --- */

.center-all {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
}


/* --- Sticky footer (footer at bottom even with little content) --- */

body {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  margin: 0;
}

main {
  flex: 1;  /* Push footer down */
}

footer {
  flex-shrink: 0;
}


/* --- Holy grail layout --- */

.holy-grail {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.holy-grail .middle {
  display: flex;
  flex: 1;
}

.holy-grail .sidebar { flex: 0 0 250px; }
.holy-grail .content { flex: 1; }
.holy-grail .aside   { flex: 0 0 200px; }

@media (max-width: 768px) {
  .holy-grail .middle { flex-direction: column; }
  .holy-grail .sidebar,
  .holy-grail .aside { flex: 0 0 auto; }
}


/* --- Responsive navbar --- */

.navbar {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem 1.5rem;
}

.navbar .logo { flex-shrink: 0; }

.navbar .nav-links {
  display: flex;
  gap: 1rem;
  margin-left: auto;  /* Push to right */
}

.navbar .actions {
  display: flex;
  gap: 0.5rem;
  flex-shrink: 0;
}


/* --- Equal-height cards --- */

.card-row {
  display: flex;
  gap: 1rem;
}

.card-row .card {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.card-row .card .body { flex: 1; }
.card-row .card .footer { margin-top: auto; }


/* --- Responsive wrapping tags/chips --- */

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.tag {
  flex: 0 0 auto;
  padding: 0.25rem 0.75rem;
  border-radius: 999px;
  background: #e2e8f0;
  font-size: 0.875rem;
}


/* --- Truncated text with flex --- */

.list-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  min-width: 0;  /* Allow flex child to shrink below content size */
}

.list-item .text {
  flex: 1;
  min-width: 0;  /* Required for text-overflow to work */
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.list-item .actions {
  flex-shrink: 0;
}


/* --- Responsive: flex to stack --- */

.flex-responsive {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
}

.flex-responsive > * {
  flex: 1 1 300px;  /* Grow, shrink, basis 300px — wraps naturally */
}
```

Flexbox patterns:
1. **`flex: 1`** — fill available space (sticky footer, holy grail content area)
2. **`margin-left: auto`** — push items to the right in a flex row
3. **`min-width: 0`** — enable text truncation inside flex children
4. **`flex: 1 1 300px`** — responsive wrapping without media queries
5. **`flex-direction: column`** — vertical layouts with `flex: 1` for main content"""
    ),
    (
        "frontend/css-modern",
        "Show modern CSS features: custom properties, cascade layers, :has() selector, and logical properties.",
        """Modern CSS features:

```css
/* --- Custom properties (design tokens) --- */

:root {
  /* Colors */
  --color-primary: #3b82f6;
  --color-primary-hover: #2563eb;
  --color-surface: #ffffff;
  --color-text: #1e293b;
  --color-muted: #64748b;

  /* Spacing scale */
  --space-xs: 0.25rem;
  --space-sm: 0.5rem;
  --space-md: 1rem;
  --space-lg: 1.5rem;
  --space-xl: 2rem;

  /* Typography */
  --font-sans: system-ui, -apple-system, sans-serif;
  --font-mono: 'JetBrains Mono', monospace;

  /* Shadows */
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
  --shadow-md: 0 4px 6px rgba(0,0,0,0.1);
}

/* Dark mode via custom properties */
[data-theme="dark"] {
  --color-surface: #0f172a;
  --color-text: #e2e8f0;
  --color-muted: #94a3b8;
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.3);
}

/* Automatic dark mode */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme]) {
    --color-surface: #0f172a;
    --color-text: #e2e8f0;
  }
}


/* --- Cascade layers (control specificity order) --- */

@layer reset, base, components, utilities;

@layer reset {
  *, *::before, *::after { box-sizing: border-box; margin: 0; }
  img { display: block; max-width: 100%; }
}

@layer base {
  body {
    font-family: var(--font-sans);
    color: var(--color-text);
    background: var(--color-surface);
    line-height: 1.6;
  }
}

@layer components {
  .btn {
    padding: var(--space-sm) var(--space-md);
    border-radius: 0.375rem;
    font-weight: 500;
    cursor: pointer;
  }
  .btn-primary {
    background: var(--color-primary);
    color: white;
  }
}

@layer utilities {
  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0,0,0,0);
  }
}


/* --- :has() selector (parent selector) --- */

/* Style form group when input is focused */
.form-group:has(input:focus) {
  border-color: var(--color-primary);
}

/* Style card differently when it has an image */
.card:has(img) {
  grid-template-rows: 200px 1fr;
}

.card:not(:has(img)) {
  padding-top: var(--space-lg);
}

/* Highlight nav link when its dropdown is open */
.nav-item:has(.dropdown:target) .nav-link {
  color: var(--color-primary);
}

/* Style table row when checkbox is checked */
tr:has(input[type="checkbox"]:checked) {
  background: #eff6ff;
}


/* --- Logical properties (RTL/LTR support) --- */

.card {
  /* Instead of margin-left/margin-right */
  margin-inline: auto;
  /* Instead of padding-left/padding-right */
  padding-inline: var(--space-md);
  /* Instead of padding-top/padding-bottom */
  padding-block: var(--space-lg);
  /* Instead of max-width */
  max-inline-size: 60ch;
  /* Instead of border-left */
  border-inline-start: 3px solid var(--color-primary);
}


/* --- Color-mix and relative colors --- */

.btn-primary:hover {
  /* Mix with black for darker shade */
  background: color-mix(in srgb, var(--color-primary) 80%, black);
}

.btn-primary:active {
  background: color-mix(in srgb, var(--color-primary) 70%, black);
}


/* --- Scroll-driven animations --- */

@keyframes fade-in {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

.animate-on-scroll {
  animation: fade-in linear both;
  animation-timeline: view();
  animation-range: entry 0% entry 100%;
}
```

Modern CSS patterns:
1. **Custom properties** — design tokens with dark mode via `[data-theme]` or `prefers-color-scheme`
2. **`@layer`** — cascade layers control specificity order (reset < base < components < utilities)
3. **`:has()`** — parent selector enables conditional styling based on children state
4. **Logical properties** — `margin-inline`, `padding-block` for automatic RTL support
5. **`color-mix()`** — derive hover/active shades from a single token color"""
    ),
]
