"""Web Vitals and performance optimization."""

PAIRS = [
    (
        "frontend/core-web-vitals",
        "Explain Core Web Vitals (LCP, FID, CLS, INP) with measurement techniques, common causes of poor scores, and optimization strategies.",
        '''Core Web Vitals are Google\'s metrics for user experience: loading (LCP), interactivity (INP, replacing FID), and visual stability (CLS). They affect search rankings and directly correlate with user engagement.

```typescript
// --- Measuring Core Web Vitals ---

import { onLCP, onINP, onCLS, onFCP, onTTFB, type Metric } from 'web-vitals';

interface VitalReport {
  name: string;
  value: number;
  rating: 'good' | 'needs-improvement' | 'poor';
  delta: number;
  id: string;
  navigationType: string;
  entries: PerformanceEntry[];
}

// Report all Core Web Vitals
function initWebVitals(sendToAnalytics: (report: VitalReport) => void): void {
  // Largest Contentful Paint
  onLCP((metric: Metric) => {
    sendToAnalytics({
      name: 'LCP',
      value: metric.value,
      rating: metric.rating,
      delta: metric.delta,
      id: metric.id,
      navigationType: metric.navigationType,
      entries: metric.entries,
    });
  });

  // Interaction to Next Paint (replaces FID)
  onINP((metric: Metric) => {
    sendToAnalytics({
      name: 'INP',
      value: metric.value,
      rating: metric.rating,
      delta: metric.delta,
      id: metric.id,
      navigationType: metric.navigationType,
      entries: metric.entries,
    });
  });

  // Cumulative Layout Shift
  onCLS((metric: Metric) => {
    sendToAnalytics({
      name: 'CLS',
      value: metric.value,
      rating: metric.rating,
      delta: metric.delta,
      id: metric.id,
      navigationType: metric.navigationType,
      entries: metric.entries,
    });
  });

  // Additional metrics
  onFCP((metric: Metric) => {
    sendToAnalytics({
      name: 'FCP',
      value: metric.value,
      rating: metric.rating,
      delta: metric.delta,
      id: metric.id,
      navigationType: metric.navigationType,
      entries: metric.entries,
    });
  });

  onTTFB((metric: Metric) => {
    sendToAnalytics({
      name: 'TTFB',
      value: metric.value,
      rating: metric.rating,
      delta: metric.delta,
      id: metric.id,
      navigationType: metric.navigationType,
      entries: metric.entries,
    });
  });
}


// --- Custom Performance Observer ---

function observeLongTasks(): void {
  if (!('PerformanceObserver' in window)) return;

  const observer = new PerformanceObserver((list) => {
    for (const entry of list.getEntries()) {
      if (entry.duration > 50) {
        console.warn('Long task detected:', {
          duration: `${entry.duration.toFixed(1)}ms`,
          name: entry.name,
          startTime: entry.startTime,
        });
      }
    }
  });

  observer.observe({ type: 'longtask', buffered: true });
}

function observeLayoutShifts(): void {
  const observer = new PerformanceObserver((list) => {
    for (const entry of list.getEntries() as PerformanceEntry[]) {
      const layoutShift = entry as any;
      if (!layoutShift.hadRecentInput) {
        console.warn('Layout shift:', {
          value: layoutShift.value.toFixed(4),
          sources: layoutShift.sources?.map((s: any) => ({
            node: s.node?.nodeName,
            previousRect: s.previousRect,
            currentRect: s.currentRect,
          })),
        });
      }
    }
  });

  observer.observe({ type: 'layout-shift', buffered: true });
}
```

```typescript
// --- LCP Optimization ---

// Common LCP elements: hero images, large text blocks, video posters

// 1. Preload the LCP image
// <link rel="preload" as="image" href="/hero.avif" fetchpriority="high">

// 2. Next.js Image component with priority
import Image from 'next/image';

function HeroSection() {
  return (
    <section>
      {/* priority = preload + fetchpriority="high" */}
      <Image
        src="/hero.avif"
        alt="Hero image"
        width={1200}
        height={600}
        priority           // preloads the image
        sizes="100vw"
        quality={85}
      />
      <h1>Welcome to Our App</h1>
    </section>
  );
}


// 3. Inline critical CSS to avoid render-blocking stylesheets
// server.ts — inject critical CSS
function renderWithCriticalCSS(html: string, criticalCSS: string): string {
  return html.replace(
    '</head>',
    `<style>${criticalCSS}</style>
     <link rel="preload" href="/styles.css" as="style" onload="this.onload=null;this.rel='stylesheet'">
     <noscript><link rel="stylesheet" href="/styles.css"></noscript>
     </head>`
  );
}


// --- CLS Optimization ---

// 4. Always set dimensions on images and videos
// BAD:  <img src="photo.jpg">
// GOOD: <img src="photo.jpg" width="800" height="600">
// GOOD: <img src="photo.jpg" style="aspect-ratio: 4/3; width: 100%">

// 5. Reserve space for dynamic content
function AdSlot({ width, height }: { width: number; height: number }) {
  return (
    <div
      style={{
        width,
        height,
        minHeight: height,
        background: '#f3f4f6',
        contain: 'layout',
      }}
    >
      {/* Ad content loads here */}
    </div>
  );
}

// 6. Avoid inserting content above existing content
// Use CSS containment to prevent layout shifts from dynamic content
// .dynamic-content { contain: layout style paint; }


// --- INP Optimization ---

// 7. Break up long tasks with yielding
async function processLargeList(items: unknown[]): Promise<void> {
  const CHUNK_SIZE = 50;

  for (let i = 0; i < items.length; i += CHUNK_SIZE) {
    const chunk = items.slice(i, i + CHUNK_SIZE);

    // Process chunk
    for (const item of chunk) {
      processItem(item);
    }

    // Yield to the main thread between chunks
    if (i + CHUNK_SIZE < items.length) {
      await yieldToMainThread();
    }
  }
}

function yieldToMainThread(): Promise<void> {
  return new Promise(resolve => {
    // scheduler.yield() is preferred (Chrome 115+)
    if ('scheduler' in globalThis && 'yield' in (globalThis as any).scheduler) {
      (globalThis as any).scheduler.yield().then(resolve);
    } else {
      // Fallback: setTimeout(0) yields to the event loop
      setTimeout(resolve, 0);
    }
  });
}

// 8. Use requestIdleCallback for non-urgent work
function deferNonCriticalWork(callback: () => void): void {
  if ('requestIdleCallback' in window) {
    requestIdleCallback(callback, { timeout: 2000 });
  } else {
    setTimeout(callback, 100);
  }
}

// 9. Debounce input handlers
function useDebounceCallback<T extends (...args: any[]) => void>(
  callback: T,
  delay: number,
): T {
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  return useCallback((...args: Parameters<T>) => {
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => callback(...args), delay);
  }, [callback, delay]) as T;
}
```

```typescript
// --- Analytics: sending vitals to your backend ---

interface AnalyticsPayload {
  url: string;
  metrics: VitalReport[];
  connection: {
    effectiveType: string;
    rtt: number;
    downlink: number;
  } | null;
  device: {
    memory: number | null;
    cores: number;
    viewport: { width: number; height: number };
  };
  timestamp: number;
}

function sendToAnalytics(report: VitalReport): void {
  // Queue metrics and send in batch
  metricsQueue.push(report);

  if (metricsQueue.length >= 5 || report.name === 'CLS') {
    flushMetrics();
  }
}

const metricsQueue: VitalReport[] = [];

function flushMetrics(): void {
  if (metricsQueue.length === 0) return;

  const payload: AnalyticsPayload = {
    url: window.location.href,
    metrics: [...metricsQueue],
    connection: getConnectionInfo(),
    device: {
      memory: (navigator as any).deviceMemory ?? null,
      cores: navigator.hardwareConcurrency ?? 1,
      viewport: {
        width: window.innerWidth,
        height: window.innerHeight,
      },
    },
    timestamp: Date.now(),
  };

  metricsQueue.length = 0;

  // Use sendBeacon for reliability (survives page unload)
  if (navigator.sendBeacon) {
    navigator.sendBeacon(
      '/api/analytics/vitals',
      JSON.stringify(payload),
    );
  } else {
    fetch('/api/analytics/vitals', {
      method: 'POST',
      body: JSON.stringify(payload),
      keepalive: true,
    }).catch(() => {
      // Silently fail — analytics should never break the app
    });
  }
}

function getConnectionInfo() {
  const conn = (navigator as any).connection;
  if (!conn) return null;
  return {
    effectiveType: conn.effectiveType ?? 'unknown',
    rtt: conn.rtt ?? 0,
    downlink: conn.downlink ?? 0,
  };
}

// Send remaining metrics on page hide
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') {
    flushMetrics();
  }
});
```

| Metric | Good | Needs Improvement | Poor | Measures |
|---|---|---|---|---|
| LCP | <= 2.5s | <= 4.0s | > 4.0s | Loading speed (largest visible element) |
| INP | <= 200ms | <= 500ms | > 500ms | Responsiveness (worst interaction) |
| CLS | <= 0.1 | <= 0.25 | > 0.25 | Visual stability (layout shifts) |
| FCP | <= 1.8s | <= 3.0s | > 3.0s | First paint (any content) |
| TTFB | <= 800ms | <= 1800ms | > 1800ms | Server response time |

| LCP Problem | Solution |
|---|---|
| Large unoptimized image | Use AVIF/WebP, responsive `srcset`, `fetchpriority="high"` |
| Render-blocking CSS/JS | Inline critical CSS, defer non-critical JS |
| Slow server response | CDN, edge caching, server-side rendering |
| Client-side rendering | SSR/SSG, prerender the LCP element |
| Web fonts blocking render | `font-display: swap`, preload font files |

| CLS Problem | Solution |
|---|---|
| Images without dimensions | Always set `width`/`height` or `aspect-ratio` |
| Ads/embeds without reserved space | Use placeholder with fixed `min-height` |
| Dynamic content insertion | Use `contain: layout`, animate with `transform` |
| Web fonts causing reflow | `font-display: optional`, size-adjust |
| Late-loading CSS | Inline critical CSS, preload stylesheets |

Key patterns:
1. Use the `web-vitals` library for accurate, standardized measurement
2. LCP: preload hero images with `fetchpriority="high"`, inline critical CSS
3. INP: break long tasks with `scheduler.yield()`, debounce input handlers
4. CLS: always set image dimensions, reserve space for dynamic content
5. Use `navigator.sendBeacon()` for reliable analytics on page unload
6. Monitor with `PerformanceObserver` for long tasks and layout shift sources
7. Track connection quality alongside vitals for meaningful performance budgets'''
    ),
    (
        "frontend/bundle-optimization",
        "Show bundle optimization techniques including code splitting, tree shaking, dynamic imports, and bundle analysis for modern web applications.",
        '''Bundle optimization reduces the JavaScript shipped to users, directly improving load times and Core Web Vitals. The key techniques are code splitting, tree shaking, and lazy loading.

```typescript
// --- Code splitting with dynamic imports ---

// 1. Route-based splitting (React + React Router)
import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';

// Each route becomes its own chunk
const Home = lazy(() => import('./pages/Home'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Settings = lazy(() => import('./pages/Settings'));
const AdminPanel = lazy(() =>
  import('./pages/AdminPanel').then(module => ({
    default: module.AdminPanel,  // named export
  }))
);

function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<PageSkeleton />}>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/admin/*" element={<AdminPanel />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}


// 2. Component-level splitting (heavy components)
const MarkdownEditor = lazy(() => import('./components/MarkdownEditor'));
const ChartDashboard = lazy(() => import('./components/ChartDashboard'));
const PDFViewer = lazy(() => import('./components/PDFViewer'));

function DocumentView({ type }: { type: 'markdown' | 'chart' | 'pdf' }) {
  return (
    <Suspense fallback={<ComponentSkeleton />}>
      {type === 'markdown' && <MarkdownEditor />}
      {type === 'chart' && <ChartDashboard />}
      {type === 'pdf' && <PDFViewer />}
    </Suspense>
  );
}


// 3. Preloading on hover/focus (user intent detection)
function NavLink({ to, children, componentImport }: {
  to: string;
  children: React.ReactNode;
  componentImport: () => Promise<unknown>;
}) {
  function handleMouseEnter() {
    // Start loading the chunk when user hovers the link
    componentImport();
  }

  return (
    <Link
      to={to}
      onMouseEnter={handleMouseEnter}
      onFocus={handleMouseEnter}
    >
      {children}
    </Link>
  );
}

// Usage:
// <NavLink to="/dashboard" componentImport={() => import('./pages/Dashboard')}>
//   Dashboard
// </NavLink>
```

```typescript
// --- Tree shaking and side-effect-free imports ---

// BAD: imports entire lodash (~70KB)
// import _ from 'lodash';
// const result = _.debounce(fn, 300);

// GOOD: tree-shakeable import (~1KB)
import debounce from 'lodash-es/debounce';

// BEST: native alternative (0KB added)
function debounceNative<T extends (...args: any[]) => void>(
  fn: T,
  ms: number,
): (...args: Parameters<T>) => void {
  let timer: ReturnType<typeof setTimeout>;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}


// Barrel file anti-pattern (kills tree shaking)
// BAD: components/index.ts that re-exports everything
// export { Button } from './Button';
// export { Modal } from './Modal';     // <-- always bundled!
// export { Chart } from './Chart';     // <-- 200KB!

// Importing from barrel: import { Button } from './components';
// ^ Bundles ALL exports even if you only use Button

// GOOD: direct imports
// import { Button } from './components/Button';


// --- Vite/webpack configuration for optimization ---

// vite.config.ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { visualizer } from 'rollup-plugin-visualizer';

export default defineConfig({
  plugins: [
    react(),
    visualizer({
      filename: 'dist/bundle-stats.html',
      gzipSize: true,
      brotliSize: true,
    }),
  ],
  build: {
    rollupOptions: {
      output: {
        // Manual chunk splitting
        manualChunks: {
          // Vendor: large stable libraries in their own chunk
          'vendor-react': ['react', 'react-dom'],
          'vendor-router': ['react-router-dom'],
          'vendor-query': ['@tanstack/react-query'],
          'vendor-charts': ['recharts', 'd3-scale', 'd3-shape'],
        },
      },
    },
    // Target modern browsers for smaller output
    target: 'es2022',
    // Enable minification
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: true,     // remove console.log in production
        drop_debugger: true,
        passes: 2,
      },
    },
    // Report compressed sizes
    reportCompressedSize: true,
    // Chunk size warning limit
    chunkSizeWarningLimit: 250,  // KB
  },
});
```

```typescript
// --- Advanced: module preloading and resource hints ---

// next.config.js — Next.js optimization
const nextConfig = {
  experimental: {
    optimizePackageImports: [
      '@heroicons/react',   // only bundles used icons
      'lucide-react',
      'date-fns',
      '@radix-ui/react-icons',
    ],
  },
  // Transpile specific packages
  transpilePackages: ['@acme/ui'],
  webpack: (config: any, { isServer }: { isServer: boolean }) => {
    if (!isServer) {
      // Replace heavy packages with lighter alternatives
      config.resolve.alias = {
        ...config.resolve.alias,
        'moment': 'dayjs',
      };
    }
    return config;
  },
};


// --- Script loading strategies ---

// 1. Defer non-critical scripts
function loadScript(src: string, options?: {
  async?: boolean;
  defer?: boolean;
  type?: string;
}): Promise<void> {
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = src;
    script.async = options?.async ?? true;
    script.defer = options?.defer ?? false;
    if (options?.type) script.type = options.type;
    script.onload = () => resolve();
    script.onerror = reject;
    document.head.appendChild(script);
  });
}

// 2. Load analytics after page is interactive
function loadAnalyticsDeferred(): void {
  if ('requestIdleCallback' in window) {
    requestIdleCallback(() => {
      loadScript('https://analytics.example.com/script.js');
    });
  } else {
    setTimeout(() => {
      loadScript('https://analytics.example.com/script.js');
    }, 3000);
  }
}

// 3. Import maps for CDN-hosted shared dependencies
// <script type="importmap">
// {
//   "imports": {
//     "react": "https://esm.sh/react@19",
//     "react-dom": "https://esm.sh/react-dom@19"
//   }
// }
// </script>


// --- Bundle analysis script ---

// package.json scripts
// "analyze": "ANALYZE=true next build"
// "analyze:vite": "vite build && open dist/bundle-stats.html"

// Common heavy dependencies to watch:
// - moment.js (330KB) -> dayjs (2KB) or date-fns (tree-shakeable)
// - lodash (70KB) -> lodash-es or native
// - chart.js (200KB) -> lightweight alternatives or lazy load
// - @mui/material -> import specific components
// - aws-sdk -> @aws-sdk/client-* (v3, modular)
```

| Technique | Impact | Effort | When to Use |
|---|---|---|---|
| Route-based code splitting | High | Low | Always (React.lazy + Suspense) |
| Component-level splitting | Medium | Low | Heavy components (charts, editors) |
| Tree shaking | High | None (automatic) | Ensure ESM imports, avoid barrel files |
| Vendor chunk splitting | Medium | Low | Large stable dependencies |
| Dynamic imports | High | Low | Features used by minority of users |
| Preloading on hover | Medium | Low | Navigation links, tabs |
| Import maps | Low | Medium | CDN-hosted shared deps |
| Module replacement | Varies | Medium | Replacing heavy libs (moment -> dayjs) |

| Bundle Budget | Target | Metric |
|---|---|---|
| Initial JS | < 150 KB gzipped | All JS loaded on first page |
| Per-route JS | < 50 KB gzipped | Additional JS per route |
| Total JS | < 300 KB gzipped | All JS across all routes |
| Main thread work | < 3.5s | TBT (Total Blocking Time) |
| Third-party JS | < 50 KB gzipped | Analytics, ads, widgets |

Key patterns:
1. Route-based splitting with `React.lazy` is the highest-impact, lowest-effort optimization
2. Avoid barrel files (`index.ts` re-exports) — they defeat tree shaking
3. Import from `lodash-es/specificFunction` instead of `lodash`
4. Split vendor chunks (`react`, `router`, `query`) for better cache utilization
5. Preload chunks on hover/focus for perceived instant navigation
6. Use `rollup-plugin-visualizer` or `@next/bundle-analyzer` to find bloat
7. Set bundle budgets and fail CI builds when exceeded'''
    ),
    (
        "frontend/image-optimization",
        "Demonstrate image optimization strategies including lazy loading, responsive images, modern formats (AVIF, WebP), and blur-up placeholders.",
        '''Image optimization is often the single biggest performance win. Modern techniques combine format selection, responsive sizing, lazy loading, and progressive rendering for optimal user experience.

```html
<!-- --- Responsive images with srcset and sizes --- -->

<!-- Basic responsive image with srcset -->
<img
  src="/images/hero-800.jpg"
  srcset="
    /images/hero-400.avif 400w,
    /images/hero-800.avif 800w,
    /images/hero-1200.avif 1200w,
    /images/hero-1600.avif 1600w
  "
  sizes="
    (max-width: 640px) 100vw,
    (max-width: 1024px) 75vw,
    50vw
  "
  alt="Hero landscape"
  width="1600"
  height="900"
  loading="lazy"
  decoding="async"
  fetchpriority="high"
/>

<!-- Picture element for format negotiation + art direction -->
<picture>
  <!-- AVIF: smallest, best quality -->
  <source
    type="image/avif"
    srcset="
      /images/product-400.avif 400w,
      /images/product-800.avif 800w,
      /images/product-1200.avif 1200w
    "
    sizes="(max-width: 768px) 100vw, 50vw"
  />
  <!-- WebP: good fallback -->
  <source
    type="image/webp"
    srcset="
      /images/product-400.webp 400w,
      /images/product-800.webp 800w,
      /images/product-1200.webp 1200w
    "
    sizes="(max-width: 768px) 100vw, 50vw"
  />
  <!-- JPEG: universal fallback -->
  <img
    src="/images/product-800.jpg"
    alt="Product photo"
    width="1200"
    height="800"
    loading="lazy"
    decoding="async"
  />
</picture>
```

```typescript
// --- Next.js Image component (best practices) ---

import Image from 'next/image';

// Hero image: above the fold, priority loading
function HeroImage() {
  return (
    <Image
      src="/hero.jpg"
      alt="Hero banner"
      width={1600}
      height={900}
      priority              // preloads + fetchpriority="high"
      quality={85}
      sizes="100vw"
      placeholder="blur"    // blur-up placeholder
      blurDataURL={heroBlurDataURL}  // base64 tiny image
    />
  );
}

// Product grid: lazy loaded with blur placeholder
function ProductCard({ product }: { product: Product }) {
  return (
    <div className="product-card">
      <Image
        src={product.imageUrl}
        alt={product.name}
        width={400}
        height={400}
        sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 25vw"
        placeholder="blur"
        blurDataURL={product.blurHash}
        quality={80}
        className="product-image"
        // loading="lazy" is default for non-priority images
      />
      <h3>{product.name}</h3>
    </div>
  );
}


// --- Generate blur placeholder (build time or server) ---

import sharp from 'sharp';

async function generateBlurDataURL(imagePath: string): Promise<string> {
  const buffer = await sharp(imagePath)
    .resize(10, 10, { fit: 'inside' })
    .blur()
    .toBuffer();

  return `data:image/jpeg;base64,${buffer.toString('base64')}`;
}

// Or use blurhash for compact placeholders
import { encode } from 'blurhash';
import { createCanvas, loadImage } from 'canvas';

async function generateBlurhash(imagePath: string): Promise<string> {
  const image = await loadImage(imagePath);
  const canvas = createCanvas(32, 32);
  const ctx = canvas.getContext('2d');
  ctx.drawImage(image, 0, 0, 32, 32);
  const imageData = ctx.getImageData(0, 0, 32, 32);

  return encode(imageData.data, imageData.width, imageData.height, 4, 3);
}
```

```typescript
// --- Custom lazy loading with IntersectionObserver ---

function useLazyImage(
  src: string,
  options?: {
    rootMargin?: string;
    threshold?: number;
    placeholder?: string;
  },
): {
  ref: React.RefObject<HTMLImageElement>;
  loaded: boolean;
  currentSrc: string;
} {
  const imgRef = useRef<HTMLImageElement>(null);
  const [loaded, setLoaded] = useState(false);
  const [currentSrc, setCurrentSrc] = useState(
    options?.placeholder ?? 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg"%3E%3C/svg%3E'
  );

  useEffect(() => {
    const img = imgRef.current;
    if (!img) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            // Preload the image
            const fullImg = new window.Image();
            fullImg.onload = () => {
              setCurrentSrc(src);
              setLoaded(true);
            };
            fullImg.src = src;
            observer.unobserve(entry.target);
          }
        });
      },
      {
        rootMargin: options?.rootMargin ?? '200px',  // start loading 200px before viewport
        threshold: options?.threshold ?? 0,
      }
    );

    observer.observe(img);
    return () => observer.disconnect();
  }, [src, options?.rootMargin, options?.threshold]);

  return { ref: imgRef, loaded, currentSrc };
}


// --- Image optimization build pipeline ---

// sharp-based image pipeline (Node.js build step)
import sharp from 'sharp';
import { glob } from 'glob';
import path from 'path';

interface ImageVariant {
  width: number;
  format: 'avif' | 'webp' | 'jpeg';
  quality: number;
}

const VARIANTS: ImageVariant[] = [
  { width: 400,  format: 'avif', quality: 60 },
  { width: 800,  format: 'avif', quality: 65 },
  { width: 1200, format: 'avif', quality: 70 },
  { width: 1600, format: 'avif', quality: 75 },
  { width: 400,  format: 'webp', quality: 70 },
  { width: 800,  format: 'webp', quality: 75 },
  { width: 1200, format: 'webp', quality: 80 },
  { width: 1600, format: 'webp', quality: 80 },
  { width: 800,  format: 'jpeg', quality: 80 },
];

async function processImages(inputDir: string, outputDir: string): Promise<void> {
  const images = await glob(`${inputDir}/**/*.{jpg,jpeg,png}`);

  for (const imagePath of images) {
    const baseName = path.parse(imagePath).name;

    for (const variant of VARIANTS) {
      const outputPath = path.join(
        outputDir,
        `${baseName}-${variant.width}.${variant.format}`
      );

      await sharp(imagePath)
        .resize(variant.width, null, {
          fit: 'inside',
          withoutEnlargement: true,
        })
        .toFormat(variant.format, { quality: variant.quality })
        .toFile(outputPath);
    }

    // Generate blur placeholder
    const blurPath = path.join(outputDir, `${baseName}-blur.json`);
    const blurData = await generateBlurDataURL(imagePath);
    await writeFile(blurPath, JSON.stringify({ blurDataURL: blurData }));
  }
}
```

| Format | Compression | Quality | Browser Support | Best For |
|---|---|---|---|---|
| AVIF | Best (50% smaller than JPEG) | Excellent | Chrome 85+, Firefox 93+, Safari 16.1+ | Photos, complex images |
| WebP | Good (25-35% smaller than JPEG) | Very good | Chrome 32+, Firefox 65+, Safari 14+ | Universal fallback |
| JPEG | Baseline | Good | Universal | Legacy fallback |
| PNG | Lossless | Perfect | Universal | Screenshots, transparency |
| SVG | N/A (vector) | Scalable | Universal | Icons, illustrations |

| Loading Attribute | Effect | Use When |
|---|---|---|
| `loading="lazy"` | Defers loading until near viewport | Below-the-fold images |
| `loading="eager"` | Loads immediately (default) | Above-the-fold images |
| `fetchpriority="high"` | Prioritizes in browser fetch queue | LCP image / hero image |
| `fetchpriority="low"` | Deprioritizes | Offscreen thumbnails |
| `decoding="async"` | Decodes off main thread | All images |

Key patterns:
1. Always serve AVIF with WebP and JPEG fallbacks using `<picture>` element
2. Use `srcset` + `sizes` so the browser picks the right resolution for each viewport
3. Set `width` and `height` attributes on every `<img>` to prevent CLS
4. `loading="lazy"` for below-the-fold images, `priority` for hero/LCP images
5. Generate blur placeholders (BlurHash or tiny base64) for progressive loading
6. Build-time image pipeline with sharp: resize, format, compress, blur placeholder
7. Preload LCP images: `<link rel="preload" as="image" href="hero.avif" fetchpriority="high">`'''
    ),
    (
        "frontend/font-loading-strategies",
        "Show font loading strategies including font-display, preloading, subsetting, and variable fonts for optimal performance.",
        '''Web fonts can block rendering and cause layout shifts (FOIT/FOUT). Proper font loading strategies minimize these issues while maintaining design fidelity.

```css
/* --- @font-face with font-display strategies --- */

/* font-display values:
   auto     — browser decides (usually block)
   block    — invisible text up to 3s, then fallback (FOIT)
   swap     — fallback immediately, swap when loaded (FOUT)
   fallback — short block (100ms), then fallback, swap within 3s
   optional — short block (100ms), then fallback, may never swap
*/

/* RECOMMENDED: swap for body text, optional for non-critical */
@font-face {
  font-family: 'Inter';
  src: url('/fonts/inter-variable.woff2') format('woff2-variations');
  font-weight: 100 900;         /* variable font weight range */
  font-style: normal;
  font-display: swap;           /* show fallback immediately */
  unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC,
                 U+2000-206F, U+2074, U+20AC, U+2122, U+2191, U+2193;
}

/* Optional for hero/display fonts — acceptable if they never load */
@font-face {
  font-family: 'Playfair Display';
  src: url('/fonts/playfair-display-700.woff2') format('woff2');
  font-weight: 700;
  font-style: normal;
  font-display: optional;       /* may not swap if too slow */
}


/* --- Size-adjust to minimize layout shift --- */

/* Match the fallback font metrics to the web font */
@font-face {
  font-family: 'Inter Fallback';
  src: local('Arial');
  size-adjust: 107.64%;         /* match Inter's metrics */
  ascent-override: 90.49%;
  descent-override: 22.56%;
  line-gap-override: 0%;
}

body {
  font-family: 'Inter', 'Inter Fallback', system-ui, sans-serif;
}
```

```html
<!-- --- Preloading fonts --- -->

<!-- Preload the most critical font file (above-the-fold text) -->
<link
  rel="preload"
  href="/fonts/inter-variable.woff2"
  as="font"
  type="font/woff2"
  crossorigin
/>
<!-- crossorigin is REQUIRED for font preloading -->

<!-- DNS prefetch for external font providers -->
<link rel="dns-prefetch" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />

<!-- Self-host Google Fonts instead of using their CDN -->
<!-- Download using: google-webfonts-helper.herokuapp.com -->
```

```typescript
// --- Font loading with Font Loading API ---

// Check if fonts are loaded before showing content
async function waitForFonts(): Promise<void> {
  if (!document.fonts) return;

  // Wait for specific fonts
  try {
    await Promise.all([
      document.fonts.load('400 1em Inter'),
      document.fonts.load('700 1em Inter'),
    ]);
    document.documentElement.classList.add('fonts-loaded');
  } catch {
    // Fonts failed to load — fallback is already showing
    document.documentElement.classList.add('fonts-failed');
  }
}

// Progressive font loading (two-stage)
async function loadFontsProgressively(): Promise<void> {
  // Stage 1: Load critical subset (Latin characters only)
  const criticalFont = new FontFace('Inter', 'url(/fonts/inter-latin.woff2)', {
    weight: '400',
    style: 'normal',
    unicodeRange: 'U+0000-00FF',
    display: 'swap',
  });

  try {
    const loaded = await criticalFont.load();
    document.fonts.add(loaded);
    document.documentElement.classList.add('fonts-stage-1');

    // Stage 2: Load remaining characters (non-blocking)
    requestIdleCallback(async () => {
      const fullFont = new FontFace('Inter', 'url(/fonts/inter-full.woff2)', {
        weight: '100 900',
        style: 'normal',
        display: 'swap',
      });

      try {
        const fullLoaded = await fullFont.load();
        document.fonts.add(fullLoaded);
        document.documentElement.classList.add('fonts-stage-2');
      } catch {
        // Extended characters not available — acceptable degradation
      }
    });
  } catch {
    // Critical font failed — system fonts are the fallback
  }
}


// --- Font subsetting build script ---

// Subset fonts at build time to reduce file size
// Requires: pip install fonttools brotli

// subset.sh equivalent in TypeScript/Node:
import { execSync } from 'child_process';

interface SubsetConfig {
  inputFont: string;
  outputFont: string;
  unicodes: string;
  features: string[];
}

function subsetFont(config: SubsetConfig): void {
  const { inputFont, outputFont, unicodes, features } = config;

  const featuresFlag = features.map(f => `--layout-features+=${f}`).join(' ');

  execSync(
    `pyftsubset "${inputFont}" ` +
    `--output-file="${outputFont}" ` +
    `--flavor=woff2 ` +
    `--unicodes="${unicodes}" ` +
    `${featuresFlag} ` +
    `--no-hinting ` +
    `--desubroutinize`
  );
}

// Create Latin-only subset (~15KB vs ~90KB full)
subsetFont({
  inputFont: 'fonts/Inter-Variable.ttf',
  outputFont: 'public/fonts/inter-latin.woff2',
  unicodes: 'U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+2000-206F,U+2074,U+20AC,U+2122',
  features: ['kern', 'liga', 'calt', 'ss01', 'ss02'],
});


// --- Variable fonts: single file for all weights ---

/*
  Variable fonts contain all weight/width/slant variations
  in a single file, replacing multiple static font files.

  1 variable font file (~90KB) vs 6 static files (~40KB each = 240KB)
*/

/* CSS for variable font */
/*
@font-face {
  font-family: 'Inter';
  src: url('/fonts/inter-variable.woff2') format('woff2-variations');
  font-weight: 100 900;
  font-stretch: 75% 125%;
  font-style: oblique 0deg 10deg;
  font-display: swap;
}

.heading { font-weight: 800; }
.body    { font-weight: 400; }
.light   { font-weight: 300; }
.caption { font-weight: 200; font-stretch: 90%; }

// Animate weight (variable fonts only)
.fancy:hover {
  font-weight: 700;
  transition: font-weight 0.3s ease;
}
*/
```

| Strategy | FOIT | FOUT | CLS | Speed |
|---|---|---|---|---|
| `font-display: block` | Yes (up to 3s) | After 3s | Low | Slow |
| `font-display: swap` | No | Yes | Possible | Fast |
| `font-display: fallback` | 100ms | Yes (within 3s) | Low | Good |
| `font-display: optional` | 100ms | Maybe | Minimal | Best |
| Preload + swap | No | Brief | Low | Very fast |
| Preload + optional | 100ms | Unlikely | Minimal | Fastest |

| Optimization | Size Reduction | Effort |
|---|---|---|
| WOFF2 compression | 30% vs WOFF | None (format choice) |
| Latin-only subset | 60-80% | Low (build step) |
| Variable font | 50%+ vs multiple statics | Low (font choice) |
| Remove unused features | 5-15% | Low (subsetting) |
| Self-hosting | Eliminates DNS + connection | Medium |
| `size-adjust` fallback | N/A (reduces CLS) | Medium |

Key patterns:
1. Use `font-display: swap` for body text, `optional` for decorative fonts
2. Preload the critical font file: `<link rel="preload" as="font" crossorigin>`
3. Self-host fonts instead of using Google Fonts CDN (fewer connections, better caching)
4. Subset fonts to Latin characters at build time (pyftsubset) — 60-80% size reduction
5. Use variable fonts (single file for all weights) instead of multiple static files
6. Apply `size-adjust`, `ascent-override`, `descent-override` to minimize FOUT shift
7. Two-stage loading: critical Latin subset first, full charset in `requestIdleCallback`'''
    ),
    (
        "frontend/performance-monitoring",
        "Build a performance monitoring system using the web-vitals library, Real User Monitoring (RUM), and custom performance marks.",
        '''A comprehensive performance monitoring system combines Core Web Vitals collection, custom performance marks, Real User Monitoring (RUM) aggregation, and alerting to catch regressions.

```typescript
// --- Performance monitoring client ---

import { onLCP, onINP, onCLS, onFCP, onTTFB, type Metric } from 'web-vitals';

interface PerformancePayload {
  sessionId: string;
  pageUrl: string;
  timestamp: number;
  vitals: Record<string, {
    value: number;
    rating: string;
    entries: any[];
  }>;
  marks: Array<{
    name: string;
    startTime: number;
    duration: number;
  }>;
  resources: Array<{
    name: string;
    type: string;
    duration: number;
    transferSize: number;
    encodedSize: number;
  }>;
  connection: {
    effectiveType: string;
    rtt: number;
    downlink: number;
    saveData: boolean;
  } | null;
  device: {
    memory: number;
    cores: number;
    devicePixelRatio: number;
    viewport: { width: number; height: number };
  };
}

class PerformanceMonitor {
  private sessionId: string;
  private vitals: PerformancePayload['vitals'] = {};
  private marks: PerformancePayload['marks'] = [];
  private reportUrl: string;
  private sampleRate: number;
  private shouldSample: boolean;

  constructor(options: {
    reportUrl: string;
    sampleRate?: number;  // 0.0 to 1.0
  }) {
    this.sessionId = crypto.randomUUID();
    this.reportUrl = options.reportUrl;
    this.sampleRate = options.sampleRate ?? 1.0;
    this.shouldSample = Math.random() < this.sampleRate;

    if (this.shouldSample) {
      this.initVitals();
      this.initResourceObserver();
      this.initLongTaskObserver();
    }
  }

  private initVitals(): void {
    const recordVital = (metric: Metric) => {
      this.vitals[metric.name] = {
        value: metric.value,
        rating: metric.rating,
        entries: metric.entries.map(e => ({
          name: e.name,
          startTime: e.startTime,
          duration: (e as any).duration ?? 0,
        })),
      };
    };

    onLCP(recordVital);
    onINP(recordVital);
    onCLS(recordVital);
    onFCP(recordVital);
    onTTFB(recordVital);
  }

  private initResourceObserver(): void {
    if (!('PerformanceObserver' in window)) return;

    const observer = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        const resource = entry as PerformanceResourceTiming;
        // Only track significant resources
        if (resource.transferSize > 1024) {
          this.marks.push({
            name: resource.name,
            startTime: resource.startTime,
            duration: resource.duration,
          });
        }
      }
    });

    observer.observe({ type: 'resource', buffered: true });
  }

  private initLongTaskObserver(): void {
    if (!('PerformanceObserver' in window)) return;

    try {
      const observer = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          this.marks.push({
            name: `long-task`,
            startTime: entry.startTime,
            duration: entry.duration,
          });
        }
      });
      observer.observe({ type: 'longtask', buffered: true });
    } catch {
      // Long task observer not supported
    }
  }

  // --- Custom performance marks ---

  mark(name: string): void {
    if (!this.shouldSample) return;
    performance.mark(name);
  }

  measure(name: string, startMark: string, endMark?: string): void {
    if (!this.shouldSample) return;
    try {
      const measure = performance.measure(
        name,
        startMark,
        endMark ?? undefined,
      );
      this.marks.push({
        name: measure.name,
        startTime: measure.startTime,
        duration: measure.duration,
      });
    } catch {
      // Marks may not exist
    }
  }

  // Track component render times
  measureComponent(componentName: string): {
    start: () => void;
    end: () => void;
  } {
    const startMark = `${componentName}-start`;
    const endMark = `${componentName}-end`;

    return {
      start: () => this.mark(startMark),
      end: () => {
        this.mark(endMark);
        this.measure(`component:${componentName}`, startMark, endMark);
      },
    };
  }

  // --- Report ---

  private buildPayload(): PerformancePayload {
    const conn = (navigator as any).connection;

    return {
      sessionId: this.sessionId,
      pageUrl: window.location.href,
      timestamp: Date.now(),
      vitals: this.vitals,
      marks: this.marks,
      resources: this.getSignificantResources(),
      connection: conn ? {
        effectiveType: conn.effectiveType ?? '4g',
        rtt: conn.rtt ?? 0,
        downlink: conn.downlink ?? 10,
        saveData: conn.saveData ?? false,
      } : null,
      device: {
        memory: (navigator as any).deviceMemory ?? 4,
        cores: navigator.hardwareConcurrency ?? 4,
        devicePixelRatio: window.devicePixelRatio ?? 1,
        viewport: {
          width: window.innerWidth,
          height: window.innerHeight,
        },
      },
    };
  }

  private getSignificantResources(): PerformancePayload['resources'] {
    return performance.getEntriesByType('resource')
      .filter((r: any) => r.transferSize > 5000)
      .slice(0, 50)
      .map((r: any) => ({
        name: r.name,
        type: r.initiatorType,
        duration: r.duration,
        transferSize: r.transferSize,
        encodedSize: r.encodedBodySize,
      }));
  }

  flush(): void {
    if (!this.shouldSample) return;

    const payload = this.buildPayload();

    if (navigator.sendBeacon) {
      navigator.sendBeacon(
        this.reportUrl,
        JSON.stringify(payload),
      );
    } else {
      fetch(this.reportUrl, {
        method: 'POST',
        body: JSON.stringify(payload),
        keepalive: true,
        headers: { 'Content-Type': 'application/json' },
      }).catch(() => {});
    }
  }
}

// Initialize
const perfMonitor = new PerformanceMonitor({
  reportUrl: '/api/perf/report',
  sampleRate: 0.1,  // 10% of sessions
});

// Auto-report on page hide
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') {
    perfMonitor.flush();
  }
});
```

```typescript
// --- React performance hooks ---

import { useRef, useEffect, useCallback } from 'react';

// Hook to measure component mount/render time
function useComponentPerf(componentName: string): void {
  const renderCount = useRef(0);
  const startTime = useRef(performance.now());

  useEffect(() => {
    const duration = performance.now() - startTime.current;
    renderCount.current++;

    if (renderCount.current === 1) {
      perfMonitor.marks.push({
        name: `mount:${componentName}`,
        startTime: startTime.current,
        duration,
      });
    } else {
      perfMonitor.marks.push({
        name: `rerender:${componentName}`,
        startTime: startTime.current,
        duration,
      });
    }

    // Reset for next render
    startTime.current = performance.now();
  });
}


// Hook to measure async operations
function useAsyncPerf() {
  return useCallback(<T>(name: string, operation: () => Promise<T>): Promise<T> => {
    const start = performance.now();

    return operation().then(
      (result) => {
        perfMonitor.marks.push({
          name: `async:${name}`,
          startTime: start,
          duration: performance.now() - start,
        });
        return result;
      },
      (error) => {
        perfMonitor.marks.push({
          name: `async:${name}:error`,
          startTime: start,
          duration: performance.now() - start,
        });
        throw error;
      },
    );
  }, []);
}


// Usage
function ProductList() {
  useComponentPerf('ProductList');
  const trackAsync = useAsyncPerf();

  async function loadProducts() {
    const products = await trackAsync('loadProducts', () =>
      fetch('/api/products').then(r => r.json())
    );
    return products;
  }

  // ...
}
```

```typescript
// --- Server-side aggregation and alerting ---

// Aggregate RUM data for dashboards and alerts

interface AggregatedMetrics {
  metric: string;
  period: string;     // '2024-01-15T14:00:00Z'
  p50: number;
  p75: number;
  p90: number;
  p99: number;
  count: number;
  goodPercent: number;
  needsImprovementPercent: number;
  poorPercent: number;
}

function aggregateVitals(
  reports: PerformancePayload[],
  metricName: string,
): AggregatedMetrics {
  const values = reports
    .filter(r => r.vitals[metricName])
    .map(r => r.vitals[metricName].value)
    .sort((a, b) => a - b);

  if (values.length === 0) {
    return {
      metric: metricName,
      period: new Date().toISOString(),
      p50: 0, p75: 0, p90: 0, p99: 0,
      count: 0,
      goodPercent: 0,
      needsImprovementPercent: 0,
      poorPercent: 0,
    };
  }

  const ratings = reports
    .filter(r => r.vitals[metricName])
    .map(r => r.vitals[metricName].rating);

  return {
    metric: metricName,
    period: new Date().toISOString(),
    p50: percentile(values, 50),
    p75: percentile(values, 75),
    p90: percentile(values, 90),
    p99: percentile(values, 99),
    count: values.length,
    goodPercent: (ratings.filter(r => r === 'good').length / ratings.length) * 100,
    needsImprovementPercent:
      (ratings.filter(r => r === 'needs-improvement').length / ratings.length) * 100,
    poorPercent: (ratings.filter(r => r === 'poor').length / ratings.length) * 100,
  };
}

function percentile(sortedValues: number[], p: number): number {
  const index = Math.ceil((p / 100) * sortedValues.length) - 1;
  return sortedValues[Math.max(0, index)];
}


// --- Alert on regressions ---

interface PerformanceBudget {
  metric: string;
  p75Threshold: number;
  poorPercentThreshold: number;
}

const BUDGETS: PerformanceBudget[] = [
  { metric: 'LCP',  p75Threshold: 2500,  poorPercentThreshold: 10 },
  { metric: 'INP',  p75Threshold: 200,   poorPercentThreshold: 10 },
  { metric: 'CLS',  p75Threshold: 0.1,   poorPercentThreshold: 10 },
  { metric: 'FCP',  p75Threshold: 1800,  poorPercentThreshold: 15 },
  { metric: 'TTFB', p75Threshold: 800,   poorPercentThreshold: 20 },
];

function checkBudgets(aggregated: AggregatedMetrics[]): string[] {
  const violations: string[] = [];

  for (const metrics of aggregated) {
    const budget = BUDGETS.find(b => b.metric === metrics.metric);
    if (!budget) continue;

    if (metrics.p75 > budget.p75Threshold) {
      violations.push(
        `${metrics.metric} p75 (${metrics.p75.toFixed(0)}) exceeds budget (${budget.p75Threshold})`
      );
    }

    if (metrics.poorPercent > budget.poorPercentThreshold) {
      violations.push(
        `${metrics.metric} poor rate (${metrics.poorPercent.toFixed(1)}%) exceeds threshold (${budget.poorPercentThreshold}%)`
      );
    }
  }

  return violations;
}
```

| Metric | What It Measures | Good p75 | Tool |
|---|---|---|---|
| LCP | Largest content render | <= 2.5s | web-vitals, Lighthouse |
| INP | Interaction responsiveness | <= 200ms | web-vitals |
| CLS | Visual stability | <= 0.1 | web-vitals, Layout Instability API |
| FCP | First content paint | <= 1.8s | web-vitals, Paint Timing API |
| TTFB | Server response time | <= 800ms | web-vitals, Navigation Timing API |
| Long Tasks | Main thread blocking | < 50ms each | Long Tasks API |
| TBT | Total blocking time | < 200ms | Lighthouse (lab only) |

| RUM vs Lab Testing | RUM (Real User Monitoring) | Lab (Lighthouse/WebPageTest) |
|---|---|---|
| Data source | Real users in production | Simulated environment |
| Metrics available | CWV + custom marks | CWV + TBT + SI |
| Network conditions | Real (varies widely) | Controlled (throttled) |
| When to use | Continuous monitoring | Pre-deploy, CI/CD |
| Sample size | Thousands of sessions | Single run |
| Percentiles | p50, p75, p90, p99 | Single value |

Key patterns:
1. Sample RUM data (10-25% of sessions) to control volume; use `sendBeacon` for reliability
2. Track p75 (not average) for Core Web Vitals — matches Google\'s assessment
3. Custom performance marks track component render times and async operation durations
4. Set performance budgets and alert on regressions before they affect users
5. Segment data by connection type, device class, and page type for actionable insights
6. Use `PerformanceObserver` with `buffered: true` to capture metrics that fired before observer setup
7. Combine RUM (production monitoring) with lab testing (CI/CD gates) for complete coverage'''
    ),
]
