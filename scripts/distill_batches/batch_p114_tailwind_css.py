"""Tailwind CSS — utility patterns, component recipes, and custom configuration."""

PAIRS = [
    (
        "frontend/tailwind-patterns",
        "Show Tailwind CSS patterns: responsive design, dark mode, animations, and common component recipes.",
        '''Tailwind CSS patterns:

```html
<!-- --- Responsive card grid --- -->
<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 p-6">
  <div class="rounded-xl bg-white shadow-md dark:bg-gray-800 overflow-hidden
              hover:shadow-lg transition-shadow duration-200">
    <img class="w-full h-48 object-cover" src="/photo.jpg" alt="Product" />
    <div class="p-4 space-y-2">
      <h3 class="text-lg font-semibold text-gray-900 dark:text-white">Product Name</h3>
      <p class="text-sm text-gray-600 dark:text-gray-300 line-clamp-2">
        Description text that might be long and will be clamped to 2 lines.
      </p>
      <div class="flex items-center justify-between pt-2">
        <span class="text-xl font-bold text-blue-600 dark:text-blue-400">$29.99</span>
        <button class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white
                       hover:bg-blue-700 active:bg-blue-800
                       focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2
                       disabled:opacity-50 disabled:cursor-not-allowed
                       transition-colors">
          Add to Cart
        </button>
      </div>
    </div>
  </div>
</div>


<!-- --- Dark mode toggle --- -->
<!-- Uses class strategy: add 'dark' class to <html> -->
<html class="dark">
  <body class="bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100">
    <!-- Content adapts automatically -->
  </body>
</html>


<!-- --- Responsive navbar --- -->
<nav class="sticky top-0 z-50 bg-white/80 dark:bg-gray-900/80 backdrop-blur-md
            border-b border-gray-200 dark:border-gray-700">
  <div class="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
    <div class="flex h-16 items-center justify-between">
      <!-- Logo -->
      <a href="/" class="text-xl font-bold text-gray-900 dark:text-white">MyApp</a>

      <!-- Desktop nav -->
      <div class="hidden md:flex items-center gap-6">
        <a href="/docs" class="text-sm font-medium text-gray-600 hover:text-gray-900
                               dark:text-gray-300 dark:hover:text-white transition-colors">
          Docs
        </a>
        <a href="/pricing" class="text-sm font-medium text-gray-600 hover:text-gray-900
                                  dark:text-gray-300 dark:hover:text-white transition-colors">
          Pricing
        </a>
        <button class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white
                       hover:bg-blue-700 transition-colors">
          Sign In
        </button>
      </div>

      <!-- Mobile menu button -->
      <button class="md:hidden p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800">
        <svg class="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>
    </div>
  </div>
</nav>


<!-- --- Form with validation states --- -->
<form class="mx-auto max-w-md space-y-4 p-6">
  <!-- Input with label -->
  <div>
    <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
      Email
    </label>
    <input type="email"
           class="w-full rounded-lg border border-gray-300 px-4 py-2
                  text-gray-900 placeholder-gray-400
                  focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 focus:outline-none
                  dark:border-gray-600 dark:bg-gray-800 dark:text-white
                  invalid:border-red-500 invalid:focus:ring-red-500/20"
           placeholder="you@example.com" />
    <!-- Error message (shown conditionally) -->
    <p class="mt-1 text-sm text-red-600 dark:text-red-400 hidden">
      Please enter a valid email address.
    </p>
  </div>

  <!-- Submit button with loading state -->
  <button type="submit"
          class="group relative w-full rounded-lg bg-blue-600 px-4 py-2.5
                 text-sm font-semibold text-white
                 hover:bg-blue-700 transition-colors
                 disabled:opacity-70 disabled:cursor-wait">
    <span class="group-disabled:invisible">Create Account</span>
    <!-- Loading spinner (visible when disabled) -->
    <span class="absolute inset-0 flex items-center justify-center invisible group-disabled:visible">
      <svg class="h-5 w-5 animate-spin" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor"
                stroke-width="4" fill="none" />
        <path class="opacity-75" fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
    </span>
  </button>
</form>


<!-- --- Animations --- -->
<div class="animate-fade-in">Fade in on mount</div>
<div class="animate-pulse">Loading skeleton</div>
<div class="hover:scale-105 transition-transform duration-200">Zoom on hover</div>

<!-- Toast notification -->
<div class="fixed bottom-4 right-4 z-50
            animate-in slide-in-from-bottom-5 fade-in duration-300
            rounded-lg bg-gray-900 px-4 py-3 text-sm text-white shadow-lg
            flex items-center gap-3">
  <svg class="h-5 w-5 text-green-400 shrink-0"><!-- check icon --></svg>
  <span>Changes saved successfully.</span>
  <button class="ml-2 text-gray-400 hover:text-white">&times;</button>
</div>
```

```javascript
// tailwind.config.js
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./src/**/*.{js,ts,jsx,tsx,html}"],
  darkMode: "class",  // or "media" for OS preference
  theme: {
    extend: {
      colors: {
        brand: {
          50:  "#eff6ff",
          500: "#3b82f6",
          600: "#2563eb",
          700: "#1d4ed8",
        },
      },
      animation: {
        "fade-in": "fadeIn 0.3s ease-in-out",
        "slide-up": "slideUp 0.3s ease-out",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { transform: "translateY(10px)", opacity: "0" },
          "100%": { transform: "translateY(0)", opacity: "1" },
        },
      },
    },
  },
  plugins: [
    require("@tailwindcss/forms"),
    require("@tailwindcss/typography"),
    require("@tailwindcss/line-clamp"),
  ],
};
```

Tailwind patterns:
1. **`sm:` / `md:` / `lg:`** — mobile-first responsive breakpoints
2. **`dark:` variant** — dark mode with class or media strategy
3. **`group-disabled:`** — style children based on parent state (loading buttons)
4. **`focus:ring-2 focus:ring-blue-500/20`** — accessible focus indicators with opacity
5. **`backdrop-blur-md` + `bg-white/80`** — glassmorphism navbar with transparency'''
    ),
    (
        "frontend/css-animations",
        "Show CSS animation patterns: keyframes, transitions, scroll animations, and performance best practices.",
        '''CSS animation patterns:

```css
/* --- Transitions (hover/focus/active) --- */

.button {
  /* Specify which properties to animate */
  transition: background-color 200ms ease-out,
              transform 150ms ease-out,
              box-shadow 200ms ease-out;
}

.button:hover {
  background-color: #2563eb;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
}

.button:active {
  transform: translateY(0);
  transition-duration: 50ms;  /* Faster on click */
}


/* --- Keyframe animations --- */

/* Fade in + slide up (for page elements) */
@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.animate-fade-in-up {
  animation: fadeInUp 0.4s ease-out both;
}

/* Staggered children */
.stagger-list > * {
  animation: fadeInUp 0.4s ease-out both;
}
.stagger-list > *:nth-child(1) { animation-delay: 0ms; }
.stagger-list > *:nth-child(2) { animation-delay: 75ms; }
.stagger-list > *:nth-child(3) { animation-delay: 150ms; }
.stagger-list > *:nth-child(4) { animation-delay: 225ms; }
.stagger-list > *:nth-child(5) { animation-delay: 300ms; }


/* Skeleton loading pulse */
@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}

.skeleton {
  background: linear-gradient(
    90deg,
    #e2e8f0 25%, #f1f5f9 50%, #e2e8f0 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
  border-radius: 4px;
}

.skeleton-text { height: 1em; width: 80%; }
.skeleton-title { height: 1.5em; width: 60%; }
.skeleton-avatar { height: 48px; width: 48px; border-radius: 50%; }


/* Spinner */
@keyframes spin {
  to { transform: rotate(360deg); }
}

.spinner {
  width: 24px;
  height: 24px;
  border: 3px solid #e2e8f0;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}


/* --- Modal enter/exit --- */

.modal-backdrop {
  opacity: 0;
  transition: opacity 200ms ease-out;
}
.modal-backdrop.open { opacity: 1; }

.modal-content {
  opacity: 0;
  transform: scale(0.95) translateY(10px);
  transition: opacity 200ms ease-out, transform 200ms ease-out;
}
.modal-content.open {
  opacity: 1;
  transform: scale(1) translateY(0);
}


/* --- Accordion expand/collapse --- */

.accordion-content {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 300ms ease-out;
}

.accordion-content.open {
  grid-template-rows: 1fr;
}

.accordion-content > div {
  overflow: hidden;
}


/* --- Performance: prefer transform and opacity --- */

/* GOOD: GPU-accelerated, no layout recalculation */
.performant {
  transform: translateX(100px);
  opacity: 0.5;
  will-change: transform, opacity;
}

/* BAD: triggers layout recalculation */
/* .slow {
  left: 100px;
  width: 200px;
  height: 100px;
} */


/* --- Reduced motion: respect user preference --- */

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}


/* --- View Transitions API (page transitions) --- */

::view-transition-old(root) {
  animation: fadeOut 200ms ease-out;
}

::view-transition-new(root) {
  animation: fadeInUp 300ms ease-out;
}

/* Named view transitions for specific elements */
.product-image {
  view-transition-name: product-hero;
}
```

CSS animation patterns:
1. **`transition`** — smooth hover/focus state changes on specific properties
2. **Staggered `animation-delay`** — cascade children for list reveal effects
3. **Skeleton shimmer** — gradient animation for loading placeholders
4. **`grid-template-rows: 0fr→1fr`** — smooth height animation for accordions
5. **`prefers-reduced-motion`** — disable animations for motion-sensitive users'''
    ),
]
"""
