"""Web animations — Framer Motion, GSAP, View Transitions."""

PAIRS = [
    (
        "frontend/framer-motion-patterns",
        "Demonstrate Framer Motion patterns including layout animations, gestures, AnimatePresence, shared layout, and scroll-linked animations.",
        '''Framer Motion is a production-ready animation library for React that provides declarative animations, layout transitions, gesture handling, and exit animations.

```typescript
// --- Basic animations ---

import { motion, AnimatePresence, useScroll, useTransform } from 'framer-motion';
import type { Variants, Transition } from 'framer-motion';

// 1. Simple enter animation
function FadeIn({ children }: { children: React.ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
    >
      {children}
    </motion.div>
  );
}

// 2. Variants for orchestrated animations
const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1,       // delay between each child
      delayChildren: 0.2,         // delay before first child
    },
  },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 20, scale: 0.95 },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { type: 'spring', stiffness: 300, damping: 25 },
  },
};

function StaggeredList({ items }: { items: string[] }) {
  return (
    <motion.ul
      variants={containerVariants}
      initial="hidden"
      animate="visible"
    >
      {items.map(item => (
        <motion.li key={item} variants={itemVariants}>
          {item}
        </motion.li>
      ))}
    </motion.ul>
  );
}


// 3. Gesture animations
function DraggableCard() {
  return (
    <motion.div
      className="card"
      whileHover={{ scale: 1.02, boxShadow: '0 10px 30px rgba(0,0,0,0.15)' }}
      whileTap={{ scale: 0.98 }}
      drag
      dragConstraints={{ left: -100, right: 100, top: -50, bottom: 50 }}
      dragElastic={0.1}
      dragTransition={{ bounceStiffness: 300, bounceDamping: 20 }}
    >
      <h3>Drag me!</h3>
    </motion.div>
  );
}


// 4. Keyframes
function PulsingDot() {
  return (
    <motion.div
      animate={{
        scale: [1, 1.2, 1],
        opacity: [1, 0.7, 1],
      }}
      transition={{
        duration: 2,
        repeat: Infinity,
        ease: 'easeInOut',
      }}
      className="notification-dot"
    />
  );
}
```

```typescript
// --- AnimatePresence for exit animations ---

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

// Toast notification with enter/exit animations
interface Toast {
  id: string;
  message: string;
  type: 'success' | 'error' | 'info';
}

function ToastContainer({ toasts }: { toasts: Toast[] }) {
  return (
    <div className="toast-container">
      <AnimatePresence mode="popLayout">
        {toasts.map(toast => (
          <motion.div
            key={toast.id}
            layout                  // smooth reflow when items add/remove
            initial={{ opacity: 0, x: 100, scale: 0.9 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: 100, scale: 0.9 }}
            transition={{ type: 'spring', stiffness: 400, damping: 30 }}
            className={`toast toast-${toast.type}`}
          >
            {toast.message}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}


// Page transitions with AnimatePresence
function PageTransition({ children, key }: { children: React.ReactNode; key: string }) {
  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={key}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -10 }}
        transition={{ duration: 0.2, ease: 'easeInOut' }}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}


// --- Layout animations ---

// Shared layout animation (morphing between views)
function ExpandableCard({ item }: { item: { id: string; title: string; body: string } }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <motion.div
      layout
      layoutId={`card-${item.id}`}
      onClick={() => setExpanded(!expanded)}
      className={expanded ? 'card-expanded' : 'card-collapsed'}
      style={{ borderRadius: 12 }}
      transition={{ type: 'spring', stiffness: 400, damping: 30 }}
    >
      <motion.h3 layout="position" layoutId={`title-${item.id}`}>
        {item.title}
      </motion.h3>

      <AnimatePresence>
        {expanded && (
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            {item.body}
          </motion.p>
        )}
      </AnimatePresence>
    </motion.div>
  );
}


// Tab indicator that morphs between tabs
function AnimatedTabs({ tabs, activeTab, onTabChange }: {
  tabs: string[];
  activeTab: string;
  onTabChange: (tab: string) => void;
}) {
  return (
    <div className="tab-list" role="tablist">
      {tabs.map(tab => (
        <button
          key={tab}
          role="tab"
          aria-selected={activeTab === tab}
          onClick={() => onTabChange(tab)}
          className="tab-button"
        >
          {tab}
          {activeTab === tab && (
            <motion.div
              layoutId="tab-indicator"
              className="tab-indicator"
              transition={{ type: 'spring', stiffness: 500, damping: 35 }}
            />
          )}
        </button>
      ))}
    </div>
  );
}
```

```typescript
// --- Scroll-linked animations ---

import { useScroll, useTransform, useSpring, motion } from 'framer-motion';
import { useRef } from 'react';

// 1. Scroll progress bar
function ScrollProgress() {
  const { scrollYProgress } = useScroll();

  return (
    <motion.div
      className="scroll-progress"
      style={{
        scaleX: scrollYProgress,
        transformOrigin: 'left',
      }}
    />
  );
}


// 2. Parallax effect
function ParallaxSection({ children }: { children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ['start end', 'end start'],  // track from entering to leaving viewport
  });

  const y = useTransform(scrollYProgress, [0, 1], [100, -100]);
  const opacity = useTransform(scrollYProgress, [0, 0.3, 0.7, 1], [0, 1, 1, 0]);

  return (
    <div ref={ref} style={{ position: 'relative', overflow: 'hidden' }}>
      <motion.div style={{ y, opacity }}>
        {children}
      </motion.div>
    </div>
  );
}


// 3. Element reveal on scroll
function ScrollReveal({
  children,
  direction = 'up',
}: {
  children: React.ReactNode;
  direction?: 'up' | 'down' | 'left' | 'right';
}) {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ['start 90%', 'start 40%'],  // trigger zone
  });

  const directionMap = {
    up:    { y: [50, 0], x: [0, 0] },
    down:  { y: [-50, 0], x: [0, 0] },
    left:  { y: [0, 0], x: [50, 0] },
    right: { y: [0, 0], x: [-50, 0] },
  };

  const y = useTransform(scrollYProgress, [0, 1], directionMap[direction].y);
  const x = useTransform(scrollYProgress, [0, 1], directionMap[direction].x);
  const opacity = useTransform(scrollYProgress, [0, 1], [0, 1]);

  // Smooth spring physics
  const smoothY = useSpring(y, { stiffness: 100, damping: 20 });
  const smoothX = useSpring(x, { stiffness: 100, damping: 20 });
  const smoothOpacity = useSpring(opacity, { stiffness: 100, damping: 20 });

  return (
    <motion.div
      ref={ref}
      style={{ y: smoothY, x: smoothX, opacity: smoothOpacity }}
    >
      {children}
    </motion.div>
  );
}


// 4. Scroll-linked number counter
function AnimatedCounter({
  target,
  label,
}: {
  target: number;
  label: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ['start 80%', 'start 30%'],
  });

  const count = useTransform(scrollYProgress, [0, 1], [0, target]);
  const rounded = useTransform(count, (v) => Math.round(v));

  return (
    <div ref={ref} className="stat">
      <motion.span className="stat-number">{rounded}</motion.span>
      <span className="stat-label">{label}</span>
    </div>
  );
}
```

| Feature | Framer Motion | CSS Animations | Web Animations API |
|---|---|---|---|
| Declarative | Yes (JSX props) | Yes (@keyframes) | Imperative (.animate()) |
| Layout animations | Yes (`layout` prop) | No | No |
| Exit animations | Yes (AnimatePresence) | No (needs JS) | Manual |
| Spring physics | Yes (built-in) | No | No |
| Gesture support | whileHover, whileTap, drag | :hover only | No |
| Scroll-linked | useScroll + useTransform | scroll-timeline | No |
| Shared layout | layoutId morphing | No | No |
| Bundle size | ~30 KB gzipped | 0 KB | 0 KB |
| SSR | Yes | Yes | Client only |

| Animation Type | Best Approach |
|---|---|
| Enter/exit | `initial`, `animate`, `exit` with AnimatePresence |
| Hover/tap | `whileHover`, `whileTap` |
| List reordering | `layout` prop on each item |
| Page transitions | AnimatePresence `mode="wait"` |
| Scroll reveal | `useScroll` + `useTransform` |
| Shared element | `layoutId` on both source and target |
| Staggered children | `variants` with `staggerChildren` |
| Drag | `drag`, `dragConstraints` |

Key patterns:
1. Use `variants` for orchestrated parent-child animations with `staggerChildren`
2. `AnimatePresence` wraps elements that mount/unmount to animate exits
3. `layout` prop auto-animates CSS layout changes (size, position, order)
4. `layoutId` creates shared element transitions across different components
5. `useScroll` + `useTransform` for performant scroll-linked animations
6. Spring physics (`type: "spring"`) feel more natural than easing curves
7. Use `mode="wait"` on AnimatePresence for sequential page transitions'''
    ),
    (
        "frontend/view-transitions-api",
        "Demonstrate the View Transitions API for smooth page transitions including same-document transitions, cross-document transitions, and CSS customization.",
        '''The View Transitions API enables smooth animated transitions between DOM states or page navigations, providing a native alternative to JavaScript animation libraries for page transitions.

```typescript
// --- Same-document view transitions ---

// Basic: wrap a DOM mutation in startViewTransition
function updateContent(newContent: string): void {
  if (!document.startViewTransition) {
    // Fallback: update without animation
    document.getElementById('content')!.innerHTML = newContent;
    return;
  }

  document.startViewTransition(() => {
    document.getElementById('content')!.innerHTML = newContent;
  });
}


// React: view transitions for state changes
import { useCallback } from 'react';
import { flushSync } from 'react-dom';

function useViewTransition() {
  return useCallback((callback: () => void) => {
    if (!document.startViewTransition) {
      callback();
      return;
    }

    document.startViewTransition(() => {
      // flushSync ensures React updates the DOM synchronously
      // so the View Transition can capture the new state
      flushSync(callback);
    });
  }, []);
}

// Usage
function TabPanel() {
  const [activeTab, setActiveTab] = useState('home');
  const withTransition = useViewTransition();

  function switchTab(tab: string) {
    withTransition(() => setActiveTab(tab));
  }

  return (
    <div>
      <nav>
        <button onClick={() => switchTab('home')}>Home</button>
        <button onClick={() => switchTab('about')}>About</button>
        <button onClick={() => switchTab('contact')}>Contact</button>
      </nav>
      <div style={{ viewTransitionName: 'tab-content' }}>
        {activeTab === 'home' && <HomePage />}
        {activeTab === 'about' && <AboutPage />}
        {activeTab === 'contact' && <ContactPage />}
      </div>
    </div>
  );
}
```

```css
/* --- Customizing view transition animations --- */

/* Default transition uses cross-fade. Customize with CSS: */

/* The root transition (entire page cross-fade) */
::view-transition-old(root) {
  animation: fade-out 0.3s ease-in-out;
}

::view-transition-new(root) {
  animation: fade-in 0.3s ease-in-out;
}

@keyframes fade-out {
  to { opacity: 0; }
}

@keyframes fade-in {
  from { opacity: 0; }
}


/* Named transition: slide for tab content */
::view-transition-old(tab-content) {
  animation: slide-out-left 0.3s ease-in-out;
}

::view-transition-new(tab-content) {
  animation: slide-in-right 0.3s ease-in-out;
}

@keyframes slide-out-left {
  to {
    transform: translateX(-100%);
    opacity: 0;
  }
}

@keyframes slide-in-right {
  from {
    transform: translateX(100%);
    opacity: 0;
  }
}


/* Named transition: morph for shared elements */
.product-image {
  view-transition-name: product-hero;
}

::view-transition-group(product-hero) {
  animation-duration: 0.4s;
  animation-timing-function: cubic-bezier(0.4, 0, 0.2, 1);
}

/* The group automatically morphs size/position — no custom keyframes needed */


/* Transition for card expand/collapse */
.card-thumbnail {
  view-transition-name: card-image;
}

.card-detail .hero-image {
  view-transition-name: card-image;  /* same name = shared transition */
}

::view-transition-group(card-image) {
  animation-duration: 0.5s;
  animation-timing-function: cubic-bezier(0.22, 1, 0.36, 1);
}


/* Reduce motion preference */
@media (prefers-reduced-motion: reduce) {
  ::view-transition-group(*),
  ::view-transition-old(*),
  ::view-transition-new(*) {
    animation-duration: 0.01ms !important;
  }
}
```

```typescript
// --- Cross-document view transitions (MPA) ---

// Works with multi-page apps (MPA) — no JavaScript framework needed
// Requires: same-origin pages

// Enable in both source and destination pages:
// <meta name="view-transition" content="same-origin">

// Or via CSS:
// @view-transition { navigation: auto; }

// page1.html
/*
<!DOCTYPE html>
<html>
<head>
  <meta name="view-transition" content="same-origin">
  <style>
    .product-image { view-transition-name: product; }
    .page-title { view-transition-name: title; }
  </style>
</head>
<body>
  <h1 class="page-title">Products</h1>
  <a href="/product/123">
    <img class="product-image" src="/img/product-123.jpg" />
  </a>
</body>
</html>
*/

// page2.html
/*
<!DOCTYPE html>
<html>
<head>
  <meta name="view-transition" content="same-origin">
  <style>
    .hero-image { view-transition-name: product; }
    .page-title { view-transition-name: title; }
  </style>
</head>
<body>
  <h1 class="page-title">Product Details</h1>
  <img class="hero-image" src="/img/product-123.jpg" />
</body>
</html>
*/

// The browser automatically animates elements with matching
// view-transition-name values between pages!


// --- Advanced: dynamic view-transition-name ---

// Generate unique transition names for list items
function ProductGrid({ products }: { products: Product[] }) {
  return (
    <div className="grid">
      {products.map(product => (
        <a
          key={product.id}
          href={`/product/${product.id}`}
          onClick={(e) => handleNavigation(e, `/product/${product.id}`)}
        >
          <img
            src={product.image}
            alt={product.name}
            style={{ viewTransitionName: `product-${product.id}` }}
          />
          <h3 style={{ viewTransitionName: `title-${product.id}` }}>
            {product.name}
          </h3>
        </a>
      ))}
    </div>
  );
}

// SPA navigation with view transitions
async function handleNavigation(
  e: React.MouseEvent<HTMLAnchorElement>,
  url: string,
): Promise<void> {
  e.preventDefault();

  if (!document.startViewTransition) {
    window.location.href = url;
    return;
  }

  const transition = document.startViewTransition(async () => {
    // Navigate using your router
    await router.push(url);
  });

  // Wait for transition to complete
  await transition.finished;
}


// --- Transition types for directional navigation ---

// Use view-transition-type to apply different animations
// based on navigation direction

function navigateWithDirection(url: string, direction: 'forward' | 'back') {
  if (!document.startViewTransition) {
    router.push(url);
    return;
  }

  const transition = document.startViewTransition({
    update: () => flushSync(() => router.push(url)),
    types: [direction],  // 'forward' or 'back'
  });
}

/*
CSS:
::view-transition-old(root):only-child {
  animation: none;
}

:active-view-transition-type(forward) {
  &::view-transition-old(root) {
    animation: slide-out-left 0.3s ease;
  }
  &::view-transition-new(root) {
    animation: slide-in-right 0.3s ease;
  }
}

:active-view-transition-type(back) {
  &::view-transition-old(root) {
    animation: slide-out-right 0.3s ease;
  }
  &::view-transition-new(root) {
    animation: slide-in-left 0.3s ease;
  }
}
*/
```

| Feature | View Transitions API | Framer Motion | FLIP animations |
|---|---|---|---|
| Same-document | Yes | Yes (AnimatePresence) | Yes (manual) |
| Cross-document (MPA) | Yes | No | No |
| Shared elements | `view-transition-name` | `layoutId` | Manual calculation |
| Animation customization | CSS @keyframes | JS/variants | CSS/JS |
| Reduced motion | `prefers-reduced-motion` | `useReducedMotion()` | Manual |
| Browser support | Chrome 111+ | All (React) | All |
| Bundle size | 0 KB (native) | ~30 KB | 0 KB |
| Framework dependency | None | React only | None |

| Pseudo-element | Purpose | Customization |
|---|---|---|
| `::view-transition` | Root container for all transitions | Rarely needed |
| `::view-transition-group(name)` | Container for old+new snapshots | Size/position animation |
| `::view-transition-image-pair(name)` | Pairs old and new images | Isolation, blending |
| `::view-transition-old(name)` | Snapshot of the old state | Exit animation |
| `::view-transition-new(name)` | Snapshot of the new state | Enter animation |

Key patterns:
1. `document.startViewTransition(() => updateDOM())` wraps any DOM mutation
2. Match `view-transition-name` on old and new elements for shared element transitions
3. Customize animations with `::view-transition-old(name)` and `::view-transition-new(name)`
4. Cross-document transitions need `<meta name="view-transition" content="same-origin">`
5. Use `flushSync` in React to ensure DOM updates happen synchronously within the transition
6. Dynamic `viewTransitionName` for list items: `style={{ viewTransitionName: \\`item-${id}\\` }}`
7. Always respect `prefers-reduced-motion` by shortening animation durations'''
    ),
    (
        "frontend/css-spring-animations",
        "Demonstrate CSS-based animations including spring physics approximation, stagger patterns, and scroll-triggered animation techniques.",
        '''CSS animations can achieve sophisticated effects including spring-like physics, staggered reveals, and scroll-triggered sequences using modern CSS features.

```css
/* --- Spring physics approximation in CSS --- */

/* CSS doesn't have native spring(), but we can approximate
   spring behavior with custom cubic-bezier curves and
   the linear() easing function */

:root {
  /* Spring-like bounce curves */
  --ease-spring-1: cubic-bezier(0.175, 0.885, 0.32, 1.275);  /* slight overshoot */
  --ease-spring-2: cubic-bezier(0.34, 1.56, 0.64, 1);        /* more bouncy */
  --ease-spring-3: cubic-bezier(0.22, 1.0, 0.36, 1.0);       /* smooth deceleration */

  /* linear() for precise spring physics (Chrome 113+) */
  --ease-spring-precise: linear(
    0, 0.009, 0.035 2.1%, 0.141, 0.281 6.7%, 0.723 12.9%,
    0.938 16.7%, 1.017, 1.077, 1.121, 1.149 24.3%,
    1.159, 1.163, 1.161, 1.154 29.9%, 1.129 32.8%,
    1.051 39.6%, 1.017 43.1%, 0.991, 0.977 51%,
    0.975 57.1%, 0.997 69.8%, 1.003 76.9%, 1
  );

  /* Standard easings */
  --ease-out: cubic-bezier(0, 0, 0.2, 1);
  --ease-in-out: cubic-bezier(0.4, 0, 0.2, 1);
}


/* Spring-animated card */
.card {
  transition: transform 0.5s var(--ease-spring-1),
              box-shadow 0.3s var(--ease-out);
}

.card:hover {
  transform: translateY(-4px) scale(1.01);
  box-shadow: 0 12px 24px rgb(0 0 0 / 0.12);
}

.card:active {
  transform: translateY(-1px) scale(0.99);
  transition-duration: 0.1s;
}


/* Button press spring effect */
.btn-spring {
  transition: transform 0.4s var(--ease-spring-2);
}

.btn-spring:hover {
  transform: scale(1.05);
}

.btn-spring:active {
  transform: scale(0.95);
  transition-duration: 0.1s;
}
```

```css
/* --- Stagger patterns --- */

/* 1. Staggered list reveal using animation-delay */
@keyframes stagger-in {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.stagger-list > * {
  opacity: 0;  /* hidden by default */
  animation: stagger-in 0.5s var(--ease-spring-3) forwards;
}

/* Generate delays with :nth-child */
.stagger-list > :nth-child(1)  { animation-delay: 0ms; }
.stagger-list > :nth-child(2)  { animation-delay: 50ms; }
.stagger-list > :nth-child(3)  { animation-delay: 100ms; }
.stagger-list > :nth-child(4)  { animation-delay: 150ms; }
.stagger-list > :nth-child(5)  { animation-delay: 200ms; }
.stagger-list > :nth-child(6)  { animation-delay: 250ms; }
.stagger-list > :nth-child(7)  { animation-delay: 300ms; }
.stagger-list > :nth-child(8)  { animation-delay: 350ms; }
.stagger-list > :nth-child(9)  { animation-delay: 400ms; }
.stagger-list > :nth-child(10) { animation-delay: 450ms; }

/* Or use CSS custom properties for dynamic stagger */
.stagger-list > * {
  animation: stagger-in 0.5s var(--ease-spring-3) forwards;
  animation-delay: calc(var(--index, 0) * 60ms);
}

/* Set via inline style: style="--index: 3" */


/* 2. Grid stagger (diagonal reveal) */
.stagger-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
}

.stagger-grid > * {
  animation: scale-in 0.4s var(--ease-spring-1) forwards;
  opacity: 0;
}

@keyframes scale-in {
  from {
    opacity: 0;
    transform: scale(0.8);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

/* Diagonal stagger: row + col based delay */
.stagger-grid > :nth-child(1)  { animation-delay: 0ms; }    /* (0,0) */
.stagger-grid > :nth-child(2)  { animation-delay: 50ms; }   /* (0,1) */
.stagger-grid > :nth-child(3)  { animation-delay: 100ms; }  /* (0,2) */
.stagger-grid > :nth-child(4)  { animation-delay: 50ms; }   /* (1,0) */
.stagger-grid > :nth-child(5)  { animation-delay: 100ms; }  /* (1,1) */
.stagger-grid > :nth-child(6)  { animation-delay: 150ms; }  /* (1,2) */
.stagger-grid > :nth-child(7)  { animation-delay: 100ms; }  /* (2,0) */
.stagger-grid > :nth-child(8)  { animation-delay: 150ms; }  /* (2,1) */
.stagger-grid > :nth-child(9)  { animation-delay: 200ms; }  /* (2,2) */
```

```typescript
// --- Scroll-triggered CSS animations with IntersectionObserver ---

// Lightweight scroll animation without any library

function initScrollAnimations(): void {
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('animate-in');
          // Once animated, stop observing
          observer.unobserve(entry.target);
        }
      });
    },
    {
      rootMargin: '-10% 0px',  // trigger slightly inside viewport
      threshold: 0.1,
    }
  );

  // Observe all elements with data-animate attribute
  document.querySelectorAll('[data-animate]').forEach(el => {
    observer.observe(el);
  });
}

// Call on page load
document.addEventListener('DOMContentLoaded', initScrollAnimations);
```

```css
/* CSS classes for scroll-triggered animations */

/* Hidden state (before animation) */
[data-animate] {
  opacity: 0;
}

/* Animated state (triggered by IntersectionObserver) */
[data-animate="fade-up"].animate-in {
  animation: fade-up 0.6s var(--ease-spring-3) forwards;
}

[data-animate="fade-left"].animate-in {
  animation: fade-left 0.6s var(--ease-spring-3) forwards;
}

[data-animate="fade-right"].animate-in {
  animation: fade-right 0.6s var(--ease-spring-3) forwards;
}

[data-animate="scale"].animate-in {
  animation: scale-reveal 0.5s var(--ease-spring-1) forwards;
}

[data-animate="clip-up"].animate-in {
  animation: clip-up 0.8s var(--ease-out) forwards;
}

@keyframes fade-up {
  from { opacity: 0; transform: translateY(30px); }
  to   { opacity: 1; transform: translateY(0); }
}

@keyframes fade-left {
  from { opacity: 0; transform: translateX(30px); }
  to   { opacity: 1; transform: translateX(0); }
}

@keyframes fade-right {
  from { opacity: 0; transform: translateX(-30px); }
  to   { opacity: 1; transform: translateX(0); }
}

@keyframes scale-reveal {
  from { opacity: 0; transform: scale(0.9); }
  to   { opacity: 1; transform: scale(1); }
}

@keyframes clip-up {
  from { clip-path: inset(100% 0 0 0); }
  to   { clip-path: inset(0); }
}

/* Stagger within scroll-animated containers */
[data-animate="stagger"].animate-in > * {
  animation: fade-up 0.5s var(--ease-spring-3) forwards;
  opacity: 0;
}

[data-animate="stagger"].animate-in > :nth-child(1)  { animation-delay: 0ms; }
[data-animate="stagger"].animate-in > :nth-child(2)  { animation-delay: 80ms; }
[data-animate="stagger"].animate-in > :nth-child(3)  { animation-delay: 160ms; }
[data-animate="stagger"].animate-in > :nth-child(4)  { animation-delay: 240ms; }


/* Reduced motion: respect user preference */
@media (prefers-reduced-motion: reduce) {
  [data-animate] {
    opacity: 1 !important;
    animation: none !important;
    transition: none !important;
  }
}
```

```html
<!-- Usage in HTML -->
<section data-animate="fade-up">
  <h2>Features</h2>
</section>

<div data-animate="stagger" style="--stagger-delay: 80ms">
  <div class="card">Card 1</div>
  <div class="card">Card 2</div>
  <div class="card">Card 3</div>
</div>

<img data-animate="scale" src="hero.avif" alt="Hero">
<p data-animate="clip-up">Revealed text</p>
```

| CSS Easing | Curve | Feel |
|---|---|---|
| `ease` | `cubic-bezier(0.25, 0.1, 0.25, 1)` | Default, generic |
| `ease-out` | `cubic-bezier(0, 0, 0.2, 1)` | Fast start, slow end |
| `ease-in-out` | `cubic-bezier(0.4, 0, 0.2, 1)` | Smooth both ends |
| Spring (light) | `cubic-bezier(0.175, 0.885, 0.32, 1.275)` | Slight overshoot |
| Spring (bouncy) | `cubic-bezier(0.34, 1.56, 0.64, 1)` | Noticeable bounce |
| Spring (precise) | `linear(...)` (Chrome 113+) | Accurate spring physics |

| Technique | JS Required | Performance | Browser Support |
|---|---|---|---|
| CSS @keyframes | No | Compositor thread | Universal |
| CSS transitions | No | Compositor thread | Universal |
| IntersectionObserver + CSS | Minimal (~10 lines) | Compositor thread | IE11+ (with polyfill) |
| Scroll-driven animations | No | Compositor thread | Chrome 115+ |
| Framer Motion | Yes (~30 KB) | React reconciler | All (React) |
| GSAP | Yes (~30 KB) | requestAnimationFrame | Universal |

Key patterns:
1. Approximate spring physics with `cubic-bezier(0.34, 1.56, 0.64, 1)` for overshoot
2. Use `linear()` for precise spring curves (Chrome 113+ only)
3. Stagger with `animation-delay: calc(var(--index) * 60ms)` and inline custom properties
4. IntersectionObserver + CSS classes is the lightest scroll animation approach
5. Always respect `prefers-reduced-motion: reduce` by disabling animations
6. Use `transform` and `opacity` only for animations (compositor-thread, jank-free)
7. CSS `clip-path` animations create elegant reveal effects'''
    ),
    (
        "frontend/gsap-scrolltrigger",
        "Show GSAP ScrollTrigger patterns for scroll-linked animations including pin, scrub, batch, and parallax effects.",
        '''GSAP (GreenSock Animation Platform) with ScrollTrigger provides the most powerful scroll-linked animation system, supporting pinning, scrubbing, batch animations, and complex timelines.

```typescript
// --- GSAP + ScrollTrigger setup ---

import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { useEffect, useRef } from 'react';

// Register the plugin
gsap.registerPlugin(ScrollTrigger);

// 1. Basic scroll-triggered animation
function FadeInSection() {
  const sectionRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.from('.fade-item', {
        y: 60,
        opacity: 0,
        duration: 0.8,
        ease: 'power3.out',
        stagger: 0.15,
        scrollTrigger: {
          trigger: sectionRef.current,
          start: 'top 80%',     // when top of section hits 80% of viewport
          end: 'bottom 20%',    // when bottom hits 20% of viewport
          toggleActions: 'play none none none',
          // play/reverse/restart/reset for:
          // onEnter, onLeave, onEnterBack, onLeaveBack
        },
      });
    }, sectionRef);

    return () => ctx.revert();  // cleanup on unmount
  }, []);

  return (
    <div ref={sectionRef}>
      <h2 className="fade-item">Title</h2>
      <p className="fade-item">Paragraph 1</p>
      <p className="fade-item">Paragraph 2</p>
    </div>
  );
}


// 2. Scrub animation (progress tied to scroll position)
function ScrubSection() {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.to('.progress-bar', {
        scaleX: 1,
        ease: 'none',
        scrollTrigger: {
          trigger: containerRef.current,
          start: 'top top',
          end: 'bottom bottom',
          scrub: true,  // ties animation progress to scroll
          // scrub: 0.5 adds 0.5s smoothing
        },
      });
    }, containerRef);

    return () => ctx.revert();
  }, []);

  return (
    <div ref={containerRef}>
      <div className="progress-bar" style={{ transformOrigin: 'left', scaleX: 0 }} />
      <div style={{ height: '200vh' }}>Scroll content</div>
    </div>
  );
}
```

```typescript
// --- Pin and horizontal scroll ---

// 3. Pinned section (stays fixed while scrolling)
function PinnedSection() {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      // Pin the section for the duration of the timeline
      const tl = gsap.timeline({
        scrollTrigger: {
          trigger: containerRef.current,
          start: 'top top',
          end: '+=200%',      // pin for 2x viewport heights of scroll
          pin: true,           // pin the trigger element
          scrub: 1,            // smooth scrubbing
          anticipatePin: 1,    // reduce jank on pin
        },
      });

      // Animations within the pinned section
      tl.from('.step-1', { opacity: 0, x: -100, duration: 1 })
        .from('.step-2', { opacity: 0, y: 50, duration: 1 }, '+=0.5')
        .from('.step-3', { opacity: 0, scale: 0.8, duration: 1 }, '+=0.5')
        .to('.step-1', { opacity: 0, x: 100, duration: 0.5 }, '+=0.5');
    }, containerRef);

    return () => ctx.revert();
  }, []);

  return (
    <div ref={containerRef} className="pinned-section">
      <div className="step-1">Step 1 content</div>
      <div className="step-2">Step 2 content</div>
      <div className="step-3">Step 3 content</div>
    </div>
  );
}


// 4. Horizontal scroll section
function HorizontalScroll() {
  const containerRef = useRef<HTMLDivElement>(null);
  const panelsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      const panels = gsap.utils.toArray<HTMLElement>('.panel');

      gsap.to(panels, {
        xPercent: -100 * (panels.length - 1),
        ease: 'none',
        scrollTrigger: {
          trigger: containerRef.current,
          pin: true,
          scrub: 1,
          snap: 1 / (panels.length - 1),  // snap to each panel
          end: () => `+=${panelsRef.current!.scrollWidth}`,
        },
      });

      // Animate content within each panel as it comes into view
      panels.forEach((panel) => {
        gsap.from(panel.querySelectorAll('.panel-content'), {
          y: 30,
          opacity: 0,
          duration: 0.6,
          stagger: 0.1,
          scrollTrigger: {
            trigger: panel,
            containerAnimation: gsap.getById('horizontal') as gsap.core.Tween,
            start: 'left center',
            toggleActions: 'play none none reverse',
          },
        });
      });
    }, containerRef);

    return () => ctx.revert();
  }, []);

  return (
    <div ref={containerRef} className="horizontal-container">
      <div ref={panelsRef} className="panels-wrapper">
        <div className="panel">
          <div className="panel-content">Section 1</div>
        </div>
        <div className="panel">
          <div className="panel-content">Section 2</div>
        </div>
        <div className="panel">
          <div className="panel-content">Section 3</div>
        </div>
      </div>
    </div>
  );
}
```

```typescript
// --- Batch animations and parallax ---

// 5. ScrollTrigger.batch for efficient list animations
function BatchList() {
  useEffect(() => {
    // Batch automatically staggers elements as they enter the viewport
    ScrollTrigger.batch('.batch-item', {
      onEnter: (elements) => {
        gsap.from(elements, {
          y: 40,
          opacity: 0,
          duration: 0.6,
          ease: 'power3.out',
          stagger: 0.1,
        });
      },
      onLeave: (elements) => {
        gsap.to(elements, { opacity: 0, y: -20, duration: 0.3 });
      },
      onEnterBack: (elements) => {
        gsap.to(elements, { opacity: 1, y: 0, duration: 0.3 });
      },
      start: 'top 85%',
      end: 'top 15%',
    });

    return () => ScrollTrigger.getAll().forEach(t => t.kill());
  }, []);

  return (
    <div>
      {Array.from({ length: 50 }, (_, i) => (
        <div key={i} className="batch-item">
          Item {i + 1}
        </div>
      ))}
    </div>
  );
}


// 6. Parallax layers
function ParallaxHero() {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      // Background moves slow, foreground moves fast
      gsap.to('.parallax-bg', {
        yPercent: 30,
        ease: 'none',
        scrollTrigger: {
          trigger: containerRef.current,
          start: 'top top',
          end: 'bottom top',
          scrub: true,
        },
      });

      gsap.to('.parallax-mid', {
        yPercent: 15,
        ease: 'none',
        scrollTrigger: {
          trigger: containerRef.current,
          start: 'top top',
          end: 'bottom top',
          scrub: true,
        },
      });

      gsap.to('.parallax-fg', {
        yPercent: -10,
        ease: 'none',
        scrollTrigger: {
          trigger: containerRef.current,
          start: 'top top',
          end: 'bottom top',
          scrub: true,
        },
      });

      // Text reveal with clip-path
      gsap.from('.hero-text', {
        clipPath: 'inset(100% 0 0 0)',
        duration: 1,
        ease: 'power4.out',
        scrollTrigger: {
          trigger: '.hero-text',
          start: 'top 80%',
        },
      });
    }, containerRef);

    return () => ctx.revert();
  }, []);

  return (
    <div ref={containerRef} className="parallax-hero">
      <div className="parallax-bg" />
      <div className="parallax-mid" />
      <div className="parallax-fg" />
      <h1 className="hero-text">Welcome</h1>
    </div>
  );
}


// 7. React cleanup pattern
function useGSAP(callback: (ctx: gsap.Context) => void, deps: unknown[] = []) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      callback(ctx);
    }, containerRef);

    return () => ctx.revert();
  }, deps);

  return containerRef;
}
```

| ScrollTrigger Property | Description | Common Values |
|---|---|---|
| `trigger` | Element that triggers the animation | CSS selector or element |
| `start` | When animation starts | `'top 80%'`, `'center center'` |
| `end` | When animation ends | `'bottom 20%'`, `'+=500'` |
| `scrub` | Tie progress to scroll | `true`, `0.5` (smooth), `1` |
| `pin` | Fix element during scroll | `true`, element |
| `snap` | Snap to points | `1/3`, `{ snapTo: 0.25 }` |
| `toggleActions` | Play/reverse behavior | `'play none none none'` |
| `markers` | Debug markers (dev only) | `true` |

| Feature | GSAP + ScrollTrigger | Framer Motion | CSS scroll-timeline |
|---|---|---|---|
| Scroll-linked | scrub, pin, snap | useScroll + useTransform | animation-timeline |
| Pinning | Built-in | Manual (position: sticky) | position: sticky |
| Horizontal scroll | xPercent animation | Manual | scroll-timeline-axis |
| Batch animations | ScrollTrigger.batch | Manual stagger | No |
| Timeline sequencing | gsap.timeline | variants | @keyframes |
| Performance | requestAnimationFrame | React reconciler | Compositor thread |
| Bundle size | ~30 KB | ~30 KB | 0 KB |
| Framework | Any (vanilla JS) | React only | CSS only |

Key patterns:
1. Always use `gsap.context()` + `ctx.revert()` for React cleanup (prevents memory leaks)
2. `scrub: true` ties animation progress 1:1 with scroll; `scrub: 0.5` adds smoothing
3. `pin: true` fixes the element while its scroll-based animations play
4. `ScrollTrigger.batch` efficiently handles large lists (staggers entering elements)
5. Parallax: multiple layers with different `yPercent` values and `scrub: true`
6. `snap` with fractional values creates section-snapping behavior
7. Use `markers: true` during development to visualize trigger zones'''
    ),

    # --- 5. CSS Scroll-Driven Animations ---
    (
        "frontend/css-scroll-driven-animations",
        "Implement scroll-driven animations using the CSS Scroll Timeline specification "
        "(scroll-timeline, view-timeline, animation-timeline). Show progress bars, parallax "
        "effects, reveal-on-scroll, and element-linked animations. Include the JavaScript "
        "ScrollTimeline polyfill for broader browser support.",
        """\
# CSS Scroll-Driven Animations (2026 Spec)

## Two Types of Scroll Timelines

```
1. Scroll Progress Timeline (scroll()):
   - Tracks scroll position of a scroll container
   - 0% = top of scroll, 100% = bottom of scroll
   - Use for: progress bars, parallax, fade-in headers

2. View Progress Timeline (view()):
   - Tracks element's visibility in the scrollport
   - 0% = element enters, 100% = element exits
   - Use for: reveal animations, sticky effects, parallax cards
```

## Scroll Progress: Reading Progress Bar

```html
<!-- Pure CSS progress indicator tied to page scroll -->
<style>
  @keyframes grow-progress {
    from { transform: scaleX(0); }
    to   { transform: scaleX(1); }
  }

  .progress-bar {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 4px;
    background: var(--color-primary);
    transform-origin: left;

    /* Tie animation to scroll progress of nearest scroll container */
    animation: grow-progress linear;
    animation-timeline: scroll();
  }

  /* Explicit scroll container targeting */
  .progress-bar-explicit {
    animation: grow-progress linear;
    animation-timeline: scroll(nearest block);
    /* scroll(<scroller> <axis>)
       scroller: nearest | root | self
       axis:     block | inline | x | y  */
  }
</style>

<div class="progress-bar" aria-hidden="true"></div>
```

## View Timeline: Reveal on Scroll

```html
<style>
  @keyframes reveal {
    from {
      opacity: 0;
      transform: translateY(40px) scale(0.95);
    }
    to {
      opacity: 1;
      transform: translateY(0) scale(1);
    }
  }

  .card {
    /* Animate as the card enters the viewport */
    animation: reveal linear both;
    animation-timeline: view();

    /* Control when the animation starts and ends:
       entry 0%   = element's leading edge hits scrollport bottom
       entry 100% = element is fully inside scrollport
       The range below: start at 10% entry, finish at 40% entry */
    animation-range: entry 10% entry 40%;
  }

  /* Staggered reveals for a grid of cards */
  .card:nth-child(1) { animation-delay: 0ms; }
  .card:nth-child(2) { animation-delay: 50ms; }
  .card:nth-child(3) { animation-delay: 100ms; }
</style>

<div class="card-grid">
  <article class="card">Card 1</article>
  <article class="card">Card 2</article>
  <article class="card">Card 3</article>
</div>
```

## Parallax Effect with Named Scroll Timeline

```html
<style>
  .parallax-container {
    /* Name this element's scroll timeline */
    scroll-timeline-name: --hero-scroll;
    scroll-timeline-axis: block;
    overflow-y: auto;
    height: 100vh;
  }

  @keyframes parallax-bg {
    from { transform: translateY(0); }
    to   { transform: translateY(-30%); }
  }

  @keyframes parallax-text {
    from { transform: translateY(0); opacity: 1; }
    to   { transform: translateY(-50%); opacity: 0; }
  }

  .hero-bg {
    animation: parallax-bg linear;
    animation-timeline: --hero-scroll;
  }

  .hero-text {
    animation: parallax-text linear;
    animation-timeline: --hero-scroll;
    animation-range: 0% 50%;  /* Only animate first half of scroll */
  }
</style>

<div class="parallax-container">
  <div class="hero-bg">
    <h1 class="hero-text">Parallax Hero</h1>
  </div>
  <main>
    <!-- Scrollable content -->
  </main>
</div>
```

## Sticky Header Shrink Animation

```html
<style>
  @keyframes shrink-header {
    from {
      height: 120px;
      font-size: 2rem;
      background: transparent;
    }
    to {
      height: 60px;
      font-size: 1rem;
      background: var(--color-surface);
      box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
  }

  .header {
    position: sticky;
    top: 0;
    z-index: 100;

    animation: shrink-header linear both;
    animation-timeline: scroll();
    /* Shrink over the first 200px of scroll */
    animation-range: 0px 200px;
  }
</style>
```

## JavaScript Polyfill for Older Browsers

```typescript
// lib/scroll-timeline-polyfill.ts
// The CSS scroll-timeline spec is supported in Chrome 115+.
// For Safari and Firefox, use the polyfill.

async function loadScrollTimelinePolyfill() {
  if ("ScrollTimeline" in window) {
    console.log("Native ScrollTimeline supported");
    return;
  }

  // Load the polyfill from CDN or npm
  // npm install scroll-timeline-polyfill
  await import("scroll-timeline-polyfill");
  console.log("ScrollTimeline polyfill loaded");
}

// Feature detection component
function ScrollAnimationWrapper({
  children,
  fallbackClass = "no-scroll-animation",
}: {
  children: React.ReactNode;
  fallbackClass?: string;
}) {
  const [supported, setSupported] = useState(false);

  useEffect(() => {
    // Check if animation-timeline is supported
    const test = document.createElement("div");
    test.style.cssText = "animation-timeline: scroll()";
    setSupported(test.style.animationTimeline !== "");

    if (!test.style.animationTimeline) {
      loadScrollTimelinePolyfill().then(() => setSupported(true));
    }
  }, []);

  return (
    <div className={supported ? "" : fallbackClass}>
      {children}
    </div>
  );
}

export { loadScrollTimelinePolyfill, ScrollAnimationWrapper };
```

## Comparison with JavaScript Alternatives

```
CSS scroll-timeline:
  + Zero JavaScript, runs on compositor thread
  + Silky smooth 60fps, never janky
  + Declarative, easy to maintain
  - Limited to CSS-expressible animations
  - Newer browser support (Chrome 115+, polyfill for others)

Intersection Observer + CSS classes:
  + Wide browser support
  + Binary trigger (visible/not visible)
  - Not smooth scroll-linked (just triggers)
  - Requires JavaScript

GSAP ScrollTrigger:
  + Full programmatic control
  + Pin, snap, batch, callbacks
  + Works everywhere
  - JavaScript dependency (~30 KB)
  - Runs on main thread

Framer Motion useScroll:
  + React-native integration
  + Spring physics
  - React only, main thread
```

| Feature | CSS scroll() | CSS view() | GSAP ScrollTrigger | IntersectionObserver |
|---|---|---|---|---|
| Thread | Compositor | Compositor | Main thread | Main thread |
| Smooth scroll-linked | Yes | Yes | Yes (scrub) | No (binary trigger) |
| Element tracking | No (container only) | Yes | Yes | Yes |
| Pin support | No | No | Yes | No |
| Bundle size | 0 KB | 0 KB | ~30 KB | 0 KB |
| Browser support | Chrome 115+ | Chrome 115+ | All | All modern |

Key patterns:
1. `scroll()` ties animation to scroll container progress (progress bar, parallax)
2. `view()` ties animation to an element entering/exiting the viewport (reveals)
3. `animation-range` controls exactly when the animation starts and ends
4. Named scroll timelines (`scroll-timeline-name`) allow cross-element linking
5. All scroll-driven CSS animations run on the compositor thread (guaranteed 60fps)
6. Use the polyfill for Safari/Firefox until native support ships
7. Fall back to IntersectionObserver for simple show/hide, GSAP for complex sequences"""
    ),
]
