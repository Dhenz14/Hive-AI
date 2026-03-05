"""Modern CSS 2025 — cascade layers, container queries, anchor positioning."""

PAIRS = [
    (
        "frontend/css-cascade-layers",
        "Explain CSS cascade layers (@layer) with practical examples for managing specificity across resets, frameworks, and application styles.",
        '''CSS cascade layers (`@layer`) give you explicit control over the cascade order, making specificity conflicts a thing of the past. Styles in earlier-declared layers are always overridden by later layers, regardless of selector specificity.

```css
/* --- Declaring layer order (must come first) --- */

/* Explicit order: resets < base < components < utilities */
@layer reset, base, components, utilities;

/* Styles in 'utilities' ALWAYS beat 'components',
   even if the component selector has higher specificity */


/* --- Reset layer (lowest priority) --- */
@layer reset {
  *,
  *::before,
  *::after {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
  }

  html {
    line-height: 1.5;
    -webkit-text-size-adjust: 100%;
    font-family: system-ui, sans-serif;
  }

  img, video, svg {
    display: block;
    max-width: 100%;
    height: auto;
  }

  button, input, textarea, select {
    font: inherit;
    color: inherit;
  }
}


/* --- Base layer (design tokens + typography) --- */
@layer base {
  :root {
    --color-primary: #3b82f6;
    --color-primary-hover: #2563eb;
    --color-surface: #ffffff;
    --color-text: #1f2937;
    --color-border: #e5e7eb;
    --radius-sm: 4px;
    --radius-md: 8px;
    --radius-lg: 16px;
    --shadow-sm: 0 1px 2px rgb(0 0 0 / 0.05);
    --shadow-md: 0 4px 6px rgb(0 0 0 / 0.1);
  }

  body {
    color: var(--color-text);
    background: var(--color-surface);
  }

  h1, h2, h3, h4, h5, h6 {
    text-wrap: balance;
    overflow-wrap: break-word;
  }

  a {
    color: var(--color-primary);
    text-decoration: none;
  }
  a:hover {
    text-decoration: underline;
  }
}


/* --- Component layer --- */
@layer components {
  .card {
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    padding: 1.5rem;
    box-shadow: var(--shadow-sm);
  }

  .btn {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    border-radius: var(--radius-sm);
    font-weight: 500;
    cursor: pointer;
    transition: background-color 0.15s;
  }

  .btn--primary {
    background: var(--color-primary);
    color: white;
  }

  .btn--primary:hover {
    background: var(--color-primary-hover);
  }

  /* Even though this has high specificity (0,2,0),
     it can still be overridden by the utilities layer */
  .card .btn--primary {
    border: 2px solid transparent;
  }
}


/* --- Utilities layer (highest priority) --- */
@layer utilities {
  /* Simple selectors that ALWAYS win over components */
  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }

  .hidden { display: none; }
  .text-center { text-align: center; }
  .mt-4 { margin-top: 1rem; }
  .p-4 { padding: 1rem; }
}
```

```css
/* --- Importing third-party CSS into a layer --- */

/* Tailwind or Bootstrap goes into a low-priority layer */
@import url('https://cdn.tailwindcss.com/base.css') layer(framework);
@import url('https://cdn.tailwindcss.com/components.css') layer(framework);
@import url('https://cdn.tailwindcss.com/utilities.css') layer(framework);

/* Now your styles always override the framework */
@layer framework, app;

@layer app {
  /* This beats any Tailwind selector, regardless of specificity */
  .custom-header {
    background: navy;
    color: white;
  }
}


/* --- Nested (sub) layers --- */
@layer components {
  @layer card {
    .card { padding: 1rem; }
  }
  @layer button {
    .btn { padding: 0.5rem 1rem; }
  }
}

/* Reference nested layers: components.card, components.button */
@layer components.card {
  .card--featured {
    border-color: gold;
  }
}
```

```css
/* --- Unlayered styles beat all layers --- */

/*
  Cascade order (weakest to strongest):
  1. @layer reset       (declared first)
  2. @layer base
  3. @layer components
  4. @layer utilities   (declared last)
  5. Unlayered styles   (always win over any layer)
*/

/* Unlayered — ultimate override */
.emergency-banner {
  background: red !important;
  color: white !important;
}

/* --- Dark mode with layers --- */
@layer base {
  @media (prefers-color-scheme: dark) {
    :root {
      --color-surface: #111827;
      --color-text: #f9fafb;
      --color-border: #374151;
      --color-primary: #60a5fa;
      --color-primary-hover: #93c5fd;
    }
  }
}

/* --- Checking layer support --- */
@supports at-rule(@layer) {
  /* Modern browsers — use layered architecture */
}
```

| Cascade Level | Specificity Matters? | Example |
|---|---|---|
| `@layer reset` | Within this layer only | `*, ::before, ::after {}` |
| `@layer base` | Within this layer only | `:root`, `body`, `a` |
| `@layer components` | Within this layer only | `.card`, `.btn--primary` |
| `@layer utilities` | Within this layer only | `.hidden`, `.text-center` |
| Unlayered styles | Yes (normal cascade) | Any CSS not in a `@layer` |
| `!important` in layers | Reversed order! | `@layer reset !important` wins over `utilities !important` |

Key patterns:
1. Declare layer order upfront: `@layer reset, base, components, utilities;`
2. Later layers always beat earlier layers, regardless of specificity
3. Import third-party CSS into a named layer so your styles always win
4. Unlayered styles beat all layers — use for emergency overrides only
5. `!important` reverses layer order (reset `!important` > utilities `!important`)
6. Nested layers with `@layer parent.child` for component library organization
7. Combine with CSS custom properties for a complete design system architecture'''
    ),
    (
        "frontend/css-container-queries",
        "Demonstrate CSS container queries for responsive component-level design including size queries, style queries, and practical layout patterns.",
        '''Container queries let components respond to their container\'s size rather than the viewport, enabling truly reusable responsive components.

```css
/* --- Container query fundamentals --- */

/* 1. Define a containment context */
.card-grid {
  container-type: inline-size;   /* track inline (width) size */
  container-name: card-grid;     /* optional name for targeting */
}

/* Shorthand */
.sidebar {
  container: sidebar / inline-size;
  /* name: sidebar, type: inline-size */
}

/* 2. Query the container */
@container card-grid (min-width: 600px) {
  .card {
    display: grid;
    grid-template-columns: 200px 1fr;
    gap: 1rem;
  }
}

@container card-grid (min-width: 900px) {
  .card {
    grid-template-columns: 250px 1fr 150px;
  }
}

/* Without a name — queries the nearest ancestor container */
@container (min-width: 400px) {
  .card-title {
    font-size: 1.5rem;
  }
}

/* Container query units */
.card-title {
  /* cqi = 1% of container inline size */
  font-size: clamp(1rem, 3cqi, 2rem);
}

/*
  Container query units:
  cqw — container query width (1% of container width)
  cqh — container query height
  cqi — container query inline size
  cqb — container query block size
  cqmin — min(cqi, cqb)
  cqmax — max(cqi, cqb)
*/
```

```css
/* --- Responsive card component --- */

.card-container {
  container: card / inline-size;
}

/* Default: stacked (mobile-like) */
.card {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: 8px;
  overflow: hidden;
}

.card__image {
  aspect-ratio: 16 / 9;
  object-fit: cover;
  width: 100%;
}

.card__body {
  padding: 1rem;
}

.card__actions {
  display: flex;
  gap: 0.5rem;
  padding: 0 1rem 1rem;
}

/* Medium: horizontal layout */
@container card (min-width: 500px) {
  .card {
    flex-direction: row;
  }

  .card__image {
    width: 200px;
    aspect-ratio: 1;
    flex-shrink: 0;
  }

  .card__body {
    flex: 1;
  }

  .card__actions {
    flex-direction: column;
    justify-content: center;
    padding: 1rem;
  }
}

/* Large: enhanced layout with metadata sidebar */
@container card (min-width: 800px) {
  .card {
    display: grid;
    grid-template-columns: 250px 1fr auto;
    grid-template-rows: 1fr auto;
  }

  .card__image {
    width: 100%;
    height: 100%;
    grid-row: 1 / -1;
  }

  .card__body {
    padding: 1.5rem;
  }

  .card__title {
    font-size: 1.5rem;
  }

  .card__actions {
    flex-direction: row;
    align-self: end;
    padding: 0 1.5rem 1.5rem;
    grid-column: 2 / -1;
  }
}
```

```css
/* --- Style queries (query custom property values) --- */

/* Style queries let you conditionally apply styles based on
   the computed value of custom properties on the container */

.theme-region {
  container-type: normal;  /* no size containment needed */
}

/* Query a custom property value */
@container style(--theme: dark) {
  .card {
    background: #1f2937;
    color: #f9fafb;
    border-color: #374151;
  }

  .btn {
    background: #3b82f6;
    color: white;
  }
}

@container style(--theme: brand) {
  .card {
    background: linear-gradient(135deg, #667eea, #764ba2);
    color: white;
    border: none;
  }
}

/* Usage in HTML:
   <div class="theme-region" style="--theme: dark">
     <div class="card">...</div>
   </div>
*/


/* --- Practical dashboard layout --- */

.dashboard {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 1rem;
}

.widget {
  container: widget / inline-size;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 1rem;
}

/* Chart widget adapts to available space */
@container widget (max-width: 350px) {
  .chart-legend {
    display: none;  /* hide legend when widget is small */
  }
  .chart-canvas {
    aspect-ratio: 1;
  }
}

@container widget (min-width: 351px) and (max-width: 600px) {
  .chart-legend {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    font-size: 0.75rem;
  }
}

@container widget (min-width: 601px) {
  .chart-wrapper {
    display: grid;
    grid-template-columns: 1fr 200px;
  }
  .chart-legend {
    flex-direction: column;
    border-left: 1px solid var(--color-border);
    padding-left: 1rem;
  }
}
```

| Feature | Media Query | Container Query |
|---|---|---|
| Responds to | Viewport size | Container size |
| Scope | Global | Component-level |
| Reusable components | No (viewport-dependent) | Yes (context-independent) |
| Units | `vw`, `vh`, `vmin`, `vmax` | `cqw`, `cqh`, `cqi`, `cqb` |
| Style queries | Not available | `@container style(--prop: val)` |
| Browser support | Universal | Chrome 105+, Safari 16+, Firefox 110+ |
| Containment needed | No | `container-type: inline-size` |

Key patterns:
1. Set `container-type: inline-size` on the parent, query from children
2. Use `container-name` when you have nested containers to avoid ambiguity
3. Container query units (`cqi`, `cqw`) for fluid typography and spacing
4. Style queries (`@container style(--x: y)`) for theme-based variants
5. Combine with CSS Grid `auto-fit` for fully responsive dashboard layouts
6. Never set `container-type` on the element you are styling (it creates a new context)
7. Progressive enhancement: use `@supports (container-type: inline-size)` for fallbacks'''
    ),
    (
        "frontend/css-anchor-positioning",
        "Show CSS anchor positioning for tooltips, popovers, and dropdown menus without JavaScript positioning libraries.",
        '''CSS anchor positioning connects a floating element to an anchor element declaratively, replacing JavaScript positioning libraries like Floating UI / Popper.

```css
/* --- Basic anchor positioning --- */

/* 1. Define an anchor */
.trigger {
  anchor-name: --tooltip-anchor;
}

/* 2. Position a floating element relative to the anchor */
.tooltip {
  /* Fixed/absolute positioning required */
  position: fixed;
  position-anchor: --tooltip-anchor;

  /* Place tooltip above the anchor, centered horizontally */
  top: anchor(top);
  left: anchor(center);
  translate: -50% calc(-100% - 8px);  /* offset above with gap */

  /* Sizing constraint: don't exceed viewport */
  max-width: 300px;

  /* Styling */
  background: #1f2937;
  color: white;
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  font-size: 0.875rem;
  filter: drop-shadow(0 4px 6px rgb(0 0 0 / 0.1));

  /* Hide by default */
  display: none;
}

/* Show on hover/focus */
.trigger:hover + .tooltip,
.trigger:focus-visible + .tooltip {
  display: block;
}
```

```css
/* --- anchor() function positions --- */

/*
  anchor() takes a side of the anchor element:
  - anchor(top)     — top edge of anchor
  - anchor(bottom)  — bottom edge
  - anchor(left)    — left edge
  - anchor(right)   — right edge
  - anchor(center)  — center of anchor (vertical or horizontal)
  - anchor(start)   — logical start
  - anchor(end)     — logical end

  Used in inset properties: top, right, bottom, left,
  inset-block-start, inset-inline-end, etc.
*/

/* Dropdown below anchor, left-aligned */
.dropdown-trigger {
  anchor-name: --dropdown;
}

.dropdown-menu {
  position: fixed;
  position-anchor: --dropdown;

  top: anchor(bottom);
  left: anchor(left);
  margin-top: 4px;

  /* Auto-flip with position-try-fallbacks */
  position-try-fallbacks:
    --above,       /* custom @position-try */
    flip-block,    /* built-in: flip vertical */
    flip-inline;   /* built-in: flip horizontal */

  min-width: anchor-size(width);  /* at least as wide as trigger */
  max-height: 300px;
  overflow-y: auto;

  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  box-shadow: 0 10px 25px rgb(0 0 0 / 0.15);
}

/* Custom fallback position: above the anchor */
@position-try --above {
  top: auto;
  bottom: anchor(top);
  margin-top: 0;
  margin-bottom: 4px;
}

/* Custom fallback: to the right */
@position-try --right {
  top: anchor(top);
  left: anchor(right);
  margin-top: 0;
  margin-left: 4px;
}


/* --- Popover with anchor positioning --- */

.popover-trigger {
  anchor-name: --popover;
}

/* Combine with Popover API */
.popover-content {
  position: fixed;
  position-anchor: --popover;

  /* Position to the right of trigger */
  top: anchor(center);
  left: anchor(right);
  translate: 8px -50%;

  /* Allow viewport-aware repositioning */
  position-try-fallbacks: flip-inline, flip-block, flip-block flip-inline;

  /* Popover API attributes */
  &:popover-open {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 1rem;
  width: 280px;
  box-shadow: 0 20px 60px rgb(0 0 0 / 0.15);
}
```

```css
/* --- anchor-size() for coordinated sizing --- */

.select-trigger {
  anchor-name: --select;
  width: 200px;
}

.select-dropdown {
  position: fixed;
  position-anchor: --select;

  /* Match the trigger width exactly */
  width: anchor-size(width);

  top: anchor(bottom);
  left: anchor(left);
  margin-top: 2px;
}


/* --- Multiple anchors (connecting elements) --- */

.step-1 { anchor-name: --step1; }
.step-2 { anchor-name: --step2; }
.step-3 { anchor-name: --step3; }

/* Line connecting step 1 to step 2 */
.connector-1-2 {
  position: fixed;
  top: anchor(--step1, bottom);
  left: anchor(--step1, center);
  bottom: anchor(--step2, top);
  width: 2px;
  background: var(--color-primary);
}


/* --- Practical: notification badge on avatar --- */

.avatar {
  anchor-name: --avatar;
  position: relative;
}

.notification-badge {
  position: fixed;
  position-anchor: --avatar;

  /* Top-right corner of avatar */
  bottom: anchor(top);
  left: anchor(right);
  translate: -50% 50%;

  min-width: 18px;
  height: 18px;
  display: grid;
  place-content: center;
  background: #ef4444;
  color: white;
  font-size: 0.7rem;
  font-weight: 700;
  border-radius: 9999px;
  padding: 0 4px;
}


/* --- Feature detection --- */
@supports (anchor-name: --x) {
  /* Use anchor positioning */
}

@supports not (anchor-name: --x) {
  /* Fallback: traditional absolute positioning */
  .tooltip {
    position: absolute;
    bottom: 100%;
    left: 50%;
    transform: translateX(-50%);
  }
}
```

| Feature | CSS Anchor Positioning | Floating UI (JS) | CSS `position: absolute` |
|---|---|---|---|
| Positioning logic | Declarative CSS | Imperative JS | Manual offsets |
| Viewport flipping | `position-try-fallbacks` | `flip` middleware | Not built-in |
| Size coordination | `anchor-size()` | Manual measurement | Manual |
| Performance | Browser-native | Layout thrashing possible | Good |
| Multiple anchors | Named anchors | One reference per float | One parent |
| Scroll handling | Automatic | `autoUpdate` listener | Breaks on scroll |
| Browser support | Chrome 125+ (partial) | Universal (polyfill) | Universal |

Key patterns:
1. `anchor-name: --name` on the anchor, `position-anchor: --name` on the floating element
2. `anchor(top|right|bottom|left|center)` positions relative to anchor edges
3. `position-try-fallbacks: flip-block, flip-inline` for viewport-aware repositioning
4. Custom fallbacks with `@position-try` for specific alternative placements
5. `anchor-size(width|height)` to match the floating element to anchor dimensions
6. Combine with Popover API (`:popover-open`) for accessible show/hide behavior
7. Always provide `@supports` fallback for browsers without anchor positioning support'''
    ),
    (
        "frontend/css-nesting-has",
        "Demonstrate CSS nesting and the :has() relational selector with real-world UI patterns.",
        '''CSS nesting and `:has()` together enable powerful parent-aware styling directly in CSS, eliminating the need for preprocessors like Sass for most use cases.

```css
/* --- CSS Nesting (native) --- */

/* Basic nesting with & */
.card {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 1rem;
  transition: box-shadow 0.2s;

  /* Equivalent to .card:hover */
  &:hover {
    box-shadow: 0 4px 12px rgb(0 0 0 / 0.1);
  }

  /* Equivalent to .card .card__title */
  & .card__title {
    font-size: 1.25rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
  }

  /* Equivalent to .card .card__body */
  & .card__body {
    color: #6b7280;
    line-height: 1.6;
  }

  /* Equivalent to .card .card__footer */
  & .card__footer {
    display: flex;
    gap: 0.5rem;
    margin-top: 1rem;
    padding-top: 1rem;
    border-top: 1px solid #e5e7eb;
  }

  /* Media query nesting */
  @media (min-width: 768px) {
    padding: 1.5rem;

    & .card__title {
      font-size: 1.5rem;
    }
  }

  /* Container query nesting */
  @container (min-width: 500px) {
    display: grid;
    grid-template-columns: 200px 1fr;
  }
}


/* Nesting with combinators */
.nav {
  display: flex;
  gap: 0.5rem;

  /* .nav > .nav-item */
  & > .nav-item {
    padding: 0.5rem 1rem;

    /* .nav > .nav-item:first-child */
    &:first-child {
      padding-left: 0;
    }

    /* .nav > .nav-item + .nav-item */
    & + .nav-item {
      border-left: 1px solid #e5e7eb;
    }
  }

  /* .nav.nav--vertical */
  &.nav--vertical {
    flex-direction: column;

    & > .nav-item + .nav-item {
      border-left: none;
      border-top: 1px solid #e5e7eb;
    }
  }
}
```

```css
/* --- :has() relational selector --- */

/* :has() selects an element based on its descendants */

/* Card that contains an image — add different layout */
.card:has(img) {
  display: grid;
  grid-template-rows: 200px 1fr;
}

/* Card WITHOUT an image */
.card:not(:has(img)) {
  padding: 2rem;
}

/* Form group that has an invalid input */
.form-group:has(input:invalid) {
  /* Highlight the entire group */
  & label {
    color: #dc2626;
  }

  & .help-text {
    display: none;
  }

  & .error-text {
    display: block;
    color: #dc2626;
    font-size: 0.875rem;
  }
}

/* Form group with a focused input */
.form-group:has(input:focus-visible) {
  & label {
    color: var(--color-primary);
    font-weight: 600;
  }
}


/* Selecting previous siblings (impossible before :has()) */

/* Style a label when its NEXT sibling input is focused */
label:has(+ input:focus-visible) {
  color: var(--color-primary);
  transform: translateY(-2px);
}

/* Style a heading when the next paragraph is empty */
h2:has(+ p:empty) {
  margin-bottom: 0;
}
```

```css
/* --- Practical UI patterns with nesting + :has() --- */

/* 1. Auto-adjusting page layout */
body:has(.sidebar) {
  .main-content {
    /* Sidebar exists — adjust grid */
    display: grid;
    grid-template-columns: 250px 1fr;
  }
}

body:not(:has(.sidebar)) {
  .main-content {
    max-width: 80ch;
    margin-inline: auto;
  }
}


/* 2. Quantity queries — style based on child count */
.tag-list:has(> :nth-child(5)) {
  /* More than 4 tags — wrap and use smaller size */
  flex-wrap: wrap;

  & .tag {
    font-size: 0.75rem;
    padding: 0.125rem 0.5rem;
  }
}


/* 3. Interactive table rows */
.data-table {
  width: 100%;
  border-collapse: collapse;

  & tr {
    border-bottom: 1px solid #e5e7eb;
    transition: background-color 0.1s;

    &:hover {
      background: #f9fafb;
    }

    /* Row with a checked checkbox */
    &:has(input[type="checkbox"]:checked) {
      background: #eff6ff;

      & td {
        color: #1d4ed8;
      }
    }
  }

  & th {
    text-align: left;
    padding: 0.75rem 1rem;
    font-weight: 600;
    background: #f9fafb;
  }

  & td {
    padding: 0.75rem 1rem;
  }
}


/* 4. Conditional dark mode */
html:has(#dark-mode-toggle:checked) {
  --color-surface: #111827;
  --color-text: #f9fafb;
  --color-border: #374151;
  color-scheme: dark;
}


/* 5. Empty state handling */
.list:has(> *) {
  /* Has children — normal display */
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.list:not(:has(> *)) {
  /* Empty list — show placeholder */
  &::after {
    content: "No items to display";
    display: block;
    text-align: center;
    padding: 2rem;
    color: #9ca3af;
    font-style: italic;
  }
}


/* 6. Responsive nav with nesting */
.header {
  display: flex;
  align-items: center;
  padding: 1rem;

  & .logo {
    font-weight: 700;
    font-size: 1.25rem;
  }

  & nav {
    margin-left: auto;
    display: flex;
    gap: 1rem;

    @media (max-width: 768px) {
      display: none;

      &.open {
        display: flex;
        flex-direction: column;
        position: absolute;
        top: 100%;
        left: 0;
        right: 0;
        background: white;
        padding: 1rem;
        box-shadow: 0 4px 12px rgb(0 0 0 / 0.1);
      }
    }
  }
}
```

| Feature | CSS Nesting | :has() Selector | Sass/SCSS |
|---|---|---|---|
| Browser support | Chrome 112+, Safari 17.2+, Firefox 117+ | Chrome 105+, Safari 15.4+, Firefox 121+ | Build step required |
| Parent selection | No | Yes (`:has()` on parent) | No |
| Previous sibling | No | Yes (`label:has(+ input:focus)`) | No |
| @media nesting | Yes | N/A | Yes |
| @container nesting | Yes | N/A | No |
| Variables | CSS custom properties | N/A | `$var` (static) |
| Build step | None | None | Required |

Key patterns:
1. Use `&` for pseudo-classes and compound selectors: `&:hover`, `&.active`
2. Use `& .child` for descendant selectors (space after `&` is significant)
3. `:has()` enables parent-aware styling: `.card:has(img)` targets cards with images
4. Combine `:has()` with `:not()` for else-like conditions
5. Previous sibling selection: `label:has(+ input:focus)` — not possible any other way
6. Nest media and container queries inside selectors for co-located responsive styles
7. `:has()` with quantity queries: `.list:has(> :nth-child(n))` for count-based styling'''
    ),
    (
        "frontend/css-scroll-animations",
        "Show CSS scroll-driven animations including scroll timelines, view timelines, and practical scroll-linked effects.",
        '''CSS scroll-driven animations bind animation progress to scroll position or element visibility, replacing JavaScript scroll listeners for smooth, performant effects.

```css
/* --- Scroll timeline (linked to scroll container) --- */

/* 1. Basic scroll-linked progress bar */
.progress-bar {
  position: fixed;
  top: 0;
  left: 0;
  height: 3px;
  background: var(--color-primary, #3b82f6);
  transform-origin: left;
  width: 100%;

  /* Animation definition */
  animation: grow-width linear;

  /* Bind to scroll timeline instead of time */
  animation-timeline: scroll();    /* nearest scroll ancestor */
  animation-range: 0% 100%;       /* full scroll range */
}

@keyframes grow-width {
  from { transform: scaleX(0); }
  to   { transform: scaleX(1); }
}


/* 2. Named scroll timeline */
.scroll-container {
  overflow-y: auto;
  height: 100vh;

  /* Define a named scroll timeline */
  scroll-timeline-name: --page-scroll;
  scroll-timeline-axis: block;    /* vertical */
}

.parallax-bg {
  animation: parallax-shift linear;
  animation-timeline: --page-scroll;
}

@keyframes parallax-shift {
  from { transform: translateY(0); }
  to   { transform: translateY(-200px); }
}


/* --- scroll() function options --- */

/*
  scroll(<scroller> <axis>)

  <scroller>:
    nearest  — nearest scroll ancestor (default)
    root     — document viewport
    self     — the element itself

  <axis>:
    block    — block direction (vertical in LTR)
    inline   — inline direction (horizontal)
    y        — vertical
    x        — horizontal
*/

.header {
  animation: shrink-header linear;
  animation-timeline: scroll(root block);
}

@keyframes shrink-header {
  from {
    padding: 2rem;
    font-size: 2rem;
  }
  to {
    padding: 0.5rem;
    font-size: 1rem;
  }
}
```

```css
/* --- View timeline (linked to element visibility) --- */

/* Animate elements as they enter/exit the viewport */
.fade-in-section {
  animation: fade-in linear both;
  animation-timeline: view();      /* this element's visibility */
  animation-range: entry 0% entry 100%;
  /* Animate from start of entering viewport to fully entered */
}

@keyframes fade-in {
  from {
    opacity: 0;
    transform: translateY(50px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}


/* Animation ranges for view() timeline:
   entry    — element enters the scroll port
   exit     — element exits the scroll port
   contain  — element fully contained in scroll port
   cover    — from first pixel visible to last pixel gone

   Each accepts 0% to 100% for sub-ranges
*/

/* Slide in from left, stay, slide out to right */
.slide-through {
  animation: slide-through linear both;
  animation-timeline: view();
}

@keyframes slide-through {
  /* Entry phase */
  entry 0% {
    opacity: 0;
    transform: translateX(-100px);
  }
  entry 100% {
    opacity: 1;
    transform: translateX(0);
  }
  /* Contain phase — fully visible */
  contain 0% {
    opacity: 1;
    transform: translateX(0);
  }
  contain 100% {
    opacity: 1;
    transform: translateX(0);
  }
  /* Exit phase */
  exit 0% {
    opacity: 1;
    transform: translateX(0);
  }
  exit 100% {
    opacity: 0;
    transform: translateX(100px);
  }
}


/* Named view timeline */
.gallery-item {
  view-timeline-name: --gallery-item;
  view-timeline-axis: block;

  & .gallery-image {
    animation: zoom-in linear both;
    animation-timeline: --gallery-item;
    animation-range: entry 0% contain 50%;
  }
}

@keyframes zoom-in {
  from { transform: scale(0.8); opacity: 0.5; }
  to   { transform: scale(1); opacity: 1; }
}
```

```css
/* --- Practical scroll animation patterns --- */

/* 1. Sticky header that shrinks on scroll */
.site-header {
  position: sticky;
  top: 0;
  z-index: 100;
  animation: compact-header linear both;
  animation-timeline: scroll(root);
  animation-range: 0px 200px;   /* animate over first 200px of scroll */
}

@keyframes compact-header {
  from {
    padding-block: 1.5rem;
    background: transparent;
    backdrop-filter: none;
  }
  to {
    padding-block: 0.5rem;
    background: rgb(255 255 255 / 0.9);
    backdrop-filter: blur(12px);
    box-shadow: 0 1px 3px rgb(0 0 0 / 0.1);
  }
}


/* 2. Horizontal scroll gallery with parallax */
.horizontal-gallery {
  display: flex;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  scroll-timeline-name: --gallery;
  scroll-timeline-axis: inline;
}

.gallery-slide {
  flex: 0 0 100%;
  scroll-snap-align: start;
  position: relative;
  overflow: hidden;

  & img {
    animation: parallax-x linear;
    animation-timeline: --gallery;
    /* Subtle parallax as you scroll horizontally */
  }
}

@keyframes parallax-x {
  from { transform: translateX(-10%); }
  to   { transform: translateX(10%); }
}


/* 3. Staggered list reveal */
.list-item {
  animation: stagger-in linear both;
  animation-timeline: view();
  animation-range: entry 0% entry 80%;
}

.list-item:nth-child(1) { animation-delay: 0ms; }
.list-item:nth-child(2) { animation-delay: 50ms; }
.list-item:nth-child(3) { animation-delay: 100ms; }
.list-item:nth-child(4) { animation-delay: 150ms; }

@keyframes stagger-in {
  from {
    opacity: 0;
    transform: translateY(30px) scale(0.95);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}


/* 4. Image reveal on scroll */
.image-reveal {
  clip-path: inset(100% 0 0 0);  /* fully clipped from bottom */
  animation: reveal-up linear both;
  animation-timeline: view();
  animation-range: entry 10% entry 90%;
}

@keyframes reveal-up {
  to {
    clip-path: inset(0 0 0 0);   /* fully revealed */
  }
}


/* 5. Feature detection */
@supports (animation-timeline: scroll()) {
  /* Use scroll-driven animations */
}

@supports not (animation-timeline: scroll()) {
  /* Fallback: use IntersectionObserver in JS or static styles */
  .fade-in-section {
    opacity: 1;
    transform: none;
  }
}
```

| Feature | Scroll Timeline | View Timeline | JS Scroll Listener |
|---|---|---|---|
| Performance | Compositor thread | Compositor thread | Main thread |
| Linked to | Scroll position | Element visibility | Manual calculation |
| Jank-free | Yes | Yes | Risk of jank |
| Range control | `animation-range` | `entry`, `exit`, `contain` | Manual |
| Named timelines | `scroll-timeline-name` | `view-timeline-name` | N/A |
| Browser support | Chrome 115+, Edge 115+ | Chrome 115+, Edge 115+ | Universal |
| Polyfill | `scroll-timeline` polyfill | `scroll-timeline` polyfill | N/A |

Key patterns:
1. `animation-timeline: scroll()` binds animation to scroll position of the nearest scroller
2. `animation-timeline: view()` binds to the element's visibility in the viewport
3. Use `animation-range: entry 0% entry 100%` for enter-only animations
4. `scroll(root block)` targets the main document scroll
5. Named timelines with `scroll-timeline-name` / `view-timeline-name` for explicit targeting
6. Always use `both` fill mode for scroll animations to hold start/end states
7. Provide `@supports` fallbacks since Safari support is still partial'''
    ),
]
