"""CSS advanced — Grid, animations, responsive design, modern CSS features."""

PAIRS = [
    (
        "css/grid-layout",
        "Show advanced CSS Grid patterns: responsive layouts, named grid areas, auto-fit/auto-fill, subgrid, and complex dashboard layouts.",
        '''Advanced CSS Grid for complex layouts:

```css
/* --- Responsive Dashboard with Named Areas --- */
.dashboard {
  display: grid;
  grid-template-areas:
    "sidebar header  header"
    "sidebar main    aside"
    "sidebar footer  footer";
  grid-template-columns: 250px 1fr 300px;
  grid-template-rows: auto 1fr auto;
  min-height: 100vh;
  gap: 1rem;
}

.dashboard-header  { grid-area: header; }
.dashboard-sidebar { grid-area: sidebar; }
.dashboard-main    { grid-area: main; }
.dashboard-aside   { grid-area: aside; }
.dashboard-footer  { grid-area: footer; }

/* Collapse to single column on mobile */
@media (max-width: 768px) {
  .dashboard {
    grid-template-areas:
      "header"
      "main"
      "aside"
      "footer";
    grid-template-columns: 1fr;
  }
  .dashboard-sidebar { display: none; }
}

/* --- Auto-fit vs Auto-fill --- */

/* auto-fill: creates empty tracks to fill the row */
.gallery-fill {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 1rem;
}

/* auto-fit: collapses empty tracks, items stretch */
.gallery-fit {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
}

/* --- Complex Card Grid with Spanning --- */
.card-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  grid-auto-rows: 200px;
  gap: 1rem;
}

/* Featured card spans 2x2 */
.card-grid .featured {
  grid-column: span 2;
  grid-row: span 2;
}

/* Wide card spans full width */
.card-grid .wide {
  grid-column: 1 / -1;
}

/* --- Subgrid (align nested grids) --- */
.card-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1.5rem;
}

.card {
  display: grid;
  grid-template-rows: subgrid;
  grid-row: span 3; /* header, body, footer */
}

.card-header { align-self: start; }
.card-body   { align-self: stretch; }
.card-footer { align-self: end; }

/* --- Masonry-like with Grid --- */
.masonry {
  columns: 3;
  column-gap: 1rem;
}

.masonry-item {
  break-inside: avoid;
  margin-bottom: 1rem;
}

/* --- Responsive table-like layout --- */
.data-grid {
  display: grid;
  grid-template-columns:
    [checkbox] 40px
    [name] 1fr
    [email] 1fr
    [role] 120px
    [actions] 100px;
  align-items: center;
}

.data-grid > * {
  padding: 0.75rem;
  border-bottom: 1px solid #e5e7eb;
}

@media (max-width: 640px) {
  .data-grid {
    grid-template-columns: 1fr;
  }
  .data-grid > *::before {
    content: attr(data-label);
    font-weight: 600;
  }
}
```

Key patterns:
1. **Named areas** — readable layout definitions, easy responsive overrides
2. **auto-fit** — items stretch to fill space; **auto-fill** — preserves empty columns
3. **Subgrid** — align nested grid children to parent tracks
4. **Spanning** — featured items span multiple tracks for visual hierarchy
5. **Grid + media queries** — restructure entire layouts at breakpoints'''
    ),
    (
        "css/animations-transitions",
        "Show CSS animation patterns: transitions, keyframe animations, scroll-driven animations, and performance-optimized motion.",
        '''CSS animation patterns from simple to advanced:

```css
/* --- Smooth Transitions --- */
.button {
  background: #3b82f6;
  color: white;
  padding: 0.75rem 1.5rem;
  border-radius: 0.5rem;
  /* Only animate specific properties for performance */
  transition:
    background-color 200ms ease,
    transform 150ms ease,
    box-shadow 200ms ease;
}

.button:hover {
  background: #2563eb;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4);
}

.button:active {
  transform: translateY(0);
  transition-duration: 50ms;
}

/* --- Keyframe Animations --- */
@keyframes slide-in {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.card {
  animation: slide-in 300ms ease-out both;
}

/* Staggered children */
.card:nth-child(1) { animation-delay: 0ms; }
.card:nth-child(2) { animation-delay: 100ms; }
.card:nth-child(3) { animation-delay: 200ms; }

/* --- Loading Spinner (composite-only) --- */
@keyframes spin {
  to { transform: rotate(360deg); }
}

.spinner {
  width: 24px;
  height: 24px;
  border: 3px solid #e5e7eb;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin 600ms linear infinite;
  /* GPU-accelerated: only transform + opacity */
}

/* --- Skeleton Loading --- */
@keyframes shimmer {
  0%   { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}

.skeleton {
  background: linear-gradient(
    90deg,
    #f0f0f0 25%,
    #e0e0e0 50%,
    #f0f0f0 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
  border-radius: 4px;
}

/* --- Scroll-Driven Animations (modern) --- */
@keyframes reveal {
  from { opacity: 0; transform: translateY(40px); }
  to   { opacity: 1; transform: translateY(0); }
}

.scroll-reveal {
  animation: reveal linear both;
  animation-timeline: view();
  animation-range: entry 0% entry 100%;
}

/* Progress bar tied to scroll */
.scroll-progress {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 3px;
  background: #3b82f6;
  transform-origin: left;
  animation: grow-width linear;
  animation-timeline: scroll();
}

@keyframes grow-width {
  from { transform: scaleX(0); }
  to   { transform: scaleX(1); }
}

/* --- Respecting Motion Preferences --- */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}

/* --- View Transitions API (page transitions) --- */
/* In JavaScript: document.startViewTransition(() => updateDOM()) */
::view-transition-old(root) {
  animation: fade-out 200ms ease;
}
::view-transition-new(root) {
  animation: fade-in 200ms ease;
}
```

Performance rules:
1. **Only animate `transform` and `opacity`** — these skip layout/paint (GPU composited)
2. **Use `will-change` sparingly** — hints browser to promote to own layer
3. **Prefer `transition` for state changes**, `animation` for autonomous motion
4. **Always respect `prefers-reduced-motion`** — accessibility requirement
5. **Scroll-driven animations** — replace JS scroll listeners with CSS'''
    ),
    (
        "css/modern-features",
        "Show modern CSS features: container queries, cascade layers, :has() selector, logical properties, color-mix, and CSS nesting.",
        '''Modern CSS features replacing JavaScript and preprocessors:

```css
/* --- Container Queries (component-level responsive) --- */
.card-container {
  container-type: inline-size;
  container-name: card;
}

.card {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1rem;
}

/* Card responds to its CONTAINER size, not viewport */
@container card (min-width: 400px) {
  .card {
    grid-template-columns: 150px 1fr;
  }
}

@container card (min-width: 700px) {
  .card {
    grid-template-columns: 200px 1fr auto;
  }
}

/* --- CSS Nesting (native, no preprocessor) --- */
.nav {
  display: flex;
  gap: 1rem;

  & a {
    color: #374151;
    text-decoration: none;
    padding: 0.5rem 1rem;
    border-radius: 0.25rem;

    &:hover {
      background: #f3f4f6;
      color: #111827;
    }

    &.active {
      background: #3b82f6;
      color: white;
    }
  }

  @media (max-width: 640px) {
    flex-direction: column;
  }
}

/* --- :has() Selector (parent selector!) --- */
/* Style parent based on child state */
.form-group:has(input:invalid) {
  border-color: #ef4444;
}

.form-group:has(input:invalid) .error-message {
  display: block;
}

/* Card with image gets different layout */
.card:has(img) {
  grid-template-rows: 200px auto;
}

/* Page with sidebar */
body:has(.sidebar.open) .main-content {
  margin-left: 250px;
}

/* Select with empty state */
.list:has(> :not(.placeholder):first-child) .empty-state {
  display: none;
}

/* --- Cascade Layers (control specificity) --- */
@layer reset, base, components, utilities;

@layer reset {
  *, *::before, *::after {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
  }
}

@layer base {
  body {
    font-family: system-ui, sans-serif;
    line-height: 1.5;
    color: #374151;
  }
  a { color: #3b82f6; }
}

@layer components {
  .btn { padding: 0.75rem 1.5rem; }
  .card { border: 1px solid #e5e7eb; }
}

@layer utilities {
  .sr-only { /* screen reader only */ }
  .hidden { display: none; }
}

/* Unlayered styles always win over layered */
.special { color: red; }

/* --- Logical Properties (internationalization) --- */
.card {
  /* Instead of margin-left/right */
  margin-inline: auto;
  /* Instead of padding-top/bottom */
  padding-block: 1rem;
  /* Instead of padding-left/right */
  padding-inline: 1.5rem;
  /* Instead of border-left */
  border-inline-start: 4px solid #3b82f6;
  /* Instead of width/height */
  inline-size: 100%;
  max-inline-size: 600px;
}

/* Works automatically for RTL languages */

/* --- Color Functions --- */
:root {
  --primary: #3b82f6;
  --primary-light: color-mix(in srgb, var(--primary) 30%, white);
  --primary-dark: color-mix(in srgb, var(--primary) 70%, black);
  --primary-subtle: color-mix(in srgb, var(--primary) 10%, transparent);
}

/* oklch for perceptually uniform colors */
:root {
  --blue: oklch(60% 0.2 250);
  --blue-hover: oklch(50% 0.2 250);  /* Just darken lightness */
}

/* --- Popover API (no JS needed) --- */
[popover] {
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  padding: 1rem;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.1);
}

[popover]::backdrop {
  background: rgba(0, 0, 0, 0.2);
}
```

```html
<!-- Popover (no JavaScript) -->
<button popovertarget="menu">Open Menu</button>
<div id="menu" popover>
  <nav>Menu content here</nav>
</div>
```

What replaces what:
1. **Container queries** replace JS resize observers for responsive components
2. **CSS nesting** replaces Sass/Less nesting
3. **`:has()`** replaces JS parent-selector hacks
4. **Cascade layers** replace specificity wars and `!important`
5. **Logical properties** replace LTR/RTL-specific stylesheets
6. **`color-mix()`** replaces Sass color functions'''
    ),
    (
        "css/custom-properties-theming",
        "Show CSS custom properties for theming: dark mode, design tokens, dynamic themes, and component-scoped variables.",
        '''CSS custom properties for scalable theming:

```css
/* --- Design Tokens as Custom Properties --- */
:root {
  /* Primitive tokens (raw values) */
  --color-blue-50: #eff6ff;
  --color-blue-500: #3b82f6;
  --color-blue-700: #1d4ed8;
  --color-gray-50: #f9fafb;
  --color-gray-900: #111827;
  --spacing-xs: 0.25rem;
  --spacing-sm: 0.5rem;
  --spacing-md: 1rem;
  --spacing-lg: 1.5rem;
  --spacing-xl: 2rem;
  --radius-sm: 0.25rem;
  --radius-md: 0.5rem;
  --radius-lg: 1rem;
  --font-sm: 0.875rem;
  --font-base: 1rem;
  --font-lg: 1.125rem;

  /* Semantic tokens (light theme) */
  --bg-primary: var(--color-gray-50);
  --bg-surface: white;
  --bg-elevated: white;
  --text-primary: var(--color-gray-900);
  --text-secondary: #6b7280;
  --text-inverse: white;
  --border-default: #e5e7eb;
  --accent: var(--color-blue-500);
  --accent-hover: var(--color-blue-700);
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);
  --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.07);
}

/* --- Dark Theme --- */
[data-theme="dark"] {
  --bg-primary: #0f172a;
  --bg-surface: #1e293b;
  --bg-elevated: #334155;
  --text-primary: #f1f5f9;
  --text-secondary: #94a3b8;
  --text-inverse: #0f172a;
  --border-default: #334155;
  --accent: #60a5fa;
  --accent-hover: #93bbfd;
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.3);
  --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.4);
}

/* Auto dark mode */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg-primary: #0f172a;
    --bg-surface: #1e293b;
    /* ... same dark overrides ... */
  }
}

/* --- Components use semantic tokens --- */
.card {
  background: var(--bg-surface);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: var(--spacing-lg);
  box-shadow: var(--shadow-sm);
}

.button-primary {
  background: var(--accent);
  color: var(--text-inverse);
  padding: var(--spacing-sm) var(--spacing-lg);
  border-radius: var(--radius-sm);
}

.button-primary:hover {
  background: var(--accent-hover);
}

/* --- Component-Scoped Variables --- */
.button {
  --btn-bg: var(--accent);
  --btn-color: var(--text-inverse);
  --btn-padding-x: var(--spacing-lg);
  --btn-padding-y: var(--spacing-sm);
  --btn-radius: var(--radius-sm);
  --btn-font-size: var(--font-base);

  background: var(--btn-bg);
  color: var(--btn-color);
  padding: var(--btn-padding-y) var(--btn-padding-x);
  border-radius: var(--btn-radius);
  font-size: var(--btn-font-size);
}

/* Variants override scoped vars */
.button.small {
  --btn-padding-x: var(--spacing-sm);
  --btn-padding-y: var(--spacing-xs);
  --btn-font-size: var(--font-sm);
}

.button.outline {
  --btn-bg: transparent;
  --btn-color: var(--accent);
  border: 1px solid var(--accent);
}

/* --- Dynamic Theme via JavaScript --- */
/* JS: document.documentElement.style.setProperty('--accent', '#8b5cf6') */

/* --- Responsive spacing with clamp --- */
:root {
  --space-fluid-sm: clamp(0.5rem, 1vw, 1rem);
  --space-fluid-md: clamp(1rem, 3vw, 2rem);
  --space-fluid-lg: clamp(1.5rem, 5vw, 4rem);
  --font-fluid-base: clamp(1rem, 0.5vw + 0.875rem, 1.125rem);
  --font-fluid-heading: clamp(1.5rem, 3vw + 1rem, 3rem);
}

.hero {
  padding: var(--space-fluid-lg);
  font-size: var(--font-fluid-heading);
}
```

```javascript
// Theme switcher
function setTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('theme', theme);
}

// Load saved theme or use system preference
const saved = localStorage.getItem('theme');
if (saved) {
  setTheme(saved);
} else if (matchMedia('(prefers-color-scheme: dark)').matches) {
  setTheme('dark');
}

// Listen for system changes
matchMedia('(prefers-color-scheme: dark)')
  .addEventListener('change', (e) => {
    if (!localStorage.getItem('theme')) {
      setTheme(e.matches ? 'dark' : 'light');
    }
  });
```

Architecture:
1. **Primitive tokens** — raw values (colors, sizes), never used directly in components
2. **Semantic tokens** — map primitives to purposes (bg-surface, text-primary)
3. **Component variables** — scoped defaults that variants can override
4. **`clamp()`** — fluid spacing/typography without media queries
5. **Theme switching** — change semantic tokens, all components update automatically'''
    ),
]
"""
