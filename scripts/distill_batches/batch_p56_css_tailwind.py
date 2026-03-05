"""CSS — Tailwind CSS patterns, responsive design, and component styling."""

PAIRS = [
    (
        "css/tailwind-patterns",
        "Show Tailwind CSS patterns: component styling, responsive design, dark mode, and custom utilities.",
        '''Tailwind CSS patterns:

```html
<!-- Responsive card component -->
<div class="group relative overflow-hidden rounded-lg bg-white shadow-md
            transition-all hover:shadow-xl dark:bg-gray-800">
  <!-- Image with aspect ratio -->
  <div class="aspect-video overflow-hidden">
    <img src="/product.jpg" alt="Product"
         class="h-full w-full object-cover transition-transform
                duration-300 group-hover:scale-105" />
  </div>

  <!-- Badge -->
  <span class="absolute left-3 top-3 rounded-full bg-red-500 px-2 py-1
               text-xs font-semibold text-white">Sale</span>

  <!-- Content -->
  <div class="p-4 space-y-2">
    <h3 class="text-lg font-semibold text-gray-900 dark:text-white
               line-clamp-1">Product Name</h3>
    <p class="text-sm text-gray-600 dark:text-gray-300 line-clamp-2">
      Description text that might be long...
    </p>

    <div class="flex items-center justify-between">
      <div class="flex items-center gap-2">
        <span class="text-xl font-bold text-gray-900 dark:text-white">$29.99</span>
        <span class="text-sm text-gray-500 line-through">$49.99</span>
      </div>
      <button class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium
                     text-white transition-colors hover:bg-blue-700
                     focus:outline-none focus:ring-2 focus:ring-blue-500
                     focus:ring-offset-2 active:bg-blue-800
                     disabled:cursor-not-allowed disabled:opacity-50">
        Add to Cart
      </button>
    </div>
  </div>
</div>


<!-- Responsive grid layout -->
<div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
  <!-- Cards go here -->
</div>


<!-- Responsive navigation -->
<nav class="sticky top-0 z-50 border-b bg-white/80 backdrop-blur-md dark:bg-gray-900/80">
  <div class="mx-auto flex h-16 max-w-7xl items-center justify-between px-4">
    <a href="/" class="text-xl font-bold">Logo</a>

    <!-- Desktop nav -->
    <div class="hidden items-center gap-6 md:flex">
      <a href="/products" class="text-gray-600 transition-colors hover:text-gray-900
                                  dark:text-gray-300 dark:hover:text-white">Products</a>
      <a href="/pricing" class="text-gray-600 transition-colors hover:text-gray-900">Pricing</a>
    </div>

    <!-- Mobile menu button -->
    <button class="rounded-lg p-2 md:hidden hover:bg-gray-100">
      <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M4 6h16M4 12h16M4 18h16" />
      </svg>
    </button>
  </div>
</nav>


<!-- Form with validation states -->
<div class="space-y-4">
  <div>
    <label class="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-200">
      Email
    </label>
    <input type="email"
           class="w-full rounded-lg border border-gray-300 px-3 py-2
                  text-gray-900 placeholder:text-gray-400
                  focus:border-blue-500 focus:outline-none focus:ring-2
                  focus:ring-blue-500/20
                  invalid:border-red-500 invalid:focus:ring-red-500/20
                  dark:border-gray-600 dark:bg-gray-800 dark:text-white"
           placeholder="you@example.com" />
    <p class="mt-1 hidden text-sm text-red-500 peer-invalid:block">
      Please enter a valid email
    </p>
  </div>

  <!-- Button variants using @apply in CSS -->
  <button class="btn btn-primary">Primary</button>
  <button class="btn btn-secondary">Secondary</button>
  <button class="btn btn-danger">Danger</button>
</div>
```

```css
/* tailwind.config.js — custom theme */
/* @layer components for reusable classes */
@layer components {
  .btn {
    @apply inline-flex items-center justify-center rounded-lg px-4 py-2
           text-sm font-medium transition-colors focus:outline-none
           focus:ring-2 focus:ring-offset-2 disabled:cursor-not-allowed
           disabled:opacity-50;
  }
  .btn-primary {
    @apply bg-blue-600 text-white hover:bg-blue-700
           focus:ring-blue-500 active:bg-blue-800;
  }
  .btn-secondary {
    @apply border border-gray-300 bg-white text-gray-700
           hover:bg-gray-50 focus:ring-gray-500
           dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200;
  }
  .btn-danger {
    @apply bg-red-600 text-white hover:bg-red-700 focus:ring-red-500;
  }
}

/* Custom utilities */
@layer utilities {
  .text-balance {
    text-wrap: balance;
  }
  .scrollbar-hide {
    -ms-overflow-style: none;
    scrollbar-width: none;
  }
  .scrollbar-hide::-webkit-scrollbar {
    display: none;
  }
}
```

Tailwind patterns:
1. **`group` + `group-hover`** — parent-child hover interactions
2. **`dark:` prefix** — dark mode variants with class strategy
3. **`@layer components`** — extract reusable component classes
4. **`space-y-*`** — vertical spacing between children without margin utilities
5. **Responsive** — mobile-first: `sm:`, `md:`, `lg:`, `xl:` breakpoints'''
    ),
    (
        "css/responsive-layouts",
        "Show responsive layout patterns: flexbox, grid, container queries, and mobile-first design.",
        '''Responsive layout patterns:

```css
/* --- Holy grail layout with CSS Grid --- */

.layout {
  display: grid;
  grid-template-areas:
    "header  header  header"
    "sidebar content aside"
    "footer  footer  footer";
  grid-template-columns: 250px 1fr 200px;
  grid-template-rows: auto 1fr auto;
  min-height: 100dvh;
  gap: 1rem;
}

.header  { grid-area: header; }
.sidebar { grid-area: sidebar; }
.content { grid-area: content; }
.aside   { grid-area: aside; }
.footer  { grid-area: footer; }

/* Collapse sidebar on mobile */
@media (max-width: 768px) {
  .layout {
    grid-template-areas:
      "header"
      "content"
      "footer";
    grid-template-columns: 1fr;
  }
  .sidebar, .aside { display: none; }
}


/* --- Responsive card grid (auto-fill) --- */

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1.5rem;
  padding: 1rem;
}


/* --- Flex responsive navigation --- */

.nav {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem 2rem;
}

.nav-links {
  display: flex;
  gap: 1.5rem;
}

@media (max-width: 640px) {
  .nav {
    flex-direction: column;
    align-items: stretch;
  }
  .nav-links {
    flex-direction: column;
    gap: 0.5rem;
  }
}


/* --- Container queries --- */

.card-container {
  container-type: inline-size;
  container-name: card;
}

.card {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1rem;
}

/* When container is wide enough, go horizontal */
@container card (min-width: 400px) {
  .card {
    grid-template-columns: 200px 1fr;
  }
}

@container card (min-width: 600px) {
  .card {
    grid-template-columns: 300px 1fr auto;
  }
}


/* --- Fluid typography --- */

:root {
  /* Clamp: min, preferred, max */
  --fs-sm: clamp(0.875rem, 0.8rem + 0.25vw, 1rem);
  --fs-base: clamp(1rem, 0.9rem + 0.5vw, 1.125rem);
  --fs-lg: clamp(1.25rem, 1rem + 1vw, 1.5rem);
  --fs-xl: clamp(1.5rem, 1.2rem + 1.5vw, 2rem);
  --fs-2xl: clamp(2rem, 1.5rem + 2.5vw, 3rem);

  /* Fluid spacing */
  --space-xs: clamp(0.5rem, 0.4rem + 0.5vw, 0.75rem);
  --space-sm: clamp(0.75rem, 0.6rem + 0.75vw, 1rem);
  --space-md: clamp(1rem, 0.8rem + 1vw, 1.5rem);
  --space-lg: clamp(1.5rem, 1rem + 2vw, 2.5rem);
}

body { font-size: var(--fs-base); }
h1 { font-size: var(--fs-2xl); }
h2 { font-size: var(--fs-xl); }
h3 { font-size: var(--fs-lg); }


/* --- Aspect ratio and object-fit --- */

.hero-image {
  aspect-ratio: 16 / 9;
  width: 100%;
  object-fit: cover;
  object-position: center;
}

.avatar {
  aspect-ratio: 1;
  width: 48px;
  border-radius: 50%;
  object-fit: cover;
}


/* --- Scroll-snap for carousels --- */

.carousel {
  display: flex;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  scroll-behavior: smooth;
  gap: 1rem;
  -webkit-overflow-scrolling: touch;
}

.carousel > * {
  scroll-snap-align: start;
  flex: 0 0 min(300px, 80vw);
}
```

Responsive patterns:
1. **`auto-fill` + `minmax`** — responsive grid that wraps automatically
2. **Container queries** — responsive to parent container, not viewport
3. **`clamp()`** — fluid typography and spacing without breakpoints
4. **`100dvh`** — dynamic viewport height (accounts for mobile browser chrome)
5. **Scroll snap** — native carousel behavior without JavaScript'''
    ),
]
"""
